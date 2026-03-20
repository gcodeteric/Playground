"""
Bot de trading autonomo — ponto de entrada principal.

Implementa o loop infinito de trading com:
  - Ligacao ao Interactive Brokers com reconnect automatico
  - Deteccao de regime de mercado (BULL / BEAR / SIDEWAYS)
  - Sinais Kotegawa (SMA25 deviation + confirmacoes)
  - Grid trading com niveis escalonados por ATR
  - Gestao de risco autonoma com kill switches (3% diario, 10% mensal)
  - Persistencia de estado em grids_state.json
  - Notificacoes via Telegram
  - Resumo diario as 23:00

Logs e comentarios em portugues (PT-PT). Nomes de variaveis e funcoes em ingles.
"""

from __future__ import annotations

import asyncio
import atexit
import hashlib
import json
import logging
import math
import os
import signal
import sys
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Coroutine

# Garante event loop activo antes de qualquer import ib_insync (Python 3.14+)
if sys.version_info >= (3, 10):
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        _loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_loop)

# ---------------------------------------------------------------------------
# Modulos internos do projecto
# ---------------------------------------------------------------------------
from config import load_config, settings, AppConfig, BASE_DIR
from src.data_feed import IBConnection, DataFeed, get_warmup_missing_rules, validate_warmup
from src.contracts import InstrumentSpec, build_contract, parse_watchlist_entry
from src.market_hours import (
    SessionState,
    get_asset_type,
    get_session_state,
    is_market_open,
    minutes_to_close,
)
from src.signal_engine import (
    analyze,
    calculate_adx,
    calculate_rsi2,  # Finding 2
    detect_regime,
    kotegawa_signal,
    Regime,
    RegimeInfo,
    SignalResult,
)
from src.sector_rotation import sector_rotation_signal
from src.gap_fade import gap_fade_signal
from src.forex_mr import forex_mr_signal, ForexRegimeSwitch, forex_kill_switches
from src.forex_breakout import detect_forex_range, generate_breakout_signal
from src.futures_mr import futures_mr_signal, check_overnight_safety
from src.futures_trend import futures_trend_signal
from src.intl_etf_mr import intl_etf_signal
from src.commodity_mr import commodity_mr_signal
from src.bond_mr_hedge import bond_mr_signal, check_defensive_rotation_trigger
from src.options_premium import csp_signal, check_csp_exit
from src.pre_trade_gate import build_pre_trade_gate, critical_inputs_are_finite
from src.ib_requests import IBErrorPolicyDecision
from src.risk_manager import RiskManager
from src.grid_engine import GridEngine, Grid, GridLevel
from src.execution import OrderManager, OrderStatus
from src.logger import TradeLogger, TelegramNotifier


# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

_VERSION: str = "1.0.0"
_BANNER_PAPER: str = """
================================================================================
   BOT DE TRADING AUTONOMO  v{version}
   MODO: *** PAPER TRADING (SIMULACAO) ***
   Nenhuma ordem real sera enviada ao mercado.
================================================================================
"""
_BANNER_LIVE: str = """
================================================================================
   BOT DE TRADING AUTONOMO  v{version}
   MODO: *** TRADING REAL ***
   ATENCAO: Ordens reais serao enviadas ao mercado!
================================================================================
"""
_DAILY_SUMMARY_HOUR: int = 23  # Hora UTC para o resumo diario
_RISK_OF_RUIN_THRESHOLD: float = 0.01  # 1% — recusa arrancar se acima disto

# Watchlist por defeito (pode ser overridden via .env WATCHLIST)
_DEFAULT_WATCHLIST: list[str] = ["AAPL", "SPY", "QQQ", "XLU", "GDXJ", "VIX"]  # Finding 10

# Capital inicial por defeito para paper trading
_DEFAULT_PAPER_CAPITAL: float = 100_000.0
_DATA_FILE_DEFAULTS: dict[str, dict[str, Any] | str] = {
    "grids_state.json": {"version": 1, "grids": []},
    "trades_log.json": {"trades": []},
    "metrics.json": {"equity_curve": [], "metrics": {}},
    "reconciliation.log": "",
    "bot.log": "",
}
_RECONCILIATION_FETCH_ATTEMPTS = 3
_RECONCILIATION_FETCH_DELAY_SECONDS = 5
_INSTANCE_LOCK_FILENAME = "bot.instance.lock"


def _get_broker_lock_root() -> Path:
    """Directoria global para locks por contexto efectivo de broker."""
    return Path(tempfile.gettempdir()) / "bot-trading-instance-locks"
_EQUITY_BASELINE_KEYS = ("daily", "weekly", "monthly")


@dataclass(slots=True)
class BrokerPositionsObservation:
    """Resultado da leitura de posições com noção explícita de confiança."""

    state: str
    positions: list[dict[str, Any]]

SECTOR_ROTATION_CONFIG: dict[str, Any] = {
    "is_active": True,
    "momentum_period": 252,
    "skip_recent_days": 21,
    "top_n": 3,
    "rebalance_day": 1,
    "bear_filter_sma": 200,
    "safe_havens": ["XLU", "XLP", "GLD"],
    "universe_by_phase": {
        1: ["XLK", "XLF", "XLV", "XLE", "XLI", "XLY", "XLP", "XLU", "XLB", "XLC", "XLRE"],
        2: ["XLK", "XLF", "XLV", "XLE", "XLI", "XLY", "XLP", "XLU", "XLB", "XLC", "XLRE",
            "QQQ", "IWM", "GLD", "TLT", "HYG", "DBC"],
        3: ["XLK", "XLF", "XLV", "XLE", "XLI", "XLY", "XLP", "XLU", "XLB", "XLC", "XLRE",
            "QQQ", "IWM", "GLD", "TLT", "HYG", "DBC", "EFA", "EEM", "EZU", "EWJ"],
    },
}
GAP_FADE_CONFIG: dict[str, Any] = {
    "is_active": True,
    "min_gap_atr": 0.5,
    "max_gap_atr": 2.5,
    "min_fill_probability": 0.60,
    "min_body_ratio_fade": 0.35,
}
FOREX_MR_CONFIG: dict[str, Any] = {
    "is_active": False,
    "pairs_by_phase": {
        1: ["EURUSD"],
        2: ["EURUSD", "GBPUSD"],
        3: ["EURUSD", "GBPUSD", "USDJPY"],
    },
    "z_entry": -2.0,
    "sma_period": 20,
    "vol_lookback": 60,
    "rsi_period": 2,
    "rsi_entry": 10,
    "adx_ranging_max": 20.0,
    "adx_dead_max": 25.0,
    "chop_min_ranging": 55.0,
    "max_trades_per_month": 6,
    "max_hold_days": 5,
    "mr_grid_levels": 3,
    "mr_spacing_atr": 0.6,
    "stop_atr_mult_fx": 1.5,
    "weekend_gap_atr_mult": 1.5,
    "max_spread_atr_ratio": 3.0,
}
FOREX_BREAKOUT_CONFIG: dict[str, Any] = {
    "is_active": False,
    "adx_breakout_min": 25.0,
    "min_body_ratio": 0.60,
    "min_days_in_range": 15,
    "max_range_atr_mult": 3.0,
    "tp_atr_mult": 2.0,
    "range_quality_min": 0.6,
    "pyramid_enabled": True,
    "pyramid_max_adds": 2,
    "pyramid_trigger_atr": [1.0, 2.0],
    "pyramid_trail_stop_atr": 2.0,
}
FUTURES_MR_CONFIG: dict[str, Any] = {
    "is_active": False,
    "kairi_thresholds": {
        "MES": -3.0,
        "MNQ": -3.5,
        "M2K": -4.0,
        "MYM": -2.5,
        "MGC": -5.0,
        "MCL": -8.0,
    },
    "sma_lookback": 25,
    "roll_days_before": 5,
    "overnight_margin_mult": 1.5,
    "min_equity_futures": 2000,
}
INTL_ETF_MR_CONFIG: dict[str, Any] = {
    "is_active": False,
    "kairi_thresholds": {
        "EWG": -20.0,
        "EWU": -20.0,
        "EWJ": -15.0,
        "EEM": -25.0,
        "FXI": -25.0,
    },
    "sma_lookback": 25,
    "max_correlation": 0.70,
    "correlation_lookback": 60,
    "min_equity": 10000,
}
COMMODITY_MR_CONFIG: dict[str, Any] = {
    "is_active": False,
    "thresholds": {
        "GLD": {"kairi_long": -10.0, "kairi_short": 10.0, "sma": 50, "enabled": True},
        "IAU": {"kairi_long": -10.0, "kairi_short": 10.0, "sma": 50, "enabled": True},
        "SLV": {"kairi_long": -15.0, "kairi_short": 15.0, "sma": 25, "enabled": True},
        "USO": {"kairi_long": -35.0, "kairi_short": 20.0, "sma": 25, "enabled": True},
        "PDBC": {"kairi_long": -20.0, "kairi_short": 20.0, "sma": 25, "enabled": True},
        "UNG": {"enabled": False, "reason": "drag_contango_>30%/ano"},
    },
    "max_hold_days": 10,
}
FUTURES_TREND_CONFIG: dict[str, Any] = {
    "is_active": False,
    "adx_min": 25.0,
    "params_by_type": {
        "indices": {"ema_fast": 20, "ema_slow": 50, "donchian_period": 20},
        "metals": {"ema_fast": 10, "ema_slow": 30},
        "energy": {"ema_fast": 10, "ema_slow": 30, "adx_min": 30},
    },
    "chandelier_period": 22,
    "chandelier_atr_mult": 3.0,
    "pyramid_max_adds": 3,
    "pyramid_trigger_atr": 1.5,
    "min_equity": 10000,
}
BOND_MR_HEDGE_CONFIG: dict[str, Any] = {
    "is_active": False,
    "min_equity_eur": 2000,
    "kairi_thresholds": {"TLT": -15.0, "IEF": -10.0, "SHY": -7.0, "LQD": -15.0},
    "max_allocation_pct": 0.20,
    "defensive_min_days": 10,
    "bear_vix_proxy": 25.0,
    "correlation_lookback": 60,
}
OPTIONS_PREMIUM_CONFIG: dict[str, Any] = {
    "is_active": False,
    "min_equity": 25000,
    "target_delta": 0.15,
    "target_dte": 45,
    "close_at_profit_pct": 0.50,
    "close_at_dte": 21,
    "iv_rank_min": 30,
    "max_delta_phase4": 0.20,
    "allowed_symbols": ["SPY", "QQQ", "IWM"],
    "vix_max_sell": 30,
    "min_days_to_earnings": 21,
}
MODULE_CONFIG: dict[str, dict[str, Any]] = {
    "sector_rotation": SECTOR_ROTATION_CONFIG,
    "gap_fade": GAP_FADE_CONFIG,
    "forex_mr": FOREX_MR_CONFIG,
    "forex_breakout": FOREX_BREAKOUT_CONFIG,
    "futures_mr": FUTURES_MR_CONFIG,
    "intl_etf_mr": INTL_ETF_MR_CONFIG,
    "commodity_mr": COMMODITY_MR_CONFIG,
    "futures_trend": FUTURES_TREND_CONFIG,
    "bond_mr_hedge": BOND_MR_HEDGE_CONFIG,
    "options_premium": OPTIONS_PREMIUM_CONFIG,
}


# ---------------------------------------------------------------------------
# Logger do modulo
# ---------------------------------------------------------------------------

logger = logging.getLogger("main")
forex_regime = ForexRegimeSwitch()


# ---------------------------------------------------------------------------
# Configuracao de logging
# ---------------------------------------------------------------------------

def setup_logging(log_level: str = "INFO", *, log_dir: Path | None = None) -> None:
    """Configura o sistema de logging com formatadores e handlers adequados."""
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)

    # Formato detalhado com timestamp, modulo e nivel
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Handler para consola (stdout)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(numeric_level)
    console_handler.setFormatter(formatter)

    # Handler para ficheiro de log
    resolved_log_dir = log_dir or settings.data_dir
    resolved_log_dir.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(
        resolved_log_dir / "bot.log",
        encoding="utf-8",
        mode="a",
    )
    file_handler.setLevel(logging.DEBUG)  # ficheiro guarda tudo
    file_handler.setFormatter(formatter)

    # Configurar logger raiz
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    # Remover handlers anteriores para evitar duplicacao
    root_logger.handlers.clear()
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)

    # Silenciar loggers demasiado verbosos de bibliotecas externas
    logging.getLogger("ib_insync").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)
    logging.getLogger("aiohttp").setLevel(logging.WARNING)

    logger.info("Sistema de logging configurado — nivel: %s", log_level)


def ensure_data_dirs(data_dir: Path) -> None:
    """Garante a existencia da directoria de dados."""
    data_dir.mkdir(parents=True, exist_ok=True)


def create_initial_files(data_dir: Path) -> None:
    """Cria os ficheiros base na primeira execucao."""
    ensure_data_dirs(data_dir)
    for filename, initial_value in _DATA_FILE_DEFAULTS.items():
        path = data_dir / filename
        if path.exists():
            continue
        if isinstance(initial_value, str):
            path.write_text(initial_value, encoding="utf-8")
        else:
            path.write_text(
                json.dumps(initial_value, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )


def mask_account_id(account_id: str) -> str:
    """Mascara um identificador de conta para logs operacionais."""
    if len(account_id) <= 5:
        return account_id
    return f"{account_id[:2]}***{account_id[-4:]}"


# ---------------------------------------------------------------------------
# Funcoes auxiliares
# ---------------------------------------------------------------------------

def get_watchlist() -> list[str]:
    """Obtem a watchlist de simbolos a partir de .env ou usa o valor por defeito."""
    watchlist_env = os.getenv("WATCHLIST", "")
    if watchlist_env.strip():
        symbols = [s.strip() for s in watchlist_env.split(",") if s.strip()]
        if symbols:
            if not any(symbol.upper() in {"VIX", "^VIX"} for symbol in symbols):
                symbols.append("VIX")
            return symbols
    return _DEFAULT_WATCHLIST


def get_watchlist_specs() -> list[InstrumentSpec]:
    """Converte a watchlist textual numa lista tipada de instrumentos."""
    specs: list[InstrumentSpec] = []
    for entry in get_watchlist():
        specs.append(parse_watchlist_entry(entry))
    return specs


def get_initial_capital() -> float:
    """Obtem o capital inicial a partir de .env ou usa o valor por defeito."""
    capital_env = os.getenv("INITIAL_CAPITAL", "")
    if capital_env.strip():
        try:
            return float(capital_env)
        except ValueError:
            logger.warning(
                "Valor invalido para INITIAL_CAPITAL ('%s') — a usar defeito %.2f",
                capital_env, _DEFAULT_PAPER_CAPITAL,
            )
    return _DEFAULT_PAPER_CAPITAL


def is_grid_exhausted(grid: Grid) -> bool:
    """Verifica se uma grid esta esgotada (todos os niveis vendidos ou parados)."""
    for level in grid.levels:
        if level.status in ("pending", "bought"):
            return False
    return True


async def process_new_modules(
    spec: InstrumentSpec,
    bars_df: Any,
    market_data: dict[str, Any],
    risk_mgr: RiskManager,
    config: dict[str, dict[str, Any]],
    spy_closes: list[float] | None = None,
    tlt_closes: list[float] | None = None,
    defensive_state: dict[str, Any] | None = None,
    open_positions: list[str] | None = None,
    returns_map: dict[str, list[float]] | None = None,
) -> dict[str, Any] | None:
    """Router para os novos módulos baseado no asset_type."""
    del risk_mgr

    asset_type = spec.asset_type.value
    symbol = spec.symbol
    if defensive_state is None:
        defensive_state = {"mode": "NORMAL", "days_in_defensive": 0}
    if spy_closes is None:
        spy_closes = []
    if tlt_closes is None:
        tlt_closes = []
    if open_positions is None:
        open_positions = []
    if returns_map is None:
        returns_map = {}

    closes = bars_df["close"].tolist()
    highs = bars_df["high"].tolist()
    lows = bars_df["low"].tolist()
    volumes = bars_df["volume"].tolist() if "volume" in bars_df else []
    opens = bars_df["open"].tolist() if "open" in bars_df else []

    signal: dict[str, Any] | None = None

    if asset_type == "FX":
        adx_val = calculate_adx(highs, lows, closes, 14)
        active_module = forex_regime.get_active_module(adx_val)

        if active_module == "forex_mr" and config["forex_mr"]["is_active"]:
            blocked, reasons = forex_kill_switches(
                highs,
                lows,
                closes,
                datetime.now(timezone.utc).weekday(),
                config["forex_mr"],
            )
            if not blocked:
                signal = forex_mr_signal(
                    closes,
                    highs,
                    lows,
                    config["forex_mr"],
                    now_utc_hour=datetime.now(timezone.utc).hour,
                )
            else:
                logger.info(
                    "Módulo Forex MR bloqueado para %s: %s",
                    spec.display,
                    ", ".join(reasons),
                )

        elif active_module == "forex_breakout" and config["forex_breakout"]["is_active"]:
            range_info = detect_forex_range(
                highs,
                lows,
                closes,
                config["forex_breakout"],
            )
            signal = generate_breakout_signal(
                closes,
                opens,
                highs,
                lows,
                range_info,
                config["forex_breakout"],
            )

    elif asset_type == "FUT":
        adx_val = calculate_adx(highs, lows, closes, 14)
        if adx_val < 25 and config["futures_mr"]["is_active"]:
            signal = futures_mr_signal(symbol, closes, highs, lows, config["futures_mr"])
        elif adx_val >= 25 and config["futures_trend"]["is_active"]:
            sym_type = "indices"
            if symbol in ("MGC",):
                sym_type = "metals"
            elif symbol in ("MCL",):
                sym_type = "energy"
            signal = futures_trend_signal(
                symbol,
                closes,
                highs,
                lows,
                sym_type,
                config["futures_trend"],
            )

    elif asset_type in ("STK", "ETF"):
        intl_etfs = set(config["intl_etf_mr"].get("kairi_thresholds", {}).keys())
        commodity_etfs = set(config["commodity_mr"].get("thresholds", {}).keys())
        bond_etfs = set(config["bond_mr_hedge"].get("kairi_thresholds", {}).keys())

        if symbol in intl_etfs and config["intl_etf_mr"]["is_active"]:
            signal = intl_etf_signal(
                symbol,
                closes,
                highs,
                lows,
                volumes,
                open_positions,
                returns_map,
                config["intl_etf_mr"],
            )
        elif symbol in commodity_etfs and config["commodity_mr"]["is_active"]:
            signal = commodity_mr_signal(symbol, closes, highs, lows, config["commodity_mr"])
        elif symbol in bond_etfs and config["bond_mr_hedge"]["is_active"]:
            signal = bond_mr_signal(
                symbol,
                closes,
                highs,
                lows,
                spy_closes=spy_closes,
                tlt_closes=tlt_closes,
                vix_proxy=market_data.get("vix_proxy"),
                defensive_state=defensive_state,
                config=config["bond_mr_hedge"],
            )
        elif config["gap_fade"]["is_active"]:
            signal = gap_fade_signal(
                closes,
                opens,
                highs,
                lows,
                config["gap_fade"],
            )

    return signal


# ---------------------------------------------------------------------------
# Classe principal do bot
# ---------------------------------------------------------------------------

_SHUTDOWN_ORDER_CANCEL_TIMEOUT: int = 10  # segundos

class TradingBot:
    """
    Bot de trading autonomo com loop infinito.

    Coordena todos os modulos: ligacao IB, dados de mercado,
    sinais, gestao de risco, grids, execucao e notificacoes.
    """

    def __init__(self, config: AppConfig) -> None:
        self._config: AppConfig = config
        self._running: bool = False
        self._shutdown_event: asyncio.Event = asyncio.Event()
        self._is_shutting_down: bool = False
        self._shutdown_request_path: Path = config.data_dir / "shutdown.request"
        self._daily_summary_sent: bool = False
        self._last_regimes: dict[str, str] = {}  # simbolo -> regime anterior
        self._last_session_open: dict[str, bool] = {}
        self._warmup_alert_state: dict[str, tuple[str, ...]] = {}
        self._orphan_positions: dict[str, dict[str, Any]] = {}
        self._reconciliation_log_path: Path = config.data_dir / "reconciliation.log"
        self._startup_reconciled: bool = False
        self._manual_pause: bool = False
        self._entry_halt_reason: str | None = None
        self._emergency_halt: bool = False
        self._reconciliation_in_progress: bool = False
        self._last_cycle_started_at: datetime | None = None
        self._last_cycle_completed_at: datetime | None = None
        self._last_error: str | None = None
        self._reference_history_cache: dict[str, list[float]] = {}
        self._defensive_state: dict[str, Any] = {"mode": "NORMAL", "days_in_defensive": 0}
        self._defensive_state_date = datetime.now(timezone.utc).date()
        self._period_pnl: dict[str, float] = {
            "daily": 0.0,
            "weekly": 0.0,
            "monthly": 0.0,
        }
        self._equity_baselines: dict[str, dict[str, Any]] = {}
        self._last_equity_snapshot: float | None = None
        self._instance_lock_fd: int | None = None
        self._instance_lock_path: Path = config.data_dir / _INSTANCE_LOCK_FILENAME
        self._broker_context_lock_fd: int | None = None
        self._broker_context_lock_path: Path = self._build_broker_context_lock_path()

        # --- Watchlist ---
        self._watchlist: list[InstrumentSpec] = get_watchlist_specs()

        # --- Capital ---
        self._capital: float = get_initial_capital()
        self._dynamic_win_rate: float = 0.50  # WinRate

        # --- Componentes ---
        self._connection: IBConnection = IBConnection(
            host=config.ib.host,
            port=config.ib.port,
            client_id=config.ib.client_id,
            paper_trading=config.ib.paper_trading,
            use_gateway=config.ib.use_gateway,
        )
        self._data_feed: DataFeed = DataFeed(self._connection)
        self._risk_manager: RiskManager = RiskManager(
            capital=self._capital,
            risk_per_level=config.risk.risk_per_level,
            kelly_cap=config.risk.kelly_cap,
            stop_atr_mult=config.risk.stop_atr_mult,
            tp_atr_mult=config.risk.tp_atr_mult,
            daily_loss_limit=config.risk.daily_loss_limit,
            weekly_loss_limit=config.risk.weekly_loss_limit,
            monthly_dd_limit=config.risk.monthly_dd_limit,
            max_positions=config.risk.max_positions,
            max_grids=config.risk.max_grids,
            min_rr=config.risk.min_rr,
        )
        self._grid_engine: GridEngine = GridEngine(
            data_dir=config.data_dir,
        )
        self._order_manager: OrderManager | None = None  # inicializado apos ligacao
        self._trade_logger: TradeLogger = TradeLogger(
            data_dir=config.data_dir,
        )
        self._telegram: TelegramNotifier | None = None
        self._telegram_poll_task: asyncio.Task[None] | None = None
        self._reconnect_attempt: int = 0

        # Inicializar Telegram se configurado
        if config.telegram.is_configured:
            self._telegram = TelegramNotifier(
                bot_token=config.telegram.bot_token,  # type: ignore[arg-type]
                chat_id=config.telegram.chat_id,  # type: ignore[arg-type]
            )
            logger.info("Notificacoes Telegram activadas.")
        else:
            logger.warning(
                "Telegram NAO configurado — notificacoes desactivadas. "
                "Defina TELEGRAM_BOT_TOKEN e TELEGRAM_CHAT_ID no .env."
            )

    def _effective_ib_port(self) -> int:
        """Resolve a porta efectiva do broker para fins de exclusao multi-instância."""
        ib_cfg = self._config.ib
        port = int(getattr(ib_cfg, "port", 0) or 0)
        if port:
            return port

        paper_trading = bool(getattr(ib_cfg, "paper_trading", True))
        use_gateway = bool(getattr(ib_cfg, "use_gateway", False))
        if paper_trading and use_gateway:
            return 4002
        if paper_trading and not use_gateway:
            return 7497
        if not paper_trading and use_gateway:
            return 4001
        return 7496

    def _broker_context_payload(self) -> dict[str, Any]:
        """Contexto efectivo do broker usado para lock operacional global."""
        ib_cfg = self._config.ib
        return {
            "host": str(getattr(ib_cfg, "host", "127.0.0.1")).strip().lower() or "127.0.0.1",
            "port": self._effective_ib_port(),
            "client_id": int(getattr(ib_cfg, "client_id", 1)),
            "paper_trading": bool(getattr(ib_cfg, "paper_trading", True)),
            "use_gateway": bool(getattr(ib_cfg, "use_gateway", False)),
        }

    def _build_broker_context_lock_path(self) -> Path:
        """Calcula o lock global por contexto de broker para evitar client_id duplicado."""
        broker_context = self._broker_context_payload()
        lock_key = (
            f"{broker_context['host']}:{broker_context['port']}:"
            f"{broker_context['client_id']}"
        )
        digest = hashlib.sha256(lock_key.encode("utf-8")).hexdigest()[:16]
        lock_name = (
            f"ib-{broker_context['host'].replace('.', '_')}-"
            f"{broker_context['port']}-"
            f"client-{broker_context['client_id']}-"
            f"{digest}.lock"
        )
        return _get_broker_lock_root() / lock_name

    def _acquire_lock_file(
        self,
        lock_path: Path,
        payload: dict[str, Any],
        *,
        error_message: str,
    ) -> int:
        """Adquire um lock por ficheiro de forma fail-closed."""
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_RDWR)
        except FileExistsError as exc:
            raise RuntimeError(error_message) from exc

        try:
            os.write(
                fd,
                json.dumps(payload, indent=2, ensure_ascii=False).encode("utf-8"),
            )
        except Exception:
            os.close(fd)
            try:
                lock_path.unlink()
            except OSError:
                pass
            raise
        return fd

        self._connection.set_alert_callback(self._send_operational_alert)
        self._connection.set_disconnect_callback(self._on_ib_disconnected)
        self._connection.set_post_reconnect_callback(self._post_reconnect_sequence)
        self._connection.set_failed_reconnect_callback(self._on_reconnect_attempt_failed)
        self._connection.set_error_callback(self._handle_ib_operational_event)

    # ------------------------------------------------------------------
    # Validacao de arranque
    # ------------------------------------------------------------------

    def validate_startup(self) -> bool:
        """
        Validacoes de seguranca antes de arrancar o bot.

        - Verifica o Risk of Ruin com os parametros actuais
        - Recusa arrancar se RoR > 1%
        """
        logger.info("A executar validacoes de arranque...")
        self.refresh_dynamic_win_rate()  # WinRate

        # Calcular Risk of Ruin com parametros por defeito conservadores
        # Win rate dinâmico, Payoff ratio: 2.5 (min_rr)  # WinRate
        ror = self._risk_manager.calculate_risk_of_ruin(
            win_rate=self._dynamic_win_rate,  # WinRate
            payoff_ratio=self._config.risk.min_rr,
            risk_per_trade=self._config.risk.risk_per_level,
        )

        logger.info(
            "Risk of Ruin calculado: %.6f%% (limiar maximo: %.2f%%)",
            ror * 100, _RISK_OF_RUIN_THRESHOLD * 100,
        )

        if ror > _RISK_OF_RUIN_THRESHOLD:
            logger.critical(
                "ARRANQUE RECUSADO — Risk of Ruin (%.4f%%) excede o limiar "
                "maximo de %.2f%%. Ajuste os parametros de risco antes de "
                "iniciar o bot.",
                ror * 100, _RISK_OF_RUIN_THRESHOLD * 100,
            )
            return False

        logger.info(
            "Validacao de Risk of Ruin aprovada — RoR: %.6f%% (< %.2f%%)",
            ror * 100, _RISK_OF_RUIN_THRESHOLD * 100,
        )
        return True

    def refresh_dynamic_win_rate(self) -> None:  # WinRate
        """Actualiza win rate real no início de cada ciclo. # WinRate"""  # WinRate
        new_rate = self._risk_manager.calculate_dynamic_win_rate(  # WinRate
            self._config.data_dir / "trades_log.json",  # WinRate
        )  # WinRate
        if abs(new_rate - self._dynamic_win_rate) > 0.02:  # WinRate
            logger.info(  # WinRate
                "Win rate actualizado: %.1f%% → %.1f%% # WinRate",  # WinRate
                self._dynamic_win_rate * 100, new_rate * 100,  # WinRate
            )  # WinRate
        self._dynamic_win_rate = new_rate  # WinRate

    @staticmethod
    def _parse_trade_timestamp(value: Any) -> datetime | None:
        """Converte timestamps de trade para UTC de forma tolerante."""
        if value is None:
            return None
        try:
            timestamp = (
                value
                if isinstance(value, datetime)
                else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            )
        except (TypeError, ValueError):
            return None

        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        return timestamp.astimezone(timezone.utc)

    def _calculate_period_pnl(
        self,
        now: datetime | None = None,
    ) -> dict[str, float]:
        """
        Calcula P&L diário, semanal e mensal a partir do trades_log.

        Usa apenas trades com ``pnl`` numérico e timestamp válido.
        """
        now_utc = (
            now.astimezone(timezone.utc)
            if now is not None else datetime.now(timezone.utc)
        )
        day_start = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
        week_start = day_start - timedelta(days=day_start.weekday())
        month_start = day_start.replace(day=1)

        period_pnl = {"daily": 0.0, "weekly": 0.0, "monthly": 0.0}

        for trade in self._trade_logger.get_trades():
            pnl_raw = trade.get("pnl")
            if pnl_raw is None:
                continue
            try:
                pnl = float(pnl_raw)
            except (TypeError, ValueError):
                continue

            timestamp = self._parse_trade_timestamp(trade.get("timestamp"))
            if timestamp is None:
                continue

            if timestamp >= month_start:
                period_pnl["monthly"] += pnl
            if timestamp >= week_start:
                period_pnl["weekly"] += pnl
            if timestamp >= day_start:
                period_pnl["daily"] += pnl

        return {key: round(value, 4) for key, value in period_pnl.items()}

    def _refresh_period_pnl(
        self,
        now: datetime | None = None,
    ) -> dict[str, float]:
        """Actualiza o snapshot local de P&L por período."""
        self._period_pnl = self._calculate_period_pnl(now=now)
        return dict(self._period_pnl)

    @staticmethod
    def _get_equity_period_ids(now: datetime | None = None) -> dict[str, str]:
        """Calcula identificadores estÃ¡veis para os baselines diÃ¡rio/semanal/mensal."""
        now_utc = (
            now.astimezone(timezone.utc)
            if now is not None else datetime.now(timezone.utc)
        )
        day_start = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
        week_start = day_start - timedelta(days=day_start.weekday())
        return {
            "daily": day_start.date().isoformat(),
            "weekly": week_start.date().isoformat(),
            "monthly": day_start.strftime("%Y-%m"),
        }

    @staticmethod
    def _is_valid_equity_baseline(
        entry: Any,
        *,
        expected_period: str | None = None,
    ) -> bool:
        """Valida um baseline persistido sem assumir que o ficheiro estÃ¡ intacto."""
        if not isinstance(entry, dict):
            return False

        period = entry.get("period")
        if not isinstance(period, str) or not period:
            return False
        if expected_period is not None and period != expected_period:
            return False

        try:
            equity = float(entry.get("equity"))
        except (TypeError, ValueError):
            return False

        return math.isfinite(equity) and equity > 0

    def _load_equity_baselines_from_snapshot(
        self,
        snapshot: dict[str, Any],
    ) -> dict[str, dict[str, Any]]:
        """Extrai baselines vÃ¡lidos do snapshot de mÃ©tricas persistido."""
        baselines: dict[str, dict[str, Any]] = {}
        raw = snapshot.get("equity_baselines")
        if not isinstance(raw, dict):
            return baselines

        for key in _EQUITY_BASELINE_KEYS:
            entry = raw.get(key)
            if self._is_valid_equity_baseline(entry):
                baselines[key] = {
                    "period": str(entry["period"]),
                    "equity": round(float(entry["equity"]), 4),
                }
            elif isinstance(entry, dict):
                baselines[key] = dict(entry)
            elif entry is not None:
                baselines[key] = {"period": None, "equity": entry}
        return baselines

    def _persist_runtime_metrics_snapshot(self) -> None:
        """Persiste o estado runtime crÃ­tico sem recalcular toda a telemetria."""
        try:
            metrics_snapshot = self._load_metrics_snapshot()
            metrics_snapshot.pop("last_updated", None)
            self._trade_logger.save_metrics(
                self._build_metrics_payload(metrics_snapshot)
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Falha ao persistir snapshot runtime em metrics.json: %s", exc)

    def _sync_equity_baselines(
        self,
        current_equity: float,
        *,
        now: datetime | None = None,
    ) -> bool:
        """
        Inicializa/roda os baselines por perÃ­odo.

        Se existir um baseline para o perÃ­odo actual mas estiver corrompido,
        o bot entra em fail-safe em vez de continuar com divisÃµes inseguras.
        """
        if not math.isfinite(current_equity) or current_equity <= 0:
            return False

        period_ids = self._get_equity_period_ids(now)
        changed = False

        for key, period_id in period_ids.items():
            entry = self._equity_baselines.get(key)

            if entry is None:
                self._equity_baselines[key] = {
                    "period": period_id,
                    "equity": round(current_equity, 4),
                }
                changed = True
                continue

            if not self._is_valid_equity_baseline(entry):
                logger.critical(
                    "Baseline de equity %s invÃƒÂ¡lido/corrompido: %s",
                    key,
                    entry,
                )
                return False

            if entry.get("period") != period_id:
                self._equity_baselines[key] = {
                    "period": period_id,
                    "equity": round(current_equity, 4),
                }
                changed = True
                continue

            if False:
                logger.critical(
                    "Baseline de equity %s invÃ¡lido para o perÃ­odo %s: %s",
                    key,
                    period_id,
                    entry,
                )
                return False

        if changed:
            logger.info(
                "Baselines de equity actualizados: %s",
                {
                    key: self._equity_baselines[key]["period"]
                    for key in _EQUITY_BASELINE_KEYS
                    if key in self._equity_baselines
                },
            )
            self._persist_runtime_metrics_snapshot()

        return True

    def _equity_delta_since_baseline(
        self,
        period_key: str,
        current_equity: float,
    ) -> float | None:
        """Calcula o delta de equity face ao baseline do perÃ­odo activo."""
        entry = self._equity_baselines.get(period_key)
        if not self._is_valid_equity_baseline(entry):
            return None
        baseline_equity = float(entry["equity"])
        return current_equity - baseline_equity

    @staticmethod
    def _equity_loss_ratio(
        baseline_equity: float,
        current_equity: float,
    ) -> float | None:
        """Calcula perda relativa desde o baseline sem permitir divisÃµes invÃ¡lidas."""
        if (
            not math.isfinite(baseline_equity)
            or not math.isfinite(current_equity)
            or baseline_equity <= 0
            or current_equity <= 0
        ):
            return None
        return abs(min((current_equity - baseline_equity) / baseline_equity, 0.0))

    async def _fetch_current_equity_snapshot(self) -> float | None:
        """ObtÃ©m a equity actual do broker via NetLiquidation (ou equivalente)."""
        try:
            account_values = await self._connection.request_executor.run(
                "account_values",
                "account_values:risk",
                self._connection.ib.accountValues,
                request_cost=1,
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("Falha ao obter snapshot de equity do broker: %s", exc)
            return None

        equity = self._extract_account_equity(account_values)
        if equity is None or not math.isfinite(equity) or equity <= 0:
            logger.error("Snapshot de equity invÃ¡lido/indisponÃ­vel: %s", equity)
            return None

        self._last_equity_snapshot = float(equity)
        return self._last_equity_snapshot

    async def _on_ib_disconnected(self) -> None:
        """Notifica a perda de ligacao ao IB."""
        logger.warning("IB desconectado. Aguardar sequencia de reconexao.")
        self._reconnect_attempt = 1
        self._schedule_telegram(
            self._telegram.notify_connection_status(False) if self._telegram else None
        )
        self._schedule_telegram(
            self._telegram.ib_reconnect(self._reconnect_attempt, self._config.ib.paper_trading)
            if self._telegram else None
        )

    async def _on_reconnect_attempt_failed(self) -> None:
        """Persiste estado sempre que uma tentativa de reconnect falha."""
        self._reconnect_attempt += 1
        try:
            self._grid_engine.save_state()
        except Exception as exc:  # noqa: BLE001
            logger.error("Falha ao persistir estado apos reconnect falhado: %s", exc)
        self._schedule_telegram(
            self._telegram.ib_reconnect(self._reconnect_attempt, self._config.ib.paper_trading)
            if self._telegram else None
        )

    @staticmethod
    def _infer_account_mode(account_id: str) -> str:
        """Infere de forma conservadora se a conta parece paper ou live."""
        return "PAPER" if account_id.upper().startswith("DU") else "LIVE"

    def _enforce_account_context(
        self,
        primary_account: str,
        *,
        phase: str,
    ) -> bool:
        """Faz fail-closed se o contexto da conta não for compatível com o modo configurado."""
        masked_account = (
            mask_account_id(primary_account)
            if primary_account != "UNKNOWN" else "UNKNOWN"
        )
        account_mode = (
            self._infer_account_mode(primary_account)
            if primary_account != "UNKNOWN" else "UNKNOWN"
        )
        logger.info("Conta IB detectada: %s (%s).", masked_account, account_mode)

        violation: str | None = None
        if primary_account == "UNKNOWN":
            violation = (
                "Contexto de conta IB ambíguo ou indisponível. "
                "O bot não pode continuar sem confirmar PAPER/LIVE."
            )
        elif self._config.ib.paper_trading and account_mode != "PAPER":
            violation = (
                "Conta live detectada com PAPER_TRADING=true. "
                "Arranque/reconexão bloqueado por segurança."
            )
        elif not self._config.ib.paper_trading and account_mode != "LIVE":
            violation = (
                "Conta paper detectada com PAPER_TRADING=false. "
                "Arranque/reconexão bloqueado por segurança."
            )

        if violation is None:
            return True

        logger.critical("%s", violation)
        self._entry_halt_reason = "account_context_violation"
        self._emergency_halt = True
        self._schedule_telegram(
            self._telegram.critical_error(
                error=violation,
                location=f"account_context:{phase}",
                paper=self._config.ib.paper_trading,
            ) if self._telegram else None
        )

        if phase == "startup":
            sys.exit(1)

        self._running = False
        self._shutdown_event.set()
        return False

    @staticmethod
    def _coerce_float(value: Any) -> float | None:
        try:
            if value in (None, ""):
                return None
            parsed = float(value)
        except (TypeError, ValueError):
            return None
        if parsed <= 0:
            return None
        return parsed

    def _load_metrics_snapshot(self) -> dict[str, Any]:
        """Lê metrics.json e achata o bloco metrics quando existir."""
        metrics_path = self._config.data_dir / "metrics.json"
        try:
            payload = json.loads(metrics_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

        if not isinstance(payload, dict):
            return {}

        merged: dict[str, Any] = {}
        metrics_block = payload.get("metrics")
        if isinstance(metrics_block, dict):
            merged.update(metrics_block)
        for key, value in payload.items():
            if key != "metrics":
                merged[key] = value
        return merged

    def _extract_account_equity(self, account_values: list[Any]) -> float | None:
        """Extrai capital/equity do payload do broker com preferência por NetLiquidation."""
        preferred_tags = (
            "NetLiquidation",
            "NetLiquidationByCurrency",
            "EquityWithLoanValue",
        )
        allowed_currencies = {"", "BASE", "USD", "EUR", None}

        for tag in preferred_tags:
            for item in account_values:
                if isinstance(item, dict):
                    item_tag = item.get("tag")
                    item_value = item.get("value")
                    item_currency = item.get("currency")
                else:
                    item_tag = getattr(item, "tag", None)
                    item_value = getattr(item, "value", None)
                    item_currency = getattr(item, "currency", None)

                if item_tag != tag:
                    continue
                if item_currency not in allowed_currencies:
                    continue

                parsed = self._coerce_float(item_value)
                if parsed is not None:
                    return parsed

        return None

    def _restore_runtime_capital(self, account_values: list[Any]) -> str:
        """Restaura o capital do runtime a partir do broker, métricas ou trade log."""
        source = "config"
        restored_capital = self._capital
        restored_peak = getattr(self._risk_manager, "peak_equity", self._capital)

        broker_capital = self._extract_account_equity(account_values)
        metrics_snapshot = self._load_metrics_snapshot()
        self._equity_baselines = self._load_equity_baselines_from_snapshot(
            metrics_snapshot
        )
        metrics_capital = self._coerce_float(metrics_snapshot.get("capital"))
        metrics_peak = self._coerce_float(metrics_snapshot.get("peak_equity"))

        trade_log_capital: float | None = None
        try:
            trade_metrics = self._trade_logger.calculate_metrics()
            total_pnl = float(trade_metrics.get("total_pnl", 0.0) or 0.0)
            num_trades = int(trade_metrics.get("num_trades", 0) or 0)
            if num_trades > 0 or abs(total_pnl) > 0:
                trade_log_capital = max(self._capital + total_pnl, 0.0)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Falha ao calcular capital a partir do trade log: %s", exc)

        if broker_capital is not None:
            restored_capital = broker_capital
            source = "broker"
        elif metrics_capital is not None:
            restored_capital = metrics_capital
            source = "metrics"
        elif trade_log_capital is not None:
            restored_capital = trade_log_capital
            source = "trade_log"

        self._capital = restored_capital
        self._last_equity_snapshot = restored_capital
        self._risk_manager.update_capital(self._capital)

        if metrics_peak is not None:
            restored_peak = max(restored_peak, metrics_peak, self._capital)
        else:
            restored_peak = max(restored_peak, self._capital)
        self._risk_manager.peak_equity = restored_peak

        logger.info(
            "Capital de runtime restaurado: %.2f (fonte=%s, peak_equity=%.2f).",
            self._capital,
            source,
            self._risk_manager.peak_equity,
        )
        return source

    def _build_metrics_payload(self, metrics: dict[str, Any]) -> dict[str, Any]:
        """Enriquece o payload de métricas com capital e peak equity de runtime."""
        payload = dict(metrics)
        payload["capital"] = round(self._capital, 4)
        payload["initial_capital"] = round(self._risk_manager.initial_capital, 4)
        payload["peak_equity"] = round(self._risk_manager.peak_equity, 4)
        payload["equity_baselines"] = {
            key: {
                "period": str(entry.get("period")),
                "equity": round(float(entry.get("equity")), 4),
            }
            for key, entry in self._equity_baselines.items()
            if self._is_valid_equity_baseline(entry)
        }
        return payload

    def _rehydrate_order_tracking(self) -> int:
        """Restaura tracking de ordens a partir das grids persistidas."""
        if (
            self._order_manager is None
            or not hasattr(self._order_manager, "rehydrate_grid_orders")
            or not hasattr(self, "_grid_engine")
        ):
            return 0

        restored = 0
        for grid in getattr(self._grid_engine, "grids", []):
            if grid.status == "closed":
                continue
            try:
                spec = self._get_instrument_spec(grid.symbol)
                contract = build_contract(spec)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Tracking de ordens não reidratado para grid %s (%s): %s",
                    grid.id,
                    grid.symbol,
                    exc,
                )
                continue

            restored += self._order_manager.rehydrate_grid_orders(grid, contract)

        if restored > 0:
            logger.info("Tracking de ordens reidratado no arranque: %d ordem(ns).", restored)
        return restored

    async def _check_data_files_integrity(self) -> None:
        """Valida os JSONs criticos e repara ficheiros corrompidos."""
        for filename, initial_value in _DATA_FILE_DEFAULTS.items():
            if not isinstance(initial_value, dict):
                continue

            file_path = self._config.data_dir / filename
            try:
                json.loads(file_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                corrupted_path = file_path.with_suffix(file_path.suffix + ".corrupted")
                try:
                    if file_path.exists():
                        file_path.replace(corrupted_path)
                except OSError as exc:
                    logger.error("Nao foi possivel preservar %s corrompido: %s", file_path, exc)

                file_path.write_text(
                    json.dumps(initial_value, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
                message = (
                    f"Ficheiro {filename} corrompido. Renomeado para "
                    f"{corrupted_path.name} e recriado."
                )
                logger.error(message)
                self._schedule_telegram(
                    self._telegram.notify_operational_alert(message)
                    if self._telegram else None
                )

    async def _fetch_positions_with_retry(self) -> BrokerPositionsObservation:
        """Obtém posições do IB com retry explícito e semântica fail-closed."""
        if self._order_manager is None:
            raise RuntimeError("OrderManager nao inicializado.")

        for attempt in range(1, _RECONCILIATION_FETCH_ATTEMPTS + 1):
            positions = await self._order_manager.get_positions()
            if positions:
                return BrokerPositionsObservation(
                    state="confirmed",
                    positions=positions,
                )
            logger.warning(
                "Leitura de posicoes do IB sem dados na tentativa %d/%d. Novo retry em %d s.",
                attempt,
                _RECONCILIATION_FETCH_ATTEMPTS,
                _RECONCILIATION_FETCH_DELAY_SECONDS,
            )
            if attempt == _RECONCILIATION_FETCH_ATTEMPTS:
                break
            await asyncio.sleep(_RECONCILIATION_FETCH_DELAY_SECONDS)
        logger.error(
            "Reconciliação inconclusiva: posições do IB continuam vazias após %d tentativas. "
            "Sem acções destrutivas neste ciclo.",
            _RECONCILIATION_FETCH_ATTEMPTS,
        )
        return BrokerPositionsObservation(state="unknown", positions=[])

    async def _write_reconciliation_log(self, lines: list[str]) -> None:
        """Escreve o log da reconciliação de arranque."""
        timestamp = datetime.now(timezone.utc).isoformat()
        payload = "\n".join([f"[{timestamp}] {line}" for line in lines]) + "\n"
        self._reconciliation_log_path.parent.mkdir(parents=True, exist_ok=True)
        with self._reconciliation_log_path.open("a", encoding="utf-8") as handle:
            handle.write(payload)

    async def _verify_market_data_permissions(self) -> None:
        """Executa um snapshot rapido para validar permissões de mercado."""
        if not self._watchlist:
            return

        spec = self._watchlist[0]
        contract = build_contract(spec)
        await self._data_feed.qualify_contract(contract)
        started_at = time.monotonic()
        price = await self._data_feed.get_current_price(contract)
        if not await self._apply_ib_request_events(
            self._connection.operational_events_since(started_at),
            spec=spec,
            phase="preflight_market_data",
        ):
            return

        if price is None:
            logger.warning(
                "Snapshot de mercado sem preco para %s durante o preflight.",
                spec.display,
            )

    async def preflight_check(self) -> None:
        """
        Executa o preflight de arranque antes do loop principal.

        Codigos IB tratados graciosamente:
        1100 -> IB desconectado
        1102 -> IB reconectado automaticamente
        2104 -> Dados de mercado OK
        2106 -> Dados historicos OK
        354  -> Sem subscricao de dados de mercado
        10197 -> Sem dados fora de horas de mercado
        """
        await self._check_data_files_integrity()

        connected = await self._connection.connect(max_attempts=3, timeout=30)
        if not connected:
            message = "Nao foi possivel ligar ao IB apos 3 tentativas"
            logger.critical(message)
            self._schedule_telegram(
                self._telegram.critical_error(
                    error=message,
                    location="preflight_check",
                    paper=self._config.ib.paper_trading,
                ) if self._telegram else None
            )
            sys.exit(1)

        if self._order_manager is None:
            self._order_manager = OrderManager(self._connection)
        self._rehydrate_order_tracking()

        self._schedule_telegram(
            self._telegram.notify_connection_status(True) if self._telegram else None
        )

        accounts = await self._connection.request_executor.run(
            "managed_accounts",
            "managed_accounts",
            self._connection.ib.managedAccounts,
            request_cost=1,
        )
        account_values = await self._connection.request_executor.run(
            "account_values",
            "account_values",
            self._connection.ib.accountValues,
            request_cost=1,
        )

        primary_account = accounts[0] if accounts else "UNKNOWN"
        self._enforce_account_context(primary_account, phase="startup")
        self._restore_runtime_capital(account_values)

        await self._verify_market_data_permissions()
        self._schedule_telegram(
            self._telegram.bot_started(
                version=_VERSION,
                paper=self._config.ib.paper_trading,
                symbols=[spec.display for spec in self._watchlist],
            ) if self._telegram else None
        )

        # Persistir estado do preflight para observabilidade externa
        state_file = self._config.data_dir / "preflight_state.json"
        telegram_status = "disabled"
        if self._telegram is not None:
            telegram_status = "OK" if getattr(self._telegram, "enabled", True) else "error"
        state = {
            "startup_reconciled": self._startup_reconciled,
            "telegram_status": telegram_status,
            "last_preflight": datetime.now(timezone.utc).isoformat(),
            "watchlist_size": len(self._watchlist),
            "capital": self._capital,
        }
        try:
            state_file.parent.mkdir(parents=True, exist_ok=True)
            state_file.write_text(
                json.dumps(state, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except OSError as exc:
            logger.warning("Falha ao persistir preflight_state.json: %s", exc)

    async def _post_reconnect_sequence(self) -> None:
        """Revalida o bot apos reconnect do IB e retoma a operacao."""
        logger.info("IB reconectado. A executar sequencia pos-reconnect.")
        await self._connection.request_executor.run(
            "req_current_time",
            "req_current_time",
            self._connection.ib.reqCurrentTime,
            request_cost=1,
        )
        accounts = await self._connection.request_executor.run(
            "managed_accounts_post_reconnect",
            "managed_accounts_post_reconnect",
            self._connection.ib.managedAccounts,
            request_cost=1,
        )
        primary_account = accounts[0] if accounts else "UNKNOWN"
        if not self._enforce_account_context(primary_account, phase="reconnect"):
            return
        await self._verify_market_data_permissions()
        if self._order_manager is None:
            self._order_manager = OrderManager(self._connection)
        self._rehydrate_order_tracking()
        await self._reconcile_startup()
        if self._entry_halt_reason == "ib_connection_lost":
            self._entry_halt_reason = None
        self._schedule_telegram(
            self._telegram.notify_reconnect_resumed(datetime.now(timezone.utc).isoformat())
            if self._telegram else None
        )

    def _load_persisted_grids_or_fail_closed(self) -> None:
        """Carrega o estado persistido ou aborta o arranque se nÃ£o houver recovery seguro."""
        try:
            self._grid_engine.load_state()
        except Exception as exc:
            message = (
                "Estado persistido de grids indisponÃ­vel/corrompido. "
                "Arranque abortado em fail-closed."
            )
            logger.critical("%s Detalhe: %s", message, exc)
            raise RuntimeError(message) from exc

        logger.info(
            "Estado de grids carregado â€” %d grid(s) existente(s).",
            len(self._grid_engine.grids),
        )

    def _acquire_instance_lock(self) -> None:
        """Impede mÃºltiplas instÃ¢ncias activas sobre o mesmo data_dir e broker context."""
        if (
            getattr(self, "_instance_lock_fd", None) is not None
            and getattr(self, "_broker_context_lock_fd", None) is not None
        ):
            return

        lock_path = getattr(self, "_instance_lock_path", None)
        if not isinstance(lock_path, Path):
            lock_path = Path(self._config.data_dir) / _INSTANCE_LOCK_FILENAME
            self._instance_lock_path = lock_path

        broker_lock_path = getattr(self, "_broker_context_lock_path", None)
        if not isinstance(broker_lock_path, Path):
            broker_lock_path = self._build_broker_context_lock_path()
            self._broker_context_lock_path = broker_lock_path

        created_at = datetime.now(timezone.utc).isoformat()
        instance_payload = {
            "pid": os.getpid(),
            "client_id": self._config.ib.client_id,
            "data_dir": str(lock_path.parent),
            "created_at": created_at,
        }
        broker_context = self._broker_context_payload()
        broker_payload = {
            "pid": os.getpid(),
            "created_at": created_at,
            "cwd": str(Path.cwd()),
            "data_dir": str(lock_path.parent),
            **broker_context,
        }

        instance_fd = self._acquire_lock_file(
            lock_path,
            instance_payload,
            error_message=(
                f"Outra instÃ¢ncia parece activa para {lock_path.parent} "
                f"(lock: {lock_path.name})."
            ),
        )
        try:
            broker_fd = self._acquire_lock_file(
                broker_lock_path,
                broker_payload,
                error_message=(
                    "Outra instÃ¢ncia parece activa para o mesmo contexto IB "
                    f"({broker_context['host']}:{broker_context['port']} "
                    f"client_id={broker_context['client_id']})."
                ),
            )
        except Exception:
            try:
                os.close(instance_fd)
            except OSError:
                pass
            try:
                lock_path.unlink()
            except OSError:
                pass
            raise

        self._instance_lock_fd = instance_fd
        self._broker_context_lock_fd = broker_fd
        atexit.register(self._release_instance_lock)
        logger.info("Lock de instÃ¢ncia adquirido: %s", lock_path)
        logger.info("Lock de contexto IB adquirido: %s", broker_lock_path)

    def _release_instance_lock(self) -> None:
        """Liberta o lock de instÃ¢ncia de forma idempotente."""
        locks = [
            ("_instance_lock_fd", "_instance_lock_path"),
            ("_broker_context_lock_fd", "_broker_context_lock_path"),
        ]

        for fd_attr, path_attr in locks:
            fd = getattr(self, fd_attr, None)
            lock_path = getattr(self, path_attr, None)
            if fd is not None:
                try:
                    os.close(fd)
                except OSError:
                    pass
                setattr(self, fd_attr, None)

            if isinstance(lock_path, Path):
                try:
                    lock_path.unlink()
                except FileNotFoundError:
                    pass
                except OSError as exc:
                    logger.warning("Falha ao remover lock de instÃ¢ncia %s: %s", lock_path, exc)

        try:
            atexit.unregister(self._release_instance_lock)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Tratamento de sinais do sistema operativo
    # ------------------------------------------------------------------

    def _setup_signal_handlers(self, loop: asyncio.AbstractEventLoop) -> None:
        """Regista handlers para SIGINT e SIGTERM para encerramento gracioso."""
        signals_to_register = [signal.SIGINT]
        sigterm = getattr(signal, "SIGTERM", None)
        if sigterm is not None:
            signals_to_register.append(sigterm)

        if sys.platform != "win32":
            try:
                for sig in signals_to_register:
                    loop.add_signal_handler(sig, self._handle_shutdown_signal, sig)
                logger.info(
                    "Caminho de sinais activo: unix_signal_handlers (%s).",
                    ", ".join(signal.Signals(sig).name for sig in signals_to_register),
                )
                return
            except NotImplementedError:
                logger.warning(
                    "Caminho de sinais unix_signal_handlers indisponivel neste loop; "
                    "a usar windows_signal_fallback."
                )

        def _fallback_handler(signum: int, _frame: Any) -> None:
            self._handle_shutdown_signal(signum)

        signal.signal(signal.SIGINT, _fallback_handler)
        registered_signals = [signal.Signals(signal.SIGINT).name]

        if sigterm is None:
            logger.info(
                "Caminho de sinais activo: windows_signal_fallback (%s); "
                "SIGTERM indisponivel nesta plataforma.",
                ", ".join(registered_signals),
            )
            return

        try:
            signal.signal(sigterm, _fallback_handler)
            registered_signals.append(signal.Signals(sigterm).name)
        except (OSError, RuntimeError, ValueError) as exc:
            logger.warning(
                "Caminho de sinais activo: windows_signal_fallback (%s); "
                "SIGTERM nao utilizavel no fallback: %s",
                ", ".join(registered_signals),
                exc,
            )
            return

        logger.info(
            "Caminho de sinais activo: windows_signal_fallback (%s).",
            ", ".join(registered_signals),
        )

    def _handle_shutdown_signal(self, sig: signal.Signals) -> None:
        """Callback invocado ao receber SIGINT ou SIGTERM."""
        sig_name = signal.Signals(sig).name
        logger.warning(
            "Sinal %s recebido — a iniciar encerramento gracioso...", sig_name,
        )
        self._running = False
        self._shutdown_event.set()

    # ------------------------------------------------------------------
    # Notificacao Telegram (segura — nunca levanta excepcao)
    # ------------------------------------------------------------------

    async def _notify(self, coro: Any) -> None:
        """Executa uma coroutine de notificacao Telegram sem propagar erros."""
        if self._telegram is None:
            return
        try:
            await coro
        except Exception as exc:  # noqa: BLE001
            logger.error("Falha ao enviar notificacao Telegram: %s", exc)

    def _schedule_telegram(self, coro: Coroutine[Any, Any, Any] | None) -> None:
        """Agenda uma notificacao Telegram sem bloquear o loop principal."""
        if self._telegram is None or coro is None:
            return

        async def _runner() -> None:
            try:
                await coro
            except asyncio.CancelledError:
                return
            except Exception as exc:  # noqa: BLE001
                logger.debug("Falha em tarefa Telegram: %s", exc)

        asyncio.create_task(_runner())

    async def _send_operational_alert(self, message: str) -> None:
        """Encaminha alertas operacionais do executor IB para Telegram."""
        logger.warning("ALERTA OPERACIONAL: %s", message)
        self._schedule_telegram(
            self._telegram.notify_operational_alert(message)
            if self._telegram else None
        )

    async def _handle_ib_operational_event(
        self,
        decision: IBErrorPolicyDecision,
    ) -> None:
        """Aplica o efeito operacional determinístico de um erro IB relevante."""
        self._last_error = f"IB {decision.error_code}: {decision.message}"

        if decision.action == "entry_halt":
            if self._entry_halt_reason in (None, decision.halt_reason):
                self._entry_halt_reason = decision.halt_reason or "ib_connection_lost"
            logger.error(
                "IB entrou em estado degradado (%d). Entradas bloqueadas: %s",
                decision.error_code,
                self._entry_halt_reason,
            )
            self._schedule_telegram(
                self._telegram.notify_operational_alert(
                    f"IB degradado ({decision.error_code}). Entradas bloqueadas: "
                    f"{self._entry_halt_reason} | detalhe={decision.message}"
                ) if self._telegram else None
            )
            return

        if decision.action == "clear_connection_halt":
            if self._entry_halt_reason == (decision.halt_reason or "ib_connection_lost"):
                self._entry_halt_reason = None
            logger.info(
                "IB reportou reconexão (%d). Estado de ligação normalizado.",
                decision.error_code,
            )
            return

    async def _apply_ib_request_events(
        self,
        events: list[IBErrorPolicyDecision],
        *,
        spec: InstrumentSpec,
        phase: str,
    ) -> bool:
        """Traduz eventos IB de request em decisão operacional no call path actual."""
        should_continue = True
        for decision in events:
            self._last_error = f"IB {decision.error_code}: {decision.message}"

            if decision.action == "entry_halt":
                await self._handle_ib_operational_event(decision)
                should_continue = False
                continue

            if decision.action != "symbol_skip":
                continue

            if decision.error_code == 354:
                message = (
                    f"Sem permissões de dados de mercado para {spec.display} "
                    f"em {phase}. Pedido saltado."
                )
                logger.warning("%s", message)
                self._schedule_telegram(
                    self._telegram.notify_operational_alert(message)
                    if self._telegram else None
                )
            elif decision.error_code == 10197:
                logger.info(
                    "Sem dados fora de horas para %s em %s: %s",
                    spec.display,
                    phase,
                    decision.message,
                )
            elif decision.error_code == 162:
                logger.warning(
                    "Pacing violation do IB para %s em %s. Pedido saltado neste ciclo.",
                    spec.display,
                    phase,
                )
            else:
                logger.warning(
                    "Erro IB accionável para %s em %s: codigo=%d %s",
                    spec.display,
                    phase,
                    decision.error_code,
                    decision.message,
                )
            should_continue = False
        return should_continue

    async def _handle_session_transition(
        self,
        spec: InstrumentSpec,
        session_state: SessionState,
    ) -> None:
        """Notifica mudancas de abertura/fecho de sessao por simbolo."""
        previous = self._last_session_open.get(spec.display)
        current = session_state.is_open
        self._last_session_open[spec.display] = current

        if previous is None or previous == current:
            return

        logger.info(
            "Sessao alterada para %s: %s",
            spec.display,
            session_state.status,
        )
        self._schedule_telegram(
            self._telegram.notify_session_status(
                symbol=spec.display,
                status=session_state.status,
                opens_at=session_state.opens_at.isoformat() if session_state.opens_at else None,
                closes_at=session_state.closes_at.isoformat() if session_state.closes_at else None,
            ) if self._telegram else None
        )

    async def _check_warmup(
        self,
        spec: InstrumentSpec,
        bars_df: Any,
    ) -> bool:
        """Valida o warm-up minimo para os indicadores criticos."""
        missing_rules = get_warmup_missing_rules(bars_df)

        cache_key = spec.display
        if missing_rules:
            current_state = tuple(missing_rules)
            if self._warmup_alert_state.get(cache_key) != current_state:
                logger.warning(
                    "Warm-up insuficiente para %s: %s",
                    spec.display,
                    ", ".join(missing_rules),
                )
                self._schedule_telegram(
                    self._telegram.notify_warmup_waiting(spec.display, missing_rules)
                    if self._telegram else None
                )
                self._warmup_alert_state[cache_key] = current_state
            return False

        self._warmup_alert_state.pop(cache_key, None)
        return validate_warmup(bars_df, spec.display)

    async def _telegram_status_callback(self) -> str:
        """Resposta ao comando /status do Telegram."""
        metrics = self._load_metrics_snapshot()

        summary = self._trade_logger.get_daily_summary()
        capital = float(metrics.get("capital", self._capital) or self._capital)
        daily_pnl = float(summary.get("total_pnl", 0.0) or 0.0)
        open_grids = len(self._grid_engine.get_active_grids())
        connected = self._connection.is_connected

        return (
            f"📊 <b>Status</b> {'📄 PAPER' if self._config.ib.paper_trading else '💰 LIVE'}\n"
            f"──────────────────\n"
            f"⏰ {datetime.now(timezone.utc).strftime('%d/%m/%Y %H:%M UTC')}\n"
            f"📡 IB: <code>{'LIGADO' if connected else 'DESLIGADO'}</code>\n"
            f"💶 Capital: <code>€{capital:,.2f}</code>\n"
            f"📈 P&L Diário: <code>€{daily_pnl:+.2f}</code>\n"
            f"🔲 Grids abertas: <code>{open_grids}</code>\n"
            f"🏆 Win Rate dinâmico: <code>{self._dynamic_win_rate * 100:.1f}%</code>\n"
            f"📋 Watchlist: <code>{', '.join(spec.display for spec in self._watchlist[:5])}</code>"
        )

    def _get_instrument_spec(self, symbol: str) -> InstrumentSpec:
        """Resolve o InstrumentSpec a partir do simbolo da grid/watchlist."""
        for spec in self._watchlist:
            if spec.symbol.upper() == symbol.upper():
                return spec
        return parse_watchlist_entry(symbol)

    async def _get_reference_closes(self, symbol: str) -> list[float]:
        """Obtém e cacheia fechos diários de um símbolo de referência."""
        symbol_key = symbol.upper()
        if symbol_key in self._reference_history_cache:
            return self._reference_history_cache[symbol_key]

        try:
            spec = self._get_instrument_spec(symbol_key)
        except ValueError:
            spec = parse_watchlist_entry(symbol_key)

        contract = build_contract(spec)
        qualified = await self._data_feed.qualify_contract(contract)
        if not qualified:
            logger.warning("Sem qualificação de contrato para referência %s.", symbol_key)
            self._reference_history_cache[symbol_key] = []
            return []

        bars_df = await self._data_feed.get_historical_bars(
            contract,
            duration="1 Y",
            bar_size="1 day",
        )
        closes = bars_df["close"].astype(float).tolist() if not bars_df.empty else []
        self._reference_history_cache[symbol_key] = closes
        return closes

    async def _get_vix_proxy(self) -> float | None:
        """Obtém o VIX actual ou devolve None para modo conservador."""
        for candidate in ("VIX", "^VIX"):
            closes = await self._get_reference_closes(candidate)
            if closes:
                return float(closes[-1])
        logger.warning(
            "vix_proxy indisponível — bond_mr_hedge e options_premium operam em modo conservador."
        )
        return None

    @staticmethod
    def _calculate_daily_returns(closes: list[float]) -> list[float]:
        """Calcula retornos diários simples a partir de uma série de fechos."""
        returns: list[float] = []
        for idx in range(1, len(closes)):
            previous = float(closes[idx - 1])
            current = float(closes[idx])
            if previous == 0.0:
                continue
            returns.append((current - previous) / previous)
        return returns

    async def _build_intl_etf_context(
        self,
        current_symbol: str,
        current_bars_df: Any,
    ) -> tuple[list[str], dict[str, list[float]]]:
        """Constrói contexto real de posições abertas e retornos para correlação."""
        open_positions = sorted(
            {
                grid.symbol
                for grid in self._grid_engine.get_active_grids()
                if any(level.status == "bought" for level in grid.levels)
            }
            | set(self._orphan_positions.keys())
        )
        returns_map: dict[str, list[float]] = {}

        current_closes = current_bars_df["close"].astype(float).tolist()
        current_returns = self._calculate_daily_returns(current_closes)
        if current_returns:
            returns_map[current_symbol] = current_returns

        for symbol in open_positions:
            if symbol == current_symbol:
                continue
            closes = await self._get_reference_closes(symbol)
            symbol_returns = self._calculate_daily_returns(closes)
            if symbol_returns:
                returns_map[symbol] = symbol_returns

        return open_positions, returns_map

    def _advance_defensive_day_counter(self) -> None:
        """Avança o contador de dias em modo defensivo apenas quando muda o dia UTC."""
        today = datetime.now(timezone.utc).date()
        if today <= self._defensive_state_date:
            return

        delta_days = (today - self._defensive_state_date).days
        if self._defensive_state.get("mode") == "DEFENSIVE":
            self._defensive_state["days_in_defensive"] = (
                int(self._defensive_state.get("days_in_defensive", 0)) + delta_days
            )
        else:
            self._defensive_state["days_in_defensive"] = 0

        self._defensive_state_date = today

    async def _evaluate_sector_rotation(self) -> None:
        """Avalia rotação sectorial apenas com o universo presente na watchlist."""
        config = MODULE_CONFIG["sector_rotation"]
        if not config.get("is_active"):
            return

        current_day = datetime.now(timezone.utc).day
        if current_day != int(config.get("rebalance_day", 1)):
            return

        spy_closes = await self._get_reference_closes("SPY")
        if not spy_closes:
            logger.info("Rotação sectorial sem avaliação: SPY indisponível.")
            return

        universe = set(config.get("universe_by_phase", {}).get(1, []))
        sector_specs = [spec for spec in self._watchlist if spec.symbol in universe]
        if not sector_specs:
            logger.info(
                "Rotação sectorial sem avaliação: watchlist não contém universo elegível."
            )
            return

        df_map: dict[str, dict[str, list[float]]] = {}
        for spec in sector_specs:
            closes = await self._get_reference_closes(spec.symbol)
            if closes:
                df_map[spec.symbol] = {"close": closes}

        # sector_rotation: módulo informativo em Fase 1.
        # Detecta oportunidades de rotação mas não submete ordens directamente.
        # Activar execução directa em Fase 2+ ajustando este bloco.
        rotation_signal = sector_rotation_signal(
            df_map=df_map,
            spy_closes=spy_closes,
            config=config,
            current_day_of_month=current_day,
        )
        if rotation_signal.get("signal") != "FLAT":
            logger.info(
                "Rotação sectorial detectada: SPY | top sectors: %s | confidence: %d",
                rotation_signal.get("metadata", {}).get("allocations", []),
                int(rotation_signal.get("confidence", 0)),
            )
            # TODO Fase 2: rebalancear posições baseado em momentum sectorial.

    async def _cancel_pending_entry_orders(self, grid: Grid) -> int:
        """Cancela apenas brackets de entrada ainda pendentes de uma grid."""
        if self._order_manager is None:
            return 0

        cancelled = 0
        seen_order_ids: set[int] = set()
        for level in grid.levels:
            if level.status != "pending":
                continue
            for order_id in (
                level.buy_order_id,
                level.stop_order_id,
                level.sell_order_id,
            ):
                if order_id is None or order_id in seen_order_ids:
                    continue
                seen_order_ids.add(order_id)
                if await self._order_manager.cancel_order(order_id):
                    cancelled += 1
        return cancelled

    async def _cancel_active_protection_orders(self, grid: Grid) -> int:
        """Cancela apenas protecções de níveis já comprados, para iniciar flatten seguro."""
        if self._order_manager is None:
            return 0

        cancelled = 0
        seen_order_ids: set[int] = set()
        for level in grid.levels:
            if level.status != "bought":
                continue
            for order_id in (level.stop_order_id, level.sell_order_id):
                if order_id is None or order_id in seen_order_ids:
                    continue
                seen_order_ids.add(order_id)
                if await self._order_manager.cancel_order(order_id):
                    cancelled += 1
        return cancelled

    async def _start_grid_flatten(self, grid: Grid) -> bool:
        """Inicia flatten broker-side para uma grid com posição aberta."""
        if self._order_manager is None:
            return False

        bought_levels = [level for level in grid.levels if level.status == "bought"]
        if not bought_levels:
            return True

        spec = self._get_instrument_spec(grid.symbol)
        contract = build_contract(spec)
        quantity = sum(level.quantity for level in bought_levels)
        if quantity <= 0:
            return False

        cancelled = await self._cancel_active_protection_orders(grid)
        close_key = f"flatten:{grid.id}:{grid.symbol}:SELL:{quantity}"
        flatten_started = await self._order_manager.close_position(
            contract,
            quantity=quantity,
            action="SELL",
            logical_close_key=close_key,
        )
        if flatten_started:
            grid.reconciliation_state = "flattening"
            self._grid_engine.save_state()
            logger.critical(
                "Flatten broker-side iniciado para %s (grid=%s, qty=%d, protecções canceladas=%d).",
                grid.symbol,
                grid.id,
                quantity,
                cancelled,
            )
            return True

        logger.critical(
            "Falha ao iniciar flatten broker-side para %s (grid=%s, qty=%d).",
            grid.symbol,
            grid.id,
            quantity,
        )
        return False

    async def _trip_partial_fill_halt(
        self,
        grid: Grid,
        level: GridLevel,
        leg: str,
        filled_quantity: int,
    ) -> None:
        """Activa halt fail-closed quando é detectado partial fill."""
        self._entry_halt_reason = "partial_fill_detected"
        self._emergency_halt = True
        grid.status = "paused"
        grid.reconciliation_state = "partial_fill"
        self._grid_engine.save_state()
        message = (
            f"Partial fill detectado em {grid.symbol} (grid={grid.id}, nível={level.level}, "
            f"perna={leg}, filled={filled_quantity}/{level.quantity}). "
            "Grid pausada e entradas bloqueadas até intervenção/reconciliação."
        )
        logger.critical(message)
        self._schedule_telegram(
            self._telegram.notify_operational_alert(message)
            if self._telegram else None
        )

    async def _run_reconciliation(self) -> None:
        """Lógica de reconciliação reutilizável — chamada por arranque e por comando runtime."""
        if self._reconciliation_in_progress:
            logger.warning("Reconciliação já em curso — a ignorar pedido duplicado.")
            return
        if self._order_manager is None:
            raise RuntimeError("OrderManager nao inicializado para reconciliacao.")

        self._reconciliation_in_progress = True
        try:
            logger.info("A iniciar reconciliacao...")
            position_observation = await self._fetch_positions_with_retry()
            open_orders = await self._order_manager.get_open_orders()
            if hasattr(self._order_manager, "sync_tracking_from_open_orders"):
                synced_orders = self._order_manager.sync_tracking_from_open_orders(open_orders)
                if synced_orders:
                    logger.info(
                        "Tracking local sincronizado com %d ordem(ns) aberta(s) do broker.",
                        synced_orders,
                    )
            if position_observation.state != "confirmed":
                reconciliation_lines = [
                    (
                        "Reconciliação inconclusiva: posições do broker não confirmadas. "
                        "Sem pausas nem cancelamentos automáticos."
                    ),
                ]
                for grid in self._grid_engine.get_active_grids():
                    grid.reconciliation_state = "unknown"
                await self._write_reconciliation_log(reconciliation_lines)
                self._grid_engine.save_state()
                self._schedule_telegram(
                    self._telegram.notify_reconciliation(reconciliation_lines[0])
                    if self._telegram else None
                )
                return

            positions = position_observation.positions

            positions_by_symbol: dict[str, float] = {}
            for position in positions:
                symbol = str(position.get("symbol", "")).upper()
                qty = float(position.get("quantity", 0.0) or 0.0)
                positions_by_symbol[symbol] = positions_by_symbol.get(symbol, 0.0) + qty

            grids_by_symbol: dict[str, list[Grid]] = {}
            for grid in self._grid_engine.get_active_grids():
                grids_by_symbol.setdefault(grid.symbol.upper(), []).append(grid)

            reconciliation_lines: list[str] = []
            ok_count = 0
            ghost_count = 0
            orphan_count = 0

            for symbol, grids in grids_by_symbol.items():
                ib_qty = positions_by_symbol.get(symbol, 0.0)
                expected_qty = sum(
                    level.quantity
                    for grid in grids
                    for level in grid.levels
                    if level.status == "bought"
                )

                if ib_qty and expected_qty == 0:
                    for grid in grids:
                        grid.status = "paused"
                        grid.reconciliation_state = "mismatch"
                    cancelled = await self._order_manager.cancel_symbol_orders(symbol)
                    line = (
                        f"{symbol}: divergencia de arranque (grid=0.00, ib={ib_qty:.2f}); "
                        f"grid pausada e ordens canceladas={cancelled}"
                    )
                    logger.critical(line)
                    reconciliation_lines.append(line)
                    continue

                if ib_qty == 0:
                    if expected_qty > 0 and any(
                        grid.reconciliation_state == "flattening"
                        for grid in grids
                    ):
                        for grid in grids:
                            self._grid_engine.close_grid(grid)
                            grid.reconciliation_state = "synced"
                        cancelled = await self._order_manager.cancel_symbol_orders(symbol)
                        line = (
                            f"{symbol}: flatten broker-side confirmado; grids fechadas e "
                            f"ordens residuais canceladas={cancelled}"
                        )
                        logger.info(line)
                        reconciliation_lines.append(line)
                        ok_count += len(grids)
                        continue
                    for grid in grids:
                        grid.status = "paused"
                        grid.reconciliation_state = "ghost"
                    cancelled = await self._order_manager.cancel_symbol_orders(symbol)
                    line = (
                        f"{symbol}: grid no JSON sem posicao real; marcada ghost e "
                        f"ordens pendentes canceladas={cancelled}"
                    )
                    logger.warning(line)
                    reconciliation_lines.append(line)
                    ghost_count += len(grids)
                    continue

                if abs(expected_qty - ib_qty) > 1e-9:
                    for grid in grids:
                        grid.status = "paused"
                        grid.reconciliation_state = "mismatch"
                    cancelled = await self._order_manager.cancel_symbol_orders(symbol)
                    line = (
                        f"{symbol}: divergencia de quantidade (grid={expected_qty:.2f}, "
                        f"ib={ib_qty:.2f}); grid pausada e ordens canceladas={cancelled}"
                    )
                    logger.critical(line)
                    reconciliation_lines.append(line)
                    continue

                for grid in grids:
                    grid.reconciliation_state = "synced"
                line = f"{symbol}: reconciliado com sucesso (qty={ib_qty:.2f})."
                logger.info(line)
                reconciliation_lines.append(line)
                ok_count += len(grids)

            for symbol, ib_qty in positions_by_symbol.items():
                if symbol not in grids_by_symbol and abs(ib_qty) > 1e-9:
                    orphan_info = {
                        "symbol": symbol,
                        "quantity": ib_qty,
                        "open_orders": [
                            order for order in open_orders
                            if str(order.get("symbol", "")).upper() == symbol
                        ],
                    }
                    self._orphan_positions[symbol] = orphan_info
                    line = (
                        f"{symbol}: posicao no IB sem grid ({ib_qty:.2f}); "
                        "registada como orfa e bloqueada para novas grids."
                    )
                    logger.warning(line)
                    reconciliation_lines.append(line)
                    orphan_count += 1

            if not reconciliation_lines:
                reconciliation_lines.append("Sem divergencias detectadas na reconciliacao.")

            summary = f"Reconciliação: {ok_count} OK | {ghost_count} fantasmas | {orphan_count} órfãos"
            reconciliation_lines.append(summary)
            await self._write_reconciliation_log(reconciliation_lines)
            self._schedule_telegram(
                self._telegram.notify_reconciliation(summary)
                if self._telegram else None
            )
            self._grid_engine.save_state()
        finally:
            self._reconciliation_in_progress = False

    async def _reconcile_startup(self) -> None:
        """Reconcilia o estado local com posicoes e ordens reais do IB no arranque."""
        await self._run_reconciliation()
        self._startup_reconciled = True

    # ------------------------------------------------------------------
    # Command consumer — ficheiros em data/commands/
    # ------------------------------------------------------------------

    def _move_command_file(self, path: Path, destination: str, result: dict[str, Any]) -> None:
        """Move um ficheiro de comando para processed/ ou failed/."""
        target_dir = path.parent / destination
        target_dir.mkdir(parents=True, exist_ok=True)
        try:
            envelope = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            envelope = {}
        envelope["status"] = destination.rstrip("/")
        envelope["processed_at"] = datetime.now(timezone.utc).isoformat()
        envelope.update(result)
        target_path = target_dir / path.name
        try:
            target_path.write_text(
                json.dumps(envelope, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            path.unlink(missing_ok=True)
        except OSError as exc:
            logger.error("Falha ao mover comando %s para %s: %s", path.name, destination, exc)

    async def _process_command_queue(self) -> None:
        """Consome ficheiros de comando pendentes em data/commands/."""
        commands_dir = self._config.data_dir / "commands"
        if not commands_dir.exists():
            return

        for cmd_path in sorted(commands_dir.glob("*.json")):
            try:
                raw = json.loads(cmd_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                logger.warning("Comando ignorado (parse error): %s — %s", cmd_path.name, exc)
                self._move_command_file(cmd_path, "failed", {"error": str(exc)})
                continue

            if not isinstance(raw, dict) or raw.get("status") != "pending":
                continue

            command = raw.get("command", "")
            payload = raw.get("payload", {})
            logger.info("A processar comando: %s (%s)", command, cmd_path.name)

            try:
                result = await self._dispatch_command(command, payload)
                self._move_command_file(cmd_path, "processed", result)
            except Exception as exc:  # noqa: BLE001
                logger.error("Erro ao executar comando %s: %s", command, exc)
                self._move_command_file(cmd_path, "failed", {"error": str(exc)})

    async def _dispatch_command(self, command: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Despacha um comando para o handler correcto."""
        if command == "pause":
            return await self._handle_pause(payload)
        if command == "resume":
            return await self._handle_resume(payload)
        if command == "reconcile_now":
            return await self._handle_reconcile_now(payload)
        if command == "export_snapshot":
            return await self._handle_export_snapshot(payload)
        return {"error": f"Comando desconhecido: {command}"}

    async def _handle_pause(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Activa pausa manual do bot."""
        del payload
        self._manual_pause = True
        logger.warning("Bot pausado manualmente via comando.")
        self._schedule_telegram(
            self._telegram.notify_operational_alert("Bot pausado manualmente.")
            if self._telegram else None
        )
        return {"action": "paused"}

    async def _handle_resume(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Desactiva pausa manual do bot."""
        del payload
        self._manual_pause = False
        logger.info("Bot retomado manualmente via comando.")
        self._schedule_telegram(
            self._telegram.notify_operational_alert("Bot retomado manualmente.")
            if self._telegram else None
        )
        return {"action": "resumed"}

    async def _handle_reconcile_now(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Executa reconciliação on-demand."""
        del payload
        if self._order_manager is None:
            return {"error": "OrderManager nao inicializado — reconciliação impossível."}
        try:
            await self._run_reconciliation()
            return {"action": "reconciled"}
        except RuntimeError as exc:
            return {"error": str(exc)}

    async def _handle_export_snapshot(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Exporta snapshot do estado actual do bot."""
        del payload
        snapshot = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "capital": getattr(self, "_capital", None),
            "manual_pause": self._manual_pause,
            "entry_halt_reason": self._entry_halt_reason,
            "emergency_halt": self._emergency_halt,
            "startup_reconciled": self._startup_reconciled,
            "active_grids": len(self._grid_engine.get_active_grids()) if hasattr(self, "_grid_engine") else 0,
            "watchlist": [spec.display for spec in self._watchlist] if hasattr(self, "_watchlist") else [],
            "period_pnl": dict(self._period_pnl) if hasattr(self, "_period_pnl") else {},
            "orphan_positions": list(self._orphan_positions.keys()) if hasattr(self, "_orphan_positions") else [],
            "dynamic_win_rate": getattr(self, "_dynamic_win_rate", None),
            "last_error": self._last_error,
        }
        snapshot_path = self._config.data_dir / "snapshot.json"
        try:
            snapshot_path.write_text(
                json.dumps(snapshot, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except OSError as exc:
            logger.error("Falha ao escrever snapshot: %s", exc)
            return {"error": str(exc)}
        logger.info("Snapshot exportado para %s", snapshot_path)
        return {"action": "exported", "path": str(snapshot_path)}

    # ------------------------------------------------------------------
    # Heartbeat — data/heartbeat.json
    # ------------------------------------------------------------------

    def _write_heartbeat(self) -> None:
        """Escreve o ficheiro de heartbeat com o estado actual do bot."""
        heartbeat = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "last_cycle_started_at": (
                self._last_cycle_started_at.isoformat()
                if self._last_cycle_started_at else None
            ),
            "last_cycle_completed_at": (
                self._last_cycle_completed_at.isoformat()
                if self._last_cycle_completed_at else None
            ),
            "manual_pause": self._manual_pause,
            "entry_halt_reason": self._entry_halt_reason,
            "emergency_halt": self._emergency_halt,
            "ib_connected": (
                self._connection.is_connected
                if hasattr(self, "_connection") and hasattr(self._connection, "is_connected")
                else False
            ),
            "last_error": self._last_error,
        }
        heartbeat_path = self._config.data_dir / "heartbeat.json"
        try:
            heartbeat_path.write_text(
                json.dumps(heartbeat, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except OSError as exc:
            logger.debug("Falha ao escrever heartbeat: %s", exc)

    # ------------------------------------------------------------------
    # Ciclo principal
    # ------------------------------------------------------------------

    async def run(self) -> None:
        """Ponto de entrada assincrono do bot — executa o loop infinito."""
        loop = asyncio.get_running_loop()
        self._setup_signal_handlers(loop)
        self._running = True

        # --- Apresentar banner ---
        if self._config.ib.paper_trading:
            logger.info("\n%s", _BANNER_PAPER.format(version=_VERSION).rstrip())
        else:
            logger.info("\n%s", _BANNER_LIVE.format(version=_VERSION).rstrip())

        logger.info(
            "Bot a iniciar — watchlist: %s | capital: %.2f | "
            "ciclo: %d s | paper: %s",
            [spec.display for spec in self._watchlist],
            self._capital,
            self._config.cycle_interval_seconds,
            self._config.ib.paper_trading,
        )
        if SECTOR_ROTATION_CONFIG.get("is_active"):
            logger.info(
                "sector_rotation: activo em modo informativo (execução directa: Fase 2+)"
            )
        if not OPTIONS_PREMIUM_CONFIG.get("is_active", False):
            logger.info(
                "options_premium: módulo desactivado (Fase 3+). "
                "Activa em OPTIONS_PREMIUM_CONFIG['is_active'] = True."
            )

        # --- Carregar estado persistido ---
        self._acquire_instance_lock()
        self._load_persisted_grids_or_fail_closed()
        try:
            self._grid_engine.load_state()
            num_grids = len(self._grid_engine.grids)
            logger.info(
                "Estado de grids carregado — %d grid(s) existente(s).", num_grids,
            )
        except Exception as exc:
            logger.error(
                "Erro ao carregar estado de grids: %s — a iniciar sem grids.", exc,
            )

        # --- Preflight e reconciliacao obrigatoria ---
        logger.info("A executar preflight operacional antes do loop principal...")
        await self.preflight_check()
        await self._reconcile_startup()
        if not self._startup_reconciled:
            raise RuntimeError("Reconciliação de arranque incompleta. Bot não pode iniciar.")

        if self._telegram is not None and (
            self._telegram_poll_task is None or self._telegram_poll_task.done()
        ):
            self._telegram_poll_task = asyncio.create_task(
                self._telegram.poll_commands(self._telegram_status_callback)
            )

        logger.info("Bot operacional — a entrar no loop principal.")

        # --- Loop principal ---
        try:
            while self._running:
                """
                # Verificar shutdown.request antes do ciclo
                # Verificar shutdown.request apos ciclo
                if self._shutdown_request_path.exists():
                    logger.warning(
                        "Ficheiro shutdown.request detectado antes do ciclo - "
                        "a iniciar encerramento gracioso."
                    )
                    self._shutdown_event.set()
                    break

                try:
                    await self._main_cycle()

                if self._shutdown_request_path.exists():
                    logger.warning(
                        "Ficheiro shutdown.request detectado apos ciclo - "
                        "a iniciar encerramento gracioso."
                    )
                    self._shutdown_event.set()

                if self._shutdown_event.is_set():
                    break
                except Exception as exc:  # noqa: BLE001
                    self._last_error = str(exc)
                    logger.error(
                        "Erro nao tratado no ciclo principal: %s", exc,
                        exc_info=True,
                    )
                    self._schedule_telegram(
                        self._telegram.critical_error(
                            error=str(exc),
                            location="main loop",
                            paper=self._config.ib.paper_trading,
                        ) if self._telegram else None
                    )

                # Persistir estado apos cada ciclo
                try:
                    self._grid_engine.save_state()
                except Exception as exc:  # noqa: BLE001
                    logger.error("Erro ao persistir estado das grids: %s", exc)

                # Dormir ate proximo ciclo (interruptivel por shutdown)
                try:
                    await asyncio.wait_for(
                        self._shutdown_event.wait(),
                        timeout=self._config.cycle_interval_seconds,
                    )
                    break
                    # Se o wait completou, o shutdown foi sinalizado
                    break
                except asyncio.TimeoutError:
                    # Timeout normal — continuar para o proximo ciclo
                    pass

                """
                if self._shutdown_request_path.exists():
                    logger.warning(
                        "Ficheiro shutdown.request detectado antes do ciclo - "
                        "a iniciar encerramento gracioso."
                    )
                    self._shutdown_event.set()
                    break

                try:
                    await self._main_cycle()
                except Exception as exc:  # noqa: BLE001
                    self._last_error = str(exc)
                    logger.error(
                        "Erro nao tratado no ciclo principal: %s", exc,
                        exc_info=True,
                    )
                    self._schedule_telegram(
                        self._telegram.critical_error(
                            error=str(exc),
                            location="main loop",
                            paper=self._config.ib.paper_trading,
                        ) if self._telegram else None
                    )

                if self._shutdown_request_path.exists():
                    logger.warning(
                        "Ficheiro shutdown.request detectado apos ciclo - "
                        "a iniciar encerramento gracioso."
                    )
                    self._shutdown_event.set()

                try:
                    self._grid_engine.save_state()
                except Exception as exc:  # noqa: BLE001
                    logger.error("Erro ao persistir estado das grids: %s", exc)

                try:
                    await asyncio.wait_for(
                        self._shutdown_event.wait(),
                        timeout=self._config.cycle_interval_seconds,
                    )
                    break
                except asyncio.TimeoutError:
                    pass

        finally:
            try:
                await self._graceful_shutdown()
            finally:
                self._release_instance_lock()

    # ------------------------------------------------------------------
    # Ciclo principal — um passo
    # ------------------------------------------------------------------

    async def _main_cycle(self) -> None:
        """Executa um ciclo completo do loop principal."""
        self._last_cycle_started_at = datetime.now(timezone.utc)

        await self._process_command_queue()
        logger.debug("--- Inicio de ciclo ---")
        self._reference_history_cache.clear()
        self._advance_defensive_day_counter()
        self._refresh_period_pnl()

        # 1. Verificar conexao IB (reconnect se necessario)
        connected = await self._connection.ensure_connected()
        if not connected:
            logger.warning("Sem ligacao ao IB — a saltar este ciclo.")
            self._write_heartbeat()
            return

        self.refresh_dynamic_win_rate()  # WinRate
        await self._evaluate_sector_rotation()

        # 7. Verificar limites de risco (daily/weekly/monthly)
        entry_halt_active = await self._check_risk_limits()

        if self._manual_pause:
            logger.info("Bot em pausa manual — novas entradas desactivadas, monitorização activa.")
        elif entry_halt_active:
            logger.warning(
                "Novas entradas bloqueadas por risco: %s",
                self._entry_halt_reason or "halt_desconhecido",
            )
        else:
            # Processar cada simbolo da watchlist
            for spec in self._watchlist:
                if not self._running:
                    break
                try:
                    await self._process_symbol(spec)
                except Exception as exc:  # noqa: BLE001
                    logger.error(
                        "Erro ao processar simbolo %s: %s", spec.display, exc,
                        exc_info=True,
                    )

        # 6. Monitorizar grids activas
        await self._monitor_active_grids()

        # Resumo diario as 23:00 UTC
        await self._check_daily_summary()

        # Limpar ordens concluidas do tracking
        if self._order_manager is not None:
            self._order_manager.cleanup_completed()

        self._last_cycle_completed_at = datetime.now(timezone.utc)
        self._write_heartbeat()
        logger.debug("--- Fim de ciclo ---")

    # ------------------------------------------------------------------
    # Processar um simbolo individual
    # ------------------------------------------------------------------

    async def _process_symbol(self, spec: InstrumentSpec) -> None:
        """Processa um simbolo: dados de mercado, regime, sinal, grid."""
        symbol = spec.symbol
        logger.debug("A processar simbolo: %s", spec.display)

        asset_type = get_asset_type(spec)
        if not is_market_open(spec.display, asset_type):
            session_state = get_session_state(spec)
            await self._handle_session_transition(spec, session_state)
            logger.info(
                "Sessao fechada para %s (%s) — sem novas entradas.",
                spec.display,
                session_state.status,
            )
            return

        session_state = get_session_state(spec)
        await self._handle_session_transition(spec, session_state)
        if minutes_to_close(spec.display, asset_type) <= 5:
            logger.info("Sessao em pre-close para %s.", spec.display)

        # 2. Obter dados de mercado (barras diarias)
        contract = build_contract(spec)
        qualified = await self._data_feed.qualify_contract(contract)
        if not qualified:
            logger.warning(
                "Nao foi possivel qualificar o contrato %s — a saltar.", spec.display,
            )
            return

        historical_started_at = time.monotonic()
        bars_df = await self._data_feed.get_historical_bars(
            contract, duration="1 Y", bar_size="1 day",
        )
        if not await self._apply_ib_request_events(
            self._connection.operational_events_since(historical_started_at),
            spec=spec,
            phase="historical_bars",
        ):
            return

        if bars_df.empty:
            logger.warning("Sem barras historicas para %s.", spec.display)
            return
        if not await self._check_warmup(spec, bars_df):
            return

        if symbol.upper() in {"VIX", "^VIX"}:
            self._reference_history_cache[symbol.upper()] = (
                bars_df["close"].astype(float).tolist()
            )
            logger.info(
                "Símbolo de referência %s actualizado — sem lógica de trading directa.",
                spec.display,
            )
            return

        # Calcular indicadores
        live_snapshot_started_at = time.monotonic()
        indicators = await self._data_feed.get_market_data_live(contract, bars_df)
        if not await self._apply_ib_request_events(
            self._connection.operational_events_since(live_snapshot_started_at),
            spec=spec,
            phase="live_snapshot",
        ):
            return

        # Verificar se todos os indicadores necessarios estao disponiveis
        required_keys = [
            "last_close", "current_price", "sma25", "sma50", "sma200",
            "rsi14", "atr14", "bb_lower", "volume_avg_20", "atr_avg_60",
        ]
        missing = [k for k in required_keys if indicators.get(k) is None]
        if missing:
            logger.warning(
                "Indicadores em falta para %s: %s — a saltar.", spec.display, missing,
            )
            return

        price_source = str(indicators.get("price_source") or "unknown")
        price_fresh = bool(indicators.get("price_fresh", False))
        if not price_fresh:
            logger.warning(
                "Entradas bloqueadas para %s por preço stale/inconclusivo (%s).",
                spec.display,
                price_source,
            )
            return

        price: float = indicators["current_price"]  # type: ignore[assignment]
        last_close: float = indicators["last_close"]  # type: ignore[assignment]
        sma25: float = indicators["sma25"]  # type: ignore[assignment]
        sma50: float = indicators["sma50"]  # type: ignore[assignment]
        sma200: float = indicators["sma200"]  # type: ignore[assignment]
        rsi14: float = indicators["rsi14"]  # type: ignore[assignment]
        atr14: float = indicators["atr14"]  # type: ignore[assignment]
        bb_lower: float = indicators["bb_lower"]  # type: ignore[assignment]
        volume_avg_20: float = indicators["volume_avg_20"]  # type: ignore[assignment]
        atr_avg_60: float = indicators["atr_avg_60"]  # type: ignore[assignment]

        # 3. Calcular regime (BULL/BEAR/SIDEWAYS)
        regime_info: RegimeInfo = detect_regime(
            price=price,
            sma50=sma50,
            sma200=sma200,
            rsi=rsi14,
            atr=atr14,
            atr_avg_60=atr_avg_60,
        )

        logger.info(
            "Regime de %s: %s — %s",
            spec.display, regime_info.regime.value, regime_info.motivo,
        )
        logger.info(
            "Mercado %s: preço actual=%.4f | último fecho=%.4f",
            spec.display,
            price,
            last_close,
        )

        # Notificar mudanca de regime
        old_regime = self._last_regimes.get(spec.display)
        new_regime = regime_info.regime.value
        if old_regime is not None and old_regime != new_regime:
            logger.info(
                "Mudanca de regime para %s: %s -> %s",
                spec.display, old_regime, new_regime,
            )
            self._schedule_telegram(
                self._telegram.notify_regime_change(spec.display, old_regime, new_regime)
                if self._telegram else None
            )
        self._last_regimes[spec.display] = new_regime

        # Obter volume actual
        volume_started_at = time.monotonic()
        current_volume = await self._data_feed.get_current_volume(contract)
        if not await self._apply_ib_request_events(
            self._connection.operational_events_since(volume_started_at),
            spec=spec,
            phase="live_volume",
        ):
            return
        volume: float = current_volume if current_volume is not None else 0.0
        closes = bars_df["close"].astype(float).tolist()  # Finding 2
        rsi2 = calculate_rsi2(closes)  # Finding 2

        # 4. Calcular sinal Kotegawa (deviation SMA25 + confirmacoes)
        signal_result: SignalResult = kotegawa_signal(
            price=price,
            sma25=sma25,
            rsi=rsi14,
            bb_lower=bb_lower,
            volume=volume,
            vol_avg_20=volume_avg_20,
            regime=regime_info.regime.value,
            sma50=sma50,
            sma200=sma200,
            rsi2=rsi2,  # Finding 2
        )

        logger.info(
            "Sinal Kotegawa para %s: signal=%s | horizonte=%s | desvio=%.2f%% | "
            "confirmacoes=%d | confianca=%s | multiplicador=%.2f",
            spec.display,
            signal_result.signal,
            signal_result.horizon.value,
            signal_result.deviation,
            signal_result.confirmacoes,
            signal_result.confianca.value,
            signal_result.size_multiplier,
        )

        market_data = dict(indicators)
        spy_closes: list[float] = []
        tlt_closes: list[float] = []
        open_positions: list[str] = []
        returns_map: dict[str, list[float]] = {}
        bond_etfs = set(MODULE_CONFIG["bond_mr_hedge"].get("kairi_thresholds", {}).keys())
        intl_etfs = set(MODULE_CONFIG["intl_etf_mr"].get("kairi_thresholds", {}).keys())
        options_symbols = set(MODULE_CONFIG["options_premium"].get("allowed_symbols", []))
        vix_proxy: float | None = None
        if spec.symbol in bond_etfs or spec.symbol in options_symbols:
            vix_proxy = await self._get_vix_proxy()
        market_data["vix_proxy"] = vix_proxy
        if spec.symbol in bond_etfs:
            spy_closes = await self._get_reference_closes("SPY")
            tlt_closes = closes if spec.symbol == "TLT" else await self._get_reference_closes("TLT")
        if spec.symbol in intl_etfs:
            open_positions, returns_map = await self._build_intl_etf_context(
                spec.symbol,
                bars_df,
            )

        new_signal = await process_new_modules(
            spec=spec,
            bars_df=bars_df,
            market_data=market_data,
            risk_mgr=self._risk_manager,
            config=MODULE_CONFIG,
            spy_closes=spy_closes,
            tlt_closes=tlt_closes,
            defensive_state=self._defensive_state,
            open_positions=open_positions,
            returns_map=returns_map,
        )

        if (
            new_signal
            and new_signal.get("metadata", {}).get("module") == "bond_mr_hedge"
            and new_signal.get("metadata", {}).get("defensive_action") == "ENTER_DEFENSIVE"
        ):
            self._defensive_state["mode"] = "DEFENSIVE"
            self._defensive_state["days_in_defensive"] = 0
        elif (
            new_signal
            and new_signal.get("metadata", {}).get("reason") == "exit_defensive"
        ):
            self._defensive_state["mode"] = "NORMAL"
            self._defensive_state["days_in_defensive"] = 0

        if new_signal and new_signal.get("signal") not in ("FLAT", None):
            logger.info(
                "Sinal multi-instrumento para %s: signal=%s | confidence=%s | módulo=%s",
                spec.display,
                new_signal.get("signal"),
                new_signal.get("confidence"),
                new_signal.get("metadata", {}).get("module"),
            )

            action = str(new_signal.get("signal", "FLAT"))
            if action == "SELL_PUT":
                logger.info(
                    "Options Premium detectado para %s com strike=%s. "
                    "Modo auditável nesta fase; submissão automática fica para Fase 3.",
                    spec.display,
                    new_signal.get("metadata", {}).get("strike"),
                )
            else:
                logger.warning(
                    "Execução directa de sinais multi-instrumento desactivada por segurança "
                    "até integração na state machine persistente: %s (%s).",
                    spec.display,
                    action,
                )

        # 5. SE sinal valido E risco ok → criar grid
        if not session_state.can_open_new_grid:
            logger.info(
                "Sem novas grids em %s: sessao em %s.",
                spec.display,
                session_state.status,
            )
            return

        if signal_result.signal and signal_result.size_multiplier > 0:
            await self._attempt_grid_creation(
                spec=spec,
                contract=contract,
                price=price,
                atr=atr14,
                regime_info=regime_info,
                signal_result=signal_result,
                bars_df=bars_df,
                session_ok=session_state.can_open_new_grid,
                data_fresh=price_fresh,
                warmup_ok=True,
            )

    async def _submit_grid_level_bracket(
        self,
        *,
        contract: Any,
        grid: Grid,
        level: GridLevel,
    ) -> bool:
        """Submete o bracket de um nível com chave lógica estável e persistência imediata."""
        assert self._order_manager is not None
        logical_trade_key = OrderManager.build_logical_trade_key(
            grid.id,
            level.level,
            "BUY",
        )
        result = await self._order_manager.submit_bracket_order(
            contract=contract,
            action="BUY",
            quantity=level.quantity,
            entry_price=level.buy_price,
            stop_price=level.stop_price,
            take_profit_price=level.sell_price,
            grid_id=grid.id,
            level=level.level,
            logical_trade_key=logical_trade_key,
        )
        if result is None:
            return False

        level.buy_order_id = result.get("order_id")
        level.stop_order_id = result.get("stop_order_id")
        level.sell_order_id = result.get("tp_order_id")
        self._grid_engine.save_state()
        logger.info(
            "Bracket colocado para %s, nivel %d a %.4f "
            "(stop=%.4f, tp=%.4f, qtd=%d, key=%s)",
            grid.symbol,
            level.level,
            level.buy_price,
            level.stop_price,
            level.sell_price,
            level.quantity,
            logical_trade_key,
        )
        return True

    # ------------------------------------------------------------------
    # Tentativa de criacao de grid
    # ------------------------------------------------------------------

    async def _attempt_grid_creation(
        self,
        spec: InstrumentSpec,
        contract: Any,
        price: float,
        atr: float,
        regime_info: RegimeInfo,
        signal_result: SignalResult,
        bars_df: Any | None = None,
        *,
        session_ok: bool,
        data_fresh: bool,
        warmup_ok: bool,
    ) -> None:
        """Tenta criar uma nova grid se o risco permitir."""
        assert self._order_manager is not None
        symbol = spec.symbol

        if symbol.upper() in self._orphan_positions:
            logger.warning(
                "Nova grid bloqueada para %s: existe posicao orfa por reconciliar.",
                spec.display,
            )
            return

        # Verificar se ja existe grid activa para este simbolo
        active_grids = self._grid_engine.get_active_grids()
        symbol_grids = [g for g in active_grids if g.symbol == symbol]
        if symbol_grids:
            logger.info(
                "Ja existe grid activa para %s — nao criar nova.", symbol,
            )
            return

        # Verificar limite de grids
        if not self._risk_manager.check_max_grids(len(active_grids)):
            logger.info(
                "Limite de grids activas atingido — nao criar nova para %s.",
                symbol,
            )
            return

        # Obter metricas para position sizing
        metrics = self._trade_logger.calculate_metrics()
        win_rate = metrics.get("win_rate", self._dynamic_win_rate) or self._dynamic_win_rate  # WinRate
        payoff_ratio = metrics.get("payoff_ratio", 2.5) or 2.5

        # Determinar numero de niveis para o regime
        num_levels = GridEngine.get_num_levels_for_regime(
            regime_info.regime.value,
        )

        initial_critical_inputs = {
            "market_price": price,
            "atr": atr,
            "signal_size_multiplier": signal_result.size_multiplier,
        }
        if not critical_inputs_are_finite(initial_critical_inputs):
            gate = build_pre_trade_gate(
                session_ok=session_ok,
                data_fresh=data_fresh,
                warmup_ok=warmup_ok,
                critical_inputs=initial_critical_inputs,
                quantity_ok=False,
                risk_ok=False,
                details={"symbol": symbol, "stage": "pre_sizing"},
            )
            logger.warning(
                "Pre-trade gate rejeitou grid para %s antes do sizing: %s | gate=%s",
                symbol,
                gate.rejection_reasons(),
                gate.as_dict(),
            )
            return

        # Calcular position size para o primeiro nivel (exemplo)
        spacing_pct = self._grid_engine.calculate_spacing_pct(price, atr)
        spacing = round(price * spacing_pct / 100.0, 6)
        first_buy = price - spacing
        first_stop = self._risk_manager.calculate_stop_loss(first_buy, atr)
        first_take_profit = self._risk_manager.calculate_take_profit(first_buy, atr)

        base_quantity = self._risk_manager.position_size_per_level(
            capital=self._capital,
            entry=first_buy,
            stop=first_stop,
            win_rate=win_rate if 0 < win_rate < 1 else self._dynamic_win_rate,  # WinRate
            payoff_ratio=payoff_ratio if payoff_ratio > 0 else 2.5,
            num_levels=num_levels,  # Finding 4d
        )

        if base_quantity <= 0:
            gate = build_pre_trade_gate(
                session_ok=session_ok,
                data_fresh=data_fresh,
                warmup_ok=warmup_ok,
                critical_inputs={
                    "market_price": price,
                    "atr": atr,
                    "entry_price": first_buy,
                    "stop_price": first_stop,
                    "take_profit_price": first_take_profit,
                },
                quantity_ok=False,
                risk_ok=False,
                details={"symbol": symbol, "stage": "post_sizing", "base_quantity": base_quantity},
            )
            logger.warning(
                "Pre-trade gate rejeitou grid para %s: %s | gate=%s",
                symbol,
                gate.rejection_reasons(),
                gate.as_dict(),
            )
            return

        # Validar a ordem com o gestor de risco
        period_pnl = dict(self._period_pnl)
        current_positions = len(
            [g for g in active_grids
             for lv in g.levels if lv.status == "bought"]
        )
        open_positions: list[str] = []
        returns_map: dict[str, list[float]] = {}
        if bars_df is not None:
            open_positions, returns_map = await self._build_intl_etf_context(
                symbol,
                bars_df,
            )

        order_approved, rejection_reason = self._risk_manager.validate_order({
            "symbol": symbol,
            "entry_price": first_buy,
            "stop_price": first_stop,
            "take_profit_price": first_take_profit,
            "capital": self._capital,
            "daily_pnl": period_pnl["daily"],
            "weekly_pnl": period_pnl["weekly"],
            "monthly_pnl": period_pnl["monthly"],
            "current_positions": current_positions,
            "current_grids": len(active_grids),
            "win_rate": win_rate if 0 < win_rate < 1 else self._dynamic_win_rate,  # WinRate
            "payoff_ratio": payoff_ratio if payoff_ratio > 0 else 2.5,
            "num_levels": num_levels,  # Finding 4d
            "open_positions": open_positions,
            "returns_map": returns_map,
        })

        gate = build_pre_trade_gate(
            session_ok=session_ok,
            data_fresh=data_fresh,
            warmup_ok=warmup_ok,
            critical_inputs={
                "market_price": price,
                "atr": atr,
                "entry_price": first_buy,
                "stop_price": first_stop,
                "take_profit_price": first_take_profit,
            },
            quantity_ok=base_quantity > 0,
            risk_ok=order_approved,
            details={
                "symbol": symbol,
                "stage": "post_risk",
                "base_quantity": base_quantity,
                "risk_rejection_reason": rejection_reason,
            },
            risk_rejection_reason=rejection_reason,
        )

        if not gate.is_admitted():
            logger.warning(
                "Pre-trade gate rejeitou grid para %s: %s | gate=%s",
                symbol,
                gate.rejection_reasons(),
                gate.as_dict(),
            )
            return

        # Criar a grid em staging antes de qualquer efeito broker-side
        grid = self._grid_engine.create_grid(
            symbol=symbol,
            center_price=price,
            atr=atr,
            regime=regime_info.regime.value,
            num_levels=num_levels,
            base_quantity=base_quantity,
            confidence=signal_result.confianca.value,
            size_multiplier=signal_result.size_multiplier,
            stop_atr_mult=self._config.risk.stop_atr_mult,
            tp_atr_mult=self._config.risk.tp_atr_mult,
            status="staging",
        )
        self._grid_engine.save_state()

        logger.info(
            "Grid staged para %s: %s | %d niveis | centro=%.4f | ATR=%.4f",
            symbol, grid.id, len(grid.levels), price, atr,
        )

        # Colocar ordens limit em cada nivel
        for level in grid.levels:
            if level.status != "pending":
                continue

            submitted = await self._submit_grid_level_bracket(
                contract=contract,
                grid=grid,
                level=level,
            )
            if not submitted:
                await self._cancel_pending_entry_orders(grid)
                self._grid_engine.fail_grid(
                    grid,
                    f"initial_order_submission_failed_level_{level.level}",
                )
                self._grid_engine.save_state()
                logger.error(
                    "Grid %s falhou durante staging no nivel %d. Activação abortada.",
                    grid.id,
                    level.level,
                )
                return

        self._grid_engine.activate_grid(grid)
        self._grid_engine.save_state()

        # Notificar Telegram
        self._schedule_telegram(
            self._telegram.notify_grid_opened(
                symbol=symbol,
                regime=regime_info.regime.value,
                levels=len(grid.levels),
                spacing=grid.spacing,
                center=grid.center_price,
                confidence=signal_result.confianca.value,
            ) if self._telegram else None
        )

    # ------------------------------------------------------------------
    # Monitorizacao de grids activas
    # ------------------------------------------------------------------

    async def _monitor_active_grids(self) -> None:
        """
        Monitoriza todas as grids activas:
        - Verifica se ordens foram executadas
        - Processa take-profit e stop-loss
        - Fecha grids esgotadas
        - Recentra grids quando o preco se afasta
        """
        if self._order_manager is None:
            return

        active_grids = self._grid_engine.get_active_grids()

        for grid in active_grids:
            try:
                await self._monitor_single_grid(grid)
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "Erro ao monitorizar grid %s: %s", grid.id, exc,
                    exc_info=True,
                )

    async def _monitor_single_grid(self, grid: Grid) -> None:
        """Monitoriza uma grid individual."""
        assert self._order_manager is not None

        now_iso = datetime.now(tz=timezone.utc).isoformat()
        spec = self._get_instrument_spec(grid.symbol)
        session_state = get_session_state(spec)

        if session_state.is_pre_close:
            cancelled = await self._cancel_pending_entry_orders(grid)
            if cancelled > 0:
                logger.info(
                    "Grid %s: %d ordens de entrada canceladas por pre-close.",
                    grid.id,
                    cancelled,
                )

        for level in grid.levels:
            logical_trade_key = OrderManager.build_logical_trade_key(
                grid.id,
                level.level,
                "BUY",
            )
            # Verificar niveis pendentes — ordem de compra executada?
            if level.status == "pending" and level.buy_order_id is not None:
                order_info = self._order_manager.get_order_info(level.buy_order_id)
                status = self._order_manager.get_order_status(level.buy_order_id)
                if (
                    order_info is not None
                    and 0 < order_info.filled_quantity < level.quantity
                    and status != OrderStatus.FILLED
                ):
                    await self._trip_partial_fill_halt(
                        grid,
                        level,
                        order_info.leg_type,
                        order_info.filled_quantity,
                    )
                    return
                if status == OrderStatus.FILLED:
                    fill_price = (
                        order_info.fill_price if order_info else level.buy_price
                    )
                    self._grid_engine.on_level_bought(
                        grid, level.level, fill_price, now_iso,
                    )
                    logger.info(
                        "Grid %s: nivel %d comprado a %.4f",
                        grid.id, level.level, fill_price,
                    )
                    # Registar trade
                    self._trade_logger.log_trade({
                        "timestamp": now_iso,
                        "symbol": grid.symbol,
                        "side": "BUY",
                        "price": fill_price,
                        "quantity": level.quantity,
                        "order_id": level.buy_order_id,
                        "grid_id": grid.id,
                        "level": level.level,
                        "pnl": None,
                        "regime": grid.regime,
                        "signal_confidence": grid.confidence,
                        "logical_trade_key": logical_trade_key,
                        "order_ref": logical_trade_key,
                        "order_leg": "parent",
                    })
                    self._schedule_telegram(
                        self._telegram.trade_opened(
                            symbol=grid.symbol,
                            action="BUY",
                            entry=fill_price,
                            stop=level.stop_price,
                            tp=level.sell_price,
                            confidence=3 if str(grid.confidence).upper() == "ALTO" else 2,
                            module="kotegawa",
                            regime=grid.regime,
                            paper=self._config.ib.paper_trading,
                        ) if self._telegram else None
                    )

            # Verificar niveis comprados — take-profit ou stop-loss?
            elif level.status == "bought":
                # Verificar take-profit (sell_order_id)
                if level.sell_order_id is not None:
                    tp_info = self._order_manager.get_order_info(level.sell_order_id)
                    tp_status = self._order_manager.get_order_status(
                        level.sell_order_id
                    )
                    if (
                        tp_info is not None
                        and 0 < tp_info.filled_quantity < level.quantity
                        and tp_status != OrderStatus.FILLED
                    ):
                        await self._trip_partial_fill_halt(
                            grid,
                            level,
                            tp_info.leg_type,
                            tp_info.filled_quantity,
                        )
                        return
                    if tp_status == OrderStatus.FILLED:
                        fill_price = (
                            tp_info.fill_price
                            if tp_info else level.sell_price
                        )
                        self._grid_engine.on_level_sold(
                            grid, level.level, fill_price, now_iso,
                        )
                        logger.info(
                            "Grid %s: nivel %d vendido (take-profit) a %.4f",
                            grid.id, level.level, fill_price,
                        )
                        # Registar trade de saida
                        pnl = (fill_price - level.buy_price) * level.quantity
                        self._trade_logger.log_trade({
                            "timestamp": now_iso,
                            "symbol": grid.symbol,
                            "side": "SELL",
                            "price": fill_price,
                            "quantity": level.quantity,
                            "order_id": level.sell_order_id,
                            "grid_id": grid.id,
                            "level": level.level,
                            "pnl": pnl,
                            "regime": grid.regime,
                            "signal_confidence": grid.confidence,
                            "logical_trade_key": logical_trade_key,
                            "order_ref": logical_trade_key,
                            "order_leg": "tp",
                        })
                        self._capital += pnl  # Finding 8
                        self._risk_manager.update_capital(self._capital)  # Finding 8
                        self._risk_manager.update_peak_equity(self._capital)  # Finding 8
                        self._refresh_period_pnl()
                        self._schedule_telegram(
                            self._telegram.trade_closed(
                                symbol=grid.symbol,
                                action="SELL",
                                entry=level.buy_price,
                                exit_price=fill_price,
                                pnl=pnl,
                                module="kotegawa",
                                paper=self._config.ib.paper_trading,
                            ) if self._telegram else None
                        )
                        self._risk_manager.clear_level_losing(grid.symbol, level.level)
                        continue  # nivel processado

                # Verificar stop-loss (stop_order_id)
                if level.stop_order_id is not None:
                    sl_info = self._order_manager.get_order_info(level.stop_order_id)
                    sl_status = self._order_manager.get_order_status(
                        level.stop_order_id
                    )
                    if (
                        sl_info is not None
                        and 0 < sl_info.filled_quantity < level.quantity
                        and sl_status != OrderStatus.FILLED
                    ):
                        await self._trip_partial_fill_halt(
                            grid,
                            level,
                            sl_info.leg_type,
                            sl_info.filled_quantity,
                        )
                        return
                    if sl_status == OrderStatus.FILLED:
                        fill_price = (
                            sl_info.fill_price
                            if sl_info else level.stop_price
                        )
                        # Stop-loss atingido — nivel NAO sera reaberto
                        self._grid_engine.on_level_stopped(
                            grid, level.level, fill_price, now_iso,
                        )
                        loss = (fill_price - level.buy_price) * level.quantity
                        logger.warning(
                            "Grid %s: nivel %d parado (stop-loss) a %.4f | "
                            "perda: %.2f | NAO sera reaberto",
                            grid.id, level.level, fill_price, loss,
                        )
                        # Registar trade de saida com perda
                        self._trade_logger.log_trade({
                            "timestamp": now_iso,
                            "symbol": grid.symbol,
                            "side": "SELL",
                            "price": fill_price,
                            "quantity": level.quantity,
                            "order_id": level.stop_order_id,
                            "grid_id": grid.id,
                            "level": level.level,
                            "pnl": loss,
                            "regime": grid.regime,
                            "signal_confidence": grid.confidence,
                            "logical_trade_key": logical_trade_key,
                            "order_ref": logical_trade_key,
                            "order_leg": "stop",
                        })
                        self._capital += loss  # Finding 8
                        self._risk_manager.update_capital(self._capital)  # Finding 8
                        self._risk_manager.update_peak_equity(self._capital)  # Finding 8
                        self._refresh_period_pnl()
                        # Verificar se o kill switch deve ser activado
                        daily_summary = self._trade_logger.get_daily_summary()
                        daily_pnl_pct = (
                            (daily_summary.get("total_pnl", 0.0) / self._capital * 100)
                            if self._capital > 0 else 0.0
                        )
                        is_killed = not self._risk_manager.check_daily_limit(
                            daily_summary.get("total_pnl", 0.0), self._capital,
                        )
                        self._schedule_telegram(
                            self._telegram.trade_closed(
                                symbol=grid.symbol,
                                action="SELL",
                                entry=level.buy_price,
                                exit_price=fill_price,
                                pnl=loss,
                                module="kotegawa",
                                paper=self._config.ib.paper_trading,
                            ) if self._telegram else None
                        )
                        self._risk_manager.mark_level_losing(grid.symbol, level.level)
                        continue  # nivel processado

        # Verificar se a grid esta esgotada
        if is_grid_exhausted(grid):
            self._grid_engine.close_grid(grid)
            logger.info(
                "Grid %s esgotada e fechada | P&L total: %.4f",
                grid.id, grid.total_pnl,
            )
            levels_used = len(
                [level for level in grid.levels if level.status in ("sold", "stopped")]
            )
            self._schedule_telegram(
                self._telegram.grid_exhausted(
                    symbol=grid.symbol,
                    regime=grid.regime,
                    levels_used=levels_used,
                    module="kotegawa",
                    paper=self._config.ib.paper_trading,
                ) if self._telegram else None
            )
            # Cancelar quaisquer ordens pendentes no IB
            await self._order_manager.cancel_all_grid_orders(grid.id)
            return

        if self._emergency_halt or grid.reconciliation_state == "flattening":
            return

        # Verificar se o preco saiu da grid → recentrar
        contract = build_contract(spec)
        price_snapshot = await self._data_feed.get_current_price_details(contract)
        current_price = price_snapshot.get("price")
        price_source = str(price_snapshot.get("source") or "unknown")
        price_fresh = bool(price_snapshot.get("fresh"))

        if current_price is None:
            return

        if not price_fresh:
            logger.warning(
                "Grid %s: ajustamento dinamico ignorado por preco stale "
                "(source=%s, price=%s).",
                grid.id,
                price_source,
                current_price,
            )
            return

        if not session_state.can_open_new_grid:
            return

        bars_df = await self._data_feed.get_historical_bars(
            contract, duration="1 Y", bar_size="1 day",
        )
        if bars_df.empty:
            return

        indicators = self._data_feed.get_market_data(contract, bars_df)
        new_atr = indicators.get("atr14") or grid.atr
        current_price = float(current_price)
        should_recenter = self._grid_engine.should_recenter(grid, current_price)
        should_respace = self._grid_engine.should_respace(
            grid,
            current_price,
            float(new_atr),
        )

        if should_recenter or should_respace:
            logger.info(
                "Grid %s: ajustamento dinamico activado "
                "(recenter=%s, respace=%s) para preco %.4f.",
                grid.id,
                should_recenter,
                should_respace,
                current_price,
            )
            # Cancelar ordens pendentes antes de recentrar
            await self._cancel_pending_entry_orders(grid)

            self._grid_engine.recenter_grid(
                grid,
                current_price,
                float(new_atr),
                stop_atr_mult=self._config.risk.stop_atr_mult,
                tp_atr_mult=self._config.risk.tp_atr_mult,
                respaced_at=now_iso,
            )
            self._grid_engine.save_state()

            # Colocar novas ordens para niveis pendentes
            for level in grid.levels:
                if level.status == "pending":
                    submitted = await self._submit_grid_level_bracket(
                        contract=contract,
                        grid=grid,
                        level=level,
                    )
                    if not submitted:
                        logger.error(
                                "Grid %s: falha ao repor bracket do nivel %d após recentragem.",
                            grid.id,
                            level.level,
                        )
                        break

    # ------------------------------------------------------------------
    # Verificacao de limites de risco
    # ------------------------------------------------------------------

    async def _check_risk_limits(self) -> bool:
        """
        Verifica os limites de risco diário, semanal e mensal.

        Retorna True se novas entradas devem ficar bloqueadas neste ciclo.
        """
        if self._emergency_halt:
            self._entry_halt_reason = self._entry_halt_reason or "monthly_kill_switch"
            return True

        self._entry_halt_reason = None
        current_equity = await self._fetch_current_equity_snapshot()
        if current_equity is None:
            logger.critical(
                "Snapshot de equity indisponivel. Entradas bloqueadas em fail-safe."
            )
            self._entry_halt_reason = "equity_snapshot_unavailable"
            for grid in self._grid_engine.get_active_grids():
                await self._cancel_pending_entry_orders(grid)
            return True

        now_utc = datetime.now(timezone.utc)
        self._capital = current_equity
        self._risk_manager.update_capital(current_equity)
        if hasattr(self._risk_manager, "update_peak_equity"):
            self._risk_manager.update_peak_equity(current_equity)

        period_pnl = self._refresh_period_pnl(now=now_utc)
        if not self._sync_equity_baselines(current_equity, now=now_utc):
            logger.critical(
                "Baselines de equity invalidos/corrompidos. Entradas bloqueadas em fail-safe."
            )
            self._entry_halt_reason = "equity_baseline_invalid"
            for grid in self._grid_engine.get_active_grids():
                await self._cancel_pending_entry_orders(grid)
            return True

        daily_baseline = float(self._equity_baselines["daily"]["equity"])
        weekly_baseline = float(self._equity_baselines["weekly"]["equity"])
        monthly_baseline = float(self._equity_baselines["monthly"]["equity"])
        daily_pnl = self._equity_delta_since_baseline("daily", current_equity)
        weekly_pnl = self._equity_delta_since_baseline("weekly", current_equity)
        monthly_pnl = self._equity_delta_since_baseline("monthly", current_equity)

        if daily_pnl is None or weekly_pnl is None or monthly_pnl is None:
            logger.critical(
                "Nao foi possivel calcular drawdown por equity. Entradas bloqueadas."
            )
            self._entry_halt_reason = "equity_baseline_invalid"
            for grid in self._grid_engine.get_active_grids():
                await self._cancel_pending_entry_orders(grid)
            return True

        daily_loss = self._equity_loss_ratio(daily_baseline, current_equity) or 0.0
        weekly_loss = self._equity_loss_ratio(weekly_baseline, current_equity) or 0.0
        monthly_loss = self._equity_loss_ratio(monthly_baseline, current_equity) or 0.0

        # Verificar limite diario (3%)
        daily_ok = self._risk_manager.check_daily_limit(daily_pnl, daily_baseline)
        if daily_loss >= 0.70 * self._config.risk.daily_loss_limit:
            self._schedule_telegram(
                self._telegram.kill_switch_warning(
                    level="diário",
                    current_pct=daily_loss,
                    limit_pct=self._config.risk.daily_loss_limit,
                    paper=self._config.ib.paper_trading,
                ) if self._telegram else None
            )
        if not daily_ok:
            logger.critical(
                "LIMITE DIARIO ATINGIDO — P&L do dia: %.2f (%.2f%% do capital). "
                "Novas entradas bloqueadas ate novo reset diário.",
                daily_pnl,
                daily_loss * 100,
            )
            self._entry_halt_reason = "daily_limit"
            for grid in self._grid_engine.get_active_grids():
                await self._cancel_pending_entry_orders(grid)
            self._schedule_telegram(
                self._telegram.kill_switch_triggered(
                    level="diário",
                    current_pct=daily_loss,
                    paper=self._config.ib.paper_trading,
                ) if self._telegram else None
            )
            return True

        # Verificar limite semanal (6%)
        weekly_ok = self._risk_manager.check_weekly_limit(weekly_pnl, weekly_baseline)
        if weekly_loss >= 0.70 * self._config.risk.weekly_loss_limit:
            self._schedule_telegram(
                self._telegram.kill_switch_warning(
                    level="semanal",
                    current_pct=weekly_loss,
                    limit_pct=self._config.risk.weekly_loss_limit,
                    paper=self._config.ib.paper_trading,
                ) if self._telegram else None
            )
        if not weekly_ok:
            logger.critical(
                "LIMITE SEMANAL ATINGIDO — P&L da semana: %.2f (%.2f%% do capital). "
                "Novas entradas bloqueadas até nova semana.",
                weekly_pnl,
                weekly_loss * 100,
            )
            self._entry_halt_reason = "weekly_limit"
            for grid in self._grid_engine.get_active_grids():
                await self._cancel_pending_entry_orders(grid)
            self._schedule_telegram(
                self._telegram.kill_switch_triggered(
                    level="semanal",
                    current_pct=weekly_loss,
                    paper=self._config.ib.paper_trading,
                ) if self._telegram else None
            )
            return True

        # Verificar kill switch mensal (10%)
        if monthly_loss >= 0.70 * self._config.risk.monthly_dd_limit:
            self._schedule_telegram(
                self._telegram.kill_switch_warning(
                    level="mensal",
                    current_pct=monthly_loss,
                    limit_pct=self._config.risk.monthly_dd_limit,
                    paper=self._config.ib.paper_trading,
                ) if self._telegram else None
            )
        monthly_ok = self._risk_manager.check_kill_switch(
            monthly_pnl, monthly_baseline,
        )
        if not monthly_ok:
            logger.critical(
                "KILL SWITCH MENSAL ACTIVADO — Drawdown mensal: %.2f. "
                "Novas entradas bloqueadas. Será iniciado flatten broker-side "
                "e o estado local só fecha após confirmação pela reconciliação.",
                monthly_pnl,
            )
            self._entry_halt_reason = "monthly_kill_switch"
            self._emergency_halt = True
            for grid in self._grid_engine.get_active_grids():
                await self._cancel_pending_entry_orders(grid)
                await self._start_grid_flatten(grid)

            self._schedule_telegram(
                self._telegram.kill_switch_triggered(
                    level="mensal",
                    current_pct=monthly_loss,
                    paper=self._config.ib.paper_trading,
                ) if self._telegram else None
            )

            return True

        return False

    # ------------------------------------------------------------------
    # Resumo diario
    # ------------------------------------------------------------------

    async def _check_daily_summary(self) -> None:
        """Envia o resumo diario as 23:00 UTC (uma vez por dia)."""
        now = datetime.now(tz=timezone.utc)

        if now.hour == _DAILY_SUMMARY_HOUR and not self._daily_summary_sent:
            logger.info("A gerar resumo diario...")

            summary = self._trade_logger.get_daily_summary()
            metrics = self._trade_logger.calculate_metrics()
            period_pnl = self._refresh_period_pnl(now=now)

            # Adicionar informacao de grids activas
            active_grids = self._grid_engine.get_active_grids()
            summary["num_active_grids"] = len(active_grids)

            # Guardar metricas
            self._trade_logger.save_metrics(self._build_metrics_payload(metrics))

            # Logar resumo
            logger.info(
                "RESUMO DIARIO — Data: %s | Trades: %d | Win rate: %.1f%% | "
                "P&L: %.2f | Drawdown: %.2f | Grids activas: %d",
                summary.get("date", "—"),
                summary.get("trades_count", 0),
                summary.get("win_rate", 0) * 100,
                summary.get("total_pnl", 0),
                summary.get("drawdown", 0),
                len(active_grids),
            )

            self._schedule_telegram(
                self._telegram.daily_report(
                    capital=self._capital,
                    daily_pnl=float(summary.get("total_pnl", 0.0) or 0.0),
                    n_trades=int(summary.get("trades_count", 0) or 0),
                    win_rate=float(summary.get("win_rate", 0.0) or 0.0) * 100,
                    open_grids=len(active_grids),
                    kill_switch_pct={
                        "daily": abs(
                            min(float(period_pnl.get("daily", 0.0) or 0.0) / self._capital, 0.0)
                        ) if self._capital > 0 else 0.0,
                        "weekly": abs(
                            min(float(period_pnl.get("weekly", 0.0) or 0.0) / self._capital, 0.0)
                        ) if self._capital > 0 else 0.0,
                        "monthly": abs(
                            min(float(period_pnl.get("monthly", 0.0) or 0.0) / self._capital, 0.0)
                        ) if self._capital > 0 else 0.0,
                    },
                    paper=self._config.ib.paper_trading,
                ) if self._telegram else None
            )

            self._daily_summary_sent = True

        elif now.hour != _DAILY_SUMMARY_HOUR:
            # Reiniciar a flag quando sair da hora do resumo
            self._daily_summary_sent = False

    # ------------------------------------------------------------------
    # Encerramento gracioso
    # ------------------------------------------------------------------

    async def _graceful_shutdown(self) -> None:
        """Executa o encerramento gracioso do bot - broker-aware."""
        self._is_shutting_down = True
        logger.info("A iniciar encerramento gracioso (broker-aware)...")

        # Impedir reconnect automatico durante shutdown
        connection = getattr(self, "_connection", None)
        if connection is not None and hasattr(connection, "set_shutting_down"):
            connection.set_shutting_down()

        # Cancelar polling Telegram
        telegram_poll_task = getattr(self, "_telegram_poll_task", None)
        if telegram_poll_task is not None and not telegram_poll_task.done():
            telegram_poll_task.cancel()
            try:
                await telegram_poll_task
            except asyncio.CancelledError:
                pass

        # Cancelar ordens abertas no broker
        order_manager = getattr(self, "_order_manager", None)
        if order_manager is None:
            logger.warning(
                "Shutdown: OrderManager indisponivel - cancelamento de ordens nao executado."
            )
        else:
            try:
                open_orders = await order_manager.get_open_orders()
                if open_orders:
                    logger.warning(
                        "Shutdown: %d ordem(ns) abertas detectadas - a tentar cancelar.",
                        len(open_orders),
                    )

                    async def _cancel_all() -> tuple[int, int]:
                        cancelled, failed = 0, 0
                        for order in open_orders:
                            order_id = order.get("orderId") or order.get("order_id")
                            if order_id:
                                success = await order_manager.cancel_order(int(order_id))
                                if success:
                                    cancelled += 1
                                else:
                                    failed += 1
                                    logger.error(
                                        "Shutdown: falha ao cancelar ordem %s.", order_id
                                    )
                        return cancelled, failed

                    cancelled, failed = await asyncio.wait_for(
                        _cancel_all(),
                        timeout=_SHUTDOWN_ORDER_CANCEL_TIMEOUT,
                    )
                    logger.info(
                        "Shutdown: %d ordem(ns) canceladas, %d por resolver.",
                        cancelled,
                        failed,
                    )
                else:
                    logger.info("Shutdown: sem ordens abertas - nada a cancelar.")
            except asyncio.TimeoutError:
                logger.error(
                    "Shutdown: timeout (%ds) ao cancelar ordens - "
                    "podem existir ordens pendentes no broker.",
                    _SHUTDOWN_ORDER_CANCEL_TIMEOUT,
                )
            except Exception as exc:  # noqa: BLE001
                logger.error("Shutdown: erro ao cancelar ordens: %s", exc)

        # Persistir estado final
        grid_engine = getattr(self, "_grid_engine", None)
        if grid_engine is None:
            logger.warning("Shutdown: GridEngine indisponivel - persistencia ignorada.")
        else:
            try:
                grid_engine.save_state()
                logger.info("Estado das grids persistido com sucesso.")
            except Exception as exc:  # noqa: BLE001
                logger.error("Erro ao persistir estado final: %s", exc)

        # Guardar metricas finais
        trade_logger = getattr(self, "_trade_logger", None)
        if trade_logger is None:
            logger.warning("Shutdown: TradeLogger indisponivel - metricas ignoradas.")
        else:
            try:
                metrics = trade_logger.calculate_metrics()
                trade_logger.save_metrics(self._build_metrics_payload(metrics))
                logger.info("Metricas finais guardadas com sucesso.")
            except Exception as exc:  # noqa: BLE001
                logger.error("Erro ao guardar metricas finais: %s", exc)

        # Desligar do IB (reconnect ja bloqueado)
        if connection is None:
            logger.warning("Shutdown: ligacao ao IB indisponivel.")
        else:
            try:
                await connection.disconnect()
                logger.info("Ligacao ao IB encerrada.")
            except Exception as exc:  # noqa: BLE001
                logger.error("Erro ao desligar do IB: %s", exc)

        # Notificacao Telegram
        telegram = getattr(self, "_telegram", None)
        self._schedule_telegram(
            telegram.bot_stopped(
                reason="shutdown normal",
                paper=self._config.ib.paper_trading,
            ) if telegram else None
        )
        if telegram is not None:
            await asyncio.sleep(1)

        # Remover ficheiro shutdown.request se existir
        try:
            if self._shutdown_request_path.exists():
                self._shutdown_request_path.unlink()
                logger.info("Ficheiro shutdown.request removido.")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Nao foi possivel remover shutdown.request: %s", exc)

        logger.info("Bot encerrado com sucesso.")
        return
        """

        if self._telegram_poll_task is not None and not self._telegram_poll_task.done():
            self._telegram_poll_task.cancel()
            try:
                await self._telegram_poll_task
            except asyncio.CancelledError:
                pass

        # Persistir estado final
        try:
            self._grid_engine.save_state()
            logger.info("Estado das grids persistido com sucesso.")
        except Exception as exc:  # noqa: BLE001
            logger.error("Erro ao persistir estado final: %s", exc)

        # Guardar metricas finais
        try:
            metrics = self._trade_logger.calculate_metrics()
            self._trade_logger.save_metrics(self._build_metrics_payload(metrics))
            logger.info("Metricas finais guardadas com sucesso.")
        except Exception as exc:  # noqa: BLE001
            logger.error("Erro ao guardar metricas finais: %s", exc)

        # Desligar do IB
        try:
            await self._connection.disconnect()
            logger.info("Ligacao ao IB encerrada.")
        except Exception as exc:  # noqa: BLE001
            logger.error("Erro ao desligar do IB: %s", exc)

        self._schedule_telegram(
            self._telegram.bot_stopped(
                reason="shutdown normal",
                paper=self._config.ib.paper_trading,
            ) if self._telegram else None
        )
        if self._telegram is not None:
            await asyncio.sleep(1)

        self._release_instance_lock()
        logger.info("Bot encerrado com sucesso.")


        """

# ---------------------------------------------------------------------------
# Ponto de entrada
# ---------------------------------------------------------------------------

def main() -> None:
    """Ponto de entrada do bot de trading autonomo."""
    # Carregar configuracao
    config = load_config()

    # Preparar estrutura de first-run
    ensure_data_dirs(config.data_dir)
    create_initial_files(config.data_dir)

    # Configurar logging
    setup_logging(config.log_level, log_dir=config.data_dir)

    logger.info("Configuracao carregada com sucesso.")
    logger.info(
        "IB: host=%s, port=%d, paper=%s, gateway=%s | "
        "Risco: rpl=%.1f%%, daily=%.1f%%, monthly=%.1f%% | "
        "Grids max: %d | Posicoes max: %d",
        config.ib.host,
        config.ib.port,
        config.ib.paper_trading,
        config.ib.use_gateway,
        config.risk.risk_per_level * 100,
        config.risk.daily_loss_limit * 100,
        config.risk.monthly_dd_limit * 100,
        config.risk.max_grids,
        config.risk.max_positions,
    )

    # Criar o bot
    bot = TradingBot(config)

    # Validacao de arranque — Risk of Ruin
    if not bot.validate_startup():
        logger.critical(
            "Validacao de arranque falhou. Bot NAO arrancou. "
            "Corrija os parametros de risco e tente novamente."
        )
        sys.exit(1)

    # Executar o loop assincrono
    try:
        asyncio.run(bot.run())
    except KeyboardInterrupt:
        logger.info("Interrupcao por teclado (Ctrl+C) — a encerrar.")
    except Exception as exc:
        logger.critical("Erro fatal nao tratado: %s", exc, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()

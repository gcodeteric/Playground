"""
Módulo de conexão ao Interactive Brokers e alimentação de dados de mercado.

Responsabilidades:
  - Ligação contínua ao IB Gateway/TWS com reconnect automático e backoff exponencial.
  - Obtenção de barras históricas (diárias) e dados em tempo real (preço, volume).
  - Criação e qualificação de contratos (Stock, Forex, Future, CFD).
  - Cálculo de indicadores técnicos (SMA, RSI, ATR, Bollinger Bands).
  - Cache de pedidos repetidos para respeitar os limites da API (máx. 50 msg/s).

Todas as operações de I/O são assíncronas (async/await).
Logs em português (PT-PT). Nomes de variáveis e funções em inglês.

Requer: Python 3.10+, ib_insync, pandas, numpy.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import time
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any

import numpy as np
import pandas as pd
import yfinance as yf

# Garante event loop activo antes de importar ib_insync em Python 3.14+
if sys.version_info >= (3, 10):
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())

from ib_insync import IB, CFD, Forex, Future, Stock, util

from src.ib_requests import (
    IBErrorPolicyDecision,
    IBRateLimiter,
    IBRequestExecutor,
    classify_ib_error,
)
from src.market_hours import get_asset_type, is_market_open

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

_MAX_RECONNECT_DELAY: int = 300          # segundos — tecto para backoff
_INITIAL_RECONNECT_DELAY: int = 5        # segundos — primeiro backoff
_CACHE_TTL_SECONDS: float = 5.0          # TTL das entradas na cache
_DAILY_RESTART_WAIT_SECONDS: int = 65
_RECONNECT_ALERT_INTERVAL_SECONDS: int = 600
_RECONNECT_ESCALATION_AFTER_SECONDS: int = 1800
_IB_PACING_ERROR_CODE: int = 162
_DATA_FEED_CIRCUIT_BREAKER_THRESHOLD: int = 3
_DATA_FEED_CIRCUIT_BREAKER_COOLDOWN_SECONDS: float = 30.0
_WARMUP_MIN_BARS: dict[str, int] = {
    "SMA200": 200,
    "SMA50": 50,
    "ATR14": 14,
}


# ---------------------------------------------------------------------------
# Cache simples com TTL
# ---------------------------------------------------------------------------

@dataclass
class _CacheEntry:
    """Entrada individual da cache com marca temporal."""
    value: Any
    timestamp: float


class _TTLCache:
    """
    Cache in-memory com TTL por chave.

    Utilizada para evitar pedidos repetidos à API do IB dentro de
    intervalos curtos (e.g., preço actual pedido várias vezes por segundo).
    """

    def __init__(self, ttl: float = _CACHE_TTL_SECONDS) -> None:
        self._ttl: float = ttl
        self._store: dict[str, _CacheEntry] = {}

    def get(self, key: str) -> Any | None:
        """Devolve o valor se a chave existir e não tiver expirado."""
        entry = self._store.get(key)
        if entry is None:
            return None
        if (time.monotonic() - entry.timestamp) > self._ttl:
            del self._store[key]
            return None
        return entry.value

    def set(self, key: str, value: Any) -> None:
        """Guarda um valor na cache com o timestamp actual."""
        self._store[key] = _CacheEntry(value=value, timestamp=time.monotonic())

    def invalidate(self, key: str) -> None:
        """Remove manualmente uma chave da cache."""
        self._store.pop(key, None)

    def clear(self) -> None:
        """Limpa toda a cache."""
        self._store.clear()

    def prune(self) -> None:
        """Remove todas as entradas expiradas."""
        now = time.monotonic()
        expired = [k for k, v in self._store.items() if (now - v.timestamp) > self._ttl]
        for k in expired:
            del self._store[k]


AlertCallback = Callable[[str], Awaitable[None]]
AsyncHook = Callable[[], Awaitable[None]]
ErrorHook = Callable[[IBErrorPolicyDecision], Awaitable[None] | None]


# ---------------------------------------------------------------------------
# IBConnection — ligação ao IB com reconnect automático
# ---------------------------------------------------------------------------

class IBConnection:
    """
    Gere a ligação ao IB Gateway/TWS via ib_insync.

    Funcionalidades:
      - Ligação inicial com retry e backoff exponencial (5 s, 10 s, 20 s, … máx. 300 s).
      - Callback de desconexão que dispara reconnect automático.
      - Método ``ensure_connected`` para verificação antes de cada operação.
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 0,
        client_id: int = 1,
        *,
        paper_trading: bool | None = None,
        use_gateway: bool | None = None,
    ) -> None:
        self.ib: IB = IB()
        self.host: str = host
        self.paper_trading: bool = (
            self._env_bool("PAPER_TRADING", True)
            if paper_trading is None else paper_trading
        )
        self.use_gateway: bool = (
            self._env_bool("USE_GATEWAY", False)
            if use_gateway is None else use_gateway
        )
        self.port: int = self.select_port(
            port=port,
            paper_trading=self.paper_trading,
            use_gateway=self.use_gateway,
        )
        self.client_id: int = client_id
        self.rate_limiter: IBRateLimiter = IBRateLimiter()
        self.request_executor: IBRequestExecutor = IBRequestExecutor(
            self.rate_limiter,
            logger,
        )

        self._connected: bool = False
        self._connection_state: str = "DISCONNECTED"
        self._connect_lock: asyncio.Lock = asyncio.Lock()
        self._reconnect_delay: int = _INITIAL_RECONNECT_DELAY
        self._reconnecting: bool = False
        self._shutting_down: bool = False
        self._reconnect_task: asyncio.Task[None] | None = None
        self._disconnect_callback: AsyncHook | None = None
        self._post_reconnect_callback: AsyncHook | None = None
        self._failed_reconnect_callback: AsyncHook | None = None
        self._error_callback: ErrorHook | None = None
        self._recent_errors: deque[tuple[float, int, str]] = deque(maxlen=100)
        self._recent_operational_events: deque[tuple[float, IBErrorPolicyDecision]] = deque(maxlen=100)
        self._market_data_type: int | None = None

        # Registar callback de desconexão
        self.ib.disconnectedEvent += self._on_disconnected
        self.ib.errorEvent += self._on_error

        logger.info(
            "Porta IB seleccionada: %d (paper=%s, gateway=%s).",
            self.port,
            self.paper_trading,
            self.use_gateway,
        )

    def set_alert_callback(self, callback: Any) -> None:
        """Actualiza o callback de alertas usado pelo executor partilhado."""
        self.request_executor.set_alert_callback(callback)

    def set_disconnect_callback(self, callback: AsyncHook | None) -> None:
        """Regista um callback para o momento da desconexao."""
        self._disconnect_callback = callback

    def set_post_reconnect_callback(self, callback: AsyncHook | None) -> None:
        """Regista um callback apos reconexao bem-sucedida."""
        self._post_reconnect_callback = callback

    def set_failed_reconnect_callback(self, callback: AsyncHook | None) -> None:
        """Regista um callback apos uma tentativa falhada de reconexao."""
        self._failed_reconnect_callback = callback

    def set_shutting_down(self) -> None:
        """Marca ligacao como em shutdown - impede reconexao automatica."""
        self._shutting_down = True
        if self._reconnect_task is not None and not self._reconnect_task.done():
            self._reconnect_task.cancel()
            logger.info("Tarefa de reconexao cancelada (shutdown em curso).")

    def set_error_callback(self, callback: ErrorHook | None) -> None:
        """Regista um callback para eventos operacionais derivados de erros IB."""
        self._error_callback = callback

    @staticmethod
    def _env_bool(key: str, default: bool) -> bool:
        value = os.getenv(key)
        if value is None or not value.strip():
            return default
        return value.strip().lower() in {"1", "true", "yes", "sim"}

    @classmethod
    def select_port(
        cls,
        *,
        port: int = 0,
        paper_trading: bool | None = None,
        use_gateway: bool | None = None,
    ) -> int:
        """Selecciona automaticamente a porta correcta do IB."""
        if port > 0:
            return port

        paper = cls._env_bool("PAPER_TRADING", True) if paper_trading is None else paper_trading
        gateway = cls._env_bool("USE_GATEWAY", False) if use_gateway is None else use_gateway
        if paper and gateway:
            return 4002
        if paper and not gateway:
            return 7497
        if not paper and gateway:
            return 4001
        return 7496

    # ----- ligação -----

    async def connect(
        self,
        *,
        max_attempts: int | None = None,
        initial_delay: int = _INITIAL_RECONNECT_DELAY,
        timeout: int = 30,
    ) -> bool:
        """
        Liga ao IB Gateway/TWS com retry e backoff exponencial.

        Tenta indefinidamente (o bot deve ser autónomo 24/7).
        Loga cada tentativa em português.

        Returns:
            True quando a ligação for estabelecida com sucesso.
        """
        async with self._connect_lock:
            if self.ib.isConnected():
                self._connected = True
                self._connection_state = "CONNECTED"
                return True

            delay = initial_delay
            attempt = 0

            while max_attempts is None or attempt < max_attempts:
                attempt += 1
                self._connection_state = "RECONNECTING" if self._reconnecting else "CONNECTING"
                try:
                    logger.info(
                        "A tentar ligar ao IB em %s:%d (client_id=%d, tentativa=%d, estado=%s)…",
                        self.host, self.port, self.client_id, attempt, self._connection_state,
                    )
                    await self.ib.connectAsync(
                        host=self.host,
                        port=self.port,
                        clientId=self.client_id,
                        timeout=timeout,
                    )
                    self._connected = True
                    self._connection_state = "CONNECTED"
                    # Activar delayed data por defeito para evitar erro 10089 sem subscrição paga.
                    self.ib.reqMarketDataType(3)
                    self._market_data_type = 3
                    self._reconnect_delay = _INITIAL_RECONNECT_DELAY  # reiniciar backoff
                    logger.info(
                        "Ligação ao IB estabelecida com sucesso (%s:%d).",
                        self.host, self.port,
                    )
                    logger.info("Tipo de dados de mercado IB configurado para delayed (3).")
                    return True

                except (
                    ConnectionRefusedError,
                    OSError,
                    asyncio.TimeoutError,
                    Exception,
                ) as exc:
                    self._connected = False
                    self._connection_state = "DISCONNECTED"
                    logger.warning(
                        "Falha ao ligar ao IB: %s. Próxima tentativa em %d s.",
                        exc, delay,
                    )
                    if max_attempts is not None and attempt >= max_attempts:
                        break
                    await asyncio.sleep(delay)
                    delay = min(delay * 2, _MAX_RECONNECT_DELAY)

            self._connected = False
            self._connection_state = "DISCONNECTED"
            return False

    async def disconnect(self) -> None:
        """Desliga do IB Gateway/TWS de forma limpa."""
        if self._reconnect_task is not None and not self._reconnect_task.done():
            self._reconnect_task.cancel()
            try:
                await self._reconnect_task
            except asyncio.CancelledError:
                pass
            self._reconnect_task = None

        if self.ib.isConnected():
            self.ib.disconnect()
            logger.info("Desligado do IB com sucesso.")

        self._connected = False
        self._connection_state = "DISCONNECTED"

    async def ensure_connected(self) -> bool:
        """
        Verifica se a ligação está activa; se não, tenta reconectar.

        Returns:
            True se a ligação estiver activa após verificação/reconexão.
        """
        if self.ib.isConnected():
            self._connected = True
            self._connection_state = "CONNECTED"
            return True

        logger.warning("Ligação ao IB perdida. A iniciar reconexão…")
        self._connected = False
        self._connection_state = "DISCONNECTED"
        return await self.connect(max_attempts=3)

    def recent_error_codes(self, since_seconds: float = 120.0) -> list[int]:
        """Lista codigos de erro recentes do IB numa janela temporal."""
        now = time.monotonic()
        return [code for ts, code, _ in self._recent_errors if (now - ts) <= since_seconds]

    def recent_errors(self, since_seconds: float = 120.0) -> list[tuple[int, str]]:
        """Lista erros recentes do IB numa janela temporal."""
        now = time.monotonic()
        return [(code, message) for ts, code, message in self._recent_errors if (now - ts) <= since_seconds]

    def operational_events_since(self, start_monotonic: float) -> list[IBErrorPolicyDecision]:
        """Devolve eventos operacionais ocorridos desde um instante monotónico."""
        return [
            decision
            for ts, decision in self._recent_operational_events
            if ts >= start_monotonic
        ]

    def _on_error(
        self,
        req_id: int,
        error_code: int,
        error_string: str,
        contract: Any,
    ) -> None:
        """Regista os erros recentes do IB para preflight e pacing."""
        del req_id, contract
        occurred_at = time.monotonic()
        self._recent_errors.append((occurred_at, error_code, error_string))

        decision = classify_ib_error(error_code, error_string)
        if decision is not None:
            self._recent_operational_events.append((occurred_at, decision))
            if decision.action == "entry_halt":
                self._connected = False
                self._connection_state = "DISCONNECTED"
            elif decision.action == "clear_connection_halt" and self.ib.isConnected():
                self._connected = True
                self._connection_state = "CONNECTED"

            log_fn = {
                "critical": logger.error,
                "error": logger.error,
                "warning": logger.warning,
                "info": logger.info,
            }.get(decision.severity, logger.warning)
            log_fn(
                "Evento operacional IB [%s/%s] codigo=%d: %s",
                decision.scope,
                decision.action,
                decision.error_code,
                decision.message,
            )
            self._dispatch_error_callback(decision)
            return

        # Codigos informativos (centro de dados OK/lost/inactive) — nivel DEBUG
        if error_code in {2103, 2104, 2105, 2106, 2107, 2108, 2119, 2157, 2158}:
            logger.debug("Codigo IB %d: %s", error_code, error_string)
        elif error_code in {1100, 1102, 354, 10197, _IB_PACING_ERROR_CODE}:
            logger.warning("Codigo IB %d: %s", error_code, error_string)

    def _dispatch_error_callback(self, decision: IBErrorPolicyDecision) -> None:
        """Encaminha eventos operacionais para o callback registado."""
        if self._error_callback is None:
            return
        try:
            result = self._error_callback(decision)
            if asyncio.iscoroutine(result):
                loop = asyncio.get_running_loop()
                loop.create_task(result)
        except RuntimeError:
            logger.debug(
                "Sem event loop activo para callback de erro IB (codigo=%d).",
                decision.error_code,
            )

    def _on_disconnected(self) -> None:
        """
        Callback invocado pelo ib_insync quando a ligação é perdida.

        Marca a ligação como inactiva e inicia o processo de reconexão
        assíncrono (se não estiver já em curso).
        """
        self._connected = False
        self._connection_state = "DISCONNECTED"
        logger.warning("Desconexão do IB detectada pelo callback.")

        if self._reconnecting:
            return
        if self._shutting_down:
            logger.info("Reconexao automatica bloqueada - shutdown em curso.")
            return

        # Agendar reconexão assíncrona
        try:
            loop = asyncio.get_running_loop()
            if self._disconnect_callback is not None:
                loop.create_task(self._disconnect_callback())
            self._reconnect_task = loop.create_task(self._auto_reconnect())
        except RuntimeError:
            # Não há event loop a correr — será reconectado na próxima chamada
            logger.warning(
                "Sem event loop activo para reconexão automática. "
                "A reconexão será tentada na próxima operação."
            )

    async def _auto_reconnect(self) -> None:
        """Tarefa interna de reconexão automática com protecção contra duplicação."""
        if self._reconnecting:
            return
        self._reconnecting = True
        self._connection_state = "RECONNECTING"
        try:
            logger.info(
                "A iniciar reconexão automática ao IB com espera inicial de %d s…",
                _DAILY_RESTART_WAIT_SECONDS,
            )
            await self.request_executor._send_alert("⚠️ IB desconectado. A reconectar...")
            await asyncio.sleep(_DAILY_RESTART_WAIT_SECONDS)

            started_at = time.monotonic()
            last_escalation = started_at
            delay = _DAILY_RESTART_WAIT_SECONDS

            while True:
                connected = await self.connect(
                    max_attempts=1,
                    initial_delay=delay,
                )
                if connected:
                    if self._post_reconnect_callback is not None:
                        await self._post_reconnect_callback()
                    break

                if self._failed_reconnect_callback is not None:
                    await self._failed_reconnect_callback()

                now = time.monotonic()
                if (
                    (now - started_at) >= _RECONNECT_ESCALATION_AFTER_SECONDS
                    and (now - last_escalation) >= _RECONNECT_ALERT_INTERVAL_SECONDS
                ):
                    await self.request_executor._send_alert(
                        "❌ IB continua desligado ha mais de 30 minutos. A tentar novamente."
                    )
                    last_escalation = now

                delay = min(delay * 2, _MAX_RECONNECT_DELAY)
                logger.warning(
                    "Reconexão ao IB falhou. Nova tentativa em %d s.",
                    delay,
                )
                await asyncio.sleep(delay)
        finally:
            self._reconnecting = False
            if not self.ib.isConnected():
                self._connection_state = "DISCONNECTED"

    @property
    def is_connected(self) -> bool:
        """Indica se a ligação está activa."""
        return self._connected and self.ib.isConnected()


# ---------------------------------------------------------------------------
# Funções auxiliares de indicadores técnicos
# ---------------------------------------------------------------------------
# Estas funções são utilizadas por DataFeed.get_market_data().
# Quando o módulo signal_engine estiver disponível, podem ser importadas
# de lá; aqui ficam como implementação canónica para que data_feed.py
# funcione de forma autónoma.
# ---------------------------------------------------------------------------

def compute_sma(series: pd.Series, period: int) -> pd.Series:
    """Média Móvel Simples (SMA)."""
    return series.rolling(window=period, min_periods=period).mean()


def compute_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """
    Relative Strength Index (RSI) usando média exponencial (Wilder).

    Período por defeito: 14.
    """
    delta = series.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    avg_gain = gain.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100.0 - (100.0 / (1.0 + rs))
    return rsi


def compute_atr(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 14,
) -> pd.Series:
    """
    Average True Range (ATR) usando média exponencial (Wilder).

    Período por defeito: 14.
    """
    prev_close = close.shift(1)
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    return atr


def compute_bollinger_bands(
    series: pd.Series,
    period: int = 20,
    num_std: float = 2.0,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """
    Bollinger Bands.

    Retorna: (upper, middle, lower).
    Período por defeito: 20, desvio-padrão: 2σ.
    """
    middle = series.rolling(window=period, min_periods=period).mean()
    std = series.rolling(window=period, min_periods=period).std()
    upper = middle + num_std * std
    lower = middle - num_std * std
    return upper, middle, lower


def get_warmup_missing_rules(bars_df: pd.DataFrame) -> list[str]:
    """Devolve a lista de indicadores ainda sem barras suficientes."""
    bars_count = len(bars_df)
    return [
        f"{name}>={minimum}"
        for name, minimum in _WARMUP_MIN_BARS.items()
        if bars_count < minimum
    ]


def validate_warmup(bars_df: pd.DataFrame, symbol: str) -> bool:
    """Valida o warm-up minimo antes de calcular indicadores criticos."""
    missing_rules = get_warmup_missing_rules(bars_df)
    if missing_rules:
        logger.warning(
            "Warm-up insuficiente para %s: %s",
            symbol,
            ", ".join(missing_rules),
        )
        return False
    return True


# ---------------------------------------------------------------------------
# DataFeed — obtenção de dados de mercado e cálculo de indicadores
# ---------------------------------------------------------------------------

class DataFeed:
    """
    Alimentação de dados de mercado via IB (ib_insync).

    Fornece:
      - Barras históricas (diárias) como DataFrame pandas.
      - Preço e volume actuais.
      - Criação e qualificação de contratos.
      - Cálculo de todos os indicadores técnicos necessários.
      - Cache por TTL e rate limiting integrados.
    """

    _YF_SYMBOL_MAP: dict[str, str] = {
        # Forex
        "EUR": "EURUSD=X",
        "GBP": "GBPUSD=X",
        "JPY": "JPY=X",
        "CHF": "CHF=X",
        "AUD": "AUDUSD=X",
        "NZD": "NZDUSD=X",
        "CAD": "USDCAD=X",
        "EURUSD": "EURUSD=X",
        "GBPUSD": "GBPUSD=X",
        "USDJPY": "JPY=X",
        "USDCHF": "CHF=X",
        "AUDUSD": "AUDUSD=X",
        "NZDUSD": "NZDUSD=X",
        "USDCAD": "USDCAD=X",
        # Futuros
        "ES": "ES=F",
        "MES": "ES=F",
        "NQ": "NQ=F",
        "MNQ": "NQ=F",
        "CL": "CL=F",
        "GC": "GC=F",
        "MGC": "GC=F",
        "ZN": "ZN=F",
        "ZB": "ZB=F",
        "SI": "SI=F",
        # Índices
        "VIX": "^VIX",
        "^VIX": "^VIX",
        "SPX": "^GSPC",
        "NDX": "^NDX",
        "DJI": "^DJI",
    }

    def __init__(self, connection: IBConnection) -> None:
        self._conn: IBConnection = connection
        self._cache: _TTLCache = _TTLCache(ttl=_CACHE_TTL_SECONDS)
        self._rate_limiter: IBRateLimiter = connection.rate_limiter
        self._request_executor: IBRequestExecutor = connection.request_executor
        # Cache de longa duração para barras históricas (actualizadas menos vezes)
        self._bars_cache: _TTLCache = _TTLCache(ttl=60.0)
        self._market_data_locks: dict[str, asyncio.Lock] = {}
        self._data_feed_failure_counts: dict[str, int] = {}
        self._data_feed_circuit_open_until: dict[str, float | None] = {}

    # ---- propriedade de conveniência ----

    @property
    def ib(self) -> IB:
        """Acesso directo à instância IB da conexão."""
        return self._conn.ib

    def _contract_market_symbol(
        self,
        contract: Stock | Forex | Future | CFD,
    ) -> str:
        """Extrai um símbolo utilizável no fallback de mercado."""
        if isinstance(contract, Forex):
            currency = getattr(contract, "currency", "") or ""
            if currency:
                return f"{contract.symbol}{currency}"
        return str(contract.symbol)

    @staticmethod
    def _contract_cache_key(contract: Stock | Forex | Future | CFD) -> str:
        """Constrói uma fingerprint estável para cache por contrato."""
        sec_type = (
            getattr(contract, "secType", None)
            or type(contract).__name__.upper()
        )
        symbol = getattr(contract, "localSymbol", None) or getattr(contract, "symbol", "")
        exchange = (
            getattr(contract, "primaryExchange", None)
            or getattr(contract, "exchange", None)
            or ""
        )
        currency = getattr(contract, "currency", None) or ""
        expiry = getattr(contract, "lastTradeDateOrContractMonth", None) or ""
        return f"{sec_type}:{symbol}:{exchange}:{currency}:{expiry}"

    def _is_market_open_for_contract(
        self,
        contract: Stock | Forex | Future | CFD,
    ) -> bool:
        """Indica se a sessão do mercado está aberta para o contrato."""
        try:
            return is_market_open(
                self._contract_market_symbol(contract),
                asset_type=get_asset_type(contract),
            )
        except Exception:
            return False

    def _is_data_feed_circuit_open(self, operation_name: str) -> bool:
        """Verifica se o circuit breaker do fluxo está activo."""
        open_until = self._data_feed_circuit_open_until.get(operation_name)
        if open_until is None:
            return False
        if time.monotonic() >= open_until:
            self._data_feed_failure_counts[operation_name] = 0
            self._data_feed_circuit_open_until.pop(operation_name, None)
            return False
        return True

    def _record_data_feed_success(self, operation_name: str) -> None:
        """Reinicia o estado do circuit breaker após sucesso real."""
        self._data_feed_failure_counts[operation_name] = 0
        self._data_feed_circuit_open_until.pop(operation_name, None)

    def _record_data_feed_failure(
        self,
        operation_name: str,
        contract: Stock | Forex | Future | CFD,
    ) -> None:
        """Conta uma falha real apenas durante mercado aberto."""
        if not self._is_market_open_for_contract(contract):
            self._data_feed_failure_counts[operation_name] = 0
            return

        failures = self._data_feed_failure_counts.get(operation_name, 0) + 1
        self._data_feed_failure_counts[operation_name] = failures
        if failures >= _DATA_FEED_CIRCUIT_BREAKER_THRESHOLD:
            self._data_feed_circuit_open_until[operation_name] = (
                time.monotonic() + _DATA_FEED_CIRCUIT_BREAKER_COOLDOWN_SECONDS
            )

    @staticmethod
    def _request_event_codes(
        request_events: list[IBErrorPolicyDecision],
    ) -> set[int]:
        """Extrai códigos de erro operacionais relevantes do pedido actual."""
        return {decision.error_code for decision in request_events}

    def _with_price_quality(
        self,
        snapshot: dict[str, Any],
        *,
        request_events: list[IBErrorPolicyDecision] | None = None,
    ) -> dict[str, Any]:
        """Anexa qualidade de dados para separar análise degradada de execução segura."""
        request_events = request_events or []
        codes = self._request_event_codes(request_events)
        result = dict(snapshot)
        source = result.get("source")
        snapshot_market_data_type = result.pop("_market_data_type", None)

        quality = "unavailable"
        execution_ready = False
        if source == "yfinance":
            quality = "yfinance_fallback"
        elif source == "close":
            quality = "ib_close_only"
        elif 10089 in codes:
            quality = "ib_subscription_limited"
        elif 10167 in codes:
            quality = "ib_delayed_subscription"
        elif 354 in codes:
            quality = "ib_permission_denied"
        elif 10197 in codes:
            quality = "ib_out_of_session"
        elif _IB_PACING_ERROR_CODE in codes:
            quality = "ib_pacing_limited"
        elif snapshot_market_data_type in {3, 4} and source in {"last", "mid", "mark"}:
            quality = "ib_delayed_mode"
        elif source in {"last", "mid", "mark"}:
            quality = "ib_reliable"
            execution_ready = True

        result["quality"] = quality
        result["execution_ready"] = execution_ready
        return result

    @staticmethod
    def _should_abort_price_request(
        request_events: list[IBErrorPolicyDecision],
    ) -> bool:
        """Interrompe cedo pedidos sem retry útil para evitar timeouts artificiais."""
        return any(decision.action == "symbol_skip_no_retry" for decision in request_events)

    @staticmethod
    def _should_abort_volume_request(
        request_events: list[IBErrorPolicyDecision],
    ) -> bool:
        """Evita aguardar volume IB quando o broker já sinalizou degradação conhecida."""
        codes = {decision.error_code for decision in request_events}
        return bool(codes & {354, 10089, 10167, 10197})

    def _yf_symbol(self, symbol: str) -> str:
        """Converte símbolo IB para símbolo Yahoo Finance."""
        symbol_map = getattr(self, "_yf_symbol_map", self._YF_SYMBOL_MAP)
        return symbol_map.get(symbol.upper(), symbol.upper())

    async def get_price_yfinance(self, symbol: str) -> float | None:
        """Fallback assíncrono: preço actual via yfinance."""
        cache_key = f"yfinance_price:{symbol.upper()}"
        asof_cache_key = f"{cache_key}:asof"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return float(cached)

        try:
            yf_symbol = self._yf_symbol(symbol)
            loop = asyncio.get_running_loop()
            df = await asyncio.wait_for(
                loop.run_in_executor(
                    None,
                    lambda: yf.download(yf_symbol, period="5d", progress=False),
                ),
                timeout=5.0,
            )
            close_series = (
                df["Close"].dropna()
                if not df.empty and "Close" in df
                else pd.Series(dtype=float)
            )
            price = _extract_last_numeric_value(close_series)
            if price is not None:
                self._cache.set(cache_key, price)
                self._cache.set(asof_cache_key, str(close_series.index[-1]))
            return price
        except asyncio.TimeoutError:
            logger.warning("yfinance timeout %s", symbol)
            return None
        except Exception as exc:  # noqa: BLE001
            logger.warning("yfinance erro %s: %s", symbol, exc)
            return None

    async def get_volume_yfinance(self, symbol: str) -> float | None:
        """Fallback assíncrono: volume actual via yfinance."""
        cache_key = f"yfinance_volume:{symbol.upper()}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return float(cached)

        try:
            yf_symbol = self._yf_symbol(symbol)
            loop = asyncio.get_running_loop()
            df = await asyncio.wait_for(
                loop.run_in_executor(
                    None,
                    lambda: yf.download(yf_symbol, period="5d", progress=False),
                ),
                timeout=5.0,
            )
            volume = (
                _extract_last_numeric_value(df["Volume"].dropna())
                if not df.empty and "Volume" in df
                else None
            )
            if volume is not None:
                self._cache.set(cache_key, volume)
            return volume
        except asyncio.TimeoutError:
            logger.warning("yfinance timeout %s", symbol)
            return None
        except Exception as exc:  # noqa: BLE001
            logger.warning("yfinance erro %s: %s", symbol, exc)
            return None

    # ----------------------------------------------------------------
    # Barras históricas
    # ----------------------------------------------------------------

    async def get_historical_bars(
        self,
        contract: Stock | Forex | Future | CFD,
        duration: str = "1 Y",
        bar_size: str = "1 day",
        what_to_show: str = "TRADES",
        use_rth: bool = True,
    ) -> pd.DataFrame:
        """
        Obtém barras históricas do IB e devolve um DataFrame.

        Colunas do DataFrame: date, open, high, low, close, volume.

        Args:
            contract: Contrato IB (Stock, Forex, Future, CFD).
            duration: Janela temporal (e.g., '1 Y', '6 M', '30 D').
            bar_size: Tamanho de cada barra (e.g., '1 day', '1 hour').
            what_to_show: Tipo de dados ('TRADES', 'MIDPOINT', 'BID', 'ASK').
            use_rth: Se True, apenas horas regulares de mercado.

        Returns:
            pd.DataFrame com colunas [date, open, high, low, close, volume].
            DataFrame vazio se não houver dados.
        """
        # Chave de cache
        contract_key = self._contract_cache_key(contract)
        cache_key = (
            f"bars:{contract_key}:{duration}:{bar_size}:{what_to_show}:{int(use_rth)}"
        )
        cached = self._bars_cache.get(cache_key)
        if cached is not None:
            logger.debug("Cache hit para barras históricas: %s", cache_key)
            return cached

        await self._conn.ensure_connected()

        async def _request_bars() -> pd.DataFrame:
            show_type = what_to_show
            logger.info(
                "A obter barras históricas: %s | duração=%s | tamanho=%s",
                contract.symbol, duration, bar_size,
            )

            # Forex utiliza MIDPOINT em vez de TRADES
            if isinstance(contract, Forex) and show_type == "TRADES":
                show_type = "MIDPOINT"

            # CFD utiliza MIDPOINT em vez de TRADES
            if isinstance(contract, CFD) and show_type == "TRADES":
                show_type = "MIDPOINT"

            bars = await self.ib.reqHistoricalDataAsync(
                contract,
                endDateTime="",
                durationStr=duration,
                barSizeSetting=bar_size,
                whatToShow=show_type,
                useRTH=use_rth,
                formatDate=1,
                timeout=60,
            )

            if not bars:
                logger.warning(
                    "Sem barras históricas devolvidas para %s.", contract.symbol
                )
                return pd.DataFrame(
                    columns=["date", "open", "high", "low", "close", "volume"]
                )

            # Converter para DataFrame
            df = util.df(bars)

            # Normalizar nomes de colunas
            rename_map: dict[str, str] = {}
            for col in df.columns:
                lower = col.lower()
                if lower in ("date", "open", "high", "low", "close", "volume"):
                    rename_map[col] = lower
            df = df.rename(columns=rename_map)

            # Garantir colunas mínimas
            required_cols = ["date", "open", "high", "low", "close", "volume"]
            for col in required_cols:
                if col not in df.columns:
                    if col == "volume":
                        df[col] = 0.0
                    elif col == "date":
                        df[col] = pd.NaT
                    else:
                        df[col] = np.nan

            df = df[required_cols].copy()

            # Converter tipos
            for col in ("open", "high", "low", "close", "volume"):
                df[col] = pd.to_numeric(df[col], errors="coerce")

            df = df.sort_values("date").reset_index(drop=True)

            logger.info(
                "Barras obtidas com sucesso: %s — %d barras (de %s a %s).",
                contract.symbol, len(df),
                df["date"].iloc[0] if len(df) > 0 else "N/A",
                df["date"].iloc[-1] if len(df) > 0 else "N/A",
            )

            # Guardar na cache
            self._bars_cache.set(cache_key, df)
            return df

        try:
            return await self._request_executor.run(
                "historical_bars",
                cache_key,
                _request_bars,
                request_cost=1,
            )
        except Exception as exc:
            logger.error(
                "Erro ao obter barras históricas para %s: %s",
                contract.symbol, exc,
            )
            return pd.DataFrame(
                columns=["date", "open", "high", "low", "close", "volume"]
            )

    # ----------------------------------------------------------------
    # Preço e volume actuais
    # ----------------------------------------------------------------

    async def get_current_price_details(
        self,
        contract: Stock | Forex | Future | CFD,
    ) -> dict[str, Any]:
        """
        Obtém o preço actual com metadados de fonte/frescura.

        Returns:
            ``{"price": float|None, "source": str|None, "fresh": bool, "volume": float|None,
            "quality": str, "execution_ready": bool}``
        """
        contract_key = self._contract_cache_key(contract)
        cache_key = f"price_snapshot:{contract_key}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return self._with_price_quality(dict(cached))
        if self._is_data_feed_circuit_open("current_price"):
            return self._with_price_quality({"price": None, "source": None, "fresh": False})

        symbol = self._contract_market_symbol(contract)
        connected = await self._conn.ensure_connected()
        if not connected:
            price = await self.get_price_yfinance(symbol)
            if price is not None:
                yfinance_asof = self._cache.get(f"yfinance_price:{symbol.upper()}:asof")
                snapshot = self._with_price_quality({
                    "price": float(price),
                    "source": "yfinance",
                    "fresh": _is_yfinance_quote_fresh(yfinance_asof),
                })
                logger.info(
                    "Preço IB indisponível — yfinance fallback: %s = %.4f",
                    symbol,
                    price,
                )
                self._cache.set(cache_key, snapshot)
                self._record_data_feed_success("current_price")
                return snapshot
            self._record_data_feed_failure("current_price", contract)
            return self._with_price_quality({"price": None, "source": None, "fresh": False})

        async def _request_price() -> dict[str, Any]:
            logger.debug("A obter preço actual de %s…", contract.symbol)
            late_snapshot: dict[str, Any] | None = None
            lock = self._market_data_locks.setdefault(contract_key, asyncio.Lock())

            async with lock:
                request_started_at = time.monotonic()
                ticker = self.ib.reqMktData(contract, snapshot=True)
                try:
                    deadline = time.monotonic() + 10.0
                    while time.monotonic() < deadline:
                        await asyncio.sleep(0.1)
                        request_events = self._conn.operational_events_since(request_started_at)
                        snapshot = _build_price_snapshot_from_ticker(ticker)
                        if snapshot is not None:
                            snapshot = self._with_price_quality(
                                snapshot,
                                request_events=request_events,
                            )
                            self._cache.set(cache_key, snapshot)
                            logger.debug(
                                "Preço de %s: %.4f (%s | quality=%s | execution_ready=%s).",
                                contract.symbol,
                                float(snapshot["price"]),
                                snapshot["source"],
                                snapshot["quality"],
                                snapshot["execution_ready"],
                            )
                            return snapshot
                        if self._should_abort_price_request(request_events):
                            break

                    late_snapshot = _build_price_snapshot_from_ticker(ticker)
                    if late_snapshot is not None:
                        late_snapshot = self._with_price_quality(
                            late_snapshot,
                            request_events=self._conn.operational_events_since(request_started_at),
                        )
                finally:
                    try:
                        self.ib.cancelMktData(contract)
                    except Exception:
                        pass

            snapshot = late_snapshot
            if snapshot is not None:
                self._cache.set(cache_key, snapshot)
                logger.info(
                    "Preço IB tardio mas utilizável para %s — a usar %s %.4f (quality=%s, execution_ready=%s).",
                    contract.symbol,
                    snapshot["source"],
                    float(snapshot["price"]),
                    snapshot["quality"],
                    snapshot["execution_ready"],
                )
                self._record_data_feed_success("current_price")
                return snapshot
            logger.warning("Timeout ao obter preço de %s.", contract.symbol)
            price = await self.get_price_yfinance(symbol)
            if price is not None:
                yfinance_asof = self._cache.get(f"yfinance_price:{symbol.upper()}:asof")
                snapshot = self._with_price_quality({
                    "price": float(price),
                    "source": "yfinance",
                    "fresh": _is_yfinance_quote_fresh(yfinance_asof),
                    "volume": None,
                })
                logger.info(
                    "Preço IB indisponível — yfinance fallback: %s = %.4f",
                    symbol,
                    price,
                )
                self._cache.set(cache_key, snapshot)
                self._record_data_feed_success("current_price")
                return snapshot
            self._record_data_feed_failure("current_price", contract)
            return self._with_price_quality({"price": None, "source": None, "fresh": False})

        try:
            snapshot = await self._request_executor.run(
                "current_price",
                cache_key,
                _request_price,
                request_cost=2,
            )
            if snapshot.get("price") is not None:
                self._record_data_feed_success("current_price")
            return snapshot
        except Exception as exc:
            logger.error("Erro ao obter preço de %s: %s", contract.symbol, exc)
            try:
                self.ib.cancelMktData(contract)
            except Exception:
                pass
            price = await self.get_price_yfinance(symbol)
            if price is not None:
                yfinance_asof = self._cache.get(f"yfinance_price:{symbol.upper()}:asof")
                snapshot = self._with_price_quality({
                    "price": float(price),
                    "source": "yfinance",
                    "fresh": _is_yfinance_quote_fresh(yfinance_asof),
                    "volume": None,
                })
                logger.info(
                    "Preço IB indisponível — yfinance fallback: %s = %.4f",
                    symbol,
                    price,
                )
                self._cache.set(cache_key, snapshot)
                self._record_data_feed_success("current_price")
                return snapshot
            self._record_data_feed_failure("current_price", contract)
            return self._with_price_quality({"price": None, "source": None, "fresh": False})

    async def get_current_price(
        self,
        contract: Stock | Forex | Future | CFD,
    ) -> float | None:
        """Obtém o preço actual em formato simples para compatibilidade."""
        details = await self.get_current_price_details(contract)
        price = details.get("price")
        return float(price) if price is not None else None

    async def get_current_price_live(
        self,
        contract: Stock | Forex | Future | CFD,
    ) -> float | None:
        """
        Obtém o snapshot actual do mercado.

        Este alias torna explícita a separação entre preço live e
        ``last_close`` diário usado nos indicadores.
        """
        return await self.get_current_price(contract)

    async def get_current_volume(
        self,
        contract: Stock | Forex | Future | CFD,
    ) -> float | None:
        """
        Obtém o volume actual (diário) de um contrato.

        Returns:
            Volume como float, ou None se indisponível.
        """
        contract_key = self._contract_cache_key(contract)
        cache_key = f"volume:{contract_key}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        price_snapshot = self._cache.get(f"price_snapshot:{contract_key}")
        if isinstance(price_snapshot, dict):
            cached_volume = price_snapshot.get("volume")
            if cached_volume is not None:
                volume = float(cached_volume)
                self._cache.set(cache_key, volume)
                logger.debug(
                    "Volume reutilizado do snapshot de preço para %s: %.0f.",
                    contract.symbol,
                    volume,
                )
                return volume
        if self._is_data_feed_circuit_open("current_volume"):
            return None

        symbol = self._contract_market_symbol(contract)
        connected = await self._conn.ensure_connected()
        if not connected:
            volume = await self.get_volume_yfinance(symbol)
            if volume is not None:
                logger.info(
                    "Volume IB indisponível — yfinance fallback: %s = %.0f",
                    symbol,
                    volume,
                )
                self._cache.set(cache_key, volume)
                self._record_data_feed_success("current_volume")
            else:
                self._record_data_feed_failure("current_volume", contract)
            return volume

        async def _request_volume() -> float | None:
            logger.debug("A obter volume actual de %s…", contract.symbol)
            lock = self._market_data_locks.setdefault(contract_key, asyncio.Lock())

            async with lock:
                request_started_at = time.monotonic()
                ticker = self.ib.reqMktData(contract, snapshot=True)
                try:
                    deadline = time.monotonic() + 10.0
                    while time.monotonic() < deadline:
                        await asyncio.sleep(0.1)
                        request_events = self._conn.operational_events_since(request_started_at)
                        if _valid_price(ticker.volume):
                            volume = float(ticker.volume)
                            self._cache.set(cache_key, volume)
                            logger.debug("Volume de %s: %.0f.", contract.symbol, volume)
                            return volume
                        if self._should_abort_volume_request(request_events):
                            break
                finally:
                    try:
                        self.ib.cancelMktData(contract)
                    except Exception:
                        pass

            logger.warning("Timeout ao obter volume de %s.", contract.symbol)
            volume = await self.get_volume_yfinance(symbol)
            if volume is not None:
                logger.info(
                    "Volume IB indisponível — yfinance fallback: %s = %.0f",
                    symbol,
                    volume,
                )
                self._cache.set(cache_key, volume)
                self._record_data_feed_success("current_volume")
            else:
                self._record_data_feed_failure("current_volume", contract)
            return volume

        try:
            volume = await self._request_executor.run(
                "current_volume",
                cache_key,
                _request_volume,
                request_cost=2,
            )
            if volume is not None:
                self._record_data_feed_success("current_volume")
            return volume
        except Exception as exc:
            logger.error("Erro ao obter volume de %s: %s", contract.symbol, exc)
            try:
                self.ib.cancelMktData(contract)
            except Exception:
                pass
            volume = await self.get_volume_yfinance(symbol)
            if volume is not None:
                logger.info(
                    "Volume IB indisponível — yfinance fallback: %s = %.0f",
                    symbol,
                    volume,
                )
                self._cache.set(cache_key, volume)
                self._record_data_feed_success("current_volume")
            else:
                self._record_data_feed_failure("current_volume", contract)
            return volume

    # ----------------------------------------------------------------
    # Criação de contratos
    # ----------------------------------------------------------------

    def create_stock_contract(
        self,
        symbol: str,
        exchange: str = "SMART",
        currency: str = "USD",
    ) -> Stock:
        """
        Cria um contrato de acção (Stock).

        Args:
            symbol: Símbolo do activo (e.g., 'AAPL', 'MSFT').
            exchange: Bolsa (por defeito SMART para roteamento inteligente).
            currency: Moeda de denominação.

        Returns:
            Objecto Stock do ib_insync.
        """
        logger.debug("A criar contrato Stock: %s (%s/%s)", symbol, exchange, currency)
        return Stock(symbol, exchange, currency)

    def create_forex_contract(self, pair: str) -> Forex:
        """
        Cria um contrato Forex.

        Args:
            pair: Par de moedas (e.g., 'EURUSD', 'GBPUSD').

        Returns:
            Objecto Forex do ib_insync.
        """
        logger.debug("A criar contrato Forex: %s", pair)
        return Forex(pair)

    def create_futures_contract(
        self,
        symbol: str,
        exchange: str,
        expiry: str = "",
    ) -> Future:
        """
        Cria um contrato de futuros (Future).

        Args:
            symbol: Símbolo do futuro (e.g., 'MES', 'MNQ', 'MYM').
            exchange: Bolsa (e.g., 'CME', 'CBOT').
            expiry: Data de expiração no formato YYYYMM ou YYYYMMDD.
                    Se vazio, o ib_insync tenta resolver o contrato contínuo.

        Returns:
            Objecto Future do ib_insync.
        """
        logger.debug(
            "A criar contrato Future: %s (%s) expiry=%s",
            symbol, exchange, expiry or "contínuo",
        )
        if expiry:
            return Future(symbol, expiry, exchange)
        return Future(symbol=symbol, exchange=exchange)

    def create_cfd_contract(self, symbol: str) -> CFD:
        """
        Cria um contrato CFD.

        Args:
            symbol: Símbolo do CFD (e.g., 'IBDE30', 'IBUS500').

        Returns:
            Objecto CFD do ib_insync.
        """
        logger.debug("A criar contrato CFD: %s", symbol)
        return CFD(symbol)

    # ----------------------------------------------------------------
    # Qualificação de contrato
    # ----------------------------------------------------------------

    async def qualify_contract(
        self,
        contract: Stock | Forex | Future | CFD,
    ) -> bool:
        """
        Qualifica um contrato junto do IB (preenche conId, exchange, etc.).

        A qualificação é obrigatória antes de submeter ordens ou pedir
        dados de mercado de forma fiável.

        Returns:
            True se o contrato foi qualificado com sucesso.
        """
        await self._conn.ensure_connected()

        async def _qualify() -> bool:
            logger.info("A qualificar contrato: %s…", contract.symbol)
            qualified = await self.ib.qualifyContractsAsync(contract)

            if qualified and len(qualified) > 0 and qualified[0].conId > 0:
                logger.info(
                    "Contrato qualificado: %s (conId=%d, exchange=%s).",
                    contract.symbol, contract.conId, contract.exchange,
                )
                return True

            logger.warning(
                "Não foi possível qualificar o contrato: %s.", contract.symbol
            )
            return False

        try:
            return await self._request_executor.run(
                "qualify_contract",
                f"qualify:{contract.symbol}:{contract.exchange}",
                _qualify,
                request_cost=1,
            )
        except Exception as exc:
            logger.error(
                "Erro ao qualificar contrato %s: %s", contract.symbol, exc
            )
            return False

    # ----------------------------------------------------------------
    # Dados de mercado com indicadores
    # ----------------------------------------------------------------

    def get_market_data(
        self,
        contract: Stock | Forex | Future | CFD,
        bars_df: pd.DataFrame,
        *,
        current_price: float | None = None,
    ) -> dict[str, float | None]:
        """
        Calcula e devolve todos os indicadores técnicos a partir de barras históricas.

        Indicadores calculados:
          - sma25        — SMA de 25 períodos (indicador central Kotegawa)
          - sma50        — SMA de 50 períodos (filtro de tendência)
          - sma200       — SMA de 200 períodos (filtro de tendência macro)
          - rsi14        — RSI de 14 períodos
          - atr14        — ATR de 14 períodos
          - bb_upper     — Bollinger Band superior (20, 2σ)
          - bb_middle    — Bollinger Band central
          - bb_lower     — Bollinger Band inferior
          - volume_avg_20 — Volume médio de 20 períodos
          - last_close   — Último preço de fecho nas barras
          - current_price — Snapshot actual do mercado (injectado externamente)
          - atr_avg_60   — Média do ATR(14) nos últimos 60 períodos
                           (utilizado para detecção de regime SIDEWAYS)

        Utiliza as funções de cálculo de indicadores definidas neste módulo.
        Quando o módulo signal_engine estiver disponível, estas funções
        poderão ser substituídas pelas implementações de lá.

        Args:
            contract: Contrato IB (utilizado apenas para logging/identificação).
            bars_df: DataFrame com colunas [date, open, high, low, close, volume].

        Returns:
            Dicionário com todos os indicadores. Valores são None quando
            não há dados suficientes para o cálculo.
        """
        result: dict[str, float | None] = {
            "sma25": None,
            "sma50": None,
            "sma200": None,
            "rsi14": None,
            "atr14": None,
            "bb_upper": None,
            "bb_middle": None,
            "bb_lower": None,
            "volume_avg_20": None,
            "last_close": None,
            "current_price": None,
            "current_volume": None,
            "atr_avg_60": None,
        }

        if bars_df.empty:
            logger.warning(
                "DataFrame vazio fornecido a get_market_data para %s. "
                "Todos os indicadores serão None.",
                contract.symbol,
            )
            return result

        close: pd.Series = bars_df["close"]
        high: pd.Series = bars_df["high"]
        low: pd.Series = bars_df["low"]
        volume: pd.Series = bars_df["volume"]

        # ---- Último fecho diário / preço actual injectado externamente ----
        result["last_close"] = _safe_last(close)
        if current_price is not None:
            result["current_price"] = round(float(current_price), 6)

        # ---- SMAs ----
        sma25 = compute_sma(close, 25)
        sma50 = compute_sma(close, 50)
        sma200 = compute_sma(close, 200)

        result["sma25"] = _safe_last(sma25)
        result["sma50"] = _safe_last(sma50)
        result["sma200"] = _safe_last(sma200)

        # ---- RSI(14) ----
        rsi14 = compute_rsi(close, 14)
        result["rsi14"] = _safe_last(rsi14)

        # ---- ATR(14) ----
        atr14 = compute_atr(high, low, close, 14)
        result["atr14"] = _safe_last(atr14)

        # ---- ATR médio de 60 períodos (para detecção de SIDEWAYS) ----
        if len(atr14.dropna()) >= 60:
            result["atr_avg_60"] = float(atr14.dropna().iloc[-60:].mean())
        elif len(atr14.dropna()) > 0:
            # Menos de 60 barras disponíveis: usar tudo o que há
            result["atr_avg_60"] = float(atr14.dropna().mean())
            logger.debug(
                "Menos de 60 barras para atr_avg_60 de %s. "
                "A usar %d barras disponíveis.",
                contract.symbol, len(atr14.dropna()),
            )

        # ---- Bollinger Bands (20, 2σ) ----
        bb_upper, bb_middle, bb_lower = compute_bollinger_bands(close, 20, 2.0)
        result["bb_upper"] = _safe_last(bb_upper)
        result["bb_middle"] = _safe_last(bb_middle)
        result["bb_lower"] = _safe_last(bb_lower)

        # ---- Volume médio de 20 períodos ----
        vol_avg_20 = compute_sma(volume, 20)
        result["volume_avg_20"] = _safe_last(vol_avg_20)

        logger.info(
            "Indicadores calculados para %s: close=%.4f | preço actual=%s | SMA25=%s | SMA50=%s | "
            "SMA200=%s | RSI14=%s | ATR14=%s | BB=[%s, %s, %s] | VolAvg20=%s | ATRavg60=%s",
            contract.symbol,
            result["last_close"] or 0.0,
            _fmt(result["current_price"]),
            _fmt(result["sma25"]),
            _fmt(result["sma50"]),
            _fmt(result["sma200"]),
            _fmt(result["rsi14"]),
            _fmt(result["atr14"]),
            _fmt(result["bb_upper"]),
            _fmt(result["bb_middle"]),
            _fmt(result["bb_lower"]),
            _fmt(result["volume_avg_20"]),
            _fmt(result["atr_avg_60"]),
        )

        return result

    async def get_market_data_live(
        self,
        contract: Stock | Forex | Future | CFD,
        bars_df: pd.DataFrame,
    ) -> dict[str, Any]:
        """
        Enriquece os indicadores técnicos com o snapshot actual do mercado.

        Quando o snapshot falha, usa o último fecho como fallback gracioso
        e regista um aviso explícito.
        """
        indicators = self.get_market_data(contract, bars_df)
        last_close = indicators.get("last_close")
        price_details = await self.get_current_price_details(contract)
        live_price = price_details.get("price")
        price_source = price_details.get("source")
        price_fresh = bool(price_details.get("fresh", False))

        if live_price is None and last_close is not None:
            live_price = float(last_close)
            price_source = "last_close"
            price_fresh = False
            logger.warning(
                "Preço actual indisponível para %s — a usar último fecho %.4f como fallback.",
                contract.symbol,
                live_price,
            )

        indicators["current_price"] = (
            round(float(live_price), 6) if live_price is not None else None
        )
        indicators["current_volume"] = (
            float(price_details["volume"])
            if price_details.get("volume") is not None
            else None
        )
        indicators["price_source"] = price_source
        indicators["price_fresh"] = price_fresh
        indicators["price_quality"] = price_details.get("quality")
        indicators["price_execution_ready"] = bool(
            price_details.get("execution_ready", False)
        )
        return indicators


# ---------------------------------------------------------------------------
# Funções auxiliares privadas
# ---------------------------------------------------------------------------

def _valid_price(value: float | None) -> bool:
    """Verifica se um valor de preço é válido (não nulo, não NaN, positivo)."""
    if value is None:
        return False
    try:
        v = float(value)
        return not (np.isnan(v) or v <= 0.0 or v > 1e12)
    except (ValueError, TypeError):
        return False


def _safe_last(series: pd.Series) -> float | None:
    """Devolve o último valor não-NaN de uma Series, ou None."""
    if series is None or series.empty:
        return None
    last = series.iloc[-1]
    if pd.isna(last):
        return None
    return round(float(last), 6)


def _fmt(value: float | None) -> str:
    """Formata um float para logging (4 casas decimais) ou 'N/A'."""
    if value is None:
        return "N/A"
    return f"{value:.4f}"


def _extract_last_numeric_value(values: Any) -> float | None:
    """Extrai o último valor numérico de Series/DataFrame sem depender de coerções implícitas."""
    if values is None:
        return None

    if isinstance(values, pd.DataFrame):
        if values.empty:
            return None
        return _extract_last_numeric_value(values.iloc[-1])

    if isinstance(values, pd.Series):
        if values.empty:
            return None
        last = values.iloc[-1]
        if isinstance(last, pd.Series):
            return _extract_last_numeric_value(last.dropna())
        if pd.isna(last):
            return None
        return float(last)

    if pd.isna(values):
        return None
    return float(values)


def _extract_ticker_volume(ticker: Any) -> float | None:
    """Extrai volume utilizável do ticker quando disponível no mesmo snapshot."""
    volume = getattr(ticker, "volume", None)
    return float(volume) if _valid_price(volume) else None


def _build_price_snapshot_from_ticker(ticker: Any) -> dict[str, Any] | None:
    """Constrói o snapshot de preço a partir do ticker IB, priorizando dados IB antes de fallback externo."""
    volume = _extract_ticker_volume(ticker)
    market_data_type = getattr(ticker, "marketDataType", None)

    if _valid_price(getattr(ticker, "last", None)):
        return {
            "price": float(ticker.last),
            "source": "last",
            "fresh": True,
            "volume": volume,
            "_market_data_type": market_data_type,
        }

    if _valid_price(getattr(ticker, "bid", None)) and _valid_price(getattr(ticker, "ask", None)):
        return {
            "price": round((float(ticker.bid) + float(ticker.ask)) / 2.0, 6),
            "source": "mid",
            "fresh": True,
            "volume": volume,
            "_market_data_type": market_data_type,
        }

    if _valid_price(getattr(ticker, "markPrice", None)):
        return {
            "price": float(ticker.markPrice),
            "source": "mark",
            "fresh": True,
            "volume": volume,
            "_market_data_type": market_data_type,
        }

    if _valid_price(getattr(ticker, "close", None)):
        return {
            "price": float(ticker.close),
            "source": "close",
            "fresh": False,
            "volume": volume,
            "_market_data_type": market_data_type,
        }

    return None


def _coerce_utc_date(value: Any) -> date | None:
    """Converte timestamps diversos para data UTC."""
    if value is None:
        return None
    try:
        ts = pd.Timestamp(value)
    except (TypeError, ValueError):
        return None
    if pd.isna(ts):
        return None
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    else:
        ts = ts.tz_convert("UTC")
    return ts.date()


def _previous_business_day(current_day: date) -> date:
    """Obtém o dia útil anterior, ignorando fins-de-semana."""
    previous_day = current_day - timedelta(days=1)
    while previous_day.weekday() >= 5:
        previous_day -= timedelta(days=1)
    return previous_day


def _is_yfinance_quote_fresh(asof: Any, *, now: datetime | None = None) -> bool:
    """
    Aceita quotes do yfinance do dia actual ou do último fecho disponível.

    Mantém a lógica IB inalterada; este critério aplica-se apenas ao fallback
    diário do yfinance, que não tem a mesma latência dos snapshots IB.
    """
    asof_date = _coerce_utc_date(asof)
    if asof_date is None:
        return False

    current_day = (now or datetime.now(timezone.utc)).date()
    if asof_date == current_day:
        return True
    return asof_date == _previous_business_day(current_day)

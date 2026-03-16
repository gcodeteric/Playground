from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

if sys.version_info >= (3, 10):
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())

from src.bond_mr_hedge import bond_mr_signal
from src.commodity_mr import commodity_mr_signal
from src.forex_breakout import detect_forex_range, generate_breakout_signal
from src.forex_mr import forex_mr_signal
from src.futures_mr import futures_mr_signal
from src.futures_trend import futures_trend_signal
from src.gap_fade import gap_fade_signal
from src.intl_etf_mr import intl_etf_signal
from src.options_premium import csp_signal
from src.sector_rotation import sector_rotation_signal

logger = logging.getLogger(__name__)


def _base_ohlcv(length: int = 260) -> dict[str, list[float]]:
    closes = [100.0 + i * 0.1 for i in range(length)]
    highs = [value + 0.5 for value in closes]
    lows = [value - 0.5 for value in closes]
    opens = [value - 0.1 for value in closes]
    volumes = [1_000_000.0 + i * 1000.0 for i in range(length)]
    return {
        "closes": closes,
        "highs": highs,
        "lows": lows,
        "opens": opens,
        "volumes": volumes,
    }


def _validate_signal(module: str, payload: dict[str, Any]) -> tuple[bool, str]:
    required = {
        "signal",
        "confidence",
        "entry_price",
        "stop_loss",
        "take_profit",
        "position_size",
        "metadata",
    }
    missing = sorted(required - set(payload.keys()))
    if missing:
        return False, f"campos em falta: {missing}"
    return True, str(payload.get("signal"))


def _run_case(name: str, fn: Any) -> tuple[bool, str]:
    try:
        payload = fn()
        if not isinstance(payload, dict):
            return False, f"retorno inválido: {type(payload).__name__}"
        ok, detail = _validate_signal(name, payload)
        if not ok:
            return False, detail
        return True, detail
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    base = _base_ohlcv()
    closes = base["closes"]
    highs = base["highs"]
    lows = base["lows"]
    opens = base["opens"]
    volumes = base["volumes"]

    sector_config = {
        "rebalance_day": 1,
        "momentum_period": 252,
        "skip_recent_days": 21,
        "top_n": 3,
        "bear_filter_sma": 200,
        "safe_havens": ["XLU", "XLP", "GLD"],
    }
    gap_config = {
        "min_gap_atr": 0.5,
        "max_gap_atr": 2.5,
        "min_fill_probability": 0.60,
        "min_body_ratio_fade": 0.35,
    }
    forex_mr_config = {
        "sma_period": 20,
        "vol_lookback": 60,
        "z_entry": -2.0,
        "rsi_period": 2,
        "rsi_entry": 10,
        "adx_ranging_max": 20.0,
        "chop_min_ranging": 55.0,
        "stop_atr_mult_fx": 1.5,
    }
    forex_breakout_config = {
        "min_body_ratio": 0.60,
        "min_days_in_range": 15,
        "max_range_atr_mult": 3.0,
        "tp_atr_mult": 2.0,
        "range_quality_min": 0.6,
    }
    futures_mr_config = {
        "kairi_thresholds": {"MES": -3.0},
        "sma_lookback": 25,
        "overnight_margin_mult": 1.5,
        "min_equity_futures": 2000,
    }
    futures_trend_config = {
        "adx_min": 25.0,
        "params_by_type": {
            "indices": {"ema_fast": 20, "ema_slow": 50, "donchian_period": 20},
        },
        "chandelier_period": 22,
        "chandelier_atr_mult": 3.0,
        "pyramid_max_adds": 3,
        "pyramid_trigger_atr": 1.5,
    }
    intl_config = {
        "kairi_thresholds": {"EWZ": -25.0},
        "sma_lookback": 25,
        "max_correlation": 0.70,
        "correlation_lookback": 60,
    }
    commodity_config = {
        "thresholds": {
            "GLD": {"kairi_long": -10.0, "kairi_short": 10.0, "sma": 50, "enabled": True},
        },
        "max_hold_days": 10,
    }
    options_config = {
        "allowed_symbols": ["SPY", "QQQ", "IWM"],
        "target_delta": 0.15,
        "target_dte": 45,
        "close_at_profit_pct": 0.50,
        "close_at_dte": 21,
        "iv_rank_min": 30,
        "vix_max_sell": 30,
        "min_days_to_earnings": 21,
    }
    bond_config = {
        "kairi_thresholds": {"TLT": -15.0, "IEF": -10.0, "SHY": -7.0, "LQD": -15.0},
        "max_allocation_pct": 0.20,
        "defensive_min_days": 10,
        "bear_vix_proxy": 25.0,
        "correlation_lookback": 60,
    }

    breakout_highs = [10.0] * 20 + [10.5]
    breakout_lows = [9.0] * 20 + [9.8]
    breakout_opens = [9.5] * 20 + [9.9]
    breakout_closes = [9.5] * 20 + [10.6]
    range_info = detect_forex_range(
        breakout_highs[:-1],
        breakout_lows[:-1],
        breakout_closes[:-1],
        forex_breakout_config,
    )

    cases: list[tuple[str, Any]] = [
        (
            "sector_rotation",
            lambda: sector_rotation_signal(
                {
                    "XLK": {"close": [100.0 + i * 0.20 for i in range(260)]},
                    "XLF": {"close": [100.0 + i * 0.15 for i in range(260)]},
                    "XLV": {"close": [100.0 + i * 0.10 for i in range(260)]},
                    "XLP": {"close": [100.0 + i * 0.05 for i in range(260)]},
                    "XLU": {"close": [100.0 + i * 0.04 for i in range(260)]},
                    "GLD": {"close": [100.0 + i * 0.06 for i in range(260)]},
                },
                spy_closes=[100.0 + i for i in range(210)],
                config=sector_config,
                current_day_of_month=1,
            ),
        ),
        (
            "gap_fade",
            lambda: gap_fade_signal(
                closes=[100.0] * 18 + [100.0, 100.0],
                opens=[100.0] * 19 + [100.8],
                highs=[100.4] * 19 + [101.1],
                lows=[99.6] * 19 + [100.1],
                config=gap_config,
            ),
        ),
        (
            "forex_mr",
            lambda: forex_mr_signal(
                closes=[1.10] * 55 + [1.08, 1.07, 1.06, 1.05, 1.04, 1.03],
                highs=[value + 0.01 for value in ([1.10] * 55 + [1.08, 1.07, 1.06, 1.05, 1.04, 1.03])],
                lows=[value - 0.01 for value in ([1.10] * 55 + [1.08, 1.07, 1.06, 1.05, 1.04, 1.03])],
                config=forex_mr_config,
                now_utc_hour=10,
            ),
        ),
        (
            "forex_breakout",
            lambda: generate_breakout_signal(
                closes=breakout_closes,
                opens=breakout_opens,
                highs=breakout_highs,
                lows=breakout_lows,
                range_info=range_info,
                config=forex_breakout_config,
            ),
        ),
        (
            "futures_mr",
            lambda: futures_mr_signal(
                symbol="MES",
                closes=[100.0] * 30 + [96.0, 95.0, 94.0, 93.0, 92.0, 91.0, 90.0, 89.0, 88.0, 87.0],
                highs=[value + 1.0 for value in ([100.0] * 30 + [96.0, 95.0, 94.0, 93.0, 92.0, 91.0, 90.0, 89.0, 88.0, 87.0])],
                lows=[value - 1.0 for value in ([100.0] * 30 + [96.0, 95.0, 94.0, 93.0, 92.0, 91.0, 90.0, 89.0, 88.0, 87.0])],
                config=futures_mr_config,
            ),
        ),
        (
            "futures_trend",
            lambda: futures_trend_signal(
                symbol="MES",
                closes=closes,
                highs=highs,
                lows=lows,
                symbol_type="indices",
                config=futures_trend_config,
            ),
        ),
        (
            "intl_etf_mr",
            lambda: intl_etf_signal(
                symbol="EWZ",
                closes=[100.0] * 205 + [90.0, 89.0, 88.0, 87.0, 86.0],
                highs=[value + 1.0 for value in ([100.0] * 205 + [90.0, 89.0, 88.0, 87.0, 86.0])],
                lows=[value - 1.0 for value in ([100.0] * 205 + [90.0, 89.0, 88.0, 87.0, 86.0])],
                volumes=[1_000_000.0] * 209 + [2_000_000.0],
                open_positions=[],
                returns_map={},
                config=intl_config,
            ),
        ),
        (
            "commodity_mr",
            lambda: commodity_mr_signal(
                symbol="GLD",
                closes=[100.0] * 55 + [92.0, 91.0, 90.0, 89.0, 88.0],
                highs=[value + 1.0 for value in ([100.0] * 55 + [92.0, 91.0, 90.0, 89.0, 88.0])],
                lows=[value - 1.0 for value in ([100.0] * 55 + [92.0, 91.0, 90.0, 89.0, 88.0])],
                config=commodity_config,
            ),
        ),
        (
            "options_premium",
            lambda: csp_signal(
                symbol="SPY",
                spot=450.0,
                iv_rank=35.0,
                iv_implied=0.18,
                regime="BULL",
                days_to_earnings=30,
                vix_proxy=18.0,
                config=options_config,
            ),
        ),
        (
            "bond_mr_hedge",
            lambda: bond_mr_signal(
                symbol="TLT",
                closes=[100.0] * 210 + [80.0, 79.0, 78.0, 77.0, 76.0],
                highs=[value + 1.0 for value in ([100.0] * 210 + [80.0, 79.0, 78.0, 77.0, 76.0])],
                lows=[value - 1.0 for value in ([100.0] * 210 + [80.0, 79.0, 78.0, 77.0, 76.0])],
                spy_closes=[100.0] * 220,
                tlt_closes=[100.0] * 220,
                vix_proxy=18.0,
                defensive_state={"mode": "NORMAL", "days_in_defensive": 0},
                config=bond_config,
            ),
        ),
    ]

    passed = 0
    for name, fn in cases:
        ok, detail = _run_case(name, fn)
        if ok:
            passed += 1
            logger.info("✅ %s — %s", name, detail)
        else:
            logger.info("❌ %s — %s", name, detail)

    logger.info("")
    logger.info("Resultado: %d/%d", passed, len(cases))
    return 0 if passed == len(cases) else 1


if __name__ == "__main__":
    raise SystemExit(main())

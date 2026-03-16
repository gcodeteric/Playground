"""Módulo 4: Micro Futuros Trend Following.

Dual EMA 20/50 para índices, EMA 10/30 para metais/energia.
ADX > 25 obrigatório. Chandelier Exit como trailing stop.
Pyramiding até 3 adições (averaging UP, nunca down).

Gate de activação: ADX > 25 (Módulo 3 adormece, Módulo 4 activa)
Fase de capital: 3+ (€10-25k)
"""

from __future__ import annotations

import logging
from typing import Any

from src.signal_engine import calculate_adx, calculate_atr, calculate_ema

logger = logging.getLogger(__name__)


def calculate_chandelier_exit(
    highs: list[float],
    lows: list[float],
    closes: list[float],
    atr: float,
    period: int = 22,
    atr_mult: float = 3.0,
    direction: str = "LONG",
) -> float:
    """Calcula o Chandelier Exit como trailing stop."""
    del highs, lows
    recent_closes = closes[-period:] if len(closes) >= period else closes
    if direction == "LONG":
        return max(recent_closes) - atr_mult * atr
    return min(recent_closes) + atr_mult * atr


def calculate_pyramid_entry(
    entry_price: float,
    current_price: float,
    atr: float,
    units_held: int,
    signal_direction: str,
    config: dict[str, Any],
) -> dict[str, Any]:
    """Calcula se deve adicionar uma unidade de pyramid."""
    max_pyramid = int(config.get("pyramid_max_adds", 3))
    trigger_atr = float(config.get("pyramid_trigger_atr", 1.5))

    if units_held >= max_pyramid:
        return {"add_unit": False}

    is_long = signal_direction == "LONG"
    profit_distance = (
        current_price - entry_price if is_long else entry_price - current_price
    )

    if profit_distance > trigger_atr * atr:
        new_stop = (
            entry_price + 0.5 * atr if is_long else entry_price - 0.5 * atr
        )
        return {
            "add_unit": True,
            "entry_price": current_price,
            "stop_loss": round(new_stop, 6),
        }

    return {"add_unit": False}


def futures_trend_signal(
    symbol: str,
    closes: list[float],
    highs: list[float],
    lows: list[float],
    symbol_type: str,
    config: dict[str, Any],
) -> dict[str, Any]:
    """Gera sinal de trend following para micro futuros."""
    params = config.get("params_by_type", {}).get(symbol_type, {})
    ema_fast_period = int(params.get("ema_fast", 20))
    ema_slow_period = int(params.get("ema_slow", 50))
    adx_min = float(params.get("adx_min", config.get("adx_min", 25.0)))

    n = min(len(closes), len(highs), len(lows))
    if n < ema_slow_period + 14:
        logger.info(
            "Futures Trend sem acção para %s: dados insuficientes (%d < %d).",
            symbol,
            n,
            ema_slow_period + 14,
        )
        return _flat_signal({"reason": "insufficient_data"})

    ema_fast = calculate_ema(closes, ema_fast_period)
    ema_slow = calculate_ema(closes, ema_slow_period)
    adx = calculate_adx(highs, lows, closes, 14)
    atr = calculate_atr(highs, lows, closes, 14)

    if any(value is None for value in (ema_fast, ema_slow, atr)):
        logger.info("Futures Trend sem acção para %s: indicador inválido.", symbol)
        return _flat_signal({"reason": "indicator_invalid"})

    if adx < adx_min:
        logger.info(
            "Futures Trend sem acção para %s: ADX %.2f abaixo de %.2f.",
            symbol,
            adx,
            adx_min,
        )
        return _flat_signal({"reason": "adx_below_threshold", "adx": adx})

    price = closes[-1]
    chandelier_period = int(config.get("chandelier_period", 22))
    chandelier_mult = float(config.get("chandelier_atr_mult", 3.0))

    if ema_fast > ema_slow:
        stop = calculate_chandelier_exit(
            highs,
            lows,
            closes,
            atr,
            chandelier_period,
            chandelier_mult,
            "LONG",
        )
        signal = {
            "signal": "LONG",
            "confidence": 2,
            "entry_price": price,
            "stop_loss": round(stop, 6),
            "take_profit": round(price + 3.0 * atr, 6),
            "position_size": 0.0,
            "metadata": {
                "ema_fast": round(ema_fast, 6),
                "ema_slow": round(ema_slow, 6),
                "adx": round(adx, 2),
                "module": "futures_trend",
            },
        }
        logger.info(
            "Futures Trend gerou LONG para %s com ADX=%.2f.",
            symbol,
            adx,
        )
        return signal

    if ema_fast < ema_slow:
        stop = calculate_chandelier_exit(
            highs,
            lows,
            closes,
            atr,
            chandelier_period,
            chandelier_mult,
            "SHORT",
        )
        signal = {
            "signal": "SHORT",
            "confidence": 2,
            "entry_price": price,
            "stop_loss": round(stop, 6),
            "take_profit": round(price - 3.0 * atr, 6),
            "position_size": 0.0,
            "metadata": {
                "ema_fast": round(ema_fast, 6),
                "ema_slow": round(ema_slow, 6),
                "adx": round(adx, 2),
                "module": "futures_trend",
            },
        }
        logger.info(
            "Futures Trend gerou SHORT para %s com ADX=%.2f.",
            symbol,
            adx,
        )
        return signal

    logger.info("Futures Trend sem acção para %s: sem crossover.", symbol)
    return _flat_signal({"reason": "no_crossover"})


def _flat_signal(metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    """Retorna sinal FLAT."""
    return {
        "signal": "FLAT",
        "confidence": 0,
        "entry_price": 0.0,
        "stop_loss": 0.0,
        "take_profit": 0.0,
        "position_size": 0.0,
        "metadata": metadata or {},
    }

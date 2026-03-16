"""Módulo 2: Forex Breakout & Range Fade.

Detecta ranges consolidados e opera breakouts (ADX > 25) ou range fades
(falsos breakouts que regressam ao range).

Gate de activação: ADX > 25 (Módulo 1 adormece, Módulo 2 activa)
Fase de capital: 2+ (€2-10k)
"""

from __future__ import annotations

import logging
from typing import Any

from src.signal_engine import calculate_adx, calculate_atr

logger = logging.getLogger(__name__)


def detect_forex_range(
    highs: list[float],
    lows: list[float],
    closes: list[float],
    config: dict[str, Any],
) -> dict[str, Any]:
    """Detecta se o preço está num range consolidado."""
    lookback = int(config.get("min_days_in_range", 15))
    adx_max = 20.0
    atr_mult = float(config.get("max_range_atr_mult", 3.0))
    quality_min = float(config.get("range_quality_min", 0.6))

    n = min(len(highs), len(lows), len(closes))
    if n < lookback + 14:
        logger.info(
            "Forex Breakout sem range: dados insuficientes (%d < %d).",
            n,
            lookback + 14,
        )
        return {"valid": False, "reason": "insufficient_data"}

    atr14 = calculate_atr(highs, lows, closes, 14)
    if atr14 is None or atr14 <= 0:
        logger.info("Forex Breakout sem range: ATR inválido.")
        return {"valid": False, "reason": "atr_invalid"}

    recent_highs = highs[-lookback:]
    recent_lows = lows[-lookback:]
    recent_closes = closes[-lookback:]

    range_high = max(recent_highs)
    range_low = min(recent_lows)
    range_size = range_high - range_low

    range_ok = range_size <= atr_mult * atr14
    adx = calculate_adx(highs, lows, closes, 14)
    adx_ok = adx < adx_max

    buffer = 0.1 * range_size
    inside_count = sum(
        1
        for close in recent_closes
        if range_low + buffer <= close <= range_high - buffer
    )
    quality_score = inside_count / len(recent_closes) if recent_closes else 0.0

    valid = range_ok and adx_ok and quality_score >= quality_min
    result = {
        "valid": bool(valid),
        "upper": round(range_high, 6),
        "lower": round(range_low, 6),
        "quality_score": round(quality_score, 4),
        "days_in_range": lookback,
        "adx": round(adx, 2),
        "atr14": atr14,
    }

    if not valid:
        reasons: list[str] = []
        if not range_ok:
            reasons.append("range_too_wide")
        if not adx_ok:
            reasons.append("adx_too_high")
        if quality_score < quality_min:
            reasons.append("quality_too_low")
        result["reason"] = ",".join(reasons) if reasons else "range_invalid"
        logger.info("Forex Breakout range inválido: %s", result["reason"])
    else:
        logger.info(
            "Forex Breakout range válido: [%.4f, %.4f] | quality=%.2f | ADX=%.2f.",
            range_low,
            range_high,
            quality_score,
            adx,
        )

    return result


def generate_breakout_signal(
    closes: list[float],
    opens: list[float],
    highs: list[float],
    lows: list[float],
    range_info: dict[str, Any],
    config: dict[str, Any],
) -> dict[str, Any]:
    """Gera sinal de breakout ou range fade."""
    if not range_info.get("valid"):
        logger.info("Forex Breakout sem sinal: range inválido.")
        return _flat_signal({"reason": "range_invalid", "range_info": range_info})

    close = closes[-1]
    open_ = opens[-1]
    atr14 = float(range_info.get("atr14", 0.0) or 0.0)
    if atr14 <= 0:
        logger.info("Forex Breakout sem sinal: ATR inválido.")
        return _flat_signal({"reason": "atr_invalid"})

    body = abs(close - open_)
    day_range = highs[-1] - lows[-1]
    body_ratio = body / day_range if day_range > 0 else 0.0

    high_n = float(range_info["upper"])
    low_n = float(range_info["lower"])
    min_body = float(config.get("min_body_ratio", 0.60))
    tp_mult = float(config.get("tp_atr_mult", 2.0))

    if close > high_n and body_ratio >= min_body and (close - high_n) >= 1.0 * atr14:
        signal = {
            "signal": "LONG",
            "confidence": 2,
            "entry_price": close,
            "stop_loss": round(low_n, 6),
            "take_profit": round(close + tp_mult * atr14, 6),
            "position_size": 0.0,
            "metadata": {
                "type": "breakout",
                "body_ratio": round(body_ratio, 4),
                "module": "forex_breakout",
            },
        }
        logger.info("Forex Breakout gerou LONG breakout.")
        return signal

    if close < low_n and body_ratio >= min_body and (low_n - close) >= 1.0 * atr14:
        signal = {
            "signal": "SHORT",
            "confidence": 2,
            "entry_price": close,
            "stop_loss": round(high_n, 6),
            "take_profit": round(close - tp_mult * atr14, 6),
            "position_size": 0.0,
            "metadata": {
                "type": "breakout",
                "body_ratio": round(body_ratio, 4),
                "module": "forex_breakout",
            },
        }
        logger.info("Forex Breakout gerou SHORT breakout.")
        return signal

    if highs[-1] > high_n and close < high_n and body_ratio < 0.35:
        midline = (high_n + low_n) / 2.0
        signal = {
            "signal": "SHORT",
            "confidence": 2,
            "entry_price": close,
            "stop_loss": round(highs[-1] + 0.5 * atr14, 6),
            "take_profit": round(midline, 6),
            "position_size": 0.0,
            "metadata": {"type": "range_fade", "module": "forex_breakout"},
        }
        logger.info("Forex Breakout gerou SHORT range fade.")
        return signal

    if lows[-1] < low_n and close > low_n and body_ratio < 0.35:
        midline = (high_n + low_n) / 2.0
        signal = {
            "signal": "LONG",
            "confidence": 2,
            "entry_price": close,
            "stop_loss": round(lows[-1] - 0.5 * atr14, 6),
            "take_profit": round(midline, 6),
            "position_size": 0.0,
            "metadata": {"type": "range_fade", "module": "forex_breakout"},
        }
        logger.info("Forex Breakout gerou LONG range fade.")
        return signal

    logger.info("Forex Breakout sem sinal: sem breakout nem fade.")
    return _flat_signal({"reason": "no_breakout_or_fade", "range_info": range_info})


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

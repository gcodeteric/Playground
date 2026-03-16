"""Módulo 8: ETFs de Commodities — KAIRI MR com thresholds assimétricos.

Thresholds LONG e SHORT separados por ETF para reflectir drag de contango
(USO: drag 10-30%/ano, UNG: DESQUALIFICADO >30%/ano).

Fase de capital: 2/3 (€2-10k+)
"""

from __future__ import annotations

import logging
from typing import Any

from src.signal_engine import calculate_atr, calculate_rsi, calculate_sma

logger = logging.getLogger(__name__)


def contango_drag_guard(
    symbol: str,
    config: dict[str, Any],
) -> dict[str, Any]:
    """Verifica se o ETF de commodity é permitido."""
    thresholds = config.get("thresholds", {})
    sym_config = thresholds.get(symbol, {})

    if not sym_config.get("enabled", True):
        logger.info(
            "Commodity MR bloqueado para %s: %s.",
            symbol,
            sym_config.get("reason", "disabled"),
        )
        return {"allowed": False, "reason": sym_config.get("reason", "disabled")}

    return {
        "allowed": True,
        "max_hold_days": config.get("max_hold_days", 10),
        "kairi_long": sym_config.get("kairi_long", -25.0),
        "kairi_short": sym_config.get("kairi_short", 25.0),
        "sma_period": sym_config.get("sma", 25),
    }


def commodity_mr_signal(
    symbol: str,
    closes: list[float],
    highs: list[float],
    lows: list[float],
    config: dict[str, Any],
) -> dict[str, Any]:
    """Gera sinal MR para ETFs de commodities com thresholds assimétricos."""
    guard = contango_drag_guard(symbol, config)
    if not guard.get("allowed"):
        return _flat_signal({"reason": guard.get("reason", "blocked")})

    sma_period = int(guard.get("sma_period", 25))
    kairi_long = float(guard.get("kairi_long", -25.0))

    if len(closes) < max(sma_period, 14) + 1:
        logger.info(
            "Commodity MR sem acção para %s: dados insuficientes (%d).",
            symbol,
            len(closes),
        )
        return _flat_signal({"reason": "insufficient_data"})

    price = closes[-1]
    sma = calculate_sma(closes, sma_period)
    if sma is None or sma <= 0:
        logger.info("Commodity MR sem acção para %s: SMA inválida.", symbol)
        return _flat_signal({"reason": "sma_invalid"})

    kairi = ((price - sma) / sma) * 100.0
    if kairi > kairi_long:
        logger.info(
            "Commodity MR sem acção para %s: KAIRI %.4f acima do threshold %.4f.",
            symbol,
            kairi,
            kairi_long,
        )
        return _flat_signal({"reason": "kairi_above_threshold", "kairi": kairi})

    rsi14 = calculate_rsi(closes, 14)
    atr = calculate_atr(highs, lows, closes, 14)
    if atr is None:
        logger.info("Commodity MR sem acção para %s: ATR inválido.", symbol)
        return _flat_signal({"reason": "atr_invalid"})

    confidence = 2
    if rsi14 is not None and rsi14 < 30:
        confidence = 3

    signal = {
        "signal": "LONG",
        "confidence": confidence,
        "entry_price": price,
        "stop_loss": round(price - 1.0 * atr, 6),
        "take_profit": round(price + 2.5 * atr, 6),
        "position_size": 0.0,
        "metadata": {
            "kairi": round(kairi, 4),
            "threshold": kairi_long,
            "module": "commodity_mr",
            "max_hold_days": guard.get("max_hold_days", 10),
        },
    }
    logger.info(
        "Commodity MR gerou LONG para %s com confidence=%d (KAIRI=%.4f).",
        symbol,
        confidence,
        kairi,
    )
    return signal


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

"""Módulo 3: Micro Futuros Mean Reversion.

Aplica KAIRI adaptado (thresholds mais baixos que acções) a micro futuros
CME (MES, MNQ, M2K, MYM, MGC, MCL).

IMPORTANTE: KAIRI -25% NÃO SE APLICA A FUTUROS — usar thresholds específicos.

Fase de capital: 2+ (€2-10k)
"""

from __future__ import annotations

import logging
from typing import Any

from src.signal_engine import calculate_atr, calculate_rsi, calculate_sma

logger = logging.getLogger(__name__)


def handle_futures_roll(
    closes_front: list[float],
    closes_next: list[float],
    highs_front: list[float],
    lows_front: list[float],
    highs_next: list[float],
    lows_next: list[float],
    opens_front: list[float],
    opens_next: list[float],
    roll_index: int,
) -> dict[str, list[float]]:
    """Ajuste de Panama para série contínua no roll de futuros."""
    max_roll = min(
        len(closes_front),
        len(closes_next),
        len(highs_front),
        len(lows_front),
        len(highs_next),
        len(lows_next),
        len(opens_front),
        len(opens_next),
    )
    if roll_index < 0 or roll_index >= max_roll:
        logger.warning("Índice de roll inválido: %d", roll_index)
        return {
            "close": list(closes_front),
            "high": list(highs_front),
            "low": list(lows_front),
            "open": list(opens_front),
        }

    gap = closes_next[roll_index] - closes_front[roll_index]

    adjusted_close = [value + gap for value in closes_front[: roll_index + 1]]
    adjusted_close.extend(closes_next[roll_index + 1 :])
    adjusted_high = [value + gap for value in highs_front[: roll_index + 1]]
    adjusted_high.extend(highs_next[roll_index + 1 :])
    adjusted_low = [value + gap for value in lows_front[: roll_index + 1]]
    adjusted_low.extend(lows_next[roll_index + 1 :])
    adjusted_open = [value + gap for value in opens_front[: roll_index + 1]]
    adjusted_open.extend(opens_next[roll_index + 1 :])

    logger.info("Panama adjustment aplicado: gap=%.4f no índice %d.", gap, roll_index)
    return {
        "close": adjusted_close,
        "high": adjusted_high,
        "low": adjusted_low,
        "open": adjusted_open,
    }


def check_overnight_safety(
    equity: float,
    margin_req: float,
    config: dict[str, Any],
) -> bool:
    """Verifica se é seguro manter posição overnight em futuros."""
    min_equity = float(config.get("min_equity_futures", 2000))
    if equity < min_equity:
        logger.info(
            "Overnight bloqueado: equity %.2f abaixo do mínimo %.2f.",
            equity,
            min_equity,
        )
        return False

    mult = float(config.get("overnight_margin_mult", 1.5))
    is_safe = equity >= margin_req * mult
    if not is_safe:
        logger.info(
            "Overnight bloqueado: equity %.2f abaixo de margem×mult %.2f.",
            equity,
            margin_req * mult,
        )
    return is_safe


def futures_mr_signal(
    symbol: str,
    closes: list[float],
    highs: list[float],
    lows: list[float],
    config: dict[str, Any],
) -> dict[str, Any]:
    """Gera sinal de mean reversion para micro futuros."""
    thresholds = config.get("kairi_thresholds", {})
    kairi_threshold = float(thresholds.get(symbol, -3.0))
    sma_lookback = int(config.get("sma_lookback", 25))

    n = min(len(closes), len(highs), len(lows))
    if n < sma_lookback + 14:
        logger.info(
            "Futures MR sem acção para %s: dados insuficientes (%d < %d).",
            symbol,
            n,
            sma_lookback + 14,
        )
        return _flat_signal({"reason": "insufficient_data"})

    price = closes[-1]
    sma = calculate_sma(closes, sma_lookback)
    if sma is None or sma <= 0:
        logger.info("Futures MR sem acção para %s: SMA inválida.", symbol)
        return _flat_signal({"reason": "sma_invalid"})

    kairi = ((price - sma) / sma) * 100.0
    rsi14 = calculate_rsi(closes, 14)
    atr = calculate_atr(highs, lows, closes, 14)

    if atr is None or atr <= 0:
        logger.info("Futures MR sem acção para %s: ATR inválido.", symbol)
        return _flat_signal({"reason": "atr_invalid"})

    if kairi > kairi_threshold:
        logger.info(
            "Futures MR sem acção para %s: KAIRI %.4f acima do threshold %.4f.",
            symbol,
            kairi,
            kairi_threshold,
        )
        return _flat_signal({"reason": "kairi_above_threshold", "kairi": kairi})

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
            "rsi14": round(rsi14, 2) if rsi14 is not None else None,
            "threshold": kairi_threshold,
            "module": "futures_mr",
        },
    }
    logger.info(
        "Futures MR gerou LONG para %s com confidence=%d (KAIRI=%.4f).",
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

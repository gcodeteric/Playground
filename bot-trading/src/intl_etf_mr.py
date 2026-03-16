"""Módulo 5: ETFs Internacionais — KAIRI Mean Reversion.

Aplica a mesma lógica Kotegawa do core mas com thresholds adaptados
por região geográfica. Inclui filtro de correlação para evitar
concentração excessiva em activos correlacionados.

Fase de capital: 3+ (€10-25k)
"""

from __future__ import annotations

import logging
from typing import Any

from src.risk_manager import check_correlation_limit
from src.signal_engine import (
    calculate_atr,
    calculate_bollinger_bands,
    calculate_rsi,
    calculate_sma,
    calculate_volume_avg,
)

logger = logging.getLogger(__name__)


def intl_etf_signal(
    symbol: str,
    closes: list[float],
    highs: list[float],
    lows: list[float],
    volumes: list[float],
    open_positions: list[str],
    returns_map: dict[str, list[float]],
    config: dict[str, Any],
) -> dict[str, Any]:
    """Gera sinal KAIRI MR para ETFs internacionais."""
    thresholds = config.get("kairi_thresholds", {})
    kairi_threshold = float(thresholds.get(symbol, -25.0))
    sma_lookback = int(config.get("sma_lookback", 25))
    max_corr = float(config.get("max_correlation", 0.70))
    corr_lookback = int(config.get("correlation_lookback", 60))

    if len(closes) < 200:
        logger.info(
            "Intl ETF MR sem acção para %s: dados insuficientes (%d < 200).",
            symbol,
            len(closes),
        )
        return _flat_signal({"reason": "insufficient_data"})

    price = closes[-1]
    sma25 = calculate_sma(closes, sma_lookback)
    if sma25 is None or sma25 <= 0:
        logger.info("Intl ETF MR sem acção para %s: SMA inválida.", symbol)
        return _flat_signal({"reason": "sma_invalid"})

    kairi = ((price - sma25) / sma25) * 100.0
    if kairi > kairi_threshold:
        logger.info(
            "Intl ETF MR sem acção para %s: KAIRI %.4f acima do threshold %.4f.",
            symbol,
            kairi,
            kairi_threshold,
        )
        return _flat_signal({"reason": "kairi_above_threshold", "kairi": kairi})

    if not check_correlation_limit(
        symbol,
        open_positions,
        returns_map,
        max_corr,
        corr_lookback,
    ):
        logger.info("Intl ETF MR bloqueado para %s por correlação.", symbol)
        return _flat_signal({"reason": "correlation_too_high"})

    rsi14 = calculate_rsi(closes, 14)
    atr = calculate_atr(highs, lows, closes, 14)
    if atr is None or rsi14 is None:
        logger.info("Intl ETF MR sem acção para %s: indicador inválido.", symbol)
        return _flat_signal({"reason": "indicator_invalid"})

    confirmations = 0
    if rsi14 < 30:
        confirmations += 1

    bb = calculate_bollinger_bands(closes, 20, 2.0)
    if bb is not None and price < bb[2]:
        confirmations += 1

    vol_avg = calculate_volume_avg(volumes, 20)
    if vol_avg is not None and volumes[-1] > 1.5 * vol_avg:
        confirmations += 1

    if confirmations < 1:
        logger.info("Intl ETF MR sem acção para %s: sem confirmações.", symbol)
        return _flat_signal({"reason": "no_confirmations"})

    confidence = min(confirmations, 3)
    signal = {
        "signal": "LONG",
        "confidence": confidence,
        "entry_price": price,
        "stop_loss": round(price - 1.0 * atr, 6),
        "take_profit": round(price + 2.5 * atr, 6),
        "position_size": 0.0,
        "metadata": {
            "kairi": round(kairi, 4),
            "rsi14": round(rsi14, 2),
            "threshold": kairi_threshold,
            "module": "intl_etf_mr",
        },
    }
    logger.info(
        "Intl ETF MR gerou LONG para %s com confidence=%d (KAIRI=%.4f).",
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

"""Módulo 6: Rotação Sectorial — Momentum 12-1 (Moskowitz).

Selecciona os Top-N sectores por momentum dos últimos 12 meses
(excluindo o último mês) e roda a carteira mensalmente.
Em bear market (SPY < SMA200), roda para safe havens.

Fase de capital: 1+ (€0-2k)
"""

from __future__ import annotations

import logging
from typing import Any

from src.signal_engine import calculate_sma

logger = logging.getLogger(__name__)


def sector_rotation_signal(
    df_map: dict[str, dict[str, list[float]]],
    spy_closes: list[float],
    config: dict[str, Any],
    current_day_of_month: int,
) -> dict[str, Any]:
    """Gera sinal de rotação sectorial baseado em Momentum 12-1.

    Metodologia (Moskowitz):
    - Momentum = retorno dos últimos 252 dias excluindo os últimos 21
    - Seleccionar Top-N sectores por momentum
    - Em bear market (SPY < SMA200): rodar para safe havens
    - Rebalancing mensal (dia 1 do mês)

    Args:
        df_map: Dicionário {symbol: {"close": [preços]}} com pelo menos 252 barras.
        spy_closes: Lista de preços de fecho do SPY.
        config: SECTOR_ROTATION_CONFIG com todos os parâmetros.
        current_day_of_month: Dia actual do mês (1-31).

    Returns:
        Signal dict no formato padrão do bot.
    """
    rebalance_day = int(config.get("rebalance_day", 1))
    if current_day_of_month != rebalance_day:
        logger.debug(
            "Rotação sectorial sem acção: dia %d != dia de rebalanceamento %d.",
            current_day_of_month,
            rebalance_day,
        )
        return _flat_signal({"reason": "not_rebalance_day"})

    momentum_period = int(config.get("momentum_period", 252))
    skip_recent = int(config.get("skip_recent_days", 21))
    top_n = int(config.get("top_n", 3))
    safe_havens = list(config.get("safe_havens", ["XLU", "XLP", "GLD"]))
    bear_sma = int(config.get("bear_filter_sma", 200))

    sma_spy = calculate_sma(spy_closes, bear_sma)
    current_spy = spy_closes[-1] if spy_closes else 0.0
    is_bear_market = sma_spy is not None and current_spy < sma_spy

    momentum_scores: dict[str, float] = {}
    min_required_bars = max(momentum_period, skip_recent)
    for symbol, data in df_map.items():
        closes = data.get("close", [])
        if len(closes) < min_required_bars:
            logger.debug(
                "Rotação sectorial ignorou %s: %d barras < mínimo %d.",
                symbol,
                len(closes),
                min_required_bars,
            )
            continue
        price_12m_ago = closes[-momentum_period]
        price_1m_ago = closes[-skip_recent]
        if price_12m_ago <= 0:
            logger.debug(
                "Rotação sectorial ignorou %s: preço de referência inválido %.4f.",
                symbol,
                price_12m_ago,
            )
            continue
        momentum_scores[symbol] = (price_1m_ago - price_12m_ago) / price_12m_ago

    if not momentum_scores:
        logger.info("Rotação sectorial sem acção: dados insuficientes.")
        return _flat_signal({"reason": "insufficient_data"})

    sorted_sectors = sorted(
        momentum_scores,
        key=momentum_scores.get,
        reverse=True,
    )

    if is_bear_market:
        target_allocations = [symbol for symbol in sorted_sectors if symbol in safe_havens][:top_n]
        if not target_allocations:
            target_allocations = [symbol for symbol in safe_havens if symbol in df_map][:top_n]
        logger.info(
            "Rotação sectorial em bear market: safe havens seleccionados=%s.",
            target_allocations,
        )
    else:
        target_allocations = sorted_sectors[:top_n]
        logger.info(
            "Rotação sectorial em bull/neutral: top-%d=%s.",
            top_n,
            target_allocations,
        )

    if not target_allocations:
        logger.info("Rotação sectorial sem acção: sem sectores válidos.")
        return _flat_signal({"reason": "no_valid_sectors"})

    return {
        "signal": "LONG",
        "confidence": 3,
        "entry_price": 0.0,
        "stop_loss": 0.0,
        "take_profit": 0.0,
        "position_size": 0.0,
        "metadata": {
            "type": "rotation",
            "allocations": target_allocations,
            "bear_regime": is_bear_market,
            "scores": {
                symbol: round(momentum_scores.get(symbol, 0.0), 4)
                for symbol in target_allocations
            },
            "module": "sector_rotation",
        },
    }


def _flat_signal(metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    """Retorna sinal FLAT (sem acção)."""
    return {
        "signal": "FLAT",
        "confidence": 0,
        "entry_price": 0.0,
        "stop_loss": 0.0,
        "take_profit": 0.0,
        "position_size": 0.0,
        "metadata": metadata or {},
    }

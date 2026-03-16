"""Módulo 10: Fixed Income & Bonds — MR táctico + hedge defensivo.

Duas vertentes:
1. MR táctico: KAIRI em TLT/IEF quando bonds estão sobrevendidos
2. Rotação defensiva: SPY < SMA200 + VIX > 25 → rodar para bonds

Anti-whipsaw: mínimo 10 dias em modo defensivo.

Fase de capital: 2+ (€2-10k)
"""

from __future__ import annotations

import logging
import math
from typing import Any

from src.signal_engine import calculate_atr, calculate_rsi, calculate_sma

logger = logging.getLogger(__name__)


def detect_stock_bond_correlation_regime(
    spy_closes: list[float],
    tlt_closes: list[float],
    lookback: int = 60,
) -> str:
    """Detecta o regime de correlação stocks/bonds."""
    min_len = min(len(spy_closes), len(tlt_closes))
    if min_len < lookback + 1:
        return "transitioning"

    spy_ret = [
        spy_closes[i] / spy_closes[i - 1] - 1.0
        for i in range(-lookback, 0)
    ]
    tlt_ret = [
        tlt_closes[i] / tlt_closes[i - 1] - 1.0
        for i in range(-lookback, 0)
    ]

    n = len(spy_ret)
    mean_s = sum(spy_ret) / n
    mean_t = sum(tlt_ret) / n
    cov = sum((a - mean_s) * (b - mean_t) for a, b in zip(spy_ret, tlt_ret)) / n
    std_s = math.sqrt(sum((a - mean_s) ** 2 for a in spy_ret) / n)
    std_t = math.sqrt(sum((b - mean_t) ** 2 for b in tlt_ret) / n)

    if std_s == 0.0 or std_t == 0.0:
        return "transitioning"

    corr = cov / (std_s * std_t)
    if corr < -0.2:
        return "negative"
    if corr > 0.2:
        return "positive"
    return "transitioning"


def check_defensive_rotation_trigger(
    spy_closes: list[float],
    vix_proxy: float | None,
    correlation_regime: str,
    defensive_state: dict[str, Any],
    config: dict[str, Any],
) -> str:
    """Verifica se deve entrar/sair do modo defensivo."""
    sma200 = calculate_sma(spy_closes, 200)
    if sma200 is None:
        return "NO_CHANGE"

    spy = spy_closes[-1]
    bear_vix = float(config.get("bear_vix_proxy", 25.0))
    min_days = int(config.get("defensive_min_days", 10))

    bear_condition = spy < sma200 and vix_proxy > bear_vix
    mode = defensive_state.get("mode", "NORMAL")

    if mode == "NORMAL":
        if bear_condition and correlation_regime == "negative":
            return "ENTER_DEFENSIVE"
    elif mode == "DEFENSIVE":
        days = int(defensive_state.get("days_in_defensive", 0))
        if spy > sma200 and days >= min_days:
            return "EXIT_DEFENSIVE"

    return "NO_CHANGE"


def bond_mr_signal(
    symbol: str,
    closes: list[float],
    highs: list[float],
    lows: list[float],
    spy_closes: list[float],
    tlt_closes: list[float],
    vix_proxy: float | None,
    defensive_state: dict[str, Any],
    config: dict[str, Any],
) -> dict[str, Any]:
    """Gera sinal MR táctico para bonds + rotação defensiva."""
    thresholds = config.get("kairi_thresholds", {})
    kairi_threshold = float(thresholds.get(symbol, -15.0))
    sma_lookback = 25

    if len(closes) < 200:
        logger.info(
            "Bond Hedge sem acção para %s: dados insuficientes (%d < 200).",
            symbol,
            len(closes),
        )
        return _flat_signal({"reason": "insufficient_data"})

    if vix_proxy is None:
        logger.info(
            "Bond Hedge sem acção para %s: vix_proxy indisponível.",
            symbol,
        )
        return _flat_signal({"reason": "vix_proxy_unavailable"})

    corr_regime = detect_stock_bond_correlation_regime(
        spy_closes,
        tlt_closes,
        int(config.get("correlation_lookback", 60)),
    )
    defensive_action = check_defensive_rotation_trigger(
        spy_closes,
        vix_proxy,
        corr_regime,
        defensive_state,
        config,
    )

    if defensive_action == "EXIT_DEFENSIVE":
        logger.info("Bond Hedge em %s: saída do modo defensivo.", symbol)
        return _flat_signal(
            {
                "reason": "exit_defensive",
                "corr_regime": corr_regime,
                "defensive_action": defensive_action,
            }
        )

    if corr_regime == "positive":
        logger.info(
            "Bond Hedge sem acção para %s: correlação stocks/bonds positiva.",
            symbol,
        )
        return _flat_signal({"reason": "positive_stock_bond_correlation"})

    if (
        defensive_action == "ENTER_DEFENSIVE"
        or defensive_state.get("mode") == "DEFENSIVE"
    ):
        atr = calculate_atr(highs, lows, closes, 14)
        if atr is None or atr <= 0:
            logger.info("Bond Hedge sem acção para %s: ATR inválido.", symbol)
            return _flat_signal({"reason": "atr_invalid"})

        price = closes[-1]
        signal = {
            "signal": "LONG",
            "confidence": 3,
            "entry_price": price,
            "stop_loss": round(price - 1.0 * atr, 6),
            "take_profit": round(price + 2.5 * atr, 6),
            "position_size": float(config.get("max_allocation_pct", 0.20)),
            "metadata": {
                "type": "defensive_rotation",
                "corr_regime": corr_regime,
                "defensive_action": defensive_action,
                "module": "bond_mr_hedge",
            },
        }
        logger.info(
            "Bond Hedge gerou LONG defensivo para %s (acção=%s).",
            symbol,
            defensive_action,
        )
        return signal

    price = closes[-1]
    sma = calculate_sma(closes, sma_lookback)
    if sma is None or sma <= 0:
        logger.info("Bond Hedge sem acção para %s: SMA inválida.", symbol)
        return _flat_signal({"reason": "sma_invalid"})

    kairi = ((price - sma) / sma) * 100.0
    if kairi > kairi_threshold:
        logger.info(
            "Bond Hedge sem acção para %s: KAIRI %.4f acima do threshold %.4f.",
            symbol,
            kairi,
            kairi_threshold,
        )
        return _flat_signal({"reason": "kairi_above_threshold", "kairi": kairi})

    rsi14 = calculate_rsi(closes, 14)
    atr = calculate_atr(highs, lows, closes, 14)
    if atr is None or atr <= 0:
        logger.info("Bond Hedge sem acção para %s: ATR inválido.", symbol)
        return _flat_signal({"reason": "atr_invalid"})

    confidence = 2
    if rsi14 is not None and rsi14 < 30:
        confidence = 3

    signal = {
        "signal": "LONG",
        "confidence": confidence,
        "entry_price": price,
        "stop_loss": round(price - 1.0 * atr, 6),
        "take_profit": round(sma, 6),
        "position_size": 0.0,
        "metadata": {
            "type": "tactical_mr",
            "kairi": round(kairi, 4),
            "threshold": kairi_threshold,
            "corr_regime": corr_regime,
            "module": "bond_mr_hedge",
        },
    }
    logger.info(
        "Bond Hedge gerou LONG táctico para %s com KAIRI=%.4f.",
        symbol,
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

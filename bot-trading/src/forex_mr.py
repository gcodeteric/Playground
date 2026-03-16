"""Módulo 1: Forex Mean Reversion.

Detecta oportunidades de mean reversion em pares FX quando o preço
desvia significativamente da média (z-score ≤ -2.0) com confirmação
de regime ranging (ADX < 20, CHOP > 55).

Gate de activação: ADX < 20 (adormece quando ADX ≥ 20)
Fase de capital: 2+ (€2-10k)
"""

from __future__ import annotations

import logging
from typing import Any

from src.signal_engine import (
    calculate_adx,
    calculate_atr,
    calculate_choppiness_index,
    calculate_rsi,
    calculate_sma,
)

logger = logging.getLogger(__name__)


class ForexRegimeSwitch:
    """State machine para alternar entre MR e Breakout em FX.

    ADX < 20 → forex_mr activo
    ADX 20-25 → zona morta (nenhum opera)
    ADX > 25 → forex_breakout activo

    Histerese: quando muda de regime com posição aberta,
    aplica tighten_stop (apertar stop 50%) em vez de fechar.
    """

    ADX_MR_MAX: float = 20.0
    ADX_DEAD_MAX: float = 25.0

    def get_active_module(self, adx: float) -> str:
        """Determina qual módulo FX deve operar com base no ADX."""
        if adx < self.ADX_MR_MAX:
            return "forex_mr"
        if adx > self.ADX_DEAD_MAX:
            return "forex_breakout"
        return "none"

    def handle_open_position(self, position_module: str, new_regime: str) -> str:
        """Política quando o regime muda com posição aberta."""
        if position_module == "forex_mr" and new_regime == "forex_breakout":
            return "tighten_stop"
        if position_module == "forex_breakout" and new_regime == "forex_mr":
            return "hold"
        return "hold"


def forex_mr_signal(
    closes: list[float],
    highs: list[float],
    lows: list[float],
    config: dict[str, Any],
    now_utc_hour: int = 12,
) -> dict[str, Any]:
    """Gera sinal de mean reversion para pares FX."""
    sma_period = int(config.get("sma_period", 20))
    vol_lookback = int(config.get("vol_lookback", 60))
    z_entry = float(config.get("z_entry", -2.0))
    rsi_period = int(config.get("rsi_period", 2))
    rsi_entry = float(config.get("rsi_entry", 10))
    adx_max = float(config.get("adx_ranging_max", 20.0))
    chop_min = float(config.get("chop_min_ranging", 55.0))
    stop_mult = float(config.get("stop_atr_mult_fx", 1.5))

    n = min(len(closes), len(highs), len(lows))
    if n < vol_lookback:
        logger.info("Forex MR sem acção: dados insuficientes (%d < %d).", n, vol_lookback)
        return _flat_signal({"reason": "insufficient_data"})

    close = closes[-1]
    sma = calculate_sma(closes, sma_period)
    if sma is None or sma <= 0:
        logger.info("Forex MR sem acção: SMA inválida.")
        return _flat_signal({"reason": "sma_invalid"})

    window = closes[-vol_lookback:]
    mean_value = sum(window) / len(window)
    variance = sum((value - mean_value) ** 2 for value in window) / len(window)
    std_value = variance ** 0.5
    z_score = (close - sma) / std_value if std_value > 0 else 0.0

    rsi2 = calculate_rsi(closes, period=rsi_period)
    if z_score > z_entry or rsi2 is None or rsi2 > rsi_entry:
        logger.info(
            "Forex MR sem acção: condições base falharam (z=%.4f, RSI2=%s).",
            z_score,
            f"{rsi2:.2f}" if rsi2 is not None else "None",
        )
        return _flat_signal(
            {"reason": "base_conditions_not_met", "z_score": z_score, "rsi2": rsi2}
        )

    atr = calculate_atr(highs, lows, closes, 14)
    if atr is None or atr <= 0:
        logger.info("Forex MR sem acção: ATR inválido.")
        return _flat_signal({"reason": "atr_invalid"})

    adx = calculate_adx(highs, lows, closes, 14)
    chop = calculate_choppiness_index(highs, lows, closes, 14)
    if adx >= adx_max or chop <= chop_min:
        logger.info(
            "Forex MR bloqueado por regime não ranging (ADX=%.2f, CHOP=%.2f).",
            adx,
            chop,
        )
        return _flat_signal(
            {
                "reason": "regime_not_ranging",
                "adx": round(adx, 2),
                "chop": round(chop, 2),
            }
        )

    confirmations = 0

    if len(closes) >= 10:
        price_lower = closes[-1] < min(closes[-10:-1])
        rsi_recent = [
            calculate_rsi(closes[: idx + 1], rsi_period)
            for idx in range(len(closes) - 5, len(closes))
        ]
        rsi_valid = [value for value in rsi_recent if value is not None]
        rsi_higher = len(rsi_valid) >= 2 and rsi_valid[-1] > rsi_valid[0]
        if price_lower and rsi_higher:
            confirmations += 1

    if len(highs) >= 10 and len(lows) >= 10:
        current_range = highs[-1] - lows[-1]
        avg_range_10 = sum(
            highs[idx] - lows[idx] for idx in range(len(highs) - 10, len(highs))
        ) / 10.0
        if current_range < avg_range_10 * 0.8:
            confirmations += 1

    if 7 <= now_utc_hour <= 17:
        confirmations += 1

    confirmations += 1

    confidence = min(confirmations, 3)
    if confidence < 2:
        logger.info(
            "Forex MR sem acção: confirmações insuficientes (%d).",
            confirmations,
        )
        return _flat_signal(
            {"reason": "insufficient_confirmations", "confirmations": confirmations}
        )

    signal = {
        "signal": "LONG",
        "confidence": confidence,
        "entry_price": close,
        "stop_loss": round(close - stop_mult * atr, 6),
        "take_profit": round(sma, 6),
        "position_size": 0.0,
        "metadata": {
            "z_score": round(z_score, 4),
            "rsi2": round(rsi2, 2) if rsi2 is not None else None,
            "adx": round(adx, 2),
            "chop": round(chop, 2),
            "confirmations": confirmations,
            "module": "forex_mr",
        },
    }
    logger.info(
        "Forex MR gerou sinal LONG com confidence=%d (z=%.4f, RSI2=%.2f).",
        confidence,
        z_score,
        rsi2,
    )
    return signal


def forex_kill_switches(
    highs: list[float],
    lows: list[float],
    closes: list[float],
    now_weekday: int,
    config: dict[str, Any],
) -> tuple[bool, list[str]]:
    """Kill switches específicos para FX."""
    reasons: list[str] = []
    atr = calculate_atr(highs, lows, closes, 14)
    if atr is None or atr <= 0:
        return True, ["atr_invalid"]

    today_range = highs[-1] - lows[-1]
    max_ratio = float(config.get("max_spread_atr_ratio", 3.0))
    if today_range / atr > max_ratio:
        reasons.append("spread_widening")

    if now_weekday == 0 and len(closes) >= 2:
        gap = abs(closes[-1] - closes[-2])
        max_gap = float(config.get("weekend_gap_atr_mult", 1.5)) * atr
        if gap > max_gap:
            reasons.append("weekend_gap")

    blocked = len(reasons) > 0
    if blocked:
        logger.warning("Forex MR bloqueado por kill switches: %s", reasons)
    return blocked, reasons


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

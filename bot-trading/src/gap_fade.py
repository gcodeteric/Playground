"""Módulo 7: Overnight Gap Fade.

Opera gap fills quando o preço abre significativamente acima/abaixo
do fecho anterior. Faz fade (aposta no fecho do gap) em gaps de
magnitude moderada (0.5-2.5 ATR).

Fase de capital: 1+ (€0-2k)
"""

from __future__ import annotations

import logging
from typing import Any

from src.signal_engine import calculate_atr

logger = logging.getLogger(__name__)


def classify_gap(
    closes: list[float],
    opens: list[float],
    highs: list[float],
    lows: list[float],
    config: dict[str, Any],
) -> dict[str, Any]:
    """Classifica o gap de abertura e calcula probabilidade de fill.

    Magnitude do gap em ATR determina a probabilidade de fill:
    - < 0.5 ATR: ~85% fill rate → operar
    - 0.5-1.0 ATR: ~75% fill rate → operar com confidence 2+
    - 1.0-2.0 ATR: ~60% fill rate → operar só com confidence 3
    - > 2.0 ATR: ~40% fill rate → evitar (gap continuation)

    Args:
        closes: Preços de fecho (mín 15 barras).
        opens: Preços de abertura.
        highs: Preços máximos.
        lows: Preços mínimos.
        config: GAP_FADE_CONFIG.

    Returns:
        Dicionário com classificação do gap.
    """
    if len(closes) < 15 or len(opens) < 2:
        logger.debug("Gap fade sem classificação: dados insuficientes.")
        return {"valid": False, "reason": "insufficient_data"}

    prev_close = closes[-2]
    today_open = opens[-1]
    atr14 = calculate_atr(highs, lows, closes, 14)

    if atr14 is None or atr14 <= 0:
        logger.info("Gap fade sem classificação: ATR inválido.")
        return {"valid": False, "reason": "atr_invalid"}

    if prev_close <= 0:
        logger.info("Gap fade sem classificação: fecho anterior inválido.")
        return {"valid": False, "reason": "prev_close_invalid"}

    gap_pct = (today_open - prev_close) / prev_close * 100.0
    gap_atr = abs(today_open - prev_close) / atr14

    if gap_atr < 0.5:
        fill_probability = 0.85
    elif gap_atr < 1.0:
        fill_probability = 0.75
    elif gap_atr < 2.0:
        fill_probability = 0.60
    else:
        fill_probability = 0.40

    min_gap = float(config.get("min_gap_atr", 0.5))
    max_gap = float(config.get("max_gap_atr", 2.5))
    is_high_prob = min_gap <= gap_atr <= max_gap

    result = {
        "valid": True,
        "gap_type": "up" if gap_pct > 0 else "down",
        "magnitude_pct": round(gap_pct, 4),
        "magnitude_atr": round(gap_atr, 4),
        "fill_probability": fill_probability,
        "is_high_prob": is_high_prob,
        "prev_close": prev_close,
        "today_open": today_open,
        "atr14": atr14,
    }
    logger.debug("Gap classificado: %s", result)
    return result


def gap_fade_signal(
    closes: list[float],
    opens: list[float],
    highs: list[float],
    lows: list[float],
    config: dict[str, Any],
) -> dict[str, Any]:
    """Gera sinal de gap fade se as condições forem satisfeitas.

    Lógica:
    - Gap up → SHORT (fade para prev_close)
    - Gap down → LONG (fade para prev_close)
    - Stop: extremo do gap + 0.5 ATR
    - TP: prev_close (target do fill)

    Args:
        closes: Preços de fecho.
        opens: Preços de abertura.
        highs: Preços máximos.
        lows: Preços mínimos.
        config: GAP_FADE_CONFIG.

    Returns:
        Signal dict no formato padrão do bot.
    """
    gap_info = classify_gap(closes, opens, highs, lows, config)

    if not gap_info.get("valid") or not gap_info.get("is_high_prob"):
        logger.info("Gap fade sem acção: gap não transaccionável.")
        return _flat_signal({"reason": "gap_not_tradeable", "gap_info": gap_info})

    min_prob = float(config.get("min_fill_probability", 0.60))
    if float(gap_info["fill_probability"]) < min_prob:
        logger.info(
            "Gap fade sem acção: probabilidade de fill %.2f abaixo de %.2f.",
            gap_info["fill_probability"],
            min_prob,
        )
        return _flat_signal({"reason": "fill_prob_too_low", "gap_info": gap_info})

    atr = float(gap_info["atr14"])
    prev_close = float(gap_info["prev_close"])
    today_open = float(gap_info["today_open"])

    gap_atr = float(gap_info["magnitude_atr"])
    if gap_atr < 1.0:
        confidence = 3
    elif gap_atr < 2.0:
        confidence = 2
    else:
        confidence = 1

    if confidence < 2:
        logger.info("Gap fade sem acção: confidence=%d abaixo do mínimo.", confidence)
        return _flat_signal({"reason": "confidence_too_low", "gap_info": gap_info})

    if gap_info["gap_type"] == "up":
        signal = {
            "signal": "SHORT",
            "confidence": confidence,
            "entry_price": today_open,
            "stop_loss": round(today_open + 0.5 * atr, 6),
            "take_profit": prev_close,
            "position_size": 0.0,
            "metadata": {
                "type": "gap_fade",
                "gap_info": gap_info,
                "module": "gap_fade",
            },
        }
    else:
        signal = {
            "signal": "LONG",
            "confidence": confidence,
            "entry_price": today_open,
            "stop_loss": round(today_open - 0.5 * atr, 6),
            "take_profit": prev_close,
            "position_size": 0.0,
            "metadata": {
                "type": "gap_fade",
                "gap_info": gap_info,
                "module": "gap_fade",
            },
        }

    logger.info(
        "Gap fade gerou sinal %s com confidence=%d.",
        signal["signal"],
        signal["confidence"],
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

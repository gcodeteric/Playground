"""Modulo 9: Options Premium Selling (Cash-Secured Puts).

Vende puts OTM em SPY/QQQ/IWM quando IV Rank >= 30 e nao ha earnings
proximos. Implementacao Black-Scholes SEM scipy -- usa math.erfc para
aproximacao de norm.cdf (Abramowitz & Stegun, erro < 1.5e-7).

Regras de saida:
- 50% lucro -> fechar imediatamente
- 21 DTE restantes -> fechar (gamma risk)
- IV Rank cai < 20 -> fechar (premium esgotado)

Fase de capital: 3+ (EUR 25k minimo -- cash-secured exige colateral)
"""

from __future__ import annotations

import logging
import math
from typing import Any

logger = logging.getLogger(__name__)


def _norm_cdf(x: float) -> float:
    """CDF da normal padrao via math.erfc."""
    return 0.5 * math.erfc(-x / math.sqrt(2.0))


def _norm_pdf(x: float) -> float:
    """PDF da normal padrao."""
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


class BlackScholes:
    """Black-Scholes-Merton para opcoes europeias."""

    @staticmethod
    def calculate_greeks(
        S: float,
        K: float,
        T: float,
        r: float,
        sigma: float,
        option_type: str = "put",
    ) -> dict[str, float]:
        """Calcula preco e greeks BSM."""
        if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
            return {
                "price": 0.0,
                "delta": 0.0,
                "gamma": 0.0,
                "theta": 0.0,
                "vega": 0.0,
            }

        d1 = (
            math.log(S / K) + (r + 0.5 * sigma**2) * T
        ) / (sigma * math.sqrt(T))
        d2 = d1 - sigma * math.sqrt(T)

        if option_type == "call":
            price = S * _norm_cdf(d1) - K * math.exp(-r * T) * _norm_cdf(d2)
            delta = _norm_cdf(d1)
            theta = (
                -(S * _norm_pdf(d1) * sigma) / (2.0 * math.sqrt(T))
                - r * K * math.exp(-r * T) * _norm_cdf(d2)
            ) / 365.0
        else:
            price = K * math.exp(-r * T) * _norm_cdf(-d2) - S * _norm_cdf(-d1)
            delta = _norm_cdf(d1) - 1.0
            theta = (
                -(S * _norm_pdf(d1) * sigma) / (2.0 * math.sqrt(T))
                + r * K * math.exp(-r * T) * _norm_cdf(-d2)
            ) / 365.0

        gamma = _norm_pdf(d1) / (S * sigma * math.sqrt(T))
        vega = S * _norm_pdf(d1) * math.sqrt(T) / 100.0

        return {
            "price": round(price, 6),
            "delta": round(delta, 6),
            "gamma": round(gamma, 6),
            "theta": round(theta, 6),
            "vega": round(vega, 6),
        }


def should_sell_premium(
    regime: str,
    iv_rank: float,
    days_to_earnings: int,
    vix_proxy: float | None,
    config: dict[str, Any],
) -> bool:
    """Gates para venda de premium: True = pode vender."""
    if vix_proxy is None:
        return False
    if regime not in ("SIDEWAYS", "BULL"):
        return False
    if iv_rank < float(config.get("iv_rank_min", 30)):
        return False
    if days_to_earnings <= int(config.get("min_days_to_earnings", 21)):
        return False
    if vix_proxy >= float(config.get("vix_max_sell", 30)):
        return False
    return True


def csp_signal(
    symbol: str,
    spot: float,
    iv_rank: float,
    iv_implied: float,
    regime: str,
    days_to_earnings: int,
    vix_proxy: float | None,
    config: dict[str, Any],
    risk_free_rate: float = 0.05,
) -> dict[str, Any]:
    """Gera sinal de Cash-Secured Put."""
    allowed = config.get("allowed_symbols", [])
    if symbol not in allowed:
        logger.info("Options Premium sem acção para %s: símbolo não permitido.", symbol)
        return _flat_signal({"reason": "symbol_not_allowed"})

    if vix_proxy is None:
        logger.info("Options Premium sem acção para %s: vix_proxy indisponível.", symbol)
        return _flat_signal({"reason": "vix_proxy_unavailable"})

    if not should_sell_premium(
        regime,
        iv_rank,
        days_to_earnings,
        vix_proxy,
        config,
    ):
        logger.info("Options Premium sem acção para %s: gates bloqueados.", symbol)
        return _flat_signal({"reason": "premium_gates_blocked"})

    target_delta = float(config.get("target_delta", 0.15))
    dte = int(config.get("target_dte", 45))
    T = dte / 365.0
    sigma = iv_implied / 100.0 if iv_implied > 1.0 else iv_implied

    lo, hi = spot * 0.70, spot * 0.99
    strike = spot * (1.0 - target_delta)
    for _ in range(20):
        mid = (lo + hi) / 2.0
        greeks_mid = BlackScholes.calculate_greeks(
            spot,
            mid,
            T,
            risk_free_rate,
            sigma,
            "put",
        )
        delta_abs = abs(greeks_mid["delta"])
        if delta_abs > target_delta:
            hi = mid
        else:
            lo = mid
        strike = mid

    greeks = BlackScholes.calculate_greeks(
        spot,
        strike,
        T,
        risk_free_rate,
        sigma,
        "put",
    )

    signal = {
        "signal": "SELL_PUT",
        "confidence": 2,
        "entry_price": greeks["price"],
        "stop_loss": 0.0,
        "take_profit": round(
            greeks["price"] * (1.0 - float(config.get("close_at_profit_pct", 0.50))),
            6,
        ),
        "position_size": 0.0,
        "metadata": {
            "type": "csp",
            "strike": round(strike, 2),
            "dte": dte,
            "iv_rank": iv_rank,
            "greeks": greeks,
            "module": "options_premium",
        },
    }
    logger.info(
        "Options Premium gerou SELL_PUT para %s com strike %.2f e delta %.4f.",
        symbol,
        signal["metadata"]["strike"],
        greeks["delta"],
    )
    return signal


def check_csp_exit(
    current_price: float,
    credit_received: float,
    strike: float,
    dte_remaining: int,
    iv_rank_current: float,
    config: dict[str, Any],
) -> dict[str, Any]:
    """Verifica se deve fechar a posição CSP."""
    close_profit = float(config.get("close_at_profit_pct", 0.50))
    close_dte = int(config.get("close_at_dte", 21))

    # Prioridade conservadora: reduzir gamma risk antes de avaliar lucro.
    if dte_remaining <= close_dte:
        return {"action": "CLOSE", "reason": f"dte_low_{dte_remaining}"}

    if iv_rank_current < 20:
        return {"action": "CLOSE", "reason": "iv_rank_low"}

    intrinsic_value = max(strike - current_price, 0.0)
    profit_pct = 1.0 - (intrinsic_value / credit_received) if credit_received > 0 else 0.0
    if profit_pct >= close_profit:
        return {"action": "CLOSE", "reason": f"profit_target_{round(profit_pct * 100)}pct"}

    return {"action": "HOLD", "reason": "within_parameters"}


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

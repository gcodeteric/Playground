"""
Pre-trade gate determinístico para novas entradas.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from numbers import Real
from typing import Any, Mapping


def _is_finite_numeric(value: Any) -> bool:
    """Valida se um valor numérico crítico é finito e utilizável."""
    if isinstance(value, bool):
        return False
    if not isinstance(value, Real):
        return False
    return math.isfinite(float(value))


def critical_inputs_are_finite(inputs: Mapping[str, Any]) -> bool:
    """Confirma que todos os inputs críticos fornecidos são finitos."""
    return all(_is_finite_numeric(value) for value in inputs.values())


@dataclass(frozen=True, slots=True)
class PreTradeGate:
    """Objeto puro de decisão para admissão pré-trade."""

    session_ok: bool
    data_fresh: bool
    finite_inputs_ok: bool
    warmup_ok: bool
    quantity_ok: bool
    risk_ok: bool
    notional_ok: bool | None = None
    size_ok: bool | None = None
    affordability_ok: bool | None = None
    details: dict[str, Any] = field(default_factory=dict)
    risk_rejection_reason: str = ""

    def implemented_flags(self) -> dict[str, bool]:
        """Devolve as flags activas neste gate."""
        flags = {
            "session_ok": self.session_ok,
            "data_fresh": self.data_fresh,
            "finite_inputs_ok": self.finite_inputs_ok,
            "warmup_ok": self.warmup_ok,
            "quantity_ok": self.quantity_ok,
            "risk_ok": self.risk_ok,
        }
        if self.notional_ok is not None:
            flags["notional_ok"] = self.notional_ok
        if self.size_ok is not None:
            flags["size_ok"] = self.size_ok
        if self.affordability_ok is not None:
            flags["affordability_ok"] = self.affordability_ok
        return flags

    def is_admitted(self) -> bool:
        """Indica se a nova entrada pode prosseguir."""
        return all(self.implemented_flags().values())

    def rejection_reasons(self) -> list[str]:
        """Lista as flags que falharam."""
        return [name for name, passed in self.implemented_flags().items() if not passed]

    def as_dict(self) -> dict[str, Any]:
        """Serializa o gate para logging/observabilidade."""
        payload = asdict(self)
        payload["implemented_flags"] = self.implemented_flags()
        payload["rejection_reasons"] = self.rejection_reasons()
        return payload


def build_pre_trade_gate(
    *,
    session_ok: bool,
    data_fresh: bool,
    warmup_ok: bool,
    critical_inputs: Mapping[str, Any],
    quantity_ok: bool,
    risk_ok: bool,
    notional_ok: bool | None = None,
    size_ok: bool | None = None,
    affordability_ok: bool | None = None,
    details: Mapping[str, Any] | None = None,
    risk_rejection_reason: str = "",
) -> PreTradeGate:
    """Constrói um gate explícito e sem side effects."""
    serialized_details = dict(details or {})
    serialized_details["critical_inputs"] = dict(critical_inputs)
    return PreTradeGate(
        session_ok=session_ok,
        data_fresh=data_fresh,
        finite_inputs_ok=critical_inputs_are_finite(critical_inputs),
        warmup_ok=warmup_ok,
        quantity_ok=quantity_ok,
        risk_ok=risk_ok,
        notional_ok=notional_ok,
        size_ok=size_ok,
        affordability_ok=affordability_ok,
        details=serialized_details,
        risk_rejection_reason=risk_rejection_reason,
    )

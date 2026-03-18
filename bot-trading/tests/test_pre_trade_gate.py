from __future__ import annotations

from src.pre_trade_gate import build_pre_trade_gate


def _build_gate(**overrides):
    payload = {
        "session_ok": True,
        "data_fresh": True,
        "warmup_ok": True,
        "critical_inputs": {"entry_price": 100.0, "atr": 2.0},
        "quantity_ok": True,
        "risk_ok": True,
    }
    payload.update(overrides)
    return build_pre_trade_gate(**payload)


def test_gate_rejects_stale_price():
    gate = _build_gate(data_fresh=False)

    assert gate.data_fresh is False
    assert gate.is_admitted() is False
    assert "data_fresh" in gate.rejection_reasons()


def test_gate_rejects_nan_entry_price():
    gate = _build_gate(critical_inputs={"entry_price": float("nan"), "atr": 2.0})

    assert gate.finite_inputs_ok is False
    assert gate.is_admitted() is False
    assert "finite_inputs_ok" in gate.rejection_reasons()


def test_gate_rejects_nan_indicator():
    gate = _build_gate(critical_inputs={"entry_price": 100.0, "atr": float("nan")})

    assert gate.finite_inputs_ok is False
    assert gate.is_admitted() is False
    assert "finite_inputs_ok" in gate.rejection_reasons()


def test_gate_rejects_zero_quantity():
    gate = _build_gate(quantity_ok=False)

    assert gate.quantity_ok is False
    assert gate.is_admitted() is False
    assert "quantity_ok" in gate.rejection_reasons()


def test_gate_admits_valid_order():
    gate = _build_gate()

    assert gate.is_admitted() is True
    assert gate.rejection_reasons() == []


def test_gate_rejection_reasons_lists_all_failures():
    gate = _build_gate(
        session_ok=False,
        data_fresh=False,
        quantity_ok=False,
        risk_ok=False,
        critical_inputs={"entry_price": float("nan"), "atr": 2.0},
    )

    assert gate.is_admitted() is False
    assert gate.rejection_reasons() == [
        "session_ok",
        "data_fresh",
        "finite_inputs_ok",
        "quantity_ok",
        "risk_ok",
    ]

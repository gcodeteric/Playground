from __future__ import annotations

import datetime

import pytest
from ib_insync import Future

from src.contracts import build_contract, parse_watchlist_entry


def test_parse_future_entry_accepts_explicit_expiry_without_region():
    spec = parse_watchlist_entry("MES:FUT:CME:USD:202406")

    assert spec.symbol == "MES"
    assert spec.exchange == "CME"
    assert spec.currency == "USD"
    assert spec.region == "US"
    assert spec.expiry == "202406"


def test_build_contract_uses_explicit_future_expiry(monkeypatch):
    monkeypatch.setattr(
        "src.contracts._today_utc_date",
        lambda: datetime.date(2026, 3, 10),
    )
    spec = parse_watchlist_entry("MES:FUT:CME:USD:202406")

    contract = build_contract(spec)

    assert isinstance(contract, Future)
    assert contract.symbol == "MES"
    assert contract.lastTradeDateOrContractMonth == "202406"


def test_build_contract_blocks_auto_future_resolution_near_rollover(monkeypatch):
    monkeypatch.setattr(
        "src.contracts._today_utc_date",
        lambda: datetime.date(2026, 3, 10),
    )
    spec = parse_watchlist_entry("MES:FUT:CME:USD")

    with pytest.raises(ValueError, match="Auto-resolução de futures bloqueada"):
        build_contract(spec)

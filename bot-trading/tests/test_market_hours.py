from __future__ import annotations

from datetime import UTC, datetime

from src.contracts import parse_watchlist_entry
from src.market_hours import get_asset_type, get_session_state, is_market_open, minutes_to_close


def test_us_equity_open_session():
    spec = parse_watchlist_entry("AAPL")
    now = datetime(2026, 3, 16, 15, 0, tzinfo=UTC)  # Segunda-feira
    state = get_session_state(spec, now)
    assert state.is_open is True
    assert state.can_open_new_grid is True
    assert get_asset_type(spec) == "STK_US"
    assert is_market_open(spec.display, get_asset_type(spec), now) is True


def test_us_equity_preclose():
    spec = parse_watchlist_entry("AAPL")
    now = datetime(2026, 3, 16, 19, 57, tzinfo=UTC)
    state = get_session_state(spec, now)
    assert state.is_open is True
    assert state.is_pre_close is True
    assert state.can_open_new_grid is False
    assert minutes_to_close(spec.display, get_asset_type(spec), now) < 5


def test_us_equity_holiday_is_closed():
    spec = parse_watchlist_entry("AAPL")
    now = datetime(2026, 12, 25, 15, 0, tzinfo=UTC)  # Natal
    state = get_session_state(spec, now)
    assert state.is_open is False
    assert state.status == "FECHADO_FERIADO"


def test_us_equity_dst_transition_updates_open_hour():
    spec = parse_watchlist_entry("AAPL")
    before_dst = datetime(2026, 3, 6, 15, 0, tzinfo=UTC)
    after_dst = datetime(2026, 3, 16, 15, 0, tzinfo=UTC)

    before_state = get_session_state(spec, before_dst)
    after_state = get_session_state(spec, after_dst)

    assert before_state.opens_at is not None
    assert after_state.opens_at is not None
    assert before_state.opens_at.hour == 14
    assert after_state.opens_at.hour == 13


def test_eu_equity_closed_after_hours():
    spec = parse_watchlist_entry("SAP:STK:XETRA:EUR")
    now = datetime(2026, 3, 16, 17, 0, tzinfo=UTC)
    state = get_session_state(spec, now)
    assert state.is_open is False


def test_forex_weekend_closed():
    spec = parse_watchlist_entry("EURUSD:FX:IDEALPRO")
    now = datetime(2026, 3, 14, 12, 0, tzinfo=UTC)  # Sabado
    state = get_session_state(spec, now)
    assert state.is_open is False


def test_micro_future_daily_pause():
    spec = parse_watchlist_entry("MES:FUT:CME:USD")
    now = datetime(2026, 3, 17, 22, 30, tzinfo=UTC)
    state = get_session_state(spec, now)
    assert state.is_open is False
    assert state.status == "PAUSA_DIARIA"
    assert get_asset_type(spec) == "FUT"

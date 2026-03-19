from __future__ import annotations

from datetime import UTC, datetime

from src.contracts import parse_watchlist_entry
from src import market_hours
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


def test_us_equity_fails_closed_when_calendar_missing(monkeypatch):
    spec = parse_watchlist_entry("AAPL")
    monkeypatch.setattr(market_hours, "get_calendar", None)

    state = get_session_state(spec, datetime(2026, 3, 16, 15, 0, tzinfo=UTC))

    assert state.is_open is False
    assert state.can_open_new_grid is False
    assert state.status == "CALENDARIO_INDISPONIVEL"


def test_us_equity_fails_closed_when_calendar_errors(monkeypatch):
    spec = parse_watchlist_entry("AAPL")

    def _boom(_name):
        raise RuntimeError("calendar offline")

    monkeypatch.setattr(market_hours, "get_calendar", _boom)

    state = get_session_state(spec, datetime(2026, 3, 16, 15, 0, tzinfo=UTC))

    assert state.is_open is False
    assert state.can_open_new_grid is False
    assert state.status == "CALENDARIO_INCONCLUSIVO"


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


def test_forex_preclose_tracks_new_york_dst():
    spec = parse_watchlist_entry("EURUSD:FX:IDEALPRO")
    before_dst = get_session_state(spec, datetime(2026, 3, 6, 21, 58, tzinfo=UTC))
    after_dst = get_session_state(spec, datetime(2026, 3, 20, 20, 58, tzinfo=UTC))

    assert before_dst.is_open is True
    assert before_dst.is_pre_close is True
    assert before_dst.closes_at is not None
    assert before_dst.closes_at.hour == 22

    assert after_dst.is_open is True
    assert after_dst.is_pre_close is True
    assert after_dst.closes_at is not None
    assert after_dst.closes_at.hour == 21


def test_micro_future_daily_pause():
    spec = parse_watchlist_entry("MES:FUT:CME:USD")
    now = datetime(2026, 3, 17, 21, 30, tzinfo=UTC)
    state = get_session_state(spec, now)
    assert state.is_open is False
    assert state.status == "PAUSA_DIARIA"
    assert get_asset_type(spec) == "FUT"


def test_micro_future_reopens_after_daily_pause():
    spec = parse_watchlist_entry("MES:FUT:CME:USD")
    now = datetime(2026, 3, 17, 22, 30, tzinfo=UTC)
    state = get_session_state(spec, now)
    assert state.is_open is True
    assert state.status == "ABERTO"


def test_micro_future_pause_tracks_chicago_dst():
    spec = parse_watchlist_entry("MES:FUT:CME:USD")
    before_dst = get_session_state(spec, datetime(2026, 3, 5, 22, 30, tzinfo=UTC))
    after_dst = get_session_state(spec, datetime(2026, 3, 17, 21, 30, tzinfo=UTC))

    assert before_dst.status == "PAUSA_DIARIA"
    assert after_dst.status == "PAUSA_DIARIA"
    assert before_dst.opens_at is not None
    assert after_dst.opens_at is not None
    assert before_dst.opens_at.hour == 23
    assert after_dst.opens_at.hour == 22

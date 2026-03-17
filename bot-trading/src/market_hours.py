"""
Gestao de sessoes de mercado por tipo de activo.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from math import floor
from typing import Any

from src.contracts import AssetType, InstrumentSpec

logger = logging.getLogger(__name__)

try:
    from pandas_market_calendars import get_calendar
except ImportError:  # pragma: no cover - depende do ambiente
    get_calendar = None


SCHEDULES: dict[str, tuple[str | None, str, str]] = {
    "STK_US": ("NYSE", "14:30", "21:00"),
    "STK_EU": ("XETRA", "08:00", "16:30"),
    "FOREX": (None, "22:00", "22:00"),
    "FUT": (None, "23:00", "22:00"),
}

_PRE_CLOSE_MINUTES = 5
_CALENDAR_ALIASES = {
    "XETRA": "XETR",
}


@dataclass(frozen=True, slots=True)
class SessionState:
    """Estado computado da sessao do mercado."""

    is_open: bool
    is_pre_close: bool
    status: str
    opens_at: datetime | None
    closes_at: datetime | None

    @property
    def can_open_new_grid(self) -> bool:
        """Indica se o bot pode abrir uma nova grid."""
        return self.is_open and not self.is_pre_close


def get_asset_type(contract: Any) -> str:
    """Auto-detecta o tipo de sessao a partir do contrato ou InstrumentSpec."""
    if isinstance(contract, InstrumentSpec):
        if contract.asset_type in (AssetType.STOCK, AssetType.ETF):
            return "STK_EU" if contract.region.upper() == "EU" else "STK_US"
        if contract.asset_type == AssetType.FOREX:
            return "FOREX"
        if contract.asset_type == AssetType.FUTURE:
            return "FUT"
        return "STK_US"

    sec_type = str(getattr(contract, "secType", "")).upper()
    if sec_type in {"STK", "ETF"}:
        exchange = str(getattr(contract, "exchange", "")).upper()
        currency = str(getattr(contract, "currency", "")).upper()
        if exchange in {"XETRA", "IBIS", "FWB"} or currency == "EUR":
            return "STK_EU"
        return "STK_US"
    if sec_type in {"CASH", "FX"}:
        return "FOREX"
    if sec_type == "FUT":
        return "FUT"
    return "STK_US"


def is_market_open(
    symbol: str,
    asset_type: str = "STK_US",
    now: datetime | None = None,
) -> bool:
    """Indica se o mercado esta aberto para o activo."""
    del symbol
    return _get_state_for_asset_type(asset_type, now or datetime.now(UTC)).is_open


def minutes_to_close(
    symbol: str,
    asset_type: str = "STK_US",
    now: datetime | None = None,
) -> int:
    """Devolve os minutos ate ao fecho da sessao actual."""
    del symbol
    state = _get_state_for_asset_type(asset_type, now or datetime.now(UTC))
    if state.closes_at is None:
        return 10**9 if state.is_open else -1
    return _minutes_between(state.closes_at, (now or datetime.now(UTC)).astimezone(UTC))


def get_session_state(
    spec: InstrumentSpec,
    now: datetime | None = None,
) -> SessionState:
    """Calcula o estado da sessao para um instrumento."""
    return _get_state_for_asset_type(
        get_asset_type(spec),
        now or datetime.now(UTC),
    )


def _get_state_for_asset_type(asset_type: str, now: datetime) -> SessionState:
    now_utc = now.astimezone(UTC)
    if asset_type in {"STK_US", "STK_EU"}:
        return _equity_session_state(asset_type, now_utc)
    if asset_type == "FOREX":
        return _forex_session_state(now_utc)
    if asset_type == "FUT":
        return _micro_future_session_state(now_utc)
    return SessionState(True, False, "SESSAO_DESCONHECIDA", None, None)


def _equity_session_state(asset_type: str, now: datetime) -> SessionState:
    calendar_name, open_str, close_str = SCHEDULES[asset_type]

    if get_calendar is not None and calendar_name:
        try:
            cal_name = _CALENDAR_ALIASES.get(calendar_name, calendar_name)
            cal = get_calendar(cal_name)
            schedule = cal.schedule(now.date(), now.date(), tz="UTC")
            if schedule.empty:
                return SessionState(False, False, "FECHADO_FERIADO", None, None)

            opens_at = schedule.iloc[0]["market_open"].to_pydatetime().replace(
                tzinfo=UTC,
            )
            closes_at = schedule.iloc[0]["market_close"].to_pydatetime().replace(
                tzinfo=UTC,
            )

            if now < opens_at:
                return SessionState(
                    False, False, "ANTES_ABERTURA", opens_at, closes_at,
                )
            if now >= closes_at:
                return SessionState(
                    False, False, "DEPOIS_FECHO", opens_at, closes_at,
                )

            mins = _minutes_between(closes_at, now)
            is_pre_close = mins <= _PRE_CLOSE_MINUTES
            return SessionState(
                True,
                is_pre_close,
                "PRE_CLOSE" if is_pre_close else "ABERTO",
                opens_at,
                closes_at,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("pandas falhou %s: %s. Fallback.", calendar_name, exc)

    # Fallback original (mantém compatibilidade)
    if not _is_trading_day(calendar_name, now):
        return SessionState(False, False, "FECHADO_FERIADO", None, None)
    open_time = _parse_time(open_str)
    close_time = _parse_time(close_str)
    opens_at = datetime.combine(now.date(), open_time, tzinfo=UTC)
    closes_at = datetime.combine(now.date(), close_time, tzinfo=UTC)

    if now < opens_at:
        return SessionState(False, False, "ANTES_ABERTURA", opens_at, closes_at)

    if now >= closes_at:
        return SessionState(False, False, "DEPOIS_FECHO", opens_at, closes_at)

    mins = _minutes_between(closes_at, now)
    is_pre_close = mins <= _PRE_CLOSE_MINUTES
    return SessionState(
        True,
        is_pre_close,
        "PRE_CLOSE" if is_pre_close else "ABERTO",
        opens_at,
        closes_at,
    )


def _forex_session_state(now: datetime) -> SessionState:
    weekday = now.weekday()
    today_22 = datetime.combine(now.date(), time(22, 0), tzinfo=UTC)

    if weekday == 5:
        return SessionState(False, False, "FECHADO_FIM_DE_SEMANA", None, None)
    if weekday == 6 and now < today_22:
        return SessionState(False, False, "ANTES_ABERTURA_SEMANAL", today_22, None)
    if weekday == 4 and now >= today_22:
        return SessionState(False, False, "DEPOIS_FECHO_SEMANAL", None, today_22)

    closes_at = today_22 if weekday == 4 else None
    mins = _minutes_between(closes_at, now) if closes_at else 10**9
    return SessionState(
        True,
        mins <= _PRE_CLOSE_MINUTES,
        "PRE_CLOSE" if mins <= _PRE_CLOSE_MINUTES else "ABERTO",
        None,
        closes_at,
    )


def _micro_future_session_state(now: datetime) -> SessionState:
    weekday = now.weekday()
    today_22 = datetime.combine(now.date(), time(22, 0), tzinfo=UTC)
    today_23 = datetime.combine(now.date(), time(23, 0), tzinfo=UTC)

    if weekday == 5:
        return SessionState(False, False, "FECHADO_FIM_DE_SEMANA", None, None)
    if weekday == 6 and now < today_23:
        return SessionState(False, False, "ANTES_ABERTURA_SEMANAL", today_23, None)
    if weekday == 4 and now >= today_22:
        return SessionState(False, False, "DEPOIS_FECHO_SEMANAL", None, today_22)
    if time(22, 0) <= now.time() < time(23, 0):
        return SessionState(False, False, "PAUSA_DIARIA", today_23, today_22)

    closes_at = today_22 if now.time() < time(22, 0) else None
    mins = _minutes_between(closes_at, now) if closes_at else 10**9
    return SessionState(
        True,
        mins <= _PRE_CLOSE_MINUTES,
        "PRE_CLOSE" if mins <= _PRE_CLOSE_MINUTES else "ABERTO",
        None,
        closes_at,
    )


def _parse_time(raw: str) -> time:
    hour_str, minute_str = raw.split(":")
    return time(int(hour_str), int(minute_str))


def _minutes_between(target: datetime, now: datetime) -> int:
    return floor((target - now).total_seconds() / 60)


def _is_trading_day(calendar_name: str | None, now: datetime) -> bool:
    if now.weekday() >= 5:
        return False
    if calendar_name is None:
        return True
    if get_calendar is None:
        logger.warning(
            "pandas_market_calendars nao disponivel; a usar apenas filtro de fim-de-semana para %s.",
            calendar_name,
        )
        return True

    normalized_name = _CALENDAR_ALIASES.get(calendar_name, calendar_name)
    calendar = get_calendar(normalized_name)
    session_date = now.date()
    schedule = calendar.schedule(
        start_date=session_date - timedelta(days=1),
        end_date=session_date + timedelta(days=1),
    )
    return not schedule.loc[schedule.index.date == session_date].empty

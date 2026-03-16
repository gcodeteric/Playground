from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pandas as pd
import pytest

from main import TradingBot, create_initial_files, ensure_data_dirs
from src.contracts import parse_watchlist_entry
from src.grid_engine import GridEngine


def _build_bot_stub() -> TradingBot:
    bot = object.__new__(TradingBot)
    bot._telegram = None
    bot._notify = AsyncMock()
    bot._warmup_alert_state = {}
    bot._orphan_positions = {}
    bot._watchlist = [parse_watchlist_entry("AAPL")]
    bot._startup_reconciled = False
    return bot


def test_first_run_files_are_created(tmp_path):
    ensure_data_dirs(tmp_path)
    create_initial_files(tmp_path)

    assert (tmp_path / "grids_state.json").exists()
    assert (tmp_path / "trades_log.json").exists()
    assert (tmp_path / "metrics.json").exists()
    assert (tmp_path / "reconciliation.log").exists()
    assert (tmp_path / "bot.log").exists()


@pytest.mark.asyncio
async def test_warmup_alert_is_deduplicated():
    bot = _build_bot_stub()
    bot._telegram = SimpleNamespace(notify_warmup_waiting=AsyncMock())
    bot._schedule_telegram = lambda coro: asyncio.create_task(coro)

    spec = parse_watchlist_entry("AAPL")
    bars_df = pd.DataFrame({"close": [100.0] * 20})
    assert await TradingBot._check_warmup(bot, spec, bars_df) is False
    assert await TradingBot._check_warmup(bot, spec, bars_df) is False
    await asyncio.sleep(0)

    assert bot._telegram.notify_warmup_waiting.await_count == 1


@pytest.mark.asyncio
async def test_reconciliation_marks_ghost_grid(tmp_path):
    bot = _build_bot_stub()
    bot._telegram = SimpleNamespace(notify_reconciliation=AsyncMock())
    bot._config = SimpleNamespace(data_dir=tmp_path)
    bot._reconciliation_log_path = tmp_path / "reconciliation.log"
    bot._grid_engine = GridEngine(data_dir=str(tmp_path))
    bot._fetch_positions_with_retry = AsyncMock(return_value=[])
    grid = bot._grid_engine.create_grid(
        symbol="AAPL",
        center_price=100.0,
        atr=2.0,
        regime="BULL",
        num_levels=3,
        base_quantity=10,
        confidence="ALTO",
        size_multiplier=1.0,
    )
    bot._order_manager = SimpleNamespace(
        get_positions=AsyncMock(return_value=[]),
        get_open_orders=AsyncMock(return_value=[]),
        cancel_symbol_orders=AsyncMock(return_value=3),
    )

    await TradingBot._reconcile_startup(bot)

    assert grid.status == "paused"
    assert grid.reconciliation_state == "ghost"
    bot._order_manager.cancel_symbol_orders.assert_awaited_once_with("AAPL")


@pytest.mark.asyncio
async def test_reconciliation_registers_orphan_position(tmp_path):
    bot = _build_bot_stub()
    bot._telegram = SimpleNamespace(notify_reconciliation=AsyncMock())
    bot._config = SimpleNamespace(data_dir=tmp_path)
    bot._reconciliation_log_path = tmp_path / "reconciliation.log"
    bot._grid_engine = GridEngine(data_dir=str(tmp_path))
    bot._fetch_positions_with_retry = AsyncMock(return_value=[{"symbol": "AAPL", "quantity": 5.0}])
    bot._order_manager = SimpleNamespace(
        get_positions=AsyncMock(return_value=[{"symbol": "AAPL", "quantity": 5.0}]),
        get_open_orders=AsyncMock(return_value=[]),
        cancel_symbol_orders=AsyncMock(return_value=0),
    )

    await TradingBot._reconcile_startup(bot)

    assert "AAPL" in bot._orphan_positions
    assert bot._startup_reconciled is True

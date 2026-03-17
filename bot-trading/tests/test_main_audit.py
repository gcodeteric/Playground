from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
import pathlib

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
    bot._manual_pause = False
    bot._reconciliation_in_progress = False
    bot._last_cycle_started_at = None
    bot._last_cycle_completed_at = None
    bot._last_error = None
    bot._capital = 100_000.0
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


@pytest.mark.asyncio
async def test_preflight_persists_state_file(tmp_path):
    bot = _build_bot_stub()
    bot._config = SimpleNamespace(
        data_dir=tmp_path,
        ib=SimpleNamespace(paper_trading=True),
    )
    bot._watchlist = [parse_watchlist_entry("AAPL")]
    bot._connection = SimpleNamespace(
        connect=AsyncMock(return_value=True),
        request_executor=SimpleNamespace(
            run=AsyncMock(side_effect=[["DU123456"], []]),
        ),
        ib=SimpleNamespace(
            managedAccounts=MagicMock(return_value=["DU123456"]),
            accountValues=MagicMock(return_value=[]),
        ),
    )
    bot._check_data_files_integrity = AsyncMock()
    bot._verify_market_data_permissions = AsyncMock()
    bot._schedule_telegram = lambda coro: None
    bot._order_manager = object()
    bot._telegram = None

    await TradingBot.preflight_check(bot)

    state = json.loads((tmp_path / "preflight_state.json").read_text(encoding="utf-8"))
    assert state["startup_reconciled"] is False
    assert state["telegram_status"] == "disabled"
    assert "last_preflight" in state
    assert state["watchlist_size"] == 1
    assert state["capital"] == 100_000.0


@pytest.mark.asyncio
async def test_preflight_write_failure_does_not_abort(tmp_path, monkeypatch):
    bot = _build_bot_stub()
    bot._config = SimpleNamespace(
        data_dir=tmp_path,
        ib=SimpleNamespace(paper_trading=True),
    )
    bot._connection = SimpleNamespace(
        connect=AsyncMock(return_value=True),
        request_executor=SimpleNamespace(
            run=AsyncMock(side_effect=[["DU123456"], []]),
        ),
        ib=SimpleNamespace(
            managedAccounts=MagicMock(return_value=["DU123456"]),
            accountValues=MagicMock(return_value=[]),
        ),
    )
    bot._check_data_files_integrity = AsyncMock()
    bot._verify_market_data_permissions = AsyncMock()
    bot._schedule_telegram = lambda coro: None
    bot._order_manager = object()
    bot._telegram = None

    original_write_text = pathlib.Path.write_text

    def _failing_write(self, *args, **kwargs):
        if self.name == "preflight_state.json":
            raise OSError("disk full")
        return original_write_text(self, *args, **kwargs)

    monkeypatch.setattr(pathlib.Path, "write_text", _failing_write)

    await TradingBot.preflight_check(bot)

    assert not (tmp_path / "preflight_state.json").exists()


# ------------------------------------------------------------------
# Command consumer tests
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_handle_pause_sets_flag():
    bot = _build_bot_stub()
    bot._schedule_telegram = lambda coro: None
    result = await TradingBot._handle_pause(bot, {})
    assert bot._manual_pause is True
    assert result["action"] == "paused"


@pytest.mark.asyncio
async def test_handle_resume_clears_flag():
    bot = _build_bot_stub()
    bot._manual_pause = True
    bot._schedule_telegram = lambda coro: None
    result = await TradingBot._handle_resume(bot, {})
    assert bot._manual_pause is False
    assert result["action"] == "resumed"


@pytest.mark.asyncio
async def test_dispatch_unknown_command_returns_error():
    bot = _build_bot_stub()
    result = await TradingBot._dispatch_command(bot, "self_destruct", {})
    assert "error" in result


@pytest.mark.asyncio
async def test_handle_reconcile_now_without_order_manager():
    bot = _build_bot_stub()
    bot._order_manager = None
    result = await TradingBot._handle_reconcile_now(bot, {})
    assert "error" in result


@pytest.mark.asyncio
async def test_handle_export_snapshot_writes_file(tmp_path):
    bot = _build_bot_stub()
    bot._config = SimpleNamespace(data_dir=tmp_path)
    bot._grid_engine = GridEngine(data_dir=str(tmp_path))
    bot._period_pnl = {"daily": 0.0, "weekly": 0.0, "monthly": 0.0}
    result = await TradingBot._handle_export_snapshot(bot, {})
    assert result["action"] == "exported"
    snapshot = json.loads((tmp_path / "snapshot.json").read_text(encoding="utf-8"))
    assert "timestamp" in snapshot
    assert snapshot["manual_pause"] is False
    assert snapshot["capital"] == 100_000.0


@pytest.mark.asyncio
async def test_process_command_queue_processes_pending(tmp_path):
    bot = _build_bot_stub()
    bot._config = SimpleNamespace(data_dir=tmp_path)
    bot._schedule_telegram = lambda coro: None
    cmd_dir = tmp_path / "commands"
    cmd_dir.mkdir(parents=True)
    cmd_file = cmd_dir / "cmd_001.json"
    cmd_file.write_text(
        json.dumps({"command": "pause", "status": "pending", "payload": {}}),
        encoding="utf-8",
    )

    await TradingBot._process_command_queue(bot)

    assert bot._manual_pause is True
    assert not cmd_file.exists()
    processed = list((cmd_dir / "processed").glob("*.json"))
    assert len(processed) == 1


@pytest.mark.asyncio
async def test_process_command_queue_skips_non_pending(tmp_path):
    bot = _build_bot_stub()
    bot._config = SimpleNamespace(data_dir=tmp_path)
    cmd_dir = tmp_path / "commands"
    cmd_dir.mkdir(parents=True)
    cmd_file = cmd_dir / "cmd_002.json"
    cmd_file.write_text(
        json.dumps({"command": "pause", "status": "done", "payload": {}}),
        encoding="utf-8",
    )

    await TradingBot._process_command_queue(bot)

    assert bot._manual_pause is False
    assert cmd_file.exists()


@pytest.mark.asyncio
async def test_process_command_queue_moves_bad_json_to_failed(tmp_path):
    bot = _build_bot_stub()
    bot._config = SimpleNamespace(data_dir=tmp_path)
    cmd_dir = tmp_path / "commands"
    cmd_dir.mkdir(parents=True)
    cmd_file = cmd_dir / "cmd_bad.json"
    cmd_file.write_text("{broken json!", encoding="utf-8")

    await TradingBot._process_command_queue(bot)

    assert not cmd_file.exists()
    failed = list((cmd_dir / "failed").glob("*.json"))
    assert len(failed) == 1


# ------------------------------------------------------------------
# Reconciliation concurrency guard
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_reconciliation_skips_when_already_in_progress(tmp_path):
    bot = _build_bot_stub()
    bot._reconciliation_in_progress = True
    bot._config = SimpleNamespace(data_dir=tmp_path)
    bot._reconciliation_log_path = tmp_path / "reconciliation.log"
    bot._grid_engine = GridEngine(data_dir=str(tmp_path))
    bot._order_manager = SimpleNamespace(
        get_open_orders=AsyncMock(return_value=[]),
    )
    bot._fetch_positions_with_retry = AsyncMock(return_value=[])

    await TradingBot._run_reconciliation(bot)

    bot._fetch_positions_with_retry.assert_not_awaited()


# ------------------------------------------------------------------
# _write_heartbeat tests
# ------------------------------------------------------------------

def test_write_heartbeat_creates_json(tmp_path):
    bot = _build_bot_stub()
    bot._config = SimpleNamespace(data_dir=tmp_path)
    bot._connection = SimpleNamespace(is_connected=True)

    TradingBot._write_heartbeat(bot)

    hb = json.loads((tmp_path / "heartbeat.json").read_text(encoding="utf-8"))
    assert "timestamp" in hb
    assert hb["manual_pause"] is False
    assert hb["ib_connected"] is True
    assert hb["last_error"] is None


def test_write_heartbeat_captures_error_state(tmp_path):
    bot = _build_bot_stub()
    bot._config = SimpleNamespace(data_dir=tmp_path)
    bot._connection = SimpleNamespace(is_connected=False)
    bot._last_error = "timeout"

    TradingBot._write_heartbeat(bot)

    hb = json.loads((tmp_path / "heartbeat.json").read_text(encoding="utf-8"))
    assert hb["ib_connected"] is False
    assert hb["last_error"] == "timeout"

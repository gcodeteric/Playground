from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
import pathlib

import pandas as pd
import pytest

from main import (
    BrokerPositionsObservation,
    TradingBot,
    create_initial_files,
    ensure_data_dirs,
)
from src.contracts import parse_watchlist_entry
from src.grid_engine import GridEngine
from src.risk_manager import RiskManager
from src.signal_engine import Confianca, Regime, RegimeInfo, SignalResult, TrendHorizon


def _build_bot_stub() -> TradingBot:
    bot = object.__new__(TradingBot)
    bot._telegram = None
    bot._schedule_telegram = (
        lambda coro: asyncio.create_task(coro) if coro is not None else None
    )
    bot._notify = AsyncMock()
    bot._warmup_alert_state = {}
    bot._orphan_positions = {}
    bot._watchlist = [parse_watchlist_entry("AAPL")]
    bot._startup_reconciled = False
    bot._manual_pause = False
    bot._entry_halt_reason = None
    bot._emergency_halt = False
    bot._reconciliation_in_progress = False
    bot._last_cycle_started_at = None
    bot._last_cycle_completed_at = None
    bot._last_error = None
    bot._reference_history_cache = {}
    bot._running = True
    bot._shutdown_event = asyncio.Event()
    bot._capital = 100_000.0
    bot._equity_baselines = {}
    bot._last_equity_snapshot = None
    bot._instance_lock_fd = None
    bot._instance_lock_path = pathlib.Path.cwd() / "bot.instance.lock"
    bot._risk_manager = SimpleNamespace(
        update_capital=MagicMock(),
        peak_equity=100_000.0,
        initial_capital=100_000.0,
    )
    bot._trade_logger = SimpleNamespace(
        calculate_metrics=MagicMock(return_value={"total_pnl": 0.0, "num_trades": 0}),
        get_trades=MagicMock(return_value=[]),
        save_metrics=MagicMock(),
    )
    return bot


def _build_regime_info() -> RegimeInfo:
    return RegimeInfo(
        regime=Regime.BULL,
        motivo="test",
        preco_vs_sma200=0.01,
        sma50_vs_sma200=0.01,
        rsi=50.0,
        atr_ratio=1.0,
        volatilidade_baixa=False,
    )


def _build_signal_result() -> SignalResult:
    return SignalResult(
        signal=True,
        regime=Regime.BULL,
        deviation=-30.0,
        deviation_minimo=-25.0,
        deviation_optimo=-35.0,
        confirmacoes=3,
        detalhes_confirmacoes=["test"],
        confianca=Confianca.ALTO,
        horizon=TrendHorizon.SHORT_TERM,
        size_multiplier=1.0,
        preco=100.0,
        rsi=40.0,
        rsi2=35.0,
        bb_lower=95.0,
        volume_ratio=1.2,
    )


def _build_runtime_config(tmp_path):
    return SimpleNamespace(
        data_dir=tmp_path,
        ib=SimpleNamespace(paper_trading=True, client_id=7),
        risk=SimpleNamespace(
            daily_loss_limit=0.03,
            weekly_loss_limit=0.06,
            monthly_dd_limit=0.10,
            stop_atr_mult=1.0,
            tp_atr_mult=2.5,
        ),
    )


def _seed_equity_baselines(bot: TradingBot, now: datetime) -> None:
    period_ids = TradingBot._get_equity_period_ids(now)
    bot._equity_baselines = {
        key: {"period": period_id, "equity": 100_000.0}
        for key, period_id in period_ids.items()
    }


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
async def test_reconciliation_unknown_positions_does_not_pause_grid(tmp_path):
    bot = _build_bot_stub()
    bot._telegram = SimpleNamespace(notify_reconciliation=AsyncMock())
    bot._config = SimpleNamespace(data_dir=tmp_path)
    bot._reconciliation_log_path = tmp_path / "reconciliation.log"
    bot._grid_engine = GridEngine(data_dir=str(tmp_path))
    bot._fetch_positions_with_retry = AsyncMock(
        return_value=BrokerPositionsObservation(state="unknown", positions=[]),
    )
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
        get_open_orders=AsyncMock(return_value=[]),
        cancel_symbol_orders=AsyncMock(return_value=3),
    )

    await TradingBot._reconcile_startup(bot)

    assert grid.status == "active"
    assert grid.reconciliation_state == "unknown"
    assert bot._startup_reconciled is True
    bot._order_manager.cancel_symbol_orders.assert_not_awaited()


@pytest.mark.asyncio
async def test_reconciliation_registers_orphan_position(tmp_path):
    bot = _build_bot_stub()
    bot._telegram = SimpleNamespace(notify_reconciliation=AsyncMock())
    bot._config = SimpleNamespace(data_dir=tmp_path)
    bot._reconciliation_log_path = tmp_path / "reconciliation.log"
    bot._grid_engine = GridEngine(data_dir=str(tmp_path))
    bot._fetch_positions_with_retry = AsyncMock(
        return_value=BrokerPositionsObservation(
            state="confirmed",
            positions=[{"symbol": "AAPL", "quantity": 5.0}],
        ),
    )
    bot._order_manager = SimpleNamespace(
        get_open_orders=AsyncMock(return_value=[]),
        cancel_symbol_orders=AsyncMock(return_value=0),
    )

    await TradingBot._reconcile_startup(bot)

    assert "AAPL" in bot._orphan_positions
    assert bot._startup_reconciled is True


@pytest.mark.asyncio
async def test_reconciliation_syncs_tracking_from_open_orders(tmp_path):
    bot = _build_bot_stub()
    bot._telegram = SimpleNamespace(notify_reconciliation=AsyncMock())
    bot._config = SimpleNamespace(data_dir=tmp_path)
    bot._reconciliation_log_path = tmp_path / "reconciliation.log"
    bot._grid_engine = GridEngine(data_dir=str(tmp_path))
    grid = bot._grid_engine.create_grid(
        symbol="AAPL",
        center_price=100.0,
        atr=2.0,
        regime="BULL",
        num_levels=1,
        base_quantity=10,
        confidence="ALTO",
        size_multiplier=1.0,
    )
    grid.levels[0].status = "bought"
    bot._fetch_positions_with_retry = AsyncMock(
        return_value=BrokerPositionsObservation(
            state="confirmed",
            positions=[{"symbol": "AAPL", "quantity": 10.0}],
        ),
    )
    bot._order_manager = SimpleNamespace(
        get_open_orders=AsyncMock(
            return_value=[
                {"order_id": 1002, "symbol": "AAPL", "status": "Submitted", "order_ref": grid.id + ":1:BUY:entry"},
            ]
        ),
        sync_tracking_from_open_orders=MagicMock(return_value=1),
        cancel_symbol_orders=AsyncMock(return_value=0),
    )

    await TradingBot._run_reconciliation(bot)

    bot._order_manager.sync_tracking_from_open_orders.assert_called_once()
    assert grid.reconciliation_state == "synced"


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


def test_rehydrate_order_tracking_rebuilds_from_grids(tmp_path):
    bot = _build_bot_stub()
    bot._grid_engine = GridEngine(data_dir=str(tmp_path))
    grid = bot._grid_engine.create_grid(
        symbol="AAPL",
        center_price=100.0,
        atr=2.0,
        regime="BULL",
        num_levels=1,
        base_quantity=10,
        confidence="ALTO",
        size_multiplier=1.0,
    )
    grid.levels[0].buy_order_id = 1001
    grid.levels[0].stop_order_id = 1002
    grid.levels[0].sell_order_id = 1003
    grid.levels[0].status = "pending"
    bot._order_manager = SimpleNamespace(
        rehydrate_grid_orders=MagicMock(return_value=3),
    )

    restored = TradingBot._rehydrate_order_tracking(bot)

    assert restored == 3
    bot._order_manager.rehydrate_grid_orders.assert_called_once()


def test_restore_runtime_capital_prefers_broker_equity(tmp_path):
    bot = _build_bot_stub()
    bot._config = SimpleNamespace(data_dir=tmp_path)

    source = TradingBot._restore_runtime_capital(
        bot,
        [{"tag": "NetLiquidation", "value": "92500.50", "currency": "BASE"}],
    )

    assert source == "broker"
    assert bot._capital == pytest.approx(92_500.50, abs=1e-5)
    bot._risk_manager.update_capital.assert_called_once_with(pytest.approx(92_500.50, abs=1e-5))
    assert bot._risk_manager.peak_equity == pytest.approx(100_000.0, abs=1e-5)


def test_restore_runtime_capital_falls_back_to_metrics_snapshot(tmp_path):
    bot = _build_bot_stub()
    bot._config = SimpleNamespace(data_dir=tmp_path)
    (tmp_path / "metrics.json").write_text(
        json.dumps(
            {
                "metrics": {
                    "capital": 88_000.0,
                    "peak_equity": 120_000.0,
                },
            },
        ),
        encoding="utf-8",
    )

    source = TradingBot._restore_runtime_capital(bot, [])

    assert source == "metrics"
    assert bot._capital == pytest.approx(88_000.0, abs=1e-5)
    assert bot._risk_manager.peak_equity == pytest.approx(120_000.0, abs=1e-5)


def test_build_metrics_payload_includes_runtime_capital_and_peak():
    bot = _build_bot_stub()
    bot._capital = 95_500.0
    bot._risk_manager.initial_capital = 100_000.0
    bot._risk_manager.peak_equity = 110_250.0

    payload = TradingBot._build_metrics_payload(bot, {"win_rate": 0.55})

    assert payload["win_rate"] == 0.55
    assert payload["capital"] == 95_500.0
    assert payload["initial_capital"] == 100_000.0
    assert payload["peak_equity"] == 110_250.0


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


@pytest.mark.asyncio
async def test_preflight_aborts_on_live_account_when_paper_mode_enabled(tmp_path):
    bot = _build_bot_stub()
    bot._config = SimpleNamespace(
        data_dir=tmp_path,
        ib=SimpleNamespace(paper_trading=True),
    )
    bot._connection = SimpleNamespace(
        connect=AsyncMock(return_value=True),
        request_executor=SimpleNamespace(
            run=AsyncMock(side_effect=[["U123456"], []]),
        ),
        ib=SimpleNamespace(
            managedAccounts=MagicMock(return_value=["U123456"]),
            accountValues=MagicMock(return_value=[]),
        ),
    )
    bot._check_data_files_integrity = AsyncMock()
    bot._verify_market_data_permissions = AsyncMock()
    bot._order_manager = object()

    with pytest.raises(SystemExit):
        await TradingBot.preflight_check(bot)


def test_enforce_account_context_halts_reconnect_on_mismatch():
    bot = _build_bot_stub()
    bot._config = SimpleNamespace(ib=SimpleNamespace(paper_trading=True))

    result = TradingBot._enforce_account_context(bot, "U123456", phase="reconnect")

    assert result is False
    assert bot._entry_halt_reason == "account_context_violation"
    assert bot._emergency_halt is True
    assert bot._running is False
    assert bot._shutdown_event.is_set()


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


@pytest.mark.asyncio
async def test_main_cycle_pause_keeps_monitoring_active():
    bot = _build_bot_stub()
    bot._manual_pause = True
    bot._process_command_queue = AsyncMock()
    bot._advance_defensive_day_counter = MagicMock()
    bot._refresh_period_pnl = MagicMock(return_value={"daily": 0.0, "weekly": 0.0, "monthly": 0.0})
    bot._connection = SimpleNamespace(ensure_connected=AsyncMock(return_value=True))
    bot.refresh_dynamic_win_rate = MagicMock()
    bot._evaluate_sector_rotation = AsyncMock()
    bot._check_risk_limits = AsyncMock(return_value=False)
    bot._process_symbol = AsyncMock()
    bot._monitor_active_grids = AsyncMock()
    bot._check_daily_summary = AsyncMock()
    bot._write_heartbeat = MagicMock()
    bot._order_manager = SimpleNamespace(cleanup_completed=MagicMock())

    await TradingBot._main_cycle(bot)

    bot._process_symbol.assert_not_awaited()
    bot._monitor_active_grids.assert_awaited_once()
    bot._check_daily_summary.assert_awaited_once()
    bot._write_heartbeat.assert_called_once()
    bot._order_manager.cleanup_completed.assert_called_once()


@pytest.mark.asyncio
async def test_daily_limit_cancels_only_pending_entry_orders(tmp_path):
    bot = _build_bot_stub()
    bot._config = SimpleNamespace(
        data_dir=tmp_path,
        ib=SimpleNamespace(paper_trading=True),
        risk=SimpleNamespace(
            daily_loss_limit=0.03,
            weekly_loss_limit=0.06,
            monthly_dd_limit=0.10,
        ),
    )
    bot._refresh_period_pnl = MagicMock(
        return_value={"daily": -4_000.0, "weekly": 0.0, "monthly": 0.0},
    )
    bot._fetch_current_equity_snapshot = AsyncMock(return_value=96_000.0)
    _seed_equity_baselines(bot, datetime(2026, 3, 18, tzinfo=timezone.utc))
    bot._risk_manager = SimpleNamespace(
        update_capital=MagicMock(),
        update_peak_equity=MagicMock(),
        check_daily_limit=MagicMock(return_value=False),
        check_weekly_limit=MagicMock(return_value=True),
        check_kill_switch=MagicMock(return_value=True),
    )
    bot._grid_engine = GridEngine(data_dir=str(tmp_path))
    bot._order_manager = SimpleNamespace(cancel_order=AsyncMock(return_value=True))

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
    pending_level = grid.levels[0]
    pending_level.status = "pending"
    pending_level.buy_order_id = 101
    pending_level.stop_order_id = 102
    pending_level.sell_order_id = 103
    bought_level = grid.levels[1]
    bought_level.status = "bought"
    bought_level.buy_order_id = 201
    bought_level.stop_order_id = 202
    bought_level.sell_order_id = 203

    should_block = await TradingBot._check_risk_limits(bot)

    assert should_block is True
    assert bot._entry_halt_reason == "daily_limit"
    cancelled_ids = {
        call.args[0]
        for call in bot._order_manager.cancel_order.await_args_list
    }
    assert cancelled_ids == {101, 102, 103}
    assert 202 not in cancelled_ids


@pytest.mark.asyncio
async def test_monthly_kill_switch_initiates_broker_flatten(tmp_path):
    bot = _build_bot_stub()
    bot._config = SimpleNamespace(
        data_dir=tmp_path,
        ib=SimpleNamespace(paper_trading=True),
        risk=SimpleNamespace(
            daily_loss_limit=0.03,
            weekly_loss_limit=0.06,
            monthly_dd_limit=0.10,
        ),
    )
    bot._refresh_period_pnl = MagicMock(
        return_value={"daily": 0.0, "weekly": 0.0, "monthly": -11_000.0},
    )
    bot._fetch_current_equity_snapshot = AsyncMock(return_value=89_000.0)
    _seed_equity_baselines(bot, datetime(2026, 3, 18, tzinfo=timezone.utc))
    bot._risk_manager = SimpleNamespace(
        update_capital=MagicMock(),
        update_peak_equity=MagicMock(),
        check_daily_limit=MagicMock(return_value=True),
        check_weekly_limit=MagicMock(return_value=True),
        check_kill_switch=MagicMock(return_value=False),
    )
    bot._grid_engine = GridEngine(data_dir=str(tmp_path))
    bot._get_instrument_spec = MagicMock(return_value=parse_watchlist_entry("AAPL"))
    bot._order_manager = SimpleNamespace(
        cancel_order=AsyncMock(return_value=True),
        close_position=AsyncMock(return_value=True),
    )

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
    grid.levels[0].status = "bought"
    grid.levels[0].quantity = 7
    grid.levels[0].stop_order_id = 301
    grid.levels[0].sell_order_id = 302

    should_block = await TradingBot._check_risk_limits(bot)

    assert should_block is True
    assert bot._entry_halt_reason == "monthly_kill_switch"
    assert bot._emergency_halt is True
    assert grid.status == "active"
    assert grid.reconciliation_state == "flattening"
    bot._order_manager.close_position.assert_awaited_once()


@pytest.mark.asyncio
async def test_unrealized_equity_loss_triggers_daily_halt(tmp_path):
    bot = _build_bot_stub()
    bot._config = _build_runtime_config(tmp_path)
    bot._grid_engine = GridEngine(data_dir=str(tmp_path))
    bot._order_manager = SimpleNamespace(cancel_order=AsyncMock(return_value=True))
    bot._risk_manager = RiskManager(
        capital=100_000.0,
        daily_loss_limit=0.03,
        weekly_loss_limit=0.06,
        monthly_dd_limit=0.10,
    )
    bot._refresh_period_pnl = MagicMock(
        return_value={"daily": 0.0, "weekly": 0.0, "monthly": 0.0},
    )
    bot._fetch_current_equity_snapshot = AsyncMock(return_value=96_000.0)
    _seed_equity_baselines(bot, datetime(2026, 3, 18, tzinfo=timezone.utc))

    grid = bot._grid_engine.create_grid(
        symbol="AAPL",
        center_price=100.0,
        atr=2.0,
        regime="BULL",
        num_levels=2,
        base_quantity=10,
        confidence="ALTO",
        size_multiplier=1.0,
    )
    pending_level = grid.levels[0]
    pending_level.status = "pending"
    pending_level.buy_order_id = 101
    pending_level.stop_order_id = 102
    pending_level.sell_order_id = 103
    bought_level = grid.levels[1]
    bought_level.status = "bought"
    bought_level.stop_order_id = 202

    should_block = await TradingBot._check_risk_limits(bot)

    assert should_block is True
    assert bot._entry_halt_reason == "daily_limit"
    cancelled_ids = {
        call.args[0]
        for call in bot._order_manager.cancel_order.await_args_list
    }
    assert cancelled_ids == {101, 102, 103}
    assert 202 not in cancelled_ids


@pytest.mark.asyncio
async def test_invalid_equity_baseline_fails_safe_without_division(tmp_path):
    bot = _build_bot_stub()
    bot._config = _build_runtime_config(tmp_path)
    bot._grid_engine = GridEngine(data_dir=str(tmp_path))
    bot._order_manager = SimpleNamespace(cancel_order=AsyncMock(return_value=True))
    bot._risk_manager = RiskManager(
        capital=100_000.0,
        daily_loss_limit=0.03,
        weekly_loss_limit=0.06,
        monthly_dd_limit=0.10,
    )
    bot._refresh_period_pnl = MagicMock(
        return_value={"daily": 0.0, "weekly": 0.0, "monthly": 0.0},
    )
    bot._fetch_current_equity_snapshot = AsyncMock(return_value=95_000.0)
    _seed_equity_baselines(bot, datetime(2026, 3, 18, tzinfo=timezone.utc))
    bot._equity_baselines["daily"]["equity"] = 0.0

    grid = bot._grid_engine.create_grid(
        symbol="AAPL",
        center_price=100.0,
        atr=2.0,
        regime="BULL",
        num_levels=1,
        base_quantity=10,
        confidence="ALTO",
        size_multiplier=1.0,
    )
    grid.levels[0].buy_order_id = 101
    grid.levels[0].stop_order_id = 102
    grid.levels[0].sell_order_id = 103

    should_block = await TradingBot._check_risk_limits(bot)

    assert should_block is True
    assert bot._entry_halt_reason == "equity_baseline_invalid"
    cancelled_ids = {
        call.args[0]
        for call in bot._order_manager.cancel_order.await_args_list
    }
    assert cancelled_ids == {101, 102, 103}


@pytest.mark.asyncio
async def test_missing_equity_snapshot_blocks_entries(tmp_path):
    bot = _build_bot_stub()
    bot._config = _build_runtime_config(tmp_path)
    bot._grid_engine = GridEngine(data_dir=str(tmp_path))
    bot._order_manager = SimpleNamespace(cancel_order=AsyncMock(return_value=True))
    bot._risk_manager = RiskManager(capital=100_000.0)
    bot._fetch_current_equity_snapshot = AsyncMock(return_value=None)

    grid = bot._grid_engine.create_grid(
        symbol="AAPL",
        center_price=100.0,
        atr=2.0,
        regime="BULL",
        num_levels=1,
        base_quantity=10,
        confidence="ALTO",
        size_multiplier=1.0,
    )
    grid.levels[0].buy_order_id = 101
    grid.levels[0].stop_order_id = 102
    grid.levels[0].sell_order_id = 103

    should_block = await TradingBot._check_risk_limits(bot)

    assert should_block is True
    assert bot._entry_halt_reason == "equity_snapshot_unavailable"
    cancelled_ids = {
        call.args[0]
        for call in bot._order_manager.cancel_order.await_args_list
    }
    assert cancelled_ids == {101, 102, 103}


def test_equity_baselines_roll_over_by_period(tmp_path):
    bot = _build_bot_stub()
    bot._config = _build_runtime_config(tmp_path)

    start = datetime(2026, 3, 18, 10, tzinfo=timezone.utc)
    assert TradingBot._sync_equity_baselines(bot, 100_000.0, now=start) is True
    assert bot._equity_baselines["daily"]["equity"] == 100_000.0
    assert bot._equity_baselines["weekly"]["equity"] == 100_000.0
    assert bot._equity_baselines["monthly"]["equity"] == 100_000.0

    next_day = datetime(2026, 3, 19, 10, tzinfo=timezone.utc)
    assert TradingBot._sync_equity_baselines(bot, 99_000.0, now=next_day) is True
    assert bot._equity_baselines["daily"]["equity"] == 99_000.0
    assert bot._equity_baselines["weekly"]["equity"] == 100_000.0
    assert bot._equity_baselines["monthly"]["equity"] == 100_000.0

    next_week = datetime(2026, 3, 23, 10, tzinfo=timezone.utc)
    assert TradingBot._sync_equity_baselines(bot, 98_000.0, now=next_week) is True
    assert bot._equity_baselines["weekly"]["equity"] == 98_000.0

    next_month = datetime(2026, 4, 1, 10, tzinfo=timezone.utc)
    assert TradingBot._sync_equity_baselines(bot, 97_000.0, now=next_month) is True
    assert bot._equity_baselines["monthly"]["equity"] == 97_000.0


@pytest.mark.asyncio
async def test_attempt_grid_creation_activates_grid_only_after_all_levels_submit(tmp_path):
    bot = _build_bot_stub()
    bot._config = SimpleNamespace(
        data_dir=tmp_path,
        ib=SimpleNamespace(paper_trading=True),
        risk=SimpleNamespace(stop_atr_mult=1.0, tp_atr_mult=2.5),
    )
    bot._grid_engine = GridEngine(data_dir=str(tmp_path))
    bot._orphan_positions = {}
    bot._trade_logger = SimpleNamespace(calculate_metrics=MagicMock(return_value={}))
    bot._period_pnl = {"daily": 0.0, "weekly": 0.0, "monthly": 0.0}
    bot._dynamic_win_rate = 0.5
    bot._risk_manager = SimpleNamespace(
        check_max_grids=MagicMock(return_value=True),
        calculate_stop_loss=MagicMock(return_value=98.8),
        calculate_take_profit=MagicMock(return_value=103.0),
        position_size_per_level=MagicMock(return_value=10),
        validate_order=MagicMock(return_value=(True, "")),
    )

    async def _submit(**kwargs):
        level = kwargs["level"]
        return {
            "order_id": 1000 + level,
            "stop_order_id": 2000 + level,
            "tp_order_id": 3000 + level,
        }

    bot._order_manager = SimpleNamespace(
        submit_bracket_order=AsyncMock(side_effect=_submit),
        cancel_order=AsyncMock(return_value=True),
    )

    await TradingBot._attempt_grid_creation(
        bot,
        spec=parse_watchlist_entry("AAPL"),
        contract=MagicMock(symbol="AAPL"),
        price=100.0,
        atr=2.0,
        regime_info=_build_regime_info(),
        signal_result=_build_signal_result(),
        session_ok=True,
        data_fresh=True,
        warmup_ok=True,
    )

    assert len(bot._grid_engine.grids) == 1
    grid = bot._grid_engine.grids[0]
    assert grid.status == "active"
    assert grid.failure_reason is None
    assert all(level.buy_order_id is not None for level in grid.levels)
    assert bot._order_manager.submit_bracket_order.await_count == len(grid.levels)


@pytest.mark.asyncio
async def test_attempt_grid_creation_marks_failed_on_partial_submission(tmp_path):
    bot = _build_bot_stub()
    bot._config = SimpleNamespace(
        data_dir=tmp_path,
        ib=SimpleNamespace(paper_trading=True),
        risk=SimpleNamespace(stop_atr_mult=1.0, tp_atr_mult=2.5),
    )
    bot._grid_engine = GridEngine(data_dir=str(tmp_path))
    bot._orphan_positions = {}
    bot._trade_logger = SimpleNamespace(calculate_metrics=MagicMock(return_value={}))
    bot._period_pnl = {"daily": 0.0, "weekly": 0.0, "monthly": 0.0}
    bot._dynamic_win_rate = 0.5
    bot._risk_manager = SimpleNamespace(
        check_max_grids=MagicMock(return_value=True),
        calculate_stop_loss=MagicMock(return_value=98.8),
        calculate_take_profit=MagicMock(return_value=103.0),
        position_size_per_level=MagicMock(return_value=10),
        validate_order=MagicMock(return_value=(True, "")),
    )

    async def _submit(**kwargs):
        level = kwargs["level"]
        if level == 3:
            return None
        return {
            "order_id": 1000 + level,
            "stop_order_id": 2000 + level,
            "tp_order_id": 3000 + level,
        }

    bot._order_manager = SimpleNamespace(
        submit_bracket_order=AsyncMock(side_effect=_submit),
        cancel_order=AsyncMock(return_value=True),
    )

    await TradingBot._attempt_grid_creation(
        bot,
        spec=parse_watchlist_entry("AAPL"),
        contract=MagicMock(symbol="AAPL"),
        price=100.0,
        atr=2.0,
        regime_info=_build_regime_info(),
        signal_result=_build_signal_result(),
        session_ok=True,
        data_fresh=True,
        warmup_ok=True,
    )

    assert len(bot._grid_engine.grids) == 1
    grid = bot._grid_engine.grids[0]
    assert grid.status == "failed"
    assert grid.failure_reason == "initial_order_submission_failed_level_3"
    cancelled_ids = {
        call.args[0]
        for call in bot._order_manager.cancel_order.await_args_list
    }
    assert cancelled_ids == {1001, 2001, 3001, 1002, 2002, 3002}


@pytest.mark.asyncio
async def test_attempt_grid_creation_gate_rejects_non_finite_inputs(tmp_path):
    bot = _build_bot_stub()
    bot._config = SimpleNamespace(
        data_dir=tmp_path,
        ib=SimpleNamespace(paper_trading=True),
        risk=SimpleNamespace(stop_atr_mult=1.0, tp_atr_mult=2.5),
    )
    bot._grid_engine = GridEngine(data_dir=str(tmp_path))
    bot._orphan_positions = {}
    bot._trade_logger = SimpleNamespace(calculate_metrics=MagicMock(return_value={}))
    bot._period_pnl = {"daily": 0.0, "weekly": 0.0, "monthly": 0.0}
    bot._dynamic_win_rate = 0.5
    bot._risk_manager = SimpleNamespace(
        check_max_grids=MagicMock(return_value=True),
        calculate_stop_loss=MagicMock(return_value=98.8),
        calculate_take_profit=MagicMock(return_value=103.0),
        position_size_per_level=MagicMock(return_value=10),
        validate_order=MagicMock(return_value=(True, "")),
    )
    bot._order_manager = SimpleNamespace(
        submit_bracket_order=AsyncMock(),
        cancel_order=AsyncMock(return_value=True),
    )

    await TradingBot._attempt_grid_creation(
        bot,
        spec=parse_watchlist_entry("AAPL"),
        contract=MagicMock(symbol="AAPL"),
        price=float("nan"),
        atr=2.0,
        regime_info=_build_regime_info(),
        signal_result=_build_signal_result(),
        session_ok=True,
        data_fresh=True,
        warmup_ok=True,
    )

    assert bot._grid_engine.grids == []
    bot._risk_manager.position_size_per_level.assert_not_called()
    bot._risk_manager.validate_order.assert_not_called()
    bot._order_manager.submit_bracket_order.assert_not_awaited()


@pytest.mark.asyncio
async def test_reconciliation_closes_flattening_grid_after_broker_confirms_flat(tmp_path):
    bot = _build_bot_stub()
    bot._telegram = SimpleNamespace(notify_reconciliation=AsyncMock())
    bot._config = SimpleNamespace(data_dir=tmp_path)
    bot._reconciliation_log_path = tmp_path / "reconciliation.log"
    bot._grid_engine = GridEngine(data_dir=str(tmp_path))
    grid = bot._grid_engine.create_grid(
        symbol="AAPL",
        center_price=100.0,
        atr=2.0,
        regime="BULL",
        num_levels=1,
        base_quantity=10,
        confidence="ALTO",
        size_multiplier=1.0,
    )
    grid.levels[0].status = "bought"
    grid.reconciliation_state = "flattening"
    bot._fetch_positions_with_retry = AsyncMock(
        return_value=BrokerPositionsObservation(state="confirmed", positions=[]),
    )
    bot._order_manager = SimpleNamespace(
        get_open_orders=AsyncMock(return_value=[]),
        sync_tracking_from_open_orders=MagicMock(return_value=0),
        cancel_symbol_orders=AsyncMock(return_value=0),
    )

    await TradingBot._run_reconciliation(bot)

    assert grid.status == "closed"
    assert grid.reconciliation_state == "synced"


@pytest.mark.asyncio
async def test_partial_fill_pauses_grid_and_trips_emergency_halt(tmp_path):
    bot = _build_bot_stub()
    bot._config = SimpleNamespace(
        data_dir=tmp_path,
        ib=SimpleNamespace(paper_trading=True),
    )
    bot._grid_engine = GridEngine(data_dir=str(tmp_path))
    bot._get_instrument_spec = MagicMock(return_value=parse_watchlist_entry("AAPL"))
    grid = bot._grid_engine.create_grid(
        symbol="AAPL",
        center_price=100.0,
        atr=2.0,
        regime="BULL",
        num_levels=1,
        base_quantity=10,
        confidence="ALTO",
        size_multiplier=1.0,
    )
    level = grid.levels[0]
    level.buy_order_id = 123
    order_info = SimpleNamespace(
        filled_quantity=4,
        fill_price=100.1,
        leg_type="parent",
    )
    bot._order_manager = SimpleNamespace(
        get_order_info=MagicMock(return_value=order_info),
        get_order_status=MagicMock(return_value="Submitted"),
        cancel_all_grid_orders=AsyncMock(return_value=0),
    )
    bot._data_feed = SimpleNamespace(get_current_price=AsyncMock(return_value=None))

    await TradingBot._monitor_single_grid(bot, grid)

    assert bot._entry_halt_reason == "partial_fill_detected"
    assert bot._emergency_halt is True
    assert grid.status == "paused"
    assert grid.reconciliation_state == "partial_fill"


@pytest.mark.asyncio
@pytest.mark.parametrize("source", ["close", "yfinance"])
async def test_monitor_single_grid_skips_dynamic_adjustments_on_stale_sources(
    tmp_path,
    monkeypatch,
    source,
):
    bot = _build_bot_stub()
    bot._config = _build_runtime_config(tmp_path)
    bot._grid_engine = GridEngine(data_dir=str(tmp_path))
    spec = parse_watchlist_entry("AAPL")
    bot._get_instrument_spec = MagicMock(return_value=spec)
    bot._cancel_pending_entry_orders = AsyncMock(return_value=0)
    bot._submit_grid_level_bracket = AsyncMock(return_value=True)
    bot._order_manager = SimpleNamespace(
        get_order_info=MagicMock(return_value=None),
        get_order_status=MagicMock(return_value=None),
        cancel_all_grid_orders=AsyncMock(return_value=0),
    )
    bot._data_feed = SimpleNamespace(
        get_current_price_details=AsyncMock(
            return_value={"price": 101.0, "source": source, "fresh": False},
        ),
        get_historical_bars=AsyncMock(),
        get_market_data=MagicMock(return_value={"atr14": 2.0}),
    )
    grid = bot._grid_engine.create_grid(
        symbol="AAPL",
        center_price=100.0,
        atr=2.0,
        regime="BULL",
        num_levels=1,
        base_quantity=10,
        confidence="ALTO",
        size_multiplier=1.0,
    )
    bot._grid_engine.should_recenter = MagicMock(return_value=True)
    bot._grid_engine.should_respace = MagicMock(return_value=True)
    bot._grid_engine.recenter_grid = MagicMock()
    bot._grid_engine.save_state = MagicMock()

    monkeypatch.setattr(
        "main.get_session_state",
        lambda _spec: SimpleNamespace(
            is_pre_close=False,
            can_open_new_grid=True,
            status="ABERTA",
        ),
    )
    monkeypatch.setattr("main.build_contract", lambda _spec: MagicMock(symbol="AAPL"))

    await TradingBot._monitor_single_grid(bot, grid)

    bot._data_feed.get_historical_bars.assert_not_awaited()
    bot._grid_engine.recenter_grid.assert_not_called()
    bot._submit_grid_level_bracket.assert_not_awaited()


@pytest.mark.asyncio
async def test_monitor_single_grid_recenters_only_with_fresh_quote(tmp_path, monkeypatch):
    bot = _build_bot_stub()
    bot._config = _build_runtime_config(tmp_path)
    bot._grid_engine = GridEngine(data_dir=str(tmp_path))
    spec = parse_watchlist_entry("AAPL")
    bot._get_instrument_spec = MagicMock(return_value=spec)
    bot._cancel_pending_entry_orders = AsyncMock(return_value=1)
    bot._submit_grid_level_bracket = AsyncMock(return_value=True)
    bot._order_manager = SimpleNamespace(
        get_order_info=MagicMock(return_value=None),
        get_order_status=MagicMock(return_value=None),
        cancel_all_grid_orders=AsyncMock(return_value=0),
    )
    bars_df = pd.DataFrame(
        {
            "date": pd.date_range("2024-01-01", periods=30, freq="B"),
            "open": [100.0] * 30,
            "high": [101.0] * 30,
            "low": [99.0] * 30,
            "close": [100.0] * 30,
            "volume": [1000.0] * 30,
        }
    )
    bot._data_feed = SimpleNamespace(
        get_current_price_details=AsyncMock(
            return_value={"price": 104.5, "source": "ib", "fresh": True},
        ),
        get_historical_bars=AsyncMock(return_value=bars_df),
        get_market_data=MagicMock(return_value={"atr14": 2.4}),
    )
    grid = bot._grid_engine.create_grid(
        symbol="AAPL",
        center_price=100.0,
        atr=2.0,
        regime="BULL",
        num_levels=1,
        base_quantity=10,
        confidence="ALTO",
        size_multiplier=1.0,
    )
    bot._grid_engine.should_recenter = MagicMock(return_value=True)
    bot._grid_engine.should_respace = MagicMock(return_value=False)
    bot._grid_engine.recenter_grid = MagicMock()
    bot._grid_engine.save_state = MagicMock()

    monkeypatch.setattr(
        "main.get_session_state",
        lambda _spec: SimpleNamespace(
            is_pre_close=False,
            can_open_new_grid=True,
            status="ABERTA",
        ),
    )
    monkeypatch.setattr("main.build_contract", lambda _spec: MagicMock(symbol="AAPL"))

    await TradingBot._monitor_single_grid(bot, grid)

    bot._grid_engine.recenter_grid.assert_called_once()
    bot._submit_grid_level_bracket.assert_awaited_once()


@pytest.mark.asyncio
async def test_monitor_single_grid_ignores_partial_snapshot(tmp_path, monkeypatch):
    bot = _build_bot_stub()
    bot._config = _build_runtime_config(tmp_path)
    bot._grid_engine = GridEngine(data_dir=str(tmp_path))
    spec = parse_watchlist_entry("AAPL")
    bot._get_instrument_spec = MagicMock(return_value=spec)
    bot._cancel_pending_entry_orders = AsyncMock(return_value=0)
    bot._submit_grid_level_bracket = AsyncMock(return_value=True)
    bot._order_manager = SimpleNamespace(
        get_order_info=MagicMock(return_value=None),
        get_order_status=MagicMock(return_value=None),
        cancel_all_grid_orders=AsyncMock(return_value=0),
    )
    bot._data_feed = SimpleNamespace(
        get_current_price_details=AsyncMock(return_value={"source": "ib"}),
        get_historical_bars=AsyncMock(),
        get_market_data=MagicMock(return_value={"atr14": 2.0}),
    )
    grid = bot._grid_engine.create_grid(
        symbol="AAPL",
        center_price=100.0,
        atr=2.0,
        regime="BULL",
        num_levels=1,
        base_quantity=10,
        confidence="ALTO",
        size_multiplier=1.0,
    )
    bot._grid_engine.recenter_grid = MagicMock()

    monkeypatch.setattr(
        "main.get_session_state",
        lambda _spec: SimpleNamespace(
            is_pre_close=False,
            can_open_new_grid=True,
            status="ABERTA",
        ),
    )
    monkeypatch.setattr("main.build_contract", lambda _spec: MagicMock(symbol="AAPL"))

    await TradingBot._monitor_single_grid(bot, grid)

    bot._data_feed.get_historical_bars.assert_not_awaited()
    bot._grid_engine.recenter_grid.assert_not_called()


def test_instance_lock_prevents_second_instance(tmp_path):
    bot_a = _build_bot_stub()
    bot_a._config = _build_runtime_config(tmp_path)
    bot_a._instance_lock_path = tmp_path / "bot.instance.lock"

    bot_b = _build_bot_stub()
    bot_b._config = _build_runtime_config(tmp_path)
    bot_b._instance_lock_path = bot_a._instance_lock_path

    TradingBot._acquire_instance_lock(bot_a)
    try:
        with pytest.raises(RuntimeError):
            TradingBot._acquire_instance_lock(bot_b)
    finally:
        TradingBot._release_instance_lock(bot_a)
        TradingBot._release_instance_lock(bot_b)


@pytest.mark.asyncio
async def test_graceful_shutdown_releases_instance_lock(tmp_path):
    bot = _build_bot_stub()
    bot._config = _build_runtime_config(tmp_path)
    bot._instance_lock_path = tmp_path / "bot.instance.lock"
    bot._grid_engine = GridEngine(data_dir=str(tmp_path))
    bot._connection = SimpleNamespace(disconnect=AsyncMock())
    bot._telegram_poll_task = None
    bot._trade_logger = SimpleNamespace(
        calculate_metrics=MagicMock(return_value={}),
        save_metrics=MagicMock(),
        get_trades=MagicMock(return_value=[]),
    )
    TradingBot._acquire_instance_lock(bot)

    await TradingBot._graceful_shutdown(bot)

    other_bot = _build_bot_stub()
    other_bot._config = _build_runtime_config(tmp_path)
    other_bot._instance_lock_path = bot._instance_lock_path
    try:
        TradingBot._acquire_instance_lock(other_bot)
    finally:
        TradingBot._release_instance_lock(other_bot)


def test_load_persisted_grids_fail_closed_on_corruption(tmp_path):
    bot = _build_bot_stub()
    bot._grid_engine = SimpleNamespace(load_state=MagicMock(side_effect=RuntimeError("bad state")))

    with pytest.raises(RuntimeError, match="fail-closed"):
        TradingBot._load_persisted_grids_or_fail_closed(bot)


@pytest.mark.asyncio
async def test_attempt_grid_creation_passes_correlation_context_to_risk_manager(tmp_path):
    bot = _build_bot_stub()
    bot._config = SimpleNamespace(
        data_dir=tmp_path,
        ib=SimpleNamespace(paper_trading=True),
        risk=SimpleNamespace(stop_atr_mult=1.0, tp_atr_mult=2.5),
    )
    bot._grid_engine = GridEngine(data_dir=str(tmp_path))
    bot._orphan_positions = {}
    bot._trade_logger = SimpleNamespace(calculate_metrics=MagicMock(return_value={}))
    bot._period_pnl = {"daily": 0.0, "weekly": 0.0, "monthly": 0.0}
    bot._dynamic_win_rate = 0.5
    bot._build_intl_etf_context = AsyncMock(
        return_value=(
            ["SPY"],
            {"AAPL": [0.01, -0.01] * 40, "SPY": [0.01, -0.01] * 40},
        )
    )
    bot._risk_manager = SimpleNamespace(
        check_max_grids=MagicMock(return_value=True),
        calculate_stop_loss=MagicMock(return_value=98.8),
        calculate_take_profit=MagicMock(return_value=103.0),
        position_size_per_level=MagicMock(return_value=10),
        validate_order=MagicMock(return_value=(True, "")),
    )
    bot._order_manager = SimpleNamespace(
        submit_bracket_order=AsyncMock(
            return_value={
                "order_id": 1001,
                "stop_order_id": 2001,
                "tp_order_id": 3001,
            }
        ),
        cancel_order=AsyncMock(return_value=True),
    )
    bars_df = pd.DataFrame(
        {
            "date": pd.date_range("2024-01-01", periods=120, freq="B"),
            "open": [100.0] * 120,
            "high": [101.0] * 120,
            "low": [99.0] * 120,
            "close": [100.0] * 120,
            "volume": [1000.0] * 120,
        }
    )

    await TradingBot._attempt_grid_creation(
        bot,
        spec=parse_watchlist_entry("AAPL"),
        contract=MagicMock(symbol="AAPL"),
        price=100.0,
        atr=2.0,
        regime_info=_build_regime_info(),
        signal_result=_build_signal_result(),
        bars_df=bars_df,
        session_ok=True,
        data_fresh=True,
        warmup_ok=True,
    )

    order_payload = bot._risk_manager.validate_order.call_args.args[0]
    assert order_payload["open_positions"] == ["SPY"]
    assert "AAPL" in order_payload["returns_map"]


@pytest.mark.asyncio
async def test_process_symbol_blocks_entries_on_stale_price(monkeypatch):
    bot = _build_bot_stub()
    spec = parse_watchlist_entry("AAPL")
    bars_df = pd.DataFrame(
        {
            "date": pd.date_range("2024-01-01", periods=250, freq="B"),
            "open": [100.0] * 250,
            "high": [101.0] * 250,
            "low": [99.0] * 250,
            "close": [100.0] * 250,
            "volume": [1000.0] * 250,
        },
    )
    bot._data_feed = SimpleNamespace(
        qualify_contract=AsyncMock(return_value=True),
        get_historical_bars=AsyncMock(return_value=bars_df),
        get_market_data_live=AsyncMock(
            return_value={
                "last_close": 100.0,
                "current_price": 100.0,
                "sma25": 100.0,
                "sma50": 100.0,
                "sma200": 100.0,
                "rsi14": 45.0,
                "atr14": 2.0,
                "bb_lower": 95.0,
                "volume_avg_20": 1000.0,
                "atr_avg_60": 2.0,
                "price_source": "close",
                "price_fresh": False,
            },
        ),
    )
    bot._handle_session_transition = AsyncMock()
    bot._check_warmup = AsyncMock(return_value=True)
    bot._attempt_grid_creation = AsyncMock()

    monkeypatch.setattr("main.is_market_open", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(
        "main.get_session_state",
        lambda _spec: SimpleNamespace(
            can_open_new_grid=True,
            is_pre_close=False,
            status="ABERTA",
        ),
    )
    monkeypatch.setattr("main.build_contract", lambda _spec: MagicMock(symbol="AAPL"))

    await TradingBot._process_symbol(bot, spec)

    bot._attempt_grid_creation.assert_not_awaited()


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

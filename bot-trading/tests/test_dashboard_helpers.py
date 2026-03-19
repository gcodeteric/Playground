from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from dashboard.helpers import (
    build_status_summary,
    compute_kpis,
    emit_command,
    load_grids_state,
    load_heartbeat,
    load_json_file,
    load_positions,
    load_trades_dataframe,
)


def test_load_json_file_returns_none_for_invalid_json(tmp_path: Path):
    path = tmp_path / "broken.json"
    path.write_text("{not-json", encoding="utf-8")
    assert load_json_file(path) is None


def test_load_trades_dataframe_parses_wrapper_and_timestamps(tmp_path: Path):
    path = tmp_path / "trades_log.json"
    path.write_text(
        json.dumps(
            {
                "trades": [
                    {
                        "timestamp": "2026-03-17T10:00:00+00:00",
                        "symbol": "AAPL",
                        "pnl": "12.5",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    df = load_trades_dataframe(path)

    assert len(df) == 1
    assert float(df["pnl"].iloc[0]) == 12.5
    assert str(df["module"].iloc[0]) == "kotegawa"
    assert pd.api.types.is_datetime64_any_dtype(df["timestamp"])


def test_load_grids_state_handles_root_grids_schema(tmp_path: Path):
    path = tmp_path / "grids_state.json"
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "grids": [
                    {"id": "grid_1", "symbol": "AAPL", "levels": []},
                    {"symbol": "SPY", "levels": []},
                ],
            }
        ),
        encoding="utf-8",
    )

    grids = load_grids_state(path)

    assert len(grids) == 2
    assert grids[0]["id"] == "grid_1"
    assert grids[1]["id"] == "grid_1" or grids[1]["id"].startswith("grid_")


def test_load_positions_derives_from_bought_levels():
    grids = [
        {
            "id": "grid_aapl",
            "symbol": "AAPL",
            "module": "kotegawa",
            "regime": "BULL",
            "levels": [
                {"level": 1, "status": "pending"},
                {
                    "level": 2,
                    "status": "bought",
                    "quantity": 10,
                    "buy_price": 95.0,
                    "stop_price": 92.0,
                    "sell_price": 100.0,
                    "current_price": 97.5,
                    "price_source": "snapshot",
                },
            ],
        }
    ]

    positions_df = load_positions(grids_state=grids)

    assert len(positions_df) == 1
    assert positions_df.iloc[0]["symbol"] == "AAPL"
    assert int(positions_df.iloc[0]["quantity"]) == 10
    assert float(positions_df.iloc[0]["open_notional"]) == 950.0
    assert float(positions_df.iloc[0]["open_risk_to_stop"]) == 30.0
    assert float(positions_df.iloc[0]["unrealized_pnl"]) == 25.0


def test_emit_command_writes_json_envelope(tmp_path: Path):
    path = emit_command("pause", {"reason": "manual"}, data_dir=tmp_path)
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert path.parent.name == "commands"
    assert payload["command"] == "pause"
    assert payload["payload"]["reason"] == "manual"
    assert payload["paper_only"] is True


def test_compute_kpis_and_status_summary(tmp_path: Path):
    trades_path = tmp_path / "trades_log.json"
    trades_path.write_text(
        json.dumps(
            {
                "trades": [
                    {
                        "timestamp": "2026-03-17T10:00:00+00:00",
                        "symbol": "AAPL",
                        "pnl": 100.0,
                    },
                    {
                        "timestamp": "2026-03-17T11:00:00+00:00",
                        "symbol": "SPY",
                        "pnl": -40.0,
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    trades_df = load_trades_dataframe(trades_path)
    grids = [
        {
            "id": "grid_1",
            "symbol": "AAPL",
            "current_price": 97.5,
            "price_source": "snapshot",
            "levels": [
                {
                    "level": 1,
                    "status": "bought",
                    "quantity": 10,
                    "buy_price": 95.0,
                    "stop_price": 92.0,
                    "sell_price": 100.0,
                }
            ],
        }
    ]
    preflight = {
        "telegram_status": "disabled",
        "last_preflight": "2026-03-17T09:00:00+00:00",
        "capital": 100_000.0,
    }
    heartbeat_path = tmp_path / "heartbeat.json"
    heartbeat_path.write_text(
        json.dumps(
            {
                "timestamp": "2026-03-17T12:00:00+00:00",
                "manual_pause": False,
                "entry_halt_reason": "daily_limit",
                "emergency_halt": True,
                "ib_connected": True,
                "last_error": "broker warning",
                "last_cycle_started_at": "2026-03-17T11:59:00+00:00",
                "last_cycle_completed_at": "2026-03-17T12:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )

    kpis = compute_kpis(trades_df, {}, grids, preflight, data_dir=tmp_path)
    status = build_status_summary(kpis, now=datetime.now(UTC))

    assert kpis["trades_count"] == 2
    assert kpis["total_pnl"] == 60.0
    assert kpis["active_grids"] == 1
    assert kpis["open_positions"] == 1
    assert kpis["open_notional"] == 950.0
    assert kpis["open_risk_to_stop"] == 30.0
    assert kpis["unrealized_pnl"] == 25.0
    assert kpis["entry_halt_reason"] == "daily_limit"
    assert kpis["emergency_halt"] is True
    assert kpis["last_error"] == "broker warning"
    assert status["paper_mode"] == "PAPER"
    assert status["bot_state"] == "EMERGENCY_HALT"
    assert status["risk_state"] == "daily_limit"

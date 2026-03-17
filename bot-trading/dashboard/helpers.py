from __future__ import annotations

import json
import math
from collections import deque
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
COMMANDS_DIR = DATA_DIR / "commands"
ALLOWED_COMMANDS = {"pause", "resume", "reconcile_now", "export_snapshot"}


def load_json_file(path: Path) -> dict[str, Any] | list[Any] | None:
    """Lê JSON de forma tolerante, devolvendo ``None`` em erro."""
    try:
        if not path.exists():
            return None
        raw = path.read_text(encoding="utf-8").strip()
        if not raw or raw == "null":
            return None
        return json.loads(raw)
    except (OSError, json.JSONDecodeError):
        return None


def load_heartbeat(path: Path) -> dict[str, Any] | None:
    """Lê o ficheiro de heartbeat do bot, devolvendo ``None`` se indisponível."""
    data = load_json_file(path)
    if isinstance(data, dict):
        return data
    return None


def load_log_tail(path: Path, max_lines: int = 200) -> list[str]:
    """Lê apenas as últimas ``max_lines`` linhas do log."""
    try:
        with path.open("r", encoding="utf-8") as handle:
            return list(deque(handle, maxlen=max_lines))
    except OSError:
        return []


def load_trades_dataframe(path: Path) -> pd.DataFrame:
    """Normaliza o trades log num DataFrame tolerante a schemas parciais."""
    data = load_json_file(path)
    trades: list[dict[str, Any]]
    if isinstance(data, dict):
        trades = data.get("trades", []) if isinstance(data.get("trades"), list) else []
    elif isinstance(data, list):
        trades = [item for item in data if isinstance(item, dict)]
    else:
        trades = []

    if not trades:
        return pd.DataFrame()

    df = pd.DataFrame(trades)
    for col in ("timestamp", "open_time", "close_time", "date"):
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce", utc=True)

    pnl_col = next(
        (col for col in ("pnl", "profit_loss", "realized_pnl") if col in df.columns),
        None,
    )
    if pnl_col is None:
        df["pnl"] = 0.0
    else:
        df["pnl"] = pd.to_numeric(df[pnl_col], errors="coerce").fillna(0.0)

    if "module" not in df.columns:
        if "strategy" in df.columns:
            df["module"] = df["strategy"]
        elif "source" in df.columns:
            df["module"] = df["source"]
        else:
            df["module"] = "kotegawa"

    return df


def load_metrics(path: Path) -> dict[str, Any]:
    """Lê o ficheiro de métricas e achata o bloco ``metrics`` se existir."""
    data = load_json_file(path)
    if not isinstance(data, dict):
        return {}

    merged: dict[str, Any] = {}
    metrics_block = data.get("metrics")
    if isinstance(metrics_block, dict):
        merged.update(metrics_block)

    for key, value in data.items():
        if key != "metrics":
            merged[key] = value
    return merged


def load_grids_state(path: Path) -> list[dict[str, Any]]:
    """Normaliza o estado de grids para uma lista de dicionários."""
    data = load_json_file(path)
    if isinstance(data, dict) and isinstance(data.get("grids"), list):
        grids: list[dict[str, Any]] = []
        for index, item in enumerate(data["grids"]):
            if not isinstance(item, dict):
                continue
            grid = dict(item)
            grid.setdefault("id", f"grid_{index}")
            grids.append(grid)
        return grids

    if isinstance(data, dict):
        grids = []
        for key, value in data.items():
            if not isinstance(value, dict):
                continue
            grid = dict(value)
            grid.setdefault("id", str(key))
            grids.append(grid)
        return grids

    return []


def load_positions(
    path: Path | None = None,
    *,
    grids_state: list[dict[str, Any]] | None = None,
) -> pd.DataFrame:
    """
    Carrega posições. Se não existir ficheiro próprio, deriva das grids activas.
    """
    rows: list[dict[str, Any]] = []

    if path is not None:
        data = load_json_file(path)
        if isinstance(data, list):
            rows = [item for item in data if isinstance(item, dict)]
        elif isinstance(data, dict) and isinstance(data.get("positions"), list):
            rows = [item for item in data["positions"] if isinstance(item, dict)]

    if not rows and grids_state:
        for grid in grids_state:
            levels = grid.get("levels", [])
            if not isinstance(levels, list):
                continue
            for level in levels:
                if not isinstance(level, dict) or level.get("status") != "bought":
                    continue
                rows.append(
                    {
                        "symbol": grid.get("symbol", "—"),
                        "grid_id": grid.get("id", "—"),
                        "module": grid.get("module", "kotegawa"),
                        "regime": grid.get("regime", "UNKNOWN"),
                        "level": level.get("level"),
                        "quantity": level.get("quantity"),
                        "entry_price": level.get("buy_price"),
                        "stop_price": level.get("stop_price"),
                        "take_profit_price": level.get("sell_price"),
                    }
                )

    return pd.DataFrame(rows)


def emit_command(
    command_name: str,
    payload: dict[str, Any] | None = None,
    *,
    data_dir: Path = DATA_DIR,
) -> Path:
    """Emite um ficheiro de comando local para consumo seguro pelo bot."""
    if command_name not in ALLOWED_COMMANDS:
        raise ValueError(f"Comando não suportado: {command_name}")

    commands_dir = data_dir / "commands"
    commands_dir.mkdir(parents=True, exist_ok=True)
    created_at = datetime.now(UTC).isoformat()
    filename = (
        f"{created_at.replace(':', '').replace('-', '').replace('+00:00', 'Z')}"
        f"_{command_name}_{uuid4().hex[:8]}.json"
    )
    envelope = {
        "command": command_name,
        "payload": payload or {},
        "paper_only": True,
        "status": "pending",
        "created_at": created_at,
    }
    command_path = commands_dir / filename
    command_path.write_text(
        json.dumps(envelope, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return command_path


def safe_metric(value: Any, default: str = "—") -> Any:
    """Devolve ``default`` para valores vazios, nulos ou NaN."""
    if value is None:
        return default
    if isinstance(value, float) and math.isnan(value):
        return default
    if value == "":
        return default
    return value


def compute_kpis(
    trades_df: pd.DataFrame,
    metrics: dict[str, Any],
    grids_state: list[dict[str, Any]],
    preflight_state: dict[str, Any],
    *,
    data_dir: Path = DATA_DIR,
) -> dict[str, Any]:
    """Calcula KPIs apenas a partir de dados reais disponíveis."""
    trades_count = int(len(trades_df))
    total_pnl = float(trades_df["pnl"].sum()) if "pnl" in trades_df.columns else 0.0
    wins_df = trades_df[trades_df["pnl"] > 0] if "pnl" in trades_df.columns else trades_df.iloc[0:0]
    losses_df = trades_df[trades_df["pnl"] < 0] if "pnl" in trades_df.columns else trades_df.iloc[0:0]
    avg_win = float(wins_df["pnl"].mean()) if not wins_df.empty else 0.0
    avg_loss = float(losses_df["pnl"].mean()) if not losses_df.empty else 0.0
    gross_profit = float(wins_df["pnl"].sum()) if not wins_df.empty else 0.0
    gross_loss = abs(float(losses_df["pnl"].sum())) if not losses_df.empty else 0.0
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else None
    win_rate = float(len(wins_df) / trades_count * 100.0) if trades_count else 0.0

    ts_col = next(
        (
            col for col in ("timestamp", "close_time", "date")
            if col in trades_df.columns and pd.api.types.is_datetime64_any_dtype(trades_df[col])
        ),
        None,
    )
    today_start = pd.Timestamp.now(tz=UTC).normalize()
    if ts_col is not None:
        day_df = trades_df[trades_df[ts_col] >= today_start]
        last_signal_time = trades_df[ts_col].max() if not trades_df.empty else None
    else:
        day_df = trades_df.iloc[0:0]
        last_signal_time = None

    daily_pnl = float(day_df["pnl"].sum()) if "pnl" in day_df.columns else 0.0
    capital = metrics.get("capital") or metrics.get("initial_capital") or preflight_state.get("capital")
    capital = float(capital) if capital not in (None, "") else None
    estimated_equity = capital if capital is not None else None
    if estimated_equity is None and metrics.get("initial_capital") is not None:
        estimated_equity = float(metrics["initial_capital"]) + total_pnl

    positions_df = load_positions(grids_state=grids_state)
    active_grids = len(grids_state)
    open_positions = int(len(positions_df))

    max_drawdown = metrics.get("max_drawdown")
    if max_drawdown is None and "pnl" in trades_df.columns and not trades_df.empty:
        equity_curve = trades_df["pnl"].cumsum()
        drawdown_curve = equity_curve.cummax() - equity_curve
        max_drawdown = float(drawdown_curve.max()) if not drawdown_curve.empty else 0.0

    heartbeat_data = load_heartbeat(data_dir / "heartbeat.json")
    if heartbeat_data is not None and isinstance(heartbeat_data.get("timestamp"), str):
        try:
            heartbeat = datetime.fromisoformat(heartbeat_data["timestamp"])
            if heartbeat.tzinfo is None:
                heartbeat = heartbeat.replace(tzinfo=UTC)
        except (TypeError, ValueError):
            heartbeat = None
    else:
        heartbeat_candidates = [
            data_dir / "bot.log",
            data_dir / "metrics.json",
            data_dir / "grids_state.json",
            data_dir / "trades_log.json",
            data_dir / "preflight_state.json",
        ]
        mtimes = [
            datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
            for path in heartbeat_candidates if path.exists()
        ]
        heartbeat = max(mtimes) if mtimes else None

    manual_pause = heartbeat_data.get("manual_pause", False) if heartbeat_data else False
    ib_connected = heartbeat_data.get("ib_connected", False) if heartbeat_data else False

    reconciliation_path = data_dir / "reconciliation.log"
    last_reconciliation = (
        datetime.fromtimestamp(reconciliation_path.stat().st_mtime, tz=UTC)
        if reconciliation_path.exists() else None
    )

    commands_dir = data_dir / "commands"
    pending_commands = len(list(commands_dir.glob("*.json"))) if commands_dir.exists() else 0

    return {
        "capital": capital,
        "estimated_equity": estimated_equity,
        "daily_pnl": daily_pnl,
        "total_pnl": total_pnl,
        "trades_count": trades_count,
        "win_rate": win_rate,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "profit_factor": profit_factor,
        "max_drawdown": max_drawdown,
        "open_positions": open_positions,
        "active_grids": active_grids,
        "last_signal_time": last_signal_time,
        "last_reconciliation_time": last_reconciliation,
        "heartbeat": heartbeat,
        "manual_pause": manual_pause,
        "ib_connected": ib_connected,
        "telegram_status": preflight_state.get("telegram_status", "unknown"),
        "preflight_status": "ok" if preflight_state else "missing",
        "last_preflight": preflight_state.get("last_preflight"),
        "pending_commands": pending_commands,
    }


def build_status_summary(
    kpis: dict[str, Any],
    *,
    now: datetime | None = None,
) -> dict[str, str]:
    """Constrói um resumo de estado simples para a UI."""
    now_utc = now or datetime.now(UTC)
    heartbeat = kpis.get("heartbeat")
    if isinstance(heartbeat, pd.Timestamp):
        heartbeat = heartbeat.to_pydatetime()
    if isinstance(heartbeat, datetime):
        age_seconds = (now_utc - heartbeat.astimezone(UTC)).total_seconds()
    else:
        age_seconds = None

    if age_seconds is None:
        health = "SEM_HEARTBEAT"
        tone = "warning"
    elif age_seconds <= 600:
        health = "OK"
        tone = "ok"
    elif age_seconds <= 3600:
        health = "STALE"
        tone = "warning"
    else:
        health = "PARADO"
        tone = "danger"

    return {
        "health": health,
        "tone": tone,
        "paper_mode": "PAPER",
        "telegram_status": str(kpis.get("telegram_status", "unknown")),
        "preflight_status": str(kpis.get("preflight_status", "missing")),
        "manual_pause": bool(kpis.get("manual_pause", False)),
        "ib_connected": bool(kpis.get("ib_connected", False)),
    }

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

APP_DIR = Path(__file__).resolve().parent
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))
if str(APP_DIR.parent) not in sys.path:
    sys.path.insert(0, str(APP_DIR.parent))

try:
    from dashboard.helpers import (
        DATA_DIR,
        build_status_summary,
        compute_kpis,
        emit_command,
        load_grids_state,
        load_json_file,
        load_log_tail,
        load_metrics,
        load_positions,
        load_trades_dataframe,
        safe_metric,
    )
except ModuleNotFoundError:  # pragma: no cover - compatibilidade streamlit local
    from helpers import (  # type: ignore[no-redef]
        DATA_DIR,
        build_status_summary,
        compute_kpis,
        emit_command,
        load_grids_state,
        load_json_file,
        load_log_tail,
        load_metrics,
        load_positions,
        load_trades_dataframe,
        safe_metric,
    )

PAPER_LABEL = "PAPER MODE"
DEFAULT_REFRESH_SECONDS = 5
MODULE_LABELS = {
    "kotegawa": "Kotegawa (Core)",
    "sector_rotation": "Rotação Sectorial",
    "gap_fade": "Gap Fade",
    "forex_mr": "Forex MR",
    "forex_breakout": "Forex Breakout",
    "futures_mr": "Futuros MR",
    "futures_trend": "Trend Following",
    "intl_etf_mr": "ETFs Internacionais",
    "commodity_mr": "Commodities MR",
    "options_premium": "Options Premium",
    "bond_mr_hedge": "Bond MR Hedge",
}
RISK_LIMITS = {"daily": 0.03, "weekly": 0.06, "monthly": 0.10}


def _file_signature(path: Path) -> tuple[str, int]:
    """Gera uma assinatura simples baseada em caminho e mtime."""
    try:
        return str(path), int(path.stat().st_mtime_ns)
    except OSError:
        return str(path), -1


@st.cache_data(show_spinner=False)
def _load_metrics_cached(path_str: str, _signature: int) -> dict[str, Any]:
    return load_metrics(Path(path_str))


@st.cache_data(show_spinner=False)
def _load_trades_cached(path_str: str, _signature: int) -> pd.DataFrame:
    return load_trades_dataframe(Path(path_str))


@st.cache_data(show_spinner=False)
def _load_grids_cached(path_str: str, _signature: int) -> list[dict[str, Any]]:
    return load_grids_state(Path(path_str))


@st.cache_data(show_spinner=False)
def _load_json_cached(path_str: str, _signature: int) -> dict[str, Any]:
    data = load_json_file(Path(path_str))
    return data if isinstance(data, dict) else {}


@st.cache_data(show_spinner=False)
def _load_logs_cached(path_str: str, _signature: int, max_lines: int) -> list[str]:
    return load_log_tail(Path(path_str), max_lines=max_lines)


def _fmt_eur(value: Any) -> str:
    numeric = value if isinstance(value, (int, float)) else None
    return f"€{numeric:,.2f}" if numeric is not None else "—"


def _fmt_dt(value: Any) -> str:
    if value is None or value == "—":
        return "—"
    if isinstance(value, pd.Timestamp):
        value = value.to_pydatetime()
    if isinstance(value, datetime):
        return value.astimezone(UTC).strftime("%Y-%m-%d %H:%M UTC")
    return str(value)


def _risk_tone(value: float, limit: float) -> str:
    if limit <= 0:
        return "secondary"
    ratio = abs(value) / limit
    if ratio >= 1.0:
        return "danger"
    if ratio >= 0.7:
        return "warning"
    return "ok"


def _build_equity_curve(trades_df: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    if trades_df.empty or "pnl" not in trades_df.columns:
        fig.add_annotation(
            text="Sem trades ainda",
            x=0.5,
            y=0.5,
            xref="paper",
            yref="paper",
            showarrow=False,
        )
    else:
        df = trades_df.copy()
        df["equity"] = df["pnl"].cumsum()
        x = df["timestamp"] if "timestamp" in df.columns else list(range(len(df)))
        fig.add_trace(
            go.Scatter(
                x=x,
                y=df["equity"],
                mode="lines",
                line={"color": "#00c853", "width": 2},
                fill="tozeroy",
                fillcolor="rgba(0,200,83,0.10)",
                name="Equity",
            )
        )
    fig.update_layout(height=320, margin={"l": 8, "r": 8, "t": 8, "b": 8})
    return fig


def _build_pnl_by_symbol(trades_df: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    if trades_df.empty or "symbol" not in trades_df.columns or "pnl" not in trades_df.columns:
        fig.add_annotation(
            text="Sem dados suficientes",
            x=0.5,
            y=0.5,
            xref="paper",
            yref="paper",
            showarrow=False,
        )
        return fig
    grouped = trades_df.groupby("symbol", dropna=False)["pnl"].sum().sort_values(ascending=False)
    colors = ["#00c853" if value >= 0 else "#d50000" for value in grouped.values]
    fig.add_trace(go.Bar(x=grouped.index.tolist(), y=grouped.values.tolist(), marker_color=colors))
    fig.update_layout(height=320, margin={"l": 8, "r": 8, "t": 8, "b": 8})
    return fig


def _build_trades_per_day(trades_df: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    if trades_df.empty or "timestamp" not in trades_df.columns:
        fig.add_annotation(text="Sem timestamps suficientes", x=0.5, y=0.5, xref="paper", yref="paper", showarrow=False)
        return fig
    df = trades_df.dropna(subset=["timestamp"]).copy()
    if df.empty:
        fig.add_annotation(text="Sem timestamps suficientes", x=0.5, y=0.5, xref="paper", yref="paper", showarrow=False)
        return fig
    df["day"] = df["timestamp"].dt.strftime("%Y-%m-%d")
    counts = df.groupby("day").size()
    fig.add_trace(go.Bar(x=counts.index.tolist(), y=counts.values.tolist(), marker_color="#1e88e5"))
    fig.update_layout(height=320, margin={"l": 8, "r": 8, "t": 8, "b": 8})
    return fig


def _build_drawdown_curve(trades_df: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    if trades_df.empty or "pnl" not in trades_df.columns:
        fig.add_annotation(text="Sem trades ainda", x=0.5, y=0.5, xref="paper", yref="paper", showarrow=False)
        return fig
    equity = trades_df["pnl"].cumsum()
    drawdown = equity.cummax() - equity
    x = trades_df["timestamp"] if "timestamp" in trades_df.columns else list(range(len(drawdown)))
    fig.add_trace(go.Scatter(x=x, y=drawdown, mode="lines", line={"color": "#ff6d00", "width": 2}))
    fig.update_layout(height=320, margin={"l": 8, "r": 8, "t": 8, "b": 8})
    return fig


def _grid_rows(grids_state: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for grid in grids_state:
        levels = grid.get("levels", [])
        bought = len([level for level in levels if isinstance(level, dict) and level.get("status") == "bought"]) if isinstance(levels, list) else 0
        rows.append(
            {
                "grid_id": grid.get("id", "—"),
                "symbol": grid.get("symbol", "—"),
                "module": MODULE_LABELS.get(str(grid.get("module", "kotegawa")), str(grid.get("module", "—"))),
                "regime": str(grid.get("regime", "UNKNOWN")).upper(),
                "status": str(grid.get("status", "unknown")).upper(),
                "levels_used": bought,
                "levels_total": len(levels) if isinstance(levels, list) else 0,
                "center_price": grid.get("center_price"),
                "total_pnl": grid.get("total_pnl"),
                "created_at": grid.get("created_at") or grid.get("opened_at"),
            }
        )
    return rows


def _render_header(status: dict[str, str], kpis: dict[str, Any]) -> None:
    title_col, status_col, meta_col = st.columns([2.2, 1.2, 1.2])
    with title_col:
        st.title("Trading Bot v8 — Dashboard Pro")
        st.caption("Observabilidade e controlo seguro local, exclusivamente em PAPER.")
    with status_col:
        tone_color = {"ok": "#00c853", "warning": "#ff6d00", "danger": "#d50000"}.get(status["tone"], "#607d8b")
        st.markdown(
            (
                f"<div style='padding:0.9rem;border-radius:0.8rem;background:{tone_color};"
                "text-align:center;font-weight:700;'>"
                f"{PAPER_LABEL} • {status['health']}</div>"
            ),
            unsafe_allow_html=True,
        )
    with meta_col:
        st.metric("Heartbeat", _fmt_dt(kpis.get("heartbeat")))
        st.metric("Preflight", _fmt_dt(kpis.get("last_preflight")))


def _render_overview(kpis: dict[str, Any], trades_df: pd.DataFrame, status: dict[str, str]) -> None:
    metrics = st.columns(6)
    metrics[0].metric("Capital", _fmt_eur(kpis.get("capital")))
    metrics[1].metric("Equity estimada", _fmt_eur(kpis.get("estimated_equity")))
    metrics[2].metric("PnL diário", _fmt_eur(kpis.get("daily_pnl")))
    metrics[3].metric("PnL acumulado", _fmt_eur(kpis.get("total_pnl")))
    metrics[4].metric("Trades", str(kpis.get("trades_count", 0)))
    metrics[5].metric("Win rate", f"{float(kpis.get('win_rate', 0.0)):.1f}%")

    info1, info2, info3, info4 = st.columns(4)
    info1.metric("Open positions", str(kpis.get("open_positions", 0)))
    info2.metric("Active grids", str(kpis.get("active_grids", 0)))
    info3.metric("Telegram", str(status.get("telegram_status", "unknown")).upper())
    info4.metric("Pending commands", str(kpis.get("pending_commands", 0)))

    left, right = st.columns(2)
    with left:
        st.subheader("Equity curve")
        st.plotly_chart(_build_equity_curve(trades_df), use_container_width=True)
    with right:
        st.subheader("PnL por símbolo")
        st.plotly_chart(_build_pnl_by_symbol(trades_df), use_container_width=True)


def _render_trading(trades_df: pd.DataFrame) -> None:
    if trades_df.empty:
        st.info("Sem trades registados. O dashboard continua funcional com o bot parado.")
        return

    module_options = ["Todos"] + sorted(trades_df["module"].dropna().astype(str).unique().tolist())
    symbol_options = ["Todos"] + sorted(trades_df["symbol"].dropna().astype(str).unique().tolist()) if "symbol" in trades_df.columns else ["Todos"]
    selected_module = st.selectbox("Módulo", module_options)
    selected_symbol = st.selectbox("Símbolo", symbol_options)

    filtered = trades_df.copy()
    if selected_module != "Todos":
        filtered = filtered[filtered["module"].astype(str) == selected_module]
    if selected_symbol != "Todos" and "symbol" in filtered.columns:
        filtered = filtered[filtered["symbol"].astype(str) == selected_symbol]

    st.plotly_chart(_build_trades_per_day(filtered), use_container_width=True)
    show_cols = [col for col in ["timestamp", "symbol", "module", "side", "price", "quantity", "pnl", "regime"] if col in filtered.columns]
    st.dataframe(filtered[show_cols].sort_values("timestamp", ascending=False), use_container_width=True, hide_index=True)
    st.download_button(
        "Exportar trades CSV",
        filtered.to_csv(index=False).encode("utf-8"),
        file_name="dashboard_trades.csv",
        mime="text/csv",
    )


def _render_risk(kpis: dict[str, Any], metrics: dict[str, Any]) -> None:
    risk_cols = st.columns(3)
    for column, key, label in zip(
        risk_cols,
        ("daily", "weekly", "monthly"),
        ("Diário", "Semanal", "Mensal"),
        strict=True,
    ):
        value = float(metrics.get(f"{key}_loss", 0.0) or 0.0)
        limit = RISK_LIMITS[key]
        ratio = min(abs(value) / limit, 1.0) if limit > 0 else 0.0
        column.metric(f"Kill Switch {label}", f"{value * 100:.2f}%")
        column.progress(ratio, text=f"{ratio * 100:.1f}% do limite")
        tone = _risk_tone(value, limit)
        column.caption({"ok": "OK", "warning": "WARNING", "danger": "DANGER"}[tone])

    meta_cols = st.columns(3)
    meta_cols[0].metric("Average win", _fmt_eur(kpis.get("avg_win")))
    meta_cols[1].metric("Average loss", _fmt_eur(kpis.get("avg_loss")))
    profit_factor = kpis.get("profit_factor")
    meta_cols[2].metric("Profit factor", f"{float(profit_factor):.2f}" if profit_factor is not None else "—")


def _render_performance(trades_df: pd.DataFrame, kpis: dict[str, Any]) -> None:
    cols = st.columns(2)
    with cols[0]:
        st.subheader("Drawdown curve")
        st.plotly_chart(_build_drawdown_curve(trades_df), use_container_width=True)
    with cols[1]:
        wins = int((trades_df["pnl"] > 0).sum()) if not trades_df.empty and "pnl" in trades_df.columns else 0
        losses = int((trades_df["pnl"] < 0).sum()) if not trades_df.empty and "pnl" in trades_df.columns else 0
        pie = go.Figure(data=[go.Pie(labels=["Wins", "Losses"], values=[wins, losses], hole=0.45)])
        pie.update_layout(height=320, margin={"l": 8, "r": 8, "t": 8, "b": 8})
        st.subheader("Distribuição wins/losses")
        st.plotly_chart(pie, use_container_width=True)

    st.metric("Max drawdown", _fmt_eur(kpis.get("max_drawdown")))


def _render_positions(grids_state: list[dict[str, Any]]) -> None:
    positions_df = load_positions(grids_state=grids_state)
    grids_df = pd.DataFrame(_grid_rows(grids_state))

    left, right = st.columns(2)
    with left:
        st.subheader("Posições abertas")
        if positions_df.empty:
            st.info("Sem posições abertas derivadas das grids activas.")
        else:
            st.dataframe(positions_df, use_container_width=True, hide_index=True)
    with right:
        st.subheader("Estado das grids")
        if grids_df.empty:
            st.info("Sem grids activas.")
        else:
            st.dataframe(grids_df, use_container_width=True, hide_index=True)


def _render_logs(log_lines: list[str]) -> None:
    if not log_lines:
        st.info("Sem logs disponíveis.")
        return
    level = st.selectbox("Filtro de nível", ["Tudo", "ERROR", "WARNING", "INFO", "DEBUG"])
    filtered = log_lines if level == "Tudo" else [line for line in log_lines if level in line]
    if not filtered:
        st.info("Sem linhas para o filtro seleccionado.")
        return
    st.code("".join(filtered[-200:]), language="text")


def _render_system_actions(
    metrics: dict[str, Any],
    preflight: dict[str, Any],
    kpis: dict[str, Any],
) -> None:
    st.subheader("System health")
    data_files = [
        DATA_DIR / "metrics.json",
        DATA_DIR / "trades_log.json",
        DATA_DIR / "grids_state.json",
        DATA_DIR / "preflight_state.json",
        DATA_DIR / "bot.log",
    ]
    file_rows = []
    for path in data_files:
        exists = path.exists()
        file_rows.append(
            {
                "ficheiro": path.name,
                "existe": "✅" if exists else "❌",
                "modificado": _fmt_dt(datetime.fromtimestamp(path.stat().st_mtime, tz=UTC) if exists else None),
            }
        )
    st.dataframe(pd.DataFrame(file_rows), use_container_width=True, hide_index=True)

    st.subheader("Ações seguras (emit command)")
    action_cols = st.columns(4)
    for column, command in zip(
        action_cols,
        ["pause", "resume", "reconcile_now", "export_snapshot"],
        strict=True,
    ):
        if column.button(f"Emitir {command}", use_container_width=True):
            command_path = emit_command(command)
            st.success(f"Comando emitido: {command_path.name}")

    snapshot = {
        "paper_mode": True,
        "kpis": {key: str(value) if isinstance(value, (datetime, pd.Timestamp)) else value for key, value in kpis.items()},
        "metrics": metrics,
        "preflight": preflight,
    }
    st.download_button(
        "Exportar snapshot JSON",
        json.dumps(snapshot, indent=2, ensure_ascii=False).encode("utf-8"),
        file_name="dashboard_snapshot.json",
        mime="application/json",
    )


def main() -> None:
    st.set_page_config(
        page_title="Trading Bot v8 Dashboard",
        page_icon="📄",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    if "auto_refresh" not in st.session_state:
        st.session_state.auto_refresh = True
    if "refresh_seconds" not in st.session_state:
        st.session_state.refresh_seconds = DEFAULT_REFRESH_SECONDS

    st.sidebar.header("Controlo do dashboard")
    st.session_state.auto_refresh = st.sidebar.toggle("Auto-refresh", value=st.session_state.auto_refresh)
    st.session_state.refresh_seconds = st.sidebar.slider(
        "Refresh (segundos)",
        min_value=5,
        max_value=60,
        value=int(st.session_state.refresh_seconds),
        step=5,
    )
    if st.sidebar.button("Refresh manual"):
        st.cache_data.clear()
        st.rerun()

    metrics_path = DATA_DIR / "metrics.json"
    trades_path = DATA_DIR / "trades_log.json"
    grids_path = DATA_DIR / "grids_state.json"
    preflight_path = DATA_DIR / "preflight_state.json"
    log_path = DATA_DIR / "bot.log"

    metrics = _load_metrics_cached(*_file_signature(metrics_path))
    trades_df = _load_trades_cached(*_file_signature(trades_path))
    grids_state = _load_grids_cached(*_file_signature(grids_path))
    preflight = _load_json_cached(*_file_signature(preflight_path))
    log_lines = _load_logs_cached(*_file_signature(log_path), max_lines=200)

    kpis = compute_kpis(trades_df, metrics, grids_state, preflight, data_dir=DATA_DIR)
    status = build_status_summary(kpis)

    _render_header(status, kpis)
    st.caption(
        f"{PAPER_LABEL} • Telegram: {status['telegram_status']} • "
        f"Preflight: {status['preflight_status']} • "
        f"Heartbeat: {_fmt_dt(kpis.get('heartbeat'))}"
    )
    st.divider()

    tabs = st.tabs(
        [
            "Overview",
            "Trading",
            "Risk",
            "Performance",
            "Positions",
            "Logs/Alerts",
            "System/Actions",
        ]
    )

    with tabs[0]:
        _render_overview(kpis, trades_df, status)
    with tabs[1]:
        _render_trading(trades_df)
    with tabs[2]:
        _render_risk(kpis, metrics)
    with tabs[3]:
        _render_performance(trades_df, kpis)
    with tabs[4]:
        _render_positions(grids_state)
    with tabs[5]:
        _render_logs(log_lines)
    with tabs[6]:
        _render_system_actions(metrics, preflight, kpis)

    if st.session_state.auto_refresh:
        st.markdown(
            (
                "<script>setTimeout(function(){window.location.reload();},"
                f"{int(st.session_state.refresh_seconds) * 1000});</script>"
            ),
            unsafe_allow_html=True,
        )


if __name__ == "__main__":
    main()

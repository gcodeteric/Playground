from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# ── Configuração ──────────────────────────────────────────────
DATA_DIR = Path(__file__).parent.parent / "data"
REFRESH_INTERVAL = 5  # segundos

KILL_SWITCH_LIMITS = {"daily": 0.03, "weekly": 0.06, "monthly": 0.10}

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

REGIME_COLOURS = {
    "BULL": "#00c853",
    "BEAR": "#d50000",
    "SIDEWAYS": "#ff6d00",
    "RANGING": "#aa00ff",
    "UNKNOWN": "#607d8b",
}


# ── Carregamento de dados ──────────────────────────────────────

@st.cache_data(ttl=REFRESH_INTERVAL)
def load_metrics() -> dict:
    try:
        raw = (DATA_DIR / "metrics.json").read_text(encoding="utf-8").strip()
        return json.loads(raw) if raw and raw != "null" else {}
    except Exception:
        return {}


@st.cache_data(ttl=REFRESH_INTERVAL)
def load_trades() -> pd.DataFrame:
    try:
        raw = (DATA_DIR / "trades_log.json").read_text(encoding="utf-8").strip()
        data = json.loads(raw) if raw and raw != "null" else {}
        trades = data.get("trades", []) if isinstance(data, dict) else data
        if not trades:
            return pd.DataFrame()
        df = pd.DataFrame(trades)
        for col in ("timestamp", "open_time", "close_time", "date"):
            if col in df.columns:
                df[col] = pd.to_datetime(df[col], errors="coerce")
        for col in ("pnl", "profit_loss", "realized_pnl"):
            if col in df.columns:
                df["pnl"] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
                break
        if "pnl" not in df.columns:
            df["pnl"] = 0.0
        return df
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=REFRESH_INTERVAL)
def load_grids() -> dict:
    try:
        raw = (DATA_DIR / "grids_state.json").read_text(encoding="utf-8").strip()
        data = json.loads(raw) if raw and raw != "null" else {}
        if isinstance(data, dict) and "grids" in data and isinstance(data["grids"], list):
            return {
                item.get("id", f"grid_{idx}"): item
                for idx, item in enumerate(data["grids"])
                if isinstance(item, dict)
            }
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


@st.cache_data(ttl=REFRESH_INTERVAL)
def load_log_tail(n_lines: int = 100) -> list[str]:
    try:
        lines = (DATA_DIR / "bot.log").read_text(encoding="utf-8").splitlines()
        return lines[-n_lines:]
    except Exception:
        return []


# ── Helpers ───────────────────────────────────────────────────

def safe_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def pct_bar(value: float, limit: float, label: str) -> None:
    ratio = min(value / limit, 1.0) if limit > 0 else 0.0
    st.markdown(f"**{label}** — `{value * 100:.2f}%` / `{limit * 100:.1f}%`")
    st.progress(ratio, text=f"{ratio * 100:.1f}% do limite usado")


def build_equity_curve(trades_df: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    if trades_df.empty or "pnl" not in trades_df.columns:
        fig.add_annotation(
            text="Sem trades ainda",
            xref="paper",
            yref="paper",
            x=0.5,
            y=0.5,
            showarrow=False,
            font={"size": 16, "color": "#607d8b"},
        )
    else:
        ts_col = next(
            (col for col in ("timestamp", "close_time", "date") if col in trades_df.columns),
            None,
        )
        df = trades_df.sort_values(ts_col) if ts_col else trades_df
        df = df.copy()
        df["equity"] = df["pnl"].cumsum()
        fig.add_trace(
            go.Scatter(
                x=list(range(len(df))),
                y=df["equity"].tolist(),
                mode="lines",
                line={"color": "#00c853", "width": 2},
                fill="tozeroy",
                fillcolor="rgba(0,200,83,0.1)",
                name="Equity",
            )
        )
    fig.update_layout(
        height=300,
        margin={"l": 10, "r": 10, "t": 10, "b": 10},
        paper_bgcolor="#0e1117",
        plot_bgcolor="#0e1117",
        xaxis={"showgrid": False, "color": "#607d8b"},
        yaxis={"showgrid": True, "gridcolor": "#1e2530", "color": "#607d8b"},
        font={"color": "#e0e0e0"},
    )
    return fig


def build_pnl_by_module(trades_df: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    if trades_df.empty or "pnl" not in trades_df.columns:
        fig.add_annotation(
            text="Sem trades ainda",
            xref="paper",
            yref="paper",
            x=0.5,
            y=0.5,
            showarrow=False,
            font={"size": 16, "color": "#607d8b"},
        )
    else:
        module_col = next(
            (col for col in ("module", "strategy", "source") if col in trades_df.columns),
            None,
        )
        df = trades_df.copy()
        if not module_col:
            df["module"] = "kotegawa"
            module_col = "module"
        grouped = (
            df.groupby(module_col)["pnl"].sum().reset_index().sort_values("pnl", ascending=False)
        )
        grouped["label"] = grouped[module_col].map(lambda value: MODULE_LABELS.get(value, value))
        colours = ["#00c853" if value >= 0 else "#d50000" for value in grouped["pnl"]]
        fig.add_trace(
            go.Bar(
                x=grouped["label"].tolist(),
                y=grouped["pnl"].tolist(),
                marker_color=colours,
                name="P&L",
            )
        )
    fig.update_layout(
        height=300,
        margin={"l": 10, "r": 10, "t": 10, "b": 10},
        paper_bgcolor="#0e1117",
        plot_bgcolor="#0e1117",
        xaxis={"color": "#607d8b"},
        yaxis={"showgrid": True, "gridcolor": "#1e2530", "color": "#607d8b"},
        font={"color": "#e0e0e0"},
    )
    return fig


# ── Layout ────────────────────────────────────────────────────

def main() -> None:
    st.set_page_config(
        page_title="Bot Trading Monitor",
        page_icon="🤖",
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    st.markdown(
        """
    <style>
    .stApp { background-color: #0e1117; color: #e0e0e0; }
    div[data-testid="stMetricValue"] { font-size: 1.8rem; }
    </style>
    """,
        unsafe_allow_html=True,
    )

    metrics = load_metrics()

    col_title, col_time, col_mode = st.columns(3)
    with col_title:
        st.title("🤖 Bot Trading — Monitor")
    with col_time:
        st.caption(f"🔄 Auto-refresh: {REFRESH_INTERVAL}s")
        st.caption(f"⏰ {datetime.now().strftime('%H:%M:%S')}")
    with col_mode:
        paper = bool(metrics.get("paper_trading", True))
        st.markdown(
            (
                f"<div style='background:{'#ff6d00' if paper else '#d50000'};"
                "padding:8px 12px;border-radius:8px;text-align:center;"
                f"font-weight:bold;'>{'📄 PAPER' if paper else '💰 LIVE'}</div>"
            ),
            unsafe_allow_html=True,
        )
    st.divider()

    tab1, tab2, tab3, tab4 = st.tabs(
        ["📊 Visão Geral", "🔲 Grids Activos", "📈 Histórico de Trades", "📋 Log ao Vivo"]
    )

    with tab1:
        trades_df = load_trades()
        grids = load_grids()
        capital = safe_float(metrics.get("capital") or metrics.get("initial_capital"))
        total_pnl = (
            trades_df["pnl"].sum()
            if not trades_df.empty and "pnl" in trades_df.columns
            else 0.0
        )
        n_trades = len(trades_df)
        n_grids = len(grids) if isinstance(grids, dict) else 0
        wins = (
            int((trades_df["pnl"] > 0).sum())
            if not trades_df.empty and "pnl" in trades_df.columns
            else 0
        )
        win_rate = (wins / n_trades * 100) if n_trades > 0 else 0.0

        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("💶 Capital", f"€{capital:,.2f}" if capital else "—")
        c2.metric(
            "📈 P&L Total",
            f"€{total_pnl:+,.2f}",
            delta=f"{(total_pnl / capital * 100):+.2f}%" if capital else None,
        )
        c3.metric("🔢 Trades", str(n_trades))
        c4.metric("🏆 Win Rate", f"{win_rate:.1f}%")
        c5.metric("🔲 Grids Abertos", str(n_grids))

        st.subheader("Equity Curve")
        st.plotly_chart(build_equity_curve(trades_df), use_container_width=True)

        st.subheader("Kill Switches")
        kc1, kc2, kc3 = st.columns(3)
        with kc1:
            pct_bar(abs(safe_float(metrics.get("daily_loss"))), KILL_SWITCH_LIMITS["daily"], "🔴 Diário")
        with kc2:
            pct_bar(abs(safe_float(metrics.get("weekly_loss"))), KILL_SWITCH_LIMITS["weekly"], "🟠 Semanal")
        with kc3:
            pct_bar(abs(safe_float(metrics.get("monthly_loss"))), KILL_SWITCH_LIMITS["monthly"], "🟡 Mensal")

        st.subheader("P&L por Módulo")
        st.plotly_chart(build_pnl_by_module(trades_df), use_container_width=True)

    with tab2:
        grids = load_grids()
        if not grids:
            st.info("ℹ️ Nenhum grid activo no momento.")
        else:
            rows: list[dict[str, str]] = []
            for grid_id, grid in grids.items():
                if not isinstance(grid, dict):
                    continue
                regime = str(grid.get("regime", "UNKNOWN")).upper()
                levels = grid.get("levels", [])
                current_level = len([item for item in levels if item.get("status") == "bought"]) if isinstance(levels, list) else 0
                rows.append(
                    {
                        "Grid ID": str(grid_id),
                        "Símbolo": str(grid.get("symbol", "—")),
                        "Módulo": MODULE_LABELS.get(str(grid.get("module", "kotegawa")), str(grid.get("module", "—"))),
                        "Regime": regime,
                        "Nível": f"{current_level} / {len(levels) if isinstance(levels, list) else '?'}",
                        "Entry": f"{safe_float(grid.get('center_price') or grid.get('entry_price')):.4f}",
                        "Stop": f"{safe_float(grid.get('stop_loss')):.4f}",
                        "TP": f"{safe_float(grid.get('take_profit')):.4f}",
                        "P&L": f"€{safe_float(grid.get('total_pnl')):+.2f}",
                        "Aberto em": str(grid.get("created_at") or grid.get("opened_at") or "—"),
                    }
                )
            df_grids = pd.DataFrame(rows)
            symbols = ["Todos"] + sorted(df_grids["Símbolo"].dropna().unique().tolist())
            selected = st.selectbox("Filtrar por símbolo:", symbols)
            if selected != "Todos":
                df_grids = df_grids[df_grids["Símbolo"] == selected]
            st.dataframe(df_grids, use_container_width=True, hide_index=True)
            sc1, sc2, sc3 = st.columns(3)
            sc1.metric("Grids abertos", len(df_grids))
            sc2.metric(
                "P&L não realizado",
                f"€{sum(safe_float(value.replace('€', '')) for value in df_grids['P&L']):+.2f}",
            )
            sc3.metric("Regimes activos", ", ".join(df_grids["Regime"].unique()) or "—")

    with tab3:
        trades_df = load_trades()
        if trades_df.empty:
            st.info("ℹ️ Nenhum trade registado ainda.")
        else:
            fc1, fc2, fc3 = st.columns(3)
            module_col = next(
                (col for col in ("module", "strategy", "source") if col in trades_df.columns),
                None,
            )
            with fc1:
                mods = (
                    ["Todos"] + sorted(trades_df[module_col].dropna().unique().tolist())
                    if module_col
                    else ["Todos"]
                )
                selected_module = st.selectbox("Módulo:", mods)
            with fc2:
                symbols = (
                    ["Todos"] + sorted(trades_df["symbol"].dropna().unique().tolist())
                    if "symbol" in trades_df.columns
                    else ["Todos"]
                )
                selected_symbol = st.selectbox("Símbolo:", symbols)
            with fc3:
                period = st.selectbox("Período:", ["Tudo", "Hoje", "Últimos 7 dias", "Últimos 30 dias"])

            df_filtered = trades_df.copy()
            if selected_module != "Todos" and module_col:
                df_filtered = df_filtered[df_filtered[module_col] == selected_module]
            if selected_symbol != "Todos" and "symbol" in df_filtered.columns:
                df_filtered = df_filtered[df_filtered["symbol"] == selected_symbol]

            ts_col = next(
                (
                    col
                    for col in ("timestamp", "close_time", "date")
                    if col in df_filtered.columns
                    and pd.api.types.is_datetime64_any_dtype(df_filtered[col])
                ),
                None,
            )
            if ts_col and period != "Tudo":
                cutoff = {
                    "Hoje": datetime.now() - timedelta(days=1),
                    "Últimos 7 dias": datetime.now() - timedelta(days=7),
                    "Últimos 30 dias": datetime.now() - timedelta(days=30),
                }.get(period, datetime.min)
                df_filtered = df_filtered[df_filtered[ts_col] >= cutoff]

            n_filtered = len(df_filtered)
            pnl_filtered = df_filtered["pnl"].sum() if "pnl" in df_filtered.columns else 0.0
            wins_filtered = int((df_filtered["pnl"] > 0).sum()) if "pnl" in df_filtered.columns else 0
            win_rate_filtered = (wins_filtered / n_filtered * 100) if n_filtered > 0 else 0.0

            tm1, tm2, tm3, tm4 = st.columns(4)
            tm1.metric("Trades", str(n_filtered))
            tm2.metric("P&L", f"€{pnl_filtered:+,.2f}")
            tm3.metric("Win Rate", f"{win_rate_filtered:.1f}%")
            tm4.metric("Média/Trade", f"€{(pnl_filtered / n_filtered):+.2f}" if n_filtered else "—")

            display_cols = [
                col
                for col in (ts_col, "symbol", module_col, "action", "entry_price", "exit_price", "pnl", "regime")
                if col and col in df_filtered.columns
            ]
            display_df = (
                df_filtered[display_cols].sort_values(ts_col, ascending=False)
                if ts_col
                else df_filtered[display_cols]
            )
            st.dataframe(display_df, use_container_width=True, hide_index=True)

    with tab4:
        lc1, lc2 = st.columns(2)
        with lc1:
            n_lines = st.slider("Linhas:", 20, 200, 50, step=10)
        with lc2:
            level = st.selectbox("Nível:", ["Tudo", "ERROR", "WARNING", "INFO", "DEBUG"])
        lines = load_log_tail(n_lines)
        if level != "Tudo":
            lines = [line for line in lines if level in line]
        if not lines:
            st.info("ℹ️ Nenhuma linha disponível.")
        else:
            coloured: list[str] = []
            for line in reversed(lines):
                if "ERROR" in line or "CRITICAL" in line:
                    coloured.append(f"🔴 `{line}`")
                elif "WARNING" in line:
                    coloured.append(f"🟠 `{line}`")
                elif "INFO" in line:
                    coloured.append(f"⚪ `{line}`")
                else:
                    coloured.append(f"🔵 `{line}`")
            st.markdown("\n\n".join(coloured))

    st.markdown(
        (
            "<script>setTimeout(function(){window.location.reload();},"
            f"{REFRESH_INTERVAL * 1000});</script>"
        ),
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()

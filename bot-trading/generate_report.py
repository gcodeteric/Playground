"""
generate_report.py
------------------
Gerado pelo ops-analyst no final de cada sessão.
Lê os ficheiros de estado do bot e produz:
  - data/reports/daily_report_YYYY-MM-DD.txt
  - data/reports/claude_prompt_YYYY-MM-DD.txt
  - data/reports/weekly_report_YYYY-MM-DD.txt (apenas às sextas)

Uso:
  python generate_report.py              → relatório diário
  python generate_report.py --weekly     → relatório semanal (forçado)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path


# ---------------------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
REPORTS_DIR = DATA_DIR / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

TODAY = datetime.now(timezone.utc).strftime("%Y-%m-%d")
NOW = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
IS_FRIDAY = datetime.now(timezone.utc).weekday() == 4


# ---------------------------------------------------------------------------
# Leitores de ficheiros
# ---------------------------------------------------------------------------

def read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def read_log_tail(path: Path, lines: int = 30) -> str:
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
        tail = content.strip().splitlines()[-lines:]
        return "\n".join(tail)
    except Exception:
        return "(log indisponível)"


def read_reports_last_n_days(n: int = 5) -> list[str]:
    reports = []
    for i in range(1, n + 1):
        date = (datetime.now(timezone.utc) - timedelta(days=i)).strftime("%Y-%m-%d")
        path = REPORTS_DIR / f"daily_report_{date}.txt"
        if path.exists():
            reports.append(f"\n{'='*60}\n{date}\n{'='*60}\n{path.read_text(encoding='utf-8')}")
    return reports


# ---------------------------------------------------------------------------
# Gerador de relatório diário
# ---------------------------------------------------------------------------

def generate_daily_report() -> str:
    heartbeat = read_json(DATA_DIR / "heartbeat.json")
    metrics = read_json(DATA_DIR / "metrics.json")
    grids = read_json(DATA_DIR / "grids_state.json")
    preflight = read_json(DATA_DIR / "preflight_state.json")
    log_tail = read_log_tail(DATA_DIR / "bot.log")

    # Métricas
    metrics_block = metrics.get("metrics", metrics)
    capital = metrics_block.get("capital", "N/D")
    initial_capital = metrics_block.get("initial_capital", "N/D")
    peak_equity = metrics_block.get("peak_equity", "N/D")
    total_pnl = metrics_block.get("total_pnl", 0.0)
    num_trades = metrics_block.get("num_trades", 0)
    win_rate = metrics_block.get("win_rate", 0.0)
    max_drawdown = metrics_block.get("max_drawdown", 0.0)

    # Baselines
    baselines = metrics_block.get("equity_baselines", {})
    daily_baseline = baselines.get("daily", {}).get("equity", "N/D")
    weekly_baseline = baselines.get("weekly", {}).get("equity", "N/D")

    # Heartbeat
    ib_connected = heartbeat.get("ib_connected", False)
    manual_pause = heartbeat.get("manual_pause", False)
    entry_halt = heartbeat.get("entry_halt_reason", None)
    emergency_halt = heartbeat.get("emergency_halt", False)
    last_error = heartbeat.get("last_error", None)
    last_cycle = heartbeat.get("last_cycle_completed_at", "N/D")

    # Grids
    grids_list = grids.get("grids", [])
    active_grids = [g for g in grids_list if g.get("status") == "active"]
    closed_grids = [g for g in grids_list if g.get("status") == "closed"]

    report = f"""
================================================================================
RELATÓRIO DIÁRIO — BOT DE TRADING
Data: {NOW}
Modo: PAPER TRADING
================================================================================

── ESTADO OPERACIONAL ──────────────────────────────────────────────────────────
IB Conectado:          {"✅ SIM" if ib_connected else "❌ NÃO"}
Pausa manual:          {"⚠️ SIM" if manual_pause else "✅ NÃO"}
Entry halt:            {f"⚠️ {entry_halt}" if entry_halt else "✅ NENHUM"}
Emergency halt:        {"🔴 SIM" if emergency_halt else "✅ NÃO"}
Último erro:           {last_error or "✅ nenhum"}
Último ciclo:          {last_cycle}

── CAPITAL ─────────────────────────────────────────────────────────────────────
Capital actual:        {capital}
Capital inicial:       {initial_capital}
Peak equity:           {peak_equity}
Baseline diário:       {daily_baseline}
Baseline semanal:      {weekly_baseline}

── PERFORMANCE ─────────────────────────────────────────────────────────────────
P&L total:             {total_pnl}
Número de trades:      {num_trades}
Win rate:              {win_rate:.1%}
Max drawdown:          {max_drawdown:.2%}

── GRIDS ───────────────────────────────────────────────────────────────────────
Grids activas:         {len(active_grids)}
Grids fechadas hoje:   {len(closed_grids)}

{"".join(f"  → {g.get('symbol')} | regime={g.get('regime')} | pnl={g.get('total_pnl', 0):.4f}" for g in active_grids) or "  (nenhuma grid activa)"}

── PREFLIGHT ───────────────────────────────────────────────────────────────────
Reconciliação:         {"✅ OK" if preflight.get("startup_reconciled") else "⚠️ INCONCLUSIVA"}
Telegram:              {preflight.get("telegram_status", "N/D")}
Watchlist size:        {preflight.get("watchlist_size", "N/D")}

── ÚLTIMAS LINHAS DO LOG ───────────────────────────────────────────────────────
{log_tail}

================================================================================
"""
    return report.strip()


# ---------------------------------------------------------------------------
# Gerador de prompt para o Claude
# ---------------------------------------------------------------------------

def generate_claude_prompt(report: str, weekly: bool = False) -> str:
    tipo = "SEMANAL (5 dias)" if weekly else "DIÁRIO"

    prompt = f"""Analisa o estado operacional do meu trading bot em paper trading com base no resumo abaixo.

Tipo de relatório: {tipo}
Data: {NOW}

Quero uma resposta em 5 secções:

1. ESTADO GERAL
- O bot arrancou e operou bem hoje?
- Houve halts, erros ou warnings críticos?
- O estado geral parece saudável para continuar amanhã?

2. RISCO
- Houve sinais de risco operacional?
- Kill switches, entry_halt, emergency_halt, reconnects, falhas de dados?
- Alguma situação que deva bloquear a próxima sessão?

3. EXECUÇÃO E COMPORTAMENTO
- Houve grids abertas ou fechadas?
- Os eventos parecem normais para paper trading supervisionado?
- Algum comportamento inesperado?

4. PROBLEMAS CONCRETOS
- Lista curta do que correu mal (se houver)
- Para cada ponto: severidade (baixa/média/alta) e causa provável

5. PRÓXIMOS PASSOS
- O que devo fazer amanhã?
- Manter igual, ajustar watchlist, rever configuração, ou abrir fix?

Regras:
- Não inventes contexto que não esteja no resumo
- Distingue claramente facto de inferência
- Se algo estiver ambíguo, diz que está ambíguo
- Responde em português europeu
- Foco em operação prática, não em teoria

================================================================================
RESUMO OPERACIONAL:
================================================================================

{report}
"""
    return prompt.strip()


# ---------------------------------------------------------------------------
# Gerador de relatório semanal
# ---------------------------------------------------------------------------

def generate_weekly_report() -> str:
    past_reports = read_reports_last_n_days(5)

    if not past_reports:
        return "(sem relatórios diários dos últimos 5 dias disponíveis)"

    weekly = f"""
================================================================================
RELATÓRIO SEMANAL — BOT DE TRADING
Semana terminada em: {NOW}
Modo: PAPER TRADING
================================================================================

Este relatório agrega os últimos 5 dias de operação.

{"".join(past_reports)}

================================================================================
"""
    return weekly.strip()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--weekly", action="store_true", help="Forçar relatório semanal")
    args = parser.parse_args()

    force_weekly = args.weekly or IS_FRIDAY

    # Relatório diário
    daily = generate_daily_report()
    daily_path = REPORTS_DIR / f"daily_report_{TODAY}.txt"
    daily_path.write_text(daily, encoding="utf-8")
    print(f"✅ Relatório diário guardado: {daily_path}")

    # Prompt Claude diário
    claude_daily = generate_claude_prompt(daily, weekly=False)
    claude_daily_path = REPORTS_DIR / f"claude_prompt_{TODAY}.txt"
    claude_daily_path.write_text(claude_daily, encoding="utf-8")
    print(f"✅ Prompt Claude guardado: {claude_daily_path}")

    # Relatório semanal (sextas ou forçado)
    if force_weekly:
        weekly = generate_weekly_report()
        weekly_path = REPORTS_DIR / f"weekly_report_{TODAY}.txt"
        weekly_path.write_text(weekly, encoding="utf-8")

        claude_weekly = generate_claude_prompt(weekly, weekly=True)
        claude_weekly_path = REPORTS_DIR / f"claude_prompt_weekly_{TODAY}.txt"
        claude_weekly_path.write_text(claude_weekly, encoding="utf-8")

        print(f"✅ Relatório semanal guardado: {weekly_path}")
        print(f"✅ Prompt Claude semanal guardado: {claude_weekly_path}")

    print(f"\n📋 Para ver o prompt de hoje:\n   {claude_daily_path}")


if __name__ == "__main__":
    main()

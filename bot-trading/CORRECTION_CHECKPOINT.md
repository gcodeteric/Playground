# CHECKPOINT — CORRECÇÃO DO BOT
Última actualização: 2026-03-20 03:00 UTC
Commit actual: cc7c4990c2a22ae3e8b04d3024f84c957aeff7bb
Python escolhido: C:\Users\berna\Desktop\Playground\bot-trading\venv\Scripts\python.exe
Testes baseline: C:\Users\berna\Desktop\Playground\bot-trading\venv\Scripts\python.exe -m pytest tests/ -q --tb=short -> 420 passed in 16.51s

## ESTADO DAS RONDAS
[~] RONDA 0 — Baseline e congelamento (baseline capturado, validar git + OpenClaw ao retomar)
[ ] RONDA 1 — P0: Shutdown, Reconciliação, Equity
[ ] RONDA 2 — P1: Scripts Windows, Reports, Logger
[ ] RONDA 3 — P2: Dashboard, Higiene, Segurança
[ ] RONDA 4 — Reauditoria final

## CORRECÇÕES APLICADAS
- Checkpoint inicial criado nesta ronda.
- Baseline conhecido preservado do último estado validado:
  - Python: C:\Users\berna\Desktop\Playground\bot-trading\venv\Scripts\python.exe
  - Testes: 420 passed in 16.51s
  - Commit registado: cc7c4990c2a22ae3e8b04d3024f84c957aeff7bb
- Tentativa de retoma nesta thread bloqueada por runner de shell:
  - `Get-Content ...CORRECTION_CHECKPOINT.md` -> exit code 1 sem stdout/stderr
  - `Get-Content ...AUDIT_REPORT.md` -> exit code 1 sem stdout/stderr
  - `git status --short` -> exit code 1 sem stdout/stderr
  - `git log --oneline -5` -> exit code 1 sem stdout/stderr

## PRÓXIMO PASSO SE INTERROMPIDO
1. Confirmar `git status` e `git log --oneline -5`
2. Confirmar testes: 420 passed (baseline já validado)
3. Confirmar estado OpenClaw: `agents list`, `cron list`, `gateway status`
4. Se tudo OK, iniciar RONDA 1 — C03 primeiro
## 2026-03-20 - H10

- `main.py`: adicionado `self._reconciliation_conclusive` no arranque.
- `_run_reconciliation()`: passa a iniciar como inconclusiva e marca conclusiva apenas no fecho normal da rotina.
- `_reconcile_startup()`: quando a reconciliacao de arranque nao fecha de forma conclusiva, ativa `self._entry_halt_reason = "reconciliation_failed"`.
- `preflight_state.json`: passa a incluir `reconciliation_conclusive` e `reconciliation_halt_active`.
- Validacao pendente: o executor de shell desta sessao devolve `exit 1` ate para comandos triviais, por isso a confirmacao local do gate de `_entry_halt_reason`, o `pytest` e o commit ficaram bloqueados.
## 2026-03-20 - H11

- `main.py`: sanitizado `peak_equity` herdado do `metrics.json` em `_restore_runtime_capital()`.
- `metrics_peak` so e reutilizado quando for coerente com o capital real do broker (`<= 10x broker_capital`).
- Quando o valor herdado e inconsistente, o bot faz warning e usa o capital real como base do peak.
- Validacao e commit pendentes de confirmacao local: o executor de shell desta sessao continua a devolver `exit 1` sem output, incluindo em `pytest`.
## 2026-03-20 - H12

- `start_all.bat`: removido o bloqueio interativo no falhanço do auto-login e removido o `pause` final.
- `tws_autologin.py`: mensagem de falha de deteccao da janela de login clarificada e `load_credentials()` agora falha de forma explicita quando o ficheiro nao existe ou esta invalido.
- Salvaguarda mantida: coordenadas hardcoded nao foram alteradas nesta correcao.
- Validacao e commit continuam pendentes de confirmacao local porque o executor de shell desta sessao devolve `exit 1` sem output, incluindo em `pytest`.
## 2026-03-20 - H13

- `generate_report.py`: adicionada extraccao de eventos intradiarios do `bot.log` do dia atual.
- O relatorio diario passa a incluir a secao `EVENTOS DO DIA` com erros/criticos, reconnects, fallbacks yfinance, reconciliacoes inconclusivas, entry halts e outros warnings, alem da janela de sessao.
- O prompt gerado para Claude passou a perguntar explicitamente por reconnects, fallbacks yfinance e reconciliacoes inconclusivas.
- Validacao, comparacao before/after e commit continuam bloqueados nesta sessao porque o executor de shell devolve `exit 1` sem output, incluindo em `python generate_report.py` e `pytest`.
## 2026-03-20 - H14

- `src/logger.py`: `_read_trades_file()` passa a criar backup `.json.corrupted` quando encontra `trades_log.json` corrompido.
- Se o backup falhar, o erro passa a ser registado explicitamente antes de continuar com `{"trades": []}`.
- `FileNotFoundError` continua a devolver `{"trades": []}` sem warning espurio.
- Validacao e commit continuam pendentes nesta sessao porque o executor de shell devolve `exit 1` sem output, incluindo em `pytest`.
## 2026-03-20 - M12

- `README.md`: secao `Parar o Bot` atualizada para descrever o shutdown gracioso real via `data/shutdown.request`.
- Documentado o comportamento de `stop_and_report.bat`, incluindo timeout de 30s e fallback com `taskkill /f`.
- Adicionada nota operacional para nao fechar o TWS/Gateway antes de parar o bot.
- `pytest` nao foi executado por instrucao explicita desta correcao.
## 2026-03-20 - H02

- `src/ib_requests.py`: extraida a constante `_PACING_VIOLATION_RETRY_SECONDS = 600.0`.
- O retry especifico para pacing violation deixou de usar `delay = 60.0` hardcoded e passou a usar a constante de modulo.
- `pytest` nao foi executado por instrucao explicita desta correcao.

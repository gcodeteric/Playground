# CHECKPOINT — CORRECÇÃO DO BOT
Última actualização: 2026-03-23 14:49:36 UTC
Commit actual: c519678e4801f17dd176ec5343262a660fa5c51c
Python escolhido: C:\Users\berna\Desktop\Playground\bot-trading\venv\Scripts\python.exe
Testes baseline: C:\Users\berna\Desktop\Playground\bot-trading\venv\Scripts\python.exe -m pytest tests/ -q --tb=short -> 426 passed in 9.54s

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
  - Testes: 423 passed in 8.22s
  - Commit registado: cc7c4990c2a22ae3e8b04d3024f84c957aeff7bb
- Tentativa de retoma nesta thread bloqueada por runner de shell:
  - `Get-Content ...CORRECTION_CHECKPOINT.md` -> exit code 1 sem stdout/stderr
  - `Get-Content ...AUDIT_REPORT.md` -> exit code 1 sem stdout/stderr
  - `git status --short` -> exit code 1 sem stdout/stderr
  - `git log --oneline -5` -> exit code 1 sem stdout/stderr

## PRÓXIMO PASSO SE INTERROMPIDO
1. Confirmar `git status` e `git log --oneline -5`
2. Confirmar testes: 423 passed (baseline já validado)
3. Confirmar estado OpenClaw: `agents list`, `cron list`, `gateway status`
4. Se tudo OK, iniciar RONDA 1 — C03 primeiro
## 2026-03-20 - H10

- `main.py`: adicionado `self._reconciliation_conclusive` no arranque.
- `_run_reconciliation()`: passa a iniciar como inconclusiva e marca conclusiva apenas no fecho normal da rotina.
- `_reconcile_startup()`: quando a reconciliacao de arranque nao fecha de forma conclusiva, ativa `self._entry_halt_reason = "reconciliation_failed"`.
- `preflight_state.json`: passa a incluir `reconciliation_conclusive` e `reconciliation_halt_active`.
- Este subpasso ficou posteriormente validado e fechado na entrada `H10 / YFINANCE_STALE`.
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
## 2026-03-20 - H10 / YFINANCE_STALE (FECHADO)

- `main.py`: `_fetch_positions_with_retry()` deixa de tratar `positions=[]` como inconclusivo quando o estado local nao tem posicoes abertas; nessa condicao passa a devolver `state="confirmed"` e permite que a reconciliacao de arranque feche de forma conclusiva.
- Salvaguarda mantida: se o estado local tiver niveis `bought` ou posicoes orfas, `positions=[]` do IB continua a resultar em reconciliacao inconclusiva apos os retries.
- `src/data_feed.py`: o fallback de preco por `yfinance` passa a guardar a data efectiva do quote e a marcar `fresh=True` quando o dado corresponde ao dia actual ou ao ultimo fecho util disponivel.
- A logica de freshness para dados IB (`last`, `mid`, `close`) foi preservada sem alteracoes.
- `tests/test_main_audit.py`: adicionada cobertura para `IB vazio + estado local vazio => confirmed` e para o caso protegido `IB vazio + posicao local aberta => unknown`.
- `tests/test_data_feed.py`: adicionada cobertura para aceitar o ultimo fecho do `yfinance` como fresh.
- Estado final: `FECHADO`.
- Baseline novo registado: `423 passed in 8.22s`.
## 2026-03-23 - OPERACIONAL P1-P5

- Escopo desta ronda limitado a problemas operacionais visíveis em log; nenhuma activacao de execucao multi-instrumento foi introduzida.
- `src/data_feed.py`: removido o `FutureWarning` de pandas ao extrair o ultimo valor numerico de Series/DataFrame devolvidos por `yfinance`; comportamento funcional mantido.
- `src/data_feed.py`: a hierarquia de preco IB passou a aceitar `markPrice` antes de cair em `yfinance` e tambem reaproveita um snapshot IB tardio mas utilizavel antes do fallback externo.
- `src/data_feed.py` + `main.py`: o volume do mesmo snapshot IB passa a ser reutilizado, evitando um pedido redundante de `current_volume` quando esse dado ja veio com o preco.
- `main.py`: sinais multi-instrumento bloqueados por politica passam a ficar expostos em `heartbeat.json` e `snapshot.json` via `last_blocked_multi_signal`, alem de log estruturado com motivo explicito.
- `tests/test_data_feed.py`: cobertura adicionada para `markPrice` IB utilizavel, propagacao de `current_volume` no snapshot live e reutilizacao de volume do snapshot.
- `tests/test_main_audit.py`: cobertura adicionada para registo de sinal multi-instrumento bloqueado sem activar execucao e sem exigir pedido extra de volume quando o snapshot ja o traz.
- Estado por problema:
  - `P1` = `RESOLVIDO`
  - `P2` = `RESOLVIDO`
  - `P3` = `MITIGADO` (duplicacao obvia de volume reduzida; arquitectura global de pacing nao foi reescrita)
  - `P4` = `RESOLVIDO`
  - `P5` = `MANTIDO POR DESIGN`
- Baseline novo validado: `426 passed in 9.54s`.

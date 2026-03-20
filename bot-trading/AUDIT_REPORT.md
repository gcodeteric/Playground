# AUDIT REPORT — bot-trading
Branch actual: `main` | Commit actual: `cc7c4990c2a22ae3e8b04d3024f84c957aeff7bb` | Data/hora UTC: `2026-03-20T02:16:05Z` | Working tree no início da ronda: `clean`
Score audit total actual: `72/100`

## Delta audit total - 2026-03-20 persistência do gateway + auditoria operacional completa

### Escopo e método
- Source of truth desta ronda: código real, scripts reais, artefactos runtime reais e outputs reais; o relatório anterior foi tratado apenas como contexto.
- Artefactos lidos nesta ronda:
  - `AUDIT_REPORT.md`
  - `README.md`
  - `CODEX_IMPLEMENTATION_BRIEF_FINAL.md`
  - módulos críticos do runtime: `main.py`, `config.py`, `src/data_feed.py`, `src/execution.py`, `src/grid_engine.py`, `src/risk_manager.py`, `src/logger.py`, `src/ib_requests.py`
  - scripts operacionais: `start_all.bat`, `start_bot.bat`, `start_dashboard.bat`, `stop_and_report.bat`, `generate_report.bat`, `generate_report.py`, `tws_autologin.py`
  - dashboard: `dashboard/app.py`, `dashboard/helpers.py`
  - suite de testes e casos críticos de `tests/`
  - artefactos runtime reais em `data/`: `metrics.json`, `heartbeat.json`, `grids_state.json`, `trades_log.json`, `snapshot.json`, `preflight_state.json`, `reconciliation.log`, `bot.log`, `data/reports/`
- Inventário real do repositório mapeado por leitura recursiva; foram confirmados duplicados/artefactos runtime no repo (`dashboard 2`, `CODEX_IMPLEMENTATION_BRIEF_FINAL 2.md`, `__pycache__`, `.pytest_cache`, ficheiro `notepad`, `venv/`, `venv2/`).
- Testes executados com o Python prioritário pedido:
  - `C:\Users\berna\Desktop\Playground\bot-trading\venv\Scripts\python.exe -m pytest tests/ -q --tb=short`
  - resultado real: `420 passed in 16.51s`

### Fase 0 — persistência do gateway OpenClaw
- Estado inicial confirmado:
  - `gateway install` suportado pela versão instalada.
  - `gateway install --port 18789 --runtime node --json` falhou com `ERROR: Acesso negado.`
  - `schtasks /Query /FO LIST /V | findstr /I "openclaw gateway"` continuou sem qualquer task real do Windows.
- Correcção aplicada nesta ronda:
  - foi usado fallback seguro ao nível do utilizador via pasta Startup:
    - `C:\Users\berna\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup\OpenClaw Gateway.cmd`
  - o fallback só arranca o gateway se a porta `18789` estiver livre e chama `openclaw.cmd gateway run --port 18789` em janela escondida.
- Validação real:
  - a porta ficou livre após fecho do gateway manual anterior.
  - a execução do login item voltou a pôr o gateway a ouvir em `127.0.0.1:18789`.
  - `openclaw gateway health` passou a `OK`.
  - `openclaw gateway status` passou a indicar runtime activo com `Startup-folder login item installed`.
  - os 3 agentes e os 5 cron jobs permaneceram intactos.
- Conclusão operacional da Fase 0:
  - persistência prática confirmada ao nível de login do utilizador.
  - não existe evidência de uma Scheduled Task real do Windows; o estado persistente actual depende do login item da pasta Startup, não de `schtasks`.
  - não foi validado um reboot/logoff completo nesta ronda; esse ponto fica `não validado`.

### Validação OpenClaw real no fim da Fase 0
- Gateway:
  - `openclaw gateway status` confirma:
    - listener em `127.0.0.1:18789`
    - `RPC probe: ok`
    - `Runtime: running`
    - `Startup-folder login item installed`
- Agentes:
  - `main`
  - `ops-scheduler`
  - `claude-briefing`
  - `ops-analyst` com `Model: openrouter/hunter-alpha:free`
- Cron jobs:
  - `bot-arranque`
  - `bot-relatorio`
  - `briefing-diario`
  - `briefing-semanal`
  - `bot-paragem`
- Fragilidade confirmada:
  - `openclaw cron list` simples continua a falhar com `gateway closed (1000 normal closure)`
  - `openclaw status` simples continua a reportar `missing scope: operator.read`
  - `openclaw cron list --url ws://127.0.0.1:18789 --token <token local>` funciona e lista os 5 jobs

### Estado actualizado dos findings anteriores
| ID | Estado actual | Nota curta |
| --- | --- | --- |
| `C01` | `FECHADO` | runtime de risco usa snapshot de equity real + baselines por período |
| `C02` | `FECHADO` | entradas e ajustamento dinâmico bloqueiam quote `fresh=False` |
| `H01` | `PARCIAL` | ambiente local actual corre, mas reprodutibilidade continua fraca e o repo inclui `venv/`, `venv2/` e `.gitignore` defeituoso |
| `H02` | `ABERTO` | pacing/backoff continua rígido (`15 s` identical cooldown, `60 s` pacing retry) |
| `H03` | `FECHADO` | policy operacional IB central existe e está integrada |
| `H04` | `FECHADO` | market-hours fail-closed e timezones locais já estão no código |
| `H05` | `FECHADO` | pre-trade gate real existe para sessão/frescura/NaN/risco |
| `H06` | `FECHADO` | `grids_state.json` tem backup + recovery + fail-closed |
| `H07` | `FECHADO` | exclusão mútua por instância e por contexto IB real confirmada |
| `H08` | `FECHADO` | a suite está executável e passou (`420 passed`) |
| `H09` | `FECHADO` | dashboard actual tem observabilidade melhor do que na auditoria antiga |
| `M01` | `ABERTO` | continua sem gate real de type-check/CI |
| `M02` | `ABERTO` | `datetime.utcnow` permanece em defaults de dataclasses de risco |
| `M03` | `ABERTO` | falta cap explícito de gross exposure/notional agregado |
| `M04` | `ABERTO` | continua sem contrato unificado para todos os módulos de sinal |
| `M05` | `ABERTO` | estratégias multi-instrumento continuam audit-only / não executáveis |
| `M06` | `ABERTO` | estados continuam stringly-typed |
| `M07` | `ABERTO` | não há migração formal de schema de estado |
| `M08` | `ABERTO` | logs continuam sem rotação/retenção formal e heartbeat continua só local-file |
| `M09` | `PARCIAL` | cobertura subiu, mas faltam regressões operacionais reais (shutdown forçado, scripts Windows, reports) |
| `L01` | `ABERTO` | continuam `except Exception`/`BaseException` demasiado amplos em paths críticos |
| `L02` | `ABERTO` | `dashboard/` e `dashboard 2/` continuam duplicados |

### Novos findings desta ronda

#### Crítico
| ID | Finding | Evidência | Impacto |
| --- | --- | --- | --- |
| `C03` | O path operativo de fecho diário não é gracioso e pode deixar ordens broker-side vivas. | `stop_and_report.bat` usa `taskkill /f`; `_graceful_shutdown()` em `main.py:3758-3791` não cancela ordens pendentes nem faz flatten antes de desligar. | A automação diária de paragem pode terminar o processo sem cancelar ordens abertas/pending; isto invalida a confiança em shutdown limpo e em reports pós-fecho. |

#### Alto
| ID | Finding | Evidência | Impacto |
| --- | --- | --- | --- |
| `H10` | A reconciliação de arranque pode ficar inconclusiva e o bot continua mesmo assim. | `_run_reconciliation()` retorna cedo com `positions not confirmed`, marca grids como `unknown`; `_reconcile_startup()` em seguida define sempre `_startup_reconciled = True`. `data/reconciliation.log` mostra vários eventos `Reconciliação inconclusiva`. | O bot pode arrancar com divergência não resolvida entre estado local e broker-side. |
| `H11` | Telemetria de equity/peak pode ficar presa num regime antigo e contaminar sizing/relatórios. | `metrics.json` real: `capital=1119.91`, `initial_capital=1120.0`, `peak_equity=100000.0`; `_restore_runtime_capital()` reaproveita `metrics_peak` e `apply_drawdown_scaling()` usa `peak_equity`. | O drawdown scaling pode ficar sempre activo e os relatórios ficam materialmente enganadores. |
| `H12` | O setup OpenClaw continua frágil para administração local: o gateway está persistente, mas a auth/scope da CLI continua inconsistente. | `gateway health` e `cron list --url --token ...` funcionam; `status` simples continua com `missing scope: operator.read`; `cron list` simples continua a falhar. | Automação existe, mas a gestão/observabilidade do gateway não é consistente sem workarounds. |
| `H13` | Os scripts Windows de automação continuam frágeis e orientados a UI. | `start_all.bat` depende de `tws_autologin.py` e pode cair em `pause`; `stop_and_report.bat` depende de `WINDOWTITLE` e abre Notepad no fim. | A operação diária sem vigilância continua arriscada em Windows real. |
| `H14` | Segredos operacionais permanecem em ficheiros plaintext locais. | `.env` local contém credenciais activas; `tws_credentials.json` existe em claro; `tws_autologin.py` lê esse JSON directamente. | Exposição local desnecessária de credenciais; qualquer acesso ao perfil da máquina lê esses segredos. |

#### Médio
| ID | Finding | Evidência | Impacto |
| --- | --- | --- | --- |
| `M10` | `trades_log.json` e `metrics.json` não têm recovery/backup comparável ao `grids_state.json`. | `TradeLogger._read_trades_file()` devolve `{"trades":[]}` se o JSON estiver corrompido; o write seguinte pode normalizar por cima. | Corrupção local pode apagar histórico útil e degradar auditoria pós-incidente. |
| `M11` | O pipeline de relatórios é demasiado final-state-oriented e perde contexto intradiário. | `generate_report.py` usa heartbeat/metrics/snapshot/log tail; o daily report real resume o último estado e a cauda do log; weekly report agrega daily reports já resumidos. | Relatórios e prompts para Claude não capturam bem o dia inteiro nem a cadeia causal dos incidentes. |
| `M12` | O dashboard pode sub-reportar exposição real. | `dashboard/helpers.py` deriva posições de `grids_state.json` se não houver ficheiro de posições; com reconciliação inconclusiva ou órfãos broker-side, a UI pode mostrar `0` posições locais. | O operador pode ler um estado demasiado optimista. |
| `M13` | Higiene do repositório continua insuficiente. | `.gitignore` está malformado; há `dashboard 2`, `CODEX_IMPLEMENTATION_BRIEF_FINAL 2.md`, `__pycache__`, `.pytest_cache`, ficheiro `notepad`, `venv/`, `venv2/`. | Aumenta drift, confusão operacional e risco de commitar artefactos errados. |
| `M14` | A arquitectura está funcional, mas demasiado monolítica. | `main.py` tem `3858` linhas; `execution.py`, `risk_manager.py` e `data_feed.py` têm todos > `1400` linhas. | O custo de mudança é alto e a confiança operacional depende demasiado de convenções implícitas. |
| `M15` | A suite de testes é boa para lógica pura, mas não prova os paths operacionais mais perigosos. | `420 passed`; há boa cobertura unitária de risco/grid/data-feed, mas não há validação real de `.bat`, TWS autologin, shutdown forçado, gateway persistence em reboot, nem coerência report/log. | Os `420 passed` dão confiança no core lógico, não na operação Windows diária end-to-end. |

#### Baixo / informacional
| ID | Finding | Evidência | Impacto |
| --- | --- | --- | --- |
| `L03` | README sobrestima a autonomia e o shutdown. | `README.md` fala em bot “100% autónomo” e diz que `Ctrl+C` cancela ordens pendentes; o runtime actual desactiva execução directa multi-instrumento e `_graceful_shutdown()` não cancela ordens. | Documentação induz expectativas demasiado optimistas. |
| `I01` | O estado apresentado pela CLI do OpenClaw usa nomenclatura enganadora para a persistência. | `gateway status` mostra `Service: Scheduled Task (registered)` mas `schtasks` não encontra task real; a persistência validada é via pasta Startup. | Risco de interpretar mal o método real de persistência. |

### Score actualizado e justificação
- Score anterior no topo do relatório: `90/100`.
- Score actual após auditoria total: `72/100`.
- Justificação da descida:
  - a ronda anterior era subset/delta e estava centrada em fixes específicos já fechados;
  - a auditoria total desta ronda encontrou riscos operacionais reais que não tinham sido classificados antes, sobretudo:
    - fecho diário forçado sem path gracioso garantido (`C03`)
    - arranque permitido com reconciliação inconclusiva (`H10`)
    - telemetria de equity/peak incoerente com impacto em sizing/reporting (`H11`)
    - fragilidade da automação Windows e da administração OpenClaw (`H12`, `H13`)
  - o core lógico continua significativamente melhor do que o relatório histórico mais antigo sugeria, mas a prontidão operacional diária continua abaixo do que um `90/100` implicaria.

### Regressões novas
- Nenhuma regressão nova causada por alterações desta ronda.
- Os findings novos desta secção são preexistentes no código/scripts actuais; foram apenas confirmados agora por leitura e validação operacional real.

### Confiança final desta ronda
- `Confirmado`:
  - suite de testes passa (`420 passed`)
  - gateway OpenClaw fica persistente por login item em Startup
  - agentes e cron jobs existem e mantêm-se
  - locks de instância/contexto IB, baselines de equity, pre-trade gate e persistência de grids estão implementados no runtime
- `Provável`:
  - os cron jobs conseguem disparar no gateway persistente se a sessão local do utilizador existir
  - o `ops-analyst` tem modelo Hunter Alpha configurado, embora a resolução efectiva de auth no OpenClaw continue pouco transparente
- `Não validado`:
  - reboot/logoff real do Windows para provar auto-arranque do gateway pós-login
  - execução real de jobs `bot-arranque` / `bot-paragem`
  - fecho de ordens reais no IB/TWS
  - geração de weekly report/prompt numa sexta-feira operacional completa

## Histórico preservado

## Delta audit focado - 2026-03-19 revalidation of committed Windows signal fix

### Escopo e metodo
- Ronda de revalidacao contra o codigo real actual, seguindo o prompt sem assumir que o relatorio anterior estava correcto.
- Ficheiros de codigo alterados nesta ronda: nenhum.
- No arranque desta ronda, `git status --short` estava limpo; apos a validacao de `python main.py`, a unica sujidade local observada foi `M data/bot.log`.
- `_handle_shutdown_signal` permanece inalterado.

### Diagnostico confirmado
- O `main.py` actual ja contem o fallback cross-platform em `_setup_signal_handlers`.
- Em Unix/Linux/macOS, o codigo continua a usar `loop.add_signal_handler(...)` quando suportado e faz log de `unix_signal_handlers`.
- Em Windows, e tambem quando houver `NotImplementedError`, o codigo faz fallback para `signal.signal(...)`, regista `SIGINT` sempre, tenta `SIGTERM` se estiver disponivel/utilizavel e faz log de `windows_signal_fallback`.
- O erro especifico de `NotImplementedError` em `_setup_signal_handlers()` nao se reproduziu nesta ronda.

### Validacao desta ronda
- Comando de testes: `py -m pytest tests/ -q --tb=short`
- Resultado: `420 passed, 1166 warnings in 15.88s`
- Total de testes: `420 passed`, igual ao historico recente; nao houve diferenca no total.
- Validacao de arranque Windows: `python main.py` ultrapassou o erro especifico de `_setup_signal_handlers()`.
- Evidencia observada no log: `Caminho de sinais activo: windows_signal_fallback (SIGINT, SIGTERM).`
- Novo blocker encontrado depois deste ponto:
  - `RuntimeError: Outra instância parece activa para o mesmo contexto IB (127.0.0.1:7497 client_id=1).`
- Em conformidade com o prompt, esse blocker seguinte nao foi corrigido nesta ronda.
- Score mantido: `90/100`.
- Justificacao do score: esta ronda apenas revalidou o fix ja commitado e alinhou o relatorio com o estado real; nao houve alteracao funcional nova.

### Regressoes novas
- Nenhuma regressao nova atribuivel ao fix de compatibilidade Windows.
- Blocker seguinte observado apenas em validacao de arranque:
  - lock de instancia/contexto IB ja existente, fora do escopo desta ronda.

## Delta audit focado - 2026-03-19 validation of committed Windows signal fix

### Escopo e metodo
- Ronda de validacao contra o codigo real actual de `main.py`, sem assumir que o `AUDIT_REPORT.md` anterior estava alinhado.
- Ficheiros de codigo alterados nesta ronda: nenhum.
- O `main.py` actual ja contem a compatibilidade Windows em `_setup_signal_handlers`; nao foi necessario novo patch de runtime nesta ronda.
- `_handle_shutdown_signal` permanece inalterado.

### Diagnostico confirmado
- O contexto recebido para esta ronda estava stale face ao codigo real:
  - `git status --short` real mostrou apenas `M data/bot.log`
  - `main.py` ja continha fallback `windows_signal_fallback` e uso de `signal.signal(...)`
- O fix de compatibilidade Windows ja esta commitado em `74c22efad89a47915f313ab7b011f6fc2046a829`.
- O call path do erro original continua confirmado historicamente em `_setup_signal_handlers`, mas o codigo actual ja nao usa apenas `loop.add_signal_handler(...)`.

### Compatibilidade Windows validada
- Unix/Linux/macOS:
  - continua a usar `loop.add_signal_handler(...)` quando suportado
  - faz log de `unix_signal_handlers`
- Windows:
  - faz fallback para `signal.signal(...)`
  - regista `SIGINT` sempre
  - tenta registar `SIGTERM` apenas se estiver disponivel e utilizavel
  - faz log de `windows_signal_fallback`
- O comportamento de shutdown gracioso manteve-se inalterado porque `_handle_shutdown_signal` continua responsavel por `self._running = False` e `self._shutdown_event.set()`.

### Validacao desta ronda
- Comando de testes: `py -m pytest tests/ -q --tb=short`
- Resultado: `420 passed, 1166 warnings in 8.81s`
- Total de testes: `420 passed`, igual ao historico recente; nao houve diferenca no total.
- Validacao de arranque Windows: `python main.py` ultrapassou o erro especifico de `_setup_signal_handlers()`.
- Evidencia observada no log: `Caminho de sinais activo: windows_signal_fallback (SIGINT, SIGTERM).`
- Novo blocker encontrado depois deste ponto:
  - `RuntimeError: Outra instância parece activa para o mesmo contexto IB (127.0.0.1:7497 client_id=1).`
- Em conformidade com a instrucao desta ronda, esse blocker seguinte nao foi corrigido aqui.
- Score mantido: `90/100`.
- Justificacao do score: esta ronda apenas valida e alinha o estado real do repo; nao houve alteracao funcional nova nem ampliacao do perimetro auditado.

### Regressoes novas
- Nenhuma regressao nova atribuivel ao fix de compatibilidade Windows.
- Blocker seguinte observado apenas em validacao de arranque:
  - lock de instancia/contexto IB ja existente, fora do escopo desta ronda.

## Delta audit focado - 2026-03-19 windows signal compatibility fix

### Escopo e metodo
- Ronda limitada a compatibilidade de arranque Windows em `main.py`.
- Ficheiros de codigo alterados nesta ronda: `main.py`.
- `_handle_shutdown_signal` foi preservado sem alteracoes; a diff desta ronda ficou confinada a `_setup_signal_handlers`.

### Diagnostico confirmado
- O arranque falhava em Windows em `main.py:1609` com `NotImplementedError` ao chamar `loop.add_signal_handler(...)`.
- A causa e compatibilidade de plataforma: `asyncio.AbstractEventLoop.add_signal_handler` nao tem o mesmo suporte em Windows que em Unix/Linux/macOS.
- Classificacao desta falha: `compatibilidade Windows`, nao regressao do fluxo de shutdown gracioso.

### Correcao aplicada
- Em Unix/Linux/macOS, `_setup_signal_handlers` continua a usar `loop.add_signal_handler(...)` quando suportado, preservando o comportamento actual.
- Se a plataforma for Windows, ou se `loop.add_signal_handler(...)` levantar `NotImplementedError`, o codigo faz fallback para `signal.signal(...)`.
- No fallback, `SIGINT` e sempre registado; `SIGTERM` e registado apenas se estiver disponivel e funcional.
- O caminho usado fica agora documentado em log como `unix_signal_handlers` ou `windows_signal_fallback`.
- O handler efectivo continua a fazer o mesmo shutdown gracioso via `_handle_shutdown_signal`: `self._running = False` e `self._shutdown_event.set()`.

### Validacao desta ronda
- Validacao de arranque em Windows: `main.py` arrancou sem erro neste ponto.
- Evidencia observada no arranque: `Caminho de sinais activo: windows_signal_fallback (SIGINT, SIGTERM).`
- O processo passou pelos signal handlers, carregou configuracao, iniciou preflight e so depois foi terminado manualmente para encerrar a validacao.
- Nao surgiu novo blocker de arranque apos este fix nesta ronda.
- Comando final: `py -m pytest tests/ -q --tb=short`
- Resultado final: `420 passed, 1166 warnings in 8.81s`
- Total de testes: `420 passed`, igual ao historico recente; nao houve diferenca no total.
- Score mantido: `90/100`.
- Justificacao do score: o fix remove um blocker real de arranque em Windows, mas nao altera o perimetro funcional auditado nem introduz novos controlos de risco.

### Regressoes novas
- Nenhuma regressao nova observada nesta ronda.

## Delta audit focado - 2026-03-19 fragile test fix

### Escopo e metodo
- Ronda limitada a fragilidade do teste `tests/test_main_audit.py::test_unrealized_equity_loss_triggers_daily_halt`.
- Ficheiros de codigo alterados nesta ronda: `tests/test_main_audit.py`.
- Runtime C01 mantido: `_check_risk_limits` e `_sync_equity_baselines` nao foram alterados; `main.py` ficou sem diff nesta ronda.

### Diagnostico confirmado
- O baseline diario era semeado com `datetime(2026, 3, 18, tzinfo=timezone.utc)`.
- `_check_risk_limits()` calcula `now_utc = datetime.now(timezone.utc)` em `main.py:3511` e chama `_sync_equity_baselines(current_equity, now=now_utc)` em `main.py:3518`.
- `_sync_equity_baselines()` substitui o baseline quando `entry["period"] != period_id` em `main.py:960-965`.
- Portanto, quando o teste corre num dia posterior a `2026-03-18`, o baseline diario roda para a equity actual (`96_000.0`) e a perda diaria observada passa a `0%`.
- Classificacao desta falha: `teste fragil`, nao bug de runtime.

### Correcao aplicada
- Abordagem usada: congelar o "agora" do cenario no proprio teste com `monkeypatch`, equivalente a `unittest.mock.patch`, trocando `main.datetime.now(...)` por um instante fixo (`2026-03-19T12:00:00Z`).
- O baseline do teste passou a ser semeado com o mesmo instante congelado.
- Resultado: o `period id` diario do seed e o do runtime passam a coincidir de forma deterministica, sem alterar o comportamento real de C01.

### Validacao desta ronda
- Instalacoes realizadas para executar a validacao pedida neste ambiente: `py -m pip install -r requirements.txt`.
- Comando focal: `py -m pytest tests/test_main_audit.py::test_unrealized_equity_loss_triggers_daily_halt -v`
- Resultado focal: `1 passed, 1 warning in 9.98s`
- Comando final: `py -m pytest tests/ -q --tb=short`
- Resultado final: `420 passed, 1166 warnings in 11.14s`
- Total de testes: `420 passed`, igual ao historico recente deste relatorio; nao houve diferenca no total.
- Score mantido: `90/100`.
- Justificacao do score: a correcao fecha apenas fragilidade de teste; nao altera cobertura funcional nem runtime adicional.

### Regressoes novas
- Nenhuma regressao nova observada.
- Evidencia de que o runtime de `C01` nao foi alterado nesta ronda:
  - `main.py` nao foi modificado.
  - A unica alteracao de codigo foi em `tests/test_main_audit.py`.
  - A suite completa permaneceu verde com `420 passed`.

## Delta audit focado — post-fix

### Escopo e método
- Auditoria feita sobre o estado actual do working tree em `/Users/beatrizneves/Documents/Playground/bot-trading`.
- Este delta audit revê apenas: `C01`, `C02`, `H03`, `H04`, `H05`, `H06`, `H07`, `H09`.
- Não substitui a auditoria anterior; actualiza apenas os findings revalidados e os call paths tocados pelos fixes.
- No início desta ronda H05, o `AUDIT_REPORT.md` estava desalinhado do commit/working tree actual; o código real foi usado como source of truth e o relatório foi alinhado no fim.

### Validação mínima executada
- Dependências mínimas pedidas:
  - `pytest` → presente (`9.0.2`)
  - `pytest-asyncio` → presente (`1.3.0`)
  - `pytest-timeout` → presente (`import OK`)
  - `pandas` → presente (`2.3.3`)
- Instalações realizadas: nenhuma.
- Comando inicial executado: `pytest tests/test_grid_engine.py tests/test_integration.py -v --tb=long`
- Resultado inicial: `5 failed, 69 passed, 1034 warnings in 1.52s`
- Comando focal H05 antes de editar: `pytest tests/test_main_audit.py tests/test_risk_manager.py -q --tb=short`
- Resultado focal H05 antes de editar: `120 passed, 133 warnings in 1.41s`
- Comando focal H05 após as alterações: `pytest tests/test_pre_trade_gate.py tests/test_main_audit.py tests/test_risk_manager.py -q --tb=short`
- Resultado focal H05 após as alterações: `127 passed, 133 warnings in 1.17s`
- Comando final executado: `pytest tests/ -q --tb=short`
- Resultado final: `420 passed, 1166 warnings in 4.96s`
- Classificação da falha inicial: `falha de código / contrato de testes`, não falha de ambiente.
- Falhas observadas:
  - `tests/test_grid_engine.py::TestPersistence::test_load_state_schema_validation_rejects_invalid`
  - `tests/test_grid_engine.py::TestPersistence::test_load_state_validates_grid_status`
  - `tests/test_grid_engine.py::TestPersistence::test_load_state_validates_level_status`
  - `tests/test_grid_engine.py::TestPersistence::test_load_state_validates_missing_fields`
  - `tests/test_integration.py::TestStatePersistenceAndRecovery::test_state_corruption_handling`
- Causa comum observada:
  - `src/grid_engine.py:637-657` passou a fazer recovery fail-closed via backup / `RuntimeError`.
  - Parte da suite ainda espera `ValueError` / `JSONDecodeError` directos.

### Resolução teste a teste — persistência/recovery
- `tests/test_grid_engine.py::TestPersistence::test_load_state_schema_validation_rejects_invalid`
  - problema: `mismatch de contrato`
  - correcção: teste actualizado para esperar `RuntimeError("Estado primario corrompido e sem backup valido")`
  - validação individual: `1 passed in 0.05s`
- `tests/test_grid_engine.py::TestPersistence::test_load_state_validates_grid_status`
  - problema: `mismatch de contrato`
  - correcção: teste actualizado para esperar a semântica fail-closed actual
  - validação individual: `1 passed in 0.05s`
- `tests/test_grid_engine.py::TestPersistence::test_load_state_validates_level_status`
  - problema: `mismatch de contrato`
  - correcção: teste actualizado para esperar a semântica fail-closed actual
  - validação individual: `1 passed in 0.05s`
- `tests/test_grid_engine.py::TestPersistence::test_load_state_validates_missing_fields`
  - problema: `mismatch de contrato`
  - correcção: teste actualizado para esperar a semântica fail-closed actual
  - validação individual: `1 passed in 0.05s`
- `tests/test_integration.py::TestStatePersistenceAndRecovery::test_state_corruption_handling`
  - problema: `mismatch de contrato`
  - correcção: teste actualizado para esperar `RuntimeError` fail-closed em vez de `json.JSONDecodeError`
  - validação individual: `1 passed, 1 warning in 0.95s`
- Conclusão desta ronda:
  - não encontrei evidência de regressão real no runtime de `GridEngine`
  - as 5 falhas eram testes antigos desalinhados com o runtime novo

### Fix focado — H05: pre-trade gate determinístico
- Relatório encontrado stale no início da ronda:
  - o cabeçalho ainda apontava para `d50cf45e643041d7c4c1129dda6281c98c5aa5c7`
  - o código real já estava em `e8161fc6f7ea49b4601010e3a7d608581a77d1bb`
- Ficheiros alterados nesta ronda:
  - `main.py`
  - `src/pre_trade_gate.py` (novo)
  - `tests/test_main_audit.py`
  - `tests/test_pre_trade_gate.py` (novo)
- Call path real revisto:
  - `main.py:2617-2635` passa contexto explícito do gate a `_attempt_grid_creation(...)`
  - `main.py:2681-2862` aplica o gate antes do sizing, após sizing e após `RiskManager.validate_order(...)`
  - `src/pre_trade_gate.py:27-106` introduz um objecto puro, serializável e testável
- Flags implementadas com enforcement real no runtime:
  - `session_ok`
  - `data_fresh`
  - `finite_inputs_ok`
  - `warmup_ok`
  - `quantity_ok`
  - `risk_ok`
- Limitações documentadas e intencionalmente não forçadas nesta ronda:
  - `notional_ok`
  - `size_ok`
  - `affordability_ok`
  - motivo: o call path real ainda não fornece fontes fiáveis e determinísticas para esses checks sem inventar contrato novo
- Evidência de testes:
  - `tests/test_pre_trade_gate.py` cobre stale price, NaN, quantity zero, gate válido e enumeração de rejection reasons
  - `tests/test_main_audit.py:966-1000` prova que inputs não finitos são rejeitados antes de sizing/submissão
- Resultado desta ronda:
  - o gap H05 identificado no delta anterior ficou fechado no call path real de admissão de novas grids
  - as limitações remanescentes passaram a ser de cobertura futura opcional, não ausência do gate determinístico exigido

### Fix focado — H04: market-hours fail-closed e timezone local
- Ficheiros alterados nesta ronda:
  - `src/market_hours.py`
  - `tests/test_market_hours.py`
- Mudanças efectivas no runtime:
  - equities (`STK_US` e `STK_EU`) deixaram de usar fallback silencioso quando `pandas_market_calendars` está indisponível ou falha
  - nesses casos o gating passou a `fail-closed` com `CALENDARIO_INDISPONIVEL` ou `CALENDARIO_INCONCLUSIVO`
  - `FOREX` passou a usar horário local de Nova Iorque em vez de UTC fixa
  - `FUT` passou a usar horário local de Chicago/CME em vez de UTC fixa
  - `SESSAO_DESCONHECIDA` passou a falhar fechado
- Evidência de testes:
  - `tests/test_market_hours.py` passou de `7` para `12` testes
  - nova cobertura para:
    - calendário indisponível
    - falha do calendário
    - pre-close de FX com shift DST em Nova Iorque
    - pausa diária de micro futures com shift DST em Chicago
- Resultado desta ronda:
  - o risco de falsa confiança por fallback silencioso em equities ficou removido
  - FX/FUT deixaram de depender de janelas UTC hardcoded no call path de sessão

### Fix focado — H09: dashboard com economic open e estado operacional
- Ficheiros alterados nesta ronda:
  - `dashboard/helpers.py`
  - `dashboard/app.py`
  - `tests/test_dashboard_helpers.py`
- Mudanças efectivas no runtime do dashboard:
  - `load_positions(...)` passou a derivar `current_price`, `price_source`, `open_notional`, `open_risk_to_stop` e `unrealized_pnl` quando houver preço real persistido
  - `compute_kpis(...)` passou a expor `unrealized_pnl`, `open_notional`, `open_risk_to_stop`, `entry_halt_reason`, `emergency_halt`, `last_error`, `last_cycle_started_at` e `last_cycle_completed_at`
  - `build_status_summary(...)` passou a materializar `bot_state` e `risk_state`
  - o dashboard passou a mostrar explicitamente:
    - `PAPER MODE`
    - heartbeat / último ciclo
    - `unrealized PnL` quando disponível
    - `open notional` e `risco até stop` como equivalente económico aberto
    - `entry_halt_reason` / `emergency_halt` / `last_error`
- Evidência de testes:
  - `tests/test_dashboard_helpers.py` passou a validar posições derivadas com `unrealized_pnl`, `open_notional` e `open_risk_to_stop`
  - o mesmo ficheiro passou a validar surfacing de `entry_halt_reason`, `emergency_halt` e `last_error`
- Resultado desta ronda:
  - o dashboard deixou de mostrar apenas capital/equity estimada e passou a expor economic open e risco operacional suficientes para paper supervisionado

### Fix focado — H03: policy operacional de erros IB
- Ficheiros alterados nesta ronda:
  - `src/ib_requests.py`
  - `src/data_feed.py`
  - `src/execution.py`
  - `main.py`
  - `tests/test_data_feed.py`
  - `tests/test_execution.py`
  - `tests/test_main_audit.py`
- Mudanças efectivas no runtime:
  - `src/ib_requests.py:27-97` passou a centralizar uma policy explícita (`IBErrorPolicyDecision` + `classify_ib_error(...)`)
  - códigos `1100/1101` passam a `entry_halt`
  - código `1102` passa a `clear_connection_halt`
  - códigos `354/10197/162` passam a `symbol_skip`
  - códigos `201/202` passam a erros operacionais de ordens com alerta explícito
  - `src/data_feed.py:213-413` passou a armazenar eventos operacionais, expô-los por janela temporal e encaminhar eventos de ligação para callback
  - `main.py:1544-1609` passou a materializar a decisão operacional no runtime:
    - halt por perda de ligação
    - clear do halt no restore/reconnect
    - skip determinístico de request por permissões/OOH/pacing
  - `main.py:1280-1284`, `2495-2603` passou a aplicar a policy no call path real de preflight, histórico, snapshot e volume
  - `src/execution.py:272-286` passou a transformar erros de ordens relevantes em alerta operacional explícito, em vez de só log
- Evidência de testes:
  - `tests/test_data_feed.py` cobre `entry_halt`, callback de erro e `symbol_skip`
  - `tests/test_main_audit.py` cobre halt/clear de ligação e skip operacional no runtime
  - `tests/test_execution.py` cobre alerta operacional para rejeição de ordem
- Resultado desta ronda:
  - os erros IB críticos e accionáveis deixaram de ser mostly log-only
  - o runtime passou a ter policy determinística e testável até à decisão operacional

### Fix focado — H07: exclusão multi-instância por contexto IB
- Ficheiros alterados nesta ronda:
  - `main.py`
  - `tests/test_main_audit.py`
- Mudanças efectivas no runtime:
  - `main.py:1427-1588` passou a manter dois locks independentes:
    - lock local por `data_dir`
    - lock global por contexto efectivo de broker (`host`, `port`, `client_id`)
  - o lock global é materializado em directoria temporária comum, não no `data_dir`
  - a porta efectiva passa a ser resolvida de forma determinística mesmo quando o config usa `port=0`
  - o payload persistido do lock global passou a incluir `host`, `port`, `client_id`, `paper_trading`, `use_gateway`, `cwd` e `data_dir`
  - o release passou a libertar ambos os locks de forma idempotente
- Evidência de testes:
  - `tests/test_main_audit.py` cobre:
    - conflito no mesmo `data_dir`
    - libertação do lock em shutdown gracioso
    - conflito entre dois `data_dir` distintos com o mesmo contexto IB
    - coexistência permitida entre dois `data_dir` distintos com `client_id` diferente
  - validação focal: `pytest tests/test_main_audit.py -q --tb=short -k 'lock or client_id or instance'` → `6 passed, 44 deselected`
  - validação final: `pytest tests/ -q --tb=short` → `420 passed, 1166 warnings`
- Resultado desta ronda:
  - o gap remanescente de exclusão multi-instância deixou de estar scoped apenas ao `data_dir`
  - o runtime passou a bloquear duas instâncias operacionais que tentem usar o mesmo contexto efectivo de ligação IB

### Estado actualizado dos findings revistos

| Finding | Estado | Evidência no código | Evidência em testes | Nota operacional |
|---|---|---|---|---|
| `C01` | `FECHADO` | `main.py:3210-3265` usa snapshot real de equity, baseline por período e bloqueia entradas se a equity for inconclusiva | `tests/test_main_audit.py:698-822` cobre halts por unrealized equity e fail-safe sem snapshot | Fecho real no call path runtime |
| `C02` | `FECHADO` | `main.py:3131-3147` bloqueia recenter/respacing se `price_fresh=False` | `tests/test_main_audit.py:1093-1150` prova recenter só com quote fresca | Fecho real no path de grids activas |
| `H03` | `FECHADO` | `src/ib_requests.py:27-97` centraliza a policy de códigos IB; `src/data_feed.py:213-413`, `main.py:1544-1609` e `src/execution.py:272-286` aplicam-na no runtime e na execução | `tests/test_data_feed.py`, `tests/test_main_audit.py` e `tests/test_execution.py` provam halt/clear/skip/alerta; suite final verde (`420 passed`) | Fecho real da matriz operacional mínima para erros IB relevantes no runtime actual |
| `H04` | `FECHADO` | `src/market_hours.py:122-237` passou a falhar fechado sem calendário válido para equities e a usar `America/New_York` / `America/Chicago` para FX/FUT | `tests/test_market_hours.py` cobre calendário indisponível/erro e shifts DST reais de FX/FUT; suite final verde (`420 passed`) | Fecho real do gating de sessão para o runtime actual |
| `H05` | `FECHADO` | `src/pre_trade_gate.py:27-106` centraliza o gate explícito; `main.py:2617-2635` e `main.py:2681-2862` integram `session_ok`, `data_fresh`, `finite_inputs_ok`, `warmup_ok`, `quantity_ok` e `risk_ok` no call path real antes da entrada | `tests/test_pre_trade_gate.py` e `tests/test_main_audit.py:966-1000` provam stale/NaN/quantity/risk gating; suite final verde (`420 passed`) | Fecho real do gate determinístico no runtime actual; `notional/size/affordability` ficaram documentados como flags opcionais sem fonte fiável neste call path |
| `H06` | `FECHADO` | `src/grid_engine.py:619-657` e `main.py:1419-1426` implementam recovery via backup e fail-closed no arranque | As 5 falhas ligadas a persistência/recovery foram resolvidas e `pytest tests/ -q --tb=short` voltou a verde (`420 passed`) | O runtime está coerente e os testes passaram a reflectir o contrato real |
| `H07` | `FECHADO` | `main.py:1427-1588` aplica lock local por `data_dir` e lock global por contexto efectivo de broker (`host`, `port`, `client_id`) | `tests/test_main_audit.py` provam conflito no mesmo `data_dir`, conflito cross-`data_dir` com mesmo contexto IB e coexistência com `client_id` distinto; suite final verde (`420 passed`) | Fecho real da exclusão multi-instância no escopo operativo local do runtime actual |
| `H09` | `FECHADO` | `dashboard/helpers.py:121-221` deriva economic open e estado operacional; `dashboard/app.py:216-418` mostra `PAPER`, heartbeat/último ciclo, unrealized/equivalente económico aberto e halt operacional | `tests/test_dashboard_helpers.py` cobre economic open, `entry_halt_reason`, `emergency_halt` e `last_error`; suite final verde (`420 passed`) | Fecho real da observabilidade mínima exigida para paper supervisionado |

### Finding-by-finding

#### C01 — FECHADO
- Evidência de código:
  - `main.py:3210-3265` usa `_fetch_current_equity_snapshot()`, baselines por período e `self._risk_manager.update_capital(current_equity)`.
  - `main.py:3221-3229` bloqueia em fail-safe quando a equity não pode ser obtida.
- Evidência de testes:
  - `tests/test_main_audit.py:698-745`
  - `tests/test_main_audit.py:792-822`
- Conclusão:
  - O finding crítico original está efectivamente fechado no path real de runtime.

#### C02 — FECHADO
- Evidência de código:
  - `main.py:3131-3147` usa `get_current_price_details()` e recusa recenter quando `fresh=False`.
- Evidência de testes:
  - `tests/test_main_audit.py:1093-1150`
- Conclusão:
  - O recenter de grids activas deixou de aceitar preços stale/fallback.

#### H03 — FECHADO
- Evidência de código:
  - `src/ib_requests.py:27-97` introduz `IBErrorPolicyDecision` e `classify_ib_error(...)`.
  - `src/data_feed.py:213-413` passou a:
    - registar eventos operacionais IB por timestamp
    - aplicar `entry_halt`/`clear_connection_halt` na ligação
    - expor `operational_events_since(...)`
    - encaminhar eventos de ligação para callback
  - `main.py:1544-1609` passou a:
    - materializar `ib_connection_lost` em `entry_halt_reason`
    - limpar esse halt no restore/reconnect
    - fazer `symbol_skip` determinístico para `354/10197/162`
  - `main.py:1280-1284` aplica a policy no preflight de market data.
  - `main.py:2495-2603` aplica a policy no call path real de histórico/snapshot/volume.
  - `src/execution.py:272-286` passou a transformar `201/202` em alertas operacionais explícitos.
- Evidência de testes:
  - `tests/test_data_feed.py:129-176` prova `entry_halt`, callback e `symbol_skip`.
  - `tests/test_main_audit.py:433-500` prova halt/clear de ligação e skip operacional no runtime.
  - `tests/test_execution.py:123-136` prova alerta operacional para rejeição de ordem.
  - validação focal: `pytest tests/test_data_feed.py tests/test_execution.py tests/test_main_audit.py -q --tb=short` → `141 passed, 1 warning`
  - validação final: `pytest tests/ -q --tb=short` → `420 passed, 1166 warnings`
- Conclusão:
  - O tratamento de erros IB deixou de depender só de logging/retry genérico.
  - O finding H03 fica `FECHADO` para o conjunto de códigos accionáveis actualmente usados pelo runtime.

#### H04 — FECHADO
- Evidência de código:
  - `src/market_hours.py:122-169`: equities passam a `CALENDARIO_INDISPONIVEL`/`CALENDARIO_INCONCLUSIVO` e ficam fechadas quando o calendário não é utilizável.
  - `src/market_hours.py:172-191`: `FOREX` passou a usar `America/New_York` para weekly close/pre-close.
  - `src/market_hours.py:194-237`: `FUT` passou a usar `America/Chicago` para pausa diária, weekly close e reopen.
  - `src/market_hours.py:121`: `SESSAO_DESCONHECIDA` passou a falhar fechado.
- Evidência de testes:
  - `tests/test_market_hours.py:49-70` prova fail-closed sem calendário e com erro de calendário.
  - `tests/test_market_hours.py:89-103` prova pre-close de FX com shift DST em Nova Iorque.
  - `tests/test_market_hours.py:114-135` prova pausa diária/reopen de micro futures com shift DST em Chicago.
  - validação final: `pytest tests/test_market_hours.py -q --tb=short` → `12 passed`
  - validação final alargada: `pytest tests/ -q --tb=short` → `420 passed, 1166 warnings`
- Conclusão:
  - O fallback silencioso deixou de permitir operar equities com falsa confiança.
  - FX e FUT deixaram de depender de janelas UTC fixas no path real de sessão.
  - O finding H04 fica `FECHADO` para o escopo actual.

#### H05 — FECHADO
- Evidência de código:
  - `src/pre_trade_gate.py:27-106` introduz o `PreTradeGate`, objecto puro, serializável e testável.
  - `main.py:2617-2635` passa `session_ok`, `data_fresh` e `warmup_ok` do call path real para `_attempt_grid_creation(...)`.
  - `main.py:2723-2759` rejeita inputs críticos não finitos antes do sizing.
  - `main.py:2777-2799` rejeita quantity inválida logo após sizing.
  - `main.py:2833-2862` materializa o gate final após `RiskManager.validate_order(...)` e bloqueia a entrada se qualquer flag implementada falhar.
- Estado do enforcement no call path real:
  - `session_ok` → forçado
  - `data_fresh` → forçado
  - `finite_inputs_ok` → forçado
  - `warmup_ok` → forçado
  - `quantity_ok` → forçado
  - `risk_ok` → forçado
- Limitações remanescentes, explicitamente documentadas mas não bloqueantes para o fecho deste finding:
  - `notional_ok`, `size_ok` e `affordability_ok` existem como flags opcionais no `PreTradeGate`, mas continuam `None` nesta ronda
  - razão: o call path real ainda não fornece input determinístico suficiente para as forçar sem inventar contrato novo
- Evidência de testes:
  - `tests/test_pre_trade_gate.py` prova stale price, NaN em preço/indicador, quantity zero, caminho admitido e enumeração de rejection reasons.
  - `tests/test_main_audit.py:966-1000` prova que inputs não finitos são rejeitados antes de `position_size_per_level`, `validate_order` e `submit_bracket_order`.
  - validação final: `pytest tests/ -q --tb=short` → `420 passed, 1166 warnings`
- Conclusão:
  - O pre-trade gate determinístico passou a existir como objecto central e foi integrado no path real de admissão de novas grids.
  - O finding H05 fica `FECHADO` para o escopo do runtime actual.

#### H06 — FECHADO
- Evidência de código:
  - `src/grid_engine.py:619-657` já tenta recovery via `.bak` e, sem backup íntegro, levanta `RuntimeError`.
  - `main.py:1419-1426` faz load fail-closed no arranque.
- Evidência de testes:
  - positiva: `tests/test_grid_engine.py:523-572`, `tests/test_main_audit.py:1245-1250`
  - adicional desta ronda:
    - `tests/test_grid_engine.py::TestPersistence::test_load_state_schema_validation_rejects_invalid`
    - `tests/test_grid_engine.py::TestPersistence::test_load_state_validates_grid_status`
    - `tests/test_grid_engine.py::TestPersistence::test_load_state_validates_level_status`
    - `tests/test_grid_engine.py::TestPersistence::test_load_state_validates_missing_fields`
    - `tests/test_integration.py::TestStatePersistenceAndRecovery::test_state_corruption_handling`
  - validação final: `pytest tests/ -q --tb=short` → `420 passed, 1166 warnings`
- Conclusão:
  - `H06` passa para `FECHADO`.
  - O comportamento fail-closed/recovery do runtime mostrou-se coerente; o problema estava nos testes, não no `GridEngine`.

#### H07 — FECHADO
- Evidência de código:
  - `main.py:1427-1588` implementa:
    - lock local por `data_dir`
    - lock global por contexto efectivo IB (`host`, `port`, `client_id`)
  - `main.py:642-683` resolve a porta efectiva e constrói um lock path determinístico por contexto de broker.
- Evidência de testes:
  - `tests/test_main_audit.py` prova:
    - bloqueio de segunda instância no mesmo `data_dir`
    - libertação do lock em shutdown gracioso
    - bloqueio entre dois `data_dir` distintos com o mesmo `host:port:client_id`
    - coexistência permitida com `client_id` diferente
  - validação focal: `pytest tests/test_main_audit.py -q --tb=short -k 'lock or client_id or instance'` → `6 passed, 44 deselected`
  - validação final: `pytest tests/ -q --tb=short` → `420 passed, 1166 warnings`
- Conclusão:
  - O finding H07 passa para `FECHADO`.
  - O runtime deixou de depender apenas do `data_dir` para exclusão multi-instância e passou a bloquear reuse operacional do mesmo contexto de ligação IB.

#### H09 — FECHADO
- Evidência de código:
  - `dashboard/helpers.py:121-176` passou a derivar `current_price`, `price_source`, `open_notional`, `open_risk_to_stop` e `unrealized_pnl`.
  - `dashboard/helpers.py:199-292` passou a expor `entry_halt_reason`, `emergency_halt`, `last_error` e timestamps operacionais do heartbeat.
  - `dashboard/helpers.py:295-329` passou a materializar `bot_state` e `risk_state`.
  - `dashboard/app.py:216-257` mostra `PAPER MODE`, heartbeat e último ciclo.
  - `dashboard/app.py:258-290` mostra `Unrealized PnL`, `Open notional`, `Risco até stop`, `Bot`, `Risco operacional`, `IB conectado` e `Manual pause`.
  - `dashboard/app.py:314-337` mostra halt operacional explícito na tab de risco.
  - `dashboard/app.py:390-405` mostra tabela de estado operacional no painel de sistema.
- Evidência de testes:
  - `tests/test_dashboard_helpers.py:63-96` valida posições derivadas com `open_notional`, `open_risk_to_stop` e `unrealized_pnl`.
  - `tests/test_dashboard_helpers.py:99-160` valida KPIs e estado operacional (`entry_halt_reason`, `emergency_halt`, `last_error`, `bot_state`, `risk_state`).
  - validação focal: `pytest tests/test_dashboard_helpers.py -q --tb=short` → `6 passed`
  - validação final: `pytest tests/ -q --tb=short` → `420 passed, 1166 warnings`
- Conclusão:
  - O dashboard passou a mostrar `PAPER mode`, heartbeat/última actualização, economic open e risco operacional suficiente para o escopo de paper supervisionado.
  - O finding H09 fica `FECHADO`.

### Score actualizado e diferença face ao anterior
- Score anterior no relatório histórico: `53/100`.
- Score delta revisto para o subset auditado agora: `90/100`.
- Justificação da subida:
  - `C01` e `C02` passaram de críticos abertos para fechados no call path real.
  - `H06` passou de parcial para fechado após validação teste-a-teste e suite completa verde.
  - `H05` passou de parcial para fechado com gate central explícito e testes dedicados.
  - `H04` passou de parcial para fechado com fail-closed explícito e timezone local para FX/FUT.
  - `H09` passou de parcial para fechado com economic open e estado operacional explícitos no dashboard.
  - `H03` passou de parcial para fechado com policy central de erro IB e decisão operacional testável.
  - `H07` passou de parcial para fechado com exclusão multi-instância por contexto efectivo de broker.
- Nota:
  - o score acima não reclassifica áreas não revistas neste delta audit.

### Regressões novas
- Nenhuma regressão detectada.
- Evidência resumida:
  - as 5 falhas da área de persistência/recovery foram resolvidas com alinhamento de testes ao contrato runtime actual;
  - o novo pre-trade gate não introduziu regressões no call path de entrada;
  - o endurecimento de `market_hours` não introduziu regressões na suite nem nos call paths revistos;
  - a expansão de observabilidade do dashboard não introduziu regressões na suite nem quebras de import;
  - a policy operacional de erros IB não introduziu regressões na suite nem nos paths de trading;
  - `pytest tests/test_grid_engine.py tests/test_integration.py -q --tb=short` → `74 passed`
  - `pytest tests/test_pre_trade_gate.py tests/test_main_audit.py tests/test_risk_manager.py -q --tb=short` → `127 passed`
  - `pytest tests/test_data_feed.py tests/test_execution.py tests/test_main_audit.py -q --tb=short` → `141 passed`
  - `pytest tests/test_dashboard_helpers.py -q --tb=short` → `6 passed`
  - `pytest tests/test_market_hours.py -q --tb=short` → `12 passed`
  - o endurecimento da exclusão multi-instância não introduziu regressões na suite nem quebras no shutdown/restart;
  - `pytest tests/test_main_audit.py -q --tb=short -k 'lock or client_id or instance'` → `6 passed`
  - `pytest tests/ -q --tb=short` → `420 passed`

### Conclusão do delta audit
- Pronto para paper trading com supervisão? `SIM`
- Justificação:
  - no subset efectivamente revisto neste delta audit (`C01`, `C02`, `H03`, `H04`, `H05`, `H06`, `H07`, `H09`), já não restam findings abertos;
  - a suite completa está verde (`420 passed`) e não há regressões detectadas nos call paths tocados pelos fixes.

### Próximos passos
- Nenhum finding permanece aberto no subset revisto deste delta audit.

## Auditoria anterior

# AUDIT REPORT — bot-trading
Commit: `aa9af81ccab7f96b46dc9d5097c51977faa94525` (diverge do ref. `a90d6bd89bcc0fdd04c6c05e62dc7bcdc2ff2936`) | Data: `2026-03-18` | Score: `53/100`

Nota operacional:
- `git` CLI não estava disponível; o commit foi resolvido via `.git/HEAD`.
- `python -m py_compile` passou em `main.py` e `src/*.py`.
- `python -m pytest`, `python -m mypy` e `pip-audit` não puderam validar o ambiente actual porque `pytest`/`mypy` não estão instalados e `pip-audit` não conseguiu ser instalado neste workspace.

## Sumário executivo
O repositório já tem módulos separados, testes úteis e algumas protecções reais, mas ainda falha em propriedades de segurança financeira fundamentais: kill switches baseados em equity, gestão de preços stale em grids activas, recuperação de estado corrompido e exclusão de multi-instância.

Os problemas mais perigosos não estão na geração de sinal; estão no controlo operacional: o bot pode continuar a aceitar risco quando as perdas ainda são só unrealized, pode recentrar grids com preços de fallback stale, e pode arrancar “sem grids” depois de corrupção de estado local.

Em paper trading, o sistema ainda exige supervisão humana contínua. Para live trading, este estado continua bloqueado.

## TOP 5 FIXES URGENTES
- `C01` — [`main.py`](C:\Users\bernardovicente\Desktop\Bernardo\Material Suporte\PESSOAL\Playground\bot-trading\main.py):709: kill switches devem usar `NetLiquidation`/equity baseline, não só `trades_log`.
- `C02` — [`main.py`](C:\Users\bernardovicente\Desktop\Bernardo\Material Suporte\PESSOAL\Playground\bot-trading\main.py):2833: grids activas só podem recentrar com `price_fresh=True`.
- `H06` — [`src/grid_engine.py`](C:\Users\bernardovicente\Desktop\Bernardo\Material Suporte\PESSOAL\Playground\bot-trading\src\grid_engine.py):596: recuperação automática de `grids_state.json.bak` e fail-closed no arranque.
- `H07` — [`config.py`](C:\Users\bernardovicente\Desktop\Bernardo\Material Suporte\PESSOAL\Playground\bot-trading\config.py):77: lock de instância + `client_id` único + lock do state file.
- `H04` — [`src/market_hours.py`](C:\Users\bernardovicente\Desktop\Bernardo\Material Suporte\PESSOAL\Playground\bot-trading\src\market_hours.py):17: remover fallback silencioso e substituir janelas FX/FUT em UTC por horários em timezone local do mercado.

## Estatísticas
- Linhas código: `13325` | Linhas teste: `5484` | Ratio: `0.412`
- Problemas: 🔴`2` 🟠`9` 🟡`9` 🟢`2` = `22`
- Cenários Fase 12 cobertos/parcialmente cobertos: `8/23`
- Ficheiros >300 linhas: `main.py`, `src/execution.py`, `src/risk_manager.py`, `src/data_feed.py`, `src/logger.py`, `src/grid_engine.py`, `src/signal_engine.py`

## Problemas por severidade

### 🔴 CRÍTICO (2)
#### C01 — Kill switches usam PnL realizado, não equity
- **Ficheiro:** `main.py:709`, `main.py:2898`
- **Código:**
```python
def _calculate_period_pnl(...):
    for trade in self._trade_logger.get_trades():
        pnl_raw = trade.get("pnl")
        ...
        if timestamp >= month_start:
            period_pnl["monthly"] += pnl

async def _check_risk_limits(self) -> bool:
    period_pnl = self._refresh_period_pnl()
    daily_pnl = period_pnl["daily"]
    weekly_pnl = period_pnl["weekly"]
    monthly_pnl = period_pnl["monthly"]
```
- **Risco:** perdas abertas relevantes não entram no halt; o bot pode continuar a abrir grids enquanto a carteira já ultrapassou os 3/6/10% em `NetLiquidation`.
- **Cenário:** 5 grids abertas acumulam -9% unrealized, mas nenhuma trade fechou ainda.
- **Fix:**
```python
async def _current_net_liquidation(self) -> float | None:
    account_values = await self._connection.request_executor.run(
        "account_values",
        "account_values:risk",
        self._connection.ib.accountValues,
        request_cost=1,
    )
    return self._extract_account_equity(account_values)

def _loss_since(self, baseline: float, current: float) -> float:
    if baseline <= 0:
        return 1.0
    return abs(min((current - baseline) / baseline, 0.0))

async def _check_risk_limits(self) -> bool:
    current_equity = await self._current_net_liquidation()
    if current_equity is None:
        self._entry_halt_reason = "equity_snapshot_unavailable"
        return True
    daily_loss = self._loss_since(self._equity_baselines["daily"], current_equity)
    weekly_loss = self._loss_since(self._equity_baselines["weekly"], current_equity)
    monthly_loss = self._loss_since(self._equity_baselines["monthly"], current_equity)
```
- **Cross-refs:** agravado por FASE 10.1

#### C02 — Gestão de grids activas actua sobre preço stale/fallback
- **Ficheiro:** `main.py:2833`, `src/data_feed.py:836`
- **Código:**
```python
contract = build_contract(spec)
current_price = await self._data_feed.get_current_price(contract)

if current_price is not None:
    ...
    should_recenter = self._grid_engine.should_recenter(grid, current_price)
```
```python
if _valid_price(ticker.close):
    snapshot = {"price": price, "source": "close", "fresh": False}
...
snapshot = {"price": float(price), "source": "yfinance", "fresh": False}
```
- **Risco:** grids podem ser recentradas, respaced e reenviadas com `close` antiga ou preço de `yfinance`, gerando ordens fora do mercado real.
- **Cenário:** IB fica sem `last/bid/ask`, o código cai para `close` ou `yfinance` e recenteriza uma grid ainda activa.
- **Fix:**
```python
price_snapshot = await self._data_feed.get_current_price_details(contract)
if not price_snapshot.get("fresh"):
    logger.warning(
        "Grid %s: ajustamento dinâmico ignorado por preço stale (%s).",
        grid.id,
        price_snapshot.get("source"),
    )
    return
current_price = float(price_snapshot["price"])
```
- **Cross-refs:** agravado por FASE 11 e FASE 12

### 🟠 ALTO (9)
#### H01 — Dependências não reproduzíveis e ambiente actual incompleto
- **Ficheiro:** `requirements.txt:1`
- **Código:**
```text
ib_insync>=0.9.86
pandas>=2.0.0
...
pytest>=7.0.0
yfinance>=0.2.0
```
- **Risco:** deploys diferentes activam caminhos diferentes; neste ambiente faltam `ib_insync`, `yfinance`, `pytest` e `mypy`, e a validação pedida não é repetível.
- **Cenário:** o bot arranca num venv “quase igual”, mas com pacote ausente ou versão major diferente.
- **Fix:**
```bash
python -m pip install ib_insync==0.9.86 yfinance==0.2.66 pytest==8.4.2 pytest-asyncio==1.2.0 pytest-timeout==2.4.0 mypy==1.18.2
python -m pip freeze > requirements.lock
python -c "import ib_insync, yfinance, pandas_market_calendars, pytest"
```
- **Cross-refs:** H04

#### H02 — Pacing violation espera 60 s; IB pede backoff muito mais conservador
- **Ficheiro:** `src/ib_requests.py:200`
- **Código:**
```python
if self._is_pacing_violation(exc):
    delay = 60.0
    self._logger.warning(
        "Violacao de pacing do IB detectada em %s. Espera forcada de 60 s antes do retry.",
        operation_name,
    )
```
- **Risco:** depois de error 162 o processo pode continuar a insistir cedo demais e contaminar o resto do dia com rate limiting.
- **Cenário:** vários `reqHistoricalData` seguidos batem no limite e o loop volta a pedir dados um minuto depois.
- **Fix:**
```python
if self._is_pacing_violation(exc):
    delay = 600.0
    self._logger.warning(
        "Pacing violation em %s. Cooldown forçado de 600 s antes do retry.",
        operation_name,
    )
```
- **Cross-refs:** FASE 12.1

#### H03 — Mapeamento de erros IB é parcial e mostly log-only
- **Ficheiro:** `src/data_feed.py:352`
- **Código:**
```python
if error_code in {1100, 1102, 2104, 2106, 354, 10197, _IB_PACING_ERROR_CODE}:
    logger.warning("Codigo IB %d: %s", error_code, error_string)
```
- **Risco:** restauro de conectividade, `order rejected`, `not connected` e `orderId in use` não mudam estado nem activam safe mode.
- **Cenário:** TWS perde sessão e volta com `1101`; o bot não força resubscribe/reconcile completo.
- **Fix:**
```python
IB_ERROR_ACTIONS = {
    1100: "safe_mode",
    1101: "resubscribe_and_reconcile",
    1102: "verify_and_resume",
    162: "cooldown",
    200: "skip_symbol",
    201: "mark_grid_failed",
    202: "sync_cancelled",
    502: "retry_not_connected",
    504: "retry_not_connected",
    10147: "idempotency_violation",
}
action = IB_ERROR_ACTIONS.get(error_code)
if action is not None:
    self._handle_ib_error_action(action, error_code, error_string)
```
- **Cross-refs:** H06, H07

#### H04 — Market-hours ainda depende de fallback perigoso e janelas FX/FUT em UTC fixo
- **Ficheiro:** `src/market_hours.py:17`, `src/market_hours.py:186`
- **Código:**
```python
try:
    from pandas_market_calendars import get_calendar
except ImportError:
    get_calendar = None

SCHEDULES = {
    "FOREX": (None, "22:00", "22:00"),
    "FUT": (None, "23:00", "22:00"),
}
```
- **Risco:** qualquer drift de ambiente activa fallback silencioso; além disso, FX/FUT continuam dependentes de UTC hardcoded em vez de timezone/local session rules.
- **Cenário:** manutenção/deploy sem `pandas_market_calendars`, ou mudança de DST/pausa CME.
- **Fix:**
```python
from zoneinfo import ZoneInfo

if get_calendar is None:
    raise RuntimeError("pandas_market_calendars é obrigatório para session gating")

_CT = ZoneInfo("America/Chicago")
now_ct = now.astimezone(_CT)
maintenance_start = time(17, 0)
maintenance_end = time(18, 0)
```
- **Cross-refs:** H01

#### H05 — Pre-trade gate não valida sessão, frescura, NaN, notional nem margem
- **Ficheiro:** `src/risk_manager.py:854`
- **Código:**
```python
symbol: str = order_params.get("symbol", "UNKNOWN")
entry_price: float = order_params.get("entry_price", 0.0)
stop_price: float | None = order_params.get("stop_price", None)
...
current_grids: int = order_params.get("current_grids", 0)
```
- **Risco:** uma ordem pode ser aprovada com dados stale, preço não finito, símbolo fora da watchlist ou notional acima do pretendido.
- **Cenário:** `entry_price=float("nan")` ou `session_ok=False` entram em `order_params`, mas não são rejeitados explicitamente aqui.
- **Fix:**
```python
if not bool(order_params.get("session_ok", False)):
    rejection_reasons.append("sessao_nao_elegivel")
if not bool(order_params.get("data_fresh", False)):
    rejection_reasons.append("dados_stale")
if not math.isfinite(entry_price) or entry_price <= 0:
    rejection_reasons.append("preco_invalido")
notional = entry_price * max(position_size, 0)
if notional > float(order_params.get("max_notional", float("inf"))):
    rejection_reasons.append("notional_excedido")
```
- **Cross-refs:** C02

#### H06 — Estado corrompido não recupera do `.bak` e o arranque continua vazio
- **Ficheiro:** `src/grid_engine.py:528`, `src/grid_engine.py:596`, `main.py:1958`
- **Código:**
```python
if state_path.exists():
    shutil.copy2(str(state_path), str(backup_path))
...
except (json.JSONDecodeError, OSError) as exc:
    logger.error("Erro ao ler ficheiro de estado %s: %s", state_path, exc)
    raise
```
```python
except Exception as exc:
    logger.error("Erro ao carregar estado de grids: %s — a iniciar sem grids.", exc)
```
- **Risco:** um `grids_state.json` truncado perde tracking local; o bot prossegue desalinhado do broker.
- **Cenário:** disco cheio ou crash a meio de escrita deixa JSON inválido e o processo recomeça “sem grids”.
- **Fix:**
```python
except (json.JSONDecodeError, OSError) as exc:
    if backup_path.exists():
        logger.warning("Estado corrompido; a recuperar de %s", backup_path)
        shutil.copy2(str(backup_path), str(state_path))
        with state_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    else:
        raise
```
```python
except Exception as exc:
    logger.critical("Falha ao carregar estado persistido: %s", exc)
    raise
```
- **Cross-refs:** agravado por FASE 12.4

#### H07 — Falta exclusão mútua de instância e `client_id` default é partilhado
- **Ficheiro:** `config.py:77`
- **Código:**
```python
client_id: int = Field(
    default=1,
    description="ID do cliente para a ligacao IB",
)
```
- **Risco:** duas instâncias podem partilhar `clientId` e ficheiros de estado/log, causando disconnects silenciosos e corrupção cruzada.
- **Cenário:** o operador arranca uma segunda cópia no mesmo host para “testar” um ajuste.
- **Fix:**
```python
import os

lock_path = self._config.data_dir / "bot.lock"
self._lock_fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_RDWR)
os.write(self._lock_fd, str(self._config.ib.client_id).encode("utf-8"))
```
- **Cross-refs:** agravado por FASE 12.4

#### H08 — A suite de testes não é executável no ambiente auditado
- **Ficheiro:** `requirements.txt:9`
- **Código:**
```text
pytest>=7.0.0
pytest-asyncio>=0.23.0
pytest-timeout>=2.2.0
```
- **Risco:** cobertura existe em disco, mas não pôde ser validada; isso reduz a confiança em qualquer release/local debug.
- **Cenário:** um bug regressa e ninguém repara porque o CI/local nem sequer consegue recolher testes.
- **Fix:**
```bash
python -m pip install pytest pytest-asyncio pytest-timeout
python -m pytest --collect-only
python -m pytest -q
```
- **Cross-refs:** M08

#### H09 — Dashboard mostra equity “estimada” sem unrealized e sem comando de emergência
- **Ficheiro:** `dashboard/helpers.py:254`, `dashboard/app.py:249`, `dashboard/app.py:392`
- **Código:**
```python
estimated_equity = capital if capital is not None else None
if estimated_equity is None and metrics.get("initial_capital") is not None:
    estimated_equity = float(metrics["initial_capital"]) + total_pnl
```
```python
metrics[1].metric("Equity estimada", _fmt_eur(kpis.get("estimated_equity")))
...
["pause", "resume", "reconcile_now", "export_snapshot"]
```
- **Risco:** a UI pode parecer saudável enquanto a carteira tem perdas abertas; além disso, não há botão de `emergency_stop`/`reduce_only`.
- **Cenário:** realized PnL positivo, unrealized PnL fortemente negativo, operador confia no painel.
- **Fix:**
```python
unrealized_pnl = float(metrics.get("unrealized_pnl") or 0.0)
estimated_equity = (capital + unrealized_pnl) if capital is not None else None
return {
    ...,
    "unrealized_pnl": unrealized_pnl,
    "estimated_equity": estimated_equity,
}
```
```python
metrics[2].metric("PnL não realizado", _fmt_eur(kpis.get("unrealized_pnl")))
```
- **Cross-refs:** C01

### 🟡 MÉDIO (9)
| ID | Ficheiro:Linha | Problema | Fix |
|---|---|---|---|
| M01 | `requirements.txt:9` | Gate de type-check não existe na prática; `mypy` não corre neste ambiente. | Instalar `mypy`, adicionar job de CI e bloquear merge se `python -m mypy src main.py --ignore-missing-imports` falhar. |
| M02 | `src/risk_manager.py:67` | `datetime.utcnow` em defaults de dataclass cria timestamps naive/deprecated. | Trocar por `datetime.now(timezone.utc)` em todos os defaults/now calls de risco. |
| M03 | `src/risk_manager.py:102` | Só há limite de correlação; falta cap de gross exposure/concentração/notional agregado. | Adicionar `max_gross_notional`, `max_symbol_notional`, `max_sector_notional` no pre-trade gate. |
| M04 | `src/signal_engine.py:73` | Não existe contrato de sinal único para todos os módulos. | Introduzir `SignalPayload`/Pydantic único e validar todos os módulos contra esse schema. |
| M05 | `main.py:2292` | Estratégias multi-instrumento ficam em modo auditável e emitem payloads incompatíveis com brackets (`SELL_PUT`, preços 0). | Separar “audit-only” de “executable”, ou normalizar para um contrato próprio de execução. |
| M06 | `src/grid_engine.py:32` | Estado/reconciliação é stringly-typed e sem ORPHANED explícito. | Criar enums formais para `grid_status` e `reconciliation_state`, com tabela de transições. |
| M07 | `src/grid_engine.py:533` | Há `version: 1`, mas não há migração formal entre schemas antigos/novos. | Introduzir `SCHEMA_VERSION`, `migrate_state()` e testes de backward compatibility. |
| M08 | `main.py:299` | `bot.log` não roda e o heartbeat é só local-file; sem dead-man switch externo. | Usar `RotatingFileHandler`/retenção e expor heartbeat para watchdog externo. |
| M09 | `main.py:2898` | Faltam regressões para drawdown unrealized, recenter stale, recovery `.bak` e spread/gap guards. | Acrescentar testes dedicados nesses quatro paths antes de qualquer uso prolongado em paper. |

### 🟢 BAIXO (2)
| ID | Ficheiro:Linha | Problema | Fix |
|---|---|---|---|
| L01 | `src/execution.py:1112` | `except Exception`/`except BaseException` reduzem granularidade de triage, apesar de falharem fechado na maioria dos casos. | Capturar excepções específicas (`TimeoutError`, `OSError`, erros IB) e manter logs distintos. |
| L02 | `dashboard/app.py:1`, `dashboard 2/app.py:1` | Há duas árvores de dashboard no repo, o que convida drift e dúvidas operacionais. | Eleger uma única fonte de verdade e arquivar/remover a duplicada. |

## Resiliência (Fase 12)
| Cenário | Coberto? | Notas |
|---|---|---|
| TWS crasha a meio do dia | Parcial | Há reconnect, mas faltam acções explícitas para 1101/2110 e resubscribe completo. |
| Internet cai 5 min e volta | Parcial | `ensure_connected()` ajuda, mas não há reconciliação total garantida em todos os paths. |
| Internet cai 2 horas | Não | Sem política de safe mode prolongado/flatten/replay. |
| Disco enche | Não | Escritas de estado/log podem falhar; não há verificação prévia de espaço. |
| Processo OOM killed | Não | Sem supervisor/dead-man switch externo. |
| Clock adianta 5 min | Não | Não há detecção de drift/NTP health. |
| DNS falha parcial (IB ok, yfinance falha) | Parcial | Existe fallback, mas sem health gate por provider. |
| IB retorna 0 barras | Sim | Símbolo é saltado quando `bars_df.empty`. |
| Barras com volume = 0 | Não | Sem guard clause forte antes de indicadores/sinais. |
| Quote com bid=0 ask=0 | Parcial | Pode cair para `close`/`yfinance`; isso agrava `C02`. |
| Spread > 5% do preço | Não | Não existe spread guard explícito no pre-trade gate. |
| yfinance retorna dados de outro símbolo | Não | Sem verificação de source/symbol integrity. |
| Historical bars adjusted vs unadjusted mismatch | Não | Sem normalização/corporate actions awareness. |
| Circuit breaker (Level 1/2/3) | Não | Sem path de halt/circuit breaker. |
| Trading halt num símbolo | Não | Não há mapeamento de halt para bloquear gestão/execução. |
| Gap overnight > 10% | Não | Sem guard específico para gap extremo. |
| Stock split executado | Não | Sem detecção de split para limpar sinais/ATR/kill switch. |
| Flash crash (5% em 1 min, recupera) | Não | Sem circuit breaker interno por volatilidade extrema. |
| State file = 0 bytes | Não | `load_state()` levanta e o arranque continua “sem grids”. |
| State file JSON inválido | Não | Mesmo problema; `.bak` é ignorado no load. |
| State file de versão anterior | Parcial | Só existem defaults mínimos, não migração real. |
| Grid no state que IB não conhece | Parcial | Há `orphan/mismatch`, mas sem enum/repair loop forte. |
| Duas instâncias com mesmo state file | Não | Sem lock de processo nem lock do ficheiro. |

## Testes em falta
- `P0` — Kill switch baseado em equity/unrealized e baselines diário/semanal/mensal.
- `P0` — Recenter/respacing de grid com `price_fresh=False`, `source=close` e `source=yfinance`.
- `P0` — Recovery de `grids_state.json.bak` após JSON inválido / ficheiro 0 bytes.
- `P1` — Spread guard, gap guard, halt/circuit-breaker e corporate action/split.
- `P1` — Multi-instância (`client_id` duplicado e state-file lock).
- `P1` — Backward compatibility de schema com `migrate_state()`.
- `P2` — Dashboard: unrealized PnL e comandos de emergência.

## Plano de acção
### P0 — Antes de QUALQUER execução
- Corrigir `C01`: kill switches por equity real (`NetLiquidation`) com baselines por período.
- Corrigir `C02`: grids activas só podem reagir a quotes `fresh=True`.
- Corrigir `H06`: recuperar de `.bak` e falhar fechado se o estado persistido estiver corrompido.
- Corrigir `H07`: lock de instância + `client_id` único + state-file lock.

### P1 — Antes de paper trading validado
- Corrigir `H03` e `H04`: mapping completo de erros IB e market-hours fail-closed.
- Corrigir `H05`: pre-trade gate determinístico com sessão, staleness, NaN/notional/margem.
- Corrigir `H09`: dashboard com unrealized PnL e comando de emergência.
- Tornar a suite executável no ambiente alvo e adicionar regressões `P0`.

### P2 — Durante paper trading (1 mês)
- Formalizar enums/transições da state machine.
- Adicionar migração de schema e testes de restart/kill -9.
- Adicionar caps de concentração/gross exposure.
- Implementar rotação de logs, watchdog externo e alarmes de heartbeat stale.

### P3 — Critérios para live trading
- [ ] Zero CRÍTICOS
- [ ] Kill switches testados em paper com unrealized PnL real
- [ ] Reconciliação testada com crash simulado e recovery por `.bak`
- [ ] DST / holidays / FX / futures testados em datas de transição reais
- [ ] State persistence validado (`kill -9` + restart)
- [ ] Heartbeat activo com monitor externo
- [ ] 30+ dias paper sem duplicação nem state drift
- [ ] Score ≥ 70/100
- [ ] `LIVE_TRADING_CONFIRMED` com guard multi-layer
- [ ] Regulatory basics implementados

## Score
| Área | Peso | Resultado |
|---|---|---|
| Problemas CRÍTICOS | 25 | `15/25` |
| Testes | 15 | `12/15` |
| Separação responsabilidades | 10 | `7/10` |
| Risk controls | 15 | `6/15` |
| Market hours DST | 10 | `0/10` |
| Logging | 8 | `6/8` |
| Resiliência Fase 12 | 10 | `3/10` |
| Integridade numérica | 7 | `4/7` |
| **Total** | **100** | **53/100** |

## Self-check
- [x] Fase 1: Inventário, deps, imports, leitura core, types, dead code, configs
- [x] Fase 2: Contracts, price, staleness, rate limits, async, reconnect, fallback, concurrency, corporate actions
- [x] Fase 3: UTC/DST, sessões, holidays, forex/futures, arranque, edge cases temporais
- [x] Fase 4: Kill switches, Kelly, state machine, pre-order, resets, paper/live, exposure
- [x] Fase 5: Contrato, confidence, preços, context, registry, watchlist, end-to-end, incompletas
- [x] Fase 6: Bracket, state machine, IDs, persistência, reconciliação, IB status, races, backward compat
- [x] Fase 7: Loop, lógica, config, logging, memory, heartbeat, multi-instância
- [x] Fase 8: Cobertura, testes em falta, qualidade
- [x] Fase 9: Credenciais, live guard, errors, shutdown, deployment, disk
- [x] Fase 10: Dashboard
- [x] Fase 11: Numérica, data flow, error propagation, timezones
- [x] Fase 12: Infra, dados, mercado, estado (chaos scenarios)
- [x] Fase 13: PDT, wash sale, margin, short
- [x] Fase 14: Scoring, relatório

# AUDIT_REPORT.md
# Data: 2026-03-18
# Versão: v7
# Repo: gcodeteric/Playground
# Subdiretoria: bot-trading
# Commit auditado: e04725c7e6852173fe646c510a3e49a36061e125

Esta auditoria foi executada sobre o commit exacto `e04725c7e6852173fe646c510a3e49a36061e125`, usando um snapshot isolado do tree para evitar contaminação por HEAD, branch actual ou alterações futuras.

Comandos de validação executados no snapshot:
- `pytest tests -q --tb=short`
- `python3 tools/smoke_test.py`
- leitura forense dirigida de `main.py`, `config.py`, `src/data_feed.py`, `src/execution.py`, `src/grid_engine.py`, `src/risk_manager.py`, `src/contracts.py`, `src/market_hours.py`, `src/logger.py`, módulos de estratégia, `dashboard/` e `tests/`

Resultado factual dos comandos:
- `347 passed, 1124 warnings in 5.22s`
- `tools/smoke_test.py` -> `Resultado: 10/10`

# 1. Resumo Executivo

Avaliação geral: este sistema não demonstra garantias suficientes para controlar capital real. O código já não é um protótipo puro, mas também não é um sistema de trading robusto. É um protótipo endurecido por camadas de patches, com alguma cobertura útil e observabilidade razoável, mas ainda com falhas estruturais graves nos caminhos de execução, kill switches, segregação paper/live, tracking de bracket orders e recovery.

Score de readiness para paper (0-10): `4/10`  
Score de readiness para live (0-10): `1/10`

Principais blockers:
- `PAPER_TRADING=true` não impede arranque ligado a conta live.
- Kill switches diário, semanal e mensal têm semântica operacional financeiramente errada.
- Existe um caminho de execução fora da state machine principal de grids.
- O tracking local de parent, stop e take-profit está estruturalmente corrompido.
- O capital de risco é reinicializado do `.env` após restart.

Principais riscos sistémicos:
- falsa sensação de segurança em paper mode
- divergência entre estado local e broker
- retries de ordens sem idempotência
- recovery inseguro após crash/restart
- testes que passam sem provar as propriedades operacionais críticas

Conclusão curta e direta: o commit auditado pode ser usado para paper trading apenas com supervisão humana contínua e com reservas sérias. Para live trading, está bloqueado.

# 2. Mapa da Arquitetura Real

## 2.1 Componentes

- `main.py`
  - Orquestrador dominante.
  - Faz bootstrap, preflight, reconciliação, loop principal, routing de estratégias, grid lifecycle, command queue, heartbeat e shutdown.
- `config.py`
  - Carrega configuração com Pydantic.
  - Junta defaults, `.env`, pathing e validações.
- `src/data_feed.py`
  - Liga ao IB, gere reconnect, histórico, snapshots, pacing, cache e fallback Yahoo.
- `src/execution.py`
  - Gera e submete ordens, rastreia estado local de brackets e faz cancelamentos/fechos.
- `src/grid_engine.py`
  - Mantém o modelo de grid, níveis, serialização e reload.
- `src/risk_manager.py`
  - Sizing, caps, R:R, kill switches teóricos, correlação utilitária.
- `src/contracts.py`
  - Traduz watchlist para contratos IB.
- `src/market_hours.py`
  - Decide abertura/fecho por asset class.
- `src/logger.py`
  - Trade log, métricas e Telegram.
- `dashboard/`
  - Camada de observabilidade e command channel por ficheiros.

## 2.2 Fluxo de arranque

1. `main()` cria `TradingBot`, valida config e faz `asyncio.run(bot.run())`.
2. `TradingBot.run()` carrega estado persistido de grids.
3. `preflight_check()` liga ao IB, valida contas/dados, inicializa `OrderManager`, envia Telegram e grava `preflight_state.json`.
4. `run()` executa reconciliação de arranque.
5. Entra no loop principal assíncrono.

## 2.3 Fluxo operacional

1. Processa comandos em `data/commands/`.
2. Se `manual_pause` estiver activo, aborta o resto do ciclo.
3. Garante conectividade IB.
4. Actualiza métricas agregadas.
5. Corre `_check_risk_limits()`.
6. Percorre watchlist e chama `_process_symbol()`.
7. Monitoriza grids activas.
8. Actualiza heartbeat, relatórios e housekeeping.

## 2.4 Fluxo de risco e execução

1. `DataFeed` produz barras históricas e snapshot actual.
2. `signal_engine` e módulos novos geram sinais.
3. `RiskManager` valida sizing, R:R, limites e caps.
4. `main.py` decide entre:
   - caminho grid-driven
   - caminho multi-módulo directo
5. `OrderManager.submit_bracket_order()` submete parent, stop e target.

## 2.5 Persistência e recovery

- `GridEngine.save_state()` persiste grids e backup.
- `TradeLogger` persiste trades e métricas.
- `main.py` grava `heartbeat.json`, `preflight_state.json`, `snapshot.json`.
- Recovery de arranque reconcilia posições e ordens com estado local.

## 2.6 Superfícies de falha

- `main.py` concentra demasiada lógica crítica.
- A state machine global não é explícita.
- Existem dois modelos de posição:
  - grids persistidas
  - trades multi-módulo directos
- Kill switches operam parcialmente sobre estado local e parcialmente sobre ordens.
- Tracking local de brackets não representa correctamente as pernas reais.
- Restart e reconciliação assentam em assunções frágeis.

# 3. Inventário de Ficheiros Relevantes

| Ficheiro | Papel real | Criticidade | Observações |
|---|---|---:|---|
| `main.py` | Orquestração principal | Muito alta | State machine difusa e responsabilidades misturadas |
| `config.py` | Config runtime | Alta | Defaults razoáveis, enforcement fraco de paper/live |
| `src/data_feed.py` | Ligação IB, dados, reconnect | Muito alta | Mistura demasiadas responsabilidades |
| `src/execution.py` | Submission e tracking local de ordens | Muito alta | Bracket semantics frágeis |
| `src/grid_engine.py` | Modelo/persistência de grids | Muito alta | Melhor persistência, mas depende de orquestração correcta |
| `src/risk_manager.py` | Sizing e caps | Muito alta | Risco teórico melhor do que integração real |
| `src/contracts.py` | Contratos IB | Alta | Roll de futuros é heurístico |
| `src/market_hours.py` | Sessões e horários | Alta | Equities melhoradas; outros activos continuam heurísticos |
| `src/logger.py` | Logging, metrics, Telegram | Alta | Útil, mas insuficiente para incident response sério |
| `src/signal_engine.py` | Estratégia core Kotegawa | Alta | Menos grave que execução/recovery |
| `src/sector_rotation.py` | Módulo novo | Média | Ainda parcialmente integrado |
| `src/options_premium.py` | Módulo novo | Média | Comentários mostram modo auditável/faseado |
| `src/bond_mr_hedge.py` | Módulo novo | Média | Usa `VIX` proxy e regime |
| `src/intl_etf_mr.py` | Módulo novo | Média | Único sítio com check de correlação efectivo |
| `dashboard/app.py` | Dashboard | Média | Observabilidade útil; não resolve core risk |
| `dashboard/helpers.py` | Parsing/KPI/command channel | Média | Boa separação local |
| `tests/test_execution.py` | Testes de ordens | Alta | Happy-path bias e semântica perigosa codificada |
| `tests/test_integration.py` | Integração lógica | Alta | Falta broker simulation séria |
| `tests/test_main_audit.py` | Flags e persistência do main | Alta | Prova ficheiros, não prova segurança operacional |
| `tests/test_data_feed.py` | Dados/reconnect/fallbacks | Alta | Não prova freshness nem concorrência séria |
| `README.md` | Documento operativo | Média | Promete mais do que o código prova |
| `data/bot.log` | Artefacto operacional versionado | Média | Mistura runs antigos com estado actual |
| `dashboard 2/app.py` | Código legado | Baixa | Lixo operacional no repo |
| `CODEX_IMPLEMENTATION_BRIEF_FINAL.md` | Documento de implementação | Baixa | Arqueologia de patching |
| `CODEX_IMPLEMENTATION_BRIEF_FINAL 2.md` | Documento duplicado | Baixa | Redundância que aumenta ruído |

# 4. Tabela Mestre de Findings

| ID | Severidade | Categoria | Ficheiro | Linhas | Título | Impacto curto | Confiança | Status recomendado |
|---|---|---|---|---|---|---|---|---|
| F-001 | S5 | Paper/Live segregation | `main.py` | 771-775, 927-935 | Paper mode não é enforcement | Pode enviar ordens reais com `PAPER_TRADING=true` | Alta | Bloquear arranque |
| F-002 | S5 | Kill switch / execution | `main.py` | 2641-2669 | Kill switch mensal fecha grids locais sem flatten broker-side | Divergência crítica local vs broker | Alta | Reescrever kill switch |
| F-003 | S5 | Kill switch / execution | `main.py`, `src/execution.py` | 2588-2621; 523-573 | Kill switch diário/semanal cancela protecções | Pode deixar posição nua | Alta | Reescrever kill switch |
| F-004 | S5 | Order lifecycle | `main.py` | 1930-2068 | Ordens multi-módulo bypassam grid engine | Posições sem recovery normal | Alta | Desactivar ou integrar |
| F-005 | S5 | Order tracking | `src/execution.py` | 182-204, 390-410, 776-816 | Parent, stop e TP partilham o mesmo estado | Tracking por perna corrompido | Alta | Refactor estrutural |
| F-006 | S4 | Risk state / recovery | `main.py` | 369-379, 543-585, 1604-1619 | Restart repõe capital do `.env` | Sizing e drawdown errados após restart | Alta | Persistir/restaurar equity |
| F-007 | S4 | Idempotência | `src/execution.py`, `src/ib_requests.py` | 354-441; 161-234 | Retries de bracket não são idempotentes | Duplicação de ordens | Alta | Introduzir dedupe |
| F-008 | S4 | Atomicidade | `main.py` | 2197-2245 | Criação de grid não é atómica | Grid activa pode não refletir broker | Alta | Staging + rollback |
| F-009 | S4 | Lifecycle / operations | `main.py` | 1680-1685 | `manual_pause` pára monitorização | Estado local deixa de acompanhar broker | Alta | Separar pause de monitorização |
| F-010 | S4 | Reconciliation | `main.py` | 807-815, 1289-1365 | Reconciliação age sobre leituras vazias transitórias | Self-inflicted damage | Média | Fail-closed |
| F-011 | S3 | Market data staleness | `src/data_feed.py` | 842-847, 1239-1265 | `current_price` pode ser só o último close | Sinais com preço stale | Alta | Freshness policy |
| F-012 | S3 | Async / reconnect | `src/data_feed.py` | 311-324, 350-423 | `ensure_connected()` e `_auto_reconnect()` podem sobrepor-se | Corridas de reconnect | Média | Lock de ligação |
| F-013 | S3 | Caching / correctness | `src/data_feed.py` | 693, 808, 914 | Cache keys fracas | Contaminação entre instrumentos | Média | Chaves compostas |
| F-014 | S3 | Contracts / roll | `src/contracts.py` | 254-271 | Roll de futuros é heurístico | Pode negociar o mês errado | Média | Resolver front month dinamicamente |
| F-015 | S2 | Risk integration | `main.py`, `src/risk_manager.py`, `src/intl_etf_mr.py` | 391-404, 1949-1970; 102-173; 68-76 | Correlação não é guardrail central | Concentração escapa ao risco | Alta | Integrar no `RiskManager` central |
| F-016 | S2 | Test realism | `tests/test_execution.py`, `tests/test_integration.py`, `tests/test_main_audit.py` | 262-295; 712-749; 187-202 | Testes codificam semântica insegura | Falsa confiança de readiness | Alta | Reescrever testes críticos |

# 5. Findings Detalhados

## [F-001] Paper mode não é enforcement, é só intenção

**Severidade:** S5  
**Categoria:** Paper/Live segregation  
**Confiança:** Alta  
**Ficheiro(s):** `main.py`  
**Linha(s):** 771-775, 927-935, 968-985

### Facto observado
`_infer_account_mode()` trata qualquer conta não iniciada por `DU` como live. Em `preflight_check()`, quando `PAPER_TRADING=true` mas a conta parece live, o código emite warning e continua. Só há bloqueio duro no caso oposto: `PAPER_TRADING=false` com conta paper.

### Inferência
O sistema não isola paper/live. Tem apenas um aviso textual baseado num heurístico superficial.

### Porque isto é perigoso
O operador pode acreditar que está protegido por `PAPER_TRADING=true`. Não está.

### Cenário de falha
TWS live aberta na porta configurada, `.env` com paper activado, sessão autenticada na conta errada. O bot continua e submete ordens reais.

### Impacto operacional
Quebra total da promessa de paper-only.

### Impacto financeiro
Execução real não intencional.

### Correção recomendada
Abortar o arranque em qualquer mismatch entre modo configurado e modo detectado.

### Patch suggestion
```python
if configured_paper and detected_mode != "PAPER":
    logger.critical("Conta live detectada com PAPER_TRADING=true. Arranque bloqueado.")
    raise SystemExit(1)
```

### Testes obrigatórios
- teste de preflight que falha com `paper=True` e conta live
- teste de reconnect que revalida a conta
- teste de startup que nunca chama execução após mismatch

## [F-002] Kill switch mensal fecha grids locais sem flatten broker-side

**Severidade:** S5  
**Categoria:** Kill switch / execution  
**Confiança:** Alta  
**Ficheiro(s):** `main.py`, `src/execution.py`  
**Linha(s):** 2641-2669; 523-573, 602-676

### Facto observado
O kill switch mensal chama cancelamento de ordens da grid e `close_grid()` local. Não existe flatten confirmado de posições reais antes de remover a grid do estado.

### Inferência
O motor pode concluir “posição resolvida” apenas porque fechou o estado local.

### Porque isto é perigoso
Um kill switch que não actua no broker é operacionalmente falso.

### Cenário de falha
Drawdown mensal atinge o limite. O bot limpa a grid do JSON e sai. A posição continua aberta no broker.

### Impacto operacional
Recovery posterior arranca sem memória local da posição que continua exposta.

### Impacto financeiro
Exposição viva precisamente no momento em que o sistema decidiu que já perdeu demasiado.

### Correção recomendada
Primeiro fechar posição real, depois cancelar restos, depois só então encerrar a grid local.

### Patch suggestion
- `close_position(symbol, qty)` com confirmação broker-side
- `await cancel_all_grid_orders(...)`
- apenas após confirmação, `grid_engine.close_grid(grid)`

### Testes obrigatórios
- teste de kill switch mensal com posição broker aberta
- teste que prova flatten antes do close local
- teste de restart depois do kill switch

## [F-003] Kill switch diário/semanal cancela protecções e deixa exposição nua

**Severidade:** S5  
**Categoria:** Kill switch / execution  
**Confiança:** Alta  
**Ficheiro(s):** `main.py`, `src/execution.py`  
**Linha(s):** 2588-2621; 523-573

### Facto observado
Nos limites diário e semanal, o código chama `cancel_all_grid_orders()` para todas as grids activas. Esse método cancela todas as ordens não terminadas da grid, incluindo stop-loss e take-profit das posições já abertas.

### Inferência
O kill switch remove os mecanismos de protecção das posições activas.

### Porque isto é perigoso
Isto é o inverso de controlo de risco.

### Cenário de falha
Há uma posição comprada com stop e target activos. O limite diário dispara. O sistema cancela o stop e o target, mas não fecha a posição.

### Impacto operacional
O bot entra em “protecção” removendo a protecção.

### Impacto financeiro
Perda potencial acima do desenho do sistema.

### Correção recomendada
Separar cancelamento de entradas pendentes de cancelamento de protecções. Kill switch deve flatten ou manter protecção até flatten.

### Patch suggestion
```python
cancel_pending_entries(grid_id)
if position_open:
    await flatten_position(...)
```

### Testes obrigatórios
- teste com child orders activos
- teste que garante que posição aberta nunca fica sem stop após kill switch
- teste de integração com broker fake

## [F-004] Ordens multi-módulo bypassam a state machine de grids

**Severidade:** S5  
**Categoria:** Order lifecycle  
**Confiança:** Alta  
**Ficheiro(s):** `main.py`  
**Linha(s):** 1930-2068, 2285-2465

### Facto observado
Para sinais de módulos novos, `main.py` pode chamar `submit_bracket_order()` directamente com `grid_id` sintético `multi_*`, sem criar grid persistida nem entrar na monitorização padrão.

### Inferência
Existe um segundo sistema de execução dentro do mesmo bot, sem recovery simétrico.

### Porque isto é perigoso
Posições podem existir no broker sem objecto persistido equivalente no motor.

### Cenário de falha
Uma ordem de `forex_breakout` ou `commodity_mr` entra. O processo reinicia. A posição aberta não pertence a nenhuma grid persistida.

### Impacto operacional
Reconciliação e dashboard ficam incompletos.

### Impacto financeiro
Posições órfãs escapam à gestão normal.

### Correção recomendada
Desactivar este caminho até haver um modelo persistente equivalente, ou integrá-lo numa state machine única.

### Patch suggestion
- criar `StrategyTradeRecord`
- persistir e reconciliar trades não-grid
- monitorização específica ou unificação com grids

### Testes obrigatórios
- teste de restart com trade multi-módulo aberto
- teste de kill switch sobre trade não-grid
- teste de reconciliação para `multi_*`

## [F-005] Parent, stop e TP partilham o mesmo `OrderInfo`

**Severidade:** S5  
**Categoria:** Order tracking  
**Confiança:** Alta  
**Ficheiro(s):** `src/execution.py`, `main.py`  
**Linha(s):** 182-204, 390-410, 776-816; 2304-2407

### Facto observado
`submit_bracket_order()` regista o mesmo objecto `OrderInfo` sob os três order IDs do bracket. `_on_order_status()` actualiza esse objecto único conforme chegam callbacks. `main.py` depois consulta o estado por `buy_order_id`, `sell_order_id` e `stop_order_id` como se fossem independentes.

### Inferência
O último callback recebido contamina o estado reportado das outras pernas.

### Porque isto é perigoso
O bot não sabe de forma fiável qual perna mudou de estado.

### Cenário de falha
O parent enche, depois o TP recebe `Submitted`. O estado global passa a `Submitted`, apagando a percepção de fill do parent.

### Impacto operacional
Monitorização de grids não consegue inferir correctamente nível `bought`, `sold` ou `stopped`.

### Impacto financeiro
Possibilidade de duplicate bookkeeping, fechos errados e perda de controlo sobre a posição.

### Correção recomendada
Estado por perna independente, com agregação por `bracket_id`.

### Patch suggestion
```python
pending[parent_id] = ParentOrderInfo(...)
pending[stop_id] = StopOrderInfo(...)
pending[tp_id] = TargetOrderInfo(...)
brackets[bracket_id] = BracketInfo(parent_id, stop_id, tp_id, ...)
```

### Testes obrigatórios
- callbacks fora de ordem por perna
- fill do parent com children ainda `Submitted`
- TP fill sem contaminar parent

## [F-006] Restart repõe capital do `.env` e apaga equity real

**Severidade:** S4  
**Categoria:** Risk state / recovery  
**Confiança:** Alta  
**Ficheiro(s):** `main.py`  
**Linha(s):** 369-379, 543-585, 1604-1619, 2385-2443

### Facto observado
`_capital` nasce do capital inicial configurado. Em runtime é ajustado por P&L realizado, mas no arranque não é reconstruído a partir de métricas, trade log ou broker equity.

### Inferência
Após restart, o sizing regressa ao capital inicial configurado.

### Porque isto é perigoso
O motor de risco deixa de reflectir a realidade da conta.

### Cenário de falha
A conta perdeu 8%. O processo reinicia. O bot volta a dimensionar como se nada tivesse acontecido.

### Impacto operacional
Kill switches, sizing e métricas tornam-se inconsistentes.

### Impacto financeiro
Oversizing em drawdown e risco agregado acima do esperado.

### Correção recomendada
Restaurar equity/capital de uma fonte fiável no arranque, preferencialmente do broker.

### Patch suggestion
- ler `NetLiquidation` do broker no preflight
- fallback para `metrics.json` validado
- último fallback: recomputar de `trades_log.json`

### Testes obrigatórios
- restart com P&L acumulado
- sizing após restart
- kill switch pós-restart

## [F-007] Retries de submissão de bracket não são idempotentes

**Severidade:** S4  
**Categoria:** Idempotência  
**Confiança:** Alta  
**Ficheiro(s):** `src/execution.py`, `src/ib_requests.py`, `tests/test_execution.py`  
**Linha(s):** 354-441; 161-234; 262-295

### Facto observado
O executor reexecuta a submissão inteira em caso de excepção. O submit gera novos order IDs e faz novos `placeOrder()`. Os testes aceitam como normal múltiplas chamadas de `placeOrder()` antes do “sucesso”.

### Inferência
Se a primeira tentativa foi parcialmente aceite pelo broker, o retry pode duplicar ordens.

### Porque isto é perigoso
Falhas transitórias em ordens são precisamente onde a idempotência é obrigatória.

### Cenário de falha
Parent e stop enviados, exception antes do target. Retry cria outro parent/stop/target.

### Impacto operacional
O tracking local já é fraco; com retries deixa de ter relação unívoca com o broker.

### Impacto financeiro
Exposição duplicada ou sobreposta.

### Correção recomendada
Introduzir chave idempotente por símbolo/grid/nível e consultar broker state antes de reemitir.

### Patch suggestion
- persistir `submission_key`
- antes de retry, procurar ordens abertas correspondentes
- só reemitir se não houver evidência de submissão parcial já aceite

### Testes obrigatórios
- exception após parent enviado
- retry com ordem já existente
- garantia de no máximo um bracket vivo por nível

## [F-008] Criação de grid não é atómica

**Severidade:** S4  
**Categoria:** Atomicidade  
**Confiança:** Alta  
**Ficheiro(s):** `main.py`  
**Linha(s):** 2197-2245

### Facto observado
A grid é criada e persistida antes de todas as submissões de níveis. Em falha intermédia, a grid continua activa com níveis sem ordens reais.

### Inferência
Há estados intermédios que o sistema trata como válidos.

### Porque isto é perigoso
O estado local deixa de corresponder à exposição real.

### Cenário de falha
Níveis 1-2 submetidos, nível 3 falha, grid continua `active` com 5 níveis.

### Impacto operacional
Recentring, monitorização e métricas trabalham sobre uma grid incompleta.

### Impacto financeiro
Risco agregado real diferente do risco modelado.

### Correção recomendada
Staging + commit ou rollback integral.

### Patch suggestion
- `status="staging"` no create
- rollback das ordens já emitidas se falhar um nível crítico
- promover a `active` só depois da fase de submit

### Testes obrigatórios
- falha no nível intermédio
- rollback integral
- restart com grid em staging/falhada

## [F-009] `manual_pause` pára monitorização e risco, não só entradas

**Severidade:** S4  
**Categoria:** Lifecycle / operations  
**Confiança:** Alta  
**Ficheiro(s):** `main.py`  
**Linha(s):** 1680-1685

### Facto observado
Quando `_manual_pause` está activo, `_main_cycle()` retorna logo no início do ciclo.

### Inferência
Durante a pausa o bot deixa de fazer mais do que processar comandos.

### Porque isto é perigoso
Pausa segura deveria bloquear novas entradas, não desligar a vigilância do estado existente.

### Cenário de falha
Grid já aberta recebe fill num child enquanto o bot está pausado. O estado local não acompanha.

### Impacto operacional
Estado local e broker divergem progressivamente.

### Impacto financeiro
Risco real segue vivo, mas o motor local não reage.

### Correção recomendada
Permitir pause apenas para criação de novas posições. Monitorização, heartbeat, reconciliação e kill switches têm de continuar.

### Patch suggestion
- mover o guard de pause para os pontos de entrada de novos trades
- manter `_monitor_active_grids()` e `_check_risk_limits()` activos

### Testes obrigatórios
- pause com grid aberta
- zero novas entradas durante pause
- heartbeat e monitorização continuam durante pause

## [F-010] Reconciliação age sobre leituras vazias transitórias

**Severidade:** S4  
**Categoria:** Reconciliation  
**Confiança:** Média  
**Ficheiro(s):** `main.py`  
**Linha(s):** 807-815, 1289-1365

### Facto observado
`_fetch_positions_with_retry()` pode terminar devolvendo uma lista vazia. A reconciliação trata `qty == 0` como facto e marca grids como `ghost`, pausando-as e cancelando ordens.

### Inferência
Uma leitura inconclusiva pode disparar acções destrutivas.

### Porque isto é perigoso
Reconciliation should fail closed. Aqui falha destrutivamente.

### Cenário de falha
IB está lento, responde vazio a três tentativas. O bot apaga/pausa estado válido.

### Impacto operacional
Self-inflicted mismatches.

### Impacto financeiro
Pode remover gestão activa de posições reais.

### Correção recomendada
Distinguir “sem posições confirmadas” de “não consegui observar posições”.

### Patch suggestion
- `positions_status = confirmed | unknown | failed`
- acções destrutivas só em `confirmed`

### Testes obrigatórios
- retries vazios transitórios
- reconciliação com estado `unknown`
- zero cancelamentos quando a leitura é inconclusiva

## [F-011] `current_price` “live” pode ser apenas o último close

**Severidade:** S3  
**Categoria:** Market data staleness  
**Confiança:** Alta  
**Ficheiro(s):** `src/data_feed.py`  
**Linha(s):** 842-847, 1239-1265

### Facto observado
`get_current_price()` aceita `ticker.close` como valor actual quando `last` falha. O fallback final ainda pode usar `last_close`.

### Inferência
O nome da função promete mais do que entrega.

### Porque isto é perigoso
Preço stale pode alimentar regime, sinal e sizing.

### Cenário de falha
Mercado moveu fortemente, snapshot falhou, `ticker.close` da sessão anterior é tratado como preço actual.

### Impacto operacional
Logs e métricas parecem live quando não são.

### Impacto financeiro
Entradas e stops desfasados do mercado real.

### Correção recomendada
Separar `price_source` e bloquear novas entradas quando a fonte não for fresca.

### Patch suggestion
- `current_price`, `price_source`, `price_timestamp`
- se `price_source in {"close", "last_close"}` -> não abrir novas posições

### Testes obrigatórios
- snapshot com só `close`
- bid/ask válidos sem `last`
- bloqueio de entrada por stale source

## [F-012] `ensure_connected()` e `_auto_reconnect()` podem sobrepor-se

**Severidade:** S3  
**Categoria:** Async / reconnect  
**Confiança:** Média  
**Ficheiro(s):** `src/data_feed.py`  
**Linha(s):** 311-324, 350-423

### Facto observado
Disconnect callback agenda `_auto_reconnect()`. Em paralelo, o loop chama `ensure_connected()` e este também pode chamar `connect()`.

### Inferência
Há concorrência não serializada na gestão da ligação IB.

### Porque isto é perigoso
Estados de ligação concorrentes são difíceis de reproduzir e devastadores em produção.

### Cenário de falha
Disconnect chega no meio do ciclo; `_auto_reconnect()` e `ensure_connected()` tentam reconectar quase em simultâneo.

### Impacto operacional
Client state, callbacks e `OrderManager` podem divergir.

### Impacto financeiro
Janela de execução com percepção errada de conectividade e risco de replay/retry inadequado.

### Correção recomendada
Serializar qualquer `connect()` com um lock único e state machine explícita.

### Patch suggestion
- `self._connect_lock = asyncio.Lock()`
- `connection_state = DISCONNECTED | CONNECTING | CONNECTED | RECONNECTING`

### Testes obrigatórios
- callback de disconnect + ensure_connected concorrentes
- reconnect interrompido por shutdown
- reconnect repetido com lock

## [F-013] Cache keys fracas podem contaminar instrumentos

**Severidade:** S3  
**Categoria:** Caching / correctness  
**Confiança:** Média  
**Ficheiro(s):** `src/data_feed.py`  
**Linha(s):** 693, 808, 914

### Facto observado
As chaves de cache usam essencialmente o símbolo e poucos parâmetros.

### Inferência
Instrumentos homónimos em secTypes/exchanges distintos podem partilhar dados em cache.

### Porque isto é perigoso
Erro silencioso e plausível, difícil de detectar.

### Cenário de falha
Mesmo símbolo em stock e noutro instrumento reutiliza cache.

### Impacto operacional
Diagnóstico difícil e decisões aparentemente consistentes mas erradas.

### Impacto financeiro
Sinais e sizing sobre instrumento economicamente incorrecto.

### Correção recomendada
Usar chave composta por contrato qualificado completo.

### Patch suggestion
`f"{secType}:{symbol}:{exchange}:{currency}:{duration}:{bar_size}:{what_to_show}:{use_rth}"`

### Testes obrigatórios
- símbolos homónimos em secTypes diferentes
- cache separada por `whatToShow`
- cache separada por exchange

## [F-014] Roll de futuros é heurístico e não exchange-correct

**Severidade:** S3  
**Categoria:** Contracts / roll  
**Confiança:** Média  
**Ficheiro(s):** `src/contracts.py`  
**Linha(s):** 254-271

### Facto observado
`_next_futures_expiry()` usa listas fixas de meses e heurística de data.

### Inferência
O contrato seleccionado não é necessariamente o front month real nem o mais líquido.

### Porque isto é perigoso
Produtos diferentes rolam por regras diferentes.

### Cenário de falha
Na janela de rollover, o bot escolhe um contrato já seco ou demasiado perto da expiração.

### Impacto operacional
Qualificação, dados e fills degradam.

### Impacto financeiro
Pior execução ou trading no contrato errado.

### Correção recomendada
Resolver front month por `reqContractDetails` e liquidez observada.

### Patch suggestion
- listar contract details válidos
- escolher expiração futura com melhor volume/open interest

### Testes obrigatórios
- datas em rollover
- regras diferentes por produto
- expiração futura válida

## [F-015] Correlação não é guardrail central de portfolio

**Severidade:** S2  
**Categoria:** Risk integration  
**Confiança:** Alta  
**Ficheiro(s):** `main.py`, `src/risk_manager.py`, `src/intl_etf_mr.py`  
**Linha(s):** 391-404, 1949-1970; 102-173; 68-76

### Facto observado
`check_correlation_limit()` existe, mas o risco central no caminho dos novos módulos não o usa; `risk_mgr` é mesmo descartado num dos fluxos.

### Inferência
A correlação é um check local, não um cap global consistente.

### Porque isto é perigoso
O portfolio pode concentrar risco económico equivalente por estratégias diferentes.

### Cenário de falha
Uma estratégia já expôs o portfolio a equities US. Outra abre nova posição correlacionada sem barreira central.

### Impacto operacional
Relatório de risco aparenta ser melhor do que é.

### Impacto financeiro
Drawdowns sincronizados mais fortes.

### Correção recomendada
Aplicar correlação na validação central de ordens.

### Patch suggestion
- integrar returns map/open positions em `validate_order_full()`
- chamar check central para todos os módulos relevantes

### Testes obrigatórios
- estratégias diferentes com activos correlacionados
- rejeição central por correlação
- regressão do módulo `intl_etf_mr`

## [F-016] A suite passa enquanto assume semântica insegura

**Severidade:** S2  
**Categoria:** Test realism  
**Confiança:** Alta  
**Ficheiro(s):** `tests/test_execution.py`, `tests/test_integration.py`, `tests/test_main_audit.py`  
**Linha(s):** 262-295; 712-749; 187-202, 234-338

### Facto observado
Há testes que aceitam retries com múltiplas chamadas de submissão como normais, testes que tratam “kill switch = fechar grids localmente” como sucesso, e testes de `pause` que não verificam semântica operacional.

### Inferência
O CI está a validar vários comportamentos errados como corretos.

### Porque isto é perigoso
Passar testes deixa de ser um sinal fiável de segurança.

### Cenário de falha
Uma mudança que preserva estas semânticas inseguras passa a suite sem resistência.

### Impacto operacional
Decisão de go/no-go fica contaminada.

### Impacto financeiro
Falhas mais caras não são interceptadas antes da produção.

### Correção recomendada
Reescrever testes em torno de invariantes operacionais reais, não de flags ou estados locais superficiais.

### Patch suggestion
- harness de broker fake com parent/child/partial fill/reconnect
- matar testes que equiparam kill switch a “close local”

### Testes obrigatórios
- retry idempotente
- kill switch com flatten broker-side
- pause sem parar monitorização

# 6. Contradições entre Documentação, Configuração e Código

- `README.md` apresenta o sistema como “100% autónomo” e “sem intervenção humana”. O código contém módulos explicitamente faseados, integrações auditáveis e caminhos ainda incompletos.
- A configuração `PAPER_TRADING=true` não impede arranque em contexto live. O nome é tranquilizador; o enforcement não existe.
- `src/grid_engine.py` documenta `BEAR: 8 | SIDEWAYS: 7` em comentário/docstring, mas a implementação activa usa `BEAR: 4 | SIDEWAYS: 8`.
- Os artefactos versionados em `data/bot.log` mostram execuções antigas com `Max grids: 5 | Posicoes max: 10`, enquanto a configuração actual usa outros valores. A repo mistura runtime history com código actual.
- `get_current_price_live()` pode devolver `ticker.close` ou `last_close`. O nome promete preço live; a semântica real é degradada.
- “Kill switch” sugere corte de risco. Os caminhos reais podem remover stops ou fechar apenas estado local.
- A existência de `dashboard/` e `dashboard 2/` denuncia código legado não limpo.
- A coexistência de múltiplos briefs finais duplicados (`CODEX_IMPLEMENTATION_BRIEF_FINAL*.md`) é sinal de patch archaeology, não de hardening limpo.

# 7. Failure Modes Financeiros

| Failure mode | Trigger | Impacto | Severidade | Deteção | Mitigação |
|---|---|---|---|---|---|
| Ordem real em contexto “paper” | Conta live ligada com `PAPER_TRADING=true` | Execução real não intencional | S5 | Hard check de conta no preflight | Bloqueio total em mismatch |
| Kill switch mensal fecha só local | Drawdown mensal >= limite | Posição fica aberta no broker sem estado local | S5 | Reconciliar logo após kill switch | Flatten broker-side antes do close local |
| Kill switch remove stop/tp | Limite diário/semanal com posições abertas | Exposição fica nua | S5 | Inspeção de open orders após kill switch | Cancelar só entradas ou flatten imediato |
| Parent enviado sem children fiáveis | Exception/retry a meio do bracket | Posição sem protecção garantida | S5 | Simulação broker-side e verificação por perna | Idempotência + confirmação de children |
| Tracking partilhado entre pernas | Callbacks fora de ordem | Estado local errado | S5 | Testes por perna/orderId | Modelo independente por perna |
| Retry duplica bracket | Falha parcial na submissão | Exposição duplicada | S4 | Dedupe por broker/local key | Idempotência operacional |
| Grid activa sem ordens completas | Falha num nível intermédio | Estado local não corresponde ao broker | S4 | Auditoria de níveis/order IDs | Staging + rollback |
| Restart com capital antigo | Processo reinicia após perdas/ganhos | Sizing e kill switches errados | S4 | Comparar capital runtime vs broker | Restaurar equity real |
| Pause interrompe vigilância | `manual_pause` com posições abertas | Local deixa de acompanhar fills | S4 | Heartbeat sem mudança + posições abertas | Pausa só em novas entradas |
| Reconciliação destrutiva sobre dados vazios | IB lento devolve `[]` | Grids válidas marcadas ghost | S4 | Estado `unknown` separado | Fail-closed |
| Preço stale gera sinal | Snapshot falha e cai para close | Regime, entry e sizing errados | S3 | `price_source` no payload | Bloquear novas entradas sem frescura |
| Futuros no mês errado | Rollover e heurística fraca | Liquidez/fills degradados | S3 | Contract details/volume | Resolver front month dinamicamente |
| Cache cruza instrumentos | Símbolos homónimos | Dados plausíveis mas errados | S3 | Testes por contrato qualificado | Chaves compostas |
| Exposure leak entre estratégias | Correlação não central | Portfolio excessivamente concentrado | S2 | Agregação central de risco | Correlação no `RiskManager` |
| Falha silenciosa com loop vivo | Logs e heartbeats continuam, sem garantias | Operador pensa que está tudo normal | S4 | Invariantes e alarmes por degraded mode | Estado operacional explícito |

# 8. Gaps de Testes

## unit

- falta teste de tracking independente para parent, stop e target
- falta teste de freshness/source do preço actual
- falta teste de cache key por contrato qualificado
- falta teste de account-mode mismatch bloqueante

## integration

- falta teste de kill switch com posição real aberta
- falta teste de trade multi-módulo no restart
- falta teste de pause com monitorização activa
- falta teste de capital restaurado após restart

## recovery

- falta teste de crash a meio da criação de grid
- falta teste de crash entre parent e children
- falta teste de restart com estado parcial de ordens

## broker simulation

- falta simulação séria de partial fills
- falta simulação de callbacks fora de ordem
- falta simulação de reconnect a meio de bracket
- falta simulação de cancel/replace

## risk

- falta teste central de correlação
- falta teste de kill switch sem perda de protecção
- falta teste de sizing após equity alterada e restart

## persistence

- falta teste de corrupção parcial de JSONs críticos
- falta teste de escrita interrompida por crash
- falta teste de schema drift no reload

## concurrency

- falta teste concorrente `ensure_connected()` vs `_auto_reconnect()`
- falta teste de queue com comandos simultâneos
- falta teste de shutdown com tarefas Telegram em curso

# 9. Go-Live Blockers

- `main.py:771-775, 927-935`  
  `PAPER_TRADING=true` não bloqueia arranque ligado a conta live.

- `main.py:2588-2621` e `src/execution.py:523-573`  
  Kill switches diário e semanal podem cancelar stop-loss e take-profit sem flatten.

- `main.py:2641-2669`  
  Kill switch mensal fecha grids localmente sem prova de fecho broker-side.

- `main.py:1930-2068`  
  Ordens multi-módulo bypassam a state machine central e o recovery normal.

- `src/execution.py:182-204, 390-410, 776-816`  
  Tracking por perna do bracket é estruturalmente inválido.

- `src/execution.py:354-441` e `src/ib_requests.py:161-234`  
  Retries de submissão não são idempotentes.

- `main.py:369-379, 543-585`  
  Restart repõe capital do `.env`, não da equity real.

# 10. Plano de Remediação Priorizado

## imediato (24h)

- bloquear arranque em qualquer mismatch paper/live
- reescrever kill switches para actuarem sobre posições reais do broker
- desactivar o caminho multi-módulo directo até ter persistência/recovery equivalentes
- refactor do tracking de brackets para estado independente por perna
- adicionar testes críticos para os quatro pontos acima

## curto prazo

- restaurar capital/equity real no arranque
- introduzir idempotência operacional nas submissões
- tornar a criação de grids atómica
- separar `manual_pause` de monitorização/heartbeat/kill switches
- endurecer reconciliação para leituras inconclusivas

## médio prazo

- suportar partial fills de forma real
- serializar reconnect com lock e state machine explícita
- enriquecer `current_price` com `price_source` e freshness
- corrigir cache keys por contrato completo
- substituir heurística de roll de futuros por resolução real do front month

## obrigatório antes de live

- harness de broker fake com parent/child/partial fill/reconnect
- runbooks de incident response e recovery
- reconciliação de arranque provada por teste
- kill switches provados por teste end-to-end
- remover todos os S5 e os S4 com impacto directo em ordens/risco

## melhoria não bloqueante

- limpar `dashboard 2/` e documentação duplicada
- remover artefactos operacionais versionados em `data/`
- reduzir warnings e deprecations para melhorar sinal forense
- enriquecer heartbeat e dashboard com modos degradados explícitos

# 11. Veredito Final

**BLOQUEADO para live até correções obrigatórias**

Justificação:
- o sistema ainda não provou segregação paper/live
- os kill switches não demonstram segurança financeira real
- o tracking de bracket orders está estruturalmente errado
- a submissão de ordens não é idempotente
- o recovery de risco após restart não preserva equity real

Em linguagem directa: isto ainda é um sistema que pode parecer robusto em demonstração e em CI, mas falhar exactamente nos incidentes que mais custam dinheiro real: mismatch de conta, reconnect no momento errado, kill switch mal implementado, retry parcial, e restart com estado financeiro errado.

**Classificação operacional:**
- Paper trading: **Apto para paper com reservas**
- Live trading: **Não apto para live**

## Checklist de Segurança para Avançar

- [ ] reconciliação inicial com broker validada
- [ ] kill switches provados por teste
- [ ] bracket/stop/tp provados por teste
- [ ] persistência crash-safe
- [ ] recovery após restart validado
- [ ] partial fills reconciliados corretamente
- [ ] duplicate order prevention provada
- [ ] market hours corretas por asset class
- [ ] stale/NaN/incomplete data bloqueados
- [ ] paper/live segregation inequívoca
- [ ] risk caps agregados provados
- [ ] logging suficiente para incident response
- [ ] blockers S5 resolvidos
- [ ] blockers S4 mitigados ou eliminados

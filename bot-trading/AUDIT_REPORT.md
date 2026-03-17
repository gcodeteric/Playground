# AUDIT_REPORT.md
# Data: 2026-03-17
# Versão: v6

## SCORE GERAL: 84/100

## RESUMO EXECUTIVO
- Baseline técnico: `320 passed`, `0 failed`, `0 errors`, `10/10` smoke tests, imports OK
- Estado geral: código está estável em testes, mas ainda há falhas de produção que os testes actuais não cobrem
- Bloqueios reais para operação autónoma:
  - sinais e regimes usam o último fecho diário como `current_price`, não o preço actual
  - kill switches semanal/mensal estão incorrectamente implementados no `main.py`
  - `market_hours.py` usa horas UTC fixas e ignora DST/calendários de sessão reais
  - fallback `yfinance` bloqueia o event loop e a camada histórica continua a bater no IB mesmo quando a reconexão falha
- Veredicto:
  - Paper trading supervisionado: ✅ possível
  - Paper trading não supervisionado: ❌ ainda não

## SECÇÃO 1 — Escopo e baseline

### Comandos executados
- `pytest -q --timeout=30 --tb=short`
- `python3 tools/smoke_test.py`
- `python3 -m py_compile main.py config.py src/*.py dashboard/app.py tools/*.py tests/*.py`
- leitura dirigida de `main.py`, `src/data_feed.py`, `src/contracts.py`, `src/logger.py`, `src/market_hours.py`, `dashboard/app.py`, `src/ib_requests.py`, `src/intl_etf_mr.py`, `src/bond_mr_hedge.py`, `src/options_premium.py`

### Resultado base
| Check | Resultado |
|---|---|
| `pytest` completo | ✅ `320 passed, 1124 warnings in 4.31s` |
| Smoke tests | ✅ `10/10` |
| `py_compile` | ✅ sem erros |
| Imports críticos | ✅ todos resolvem |

## SECÇÃO 2 — Resultados automáticos

### Imports
Todos os imports auditados resolveram:
- `src.data_feed`
- `src.execution`
- `src.contracts`
- `src.signal_engine`
- `src.risk_manager`
- `src.grid_engine`
- `src.sector_rotation`
- `src.gap_fade`
- `src.forex_mr`
- `src.forex_breakout`
- `src.futures_mr`
- `src.futures_trend`
- `src.intl_etf_mr`
- `src.commodity_mr`
- `src.options_premium`
- `src.bond_mr_hedge`
- `src.logger`
- `dashboard/app.py`

### Smoke tests
`python3 tools/smoke_test.py`:
- `sector_rotation` ✅
- `gap_fade` ✅
- `forex_mr` ✅
- `forex_breakout` ✅
- `futures_mr` ✅
- `futures_trend` ✅
- `intl_etf_mr` ✅
- `commodity_mr` ✅
- `options_premium` ✅
- `bond_mr_hedge` ✅

## SECÇÃO 3 — Robustez IB + yfinance fallback

### O que está correcto
- `IBConnection.connect()` liga via `connectAsync()` e activa `reqMarketDataType(3)` em [src/data_feed.py:260](/Users/beatrizneves/Documents/Playground/bot-trading/src/data_feed.py#L260)
- `get_current_price()` e `get_current_volume()` deixaram de usar `run_until_complete`/`asyncio.run`
- o fallback `yfinance` existe e foi validado para `AAPL`, `SPY`, `EWG`, `EWJ`, `EUR`, `GBP`, `ES`, `GC`, `VIX`

### Problemas encontrados
1. O fallback `yfinance` é síncrono e corre dentro de métodos `async`, bloqueando o event loop em [src/data_feed.py:604](/Users/beatrizneves/Documents/Playground/bot-trading/src/data_feed.py#L604) e [src/data_feed.py:625](/Users/beatrizneves/Documents/Playground/bot-trading/src/data_feed.py#L625).
2. A hierarquia “real-time -> delayed -> yfinance” não está implementada. O código fixa logo `reqMarketDataType(3)` em [src/data_feed.py:268](/Users/beatrizneves/Documents/Playground/bot-trading/src/data_feed.py#L268), o que força delayed como modo principal.
3. `get_historical_bars()` ignora o retorno de `ensure_connected()` em [src/data_feed.py:682](/Users/beatrizneves/Documents/Playground/bot-trading/src/data_feed.py#L682) e continua a tentar IB mesmo sem ligação, o que degrada muito o ciclo durante quedas de gateway/TWS.

## SECÇÃO 4 — Contratos expandidos

### O que está correcto
- `Index` para `VIX`, `^VIX`, `SPX`, `NDX`, `DJI`, `RUT` em [src/contracts.py:61](/Users/beatrizneves/Documents/Playground/bot-trading/src/contracts.py#L61)
- `Forex` para `EUR`, `GBP`, `JPY`, `CHF`, `AUD`, `NZD`, `CAD` em [src/contracts.py:70](/Users/beatrizneves/Documents/Playground/bot-trading/src/contracts.py#L70)
- `Future` com expiry automático em [src/contracts.py:254](/Users/beatrizneves/Documents/Playground/bot-trading/src/contracts.py#L254)
- ETFs internacionais continuam a cair em `Stock`

### Problemas encontrados
1. O rollover de futuros é heurístico e não usa o contrato realmente dominante por volume/open interest. `_next_futures_expiry()` em [src/contracts.py:254](/Users/beatrizneves/Documents/Playground/bot-trading/src/contracts.py#L254) escolhe meses fixos e o dia 15, o que pode seleccionar um contrato ainda listável mas já não front-month operacional.
2. O `build_contract()` está correcto para contratos, mas `market_hours.py` não distingue índices (`IND`) de equities; do ponto de vista de sessão, VIX/SPX acabam tratados como `STK_US`.

## SECÇÃO 5 — Event loop e asyncio

### O que está correcto
- não há mais `run_until_complete` nem `asyncio.run` dentro do fluxo de mercado
- as notificações Telegram são agendadas via `_schedule_telegram()` em [main.py:925](/Users/beatrizneves/Documents/Playground/bot-trading/main.py#L925)

### Problemas encontrados
1. O path de falha do preflight agenda `critical_error()` e faz `sys.exit(1)` logo a seguir em [main.py:815](/Users/beatrizneves/Documents/Playground/bot-trading/main.py#L815), [main.py:822](/Users/beatrizneves/Documents/Playground/bot-trading/main.py#L822). Isto é frágil e já foi observado a produzir coroutine não aguardada no arranque falhado.
2. `poll_commands()` abre um `aiohttp.ClientSession()` novo a cada 10 segundos em [src/logger.py:971](/Users/beatrizneves/Documents/Playground/bot-trading/src/logger.py#L971). Não é uma falha funcional, mas cria churn desnecessário de sockets/sessões.
3. O bootstrap de compatibilidade com `asyncio.get_event_loop()` continua espalhado por vários ficheiros. Funciona hoje, mas não resolve a deprecação estrutural do ecossistema `eventkit`/Python 3.14+.

## SECÇÃO 6 — Risk Manager em produção

### Problemas críticos
1. O bot não aplica qualquer limite semanal no loop principal. `weekly_loss` está hardcoded a `0.0` em [main.py:2274](/Users/beatrizneves/Documents/Playground/bot-trading/main.py#L2274), apesar de o `RiskManager` já suportar `weekly_loss_limit`.
2. O “kill switch mensal” usa `metrics.get("total_pnl")` em [main.py:2309](/Users/beatrizneves/Documents/Playground/bot-trading/main.py#L2309)-[main.py:2323](/Users/beatrizneves/Documents/Playground/bot-trading/main.py#L2323), ou seja, P&L acumulado de toda a história, não do mês actual. Depois de um ou dois meses, o comportamento deixa de corresponder ao limite mensal de 10%.

### Observações adicionais
- As rejeições `R:R` do tipo `1.27 vs 2.5` são normais à luz da regra actual; não são bug, são um bloqueio correcto do `RiskManager`.
- O filtro de correlação existe e está a ser usado em `intl_etf_mr`, mas não há expansão equivalente para outros módulos multi-activo.

## SECÇÃO 7 — Market Hours

### Problema principal
`market_hours.py` usa horas UTC fixas em [src/market_hours.py:23](/Users/beatrizneves/Documents/Playground/bot-trading/src/market_hours.py#L23)-[src/market_hours.py:27](/Users/beatrizneves/Documents/Playground/bot-trading/src/market_hours.py#L27) e depois constrói `opens_at/closes_at` com esses valores em [src/market_hours.py:122](/Users/beatrizneves/Documents/Playground/bot-trading/src/market_hours.py#L122)-[src/market_hours.py:147](/Users/beatrizneves/Documents/Playground/bot-trading/src/market_hours.py#L147).

Impacto:
- NYSE está correcto apenas numa parte do ano; em DST, `09:30-16:00 ET` não corresponde a `14:30-21:00 UTC`
- XETRA também varia com DST europeu
- Forex e micro futures usam janelas UTC fixas em [src/market_hours.py:150](/Users/beatrizneves/Documents/Playground/bot-trading/src/market_hours.py#L150)-[src/market_hours.py:194](/Users/beatrizneves/Documents/Playground/bot-trading/src/market_hours.py#L194), sem modelar mudanças sazonais de sessão

Conclusão:
- o gating “can open new grid / pre-close / closed” pode estar errado durante vários meses do ano

## SECÇÃO 8 — Performance e escalabilidade

### Problemas encontrados
1. O ciclo principal obtém `1 Y` de barras diárias para cada símbolo em [main.py:1487](/Users/beatrizneves/Documents/Playground/bot-trading/main.py#L1487)-[main.py:1489](/Users/beatrizneves/Documents/Playground/bot-trading/main.py#L1489).
2. O monitor de grids volta a pedir `1 Y` de barras para recentragem em [main.py:2207](/Users/beatrizneves/Documents/Playground/bot-trading/main.py#L2207)-[main.py:2209](/Users/beatrizneves/Documents/Playground/bot-trading/main.py#L2209).
3. A cache histórica vive só 60s em [src/data_feed.py:579](/Users/beatrizneves/Documents/Playground/bot-trading/src/data_feed.py#L579), mas o ciclo por defeito é 300s em [config.py:216](/Users/beatrizneves/Documents/Playground/bot-trading/config.py#L216)-[config.py:218](/Users/beatrizneves/Documents/Playground/bot-trading/config.py#L218). Resultado: quase todos os pedidos históricos expiram antes do ciclo seguinte.
4. Cada símbolo consome, no mínimo, `1` request histórica + `2` de preço + `2` de volume ([src/data_feed.py:760](/Users/beatrizneves/Documents/Playground/bot-trading/src/data_feed.py#L760)-[src/data_feed.py:764](/Users/beatrizneves/Documents/Playground/bot-trading/src/data_feed.py#L764), [src/data_feed.py:852](/Users/beatrizneves/Documents/Playground/bot-trading/src/data_feed.py#L852)-[src/data_feed.py:857](/Users/beatrizneves/Documents/Playground/bot-trading/src/data_feed.py#L857), [src/data_feed.py:930](/Users/beatrizneves/Documents/Playground/bot-trading/src/data_feed.py#L930)-[src/data_feed.py:935](/Users/beatrizneves/Documents/Playground/bot-trading/src/data_feed.py#L930)). Com 30 símbolos, o orçamento do rate limiter fica rapidamente saturado.

Conclusão:
- `9` símbolos é aceitável
- `30+` símbolos, no estado actual, vai gerar pacing, latência de ciclo e backlog

## SECÇÃO 9 — Dashboard

### O que está correcto
- `dashboard/` está read-only
- o layout é funcional e os 4 tabs existem

### Problemas encontrados
1. `load_trades()`, `load_grids()` e `load_log_tail()` lêem o ficheiro inteiro a cada refresh em [dashboard/app.py:52](/Users/beatrizneves/Documents/Playground/bot-trading/dashboard/app.py#L52)-[dashboard/app.py:95](/Users/beatrizneves/Documents/Playground/bot-trading/dashboard/app.py#L95). Com logs/trades grandes, o custo cresce linearmente.
2. O refresh via full page reload em [dashboard/app.py:427](/Users/beatrizneves/Documents/Playground/bot-trading/dashboard/app.py#L427)-[dashboard/app.py:430](/Users/beatrizneves/Documents/Playground/bot-trading/dashboard/app.py#L427) reinicia filtros e repete parse total dos ficheiros.
3. O campo “P&L não realizado” em [dashboard/app.py:324](/Users/beatrizneves/Documents/Playground/bot-trading/dashboard/app.py#L324)-[dashboard/app.py:327](/Users/beatrizneves/Documents/Playground/bot-trading/dashboard/app.py#L324) é derivado de `total_pnl` do estado da grid, não de mark-to-market real.

## SECÇÃO 10 — Qualidade funcional adicional

### Problemas encontrados
1. O preço usado por regimes e sinais não é o preço actual. `get_market_data()` documenta e devolve “último preço de fecho” em [src/data_feed.py:1099](/Users/beatrizneves/Documents/Playground/bot-trading/src/data_feed.py#L1099), [src/data_feed.py:1142](/Users/beatrizneves/Documents/Playground/bot-trading/src/data_feed.py#L1142)-[src/data_feed.py:1143](/Users/beatrizneves/Documents/Playground/bot-trading/src/data_feed.py#L1143). Depois `main.py` consome isso como `price` em [main.py:1522](/Users/beatrizneves/Documents/Playground/bot-trading/main.py#L1522)-[main.py:1539](/Users/beatrizneves/Documents/Playground/bot-trading/main.py#L1539).
2. `preflight_check()` já chama `_reconcile_startup()` em [main.py:887](/Users/beatrizneves/Documents/Playground/bot-trading/main.py#L887), mas `run()` volta a chamá-la em [main.py:1352](/Users/beatrizneves/Documents/Playground/bot-trading/main.py#L1352). Isto duplica fetches ao IB, logs e notificação de reconciliação no arranque.
3. `vix_proxy` para bonds/options vem de fechos diários históricos em [main.py:1036](/Users/beatrizneves/Documents/Playground/bot-trading/main.py#L1036)-[main.py:1068](/Users/beatrizneves/Documents/Playground/bot-trading/main.py#L1068), não de snapshot actual. Intraday, o gating de VIX pode ficar um dia inteiro atrasado.
4. `options_premium` continua intencionalmente desactivado por config e não tem pipeline de IV/earnings no `main.py`. Não é bug escondido, mas também não é uma funcionalidade operacional hoje.

## SECÇÃO 11 — Comandos para teste manual

### Regressão base
```bash
pytest -q --timeout=30 --tb=short
python3 tools/smoke_test.py
```

### Sessões / DST
```bash
python3 - <<'PY'
from datetime import datetime, UTC
from src.market_hours import is_market_open

summer = datetime(2026, 6, 15, 13, 40, tzinfo=UTC)  # NYSE já devia estar aberto
winter = datetime(2026, 1, 15, 14, 40, tzinfo=UTC)

print("NYSE verão:", is_market_open("SPY", "STK_US", summer))
print("NYSE inverno:", is_market_open("SPY", "STK_US", winter))
PY
```

### Kill switches
```bash
rg -n "weekly_loss = 0.0|monthly_pnl = metrics.get\\(\"total_pnl\"" main.py
```

### Preço de decisão vs preço actual
```bash
python3 - <<'PY'
from pathlib import Path
text = Path("src/data_feed.py").read_text()
print("current_price usa último fecho:", "result[\"current_price\"] = _safe_last(close)" in text)
PY
```

### Escala / pacing
```bash
python3 - <<'PY'
symbols = 30
per_symbol_cost = 1 + 2 + 2
print("Custo mínimo por ciclo:", symbols * per_symbol_cost)
print("Limite histórico do rate limiter:", 60, "por 600s")
PY
```

### Arranque com IB local
```bash
python3 main.py
```

## SECÇÃO 12 — Descobertas autónomas

1. O `.env` local continua a sobrepor `MAX_POSITIONS=10` e `MAX_GRIDS=5`; por isso os logs reais de arranque não reflectem os fallbacks/documentação actualizados.
2. O bot mostra uma boa cobertura de testes de unidade/integração, mas os testes não estão a validar três pontos centrais de produção:
   - preço actual vs último fecho
   - kill switches semanal/mensal no `main.py`
   - janelas horárias correctas com DST
3. O score `100/100` do v5 era excessivamente optimista porque media sobretudo compilação, imports e testes existentes; não cobria estes edge cases de produção.

## SECÇÃO 13 — Score actualizado

| Categoria | Peso | Nota |
|---|---:|---:|
| Correcção funcional em produção | 35% | 22/35 |
| Risco / kill switches / segurança operacional | 25% | 16/25 |
| Robustez IB / fallback / asyncio | 15% | 11/15 |
| Testes / imports / baseline | 15% | 15/15 |
| Performance / escalabilidade / observabilidade | 10% | 8/10 |
| **TOTAL** | **100%** | **84/100** |

## SECÇÃO 14 — Plano de implementação por impacto

### Fase A — Bloqueadores para unsupervised
1. Corrigir `current_price` para usar snapshot real e separar “último fecho” de “preço actual”.
2. Corrigir kill switches no `main.py`: semanal real, mensal baseado no mês corrente, e testes de regressão.
3. Reescrever `market_hours.py` para usar calendários/horários reais com DST.

### Fase B — Robustez operacional
4. Tornar o fallback `yfinance` não bloqueante e abortar cedo pedidos históricos quando IB estiver offline.
5. Corrigir path de `preflight`/shutdown para não deixar coroutines de Telegram por agendar.
6. Remover a reconciliação duplicada no arranque.

### Fase C — Escala e qualidade
7. Reduzir pressão de pacing: barras incrementais, TTL alinhado com o ciclo, requests partilhados por símbolo/referência.
8. Melhorar dashboard para ficheiros grandes.
9. Melhorar front-month de futuros por regra de roll real, não só por calendário fixo.

## SECÇÃO 15 — PROBLEMAS ENCONTRADOS (priorizados)

| ID | Prioridade | Ficheiro:linha | Problema | Impacto |
|---|---|---|---|---|
| P0-1 | Crítico | `src/data_feed.py:1142`, `main.py:1522` | O bot decide e executa com o último fecho diário, não com preço actual | Sinais, regimes, entradas e stops podem ficar desfasados do mercado real |
| P0-2 | Crítico | `main.py:2274`, `main.py:2309` | Kill switch semanal ausente; kill switch mensal usa P&L total histórico | O controlo de risco em produção não corresponde às regras 3/6/10% |
| P1-1 | Alto | `src/market_hours.py:23-27`, `:122-194` | Sessões hardcoded em UTC e sem DST real | O bot pode abrir/fechar grids fora da sessão correcta |
| P1-2 | Alto | `src/data_feed.py:604-645`, `:682`, `:799-950` | Fallback Yahoo bloqueia o event loop; histórico insiste no IB mesmo offline | Latência, stalls e degradação em falhas de broker |
| P1-3 | Alto | `src/data_feed.py:268` | Delayed data é forçado globalmente; hierarquia live->delayed->Yahoo não existe | Quem tiver live data continua preso a delayed |
| P2-1 | Médio | `main.py:887`, `main.py:1352` | Reconciliação de arranque corre duas vezes | Requests/alertas/logs duplicados no startup |
| P2-2 | Médio | `main.py:815-822`, `main.py:930-938` | Path de erro crítico ainda é frágil para Telegram/asyncio | Risco de warnings/tarefas perdidas em falhas precoces |
| P2-3 | Médio | `main.py:1036-1068` | `vix_proxy` usa fecho diário, não snapshot actual | Gating de bonds/options pode ficar stale intraday |
| P2-4 | Médio | `src/contracts.py:254-283` | Expiry de futuros usa heurística simplificada | Risco de escolher contrato errado junto ao roll |
| P3-1 | Baixo | `dashboard/app.py:52-95`, `:427-430` | Dashboard relê ficheiros inteiros e faz full reload a cada 5s | Escala mal com logs/trades grandes |
| P3-2 | Baixo | `src/logger.py:958-980` | `poll_commands()` recria `ClientSession` continuamente | Overhead desnecessário, mas não bloqueante |
| P3-3 | Baixo | `main.py:1333`, `src/options_premium.py` | `options_premium` continua sem pipeline operacional real | Módulo existe, mas não participa na operação actual |

## SECÇÃO 16 — PROMPTS PARA FIX (copiar-colar para Claude Code)

### Prompt 1 — Corrigir preço actual no pipeline de sinais
```markdown
Corrige o pipeline de preço no bot sem tocar em signal_engine.py, grid_engine.py nem risk_manager.py.

Problema:
- `src/data_feed.py:get_market_data()` preenche `current_price` com o último fecho diário.
- `main.py:_process_symbol()` usa esse valor para regime, sinal e execução.

Objectivo:
1. Separar claramente:
   - `last_close` = último fecho diário das barras
   - `current_price` = snapshot actual via IB, com fallback yfinance
2. Em `main.py`, usar `current_price` real para:
   - `detect_regime`
   - `kotegawa_signal`
   - sizing/entrada/grid creation
3. Manter `sma25/sma50/sma200/rsi14/atr14/bb/volume_avg` calculados nas barras diárias.
4. Garantir fallback gracioso se o snapshot actual falhar:
   - usar `last_close`
   - logar aviso explícito
5. Adicionar testes que falhariam antes:
   - `get_market_data()` deixa de chamar “current_price” ao último fecho
   - `_process_symbol()` usa snapshot actual quando disponível

Validação:
- pytest dos testes afectados
- smoke test do símbolo com bars diárias + snapshot mockado
```

### Prompt 2 — Corrigir kill switches semanal e mensal no main.py
```markdown
Corrige a lógica de kill switches em `main.py` sem alterar as regras do `RiskManager`.

Problema:
- `weekly_loss = 0.0`
- o “mensal” usa `calculate_metrics()['total_pnl']`, ou seja, P&L de toda a história

Objectivo:
1. Calcular no `main.py`:
   - P&L diário real
   - P&L semanal real (semana ISO ou janela definida claramente)
   - P&L mensal real (mês corrente UTC)
2. Usar:
   - `check_daily_limit`
   - `check_weekly_limit`
   - `check_kill_switch`
3. Manter 3% / 6% / 10% intactos.
4. Adicionar testes de regressão:
   - semanal dispara a 6% e não fica sempre a zero
   - mensal olha só para trades do mês corrente
   - histórico acumulado de meses anteriores não dispara o kill switch mensal

Validação:
- pytest tests/test_integration.py tests/test_main_audit.py -q
```

### Prompt 3 — Reescrever market_hours para calendários reais e DST
```markdown
Corrige `src/market_hours.py` para usar horários reais com DST e calendários de exchange.

Problema:
- NYSE/XETRA/FOREX/FUT estão hardcoded em UTC
- DST e horários reais das exchanges não são respeitados

Objectivo:
1. Para equities US/EU:
   - usar `pandas_market_calendars` não só para dia útil, mas também para open/close exactos da sessão
2. Para FOREX e micro futures:
   - modelar explicitamente a janela semanal e a pausa diária com timezone correcto
   - evitar horários UTC fixos quando DST altera a referência operacional
3. Tratar `Index`/VIX de forma explícita
4. Adicionar testes:
   - NYSE em verão vs inverno
   - XETRA em verão vs inverno
   - Forex Sunday open / Friday close
   - micro futures pause diária

Validação:
- pytest tests/test_market_hours.py -q
```

### Prompt 4 — Tornar yfinance não bloqueante e abortar cedo quando IB cai
```markdown
Melhora `src/data_feed.py` para robustez operacional sem tocar na lógica de estratégia.

Problemas:
- fallback yfinance é síncrono e bloqueia o event loop
- `get_historical_bars()` continua a tentar IB mesmo quando `ensure_connected()` devolve False

Objectivo:
1. Mover chamadas yfinance para thread executor (`asyncio.to_thread`) ou helper async equivalente
2. Em `get_current_price()` e `get_current_volume()`, manter a API async
3. Em `get_historical_bars()`, se IB não estiver ligado:
   - devolver DataFrame vazio imediatamente
   - logar o motivo
4. Se quiseres, criar fallback histórico opcional Yahoo só para símbolos suportados, mas sem mexer em estratégia
5. Adicionar testes:
   - event loop não bloqueia
   - histórico não tenta IB quando disconnected
   - fallback Yahoo continua funcional

Validação:
- pytest tests/test_data_feed.py -q
```

### Prompt 5 — Corrigir preflight/Telegram e reconciliação duplicada
```markdown
Corrige o arranque em `main.py` com foco em asyncio/Telegram.

Problemas:
- `preflight_check()` agenda `critical_error()` e faz `sys.exit(1)` logo a seguir
- `_reconcile_startup()` corre duas vezes

Objectivo:
1. Substituir `sys.exit(1)` dentro de coroutine por excepção controlada
2. Garantir que a notificação crítica é:
   - aguardada de forma segura
   - ou criada por factory lazy que não deixa coroutine solta
3. Remover a segunda chamada de `_reconcile_startup()` em `run()`
4. Adicionar teste de regressão:
   - falha de preflight não gera “coroutine was never awaited”
   - reconciliação arranca uma só vez

Validação:
- pytest tests/test_main_audit.py tests/test_logger.py -q
```

### Prompt 6 — Reduzir pacing e custo por ciclo para 30+ símbolos
```markdown
Optimiza o pipeline de dados em `main.py` e `src/data_feed.py` para escalar acima de 30 símbolos.

Problema:
- cada ciclo pede 1Y de barras para cada símbolo
- monitor de grids volta a pedir 1Y
- cache histórica expira em 60s, mas o ciclo é 300s

Objectivo:
1. Alinhar TTL/caching com `cycle_interval_seconds`
2. Evitar voltar a pedir 1Y inteiro em cada ciclo:
   - usar incremental update
   - ou cache por ciclo reutilizável
3. Reutilizar barras/ref data entre `_process_symbol`, `_get_reference_closes` e `_monitor_single_grid`
4. Adicionar instrumentação simples:
   - nº de pedidos históricos por ciclo
   - tempo de ciclo
   - tempo em pacing wait
5. Adicionar teste/unit smoke que demonstre redução de chamadas

Validação:
- pytest relevante
- log com métricas de requests por ciclo
```

### Prompt 7 — Dashboard para datasets grandes
```markdown
Optimiza `dashboard/app.py` sem introduzir escrita em disco.

Problema:
- trades/log/grids são lidos integralmente a cada 5s
- reload total da página reinicia filtros e escala mal

Objectivo:
1. Tornar leitura do log incremental ou por tail real
2. Reduzir parse completo de trades/grids quando o ficheiro não mudou
3. Manter dashboard 100% read-only
4. Se possível, trocar full reload por refresh nativo de componentes
5. Adicionar um pequeno benchmark/manual note no README

Validação:
- py_compile
- abrir dashboard com ficheiros grandes e confirmar responsividade
```

## HISTÓRICO

| Versão | Data | Score | Estado |
|---|---|---:|---|
| v5 | 2026-03-16 | 100/100 | Score sobrestimado para produção |
| v6 | 2026-03-17 | 84/100 | Boa base de testes, ainda não pronto para operação não supervisionada |

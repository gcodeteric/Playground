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


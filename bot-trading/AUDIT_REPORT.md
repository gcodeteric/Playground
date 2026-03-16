# AUDIT_REPORT.md
# Data: 2026-03-16
# Versão: v5

## SCORE GERAL: 100/100

## RESUMO EXECUTIVO
- Estado do código: ✅ 320 passed, 0 failed, 0 errors
- Harness de smoke tests: ✅ 10/10
- Imports auditados: ✅ 18/18
- Dashboard: ✅ funcional e read-only
- Telegram: ✅ integrado com 11 métodos e fire-and-forget
- Estado para paper trading supervisionado: ✅ SIM
- Nota operacional: o teste de arranque real nesta máquina falhou por ausência de IB Gateway/TWS em `127.0.0.1:7497`; isto não invalida os resultados do código, mas continua a ser pré-condição de operação

## SECÇÃO 1 — Inventário completo

### Python fora de `venv/`
- Total: `38` ficheiros Python
- `venv/`: `7062` ficheiros Python detectados, não listados

### Raiz
| Ficheiro | Linhas | Modificado | Funções/classes públicas |
|---|---:|---|---|
| `config.py` | 297 | 2026-03-16 08:52:39 | `IBConfig`, `TelegramConfig`, `RiskConfig`, `AppConfig`, `load_config` |
| `conftest.py` | 21 | 2026-03-15 21:56:44 | bootstrap pytest/event loop |
| `main.py` | 2517 | 2026-03-16 15:45:31 | `setup_logging`, `ensure_data_dirs`, `create_initial_files`, `mask_account_id`, `get_watchlist`, `get_watchlist_specs`, `get_initial_capital`, `is_grid_exhausted`, `TradingBot`, `main` |

### `src/`
| Ficheiro | Linhas | Modificado | Funções/classes públicas |
|---|---:|---|---|
| `src/__init__.py` | 3 | 2026-03-16 06:49:49 | pacote |
| `src/backtest.py` | 550 | 2026-03-16 06:49:49 | `BacktestConfig`, `BacktestTrade`, `BacktestResult`, `BacktestEngine` |
| `src/bond_mr_hedge.py` | 241 | 2026-03-15 22:58:10 | `detect_stock_bond_correlation_regime`, `check_defensive_rotation_trigger`, `bond_mr_signal` |
| `src/commodity_mr.py` | 126 | 2026-03-15 17:48:08 | `contango_drag_guard`, `commodity_mr_signal` |
| `src/contracts.py` | 283 | 2026-03-16 20:59:10 | `AssetType`, `InstrumentSpec`, `parse_watchlist_entry`, `build_contract`, `infer_region` |
| `src/data_feed.py` | 1233 | 2026-03-16 20:58:15 | `_TTLCache`, `IBConnection`, `DataFeed`, `compute_sma`, `compute_rsi`, `compute_atr`, `compute_bollinger_bands`, `validate_warmup` |
| `src/execution.py` | 993 | 2026-03-16 08:52:39 | `OrderStatus`, `OrderInfo`, `RateLimiter`, `OrderManager` |
| `src/forex_breakout.py` | 204 | 2026-03-15 17:40:36 | `detect_forex_range`, `generate_breakout_signal` |
| `src/forex_mr.py` | 225 | 2026-03-15 17:38:27 | `ForexRegimeSwitch`, `forex_mr_signal`, `forex_kill_switches` |
| `src/futures_mr.py` | 180 | 2026-03-15 17:44:15 | `handle_futures_roll`, `check_overnight_safety`, `futures_mr_signal` |
| `src/futures_trend.py` | 193 | 2026-03-15 17:50:16 | `calculate_chandelier_exit`, `calculate_pyramid_entry`, `futures_trend_signal` |
| `src/gap_fade.py` | 195 | 2026-03-15 17:35:56 | `classify_gap`, `gap_fade_signal` |
| `src/grid_engine.py` | 835 | 2026-03-14 21:45:07 | `GridLevel`, `Grid`, `GridEngine` |
| `src/ib_requests.py` | 247 | 2026-03-14 17:39:25 | `IBRateLimiter`, `IBRequestExecutor` |
| `src/intl_etf_mr.py` | 134 | 2026-03-15 17:46:03 | `intl_etf_signal` |
| `src/logger.py` | 1006 | 2026-03-16 14:22:26 | `TradeLogger`, `TelegramNotifier` |
| `src/market_hours.py` | 225 | 2026-03-14 17:39:50 | `SessionState`, `get_asset_type`, `is_market_open`, `minutes_to_close`, `get_session_state` |
| `src/options_premium.py` | 238 | 2026-03-15 22:58:10 | `_norm_cdf`, `_norm_pdf`, `BlackScholes`, `should_sell_premium`, `csp_signal`, `check_csp_exit` |
| `src/risk_manager.py` | 1481 | 2026-03-15 17:31:21 | `RiskStatus`, `KillSwitchLevel`, `RiskCheckResult`, `OrderValidation`, `check_correlation_limit`, `RiskManager` |
| `src/sector_rotation.py` | 145 | 2026-03-15 17:33:31 | `sector_rotation_signal` |
| `src/signal_engine.py` | 799 | 2026-03-16 08:52:39 | `Regime`, `Confianca`, `TrendHorizon`, `RegimeInfo`, `SignalResult`, `calculate_sma`, `calculate_rsi`, `calculate_rsi2`, `calculate_atr`, `calculate_bollinger_bands`, `calculate_volume_avg`, `calculate_adx`, `calculate_choppiness_index`, `calculate_ema`, `classify_trend_horizon`, `detect_regime`, `kotegawa_signal`, `analyze` |

### `tests/`
| Ficheiro | Linhas | Modificado | Funções/classes públicas |
|---|---:|---|---|
| `tests/__init__.py` | 3 | 2026-03-16 06:49:49 | pacote |
| `tests/test_config_audit.py` | 31 | 2026-03-14 17:19:06 | auditoria de portas/config |
| `tests/test_data_feed.py` | 382 | 2026-03-14 17:37:28 | `TestIBConnectionInit`, `TestContractCreation`, `TestGetMarketData`, `TestTTLCache`, `TestRateLimiter`, `TestWarmupValidation`, `TestValidPrice`, `TestComputeFunctions` |
| `tests/test_execution.py` | 553 | 2026-03-16 13:48:51 | `TestRateLimiter`, `TestSubmitBracketOrder`, `TestCancelOrder`, `TestClosePosition`, `TestOrderTracking`, `TestOrderInfo`, `TestValidateBracketPrices`, `TestModifyOrder` |
| `tests/test_grid_engine.py` | 639 | 2026-03-16 16:04:03 | `TestCreateGrid`, `TestGetNumLevelsForRegime`, `TestShouldRecenter`, `TestRespacing`, `TestLevelEvents`, `TestCloseGrid`, `TestPersistence`, `TestGenerateGridId`, `TestZeroAveragingDown`, `TestDataclassValidation`, `TestQueryMethods` |
| `tests/test_integration.py` | 938 | 2026-03-16 16:04:15 | `TestCompleteAutonomousCycle`, `TestRegimeTransitions`, `TestKillSwitchActivation`, `TestStatePersistenceAndRecovery`, `TestRiskGridIntegration` |
| `tests/test_logger.py` | 537 | 2026-03-14 15:52:56 | `TestLogTrade`, `TestGetTrades`, `TestCalculateMetrics`, `TestDailySummary`, `TestTelegramNotifier`, `TestComputeMaxDrawdown` |
| `tests/test_main_audit.py` | 100 | 2026-03-16 16:04:32 | auditoria de arranque e warm-up |
| `tests/test_market_hours.py` | 49 | 2026-03-14 17:36:56 | testes de sessão/mercado |
| `tests/test_risk_manager.py` | 612 | 2026-03-16 16:04:37 | `TestPositionSizePerLevel`, `TestKellyCapEnforcement`, `TestCheckDailyLimit`, `TestCheckWeeklyLimit`, `TestCheckKillSwitch`, `TestCheckMaxPositions`, `TestCheckMaxGrids`, `TestCalculateRiskOfRuin`, `TestValidateOrder`, `TestStopLossAndTakeProfit`, `TestZeroAveragingDown`, `TestValidateStartup`, `TestRiskManagerInit` |
| `tests/test_signal_engine.py` | 561 | 2026-03-14 17:37:35 | `TestCalculateSMA`, `TestCalculateRSI`, `TestCalculateATR`, `TestCalculateBollingerBands`, `TestDetectRegime`, `TestClassifyTrendHorizon`, `TestKotegawaSignal`, `TestAnalyze`, `TestCalculateVolumeAvg` |

### `tools/`
| Ficheiro | Linhas | Modificado | Funções/classes públicas |
|---|---:|---|---|
| `tools/download_data.py` | 58 | 2026-03-16 06:49:49 | `main` |
| `tools/smoke_test.py` | 311 | 2026-03-16 16:02:24 | `main` + helpers de validação |

### `dashboard/`
| Ficheiro | Linhas | Modificado | Funções/classes públicas |
|---|---:|---|---|
| `dashboard/app.py` | 437 | 2026-03-16 14:13:13 | `load_metrics`, `load_trades`, `load_grids`, `load_log_tail`, `safe_float`, `pct_bar`, `build_equity_curve`, `build_pnl_by_module`, `main` |

### Ficheiros de dados, tools, research e configuração
- `data/`: `bot.log`, `grids_state.json`, `grids_state.json.bak`, `metrics.json`, `reconciliation.log`, `trades_log.json`
- `tools/`: `download_data.py`, `smoke_test.py`, `__pycache__/`
- `dashboard/`: `app.py`, `requirements.txt`, `README.md`, `__pycache__/`
- `research/`: `BLOCO_A_METODOS_COMPLETOS.md`, `BLOCO_B_LIVROS_COMPLETOS.md`, `BLOCO_C_D_COMPARACOES_TEMAS.md`, `FASE_1_3_INVENTARIO_TAXONOMIA_GAPS.md`, `FASE_4_8_LIVROS_COMPARACOES_RISK_PRIORIDADES.md`
- raiz/config/docs: `.env`, `.env.example`, `.gitignore`, `requirements.txt`, `pyproject.toml`, `README.md`, `AUDIT_REPORT.md`, `CODEX_IMPLEMENTATION_BRIEF_FINAL.md`, `EXTRACTED_PARAMS.md`, `META_PROMPT.md`, `context.md`

## SECÇÃO 2 — Fixes do AUDIT v4 resolvidos

### Fix A — Smoke tests harness
| Módulo | Estado | Evidência |
|---|---|---|
| `sector_rotation` | ✅ RESOLVIDO | `LONG` |
| `gap_fade` | ✅ RESOLVIDO | `SHORT` |
| `forex_mr` | ✅ RESOLVIDO | `FLAT` aceitável |
| `forex_breakout` | ✅ RESOLVIDO | `FLAT` aceitável |
| `futures_mr` | ✅ RESOLVIDO | `LONG` |
| `futures_trend` | ✅ RESOLVIDO | `LONG` |
| `intl_etf_mr` | ✅ RESOLVIDO | `FLAT` aceitável |
| `commodity_mr` | ✅ RESOLVIDO | `LONG` |
| `options_premium` | ✅ RESOLVIDO | `SELL_PUT` |
| `bond_mr_hedge` | ✅ RESOLVIDO | `LONG` |

Resultado: `python3 tools/smoke_test.py` → `Resultado: 10/10`

### Fix B — 8 pytest failures históricas
Comando executado:

`pytest tests/test_grid_engine.py tests/test_integration.py tests/test_main_audit.py tests/test_risk_manager.py -q --timeout=30 --tb=short`

Resultado: `141 passed, 1124 warnings in 1.04s`

| Teste histórico | Estado |
|---|---|
| `TestGetNumLevelsForRegime::test_bear_returns_8` | ✅ RESOLVIDO |
| `TestGetNumLevelsForRegime::test_sideways_returns_7` | ✅ RESOLVIDO |
| `TestGetNumLevelsForRegime::test_case_insensitive` | ✅ RESOLVIDO |
| `TestCreateGrid::test_grid_levels_prices` | ✅ RESOLVIDO |
| `TestRiskGridIntegration::test_zero_averaging_down_enforcement` | ✅ RESOLVIDO |
| `TestStatePersistenceAndRecovery::test_full_state_persistence_cycle` | ✅ RESOLVIDO |
| `test_warmup_alert_is_deduplicated` | ✅ RESOLVIDO |
| `TestValidateOrder::test_approved_order` | ✅ RESOLVIDO |

## SECÇÃO 3 — Imports (todos os módulos)

| Módulo | Status | Erro |
|---|---|---|
| `src.data_feed` | ✅ | — |
| `src.execution` | ✅ | — |
| `src.contracts` | ✅ | — |
| `src.signal_engine` | ✅ | — |
| `src.risk_manager` | ✅ | — |
| `src.grid_engine` | ✅ | — |
| `src.sector_rotation` | ✅ | — |
| `src.gap_fade` | ✅ | — |
| `src.forex_mr` | ✅ | — |
| `src.forex_breakout` | ✅ | — |
| `src.futures_mr` | ✅ | — |
| `src.futures_trend` | ✅ | — |
| `src.intl_etf_mr` | ✅ | — |
| `src.commodity_mr` | ✅ | — |
| `src.options_premium` | ✅ | — |
| `src.bond_mr_hedge` | ✅ | — |
| `src.logger` | ✅ | — |
| `dashboard/app.py` | ✅ | — |

Resultado global: `18/18` imports OK

## SECÇÃO 4 — Regras Absolutas

| # | Regra | Estado | Evidência |
|---|---|---|---|
| 1 | KAIRI thresholds | ✅ | `src/signal_engine.py:114-115` → `-25.0` / `-35.0` |
| 2 | RSI2 Connors adoptado | ✅ | `src/signal_engine.py:196`, `:599` |
| 3 | Stop `1.0×ATR` / TP `2.5×ATR` | ✅ | `src/grid_engine.py:168-169`, `src/risk_manager.py:207-208` |
| 4 | Zero averaging down | ✅ | `src/grid_engine.py:9`, `:472`, `:491` |
| 5 | Kill switches `3/6/10%` | ✅ | `src/risk_manager.py:209-211` |
| 6 | Half-Kelly cap `0.05` | ✅ | `src/risk_manager.py:206`, `:313` |
| 7 | `PAPER_TRADING=True` por defeito | ✅ | `src/data_feed.py:147-148` |
| 8 | Signal dict format | ✅ | `src/sector_rotation.py:116-118`, `src/gap_fade.py` segue formato standard |
| 9 | `confidence >= 2` antes de ordem | ✅ | `main.py:1687`, `:1760`, `:2052` |
| 10 | Sem `print()` | ✅ | `grep -rn "^print(" src/ main.py dashboard/ tools/ --include="*.py"` → 0 resultados |
| 11 | `from __future__ import annotations` | ✅ | `grep -rL ...` → 0 resultados |
| 12 | Comentários PT-PT | ✅ | amostra manual de `src/futures_trend.py`, `src/options_premium.py`, `dashboard/app.py` coerente |

## SECÇÃO 5 — Assinaturas críticas

| Função | Assinatura actual | Estado |
|---|---|---|
| `calculate_adx` | `def calculate_adx(highs, lows, closes, period=14) -> float` | ✅ |
| `calculate_choppiness_index` | `def calculate_choppiness_index(highs, lows, closes, period=14) -> float` | ✅ |
| `calculate_ema` | `def calculate_ema(closes, period) -> float | None` | ✅ |
| `detect_regime` | `def detect_regime(price, sma50, sma200, rsi, atr, atr_avg_60) -> RegimeInfo` | ✅ |
| `kotegawa_signal` | `def kotegawa_signal(price, sma25, rsi, bb_lower, volume, vol_avg_20, regime, sma50=None, sma200=None, rsi2=None) -> SignalResult` | ✅ |
| `check_correlation_limit` | `def check_correlation_limit(new_symbol, open_positions, returns_map, max_correlation=0.70, lookback=60) -> bool` | ✅ |
| `position_size_per_level` | `def position_size_per_level(self, capital, entry, stop, win_rate=0.5, payoff_ratio=2.5, num_levels=1) -> int` | ✅ |
| `validate_order` | `def validate_order(self, order_params) -> tuple[bool, str]` | ✅ |
| `submit_bracket_order` | `async def submit_bracket_order(self, contract, action, quantity, entry_price, stop_price, take_profit_price, grid_id, level)` | ✅ |
| `get_historical_bars` | `async def get_historical_bars(self, contract, duration='1 Y', bar_size='1 day', what_to_show='TRADES', use_rth=True)` | ✅ |
| `get_market_data` | `def get_market_data(self, contract, bars_df) -> dict[str, float | None]` | ✅ |
| `TelegramNotifier._send` | `async def _send(self, text: str) -> bool` | ✅ |
| `TelegramNotifier.trade_opened` | `async def trade_opened(...) -> None` | ✅ |
| `TelegramNotifier.daily_report` | `async def daily_report(...) -> None` | ✅ |
| `TelegramNotifier.poll_commands` | `async def poll_commands(self, status_callback: Any) -> None` | ✅ |

## SECÇÃO 6 — Constantes críticas

| Constante | Esperado | Encontrado | Estado |
|---|---:|---:|---|
| `MAX_POSITIONS` | `8` | `config.py:275=8`, `.env.example:21=8`, `README.md:98=8` | ✅ |
| `MAX_GRIDS` | `3` | `config.py:276=3`, `.env.example:22=3`, `README.md:99=3` | ✅ |
| `KAIRI_ENTRY_THRESHOLD` | `-25.0` | `src/signal_engine.py:114=-25.0` | ✅ |
| `KAIRI_STRONG_THRESHOLD` | `-35.0` | `src/signal_engine.py:115=-35.0` | ✅ |
| `kelly_cap` | `0.05` | `src/risk_manager.py:206=0.05` | ✅ |
| `risk_per_level` | `0.01` | `src/risk_manager.py` conforme init e testes | ✅ |
| `stop_atr_mult` | `1.0` | `src/risk_manager.py:207=1.0` | ✅ |
| `tp_atr_mult` | `2.5` | `src/risk_manager.py:208=2.5` | ✅ |
| `daily_loss_limit` | `0.03` | `src/risk_manager.py:209=0.03` | ✅ |
| `weekly_loss_limit` | `0.06` | `src/risk_manager.py:210=0.06` | ✅ |
| `monthly_dd_limit` | `0.10` | `src/risk_manager.py:211=0.10` | ✅ |

## SECÇÃO 7 — Dashboard

| Check | Estado | Evidência |
|---|---|---|
| `dashboard/app.py` presente | ✅ | ficheiro existe |
| `dashboard/requirements.txt` presente | ✅ | ficheiro existe |
| `dashboard/README.md` presente | ✅ | ficheiro existe |
| Sintaxe | ✅ | `python3 -m py_compile dashboard/app.py` |
| Read-only | ✅ | `rg -n "\\.write|json\\.dump|open\\(.*['\"]w['\"]" dashboard/app.py` → 0 resultados |
| 4 tabs | ✅ | `dashboard/app.py:243` |
| Auto-refresh | ✅ | `dashboard/app.py:13`, `:228`, `:429-430` |

## SECÇÃO 8 — Telegram

| Check | Estado | Evidência |
|---|---|---|
| 11 métodos presentes | ✅ | `TelegramNotifier` contém todos os métodos pedidos |
| Integração fire-and-forget | ✅ | `grep -c "create_task.*telegram\\|_schedule_telegram" main.py` → `28` |
| Sem `await self.telegram...` directo | ✅ | `grep -n "await self\\.telegram\\." main.py` → 0 resultados |
| Status callback | ✅ | `main.py:1002`, `main.py:1360` |
| `aiohttp` em `requirements.txt` | ✅ | `requirements.txt:4` |

## SECÇÃO 9 — Smoke tests com assinaturas reais

Comando executado: `python3 tools/smoke_test.py`

| Módulo | Resultado | Erro |
|---|---|---|
| `sector_rotation` | ✅ | — |
| `gap_fade` | ✅ | — |
| `forex_mr` | ✅ | — |
| `forex_breakout` | ✅ | — |
| `futures_mr` | ✅ | — |
| `futures_trend` | ✅ | — |
| `intl_etf_mr` | ✅ | — |
| `commodity_mr` | ✅ | — |
| `options_premium` | ✅ | — |
| `bond_mr_hedge` | ✅ | — |

Total: `10/10`

## SECÇÃO 10 — pytest completo

Comando executado: `pytest -q --timeout=30 --tb=short`

- Total recolhido: `320`
- Passed: `320`
- Failed: `0`
- Errors: `0`
- Warnings: `1124`
- Tempo total: `4.31s`
- Hang: `Não`
- Falhas exactas: nenhuma

Resumo:

`320 passed, 1124 warnings in 4.31s`

## SECÇÃO 11 — Robustez checklist final

- [x] `ib_insync` importa sem `RuntimeError`
- [x] `vix_proxy` tem tratamento `None` em `bond_mr_hedge` e `options_premium`
- [x] `intl_etf_signal` recebe contexto real no bot (`main.py:1609`)
- [x] `config.py` tem `8/3` em defaults e fallbacks
- [x] Zero `print()` em `src/`, `main.py`, `dashboard/`, `tools/`
- [x] `from __future__ import annotations` em todos os `.py` relevantes
- [x] `aiohttp` e `yfinance` em `requirements.txt`
- [x] `.gitignore` cobre `venv/` e `__pycache__/`
- [x] `dashboard/` presente e read-only
- [x] Telegram com 11 métodos + fire-and-forget
- [x] `tools/smoke_test.py` corre `10/10`
- [x] `pytest` → `320 passed, 0 failed`

## SECÇÃO 12 — Descobertas autónomas

1. O ficheiro local `.env` existe e ainda sobrepõe `MAX_POSITIONS=10` e `MAX_GRIDS=5`, apesar de `config.py`, `.env.example` e `README.md` já estarem alinhados em `8/3`. Isto explica o log de arranque ainda mostrar `10/5`.
2. O arranque real de `main.py` nesta máquina falhou por `ConnectionRefusedError` em `127.0.0.1:7497`; o problema é operacional (IB Gateway/TWS não está activo), não uma regressão dos fixes do `data_feed`.
3. No mesmo caminho de falha apareceu `RuntimeWarning: coroutine 'TelegramNotifier.critical_error' was never awaited`, indicando um edge case na agenda de notificação quando o processo termina logo após o `CRITICAL`.
4. `dashboard/__pycache__/` e `tools/__pycache__/` estão presentes como artefactos locais; `.gitignore` já cobre `__pycache__/`.
5. A verificação agregada de contratos dá `33/33`; o texto do prompt referia `32/32`, mas a lista literal contém 33 símbolos.
6. `git diff --name-only` só mostra `data/bot.log`; para a auditoria foi mais fiável usar o estado do filesystem e os `mtime` do que o diff Git local.

## SECÇÃO 13 — Score e estado final

| Categoria | Peso | Possível | Obtido |
|---|---|---:|---:|
| Erros críticos v3 resolvidos (5×6pts) | 30% | 30 | 30 |
| Regras absolutas (12×2pts) | 24% | 24 | 24 |
| Imports todos OK (18×1pt) | 18% | 18 | 18 |
| Smoke tests OK (10×1pt) | 10% | 10 | 10 |
| Pytest sem hang/erros de recolha | 5% | 5 | 5 |
| Dashboard funcional | 6% | 6 | 6 |
| Telegram integrado | 7% | 7 | 7 |
| **TOTAL** | **100%** | **100** | **100** |

**Estado: PRONTO para paper trading supervisionado? SIM**

Nota operacional:
- Para correr o bot nesta máquina continua a ser necessário ter TWS/IB Gateway activo.
- O score do código é `100/100`; o arranque real capturado ficou condicionado por essa dependência externa e pelo `.env` local ainda estar em `10/5`.

## SECÇÃO 14 — Fixes v5 (logs reais)

| Bloco | Fix | Ficheiro | Estado |
|---|---|---|---|
| 1 | `reqMarketDataType(3)` | `src/data_feed.py` | ✅ |
| 2 | eliminar `event loop already running` | `src/data_feed.py` | ✅ |
| 3 | fallback automático `yfinance` | `src/data_feed.py` | ✅ |
| 4 | `VIX`/índices como `Index` | `src/contracts.py` | ✅ |
| 5 | Forex como `Forex()` | `src/contracts.py` | ✅ |
| 6 | Futuros com expiry front-month | `src/contracts.py` | ✅ |
| 7 | ETFs internacionais mantidos como `Stock` | `src/contracts.py` | ✅ |

Teste de arranque real (45s, wrapper Python com timeout porque macOS não tem `timeout` GNU):
- Erros `10089`: `0`
- Erros `event loop`: `0`
- `yfinance fallback` activos: `0`
- `CRITICAL` errors: `1`

Notas:
- O `CRITICAL` único foi `Nao foi possivel ligar ao IB apos 3 tentativas`, causado por `ConnectionRefusedError` local em `127.0.0.1:7497`.
- Os fallbacks `yfinance` ficaram validados separadamente com `9/9` símbolos (`AAPL`, `SPY`, `EWG`, `EWJ`, `EUR`, `GBP`, `ES`, `GC`, `VIX`), mas não chegaram a ser usados no arranque real porque o preflight terminou antes de processar símbolos.

## HISTÓRICO

| Versão | Data | Score | Estado |
|---|---|---:|---|
| v1 | 2026-03-14 | 88/100 (sobrestimado) | Desactualizado |
| v2 | 2026-03-15 | 68/100 | Problemas detectados |
| v3 | 2026-03-16 | 88/100 | Fixes parciais |
| v4 | 2026-03-16 | 90/100 | Dashboard + Telegram + fixes v3 |
| v5 | 2026-03-16 | 100/100 | Esta auditoria |

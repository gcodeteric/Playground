# AUDIT_REPORT.md
# Data: 2026-03-16 16:17:53 UTC
# Versão: v5

## SCORE GERAL: 100/100

## RESUMO EXECUTIVO
- Erros críticos activos: 0
- Imports quebrados: 0/18
- Violações de regras absolutas: 0
- Smoke tests com assinaturas reais: 10/10
- Pytest completo: 320 passed, 0 failed, 0 errors
- Warnings: 1124 (não bloqueantes; maioritariamente deprecações)
- Estado para paper trading supervisionado: SIM

## SECÇÃO 1 — Inventário completo

### Python fora de `venv/`
Ficheiros Python fora de `venv/`: 38  
Ficheiros em `venv/` contados mas não listados: 11659

| Ficheiro | Linhas | Modificado | Funções/classes públicas |
|---|---:|---|---|
| `config.py` | 297 | 2026-03-16 08:52:39 | `IBConfig`, `TelegramConfig`, `RiskConfig`, `AppConfig`, `load_config` |
| `conftest.py` | 21 | 2026-03-15 21:56:44 | - |
| `dashboard/app.py` | 437 | 2026-03-16 14:13:13 | `load_metrics`, `load_trades`, `load_grids`, `load_log_tail`, `safe_float`, `pct_bar`, `build_equity_curve`, `build_pnl_by_module`, `main` |
| `main.py` | 2517 | 2026-03-16 15:45:31 | `setup_logging`, `ensure_data_dirs`, `create_initial_files`, `mask_account_id`, `get_watchlist`, `get_watchlist_specs`, `get_initial_capital`, `is_grid_exhausted`, `process_new_modules`, `TradingBot`, `main` |
| `src/__init__.py` | 3 | 2026-03-16 06:49:49 | - |
| `src/backtest.py` | 550 | 2026-03-16 06:49:49 | `BacktestConfig`, `BacktestTrade`, `BacktestResult`, `BacktestEngine` |
| `src/bond_mr_hedge.py` | 241 | 2026-03-15 22:58:10 | `detect_stock_bond_correlation_regime`, `check_defensive_rotation_trigger`, `bond_mr_signal` |
| `src/commodity_mr.py` | 126 | 2026-03-15 17:48:08 | `contango_drag_guard`, `commodity_mr_signal` |
| `src/contracts.py` | 171 | 2026-03-15 21:56:44 | `AssetType`, `InstrumentSpec`, `parse_watchlist_entry`, `build_contract`, `infer_region` |
| `src/data_feed.py` | 1083 | 2026-03-15 21:56:44 | `IBConnection`, `compute_sma`, `compute_rsi`, `compute_atr`, `compute_bollinger_bands`, `get_warmup_missing_rules`, `validate_warmup`, `DataFeed` |
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
| `src/options_premium.py` | 238 | 2026-03-15 22:58:10 | `BlackScholes`, `should_sell_premium`, `csp_signal`, `check_csp_exit` |
| `src/risk_manager.py` | 1481 | 2026-03-15 17:31:21 | `RiskStatus`, `KillSwitchLevel`, `RiskCheckResult`, `OrderValidation`, `check_correlation_limit`, `RiskManager` |
| `src/sector_rotation.py` | 145 | 2026-03-15 17:33:31 | `sector_rotation_signal` |
| `src/signal_engine.py` | 799 | 2026-03-16 08:52:39 | `Regime`, `Confianca`, `TrendHorizon`, `RegimeInfo`, `SignalResult`, `calculate_sma`, `calculate_rsi`, `calculate_rsi2`, `calculate_atr`, `calculate_bollinger_bands`, `calculate_volume_avg`, `calculate_adx`, `calculate_choppiness_index`, `calculate_ema`, `classify_trend_horizon`, `detect_regime`, `kotegawa_signal`, `analyze` |
| `tests/__init__.py` | 3 | 2026-03-16 06:49:49 | - |
| `tests/test_config_audit.py` | 31 | 2026-03-14 17:19:06 | `test_ib_port_paper_gateway_auto`, `test_ib_port_paper_tws_auto`, `test_ib_port_live_gateway_auto`, `test_ib_port_live_tws_auto`, `test_ib_port_manual_override` |
| `tests/test_data_feed.py` | 382 | 2026-03-14 17:37:28 | `mock_ib`, `mock_connection`, `data_feed`, `sample_bars_df`, `TestIBConnectionInit`, `TestContractCreation`, `TestGetMarketData`, `TestTTLCache`, `TestRateLimiter`, `TestWarmupValidation`, `TestValidPrice`, `TestComputeFunctions` |
| `tests/test_execution.py` | 553 | 2026-03-16 13:48:51 | `mock_ib`, `mock_connection`, `order_manager`, `mock_contract`, `TestRateLimiter`, `TestSubmitBracketOrder`, `TestCancelOrder`, `TestClosePosition`, `TestOrderTracking`, `TestOrderInfo`, `TestValidateBracketPrices`, `TestModifyOrder` |
| `tests/test_grid_engine.py` | 639 | 2026-03-16 16:04:03 | `tmp_data_dir`, `engine`, `sample_grid`, `TestCreateGrid`, `TestGetNumLevelsForRegime`, `TestShouldRecenter`, `TestRespacing`, `TestLevelEvents`, `TestCloseGrid`, `TestPersistence`, `TestGenerateGridId`, `TestZeroAveragingDown`, `TestDataclassValidation`, `TestQueryMethods` |
| `tests/test_integration.py` | 938 | 2026-03-16 16:04:15 | `tmp_data_dir`, `risk_manager`, `grid_engine`, `trade_logger`, `simulate_price_series`, `execute_trading_cycle`, `TestCompleteAutonomousCycle`, `TestRegimeTransitions`, `TestKillSwitchActivation`, `TestStatePersistenceAndRecovery`, `TestRiskGridIntegration` |
| `tests/test_logger.py` | 537 | 2026-03-14 15:52:56 | `tmp_data_dir`, `logger`, `sample_trade`, `TestLogTrade`, `TestGetTrades`, `TestCalculateMetrics`, `TestDailySummary`, `TestTelegramNotifier`, `TestComputeMaxDrawdown` |
| `tests/test_main_audit.py` | 100 | 2026-03-16 16:04:32 | `test_first_run_files_are_created`, `test_warmup_alert_is_deduplicated`, `test_reconciliation_marks_ghost_grid`, `test_reconciliation_registers_orphan_position` |
| `tests/test_market_hours.py` | 49 | 2026-03-14 17:36:56 | `test_us_equity_open_session`, `test_us_equity_preclose`, `test_eu_equity_closed_after_hours`, `test_forex_weekend_closed`, `test_micro_future_daily_pause` |
| `tests/test_risk_manager.py` | 612 | 2026-03-16 16:04:37 | `rm`, `rm_small`, `TestPositionSizePerLevel`, `TestKellyCapEnforcement`, `TestCheckDailyLimit`, `TestCheckWeeklyLimit`, `TestCheckKillSwitch`, `TestCheckMaxPositions`, `TestCheckMaxGrids`, `TestCalculateRiskOfRuin`, `TestValidateOrder`, `TestStopLossAndTakeProfit`, `TestZeroAveragingDown`, `TestValidateStartup`, `TestRiskManagerInit` |
| `tests/test_signal_engine.py` | 561 | 2026-03-14 17:37:35 | `TestCalculateSMA`, `TestCalculateRSI`, `TestCalculateATR`, `TestCalculateBollingerBands`, `TestDetectRegime`, `TestClassifyTrendHorizon`, `TestKotegawaSignal`, `TestAnalyze`, `TestCalculateVolumeAvg` |
| `tools/download_data.py` | 58 | 2026-03-16 06:49:49 | `main` |
| `tools/smoke_test.py` | 311 | 2026-03-16 16:02:24 | `main` |

### `data/`
- `data/bot.log`
- `data/grids_state.json`
- `data/grids_state.json.bak`
- `data/metrics.json`
- `data/reconciliation.log`
- `data/trades_log.json`

### `tools/`
- `tools/download_data.py`
- `tools/smoke_test.py`
- `tools/__pycache__/download_data.cpython-314.pyc`
- `tools/__pycache__/smoke_test.cpython-314.pyc`

### `research/`
- `research/BLOCO_A_METODOS_COMPLETOS.md`
- `research/BLOCO_B_LIVROS_COMPLETOS.md`
- `research/BLOCO_C_D_COMPARACOES_TEMAS.md`
- `research/FASE_1_3_INVENTARIO_TAXONOMIA_GAPS.md`
- `research/FASE_4_8_LIVROS_COMPARACOES_RISK_PRIORIDADES.md`

### `dashboard/`
- `dashboard/README.md`
- `dashboard/app.py`
- `dashboard/requirements.txt`
- `dashboard/__pycache__/app.cpython-314.pyc`

### Configuração na raiz
- `.env`
- `.env.example`
- `.gitignore`
- `AUDIT_REPORT.md`
- `CODEX_IMPLEMENTATION_BRIEF_FINAL.md`
- `EXTRACTED_PARAMS.md`
- `META_PROMPT.md`
- `README.md`
- `context.md`
- `pyproject.toml`
- `requirements.txt`

## SECÇÃO 2 — Fixes do AUDIT v4 resolvidos

### Fix A — Smoke tests harness
`tools/smoke_test.py` existe e correu com `10/10`.

| Módulo | Estado | Evidência |
|---|---|---|
| `sector_rotation` | ✅ RESOLVIDO | `LONG` |
| `gap_fade` | ✅ RESOLVIDO | `SHORT` |
| `forex_mr` | ✅ RESOLVIDO | `FLAT` válido |
| `forex_breakout` | ✅ RESOLVIDO | `FLAT` válido |
| `futures_mr` | ✅ RESOLVIDO | `LONG` |
| `futures_trend` | ✅ RESOLVIDO | `LONG` |
| `intl_etf_mr` | ✅ RESOLVIDO | `FLAT` válido |
| `commodity_mr` | ✅ RESOLVIDO | `LONG` |
| `options_premium` | ✅ RESOLVIDO | `SELL_PUT` |
| `bond_mr_hedge` | ✅ RESOLVIDO | `LONG` |

### Fix B — 8 pytest failures
Comando executado:

`pytest tests/test_grid_engine.py tests/test_integration.py tests/test_main_audit.py tests/test_risk_manager.py -q --timeout=30 --tb=short`

Resultado: `141 passed, 1124 warnings in 0.94s`

| Falha anterior | Estado | Evidência |
|---|---|---|
| `TestGetNumLevelsForRegime::test_bear_returns_8` | ✅ RESOLVIDO | suite alvo passou |
| `TestGetNumLevelsForRegime::test_sideways_returns_7` | ✅ RESOLVIDO | suite alvo passou |
| `TestGetNumLevelsForRegime::test_case_insensitive` | ✅ RESOLVIDO | suite alvo passou |
| `TestCreateGrid::test_grid_levels_prices` | ✅ RESOLVIDO | suite alvo passou |
| `TestRiskGridIntegration::test_zero_averaging_down_enforcement` | ✅ RESOLVIDO | suite alvo passou |
| `TestStatePersistenceAndRecovery::test_full_state_persistence_cycle` | ✅ RESOLVIDO | suite alvo passou |
| `test_warmup_alert_is_deduplicated` | ✅ RESOLVIDO | suite alvo passou |
| `TestValidateOrder::test_approved_order` | ✅ RESOLVIDO | suite alvo passou |

## SECÇÃO 3 — Imports (todos os módulos)

| Módulo | Status | Erro |
|---|---|---|
| `data_feed` | ✅ | - |
| `execution` | ✅ | - |
| `contracts` | ✅ | - |
| `signal_engine` | ✅ | - |
| `risk_manager` | ✅ | - |
| `grid_engine` | ✅ | - |
| `sector_rotation` | ✅ | - |
| `gap_fade` | ✅ | - |
| `forex_mr` | ✅ | - |
| `forex_breakout` | ✅ | - |
| `futures_mr` | ✅ | - |
| `futures_trend` | ✅ | - |
| `intl_etf_mr` | ✅ | - |
| `commodity_mr` | ✅ | - |
| `options_premium` | ✅ | - |
| `bond_mr_hedge` | ✅ | - |
| `logger/telegram` | ✅ | - |
| `dashboard/app.py` | ✅ | - |

## SECÇÃO 4 — Regras Absolutas

| # | Regra | Estado | Evidência |
|---|---|---|---|
| 1 | KAIRI thresholds `-25.0 / -35.0` | ✅ | `src/signal_engine.py:114-115` |
| 2 | RSI com Connors RSI2 adoptado | ✅ | `src/signal_engine.py:196`, `:599` |
| 3 | Stop `1.0xATR` / TP `2.5xATR` | ✅ | `src/grid_engine.py:168-169`, `src/risk_manager.py:207-208` |
| 4 | Zero averaging down | ✅ | `src/grid_engine.py:9`, `:472`, `:491` |
| 5 | Kill switches `3/6/10%` | ✅ | `src/risk_manager.py:209-211` |
| 6 | Half-Kelly `0.05` | ✅ | `src/risk_manager.py:206`, `:313` |
| 7 | `PAPER_TRADING=True` por defeito | ✅ | `src/data_feed.py:146-147` |
| 8 | Signal dict format | ✅ | `src/sector_rotation.py:116-118`, `:138-140` |
| 9 | `confidence >= 2` antes de ordem | ✅ | `main.py:1687-1692` |
| 10 | Sem `print()` | ✅ | `grep` sem resultados em `src/`, `main.py`, `dashboard/`, `tools/` |
| 11 | `from __future__ import annotations` | ✅ | `grep -rL` sem resultados |
| 12 | Comentários PT-PT | ✅ | amostra manual coerente em `src/options_premium.py`, `dashboard/app.py`; docstrings PT-PT também em `src/futures_trend.py` |

## SECÇÃO 5 — Assinaturas críticas

| Função | Assinatura actual | Estado |
|---|---|---|
| `calculate_adx` | `(highs: list[float], lows: list[float], closes: list[float], period: int = 14) -> float` | ✅ |
| `calculate_choppiness_index` | `(highs: list[float], lows: list[float], closes: list[float], period: int = 14) -> float` | ✅ |
| `calculate_ema` | `(closes: list[float], period: int) -> float \| None` | ✅ |
| `detect_regime` | `(price: float, sma50: float, sma200: float, rsi: float, atr: float, atr_avg_60: float) -> RegimeInfo` | ✅ |
| `kotegawa_signal` | `(price, sma25, rsi, bb_lower, volume, vol_avg_20, regime, sma50=None, sma200=None, rsi2=None) -> SignalResult` | ✅ |
| `check_correlation_limit` | `(new_symbol: str, open_positions: list[str], returns_map: dict[str, list[float]], max_correlation: float = 0.7, lookback: int = 60) -> bool` | ✅ |
| `RiskManager.position_size_per_level` | `(self, capital, entry, stop, win_rate=0.5, payoff_ratio=2.5, num_levels=1) -> int` | ✅ |
| `RiskManager.validate_order` | `(self, order_params: dict[str, Any]) -> tuple[bool, str]` | ✅ |
| `OrderManager.submit_bracket_order` | `(self, contract, action, quantity, entry_price, stop_price, take_profit_price, grid_id, level) -> dict[str, Any] \| None` | ✅ |
| `DataFeed.get_historical_bars` | `(self, contract, duration='1 Y', bar_size='1 day', what_to_show='TRADES', use_rth=True) -> pd.DataFrame` | ✅ |
| `DataFeed.get_market_data` | `(self, contract, bars_df: pd.DataFrame) -> dict[str, float \| None]` | ✅ |
| `TelegramNotifier._send` | `(self, text: str) -> bool` | ✅ |
| `TelegramNotifier.trade_opened` | `(self, symbol, action, entry, stop, tp, confidence, module, regime, paper=True) -> None` | ✅ |
| `TelegramNotifier.daily_report` | `(self, capital, daily_pnl, n_trades, win_rate, open_grids, kill_switch_pct, paper=True) -> None` | ✅ |
| `TelegramNotifier.poll_commands` | `(self, status_callback: Any) -> None` | ✅ |

## SECÇÃO 6 — Constantes críticas

| Constante | Esperado | Encontrado | Estado |
|---|---:|---:|---|
| `MAX_POSITIONS` fallback | 8 | 8 | ✅ |
| `MAX_GRIDS` fallback | 3 | 3 | ✅ |
| `.env.example MAX_POSITIONS` | 8 | 8 | ✅ |
| `.env.example MAX_GRIDS` | 3 | 3 | ✅ |
| `README MAX_POSITIONS` | 8 | 8 | ✅ |
| `README MAX_GRIDS` | 3 | 3 | ✅ |
| `_KAIRI_ENTRY_THRESHOLD` | -25.0 | -25.0 | ✅ |
| `_KAIRI_STRONG_THRESHOLD` | -35.0 | -35.0 | ✅ |
| `kelly_cap` | 0.05 | 0.05 | ✅ |
| `risk_per_level` | 0.01 | 0.01 | ✅ |
| `stop_atr_mult` | 1.0 | 1.0 | ✅ |
| `tp_atr_mult` | 2.5 | 2.5 | ✅ |
| `daily_loss_limit` | 0.03 | 0.03 | ✅ |
| `weekly_loss_limit` | 0.06 | 0.06 | ✅ |
| `monthly_dd_limit` | 0.10 | 0.10 | ✅ |

## SECÇÃO 7 — Dashboard

| Check | Estado | Evidência |
|---|---|---|
| `dashboard/app.py` presente | ✅ | comando `test -f` |
| `dashboard/requirements.txt` presente | ✅ | comando `test -f` |
| `dashboard/README.md` presente | ✅ | comando `test -f` |
| Sintaxe | ✅ | `python3 -m py_compile dashboard/app.py` |
| Read-only | ✅ | `grep ".write\|open.*w\|json.dump"` sem resultados |
| 4 tabs | ✅ | `dashboard/app.py:243` |
| Auto-refresh | ✅ | `dashboard/app.py:13`, `dashboard/app.py:429` |

## SECÇÃO 8 — Telegram

| Check | Estado | Evidência |
|---|---|---|
| 11 métodos presentes | ✅ | `✅ Todos os 11 métodos presentes` |
| Integração fire-and-forget | ✅ | `28` ocorrências de `_schedule_telegram/create_task` |
| Sem `await self.telegram...` directo | ✅ | `grep` sem resultados |
| `_telegram_status_callback` presente | ✅ | `main.py:1002`, `main.py:1360` |
| `aiohttp` em `requirements.txt` | ✅ | `requirements.txt:4` |

## SECÇÃO 9 — Smoke tests com assinaturas reais

Comando executado: `python3 tools/smoke_test.py`

| Módulo | Resultado | Erro |
|---|---|---|
| `sector_rotation` | ✅ | - |
| `gap_fade` | ✅ | - |
| `forex_mr` | ✅ | - |
| `forex_breakout` | ✅ | - |
| `futures_mr` | ✅ | - |
| `futures_trend` | ✅ | - |
| `intl_etf_mr` | ✅ | - |
| `commodity_mr` | ✅ | - |
| `options_premium` | ✅ | - |
| `bond_mr_hedge` | ✅ | - |

Total: 10/10

## SECÇÃO 10 — pytest completo

Comando executado: `pytest -q --timeout=30 --tb=short`

| Métrica | Valor |
|---|---:|
| Testes recolhidos | 320 |
| Passed | 320 |
| Failed | 0 |
| Errors | 0 |
| Warnings | 1124 |
| Tempo total | 3.73s |
| Hang | Não |

Falhas exactas: nenhuma.

Warnings dominantes:
- `eventkit/util.py`: deprecação de `asyncio.get_event_loop_policy`
- `tests/test_integration.py` e `tests/test_risk_manager.py`: uso indirecto de `datetime.utcnow()`

## SECÇÃO 11 — Robustez checklist final

- [x] `ib_insync` importa sem RuntimeError
- [x] `vix_proxy` tem tratamento `None` em `bond_mr_hedge` e `options_premium`
- [x] `intl_etf_signal` recebe contexto real no bot
- [x] `config.py` tem `8/3` em defaults e fallbacks
- [x] Zero `print()` em `src/`, `main.py`, `dashboard/`, `tools/`
- [x] `from __future__ import annotations` em todos os `.py` relevantes
- [x] `aiohttp` e `yfinance` em `requirements.txt`
- [x] `.gitignore` cobre `venv/` e `__pycache__/`
- [x] `dashboard/` presente e read-only
- [x] Telegram com 11 métodos e fire-and-forget
- [x] `tools/smoke_test.py` corre `10/10`
- [x] Pytest `320 passed, 0 failed`

## SECÇÃO 12 — Descobertas autónomas

1. Foram gerados artefactos locais que não devem ser versionados:
   - `tools/__pycache__/download_data.cpython-314.pyc`
   - `tools/__pycache__/smoke_test.cpython-314.pyc`
   - `dashboard/__pycache__/app.cpython-314.pyc`
2. O directório `research/` contém 5 documentos auxiliares não operacionais.
3. Não há diff local nos ficheiros protegidos auditados neste lote:
   - `src/signal_engine.py`
   - `src/grid_engine.py`
   - `src/risk_manager.py`
   - `src/execution.py`
   - `src/data_feed.py`
4. O bot está funcional para paper trading supervisionado, mas mantém warnings de deprecação em bibliotecas externas e helpers de testes.
5. `dashboard/app.py` e `tools/smoke_test.py` criaram artefactos `__pycache__` no workspace ao compilar/executar.

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

Acções em aberto por impacto no score: nenhuma.  
Melhorias não bloqueantes:
- limpar `__pycache__`
- reduzir warnings de deprecação em `eventkit` e uso de `datetime.utcnow()` nos testes

## HISTÓRICO

| Versão | Data | Score | Estado |
|---|---|---:|---|
| v1 | 2026-03-14 | 88/100 (sobrestimado) | Desactualizado |
| v2 | 2026-03-15 | 68/100 | Problemas detectados |
| v3 | 2026-03-16 | 88/100 | Fixes parciais |
| v4 | 2026-03-16 | 90/100 | Dashboard + Telegram + fixes v3 |
| v5 | 2026-03-16 | 100/100 | Esta auditoria |

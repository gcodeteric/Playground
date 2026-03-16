# CODEX IMPLEMENTATION BRIEF — FINAL
# Bot Multi-Instrumento v2.0
# Gerado por: Claude Cowork
# Data: 2026-03-15
# ════════════════════════════════════════════════════════════

---

## SECÇÃO 0 — ARQUITECTURA RESUMIDA DO BOT ACTUAL

### Stack Técnico
- **Linguagem:** Python 3.12+
- **Broker:** Interactive Brokers via `ib_insync` (async)
- **Dependências:** pydantic, pandas, numpy, ib_insync, dotenv
- **Sem:** talib, scipy (excepto opções), sem novas dependências
- **Modo:** PAPER_TRADING = True por defeito

### Ficheiros e Responsabilidades

| Ficheiro | Responsabilidade |
|---|---|
| `main.py` | Loop principal, orquestração de todos os módulos, watchlist iteration |
| `config.py` | Configuração via .env com pydantic (IBConfig, RiskConfig, TelegramConfig) |
| `src/signal_engine.py` | Indicadores técnicos puros (SMA, RSI, RSI2, ATR, BB, Volume), detecção de regime, sinal Kotegawa |
| `src/grid_engine.py` | Criação/gestão de grids com níveis geométricos, recentragem, persistência JSON |
| `src/risk_manager.py` | Position sizing Half-Kelly, kill switches, validação de ordens, drawdown scaling |
| `src/execution.py` | Submissão de ordens bracket ao IB (LimitOrder + StopOrder + LimitOrder TP) |
| `src/data_feed.py` | Conexão IB, barras históricas, preço actual, indicadores pandas |
| `src/market_hours.py` | Sessões por tipo de activo (STK_US, STK_EU, FOREX, FUT), can_open_new_grid |
| `src/contracts.py` | Parsing de watchlist, construção de contratos IB (Stock, Forex, Future, CFD) |
| `src/ib_requests.py` | Rate limiter e request executor para API IB |
| `src/logger.py` | Configuração de logging |

### Fluxo de Execução Actual (main.py)
```
1. connect() → IBConnection ao IB Gateway/TWS
2. load_state() → GridEngine.load_state() (grids_state.json)
3. LOOP INFINITO (cycle_interval_seconds = 300s):
   a. Para cada símbolo na watchlist:
      i.   get_historical_bars() → DataFrame OHLCV
      ii.  get_market_data() → dict com indicadores
      iii. detect_regime() → RegimeInfo (BULL/BEAR/SIDEWAYS)
      iv.  kotegawa_signal() → SignalResult
      v.   Se sinal válido: validate_order() → (bool, str)
      vi.  Se aprovado: create_grid() + submit_bracket_order()
   b. Verificar grids activas: recentrar se necessário
   c. save_state() → persistir grids
   d. Resumo diário às 23:00
   e. sleep(cycle_interval_seconds)
```

### Regras Absolutas que NUNCA Mudam
1. **KAIRI = (price - SMA25) / SMA25 × 100** — fórmula sagrada para acções
2. **Thresholds Kotegawa:** entrada mínima -25%, forte -35% (ACÇÕES APENAS)
3. **RSI(14) < 30** obrigatório para sinal válido em acções
4. **Grid:** BULL 5 níveis | BEAR 4 níveis | SIDEWAYS 8 níveis
5. **Stop: 1.0 × ATR | TP: 2.5 × ATR | R:R = 2.5:1**
6. **ZERO averaging down** — níveis stopped NÃO reabrem
7. **Kill switches:** diário 3% | semanal 6% | mensal 10%
8. **Half-Kelly:** kelly_cap=5% | risk_per_level=1%
9. **PAPER_TRADING = True** por defeito
10. **Signal dict format para novos módulos:** `{signal, confidence, entry_price, stop_loss, take_profit, position_size, metadata}`
11. **Só operar com confidence >= 2** (HIGH-CERTAINTY GATE)
12. **Logging via `logging.getLogger(__name__)`** — nunca print()
13. **`from __future__ import annotations`** em todos os ficheiros
14. **Comentários em PT-PT | variáveis/funções em inglês**

### Assinaturas Existentes Críticas (NÃO ALTERAR)

```python
# signal_engine.py
def calculate_sma(closes: list[float], period: int) -> float | None
def calculate_rsi(closes: list[float], period: int = 14) -> float | None
def calculate_rsi2(closes: list[float]) -> float | None
def calculate_atr(highs: list[float], lows: list[float], closes: list[float], period: int = 14) -> float | None
def calculate_bollinger_bands(closes: list[float], period: int = 20, std_dev: float = 2.0) -> tuple[float, float, float] | None
def calculate_volume_avg(volumes: list[float], period: int = 20) -> float | None
def detect_regime(price, sma50, sma200, rsi, atr, atr_avg_60) -> RegimeInfo
def kotegawa_signal(price, sma25, rsi, bb_lower, volume, vol_avg_20, regime, sma50=None, sma200=None, rsi2=None) -> SignalResult

# grid_engine.py — GridEngine class
def create_grid(self, symbol, center_price, atr, regime, num_levels, base_quantity, confidence, size_multiplier, stop_atr_mult=1.0, tp_atr_mult=2.5) -> Grid

# risk_manager.py — RiskManager class
def position_size_per_level(self, capital, entry, stop, win_rate=0.5, payoff_ratio=2.5, num_levels=1) -> int
def validate_order(self, order_params: dict[str, Any]) -> tuple[bool, str]
# order_params keys: symbol, entry_price, stop_price, take_profit_price, capital, daily_pnl, weekly_pnl, monthly_pnl, current_positions, current_grids, level, win_rate, payoff_ratio, num_levels

# execution.py — OrderManager class
async def submit_bracket_order(self, contract, action, quantity, entry_price, stop_price, take_profit_price, grid_id, level) -> dict | None

# data_feed.py — DataFeed class
async def get_historical_bars(self, contract, duration="1 Y", bar_size="1 day", what_to_show="TRADES", use_rth=True) -> pd.DataFrame
def get_market_data(self, contract, bars_df) -> dict[str, float | None]
# Retorna: sma25, sma50, sma200, rsi14, atr14, bb_upper, bb_middle, bb_lower, volume_avg_20, current_price, atr_avg_60

# market_hours.py
def get_session_state(spec: InstrumentSpec, now=None) -> SessionState
# SessionState.can_open_new_grid → bool (is_open AND NOT is_pre_close)

# contracts.py
def parse_watchlist_entry(raw_entry: str) -> InstrumentSpec
def build_contract(spec: InstrumentSpec) -> Contract
# AssetType: STK, ETF, FX, FUT, CFD
```

### Constantes Reais do Código

```python
# grid_engine.py
_REGIME_NUM_LEVELS = {"BULL": 5, "BEAR": 4, "SIDEWAYS": 8}
_RECENTER_THRESHOLDS = {"BULL": 0.80, "BEAR": 0.60, "SIDEWAYS": 0.70}
_MIN_SPACING_PCT = 1.0
_MAX_SPACING_PCT = 4.0

# signal_engine.py
_KAIRI_ENTRY_THRESHOLD = -25.0
_KAIRI_STRONG_THRESHOLD = -35.0

# risk_manager.py (defaults)
risk_per_level = 0.01       # 1%
kelly_cap = 0.05            # 5%
stop_atr_mult = 1.0
tp_atr_mult = 2.5
daily_loss_limit = 0.03     # 3%
weekly_loss_limit = 0.06    # 6%
monthly_dd_limit = 0.10     # 10%
max_positions = 8
max_grids = 3
min_rr = 2.5

# market_hours.py
SCHEDULES = {
    "STK_US": ("NYSE", "14:30", "21:00"),
    "STK_EU": ("XETRA", "08:00", "16:30"),
    "FOREX": (None, "22:00", "22:00"),
    "FUT": (None, "23:00", "22:00"),
}
_PRE_CLOSE_MINUTES = 5
```

---

## SECÇÃO 1 — NOVOS HELPERS GLOBAIS (implementar primeiro)

Estas funções são necessárias por vários módulos e devem ser implementadas antes de qualquer módulo novo.

### 1.1 calculate_adx() — Adicionar a `src/signal_engine.py`

```python
def calculate_adx(
    highs: list[float],
    lows: list[float],
    closes: list[float],
    period: int = 14,
) -> float:
    """Calcula o Average Directional Index (ADX).

    Mede a força da tendência sem indicar direcção.
    ADX < 20 → mercado ranging (bom para mean reversion)
    ADX 20-25 → zona morta (nenhum módulo opera)
    ADX > 25 → mercado trending (bom para trend following)

    Implementação sem pandas, sem talib — compatível com os helpers existentes
    em signal_engine.py (calculate_sma, calculate_rsi, calculate_atr).

    Args:
        highs: Lista de preços máximos (mais antigo → mais recente).
        lows: Lista de preços mínimos.
        closes: Lista de preços de fecho.
        period: Período do ADX (por defeito 14).

    Returns:
        Valor do ADX (0-100). Retorna 0.0 se dados insuficientes.
    """
    if len(closes) < period + 1:
        return 0.0

    tr_list: list[float] = []
    dm_plus: list[float] = []
    dm_minus: list[float] = []

    for i in range(1, len(closes)):
        h, l, pc = highs[i], lows[i], closes[i - 1]
        tr = max(h - l, abs(h - pc), abs(l - pc))
        up = highs[i] - highs[i - 1]
        down = lows[i - 1] - lows[i]
        dm_plus.append(up if up > down and up > 0 else 0.0)
        dm_minus.append(down if down > up and down > 0 else 0.0)
        tr_list.append(tr)

    def _smooth(data: list[float], n: int) -> list[float]:
        """Suavização de Wilder para séries de período n."""
        if len(data) < n:
            return []
        s = sum(data[:n])
        result = [s]
        for i in range(n, len(data)):
            s = s - s / n + data[i]
            result.append(s)
        return result

    atr_s = _smooth(tr_list, period)
    dmp_s = _smooth(dm_plus, period)
    dmm_s = _smooth(dm_minus, period)

    dx_list: list[float] = []
    for a, p, m in zip(atr_s, dmp_s, dmm_s):
        if a == 0:
            dx_list.append(0.0)
            continue
        pdi = 100.0 * p / a
        mdi = 100.0 * m / a
        if pdi + mdi == 0:
            dx_list.append(0.0)
        else:
            dx_list.append(100.0 * abs(pdi - mdi) / (pdi + mdi))

    if len(dx_list) < period:
        return 0.0

    return sum(dx_list[-period:]) / period
```

**Onde adicionar:** No ficheiro `src/signal_engine.py`, após a função `calculate_volume_avg()` (linha ~313), antes da secção "Detecção de regime de mercado".

### 1.2 calculate_choppiness_index() — Adicionar a `src/signal_engine.py`

```python
def calculate_choppiness_index(
    highs: list[float],
    lows: list[float],
    closes: list[float],
    period: int = 14,
) -> float:
    """Calcula o Choppiness Index (CHOP).

    Mede se o mercado está em tendência ou em consolidação.
    CHOP > 55-60 → mercado ranging (bom para mean reversion)
    CHOP < 45 → mercado trending (evitar mean reversion)

    Fórmula: CHOP = 100 × log10(sum(TR, N) / (HH - LL)) / log10(N)

    Args:
        highs: Lista de preços máximos (mais antigo → mais recente).
        lows: Lista de preços mínimos.
        closes: Lista de preços de fecho.
        period: Período do CHOP (por defeito 14).

    Returns:
        Valor do CHOP (0-100). Retorna 100.0 se dados insuficientes ou range zero.
    """
    import math

    n = min(len(highs), len(lows), len(closes))
    if n < period + 1:
        return 100.0

    # Calcular soma dos True Range dos últimos N períodos
    tr_sum = 0.0
    for i in range(n - period, n):
        if i == 0:
            tr = highs[i] - lows[i]
        else:
            tr = max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i - 1]),
                abs(lows[i] - closes[i - 1]),
            )
        tr_sum += tr

    # Highest high e lowest low dos últimos N períodos
    hh = max(highs[n - period : n])
    ll = min(lows[n - period : n])

    if hh == ll:
        return 100.0

    chop = 100.0 * math.log10(tr_sum / (hh - ll)) / math.log10(period)
    return max(0.0, min(100.0, chop))
```

**Onde adicionar:** No ficheiro `src/signal_engine.py`, imediatamente após `calculate_adx()`.

### 1.3 calculate_ema() — Adicionar a `src/signal_engine.py`

```python
def calculate_ema(
    closes: list[float],
    period: int,
) -> float | None:
    """Calcula a Média Móvel Exponencial (EMA) para o período indicado.

    Utilizada pelos módulos de futuros (trend following) para sinais
    de cruzamento EMA 20/50.

    Args:
        closes: Lista de preços de fecho (mais antigo → mais recente).
        period: Número de períodos para a EMA.

    Returns:
        Valor da EMA ou None se dados insuficientes.
    """
    if len(closes) < period or period <= 0:
        return None

    # Iniciar com SMA dos primeiros 'period' valores
    ema = sum(closes[:period]) / period
    multiplier = 2.0 / (period + 1)

    for price in closes[period:]:
        ema = (price - ema) * multiplier + ema

    return ema
```

**Onde adicionar:** No ficheiro `src/signal_engine.py`, imediatamente após `calculate_choppiness_index()`.

### 1.4 check_correlation_limit() — Adicionar a `src/risk_manager.py`

```python
def check_correlation_limit(
    new_symbol: str,
    open_positions: list[str],
    returns_map: dict[str, list[float]],
    max_correlation: float = 0.70,
    lookback: int = 60,
) -> bool:
    """Verifica se um novo instrumento tem correlação excessiva com posições abertas.

    Bloqueia a abertura se a correlação de Pearson com qualquer posição
    aberta for superior a max_correlation (70% por defeito).

    Integrar em validate_order() como verificação adicional para módulos
    multi-instrumento (ETFs internacionais, commodities, sector rotation).

    Args:
        new_symbol: Símbolo do novo instrumento a avaliar.
        open_positions: Lista de símbolos com posição aberta.
        returns_map: Dicionário {symbol: [retornos diários]} com pelo menos
                     lookback dias de dados para cada símbolo.
        max_correlation: Correlação máxima permitida (0.70 = 70%).
        lookback: Número de dias para o cálculo (60 = trimestral).

    Returns:
        True se permitido (correlação OK), False se bloqueado.
    """
    import math

    if not open_positions:
        return True  # portfólio vazio: passe livre

    if new_symbol not in returns_map:
        logger.warning(
            "Sem dados de retornos para %s — a bloquear por precaução.",
            new_symbol,
        )
        return False

    new_returns = returns_map[new_symbol][-lookback:]

    for pos_symbol in open_positions:
        if pos_symbol not in returns_map:
            continue

        pos_returns = returns_map[pos_symbol][-lookback:]
        min_len = min(len(new_returns), len(pos_returns))

        if min_len < lookback * 0.5:
            continue  # dados insuficientes para este par

        # Correlação de Pearson manual (sem numpy/pandas)
        nr = new_returns[-min_len:]
        pr = pos_returns[-min_len:]
        n = len(nr)

        mean_nr = sum(nr) / n
        mean_pr = sum(pr) / n

        cov = sum((a - mean_nr) * (b - mean_pr) for a, b in zip(nr, pr)) / n
        std_nr = math.sqrt(sum((a - mean_nr) ** 2 for a in nr) / n)
        std_pr = math.sqrt(sum((b - mean_pr) ** 2 for b in pr) / n)

        if std_nr == 0 or std_pr == 0:
            continue

        corr = cov / (std_nr * std_pr)

        if corr > max_correlation:
            logger.info(
                "Correlacao %s<->%s = %.2f > %.2f -- BLOQUEADO.",
                new_symbol, pos_symbol, corr, max_correlation,
            )
            return False

    return True  # nenhum par excedeu max_correlation
```

**Onde adicionar:** No ficheiro `src/risk_manager.py`, como funcao de modulo (apos as dataclasses, antes da classe `RiskManager`), importavel como `from src.risk_manager import check_correlation_limit`.

---

## SECÇÃO 2 — 10 MÓDULOS (por ordem de implementação)

### MÓDULO 6 — ROTAÇÃO SECTORIAL (`src/sector_rotation.py`)

**STATUS:** Novo ficheiro | **Fase de capital:** 1 (€0-2k+)
**Prioridade:** 1º — mais simples, alto Sharpe, sem dependências complexas

**PARÂMETROS DE CONFIGURAÇÃO:**
```python
SECTOR_ROTATION_CONFIG = {
    "is_active": True,                   # Activo desde Fase 1
    "momentum_period": 252,              # 12 meses de lookback
    "skip_recent_days": 21,              # Excluir último mês (momentum reversal)
    "top_n": 3,                          # Top-3 sectores (melhor Sharpe documentado)
    "rebalance_day": 1,                  # Dia 1 de cada mês
    "bear_filter_sma": 200,              # SPY < SMA200 → safe havens
    "safe_havens": ["XLU", "XLP", "GLD"],
    "universe_by_phase": {
        1: ["XLK", "XLF", "XLV", "XLE", "XLI", "XLY", "XLP", "XLU", "XLB", "XLC", "XLRE"],
        2: ["XLK", "XLF", "XLV", "XLE", "XLI", "XLY", "XLP", "XLU", "XLB", "XLC", "XLRE",
            "QQQ", "IWM", "GLD", "TLT", "HYG", "DBC"],
        3: ["XLK", "XLF", "XLV", "XLE", "XLI", "XLY", "XLP", "XLU", "XLB", "XLC", "XLRE",
            "QQQ", "IWM", "GLD", "TLT", "HYG", "DBC", "EFA", "EEM", "EZU", "EWJ"],
    },
}
```

**FUNÇÕES A IMPLEMENTAR:**

```python
"""
Módulo 6: Rotação Sectorial — Momentum 12-1 (Moskowitz).

Selecciona os Top-N sectores por momentum dos últimos 12 meses
(excluindo o último mês) e roda a carteira mensalmente.
Em bear market (SPY < SMA200), roda para safe havens.

Fase de capital: 1+ (€0-2k)
"""

from __future__ import annotations

import logging
from typing import Any

from src.signal_engine import calculate_sma

logger = logging.getLogger(__name__)


def sector_rotation_signal(
    df_map: dict[str, dict[str, list[float]]],
    spy_closes: list[float],
    config: dict[str, Any],
    current_day_of_month: int,
) -> dict[str, Any]:
    """Gera sinal de rotação sectorial baseado em Momentum 12-1.

    Metodologia (Moskowitz):
    - Momentum = retorno dos últimos 252 dias excluindo os últimos 21
    - Seleccionar Top-N sectores por momentum
    - Em bear market (SPY < SMA200): rodar para safe havens
    - Rebalancing mensal (dia 1 do mês)

    Args:
        df_map: Dicionário {symbol: {"close": [preços]}} com pelo menos 252 barras.
        spy_closes: Lista de preços de fecho do SPY.
        config: SECTOR_ROTATION_CONFIG com todos os parâmetros.
        current_day_of_month: Dia actual do mês (1-31).

    Returns:
        Signal dict no formato padrão do bot.
    """
    rebalance_day = config.get("rebalance_day", 1)
    if current_day_of_month != rebalance_day:
        return _flat_signal({"reason": "not_rebalance_day"})

    momentum_period = config.get("momentum_period", 252)
    skip_recent = config.get("skip_recent_days", 21)
    top_n = config.get("top_n", 3)
    safe_havens = config.get("safe_havens", ["XLU", "XLP", "GLD"])
    bear_sma = config.get("bear_filter_sma", 200)

    # Detectar bear market via SPY < SMA200
    sma200_spy = calculate_sma(spy_closes, bear_sma)
    current_spy = spy_closes[-1] if spy_closes else 0.0
    is_bear_market = sma200_spy is not None and current_spy < sma200_spy

    # Calcular momentum 12-1 para cada sector
    momentum_scores: dict[str, float] = {}
    for sym, data in df_map.items():
        closes = data.get("close", [])
        if len(closes) < momentum_period:
            continue
        price_12m_ago = closes[-(momentum_period)]
        price_1m_ago = closes[-(skip_recent)]
        if price_12m_ago <= 0:
            continue
        momentum_scores[sym] = (price_1m_ago - price_12m_ago) / price_12m_ago

    if not momentum_scores:
        return _flat_signal({"reason": "insufficient_data"})

    # Ordenar por momentum descendente
    sorted_sectors = sorted(momentum_scores, key=momentum_scores.get, reverse=True)

    # Seleccionar Top-N (ou safe havens em bear market)
    if is_bear_market:
        target_allocations = [s for s in sorted_sectors if s in safe_havens][:top_n]
        if not target_allocations:
            target_allocations = [s for s in safe_havens if s in df_map][:top_n]
    else:
        target_allocations = sorted_sectors[:top_n]

    if not target_allocations:
        return _flat_signal({"reason": "no_valid_sectors"})

    return {
        "signal": "LONG",
        "confidence": 3,
        "entry_price": 0.0,
        "stop_loss": 0.0,
        "take_profit": 0.0,
        "position_size": 0.0,
        "metadata": {
            "type": "rotation",
            "allocations": target_allocations,
            "bear_regime": is_bear_market,
            "scores": {s: round(momentum_scores.get(s, 0.0), 4) for s in target_allocations},
            "module": "sector_rotation",
        },
    }


def _flat_signal(metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    """Retorna sinal FLAT (sem acção)."""
    return {
        "signal": "FLAT",
        "confidence": 0,
        "entry_price": 0.0,
        "stop_loss": 0.0,
        "take_profit": 0.0,
        "position_size": 0.0,
        "metadata": metadata or {},
    }
```

**INTEGRAÇÃO EM main.py:**
```python
# No loop principal, ANTES do processamento de símbolos individuais:
from src.sector_rotation import sector_rotation_signal

# Executar 1x por ciclo, só no dia de rebalancing
if MODULE_CONFIG["sector_rotation"]["is_active"]:
    rotation_signal = sector_rotation_signal(
        df_map=sector_data_map,  # construído a partir das barras
        spy_closes=spy_closes,
        config=MODULE_CONFIG["sector_rotation"],
        current_day_of_month=datetime.now(timezone.utc).day,
    )
    if rotation_signal["signal"] == "LONG" and rotation_signal["metadata"].get("type") == "rotation":
        # Executar rebalancing: fechar posições fora do top-N, abrir novas
        await _execute_rotation(rotation_signal, grid_engine, risk_manager, execution)
```

**CASOS DE TESTE:**

| Caso | Input | Esperado |
|---|---|---|
| Normal | SPY > SMA200, XLK=+15%, XLF=+12%, XLV=+10%, dia 1 | LONG conf=3, metadata.type="rotation", allocations=[XLK,XLF,XLV] |
| Edge (Bear) | SPY < SMA200, XLU=+5%, XLP=+3%, GLD=+8%, dia 1 | LONG conf=3, metadata.type="rotation", allocations=[GLD,XLU,XLP] |
| Fail (Not rebalance day) | Dia 15 | FLAT conf=0 |

---

### MÓDULO 7 — OVERNIGHT GAP FADE (`src/gap_fade.py`)

**STATUS:** Novo ficheiro | **Fase de capital:** 1 (€0-2k+)
**Prioridade:** 2º — independente, validação rápida

**PARÂMETROS DE CONFIGURAÇÃO:**
```python
GAP_FADE_CONFIG = {
    "is_active": True,                   # Activo desde Fase 1
    "min_gap_atr": 0.5,                  # Gap mínimo em ATR
    "max_gap_atr": 2.5,                  # Gap máximo em ATR (acima = gap continuation)
    "min_fill_probability": 0.60,        # Probabilidade mínima de fill
    "min_body_ratio_fade": 0.35,         # Body ratio máx para range fade
}
```

**FUNÇÕES A IMPLEMENTAR:**

```python
"""
Módulo 7: Overnight Gap Fade.

Opera gap fills quando o preço abre significativamente acima/abaixo
do fecho anterior. Faz fade (aposta no fecho do gap) em gaps de
magnitude moderada (0.5-2.5 ATR).

Fase de capital: 1+ (€0-2k)
"""

from __future__ import annotations

import logging
from typing import Any

from src.signal_engine import calculate_atr

logger = logging.getLogger(__name__)


def classify_gap(
    closes: list[float],
    opens: list[float],
    highs: list[float],
    lows: list[float],
    config: dict[str, Any],
) -> dict[str, Any]:
    """Classifica o gap de abertura e calcula probabilidade de fill.

    Magnitude do gap em ATR determina a probabilidade de fill:
    - < 0.5 ATR: ~85% fill rate → operar
    - 0.5-1.0 ATR: ~75% fill rate → operar com confidence 2+
    - 1.0-2.0 ATR: ~60% fill rate → operar só com confidence 3
    - > 2.0 ATR: ~40% fill rate → evitar (gap continuation)

    Args:
        closes: Preços de fecho (mín 15 barras).
        opens: Preços de abertura.
        highs: Preços máximos.
        lows: Preços mínimos.
        config: GAP_FADE_CONFIG.

    Returns:
        Dicionário com classificação do gap.
    """
    if len(closes) < 15 or len(opens) < 2:
        return {"valid": False, "reason": "insufficient_data"}

    prev_close = closes[-2]
    today_open = opens[-1]
    atr14 = calculate_atr(highs, lows, closes, 14)

    if atr14 is None or atr14 <= 0:
        return {"valid": False, "reason": "atr_invalid"}

    gap_pct = (today_open - prev_close) / prev_close * 100.0
    gap_atr = abs(today_open - prev_close) / atr14

    # Determinar fill probability pela magnitude ATR
    if gap_atr < 0.5:
        fill_probability = 0.85
    elif gap_atr < 1.0:
        fill_probability = 0.75
    elif gap_atr < 2.0:
        fill_probability = 0.60
    else:
        fill_probability = 0.40

    min_gap = config.get("min_gap_atr", 0.5)
    max_gap = config.get("max_gap_atr", 2.5)
    is_high_prob = min_gap <= gap_atr <= max_gap

    return {
        "valid": True,
        "gap_type": "up" if gap_pct > 0 else "down",
        "magnitude_pct": round(gap_pct, 4),
        "magnitude_atr": round(gap_atr, 4),
        "fill_probability": fill_probability,
        "is_high_prob": is_high_prob,
        "prev_close": prev_close,
        "today_open": today_open,
        "atr14": atr14,
    }


def gap_fade_signal(
    closes: list[float],
    opens: list[float],
    highs: list[float],
    lows: list[float],
    config: dict[str, Any],
) -> dict[str, Any]:
    """Gera sinal de gap fade se as condições forem satisfeitas.

    Lógica:
    - Gap up → SHORT (fade para prev_close)
    - Gap down → LONG (fade para prev_close)
    - Stop: extremo do gap + 0.5 ATR
    - TP: prev_close (target do fill)

    Args:
        closes: Preços de fecho.
        opens: Preços de abertura.
        highs: Preços máximos.
        lows: Preços mínimos.
        config: GAP_FADE_CONFIG.

    Returns:
        Signal dict no formato padrão do bot.
    """
    gap_info = classify_gap(closes, opens, highs, lows, config)

    if not gap_info.get("valid") or not gap_info.get("is_high_prob"):
        return _flat_signal({"reason": "gap_not_tradeable", "gap_info": gap_info})

    min_prob = config.get("min_fill_probability", 0.60)
    if gap_info["fill_probability"] < min_prob:
        return _flat_signal({"reason": "fill_prob_too_low"})

    atr = gap_info["atr14"]
    prev_close = gap_info["prev_close"]
    today_open = gap_info["today_open"]

    # Determinar confidence baseado na magnitude
    gap_atr = gap_info["magnitude_atr"]
    if gap_atr < 1.0:
        confidence = 3
    elif gap_atr < 2.0:
        confidence = 2
    else:
        confidence = 1  # Não opera (< 2)

    if confidence < 2:
        return _flat_signal({"reason": "confidence_too_low"})

    if gap_info["gap_type"] == "up":
        # Gap up → SHORT fade
        return {
            "signal": "SHORT",
            "confidence": confidence,
            "entry_price": today_open,
            "stop_loss": round(today_open + 0.5 * atr, 6),
            "take_profit": prev_close,
            "position_size": 0.0,
            "metadata": {"type": "gap_fade", "gap_info": gap_info, "module": "gap_fade"},
        }
    else:
        # Gap down → LONG fade
        return {
            "signal": "LONG",
            "confidence": confidence,
            "entry_price": today_open,
            "stop_loss": round(today_open - 0.5 * atr, 6),
            "take_profit": prev_close,
            "position_size": 0.0,
            "metadata": {"type": "gap_fade", "gap_info": gap_info, "module": "gap_fade"},
        }


def _flat_signal(metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    """Retorna sinal FLAT."""
    return {
        "signal": "FLAT",
        "confidence": 0,
        "entry_price": 0.0,
        "stop_loss": 0.0,
        "take_profit": 0.0,
        "position_size": 0.0,
        "metadata": metadata or {},
    }
```

**CASOS DE TESTE:**

| Caso | Input | Esperado |
|---|---|---|
| Normal | Gap up 0.8%, gap_atr=0.7, fill_prob=0.75 | SHORT conf=3, TP=prev_close |
| Edge | Gap down 2.3%, gap_atr=2.4, fill_prob=0.40 | FLAT (prob < 0.60) |
| Fail | Dados < 15 barras | FLAT (insufficient_data) |

---

### MÓDULO 1 — FOREX MEAN REVERSION (`src/forex_mr.py`)

**STATUS:** Novo ficheiro | **Fase de capital:** 2 (€2-10k)
**Prioridade:** 3º — depende de ADX helper (Secção 1)

**PARÂMETROS DE CONFIGURAÇÃO:**
```python
FOREX_MR_CONFIG = {
    "is_active": False,                  # Activo na Fase 2
    "pairs_by_phase": {
        1: ["EURUSD"],
        2: ["EURUSD", "GBPUSD"],
        3: ["EURUSD", "GBPUSD", "USDJPY"],
    },
    "z_entry": -2.0,                    # z-score mínimo para entrada
    "sma_period": 20,                   # SMA de 20 dias (NÃO usar SMA25 das acções)
    "vol_lookback": 60,                 # Lookback para desvio padrão
    "rsi_period": 2,                    # RSI(2) como trigger
    "rsi_entry": 10,                    # RSI(2) < 10 = oversold extremo
    "adx_ranging_max": 20.0,            # ADX < 20 → MR activo
    "adx_dead_max": 25.0,              # ADX 20-25 → zona morta
    "chop_min_ranging": 55.0,           # CHOP > 55 → ranging confirmado
    "max_trades_per_month": 6,
    "max_hold_days": 5,                 # Fase 1 cap
    "mr_grid_levels": 3,               # Grid de 3 níveis via grid_engine
    "mr_spacing_atr": 0.6,             # Espaçamento ATR × 0.6
    "stop_atr_mult_fx": 1.5,           # SL = 1.5 × ATR (FX)
    "weekend_gap_atr_mult": 1.5,
    "max_spread_atr_ratio": 3.0,
}
```

**FUNÇÕES A IMPLEMENTAR:**

```python
"""
Módulo 1: Forex Mean Reversion.

Detecta oportunidades de mean reversion em pares FX quando o preço
desvia significativamente da média (z-score ≤ -2.0) com confirmação
de regime ranging (ADX < 20, CHOP > 55).

Gate de activação: ADX < 20 (adormece quando ADX ≥ 20)
Fase de capital: 2+ (€2-10k)
"""

from __future__ import annotations

import logging
from typing import Any

from src.signal_engine import (
    calculate_adx,
    calculate_atr,
    calculate_choppiness_index,
    calculate_rsi,
    calculate_sma,
)

logger = logging.getLogger(__name__)


class ForexRegimeSwitch:
    """State machine para alternar entre MR e Breakout em FX.

    ADX < 20 → forex_mr activo
    ADX 20-25 → zona morta (nenhum opera)
    ADX > 25 → forex_breakout activo

    Histerese: quando muda de regime com posição aberta,
    aplica tighten_stop (apertar stop 50%) em vez de fechar.
    """

    ADX_MR_MAX: float = 20.0
    ADX_DEAD_MAX: float = 25.0

    def get_active_module(self, adx: float) -> str:
        """Determina qual módulo FX deve operar com base no ADX.

        Args:
            adx: Valor actual do ADX(14).

        Returns:
            'forex_mr', 'forex_breakout' ou 'none' (zona morta).
        """
        if adx < self.ADX_MR_MAX:
            return "forex_mr"
        if adx > self.ADX_DEAD_MAX:
            return "forex_breakout"
        return "none"

    def handle_open_position(self, position_module: str, new_regime: str) -> str:
        """Política quando o regime muda com posição aberta.

        Decisão (compromisso entre GPT/GEM/PPX):
        - MR → Breakout: tighten_stop (apertar stop 50%)
        - Breakout → MR: hold (deixar correr)

        Args:
            position_module: Módulo que abriu a posição ('forex_mr' ou 'forex_breakout').
            new_regime: Novo regime activo.

        Returns:
            'tighten_stop', 'hold' ou 'close'.
        """
        if position_module == "forex_mr" and new_regime == "forex_breakout":
            return "tighten_stop"
        if position_module == "forex_breakout" and new_regime == "forex_mr":
            return "hold"
        return "hold"


def forex_mr_signal(
    closes: list[float],
    highs: list[float],
    lows: list[float],
    config: dict[str, Any],
    now_utc_hour: int = 12,
) -> dict[str, Any]:
    """Gera sinal de mean reversion para pares FX.

    Condições de entrada:
    1. z-score ≤ -2.0 (desvio significativo abaixo da média)
    2. RSI(2) ≤ 10 (oversold extremo)

    Confirmações (mín 2 de 4 para confidence ≥ 2):
    1. Divergência RSI bullish (preço lower-low, RSI higher-low)
    2. Contracção de range ((H-L) actual < média 10d × 0.8)
    3. Sessão London/NY (07:00-17:00 UTC)
    4. ADX(14) < 20 AND CHOP > 55 (regime ranging forte)

    Args:
        closes: Preços de fecho (mín 60 barras).
        highs: Preços máximos.
        lows: Preços mínimos.
        config: FOREX_MR_CONFIG.
        now_utc_hour: Hora UTC actual (para filtro de sessão).

    Returns:
        Signal dict no formato padrão do bot.
    """
    sma_period = config.get("sma_period", 20)
    vol_lookback = config.get("vol_lookback", 60)
    z_entry = config.get("z_entry", -2.0)
    rsi_period = config.get("rsi_period", 2)
    rsi_entry = config.get("rsi_entry", 10)
    adx_max = config.get("adx_ranging_max", 20.0)
    chop_min = config.get("chop_min_ranging", 55.0)
    stop_mult = config.get("stop_atr_mult_fx", 1.5)

    n = min(len(closes), len(highs), len(lows))
    if n < vol_lookback:
        return _flat_signal({"reason": "insufficient_data"})

    close = closes[-1]
    sma = calculate_sma(closes, sma_period)
    if sma is None or sma <= 0:
        return _flat_signal({"reason": "sma_invalid"})

    # Calcular z-score
    janela = closes[-vol_lookback:]
    mean = sum(janela) / len(janela)
    std = (sum((x - mean) ** 2 for x in janela) / len(janela)) ** 0.5
    z_score = (close - sma) / std if std > 0 else 0.0

    # RSI(2)
    rsi2 = calculate_rsi(closes, period=rsi_period)

    # Verificar condições base
    if z_score > z_entry or rsi2 is None or rsi2 > rsi_entry:
        return _flat_signal({"reason": "base_conditions_not_met", "z_score": z_score, "rsi2": rsi2})

    # ATR para stop/TP
    atr = calculate_atr(highs, lows, closes, 14)
    if atr is None or atr <= 0:
        return _flat_signal({"reason": "atr_invalid"})

    # Confirmações (4 possíveis)
    confirmations = 0

    # 1. Divergência RSI bullish (simplificada: RSI subindo enquanto preço desce)
    if len(closes) >= 10:
        price_lower = closes[-1] < min(closes[-10:-1])
        rsi_recent = [calculate_rsi(closes[:i+1], rsi_period) for i in range(len(closes)-5, len(closes))]
        rsi_valid = [r for r in rsi_recent if r is not None]
        rsi_higher = len(rsi_valid) >= 2 and rsi_valid[-1] > rsi_valid[0]
        if price_lower and rsi_higher:
            confirmations += 1

    # 2. Contracção de range
    if len(highs) >= 10 and len(lows) >= 10:
        current_range = highs[-1] - lows[-1]
        avg_range_10 = sum(highs[i] - lows[i] for i in range(-10, 0)) / 10
        if current_range < avg_range_10 * 0.8:
            confirmations += 1

    # 3. Sessão London/NY (07:00-17:00 UTC)
    if 7 <= now_utc_hour <= 17:
        confirmations += 1

    # 4. ADX < 20 AND CHOP > 55
    adx = calculate_adx(highs, lows, closes, 14)
    chop = calculate_choppiness_index(highs, lows, closes, 14)
    if adx < adx_max and chop > chop_min:
        confirmations += 1

    confidence = min(confirmations, 3)
    if confidence < 2:
        return _flat_signal({"reason": "insufficient_confirmations", "confirmations": confirmations})

    return {
        "signal": "LONG",
        "confidence": confidence,
        "entry_price": close,
        "stop_loss": round(close - stop_mult * atr, 6),
        "take_profit": round(sma, 6),  # Regressão à média
        "position_size": 0.0,  # Calculado pelo risk_manager
        "metadata": {
            "z_score": round(z_score, 4),
            "rsi2": round(rsi2, 2) if rsi2 else None,
            "adx": round(adx, 2),
            "chop": round(chop, 2),
            "confirmations": confirmations,
            "module": "forex_mr",
        },
    }


def forex_kill_switches(
    highs: list[float],
    lows: list[float],
    closes: list[float],
    now_weekday: int,
    config: dict[str, Any],
) -> tuple[bool, list[str]]:
    """Kill switches específicos para FX.

    Verifica:
    1. Spread alargado proxy (range/ATR > 3.0)
    2. Gap de fim-de-semana (segunda-feira, gap > 1.5 ATR)

    Args:
        highs, lows, closes: Dados OHLC.
        now_weekday: Dia da semana (0=segunda, 6=domingo).
        config: FOREX_MR_CONFIG.

    Returns:
        (blocked, reasons) — blocked=True se algum kill switch activo.
    """
    reasons: list[str] = []
    atr = calculate_atr(highs, lows, closes, 14)
    if atr is None or atr <= 0:
        return True, ["atr_invalid"]

    # 1. Spread alargado
    today_range = highs[-1] - lows[-1]
    max_ratio = config.get("max_spread_atr_ratio", 3.0)
    if today_range / atr > max_ratio:
        reasons.append("spread_widening")

    # 2. Gap segunda-feira
    if now_weekday == 0 and len(closes) >= 2:
        gap = abs(closes[-1] - closes[-2])
        max_gap = config.get("weekend_gap_atr_mult", 1.5) * atr
        if gap > max_gap:
            reasons.append("weekend_gap")

    return len(reasons) > 0, reasons


def _flat_signal(metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    """Retorna sinal FLAT."""
    return {
        "signal": "FLAT", "confidence": 0, "entry_price": 0.0,
        "stop_loss": 0.0, "take_profit": 0.0, "position_size": 0.0,
        "metadata": metadata or {},
    }
```

**CASOS DE TESTE:**

| Caso | Input | Esperado |
|---|---|---|
| Normal | EUR/USD z=-2.1, RSI2=8, ADX=15, CHOP=62, 3 conf | LONG conf=3 |
| Edge | z=-2.1 mas ADX=28 (trending) | FLAT (regime_not_ranging) |
| Fail | Kill switch: spread_widening activo | FLAT (blocked) |

---

### MÓDULO 2 — FOREX BREAKOUT & RANGE FADE (`src/forex_breakout.py`)

**STATUS:** Novo ficheiro | **Fase de capital:** 2+ (€2-10k)
**Prioridade:** 4º — depende do Módulo 1

**PARÂMETROS DE CONFIGURAÇÃO:**
```python
FOREX_BREAKOUT_CONFIG = {
    "is_active": False,
    "adx_breakout_min": 25.0,
    "min_body_ratio": 0.60,
    "min_days_in_range": 15,
    "max_range_atr_mult": 3.0,
    "tp_atr_mult": 2.0,
    "range_quality_min": 0.6,
    "pyramid_enabled": True,
    "pyramid_max_adds": 2,
    "pyramid_trigger_atr": [1.0, 2.0],
    "pyramid_trail_stop_atr": 2.0,
}
```

**FUNÇÕES A IMPLEMENTAR:**

```python
"""
Módulo 2: Forex Breakout & Range Fade.

Detecta ranges consolidados e opera breakouts (ADX > 25) ou range fades
(falsos breakouts que regressam ao range).

Gate de activação: ADX > 25 (Módulo 1 adormece, Módulo 2 activa)
Fase de capital: 2+ (€2-10k)
"""

from __future__ import annotations

import logging
from typing import Any

from src.signal_engine import calculate_adx, calculate_atr

logger = logging.getLogger(__name__)


def detect_forex_range(
    highs: list[float],
    lows: list[float],
    closes: list[float],
    config: dict[str, Any],
) -> dict[str, Any]:
    """Detecta se o preço está num range consolidado.

    Validação:
    - Range size ≤ max_range_atr_mult × ATR14
    - ADX < 20 durante todo o lookback
    - Quality score ≥ 0.6 (% de fechos dentro do range com buffer)

    Args:
        highs, lows, closes: Dados OHLC (mín 20 barras).
        config: FOREX_BREAKOUT_CONFIG.

    Returns:
        Dicionário com informação do range detectado.
    """
    lookback = config.get("min_days_in_range", 15)
    adx_max = 20.0
    atr_mult = config.get("max_range_atr_mult", 3.0)
    quality_min = config.get("range_quality_min", 0.6)

    n = min(len(highs), len(lows), len(closes))
    if n < lookback + 14:
        return {"valid": False, "reason": "insufficient_data"}

    atr14 = calculate_atr(highs, lows, closes, 14)
    if atr14 is None or atr14 <= 0:
        return {"valid": False, "reason": "atr_invalid"}

    recent_highs = highs[-lookback:]
    recent_lows = lows[-lookback:]
    recent_closes = closes[-lookback:]

    range_high = max(recent_highs)
    range_low = min(recent_lows)
    range_size = range_high - range_low

    range_ok = range_size <= atr_mult * atr14

    # ADX < 20 durante o lookback
    adx = calculate_adx(highs, lows, closes, 14)
    adx_ok = adx < adx_max

    # Quality score: % de fechos dentro do range (com buffer 10%)
    buffer = 0.1 * range_size
    inside_count = sum(
        1 for c in recent_closes
        if range_low + buffer <= c <= range_high - buffer
    )
    quality_score = inside_count / len(recent_closes) if recent_closes else 0.0

    valid = range_ok and adx_ok and quality_score >= quality_min

    return {
        "valid": bool(valid),
        "upper": round(range_high, 6),
        "lower": round(range_low, 6),
        "quality_score": round(quality_score, 4),
        "days_in_range": lookback,
        "adx": round(adx, 2),
        "atr14": atr14,
    }


def generate_breakout_signal(
    closes: list[float],
    opens: list[float],
    highs: list[float],
    lows: list[float],
    range_info: dict[str, Any],
    config: dict[str, Any],
) -> dict[str, Any]:
    """Gera sinal de breakout ou range fade.

    Breakout válido:
    - Close > range_high (ou < range_low)
    - Body ratio ≥ 0.60 (vela forte)
    - Move ≥ 1.0 ATR desde a boundary

    Range Fade:
    - Preço toca boundary mas fecha dentro do range
    - Body ratio < 0.35 (vela fraca → reversão)

    Args:
        closes, opens, highs, lows: Dados OHLC.
        range_info: Resultado de detect_forex_range().
        config: FOREX_BREAKOUT_CONFIG.

    Returns:
        Signal dict no formato padrão do bot.
    """
    if not range_info.get("valid"):
        return _flat_signal({"reason": "range_invalid"})

    close = closes[-1]
    open_ = opens[-1]
    atr14 = range_info.get("atr14", 0.0)
    if atr14 <= 0:
        return _flat_signal({"reason": "atr_invalid"})

    body = abs(close - open_)
    day_range = highs[-1] - lows[-1]
    body_ratio = body / day_range if day_range > 0 else 0.0

    high_n = range_info["upper"]
    low_n = range_info["lower"]
    min_body = config.get("min_body_ratio", 0.60)
    tp_mult = config.get("tp_atr_mult", 2.0)

    # Breakout LONG
    if close > high_n and body_ratio >= min_body and (close - high_n) >= 1.0 * atr14:
        return {
            "signal": "LONG", "confidence": 2,
            "entry_price": close,
            "stop_loss": round(low_n, 6),
            "take_profit": round(close + tp_mult * atr14, 6),
            "position_size": 0.0,
            "metadata": {"type": "breakout", "body_ratio": round(body_ratio, 4), "module": "forex_breakout"},
        }

    # Breakout SHORT
    if close < low_n and body_ratio >= min_body and (low_n - close) >= 1.0 * atr14:
        return {
            "signal": "SHORT", "confidence": 2,
            "entry_price": close,
            "stop_loss": round(high_n, 6),
            "take_profit": round(close - tp_mult * atr14, 6),
            "position_size": 0.0,
            "metadata": {"type": "breakout", "body_ratio": round(body_ratio, 4), "module": "forex_breakout"},
        }

    # Range Fade (falso breakout)
    if highs[-1] > high_n and close < high_n and body_ratio < 0.35:
        midline = (high_n + low_n) / 2
        return {
            "signal": "SHORT", "confidence": 2,
            "entry_price": close,
            "stop_loss": round(highs[-1] + 0.5 * atr14, 6),
            "take_profit": round(midline, 6),
            "position_size": 0.0,
            "metadata": {"type": "range_fade", "module": "forex_breakout"},
        }

    if lows[-1] < low_n and close > low_n and body_ratio < 0.35:
        midline = (high_n + low_n) / 2
        return {
            "signal": "LONG", "confidence": 2,
            "entry_price": close,
            "stop_loss": round(lows[-1] - 0.5 * atr14, 6),
            "take_profit": round(midline, 6),
            "position_size": 0.0,
            "metadata": {"type": "range_fade", "module": "forex_breakout"},
        }

    return _flat_signal({"reason": "no_breakout_or_fade"})


def _flat_signal(metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "signal": "FLAT", "confidence": 0, "entry_price": 0.0,
        "stop_loss": 0.0, "take_profit": 0.0, "position_size": 0.0,
        "metadata": metadata or {},
    }
```

**CASOS DE TESTE:**

| Caso | Input | Esperado |
|---|---|---|
| Normal (Breakout) | Close > range_high, body=0.7, move=1.2 ATR | LONG conf=2 |
| Edge (Dead zone) | ADX=22 | FLAT (range invalid, ADX too high) |
| Normal (Range Fade) | High > range_high, close < range_high, body=0.3 | SHORT conf=2 |

---

### MÓDULO 3 — MICRO FUTUROS: MEAN REVERSION (`src/futures_mr.py`)

**STATUS:** Novo ficheiro | **Fase de capital:** 2+ (€2-10k)
**Prioridade:** 5º — depende de Panama roll (complexo)

**PARÂMETROS DE CONFIGURAÇÃO:**
```python
FUTURES_MR_CONFIG = {
    "is_active": False,
    "kairi_thresholds": {
        "MES": -3.0, "MNQ": -3.5, "M2K": -4.0,
        "MYM": -2.5, "MGC": -5.0, "MCL": -8.0,
    },
    "sma_lookback": 25,
    "roll_days_before": 5,
    "overnight_margin_mult": 1.5,
    "min_equity_futures": 2000,
}
```

**FUNÇÕES A IMPLEMENTAR:**

```python
"""
Módulo 3: Micro Futuros Mean Reversion.

Aplica KAIRI adaptado (thresholds mais baixos que acções) a micro futuros
CME (MES, MNQ, M2K, MYM, MGC, MCL).

IMPORTANTE: KAIRI -25% NÃO SE APLICA A FUTUROS — usar thresholds específicos.

Fase de capital: 2+ (€2-10k)
"""

from __future__ import annotations

import logging
from typing import Any

from src.signal_engine import calculate_atr, calculate_rsi, calculate_sma

logger = logging.getLogger(__name__)


def handle_futures_roll(
    closes_front: list[float],
    closes_next: list[float],
    highs_front: list[float],
    lows_front: list[float],
    highs_next: list[float],
    lows_next: list[float],
    opens_front: list[float],
    opens_next: list[float],
    roll_index: int,
) -> dict[str, list[float]]:
    """Ajuste de Panama para série contínua no roll de futuros.

    Elimina a descontinuidade OHLCV quando o contrato rola do front
    para o next month. Calcula o gap no ponto de roll e ajusta
    retroactivamente toda a série do contrato antigo.

    Args:
        closes_front: Fecho do contrato que expira.
        closes_next: Fecho do próximo contrato.
        highs/lows/opens_front: OHLC do contrato que expira.
        highs/lows/opens_next: OHLC do próximo contrato.
        roll_index: Índice na série onde ocorre o roll.

    Returns:
        Dicionário com séries ajustadas: close, high, low, open.
    """
    if roll_index < 0 or roll_index >= min(len(closes_front), len(closes_next)):
        logger.warning("Índice de roll inválido: %d", roll_index)
        return {
            "close": closes_front, "high": highs_front,
            "low": lows_front, "open": opens_front,
        }

    gap = closes_next[roll_index] - closes_front[roll_index]

    adjusted_close = [c + gap for c in closes_front[:roll_index + 1]] + list(closes_next[roll_index + 1:])
    adjusted_high = [h + gap for h in highs_front[:roll_index + 1]] + list(highs_next[roll_index + 1:])
    adjusted_low = [l + gap for l in lows_front[:roll_index + 1]] + list(lows_next[roll_index + 1:])
    adjusted_open = [o + gap for o in opens_front[:roll_index + 1]] + list(opens_next[roll_index + 1:])

    logger.info("Panama adjustment aplicado: gap=%.4f no índice %d.", gap, roll_index)
    return {
        "close": adjusted_close, "high": adjusted_high,
        "low": adjusted_low, "open": adjusted_open,
    }


def check_overnight_safety(
    equity: float,
    margin_req: float,
    config: dict[str, Any],
) -> bool:
    """Verifica se é seguro manter posição overnight em futuros.

    Fase 1 (€0-2k): proibido overnight (capital insuficiente).
    Fase 2+: equity ≥ 1.5 × margem overnight.

    Args:
        equity: Capital actual em EUR.
        margin_req: Margem overnight estimada do contrato.
        config: FUTURES_MR_CONFIG.

    Returns:
        True se overnight é seguro.
    """
    min_equity = config.get("min_equity_futures", 2000)
    if equity < min_equity:
        return False
    mult = config.get("overnight_margin_mult", 1.5)
    return equity >= margin_req * mult


def futures_mr_signal(
    symbol: str,
    closes: list[float],
    highs: list[float],
    lows: list[float],
    config: dict[str, Any],
) -> dict[str, Any]:
    """Gera sinal de mean reversion para micro futuros.

    Usa KAIRI com thresholds adaptados por contrato (muito mais baixos
    que os -25% das acções).

    Args:
        symbol: Símbolo do futuro (MES, MNQ, etc.).
        closes, highs, lows: Dados OHLC.
        config: FUTURES_MR_CONFIG.

    Returns:
        Signal dict no formato padrão do bot.
    """
    thresholds = config.get("kairi_thresholds", {})
    kairi_threshold = thresholds.get(symbol, -3.0)
    sma_lookback = config.get("sma_lookback", 25)

    if len(closes) < sma_lookback + 14:
        return _flat_signal({"reason": "insufficient_data"})

    price = closes[-1]
    sma = calculate_sma(closes, sma_lookback)
    if sma is None or sma <= 0:
        return _flat_signal({"reason": "sma_invalid"})

    kairi = ((price - sma) / sma) * 100.0
    rsi14 = calculate_rsi(closes, 14)
    atr = calculate_atr(highs, lows, closes, 14)

    if atr is None or atr <= 0:
        return _flat_signal({"reason": "atr_invalid"})

    if kairi > kairi_threshold:
        return _flat_signal({"reason": "kairi_above_threshold", "kairi": kairi})

    # RSI < 30 como confirmação (adaptado de acções)
    confidence = 2
    if rsi14 is not None and rsi14 < 30:
        confidence = 3

    return {
        "signal": "LONG",
        "confidence": confidence,
        "entry_price": price,
        "stop_loss": round(price - 1.0 * atr, 6),
        "take_profit": round(price + 2.5 * atr, 6),
        "position_size": 0.0,
        "metadata": {
            "kairi": round(kairi, 4),
            "rsi14": round(rsi14, 2) if rsi14 else None,
            "threshold": kairi_threshold,
            "module": "futures_mr",
        },
    }


def _flat_signal(metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "signal": "FLAT", "confidence": 0, "entry_price": 0.0,
        "stop_loss": 0.0, "take_profit": 0.0, "position_size": 0.0,
        "metadata": metadata or {},
    }
```

**CASOS DE TESTE:**

| Caso | Input | Esperado |
|---|---|---|
| Normal | MES KAIRI=-3.2, RSI=28, equity=3k | LONG conf=3 |
| Edge | Equity < margin×1.5 | overnight blocked |
| Fail | Roll date → usar série ajustada | Panama adjustment applied |

---

### MÓDULO 5 — ETFs INTERNACIONAIS (`src/intl_etf_mr.py`)

**STATUS:** Novo ficheiro | **Fase de capital:** 3 (€10-25k)
**Prioridade:** 6º — depende de correlation check (Secção 1)

**PARÂMETROS DE CONFIGURAÇÃO:**
```python
INTL_ETF_MR_CONFIG = {
    "is_active": False,
    "kairi_thresholds": {
        "EWG": -20.0, "EWU": -20.0, "EWJ": -15.0,
        "EEM": -25.0, "FXI": -25.0,
    },
    "sma_lookback": 25,
    "max_correlation": 0.70,
    "correlation_lookback": 60,
    "min_equity": 10000,
}
```

**FUNÇÕES A IMPLEMENTAR:**

```python
"""
Módulo 5: ETFs Internacionais — KAIRI Mean Reversion.

Aplica a mesma lógica Kotegawa do core mas com thresholds adaptados
por região geográfica. Inclui filtro de correlação para evitar
concentração excessiva em activos correlacionados.

Fase de capital: 3+ (€10-25k)
"""

from __future__ import annotations

import logging
from typing import Any

from src.risk_manager import check_correlation_limit
from src.signal_engine import calculate_atr, calculate_rsi, calculate_sma

logger = logging.getLogger(__name__)


def intl_etf_signal(
    symbol: str,
    closes: list[float],
    highs: list[float],
    lows: list[float],
    volumes: list[float],
    open_positions: list[str],
    returns_map: dict[str, list[float]],
    config: dict[str, Any],
) -> dict[str, Any]:
    """Gera sinal KAIRI MR para ETFs internacionais.

    Lógica idêntica ao core Kotegawa mas com:
    - Thresholds KAIRI adaptados por ETF/região
    - Filtro de correlação (máx 70% com posições abertas)

    Args:
        symbol: Símbolo do ETF (EWG, EWU, EWJ, etc.).
        closes, highs, lows, volumes: Dados OHLCV.
        open_positions: Lista de símbolos com posição aberta.
        returns_map: Retornos diários para cálculo de correlação.
        config: INTL_ETF_MR_CONFIG.

    Returns:
        Signal dict no formato padrão do bot.
    """
    thresholds = config.get("kairi_thresholds", {})
    kairi_threshold = thresholds.get(symbol, -25.0)
    sma_lookback = config.get("sma_lookback", 25)
    max_corr = config.get("max_correlation", 0.70)
    corr_lookback = config.get("correlation_lookback", 60)

    if len(closes) < 200:
        return _flat_signal({"reason": "insufficient_data"})

    price = closes[-1]
    sma25 = calculate_sma(closes, sma_lookback)
    if sma25 is None or sma25 <= 0:
        return _flat_signal({"reason": "sma_invalid"})

    kairi = ((price - sma25) / sma25) * 100.0
    if kairi > kairi_threshold:
        return _flat_signal({"reason": "kairi_above_threshold", "kairi": kairi})

    # Verificar correlação
    if not check_correlation_limit(symbol, open_positions, returns_map, max_corr, corr_lookback):
        return _flat_signal({"reason": "correlation_too_high"})

    rsi14 = calculate_rsi(closes, 14)
    atr = calculate_atr(highs, lows, closes, 14)
    if atr is None or rsi14 is None:
        return _flat_signal({"reason": "indicator_invalid"})

    # Confirmações (mesma lógica Kotegawa)
    confirmations = 0
    if rsi14 < 30:
        confirmations += 1
    from src.signal_engine import calculate_bollinger_bands
    bb = calculate_bollinger_bands(closes, 20, 2.0)
    if bb is not None and price < bb[2]:  # abaixo da banda inferior
        confirmations += 1
    from src.signal_engine import calculate_volume_avg
    vol_avg = calculate_volume_avg(volumes, 20)
    if vol_avg is not None and volumes[-1] > 1.5 * vol_avg:
        confirmations += 1

    if confirmations < 1:
        return _flat_signal({"reason": "no_confirmations"})

    confidence = min(confirmations, 3)

    return {
        "signal": "LONG",
        "confidence": confidence,
        "entry_price": price,
        "stop_loss": round(price - 1.0 * atr, 6),
        "take_profit": round(price + 2.5 * atr, 6),
        "position_size": 0.0,
        "metadata": {
            "kairi": round(kairi, 4),
            "rsi14": round(rsi14, 2),
            "threshold": kairi_threshold,
            "module": "intl_etf_mr",
        },
    }


def _flat_signal(metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "signal": "FLAT", "confidence": 0, "entry_price": 0.0,
        "stop_loss": 0.0, "take_profit": 0.0, "position_size": 0.0,
        "metadata": metadata or {},
    }
```

---

### MÓDULO 8 — ETFs DE COMMODITIES (`src/commodity_mr.py`)

**STATUS:** Novo ficheiro | **Fase de capital:** 2/3 (€2-10k+)
**Prioridade:** 7º

**PARÂMETROS DE CONFIGURAÇÃO:**
```python
COMMODITY_MR_CONFIG = {
    "is_active": False,
    "thresholds": {
        "GLD": {"kairi_long": -10.0, "kairi_short": 10.0, "sma": 50, "enabled": True},
        "IAU": {"kairi_long": -10.0, "kairi_short": 10.0, "sma": 50, "enabled": True},
        "SLV": {"kairi_long": -15.0, "kairi_short": 15.0, "sma": 25, "enabled": True},
        "USO": {"kairi_long": -35.0, "kairi_short": 20.0, "sma": 25, "enabled": True},
        "PDBC": {"kairi_long": -20.0, "kairi_short": 20.0, "sma": 25, "enabled": True},
        "UNG": {"enabled": False, "reason": "drag_contango_>30%/ano"},
    },
    "max_hold_days": 10,
}
```

**FUNÇÕES A IMPLEMENTAR:**

```python
"""
Módulo 8: ETFs de Commodities — KAIRI MR com thresholds assimétricos.

Thresholds LONG e SHORT separados por ETF para reflectir drag de contango
(USO: drag 10-30%/ano, UNG: DESQUALIFICADO >30%/ano).

Fase de capital: 2/3 (€2-10k+)
"""

from __future__ import annotations

import logging
from typing import Any

from src.signal_engine import calculate_atr, calculate_rsi, calculate_sma

logger = logging.getLogger(__name__)


def contango_drag_guard(
    symbol: str,
    config: dict[str, Any],
) -> dict[str, Any]:
    """Verifica se o ETF de commodity é permitido.

    UNG está permanentemente desqualificado (drag contango >30%/ano).
    Outros ETFs têm limites de holding adaptados.

    Args:
        symbol: Símbolo do ETF.
        config: COMMODITY_MR_CONFIG.

    Returns:
        Dicionário com allowed, max_hold_days, thresholds.
    """
    thresholds = config.get("thresholds", {})
    sym_config = thresholds.get(symbol, {})

    if not sym_config.get("enabled", True):
        return {"allowed": False, "reason": sym_config.get("reason", "disabled")}

    return {
        "allowed": True,
        "max_hold_days": config.get("max_hold_days", 10),
        "kairi_long": sym_config.get("kairi_long", -25.0),
        "kairi_short": sym_config.get("kairi_short", 25.0),
        "sma_period": sym_config.get("sma", 25),
    }


def commodity_mr_signal(
    symbol: str,
    closes: list[float],
    highs: list[float],
    lows: list[float],
    config: dict[str, Any],
) -> dict[str, Any]:
    """Gera sinal MR para ETFs de commodities com thresholds assimétricos.

    Args:
        symbol: Símbolo do ETF commodity.
        closes, highs, lows: Dados OHLC.
        config: COMMODITY_MR_CONFIG.

    Returns:
        Signal dict no formato padrão do bot.
    """
    guard = contango_drag_guard(symbol, config)
    if not guard.get("allowed"):
        return _flat_signal({"reason": guard.get("reason", "blocked")})

    sma_period = guard.get("sma_period", 25)
    kairi_long = guard.get("kairi_long", -25.0)

    if len(closes) < max(sma_period, 14) + 1:
        return _flat_signal({"reason": "insufficient_data"})

    price = closes[-1]
    sma = calculate_sma(closes, sma_period)
    if sma is None or sma <= 0:
        return _flat_signal({"reason": "sma_invalid"})

    kairi = ((price - sma) / sma) * 100.0
    if kairi > kairi_long:
        return _flat_signal({"reason": "kairi_above_threshold", "kairi": kairi})

    rsi14 = calculate_rsi(closes, 14)
    atr = calculate_atr(highs, lows, closes, 14)
    if atr is None:
        return _flat_signal({"reason": "atr_invalid"})

    confidence = 2
    if rsi14 is not None and rsi14 < 30:
        confidence = 3

    return {
        "signal": "LONG",
        "confidence": confidence,
        "entry_price": price,
        "stop_loss": round(price - 1.0 * atr, 6),
        "take_profit": round(price + 2.5 * atr, 6),
        "position_size": 0.0,
        "metadata": {
            "kairi": round(kairi, 4),
            "threshold": kairi_long,
            "module": "commodity_mr",
        },
    }


def _flat_signal(metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "signal": "FLAT", "confidence": 0, "entry_price": 0.0,
        "stop_loss": 0.0, "take_profit": 0.0, "position_size": 0.0,
        "metadata": metadata or {},
    }
```

---

### MÓDULO 4 — MICRO FUTUROS: TREND FOLLOWING (`src/futures_trend.py`)

**STATUS:** Novo ficheiro | **Fase de capital:** 3 (€10-25k)
**Prioridade:** 8º — depende do Módulo 3 + ADX

**PARÂMETROS DE CONFIGURAÇÃO:**
```python
FUTURES_TREND_CONFIG = {
    "is_active": False,
    "adx_min": 25.0,
    "params_by_type": {
        "indices": {"ema_fast": 20, "ema_slow": 50, "donchian_period": 20},
        "metals": {"ema_fast": 10, "ema_slow": 30},
        "energy": {"ema_fast": 10, "ema_slow": 30, "adx_min": 30},
    },
    "chandelier_period": 22,
    "chandelier_atr_mult": 3.0,
    "pyramid_max_adds": 3,
    "pyramid_trigger_atr": 1.5,
    "min_equity": 10000,
}
```

**FUNÇÕES A IMPLEMENTAR:**

```python
"""
Módulo 4: Micro Futuros Trend Following.

Dual EMA 20/50 para índices, EMA 10/30 para metais/energia.
ADX > 25 obrigatório. Chandelier Exit como trailing stop.
Pyramiding até 3 adições (averaging UP, nunca down).

Gate de activação: ADX > 25 (Módulo 3 adormece, Módulo 4 activa)
Fase de capital: 3+ (€10-25k)
"""

from __future__ import annotations

import logging
from typing import Any

from src.signal_engine import calculate_adx, calculate_atr, calculate_ema

logger = logging.getLogger(__name__)


def calculate_chandelier_exit(
    highs: list[float],
    lows: list[float],
    closes: list[float],
    atr: float,
    period: int = 22,
    atr_mult: float = 3.0,
    direction: str = "LONG",
) -> float:
    """Calcula o Chandelier Exit como trailing stop.

    LONG: highest_close(N) - atr_mult × ATR
    SHORT: lowest_close(N) + atr_mult × ATR

    Args:
        highs, lows, closes: Dados OHLC.
        atr: Valor actual do ATR.
        period: Lookback para highest/lowest (defeito 22).
        atr_mult: Multiplicador ATR (defeito 3.0).
        direction: 'LONG' ou 'SHORT'.

    Returns:
        Preço do Chandelier Exit.
    """
    recent_closes = closes[-period:] if len(closes) >= period else closes
    if direction == "LONG":
        return max(recent_closes) - atr_mult * atr
    return min(recent_closes) + atr_mult * atr


def calculate_pyramid_entry(
    entry_price: float,
    current_price: float,
    atr: float,
    units_held: int,
    signal_direction: str,
    config: dict[str, Any],
) -> dict[str, Any]:
    """Calcula se deve adicionar uma unidade de pyramid (averaging UP).

    Averaging UP: adiciona posição quando preço move a favor em N×ATR.
    NUNCA averaging down.

    Args:
        entry_price: Preço de entrada original.
        current_price: Preço actual.
        atr: ATR actual.
        units_held: Unidades já detidas.
        signal_direction: 'LONG' ou 'SHORT'.
        config: FUTURES_TREND_CONFIG.

    Returns:
        Dicionário com add_unit (bool), novo stop (break-even).
    """
    max_pyramid = config.get("pyramid_max_adds", 3)
    trigger_atr = config.get("pyramid_trigger_atr", 1.5)

    if units_held >= max_pyramid:
        return {"add_unit": False}

    is_long = signal_direction == "LONG"
    profit_distance = (current_price - entry_price) if is_long else (entry_price - current_price)

    if profit_distance > trigger_atr * atr:
        # Mover stop para break-even
        new_stop = entry_price + 0.5 * atr if is_long else entry_price - 0.5 * atr
        return {
            "add_unit": True,
            "entry_price": current_price,
            "stop_loss": round(new_stop, 6),
        }

    return {"add_unit": False}


def futures_trend_signal(
    symbol: str,
    closes: list[float],
    highs: list[float],
    lows: list[float],
    symbol_type: str,
    config: dict[str, Any],
) -> dict[str, Any]:
    """Gera sinal de trend following para micro futuros.

    Dual EMA crossover + ADX > 25 como filtro de regime.

    Args:
        symbol: Símbolo do futuro.
        closes, highs, lows: Dados OHLC.
        symbol_type: 'indices', 'metals' ou 'energy'.
        config: FUTURES_TREND_CONFIG.

    Returns:
        Signal dict no formato padrão do bot.
    """
    params = config.get("params_by_type", {}).get(symbol_type, {})
    ema_fast_period = params.get("ema_fast", 20)
    ema_slow_period = params.get("ema_slow", 50)
    adx_min = params.get("adx_min", config.get("adx_min", 25.0))

    if len(closes) < ema_slow_period + 14:
        return _flat_signal({"reason": "insufficient_data"})

    ema_fast = calculate_ema(closes, ema_fast_period)
    ema_slow = calculate_ema(closes, ema_slow_period)
    adx = calculate_adx(highs, lows, closes, 14)
    atr = calculate_atr(highs, lows, closes, 14)

    if any(v is None for v in (ema_fast, ema_slow, atr)):
        return _flat_signal({"reason": "indicator_invalid"})

    if adx < adx_min:
        return _flat_signal({"reason": "adx_below_threshold", "adx": adx})

    price = closes[-1]
    chandelier_period = config.get("chandelier_period", 22)
    chandelier_mult = config.get("chandelier_atr_mult", 3.0)

    if ema_fast > ema_slow:  # Bullish crossover
        stop = calculate_chandelier_exit(highs, lows, closes, atr, chandelier_period, chandelier_mult, "LONG")
        return {
            "signal": "LONG", "confidence": 2,
            "entry_price": price,
            "stop_loss": round(stop, 6),
            "take_profit": round(price + 3.0 * atr, 6),
            "position_size": 0.0,
            "metadata": {"ema_fast": ema_fast, "ema_slow": ema_slow, "adx": round(adx, 2), "module": "futures_trend"},
        }

    if ema_fast < ema_slow:  # Bearish crossover
        stop = calculate_chandelier_exit(highs, lows, closes, atr, chandelier_period, chandelier_mult, "SHORT")
        return {
            "signal": "SHORT", "confidence": 2,
            "entry_price": price,
            "stop_loss": round(stop, 6),
            "take_profit": round(price - 3.0 * atr, 6),
            "position_size": 0.0,
            "metadata": {"ema_fast": ema_fast, "ema_slow": ema_slow, "adx": round(adx, 2), "module": "futures_trend"},
        }

    return _flat_signal({"reason": "no_crossover"})


def _flat_signal(metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "signal": "FLAT", "confidence": 0, "entry_price": 0.0,
        "stop_loss": 0.0, "take_profit": 0.0, "position_size": 0.0,
        "metadata": metadata or {},
    }
```

---

### MÓDULO 10 — FIXED INCOME & BONDS (`src/bond_mr_hedge.py`)

**STATUS:** Novo ficheiro | **Fase de capital:** 2+ (€2-10k)
**Prioridade:** 9º

**PARÂMETROS DE CONFIGURAÇÃO:**
```python
BOND_MR_HEDGE_CONFIG = {
    "is_active": False,
    "min_equity_eur": 2000,
    "kairi_thresholds": {"TLT": -15.0, "IEF": -10.0, "SHY": -7.0, "LQD": -15.0},
    "max_allocation_pct": 0.20,
    "defensive_min_days": 10,
    "bear_vix_proxy": 25.0,
    "correlation_lookback": 60,
}
```

**FUNÇÕES A IMPLEMENTAR:**

```python
"""
Módulo 10: Fixed Income & Bonds — MR táctico + hedge defensivo.

Duas vertentes:
1. MR táctico: KAIRI em TLT/IEF quando bonds estão sobrevendidos
2. Rotação defensiva: SPY < SMA200 + VIX > 25 → rodar para bonds

Anti-whipsaw: mínimo 10 dias em modo defensivo.

Fase de capital: 2+ (€2-10k)
"""

from __future__ import annotations

import logging
from typing import Any

from src.signal_engine import calculate_atr, calculate_rsi, calculate_sma

logger = logging.getLogger(__name__)


def detect_stock_bond_correlation_regime(
    spy_closes: list[float],
    tlt_closes: list[float],
    lookback: int = 60,
) -> str:
    """Detecta o regime de correlação stocks/bonds.

    Correlação negativa (< -0.2): bonds são hedge eficaz (deflação/recessão)
    Correlação positiva (> 0.2): bonds NÃO protegem (inflação, 2022)
    Transição (-0.2 a 0.2): incerto, reduzir alocação

    Args:
        spy_closes: Fechos do SPY.
        tlt_closes: Fechos do TLT.
        lookback: Janela de cálculo (60 dias).

    Returns:
        'negative', 'positive' ou 'transitioning'.
    """
    min_len = min(len(spy_closes), len(tlt_closes))
    if min_len < lookback + 1:
        return "transitioning"

    spy_ret = [spy_closes[i] / spy_closes[i-1] - 1 for i in range(-lookback, 0)]
    tlt_ret = [tlt_closes[i] / tlt_closes[i-1] - 1 for i in range(-lookback, 0)]

    n = len(spy_ret)
    mean_s = sum(spy_ret) / n
    mean_t = sum(tlt_ret) / n
    import math
    cov = sum((a - mean_s) * (b - mean_t) for a, b in zip(spy_ret, tlt_ret)) / n
    std_s = math.sqrt(sum((a - mean_s) ** 2 for a in spy_ret) / n)
    std_t = math.sqrt(sum((b - mean_t) ** 2 for b in tlt_ret) / n)

    if std_s == 0 or std_t == 0:
        return "transitioning"

    corr = cov / (std_s * std_t)

    if corr < -0.2:
        return "negative"
    if corr > 0.2:
        return "positive"
    return "transitioning"


def check_defensive_rotation_trigger(
    spy_closes: list[float],
    vix_proxy: float,
    correlation_regime: str,
    defensive_state: dict[str, Any],
    config: dict[str, Any],
) -> str:
    """Verifica se deve entrar/sair do modo defensivo.

    NORMAL → DEFENSIVE: SPY < SMA200 + VIX > 25 + correlação negativa
    DEFENSIVE → NORMAL: SPY > SMA200 + mín 10 dias em defensivo

    Args:
        spy_closes: Fechos do SPY.
        vix_proxy: Proxy de volatilidade.
        correlation_regime: Resultado de detect_stock_bond_correlation_regime().
        defensive_state: {'mode': 'NORMAL'|'DEFENSIVE', 'days_in_defensive': int}
        config: BOND_MR_HEDGE_CONFIG.

    Returns:
        'ENTER_DEFENSIVE', 'EXIT_DEFENSIVE' ou 'NO_CHANGE'.
    """
    sma200 = calculate_sma(spy_closes, 200)
    if sma200 is None:
        return "NO_CHANGE"

    spy = spy_closes[-1]
    bear_vix = config.get("bear_vix_proxy", 25.0)
    min_days = config.get("defensive_min_days", 10)

    bear_condition = spy < sma200 and vix_proxy > bear_vix
    mode = defensive_state.get("mode", "NORMAL")

    if mode == "NORMAL":
        if bear_condition and correlation_regime == "negative":
            return "ENTER_DEFENSIVE"
    elif mode == "DEFENSIVE":
        days = defensive_state.get("days_in_defensive", 0)
        if spy > sma200 and days >= min_days:
            return "EXIT_DEFENSIVE"

    return "NO_CHANGE"


def bond_mr_signal(
    symbol: str,
    closes: list[float],
    highs: list[float],
    lows: list[float],
    spy_closes: list[float],
    tlt_closes: list[float],
    vix_proxy: float,
    defensive_state: dict[str, Any],
    config: dict[str, Any],
) -> dict[str, Any]:
    """Gera sinal MR táctico para bonds + rotação defensiva.

    Duas vertentes:
    1. MR táctico: KAIRI em TLT/IEF quando bonds estão sobrevendidos
    2. Rotação defensiva: SPY < SMA200 + VIX > 25 → rodar para bonds

    Args:
        symbol: Símbolo do bond ETF (TLT, IEF, SHY, LQD).
        closes, highs, lows: Dados OHLC do bond ETF.
        spy_closes: Fechos do SPY para filtro bear market.
        tlt_closes: Fechos do TLT para correlação stocks/bonds.
        vix_proxy: Proxy de volatilidade actual.
        defensive_state: {'mode': 'NORMAL'|'DEFENSIVE', 'days_in_defensive': int}
        config: BOND_MR_HEDGE_CONFIG.

    Returns:
        Signal dict no formato padrão do bot.
    """
    thresholds = config.get("kairi_thresholds", {})
    kairi_threshold = thresholds.get(symbol, -15.0)
    sma_lookback = 25

    if len(closes) < 200:
        return _flat_signal({"reason": "insufficient_data"})

    # Verificar correlação stocks/bonds
    corr_regime = detect_stock_bond_correlation_regime(
        spy_closes, tlt_closes, config.get("correlation_lookback", 60)
    )

    # Verificar trigger defensivo
    defensive_action = check_defensive_rotation_trigger(
        spy_closes, vix_proxy, corr_regime, defensive_state, config
    )

    # Modo defensivo: sinal LONG nos bonds
    if defensive_action == "ENTER_DEFENSIVE" or defensive_state.get("mode") == "DEFENSIVE":
        atr = calculate_atr(highs, lows, closes, 14)
        if atr is None or atr <= 0:
            return _flat_signal({"reason": "atr_invalid"})
        price = closes[-1]
        return {
            "signal": "LONG",
            "confidence": 3,
            "entry_price": price,
            "stop_loss": round(price - 1.0 * atr, 6),
            "take_profit": round(price + 2.5 * atr, 6),
            "position_size": config.get("max_allocation_pct", 0.20),
            "metadata": {
                "type": "defensive_rotation",
                "corr_regime": corr_regime,
                "defensive_action": defensive_action,
                "module": "bond_mr_hedge",
            },
        }

    # MR táctico: KAIRI oversold em bonds
    price = closes[-1]
    sma = calculate_sma(closes, sma_lookback)
    if sma is None or sma <= 0:
        return _flat_signal({"reason": "sma_invalid"})

    kairi = ((price - sma) / sma) * 100.0
    if kairi > kairi_threshold:
        return _flat_signal({"reason": "kairi_above_threshold", "kairi": kairi})

    rsi14 = calculate_rsi(closes, 14)
    atr = calculate_atr(highs, lows, closes, 14)
    if atr is None:
        return _flat_signal({"reason": "atr_invalid"})

    confidence = 2
    if rsi14 is not None and rsi14 < 30:
        confidence = 3

    return {
        "signal": "LONG",
        "confidence": confidence,
        "entry_price": price,
        "stop_loss": round(price - 1.0 * atr, 6),
        "take_profit": round(sma, 6),
        "position_size": 0.0,
        "metadata": {
            "type": "tactical_mr",
            "kairi": round(kairi, 4),
            "threshold": kairi_threshold,
            "corr_regime": corr_regime,
            "module": "bond_mr_hedge",
        },
    }


def _flat_signal(metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "signal": "FLAT", "confidence": 0, "entry_price": 0.0,
        "stop_loss": 0.0, "take_profit": 0.0, "position_size": 0.0,
        "metadata": metadata or {},
    }
```

**CASOS DE TESTE — MÓDULO 10:**

| Caso | Input | Esperado |
|---|---|---|
| MR táctico (oversold) | TLT, KAIRI=-18%, RSI=25, corr=negative, mode=NORMAL | LONG conf=3, type=tactical_mr, TP=SMA25 |
| MR táctico (not oversold) | IEF, KAIRI=-5%, corr=negative, mode=NORMAL | FLAT reason=kairi_above_threshold |
| Defensivo (enter) | TLT, SPY<SMA200, VIX=28, corr=negative, mode=NORMAL | LONG conf=3, type=defensive_rotation, position_size=0.20 |
| Defensivo (manter) | IEF, mode=DEFENSIVE, days=5 | LONG conf=3, type=defensive_rotation |
| Defensivo (sair) | SHY, SPY>SMA200, mode=DEFENSIVE, days=15 | FLAT (via check_defensive_rotation_trigger) |
| Correlação positiva | TLT, corr=positive (inflação) | FLAT (bonds não protegem, regime 2022-style) |
| Dados insuficientes | LQD, len(closes)<200 | FLAT reason=insufficient_data |

---

### MÓDULO 9 — OPTIONS: PREMIUM SELLING (`src/options_premium.py`)

**STATUS:** Novo ficheiro | **Fase de capital:** 3+ (€25k mínimo — cash-secured exige colateral)
**Prioridade:** 10º — último, mais complexo (BSM + greeks)

**PARÂMETROS DE CONFIGURAÇÃO:**
```python
OPTIONS_PREMIUM_CONFIG = {
    "is_active": False,
    "min_equity": 25000,
    "target_delta": 0.15,
    "target_dte": 45,
    "close_at_profit_pct": 0.50,
    "close_at_dte": 21,
    "iv_rank_min": 30,
    "max_delta_phase4": 0.20,
    "allowed_symbols": ["SPY", "QQQ", "IWM"],
    "vix_max_sell": 30,
    "min_days_to_earnings": 21,
}
```

**FUNCOES A IMPLEMENTAR:**

```python
"""
Modulo 9: Options Premium Selling (Cash-Secured Puts).

Vende puts OTM em SPY/QQQ/IWM quando IV Rank >= 30 e nao ha earnings
proximos. Implementacao Black-Scholes SEM scipy -- usa math.erfc para
aproximacao de norm.cdf (Abramowitz & Stegun, erro < 1.5e-7).

Regras de saida:
- 50% lucro -> fechar imediatamente
- 21 DTE restantes -> fechar (gamma risk)
- IV Rank cai < 20 -> fechar (premium esgotado)

Fase de capital: 3+ (EUR 25k minimo -- cash-secured exige colateral)
"""

from __future__ import annotations

import logging
import math
from typing import Any

logger = logging.getLogger(__name__)


# ── Aproximacoes norm.cdf / norm.pdf sem scipy ──

def _norm_cdf(x: float) -> float:
    """CDF da normal padrao via math.erfc (Abramowitz & Stegun).

    Precisao: erro maximo < 1.5e-7. Suficiente para BSM.
    """
    return 0.5 * math.erfc(-x / math.sqrt(2))


def _norm_pdf(x: float) -> float:
    """PDF da normal padrao."""
    return math.exp(-0.5 * x * x) / math.sqrt(2 * math.pi)


class BlackScholes:
    """Black-Scholes-Merton para opcoes europeias."""

    @staticmethod
    def calculate_greeks(
        S: float,
        K: float,
        T: float,
        r: float,
        sigma: float,
        option_type: str = "put",
    ) -> dict[str, float]:
        """Calcula preco e greeks BSM.

        S=spot, K=strike, T=anos, r=taxa, sigma=vol implicita.
        Retorna {price, delta, gamma, theta, vega}.
        Retorna zeros se T<=0 ou sigma<=0.
        """
        if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
            return {"price": 0.0, "delta": 0.0, "gamma": 0.0, "theta": 0.0, "vega": 0.0}

        d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
        d2 = d1 - sigma * math.sqrt(T)

        if option_type == "call":
            price = S * _norm_cdf(d1) - K * math.exp(-r * T) * _norm_cdf(d2)
            delta = _norm_cdf(d1)
        else:  # put
            price = K * math.exp(-r * T) * _norm_cdf(-d2) - S * _norm_cdf(-d1)
            delta = _norm_cdf(d1) - 1.0

        gamma = _norm_pdf(d1) / (S * sigma * math.sqrt(T))
        theta = (
            -(S * _norm_pdf(d1) * sigma) / (2 * math.sqrt(T))
            - r * K * math.exp(-r * T) * _norm_cdf(-d2)
        ) / 365.0
        vega = S * _norm_pdf(d1) * math.sqrt(T) / 100.0

        return {
            "price": round(price, 6),
            "delta": round(delta, 6),
            "gamma": round(gamma, 6),
            "theta": round(theta, 6),
            "vega": round(vega, 6),
        }


def should_sell_premium(
    regime: str,
    iv_rank: float,
    days_to_earnings: int,
    vix_proxy: float,
    config: dict[str, Any],
) -> bool:
    """Gates para venda de premium: True = pode vender.

    Condicoes: regime SIDEWAYS/BULL, iv_rank>=30,
    days_to_earnings>21, vix_proxy<30.
    """
    if regime not in ("SIDEWAYS", "BULL"):
        return False
    if iv_rank < config.get("iv_rank_min", 30):
        return False
    if days_to_earnings <= config.get("min_days_to_earnings", 21):
        return False
    if vix_proxy >= config.get("vix_max_sell", 30):
        return False
    return True


def csp_signal(
    symbol: str,
    spot: float,
    iv_rank: float,
    iv_implied: float,
    regime: str,
    days_to_earnings: int,
    vix_proxy: float,
    config: dict[str, Any],
    risk_free_rate: float = 0.05,
) -> dict[str, Any]:
    """Gera sinal de Cash-Secured Put.

    Encontra strike com delta aprox target_delta via BSM (busca binaria).
    Retorna FLAT se gates nao passarem.

    Args:
        symbol: Simbolo do subjacente (SPY, QQQ, IWM).
        spot: Preco actual do subjacente.
        iv_rank: IV Rank actual (0-100).
        iv_implied: Volatilidade implicita actual (decimal ou percentagem).
        regime: Regime de mercado ('BULL', 'BEAR', 'SIDEWAYS').
        days_to_earnings: Dias ate proximos earnings.
        vix_proxy: Proxy de VIX actual.
        config: OPTIONS_PREMIUM_CONFIG.
        risk_free_rate: Taxa de juro livre de risco (default 5%).

    Returns:
        Signal dict com strike, DTE, greeks, e premium estimado.
    """
    allowed = config.get("allowed_symbols", [])
    if symbol not in allowed:
        return _flat_signal({"reason": "symbol_not_allowed"})

    if not should_sell_premium(regime, iv_rank, days_to_earnings, vix_proxy, config):
        return _flat_signal({"reason": "premium_gates_blocked"})

    target_delta = config.get("target_delta", 0.15)
    dte = config.get("target_dte", 45)
    T = dte / 365.0
    sigma = iv_implied / 100.0 if iv_implied > 1 else iv_implied

    # Procurar strike com |delta| aprox target_delta (busca binaria)
    lo, hi = spot * 0.70, spot * 0.99
    strike = spot * (1 - target_delta)  # aproximacao inicial
    for _ in range(20):
        mid = (lo + hi) / 2.0
        g = BlackScholes.calculate_greeks(spot, mid, T, risk_free_rate, sigma, "put")
        d = abs(g["delta"])
        if d > target_delta:
            hi = mid
        else:
            lo = mid
        strike = mid

    greeks = BlackScholes.calculate_greeks(spot, strike, T, risk_free_rate, sigma, "put")

    return {
        "signal": "SELL_PUT",
        "confidence": 2,
        "entry_price": greeks["price"],
        "stop_loss": 0.0,
        "take_profit": round(greeks["price"] * (1 - config.get("close_at_profit_pct", 0.50)), 6),
        "position_size": 0.0,
        "metadata": {
            "type": "csp",
            "strike": round(strike, 2),
            "dte": dte,
            "iv_rank": iv_rank,
            "greeks": greeks,
            "module": "options_premium",
        },
    }


def check_csp_exit(
    current_price: float,
    credit_received: float,
    strike: float,
    dte_remaining: int,
    iv_rank_current: float,
    config: dict[str, Any],
) -> dict[str, Any]:
    """Verifica se deve fechar a posicao CSP.

    Saidas: 50% lucro, 21 DTE, IV Rank < 20.

    Args:
        current_price: Preco actual do subjacente.
        credit_received: Credito recebido ao vender a put.
        strike: Strike da put vendida.
        dte_remaining: Dias ate expiracao.
        iv_rank_current: IV Rank actual.
        config: OPTIONS_PREMIUM_CONFIG.

    Returns:
        Dict com "action" ("CLOSE" ou "HOLD") e "reason".
    """
    profit_pct = 1 - (current_price / credit_received) if credit_received > 0 else 0
    close_profit = config.get("close_at_profit_pct", 0.50)
    close_dte = config.get("close_at_dte", 21)

    if profit_pct >= close_profit:
        return {"action": "CLOSE", "reason": f"profit_target_{round(profit_pct * 100)}pct"}
    if dte_remaining <= close_dte:
        return {"action": "CLOSE", "reason": f"dte_low_{dte_remaining}"}
    if iv_rank_current < 20:
        return {"action": "CLOSE", "reason": "iv_rank_low"}
    return {"action": "HOLD", "reason": "within_parameters"}


def _flat_signal(metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "signal": "FLAT", "confidence": 0, "entry_price": 0.0,
        "stop_loss": 0.0, "take_profit": 0.0, "position_size": 0.0,
        "metadata": metadata or {},
    }
```

**CASOS DE TESTE -- MODULO 9:**

| Caso | Input | Esperado |
|---|---|---|
| Normal (BULL) | SPY, spot=450, iv_rank=45, iv_implied=0.22, regime=BULL, earnings=60d, vix=18 | SELL_PUT conf=2, strike via delta search, greeks preenchidos |
| Blocked (BEAR) | SPY, spot=400, iv_rank=50, regime=BEAR, earnings=60d, vix=25 | FLAT reason=premium_gates_blocked |
| Blocked (low IV) | QQQ, spot=380, iv_rank=20, regime=SIDEWAYS, earnings=40d, vix=15 | FLAT reason=premium_gates_blocked |
| Blocked (earnings) | SPY, spot=450, iv_rank=40, regime=BULL, earnings=15d, vix=18 | FLAT reason=premium_gates_blocked |
| Blocked (VIX) | IWM, spot=200, iv_rank=60, regime=SIDEWAYS, earnings=40d, vix=35 | FLAT reason=premium_gates_blocked |
| Blocked (symbol) | AAPL, spot=180, iv_rank=40, regime=BULL, earnings=60d, vix=18 | FLAT reason=symbol_not_allowed |
| Exit (profit) | price=460, credit=5.0, strike=430, dte=30, iv=25 | CLOSE reason=profit_target |
| Exit (DTE) | price=445, credit=5.0, strike=430, dte=18, iv=35 | CLOSE reason=dte_low_18 |
| Exit (IV drop) | price=445, credit=5.0, strike=430, dte=35, iv=15 | CLOSE reason=iv_rank_low |
| Hold | price=445, credit=5.0, strike=430, dte=35, iv=35 | HOLD reason=within_parameters |

---

## SECÇÃO 3 — MODIFICAÇÕES EM main.py

### 3.1 Schema de Configuração Global MODULE_CONFIG

Adicionar ao ficheiro `config.py` ou como constante em `main.py`:

```python
MODULE_CONFIG: dict[str, dict[str, Any]] = {
    "sector_rotation": SECTOR_ROTATION_CONFIG,
    "gap_fade": GAP_FADE_CONFIG,
    "forex_mr": FOREX_MR_CONFIG,
    "forex_breakout": FOREX_BREAKOUT_CONFIG,
    "futures_mr": FUTURES_MR_CONFIG,
    "intl_etf_mr": INTL_ETF_MR_CONFIG,
    "commodity_mr": COMMODITY_MR_CONFIG,
    "futures_trend": FUTURES_TREND_CONFIG,
    "bond_mr_hedge": BOND_MR_HEDGE_CONFIG,
    "options_premium": OPTIONS_PREMIUM_CONFIG,
}
```

### 3.2 Routing por asset_type no Loop Principal

Adicionar após o processamento Kotegawa existente no loop principal de `main.py`:

```python
# ── NOVOS MÓDULOS: Routing por asset_type ──
from src.sector_rotation import sector_rotation_signal
from src.gap_fade import gap_fade_signal
from src.forex_mr import forex_mr_signal, ForexRegimeSwitch, forex_kill_switches
from src.forex_breakout import detect_forex_range, generate_breakout_signal
from src.futures_mr import futures_mr_signal, check_overnight_safety
from src.futures_trend import futures_trend_signal
from src.intl_etf_mr import intl_etf_signal
from src.commodity_mr import commodity_mr_signal
from src.bond_mr_hedge import bond_mr_signal, check_defensive_rotation_trigger
from src.options_premium import csp_signal, check_csp_exit

forex_regime = ForexRegimeSwitch()

async def process_new_modules(
    spec: InstrumentSpec,
    bars_df: pd.DataFrame,
    market_data: dict,
    risk_mgr: RiskManager,
    config: dict[str, Any],
    spy_closes: list[float] | None = None,
    tlt_closes: list[float] | None = None,
    defensive_state: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Router para os novos módulos baseado no asset_type.

    Args:
        spy_closes: Fechos SPY (necessário para bond_mr_signal defensivo).
        tlt_closes: Fechos TLT (necessário para correlação stocks/bonds).
        defensive_state: Estado persistido {'mode': 'NORMAL'|'DEFENSIVE', 'days_in_defensive': int}.
    """
    asset_type = spec.asset_type.value  # STK, ETF, FX, FUT, CFD
    symbol = spec.symbol
    if defensive_state is None:
        defensive_state = {"mode": "NORMAL", "days_in_defensive": 0}
    if spy_closes is None:
        spy_closes = []
    if tlt_closes is None:
        tlt_closes = []

    closes = bars_df["close"].tolist()
    highs = bars_df["high"].tolist()
    lows = bars_df["low"].tolist()
    volumes = bars_df["volume"].tolist() if "volume" in bars_df else []
    opens = bars_df["open"].tolist() if "open" in bars_df else []

    signal = None

    # ── FOREX ──
    if asset_type == "FX":
        adx_val = calculate_adx(highs, lows, closes, 14)
        active_module = forex_regime.get_active_module(adx_val)

        if active_module == "forex_mr" and config["forex_mr"]["is_active"]:
            blocked, reasons = forex_kill_switches(highs, lows, closes,
                                                    datetime.now(timezone.utc).weekday(),
                                                    config["forex_mr"])
            if not blocked:
                signal = forex_mr_signal(closes, highs, lows, config["forex_mr"])

        elif active_module == "forex_breakout" and config["forex_breakout"]["is_active"]:
            range_info = detect_forex_range(highs, lows, closes, config["forex_breakout"])
            signal = generate_breakout_signal(closes, opens, highs, lows, range_info, config["forex_breakout"])

    # ── FUTURES ──
    elif asset_type == "FUT":
        adx_val = calculate_adx(highs, lows, closes, 14)

        if adx_val < 25 and config["futures_mr"]["is_active"]:
            signal = futures_mr_signal(symbol, closes, highs, lows, config["futures_mr"])
        elif adx_val >= 25 and config["futures_trend"]["is_active"]:
            sym_type = "indices"  # Determinar tipo por símbolo
            if symbol in ("MGC",): sym_type = "metals"
            elif symbol in ("MCL",): sym_type = "energy"
            signal = futures_trend_signal(symbol, closes, highs, lows, sym_type, config["futures_trend"])

    # ── ETFs (Internacional, Commodity, Bond) ──
    elif asset_type in ("STK", "ETF"):
        intl_etfs = set(config["intl_etf_mr"].get("kairi_thresholds", {}).keys())
        commodity_etfs = set(config["commodity_mr"].get("thresholds", {}).keys())
        bond_etfs = set(config["bond_mr_hedge"].get("kairi_thresholds", {}).keys())

        if symbol in intl_etfs and config["intl_etf_mr"]["is_active"]:
            signal = intl_etf_signal(symbol, closes, highs, lows, volumes,
                                      [], {}, config["intl_etf_mr"])
        elif symbol in commodity_etfs and config["commodity_mr"]["is_active"]:
            signal = commodity_mr_signal(symbol, closes, highs, lows, config["commodity_mr"])
        elif symbol in bond_etfs and config["bond_mr_hedge"]["is_active"]:
            # bond_mr_signal requer SPY e TLT closes + estado defensivo
            signal = bond_mr_signal(
                symbol, closes, highs, lows,
                spy_closes=spy_closes,       # passado ao process_new_modules
                tlt_closes=tlt_closes,       # passado ao process_new_modules
                vix_proxy=market_data.get("vix_proxy", 0.0),
                defensive_state=defensive_state,  # dict persistido em state
                config=config["bond_mr_hedge"],
            )
        # else: fallback para Kotegawa existente (já processado acima)

    return signal
```

### 3.3 Integração no Loop Existente

**ONDE:** No loop `for spec in watchlist:` do `main.py`, **APÓS** o processamento Kotegawa existente:

```python
# ── EXISTENTE: Kotegawa signal processing (NAO TOCAR) ──
# kotegawa_result = kotegawa_signal(market_data, regime_info)
# if kotegawa_result.signal: validate_order() + submit_bracket_order()
# (manter todo o codigo Kotegawa existente sem alteracoes)

# ── NOVO: Processar módulos multi-instrumento ──
new_signal = await process_new_modules(spec, bars_df, market_data, risk_manager, MODULE_CONFIG)
if new_signal and new_signal.get("signal") not in ("FLAT", None):
    if new_signal.get("confidence", 0) >= 2:
        # Validar via risk_manager (mesmo pipeline)
        order_params = {
            "symbol": spec.symbol,
            "entry_price": new_signal["entry_price"],
            "stop_price": new_signal["stop_loss"],
            "take_profit_price": new_signal["take_profit"],
            "capital": risk_manager.capital,
            "daily_pnl": daily_pnl,
            "weekly_pnl": weekly_pnl,
            "monthly_pnl": monthly_pnl,
            "current_positions": current_positions,
            "current_grids": len(grid_engine.get_active_grids()),
        }
        approved, reason = risk_manager.validate_order(order_params)
        if approved:
            # Submeter via execution
            contract = build_contract(spec)
            await data_feed.qualify_contract(contract)
            action = new_signal.get("signal", "FLAT")
            quantity = risk_manager.position_size_per_level(
                capital=risk_manager.capital,
                entry=new_signal["entry_price"],
                stop=new_signal["stop_loss"],
            )
            if action == "SELL_PUT":
                logger.info("CSP sinal aprovado para %s — strike=%s",
                            spec.symbol, new_signal["metadata"].get("strike"))
                # Opções: submeter via execution com contract tipo OPT
            else:
                await execution.submit_bracket_order(
                    contract=contract,
                    action="BUY" if action == "LONG" else "SELL",
                    quantity=quantity,
                    entry_price=new_signal["entry_price"],
                    stop_price=new_signal["stop_loss"],
                    take_profit_price=new_signal["take_profit"],
                    grid_id=f"{spec.symbol}_new_module",
                    level=0,
                )
```

---

## SECÇÃO 4 — CHECKLIST FINAL

Sequência de implementação com dependências:

- [ ] **Passo 1:** `signal_engine.py` → adicionar `calculate_adx()`, `calculate_choppiness_index()`, `calculate_ema()`
- [ ] **Passo 2:** `risk_manager.py` → adicionar `check_correlation_limit()` como função de módulo
- [ ] **Passo 3:** Criar `src/sector_rotation.py` (Módulo 6) — mais simples, sem dependências
- [ ] **Passo 4:** Criar `src/gap_fade.py` (Módulo 7) — independente
- [ ] **Passo 5:** Criar `src/forex_mr.py` (Módulo 1) — depende de ADX (Passo 1)
- [ ] **Passo 6:** Criar `src/forex_breakout.py` (Módulo 2) — depende de forex_mr
- [ ] **Passo 7:** Criar `src/intl_etf_mr.py` (Módulo 5) — depende de correlation check (Passo 2)
- [ ] **Passo 8:** Criar `src/commodity_mr.py` (Módulo 8) — independente excepto thresholds
- [ ] **Passo 9:** Criar `src/futures_mr.py` (Módulo 3) — depende de Panama roll
- [ ] **Passo 10:** Criar `src/futures_trend.py` (Módulo 4) — depende de futures_mr + ADX
- [ ] **Passo 11:** Criar `src/bond_mr_hedge.py` (Módulo 10) — depende de correlation regime
- [ ] **Passo 12:** Criar `src/options_premium.py` (Módulo 9) — ultimo (BSM via math.erfc, sem scipy)
- [ ] **Passo 13:** `main.py` → adicionar MODULE_CONFIG + routing por asset_type
- [ ] **Passo 14:** Testes unitários para cada módulo novo
- [ ] **Passo 15:** Teste de integração end-to-end com paper trading

---

## SECÇÃO 5 — VALIDAÇÃO PÓS-IMPLEMENTAÇÃO

### Critérios de Aprovação por Módulo

| Módulo | Critério | Mínimo |
|---|---|---|
| sector_rotation | Backtest 2015-2024, CAGR > 10% | Sharpe > 0.85 |
| gap_fade | Backtest 2020-2024, win rate > 55% | 50+ trades |
| forex_mr | Backtest EUR/USD 2018-2024, win rate > 55% | Sharpe > 0.8 |
| forex_breakout | Backtest 2018-2024, payoff > 2:1 | Win rate > 40% |
| futures_mr | Backtest MES 2020-2024, MR em ranging | Sharpe > 0.9 |
| futures_trend | Backtest MES 2018-2024, trend following | Payoff > 2.5:1 |
| intl_etf_mr | Backtest EWG/EWJ 2015-2024 | Correlação < 0.70 |
| commodity_mr | Backtest GLD/USO 2018-2024 | UNG = 0 trades |
| options_premium | Paper trade SPY CSP 30 dias | 80%+ win rate |
| bond_mr_hedge | Backtest TLT 2018-2024 | Hedge eficaz em 2020/2022 |

### Plano de Paper Trading

1. **Semana 1-2:** Módulos 6 (Sector Rotation) + 7 (Gap Fade) — Fase 1
2. **Semana 3-4:** Módulos 1 (Forex MR) + 8 (Commodity MR) — Fase 2
3. **Semana 5-6:** Módulos 3 (Futures MR) + 10 (Bond Hedge) — Fase 2
4. **Semana 7-8:** Módulos 2 (Forex Breakout) + 5 (ETFs Int.) — Fase 3
5. **Semana 9-10:** Módulos 4 (Futures Trend) + 9 (Options) — Fase 3
6. **Semana 11-12:** Integração completa com todos os módulos activos

### Comandos de Verificação

```bash
# Executar testes unitários
python -m pytest tests/ -v

# Verificar que nenhum ficheiro usa print() em vez de logger
grep -rn "print(" src/ --include="*.py" | grep -v "# noqa"

# Verificar que todos os ficheiros têm from __future__ import annotations
for f in src/*.py; do head -5 "$f" | grep -q "from __future__" || echo "FALTA: $f"; done

# Executar backtest de módulo individual (exemplo)
python -m src.backtest --module sector_rotation --start 2015-01-01 --end 2024-12-31

# Paper trading com todos os módulos activos
PAPER_TRADING=true python main.py
```

---

## APÊNDICE A — RESUMO DAS FASES VS MÓDULOS

| Fase | Capital | Módulos Activos | Módulos Dormentes |
|---|---|---|---|
| 1 | €0-2k | KAIRI acções (core) + Sector Rotation + Gap Fade | Todos os outros |
| 2 | €2-10k | +Forex MR (EUR/USD) + Commodity MR + Bond defensivo (IEF 20%) | Futuros, Opções |
| 3 | €5-15k | +Futures MR (MES, MNQ) + Options CSP | — |
| 4 | €10-25k | +Forex Breakout + ETFs Int. alargados + Futures Trend | — |
| 5 | €25k+ | +Options Strangles + Bond MR táctico + Sector Rotation alargado | — |
| 6 | €100k+ | Todos activos + Standard futures + Bond ladder individual | — |

---

## APÊNDICE B — FICHEIROS NOVOS A CRIAR

| Ficheiro | Módulo | Funções |
|---|---|---|
| `src/sector_rotation.py` | 6 | `sector_rotation_signal` |
| `src/gap_fade.py` | 7 | `classify_gap`, `gap_fade_signal` |
| `src/forex_mr.py` | 1 | `ForexRegimeSwitch`, `forex_mr_signal`, `forex_kill_switches` |
| `src/forex_breakout.py` | 2 | `detect_forex_range`, `generate_breakout_signal` |
| `src/futures_mr.py` | 3 | `handle_futures_roll`, `check_overnight_safety`, `futures_mr_signal` |
| `src/futures_trend.py` | 4 | `calculate_chandelier_exit`, `calculate_pyramid_entry`, `futures_trend_signal` |
| `src/intl_etf_mr.py` | 5 | `intl_etf_signal` |
| `src/commodity_mr.py` | 8 | `contango_drag_guard`, `commodity_mr_signal` |
| `src/options_premium.py` | 9 | `BlackScholes.calculate_greeks` (staticmethod), `should_sell_premium`, `csp_signal`, `check_csp_exit` |
| `src/bond_mr_hedge.py` | 10 | `detect_stock_bond_correlation_regime`, `check_defensive_rotation_trigger`, `bond_mr_signal` |

## APÊNDICE C — FICHEIROS EXISTENTES A MODIFICAR

| Ficheiro | Alteração | O que NÃO tocar |
|---|---|---|
| `src/signal_engine.py` | Adicionar `calculate_adx()`, `calculate_choppiness_index()`, `calculate_ema()` | `kotegawa_signal()`, thresholds -25/-35, RSI<30 |
| `src/risk_manager.py` | Adicionar `check_correlation_limit()` | Half-Kelly, kill switches, caps existentes |
| `main.py` | Adicionar routing por asset_type + MODULE_CONFIG | Loop principal, conexão IBKR existente |
| `config.py` | Adicionar MODULE_CONFIG schema (opcional) | IBConfig, RiskConfig existentes |

---

**FIM DO CODEX IMPLEMENTATION BRIEF — FINAL**

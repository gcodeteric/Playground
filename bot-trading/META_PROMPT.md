# META ULTRA-PROMPT — BOT DE TRADING AUTÓNOMO COM GRID ENGINE

> **Instruções para o Claude Code:** Este prompt deve ser executado numa sessão com Ruflo multi-agente ativo.
> Cola este ficheiro inteiro no Claude Code e executa-o. O sistema de 9 agentes coordena tudo automaticamente.

---

<contexto>

## Contexto do Projeto

Estás a construir um **bot de trading 100% autónomo em Python** que opera sem qualquer intervenção humana.
O bot liga-se ao **Interactive Brokers via ib_insync** e gere grids de trading automaticamente.

### Investigação de suporte
Na pasta `research/` existem 5 ficheiros .md com investigação completa:
- `FASE_1_3_INVENTARIO_TAXONOMIA_GAPS.md` — inventário de 25 métodos, taxonomia, caso Kotegawa/BNF
- `FASE_4_8_LIVROS_COMPARACOES_RISK_PRIORIDADES.md` — risk framework, Kelly, métricas, arquitetura de módulos
- `BLOCO_A_METODOS_COMPLETOS.md` — dossiers de position trading, EOD trading, factor investing
- `BLOCO_B_LIVROS_COMPLETOS.md` — dossiers de 30 livros com parâmetros extraídos
- `BLOCO_C_D_COMPARACOES_TEMAS.md` — comparações entre escolas, backtesting pitfalls, futures mechanics

### Parâmetros Extraídos da Investigação (valores concretos)

**Estratégia Kotegawa (SMA25 Deviation) — Filtro de Entrada:**
- Fórmula: `deviation = ((preco_atual - SMA25) / SMA25) * 100`
- Limiares BEAR market: deviation ≤ -20% a -60% (ajustado por setor)
- Limiares BULL market: deviation ≤ -5% a -15%
- Limiares SIDEWAYS: deviation ≤ -10% a -25%
- Confirmação obrigatória: RSI(14) < 30, Bollinger(20,2) abaixo da banda inferior, volume > 150% da média 20 dias
- Padrões de vela de confirmação: hammer, bullish engulfing
- Holding period típico: 2-6 dias (para referência de take-profit)

**Indicadores Técnicos (parâmetros exatos):**
- SMA(25) — indicador central Kotegawa
- SMA(50) e SMA(200) — filtros de tendência macro
- RSI(14) — sobrecompra > 70, sobrevenda < 30
- ATR(14) — para position sizing e espaçamento de grid
- Bollinger Bands(20, 2σ) — confirmação de extremos
- Volume médio de 20 períodos — baseline para spikes

**Regime Detection Automático:**
- BULL: preço > SMA(200) E SMA(50) > SMA(200) E RSI(14) > 50
- BEAR: preço < SMA(200) E SMA(50) < SMA(200) E RSI(14) < 50
- SIDEWAYS: nenhuma das condições anteriores OU ATR(14) < 50% da média ATR de 60 dias
- Recalibrar regime a cada barra diária
- Transição de regime = alerta Telegram obrigatório

**Gestão de Risco (valores concretos da investigação):**
- Risco por nível de grid: 1% do capital
- R:R mínimo: 1:2 (alvo ≥ 2× risco)
- Stop-loss por nível: 1.5× ATR(14) abaixo do preço de entrada
- Take-profit por nível: 2× ATR(14) acima do preço de entrada (mínimo)
- Daily loss limit: 3% do capital → pausa automática
- Weekly loss limit: 6% do capital → pausa automática
- Monthly drawdown kill switch: 10% → bot para, alerta Telegram, só reinicia com confirmação manual
- Máximo de posições simultâneas: 5-8 (configurável)
- Máximo de grids ativas simultâneas: 3 (configurável)

**Half-Kelly Criterion para Position Sizing:**
- Fórmula Kelly: `K = W - (1 - W) / R` onde W = win_rate, R = payoff_ratio
- Usar sempre HALF-Kelly: `position_pct = K / 2`
- Half-Kelly captura ~75% do crescimento com ~50% da volatilidade
- Cap máximo: nunca mais de 5% do capital por nível, independentemente do Kelly

**Risk of Ruin (meta: ≈ 0%):**
- Com 1% risco/trade, 50% WR, 2:1 R:R → risk of ruin ≈ 0%
- Com 5% risco/trade → risk of ruin ≈ 13% (INACEITÁVEL)
- O bot DEVE operar com risco que garanta risk of ruin < 0.1%

**Grid Trading — Parâmetros:**
- Espaçamento entre níveis: 1× ATR(14) do timeframe diário
- Número de níveis por grid: 5-10 (ajustado pelo regime)
  - BULL: 5 níveis (grids mais apertadas, foco em tendência)
  - BEAR: 7-10 níveis (grids mais largas, foco em mean reversion)
  - SIDEWAYS: 6-8 níveis (grids normais)
- Re-centrar grid quando preço ultrapassa 70% da extensão da grid
- Cada nível tem: ordem limit de compra, stop-loss individual, take-profit individual
- Zero averaging down — regra absoluta extraída de Kotegawa

**Métricas de Performance a Calcular:**
- Win rate (sem contexto é inútil; com payoff ratio conta a história)
- Payoff ratio: média ganho / média perda (≥ 2.0 ideal)
- Expectancy: (prob_ganho × ganho_medio) - (prob_perda × perda_media) — deve ser > 0
- Max drawdown: maior queda pico-vale
- Sharpe ratio: ≥ 1.0 bom, ≥ 2.0 excelente
- Profit factor: gross_profit / gross_loss — > 1.5 bom
- Número mínimo de trades para significância: 100+

**7 Backtesting Pitfalls a Validar (da investigação):**
1. Overfitting/data snooping — máx 5 parâmetros otimizados
2. Lookahead bias — verificar que dados usados existiam no momento do sinal
3. Survivorship bias — usar dados point-in-time com delisted stocks
4. Assumption errors — modelar slippage, gaps, dividendos
5. Data mining bias — usar out-of-sample e walk-forward
6. Regime change — testar em bull, bear e sideways (incluir 2008, 2020, 2022)
7. Custos subestimados — incluir spreads, comissões, swaps, market impact

**Mercados suportados (via IB):**
- Ações (US, EU) — mercado principal
- ETFs (SPY, QQQ, VWCE, etc.)
- Forex (EUR/USD, GBP/USD, USD/JPY, etc.)
- CFDs (índices)
- Micro futuros (MES $1.25/tick, MNQ $0.50/tick, MYM)

</contexto>

---

<objetivo>

## Objetivo

Construir um **bot de trading 100% autónomo** em Python que:

1. **Opera sem intervenção humana** — ciclo completamente autónomo 24/7
2. **Cria e gere grids de trading** — compra e vende automaticamente em múltiplos níveis
3. **Liga ao Interactive Brokers** via `ib_insync` (ações, ETFs, Forex, CFDs, micro futuros)
4. **Usa a estratégia Kotegawa** (desvio da SMA25) como filtro de entrada em cada grid
5. **Deteta regime automaticamente** (BULL/BEAR/SIDEWAYS) e ajusta as grids dinamicamente
6. **Gestão de risco automática** — 1% por nível, kill switch a 10%, Half-Kelly sizing
7. **Envia alertas Telegram** para cada ação autónoma (abertura de grid, compra, venda, alerta, erro)
8. **Corre 24/7** com reconnect automático ao IB Gateway/TWS

### Ciclo Autónomo Completo (sem humano)
```
LOOP INFINITO:
  1. Verificar conexão IB (reconnect se necessário)
  2. Obter dados de mercado (barras diárias + intraday se necessário)
  3. Calcular regime (BULL/BEAR/SIDEWAYS)
  4. Calcular sinal Kotegawa (deviation SMA25 + confirmações)
  5. SE sinal válido E risco ok:
     → Criar nova grid com níveis calculados por ATR
     → Colocar ordens limit em cada nível
     → Colocar stop-loss e take-profit por nível
  6. Monitorizar grids ativas:
     → Ordem executada? → Log + Telegram + Colocar ordens seguintes
     → Take-profit atingido? → Fechar nível + Recolocar se grid ainda ativa
     → Stop-loss atingido? → Fechar nível + Avaliar grid
     → Grid esgotada? → Fechar + Avaliar re-abertura
     → Preço saiu da grid? → Re-centrar grid
  7. Verificar limites de risco:
     → Daily loss > 3%? → Pausar
     → Monthly drawdown > 10%? → Kill switch + Telegram
  8. Persistir estado em grids_state.json
  9. Dormir até próximo ciclo (intervalo configurável)
```

</objetivo>

---

<arquitetura_agentes>

## Arquitetura de 9 Agentes Ruflo

### AGENTE 1 — ORQUESTRADOR (Maestro)
**Responsabilidades:**
- Coordena todos os 8 agentes restantes
- Mantém `context.md` partilhado com estado do projeto
- Define ordem de execução dos módulos
- Resolve conflitos entre agentes
- **Só avança para o módulo seguinte após validação dos Agentes 8 (Tester) e 9 (Auditor)**
- Tem autoridade final em caso de desacordo
- Atualiza `context.md` após cada módulo aprovado

**Ferramentas:** `claims`, `coordination`, `task`, `progress`

---

### AGENTE 2 — ARQUITETO (Skeleton Builder)
**Responsabilidades:**
- Define a estrutura completa de ficheiros ANTES de qualquer código
- Define interfaces entre módulos (contratos de funções, tipos, dataclasses)
- Cria o esqueleto de todos os ficheiros com assinaturas de funções e docstrings
- Garante que a arquitetura suporta autonomia total (zero intervenção humana)
- Define o ficheiro `config.py` com todos os parâmetros configuráveis
- Cria `.env.example` com todas as variáveis de ambiente necessárias

**Output esperado:**
```
bot-trading/
├── .env.example
├── .gitignore
├── config.py              # Todas as constantes e parâmetros
├── main.py                # Entry point — loop autónomo principal
├── requirements.txt
├── context.md             # Estado partilhado entre agentes
├── EXTRACTED_PARAMS.md    # Parâmetros extraídos da investigação
├── README.md
├── src/
│   ├── __init__.py
│   ├── data_feed.py       # Módulo 1: Conexão IB + dados de mercado
│   ├── grid_engine.py     # Módulo 2: Lógica de grid autónoma
│   ├── signal_engine.py   # Módulo 3: Kotegawa + regime detection
│   ├── risk_manager.py    # Módulo 4: Gestão de risco
│   ├── execution.py       # Módulo 5: Execução de ordens no IB
│   └── logger.py          # Módulo 6: Logs + Telegram
├── tests/
│   ├── __init__.py
│   ├── test_data_feed.py
│   ├── test_grid_engine.py
│   ├── test_signal_engine.py
│   ├── test_risk_manager.py
│   ├── test_execution.py
│   ├── test_logger.py
│   └── test_integration.py  # Ciclo autónomo completo simulado
├── data/
│   ├── grids_state.json     # Estado persistente das grids
│   ├── trades_log.json      # Log imutável de trades
│   └── metrics.json         # Métricas de performance acumuladas
└── research/                # Investigação (já existente, NÃO tocar)
    ├── BLOCO_A_METODOS_COMPLETOS.md
    ├── BLOCO_B_LIVROS_COMPLETOS.md
    ├── BLOCO_C_D_COMPARACOES_TEMAS.md
    ├── FASE_1_3_INVENTARIO_TAXONOMIA_GAPS.md
    └── FASE_4_8_LIVROS_COMPARACOES_RISK_PRIORIDADES.md
```

**Ferramentas:** `workflow`, `task`

---

### AGENTE 3 — PROGRAMADOR IB (Interactive Brokers Specialist)
**Responsabilidades EXCLUSIVAS:**
- Implementar `src/data_feed.py` — conexão e dados
- Implementar `src/execution.py` — execução de ordens
- Usar EXCLUSIVAMENTE `ib_insync` como biblioteca de ligação ao IB
- Garantir:
  - Ligação contínua com reconnect automático (IB Gateway ou TWS)
  - Heartbeat/watchdog que deteta desconexão em < 30 segundos
  - Reconexão automática com backoff exponencial (5s, 10s, 20s, 40s, max 300s)
  - Suporte para múltiplos tipos de contrato: Stock, Forex, CFD, Future
  - Bracket orders (entry + stop + take-profit numa única submissão)
  - Ordens limit com preço calculado pelo grid_engine
  - Cancelamento automático de ordens pendentes quando grid fecha
  - Recolocação automática de ordens quando nível é executado
  - Qualificação de contratos antes de submissão de ordens
  - Rate limiting para evitar exceder limites da API do IB (max 50 msg/s)

**Padrão de conexão obrigatório:**
```python
# Pseudocódigo — o agente implementa a versão completa
from ib_insync import IB, util

class IBConnection:
    def __init__(self, host='127.0.0.1', port=4002, client_id=1):
        # port 4002 = IB Gateway paper, 4001 = IB Gateway live
        # port 7497 = TWS paper, 7496 = TWS live
        self.ib = IB()
        self.paper_trading = True  # SEMPRE True por defeito

    async def connect_with_retry(self):
        # Backoff exponencial: 5s, 10s, 20s, 40s... max 300s
        # Alerta Telegram a cada tentativa falhada
        pass

    def on_disconnected(self):
        # Callback automático — inicia reconnect
        # Pausa todas as grids enquanto desconectado
        pass
```

**Ferramentas:** `terminal`, `task`

---

### AGENTE 4 — PROGRAMADOR GRID ENGINE (Grid Logic Specialist)
**Responsabilidades EXCLUSIVAS:**
- Implementar `src/grid_engine.py` — toda a lógica de grid autónoma
- Implementar o ciclo autónomo completo de cada grid:

```
CICLO DE VIDA DE UMA GRID:
  1. ABRIR GRID
     - Receber sinal do signal_engine (ativo, direção, confiança)
     - Calcular preço central (preço atual do ativo)
     - Calcular espaçamento: 1× ATR(14) diário
     - Calcular número de níveis: 5-10 (ajustado pelo regime)
     - Calcular preço de cada nível (central ± n × espaçamento)
     - Calcular position size por nível via risk_manager
     - Submeter ordens limit de compra em cada nível via execution

  2. COMPRA EXECUTADA
     - Nível N comprado → registar no estado
     - Colocar take-profit: preço_compra + 2× ATR(14)
     - Confirmar stop-loss: preço_compra - 1.5× ATR(14)
     - Alerta Telegram: "Nível {N} comprado a {preço} em {ativo}"

  3. VENDA EXECUTADA (take-profit)
     - Nível N vendido com lucro → registar
     - Avaliar re-colocação: SE grid ainda ativa E risco ok
       → Recolocar ordem de compra no mesmo nível
     - Alerta Telegram: "Nível {N} vendido com +{lucro}€"

  4. STOP-LOSS ATINGIDO
     - Nível N parado com perda → registar
     - NÃO recolocar (zero averaging down)
     - Alerta Telegram: "Stop-loss nível {N}: -{perda}€"

  5. RE-CENTRAR GRID
     - SE preço ultrapassa 70% da extensão da grid:
       → Cancelar ordens não executadas dos níveis mais distantes
       → Recalcular novos níveis centrados no preço atual
       → Submeter novas ordens
       → Alerta Telegram: "Grid re-centrada em {ativo}"

  6. FECHAR GRID
     - Condições: todos os stops atingidos OU sinal contrário OU kill switch
     - Cancelar TODAS as ordens pendentes da grid
     - Fechar TODAS as posições abertas da grid (market orders se necessário)
     - Calcular P&L total da grid
     - Alerta Telegram: "Grid fechada em {ativo}: P&L = {total}€"

  7. REINICIAR
     - Avaliar condições para nova grid (novo sinal necessário)
     - Volta ao passo 1
```

**Estado persistente obrigatório (`grids_state.json`):**
```json
{
  "grids": [
    {
      "id": "grid_AAPL_20260314_001",
      "symbol": "AAPL",
      "status": "active",
      "regime": "BULL",
      "created_at": "2026-03-14T10:30:00Z",
      "center_price": 185.50,
      "atr": 3.25,
      "spacing": 3.25,
      "levels": [
        {
          "level": 1,
          "buy_price": 182.25,
          "sell_price": 188.75,
          "stop_price": 177.38,
          "status": "bought",
          "quantity": 15,
          "buy_order_id": 12345,
          "sell_order_id": 12346,
          "stop_order_id": 12347,
          "bought_at": "2026-03-14T11:00:00Z",
          "pnl": null
        }
      ],
      "total_pnl": 0.0
    }
  ],
  "last_updated": "2026-03-14T12:00:00Z"
}
```

**Ferramentas:** `terminal`, `task`

---

### AGENTE 5 — PROGRAMADOR ESTRATÉGIAS (Signal Engine Specialist)
**Responsabilidades EXCLUSIVAS:**
- Implementar `src/signal_engine.py` — Kotegawa + regime detection

**Regime Detection — implementação exata:**
```python
def detect_regime(closes: list, sma50: float, sma200: float, rsi: float, atr: float, atr_avg_60: float) -> str:
    """
    Classifica o regime de mercado atual.

    BULL: preco > SMA(200) E SMA(50) > SMA(200) E RSI(14) > 50
    BEAR: preco < SMA(200) E SMA(50) < SMA(200) E RSI(14) < 50
    SIDEWAYS: nenhuma das anteriores OU ATR(14) < 50% da média ATR de 60 dias
    """
    preco = closes[-1]

    # Sideways por baixa volatilidade tem prioridade
    if atr < 0.5 * atr_avg_60:
        return "SIDEWAYS"

    if preco > sma200 and sma50 > sma200 and rsi > 50:
        return "BULL"
    elif preco < sma200 and sma50 < sma200 and rsi < 50:
        return "BEAR"
    else:
        return "SIDEWAYS"
```

**Sinal Kotegawa — implementação exata:**
```python
def kotegawa_signal(preco: float, sma25: float, rsi: float,
                    bb_lower: float, volume: float, vol_avg_20: float,
                    regime: str) -> dict:
    """
    Calcula o sinal de entrada Kotegawa com score de confiança.

    Fórmula: deviation = ((preco - SMA25) / SMA25) * 100

    Limiares por regime:
      BULL:     deviation <= -5%  (mínimo), ótimo <= -10%
      BEAR:     deviation <= -20% (mínimo), ótimo <= -40%
      SIDEWAYS: deviation <= -10% (mínimo), ótimo <= -20%

    Confirmações (cada uma adiciona confiança):
      1. RSI(14) < 30                    → +1
      2. Preço < Bollinger Lower Band    → +1
      3. Volume > 150% da média 20 dias  → +1

    Score de confiança:
      0 confirmações = BAIXO  → NÃO operar
      1 confirmação  = MEDIO → operar com 50% do size normal
      2 confirmações = MEDIO → operar com 75% do size normal
      3 confirmações = ALTO  → operar com 100% do size normal
    """
    deviation = ((preco - sma25) / sma25) * 100

    # Limiares por regime
    thresholds = {
        "BULL":     {"min": -5,  "optimal": -10},
        "BEAR":     {"min": -20, "optimal": -40},
        "SIDEWAYS": {"min": -10, "optimal": -20}
    }

    threshold = thresholds[regime]

    if deviation > threshold["min"]:
        return {"signal": False, "deviation": deviation, "confidence": "NONE"}

    # Contar confirmações
    confirmations = 0
    if rsi < 30:
        confirmations += 1
    if preco < bb_lower:
        confirmations += 1
    if volume > 1.5 * vol_avg_20:
        confirmations += 1

    # Score de confiança
    confidence_map = {0: "BAIXO", 1: "MEDIO", 2: "MEDIO", 3: "ALTO"}
    size_multiplier = {0: 0.0, 1: 0.5, 2: 0.75, 3: 1.0}

    confidence = confidence_map[confirmations]

    return {
        "signal": confirmations >= 1,  # Mínimo 1 confirmação
        "deviation": round(deviation, 2),
        "regime": regime,
        "confidence": confidence,
        "size_multiplier": size_multiplier[confirmations],
        "confirmations": confirmations,
        "details": {
            "rsi_confirmed": rsi < 30,
            "bb_confirmed": preco < bb_lower,
            "volume_confirmed": volume > 1.5 * vol_avg_20
        }
    }
```

**Ferramentas:** `terminal`, `task`

---

### AGENTE 6 — PROGRAMADOR RISCO (Risk Manager Specialist)
**Responsabilidades EXCLUSIVAS:**
- Implementar `src/risk_manager.py` — toda a gestão de risco

**Implementações obrigatórias:**
```python
class RiskManager:
    """
    Gestão de risco autónoma.
    Todos os valores vêm de config.py / .env
    """

    def position_size_per_level(self, capital: float, entry: float,
                                 stop: float, win_rate: float = 0.5,
                                 payoff_ratio: float = 2.0) -> int:
        """
        Position sizing por nível usando Half-Kelly.

        1. Calcular Kelly: K = win_rate - (1 - win_rate) / payoff_ratio
        2. Half-Kelly: K_half = K / 2
        3. Cap: máximo 5% do capital por nível
        4. Risk-based: risco_max = capital * min(K_half, 0.05)
        5. Quantidade: risco_max / abs(entry - stop)
        """
        pass

    def check_daily_limit(self, daily_pnl: float, capital: float) -> bool:
        """Daily loss > 3% → retorna False (parar)."""
        pass

    def check_weekly_limit(self, weekly_pnl: float, capital: float) -> bool:
        """Weekly loss > 6% → retorna False (parar)."""
        pass

    def check_kill_switch(self, monthly_pnl: float, capital: float) -> bool:
        """Monthly drawdown > 10% → retorna False (kill switch)."""
        pass

    def check_max_positions(self, current_positions: int) -> bool:
        """Máximo 5-8 posições simultâneas (configurável)."""
        pass

    def check_max_grids(self, current_grids: int) -> bool:
        """Máximo 3 grids ativas simultâneas (configurável)."""
        pass

    def calculate_risk_of_ruin(self, win_rate: float, payoff_ratio: float,
                                risk_per_trade: float) -> float:
        """
        Calcula probabilidade de ruína.
        Meta: < 0.1% (essencialmente zero).
        """
        pass

    def validate_order(self, order_params: dict) -> tuple[bool, str]:
        """
        Valida CADA ordem antes de submissão:
        - Stop-loss presente? (obrigatório)
        - Risco dentro dos limites?
        - Limites diários/semanais/mensais ok?
        - Número de posições ok?
        Retorna (aprovado, motivo_rejeicao)
        """
        pass
```

**Regras de ferro (NUNCA violar):**
1. Stop-loss em CADA ordem — sem exceção
2. ZERO averaging down — NUNCA comprar mais num nível em perda
3. Risco por nível: máximo 1% do capital (Hard limit: 5% via Half-Kelly cap)
4. Kill switch: 10% drawdown mensal → para TUDO
5. Risk of ruin calculado deve ser < 0.1%
6. PAPER_TRADING=true por defeito — NUNCA desativar sem confirmação

**Ferramentas:** `terminal`, `task`

---

### AGENTE 7 — PROGRAMADOR LOGGER & TELEGRAM (Logging & Alerts Specialist)
**Responsabilidades EXCLUSIVAS:**
- Implementar `src/logger.py` — logs imutáveis + alertas Telegram

**Funcionalidades obrigatórias:**

1. **Log Imutável de Trades:**
   - Cada trade registado em `data/trades_log.json` (append-only)
   - Campos: timestamp, symbol, side, price, quantity, order_id, grid_id, level, pnl, regime, signal_confidence
   - NUNCA apagar ou modificar entradas existentes

2. **Dashboard de Métricas (calculado e persistido em `data/metrics.json`):**
   - Equity curve (valor da conta ao longo do tempo)
   - Win rate, payoff ratio, expectancy
   - Max drawdown (corrente e histórico)
   - Sharpe ratio (rolling 30 dias)
   - Profit factor
   - Número total de trades
   - P&L por grid, por ativo, por regime
   - Atualizado após cada trade fechado

3. **Alertas Telegram (via Bot API):**
   ```
   Cada ação autónoma gera alerta Telegram:

   📊 NOVA GRID ABERTA
   Ativo: AAPL | Regime: BULL
   Níveis: 5 | Espaçamento: $3.25 (ATR)
   Centro: $185.50
   Confiança: ALTO (3/3 confirmações)

   🟢 COMPRA EXECUTADA
   AAPL Nível 2 | Preço: $182.25 | Qty: 15
   Stop: $177.38 | Target: $188.75
   Grid: grid_AAPL_20260314_001

   🔴 VENDA EXECUTADA
   AAPL Nível 2 | Preço: $188.75 | P&L: +$97.50
   Grid P&L total: +$145.00

   ⚠️ STOP-LOSS ATINGIDO
   AAPL Nível 3 | Perda: -$48.75
   Daily P&L: -1.2% | Kill switch: NÃO

   🛑 KILL SWITCH ATIVADO
   Monthly drawdown: -10.3%
   TODAS as grids pausadas.
   Requer confirmação manual para reiniciar.

   🔄 REGIME CHANGED
   AAPL: BULL → SIDEWAYS
   Grids recalibradas automaticamente.

   📈 RESUMO DIÁRIO (23:00)
   Data: 2026-03-14
   Trades: 12 | Win rate: 58%
   P&L dia: +€127.50 | P&L mês: +€890.00
   Drawdown corrente: -2.1% | Max DD: -4.8%
   Grids ativas: 2 (AAPL, SPY)
   ```

4. **Resumo diário automático às 23:00:**
   - Win rate do dia, P&L, drawdown, grids ativas
   - Comparação com métricas históricas

**Configuração Telegram:**
```
TELEGRAM_BOT_TOKEN=<token do @BotFather>
TELEGRAM_CHAT_ID=<chat_id do utilizador>
```

**Ferramentas:** `terminal`, `task`

---

### AGENTE 8 — TESTER (Quality Assurance)
**Responsabilidades:**
- Testar CADA módulo individualmente com dados simulados
- Testes unitários para todas as funções críticas
- Simular ciclo autónomo completo passo a passo
- Validar os 7 backtesting pitfalls da investigação
- Correr backtest com dados históricos reais do IB (mínimo 1 ano)
- **Só aprovar módulo quando 100% dos testes passam**
- Levantar BLOCKER se algum teste crítico falhar

**Testes obrigatórios por módulo:**

| Módulo | Testes mínimos |
|--------|---------------|
| data_feed | Conexão mock, parsing de barras, reconnect simulado, timeout handling |
| grid_engine | Criação de grid, execução de nível, re-centrar, fechar, rebuild de estado corrompido |
| signal_engine | Kotegawa em 3 regimes, regime detection com dados reais, edge cases (dados insuficientes) |
| risk_manager | Position sizing, daily/weekly/monthly limits, kill switch, risk of ruin cálculo |
| execution | Bracket orders mock, cancelamento, recolocação, rate limiting |
| logger | Log append-only, Telegram mock, resumo diário, métricas calculation |
| integration | Ciclo autónomo completo com 100 trades simulados, passando por BULL→BEAR→SIDEWAYS |

**Validação dos 7 pitfalls:**
1. Verificar que nenhum indicador usa dados futuros (lookahead)
2. Verificar que backtest inclui ações que foram delisted (survivorship)
3. Verificar que slippage está modelado (assumption errors)
4. Verificar que não há mais de 5 parâmetros otimizados (overfitting)
5. Verificar out-of-sample validation implementado
6. Verificar que backtest inclui períodos de crise (regime change)
7. Verificar que custos (comissões IB, spreads) estão incluídos

**Ferramentas:** `terminal`, `task`

---

### AGENTE 9 — AUDITOR DE SEGURANÇA (Security & Safety Auditor)
**Responsabilidades:**
- Auditoria final de segurança COMPLETA antes de aprovação
- Foco EXCLUSIVO em segurança, cenários de falha e proteção do capital

**Checklist obrigatória:**

**A. Segurança de Credenciais:**
- [ ] ZERO credenciais hard-coded em qualquer ficheiro `.py`
- [ ] Todas as credenciais em `.env` (IB host/port, Telegram token/chat_id)
- [ ] `.env` está no `.gitignore`
- [ ] `.env.example` existe com placeholders (não valores reais)

**B. Paper Trading por Defeito:**
- [ ] `PAPER_TRADING=true` é o valor por defeito em `config.py`
- [ ] Variável `PAPER_TRADING` é lida de `.env`
- [ ] Se `PAPER_TRADING` não está definida no `.env`, assume `true`
- [ ] Para mudar para `false` é necessário: alterar `.env` E reiniciar o bot
- [ ] Port automático: `PAPER_TRADING=true` → port 4002/7497, `false` → port 4001/7496
- [ ] Log explícito no arranque: "MODO: PAPER TRADING" ou "⚠️ MODO: CONTA REAL ⚠️"

**C. Stop-Loss Universal:**
- [ ] CADA ordem de compra tem stop-loss associado (bracket order ou OCA)
- [ ] `risk_manager.validate_order()` rejeita QUALQUER ordem sem stop
- [ ] IMPOSSÍVEL submeter ordem sem stop — validação no execution.py
- [ ] Stops não podem ser removidos ou movidos contra a posição

**D. Risk of Ruin:**
- [ ] Calculado matematicamente no arranque
- [ ] Com parâmetros atuais deve ser ≈ 0% (< 0.1%)
- [ ] Se risk of ruin > 1% → bot RECUSA arrancar + alerta Telegram
- [ ] Recalculado após cada 50 trades com win rate e payoff reais

**E. Rate Limits e Timeouts:**
- [ ] Requests à API do IB limitados (max 50 msg/s)
- [ ] Timeout em todas as chamadas de rede (default 30s)
- [ ] Timeout no Telegram API (10s, não bloqueia loop principal)
- [ ] Backoff exponencial em retries

**F. Cenários de Falha Catastrófica:**
- [ ] IB desconecta → reconnect automático com backoff exponencial
- [ ] Internet cai → bot pausa grids, retenta conexão, alerta Telegram quando volta
- [ ] Ordem não executada → retry (max 3×), depois alerta Telegram e marca como falhada
- [ ] `grids_state.json` corrompido → rebuild automático a partir de posições reais no IB
- [ ] Bot crasha → ao reiniciar, lê `grids_state.json` e retoma estado
- [ ] Dados de mercado indisponíveis → pausa grids, não cria novas, alerta Telegram
- [ ] Kill switch ativado → fecha tudo, alerta, NÃO reinicia automaticamente

**G. Integridade de Dados:**
- [ ] `grids_state.json` escrito atomicamente (write to temp + rename)
- [ ] Backup automático antes de cada escrita
- [ ] `trades_log.json` é append-only, nunca truncado
- [ ] Validação de schema no load de ficheiros JSON

**Relatório final obrigatório:**
```
=== RELATÓRIO DE AUDITORIA DE SEGURANÇA ===
Data: {data}
Auditor: Agente 9

CREDENCIAIS: ✅ PASS / ❌ FAIL
PAPER TRADING: ✅ PASS / ❌ FAIL
STOP-LOSS: ✅ PASS / ❌ FAIL
RISK OF RUIN: ✅ PASS (valor: X%) / ❌ FAIL
RATE LIMITS: ✅ PASS / ❌ FAIL
CENÁRIOS FALHA: ✅ PASS / ❌ FAIL
INTEGRIDADE DADOS: ✅ PASS / ❌ FAIL

RESULTADO: APROVADO / REPROVADO
ISSUES: [lista de issues se reprovado]

MÉTRICAS CALCULADAS:
- Risk of ruin: X%
- Win rate esperado (backtest): X%
- Max drawdown esperado: X%
- Sharpe ratio esperado: X

INSTRUÇÕES PARA CONTA REAL:
1. Verificar que paper trading correu 30+ minutos sem erros
2. Alterar PAPER_TRADING=false no .env
3. Alterar port para 4001 (Gateway) ou 7496 (TWS)
4. Começar com 25% do capital disponível
5. Monitorizar primeiras 24h manualmente
6. Só escalar capital após 100+ trades em conta real
```

**Ferramentas:** `terminal`, `task`, `analyze`

</arquitetura_agentes>

---

<modulos>

## Os 6 Módulos do Bot

### Módulo 1: `data_feed.py` — Conexão e Dados
**Agente responsável:** Agente 3 (Programador IB)
- Conexão ao IB via ib_insync com reconnect automático
- Obter barras históricas (diárias, 1 ano mínimo para cálculos)
- Obter dados em tempo real (preço atual, volume)
- Calcular indicadores: SMA(25), SMA(50), SMA(200), RSI(14), ATR(14), Bollinger(20,2)
- Cache de dados para evitar requests repetidos
- Suporte para múltiplos contratos: Stock, Forex, CFD, Future

### Módulo 2: `grid_engine.py` — Lógica de Grid Autónoma
**Agente responsável:** Agente 4 (Programador Grid Engine)
- Criar grid com N níveis baseados em ATR
- Gerir ciclo de vida completo de cada grid
- Re-centrar grid quando preço ultrapassa 70% da extensão
- Persistir estado em grids_state.json (escrita atómica)
- Rebuild de estado a partir de posições IB se JSON corrompido
- Fechar grid quando condições de saída atingidas

### Módulo 3: `signal_engine.py` — Kotegawa + Regime Detection
**Agente responsável:** Agente 5 (Programador Estratégias)
- Regime detection (BULL/BEAR/SIDEWAYS) com recalibração diária
- Sinal Kotegawa (deviation SMA25) com 3 confirmações
- Score de confiança (BAIXO/MEDIO/ALTO) com multiplicador de size
- Emitir sinal apenas quando confiança ≥ MEDIO

### Módulo 4: `risk_manager.py` — Gestão de Risco
**Agente responsável:** Agente 6 (Programador Risco)
- Position sizing por Half-Kelly com cap de 5%
- Validação de CADA ordem antes de submissão
- Kill switches automáticos (daily 3%, weekly 6%, monthly 10%)
- Risk of ruin calculado e validado no arranque
- Zero averaging down enforçado

### Módulo 5: `execution.py` — Execução de Ordens
**Agente responsável:** Agente 3 (Programador IB)
- Submissão de bracket orders (entry + stop + target)
- Cancelamento e recolocação de ordens
- Qualificação de contratos
- Rate limiting (max 50 msg/s para IB API)
- Tracking de estado de ordens

### Módulo 6: `logger.py` — Logs + Telegram
**Agente responsável:** Agente 7 (Programador Logger & Telegram)
- Log imutável append-only em trades_log.json
- Cálculo de métricas de performance
- Alertas Telegram para cada ação autónoma
- Resumo diário automático às 23:00
- Dashboard de métricas persistido em metrics.json

</modulos>

---

<restricoes>

## Restrições de Segurança e Qualidade

### Segurança (inegociáveis)
1. `PAPER_TRADING=true` por defeito — SEMPRE
2. `.env` obrigatório para TODAS as credenciais — NUNCA no código
3. `.env` no `.gitignore` — SEMPRE
4. Stop-loss em cada nível — SEM EXCEÇÃO
5. Zero averaging down — NUNCA comprar mais num nível em perda
6. Reconnect automático ao IB — o bot NUNCA fica pendurado
7. `grids_state.json` persistente entre reinícios — o bot NUNCA perde estado
8. Kill switch a 10% drawdown mensal — para tudo, sem discussão

### Código
9. Comentários e logs em **português** (PT-PT)
10. Nomes de variáveis e funções em **inglês**
11. Python 3.10+ com type hints em todas as funções
12. Async/await para operações IO (IB, Telegram, ficheiros)
13. Dataclasses ou Pydantic para estruturas de dados tipadas
14. Logging com módulo `logging` do Python (não print)
15. Configuração centralizada em `config.py` com valores de `.env`

### Dependências (requirements.txt)
```
ib_insync>=0.9.86
pandas>=2.0
numpy>=1.24
python-telegram-bot>=20.0
python-dotenv>=1.0
aiohttp>=3.9
pydantic>=2.0
```

### Testes
16. pytest como framework de testes
17. Mínimo 80% de cobertura nos módulos críticos (risk_manager, grid_engine)
18. Testes com dados simulados (não dependem de IB conectado)
19. Teste de integração com ciclo completo simulado

</restricoes>

---

<output_esperado>

## Output Esperado

Após execução completa deste prompt, o projeto deve conter:

```
bot-trading/
├── .env.example                    # Template de variáveis de ambiente
├── .gitignore                      # Inclui .env, __pycache__, data/*.json
├── config.py                       # Configuração centralizada
├── main.py                         # Entry point — loop autónomo
├── requirements.txt                # Dependências Python
├── context.md                      # Estado do projeto (agentes)
├── EXTRACTED_PARAMS.md             # Parâmetros extraídos da investigação
├── README.md                       # Instruções completas de setup
├── src/
│   ├── __init__.py
│   ├── data_feed.py                # Módulo 1: Conexão IB + indicadores
│   ├── grid_engine.py              # Módulo 2: Grid autónoma
│   ├── signal_engine.py            # Módulo 3: Kotegawa + regime
│   ├── risk_manager.py             # Módulo 4: Gestão de risco
│   ├── execution.py                # Módulo 5: Ordens IB
│   └── logger.py                   # Módulo 6: Logs + Telegram
├── tests/
│   ├── __init__.py
│   ├── test_data_feed.py
│   ├── test_grid_engine.py
│   ├── test_signal_engine.py
│   ├── test_risk_manager.py
│   ├── test_execution.py
│   ├── test_logger.py
│   └── test_integration.py
├── data/
│   ├── grids_state.json
│   ├── trades_log.json
│   └── metrics.json
└── research/                       # NÃO TOCAR — investigação existente
    ├── BLOCO_A_METODOS_COMPLETOS.md
    ├── BLOCO_B_LIVROS_COMPLETOS.md
    ├── BLOCO_C_D_COMPARACOES_TEMAS.md
    ├── FASE_1_3_INVENTARIO_TAXONOMIA_GAPS.md
    └── FASE_4_8_LIVROS_COMPARACOES_RISK_PRIORIDADES.md
```

</output_esperado>

---

<retoma>

## Sistema de Retoma

**ANTES de começar qualquer trabalho, o Agente 1 (Orquestrador) DEVE:**

### Se `context.md` EXISTE:
1. Ler `context.md` integralmente
2. Identificar o último módulo aprovado
3. Identificar módulos pendentes e seus estados
4. Verificar issues abertos
5. Retomar a partir do primeiro módulo NÃO aprovado
6. Anunciar: "Retomando do módulo {N}: {nome}. Últimos {M} módulos aprovados."

### Se `context.md` NÃO EXISTE:
1. Criar `context.md` com estado inicial
2. Começar do PASSO 0 (ver <instrucao_final>)
3. Anunciar: "Iniciando projeto do zero. PASSO 0: extrair parâmetros da investigação."

### Formato do `context.md`:
```markdown
# Context — Bot Trading Autónomo
Última atualização: {timestamp}

## Estado dos Módulos
| Módulo | Estado | Agente | Aprovado Tester | Aprovado Auditor |
|--------|--------|--------|-----------------|------------------|
| PASSO 0: EXTRACTED_PARAMS | ✅ Completo | - | - | - |
| Esqueleto (Arquiteto) | ✅ Completo | Agente 2 | - | - |
| data_feed | ✅ Completo | Agente 3 | ✅ | ✅ |
| grid_engine | 🔄 Em progresso | Agente 4 | ⏳ | ⏳ |
| signal_engine | ⏳ Pendente | Agente 5 | ⏳ | ⏳ |
| risk_manager | ⏳ Pendente | Agente 6 | ⏳ | ⏳ |
| execution | ⏳ Pendente | Agente 3 | ⏳ | ⏳ |
| logger | ⏳ Pendente | Agente 7 | ⏳ | ⏳ |
| Integração | ⏳ Pendente | Agente 8 | ⏳ | ⏳ |
| Auditoria Final | ⏳ Pendente | Agente 9 | - | ⏳ |

## Decisões Tomadas
- {data}: {decisão e justificação}

## Issues Resolvidos
- {data}: {issue e resolução}

## Blockers Ativos
- {nenhum ou lista}
```

</retoma>

---

<definition_of_done>

## Definition of Done

O bot SÓ está pronto quando TODAS as condições seguintes são verdadeiras:

### 1. Módulos Aprovados
- [ ] Todos os 6 módulos implementados (data_feed, grid_engine, signal_engine, risk_manager, execution, logger)
- [ ] Cada módulo aprovado pelo Agente 8 (Tester) com 100% dos testes a passar
- [ ] Cada módulo sem issues do Agente 9 (Auditor)

### 2. Auditoria de Segurança
- [ ] Relatório completo do Agente 9 sem nenhum FAIL
- [ ] Zero credenciais hard-coded
- [ ] PAPER_TRADING=true por defeito confirmado
- [ ] Stop-loss em CADA ordem confirmado
- [ ] Risk of ruin calculado e < 0.1%

### 3. Teste de Integração
- [ ] Ciclo autónomo simulado com 100 trades fictícios completado
- [ ] Passagem por 3 regimes (BULL→BEAR→SIDEWAYS) simulada
- [ ] Kill switch testado e funcionando
- [ ] Reconnect testado e funcionando
- [ ] Rebuild de estado (JSON corrompido) testado e funcionando

### 4. Backtest com Dados Reais
- [ ] Backtest com dados históricos do IB (mínimo 1 ano)
- [ ] Resultados documentados: win rate, payoff ratio, max drawdown, Sharpe
- [ ] Os 7 pitfalls de backtesting validados (ver checklist do Agente 8)
- [ ] Out-of-sample validation realizada

### 5. Paper Trading
- [ ] Bot correu 30 minutos em paper trading sem erros
- [ ] Pelo menos 1 grid aberta e gerida autonomamente
- [ ] Pelo menos 1 alerta Telegram recebido com sucesso
- [ ] Estado persistido e recuperado após reinício

### 6. Documentação
- [ ] README.md criado com instruções completas de setup:
  - Pré-requisitos (Python, IB Gateway/TWS)
  - Instalação (pip install, .env setup)
  - Configuração do IB Gateway
  - Configuração do bot Telegram
  - Como arrancar em paper trading
  - Como monitorizar
  - Como parar
  - FAQ com troubleshooting

### 7. Relatório Final
- [ ] Relatório do Agente 9 com:
  - Risk of ruin calculado
  - Win rate esperado (backtest)
  - Max drawdown esperado
  - Sharpe ratio esperado
  - Instruções detalhadas para passar a conta real
  - Aviso de risco explícito

</definition_of_done>

---

<instrucao_final>

## Instrução Final — Sequência de Execução

### PASSO 0 (OBRIGATÓRIO — antes de qualquer código)
**Antes de iniciar qualquer agente ou escrever qualquer linha de código:**

1. Ler TODOS os ficheiros `.md` na pasta `research/`:
   - `FASE_1_3_INVENTARIO_TAXONOMIA_GAPS.md`
   - `FASE_4_8_LIVROS_COMPARACOES_RISK_PRIORIDADES.md`
   - `BLOCO_A_METODOS_COMPLETOS.md`
   - `BLOCO_B_LIVROS_COMPLETOS.md`
   - `BLOCO_C_D_COMPARACOES_TEMAS.md`

2. Criar `EXTRACTED_PARAMS.md` com:
   - **Todos os indicadores e parâmetros exatos** extraídos (SMA25, RSI, ATR, Bollinger — com períodos e limiares)
   - **Todas as regras de risco com valores concretos** (1% por trade, R:R 1:2, daily 3%, weekly 6%, monthly 10%, Half-Kelly)
   - **Estratégias selecionadas e justificação** (Kotegawa mean reversion como filtro, grid trading como execução)
   - **Parâmetros de grid recomendados** (espaçamento ATR, número de níveis por regime, condições de re-centrar)
   - **Limiares de regime detection** (BULL/BEAR/SIDEWAYS com condições exatas)
   - **7 backtesting pitfalls** e como cada um é tratado no código
   - **Métricas de performance** a calcular com targets (Sharpe ≥ 1.0, profit factor > 1.5, etc.)

3. Só depois de `EXTRACTED_PARAMS.md` criado e validado, iniciar os agentes.

### PASSO 1 — Agente 2 (Arquiteto)
- Criar estrutura completa de ficheiros
- Definir interfaces entre módulos
- Criar esqueleto com assinaturas e docstrings
- Criar `config.py` e `.env.example`

### PASSO 2 — Agentes 3, 4, 5, 6, 7 (em PARALELO)
- Agente 3: implementa `data_feed.py` e `execution.py`
- Agente 4: implementa `grid_engine.py`
- Agente 5: implementa `signal_engine.py`
- Agente 6: implementa `risk_manager.py`
- Agente 7: implementa `logger.py`

**REGRA DE PARALELISMO:**
- Agentes 3, 4, 5, 6 e 7 trabalham em PARALELO
- Cada agente pode levantar BLOCKER a qualquer momento
- Agente 1 resolve conflitos e desbloqueia

### PASSO 3 — Agente 8 (Tester)
- Testa cada módulo individualmente
- Testa integração com ciclo completo
- Valida os 7 pitfalls de backtesting
- Corre backtest com dados históricos (1 ano mínimo)
- **Só aprova módulo quando 100% dos testes passam**
- Se falhar: devolve ao agente responsável com detalhes

### PASSO 4 — Agente 9 (Auditor)
- Auditoria completa de segurança (checklist acima)
- Cálculo de risk of ruin
- Verificação de cenários de falha
- Relatório final

### PASSO 5 — Agente 1 (Orquestrador)
- Implementa `main.py` (loop autónomo principal)
- Cria `README.md`
- Verifica Definition of Done
- Corre bot em paper trading por 30 minutos
- Gera relatório final

### Regras do Swarm
1. Agentes 3, 4, 5, 6, 7 trabalham em **PARALELO** (PASSO 2)
2. Agente 8 valida **CADA módulo** antes de avançar para o seguinte (PASSO 3)
3. Agente 9 faz auditoria **FINAL** de segurança (PASSO 4)
4. Qualquer agente pode levantar **BLOCKER** — o Agente 1 decide como resolver
5. Agente 1 tem **autoridade final** em caso de conflito
6. `context.md` é atualizado após **CADA módulo** aprovado
7. Se um módulo é reprovado pelo Tester ou Auditor, volta ao agente responsável — NÃO avança

### COMEÇA AGORA
Executa o PASSO 0 imediatamente. Lê a investigação, cria EXTRACTED_PARAMS.md, e inicia a construção módulo a módulo.

</instrucao_final>

# EXTRACTED_PARAMS.md — Parâmetros Extraídos da Investigação

> Compilação de todos os parâmetros concretos extraídos dos 5 ficheiros de research.
> Este ficheiro serve de referência para a implementação do bot.

---

## 1. Indicadores Técnicos — Parâmetros Exatos

| Indicador | Período | Uso | Limiares |
|-----------|---------|-----|----------|
| **SMA(25)** | 25 dias | Indicador central Kotegawa (deviation) | Fórmula: `((preço - SMA25) / SMA25) × 100` |
| **SMA(50)** | 50 dias | Filtro de tendência macro (regime detection) | Cruzamento com SMA(200) |
| **SMA(200)** | 200 dias | Filtro de tendência macro (regime detection) | Preço acima/abaixo define trend |
| **RSI(14)** | 14 períodos | Confirmação de sobrevenda/sobrecompra | < 30 sobrevenda, > 70 sobrecompra |
| **ATR(14)** | 14 períodos | Position sizing, espaçamento de grid, stops | Dinâmico por ativo |
| **Bollinger Bands** | 20 períodos, 2σ | Confirmação de extremos | Preço abaixo da banda inferior = confirmação |
| **Volume Médio** | 20 períodos | Baseline para spikes de volume | Volume > 150% da média = confirmação |

---

## 2. Regime Detection — Condições Exatas

```
BULL:     preço > SMA(200) E SMA(50) > SMA(200) E RSI(14) > 50
BEAR:     preço < SMA(200) E SMA(50) < SMA(200) E RSI(14) < 50
SIDEWAYS: nenhuma das anteriores OU ATR(14) < 50% da média ATR de 60 dias
```

- Sideways por baixa volatilidade tem **prioridade** sobre BULL/BEAR
- Recalibrar regime a **cada barra diária**
- Transição de regime = **alerta Telegram obrigatório**

---

## 3. Estratégia Kotegawa (SMA25 Deviation) — Filtro de Entrada

### Fórmula
```
deviation = ((preço_atual - SMA25) / SMA25) × 100
```

### Limiares por Regime

| Regime | Mínimo | Ótimo |
|--------|--------|-------|
| BULL | ≤ -5% | ≤ -10% |
| BEAR | ≤ -20% | ≤ -40% |
| SIDEWAYS | ≤ -10% | ≤ -20% |

### Confirmações (cada uma adiciona confiança)
1. RSI(14) < 30 → +1
2. Preço < Bollinger Lower Band → +1
3. Volume > 150% da média 20 dias → +1

### Score de Confiança

| Confirmações | Confiança | Size Multiplier | Ação |
|-------------|-----------|-----------------|------|
| 0 | BAIXO | 0% | NÃO operar |
| 1 | MEDIO | 50% | Operar com metade |
| 2 | MEDIO | 75% | Operar com 75% |
| 3 | ALTO | 100% | Operar com 100% |

### Padrões de Vela de Confirmação (opcional)
- Hammer, Bullish Engulfing

### Holding Period Típico
- 2-6 dias (referência para take-profit)

---

## 4. Gestão de Risco — Valores Concretos

### Risco por Nível
- **1% do capital** por nível de grid (hard limit)
- **Cap máximo: 5%** independentemente do Kelly

### Rácios
- **R:R mínimo: 1:2** (alvo ≥ 2× risco)
- Stop-loss por nível: **1.5× ATR(14)** abaixo do preço de entrada
- Take-profit por nível: **2× ATR(14)** acima do preço de entrada

### Kill Switches

| Limite | Valor | Ação |
|--------|-------|------|
| Daily loss | 3% do capital | Pausa automática |
| Weekly loss | 6% do capital | Pausa automática |
| Monthly drawdown | 10% do capital | Kill switch — para tudo, alerta Telegram, só reinicia com confirmação manual |

### Limites de Exposição
- Máximo posições simultâneas: **5-8** (configurável)
- Máximo grids ativas simultâneas: **3** (configurável)

### Regras Absolutas
- Stop-loss em **CADA** ordem — sem exceção
- **ZERO averaging down** — NUNCA comprar mais num nível em perda
- **PAPER_TRADING=true** por defeito — NUNCA desativar sem confirmação

---

## 5. Half-Kelly Criterion — Position Sizing

### Fórmula
```
K = W - (1 - W) / R

Onde:
  W = win_rate (ex: 0.50)
  R = payoff_ratio (ex: 2.0)

Half-Kelly: position_pct = K / 2
```

### Exemplo
```
W=0.50, R=2.0
K = 0.50 - 0.50/2.0 = 0.25 (25%)
Half-Kelly = 12.5%
Cap = min(12.5%, 5%) = 5%
```

### Propriedades
- Half-Kelly captura ~75% do crescimento com ~50% da volatilidade
- Cap máximo: nunca mais de **5% do capital** por nível

---

## 6. Risk of Ruin

| Risco/Trade | Win Rate | R:R | Risk of Ruin |
|-------------|----------|-----|-------------|
| 1% | 50% | 2:1 | ≈ 0% |
| 5% | 50% | 2:1 | ≈ 13% (INACEITÁVEL) |
| 10% | 50% | 2:1 | > 50% (CATASTRÓFICO) |

- **Meta: Risk of Ruin < 0.1%**
- Recalcular após cada 50 trades com win rate e payoff reais
- Se risk of ruin > 1% → bot RECUSA arrancar

---

## 7. Grid Trading — Parâmetros

### Espaçamento
- Entre níveis: **1× ATR(14)** do timeframe diário

### Número de Níveis por Regime

| Regime | Níveis | Lógica |
|--------|--------|--------|
| BULL | 5 | Grids mais apertadas, foco em tendência |
| BEAR | 7-10 | Grids mais largas, foco em mean reversion |
| SIDEWAYS | 6-8 | Grids normais |

### Re-centrar
- Quando preço ultrapassa **70% da extensão** da grid

### Estrutura por Nível
- Ordem limit de compra
- Stop-loss individual: preço_compra - 1.5× ATR(14)
- Take-profit individual: preço_compra + 2× ATR(14)

---

## 8. Métricas de Performance — Targets

| Métrica | Fórmula | Target |
|---------|---------|--------|
| Win Rate | trades_ganhos / total_trades | Contextual (com payoff ratio) |
| Payoff Ratio | média_ganho / média_perda | ≥ 2.0 |
| Expectancy | (prob_ganho × ganho_medio) - (prob_perda × perda_media) | > 0 |
| Max Drawdown | maior queda pico-vale | Monitorizar |
| Sharpe Ratio | retorno_excess / volatilidade | ≥ 1.0 bom, ≥ 2.0 excelente |
| Profit Factor | gross_profit / gross_loss | > 1.5 |
| Nº Trades Mínimo | — | 100+ para significância |

---

## 9. Os 7 Backtesting Pitfalls — Tratamento no Código

| # | Pitfall | Como Tratar |
|---|---------|------------|
| 1 | **Overfitting/Data Snooping** | Máximo 5 parâmetros otimizados |
| 2 | **Lookahead Bias** | Verificar que dados usados existiam no momento do sinal |
| 3 | **Survivorship Bias** | Usar dados point-in-time com delisted stocks |
| 4 | **Assumption Errors** | Modelar slippage, gaps, dividendos |
| 5 | **Data Mining Bias** | Usar out-of-sample e walk-forward |
| 6 | **Regime Change** | Testar em bull, bear e sideways (incluir 2008, 2020, 2022) |
| 7 | **Custos Subestimados** | Incluir spreads, comissões, swaps, market impact |

### Framework de Validação
1. In-sample development (ex: 2000-2015)
2. Out-of-sample validation (ex: 2016-2020)
3. Walk-forward re-optimization
4. Monte Carlo randomization
5. Stress test (períodos de crise)
6. Paper trading: 3-6 meses
7. Mínimo 100+ trades (idealmente 200+)

---

## 10. Mercados Suportados (via IB)

| Mercado | Exemplos | Contrato IB |
|---------|----------|-------------|
| Ações US | AAPL, MSFT, TSLA | Stock |
| Ações EU | SAP, ASML, Siemens | Stock |
| ETFs | SPY, QQQ, VWCE | Stock |
| Forex | EUR/USD, GBP/USD, USD/JPY | Forex |
| CFDs | Índices | CFD |
| Micro Futuros | MES ($1.25/tick), MNQ ($0.50/tick), MYM | Future |

---

## 11. Estratégia Selecionada — Justificação

**Filtro de Entrada:** Kotegawa (SMA25 Deviation + confirmações)
- Baseado no caso real de Kotegawa/BNF: ¥1.64M → ¥21B (~1,300,000% retorno)
- Win rate histórico: ~60%
- Mean reversion com confirmação técnica
- Holding period 2-6 dias (swing trading)

**Motor de Execução:** Grid Trading
- Operação autónoma 24/7 sem intervenção humana
- Múltiplos níveis de entrada distribuídos por ATR
- Gestão automática de take-profit e stop-loss por nível
- Re-centrar dinâmico quando preço move

**Gestão de Risco:** Half-Kelly + Kill Switches
- Position sizing matemático (não arbitrário)
- Limites automáticos em múltiplas timeframes (diário, semanal, mensal)
- Risk of ruin calculado e validado

**Perfil Ideal:** 1-2h/dia, swing trading, conta pequena a média
- EOD analysis (uma vez por dia)
- Bot gere tudo autonomamente após configuração

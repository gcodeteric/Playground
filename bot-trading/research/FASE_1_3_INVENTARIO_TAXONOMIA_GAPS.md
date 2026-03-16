# INVESTIGAÇÃO-MÃE — FASES 1 a 3
## Inventário Mestre, Taxonomia Canónica e Gap Analysis

---

# PARTE 1 — INVENTÁRIO MESTRE EXTRAÍDO DOS 3 FICHEIROS + PDF KOTEGAWA

## 1.1 MÉTODOS E ESTRATÉGIAS IDENTIFICADOS

### Estratégias por família lógica

**A. Trend Following / Seguimento de Tendência**
- Comprar em tendências de alta, vender/ficar fora nas de baixa
- Ferramentas: MAs (50/200), MACD, linhas de tendência
- Exemplo: comprar quando índice fecha acima da MA 200, vender quando fecha abaixo
- Livros associados: Following the Trend (Clenow), Trend Following (Covel — implícito)

**B. Range Trading**
- Mercado preso entre suporte e resistência
- Comprar perto do suporte, vender perto da resistência
- Ferramentas: S/R, RSI, osciladores

**C. Breakout**
- Entrada quando preço rompe nível importante com volume
- Máximos/mínimos, consolidações, padrões gráficos

**D. Momentum**
- Comprar ativos com força recente, vender/short os fracos
- Assume continuação da força

**E. Mean Reversion / Reversão à Média**
- Preço desvia-se da média e tende a regressar
- Ferramentas: Bollinger Bands, RSI extremo
- **Caso Kotegawa (BNF)**: 25-day MA deviation rate como indicador central; compra de ações extremamente oversold com limiares ajustados por setor e regime de mercado

**F. News / Event-Driven**
- Volatilidade causada por notícias, dados macro, resultados
- Calendários económicos, execução rápida

**G. Pairs Trading**
- Long num ativo + short noutro correlacionado
- Aposta na convergência do spread

**H. Arbitragem**
- Explorar diferenças de preço entre mercados/produtos
- Mais institucional que retalhista

**I. Opções — Income / Volatilidade**
- Venda de prémio: covered calls, credit spreads
- Gerar income assumindo preço dentro de faixa
- Exploração de volatilidade (Natenberg, McMillan)

**J. Trading Algorítmico / Sistemático**
- Regras automáticas em código
- Alta frequência a baixa frequência
- Referências: Chan, López de Prado, Carver

**K. Sector Rotation (Kotegawa Fase 2)**
- Comprar laggards dentro de setores em rally
- "Sympathy rallies" — stocks correlacionados dentro de indústria
- 80% momentum na fase bull vs 80% contrarian na fase bear

**L. Sequential Swing Trading (連動スイングトレード — Kotegawa)**
- Agrupamento de ações por indústria
- Tracking de correlação com Nikkei 225
- Compra de laggards que ainda não subiram

---

## 1.2 ESTILOS DE TRADING POR HORIZONTE TEMPORAL

| Estilo | Horizonte | Mencionado | Notas |
|--------|-----------|------------|-------|
| Scalping | Segundos a minutos | Sim (Inv 1) | Exige tempo quase full-time, infraestrutura profissional |
| Day Trading | Intradiário | Sim (Inv 1, 2) | Fecha posições no mesmo dia |
| Swing Trading | Dias a semanas | Sim (todos) | Recomendado para 1-2h/dia |
| Position Trading | Semanas a meses | Sim (Inv 1) | Macro + tendência de longo prazo |
| End-of-Day | Decisões no fecho | Sim (Inv 1) | Adequado para tempo limitado |
| Investing (longo prazo) | Meses a anos | Sim (Inv 2) | Value, growth, index investing |
| Kotegawa (BNF) | 2-6 dias típico | Sim (PDF) | Swing trader mean-reversion |

---

## 1.3 FERRAMENTAS DE ANÁLISE TÉCNICA IDENTIFICADAS

### Indicadores e conceitos

1. **Candlesticks / Price Action**
   - Hammer, Shooting Star, Doji, Spinning Top
   - Engulfing (bullish/bearish)
   - Morning Star, Evening Star
   - Three White Soldiers
   - Padrões de continuação

2. **Médias Móveis (MA)**
   - SMA (Simple Moving Average) — 20, 50, 200
   - EMA (Exponential Moving Average) — reage mais rápido
   - Cruzamentos (ex: EMA 20 × SMA 50)
   - MA como suporte/resistência dinâmica
   - VWMA (Volume Weighted MA)
   - 25-day SMA deviation rate (Kotegawa)

3. **RSI (Relative Strength Index)**
   - Escala 0-100
   - Sobrecompra >70, sobrevenda <30
   - Divergências
   - Kotegawa usava RSI <30 como confirmação

4. **MACD**
   - Mencionado como ferramenta de tendência

5. **Bollinger Bands**
   - Bandas de volatilidade
   - Preço em extremos como sinal de reversão
   - Kotegawa usava como confirmação

6. **Volume**
   - Validação de breakouts
   - VWMA
   - Volume spikes (>50% acima do normal — Kotegawa)
   - Volume Profile (volume por nível de preço)

7. **ATR (Average True Range)**
   - Position sizing
   - Definição de distância de stops

8. **Suporte / Resistência**
   - Níveis horizontais
   - Linhas de tendência
   - Zonas dinâmicas (MAs)

9. **Order Flow / Microestrutura**
   - Livro de ordens (order book)
   - Heatmap de liquidez (Bookmap)
   - Footprint charts
   - Tape reading
   - Ordens limit vs mercado
   - Desequilíbrios de oferta/procura

10. **Volume Profile**
    - Volume histórico por preço
    - Zonas de liquidez
    - Point of Control, Value Area

11. **Nikkei 225 Futures como leading indicator** (Kotegawa)

---

## 1.4 GESTÃO DE RISCO E POSITION SIZING

### Conceitos identificados

1. **Risco por trade**: 0.25–2% do capital (consenso: 1-2%)
2. **Position sizing**: risco monetário / (entrada - stop)
3. **R:R (Risk-Reward Ratio)**: mínimo 1:2 recomendado
4. **Limite de perda diária**: 3-5% da conta
5. **Stop-loss**: técnico, baseado em suporte/resistência
6. **Trailing stop**: seguir tendência
7. **Max drawdown**: maior queda pico-vale
8. **Win rate**: por si só irrelevante sem payoff ratio
9. **Payoff ratio**: média ganho / média perda
10. **Expectancy**: (prob ganho × ganho médio) – (prob perda × perda média)
11. **Volatilidade do equity curve**
12. **Alavancagem**: amplifica ganhos e perdas; evitar excesso
13. **Cash-only trading** (Kotegawa: sem margem nos primeiros anos)
14. **Nunca fazer averaging down** (regra explícita de Kotegawa)
15. **Stop automático cortando posições imediatamente** (Kotegawa: 1-2% capital por trade)
16. **Regra dos 50 trades consecutivos**: Kotegawa podia absorver 50 losses seguidos e manter ~75% do capital

### Métricas de performance

- Taxa de acerto (win rate)
- Payoff ratio
- Expectância
- Max drawdown
- Volatilidade do equity curve
- Kotegawa: ~60% win rate, edge vinha de cortar perdas a 1-2% e deixar winners correr

---

## 1.5 PSICOLOGIA E DISCIPLINA

### Conceitos identificados

1. Medo e ganância como sintomas de risco mal definido
2. FOMO (Fear Of Missing Out)
3. Revenge trading
4. Overtrading
5. Necessidade de ter razão
6. Disciplina > estratégia
7. Diário de trading (screenshots, emoções, justificações)
8. Pausar após série de perdas (ex: 24h após 3 perdas)
9. Tratar conta como negócio, não casino
10. **Kotegawa — psicologia extrema**:
    - Desapego total do dinheiro ("If you care about money, you cannot successfully trade")
    - Avaliar trades pela qualidade da decisão, não pelo lucro
    - Rotina rígida: acordar 8:15, evitar relatórios de analistas, 1h de revisão focada em emoções
    - Admitiu que "missing out on profits is as painful as losing"
    - Único colapso emocional registado: trade Lehman Brothers (~¥700M perdidos, partiu 2 monitores)
    - Lição: ficar dentro do círculo de competência
    - Recusou gerir dinheiro de outros, escrever livros, vender cursos

---

## 1.6 CLASSES DE ATIVOS E MERCADOS

| Classe | Mencionada | Detalhe nos ficheiros |
|--------|-----------|----------------------|
| Ações | Sim | Swing, position, value investing |
| ETFs | Sim | Investing passivo, Bogle |
| Índices | Sim | S&P 500, DAX, NASDAQ, Nikkei 225 |
| Forex | Sim | Day/swing trading, Kathy Lien |
| Futuros | Sim | Hedging, spreads, trend following |
| Opções | Sim (Inv 3 aprofunda) | McMillan, Natenberg, Passarelli |
| Criptomoedas | Sim (Inv 2 aprofunda) | Bitcoin, altcoins, DeFi mencionado |
| CFDs/Derivados | Sim | Produto principal de retalho |
| Commodities | Menção implícita | Pouco desenvolvido |
| Obrigações | Menção marginal | Graham/Dodd, muito pouco |
| Real Estate | Kotegawa PDF | Pivot de Kotegawa para imobiliário |
| Japanese equities | Kotegawa PDF | Mercado específico explorado |

---

## 1.7 LIVROS IDENTIFICADOS (INVENTÁRIO BRUTO COMPLETO)

### Investimento / Value / Portfolios
1. The Intelligent Investor — Benjamin Graham
2. Security Analysis — Graham & Dodd
3. One Up On Wall Street — Peter Lynch
4. Beating the Street — Peter Lynch
5. Common Stocks and Uncommon Profits — Philip Fisher
6. The Little Book of Common Sense Investing — John C. Bogle
7. A Random Walk Down Wall Street — Burton Malkiel
8. The Most Important Thing — Howard Marks
9. Richer, Wiser, Happier — William Green
10. The Dhandho Investor — Mohnish Pabrai
11. The Four Pillars of Investing — William Bernstein
12. What Works on Wall Street — James O'Shaughnessy

### Trading (Sistemas, Técnica, Prática)
13. Market Wizards — Jack Schwager
14. The New Market Wizards — Jack Schwager
15. Trade Your Way to Financial Freedom — Van K. Tharp
16. The New Trading for a Living — Alexander Elder
17. Mastering the Trade — John Carter
18. How to Day Trade for a Living — Andrew Aziz
19. Day Trading and Swing Trading the Currency Market — Kathy Lien
20. The Master Swing Trader — Alan Farley
21. Think and Trade Like a Champion — Mark Minervini
22. Reminiscences of a Stock Operator — Edwin Lefèvre

### Psicologia
23. Trading in the Zone — Mark Douglas
24. The Disciplined Trader — Mark Douglas
25. The Psychology of Trading — Brett Steenbarger
26. The Daily Trading Coach — Brett Steenbarger
27. Market Mind Games — Denise Shull
28. The Mental Game of Trading — Jared Tendler

### Risco, Probabilidade, Macro
29. The Black Swan — Nassim Nicholas Taleb
30. Fooled by Randomness — Nassim Nicholas Taleb
31. Big Debt Crises — Ray Dalio
32. More Money Than God — Sebastian Mallaby

### Opções
33. Options as a Strategic Investment — Lawrence McMillan
34. Option Volatility & Pricing — Sheldon Natenberg
35. Trading Option Greeks — Dan Passarelli
36. Understanding Options — Michael Sincere
37. Trading Options for Dummies — Joe Duarte
38. The Options Playbook — Brian Overby
39. The Option Trader's Hedge Fund — Dennis Chen & Mark Sebastian

### Order Flow / Volume / Microestrutura
40. A Complete Guide to Volume Price Analysis — Anna Coulling
41. Order Flow & Volume Profile Forex Trading — Dominic Raye
42. Playbooks de Volume Profile / Order Book (Trader-Dale, etc.)

### Quant / Algorítmico
43. Quantitative Trading — Ernest P. Chan
44. Algorithmic Trading — Ernest P. Chan
45. Advances in Financial Machine Learning — Marcos López de Prado
46. Systematic Trading — Robert Carver
47. Inside the Black Box — Rishi Narang
48. Following the Trend — Andreas Clenow
49. Mechanical Trading Systems — Richard Weissman

### Cripto / Blockchain
50. Mastering Bitcoin — Andreas Antonopoulos
51. The Basics of Bitcoins and Blockchains — Antony Lewis
52. Cryptoassets — Chris Burniske & Jack Tatar
53. Blockchain Bubble or Revolution — Agashe, Mehta & Detroja
54. The Only Cryptocurrency Investing Book You'll Ever Need — Freeman Publications
55. The Bitcoin Standard — Saifedean Ammous
56. Crypto Trading for Ambitious Beginners — Willem Middelkoop et al.

### Histórias / Biografias
57. Reminiscences of a Stock Operator — Lefèvre (já listado)
58. Market Wizards série — Schwager (já listado)
59. More Money Than God — Mallaby (já listado)

---

## 1.8 AUTORES IDENTIFICADOS

Benjamin Graham, David Dodd, Peter Lynch, Philip Fisher, John C. Bogle, Burton Malkiel, Howard Marks, William Green, Mohnish Pabrai, William Bernstein, James O'Shaughnessy, Jack Schwager, Van K. Tharp, Alexander Elder, John Carter, Andrew Aziz, Kathy Lien, Alan Farley, Mark Minervini, Edwin Lefèvre, Mark Douglas, Brett Steenbarger, Denise Shull, Jared Tendler, Nassim Nicholas Taleb, Ray Dalio, Sebastian Mallaby, Lawrence McMillan, Sheldon Natenberg, Dan Passarelli, Michael Sincere, Joe Duarte, Brian Overby, Dennis Chen, Mark Sebastian, Anna Coulling, Dominic Raye, Ernest P. Chan, Marcos López de Prado, Robert Carver, Rishi Narang, Andreas Clenow, Richard Weissman, Andreas Antonopoulos, Antony Lewis, Chris Burniske, Jack Tatar, Saifedean Ammous, Willem Middelkoop, Takashi Kotegawa (BNF)

---

## 1.9 CASO KOTEGAWA (BNF) — SÍNTESE DO PDF

### Dados biográficos
- Nascido: 5 março 1978, Ichikawa, Chiba, Japão
- Formação: dropout de Nihon University (Direito), 2 créditos de terminar
- Inspiração: documentário NHK "Money Revolution" (1998), perfil de Victor Niederhoffer
- Pseudónimo: BNF (transliteração fonética japonesa de V.N.F. = Victor Niederhoffer)
- Capital inicial: ¥1.64 milhões (~$13,600) em 2000
- Capital final: ~¥21 mil milhões (~$185M) em 2008
- Retorno cumulativo: ~1,300,000% em 8 anos (~170% anualizado)

### Método central
- Mean-reversion swing trading usando taxa de desvio da 25-day SMA
- Fórmula: ((Preço Atual − 25-day SMA) / 25-day SMA) × 100
- Limiares de compra ajustados por setor e regime de mercado
- Bear market 2001-2003: exigia desvios de -20% a -60% dependendo do setor
- Bull market 2006: recalibrou para -5% a -15%
- Confirmação com RSI <30, Bollinger Bands extremos, volume spikes >50%, candlestick patterns (engulfing, hammer)
- Holding period típico: 2-6 dias
- Monitorizava 600-700 ações em 3 computadores, 1-2 laptops, 6 monitores

### Evolução por fases
1. 2001-2003: Bear market contrarian (80% contrarian)
2. 2003-2005: Bull market sector rotation (80% momentum)
3. 2005-2008: Large-cap scaling
4. 2008+: Diversificação para imobiliário e position trading

### Risk management
- Máximo 1-2% capital por trade
- Stop-loss automático
- Nunca averaging down
- Cash-only (sem margem nos primeiros anos)
- Win rate ~60%
- Edge: cortar losses rápido, deixar winners correr para a média

### Trade J-Com (8 Dez 2005)
- Fat-finger da Mizuho Securities: venda de 610,000 ações a ¥1 em vez de 1 ação a ¥610,000
- Kotegawa comprou 7,100 ações durante o crash
- Lucro: ~¥2.2 mil milhões (~$20M) em ~10 minutos
- Resultado: Mizuho perdeu ¥40.7 mil milhões, presidente da TSE demitiu-se

### Pivot para imobiliário
- Comprou edifício Chomp Chomp Akihabara por ~¥9B em 2008
- Vendeu em 2018 por ~¥12-13B + ~¥7B em rendas = ~¥10B retorno total
- Comprou AKIBA Cultures ZONE, construiu Lydia Building em Sapporo
- Apareceu como acionista em 19 empresas cotadas (2014-2021)

### Lições extraídas
1. Process > outcome (avaliar qualidade da decisão, não lucro)
2. Adaptabilidade radical dentro de framework disciplinado
3. Paradoxo da escala (sucesso destruiu o edge original)
4. Detachment do dinheiro como vantagem psicológica
5. Círculo de competência (erro Lehman)
6. Nunca vendeu cursos, livros, ou geriu dinheiro alheio

---

# PARTE 2 — TAXONOMIA CANÓNICA INICIAL

## 2.1 Taxonomia por tipo de atividade

```
MERCADOS FINANCEIROS
├── INVESTIMENTO (comprar e manter)
│   ├── Value Investing (Graham, Buffett, Pabrai)
│   ├── Growth Investing (Fisher, Lynch)
│   ├── Index / Passive Investing (Bogle, Malkiel)
│   ├── Quality Investing
│   ├── Factor Investing (momentum, value, size, quality)
│   └── Portfolio Construction (Bernstein, Marks)
│
├── TRADING (especulação de curto/médio prazo)
│   ├── Por horizonte temporal
│   │   ├── Scalping
│   │   ├── Day Trading
│   │   ├── Swing Trading ← recomendado para o leitor
│   │   ├── Position Trading
│   │   └── End-of-Day
│   │
│   ├── Por lógica de edge
│   │   ├── Trend Following
│   │   ├── Mean Reversion
│   │   ├── Breakout
│   │   ├── Momentum
│   │   ├── Range Trading
│   │   ├── Event-Driven / News Trading
│   │   ├── Pairs / Statistical Arbitrage
│   │   ├── Carry Trade
│   │   ├── Seasonality
│   │   ├── Volatility Trading
│   │   ├── Arbitrage (pura)
│   │   └── Sector Rotation
│   │
│   ├── Por tipo de análise
│   │   ├── Price Action puro
│   │   ├── Análise Técnica (indicadores)
│   │   ├── Análise Fundamental
│   │   ├── Análise Macro / Global Macro
│   │   ├── Análise Quantitativa / Estatística
│   │   ├── Order Flow / Microestrutura
│   │   ├── Volume Profile / Market Profile
│   │   ├── Intermarket Analysis
│   │   ├── Sentiment Analysis
│   │   └── On-Chain Analysis (cripto)
│   │
│   ├── Por grau de automação
│   │   ├── Discricionário
│   │   ├── Sistemático (regras fixas, execução manual)
│   │   ├── Semi-automático (alertas + execução manual)
│   │   └── Algorítmico / Automático / HFT
│   │
│   └── Por instrumento
│       ├── Ações / Equities
│       ├── ETFs
│       ├── Índices (CFDs, futuros)
│       ├── Forex
│       ├── Futuros / Futures
│       ├── Opções
│       ├── Commodities
│       ├── Obrigações / Bonds
│       ├── Cripto spot
│       ├── Cripto perpétuos/futuros
│       └── DeFi (yield, staking, LPs)
│
├── GESTÃO DE RISCO
│   ├── Position Sizing
│   │   ├── Percent Risk Model (1-2%)
│   │   ├── Kelly Criterion
│   │   ├── Fixed Fractional
│   │   └── Volatility-based (ATR)
│   ├── Stop-Loss
│   │   ├── Técnico (S/R)
│   │   ├── Percentage-based
│   │   ├── ATR-based
│   │   └── Trailing
│   ├── Métricas
│   │   ├── Win Rate
│   │   ├── Payoff Ratio
│   │   ├── Expectancy
│   │   ├── Max Drawdown
│   │   ├── Sharpe Ratio
│   │   ├── Sortino Ratio
│   │   ├── Risk of Ruin
│   │   └── Portfolio Heat
│   └── Limites operacionais
│       ├── Risco diário
│       ├── Drawdown máximo tolerado
│       └── Regras de pausa
│
├── PSICOLOGIA
│   ├── Emoções destrutivas
│   │   ├── Medo
│   │   ├── Ganância
│   │   ├── FOMO
│   │   ├── Revenge trading
│   │   └── Overtrading
│   ├── Vieses cognitivos
│   │   ├── Aversão à perda
│   │   ├── Excesso de confiança
│   │   ├── Recency bias
│   │   ├── Confirmation bias
│   │   └── Anchoring
│   ├── Práticas de disciplina
│   │   ├── Journaling / Diário
│   │   ├── Rotina de trading
│   │   ├── Autoavaliação
│   │   └── Regras de pausa
│   └── Detachment (escola Kotegawa/Douglas)
│
├── BACKTESTING E SISTEMATIZAÇÃO
│   ├── Backtesting manual (scroll histórico)
│   ├── Backtesting programático (Python, Amibroker, etc.)
│   ├── Pitfalls
│   │   ├── Overfitting
│   │   ├── Lookahead bias
│   │   ├── Survivorship bias
│   │   └── Data snooping
│   ├── Validação
│   │   ├── Out-of-sample
│   │   ├── Walk-forward
│   │   └── Monte Carlo
│   └── Journaling e registo
│       ├── Screenshots
│       ├── R:R planeado vs real
│       ├── Emoções
│       └── Análise de erros de processo
│
└── INFRAESTRUTURA
    ├── Plataformas (MetaTrader, TradingView, Bookmap, MarketSpeed)
    ├── Dados (qualidade, feeds, históricos)
    ├── Execução (slippage, spreads, comissões)
    └── Tecnologia (colocation, acesso direto — para HFT)
```

---

## 2.2 Taxonomia de livros por categoria

```
LIVROS
├── INVESTIMENTO FUNDAMENTAL
│   ├── Value: Graham, Dodd, Pabrai
│   ├── Growth: Fisher, Lynch
│   ├── Passivo/Índices: Bogle, Malkiel
│   ├── Multi-estilo: Marks, Green, Bernstein
│   └── Quantitativo-fundamental: O'Shaughnessy
│
├── TRADING (Prática e Sistemas)
│   ├── Generalistas: Elder, Tharp, Schwager
│   ├── Day Trading: Aziz, Carter
│   ├── Swing: Farley, Minervini
│   ├── Forex: Lien
│   └── Clássico/Histórico: Lefèvre
│
├── PSICOLOGIA
│   ├── Douglas (Trading in the Zone, Disciplined Trader)
│   ├── Steenbarger (Psychology of Trading, Daily Trading Coach)
│   ├── Shull (Market Mind Games)
│   └── Tendler (Mental Game of Trading)
│
├── RISCO E PROBABILIDADE
│   ├── Taleb (Black Swan, Fooled by Randomness)
│   ├── Dalio (Big Debt Crises)
│   └── Mallaby (More Money Than God)
│
├── OPÇÕES
│   ├── Fundamentais: McMillan, Natenberg
│   ├── Greeks: Passarelli
│   ├── Introdutórios: Sincere, Duarte, Overby
│   └── Prática/Negócio: Chen & Sebastian
│
├── ORDER FLOW / MICROESTRUTURA
│   ├── Coulling (Volume Price Analysis)
│   ├── Raye (Order Flow & Volume Profile Forex)
│   └── Playbooks diversos (Trader-Dale, etc.)
│
├── QUANT / ALGO
│   ├── Chan (Quantitative Trading, Algorithmic Trading)
│   ├── López de Prado (Advances in Financial ML)
│   ├── Carver (Systematic Trading)
│   ├── Narang (Inside the Black Box)
│   ├── Clenow (Following the Trend)
│   └── Weissman (Mechanical Trading Systems)
│
├── CRIPTO / BLOCKCHAIN
│   ├── Técnico: Antonopoulos (Mastering Bitcoin)
│   ├── Introdução: Lewis, Agashe/Mehta/Detroja
│   ├── Investimento: Burniske & Tatar, Ammous
│   └── Trading: Middelkoop, Freeman Publications
│
└── HISTÓRIAS / BIOGRAFIAS
    ├── Lefèvre (Reminiscences)
    ├── Schwager (Market Wizards série)
    ├── Mallaby (More Money Than God)
    └── Kotegawa/BNF (artigos, não livro)
```

---

# PARTE 3 — GAP ANALYSIS: O QUE FALTA NOS FICHEIROS

## 3.1 LACUNAS GRAVES (áreas fundamentais não cobertas ou muito fracas)

### A. Commodities
- Quase ausente nos 3 ficheiros
- Faltam: ouro, petróleo, gás natural, agrícolas, metais industriais
- Faltam livros clássicos de commodities trading
- Falta explicação de futures de commodities, contango, backwardation

### B. Obrigações / Fixed Income
- Menção marginal em Graham/Dodd
- Falta: curva de yields, credit spreads, duration, convexity
- Falta relação obrigações-ações-macro
- Faltam livros de fixed income trading

### C. Análise Fundamental aprofundada
- Mencionada superficialmente
- Faltam: demonstrações financeiras em detalhe, cash flow analysis, valuation models (DCF, multiples), quality metrics, competitive advantage frameworks (Moat)
- Faltam livros de Aswath Damodaran, Pat Dorsey, Joel Greenblatt

### D. Macro / Global Macro Trading
- Dalio mencionado parcialmente
- Faltam: ciclos económicos, política monetária, yield curve, inflation, intermarket analysis
- Faltam livros como: Principles (Dalio completo), Currency Wars, Global Macro Trading (Greg Gliner)

### E. Volatilidade como classe
- Natenberg mencionado para opções
- Falta: VIX, volatility surface, term structure, variance swaps, vol-of-vol
- Faltam livros de Euan Sinclair (Volatility Trading, Positional Option Trading)

### F. Kelly Criterion e Risk of Ruin
- Mencionados na taxonomia mas não desenvolvidos nos ficheiros
- Faltam detalhes de implementação, limitações, half-Kelly
- Faltam livros: Fortune's Formula (Poundstone), The Kelly Capital Growth Investment Criterion (MacLean et al.)

### G. Behavioural Finance académica
- Psicologia coberta via Douglas/Steenbarger
- Falta vertente académica: Kahneman (Thinking Fast and Slow), Thaler (Misbehaving, Nudge), Shiller (Irrational Exuberance)

### H. Portfolio Construction moderna
- Bernstein mencionado brevemente
- Falta: Modern Portfolio Theory, Efficient Frontier, Black-Litterman, Risk Parity, All-Weather
- Faltam livros: Meb Faber (Global Asset Allocation), Swensen (Unconventional Success)

### I. Market Microstructure académica
- Order flow coberto superficialmente
- Faltam livros académicos: Harris (Trading and Exchanges), Hasbrouck (Empirical Market Microstructure), O'Hara (Market Microstructure Theory)

### J. DeFi em profundidade
- Mencionado mas não desenvolvido
- Faltam: AMMs, impermanent loss, yield farming, liquidation cascades, MEV, bridges, oracles
- Faltam livros/recursos: How to DeFi (CoinGecko), DeFi and the Future of Finance (Harvey et al.)

### K. Futures Trading específico
- Clenow aborda futuros, mas falta profundidade
- Faltam: margin mechanics, rollover, contango/backwardation, basis, settlement
- Faltam livros: A Complete Guide to the Futures Market (Schwager), Futures Fundamentals

### L. Chart Patterns clássicos
- Candlesticks cobertos
- Faltam: head & shoulders, double tops/bottoms, triangles, flags, pennants, cups
- Falta livro: Technical Analysis of Stock Trends (Edwards, Magee & Bassetti) — o original de AT
- Falta livro: Encyclopedia of Chart Patterns (Bulkowski)

### M. Wyckoff Method
- Não mencionado em nenhum ficheiro
- Escola importante de price action/volume institucional
- Falta livro: Trades About to Happen (David Weis), estudos de Wyckoff

### N. Elliott Wave
- Não mencionado
- Controverso mas influente
- Falta livro: Elliott Wave Principle (Prechter & Frost)

### O. Fibonacci / Harmonic Patterns
- Não mencionados
- Populares mas controversos
- Faltam livros: Harmonic Trading (Scott Carney)

### P. ICT / Smart Money Concepts
- Não mencionados
- Escola moderna muito popular em retail trading
- Controversa mas amplamente seguida

### Q. Tape Reading clássico
- Mencionado como conceito, não desenvolvido
- Faltam livros: Tape Reading and Market Tactics (Humphrey Neill)

### R. Seasonal Trading
- Mencionado como família de edge, não desenvolvido
- Falta livro: Stock Trader's Almanac (Hirsch)

### S. Crypto on-chain analysis
- Mencionado como conceito, não desenvolvido
- Faltam: Glassnode metrics, MVRV, SOPR, exchange flows, miner metrics, NUPL

### T. Trading Execution prática
- Tipos de ordens mencionados brevemente
- Faltam: slippage real, market impact, execution algos, TWAP, VWAP execution
- Falta: diferença entre demo e real (psicologia e execução)

### U. Regulação e fiscalidade
- Completamente ausente
- Importante para quem quer viver de trading

### V. Autores e livros importantes em falta
- **Nicolas Darvas** — How I Made $2 Million in the Stock Market
- **Jesse Livermore** — How to Trade in Stocks (versão própria)
- **William O'Neil** — How to Make Money in Stocks (CANSLIM)
- **Linda Raschke** — Street Smarts
- **Larry Connors** — Short-Term Trading Strategies That Work
- **Nassim Taleb** — Antifragile, Skin in the Game (complementos)
- **Ed Seykota** — mencionado em Market Wizards mas sem livro dedicado
- **Richard Dennis / Turtle Traders** — Curtis Faith (Way of the Turtle)
- **Michael Covel** — Trend Following
- **Perry Kaufman** — Trading Systems and Methods
- **John Murphy** — Technical Analysis of the Financial Markets (a "bíblia" de AT)
- **Martin Pring** — Technical Analysis Explained
- **Steve Nison** — Japanese Candlestick Charting Techniques (o original)
- **Aswath Damodaran** — The Little Book of Valuation, Investment Valuation
- **Pat Dorsey** — The Little Book That Builds Wealth (moats)
- **Joel Greenblatt** — The Little Book That Beats the Market (Magic Formula)
- **Daniel Kahneman** — Thinking Fast and Slow
- **Richard Thaler** — Misbehaving
- **Robert Shiller** — Irrational Exuberance
- **Euan Sinclair** — Volatility Trading, Positional Option Trading
- **Larry Harris** — Trading and Exchanges
- **David Swensen** — Unconventional Success
- **Meb Faber** — Global Asset Allocation
- **William Poundstone** — Fortune's Formula

---

## 3.2 LACUNAS MODERADAS (cobertos mas incompletos)

1. **Divergências entre escolas** — mencionadas em alguns pontos mas sem comparação estruturada
2. **Adaptação a diferentes capitais** — pouco desenvolvido (conta de $1K vs $50K vs $500K)
3. **Custos reais de trading** — spreads, swaps, comissões, impacto na rentabilidade
4. **Correlação entre mercados** — mencionada implicitamente, não desenvolvida
5. **Regime detection** — Kotegawa fazia isto intuitivamente, mas falta framework
6. **Paper trading vs real** — mencionado brevemente, falta análise das diferenças psicológicas
7. **Ferramentas/plataformas específicas** — TradingView, MetaTrader mencionados; falta comparação
8. **Prop firms** — mencionadas como aviso, falta análise detalhada do modelo

---

## 3.3 CONTRADIÇÕES E TENSÕES DETECTADAS

1. **Kotegawa usou all-in sem risco nos primeiros anos** vs **regra dos 1-2%** que ele próprio depois seguiu — a agressividade inicial foi essencial para o crescimento exponencial, mas é impossível de replicar com gestão de risco prudente
2. **Trading como profissão** vs **maioria falha** — os ficheiros reconhecem ambos mas não quantificam taxas de sucesso reais
3. **Mean reversion vs Trend following** — apresentados como famílias separadas, mas Kotegawa demonstra que o mesmo trader pode usar ambos dependendo do regime
4. **Simplicidade** (poucos indicadores) vs **profundidade** (order flow, ML, quant) — não ficou claro quando vale a pena a complexidade adicional

---

# PARTE 4 — PLANO DE EXPANSÃO DA INVESTIGAÇÃO

## Áreas a investigar a fundo com pesquisa externa:

### Prioridade 1 (Fundamentais em falta)
1. Commodities trading — mercados, métodos, livros
2. Análise fundamental e valuation em profundidade
3. Global macro trading — framework, livros, aplicação
4. Chart patterns clássicos — Edwards/Magee, Bulkowski, Murphy
5. Wyckoff Method
6. John Murphy — Technical Analysis of the Financial Markets
7. Steve Nison — Japanese Candlestick Charting Techniques
8. Behavioural finance — Kahneman, Thaler, Shiller
9. Portfolio construction moderna
10. Futures mechanics em detalhe

### Prioridade 2 (Profundidade adicional)
11. Kelly Criterion e Risk of Ruin
12. Volatilidade como classe/trading de volatilidade
13. DeFi aprofundado
14. On-chain analysis cripto
15. ICT / Smart Money Concepts — análise crítica
16. Elliott Wave — análise crítica
17. Fibonacci / Harmonics — análise crítica
18. Regime detection frameworks
19. Autores e livros em falta (Darvas, O'Neil, Raschke, Connors, Covel, etc.)

### Prioridade 3 (Prático e comparativo)
20. Comparação estruturada entre escolas
21. Custos reais de trading por mercado
22. Prop firms — modelo, riscos, prós/contras
23. Plataformas e ferramentas — comparação
24. Regulação e fiscalidade básica
25. Adaptação de métodos a diferentes capitais
26. Paper vs real — diferenças documentadas

---

**STATUS**: Fases 1-3 completas. Inventário mestre extraído, taxonomia canónica construída, 25+ lacunas significativas identificadas, plano de expansão com 26 áreas prioritárias definido.

**PRÓXIMO PASSO**: Lançar investigação profunda externa cobrindo todas as lacunas e aprofundando cada método, livro e escola para construir os dossiers individuais das Fases 4-8.

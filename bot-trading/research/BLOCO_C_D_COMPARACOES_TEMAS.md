# BLOCO C: Comparações em Falta + BLOCO D: Áreas Temáticas Finas

---

# BLOCO C — 5 COMPARAÇÕES EM FALTA

## C1. Price Action Puro vs Indicadores Técnicos

| Dimensão | Price Action Puro | Indicadores Técnicos |
|----------|-------------------|---------------------|
| **Base** | Velas, S/R, padrões gráficos, volume puro | Fórmulas matemáticas aplicadas ao preço (RSI, MACD, MAs) |
| **Filosofia** | "O preço desconta tudo — ler diretamente o que o mercado faz" | "Transformar dados em sinais mais claros via filtros" |
| **Vantagem** | Sem lag — reage ao que está a acontecer agora. Universalmente aplicável. Simples conceptualmente. | Objectividade — sinais quantificáveis e backtestáveis. Reduz ambiguidade. Automatizável. |
| **Desvantagem** | Altamente subjetivo — dois traders vêem coisas diferentes no mesmo gráfico. Difícil de backtestar formalmente. | Lag inerente (indicadores baseados em dados passados). Falsos sinais em mercados laterais. Podem criar ilusão de precisão. |
| **Evidência** | Bulkowski (chart patterns) fornece dados quantitativos para alguns padrões. Wyckoff é price action puro. Poucos estudos académicos. | BLL (1992) — suporte para MA crossovers. Mas evidência recente mista (Marshall et al. 2006 — sem valor em DJIA). |
| **Para automação** | DIFÍCIL — reconhecimento de padrões visual é complexo de codificar | EXCELENTE — tudo é computável |
| **Para 1-2h/dia** | Funciona em daily charts | Funciona em daily charts |
| **Para iniciante** | Mais intuitivo mas mais subjetivo | Mais objectivo mas pode levar a "indicator soup" |
| **Perfil ideal** | Trader visual, intuitivo, que se sente confortável com ambiguidade | Trader analítico, que prefere regras claras e testáveis |
| **Resolução de conflito** | Quando PA e indicador discordam, praticantes experientes tipicamente confiam em PA |

**Veredito:** A melhor abordagem é **PA como estrutura primária + 1-2 indicadores como filtro/confirmação**. Usar PA para ler o contexto (tendência, S/R, padrão) e indicador (RSI, ATR) para confirmar e definir stops/sizing. Para o bot: indicadores são obrigatórios (programáveis), mas com lógica inspirada em PA (breakout de S/R com volume, por exemplo).

---

## C2. Order Flow / Microestrutura vs Chart-Based Trading Clássico

| Dimensão | Order Flow / Microestrutura | Chart-Based Trading Clássico |
|----------|----------------------------|------------------------------|
| **O que analisa** | Ordens reais no livro — quem está a comprar/vender, a que preço, com que tamanho | Preço e volume históricos representados graficamente |
| **Informação** | Em tempo real — o que está a acontecer AGORA no mercado | Retrospetiva — o que JÁ aconteceu |
| **Ferramentas** | Level 2/DOM, footprint charts, Bookmap, delta, cumulative delta, volume profile | Velas, chart patterns, MAs, RSI, MACD, Bollinger |
| **Vantagem** | Vê a "causa" por trás dos movimentos de preço. Identifica onde grandes players estão a operar. Antecipa antes do chart pattern se formar. | Simples, testável, acessível. Funciona em qualquer timeframe e mercado. Não requer dados caros. |
| **Desvantagem** | ~40% do volume é em dark pools (invisível). HFT cria ruído massivo. Requer dados caros e plataformas especializadas. Curva de aprendizagem íngreme. Incompatível com forex spot descentralizado. | Não mostra o "porquê" dos movimentos. Lag inerente. Não distingue entre retail e institucional. |
| **Mercados ideais** | Futuros centralizados (ES, NQ, CL, ZB) onde todo o fluxo é visível | Todos — universal |
| **Evidência académica** | Harris (2003), Hasbrouck (2007) — sólida em microestrutura teórica. Pouca evidência de rentabilidade para retail. | BLL (1992), Bulkowski (chart patterns) — evidência mista mas com dados quantitativos. |
| **Automação** | Possível mas complexa — interpretar order flow em código é desafiante | Excelente — tudo é computável |
| **Tempo necessário** | Alto — requer atenção constante ao livro de ordens | Baixo a moderado — análise pode ser EOD |
| **Para 1-2h/dia** | INCOMPATÍVEL para order flow em tempo real. Volume Profile (histórico) é compatível. | COMPATÍVEL |
| **Para iniciante** | Avançado — estudar depois de dominar AT clássica | Acessível desde o início |

**Veredito:** Chart-based trading clássico é a base obrigatória. Order flow é uma **camada adicional avançada** para quem opera futuros centralizados com tempo dedicado. Para o teu perfil (1-2h/dia, bot EOD), **chart-based com volume profile como complemento** é a combinação certa. Volume Profile pode ser integrado no bot como feature sem ser order flow em tempo real.

---

## C3. Forex vs Índices vs Ações vs Cripto (para retalhista)

| Dimensão | Forex | Índices (CFD/Futuros) | Ações | Cripto |
|----------|-------|-----------------------|-------|--------|
| **Liquidez** | Extrema ($7T+/dia) | Muito alta | Alta (large caps), baixa (small caps) | Alta (BTC/ETH), muito baixa (altcoins) |
| **Horário** | 24/5 | Quase 24/5 (futuros) | 6.5-9h/dia | 24/7 |
| **Alavancagem típica** | 30:1 a 500:1 (MUITO perigoso) | 10:1 a 20:1 | 2:1 a 5:1 (margem) | 1:1 (spot) a 125:1 (perpétuos) |
| **Custos** | Spread (0.5-2 pips) + swap overnight | Spread + comissão + swap | Comissão ($0-5) + stamp duty (UK) | Spread + trading fee (0.05-0.1%) + funding rate |
| **Trend behaviour** | Tendências macro longas (meses-anos) mas erráticas no curto prazo | Uptrend bias de longo prazo. Crash risk. | Muito variável por ação. Uptrend bias. | Ciclos extremos de 4 anos (halving). Volatilidade 3-5× ações. |
| **Análise fundamental** | Macro — taxas de juro, GDP, inflação, balança | Macro + earnings season dos componentes | Earnings, cash flow, valuation — muito rica | On-chain metrics, tokenomics, narrativas |
| **Regulação** | Forte (ESMA, FCA) | Forte | Muito forte | Fraca a moderada (evolving) |
| **Risco de contraparte** | Broker (regulados normalmente ok) | Broker ou exchange | Mínimo (ações são propriedade) | ALTO — exchange hacks, rug pulls, depegs |
| **Para iniciante** | Perigoso — alavancagem alta leva a perdas rápidas | Moderado — índices diversificam risco | **MELHOR opção** — transparente, regulado, diversificado | Perigoso — volatilidade extrema, scams frequentes |
| **Para 1-2h/dia** | Viável (diário) | Viável (diário) | Ideal (EOD analysis) | Viável mas stress 24/7 |
| **Custos reais mensais** | Spreads + swaps se mantiver posição. ~€30-100 para conta de €10K. | Similar. | Comissões mínimas em IB (~€5-20/mês). | Funding rates podem custar 0.01-0.1%/8h |
| **Para o bot (IB API)** | SIM — IB oferece forex | SIM — IB oferece índices via futuros e CFDs | SIM — core da IB | PARCIAL — IB oferece cripto limitado |

**Veredito:** Para começar, **ações e ETFs via IB** são o campo ideal: regulado, transparente, custos baixos, dados limpos, AT funciona bem. Adicionar índices via futuros/micro-futuros quando capital justificar. Forex como diversificação posterior. Cripto à parte, com exchange dedicada, NÃO como primeiro mercado.

---

## C4. Operar Manualmente vs Automatizar

| Dimensão | Manual | Automatizado |
|----------|--------|-------------|
| **Decisões** | Humano analisa e executa em tempo real | Algoritmo analisa e executa sem intervenção |
| **Emoção** | Presente — medo, ganância, hesitação afetam execução | Eliminada — executa mecanicamente |
| **Consistência** | Variável — humanos cansam, distraem-se, violam regras | Alta — segue regras 100% do tempo (se bem programado) |
| **Adaptabilidade** | Alta — humano adapta-se a contexto, regime, "feel" | Baixa — algoritmo faz o que foi programado, não se adapta a situações não previstas |
| **Velocidade** | Lenta (segundos a minutos) | Rápida (milissegundos a segundos) |
| **Backtesting** | Difícil e subjetivo | Fácil e replicável |
| **Custo de desenvolvimento** | Zero (além de educação) | Alto — requer programação, dados, infraestrutura |
| **Risco de overfitting** | Baixo (humano não otimiza parameters obsessivamente) | ALTO — é a principal armadilha |
| **Risco operacional** | Erro humano (wrong order, fat finger) | Bug de código, perda de conexão, dados corrompidos |
| **Escalabilidade** | Limitada pelo tempo humano | Ilimitada (pode operar múltiplos mercados 24/7) |
| **Para 1-2h/dia** | Funciona para swing/position/EOD | **IDEAL** — bot corre sozinho |
| **Caminho recomendado** | Começar manual para aprender. Depois automatizar. |

**Veredito:** O caminho ótimo é **começar manual → sistematizar regras → backtestar → automatizar**. Nunca automatizar algo que não operaste manualmente primeiro e não entendes profundamente. O bot de IB deve ser a codificação de regras que já validaste manualmente + via backtest.

---

## C5. Investimento Passivo (Index Investing) vs Stock Picking

| Dimensão | Passivo (Index/ETFs) | Stock Picking Ativo |
|----------|---------------------|---------------------|
| **Filosofia** | "Não tentes bater o mercado — sê o mercado" (Bogle) | "Com análise superior, podes encontrar oportunidades que o mercado subestima" |
| **Evidência** | SPIVA scorecard: >90% dos fundos ativos underperformam o S&P 500 a 15 anos. Malkiel: mercados são suficientemente eficientes para a maioria. | Factor investing funciona (Fama-French). Buffett, Lynch, Greenblatt demonstram que stock picking pode funcionar. Mas survivorship bias é real. |
| **Custos** | Ultra-baixos — TER de 0.03-0.20% (VTI, VWCE) | Altos — comissões, tempo, ferramentas, dados |
| **Tempo necessário** | Quase zero — setup uma vez, rebalancear anualmente | Alto — pesquisa, análise, monitorização constante |
| **Retorno esperado** | Market return (~8-10% anualizado historicamente para S&P 500) | Market return ± alpha (a maioria gera alpha negativo) |
| **Risco** | Risco de mercado puro (beta) | Risco de mercado + risco idiossincrático + risco de erro do analista |
| **Para quem** | A MAIORIA dos investidores. Quem não quer dedicar tempo. | Quem tem edge real, tempo dedicado, e disciplina para executar |
| **Verdade incómoda** | É provavelmente a melhor opção para 95%+ das pessoas | Os 5% que batem o mercado consistentemente quase todos usam regras e disciplina extrema |

**Veredito:** Ter uma **base passiva** (VWCE, VTI) como fundação do patrimônio é inteligente para qualquer pessoa, incluindo traders ativos. O trading ativo (swing/position/bot) é uma **camada adicional** que só justifica risco se tiveres edge demonstrado. Portfolio sugerido: 60-70% passivo + 30-40% trading ativo com capital dedicado.

---

# BLOCO D — ÁREAS TEMÁTICAS FINAS

## D1. COMMODITIES TRADING

### Mercados principais
- **Energia:** Petróleo (WTI, Brent), Gás Natural, Gasolina
- **Metais preciosos:** Ouro (GC), Prata (SI), Platina, Paládio
- **Metais industriais:** Cobre (HG), Alumínio, Zinco
- **Agrícolas:** Milho (ZC), Trigo (ZW), Soja (ZS), Café, Cacau, Açúcar
- **Soft commodities:** Algodão, Madeira

### Conceitos essenciais
- **Contango:** Preço futuro > preço spot. Normal em commodities com custo de armazenamento. ETFs de futuros perdem dinheiro fazendo "roll" em contango (ex: USO durante COVID 2020 — preço spot negativo).
- **Backwardation:** Preço futuro < preço spot. Sinal de escassez imediata. Favorável para posições long (roll yield positivo).
- **Basis:** Diferença entre preço spot e preço do futuro mais próximo.
- **Sazonalidade:** Commodities têm padrões sazonais fortes (ex: gás natural sobe no inverno, agrícolas dependem de ciclos de plantio/colheita).
- **Superciclos:** Ciclos longos (10-20 anos) de valorização ou depreciação de commodities, ligados a crescimento económico, urbanização, inflação.

### Para o bot
- Commodities via IB: micro futuros (MES, MNQ, MYM) e mini commodities.
- Trend following funciona MUITO BEM em commodities (AQR centenário evidence inclui commodities).
- Sazonalidade pode ser implementada como filtro.

### Livros
- Jim Rogers "Hot Commodities" (introdução)
- Schwager "A Complete Guide to the Futures Market" (técnico)
- Kaufman "Trading Systems and Methods" (sistemas para commodities)

---

## D2. OBRIGAÇÕES / FIXED INCOME

### Conceitos essenciais
- **Yield:** Retorno de uma obrigação. Relação INVERSA com preço — quando yields sobem, preços descem.
- **Yield Curve:** Gráfico de yields por maturidade (2Y, 5Y, 10Y, 30Y). Normal = ascending. Invertida = sinal de recessão (precedeu TODAS as recessões US desde 1960).
- **Duration:** Sensibilidade do preço da obrigação a mudanças nas taxas. Duration mais alta = mais sensível.
- **Credit Spread:** Diferença entre yields corporativos e soberanos. Alarga em crises (medo), contrai em expansões (confiança).
- **Investment Grade vs High Yield (Junk):** IG = baixo risco default. HY = maior yield mas maior risco de default.

### Porque importa para traders
- A yield curve é o indicador macro mais fiável para prever recessões.
- Obrigações e ações tipicamente correlacionam-se negativamente (bonds sobem quando ações caem) — EXCEPTO em regimes de inflação alta (2022: ambos caíram).
- Fed funds rate influencia yields curtas → afeta custo de financiamento → afeta ações → afeta tudo.
- Um trader sério PRECISA de monitorizar yields de 2Y e 10Y US, credit spreads, e expectativas de Fed funds.

### Para o bot
- Monitor de yield curve como indicador macro (regime filter).
- Spread 10Y-2Y como sinal de risk-on/risk-off.
- IB API permite acesso a dados de bonds e futuros de bonds (ZN, ZB).

---

## D3. ANÁLISE FUNDAMENTAL PROFUNDA

### Demonstrações Financeiras — os 3 relatórios
1. **Income Statement:** Revenue → COGS → Gross Profit → Operating Expenses → EBIT → Interest → Tax → Net Income. Margens chave: Gross Margin, Operating Margin, Net Margin.
2. **Balance Sheet:** Assets = Liabilities + Equity. Liquidez (current ratio), solvência (debt/equity), qualidade dos ativos.
3. **Cash Flow Statement:** Operating CF (o mais importante), Investing CF (capex), Financing CF (dívida, dividendos). Free Cash Flow = Operating CF − Capex.

### Rácios chave para screening
| Rácio | Fórmula | O que mede | Benchmark |
|-------|---------|-----------|-----------|
| P/E | Preço / EPS | Quanto pagas por € de lucro | <15 value, >25 growth |
| P/B | Preço / Book Value | Preço vs patrimônio líquido | <1.5 value |
| EV/EBITDA | Enterprise Value / EBITDA | Valuation incluindo dívida | <10 é barato |
| ROE | Net Income / Equity | Rentabilidade do capital próprio | >15% é bom |
| ROIC | NOPAT / Invested Capital | Rentabilidade do capital total | >15% é excelente |
| Debt/Equity | Total Debt / Equity | Alavancagem financeira | <0.5 conservador |
| FCF Yield | FCF / Market Cap | Cash yield real | >5% atrativo |

### Valuation Models
- **DCF (Discounted Cash Flow):** Projetar free cash flows futuros (5-10 anos), desconta-los ao valor presente usando WACC, adicionar terminal value. O mais rigoroso mas sensível a pressupostos. Damodaran é a referência.
- **Múltiplos comparáveis:** Comparar P/E, EV/EBITDA com peers do mesmo setor. Mais prático, menos rigoroso.
- **Dividend Discount Model (DDM):** Valor = Dividendo / (r − g). Só funciona para empresas com dividendos estáveis.

### Moats (Pat Dorsey)
- **Network Effects:** Valor aumenta com cada utilizador (Facebook, Visa)
- **Switching Costs:** Custa mudar (SAP, Microsoft)
- **Intangible Assets:** Patentes, marcas, licenças (Coca-Cola, Pfizer)
- **Cost Advantage:** Produz mais barato (Walmart, Costco)
- **Efficient Scale:** Mercado natural limitado que não suporta mais concorrentes (utilities, aeroportos)

### Para o bot
- Fundamental screening como FILTER de universo: só operar ações com fundamentos sólidos (earnings growth, ROE >15%, FCF positivo).
- IB API permite acesso a dados fundamentais (fundamental data subscription).

---

## D4. DeFi EM PROFUNDIDADE

### Componentes essenciais
- **AMMs (Automated Market Makers):** Uniswap, Curve, Balancer. Pools de liquidez onde preço é determinado por fórmula (x·y=k). Substituem order books tradicionais.
- **Impermanent Loss (IL):** Perda temporária para LPs quando preço do ativo diverge do preço na hora do depósito. Numa pool 50/50 com 2× de divergência de preço, IL ≈ 5.7%. Com 5×, IL ≈ 25.5%. Pode exceder fees ganhas.
- **Yield Farming:** Fornecer liquidez a protocolos em troca de rewards (tokens de governance + trading fees). APYs de 3-1000%+ — os mais altos são quase sempre insustentáveis ou compensam risco extremo.
- **Liquidation Cascades:** Em protocolos de lending (Aave, Compound), quando colateral cai abaixo de threshold, posições são liquidadas automaticamente. Cascatas acontecem quando liquidações empurram preço para baixo → mais liquidações. Comum em crashes cripto.
- **MEV (Maximum Extractable Value):** Lucro que miners/validators podem extrair reordenando, inserindo ou censurando transações num bloco. Formas: front-running, sandwich attacks, arbitragem de liquidação. ~$600M+ extraído em 2023 (Flashbots data).
- **Flash Loans:** Empréstimos sem colateral que devem ser repagos na mesma transação. Usados para arbitragem, liquidações, e ataques (exploits).
- **Oracles:** Feeds de preço externos (Chainlink, Pyth) que DeFi usa. Risco: oracle manipulation pode drenar protocolos.

### Riscos reais
1. **Smart contract risk:** Bugs no código. ~$3.8B perdidos em hacks DeFi em 2022 (Chainalysis).
2. **Rug pulls:** Criadores retiram liquidez e fogem com fundos.
3. **Regulatory risk:** Governos podem classificar tokens como securities (SEC vs Ripple).
4. **Depeg risk:** Stablecoins podem perder o peg (UST/LUNA collapse 2022 — ~$40B evaporados).

### Para o bot
- DeFi NÃO é prioritário para o bot de IB (IB não opera DeFi).
- Compreender DeFi é útil para trading de cripto em exchanges centralizadas (entender funding rates, liquidation cascades, on-chain flows).

---

## D5. ON-CHAIN ANALYSIS

### Métricas essenciais (Glassnode)
- **MVRV (Market Value to Realized Value):** Ratio entre market cap e realized cap (preço médio de aquisição de todas as moedas). MVRV > 3.5 = topo historicamente. MVRV < 1 = fundo.
- **SOPR (Spent Output Profit Ratio):** Se moedas movidas estão em lucro (>1) ou perda (<1). SOPR < 1 sustentado = capitulação.
- **NUPL (Net Unrealized Profit/Loss):** % de lucro/perda não realizado da rede. >0.75 = euforia (vender). <0 = capitulação (comprar historicamente).
- **Exchange Flows:** Inflows para exchanges = pressão de venda iminente. Outflows = accumulation.
- **Miner Metrics:** Hashrate, miner revenue, miner outflows. Capitulação de miners = possível fundo.
- **Active Addresses:** Atividade on-chain como proxy de adoção/uso real.
- **Realized Cap vs Market Cap:** Divergência indica acumulação ou distribuição.

### Ciclos de halving BTC
- Halving reduz emissão de BTC em 50% (~cada 4 anos).
- Historicamente, BTC fez topo 12-18 meses após halving (2013, 2017, 2021).
- Último halving: Abril 2024. Se padrão repetir: topo potencial em H2 2025 - H1 2026.
- **AVISO:** "Past performance ≠ future results" é especialmente verdade com amostra de apenas 4 ciclos.

### Para o bot
- Se implementar módulo cripto: MVRV, SOPR e exchange flows como filtros macro de regime.
- APIs: Glassnode (paga), CryptoQuant, IntoTheBlock.

---

## D6. BACKTESTING — PITFALLS DEDICADOS

### Os 7 pecados mortais do backtesting

1. **Overfitting (data snooping):** Otimizar parâmetros até o backtest ficar perfeito — mas performance degrada em dados novos. REGRA: quanto mais parâmetros, mais overfitting. Estratégia com >5 parâmetros optimizados é quase certamente overfitted.

2. **Lookahead Bias:** Usar informação que não estava disponível no momento da decisão. Ex: usar closing price para decisões intradiárias. Verificar sempre: "esta informação existia no momento do sinal?"

3. **Survivorship Bias:** Backtestar apenas ações que sobreviveram até hoje. Ex: testar momentum em "S&P 500 de hoje" ignora as empresas que faliram/foram removidas. Usar dados point-in-time com delisted stocks.

4. **Assumption Errors:** Executar trades ao closing price quando na realidade entrarias no dia seguinte com gap. Slippage não modelado (especialmente em ações ilíquidas). Dividendos/splits não ajustados.

5. **Data Mining Bias (multiple testing):** Testar 100 estratégias → 5 "funcionam" por puro acaso (p<0.05 em 100 testes = 5 falsos positivos). Correcção: Bonferroni, out-of-sample testing, walk-forward.

6. **Regime Change:** Backtest em bull market → falha em bear market. Backtest em alta volatilidade → falha em baixa volatilidade. SOLUÇÃO: testar em múltiplos regimes, incluir 2000-2002, 2008, 2020, 2022.

7. **Custos Subestimados:** Não contabilizar spreads, comissões, slippage, market impact (para posições grandes), funding/swap costs, impostos.

### Framework de validação robusto
1. **Develop** em in-sample data (ex: 2000-2015)
2. **Validate** em out-of-sample (ex: 2016-2020)
3. **Walk-forward:** Re-optimize periodicamente em janela rolante, testar em período seguinte
4. **Monte Carlo:** Randomizar sequência de trades para ver distribuição de outcomes
5. **Stress test:** Testar em períodos de crise específicos
6. **Paper trade:** 3-6 meses em tempo real antes de capital real
7. **Minimum trades:** 100+ trades para significância estatística. Idealmente 200+.

### Para o bot
- OBRIGATÓRIO implementar framework de validação ANTES de ir live.
- Walk-forward optimization como módulo do bot.
- Logging de diferença entre backtest fill price e real fill price (slippage tracking).

---

## D7. FUTURES MECHANICS

### Conceitos essenciais
- **Margin (Initial):** Depósito exigido para abrir posição. Tipicamente 5-12% do valor do contrato. NÃO é o mesmo que margem em ações.
- **Margin (Maintenance):** Nível mínimo de equity na conta. Se equity cai abaixo → margin call → liquidação forçada.
- **Mark-to-Market:** Lucros e perdas liquidados DIARIAMENTE. Não podes "sentar" numa posição sem ter margem suficiente.
- **Rollover:** Contratos de futuros expiram. Para manter posição, fecha-se contrato corrente e abre-se o seguinte. Custo/benefício do roll depende de contango/backwardation.
- **Settlement:** Cash settlement (maioria dos financeiros — ES, NQ) vs physical delivery (commodities — CL, ZW). NUNCA manter posição até delivery se não queres receber 1000 barris de petróleo.
- **Contract Specifications:** Cada futuro tem tick size, tick value, trading hours, expiration dates específicas.
- **Micro Futures:** Versões menores dos contratos standard. MES (Micro E-mini S&P 500) = 1/10 do ES. Ideais para contas pequenas.

### Contratos mais relevantes para retail (via IB)
| Contrato | Ticker | Tick Size | Tick Value | Margin (~) |
|----------|--------|-----------|-----------|-----------|
| E-mini S&P 500 | ES | 0.25 | $12.50 | ~$12,000 |
| Micro E-mini S&P | MES | 0.25 | $1.25 | ~$1,200 |
| E-mini NASDAQ | NQ | 0.25 | $5.00 | ~$17,000 |
| Micro E-mini NASDAQ | MNQ | 0.25 | $0.50 | ~$1,700 |
| Crude Oil | CL | $0.01 | $10.00 | ~$6,000 |
| Gold | GC | $0.10 | $10.00 | ~$9,000 |
| Euro FX | 6E | $0.00005 | $6.25 | ~$2,500 |

### Para o bot
- Micro futuros (MES, MNQ) são ideais para contas pequenas via IB.
- Rollover automático precisa de ser programado (IB API tem continuous contracts).
- Mark-to-market significa que o bot precisa de monitorizar margem disponível.

---

**STATUS:** Blocos A, B, C e D COMPLETOS.

**INVENTÁRIO FINAL DA INVESTIGAÇÃO:**
- 25 métodos com dossier detalhado
- 55 livros com dossier (25 detalhados + 30 compactos)
- 11 comparações entre escolas (6 anteriores + 5 novas)
- Risk management framework completo
- 7 áreas temáticas cobertas em profundidade (commodities, bonds, fundamental, DeFi, on-chain, backtesting, futures)
- Bibliografia mestra com ordem de leitura
- Roadmap de 12 meses
- Arquitectura do bot para IB
- Caso de estudo Kotegawa/BNF integrado

**LACUNAS REMANESCENTES HONESTAS:**
- Dossiers de métodos com 36 pontos COMPLETOS existem para 5 (scalping, position, EOD, factor, arbitrage); os 20 da pesquisa deep research têm ~15-20 pontos cada — expandir para 36 requereria volume impraticável sem valor marginal significativo
- Regulação e fiscalidade — específica ao país de residência, não coberta
- Plataformas comparadas em detalhe (TradingView vs MT4/5 vs cTrader) — mencionadas mas sem dossier

# INVESTIGAÇÃO-MÃE — COMPLETAÇÃO TOTAL
## BLOCO A: Dossiers de Métodos em Falta (36 pontos cada)

---

## MÉTODO 21: SCALPING

1. **Nome canónico:** Scalping
2. **Nomes alternativos:** Micro-trading, pip hunting, tick trading, market making (variante)
3. **Categoria:** Trading de curtíssimo prazo / alta frequência retail
4. **Definição exata:** Estratégia que visa lucrar com movimentos de preço muito pequenos (1-10 pips em forex, poucos ticks em futuros), mantendo posições por segundos a poucos minutos, executando 50-200+ trades por dia.
5. **Ideia central / edge teórico:** Acumulação de pequenos lucros consistentes que compõem retornos significativos via volume de trades. Menor exposição a overnight risk. Edge teórico baseado em mean reversion de curtíssimo prazo e exploração do bid-ask spread.
6. **Lógica operacional:** Identificar micro-movimentos via price action em timeframes de 1-5 minutos ou tick charts. Entrar e sair rapidamente com targets de 0.05-0.2% por trade. Usar volume, VWAP, order flow como confirmação.
7. **Mercados usados:** Forex (majors — EUR/USD, USD/JPY), futuros de índices (ES, NQ), large-cap stocks com alta liquidez, cripto (BTC, ETH em perpétuos)
8. **Timeframes:** 1 segundo a 5 minutos. Tick charts. 15-second charts.
9. **Retalho vs institucional:** Ambos, mas institucionais (HFT) dominam esmagadoramente. Retail em desvantagem estrutural de latência.
10. **Discricionário/sistemático/híbrido:** Ambos. 78% dos retail scalpers usam ferramentas automatizadas (VT Markets 2025 survey).
11. **Ferramentas:** Level 2/DOM, Time & Sales, VWAP, EMA 9/20, Bollinger Bands (curto prazo), footprint charts, Bookmap, order flow
12. **Regras típicas de entrada:** Breakout de range de 1-5 min com volume confirmado; bounce no VWAP; reversão em Bollinger Band extrema; order flow imbalance
13. **Regras típicas de saída:** Target fixo de 3-10 pips/ticks; sinal contrário; time stop (máx 2-5 min)
14. **Stop-loss:** Muito apertado — 3-5 pips/ticks. Automático e não negociável.
15. **Take-profit:** Fixo ou level-based (próximo S/R em timeframe curto). R:R tipicamente 1:1 a 1:1.5.
16. **Position sizing:** Maior que swing/position por causa do target pequeno. Risco por trade 0.25-0.5% (mais conservador que swing porque frequência é alta).
17. **Perfil de risco:** Alto — muitas oportunidades para erros, custos acumulam rapidamente, stress psicológico extremo. Death by a thousand cuts se edge desaparece.
18. **Vantagens reais:** Zero overnight risk. Feedback rápido. Muitas oportunidades diárias. Compounding rápido quando funciona.
19. **Limitações reais:** Custos (spreads + comissões) corroem margens finas. Latência vs HFT. Stress extremo. Barber et al. (2019): menos de 1% dos day traders (incluindo scalpers) obtêm retornos positivos líquidos após custos. VT Markets 2025: apenas 34% dos retail scalpers são consistentemente rentáveis em 12 meses.
20. **Condições favoráveis:** Alta liquidez, alta volatilidade intradiária, spreads apertados, mercados com volume constante
21. **Condições desfavoráveis:** Mercados ilíquidos, spreads alargados (pré/pós-mercado), volatilidade extrema (flash crashes), publicações de notícias macro
22. **Erros comuns dos iniciantes:** Overtrading compulsivo; ignorar custos de transação no cálculo de rentabilidade; usar alavancagem excessiva; não ter stop automático; trading "por instinto" sem sistema definido
23. **Riscos de interpretação errada:** Confundir lucro bruto com lucro líquido (antes de custos); extrapolar backtests de timeframes curtos para real (slippage não modelado); assumir que alta frequência = mais lucro
24. **Overfitting:** MUITO ALTO — timeframes curtos têm mais ruído que sinal. Backtests de scalping raramente refletem realidade (Quantified Strategies).
25. **Dependência de execução rápida/custos baixos/liquidez:** EXTREMA — é o factor mais crítico. Milissegundos importam. Comissões acima de $2/round-turn por contrato destroem a maioria das estratégias.
26. **Adaptação por mercado:** Forex majors (melhor), ES/NQ futures (bom), ações large-cap (aceitável), cripto perpétuos (bom mas funding rates complicam), small-caps (péssimo — spread mata)
27. **Compatibilidade com conta pequena:** LIMITADA — precisa de capital suficiente para absorver custos e posições grandes o bastante para targets pequenos serem significativos. Mínimo prático ~$5,000-10,000.
28. **Compatibilidade com 1-2h/dia:** **INCOMPATÍVEL** — scalping requer 4-8h de atenção contínua e dedicada. Absolutamente inadequado para part-time.
29. **Compatibilidade com automação:** BOA em teoria, mas latência retail vs institucional é desvantagem real. Bots de scalping cripto mostram resultados promissores em papers (e.g., 13/15 trades bem-sucedidos num teste de 2h), mas condições laboratoriais ≠ mercado real.
30. **Nível de dificuldade:** 9/10 — provavelmente o estilo mais difícil. Combina exigências técnicas, psicológicas e infraestruturais extremas.
31. **Relação com outros métodos:** Subset de day trading. Variante de alta frequência de mean reversion e breakout. Tape reading é competência core.
32. **Livros relevantes:** Volman "Understanding Price Action" (scalping puro); Brooks "Trading Price Action" (serie); não há muitos livros sérios — a maioria do conteúdo de scalping é em vídeos e cursos (sinal de alerta).
33. **Autores/escolas:** Bob Volman, Al Brooks (price action scalping); John Carter (futuros)
34. **Evidência histórica:** Floor traders (market makers) foram os scalpers originais e tinham edge real (acesso ao pit). Esse edge desapareceu com electronificação. Académica: Barber et al. — <1% consistentemente rentável. VT Markets 2025: 34% rentáveis (dados self-reported, provavelmente inflados).
35. **Opiniões divergentes:** Defensores dizem que com disciplina e plataforma adequada continua viável. Quantified Strategies diz explicitamente: "scalping is a waste of time — do this instead [longer timeframes]." Verdade provavelmente no meio: funciona para poucos com infraestrutura certa.
36. **Veredito honesto:** **NÃO RECOMENDADO** para o teu perfil. Incompatível com 1-2h/dia, exige infraestrutura cara, evidência fortemente contra retail. As mesmas competências (leitura de price action, disciplina, gestão de risco) aplicadas a swing trading produzem melhores resultados com menos stress e custos.

---

## MÉTODO 22: POSITION TRADING

1. **Nome canónico:** Position Trading
2. **Nomes alternativos:** Macro trading (quando guiado por macro), trend investing, longer-term swing trading
3. **Categoria:** Trading de médio a longo prazo
4. **Definição exata:** Manter posições por semanas a meses, capturando movimentos de preço significativos guiados por tendências macro, técnicas de longo prazo ou análise fundamental.
5. **Ideia central / edge teórico:** Capturar a "meat" de tendências grandes, evitando ruído intradiário e custos de transação. Edge baseado em persistência de tendências macro e valuations a reverterem para fair value.
6. **Lógica operacional:** Identificar tendência primária (semanal/mensal), esperar por pullback para zona de valor (MA 50/200 dias, Fibonacci 50-61.8%), entrar com stop abaixo de swing low significativo, trail stop com MA ou ATR.
7. **Mercados usados:** Todos — ações, ETFs, forex, futuros, cripto. Particularmente eficaz em mercados com tendências sustentadas (commodities, forex majors, índices).
8. **Timeframes:** Diário e semanal. Decisões no fecho do dia ou da semana.
9. **Retalho vs institucional:** Ambos. Hedge funds macro são essencialmente position traders (Soros, Druckenmiller, Dalio).
10. **Discricionário/sistemático/híbrido:** Todos os três. Trend following sistemático é position trading codificado.
11. **Ferramentas:** MAs longas (50, 100, 200 dias), MACD semanal, RSI 14 diário/semanal, ATR para sizing e stops, análise fundamental (P/E, earnings growth), calendário macro
12. **Regras típicas de entrada:** Preço acima da MA 200 (trend filter) + pullback à MA 50 + RSI saindo de sobrevenda + volume crescente na recuperação. OU: breakout de range semanal com volume.
13. **Regras típicas de saída:** MA 200 violada no fecho semanal (stop de trend); target baseado em extensão Fibonacci ou measured move; sinal fundamental de deterioração.
14. **Stop-loss:** Largo — abaixo de swing low significativo em timeframe semanal. Tipicamente 5-15% do preço de entrada. Compensado por position size menor.
15. **Take-profit:** Trailing stop via MA 50 dias ou 2-3× ATR semanal. OU: target fundamental (fair value atingido).
16. **Position sizing:** Risco por trade 1-2% do capital. Como stop é largo, posição é proporcionalmente menor. Ex: stop a 10% → posição = 10-20% do capital (para 1-2% de risco).
17. **Perfil de risco:** Moderado — menos trades = menos custos e menos decisões emocionais. Overnight e over-weekend risk existe mas é compensado por timeframe.
18. **Vantagens reais:** Mínimo tempo de ecrã (15-30 min/dia). Custos de transação muito baixos (poucas trades por mês). Captura de movimentos grandes. Compatível com emprego full-time.
19. **Limitações reais:** Drawdowns longos se a tendência reverter lentamente. Exige paciência extrema — semanas sem ação. Swaps/rollover podem custar em posições forex mantidas meses. Capital preso por longos períodos.
20. **Condições favoráveis:** Mercados com tendências claras (bull/bear definidos). Alta correlação setorial. Políticas monetárias unidirecionais.
21. **Condições desfavoráveis:** Mercados laterais prolongados (whipsaw lento). Regimes de alta volatilidade com reversões bruscas (2020 COVID crash).
22. **Erros comuns:** Entrar cedo demais numa tendência incipiente. Usar stop demasiado apertado para o timeframe (batido pelo ruído normal). Não ajustar position size ao stop largo. Abandonar posição vencedora prematuramente.
23. **Riscos de interpretação:** Confundir position trading com buy-and-hold (position trading tem stops e regras de saída). Confundir paciência com inação — position trading requer monitorização regular.
24. **Overfitting:** BAIXO — timeframes longos têm mais sinal e menos ruído. Backtests mais fiáveis.
25. **Dependência de execução:** BAIXA — ordens executadas com calma, slippage irrelevante na maioria dos mercados.
26. **Adaptação:** Universal. Funciona em ações, ETFs, forex, futuros, cripto.
27. **Conta pequena:** EXCELENTE — custos baixos, position size flexível.
28. **1-2h/dia:** **IDEAL** — 15-30 min/dia é suficiente. Pode ser end-of-day ou end-of-week.
29. **Automação:** EXCELENTE — regras simples, poucos parâmetros, facilmente sistematizável.
30. **Dificuldade:** 3/10 técnico, 7/10 psicológico (paciência é difícil).
31. **Relação com outros:** Versão lenta de trend following. Complementar a swing trading. Pode integrar elementos de macro trading.
32. **Livros:** Clenow "Following the Trend" (futuros), Minervini "Trade Like a Stock Market Wizard" (ações growth), Murphy "Technical Analysis" (princípios gerais), Darvas "How I Made $2 Million" (caso clássico).
33. **Autores/escolas:** Nicolas Darvas (box method), William O'Neil (CANSLIM como position trading), managed futures CTAs (systematic position trading).
34. **Evidência:** AQR "A Century of Evidence on Trend-Following Investing" — trend following é essencialmente position trading sistemático, com evidência centenária. Factor momentum (Baltussen et al., 2026): momentum documentado com dados de 150+ anos e 46 países — t-statistics muito acima de thresholds de significância.
35. **Opiniões divergentes:** Críticos argumentam que buy-and-hold simples supera position trading após impostos e custos em muitos períodos. Defensores contra-argumentam que position trading protege em bear markets (a grande vantagem).
36. **Veredito:** **EXCELENTE — provavelmente o método mais adequado para o teu perfil.** Combina evidência forte, tempo mínimo de ecrã, baixos custos, e compatibilidade total com automação via IB API. Juntamente com swing trading, é o estilo nuclear recomendado.

---

## MÉTODO 23: END-OF-DAY TRADING

1. **Nome canónico:** End-of-Day (EOD) Trading
2. **Nomes alternativos:** Close-only trading, after-hours analysis, daily bar trading
3. **Categoria:** Variante de swing/position trading
4. **Definição:** Todas as decisões são tomadas depois do fecho do mercado. Análise e ordens colocadas à noite ou de manhã cedo, executadas na abertura do dia seguinte. Posições mantidas dias a semanas.
5. **Edge teórico:** Elimina ruído intradiário e decisões impulsivas. Barra diária completa contém informação mais fiável que barras intradiárias incompletas. Daily close é o preço mais importante do dia.
6. **Lógica operacional:** Após fecho, analisar gráficos diários. Identificar setups. Colocar ordens limit ou market-on-open com stops predefinidos. Verificar 1× por dia.
7. **Mercados:** Todos — mas particularmente eficaz em ações, ETFs e forex (onde a "London close" ou "NY close" é significativa).
8. **Timeframes:** Diário exclusivamente. Decisões baseadas apenas em barras completas.
9. **Retail vs institucional:** Ideal para retail. Muitos profissionais também operam EOD.
10. **Tipo:** Pode ser totalmente sistemático.
11. **Ferramentas:** Velas diárias, MAs, RSI, ATR, S/R semanal. Screening tools (TradingView, Finviz).
12. **Entrada:** Padrão de vela no fecho diário (pin bar, engulfing) + contexto de tendência. Ordem colocada à noite para execução no dia seguinte.
13. **Saída:** Stop técnico (abaixo do low da barra de setup). Take-profit no próximo nível de S/R significativo ou R:R de 1:2-1:3.
14. **Stop-loss:** Baseado no range da barra de setup ou ATR(14). Colocado no momento da ordem.
15. **Take-profit:** Fixo ou trailing. 2-3× ATR ou próximo nível de S/R semanal.
16. **Position sizing:** Standard 1-2% de risco. ATR-based.
17. **Perfil de risco:** Moderado — overnight gaps são o principal risco, mitigado por position sizing conservador.
18. **Vantagens:** MÍNIMO tempo necessário (15-30 min/dia). Decisões calmas sem pressão de tempo. Eliminação de overtrading. Compatível com emprego.
19. **Limitações:** Overnight gap risk. Menos oportunidades que intraday. Execução na abertura pode ter slippage em ações menos líquidas.
20. **Favorável:** Mercados com tendências claras no daily. Ações com earnings previsíveis.
21. **Desfavorável:** Mercados muito voláteis com gaps frequentes. Períodos de alta incerteza (pré-eleições, crises).
22. **Erros comuns:** Olhar para intraday e tomar decisões baseadas em ruído. Não respeitar as ordens colocadas à noite. "Ajustar" ordens baseado em emoções da manhã.
23. **Interpretação errada:** EOD não é "lazy trading" — requer análise rigorosa, simplesmente feita num momento específico.
24. **Overfitting:** BAIXO — daily bars são relativamente limpas.
25. **Execução:** BAIXA dependência — ordens colocadas com tempo, sem urgência.
26. **Adaptação:** Universal.
27. **Conta pequena:** EXCELENTE.
28. **1-2h/dia:** **PERFEITO** — desenhado exatamente para isto.
29. **Automação:** EXCELENTE — ideal para bot que corre 1×/dia após o fecho.
30. **Dificuldade:** 3/10 — um dos métodos mais acessíveis.
31. **Relação:** Subset de swing trading. Combina com position trading.
32. **Livros:** Elder "The New Trading for a Living" (triple screen usa daily), Carver "Systematic Trading" (daily signals)
33. **Autores:** Nial Fuller (price action EOD), Elder, Carver
34. **Evidência:** Não há estudos específicos de "EOD trading" como categoria separada, mas toda a evidência de swing e trend following em daily charts aplica-se.
35. **Divergentes:** Alguns argumentam que perdes edge por não estar presente no intraday. Contra-argumento forte: a maioria do edge retail está em daily bars, não em intraday (onde HFT domina).
36. **Veredito:** **IDEAL para o teu perfil.** O bot para IB deve ser construído primariamente como EOD system — correr após o fecho, analisar sinais, colocar ordens para o dia seguinte.

---

## MÉTODO 24: FACTOR INVESTING

1. **Nome canónico:** Factor Investing
2. **Nomes alternativos:** Smart Beta, Evidence-Based Investing, Quantitative Factor Strategies, Style Investing
3. **Categoria:** Investimento sistemático baseado em prémios de risco documentados
4. **Definição:** Construção de portfolios sobreexpondo-os sistematicamente a factores com prémio de retorno documentado academicamente: Value, Momentum, Size, Quality, Low Volatility.
5. **Edge teórico:** Factores representam prémios de risco compensados (risco não diversificável) ou anomalias comportamentais persistentes. Fama-French (1993): value e size. Carhart (1997): momentum. Novy-Marx (2013): quality/profitability. Frazzini & Pedersen (2014): low beta.
6. **Lógica operacional:** Screening quantitativo de universo de ações/ETFs por métricas de factor. Rebalanceamento periódico (mensal, trimestral, anual). Long-only (retail) ou long-short (institucional).
7. **Mercados:** Ações globais primariamente. Também aplicável a bonds, commodities, forex (Asness et al., 2013: value e momentum em 8 mercados).
8. **Timeframes:** Longo prazo — rebalanceamento mensal a anual.
9. **Retail vs institucional:** Ambos. Retail via ETFs smart beta (DFA, Vanguard Factor, AQR). Institucional via portfolios long-short.
10. **Tipo:** SISTEMÁTICO — 100% baseado em regras quantitativas.
11. **Ferramentas:** Screening fundamental (P/E, P/B, ROE, momentum 12-1 meses), databases (Bloomberg, Finviz, Factor Research), ETFs smart beta.
12. **Entrada:** Rebalanceamento periódico — sem timing de mercado. Comprar os ativos que passam no screening de factor.
13. **Saída:** Rebalanceamento — vender quando ativo deixa de cumprir critérios de factor.
14. **Stop-loss:** Tipicamente não usado — factor investing é long-term. Drawdowns suportados pela diversificação.
15. **Take-profit:** Rebalanceamento periódico captura lucros naturalmente.
16. **Position sizing:** Equal-weight ou market-cap weight dentro de cada factor. Diversificação ampla (30-100+ posições).
17. **Perfil de risco:** Moderado — diversificado mas sujeito a períodos longos de underperformance (value underperformou 2010-2020 nos EUA).
18. **Vantagens:** Evidência académica FORTÍSSIMA. Implementável com ETFs baratos. Mínimo tempo. Diversificação natural. Berkin & Swedroe identificaram 5 factores que passam critérios de persistência, pervasividade, robustez e investibilidade.
19. **Limitações:** Períodos longos de underperformance vs benchmark (paciência extrema necessária). "Factor winter" (2018-2020 em value). Post-publication decay de alguns factores. Crowding risk quando demasiado capital segue os mesmos factores. Blitz et al. (2024): debate sobre data integrity da database Fama-French.
20. **Favorável:** Múltiplos factores em carteira diversificada. Combinação value + momentum (Sharpe 1.45).
21. **Desfavorável:** Factor winter prolongado. Período pós-publicação com decay.
22. **Erros comuns:** Escolher apenas 1 factor. Abandonar durante underperformance. Confundir smart beta ETFs com factor investing genuíno.
23. **Interpretação errada:** Factor investing NÃO garante outperformance em qualquer período — é um prémio de longo prazo com muita variância.
24. **Overfitting:** MODERADO — depende de quantos factores e parâmetros se usam. Os 5 canónicos (value, momentum, size, quality, low vol) são robustos.
25. **Execução:** MÍNIMA dependência — rebalanceamento mensal/trimestral.
26. **Adaptação:** Ações globais, bonds, commodities, forex — documentado em todos.
27. **Conta pequena:** EXCELENTE via ETFs (QVAL, QMOM, IVAL, etc.). Possível com €1,000+.
28. **1-2h/dia:** EXCELENTE — rebalanceamento mensal requer 1-2h POR MÊS.
29. **Automação:** EXCELENTE — screening + rebalanceamento automatizável trivialmente.
30. **Dificuldade:** 4/10 (implementação via ETFs) a 7/10 (construção de portfolio long-short próprio).
31. **Relação:** Momentum factor é a base de Dual Momentum (Antonacci). Value factor é o fundamento de Graham/Buffett sistematizado. Quality é Fisher/Novy-Marx. Trend following em futuros é time-series momentum applied.
32. **Livros:** Berkin & Swedroe "Your Complete Guide to Factor-Based Investing", Ilmanen "Expected Returns", Ang "Asset Management", Pedersen "Efficiently Inefficient", Antonacci "Dual Momentum Investing"
33. **Autores/escolas:** Fama & French (value, size), Jegadeesh & Titman (momentum), Asness (AQR — multifactor), Swedroe (divulgação), Baltussen et al. (2026 — momentum 150 anos). Escola de Chicago + AQR.
34. **Evidência:** A MAIS FORTE que existe em finanças. Momentum: 150+ anos, 46 países (Baltussen 2026). Value: 60+ anos, múltiplos mercados. Factor combination: Sharpe 1.45 (Asness). Blitz et al. 2019: long factor positions com Sharpe ratio até 1.10 e t-stat de 7.44. 2025: factor strategies com forte outperformance internacional (DFA funds).
35. **Divergentes:** EMH purists dizem que factores compensam risco (esperado). Behavioralists dizem que são anomalias que eventualmente desaparecerão. Realistas: provavelmente combinação de ambos. Post-2020: debate sobre se US factor underperformance é morte dos factores ou simplesmente um período difícil (2025 vingou os factores internacionalmente).
36. **Veredito:** **EXCELENTE — uma das abordagens com mais evidência científica que existe.** Ideal para a componente "investimento" do portfolio, complementando a componente "trading" com swing/position. O bot pode implementar factor screening como módulo de seleção de universo.

---

## MÉTODO 25: ARBITRAGEM PURA

1. **Nome canónico:** Arbitragem (Pure Arbitrage)
2. **Nomes alternativos:** Riskless arbitrage, price arbitrage, market arbitrage
3. **Categoria:** Exploração de ineficiências de preço entre mercados
4. **Definição:** Compra e venda simultânea do mesmo ativo (ou equivalentes) em mercados diferentes para lucrar com diferenças de preço, teoricamente sem risco.
5. **Edge teórico:** Lei do preço único — ativos idênticos devem ter o mesmo preço. Quando não têm, o arbitrageur lucra corrigindo a ineficiência.
6. **Lógica:** Comprar barato no mercado A, vender caro no mercado B, simultaneamente. Diferença = lucro.
7. **Mercados:** Forex (triangular arb), ETFs vs underlying basket, futures vs spot (cash-and-carry), cripto exchanges (preços diferentes entre exchanges), ADRs vs ações locais.
8. **Timeframes:** Milissegundos a minutos. Oportunidades desaparecem instantaneamente.
9. **Retail vs institucional:** **QUASE EXCLUSIVAMENTE INSTITUCIONAL** em mercados tradicionais. Retail só tem chance marginal em cripto (exchanges fragmentadas).
10. **Tipo:** SISTEMÁTICO — requer automação total.
11. **Ferramentas:** Colocation servers, feeds de dados diretos, software de execução ultra-low latency, algoritmos dedicados.
12. **Entrada:** Automática quando spread entre mercados excede threshold + custos.
13. **Saída:** Simultânea com entrada (compra e venda ao mesmo tempo).
14. **Stop-loss:** N/A — se execução é simultânea, não há risco direcional. Na prática, execution risk existe.
15. **Take-profit:** O spread capturado menos custos.
16. **Position sizing:** Máximo possível — quanto maior, mais lucro absoluto (retorno % é pequeno).
17. **Perfil de risco:** Teoricamente zero. Na prática: execution risk, latency risk, regulatory risk, counterparty risk (especialmente em cripto).
18. **Vantagens:** "Riskless" quando executado perfeitamente. Sem exposição direcional.
19. **Limitações:** Oportunidades minúsculas e efémeras. Requer infraestrutura cara. Capital intensivo (retorno % muito baixo). HFTs dominam completamente. Em cripto: risco de exchange (hack, freeze), risco de transferência (tempo de confirmação blockchain).
20. **Favorável:** Mercados fragmentados com liquidez irregular (cripto early stage, mercados emergentes).
21. **Desfavorável:** Mercados eficientes e integrados (US equities, forex majors — arb praticamente inexistente).
22. **Erros comuns:** Tentar arbitragem manual (impossível — oportunidades duram milissegundos). Não contabilizar custos de transferência. Assumir que preço diferente = oportunidade (pode ser spread legítimo por liquidez).
23. **Interpretação errada:** Arbitragem ≠ spread trading. Arbitragem genuína é sem risco. Spread trading (pairs) envolve risco direcional residual.
24. **Overfitting:** N/A — estratégia não depende de padrões históricos.
25. **Execução:** DEPENDÊNCIA ABSOLUTA — é TUDO sobre execução. Latência de milissegundos é a diferença entre lucro e perda.
26. **Adaptação:** Cripto (melhor oportunidade para retail), forex (triangular — dominado por HFT), futures/spot (cash-and-carry — capital intensivo).
27. **Conta pequena:** INVIÁVEL em mercados tradicionais. MARGINAL em cripto (spreads entre exchanges menores).
28. **1-2h/dia:** INCOMPATÍVEL — requer sistemas 24/7 automatizados.
29. **Automação:** OBRIGATÓRIA — impossível manual.
30. **Dificuldade:** 9/10 — infraestrutura e desenvolvimento são barreiras imensas.
31. **Relação:** Base teórica de pairs trading e stat arb. Versão "pura" do que pairs traders tentam fazer com risco.
32. **Livros:** Harris "Trading and Exchanges" (microestrutura), Narang "Inside the Black Box" (como HFTs fazem arb)
33. **Autores:** Nunzio Tartaglia (pioneer de pairs em Morgan Stanley), Renaissance Technologies (Medallion Fund — a arb mais bem-sucedida da história)
34. **Evidência:** Medallion Fund: ~66% retorno anualizado bruto (1988-2018). Mas usa infraestrutura que custa centenas de milhões. Para retail: evidência quase inexistente de sucesso sustentável.
35. **Divergentes:** Cripto arb traders argumentam que ainda há oportunidades entre exchanges descentralizadas (DEXs vs CEXs). MEV (Maximum Extractable Value) em Ethereum é uma forma de arb on-chain. Mas MEV é dominada por bots sofisticados.
36. **Veredito:** **NÃO APLICÁVEL para retail** em mercados tradicionais. Marginal em cripto. Compreender o conceito é valioso para entender microestrutura, mas NÃO é uma estratégia viável para implementar no bot de IB.

---

*Os 20 métodos da investigação anterior + estes 5 completam 25 métodos com dossier. Os métodos restantes (investimento passivo, index investing, dividend investing) são variantes de investimento cobertas nos dossiers de livros e nas comparações.*

---

**STATUS DO BLOCO A:** COMPLETO. 25 métodos com dossiers detalhados (20 da investigação anterior + 5 novos).

**PRÓXIMO:** Bloco B — Dossiers dos 30 livros em falta.

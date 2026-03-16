"""
Signal Engine — Motor de sinais do bot de trading autónomo.

Responsável pela detecção de regime de mercado, cálculo de indicadores
técnicos e geração de sinais Kotegawa (SMA25 deviation + confirmações).

Sem dependências externas — utiliza apenas módulos da stdlib do Python.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class Regime(str, Enum):
    """Regimes de mercado suportados."""

    BULL = "BULL"
    BEAR = "BEAR"
    SIDEWAYS = "SIDEWAYS"


class Confianca(str, Enum):
    """Níveis de confiança do sinal Kotegawa."""

    BAIXO = "BAIXO"
    MEDIO = "MEDIO"
    ALTO = "ALTO"


class TrendHorizon(str, Enum):
    """Horizonte de tendência usado para os thresholds de KAIRI."""

    SHORT_TERM = "SHORT_TERM"
    MEDIUM_TERM = "MEDIUM_TERM"
    LONG_TERM = "LONG_TERM"


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class RegimeInfo:
    """Informação completa sobre o regime de mercado detectado.

    Attributes:
        regime: Regime actual (BULL, BEAR ou SIDEWAYS).
        motivo: Descrição curta do porquê do regime atribuído.
        preco_vs_sma200: Diferença percentual entre o preço e a SMA(200).
        sma50_vs_sma200: Diferença percentual entre a SMA(50) e a SMA(200).
        rsi: Valor actual do RSI(14).
        atr_ratio: Rácio ATR(14) / média ATR de 60 dias.
        volatilidade_baixa: True se ATR(14) < 50% da média de 60 dias.
    """

    regime: Regime
    motivo: str
    preco_vs_sma200: float
    sma50_vs_sma200: float
    rsi: float
    atr_ratio: float
    volatilidade_baixa: bool


@dataclass(frozen=True, slots=True)
class SignalResult:
    """Resultado completo do sinal Kotegawa.

    Attributes:
        signal: True se existe sinal de entrada válido.
        regime: Regime de mercado no momento do sinal.
        deviation: Desvio percentual do preço face à SMA(25).
        deviation_minimo: Limiar mínimo de desvio para o regime actual.
        deviation_optimo: Limiar óptimo de desvio para o regime actual.
        confirmacoes: Número de confirmações obtidas (0-3).
        detalhes_confirmacoes: Lista descritiva de cada confirmação activa.
        confianca: Nível de confiança (BAIXO, MEDIO, ALTO).
        size_multiplier: Multiplicador de posição (0.0, 0.5, 0.75 ou 1.0).
        preco: Preço actual do activo.
        rsi: Valor actual do RSI(14).
        bb_lower: Valor da banda inferior de Bollinger.
        volume_ratio: Rácio volume actual / média de volume 20 dias.
    """

    signal: bool
    regime: Regime
    deviation: float
    deviation_minimo: float
    deviation_optimo: float
    confirmacoes: int
    detalhes_confirmacoes: list[str]
    confianca: Confianca
    horizon: TrendHorizon
    size_multiplier: float
    preco: float
    rsi: float
    rsi2: float | None  # Finding 2
    bb_lower: float
    volume_ratio: float


# ---------------------------------------------------------------------------
# Limiares de KAIRI
# ---------------------------------------------------------------------------

# Kotegawa method — NAO ALTERAR
_KAIRI_ENTRY_THRESHOLD = -25.0
_KAIRI_STRONG_THRESHOLD = -35.0

# Mapeamento de número de confirmações para (confiança, size_multiplier)
_CONFIANCA_MAP: dict[int, tuple[Confianca, float]] = {
    0: (Confianca.BAIXO, 0.0),
    1: (Confianca.MEDIO, 0.50),
    2: (Confianca.MEDIO, 0.75),
    3: (Confianca.ALTO, 1.0),
}


# ---------------------------------------------------------------------------
# Indicadores técnicos — cálculos puros sem dependências externas
# ---------------------------------------------------------------------------

def calculate_sma(closes: list[float], period: int) -> float | None:
    """Calcula a Média Móvel Simples (SMA) para o período indicado.

    Args:
        closes: Lista de preços de fecho, do mais antigo para o mais recente.
        period: Número de períodos para a média.

    Returns:
        Valor da SMA ou None se não houver dados suficientes.
    """
    if len(closes) < period or period <= 0:
        return None

    # Utilizar apenas os últimos *period* valores
    janela = closes[-period:]
    return sum(janela) / period


def calculate_rsi(closes: list[float], period: int = 14) -> float | None:
    """Calcula o Relative Strength Index (RSI) com suavização exponencial (Wilder).

    Utiliza o método de Wilder: média exponencial dos ganhos e das perdas,
    tal como originalmente definido no livro "New Concepts in Technical
    Trading Systems" (1978).

    Args:
        closes: Lista de preços de fecho, do mais antigo para o mais recente.
        period: Número de períodos (por defeito 14).

    Returns:
        Valor do RSI (0-100) ou None se não houver dados suficientes.
    """
    # Precisamos de pelo menos period+1 preços para calcular period variações
    if len(closes) < period + 1 or period <= 0:
        return None

    # Calcular variações diárias
    deltas: list[float] = []
    for i in range(1, len(closes)):
        deltas.append(closes[i] - closes[i - 1])

    # Primeira média: média aritmética dos primeiros *period* deltas
    ganhos_iniciais = [max(d, 0.0) for d in deltas[:period]]
    perdas_iniciais = [abs(min(d, 0.0)) for d in deltas[:period]]

    avg_gain = sum(ganhos_iniciais) / period
    avg_loss = sum(perdas_iniciais) / period

    # Suavização de Wilder para os deltas restantes
    for d in deltas[period:]:
        ganho_actual = max(d, 0.0)
        perda_actual = abs(min(d, 0.0))
        avg_gain = (avg_gain * (period - 1) + ganho_actual) / period
        avg_loss = (avg_loss * (period - 1) + perda_actual) / period

    # Evitar divisão por zero — se avg_loss == 0, RSI = 100
    if avg_loss == 0.0:
        return 100.0

    rs = avg_gain / avg_loss
    rsi = 100.0 - (100.0 / (1.0 + rs))
    return rsi


def calculate_rsi2(closes: list[float]) -> float | None:  # Finding 2
    """
    RSI de 2 períodos via EWM — método Larry Connors.  # Finding 2
    Isola capitulações agudas de 1-2 dias.  # Finding 2
    Retorna None se menos de 3 barras disponíveis.  # Finding 2
    """
    if len(closes) < 3:  # Finding 2
        return None  # Finding 2
    delta = [closes[i] - closes[i - 1] for i in range(1, len(closes))]  # Finding 2
    gains = [max(d, 0.0) for d in delta]  # Finding 2
    losses = [abs(min(d, 0.0)) for d in delta]  # Finding 2
    alpha = 0.5  # Finding 2
    avg_gain = gains[0]  # Finding 2
    avg_loss = losses[0]  # Finding 2
    for g, l in zip(gains[1:], losses[1:]):  # Finding 2
        avg_gain = alpha * g + (1 - alpha) * avg_gain  # Finding 2
        avg_loss = alpha * l + (1 - alpha) * avg_loss  # Finding 2
    if avg_loss == 0.0:  # Finding 2
        return 100.0  # Finding 2
    rs = avg_gain / avg_loss  # Finding 2
    return 100.0 - (100.0 / (1.0 + rs))  # Finding 2


def calculate_atr(
    highs: list[float],
    lows: list[float],
    closes: list[float],
    period: int = 14,
) -> float | None:
    """Calcula o Average True Range (ATR) com suavização de Wilder.

    O True Range de cada barra é o maior de:
      - high - low
      - |high - close_anterior|
      - |low - close_anterior|

    Args:
        highs: Lista de preços máximos (do mais antigo para o mais recente).
        lows: Lista de preços mínimos.
        closes: Lista de preços de fecho.
        period: Número de períodos (por defeito 14).

    Returns:
        Valor do ATR ou None se não houver dados suficientes.
    """
    n = min(len(highs), len(lows), len(closes))
    # Precisamos de pelo menos period+1 barras (a 1.ª barra não tem close anterior)
    if n < period + 1 or period <= 0:
        return None

    # Calcular True Range para cada barra a partir da segunda
    true_ranges: list[float] = []
    for i in range(1, n):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        true_ranges.append(tr)

    if len(true_ranges) < period:
        return None

    # Primeira média: média aritmética dos primeiros *period* TRs
    atr = sum(true_ranges[:period]) / period

    # Suavização de Wilder
    for tr in true_ranges[period:]:
        atr = (atr * (period - 1) + tr) / period

    return atr


def calculate_bollinger_bands(
    closes: list[float],
    period: int = 20,
    std_dev: float = 2.0,
) -> tuple[float, float, float] | None:
    """Calcula as Bandas de Bollinger (upper, middle, lower).

    Args:
        closes: Lista de preços de fecho, do mais antigo para o mais recente.
        period: Período da SMA central (por defeito 20).
        std_dev: Número de desvios-padrão (por defeito 2.0).

    Returns:
        Tuplo (upper, middle, lower) ou None se não houver dados suficientes.
    """
    if len(closes) < period or period <= 0:
        return None

    janela = closes[-period:]
    middle = sum(janela) / period

    # Desvio-padrão populacional (pstdev) — é o padrão para Bollinger Bands
    variancia = sum((x - middle) ** 2 for x in janela) / period
    dp = math.sqrt(variancia)

    upper = middle + std_dev * dp
    lower = middle - std_dev * dp

    return (upper, middle, lower)


def calculate_volume_avg(volumes: list[float], period: int = 20) -> float | None:
    """Calcula a média de volume para o período indicado.

    Args:
        volumes: Lista de volumes, do mais antigo para o mais recente.
        period: Número de períodos (por defeito 20).

    Returns:
        Média de volume ou None se não houver dados suficientes.
    """
    if len(volumes) < period or period <= 0:
        return None

    janela = volumes[-period:]
    return sum(janela) / period


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
    n = min(len(highs), len(lows), len(closes))
    if n < period + 1 or period <= 0:
        return 0.0

    tr_list: list[float] = []
    dm_plus: list[float] = []
    dm_minus: list[float] = []

    for i in range(1, n):
        high_value = highs[i]
        low_value = lows[i]
        prev_close = closes[i - 1]
        tr = max(
            high_value - low_value,
            abs(high_value - prev_close),
            abs(low_value - prev_close),
        )
        up = highs[i] - highs[i - 1]
        down = lows[i - 1] - lows[i]
        dm_plus.append(up if up > down and up > 0 else 0.0)
        dm_minus.append(down if down > up and down > 0 else 0.0)
        tr_list.append(tr)

    def _smooth(data: list[float], smooth_period: int) -> list[float]:
        """Suavização de Wilder para séries de período n."""
        if len(data) < smooth_period:
            return []
        smoothed = sum(data[:smooth_period])
        result = [smoothed]
        for idx in range(smooth_period, len(data)):
            smoothed = smoothed - smoothed / smooth_period + data[idx]
            result.append(smoothed)
        return result

    atr_s = _smooth(tr_list, period)
    dmp_s = _smooth(dm_plus, period)
    dmm_s = _smooth(dm_minus, period)

    dx_list: list[float] = []
    for atr_value, plus_value, minus_value in zip(atr_s, dmp_s, dmm_s):
        if atr_value == 0:
            dx_list.append(0.0)
            continue
        pdi = 100.0 * plus_value / atr_value
        mdi = 100.0 * minus_value / atr_value
        if pdi + mdi == 0:
            dx_list.append(0.0)
        else:
            dx_list.append(100.0 * abs(pdi - mdi) / (pdi + mdi))

    if len(dx_list) < period:
        return 0.0

    return sum(dx_list[-period:]) / period


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
    n = min(len(highs), len(lows), len(closes))
    if n < period + 1 or period <= 1:
        return 100.0

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

    highest_high = max(highs[n - period:n])
    lowest_low = min(lows[n - period:n])

    if highest_high == lowest_low:
        return 100.0

    chop = 100.0 * math.log10(tr_sum / (highest_high - lowest_low)) / math.log10(period)
    return max(0.0, min(100.0, chop))


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

    ema = sum(closes[:period]) / period
    multiplier = 2.0 / (period + 1)

    for price in closes[period:]:
        ema = (price - ema) * multiplier + ema

    return ema


# ---------------------------------------------------------------------------
# Detecção de regime de mercado
# ---------------------------------------------------------------------------


def classify_trend_horizon(
    price: float,
    sma50: float,
    sma200: float,
) -> TrendHorizon:
    """Classifica o horizonte de tendência para os thresholds de KAIRI."""
    if price >= sma200 and sma50 >= sma200:
        return TrendHorizon.LONG_TERM
    if price >= sma50 or sma50 >= sma200:
        return TrendHorizon.MEDIUM_TERM
    return TrendHorizon.SHORT_TERM

def detect_regime(
    price: float,
    sma50: float,
    sma200: float,
    rsi: float,
    atr: float,
    atr_avg_60: float,
) -> RegimeInfo:
    """Detecta o regime de mercado actual com base em indicadores técnicos.

    Ordem de prioridade:
      1. SIDEWAYS por baixa volatilidade — ATR(14) < 50% da média ATR de 60 dias.
      2. BULL — preço > SMA(200) E SMA(50) > SMA(200) E RSI(14) > 50.
      3. BEAR — preço < SMA(200) E SMA(50) < SMA(200) E RSI(14) < 50.
      4. SIDEWAYS — nenhuma das condições anteriores satisfeita.

    Args:
        price: Preço actual do activo.
        sma50: Valor da SMA de 50 períodos.
        sma200: Valor da SMA de 200 períodos.
        rsi: Valor actual do RSI(14).
        atr: Valor actual do ATR(14).
        atr_avg_60: Média do ATR dos últimos 60 dias.

    Returns:
        RegimeInfo com todos os detalhes da classificação.
    """
    # Métricas comuns
    preco_vs_sma200 = ((price - sma200) / sma200) * 100.0 if sma200 != 0 else 0.0
    sma50_vs_sma200 = ((sma50 - sma200) / sma200) * 100.0 if sma200 != 0 else 0.0
    atr_ratio = atr / atr_avg_60 if atr_avg_60 != 0 else 0.0
    volatilidade_baixa = atr_ratio < 0.5

    # 1. Prioridade: SIDEWAYS por baixa volatilidade
    if volatilidade_baixa:
        return RegimeInfo(
            regime=Regime.SIDEWAYS,
            motivo="ATR(14) inferior a 50% da média de 60 dias — volatilidade baixa",
            preco_vs_sma200=preco_vs_sma200,
            sma50_vs_sma200=sma50_vs_sma200,
            rsi=rsi,
            atr_ratio=atr_ratio,
            volatilidade_baixa=True,
        )

    # 2. BULL: preço > SMA(200) E SMA(50) > SMA(200) E RSI > 50
    condicao_bull = price > sma200 and sma50 > sma200 and rsi > 50.0
    if condicao_bull:
        return RegimeInfo(
            regime=Regime.BULL,
            motivo="Preço e SMA(50) acima da SMA(200) com RSI > 50 — tendência ascendente",
            preco_vs_sma200=preco_vs_sma200,
            sma50_vs_sma200=sma50_vs_sma200,
            rsi=rsi,
            atr_ratio=atr_ratio,
            volatilidade_baixa=False,
        )

    # 3. BEAR: preço < SMA(200) E SMA(50) < SMA(200) E RSI < 50
    condicao_bear = price < sma200 and sma50 < sma200 and rsi < 50.0
    if condicao_bear:
        return RegimeInfo(
            regime=Regime.BEAR,
            motivo="Preço e SMA(50) abaixo da SMA(200) com RSI < 50 — tendência descendente",
            preco_vs_sma200=preco_vs_sma200,
            sma50_vs_sma200=sma50_vs_sma200,
            rsi=rsi,
            atr_ratio=atr_ratio,
            volatilidade_baixa=False,
        )

    # 4. Fallback: SIDEWAYS — condições mistas, sem tendência clara
    return RegimeInfo(
        regime=Regime.SIDEWAYS,
        motivo="Condições mistas — sem tendência clara definida",
        preco_vs_sma200=preco_vs_sma200,
        sma50_vs_sma200=sma50_vs_sma200,
        rsi=rsi,
        atr_ratio=atr_ratio,
        volatilidade_baixa=False,
    )


# ---------------------------------------------------------------------------
# Sinal Kotegawa (SMA25 Deviation + confirmações)
# ---------------------------------------------------------------------------

def kotegawa_signal(
    price: float,
    sma25: float,
    rsi: float,
    bb_lower: float,
    volume: float,
    vol_avg_20: float,
    regime: str,
    sma50: float | None = None,
    sma200: float | None = None,
    rsi2: float | None = None,  # Finding 2
) -> SignalResult:
    """Gera sinal de entrada Kotegawa com base no desvio SMA(25) e confirmações.

    O sinal Kotegawa baseia-se na estratégia de mean reversion inspirada
    em BNF/Kotegawa: comprar quando o preço desvia significativamente
    abaixo da SMA(25), com confirmações técnicas adicionais.

    Limiares de KAIRI:
      - Entrada: KAIRI <= -25%
      - Entrada forte: KAIRI <= -35%

    Regras de confirmação RSI (Connors RSI2 — adoptado em v3):
      1. RSI2 <= 10 é a confirmação principal (sinal mais preciso em mean reversion).
      2. RSI14 <= 30 é o fallback quando RSI2 não está disponível.
      3. Preço < banda inferior de Bollinger e volume extremo mantêm-se como filtros adicionais.

    Score de confiança:
      - 0 confirmações → BAIXO  (size_multiplier = 0%)   → NÃO operar
      - 1 confirmação  → MEDIO  (size_multiplier = 50%)  → metade da posição
      - 2 confirmações → MEDIO  (size_multiplier = 75%)  → 75% da posição
      - 3 confirmações → ALTO   (size_multiplier = 100%) → posição completa

    Args:
        price: Preço actual do activo.
        sma25: Valor da SMA de 25 períodos.
        rsi: Valor actual do RSI(14).
        bb_lower: Valor da banda inferior de Bollinger.
        volume: Volume actual da barra.
        vol_avg_20: Média de volume dos últimos 20 dias.
        regime: String com o regime actual ("BULL", "BEAR" ou "SIDEWAYS").
        sma50: SMA de 50 períodos para classificar o horizonte.
        sma200: SMA de 200 períodos para classificar o horizonte.

    Returns:
        SignalResult com todos os detalhes do sinal.
    """
    # Converter string de regime para enum
    try:
        regime_enum = Regime(regime.upper())
    except ValueError:
        # Se o regime não for reconhecido, assumir SIDEWAYS (mais conservador)
        regime_enum = Regime.SIDEWAYS

    # Calcular desvio percentual do preço face à SMA(25)
    if sma25 == 0.0:
        deviation = 0.0
    else:
        deviation = ((price - sma25) / sma25) * 100.0

    horizon = classify_trend_horizon(
        price=price,
        sma50=sma50 if sma50 is not None else price,
        sma200=sma200 if sma200 is not None else price,
    )

    dev_minimo = _KAIRI_ENTRY_THRESHOLD
    dev_optimo = _KAIRI_STRONG_THRESHOLD

    # Rácio de volume
    volume_ratio = volume / vol_avg_20 if vol_avg_20 != 0.0 else 0.0

    # --- Verificar confirmações ---
    confirmacoes = 0
    detalhes: list[str] = []

    # Finding 2 — RSI2 substitui RSI14 como confirmação obrigatória
    _rsi_val = rsi2 if rsi2 is not None else rsi  # Finding 2
    _rsi_thresh = 10.0 if rsi2 is not None else 30.0  # Finding 2
    _rsi_label = "RSI2" if rsi2 is not None else "RSI14(fallback)"  # Finding 2
    if _rsi_val <= _rsi_thresh:  # Finding 2
        confirmacoes += 1  # Finding 2
        detalhes.append(  # Finding 2
            f"{_rsi_label}={_rsi_val:.2f} ≤ {_rsi_thresh:.0f} "  # Finding 2
            f"(sobrevenda aguda) # Finding 2"  # Finding 2
        )

    # Confirmação 2: preço abaixo da banda inferior de Bollinger
    if price < bb_lower:
        confirmacoes += 1
        detalhes.append(
            f"Preço ({price:.2f}) abaixo da Bollinger inferior ({bb_lower:.2f})"
        )

    # Confirmação 3: volume > 150% da média de 20 dias
    if volume > 1.5 * vol_avg_20:
        confirmacoes += 1
        detalhes.append(
            f"Volume elevado ({volume_ratio:.2f}x da média — acima de 1.5x)"
        )

    # Determinar confiança e size_multiplier
    confianca, size_multiplier = _CONFIANCA_MAP[confirmacoes]

    # Verificar se o desvio atinge o limiar mínimo para o regime
    # (deviation é negativo, dev_minimo também — comparar com <=)
    desvio_suficiente = deviation <= dev_minimo

    # Sinal válido: KAIRI suficiente, RSI obrigatório e pelo menos 1 confirmação
    signal = desvio_suficiente and (_rsi_val <= _rsi_thresh) and confirmacoes >= 1  # Finding 2

    return SignalResult(
        signal=signal,
        regime=regime_enum,
        deviation=deviation,
        deviation_minimo=dev_minimo,
        deviation_optimo=dev_optimo,
        confirmacoes=confirmacoes,
        detalhes_confirmacoes=detalhes,
        confianca=confianca,
        horizon=horizon,
        size_multiplier=size_multiplier,
        preco=price,
        rsi=rsi,
        rsi2=rsi2,  # Finding 2
        bb_lower=bb_lower,
        volume_ratio=volume_ratio,
    )


# ---------------------------------------------------------------------------
# Função de conveniência — pipeline completo a partir de dados em bruto
# ---------------------------------------------------------------------------

def analyze(
    closes: list[float],
    highs: list[float],
    lows: list[float],
    volumes: list[float],
) -> tuple[RegimeInfo, SignalResult] | None:
    """Executa a pipeline completa de análise: indicadores → regime → sinal.

    Função de conveniência que calcula todos os indicadores técnicos a
    partir das séries em bruto e devolve o regime e o sinal Kotegawa.

    Requer pelo menos 200 barras de dados para calcular todos os
    indicadores necessários (SMA 200 é o mais exigente).

    Args:
        closes: Preços de fecho (mais antigo → mais recente).
        highs: Preços máximos.
        lows: Preços mínimos.
        volumes: Volumes de negociação.

    Returns:
        Tuplo (RegimeInfo, SignalResult) ou None se dados insuficientes.
    """
    n = min(len(closes), len(highs), len(lows), len(volumes))
    if n < 200:
        return None

    # --- Calcular indicadores ---
    price = closes[-1]
    volume_actual = volumes[-1]

    sma25 = calculate_sma(closes, 25)
    sma50 = calculate_sma(closes, 50)
    sma200 = calculate_sma(closes, 200)
    rsi = calculate_rsi(closes, 14)
    rsi2 = calculate_rsi2(closes)  # Finding 2
    atr = calculate_atr(highs, lows, closes, 14)
    bb = calculate_bollinger_bands(closes, 20, 2.0)
    vol_avg_20 = calculate_volume_avg(volumes, 20)

    # Verificar se todos os indicadores foram calculados com sucesso
    if any(v is None for v in (sma25, sma50, sma200, rsi, atr, bb, vol_avg_20)):
        return None

    # Garantir que os tipos são correctos após a verificação de None
    assert sma25 is not None
    assert sma50 is not None
    assert sma200 is not None
    assert rsi is not None
    assert atr is not None
    assert bb is not None
    assert vol_avg_20 is not None

    _bb_upper, _bb_middle, bb_lower = bb

    # Calcular ATR médio de 60 dias — média dos últimos 60 valores de ATR diário
    # Para simplificar, calculamos o ATR com period=14 sobre janelas deslizantes
    # dos últimos 60 dias e fazemos a média
    atrs_60: list[float] = []
    for i in range(60):
        idx_fim = n - i
        if idx_fim < 15:
            break
        atr_i = calculate_atr(
            highs[:idx_fim], lows[:idx_fim], closes[:idx_fim], 14
        )
        if atr_i is not None:
            atrs_60.append(atr_i)

    atr_avg_60 = sum(atrs_60) / len(atrs_60) if atrs_60 else atr

    # --- Detecção de regime ---
    regime_info = detect_regime(price, sma50, sma200, rsi, atr, atr_avg_60)

    # --- Sinal Kotegawa ---
    signal_result = kotegawa_signal(
        price=price,
        sma25=sma25,
        rsi=rsi,
        bb_lower=bb_lower,
        volume=volume_actual,
        vol_avg_20=vol_avg_20,
        regime=regime_info.regime.value,
        sma50=sma50,
        sma200=sma200,
        rsi2=rsi2,  # Finding 2
    )

    return regime_info, signal_result

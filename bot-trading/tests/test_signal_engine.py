"""
Tests for src/signal_engine.py

Covers: SMA, RSI, ATR, Bollinger Bands, detect_regime, kotegawa_signal,
        edge cases (insufficient data, zero values).
"""

from __future__ import annotations

import math

import pytest

from src.signal_engine import (
    Confianca,
    Regime,
    RegimeInfo,
    SignalResult,
    TrendHorizon,
    calculate_atr,
    calculate_bollinger_bands,
    calculate_rsi,
    calculate_sma,
    calculate_volume_avg,
    classify_trend_horizon,
    detect_regime,
    kotegawa_signal,
    analyze,
)


# ===================================================================
# Helpers
# ===================================================================

def _constant_closes(value: float, n: int) -> list[float]:
    """Generate a list of constant close prices."""
    return [value] * n


def _linear_closes(start: float, step: float, n: int) -> list[float]:
    """Generate a linearly increasing/decreasing series."""
    return [start + i * step for i in range(n)]


# ===================================================================
# Tests: calculate_sma
# ===================================================================


class TestCalculateSMA:
    def test_sma_with_known_data(self):
        closes = [1.0, 2.0, 3.0, 4.0, 5.0]
        result = calculate_sma(closes, 5)
        assert result == pytest.approx(3.0)

    def test_sma_uses_last_n_values(self):
        closes = [10.0, 20.0, 30.0, 40.0, 50.0]
        result = calculate_sma(closes, 3)
        # Last 3 values: 30, 40, 50 => average = 40
        assert result == pytest.approx(40.0)

    def test_sma_period_equals_length(self):
        closes = [2.0, 4.0, 6.0]
        result = calculate_sma(closes, 3)
        assert result == pytest.approx(4.0)

    def test_sma_insufficient_data_returns_none(self):
        closes = [1.0, 2.0]
        result = calculate_sma(closes, 5)
        assert result is None

    def test_sma_empty_list_returns_none(self):
        result = calculate_sma([], 5)
        assert result is None

    def test_sma_period_zero_returns_none(self):
        closes = [1.0, 2.0, 3.0]
        result = calculate_sma(closes, 0)
        assert result is None

    def test_sma_period_negative_returns_none(self):
        closes = [1.0, 2.0, 3.0]
        result = calculate_sma(closes, -1)
        assert result is None

    def test_sma_single_value(self):
        result = calculate_sma([42.0], 1)
        assert result == pytest.approx(42.0)


# ===================================================================
# Tests: calculate_rsi
# ===================================================================


class TestCalculateRSI:
    def test_rsi_with_known_uptrend(self):
        """All gains => RSI should be 100."""
        # 16 prices, each one higher than the previous (15 deltas, all positive)
        closes = [float(i) for i in range(1, 17)]
        result = calculate_rsi(closes, 14)
        assert result == pytest.approx(100.0)

    def test_rsi_with_known_downtrend(self):
        """All losses => RSI should be 0."""
        closes = [float(100 - i) for i in range(16)]
        result = calculate_rsi(closes, 14)
        assert result == pytest.approx(0.0)

    def test_rsi_mixed_data_within_bounds(self):
        """RSI must be between 0 and 100."""
        closes = [44, 44.34, 44.09, 43.61, 44.33,
                  44.83, 45.10, 45.42, 45.84, 46.08,
                  45.89, 46.03, 45.61, 46.28, 46.28, 46.00]
        result = calculate_rsi(closes, 14)
        assert result is not None
        assert 0.0 <= result <= 100.0

    def test_rsi_insufficient_data_returns_none(self):
        closes = [1.0] * 14  # Need 15 for period=14
        result = calculate_rsi(closes, 14)
        assert result is None

    def test_rsi_period_zero_returns_none(self):
        result = calculate_rsi([1.0, 2.0, 3.0], 0)
        assert result is None

    def test_rsi_constant_prices(self):
        """Constant prices => no gains, no losses. avg_loss=0 => RSI=100."""
        closes = [50.0] * 20
        result = calculate_rsi(closes, 14)
        assert result == pytest.approx(100.0)


# ===================================================================
# Tests: calculate_atr
# ===================================================================


class TestCalculateATR:
    def test_atr_with_known_data(self):
        """ATR calculation with simple data where TR = high - low (no gaps)."""
        n = 16
        highs = [10.0 + i * 0.1 for i in range(n)]
        lows = [9.0 + i * 0.1 for i in range(n)]
        closes = [9.5 + i * 0.1 for i in range(n)]

        result = calculate_atr(highs, lows, closes, 14)
        assert result is not None
        # Each bar: high - low = 1.0, and since close is midpoint there are
        # no big gaps, so true range ~ 1.0 each bar => ATR ~ 1.0
        assert result == pytest.approx(1.0, abs=0.05)

    def test_atr_insufficient_data_returns_none(self):
        result = calculate_atr([10], [9], [9.5], 14)
        assert result is None

    def test_atr_period_zero_returns_none(self):
        result = calculate_atr([10, 11], [9, 10], [9.5, 10.5], 0)
        assert result is None

    def test_atr_mismatched_lengths(self):
        """Uses minimum length of all three lists."""
        highs = [10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25]
        lows = [9, 10, 11, 12, 13, 14, 15]
        closes = [9.5, 10.5, 11.5, 12.5, 13.5, 14.5, 15.5]
        # min length = 7, need period+1=15 => None
        result = calculate_atr(highs, lows, closes, 14)
        assert result is None

    def test_atr_with_gaps(self):
        """Verify ATR handles gaps (previous close far from current range)."""
        n = 16
        highs = [100.0] * n
        lows = [99.0] * n
        closes = [99.5] * n
        # Introduce a gap: bar 8 closed at 95, bar 9 opens at 100
        closes[7] = 95.0
        result = calculate_atr(highs, lows, closes, 14)
        assert result is not None
        assert result > 1.0  # Gap should push ATR above the normal 1.0


# ===================================================================
# Tests: calculate_bollinger_bands
# ===================================================================


class TestCalculateBollingerBands:
    def test_bollinger_constant_prices(self):
        """Constant prices => std=0, bands collapse to the mean."""
        closes = [100.0] * 25
        result = calculate_bollinger_bands(closes, 20, 2.0)
        assert result is not None
        upper, middle, lower = result
        assert middle == pytest.approx(100.0)
        assert upper == pytest.approx(100.0)
        assert lower == pytest.approx(100.0)

    def test_bollinger_known_data(self):
        """Verify structure: lower < middle < upper for non-constant data."""
        closes = list(range(1, 25))
        closes_float = [float(c) for c in closes]
        result = calculate_bollinger_bands(closes_float, 20, 2.0)
        assert result is not None
        upper, middle, lower = result
        assert lower < middle < upper

    def test_bollinger_middle_equals_sma(self):
        """Middle band should equal SMA of the same period."""
        closes = [float(x) for x in range(1, 30)]
        result = calculate_bollinger_bands(closes, 20, 2.0)
        sma = calculate_sma(closes, 20)
        assert result is not None
        assert sma is not None
        _, middle, _ = result
        assert middle == pytest.approx(sma)

    def test_bollinger_insufficient_data_returns_none(self):
        closes = [1.0] * 15
        result = calculate_bollinger_bands(closes, 20)
        assert result is None

    def test_bollinger_symmetry(self):
        """Upper and lower bands should be symmetric around the middle."""
        closes = [float(x) for x in range(1, 30)]
        result = calculate_bollinger_bands(closes, 20, 2.0)
        assert result is not None
        upper, middle, lower = result
        assert upper - middle == pytest.approx(middle - lower)


# ===================================================================
# Tests: detect_regime
# ===================================================================


class TestDetectRegime:
    def test_bull_regime(self):
        """Price > SMA200, SMA50 > SMA200, RSI > 50 => BULL."""
        info = detect_regime(
            price=110.0,
            sma50=105.0,
            sma200=100.0,
            rsi=60.0,
            atr=2.0,
            atr_avg_60=2.0,
        )
        assert info.regime == Regime.BULL
        assert info.volatilidade_baixa is False

    def test_bear_regime(self):
        """Price < SMA200, SMA50 < SMA200, RSI < 50 => BEAR."""
        info = detect_regime(
            price=90.0,
            sma50=95.0,
            sma200=100.0,
            rsi=40.0,
            atr=2.0,
            atr_avg_60=2.0,
        )
        assert info.regime == Regime.BEAR
        assert info.volatilidade_baixa is False

    def test_sideways_mixed_conditions(self):
        """Mixed conditions (e.g., price > SMA200 but RSI < 50) => SIDEWAYS."""
        info = detect_regime(
            price=105.0,
            sma50=102.0,
            sma200=100.0,
            rsi=45.0,  # RSI < 50 breaks BULL condition
            atr=2.0,
            atr_avg_60=2.0,
        )
        assert info.regime == Regime.SIDEWAYS
        assert info.volatilidade_baixa is False

    def test_sideways_low_volatility(self):
        """ATR < 50% of avg => SIDEWAYS by low volatility (highest priority)."""
        info = detect_regime(
            price=110.0,
            sma50=105.0,
            sma200=100.0,
            rsi=60.0,
            atr=0.4,       # 40% of avg => low volatility
            atr_avg_60=1.0,
        )
        assert info.regime == Regime.SIDEWAYS
        assert info.volatilidade_baixa is True

    def test_low_volatility_overrides_bull(self):
        """Even when BULL conditions are met, low volatility forces SIDEWAYS."""
        info = detect_regime(
            price=200.0,
            sma50=190.0,
            sma200=180.0,
            rsi=80.0,
            atr=0.3,       # 30% of avg
            atr_avg_60=1.0,
        )
        assert info.regime == Regime.SIDEWAYS
        assert info.volatilidade_baixa is True

    def test_preco_vs_sma200_calculation(self):
        info = detect_regime(
            price=110.0,
            sma50=105.0,
            sma200=100.0,
            rsi=60.0,
            atr=2.0,
            atr_avg_60=2.0,
        )
        assert info.preco_vs_sma200 == pytest.approx(10.0)

    def test_sma50_vs_sma200_calculation(self):
        info = detect_regime(
            price=110.0,
            sma50=105.0,
            sma200=100.0,
            rsi=60.0,
            atr=2.0,
            atr_avg_60=2.0,
        )
        assert info.sma50_vs_sma200 == pytest.approx(5.0)

    def test_sma200_zero_no_division_error(self):
        info = detect_regime(
            price=100.0,
            sma50=100.0,
            sma200=0.0,
            rsi=50.0,
            atr=2.0,
            atr_avg_60=2.0,
        )
        assert info.preco_vs_sma200 == 0.0
        assert info.sma50_vs_sma200 == 0.0

    def test_atr_avg_60_zero_no_division_error(self):
        info = detect_regime(
            price=100.0,
            sma50=100.0,
            sma200=100.0,
            rsi=50.0,
            atr=2.0,
            atr_avg_60=0.0,
        )
        assert info.atr_ratio == 0.0


# ===================================================================
# Tests: classify_trend_horizon
# ===================================================================


class TestClassifyTrendHorizon:
    def test_long_term(self):
        result = classify_trend_horizon(price=110.0, sma50=105.0, sma200=100.0)
        assert result == TrendHorizon.LONG_TERM

    def test_medium_term(self):
        result = classify_trend_horizon(price=95.0, sma50=90.0, sma200=100.0)
        assert result == TrendHorizon.MEDIUM_TERM

    def test_short_term(self):
        result = classify_trend_horizon(price=80.0, sma50=85.0, sma200=100.0)
        assert result == TrendHorizon.SHORT_TERM


# ===================================================================
# Tests: kotegawa_signal
# ===================================================================


class TestKotegawaSignal:
    def test_long_term_signal_with_3_confirmations(self):
        result = kotegawa_signal(
            price=100.0,
            sma25=140.0,       # ~ -28.57%
            sma50=120.0,
            sma200=95.0,
            rsi=25.0,          # confirmation 1: RSI < 30
            bb_lower=110.0,    # confirmation 2
            volume=2000.0,     # confirmation 3
            vol_avg_20=1000.0,
            regime="BULL",
        )
        assert result.signal is True
        assert result.regime == Regime.BULL
        assert result.horizon == TrendHorizon.LONG_TERM
        assert result.confirmacoes == 3
        assert result.confianca == Confianca.ALTO
        assert result.size_multiplier == 1.0
        assert result.deviation_minimo == -25.0

    def test_medium_term_threshold(self):
        result = kotegawa_signal(
            price=90.0,
            sma25=130.0,       # ~ -30.77%
            sma50=85.0,
            sma200=100.0,
            rsi=25.0,
            bb_lower=95.0,
            volume=1000.0,
            vol_avg_20=1000.0,
            regime="BULL",
        )
        assert result.signal is True
        assert result.horizon == TrendHorizon.MEDIUM_TERM
        assert result.deviation_minimo == -25.0
        assert result.deviation_optimo == -35.0

    def test_short_term_threshold(self):
        result = kotegawa_signal(
            price=60.0,
            sma25=100.0,
            sma50=70.0,
            sma200=80.0,
            rsi=25.0,
            bb_lower=65.0,
            volume=1000.0,
            vol_avg_20=1000.0,
            regime="BEAR",
        )
        assert result.signal is True
        assert result.horizon == TrendHorizon.SHORT_TERM
        assert result.deviation_minimo == -25.0
        assert result.deviation_optimo == -35.0

    def test_rsi_is_mandatory_for_signal(self):
        result = kotegawa_signal(
            price=60.0,
            sma25=100.0,
            sma50=70.0,
            sma200=80.0,
            rsi=35.0,          # obrigatorio falha
            bb_lower=70.0,
            volume=2000.0,
            vol_avg_20=1000.0,
            regime="BEAR",
        )
        assert result.signal is False
        assert result.confirmacoes == 2

    def test_sma25_zero_deviation(self):
        """When SMA25 is zero, deviation should be 0 and no signal."""
        result = kotegawa_signal(
            price=100.0,
            sma25=0.0,
            sma50=100.0,
            sma200=100.0,
            rsi=25.0,
            bb_lower=90.0,
            volume=2000.0,
            vol_avg_20=1000.0,
            regime="BULL",
        )
        assert result.deviation == 0.0
        assert result.signal is False

    def test_vol_avg_zero_no_division_error(self):
        result = kotegawa_signal(
            price=90.0,
            sma25=100.0,
            sma50=85.0,
            sma200=100.0,
            rsi=25.0,
            bb_lower=95.0,
            volume=1000.0,
            vol_avg_20=0.0,
            regime="BULL",
        )
        assert result.volume_ratio == 0.0

    def test_unknown_regime_defaults_to_sideways(self):
        result = kotegawa_signal(
            price=60.0,
            sma25=100.0,
            sma50=70.0,
            sma200=80.0,
            rsi=25.0,
            bb_lower=90.0,
            volume=2000.0,
            vol_avg_20=1000.0,
            regime="INVALID_REGIME",
        )
        assert result.regime == Regime.SIDEWAYS

    def test_volume_confirmation_exactly_1_5x(self):
        """Volume exactly at 1.5x is NOT above threshold (strict >)."""
        result = kotegawa_signal(
            price=60.0,
            sma25=100.0,
            sma50=70.0,
            sma200=80.0,
            rsi=25.0,
            bb_lower=50.0,
            volume=1500.0,
            vol_avg_20=1000.0,
            regime="BEAR",
        )
        assert result.confirmacoes == 1

    def test_case_insensitive_regime(self):
        result = kotegawa_signal(
            price=90.0,
            sma25=100.0,
            sma50=90.0,
            sma200=80.0,
            rsi=25.0,
            bb_lower=95.0,
            volume=2000.0,
            vol_avg_20=1000.0,
            regime="bull",
        )
        assert result.regime == Regime.BULL


# ===================================================================
# Tests: analyze (convenience pipeline)
# ===================================================================


class TestAnalyze:
    def test_insufficient_data_returns_none(self):
        closes = [100.0] * 100
        highs = [101.0] * 100
        lows = [99.0] * 100
        volumes = [1000.0] * 100
        result = analyze(closes, highs, lows, volumes)
        assert result is None

    def test_sufficient_data_returns_tuple(self):
        """Generate enough data for all indicators (200+ bars)."""
        n = 250
        closes = [100.0 + 0.1 * math.sin(i * 0.1) for i in range(n)]
        highs = [c + 1.0 for c in closes]
        lows = [c - 1.0 for c in closes]
        volumes = [1000.0 + 100 * math.sin(i * 0.2) for i in range(n)]

        result = analyze(closes, highs, lows, volumes)
        assert result is not None
        regime_info, signal_result = result
        assert isinstance(regime_info, RegimeInfo)
        assert isinstance(signal_result, SignalResult)


# ===================================================================
# Tests: calculate_volume_avg
# ===================================================================


class TestCalculateVolumeAvg:
    def test_volume_avg_known_data(self):
        volumes = [100.0, 200.0, 300.0, 400.0, 500.0]
        result = calculate_volume_avg(volumes, 5)
        assert result == pytest.approx(300.0)

    def test_volume_avg_insufficient_data(self):
        result = calculate_volume_avg([1.0], 5)
        assert result is None

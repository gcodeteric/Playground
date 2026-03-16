"""
Tests for src/risk_manager.py

Covers: position sizing (Half-Kelly), Kelly cap enforcement, daily/weekly/monthly
        limits, kill switch, max positions/grids, risk of ruin, validate_order,
        calculate_stop_loss/take_profit, zero averaging down, validate_startup.
"""

from __future__ import annotations

import math

import pytest

from src.risk_manager import (
    KillSwitchLevel,
    OrderValidation,
    RiskCheckResult,
    RiskManager,
    RiskStatus,
)


# ===================================================================
# Fixtures
# ===================================================================


@pytest.fixture
def rm() -> RiskManager:
    """Default RiskManager with 100_000 capital."""
    return RiskManager(capital=100_000.0)


@pytest.fixture
def rm_small() -> RiskManager:
    """RiskManager with smaller capital for edge case testing."""
    return RiskManager(capital=10_000.0, risk_per_level=0.02, kelly_cap=0.05)


# ===================================================================
# Tests: position_size_per_level (Half-Kelly)
# ===================================================================


class TestPositionSizePerLevel:
    def test_basic_position_size(self, rm: RiskManager):
        """With default params (1% risk, 5% kelly cap), verify sizing logic."""
        size = rm.position_size_per_level(
            capital=100_000,
            entry=100.0,
            stop=95.0,
            win_rate=0.5,
            payoff_ratio=2.0,
        )
        # Kelly = 0.5 - 0.5/2.0 = 0.25
        # Half-Kelly = 0.125
        # Capped by kelly_cap (0.05) => 0.05
        # Capped by risk_per_level (0.01) => 0.01
        # risk_amount = 100_000 * 0.01 = 1_000
        # risk_per_unit = |100 - 95| = 5
        # quantity = 1_000 / 5 = 200
        assert size == 200

    def test_half_kelly_calculation(self):
        """Verify Half-Kelly with high kelly_cap and risk_per_level."""
        rm = RiskManager(capital=100_000, risk_per_level=0.50, kelly_cap=0.50)
        size = rm.position_size_per_level(
            capital=100_000,
            entry=100.0,
            stop=95.0,
            win_rate=0.5,
            payoff_ratio=2.0,
        )
        # Kelly = 0.5 - 0.5/2.0 = 0.25
        # Half-Kelly = 0.125
        # Capped by kelly_cap (0.50) => 0.125 (below cap)
        # Capped by risk_per_level (0.50) => 0.125 (below cap)
        # risk_amount = 100_000 * 0.125 = 12_500
        # risk_per_unit = 5
        # quantity = 12_500 / 5 = 2_500
        assert size == 2500

    def test_kelly_negative_returns_zero(self, rm: RiskManager):
        """When Kelly is negative (no edge), position size should be 0."""
        size = rm.position_size_per_level(
            capital=100_000,
            entry=100.0,
            stop=95.0,
            win_rate=0.3,
            payoff_ratio=1.0,
        )
        # Kelly = 0.3 - 0.7/1.0 = -0.4 => negative => 0
        assert size == 0

    def test_zero_capital_returns_zero(self, rm: RiskManager):
        size = rm.position_size_per_level(
            capital=0, entry=100.0, stop=95.0
        )
        assert size == 0

    def test_negative_capital_returns_zero(self, rm: RiskManager):
        size = rm.position_size_per_level(
            capital=-1000, entry=100.0, stop=95.0
        )
        assert size == 0

    def test_entry_equals_stop_returns_zero(self, rm: RiskManager):
        size = rm.position_size_per_level(
            capital=100_000, entry=100.0, stop=100.0
        )
        assert size == 0

    def test_invalid_win_rate_returns_zero(self, rm: RiskManager):
        size = rm.position_size_per_level(
            capital=100_000, entry=100.0, stop=95.0, win_rate=0.0
        )
        assert size == 0

        size = rm.position_size_per_level(
            capital=100_000, entry=100.0, stop=95.0, win_rate=1.0
        )
        assert size == 0

    def test_invalid_payoff_returns_zero(self, rm: RiskManager):
        size = rm.position_size_per_level(
            capital=100_000, entry=100.0, stop=95.0, payoff_ratio=0.0
        )
        assert size == 0

    def test_floor_rounding(self, rm: RiskManager):
        """Result should always be floor (conservative rounding)."""
        size = rm.position_size_per_level(
            capital=100_000,
            entry=100.0,
            stop=97.0,
            win_rate=0.5,
            payoff_ratio=2.0,
        )
        # risk_amount = 100_000 * 0.01 = 1_000
        # risk_per_unit = 3.0
        # quantity = 1_000 / 3 = 333.33 => floor => 333
        assert size == 333


# ===================================================================
# Tests: Kelly cap enforcement
# ===================================================================


class TestKellyCapEnforcement:
    def test_kelly_cap_never_exceeds_5_percent(self):
        """Position risk never exceeds kelly_cap regardless of Kelly value."""
        rm = RiskManager(capital=100_000, risk_per_level=0.10, kelly_cap=0.05)
        size = rm.position_size_per_level(
            capital=100_000,
            entry=100.0,
            stop=99.0,
            win_rate=0.8,
            payoff_ratio=3.0,
        )
        # Kelly = 0.8 - 0.2/3.0 = 0.7333
        # Half-Kelly = 0.3666
        # Capped by kelly_cap (0.05) => 0.05
        # Capped by risk_per_level (0.10) => 0.05
        risk_amount = size * abs(100.0 - 99.0)
        risk_pct = risk_amount / 100_000
        assert risk_pct <= 0.05 + 1e-9

    def test_kelly_cap_default_is_5_percent(self, rm: RiskManager):
        assert rm.kelly_cap == 0.05


# ===================================================================
# Tests: check_daily_limit
# ===================================================================


class TestCheckDailyLimit:
    def test_within_daily_limit(self, rm: RiskManager):
        # 3% of 100_000 = 3_000. Loss of 2_000 is within limit.
        assert rm.check_daily_limit(-2_000, 100_000) is True

    def test_exceeds_daily_limit(self, rm: RiskManager):
        # Loss of 4_000 = 4% > 3% limit
        assert rm.check_daily_limit(-4_000, 100_000) is False

    def test_exactly_at_daily_limit(self, rm: RiskManager):
        # Loss of exactly 3_000 = 3% => NOT within limit (strict <)
        assert rm.check_daily_limit(-3_000, 100_000) is False

    def test_positive_pnl_passes(self, rm: RiskManager):
        assert rm.check_daily_limit(5_000, 100_000) is True

    def test_zero_capital_returns_false(self, rm: RiskManager):
        assert rm.check_daily_limit(-100, 0) is False


# ===================================================================
# Tests: check_weekly_limit
# ===================================================================


class TestCheckWeeklyLimit:
    def test_within_weekly_limit(self, rm: RiskManager):
        # 6% of 100_000 = 6_000. Loss of 5_000 is within limit.
        assert rm.check_weekly_limit(-5_000, 100_000) is True

    def test_exceeds_weekly_limit(self, rm: RiskManager):
        # Loss of 7_000 = 7% > 6% limit
        assert rm.check_weekly_limit(-7_000, 100_000) is False

    def test_exactly_at_weekly_limit(self, rm: RiskManager):
        # 6% of 100_000 = 6_000 => strict < fails
        assert rm.check_weekly_limit(-6_000, 100_000) is False


# ===================================================================
# Tests: check_kill_switch
# ===================================================================


class TestCheckKillSwitch:
    def test_within_monthly_limit(self, rm: RiskManager):
        # 10% of 100_000 = 10_000. Loss of 8_000 is within.
        assert rm.check_kill_switch(-8_000, 100_000) is True

    def test_exceeds_monthly_limit(self, rm: RiskManager):
        # Loss of 12_000 = 12% > 10% limit
        assert rm.check_kill_switch(-12_000, 100_000) is False

    def test_exactly_at_monthly_limit(self, rm: RiskManager):
        # 10% of 100_000 = 10_000 => strict < fails
        assert rm.check_kill_switch(-10_000, 100_000) is False

    def test_positive_monthly_pnl_passes(self, rm: RiskManager):
        assert rm.check_kill_switch(5_000, 100_000) is True


# ===================================================================
# Tests: check_max_positions
# ===================================================================


class TestCheckMaxPositions:
    def test_below_max_positions(self, rm: RiskManager):
        assert rm.check_max_positions(5) is True

    def test_at_max_positions(self, rm: RiskManager):
        # max_positions=8, current=8 => NOT within (strict <)
        assert rm.check_max_positions(8) is False

    def test_above_max_positions(self, rm: RiskManager):
        assert rm.check_max_positions(10) is False

    def test_zero_positions(self, rm: RiskManager):
        assert rm.check_max_positions(0) is True


# ===================================================================
# Tests: check_max_grids
# ===================================================================


class TestCheckMaxGrids:
    def test_below_max_grids(self, rm: RiskManager):
        assert rm.check_max_grids(1) is True

    def test_at_max_grids(self, rm: RiskManager):
        # max_grids=3, current=3 => NOT within (strict <)
        assert rm.check_max_grids(3) is False

    def test_zero_grids(self, rm: RiskManager):
        assert rm.check_max_grids(0) is True


# ===================================================================
# Tests: calculate_risk_of_ruin
# ===================================================================


class TestCalculateRiskOfRuin:
    def test_with_edge_low_risk(self, rm: RiskManager):
        """1% risk, 50% WR, 2:1 RR => very low risk of ruin."""
        ror = rm.calculate_risk_of_ruin(
            win_rate=0.5, payoff_ratio=2.0, risk_per_trade=0.01
        )
        assert 0.0 <= ror < 0.001  # < 0.1%

    def test_with_high_risk_per_trade(self, rm: RiskManager):
        """5% risk per trade => higher risk of ruin."""
        ror = rm.calculate_risk_of_ruin(
            win_rate=0.5, payoff_ratio=2.0, risk_per_trade=0.05
        )
        assert ror > 0.0
        assert ror <= 1.0

    def test_no_edge_returns_one(self, rm: RiskManager):
        """Win rate and payoff that yield no edge => RoR = 1.0."""
        # edge = 0.3 * 1.0 - 0.7 = -0.4 => no edge
        ror = rm.calculate_risk_of_ruin(
            win_rate=0.3, payoff_ratio=1.0, risk_per_trade=0.01
        )
        assert ror == 1.0

    def test_invalid_win_rate_returns_one(self, rm: RiskManager):
        ror = rm.calculate_risk_of_ruin(0.0, 2.0, 0.01)
        assert ror == 1.0

    def test_invalid_payoff_returns_one(self, rm: RiskManager):
        ror = rm.calculate_risk_of_ruin(0.5, 0.0, 0.01)
        assert ror == 1.0

    def test_invalid_risk_per_trade_returns_one(self, rm: RiskManager):
        ror = rm.calculate_risk_of_ruin(0.5, 2.0, 0.0)
        assert ror == 1.0

    def test_result_bounded_0_to_1(self, rm: RiskManager):
        ror = rm.calculate_risk_of_ruin(0.6, 2.5, 0.02)
        assert 0.0 <= ror <= 1.0


# ===================================================================
# Tests: validate_order
# ===================================================================


class TestValidateOrder:
    def test_approved_order(self, rm: RiskManager):
        approved, reason = rm.validate_order({
            "symbol": "AAPL",
            "entry_price": 100.0,
            "stop_price": 95.0,
            "take_profit_price": 112.5,
            "capital": 100_000.0,
            "daily_pnl": 0.0,
            "weekly_pnl": 0.0,
            "monthly_pnl": 0.0,
            "current_positions": 2,
            "current_grids": 1,
        })
        assert approved is True
        assert reason == ""

    def test_rejected_no_stop_loss(self, rm: RiskManager):
        approved, reason = rm.validate_order({
            "symbol": "AAPL",
            "entry_price": 100.0,
            "stop_price": None,
            "take_profit_price": 110.0,
            "capital": 100_000.0,
            "daily_pnl": 0.0,
            "weekly_pnl": 0.0,
            "monthly_pnl": 0.0,
            "current_positions": 2,
            "current_grids": 1,
        })
        assert approved is False
        assert "Stop-loss" in reason

    def test_rejected_zero_entry_price(self, rm: RiskManager):
        approved, reason = rm.validate_order({
            "symbol": "AAPL",
            "entry_price": 0.0,
            "stop_price": 95.0,
            "take_profit_price": 110.0,
            "capital": 100_000.0,
            "daily_pnl": 0.0,
            "weekly_pnl": 0.0,
            "monthly_pnl": 0.0,
            "current_positions": 2,
            "current_grids": 1,
        })
        assert approved is False

    def test_rejected_daily_limit_exceeded(self, rm: RiskManager):
        approved, reason = rm.validate_order({
            "symbol": "AAPL",
            "entry_price": 100.0,
            "stop_price": 95.0,
            "take_profit_price": 110.0,
            "capital": 100_000.0,
            "daily_pnl": -5_000.0,  # 5% > 3% limit
            "weekly_pnl": 0.0,
            "monthly_pnl": 0.0,
            "current_positions": 2,
            "current_grids": 1,
        })
        assert approved is False
        assert "diári" in reason.lower() or "daily" in reason.lower() or "diario" in reason.lower()

    def test_rejected_max_positions(self, rm: RiskManager):
        approved, reason = rm.validate_order({
            "symbol": "AAPL",
            "entry_price": 100.0,
            "stop_price": 95.0,
            "take_profit_price": 110.0,
            "capital": 100_000.0,
            "daily_pnl": 0.0,
            "weekly_pnl": 0.0,
            "monthly_pnl": 0.0,
            "current_positions": 8,  # At max
            "current_grids": 1,
        })
        assert approved is False

    def test_rejected_max_grids(self, rm: RiskManager):
        approved, reason = rm.validate_order({
            "symbol": "AAPL",
            "entry_price": 100.0,
            "stop_price": 95.0,
            "take_profit_price": 110.0,
            "capital": 100_000.0,
            "daily_pnl": 0.0,
            "weekly_pnl": 0.0,
            "monthly_pnl": 0.0,
            "current_positions": 2,
            "current_grids": 3,  # At max
        })
        assert approved is False

    def test_rejected_insufficient_rr_ratio(self, rm: RiskManager):
        """R:R = 1.0 < 2.0 min => rejected."""
        approved, reason = rm.validate_order({
            "symbol": "AAPL",
            "entry_price": 100.0,
            "stop_price": 95.0,
            "take_profit_price": 105.0,  # R:R = 5/5 = 1.0
            "capital": 100_000.0,
            "daily_pnl": 0.0,
            "weekly_pnl": 0.0,
            "monthly_pnl": 0.0,
            "current_positions": 2,
            "current_grids": 1,
        })
        assert approved is False
        assert "R:R" in reason

    def test_rejected_averaging_down(self, rm: RiskManager):
        rm.mark_level_losing("AAPL", 3)
        approved, reason = rm.validate_order({
            "symbol": "AAPL",
            "entry_price": 100.0,
            "stop_price": 95.0,
            "take_profit_price": 110.0,
            "capital": 100_000.0,
            "daily_pnl": 0.0,
            "weekly_pnl": 0.0,
            "monthly_pnl": 0.0,
            "current_positions": 2,
            "current_grids": 1,
            "level": 3,
        })
        assert approved is False
        assert "averaging" in reason.lower()

    def test_rejected_kill_switch(self, rm: RiskManager):
        approved, reason = rm.validate_order({
            "symbol": "AAPL",
            "entry_price": 100.0,
            "stop_price": 95.0,
            "take_profit_price": 110.0,
            "capital": 100_000.0,
            "daily_pnl": 0.0,
            "weekly_pnl": 0.0,
            "monthly_pnl": -15_000.0,  # 15% > 10% limit
            "current_positions": 2,
            "current_grids": 1,
        })
        assert approved is False
        assert "KILL" in reason.upper()


# ===================================================================
# Tests: calculate_stop_loss and calculate_take_profit
# ===================================================================


class TestStopLossAndTakeProfit:
    def test_stop_loss_basic(self, rm: RiskManager):
        stop = rm.calculate_stop_loss(entry_price=100.0, atr=2.0, multiplier=1.0)
        assert stop == pytest.approx(98.0)

    def test_stop_loss_default_multiplier(self, rm: RiskManager):
        stop = rm.calculate_stop_loss(entry_price=100.0, atr=2.0)
        assert stop == pytest.approx(98.0)

    def test_stop_loss_never_negative(self, rm: RiskManager):
        stop = rm.calculate_stop_loss(entry_price=1.0, atr=5.0, multiplier=2.0)
        assert stop >= 0.01

    def test_stop_loss_invalid_entry_raises(self, rm: RiskManager):
        with pytest.raises(ValueError):
            rm.calculate_stop_loss(entry_price=0.0, atr=2.0)

    def test_stop_loss_invalid_atr_raises(self, rm: RiskManager):
        with pytest.raises(ValueError):
            rm.calculate_stop_loss(entry_price=100.0, atr=0.0)

    def test_take_profit_basic(self, rm: RiskManager):
        tp = rm.calculate_take_profit(entry_price=100.0, atr=2.0, multiplier=2.5)
        assert tp == pytest.approx(105.0)

    def test_take_profit_default_multiplier(self, rm: RiskManager):
        tp = rm.calculate_take_profit(entry_price=100.0, atr=2.0)
        assert tp == pytest.approx(105.0)

    def test_take_profit_invalid_entry_raises(self, rm: RiskManager):
        with pytest.raises(ValueError):
            rm.calculate_take_profit(entry_price=0.0, atr=2.0)

    def test_take_profit_invalid_atr_raises(self, rm: RiskManager):
        with pytest.raises(ValueError):
            rm.calculate_take_profit(entry_price=100.0, atr=-1.0)


# ===================================================================
# Tests: Zero averaging down
# ===================================================================


class TestZeroAveragingDown:
    def test_mark_and_check_losing(self, rm: RiskManager):
        rm.mark_level_losing("AAPL", 2)
        assert rm.is_level_losing("AAPL", 2) is True
        assert rm.check_averaging_down("AAPL", 2) is False

    def test_clear_losing(self, rm: RiskManager):
        rm.mark_level_losing("AAPL", 2)
        rm.clear_level_losing("AAPL", 2)
        assert rm.is_level_losing("AAPL", 2) is False
        assert rm.check_averaging_down("AAPL", 2) is True

    def test_different_symbols_independent(self, rm: RiskManager):
        rm.mark_level_losing("AAPL", 1)
        assert rm.is_level_losing("AAPL", 1) is True
        assert rm.is_level_losing("MSFT", 1) is False

    def test_different_levels_independent(self, rm: RiskManager):
        rm.mark_level_losing("AAPL", 1)
        assert rm.is_level_losing("AAPL", 1) is True
        assert rm.is_level_losing("AAPL", 2) is False

    def test_unmarked_level_is_safe(self, rm: RiskManager):
        assert rm.check_averaging_down("XYZ", 5) is True


# ===================================================================
# Tests: validate_startup
# ===================================================================


class TestValidateStartup:
    def test_startup_passes_with_low_risk(self, rm: RiskManager):
        result = rm.validate_startup(win_rate=0.5, payoff_ratio=2.0)
        assert result.passed is True
        assert result.status == RiskStatus.APPROVED

    def test_startup_fails_with_high_risk(self):
        """Very high risk_per_level should cause high RoR and fail startup."""
        rm = RiskManager(capital=100_000, risk_per_level=0.10, kelly_cap=0.25)
        # With poor win rate, the RoR might exceed 1%
        result = rm.validate_startup(win_rate=0.4, payoff_ratio=1.5)
        # edge = 0.4 * 1.5 - 0.6 = 0.0 => no edge => RoR = 1.0
        assert result.passed is False

    def test_startup_result_is_risk_check_result(self, rm: RiskManager):
        result = rm.validate_startup()
        assert isinstance(result, RiskCheckResult)
        assert result.metric_name == "risk_of_ruin_arranque"


# ===================================================================
# Tests: RiskManager initialization validation
# ===================================================================


class TestRiskManagerInit:
    def test_zero_capital_raises(self):
        with pytest.raises(ValueError):
            RiskManager(capital=0)

    def test_negative_capital_raises(self):
        with pytest.raises(ValueError):
            RiskManager(capital=-1000)

    def test_invalid_risk_per_level_raises(self):
        with pytest.raises(ValueError):
            RiskManager(capital=100_000, risk_per_level=0.0)

    def test_invalid_max_positions_raises(self):
        with pytest.raises(ValueError):
            RiskManager(capital=100_000, max_positions=0)

    def test_invalid_min_rr_raises(self):
        with pytest.raises(ValueError):
            RiskManager(capital=100_000, min_rr=0)

    def test_capital_property(self, rm: RiskManager):
        assert rm.capital == 100_000.0

    def test_initial_capital_property(self, rm: RiskManager):
        assert rm.initial_capital == 100_000.0

    def test_update_capital(self, rm: RiskManager):
        rm.update_capital(110_000.0)
        assert rm.capital == 110_000.0
        assert rm.initial_capital == 100_000.0

    def test_update_capital_negative_raises(self, rm: RiskManager):
        with pytest.raises(ValueError):
            rm.update_capital(-1.0)

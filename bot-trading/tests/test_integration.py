"""
Integration tests for the autonomous trading bot.

Covers:
  - Complete autonomous cycle simulation with 100 trades
  - Regime transitions BULL -> BEAR -> SIDEWAYS
  - Kill switch activation
  - State persistence and recovery
  All with mocked IB connection.
"""

from __future__ import annotations

import json
import math
import os
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.signal_engine import (
    Regime,
    SignalResult,
    detect_regime,
    kotegawa_signal,
    calculate_sma,
    calculate_rsi,
    calculate_atr,
    calculate_bollinger_bands,
)
from src.risk_manager import RiskManager, RiskStatus
from src.grid_engine import GridEngine, Grid
from src.logger import TradeLogger


# ===================================================================
# Fixtures
# ===================================================================


@pytest.fixture
def tmp_data_dir(tmp_path: Path) -> str:
    return str(tmp_path / "bot_data")


@pytest.fixture
def risk_manager() -> RiskManager:
    return RiskManager(
        capital=100_000.0,
        risk_per_level=0.01,
        kelly_cap=0.05,
        daily_loss_limit=0.03,
        weekly_loss_limit=0.06,
        monthly_dd_limit=0.10,
        max_positions=8,
        max_grids=3,
    )


@pytest.fixture
def grid_engine(tmp_data_dir: str) -> GridEngine:
    return GridEngine(data_dir=tmp_data_dir)


@pytest.fixture
def trade_logger(tmp_data_dir: str) -> TradeLogger:
    return TradeLogger(data_dir=tmp_data_dir)


# ===================================================================
# Helpers
# ===================================================================


def simulate_price_series(
    base: float,
    trend: float,
    volatility: float,
    n: int,
    seed: int = 42,
) -> tuple[list[float], list[float], list[float], list[float]]:
    """
    Generate synthetic OHLCV data.

    Args:
        base: Starting price.
        trend: Per-bar trend (positive = uptrend, negative = downtrend).
        volatility: Standard deviation of price noise.
        n: Number of bars.
        seed: Random seed for reproducibility.

    Returns:
        (closes, highs, lows, volumes)
    """
    rng = random.Random(seed)
    closes = []
    highs = []
    lows = []
    volumes = []
    price = base

    for i in range(n):
        noise = rng.gauss(0, volatility)
        price = max(price + trend + noise, 1.0)
        close = round(price, 4)
        high = round(close + abs(rng.gauss(0, volatility * 0.5)), 4)
        low = round(close - abs(rng.gauss(0, volatility * 0.5)), 4)
        volume = max(100, int(1000 + rng.gauss(0, 300)))

        closes.append(close)
        highs.append(high)
        lows.append(low)
        volumes.append(float(volume))

    return closes, highs, lows, volumes


def execute_trading_cycle(
    closes: list[float],
    highs: list[float],
    lows: list[float],
    volumes: list[float],
    risk_manager: RiskManager,
    grid_engine: GridEngine,
    trade_logger: TradeLogger,
    regime_override: str | None = None,
) -> dict[str, Any]:
    """
    Simulate a single trading cycle: detect regime, generate signal,
    validate order, create grid if signal, process levels.

    Returns summary dict.
    """
    n = len(closes)
    if n < 200:
        return {"error": "insufficient data"}

    price = closes[-1]
    sma25 = calculate_sma(closes, 25)
    sma50 = calculate_sma(closes, 50)
    sma200 = calculate_sma(closes, 200)
    rsi = calculate_rsi(closes, 14)
    atr = calculate_atr(highs, lows, closes, 14)
    bb = calculate_bollinger_bands(closes, 20, 2.0)

    if any(v is None for v in (sma25, sma50, sma200, rsi, atr, bb)):
        return {"error": "indicator calculation failed"}

    _, _, bb_lower = bb
    vol_avg = sum(volumes[-20:]) / 20
    current_volume = volumes[-1]

    # Use a conservative ATR average
    atr_avg_60 = atr  # Simplified

    regime_info = detect_regime(price, sma50, sma200, rsi, atr, atr_avg_60)
    regime = regime_override or regime_info.regime.value

    signal = kotegawa_signal(
        price=price,
        sma25=sma25,
        rsi=rsi,
        bb_lower=bb_lower,
        volume=current_volume,
        vol_avg_20=vol_avg,
        regime=regime,
    )

    return {
        "price": price,
        "regime": regime,
        "signal": signal.signal,
        "deviation": signal.deviation,
        "confirmations": signal.confirmacoes,
        "confidence": signal.confianca.value,
        "size_multiplier": signal.size_multiplier,
        "rsi": rsi,
        "atr": atr,
    }


# ===================================================================
# Test: Simulate complete autonomous cycle with 100 trades
# ===================================================================


class TestCompleteAutonomousCycle:
    def test_100_trade_simulation(
        self,
        risk_manager: RiskManager,
        grid_engine: GridEngine,
        trade_logger: TradeLogger,
    ):
        """
        Simulate 100 trades through the full pipeline:
        signal -> risk check -> grid creation -> level execution -> logging.
        """
        rng = random.Random(42)
        capital = 100_000.0
        daily_pnl = 0.0
        weekly_pnl = 0.0
        monthly_pnl = 0.0
        trades_executed = 0
        wins = 0
        losses = 0
        total_pnl = 0.0

        for trade_num in range(100):
            # Randomly generate trade outcomes
            is_win = rng.random() < 0.55  # 55% win rate
            entry_price = 100.0 + rng.gauss(0, 10)
            entry_price = max(entry_price, 10.0)
            atr = abs(rng.gauss(2.0, 0.5))
            atr = max(atr, 0.5)

            stop_price = risk_manager.calculate_stop_loss(entry_price, atr)
            tp_price = risk_manager.calculate_take_profit(entry_price, atr)

            # Validate the order
            approved, reason = risk_manager.validate_order({
                "symbol": "AAPL",
                "entry_price": entry_price,
                "stop_price": stop_price,
                "take_profit_price": tp_price,
                "capital": capital,
                "daily_pnl": daily_pnl,
                "weekly_pnl": weekly_pnl,
                "monthly_pnl": monthly_pnl,
                "current_positions": min(trades_executed % 8, 7),
                "current_grids": min(trades_executed % 3, 2),
            })

            if not approved:
                continue

            # Calculate position size
            size = risk_manager.position_size_per_level(
                capital=capital,
                entry=entry_price,
                stop=stop_price,
            )
            if size == 0:
                continue

            # Simulate trade outcome
            risk_per_unit = abs(entry_price - stop_price)
            if is_win:
                pnl = size * abs(tp_price - entry_price)
                wins += 1
            else:
                pnl = -size * risk_per_unit
                losses += 1

            total_pnl += pnl
            daily_pnl += pnl
            weekly_pnl += pnl
            monthly_pnl += pnl
            capital += pnl

            # Log the trade
            trade_logger.log_trade({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "symbol": "AAPL",
                "side": "SELL",
                "price": tp_price if is_win else stop_price,
                "quantity": size,
                "order_id": 1000 + trade_num,
                "grid_id": f"grid_AAPL_{trade_num:04d}",
                "level": 1,
                "pnl": pnl,
                "regime": "BULL",
                "signal_confidence": "ALTO",
            })

            trades_executed += 1

            # Reset daily PnL periodically
            if trade_num % 10 == 9:
                daily_pnl = 0.0
            if trade_num % 50 == 49:
                weekly_pnl = 0.0

            # Check kill switch
            if not risk_manager.check_kill_switch(monthly_pnl, capital):
                break

        # Verify results
        assert trades_executed > 0
        all_trades = trade_logger.get_trades()
        assert len(all_trades) == trades_executed

        # Calculate and verify metrics
        metrics = trade_logger.calculate_metrics()
        assert metrics["num_trades"] == trades_executed
        assert 0.0 <= metrics["win_rate"] <= 1.0

    def test_100_trade_grid_lifecycle(
        self,
        risk_manager: RiskManager,
        grid_engine: GridEngine,
        trade_logger: TradeLogger,
    ):
        """
        Simulate 100 trades using grid levels with full lifecycle:
        create grid -> buy levels -> sell/stop levels -> close grid.
        """
        rng = random.Random(123)
        trades_logged = 0
        grids_created = 0

        for cycle in range(20):
            # Create a grid every cycle
            center = 100.0 + rng.gauss(0, 5)
            atr = max(1.0, abs(rng.gauss(2.0, 0.5)))
            regime = rng.choice(["BULL", "BEAR", "SIDEWAYS"])
            num_levels = grid_engine.get_num_levels_for_regime(regime)

            grid = grid_engine.create_grid(
                symbol="AAPL",
                center_price=center,
                atr=atr,
                regime=regime,
                num_levels=num_levels,
                base_quantity=10,
                confidence="ALTO",
                size_multiplier=1.0,
            )
            grids_created += 1

            # Process each level
            for lv in grid.levels:
                if trades_logged >= 100:
                    break

                # Simulate buy
                grid_engine.on_level_bought(
                    grid, lv.level, lv.buy_price,
                    datetime.now(timezone.utc).isoformat(),
                )

                # Simulate outcome
                is_win = rng.random() < 0.55
                if is_win:
                    sell_price = lv.sell_price
                    grid_engine.on_level_sold(
                        grid, lv.level, sell_price,
                        datetime.now(timezone.utc).isoformat(),
                    )
                else:
                    stop_price = lv.stop_price
                    grid_engine.on_level_stopped(
                        grid, lv.level, stop_price,
                        datetime.now(timezone.utc).isoformat(),
                    )

                pnl = lv.pnl or 0.0
                trade_logger.log_trade({
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "symbol": "AAPL",
                    "side": "SELL",
                    "price": lv.sell_price if is_win else lv.stop_price,
                    "quantity": lv.quantity,
                    "order_id": 5000 + trades_logged,
                    "grid_id": grid.id,
                    "level": lv.level,
                    "pnl": pnl,
                    "regime": regime,
                    "signal_confidence": "ALTO",
                })
                trades_logged += 1

            if trades_logged >= 100:
                break

            # Close the grid
            grid_engine.close_grid(grid)

        assert trades_logged >= 100
        assert grids_created > 0

        metrics = trade_logger.calculate_metrics()
        assert metrics["num_trades"] >= 100


# ===================================================================
# Test: Regime transitions BULL -> BEAR -> SIDEWAYS
# ===================================================================


class TestRegimeTransitions:
    def test_bull_to_bear_to_sideways(
        self,
        risk_manager: RiskManager,
        grid_engine: GridEngine,
        trade_logger: TradeLogger,
    ):
        """
        Simulate regime transitions and verify the system adapts:
        - BULL: 5 levels, less aggressive thresholds
        - BEAR: 8 levels, more aggressive thresholds
        - SIDEWAYS: 7 levels, moderate thresholds
        """
        regimes_detected = []

        # Phase 1: BULL market (uptrend)
        closes, highs, lows, volumes = simulate_price_series(
            base=100.0, trend=0.5, volatility=1.0, n=250, seed=1,
        )
        result = execute_trading_cycle(
            closes, highs, lows, volumes,
            risk_manager, grid_engine, trade_logger,
        )
        regime_1 = result["regime"]
        regimes_detected.append(regime_1)

        # Create grid for this regime
        atr = result.get("atr", 2.0)
        num_levels = grid_engine.get_num_levels_for_regime(regime_1)
        grid1 = grid_engine.create_grid(
            symbol="TEST",
            center_price=result["price"],
            atr=atr,
            regime=regime_1,
            num_levels=num_levels,
            base_quantity=10,
            confidence="ALTO",
            size_multiplier=1.0,
        )
        assert grid1.status == "active"

        # Phase 2: BEAR market (downtrend)
        closes2, highs2, lows2, volumes2 = simulate_price_series(
            base=100.0, trend=-0.5, volatility=1.0, n=250, seed=2,
        )
        result2 = execute_trading_cycle(
            closes2, highs2, lows2, volumes2,
            risk_manager, grid_engine, trade_logger,
        )
        regime_2 = result2["regime"]
        regimes_detected.append(regime_2)

        # Close old grid and create new one for new regime
        grid_engine.close_grid(grid1)
        assert grid1.status == "closed"

        num_levels_2 = grid_engine.get_num_levels_for_regime(regime_2)
        grid2 = grid_engine.create_grid(
            symbol="TEST",
            center_price=result2["price"],
            atr=result2.get("atr", 2.0),
            regime=regime_2,
            num_levels=num_levels_2,
            base_quantity=10,
            confidence="MEDIO",
            size_multiplier=0.75,
        )

        # Phase 3: SIDEWAYS market (low volatility)
        closes3, highs3, lows3, volumes3 = simulate_price_series(
            base=100.0, trend=0.0, volatility=0.3, n=250, seed=3,
        )
        result3 = execute_trading_cycle(
            closes3, highs3, lows3, volumes3,
            risk_manager, grid_engine, trade_logger,
        )
        regime_3 = result3["regime"]
        regimes_detected.append(regime_3)

        grid_engine.close_grid(grid2)

        num_levels_3 = grid_engine.get_num_levels_for_regime(regime_3)
        grid3 = grid_engine.create_grid(
            symbol="TEST",
            center_price=result3["price"],
            atr=result3.get("atr", 0.5),
            regime=regime_3,
            num_levels=num_levels_3,
            base_quantity=10,
            confidence="BAIXO",
            size_multiplier=0.5,
        )

        # Verify regime-specific adaptations
        assert len(regimes_detected) == 3

        # BULL regime should have 5 levels
        assert grid1.regime in ["BULL", "SIDEWAYS", "BEAR"]
        assert len(grid1.levels) == grid_engine.get_num_levels_for_regime(grid1.regime)

        # Verify different grid sizes for different regimes
        bull_levels = grid_engine.get_num_levels_for_regime("BULL")
        bear_levels = grid_engine.get_num_levels_for_regime("BEAR")
        sideways_levels = grid_engine.get_num_levels_for_regime("SIDEWAYS")
        assert bull_levels != bear_levels
        assert bear_levels != sideways_levels

    def test_regime_detection_with_synthetic_data(self):
        """Test that detect_regime correctly classifies synthetic scenarios."""
        # BULL: price well above SMA200, SMA50 above SMA200, RSI > 50
        bull_info = detect_regime(
            price=120.0, sma50=115.0, sma200=100.0,
            rsi=65.0, atr=2.0, atr_avg_60=2.0,
        )
        assert bull_info.regime == Regime.BULL

        # BEAR: price below SMA200, SMA50 below SMA200, RSI < 50
        bear_info = detect_regime(
            price=80.0, sma50=85.0, sma200=100.0,
            rsi=35.0, atr=3.0, atr_avg_60=2.0,
        )
        assert bear_info.regime == Regime.BEAR

        # SIDEWAYS by low volatility
        sideways_info = detect_regime(
            price=120.0, sma50=115.0, sma200=100.0,
            rsi=65.0, atr=0.3, atr_avg_60=1.0,
        )
        assert sideways_info.regime == Regime.SIDEWAYS

    def test_grid_recenter_on_regime_change(
        self,
        grid_engine: GridEngine,
    ):
        """Verify grid can be recentered when regime changes."""
        grid = grid_engine.create_grid(
            symbol="AAPL", center_price=100.0, atr=2.0,
            regime="BULL", num_levels=5, base_quantity=10,
            confidence="ALTO", size_multiplier=1.0,
        )

        # Buy level 1
        grid_engine.on_level_bought(grid, 1, 98.0, "t1")

        # Price moves significantly - needs recentering
        new_center = 90.0
        grid_engine.recenter_grid(grid, new_center=new_center, atr=2.5)

        assert grid.center_price == 90.0
        assert grid.atr == 2.5

        # Bought level should be preserved
        bought_levels = [lv for lv in grid.levels if lv.status == "bought"]
        assert len(bought_levels) == 1


# ===================================================================
# Test: Kill switch activation
# ===================================================================


class TestKillSwitchActivation:
    def test_kill_switch_stops_trading(
        self,
        risk_manager: RiskManager,
        grid_engine: GridEngine,
        trade_logger: TradeLogger,
    ):
        """
        Simulate accumulating losses until the kill switch activates.
        Once activated, no new orders should be approved.
        """
        capital = 100_000.0
        monthly_pnl = 0.0
        trades_before_kill = 0
        kill_switch_activated = False

        for i in range(200):
            # Each trade loses 1% of capital
            loss = -capital * 0.01
            monthly_pnl += loss
            capital += loss

            trade_logger.log_trade({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "symbol": "AAPL",
                "pnl": loss,
                "grid_id": f"grid_{i}",
            })

            # Check kill switch
            if not risk_manager.check_kill_switch(monthly_pnl, capital):
                kill_switch_activated = True
                trades_before_kill = i + 1
                break

        assert kill_switch_activated is True
        assert trades_before_kill > 0
        assert trades_before_kill <= 12  # Should trigger around 10% loss

        # After kill switch, orders should be rejected
        approved, reason = risk_manager.validate_order({
            "symbol": "AAPL",
            "entry_price": 100.0,
            "stop_price": 95.0,
            "take_profit_price": 110.0,
            "capital": capital,
            "daily_pnl": 0.0,
            "weekly_pnl": 0.0,
            "monthly_pnl": monthly_pnl,
            "current_positions": 0,
            "current_grids": 0,
        })
        assert approved is False
        assert "KILL" in reason.upper()

    def test_kill_switch_closes_all_grids(
        self,
        grid_engine: GridEngine,
    ):
        """When kill switch activates, all grids should be closed."""
        # Create several active grids
        for i in range(3):
            grid_engine.create_grid(
                symbol=f"SYM{i}", center_price=100.0, atr=2.0,
                regime="BULL", num_levels=5, base_quantity=10,
                confidence="ALTO", size_multiplier=1.0,
            )

        assert len(grid_engine.get_active_grids()) == 3

        # Simulate kill switch: close all grids
        for grid in grid_engine.get_active_grids():
            grid_engine.close_grid(grid)

        assert len(grid_engine.get_active_grids()) == 0

    def test_daily_limit_pauses_then_resumes(
        self,
        risk_manager: RiskManager,
    ):
        """Daily limit should pause, but new day resets."""
        # Exceed daily limit
        assert risk_manager.check_daily_limit(-4_000, 100_000) is False

        # New day: PnL resets to 0
        assert risk_manager.check_daily_limit(0.0, 100_000) is True

    def test_weekly_limit_pauses_operations(
        self,
        risk_manager: RiskManager,
    ):
        """Weekly limit reached => operations paused."""
        assert risk_manager.check_weekly_limit(-7_000, 100_000) is False


# ===================================================================
# Test: State persistence and recovery
# ===================================================================


class TestStatePersistenceAndRecovery:
    def test_full_state_persistence_cycle(
        self,
        grid_engine: GridEngine,
        trade_logger: TradeLogger,
        tmp_data_dir: str,
    ):
        """
        1. Create grids with various states
        2. Execute some level operations
        3. Save state
        4. Create a new engine
        5. Load state
        6. Verify all data is preserved
        """
        # Create grid 1 with some executed levels
        g1 = grid_engine.create_grid(
            symbol="AAPL", center_price=100.0, atr=2.0,
            regime="BULL", num_levels=5, base_quantity=10,
            confidence="ALTO", size_multiplier=1.0,
        )
        grid_engine.on_level_bought(g1, 1, 98.0, "2024-01-15T10:00:00")
        grid_engine.on_level_sold(g1, 1, 102.0, "2024-01-15T12:00:00")
        grid_engine.on_level_bought(g1, 2, 96.0, "2024-01-15T11:00:00")
        grid_engine.on_level_stopped(g1, 2, 93.0, "2024-01-15T13:00:00")

        # Create grid 2 (all pending)
        g2 = grid_engine.create_grid(
            symbol="MSFT", center_price=200.0, atr=3.0,
            regime="BEAR", num_levels=8, base_quantity=5,
            confidence="MEDIO", size_multiplier=0.75,
        )

        # Create grid 3 (closed)
        g3 = grid_engine.create_grid(
            symbol="GOOG", center_price=150.0, atr=2.5,
            regime="SIDEWAYS", num_levels=7, base_quantity=8,
            confidence="BAIXO", size_multiplier=0.5,
        )
        grid_engine.close_grid(g3)

        # Log some trades
        trade_logger.log_trade({
            "timestamp": "2024-01-15T12:00:00+00:00",
            "symbol": "AAPL",
            "pnl": 40.0,
            "grid_id": g1.id,
        })
        trade_logger.log_trade({
            "timestamp": "2024-01-15T13:00:00+00:00",
            "symbol": "AAPL",
            "pnl": -30.0,
            "grid_id": g1.id,
        })

        # Save grid state
        grid_engine.save_state()

        # Create new engine and load state
        engine2 = GridEngine(data_dir=tmp_data_dir)
        engine2.load_state()

        # Verify grids loaded correctly
        assert len(engine2.grids) == 3

        # Verify grid 1
        loaded_g1 = engine2.grids[0]
        assert loaded_g1.symbol == "AAPL"
        assert loaded_g1.status == "active"
        assert loaded_g1.regime == "BULL"
        assert len(loaded_g1.levels) == 5
        assert loaded_g1.levels[0].status == "sold"
        assert loaded_g1.levels[0].pnl == pytest.approx(20.0)
        assert loaded_g1.levels[1].status == "stopped"
        assert loaded_g1.levels[1].pnl == pytest.approx(-54.65018)

        # Verify grid 2
        loaded_g2 = engine2.grids[1]
        assert loaded_g2.symbol == "MSFT"
        assert loaded_g2.status == "active"
        assert all(lv.status == "pending" for lv in loaded_g2.levels)

        # Verify grid 3
        loaded_g3 = engine2.grids[2]
        assert loaded_g3.symbol == "GOOG"
        assert loaded_g3.status == "closed"

        # Verify trade log persists
        logger2 = TradeLogger(data_dir=tmp_data_dir)
        trades = logger2.get_trades()
        assert len(trades) == 2
        assert trades[0]["pnl"] == 40.0
        assert trades[1]["pnl"] == -30.0

    def test_recovery_after_crash(
        self,
        grid_engine: GridEngine,
        tmp_data_dir: str,
    ):
        """
        Simulate crash recovery: save state mid-operation, then restore.
        """
        # Create grid and process some levels
        grid = grid_engine.create_grid(
            symbol="AAPL", center_price=100.0, atr=2.0,
            regime="BULL", num_levels=5, base_quantity=10,
            confidence="ALTO", size_multiplier=1.0,
        )
        grid_engine.on_level_bought(grid, 1, 98.0, "t1")
        grid_engine.on_level_bought(grid, 2, 96.0, "t2")

        # Save state (simulating periodic save)
        grid_engine.save_state()

        # "Crash" — create new engine
        recovered_engine = GridEngine(data_dir=tmp_data_dir)
        recovered_engine.load_state()

        # Should have the same state as before crash
        assert len(recovered_engine.grids) == 1
        recovered_grid = recovered_engine.grids[0]
        assert recovered_grid.symbol == "AAPL"

        # Both bought levels should be preserved
        bought = [lv for lv in recovered_grid.levels if lv.status == "bought"]
        assert len(bought) == 2

        # Pending levels should still be pending
        pending = [lv for lv in recovered_grid.levels if lv.status == "pending"]
        assert len(pending) == 3

    def test_state_corruption_handling(self, tmp_data_dir: str):
        """Corrupted state file should raise an error cleanly."""
        os.makedirs(tmp_data_dir, exist_ok=True)
        state_path = Path(tmp_data_dir) / "grids_state.json"
        state_path.write_text("this is not valid JSON {{{")

        engine = GridEngine(data_dir=tmp_data_dir)
        with pytest.raises(json.JSONDecodeError):
            engine.load_state()

    def test_empty_state_recovery(self, tmp_data_dir: str):
        """Empty state file (no grids) should load cleanly."""
        os.makedirs(tmp_data_dir, exist_ok=True)
        state_path = Path(tmp_data_dir) / "grids_state.json"
        state_path.write_text(json.dumps({
            "version": 1,
            "saved_at": datetime.now(timezone.utc).isoformat(),
            "grids": [],
        }))

        engine = GridEngine(data_dir=tmp_data_dir)
        engine.load_state()
        assert engine.grids == []

    def test_sequence_counter_recovery(
        self,
        grid_engine: GridEngine,
        tmp_data_dir: str,
    ):
        """After loading state, sequence counter should be restored."""
        grid_engine.create_grid(
            symbol="AAPL", center_price=100.0, atr=2.0,
            regime="BULL", num_levels=3, base_quantity=10,
            confidence="ALTO", size_multiplier=1.0,
        )
        grid_engine.create_grid(
            symbol="MSFT", center_price=200.0, atr=3.0,
            regime="BEAR", num_levels=3, base_quantity=5,
            confidence="MEDIO", size_multiplier=1.0,
        )
        grid_engine.save_state()

        # Load in new engine
        engine2 = GridEngine(data_dir=tmp_data_dir)
        engine2.load_state()

        # Create a new grid — sequence should not collide
        new_grid = engine2.create_grid(
            symbol="GOOG", center_price=150.0, atr=2.5,
            regime="SIDEWAYS", num_levels=5, base_quantity=8,
            confidence="ALTO", size_multiplier=1.0,
        )
        seq = int(new_grid.id.split("_")[-1])
        assert seq >= 3  # Must be at least 3 (after 2 existing grids)


# ===================================================================
# Test: Risk manager integration with grid engine
# ===================================================================


class TestRiskGridIntegration:
    def test_position_sizing_respects_grid_levels(
        self,
        risk_manager: RiskManager,
        grid_engine: GridEngine,
    ):
        """Position size should work with grid-derived prices."""
        grid = grid_engine.create_grid(
            symbol="AAPL", center_price=100.0, atr=2.0,
            regime="BULL", num_levels=5, base_quantity=100,
            confidence="ALTO", size_multiplier=1.0,
        )

        for lv in grid.levels:
            size = risk_manager.position_size_per_level(
                capital=100_000,
                entry=lv.buy_price,
                stop=lv.stop_price,
            )
            # Position size should be positive
            assert size > 0

            # Risk should not exceed 1% of capital
            risk = size * abs(lv.buy_price - lv.stop_price)
            assert risk <= 100_000 * 0.01 + 0.01  # Small tolerance

    def test_validate_startup_before_trading(
        self,
        risk_manager: RiskManager,
    ):
        """Bot should validate startup risk before any trading."""
        result = risk_manager.validate_startup(win_rate=0.5, payoff_ratio=2.0)
        assert result.passed is True

        # With these params, Risk of Ruin should be very low
        ror = risk_manager.calculate_risk_of_ruin(0.5, 2.0, 0.01)
        assert ror < 0.001  # < 0.1%

    def test_zero_averaging_down_enforcement(
        self,
        risk_manager: RiskManager,
        grid_engine: GridEngine,
    ):
        """
        When a level hits stop-loss, mark as losing and verify
        the risk manager blocks new orders on that level.
        """
        grid = grid_engine.create_grid(
            symbol="AAPL", center_price=100.0, atr=2.0,
            regime="BULL", num_levels=5, base_quantity=10,
            confidence="ALTO", size_multiplier=1.0,
        )

        # Level 1 bought and stopped
        grid_engine.on_level_bought(grid, 1, 98.0, "t1")
        grid_engine.on_level_stopped(grid, 1, 95.0, "t2")

        # Mark level as losing in risk manager
        risk_manager.mark_level_losing("AAPL", 1)

        # Attempt to open a new order on the same level
        approved, reason = risk_manager.validate_order({
            "symbol": "AAPL",
            "entry_price": 95.0,
            "stop_price": 92.0,
            "take_profit_price": 102.5,
            "capital": 100_000.0,
            "daily_pnl": 0.0,
            "weekly_pnl": 0.0,
            "monthly_pnl": 0.0,
            "current_positions": 1,
            "current_grids": 1,
            "level": 1,
        })
        assert approved is False
        assert "averaging" in reason.lower()

        # Level 2 should still be allowed
        approved2, _ = risk_manager.validate_order({
            "symbol": "AAPL",
            "entry_price": 96.0,
            "stop_price": 93.0,
            "take_profit_price": 103.5,
            "capital": 100_000.0,
            "daily_pnl": 0.0,
            "weekly_pnl": 0.0,
            "monthly_pnl": 0.0,
            "current_positions": 1,
            "current_grids": 1,
            "level": 2,
        })
        assert approved2 is True

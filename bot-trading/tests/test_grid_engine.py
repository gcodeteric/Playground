"""
Tests for src/grid_engine.py

Covers: create_grid, get_num_levels_for_regime, should_recenter,
        on_level_bought/sold/stopped, close_grid, save_state/load_state,
        generate_grid_id, zero averaging down.
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.grid_engine import (
    Grid,
    GridEngine,
    GridLevel,
    _REGIME_NUM_LEVELS,
    _VALID_GRID_STATUSES,
    _VALID_LEVEL_STATUSES,
)


# ===================================================================
# Fixtures
# ===================================================================


@pytest.fixture
def tmp_data_dir(tmp_path: Path) -> str:
    """Create a temporary data directory for state persistence tests."""
    return str(tmp_path / "data")


@pytest.fixture
def engine(tmp_data_dir: str) -> GridEngine:
    return GridEngine(data_dir=tmp_data_dir)


@pytest.fixture
def sample_grid(engine: GridEngine) -> Grid:
    """Create a sample BULL grid with 5 levels."""
    return engine.create_grid(
        symbol="AAPL",
        center_price=100.0,
        atr=2.0,
        regime="BULL",
        num_levels=5,
        base_quantity=10,
        confidence="ALTO",
        size_multiplier=1.0,
    )


# ===================================================================
# Tests: create_grid
# ===================================================================


class TestCreateGrid:
    def test_grid_created_with_correct_fields(self, engine: GridEngine):
        grid = engine.create_grid(
            symbol="AAPL",
            center_price=100.0,
            atr=2.0,
            regime="BULL",
            num_levels=5,
            base_quantity=10,
            confidence="ALTO",
            size_multiplier=1.0,
        )
        assert grid.symbol == "AAPL"
        assert grid.status == "active"
        assert grid.regime == "BULL"
        assert grid.center_price == 100.0
        assert grid.atr == 2.0
        assert grid.spacing == pytest.approx(1.2)
        assert grid.spacing_pct == pytest.approx(1.2)
        assert grid.confidence == "ALTO"
        assert grid.size_multiplier == 1.0
        assert len(grid.levels) == 5
        assert grid.total_pnl == 0.0

    def test_grid_levels_prices(self, engine: GridEngine):
        grid = engine.create_grid(
            symbol="AAPL",
            center_price=100.0,
            atr=2.0,
            regime="BULL",
            num_levels=3,
            base_quantity=10,
            confidence="MEDIO",
            size_multiplier=1.0,
        )
        # spacing = clamp(ATR% * 0.6, 1%, 4%) = 1.2%
        # Finding v3: a grelha passou a geométrica.
        # Para 3 níveis: [100.0, 98.183502, 96.4]
        assert grid.levels[0].buy_price == pytest.approx(100.0)
        assert grid.levels[0].sell_price == pytest.approx(105.0)
        assert grid.levels[0].stop_price == pytest.approx(98.0)
        assert grid.levels[0].level == 1
        assert grid.levels[0].status == "pending"

        assert grid.levels[1].buy_price == pytest.approx(98.183502)

        assert grid.levels[2].buy_price == pytest.approx(96.4)

    def test_grid_quantity_adjusted_by_size_multiplier(self, engine: GridEngine):
        grid = engine.create_grid(
            symbol="AAPL",
            center_price=100.0,
            atr=2.0,
            regime="BULL",
            num_levels=3,
            base_quantity=10,
            confidence="MEDIO",
            size_multiplier=0.5,
        )
        # adjusted_qty = max(1, int(round(10 * 0.5))) = max(1, 5) = 5
        for lv in grid.levels:
            assert lv.quantity == 5

    def test_grid_quantity_minimum_one(self, engine: GridEngine):
        grid = engine.create_grid(
            symbol="AAPL",
            center_price=100.0,
            atr=2.0,
            regime="BULL",
            num_levels=1,
            base_quantity=1,
            confidence="BAIXO",
            size_multiplier=0.01,
        )
        # adjusted_qty = max(1, int(round(1 * 0.01))) = max(1, 0) = 1
        assert grid.levels[0].quantity == 1

    def test_grid_added_to_engine(self, engine: GridEngine):
        grid = engine.create_grid(
            symbol="AAPL", center_price=100.0, atr=2.0,
            regime="BULL", num_levels=5, base_quantity=10,
            confidence="ALTO", size_multiplier=1.0,
        )
        assert grid in engine.grids

    def test_create_grid_different_regimes(self, engine: GridEngine):
        for regime in ["BULL", "BEAR", "SIDEWAYS"]:
            grid = engine.create_grid(
                symbol="TEST", center_price=100.0, atr=2.0,
                regime=regime, num_levels=3, base_quantity=10,
                confidence="MEDIO", size_multiplier=1.0,
            )
            assert grid.regime == regime


# ===================================================================
# Tests: get_num_levels_for_regime
# ===================================================================


class TestGetNumLevelsForRegime:
    def test_bull_returns_5(self):
        assert GridEngine.get_num_levels_for_regime("BULL") == 5

    def test_bear_returns_4(self):
        assert GridEngine.get_num_levels_for_regime("BEAR") == 4

    def test_sideways_returns_8(self):
        assert GridEngine.get_num_levels_for_regime("SIDEWAYS") == 8

    def test_unknown_regime_returns_default_5(self):
        assert GridEngine.get_num_levels_for_regime("UNKNOWN") == 5

    def test_case_insensitive(self):
        assert GridEngine.get_num_levels_for_regime("bull") == 5
        assert GridEngine.get_num_levels_for_regime("Bear") == 4
        assert GridEngine.get_num_levels_for_regime("sideways") == 8


# ===================================================================
# Tests: should_recenter
# ===================================================================


class TestShouldRecenter:
    def test_no_recenter_when_price_at_center(self, engine: GridEngine, sample_grid: Grid):
        """Price at center => no recenter needed."""
        assert engine.should_recenter(sample_grid, 100.0) is False

    def test_recenter_when_price_drops_below_70_pct(self, engine: GridEngine, sample_grid: Grid):
        """Price drops below 70% of extension => should recenter."""
        # Center = 100, lowest_buy = 94.0
        # extension_down = 6.0
        # threshold_down = 95.8
        assert engine.should_recenter(sample_grid, 95.0) is True

    def test_no_recenter_within_70_pct(self, engine: GridEngine, sample_grid: Grid):
        """Price above 70% threshold => no recenter."""
        assert engine.should_recenter(sample_grid, 96.0) is False

    def test_recenter_price_moves_up_beyond_70_pct(self, engine: GridEngine, sample_grid: Grid):
        """Price moves above center + 70% of extension => recenter."""
        assert engine.should_recenter(sample_grid, 105.0) is True

    def test_no_recenter_empty_levels(self, engine: GridEngine):
        grid = Grid(
            id="test", symbol="AAPL", status="active", regime="BULL",
            created_at="2024-01-01", center_price=100.0, atr=2.0,
            spacing=2.0, levels=[],
        )
        assert engine.should_recenter(grid, 50.0) is False


class TestRespacing:
    def test_calculate_spacing_pct_uses_clamp(self, engine: GridEngine):
        assert engine.calculate_spacing_pct(100.0, 2.0) == pytest.approx(1.2)
        assert engine.calculate_spacing_pct(100.0, 20.0) == pytest.approx(4.0)

    def test_should_respace_requires_threshold_and_cooldown(
        self, engine: GridEngine, sample_grid: Grid
    ):
        sample_grid.last_respaced_at = "2024-01-01T10:00:00+00:00"
        now = datetime(2024, 1, 1, 10, 30, tzinfo=timezone.utc)
        assert engine.should_respace(sample_grid, 100.0, 5.0, now=now) is False

        later = datetime(2024, 1, 1, 11, 30, tzinfo=timezone.utc)
        assert engine.should_respace(sample_grid, 100.0, 5.0, now=later) is True


# ===================================================================
# Tests: on_level_bought, on_level_sold, on_level_stopped
# ===================================================================


class TestLevelEvents:
    def test_on_level_bought(self, engine: GridEngine, sample_grid: Grid):
        engine.on_level_bought(sample_grid, level=1, price=98.0, timestamp="2024-01-01T12:00:00")
        lv = sample_grid.levels[0]
        assert lv.status == "bought"
        assert lv.bought_at == "2024-01-01T12:00:00"

    def test_on_level_sold(self, engine: GridEngine, sample_grid: Grid):
        # First buy the level
        buy_price = sample_grid.levels[0].buy_price
        sell_price = sample_grid.levels[0].sell_price
        engine.on_level_bought(sample_grid, level=1, price=buy_price, timestamp="2024-01-01T12:00:00")

        # Then sell at take-profit
        engine.on_level_sold(sample_grid, level=1, price=sell_price, timestamp="2024-01-01T14:00:00")
        lv = sample_grid.levels[0]
        assert lv.status == "sold"
        assert lv.sold_at == "2024-01-01T14:00:00"
        expected_pnl = (sell_price - buy_price) * 10
        assert lv.pnl == pytest.approx(expected_pnl)
        assert sample_grid.total_pnl == pytest.approx(expected_pnl)

    def test_on_level_stopped(self, engine: GridEngine, sample_grid: Grid):
        buy_price = sample_grid.levels[1].buy_price
        stop_price = sample_grid.levels[1].stop_price
        engine.on_level_bought(sample_grid, level=2, price=buy_price, timestamp="2024-01-01T12:00:00")
        engine.on_level_stopped(sample_grid, level=2, price=stop_price, timestamp="2024-01-01T15:00:00")
        lv = sample_grid.levels[1]
        assert lv.status == "stopped"
        expected_pnl = (stop_price - buy_price) * 10
        assert lv.pnl == pytest.approx(expected_pnl)
        assert sample_grid.total_pnl == pytest.approx(expected_pnl)

    def test_on_level_not_found(self, engine: GridEngine, sample_grid: Grid):
        """Calling on_level_bought with nonexistent level should not crash."""
        engine.on_level_bought(sample_grid, level=99, price=50.0, timestamp="2024-01-01")
        # No exception, all levels unchanged
        for lv in sample_grid.levels:
            assert lv.status == "pending"

    def test_multiple_level_operations_accumulate_pnl(
        self, engine: GridEngine, sample_grid: Grid
    ):
        level1 = sample_grid.levels[0]
        engine.on_level_bought(sample_grid, 1, level1.buy_price, "t1")
        engine.on_level_sold(sample_grid, 1, level1.sell_price, "t2")

        level2 = sample_grid.levels[1]
        engine.on_level_bought(sample_grid, 2, level2.buy_price, "t3")
        engine.on_level_stopped(sample_grid, 2, level2.stop_price, "t4")

        expected_pnl = (
            (level1.sell_price - level1.buy_price) * level1.quantity
            + (level2.stop_price - level2.buy_price) * level2.quantity
        )
        assert sample_grid.total_pnl == pytest.approx(expected_pnl)


# ===================================================================
# Tests: close_grid
# ===================================================================


class TestCloseGrid:
    def test_close_grid_sets_status(self, engine: GridEngine, sample_grid: Grid):
        engine.close_grid(sample_grid)
        assert sample_grid.status == "closed"

    def test_close_grid_cancels_pending_levels(self, engine: GridEngine, sample_grid: Grid):
        engine.close_grid(sample_grid)
        for lv in sample_grid.levels:
            assert lv.status == "cancelled"

    def test_close_grid_calculates_pnl(self, engine: GridEngine, sample_grid: Grid):
        # Execute some levels before closing
        level1 = sample_grid.levels[0]
        level2 = sample_grid.levels[1]
        engine.on_level_bought(sample_grid, 1, level1.buy_price, "t1")
        engine.on_level_sold(sample_grid, 1, level1.sell_price, "t2")

        engine.on_level_bought(sample_grid, 2, level2.buy_price, "t3")
        engine.on_level_stopped(sample_grid, 2, level2.stop_price, "t4")

        engine.close_grid(sample_grid)

        expected_total = (
            (level1.sell_price - level1.buy_price) * level1.quantity
            + (level2.stop_price - level2.buy_price) * level2.quantity
        )
        assert sample_grid.total_pnl == pytest.approx(expected_total)
        assert sample_grid.status == "closed"

    def test_close_grid_preserves_completed_level_status(
        self, engine: GridEngine, sample_grid: Grid
    ):
        engine.on_level_bought(sample_grid, 1, sample_grid.levels[0].buy_price, "t1")
        engine.on_level_sold(sample_grid, 1, sample_grid.levels[0].sell_price, "t2")

        engine.close_grid(sample_grid)
        assert sample_grid.levels[0].status == "sold"  # Not cancelled
        assert sample_grid.levels[1].status == "cancelled"  # Was pending


# ===================================================================
# Tests: save_state and load_state
# ===================================================================


class TestPersistence:
    def test_save_and_load_state(self, engine: GridEngine, tmp_data_dir: str):
        engine.create_grid(
            symbol="AAPL", center_price=100.0, atr=2.0,
            regime="BULL", num_levels=3, base_quantity=10,
            confidence="ALTO", size_multiplier=1.0,
        )
        engine.save_state()

        # Load in a new engine
        engine2 = GridEngine(data_dir=tmp_data_dir)
        engine2.load_state()

        assert len(engine2.grids) == 1
        assert engine2.grids[0].symbol == "AAPL"
        assert engine2.grids[0].regime == "BULL"
        assert len(engine2.grids[0].levels) == 3

    def test_save_state_atomic_write(self, engine: GridEngine, tmp_data_dir: str):
        """Verify the state file exists after save (atomic rename)."""
        engine.create_grid(
            symbol="AAPL", center_price=100.0, atr=2.0,
            regime="BULL", num_levels=3, base_quantity=10,
            confidence="ALTO", size_multiplier=1.0,
        )
        engine.save_state()

        state_path = Path(tmp_data_dir) / "grids_state.json"
        assert state_path.exists()

        with open(state_path, "r") as f:
            data = json.load(f)
        assert data["version"] == 1
        assert len(data["grids"]) == 1

    def test_save_state_creates_backup(self, engine: GridEngine, tmp_data_dir: str):
        """Second save should create a backup of the first save."""
        engine.create_grid(
            symbol="AAPL", center_price=100.0, atr=2.0,
            regime="BULL", num_levels=2, base_quantity=10,
            confidence="MEDIO", size_multiplier=1.0,
        )
        engine.save_state()

        # Modify and save again
        engine.create_grid(
            symbol="MSFT", center_price=200.0, atr=3.0,
            regime="BEAR", num_levels=3, base_quantity=5,
            confidence="ALTO", size_multiplier=1.0,
        )
        engine.save_state()

        backup_path = Path(tmp_data_dir) / "grids_state.json.bak"
        assert backup_path.exists()

    def test_load_state_nonexistent_file(self, tmp_data_dir: str):
        """Loading from nonexistent file starts with empty grids."""
        engine = GridEngine(data_dir=tmp_data_dir)
        engine.load_state()
        assert engine.grids == []

    def test_load_state_schema_validation_rejects_invalid(self, tmp_data_dir: str):
        """Invalid schema should raise ValueError."""
        os.makedirs(tmp_data_dir, exist_ok=True)
        state_path = Path(tmp_data_dir) / "grids_state.json"
        state_path.write_text(json.dumps({"not_valid": True}))

        engine = GridEngine(data_dir=tmp_data_dir)
        with pytest.raises(ValueError, match="Esquema invalido"):
            engine.load_state()

    def test_load_state_validates_grid_status(self, tmp_data_dir: str):
        """Invalid grid status should raise ValueError."""
        os.makedirs(tmp_data_dir, exist_ok=True)
        state_path = Path(tmp_data_dir) / "grids_state.json"
        bad_data = {
            "version": 1,
            "grids": [{
                "id": "grid_TEST_20240101_0001",
                "symbol": "TEST",
                "status": "INVALID_STATUS",
                "regime": "BULL",
                "created_at": "2024-01-01",
                "center_price": 100.0,
                "atr": 2.0,
                "spacing": 2.0,
                "levels": [],
            }],
        }
        state_path.write_text(json.dumps(bad_data))

        engine = GridEngine(data_dir=tmp_data_dir)
        with pytest.raises(ValueError):
            engine.load_state()

    def test_load_state_validates_level_status(self, tmp_data_dir: str):
        """Invalid level status should raise ValueError."""
        os.makedirs(tmp_data_dir, exist_ok=True)
        state_path = Path(tmp_data_dir) / "grids_state.json"
        bad_data = {
            "version": 1,
            "grids": [{
                "id": "grid_TEST_20240101_0001",
                "symbol": "TEST",
                "status": "active",
                "regime": "BULL",
                "created_at": "2024-01-01",
                "center_price": 100.0,
                "atr": 2.0,
                "spacing": 2.0,
                "levels": [{
                    "level": 1,
                    "buy_price": 98.0,
                    "sell_price": 102.0,
                    "stop_price": 95.0,
                    "status": "BAD_STATUS",
                    "quantity": 10,
                }],
            }],
        }
        state_path.write_text(json.dumps(bad_data))

        engine = GridEngine(data_dir=tmp_data_dir)
        with pytest.raises(ValueError):
            engine.load_state()

    def test_load_state_validates_missing_fields(self, tmp_data_dir: str):
        """Missing required grid fields should raise ValueError."""
        os.makedirs(tmp_data_dir, exist_ok=True)
        state_path = Path(tmp_data_dir) / "grids_state.json"
        bad_data = {
            "version": 1,
            "grids": [{"id": "test"}],  # Missing most fields
        }
        state_path.write_text(json.dumps(bad_data))

        engine = GridEngine(data_dir=tmp_data_dir)
        with pytest.raises(ValueError, match="campos em falta"):
            engine.load_state()

    def test_save_load_preserves_level_state(self, engine: GridEngine, tmp_data_dir: str):
        """Verify that level status changes survive save/load cycle."""
        grid = engine.create_grid(
            symbol="AAPL", center_price=100.0, atr=2.0,
            regime="BULL", num_levels=3, base_quantity=10,
            confidence="ALTO", size_multiplier=1.0,
        )
        engine.on_level_bought(grid, 1, grid.levels[0].buy_price, "2024-01-01T12:00:00")
        engine.on_level_sold(grid, 1, grid.levels[0].sell_price, "2024-01-01T14:00:00")
        engine.save_state()

        engine2 = GridEngine(data_dir=tmp_data_dir)
        engine2.load_state()

        loaded_grid = engine2.grids[0]
        assert loaded_grid.levels[0].status == "sold"
        assert loaded_grid.levels[0].pnl == pytest.approx(
            (grid.levels[0].sell_price - grid.levels[0].buy_price) * grid.levels[0].quantity
        )


# ===================================================================
# Tests: generate_grid_id
# ===================================================================


class TestGenerateGridId:
    def test_grid_id_format(self, engine: GridEngine):
        grid_id = engine.generate_grid_id("AAPL")
        parts = grid_id.split("_")
        assert parts[0] == "grid"
        assert parts[1] == "AAPL"
        # Date part should be 8 digits
        assert len(parts[2]) == 8
        assert parts[2].isdigit()
        # Sequence part should be zero-padded 4 digits
        assert len(parts[3]) == 4
        assert parts[3].isdigit()

    def test_grid_id_sequence_increments(self, engine: GridEngine):
        id1 = engine.generate_grid_id("AAPL")
        id2 = engine.generate_grid_id("AAPL")
        seq1 = int(id1.split("_")[-1])
        seq2 = int(id2.split("_")[-1])
        assert seq2 == seq1 + 1

    def test_grid_id_symbol_cleaned(self, engine: GridEngine):
        grid_id = engine.generate_grid_id("EUR/USD")
        assert "EURUSD" in grid_id

    def test_grid_id_spaces_removed(self, engine: GridEngine):
        grid_id = engine.generate_grid_id("N K E")
        assert "NKE" in grid_id


# ===================================================================
# Tests: zero averaging down (stopped levels NOT reopened)
# ===================================================================


class TestZeroAveragingDown:
    def test_stopped_level_stays_stopped_after_close(
        self, engine: GridEngine, sample_grid: Grid
    ):
        """Once a level is stopped, it should not be reopened."""
        engine.on_level_bought(sample_grid, 1, sample_grid.levels[0].buy_price, "t1")
        engine.on_level_stopped(sample_grid, 1, sample_grid.levels[0].stop_price, "t2")

        # Verify the level is stopped
        lv = sample_grid.levels[0]
        assert lv.status == "stopped"

        # The level should NOT be changed to pending/bought again
        # This is enforced by convention: on_level_stopped is terminal
        # Calling close_grid should not change stopped status
        engine.close_grid(sample_grid)
        assert lv.status == "stopped"

    def test_recenter_preserves_stopped_levels(self, engine: GridEngine, sample_grid: Grid):
        """Recentering should keep stopped levels in their current state."""
        engine.on_level_bought(sample_grid, 1, sample_grid.levels[0].buy_price, "t1")
        engine.on_level_stopped(sample_grid, 1, sample_grid.levels[0].stop_price, "t2")

        # Recenter the grid
        engine.recenter_grid(sample_grid, new_center=95.0, atr=2.0)

        # The stopped level should still be stopped
        stopped_levels = [lv for lv in sample_grid.levels if lv.status == "stopped"]
        assert len(stopped_levels) == 1
        assert stopped_levels[0].level == 1


# ===================================================================
# Tests: GridLevel and Grid validation
# ===================================================================


class TestDataclassValidation:
    def test_grid_level_invalid_status_raises(self):
        with pytest.raises(ValueError, match="Estado de nivel invalido"):
            GridLevel(
                level=1, buy_price=98.0, sell_price=102.0,
                stop_price=95.0, status="INVALID", quantity=10,
            )

    def test_grid_invalid_status_raises(self):
        with pytest.raises(ValueError, match="Estado de grid invalido"):
            Grid(
                id="test", symbol="AAPL", status="INVALID",
                regime="BULL", created_at="2024-01-01",
                center_price=100.0, atr=2.0, spacing=2.0, levels=[],
            )

    def test_grid_level_valid_statuses(self):
        for status in _VALID_LEVEL_STATUSES:
            lv = GridLevel(
                level=1, buy_price=98.0, sell_price=102.0,
                stop_price=95.0, status=status, quantity=10,
            )
            assert lv.status == status


# ===================================================================
# Tests: get_active_grids, get_grid_by_id
# ===================================================================


class TestQueryMethods:
    def test_get_active_grids(self, engine: GridEngine):
        g1 = engine.create_grid(
            symbol="AAPL", center_price=100.0, atr=2.0,
            regime="BULL", num_levels=3, base_quantity=10,
            confidence="ALTO", size_multiplier=1.0,
        )
        g2 = engine.create_grid(
            symbol="MSFT", center_price=200.0, atr=3.0,
            regime="BEAR", num_levels=3, base_quantity=5,
            confidence="MEDIO", size_multiplier=1.0,
        )
        engine.close_grid(g1)

        active = engine.get_active_grids()
        assert len(active) == 1
        assert active[0].symbol == "MSFT"

    def test_get_grid_by_id(self, engine: GridEngine, sample_grid: Grid):
        found = engine.get_grid_by_id(sample_grid.id)
        assert found is not None
        assert found.id == sample_grid.id

    def test_get_grid_by_id_not_found(self, engine: GridEngine):
        found = engine.get_grid_by_id("nonexistent_id")
        assert found is None

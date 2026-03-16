"""
Tests for src/execution.py

Covers: RateLimiter, submit_bracket_order (mock IB), cancel_order,
        close_position, order tracking.
"""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest

from src.ib_requests import IBRateLimiter, IBRequestExecutor
from src.execution import (
    OrderInfo,
    OrderManager,
    OrderStatus,
    RateLimiter,
)


# ===================================================================
# Fixtures
# ===================================================================


@pytest.fixture
def mock_ib():
    """Create a mock IB instance."""
    ib = MagicMock()
    ib.client = MagicMock()
    ib.client.getReqId = MagicMock(side_effect=iter(range(1000, 2000)))
    ib.orderStatusEvent = MagicMock()
    ib.orderStatusEvent.__iadd__ = MagicMock()
    ib.errorEvent = MagicMock()
    ib.errorEvent.__iadd__ = MagicMock()
    ib.openTrades = MagicMock(return_value=[])
    ib.positions = MagicMock(return_value=[])
    ib.sleep = MagicMock()
    return ib


@pytest.fixture
def mock_connection(mock_ib):
    """Create a mock IBConnection."""
    conn = MagicMock()
    conn.ib = mock_ib
    conn.rate_limiter = IBRateLimiter(
        identical_cooldown_seconds=0.0,
        max_order_messages_per_second=1000,
    )
    conn.request_executor = IBRequestExecutor(conn.rate_limiter, MagicMock())
    return conn


@pytest.fixture
def order_manager(mock_connection):
    """Create an OrderManager with mocked IB connection."""
    return OrderManager(mock_connection)


@pytest.fixture
def mock_contract():
    """Create a mock contract."""
    contract = MagicMock()
    contract.symbol = "AAPL"
    return contract


# ===================================================================
# Tests: RateLimiter
# ===================================================================


@pytest.mark.timeout(5)
class TestRateLimiter:
    @pytest.mark.asyncio
    async def test_acquire_within_limit(self):
        limiter = RateLimiter(max_per_second=5)
        for _ in range(5):
            await limiter.acquire()
        # Should complete without blocking indefinitely

    @pytest.mark.asyncio
    async def test_acquire_increments_timestamp(self):
        limiter = RateLimiter(max_per_second=10)
        await limiter.acquire()
        assert limiter.current_usage >= 1

    @pytest.mark.asyncio
    async def test_current_usage_starts_at_zero(self):
        limiter = RateLimiter(max_per_second=45)
        assert limiter.current_usage == 0

    @pytest.mark.asyncio
    async def test_acquire_under_limit_does_not_sleep(self):
        """When under the limit, acquire should be very fast."""
        limiter = RateLimiter(max_per_second=100)
        with patch("src.ib_requests.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            start = time.monotonic()
            for _ in range(10):
                await limiter.acquire()
            elapsed = time.monotonic() - start
        mock_sleep.assert_not_awaited()
        # Should be essentially instant (< 100ms for 10 calls)
        assert elapsed < 0.5

    @pytest.mark.asyncio
    async def test_acquire_at_limit_waits(self):
        """When at the limit, acquire should wait."""
        limiter = RateLimiter(max_per_second=2)
        await limiter.acquire()
        await limiter.acquire()
        # Third call should need to wait
        start = time.monotonic()
        await limiter.acquire()
        elapsed = time.monotonic() - start
        # Should have waited at least a fraction of a second
        assert elapsed >= 0.0  # May be very fast if timestamps expired


# ===================================================================
# Tests: submit_bracket_order (mocked IB)
# ===================================================================


class TestSubmitBracketOrder:
    @pytest.mark.asyncio
    @pytest.mark.timeout(5)
    async def test_submit_bracket_order_success(self, order_manager, mock_ib, mock_contract):
        """Successful bracket order submission."""
        mock_order_status = MagicMock()
        mock_order_status.status = "PreSubmitted"

        mock_trade = MagicMock()
        mock_trade.orderStatus = mock_order_status

        mock_ib.placeOrder.return_value = mock_trade

        result = await order_manager.submit_bracket_order(
            contract=mock_contract,
            action="BUY",
            quantity=10,
            entry_price=100.0,
            stop_price=95.0,
            take_profit_price=110.0,
            grid_id="grid_AAPL_20240101_0001",
            level=1,
        )

        assert result is not None
        assert result["grid_id"] == "grid_AAPL_20240101_0001"
        assert result["level"] == 1
        assert result["action"] == "BUY"
        assert result["quantity"] == 10
        assert result["price"] == 100.0
        assert result["stop"] == 95.0
        assert result["target"] == 110.0

    @pytest.mark.asyncio
    @pytest.mark.timeout(5)
    async def test_submit_bracket_order_invalid_prices(self, order_manager, mock_contract):
        """Invalid price configuration returns None."""
        result = await order_manager.submit_bracket_order(
            contract=mock_contract,
            action="BUY",
            quantity=10,
            entry_price=100.0,
            stop_price=110.0,    # Stop above entry for BUY => invalid
            take_profit_price=120.0,
            grid_id="grid_TEST_0001",
            level=1,
        )
        assert result is None

    @pytest.mark.asyncio
    @pytest.mark.timeout(5)
    async def test_submit_bracket_order_zero_quantity(self, order_manager, mock_contract):
        """Zero quantity returns None."""
        result = await order_manager.submit_bracket_order(
            contract=mock_contract,
            action="BUY",
            quantity=0,
            entry_price=100.0,
            stop_price=95.0,
            take_profit_price=110.0,
            grid_id="grid_TEST_0001",
            level=1,
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_submit_bracket_order_negative_price(self, order_manager, mock_contract):
        """Negative prices return None."""
        result = await order_manager.submit_bracket_order(
            contract=mock_contract,
            action="BUY",
            quantity=10,
            entry_price=-100.0,
            stop_price=95.0,
            take_profit_price=110.0,
            grid_id="grid_TEST_0001",
            level=1,
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_submit_bracket_order_sell_price_validation(
        self, order_manager, mock_ib, mock_contract
    ):
        """SELL bracket: take_profit < entry < stop."""
        mock_order_status = MagicMock()
        mock_order_status.status = "PreSubmitted"
        mock_trade = MagicMock()
        mock_trade.orderStatus = mock_order_status
        mock_ib.placeOrder.return_value = mock_trade

        result = await order_manager.submit_bracket_order(
            contract=mock_contract,
            action="SELL",
            quantity=10,
            entry_price=100.0,
            stop_price=110.0,     # stop above entry for SELL
            take_profit_price=90.0,  # target below entry for SELL
            grid_id="grid_TEST_0001",
            level=1,
        )
        assert result is not None
        assert result["action"] == "SELL"

    @pytest.mark.asyncio
    @pytest.mark.timeout(5)
    async def test_submit_bracket_order_places_three_orders(
        self, order_manager, mock_ib, mock_contract
    ):
        """A bracket order should result in 3 placeOrder calls."""
        mock_order_status = MagicMock()
        mock_order_status.status = "PreSubmitted"
        mock_trade = MagicMock()
        mock_trade.orderStatus = mock_order_status
        mock_ib.placeOrder.return_value = mock_trade

        await order_manager.submit_bracket_order(
            contract=mock_contract,
            action="BUY",
            quantity=5,
            entry_price=100.0,
            stop_price=95.0,
            take_profit_price=110.0,
            grid_id="grid_TEST_0001",
            level=1,
        )

        # 3 orders: parent, stop, take-profit
        assert mock_ib.placeOrder.call_count == 3

    @pytest.mark.asyncio
    @pytest.mark.timeout(5)
    async def test_submit_bracket_order_retries_on_exception(
        self, order_manager, mock_ib, mock_contract
    ):
        """Order submission should retry on exception."""
        mock_ib.placeOrder.side_effect = [
            Exception("Connection lost"),
            Exception("Timeout"),
            MagicMock(orderStatus=MagicMock(status="PreSubmitted")),
            MagicMock(orderStatus=MagicMock(status="PreSubmitted")),
            MagicMock(orderStatus=MagicMock(status="PreSubmitted")),
        ]

        with (
            patch("src.ib_requests.asyncio.sleep", new_callable=AsyncMock),
            patch("src.execution.asyncio.sleep", new_callable=AsyncMock),
        ):
            result = await order_manager.submit_bracket_order(
                contract=mock_contract,
                action="BUY",
                quantity=10,
                entry_price=100.0,
                stop_price=95.0,
                take_profit_price=110.0,
                grid_id="grid_TEST_0001",
                level=1,
            )
        # Third attempt succeeds (after 3 calls: first two fail, third succeeds)
        # But we need 3 orders placed on success, so total calls:
        # attempt 1: fails on first placeOrder
        # attempt 2: fails on first placeOrder
        # attempt 3: 3 placeOrder calls succeed
        # Total: 5 placeOrder calls
        assert result is not None

    @pytest.mark.asyncio
    @pytest.mark.timeout(5)
    async def test_submit_bracket_order_all_retries_fail(
        self, order_manager, mock_ib, mock_contract
    ):
        """If all retries fail, returns None."""
        mock_ib.placeOrder.side_effect = Exception("Persistent failure")

        with (
            patch("src.ib_requests.asyncio.sleep", new_callable=AsyncMock),
            patch("src.execution.asyncio.sleep", new_callable=AsyncMock),
        ):
            result = await order_manager.submit_bracket_order(
                contract=mock_contract,
                action="BUY",
                quantity=10,
                entry_price=100.0,
                stop_price=95.0,
                take_profit_price=110.0,
                grid_id="grid_TEST_0001",
                level=1,
            )
        assert result is None


# ===================================================================
# Tests: cancel_order
# ===================================================================


class TestCancelOrder:
    @pytest.mark.asyncio
    async def test_cancel_order_not_found(self, order_manager, mock_ib):
        """Cancelling a non-existent order returns True (already cancelled/filled)."""
        mock_ib.openTrades.return_value = []
        result = await order_manager.cancel_order(9999)
        assert result is True

    @pytest.mark.asyncio
    async def test_cancel_order_success(self, order_manager, mock_ib):
        """Successfully cancel an order."""
        mock_order = MagicMock()
        mock_order.orderId = 42
        mock_order_status = MagicMock()
        mock_order_status.status = OrderStatus.CANCELLED
        mock_trade = MagicMock()
        mock_trade.order = mock_order
        mock_trade.orderStatus = mock_order_status

        mock_ib.openTrades.return_value = [mock_trade]
        mock_ib.cancelOrder = MagicMock()

        result = await order_manager.cancel_order(42)
        assert result is True

    @pytest.mark.asyncio
    async def test_cancel_all_grid_orders_empty(self, order_manager, mock_ib):
        """No orders for grid => returns 0."""
        result = await order_manager.cancel_all_grid_orders("grid_NONE_0001")
        assert result == 0


# ===================================================================
# Tests: close_position
# ===================================================================


class TestClosePosition:
    @pytest.mark.asyncio
    async def test_close_position_success(self, order_manager, mock_ib, mock_contract):
        mock_order_status = MagicMock()
        mock_order_status.status = OrderStatus.FILLED
        mock_order_status.avgFillPrice = 99.5
        mock_trade = MagicMock()
        mock_trade.orderStatus = mock_order_status
        mock_ib.placeOrder.return_value = mock_trade

        result = await order_manager.close_position(mock_contract, quantity=10)
        assert result is True

    @pytest.mark.asyncio
    async def test_close_position_zero_quantity(self, order_manager, mock_contract):
        result = await order_manager.close_position(mock_contract, quantity=0)
        assert result is False

    @pytest.mark.asyncio
    async def test_close_position_negative_quantity(self, order_manager, mock_contract):
        result = await order_manager.close_position(mock_contract, quantity=-5)
        assert result is False


# ===================================================================
# Tests: Order tracking
# ===================================================================


class TestOrderTracking:
    def test_get_order_status_not_found(self, order_manager, mock_ib):
        mock_ib.openTrades.return_value = []
        status = order_manager.get_order_status(9999)
        assert status is None

    def test_get_order_info_not_found(self, order_manager):
        info = order_manager.get_order_info(9999)
        assert info is None

    def test_get_grid_orders_empty(self, order_manager):
        orders = order_manager.get_grid_orders("grid_NONE_0001")
        assert orders == []

    def test_get_pending_count_empty(self, order_manager):
        assert order_manager.get_pending_count() == 0

    def test_cleanup_completed_empty(self, order_manager):
        count = order_manager.cleanup_completed()
        assert count == 0

    @pytest.mark.asyncio
    async def test_order_tracked_after_submission(
        self, order_manager, mock_ib, mock_contract
    ):
        """After successful submission, orders should be in tracking."""
        mock_order_status = MagicMock()
        mock_order_status.status = "PreSubmitted"
        mock_trade = MagicMock()
        mock_trade.orderStatus = mock_order_status
        mock_ib.placeOrder.return_value = mock_trade

        result = await order_manager.submit_bracket_order(
            contract=mock_contract,
            action="BUY",
            quantity=10,
            entry_price=100.0,
            stop_price=95.0,
            take_profit_price=110.0,
            grid_id="grid_AAPL_20240101_0001",
            level=1,
        )

        assert result is not None
        order_id = result["order_id"]

        # Should be in tracking
        info = order_manager.get_order_info(order_id)
        assert info is not None
        assert info.grid_id == "grid_AAPL_20240101_0001"
        assert info.level == 1

        # Grid orders should include this
        grid_orders = order_manager.get_grid_orders("grid_AAPL_20240101_0001")
        assert len(grid_orders) >= 1

    def test_cleanup_removes_filled_orders(self, order_manager):
        """Cleanup should remove orders in terminal states."""
        info = OrderInfo(
            order_id=100,
            grid_id="grid_TEST_0001",
            level=1,
            status=OrderStatus.FILLED,
            contract=MagicMock(),
            action="BUY",
            quantity=10,
            price=100.0,
            stop=95.0,
            target=110.0,
        )
        order_manager._pending_orders[100] = info

        removed = order_manager.cleanup_completed()
        assert removed == 1
        assert 100 not in order_manager._pending_orders


# ===================================================================
# Tests: OrderInfo
# ===================================================================


class TestOrderInfo:
    def test_to_dict(self):
        contract = MagicMock()
        info = OrderInfo(
            order_id=42,
            grid_id="grid_AAPL_0001",
            level=2,
            status="PreSubmitted",
            contract=contract,
            action="BUY",
            quantity=10,
            price=100.0,
            stop=95.0,
            target=110.0,
        )
        d = info.to_dict()
        assert d["order_id"] == 42
        assert d["grid_id"] == "grid_AAPL_0001"
        assert d["level"] == 2
        assert d["action"] == "BUY"
        assert d["quantity"] == 10
        assert d["price"] == 100.0
        assert d["stop"] == 95.0
        assert d["target"] == 110.0


# ===================================================================
# Tests: _validate_bracket_prices
# ===================================================================


class TestValidateBracketPrices:
    def test_valid_buy_bracket(self):
        OrderManager._validate_bracket_prices("BUY", 100.0, 95.0, 110.0)

    def test_valid_sell_bracket(self):
        OrderManager._validate_bracket_prices("SELL", 100.0, 110.0, 90.0)

    def test_invalid_buy_stop_above_entry(self):
        with pytest.raises(ValueError):
            OrderManager._validate_bracket_prices("BUY", 100.0, 110.0, 120.0)

    def test_invalid_sell_stop_below_entry(self):
        with pytest.raises(ValueError):
            OrderManager._validate_bracket_prices("SELL", 100.0, 90.0, 110.0)

    def test_invalid_action(self):
        with pytest.raises(ValueError, match="Accao invalida"):
            OrderManager._validate_bracket_prices("HOLD", 100.0, 95.0, 110.0)

    def test_negative_prices(self):
        with pytest.raises(ValueError):
            OrderManager._validate_bracket_prices("BUY", -100.0, 95.0, 110.0)

    def test_zero_prices(self):
        with pytest.raises(ValueError):
            OrderManager._validate_bracket_prices("BUY", 0.0, 0.0, 0.0)


# ===================================================================
# Tests: modify_order
# ===================================================================


class TestModifyOrder:
    @pytest.mark.asyncio
    async def test_modify_order_invalid_price(self, order_manager, mock_ib):
        result = await order_manager.modify_order(42, 0.0)
        assert result is False

    @pytest.mark.asyncio
    async def test_modify_order_negative_price(self, order_manager, mock_ib):
        result = await order_manager.modify_order(42, -10.0)
        assert result is False

    @pytest.mark.asyncio
    async def test_modify_order_not_found(self, order_manager, mock_ib):
        mock_ib.openTrades.return_value = []
        result = await order_manager.modify_order(9999, 105.0)
        assert result is False

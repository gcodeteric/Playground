"""
Tests for src/data_feed.py

Covers: IBConnection init (mocked), contract creation (Stock, Forex, Futures, CFD),
        get_market_data returns all indicators. Uses unittest.mock for IB connection.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from src.data_feed import (
    DataFeed,
    IBConnection,
    _TTLCache,
    _valid_price,
    compute_atr,
    compute_bollinger_bands,
    compute_rsi,
    compute_sma,
    get_warmup_missing_rules,
    validate_warmup,
)
from src.ib_requests import IBRateLimiter


# ===================================================================
# Fixtures
# ===================================================================


@pytest.fixture
def mock_ib():
    """Create a mock IB instance."""
    ib = MagicMock()
    ib.isConnected.return_value = True
    ib.connectAsync = AsyncMock(return_value=None)
    ib.disconnectedEvent = MagicMock()
    ib.disconnectedEvent.__iadd__ = MagicMock(return_value=ib.disconnectedEvent)
    return ib


@pytest.fixture
def mock_connection(mock_ib):
    """Create a mock IBConnection with a mocked IB instance."""
    with patch("src.data_feed.IB", return_value=mock_ib):
        conn = IBConnection(host="127.0.0.1", port=4002, client_id=1)
    conn.ib = mock_ib
    conn._connected = True
    return conn


@pytest.fixture
def data_feed(mock_connection):
    """Create a DataFeed with mocked connection."""
    return DataFeed(connection=mock_connection)


@pytest.fixture
def sample_bars_df():
    """Create a sample DataFrame with enough data for all indicators."""
    n = 250
    np.random.seed(42)
    base = 100.0
    closes = [base + np.random.randn() * 2 for _ in range(n)]
    highs = [c + abs(np.random.randn()) for c in closes]
    lows = [c - abs(np.random.randn()) for c in closes]
    opens = [(h + l) / 2 for h, l in zip(highs, lows)]
    volumes = [1000 + abs(np.random.randn()) * 500 for _ in range(n)]
    dates = pd.date_range("2023-01-01", periods=n, freq="B")

    df = pd.DataFrame({
        "date": dates,
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": volumes,
    })
    return df


# ===================================================================
# Tests: IBConnection init
# ===================================================================


class TestIBConnectionInit:
    def test_init_default_params(self, mock_ib):
        with patch("src.data_feed.IB", return_value=mock_ib):
            conn = IBConnection()
        assert conn.host == "127.0.0.1"
        assert conn.port == 7497
        assert conn.client_id == 1

    def test_init_custom_params(self, mock_ib):
        with patch("src.data_feed.IB", return_value=mock_ib):
            conn = IBConnection(host="192.168.1.100", port=7497, client_id=5)
        assert conn.host == "192.168.1.100"
        assert conn.port == 7497
        assert conn.client_id == 5

    def test_init_creates_ib_instance(self, mock_ib):
        with patch("src.data_feed.IB", return_value=mock_ib) as mock_ib_cls:
            conn = IBConnection()
            mock_ib_cls.assert_called_once()

    def test_initial_state_not_connected(self, mock_ib):
        with patch("src.data_feed.IB", return_value=mock_ib):
            conn = IBConnection()
        assert conn._connected is False

    def test_is_connected_property(self, mock_connection):
        mock_connection.ib.isConnected.return_value = True
        mock_connection._connected = True
        assert mock_connection.is_connected is True

    def test_is_not_connected_property(self, mock_connection):
        mock_connection.ib.isConnected.return_value = False
        assert mock_connection.is_connected is False

    def test_on_error_records_actionable_connection_event(self, mock_ib):
        with patch("src.data_feed.IB", return_value=mock_ib):
            conn = IBConnection()

        conn._on_error(
            req_id=1,
            error_code=1100,
            error_string="Connectivity between IB and Trader Workstation has been lost",
            contract=None,
        )

        events = conn.operational_events_since(0.0)
        assert len(events) == 1
        assert events[0].action == "entry_halt"
        assert events[0].halt_reason == "ib_connection_lost"
        assert conn._connection_state == "DISCONNECTED"

    @pytest.mark.asyncio
    async def test_on_error_dispatches_connection_error_callback(self, mock_ib):
        with patch("src.data_feed.IB", return_value=mock_ib):
            conn = IBConnection()

        callback = AsyncMock()
        conn.set_error_callback(callback)

        conn._on_error(
            req_id=2,
            error_code=1100,
            error_string="Connectivity between IB and Trader Workstation has been lost",
            contract=None,
        )
        await asyncio.sleep(0)

        callback.assert_awaited_once()

    def test_on_error_records_market_data_permission_as_symbol_skip(self, mock_ib):
        with patch("src.data_feed.IB", return_value=mock_ib):
            conn = IBConnection()

        conn._on_error(
            req_id=3,
            error_code=354,
            error_string="Requested market data is not subscribed",
            contract=None,
        )

        events = conn.operational_events_since(0.0)
        assert len(events) == 1
        assert events[0].action == "symbol_skip"
        assert events[0].scope == "request"


# ===================================================================
# Tests: Contract creation
# ===================================================================


class TestContractCreation:
    def test_create_stock_contract(self, data_feed):
        with patch("src.data_feed.Stock") as MockStock:
            MockStock.return_value = MagicMock(symbol="AAPL")
            contract = data_feed.create_stock_contract("AAPL", "SMART", "USD")
            MockStock.assert_called_once_with("AAPL", "SMART", "USD")

    def test_create_stock_contract_defaults(self, data_feed):
        with patch("src.data_feed.Stock") as MockStock:
            MockStock.return_value = MagicMock(symbol="MSFT")
            contract = data_feed.create_stock_contract("MSFT")
            MockStock.assert_called_once_with("MSFT", "SMART", "USD")

    def test_create_forex_contract(self, data_feed):
        with patch("src.data_feed.Forex") as MockForex:
            MockForex.return_value = MagicMock(symbol="EURUSD")
            contract = data_feed.create_forex_contract("EURUSD")
            MockForex.assert_called_once_with("EURUSD")

    def test_create_futures_contract_with_expiry(self, data_feed):
        with patch("src.data_feed.Future") as MockFuture:
            MockFuture.return_value = MagicMock(symbol="MES")
            contract = data_feed.create_futures_contract("MES", "CME", "202412")
            MockFuture.assert_called_once_with("MES", "202412", "CME")

    def test_create_futures_contract_without_expiry(self, data_feed):
        with patch("src.data_feed.Future") as MockFuture:
            MockFuture.return_value = MagicMock(symbol="MES")
            contract = data_feed.create_futures_contract("MES", "CME")
            MockFuture.assert_called_once_with(symbol="MES", exchange="CME")

    def test_create_cfd_contract(self, data_feed):
        with patch("src.data_feed.CFD") as MockCFD:
            MockCFD.return_value = MagicMock(symbol="IBDE30")
            contract = data_feed.create_cfd_contract("IBDE30")
            MockCFD.assert_called_once_with("IBDE30")


# ===================================================================
# Tests: get_market_data
# ===================================================================


class TestGetMarketData:
    def test_returns_all_indicator_keys(self, data_feed, sample_bars_df):
        contract = MagicMock()
        contract.symbol = "AAPL"
        result = data_feed.get_market_data(contract, sample_bars_df)

        expected_keys = {
            "sma25", "sma50", "sma200", "rsi14", "atr14",
            "bb_upper", "bb_middle", "bb_lower",
            "volume_avg_20", "last_close", "current_price", "atr_avg_60",
        }
        assert set(result.keys()) == expected_keys

    def test_indicators_are_not_none_with_sufficient_data(
        self, data_feed, sample_bars_df
    ):
        contract = MagicMock()
        contract.symbol = "AAPL"
        result = data_feed.get_market_data(contract, sample_bars_df)

        for key in ["sma25", "sma50", "sma200", "rsi14", "atr14",
                     "bb_upper", "bb_middle", "bb_lower",
                     "volume_avg_20", "last_close", "atr_avg_60"]:
            assert result[key] is not None, f"{key} should not be None"
        assert result["current_price"] is None

    def test_empty_dataframe_returns_all_none(self, data_feed):
        contract = MagicMock()
        contract.symbol = "AAPL"
        empty_df = pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume"])
        result = data_feed.get_market_data(contract, empty_df)

        for key in result:
            assert result[key] is None

    def test_last_close_is_last_bar_close(self, data_feed, sample_bars_df):
        contract = MagicMock()
        contract.symbol = "AAPL"
        result = data_feed.get_market_data(contract, sample_bars_df)
        expected_price = round(float(sample_bars_df["close"].iloc[-1]), 6)
        assert result["last_close"] == pytest.approx(expected_price, abs=1e-5)
        assert result["current_price"] is None

    @pytest.mark.asyncio
    async def test_get_market_data_live_uses_live_snapshot(
        self,
        data_feed,
        sample_bars_df,
    ):
        contract = MagicMock()
        contract.symbol = "AAPL"
        data_feed.get_current_price_details = AsyncMock(
            return_value={"price": 123.4567, "source": "last", "fresh": True},
        )

        result = await data_feed.get_market_data_live(contract, sample_bars_df)

        assert result["current_price"] == pytest.approx(123.4567, abs=1e-5)
        assert result["price_source"] == "last"
        assert result["price_fresh"] is True
        assert result["last_close"] == pytest.approx(
            float(sample_bars_df["close"].iloc[-1]),
            abs=1e-5,
        )

    @pytest.mark.asyncio
    async def test_get_market_data_live_falls_back_to_last_close(
        self,
        data_feed,
        sample_bars_df,
    ):
        contract = MagicMock()
        contract.symbol = "AAPL"
        data_feed.get_current_price_details = AsyncMock(
            return_value={"price": None, "source": None, "fresh": False},
        )

        result = await data_feed.get_market_data_live(contract, sample_bars_df)

        expected_price = round(float(sample_bars_df["close"].iloc[-1]), 6)
        assert result["current_price"] == pytest.approx(expected_price, abs=1e-5)
        assert result["price_source"] == "last_close"
        assert result["price_fresh"] is False
        assert result["last_close"] == pytest.approx(expected_price, abs=1e-5)

    def test_sma_values_are_reasonable(self, data_feed, sample_bars_df):
        contract = MagicMock()
        contract.symbol = "TEST"
        result = data_feed.get_market_data(contract, sample_bars_df)

        # SMAs should be around the base price (100)
        for key in ["sma25", "sma50", "sma200"]:
            assert 90 < result[key] < 110

    def test_rsi_within_bounds(self, data_feed, sample_bars_df):
        contract = MagicMock()
        contract.symbol = "TEST"
        result = data_feed.get_market_data(contract, sample_bars_df)
        assert 0 <= result["rsi14"] <= 100

    def test_bollinger_band_ordering(self, data_feed, sample_bars_df):
        contract = MagicMock()
        contract.symbol = "TEST"
        result = data_feed.get_market_data(contract, sample_bars_df)
        assert result["bb_lower"] < result["bb_middle"] < result["bb_upper"]

    def test_insufficient_data_returns_none_for_sma200(self, data_feed):
        """DataFrame with only 50 bars: SMA200 should be None."""
        n = 50
        df = pd.DataFrame({
            "date": pd.date_range("2023-01-01", periods=n, freq="B"),
            "open": [100.0] * n,
            "high": [101.0] * n,
            "low": [99.0] * n,
            "close": [100.0] * n,
            "volume": [1000.0] * n,
        })
        contract = MagicMock()
        contract.symbol = "TEST"
        result = data_feed.get_market_data(contract, df)
        assert result["sma200"] is None
        assert result["sma25"] is not None


# ===================================================================
# Tests: get_current_price / get_current_volume
# ===================================================================


class TestCurrentSnapshotFallbacks:
    def test_contract_cache_key_distinguishes_material_contract_fields(self, data_feed):
        stock_a = SimpleNamespace(
            secType="STK",
            symbol="AAPL",
            exchange="SMART",
            primaryExchange="NASDAQ",
            currency="USD",
            lastTradeDateOrContractMonth="",
            localSymbol="AAPL",
        )
        future_a = SimpleNamespace(
            secType="FUT",
            symbol="MES",
            exchange="CME",
            primaryExchange="CME",
            currency="USD",
            lastTradeDateOrContractMonth="202406",
            localSymbol="MESM4",
        )
        future_b = SimpleNamespace(
            secType="FUT",
            symbol="MES",
            exchange="CME",
            primaryExchange="CME",
            currency="USD",
            lastTradeDateOrContractMonth="202409",
            localSymbol="MESU4",
        )

        assert data_feed._contract_cache_key(stock_a) != data_feed._contract_cache_key(future_a)
        assert data_feed._contract_cache_key(future_a) != data_feed._contract_cache_key(future_b)

    @pytest.mark.asyncio
    async def test_get_current_price_prefers_midpoint_over_close(
        self,
        data_feed,
        mock_connection,
        mock_ib,
    ):
        contract = MagicMock()
        contract.symbol = "AAPL"
        mock_connection.ensure_connected = AsyncMock(return_value=True)
        mock_ib.reqMktData.return_value = SimpleNamespace(
            last=None,
            close=99.0,
            bid=100.0,
            ask=101.0,
        )

        result = await data_feed.get_current_price(contract)

        assert result == pytest.approx(100.5, abs=1e-5)

    @pytest.mark.asyncio
    async def test_get_current_price_uses_async_yfinance_when_ib_disconnected(
        self,
        data_feed,
        mock_connection,
    ):
        contract = MagicMock()
        contract.symbol = "AAPL"
        mock_connection.ensure_connected = AsyncMock(return_value=False)
        data_feed.get_price_yfinance = AsyncMock(return_value=123.45)

        result = await data_feed.get_current_price(contract)

        assert result == pytest.approx(123.45, abs=1e-5)
        data_feed.get_price_yfinance.assert_awaited_once_with("AAPL")

    @pytest.mark.asyncio
    async def test_get_current_price_details_accepts_latest_yfinance_close_as_fresh(
        self,
        data_feed,
        mock_connection,
    ):
        contract = SimpleNamespace(
            secType="STK",
            symbol="AAPL",
            exchange="SMART",
            primaryExchange="NASDAQ",
            currency="USD",
            lastTradeDateOrContractMonth="",
        )
        latest_close = pd.Timestamp.now(tz="UTC").normalize() - pd.offsets.BDay(1)
        mock_connection.ensure_connected = AsyncMock(return_value=False)

        with patch(
            "src.data_feed.yf.download",
            return_value=pd.DataFrame(
                {"Close": [123.45]},
                index=pd.DatetimeIndex([latest_close]),
            ),
        ):
            result = await data_feed.get_current_price_details(contract)

        assert result["price"] == pytest.approx(123.45, abs=1e-5)
        assert result["source"] == "yfinance"
        assert result["fresh"] is True

    @pytest.mark.asyncio
    async def test_get_current_volume_uses_async_yfinance_when_ib_disconnected(
        self,
        data_feed,
        mock_connection,
    ):
        contract = MagicMock()
        contract.symbol = "AAPL"
        mock_connection.ensure_connected = AsyncMock(return_value=False)
        data_feed.get_volume_yfinance = AsyncMock(return_value=999_999.0)

        result = await data_feed.get_current_volume(contract)

        assert result == pytest.approx(999_999.0, abs=1e-5)
        data_feed.get_volume_yfinance.assert_awaited_once_with("AAPL")


# ===================================================================
# Tests: TTLCache
# ===================================================================


class TestTTLCache:
    def test_set_and_get(self):
        cache = _TTLCache(ttl=10.0)
        cache.set("key1", "value1")
        assert cache.get("key1") == "value1"

    def test_get_nonexistent_returns_none(self):
        cache = _TTLCache(ttl=10.0)
        assert cache.get("nonexistent") is None

    def test_invalidate(self):
        cache = _TTLCache(ttl=10.0)
        cache.set("key1", "value1")
        cache.invalidate("key1")
        assert cache.get("key1") is None

    def test_clear(self):
        cache = _TTLCache(ttl=10.0)
        cache.set("a", 1)
        cache.set("b", 2)
        cache.clear()
        assert cache.get("a") is None
        assert cache.get("b") is None


class TestConnectionSerialization:
    @pytest.mark.asyncio
    async def test_ensure_connected_serializes_overlapping_connect_attempts(self, mock_ib):
        state = {"connected": False}

        async def _connect_async(**_kwargs):
            await asyncio.sleep(0.01)
            state["connected"] = True

        mock_ib.connectAsync = AsyncMock(side_effect=_connect_async)
        mock_ib.isConnected.side_effect = lambda: state["connected"]

        with patch("src.data_feed.IB", return_value=mock_ib):
            conn = IBConnection(host="127.0.0.1", port=4002, client_id=1)

        results = await asyncio.gather(
            conn.ensure_connected(),
            conn.ensure_connected(),
        )

        assert results == [True, True]
        assert mock_ib.connectAsync.await_count == 1


# ===================================================================
# Tests: RateLimiter
# ===================================================================


class TestRateLimiter:
    @pytest.mark.asyncio
    async def test_acquire_within_limit(self):
        limiter = IBRateLimiter(max_requests=5, request_window_seconds=1.0)
        for _ in range(5):
            await limiter.acquire(
                f"test:{_}",
                category="order",
                request_cost=1,
                order_messages=1,
            )
        # Should not raise

    @pytest.mark.asyncio
    async def test_acquire_respects_limit(self):
        limiter = IBRateLimiter(max_requests=2, request_window_seconds=0.5)
        await limiter.acquire("t1", category="order", request_cost=1, order_messages=1)
        await limiter.acquire("t2", category="order", request_cost=1, order_messages=1)
        # Third acquire should wait but not raise
        await limiter.acquire("t3", category="order", request_cost=1, order_messages=1)


class TestWarmupValidation:
    def test_validate_warmup_returns_false_when_missing_bars(self):
        df = pd.DataFrame({"close": [1.0] * 20})
        assert validate_warmup(df, "AAPL") is False
        assert "SMA200>=200" in get_warmup_missing_rules(df)

    def test_validate_warmup_returns_true_with_sufficient_bars(self):
        df = pd.DataFrame({"close": [1.0] * 250})
        assert validate_warmup(df, "AAPL") is True


# ===================================================================
# Tests: _valid_price
# ===================================================================


class TestValidPrice:
    def test_valid_price(self):
        assert _valid_price(100.0) is True

    def test_none_is_invalid(self):
        assert _valid_price(None) is False

    def test_nan_is_invalid(self):
        assert _valid_price(float("nan")) is False

    def test_zero_is_invalid(self):
        assert _valid_price(0.0) is False

    def test_negative_is_invalid(self):
        assert _valid_price(-10.0) is False

    def test_very_large_is_invalid(self):
        assert _valid_price(1e13) is False


# ===================================================================
# Tests: compute_* functions
# ===================================================================


class TestComputeFunctions:
    def test_compute_sma(self):
        series = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
        result = compute_sma(series, 3)
        assert result.iloc[-1] == pytest.approx(4.0)

    def test_compute_rsi_bounds(self):
        np.random.seed(42)
        series = pd.Series(100 + np.random.randn(50).cumsum())
        result = compute_rsi(series, 14)
        valid = result.dropna()
        assert all(0 <= v <= 100 for v in valid)

    def test_compute_atr_positive(self):
        n = 50
        high = pd.Series([101.0 + i * 0.1 for i in range(n)])
        low = pd.Series([99.0 + i * 0.1 for i in range(n)])
        close = pd.Series([100.0 + i * 0.1 for i in range(n)])
        result = compute_atr(high, low, close, 14)
        valid = result.dropna()
        assert all(v > 0 for v in valid)

    def test_compute_bollinger_bands_structure(self):
        series = pd.Series([float(x) for x in range(1, 30)])
        upper, middle, lower = compute_bollinger_bands(series, 20, 2.0)
        last_upper = upper.dropna().iloc[-1]
        last_middle = middle.dropna().iloc[-1]
        last_lower = lower.dropna().iloc[-1]
        assert last_lower < last_middle < last_upper

"""Tests for src/client/protocol.py.

Covers:
  - UpstoxMarketClient satisfies MarketDataProvider (the methods it provides)
  - UpstoxMarketClient does NOT satisfy BrokerClient (intentional gap — documented here)
  - A full DummyBrokerClient satisfies BrokerClient and all three sub-protocols
  - MarketDataProvider is importable from both protocol.py and tracker.py,
    and both names resolve to the same object

All tests are offline — no HTTP, no DB, no tokens exchanged.
"""

import pytest

from src.client.protocol import (
    BrokerClient,
    MarketDataProvider,
    MarketStream,
    OrderExecutor,
    PortfolioReader,
)


# ---------------------------------------------------------------------------
# Minimal DummyBrokerClient — all 10 required async methods
# ---------------------------------------------------------------------------


class DummyBrokerClient:
    """Inline stub that satisfies the full BrokerClient protocol."""

    async def get_ltp(self, instruments, *a, **kw): ...
    async def get_option_chain(self, instrument, expiry, *a, **kw): ...
    async def place_order(self, order, *a, **kw): ...
    async def modify_order(self, order_id, changes, *a, **kw): ...
    async def cancel_order(self, order_id, *a, **kw): ...
    async def get_positions(self, *a, **kw): ...
    async def get_holdings(self, *a, **kw): ...
    async def get_margins(self, *a, **kw): ...
    async def get_historical_candles(self, params, *a, **kw): ...
    async def get_expired_option_contracts(self, instrument, expiry, *a, **kw): ...


class DummyMarketStream:
    """Inline stub satisfying the MarketStream protocol."""

    async def subscribe(self, instruments, mode): ...
    async def unsubscribe(self, instruments): ...
    def on_tick(self, callback): ...
    async def connect(self): ...
    async def disconnect(self): ...


# ---------------------------------------------------------------------------
# UpstoxMarketClient — partial protocol satisfaction
# ---------------------------------------------------------------------------


class TestUpstoxMarketClientProtocolFit:
    """UpstoxMarketClient provides market data methods only.

    This test class documents the known gap: UpstoxMarketClient satisfies
    MarketDataProvider (the two async methods it exposes) but NOT BrokerClient
    (which additionally requires order execution and portfolio read methods).
    UpstoxLiveClient (task 5.c) will be the full BrokerClient implementation.
    """

    def _make_client(self):
        from src.client.upstox_market import UpstoxMarketClient

        # Pass a fake token to satisfy the constructor guard without env vars.
        return UpstoxMarketClient(token="offline-test-token")

    def test_satisfies_market_data_provider(self):
        client = self._make_client()
        assert isinstance(client, MarketDataProvider)

    def test_does_not_satisfy_broker_client(self):
        """Intentional — UpstoxMarketClient is not the full BrokerClient."""
        client = self._make_client()
        assert not isinstance(client, BrokerClient)


# ---------------------------------------------------------------------------
# DummyBrokerClient — full protocol satisfaction
# ---------------------------------------------------------------------------


class TestDummyBrokerClientSatisfiesAll:
    """A class with all 10 BrokerClient methods satisfies every protocol."""

    def setup_method(self):
        self.client = DummyBrokerClient()

    def test_satisfies_broker_client(self):
        assert isinstance(self.client, BrokerClient)

    def test_satisfies_market_data_provider(self):
        assert isinstance(self.client, MarketDataProvider)

    def test_satisfies_order_executor(self):
        assert isinstance(self.client, OrderExecutor)

    def test_satisfies_portfolio_reader(self):
        assert isinstance(self.client, PortfolioReader)


# ---------------------------------------------------------------------------
# MarketStream — protocol satisfaction
# ---------------------------------------------------------------------------


class TestMarketStreamProtocol:
    def test_dummy_stream_satisfies_market_stream(self):
        assert isinstance(DummyMarketStream(), MarketStream)

    def test_broker_client_does_not_satisfy_market_stream(self):
        """BrokerClient and MarketStream are independent — no crossover."""
        assert not isinstance(DummyBrokerClient(), MarketStream)


# ---------------------------------------------------------------------------
# Import path: both tracker.py and protocol.py export the same object
# ---------------------------------------------------------------------------


class TestMarketDataProviderImportPaths:
    """MarketDataProvider must be importable from both the protocol module
    and tracker.py (which re-exports it). Both names must resolve to the same
    class so that isinstance checks are consistent regardless of import path.
    """

    def test_import_from_protocol_no_error(self):
        from src.client.protocol import MarketDataProvider as MDP  # noqa: F401

        assert MDP is not None

    def test_import_from_tracker_no_error(self):
        from src.portfolio.tracker import MarketDataProvider as MDP  # noqa: F401

        assert MDP is not None

    def test_both_imports_are_same_object(self):
        from src.client.protocol import MarketDataProvider as from_protocol
        from src.portfolio.tracker import MarketDataProvider as from_tracker

        assert from_protocol is from_tracker

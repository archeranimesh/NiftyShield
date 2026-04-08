"""Unit tests for src/client/upstox_live.py.

All tests are fully offline — UpstoxMarketClient is monkeypatched so no
network or env vars are needed. Tests cover:
  - Protocol conformance (MarketDataProvider and BrokerClient isinstance checks)
  - Delegation: get_ltp and get_option_chain pass through to _market unchanged
  - NotImplementedError: all eight blocked methods raise with descriptive messages
  - Error passthrough: LTPFetchError from _market propagates unmodified
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.client.exceptions import LTPFetchError
from src.client.protocol import BrokerClient, MarketDataProvider
from src.client.upstox_live import UpstoxLiveClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_client() -> UpstoxLiveClient:
    """Return an UpstoxLiveClient with a patched UpstoxMarketClient.

    UpstoxMarketClient.__init__ is patched to a no-op so no env var is
    required. The resulting _market attribute is replaced with a MagicMock
    inside each test that needs to control its behaviour.
    """
    with patch(
        "src.client.upstox_live.UpstoxMarketClient.__init__",
        return_value=None,
    ):
        client = UpstoxLiveClient(token="fake-token")
    return client


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------


class TestProtocolConformance:
    """UpstoxLiveClient must satisfy both MarketDataProvider and BrokerClient."""

    def test_isinstance_market_data_provider(self) -> None:
        client = make_client()
        assert isinstance(client, MarketDataProvider)

    def test_isinstance_broker_client(self) -> None:
        client = make_client()
        assert isinstance(client, BrokerClient)


# ---------------------------------------------------------------------------
# Delegation — market data methods
# ---------------------------------------------------------------------------


class TestDelegation:
    """Market data calls delegate to _market with identical arguments."""

    @pytest.mark.asyncio
    async def test_get_ltp_delegates_to_market(self) -> None:
        client = make_client()
        instruments = ["NSE_EQ|INF754K01LE1", "NSE_FO|37810"]
        expected = {"NSE_EQ|INF754K01LE1": 1388.5, "NSE_FO|37810": 975.0}

        client._market = MagicMock()
        client._market.get_ltp = AsyncMock(return_value=expected)

        result = await client.get_ltp(instruments)

        client._market.get_ltp.assert_awaited_once_with(instruments)
        assert result == expected

    @pytest.mark.asyncio
    async def test_get_option_chain_delegates_to_market(self) -> None:
        client = make_client()
        instrument = "NSE_INDEX|Nifty 50"
        expiry = "2026-06-30"
        expected = {"data": "chain"}

        client._market = MagicMock()
        client._market.get_option_chain = AsyncMock(return_value=expected)

        result = await client.get_option_chain(instrument, expiry)

        client._market.get_option_chain.assert_awaited_once_with(instrument, expiry)
        assert result == expected


# ---------------------------------------------------------------------------
# NotImplementedError — all eight blocked methods
# ---------------------------------------------------------------------------


class TestNotImplemented:
    """All blocked methods raise NotImplementedError with a descriptive message."""

    @pytest.mark.asyncio
    async def test_place_order_raises(self) -> None:
        client = make_client()
        with pytest.raises(NotImplementedError, match="static IP"):
            await client.place_order(object())

    @pytest.mark.asyncio
    async def test_modify_order_raises(self) -> None:
        client = make_client()
        with pytest.raises(NotImplementedError, match="static IP"):
            await client.modify_order("order-id", object())

    @pytest.mark.asyncio
    async def test_cancel_order_raises(self) -> None:
        client = make_client()
        with pytest.raises(NotImplementedError, match="static IP"):
            await client.cancel_order("order-id")

    @pytest.mark.asyncio
    async def test_get_positions_raises(self) -> None:
        client = make_client()
        with pytest.raises(NotImplementedError, match="Daily OAuth token"):
            await client.get_positions()

    @pytest.mark.asyncio
    async def test_get_holdings_raises(self) -> None:
        client = make_client()
        with pytest.raises(NotImplementedError, match="Daily OAuth token"):
            await client.get_holdings()

    @pytest.mark.asyncio
    async def test_get_margins_raises(self) -> None:
        client = make_client()
        with pytest.raises(NotImplementedError, match="Daily OAuth token"):
            await client.get_margins()

    @pytest.mark.asyncio
    async def test_get_historical_candles_raises(self) -> None:
        client = make_client()
        with pytest.raises(NotImplementedError):
            await client.get_historical_candles(object())

    @pytest.mark.asyncio
    async def test_get_expired_option_contracts_raises(self) -> None:
        client = make_client()
        with pytest.raises(NotImplementedError, match="paid subscription"):
            await client.get_expired_option_contracts("NSE_INDEX|Nifty 50", "2026-06-30")


# ---------------------------------------------------------------------------
# Error passthrough
# ---------------------------------------------------------------------------


class TestErrorPassthrough:
    """Exceptions from _market must propagate without being swallowed."""

    @pytest.mark.asyncio
    async def test_ltp_fetch_error_propagates(self) -> None:
        client = make_client()
        client._market = MagicMock()
        client._market.get_ltp = AsyncMock(
            side_effect=LTPFetchError("API returned empty data")
        )

        with pytest.raises(LTPFetchError, match="API returned empty data"):
            await client.get_ltp(["NSE_EQ|INF754K01LE1"])

    @pytest.mark.asyncio
    async def test_option_chain_error_propagates(self) -> None:
        from src.client.exceptions import DataFetchError

        client = make_client()
        client._market = MagicMock()
        client._market.get_option_chain = AsyncMock(
            side_effect=DataFetchError("Option chain fetch failed: timeout")
        )

        with pytest.raises(DataFetchError, match="timeout"):
            await client.get_option_chain("NSE_INDEX|Nifty 50", "2026-06-30")

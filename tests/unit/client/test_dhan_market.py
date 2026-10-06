"""Tests for DhanMarketClient and parsing."""

import asyncio
import json
from datetime import date
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest

from src.client.dhan_market import DhanMarketClient, SpacingRateLimiter, parse_dhan_option_chain
from src.client.exceptions import AuthenticationError, DataFetchError, NotSubscribedError


class FakeClock:
    def __init__(self):
        self._time = 0.0
        self.sleeps = []

    def time(self) -> float:
        return self._time

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self._time += seconds


class DummyRateLimiter:
    async def acquire(self) -> None:
        pass


@pytest.fixture
def dec2027_fixture() -> dict[str, Any]:
    with open("tests/fixtures/dhan_chain/dec2027.json") as f:
        return json.load(f)


def test_parse_dec2027_fixture_has_nonzero_deltas(dec2027_fixture: dict[str, Any]):
    chain = parse_dhan_option_chain(dec2027_fixture, date(2027, 12, 30))
    # Find a strike that has a nonzero delta
    has_nonzero = False
    for _strike, data in chain.strikes.items():
        if data.pe and data.pe.delta and data.pe.delta != Decimal("0"):
            has_nonzero = True
            break
        if data.ce and data.ce.delta and data.ce.delta != Decimal("0"):
            has_nonzero = True
            break

    assert has_nonzero, "Should have parsed at least one non-zero delta from the fixture"


def test_parse_empty_chain_returns_empty_not_error():
    empty_data = {"data": {}}
    chain = parse_dhan_option_chain(empty_data, date(2027, 12, 30))
    assert chain.underlying_spot == Decimal("0")
    assert chain.strikes == {}


def test_missing_delta_is_None(dec2027_fixture: dict[str, Any]):
    # Pop delta key
    strike_oc = dec2027_fixture["data"]["oc"]["3000.000000"]
    del strike_oc["ce"]["greeks"]["delta"]

    chain = parse_dhan_option_chain(dec2027_fixture, date(2027, 12, 30))
    assert chain.strikes[Decimal("3000")].ce.delta is None

    # Set it to null
    strike_oc["pe"]["greeks"]["delta"] = None
    chain2 = parse_dhan_option_chain(dec2027_fixture, date(2027, 12, 30))
    assert chain2.strikes[Decimal("3000")].pe.delta is None


@pytest.mark.asyncio
async def test_requests_spaced_by_rate_limiter():
    clock = FakeClock()
    rate_limiter = SpacingRateLimiter(4.0, clock)

    await rate_limiter.acquire()
    assert clock.time() == 0.0

    # 2 seconds pass
    clock._time = 2.0
    await rate_limiter.acquire()
    assert clock.time() == 4.0

    # Next spacing should happen after 4 seconds
    clock._time = 5.0
    await rate_limiter.acquire()
    assert clock.time() == 8.0


@pytest.fixture
def mock_session_get():
    with patch("aiohttp.ClientSession.get") as mock_get:
        yield mock_get


def _make_mock_response(status=200, json_data=None, exception=None):
    mock_resp = AsyncMock()
    mock_resp.status = status
    if json_data is not None:
        mock_resp.json.return_value = json_data
    if status >= 400:
        mock_resp.raise_for_status.side_effect = aiohttp.ClientResponseError(
            request_info=MagicMock(), history=(), status=status
        )
    mock_ctx = MagicMock()
    if exception:
        mock_ctx.__aenter__.side_effect = exception
    else:
        mock_ctx.__aenter__.return_value = mock_resp
    return mock_ctx


@pytest.mark.asyncio
async def test_805_backs_off_then_raises(mock_session_get):
    clock = FakeClock()
    mock_session_get.return_value = _make_mock_response(json_data={"errorCode": "805"})

    async with aiohttp.ClientSession() as session:
        client = DhanMarketClient(session, DummyRateLimiter(), clock)
        with pytest.raises(DataFetchError, match="Error 805 after max retries"):
            await client.get_option_chain("NIFTY", date(2027, 12, 30))

    assert mock_session_get.call_count == 4
    assert clock.sleeps == [2.0, 4.0, 8.0]


@pytest.mark.asyncio
async def test_806_raises_not_subscribed(mock_session_get):
    clock = FakeClock()
    mock_session_get.return_value = _make_mock_response(json_data={"errorCode": "806"})

    async with aiohttp.ClientSession() as session:
        client = DhanMarketClient(session, DummyRateLimiter(), clock)
        with pytest.raises(NotSubscribedError, match="Not subscribed"):
            await client.get_option_chain("NIFTY", date(2027, 12, 30))


@pytest.mark.asyncio
async def test_timeout_raises(mock_session_get):
    clock = FakeClock()
    mock_session_get.return_value = _make_mock_response(exception=asyncio.TimeoutError())

    async with aiohttp.ClientSession() as session:
        client = DhanMarketClient(session, DummyRateLimiter(), clock)
        with pytest.raises(DataFetchError, match="Request timed out"):
            await client.get_option_chain("NIFTY", date(2027, 12, 30))


@pytest.mark.asyncio
async def test_auth_failure(mock_session_get):
    clock = FakeClock()
    mock_session_get.return_value = _make_mock_response(status=401)

    async with aiohttp.ClientSession() as session:
        client = DhanMarketClient(session, DummyRateLimiter(), clock)
        with pytest.raises(AuthenticationError):
            await client.get_option_chain("NIFTY", date(2027, 12, 30))


@pytest.mark.live
@pytest.mark.asyncio
async def test_live_read():
    import time

    class RealClock:
        def time(self):
            return time.time()

        async def sleep(self, s):
            await asyncio.sleep(s)

    async with aiohttp.ClientSession() as session:
        client = DhanMarketClient(session, DummyRateLimiter(), RealClock())
        # Just verifying it makes the request without throwing immediately
        with pytest.raises(aiohttp.ClientError):
            await client.get_option_chain("NIFTY", date(2027, 12, 30))

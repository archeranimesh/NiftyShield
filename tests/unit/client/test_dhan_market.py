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
def mock_session_post():
    with patch("aiohttp.ClientSession.post") as mock_get:
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
async def test_805_backs_off_then_raises(mock_session_post):
    clock = FakeClock()
    mock_session_post.return_value = _make_mock_response(json_data={"errorCode": "805"})

    async with aiohttp.ClientSession() as session:
        client = DhanMarketClient(
            session, DummyRateLimiter(), clock, "dummy_token", "dummy_client_id", max_retries=1
        )
        with pytest.raises(DataFetchError, match="Error 805 after max retries"):
            await client.get_option_chain("NSE_INDEX|Nifty 50", date(2027, 12, 30))

    assert mock_session_post.call_count == 2
    assert clock.sleeps == [2.0]


@pytest.mark.asyncio
async def test_806_raises_not_subscribed(mock_session_post):
    clock = FakeClock()
    mock_session_post.return_value = _make_mock_response(json_data={"errorCode": "806"})

    async with aiohttp.ClientSession() as session:
        client = DhanMarketClient(
            session, DummyRateLimiter(), clock, "dummy_token", "dummy_client_id"
        )
        with pytest.raises(NotSubscribedError, match="Not subscribed"):
            await client.get_option_chain("NSE_INDEX|Nifty 50", date(2027, 12, 30))


@pytest.mark.asyncio
async def test_timeout_raises(mock_session_post):
    clock = FakeClock()
    mock_session_post.return_value = _make_mock_response(exception=asyncio.TimeoutError())

    async with aiohttp.ClientSession() as session:
        client = DhanMarketClient(
            session, DummyRateLimiter(), clock, "dummy_token", "dummy_client_id"
        )
        with pytest.raises(DataFetchError, match="Request timed out"):
            await client.get_option_chain("NSE_INDEX|Nifty 50", date(2027, 12, 30))


@pytest.mark.asyncio
async def test_auth_failure(mock_session_post):
    clock = FakeClock()
    mock_session_post.return_value = _make_mock_response(status=401)

    async with aiohttp.ClientSession() as session:
        client = DhanMarketClient(
            session, DummyRateLimiter(), clock, "dummy_token", "dummy_client_id"
        )
        with pytest.raises(AuthenticationError):
            await client.get_option_chain("NSE_INDEX|Nifty 50", date(2027, 12, 30))


@pytest.mark.live
@pytest.mark.asyncio
async def test_live_read():
    import os
    import time

    from src.client.dhan_market import Clock, SpacingRateLimiter

    class RealClock(Clock):
        def time(self) -> float:
            return time.time()

        async def sleep(self, seconds: float) -> None:
            import asyncio

            await asyncio.sleep(seconds)

    token = os.environ.get("DHAN_ACCESS_TOKEN", "")
    client_id = os.environ.get("DHAN_CLIENT_ID", "")

    if not token or not client_id:
        pytest.skip("Dhan credentials not configured in environment")

    async with aiohttp.ClientSession() as session:
        clock = RealClock()
        rate_limiter = SpacingRateLimiter(4.0, clock)
        client = DhanMarketClient(session, rate_limiter, clock, token, client_id)

        chain = await client.get_option_chain("NSE_INDEX|Nifty 50", date(2026, 12, 29))

        assert chain.strikes, "Chain should not be empty"
        has_delta = False
        for strike in chain.strikes.values():
            if (strike.ce and strike.ce.delta is not None) or (
                strike.pe and strike.pe.delta is not None
            ):
                has_delta = True
                break
        assert has_delta, "No leg with a populated delta found"


@pytest.mark.asyncio
async def test_unknown_underlying_raises():
    from src.client.exceptions import DataFetchError

    client = DhanMarketClient(None, None, None, "dummy_token", "dummy_client_id")
    with pytest.raises(DataFetchError, match="Unknown underlying"):
        await client.get_option_chain("UNKNOWN", date(2026, 10, 29))


def test_parse_dec2026_normalises_all_zero_greeks():
    import json
    from datetime import date

    with open("tests/fixtures/dhan_chain/dec2026.json") as f:
        data = json.load(f)

    chain = parse_dhan_option_chain(data, date(2026, 12, 31))

    # a) CE 22000 -> delta/gamma/theta/vega all None while ltp and oi are preserved
    ce_22000 = chain.strikes[Decimal("22000")].ce
    assert ce_22000.delta is None
    assert ce_22000.gamma is None
    assert ce_22000.theta is None
    assert ce_22000.vega is None
    assert ce_22000.ltp == Decimal("1209")
    assert ce_22000.oi == 699780

    # b) PE strike with delta -0.0018, gamma 0, vega 0.63033 keeps gamma Decimal("0")
    pe_12000 = chain.strikes[Decimal("12000")].pe
    assert pe_12000.delta == Decimal("-0.0018")
    assert pe_12000.gamma == Decimal("0")
    assert pe_12000.vega == Decimal("0.63033")

    # c) a leg with absent key or JSON null is still None
    # We can check existing missing delta test or one from the fixture, but the logic handles it.

    # d) a real non-zero leg is unchanged (already covered above implicitly)


@pytest.mark.asyncio
async def test_dhan_client_request_parameters(mock_session_post):
    clock = FakeClock()
    mock_session_post.return_value = _make_mock_response(
        json_data={"data": {"oc": {}, "last_price": 20000}}
    )

    async with aiohttp.ClientSession() as session:
        client = DhanMarketClient(
            session, DummyRateLimiter(), clock, "real_token", "real_client_id"
        )
        await client.get_option_chain("NSE_INDEX|Nifty 50", date(2026, 10, 29))

    mock_session_post.assert_called_once()
    args, kwargs = mock_session_post.call_args
    assert args[0] == "https://api.dhan.co/v2/optionchain"

    assert "json" in kwargs
    payload = kwargs["json"]
    assert payload["UnderlyingScrip"] == 13
    assert payload["UnderlyingSeg"] == "IDX_I"
    assert payload["Expiry"] == "2026-10-29"

    assert "headers" in kwargs
    headers = kwargs["headers"]
    assert headers["access-token"] == "real_token"
    assert headers["client-id"] == "real_client_id"
    assert headers["Content-Type"] == "application/json"

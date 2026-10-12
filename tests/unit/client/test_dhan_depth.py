"""Unit tests for DhanDepthAdapter."""

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.client.dhan_depth import DhanDepthAdapter, parse_dhan_depth_quote
from src.client.exceptions import AuthenticationError, DataFetchError, RateLimitError
from src.gamma.depth import DepthSource


class FakeClock:
    def __init__(self) -> None:
        self._time = 0.0
        self.sleeps: list[float] = []

    def time(self) -> float:
        return self._time

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self._time += seconds


class DummyRateLimiter:
    async def acquire(self) -> None:
        pass


@pytest.fixture
def synthetic_depth_fixture() -> dict:
    fixture_path = (
        Path(__file__).parents[3]
        / "tests"
        / "fixtures"
        / "dhan_depth"
        / "synthetic_depth_response.json"
    )
    with open(fixture_path, encoding="utf-8") as f:
        return json.load(f)


def test_parse_dhan_depth_happy_path(synthetic_depth_fixture: dict):
    snap = parse_dhan_depth_quote(synthetic_depth_fixture, "49081", "NSE_FNO")
    assert snap is not None
    assert snap.bid_qty_l1 == 150
    assert snap.ask_qty_l1 == 300
    assert snap.total_bid_qty == 1500
    assert snap.total_ask_qty == 2250
    assert snap.timestamp is not None


def test_parse_dhan_depth_missing_security_id(synthetic_depth_fixture: dict):
    # Security id 99999 is not present in data.NSE_FNO
    snap = parse_dhan_depth_quote(synthetic_depth_fixture, "99999", "NSE_FNO")
    assert snap is None


def test_parse_dhan_depth_all_zero_quantities():
    data = {
        "status": "success",
        "data": {
            "NSE_FNO": {
                "49081": {
                    "buy_quantity": 0,
                    "sell_quantity": 0,
                    "depth": {
                        "buy": [{"quantity": 0, "price": 0.0, "orders": 0}],
                        "sell": [{"quantity": 0, "price": 0.0, "orders": 0}],
                    },
                }
            }
        },
    }
    snap = parse_dhan_depth_quote(data, "49081", "NSE_FNO")
    assert snap is None


def test_parse_dhan_depth_malformed_or_status_failure():
    assert parse_dhan_depth_quote({"status": "failure"}, "49081") is None
    assert parse_dhan_depth_quote({"status": "success", "data": {}}, "49081") is None
    assert (
        parse_dhan_depth_quote(
            {"status": "success", "data": {"NSE_FNO": {"49081": {"depth": {}}}}},
            "49081",
        )
        is None
    )


@pytest.mark.asyncio
async def test_adapter_satisfies_depth_source_protocol():
    session = AsyncMock()
    adapter = DhanDepthAdapter(
        session=session,
        rate_limiter=DummyRateLimiter(),
        clock=FakeClock(),
        access_token="test_token",
        client_id="test_client",
    )
    assert isinstance(adapter, DepthSource)


@pytest.mark.asyncio
async def test_adapter_happy_path(synthetic_depth_fixture: dict):
    mock_resp = AsyncMock()
    mock_resp.status = 200
    mock_resp.json = AsyncMock(return_value=synthetic_depth_fixture)

    mock_post = MagicMock()
    mock_post.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_post.__aexit__ = AsyncMock(return_value=None)

    mock_session = MagicMock()
    mock_session.post.return_value = mock_post

    adapter = DhanDepthAdapter(
        session=mock_session,
        rate_limiter=DummyRateLimiter(),
        clock=FakeClock(),
        access_token="test_token",
        client_id="test_client",
    )

    snap = await adapter.fetch("49081", "NSE_FNO")
    assert snap is not None
    assert snap.bid_qty_l1 == 150
    assert snap.ask_qty_l1 == 300

    # Verify request payload format
    call_args = mock_session.post.call_args
    assert call_args[1]["json"] == {"NSE_FNO": [49081]}


@pytest.mark.asyncio
async def test_adapter_invalid_non_numeric_security_id():
    mock_session = MagicMock()
    adapter = DhanDepthAdapter(
        session=mock_session,
        rate_limiter=DummyRateLimiter(),
        clock=FakeClock(),
        access_token="test_token",
        client_id="test_client",
    )
    snap = await adapter.fetch("non_numeric_id", "NSE_FNO")
    assert snap is None
    assert not mock_session.post.called


@pytest.mark.asyncio
async def test_adapter_auth_error_mapping():
    for status in (401, 403):
        mock_resp = AsyncMock()
        mock_resp.status = status

        mock_post = MagicMock()
        mock_post.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_post.__aexit__ = AsyncMock(return_value=None)

        mock_session = MagicMock()
        mock_session.post.return_value = mock_post

        adapter = DhanDepthAdapter(
            session=mock_session,
            rate_limiter=DummyRateLimiter(),
            clock=FakeClock(),
            access_token="test_token",
            client_id="test_client",
        )

        with pytest.raises(AuthenticationError):
            await adapter.fetch("49081")


@pytest.mark.asyncio
async def test_adapter_rate_limit_429_mapping():
    mock_resp = AsyncMock()
    mock_resp.status = 429

    mock_post = MagicMock()
    mock_post.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_post.__aexit__ = AsyncMock(return_value=None)

    mock_session = MagicMock()
    mock_session.post.return_value = mock_post

    adapter = DhanDepthAdapter(
        session=mock_session,
        rate_limiter=DummyRateLimiter(),
        clock=FakeClock(),
        access_token="test_token",
        client_id="test_client",
    )

    with pytest.raises(RateLimitError):
        await adapter.fetch("49081")


@pytest.mark.asyncio
async def test_adapter_timeout_maps_to_data_fetch_error():
    mock_post = MagicMock()
    mock_post.__aenter__ = AsyncMock(side_effect=asyncio.TimeoutError())
    mock_post.__aexit__ = AsyncMock(return_value=None)

    mock_session = MagicMock()
    mock_session.post.return_value = mock_post

    clock = FakeClock()
    adapter = DhanDepthAdapter(
        session=mock_session,
        rate_limiter=DummyRateLimiter(),
        clock=clock,
        access_token="test_token",
        client_id="test_client",
        max_retries=2,
    )

    with pytest.raises(DataFetchError, match="Request timed out"):
        await adapter.fetch("49081")

    # Retries occurred
    assert len(clock.sleeps) == 2


@pytest.mark.asyncio
async def test_adapter_non_200_returns_none():
    mock_resp = AsyncMock()
    mock_resp.status = 500

    mock_post = MagicMock()
    mock_post.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_post.__aexit__ = AsyncMock(return_value=None)

    mock_session = MagicMock()
    mock_session.post.return_value = mock_post

    adapter = DhanDepthAdapter(
        session=mock_session,
        rate_limiter=DummyRateLimiter(),
        clock=FakeClock(),
        access_token="test_token",
        client_id="test_client",
    )

    res = await adapter.fetch("49081")
    assert res is None

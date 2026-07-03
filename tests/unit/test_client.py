"""Unit tests for src/client/upstox_market.py error propagation.

All tests are offline — UpstoxMarketClient is instantiated with a fake
token and requests are intercepted via monkeypatching.

Covers:
- LTPFetchError raised on HTTP failure (connection error, timeout, 5xx)
- LTPFetchError raised on empty API response
- LTPFetchError raised when response data has no resolvable instrument_tokens
- Partial success (some instruments resolve) returns only resolved keys
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest
import requests
import structlog

from src.client.exceptions import LTPFetchError
from src.client.upstox_market import UpstoxMarketClient

FAKE_TOKEN = "fake-analytics-token"


@pytest.fixture
def client() -> UpstoxMarketClient:
    return UpstoxMarketClient(token=FAKE_TOKEN)


# ── HTTP failure → LTPFetchError ──────────────────────────────────


def test_ltp_raises_on_connection_error(client: UpstoxMarketClient, monkeypatch) -> None:
    """A ConnectionError from requests must surface as LTPFetchError."""

    def _fail(*args, **kwargs):
        raise requests.ConnectionError("connection refused")

    monkeypatch.setattr(client._session, "get", _fail)
    with pytest.raises(LTPFetchError, match="LTP batch request failed"):
        client.get_ltp_sync(["NSE_FO|37810"])


def test_ltp_raises_on_timeout(client: UpstoxMarketClient, monkeypatch) -> None:
    """A timeout from requests must surface as LTPFetchError."""

    def _fail(*args, **kwargs):
        raise requests.Timeout("read timeout")

    monkeypatch.setattr(client._session, "get", _fail)
    with pytest.raises(LTPFetchError):
        client.get_ltp_sync(["NSE_FO|37810"])


def test_ltp_raises_on_http_500(client: UpstoxMarketClient, monkeypatch) -> None:
    """An HTTP 500 must surface as LTPFetchError."""

    class _Resp:
        status_code = 500

        def raise_for_status(self):
            raise requests.HTTPError("500 Server Error")

    monkeypatch.setattr(client._session, "get", lambda *a, **kw: _Resp())
    with pytest.raises(LTPFetchError):
        client.get_ltp_sync(["NSE_FO|37810"])


# ── Empty / unresolvable response → LTPFetchError ─────────────────


def test_ltp_raises_on_empty_data(client: UpstoxMarketClient, monkeypatch) -> None:
    """An API response with empty 'data' must raise LTPFetchError."""

    class _Resp:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {"status": "success", "data": {}}

    monkeypatch.setattr(client._session, "get", lambda *a, **kw: _Resp())
    with pytest.raises(LTPFetchError, match="empty data"):
        client.get_ltp_sync(["NSE_FO|37810"])


def test_ltp_raises_when_no_instrument_token(client: UpstoxMarketClient, monkeypatch) -> None:
    """Response data present but no instrument_token fields → LTPFetchError."""

    class _Resp:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            # Entries exist but instrument_token is missing — can't remap
            return {"data": {"NSE_FO:NIFTY26D2923000PE": {"last_price": 975.0}}}

    monkeypatch.setattr(client._session, "get", lambda *a, **kw: _Resp())
    with pytest.raises(LTPFetchError, match="no resolvable instrument_token"):
        client.get_ltp_sync(["NSE_FO|37810"])


# ── Empty instruments list → fast return ──────────────────────────


def test_ltp_returns_empty_for_no_instruments(client: UpstoxMarketClient) -> None:
    """Empty input must return {} without making any HTTP call."""
    result = client.get_ltp_sync([])
    assert result == {}


# ── Successful response → correct mapping ─────────────────────────


def test_ltp_maps_instrument_token_to_price(client: UpstoxMarketClient, monkeypatch) -> None:
    """Successful response must be keyed by pipe-format instrument_token."""

    class _Resp:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {
                "data": {
                    "NSE_FO:NIFTY26D2923000PE": {
                        "instrument_token": "NSE_FO|37810",
                        "last_price": 975.0,
                    }
                }
            }

    monkeypatch.setattr(client._session, "get", lambda *a, **kw: _Resp())
    result = client.get_ltp_sync(["NSE_FO|37810"])
    assert result == {"NSE_FO|37810": Decimal("975.0")}


# ── Structured latency logging (FR-5) ────────────────────────────


class _OkResp:
    """Minimal successful response stub shared by logging tests."""

    status_code = 200

    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict:
        return {
            "data": {
                "NSE_FO:NIFTY26D2923000PE": {
                    "instrument_token": "NSE_FO|37810",
                    "last_price": 100.0,
                }
            }
        }


def test_ltp_logs_latency_ms_and_status_code(client: UpstoxMarketClient, monkeypatch) -> None:
    """_fetch_ltp_batch must emit endpoint, status_code, and latency_ms.

    Uses structlog's `capture_logs()` rather than stdlib `caplog` — after the
    BUG-010 B010.2 migration, `upstox_market.logger` is a structlog logger
    whose keyword-argument event dict isn't rendered into stdlib
    `record.getMessage()` text the way the old `%s`-style call was.
    """
    monkeypatch.setattr(client._session, "get", lambda *a, **kw: _OkResp())

    with structlog.testing.capture_logs() as captured:
        client.get_ltp_sync(["NSE_FO|37810"])

    events = [e for e in captured if e.get("event") == "upstox.api_call"]
    assert events, f"expected an 'upstox.api_call' event, got {captured}"
    assert "latency_ms" in events[0]
    assert "status_code" in events[0]


def test_ohlc_logs_latency_ms_and_status_code(client: UpstoxMarketClient, monkeypatch) -> None:
    """get_ohlc_sync must emit endpoint, status_code, and latency_ms."""

    class _OhlcResp:
        status_code = 200

        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict:
            return {"data": {}}

    monkeypatch.setattr(client._session, "get", lambda *a, **kw: _OhlcResp())

    with structlog.testing.capture_logs() as captured:
        client.get_ohlc_sync(["NSE_FO|37810"], interval="1d")

    events = [e for e in captured if e.get("event") == "upstox.api_call"]
    assert events, f"expected an 'upstox.api_call' event, got {captured}"
    assert "latency_ms" in events[0]
    assert "status_code" in events[0]


def test_option_chain_logs_latency_ms_and_status_code(
    client: UpstoxMarketClient, monkeypatch
) -> None:
    """get_option_chain_sync must emit endpoint, status_code, and latency_ms."""

    class _ChainResp:
        status_code = 200

        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict:
            return {"data": {}}

    monkeypatch.setattr(client._session, "get", lambda *a, **kw: _ChainResp())

    with structlog.testing.capture_logs() as captured:
        client.get_option_chain_sync("NSE_INDEX|Nifty 50", "2026-06-19")

    events = [e for e in captured if e.get("event") == "upstox.api_call"]
    assert events, f"expected an 'upstox.api_call' event, got {captured}"
    assert "latency_ms" in events[0]
    assert "status_code" in events[0]


@pytest.mark.asyncio
async def test_async_get_ltp_maps_correctly(
    client: UpstoxMarketClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Async get_ltp must correctly return remapped Decimal prices."""

    class _Resp:
        status_code = 200

        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict[str, Any]:
            return {
                "data": {
                    "NSE_FO:NIFTY26D2923000PE": {
                        "instrument_token": "NSE_FO|37810",
                        "last_price": 975.0,
                    }
                }
            }

    monkeypatch.setattr(client._session, "get", lambda *a, **kw: _Resp())
    result = await client.get_ltp(["NSE_FO|37810"])
    assert result == {"NSE_FO|37810": Decimal("975.0")}


@pytest.mark.asyncio
async def test_async_get_ltp_raises_on_empty_data(
    client: UpstoxMarketClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Async get_ltp must raise LTPFetchError on empty response."""

    class _Resp:
        status_code = 200

        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict[str, Any]:
            return {"status": "success", "data": {}}

    monkeypatch.setattr(client._session, "get", lambda *a, **kw: _Resp())
    with pytest.raises(LTPFetchError, match="empty data"):
        await client.get_ltp(["NSE_FO|37810"])

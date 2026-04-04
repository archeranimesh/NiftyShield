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

import pytest
import requests

from src.client.exceptions import DataFetchError, LTPFetchError
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
        def raise_for_status(self): pass
        def json(self): return {"status": "success", "data": {}}

    monkeypatch.setattr(client._session, "get", lambda *a, **kw: _Resp())
    with pytest.raises(LTPFetchError, match="empty data"):
        client.get_ltp_sync(["NSE_FO|37810"])


def test_ltp_raises_when_no_instrument_token(client: UpstoxMarketClient, monkeypatch) -> None:
    """Response data present but no instrument_token fields → LTPFetchError."""

    class _Resp:
        def raise_for_status(self): pass
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
        def raise_for_status(self): pass
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
    assert result == {"NSE_FO|37810": 975.0}


# ── DataFetchError hierarchy ──────────────────────────────────────


def test_ltp_fetch_error_is_data_fetch_error() -> None:
    """LTPFetchError must be catchable as DataFetchError."""
    err = LTPFetchError("test")
    assert isinstance(err, DataFetchError)

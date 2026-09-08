"""Tests for GrokSignalProvider — HTTP mocked, no network."""

import asyncio
import json
from datetime import date
from decimal import Decimal
from unittest.mock import patch

import aiohttp
import pytest

from src.client.exceptions import DataFetchError
from src.signals.models import (
    Direction,
    FIIData,
    MarketSnapshot,
    OILevel,
    OptionChainSummary,
    SignalResponse,
)
from src.signals.protocol import SignalProvider
from src.signals.providers.grok import GrokSignalProvider

ATM = 24000


@pytest.fixture
def snapshot() -> MarketSnapshot:
    return MarketSnapshot(
        trade_date=date(2026, 9, 7),
        nifty_spot=Decimal("24000.50"),
        prev_close=Decimal("23900.00"),
        prev_high=Decimal("24050.00"),
        prev_low=Decimal("23850.00"),
        gift_nifty=Decimal("24100.00"),
        india_vix=Decimal("15.5"),
        vix_5d_trend="rising",
        usd_inr=Decimal("83.50"),
        monthly_expiry=date(2026, 9, 24),
        option_chain=OptionChainSummary(
            atm_strike=ATM,
            atm_iv=Decimal("16.0"),
            iv_skew=Decimal("-0.5"),
            pcr_total=Decimal("0.85"),
            pcr_atm=Decimal("0.90"),
            top_call_oi=[OILevel(strike=24100, oi=100000, oi_change=5000)],
            top_put_oi=[OILevel(strike=23900, oi=150000, oi_change=-2000)],
        ),
        fii=FIIData(
            fii_cash_net_cr=Decimal("1500.5"),
            dii_cash_net_cr=Decimal("-500.0"),
        ),
    )


class _FakeResponse:
    def __init__(self, *, body: str, raise_status: aiohttp.ClientResponseError | None = None):
        self._body = body
        self._raise_status = raise_status

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def raise_for_status(self):
        if self._raise_status is not None:
            raise self._raise_status

    async def json(self):
        return json.loads(self._body)


class _FakeSession:
    def __init__(self, response: _FakeResponse):
        self._response = response
        self.calls: list[tuple[tuple, dict]] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def post(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return self._response


def _patch_session(session: _FakeSession):
    return patch("aiohttp.ClientSession", return_value=session)


def _valid_body(direction: str = "BULLISH", confidence: int = 4) -> str:
    content = json.dumps(
        {
            "direction": direction,
            "confidence": confidence,
            "recommended_strike": ATM,
            "entry_premium_low": 50,
            "entry_premium_high": 60,
            "key_reason": "trend up",
            "key_risk": "gap down",
        }
    )
    return json.dumps({"choices": [{"message": {"content": content}}]})


async def test_phase1_openrouter_returns_signal(snapshot: MarketSnapshot) -> None:
    session = _FakeSession(_FakeResponse(body=_valid_body("BEARISH", 3)))
    with _patch_session(session):
        resp = await GrokSignalProvider(api_key="k").get_signal(snapshot)
    assert isinstance(resp, SignalResponse)
    assert resp.direction is Direction.BEARISH
    assert resp.confidence == 3
    assert resp.provider == "grok"
    assert resp.entry_premium_low == Decimal("50")
    url = session.calls[0][0][0]
    assert url == "https://openrouter.ai/api/v1/chat/completions"
    assert "search" not in session.calls[0][1]["json"]


async def test_phase2_xai_direct_uses_xai_base_url(snapshot: MarketSnapshot) -> None:
    session = _FakeSession(_FakeResponse(body=_valid_body()))
    with _patch_session(session):
        await GrokSignalProvider(api_key="k", use_openrouter=False).get_signal(snapshot)
    args, kwargs = session.calls[0]
    assert args[0] == "https://api.x.ai/v1/chat/completions"
    assert kwargs["json"]["model"] == "grok-3"
    assert kwargs["json"]["search"] is True


async def test_http_429_raises_datafetcherror(snapshot: MarketSnapshot) -> None:
    req_info = aiohttp.RequestInfo(
        url=aiohttp.client.URL("https://openrouter.ai/api/v1/chat/completions"),
        method="POST",
        headers=aiohttp.typedefs.CIMultiDict(),
        real_url=aiohttp.client.URL("https://openrouter.ai/api/v1/chat/completions"),
    )
    err = aiohttp.ClientResponseError(request_info=req_info, history=(), status=429)
    with _patch_session(_FakeSession(_FakeResponse(body="{}", raise_status=err))):
        with pytest.raises(DataFetchError):
            await GrokSignalProvider(api_key="k").get_signal(snapshot)


async def test_non_json_body_raises_datafetcherror(snapshot: MarketSnapshot) -> None:
    body = json.dumps({"choices": [{"message": {"content": "not json at all"}}]})
    with _patch_session(_FakeSession(_FakeResponse(body=body))):
        with pytest.raises(DataFetchError, match="could not parse"):
            await GrokSignalProvider(api_key="k").get_signal(snapshot)


async def test_missing_key_raises_datafetcherror(snapshot: MarketSnapshot) -> None:
    content = json.dumps({"direction": "BULLISH"})  # missing confidence, strike, premiums
    body = json.dumps({"choices": [{"message": {"content": content}}]})
    with _patch_session(_FakeSession(_FakeResponse(body=body))):
        with pytest.raises(DataFetchError, match="could not parse"):
            await GrokSignalProvider(api_key="k").get_signal(snapshot)


async def test_timeout_raises_datafetcherror(snapshot: MarketSnapshot) -> None:
    with patch("aiohttp.ClientSession", side_effect=asyncio.TimeoutError):
        with pytest.raises(DataFetchError, match="timed out"):
            await GrokSignalProvider(api_key="k").get_signal(snapshot)


def test_provider_name_attribute() -> None:
    assert GrokSignalProvider(api_key="k").provider_name == "grok"


def test_default_model_slug() -> None:
    assert GrokSignalProvider(api_key="k")._model == "x-ai/grok-3"


async def test_model_override_sent_in_payload(snapshot: MarketSnapshot) -> None:
    session = _FakeSession(_FakeResponse(body=_valid_body()))
    with _patch_session(session):
        await GrokSignalProvider(api_key="k", model="x-ai/grok-4.1-fast").get_signal(snapshot)
    assert session.calls[0][1]["json"]["model"] == "x-ai/grok-4.1-fast"


def test_is_runtime_signal_provider() -> None:
    assert isinstance(GrokSignalProvider(api_key="k"), SignalProvider)

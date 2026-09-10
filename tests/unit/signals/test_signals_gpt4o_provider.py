"""Tests for GPT4oSignalProvider — HTTP mocked, no network."""

import asyncio
import json
from datetime import date
from decimal import Decimal
from unittest.mock import patch

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
from src.signals.providers.gpt4o import GPT4oSignalProvider

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
    def __init__(self, *, body: str, status: int = 200):
        self._body = body
        self.status = status

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def text(self) -> str:
        return self._body


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


async def test_valid_response_returns_signal(snapshot: MarketSnapshot) -> None:
    with _patch_session(_FakeSession(_FakeResponse(body=_valid_body("BEARISH", 3)))):
        resp = await GPT4oSignalProvider(api_key="k").get_signal(snapshot)
    assert isinstance(resp, SignalResponse)
    assert resp.direction is Direction.BEARISH
    assert resp.confidence == 3
    assert resp.entry_premium_low == Decimal("50")


async def test_http_429_raises_datafetcherror(snapshot: MarketSnapshot) -> None:
    with _patch_session(_FakeSession(_FakeResponse(body="{}", status=429))):
        with pytest.raises(DataFetchError, match="HTTP 429"):
            await GPT4oSignalProvider(api_key="k").get_signal(snapshot)


async def test_error_body_captured_in_datafetcherror(snapshot: MarketSnapshot) -> None:
    body = json.dumps({"error": {"message": "response_format not supported", "code": 400}})
    with _patch_session(_FakeSession(_FakeResponse(body=body, status=400))):
        with pytest.raises(DataFetchError, match="response_format not supported"):
            await GPT4oSignalProvider(api_key="k").get_signal(snapshot)


async def test_non_json_envelope_raises_datafetcherror(snapshot: MarketSnapshot) -> None:
    with _patch_session(_FakeSession(_FakeResponse(body="<html>Bad Gateway</html>"))):
        with pytest.raises(DataFetchError, match="non-JSON response body"):
            await GPT4oSignalProvider(api_key="k").get_signal(snapshot)


async def test_non_json_body_raises_datafetcherror(snapshot: MarketSnapshot) -> None:
    body = json.dumps({"choices": [{"message": {"content": "not json at all"}}]})
    with _patch_session(_FakeSession(_FakeResponse(body=body))):
        with pytest.raises(DataFetchError):
            await GPT4oSignalProvider(api_key="k").get_signal(snapshot)


async def test_timeout_raises_datafetcherror(snapshot: MarketSnapshot) -> None:
    with patch("aiohttp.ClientSession", side_effect=asyncio.TimeoutError):
        with pytest.raises(DataFetchError, match="timed out"):
            await GPT4oSignalProvider(api_key="k").get_signal(snapshot)


async def test_missing_key_raises_datafetcherror(snapshot: MarketSnapshot) -> None:
    content = json.dumps({"direction": "BULLISH"})  # missing confidence, strike, premiums
    body = json.dumps({"choices": [{"message": {"content": content}}]})
    with _patch_session(_FakeSession(_FakeResponse(body=body))):
        with pytest.raises(DataFetchError, match="could not parse"):
            await GPT4oSignalProvider(api_key="k").get_signal(snapshot)


async def test_payload_has_headroom_for_reasoning_models(snapshot: MarketSnapshot) -> None:
    session = _FakeSession(_FakeResponse(body=_valid_body()))
    with _patch_session(session):
        provider = GPT4oSignalProvider(api_key="k")
        await provider.get_signal(snapshot)
    assert session.calls[0][1]["json"]["max_tokens"] == 2048
    assert provider._timeout.total == 60.0


def test_provider_name_attribute() -> None:
    assert GPT4oSignalProvider(api_key="k").provider_name == "gpt4o"


def test_is_runtime_signal_provider() -> None:
    assert isinstance(GPT4oSignalProvider(api_key="k"), SignalProvider)


def _body_with_usage(usage: object) -> str:
    envelope = json.loads(_valid_body())
    envelope["usage"] = usage
    return json.dumps(envelope)


async def test_get_signal_parses_usage(snapshot: MarketSnapshot) -> None:
    body = _body_with_usage({"prompt_tokens": 1200, "completion_tokens": 40, "cost": 0.0031})
    session = _FakeSession(_FakeResponse(body=body))
    with _patch_session(session):
        resp = await GPT4oSignalProvider(api_key="k").get_signal(snapshot)
    assert resp.usage is not None
    assert resp.usage.prompt_tokens == 1200
    assert resp.usage.completion_tokens == 40
    assert resp.usage.cost_usd == Decimal("0.0031")
    assert session.calls[0][1]["json"]["usage"] == {"include": True}


async def test_get_signal_usage_absent_is_none(snapshot: MarketSnapshot) -> None:
    session = _FakeSession(_FakeResponse(body=_valid_body()))
    with _patch_session(session):
        resp = await GPT4oSignalProvider(api_key="k").get_signal(snapshot)
    assert resp.usage is None


async def test_get_signal_usage_malformed_is_none(snapshot: MarketSnapshot) -> None:
    session = _FakeSession(_FakeResponse(body=_body_with_usage({"cost": "not-a-number"})))
    with _patch_session(session):
        resp = await GPT4oSignalProvider(api_key="k").get_signal(snapshot)
    assert resp.usage is None
    assert resp.direction is Direction.BULLISH


async def test_get_signal_usage_non_dict_is_none(snapshot: MarketSnapshot) -> None:
    session = _FakeSession(_FakeResponse(body=_body_with_usage("unexpected-string")))
    with _patch_session(session):
        resp = await GPT4oSignalProvider(api_key="k").get_signal(snapshot)
    assert resp.usage is None
    assert resp.direction is Direction.BULLISH

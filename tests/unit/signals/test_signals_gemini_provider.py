"""Tests for GeminiSignalProvider — HTTP and SDK mocked, no network."""

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
from src.signals.providers.gemini import GeminiSignalProvider

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
        resp = await GeminiSignalProvider(api_key="k").get_signal(snapshot)
    assert isinstance(resp, SignalResponse)
    assert resp.direction is Direction.BEARISH
    assert resp.confidence == 3
    assert resp.provider == "gemini"
    url = session.calls[0][0][0]
    assert url == "https://openrouter.ai/api/v1/chat/completions"
    assert session.calls[0][1]["json"]["model"] == "google/gemini-2.0-flash"


def test_phase2_without_sdk_raises_import_error() -> None:
    with patch("src.signals.providers.gemini.genai", None):
        with pytest.raises(ImportError, match="google-generativeai not installed"):
            GeminiSignalProvider(api_key="k", use_openrouter=False)


class _FakeGenai:
    def __init__(self, text: str) -> None:
        self._text = text
        self.configured_key: str | None = None

    def configure(self, api_key: str) -> None:
        self.configured_key = api_key

    def GenerativeModel(self, model: str):  # noqa: N802 - mirrors SDK name
        text = self._text

        class _Model:
            def generate_content(self, prompt, tools=None):
                return type("_R", (), {"text": text})()

        return _Model()


async def test_phase2_sdk_happy_path_returns_signal(snapshot: MarketSnapshot) -> None:
    content = json.dumps(
        {
            "direction": "BULLISH",
            "confidence": 5,
            "recommended_strike": ATM,
            "entry_premium_low": 40,
            "entry_premium_high": 55,
            "key_reason": "global cues up",
            "key_risk": "vix spike",
        }
    )
    fake = _FakeGenai(content)
    with patch("src.signals.providers.gemini.genai", fake):
        provider = GeminiSignalProvider(api_key="gkey", use_openrouter=False)
        resp = await provider.get_signal(snapshot)
    assert isinstance(resp, SignalResponse)
    assert resp.direction is Direction.BULLISH
    assert resp.confidence == 5
    assert fake.configured_key == "gkey"


async def test_phase2_sdk_failure_raises_datafetcherror(snapshot: MarketSnapshot) -> None:
    fake = _FakeGenai("")

    def _boom(model: str):
        raise RuntimeError("sdk exploded")

    fake.GenerativeModel = _boom
    with patch("src.signals.providers.gemini.genai", fake):
        provider = GeminiSignalProvider(api_key="gkey", use_openrouter=False)
        with pytest.raises(DataFetchError, match="Google AI SDK call failed"):
            await provider.get_signal(snapshot)


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
            await GeminiSignalProvider(api_key="k").get_signal(snapshot)


async def test_non_json_body_raises_datafetcherror(snapshot: MarketSnapshot) -> None:
    body = json.dumps({"choices": [{"message": {"content": "not json at all"}}]})
    with _patch_session(_FakeSession(_FakeResponse(body=body))):
        with pytest.raises(DataFetchError, match="could not parse"):
            await GeminiSignalProvider(api_key="k").get_signal(snapshot)


async def test_timeout_raises_datafetcherror(snapshot: MarketSnapshot) -> None:
    with patch("aiohttp.ClientSession", side_effect=asyncio.TimeoutError):
        with pytest.raises(DataFetchError, match="timed out"):
            await GeminiSignalProvider(api_key="k").get_signal(snapshot)


def test_provider_name_attribute() -> None:
    assert GeminiSignalProvider(api_key="k").provider_name == "gemini"


def test_default_model_slug() -> None:
    assert GeminiSignalProvider(api_key="k")._model == "google/gemini-2.0-flash"


async def test_model_override_sent_in_payload(snapshot: MarketSnapshot) -> None:
    session = _FakeSession(_FakeResponse(body=_valid_body("BEARISH", 3)))
    with _patch_session(session):
        await GeminiSignalProvider(api_key="k", model="google/gemini-3.7-flash").get_signal(
            snapshot
        )
    assert session.calls[0][1]["json"]["model"] == "google/gemini-3.7-flash"


async def test_payload_has_headroom_for_reasoning_models(snapshot: MarketSnapshot) -> None:
    session = _FakeSession(_FakeResponse(body=_valid_body("BEARISH", 3)))
    with _patch_session(session):
        provider = GeminiSignalProvider(api_key="k")
        await provider.get_signal(snapshot)
    assert session.calls[0][1]["json"]["max_tokens"] == 2048
    assert provider._timeout.total == 60.0


def test_is_runtime_signal_provider() -> None:
    assert isinstance(GeminiSignalProvider(api_key="k"), SignalProvider)

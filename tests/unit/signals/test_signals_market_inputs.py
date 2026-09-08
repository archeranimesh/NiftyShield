"""Offline tests for :mod:`src.signals.market_inputs`.

No network, no real BOD file. The broker is a hand-built fake; ``requests.get``
is monkeypatched for the FII fetcher.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest

from src.client.exceptions import DataFetchError
from src.instruments.lookup import InstrumentLookup
from src.signals import market_inputs
from src.signals.market_inputs import (
    GIFT_NIFTY_KEY,
    fetch_fii_data,
    fetch_gift_nifty,
    fetch_usd_inr,
)


class _FakeBroker:
    """Minimal broker stub — only ``get_ltp`` is exercised."""

    def __init__(self, quotes: dict[str, Decimal]) -> None:
        self._quotes = quotes

    async def get_ltp(self, instruments: list[str]) -> dict[str, Decimal]:
        return {k: v for k, v in self._quotes.items() if k in instruments}


@pytest.fixture(autouse=True)
def _freeze_today(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin `dt.date.today()` in the module under test to 2026-09-08."""

    class _FixedDate(dt.date):
        @classmethod
        def today(cls) -> dt.date:
            return dt.date(2026, 9, 8)

    monkeypatch.setattr(market_inputs.dt, "date", _FixedDate)


def _fut(key: str, symbol: str, expiry: str) -> dict[str, str]:
    return {
        "instrument_key": key,
        "trading_symbol": symbol,
        "segment": "NCD_FO",
        "instrument_type": "FUT",
        "underlying_symbol": "USDINR",
        "name": "USDINR",
        "expiry": expiry,
    }


def _usdinr_lookup() -> InstrumentLookup:
    """Two USDINR futures: a mid-month weekly and the Sep month-end contract."""
    return InstrumentLookup(
        instruments=[
            _fut("NCD_FO|WEEKLY", "USDINR FUT 18 SEP 26", "2026-09-18"),
            _fut("NCD_FO|MONTHLY", "USDINR FUT 29 SEP 26", "2026-09-29"),
        ]
    )


# ── fetch_gift_nifty ──────────────────────────────────────────────────────────


async def test_fetch_gift_nifty_happy_path() -> None:
    broker = _FakeBroker({GIFT_NIFTY_KEY: Decimal("23791.0")})
    assert await fetch_gift_nifty(broker) == Decimal("23791.0")


async def test_fetch_gift_nifty_missing_key_raises() -> None:
    with pytest.raises(DataFetchError, match="gift_nifty"):
        await fetch_gift_nifty(_FakeBroker({}))


# ── fetch_usd_inr ─────────────────────────────────────────────────────────────


async def test_fetch_usd_inr_picks_month_end_contract() -> None:
    broker = _FakeBroker({"NCD_FO|MONTHLY": Decimal("94.57"), "NCD_FO|WEEKLY": Decimal("0.0")})
    assert await fetch_usd_inr(broker, lookup=_usdinr_lookup()) == Decimal("94.57")


async def test_fetch_usd_inr_rolls_to_next_month_when_earliest_expired() -> None:
    lookup = InstrumentLookup(
        instruments=[
            _fut("NCD_FO|SEP", "USDINR FUT 01 SEP 26", "2026-09-01"),  # expired
            _fut("NCD_FO|OCT", "USDINR FUT 29 OCT 26", "2026-10-29"),
        ]
    )
    broker = _FakeBroker({"NCD_FO|OCT": Decimal("94.80")})
    assert await fetch_usd_inr(broker, lookup=lookup) == Decimal("94.80")


async def test_fetch_usd_inr_no_contract_raises() -> None:
    empty = InstrumentLookup(instruments=[])
    with pytest.raises(DataFetchError, match="no live monthly"):
        await fetch_usd_inr(_FakeBroker({}), lookup=empty)


async def test_fetch_usd_inr_zero_ltp_raises() -> None:
    broker = _FakeBroker({"NCD_FO|MONTHLY": Decimal("0")})
    with pytest.raises(DataFetchError, match="usd_inr"):
        await fetch_usd_inr(broker, lookup=_usdinr_lookup())


# ── fetch_fii_data ────────────────────────────────────────────────────────────

_FII_JSON = [
    {
        "category": "DII",
        "date": "07-Sep-2026",
        "buyValue": "13154.13",
        "sellValue": "12587.37",
        "netValue": "566.76",
    },
    {
        "category": "FII/FPI",
        "date": "07-Sep-2026",
        "buyValue": "9581.19",
        "sellValue": "9301.06",
        "netValue": "280.13",
    },
]


class _FakeResponse:
    def __init__(self, status_code: int, payload: object) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> object:
        return self._payload


async def test_fetch_fii_data_happy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        market_inputs.requests, "get", lambda *a, **k: _FakeResponse(200, _FII_JSON)
    )
    result = await fetch_fii_data(_FakeBroker({}))
    assert result.fii_cash_net_cr == Decimal("280.13")
    assert result.dii_cash_net_cr == Decimal("566.76")


async def test_fetch_fii_data_non_200_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(market_inputs.requests, "get", lambda *a, **k: _FakeResponse(503, None))
    with pytest.raises(DataFetchError, match="HTTP 503"):
        await fetch_fii_data(_FakeBroker({}))


async def test_fetch_fii_data_missing_category_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        market_inputs.requests,
        "get",
        lambda *a, **k: _FakeResponse(200, [_FII_JSON[0]]),  # DII only
    )
    with pytest.raises(DataFetchError, match="missing a category"):
        await fetch_fii_data(_FakeBroker({}))

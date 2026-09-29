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


async def test_fetch_usd_inr_picks_off_cadence_monthly_not_bucket_max() -> None:
    """Monthly (28-Oct, Wed) breaks the Friday weekly cadence; a trailing
    weekly (30-Oct, Fri) is a later bucket max but must lose to the monthly.
    Reproduces the 2026-09-29 NCD_FO|1420 incident."""
    lookup = InstrumentLookup(
        instruments=[
            _fut("NCD_FO|OCT01", "USDINR FUT 01 OCT 26", "2026-10-01"),
            _fut("NCD_FO|OCT09", "USDINR FUT 09 OCT 26", "2026-10-09"),
            _fut("NCD_FO|OCT16", "USDINR FUT 16 OCT 26", "2026-10-16"),
            _fut("NCD_FO|OCT23", "USDINR FUT 23 OCT 26", "2026-10-23"),
            # true monthly — off Friday cadence
            _fut("NCD_FO|OCT28", "USDINR FUT 28 OCT 26", "2026-10-28"),
            # trailing weekly, still Friday-anchored, illiquid
            _fut("NCD_FO|OCT30", "USDINR FUT 30 OCT 26", "2026-10-30"),
        ]
    )
    broker = _FakeBroker({"NCD_FO|OCT28": Decimal("94.90"), "NCD_FO|OCT30": Decimal("0.0")})
    assert await fetch_usd_inr(broker, lookup=lookup) == Decimal("94.90")


async def test_fetch_usd_inr_falls_back_to_bucket_max_when_monthly_on_anchor() -> None:
    """When the monthly happens to land on the weekly's own anchor weekday,
    every contract in the bucket shares one weekday and off_cadence is empty
    — the fallback to bucket-max must still resolve to the monthly (the
    latest Friday in the month)."""
    lookup = InstrumentLookup(
        instruments=[
            _fut("NCD_FO|F1", "USDINR FUT 02 OCT 26", "2026-10-02"),
            _fut("NCD_FO|F2", "USDINR FUT 09 OCT 26", "2026-10-09"),
            _fut("NCD_FO|F3", "USDINR FUT 16 OCT 26", "2026-10-16"),
            _fut("NCD_FO|F4", "USDINR FUT 23 OCT 26", "2026-10-23"),
            _fut("NCD_FO|F5", "USDINR FUT 30 OCT 26", "2026-10-30"),  # monthly, also Friday
        ]
    )
    broker = _FakeBroker({"NCD_FO|F5": Decimal("95.10")})
    assert await fetch_usd_inr(broker, lookup=lookup) == Decimal("95.10")


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

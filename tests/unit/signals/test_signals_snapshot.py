"""Offline tests for :mod:`src.signals.snapshot`.

No network, no real BOD file. The broker is a hand-built fake; the three
``market_inputs`` fetchers are monkeypatched on the module under test.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from src.client.exceptions import DataFetchError
from src.instruments.lookup import InstrumentLookup
from src.signals import snapshot
from src.signals.models import FIIData, MarketSnapshot, OptionChainSummary
from src.signals.snapshot import assemble_market_snapshot


class _FakeBroker:
    """Minimal broker stub exercising get_ltp / get_ohlc / get_historical_candles / get_option_chain."""

    def __init__(
        self, *, ltp=None, ohlc=None, historical_candles=None, chain=None, raise_on=None
    ) -> None:
        self._ltp = ltp or {}
        self._ohlc = ohlc or {}
        self._historical_candles = historical_candles or []
        self._chain = chain if chain is not None else []
        self._raise_on = raise_on

    async def get_ltp(self, instruments):
        if self._raise_on == "get_ltp":
            raise DataFetchError("ltp down")
        return {k: v for k, v in self._ltp.items() if k in instruments}

    async def get_ohlc(self, instruments, interval="1d"):
        return {k: v for k, v in self._ohlc.items() if k in instruments}

    async def get_historical_candles(self, params):
        return self._historical_candles

    async def get_option_chain(self, instrument, expiry):
        return self._chain


class _StubStore:
    def __init__(self, recent=None) -> None:
        self._recent = recent or []

    def get_recent_snapshots(self, n):
        return self._recent[:n]


def _nifty_expiry_lookup() -> InstrumentLookup:
    """One NIFTY monthly expiry (last Tuesday of Sep 2026)."""
    return InstrumentLookup(
        instruments=[
            {
                "instrument_key": "NSE_FO|CE1",
                "trading_symbol": "NIFTY 25000 CE",
                "segment": "NSE_FO",
                "instrument_type": "CE",
                "underlying_symbol": "NIFTY",
                "name": "NIFTY",
                "expiry": "2026-09-29",
            },
            {
                "instrument_key": "NSE_FO|PE1",
                "trading_symbol": "NIFTY 25000 PE",
                "segment": "NSE_FO",
                "instrument_type": "PE",
                "underlying_symbol": "NIFTY",
                "name": "NIFTY",
                "expiry": "2026-09-29",
            },
        ]
    )


def _leg(ltp: str, oi: int, iv: str) -> dict:
    return {
        "market_data": {"ltp": ltp, "bid_price": ltp, "ask_price": ltp, "oi": oi, "volume": 1},
        "option_greeks": {"iv": iv, "delta": "0.5"},
    }


def _raw_chain() -> list[dict]:
    """Three strikes around a 23800 spot with distinct call/put OI + IV."""
    rows = []
    for strike, coi, poi, civ, piv in (
        (23700, 100, 400, "12.0", "14.0"),
        (23800, 300, 300, "11.0", "11.0"),
        (23900, 500, 120, "13.0", "10.0"),
    ):
        rows.append(
            {
                "strike_price": strike,
                "underlying_spot_price": 23800,
                "expiry": "2026-09-29",
                "call_options": _leg("50", coi, civ),
                "put_options": _leg("48", poi, piv),
            }
        )
    return rows


@pytest.fixture
def _patch_market_inputs(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _gift(_broker):
        return Decimal("23850")

    async def _usd(_broker, *, lookup=None):
        return Decimal("94.5")

    async def _fii(_broker):
        return FIIData(fii_cash_net_cr=Decimal("-1200.5"), dii_cash_net_cr=Decimal("900.25"))

    monkeypatch.setattr(snapshot, "fetch_gift_nifty", _gift)
    monkeypatch.setattr(snapshot, "fetch_usd_inr", _usd)
    monkeypatch.setattr(snapshot, "fetch_fii_data", _fii)


@pytest.mark.asyncio
async def test_assemble_happy_path(_patch_market_inputs) -> None:
    broker = _FakeBroker(
        ltp={
            "NSE_INDEX|Nifty 50": Decimal("23779.15"),
            "NSE_INDEX|India VIX": Decimal("11.16"),
        },
        historical_candles=[["2026-08-25", 23800, 23850, 23700, 23760, 0, 0]],
        chain=_raw_chain(),
    )
    snap = await assemble_market_snapshot(
        broker,
        store=_StubStore(),
        trade_date=date(2026, 9, 8),
        lookup=_nifty_expiry_lookup(),
    )

    assert snap.nifty_spot == Decimal("23779.15")
    assert snap.india_vix == Decimal("11.16")
    assert (snap.prev_close, snap.prev_high, snap.prev_low) == (
        Decimal("23760"),
        Decimal("23850"),
        Decimal("23700"),
    )
    assert snap.gift_nifty == Decimal("23850")
    assert snap.usd_inr == Decimal("94.5")
    assert snap.fii.fii_cash_net_cr == Decimal("-1200.5")
    assert snap.monthly_expiry == date(2026, 9, 29)
    assert snap.vix_5d_trend == "flat"  # bootstrap: no history

    oc = snap.option_chain
    assert oc.atm_strike == 23800  # nearest to 23779.15
    assert oc.atm_iv == Decimal("11.0")
    # first OTM call IV (23800, 11.0) - first OTM put IV (23700, 14.0)
    assert oc.iv_skew == Decimal("-3.0")
    assert oc.pcr_total == Decimal("820") / Decimal("900")  # (400+300+120)/(100+300+500)
    assert oc.pcr_atm == Decimal("1")  # 300/300
    assert oc.top_call_oi[0].strike == 23900 and oc.top_call_oi[0].oi == 500
    assert oc.top_put_oi[0].strike == 23700 and oc.top_put_oi[0].oi == 400
    assert oc.top_call_oi[0].oi_change == 0


@pytest.mark.asyncio
async def test_vix_trend_rising(_patch_market_inputs) -> None:
    history = [
        _make_snap(vix)
        for vix in ("13", "12", "11", "10", "9")  # newest-first -> oldest->newest rising
    ]
    broker = _FakeBroker(
        ltp={
            "NSE_INDEX|Nifty 50": Decimal("23779.15"),
            "NSE_INDEX|India VIX": Decimal("11.16"),
        },
        historical_candles=[["2026-08-25", 1, 1, 1, 1, 0, 0]],
        chain=_raw_chain(),
    )
    snap = await assemble_market_snapshot(
        broker,
        store=_StubStore(history),
        trade_date=date(2026, 9, 8),
        lookup=_nifty_expiry_lookup(),
    )
    assert snap.vix_5d_trend == "rising"


@pytest.mark.asyncio
async def test_iv_skew_zero_when_one_otm_side_missing(_patch_market_inputs) -> None:
    """Exactly one OTM IV present -> iv_skew falls back to 0, not one-sided noise."""
    chain = _raw_chain()
    chain[2]["call_options"]["option_greeks"].pop("iv")  # 23900 CE (first OTM call) loses IV
    broker = _FakeBroker(
        ltp={
            "NSE_INDEX|Nifty 50": Decimal("23850"),  # ATM 23800, first OTM call 23900
            "NSE_INDEX|India VIX": Decimal("11.16"),
        },
        historical_candles=[["2026-08-25", 1, 1, 1, 1, 0, 0]],
        chain=chain,
    )
    snap = await assemble_market_snapshot(
        broker,
        store=_StubStore(),
        trade_date=date(2026, 9, 8),
        lookup=_nifty_expiry_lookup(),
    )
    assert snap.option_chain.iv_skew == Decimal("0")


@pytest.mark.asyncio
async def test_empty_option_chain_raises(_patch_market_inputs) -> None:
    broker = _FakeBroker(
        ltp={
            "NSE_INDEX|Nifty 50": Decimal("23779.15"),
            "NSE_INDEX|India VIX": Decimal("11.16"),
        },
        historical_candles=[["2026-08-25", 1, 1, 1, 1, 0, 0]],
        chain=[],
    )
    with pytest.raises(DataFetchError, match="no strikes"):
        await assemble_market_snapshot(
            broker,
            store=_StubStore(),
            trade_date=date(2026, 9, 8),
            lookup=_nifty_expiry_lookup(),
        )


@pytest.mark.asyncio
async def test_assemble_missing_nifty_spot_raises(_patch_market_inputs) -> None:
    broker = _FakeBroker(ltp={"NSE_INDEX|India VIX": Decimal("11.16")})
    with pytest.raises(DataFetchError, match="nifty_spot unavailable"):
        await assemble_market_snapshot(
            broker,
            store=_StubStore(),
            trade_date=date(2026, 9, 8),
            lookup=_nifty_expiry_lookup(),
        )


@pytest.mark.asyncio
async def test_assemble_broker_error_propagates(_patch_market_inputs) -> None:
    broker = _FakeBroker(raise_on="get_ltp")
    with pytest.raises(DataFetchError):
        await assemble_market_snapshot(
            broker,
            store=_StubStore(),
            trade_date=date(2026, 9, 8),
            lookup=_nifty_expiry_lookup(),
        )


@pytest.mark.asyncio
async def test_prev_ohlc_skips_todays_partial_candle(_patch_market_inputs) -> None:
    # candles[0] is dated on trade_date (a post-close re-run) — must fall through
    # to the prior session's row.
    broker = _FakeBroker(
        ltp={
            "NSE_INDEX|Nifty 50": Decimal("23779.15"),
            "NSE_INDEX|India VIX": Decimal("11.16"),
        },
        historical_candles=[
            ["2026-09-08T00:00:00+05:30", 23780, 23800, 23600, 23700, 0, 0],
            ["2026-09-05T00:00:00+05:30", 23800, 23850, 23700, 23760, 0, 0],
        ],
        chain=_raw_chain(),
    )
    snap = await assemble_market_snapshot(
        broker,
        store=_StubStore(),
        trade_date=date(2026, 9, 8),
        lookup=_nifty_expiry_lookup(),
    )
    assert (snap.prev_close, snap.prev_high, snap.prev_low) == (
        Decimal("23760"),
        Decimal("23850"),
        Decimal("23700"),
    )


@pytest.mark.asyncio
async def test_prev_ohlc_no_prior_session_raises(_patch_market_inputs) -> None:
    broker = _FakeBroker(
        ltp={
            "NSE_INDEX|Nifty 50": Decimal("23779.15"),
            "NSE_INDEX|India VIX": Decimal("11.16"),
        },
        historical_candles=[["2026-09-08T00:00:00+05:30", 1, 1, 1, 1, 0, 0]],
        chain=_raw_chain(),
    )
    with pytest.raises(DataFetchError, match="no prior session"):
        await assemble_market_snapshot(
            broker,
            store=_StubStore(),
            trade_date=date(2026, 9, 8),
            lookup=_nifty_expiry_lookup(),
        )


def _make_snap(vix: str) -> MarketSnapshot:
    return MarketSnapshot(
        trade_date=date(2026, 9, 1),
        nifty_spot=Decimal("23800"),
        prev_close=Decimal("23800"),
        prev_high=Decimal("23850"),
        prev_low=Decimal("23750"),
        gift_nifty=Decimal("23810"),
        india_vix=Decimal(vix),
        vix_5d_trend="flat",
        usd_inr=Decimal("94"),
        monthly_expiry=date(2026, 9, 29),
        option_chain=OptionChainSummary(
            atm_strike=23800,
            atm_iv=Decimal("11"),
            iv_skew=Decimal("0"),
            pcr_total=Decimal("1"),
            pcr_atm=Decimal("1"),
            top_call_oi=[],
            top_put_oi=[],
        ),
        fii=FIIData(fii_cash_net_cr=Decimal("0"), dii_cash_net_cr=Decimal("0")),
    )

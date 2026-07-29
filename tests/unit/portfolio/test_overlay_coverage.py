"""Tests for src.portfolio.overlay_coverage (S3r — query-time overlay coverage)."""

from datetime import date
from decimal import Decimal

import pytest

from src.models.portfolio import TradeAction
from src.paper.constants import STRATEGY_FUTURES, STRATEGY_OVERLAY, STRATEGY_PROXY, STRATEGY_SPOT
from src.paper.models import PaperPosition, PaperTrade
from src.portfolio.overlay_coverage import compute_overlay_coverage


class MockPaperStore:
    """Minimal PaperStore double — mirrors tests/unit/paper/test_track_snapshot.py's pattern."""

    def __init__(self, trades, positions):
        self._trades = trades
        self._positions = positions

    def get_trades(self, strategy_name):
        return [t for t in self._trades if t.strategy_name == strategy_name]

    def get_position(self, strategy_name, leg_role):
        for p in self._positions:
            if p.strategy_name == strategy_name and p.leg_role == leg_role:
                return p
        return PaperPosition(
            strategy_name=strategy_name,
            leg_role=leg_role,
            net_qty=0,
            avg_cost=Decimal("0"),
            avg_sell_price=Decimal("0"),
            instrument_key="",
        )


class MockInstrumentLookup:
    def __init__(self, instruments=None):
        self._instruments = instruments or {}

    def get_by_key(self, instrument_key):
        return self._instruments.get(instrument_key)


class MockBrokerClient:
    """Returns raw Upstox-shaped chain data per expiry, as get_option_chain does live.

    ``resolve_leg_delta`` (src.paper.track_snapshot) feeds this straight into
    ``parse_upstox_option_chain`` — the mock must speak that raw format, not a
    pre-parsed OptionChain, or it silently produces an empty chain.
    """

    def __init__(self, raw_chains_by_expiry=None):
        self._raw_chains_by_expiry = raw_chains_by_expiry or {}

    async def get_ltp(self, instrument_keys):
        return {}

    async def get_option_chain(self, underlying, expiry):
        return self._raw_chains_by_expiry.get(expiry, [])


def _raw_ce_strike(expiry_iso: str, strike: str, delta: str) -> list[dict]:
    """One-strike raw Upstox chain response with only a CE leg populated."""
    return [
        {
            "underlying_spot_price": "24000",
            "expiry": expiry_iso,
            "strike_price": strike,
            "call_options": {
                "market_data": {"ltp": "500", "bid_price": "495", "ask_price": "505"},
                "option_greeks": {
                    "delta": delta,
                    "gamma": "0",
                    "theta": "0",
                    "vega": "0",
                    "iv": "0",
                },
            },
        }
    ]


def _raw_pe_strike(expiry_iso: str, strike: str, delta: str) -> list[dict]:
    """One-strike raw Upstox chain response with only a PE leg populated."""
    return [
        {
            "underlying_spot_price": "24000",
            "expiry": expiry_iso,
            "strike_price": strike,
            "put_options": {
                "market_data": {"ltp": "50", "bid_price": "48", "ask_price": "52"},
                "option_greeks": {
                    "delta": delta,
                    "gamma": "0",
                    "theta": "0",
                    "vega": "0",
                    "iv": "0",
                },
            },
        }
    ]


def _proxy_instrument(strike: str) -> dict:
    return {"expiry": "2026-12-31", "strike_price": strike, "instrument_type": "CE"}


@pytest.mark.asyncio
async def test_coverage_spot_track_no_overlay():
    """Spot base leg open, no overlay legs anywhere — coverage is 0%, not undefined."""
    positions = [
        PaperPosition(
            strategy_name=STRATEGY_SPOT,
            leg_role="base_etf",
            net_qty=5735,
            avg_cost=Decimal("240"),
            avg_sell_price=Decimal("0"),
            instrument_key="NIFTYBEES",
        ),
    ]
    trades = [
        PaperTrade(
            strategy_name=STRATEGY_SPOT,
            leg_role="base_etf",
            instrument_key="NIFTYBEES",
            trade_date=date.today(),
            action=TradeAction.BUY,
            quantity=5735,
            price=Decimal("240"),
            notes="",
        )
    ]
    store = MockPaperStore(trades, positions)
    broker = MockBrokerClient()
    lookup = MockInstrumentLookup()

    result = await compute_overlay_coverage(store, broker, lookup, STRATEGY_SPOT, date.today())

    assert result.track_effective_units == Decimal("5735") * Decimal("0.92")
    assert result.overlay_effective_units == Decimal("0")
    assert result.coverage_pct == Decimal("0")


@pytest.mark.asyncio
async def test_coverage_undefined_when_track_has_no_open_base_position():
    """Flat base leg (net_qty=0) → coverage_pct is None, not zero — no exposure to cover."""
    store = MockPaperStore([], [])
    broker = MockBrokerClient()
    lookup = MockInstrumentLookup()

    result = await compute_overlay_coverage(store, broker, lookup, STRATEGY_FUTURES, date.today())

    assert result.track_effective_units == Decimal("0")
    assert result.coverage_pct is None


@pytest.mark.asyncio
async def test_coverage_futures_track_with_shared_overlay_pp():
    """Futures base + a PP leg in the shared overlay namespace — coverage computed from live delta."""
    positions = [
        PaperPosition(
            strategy_name=STRATEGY_FUTURES,
            leg_role="base_futures",
            net_qty=65,
            avg_cost=Decimal("24000"),
            avg_sell_price=Decimal("0"),
            instrument_key="NIFTY_FUT",
        ),
        PaperPosition(
            strategy_name=STRATEGY_OVERLAY,
            leg_role="overlay_pp",
            net_qty=65,
            avg_cost=Decimal("50"),
            avg_sell_price=Decimal("0"),
            instrument_key="NIFTY_PE_23500",
        ),
    ]
    trades = [
        PaperTrade(
            strategy_name=STRATEGY_FUTURES,
            leg_role="base_futures",
            instrument_key="NIFTY_FUT",
            trade_date=date.today(),
            action=TradeAction.BUY,
            quantity=65,
            price=Decimal("24000"),
            notes="",
        ),
        PaperTrade(
            strategy_name=STRATEGY_OVERLAY,
            leg_role="overlay_pp",
            instrument_key="NIFTY_PE_23500",
            trade_date=date.today(),
            action=TradeAction.BUY,
            quantity=65,
            price=Decimal("50"),
            notes="",
        ),
    ]
    store = MockPaperStore(trades, positions)
    broker = MockBrokerClient(
        raw_chains_by_expiry={
            "2026-12-31": _raw_pe_strike("2026-12-31", "23500", "-0.30"),
        }
    )
    lookup = MockInstrumentLookup(
        {
            "NIFTY_PE_23500": {
                "expiry": "2026-12-31",
                "strike_price": "23500",
                "instrument_type": "PE",
            }
        }
    )

    result = await compute_overlay_coverage(store, broker, lookup, STRATEGY_FUTURES, date.today())

    # Futures base: 65 units * delta 1.0 = 65
    assert result.track_effective_units == Decimal("65")
    # Overlay PP: 65 units * delta -0.30 = -19.5
    assert result.overlay_effective_units == Decimal("-19.5")
    assert result.coverage_pct == (Decimal("-19.5") / Decimal("65")) * Decimal("100")


@pytest.mark.asyncio
async def test_coverage_proxy_track_delta_drift_recalculates_live():
    """Proxy DITM call delta drifting from ~0.95 toward ~0.7 — coverage must use the live value.

    Guards against a regression where entry-time delta gets cached/assumed instead
    of re-resolved from the current chain snapshot (mandated by stories.md S3r).
    """
    positions = [
        PaperPosition(
            strategy_name=STRATEGY_PROXY,
            leg_role="base_ditm_call",
            net_qty=65,
            avg_cost=Decimal("2000"),
            avg_sell_price=Decimal("0"),
            instrument_key="NIFTY_CE_22000",
        ),
    ]
    trades = [
        PaperTrade(
            strategy_name=STRATEGY_PROXY,
            leg_role="base_ditm_call",
            instrument_key="NIFTY_CE_22000",
            trade_date=date.today(),
            action=TradeAction.BUY,
            quantity=65,
            price=Decimal("2000"),
            notes="",
        ),
    ]
    lookup = MockInstrumentLookup({"NIFTY_CE_22000": _proxy_instrument("22000")})
    store = MockPaperStore(trades, positions)

    # Entry-time delta was ~0.95 (deep ITM); spot has since fallen and the same
    # strike's live delta has drifted to ~0.70. Only the live chain value should
    # be used — never a stale/entry-time figure.
    broker_now = MockBrokerClient(
        raw_chains_by_expiry={"2026-12-31": _raw_ce_strike("2026-12-31", "22000", "0.70")}
    )
    result_now = await compute_overlay_coverage(
        store, broker_now, lookup, STRATEGY_PROXY, date.today()
    )
    assert result_now.track_effective_units == Decimal("65") * Decimal("0.70")

    broker_earlier = MockBrokerClient(
        raw_chains_by_expiry={"2026-12-31": _raw_ce_strike("2026-12-31", "22000", "0.95")}
    )
    result_earlier = await compute_overlay_coverage(
        store, broker_earlier, lookup, STRATEGY_PROXY, date.today()
    )
    assert result_earlier.track_effective_units == Decimal("65") * Decimal("0.95")
    assert result_now.track_effective_units != result_earlier.track_effective_units


@pytest.mark.asyncio
async def test_coverage_unknown_track_namespace_raises_keyerror():
    """A caller bug (unknown track name) must surface loudly, not silently default."""
    store = MockPaperStore([], [])
    broker = MockBrokerClient()
    lookup = MockInstrumentLookup()

    with pytest.raises(KeyError):
        await compute_overlay_coverage(
            store, broker, lookup, "paper_not_a_real_track", date.today()
        )

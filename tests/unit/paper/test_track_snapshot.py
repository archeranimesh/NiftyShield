"""Tests for track snapshot reporter."""

import logging
from datetime import date
from decimal import Decimal

import pytest

from src.models.portfolio import TradeAction
from src.paper.models import PaperPosition, PaperTrade
from src.paper.track_snapshot import _compute_realized_pnl_by_leg, generate_track_snapshot


class MockPaperStore:
    def __init__(self, trades, positions, snapshots):
        self._trades = trades
        self._positions = positions
        self._snapshots = snapshots

    def get_trades(self, strategy_name):
        return [t for t in self._trades if t.strategy_name == strategy_name]

    def get_position(self, strategy_name, leg_role):
        for p in self._positions:
            if p.strategy_name == strategy_name and p.leg_role == leg_role:
                return p
        return PaperPosition(strategy_name, leg_role, "", 0, Decimal("0"), Decimal("0"))

    def get_nav_snapshots(self, strategy_name):
        return [s for s in self._snapshots if s.strategy_name == strategy_name]


class MockBrokerClient:
    async def get_ltp(self, instrument_keys: list[str]) -> dict[str, Decimal]:
        return {
            "NIFTYBEES": Decimal("250.0"),
            "NIFTY_FUT": Decimal("24000.0"),
            "NIFTY_OPT": Decimal("100.0"),
        }


class MockInstrumentLookup:
    def get_by_key(self, instrument_key: str):
        return None


@pytest.mark.asyncio
async def test_generate_track_snapshot_empty():
    store = MockPaperStore([], [], [])
    broker = MockBrokerClient()
    lookup = MockInstrumentLookup()

    snap = await generate_track_snapshot(
        store, broker, lookup, "paper_nifty_spot", Decimal("24000"), Decimal("10000"), date.today()
    )

    assert snap.pnl.net_pnl == Decimal("0")
    assert snap.greeks.net_delta == Decimal("0")


@pytest.mark.asyncio
async def test_generate_track_snapshot_base_etf():
    trades = [
        PaperTrade(
            strategy_name="paper_nifty_spot",
            leg_role="base_etf",
            instrument_key="NIFTYBEES",
            trade_date=date.today(),
            action=TradeAction.BUY,
            quantity=100,
            price=Decimal("240.0"),
            notes="",
        )
    ]
    positions = [
        PaperPosition(
            strategy_name="paper_nifty_spot",
            leg_role="base_etf",
            instrument_key="NIFTYBEES",
            net_qty=100,
            avg_cost=Decimal("240.0"),
            avg_sell_price=Decimal("0"),
        )
    ]

    store = MockPaperStore(trades, positions, [])
    broker = MockBrokerClient()
    lookup = MockInstrumentLookup()

    snap = await generate_track_snapshot(
        store, broker, lookup, "paper_nifty_spot", Decimal("24000"), Decimal("100000"), date.today()
    )

    # PnL = (250 - 240) * 100 = 1000
    assert snap.pnl.base_pnl == Decimal("1000")
    assert snap.pnl.net_pnl == Decimal("1000")

    # Delta = 0.92 * 100 = 92.0
    assert snap.greeks.net_delta == Decimal("92.0")

    # Return on NEE = 1000 / 100000 = 1.0%
    assert snap.return_on_nee == Decimal("1.0")


@pytest.mark.asyncio
async def test_overlay_legs_under_a_track_are_ignored() -> None:
    """BUG-028 (2026-08-10): a track's own trades/positions may still carry a
    leftover ``overlay_*``-role row (pre-S2r, not yet closed/rolled off), but
    ``generate_track_snapshot`` must not attribute it to this track's P&L or
    Greeks any more — overlay legs are the independent ``STRATEGY_OVERLAY``
    book's responsibility now (see
    ``scripts/strategies/three_track/paper_3track_snapshot.py``'s standalone
    overlay pipeline). Only the base leg counts.
    """
    trades = [
        PaperTrade(
            strategy_name="paper_nifty_spot",
            leg_role="base_etf",
            instrument_key="NIFTYBEES",
            trade_date=date(2026, 6, 1),
            action=TradeAction.BUY,
            quantity=100,
            price=Decimal("240.0"),
            notes="",
        ),
        # Leftover overlay_cc row under this track's own strategy_name — must
        # be ignored entirely, not folded into base_pnl/net_pnl/Greeks.
        PaperTrade(
            strategy_name="paper_nifty_spot",
            leg_role="overlay_cc",
            instrument_key="NIFTY_OPT",
            trade_date=date(2026, 6, 1),
            action=TradeAction.SELL,
            quantity=1,
            price=Decimal("100.0"),
            notes="",
        ),
    ]
    positions = [
        PaperPosition(
            strategy_name="paper_nifty_spot",
            leg_role="base_etf",
            instrument_key="NIFTYBEES",
            net_qty=100,
            avg_cost=Decimal("240.0"),
            avg_sell_price=Decimal("0"),
        ),
        PaperPosition(
            strategy_name="paper_nifty_spot",
            leg_role="overlay_cc",
            instrument_key="NIFTY_OPT",
            net_qty=-1,
            avg_cost=Decimal("0"),
            avg_sell_price=Decimal("100.0"),
        ),
    ]

    store = MockPaperStore(trades, positions, [])
    broker = MockBrokerClient()
    lookup = MockInstrumentLookup()

    snap = await generate_track_snapshot(
        store, broker, lookup, "paper_nifty_spot", Decimal("24000"), Decimal("100000"), date.today()
    )

    # base_pnl = (250 - 240) * 100 = 1000; the overlay_cc leg contributes
    # nothing — pre-fix this would have added its P&L to net_pnl.
    assert snap.pnl.base_pnl == Decimal("1000")
    assert snap.pnl.net_pnl == Decimal("1000")
    # No overlay attribute survives on TrackPnL at all (BUG-028 dataclass change).
    assert not hasattr(snap.pnl, "overlay_pnls")
    assert not hasattr(snap.pnl, "raw_overlay_pnls")
    # Greeks reflect only the base ETF leg (fixed beta), never the overlay short.
    assert snap.greeks.net_delta == Decimal("92.0")


@pytest.mark.asyncio
async def test_track_with_only_leftover_overlay_legs_reports_zero() -> None:
    """Edge case: a track whose only positions are leftover overlay_* rows
    (no base leg at all — e.g. fully rolled-off/legacy data) must report a
    flat zero snapshot, not attempt to resolve overlay Greeks/P&L for it.
    """
    trades = [
        PaperTrade(
            strategy_name="paper_nifty_spot",
            leg_role="overlay_cc",
            instrument_key="NIFTY_OPT",
            trade_date=date(2026, 6, 1),
            action=TradeAction.SELL,
            quantity=2,
            price=Decimal("50.0"),
            notes="",
        ),
    ]
    positions = [
        PaperPosition(
            strategy_name="paper_nifty_spot",
            leg_role="overlay_cc",
            instrument_key="NIFTY_OPT",
            net_qty=-2,
            avg_cost=Decimal("0"),
            avg_sell_price=Decimal("50.0"),
        ),
    ]
    store = MockPaperStore(trades, positions, [])
    broker = MockBrokerClient()
    lookup = MockInstrumentLookup()

    snap = await generate_track_snapshot(
        store, broker, lookup, "paper_nifty_spot", Decimal("24000"), Decimal("100000"), date.today()
    )

    assert snap.pnl.base_pnl == Decimal("0")
    assert snap.pnl.net_pnl == Decimal("0")
    assert snap.greeks.net_delta == Decimal("0")


def test_compute_realized_pnl_by_leg():
    trades = [
        PaperTrade(
            strategy_name="paper_strat",
            leg_role="base",
            instrument_key="A",
            trade_date=date(2023, 1, 1),
            action=TradeAction.BUY,
            quantity=100,
            price=Decimal("100"),
            notes="",
        ),
        PaperTrade(
            strategy_name="paper_strat",
            leg_role="base",
            instrument_key="A",
            trade_date=date(2023, 1, 2),
            action=TradeAction.SELL,
            quantity=50,
            price=Decimal("120"),
            notes="",
        ),
        PaperTrade(
            strategy_name="paper_strat",
            leg_role="overlay",
            instrument_key="B",
            trade_date=date(2023, 1, 1),
            action=TradeAction.SELL,
            quantity=50,
            price=Decimal("50"),
            notes="",
        ),
        PaperTrade(
            strategy_name="paper_strat",
            leg_role="overlay",
            instrument_key="B",
            trade_date=date(2023, 1, 2),
            action=TradeAction.BUY,
            quantity=50,
            price=Decimal("30"),
            notes="",
        ),
    ]

    store = MockPaperStore(trades, [], [])
    realized = _compute_realized_pnl_by_leg(store, "paper_strat")

    # base: buy 100 @ 100, sell 50 @ 120 -> closed 50. realized = (120 - 100) * 50 = 1000
    assert realized["base"] == Decimal("1000")
    # overlay: sell 50 @ 50, buy 50 @ 30 -> closed 50. realized = (50 - 30) * 50 = 1000
    assert realized["overlay"] == Decimal("1000")


@pytest.mark.asyncio
async def test_total_pnl_invariant_holds_with_base_leg_only() -> None:
    """total_unrealized + total_realized must equal net_pnl.

    BUG-028 (2026-08-10) superseded the SNAP-5 CC/collar-dedup regression
    guard this test used to cover: overlay legs no longer enter this
    computation at all (see test_overlay_legs_under_a_track_are_ignored),
    so the dedup-vs-total-drift failure mode this test guarded is now
    structurally impossible here. Kept as a plain base-leg invariant check.
    """
    trades = [
        PaperTrade(
            strategy_name="paper_nifty_spot",
            leg_role="base_etf",
            instrument_key="NIFTYBEES",
            trade_date=date(2026, 6, 1),
            action=TradeAction.BUY,
            quantity=100,
            price=Decimal("240.0"),
            notes="",
        ),
    ]
    positions = [
        PaperPosition(
            strategy_name="paper_nifty_spot",
            leg_role="base_etf",
            instrument_key="NIFTYBEES",
            net_qty=100,
            avg_cost=Decimal("240.0"),
            avg_sell_price=Decimal("0"),
        ),
    ]

    store = MockPaperStore(trades, positions, [])
    broker = MockBrokerClient()
    lookup = MockInstrumentLookup()

    snap = await generate_track_snapshot(
        store, broker, lookup, "paper_nifty_spot", Decimal("24000"), Decimal("100000"), date.today()
    )

    assert snap.pnl.net_pnl == Decimal("1000")
    assert snap.pnl.unrealized_pnl + snap.pnl.realized_pnl == snap.pnl.net_pnl
    assert snap.pnl.unrealized_pnl == Decimal("1000")
    assert snap.pnl.realized_pnl == Decimal("0")


# ---------------------------------------------------------------------------
# P1-2: None LTP guard — expired instrument must not produce notional loss
# ---------------------------------------------------------------------------


class _BrokerNoPrice:
    """Simulates an expired instrument: get_ltp returns an empty dict (key absent)."""

    async def get_ltp(self, keys: list[str]) -> dict[str, Decimal]:
        return {}

    async def get_option_chain(self, underlying: str, expiry) -> list:
        return []


@pytest.mark.asyncio
async def test_none_ltp_skips_mtm_and_logs_warning(caplog: pytest.LogCaptureFixture) -> None:
    """When get_ltp returns no price for a base leg (expired instrument),
    unrealized P&L must be 0 and a WARNING must be logged — not a full notional loss.

    Regression guard for P1-1 (2026-05-27): May futures expiry propagated
    ``(0 - avg_cost) * qty`` as a ₹24 000 loss because the absent key fell
    back to the default 0.0 in prices.get().
    """
    trades = [
        PaperTrade(
            strategy_name="paper_nifty_futures",
            leg_role="base_futures",
            instrument_key="NSE_FO|EXPIRED_FUT",
            trade_date=date(2026, 5, 1),
            action=TradeAction.BUY,
            quantity=1,
            price=Decimal("24000.0"),
            notes="",
        )
    ]
    positions = [
        PaperPosition(
            strategy_name="paper_nifty_futures",
            leg_role="base_futures",
            instrument_key="NSE_FO|EXPIRED_FUT",
            net_qty=1,
            avg_cost=Decimal("24000.0"),
            avg_sell_price=Decimal("0"),
        )
    ]

    store = MockPaperStore(trades, positions, [])
    broker = _BrokerNoPrice()
    lookup = MockInstrumentLookup()

    with caplog.at_level(logging.WARNING, logger="src.paper.track_snapshot"):
        snap = await generate_track_snapshot(
            store,
            broker,
            lookup,
            "paper_nifty_futures",
            Decimal("24000"),
            Decimal("100000"),
            date(2026, 5, 28),
        )

    # Must not propagate a notional loss — unrealized is 0 when LTP is unavailable
    assert snap.pnl.base_pnl == Decimal("0"), (
        f"Expected base_pnl=0 for expired leg, got {snap.pnl.base_pnl}"
    )
    assert snap.pnl.net_pnl == Decimal("0")
    # WARNING must be logged
    assert any("LTP unavailable" in r.message for r in caplog.records), (
        "Expected a WARNING about unavailable LTP — none found"
    )


@pytest.mark.asyncio
async def test_none_ltp_does_not_suppress_realized_pnl(caplog: pytest.LogCaptureFixture) -> None:
    """Realized P&L from prior closes must still be reported even when the
    current LTP is unavailable (e.g. expired but partially closed earlier).
    """
    # One BUY trade + one partial SELL already recorded (realized gain)
    trades = [
        PaperTrade(
            strategy_name="paper_nifty_futures",
            leg_role="base_futures",
            instrument_key="NSE_FO|EXPIRED_FUT",
            trade_date=date(2026, 5, 1),
            action=TradeAction.BUY,
            quantity=2,
            price=Decimal("24000.0"),
            notes="",
        ),
        PaperTrade(
            strategy_name="paper_nifty_futures",
            leg_role="base_futures",
            instrument_key="NSE_FO|EXPIRED_FUT",
            trade_date=date(2026, 5, 20),
            action=TradeAction.SELL,
            quantity=1,
            price=Decimal("24500.0"),
            notes="",
        ),
    ]
    # Remaining open qty = 1
    positions = [
        PaperPosition(
            strategy_name="paper_nifty_futures",
            leg_role="base_futures",
            instrument_key="NSE_FO|EXPIRED_FUT",
            net_qty=1,
            avg_cost=Decimal("24000.0"),
            avg_sell_price=Decimal("24500.0"),
        )
    ]

    store = MockPaperStore(trades, positions, [])
    broker = _BrokerNoPrice()
    lookup = MockInstrumentLookup()

    with caplog.at_level(logging.WARNING, logger="src.paper.track_snapshot"):
        snap = await generate_track_snapshot(
            store,
            broker,
            lookup,
            "paper_nifty_futures",
            Decimal("24000"),
            Decimal("100000"),
            date(2026, 5, 28),
        )

    # realized = (24500 - 24000) * 1 = 500; unrealized = 0 (LTP unavailable)
    assert snap.pnl.base_pnl == Decimal("500")
    assert snap.pnl.net_pnl == Decimal("500")
    assert any("LTP unavailable" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# BUG-028: collar legs (or any overlay_*) under a track are ignored outright
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_track_snapshot_ignores_collar_legs_under_a_track() -> None:
    """A track carrying leftover overlay_collar_call/overlay_collar_put rows
    must not surface them anywhere on TrackPnL — collar P&L is the standalone
    ``STRATEGY_OVERLAY`` book's responsibility since S2r/BUG-028, not a
    track's. Supersedes the old S7 raw_overlay_pnls exposure test, which
    covered the now-removed per-track overlay discovery/persistence path.
    """
    trades = [
        PaperTrade(
            strategy_name="paper_nifty_spot",
            leg_role="overlay_collar_call",
            instrument_key="NIFTY_CALL",
            trade_date=date(2026, 6, 1),
            action=TradeAction.SELL,
            quantity=1,
            price=Decimal("50.0"),
            notes="",
        ),
        PaperTrade(
            strategy_name="paper_nifty_spot",
            leg_role="overlay_collar_put",
            instrument_key="NIFTY_PUT",
            trade_date=date(2026, 6, 1),
            action=TradeAction.BUY,
            quantity=1,
            price=Decimal("40.0"),
            notes="",
        ),
    ]
    positions = [
        PaperPosition(
            strategy_name="paper_nifty_spot",
            leg_role="overlay_collar_call",
            instrument_key="NIFTY_CALL",
            net_qty=-1,
            avg_cost=Decimal("0"),
            avg_sell_price=Decimal("50.0"),
        ),
        PaperPosition(
            strategy_name="paper_nifty_spot",
            leg_role="overlay_collar_put",
            instrument_key="NIFTY_PUT",
            net_qty=1,
            avg_cost=Decimal("40.0"),
            avg_sell_price=Decimal("0"),
        ),
    ]

    store = MockPaperStore(trades, positions, [])
    broker = MockBrokerClient()
    lookup = MockInstrumentLookup()

    snap = await generate_track_snapshot(
        store, broker, lookup, "paper_nifty_spot", Decimal("24000"), Decimal("100000"), date.today()
    )

    assert snap.pnl.base_pnl == Decimal("0")
    assert snap.pnl.net_pnl == Decimal("0")
    assert not hasattr(snap.pnl, "overlay_pnls")
    assert not hasattr(snap.pnl, "raw_overlay_pnls")

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
async def test_closed_overlay_leg_included_in_snapshot() -> None:
    """Closed overlay leg (net_qty == 0) must contribute realized P&L to overlay_pnls.

    Regression guard for RPT-1: prior to the second-pass fix, a fully closed
    CC/PP/Collar leg was invisible in overlay_pnls — net_pnl showed base only.
    """
    trades = [
        # Base leg: open ETF position
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
        # Overlay CC: opened (SELL) and closed (BUY) — net_qty == 0
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
        PaperTrade(
            strategy_name="paper_nifty_spot",
            leg_role="overlay_cc",
            instrument_key="NIFTY_OPT",
            trade_date=date(2026, 6, 10),
            action=TradeAction.BUY,
            quantity=1,
            price=Decimal("30.0"),
            notes="",
        ),
    ]
    positions = [
        # base_etf open
        PaperPosition(
            strategy_name="paper_nifty_spot",
            leg_role="base_etf",
            instrument_key="NIFTYBEES",
            net_qty=100,
            avg_cost=Decimal("240.0"),
            avg_sell_price=Decimal("0"),
        ),
        # overlay_cc fully closed — net_qty == 0, must not enter open_positions loop
        PaperPosition(
            strategy_name="paper_nifty_spot",
            leg_role="overlay_cc",
            instrument_key="NIFTY_OPT",
            net_qty=0,
            avg_cost=Decimal("30.0"),
            avg_sell_price=Decimal("100.0"),
        ),
    ]

    store = MockPaperStore(trades, positions, [])
    broker = MockBrokerClient()
    lookup = MockInstrumentLookup()

    snap = await generate_track_snapshot(
        store, broker, lookup, "paper_nifty_spot", Decimal("24000"), Decimal("100000"), date.today()
    )

    # overlay_cc realized = (100 - 30) * 1 = 70; normalized to "cc" by _normalize_overlay_pnls
    assert "cc" in snap.pnl.overlay_pnls
    assert snap.pnl.overlay_pnls["cc"] == Decimal("70")
    # base_pnl = (250 - 240) * 100 = 1000; net_pnl = 1000 + 70 = 1070
    assert snap.pnl.base_pnl == Decimal("1000")
    assert snap.pnl.net_pnl == Decimal("1070")


@pytest.mark.asyncio
async def test_all_closed_overlay_no_open_positions() -> None:
    """Track with only closed overlay legs (base also closed) must return their
    realized P&L — not zero — in overlay_pnls.

    Edge case: open_positions is empty so the main loop does nothing, but
    the second pass must still pick up closed overlay realized P&L.
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
        PaperTrade(
            strategy_name="paper_nifty_spot",
            leg_role="overlay_cc",
            instrument_key="NIFTY_OPT",
            trade_date=date(2026, 6, 10),
            action=TradeAction.BUY,
            quantity=2,
            price=Decimal("20.0"),
            notes="",
        ),
    ]
    # Explicit flat position — net_qty=0 so it must NOT enter open_positions loop
    positions = [
        PaperPosition(
            strategy_name="paper_nifty_spot",
            leg_role="overlay_cc",
            instrument_key="NIFTY_OPT",
            net_qty=0,
            avg_cost=Decimal("20.0"),
            avg_sell_price=Decimal("50.0"),
        ),
    ]
    store = MockPaperStore(trades, positions, [])
    broker = MockBrokerClient()
    lookup = MockInstrumentLookup()

    snap = await generate_track_snapshot(
        store, broker, lookup, "paper_nifty_spot", Decimal("24000"), Decimal("100000"), date.today()
    )

    # realized = (50 - 20) * 2 = 60
    assert snap.pnl.overlay_pnls.get("cc") == Decimal("60")  # normalized from overlay_cc
    assert snap.pnl.net_pnl == Decimal("60")


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
# S7: raw (pre-normalization) overlay leg_role exposure for persistence
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_track_snapshot_exposes_raw_overlay_leg_roles() -> None:
    """pnl.raw_overlay_pnls must carry the real leg_role keys (overlay_collar_call/
    overlay_collar_put) even though pnl.overlay_pnls collapses them into "collar"
    for display. _save_leg_snapshots() needs the real keys to call
    store.get_position() correctly — persisting off the collapsed label was the
    S7 bug (2026-07-28): overlay_ltp was always None because "collar"/"cc"/"pp"
    are never real leg_role values in paper_trades.
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

    # Display view: collapsed to a single merged "collar" label.
    assert set(snap.pnl.overlay_pnls) == {"collar"}
    # Persistence view: both real leg_roles must survive, uncollapsed.
    assert set(snap.pnl.raw_overlay_pnls) == {"overlay_collar_call", "overlay_collar_put"}

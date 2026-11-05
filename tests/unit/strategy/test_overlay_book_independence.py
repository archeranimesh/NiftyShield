"""YV-1: the monthly and yearly overlay books never block or mix each other.

Each test seeds one book through the real ``PaperStore`` (temp SQLite) and asserts the other
book's consumers see nothing, then repeats in the opposite direction. Per-consumer unit
coverage lives in ``tests/unit/paper/test_yearly_namespace_read_paths.py`` and
``test_overlay_entry.py``; this file asserts the cross-book contract end to end.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from scripts.strategies.three_track.paper_3track_overlay_entry import (
    _has_open_overlay_leg,
    _query_open_call_role,
)
from src.models.portfolio import TradeAction
from src.paper.constants import (
    STRATEGY_OVERLAY,
    STRATEGY_OVERLAY_YEARLY_CC,
    STRATEGY_OVERLAY_YEARLY_COLLAR,
    STRATEGY_OVERLAY_YEARLY_PP,
    STRATEGY_SPOT,
)
from src.paper.models import ExitSignal, OverlayPnLSnapshot, PaperTrade
from src.paper.store import PaperStore
from src.risk.collateral_gate import check_collateral_capacity

_LOT = 65
_D = date(2026, 11, 3)
_CALL_KEY = "NSE_FO|NIFTY26DEC24500CE"
_YEARLY_CC_COLLAR = (STRATEGY_OVERLAY_YEARLY_CC, STRATEGY_OVERLAY_YEARLY_COLLAR)

# (monthly ledger, yearly ledger, leg role, entry action)
_PAIRS = [
    (STRATEGY_OVERLAY, STRATEGY_OVERLAY_YEARLY_CC, "overlay_cc", TradeAction.SELL),
    (STRATEGY_OVERLAY, STRATEGY_OVERLAY_YEARLY_PP, "overlay_pp", TradeAction.BUY),
    (STRATEGY_OVERLAY, STRATEGY_OVERLAY_YEARLY_COLLAR, "overlay_collar_call", TradeAction.SELL),
]
_PAIR_IDS = ["cc", "pp", "collar"]


@pytest.fixture
def store(tmp_path: Path) -> PaperStore:
    """Fresh temp-SQLite ``PaperStore``."""
    return PaperStore(tmp_path / "independence.db")


def _open(
    store: PaperStore,
    strategy: str,
    role: str,
    key: str,
    action: TradeAction = TradeAction.SELL,
    qty: int = _LOT,
) -> None:
    """Record one opening paper trade in *strategy*'s ledger."""
    store.record_trade(
        PaperTrade(
            strategy_name=strategy,
            leg_role=role,
            instrument_key=key,
            trade_date=_D,
            action=action,
            quantity=qty,
            price=Decimal("100.00"),
        )
    )


def _exit_event(store: PaperStore, strategy: str, leg: str) -> int:
    """Create one OPEN exit event for *strategy* and return its id."""
    return store.create_exit_event(
        strategy_name=strategy,
        leg_name=leg,
        trade_id="1",
        event_time=datetime(2026, 11, 3, 10, 0),
        detected_by="EOD",
        exit_signal=ExitSignal.DTE_REVIEW,
        severity="INFO",
        entry_price=Decimal("100.00"),
    )


@pytest.mark.parametrize(("monthly", "yearly", "role", "action"), _PAIRS, ids=_PAIR_IDS)
def test_monthly_open_does_not_block_yearly_entry(
    store: PaperStore, monthly: str, yearly: str, role: str, action: TradeAction
) -> None:
    """An open monthly leg is invisible to the yearly entry guard and yearly positions."""
    _open(store, monthly, role, "NSE_FO|M1", action)

    assert _has_open_overlay_leg(store, role, monthly) is True
    assert _has_open_overlay_leg(store, role, yearly) is False
    assert store.get_positions(yearly) == []
    assert [p.instrument_key for p in store.get_positions(monthly)] == ["NSE_FO|M1"]


@pytest.mark.parametrize(("monthly", "yearly", "role", "action"), _PAIRS, ids=_PAIR_IDS)
def test_yearly_open_does_not_block_monthly_entry(
    store: PaperStore, monthly: str, yearly: str, role: str, action: TradeAction
) -> None:
    """An open yearly leg is invisible to the monthly entry guard and monthly positions."""
    _open(store, yearly, role, "NSE_FO|Y1", action)

    assert _has_open_overlay_leg(store, role, yearly) is True
    assert _has_open_overlay_leg(store, role, monthly) is False
    assert store.get_positions(monthly) == []
    assert [p.instrument_key for p in store.get_positions(yearly)] == ["NSE_FO|Y1"]


def test_exit_event_in_one_book_not_visible_in_other(store: PaperStore) -> None:
    """Exit events are keyed by book in both directions; the unfiltered view sees both."""
    monthly_id = _exit_event(store, STRATEGY_OVERLAY, "overlay_cc")
    yearly_id = _exit_event(store, STRATEGY_OVERLAY_YEARLY_CC, "overlay_cc")

    assert [e["id"] for e in store.get_open_exit_events(STRATEGY_OVERLAY)] == [monthly_id]
    assert [e["id"] for e in store.get_open_exit_events(STRATEGY_OVERLAY_YEARLY_CC)] == [yearly_id]
    assert store.get_open_exit_events(STRATEGY_OVERLAY_YEARLY_PP) == []
    assert {e["id"] for e in store.get_open_exit_events()} == {monthly_id, yearly_id}


def test_exit_event_only_in_yearly_leaves_monthly_empty(store: PaperStore) -> None:
    """A lone yearly exit event never shows in the monthly book (and vice versa)."""
    _exit_event(store, STRATEGY_OVERLAY_YEARLY_COLLAR, "overlay_collar_call")
    assert store.get_open_exit_events(STRATEGY_OVERLAY) == []

    other = PaperStore(store.db_path.parent / "other.db")
    _exit_event(other, STRATEGY_OVERLAY, "overlay_cc")
    assert other.get_open_exit_events(STRATEGY_OVERLAY_YEARLY_COLLAR) == []


def _gate(store: PaperStore, name: str) -> tuple[str, str] | None:
    """Run the collateral gate for one lot of *name*; return (actual, threshold) or None."""
    v = check_collateral_capacity(store, name, 1, Decimal("24500"), Decimal("280"), lot_size=_LOT)
    return None if v is None else (v.actual, v.threshold)


def test_collateral_gates_are_separate_per_book(store: PaperStore) -> None:
    """Monthly lots never consume yearly collateral, and yearly lots never consume monthly.

    Decision 6 (yearly-foundation): the yearly gate is its own pool, not the audit's shared
    pool. 5725 NiftyBees units support exactly one monthly lot; the yearly pool allocates zero.
    """
    store.record_trade(
        PaperTrade(
            strategy_name=STRATEGY_SPOT,
            leg_role="base_etf",
            instrument_key="NSE_EQ|NB",
            trade_date=_D,
            action=TradeAction.BUY,
            quantity=5725,
            price=Decimal("260.00"),
        )
    )
    # Empty books: monthly fits one lot; yearly has no collateral at all.
    assert _gate(store, STRATEGY_OVERLAY) is None
    assert _gate(store, STRATEGY_OVERLAY_YEARLY_CC) == ("1", "0")

    # Monthly lot opened: monthly pool now full, yearly count unchanged (still 1 vs 0).
    _open(store, STRATEGY_OVERLAY, "overlay_cc", "NSE_FO|M1")
    assert _gate(store, STRATEGY_OVERLAY) == ("2", "1")
    assert _gate(store, STRATEGY_OVERLAY_YEARLY_CC) == ("1", "0")


def test_yearly_open_does_not_consume_monthly_collateral(store: PaperStore) -> None:
    """Opening yearly legs leaves the monthly gate result untouched."""
    store.record_trade(
        PaperTrade(
            strategy_name=STRATEGY_SPOT,
            leg_role="base_etf",
            instrument_key="NSE_EQ|NB",
            trade_date=_D,
            action=TradeAction.BUY,
            quantity=5725,
            price=Decimal("260.00"),
        )
    )
    before = _gate(store, STRATEGY_OVERLAY)
    _open(store, STRATEGY_OVERLAY_YEARLY_CC, "overlay_cc", "NSE_FO|Y1")
    _open(store, STRATEGY_OVERLAY_YEARLY_PP, "overlay_pp", "NSE_FO|Y2", TradeAction.BUY)
    assert before is None
    assert _gate(store, STRATEGY_OVERLAY) == before
    # Yearly count is yearly lots only (CC 1 + PP 1 + this lot), against zero allocation.
    assert _gate(store, STRATEGY_OVERLAY_YEARLY_CC) == ("3", "0")


def _pnl(strategy: str, overlay: str, pnl: str) -> OverlayPnLSnapshot:
    """Build an ``OverlayPnLSnapshot`` for ``_D`` with a single P&L value."""
    v = Decimal(pnl)
    return OverlayPnLSnapshot(
        strategy_name=strategy,
        overlay_type=overlay,
        snapshot_date=_D,
        pnl_1d_abs=v,
        pnl_1d_pct=Decimal("0.01"),
        pnl_inception_abs=v,
        pnl_inception_pct=Decimal("0.02"),
    )


def test_overlay_pnl_snapshot_keys_do_not_collide_across_books(store: PaperStore) -> None:
    """Same date and overlay_type under monthly and yearly names are separate rows."""
    store.record_overlay_pnl_snapshot(_pnl(STRATEGY_OVERLAY, "cc", "100"))
    store.record_overlay_pnl_snapshot(_pnl(STRATEGY_OVERLAY_YEARLY_CC, "cc", "-250"))

    monthly = store.get_overlay_pnl_snapshots(STRATEGY_OVERLAY, "cc")
    yearly = store.get_overlay_pnl_snapshots(STRATEGY_OVERLAY_YEARLY_CC, "cc")
    assert [s.pnl_inception_abs for s in monthly] == [Decimal("100")]
    assert [s.pnl_inception_abs for s in yearly] == [Decimal("-250")]
    assert store.get_overlay_pnl_snapshots(STRATEGY_OVERLAY_YEARLY_PP, "cc") == []

    # Upserting the yearly row must not overwrite the monthly one.
    store.record_overlay_pnl_snapshot(_pnl(STRATEGY_OVERLAY_YEARLY_CC, "cc", "-300"))
    assert store.get_overlay_pnl_snapshots(STRATEGY_OVERLAY, "cc")[0].pnl_inception_abs == Decimal(
        "100"
    )


def _seed_call(store: PaperStore, ledger: str, role: str) -> None:
    """Short the shared test call contract in *ledger*."""
    _open(store, ledger, role, _CALL_KEY, TradeAction.SELL)


def test_yearly_cc_and_collar_call_legs_do_not_double_cover(store: PaperStore) -> None:
    """The yearly CC and Collar ledgers see each other's short call, in both directions.

    Exercises the real dedup helper with the exact ledger tuple ``main()`` passes for yearly
    CC/collar entries (the 9d4280b fix); the monthly book stays out of that namespace.
    """
    _seed_call(store, STRATEGY_OVERLAY_YEARLY_COLLAR, "overlay_collar_call")
    assert _query_open_call_role(store.db_path, _CALL_KEY, _YEARLY_CC_COLLAR) == (
        "overlay_collar_call"
    )

    other = PaperStore(store.db_path.parent / "cc_first.db")
    _seed_call(other, STRATEGY_OVERLAY_YEARLY_CC, "overlay_cc")
    assert _query_open_call_role(other.db_path, _CALL_KEY, _YEARLY_CC_COLLAR) == "overlay_cc"


def test_call_dedup_does_not_cross_monthly_and_yearly_books(store: PaperStore) -> None:
    """A monthly short call does not block a yearly entry on the same key, nor vice versa."""
    _seed_call(store, STRATEGY_OVERLAY, "overlay_cc")
    assert _query_open_call_role(store.db_path, _CALL_KEY, _YEARLY_CC_COLLAR) is None
    assert _query_open_call_role(store.db_path, _CALL_KEY) == "overlay_cc"

    other = PaperStore(store.db_path.parent / "yearly_only.db")
    _seed_call(other, STRATEGY_OVERLAY_YEARLY_CC, "overlay_cc")
    assert _query_open_call_role(other.db_path, _CALL_KEY) is None

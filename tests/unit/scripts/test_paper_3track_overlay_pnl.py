"""Unit tests for S8/BUG-028: daily P&L comparison table for CC/PP/Collar overlays.

Coverage (see docs/plan/3track-consolidation/stories.md S8,
docs/council/2026-08-10_overlay-pnl-reporting-track-independence.md BUG-028):
- _compute_overlay_pnl_snapshots: persists a snapshot per overlay_type present
  today, reading only the real-leg-role paper_leg_snapshots rows under the
  standalone STRATEGY_OVERLAY strategy_name (BUG-028 fix, 2026-08-10 — was
  incorrectly scoped to a 3-track strategy's own strategy_name before this).
- pnl_1d_pct uses yesterday's mark value as denominator, not entry basis.
- pnl_inception_pct uses entry cost/credit basis as denominator, symmetric
  for CC's credit-received and PP's debit-paid legs (confirmed with operator,
  2026-08-01 — no overlay-specific sign inversion; pnl_abs is already
  direction-aware).
- Collar's call + put legs merge into a single "collar" row, matching
  _overlay_type_groups' display convention.
- record_overlay_pnl_snapshot / get_overlay_pnl_snapshots: covered in
  tests/unit/paper/test_store.py.
"""

from __future__ import annotations

import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from scripts.strategies.three_track.paper_3track_snapshot import (
    _build_recovery_digest,
    _compute_overlay_pnl_snapshots,
    _compute_protection_recovery_snapshot,
    _overlay_type_groups,
)
from src.models.portfolio import TradeAction
from src.paper.constants import STRATEGY_OVERLAY, STRATEGY_SPOT
from src.paper.models import PaperLegSnapshot, PaperTrade, TrackComparisonSnapshot
from src.paper.store import PaperStore

_TRACK = STRATEGY_OVERLAY


def _store(tmp_path: Path) -> PaperStore:
    return PaperStore(tmp_path / "test_paper.db")


def _open_leg(
    store: PaperStore,
    role: str,
    entry_date: date,
    qty: int,
    price: Decimal,
    action: TradeAction = TradeAction.SELL,
    instrument_key: str = "NSE_FO|99999",
) -> None:
    store.record_trade(
        PaperTrade(
            strategy_name=_TRACK,
            leg_role=role,
            instrument_key=instrument_key,
            trade_date=entry_date,
            action=action,
            quantity=qty,
            price=price,
            notes="entry",
        )
    )


def _leg_snap(
    role: str,
    total_pnl: Decimal,
    snap_date: date,
    ltp: Decimal | None = None,
    net_qty: int | None = None,
) -> PaperLegSnapshot:
    return PaperLegSnapshot(
        strategy_name=_TRACK,
        leg_role=role,
        snapshot_date=snap_date,
        unrealized_pnl=total_pnl,
        realized_pnl=Decimal("0"),
        total_pnl=total_pnl,
        ltp=ltp,
        net_qty=net_qty,
    )


def test_overlay_pnl_snapshot_persists_all_three_types_daily(tmp_path: Path) -> None:
    """CC, PP, and Collar all present today each produce their own row.

    ``overlay_cc`` is deliberately omitted here — per ``_overlay_type_groups``
    precedence, a standalone ``overlay_cc`` and a ``overlay_collar_call`` are
    mutually exclusive readings of "a short call is open" (the former is a
    plain CC, the latter is one leg of a collar); a strategy never carries
    both simultaneously in practice, and the dedup-vs-collar-call precedence
    itself is covered separately below.
    """
    store = _store(tmp_path)
    entry_date = date(2026, 5, 1)
    snap_date = date(2026, 5, 2)

    # PP: bought put for debit 50, qty 50.
    _open_leg(
        store,
        "overlay_pp",
        entry_date,
        qty=50,
        price=Decimal("50.00"),
        action=TradeAction.BUY,
        instrument_key="NSE_FO|88888",
    )
    store.record_leg_snapshot(_leg_snap("overlay_pp", Decimal("30"), snap_date, ltp=Decimal("80")))

    # Collar: sold call (credit 40) + bought put (debit 20), qty 50 each.
    _open_leg(
        store,
        "overlay_collar_call",
        entry_date,
        qty=50,
        price=Decimal("40.00"),
        instrument_key="NSE_FO|77777",
    )
    _open_leg(
        store,
        "overlay_collar_put",
        entry_date,
        qty=50,
        price=Decimal("20.00"),
        action=TradeAction.BUY,
        instrument_key="NSE_FO|66666",
    )
    store.record_leg_snapshot(
        _leg_snap("overlay_collar_call", Decimal("10"), snap_date, ltp=Decimal("38"))
    )
    store.record_leg_snapshot(
        _leg_snap("overlay_collar_put", Decimal("-5"), snap_date, ltp=Decimal("15"))
    )

    results = _compute_overlay_pnl_snapshots(store, snap_date)
    types = {r.overlay_type for r in results}
    assert types == {"pp", "collar"}


def test_overlay_pnl_1d_uses_yesterday_mark_denominator(tmp_path: Path) -> None:
    """pnl_1d_pct denominator is yesterday's closing mark value, not entry basis."""
    store = _store(tmp_path)
    entry_date = date(2026, 5, 1)
    day1, day2 = date(2026, 5, 1), date(2026, 5, 2)
    qty = 50
    _open_leg(store, "overlay_cc", entry_date, qty=qty, price=Decimal("100.00"))

    # Day 1: mark = 100 * 50 = 5000, total_pnl = 0 (no move yet).
    store.record_leg_snapshot(_leg_snap("overlay_cc", Decimal("0"), day1, ltp=Decimal("100.00")))
    # Day 2: premium decayed to 40 -> total_pnl = (100-40)*50 = 3000.
    store.record_leg_snapshot(_leg_snap("overlay_cc", Decimal("3000"), day2, ltp=Decimal("40.00")))

    results = _compute_overlay_pnl_snapshots(store, day2)
    cc = next(r for r in results if r.overlay_type == "cc")
    assert cc.pnl_1d_abs == Decimal("3000")
    # denominator = yesterday's mark value = 100.00 * 50 = 5000
    assert cc.pnl_1d_pct == Decimal("3000") / Decimal("5000")


def test_overlay_pnl_1d_denominator_uses_prev_day_qty_not_todays(tmp_path: Path) -> None:
    """BUG-036: a day-over-day quantity change must not blend today's size
    with yesterday's price in pnl_1d_pct's denominator.

    Day 1: 50 short calls open, ltp=100 -> mark value 5000, snapshot carries
    net_qty=50 (as a post-BUG-036-fix/backfilled row would).
    Day 2: half the position is bought back (partial close), leaving 25 open
    -> today's LIVE quantity is 25, not 50.

    Before the fix, prev_mark_value used TODAY's live quantity (25) against
    YESTERDAY's ltp (100), giving a denominator of 2500 -- wrong, since only
    50 contracts were actually open and marked at 100 yesterday. The fix must
    use prev_by_role[r].net_qty (50) instead, giving a denominator of 5000.
    """
    store = _store(tmp_path)
    entry_date = date(2026, 5, 1)
    day1, day2 = date(2026, 5, 1), date(2026, 5, 2)

    # Day 1: sell 50 to open.
    _open_leg(store, "overlay_cc", entry_date, qty=50, price=Decimal("100.00"))
    store.record_leg_snapshot(
        _leg_snap("overlay_cc", Decimal("0"), day1, ltp=Decimal("100.00"), net_qty=50)
    )

    # Day 2: buy back 25 (partial close) -- today's live net_qty is now 25.
    _open_leg(
        store,
        "overlay_cc",
        day2,
        qty=25,
        price=Decimal("60.00"),
        action=TradeAction.BUY,
    )
    store.record_leg_snapshot(
        _leg_snap("overlay_cc", Decimal("1000"), day2, ltp=Decimal("60.00"), net_qty=25)
    )

    results = _compute_overlay_pnl_snapshots(store, day2)
    cc = next(r for r in results if r.overlay_type == "cc")
    # denominator must be yesterday's mark value = 100.00 * 50 = 5000, using
    # yesterday's quantity -- NOT today's live 25 (which would give 2500).
    assert cc.pnl_1d_pct == cc.pnl_1d_abs / Decimal("5000")


def test_overlay_pnl_inception_uses_entry_basis_denominator(tmp_path: Path) -> None:
    """pnl_inception_pct denominator is entry cost/credit basis (avg_cost * qty)."""
    store = _store(tmp_path)
    entry_date = date(2026, 5, 1)
    snap_date = date(2026, 5, 5)
    qty = 50

    # PP: debit 50 at entry.
    _open_leg(
        store,
        "overlay_pp",
        entry_date,
        qty=qty,
        price=Decimal("50.00"),
        action=TradeAction.BUY,
    )
    store.record_leg_snapshot(
        _leg_snap("overlay_pp", Decimal("1500"), snap_date, ltp=Decimal("80"))
    )

    results = _compute_overlay_pnl_snapshots(store, snap_date)
    pp = next(r for r in results if r.overlay_type == "pp")
    # entry_basis = 50.00 * 50 = 2500
    assert pp.pnl_inception_pct == Decimal("1500") / Decimal("2500")


def test_collar_call_and_put_merged_as_one_row(tmp_path: Path) -> None:
    """Collar's two legs produce one comparison row, not two."""
    store = _store(tmp_path)
    entry_date = date(2026, 5, 1)
    snap_date = date(2026, 5, 2)
    qty = 50

    _open_leg(
        store,
        "overlay_collar_call",
        entry_date,
        qty=qty,
        price=Decimal("40.00"),
        instrument_key="NSE_FO|77777",
    )
    _open_leg(
        store,
        "overlay_collar_put",
        entry_date,
        qty=qty,
        price=Decimal("20.00"),
        action=TradeAction.BUY,
        instrument_key="NSE_FO|66666",
    )
    store.record_leg_snapshot(
        _leg_snap("overlay_collar_call", Decimal("100"), snap_date, ltp=Decimal("38"))
    )
    store.record_leg_snapshot(
        _leg_snap("overlay_collar_put", Decimal("-50"), snap_date, ltp=Decimal("15"))
    )

    results = _compute_overlay_pnl_snapshots(store, snap_date)
    collar_rows = [r for r in results if r.overlay_type == "collar"]
    assert len(collar_rows) == 1
    # Merged P&L = call + put total_pnl = 100 + (-50) = 50
    assert collar_rows[0].pnl_inception_abs == Decimal("50")
    # No separate "cc" row should appear once collar_put is also present.
    assert not any(r.overlay_type == "cc" for r in results)


def test_queryable_by_strategy_and_overlay_type(tmp_path: Path) -> None:
    """Computed snapshots persist and are queryable via the store."""
    store = _store(tmp_path)
    entry_date = date(2026, 5, 1)
    snap_date = date(2026, 5, 2)
    qty = 50
    _open_leg(store, "overlay_cc", entry_date, qty=qty, price=Decimal("100.00"))
    store.record_leg_snapshot(_leg_snap("overlay_cc", Decimal("60"), snap_date, ltp=Decimal("40")))

    for snap in _compute_overlay_pnl_snapshots(store, snap_date):
        store.record_overlay_pnl_snapshot(snap)

    retrieved = store.get_overlay_pnl_snapshots(_TRACK, "cc")
    assert len(retrieved) == 1
    assert retrieved[0].pnl_inception_abs == Decimal("60")


def test_collar_put_alone_still_reports_as_collar(tmp_path: Path) -> None:
    """Call leg closed/rolled off, put leg still open: no silent data gap.

    Regression guard (code-review finding, 2026-08-01): a lone
    overlay_collar_put with no overlay_collar_call must still produce a row,
    not disappear from the table.
    """
    store = _store(tmp_path)
    entry_date = date(2026, 5, 1)
    snap_date = date(2026, 5, 2)
    qty = 50

    _open_leg(
        store,
        "overlay_collar_put",
        entry_date,
        qty=qty,
        price=Decimal("20.00"),
        action=TradeAction.BUY,
        instrument_key="NSE_FO|66666",
    )
    store.record_leg_snapshot(
        _leg_snap("overlay_collar_put", Decimal("-50"), snap_date, ltp=Decimal("15"))
    )

    results = _compute_overlay_pnl_snapshots(store, snap_date)
    assert len(results) == 1
    assert results[0].overlay_type == "collar"
    assert results[0].pnl_inception_abs == Decimal("-50")


def test_overlay_with_no_legs_produces_no_rows(tmp_path: Path) -> None:
    """A track with no overlay legs at all produces an empty list, not an error."""
    store = _store(tmp_path)
    results = _compute_overlay_pnl_snapshots(store, date(2026, 5, 2))
    assert results == []


def test_group_standalone_cc_with_collar_put() -> None:
    """BUG-044 fix: overlay_cc + collar_put must split into two groups.

    A standalone weekly overlay_cc bootstrap can genuinely coexist with an
    unrelated, already-open collar (put leg only, call leg closed/rolled
    off) — see docs/bugs/bugs.md BUG-044. No marker distinguishes "overlay_cc
    is the collar's own call" from "unrelated standalone CC" after the fact,
    so the two must never be merged: overlay_cc always gets its own "cc"
    group, and the put alone reports as "collar" (BUG-030's old merge
    silently added the standalone CC's P&L into the Collar total).
    """
    groups = _overlay_type_groups({"overlay_cc", "overlay_collar_put"})
    assert groups == {"cc": ["overlay_cc"], "collar": ["overlay_collar_put"]}


def test_overlay_type_groups_call_and_put_still_merge_into_collar() -> None:
    """Unaffected existing combination: collar_call + collar_put -> collar."""
    groups = _overlay_type_groups({"overlay_collar_call", "overlay_collar_put"})
    assert groups == {"collar": ["overlay_collar_call", "overlay_collar_put"]}


def test_overlay_type_groups_call_alone_is_cc() -> None:
    """Unaffected existing combination: lone overlay_collar_call -> cc."""
    groups = _overlay_type_groups({"overlay_collar_call"})
    assert groups == {"cc": ["overlay_collar_call"]}


def test_overlay_type_groups_put_alone_is_collar() -> None:
    """Unaffected existing combination: lone overlay_collar_put -> collar
    (lifecycle transition)."""
    groups = _overlay_type_groups({"overlay_collar_put"})
    assert groups == {"collar": ["overlay_collar_put"]}


def test_overlay_type_groups_cc_alone_is_cc() -> None:
    """Unaffected existing combination: lone overlay_cc -> cc."""
    groups = _overlay_type_groups({"overlay_cc"})
    assert groups == {"cc": ["overlay_cc"]}


def test_overlay_type_groups_pp_is_independent_of_collar_combinations() -> None:
    """overlay_pp always gets its own row regardless of which
    cc/collar combo fires."""
    groups = _overlay_type_groups({"overlay_cc", "overlay_collar_put", "overlay_pp"})
    assert groups == {
        "cc": ["overlay_cc"],
        "collar": ["overlay_collar_put"],
        "pp": ["overlay_pp"],
    }


def test_standalone_cc_and_collar_put_split_into_two_rows_end_to_end(
    tmp_path: Path,
) -> None:
    """BUG-044 end-to-end: standalone CC and collar-put report separately.

    Reproduces the live 2026-09-09 scenario: an overlay_cc short call
    (+53.625 P&L) and an unrelated, already-open overlay_collar_put
    (-973.375 P&L) present the same day. Before the fix, no
    ``overlay_type='cc'`` row was ever emitted and the cc leg's P&L was
    silently folded into the ``collar`` row's total (BUG-044).
    """
    store = _store(tmp_path)
    entry_date = date(2026, 5, 1)
    snap_date = date(2026, 5, 2)
    qty = 50

    _open_leg(
        store,
        "overlay_cc",
        entry_date,
        qty=qty,
        price=Decimal("40.00"),
        instrument_key="NSE_FO|77777",
    )
    _open_leg(
        store,
        "overlay_collar_put",
        entry_date,
        qty=qty,
        price=Decimal("20.00"),
        action=TradeAction.BUY,
        instrument_key="NSE_FO|66666",
    )
    store.record_leg_snapshot(
        _leg_snap("overlay_cc", Decimal("53.625"), snap_date, ltp=Decimal("38"))
    )
    store.record_leg_snapshot(
        _leg_snap(
            "overlay_collar_put",
            Decimal("-973.375"),
            snap_date,
            ltp=Decimal("15"),
        )
    )

    results = _compute_overlay_pnl_snapshots(store, snap_date)
    cc_rows = [r for r in results if r.overlay_type == "cc"]
    collar_rows = [r for r in results if r.overlay_type == "collar"]
    assert len(cc_rows) == 1
    assert len(collar_rows) == 1
    # Each row's P&L is its own leg only — no cross-contamination.
    assert cc_rows[0].pnl_inception_abs == Decimal("53.625")
    assert collar_rows[0].pnl_inception_abs == Decimal("-973.375")


def test_recovery_digest_shows_cc_line_for_standalone_cc(tmp_path: Path) -> None:
    """BUG-044 end-to-end: the S9 digest gets a real CC line, not 'No data'.

    With a standalone overlay_cc leg open alongside an unrelated collar-put,
    ``_compute_overlay_pnl_snapshots`` must now persist a standalone "cc"
    row (per the grouping fix above), so
    ``_compute_protection_recovery_snapshot`` reads it back without firing
    ``protection_recovery.overlay_source_missing`` for "cc", and the digest
    shows a real CC figure instead of "No data".
    """
    store = _store(tmp_path)
    entry_date = date(2026, 5, 1)
    snap_date = date(2026, 5, 2)
    qty = 50

    store.record_track_comparison_snapshot(
        TrackComparisonSnapshot(
            strategy_name=STRATEGY_SPOT,
            snapshot_date=snap_date,
            pnl_1d_abs=Decimal("-10724"),
            pnl_1d_pct=Decimal("0"),
            pnl_inception_abs=Decimal("-10724"),
            pnl_inception_pct=Decimal("0"),
        )
    )
    _open_leg(
        store,
        "overlay_cc",
        entry_date,
        qty=qty,
        price=Decimal("53.90"),
        instrument_key="NSE_FO|77777",
    )
    _open_leg(
        store,
        "overlay_collar_put",
        entry_date,
        qty=qty,
        price=Decimal("20.00"),
        action=TradeAction.BUY,
        instrument_key="NSE_FO|66666",
    )
    store.record_leg_snapshot(_leg_snap("overlay_cc", Decimal("793"), snap_date, ltp=Decimal("38")))
    store.record_leg_snapshot(
        _leg_snap("overlay_collar_put", Decimal("5694"), snap_date, ltp=Decimal("15"))
    )

    for snap in _compute_overlay_pnl_snapshots(store, snap_date):
        store.record_overlay_pnl_snapshot(snap)

    recovery_snap = _compute_protection_recovery_snapshot(store, snap_date)
    assert recovery_snap is not None
    assert recovery_snap.cc_pnl_1d == Decimal("793")
    # Collar figure reflects only the collar's own leg — no CC leakage.
    assert recovery_snap.collar_pnl_1d == Decimal("5694")

    digest = _build_recovery_digest(recovery_snap)
    assert "CC" in digest
    assert "CC     No data" not in digest

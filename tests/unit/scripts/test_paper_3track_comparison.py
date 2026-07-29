"""Unit tests for S3: independent daily base-leg comparison snapshot.

Coverage (see docs/plan/3track-consolidation/stories.md S3):
- _compute_track_comparison_snapshot: base-only P&L, overlay rows never enter
  the aggregation even when present in paper_leg_snapshots.
- _compute_track_comparison_snapshot: pnl_1d_pct uses yesterday's mark value
  as denominator, not entry cost or NEE.
- _compute_track_comparison_snapshot: pnl_inception_pct uses entry cost basis
  as denominator — deliberately different from pnl_1d_pct's denominator.
- _compute_track_comparison_snapshot: tracking_error_pct computed against
  Nifty spot return since the track's entry date.
- _compute_track_comparison_snapshot: returns None if today's base-leg
  snapshot has not been persisted yet.
- _compute_spot_comparison_snapshot: 4th synthetic "nifty_index" series, same
  field shape/denominators as the three tracks.
- record_track_comparison_snapshot / get_track_comparison_snapshots: covered
  in tests/unit/paper/test_store.py.
"""

from __future__ import annotations

import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from scripts.strategies.three_track.paper_3track_snapshot import (
    _compute_spot_comparison_snapshot,
    _compute_track_comparison_snapshot,
)
from src.models.portfolio import TradeAction
from src.paper.constants import STRATEGY_SPOT
from src.paper.models import PaperLegSnapshot, PaperNavSnapshot, PaperTrade
from src.paper.store import PaperStore

_TRACK = STRATEGY_SPOT
_BASE_ROLE = "base_etf"
_KEY = "NSE_EQ|NIFTYBEES"


def _store(tmp_path: Path) -> PaperStore:
    return PaperStore(tmp_path / "test_paper.db")


def _open_base_position(
    store: PaperStore, entry_date: date, qty: int = 1000, price: Decimal = Decimal("250.00")
) -> None:
    store.record_trade(
        PaperTrade(
            strategy_name=_TRACK,
            leg_role=_BASE_ROLE,
            instrument_key=_KEY,
            trade_date=entry_date,
            action=TradeAction.BUY,
            quantity=qty,
            price=price,
            notes="entry",
        )
    )


def _leg_snap(total_pnl: Decimal, snap_date: date, ltp: Decimal | None = None) -> PaperLegSnapshot:
    return PaperLegSnapshot(
        strategy_name=_TRACK,
        leg_role=_BASE_ROLE,
        snapshot_date=snap_date,
        unrealized_pnl=total_pnl,
        realized_pnl=Decimal("0"),
        total_pnl=total_pnl,
        ltp=ltp,
    )


# ── _compute_track_comparison_snapshot ──────────────────────────────────────


def test_comparison_snapshot_excludes_overlay_legs(tmp_path: Path) -> None:
    """Overlay leg rows present in paper_leg_snapshots never enter the calc."""
    store = _store(tmp_path)
    entry_date = date(2026, 5, 1)
    snap_date = date(2026, 5, 2)
    _open_base_position(store, entry_date)

    # Base leg: +5000 total P&L
    store.record_leg_snapshot(_leg_snap(Decimal("5000"), snap_date, ltp=Decimal("255.00")))
    # Overlay leg with a huge P&L — must never leak into the base-only calc.
    store.record_leg_snapshot(
        PaperLegSnapshot(
            strategy_name=_TRACK,
            leg_role="overlay_cc",
            snapshot_date=snap_date,
            unrealized_pnl=Decimal("999999"),
            realized_pnl=Decimal("0"),
            total_pnl=Decimal("999999"),
        )
    )

    result = _compute_track_comparison_snapshot(store, _TRACK, snap_date, Decimal("24000"))
    assert result is not None
    assert result.pnl_inception_abs == Decimal("5000")


def test_pnl_1d_uses_yesterday_mark_denominator(tmp_path: Path) -> None:
    """pnl_1d_pct denominator is yesterday's closing mark value, not entry cost."""
    store = _store(tmp_path)
    entry_date = date(2026, 5, 1)
    day1, day2 = date(2026, 5, 1), date(2026, 5, 2)
    qty = 1000
    _open_base_position(store, entry_date, qty=qty, price=Decimal("250.00"))

    # Day 1: mark = 250 * 1000 = 250000, total_pnl = 0
    store.record_leg_snapshot(_leg_snap(Decimal("0"), day1, ltp=Decimal("250.00")))
    # Day 2: total_pnl = 5000 (mark moved to 255)
    store.record_leg_snapshot(_leg_snap(Decimal("5000"), day2, ltp=Decimal("255.00")))

    result = _compute_track_comparison_snapshot(store, _TRACK, day2, Decimal("24000"))
    assert result is not None
    assert result.pnl_1d_abs == Decimal("5000")
    # denominator = yesterday's mark value = 250.00 * 1000 = 250000
    assert result.pnl_1d_pct == Decimal("5000") / Decimal("250000")


def test_pnl_inception_uses_entry_cost_denominator(tmp_path: Path) -> None:
    """pnl_inception_pct denominator is entry cost basis (avg_cost * qty)."""
    store = _store(tmp_path)
    entry_date = date(2026, 5, 1)
    snap_date = date(2026, 5, 5)
    qty = 1000
    _open_base_position(store, entry_date, qty=qty, price=Decimal("200.00"))
    store.record_leg_snapshot(_leg_snap(Decimal("10000"), snap_date, ltp=Decimal("210.00")))

    result = _compute_track_comparison_snapshot(store, _TRACK, snap_date, Decimal("24000"))
    assert result is not None
    # entry_cost_basis = 200.00 * 1000 = 200000
    assert result.pnl_inception_pct == Decimal("10000") / Decimal("200000")


def test_pnl_1d_and_inception_use_different_denominators(tmp_path: Path) -> None:
    """Regression guard: the two percentage fields must not share a denominator."""
    store = _store(tmp_path)
    entry_date = date(2026, 5, 1)
    day1, day2 = date(2026, 5, 1), date(2026, 5, 2)
    qty = 1000
    _open_base_position(store, entry_date, qty=qty, price=Decimal("200.00"))
    store.record_leg_snapshot(_leg_snap(Decimal("0"), day1, ltp=Decimal("200.00")))
    store.record_leg_snapshot(_leg_snap(Decimal("10000"), day2, ltp=Decimal("210.00")))

    result = _compute_track_comparison_snapshot(store, _TRACK, day2, Decimal("24000"))
    assert result is not None
    # inception denom = 200000 (entry cost), 1d denom = 200000 (yesterday's mark)
    # — same value here by coincidence of day1==entry, but computed via two
    # independent code paths; assert they diverge once marks move apart.
    day3 = date(2026, 5, 3)
    store.record_leg_snapshot(_leg_snap(Decimal("15000"), day3, ltp=Decimal("215.00")))
    result3 = _compute_track_comparison_snapshot(store, _TRACK, day3, Decimal("24100"))
    assert result3 is not None
    inception_denom = Decimal("200000")  # entry cost, fixed
    day2_mark_denom = Decimal("210.00") * qty  # yesterday's (day2) mark, moved
    assert inception_denom != day2_mark_denom
    assert result3.pnl_inception_pct == Decimal("15000") / inception_denom
    assert result3.pnl_1d_pct == Decimal("5000") / day2_mark_denom


def test_tracking_error_computed_against_spot(tmp_path: Path) -> None:
    """tracking_error_pct = track's inception return % minus spot's return % since entry."""
    store = _store(tmp_path)
    entry_date = date(2026, 5, 1)
    snap_date = date(2026, 5, 5)
    qty = 1000
    _open_base_position(store, entry_date, qty=qty, price=Decimal("200.00"))
    store.record_leg_snapshot(_leg_snap(Decimal("10000"), snap_date, ltp=Decimal("210.00")))

    # Spot at entry recorded via nav snapshot (underlying_price), as _spot_price_on reuses it.
    store.record_nav_snapshot(
        PaperNavSnapshot(
            strategy_name=_TRACK,
            snapshot_date=entry_date,
            unrealized_pnl=Decimal("0"),
            realized_pnl=Decimal("0"),
            total_pnl=Decimal("0"),
            underlying_price=Decimal("24000.00"),
        )
    )

    nifty_spot_today = Decimal("24240.00")  # +1% since entry
    result = _compute_track_comparison_snapshot(store, _TRACK, snap_date, nifty_spot_today)
    assert result is not None
    track_return_pct = Decimal("10000") / Decimal("200000")  # +5%
    spot_return_pct = (nifty_spot_today - Decimal("24000.00")) / Decimal("24000.00")  # +1%
    assert result.tracking_error_pct == track_return_pct - spot_return_pct


def test_comparison_snapshot_returns_none_without_base_leg_snapshot(tmp_path: Path) -> None:
    """Guard: if today's base-leg snapshot hasn't been persisted, return None."""
    store = _store(tmp_path)
    result = _compute_track_comparison_snapshot(store, _TRACK, date(2026, 5, 2), Decimal("24000"))
    assert result is None


# ── _compute_spot_comparison_snapshot ───────────────────────────────────────


def test_spot_persisted_as_fourth_series(tmp_path: Path) -> None:
    """Spot series uses the same 4 pnl_* fields/denominators as the 3 tracks."""
    store = _store(tmp_path)
    entry_date = date(2026, 5, 1)
    snap_date = date(2026, 5, 5)

    store.record_nav_snapshot(
        PaperNavSnapshot(
            strategy_name=STRATEGY_SPOT,
            snapshot_date=entry_date,
            unrealized_pnl=Decimal("0"),
            realized_pnl=Decimal("0"),
            total_pnl=Decimal("0"),
            underlying_price=Decimal("24000.00"),
        )
    )

    nifty_spot_today = Decimal("24240.00")
    result = _compute_spot_comparison_snapshot(store, snap_date, nifty_spot_today, entry_date)

    assert result.strategy_name == "nifty_index"
    assert result.pnl_inception_abs == Decimal("240.00")
    assert result.pnl_inception_pct == Decimal("240.00") / Decimal("24000.00")
    # No prior comparison row yet — 1-day defaults to the inception move.
    assert result.pnl_1d_abs == Decimal("240.00")
    assert result.tracking_error_pct is None


def test_spot_comparison_bootstraps_when_no_entry_history(tmp_path: Path) -> None:
    """No nav-snapshot history for entry_date yet → today's spot is a same-day proxy."""
    store = _store(tmp_path)
    snap_date = date(2026, 5, 1)
    nifty_spot_today = Decimal("24000.00")

    result = _compute_spot_comparison_snapshot(store, snap_date, nifty_spot_today, date(2026, 5, 1))
    assert result.pnl_inception_abs == Decimal("0")
    assert result.pnl_inception_pct == Decimal("0")

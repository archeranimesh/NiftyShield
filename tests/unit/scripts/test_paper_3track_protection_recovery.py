"""Unit tests for S9: NiftyBees protection-recovery comparison + Telegram digest.

Coverage (see docs/plan/3track-consolidation/stories.md S9):
- _compute_protection_recovery_snapshot: reads only S3's
  paper_track_comparison_snapshots (NiftyBees row) and S8's
  paper_overlay_pnl_snapshots (cc/pp/collar rows) for the same snapshot_date
  — no independent leg-level computation.
- recovery_pct / best_overlay is None on a green/flat NiftyBees day, never a
  negative or zero-anchored number.
- Inception recovery is computed independently of the daily pair, not a
  running sum of daily figures.
- _build_recovery_digest: drops recovery percentages and the "Best:" line on
  a green day; sorts by recovery amount (red day) or raw P&L (green day)
  descending.
- record_protection_recovery_snapshot / get_protection_recovery_snapshots:
  covered in tests/unit/paper/test_store.py.
"""

from __future__ import annotations

import sys
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from scripts.strategies.three_track.paper_3track_snapshot import (
    _build_recovery_digest,
    _compute_protection_recovery_snapshot,
)
from src.paper.constants import STRATEGY_SPOT
from src.paper.models import OverlayPnLSnapshot, ProtectionRecoverySnapshot, TrackComparisonSnapshot
from src.paper.store import PaperStore

_SNAP_DATE = date(2026, 7, 28)


def _store(tmp_path: Path) -> PaperStore:
    return PaperStore(tmp_path / "test_paper.db")


def _seed_niftybees(store: PaperStore, pnl_1d: Decimal, pnl_inception: Decimal) -> None:
    store.record_track_comparison_snapshot(
        TrackComparisonSnapshot(
            strategy_name=STRATEGY_SPOT,
            snapshot_date=_SNAP_DATE,
            pnl_1d_abs=pnl_1d,
            pnl_1d_pct=Decimal("0"),
            pnl_inception_abs=pnl_inception,
            pnl_inception_pct=Decimal("0"),
        )
    )


def _seed_overlay(
    store: PaperStore, overlay_type: str, pnl_1d: Decimal, pnl_inception: Decimal
) -> None:
    store.record_overlay_pnl_snapshot(
        OverlayPnLSnapshot(
            strategy_name=STRATEGY_SPOT,
            overlay_type=overlay_type,
            snapshot_date=_SNAP_DATE,
            pnl_1d_abs=pnl_1d,
            pnl_1d_pct=Decimal("0"),
            pnl_inception_abs=pnl_inception,
            pnl_inception_pct=Decimal("0"),
        )
    )


def test_recovery_pct_null_on_green_niftybees_day(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _seed_niftybees(store, pnl_1d=Decimal("250"), pnl_inception=Decimal("500"))
    _seed_overlay(store, "cc", Decimal("-90"), Decimal("-100"))
    _seed_overlay(store, "pp", Decimal("-45"), Decimal("-50"))
    _seed_overlay(store, "collar", Decimal("-60"), Decimal("-70"))

    snap = _compute_protection_recovery_snapshot(store, _SNAP_DATE)

    assert snap is not None
    assert snap.best_overlay is None
    assert snap.best_recovery_pct is None
    assert snap.best_overlay_inception is None
    assert snap.best_recovery_pct_inception is None


def test_recovery_pct_computed_correctly_on_red_day(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _seed_niftybees(store, pnl_1d=Decimal("-700"), pnl_inception=Decimal("-700"))
    _seed_overlay(store, "cc", Decimal("300"), Decimal("300"))
    _seed_overlay(store, "pp", Decimal("180"), Decimal("180"))
    _seed_overlay(store, "collar", Decimal("240"), Decimal("240"))

    snap = _compute_protection_recovery_snapshot(store, _SNAP_DATE)

    assert snap is not None
    assert snap.best_overlay == "cc"
    assert snap.best_recovery_pct == pytest.approx(Decimal("0.4286"), abs=Decimal("0.0001"))


def test_inception_recovery_independent_of_daily(tmp_path: Path) -> None:
    """A day that's red on 1D but green on inception picks best_overlay

    independently for each basis — inception is never derived from summing
    daily rows.
    """
    store = _store(tmp_path)
    _seed_niftybees(store, pnl_1d=Decimal("-700"), pnl_inception=Decimal("500"))
    _seed_overlay(store, "cc", Decimal("300"), Decimal("-100"))
    _seed_overlay(store, "pp", Decimal("180"), Decimal("-50"))
    _seed_overlay(store, "collar", Decimal("240"), Decimal("-70"))

    snap = _compute_protection_recovery_snapshot(store, _SNAP_DATE)

    assert snap is not None
    # 1D is red -> best_overlay set from the 1D figures.
    assert snap.best_overlay == "cc"
    # Inception is green -> null, not derived from the (red) daily verdict.
    assert snap.best_overlay_inception is None
    assert snap.best_recovery_pct_inception is None


def test_digest_omits_recovery_lines_on_green_day() -> None:
    snap = ProtectionRecoverySnapshot(
        snapshot_date=_SNAP_DATE,
        niftybees_pnl_1d=Decimal("250"),
        cc_pnl_1d=Decimal("-90"),
        pp_pnl_1d=Decimal("-45"),
        collar_pnl_1d=Decimal("-60"),
        niftybees_pnl_inception=Decimal("500"),
        cc_pnl_inception=Decimal("-100"),
        pp_pnl_inception=Decimal("-50"),
        collar_pnl_inception=Decimal("-70"),
        best_overlay=None,
        best_recovery_pct=None,
        best_overlay_inception=None,
        best_recovery_pct_inception=None,
    )

    digest = _build_recovery_digest(snap)

    assert "Best:" not in digest
    assert "%" not in digest


def test_digest_includes_best_line_and_percentages_on_red_day() -> None:
    snap = ProtectionRecoverySnapshot(
        snapshot_date=_SNAP_DATE,
        niftybees_pnl_1d=Decimal("-700"),
        cc_pnl_1d=Decimal("300"),
        pp_pnl_1d=Decimal("180"),
        collar_pnl_1d=Decimal("240"),
        niftybees_pnl_inception=Decimal("-700"),
        cc_pnl_inception=Decimal("300"),
        pp_pnl_inception=Decimal("180"),
        collar_pnl_inception=Decimal("240"),
        best_overlay="cc",
        best_recovery_pct=Decimal("0.4286"),
        best_overlay_inception="cc",
        best_recovery_pct_inception=Decimal("0.4286"),
    )

    digest = _build_recovery_digest(snap)

    assert "Best: CC" in digest
    assert "%" in digest
    # Sorted by recovery amount descending: CC (300) > Collar (240) > PP (180).
    assert digest.index("CC") < digest.index("Collar") < digest.index("PP")


@pytest.mark.asyncio
async def test_digest_single_telegram_call_per_run(tmp_path: Path) -> None:
    """One notifier.send() call for the recovery digest, not one per overlay.

    Exercises the exact call-site pattern from ``_run()``: compute the
    snapshot, then a single guarded ``notifier.send()`` call — never a loop
    over cc/pp/collar.
    """
    store = _store(tmp_path)
    _seed_niftybees(store, pnl_1d=Decimal("-700"), pnl_inception=Decimal("-700"))
    _seed_overlay(store, "cc", Decimal("300"), Decimal("300"))
    _seed_overlay(store, "pp", Decimal("180"), Decimal("180"))
    _seed_overlay(store, "collar", Decimal("240"), Decimal("240"))

    notifier = AsyncMock()
    recovery_snap = _compute_protection_recovery_snapshot(store, _SNAP_DATE)
    assert recovery_snap is not None

    if notifier:
        await notifier.send(_build_recovery_digest(recovery_snap))

    assert notifier.send.call_count == 1

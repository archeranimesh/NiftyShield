"""Unit tests for scripts/dev/backfill_nav_total_pnl.py (SNAP-5).

Offline — no network, no broker. DB is a temp SQLite file via PaperStore.
Deliberately-bad rows are written with raw sqlite (not PaperStore.record_nav_snapshot,
which now enforces the invariant this script exists to repair).
"""

from __future__ import annotations

import sqlite3
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from scripts.dev.backfill_nav_total_pnl import backfill
from src.paper.models import PaperNavSnapshot
from src.paper.store import PaperStore


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "portfolio.sqlite"


@pytest.fixture()
def store(db_path: Path) -> PaperStore:
    return PaperStore(db_path)


def _insert_bad_row(
    db_path: Path,
    strategy_name: str,
    snapshot_date: str,
    unrealized_pnl: str,
    realized_pnl: str,
    total_pnl: str,
) -> None:
    """Write a row directly via sqlite3, bypassing PaperStore's invariant check."""
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """INSERT INTO paper_nav_snapshots
               (strategy_name, snapshot_date, unrealized_pnl, realized_pnl,
                total_pnl, underlying_price)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (strategy_name, snapshot_date, unrealized_pnl, realized_pnl, total_pnl, None),
        )
        conn.commit()
    finally:
        conn.close()


def test_backfill_corrects_bad_rows(store: PaperStore, db_path: Path) -> None:
    # Good row — must be left untouched.
    store.record_nav_snapshot(
        PaperNavSnapshot(
            strategy_name="paper_nifty_spot",
            snapshot_date=date(2026, 6, 1),
            unrealized_pnl=Decimal("100"),
            realized_pnl=Decimal("50"),
            total_pnl=Decimal("150"),
        )
    )
    # Bad row — total_pnl drifted, matches the SNAP-1-found pattern.
    _insert_bad_row(db_path, "paper_nifty_proxy", "2026-06-17", "980", "0", "930")

    corrected = backfill(db_path)

    assert corrected == 1
    good = store.get_nav_snapshots("paper_nifty_spot")[0]
    assert good.total_pnl == Decimal("150")
    bad_fixed = store.get_nav_snapshots("paper_nifty_proxy")[0]
    assert bad_fixed.total_pnl == Decimal("980")
    assert bad_fixed.unrealized_pnl == Decimal("980")
    assert bad_fixed.realized_pnl == Decimal("0")


def test_backfill_no_bad_rows_is_noop(store: PaperStore, db_path: Path) -> None:
    store.record_nav_snapshot(
        PaperNavSnapshot(
            strategy_name="paper_nifty_spot",
            snapshot_date=date(2026, 6, 1),
            unrealized_pnl=Decimal("100"),
            realized_pnl=Decimal("50"),
            total_pnl=Decimal("150"),
        )
    )

    corrected = backfill(db_path)

    assert corrected == 0
    assert store.get_nav_snapshots("paper_nifty_spot")[0].total_pnl == Decimal("150")


def test_backfill_dry_run_does_not_write(store: PaperStore, db_path: Path) -> None:
    _insert_bad_row(db_path, "paper_nifty_proxy", "2026-06-17", "980", "0", "930")

    corrected = backfill(db_path, dry_run=True)

    assert corrected == 1
    still_bad = store.get_nav_snapshots("paper_nifty_proxy")[0]
    assert still_bad.total_pnl == Decimal("930")  # unchanged

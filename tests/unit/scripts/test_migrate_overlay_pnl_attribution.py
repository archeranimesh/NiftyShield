"""Unit tests for scripts/dev/migrate_overlay_pnl_attribution.py (BUG-028 Phase 3).

Offline — no network, no broker. DB is a temp SQLite file via PaperStore.
Legacy pre-S2r rows are inserted directly with raw sqlite (PaperStore.
record_overlay_pnl_snapshot only ever writes STRATEGY_OVERLAY rows post-fix, so
it can't produce the legacy shape this script exists to repair).
"""

from __future__ import annotations

import sqlite3
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from scripts.dev.migrate_overlay_pnl_attribution import migrate
from src.models.portfolio import TradeAction
from src.paper.constants import STRATEGY_OVERLAY, STRATEGY_PROXY, STRATEGY_SPOT
from src.paper.models import OverlayPnLSnapshot, PaperTrade
from src.paper.store import PaperStore


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "portfolio.sqlite"


@pytest.fixture()
def store(db_path: Path) -> PaperStore:
    return PaperStore(db_path)


def _insert_legacy_row(
    db_path: Path, strategy_name: str, overlay_type: str, snapshot_date: str
) -> None:
    """Write a legacy pre-S2r overlay_pnl row directly via sqlite3."""
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """INSERT INTO paper_overlay_pnl_snapshots
               (strategy_name, overlay_type, snapshot_date, pnl_1d_abs,
                pnl_1d_pct, pnl_inception_abs, pnl_inception_pct)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (strategy_name, overlay_type, snapshot_date, "10", "0.01", "50", "0.05"),
        )
        conn.commit()
    finally:
        conn.close()


def _seed_cutover_trade(store: PaperStore, trade_date: date) -> None:
    """Record the first STRATEGY_OVERLAY trade — establishes the S2r cutover date."""
    store.record_trade(
        PaperTrade(
            strategy_name=STRATEGY_OVERLAY,
            leg_role="overlay_cc",
            instrument_key="NSE_FO|99999",
            trade_date=trade_date,
            action=TradeAction.SELL,
            quantity=65,
            price=Decimal("50"),
        )
    )


def test_migrate_relabels_precutover_legacy_row(store: PaperStore, db_path: Path) -> None:
    _seed_cutover_trade(store, date(2026, 7, 29))
    _insert_legacy_row(db_path, STRATEGY_SPOT, "cc", "2026-07-20")

    result = migrate(db_path)

    assert result.migrated == 1
    assert result.skipped == 0
    rows = store.get_overlay_pnl_snapshots(STRATEGY_OVERLAY, "cc")
    assert len(rows) == 1
    assert rows[0].snapshot_date == date(2026, 7, 20)
    # Legacy row must no longer exist under the old strategy_name.
    assert store.get_overlay_pnl_snapshots(STRATEGY_SPOT, "cc") == []


def test_migrate_skips_on_collision_and_leaves_legacy_row_intact(
    store: PaperStore, db_path: Path
) -> None:
    _seed_cutover_trade(store, date(2026, 7, 29))
    _insert_legacy_row(db_path, STRATEGY_PROXY, "pp", "2026-07-15")
    # A canonical STRATEGY_OVERLAY row already exists for the same key.
    store.record_overlay_pnl_snapshot(
        OverlayPnLSnapshot(
            strategy_name=STRATEGY_OVERLAY,
            overlay_type="pp",
            snapshot_date=date(2026, 7, 15),
            pnl_1d_abs=Decimal("5"),
            pnl_1d_pct=Decimal("0.01"),
            pnl_inception_abs=Decimal("20"),
            pnl_inception_pct=Decimal("0.02"),
        )
    )

    result = migrate(db_path)

    assert result.migrated == 0
    assert result.skipped == 1
    # Legacy row left intact — never overwritten, never deleted.
    legacy_rows = store.get_overlay_pnl_snapshots(STRATEGY_PROXY, "pp")
    assert len(legacy_rows) == 1
    # Canonical row unchanged (not dual-written over).
    canonical = store.get_overlay_pnl_snapshots(STRATEGY_OVERLAY, "pp")
    assert len(canonical) == 1
    assert canonical[0].pnl_1d_abs == Decimal("5")


def test_migrate_no_overlay_trades_yet_is_noop(store: PaperStore, db_path: Path) -> None:
    # No STRATEGY_OVERLAY trade recorded — S2r cutover hasn't happened in this DB.
    _insert_legacy_row(db_path, STRATEGY_SPOT, "cc", "2026-07-20")

    result = migrate(db_path)

    assert result.migrated == 0
    assert result.skipped == 0
    assert store.get_overlay_pnl_snapshots(STRATEGY_SPOT, "cc") != []


def test_migrate_dry_run_does_not_write(store: PaperStore, db_path: Path) -> None:
    _seed_cutover_trade(store, date(2026, 7, 29))
    _insert_legacy_row(db_path, STRATEGY_SPOT, "cc", "2026-07-20")

    result = migrate(db_path, dry_run=True)

    assert result.migrated == 1
    # Nothing actually written — legacy row still under the old strategy_name.
    assert store.get_overlay_pnl_snapshots(STRATEGY_SPOT, "cc") != []
    assert store.get_overlay_pnl_snapshots(STRATEGY_OVERLAY, "cc") == []

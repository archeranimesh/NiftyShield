#!/usr/bin/env python3
"""One-time historical repair: backfill ``net_qty`` on existing ``paper_leg_snapshots`` rows.

BUG-036 (2026-08-24). `PaperLegSnapshot.net_qty` was added so
`_compute_overlay_pnl_snapshots`'s `prev_mark_value` can use the quantity that
was actually open on a prior snapshot date, instead of today's live quantity
(which blends mismatched quantity/price whenever a role's size changed
day-over-day). New snapshots populate `net_qty` going forward; this script
reconstructs it for every row written before that fix.

Reconstruction: `paper_trades` is the append-only source of truth for
positions (see DB_REGISTRY.md) — for each `(strategy_name, leg_role,
snapshot_date)` row, net_qty is the signed sum of `quantity` over every
`paper_trades` row for that `(strategy_name, leg_role)` with
`trade_date <= snapshot_date` (BUY: +quantity, SELL: -quantity) — the same
netting formula `PaperStore.get_position` uses, just bounded to trades on or
before the snapshot date rather than all trades to date.

Writes go through `PaperStore.record_leg_snapshot` (upsert), never raw SQL —
this rebuilds each existing row's full PaperLegSnapshot from what's already
in the table plus the computed net_qty, so unrealized/realized/total_pnl/ltp
are round-tripped unchanged. Idempotent: rows that already carry a
(non-NULL) net_qty are left untouched unless ``--force`` is passed.

Usage:
    python -m scripts.dev.backfill_leg_snapshot_net_qty
    python -m scripts.dev.backfill_leg_snapshot_net_qty --db-path /path/to/db.sqlite
    python -m scripts.dev.backfill_leg_snapshot_net_qty --dry-run
    python -m scripts.dev.backfill_leg_snapshot_net_qty --force
"""

from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import structlog

from src.utils.logging import setup_logging

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.models.portfolio import TradeAction  # noqa: E402
from src.paper.constants import DEFAULT_DB_PATH  # noqa: E402
from src.paper.models import PaperLegSnapshot  # noqa: E402
from src.paper.store import PaperStore  # noqa: E402

_SCRIPT_NAME = "scripts.dev.backfill_leg_snapshot_net_qty"
logger = structlog.get_logger(_SCRIPT_NAME)


@dataclass(frozen=True)
class BackfillResult:
    """Outcome counts for a single backfill run.

    Attributes:
        backfilled: Rows whose net_qty was computed and written.
        skipped: Rows left untouched because net_qty was already non-NULL
            (only possible with --force omitted).
    """

    backfilled: int
    skipped: int


def _backup_db(db_path: Path) -> Path:
    """Copy *db_path* to a timestamped sibling file before any write.

    Args:
        db_path: Path to the live portfolio SQLite database.

    Returns:
        Path to the created backup file.
    """
    timestamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    backup_path = db_path.with_name(f"{db_path.stem}.bak_{timestamp}{db_path.suffix}")
    shutil.copy2(db_path, backup_path)
    return backup_path


def _find_target_rows(conn: sqlite3.Connection, force: bool) -> list[sqlite3.Row]:
    """Return paper_leg_snapshots rows in need of a net_qty backfill.

    Args:
        conn: Open sqlite3 connection (row_factory=sqlite3.Row).
        force: If True, return every row regardless of current net_qty.
            If False, return only rows where net_qty IS NULL.

    Returns:
        Matching rows, each with strategy_name, leg_role, snapshot_date,
        unrealized_pnl, realized_pnl, total_pnl, ltp.
    """
    where = "" if force else "WHERE net_qty IS NULL"
    return conn.execute(
        f"""SELECT strategy_name, leg_role, snapshot_date, unrealized_pnl,
                   realized_pnl, total_pnl, ltp
            FROM paper_leg_snapshots
            {where}
            ORDER BY strategy_name, leg_role, snapshot_date"""
    ).fetchall()


def _net_qty_as_of(
    conn: sqlite3.Connection,
    strategy_name: str,
    leg_role: str,
    snapshot_date: str,
) -> int:
    """Signed net quantity for (strategy_name, leg_role) as of snapshot_date, inclusive.

    Same netting formula as `PaperStore.get_position` (SUM(BUY qty) -
    SUM(SELL qty)), bounded to `trade_date <= snapshot_date` so the result
    reflects what was actually open on that historical date, not today.

    Args:
        conn: Open sqlite3 connection.
        strategy_name: Paper strategy name.
        leg_role: Leg identifier within the strategy.
        snapshot_date: ISO date string, inclusive upper bound on trade_date.

    Returns:
        Net quantity (positive = long, negative = short); 0 if no trades on
        or before snapshot_date exist for this (strategy_name, leg_role).
    """
    rows = conn.execute(
        """SELECT action, quantity FROM paper_trades
           WHERE strategy_name = ? AND leg_role = ? AND trade_date <= ?""",
        (strategy_name, leg_role, snapshot_date),
    ).fetchall()
    net = 0
    for row in rows:
        action = TradeAction(row["action"])
        net += row["quantity"] if action is TradeAction.BUY else -row["quantity"]
    return net


def backfill(db_path: Path, dry_run: bool = False, force: bool = False) -> BackfillResult:
    """Backfill net_qty for existing paper_leg_snapshots rows.

    Args:
        db_path: Path to the portfolio SQLite database.
        dry_run: If True, compute and log what would change but write nothing.
        force: If True, recompute and overwrite every row's net_qty, not just
            NULL ones.

    Returns:
        BackfillResult with counts of rows backfilled/skipped.
    """
    # Constructing PaperStore runs its idempotent schema migration (adds
    # net_qty if missing) BEFORE any raw query below touches the column —
    # without this, a DB whose net_qty column hasn't been created yet
    # (e.g. dry-run against a DB no PaperStore call has opened this
    # process) fails with "no such column: net_qty".
    PaperStore(db_path)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        targets = _find_target_rows(conn, force)
    finally:
        conn.close()

    if not targets:
        print(f"[{_SCRIPT_NAME}] No rows need a net_qty backfill — nothing to do.")
        return BackfillResult(backfilled=0, skipped=0)

    print(f"[{_SCRIPT_NAME}] {len(targets)} row(s) targeted for net_qty backfill.")

    if dry_run:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            for row in targets:
                net_qty = _net_qty_as_of(
                    conn, row["strategy_name"], row["leg_role"], row["snapshot_date"]
                )
                print(
                    f"  [DRY RUN] {row['strategy_name']} / {row['leg_role']} / "
                    f"{row['snapshot_date']}: net_qty -> {net_qty}"
                )
        finally:
            conn.close()
        return BackfillResult(backfilled=0, skipped=0)

    backup_path = _backup_db(db_path)
    print(f"[{_SCRIPT_NAME}] Backup written to {backup_path}")

    store = PaperStore(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    backfilled = 0
    try:
        for row in targets:
            net_qty = _net_qty_as_of(
                conn, row["strategy_name"], row["leg_role"], row["snapshot_date"]
            )
            snap = PaperLegSnapshot(
                strategy_name=row["strategy_name"],
                leg_role=row["leg_role"],
                snapshot_date=date.fromisoformat(row["snapshot_date"]),
                unrealized_pnl=Decimal(row["unrealized_pnl"]),
                realized_pnl=Decimal(row["realized_pnl"]),
                total_pnl=Decimal(row["total_pnl"]),
                ltp=Decimal(row["ltp"]) if row["ltp"] is not None else None,
                net_qty=net_qty,
            )
            store.record_leg_snapshot(snap)
            backfilled += 1
            logger.info(
                "backfill_leg_snapshot_net_qty.row_backfilled",
                strategy_name=row["strategy_name"],
                leg_role=row["leg_role"],
                snapshot_date=row["snapshot_date"],
                net_qty=net_qty,
            )
    finally:
        conn.close()

    print(f"[{_SCRIPT_NAME}] Backfilled {backfilled} row(s).")
    return BackfillResult(backfilled=backfilled, skipped=0)


def main() -> None:
    """CLI entrypoint."""
    setup_logging()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--dry-run", action="store_true", help="Compute and print, write nothing.")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Recompute every row's net_qty, not just NULL ones.",
    )
    args = parser.parse_args()

    result = backfill(args.db_path, dry_run=args.dry_run, force=args.force)
    logger.info(
        "backfill_leg_snapshot_net_qty.complete",
        backfilled=result.backfilled,
        skipped=result.skipped,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()

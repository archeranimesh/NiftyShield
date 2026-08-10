#!/usr/bin/env python3
"""One-time historical repair: reattribute pre-S2r overlay P&L snapshot rows.

BUG-028 Phase 3 (council-ruled 2026-08-10, `docs/council/2026-08-10_overlay-pnl-
reporting-track-independence.md`, unanimous 4/4, Position B "B-lite"). Phases 1-2
fixed the pipeline going forward — canonical `paper_overlay_pnl_snapshots` rows
now write `strategy_name = STRATEGY_OVERLAY`. This script repairs the historical
rows written *before* that fix, which are still filed under whichever 3-track
base strategy (`paper_nifty_spot` / `paper_nifty_futures` / `paper_nifty_proxy`)
happened to own the overlay leg at the time.

Cutover date is derived from the trade ledger — the date of the first
`STRATEGY_OVERLAY`-strategy_name trade (the S2r track-independence change,
2026-07-29) — not a hardcoded commit date, since the exact cutover in a given
DB depends on when that operator's overlay legs were actually re-filed.

For each pre-cutover `paper_overlay_pnl_snapshots` row under a legacy track
strategy_name, the row is relabeled to `STRATEGY_OVERLAY` UNLESS a canonical
`(STRATEGY_OVERLAY, overlay_type, snapshot_date)` row already exists — a
collision is skipped with a logged WARNING and the legacy row is left intact
rather than guessing which row is authoritative. No dual-write: a relabeled row
is a rename (UPDATE strategy_name), never a copy, so the same economic P&L
never exists under two strategy_names simultaneously.

Idempotent: rows already under STRATEGY_OVERLAY, or past the cutover date, are
left untouched; running twice is a no-op the second time.

Usage:
    python -m scripts.dev.migrate_overlay_pnl_attribution
    python -m scripts.dev.migrate_overlay_pnl_attribution --db-path /path/to/db.sqlite
    python -m scripts.dev.migrate_overlay_pnl_attribution --dry-run
"""

from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import structlog

from src.utils.logging import setup_logging

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.paper.constants import (
    DEFAULT_DB_PATH,
    STRATEGY_FUTURES,
    STRATEGY_OVERLAY,
    STRATEGY_PROXY,
    STRATEGY_SPOT,
)

_SCRIPT_NAME = "scripts.dev.migrate_overlay_pnl_attribution"
logger = structlog.get_logger(_SCRIPT_NAME)

# Pre-S2r, overlay legs were recorded under whichever 3-track base strategy
# "owned" them at entry time — these are the only legacy candidates.
_LEGACY_TRACK_STRATEGIES = (STRATEGY_SPOT, STRATEGY_FUTURES, STRATEGY_PROXY)


@dataclass(frozen=True)
class MigrationResult:
    """Outcome counts for a single migration run.

    Attributes:
        migrated: Rows successfully relabeled to STRATEGY_OVERLAY.
        skipped: Rows left intact due to a canonical-row collision.
        unchanged: Always 0 by construction — `_find_legacy_rows` already
            scopes to strictly-pre-cutover rows, so every candidate row is
            either migrated or skipped, never "found but not applicable."
            Kept as an explicit field (rather than dropped) to match B028.11's
            output-contract wording ("migrated/skipped/unchanged counts") and
            leave room for a future scope widening without an API change.
    """

    migrated: int
    skipped: int
    unchanged: int


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


def _resolve_cutover_date(conn: sqlite3.Connection) -> str | None:
    """Return the earliest trade_date recorded under STRATEGY_OVERLAY.

    Args:
        conn: Open sqlite3 connection.

    Returns:
        ISO date string of the first STRATEGY_OVERLAY trade, or None if no
        such trade exists yet (nothing to migrate — S2r cutover hasn't
        happened in this DB).
    """
    row = conn.execute(
        "SELECT MIN(trade_date) FROM paper_trades WHERE strategy_name = ?",
        (STRATEGY_OVERLAY,),
    ).fetchone()
    return row[0] if row and row[0] is not None else None


def _find_legacy_rows(conn: sqlite3.Connection, cutover_date: str) -> list[sqlite3.Row]:
    """Return pre-cutover paper_overlay_pnl_snapshots rows under a legacy strategy_name.

    Named columns only, scoped to the legacy strategies and strictly-before the
    cutover date — never a full-table SELECT *.

    Args:
        conn: Open sqlite3 connection.
        cutover_date: ISO date string; rows on or after this date are excluded
            (they were written post-fix, or belong to genuinely-still-open
            pre-cutover track/overlay overlap and are out of this script's scope).

    Returns:
        Matching rows ordered by snapshot_date ASC.
    """
    placeholders = ",".join("?" for _ in _LEGACY_TRACK_STRATEGIES)
    rows = conn.execute(
        f"""SELECT strategy_name, overlay_type, snapshot_date
            FROM paper_overlay_pnl_snapshots
            WHERE strategy_name IN ({placeholders}) AND snapshot_date < ?
            ORDER BY snapshot_date ASC""",
        (*_LEGACY_TRACK_STRATEGIES, cutover_date),
    ).fetchall()
    return rows


def _canonical_row_exists(conn: sqlite3.Connection, overlay_type: str, snapshot_date: str) -> bool:
    """Return True if a STRATEGY_OVERLAY row already exists for this key.

    Args:
        conn: Open sqlite3 connection.
        overlay_type: One of "cc", "pp", "collar".
        snapshot_date: ISO date string.

    Returns:
        True if (STRATEGY_OVERLAY, overlay_type, snapshot_date) already exists.
    """
    row = conn.execute(
        """SELECT 1 FROM paper_overlay_pnl_snapshots
           WHERE strategy_name = ? AND overlay_type = ? AND snapshot_date = ?""",
        (STRATEGY_OVERLAY, overlay_type, snapshot_date),
    ).fetchone()
    return row is not None


def migrate(db_path: Path, dry_run: bool = False) -> MigrationResult:
    """Reattribute pre-cutover legacy-track overlay P&L rows to STRATEGY_OVERLAY.

    Args:
        db_path: Path to the portfolio SQLite database.
        dry_run: If True, report what would change without writing or backing up.

    Returns:
        MigrationResult with migrated/skipped/unchanged counts.
    """
    conn = sqlite3.connect(db_path)
    try:
        conn.row_factory = sqlite3.Row

        cutover_date = _resolve_cutover_date(conn)
        if cutover_date is None:
            print(
                f"[{_SCRIPT_NAME}] No STRATEGY_OVERLAY trades found — "
                "nothing to do (S2r cutover hasn't occurred in this DB)."
            )
            return MigrationResult(migrated=0, skipped=0, unchanged=0)

        print(f"[{_SCRIPT_NAME}] Cutover date resolved from trade ledger: {cutover_date}")

        legacy_rows = _find_legacy_rows(conn, cutover_date)
        if not legacy_rows:
            print(f"[{_SCRIPT_NAME}] No pre-cutover legacy-track overlay rows found.")
            return MigrationResult(migrated=0, skipped=0, unchanged=0)

        print(f"[{_SCRIPT_NAME}] Found {len(legacy_rows)} pre-cutover legacy-track row(s).")

        if not dry_run:
            backup_path = _backup_db(db_path)
            print(f"[{_SCRIPT_NAME}] Backed up DB to {backup_path}")

        migrated = 0
        skipped = 0
        for row in legacy_rows:
            overlay_type = row["overlay_type"]
            snapshot_date = row["snapshot_date"]
            legacy_strategy = row["strategy_name"]

            if _canonical_row_exists(conn, overlay_type, snapshot_date):
                skipped += 1
                logger.warning(
                    "migrate_overlay_pnl_attribution.collision_skipped",
                    legacy_strategy_name=legacy_strategy,
                    overlay_type=overlay_type,
                    snapshot_date=snapshot_date,
                )
                print(
                    f"  SKIP (collision) {legacy_strategy} / {overlay_type} / "
                    f"{snapshot_date}: canonical STRATEGY_OVERLAY row already exists"
                )
                continue

            print(
                f"  RELABEL {legacy_strategy} -> {STRATEGY_OVERLAY} "
                f"({overlay_type} / {snapshot_date})"
            )
            if not dry_run:
                conn.execute(
                    """UPDATE paper_overlay_pnl_snapshots
                       SET strategy_name = ?
                       WHERE strategy_name = ? AND overlay_type = ? AND snapshot_date = ?""",
                    (STRATEGY_OVERLAY, legacy_strategy, overlay_type, snapshot_date),
                )
            migrated += 1

        if dry_run:
            print(f"[{_SCRIPT_NAME}] Dry run — no rows written.")
        else:
            conn.commit()

        print(
            f"[{_SCRIPT_NAME}] Done. migrated={migrated} skipped={skipped} "
            f"unchanged=0 (of {len(legacy_rows)} candidate row(s))."
        )
        return MigrationResult(migrated=migrated, skipped=skipped, unchanged=0)
    finally:
        conn.close()


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--db-path",
        type=Path,
        default=DEFAULT_DB_PATH,
        help=f"Path to SQLite DB (default: {DEFAULT_DB_PATH})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would change without writing or backing up.",
    )
    args = parser.parse_args()

    if not args.db_path.exists():
        print(f"ERROR: DB not found at {args.db_path}", file=sys.stderr)
        sys.exit(1)

    migrate(args.db_path, dry_run=args.dry_run)


if __name__ == "__main__":
    setup_logging()
    main()

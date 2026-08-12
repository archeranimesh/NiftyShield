"""One-off full wipe of every CC/PP/Collar overlay reference in portfolio.sqlite.

Throwaway script per CLAUDE.md's scratch/ convention — NOT a permanent repo
migration (unlike scripts/dev/migrate_overlay_pnl_attribution.py, which does a
narrower collision-safe relabel and is kept as a documented, re-runnable fix).
This script is the "just delete it all, we'll let the self-healing PP cron
re-enter fresh tomorrow" decision from the 2026-08-10 chat session — see
scratch/2026-08-10_overlay_full_cleanup.md for the full rationale.

Deletes every row (legacy-track AND live paper_nifty_overlay) tagged as a
CC/PP/Collar overlay across:
    paper_trades, paper_leg_snapshots, paper_overlay_pnl_snapshots,
    paper_exit_events, paper_action_audit
and nulls (not deletes — the row also carries real NiftyBees P&L) the overlay
columns in paper_protection_recovery_snapshots.

paper_leg_snapshots has TWO leg_role naming generations for overlay legs:
the real overlay_cc/overlay_pp/overlay_collar_call/overlay_collar_put keys
(post-S7, 2026-08-01) and pre-S7 collapsed display-label rows literally named
"cc"/"pp"/"collar" (no prefix) — CONTEXT.md's S7 entry: "_save_leg_snapshots()
now persists overlay legs off raw_overlay_pnls, not the collapsed dict."
Confirmed via direct DB query this DB has both generations (168 bare-label
rows in addition to the overlay_*-prefixed ones); paper_trades and
paper_exit_events only ever used the overlay_* naming, no bare-label rows
found there. Filtered for accordingly below — matched leg_role IN
('cc','pp','collar') OR LIKE 'overlay_%' for paper_leg_snapshots specifically.

Confirmed safe to include the live PP trade: paper_3track_overlay_entry
--auto-pp runs every weekday 10:30 IST and self-selects "no open overlay_pp ->
bootstrap a fresh entry" (see logs/cron.log), so deleting today's live PP
position just resets the clock — tomorrow's cron re-enters it, now correctly
attributed to STRATEGY_OVERLAY from the start.

Usage:
    python3 scratch/2026-08-10_overlay_full_cleanup.py               # dry-run (default)
    python3 scratch/2026-08-10_overlay_full_cleanup.py --execute     # backs up + writes
    python3 scratch/2026-08-10_overlay_full_cleanup.py --db-path /path/to/db.sqlite --execute
"""

from __future__ import annotations

import argparse
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

# Inlined verbatim from src/paper/store.py PaperStore.__init__'s BUG-028
# Phase 2 migration block, rather than importing PaperStore itself — the real
# module pulls in structlog/pydantic, which this throwaway script shouldn't
# need to depend on just to apply one schema fix. Kept byte-for-byte
# identical to the source so it stays a faithful mirror, not a fork.
_PROTECTION_RECOVERY_REBUILD_SQL = """
PRAGMA foreign_keys = OFF;
BEGIN;
CREATE TABLE paper_protection_recovery_snapshots_new (
    snapshot_date                 TEXT NOT NULL,
    niftybees_pnl_1d              TEXT NOT NULL,
    cc_pnl_1d                     TEXT,
    pp_pnl_1d                     TEXT,
    collar_pnl_1d                 TEXT,
    niftybees_pnl_inception       TEXT NOT NULL,
    cc_pnl_inception              TEXT,
    pp_pnl_inception              TEXT,
    collar_pnl_inception          TEXT,
    best_overlay                  TEXT,
    best_recovery_pct             TEXT,
    best_overlay_inception         TEXT,
    best_recovery_pct_inception    TEXT,
    PRIMARY KEY (snapshot_date)
) STRICT;
INSERT INTO paper_protection_recovery_snapshots_new
    SELECT * FROM paper_protection_recovery_snapshots;
DROP TABLE paper_protection_recovery_snapshots;
ALTER TABLE paper_protection_recovery_snapshots_new
    RENAME TO paper_protection_recovery_snapshots;
COMMIT;
PRAGMA foreign_keys = ON;
"""


def _apply_protection_recovery_migration_if_needed(conn: sqlite3.Connection) -> bool:
    """Rebuild paper_protection_recovery_snapshots to drop NOT NULL, if needed.

    Mirrors PaperStore.__init__'s BUG-028 Phase 2 migration exactly —
    idempotent, detected via PRAGMA table_info's notnull flag (not a string
    match against sqlite_master.sql).

    Args:
        conn: Open sqlite3 connection.

    Returns:
        True if the rebuild ran, False if the schema was already migrated.
    """
    table_exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table'"
        " AND name='paper_protection_recovery_snapshots'"
    ).fetchone()
    cc_col_still_not_null = table_exists and any(
        col[1] == "cc_pnl_1d" and col[3] == 1
        for col in conn.execute("PRAGMA table_info(paper_protection_recovery_snapshots)").fetchall()
    )
    if cc_col_still_not_null:
        conn.executescript(_PROTECTION_RECOVERY_REBUILD_SQL)
    return bool(cc_col_still_not_null)


_OVERLAY_STRATEGIES = (
    "paper_nifty_spot",
    "paper_nifty_futures",
    "paper_nifty_proxy",
    "paper_nifty_overlay",
)

_DEFAULT_DB_PATH = Path("data/portfolio/portfolio.sqlite")


def _count(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> int:
    return conn.execute(sql, params).fetchone()[0]


def _backup_db(db_path: Path) -> Path:
    timestamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    backup_path = db_path.with_name(f"{db_path.stem}.bak_{timestamp}{db_path.suffix}")
    shutil.copy2(db_path, backup_path)
    return backup_path


def run(db_path: Path, execute: bool) -> None:
    """Report (and optionally perform) the full overlay wipe.

    Args:
        db_path: Path to the portfolio SQLite database.
        execute: If False (default), only reports what would change — no
            backup, no writes. If True, backs up the DB first, then commits.
    """
    conn = sqlite3.connect(db_path)
    placeholders = ",".join("?" for _ in _OVERLAY_STRATEGIES)

    checks = [
        (
            "paper_trades",
            f"""SELECT COUNT(*) FROM paper_trades
                WHERE strategy_name IN ({placeholders}) AND leg_role LIKE 'overlay_%'""",
            f"""DELETE FROM paper_trades
                WHERE strategy_name IN ({placeholders}) AND leg_role LIKE 'overlay_%'""",
        ),
        (
            "paper_leg_snapshots",
            f"""SELECT COUNT(*) FROM paper_leg_snapshots
                WHERE strategy_name IN ({placeholders})
                  AND (leg_role LIKE 'overlay_%' OR leg_role IN ('cc', 'pp', 'collar'))""",
            f"""DELETE FROM paper_leg_snapshots
                WHERE strategy_name IN ({placeholders})
                  AND (leg_role LIKE 'overlay_%' OR leg_role IN ('cc', 'pp', 'collar'))""",
        ),
        (
            "paper_overlay_pnl_snapshots",
            f"""SELECT COUNT(*) FROM paper_overlay_pnl_snapshots
                WHERE strategy_name IN ({placeholders})""",
            f"""DELETE FROM paper_overlay_pnl_snapshots
                WHERE strategy_name IN ({placeholders})""",
        ),
        (
            "paper_exit_events",
            f"""SELECT COUNT(*) FROM paper_exit_events
                WHERE strategy_name IN ({placeholders}) AND leg_name LIKE 'overlay_%'""",
            f"""DELETE FROM paper_exit_events
                WHERE strategy_name IN ({placeholders}) AND leg_name LIKE 'overlay_%'""",
        ),
        (
            "paper_action_audit",
            """SELECT COUNT(*) FROM paper_action_audit WHERE strategy_name = 'paper_nifty_overlay'""",
            """DELETE FROM paper_action_audit WHERE strategy_name = 'paper_nifty_overlay'""",
        ),
    ]

    print(f"[overlay_full_cleanup] DB: {db_path}  mode: {'EXECUTE' if execute else 'DRY-RUN'}")
    print()

    total = 0
    for label, count_sql, _delete_sql in checks:
        n = _count(conn, count_sql, _OVERLAY_STRATEGIES[: count_sql.count("?")])
        total += n
        print(f"  {label}: {n} row(s) to delete")

    recovery_n = _count(
        conn,
        """SELECT COUNT(*) FROM paper_protection_recovery_snapshots
           WHERE cc_pnl_1d IS NOT NULL OR pp_pnl_1d IS NOT NULL OR collar_pnl_1d IS NOT NULL""",
    )
    print(f"  paper_protection_recovery_snapshots: {recovery_n} row(s) to null overlay columns on")
    print(f"\n  Total rows deleted: {total}; rows updated: {recovery_n}")

    if not execute:
        print("\n[overlay_full_cleanup] Dry run — no backup taken, no writes made.")
        print("Re-run with --execute to perform the cleanup for real.")
        conn.close()
        return

    backup_path = _backup_db(db_path)
    print(f"\n[overlay_full_cleanup] Backed up DB to {backup_path}")

    # This DB's paper_protection_recovery_snapshots was still on the
    # pre-BUG-028-Phase-2 NOT NULL schema (confirmed via PRAGMA table_info:
    # notnull=1 on cc_pnl_1d) — a bare sqlite3.connect() never fixes that on
    # its own. Apply the migration now, only in --execute mode (after the
    # backup, before any of this script's own writes) — never during
    # dry-run, since it's itself a real schema write.
    migrated = _apply_protection_recovery_migration_if_needed(conn)
    if migrated:
        print(
            "[overlay_full_cleanup] Applied BUG-028 Phase 2 schema migration "
            "(paper_protection_recovery_snapshots NOT NULL -> nullable)."
        )
    else:
        print(
            "[overlay_full_cleanup] paper_protection_recovery_snapshots already "
            "nullable — no schema migration needed."
        )

    for _label, _count_sql, delete_sql in checks:
        conn.execute(delete_sql, _OVERLAY_STRATEGIES[: delete_sql.count("?")])

    conn.execute(
        """UPDATE paper_protection_recovery_snapshots
           SET cc_pnl_1d = NULL, pp_pnl_1d = NULL, collar_pnl_1d = NULL,
               cc_pnl_inception = NULL, pp_pnl_inception = NULL, collar_pnl_inception = NULL,
               best_overlay = NULL, best_recovery_pct = NULL,
               best_overlay_inception = NULL, best_recovery_pct_inception = NULL"""
    )

    conn.commit()
    print(
        "[overlay_full_cleanup] Done. All overlay references deleted, "
        "protection_recovery overlay columns nulled."
    )
    conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-path", type=Path, default=_DEFAULT_DB_PATH)
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Perform the cleanup for real (backs up first). Default is dry-run.",
    )
    args = parser.parse_args()
    run(args.db_path, execute=args.execute)


if __name__ == "__main__":
    main()

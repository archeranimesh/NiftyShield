"""Unit tests for scripts/dev/migrate_exit_events_counterfactual_dte_marks.py (BUG-029).

Offline — no network, no broker. DB is a temp SQLite file with paper_exit_events built
in its pre-2026-08-05 shape (raw sqlite3, not PaperStore — PaperStore.__init__ already
creates the table with counterfactual_dte_marks via _SCHEMA, so it can't reproduce the
drifted shape this migration exists to repair).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from scripts.dev.migrate_exit_events_counterfactual_dte_marks import _run

# Pre-2026-08-05 shape: every paper_exit_events column except counterfactual_dte_marks
# (added by commit 17b4ff9, "feat(paper): add counterfactual_dte_marks column to
# paper_exit_events", 2026-08-05 — the column was added to _SCHEMA and to every
# read/write query, but this migration was never run against the live DB, causing
# BUG-029's get_open_exit_events() crash every market day since).
_PRE_MIGRATION_DDL = """
CREATE TABLE paper_exit_events (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy_name           TEXT    NOT NULL,
    leg_name                TEXT    NOT NULL,
    trade_id                TEXT    NOT NULL,
    snapshot_id             INTEGER,
    event_time              TEXT    NOT NULL,
    detected_by             TEXT    NOT NULL,
    exit_signal             TEXT    NOT NULL,
    severity                TEXT    NOT NULL,
    ltp                     TEXT,
    mid                     TEXT,
    bid                     TEXT,
    ask                     TEXT,
    delta                   REAL,
    dte                     INTEGER,
    entry_price             TEXT    NOT NULL,
    threshold_value         TEXT,
    delta_stop_would_fire   INTEGER,
    premium_stop_would_fire INTEGER,
    actual_rule_used        TEXT,
    status                  TEXT    NOT NULL DEFAULT 'OPEN',
    notes                   TEXT,
    created_at              TEXT    NOT NULL DEFAULT (datetime('now'))
);
"""


@pytest.fixture()
def pre_migration_db(tmp_path: Path) -> Path:
    """A DB with paper_exit_events in its drifted, pre-migration shape."""
    db_path = tmp_path / "portfolio.sqlite"
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(_PRE_MIGRATION_DDL)
        conn.execute(
            """INSERT INTO paper_exit_events
               (strategy_name, leg_name, trade_id, event_time, detected_by,
                exit_signal, severity, entry_price)
               VALUES ('paper_nifty_spot', 'base_etf', 'trade-1', '2026-08-07T15:35:00',
                       'exit_signal_check', 'PREMIUM_STOP', 'ACTION', '50.0')"""
        )
        conn.commit()
    finally:
        conn.close()
    return db_path


def _columns(db_path: Path) -> list[str]:
    conn = sqlite3.connect(db_path)
    try:
        return [row[1] for row in conn.execute("PRAGMA table_info(paper_exit_events)").fetchall()]
    finally:
        conn.close()


def test_migrate_adds_column_and_preserves_existing_row(pre_migration_db: Path) -> None:
    assert "counterfactual_dte_marks" not in _columns(pre_migration_db)

    _run(pre_migration_db, dry_run=False)

    cols = _columns(pre_migration_db)
    assert "counterfactual_dte_marks" in cols

    conn = sqlite3.connect(pre_migration_db)
    try:
        row = conn.execute(
            "SELECT strategy_name, leg_name, trade_id, counterfactual_dte_marks "
            "FROM paper_exit_events WHERE trade_id = 'trade-1'"
        ).fetchone()
    finally:
        conn.close()
    assert row == ("paper_nifty_spot", "base_etf", "trade-1", None)


def test_migrate_is_idempotent_on_second_run(pre_migration_db: Path) -> None:
    _run(pre_migration_db, dry_run=False)
    # Second run must not raise "duplicate column name" — the skip-if-exists check
    # is exactly what BUG-029's crash class needs (safe to re-run against a DB that
    # was already migrated, e.g. after a partial/failed first attempt elsewhere).
    _run(pre_migration_db, dry_run=False)

    cols = _columns(pre_migration_db)
    assert cols.count("counterfactual_dte_marks") == 1


def test_migrate_dry_run_does_not_alter_schema(pre_migration_db: Path) -> None:
    _run(pre_migration_db, dry_run=True)

    assert "counterfactual_dte_marks" not in _columns(pre_migration_db)


def test_migrate_skips_when_column_already_present(tmp_path: Path) -> None:
    """A DB that already has the column (e.g. a fresh PaperStore-created one) is a no-op."""
    db_path = tmp_path / "portfolio.sqlite"
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(_PRE_MIGRATION_DDL)
        conn.execute("ALTER TABLE paper_exit_events ADD COLUMN counterfactual_dte_marks TEXT")
        conn.commit()
    finally:
        conn.close()

    _run(db_path, dry_run=False)

    cols = _columns(db_path)
    assert cols.count("counterfactual_dte_marks") == 1

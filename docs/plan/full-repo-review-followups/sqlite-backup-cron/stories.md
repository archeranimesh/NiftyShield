# SQLite Portfolio DB Backup Cron — Story

**Source:** `docs/plan/full-repo-review/findings/FR-7_synthesis.md`, FR-7 row 2 (CRITICAL) — FR-6 S-4.

## T1

Add a new script (e.g. `scripts/portfolio/backup_db.py`) that uses SQLite's online `.backup` API (via `sqlite3.Connection.backup()` in Python, or the `.backup` CLI command) —
never a raw file copy, which risks a torn WAL-mode copy.
Write the backup to a separate directory/drive from the live DB, with 30-daily + 12-monthly retention (prune older files after each run).
Add the cron line to the project's cron documentation.
Tests: verify a backup file is created and passes `PRAGMA integrity_check`; verify retention pruning drops files older than the window without touching the newest 30 daily / 12 monthly.

**Files touched:** `scripts/portfolio/backup_db.py`, `tests/unit/portfolio/test_backup_db.py`, cron docs

**Tests:** happy-path + error/edge-case per CLAUDE.md Step 4, in the files listed above.

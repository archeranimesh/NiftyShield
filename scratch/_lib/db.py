"""Scratch-only helper — not for src/ or scripts/dev/ import. Graduate (with tests) before reuse there.

Extracted per SCRATCH.md's convergence rule: read-only sqlite3.connect(...)
boilerplate with row_factory=sqlite3.Row was hand-rolled in 5+ scratch scripts
(overlay_cleanup_verify.py, check_stale_flat_legs.py, dump_overlay_tables.py,
overlay_full_cleanup.py, close_all_pp_legs.py) before this existed.
"""

import sqlite3
from pathlib import Path

DEFAULT_DB_PATH = Path("data/portfolio/portfolio.sqlite")


def connect_ro(db_path: Path = DEFAULT_DB_PATH) -> sqlite3.Connection:
    """Open the portfolio DB read-only with row_factory set to sqlite3.Row.

    Args:
        db_path: Path to the sqlite file. Defaults to the live portfolio DB.

    Returns:
        A read-only connection; writes will raise sqlite3.OperationalError.
    """
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def connect_rw(db_path: Path = DEFAULT_DB_PATH) -> sqlite3.Connection:
    """Open the portfolio DB read-write with row_factory set to sqlite3.Row.

    Args:
        db_path: Path to the sqlite file. Defaults to the live portfolio DB.

    Returns:
        A writable connection — caller is responsible for commit()/close().
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

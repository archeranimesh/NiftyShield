"""Shared SQLite connection utilities.

Single source of truth for the WAL-mode, row-factory connection pattern
used by both PortfolioStore and MFStore.  Any change to PRAGMAs, isolation
level, or connection flags happens here and applies everywhere.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Generator


@contextmanager
def connect(db_path: Path) -> Generator[sqlite3.Connection, None, None]:
    """Open a WAL-mode SQLite connection with auto-commit/rollback.

    Yields a connection with:
    - ``sqlite3.Row`` row factory for dict-like access.
    - WAL journal mode for concurrent readers.
    - Foreign key enforcement enabled.

    The caller must not call ``conn.commit()`` or ``conn.close()`` — both
    are handled by the context manager.

    Args:
        db_path: Filesystem path to the SQLite database file.

    Yields:
        An open, configured ``sqlite3.Connection``.

    Raises:
        Exception: Any exception raised inside the ``with`` block triggers a
            rollback before re-raising.
    """
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

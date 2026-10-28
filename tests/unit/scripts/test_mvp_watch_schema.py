"""BUG-078: mvp_watch must create missing mvp_* tables on a pre-existing DB."""

from __future__ import annotations

import asyncio
import sqlite3

import pytest

from scripts import mvp_watch


def _tables(db_path: str) -> set[str]:
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    return {r[0] for r in rows}


@pytest.mark.parametrize("entry", ["run", "run_eod"])
def test_entrypoints_create_corporate_actions_table(tmp_path, monkeypatch, entry):
    db = str(tmp_path / "legacy.sqlite")
    sqlite3.connect(db).close()  # empty DB: predates every mvp_* table
    monkeypatch.setattr(mvp_watch.settings, "db_path", db)

    asyncio.run(getattr(mvp_watch, entry)())

    assert "mvp_corporate_actions" in _tables(db)

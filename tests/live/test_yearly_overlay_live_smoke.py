"""YV-3: opt-in live smoke of the yearly overlay dry run (marker: ``live``).

Drives ``main()`` of ``paper_3track_overlay_entry`` with ``--expiry-type yearly --dry-run``
through the real instrument file, VIX history and chain fetch. Read-only: the DB is a temp
file, Telegram is neutralised, and the real instrument file is verified untouched.

Run: ``python -m pytest -m live tests/live/test_yearly_overlay_live_smoke.py -q``
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.strategies.three_track import paper_3track_overlay_entry as oe
from src.paper.store import PaperStore

pytestmark = pytest.mark.live

# flag -> leg roles that must appear in the previewed selection
_CASES = {
    "--auto-cc": ("overlay_cc",),
    "--auto-pp": ("overlay_pp",),
    "--auto-collar": ("overlay_collar_put", "overlay_collar_call"),
}


@pytest.fixture(autouse=True)
def _require_live_marker(request: pytest.FixtureRequest) -> None:
    """Skip unless the run explicitly selected the ``live`` marker with ``-m``."""
    if "live" not in (request.config.getoption("markexpr") or ""):
        pytest.skip("live test: run with -m live")


def _row_total(db_path: Path) -> int:
    """Total rows across every user table of the SQLite DB."""
    with sqlite3.connect(db_path) as conn:
        tables = [
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        ]
        return sum(conn.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0] for t in tables)


@pytest.mark.parametrize("flag", list(_CASES))
def test_live_dry_run_resolves_december_and_writes_nothing(
    flag: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A live yearly dry run selects a non-empty December leg set and writes no row."""
    for var in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(oe, "build_notifier", lambda: None)
    monkeypatch.setattr(oe, "setup_logging", lambda: None)
    bod = oe.DEFAULT_BOD_PATH
    mtime_before = bod.stat().st_mtime_ns
    db_path = tmp_path / "paper.sqlite"
    PaperStore(db_path)  # --auto-pp reads the schema before the store opens
    argv = [
        "overlay_entry",
        flag,
        "--expiry-type",
        "yearly",
        "--dry-run",
        "--db-path",
        str(db_path),
    ]
    with patch.object(sys, "argv", argv):
        oe.main()
    out = capsys.readouterr().out
    with capsys.disabled():
        print(f"\n--- {flag} yearly dry run ---\n{out}")
    assert "(yearly" in out, "no yearly expiry selected - instrument file stale?"
    for role in _CASES[flag]:
        assert role in out, f"{role} missing from selection - instrument file stale?"
    assert _row_total(db_path) == 0
    assert bod.stat().st_mtime_ns == mtime_before

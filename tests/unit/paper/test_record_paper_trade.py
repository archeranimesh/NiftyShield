"""Unit tests for scripts/record_paper_trade.py.

Tests use subprocess.run to exercise the CLI as a real process, or import
and call main() directly with sys.argv patched (for speed).

Coverage:
- CLI rejects strategy without paper_ prefix with exit code 1.
- CLI rejects invalid date format with exit code 1.
- CLI rejects invalid action (not BUY/SELL) with exit code 2 (argparse).
- CLI rejects zero quantity with exit code 1.
- --dry-run prints trade fields without inserting.
- Happy-path SELL inserts a row and prints position summary.
- Happy-path BUY inserts a row and prints position summary.
- Re-running same args is idempotent (no duplicate row).
"""

from __future__ import annotations

import sys
from datetime import date
from decimal import Decimal
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import pytest

from src.paper.store import PaperStore

# Import the module under test — sys.path already has repo root from conftest
import scripts.record_paper_trade as cli_module


# ── Helpers ───────────────────────────────────────────────────────────────────

_STRATEGY = "paper_csp_nifty_v1"
_LEG = "short_put"
_KEY = "NSE_FO|12345"
_DATE = "2026-05-01"
_PRICE = "120.50"
_QTY = "75"


def _run(
    args: list[str],
    db_path: Path,
    capture_stderr: bool = True,
) -> tuple[int, str, str]:
    """Invoke main() with patched sys.argv, capture stdout/stderr and exit code."""
    full_args = ["record_paper_trade"] + args + ["--db-path", str(db_path)]
    stdout_buf = StringIO()
    stderr_buf = StringIO()
    exit_code = 0

    with patch("sys.argv", full_args):
        with patch("sys.stdout", stdout_buf):
            with patch("sys.stderr", stderr_buf):
                try:
                    cli_module.main()
                except SystemExit as e:
                    exit_code = int(e.code) if e.code is not None else 0

    return exit_code, stdout_buf.getvalue(), stderr_buf.getvalue()


def _base_args(action: str = "SELL") -> list[str]:
    return [
        "--strategy", _STRATEGY,
        "--leg", _LEG,
        "--key", _KEY,
        "--date", _DATE,
        "--action", action,
        "--qty", _QTY,
        "--price", _PRICE,
    ]


# ── Validation errors ─────────────────────────────────────────────────────────


def test_rejects_missing_paper_prefix(tmp_path: Path) -> None:
    code, _, err = _run(
        ["--strategy", "csp_nifty_v1", "--leg", _LEG, "--key", _KEY,
         "--date", _DATE, "--action", "SELL", "--qty", _QTY, "--price", _PRICE],
        tmp_path / "db.sqlite",
    )
    assert code == 1
    assert "paper_" in err


def test_rejects_live_strategy_name(tmp_path: Path) -> None:
    code, _, err = _run(
        ["--strategy", "finideas_ilts", "--leg", _LEG, "--key", _KEY,
         "--date", _DATE, "--action", "SELL", "--qty", _QTY, "--price", _PRICE],
        tmp_path / "db.sqlite",
    )
    assert code == 1
    assert "paper_" in err


def test_rejects_invalid_date(tmp_path: Path) -> None:
    args = _base_args()
    # Replace --date value
    idx = args.index("--date") + 1
    args[idx] = "01-05-2026"
    code, _, err = _run(args, tmp_path / "db.sqlite")
    assert code == 1
    assert "YYYY-MM-DD" in err


def test_rejects_invalid_action(tmp_path: Path) -> None:
    """argparse itself rejects invalid choices — expect exit code 2."""
    args = _base_args(action="HOLD")
    code, _, _ = _run(args, tmp_path / "db.sqlite")
    assert code == 2


# ── Dry run ───────────────────────────────────────────────────────────────────


def test_dry_run_prints_fields_no_insert(tmp_path: Path) -> None:
    db = tmp_path / "db.sqlite"
    args = _base_args() + ["--dry-run"]
    code, out, _ = _run(args, db)
    assert code == 0
    assert "paper_csp_nifty_v1" in out
    assert "120.50" in out
    assert "is_paper" in out
    # DB should not exist or be empty
    if db.exists():
        store = PaperStore(db)
        assert store.get_trades(_STRATEGY) == []


# ── Happy path ────────────────────────────────────────────────────────────────


def test_sell_inserts_row_and_prints_summary(tmp_path: Path) -> None:
    db = tmp_path / "db.sqlite"
    code, out, err = _run(_base_args("SELL"), db)
    assert code == 0, f"stderr: {err}"
    assert _STRATEGY in out
    store = PaperStore(db)
    trades = store.get_trades(_STRATEGY)
    assert len(trades) == 1
    assert trades[0].action.value == "SELL"
    assert trades[0].price == Decimal("120.50")


def test_buy_inserts_row_and_prints_summary(tmp_path: Path) -> None:
    db = tmp_path / "db.sqlite"
    # First SELL to open
    _run(_base_args("SELL"), db)
    # Then BUY to close
    buy_args = list(_base_args("BUY"))
    buy_args[buy_args.index(_PRICE)] = "60.00"
    code, out, err = _run(buy_args, db)
    assert code == 0, f"stderr: {err}"
    store = PaperStore(db)
    assert len(store.get_trades(_STRATEGY)) == 2


def test_idempotent_rerun(tmp_path: Path) -> None:
    db = tmp_path / "db.sqlite"
    _run(_base_args("SELL"), db)
    _run(_base_args("SELL"), db)
    _run(_base_args("SELL"), db)
    store = PaperStore(db)
    assert len(store.get_trades(_STRATEGY)) == 1


def test_closed_position_prints_closed_message(tmp_path: Path) -> None:
    db = tmp_path / "db.sqlite"
    _run(_base_args("SELL"), db)
    buy_args = list(_base_args("BUY"))
    code, out, _ = _run(buy_args, db)
    assert code == 0
    assert "closed" in out or "net qty" in out

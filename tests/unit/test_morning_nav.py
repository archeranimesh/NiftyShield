"""Tests for scripts/morning_nav.py.

All tests are fully offline — no AMFI fetch, no dotenv, no SQLite I/O.
MFTracker.record_snapshot and MFStore are patched at the call site inside
run_morning_nav() using unittest.mock.patch.
"""

from __future__ import annotations

import tempfile
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from scripts.morning_nav import main, run_morning_nav
from src.mf.tracker import PortfolioPnL, SchemePnL


# ── Helpers ──────────────────────────────────────────────────────


def _make_pnl(n_schemes: int = 2) -> PortfolioPnL:
    """Return a minimal PortfolioPnL with n_schemes stub entries."""
    schemes = [
        SchemePnL(
            amfi_code=str(i),
            scheme_name=f"Scheme {i}",
            current_nav=Decimal("100"),
            total_units=Decimal("10"),
            total_invested=Decimal("900"),
            current_value=Decimal("1000"),
            pnl=Decimal("100"),
            pnl_pct=Decimal("11.11"),
        )
        for i in range(n_schemes)
    ]
    return PortfolioPnL(
        snapshot_date=date(2026, 4, 21),
        schemes=schemes,
        total_invested=Decimal("1800"),
        total_current_value=Decimal("2000"),
        total_pnl=Decimal("200"),
        total_pnl_pct=Decimal("11.11"),
    )


# ── run_morning_nav ───────────────────────────────────────────────


class TestRunMorningNav:
    def test_happy_path_calls_record_snapshot_with_correct_date(
        self, tmp_path: Path
    ) -> None:
        """record_snapshot must be called with the exact target_date."""
        db = tmp_path / "portfolio.sqlite"
        db.touch()
        target = date(2026, 4, 21)
        mock_pnl = _make_pnl()

        with (
            patch("src.mf.store.MFStore") as MockStore,
            patch("src.mf.tracker.MFTracker") as MockTracker,
            patch("dotenv.load_dotenv"),
        ):
            MockTracker.return_value.record_snapshot.return_value = mock_pnl
            result = run_morning_nav(target, db)

        assert result == 0
        MockTracker.return_value.record_snapshot.assert_called_once_with(
            snapshot_date=target
        )

    def test_returns_1_when_db_missing(self, tmp_path: Path) -> None:
        """Missing DB must return exit code 1 without touching MFTracker."""
        db = tmp_path / "nonexistent.sqlite"
        with patch("src.mf.tracker.MFTracker") as MockTracker:
            result = run_morning_nav(date(2026, 4, 21), db)

        assert result == 1
        MockTracker.assert_not_called()

    def test_returns_1_on_tracker_exception(self, tmp_path: Path) -> None:
        """Any exception from record_snapshot must be caught and return 1."""
        db = tmp_path / "portfolio.sqlite"
        db.touch()

        with (
            patch("src.mf.store.MFStore"),
            patch("src.mf.tracker.MFTracker") as MockTracker,
            patch("dotenv.load_dotenv"),
        ):
            MockTracker.return_value.record_snapshot.side_effect = RuntimeError(
                "AMFI unreachable"
            )
            result = run_morning_nav(date(2026, 4, 21), db)

        assert result == 1


# ── main() — date resolution ──────────────────────────────────────


class TestMain:
    def _patch_run(self, mock_pnl: PortfolioPnL | None = None):
        """Context manager that patches run_morning_nav to return 0."""
        return patch(
            "scripts.morning_nav.run_morning_nav",
            return_value=0,
        )

    def test_no_date_arg_uses_prev_trading_day(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Without --date, main must pass prev_trading_day(today) to run_morning_nav."""
        today = date(2026, 4, 22)  # Wednesday
        expected = date(2026, 4, 21)  # Tuesday

        monkeypatch.setattr("scripts.morning_nav.date", _FakeDate(today))

        with patch("scripts.morning_nav.run_morning_nav", return_value=0) as mock_run:
            monkeypatch.setattr("sys.argv", ["morning_nav"])
            main()

        called_date = mock_run.call_args[0][0]
        assert called_date == expected

    def test_no_date_arg_monday_uses_friday(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Monday morning must resolve to previous Friday."""
        today = date(2026, 4, 20)  # Monday
        expected = date(2026, 4, 17)  # Friday

        monkeypatch.setattr("scripts.morning_nav.date", _FakeDate(today))

        with patch("scripts.morning_nav.run_morning_nav", return_value=0) as mock_run:
            monkeypatch.setattr("sys.argv", ["morning_nav"])
            main()

        called_date = mock_run.call_args[0][0]
        assert called_date == expected

    def test_explicit_date_arg_passes_through(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """--date YYYY-MM-DD must pass that exact date to run_morning_nav."""
        with patch("scripts.morning_nav.run_morning_nav", return_value=0) as mock_run:
            monkeypatch.setattr(
                "sys.argv", ["morning_nav", "--date", "2026-04-15"]
            )
            main()

        called_date = mock_run.call_args[0][0]
        assert called_date == date(2026, 4, 15)


# ── Helpers for date patching ─────────────────────────────────────


class _FakeDate:
    """Minimal date shim: overrides today() while delegating everything else."""

    def __init__(self, fixed: date) -> None:
        self._fixed = fixed

    def today(self) -> date:
        return self._fixed

    def fromisoformat(self, s: str) -> date:
        return date.fromisoformat(s)

    def __call__(self, *args, **kwargs):  # type: ignore[override]
        return date(*args, **kwargs)

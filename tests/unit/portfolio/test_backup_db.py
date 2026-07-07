"""Tests for the online SQLite backup and retention pruning script."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.portfolio.backup_db import backup_database, prune_backups
from src.config import settings
from src.db import connect


@pytest.fixture
def source_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Create a mock source database with WAL mode."""
    db_path = tmp_path / "portfolio.sqlite"
    with connect(db_path) as conn:
        conn.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, value TEXT)")
        conn.execute("INSERT INTO test (value) VALUES ('hello')")

    monkeypatch.setattr(settings, "db_path", str(db_path))
    return db_path


@patch("scripts.portfolio.backup_db.datetime")
def test_backup_database_creates_valid_backup(
    mock_datetime, source_db: Path, tmp_path: Path
) -> None:
    # Set the mock to return a specific time
    fake_time = datetime(2026, 7, 7, 10, 0, 0, tzinfo=timezone.utc)
    mock_datetime.now.return_value = fake_time
    mock_datetime.strptime = datetime.strptime

    backup_dir = tmp_path / "backups"
    backup_file = backup_database(backup_dir)

    assert backup_file.exists()
    assert backup_file.name == "portfolio_20260707_100000.sqlite"

    # Verify integrity
    with sqlite3.connect(backup_file) as conn:
        cursor = conn.cursor()
        cursor.execute("PRAGMA integrity_check")
        result = cursor.fetchone()
        assert result[0] == "ok"

    # Verify data copied
    cursor.execute("SELECT value FROM test")
    assert cursor.fetchone()[0] == "hello"


def test_backup_database_raises_when_source_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Set a nonexistent db path
    missing_db = tmp_path / "missing.sqlite"
    monkeypatch.setattr(settings, "db_path", str(missing_db))

    backup_dir = tmp_path / "backups"
    with pytest.raises(FileNotFoundError, match="Source database not found"):
        backup_database(backup_dir)


def test_prune_backups(tmp_path: Path) -> None:
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()

    # Create dummy backup files
    def create_dummy(date_str: str, time_str: str) -> None:
        (backup_dir / f"portfolio_{date_str}_{time_str}.sqlite").touch()

    # Create 35 daily backups (one per day)
    for day in range(1, 36):
        date_str = f"202601{day:02d}" if day <= 31 else f"202602{day - 31:02d}"
        create_dummy(date_str, "120000")

    # Create multiple backups on the same day (should keep the latest)
    create_dummy("20260204", "130000")
    create_dummy("20260204", "140000")  # This is the latest for 20260204

    # Create 14 months of backups (1 per month) to test the 12-month limit
    for i in range(1, 15):
        # We need to go backwards from 202512 to ensure they are older
        month = 13 - i
        year = 2025
        if month <= 0:
            month += 12
            year -= 1
        create_dummy(f"{year}{month:02d}01", "120000")

    # Prune
    prune_backups(backup_dir, daily_keep=30, monthly_keep=12)

    remaining_files = list(backup_dir.glob("portfolio_*.sqlite"))
    remaining_names = {p.name for p in remaining_files}

    # Verify latest of the day is kept
    assert "portfolio_20260204_140000.sqlite" in remaining_names
    assert "portfolio_20260204_130000.sqlite" not in remaining_names
    assert "portfolio_20260204_120000.sqlite" not in remaining_names

    # The oldest backups (202411 and 202412) should be gone, as they exceed the 12 monthly limit
    assert "portfolio_20241101_120000.sqlite" not in remaining_names
    assert "portfolio_20241201_120000.sqlite" not in remaining_names

    # The 30 daily keep should preserve the last 30 distinct days
    # (Since we have 35 days total in early 2026, 20260101 to 20260105 should not be in the daily retained,
    # except 20260131 is the latest of month 202601, so it is the monthly retained for 202601.
    # 20260101 is not a monthly latest, and it's older than 30 days. So it gets deleted.)
    assert "portfolio_20260101_120000.sqlite" not in remaining_names

    # 20260131 is within the 30 daily days (it's the 31st out of 35 days), so it should be retained
    assert "portfolio_20260131_120000.sqlite" in remaining_names


def test_prune_backups_no_op_when_under_limit(tmp_path: Path) -> None:
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()

    # Create 5 dummy backup files (fewer than daily_keep=30)
    for day in range(1, 6):
        (backup_dir / f"portfolio_2026010{day}_120000.sqlite").touch()

    # Prune
    prune_backups(backup_dir, daily_keep=30, monthly_keep=12)

    # Verify no files were deleted
    remaining_files = list(backup_dir.glob("portfolio_*.sqlite"))
    assert len(remaining_files) == 5

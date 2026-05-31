"""Unit tests for NiftyShield system healthcheck script."""

from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from scripts.healthcheck import main, run_checks


@patch("scripts.healthcheck.connect")
@patch("scripts.healthcheck.load_vix_series")
@patch("scripts.healthcheck.shutil.disk_usage")
def test_run_checks_all_pass(mock_disk, mock_load_vix, mock_connect) -> None:
    """Test that run_checks returns success when all checks pass."""
    mock_conn = MagicMock()
    mock_connect.return_value.__enter__.return_value = mock_conn
    # DB access queries:
    # 1. DB accessibility check (returns (1,))
    # 2. daily_snapshots check (returns (1,))
    # 3. paper_nav_snapshots check (returns (1,))
    mock_conn.execute.return_value.fetchone.side_effect = [(1,), (1,), (1,)]

    today = date(2026, 5, 31)
    mock_load_vix.return_value = pd.Series([15.0], index=[today])
    # 800 MB free (>= 500 MB threshold)
    mock_disk.return_value = (1000 * 1024 * 1024, 200 * 1024 * 1024, 800 * 1024 * 1024)

    has_issue, messages = run_checks(today, Path("dummy.db"), Path("dummy_vix"))

    assert not has_issue
    assert any("DB: accessible" in msg for msg in messages)
    assert any("daily_snapshots: ok" in msg for msg in messages)
    assert any("paper_nav_snapshots: ok" in msg for msg in messages)
    assert any("VIX data: ok" in msg for msg in messages)
    assert any("Disk space: ok" in msg for msg in messages)


@patch("scripts.healthcheck.connect")
@patch("scripts.healthcheck.load_vix_series")
@patch("scripts.healthcheck.shutil.disk_usage")
def test_run_checks_missing_daily_snapshot(mock_disk, mock_load_vix, mock_connect) -> None:
    """Test that run_checks fails when daily snapshot is missing."""
    mock_conn = MagicMock()
    mock_connect.return_value.__enter__.return_value = mock_conn
    # Side effect: DB ok, daily snapshot missing (None), paper snapshot ok
    mock_conn.execute.return_value.fetchone.side_effect = [(1,), None, (1,)]

    today = date(2026, 5, 31)
    mock_load_vix.return_value = pd.Series([15.0], index=[today])
    mock_disk.return_value = (1000 * 1024 * 1024, 200 * 1024 * 1024, 800 * 1024 * 1024)

    has_issue, messages = run_checks(today, Path("dummy.db"), Path("dummy_vix"))

    assert has_issue
    assert any("DB: accessible" in msg for msg in messages)
    assert any("daily_snapshots: no row for today" in msg for msg in messages)
    assert any("paper_nav_snapshots: ok" in msg for msg in messages)


@pytest.mark.asyncio
@patch("scripts.healthcheck.is_trading_day")
@patch("scripts.healthcheck.run_checks")
async def test_main_non_trading_day(mock_run_checks, mock_is_trading_day) -> None:
    """Test that main exits silently on market holiday."""
    mock_is_trading_day.return_value = False

    with patch("sys.argv", ["healthcheck.py"]):
        res = await main()
        assert res == 0

    mock_run_checks.assert_not_called()


@pytest.mark.asyncio
@patch("scripts.healthcheck.is_trading_day")
@patch("scripts.healthcheck.run_checks")
@patch("scripts.healthcheck.build_notifier")
async def test_main_success_flow(mock_build_notifier, mock_run_checks, mock_is_trading_day) -> None:
    """Test that main returns 0 when checks pass."""
    mock_is_trading_day.return_value = True
    mock_run_checks.return_value = (False, ["✅ DB: accessible", "✅ daily_snapshots: ok"])

    with patch("sys.argv", ["healthcheck.py"]):
        res = await main()
        assert res == 0

    mock_build_notifier.assert_not_called()


@pytest.mark.asyncio
@patch("scripts.healthcheck.is_trading_day")
@patch("scripts.healthcheck.run_checks")
@patch("scripts.healthcheck.build_notifier")
async def test_main_failure_alerts(
    mock_build_notifier, mock_run_checks, mock_is_trading_day
) -> None:
    """Test that main returns 1 and alerts on issue."""
    mock_is_trading_day.return_value = True
    mock_run_checks.return_value = (True, ["❌ daily_snapshots: no row for today"])

    from unittest.mock import AsyncMock, MagicMock

    mock_notifier = MagicMock()
    mock_notifier.send = AsyncMock(return_value=True)
    mock_build_notifier.return_value = mock_notifier

    with patch("sys.argv", ["healthcheck.py"]):
        res = await main()
        assert res == 1

    mock_notifier.send.assert_called_once()
    assert "no row for today" in mock_notifier.send.call_args[0][0]

"""Unit tests for NiftyShield system healthcheck script."""

import importlib
import os
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

import scripts.healthcheck as healthcheck_module
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


def _reload_healthcheck_without_touching_real_env() -> None:
    """Reload scripts.healthcheck with dotenv.load_dotenv patched to a no-op.

    Real load_dotenv() mutates os.environ directly — monkeypatch cannot undo
    that. Every test below that reloads the module with the *real*
    load_dotenv() (intentionally, to exercise BUG-027's fix) must restore the
    module afterwards via this no-op reload instead of a second real one, or
    a fake TELEGRAM_BOT_TOKEN/CHAT_ID leaks into every later test in the
    process for the rest of the suite.
    """
    with patch("dotenv.load_dotenv"):
        importlib.reload(healthcheck_module)
    # Belt-and-suspenders: strip anything a prior real load_dotenv() call in
    # this test already wrote directly into process os.environ.
    os.environ.pop("TELEGRAM_BOT_TOKEN", None)
    os.environ.pop("TELEGRAM_CHAT_ID", None)


def test_healthcheck_module_calls_load_dotenv_at_import() -> None:
    """Regression test for BUG-027.

    build_notifier() (src/notifications/telegram.py) only reads real
    os.environ, never .env, so healthcheck.py must call load_dotenv() at
    import time — before build_notifier()/settings are touched — the same
    way every sibling cron script does. Prior to the fix, healthcheck.py had
    no dotenv import/call at all, so under cron (which never has
    TELEGRAM_BOT_TOKEN/CHAT_ID pre-exported) build_notifier() silently
    returned None on every run. None of the other tests in this file would
    have caught this — they all mock build_notifier directly.
    """
    try:
        with patch("dotenv.load_dotenv") as mock_load_dotenv:
            importlib.reload(healthcheck_module)
            mock_load_dotenv.assert_called_once()
    finally:
        _reload_healthcheck_without_touching_real_env()


def test_healthcheck_build_notifier_resolves_after_dotenv_load(monkeypatch, tmp_path) -> None:
    """Edge case for BUG-027: with a real .env file on disk (not just real
    os.environ), calling load_dotenv() the way healthcheck.py now does at
    import time must result in build_notifier() resolving to a real notifier
    — not silently returning None the way it did before the fix.

    Calls dotenv.load_dotenv() directly against a fixture path (python-dotenv
    discovers files by walking up from the *caller's* source file by default,
    not by cwd — monkeypatch.chdir() alone doesn't change which .env it
    finds, so an explicit dotenv_path is used here rather than relying on
    that discovery mechanism, which is dotenv's own behavior to test, not
    this codebase's).
    """
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)

    env_file = tmp_path / ".env"
    env_file.write_text(
        "TELEGRAM_BOT_TOKEN=test-token\nTELEGRAM_CHAT_ID=test-chat\n"  # pragma: allowlist secret
    )

    from dotenv import load_dotenv

    try:
        load_dotenv(dotenv_path=env_file)  # exactly what scripts.healthcheck now calls
        notifier = healthcheck_module.build_notifier()
        assert notifier is not None
        assert "test-token" in notifier._url
        assert notifier._chat_id == "test-chat"
    finally:
        os.environ.pop("TELEGRAM_BOT_TOKEN", None)
        os.environ.pop("TELEGRAM_CHAT_ID", None)


def test_healthcheck_build_notifier_still_none_without_configured_env(monkeypatch) -> None:
    """No TELEGRAM_BOT_TOKEN/CHAT_ID in the real environment — build_notifier()
    must still gracefully return None (matching existing
    test_main_failure_alerts-style behavior), not raise. Confirms the fix
    doesn't regress the documented "not configured" skip path.
    """
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)

    assert healthcheck_module.build_notifier() is None

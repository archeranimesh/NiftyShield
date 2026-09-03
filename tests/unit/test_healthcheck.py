"""Unit tests for NiftyShield system healthcheck script."""

import importlib
import os
from datetime import date, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

import scripts.healthcheck as healthcheck_module
from scripts.healthcheck import (
    CheckResult,
    build_healthcheck_alert,
    main,
    run_checks,
)


def _by_label(results: list[CheckResult], label: str) -> CheckResult:
    return next(r for r in results if r.label == label)


@patch("scripts.healthcheck.connect")
@patch("scripts.healthcheck.load_vix_series")
@patch("scripts.healthcheck.shutil.disk_usage")
def test_run_checks_all_pass(mock_disk, mock_load_vix, mock_connect, tmp_path) -> None:
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

    cron_log = tmp_path / "paper_snapshot.log"
    cron_log.write_text(
        "2026-05-31 15:35:07 [INFO] [scripts] [strategies] [three_track] "
        "[paper_3track_snapshot] snapshot.starting\n"
        "2026-05-31 15:35:12 [INFO] [scripts] [strategies] [three_track] "
        "[paper_3track_snapshot] snapshot.complete\n"
        "2026-05-31 15:36:03 [INFO] [scripts] [portfolio] [paper_snapshot] snapshot.starting\n"
    )

    results = run_checks(today, Path("dummy.db"), Path("dummy_vix"), cron_log)

    assert all(r.severity == "ok" for r in results)
    assert {r.label for r in results} == {
        "DB Access",
        "Daily Snapshot",
        "Paper NAV",
        "VIX Data",
        "Disk Space",
        "3track Cron",
    }


@patch("scripts.healthcheck.connect")
@patch("scripts.healthcheck.load_vix_series")
@patch("scripts.healthcheck.shutil.disk_usage")
def test_run_checks_missing_daily_snapshot(
    mock_disk, mock_load_vix, mock_connect, tmp_path
) -> None:
    """Test that run_checks fails when daily snapshot is missing."""
    mock_conn = MagicMock()
    mock_connect.return_value.__enter__.return_value = mock_conn
    # Side effect: DB ok, daily snapshot missing (None), paper snapshot ok
    mock_conn.execute.return_value.fetchone.side_effect = [(1,), None, (1,)]

    today = date(2026, 5, 31)
    mock_load_vix.return_value = pd.Series([15.0], index=[today])
    mock_disk.return_value = (1000 * 1024 * 1024, 200 * 1024 * 1024, 800 * 1024 * 1024)

    cron_log = tmp_path / "paper_snapshot.log"
    cron_log.write_text(
        "2026-05-31 15:35:07 [INFO] [scripts] [strategies] [three_track] "
        "[paper_3track_snapshot] snapshot.starting\n"
    )

    results = run_checks(today, Path("dummy.db"), Path("dummy_vix"), cron_log)

    assert _by_label(results, "DB Access").severity == "ok"
    daily = _by_label(results, "Daily Snapshot")
    assert daily.severity == "critical"
    assert daily.status_word == "MISSING"
    assert _by_label(results, "Paper NAV").severity == "ok"


@patch("scripts.healthcheck.connect")
@patch("scripts.healthcheck.load_vix_series")
@patch("scripts.healthcheck.shutil.disk_usage")
def test_run_checks_3track_cron_traceback(mock_disk, mock_load_vix, mock_connect, tmp_path) -> None:
    """Regression test for BUG-029/B029.5.

    An unhandled Traceback between today's paper_3track_snapshot-tagged lines
    and the next cron entry's (paper_snapshot) tagged lines must be flagged,
    even though every other check passes and the log still shows other
    entries succeeding right after it — the exact shape that let BUG-029 hit
    silently for 4 consecutive market days.
    """
    mock_conn = MagicMock()
    mock_connect.return_value.__enter__.return_value = mock_conn
    mock_conn.execute.return_value.fetchone.side_effect = [(1,), (1,), (1,)]

    today = date(2026, 8, 10)
    mock_load_vix.return_value = pd.Series([15.0], index=[today])
    mock_disk.return_value = (1000 * 1024 * 1024, 200 * 1024 * 1024, 800 * 1024 * 1024)

    cron_log = tmp_path / "paper_snapshot.log"
    cron_log.write_text(
        "2026-08-10 15:35:07 [INFO] [scripts] [strategies] [three_track] "
        "[paper_3track_snapshot] snapshot.starting\n"
        "Traceback (most recent call last):\n"
        '  File "paper_3track_snapshot.py", line 1925, in <module>\n'
        "sqlite3.OperationalError: no such column: counterfactual_dte_marks\n"
        "2026-08-10 15:36:03 [INFO] [scripts] [portfolio] [paper_snapshot] "
        "snapshot.recorded\n"
    )

    results = run_checks(today, Path("dummy.db"), Path("dummy_vix"), cron_log)

    cron = _by_label(results, "3track Cron")
    assert cron.severity == "critical"
    assert cron.status_word == "CRASHED"


@patch("scripts.healthcheck.connect")
@patch("scripts.healthcheck.load_vix_series")
@patch("scripts.healthcheck.shutil.disk_usage")
def test_run_checks_3track_cron_no_run_today(
    mock_disk, mock_load_vix, mock_connect, tmp_path
) -> None:
    """Edge case: log file exists but has no entry for today at all.

    This must be flagged (not silently skipped) — a missing cron run is at
    least as bad a signal as a crashed one.
    """
    mock_conn = MagicMock()
    mock_connect.return_value.__enter__.return_value = mock_conn
    mock_conn.execute.return_value.fetchone.side_effect = [(1,), (1,), (1,)]

    today = date(2026, 8, 10)
    mock_load_vix.return_value = pd.Series([15.0], index=[today])
    mock_disk.return_value = (1000 * 1024 * 1024, 200 * 1024 * 1024, 800 * 1024 * 1024)

    cron_log = tmp_path / "paper_snapshot.log"
    cron_log.write_text(
        "2026-08-07 15:35:07 [INFO] [scripts] [strategies] [three_track] "
        "[paper_3track_snapshot] snapshot.starting\n"
    )

    results = run_checks(today, Path("dummy.db"), Path("dummy_vix"), cron_log)

    cron = _by_label(results, "3track Cron")
    assert cron.severity == "warn"
    assert cron.status_word == "NO RUN"


def test_check_3track_snapshot_cron_missing_file(tmp_path) -> None:
    """Edge case: log file doesn't exist yet — must flag, not raise."""
    from scripts.healthcheck import _check_3track_snapshot_cron

    result = _check_3track_snapshot_cron(tmp_path / "does_not_exist.log", date(2026, 8, 10))

    assert result.severity == "warn"
    assert result.status_word == "NO LOG"


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
    mock_run_checks.return_value = [
        CheckResult("DB Access", "ok"),
        CheckResult("Daily Snapshot", "ok"),
    ]

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
    mock_run_checks.return_value = [
        CheckResult("Daily Snapshot", "critical", "MISSING", "Today"),
    ]

    from unittest.mock import AsyncMock, MagicMock

    mock_notifier = MagicMock()
    mock_notifier.send = AsyncMock(return_value=True)
    mock_build_notifier.return_value = mock_notifier

    with patch("sys.argv", ["healthcheck.py"]):
        res = await main()
        assert res == 1

    mock_notifier.send.assert_called_once()
    sent = mock_notifier.send.call_args[0][0]
    assert "Daily Snapshot" in sent
    assert "MISSING" in sent


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


# ── ROLL-11: grouped MarkdownV2 healthcheck alert ──────────────────────────────

_NOON = datetime(2026, 8, 10, 12, 17)

_SINGLE_ISSUE = [
    CheckResult("DB Access", "ok"),
    CheckResult("Daily Snapshot", "ok"),
    CheckResult("Paper NAV", "ok"),
    CheckResult("VIX Data", "warn", "STALE", "3 days"),
    CheckResult("Disk Space", "ok"),
    CheckResult("3track Cron", "ok"),
]

_MULTI_ISSUE = [
    CheckResult("DB Access", "ok"),
    CheckResult("Daily Snapshot", "critical", "MISSING", "Today"),
    CheckResult("Paper NAV", "warn", "MISSING", "Today"),
    CheckResult("VIX Data", "ok"),
    CheckResult("Disk Space", "warn", "LOW", "450.2 MB"),
    CheckResult("3track Cron", "ok"),
]

_DB_DOWN = [
    CheckResult("DB Access", "critical", "INACCESSIBLE"),
    CheckResult("Daily Snapshot", "critical", "SKIPPED", "DB error"),
    CheckResult("Paper NAV", "warn", "SKIPPED", "DB error"),
    CheckResult("VIX Data", "ok"),
    CheckResult("Disk Space", "ok"),
    CheckResult("3track Cron", "ok"),
]


def test_healthcheck_alert_single_issue() -> None:
    """One warn check, the rest folded into the SYSTEMS NORMAL summary line."""
    msg = build_healthcheck_alert(_SINGLE_ISSUE, now=_NOON)

    assert msg == (
        "⚠️ NIFTYSHIELD: DEGRADED \\[12:17\\]\n"
        "\n"
        "🚨 ACTION REQUIRED:\n"
        "⚠️ VIX Data: STALE \\(3 days\\)\n"
        "\n"
        "✅ SYSTEMS NORMAL: DB Access, Daily Snapshot, Paper NAV, Disk Space, 3track Cron"
    )


def test_healthcheck_alert_multi_issue() -> None:
    """Multiple issues, original check order preserved, passes summarised."""
    msg = build_healthcheck_alert(_MULTI_ISSUE, now=_NOON)

    assert msg == (
        "⚠️ NIFTYSHIELD: DEGRADED \\[12:17\\]\n"
        "\n"
        "🚨 ACTION REQUIRED:\n"
        "❌ Daily Snapshot: MISSING \\(Today\\)\n"
        "⚠️ Paper NAV: MISSING \\(Today\\)\n"
        "⚠️ Disk Space: LOW \\(450\\.2 MB\\)\n"
        "\n"
        "✅ SYSTEMS NORMAL: DB Access, VIX Data, 3track Cron"
    )


def test_healthcheck_alert_db_down() -> None:
    """DB-inaccessible collapses checks 1-3 into critical/warn lines."""
    msg = build_healthcheck_alert(_DB_DOWN, now=_NOON)

    assert "❌ DB Access: INACCESSIBLE" in msg
    assert "❌ Daily Snapshot: SKIPPED \\(DB error\\)" in msg
    assert "⚠️ Paper NAV: SKIPPED \\(DB error\\)" in msg
    assert "✅ SYSTEMS NORMAL: VIX Data, Disk Space, 3track Cron" in msg


def test_healthcheck_normal_line_omitted_when_all_issues() -> None:
    """Finding 6: no trailing SYSTEMS NORMAL line when no check is ok."""
    all_bad = [
        CheckResult("DB Access", "critical", "INACCESSIBLE"),
        CheckResult("Daily Snapshot", "critical", "SKIPPED", "DB error"),
        CheckResult("Paper NAV", "warn", "SKIPPED", "DB error"),
        CheckResult("VIX Data", "warn", "MISSING"),
        CheckResult("Disk Space", "warn", "LOW", "12.0 MB"),
        CheckResult("3track Cron", "critical", "CRASHED", "Traceback in today's run"),
    ]
    msg = build_healthcheck_alert(all_bad, now=_NOON)

    assert "SYSTEMS NORMAL" not in msg
    assert not msg.endswith("\n")


def test_healthcheck_escapes_exception_text_in_detail() -> None:
    """Highest-risk field: a str(e) detail with . ( ) survives escaping."""
    results = [
        CheckResult("DB Access", "ok"),
        CheckResult("Daily Snapshot", "ok"),
        CheckResult("Paper NAV", "ok"),
        CheckResult("VIX Data", "warn", "ERROR", "Connection refused: (errno 111)"),
        CheckResult("Disk Space", "ok"),
        CheckResult("3track Cron", "ok"),
    ]
    msg = build_healthcheck_alert(results, now=_NOON)

    assert "\\(errno 111\\)" in msg
    assert "(errno 111)" not in msg.replace("\\(errno 111\\)", "")


def test_healthcheck_overall_status_always_degraded() -> None:
    """Finding 4: a critical + warn mix still renders the single DEGRADED tier."""
    mixed = [
        CheckResult("DB Access", "ok"),
        CheckResult("Daily Snapshot", "critical", "MISSING", "Today"),
        CheckResult("VIX Data", "warn", "STALE", "5 days"),
    ]
    msg = build_healthcheck_alert(mixed, now=_NOON)

    assert msg.startswith("⚠️ NIFTYSHIELD: DEGRADED ")
    assert "DOWN" not in msg
    assert "CRITICAL" not in msg


@patch("scripts.healthcheck.connect")
@patch("scripts.healthcheck.load_vix_series")
@patch("scripts.healthcheck.shutil.disk_usage")
def test_healthcheck_run_checks_returns_check_results(
    mock_disk, mock_load_vix, mock_connect, tmp_path
) -> None:
    """Finding 2: run_checks() returns list[CheckResult], not pre-formatted strings."""
    mock_conn = MagicMock()
    mock_connect.return_value.__enter__.return_value = mock_conn
    mock_conn.execute.return_value.fetchone.side_effect = [(1,), (1,), (1,)]

    today = date(2026, 5, 31)
    mock_load_vix.return_value = pd.Series([15.0], index=[today])
    mock_disk.return_value = (1000 * 1024 * 1024, 200 * 1024 * 1024, 800 * 1024 * 1024)

    cron_log = tmp_path / "paper_snapshot.log"
    cron_log.write_text(
        "2026-05-31 15:35:07 [INFO] [scripts] [strategies] [three_track] "
        "[paper_3track_snapshot] snapshot.starting\n"
    )

    # Reference the class/function through the module object rather than the
    # module-level `from` imports: the BUG-027 dotenv tests reload
    # scripts.healthcheck, which rebinds its CheckResult to a fresh class object
    # and would break a stale-import isinstance() check under randomized ordering.
    results = healthcheck_module.run_checks(today, Path("dummy.db"), Path("dummy_vix"), cron_log)

    assert isinstance(results, list)
    assert results
    assert all(isinstance(r, healthcheck_module.CheckResult) for r in results)
    assert not any(isinstance(r, str) for r in results)

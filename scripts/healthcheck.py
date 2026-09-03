#!/usr/bin/env python3
"""System healthcheck script for NiftyShield.

Validates:
1. Trading day guard (exits early silently on holidays).
2. Database accessibility.
3. Snapshot recency in daily_snapshots (for today).
4. Paper snapshot recency in paper_nav_snapshots (for today).
5. India VIX data recency (warns if > 2 days stale).
6. Disk space (warns if < 500 MB free).
7. paper_3track_snapshot cron crash detection (BUG-029 follow-up, B029.5):
   flags an unhandled Traceback in today's 15:35 cron run before it's caught
   by the next day's `get_open_exit_events` call.

Fires a Telegram alert if any check fails or warns, and exits 1.
Runs silently and exits 0 on success.
"""

import argparse
import asyncio
import shutil
import sys
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Literal

import structlog
from dotenv import load_dotenv

# Load environment before local imports — build_notifier() reads only real
# os.environ (Settings(_env_file=None), see BUG-011), so this must run before
# settings/build_notifier are touched. Every other cron-invoked script in this
# repo already does this; healthcheck.py was missing it entirely (BUG-027),
# which meant every alert silently no-op'd under cron ("Telegram notifier not
# configured") despite has_issue correctly firing.
load_dotenv()

from src.backtest.vix_ingest import load_vix_series  # noqa: E402
from src.config import settings  # noqa: E402
from src.db import connect  # noqa: E402
from src.market_calendar.holidays import is_trading_day  # noqa: E402
from src.notifications.markdown import escape_markdown  # noqa: E402
from src.notifications.telegram import build_notifier  # noqa: E402
from src.utils.logging import setup_logging  # noqa: E402

logger = structlog.get_logger()

Severity = Literal["ok", "warn", "critical"]

_SEVERITY_EMOJI: dict[str, str] = {"ok": "✅", "warn": "⚠️", "critical": "❌"}


@dataclass(frozen=True)
class CheckResult:
    """One healthcheck's structured outcome.

    Replaces the pre-formatted ``✅/❌/⚠️``-prefixed strings ``run_checks()``
    used to return. Re-parsing those back into ``(label, severity)`` for the
    ROLL-11 grouped alert format would repeat the brittle-string-parsing
    anti-pattern this epic already rejected in ROLL-7's ``blocked_reason``
    split.

    Attributes:
        label: Human-readable check name (e.g. ``"Daily Snapshot"``) — no raw
            snake_case keys, which also sidesteps escaping an underscore.
        severity: ``"ok"`` / ``"warn"`` / ``"critical"``.
        status_word: Compact all-caps state, only meaningful when
            ``severity != "ok"`` (e.g. ``"MISSING"``, ``"LOW"``, ``"STALE"``).
        detail: Optional context rendered parenthesised in the alert (e.g.
            ``"Today"``, ``"450.2 MB"``, an exception string).
    """

    label: str
    severity: Severity
    status_word: str = ""
    detail: str | None = None


def _check_3track_snapshot_cron(log_path: Path, target_date: date) -> CheckResult:
    """Detect whether today's ``paper_3track_snapshot`` cron run crashed.

    ``logs/paper_snapshot.log`` is shared by two cron entries (see
    ``scripts/cron/paper_snapshot.cron.txt``): the 15:35 ``paper_3track_snapshot``
    run, and the 15:36 ``scripts.portfolio.paper_snapshot`` run appended right
    after it in the same file. An unhandled exception in the first script
    prints a bare Python traceback (no structlog timestamp/tag — it bypasses
    structlog entirely) between its own tagged lines and the next script's
    tagged lines. This is exactly the silent-failure shape BUG-029 hit for 4
    consecutive market days (2026-08-05 through 2026-08-10): the crash was
    logged but nothing alerted on it, and the second cron entry's unrelated
    success made the log look healthy at a glance.

    Args:
        log_path: Path to the shared cron log file.
        target_date: Date to check the most recent run for.

    Returns:
        A ``CheckResult`` labelled ``"3track Cron"``.
    """
    if not log_path.exists():
        return CheckResult("3track Cron", "warn", "NO LOG")

    date_prefix = target_date.isoformat()
    lines = log_path.read_text(errors="replace").splitlines()

    last_start_idx: int | None = None
    end_idx = len(lines)
    for i, line in enumerate(lines):
        if not line.startswith(date_prefix):
            continue
        if "[paper_3track_snapshot]" in line:
            last_start_idx = i
            end_idx = len(lines)
        elif last_start_idx is not None and "[paper_snapshot]" in line:
            end_idx = i
            break

    if last_start_idx is None:
        return CheckResult("3track Cron", "warn", "NO RUN", "today")

    run_lines = lines[last_start_idx:end_idx]
    if any("Traceback (most recent call last)" in line for line in run_lines):
        return CheckResult("3track Cron", "critical", "CRASHED", "Traceback in today's run")

    return CheckResult("3track Cron", "ok")


def run_checks(
    target_date: date, db_path: Path, vix_dir: Path, cron_log_path: Path
) -> list[CheckResult]:
    """Execute all system health checks.

    Args:
        target_date: Date to check snapshots against.
        db_path: Path to SQLite database.
        vix_dir: Path to VIX data directory.
        cron_log_path: Path to the shared paper_snapshot cron log file.

    Returns:
        One ``CheckResult`` per check, in check order. The caller derives the
        overall state via ``any(r.severity != "ok" for r in results)``.
    """
    results: list[CheckResult] = []

    # Check 1: DB Accessibility & Snapshot Recency
    try:
        with connect(db_path) as conn:
            conn.execute("SELECT 1").fetchone()
            results.append(CheckResult("DB Access", "ok"))

            # Check 2: Snapshot recency (daily_snapshots) - Mandatory/Production data (❌ if missing)
            row_daily = conn.execute(
                "SELECT 1 FROM daily_snapshots WHERE snapshot_date = ? LIMIT 1",
                (target_date.isoformat(),),
            ).fetchone()
            if row_daily:
                results.append(CheckResult("Daily Snapshot", "ok"))
            else:
                results.append(CheckResult("Daily Snapshot", "critical", "MISSING", "Today"))

            # Check 3: Paper snapshot recency (paper_nav_snapshots) - Advisory/Paper-only data (⚠️ if missing)
            row_paper = conn.execute(
                "SELECT 1 FROM paper_nav_snapshots WHERE snapshot_date = ? LIMIT 1",
                (target_date.isoformat(),),
            ).fetchone()
            if row_paper:
                results.append(CheckResult("Paper NAV", "ok"))
            else:
                results.append(CheckResult("Paper NAV", "warn", "MISSING", "Today"))

    except Exception as e:
        logger.exception("Database access or query failed", error=str(e), db_path=str(db_path))
        results.append(CheckResult("DB Access", "critical", "INACCESSIBLE"))
        results.append(CheckResult("Daily Snapshot", "critical", "SKIPPED", "DB error"))
        results.append(CheckResult("Paper NAV", "warn", "SKIPPED", "DB error"))

    # Check 4: VIX data recency
    try:
        vix_series = load_vix_series(vix_dir)
        if vix_series.empty:
            results.append(CheckResult("VIX Data", "warn", "MISSING"))
        else:
            latest_vix_date = vix_series.index[-1]
            if hasattr(latest_vix_date, "date"):
                latest_vix_date = latest_vix_date.date()
            stale_days = (target_date - latest_vix_date).days
            if stale_days > 2:
                results.append(CheckResult("VIX Data", "warn", "STALE", f"{stale_days} days"))
            else:
                results.append(CheckResult("VIX Data", "ok"))
    except Exception as e:
        logger.exception("Failed to check VIX data recency", error=str(e))
        results.append(CheckResult("VIX Data", "warn", "ERROR", str(e)))

    # Check 5: Disk space
    try:
        target_dir = db_path.parent if db_path.parent.exists() else Path(".")
        total, used, free = shutil.disk_usage(str(target_dir))
        free_mb = free / (1024 * 1024)
        if free_mb < 500:
            results.append(CheckResult("Disk Space", "warn", "LOW", f"{free_mb:.1f} MB"))
        else:
            results.append(CheckResult("Disk Space", "ok"))
    except Exception as e:
        logger.exception("Failed to check disk space", error=str(e))
        results.append(CheckResult("Disk Space", "warn", "ERROR", str(e)))

    # Check 6: 3track snapshot cron crash detection (BUG-029 / B029.5)
    results.append(_check_3track_snapshot_cron(cron_log_path, target_date))

    return results


def build_healthcheck_alert(results: list[CheckResult], now: datetime | None = None) -> str:
    """Render the System Healthcheck alert in the ROLL-11 grouped MarkdownV2 format.

    Shape (confirmed 2026-08-10, ``message-format-workshop.md`` — reference
    ``scratch/2026-08-10_healthcheck_alert_format.py``)::

        ⚠️ NIFTYSHIELD: DEGRADED [HH:MM]

        🚨 ACTION REQUIRED:
        {emoji} {label}: {STATUS_WORD} ({detail})   ← one line per non-ok check

        ✅ SYSTEMS NORMAL: {comma-joined ok labels}  ← omitted if no check is ok

    Overall status word is a single fixed ``DEGRADED`` for any non-ok state —
    there is no ``DOWN``/``CRITICAL`` overall tier (matches ``run_checks()``'s
    boolean model; a tiered model would need its own design decision).

    Only ever called when at least one check is non-ok (``main()`` guards on the
    derived ``has_issue``), so an empty ACTION REQUIRED section is unreachable.

    Args:
        results: The full check list from ``run_checks()``.
        now: Override for the headline timestamp (testing). Defaults to
            ``datetime.now()``.

    Returns:
        A MarkdownV2-safe message body — every dynamic value and reserved
        punctuation escaped via ``escape_markdown()``.
    """
    now = now or datetime.now()
    lines = [f"⚠️ NIFTYSHIELD: DEGRADED {escape_markdown(f'[{now:%H:%M}]')}", ""]

    lines.append("🚨 ACTION REQUIRED:")
    for r in results:
        if r.severity == "ok":
            continue
        tail = f" {escape_markdown(f'({r.detail})')}" if r.detail else ""
        lines.append(
            f"{_SEVERITY_EMOJI[r.severity]} {escape_markdown(r.label)}: "
            f"{escape_markdown(r.status_word)}{tail}"
        )

    normal = [r.label for r in results if r.severity == "ok"]
    if normal:
        lines.append("")
        lines.append(f"✅ SYSTEMS NORMAL: {escape_markdown(', '.join(normal))}")

    return "\n".join(lines)


async def main() -> int:
    """Run the healthcheck script.

    Returns:
        0 on success, 1 on any check failure or warning.
    """
    parser = argparse.ArgumentParser(description="Validate NiftyShield system health")
    parser.add_argument(
        "--db-path",
        type=Path,
        default=Path(settings.db_path),
        help="Path to portfolio SQLite DB",
    )
    parser.add_argument(
        "--vix-dir",
        type=Path,
        default=Path(settings.vix_data_dir),
        help="Path to India VIX data directory",
    )
    parser.add_argument(
        "--date",
        type=str,
        default=None,
        help="Date to check health for (YYYY-MM-DD). Defaults to today.",
    )
    parser.add_argument(
        "--cron-log-path",
        type=Path,
        default=Path("logs/paper_snapshot.log"),
        help="Path to the shared paper_3track_snapshot/paper_snapshot cron log",
    )
    args = parser.parse_args()

    # Configure logging
    setup_logging(json=(settings.upstox_env == "prod"))

    # Resolve date
    if args.date:
        today = date.fromisoformat(args.date)
    else:
        today = date.today()

    # Check 1: Trading day guard (holiday check)
    if not is_trading_day(today):
        logger.info("Non-trading day. Skipping health checks.", date=today.isoformat())
        return 0

    logger.info("Running system health check", date=today.isoformat())
    results = run_checks(today, args.db_path, args.vix_dir, args.cron_log_path)
    has_issue = any(r.severity != "ok" for r in results)

    if has_issue:
        alert_msg = build_healthcheck_alert(results)

        logger.warning("System healthcheck failed or warned", alert=alert_msg)

        # Send Telegram alert
        notifier = build_notifier()
        if notifier:
            success = await notifier.send(alert_msg)
            if success:
                logger.info("Telegram healthcheck alert sent successfully")
            else:
                logger.error("Failed to send Telegram healthcheck alert")
        else:
            logger.info("Telegram notifier not configured. Skipping alert.")

        return 1

    logger.info("System healthcheck passed successfully")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

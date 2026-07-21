#!/usr/bin/env python3
"""Position/instrument staleness healthcheck for NiftyShield paper strategies.

Detects the class of bug that BUG-015/016/017 all shared: an open leg's
`instrument_key` silently drifting out of sync with reality, discovered only
by accident during an unrelated investigation. This script asks two
questions for every leg with a non-zero net position, across every
strategy, in one BOD load:

1. ROLL_OVERDUE — the leg's instrument_key has an expiry strictly before
   today, but the position is still open (net_qty != 0). This is exactly
   the BUG-017 shape: a contract settles and nobody records the roll, so
   the leg sits on a dead contract indefinitely.
2. UNRESOLVED_INSTRUMENT — the leg's instrument_key does not resolve
   against the current BOD file at all, while the position is still open.
   `PaperStore._resolve_option_type` already logs a WARNING for this case
   (BUG-014 scoped it to only fire on open legs), but that warning is
   easy to miss in cron logs. This check turns it into an active,
   Telegram-alerted signal on the same cadence as `scripts/healthcheck.py`.

This does not replace `scripts/healthcheck.py` (DB/VIX/disk recency) — it
is a second, narrower dead-man's-switch focused on paper position/instrument
integrity. Intended cron: same EOD slot as healthcheck.py, e.g. `35 16 * * 1-5`.

Fires a Telegram alert and exits 1 on any finding. Silent, exits 0 on a
clean pass.
"""

import argparse
import asyncio
import sys
from datetime import date
from pathlib import Path

import structlog

from src.config import settings
from src.instruments.lookup import InstrumentLookup, parse_expiry
from src.notifications.telegram import build_notifier
from src.paper.constants import DEFAULT_BOD_PATH
from src.paper.store import PaperStore
from src.utils.logging import setup_logging

_SCRIPT_NAME = "scripts.position_health_check"
logger = structlog.get_logger(_SCRIPT_NAME)


def run_position_checks(
    store: PaperStore, lookup: InstrumentLookup, today: date
) -> tuple[bool, list[str]]:
    """Scan every open leg across every strategy for roll/resolution staleness.

    Args:
        store: PaperStore to enumerate strategies and positions from.
        lookup: InstrumentLookup built from the current BOD file.
        today: Reference date for expiry comparison.

    Returns:
        Tuple of (has_issue, list_of_finding_messages). Empty list on a
        clean pass — never returns raw position rows, only pre-aggregated
        finding strings (Rule 1).
    """
    findings: list[str] = []

    for strategy_name in store.get_strategy_names():
        for position in store.get_positions(strategy_name):
            if position.net_qty == 0:
                continue  # closed legs are exempt — BUG-014 scoping applies here too

            inst = lookup.get_by_key(position.instrument_key)
            if inst is None:
                findings.append(
                    f"❌ UNRESOLVED_INSTRUMENT: {strategy_name}/{position.leg_role} "
                    f"key={position.instrument_key} net_qty={position.net_qty}"
                )
                continue

            expiry_str = parse_expiry(inst.get("expiry"))
            if expiry_str is None:
                continue  # non-expiring instrument (e.g. EQ) — nothing to check

            expiry_date = date.fromisoformat(expiry_str)
            if expiry_date < today:
                days_overdue = (today - expiry_date).days
                findings.append(
                    f"❌ ROLL_OVERDUE: {strategy_name}/{position.leg_role} "
                    f"key={position.instrument_key} expiry={expiry_str} "
                    f"({days_overdue}d overdue) net_qty={position.net_qty}"
                )

    return bool(findings), findings


async def main() -> int:
    """Run the position health check script.

    Returns:
        0 on a clean pass, 1 if any finding was raised.
    """
    parser = argparse.ArgumentParser(
        description="Scan open paper positions for roll/instrument staleness"
    )
    parser.add_argument(
        "--db-path", type=Path, default=Path(settings.db_path), help="Path to portfolio SQLite DB"
    )
    parser.add_argument(
        "--bod-path", type=Path, default=DEFAULT_BOD_PATH, help="Path to BOD instrument JSON"
    )
    parser.add_argument(
        "--date",
        type=str,
        default=None,
        help="Date to check staleness against (YYYY-MM-DD). Defaults to today.",
    )
    args = parser.parse_args()

    setup_logging(json=(settings.upstox_env == "prod"))

    today = date.fromisoformat(args.date) if args.date else date.today()

    lookup = InstrumentLookup.from_file(args.bod_path)
    store = PaperStore(args.db_path, instrument_lookup=lookup)

    logger.info("Running position health check", date=today.isoformat())
    has_issue, findings = run_position_checks(store, lookup, today)

    if has_issue:
        alert_body = "\n".join(findings)
        alert_msg = f"⚠️ NiftyShield Position Health — {today.isoformat()}\n{alert_body}"

        logger.warning("position_health_check_failed", finding_count=len(findings))

        notifier = build_notifier()
        if notifier:
            success = await notifier.send(alert_msg)
            if success:
                logger.info("Telegram position-health alert sent successfully")
            else:
                logger.error("Failed to send Telegram position-health alert")
        else:
            logger.info("Telegram notifier not configured. Skipping alert.")

        return 1

    logger.info("Position health check passed successfully")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

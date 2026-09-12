#!/usr/bin/env python3
"""Manual backfill / re-entry tool for the signals paper track (SPT-6).

Not a cron. `morning_signal.py` already opens `paper_signal_track_v1` via a
guarded tail-call at 09:30 — this script exists for the operator to re-run
`open_signal_paper_entry` by hand when that tail-call logged
`morning_signal.paper_entry_failed`. Idempotent: NO_TRADE, an already-open
position, and a non-trading day are all logged no-ops (the SPT-2 one-open
guard makes a re-run safe).

Usage:
    python -m scripts.signal_paper_entry --date 2026-09-29
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import date
from pathlib import Path

import structlog
from dotenv import load_dotenv

# Path setup must happen before importing local src modules
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Load environment before local imports
load_dotenv()

from src.client.factory import create_client  # noqa: E402
from src.config import settings  # noqa: E402
from src.market_calendar import market_today  # noqa: E402
from src.market_calendar.holidays import guard_trading_day  # noqa: E402
from src.paper.store import PaperStore  # noqa: E402
from src.signals.store import SignalStore  # noqa: E402
from src.strategy.signal_track_v1 import open_signal_paper_entry  # noqa: E402
from src.utils.logging import setup_logging  # noqa: E402

_SCRIPT_NAME = "scripts.signal_paper_entry"
logger = structlog.get_logger(_SCRIPT_NAME)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Manual backfill/re-entry for the signals paper track.",
    )
    parser.add_argument(
        "--date",
        dest="trade_date",
        default=market_today().isoformat(),
        metavar="YYYY-MM-DD",
        help="Trading day to (re-)open the paper entry for. Default: today (IST).",
    )
    return parser.parse_args()


async def run(trade_date: date) -> None:
    """Load the persisted signal + snapshot for ``trade_date`` and open the entry."""
    if guard_trading_day(logger, "signal_paper_entry", trade_date):
        return

    signal_store = SignalStore(settings.db_path)
    await asyncio.to_thread(signal_store.init_db)

    signal = await asyncio.to_thread(signal_store.get_signal, trade_date)
    if signal is None:
        logger.warning("signal_paper_entry.no_signal_recorded", date=trade_date.isoformat())
        return

    snapshot = await asyncio.to_thread(signal_store.get_snapshot, trade_date)
    if snapshot is None:
        logger.warning("signal_paper_entry.no_snapshot_recorded", date=trade_date.isoformat())
        return

    broker = create_client(settings.upstox_env)
    paper_store = PaperStore(settings.db_path)
    await asyncio.to_thread(paper_store.init_db)

    entry = await open_signal_paper_entry(signal, snapshot, broker, paper_store)
    if entry is None:
        logger.info("signal_paper_entry.no_op", date=trade_date.isoformat())
    else:
        logger.info(
            "signal_paper_entry.opened",
            date=trade_date.isoformat(),
            instrument_key=entry.instrument_key,
            entry_premium=str(entry.entry_premium),
        )


def main() -> None:
    args = _parse_args()
    try:
        trade_date = date.fromisoformat(args.trade_date)
    except ValueError:
        print(f"ERROR: --date must be YYYY-MM-DD, got: {args.trade_date}", file=sys.stderr)
        sys.exit(1)

    setup_logging()
    asyncio.run(run(trade_date))


if __name__ == "__main__":
    main()

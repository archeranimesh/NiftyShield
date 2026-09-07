#!/usr/bin/env python3
"""EOD PT Summary cron — cross-strategy paper-trade summary via Telegram.

Sends 1-3 MarkdownV2 messages (open positions / closed today / strategy P&L +
Ann.% on margin) built from live ``PaperStore.get_positions()`` + broker LTP.
Runs alongside ``scripts/eod_summary.py`` (the coarser NAV-snapshot digest), not
as a replacement — see ``docs/plan/eod-pt-summary/`` (PT-2).

Logic lives in ``src/reporting/eod_pt_summary.py``; this is a thin transport
wrapper. Every send is independent and non-fatal — one failing message never
blocks the others or raises past this entrypoint.

Run:
    python -m scripts.eod_pt_summary                # print only, never sends
    python -m scripts.eod_pt_summary --send         # print + send 1-3 messages
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import date
from decimal import Decimal
from pathlib import Path

import structlog
from dotenv import load_dotenv

from src.client.factory import create_client
from src.config import settings
from src.instruments.lookup import InstrumentLookup
from src.paper.constants import DEFAULT_BOD_PATH, DEFAULT_DB_PATH
from src.paper.store import PaperStore
from src.reporting.eod_pt_summary import (
    LtpProvider,
    build_summary_parts,
    send_telegram_markdown,
)
from src.utils.logging import setup_logging

load_dotenv()

_SCRIPT_NAME = "scripts.eod_pt_summary"
logger = structlog.get_logger(_SCRIPT_NAME)


class _MockBroker:
    """Zero-LTP fallback used only under ``--dry-run`` when live client init fails."""

    async def get_ltp(self, keys: list[str]) -> dict[str, Decimal]:
        return {k: Decimal("0.0") for k in keys}


async def _run(args: argparse.Namespace) -> None:
    setup_logging()
    snap_date: date = args.date or date.today()

    store = PaperStore(args.db_path)
    lookup = InstrumentLookup.from_file(args.bod_path)

    broker: LtpProvider
    try:
        broker = create_client(settings.upstox_env)
    except ValueError:
        if not args.dry_run:
            logger.error("eod_pt_summary.broker_init_failed")
            raise
        logger.warning("eod_pt_summary.broker_init_failed_mock_fallback")
        broker = _MockBroker()

    parts = await build_summary_parts(store, broker, lookup, snap_date)
    for part in parts:
        print(f"\n{part}\n")

    if not args.send:
        print(f"(--send not passed — nothing sent. {len(parts)} message(s) would be sent.)")
        return

    bot_token = settings.telegram_bot_token or ""
    chat_id = settings.telegram_chat_id or ""
    if not (bot_token and chat_id):
        logger.warning("eod_pt_summary.telegram_not_configured")
        print("!! TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set — cannot send.")
        return

    for part in parts:
        await send_telegram_markdown(bot_token, chat_id, part)


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="EOD PT Summary — cross-strategy paper-trade summary via Telegram.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--date",
        default=None,
        type=date.fromisoformat,
        metavar="YYYY-MM-DD",
        help="Snapshot date (default: today).",
    )
    parser.add_argument(
        "--dry-run",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Fall back to a zero-LTP mock broker if live client init fails (default: on).",
    )
    parser.add_argument(
        "--send",
        action="store_true",
        help="Actually send to Telegram (default: print only). "
        "Requires TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID.",
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        default=DEFAULT_DB_PATH,
        help=f"SQLite DB path (default: {DEFAULT_DB_PATH})",
    )
    parser.add_argument(
        "--bod-path",
        type=Path,
        default=DEFAULT_BOD_PATH,
        help=f"BOD instruments JSON path (default: {DEFAULT_BOD_PATH})",
    )

    asyncio.run(_run(parser.parse_args()))


if __name__ == "__main__":
    main()

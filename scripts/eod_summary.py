#!/usr/bin/env python3
"""EOD summary cron script.

Cron: 35 15 * * 1-5
Fetches today's paper NAV snapshots and sends a summary via Telegram.
"""

from __future__ import annotations

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

from src.config import settings  # noqa: E402
from src.db import connect as _connect  # noqa: E402
from src.notifications.telegram_gateway import TelegramGateway  # noqa: E402
from src.paper.store import PaperStore  # noqa: E402
from src.utils.logging import setup_logging  # noqa: E402

logger = structlog.get_logger("scripts.eod_summary")


async def main() -> int:
    logger.info("Running EOD summary...")

    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        logger.error("Telegram credentials missing in settings.")
        return 1

    store = PaperStore(settings.db_path)
    gateway = TelegramGateway(
        bot_token=settings.telegram_bot_token,
        chat_id=settings.telegram_chat_id,
        db_path=str(store.db_path),
    )

    today_str = date.today().isoformat()

    def _fetch_data():
        with _connect(store.db_path) as conn:
            nav_rows = conn.execute(
                "SELECT strategy_name, unrealized_pnl, "
                "realized_pnl, total_pnl, underlying_price "
                "FROM paper_nav_snapshots "
                "WHERE snapshot_date = ? "
                "ORDER BY strategy_name",
                (today_str,),
            ).fetchall()

            count_query = "SELECT COUNT(*) FROM pending_approvals "
            count_query += "WHERE date(created_at, '+5 hours', '+30 minutes') = ?"
            count_row = conn.execute(count_query, (today_str,)).fetchone()
            council_count = count_row[0] if count_row else 0

            # Convert rows to plain dicts to avoid SQLite thread-safety issues
            nav_dicts = [dict(r) for r in nav_rows]
            return nav_dicts, council_count

    try:
        nav_rows_dict, council_count = await asyncio.to_thread(_fetch_data)
    except Exception as e:
        # Intentional: Isolate database loading failures from crashing cron
        logger.error(
            "Database query failed during EOD summary compilation",
            error=str(e),
        )
        return 1

    msg_lines = [
        "📝 <b>NiftyShield EOD Paper Summary</b>",
        f"Date: {today_str}",
        f"Today's Council Activities: {council_count}",
        "",
        "<b>Strategy Performance:</b>",
    ]

    if not nav_rows_dict:
        msg_lines.append("No paper NAV snapshots recorded for today.")
    else:
        for r in nav_rows_dict:
            strat = r["strategy_name"]
            unrealized = float(r["unrealized_pnl"])
            realized = float(r["realized_pnl"])
            total = float(r["total_pnl"])
            spot_val = r["underlying_price"]

            spot_text = ""
            if spot_val:
                spot_text = f" (Spot: ₹{float(spot_val):,.2f})"

            msg_lines.extend(
                [
                    f"🔹 <b>{strat}</b>{spot_text}",
                    f"  Unrealized: ₹{unrealized:+,.2f}",
                    f"  Realized: ₹{realized:+,.2f}",
                    f"  Total P&L: ₹{total:+,.2f}",
                    "",
                ]
            )

    full_message = "\n".join(msg_lines)

    # Send plain telegram message
    success = await gateway.send_plain_message(full_message)
    if success:
        logger.info("EOD summary sent successfully.")
    else:
        logger.warning("Failed to send EOD summary via Telegram.")

    return 0


if __name__ == "__main__":
    setup_logging()
    sys.exit(asyncio.run(main()))

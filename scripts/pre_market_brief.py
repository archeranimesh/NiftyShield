#!/usr/bin/env python3
"""Pre-market brief cron script.

Cron: 00 09 * * 1-5
Fetches open paper positions and sends a brief summary via Telegram.
"""

from __future__ import annotations

import asyncio
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

import structlog
from dotenv import load_dotenv

# Path setup must happen before importing local src modules
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Load environment before local imports
load_dotenv()

from src.backtest.ivr import compute_ivr  # noqa: E402
from src.backtest.vix_ingest import load_vix_series  # noqa: E402
from src.client.factory import create_client  # noqa: E402
from src.config import settings  # noqa: E402
from src.notifications.telegram_gateway import TelegramGateway  # noqa: E402
from src.paper.store import PaperStore  # noqa: E402
from src.paper.tracker import PaperTracker  # noqa: E402
from src.utils.logging import setup_logging  # noqa: E402

logger = structlog.get_logger("scripts.pre_market_brief")


async def get_current_ivr() -> float | None:
    """Compute trailing 252-day IVR for India VIX."""
    try:
        vix_dir = Path(settings.vix_data_dir)
        if not vix_dir.exists():
            return None
        series = await asyncio.to_thread(load_vix_series, vix_dir)
        if series.empty:
            return None

        vix_today = float(series.iloc[-1])
        historical = series.iloc[:-1]

        return compute_ivr(vix_today, historical)
    except Exception as e:
        # Intentional: Isolate VIX fetching and loading failures
        logger.warning("Failed to compute current IVR", error=str(e))
        return None


async def main() -> int:
    logger.info("Running pre-market brief...")

    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        logger.error("Telegram credentials missing in settings.")
        return 1

    store = PaperStore(settings.db_path)
    gateway = TelegramGateway(
        bot_token=settings.telegram_bot_token,
        chat_id=settings.telegram_chat_id,
        db_path=str(store.db_path),
    )

    # Use database-indexed strategies that have active positions/trades
    strategy_names = await asyncio.to_thread(store.get_strategy_names)
    if not strategy_names:
        logger.info("No paper strategies with trades found in database.")
        msg = (
            "☀️ <b>NiftyShield Pre-Market Brief</b>\n"
            + "No active paper trading strategies found in database."
        )
        await gateway.send_plain_message(msg)
        return 0

    broker = create_client(settings.upstox_env)
    tracker = PaperTracker(store=store, market=broker)

    ivr_val = await get_current_ivr()
    ivr_text = f"{ivr_val * 100:.1f}%" if ivr_val is not None else "N/A"

    msg_lines = [
        "☀️ <b>NiftyShield Pre-Market Brief</b>",
        f"Date: {date.today().isoformat()}",
        f"India VIX IVR: {ivr_text}",
        "",
    ]

    has_open_positions = False
    for name in strategy_names:
        # Only count legs with non-zero open positions
        positions = await asyncio.to_thread(store.get_positions, name)
        open_legs = [p for p in positions if p.net_qty != 0]
        if not open_legs:
            continue

        has_open_positions = True
        try:
            pnl_info = await tracker.compute_pnl(name)
            unrealized = pnl_info[0] if pnl_info else Decimal("0")
        except Exception as e:
            # Intentional: Isolate P&L calculation failures per strategy
            logger.warning(
                "Failed to compute P&L for strategy",
                strategy=name,
                error=str(e),
            )
            unrealized = Decimal("0")

        msg_lines.extend(
            [
                f"🔹 <b>{name}</b>",
                f"  Legs: {len(open_legs)}",
                f"  Unrealized P&L: ₹{float(unrealized):+,.2f}",
                "",
            ]
        )

    if not has_open_positions:
        no_pos_msg = "No active open positions across paper trading strategies."
        msg_lines.append(no_pos_msg)

    full_message = "\n".join(msg_lines)

    # Send plain telegram message
    success = await gateway.send_plain_message(full_message)
    if success:
        logger.info("Pre-market brief sent successfully.")
    else:
        logger.warning("Failed to send pre-market brief via Telegram.")

    return 0


if __name__ == "__main__":
    setup_logging()
    sys.exit(asyncio.run(main()))

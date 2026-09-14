#!/usr/bin/env python3
"""EOD summary cron script.

Cron: 35 15 * * 1-5
Fetches today's paper NAV snapshots and sends the EOD Paper Summary via Telegram
in the confirmed bucketed Flt/Bkd MarkdownV2 format (ROLL-6,
docs/plan/telegram-markdown-migration/strategy-rollout/stories.md; reference
scratch/2026-08-08_eod_paper_summary_format.py).

`Bkd` (realized) is sourced since-inception from get_strategy_realized_pnl() —
NOT paper_nav_snapshots.realized_pnl's latest row, which resets to 0 on a full
open->close->reopen cycle (CONTEXT.md SNAP-1). `Flt` (unrealized) stays a
point-in-time read from paper_nav_snapshots.unrealized_pnl's latest row.
"""

from __future__ import annotations

import asyncio
import sys
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import structlog
from dotenv import load_dotenv

# Path setup must happen before importing local src modules
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Load environment before local imports
load_dotenv()

from src.config import settings  # noqa: E402
from src.db import connect as _connect  # noqa: E402
from src.notifications.formatting import (  # noqa: E402
    StrategyPnLRow,
    build_strategy_table,
    format_summary_money,
    pnl_emoji,
)
from src.notifications.markdown import escape_markdown  # noqa: E402
from src.notifications.telegram import build_notifier  # noqa: E402
from src.paper.store import PaperStore  # noqa: E402
from src.paper.tracker import get_strategy_realized_pnl  # noqa: E402
from src.utils.logging import setup_logging  # noqa: E402

logger = structlog.get_logger("scripts.eod_summary")

# strategy_id -> (bucket, display label). Labels are bucket-prefix-free (§12) —
# the bucket's own total row establishes context. strategy_id values verified
# against src/paper/constants.py (Track/CSP/Overlay) and
# src/strategy/ic_expiry_config_v2.py::ICExpiryConfigV2.strategy_name (IC V2).
_STRATEGY_META: dict[str, tuple[str, str]] = {
    "paper_nifty_futures": ("Track", "Fut"),
    "paper_nifty_proxy": ("Track", "Proxy"),
    "paper_nifty_spot": ("Track", "Spot"),
    "paper_ic_nifty_v1_weekly": ("IC", "V1 Wkly"),
    "paper_ic_nifty_v1_monthly": ("IC", "V1 Mth"),
    "paper_ic_nifty_v1_leaps": ("IC", "V1 Leap"),
    "paper_ic_nifty_v1_yearly": ("IC", "V1 Yrly"),
    "paper_ic_nifty_v2_monthly": ("IC", "V2 Mth"),
    "paper_nifty_overlay": ("Overlay", "Overlay"),
    "paper_csp_nifty_v1": ("CSP", "V1"),
}
_BUCKET_ORDER = ["Track", "IC", "Overlay", "CSP"]

# Whole-message tag — this message aggregates every strategy in one send, unlike
# the per-variant IC EOD Audit. Sits on its own line AFTER the closing fence:
# MarkdownV2 does not parse entities (hashtag auto-detection included) inside a
# fenced block.
_MESSAGE_HASHTAG = "#EOD_SUMMARY"


def build_eod_summary_message(
    date_str: str,
    council_count: int,
    strategy_pnl: list[tuple[str, Decimal, Decimal]],
) -> str:
    """Render the confirmed EOD Paper Summary MarkdownV2 message.

    Args:
        date_str: header date label, e.g. "07 Aug 2026".
        council_count: number of council/approval activities today.
        strategy_pnl: (strategy_id, floating, booked) per strategy with a
            snapshot today. A strategy_id absent from `_STRATEGY_META` raises
            ValueError — a new strategy needs an explicit bucket assignment
            before it shows here, never a silent drop.

    Returns:
        The full message: header line + summary line + fenced bucketed table +
        hashtag line. Everything outside the fence is escaped for MarkdownV2;
        the fenced table is passed through verbatim (§6 escaping contract).
    """
    # Round each strategy's figures to whole rupees up front so the table foots
    # exactly: member cells, bucket subtotals, and the Net P&L line are then all
    # sums of the same integers (rounding the raw Decimals independently at each
    # level would let a bucket subtotal or the Net line drift ±₹1 from what the
    # rows visibly add up to — unacceptable for a summary someone eyeballs).
    rows: list[StrategyPnLRow] = []
    for strategy_id, floating, booked in strategy_pnl:
        meta = _STRATEGY_META.get(strategy_id)
        if meta is None:
            raise ValueError(f"eod_summary: strategy_id not mapped to a bucket: {strategy_id!r}")
        bucket, label = meta
        rows.append(
            StrategyPnLRow(
                label=label,
                bucket=bucket,
                floating=floating.quantize(Decimal("1"), rounding=ROUND_HALF_UP),
                booked=booked.quantize(Decimal("1"), rounding=ROUND_HALF_UP),
            )
        )

    total_pnl = sum((r.floating + r.booked for r in rows), Decimal("0"))
    table = build_strategy_table(rows, _BUCKET_ORDER)

    # format_summary_money returns "-" for zero, else a sign-prefixed integer.
    net = format_summary_money(total_pnl)
    if net == "-":
        net_str = "₹0"
    else:
        net_str = f"{net[0]}₹{net[1:]}"  # sign, then the sole ₹ in the whole message

    header_line = escape_markdown(f"📝 NiftyShield Paper EOD | {date_str}")
    summary_line = escape_markdown(
        f"Activities: {council_count} | Net P&L: {net_str} {pnl_emoji(total_pnl)}"
    )
    hashtag_line = escape_markdown(_MESSAGE_HASHTAG)
    return f"{header_line}\n{summary_line}\n```\n{table}\n```\n{hashtag_line}"


async def main() -> int:
    logger.info("Running EOD summary...")

    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        logger.error("Telegram credentials missing in settings.")
        return 1

    store = PaperStore(settings.db_path)
    today_str = date.today().isoformat()

    def _fetch_data() -> tuple[list[tuple[str, Decimal, Decimal]], int]:
        with _connect(store.db_path) as conn:
            nav_rows = conn.execute(
                "SELECT strategy_name, unrealized_pnl "
                "FROM paper_nav_snapshots "
                "WHERE snapshot_date = ? "
                "ORDER BY strategy_name",
                (today_str,),
            ).fetchall()

            count_query = "SELECT COUNT(*) FROM pending_approvals "
            count_query += "WHERE date(created_at, '+5 hours', '+30 minutes') = ?"
            count_row = conn.execute(count_query, (today_str,)).fetchone()
            council_count = count_row[0] if count_row else 0

            strategy_names = [r["strategy_name"] for r in nav_rows]
            floating_by_name = {
                r["strategy_name"]: Decimal(str(r["unrealized_pnl"])) for r in nav_rows
            }

        # Realized P&L reads open their own connection via `store`; keep them out
        # of the connect() block above. Still on this worker thread (single
        # asyncio.to_thread call), so no cross-thread SQLite handle sharing.
        strategy_pnl = [
            (name, floating_by_name[name], get_strategy_realized_pnl(store, name))
            for name in strategy_names
        ]
        return strategy_pnl, council_count

    try:
        strategy_pnl, council_count = await asyncio.to_thread(_fetch_data)
    except Exception as e:
        # Intentional: Isolate database loading failures from crashing cron
        logger.error(
            "Database query failed during EOD summary compilation",
            error=str(e),
        )
        return 1

    if not strategy_pnl:
        logger.info("No paper NAV snapshots recorded for today; skipping EOD summary.")
        return 0

    try:
        message = build_eod_summary_message(
            date.today().strftime("%d %b %Y"), council_count, strategy_pnl
        )
    except ValueError as e:
        logger.error("EOD summary message build failed", error=str(e))
        return 1

    notifier = build_notifier()
    if notifier is None:
        logger.error("Telegram credentials missing in settings.")
        return 1

    success = await notifier.send(message)
    if success:
        logger.info("EOD summary sent successfully.")
    else:
        logger.warning("Failed to send EOD summary via Telegram.")

    return 0


if __name__ == "__main__":
    setup_logging()
    sys.exit(asyncio.run(main()))

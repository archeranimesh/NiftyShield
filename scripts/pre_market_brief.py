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
from src.client.protocol import BrokerClient  # noqa: E402
from src.config import settings  # noqa: E402
from src.notifications.formatting import format_expiry, format_money, strategy_label  # noqa: E402
from src.notifications.markdown import escape_markdown  # noqa: E402
from src.notifications.telegram_gateway import TelegramGateway  # noqa: E402
from src.paper.constants import STRATEGY_OVERLAY  # noqa: E402
from src.paper.cycle_pnl import resolve_target  # noqa: E402
from src.paper.models import PaperPosition  # noqa: E402
from src.paper.store import PaperStore  # noqa: E402
from src.paper.tracker import _compute_leg_unrealized_pnl  # noqa: E402

# _compute_leg_unrealized_pnl is intentionally reused rather than duplicated —
# it is the single source of truth for the short/long P&L formula (see
# src/paper/tracker.py); reimplementing it here would risk the two drifting.
from src.utils.logging import setup_logging  # noqa: E402

logger = structlog.get_logger("scripts.pre_market_brief")


async def _compute_unrealized_with_fallback(
    store: PaperStore,
    broker: BrokerClient,
    strategy_name: str,
    positions: list[PaperPosition],
) -> Decimal:
    """Compute unrealized P&L for a strategy's open legs, pre-market safe.

    Futures have no pre-open session, so ``get_ltp`` returns nothing for
    them before market open — treating that as a live price of 0 would
    report a large notional loss that doesn't exist. For any FUT leg with
    no usable live LTP, fall back to the most recent EOD ``paper_leg_snapshots``
    row for that leg instead of pricing it at zero. Non-futures legs are
    unaffected: pre-market LTP for options/equity is expected to already be
    the prior close and is used as-is.

    Args:
        store: Paper trading store, for the EOD snapshot fallback lookup.
        broker: Broker client used to fetch live LTPs.
        strategy_name: Paper strategy name (must start with ``paper_``).
        positions: Open (net_qty != 0) positions for this strategy.

    Returns:
        Total unrealized P&L across the given positions.
    """
    instrument_keys = [p.instrument_key for p in positions if p.instrument_key]
    prices: dict[str, Decimal] = {}
    if instrument_keys:
        prices = await broker.get_ltp(instrument_keys)

    today = date.today()
    unrealized = Decimal("0")
    for pos in positions:
        ltp = prices.get(pos.instrument_key)
        if pos.option_type == "FUT" and (ltp is None or ltp == Decimal("0")):
            snapshot = await asyncio.to_thread(
                store.get_prev_leg_snapshot, strategy_name, pos.leg_role, today
            )
            if snapshot is not None:
                unrealized += snapshot.unrealized_pnl
                continue
            logger.warning(
                "No live LTP and no prior EOD snapshot for futures leg; "
                "reporting zero unrealized P&L for this leg",
                strategy=strategy_name,
                leg_role=pos.leg_role,
            )
            # Deliberately skip _compute_leg_unrealized_pnl here — pricing a
            # futures leg at 0 is exactly the fabricated-notional-loss bug
            # this fallback exists to avoid (RO-2). No snapshot means no
            # informed P&L is available, so report zero for this leg only.
            continue
        elif ltp is None:
            ltp = Decimal("0")
        unrealized += _compute_leg_unrealized_pnl(pos, ltp)

    return unrealized


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


_OVERLAY_SUBGROUPS = ("cc", "collar", "pp")
_OVERLAY_SUB_PREFIX = {"cc": "├ CC", "collar": "├ Collar", "pp": "└ PP"}


def _build_brief_table(rows: list[tuple[str, str, str]]) -> str:
    """Fenced-ready `Strategy | Legs | Unrealized P&L` table.

    Args:
        rows: `(label, legs, pnl)` triples, already rendered as display strings
            (a sub-group with no open legs passes `"—"` for both). Caller
            supplies the trailing `Total` row as an ordinary row.

    Returns:
        The table body, column-aligned. Caller wraps it in a fenced block.
    """
    header = ("Strategy", "Legs", "Unrealized P&L")
    name_col = max(len(header[0]), *(len(r[0]) for r in rows))
    legs_col = max(len(header[1]), *(len(r[1]) for r in rows))
    pnl_col = max(len(header[2]), *(len(r[2]) for r in rows))
    lines = [
        f"{header[0]:<{name_col}} | {header[1]:>{legs_col}} | {header[2]:>{pnl_col}}",
        f"{'-' * name_col}-|-{'-' * legs_col}-|-{'-' * pnl_col}",
    ]
    for label, legs, pnl in rows:
        lines.append(f"{label:<{name_col}} | {legs:>{legs_col}} | {pnl:>{pnl_col}}")
    return "\n".join(lines)


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

    header_lines = ["☀️ *NiftyShield Pre\\-Market Brief*"]

    # Use database-indexed strategies that have active positions/trades
    strategy_names = await asyncio.to_thread(store.get_strategy_names)
    if not strategy_names:
        logger.info("No paper strategies with trades found in database.")
        header_lines.append(
            escape_markdown("No active paper trading strategies found in database.")
        )
        await gateway.send_plain_message("\n".join(header_lines))
        return 0

    broker = create_client(settings.upstox_env)

    ivr_val = await get_current_ivr()
    ivr_text = f"{ivr_val * 100:.1f}%" if ivr_val is not None else "N/A"
    header_lines.append(
        f"*Date:* {escape_markdown(format_expiry(date.today()))}   "
        f"*India VIX IVR:* {escape_markdown(ivr_text)}"
    )

    async def _safe_unrealized(strategy_name: str, positions: list[PaperPosition]) -> Decimal:
        try:
            return await _compute_unrealized_with_fallback(store, broker, strategy_name, positions)
        except Exception as e:
            # Intentional: Isolate P&L calculation failures per strategy
            logger.warning(
                "Failed to compute P&L for strategy",
                strategy=strategy_name,
                error=str(e),
            )
            return Decimal("0")

    rows: list[tuple[str, str, str]] = []
    total_legs = 0
    total_pnl = Decimal("0")
    has_open_positions = False

    for name in strategy_names:
        # Only count legs with non-zero open positions
        positions = await asyncio.to_thread(store.get_positions, name)
        open_legs = [p for p in positions if p.net_qty != 0]
        if not open_legs:
            continue

        has_open_positions = True
        unrealized = await _safe_unrealized(name, open_legs)
        rows.append(
            (strategy_label(name), str(len(open_legs)), format_money(unrealized, signed=True))
        )
        total_legs += len(open_legs)
        total_pnl += unrealized

        if name == STRATEGY_OVERLAY:
            for alias in _OVERLAY_SUBGROUPS:
                (group,) = resolve_target(alias)
                sub_legs = [p for p in open_legs if p.leg_role in (group.leg_roles or ())]
                prefix = _OVERLAY_SUB_PREFIX[alias]
                if not sub_legs:
                    rows.append((prefix, "—", "—"))
                    continue
                sub_unrealized = await _safe_unrealized(name, sub_legs)
                rows.append((prefix, str(len(sub_legs)), format_money(sub_unrealized, signed=True)))

    if not has_open_positions:
        header_lines.append(
            escape_markdown("No active open positions across paper trading strategies.")
        )
        full_message = "\n".join(header_lines)
    else:
        rows.append(("Total", str(total_legs), format_money(total_pnl, signed=True)))
        table = "\n".join(["```", _build_brief_table(rows), "```"])
        full_message = "\n".join([*header_lines, "", table])

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

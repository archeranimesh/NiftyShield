#!/usr/bin/env python3
"""Hourly watch cron for MVP picks: LTP fetch, snapshot recording, auto-close.

Cron schedule: 0 9-15 * * 1-5

For each open pick with an `instrument_key`, fetches the latest LTP via
`BrokerClient.get_ltp`, records a snapshot, then auto-closes any pick whose
target or stop-loss was breached (`check_prices`). Sends a per-alert
Telegram message for each breach, then a consolidated hourly summary.
"""

from __future__ import annotations

import asyncio
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import structlog
from dotenv import load_dotenv

# Path setup must happen before importing local src modules
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Load environment before local imports
load_dotenv()

from src.client.factory import create_client  # noqa: E402
from src.config import settings  # noqa: E402
from src.mvp.models import (  # noqa: E402
    CategoryStats,
    ClosePickResult,
    MVPSnapshot,
    Pick,
    PickStatus,
)
from src.mvp.store import MVPStore  # noqa: E402
from src.mvp.tracker import (  # noqa: E402
    MVPEvent,
    check_prices,
    format_hourly_summary,
)
from src.notifications.formatting import format_money, format_pct  # noqa: E402
from src.notifications.markdown import escape_markdown  # noqa: E402
from src.notifications.telegram import build_notifier  # noqa: E402
from src.utils.logging import setup_logging  # noqa: E402

_SCRIPT_NAME = "scripts.mvp_watch"
logger = structlog.get_logger(_SCRIPT_NAME)


async def run() -> None:
    """Fetch LTP for all open picks, record snapshots,
    and auto-close breaches."""
    store = MVPStore(settings.db_path)
    picks = await asyncio.to_thread(store.get_open_picks)
    if not picks:
        logger.info("mvp_watch.no_open_picks")
        return

    keyed_picks: dict[str, Pick] = {}
    for pick in picks:
        if pick.instrument_key is None:
            continue
        if pick.instrument_key in keyed_picks:
            logger.warning(
                "mvp_watch.duplicate_instrument_key",
                instrument_key=pick.instrument_key,
                kept=keyed_picks[pick.instrument_key].pick_id,
                dropped=pick.pick_id,
            )
            continue
        keyed_picks[pick.instrument_key] = pick
    if not keyed_picks:
        logger.info("mvp_watch.no_picks_with_instrument_key")
        return

    broker = create_client(settings.upstox_env)
    ltp_map = await broker.get_ltp(list(keyed_picks))

    now = datetime.now(timezone.utc).isoformat()
    for instrument_key, pick in keyed_picks.items():
        ltp = ltp_map.get(instrument_key)
        if ltp is None:
            logger.warning(
                "mvp_watch.ltp_missing",
                pick_id=pick.pick_id,
                instrument_key=instrument_key,
            )
            continue
        await asyncio.to_thread(
            store.record_snapshot,
            MVPSnapshot(pick_id=pick.pick_id, ltp=ltp, captured_at=now),
        )

    picks_by_id: dict[str, Pick] = {pick.pick_id: pick for pick in keyed_picks.values()}

    events = check_prices(list(keyed_picks.values()), ltp_map)
    close_results: dict[str, ClosePickResult] = {}
    for event in events:
        close_results[event.pick_id] = await asyncio.to_thread(
            store.close_pick,
            event.pick_id,
            event.trigger_price,
            event.event_type,
        )
        logger.info(
            "mvp_watch.pick_closed",
            pick_id=event.pick_id,
            symbol=event.symbol,
            event_type=event.event_type.value,
            trigger_price=str(event.trigger_price),
        )

    notifier = build_notifier()
    if notifier is not None:
        providers = await asyncio.to_thread(store.list_providers)
        provider_names = {provider.provider_id: provider.display_name for provider in providers}
        categories = []
        for provider in providers:
            categories.extend(await asyncio.to_thread(store.list_categories, provider.provider_id))
        joined_category_labels = {
            category.category_id: (
                f"{provider_names.get(category.provider_id, category.provider_id)}"
                f" / {category.display_name}"
            )
            for category in categories
        }

        for event in events:
            pick = picks_by_id.get(event.pick_id)
            if pick is None:
                continue
            label = _pick_label(pick, joined_category_labels)
            close = close_results[event.pick_id]
            stats = (
                await asyncio.to_thread(store.get_category_stats, pick.category_id)
                if pick.category_id is not None
                else None
            )
            await notifier.send(_format_alert_message(event, pick, close, label, stats))

        open_picks = await asyncio.to_thread(store.get_open_picks)
        pending_picks = await asyncio.to_thread(store.list_picks, PickStatus.PENDING)
        run_time = datetime.now(timezone.utc).astimezone().strftime("%I:%M %p").lstrip("0")
        summary = format_hourly_summary(open_picks + pending_picks, ltp_map, run_time)
        if summary:
            await notifier.send(summary)


def _pick_label(pick: Pick | None, category_labels: dict[str, str]) -> str:
    """Look up a pick's "Provider / Category" label, or "" if unresolvable."""
    if pick is None or pick.category_id is None:
        return ""
    return category_labels.get(pick.category_id, "")


MIN_CLOSED_FOR_STATS = 5  # same threshold as src.notifications.exit_message._win_rate_line


def _format_alert_message(
    event: MVPEvent,
    pick: Pick,
    close: ClosePickResult,
    label: str,
    stats: CategoryStats | None = None,
) -> str:
    """Render a single-pick target/SL breach as a MarkdownV2 close alert.

    IC exit-message visual language at MVP's smaller scale: headline ->
    `Provider / Category Held: Nd` kv line -> fenced Entry/Exit/P&L table ->
    `---` separator -> a footer line with return %, qty, deployed capital ->
    an optional category win-rate/inception stats line (M11), shown only
    when the category has at least ``MIN_CLOSED_FOR_STATS`` closed picks.
    """
    if event.event_type == PickStatus.TARGET_HIT:
        header = f"\U0001f3af *TARGET HIT* — {escape_markdown(event.symbol)}"
    else:
        header = f"\U0001f6d1 *SL HIT* — {escape_markdown(event.symbol)}"

    held_days = (date.today() - date.fromisoformat(pick.pick_date[:10])).days
    kv = f"{label} Held: {held_days}d" if label else f"Held: {held_days}d"

    entry_str = format_money(close.avg_cost) if close.avg_cost is not None else "-"
    table = "\n".join(
        [
            f"Entry : {entry_str}",
            f"Exit  : {format_money(event.trigger_price)}",
            f"P&L   : {format_money(close.realized_pnl, signed=True)}",
        ]
    )

    if close.deployed_capital > 0:
        return_pct = close.realized_pnl / close.deployed_capital * 100
        sign = "+" if return_pct > 0 else ""
        return_str = f"{sign}{format_pct(float(return_pct))}"
    else:
        return_str = "-"

    sep = escape_markdown(" | ")
    footer = (
        f"Return: {escape_markdown(return_str)}{sep}"
        f"Qty: {close.total_qty}{sep}"
        f"Deployed: {escape_markdown(format_money(close.deployed_capital))}"
    )

    lines = [
        header,
        escape_markdown(kv),
        "",
        "```",
        table,
        "```",
        "━━━━━━━━━━━━━━━━━━━━━━━━",
        footer,
    ]
    stats_line = _category_stats_line(stats)
    if stats_line:
        lines.append(stats_line)
    return "\n".join(lines)


def _category_stats_line(stats: CategoryStats | None) -> str | None:
    """``🎯 Win rate: {r}% ({W}W / {L}L)  |  📈 Inception: {pnl}``.

    ``None`` when ``stats`` is missing or the category has fewer than
    ``MIN_CLOSED_FOR_STATS`` closed picks (same gate as
    ``exit_message._win_rate_line``).
    """
    if stats is None or stats.closed_count < MIN_CLOSED_FOR_STATS or stats.win_rate is None:
        return None

    rate = escape_markdown(f"{stats.win_rate * 100:.0f}")
    wins = escape_markdown(str(stats.wins))
    losses = escape_markdown(str(stats.losses))
    inception = escape_markdown(format_money(stats.inception_pnl, signed=True))
    sep = escape_markdown(" | ")
    return (
        f"\U0001f3af Win rate: {rate}%  \\({wins}W / {losses}L\\){sep}"
        f"\U0001f4c8 Inception: {inception}"
    )


if __name__ == "__main__":
    setup_logging()
    asyncio.run(run())

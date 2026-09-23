#!/usr/bin/env python3
"""Hourly watch cron for MVP picks: LTP fetch, snapshot recording, auto-close.

Cron schedule: 0 9-15 * * 1-5

For each open pick with an `instrument_key`, fetches the latest LTP via
`BrokerClient.get_ltp`, records a snapshot, then auto-closes any pick whose
target or stop-loss was breached (`check_prices`). Telegram alerts land in
M4.2 — this pass only logs and persists.
"""

from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path

import structlog
from dotenv import load_dotenv

# Path setup must happen before importing local src modules
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Load environment before local imports
load_dotenv()

from src.client.factory import create_client  # noqa: E402
from src.config import settings  # noqa: E402
from src.mvp.models import MVPSnapshot, Pick  # noqa: E402
from src.mvp.store import MVPStore  # noqa: E402
from src.mvp.tracker import check_prices  # noqa: E402
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

    events = check_prices(list(keyed_picks.values()), ltp_map)
    for event in events:
        await asyncio.to_thread(
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


if __name__ == "__main__":
    setup_logging()
    asyncio.run(run())

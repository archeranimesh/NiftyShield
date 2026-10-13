"""Entry-time margin capture shared by every paper strategy entry script."""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

import structlog

from src.client.protocol import BrokerClient
from src.paper.models import MarginSnapshot
from src.paper.store import PaperStore

logger = structlog.get_logger(__name__)


async def capture_entry_margin(
    broker: BrokerClient,
    store: PaperStore,
    strategy_name: str,
    entry_date: date,
    legs: list[tuple[str, str, int]],
    *,
    product: str = "D",
) -> MarginSnapshot | None:
    """Fetch and persist the entry-cycle margin snapshot for a just-opened structure.

    Called once, after all legs of an entry cycle are confirmed persisted to
    ``paper_trades`` — never on a re-run of an already-open position. Failure
    here (network error, expired Daily OAuth token, bad instrument key) is
    logged and swallowed, never raised: margin capture is a reporting
    convenience, not a condition of a successful entry. A missing snapshot
    just means ``get_margin_snapshot`` returns None later and the EOD report
    skips ROI-on-margin for that cycle.

    Args:
        broker: BrokerClient with get_order_margin wired (UpstoxLiveClient in
            practice — MockBrokerClient in tests).
        store: Open PaperStore instance.
        strategy_name: DB strategy name (e.g. ``paper_ic_nifty_v2_monthly``).
        entry_date: Date this entry cycle opened — stamped onto the snapshot,
            must match the value ``PaperPosition.entry_date`` will later
            resolve to for the same cycle.
        legs: List of ``(instrument_key, action, quantity)`` tuples — action
            is ``"BUY"``/``"SELL"``, matching Upstox's transaction_type.
        product: Upstox product code. Default ``"D"`` (delivery/NRML),
            matching how paper strategies are conceptually held.

    Returns:
        The persisted MarginSnapshot, or None if the margin-calculator call
        or the DB write failed.
    """
    instruments = [
        {
            "instrument_key": key,
            "quantity": qty,
            "transaction_type": action,
            "product": product,
        }
        for key, action, qty in legs
    ]
    try:
        margin_data = await broker.get_order_margin(instruments)
        snapshot = MarginSnapshot(
            strategy_name=strategy_name,
            entry_date=entry_date,
            required_margin=Decimal(str(margin_data["required_margin"])),
            final_margin=Decimal(str(margin_data["final_margin"])),
            captured_at=datetime.now(timezone.utc),
        )
        store.record_margin_snapshot(snapshot)
    except Exception as exc:  # noqa: BLE001 — margin capture must never block/fail entry
        logger.warning(
            "capture_entry_margin.failed",
            strategy_name=strategy_name,
            entry_date=str(entry_date),
            error=str(exc),
        )
        return None

    logger.info(
        "capture_entry_margin.recorded",
        strategy_name=strategy_name,
        entry_date=str(entry_date),
        final_margin=str(snapshot.final_margin),
    )
    return snapshot

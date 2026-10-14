"""Close and re-centre Telegram message for NiftyCalendarV1 (non-fatal).

Builds the ``ExitMessage`` from the just-closed legs and the ledger, then sends it through
the injected notifier (a ``TelegramGateway``: it needs ``send_notification``). A re-centre renders as a roll; the entry card for the re-entered
structure follows from the entry script, which runs in another process.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

import structlog

from src.instruments.lookup import InstrumentLookup
from src.notifications.calendar_messages import build_calendar_exit_message, leg_instrument
from src.notifications.exit_message import format_exit_message
from src.notifications.formatting import CloseLegRow
from src.notifications.protocol import NotifierProtocol
from src.paper.cycle_pnl import cycle_stats, reconstruct_cycles
from src.paper.store import PaperStore
from src.strategy.nifty_calendar_state import (
    LONG_CALL_WING,
    LONG_PUT_WING,
    SHORT_CALL,
    SHORT_PUT,
)

log = structlog.get_logger(__name__)

_ROLE_LABELS = {
    SHORT_CALL: "Short Call",
    SHORT_PUT: "Short Put",
    LONG_CALL_WING: "Long Call",
    LONG_PUT_WING: "Long Put",
}


@dataclass(frozen=True)
class ClosedLeg:
    """One leg closed in this action: its role, key, entry price, exit fill and quantity."""

    role: str
    instrument_key: str
    entry: Decimal
    exit: Decimal
    quantity: int


def _close_row(leg: ClosedLeg, lookup: InstrumentLookup) -> CloseLegRow:
    inst = lookup.get_by_key(leg.instrument_key) or {}
    label = (
        leg_instrument(Decimal(str(inst["strike_price"])), str(inst["instrument_type"]))
        if "strike_price" in inst
        else leg.instrument_key
    )
    short = leg.role in (SHORT_CALL, SHORT_PUT)
    gain = (leg.entry - leg.exit) if short else (leg.exit - leg.entry)
    return CloseLegRow(
        role=_ROLE_LABELS.get(leg.role, leg.role),
        instrument=label,
        entry=leg.entry,
        exit=leg.exit,
        pnl=gain * leg.quantity,
    )


async def send_close_message(
    notifier: NotifierProtocol | None,
    store: PaperStore,
    lookup: InstrumentLookup,
    *,
    strategy_name: str,
    signal: str,
    near_expiry: date,
    today: date,
    held_days: int,
    legs: list[ClosedLeg],
    recentre: bool,
    label: str = "Cal M",
) -> None:
    """Send the close (or re-centre) card; any failure is logged, never raised."""
    if notifier is None or not legs:
        return
    try:
        # Deferred: src.paper.tracker -> store -> src.strategy imports would cycle at module load.
        from src.paper.tracker import get_strategy_realized_pnl

        rows = [_close_row(leg, lookup) for leg in legs]
        trades = store.get_trades(strategy_name)
        cycles = reconstruct_cycles(trades)
        closed = cycles[-1] if cycles and not cycles[-1].is_open else None
        this_exit = sum((r.pnl for r in rows), Decimal("0"))
        message = build_calendar_exit_message(
            signal=signal,
            near_dte=(near_expiry - today).days,
            held_days=held_days,
            legs=rows,
            cycle_pnl=closed.realized_pnl if closed else this_exit,
            cycle_index=closed.index if closed else len(cycles),
            inception_pnl=get_strategy_realized_pnl(store, strategy_name),
            stats=cycle_stats(trades),
            recentre=recentre,
            headline_label=label,
        )
        # Pre-rendered MarkdownV2 card: sent through send_notification like every other close card.
        send = getattr(notifier, "send_notification", None)
        if send is None:
            log.warning("nifty_calendar.close_message_no_send_notification")
            return
        await send(format_exit_message(message))
    except Exception as exc:  # noqa: BLE001 -- Intentional: notification must never undo a persisted close
        log.warning("nifty_calendar.close_message_failed", error=str(exc))

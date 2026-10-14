# scripts/strategies/nifty_calendar/paper_calendar_entry.py
"""Entry script for the Nifty positional calendar (``--variant monthly|biweekly``).

The monitor never ticks a flat strategy, so this script calls ``NiftyCalendarV1.plan_entry``
and ``apply_action`` directly (entry events must not go through the monitor, whose close path
would treat their empty ``legs_to_close`` as a default close). It also re-enters the same day
after a RECENTRE close, under the original cycle's plan (Animesh, 2026-10-13).

Default is ``--dry-run``: chains are fetched and the proposed legs printed; nothing is written
or sent. Exits quietly when the chosen variant's entry window is not the active one, so cron can
run both variants unconditionally. ``--no-dry-run`` persists the four legs, captures margin, and sends the entry card
and payoff chart. Cron lines live in the CM-8 cutover note, not here.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Protocol
from zoneinfo import ZoneInfo

import structlog
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from src.backtest.vix_ingest import fetch_vix_latest
from src.client.factory import create_client
from src.client.protocol import BrokerClient
from src.client.upstox_market import parse_upstox_option_chain
from src.config import settings
from src.instruments.lookup import InstrumentLookup
from src.market_calendar.holidays import guard_trading_day
from src.models.options import OptionChain
from src.nifty_calendar.cycle import active_variant
from src.nifty_calendar.selector import mid
from src.notifications.calendar_messages import build_calendar_entry_message
from src.notifications.entry_message import format_entry_message
from src.notifications.markdown import escape_markdown
from src.notifications.payoff_chart import send_payoff_chart
from src.notifications.telegram_gateway import TelegramGateway
from src.paper.constants import DEFAULT_BOD_PATH, DEFAULT_DB_PATH
from src.paper.margin_capture import capture_entry_margin
from src.paper.store import PaperStore
from src.payoff.registry import PayoffContext
from src.strategy.nifty_calendar_factory import REGISTRY, build_calendar_shell, build_cycle_policies
from src.strategy.nifty_calendar_state import ROLES, build_view, resolve_open_legs
from src.strategy.nifty_calendar_v1 import NiftyCalendarV1
from src.strategy.payoff_registrations import ensure_registered
from src.strategy.protocol import ApprovedAction, LegClose
from src.utils.logging import setup_logging

load_dotenv()

_SCRIPT_NAME = "scripts.strategies.nifty_calendar.paper_calendar_entry"
logger = structlog.get_logger(_SCRIPT_NAME)

_IST = ZoneInfo("Asia/Kolkata")
_NIFTY = "NSE_INDEX|Nifty 50"
_SHORT_ROLES = ("short_call", "short_put")


class _Notifier(Protocol):
    """The gateway surface this script uses (text and photo)."""

    async def send_plain_message(self, text: str) -> bool: ...

    async def send_notification(self, message: str) -> None: ...

    async def send_photo(self, png: bytes, *, caption: str = "") -> None: ...


async def _fetch_chain(broker: BrokerClient, expiry: date) -> OptionChain | None:
    """Fetch and parse one expiry's chain; None when the fetch fails or returns no strikes."""
    try:
        raw = await asyncio.wait_for(broker.get_option_chain(_NIFTY, expiry.isoformat()), 15.0)
    except Exception as exc:  # noqa: BLE001 — any fetch failure is a fail-closed "no chain"
        logger.error("calendar_entry.chain_fetch_failed", expiry=str(expiry), error=str(exc))
        return None
    chain = parse_upstox_option_chain(raw if isinstance(raw, list) else [])
    return chain if chain.strikes else None


async def _alert(notifier: _Notifier | None, text: str) -> None:
    """Send a plain-text alert; Telegram is non-fatal."""
    if notifier is None:
        return
    try:
        await notifier.send_plain_message(escape_markdown(text))
    except Exception as exc:  # noqa: BLE001 — Intentional: telegram must never abort the script
        logger.warning("calendar_entry.alert_failed", error=str(exc))


async def _send_entry_card(
    shell: NiftyCalendarV1,
    store: PaperStore,
    broker: BrokerClient,
    lookup: InstrumentLookup,
    notifier: _Notifier,
    first_chain: OptionChain,
    today: date,
    margin_final: Decimal | None,
) -> None:
    """Entry message plus payoff chart for the structure just persisted (non-fatal)."""
    config = shell.config
    positions = [p for p in store.get_positions(shell.strategy_name) if p.net_qty != 0]
    legs = resolve_open_legs(positions, lookup)
    chains = {first_chain.expiry: first_chain}
    for expiry in {leg.expiry for leg in legs.values()} - chains.keys():
        fetched = await _fetch_chain(broker, expiry)
        if fetched is not None:
            chains[expiry] = fetched
    view = build_view(positions, lookup, chains, first_chain.underlying_spot, config.lot_size)
    spot = first_chain.underlying_spot
    ltps = {leg.position.instrument_key: mid(view.quotes[r]) for r, leg in view.legs.items()}
    card = build_calendar_entry_message(
        view.structure, view.metrics, spot, today, ltps=ltps, headline_label=config.label
    )
    await notifier.send_notification(format_entry_message(card))
    ensure_registered()
    await send_payoff_chart(
        notifier,  # type: ignore[arg-type]  # PhotoSender: TelegramGateway.send_photo
        shell.strategy_name,
        PayoffContext(
            positions=positions,
            spot=spot,
            lot_size=config.lot_size,
            strategy_name=shell.strategy_name,
            extras={"structure": view.structure, "far_carry": view.carry},
        ),
        dte=(view.near_expiry - today).days,
        margin=margin_final,
    )


def _other_variant_open(store: PaperStore, variant: str) -> str | None:
    """Return the strategy name of another registered variant holding positions, if any."""
    for other, entry in REGISTRY.items():
        name = entry.config.strategy_name
        if other != variant and any(p.net_qty != 0 for p in store.get_positions(name)):
            return name
    return None


async def run_entry(
    *,
    shell: NiftyCalendarV1,
    store: PaperStore,
    broker: BrokerClient,
    lookup: InstrumentLookup,
    notifier: _Notifier | None,
    now: datetime,
    dry_run: bool,
) -> str:
    """Run one entry attempt and return its outcome code.

    Outcomes: ``ALREADY_OPEN``, ``NOT_ACTIVE`` (another variant owns today),
    ``OTHER_VARIANT_OPEN`` (another variant still holds a structure), ``NO_EXPIRY``,
    ``CHAIN_FAILED``, ``NO_ENTRY`` (no window, too early, a blocking trade today, or a failed
    filter), ``DRY_RUN``, ``ENTERED`` and ``INCOMPLETE`` (a leg did not land; manual
    intervention needed).

    Args:
        shell: Wired strategy shell.
        store: Paper ledger (the duplicate-position guard reads it).
        broker: Chain and margin source.
        lookup: BOD instrument lookup.
        notifier: Telegram gateway, or None.
        now: IST timestamp.
        dry_run: True prints the proposal and writes nothing.
    """
    name = shell.strategy_name
    if any(p.net_qty != 0 for p in store.get_positions(name)):
        logger.info("calendar_entry.already_open", strategy=name)
        return "ALREADY_OPEN"
    today = now.date()
    policies = build_cycle_policies(lookup, today)
    if active_variant(today, policies) != shell.config.name:
        logger.info("calendar_entry.variant_not_active", strategy=name, today=str(today))
        return "NOT_ACTIVE"
    if others := _other_variant_open(store, shell.config.name):
        logger.info("calendar_entry.other_variant_open", strategy=name, open_strategy=others)
        return "OTHER_VARIANT_OPEN"
    plan = policies[shell.config.name].entry_window(today)
    if plan is None:
        logger.error("calendar_entry.no_expiry", strategy=name)
        return "NO_EXPIRY"
    label = shell.config.label
    market = await _fetch_chain(broker, plan.near_expiry)
    if market is None:
        await _alert(notifier, f"{label} entry blocked ({name}): option chain unavailable")
        return "CHAIN_FAILED"
    events = await shell.plan_entry(market, now)
    entry = next((e for e in events if e.event_type == "NC_ENTRY"), None)
    if entry is None:
        for e in events:
            logger.warning("calendar_entry.no_entry", code=e.event_type, reason=e.description)
            await _alert(
                notifier, f"{label} entry skipped ({name}): {e.event_type} {e.description}"
            )
        return "NO_ENTRY"
    specs = entry.payload["legs_to_open"]
    if dry_run:
        for s in specs:
            print(
                f"[DRY-RUN] {s.leg_role:<15} {s.action:<4} {s.quantity} @ {s.price}  {s.instrument_key}"
            )
        return "DRY_RUN"
    action = ApprovedAction(
        action_type=entry.payload["auto_action"],
        legs_to_close=[LegClose(**d) for d in entry.payload["legs_to_close"]],
        legs_to_open=specs,
        rationale="entry script",
        council_rank=1,
        metadata=dict(entry.payload),
    )
    positions = [p for p in await shell.apply_action([], action) if p.net_qty != 0]
    missing = [r for r in ROLES if r not in {p.leg_role for p in positions}]
    if missing:
        logger.error("calendar_entry.legs_not_persisted", strategy=name, missing=missing)
        await _alert(
            notifier,
            f"{label} entry INCOMPLETE ({name}): legs {missing} did not land. "
            "Partial structure is open: manual intervention required.",
        )
        return "INCOMPLETE"
    entry_dates = [p.entry_date for p in positions if p.leg_role in _SHORT_ROLES and p.entry_date]
    snapshot = await capture_entry_margin(
        broker, store, name, min(entry_dates, default=today),
        [(s.instrument_key, s.action, s.quantity) for s in specs],
    )  # fmt: skip
    if notifier is not None:
        try:
            await _send_entry_card(
                shell, store, broker, lookup, notifier, market, today,
                snapshot.final_margin if snapshot else None,
            )  # fmt: skip
        except Exception as exc:  # noqa: BLE001 — Intentional: message failure never undoes an entry
            logger.warning("calendar_entry.message_failed", error=str(exc))
    return "ENTERED"


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description="Nifty calendar paper entry.")
    parser.add_argument(
        "--variant", required=True, choices=sorted(REGISTRY), help="Calendar variant to enter."
    )
    parser.add_argument(
        "--dry-run",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Print the proposed legs only; write and send nothing (default: on).",
    )
    parser.add_argument("--env", default=None, help="Broker env (default: settings.upstox_env).")
    parser.add_argument("--bod-path", type=Path, default=DEFAULT_BOD_PATH)
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH)
    return parser.parse_args()


async def _amain(args: argparse.Namespace) -> int:
    setup_logging()
    if guard_trading_day(logger, _SCRIPT_NAME):
        return 0
    store = PaperStore(args.db_path)
    lookup = InstrumentLookup.from_file(args.bod_path)
    broker = create_client(args.env or settings.upstox_env)
    notifier = (
        TelegramGateway(settings.telegram_bot_token, settings.telegram_chat_id, str(args.db_path))
        if settings.telegram_bot_token and settings.telegram_chat_id
        else None
    )
    vix = None if args.dry_run else await asyncio.to_thread(fetch_vix_latest)
    shell = build_calendar_shell(
        broker=broker, store=store, notifier=notifier, lookup=lookup,
        config=REGISTRY[args.variant].config,
        vix_fn=lambda: vix,
    )  # fmt: skip
    outcome = await run_entry(
        shell=shell, store=store, broker=broker, lookup=lookup, notifier=notifier,
        now=datetime.now(tz=_IST), dry_run=args.dry_run,
    )  # fmt: skip
    logger.info("calendar_entry.done", outcome=outcome, dry_run=args.dry_run)
    return 1 if outcome == "INCOMPLETE" else 0


def main() -> None:
    """CLI entry point."""
    sys.exit(asyncio.run(_amain(parse_args())))


if __name__ == "__main__":
    main()

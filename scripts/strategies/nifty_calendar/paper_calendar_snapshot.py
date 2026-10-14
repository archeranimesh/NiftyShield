# scripts/strategies/nifty_calendar/paper_calendar_snapshot.py
"""EOD snapshot for the Nifty positional calendar (``--variant monthly|biweekly``).

Writes the strategy's ``paper_nav_snapshots`` row (via ``PaperTracker``) and one
``paper_leg_snapshots`` row per leg role, then sends the EOD audit report and the payoff chart.
Written as its own script, not an extension of ``paper_ic_snapshot.process_variant``, which is
coupled to the IC classes.

Default is ``--dry-run``: the report is printed; nothing is written or sent. Cron lines live
in the CM-8 cutover note, not here.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Protocol

import structlog
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from src.client.factory import create_client
from src.client.protocol import BrokerClient
from src.client.upstox_market import parse_upstox_option_chain
from src.config import settings
from src.instruments.lookup import InstrumentLookup
from src.market_calendar.holidays import guard_trading_day
from src.models.options import OptionChain
from src.notifications.payoff_chart import send_payoff_chart
from src.notifications.telegram_gateway import TelegramGateway
from src.paper.constants import DEFAULT_BOD_PATH, DEFAULT_DB_PATH
from src.paper.models import PaperLegSnapshot, PaperPosition
from src.paper.store import PaperStore
from src.paper.tracker import PaperTracker
from src.payoff.registry import PayoffContext
from src.strategy.nifty_calendar_factory import REGISTRY, build_calendar_shell
from src.strategy.nifty_calendar_report import build_eod_report
from src.strategy.nifty_calendar_state import (
    CalendarView,
    build_view,
    cycle_entry_date,
    resolve_open_legs,
)
from src.strategy.nifty_calendar_v1 import NiftyCalendarV1
from src.strategy.payoff_registrations import ensure_registered
from src.utils.logging import setup_logging

load_dotenv()

_SCRIPT_NAME = "scripts.strategies.nifty_calendar.paper_calendar_snapshot"
logger = structlog.get_logger(_SCRIPT_NAME)

_NIFTY = "NSE_INDEX|Nifty 50"


class _Notifier(Protocol):
    """The gateway surface this script uses (text and photo)."""

    async def send_notification(self, message: str) -> None: ...

    async def send_photo(self, png: bytes, *, caption: str = "") -> None: ...


async def record_snapshots(
    store: PaperStore, broker: BrokerClient, name: str, snap_date: date, spot: Decimal | None
) -> int:
    """Write the NAV row and one leg row per role; return the number of leg rows written."""
    tracker = PaperTracker(store, broker)
    await tracker.record_daily_snapshot(
        name, snapshot_date=snap_date, underlying_price=float(spot) if spot is not None else None
    )
    open_pos = [p for p in store.get_positions(name) if p.net_qty != 0]
    ltps = await broker.get_ltp([p.instrument_key for p in open_pos]) if open_pos else {}
    written = 0
    for role, (unreal, real, total) in (await tracker.compute_pnl_by_leg_group(name)).items():
        held = [p for p in open_pos if p.leg_role == role]
        store.record_leg_snapshot(
            PaperLegSnapshot(
                strategy_name=name,
                leg_role=role,
                snapshot_date=snap_date,
                unrealized_pnl=unreal,
                realized_pnl=real,
                total_pnl=total,
                ltp=ltps.get(held[0].instrument_key) if held else None,
                net_qty=sum(p.net_qty for p in held),
            )
        )
        written += 1
    return written


async def _view(
    broker: BrokerClient, lookup: InstrumentLookup, store: PaperStore, name: str, lot_size: int
) -> tuple[CalendarView, Decimal, list[PaperPosition]] | None:
    """Rebuild the open structure at live quotes; None when a chain or quote is unavailable."""
    positions = [p for p in store.get_positions(name) if p.net_qty != 0]
    try:
        legs = resolve_open_legs(positions, lookup)
        chains: dict[date, OptionChain] = {}
        for expiry in {leg.expiry for leg in legs.values()}:
            raw = await asyncio.wait_for(broker.get_option_chain(_NIFTY, expiry.isoformat()), 15.0)
            chains[expiry] = parse_upstox_option_chain(raw if isinstance(raw, list) else [])
        spot = chains[min(chains)].underlying_spot  # near chain carries the spot
        return build_view(positions, lookup, chains, spot, lot_size), spot, positions
    except Exception as exc:  # noqa: BLE001 — fail-closed: no report beats a wrong report
        logger.error("calendar_snapshot.view_failed", strategy=name, error=str(exc))
        return None


async def run_snapshot(
    *,
    shell: NiftyCalendarV1,
    store: PaperStore,
    broker: BrokerClient,
    lookup: InstrumentLookup,
    notifier: _Notifier | None,
    snap_date: date,
    dry_run: bool,
) -> tuple[str, str | None]:
    """Record snapshots and report; return ``(outcome, report_text)``.

    Outcomes: ``NO_TRADES``, ``FLAT`` (snapshots only), ``VIEW_FAILED`` (open but unquotable),
    ``REPORTED``. Snapshots are written only when ``dry_run`` is False.
    """
    name, config = shell.strategy_name, shell.config
    if not store.get_trades(name):
        logger.info("calendar_snapshot.no_trades", strategy=name)
        return "NO_TRADES", None
    open_pos = [p for p in store.get_positions(name) if p.net_qty != 0]
    built = await _view(broker, lookup, store, name, config.lot_size) if open_pos else None
    if not dry_run:
        spot = built[1] if built else None
        written = await record_snapshots(store, broker, name, snap_date, spot)
        logger.info("calendar_snapshot.recorded", strategy=name, leg_rows=written)
    if not open_pos:
        return "FLAT", None
    if built is None:
        return "VIEW_FAILED", None
    view, spot, positions = built
    entry_date = cycle_entry_date(view.legs)
    lots = abs(view.legs["short_call"].position.net_qty) // config.lot_size
    margin = store.get_margin_snapshot(name, entry_date)
    report = build_eod_report(
        view,
        label=shell.config.label,
        strategy_name=name,
        snap_date=snap_date,
        spot=spot,
        held_days=(snap_date - entry_date).days,
        plan=shell.cycle_plan(entry_date),
        target=config.target_per_lot * lots,
        margin=margin,
    )
    print(report)
    if not dry_run and notifier is not None:
        ctx = PayoffContext(
            positions=positions,
            spot=spot,
            lot_size=config.lot_size,
            strategy_name=name,
            extras={"structure": view.structure, "far_carry": view.carry},
        )
        dte = (view.near_expiry - snap_date).days
        await _send(notifier, report, ctx, dte, view.pnl, margin.final_margin if margin else None)
    return "REPORTED", report


async def _send(
    notifier: _Notifier,
    report: str,
    ctx: PayoffContext,
    dte: int,
    pnl: Decimal,
    margin: Decimal | None,
) -> None:
    """Send the report and payoff chart; Telegram failures are logged, never raised."""
    try:
        await notifier.send_notification(report)
        ensure_registered()
        await send_payoff_chart(
            notifier,  # type: ignore[arg-type]  # PhotoSender: TelegramGateway.send_photo
            ctx.strategy_name,
            ctx,
            dte=dte,
            current_pnl=pnl,
            margin=margin,
        )
    except Exception as exc:  # noqa: BLE001 — Intentional: telegram must never abort the snapshot
        logger.warning("calendar_snapshot.send_failed", error=str(exc))


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description="Nifty calendar EOD snapshot.")
    parser.add_argument(
        "--variant", required=True, choices=sorted(REGISTRY), help="Calendar variant to snapshot."
    )
    parser.add_argument("--date", type=date.fromisoformat, default=None, metavar="YYYY-MM-DD")
    parser.add_argument(
        "--dry-run",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Print the report only; write and send nothing (default: on).",
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
    shell = build_calendar_shell(
        broker=broker,
        store=store,
        notifier=notifier,
        lookup=lookup,
        config=REGISTRY[args.variant].config,
    )
    outcome, _ = await run_snapshot(
        shell=shell, store=store, broker=broker, lookup=lookup, notifier=notifier,
        snap_date=args.date or date.today(), dry_run=args.dry_run,
    )  # fmt: skip
    logger.info("calendar_snapshot.done", outcome=outcome, dry_run=args.dry_run)
    return 1 if outcome == "VIEW_FAILED" else 0


def main() -> None:
    """CLI entry point."""
    sys.exit(asyncio.run(_amain(parse_args())))


if __name__ == "__main__":
    main()

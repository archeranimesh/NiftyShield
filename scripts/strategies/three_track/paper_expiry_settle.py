#!/usr/bin/env python3
"""Settle expired paper option legs at intrinsic value (BUG-060, B060.2).

Every non-flat ``OPEN``/``DEFENDED`` NIFTY option leg in ``paper_trades``
whose expiry is before today gets a closing trade at intrinsic value against
the official NIFTY 50 close on its expiry date, then ``mark_trade_closed``.
Fail-closed: a leg whose contract or expiry-date close can't be resolved stays
``OPEN`` and is Telegram-warned. Logic: ``src/strategy/expiry_settlement.py``.

Runs automatically once a day: ``scripts/monitor_daemon.py`` calls
``settle_expired_legs`` at startup (09:15, before the 10:30 overlay-entry
cron, where an expired marker leg would block the collar bootstrap) — there is
no separate cron. This entrypoint is the manual tool: dry-runs, and
``--contract`` overrides for contracts already dropped from the BOD master.

Usage:
    # Dry-run (default) — log what would settle, no DB writes, no Telegram:
    python -m scripts.strategies.three_track.paper_expiry_settle

    # Persist:
    python -m scripts.strategies.three_track.paper_expiry_settle --no-dry-run

    # Contract already dropped out of the BOD master — supply it explicitly:
    python -m scripts.strategies.three_track.paper_expiry_settle \\
        --contract 'NSE_FO|73994=25000:PE:2026-09-29'
"""

from __future__ import annotations

# ruff: noqa: E402
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from dotenv import load_dotenv

load_dotenv()

import argparse
import asyncio
from datetime import date
from decimal import Decimal, InvalidOperation

import structlog

from src.config import settings
from src.instruments.lookup import InstrumentLookup
from src.market_calendar.holidays import market_today
from src.notifications.formatting import format_expiry, format_money, format_strike
from src.notifications.markdown import escape_markdown, mdcode
from src.notifications.telegram import TelegramNotifier, build_notifier
from src.paper.constants import DEFAULT_BOD_PATH, DEFAULT_DB_PATH
from src.paper.store import PaperStore
from src.strategy.expiry_settlement import ContractSpec, SettlementReport, settle_expired_legs
from src.utils.logging import bind_trace_id, generate_trace_id, setup_logging

_SCRIPT_NAME = "scripts.strategies.three_track.paper_expiry_settle"
logger = structlog.get_logger(_SCRIPT_NAME)


def parse_contract_override(spec: str) -> tuple[str, ContractSpec]:
    """Parse ``KEY=STRIKE:CE|PE:YYYY-MM-DD`` into ``(key, ContractSpec)``.

    Args:
        spec: e.g. ``NSE_FO|73994=25000:PE:2026-09-29``.

    Returns:
        Instrument key and its contract spec.

    Raises:
        argparse.ArgumentTypeError: On any malformed part.
    """
    try:
        key, rest = spec.split("=", 1)
        strike_s, opt_type, expiry_s = rest.split(":")
        strike = Decimal(strike_s)
        expiry = date.fromisoformat(expiry_s)
    except (ValueError, InvalidOperation) as exc:
        raise argparse.ArgumentTypeError(f"bad --contract {spec!r}: {exc}") from exc
    opt_type = opt_type.upper()
    if not key.startswith("NSE_FO|") or opt_type not in ("CE", "PE") or strike <= 0:
        raise argparse.ArgumentTypeError(f"bad --contract {spec!r}")
    return key, ContractSpec(strike=strike, option_type=opt_type, expiry=expiry)  # type: ignore[arg-type]


async def notify_settlement(notifier: TelegramNotifier | None, report: SettlementReport) -> None:
    """Send the MarkdownV2 settlement summary/warning for a persisted run.

    Nothing is sent when ``notifier`` is ``None`` or the report is empty.

    Args:
        notifier: Telegram notifier, or ``None`` when not configured.
        report: Settlement outcome.
    """
    if notifier is None or (not report.settled and not report.failures):
        return
    lines = [f"*{escape_markdown('Paper expiry settlement (BUG-060)')}*"]
    for s in report.settled:
        c = s.leg.contract
        detail = (
            f"{format_strike(int(c.strike))} {c.option_type} {format_expiry(c.expiry)} "
            f"{s.trade.action.value} {s.trade.quantity} @ {format_money(s.trade.price)}"
        )
        lines.append(f"✅ {mdcode(s.leg.leg_role)} {escape_markdown(detail)}")
    if report.failures:
        lines.append(f"⚠️ *{escape_markdown('Left OPEN — settle manually:')}*")
    for f in report.failures:
        lines.append(
            f"{mdcode(f.strategy_name)} {mdcode(f.leg_role)} {mdcode(f.instrument_key)} "
            f"{escape_markdown('— ' + f.reason)}"
        )
    msg = "\n".join(lines)
    delivered = await notifier.send(msg)
    logger.info(
        "paper_expiry_settle.report_sent", channel="telegram", delivered=delivered, body=msg
    )


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", type=date.fromisoformat, default=None, help="Run date (IST).")
    parser.add_argument(
        "--dry-run",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Log only, no DB writes or Telegram (default: on).",
    )
    parser.add_argument(
        "--contract",
        type=parse_contract_override,
        action="append",
        default=[],
        metavar="KEY=STRIKE:CE|PE:YYYY-MM-DD",
        help="Contract spec for a key missing from the BOD master (repeatable).",
    )
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--bod-path", type=Path, default=DEFAULT_BOD_PATH)
    return parser.parse_args(argv)


async def _amain(argv: list[str] | None = None) -> None:
    from src.client.factory import create_client

    args = _parse_args(argv)
    today = args.date or market_today()
    lookup = InstrumentLookup.from_file(args.bod_path)
    store = PaperStore(args.db_path, instrument_lookup=lookup)
    broker = create_client(settings.upstox_env)
    report = await settle_expired_legs(
        store, broker, lookup, today, dry_run=args.dry_run, overrides=dict(args.contract)
    )
    logger.info(
        "paper_expiry_settle.done",
        date=today.isoformat(),
        settled=len(report.settled),
        left_open=len(report.failures),
        dry_run=args.dry_run,
    )
    if not args.dry_run:
        await notify_settlement(build_notifier(), report)


def main() -> None:
    """CLI entry point."""
    setup_logging()
    bind_trace_id(generate_trace_id())
    asyncio.run(_amain())


if __name__ == "__main__":
    main()

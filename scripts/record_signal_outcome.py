#!/usr/bin/env python3
"""Record the realised outcome of a daily directional signal.

Cron: 0 15 * * 1-5  (or run manually after market close)

Reads the aggregated ``DailySignal`` for a trading day, captures the entry/exit
premium of the recommended long option (manually or via ``--auto``), and writes
one ``SignalOutcome`` row to the ``signal_outcomes`` table. Non-executed signals
are still logged — direction-accuracy stats need every model call, executed or
not.

Usage:
    # Manual — you traded it:
    python -m scripts.record_signal_outcome --entry-premium 65.50 --exit-premium 42.00 --executed

    # Manual — you skipped the trade, log for accuracy only:
    python -m scripts.record_signal_outcome --exit-premium 42.00

    # Auto — resolve the recommended option, fetch its 15:00 LTP as exit premium:
    python -m scripts.record_signal_outcome --auto
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from statistics import mean

import structlog

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

from src.config import settings
from src.instruments.lookup import InstrumentLookup
from src.market_calendar import market_today
from src.notifications.formatting import format_money, pnl_emoji
from src.notifications.markdown import escape_markdown
from src.notifications.telegram import build_notifier
from src.paper.constants import DEFAULT_BOD_PATH, LOT_SIZE
from src.signals.models import DailySignal, SignalOutcome, TradeAction
from src.signals.option_resolver import OPTION_TYPE
from src.signals.store import SignalStore
from src.utils.logging import setup_logging

_SCRIPT_NAME = "scripts.record_signal_outcome"
logger = structlog.get_logger(_SCRIPT_NAME)

load_dotenv()

_NIFTY_SPOT_KEY = "NSE_INDEX|Nifty 50"
_ACTION_LABEL = {TradeAction.BUY_CALL: "BUY CALL", TradeAction.BUY_PUT: "BUY PUT"}
_DIRECTION_EMOJI = {"BULLISH": "📈", "BEARISH": "📉"}
_E = escape_markdown


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Record the realised outcome of a daily directional signal.",
    )
    parser.add_argument("--entry-premium", default=None, help="Entry premium per unit (Decimal).")
    parser.add_argument("--exit-premium", default=None, help="Exit premium per unit (Decimal).")
    parser.add_argument(
        "--executed",
        action="store_true",
        default=False,
        help="Set when the signal was actually paper-traded. Omit if you chose not to trade.",
    )
    parser.add_argument("--notes", default="", help="Optional annotation.")
    parser.add_argument(
        "--date",
        dest="trade_date",
        default=market_today().isoformat(),
        metavar="YYYY-MM-DD",
        help="Trading day to record. Default: today (IST).",
    )
    parser.add_argument(
        "--auto",
        action="store_true",
        default=False,
        help=(
            "Non-interactive: derive entry premium from the consensus band and "
            "exit premium from the recommended option's live LTP at 15:00."
        ),
    )
    parser.add_argument(
        "--nifty-close",
        default=None,
        help="Override Nifty close (Decimal). Default: live spot LTP (required back-dated).",
    )
    parser.add_argument(
        "--bod-path",
        type=Path,
        default=DEFAULT_BOD_PATH,
        help=f"Path to the Upstox BOD JSON (default: {DEFAULT_BOD_PATH}).",
    )
    return parser.parse_args()


def _resolve_phase() -> str:
    """Return the pipeline phase from ``SIGNAL_PHASE`` or the live key set."""
    env = os.getenv("SIGNAL_PHASE")
    if env:
        return env
    if os.getenv("XAI_API_KEY") or os.getenv("GOOGLE_AI_API_KEY"):
        return "search_enabled"
    return "openrouter_only"


def _to_decimal(raw: str | None, label: str) -> Decimal | None:
    """Parse an optional CLI Decimal argument, exiting 1 on a malformed value."""
    if raw is None:
        return None
    try:
        return Decimal(raw)
    except InvalidOperation:
        print(f"ERROR: --{label} must be a number, got: {raw!r}", file=sys.stderr)
        sys.exit(1)


def _consensus_entry_premium(signal: DailySignal) -> Decimal | None:
    """Mean midpoint of the agreeing models' quoted entry-premium bands."""
    mids = [
        (r.entry_premium_low + r.entry_premium_high) / 2
        for r in signal.responses
        if r.provider in signal.agreeing_models
    ]
    if not mids:
        return None
    return Decimal(str(mean(mids))).quantize(Decimal("0.01"))


def _fetch_ltp(keys: list[str]) -> dict[str, Decimal]:
    """Fetch last-traded prices for ``keys`` via the live Upstox market client."""
    # Intentional: sync-only cron script, no asyncio event loop — the sync
    # client is the right boundary here, mirroring record_paper_trade.py.
    from src.client.upstox_market import UpstoxMarketClient

    return UpstoxMarketClient().get_ltp_sync(keys)


def _resolve_option_key(signal: DailySignal, bod_path: Path) -> str:
    """Resolve the recommended option's instrument key from the offline BOD."""
    if not bod_path.exists():
        print(f"ERROR: BOD file not found at {bod_path}.", file=sys.stderr)
        sys.exit(1)
    if signal.recommended_strike is None:
        print("ERROR: signal has no recommended strike — cannot resolve option.", file=sys.stderr)
        sys.exit(1)
    lookup = InstrumentLookup.from_file(bod_path)
    candidates = lookup.get_expiry_candidates(
        underlying="NIFTY", today=signal.trade_date, preference=["weekly"]
    )
    if not candidates:
        print("ERROR: no weekly expiry found in BOD.", file=sys.stderr)
        sys.exit(1)
    _, expiry = candidates[0]
    matches = lookup.search_options(
        underlying="NIFTY",
        strike=float(signal.recommended_strike),
        option_type=OPTION_TYPE[signal.trade_action],
        expiry=expiry,
    )
    if not matches:
        print(
            f"ERROR: no {OPTION_TYPE[signal.trade_action]} at strike "
            f"{signal.recommended_strike} expiry {expiry} in BOD.",
            file=sys.stderr,
        )
        sys.exit(1)
    return matches[0]["instrument_key"]


def _pnl_per_lot(entry: Decimal | None, exit_premium: Decimal | None) -> Decimal | None:
    """Realised P&L per lot for a long option, or ``None`` if a leg is missing."""
    if entry is None or exit_premium is None:
        return None
    return (exit_premium - entry) * LOT_SIZE


def _format_outcome_notification(outcome: SignalOutcome, signal: DailySignal) -> str:
    """Render the daily outcome as MarkdownV2-ready Telegram message text.

    S5.5c vertical layout (reference renderer ``format_outcome_notification``,
    validated on-device 2026-09-08): bold header + blank line + one
    emoji-prefixed line per field. This formatter owns its escaping — every
    dynamic part is escaped per value and literal ``*`` is emitted for bold — so
    the caller sends the result WITHOUT re-wrapping it in ``escape_markdown``.

    Would-be P&L for the not-taken case is derived here from
    ``entry_premium``/``exit_premium`` (both populated by ``--auto`` even when
    ``executed`` is False) — no ``SignalOutcome`` change.

    Args:
        outcome: The persisted ``SignalOutcome`` for the trading day.
        signal: The aggregated ``DailySignal`` — direction of the trade call.

    Returns:
        Fully-escaped message text. One of: an executed block, a not-taken
        (would-be P&L) block, a NO_TRADE line, or a close-only fallback when a
        premium leg is missing.
    """
    day = outcome.trade_date.strftime("%d %b")
    close = _E(f"🏁 Nifty close: {outcome.nifty_close:,.0f}")
    entry, exit_ = outcome.entry_premium, outcome.exit_premium

    if outcome.trade_action is TradeAction.NO_TRADE:
        header = _E(f"📊 SIGNAL OUTCOME · {day} · NO TRADE")
        return f"*{header}*\n\n{_E('➖ No signal issued today')}\n{close}"
    if entry is None or exit_ is None:
        header = _E(f"📊 SIGNAL OUTCOME · {day}")
        return f"*{header}*\n\n{_E('➖ Outcome not priced')}\n{close}"

    emoji = _DIRECTION_EMOJI.get(signal.consensus_direction.value, "📊")
    action = _ACTION_LABEL[outcome.trade_action]
    line_dir = _E(
        f"{emoji} {signal.consensus_direction.value} · {action} {outcome.recommended_strike}"
    )

    pnl_val = outcome.pnl_per_lot if outcome.pnl_per_lot is not None else (exit_ - entry) * LOT_SIZE
    label = "P&L" if outcome.executed else "Paper P&L"
    pnl_line = f"{pnl_emoji(pnl_val)} {_E(f'{label}: {format_money(pnl_val, signed=True)} / lot')}"

    if outcome.executed:
        header = _E(f"📊 SIGNAL OUTCOME · {day}")
        prem = _E(f"💰 Entry {format_money(entry)} → Exit {format_money(exit_)}")
    else:
        header = _E(f"📊 SIGNAL OUTCOME · {day} · NOT TAKEN")
        prem = _E(f"💰 Entry {format_money(entry)} → Exit {format_money(exit_)} (would-be)")

    return (
        f"*{header}*\n\n{line_dir}\n{prem}\n{pnl_line}\n\n"
        f"{close}\n{_E(f'🔧 Phase: {outcome.phase}')}"
    )


def _notify(outcome: SignalOutcome, signal: DailySignal) -> None:
    """Push the outcome to Telegram; non-fatal when no notifier is configured."""
    notifier = build_notifier()
    if notifier is None:
        return
    try:
        asyncio.run(notifier.send(_format_outcome_notification(outcome, signal)))
    # noqa BLE001: the outcome row is already persisted — a formatting/send failure
    # must not crash the cron after the write. Log and move on.
    except Exception as exc:  # noqa: BLE001
        logger.warning("signal_outcome_notify_failed", error=str(exc))


def main() -> None:
    """CLI entry point — assemble one ``SignalOutcome`` and persist it."""
    args = _parse_args()

    try:
        trade_date = date.fromisoformat(args.trade_date)
    except ValueError:
        print(f"ERROR: --date must be YYYY-MM-DD, got: {args.trade_date}", file=sys.stderr)
        sys.exit(1)

    store = SignalStore(settings.db_path)
    signal = store.get_signal(trade_date)
    if signal is None:
        print(f"ERROR: no signal recorded for {trade_date}.", file=sys.stderr)
        sys.exit(1)

    entry_premium = _to_decimal(args.entry_premium, "entry-premium")
    exit_premium = _to_decimal(args.exit_premium, "exit-premium")
    executed = args.executed
    nifty_close = _to_decimal(args.nifty_close, "nifty-close")

    is_trade = signal.trade_action is not TradeAction.NO_TRADE

    if args.auto and is_trade:
        if entry_premium is None:
            entry_premium = _consensus_entry_premium(signal)
        try:
            option_key = _resolve_option_key(signal, args.bod_path)
            ltps = _fetch_ltp([option_key, _NIFTY_SPOT_KEY])
        # noqa BLE001: a live fetch failure must surface as exit 1, not a traceback.
        except Exception as exc:  # noqa: BLE001
            print(f"ERROR: auto price fetch failed — {exc}", file=sys.stderr)
            sys.exit(1)
        if option_key not in ltps:
            print(
                f"ERROR: no LTP returned for the recommended option ({option_key}) — "
                "pass --exit-premium explicitly.",
                file=sys.stderr,
            )
            sys.exit(1)
        exit_premium = ltps[option_key].quantize(Decimal("0.01"))
        if nifty_close is None and _NIFTY_SPOT_KEY in ltps:
            nifty_close = ltps[_NIFTY_SPOT_KEY].quantize(Decimal("0.01"))

    if nifty_close is None:
        try:
            spot = _fetch_ltp([_NIFTY_SPOT_KEY]).get(_NIFTY_SPOT_KEY)
        # noqa BLE001: the Nifty-close fallback must surface as exit 1, not a traceback.
        except Exception as exc:  # noqa: BLE001
            print(f"ERROR: could not fetch Nifty close — {exc}", file=sys.stderr)
            sys.exit(1)
        if spot is None:
            print("ERROR: Nifty spot LTP unavailable — pass --nifty-close.", file=sys.stderr)
            sys.exit(1)
        nifty_close = spot.quantize(Decimal("0.01"))

    if not is_trade:
        entry_premium = exit_premium = None
        executed = False

    outcome = SignalOutcome(
        trade_date=trade_date,
        trade_action=signal.trade_action,
        recommended_strike=signal.recommended_strike,
        entry_premium=entry_premium,
        exit_premium=exit_premium,
        pnl_per_lot=_pnl_per_lot(entry_premium, exit_premium) if executed else None,
        nifty_close=nifty_close,
        executed=executed,
        phase=_resolve_phase(),
        notes=args.notes,
    )
    store.record_outcome(outcome)
    _notify(outcome, signal)

    logger.info(
        "signal_outcome_recorded",
        trade_date=trade_date.isoformat(),
        trade_action=outcome.trade_action.value,
        executed=outcome.executed,
        pnl_per_lot=str(outcome.pnl_per_lot),
        phase=outcome.phase,
    )

    if outcome.executed and outcome.pnl_per_lot is not None:
        print(
            f"✓ Outcome recorded for {trade_date}: {outcome.trade_action.value} "
            f"| P&L: ₹{outcome.pnl_per_lot} per lot"
        )
    else:
        print(f"✓ Outcome recorded for {trade_date}: {outcome.trade_action.value} | not executed")


if __name__ == "__main__":
    setup_logging()
    main()

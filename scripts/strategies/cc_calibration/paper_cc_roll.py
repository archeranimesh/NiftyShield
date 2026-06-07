#!/usr/bin/env python3
"""Manual inspection and override exit handler for Covered Call (CC) overlay positions.

Loads open CC legs (leg_role="covered_call") under paper_covered_call_v1,
fetches the live price/delta from the option chain, and evaluates triggers
(loss stop, delta stop, profit target, time stop) matching evaluate_cc thresholds.
"""

from __future__ import annotations

import argparse
import asyncio
import re
import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import structlog

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from src.client.factory import create_client
from src.client.upstox_market import parse_upstox_option_chain
from src.config import settings
from src.instruments.lookup import InstrumentLookup
from src.paper.constants import (
    DEFAULT_BOD_PATH,
    DEFAULT_DB_PATH,
    STRATEGY_CC_OVERLAY,
)
from src.paper.models import PaperTrade
from src.paper.store import PaperStore
from src.utils.logging import setup_logging

_SCRIPT_NAME = "scripts.strategies.cc_calibration.paper_cc_roll"
logger = structlog.get_logger(_SCRIPT_NAME)

# Core thresholds from exit_signals.py
_PROFIT_TARGET_RETENTION = Decimal("0.30")
_CC_MIN_ENTRY_CREDIT = Decimal("15")


def profit_target_hit(entry_credit: Decimal, current_ltp: Decimal) -> bool:
    """Return True if call has decayed to ≤ 30% of entry credit (70% profit captured).

    Threshold mirrors _PROFIT_TARGET_RETENTION in exit_signals.py.
    Only fires if entry_credit >= _CC_MIN_ENTRY_CREDIT (Decimal("15")).
    """
    if entry_credit < _CC_MIN_ENTRY_CREDIT:
        return False
    return current_ltp <= entry_credit * _PROFIT_TARGET_RETENTION


def time_stop_hit(entry_date: date, today: date, days: int = 21) -> bool:
    """Return True if calendar days since entry >= days."""
    return (today - entry_date).days >= days


def delta_stop_hit(current_delta: float, threshold: float = 0.55) -> bool:
    """Return True if call delta has crossed the delta stop threshold."""
    return current_delta >= threshold


def _get_close_price(current_ltp: Decimal) -> Decimal:
    """Return a valid positive close price (> 0) even if current LTP is 0."""
    return max(current_ltp, Decimal("0.01"))


def loss_stop_hit(entry_credit: Decimal, current_ltp: Decimal, multiplier: float = 2.5) -> bool:
    """Return True if current mark has exceeded multiplier × entry credit (loss stop)."""
    return current_ltp >= entry_credit * Decimal(str(multiplier))


async def _run(args: argparse.Namespace) -> None:
    today: date = args.date or date.today()
    store = PaperStore(args.db_path)

    # 1. Load open CC trade using authoritative store helper
    pos = store.get_position(STRATEGY_CC_OVERLAY, "covered_call")
    if pos.net_qty >= 0:
        # Load the last trade for notes fallback or check history
        all_trades = store.get_trades(STRATEGY_CC_OVERLAY, "covered_call")
        open_trade = all_trades[-1] if all_trades else None
    else:
        # Find the open trade (last SELL trade)
        all_trades = store.get_trades(STRATEGY_CC_OVERLAY, "covered_call")
        open_trade = next((t for t in reversed(all_trades) if t.action.value == "SELL"), None)

    if (pos.net_qty >= 0 or open_trade is None) and not args.force:
        print("No open covered_call leg for paper_covered_call_v1.")
        return

    # In case --force is passed and there's no open position, fallback to last trade in history
    if open_trade is None:
        print("ERROR: --force specified but no history of covered_call trade exists to override.")
        sys.exit(1)

    # 2. Setup broker client to fetch option chain or LTP
    env = settings.upstox_env
    token = ""
    if env in ("prod", "sandbox"):
        token = settings.upstox_analytics_token if env == "prod" else settings.upstox_sandbox_token
        if not token and not args.dry_run:
            token_env = "UPSTOX_ANALYTICS_TOKEN" if env == "prod" else "UPSTOX_SANDBOX_TOKEN"
            print(f"ERROR: {token_env} not set.", file=sys.stderr)
            sys.exit(1)

    broker = create_client(env, token=token)

    # Key format check: e.g. NSE_FO|NIFTY26JUN2026CE24500 or numeric key
    m = re.search(
        r"NIFTY\d{2}[A-Za-z]{3}\d{4}(?:CE|PE)(\d+)", open_trade.instrument_key, re.IGNORECASE
    )
    if not m:
        # Check if we can get it via lookup (Lazy initialize BOD lookup)
        if not args.bod_path.exists():
            print(f"ERROR: BOD lookup file required but not found at {args.bod_path}")
            sys.exit(1)
        lookup = InstrumentLookup.from_file(args.bod_path)
        resolved = lookup.get_by_key(open_trade.instrument_key)
        if resolved:
            strike = Decimal(str(resolved.get("strike_price", 0)))
            expiry_str = resolved.get("expiry")
            if expiry_str:
                from src.instruments.lookup import parse_expiry

                exp_date_str = parse_expiry(expiry_str)
                expiry = date.fromisoformat(exp_date_str) if exp_date_str else today
            else:
                expiry = today
        else:
            print(f"ERROR: Could not parse instrument key {open_trade.instrument_key}")
            sys.exit(1)
    else:
        strike = Decimal(m.group(1))
        # Expiry matches NIFTY{DD}{MMM}{YYYY}{CE|PE}
        exp_m = re.search(
            r"NIFTY(\d{2}[A-Za-z]{3}\d{4})(CE|PE)", open_trade.instrument_key, re.IGNORECASE
        )
        if exp_m:
            expiry = datetime.strptime(exp_m.group(1).upper(), "%d%b%Y").date()
        else:
            # Fallback
            expiry = today

    print(f"Fetching live market data for {open_trade.instrument_key} ...")
    try:
        raw_chain = await broker.get_option_chain("NSE_INDEX|Nifty 50", expiry.isoformat())
        chain = parse_upstox_option_chain(raw_chain)
    except Exception as exc:
        print(f"ERROR: failed to fetch option chain — {exc}", file=sys.stderr)
        sys.exit(1)

    # Find the leg
    call_leg = None
    if chain and chain.strikes:
        strike_data = chain.strikes.get(strike)
        if strike_data and strike_data.ce:
            call_leg = strike_data.ce

    if not call_leg:
        # Fallback to get_ltp if option chain doesn't have it (or mock environment without delta)
        print("WARNING: option chain strike lookup failed; fetching LTP only.")
        try:
            ltp_map = await broker.get_ltp(open_trade.instrument_key)
            current_ltp = ltp_map.get(open_trade.instrument_key)
        except Exception as exc:
            print(f"ERROR: failed to fetch LTP — {exc}", file=sys.stderr)
            sys.exit(1)
        current_delta = 0.0  # default when missing
    else:
        current_ltp = call_leg.ltp
        current_delta = float(call_leg.delta) if call_leg.delta is not None else 0.0

    if current_ltp is None:
        print(f"ERROR: Could not fetch LTP for {open_trade.instrument_key}")
        sys.exit(1)

    # Ensure Decimal types
    entry_credit = Decimal(str(open_trade.price))
    current_ltp_dec = Decimal(str(current_ltp))

    # Evaluate Triggers
    loss = loss_stop_hit(entry_credit, current_ltp_dec)
    delta_stop = delta_stop_hit(current_delta)
    profit = profit_target_hit(entry_credit, current_ltp_dec)
    # Use real trade_date or fall back to pos.entry_date
    entry_d = open_trade.trade_date if open_trade else (pos.entry_date or today)
    time_stop = time_stop_hit(entry_d, today)

    # Print Report
    loss_status = "✅ HIT " if loss else "⬜ not hit"
    delta_status = "✅ HIT " if delta_stop else "⬜ not hit"
    profit_status = "✅ HIT " if profit else "⬜ not hit"
    time_status = "✅ HIT " if time_stop else "⬜ not hit"

    print(f"\nCovered Call Roll Check | {today}")
    print(f"Instrument: {open_trade.instrument_key} | Entry price: ₹{entry_credit:.2f}")
    print(f"Current LTP: ₹{current_ltp_dec:.2f} | Current Delta: {current_delta:.3f}\n")
    print(
        f"Loss stop:      {loss_status}  (LTP ₹{current_ltp_dec:.2f} / 2.5× entry ₹{entry_credit * Decimal('2.5'):.2f})"
    )
    print(f"Delta stop:     {delta_status}  (delta {current_delta:.2f} / 0.55 limit)")
    print(
        f"Profit target:  {profit_status}  (LTP ₹{current_ltp_dec:.2f} ≤ 30% of entry ₹{entry_credit * Decimal('0.3'):.2f})"
    )
    days_held = (today - entry_d).days
    print(f"Time stop:      {time_status}  ({days_held} days held / 21 limit)")

    if current_delta >= 0.45:
        print(f"⚠️  Delta warn: delta {current_delta:.2f} approaching stop (0.55). Monitor closely.")

    # Determine highest-priority trigger
    trigger_name = None
    if loss:
        trigger_name = "loss_stop"
    elif delta_stop:
        trigger_name = "delta_stop"
    elif profit:
        trigger_name = "profit_target"
    elif time_stop:
        trigger_name = "time_stop"

    if trigger_name:
        print(f"\nTrigger: {trigger_name}")
        notes = f"exit: {trigger_name}; LTP={current_ltp_dec:.2f}; entry={entry_credit:.2f}; delta={current_delta:.2f}"

        # Enforce positive price > 0 for PaperTrade validation
        validated_close_price = _get_close_price(current_ltp_dec)

        # Build closing command representation
        close_cmd = (
            f"python -m scripts.record_paper_trade \\\n"
            f"  --strategy {STRATEGY_CC_OVERLAY} \\\n"
            f"  --leg covered_call \\\n"
            f"  --action BUY \\\n"
            f"  --key {open_trade.instrument_key} \\\n"
            f"  --qty {-pos.net_qty if pos.net_qty < 0 else open_trade.quantity} \\\n"
            f"  --price {validated_close_price:.2f} \\\n"
            f"  --no-dry-run \\\n"
            f"  --notes {notes!r}"
        )
        print(f"\nClose Command:\n{close_cmd}")

        if args.dry_run:
            print("\nDry run — no actions executed.")
            return

        # Interactive Confirmation or --yes
        if not args.yes:
            try:
                confirm = input("\nExecute close? [y/N]: ").strip().lower()
                if confirm != "y":
                    print("Aborted.")
                    return
            except (KeyboardInterrupt, EOFError):
                print("\nAborted.")
                return

        # Perform the actual write
        close_trade = PaperTrade(
            strategy_name=STRATEGY_CC_OVERLAY,
            leg_role="covered_call",
            instrument_key=open_trade.instrument_key,
            trade_date=today,
            action="BUY",
            quantity=-pos.net_qty if pos.net_qty < 0 else open_trade.quantity,
            price=validated_close_price,
            notes=notes,
        )
        if store.record_trade(close_trade):
            print("Success: Closed position recorded to paper_trades.")
        else:
            print("Skipped: Duplicate close trade found.")
    else:
        print("\nNo exit triggers hit.")


def main() -> None:
    """CLI Entry Point."""
    parser = argparse.ArgumentParser(
        description="Inspect and roll Covered Call overlay positions manually."
    )
    parser.add_argument(
        "--date",
        type=date.fromisoformat,
        default=None,
        help="Date to evaluate triggers (YYYY-MM-DD). Defaults to today.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Bypass 'no open CC leg' guard for manual override.",
    )
    parser.add_argument(
        "--dry-run",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Print status report without writing close trade (default: on).",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip interactive confirmation.",
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        default=DEFAULT_DB_PATH,
        help=f"Path to SQLite DB (default: {DEFAULT_DB_PATH})",
    )
    parser.add_argument(
        "--bod-path",
        type=Path,
        default=DEFAULT_BOD_PATH,
        help=f"Path to BOD instrument JSON (default: {DEFAULT_BOD_PATH})",
    )
    args = parser.parse_args()
    asyncio.run(_run(args))


if __name__ == "__main__":
    setup_logging()
    main()

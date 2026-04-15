"""CLI for atomically rolling an option leg: close old + open new in one transaction.

Both trades are validated via the Trade Pydantic model before any DB write.
If either INSERT fails (e.g. connection error), the entire roll is rolled back —
no half-committed state. Re-running the same roll is always safe (idempotent).

Usage:
    python scripts/roll_leg.py \\
        --strategy finideas_ilts \\
        --date 2026-06-20 \\
        --old-leg NIFTY_MAY_PE_ATM \\
        --old-key "NSE_FO|<token>" \\
        --old-action BUY \\
        --old-qty 50 \\
        --old-price 45.00 \\
        --new-leg NIFTY_JUN_PE_ATM \\
        --new-key "NSE_FO|<token>" \\
        --new-action SELL \\
        --new-qty 50 \\
        --new-price 85.00 \\
        [--notes "JUN expiry roll"] \\
        [--dry-run]

    # Dry run — prints both Trade objects without touching the DB:
    python scripts/roll_leg.py --strategy finideas_ilts --date 2026-06-20 \\
        --old-leg NIFTY_MAY_PE_ATM --old-key "NSE_FO|12345" \\
        --old-action BUY --old-qty 50 --old-price 45.00 \\
        --new-leg NIFTY_JUN_PE_ATM --new-key "NSE_FO|67890" \\
        --new-action SELL --new-qty 50 --new-price 85.00 --dry-run

Strategy names must match the strategies table exactly:
    finideas_ilts   (not ILTS or "Finideas ILTS")
    finrakshak      (not FinRakshak)
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.portfolio.models import Trade, TradeAction
from src.portfolio.store import PortfolioStore

DEFAULT_DB_PATH = Path("data/portfolio/portfolio.sqlite")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Atomically roll an option leg: close old position + open new one."
    )
    parser.add_argument("--strategy", required=True, help='Strategy name, e.g. "finideas_ilts"')
    parser.add_argument(
        "--date",
        required=True,
        dest="trade_date",
        help="Execution date in YYYY-MM-DD format (applies to both trades)",
    )
    # Close (old) leg
    parser.add_argument("--old-leg", required=True, help="Leg role being closed, e.g. NIFTY_MAY_PE_ATM")
    parser.add_argument("--old-key", required=True, help="Upstox instrument key for the old leg")
    parser.add_argument(
        "--old-action",
        required=True,
        choices=["BUY", "SELL"],
        help="Action to close the old position (BUY to cover a short, SELL to exit a long)",
    )
    parser.add_argument("--old-qty", required=True, type=int, help="Units to close (positive integer)")
    parser.add_argument("--old-price", required=True, help="Execution price for the closing trade")
    # Open (new) leg
    parser.add_argument("--new-leg", required=True, help="Leg role being opened, e.g. NIFTY_JUN_PE_ATM")
    parser.add_argument("--new-key", required=True, help="Upstox instrument key for the new leg")
    parser.add_argument(
        "--new-action",
        required=True,
        choices=["BUY", "SELL"],
        help="Action to open the new position (BUY for long, SELL for short)",
    )
    parser.add_argument("--new-qty", required=True, type=int, help="Units to open (positive integer)")
    parser.add_argument("--new-price", required=True, help="Execution price for the opening trade")
    # Shared / meta
    parser.add_argument("--notes", default="", help="Optional annotation applied to both trades")
    parser.add_argument(
        "--db-path",
        type=Path,
        default=DEFAULT_DB_PATH,
        help=f"Path to the SQLite database (default: {DEFAULT_DB_PATH})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print both Trade objects without inserting into the DB.",
    )
    return parser.parse_args()


def _build_trades(
    strategy: str,
    trade_date: date,
    old_leg: str,
    old_key: str,
    old_action: str,
    old_qty: int,
    old_price: str,
    new_leg: str,
    new_key: str,
    new_action: str,
    new_qty: int,
    new_price: str,
    notes: str = "",
) -> tuple[Trade, Trade]:
    """Construct and validate both trades from raw CLI values.

    Pure function — no I/O. Raises Pydantic ``ValidationError`` or
    ``ValueError`` if any field is invalid (e.g. qty <= 0, price <= 0).

    Args:
        strategy: Strategy name matching the strategies table.
        trade_date: Execution date applied to both trades.
        old_leg: Leg role being closed.
        old_key: Upstox instrument key for the old leg.
        old_action: "BUY" or "SELL" to close the position.
        old_qty: Units transacted on the close side.
        old_price: Execution price string for the close trade.
        new_leg: Leg role being opened.
        new_key: Upstox instrument key for the new leg.
        new_action: "BUY" or "SELL" to open the new position.
        new_qty: Units transacted on the open side.
        new_price: Execution price string for the open trade.
        notes: Optional annotation applied to both trades.

    Returns:
        ``(close_trade, open_trade)`` as validated Trade objects.
    """
    close_trade = Trade(
        strategy_name=strategy,
        leg_role=old_leg,
        instrument_key=old_key,
        trade_date=trade_date,
        action=TradeAction(old_action),
        quantity=old_qty,
        price=Decimal(old_price),
        notes=notes,
    )
    open_trade = Trade(
        strategy_name=strategy,
        leg_role=new_leg,
        instrument_key=new_key,
        trade_date=trade_date,
        action=TradeAction(new_action),
        quantity=new_qty,
        price=Decimal(new_price),
        notes=notes,
    )
    return close_trade, open_trade


def _print_trade_block(label: str, trade: Trade) -> None:
    """Print a formatted single-trade block."""
    print(f"  {label}:")
    print(f"    leg_role  : {trade.leg_role}")
    print(f"    key       : {trade.instrument_key}")
    print(f"    action    : {trade.action.value}")
    print(f"    quantity  : {trade.quantity}")
    print(f"    price     : ₹{trade.price}")


def main() -> None:
    """CLI entry point. Validates both trades, optionally records, prints positions."""
    args = _parse_args()

    try:
        trade_date = date.fromisoformat(args.trade_date)
    except ValueError:
        print(f"ERROR: --date must be YYYY-MM-DD, got: {args.trade_date}", file=sys.stderr)
        sys.exit(1)

    try:
        close_trade, open_trade = _build_trades(
            strategy=args.strategy,
            trade_date=trade_date,
            old_leg=args.old_leg,
            old_key=args.old_key,
            old_action=args.old_action,
            old_qty=args.old_qty,
            old_price=args.old_price,
            new_leg=args.new_leg,
            new_key=args.new_key,
            new_action=args.new_action,
            new_qty=args.new_qty,
            new_price=args.new_price,
            notes=args.notes,
        )
    except Exception as exc:
        print(f"ERROR: invalid trade data — {exc}", file=sys.stderr)
        sys.exit(1)

    if args.dry_run:
        print("Dry run — roll NOT recorded:\n")
        print(f"  strategy  : {close_trade.strategy_name}")
        print(f"  date      : {close_trade.trade_date}")
        if close_trade.notes:
            print(f"  notes     : {close_trade.notes}")
        print()
        _print_trade_block("CLOSE", close_trade)
        print()
        _print_trade_block("OPEN", open_trade)
        return

    store = PortfolioStore(args.db_path)
    store.record_roll(close_trade, open_trade)

    old_qty, old_avg = store.get_position(close_trade.strategy_name, close_trade.leg_role)
    new_qty, new_avg = store.get_position(open_trade.strategy_name, open_trade.leg_role)

    print(f"Roll complete — {close_trade.strategy_name}  [{close_trade.trade_date}]")
    print(f"  CLOSED  {close_trade.leg_role} : {old_qty} units @ avg ₹{old_avg:.2f}")
    print(f"  OPENED  {open_trade.leg_role} : {new_qty} units @ avg ₹{new_avg:.2f}")


if __name__ == "__main__":
    main()

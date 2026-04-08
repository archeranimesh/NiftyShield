"""CLI for recording a single trade execution into the trades ledger.

Validates all fields via the Trade Pydantic model before touching the DB.
Pure insert path — no DB reads until the post-insert position summary.

Usage:
    python scripts/record_trade.py \\
        --strategy ILTS \\
        --leg EBBETF0431 \\
        --key "NSE_EQ|INF754K01LE1" \\
        --date 2026-04-08 \\
        --action BUY \\
        --qty 27 \\
        --price 1386.20 \\
        --notes "addition to ILTS position"

    # Dry run — prints Trade object without inserting:
    python scripts/record_trade.py --strategy ILTS --leg EBBETF0431 \\
        --key "NSE_EQ|INF754K01LE1" --date 2026-04-08 --action BUY \\
        --qty 27 --price 1386.20 --dry-run
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
        description="Record a single trade execution into the portfolio trade ledger."
    )
    parser.add_argument("--strategy", required=True, help='Strategy name, e.g. "ILTS"')
    parser.add_argument("--leg", required=True, help='Leg role label, e.g. "EBBETF0431"')
    parser.add_argument(
        "--key", required=True, help='Upstox instrument key, e.g. "NSE_EQ|INF754K01LE1"'
    )
    parser.add_argument(
        "--date",
        required=True,
        dest="trade_date",
        help="Execution date in YYYY-MM-DD format",
    )
    parser.add_argument(
        "--action",
        required=True,
        choices=["BUY", "SELL"],
        help="BUY or SELL",
    )
    parser.add_argument("--qty", required=True, type=int, help="Units transacted (positive integer)")
    parser.add_argument("--price", required=True, help="Execution price per unit")
    parser.add_argument("--notes", default="", help="Optional annotation (contract note ref, etc.)")
    parser.add_argument(
        "--db-path",
        type=Path,
        default=DEFAULT_DB_PATH,
        help=f"Path to the SQLite database (default: {DEFAULT_DB_PATH})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the Trade object without inserting into the DB.",
    )
    return parser.parse_args()


def main() -> None:
    """CLI entry point.  Validates, optionally inserts, prints position summary."""
    args = _parse_args()

    try:
        trade_date = date.fromisoformat(args.trade_date)
    except ValueError:
        print(f"ERROR: --date must be YYYY-MM-DD, got: {args.trade_date}", file=sys.stderr)
        sys.exit(1)

    try:
        trade = Trade(
            strategy_name=args.strategy,
            leg_role=args.leg,
            instrument_key=args.key,
            trade_date=trade_date,
            action=TradeAction(args.action),
            quantity=args.qty,
            price=Decimal(args.price),
            notes=args.notes,
        )
    except Exception as exc:
        print(f"ERROR: invalid trade data — {exc}", file=sys.stderr)
        sys.exit(1)

    if args.dry_run:
        print("Dry run — trade NOT inserted:\n")
        print(f"  strategy  : {trade.strategy_name}")
        print(f"  leg_role  : {trade.leg_role}")
        print(f"  key       : {trade.instrument_key}")
        print(f"  date      : {trade.trade_date}")
        print(f"  action    : {trade.action.value}")
        print(f"  quantity  : {trade.quantity}")
        print(f"  price     : ₹{trade.price}")
        if trade.notes:
            print(f"  notes     : {trade.notes}")
        return

    store = PortfolioStore(args.db_path)
    store.record_trade(trade)

    net_qty, avg_price = store.get_position(trade.strategy_name, trade.leg_role)
    print(
        f"{trade.strategy_name} / {trade.leg_role}: "
        f"{net_qty} units @ avg ₹{avg_price:.2f}"
    )


if __name__ == "__main__":
    main()

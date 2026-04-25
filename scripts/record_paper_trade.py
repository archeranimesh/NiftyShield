"""CLI for recording a single paper trade into the paper_trades ledger.

Validates all fields via PaperTrade before touching the DB.
Enforces the ``paper_`` prefix on --strategy before construction.

Usage:
    python scripts/record_paper_trade.py \\
        --strategy paper_csp_nifty_v1 \\
        --leg short_put \\
        --key "NSE_FO|12345" \\
        --date 2026-05-01 \\
        --action SELL \\
        --qty 75 \\
        --price 120.50 \\
        --notes "entry at mid; assumed 0.25 slippage"

    # Dry run — prints PaperTrade without inserting:
    python scripts/record_paper_trade.py --strategy paper_csp_nifty_v1 \\
        --leg short_put --key "NSE_FO|12345" --date 2026-05-01 \\
        --action SELL --qty 75 --price 120.50 --dry-run
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.models.portfolio import TradeAction
from src.paper.models import PaperTrade
from src.paper.store import PaperStore

DEFAULT_DB_PATH = Path("data/portfolio/portfolio.sqlite")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Record a single paper trade into the paper_trades ledger. "
            "--strategy must start with 'paper_'."
        )
    )
    parser.add_argument(
        "--strategy",
        required=True,
        help='Paper strategy name — must start with "paper_", e.g. "paper_csp_nifty_v1"',
    )
    parser.add_argument("--leg", required=True, help='Leg role label, e.g. "short_put"')
    parser.add_argument(
        "--key", required=True, help='Upstox instrument key, e.g. "NSE_FO|12345"'
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
    parser.add_argument(
        "--qty", required=True, type=int, help="Units transacted (positive integer)"
    )
    parser.add_argument("--price", required=True, help="Execution price per unit")
    parser.add_argument(
        "--notes",
        default="",
        help="Optional annotation (slippage assumption, decision rationale, etc.)",
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        default=DEFAULT_DB_PATH,
        help=f"Path to the SQLite database (default: {DEFAULT_DB_PATH})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the PaperTrade object without inserting into the DB.",
    )
    return parser.parse_args()


def main() -> None:
    """CLI entry point. Validates, optionally inserts, prints position summary."""
    args = _parse_args()

    # Enforce paper_ prefix before attempting model construction
    if not args.strategy.startswith("paper_"):
        print(
            f"ERROR: --strategy must start with 'paper_', got: {args.strategy!r}",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        trade_date = date.fromisoformat(args.trade_date)
    except ValueError:
        print(
            f"ERROR: --date must be YYYY-MM-DD, got: {args.trade_date}",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        trade = PaperTrade(
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
        print("Dry run — paper trade NOT inserted:\n")
        print(f"  strategy  : {trade.strategy_name}")
        print(f"  leg_role  : {trade.leg_role}")
        print(f"  key       : {trade.instrument_key}")
        print(f"  date      : {trade.trade_date}")
        print(f"  action    : {trade.action.value}")
        print(f"  quantity  : {trade.quantity}")
        print(f"  price     : ₹{trade.price}")
        print(f"  is_paper  : {trade.is_paper}")
        if trade.notes:
            print(f"  notes     : {trade.notes}")
        return

    store = PaperStore(args.db_path)
    store.record_trade(trade)

    pos = store.get_position(trade.strategy_name, trade.leg_role)
    if pos.net_qty == 0:
        print(
            f"{trade.strategy_name} / {trade.leg_role}: position closed (net qty = 0)"
        )
    else:
        direction = "short" if pos.net_qty < 0 else "long"
        ref_price = pos.avg_sell_price if pos.net_qty < 0 else pos.avg_cost
        print(
            f"{trade.strategy_name} / {trade.leg_role}: "
            f"{pos.net_qty} units ({direction}) @ avg ₹{ref_price:.2f}"
        )


if __name__ == "__main__":
    main()

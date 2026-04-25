"""CLI for recording a single paper trade into the paper_trades ledger.

Validates all fields via PaperTrade before touching the DB.
Enforces the ``paper_`` prefix on --strategy before construction.

Instrument key can be supplied directly via --key, or auto-resolved from the
offline BOD JSON using the --underlying / --strike / --option-type / --expiry
lookup flags.  Both modes are mutually exclusive.

Usage — explicit key:
    python scripts/record_paper_trade.py \\
        --strategy paper_csp_nifty_v1 \\
        --leg short_put \\
        --key "NSE_FO|12345" \\
        --date 2026-05-01 \\
        --action SELL \\
        --qty 75 \\
        --price 120.50 \\
        --notes "entry at mid; assumed 0.25 slippage"

Usage — auto instrument lookup ("sell a Nifty 50 put at 23000, May expiry"):
    python scripts/record_paper_trade.py \\
        --strategy paper_csp_nifty_v1 \\
        --leg short_put \\
        --underlying NIFTY \\
        --strike 23000 \\
        --option-type PE \\
        --expiry 2026-05-29 \\
        --date 2026-05-01 \\
        --action SELL \\
        --qty 75 \\
        --price 120.50

    If --expiry is omitted, all matching expiries are shown — re-run with --expiry
    to narrow the selection.  If multiple instruments match after all filters are
    applied, the list is printed and no insert is made; use --key directly.

    # Dry run — prints PaperTrade without inserting:
    python scripts/record_paper_trade.py --strategy paper_csp_nifty_v1 \\
        --leg short_put --underlying NIFTY --strike 23000 --option-type PE \\
        --expiry 2026-05-29 --date 2026-05-01 --action SELL --qty 75 --price 120.50 \\
        --dry-run
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.instruments.lookup import InstrumentLookup
from src.models.portfolio import TradeAction
from src.paper.models import PaperTrade
from src.paper.store import PaperStore

DEFAULT_DB_PATH = Path("data/portfolio/portfolio.sqlite")
DEFAULT_BOD_PATH = Path("data/instruments/NSE.json.gz")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Record a single paper trade into the paper_trades ledger. "
            "--strategy must start with 'paper_'.  Provide either --key "
            "(direct instrument key) or the lookup flags "
            "(--underlying / --strike / --option-type / --expiry)."
        )
    )
    parser.add_argument(
        "--strategy",
        required=True,
        help='Paper strategy name — must start with "paper_", e.g. "paper_csp_nifty_v1"',
    )
    parser.add_argument("--leg", required=True, help='Leg role label, e.g. "short_put"')

    # ── Instrument identification (one of two modes) ──────────────────────────
    key_group = parser.add_argument_group(
        "direct key", "Provide the Upstox instrument key directly"
    )
    key_group.add_argument(
        "--key",
        default=None,
        help='Upstox instrument key, e.g. "NSE_FO|12345"',
    )

    lookup_group = parser.add_argument_group(
        "instrument lookup",
        "Auto-resolve instrument key from the offline BOD JSON "
        "(mutually exclusive with --key)",
    )
    lookup_group.add_argument(
        "--underlying",
        default=None,
        help='Underlying symbol for option lookup, e.g. "NIFTY"',
    )
    lookup_group.add_argument(
        "--strike",
        type=float,
        default=None,
        help="Strike price, e.g. 23000",
    )
    lookup_group.add_argument(
        "--option-type",
        choices=["CE", "PE"],
        default=None,
        help="CE or PE",
    )
    lookup_group.add_argument(
        "--expiry",
        default=None,
        help="Expiry date in YYYY-MM-DD, e.g. 2026-05-29",
    )
    lookup_group.add_argument(
        "--bod-path",
        type=Path,
        default=DEFAULT_BOD_PATH,
        help=f"Path to Upstox BOD JSON file (default: {DEFAULT_BOD_PATH})",
    )
    # ──────────────────────────────────────────────────────────────────────────

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


def _resolve_instrument_key(args: argparse.Namespace) -> str | None:
    """Resolve instrument key from --key or from BOD lookup flags.

    Returns the resolved key, or None after printing an error/ambiguity message
    (caller should exit 1).

    Args:
        args: Parsed CLI arguments.

    Returns:
        Resolved instrument_key string, or None on failure.
    """
    # Direct key — no lookup needed
    if args.key:
        if args.underlying or args.strike or args.option_type or args.expiry:
            print(
                "ERROR: --key and lookup flags (--underlying/--strike/--option-type/"
                "--expiry) are mutually exclusive.",
                file=sys.stderr,
            )
            return None
        return args.key

    # Lookup mode — --underlying is the minimum required field
    if not args.underlying:
        print(
            "ERROR: provide either --key or at least --underlying for instrument lookup.",
            file=sys.stderr,
        )
        return None

    if not args.bod_path.exists():
        print(
            f"ERROR: BOD file not found at {args.bod_path}.\n"
            "Download it with:\n"
            "  curl -o data/instruments/NSE.json.gz "
            "https://assets.upstox.com/market-quote/instruments/exchange/NSE.json.gz",
            file=sys.stderr,
        )
        return None

    try:
        lookup = InstrumentLookup.from_file(args.bod_path)
    except Exception as exc:
        print(f"ERROR: failed to load BOD file — {exc}", file=sys.stderr)
        return None

    results = lookup.search_options(
        underlying=args.underlying,
        strike=args.strike,
        option_type=args.option_type,
        expiry=args.expiry,
    )

    if not results:
        filters = []
        if args.strike:
            filters.append(f"strike={args.strike}")
        if args.option_type:
            filters.append(f"type={args.option_type}")
        if args.expiry:
            filters.append(f"expiry={args.expiry}")
        filter_str = ", ".join(filters) if filters else "no filters"
        print(
            f"ERROR: no instruments found for underlying={args.underlying!r} "
            f"({filter_str}).\n"
            "Check spelling, ensure the BOD file is fresh, and verify the expiry date.",
            file=sys.stderr,
        )
        return None

    if len(results) == 1:
        inst = results[0]
        key = inst.get("instrument_key", "")
        sym = inst.get("trading_symbol", "")
        print(f"Resolved instrument: {sym}  ({key})")
        return key

    # Multiple matches — print them and ask user to be more specific
    print(
        f"Multiple instruments matched for {args.underlying!r} "
        f"(showing up to {len(results)}):\n",
        file=sys.stderr,
    )
    for i, inst in enumerate(results, 1):
        key = inst.get("instrument_key", "")
        sym = inst.get("trading_symbol", "")
        strike = inst.get("strike_price", "")
        expiry = inst.get("expiry", "")
        itype = inst.get("instrument_type", "")
        print(
            f"  {i:2d}. {sym:<28} strike={strike:<8} type={itype}  expiry={expiry}  key={key}",
            file=sys.stderr,
        )
    print(
        "\nRe-run with --key <key> from the list above, or add "
        "--strike / --option-type / --expiry to narrow results.",
        file=sys.stderr,
    )
    return None


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

    # Resolve instrument key (direct --key or BOD lookup)
    instrument_key = _resolve_instrument_key(args)
    if instrument_key is None:
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
            instrument_key=instrument_key,
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

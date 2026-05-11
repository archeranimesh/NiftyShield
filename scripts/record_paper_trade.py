"""CLI for recording a single paper trade into the paper_trades ledger.

Supports four modes of instrument resolution:
1. Direct Key: Provide --key "NSE_FO|12345" and --price.
2. Auto-expiry (Live Chain): Provide --expiry YYYY-MM-DD. Fetches live LTP and
   delta-ranked strikes (like find_strike_by_delta), picking rank via --index N.
3. BOD Lookup: Provide --underlying, --strike, --option-type, --expiry to
   resolve a key from the offline BOD JSON (data/instruments/NSE.json.gz).
4. Close Shorthand: Use --close to auto-resolve the instrument key from the
   current open short position in the DB and fetch live LTP for the price.

Dry-run is on by default — use ``--no-dry-run`` to actually write to the DB.

Usage Examples:
    # Explicit key:
    python scripts/record_paper_trade.py --key "NSE_FO|12345" --price 120.5 --no-dry-run

    # Live chain pick (rank 1):
    python scripts/record_paper_trade.py --expiry 2026-05-29 --delta-min 0.15 --no-dry-run

    # Close current short position at live LTP:
    python scripts/record_paper_trade.py --strategy paper_nifty_spot --leg overlay_pp --close --no-dry-run
"""

from __future__ import annotations

import argparse
import sys
from typing import Any
from datetime import date
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

from src.instruments.lookup import InstrumentLookup
from src.models.portfolio import TradeAction
from src.paper.models import PaperTrade
from src.paper.store import PaperStore
from scripts.find_strike_by_delta import (
    DEFAULT_LOT_SIZE,
    UNDERLYING_DEFAULT,
    filter_strikes_by_delta,
    format_table,
    rank_strikes,
)
from src.client.upstox_market import UpstoxMarketClient
from src.paper.constants import DEFAULT_BOD_PATH, DEFAULT_DB_PATH
from src.paper._utils import safe_float

load_dotenv()




def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Record a single paper trade into the paper_trades ledger. "
            "--strategy must start with 'paper_'.  Provide either --key "
            "(direct instrument key), --expiry (live chain lookup), or "
            "lookup flags (--underlying / --strike / --option-type / --expiry)."
        )
    )
    parser.add_argument(
        "--strategy",
        default="paper_csp_nifty_v1",
        help='Paper strategy name — must start with "paper_". Default: paper_csp_nifty_v1.',
    )
    parser.add_argument(
        "--leg",
        default="short_put",
        help='Leg role label, e.g. "short_put". Default: short_put.',
    )

    # ── Chain lookup mode ─────────────────────────────────────────────────────
    chain_group = parser.add_argument_group(
        "chain lookup",
        "Auto-select strike from live option chain (mutually exclusive with --key and --underlying).",
    )
    chain_group.add_argument(
        "--expiry",
        default=None,
        metavar="YYYY-MM-DD",
        help="Fetch live option chain and auto-select best strike for this expiry.",
    )
    chain_group.add_argument(
        "--delta-min",
        type=float,
        default=0.20,
        metavar="FLOAT",
        help="Lower |delta| bound for chain filter. Default: 0.20.",
    )
    chain_group.add_argument(
        "--delta-max",
        type=float,
        default=0.35,
        metavar="FLOAT",
        help="Upper |delta| bound for chain filter. Default: 0.35.",
    )
    chain_group.add_argument(
        "--option-type",
        choices=["CE", "PE", "BOTH"],
        default=None,
        help="Option side for chain filter. Default: PE.",
    )
    chain_group.add_argument(
        "--index",
        type=int,
        default=1,
        metavar="N",
        help="Select the Nth-ranked candidate from the chain (1-based). Default: 1.",
    )
    # ──────────────────────────────────────────────────────────────────────────

    # ── Instrument identification (one of two lookup modes) ───────────────────
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
        "(mutually exclusive with --key and --expiry)",
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
        "--bod-path",
        type=Path,
        default=DEFAULT_BOD_PATH,
        help=f"Path to Upstox BOD JSON file (default: {DEFAULT_BOD_PATH})",
    )
    # ──────────────────────────────────────────────────────────────────────────

    parser.add_argument(
        "--date",
        dest="trade_date",
        default=str(date.today()),
        help="Execution date in YYYY-MM-DD format. Default: today.",
    )
    parser.add_argument(
        "--action",
        choices=["BUY", "SELL"],
        default="SELL",
        help="BUY or SELL. Default: SELL.",
    )
    parser.add_argument(
        "--qty",
        type=int,
        default=DEFAULT_LOT_SIZE,
        help=f"Units transacted (positive integer). Default: {DEFAULT_LOT_SIZE}.",
    )
    parser.add_argument("--price", default=None, help="Execution price per unit.")
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
        "--close",
        action="store_true",
        default=False,
        help=(
            "Buy-to-close shorthand: implies --action BUY. "
            "Use when closing an existing short leg (e.g. roll-close of a CSP). "
            "Mutually exclusive with --action."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "Preview the PaperTrade without inserting into the DB (default: on). "
            "Use --no-dry-run to write."
        ),
    )
    return parser.parse_args()


def _resolve_from_chain(args: argparse.Namespace) -> tuple[str, str] | None:
    """Fetch live option chain, rank candidates, return (instrument_key, price).

    Prints the ranked table (mirroring find_strike_by_delta output) and the
    selected row so the user can verify before the DB write.

    Args:
        args: Parsed CLI arguments (uses expiry, delta_min, delta_max,
              option_type, index, underlying=UNDERLYING_DEFAULT).

    Returns:
        (instrument_key, price_str) for the selected rank, or None on failure
        (caller should sys.exit(1)).
    """
    try:
        client = UpstoxMarketClient()
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return None

    # Resolve expiries
    expiries: list[tuple[str, str]] = []  # (label, expiry_str)
    if args.expiry:
        expiries = [("manual", args.expiry)]
    else:
        try:
            lookup = InstrumentLookup.from_file(args.bod_path)
            # Preference for CSP: monthly -> quarterly -> yearly
            # TODO: derive symbol from args.underlying
            expiries = lookup.get_expiry_candidates(
                underlying="NIFTY", today=date.today()
            )
        # Intentional: catch all API connectivity issues during chain fetch.
        except Exception as exc:
            print(f"ERROR: failed to load BOD or resolve expiries — {exc}", file=sys.stderr)
            return None

    if not expiries:
        print("ERROR: no eligible expiries found (DTE 15–420).", file=sys.stderr)
        return None

    all_rows: list[dict[str, Any]] = []
    underlying_spot = 0.0

    for label, expiry in expiries:
        print(
            f"Fetching live chain: {UNDERLYING_DEFAULT}  expiry={expiry} ({label}) …",
            flush=True,
        )
        try:
            raw_data = client.get_option_chain_sync(UNDERLYING_DEFAULT, expiry)
            if not raw_data:
                print(f"  WARNING: API returned empty data for {expiry} — skipping.")
                continue

            if underlying_spot <= 0.0:
                underlying_spot = safe_float(raw_data[0].get("underlying_spot_price", 0.0))

            option_type = args.option_type or "PE"
            rows = filter_strikes_by_delta(
                raw_data,
                option_type=option_type,
                delta_min=args.delta_min,
                delta_max=args.delta_max,
            )
            # Annotate rows with expiry and label
            for r in rows:
                r["expiry"] = expiry
                r["expiry_label"] = label
            
            all_rows.extend(rows)

        # Intentional: prevent a single processing failure from crashing the sweep.
        except Exception as exc:
            print(f"  WARNING: fetch failed for {expiry} — {exc} — skipping.")
            continue

    if not all_rows:
        print("ERROR: no strikes found across all candidate expiries (empty data).", file=sys.stderr)
        return None

    ranked = rank_strikes(all_rows)
    pick_idx = min(args.index - 1, len(ranked) - 1)
    if args.index - 1 > len(ranked) - 1:
        print(
            f"WARNING: --index {args.index} out of range; clamping to rank {len(ranked)}.",
            file=sys.stderr,
        )

    selected = ranked[pick_idx]

    print()
    print(
        format_table(
            ranked,
            underlying_spot=underlying_spot,
            expiry=args.expiry or "Multiple (auto)",
            selected_key=selected["instrument_key"],
        )
    )

    price = round(selected["mid"] if selected["mid"] > 0 else selected["ltp"], 2)
    print(
        f"\n# Rank {args.index}: {selected['side']} {selected['strike']:.0f} | "
        f"delta={selected['delta']:+.4f} | iv={selected['iv']:.2f}% | "
        f"expiry={selected['expiry']} ({selected['expiry_label']}) | price=₹{price}"
    )

    return selected["instrument_key"], str(price)


def _resolve_from_position(args: argparse.Namespace) -> str | None:
    """Resolve instrument key from the current open position in the DB.

    Args:
        args: Parsed CLI arguments (uses db_path, strategy, leg).

    Returns:
        Resolved instrument_key string, or None if no open short position.
    """
    store = PaperStore(args.db_path)
    pos = store.get_position(args.strategy, args.leg)

    if pos.net_qty >= 0:
        print(
            f"ERROR: no open short position to close for {args.strategy} / {args.leg} "
            f"(net qty = {pos.net_qty}).",
            file=sys.stderr,
        )
        return None

    print(f"Resolved key from position: {pos.instrument_key}")
    return pos.instrument_key


def _resolve_instrument_key(args: argparse.Namespace) -> str | None:
    """Resolve instrument key from --key or from BOD lookup flags.

    Returns the resolved key, or None after printing an error/ambiguity message
    (caller should exit 1).

    Args:
        args: Parsed CLI arguments.

    Returns:
        Resolved instrument_key string, or None on failure.
    """
    # Auto-key from DB — --close provided AND (no key AND no underlying provided)
    if args.close and not args.key and not args.underlying:
        key = _resolve_from_position(args)
        if key is not None:
            return key
        return None

    # Chain mode — --expiry provided OR (no key AND no underlying provided)
    # We need to distinguish between chain-mode --expiry and lookup-mode --expiry.
    # Chain mode is active if --underlying is NOT set AND --key is NOT set.
    if not args.key and not args.underlying:
        result = _resolve_from_chain(args)
        if result is None:
            return None
        key, price_str = result
        # Inject resolved price back into args so main() can use it
        args.price = price_str
        return key

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
    # Intentional: catch all BOD file loading/parsing errors.
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

    # --close implies BUY; reject combination with explicit --action
    if args.close:
        if args.action != "SELL":  # SELL is the argparse default — any other value means explicit
            print(
                "ERROR: --close and --action are mutually exclusive; "
                "--close already implies --action BUY.",
                file=sys.stderr,
            )
            sys.exit(1)
        args.action = "BUY"

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

    if args.expiry:
        try:
            date.fromisoformat(args.expiry)
        except ValueError:
            print(
                f"ERROR: --expiry must be YYYY-MM-DD, got: {args.expiry}",
                file=sys.stderr,
            )
            sys.exit(1)

    if args.price is None:
        if args.close:
            # Auto-price from LTP
            try:
                client = UpstoxMarketClient()
                ltp_dict = client.get_ltp_sync([instrument_key])
                if instrument_key not in ltp_dict:
                    print(f"ERROR: LTP not found for {instrument_key}", file=sys.stderr)
                    sys.exit(1)
                
                price = ltp_dict[instrument_key]
                rounded_price = round(price, 2)
                print(f"Auto-price: LTP=₹{rounded_price}")
                args.price = str(rounded_price)
            except ValueError as exc:
                print(f"ERROR: {exc}", file=sys.stderr)
                sys.exit(1)
            # Intentional: prevent LTP fetch failure from crashing the script.
            except Exception as exc:
                print(f"ERROR: failed to fetch LTP — {exc}", file=sys.stderr)
                sys.exit(1)
        elif args.key or args.underlying:
            print(
                "ERROR: --price is required when not in chain mode (auto-expiry).",
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
    # Intentional: top-level catch for trade recording failure.
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

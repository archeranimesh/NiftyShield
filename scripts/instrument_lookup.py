"""Look up Upstox instrument keys from the BOD JSON file.

Download the BOD file first:
    mkdir -p data/instruments
    curl -o data/instruments/NSE.json.gz \
        https://assets.upstox.com/market-quote/instruments/exchange/NSE.json.gz

Usage:
    # Search by symbol
    python -m scripts.instrument_lookup --query EBBETF0431

    # Search options by underlying, strike, type, expiry
    python -m scripts.instrument_lookup --query NIFTY --strike 23000 --type PE --expiry 2026-12-31

    # Search equity only
    python -m scripts.instrument_lookup --query EBBETF0431 --segment NSE_EQ

    # Find all our strategy legs at once
    python -m scripts.instrument_lookup --find-legs
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.instruments.lookup import InstrumentLookup, format_results

DEFAULT_BOD_PATH = Path("data/instruments/NSE.json.gz")


def find_strategy_legs(lookup: InstrumentLookup) -> None:
    """Look up instrument keys for all legs in our strategies."""
    legs_to_find = [
        {
            "label": "EBBETF0431 (Bharat Bond ETF Apr 2031)",
            "method": "search_equity",
            "args": {"symbol": "EBBETF0431"},
        },
        {
            "label": "NIFTY DEC 2026 23000 PE (ILTS + FinRakshak)",
            "method": "search_options",
            "args": {
                "underlying": "NIFTY",
                "strike": 23000.0,
                "option_type": "PE",
                "expiry": "2026-12-29",
            },
        },
        {
            "label": "NIFTY JUN 2026 23000 CE (ILTS)",
            "method": "search_options",
            "args": {
                "underlying": "NIFTY",
                "strike": 23000.0,
                "option_type": "CE",
                "expiry": "2026-06-30",
            },
        },
        {
            "label": "NIFTY JUN 2026 23000 PE (ILTS short)",
            "method": "search_options",
            "args": {
                "underlying": "NIFTY",
                "strike": 23000.0,
                "option_type": "PE",
                "expiry": "2026-06-30",
            },
        },
    ]

    print("Looking up instrument keys for strategy legs...\n")

    for leg in legs_to_find:
        method = getattr(lookup, leg["method"])
        results = method(**leg["args"])

        print(f"  {leg['label']}")
        if results:
            for r in results[:3]:
                expiry_str = ""
                if "expiry" in r:
                    parsed = lookup._parse_expiry(r["expiry"])
                    expiry_str = f"  expiry={parsed}"
                print(
                    f"    → {r['instrument_key']:<25} "
                    f"{r.get('trading_symbol', '')}{expiry_str}"
                )
        else:
            print("    → NOT FOUND — check expiry date or BOD file freshness")
        print()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Look up Upstox instrument keys from BOD JSON"
    )
    parser.add_argument(
        "--bod-path",
        type=Path,
        default=DEFAULT_BOD_PATH,
        help=f"Path to BOD JSON file (default: {DEFAULT_BOD_PATH})",
    )
    parser.add_argument("--query", "-q", type=str, help="Free-text search query")
    parser.add_argument("--strike", type=float, help="Strike price filter")
    parser.add_argument(
        "--type", dest="option_type", type=str, help="Instrument type: CE, PE, FUT, EQ"
    )
    parser.add_argument("--expiry", type=str, help="Expiry date YYYY-MM-DD")
    parser.add_argument(
        "--segment", type=str, help="Segment filter: NSE_EQ, NSE_FO"
    )
    parser.add_argument(
        "--find-legs",
        action="store_true",
        help="Look up all strategy leg instrument keys at once",
    )
    parser.add_argument(
        "--max-results", type=int, default=10, help="Max results to show"
    )
    args = parser.parse_args()

    if not args.bod_path.exists():
        print(f"BOD file not found at: {args.bod_path}")
        print("\nDownload it first:")
        print("  mkdir -p data/instruments")
        print(
            "  curl -o data/instruments/NSE.json.gz "
            "https://assets.upstox.com/market-quote/instruments/exchange/NSE.json.gz"
        )
        sys.exit(1)

    print(f"Loading {args.bod_path}...")
    lookup = InstrumentLookup.from_file(args.bod_path)
    print(f"Loaded {lookup.count} instruments.\n")

    if args.find_legs:
        find_strategy_legs(lookup)
        return

    if not args.query:
        parser.print_help()
        return

    # Route to the right search method
    if args.strike is not None or args.option_type in ("CE", "PE"):
        results = lookup.search_options(
            underlying=args.query,
            strike=args.strike,
            option_type=args.option_type,
            expiry=args.expiry,
            max_results=args.max_results,
        )
    elif args.option_type == "FUT":
        results = lookup.search_futures(
            underlying=args.query,
            expiry=args.expiry,
            max_results=args.max_results,
        )
    else:
        results = lookup.search(
            query=args.query,
            segment=args.segment,
            instrument_type=args.option_type,
            max_results=args.max_results,
        )

    print(format_results(results))


if __name__ == "__main__":
    main()

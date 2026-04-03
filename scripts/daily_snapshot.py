"""Record daily price snapshots for all portfolio strategies.

Fetches live LTPs from Upstox V3 API, records to SQLite, exits.
Designed for cron — no interactive prompts, returns exit code 0/1.

Usage:
    # Record today's snapshot
    python -m scripts.daily_snapshot

    # Record for a specific date (backfill)
    python -m scripts.daily_snapshot --date 2026-04-01

    # Custom DB path
    python -m scripts.daily_snapshot --db-path data/portfolio/portfolio.sqlite

Cron example (run at 3:45 PM IST on weekdays):
    45 15 * * 1-5 cd /path/to/NiftyShield && /path/to/python -m scripts.daily_snapshot >> logs/snapshot.log 2>&1
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv()

from src.client.upstox_market import UpstoxMarketClient
from src.portfolio.store import PortfolioStore
from src.portfolio.tracker import PortfolioTracker


def main() -> int:
    parser = argparse.ArgumentParser(description="Record daily portfolio snapshots")
    parser.add_argument(
        "--db-path",
        type=Path,
        default=Path("data/portfolio/portfolio.sqlite"),
        help="Path to portfolio SQLite DB",
    )
    parser.add_argument(
        "--date",
        type=str,
        default=None,
        help="Snapshot date as YYYY-MM-DD (defaults to today)",
    )
    args = parser.parse_args()

    snap_date = date.fromisoformat(args.date) if args.date else date.today()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    print(f"[{now}] Daily snapshot for {snap_date.isoformat()}")

    # ── Validate DB exists ───────────────────────────────────────
    if not args.db_path.exists():
        print(f"  ERROR: DB not found at {args.db_path}")
        print("  Run 'python -m scripts.seed_portfolio' first.")
        return 1

    store = PortfolioStore(args.db_path)
    strategies = store.get_all_strategies()

    if not strategies:
        print("  ERROR: No strategies found in DB. Run seed_portfolio first.")
        return 1

    # ── Initialize market client ─────────────────────────────────
    try:
        client = UpstoxMarketClient()
    except ValueError as e:
        print(f"  ERROR: {e}")
        return 1

    # ── Collect all unique instrument keys across strategies ──────
    NIFTY_INDEX_KEY = "NSE_INDEX|Nifty 50"

    all_keys = set()
    for strategy in strategies:
        for leg in strategy.legs:
            all_keys.add(leg.instrument_key)

    print(f"  Strategies: {len(strategies)}, Instruments: {len(all_keys)}")

    # ── Fetch all LTPs in one batch (Nifty spot piggybacked) ─────
    prices = client.get_ltp_sync(list(all_keys | {NIFTY_INDEX_KEY}))
    if not prices:
        print("  ERROR: No prices returned from Upstox API.")
        return 1

    underlying_price = prices.get(NIFTY_INDEX_KEY)
    if underlying_price:
        print(f"  Nifty spot: {underlying_price:,.2f}")
    else:
        print("  WARNING: Could not fetch Nifty spot price.")

    missing = all_keys - set(prices.keys())
    if missing:
        print(f"  WARNING: No LTP for {len(missing)} instruments: {missing}")

    # ── Record snapshots via tracker ─────────────────────────────
    tracker = PortfolioTracker(store, client)
    results = asyncio.run(
        tracker.record_all_strategies(
            snapshot_date=snap_date,
            underlying_price=underlying_price,
        )
    )

    # ── Print summary ────────────────────────────────────────────
    total_snaps = sum(results.values())
    print(f"  Recorded {total_snaps} snapshots:")

    for strategy in strategies:
        count = results.get(strategy.name, 0)
        pnl = asyncio.run(tracker.compute_pnl(strategy.name))
        if pnl:
            print(
                f"    {strategy.name}: {count} legs, "
                f"P&L: {pnl.total_pnl:+,.0f} ({pnl.total_pnl_percent:+.2f}%)"
            )
        else:
            print(f"    {strategy.name}: {count} legs")

    print(f"  Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

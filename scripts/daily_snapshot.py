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
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv()

from src.client.exceptions import LTPFetchError
from src.client.upstox_market import UpstoxMarketClient
from src.mf.store import MFStore
from src.mf.tracker import MFTracker, PortfolioPnL
from src.portfolio.models import AssetType, Strategy
from src.portfolio.store import PortfolioStore
from src.portfolio.tracker import PortfolioTracker


def _etf_current_value(strategies: list[Strategy], prices: dict[str, float]) -> Decimal:
    """Mark-to-market value of all EQUITY legs across strategies.

    ETF legs are assets — value is qty × current LTP.
    Falls back to entry price if LTP is missing (e.g. market closed).

    Args:
        strategies: All loaded Strategy objects.
        prices: instrument_key → LTP from the batch fetch.

    Returns:
        Total ETF value as Decimal.
    """
    total = Decimal("0")
    for strategy in strategies:
        for leg in strategy.legs:
            if leg.asset_type == AssetType.EQUITY:
                ltp = prices.get(leg.instrument_key, leg.entry_price)
                total += Decimal(str(ltp)) * Decimal(str(leg.quantity))
    return total


def _etf_cost_basis(strategies: list[Strategy]) -> Decimal:
    """Total entry cost of all EQUITY legs (qty × entry_price).

    Args:
        strategies: All loaded Strategy objects.

    Returns:
        Sum of entry costs as Decimal.
    """
    return sum(
        Decimal(str(leg.entry_price)) * Decimal(str(leg.quantity))
        for strategy in strategies
        for leg in strategy.legs
        if leg.asset_type == AssetType.EQUITY
    )


def _print_combined_summary(
    strategies: list,
    prices: dict[str, float],
    strategy_pnls: dict[str, object],
    mf_pnl: PortfolioPnL | None,
) -> None:
    """Print the combined portfolio value across MF, ETF, and options.

    Args:
        strategies: All loaded Strategy objects.
        prices: instrument_key → LTP.
        strategy_pnls: strategy name → P&L object (from compute_pnl).
        mf_pnl: Completed MF PortfolioPnL, or None if the MF fetch failed.
    """
    etf_value = _etf_current_value(strategies, prices)
    etf_basis = _etf_cost_basis(strategies)

    # Options net P&L — sign already correct for short legs in compute_pnl
    options_pnl = sum(
        (Decimal(str(p.total_pnl)) for p in strategy_pnls.values() if p),
        Decimal("0"),
    )

    mf_value = mf_pnl.total_current_value if mf_pnl else Decimal("0")
    mf_invested = mf_pnl.total_invested if mf_pnl else Decimal("0")
    mf_pnl_amt = mf_pnl.total_pnl if mf_pnl else Decimal("0")

    total_value = mf_value + etf_value + options_pnl
    total_invested = mf_invested + etf_basis
    total_pnl = mf_pnl_amt + (etf_value - etf_basis) + options_pnl
    total_pnl_pct = (
        (total_pnl / total_invested * 100).quantize(Decimal("0.01"))
        if total_invested
        else Decimal("0")
    )

    mf_label = f"₹{mf_value:>14,.0f}" if mf_pnl else "         [failed]"
    print()
    print("  ── Combined Portfolio ─────────────────────────────────")
    print(f"  MF current value    : {mf_label}")
    print(f"  ETF current value   : ₹{etf_value:>14,.0f}  (basis ₹{etf_basis:,.0f})")
    print(f"  Options net P&L     : ₹{options_pnl:>+14,.0f}")
    print("  ───────────────────────────────────────────────────────")
    print(f"  Total value         : ₹{total_value:>14,.0f}")
    print(f"  Total invested      : ₹{total_invested:>14,.0f}")
    print(f"  Total P&L           : ₹{total_pnl:>+14,.0f}  ({total_pnl_pct:+}%)")
    if not mf_pnl:
        print("  NOTE: MF fetch failed — MF value excluded from total")


async def _async_main(
    snap_date: date,
    db_path: Path,
) -> int:
    """All async I/O for the daily snapshot run.

    Separated from main() so the entire async workflow runs in a single
    event loop — no repeated asyncio.run() calls.

    Args:
        snap_date: Date to record snapshots for.
        db_path: Path to the SQLite database.

    Returns:
        Exit code: 0 for success, 1 for any fatal error.
    """
    # ── Validate DB exists ───────────────────────────────────────
    if not db_path.exists():
        print(f"  ERROR: DB not found at {db_path}")
        print("  Run 'python -m scripts.seed_portfolio' first.")
        return 1

    store = PortfolioStore(db_path)
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

    all_keys = {leg.instrument_key for strategy in strategies for leg in strategy.legs}
    print(f"  Strategies: {len(strategies)}, Instruments: {len(all_keys)}")

    # ── Fetch all LTPs in one batch (Nifty spot piggybacked) ─────
    try:
        prices = client.get_ltp_sync(list(all_keys | {NIFTY_INDEX_KEY}))
    except LTPFetchError as e:
        print(f"  ERROR: LTP fetch failed — {e}")
        print("  Aborting: cannot record snapshots with stale/zero prices.")
        return 1

    underlying_price = prices.get(NIFTY_INDEX_KEY)
    if underlying_price:
        print(f"  Nifty spot: {underlying_price:,.2f}")
    else:
        print("  WARNING: Could not fetch Nifty spot price.")

    missing = all_keys - set(prices.keys())
    if missing:
        print(f"  WARNING: No LTP for {len(missing)} instruments: {missing}")

    # ── Record snapshots and collect P&L — single event loop ─────
    tracker = PortfolioTracker(store, client)
    results = await tracker.record_all_strategies(
        snapshot_date=snap_date,
        underlying_price=underlying_price,
    )

    total_snaps = sum(results.values())
    print(f"  Recorded {total_snaps} snapshots:")

    strategy_pnls: dict[str, object] = {}
    for strategy in strategies:
        count = results.get(strategy.name, 0)
        pnl = await tracker.compute_pnl(strategy.name)
        strategy_pnls[strategy.name] = pnl
        if pnl:
            print(
                f"    {strategy.name}: {count} legs, "
                f"P&L: {pnl.total_pnl:+,.0f} ({pnl.total_pnl_percent:+.2f}%)"
            )
        else:
            print(f"    {strategy.name}: {count} legs")

    # ── MF portfolio snapshot (non-fatal) ─────────────────────────
    mf_pnl: PortfolioPnL | None = None
    try:
        mf_store = MFStore(db_path)
        mf_pnl = MFTracker(mf_store).record_snapshot(snap_date)
        if mf_pnl.schemes:
            print(
                f"  MF portfolio ({len(mf_pnl.schemes)} schemes): "
                f"₹{mf_pnl.total_current_value:,.0f}  "
                f"P&L {mf_pnl.total_pnl:+,.0f} ({mf_pnl.total_pnl_pct:+}%)"
            )
        else:
            print(
                "  MF portfolio: no holdings — skipped (run seed_mf_holdings.py first)"
            )
    except Exception as e:  # noqa: BLE001
        print(f"  WARNING: MF snapshot failed — {e}")

    # ── Combined portfolio summary ────────────────────────────────
    _print_combined_summary(strategies, prices, strategy_pnls, mf_pnl)

    print("\n  Done.")
    return 0


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

    return asyncio.run(_async_main(snap_date, args.db_path))


if __name__ == "__main__":
    sys.exit(main())

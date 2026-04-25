"""Standalone mark-to-market snapshot for paper trading strategies.

Fetches live LTPs for all open paper positions, computes P&L, and persists a
PaperNavSnapshot row in paper_nav_snapshots.  Idempotent — re-running for the
same (strategy, date) updates the existing row.

Does NOT touch daily_snapshot.py or the live trades ledger.

Usage:
    # Snapshot all known paper strategies (uses today's date):
    python scripts/paper_snapshot.py

    # Single strategy:
    python scripts/paper_snapshot.py --strategy paper_csp_nifty_v1

    # With known underlying price (skips a market fetch):
    python scripts/paper_snapshot.py --underlying-price 23250.5

    # Historical date (P&L computation uses that date but LTPs are still live):
    python scripts/paper_snapshot.py --date 2026-05-01

    # Dry run — prints P&L without writing to DB:
    python scripts/paper_snapshot.py --dry-run

Environment:
    UPSTOX_ENV            prod | sandbox | test  (default: prod)
    UPSTOX_ACCESS_TOKEN   required for prod/sandbox
    UPSTOX_ANALYTICS_TOKEN  required for market data (LTP)
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.client.factory import create_broker_client
from src.paper.store import PaperStore
from src.paper.tracker import PaperTracker

DEFAULT_DB_PATH = Path("data/portfolio/portfolio.sqlite")

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Mark-to-market all open paper trading positions and persist a "
            "PaperNavSnapshot.  Safe to run multiple times — idempotent upsert."
        )
    )
    parser.add_argument(
        "--strategy",
        default=None,
        help=(
            "Restrict to a single paper strategy, e.g. 'paper_csp_nifty_v1'. "
            "Omit to snapshot all known strategies."
        ),
    )
    parser.add_argument(
        "--date",
        dest="snapshot_date",
        default=None,
        help="Snapshot date in YYYY-MM-DD (defaults to today).",
    )
    parser.add_argument(
        "--underlying-price",
        type=float,
        default=None,
        help="Nifty 50 spot price for context (optional; stored in snapshot).",
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        default=DEFAULT_DB_PATH,
        help=f"Path to SQLite DB (default: {DEFAULT_DB_PATH}).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Compute and print P&L without writing to the DB.",
    )
    return parser.parse_args()


async def _run(args: argparse.Namespace) -> int:
    """Async entry point. Returns exit code."""
    snapshot_date: date | None = None
    if args.snapshot_date:
        try:
            snapshot_date = date.fromisoformat(args.snapshot_date)
        except ValueError:
            print(
                f"ERROR: --date must be YYYY-MM-DD, got: {args.snapshot_date!r}",
                file=sys.stderr,
            )
            return 1

    env = os.environ.get("UPSTOX_ENV", "prod")
    client = create_broker_client(env=env)
    store = PaperStore(args.db_path)
    tracker = PaperTracker(store=store, market=client)

    strategy_names: list[str]
    if args.strategy:
        if not args.strategy.startswith("paper_"):
            print(
                f"ERROR: --strategy must start with 'paper_', got: {args.strategy!r}",
                file=sys.stderr,
            )
            return 1
        strategy_names = [args.strategy]
    else:
        strategy_names = store.get_strategy_names()

    if not strategy_names:
        print("No paper strategies found in DB.  Record a trade first.")
        return 0

    snap_date = snapshot_date or date.today()
    any_printed = False

    for name in strategy_names:
        pnl = await tracker.compute_pnl(name)
        if pnl is None:
            print(f"{name}: no trades — skipped")
            continue

        unrealized, realized, total = pnl
        underlying_str = (
            f"  underlying : ₹{args.underlying_price:,.2f}\n"
            if args.underlying_price is not None
            else ""
        )
        any_printed = True

        if args.dry_run:
            print(
                f"\n[DRY RUN] {name} — {snap_date}\n"
                f"  unrealized : ₹{unrealized:,.2f}\n"
                f"  realized   : ₹{realized:,.2f}\n"
                f"  total P&L  : ₹{total:,.2f}\n"
                f"{underlying_str}"
                f"  (not written to DB)"
            )
        else:
            snap = await tracker.record_daily_snapshot(
                name,
                snapshot_date=snap_date,
                underlying_price=args.underlying_price,
            )
            if snap:
                print(
                    f"{name} — {snap.snapshot_date}\n"
                    f"  unrealized : ₹{snap.unrealized_pnl:,.2f}\n"
                    f"  realized   : ₹{snap.realized_pnl:,.2f}\n"
                    f"  total P&L  : ₹{snap.total_pnl:,.2f}"
                )
                if snap.underlying_price is not None:
                    print(f"  underlying : ₹{snap.underlying_price:,.2f}")

    if not any_printed and not args.dry_run:
        print("All strategies skipped — no trades found.")

    return 0


def main() -> None:
    """CLI entry point."""
    args = _parse_args()
    exit_code = asyncio.run(_run(args))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()

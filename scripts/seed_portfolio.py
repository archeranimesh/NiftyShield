"""Seed the portfolio database with strategy definitions.

Run once to create the DB and populate strategies + legs.
Safe to re-run — uses upsert logic so existing data is not duplicated.

Usage:
    python -m scripts.seed_portfolio [--db-path data/portfolio/portfolio.sqlite]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow running from project root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.portfolio.models import DailySnapshot
from src.portfolio.store import PortfolioStore
from src.portfolio.strategies import ALL_STRATEGIES


def seed(db_path: Path) -> None:
    """Create DB, insert strategies, and record entry-day snapshots."""
    store = PortfolioStore(db_path)

    for strategy in ALL_STRATEGIES:
        strategy_id = store.upsert_strategy(strategy)
        print(f"  Strategy '{strategy.name}' → id={strategy_id}")

        # Reload to get leg IDs assigned by the DB
        saved = store.get_strategy(strategy.name)
        if not saved:
            continue

        for leg in saved.legs:
            print(
                f"    Leg {leg.id}: {leg.direction.value} {leg.display_name} "
                f"@ {leg.entry_price} x {leg.quantity}"
            )

        # Record entry-day snapshot using entry prices (day 0 baseline)
        entry_snapshots = [
            DailySnapshot(
                leg_id=leg.id,  # type: ignore[arg-type]
                snapshot_date=leg.entry_date,
                ltp=leg.entry_price,
                close=leg.entry_price,
            )
            for leg in saved.legs
            if leg.id is not None
        ]
        if entry_snapshots:
            count = store.record_snapshots_bulk(entry_snapshots)
            print(f"    Recorded {count} entry-day snapshots (P&L = 0 baseline)")

    print(f"\nDatabase ready at: {db_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed portfolio database")
    parser.add_argument(
        "--db-path",
        type=Path,
        default=Path("data/portfolio/portfolio.sqlite"),
        help="Path to SQLite database file",
    )
    args = parser.parse_args()

    print(f"Seeding portfolio DB at {args.db_path}...")
    seed(args.db_path)


if __name__ == "__main__":
    main()

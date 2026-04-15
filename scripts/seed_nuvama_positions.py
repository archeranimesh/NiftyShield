"""One-time seed of Nuvama bond cost-basis positions.

Inserts known ISIN → avg_price mappings into the nuvama_positions table.
Idempotent: uses INSERT OR IGNORE by default so repeated runs are safe.
Use --overwrite to replace existing rows when avg_price changes.

Avg prices sourced from Nuvama holdings UI screenshot (2026-04-14).
Update this script when new bonds are purchased.

Usage:
    python -m scripts.seed_nuvama_positions            # dry-run preview
    python -m scripts.seed_nuvama_positions --write    # commit to DB
    python -m scripts.seed_nuvama_positions --write --overwrite  # replace existing
"""

from __future__ import annotations

import argparse
from decimal import Decimal

from src.nuvama.store import NuvamaStore

# ---------------------------------------------------------------------------
# Known positions (sourced from Nuvama UI 2026-04-14)
# Update avg_price when buying more units of the same instrument.
# ---------------------------------------------------------------------------

_POSITIONS: list[dict] = [
    {
        "isin": "INE532F07FD3",
        "avg_price": Decimal("1000.00"),
        "qty": 700,
        "label": "EFSL 10% NCD 2034",
    },
    {
        "isin": "INE532F07EC8",
        "avg_price": Decimal("1000.00"),
        "qty": 500,
        "label": "EFSL 9.20% NCD 2026",
    },
    {
        "isin": "INE532F07DK3",
        "avg_price": Decimal("1001.06"),
        "qty": 1200,
        "label": "EFSL 9.67% NCD 2028",
    },
    {
        "isin": "INE532F07FN2",
        "avg_price": Decimal("1000.00"),
        "qty": 700,
        "label": "EFSL 9.67% NCD 2029",
    },
    {
        "isin": "IN0020070069",
        "avg_price": Decimal("109.00"),
        "qty": 2000,
        "label": "G-Sec 8.28% 2027",
    },
    {
        "isin": "IN0020230168",
        "avg_price": Decimal("6199.00"),
        "qty": 50,
        "label": "SGB 2023-24 Series III 2031 2.50%",
    },
]


def build_positions() -> list[dict]:
    """Return the canonical list of Nuvama bond positions.

    Pure function — no I/O. Used directly by tests.

    Returns:
        List of position dicts with keys: isin, avg_price, qty, label.
    """
    return list(_POSITIONS)


def seed_positions(
    db_path: str = "data/portfolio/portfolio.sqlite",
    *,
    overwrite: bool = False,
) -> int:
    """Insert Nuvama bond positions into the nuvama_positions table.

    Args:
        db_path: Path to portfolio.sqlite.
        overwrite: When True, replaces existing rows (INSERT OR REPLACE).
                   When False (default), skips existing rows (INSERT OR IGNORE).

    Returns:
        Number of rows actually inserted.
    """
    store = NuvamaStore(db_path)
    return store.seed_positions(build_positions(), overwrite=overwrite)


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Seed Nuvama bond cost-basis positions.")
    p.add_argument(
        "--write",
        action="store_true",
        help="Commit to DB (default is dry-run preview only).",
    )
    p.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace existing rows (default: skip existing rows).",
    )
    p.add_argument(
        "--db",
        default="data/portfolio/portfolio.sqlite",
        help="Path to portfolio.sqlite (default: data/portfolio/portfolio.sqlite).",
    )
    return p.parse_args()


def main() -> None:
    args = _parse_args()
    positions = build_positions()

    total_invested = sum(
        p["avg_price"] * p["qty"] for p in positions
    )

    print(f"\nNuvama bond positions to seed ({len(positions)} instruments):\n")
    for p in positions:
        basis = p["avg_price"] * p["qty"]
        print(
            f"  {p['isin']}  {p['label']:40s}"
            f"  qty={p['qty']:>5}  avg=₹{p['avg_price']:>10}  basis=₹{basis:>14,.2f}"
        )
    print(f"\n  Total invested: ₹{total_invested:,.2f}")

    if not args.write:
        print("\n[dry-run] Pass --write to commit to DB.")
        return

    inserted = seed_positions(args.db, overwrite=args.overwrite)
    mode = "overwrite" if args.overwrite else "ignore-existing"
    print(f"\n✓ Seeded {inserted} row(s) into nuvama_positions ({mode} mode).")


if __name__ == "__main__":
    main()

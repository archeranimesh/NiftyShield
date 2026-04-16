"""Seed initial MF holdings into mf_transactions.

Inserts one INITIAL transaction per scheme for all 11 schemes in the
FinRakshak protected MF portfolio. Safe to re-run — the unique constraint
on (amfi_code, transaction_date, transaction_type) with ON CONFLICT DO NOTHING
guarantees idempotency.

AMFI codes verified against https://www.amfiindia.com/spages/NAVAll.txt
on 2026-04-01.  If a code ever needs updating, change it here and re-run.

Usage:
    python scripts/seed_mf_holdings.py
    python scripts/seed_mf_holdings.py --db-path /path/to/other.sqlite
    python scripts/seed_mf_holdings.py --dry-run
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

# Allow ``python scripts/seed_mf_holdings.py`` from repo root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.models.mf import MFTransaction, TransactionType
from src.mf.store import MFStore

# ---------------------------------------------------------------------------
# Portfolio data — locked in on 2026-04-01 (entry baseline)
# ---------------------------------------------------------------------------

#: (amfi_code, scheme_name, units, invested_amount_inr)
_HOLDINGS: list[tuple[str, str, str, str]] = [
    ("104481", "DSP Midcap Fund - Regular Plan - Growth", "4020.602", "439978.00"),
    (
        "146193",
        "Edelweiss Small Cap Fund - Regular Plan - Growth",
        "8962.544",
        "379981.00",
    ),
    ("101281", "HDFC BSE Sensex Index Fund - Regular Growth", "291.628", "187371.53"),
    ("102760", "HDFC Focused Fund - Growth", "3511.563", "789960.50"),
    ("112090", "Kotak Flexicap Fund - Growth", "5766.492", "235105.58"),
    ("142109", "Mahindra Manulife Mid Cap Fund - Growth", "13962.132", "449977.50"),
    (
        "122640",
        "Parag Parikh Flexi Cap Fund - Regular Growth",
        "32424.322",
        "1719925.75",
    ),
    ("100177", "Quant Small Cap Fund - Growth", "714.722", "116321.50"),
    (
        "101659",
        "Tata Nifty 50 Index Fund - Regular Plan - Growth",
        "4506.202",
        "587002.67",
    ),
    ("101672", "Tata Value Fund - Growth", "3726.583", "959956.25"),
    ("150799", "WhiteOak Capital Large Cap Fund - Growth", "20681.514", "299985.00"),
]

ENTRY_DATE = date(2026, 4, 1)

DEFAULT_DB_PATH = Path("data/portfolio/portfolio.sqlite")


def build_transactions(entry_date: date = ENTRY_DATE) -> list[MFTransaction]:
    """Build the 11 INITIAL MFTransaction objects from the holdings table.

    Separated from the store call so tests can verify the transactions
    without touching a database.

    Args:
        entry_date: Allotment date to record against all transactions.

    Returns:
        One MFTransaction per scheme, type INITIAL.
    """
    return [
        MFTransaction(
            scheme_name=name,
            amfi_code=code,
            transaction_date=entry_date,
            units=Decimal(units),
            amount=Decimal(amount),
            transaction_type=TransactionType.INITIAL,
        )
        for code, name, units, amount in _HOLDINGS
    ]


def seed_holdings(store: MFStore, entry_date: date = ENTRY_DATE) -> int:
    """Insert initial holdings into *store*.  Idempotent.

    Args:
        store: Initialised MFStore to insert into.
        entry_date: Transaction date for all INITIAL entries.

    Returns:
        Number of transactions attempted (always 11 — duplicates are silently
        skipped by the store, not counted separately).
    """
    txs = build_transactions(entry_date)
    return store.insert_transactions_bulk(txs)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Seed initial MF holdings into the portfolio database."
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
        help="Print the transactions that would be inserted without touching the DB.",
    )
    return parser.parse_args()


def main() -> None:
    """CLI entry point."""
    args = _parse_args()

    txs = build_transactions()

    if args.dry_run:
        print(f"Dry run — {len(txs)} transactions would be inserted:\n")
        for tx in txs:
            print(f"  {tx.amfi_code}  {tx.scheme_name}")
            print(
                f"    units={tx.units}  amount={tx.amount}  date={tx.transaction_date}"
            )
        return

    store = MFStore(args.db_path)
    count = seed_holdings(store)
    print(f"Seeded {count} transactions into {args.db_path}")

    holdings = store.get_holdings()
    print(f"\n{len(holdings)} schemes now in holdings:")
    total_invested = sum(h.total_invested for h in holdings.values())
    for code, h in sorted(holdings.items()):
        print(f"  {code}  {h.scheme_name}")
        print(f"    units={h.total_units}  invested=₹{h.total_invested:,.2f}")
    print(f"\nTotal invested: ₹{total_invested:,.2f}")


if __name__ == "__main__":
    main()

"""Backfill all existing ILTS and FinRakshak positions as initial BUY/SELL trades.

Idempotent — safe to run any number of times.  The unique constraint on
(strategy_name, leg_role, trade_date, action) with ON CONFLICT DO NOTHING
guarantees that no row is ever double-inserted.

Dates marked 2026-01-15 are placeholder entry dates for the original strategy
launch.  Correct them once actual contract notes are available by editing
``_ILTS_TRADES`` / ``_FINRAKSHAK_TRADES`` and re-running.

LIQUIDBEES instrument key (NSE_EQ|INF204KA1983) must be verified against the
BOD instrument file via ``src/instruments/lookup.py --find-legs`` before use in
production.  The correct ISIN is INF204KA1983 (LiquidBees ETF).

Usage:
    python scripts/seed_trades.py
    python scripts/seed_trades.py --db-path /path/to/other.sqlite
    python scripts/seed_trades.py --dry-run
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.models.portfolio import Trade, TradeAction
from src.portfolio.store import PortfolioStore

# ---------------------------------------------------------------------------
# Trade data — placeholder dates (2026-01-15) pending contract note review
# ---------------------------------------------------------------------------

# Each tuple: (strategy_name, leg_role, instrument_key, trade_date, action, qty, price)
_ILTS_TRADES: list[tuple[str, str, str, date, TradeAction, int, str]] = [
    (
        "finideas_ilts", "EBBETF0431", "NSE_EQ|INF754K01LE1",
        date(2026, 1, 15), TradeAction.BUY, 438, "1388.12",
    ),
    (
        "finideas_ilts", "EBBETF0431", "NSE_EQ|INF754K01LE1",
        date(2026, 4, 8), TradeAction.BUY, 27, "1386.20",
    ),
    (
        # LIQUIDBEES instrument key verified against NSE.json.gz BOD file
        # on 2026-04-08 via InstrumentLookup.search_equity('LIQUIDBEES').
        "finideas_ilts", "LIQUIDBEES", "NSE_EQ|INF732E01037",
        date(2026, 4, 8), TradeAction.BUY, 22, "1000.00",
    ),
    (
        "finideas_ilts", "NIFTY_DEC_PE", "NSE_FO|37810",
        date(2026, 1, 15), TradeAction.BUY, 65, "975.00",
    ),
    (
        "finideas_ilts", "NIFTY_JUN_CE", "NSE_FO|37799",
        date(2026, 1, 15), TradeAction.BUY, 65, "1082.00",
    ),
    (
        # SELL = short leg; premium received, not paid.
        "finideas_ilts", "NIFTY_JUN_PE", "NSE_FO|37805",
        date(2026, 1, 15), TradeAction.SELL, 65, "840.00",
    ),
]

_FINRAKSHAK_TRADES: list[tuple[str, str, str, date, TradeAction, int, str]] = [
    (
        "finrakshak", "NIFTY_DEC_PE", "NSE_FO|37810",
        date(2026, 1, 15), TradeAction.BUY, 65, "962.15",
    ),
]

DEFAULT_DB_PATH = Path("data/portfolio/portfolio.sqlite")


def build_trades() -> list[Trade]:
    """Construct all seed Trade objects from the static tables above.

    Pure function — no I/O.  Tests call this directly to verify shape
    without touching a database.

    Returns:
        Ordered list of Trade objects: ILTS trades first, FinRakshak second.
    """
    rows = _ILTS_TRADES + _FINRAKSHAK_TRADES
    return [
        Trade(
            strategy_name=strategy,
            leg_role=leg_role,
            instrument_key=instrument_key,
            trade_date=trade_date,
            action=action,
            quantity=qty,
            price=Decimal(price),
        )
        for strategy, leg_role, instrument_key, trade_date, action, qty, price in rows
    ]


def seed_trades(store: PortfolioStore) -> int:
    """Insert all seed trades into *store*.  Idempotent.

    Args:
        store: Initialised PortfolioStore to insert into.

    Returns:
        Number of trades attempted (duplicates silently skipped by the store).
    """
    trades = build_trades()
    for trade in trades:
        store.record_trade(trade)
    return len(trades)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Backfill ILTS and FinRakshak positions as initial trade records."
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
        help="Print trades that would be inserted without touching the DB.",
    )
    return parser.parse_args()


def main() -> None:
    """CLI entry point."""
    args = _parse_args()
    trades = build_trades()

    if args.dry_run:
        print(f"Dry run — {len(trades)} trades would be inserted:\n")
        for t in trades:
            print(
                f"  {t.strategy_name:12s}  {t.leg_role:16s}  "
                f"{t.action.value:4s}  {t.quantity:5d} @ ₹{t.price}  "
                f"({t.trade_date})"
            )
        return

    store = PortfolioStore(args.db_path)
    count = seed_trades(store)
    print(f"Seeded {count} trades into {args.db_path}\n")

    for strategy in ("finideas_ilts", "finrakshak"):
        legs = {t.leg_role for t in trades if t.strategy_name == strategy}
        print(f"{strategy}:")
        for leg in sorted(legs):
            net_qty, avg_price = store.get_position(strategy, leg)
            print(f"  {leg:16s}  net={net_qty:5d}  avg_price=₹{avg_price:.2f}")


if __name__ == "__main__":
    main()

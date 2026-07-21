"""Standalone mark-to-market snapshot for paper trading strategies.

Fetches live LTPs for all open paper positions, computes P&L, and persists a
PaperNavSnapshot row in paper_nav_snapshots.  Idempotent — re-running for the
same (strategy, date) updates the existing row.

Does NOT touch daily_snapshot.py or the live trades ledger.

Dry-run is on by default — use ``--no-dry-run`` to write to the DB.

Usage:
    # Inspect all strategies (dry-run, no DB write):
    python scripts/paper_snapshot.py

    # Inspect a single strategy:
    python scripts/paper_snapshot.py --strategy paper_csp_nifty_v1

    # Write snapshot for a single strategy:
    python scripts/paper_snapshot.py --strategy paper_csp_nifty_v1 --no-dry-run

    # With known underlying price:
    python scripts/paper_snapshot.py --spot 23250.5 --no-dry-run

    # Historical date:
    python scripts/paper_snapshot.py --date 2026-05-01 --no-dry-run

Cron line (15:35 IST = 10:05 UTC):
    5 10 * * 1-5  cd /path/to/NiftyShield && python scripts/paper_snapshot.py --strategy paper_csp_nifty_v1 --no-dry-run

Environment:
    UPSTOX_ENV              prod | sandbox | test  (default: prod)
    UPSTOX_ACCESS_TOKEN     required for prod/sandbox
    UPSTOX_ANALYTICS_TOKEN  required for market data (LTP)
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import date
from pathlib import Path

import structlog

from src.config import settings
from src.utils.logging import setup_logging

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.client.factory import create_client
from src.paper.constants import DEFAULT_DB_PATH
from src.paper.formatting import format_pnl_table
from src.paper.store import PaperStore
from src.paper.tracker import PaperTracker

pass
_SCRIPT_NAME = "scripts.portfolio.paper_snapshot"
logger = structlog.get_logger(_SCRIPT_NAME)


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
        type=date.fromisoformat,
        default=None,
        help="Snapshot date in YYYY-MM-DD (defaults to today).",
    )
    parser.add_argument(
        "--spot",
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
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "Compute and print P&L without writing to the DB (default: on). "
            "Use --no-dry-run to write."
        ),
    )
    return parser.parse_args()


async def _run(args: argparse.Namespace) -> int:
    """Async entry point. Returns exit code."""
    from dotenv import load_dotenv

    load_dotenv()

    snap_date = args.date or date.today()

    env = settings.upstox_env
    client = create_client(env=env)
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

    any_printed = False
    pnl_rows = []
    all_notes = []
    failed_strategies: list[str] = []

    for name in strategy_names:
        # Fault isolation: one strategy's LTP/broker failure must not abort
        # the batch and silently skip every strategy that sorts after it
        # alphabetically. Log, record the failure, and move on. See
        # docs/bugs/bugs.md BUG-016/017/018 for prior incidents where a
        # single bad leg's resolution failure went undetected because
        # nothing downstream distinguished "no trades" from "fetch failed".
        try:
            pnl = await tracker.compute_pnl(name)
            if pnl is None:
                continue

            unrealized, realized, total = pnl
            pnl_rows.append(
                {
                    "strategy": name,
                    "unrealized": unrealized,
                    "realized": realized,
                    "total": total,
                }
            )
            any_printed = True

            # Collect notes from open trades/legs (only the most recent trade per open leg)
            trades = store.get_trades(name)
            positions = store.get_positions(name)
            open_legs = {p.leg_role for p in positions if p.net_qty != 0}

            most_recent_trade_per_leg = {}
            for trade in trades:
                if trade.leg_role in open_legs:
                    most_recent_trade_per_leg[trade.leg_role] = trade

            for leg_role, trade in most_recent_trade_per_leg.items():
                if trade.notes and trade.notes.strip():
                    all_notes.append((leg_role, trade.notes.strip()))

            if args.dry_run:
                # Still print the underlying for context in dry-run
                if args.spot is not None:
                    print(f"{name} underlying : ₹{args.spot:,.2f}")
            else:
                snap = await tracker.record_daily_snapshot(
                    name,
                    snapshot_date=snap_date,
                    underlying_price=args.spot,
                )
                if snap:
                    print(f"  ✅  {name}: recorded to DB (P&L: ₹{float(total):+,.2f})")
        except Exception as exc:  # noqa: BLE001 - deliberate batch-fault isolation boundary
            failed_strategies.append(name)
            logger.error(
                "paper_snapshot.strategy_failed",
                strategy=name,
                error=str(exc),
                error_type=type(exc).__name__,
            )
            print(f"  ❌  {name}: snapshot FAILED — {type(exc).__name__}: {exc}", file=sys.stderr)
            continue
    if pnl_rows:
        print(
            "\n"
            + format_pnl_table(
                pnl_rows, title=f"Snapshots for {snap_date}", is_dry_run=args.dry_run
            )
        )
        if all_notes:
            seen = set()
            deduped_notes = []
            for leg_role, note in all_notes:
                pair = (leg_role, note)
                if pair not in seen:
                    seen.add(pair)
                    deduped_notes.append(f"[{leg_role}] {note}")
            print("Notes: " + " | ".join(deduped_notes))
    elif not any_printed:
        print("No active strategies with trades found.")

    if failed_strategies:
        logger.error(
            "paper_snapshot.batch_partial_failure",
            failed_count=len(failed_strategies),
            failed_strategies=failed_strategies,
        )
        print(
            f"\n⚠️  {len(failed_strategies)} strategy(ies) FAILED to snapshot: "
            f"{', '.join(failed_strategies)}",
            file=sys.stderr,
        )
        return 1

    return 0


def main() -> None:
    """CLI entry point."""
    args = _parse_args()
    exit_code = asyncio.run(_run(args))
    sys.exit(exit_code)


if __name__ == "__main__":
    setup_logging()
    main()

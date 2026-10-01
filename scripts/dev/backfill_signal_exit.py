#!/usr/bin/env python3
"""Repair ``signal_outcomes`` rows that stored the EOD LTP instead of the tracker's exit fill.

BUG-063. Before the fix, ``scripts/signal_eod.py`` wrote the 16:00 LTP as ``exit_premium`` for
every executed day. For each executed outcome in the date range that has a closed
``SignalTrackV1`` position, this rewrites ``exit_premium`` to the closing SELL fill and
recomputes ``pnl_per_lot = (exit - entry) * LOT_SIZE``. Every other column is preserved.

Dry-run by default; ``--apply`` backs up the DB file first, then upserts via
``SignalStore.record_outcome``. Idempotent: rows already equal to the fill are skipped.

Usage:
    python -m scripts.dev.backfill_signal_exit --from 2026-09-21 --to 2026-10-01
    python -m scripts.dev.backfill_signal_exit --from 2026-09-21 --to 2026-10-01 --apply
"""

from __future__ import annotations

import argparse
import shutil
import sys
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import structlog

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.config import settings  # noqa: E402
from src.paper.constants import LOT_SIZE  # noqa: E402
from src.paper.store import PaperStore  # noqa: E402
from src.signals.store import SignalStore  # noqa: E402
from src.utils.logging import setup_logging  # noqa: E402

_SCRIPT_NAME = "scripts.dev.backfill_signal_exit"
logger = structlog.get_logger(_SCRIPT_NAME)


@dataclass(frozen=True)
class Change:
    """One outcome row whose stored exit differs from the tracker's fill."""

    trade_date: date
    old_exit: Decimal | None
    new_exit: Decimal
    old_pnl: Decimal | None
    new_pnl: Decimal
    reason: str


def backfill(
    signal_store: SignalStore,
    paper_store: PaperStore,
    from_date: date,
    to_date: date,
    apply: bool,
) -> list[Change]:
    """Find (and, when ``apply``, rewrite) outcomes disagreeing with the tracker exit fill.

    Args:
        signal_store: Store holding ``signal_outcomes``.
        paper_store: Store holding the signal-track ledger and exit events.
        from_date: Inclusive lower bound on ``trade_date``.
        to_date: Inclusive upper bound on ``trade_date``.
        apply: Write the corrected rows; otherwise only report them.

    Returns:
        The changes found, oldest first.
    """
    changes: list[Change] = []
    for outcome in signal_store.get_all_outcomes(from_date, to_date):
        if not outcome.executed or outcome.entry_premium is None:
            continue
        entries = paper_store.get_entries(outcome.trade_date, outcome.trade_date)
        if not entries:
            continue
        tracker_exit = paper_store.get_signal_exit(entries[0].trade_id)
        if tracker_exit is None or tracker_exit.exit_price == outcome.exit_premium:
            continue
        new_pnl = (tracker_exit.exit_price - outcome.entry_premium) * LOT_SIZE
        changes.append(
            Change(
                outcome.trade_date,
                outcome.exit_premium,
                tracker_exit.exit_price,
                outcome.pnl_per_lot,
                new_pnl,
                tracker_exit.reason.value,
            )
        )
        if apply:
            signal_store.record_outcome(
                outcome.model_copy(
                    update={"exit_premium": tracker_exit.exit_price, "pnl_per_lot": new_pnl}
                )
            )
    return changes


def _parse_date(value: str) -> date:
    return date.fromisoformat(value)


def main() -> None:
    """CLI entrypoint."""
    setup_logging()
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--from", dest="from_date", type=_parse_date, required=True)
    parser.add_argument("--to", dest="to_date", type=_parse_date, required=True)
    parser.add_argument("--apply", action="store_true", help="Write changes (default: dry-run).")
    args = parser.parse_args()

    db_path = Path(settings.db_path)
    if args.apply:
        backup = db_path.with_name(f"{db_path.name}.bak-{datetime.now():%Y%m%d%H%M%S}")
        shutil.copy2(db_path, backup)
        logger.info("backfill_signal_exit_backup", path=str(backup))

    changes = backfill(
        SignalStore(str(db_path)), PaperStore(db_path), args.from_date, args.to_date, args.apply
    )
    for c in changes:
        print(
            f"{c.trade_date} {c.reason:<13} exit {c.old_exit} -> {c.new_exit}  "
            f"pnl {c.old_pnl} -> {c.new_pnl}"
        )
    mode = "applied" if args.apply else "dry-run (nothing written)"
    print(f"{len(changes)} row(s) {mode}")


if __name__ == "__main__":
    main()

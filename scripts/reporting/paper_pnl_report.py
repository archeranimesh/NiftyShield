"""Daily P&L reporting for paper-trading strategies.

Reads ``paper_nav_snapshots`` (per-strategy, cumulative-as-of-date — see SNAP-1
findings, `docs/plan/paper-ic-daily-snapshot/stories.md`) and produces:

1. Daily P&L graph data (one point per snapshot date).
2. Realized P&L since inception.
3. Realized P&L for the current calendar month.
4. Unrealized P&L since inception.

Design notes (see SNAP-1/SNAP-4 findings for full rationale):

- ``paper_nav_snapshots.total_pnl`` is NOT trusted as-stored — SNAP-1 found 42/267 rows
  where it doesn't equal ``unrealized_pnl + realized_pnl``. Every total in this module is
  recomputed at query time from the two components instead of reading the stored column.
- "Realized P&L since inception" does NOT read the latest snapshot's ``realized_pnl``
  directly — that field resets to 0 on a full open→close→reopen cycle boundary (confirmed
  live for ``paper_nifty_futures`` on 2026-08-05), which would silently drop every prior
  cycle's realized P&L. Instead this sums directly from the append-only ``paper_trades``
  ledger via ``get_strategy_realized_pnl()`` (`src/paper/tracker.py`), which is immune to
  that reset because it recomputes from the full trade history every call.
- "Realized P&L this month" uses the simpler nav-snapshot-diff approach the story
  specifies (latest row minus the last row strictly before the current month started,
  falling back to the latest row directly when the strategy opened mid-month). This is a
  narrower window than "since inception" so a mid-window cycle reset is a real but rarer
  edge case, not handled in this first pass — flagged here rather than silently ignored.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

import structlog

# Add project root to sys.path (matches scripts/strategies/ic/paper_ic_snapshot.py convention)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.paper.constants import DEFAULT_DB_PATH
from src.paper.store import PaperStore
from src.paper.tracker import get_strategy_realized_pnl
from src.utils.logging import setup_logging

_SCRIPT_NAME = "scripts.reporting.paper_pnl_report"
logger = structlog.get_logger(_SCRIPT_NAME)


@dataclass(frozen=True)
class DailyPnLPoint:
    """One point in the daily P&L graph series.

    Attributes:
        snapshot_date: Date of this snapshot.
        total_pnl: unrealized_pnl + realized_pnl, recomputed at query time
            (never read from the stored `paper_nav_snapshots.total_pnl` column — see
            module docstring for why).
    """

    snapshot_date: date
    total_pnl: Decimal


@dataclass(frozen=True)
class PnLReport:
    """Daily graph data plus inception/monthly P&L summary for one strategy.

    Attributes:
        strategy_name: Paper strategy this report covers.
        has_data: False when the strategy has zero `paper_nav_snapshots` rows (e.g. every
            IC variant until SNAP-2's decision lands enough daily rows) — callers must
            check this before treating the other fields as meaningful, never assume an
            empty `daily_series` means zero P&L.
        daily_series: One `DailyPnLPoint` per snapshot date, ordered ASC.
        realized_since_inception: Cumulative realized P&L, summed from `paper_trades`
            directly (survives cycle resets — see module docstring).
        realized_this_month: Realized P&L change within the current calendar month.
        unrealized_since_inception: Latest snapshot's unrealized_pnl (mark-to-market of
            currently open positions).
    """

    strategy_name: str
    has_data: bool
    daily_series: list[DailyPnLPoint]
    realized_since_inception: Decimal
    realized_this_month: Decimal
    unrealized_since_inception: Decimal


def build_pnl_report(
    store: PaperStore,
    strategy_name: str,
    as_of: date | None = None,
) -> PnLReport:
    """Build a `PnLReport` for one strategy.

    Pure data function — no I/O beyond the `PaperStore` reads passed in. Importable
    directly by a future graphing layer without going through the CLI.

    Args:
        store: PaperStore instance to read from.
        strategy_name: Paper strategy to report on.
        as_of: Date to treat as "today" for the current-month window. Defaults to
            `date.today()`. Exposed as a param so tests don't depend on wall-clock time.

    Returns:
        PnLReport. `has_data=False` with all-zero aggregates when the strategy has no
        `paper_nav_snapshots` rows yet.
    """
    snapshots = store.get_nav_snapshots(strategy_name)

    if not snapshots:
        logger.warning("paper_pnl_report.no_snapshots", strategy=strategy_name)
        return PnLReport(
            strategy_name=strategy_name,
            has_data=False,
            daily_series=[],
            realized_since_inception=Decimal("0"),
            realized_this_month=Decimal("0"),
            unrealized_since_inception=Decimal("0"),
        )

    daily_series = [
        DailyPnLPoint(
            snapshot_date=s.snapshot_date,
            total_pnl=s.realized_pnl + s.unrealized_pnl,
        )
        for s in snapshots
    ]

    latest = snapshots[-1]
    as_of = as_of or date.today()
    month_start = as_of.replace(day=1)

    baseline = None
    for s in snapshots:
        if s.snapshot_date < month_start:
            baseline = s
        else:
            break

    realized_this_month = (
        latest.realized_pnl - baseline.realized_pnl if baseline is not None else latest.realized_pnl
    )

    realized_since_inception = get_strategy_realized_pnl(store, strategy_name)

    return PnLReport(
        strategy_name=strategy_name,
        has_data=True,
        daily_series=daily_series,
        realized_since_inception=realized_since_inception,
        realized_this_month=realized_this_month,
        unrealized_since_inception=latest.unrealized_pnl,
    )


def _report_to_json(report: PnLReport) -> str:
    """Serialize a PnLReport to a JSON string (Decimal/date as str)."""

    def _default(obj: object) -> str:
        if isinstance(obj, Decimal):
            return str(obj)
        if isinstance(obj, date):
            return obj.isoformat()
        raise TypeError(f"Not serializable: {obj!r}")

    return json.dumps(asdict(report), default=_default, indent=2)


def _report_to_text(report: PnLReport) -> str:
    if not report.has_data:
        return f"{report.strategy_name}: no snapshot data yet."

    lines = [
        f"P&L report — {report.strategy_name}",
        f"  Realized since inception:   {report.realized_since_inception:+,.2f}",
        f"  Realized this month:        {report.realized_this_month:+,.2f}",
        f"  Unrealized since inception: {report.unrealized_since_inception:+,.2f}",
        f"  Daily points: {len(report.daily_series)}"
        f" ({report.daily_series[0].snapshot_date} → {report.daily_series[-1].snapshot_date})",
    ]
    return "\n".join(lines)


def main() -> int:
    setup_logging()

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strategy", required=True, help="Paper strategy_name to report on.")
    parser.add_argument("--json", action="store_true", help="Print JSON instead of plain text.")
    args = parser.parse_args()

    store = PaperStore(DEFAULT_DB_PATH)
    report = build_pnl_report(store, args.strategy)

    logger.info(
        "paper_pnl_report.built",
        strategy=args.strategy,
        has_data=report.has_data,
        points=len(report.daily_series),
    )

    print(_report_to_json(report) if args.json else _report_to_text(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())

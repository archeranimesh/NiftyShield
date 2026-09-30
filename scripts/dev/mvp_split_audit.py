#!/usr/bin/env python3
"""Read-only audit: shortlist possible splits/bonuses for OPEN/PENDING MVP picks.

Scans ``data/offline/equity_ohlcv/`` day-over-day closes from each pick's
``pick_date`` to today and flags any overnight gap within 3% of a standard
split/bonus factor (2, 3, 4, 5, 10, 1.5, 2.5 or inverses). This is a
detection heuristic, not a classifier: it only prints candidates. It never
writes to the database and never inserts a corporate-action row (BUG-054).

Confirm each candidate against the NSE announcement, then record it manually
with ``python -m scripts.mvp corporate-action add`` using the bhavcopy gap
date printed here as ``--ex-date`` (not the news article's record date).
Gaps already covered by a recorded action are omitted.

``print`` is the CLI output contract (a candidate table on stdout), not a log
line — so this script declares no structlog logger, matching
``graph_snippet.py``.

Usage::

    python -m scripts.dev.mvp_split_audit [--db PATH] [--data-dir PATH]
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

from src.mvp.backfill import DEFAULT_EQUITY_DIR, fetch_historical_closes
from src.mvp.detection import GapMatch, match_split_factor
from src.mvp.models import CorporateAction, Pick, PickStatus
from src.mvp.store import MVPStore

DEFAULT_DB_PATH = Path("data/portfolio/portfolio.sqlite")


@dataclass(frozen=True)
class GapCandidate:
    """One day-over-day close gap that matches a standard split factor."""

    symbol: str
    gap_date: date
    prev_close: Decimal
    close: Decimal
    match: GapMatch


def find_gap_candidates(
    symbol: str,
    closes: list[tuple[date, Decimal]],
    actions: list[CorporateAction] | None = None,
) -> list[GapCandidate]:
    """Flag consecutive-close gaps matching a standard factor.

    Args:
        symbol: The symbol the closes belong to.
        closes: ``(date, raw close)`` pairs, ascending by date.
        actions: Recorded actions; a gap on a recorded ``ex_date`` is skipped.

    Returns:
        Candidates ordered by ``gap_date`` (the later day of the pair, i.e.
        the would-be ex-date).
    """
    recorded = {a.ex_date for a in actions or []}
    found: list[GapCandidate] = []
    for (_, prev), (day, close) in zip(closes, closes[1:], strict=False):
        if day.isoformat() in recorded:
            continue
        match = match_split_factor(prev, close)
        if match is not None:
            found.append(GapCandidate(symbol, day, prev, close, match))
    return found


def audit_picks(
    store: MVPStore,
    *,
    data_dir: Path = DEFAULT_EQUITY_DIR,
    to_date: date | None = None,
) -> list[tuple[Pick, GapCandidate]]:
    """Scan every OPEN/PENDING pick's price history for split-like gaps.

    Args:
        store: The MVP store (read only; ``init_db`` is not called).
        data_dir: Root of the equity Parquet tree.
        to_date: End of the scan; defaults to today.

    Returns:
        ``(pick, candidate)`` pairs.
    """
    to_date = to_date or date.today()
    picks = store.list_picks(PickStatus.OPEN) + store.list_picks(PickStatus.PENDING)
    results: list[tuple[Pick, GapCandidate]] = []
    for pick in picks:
        from_date = date.fromisoformat(pick.pick_date[:10])
        closes = fetch_historical_closes(pick.symbol, from_date, to_date, data_dir=data_dir)
        actions = store.get_corporate_actions(pick.symbol)
        results.extend((pick, c) for c in find_gap_candidates(pick.symbol, closes, actions))
    return results


def main(argv: list[str] | None = None) -> int:
    """CLI entry point; prints candidates, returns a process exit code."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_EQUITY_DIR)
    args = parser.parse_args(argv)
    if not args.db.exists():
        print(f"DB not found: {args.db}")
        return 1

    candidates = audit_picks(MVPStore(args.db), data_dir=args.data_dir)
    if not candidates:
        print("No split-like gaps found.")
        return 0
    print("PICK | SYMBOL | STATUS | GAP_DATE | PREV_CLOSE | CLOSE | PATTERN")
    for pick, c in candidates:
        print(
            f"{pick.pick_id[:8]} | {c.symbol} | {pick.status.value} | {c.gap_date} | "
            f"{c.prev_close} | {c.close} | {c.match.label}"
        )
    print("Candidates only: confirm against NSE announcements before any corporate-action add.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

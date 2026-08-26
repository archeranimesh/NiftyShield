"""Unit tests for scripts/reporting/paper_pnl_report.py.

No network. Uses a tmp_path SQLite DB via PaperStore, no MockBrokerClient needed since
build_pnl_report only reads persisted PaperNavSnapshot/PaperTrade rows.
"""

from __future__ import annotations

import sqlite3
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from scripts.reporting.paper_pnl_report import build_pnl_report
from src.models.portfolio import TradeAction
from src.paper.models import PaperTrade
from src.paper.store import PaperStore

_STRATEGY = "paper_ic_nifty_v2_monthly"
_KEY = "NSE_FO|12345"


@pytest.fixture
def store(tmp_path: Path) -> PaperStore:
    return PaperStore(tmp_path / "paper_pnl_report.db")


def _write_snapshot_with_wrong_total_pnl(
    db_path: Path, snapshot_date: date, unrealized: str, realized: str
) -> None:
    """Insert a paper_nav_snapshots row with a deliberately wrong total_pnl.

    Bypasses PaperStore.record_nav_snapshot (which enforces total_pnl ==
    unrealized_pnl + realized_pnl as of SNAP-5) via raw sqlite3, to prove
    build_pnl_report recomputes rather than trusting the stored column
    (SNAP-1's 42/267-row invariant-violation finding — the scenario this
    test guards against predates SNAP-5's write-time enforcement and can
    still exist in historical rows before any backfill runs).
    """
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """INSERT INTO paper_nav_snapshots
               (strategy_name, snapshot_date, unrealized_pnl, realized_pnl,
                total_pnl, underlying_price)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (_STRATEGY, snapshot_date.isoformat(), unrealized, realized, "999999", None),
        )
        conn.commit()
    finally:
        conn.close()


def test_happy_path_multi_day_series_and_aggregates(store: PaperStore, tmp_path: Path) -> None:
    """3+ snapshot dates, one leg closed within the month → correct series + aggregates."""
    db_path = tmp_path / "paper_pnl_report.db"
    _write_snapshot_with_wrong_total_pnl(db_path, date(2026, 7, 30), "1000.00", "0")
    _write_snapshot_with_wrong_total_pnl(db_path, date(2026, 8, 3), "1200.00", "0")
    _write_snapshot_with_wrong_total_pnl(db_path, date(2026, 8, 5), "500.00", "700.00")

    # Realized-since-inception is sourced from paper_trades, not the snapshot's
    # realized_pnl column — record a closed round-trip so get_strategy_realized_pnl has
    # something to sum.
    store.record_trade(
        PaperTrade(
            strategy_name=_STRATEGY,
            leg_role="short_put",
            instrument_key=_KEY,
            trade_date=date(2026, 8, 5),
            action=TradeAction.SELL,
            quantity=75,
            price=Decimal("100.00"),
        )
    )
    store.record_trade(
        PaperTrade(
            strategy_name=_STRATEGY,
            leg_role="short_put",
            instrument_key=_KEY,
            trade_date=date(2026, 8, 5),
            action=TradeAction.BUY,
            quantity=75,
            price=Decimal("90.00"),
        )
    )

    report = build_pnl_report(store, _STRATEGY, as_of=date(2026, 8, 7))

    assert report.has_data is True
    assert [p.snapshot_date for p in report.daily_series] == [
        date(2026, 7, 30),
        date(2026, 8, 3),
        date(2026, 8, 5),
    ]
    # Recomputed total, not the deliberately-wrong stored 999999.
    assert report.daily_series[0].total_pnl == Decimal("1000.00")
    assert report.daily_series[2].total_pnl == Decimal("1200.00")

    # (100-90)*75 = 750, summed from paper_trades directly.
    assert report.realized_since_inception == Decimal("750.00")

    # Baseline = last row strictly before month start (2026-08-01) = 2026-07-30 row.
    # realized_this_month = latest.realized_pnl(700) - baseline.realized_pnl(0) = 700.
    assert report.realized_this_month == Decimal("700.00")

    assert report.unrealized_since_inception == Decimal("500.00")

    # ROLL-2b: month-delta off the same 2026-07-30 baseline row realized_this_month uses.
    # 500 (latest) - 1000 (baseline) = -500, deliberately different from the +500
    # since-inception mark above.
    assert report.unrealized_this_month == Decimal("-500.00")


def test_zero_snapshot_rows_returns_no_data_result(store: PaperStore) -> None:
    """Strategy with no paper_nav_snapshots rows (every IC variant pre-SNAP-2-accrual) →
    a clear has_data=False result, not a crash or a silently empty/misleading chart."""
    report = build_pnl_report(store, "paper_ic_nifty_v1_weekly", as_of=date(2026, 8, 7))

    assert report.has_data is False
    assert report.daily_series == []
    assert report.realized_since_inception == Decimal("0")
    assert report.realized_this_month == Decimal("0")
    assert report.unrealized_since_inception == Decimal("0")
    assert report.unrealized_this_month == Decimal("0")


# --------------------------------------------------------------------------------------
# ROLL-2b — `unrealized_this_month` (`Flt (M)`) + uniform as-of row selection.
# --------------------------------------------------------------------------------------


def test_unrealized_this_month_differs_from_since_inception(
    store: PaperStore, tmp_path: Path
) -> None:
    """A position already open before the 1st makes `Flt (M)` != `Flt (I)` structurally.

    This is the regression the ROLL-2 spec calls mandatory: implementing `Flt (M)` as a
    copy of `Flt (I)` looks correct on any position open the whole month and breaks only
    on a mid-month entry. Here the prior-month baseline row is what separates them, so a
    copy-of-`Flt (I)` implementation fails this assertion rather than coincidentally
    passing it.
    """
    db_path = tmp_path / "paper_pnl_report.db"
    _write_snapshot_with_wrong_total_pnl(db_path, date(2026, 7, 28), "2000.00", "0")
    _write_snapshot_with_wrong_total_pnl(db_path, date(2026, 7, 31), "2400.00", "0")
    _write_snapshot_with_wrong_total_pnl(db_path, date(2026, 8, 4), "3100.00", "0")

    report = build_pnl_report(store, _STRATEGY, as_of=date(2026, 8, 6))

    # Baseline = last row strictly before 2026-08-01 = the 2026-07-31 row (2400), NOT the
    # earliest row (2000) — guards the "last before month start" selection, not just "some
    # earlier row".
    assert report.unrealized_since_inception == Decimal("3100.00")
    assert report.unrealized_this_month == Decimal("700.00")
    assert report.unrealized_this_month != report.unrealized_since_inception


def test_unrealized_this_month_falls_back_when_opened_mid_month(
    store: PaperStore, tmp_path: Path
) -> None:
    """No pre-month snapshot row → month delta IS the since-inception value.

    Documents the one case where `Flt (M)` and `Flt (I)` legitimately coincide, so a future
    reader doesn't mistake the equality for the copy-of-`Flt (I)` bug the test above guards.
    """
    db_path = tmp_path / "paper_pnl_report.db"
    _write_snapshot_with_wrong_total_pnl(db_path, date(2026, 8, 3), "900.00", "0")
    _write_snapshot_with_wrong_total_pnl(db_path, date(2026, 8, 5), "1400.00", "0")

    report = build_pnl_report(store, _STRATEGY, as_of=date(2026, 8, 6))

    assert report.unrealized_since_inception == Decimal("1400.00")
    assert report.unrealized_this_month == Decimal("1400.00")


def test_as_of_bounds_every_row_read_not_just_the_month_baseline(
    store: PaperStore, tmp_path: Path
) -> None:
    """Rows after `as_of` are excluded from the series and from every aggregate.

    Regression for the pre-ROLL-2b behaviour where `latest` was `snapshots[-1]`
    unconditionally: a report built for a past date mixed that date's month window with the
    newest mark on file. Also pins the "latest row at or before as_of" convention ROLL-2b
    settled on — a snapshot gap (holiday, or a run before the 15:36 cron) must read the last
    real mark, never a false zero.
    """
    db_path = tmp_path / "paper_pnl_report.db"
    _write_snapshot_with_wrong_total_pnl(db_path, date(2026, 7, 31), "100.00", "0")
    _write_snapshot_with_wrong_total_pnl(db_path, date(2026, 8, 3), "600.00", "0")
    _write_snapshot_with_wrong_total_pnl(db_path, date(2026, 8, 20), "9999.00", "0")

    # as_of falls on a day with no snapshot row of its own, and before the 08-20 row.
    report = build_pnl_report(store, _STRATEGY, as_of=date(2026, 8, 10))

    assert [p.snapshot_date for p in report.daily_series] == [
        date(2026, 7, 31),
        date(2026, 8, 3),
    ]
    # Last row at or before as_of (08-03), not the newest row on file (08-20).
    assert report.unrealized_since_inception == Decimal("600.00")
    assert report.unrealized_this_month == Decimal("500.00")


def test_as_of_before_every_snapshot_returns_no_data(store: PaperStore, tmp_path: Path) -> None:
    """All rows newer than `as_of` → has_data=False, not a crash on an empty list."""
    db_path = tmp_path / "paper_pnl_report.db"
    _write_snapshot_with_wrong_total_pnl(db_path, date(2026, 8, 3), "600.00", "0")

    report = build_pnl_report(store, _STRATEGY, as_of=date(2026, 7, 15))

    assert report.has_data is False
    assert report.daily_series == []
    assert report.unrealized_since_inception == Decimal("0")
    assert report.unrealized_this_month == Decimal("0")

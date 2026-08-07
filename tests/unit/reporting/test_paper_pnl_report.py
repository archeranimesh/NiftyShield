"""Unit tests for scripts/reporting/paper_pnl_report.py.

No network. Uses a tmp_path SQLite DB via PaperStore, no MockBrokerClient needed since
build_pnl_report only reads persisted PaperNavSnapshot/PaperTrade rows.
"""

from __future__ import annotations

import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from scripts.reporting.paper_pnl_report import build_pnl_report
from src.models.portfolio import TradeAction
from src.paper.models import PaperNavSnapshot, PaperTrade
from src.paper.store import PaperStore

_STRATEGY = "paper_ic_nifty_v2_monthly"
_KEY = "NSE_FO|12345"


@pytest.fixture
def store(tmp_path: Path) -> PaperStore:
    return PaperStore(tmp_path / "paper_pnl_report.db")


def _snapshot(snapshot_date: date, unrealized: str, realized: str) -> PaperNavSnapshot:
    return PaperNavSnapshot(
        strategy_name=_STRATEGY,
        snapshot_date=snapshot_date,
        unrealized_pnl=Decimal(unrealized),
        realized_pnl=Decimal(realized),
        # Deliberately wrong total_pnl to prove build_pnl_report recomputes rather than
        # trusting the stored column (SNAP-1's 42/267-row invariant-violation finding).
        total_pnl=Decimal("999999"),
    )


def test_happy_path_multi_day_series_and_aggregates(store: PaperStore) -> None:
    """3+ snapshot dates, one leg closed within the month → correct series + aggregates."""
    store.record_nav_snapshot(_snapshot(date(2026, 7, 30), "1000.00", "0"))
    store.record_nav_snapshot(_snapshot(date(2026, 8, 3), "1200.00", "0"))
    store.record_nav_snapshot(_snapshot(date(2026, 8, 5), "500.00", "700.00"))

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


def test_zero_snapshot_rows_returns_no_data_result(store: PaperStore) -> None:
    """Strategy with no paper_nav_snapshots rows (every IC variant pre-SNAP-2-accrual) →
    a clear has_data=False result, not a crash or a silently empty/misleading chart."""
    report = build_pnl_report(store, "paper_ic_nifty_v1_weekly", as_of=date(2026, 8, 7))

    assert report.has_data is False
    assert report.daily_series == []
    assert report.realized_since_inception == Decimal("0")
    assert report.realized_this_month == Decimal("0")
    assert report.unrealized_since_inception == Decimal("0")

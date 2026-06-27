# tests/unit/strategies/ic/test_paper_ic_monthly_comparison.py
from datetime import date
from decimal import Decimal

import pytest

from scripts.strategies.ic.paper_ic_monthly_comparison import (
    ICMonthlyStats,
    _get_cycle_start_date,
    build_comparison_report,
)
from src.paper.store import PaperStore
from src.strategy.ic_expiry_config import CONFIGS as V1_CONFIGS
from src.strategy.ic_nifty_v1 import IronCondorV1

V1_CONFIG = V1_CONFIGS["monthly"]


@pytest.fixture
def store(tmp_path) -> PaperStore:
    db_path = tmp_path / "test.sqlite"
    return PaperStore(db_path)


def test_build_stats_no_open_position(store):
    # This is a unit test of the functions and structure
    # _get_cycle_start_date on empty returns None
    assert _get_cycle_start_date(store, "paper_ic_nifty_v1_monthly") is None


def test_captured_fraction_formula():
    # If entry=200, mark=50 -> captured=(200-50)/200 = 0.75
    entry = Decimal("200")
    mark = Decimal("50")
    captured = (entry - mark) / entry
    assert captured == Decimal("0.75")


def test_comparison_report_format():
    v1 = ICMonthlyStats(
        strategy_name="paper_ic_nifty_v1_monthly",
        entry_credit_pts=Decimal("200"),
        current_mark_pts=Decimal("50"),
        captured_fraction=Decimal("0.75"),
        dte=15,
        short_put_delta=Decimal("0.18"),
        short_call_delta=Decimal("0.12"),
        profit_lock_zone=0,
        realized_pnl_month=Decimal("1500"),
        unrealized_pnl=Decimal("7500"),
        signals_fired_today=["DELTA_WARN"],
        roll_count=1,
        lock_count=0,
    )
    v2 = ICMonthlyStats(
        strategy_name="paper_ic_nifty_v2_monthly",
        entry_credit_pts=Decimal("200"),
        current_mark_pts=Decimal("40"),
        captured_fraction=Decimal("0.80"),
        dte=15,
        short_put_delta=Decimal("0.27"),
        short_call_delta=Decimal("0.24"),
        profit_lock_zone=2,
        realized_pnl_month=Decimal("2500"),
        unrealized_pnl=Decimal("8000"),
        signals_fired_today=[],
        roll_count=1,
        lock_count=1,
    )

    report = build_comparison_report(v1, v2, date(2026, 6, 27))
    assert "paper_ic_nifty_v1_monthly" not in report  # It uses "V1 Monthly" and "V2 Monthly"
    assert "V1 Monthly" in report
    assert "V2 Monthly" in report
    assert "Zone 2 ✓" in report
    assert "1 rolls + 1 locks" in report
    assert "Edge so far:  V2 +₹1,500 vs V1" in report


def test_comparison_report_one_missing():
    v1 = ICMonthlyStats(
        strategy_name="paper_ic_nifty_v1_monthly",
        entry_credit_pts=Decimal("200"),
        current_mark_pts=Decimal("50"),
        captured_fraction=Decimal("0.75"),
        dte=15,
        short_put_delta=Decimal("0.18"),
        short_call_delta=Decimal("0.12"),
        profit_lock_zone=0,
        realized_pnl_month=Decimal("1500"),
        unrealized_pnl=Decimal("7500"),
        signals_fired_today=["DELTA_WARN"],
        roll_count=1,
        lock_count=0,
    )
    v2 = ICMonthlyStats(
        strategy_name="paper_ic_nifty_v2_monthly",
        entry_credit_pts=None,
        current_mark_pts=None,
        captured_fraction=None,
        dte=None,
        short_put_delta=None,
        short_call_delta=None,
        profit_lock_zone=0,
        realized_pnl_month=Decimal("2500"),
        unrealized_pnl=Decimal("0"),
        signals_fired_today=[],
        roll_count=0,
        lock_count=0,
    )

    report = build_comparison_report(v1, v2, date(2026, 6, 27))
    assert "No open position" in report
    # V1 total: 1500 + 7500 = 9000
    # V2 total: 2500 + 0 = 2500
    # V2 - V1 = -6500
    assert "Edge so far:  V1 +₹6,500 vs V2" in report


def test_edge_calculation():
    v1 = ICMonthlyStats(
        strategy_name="paper_ic_nifty_v1_monthly",
        entry_credit_pts=None,
        current_mark_pts=None,
        captured_fraction=None,
        dte=None,
        short_put_delta=None,
        short_call_delta=None,
        profit_lock_zone=0,
        realized_pnl_month=Decimal("100"),
        unrealized_pnl=Decimal("100"),
        signals_fired_today=[],
        roll_count=0,
        lock_count=0,
    )
    v2 = ICMonthlyStats(
        strategy_name="paper_ic_nifty_v2_monthly",
        entry_credit_pts=None,
        current_mark_pts=None,
        captured_fraction=None,
        dte=None,
        short_put_delta=None,
        short_call_delta=None,
        profit_lock_zone=0,
        realized_pnl_month=Decimal("150"),
        unrealized_pnl=Decimal("100"),
        signals_fired_today=[],
        roll_count=0,
        lock_count=0,
    )

    report = build_comparison_report(v1, v2, date(2026, 6, 27))
    assert "Edge so far:  V2 +₹50 vs V1" in report


@pytest.mark.asyncio
async def test_build_stats_happy_path(store):
    from scripts.strategies.ic.paper_ic_monthly_comparison import build_stats

    # We will just insert some positions and check if build_stats handles them.
    # We can mock the broker and chain logic.
    class _MockBroker:
        pass

    from datetime import date

    from src.models.portfolio import TradeAction
    from src.paper.models import PaperTrade

    store.record_trades(
        [
            PaperTrade(
                strategy_name="paper_ic_nifty_v1_monthly",
                leg_role="short_put",
                instrument_key="NSE_FO|NIFTY31JUL202624000PE",
                trade_date=date(2026, 6, 25),
                action=TradeAction.SELL,
                quantity=25,
                price=Decimal("100"),
            ),
            PaperTrade(
                strategy_name="paper_ic_nifty_v1_monthly",
                leg_role="short_call",
                instrument_key="NSE_FO|NIFTY31JUL202625000CE",
                trade_date=date(2026, 6, 25),
                action=TradeAction.SELL,
                quantity=25,
                price=Decimal("100"),
            ),
        ]
    )

    stats = await build_stats(
        strategy_name="paper_ic_nifty_v1_monthly",
        strategy_cls=IronCondorV1,
        config=V1_CONFIG,
        store=store,
        broker=_MockBroker(),
        today=date(2026, 6, 27),
    )
    assert stats.dte is not None
    assert stats.dte > 0

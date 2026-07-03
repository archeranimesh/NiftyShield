# tests/unit/strategies/ic/test_paper_ic_monthly_comparison.py
import argparse
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import structlog.testing

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


# ---------------------------------------------------------------------------
# B010.3 — structlog migration (setup_logging() entrypoint + report_sent event)
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_run_deps():
    """Mock all _run() collaborators so it can execute end-to-end offline."""
    with (
        patch("scripts.strategies.ic.paper_ic_monthly_comparison.PaperStore") as m_store_cls,
        patch("scripts.strategies.ic.paper_ic_monthly_comparison.create_client") as m_create,
        patch("scripts.strategies.ic.paper_ic_monthly_comparison.build_stats") as m_build_stats,
        patch("scripts.strategies.ic.paper_ic_monthly_comparison.TelegramGateway") as m_tg_cls,
    ):
        store_inst = MagicMock()
        m_store_cls.return_value = store_inst
        m_create.side_effect = ValueError("no live client in tests")

        async def _fake_build_stats(**kwargs):
            return ICMonthlyStats(
                strategy_name=kwargs["strategy_name"],
                entry_credit_pts=None,
                current_mark_pts=None,
                captured_fraction=None,
                dte=None,
                short_put_delta=None,
                short_call_delta=None,
                profit_lock_zone=0,
                realized_pnl_month=Decimal("0"),
                unrealized_pnl=Decimal("0"),
                signals_fired_today=[],
                roll_count=0,
                lock_count=0,
            )

        m_build_stats.side_effect = _fake_build_stats

        tg_inst = MagicMock()
        tg_inst.send_notification = AsyncMock()
        m_tg_cls.return_value = tg_inst

        yield {"store": store_inst, "telegram": tg_inst, "create_client": m_create}


@pytest.mark.asyncio
async def test_run_calls_setup_logging_first(mock_run_deps) -> None:
    """_run() must call setup_logging() as its first action (LOGGING.md standard)."""
    from scripts.strategies.ic.paper_ic_monthly_comparison import _run

    args = argparse.Namespace(date=date(2026, 6, 27), dry_run=True, db_path="dummy.sqlite")

    with patch("scripts.strategies.ic.paper_ic_monthly_comparison.setup_logging") as mock_setup:
        await _run(args)

    mock_setup.assert_called_once()


@pytest.mark.asyncio
async def test_run_dry_run_does_not_send_or_log_report(mock_run_deps) -> None:
    """--dry-run (default save=False) must not log report_sent or call Telegram."""
    from scripts.strategies.ic.paper_ic_monthly_comparison import _run

    args = argparse.Namespace(date=date(2026, 6, 27), dry_run=True, db_path="dummy.sqlite")

    with structlog.testing.capture_logs() as logs:
        await _run(args)

    events = [entry["event"] for entry in logs]
    assert "ic_monthly_comparison.report_sent" not in events
    mock_run_deps["telegram"].send_notification.assert_not_called()


@pytest.mark.asyncio
async def test_run_no_dry_run_logs_report_sent(mock_run_deps, monkeypatch) -> None:
    """--no-dry-run (save=True) with telegram creds present logs report_sent."""
    from scripts.strategies.ic.paper_ic_monthly_comparison import _run

    monkeypatch.setattr(
        "scripts.strategies.ic.paper_ic_monthly_comparison.settings.telegram_bot_token",
        "dummy-token",
    )
    monkeypatch.setattr(
        "scripts.strategies.ic.paper_ic_monthly_comparison.settings.telegram_chat_id",
        "dummy-chat",
    )
    # Under --no-dry-run, a broker init failure is fatal (sys.exit(1)) rather
    # than falling back to the mock broker — so give create_client a real
    # (mocked) success path instead of the ValueError used by other tests.
    mock_run_deps["create_client"].side_effect = None
    mock_run_deps["create_client"].return_value = MagicMock()

    args = argparse.Namespace(date=date(2026, 6, 27), dry_run=False, db_path="dummy.sqlite")

    with (
        patch("scripts.strategies.ic.paper_ic_monthly_comparison.setup_logging"),
        structlog.testing.capture_logs() as logs,
    ):
        await _run(args)

    events = [entry["event"] for entry in logs]
    assert "ic_monthly_comparison.report_sent" in events
    mock_run_deps["telegram"].send_notification.assert_called_once()

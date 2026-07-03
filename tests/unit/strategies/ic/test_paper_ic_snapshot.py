# tests/unit/strategies/ic/test_paper_ic_snapshot.py
"""Unit tests for EOD audit cron script paper_ic_snapshot.py."""

# fmt: off
from __future__ import annotations

import argparse
import re
from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import structlog.testing

from scripts.strategies.ic.paper_ic_snapshot import _run, process_variant
from src.paper.models import PaperPosition
from src.strategy.ic_expiry_config import CONFIGS
from src.strategy.ic_expiry_config_v2 import CONFIGS_V2
from src.strategy.protocol import SignalEvent


# Test fixtures encode a trading-symbol-shaped date substring inside the
# (otherwise numeric-form) instrument_key purely for readability, e.g.
# "NSE_FO|NIFTY26JUN202624000PE". This helper mirrors that fixture
# convention by resolving it into the {"expiry": epoch_ms} shape
# InstrumentLookup.get_by_key returns in production (BUG-009 fix); it does
# NOT re-implement or re-test production regex logic, which no longer
# exists in scripts/strategies/ic/paper_ic_snapshot.py.
def _fixture_get_by_key(instrument_key: str) -> dict | None:
    m = re.search(r"NIFTY(\d{2}[A-Za-z]{3}\d{4})", instrument_key, re.IGNORECASE)
    if not m:
        return None
    dt = datetime.strptime(m.group(1).upper(), "%d%b%Y").replace(tzinfo=timezone.utc)
    return {"instrument_type": "PE", "expiry": int(dt.timestamp() * 1000)}


@pytest.fixture(autouse=True)
def mock_lookup():
    """Mock InstrumentLookup.from_file globally for tests."""
    target = "src.instruments.lookup.InstrumentLookup.from_file"
    with patch(target) as mock_from_file:
        inst = MagicMock()
        inst.get_by_key.side_effect = _fixture_get_by_key
        mock_from_file.return_value = inst
        yield inst


@pytest.fixture
def mock_store():
    """Mock PaperStore."""
    target = "scripts.strategies.ic.paper_ic_snapshot.PaperStore"
    with patch(target) as mock_cls:
        store_inst = MagicMock()
        store_inst.get_positions.return_value = []
        store_inst.get_open_exit_events.return_value = []
        mock_cls.return_value = store_inst
        yield store_inst


@pytest.fixture
def mock_telegram():
    """Mock TelegramGateway."""
    target = "scripts.strategies.ic.paper_ic_snapshot.TelegramGateway"
    with patch(target) as mock_cls:
        inst = MagicMock()
        inst.send_notification = AsyncMock()
        mock_cls.return_value = inst
        yield inst


@pytest.fixture
def mock_create_client():
    """Mock create_client and the returned broker client."""
    target = "scripts.strategies.ic.paper_ic_snapshot.create_client"
    with patch(target) as mock_cls:
        broker = MagicMock()
        broker.get_option_chain = AsyncMock(return_value=[])
        mock_cls.return_value = broker
        yield broker


@pytest.fixture
def mock_parse_chain():
    """Mock parse_upstox_option_chain."""
    target = (
        "scripts.strategies.ic.paper_ic_snapshot."
        "parse_upstox_option_chain"
    )
    with patch(target) as mock_fn:
        chain = MagicMock()
        chain.underlying_spot = Decimal("24500")
        mock_fn.return_value = chain
        yield mock_fn


@pytest.fixture
def mock_ic_class():
    """Mock IronCondorV1 wrapper."""
    target = "scripts.strategies.ic.paper_ic_snapshot.IronCondorV1"
    with patch(target) as mock_cls:
        ic_inst = MagicMock()
        ic_inst.strategy_name = "paper_ic_nifty_v1_monthly"
        ic_inst.check_signals = AsyncMock(return_value=[])
        ic_inst._compute_ivr_str.return_value = "IVR: 0.42"
        # Mock _find_leg
        leg = MagicMock()
        leg.ltp = Decimal("50.0")
        leg.delta = Decimal("0.10")
        ic_inst._find_leg.return_value = leg
        ic_inst._compute_combined_pnl.return_value = (
            Decimal("100.0"),
            Decimal("150.0"),
        )
        mock_cls.return_value = ic_inst
        yield ic_inst


@pytest.mark.asyncio
async def test_no_active_variants(
    mock_store, mock_telegram, mock_create_client
):
    """6. No active variants → single 'no open positions' message."""
    mock_store.get_positions.return_value = []
    args = argparse.Namespace(
        date=date(2026, 6, 26),
        dry_run=False,
        db_path="dummy.db",
        bod_path="dummy.json",
    )
    await _run(args)
    mock_telegram.send_notification.assert_called_once_with(
        "IC EOD: no open positions across all expiry types."
    )


@pytest.mark.asyncio
async def test_one_variant_active(
    mock_store,
    mock_telegram,
    mock_create_client,
    mock_parse_chain,
    mock_ic_class,
):
    """1. One variant active → one Telegram message with summary."""
    monthly_name = CONFIGS["monthly"].strategy_name
    positions = [
        PaperPosition(
            strategy_name=monthly_name,
            leg_role="short_put",
            net_qty=-1,
            avg_cost=Decimal("0.0"),
            avg_sell_price=Decimal("80.0"),
            instrument_key="NSE_FO|NIFTY26JUN202624000PE",
            entry_date=date(2026, 6, 1),
        )
    ]
    mock_store.get_positions.side_effect = (
        lambda name: positions if name == monthly_name else []
    )

    args = argparse.Namespace(
        date=date(2026, 6, 26),
        dry_run=False,
        db_path="dummy.db",
        bod_path="dummy.json",
    )

    with patch("sqlite3.connect") as mock_conn:
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []  # No acted events
        exe = mock_conn.return_value.__enter__.return_value.execute
        exe.return_value = mock_cursor

        await _run(args)

    assert mock_telegram.send_notification.call_count == 1
    call_arg = mock_telegram.send_notification.call_args[0][0]
    assert "📋 IC EOD Audit — monthly" in call_arg
    assert "DTE: 0" in call_arg
    assert "Short Put" in call_arg
    assert "P&L: combined" in call_arg
    # because DTE 0 <= dte_warn 21
    assert "Today's signals: DTE_WARN" in call_arg


@pytest.mark.asyncio
async def test_all_four_active(
    mock_store,
    mock_telegram,
    mock_create_client,
    mock_parse_chain,
    mock_ic_class,
):
    """2. All four active → four messages sent."""
    # Setup open positions for all variants
    def get_positions_side_effect(name):
        return [
            PaperPosition(
                strategy_name=name,
                leg_role="short_put",
                net_qty=-1,
                avg_cost=Decimal("0.0"),
                avg_sell_price=Decimal("80.0"),
                instrument_key="NSE_FO|NIFTY26JUN202624000PE",
                entry_date=date(2026, 6, 1),
            )
        ]

    mock_store.get_positions.side_effect = get_positions_side_effect

    args = argparse.Namespace(
        date=date(2026, 6, 26),
        dry_run=False,
        db_path="dummy.db",
        bod_path="dummy.json",
    )

    with patch("sqlite3.connect") as mock_conn:
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []
        exe = mock_conn.return_value.__enter__.return_value.execute
        exe.return_value = mock_cursor

        await _run(args)

    assert mock_telegram.send_notification.call_count == 5


@pytest.mark.asyncio
async def test_intraday_acted_event(
    mock_store,
    mock_telegram,
    mock_create_client,
    mock_parse_chain,
    mock_ic_class,
):
    """3. Intraday ACTED exit event → message has Intraday actions."""
    monthly_name = CONFIGS["monthly"].strategy_name
    positions = [
        PaperPosition(
            strategy_name=monthly_name,
            leg_role="short_put",
            net_qty=-1,
            avg_cost=Decimal("0.0"),
            avg_sell_price=Decimal("80.0"),
            instrument_key="NSE_FO|NIFTY26JUN202624000PE",
            entry_date=date(2026, 6, 1),
        )
    ]
    mock_store.get_positions.side_effect = (
        lambda name: positions if name == monthly_name else []
    )

    args = argparse.Namespace(
        date=date(2026, 6, 26),
        dry_run=False,
        db_path="dummy.db",
        bod_path="dummy.json",
    )

    with patch("sqlite3.connect") as mock_conn:
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            {
                "exit_signal": "PROFIT_TARGET",
                "notes": "CLOSE_FULL",
                "event_time": "2026-06-26T11:42:00",
                "actual_rule_used": "CLOSE_FULL",
            }
        ]
        exe = mock_conn.return_value.__enter__.return_value.execute
        exe.return_value = mock_cursor

        await _run(args)

    call_arg = mock_telegram.send_notification.call_args[0][0]
    expected = "Intraday actions: PROFIT_TARGET → CLOSE_FULL executed at 11:42"
    assert expected in call_arg


@pytest.mark.asyncio
async def test_unresolved_action_signal_at_eod(
    mock_store,
    mock_telegram,
    mock_create_client,
    mock_parse_chain,
    mock_ic_class,
):
    """4. Unresolved ACTION signal → Unresolved block in message."""
    monthly_name = CONFIGS["monthly"].strategy_name
    positions = [
        PaperPosition(
            strategy_name=monthly_name,
            leg_role="short_put",
            net_qty=-1,
            avg_cost=Decimal("0.0"),
            avg_sell_price=Decimal("80.0"),
            instrument_key="NSE_FO|NIFTY26JUN202624000PE",
            entry_date=date(2026, 6, 1),
        )
    ]
    mock_store.get_positions.side_effect = (
        lambda name: positions if name == monthly_name else []
    )

    # Mock an unresolved ACTION event returned by check_signals
    mock_ic_class.check_signals.return_value = [
        SignalEvent(
            event_type="TIME_STOP",
            severity="ACTION",
            description="DTE 14 — position should have been closed today",
            payload={},
        )
    ]

    args = argparse.Namespace(
        date=date(2026, 6, 26),
        dry_run=False,
        db_path="dummy.db",
        bod_path="dummy.json",
    )

    with patch("sqlite3.connect") as mock_conn:
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []
        exe = mock_conn.return_value.__enter__.return_value.execute
        exe.return_value = mock_cursor

        await _run(args)

    call_arg = mock_telegram.send_notification.call_args[0][0]
    assert "⚠️  Unresolved ACTION signals:" in call_arg
    expected = "TIME_STOP 🔴  DTE 14 — position should have been closed today"
    assert expected in call_arg


@pytest.mark.asyncio
async def test_dte_warning_noted(
    mock_store,
    mock_telegram,
    mock_create_client,
    mock_parse_chain,
    mock_ic_class,
):
    """5. DTE ≤ config.dte_warn → DTE_WARN noted."""
    monthly_name = CONFIGS["monthly"].strategy_name
    positions = [
        PaperPosition(
            strategy_name=monthly_name,
            leg_role="short_put",
            net_qty=-1,
            avg_cost=Decimal("0.0"),
            avg_sell_price=Decimal("80.0"),
            instrument_key="NSE_FO|NIFTY26JUN202624000PE",
            entry_date=date(2026, 6, 1),
        )
    ]
    mock_store.get_positions.side_effect = (
        lambda name: positions if name == monthly_name else []
    )
    mock_ic_class.check_signals.return_value = []

    # Expiry is 26th, today is 20th (DTE 6, dte_warn is 21)
    args = argparse.Namespace(
        date=date(2026, 6, 20),
        dry_run=False,
        db_path="dummy.db",
        bod_path="dummy.json",
    )

    with patch("sqlite3.connect") as mock_conn:
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []
        exe = mock_conn.return_value.__enter__.return_value.execute
        exe.return_value = mock_cursor

        await _run(args)

    call_arg = mock_telegram.send_notification.call_args[0][0]
    assert "Today's signals: DTE_WARN ℹ️" in call_arg


@pytest.mark.asyncio
async def test_chain_fetch_fails_for_one_variant(
    mock_store,
    mock_telegram,
    mock_create_client,
    mock_parse_chain,
    mock_ic_class,
):
    """7. Chain fetch fails for one variant → error note in Telegram."""
    weekly_name = CONFIGS["weekly"].strategy_name
    monthly_name = CONFIGS["monthly"].strategy_name

    # Let's customize positions keys so we have different expiries
    weekly_positions = [
        PaperPosition(
            strategy_name=weekly_name,
            leg_role="short_put",
            net_qty=-1,
            avg_cost=Decimal("0.0"),
            avg_sell_price=Decimal("80.0"),
            instrument_key="NSE_FO|NIFTY19JUN202624000PE",  # expiry 19 Jun
            entry_date=date(2026, 6, 1),
        )
    ]
    monthly_positions = [
        PaperPosition(
            strategy_name=monthly_name,
            leg_role="short_put",
            net_qty=-1,
            avg_cost=Decimal("0.0"),
            avg_sell_price=Decimal("80.0"),
            instrument_key="NSE_FO|NIFTY26JUN202624000PE",  # expiry 26 Jun
            entry_date=date(2026, 6, 1),
        )
    ]

    mock_store.get_positions.side_effect = lambda name: (
        weekly_positions if name == weekly_name
        else (monthly_positions if name == monthly_name else [])
    )

    async def get_chain_side_effect(underlying, expiry):
        if "19JUN" in expiry or "2026-06-19" in expiry:
            raise Exception("Weekly chain fetch failed")
        return []

    mock_create_client.get_option_chain.side_effect = get_chain_side_effect

    args = argparse.Namespace(
        date=date(2026, 6, 15),
        dry_run=False,
        db_path="dummy.db",
        bod_path="dummy.json",
    )

    with patch("sqlite3.connect") as mock_conn:
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []
        exe = mock_conn.return_value.__enter__.return_value.execute
        exe.return_value = mock_cursor

        await _run(args)

    assert mock_telegram.send_notification.call_count == 2
    calls = [
        call[0][0] for call in mock_telegram.send_notification.call_args_list
    ]
    assert any("Error: Failed to fetch live option chain" in c for c in calls)
    assert any(
        "📋 IC EOD Audit — monthly" in c and "Error" not in c
        for c in calls
    )


@pytest.mark.asyncio
async def test_check_signals_raises_for_one_variant(
    mock_store,
    mock_telegram,
    mock_create_client,
    mock_parse_chain,
    mock_ic_class,
):
    """8. check_signals raises for one variant → remaining processed."""
    weekly_name = CONFIGS["weekly"].strategy_name
    monthly_name = CONFIGS["monthly"].strategy_name

    weekly_positions = [
        PaperPosition(
            strategy_name=weekly_name,
            leg_role="short_put",
            net_qty=-1,
            avg_cost=Decimal("0.0"),
            avg_sell_price=Decimal("80.0"),
            instrument_key="NSE_FO|NIFTY19JUN202624000PE",
            entry_date=date(2026, 6, 1),
        )
    ]
    monthly_positions = [
        PaperPosition(
            strategy_name=monthly_name,
            leg_role="short_put",
            net_qty=-1,
            avg_cost=Decimal("0.0"),
            avg_sell_price=Decimal("80.0"),
            instrument_key="NSE_FO|NIFTY26JUN202624000PE",
            entry_date=date(2026, 6, 1),
        )
    ]

    mock_store.get_positions.side_effect = lambda name: (
        weekly_positions if name == weekly_name
        else (monthly_positions if name == monthly_name else [])
    )

    async def check_signals_side_effect(chain, positions):
        if any(p.strategy_name == weekly_name for p in positions):
            raise Exception("Weekly signals check failed")
        return []

    mock_ic_class.check_signals.side_effect = check_signals_side_effect

    args = argparse.Namespace(
        date=date(2026, 6, 15),
        dry_run=False,
        db_path="dummy.db",
        bod_path="dummy.json",
    )

    with patch("sqlite3.connect") as mock_conn:
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []
        exe = mock_conn.return_value.__enter__.return_value.execute
        exe.return_value = mock_cursor

        await _run(args)

    assert mock_telegram.send_notification.call_count == 2
    calls = [
        call[0][0] for call in mock_telegram.send_notification.call_args_list
    ]
    assert any("Error: Signal evaluation failed" in c for c in calls)
    assert any(
        "📋 IC EOD Audit — monthly" in c and "Error" not in c
        for c in calls
    )

@pytest.fixture
def mock_v2_class():
    """Mock IronCondorV2 wrapper."""
    target = "scripts.strategies.ic.paper_ic_snapshot.IronCondorV2"
    with patch(target) as mock_cls:
        ic_inst = MagicMock()
        ic_inst.strategy_name = "paper_ic_nifty_v2_monthly"
        ic_inst.check_signals = AsyncMock(return_value=[])
        ic_inst._compute_ivr_str.return_value = "IVR: 0.42"
        leg = MagicMock()
        leg.ltp = Decimal("50.0")
        leg.delta = Decimal("0.10")
        ic_inst._find_leg.return_value = leg
        ic_inst._compute_combined_pnl.return_value = (
            Decimal("100.0"),
            Decimal("150.0"),
        )
        mock_cls.return_value = ic_inst
        yield mock_cls



@pytest.mark.asyncio
async def test_v2_monthly_included_in_audit(
    mock_store,
    mock_telegram,
    mock_create_client,
    mock_parse_chain,
    mock_ic_class,
    mock_v2_class,
):
    """test_v2_monthly_included_in_audit — V2 position in store → process_variant called with strategy_cls=IronCondorV2."""
    v2_monthly_name = CONFIGS_V2["monthly"].strategy_name
    positions = [
        PaperPosition(
            strategy_name=v2_monthly_name,
            leg_role="short_put",
            net_qty=-1,
            avg_cost=Decimal("0.0"),
            avg_sell_price=Decimal("80.0"),
            instrument_key="NSE_FO|NIFTY26JUN202624000PE",
            entry_date=date(2026, 6, 1),
        )
    ]
    mock_store.get_positions.side_effect = (
        lambda name: positions if name == v2_monthly_name else []
    )

    args = argparse.Namespace(
        date=date(2026, 6, 26),
        dry_run=False,
        db_path="dummy.db",
        bod_path="dummy.json",
    )

    with patch("sqlite3.connect") as mock_conn:
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []
        exe = mock_conn.return_value.__enter__.return_value.execute
        exe.return_value = mock_cursor

        await _run(args)

    assert mock_telegram.send_notification.call_count == 1
    call_arg = mock_telegram.send_notification.call_args[0][0]
    assert "📋 IC EOD Audit — monthly (paper_ic_nifty_v2_monthly)" in call_arg
    mock_v2_class.assert_called_once()

@pytest.mark.asyncio
async def test_v2_no_position_skipped(
    mock_store, mock_telegram, mock_create_client, mock_v2_class, mock_ic_class
):
    """test_v2_no_position_skipped — no V2 positions → no V2 report, no error."""
    mock_store.get_positions.return_value = []
    args = argparse.Namespace(
        date=date(2026, 6, 26),
        dry_run=False,
        db_path="dummy.db",
        bod_path="dummy.json",
    )
    await _run(args)
    mock_v2_class.assert_not_called()
    mock_telegram.send_notification.assert_called_once_with(
        "IC EOD: no open positions across all expiry types."
    )

@pytest.mark.asyncio
async def test_v1_loop_unchanged(
    mock_store,
    mock_telegram,
    mock_create_client,
    mock_parse_chain,
    mock_ic_class,
    mock_v2_class,
):
    """test_v1_loop_unchanged — V2 addition does not alter V1 report output."""
    v1_monthly_name = CONFIGS["monthly"].strategy_name
    positions = [
        PaperPosition(
            strategy_name=v1_monthly_name,
            leg_role="short_put",
            net_qty=-1,
            avg_cost=Decimal("0.0"),
            avg_sell_price=Decimal("80.0"),
            instrument_key="NSE_FO|NIFTY26JUN202624000PE",
            entry_date=date(2026, 6, 1),
        )
    ]
    mock_store.get_positions.side_effect = (
        lambda name: positions if name == v1_monthly_name else []
    )

    args = argparse.Namespace(
        date=date(2026, 6, 26),
        dry_run=False,
        db_path="dummy.db",
        bod_path="dummy.json",
    )

    with patch("sqlite3.connect") as mock_conn:
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []
        exe = mock_conn.return_value.__enter__.return_value.execute
        exe.return_value = mock_cursor

        await _run(args)

    assert mock_telegram.send_notification.call_count == 1
    call_arg = mock_telegram.send_notification.call_args[0][0]
    assert "📋 IC EOD Audit — monthly (paper_ic_nifty_v1_monthly)" in call_arg
    mock_v2_class.assert_not_called()


# ---------------------------------------------------------------------------
# B010.3 — structlog migration (setup_logging() entrypoint + report_sent event)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_calls_setup_logging_first(
    mock_store, mock_telegram, mock_create_client
) -> None:
    """_run() must call setup_logging() as its first action (LOGGING.md standard)."""
    args = argparse.Namespace(
        date=date(2026, 6, 26),
        dry_run=False,
        db_path="dummy.db",
        bod_path="dummy.json",
    )
    with patch("scripts.strategies.ic.paper_ic_snapshot.setup_logging") as mock_setup:
        await _run(args)

    mock_setup.assert_called_once()


@pytest.mark.asyncio
async def test_no_positions_report_sent_logs_zero_reports(
    mock_store, mock_telegram, mock_create_client
) -> None:
    """No-open-positions path logs ic_snapshot.report_sent with report_count=0."""
    mock_store.get_positions.return_value = []
    args = argparse.Namespace(
        date=date(2026, 6, 26),
        dry_run=False,
        db_path="dummy.db",
        bod_path="dummy.json",
    )
    with (
        patch("scripts.strategies.ic.paper_ic_snapshot.setup_logging"),
        structlog.testing.capture_logs() as logs,
    ):
        await _run(args)

    events = [entry["event"] for entry in logs]
    assert "ic_snapshot.report_sent" in events
    sent = next(e for e in logs if e["event"] == "ic_snapshot.report_sent")
    assert sent["report_count"] == 0
    assert sent["channel"] == "telegram"


@pytest.mark.asyncio
async def test_one_variant_active_logs_report_sent(
    mock_store,
    mock_telegram,
    mock_create_client,
    mock_parse_chain,
    mock_ic_class,
) -> None:
    """Active-variant path logs ic_snapshot.report_sent with report_count>0."""
    monthly_name = CONFIGS["monthly"].strategy_name
    positions = [
        PaperPosition(
            strategy_name=monthly_name,
            leg_role="short_put",
            net_qty=-1,
            avg_cost=Decimal("0.0"),
            avg_sell_price=Decimal("80.0"),
            instrument_key="NSE_FO|NIFTY26JUN202624000PE",
            entry_date=date(2026, 6, 1),
        )
    ]
    mock_store.get_positions.side_effect = (
        lambda name: positions if name == monthly_name else []
    )

    args = argparse.Namespace(
        date=date(2026, 6, 26),
        dry_run=False,
        db_path="dummy.db",
        bod_path="dummy.json",
    )

    with (
        patch("sqlite3.connect") as mock_conn,
        patch("scripts.strategies.ic.paper_ic_snapshot.setup_logging"),
        structlog.testing.capture_logs() as logs,
    ):
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []
        exe = mock_conn.return_value.__enter__.return_value.execute
        exe.return_value = mock_cursor

        await _run(args)

    events = [entry["event"] for entry in logs]
    assert "ic_snapshot.report_sent" in events
    sent = next(e for e in logs if e["event"] == "ic_snapshot.report_sent")
    assert sent["report_count"] > 0


@pytest.mark.asyncio
async def test_variant_failure_logs_structured_error(
    mock_store, mock_telegram, mock_create_client, mock_parse_chain, mock_ic_class
) -> None:
    """A variant raising unexpectedly logs ic_snapshot.variant_failed, still completes."""
    monthly_name = CONFIGS["monthly"].strategy_name
    positions = [
        PaperPosition(
            strategy_name=monthly_name,
            leg_role="short_put",
            net_qty=-1,
            avg_cost=Decimal("0.0"),
            avg_sell_price=Decimal("80.0"),
            instrument_key="NSE_FO|NIFTY26JUN202624000PE",
            entry_date=date(2026, 6, 1),
        )
    ]
    mock_store.get_positions.side_effect = (
        lambda name: positions if name == monthly_name else []
    )
    mock_ic_class.check_signals.side_effect = RuntimeError("boom")
    # Force process_variant's internal try/except for check_signals to instead
    # raise from a point caught by _run's own variant-level try/except: make
    # _find_leg blow up unexpectedly deep in report assembly instead.
    mock_ic_class.check_signals = AsyncMock(return_value=[])
    mock_ic_class._compute_combined_pnl.side_effect = RuntimeError("boom")

    args = argparse.Namespace(
        date=date(2026, 6, 26),
        dry_run=False,
        db_path="dummy.db",
        bod_path="dummy.json",
    )

    with (
        patch("sqlite3.connect") as mock_conn,
        patch("scripts.strategies.ic.paper_ic_snapshot.setup_logging"),
        structlog.testing.capture_logs() as logs,
    ):
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []
        exe = mock_conn.return_value.__enter__.return_value.execute
        exe.return_value = mock_cursor

        await _run(args)

    events = [entry["event"] for entry in logs]
    assert "ic_snapshot.variant_failed" in events
    assert mock_telegram.send_notification.call_count == 1


# ---------------------------------------------------------------------------
# BUG-009 — expiry resolution via InstrumentLookup.get_by_key, not regex
# against the numeric instrument_key (which never contains a date substring)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_process_variant_resolves_expiry_via_numeric_instrument_key(
    mock_ic_class,
):
    """Happy-path: a numeric instrument_key (e.g. "NSE_FO|63930") with no
    embedded date resolves expiry via InstrumentLookup.get_by_key instead of
    staying stuck on the always-None regex path."""
    store = MagicMock()
    monthly_name = CONFIGS["monthly"].strategy_name
    positions = [
        PaperPosition(
            strategy_name=monthly_name,
            leg_role="short_put",
            net_qty=-1,
            avg_cost=Decimal("0.0"),
            avg_sell_price=Decimal("80.0"),
            instrument_key="NSE_FO|63930",
            entry_date=date(2026, 6, 1),
        )
    ]
    store.get_positions.return_value = positions

    lookup = MagicMock()
    expiry_epoch_ms = int(
        datetime(2026, 6, 26, tzinfo=timezone.utc).timestamp() * 1000
    )
    lookup.get_by_key.return_value = {
        "instrument_type": "PE",
        "expiry": expiry_epoch_ms,
    }

    broker = MagicMock()
    broker.get_option_chain = AsyncMock(return_value=[])
    chain = MagicMock()
    chain.underlying_spot = Decimal("24500")

    with (
        patch("sqlite3.connect") as mock_conn,
        patch(
            "scripts.strategies.ic.paper_ic_snapshot.parse_upstox_option_chain",
            return_value=chain,
        ),
    ):
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []
        exe = mock_conn.return_value.__enter__.return_value.execute
        exe.return_value = mock_cursor

        report = await process_variant(
            "monthly",
            CONFIGS["monthly"],
            store,
            broker,
            lookup,
            None,
            date(2026, 6, 26),
            False,
        )

    lookup.get_by_key.assert_called_with("NSE_FO|63930")
    assert report is not None
    assert "Error: Expiry date could not be parsed" not in report
    assert "DTE: 0" in report


@pytest.mark.asyncio
async def test_process_variant_unresolvable_key_falls_back_no_expiry_found(
    mock_ic_class,
):
    """Edge-case: instrument_key not found in the BOD instrument master
    (unresolvable/legacy key) falls back to the existing no_expiry_found
    error branch instead of crashing."""
    store = MagicMock()
    monthly_name = CONFIGS["monthly"].strategy_name
    positions = [
        PaperPosition(
            strategy_name=monthly_name,
            leg_role="short_put",
            net_qty=-1,
            avg_cost=Decimal("0.0"),
            avg_sell_price=Decimal("80.0"),
            instrument_key="NSE_FO|UNKNOWN_LEGACY_KEY",
            entry_date=date(2026, 6, 1),
        )
    ]
    store.get_positions.return_value = positions

    lookup = MagicMock()
    lookup.get_by_key.return_value = None

    broker = MagicMock()
    with structlog.testing.capture_logs() as logs:
        report = await process_variant(
            "monthly",
            CONFIGS["monthly"],
            store,
            broker,
            lookup,
            None,
            date(2026, 6, 26),
            False,
        )

    assert report is not None
    assert "Error: Expiry date could not be parsed from positions." in report
    events = [entry["event"] for entry in logs]
    assert "ic_snapshot.no_expiry_found" in events

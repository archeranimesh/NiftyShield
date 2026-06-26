# tests/unit/strategies/ic/test_paper_ic_snapshot.py
"""Unit tests for EOD audit cron script paper_ic_snapshot.py."""

# fmt: off
from __future__ import annotations

import argparse
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from scripts.strategies.ic.paper_ic_snapshot import _run
from src.paper.models import PaperPosition
from src.strategy.ic_expiry_config import CONFIGS
from src.strategy.protocol import SignalEvent


@pytest.fixture(autouse=True)
def mock_lookup():
    """Mock InstrumentLookup.from_file globally for tests."""
    target = "src.instruments.lookup.InstrumentLookup.from_file"
    with patch(target) as mock_from_file:
        inst = MagicMock()
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

    assert mock_telegram.send_notification.call_count == 4


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

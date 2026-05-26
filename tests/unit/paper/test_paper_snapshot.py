"""Unit tests for scripts/paper_snapshot.py, specifically trade notes.

Tests the display of trade notes from open legs under the P&L table.
"""

from __future__ import annotations

import argparse
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.models.portfolio import TradeAction
from src.paper.models import PaperPosition, PaperTrade
from scripts.paper_snapshot import _run


@pytest.mark.asyncio
@patch("scripts.paper_snapshot.create_client")
@patch("scripts.paper_snapshot.PaperStore")
@patch("scripts.paper_snapshot.PaperTracker")
async def test_notes_printed_for_open_legs_with_notes(
    mock_tracker_cls: MagicMock,
    mock_store_cls: MagicMock,
    mock_create_client: MagicMock,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Test that notes are printed only for open legs that have non-empty notes."""
    mock_store = MagicMock()
    mock_store_cls.return_value = mock_store

    mock_tracker = MagicMock()
    mock_tracker_cls.return_value = mock_tracker

    # Setup strategies and mock calls
    mock_store.get_strategy_names.return_value = ["paper_strategy_1"]
    mock_tracker.compute_pnl = AsyncMock(return_value=(Decimal("100"), Decimal("50"), Decimal("150")))

    # Set up mock trades:
    # 1. Open leg with notes
    # 2. Open leg without notes (or empty notes)
    # 3. Closed leg with notes (should NOT be printed)
    trades = [
        PaperTrade(
            strategy_name="paper_strategy_1",
            leg_role="leg_open_with_notes",
            instrument_key="NSE_FO|NIFTY26500CE",
            trade_date=date(2026, 5, 26),
            action=TradeAction.SELL,
            quantity=65,
            price=Decimal("150.00"),
            notes="entered at high IVR",
        ),
        PaperTrade(
            strategy_name="paper_strategy_1",
            leg_role="leg_open_no_notes",
            instrument_key="NSE_FO|NIFTY26600CE",
            trade_date=date(2026, 5, 26),
            action=TradeAction.SELL,
            quantity=65,
            price=Decimal("120.00"),
            notes="",
        ),
        PaperTrade(
            strategy_name="paper_strategy_1",
            leg_role="leg_closed_with_notes",
            instrument_key="NSE_FO|NIFTY26700CE",
            trade_date=date(2026, 5, 26),
            action=TradeAction.SELL,
            quantity=65,
            price=Decimal("90.00"),
            notes="this leg is closed, do not print",
        ),
    ]
    mock_store.get_trades.return_value = trades

    # Mock get_position to return net_qty for each leg
    def mock_get_position(strategy_name: str, leg_role: str) -> PaperPosition:
        if leg_role == "leg_open_with_notes":
            return PaperPosition(
                strategy_name=strategy_name,
                leg_role=leg_role,
                net_qty=-65,
                avg_cost=Decimal("0"),
                avg_sell_price=Decimal("150.00"),
                instrument_key="NSE_FO|NIFTY26500CE",
            )
        elif leg_role == "leg_open_no_notes":
            return PaperPosition(
                strategy_name=strategy_name,
                leg_role=leg_role,
                net_qty=-65,
                avg_cost=Decimal("0"),
                avg_sell_price=Decimal("120.00"),
                instrument_key="NSE_FO|NIFTY26600CE",
            )
        else:
            return PaperPosition(
                strategy_name=strategy_name,
                leg_role=leg_role,
                net_qty=0,
                avg_cost=Decimal("90.00"),
                avg_sell_price=Decimal("90.00"),
                instrument_key="NSE_FO|NIFTY26700CE",
            )

    mock_store.get_position.side_effect = mock_get_position

    args = argparse.Namespace(
        strategy="paper_strategy_1",
        date=None,
        spot=25000.0,
        db_path="dummy.db",
        dry_run=True,
    )

    exit_code = await _run(args)
    assert exit_code == 0

    captured = capsys.readouterr()
    # Check that the open leg with notes appears in the printed notes
    assert "Notes: [leg_open_with_notes] entered at high IVR" in captured.out
    # Check that closed leg and no-notes leg are NOT in the printed notes
    assert "leg_closed_with_notes" not in captured.out
    assert "leg_open_no_notes" not in captured.out


@pytest.mark.asyncio
@patch("scripts.paper_snapshot.create_client")
@patch("scripts.paper_snapshot.PaperStore")
@patch("scripts.paper_snapshot.PaperTracker")
async def test_no_notes_printed_when_empty_or_null(
    mock_tracker_cls: MagicMock,
    mock_store_cls: MagicMock,
    mock_create_client: MagicMock,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Test that the Notes line does not appear at all if there are no notes."""
    mock_store = MagicMock()
    mock_store_cls.return_value = mock_store

    mock_tracker = MagicMock()
    mock_tracker_cls.return_value = mock_tracker

    mock_store.get_strategy_names.return_value = ["paper_strategy_1"]
    mock_tracker.compute_pnl = AsyncMock(return_value=(Decimal("100"), Decimal("50"), Decimal("150")))

    # Trades with only empty notes
    trades = [
        PaperTrade(
            strategy_name="paper_strategy_1",
            leg_role="leg_open_no_notes",
            instrument_key="NSE_FO|NIFTY26600CE",
            trade_date=date(2026, 5, 26),
            action=TradeAction.SELL,
            quantity=65,
            price=Decimal("120.00"),
            notes="",
        )
    ]
    mock_store.get_trades.return_value = trades

    mock_store.get_position.return_value = PaperPosition(
        strategy_name="paper_strategy_1",
        leg_role="leg_open_no_notes",
        net_qty=-65,
        avg_cost=Decimal("0"),
        avg_sell_price=Decimal("120.00"),
        instrument_key="NSE_FO|NIFTY26600CE",
    )

    args = argparse.Namespace(
        strategy="paper_strategy_1",
        date=None,
        spot=25000.0,
        db_path="dummy.db",
        dry_run=True,
    )

    exit_code = await _run(args)
    assert exit_code == 0

    captured = capsys.readouterr()
    # The output should NOT have any "Notes: " prefix
    assert "Notes: " not in captured.out

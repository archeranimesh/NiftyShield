"""Unit tests for scripts/paper_snapshot.py, specifically trade notes.

Tests the display of trade notes from open legs under the P&L table.
"""

from __future__ import annotations

import argparse
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from scripts.portfolio.paper_snapshot import _run
from src.models.portfolio import TradeAction
from src.paper.models import PaperPosition, PaperTrade


@pytest.mark.asyncio
@patch("scripts.portfolio.paper_snapshot.create_client")
@patch("scripts.portfolio.paper_snapshot.PaperStore")
@patch("scripts.portfolio.paper_snapshot.PaperTracker")
async def test_notes_printed_for_open_legs_with_notes(
    mock_tracker_cls: MagicMock,
    mock_store_cls: MagicMock,
    mock_create_client: MagicMock,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Test that notes are printed only for open legs that have non-empty notes, using bulk get_positions."""
    mock_store = MagicMock()
    mock_store_cls.return_value = mock_store

    mock_tracker = MagicMock()
    mock_tracker_cls.return_value = mock_tracker

    # Setup strategies and mock calls
    mock_store.get_strategy_names.return_value = ["paper_strategy_1"]
    mock_tracker.compute_pnl = AsyncMock(
        return_value=(Decimal("100"), Decimal("50"), Decimal("150"))
    )

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

    # Mock get_positions (Issue 2 bulk call)
    mock_store.get_positions.return_value = [
        PaperPosition(
            strategy_name="paper_strategy_1",
            leg_role="leg_open_with_notes",
            net_qty=-65,
            avg_cost=Decimal("0"),
            avg_sell_price=Decimal("150.00"),
            instrument_key="NSE_FO|NIFTY26500CE",
        ),
        PaperPosition(
            strategy_name="paper_strategy_1",
            leg_role="leg_open_no_notes",
            net_qty=-65,
            avg_cost=Decimal("0"),
            avg_sell_price=Decimal("120.00"),
            instrument_key="NSE_FO|NIFTY26600CE",
        ),
        PaperPosition(
            strategy_name="paper_strategy_1",
            leg_role="leg_closed_with_notes",
            net_qty=0,
            avg_cost=Decimal("90.00"),
            avg_sell_price=Decimal("90.00"),
            instrument_key="NSE_FO|NIFTY26700CE",
        ),
    ]

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
@patch("scripts.portfolio.paper_snapshot.create_client")
@patch("scripts.portfolio.paper_snapshot.PaperStore")
@patch("scripts.portfolio.paper_snapshot.PaperTracker")
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
    mock_tracker.compute_pnl = AsyncMock(
        return_value=(Decimal("100"), Decimal("50"), Decimal("150"))
    )

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

    mock_store.get_positions.return_value = [
        PaperPosition(
            strategy_name="paper_strategy_1",
            leg_role="leg_open_no_notes",
            net_qty=-65,
            avg_cost=Decimal("0"),
            avg_sell_price=Decimal("120.00"),
            instrument_key="NSE_FO|NIFTY26600CE",
        )
    ]

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


@pytest.mark.asyncio
@patch("scripts.portfolio.paper_snapshot.create_client")
@patch("scripts.portfolio.paper_snapshot.PaperStore")
@patch("scripts.portfolio.paper_snapshot.PaperTracker")
async def test_most_recent_note_only_for_multiple_trades_per_leg(
    mock_tracker_cls: MagicMock,
    mock_store_cls: MagicMock,
    mock_create_client: MagicMock,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Test that if a leg has multiple trades (e.g. roll/entry), only the most recent note is printed (Issue 1)."""
    mock_store = MagicMock()
    mock_store_cls.return_value = mock_store

    mock_tracker = MagicMock()
    mock_tracker_cls.return_value = mock_tracker

    mock_store.get_strategy_names.return_value = ["paper_strategy_1"]
    mock_tracker.compute_pnl = AsyncMock(
        return_value=(Decimal("100"), Decimal("50"), Decimal("150"))
    )

    # Two trades on the same open leg:
    # 1. First trade (older): notes = "initial entry note"
    # 2. Second trade (newer): notes = "roll adjustment note"
    trades = [
        PaperTrade(
            strategy_name="paper_strategy_1",
            leg_role="leg_open_multi_trade",
            instrument_key="NSE_FO|NIFTY26500CE",
            trade_date=date(2026, 5, 20),
            action=TradeAction.BUY,
            quantity=65,
            price=Decimal("140.00"),
            notes="initial entry note",
        ),
        PaperTrade(
            strategy_name="paper_strategy_1",
            leg_role="leg_open_multi_trade",
            instrument_key="NSE_FO|NIFTY26500CE",
            trade_date=date(2026, 5, 26),
            action=TradeAction.SELL,
            quantity=65,
            price=Decimal("150.00"),
            notes="roll adjustment note",
        ),
    ]
    mock_store.get_trades.return_value = trades

    mock_store.get_positions.return_value = [
        PaperPosition(
            strategy_name="paper_strategy_1",
            leg_role="leg_open_multi_trade",
            net_qty=65,  # net qty is open
            avg_cost=Decimal("140.00"),
            avg_sell_price=Decimal("150.00"),
            instrument_key="NSE_FO|NIFTY26500CE",
        )
    ]

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
    # Check that ONLY the most recent note ("roll adjustment note") is printed
    assert "Notes: [leg_open_multi_trade] roll adjustment note" in captured.out
    assert "initial entry note" not in captured.out


@pytest.mark.asyncio
@patch("scripts.portfolio.paper_snapshot.create_client")
@patch("scripts.portfolio.paper_snapshot.PaperStore")
@patch("scripts.portfolio.paper_snapshot.PaperTracker")
async def test_all_strategies_snapshot_when_none_fail(
    mock_tracker_cls: MagicMock,
    mock_store_cls: MagicMock,
    mock_create_client: MagicMock,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Happy path: multiple strategies in one no-flag run all get snapshotted, exit code 0."""
    mock_store = MagicMock()
    mock_store_cls.return_value = mock_store

    mock_tracker = MagicMock()
    mock_tracker_cls.return_value = mock_tracker

    mock_store.get_strategy_names.return_value = ["paper_strategy_a", "paper_strategy_b"]
    mock_tracker.compute_pnl = AsyncMock(
        side_effect=[
            (Decimal("10"), Decimal("5"), Decimal("15")),
            (Decimal("20"), Decimal("0"), Decimal("20")),
        ]
    )
    mock_store.get_trades.return_value = []
    mock_store.get_positions.return_value = []

    args = argparse.Namespace(
        strategy=None,
        date=None,
        spot=None,
        db_path="dummy.db",
        dry_run=True,
    )

    exit_code = await _run(args)
    assert exit_code == 0

    captured = capsys.readouterr()
    assert "paper_strategy_a" in captured.out
    assert "paper_strategy_b" in captured.out
    assert "FAILED" not in captured.out


@pytest.mark.asyncio
@patch("scripts.portfolio.paper_snapshot.create_client")
@patch("scripts.portfolio.paper_snapshot.PaperStore")
@patch("scripts.portfolio.paper_snapshot.PaperTracker")
async def test_one_strategy_failure_does_not_block_others(
    mock_tracker_cls: MagicMock,
    mock_store_cls: MagicMock,
    mock_create_client: MagicMock,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """One strategy's compute_pnl raising (e.g. a broker LTP fetch error) must not
    prevent strategies that sort after it alphabetically from being snapshotted.
    Regression guard for the failure mode described in docs/bugs/bugs.md
    BUG-016/017/018: an unhandled per-leg fetch failure previously would have
    aborted the whole batch run silently.
    """
    mock_store = MagicMock()
    mock_store_cls.return_value = mock_store

    mock_tracker = MagicMock()
    mock_tracker_cls.return_value = mock_tracker

    mock_store.get_strategy_names.return_value = [
        "paper_strategy_a_broken",
        "paper_strategy_b_ok",
    ]

    async def _compute_pnl(name: str):
        if name == "paper_strategy_a_broken":
            raise ConnectionError("simulated LTP fetch failure")
        return (Decimal("20"), Decimal("0"), Decimal("20"))

    mock_tracker.compute_pnl = AsyncMock(side_effect=_compute_pnl)
    mock_store.get_trades.return_value = []
    mock_store.get_positions.return_value = []

    args = argparse.Namespace(
        strategy=None,
        date=None,
        spot=None,
        db_path="dummy.db",
        dry_run=True,
    )

    exit_code = await _run(args)

    # Batch must report failure (non-zero) but must NOT have aborted early —
    # the second, unaffected strategy still needs to appear in the output.
    assert exit_code == 1

    captured = capsys.readouterr()
    assert "paper_strategy_b_ok" in captured.out
    assert "paper_strategy_a_broken" in captured.err
    assert "FAILED" in captured.err

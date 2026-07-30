"""Tests for OPS-1: insert/skip logging in paper_3track_overlay_entry.main()."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from src.models.portfolio import TradeAction
from src.paper.models import PaperTrade


def _make_trade(strategy: str = "paper_nifty_spot", leg: str = "overlay_cc") -> PaperTrade:
    return PaperTrade(
        strategy_name=strategy,
        leg_role=leg,
        instrument_key="NSE_FO|12345",
        trade_date=date(2026, 6, 15),
        action=TradeAction.SELL,
        quantity=65,
        price=Decimal("50.00"),
    )


@dataclass
class _FakeOverlayTrade:
    trade: PaperTrade
    strategy: str


def _run_main_with_mock_store(record_trade_return: bool) -> list[tuple]:
    """Run main() with a fully mocked store and return captured log calls."""
    trade = _make_trade()
    overlay_trade = _FakeOverlayTrade(trade=trade, strategy="paper_nifty_spot")

    log_calls: list[tuple] = []

    def fake_log_info(event: str, **kwargs: object) -> None:
        log_calls.append((event, kwargs))

    mock_store = MagicMock()
    mock_store.record_trade.return_value = record_trade_return
    mock_store.get_positions.return_value = []  # no existing overlay leg → bootstrap fires

    mock_logger = MagicMock()
    mock_logger.info.side_effect = fake_log_info

    mock_cfg = MagicMock()
    mock_cfg.overlay_type = "cc"
    mock_cfg.call_instrument_key = None  # skips the open-call dedup query

    with (
        patch(
            "scripts.strategies.three_track.paper_3track_overlay_entry.load_overlay_config",
            return_value=mock_cfg,
        ),
        patch(
            "scripts.strategies.three_track.paper_3track_overlay_entry.build_overlay_trades",
            return_value=([overlay_trade], []),
        ),
        patch("scripts.strategies.three_track.paper_3track_overlay_entry.print_summary"),
        patch(
            "scripts.strategies.three_track.paper_3track_overlay_entry.PaperStore",
            return_value=mock_store,
        ),
        patch("scripts.strategies.three_track.paper_3track_overlay_entry.setup_logging"),
        patch(
            "scripts.strategies.three_track.paper_3track_overlay_entry.logger",
            mock_logger,
        ),
        patch(
            "scripts.strategies.three_track.paper_3track_overlay_entry.build_notifier",
            return_value=None,
        ),
        patch("sys.argv", ["paper_3track_overlay_entry.py"]),
    ):
        from scripts.strategies.three_track import paper_3track_overlay_entry

        paper_3track_overlay_entry.main()

    return log_calls


class TestOps1InsertSkipLogging:
    """OPS-1: record_trade return value must be logged at INFO."""

    def test_inserted_logs_trade_inserted(self) -> None:
        log_calls = _run_main_with_mock_store(record_trade_return=True)
        assert len(log_calls) == 1
        event, kwargs = log_calls[0]
        assert "INSERTED" in event
        assert kwargs["strategy"] == "paper_nifty_spot"
        assert kwargs["leg"] == "overlay_cc"

    def test_skipped_logs_trade_skipped(self) -> None:
        log_calls = _run_main_with_mock_store(record_trade_return=False)
        assert len(log_calls) == 1
        event, kwargs = log_calls[0]
        assert "SKIPPED" in event
        assert kwargs["strategy"] == "paper_nifty_spot"
        assert kwargs["leg"] == "overlay_cc"
        assert "conflict" in kwargs.get("reason", "")

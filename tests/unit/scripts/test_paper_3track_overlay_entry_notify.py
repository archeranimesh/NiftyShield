"""S6 — one-time bootstrap entry trigger + Telegram notify for
paper_3track_overlay_entry.py.

See docs/plan/3track-consolidation/stories.md S6 for the confirmed decision log
(bootstrap-only per overlay leg, never a recurring re-entry).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from scripts.strategies.three_track import paper_3track_overlay_entry as ov_entry
from src.models.portfolio import TradeAction
from src.paper.constants import STRATEGY_OVERLAY
from src.paper.models import PaperTrade


def _make_trade(leg: str = "overlay_cc") -> PaperTrade:
    return PaperTrade(
        strategy_name=STRATEGY_OVERLAY,
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
    leg_role: str


def _run_main(mock_store: MagicMock, mock_notifier, overlay_trade) -> None:
    mock_cfg = MagicMock()
    mock_cfg.overlay_type = "cc"
    mock_cfg.call_instrument_key = None

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
            "scripts.strategies.three_track.paper_3track_overlay_entry.build_notifier",
            return_value=mock_notifier,
        ),
        patch("sys.argv", ["paper_3track_overlay_entry.py"]),
    ):
        ov_entry.main()


def test_overlay_entry_trigger_fires_when_no_open_leg() -> None:
    trade = _make_trade()
    overlay_trade = _FakeOverlayTrade(trade=trade, strategy=STRATEGY_OVERLAY, leg_role="overlay_cc")
    mock_store = MagicMock()
    mock_store.get_positions.return_value = []  # overlay_cc not yet open
    mock_store.record_trade.return_value = True

    _run_main(mock_store, mock_notifier=None, overlay_trade=overlay_trade)

    mock_store.record_trade.assert_called_once()


def test_overlay_entry_does_not_refire_once_leg_open() -> None:
    trade = _make_trade()
    overlay_trade = _FakeOverlayTrade(trade=trade, strategy=STRATEGY_OVERLAY, leg_role="overlay_cc")
    existing_position = MagicMock()
    existing_position.leg_role = "overlay_cc"  # matches the primary marker for "cc"

    mock_store = MagicMock()
    mock_store.get_positions.return_value = [existing_position]

    _run_main(mock_store, mock_notifier=None, overlay_trade=overlay_trade)

    mock_store.record_trade.assert_not_called()


def test_overlay_entry_notifies_telegram_on_success() -> None:
    trade = _make_trade()
    overlay_trade = _FakeOverlayTrade(trade=trade, strategy=STRATEGY_OVERLAY, leg_role="overlay_cc")
    mock_store = MagicMock()
    mock_store.get_positions.return_value = []
    mock_store.record_trade.return_value = True
    mock_notifier = MagicMock()
    mock_notifier.send = AsyncMock(return_value=True)

    _run_main(mock_store, mock_notifier=mock_notifier, overlay_trade=overlay_trade)

    mock_notifier.send.assert_awaited_once()
    msg = mock_notifier.send.await_args[0][0]
    assert "OVERLAY ENTRY" in msg
    assert "*" not in msg


def test_overlay_entry_notification_failure_does_not_block_trade() -> None:
    trade = _make_trade()
    overlay_trade = _FakeOverlayTrade(trade=trade, strategy=STRATEGY_OVERLAY, leg_role="overlay_cc")
    mock_store = MagicMock()
    mock_store.get_positions.return_value = []
    mock_store.record_trade.return_value = True
    mock_notifier = MagicMock()
    mock_notifier.send = AsyncMock(side_effect=RuntimeError("network down"))

    _run_main(mock_store, mock_notifier=mock_notifier, overlay_trade=overlay_trade)  # no raise

    mock_store.record_trade.assert_called_once()

"""S6 — one-time bootstrap entry trigger + Telegram notify for
paper_3track_overlay_entry.py.

See docs/plan/3track-consolidation/stories.md S6 for the confirmed decision log
(bootstrap-only per overlay leg, never a recurring re-entry). OEM-4
(docs/plan/telegram-message-unification/overlay-entry-message/) migrated the
notify card from a hand-rolled f-string to the shared ``format_entry_message``
renderer.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from scripts.strategies.three_track import paper_3track_overlay_entry as ov_entry
from src.models.portfolio import TradeAction
from src.paper.constants import STRATEGY_OVERLAY, STRATEGY_SPOT
from src.paper.models import GateViolation, PaperTrade

_SPOT = Decimal("24000.00")


def _make_trade(leg: str = "overlay_cc", price: Decimal = Decimal("50.00")) -> PaperTrade:
    return PaperTrade(
        strategy_name=STRATEGY_OVERLAY,
        leg_role=leg,
        instrument_key="NSE_FO|12345",
        trade_date=date(2026, 6, 15),
        action=TradeAction.SELL,
        quantity=65,
        price=price,
    )


@dataclass
class _FakeOverlayTrade:
    trade: PaperTrade
    strategy: str
    leg_role: str


def _make_cfg(
    overlay_type: str = "cc",
    *,
    put_strike: float = 23500,
    call_strike: float = 24800,
) -> MagicMock:
    cfg = MagicMock()
    cfg.overlay_type = overlay_type
    cfg.call_instrument_key = None
    cfg.expiry = "2026-09-29"
    cfg.expiry_type = "monthly"
    cfg.dte_at_entry = 21
    cfg.lot_size = 65
    cfg.put_strike = put_strike
    cfg.call_strike = call_strike
    return cfg


def _run_main(
    mock_store: MagicMock,
    mock_notifier: MagicMock,
    overlay_trade: _FakeOverlayTrade | list[_FakeOverlayTrade],
    mock_cfg: MagicMock | None = None,
) -> None:
    if not isinstance(overlay_trade, list):
        overlay_trades = [overlay_trade]
    else:
        overlay_trades = overlay_trade

    if mock_cfg is None:
        mock_cfg = _make_cfg()

    with (
        patch(
            "scripts.strategies.three_track.paper_3track_overlay_entry.load_overlay_config",
            return_value=mock_cfg,
        ),
        patch(
            "scripts.strategies.three_track.paper_3track_overlay_entry.build_overlay_trades",
            return_value=(overlay_trades, []),
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
        patch(
            "scripts.strategies.three_track.paper_3track_overlay_entry._fetch_nifty_spot",
            return_value=_SPOT,
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

    def _get_positions(strategy_name: str) -> list[MagicMock]:
        # SPOT-track idempotency guard (eba1806) must see no overlay_cc position —
        # only the OVERLAY-track bootstrap guard this test exercises should fire.
        if strategy_name == STRATEGY_SPOT:
            return []
        return [existing_position]

    mock_store.get_positions.side_effect = _get_positions

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
    assert "✅ *CC Entry*" in msg


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


def test_overlay_entry_pp_bootstrap() -> None:
    trade = _make_trade("overlay_pp", price=Decimal("142.10"))
    overlay_trade = _FakeOverlayTrade(trade=trade, strategy=STRATEGY_OVERLAY, leg_role="overlay_pp")
    mock_store = MagicMock()
    mock_store.get_positions.return_value = []
    mock_store.record_trade.return_value = True
    mock_notifier = MagicMock()
    mock_notifier.send = AsyncMock(return_value=True)

    mock_cfg = _make_cfg("pp", put_strike=23500)

    with patch("sys.argv", ["paper_3track_overlay_entry.py"]):
        _run_main(
            mock_store, mock_notifier=mock_notifier, overlay_trade=overlay_trade, mock_cfg=mock_cfg
        )

    mock_notifier.send.assert_awaited_once()
    msg = mock_notifier.send.await_args[0][0]
    assert "✅ *PP Entry*" in msg
    assert "[B]" in msg
    assert "23500" in msg
    assert "💰 *Net debit:*" in msg


def test_overlay_entry_cc_bootstrap() -> None:
    trade = _make_trade("overlay_cc", price=Decimal("185.20"))
    overlay_trade = _FakeOverlayTrade(trade=trade, strategy=STRATEGY_OVERLAY, leg_role="overlay_cc")
    mock_store = MagicMock()
    mock_store.get_positions.return_value = []
    mock_store.record_trade.return_value = True
    mock_notifier = MagicMock()
    mock_notifier.send = AsyncMock(return_value=True)

    mock_cfg = _make_cfg("cc", call_strike=24800)

    with patch("sys.argv", ["paper_3track_overlay_entry.py"]):
        _run_main(
            mock_store, mock_notifier=mock_notifier, overlay_trade=overlay_trade, mock_cfg=mock_cfg
        )

    mock_notifier.send.assert_awaited_once()
    msg = mock_notifier.send.await_args[0][0]
    assert "✅ *CC Entry*" in msg
    assert "[S]" in msg
    assert "24800" in msg
    assert "💰 *Net credit:*" in msg


def test_overlay_entry_collar_bootstrap() -> None:
    trade1 = _make_trade("overlay_collar_put", price=Decimal("142.10"))
    ot1 = _FakeOverlayTrade(trade=trade1, strategy=STRATEGY_OVERLAY, leg_role="overlay_collar_put")

    trade2 = _make_trade("overlay_collar_call", price=Decimal("185.20"))
    ot2 = _FakeOverlayTrade(trade=trade2, strategy=STRATEGY_OVERLAY, leg_role="overlay_collar_call")

    mock_store = MagicMock()
    mock_store.get_positions.return_value = []
    mock_store.record_trade.return_value = True
    mock_store.record_trades.return_value = ([trade1, trade2], [])
    mock_notifier = MagicMock()
    mock_notifier.send = AsyncMock(return_value=True)

    mock_cfg = _make_cfg("collar", put_strike=23500, call_strike=24800)

    with patch("sys.argv", ["paper_3track_overlay_entry.py"]):
        _run_main(
            mock_store, mock_notifier=mock_notifier, overlay_trade=[ot1, ot2], mock_cfg=mock_cfg
        )

    mock_notifier.send.assert_awaited_once()
    msg = mock_notifier.send.await_args[0][0]
    assert "✅ *COLLAR Entry*" in msg
    assert "[B]" in msg
    assert "[S]" in msg
    # put 142.10 debit, call 185.20 credit -> net credit of 43.10
    assert "💰 *Net credit:*" in msg


def test_overlay_entry_collar_shows_both_directions() -> None:
    # Covered by test_overlay_entry_collar_bootstrap where one leg is [B] and one [S].
    trade1 = _make_trade("overlay_collar_put")
    trade2 = _make_trade("overlay_collar_call")
    ot1 = _FakeOverlayTrade(trade=trade1, strategy=STRATEGY_OVERLAY, leg_role="overlay_collar_put")
    ot2 = _FakeOverlayTrade(trade=trade2, strategy=STRATEGY_OVERLAY, leg_role="overlay_collar_call")

    mock_store = MagicMock()
    mock_store.get_positions.return_value = []
    mock_store.record_trade.return_value = True
    mock_store.record_trades.return_value = ([trade1, trade2], [])
    mock_notifier = MagicMock()
    mock_notifier.send = AsyncMock(return_value=True)

    mock_cfg = _make_cfg("collar", put_strike=23500, call_strike=24800)

    with patch("sys.argv", ["paper_3track_overlay_entry.py"]):
        _run_main(
            mock_store, mock_notifier=mock_notifier, overlay_trade=[ot1, ot2], mock_cfg=mock_cfg
        )

    msg = mock_notifier.send.await_args[0][0]
    assert "[B]" in msg
    assert "[S]" in msg


def test_overlay_entry_cc_bootstrap_gate_logged() -> None:
    trade = _make_trade("overlay_cc", price=Decimal("185.20"))
    overlay_trade = _FakeOverlayTrade(trade=trade, strategy=STRATEGY_OVERLAY, leg_role="overlay_cc")
    mock_store = MagicMock()
    mock_store.get_positions.return_value = []
    mock_store.record_trade.return_value = True
    mock_notifier = MagicMock()
    mock_notifier.send = AsyncMock(return_value=True)

    mock_cfg = _make_cfg("cc", call_strike=24800)

    gate_violation = GateViolation(
        gate_name="ivr_cc_reentry",
        threshold="0.25",
        actual="0.19",
        strategy_name="test",
        logged_at=datetime.now(),
    )

    with (
        patch("sys.argv", ["paper_3track_overlay_entry.py", "--auto-cc"]),
        patch(
            "scripts.strategies.three_track.paper_3track_overlay_entry.auto_cc_bootstrap",
            return_value=(mock_cfg, gate_violation),
        ),
        patch(
            "scripts.strategies.three_track.paper_3track_overlay_entry.build_overlay_trades",
            return_value=([overlay_trade], []),
        ),
        patch("scripts.strategies.three_track.paper_3track_overlay_entry.setup_logging"),
        patch(
            "scripts.strategies.three_track.paper_3track_overlay_entry.build_notifier",
            return_value=mock_notifier,
        ),
        patch(
            "scripts.strategies.three_track.paper_3track_overlay_entry._fetch_nifty_spot",
            return_value=_SPOT,
        ),
        patch("scripts.strategies.three_track.paper_3track_overlay_entry.print_summary"),
        patch(
            "scripts.strategies.three_track.paper_3track_overlay_entry.PaperStore",
            return_value=mock_store,
        ),
    ):
        ov_entry.main()

    mock_notifier.send.assert_awaited_once()
    msg = mock_notifier.send.await_args[0][0]
    assert "✅ *CC Entry*" in msg
    expected_gate_line = (
        "⚠️ Gate Logged: ivr\\_cc\\_reentry \\(threshold\\=0\\.25, actual\\=0\\.19\\)"
    )
    assert msg.endswith(expected_gate_line)


def test_overlay_entry_gate_violation_line_omitted_when_none() -> None:
    trade = _make_trade("overlay_cc", price=Decimal("185.20"))
    overlay_trade = _FakeOverlayTrade(trade=trade, strategy=STRATEGY_OVERLAY, leg_role="overlay_cc")
    mock_store = MagicMock()
    mock_store.get_positions.return_value = []
    mock_store.record_trade.return_value = True
    mock_notifier = MagicMock()
    mock_notifier.send = AsyncMock(return_value=True)

    mock_cfg = _make_cfg("cc", call_strike=24800)

    with patch(
        "scripts.strategies.three_track.paper_3track_overlay_entry.load_overlay_config"
    ) as mock_load:
        mock_load.return_value = mock_cfg

        with patch("sys.argv", ["paper_3track_overlay_entry.py"]):
            _run_main(
                mock_store,
                mock_notifier=mock_notifier,
                overlay_trade=overlay_trade,
                mock_cfg=mock_cfg,
            )

    mock_notifier.send.assert_awaited_once()
    msg = mock_notifier.send.await_args[0][0]
    assert "Gate Logged" not in msg


def test_overlay_entry_unmapped_leg_role_raises() -> None:
    trade = _make_trade("unmapped_role")
    overlay_trade = _FakeOverlayTrade(
        trade=trade, strategy=STRATEGY_OVERLAY, leg_role="unmapped_role"
    )
    mock_store = MagicMock()
    mock_store.get_positions.return_value = []
    mock_store.record_trade.return_value = True
    mock_notifier = MagicMock()

    mock_cfg = _make_cfg("cc", call_strike=24800)

    with patch(
        "scripts.strategies.three_track.paper_3track_overlay_entry.load_overlay_config"
    ) as mock_load:
        mock_load.return_value = mock_cfg

        with patch("sys.argv", ["paper_3track_overlay_entry.py"]):
            with pytest.raises(
                ValueError, match="no display label mapped for leg_role='unmapped_role'"
            ):
                _run_main(
                    mock_store,
                    mock_notifier=mock_notifier,
                    overlay_trade=overlay_trade,
                    mock_cfg=mock_cfg,
                )


def test_overlay_entry_spot_unavailable_skips_card() -> None:
    """When live spot cannot be fetched, the card is skipped (logged) rather than
    sent with a bad value or crashing the trade."""
    trade = _make_trade("overlay_cc", price=Decimal("185.20"))
    overlay_trade = _FakeOverlayTrade(trade=trade, strategy=STRATEGY_OVERLAY, leg_role="overlay_cc")
    mock_store = MagicMock()
    mock_store.get_positions.return_value = []
    mock_store.record_trade.return_value = True
    mock_notifier = MagicMock()
    mock_notifier.send = AsyncMock(return_value=True)

    mock_cfg = _make_cfg("cc", call_strike=24800)

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
        patch(
            "scripts.strategies.three_track.paper_3track_overlay_entry._fetch_nifty_spot",
            return_value=None,
        ),
        patch("sys.argv", ["paper_3track_overlay_entry.py"]),
    ):
        ov_entry.main()

    mock_notifier.send.assert_not_awaited()
    mock_store.record_trade.assert_called_once()


def test_overlay_entry_all_reserved_chars_escaped() -> None:
    # Test that reserved chars like '-', '.', '_' in the gate line are escaped.
    trade = _make_trade("overlay_cc", price=Decimal("185.20"))
    overlay_trade = _FakeOverlayTrade(trade=trade, strategy=STRATEGY_OVERLAY, leg_role="overlay_cc")
    mock_store = MagicMock()
    mock_store.get_positions.return_value = []
    mock_store.record_trade.return_value = True
    mock_notifier = MagicMock()
    mock_notifier.send = AsyncMock(return_value=True)

    mock_cfg = _make_cfg("cc", call_strike=24800)

    gate_violation = GateViolation(
        gate_name="my_gate-with_chars",
        threshold="-1.5",
        actual="-2.0",
        strategy_name="test",
        logged_at=datetime.now(),
    )

    with (
        patch("sys.argv", ["paper_3track_overlay_entry.py", "--auto-cc"]),
        patch(
            "scripts.strategies.three_track.paper_3track_overlay_entry.auto_cc_bootstrap",
            return_value=(mock_cfg, gate_violation),
        ),
        patch(
            "scripts.strategies.three_track.paper_3track_overlay_entry.build_overlay_trades",
            return_value=([overlay_trade], []),
        ),
        patch("scripts.strategies.three_track.paper_3track_overlay_entry.setup_logging"),
        patch(
            "scripts.strategies.three_track.paper_3track_overlay_entry.build_notifier",
            return_value=mock_notifier,
        ),
        patch(
            "scripts.strategies.three_track.paper_3track_overlay_entry._fetch_nifty_spot",
            return_value=_SPOT,
        ),
        patch("scripts.strategies.three_track.paper_3track_overlay_entry.print_summary"),
        patch(
            "scripts.strategies.three_track.paper_3track_overlay_entry.PaperStore",
            return_value=mock_store,
        ),
    ):
        ov_entry.main()

    msg = mock_notifier.send.await_args[0][0]
    # Check escaped minus and underscore in gate
    assert "my\\_gate\\-with\\_chars" in msg
    # Check threshold escaped minus and dot
    assert "threshold\\=\\-1\\.5" in msg
    assert "actual\\=\\-2\\.0" in msg

"""UEM-2 / UXM-4 — entry + exit Telegram cards behind ``record_paper_trade.py --notify``.

Covers: entry card sent on a successful CSP/CC open, exit card sent on a successful
``--close``, send failure is non-fatal, and no notifier work happens without --notify.
"""

from __future__ import annotations

import argparse
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import scripts.record.record_paper_trade as rpt
from src.models.portfolio import TradeAction
from src.paper.constants import STRATEGY_CC_OVERLAY, STRATEGY_CSP
from src.paper.models import PaperTrade
from src.paper.store import PaperStore


def _csp_trade() -> PaperTrade:
    return PaperTrade(
        strategy_name=STRATEGY_CSP,
        leg_role="short_put",
        instrument_key="NIFTY29MAY2026PE23000",
        trade_date=date(2026, 5, 1),
        action=TradeAction.SELL,
        quantity=75,
        price=Decimal("120.50"),
    )


def _cc_trade() -> PaperTrade:
    return PaperTrade(
        strategy_name=STRATEGY_CC_OVERLAY,
        leg_role="short_call",
        instrument_key="NIFTY29MAY2026CE25000",
        trade_date=date(2026, 5, 1),
        action=TradeAction.SELL,
        quantity=75,
        price=Decimal("80.00"),
    )


def _args(notify: bool = True, close: bool = False) -> argparse.Namespace:
    return argparse.Namespace(notify=notify, close=close)


def _patch_spot(monkeypatch, spot: Decimal = Decimal("22500.0")) -> None:
    fake_client = MagicMock()
    fake_client.get_ltp_sync.return_value = {"NSE_INDEX|Nifty 50": spot}
    monkeypatch.setattr(rpt, "UpstoxMarketClient", lambda: fake_client)


def test_notify_flag_sends_csp_entry_card_on_open(monkeypatch):
    _patch_spot(monkeypatch)
    fake_notifier = MagicMock()
    fake_notifier.send = AsyncMock(return_value=True)
    monkeypatch.setattr(rpt, "build_notifier", lambda: fake_notifier)

    rpt._send_entry_card_if_requested(_csp_trade(), _args())

    fake_notifier.send.assert_awaited_once()
    body = fake_notifier.send.call_args[0][0]
    assert "CSP Entry" in body
    assert "[S]" in body


def test_notify_flag_sends_cc_entry_card_on_open(monkeypatch):
    _patch_spot(monkeypatch)
    fake_notifier = MagicMock()
    fake_notifier.send = AsyncMock(return_value=True)
    monkeypatch.setattr(rpt, "build_notifier", lambda: fake_notifier)

    rpt._send_entry_card_if_requested(_cc_trade(), _args())

    fake_notifier.send.assert_awaited_once()
    body = fake_notifier.send.call_args[0][0]
    assert "CC Entry" in body
    assert "[S]" in body
    assert "CE" in body


def test_notify_send_failure_is_non_fatal(monkeypatch):
    _patch_spot(monkeypatch)
    fake_notifier = MagicMock()
    fake_notifier.send = AsyncMock(side_effect=RuntimeError("boom"))
    monkeypatch.setattr(rpt, "build_notifier", lambda: fake_notifier)

    # Must not raise.
    rpt._send_entry_card_if_requested(_csp_trade(), _args())


def test_no_notify_flag_sends_nothing(monkeypatch):
    with patch.object(rpt, "build_notifier") as mock_build_notifier:
        rpt._send_entry_card_if_requested(_csp_trade(), _args(notify=False))
        mock_build_notifier.assert_not_called()


# ── UXM-4 — exit card on --close ────────────────────────────────────────────


def _closed_csp_store(tmp_path: Path) -> tuple[PaperStore, PaperTrade]:
    """A PaperStore with a fully closed CSP cycle: SELL then BUY-to-close."""
    store = PaperStore(tmp_path / "close.sqlite")
    store.record_trade(_csp_trade())
    close_trade = PaperTrade(
        strategy_name=STRATEGY_CSP,
        leg_role="short_put",
        instrument_key="NIFTY29MAY2026PE23000",
        trade_date=date(2026, 5, 1) + timedelta(days=5),
        action=TradeAction.BUY,
        quantity=75,
        price=Decimal("20.00"),
    )
    store.record_trade(close_trade)
    return store, close_trade


def test_record_close_notify_sends_exit_card(tmp_path: Path) -> None:
    store, close_trade = _closed_csp_store(tmp_path)
    fake_notifier = MagicMock()
    fake_notifier.send = AsyncMock(return_value=True)
    with patch.object(rpt, "build_notifier", lambda: fake_notifier):
        rpt._send_close_card_if_requested(close_trade, store, _args(notify=True, close=True))

    fake_notifier.send.assert_awaited_once()
    body = fake_notifier.send.call_args[0][0]
    assert "CSP V1" in body
    assert "📈" in body


def test_record_close_no_notify_silent(tmp_path: Path) -> None:
    store, close_trade = _closed_csp_store(tmp_path)
    with patch.object(rpt, "build_notifier") as mock_build_notifier:
        rpt._send_close_card_if_requested(close_trade, store, _args(notify=False, close=True))
        mock_build_notifier.assert_not_called()


def test_record_open_notify_does_not_send_close_card(tmp_path: Path) -> None:
    store, close_trade = _closed_csp_store(tmp_path)
    with patch.object(rpt, "build_notifier") as mock_build_notifier:
        rpt._send_close_card_if_requested(close_trade, store, _args(notify=True, close=False))
        mock_build_notifier.assert_not_called()

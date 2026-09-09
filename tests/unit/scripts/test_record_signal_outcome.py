"""No-network render tests for the S5.5a outcome Telegram message."""

from __future__ import annotations

import sys
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from scripts import record_signal_outcome
from src.paper.constants import LOT_SIZE
from src.signals.models import (
    DailySignal,
    Direction,
    SignalOutcome,
    SignalResponse,
    TradeAction,
)

_FMT = record_signal_outcome._format_outcome_notification


def _resp(provider: str, direction: Direction) -> SignalResponse:
    return SignalResponse(
        trade_date=date(2026, 9, 8),
        provider=provider,
        direction=direction,
        confidence=4,
        recommended_strike=24800,
        entry_premium_low=Decimal("58.00"),
        entry_premium_high=Decimal("72.00"),
        key_reason="GIFT Nifty supportive.",
        key_risk="US CPI tonight.",
        raw_response="{}",
    )


_SIGNAL_BUY = DailySignal(
    trade_date=date(2026, 9, 8),
    responses=[_resp("grok", Direction.BULLISH), _resp("gpt4o", Direction.BULLISH)],
    consensus_direction=Direction.BULLISH,
    consensus_confidence=Decimal("3.5"),
    trade_action=TradeAction.BUY_CALL,
    recommended_strike=24800,
    agreeing_models=["grok", "gpt4o"],
    dissenting_models=["gemini"],
)
_SIGNAL_NOTRADE = DailySignal(
    trade_date=date(2026, 9, 8),
    responses=[],
    consensus_direction=Direction.NEUTRAL,
    consensus_confidence=Decimal("0"),
    trade_action=TradeAction.NO_TRADE,
    recommended_strike=None,
    agreeing_models=[],
    dissenting_models=[],
)

_OUT_EXEC = SignalOutcome(
    trade_date=date(2026, 9, 8),
    trade_action=TradeAction.BUY_CALL,
    recommended_strike=24800,
    entry_premium=Decimal("65.50"),
    exit_premium=Decimal("92.00"),
    pnl_per_lot=(Decimal("92.00") - Decimal("65.50")) * LOT_SIZE,
    nifty_close=Decimal("24842.10"),
    executed=True,
)


def test_executed_outcome_renders_realised_pnl() -> None:
    msg = _FMT(_OUT_EXEC, _SIGNAL_BUY)

    assert msg.startswith("*📊 SIGNAL OUTCOME · 08 Sep*\n\n")
    assert "📈 BULLISH · BUY CALL 24800" in msg
    assert "💰 Entry ₹65\\.50 → Exit ₹92\\.00" in msg
    assert "(would-be)" not in msg
    assert "✅ P&L: \\+₹1,722\\.50 / lot" in msg
    assert "🏁 Nifty close: 24,842" in msg
    assert "🔧 Phase: openrouter\\_only" in msg


def test_not_taken_outcome_derives_would_be_pnl_in_formatter() -> None:
    out_skip = _OUT_EXEC.model_copy(update={"executed": False, "pnl_per_lot": None})
    msg = _FMT(out_skip, _SIGNAL_BUY)

    assert msg.startswith("*📊 SIGNAL OUTCOME · 08 Sep · NOT TAKEN*\n\n")
    assert "💰 Entry ₹65\\.50 → Exit ₹92\\.00 \\(would\\-be\\)" in msg
    assert "✅ Paper P&L: \\+₹1,722\\.50 / lot" in msg


def test_no_trade_outcome_renders_close_only_line() -> None:
    out = SignalOutcome(
        trade_date=date(2026, 9, 8),
        trade_action=TradeAction.NO_TRADE,
        recommended_strike=None,
        entry_premium=None,
        exit_premium=None,
        pnl_per_lot=None,
        nifty_close=Decimal("24842.10"),
        executed=False,
    )
    msg = _FMT(out, _SIGNAL_NOTRADE)

    assert msg.startswith("*📊 SIGNAL OUTCOME · 08 Sep · NO TRADE*\n\n")
    assert "➖ No signal issued today" in msg
    assert "🏁 Nifty close: 24,842" in msg
    assert "P&L" not in msg


def test_missing_premium_falls_back_to_close_only() -> None:
    out = _OUT_EXEC.model_copy(update={"exit_premium": None, "pnl_per_lot": None})
    msg = _FMT(out, _SIGNAL_BUY)

    assert msg.startswith("*📊 SIGNAL OUTCOME · 08 Sep*\n\n")
    assert "➖ Outcome not priced" in msg
    assert "🏁 Nifty close: 24,842" in msg
    assert "Entry" not in msg


def test_resolve_option_key_delegates_and_exits_on_none() -> None:
    signal = DailySignal(
        trade_date=date(2026, 9, 8),
        responses=[],
        consensus_direction=Direction.BULLISH,
        consensus_confidence=Decimal("4"),
        trade_action=TradeAction.BUY_CALL,
        recommended_strike=24800,
        entry_premium=None,
        agreeing_models=[],
        dissenting_models=[],
    )
    with patch("scripts.record_signal_outcome.resolve_monthly_option") as mock_resolve:
        mock_resolve.return_value = "NSE_FO|12345"
        key = record_signal_outcome._resolve_option_key(signal, Path("/fake/bod.json"))
        assert key == "NSE_FO|12345"
        mock_resolve.assert_called_once_with(signal, Path("/fake/bod.json"))

        mock_resolve.return_value = None
        with pytest.raises(SystemExit) as exc_info:
            record_signal_outcome._resolve_option_key(signal, Path("/fake/bod.json"))
        assert exc_info.value.code == 1


@patch("scripts.record_signal_outcome._parse_args")
@patch("scripts.record_signal_outcome.market_today")
@patch("scripts.record_signal_outcome.SignalStore")
@patch("scripts.record_signal_outcome._resolve_option_key")
@patch("scripts.record_signal_outcome._fetch_ltp")
@patch("scripts.record_signal_outcome.build_notifier")
def test_auto_path_prefers_stored_entry_premium_over_consensus(
    mock_notifier: MagicMock,
    mock_fetch_ltp: MagicMock,
    mock_resolve: MagicMock,
    mock_store_cls: MagicMock,
    mock_market_today: MagicMock,
    mock_parse_args: MagicMock,
) -> None:
    mock_parse_args.return_value = MagicMock(
        auto=True,
        entry_premium=None,
        exit_premium=None,
        executed=False,
        nifty_close=None,
        bod_path=Path("/fake/bod.json"),
        notes="",
        trade_date="2026-09-08",
    )
    mock_market_today.return_value = date(2026, 9, 8)
    mock_notifier.return_value = None

    mock_store = MagicMock()
    mock_store_cls.return_value = mock_store

    # signal WITH entry_premium
    signal = DailySignal(
        trade_date=date(2026, 9, 8),
        responses=[],
        consensus_direction=Direction.BULLISH,
        consensus_confidence=Decimal("4"),
        trade_action=TradeAction.BUY_CALL,
        recommended_strike=24800,
        entry_premium=Decimal("120.00"),
        agreeing_models=[],
        dissenting_models=[],
    )
    mock_store.get_signal.return_value = signal

    mock_resolve.return_value = "NSE_FO|12345"
    mock_fetch_ltp.return_value = {
        "NSE_FO|12345": Decimal("150.00"),
        "NSE_INDEX|Nifty 50": Decimal("24850.00"),
    }

    with patch("scripts.record_signal_outcome._consensus_entry_premium") as mock_consensus:
        mock_consensus.return_value = Decimal("99.99")

        record_signal_outcome.main()

        # assert outcome was recorded with 120.00, not 99.99
        outcome = mock_store.record_outcome.call_args[0][0]
        assert outcome.entry_premium == Decimal("120.00")
        mock_consensus.assert_not_called()


@patch("scripts.record_signal_outcome._parse_args")
@patch("scripts.record_signal_outcome.market_today")
@patch("scripts.record_signal_outcome.SignalStore")
@patch("scripts.record_signal_outcome._resolve_option_key")
@patch("scripts.record_signal_outcome._fetch_ltp")
@patch("scripts.record_signal_outcome.build_notifier")
def test_auto_path_falls_back_to_consensus_when_entry_premium_none(
    mock_notifier: MagicMock,
    mock_fetch_ltp: MagicMock,
    mock_resolve: MagicMock,
    mock_store_cls: MagicMock,
    mock_market_today: MagicMock,
    mock_parse_args: MagicMock,
) -> None:
    mock_parse_args.return_value = MagicMock(
        auto=True,
        entry_premium=None,
        exit_premium=None,
        executed=False,
        nifty_close=None,
        bod_path=Path("/fake/bod.json"),
        notes="",
        trade_date="2026-09-08",
    )
    mock_market_today.return_value = date(2026, 9, 8)
    mock_notifier.return_value = None

    mock_store = MagicMock()
    mock_store_cls.return_value = mock_store

    # signal WITHOUT entry_premium
    signal = DailySignal(
        trade_date=date(2026, 9, 8),
        responses=[],
        consensus_direction=Direction.BULLISH,
        consensus_confidence=Decimal("4"),
        trade_action=TradeAction.BUY_CALL,
        recommended_strike=24800,
        entry_premium=None,
        agreeing_models=[],
        dissenting_models=[],
    )
    mock_store.get_signal.return_value = signal

    mock_resolve.return_value = "NSE_FO|12345"
    mock_fetch_ltp.return_value = {
        "NSE_FO|12345": Decimal("150.00"),
        "NSE_INDEX|Nifty 50": Decimal("24850.00"),
    }

    with patch("scripts.record_signal_outcome._consensus_entry_premium") as mock_consensus:
        mock_consensus.return_value = Decimal("99.99")

        record_signal_outcome.main()

        # assert outcome was recorded with 99.99
        outcome = mock_store.record_outcome.call_args[0][0]
        assert outcome.entry_premium == Decimal("99.99")
        mock_consensus.assert_called_once()

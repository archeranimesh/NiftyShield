"""No-network render tests for the S5.5a outcome Telegram message."""

from __future__ import annotations

import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

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

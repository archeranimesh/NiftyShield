"""Tests for morning_signal.run() per-provider logging (BUG-040 follow-up)."""

from __future__ import annotations

import sys
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from scripts import morning_signal
from src.signals.models import DailySignal, Direction, SignalResponse, TradeAction


def _fake_signal(action: TradeAction = TradeAction.NO_TRADE) -> MagicMock:
    sig = MagicMock()
    sig.consensus_direction = Direction.NEUTRAL
    sig.trade_action = action
    sig.is_actionable = action is not TradeAction.NO_TRADE
    sig.consensus_confidence = Decimal("0")
    sig.agreeing_models = []
    sig.dissenting_models = ["gpt4o"]
    sig.responses = []
    return sig


def _fake_snapshot() -> MagicMock:
    snap = MagicMock()
    snap.nifty_spot = Decimal("23644.35")
    snap.prev_close = Decimal("23779.15")
    snap.prev_high = Decimal("23890.0")
    snap.prev_low = Decimal("23737.9")
    snap.gift_nifty = Decimal("23704.5")
    snap.india_vix = Decimal("11.15")
    snap.vix_5d_trend = "flat"
    snap.usd_inr = Decimal("94.78")
    snap.monthly_expiry = date(2026, 9, 29)
    snap.option_chain.atm_strike = 23650
    snap.option_chain.atm_iv = Decimal("10.32")
    snap.option_chain.iv_skew = Decimal("0.26")
    snap.option_chain.pcr_total = Decimal("1.05")
    snap.option_chain.pcr_atm = Decimal("1.02")
    snap.fii.fii_cash_net_cr = Decimal("280.13")
    snap.fii.dii_cash_net_cr = Decimal("566.76")
    return snap


@pytest.mark.asyncio
async def test_run_delegates_to_pipeline_and_sends_notification() -> None:
    """`run()` is orchestration-only: pipeline call, then Telegram send.

    Provider dispatch / snapshot logging / entry-premium capture are now
    `src.signals.pipeline` behaviour — covered by
    `tests/unit/signals/test_pipeline.py`.
    """
    from src.signals.pipeline import MorningSignalResult

    sig = _fake_signal()
    snap = _fake_snapshot()
    fake_result = MorningSignalResult(
        signal=sig, snapshot=snap, n_providers=2, day_cost_usd=Decimal("0.0042"), n_priced=1
    )
    fake_notifier = AsyncMock()

    with (
        patch.object(morning_signal, "create_client", return_value=MagicMock()),
        patch.object(morning_signal, "SignalStore", return_value=MagicMock()),
        patch.object(morning_signal, "guard_trading_day", return_value=False),
        patch.object(
            morning_signal,
            "run_morning_signal_pipeline",
            AsyncMock(return_value=fake_result),
        ) as mock_pipeline,
        patch.object(morning_signal, "build_notifier", return_value=fake_notifier),
    ):
        await morning_signal.run()

    mock_pipeline.assert_awaited_once()
    fake_notifier.send.assert_awaited_once()


@pytest.mark.asyncio
async def test_run_returns_early_on_non_trading_day() -> None:
    with (
        patch.object(morning_signal, "guard_trading_day", return_value=True),
        patch.object(morning_signal, "create_client") as mock_create_client,
        patch.object(morning_signal, "run_morning_signal_pipeline") as mock_pipeline,
    ):
        await morning_signal.run()

    mock_create_client.assert_not_called()
    mock_pipeline.assert_not_called()


def _resp(
    provider: str,
    direction: Direction,
    conf: int = 4,
    low: str = "58.00",
    high: str = "72.00",
) -> SignalResponse:
    return SignalResponse(
        trade_date=date(2026, 9, 8),
        provider=provider,
        direction=direction,
        confidence=conf,
        recommended_strike=24800,
        entry_premium_low=Decimal(low),
        entry_premium_high=Decimal(high),
        key_reason="GIFT Nifty supportive.",
        key_risk="US CPI tonight.",
        raw_response="{}",
    )


def test_format_signal_notification_with_real_entry() -> None:
    signal = DailySignal(
        trade_date=date(2026, 9, 8),
        responses=[
            _resp("grok", Direction.BULLISH, 4, low="50.00", high="66.00"),
            _resp("gpt4o", Direction.BULLISH, 3, low="66.00", high="78.00"),
        ],
        consensus_direction=Direction.BULLISH,
        consensus_confidence=Decimal("3.5"),
        trade_action=TradeAction.BUY_CALL,
        recommended_strike=24800,
        agreeing_models=["grok", "gpt4o"],
        dissenting_models=["gemini"],
        entry_premium=Decimal("65.40"),
    )
    msg = morning_signal._format_signal_notification(signal, 3)

    assert r"💰 Entry: ₹65\.40" in msg
    assert "Entry band" not in msg


def test_format_signal_notification_fallback_band() -> None:
    signal = DailySignal(
        trade_date=date(2026, 9, 8),
        responses=[
            _resp("grok", Direction.BULLISH, 4, low="50.00", high="66.00"),
            _resp("gpt4o", Direction.BULLISH, 3, low="66.00", high="78.00"),
        ],
        consensus_direction=Direction.BULLISH,
        consensus_confidence=Decimal("3.5"),
        trade_action=TradeAction.BUY_CALL,
        recommended_strike=24800,
        agreeing_models=["grok", "gpt4o"],
        dissenting_models=["gemini"],
    )
    msg = morning_signal._format_signal_notification(signal, 3)

    assert msg.startswith("*📈 CONSENSUS: BULLISH*\n\n")
    assert "🎯 Strike: 24800" in msg
    assert "📊 Confidence: 3\\.5 / 5\\.0" in msg
    assert "💰 Entry band: ₹58\\.00 – ₹72\\.00" in msg
    assert "*Model Votes:*" in msg
    assert "👍 Agree: grok, gpt4o" in msg
    assert "👎 Dissent: gemini" in msg


def test_format_signal_notification_no_consensus_lists_every_vote() -> None:
    signal = DailySignal(
        trade_date=date(2026, 9, 8),
        responses=[
            _resp("grok", Direction.BULLISH),
            _resp("gpt4o", Direction.BEARISH),
            _resp("gemini", Direction.NEUTRAL),
        ],
        consensus_direction=Direction.NEUTRAL,
        consensus_confidence=Decimal("0"),
        trade_action=TradeAction.NO_TRADE,
        recommended_strike=None,
        agreeing_models=[],
        dissenting_models=["grok", "gpt4o", "gemini"],
    )
    msg = morning_signal._format_signal_notification(signal, 3)

    assert msg.startswith("*⏸ NO TRADE · NO CONSENSUS*\n\n")
    assert "📈 grok: BULLISH" in msg
    assert "📉 gpt4o: BEARISH" in msg
    assert "➖ gemini: NEUTRAL" in msg


def _consensus_signal() -> DailySignal:
    return DailySignal(
        trade_date=date(2026, 9, 8),
        responses=[
            _resp("grok", Direction.BULLISH, 4, low="50.00", high="66.00"),
            _resp("gpt4o", Direction.BULLISH, 3, low="66.00", high="78.00"),
        ],
        consensus_direction=Direction.BULLISH,
        consensus_confidence=Decimal("3.5"),
        trade_action=TradeAction.BUY_CALL,
        recommended_strike=24800,
        agreeing_models=["grok", "gpt4o"],
        dissenting_models=["gemini"],
        entry_premium=Decimal("65.40"),
    )


def test_notification_consensus_shows_cost() -> None:
    msg = morning_signal._format_signal_notification(_consensus_signal(), 3, Decimal("0.0042"), 2)
    assert r"💵 LLM cost: $0\.0042 \(2 calls\)" in msg


def test_notification_no_consensus_shows_cost() -> None:
    signal = DailySignal(
        trade_date=date(2026, 9, 8),
        responses=[
            _resp("grok", Direction.BULLISH),
            _resp("gpt4o", Direction.BEARISH),
        ],
        consensus_direction=Direction.NEUTRAL,
        consensus_confidence=Decimal("0"),
        trade_action=TradeAction.NO_TRADE,
        recommended_strike=None,
        agreeing_models=[],
        dissenting_models=["grok", "gpt4o"],
    )
    msg = morning_signal._format_signal_notification(signal, 3, Decimal("0.0030"), 2)
    assert r"💵 LLM cost: $0\.0030 \(2 calls\)" in msg


def test_notification_pipeline_failure_shows_zero_cost() -> None:
    signal = DailySignal(
        trade_date=date(2026, 9, 8),
        responses=[],
        consensus_direction=Direction.NEUTRAL,
        consensus_confidence=Decimal("0"),
        trade_action=TradeAction.NO_TRADE,
        recommended_strike=None,
        agreeing_models=[],
        dissenting_models=[],
    )
    msg = morning_signal._format_signal_notification(signal, 2)
    assert r"💵 LLM cost: $0\.0000 \(0 calls\)" in msg


def test_notification_cost_line_escaped() -> None:
    msg = morning_signal._format_signal_notification(_consensus_signal(), 3, Decimal("0.0042"), 2)
    assert r"$0\.0042" in msg
    assert "$0.0042" not in msg


def test_notification_singular_call() -> None:
    msg = morning_signal._format_signal_notification(_consensus_signal(), 3, Decimal("0.0011"), 1)
    assert r"💵 LLM cost: $0\.0011 \(1 call\)" in msg


def test_format_signal_notification_pipeline_failed_uses_provider_count() -> None:
    signal = DailySignal(
        trade_date=date(2026, 9, 8),
        responses=[],
        consensus_direction=Direction.NEUTRAL,
        consensus_confidence=Decimal("0"),
        trade_action=TradeAction.NO_TRADE,
        recommended_strike=None,
        agreeing_models=[],
        dissenting_models=[],
    )
    msg = morning_signal._format_signal_notification(signal, 2)

    assert msg.startswith("*🚨 SIGNAL PIPELINE FAILED*\n\n")
    assert "❌ 0 / 2 models responded" in msg
    assert "No signal issued today" in msg

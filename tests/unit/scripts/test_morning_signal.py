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


def _response(provider: str = "gpt4o", direction: Direction = Direction.NEUTRAL) -> SignalResponse:
    return SignalResponse(
        trade_date=date(2026, 9, 8),
        provider=provider,
        direction=direction,
        confidence=3,
        recommended_strike=23650,
        entry_premium_low=Decimal("150"),
        entry_premium_high=Decimal("180"),
        key_reason="Balanced flows, PCR near 1.",
        key_risk="A sharp FII flow reversal.",
        raw_response="{}",
    )


class _OkProvider:
    def __init__(self, resp: SignalResponse) -> None:
        self._resp = resp

    async def get_signal(self, _snapshot: object) -> SignalResponse:
        return self._resp


class _ErrProvider:
    async def get_signal(self, _snapshot: object) -> SignalResponse:
        raise RuntimeError("openrouter 429")


def _fake_signal(action: TradeAction = TradeAction.NO_TRADE) -> MagicMock:
    sig = MagicMock()
    sig.consensus_direction = Direction.NEUTRAL
    sig.trade_action = action
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


async def _run_with(providers: list[object]) -> list[tuple[str, dict]]:
    """Run morning_signal.run() with all I/O mocked; return captured log calls."""
    calls: list[tuple[str, dict]] = []
    fake_logger = MagicMock()
    fake_logger.info.side_effect = lambda event, **kw: calls.append((event, kw))
    fake_logger.warning.side_effect = lambda event, **kw: calls.append((event, kw))

    aggregator = MagicMock()
    aggregator.aggregate.return_value = _fake_signal()

    with (
        patch.object(morning_signal, "logger", fake_logger),
        patch.object(morning_signal, "build_providers", return_value=providers),
        patch.object(morning_signal, "create_client", return_value=MagicMock()),
        patch.object(morning_signal, "SignalStore", return_value=MagicMock()),
        patch.object(
            morning_signal,
            "assemble_market_snapshot",
            AsyncMock(return_value=_fake_snapshot()),
        ),
        patch.object(morning_signal, "build_aggregator", return_value=aggregator),
        patch.object(morning_signal, "build_notifier", return_value=None),
        patch.object(morning_signal, "market_today", return_value=date(2026, 9, 8)),
    ):
        await morning_signal.run()
    return calls


@pytest.mark.asyncio
async def test_each_provider_response_is_logged() -> None:
    calls = await _run_with([_OkProvider(_response()), _ErrProvider()])
    events = {e for e, _ in calls}

    assert "morning_signal.providers_dispatched" in events
    assert "morning_signal.provider_error" in events

    resp_line = next(kw for e, kw in calls if e == "morning_signal.provider_response")
    assert resp_line["provider"] == "gpt4o"
    assert resp_line["direction"] == "NEUTRAL"
    assert resp_line["confidence"] == 3
    assert resp_line["recommended_strike"] == 23650
    assert resp_line["key_reason"] == "Balanced flows, PCR near 1."

    complete = next(kw for e, kw in calls if e == "morning_signal_complete")
    assert complete["n_responses"] == 1


@pytest.mark.asyncio
async def test_snapshot_inputs_are_logged() -> None:
    calls = await _run_with([_OkProvider(_response())])
    snap_line = next(kw for e, kw in calls if e == "morning_signal.snapshot_assembled")
    assert snap_line["usd_inr"] == "94.78"
    assert snap_line["india_vix"] == "11.15"
    assert snap_line["gift_nifty"] == "23704.5"
    assert snap_line["atm_strike"] == 23650
    assert snap_line["pcr_total"] == "1.05"
    assert snap_line["fii_cash_net_cr"] == "280.13"
    assert snap_line["monthly_expiry"] == "2026-09-29"


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


def test_format_signal_notification_directional_consensus() -> None:
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


@pytest.mark.asyncio
async def test_all_providers_failing_logs_no_valid_responses() -> None:
    calls = await _run_with([_ErrProvider(), _ErrProvider()])
    events = [e for e, _ in calls]

    assert "morning_signal.no_valid_responses" in events
    assert "morning_signal.provider_response" not in events
    warn = next(kw for e, kw in calls if e == "morning_signal.no_valid_responses")
    assert warn["dispatched"] == 2
    assert warn["errors"] == 2


@pytest.mark.asyncio
async def test_run_captures_entry_premium_on_directional_signal() -> None:
    # Setup mock broker that returns LTP for the resolved option
    fake_broker = AsyncMock()
    fake_broker.get_ltp.return_value = {"NSE_FO|resolved_monthly_key": Decimal("112.50")}

    aggregator = MagicMock()
    sig = DailySignal(
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
    aggregator.aggregate.return_value = sig

    store_mock = MagicMock()

    with (
        patch.object(morning_signal, "logger"),
        patch.object(morning_signal, "build_providers", return_value=[_OkProvider(_response())]),
        patch.object(morning_signal, "create_client", return_value=fake_broker),
        patch.object(morning_signal, "SignalStore", return_value=store_mock),
        patch.object(
            morning_signal,
            "assemble_market_snapshot",
            AsyncMock(return_value=_fake_snapshot()),
        ),
        patch.object(morning_signal, "build_aggregator", return_value=aggregator),
        patch.object(morning_signal, "build_notifier", return_value=None),
        patch.object(morning_signal, "market_today", return_value=date(2026, 9, 8)),
        patch.object(
            morning_signal, "resolve_monthly_option", return_value="NSE_FO|resolved_monthly_key"
        ),
    ):
        await morning_signal.run()

    # The signal saved should have entry_premium updated
    record_call = store_mock.record_signal.call_args[0][0]
    assert record_call.entry_premium == Decimal("112.50")


@pytest.mark.asyncio
async def test_run_leaves_entry_premium_none_on_fetch_failure() -> None:
    fake_broker = AsyncMock()
    # broker raises exception
    fake_broker.get_ltp.side_effect = Exception("network error")

    aggregator = MagicMock()
    sig = DailySignal(
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
    aggregator.aggregate.return_value = sig

    store_mock = MagicMock()

    with (
        patch.object(morning_signal, "logger"),
        patch.object(morning_signal, "build_providers", return_value=[_OkProvider(_response())]),
        patch.object(morning_signal, "create_client", return_value=fake_broker),
        patch.object(morning_signal, "SignalStore", return_value=store_mock),
        patch.object(
            morning_signal,
            "assemble_market_snapshot",
            AsyncMock(return_value=_fake_snapshot()),
        ),
        patch.object(morning_signal, "build_aggregator", return_value=aggregator),
        patch.object(morning_signal, "build_notifier", return_value=None),
        patch.object(morning_signal, "market_today", return_value=date(2026, 9, 8)),
        patch.object(
            morning_signal, "resolve_monthly_option", return_value="NSE_FO|resolved_monthly_key"
        ),
    ):
        await morning_signal.run()

    # Pipeline shouldn't crash, entry_premium should remain None
    record_call = store_mock.record_signal.call_args[0][0]
    assert record_call.entry_premium is None


@pytest.mark.asyncio
@patch("scripts.morning_signal.assemble_market_snapshot")
@patch("scripts.morning_signal.build_aggregator")
@patch("scripts.morning_signal.build_providers")
@patch("scripts.morning_signal.SignalStore")
@patch("scripts.morning_signal.build_notifier")
@patch("scripts.morning_signal.create_client")
@patch("scripts.morning_signal.resolve_monthly_option")
@patch("scripts.morning_signal.logger")
async def test_run_leaves_entry_premium_none_on_resolver_none(
    mock_logger: MagicMock,
    mock_resolve: MagicMock,
    mock_broker_create: MagicMock,
    mock_build_notifier: MagicMock,
    mock_signal_store: MagicMock,
    mock_build_providers: MagicMock,
    mock_signal_aggregator: MagicMock,
    mock_assemble_market_snapshot: AsyncMock,
) -> None:
    # (a) resolve_monthly_option returns None -> entry_premium stays None, no warning
    mock_build_notifier.return_value = AsyncMock()
    mock_store = MagicMock()
    mock_signal_store.return_value = mock_store

    sig = DailySignal(
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

    mock_agg = MagicMock()
    mock_agg.aggregate.return_value = sig
    mock_signal_aggregator.return_value = mock_agg
    mock_build_providers.return_value = []

    mock_resolve.return_value = None

    await morning_signal.run()

    record_call = mock_store.record_signal.call_args[0][0]
    assert record_call.entry_premium is None

    # Check no warning was logged for missing LTP
    for call in mock_logger.warning.call_args_list:
        assert "morning_signal.ltp_missing_for_key" not in call[0]


@pytest.mark.asyncio
@patch("scripts.morning_signal.assemble_market_snapshot")
@patch("scripts.morning_signal.build_aggregator")
@patch("scripts.morning_signal.build_providers")
@patch("scripts.morning_signal.SignalStore")
@patch("scripts.morning_signal.build_notifier")
@patch("scripts.morning_signal.create_client")
@patch("scripts.morning_signal.resolve_monthly_option")
@patch("scripts.morning_signal.logger")
async def test_run_leaves_entry_premium_none_on_missing_key(
    mock_logger: MagicMock,
    mock_resolve: MagicMock,
    mock_broker_create: MagicMock,
    mock_build_notifier: MagicMock,
    mock_signal_store: MagicMock,
    mock_build_providers: MagicMock,
    mock_signal_aggregator: MagicMock,
    mock_assemble_market_snapshot: AsyncMock,
) -> None:
    # (b) get_ltp returns a dict without the key -> warning logged, entry_premium None.
    mock_build_notifier.return_value = AsyncMock()
    mock_store = MagicMock()
    mock_signal_store.return_value = mock_store

    mock_broker = MagicMock()
    mock_broker.get_ltp = AsyncMock()
    mock_broker.get_ltp.return_value = {"NSE_FO|SOME_OTHER_KEY": Decimal("100.00")}
    mock_broker_create.return_value = mock_broker

    sig = DailySignal(
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

    mock_agg = MagicMock()
    mock_agg.aggregate.return_value = sig
    mock_signal_aggregator.return_value = mock_agg
    mock_build_providers.return_value = []

    mock_resolve.return_value = "NSE_FO|12345"

    await morning_signal.run()

    record_call = mock_store.record_signal.call_args[0][0]
    assert record_call.entry_premium is None

    mock_logger.warning.assert_any_call(
        "morning_signal.ltp_missing_for_key",
        option_key="NSE_FO|12345",
    )

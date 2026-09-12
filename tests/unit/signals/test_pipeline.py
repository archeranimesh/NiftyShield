"""Tests for src.signals.pipeline.run_morning_signal_pipeline (SEC-4 extraction).

Moved out of ``tests/unit/scripts/test_morning_signal.py`` — this behaviour now
lives in ``src/signals/pipeline.py``; the script only orchestrates + sends
Telegram.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.signals import pipeline
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


async def _run_with(
    providers: list[object],
    *,
    broker: object | None = None,
    aggregator: MagicMock | None = None,
) -> tuple[pipeline.MorningSignalResult, list[tuple[str, dict]]]:
    """Run the pipeline with all I/O mocked; return the result + captured logs."""
    calls: list[tuple[str, dict]] = []
    fake_logger = MagicMock()
    fake_logger.info.side_effect = lambda event, **kw: calls.append((event, kw))
    fake_logger.warning.side_effect = lambda event, **kw: calls.append((event, kw))

    agg = aggregator or MagicMock()
    if aggregator is None:
        agg.aggregate.return_value = _fake_signal()

    fake_store = MagicMock()
    fake_broker = broker if broker is not None else AsyncMock()

    with (
        patch.object(pipeline, "logger", fake_logger),
        patch.object(pipeline, "build_providers", return_value=providers),
        patch.object(
            pipeline, "assemble_market_snapshot", AsyncMock(return_value=_fake_snapshot())
        ),
        patch.object(pipeline, "build_aggregator", return_value=agg),
        patch.object(pipeline, "market_today", return_value=date(2026, 9, 8)),
        patch.object(pipeline, "open_signal_paper_entry", AsyncMock(return_value=None)),
        patch.object(pipeline, "PaperStore", return_value=MagicMock()),
    ):
        result = await pipeline.run_morning_signal_pipeline(
            fake_broker, fake_store, bod_path=Path("/tmp/bod.csv")
        )
    return result, calls


@pytest.mark.asyncio
async def test_each_provider_response_is_logged() -> None:
    result, calls = await _run_with([_OkProvider(_response()), _ErrProvider()])
    events = {e for e, _ in calls}

    assert "morning_signal.providers_dispatched" in events
    assert "morning_signal.provider_error" in events
    assert result.n_providers == 2

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
    _, calls = await _run_with([_OkProvider(_response())])
    snap_line = next(kw for e, kw in calls if e == "morning_signal.snapshot_assembled")
    assert snap_line["usd_inr"] == "94.78"
    assert snap_line["india_vix"] == "11.15"
    assert snap_line["gift_nifty"] == "23704.5"
    assert snap_line["atm_strike"] == 23650
    assert snap_line["pcr_total"] == "1.05"
    assert snap_line["fii_cash_net_cr"] == "280.13"
    assert snap_line["monthly_expiry"] == "2026-09-29"


@pytest.mark.asyncio
async def test_all_providers_failing_logs_no_valid_responses() -> None:
    _, calls = await _run_with([_ErrProvider(), _ErrProvider()])
    events = [e for e, _ in calls]

    assert "morning_signal.no_valid_responses" in events
    assert "morning_signal.provider_response" not in events
    warn = next(kw for e, kw in calls if e == "morning_signal.no_valid_responses")
    assert warn["dispatched"] == 2
    assert warn["errors"] == 2


@pytest.mark.asyncio
async def test_run_captures_entry_premium_on_directional_signal() -> None:
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

    with patch.object(
        pipeline, "resolve_monthly_option", return_value="NSE_FO|resolved_monthly_key"
    ):
        result, _ = await _run_with(
            [_OkProvider(_response())], broker=fake_broker, aggregator=aggregator
        )

    assert result.signal.entry_premium == Decimal("112.50")


@pytest.mark.asyncio
async def test_run_leaves_entry_premium_none_on_fetch_failure() -> None:
    fake_broker = AsyncMock()
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

    with patch.object(
        pipeline, "resolve_monthly_option", return_value="NSE_FO|resolved_monthly_key"
    ):
        result, _ = await _run_with(
            [_OkProvider(_response())], broker=fake_broker, aggregator=aggregator
        )

    assert result.signal.entry_premium is None


@pytest.mark.asyncio
async def test_run_leaves_entry_premium_none_on_resolver_none() -> None:
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

    with patch.object(pipeline, "resolve_monthly_option", return_value=None):
        result, calls = await _run_with([], aggregator=aggregator)

    assert result.signal.entry_premium is None
    for event, _ in calls:
        assert event != "morning_signal.ltp_missing_for_key"


@pytest.mark.asyncio
async def test_run_leaves_entry_premium_none_on_missing_key() -> None:
    mock_broker = AsyncMock()
    mock_broker.get_ltp.return_value = {"NSE_FO|SOME_OTHER_KEY": Decimal("100.00")}

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

    with patch.object(pipeline, "resolve_monthly_option", return_value="NSE_FO|12345"):
        result, calls = await _run_with([], broker=mock_broker, aggregator=aggregator)

    assert result.signal.entry_premium is None
    warn = next(kw for e, kw in calls if e == "morning_signal.ltp_missing_for_key")
    assert warn["option_key"] == "NSE_FO|12345"


@pytest.mark.asyncio
async def test_paper_entry_hook_called_once_when_actionable() -> None:
    aggregator = MagicMock()
    aggregator.aggregate.return_value = _fake_signal(action=TradeAction.BUY_CALL)

    with (
        patch.object(pipeline, "resolve_monthly_option", return_value=None),
        patch.object(pipeline, "open_signal_paper_entry", AsyncMock(return_value=None)) as hook,
        patch.object(pipeline, "PaperStore", return_value=MagicMock()),
        patch.object(pipeline, "logger", MagicMock()),
        patch.object(pipeline, "build_providers", return_value=[]),
        patch.object(
            pipeline, "assemble_market_snapshot", AsyncMock(return_value=_fake_snapshot())
        ),
        patch.object(pipeline, "build_aggregator", return_value=aggregator),
        patch.object(pipeline, "market_today", return_value=date(2026, 9, 8)),
    ):
        await pipeline.run_morning_signal_pipeline(
            AsyncMock(), MagicMock(), bod_path=Path("/tmp/bod.csv")
        )

    hook.assert_awaited_once()


@pytest.mark.asyncio
async def test_paper_entry_hook_called_once_on_no_trade_too() -> None:
    aggregator = MagicMock()
    aggregator.aggregate.return_value = _fake_signal(action=TradeAction.NO_TRADE)

    with (
        patch.object(pipeline, "open_signal_paper_entry", AsyncMock(return_value=None)) as hook,
        patch.object(pipeline, "PaperStore", return_value=MagicMock()),
        patch.object(pipeline, "logger", MagicMock()),
        patch.object(pipeline, "build_providers", return_value=[]),
        patch.object(
            pipeline, "assemble_market_snapshot", AsyncMock(return_value=_fake_snapshot())
        ),
        patch.object(pipeline, "build_aggregator", return_value=aggregator),
        patch.object(pipeline, "market_today", return_value=date(2026, 9, 8)),
    ):
        result = await pipeline.run_morning_signal_pipeline(
            AsyncMock(), MagicMock(), bod_path=Path("/tmp/bod.csv")
        )

    # SPT-6's own guard is a no-op on NO_TRADE, but the tail-call itself is
    # still made (isolated by try/except) — assert the pipeline still
    # completes and records the NO_TRADE signal.
    hook.assert_awaited_once()
    assert result.signal.trade_action is TradeAction.NO_TRADE

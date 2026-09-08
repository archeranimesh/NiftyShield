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
from src.signals.models import Direction, SignalResponse, TradeAction


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
        patch.object(morning_signal, "SignalAggregator", return_value=aggregator),
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


@pytest.mark.asyncio
async def test_all_providers_failing_logs_no_valid_responses() -> None:
    calls = await _run_with([_ErrProvider(), _ErrProvider()])
    events = [e for e, _ in calls]

    assert "morning_signal.no_valid_responses" in events
    assert "morning_signal.provider_response" not in events
    warn = next(kw for e, kw in calls if e == "morning_signal.no_valid_responses")
    assert warn["dispatched"] == 2
    assert warn["errors"] == 2

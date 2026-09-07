from datetime import date
from decimal import Decimal

import pytest

from src.signals.aggregator import SignalAggregator
from src.signals.models import (
    Direction,
    FIIData,
    MarketSnapshot,
    OILevel,
    OptionChainSummary,
    SignalResponse,
    TradeAction,
)

ATM = 24000


@pytest.fixture
def snapshot() -> MarketSnapshot:
    return MarketSnapshot(
        trade_date=date(2026, 9, 7),
        nifty_spot=Decimal("24000.50"),
        prev_close=Decimal("23900.00"),
        prev_high=Decimal("24050.00"),
        prev_low=Decimal("23850.00"),
        gift_nifty=Decimal("24100.00"),
        india_vix=Decimal("15.5"),
        vix_5d_trend="rising",
        usd_inr=Decimal("83.50"),
        monthly_expiry=date(2026, 9, 24),
        option_chain=OptionChainSummary(
            atm_strike=ATM,
            atm_iv=Decimal("16.0"),
            iv_skew=Decimal("-0.5"),
            pcr_total=Decimal("0.85"),
            pcr_atm=Decimal("0.90"),
            top_call_oi=[OILevel(strike=24100, oi=100000, oi_change=5000)],
            top_put_oi=[OILevel(strike=23900, oi=150000, oi_change=-2000)],
        ),
        fii=FIIData(
            net_futures_cr=Decimal("1500.5"),
            net_options_cr=Decimal("-500.0"),
        ),
    )


def _response(
    provider: str,
    direction: Direction,
    confidence: int = 4,
    strike: int = ATM,
) -> SignalResponse:
    return SignalResponse(
        trade_date=date(2026, 9, 7),
        provider=provider,
        direction=direction,
        confidence=confidence,
        recommended_strike=strike,
        entry_premium_low=Decimal("80"),
        entry_premium_high=Decimal("100"),
        key_reason="reason",
        key_risk="risk",
        raw_response="{}",
    )


def test_two_bullish_gives_buy_call(snapshot: MarketSnapshot) -> None:
    responses = [
        _response("grok", Direction.BULLISH),
        _response("gpt4o", Direction.BULLISH),
    ]
    signal = SignalAggregator().aggregate(snapshot, responses)
    assert signal.trade_action is TradeAction.BUY_CALL
    assert signal.consensus_direction is Direction.BULLISH
    assert sorted(signal.agreeing_models) == ["gpt4o", "grok"]


def test_two_bearish_gives_buy_put(snapshot: MarketSnapshot) -> None:
    responses = [
        _response("grok", Direction.BEARISH),
        _response("gpt4o", Direction.BEARISH),
    ]
    signal = SignalAggregator().aggregate(snapshot, responses)
    assert signal.trade_action is TradeAction.BUY_PUT


def test_three_way_split_gives_no_trade(snapshot: MarketSnapshot) -> None:
    responses = [
        _response("grok", Direction.BULLISH),
        _response("gpt4o", Direction.BEARISH),
        _response("gemini", Direction.NEUTRAL),
    ]
    signal = SignalAggregator().aggregate(snapshot, responses)
    assert signal.trade_action is TradeAction.NO_TRADE
    assert signal.consensus_direction is Direction.NEUTRAL
    assert signal.recommended_strike is None


def test_confidence_gate_overrides_no_trade(snapshot: MarketSnapshot) -> None:
    responses = [
        _response("grok", Direction.BULLISH, confidence=2),
        _response("gpt4o", Direction.BULLISH, confidence=2),
    ]
    signal = SignalAggregator().aggregate(snapshot, responses)
    assert signal.trade_action is TradeAction.NO_TRADE
    assert signal.consensus_direction is Direction.BULLISH
    assert signal.consensus_confidence == Decimal("2")


def test_strike_out_of_band_excluded_no_trade(snapshot: MarketSnapshot) -> None:
    responses = [
        _response("grok", Direction.BULLISH, strike=ATM + 500),
        _response("gpt4o", Direction.BULLISH),
    ]
    signal = SignalAggregator().aggregate(snapshot, responses)
    assert signal.trade_action is TradeAction.NO_TRADE
    assert "grok" in signal.dissenting_models


def test_confidence_zero_rejected_not_neutral(snapshot: MarketSnapshot) -> None:
    responses = [
        _response("grok", Direction.BULLISH, confidence=0),
        _response("gpt4o", Direction.BULLISH),
        _response("gemini", Direction.BULLISH),
    ]
    signal = SignalAggregator().aggregate(snapshot, responses)
    assert signal.trade_action is TradeAction.BUY_CALL
    assert sorted(signal.agreeing_models) == ["gemini", "gpt4o"]
    assert signal.dissenting_models == ["grok"]


def test_consensus_confidence_exact_decimal(snapshot: MarketSnapshot) -> None:
    responses = [
        _response("grok", Direction.BULLISH, confidence=3),
        _response("gpt4o", Direction.BULLISH, confidence=4),
        _response("gemini", Direction.BULLISH, confidence=5),
    ]
    signal = SignalAggregator().aggregate(snapshot, responses)
    assert signal.consensus_confidence == Decimal("4")


def test_modal_strike_atm_wins_on_tie(snapshot: MarketSnapshot) -> None:
    responses = [
        _response("grok", Direction.BULLISH, strike=ATM),
        _response("gpt4o", Direction.BULLISH, strike=ATM + 50),
    ]
    signal = SignalAggregator().aggregate(snapshot, responses)
    assert signal.recommended_strike == ATM


def test_modal_strike_picks_plurality(snapshot: MarketSnapshot) -> None:
    responses = [
        _response("grok", Direction.BULLISH, strike=ATM + 50),
        _response("gpt4o", Direction.BULLISH, strike=ATM + 50),
        _response("gemini", Direction.BULLISH, strike=ATM),
    ]
    signal = SignalAggregator().aggregate(snapshot, responses)
    assert signal.recommended_strike == ATM + 50


def test_single_response_gives_no_trade(snapshot: MarketSnapshot) -> None:
    signal = SignalAggregator().aggregate(snapshot, [_response("grok", Direction.BULLISH)])
    assert signal.trade_action is TradeAction.NO_TRADE

from datetime import date
from decimal import Decimal

from src.signals.models import (
    DailySignal,
    Direction,
    FIIData,
    MarketSnapshot,
    OILevel,
    OptionChainSummary,
    SignalOutcome,
    SignalResponse,
    TradeAction,
)


def test_direction_enum_values():
    assert Direction.BULLISH.value == "BULLISH"
    assert Direction.BEARISH.value == "BEARISH"
    assert Direction.NEUTRAL.value == "NEUTRAL"


def test_trade_action_enum_values():
    assert TradeAction.BUY_CALL.value == "BUY_CALL"
    assert TradeAction.BUY_PUT.value == "BUY_PUT"
    assert TradeAction.NO_TRADE.value == "NO_TRADE"


def test_market_snapshot_round_trip():
    snapshot = MarketSnapshot(
        trade_date=date(2026, 4, 6),
        nifty_spot=Decimal("22500.50"),
        prev_close=Decimal("22450.00"),
        prev_high=Decimal("22600.00"),
        prev_low=Decimal("22400.00"),
        gift_nifty=Decimal("22550.00"),
        india_vix=Decimal("12.5"),
        vix_5d_trend="flat",
        usd_inr=Decimal("83.50"),
        monthly_expiry=date(2026, 4, 30),
        option_chain=OptionChainSummary(
            atm_strike=22500,
            atm_iv=Decimal("14.2"),
            iv_skew=Decimal("-0.5"),
            pcr_total=Decimal("0.95"),
            pcr_atm=Decimal("1.10"),
            top_call_oi=[OILevel(strike=23000, oi=5000000, oi_change=100000)],
            top_put_oi=[OILevel(strike=22000, oi=4500000, oi_change=-50000)],
        ),
        fii=FIIData(
            net_futures_cr=Decimal("1500.00"),
            net_options_cr=Decimal("-500.00"),
        ),
    )

    dumped = snapshot.model_dump(mode="json")
    loaded = MarketSnapshot.model_validate(dumped)

    assert loaded == snapshot
    assert isinstance(loaded.nifty_spot, Decimal)
    assert isinstance(loaded.option_chain.atm_iv, Decimal)
    assert isinstance(loaded.fii.net_futures_cr, Decimal)


def test_signal_response_construction():
    response = SignalResponse(
        trade_date=date(2026, 4, 6),
        provider="gpt4o",
        direction=Direction.BULLISH,
        confidence=4,
        recommended_strike=22500,
        entry_premium_low=Decimal("105.50"),
        entry_premium_high=Decimal("125.00"),
        key_reason="Strong FII buying and PCR>1.",
        key_risk="VIX is low, sudden spike possible.",
        raw_response='{"direction": "BULLISH", "confidence": 4, "recommended_strike": 22500, "entry_premium_low": 105.5, "entry_premium_high": 125.0, "key_reason": "Strong FII buying and PCR>1.", "key_risk": "VIX is low, sudden spike possible."}',
    )
    assert response.provider == "gpt4o"
    assert response.direction == Direction.BULLISH


def test_daily_signal_no_trade():
    signal = DailySignal(
        trade_date=date(2026, 4, 6),
        responses=[],
        consensus_direction=Direction.NEUTRAL,
        consensus_confidence=Decimal("0"),
        trade_action=TradeAction.NO_TRADE,
        recommended_strike=None,
        agreeing_models=[],
        dissenting_models=[],
    )
    assert signal.trade_action == TradeAction.NO_TRADE
    assert signal.recommended_strike is None


def test_signal_outcome_skipped():
    outcome = SignalOutcome(
        trade_date=date(2026, 4, 6),
        trade_action=TradeAction.BUY_CALL,
        recommended_strike=22500,
        entry_premium=None,
        exit_premium=None,
        pnl_per_lot=None,
        nifty_close=Decimal("22600.00"),
        executed=False,
        phase="openrouter_only",
        notes="Skipped due to low margin",
    )
    assert not outcome.executed
    assert outcome.entry_premium is None
    assert outcome.pnl_per_lot is None


def test_oi_level_negative_change():
    level = OILevel(strike=22500, oi=1500000, oi_change=-350000)
    assert level.oi_change == -350000

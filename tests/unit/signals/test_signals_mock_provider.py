from datetime import date
from decimal import Decimal

import pytest

from src.signals.models import (
    Direction,
    FIIData,
    MarketSnapshot,
    OILevel,
    OptionChainSummary,
    SignalResponse,
)
from src.signals.protocol import SignalProvider
from src.signals.providers.mock import MockSignalProvider

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


def test_is_runtime_signal_provider() -> None:
    assert isinstance(MockSignalProvider(), SignalProvider)


async def test_default_direction_is_bullish(snapshot: MarketSnapshot) -> None:
    resp = await MockSignalProvider().get_signal(snapshot)
    assert isinstance(resp, SignalResponse)
    assert resp.direction is Direction.BULLISH


async def test_constructor_confidence_surfaces(
    snapshot: MarketSnapshot,
) -> None:
    resp = await MockSignalProvider(confidence=2).get_signal(snapshot)
    assert resp.confidence == 2


async def test_recommended_strike_applies_offset(
    snapshot: MarketSnapshot,
) -> None:
    resp = await MockSignalProvider(strike_offset=-50).get_signal(snapshot)
    assert resp.recommended_strike == ATM - 50


async def test_bearish_direction(snapshot: MarketSnapshot) -> None:
    provider = MockSignalProvider(direction=Direction.BEARISH)
    resp = await provider.get_signal(snapshot)
    assert resp.direction is Direction.BEARISH

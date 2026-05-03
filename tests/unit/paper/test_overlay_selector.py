"""Tests for overlay selector."""

import pytest
from decimal import Decimal
import asyncio

from src.paper.overlay_selector import select_overlay_expiry, LegSpreadProfile, CollarSpreadProfile


class MockBrokerClient:
    def __init__(self, expiries_data=None):
        self.expiries_data = expiries_data or {}
        
    async def get_option_chain(self, underlying_key: str, expiry: str) -> list[dict]:
        if expiry not in self.expiries_data:
            raise Exception("No data")
        return self.expiries_data[expiry]


def make_chain_data(expiry: str, strike: float, pe_bid: float, pe_ask: float, ce_bid: float, ce_ask: float, pe_delta: float=-0.5, ce_delta: float=0.5):
    return [{
        "strike_price": strike,
        "expiry": expiry,
        "underlying_spot_price": 24000.0,
        "call_options": {
            "market_data": {"ltp": 100.0, "bid_price": ce_bid, "ask_price": ce_ask, "oi": 1000},
            "option_greeks": {"delta": ce_delta, "theta": -10, "gamma": 0.01, "vega": 5, "iv": 0.2}
        },
        "put_options": {
            "market_data": {"ltp": 100.0, "bid_price": pe_bid, "ask_price": pe_ask, "oi": 1000},
            "option_greeks": {"delta": pe_delta, "theta": -10, "gamma": 0.01, "vega": 5, "iv": 0.2}
        }
    }]


@pytest.mark.asyncio
async def test_select_overlay_expiry_collar_passed():
    # quarterly fails (spread > 3%), yearly passes (spread <= 3%)
    q_expiry = "2026-03-31"
    y_expiry = "2026-12-31"
    
    # Q: mid = 100. Spread = 5/100 = 5%
    q_data = make_chain_data(q_expiry, 23000.0, 97.5, 102.5, 97.5, 102.5)
    # Y: mid = 100. Spread = 2/100 = 2%
    y_data = make_chain_data(y_expiry, 23000.0, 99.0, 101.0, 99.0, 101.0)
    
    broker = MockBrokerClient({
        q_expiry: q_data,
        y_expiry: y_data
    })
    
    candidate_expiries = [q_expiry, y_expiry]
    
    res = await select_overlay_expiry(
        broker=broker,
        underlying_key="NIFTY",
        candidate_expiries=candidate_expiries,
        option_type="COLLAR",
        put_target_strike=Decimal("23000"),
        call_target_strike=Decimal("23000")
    )
    
    assert res.chosen_expiry == y_expiry
    assert "Gate passed" in res.fallback_reason
    assert len(res.profiles) == 2
    
    q_prof = res.profiles[0]
    assert q_prof.put_spread_pct == Decimal("5.0")
    assert q_prof.call_spread_pct == Decimal("5.0")
    
    y_prof = res.profiles[1]
    assert y_prof.put_spread_pct == Decimal("2.0")
    assert y_prof.call_spread_pct == Decimal("2.0")


@pytest.mark.asyncio
async def test_select_overlay_expiry_fallback():
    # All fail
    e1 = "2026-03-31"
    e2 = "2026-04-30"
    
    # e1: 4%, e2: 5%
    d1 = make_chain_data(e1, 23000.0, 98.0, 102.0, 98.0, 102.0)
    d2 = make_chain_data(e2, 23000.0, 97.5, 102.5, 97.5, 102.5)
    
    broker = MockBrokerClient({e1: d1, e2: d2})
    
    res = await select_overlay_expiry(
        broker=broker,
        underlying_key="NIFTY",
        candidate_expiries=[e1, e2],
        option_type="PE",
        put_target_strike=Decimal("23000")
    )
    
    assert res.chosen_expiry == e2  # Fallback to last
    assert "failed" in res.fallback_reason


@pytest.mark.asyncio
async def test_select_overlay_expiry_by_delta():
    e1 = "2026-03-31"
    
    data = [
        {
            "strike_price": 23000.0,
            "expiry": e1,
            "put_options": {
                "market_data": {"ltp": 100.0, "bid_price": 99.0, "ask_price": 101.0, "oi": 1000},
                "option_greeks": {"delta": -0.2, "theta": -10, "gamma": 0.01, "vega": 5}
            }
        },
        {
            "strike_price": 23500.0,
            "expiry": e1,
            "put_options": {
                "market_data": {"ltp": 200.0, "bid_price": 198.0, "ask_price": 202.0, "oi": 1000},
                "option_greeks": {"delta": -0.4, "theta": -10, "gamma": 0.01, "vega": 5}
            }
        }
    ]
    
    broker = MockBrokerClient({e1: data})
    
    res = await select_overlay_expiry(
        broker=broker,
        underlying_key="NIFTY",
        candidate_expiries=[e1],
        option_type="PE",
        put_target_delta=Decimal("-0.39")  # Should pick 23500.0
    )
    
    assert res.chosen_expiry == e1
    prof = res.profiles[0]
    # Spread of 23500 is (202-198)/200 = 4/200 = 2%
    assert prof.spread_pct == Decimal("2.0")

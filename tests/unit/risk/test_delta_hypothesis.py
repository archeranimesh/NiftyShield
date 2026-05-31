"""Hypothesis property tests for aggregate_delta."""

from decimal import Decimal

import hypothesis.strategies as st
import pytest
from hypothesis import given, settings

from src.paper.models import PaperPosition
from src.risk.delta_tracker import PortfolioDeltaTracker


@st.composite
def option_position_strategy(draw, option_type: str | None = None):
    """Generate random PaperPosition option legs with optimized strategies."""
    strategy_name = "test_strat"
    leg_role = "test_leg"
    # Draw non-zero integer net_qty
    net_qty = draw(st.integers(min_value=-1000, max_value=1000).filter(lambda x: x != 0))

    # Fast float -> Decimal path for average prices
    avg_cost_f = draw(
        st.floats(min_value=0.01, max_value=10000.0, allow_nan=False, allow_infinity=False)
    )
    avg_cost = Decimal(str(round(avg_cost_f, 2)))

    avg_sell_price_f = draw(
        st.floats(min_value=0.01, max_value=10000.0, allow_nan=False, allow_infinity=False)
    )
    avg_sell_price = Decimal(str(round(avg_sell_price_f, 2)))

    expiry = draw(st.sampled_from(["25JUN", "26DEC", "31DEC"]))
    strike = draw(st.integers(min_value=10000, max_value=30000))

    if option_type is None:
        opt_type = draw(st.sampled_from(["CE", "PE"]))
    else:
        opt_type = option_type

    instrument_key = f"NSE_FO|NIFTY{expiry}{strike}{opt_type}"

    return PaperPosition(
        strategy_name=strategy_name,
        leg_role=leg_role,
        net_qty=net_qty,
        avg_cost=avg_cost,
        avg_sell_price=avg_sell_price,
        instrument_key=instrument_key,
    )


@settings(max_examples=200)
@given(
    nifty_spot_f=st.floats(min_value=1.0, max_value=30000.0, allow_nan=False, allow_infinity=False),
    lot_size=st.integers(min_value=1, max_value=200),
)
def test_aggregate_delta_empty_positions(nifty_spot_f, lot_size):
    tracker = PortfolioDeltaTracker()
    nifty_spot = Decimal(str(round(nifty_spot_f, 2)))
    result = tracker.aggregate_delta([], nifty_spot, lot_size)
    assert result.options_delta_lots == Decimal(0)
    assert result.niftybees_delta_lots == Decimal(0)
    assert result.total_delta_lots == Decimal(0)


@settings(max_examples=200)
@given(
    positions=st.lists(option_position_strategy(), min_size=0, max_size=10),
    nifty_spot_f=st.floats(
        min_value=1000.0, max_value=30000.0, allow_nan=False, allow_infinity=False
    ),
    lot_size=st.integers(min_value=1, max_value=200),
)
def test_aggregate_delta_additive_invariant(positions, nifty_spot_f, lot_size):
    tracker = PortfolioDeltaTracker()
    nifty_spot = Decimal(str(round(nifty_spot_f, 2)))
    result = tracker.aggregate_delta(positions, nifty_spot, lot_size)
    assert result.total_delta_lots == result.options_delta_lots + result.niftybees_delta_lots


@settings(max_examples=200)
@given(
    pos=option_position_strategy(option_type="CE"),
    nifty_spot_f=st.floats(
        min_value=1000.0, max_value=30000.0, allow_nan=False, allow_infinity=False
    ),
    lot_size=st.integers(min_value=1, max_value=200),
)
def test_ce_delta_sign_matches_net_qty(pos, nifty_spot_f, lot_size):
    tracker = PortfolioDeltaTracker()
    nifty_spot = Decimal(str(round(nifty_spot_f, 2)))
    result = tracker.aggregate_delta([pos], nifty_spot, lot_size)
    expected_sign = 1 if pos.net_qty > 0 else -1
    assert (result.options_delta_lots > 0) == (expected_sign > 0)


@settings(max_examples=200)
@given(
    pos=option_position_strategy(option_type="PE"),
    nifty_spot_f=st.floats(
        min_value=1000.0, max_value=30000.0, allow_nan=False, allow_infinity=False
    ),
    lot_size=st.integers(min_value=1, max_value=200),
)
def test_pe_delta_sign_opposite_net_qty(pos, nifty_spot_f, lot_size):
    tracker = PortfolioDeltaTracker()
    nifty_spot = Decimal(str(round(nifty_spot_f, 2)))
    result = tracker.aggregate_delta([pos], nifty_spot, lot_size)
    expected_sign = -1 if pos.net_qty > 0 else 1
    assert (result.options_delta_lots > 0) == (expected_sign > 0)


@settings(max_examples=200)
@given(
    nifty_spot_f=st.floats(max_value=0.0, allow_nan=False, allow_infinity=False),
    lot_size=st.integers(min_value=1, max_value=200),
)
def test_aggregate_delta_nonpositive_spot_raises(nifty_spot_f, lot_size):
    tracker = PortfolioDeltaTracker()
    nifty_spot = Decimal(str(nifty_spot_f))
    with pytest.raises(ValueError):
        tracker.aggregate_delta([], nifty_spot, lot_size)


@settings(max_examples=200)
@given(
    lot_size=st.integers(max_value=0),
)
def test_aggregate_delta_nonpositive_lot_raises(lot_size):
    tracker = PortfolioDeltaTracker()
    with pytest.raises(ValueError):
        tracker.aggregate_delta([], Decimal("22000"), lot_size)

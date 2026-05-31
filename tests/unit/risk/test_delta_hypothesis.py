"""Hypothesis property tests for aggregate_delta."""

from decimal import Decimal

import hypothesis.strategies as st
import pytest
from hypothesis import given, settings

from src.paper.models import PaperPosition
from src.risk.delta_tracker import PortfolioDeltaTracker


def build_ce_position(net_qty: int) -> PaperPosition:
    """Helper to build a CE option position."""
    return PaperPosition(
        strategy_name="test_strat",
        leg_role="ce_leg",
        net_qty=net_qty,
        avg_cost=Decimal("100"),
        avg_sell_price=Decimal("100"),
        instrument_key="NSE_FO|NIFTY25JUN23000CE",
    )


def build_pe_position(net_qty: int) -> PaperPosition:
    """Helper to build a PE option position."""
    return PaperPosition(
        strategy_name="test_strat",
        leg_role="pe_leg",
        net_qty=net_qty,
        avg_cost=Decimal("100"),
        avg_sell_price=Decimal("100"),
        instrument_key="NSE_FO|NIFTY25JUN23000PE",
    )


@st.composite
def ce_position_strategy(draw):
    strategy_name = draw(st.text(min_size=1, max_size=20))
    leg_role = draw(st.text(min_size=1, max_size=20))
    net_qty = draw(st.integers(min_value=-1000, max_value=1000).filter(lambda x: x != 0))
    avg_cost = draw(
        st.decimals(
            min_value=Decimal("0.01"),
            max_value=Decimal("10000"),
            allow_nan=False,
            allow_infinity=False,
        )
    )
    avg_sell_price = draw(
        st.decimals(
            min_value=Decimal("0.01"),
            max_value=Decimal("10000"),
            allow_nan=False,
            allow_infinity=False,
        )
    )
    expiry = draw(st.sampled_from(["25JUN", "26DEC", "31DEC"]))
    strike = draw(st.integers(min_value=10000, max_value=30000))
    instrument_key = f"NSE_FO|NIFTY{expiry}{strike}CE"
    return PaperPosition(
        strategy_name=strategy_name,
        leg_role=leg_role,
        net_qty=net_qty,
        avg_cost=avg_cost,
        avg_sell_price=avg_sell_price,
        instrument_key=instrument_key,
    )


@st.composite
def pe_position_strategy(draw):
    strategy_name = draw(st.text(min_size=1, max_size=20))
    leg_role = draw(st.text(min_size=1, max_size=20))
    net_qty = draw(st.integers(min_value=-1000, max_value=1000).filter(lambda x: x != 0))
    avg_cost = draw(
        st.decimals(
            min_value=Decimal("0.01"),
            max_value=Decimal("10000"),
            allow_nan=False,
            allow_infinity=False,
        )
    )
    avg_sell_price = draw(
        st.decimals(
            min_value=Decimal("0.01"),
            max_value=Decimal("10000"),
            allow_nan=False,
            allow_infinity=False,
        )
    )
    expiry = draw(st.sampled_from(["25JUN", "26DEC", "31DEC"]))
    strike = draw(st.integers(min_value=10000, max_value=30000))
    instrument_key = f"NSE_FO|NIFTY{expiry}{strike}PE"
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
    nifty_spot=st.decimals(
        min_value=Decimal("1"), max_value=Decimal("30000"), allow_nan=False, allow_infinity=False
    ),
    lot_size=st.integers(min_value=1, max_value=200),
)
def test_aggregate_delta_empty_positions(nifty_spot, lot_size):
    tracker = PortfolioDeltaTracker()
    result = tracker.aggregate_delta([], nifty_spot, lot_size)
    assert result.options_delta_lots == Decimal(0)
    assert result.niftybees_delta_lots == Decimal(0)
    assert result.total_delta_lots == Decimal(0)


@settings(max_examples=200)
@given(positions=st.lists(ce_position_strategy() | pe_position_strategy(), min_size=0, max_size=10))
def test_aggregate_delta_additive_invariant(positions):
    tracker = PortfolioDeltaTracker()
    result = tracker.aggregate_delta(positions, Decimal("22000"), 65)
    assert result.total_delta_lots == result.options_delta_lots + result.niftybees_delta_lots


@settings(max_examples=200)
@given(
    net_qty=st.integers(min_value=-10, max_value=10).filter(lambda x: x != 0),
    nifty_spot=st.decimals(
        min_value=Decimal("1000"), max_value=Decimal("30000"), allow_nan=False, allow_infinity=False
    ),
    lot_size=st.integers(min_value=1, max_value=200),
)
def test_ce_delta_sign_matches_net_qty(net_qty, nifty_spot, lot_size):
    pos = build_ce_position(net_qty=net_qty)
    tracker = PortfolioDeltaTracker()
    result = tracker.aggregate_delta([pos], nifty_spot, lot_size)
    expected_sign = 1 if net_qty > 0 else -1
    assert (result.options_delta_lots > 0) == (expected_sign > 0)


@settings(max_examples=200)
@given(
    net_qty=st.integers(min_value=-10, max_value=10).filter(lambda x: x != 0),
    nifty_spot=st.decimals(
        min_value=Decimal("1000"), max_value=Decimal("30000"), allow_nan=False, allow_infinity=False
    ),
    lot_size=st.integers(min_value=1, max_value=200),
)
def test_pe_delta_sign_opposite_net_qty(net_qty, nifty_spot, lot_size):
    pos = build_pe_position(net_qty=net_qty)
    tracker = PortfolioDeltaTracker()
    result = tracker.aggregate_delta([pos], nifty_spot, lot_size)
    expected_sign = -1 if net_qty > 0 else 1
    assert (result.options_delta_lots > 0) == (expected_sign > 0)


@settings(max_examples=200)
@given(
    nifty_spot=st.decimals(max_value=Decimal("0"), allow_nan=False, allow_infinity=False),
    lot_size=st.integers(min_value=1, max_value=200),
)
def test_aggregate_delta_nonpositive_spot_raises(nifty_spot, lot_size):
    tracker = PortfolioDeltaTracker()
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

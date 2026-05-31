"""Hypothesis property tests for P&L arithmetic."""

from decimal import Decimal

import hypothesis.strategies as st
from hypothesis import given, settings

from src.paper.models import PaperPosition
from src.paper.store import PaperStore
from src.paper.tracker import _compute_leg_unrealized_pnl, _compute_realized_pnl


def build_paper_position(
    net_qty: int,
    avg_cost: Decimal = Decimal("0"),
    avg_sell_price: Decimal = Decimal("0"),
) -> PaperPosition:
    """Helper to build a PaperPosition."""
    return PaperPosition(
        strategy_name="test_strategy",
        leg_role="test_leg",
        net_qty=net_qty,
        avg_cost=avg_cost,
        avg_sell_price=avg_sell_price,
        instrument_key="NSE_FO|NIFTY25JUN23000PE",
    )


@settings(max_examples=200)
@given(
    avg_cost=st.decimals(
        min_value=Decimal("0.01"), max_value=Decimal("10000"), allow_nan=False, allow_infinity=False
    ),
    avg_sell_price=st.decimals(
        min_value=Decimal("0.01"), max_value=Decimal("10000"), allow_nan=False, allow_infinity=False
    ),
    ltp=st.decimals(
        min_value=Decimal("0.01"), max_value=Decimal("10000"), allow_nan=False, allow_infinity=False
    ),
)
def test_unrealized_zero_qty_is_zero(avg_cost, avg_sell_price, ltp):
    pos = build_paper_position(net_qty=0, avg_cost=avg_cost, avg_sell_price=avg_sell_price)
    result = _compute_leg_unrealized_pnl(pos, ltp)
    assert result == Decimal("0")


@settings(max_examples=200)
@given(
    avg_cost=st.decimals(
        min_value=Decimal("0.01"), max_value=Decimal("10000"), allow_nan=False, allow_infinity=False
    ),
    net_qty=st.integers(min_value=1, max_value=1000),
)
def test_long_at_cost_is_flat(avg_cost, net_qty):
    pos = build_paper_position(net_qty=net_qty, avg_cost=avg_cost)
    result = _compute_leg_unrealized_pnl(pos, ltp=avg_cost)
    assert result == Decimal("0")


@settings(max_examples=200)
@given(
    avg_sell_price=st.decimals(
        min_value=Decimal("0.01"), max_value=Decimal("10000"), allow_nan=False, allow_infinity=False
    ),
    net_qty=st.integers(min_value=1, max_value=1000),
)
def test_short_at_sell_price_is_flat(avg_sell_price, net_qty):
    pos = build_paper_position(net_qty=-net_qty, avg_sell_price=avg_sell_price)
    result = _compute_leg_unrealized_pnl(pos, ltp=avg_sell_price)
    assert result == Decimal("0")


@settings(max_examples=200)
@given(
    avg_cost=st.decimals(
        min_value=Decimal("1"), max_value=Decimal("5000"), allow_nan=False, allow_infinity=False
    ),
    premium=st.decimals(
        min_value=Decimal("0.01"), max_value=Decimal("5000"), allow_nan=False, allow_infinity=False
    ),
    net_qty=st.integers(min_value=1, max_value=1000),
)
def test_long_profit_loss_direction(avg_cost, premium, net_qty):
    pos = build_paper_position(net_qty=net_qty, avg_cost=avg_cost)
    ltp_up = avg_cost + premium
    ltp_down = max(Decimal("0.01"), avg_cost - premium)
    assert _compute_leg_unrealized_pnl(pos, ltp_up) >= Decimal("0")
    if ltp_down < avg_cost:
        assert _compute_leg_unrealized_pnl(pos, ltp_down) <= Decimal("0")


@settings(max_examples=200)
@given(
    avg_sell_price=st.decimals(
        min_value=Decimal("1"), max_value=Decimal("5000"), allow_nan=False, allow_infinity=False
    ),
    premium=st.decimals(
        min_value=Decimal("0.01"), max_value=Decimal("5000"), allow_nan=False, allow_infinity=False
    ),
    net_qty=st.integers(min_value=1, max_value=1000),
)
def test_short_profit_loss_direction(avg_sell_price, premium, net_qty):
    pos = build_paper_position(net_qty=-net_qty, avg_sell_price=avg_sell_price)
    ltp_down = max(Decimal("0.01"), avg_sell_price - premium)
    ltp_up = avg_sell_price + premium
    if ltp_down < avg_sell_price:
        assert _compute_leg_unrealized_pnl(pos, ltp_down) >= Decimal("0")
    assert _compute_leg_unrealized_pnl(pos, ltp_up) <= Decimal("0")


@settings(max_examples=200)
@given(
    net_qty=st.integers(min_value=-100, max_value=100),
    avg_cost=st.decimals(
        min_value=Decimal("0.01"), max_value=Decimal("10000"), allow_nan=False, allow_infinity=False
    ),
    avg_sell_price=st.decimals(
        min_value=Decimal("0.01"), max_value=Decimal("10000"), allow_nan=False, allow_infinity=False
    ),
    ltp=st.decimals(
        min_value=Decimal("0.01"), max_value=Decimal("10000"), allow_nan=False, allow_infinity=False
    ),
)
def test_unrealized_return_type_is_decimal(net_qty, avg_cost, avg_sell_price, ltp):
    pos = build_paper_position(net_qty=net_qty, avg_cost=avg_cost, avg_sell_price=avg_sell_price)
    result = _compute_leg_unrealized_pnl(pos, ltp)
    assert isinstance(result, Decimal)


def test_realized_pnl_no_trades(tmp_path):
    store = PaperStore(tmp_path / "test_paper.db")
    result = _compute_realized_pnl(store, "paper_test")
    assert result == Decimal("0")
    assert isinstance(result, Decimal)

from decimal import Decimal
import numpy as np

from src.payoff.core import StrategyPayoff, PayoffLeg
from src.notifications.payoff_chart_axes import x_range, sample_xs, strike_ticks

def test_x_range_pads_key_spots_by_point_four_span():
    payoff = StrategyPayoff(
        legs=(),
        net_premium=Decimal(0),
        max_profit=None,
        max_loss=None,
        breakevens=(),
        rr_ratio=None,
        key_spots=(Decimal("21000"), Decimal("23500"))
    )
    lo, hi = x_range(payoff, Decimal("22348"))
    span = 23500.0 - 21000.0
    expected_lo = 21000.0 - 0.4 * span
    expected_hi = 23500.0 + 0.4 * span
    assert lo == expected_lo
    assert hi == expected_hi

def test_x_range_includes_spot_outside_strikes():
    payoff = StrategyPayoff(
        legs=(),
        net_premium=Decimal(0),
        max_profit=None,
        max_loss=None,
        breakevens=(),
        rr_ratio=None,
        key_spots=(Decimal("21000"), Decimal("22000"))
    )
    lo, hi = x_range(payoff, Decimal("23000"))
    assert hi == 23000.0
    assert lo == 21000.0 - 0.4 * 1000.0

def test_x_range_floors_at_zero():
    payoff = StrategyPayoff(
        legs=(),
        net_premium=Decimal(0),
        max_profit=None,
        max_loss=None,
        breakevens=(),
        rr_ratio=None,
        key_spots=(Decimal("10"), Decimal("20"))
    )
    lo, hi = x_range(payoff, Decimal("15"))
    assert lo == 6.0 # Not negative, so not floored

def test_x_range_actually_floors_at_zero():
    payoff = StrategyPayoff(
        legs=(),
        net_premium=Decimal(0),
        max_profit=None,
        max_loss=None,
        breakevens=(),
        rr_ratio=None,
        key_spots=(Decimal("10"), Decimal("50"))
    )
    lo, hi = x_range(payoff, Decimal("30"))
    assert lo == 0.0

def test_x_range_without_strikes_uses_spot():
    payoff = StrategyPayoff(
        legs=(PayoffLeg(kind="FUT", strike=None, qty=1, entry_price=Decimal("20000")),),
        net_premium=Decimal(0),
        max_profit=None,
        max_loss=None,
        breakevens=(),
        rr_ratio=None,
        key_spots=()
    )
    lo, hi = x_range(payoff, Decimal("20000"))
    span = 20000.0 * 0.1
    assert lo == 20000.0 - 0.4 * span
    assert hi == 20000.0 + 0.4 * span

def test_x_range_single_strike_uses_ten_percent_span():
    payoff = StrategyPayoff(
        legs=(),
        net_premium=Decimal(0),
        max_profit=None,
        max_loss=None,
        breakevens=(),
        rr_ratio=None,
        key_spots=(Decimal("20000"),)
    )
    lo, hi = x_range(payoff, Decimal("20000"))
    span = 20000.0 * 0.1
    assert lo == 20000.0 - 0.4 * span
    assert hi == 20000.0 + 0.4 * span

def test_sample_xs_contains_every_strike_and_breakeven_exactly():
    payoff = StrategyPayoff(
        legs=(
            PayoffLeg(kind="CE", strike=Decimal("21500"), qty=1, entry_price=Decimal("100")),
            PayoffLeg(kind="PE", strike=Decimal("22000"), qty=-1, entry_price=Decimal("150")),
        ),
        net_premium=Decimal(0),
        max_profit=None,
        max_loss=None,
        breakevens=(Decimal("21700"),),
        rr_ratio=None,
        key_spots=()
    )
    xs = sample_xs(payoff, 21000.0, 23000.0)
    assert 21500.0 in xs
    assert 22000.0 in xs
    assert 21700.0 in xs
    # Check strictly increasing
    assert np.all(np.diff(xs) > 0)

def test_strike_ticks_ic_labels_and_sides():
    payoff = StrategyPayoff(
        legs=(
            PayoffLeg(kind="PE", strike=Decimal("21000"), qty=1, entry_price=Decimal("100")),
            PayoffLeg(kind="PE", strike=Decimal("21900"), qty=-1, entry_price=Decimal("150")),
            PayoffLeg(kind="CE", strike=Decimal("23000"), qty=-1, entry_price=Decimal("150")),
            PayoffLeg(kind="CE", strike=Decimal("23500"), qty=1, entry_price=Decimal("100")),
        ),
        net_premium=Decimal(0),
        max_profit=None,
        max_loss=None,
        breakevens=(),
        rr_ratio=None,
        key_spots=()
    )
    span = 4000.0 # Wide enough so no stagger
    ticks = strike_ticks(payoff, span)
    assert len(ticks) == 4
    assert ticks[0].text == "21000 PE\nBUY"
    assert ticks[0].short is False
    assert ticks[1].text == "21900 PE\nSELL"
    assert ticks[1].short is True
    assert ticks[2].text == "23000 CE\nSELL"
    assert ticks[2].short is True

def test_strike_ticks_stagger_close_neighbours():
    payoff = StrategyPayoff(
        legs=(
            PayoffLeg(kind="CE", strike=Decimal("23000"), qty=-1, entry_price=Decimal("100")),
            PayoffLeg(kind="CE", strike=Decimal("23500"), qty=1, entry_price=Decimal("150")),
            PayoffLeg(kind="CE", strike=Decimal("23600"), qty=-1, entry_price=Decimal("150")),
        ),
        net_premium=Decimal(0),
        max_profit=None,
        max_loss=None,
        breakevens=(),
        rr_ratio=None,
        key_spots=()
    )
    span = 4250.0
    ticks = strike_ticks(payoff, span)
    assert not ticks[0].text.startswith("\n")
    # 23500 is within 0.14 * 4250 (595) of 23000 -> drops one row
    assert ticks[1].text.startswith("\n")
    # 23600 is close to 23500, but predecessor was lowered, so it shouldn't drop
    assert not ticks[2].text.startswith("\n")

def test_strike_ticks_skip_strikeless_legs():
    payoff = StrategyPayoff(
        legs=(
            PayoffLeg(kind="EQ", strike=None, qty=1, entry_price=Decimal("100")),
            PayoffLeg(kind="CE", strike=Decimal("21500"), qty=1, entry_price=Decimal("100")),
        ),
        net_premium=Decimal(0),
        max_profit=None,
        max_loss=None,
        breakevens=(),
        rr_ratio=None,
        key_spots=()
    )
    ticks = strike_ticks(payoff, 1000.0)
    assert len(ticks) == 1
    assert ticks[0].x == 21500.0

"""Tests for src.payoff.core.compute_payoff."""

from decimal import Decimal as D

import pytest

from src.payoff.core import PayoffLeg, compute_payoff
from src.payoff.errors import InvalidLegsError


def _ic(lp=22800, sp=23000, sc=23500, lc=23700, qty=65):
    return [
        PayoffLeg("PE", D(lp), qty, D("20"), "long_put"),
        PayoffLeg("PE", D(sp), -qty, D("80"), "short_put"),
        PayoffLeg("CE", D(sc), -qty, D("70"), "short_call"),
        PayoffLeg("CE", D(lc), qty, D("10"), "long_call"),
    ]


def test_compute_payoff_iron_condor():
    p = compute_payoff(_ic())
    assert p.max_profit == D("7800")
    assert p.max_loss == D("-5200")
    assert p.breakevens == (D("22880"), D("23620"))
    assert p.rr_ratio == D("1.5")
    assert p.net_premium == D("7800")
    assert p.key_spots == (D("22800"), D("23000"), D("23500"), D("23700"))


def test_compute_payoff_skewed_wings():
    p = compute_payoff(_ic(lp=22700))  # put wing 300 wide, call wing 200
    assert p.max_loss == D("-300") * 65 + D("7800")


def test_compute_payoff_naked_short_call_unbounded_loss():
    p = compute_payoff([PayoffLeg("CE", D("23500"), -65, D("100"))])
    assert p.max_loss is None
    assert p.rr_ratio is None
    assert p.max_profit == D("6500")
    assert p.breakevens == (D("23600"),)


def test_compute_payoff_long_call_unbounded_profit():
    p = compute_payoff([PayoffLeg("CE", D("23500"), 65, D("100"))])
    assert p.max_profit is None
    assert p.max_loss == D("-6500")
    assert p.breakevens == (D("23600"),)


def test_compute_payoff_empty_legs():
    with pytest.raises(InvalidLegsError):
        compute_payoff([])


def test_compute_payoff_linear_leg_with_strike():
    with pytest.raises(InvalidLegsError):
        compute_payoff([PayoffLeg("FUT", D("23000"), 65, D("100"))])


def test_compute_payoff_option_without_strike():
    with pytest.raises(InvalidLegsError):
        compute_payoff([PayoffLeg("CE", None, 65, D("100"))])


def test_compute_payoff_zero_net_premium():
    legs = [
        PayoffLeg("PE", D("23000"), -65, D("50")),
        PayoffLeg("CE", D("23500"), -65, D("50")),
        PayoffLeg("PE", D("22800"), 65, D("50")),
        PayoffLeg("CE", D("23700"), 65, D("50")),
    ]
    p = compute_payoff(legs)
    assert p.net_premium == D("0")
    assert list(p.breakevens) == sorted(p.breakevens)

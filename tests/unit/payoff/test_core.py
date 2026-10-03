"""Tests for src.payoff.core."""

from decimal import Decimal as D

import pytest

from src.payoff.core import (
    PayoffLeg,
    compute_payoff,
    expiry_pnl_at,
    expiry_pnl_series,
)
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


def test_expiry_pnl_at_plateau():
    p = compute_payoff(_ic())
    assert expiry_pnl_at(p, D("23250")) == p.max_profit


def test_expiry_pnl_at_deep_otm():
    p = compute_payoff(_ic())
    assert expiry_pnl_at(p, D("22000")) == p.max_loss


def test_expiry_pnl_at_breakeven():
    p = compute_payoff(_ic())
    for be in p.breakevens:
        assert abs(expiry_pnl_at(p, be)) < D("0.01")


def test_expiry_pnl_at_unbounded_tail():
    p = compute_payoff([PayoffLeg("CE", D("23500"), -65, D("100"))])
    far, farther = D("25000"), D("26000")
    assert expiry_pnl_at(p, far) - expiry_pnl_at(p, farther) == D("65000")


def test_expiry_pnl_series_length():
    p = compute_payoff(_ic())
    spots, pnls = expiry_pnl_series(p, D("22000"), D("24500"), 11)
    assert len(spots) == len(pnls) == 11
    assert spots[0] == D("22000") and spots[-1] == D("24500")


def test_expiry_pnl_series_rejects_bad_range():
    p = compute_payoff(_ic())
    with pytest.raises(ValueError):
        expiry_pnl_series(p, D("24500"), D("22000"), 5)
    with pytest.raises(ValueError):
        expiry_pnl_series(p, D("22000"), D("24500"), 1)


def test_expiry_pnl_series_min_n():
    p = compute_payoff(_ic())
    spots, pnls = expiry_pnl_series(p, D("22000"), D("24500"), 2)
    assert spots == [D("22000"), D("24500")]
    assert len(pnls) == 2

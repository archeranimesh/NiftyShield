"""Tests for the Phase B signal stack (Layers 0-4)."""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal as D

import pytest

from src.gamma import signals as s
from src.gamma.signals import Candidate, ReasonCode, SignalConfig, SignalStack

CFG = SignalConfig(min_ask_qty=65)


def make(**kw: object) -> Candidate:
    """A CE candidate that passes every layer; override fields via kw."""
    base: dict[str, object] = dict(
        option_type="CE",
        dte=0,
        ask=D("5"),
        bid=D("4.8"),
        spread=D("0.2"),
        ask_qty_l1=130,
        india_vix=D("14"),
        quote_age_seconds=30,
        oi=5000,
        underlying_return_15m=D("0.005"),
        distance_pct=D("0.01"),
        distance_pct_15m_ago=D("0.012"),
        distance_sigma=D("1.0"),
        gamma_gearing=D("20000"),
        speed_5m=D("0.001"),
        theoretical_price=D("7"),
        strike_iv_pctile_20d=None,
        volume_zscore_5m=D("3"),
        oi_velocity_15m=D("0.2"),
        option_price_rising=True,
    )
    base.update(kw)
    return Candidate(**base)  # type: ignore[arg-type]  # kwargs dict is untyped test input


# (predicate, passing override, failing override, expected code)
CASES = [
    (s.l0_dte, {"dte": 1}, {"dte": 2}, ReasonCode.L0_DTE),
    (s.l0_option_type, {}, {"option_type": "XX"}, ReasonCode.L0_OPTION_TYPE),
    (s.l0_premium, {"ask": D("2")}, {"ask": D("1.99")}, ReasonCode.L0_PREMIUM),
    (s.l0_premium, {"ask": D("10")}, {"ask": D("10.01")}, ReasonCode.L0_PREMIUM),
    # mid = 4.9; 25% = 1.225
    (s.l0_spread, {"spread": D("1.225")}, {"spread": D("1.226")}, ReasonCode.L0_SPREAD),
    (s.l0_spread, {}, {"bid": None}, ReasonCode.L0_SPREAD_UNAVAILABLE),
    (s.l0_ask_qty, {"ask_qty_l1": 65}, {"ask_qty_l1": 64}, ReasonCode.L0_ASK_QTY),
    (s.l0_vix, {"india_vix": D("12.01")}, {"india_vix": D("12")}, ReasonCode.L0_VIX),
    (s.l0_vix, {}, {"india_vix": None}, ReasonCode.L0_VIX_UNAVAILABLE),
    (
        s.l0_quote_fresh,
        {"quote_age_seconds": 300},
        {"quote_age_seconds": 301},
        ReasonCode.L0_QUOTE_STALE,
    ),
    (s.l0_quote_fresh, {}, {"quote_age_seconds": None}, ReasonCode.L0_QUOTE_AGE_UNAVAILABLE),
    (s.l0_oi, {"oi": 1000}, {"oi": 999}, ReasonCode.L0_OI),
    (s.l0_oi, {}, {"oi": None}, ReasonCode.L0_OI),
    (
        s.l1_return_direction,
        {"underlying_return_15m": D("0.0001")},
        {"underlying_return_15m": D("0")},
        ReasonCode.L1_RETURN_DIRECTION,
    ),
    (s.l1_return_direction, {}, {"underlying_return_15m": None}, ReasonCode.L1_INPUT_UNAVAILABLE),
    (
        s.l1_distance_shrinking,
        {"distance_pct": D("0.0119")},
        {"distance_pct": D("0.012")},
        ReasonCode.L1_DISTANCE_NOT_SHRINKING,
    ),
    (s.l1_distance_shrinking, {}, {"distance_pct_15m_ago": None}, ReasonCode.L1_INPUT_UNAVAILABLE),
    (s.l1_sigma, {"distance_sigma": D("1.5")}, {"distance_sigma": D("1.51")}, ReasonCode.L1_SIGMA),
    (s.l1_sigma, {}, {"distance_sigma": None}, ReasonCode.L1_INPUT_UNAVAILABLE),
    (
        s.l2_gearing,
        {"gamma_gearing": D("5.01")},
        {"gamma_gearing": D("5.0")},
        ReasonCode.L2_GEARING,
    ),
    (s.l2_gearing, {}, {"gamma_gearing": None}, ReasonCode.L2_GEARING_UNAVAILABLE),
    (s.l2_speed, {"speed_5m": D("0.0001")}, {"speed_5m": D("0")}, ReasonCode.L2_SPEED),
    (s.l2_speed, {}, {"speed_5m": None}, ReasonCode.L2_SPEED_UNAVAILABLE),
    (
        s.l2_move_toward_strike,
        {"underlying_return_15m": D("0.0031")},
        {"underlying_return_15m": D("0.003")},
        ReasonCode.L2_MOVE_TOWARD_STRIKE,
    ),
    (
        s.l4_volume,
        {"volume_zscore_5m": D("2.01")},
        {"volume_zscore_5m": D("2.0")},
        ReasonCode.L4_VOLUME,
    ),
    (s.l4_volume, {}, {"volume_zscore_5m": None}, ReasonCode.L4_INPUT_UNAVAILABLE),
    (
        s.l4_oi_velocity,
        {"oi_velocity_15m": D("0.16")},
        {"oi_velocity_15m": D("0.15")},
        ReasonCode.L4_OI_VELOCITY,
    ),
    (s.l4_oi_velocity, {}, {"oi_velocity_15m": None}, ReasonCode.L4_INPUT_UNAVAILABLE),
    (s.l4_price_rising, {}, {"option_price_rising": False}, ReasonCode.L4_PRICE_NOT_RISING),
    (s.l4_price_rising, {}, {"option_price_rising": None}, ReasonCode.L4_INPUT_UNAVAILABLE),
]


@pytest.mark.parametrize("pred,ok,bad,code", CASES)
def test_predicate_boundary(pred, ok, bad, code) -> None:
    assert pred(make(**ok), CFG) is None
    assert pred(make(**bad), CFG) is code


def test_ask_qty_none_passes_reduced_mode() -> None:
    assert s.l0_ask_qty(make(ask_qty_l1=None), CFG) is None


def test_pe_direction_inverted() -> None:
    pe = make(option_type="PE", underlying_return_15m=D("-0.0031"))
    assert s.l1_return_direction(pe, CFG) is None
    assert s.l2_move_toward_strike(pe, CFG) is None
    up = make(option_type="PE", underlying_return_15m=D("0.005"))
    assert s.l1_return_direction(up, CFG) is ReasonCode.L1_RETURN_DIRECTION
    assert s.l2_move_toward_strike(up, CFG) is ReasonCode.L2_MOVE_TOWARD_STRIKE


def test_move_toward_strike_none_fails() -> None:
    c = make(underlying_return_15m=None)
    assert s.l2_move_toward_strike(c, CFG) is ReasonCode.L2_MOVE_TOWARD_STRIKE


def test_gearing_threshold_is_injected() -> None:
    cfg = replace(CFG, gearing_threshold=D("30000"))
    assert s.l2_gearing(make(), cfg) is ReasonCode.L2_GEARING


# Layer 3. ask=5, spread=0.2 -> need = max(0.75, 0.2, 1.75) = 1.75
def test_l3_condition_a_boundary() -> None:
    assert s.l3_quality(make(theoretical_price=D("6.75")), CFG) is None
    c = make(theoretical_price=D("6.74"))
    assert s.l3_quality(c, CFG) is ReasonCode.L3_B_UNAVAILABLE


def test_l3_condition_a_abs_floor_and_spread_terms() -> None:
    # ask 1 not valid L0 but the predicate is independent: need = max(0.75, .., 0.35)
    low = make(ask=D("2"), spread=D("0.1"), theoretical_price=D("2.75"))
    assert s.l3_quality(low, CFG) is None
    low_fail = make(ask=D("2"), spread=D("0.1"), theoretical_price=D("2.74"))
    assert s.l3_quality(low_fail, CFG) is not None
    wide = make(ask=D("2"), spread=D("1.2"), theoretical_price=D("3.2"))
    assert s.l3_quality(wide, CFG) is None
    wide_fail = make(ask=D("2"), spread=D("1.2"), theoretical_price=D("3.19"))
    assert s.l3_quality(wide_fail, CFG) is not None


def test_l3_condition_a_distance_limit() -> None:
    at = make(distance_pct=D("0.10"), theoretical_price=D("9"))
    assert s.l3_quality(at, CFG) is None
    beyond = make(distance_pct=D("0.1001"), theoretical_price=D("9"))
    assert s.l3_quality(beyond, CFG) is ReasonCode.L3_B_UNAVAILABLE


def test_l3_condition_b_boundary_and_scale() -> None:
    far = make(distance_pct=D("0.2"), theoretical_price=None)
    assert s.l3_quality(replace(far, strike_iv_pctile_20d=D("0.2999")), CFG) is None
    failing = replace(far, strike_iv_pctile_20d=D("0.30"))
    assert s.l3_quality(failing, CFG) is ReasonCode.L3_QUALITY


def test_l3_b_unavailable_never_passes() -> None:
    c = make(theoretical_price=None, strike_iv_pctile_20d=None)
    assert s.l3_quality(c, CFG) is ReasonCode.L3_B_UNAVAILABLE


def test_quality_method_values() -> None:
    both = make(strike_iv_pctile_20d=D("0.1"))
    assert s.quality_method(*s.quality_conditions(both, CFG)) == "both"
    only_a = make()
    assert s.quality_method(*s.quality_conditions(only_a, CFG)) == "A"
    only_b = make(theoretical_price=None, strike_iv_pctile_20d=D("0.1"))
    assert s.quality_method(*s.quality_conditions(only_b, CFG)) == "B"
    none = make(theoretical_price=None)
    assert s.quality_method(*s.quality_conditions(none, CFG)) == "none"


# Stack
def test_stack_full_pass() -> None:
    r = SignalStack(CFG).evaluate(make())
    assert r.passed and r.reason is None and r.failed_layer is None
    assert (r.f0, r.f1, r.f2, r.f3, r.f4) == (True,) * 5
    assert r.quality_method == "A"


def test_stack_stops_at_first_failing_layer() -> None:
    r = SignalStack(CFG).evaluate(make(oi=10, speed_5m=None))
    assert not r.passed and r.failed_layer == 0
    assert r.reason is ReasonCode.L0_OI
    assert (r.f0, r.f1, r.f2, r.f3, r.f4) == (False, None, None, None, None)
    assert r.quality_method == "none"


def test_stack_first_predicate_wins_within_layer() -> None:
    r = SignalStack(CFG).evaluate(make(dte=5, oi=10))
    assert r.reason is ReasonCode.L0_DTE


def test_stack_layer2_cold_start_fails() -> None:
    r = SignalStack(CFG).evaluate(make(speed_5m=None))
    assert r.failed_layer == 2 and r.reason is ReasonCode.L2_SPEED_UNAVAILABLE
    assert (r.f0, r.f1, r.f2, r.f3, r.f4) == (True, True, False, None, None)


def test_stack_layer3_fail_reports_method_none() -> None:
    r = SignalStack(CFG).evaluate(make(theoretical_price=D("5")))
    assert r.failed_layer == 3 and r.f3 is False and r.f4 is None
    assert r.quality_method == "none"


def test_stack_missing_vix_fails_closed() -> None:
    r = SignalStack(CFG).evaluate(make(india_vix=None))
    assert r.reason is ReasonCode.L0_VIX_UNAVAILABLE


@pytest.mark.parametrize("hit", [True, False])
def test_watchlist_hit_carried_not_decisive(hit: bool) -> None:
    stack = SignalStack(CFG)
    good = stack.evaluate(make(watchlist_hit=hit))
    bad = stack.evaluate(make(watchlist_hit=hit, oi=1))
    assert good.passed and not bad.passed
    assert good.watchlist_hit is hit and bad.watchlist_hit is hit


def test_min_ask_qty_is_required() -> None:
    with pytest.raises(TypeError):
        SignalConfig()  # type: ignore[call-arg]  # omitting required arg on purpose

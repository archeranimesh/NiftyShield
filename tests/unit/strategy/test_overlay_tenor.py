"""Tests for the overlay tenor policy registry (YF-3)."""

from __future__ import annotations

import dataclasses
from decimal import Decimal

import pytest

from src.client.dhan_market import SpacingRateLimiter
from src.config import DEFAULT_DHAN_MIN_INTERVAL_S
from src.paper.constants import (
    STRATEGY_OVERLAY,
    STRATEGY_OVERLAY_YEARLY_CC,
    STRATEGY_OVERLAY_YEARLY_COLLAR,
    STRATEGY_OVERLAY_YEARLY_PP,
)
from src.strategy.overlay_tenor import (
    OVERLAY_TENORS,
    OverlayTenorPolicy,
    min_freshness_bound_s,
    validate_overlay_tenors,
    validate_tenor_policy,
)


def test_monthly_policy_pins_current_values() -> None:
    """Every monthly field equals the value hardcoded in the code today."""
    p = OVERLAY_TENORS["monthly"]
    assert p.expiry_type == "monthly"
    assert p.expiry_bucket == "monthly"
    assert p.cc_strategy_name == STRATEGY_OVERLAY == "paper_nifty_overlay"
    assert p.pp_strategy_name == STRATEGY_OVERLAY
    assert p.collar_strategy_name == STRATEGY_OVERLAY
    assert p.entry_min_dte == 14  # paper_3track_overlay_entry `dte < 14`
    assert p.reentry_min_dte == 14  # reentry_mixin `dte < 14`
    assert p.review_dte == 5  # exit_signals evaluate_cc `dte <= 5`
    assert p.roll_dte == 5  # evaluate_pp / main() PP roll gate
    assert p.profit_target_decay == Decimal("0.70")  # retention 0.30
    assert p.delta_stop == Decimal("0.55")
    assert p.premium_stop_multiple == Decimal("2.5")
    assert p.premium_stop_alert_only is False


def test_yearly_policy_values() -> None:
    p = OVERLAY_TENORS["yearly"]
    assert (p.expiry_type, p.expiry_bucket) == ("yearly", "yearly")
    assert (p.review_dte, p.roll_dte) == (15, 15)
    assert p.entry_min_dte == 20 and p.reentry_min_dte == 20
    assert p.profit_target_decay == Decimal("0.75")
    assert p.premium_stop_multiple == Decimal("2.5")
    assert p.premium_stop_alert_only is True


def test_yearly_delta_stop_copied_from_monthly() -> None:
    assert OVERLAY_TENORS["yearly"].delta_stop == OVERLAY_TENORS["monthly"].delta_stop


def test_yearly_entry_floor_strictly_above_exit_thresholds() -> None:
    p = OVERLAY_TENORS["yearly"]
    assert p.entry_min_dte > max(p.review_dte, p.roll_dte)
    assert p.reentry_min_dte > max(p.review_dte, p.roll_dte)


def test_yearly_has_three_distinct_names_apart_from_monthly() -> None:
    p = OVERLAY_TENORS["yearly"]
    names = {p.cc_strategy_name, p.pp_strategy_name, p.collar_strategy_name}
    assert names == {
        STRATEGY_OVERLAY_YEARLY_CC,
        STRATEGY_OVERLAY_YEARLY_PP,
        STRATEGY_OVERLAY_YEARLY_COLLAR,
    }
    assert len(names) == 3
    assert STRATEGY_OVERLAY not in names
    assert all(n.startswith("paper_") for n in names)


def test_registry_keys_match_expiry_type() -> None:
    assert set(OVERLAY_TENORS) == {"monthly", "yearly"}
    assert all(k == v.expiry_type for k, v in OVERLAY_TENORS.items())


def test_policy_is_frozen() -> None:
    with pytest.raises(dataclasses.FrozenInstanceError):
        OVERLAY_TENORS["monthly"].review_dte = 99  # type: ignore[misc]


def test_unknown_expiry_type_raises_keyerror() -> None:
    with pytest.raises(KeyError):
        OVERLAY_TENORS["weekly"]  # type: ignore[index]


def test_registry_is_read_only() -> None:
    with pytest.raises(TypeError):
        OVERLAY_TENORS["weekly"] = OVERLAY_TENORS["monthly"]  # type: ignore[index]


def test_policy_type_exported() -> None:
    assert isinstance(OVERLAY_TENORS["monthly"], OverlayTenorPolicy)


def test_only_yearly_routes_the_entry_chain() -> None:
    assert OVERLAY_TENORS["yearly"].routed_chain is True
    assert OVERLAY_TENORS["monthly"].routed_chain is False


# --- DSN-4: monitor cadence and freshness bound -------------------------------------------------


def test_monthly_cadence_pinned_to_monitor_default() -> None:
    """Monthly overlays tick at the StrategyMonitor / monitor_daemon default (90 s)."""
    p = OVERLAY_TENORS["monthly"]
    assert p.monitor_cadence_s == 90
    assert (p.greeks_cache_max_age_days, p.greeks_action_max_age_days) == (3, 1)


def test_yearly_cadence_is_hourly_with_derived_bound() -> None:
    p = OVERLAY_TENORS["yearly"]
    assert p.monitor_cadence_s == 3600
    assert p.greeks_freshness_bound_s == 7204  # 2 x 3600 + one 4 s slot
    assert (p.greeks_cache_max_age_days, p.greeks_action_max_age_days) == (3, 1)


def test_min_freshness_bound_formula() -> None:
    assert min_freshness_bound_s(3600, 4.0) == 7204
    assert min_freshness_bound_s(300, 4.0) == 604


def test_registry_passes_startup_validation() -> None:
    validate_overlay_tenors()  # default 4 s floor
    validate_overlay_tenors(dhan_min_interval_s=4.0)


def test_inconsistent_bound_rejected() -> None:
    bad = dataclasses.replace(
        OVERLAY_TENORS["yearly"], monitor_cadence_s=300, greeks_freshness_bound_s=120
    )
    with pytest.raises(ValueError, match="greeks_freshness_bound_s"):
        validate_tenor_policy(bad)


def test_bound_exactly_at_minimum_accepted() -> None:
    ok = dataclasses.replace(
        OVERLAY_TENORS["yearly"], monitor_cadence_s=300, greeks_freshness_bound_s=604
    )
    validate_tenor_policy(ok)


def test_larger_configured_floor_rejects_registry() -> None:
    """A slower configured Dhan floor can make the shipped bound too tight."""
    with pytest.raises(ValueError, match="greeks_freshness_bound_s"):
        validate_tenor_policy(OVERLAY_TENORS["yearly"], dhan_min_interval_s=1800.0)
    with pytest.raises(ValueError):
        validate_overlay_tenors(dhan_min_interval_s=1800.0)


def test_cadence_below_throttle_slot_rejected() -> None:
    bad = dataclasses.replace(
        OVERLAY_TENORS["yearly"], monitor_cadence_s=2, greeks_freshness_bound_s=7204
    )
    with pytest.raises(ValueError, match="monitor_cadence_s"):
        validate_tenor_policy(bad)


def test_non_positive_cadence_or_ages_rejected() -> None:
    with pytest.raises(ValueError):
        dataclasses.replace(OVERLAY_TENORS["yearly"], monitor_cadence_s=0)
    with pytest.raises(ValueError):
        dataclasses.replace(OVERLAY_TENORS["yearly"], greeks_action_max_age_days=0)
    with pytest.raises(ValueError, match="greeks_action_max_age_days"):
        dataclasses.replace(
            OVERLAY_TENORS["yearly"],
            greeks_cache_max_age_days=1,
            greeks_action_max_age_days=2,
        )


class _FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def time(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.now += seconds


async def test_yearly_cadence_keeps_chain_calls_at_least_one_slot_apart() -> None:
    """Cadence-driven yearly cycles plus a cron call landing mid-cycle stay >= 4 s apart."""
    clock = _FakeClock()
    limiter = SpacingRateLimiter(spacing=DEFAULT_DHAN_MIN_INTERVAL_S, clock=clock)
    cadence = OVERLAY_TENORS["yearly"].monitor_cadence_s
    grants: list[float] = []
    for _ in range(4):
        await limiter.acquire()  # monitor cycle: one chain call
        grants.append(clock.time())
        await limiter.acquire()  # a capture cron firing right behind it
        grants.append(clock.time())
        clock.now += cadence
    gaps = [b - a for a, b in zip(grants, grants[1:], strict=False)]
    assert all(g >= DEFAULT_DHAN_MIN_INTERVAL_S for g in gaps)
    assert cadence >= DEFAULT_DHAN_MIN_INTERVAL_S

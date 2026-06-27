# tests/unit/strategy/test_ic_expiry_config_v2.py
"""Structural invariant tests for IronCondorV2ExpiryConfig and IC_V2_MONTHLY preset.

Council ruling: docs/archive/council/strategy/2026-06-26_ic-v2-core-design.md Stage 3.
Story: docs/plan/ic-nifty-v2/stories.md — IC-V2-0.
"""

from dataclasses import FrozenInstanceError
from decimal import Decimal

import pytest

from src.strategy.ic_expiry_config_v2 import IC_V2_MONTHLY, IronCondorV2ExpiryConfig

# ---------------------------------------------------------------------------
# IC_V2_MONTHLY preset — field values
# ---------------------------------------------------------------------------


def test_monthly_preset_defaults() -> None:
    """IC_V2_MONTHLY must have the exact D1/D2/D3/D4 values from the council ruling."""
    cfg = IC_V2_MONTHLY

    # Identity
    assert cfg.expiry_type == "monthly"

    # D1 — short-leg deltas
    assert cfg.short_put_delta_target == Decimal("0.25")
    assert cfg.short_call_delta_target == Decimal("0.22")
    assert cfg.delta_range == Decimal("0.03")

    # D2 — wing sizing
    assert cfg.long_wing_delta_target == Decimal("0.10")
    assert cfg.long_wing_delta_floor == Decimal("0.05")
    assert cfg.long_wing_min_premium == Decimal("15"), (
        "D2 ruling requires ₹15 minimum premium for monthly long wing"
    )

    # D2 — SD sanity guard multipliers
    assert cfg.sd_width_warn_upper_multiplier == Decimal("1.5")
    assert cfg.sd_width_warn_lower_multiplier == Decimal("0.4")
    assert cfg.sd_atm_iv_multiplier == Decimal("1.25")

    # D3 — adjustment thresholds
    assert cfg.roll_warn_delta == Decimal("0.30")
    assert cfg.roll_trigger_delta == Decimal("0.35")
    assert cfg.forced_close_delta == Decimal("0.45")
    assert cfg.roll_debit_cap_fraction == Decimal("0.50")

    # D4 — DTE-tiered exit
    assert cfg.monthly_close_full_dte == 7


def test_immutability() -> None:
    """frozen=True; any field assignment must raise FrozenInstanceError."""
    with pytest.raises((FrozenInstanceError, AttributeError)):
        IC_V2_MONTHLY.short_put_delta_target = Decimal("0.99")  # type: ignore[misc]


def test_delta_range_positive() -> None:
    """delta_range must be strictly positive — a zero band would prevent all strike selection."""
    assert IC_V2_MONTHLY.delta_range > Decimal("0")


def test_max_rolls_is_one() -> None:
    """D3 ruling: max_rolls_per_side_per_cycle == 1 on the monthly preset.

    A second breach escalates to FORCED_CLOSE rather than rolling again.
    """
    assert IC_V2_MONTHLY.max_rolls_per_side_per_cycle == 1


# ---------------------------------------------------------------------------
# Class-level invariants (independent of preset values)
# ---------------------------------------------------------------------------


def test_custom_instance_creation() -> None:
    """IronCondorV2ExpiryConfig can be instantiated with only expiry_type; all
    other fields must have defaults supplied by the class definition."""
    cfg = IronCondorV2ExpiryConfig(expiry_type="monthly")
    assert cfg.expiry_type == "monthly"
    # Defaults must match class-level defaults
    assert cfg.short_put_delta_target == Decimal("0.25")
    assert cfg.long_wing_delta_target == Decimal("0.10")
    assert cfg.max_rolls_per_side_per_cycle == 1


def test_wing_delta_floor_below_target() -> None:
    """long_wing_delta_floor must be strictly below long_wing_delta_target.

    If the floor equals or exceeds the target, the only valid wing is at the
    floor itself, which defeats the adaptive wing selection logic.
    """
    assert IC_V2_MONTHLY.long_wing_delta_floor < IC_V2_MONTHLY.long_wing_delta_target


def test_roll_warn_delta_below_trigger() -> None:
    """Signal hierarchy: DELTA_WARN fires before ROLL_WING.

    roll_warn_delta must be strictly less than roll_trigger_delta so that
    the warn signal does not coincide with an action signal.
    """
    assert IC_V2_MONTHLY.roll_warn_delta < IC_V2_MONTHLY.roll_trigger_delta


def test_roll_trigger_delta_below_forced_close() -> None:
    """Signal hierarchy: ROLL_WING fires before FORCED_CLOSE.

    roll_trigger_delta must be strictly less than forced_close_delta.
    """
    assert IC_V2_MONTHLY.roll_trigger_delta < IC_V2_MONTHLY.forced_close_delta


def test_roll_debit_cap_fraction_in_valid_range() -> None:
    """roll_debit_cap_fraction must be in (0, 1].

    A fraction > 1 would allow rolling at a debit larger than the original IC
    credit, which is nonsensical — the strategy would be paying more to roll
    than it collected in the first place.  Zero would block all rolls entirely.
    """
    assert Decimal("0") < IC_V2_MONTHLY.roll_debit_cap_fraction <= Decimal("1")


def test_long_wing_min_premium_positive() -> None:
    """long_wing_min_premium must be strictly positive.

    A zero or negative floor would accept dead / worthless wings, defeating
    the D2 ruling's requirement for real convexity protection.
    """
    assert IC_V2_MONTHLY.long_wing_min_premium > Decimal("0")

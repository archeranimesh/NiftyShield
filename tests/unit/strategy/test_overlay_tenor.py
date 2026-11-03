"""Tests for the overlay tenor policy registry (YF-3)."""

from __future__ import annotations

import dataclasses
from decimal import Decimal

import pytest

from src.paper.constants import (
    STRATEGY_OVERLAY,
    STRATEGY_OVERLAY_YEARLY_CC,
    STRATEGY_OVERLAY_YEARLY_COLLAR,
    STRATEGY_OVERLAY_YEARLY_PP,
)
from src.strategy.overlay_tenor import OVERLAY_TENORS, OverlayTenorPolicy


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
    assert p.roll_dte == 5  # evaluate_pp / _PP_ROLL_DTE_THRESHOLD
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

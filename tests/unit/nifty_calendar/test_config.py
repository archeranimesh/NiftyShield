"""Unit tests for CalendarVariantConfig and MONTHLY configuration."""

from dataclasses import FrozenInstanceError
from datetime import time
from decimal import Decimal

import pytest

from src.nifty_calendar.config import MONTHLY, CalendarVariantConfig


def test_config_frozen() -> None:
    """Assert attempting to mutate any field raises FrozenInstanceError."""
    with pytest.raises(FrozenInstanceError):
        MONTHLY.lots = 2  # type: ignore[misc]

    with pytest.raises(FrozenInstanceError):
        MONTHLY.target_per_lot = Decimal("5000")  # type: ignore[misc]

    with pytest.raises(FrozenInstanceError):
        MONTHLY.name = "custom"  # type: ignore[misc]


def test_monthly_defaults_match_decisions() -> None:
    """Assert MONTHLY defaults match the documented design decisions."""
    assert isinstance(MONTHLY, CalendarVariantConfig)
    assert MONTHLY.name == "monthly"
    assert MONTHLY.strategy_name == "paper_nifty_calendar_monthly"
    assert MONTHLY.target_per_lot == Decimal("3000")
    assert MONTHLY.planned_hold_days == 7
    assert MONTHLY.hard_hold_days == 10
    assert MONTHLY.exit_by_dte == 7
    assert MONTHLY.put_wing_start_points == 600
    assert MONTHLY.call_wing_start_points == 600
    assert MONTHLY.min_wing_points == 300
    assert MONTHLY.vega_cap == Decimal("20")
    assert MONTHLY.delta_cap == Decimal("0.10")
    assert MONTHLY.risk_reward_floor == Decimal("0.75")
    assert MONTHLY.breakeven_symmetry_tolerance_pct == Decimal("0.50")
    assert MONTHLY.breakeven_loss_symmetry_tolerance == Decimal("0.25")
    assert MONTHLY.spread_tolerance == Decimal("3.0")
    assert MONTHLY.breach_confirm_minutes == 30
    assert MONTHLY.breach_adjust_window_days == 7
    assert MONTHLY.lots == 1
    assert MONTHLY.lot_size == 65
    assert MONTHLY.wing_step_points == 100
    assert MONTHLY.max_wing_search_steps == 3
    assert MONTHLY.entry_time_ist == time(10, 30)
    assert MONTHLY.hard_exit_time_ist == time(15, 15)

"""Unit tests for BIWEEKLY config and BiweeklyCyclePolicy."""

from dataclasses import FrozenInstanceError
from datetime import date, time, timedelta
from decimal import Decimal

import pytest

from src.nifty_calendar.config import BIWEEKLY, CalendarVariantConfig
from src.nifty_calendar.cycle import (
    BiweeklyCyclePolicy,
    CyclePolicy,
    MonthlyCyclePolicy,
    active_variant,
)


def _trading_days_calendar(d: date) -> bool:
    """Mock calendar where Monday-Friday are trading days (no mid-week holidays)."""
    return d.weekday() < 5


@pytest.fixture
def sample_expiries() -> tuple[list[date], list[date]]:
    """Sample weekly and monthly expiries for Sep-Nov 2026."""
    monthly = [
        date(2026, 8, 25),
        date(2026, 9, 29),
        date(2026, 10, 27),
        date(2026, 11, 23),  # Holiday shifted (Mon)
        date(2026, 12, 29),
    ]
    all_weekly = [
        date(2026, 9, 22),
        date(2026, 9, 29),
        date(2026, 10, 6),
        date(2026, 10, 13),
        date(2026, 10, 20),
        date(2026, 10, 27),
        date(2026, 11, 3),
        date(2026, 11, 10),
        date(2026, 11, 17),
        date(2026, 11, 23),
        date(2026, 12, 1),
        date(2026, 12, 8),
        date(2026, 12, 15),
        date(2026, 12, 22),
        date(2026, 12, 29),
    ]
    return all_weekly, monthly


def test_biweekly_config_defaults() -> None:
    """Assert BIWEEKLY configuration parameters match the trade research findings."""
    assert BIWEEKLY.name == "biweekly"
    assert BIWEEKLY.strategy_name == "paper_nifty_calendar_biweekly"
    assert BIWEEKLY.target_per_lot == Decimal("1600")
    assert BIWEEKLY.hard_hold_days == 7
    assert BIWEEKLY.planned_hold_days == 5
    assert BIWEEKLY.exit_by_dte == 7
    assert BIWEEKLY.put_wing_start_points == 400
    assert BIWEEKLY.call_wing_start_points == 400
    assert BIWEEKLY.min_wing_points == 300
    assert BIWEEKLY.vega_cap == Decimal("5")
    assert BIWEEKLY.delta_cap == Decimal("0.10")
    assert BIWEEKLY.risk_reward_floor == Decimal("0.75")
    assert BIWEEKLY.breach_confirm_minutes == 30
    assert BIWEEKLY.breach_adjust_window_days == 4
    assert BIWEEKLY.breach_adjust_window_days_start == 3
    assert BIWEEKLY.recentre_spot_threshold_points == 200
    assert BIWEEKLY.off_centre_window_days_start == 4
    assert BIWEEKLY.off_centre_window_days_end == 5
    assert BIWEEKLY.lots == 1
    assert BIWEEKLY.lot_size == 65
    assert BIWEEKLY.entry_time_ist == time(10, 30)
    assert BIWEEKLY.hard_exit_time_ist == time(15, 15)


def test_biweekly_config_frozen() -> None:
    """Assert CalendarVariantConfig is immutable."""
    with pytest.raises(FrozenInstanceError):
        BIWEEKLY.target_per_lot = Decimal("2000")  # type: ignore[misc]


def test_biweekly_cycle_policy_protocol(sample_expiries: tuple[list[date], list[date]]) -> None:
    """Assert BiweeklyCyclePolicy conforms to CyclePolicy runtime protocol."""
    weekly, monthly = sample_expiries
    policy = BiweeklyCyclePolicy(expiries=weekly, monthly_expiries=monthly)
    assert isinstance(policy, CyclePolicy)


def test_pair_skips_current_weekly(sample_expiries: tuple[list[date], list[date]]) -> None:
    """Assert entry selects expiry after next (skipping current weekly)."""
    weekly, monthly = sample_expiries
    entry_day = date(2026, 10, 15)  # Thursday
    policy = BiweeklyCyclePolicy(
        expiries=weekly,
        monthly_expiries=monthly,
        is_trading_day_fn=_trading_days_calendar,
        entry_dates=[entry_day],
    )
    plan = policy.entry_window(entry_day)
    assert plan is not None
    assert plan.entry_date == entry_day
    # Upcoming expiries after 15 Oct:
    # 20 Oct (skipped current weekly)
    # 27 Oct (near expiry)
    assert plan.near_expiry == date(2026, 10, 27)


def test_far_is_one_week_beyond_near(sample_expiries: tuple[list[date], list[date]]) -> None:
    """Assert far expiry is exactly one week beyond near expiry."""
    weekly, monthly = sample_expiries
    entry_day = date(2026, 10, 15)
    policy = BiweeklyCyclePolicy(
        expiries=weekly,
        monthly_expiries=monthly,
        is_trading_day_fn=_trading_days_calendar,
        entry_dates=[entry_day],
    )
    plan = policy.entry_window(entry_day)
    assert plan is not None
    assert plan.near_expiry == date(2026, 10, 27)
    assert plan.far_expiry == date(2026, 11, 3)
    assert (plan.far_expiry - plan.near_expiry).days == 7


def test_chain_stops_before_monthly_window(
    sample_expiries: tuple[list[date], list[date]],
) -> None:
    """Assert no bi-weekly entry when hard exit runs past start of next monthly entry window."""
    weekly, monthly = sample_expiries
    # Next monthly expiry is 27 Oct 2026. Next monthly entry window starts 28 Oct 2026.
    # Suppose entry was attempted late in the cycle on 23 Oct 2026 (Friday).
    # Future expiries after 23 Oct:
    # 27 Oct (skipped), 3 Nov (near), 10 Nov (far).
    # 7 trading days from 23 Oct is 3 Nov. Hard exit capped at DTE > 7 is 26 Oct.
    # If a config has hard_hold extending into 28 Oct, entry must be rejected.
    cfg_longer_hold = CalendarVariantConfig(
        name="biweekly_long",
        strategy_name="paper_nifty_calendar_biweekly",
        target_per_lot=Decimal("1600"),
        planned_hold_days=5,
        hard_hold_days=10,
        exit_by_dte=2,  # Low DTE cap allows hard exit past 28 Oct
        put_wing_start_points=400,
        call_wing_start_points=400,
        min_wing_points=300,
        vega_cap=Decimal("5"),
        delta_cap=Decimal("0.10"),
        risk_reward_floor=Decimal("0.75"),
        breakeven_symmetry_tolerance_pct=Decimal("0.50"),
        breakeven_loss_symmetry_tolerance=Decimal("0.25"),
        spread_tolerance=Decimal("3.0"),
        lot_size=65,
    )
    policy = BiweeklyCyclePolicy(
        expiries=weekly,
        monthly_expiries=monthly,
        is_trading_day_fn=_trading_days_calendar,
        config=cfg_longer_hold,
        entry_dates=[date(2026, 10, 23)],
    )
    # Hard exit would be after 28 Oct 2026 (start of next monthly window), so entry is blocked
    assert policy.entry_window(date(2026, 10, 23)) is None


def test_redeploy_keeps_original_hard_exit(
    sample_expiries: tuple[list[date], list[date]],
) -> None:
    """Assert same-pair redeployment retains original near/far pair and original hard exit date."""
    weekly, monthly = sample_expiries
    entry_day = date(2026, 10, 15)
    policy = BiweeklyCyclePolicy(
        expiries=weekly,
        monthly_expiries=monthly,
        is_trading_day_fn=_trading_days_calendar,
        entry_dates=[entry_day],
    )
    initial_plan = policy.entry_window(entry_day)
    assert initial_plan is not None

    # Redeploy on 19 Oct 2026 (e.g. after early target hit on day 2)
    redeploy_day = date(2026, 10, 19)
    redeploy_plan = policy.redeploy_plan(initial_plan, today=redeploy_day)

    assert redeploy_plan.entry_date == redeploy_day
    assert redeploy_plan.near_expiry == initial_plan.near_expiry
    assert redeploy_plan.far_expiry == initial_plan.far_expiry
    assert redeploy_plan.hard_exit_date == initial_plan.hard_exit_date
    assert redeploy_plan.variant_name == "biweekly"


def test_holiday_shifted_expiry_used() -> None:
    """Assert holiday-shifted expiries are taken from the listed sequence, not computed."""
    # 23 Nov 2026 is Monday (holiday shifted from Tuesday 24 Nov)
    weekly = [
        date(2026, 11, 10),
        date(2026, 11, 17),
        date(2026, 11, 23),  # Monday
        date(2026, 12, 1),
    ]
    monthly = [date(2026, 10, 27), date(2026, 11, 23), date(2026, 12, 29)]
    policy = BiweeklyCyclePolicy(
        expiries=weekly,
        monthly_expiries=monthly,
        is_trading_day_fn=_trading_days_calendar,
        entry_dates=[date(2026, 11, 11)],
    )
    plan = policy.entry_window(date(2026, 11, 11))
    assert plan is not None
    # 17 Nov is skipped current weekly
    # 23 Nov is near expiry (holiday shifted Monday, taken as-is)
    assert plan.near_expiry == date(2026, 11, 23)
    assert plan.far_expiry == date(2026, 12, 1)


def test_calendar_returns_one_variant_per_date_with_both_registered(
    sample_expiries: tuple[list[date], list[date]],
) -> None:
    """Assert active_variant returns at most one variant per date across a full monthly cycle."""
    weekly, monthly = sample_expiries
    m_policy = MonthlyCyclePolicy(
        monthly_expiries=monthly,
        is_trading_day_fn=_trading_days_calendar,
    )
    bw_policy = BiweeklyCyclePolicy(
        expiries=weekly,
        monthly_expiries=monthly,
        is_trading_day_fn=_trading_days_calendar,
    )

    policies = [m_policy, bw_policy]

    # Test every date from 29 Sep 2026 to 28 Oct 2026
    start = date(2026, 9, 29)
    end = date(2026, 10, 28)
    curr = start

    seen_monthly = False
    seen_biweekly = False

    while curr <= end:
        v = active_variant(curr, policies)
        m_plan = m_policy.entry_window(curr)
        bw_plan = bw_policy.entry_window(curr)

        # Mutually exclusive: never both active on the same date
        assert not (m_plan is not None and bw_plan is not None), f"Both active on {curr}"

        if m_plan is not None:
            assert v == "monthly"
            seen_monthly = True
        elif bw_plan is not None:
            assert v == "biweekly"
            seen_biweekly = True
        else:
            assert v is None

        curr += timedelta(days=1)

    assert seen_monthly, "Monthly entry was never activated"
    assert seen_biweekly, "Bi-weekly entry was never activated"


def test_next_variant_after_exit(sample_expiries: tuple[list[date], list[date]]) -> None:
    """Assert next_variant_after_exit transitions correctly between biweekly and monthly."""
    weekly, monthly = sample_expiries
    policy = BiweeklyCyclePolicy(
        expiries=weekly,
        monthly_expiries=monthly,
        is_trading_day_fn=_trading_days_calendar,
    )

    # After first bi-weekly exit in mid October: another bi-weekly fits
    assert policy.next_variant_after_exit(date(2026, 10, 16)) == "biweekly"

    # Near next monthly expiry (27 Oct): bi-weekly chain has ended
    assert policy.next_variant_after_exit(date(2026, 10, 26)) == "monthly"
    assert policy.next_variant_after_exit(date(2026, 10, 27)) == "monthly"


def test_biweekly_empty_expiries_raises() -> None:
    """Assert empty expiries or monthly_expiries raises ValueError."""
    with pytest.raises(ValueError, match="expiries must not be empty"):
        BiweeklyCyclePolicy(expiries=[])

    with pytest.raises(ValueError, match="monthly_expiries must not be empty"):
        BiweeklyCyclePolicy(expiries=[date(2026, 9, 29)], monthly_expiries=[])


def test_candidate_entry_window_continuous_from_day_7(
    sample_expiries: tuple[list[date], list[date]],
) -> None:
    """Assert entry_window opens continuously on each trading day from monthly day 7."""
    weekly, monthly = sample_expiries
    policy = BiweeklyCyclePolicy(
        expiries=weekly,
        monthly_expiries=monthly,
        is_trading_day_fn=_trading_days_calendar,
    )
    # Previous monthly expiry: 29 Sep 2026. Next monthly: 27 Oct 2026.
    # Monthly entry: 30 Sep 2026 (Wed).
    # Monthly planned exit (day 7): 9 Oct 2026 (Fri).
    # Day 6 (8 Oct) is blocked; days 7-10 (9, 12, 13, 14 Oct) are active.
    assert policy.entry_window(date(2026, 10, 8)) is None  # Day 6: blocked
    for d in [date(2026, 10, 9), date(2026, 10, 12), date(2026, 10, 13), date(2026, 10, 14)]:
        plan = policy.entry_window(d)
        assert plan is not None, f"Expected entry_window active on {d}"
        assert plan.entry_date == d

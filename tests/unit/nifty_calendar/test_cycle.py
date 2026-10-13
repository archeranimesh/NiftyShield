"""Unit tests for CyclePolicy, MonthlyCyclePolicy, and CycleCalendar."""

from datetime import date, time, timedelta

from src.market_calendar.holidays import is_trading_day
from src.nifty_calendar.cycle import (
    CycleCalendar,
    CyclePolicy,
    EntryPlan,
    MonthlyCyclePolicy,
)


def test_entry_day_after_tuesday_expiry() -> None:
    """Assert entry is the next trading day (Wed) following a Tuesday expiry."""
    expiries = [
        date(2026, 8, 25),
        date(2026, 9, 29),
        date(2026, 10, 27),
        date(2026, 11, 23),
    ]
    policy = MonthlyCyclePolicy(monthly_expiries=expiries)
    assert isinstance(policy, CyclePolicy)

    # Expiry day itself is not an entry day
    assert policy.entry_window(date(2026, 9, 29)) is None

    # First trading day strictly after 29 Sep 2026 expiry is Wed 30 Sep 2026
    plan = policy.entry_window(date(2026, 9, 30))
    assert plan is not None
    assert isinstance(plan, EntryPlan)
    assert plan.variant_name == "monthly"
    assert plan.entry_date == date(2026, 9, 30)
    assert plan.entry_time_ist == time(10, 30)
    assert plan.near_expiry == date(2026, 10, 27)
    assert plan.far_expiry == date(2026, 11, 23)
    # 7 trading days after 30 Sep: 1 Oct (1), 2 Oct holiday, 5-9 Oct (2-6), 12 Oct (7)
    assert plan.planned_exit_date == date(2026, 10, 12)
    # 10 trading days: 13-15 Oct (8-10) -> 15 Oct. DTE relative to 27 Oct is 12 > 7
    assert plan.hard_exit_date == date(2026, 10, 15)


def test_holiday_pushes_entry_forward() -> None:
    """Assert that if the day after expiry is an NSE holiday, entry pushes forward."""
    expiries = [
        date(2026, 8, 25),
        date(2026, 9, 29),
        date(2026, 10, 27),
        date(2026, 11, 23),
    ]

    def mock_trading_day_with_holiday(d: date) -> bool:
        # Simulate Wed 30 Sep 2026 as a market holiday
        if d == date(2026, 9, 30):
            return False
        return is_trading_day(d)

    policy = MonthlyCyclePolicy(
        monthly_expiries=expiries,
        is_trading_day_fn=mock_trading_day_with_holiday,
    )

    # Wednesday is a holiday, so no entry
    assert policy.entry_window(date(2026, 9, 30)) is None

    # Thursday 1 Oct 2026 is the first trading day strictly after expiry
    plan = policy.entry_window(date(2026, 10, 1))
    assert plan is not None
    assert plan.entry_date == date(2026, 10, 1)
    assert plan.near_expiry == date(2026, 10, 27)
    assert plan.far_expiry == date(2026, 11, 23)


def test_monday_holiday_shifted_expiry_nov_2026() -> None:
    """Assert that a Monday monthly expiry opens an entry window on Tuesday."""
    expiries = [
        date(2026, 10, 27),
        date(2026, 11, 23),
        date(2026, 12, 29),
        date(2027, 1, 26),
    ]

    # In a calendar where weekdays are trading days
    def weekday_calendar(d: date) -> bool:
        return d.weekday() < 5

    policy = MonthlyCyclePolicy(
        monthly_expiries=expiries,
        is_trading_day_fn=weekday_calendar,
    )

    # 23 Nov 2026 is Monday expiry
    assert policy.entry_window(date(2026, 11, 23)) is None

    # Entry is Tue 24 Nov 2026
    plan = policy.entry_window(date(2026, 11, 24))
    assert plan is not None
    assert plan.entry_date == date(2026, 11, 24)
    assert plan.near_expiry == date(2026, 12, 29)
    assert plan.far_expiry == date(2027, 1, 26)


def test_hard_exit_never_inside_dte_7() -> None:
    """Assert hard_exit_date maintains (near_expiry - hard_exit_date).days > 7."""
    # Near expiry is only 13 days after entry
    expiries = [
        date(2026, 6, 2),  # Prev expiry (Tue)
        date(2026, 6, 16),  # Near expiry (Tue, 13 calendar days after Wed entry)
        date(2026, 7, 14),  # Far expiry
    ]

    def weekday_calendar(d: date) -> bool:
        return d.weekday() < 5

    policy = MonthlyCyclePolicy(
        monthly_expiries=expiries,
        is_trading_day_fn=weekday_calendar,
    )

    # Entry is Wed 3 Jun 2026
    plan = policy.entry_window(date(2026, 6, 3))
    assert plan is not None
    # 10 trading days after 3 Jun would be 17 Jun (past expiry!).
    # Hard exit must be capped strictly before DTE 7:
    # (16 Jun - hard_exit_date).days > 7 => days >= 8 => hard_exit <= 8 Jun (Mon)
    dte_at_hard_exit = (plan.near_expiry - plan.hard_exit_date).days
    assert dte_at_hard_exit > 7
    assert plan.hard_exit_date < plan.near_expiry
    assert plan.hard_exit_date == date(2026, 6, 8)


def test_exactly_one_active_variant_per_date() -> None:
    """Assert CycleCalendar returns 'monthly' on valid entry days and None on others."""
    expiries = [
        date(2026, 8, 25),
        date(2026, 9, 29),
        date(2026, 10, 27),
        date(2026, 11, 23),
    ]
    policy = MonthlyCyclePolicy(monthly_expiries=expiries)
    policies_seq = [policy]
    policies_map = {"monthly": policy}

    entry_day = date(2026, 9, 30)

    # Valid entry day
    assert CycleCalendar.active_variant(entry_day, policies_seq) == "monthly"
    assert CycleCalendar.active_variant(entry_day, policies_map) == "monthly"

    # Non-entry days across the surrounding window
    for delta in range(-7, 14):
        test_day = entry_day + timedelta(days=delta)
        if test_day == entry_day:
            continue
        assert CycleCalendar.active_variant(test_day, policies_seq) is None
        assert CycleCalendar.active_variant(test_day, policies_map) is None


def test_next_variant_after_exit() -> None:
    """Assert next_variant_after_exit returns 'biweekly'."""
    expiries = [
        date(2026, 8, 25),
        date(2026, 9, 29),
        date(2026, 10, 27),
    ]
    policy = MonthlyCyclePolicy(monthly_expiries=expiries)
    assert policy.next_variant_after_exit(date(2026, 10, 15)) == "biweekly"
    assert policy.next_variant_after_exit(date(2026, 10, 28)) == "biweekly"

"""Unit tests for monthly expiry derivation (rule for settled months, listing for the rest)."""

from __future__ import annotations

from datetime import date

from src.nifty_calendar.cycle import MonthlyCyclePolicy
from src.nifty_calendar.expiries import monthly_expiries


def _weekdays(d: date) -> bool:
    return d.weekday() < 5


LISTED = [date(2026, 10, 27), date(2026, 11, 3), date(2026, 11, 9), date(2026, 11, 23),
          date(2026, 12, 29)]  # fmt: skip


def test_settled_months_come_from_rule_and_future_from_last_listed() -> None:
    # 2026-10-27 has settled and dropped out of the BOD listing by this morning.
    out = monthly_expiries(LISTED[1:], date(2026, 10, 28), _weekdays)
    assert out == [date(2026, 8, 25), date(2026, 9, 29), date(2026, 10, 27),
                   date(2026, 11, 23), date(2026, 12, 29)]  # fmt: skip


def test_entry_window_opens_the_session_after_a_settled_expiry() -> None:
    policy = MonthlyCyclePolicy(monthly_expiries(LISTED[1:], date(2026, 10, 28), _weekdays))
    plan = policy.entry_window(date(2026, 10, 28))
    assert plan is not None
    assert (plan.near_expiry, plan.far_expiry) == (date(2026, 11, 23), date(2026, 12, 29))


def test_rule_expiry_moves_back_over_a_holiday() -> None:
    def holiday_sep_29(d: date) -> bool:
        return d.weekday() < 5 and d != date(2026, 9, 29)

    out = monthly_expiries([date(2026, 11, 23)], date(2026, 10, 1), holiday_sep_29)
    assert date(2026, 9, 28) in out and date(2026, 9, 29) not in out


def test_listed_expiry_wins_over_rule_in_an_unsettled_month() -> None:
    # Nov 24 (last Tuesday) is a holiday-shifted Monday the 23rd in the listing.
    assert monthly_expiries([date(2026, 11, 3), date(2026, 11, 23)], date(2026, 11, 1), _weekdays)[
        -1
    ] == date(2026, 11, 23)


def test_past_listed_dates_are_ignored_and_empty_listing_yields_only_settled() -> None:
    out = monthly_expiries([date(2026, 1, 1)], date(2026, 10, 28), _weekdays)
    assert out == [date(2026, 8, 25), date(2026, 9, 29), date(2026, 10, 27)]

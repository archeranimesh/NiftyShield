"""Monthly Nifty expiry dates for the cycle policy, past and future."""

import calendar
from collections.abc import Callable, Iterable
from datetime import date, timedelta

from src.market_calendar.holidays import is_trading_day

__all__ = ["monthly_expiries"]

_LOOKBACK_MONTHS = 2


def _rule_expiry(year: int, month: int, trading_day: Callable[[date], bool]) -> date:
    """Last Tuesday of the month, moved back to the previous trading day on a holiday."""
    last = date(year, month, calendar.monthrange(year, month)[1])
    expiry = last - timedelta(days=(last.weekday() - 1) % 7)
    while not trading_day(expiry):
        expiry -= timedelta(days=1)
    return expiry


def _months_back(today: date, count: int) -> list[tuple[int, int]]:
    out, year, month = [], today.year, today.month
    for _ in range(count + 1):
        out.append((year, month))
        year, month = (year, month - 1) if month > 1 else (year - 1, 12)
    return out


def monthly_expiries(
    listed: Iterable[date],
    today: date,
    trading_day: Callable[[date], bool] = is_trading_day,
) -> list[date]:
    """Sorted monthly expiries: rule-derived for settled months, listed for the rest.

    The BOD instrument file drops a contract once it settles, but the entry window opens
    the session after the previous monthly expiry, so that expiry must still be known.
    Settled months therefore come from the expiry rule (last Tuesday, holiday-shifted back);
    months not yet settled take the last listed expiry in the month, which is authoritative.

    Args:
        listed: Every listed NIFTY option expiry.
        today: The date being evaluated.
        trading_day: True for an NSE trading day.

    Returns:
        Sorted distinct monthly expiry dates.
    """
    last_listed: dict[tuple[int, int], date] = {}
    for d in listed:
        if d >= today and d > last_listed.get((d.year, d.month), date.min):
            last_listed[(d.year, d.month)] = d
    settled = {
        e
        for y, m in _months_back(today, _LOOKBACK_MONTHS)
        if (e := _rule_expiry(y, m, trading_day)) < today
    }
    return sorted(settled | set(last_listed.values()))

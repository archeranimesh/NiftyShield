"""Cycle policies and calendar scheduling for Nifty calendar spreads."""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, time, timedelta
from typing import Protocol, runtime_checkable

from src.market_calendar.holidays import is_trading_day
from src.nifty_calendar.config import MONTHLY, CalendarVariantConfig

__all__ = [
    "CycleCalendar",
    "CyclePolicy",
    "EntryPlan",
    "MonthlyCyclePolicy",
]


@dataclass(frozen=True)
class EntryPlan:
    """Execution plan for opening a calendar spread position.

    Attributes:
        variant_name: Strategy variant identifier (e.g. 'monthly', 'biweekly').
        entry_date: Target entry date.
        entry_time_ist: Target entry time in IST.
        near_expiry: Expiry date of the short near-month legs.
        far_expiry: Expiry date of the long far-month legs.
        planned_exit_date: Standard planned exit date (entry + planned hold days).
        hard_exit_date: Mandatory exit date before expiry (capped before DTE limit).
    """

    variant_name: str
    entry_date: date
    entry_time_ist: time
    near_expiry: date
    far_expiry: date
    planned_exit_date: date
    hard_exit_date: date


@runtime_checkable
class CyclePolicy(Protocol):
    """Protocol for calendar spread cycle policies."""

    def entry_window(self, today: date) -> EntryPlan | None:
        """Return the entry plan if today is an entry day for this policy, else None.

        Args:
            today: The current date being evaluated.

        Returns:
            An EntryPlan if today is a valid entry day, otherwise None.
        """
        ...

    def next_variant_after_exit(self, today: date) -> str | None:
        """Return the name of the next variant to evaluate after exit, or None.

        Args:
            today: The date on which exit occurred.

        Returns:
            The name of the next variant (e.g. 'biweekly'), or None.
        """
        ...


class MonthlyCyclePolicy:
    """Monthly calendar cycle policy.

    Governs cycle entry and planned hold windows for the monthly calendar variant.
    Entry occurs on the first trading day strictly after a previous monthly expiry.
    """

    def __init__(
        self,
        monthly_expiries: Sequence[date],
        is_trading_day_fn: Callable[[date], bool] = is_trading_day,
        config: CalendarVariantConfig = MONTHLY,
    ) -> None:
        """Initialize the MonthlyCyclePolicy.

        Args:
            monthly_expiries: Sorted distinct monthly expiry dates.
            is_trading_day_fn: Callable returning True if a date is a trading day.
            config: Calendar variant configuration instance.

        Raises:
            ValueError: If monthly_expiries is not sorted or contains duplicates.
        """
        expiries_list = list(monthly_expiries)
        if expiries_list != sorted(set(expiries_list)):
            raise ValueError("monthly_expiries must be sorted distinct dates")

        self._monthly_expiries: tuple[date, ...] = tuple(expiries_list)
        self._is_trading_day_fn: Callable[[date], bool] = is_trading_day_fn
        self._config: CalendarVariantConfig = config

    def _next_trading_day(self, d: date) -> date:
        """Return the first trading day strictly after d."""
        candidate = d + timedelta(days=1)
        while not self._is_trading_day_fn(candidate):
            candidate += timedelta(days=1)
        return candidate

    def _add_trading_days(self, start: date, days: int) -> date:
        """Walk forward by a specified number of trading days from start."""
        curr = start
        added = 0
        while added < days:
            curr += timedelta(days=1)
            if self._is_trading_day_fn(curr):
                added += 1
        return curr

    def entry_window(self, today: date) -> EntryPlan | None:
        """Return EntryPlan if today is the entry day following an expiry, else None.

        Args:
            today: Date to evaluate.

        Returns:
            EntryPlan if today is the entry day following a monthly expiry, else None.
        """
        matched_prev: date | None = None
        for prev_expiry in self._monthly_expiries:
            if self._next_trading_day(prev_expiry) == today:
                matched_prev = prev_expiry
                break

        if matched_prev is None:
            return None

        future_expiries = [exp for exp in self._monthly_expiries if exp > today]
        if len(future_expiries) < 2:
            return None

        near_expiry = future_expiries[0]
        far_expiry = future_expiries[1]

        planned_exit = self._add_trading_days(today, self._config.planned_hold_days)
        tentative_hard_exit = self._add_trading_days(today, self._config.hard_hold_days)

        # Cap hard exit so (near_expiry - hard_exit_date).days > exit_by_dte (never inside DTE 7)
        latest_allowed = near_expiry - timedelta(days=self._config.exit_by_dte + 1)
        while not self._is_trading_day_fn(latest_allowed):
            latest_allowed -= timedelta(days=1)

        hard_exit = min(tentative_hard_exit, latest_allowed)

        return EntryPlan(
            variant_name=self._config.name,
            entry_date=today,
            entry_time_ist=self._config.entry_time_ist,
            near_expiry=near_expiry,
            far_expiry=far_expiry,
            planned_exit_date=planned_exit,
            hard_exit_date=hard_exit,
        )

    def next_variant_after_exit(self, today: date) -> str | None:
        """Return the next variant to consider after exit.

        Args:
            today: Date when exit occurred.

        Returns:
            'biweekly' for the monthly policy.
        """
        return "biweekly"


class CycleCalendar:
    """Evaluates active calendar spread variants across policies."""

    @staticmethod
    def active_variant(
        today: date,
        policies: Sequence[CyclePolicy] | Mapping[str, CyclePolicy],
    ) -> str | None:
        """Return the variant name of the policy whose entry window is active.

        Args:
            today: Date to check.
            policies: Sequence or mapping of CyclePolicy instances.

        Returns:
            The variant name if an entry window is active, otherwise None.
        """
        policy_list = policies.values() if isinstance(policies, Mapping) else policies
        for policy in policy_list:
            plan = policy.entry_window(today)
            if plan is not None:
                return plan.variant_name
        return None

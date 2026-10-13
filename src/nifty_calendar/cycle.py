"""Cycle policies and calendar scheduling for Nifty calendar spreads."""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, time, timedelta
from typing import Protocol, runtime_checkable

from src.market_calendar.holidays import is_trading_day
from src.nifty_calendar.config import BIWEEKLY, MONTHLY, CalendarVariantConfig
from src.nifty_calendar.expiries import monthly_expiries as derive_monthly_expiries

__all__ = [
    "BiweeklyCyclePolicy",
    "CyclePolicy",
    "EntryPlan",
    "MonthlyCyclePolicy",
    "active_variant",
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
    """Protocol for calendar spread cycle policies.

    A policy may also define ``redeploy_plan(current_plan, today) -> EntryPlan``. It is optional and
    deliberately off the protocol: ``NiftyCalendarV1.cycle_plan`` detects it with ``hasattr`` and, when
    present, uses it so a re-centre or same-pair redeploy keeps the original expiries and hard exit.
    Renaming it silently disables that path, so keep the name in step with ``cycle_plan``.
    """

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


class BiweeklyCyclePolicy:
    """Bi-weekly calendar cycle policy.

    Governs cycle entry, skip-current-weekly pair selection, planned hold windows,
    and same-pair redeployment for the bi-weekly calendar variant.
    """

    def __init__(
        self,
        expiries: Sequence[date],
        monthly_expiries: Sequence[date] | None = None,
        is_trading_day_fn: Callable[[date], bool] = is_trading_day,
        config: CalendarVariantConfig = BIWEEKLY,
        monthly_config: CalendarVariantConfig = MONTHLY,
        entry_dates: Sequence[date] | None = None,
    ) -> None:
        """Initialize the BiweeklyCyclePolicy.

        Args:
            expiries: Sorted distinct listed option expiry dates (weekly and monthly).
            monthly_expiries: Optional sorted distinct monthly expiry dates. If omitted,
                derived from `expiries`.
            is_trading_day_fn: Callable returning True if a date is an NSE trading day.
            config: Bi-weekly variant configuration instance (defaults to BIWEEKLY).
            monthly_config: Monthly variant configuration instance (defaults to MONTHLY).
            entry_dates: Optional explicit allowed entry dates. If None, candidate entry
                dates are derived from the monthly exit days and bi-weekly hold intervals.

        Raises:
            ValueError: If expiries is not sorted or contains duplicates.
        """
        expiries_list = list(expiries)
        if not expiries_list:
            raise ValueError("expiries must not be empty")
        if expiries_list != sorted(set(expiries_list)):
            raise ValueError("expiries must be sorted distinct dates")

        self._all_expiries: tuple[date, ...] = tuple(expiries_list)
        self._is_trading_day_fn: Callable[[date], bool] = is_trading_day_fn
        self._config: CalendarVariantConfig = config
        self._monthly_config: CalendarVariantConfig = monthly_config

        if monthly_expiries is not None:
            m_list = list(monthly_expiries)
            if not m_list:
                raise ValueError("monthly_expiries must not be empty")
            if m_list != sorted(set(m_list)):
                raise ValueError("monthly_expiries must be sorted distinct dates")
            self._monthly_expiries: tuple[date, ...] = tuple(m_list)
        else:
            earliest = expiries_list[0]
            self._monthly_expiries = tuple(
                derive_monthly_expiries(expiries_list, earliest, is_trading_day_fn)
            )

        self._entry_dates: tuple[date, ...] | None = (
            tuple(entry_dates) if entry_dates is not None else None
        )
        # Inputs are immutable, so the derived window is computed once, not per entry_window call.
        self._candidates: frozenset[date] = (
            frozenset() if entry_dates is not None else frozenset(self._candidate_entry_dates())
        )

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

    def _candidate_entry_dates(self) -> set[date]:
        """Compute the set of eligible entry dates based on cycle handoffs."""
        candidates: set[date] = set()
        for i, prev_m in enumerate(self._monthly_expiries[:-1]):
            next_m = self._monthly_expiries[i + 1]
            m_entry = self._next_trading_day(prev_m)
            earliest_bw_entry = self._add_trading_days(
                m_entry, self._monthly_config.planned_hold_days
            )
            curr = earliest_bw_entry
            while curr < next_m:
                candidates.add(curr)
                curr = self._next_trading_day(curr)
        return candidates

    def entry_window(self, today: date) -> EntryPlan | None:
        """Return EntryPlan if today is an active bi-weekly entry day, else None.

        Near expiry = weekly expiry after next (skips current weekly).
        Far expiry = one week beyond near expiry.
        Hard exit is capped before near DTE 7.
        Entry is rejected if hard exit runs past the start of the next monthly entry window.

        Args:
            today: Date to evaluate.

        Returns:
            An EntryPlan if today is a valid entry day, otherwise None.
        """
        # Determine the monthly cycle today falls in
        prev_monthly_expiries = [e for e in self._monthly_expiries if e < today]
        if not prev_monthly_expiries:
            return None
        prev_m = prev_monthly_expiries[-1]
        m_entry = self._next_trading_day(prev_m)
        earliest_bw_entry = self._add_trading_days(m_entry, self._monthly_config.planned_hold_days)
        if today < earliest_bw_entry:
            return None

        if self._entry_dates is not None:
            if today not in self._entry_dates:
                return None
        else:
            if today not in self._candidates:
                return None

        next_monthly_expiries = [e for e in self._monthly_expiries if e > today]
        if not next_monthly_expiries:
            return None

        next_monthly_expiry = next_monthly_expiries[0]
        next_monthly_entry_window_start = self._next_trading_day(next_monthly_expiry)
        if today >= next_monthly_expiry:
            return None

        future_expiries = [e for e in self._all_expiries if e > today]
        if len(future_expiries) < 3:
            return None

        near_expiry = future_expiries[1]
        far_expiry = future_expiries[2]

        planned_exit = self._add_trading_days(today, self._config.planned_hold_days)
        tentative_hard_exit = self._add_trading_days(today, self._config.hard_hold_days)

        latest_allowed = near_expiry - timedelta(days=self._config.exit_by_dte + 1)
        while not self._is_trading_day_fn(latest_allowed):
            latest_allowed -= timedelta(days=1)

        hard_exit = min(tentative_hard_exit, latest_allowed)
        if hard_exit < today or hard_exit >= next_monthly_entry_window_start:
            return None

        return EntryPlan(
            variant_name=self._config.name,
            entry_date=today,
            entry_time_ist=self._config.entry_time_ist,
            near_expiry=near_expiry,
            far_expiry=far_expiry,
            planned_exit_date=planned_exit,
            hard_exit_date=hard_exit,
        )

    def redeploy_plan(self, current_plan: EntryPlan, today: date) -> EntryPlan:
        """Return a same-pair redeploy plan retaining near/far expiry and original hard exit date.

        Args:
            current_plan: The active cycle's EntryPlan.
            today: Date of redeployment.

        Returns:
            An EntryPlan with current date as entry_date, but retaining the original
            near_expiry, far_expiry, and hard_exit_date.
        """
        return EntryPlan(
            variant_name=self._config.name,
            entry_date=today,
            entry_time_ist=self._config.entry_time_ist,
            near_expiry=current_plan.near_expiry,
            far_expiry=current_plan.far_expiry,
            planned_exit_date=min(
                self._add_trading_days(today, self._config.planned_hold_days),
                current_plan.hard_exit_date,
            ),
            hard_exit_date=current_plan.hard_exit_date,
        )

    def next_variant_after_exit(self, today: date) -> str | None:
        """Return the next variant to consider after exit.

        Returns 'biweekly' if another bi-weekly entry can fit before the next monthly
        entry window, else 'monthly'.
        """
        if today in self._monthly_expiries:
            return "monthly"

        next_m_exp = next((e for e in self._monthly_expiries if e > today), None)
        if next_m_exp is None or today >= next_m_exp:
            return "monthly"
        next_m_entry = self._next_trading_day(next_m_exp)

        # Check if next bi-weekly's hold would extend into the monthly window
        tentative_hard_exit = self._add_trading_days(today, self._config.hard_hold_days)
        if tentative_hard_exit >= next_m_entry:
            return "monthly"
        return "biweekly"


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

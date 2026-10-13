"""Exit rules and protocols for Nifty calendar spreads."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Protocol, runtime_checkable
from zoneinfo import ZoneInfo

import structlog

from src.nifty_calendar.config import BIWEEKLY, MONTHLY, CalendarVariantConfig
from src.nifty_calendar.cycle import EntryPlan

logger = structlog.stdlib.get_logger(__name__)

_IST = ZoneInfo("Asia/Kolkata")


class ExitDecision(str, Enum):
    """Exit decision emitted by exit rule evaluation."""

    HOLD = "HOLD"
    TARGET = "TARGET"
    RECENTRE = "RECENTRE"
    CLOSE_BREACH_LATE = "CLOSE_BREACH_LATE"
    TIME_EXIT = "TIME_EXIT"
    DTE_GUARD = "DTE_GUARD"
    REDEPLOY_SAME_PAIR = "REDEPLOY_SAME_PAIR"
    RECENTRE_OFF_CENTRE = "RECENTRE_OFF_CENTRE"


@dataclass(frozen=True)
class CycleExitState:
    """State of an open cycle relevant to exit decisions.

    Attributes:
        entry_date: Date the position was opened.
        entry_spot: Underlying spot index price at entry.
        entry_short_strike: Short strike price opened at entry.
        plan: The original entry plan governing this cycle.
        target_pnl: Target profit in rupees for the entire position.
    """

    entry_date: date
    entry_spot: Decimal
    entry_short_strike: Decimal
    plan: EntryPlan
    target_pnl: Decimal


@dataclass(frozen=True)
class ExitSnapshot:
    """Market and position snapshot evaluated for exit conditions.

    Attributes:
        spot: Current underlying index spot price.
        spot_closes: Chronological series of (timestamp, spot) recent closes.
        executable_pnl: Mark-to-market P&L in rupees based on executable bid/ask.
        breakeven_low: Lower breakeven spot price of the structure.
        breakeven_high: Upper breakeven spot price of the structure.
        ltp_pnl: Optional mark-to-market P&L based on raw LTP.
    """

    spot: Decimal
    spot_closes: tuple[tuple[datetime, Decimal], ...]
    executable_pnl: Decimal
    breakeven_low: Decimal
    breakeven_high: Decimal
    ltp_pnl: Decimal | None = None

    def __post_init__(self) -> None:
        """Ensure spot_closes is an immutable tuple of tuples."""
        if not isinstance(self.spot_closes, tuple) or any(
            not isinstance(item, tuple) for item in self.spot_closes
        ):
            converted = tuple(
                (item[0], item[1]) if not isinstance(item, tuple) else item
                for item in self.spot_closes
            )
            object.__setattr__(self, "spot_closes", converted)


@runtime_checkable
class ExitRule(Protocol):
    """Protocol for calendar spread exit evaluation."""

    def evaluate(
        self,
        state: CycleExitState,
        snapshot: ExitSnapshot,
        now: datetime,
    ) -> ExitDecision:
        """Evaluate exit rules against current state and snapshot.

        Args:
            state: Open cycle state.
            snapshot: Current market and position snapshot.
            now: Current timestamp (must be timezone-aware).

        Returns:
            ExitDecision determining whether to hold, take profit, recentre, or exit.
        """
        ...


class MonthlyExitRule:
    """Exit rule implementation for the monthly calendar variant.

    Enforces strict priority order:
    1. DTE guard (exit if near leg DTE <= exit_by_dte)
    2. Time exit (exit if past hard exit date/time)
    3. Target profit (based strictly on executable_pnl, ignoring LTP)
    4. Confirmed breakeven breach (recentre before breach_adjust_window_days, else close)
    5. Hold
    """

    def __init__(self, config: CalendarVariantConfig = MONTHLY) -> None:
        """Initialize MonthlyExitRule with variant configuration.

        Args:
            config: Calendar variant configuration (defaults to MONTHLY).
        """
        self.config = config

    def evaluate(
        self,
        state: CycleExitState,
        snapshot: ExitSnapshot,
        now: datetime,
    ) -> ExitDecision:
        """Evaluate exit conditions for a monthly calendar spread.

        Args:
            state: Cycle exit state including entry details and target PnL.
            snapshot: Current market and position snapshot.
            now: Current timestamp (must be timezone-aware).

        Returns:
            ExitDecision indicating the required action.

        Raises:
            ValueError: If `now` or any timestamp in `snapshot.spot_closes` is naive.
        """
        if now.tzinfo is None or now.tzinfo.utcoffset(now) is None:
            raise ValueError("now must be timezone-aware datetime")

        for ts, _ in snapshot.spot_closes:
            if ts.tzinfo is None or ts.tzinfo.utcoffset(ts) is None:
                raise ValueError("spot_closes timestamps must be timezone-aware")

        now_ist = now.astimezone(_IST)

        # 1. DTE_GUARD
        dte = (state.plan.near_expiry - now_ist.date()).days
        if dte <= self.config.exit_by_dte:
            return ExitDecision.DTE_GUARD

        # 2. TIME_EXIT
        if now_ist.date() > state.plan.hard_exit_date or (
            now_ist.date() == state.plan.hard_exit_date
            and now_ist.time() >= self.config.hard_exit_time_ist
        ):
            return ExitDecision.TIME_EXIT

        # 3. TARGET (executable_pnl only, ltp_pnl is ignored)
        if snapshot.executable_pnl >= state.target_pnl:
            if now_ist.date() <= state.entry_date:
                logger.warning(
                    "monthly_exit_rule.first_day_target_hit",
                    entry_date=state.entry_date.isoformat(),
                    executable_pnl=str(snapshot.executable_pnl),
                    target_pnl=str(state.target_pnl),
                )
            return ExitDecision.TARGET

        # 4. Confirmed Breach
        n_minutes = self.config.breach_confirm_minutes
        window_delta = timedelta(minutes=n_minutes)
        window_start = now_ist - window_delta

        window_entries = [
            (ts.astimezone(_IST), s)
            for ts, s in snapshot.spot_closes
            if window_start <= ts.astimezone(_IST) <= now_ist
        ]

        if len(window_entries) >= 2:
            earliest_ts = min(ts for ts, _ in window_entries)
            latest_ts = max(ts for ts, _ in window_entries)
            if latest_ts - earliest_ts >= window_delta:
                low_breach = (
                    all(s < snapshot.breakeven_low for _, s in window_entries)
                    and snapshot.spot < snapshot.breakeven_low
                )
                high_breach = (
                    all(s > snapshot.breakeven_high for _, s in window_entries)
                    and snapshot.spot > snapshot.breakeven_high
                )
                if low_breach or high_breach:
                    days_held = (now_ist.date() - state.entry_date).days
                    if days_held < self.config.breach_adjust_window_days:
                        return ExitDecision.RECENTRE
                    return ExitDecision.CLOSE_BREACH_LATE

        # 5. HOLD
        return ExitDecision.HOLD


class BiweeklyExitRule:
    """Exit rule implementation for the bi-weekly calendar variant.

    Enforces strict priority order:
    1. DTE guard (exit if near leg DTE <= exit_by_dte)
    2. Time exit (exit if past hard exit date/time)
    3. Target profit (executable_pnl >= target_pnl; redeploy if DTE > exit_by_dte, else close)
    4. Confirmed breakeven breach:
       - Days held < breach_adjust_window_days_start: HOLD (pending Animesh confirmation)
       - Days held in [breach_adjust_window_days_start, breach_adjust_window_days]: RECENTRE
       - Days held > breach_adjust_window_days: CLOSE_BREACH_LATE
    5. Off-centre spot drift on hold days [off_centre_window_days_start, off_centre_window_days_end]:
       - abs(spot - entry_short_strike) >= recentre_spot_threshold_points: RECENTRE_OFF_CENTRE
    6. Hold
    """

    def __init__(self, config: CalendarVariantConfig = BIWEEKLY) -> None:
        """Initialize BiweeklyExitRule with variant configuration.

        Args:
            config: Calendar variant configuration (defaults to BIWEEKLY).
        """
        self.config = config

    def evaluate(
        self,
        state: CycleExitState,
        snapshot: ExitSnapshot,
        now: datetime,
    ) -> ExitDecision:
        """Evaluate exit conditions for a bi-weekly calendar spread.

        Args:
            state: Cycle exit state including entry details and target PnL.
            snapshot: Current market and position snapshot.
            now: Current timestamp (must be timezone-aware).

        Returns:
            ExitDecision indicating the required action.

        Raises:
            ValueError: If `now` or any timestamp in `snapshot.spot_closes` is naive.
        """
        if now.tzinfo is None or now.tzinfo.utcoffset(now) is None:
            raise ValueError("now must be timezone-aware datetime")

        for ts, _ in snapshot.spot_closes:
            if ts.tzinfo is None or ts.tzinfo.utcoffset(ts) is None:
                raise ValueError("spot_closes timestamps must be timezone-aware")

        now_ist = now.astimezone(_IST)

        # 1. DTE_GUARD
        dte = (state.plan.near_expiry - now_ist.date()).days
        if dte <= self.config.exit_by_dte:
            return ExitDecision.DTE_GUARD

        # 2. TIME_EXIT
        if now_ist.date() > state.plan.hard_exit_date or (
            now_ist.date() == state.plan.hard_exit_date
            and now_ist.time() >= self.config.hard_exit_time_ist
        ):
            return ExitDecision.TIME_EXIT

        # 3. TARGET (executable_pnl only, ltp_pnl is ignored)
        if snapshot.executable_pnl >= state.target_pnl:
            if now_ist.date() <= state.entry_date:
                logger.warning(
                    "biweekly_exit_rule.first_day_target_hit",
                    entry_date=state.entry_date.isoformat(),
                    executable_pnl=str(snapshot.executable_pnl),
                    target_pnl=str(state.target_pnl),
                )
            if dte > self.config.exit_by_dte:
                return ExitDecision.REDEPLOY_SAME_PAIR
            return ExitDecision.TARGET

        # 4. Confirmed Breach
        n_minutes = self.config.breach_confirm_minutes
        window_delta = timedelta(minutes=n_minutes)
        window_start = now_ist - window_delta

        window_entries = [
            (ts.astimezone(_IST), s)
            for ts, s in snapshot.spot_closes
            if window_start <= ts.astimezone(_IST) <= now_ist
        ]

        if len(window_entries) >= 2:
            earliest_ts = min(ts for ts, _ in window_entries)
            latest_ts = max(ts for ts, _ in window_entries)
            if latest_ts - earliest_ts >= window_delta:
                low_breach = (
                    all(s < snapshot.breakeven_low for _, s in window_entries)
                    and snapshot.spot < snapshot.breakeven_low
                )
                high_breach = (
                    all(s > snapshot.breakeven_high for _, s in window_entries)
                    and snapshot.spot > snapshot.breakeven_high
                )
                if low_breach or high_breach:
                    days_held = (now_ist.date() - state.entry_date).days
                    if days_held < self.config.breach_adjust_window_days_start:
                        # Breach before day 3: HOLD until adjustment window opens
                        pass
                    elif days_held <= self.config.breach_adjust_window_days:
                        return ExitDecision.RECENTRE
                    else:
                        return ExitDecision.CLOSE_BREACH_LATE

        # 5. Off-centre spot drift on day 4-5
        days_held = (now_ist.date() - state.entry_date).days
        if (
            self.config.off_centre_window_days_start
            <= days_held
            <= self.config.off_centre_window_days_end
        ):
            drift = abs(snapshot.spot - state.entry_short_strike)
            if drift >= self.config.recentre_spot_threshold_points:
                return ExitDecision.RECENTRE_OFF_CENTRE

        # 6. HOLD
        return ExitDecision.HOLD

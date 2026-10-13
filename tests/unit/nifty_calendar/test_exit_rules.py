"""Unit tests for ExitRule protocol and MonthlyExitRule."""

from datetime import date, datetime, time
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
import structlog.testing

from src.nifty_calendar.cycle import EntryPlan
from src.nifty_calendar.exit_rules import (
    CycleExitState,
    ExitDecision,
    ExitRule,
    ExitSnapshot,
    MonthlyExitRule,
)

IST = ZoneInfo("Asia/Kolkata")


def _make_plan(
    entry_date: date = date(2026, 10, 28),
    near_expiry: date = date(2026, 11, 24),
    far_expiry: date = date(2026, 12, 29),
    planned_exit_date: date = date(2026, 11, 6),
    hard_exit_date: date = date(2026, 11, 11),
    entry_time_ist: time = time(10, 30),
    variant_name: str = "monthly",
) -> EntryPlan:
    """Build a valid EntryPlan helper for testing."""
    return EntryPlan(
        variant_name=variant_name,
        entry_date=entry_date,
        entry_time_ist=entry_time_ist,
        near_expiry=near_expiry,
        far_expiry=far_expiry,
        planned_exit_date=planned_exit_date,
        hard_exit_date=hard_exit_date,
    )


def _make_state(
    entry_date: date = date(2026, 10, 28),
    entry_spot: Decimal = Decimal("24500"),
    entry_short_strike: Decimal = Decimal("24500"),
    target_pnl: Decimal = Decimal("3000"),
    plan: EntryPlan | None = None,
) -> CycleExitState:
    """Build a valid CycleExitState helper for testing."""
    if plan is None:
        plan = _make_plan(entry_date=entry_date)
    return CycleExitState(
        entry_date=entry_date,
        entry_spot=entry_spot,
        entry_short_strike=entry_short_strike,
        plan=plan,
        target_pnl=target_pnl,
    )


def _make_snapshot(
    spot: Decimal = Decimal("24500"),
    spot_closes: tuple[tuple[datetime, Decimal], ...] = (),
    executable_pnl: Decimal = Decimal("500"),
    breakeven_low: Decimal = Decimal("24100"),
    breakeven_high: Decimal = Decimal("24900"),
    ltp_pnl: Decimal | None = None,
) -> ExitSnapshot:
    """Build a valid ExitSnapshot helper for testing."""
    return ExitSnapshot(
        spot=spot,
        spot_closes=spot_closes,
        executable_pnl=executable_pnl,
        breakeven_low=breakeven_low,
        breakeven_high=breakeven_high,
        ltp_pnl=ltp_pnl,
    )


def test_decision_hold() -> None:
    """Position within normal bounds and time horizon evaluates to HOLD."""
    rule = MonthlyExitRule()
    assert isinstance(rule, ExitRule)
    state = _make_state(entry_date=date(2026, 10, 28))
    now = datetime(2026, 10, 30, 11, 0, tzinfo=IST)
    snapshot = _make_snapshot(
        spot=Decimal("24500"),
        executable_pnl=Decimal("1200"),
    )
    decision = rule.evaluate(state, snapshot, now)
    assert decision == ExitDecision.HOLD


def test_decision_target() -> None:
    """Executable PnL meeting or exceeding target evaluates to TARGET."""
    rule = MonthlyExitRule()
    state = _make_state(
        entry_date=date(2026, 10, 28),
        target_pnl=Decimal("3000"),
    )
    now = datetime(2026, 10, 30, 11, 0, tzinfo=IST)

    snapshot_met = _make_snapshot(
        executable_pnl=Decimal("3000"),
    )
    assert rule.evaluate(state, snapshot_met, now) == ExitDecision.TARGET

    snapshot_exceeded = _make_snapshot(
        executable_pnl=Decimal("3500"),
    )
    assert rule.evaluate(state, snapshot_exceeded, now) == ExitDecision.TARGET


def test_decision_recentre() -> None:
    """Confirmed breach within first 7 calendar days evaluates to RECENTRE."""
    rule = MonthlyExitRule()
    state = _make_state(entry_date=date(2026, 10, 28))
    # 2026-11-03 is 6 calendar days from entry (< 7 days)
    now = datetime(2026, 11, 3, 11, 30, tzinfo=IST)
    breakeven_low = Decimal("24100")
    spot_closes_low = (
        (datetime(2026, 11, 3, 11, 0, tzinfo=IST), Decimal("24080")),
        (datetime(2026, 11, 3, 11, 15, tzinfo=IST), Decimal("24060")),
        (datetime(2026, 11, 3, 11, 30, tzinfo=IST), Decimal("24050")),
    )
    snapshot_low = _make_snapshot(
        spot=Decimal("24040"),
        spot_closes=spot_closes_low,
        breakeven_low=breakeven_low,
        executable_pnl=Decimal("-800"),
    )
    assert rule.evaluate(state, snapshot_low, now) == ExitDecision.RECENTRE

    # High side breach within 7 calendar days
    breakeven_high = Decimal("24900")
    spot_closes_high = (
        (datetime(2026, 11, 3, 11, 0, tzinfo=IST), Decimal("24920")),
        (datetime(2026, 11, 3, 11, 30, tzinfo=IST), Decimal("24950")),
    )
    snapshot_high = _make_snapshot(
        spot=Decimal("24960"),
        spot_closes=spot_closes_high,
        breakeven_high=breakeven_high,
        executable_pnl=Decimal("-600"),
    )
    assert rule.evaluate(state, snapshot_high, now) == ExitDecision.RECENTRE


def test_decision_close_breach_late() -> None:
    """Confirmed breach on day 8+ (days >= 7) evaluates to CLOSE_BREACH_LATE."""
    rule = MonthlyExitRule()
    state = _make_state(entry_date=date(2026, 10, 28))
    # 2026-11-04 is 7 calendar days from entry (days >= 7)
    now = datetime(2026, 11, 4, 11, 30, tzinfo=IST)
    breakeven_low = Decimal("24100")
    spot_closes = (
        (datetime(2026, 11, 4, 11, 0, tzinfo=IST), Decimal("24050")),
        (datetime(2026, 11, 4, 11, 30, tzinfo=IST), Decimal("24020")),
    )
    snapshot = _make_snapshot(
        spot=Decimal("24010"),
        spot_closes=spot_closes,
        breakeven_low=breakeven_low,
        executable_pnl=Decimal("-1200"),
    )
    assert rule.evaluate(state, snapshot, now) == ExitDecision.CLOSE_BREACH_LATE


def test_decision_time_exit() -> None:
    """Exit triggered on or past hard exit date/time."""
    rule = MonthlyExitRule()
    plan = _make_plan(
        entry_date=date(2026, 10, 28),
        hard_exit_date=date(2026, 11, 11),
    )
    state = _make_state(plan=plan, entry_date=date(2026, 10, 28))
    snapshot = _make_snapshot()

    # Before hard exit time on hard exit date (15:14) -> HOLD
    now_before = datetime(2026, 11, 11, 15, 14, tzinfo=IST)
    assert rule.evaluate(state, snapshot, now_before) == ExitDecision.HOLD

    # At hard exit time on hard exit date (15:15) -> TIME_EXIT
    now_at = datetime(2026, 11, 11, 15, 15, tzinfo=IST)
    assert rule.evaluate(state, snapshot, now_at) == ExitDecision.TIME_EXIT

    # Past hard exit time on hard exit date (15:20) -> TIME_EXIT
    now_past_time = datetime(2026, 11, 11, 15, 20, tzinfo=IST)
    assert rule.evaluate(state, snapshot, now_past_time) == ExitDecision.TIME_EXIT

    # Strictly past hard exit date (2026-11-12) -> TIME_EXIT
    now_past_date = datetime(2026, 11, 12, 9, 30, tzinfo=IST)
    assert rule.evaluate(state, snapshot, now_past_date) == ExitDecision.TIME_EXIT


def test_decision_dte_guard() -> None:
    """Mandatory exit triggered when near leg DTE falls inside exit_by_dte."""
    rule = MonthlyExitRule()
    plan = _make_plan(
        entry_date=date(2026, 10, 28),
        near_expiry=date(2026, 11, 24),
        hard_exit_date=date(2026, 11, 20),
    )
    state = _make_state(plan=plan, entry_date=date(2026, 10, 28))
    snapshot = _make_snapshot()

    # DTE = 8 (2026-11-16) -> not triggered (HOLD)
    now_dte_8 = datetime(2026, 11, 16, 11, 0, tzinfo=IST)
    assert rule.evaluate(state, snapshot, now_dte_8) == ExitDecision.HOLD

    # DTE = 7 (2026-11-17) -> DTE_GUARD
    now_dte_7 = datetime(2026, 11, 17, 11, 0, tzinfo=IST)
    assert rule.evaluate(state, snapshot, now_dte_7) == ExitDecision.DTE_GUARD

    # DTE = 6 (2026-11-18) -> DTE_GUARD
    now_dte_6 = datetime(2026, 11, 18, 11, 0, tzinfo=IST)
    assert rule.evaluate(state, snapshot, now_dte_6) == ExitDecision.DTE_GUARD


def test_priority_order() -> None:
    """Priority order is strictly enforced: DTE guard beats target, target beats breach."""
    rule = MonthlyExitRule()
    plan = _make_plan(
        entry_date=date(2026, 10, 28),
        near_expiry=date(2026, 11, 24),
    )
    state = _make_state(plan=plan, entry_date=date(2026, 10, 28), target_pnl=Decimal("3000"))

    # Case 1: DTE guard (DTE=7 on 2026-11-17) AND Target hit (pnl=4000) -> DTE_GUARD
    now_dte = datetime(2026, 11, 17, 11, 0, tzinfo=IST)
    snapshot_target_and_dte = _make_snapshot(
        executable_pnl=Decimal("4000"),
    )
    assert rule.evaluate(state, snapshot_target_and_dte, now_dte) == ExitDecision.DTE_GUARD

    # Case 2: Target hit AND Breakeven breach confirmed (on day 6: 2026-11-03) -> TARGET
    now_breach = datetime(2026, 11, 3, 11, 30, tzinfo=IST)
    spot_closes = (
        (datetime(2026, 11, 3, 11, 0, tzinfo=IST), Decimal("24050")),
        (datetime(2026, 11, 3, 11, 30, tzinfo=IST), Decimal("24050")),
    )
    snapshot_target_and_breach = _make_snapshot(
        spot=Decimal("24050"),
        spot_closes=spot_closes,
        breakeven_low=Decimal("24100"),
        executable_pnl=Decimal("3500"),
    )
    assert rule.evaluate(state, snapshot_target_and_breach, now_breach) == ExitDecision.TARGET


def test_breach_requires_full_confirmation_window() -> None:
    """Breach is confirmed only when the window has >= 2 entries spanning >= 30 minutes."""
    rule = MonthlyExitRule()
    state = _make_state(entry_date=date(2026, 10, 28))
    now = datetime(2026, 11, 3, 11, 30, tzinfo=IST)
    breakeven_low = Decimal("24100")

    # 1. 25-minute span (11:05 to 11:30) does NOT confirm breach -> HOLD
    closes_25min = (
        (datetime(2026, 11, 3, 11, 5, tzinfo=IST), Decimal("24050")),
        (datetime(2026, 11, 3, 11, 30, tzinfo=IST), Decimal("24050")),
    )
    snapshot_25min = _make_snapshot(
        spot=Decimal("24050"),
        spot_closes=closes_25min,
        breakeven_low=breakeven_low,
    )
    assert rule.evaluate(state, snapshot_25min, now) == ExitDecision.HOLD

    # 2. 30-minute span (11:00 to 11:30) DOES confirm breach -> RECENTRE
    closes_30min = (
        (datetime(2026, 11, 3, 11, 0, tzinfo=IST), Decimal("24050")),
        (datetime(2026, 11, 3, 11, 30, tzinfo=IST), Decimal("24050")),
    )
    snapshot_30min = _make_snapshot(
        spot=Decimal("24050"),
        spot_closes=closes_30min,
        breakeven_low=breakeven_low,
    )
    assert rule.evaluate(state, snapshot_30min, now) == ExitDecision.RECENTRE

    # 3. Only 1 entry (at 11:30) does NOT confirm breach -> HOLD
    closes_single = ((datetime(2026, 11, 3, 11, 30, tzinfo=IST), Decimal("24050")),)
    snapshot_single = _make_snapshot(
        spot=Decimal("24050"),
        spot_closes=closes_single,
        breakeven_low=breakeven_low,
    )
    assert rule.evaluate(state, snapshot_single, now) == ExitDecision.HOLD

    # 4. 30-minute span but an intermediate close was within breakevens -> HOLD
    closes_interrupted = (
        (datetime(2026, 11, 3, 11, 0, tzinfo=IST), Decimal("24050")),
        (datetime(2026, 11, 3, 11, 15, tzinfo=IST), Decimal("24150")),
        (datetime(2026, 11, 3, 11, 30, tzinfo=IST), Decimal("24050")),
    )
    snapshot_interrupted = _make_snapshot(
        spot=Decimal("24050"),
        spot_closes=closes_interrupted,
        breakeven_low=breakeven_low,
    )
    assert rule.evaluate(state, snapshot_interrupted, now) == ExitDecision.HOLD

    # 5. 30-minute span all below breakeven_low, but current spot rebounded inside -> HOLD
    snapshot_spot_rebound = _make_snapshot(
        spot=Decimal("24120"),
        spot_closes=closes_30min,
        breakeven_low=breakeven_low,
    )
    assert rule.evaluate(state, snapshot_spot_rebound, now) == ExitDecision.HOLD


def test_breach_day8_closes_not_recentres() -> None:
    """Explicit assertions verifying Day 7 recentres while Day 8 and 9 close."""
    rule = MonthlyExitRule()
    entry_date = date(2026, 10, 28)
    state = _make_state(entry_date=entry_date)
    breakeven_low = Decimal("24100")

    # Day 7: 2026-11-03 (days diff = 6 < 7) -> RECENTRE
    now_day7 = datetime(2026, 11, 3, 11, 30, tzinfo=IST)
    closes_day7 = (
        (datetime(2026, 11, 3, 11, 0, tzinfo=IST), Decimal("24000")),
        (datetime(2026, 11, 3, 11, 30, tzinfo=IST), Decimal("24000")),
    )
    snapshot_day7 = _make_snapshot(
        spot=Decimal("24000"),
        spot_closes=closes_day7,
        breakeven_low=breakeven_low,
    )
    assert (now_day7.date() - entry_date).days == 6
    assert rule.evaluate(state, snapshot_day7, now_day7) == ExitDecision.RECENTRE

    # Day 8: 2026-11-04 (days diff = 7 >= 7) -> CLOSE_BREACH_LATE
    now_day8 = datetime(2026, 11, 4, 11, 30, tzinfo=IST)
    closes_day8 = (
        (datetime(2026, 11, 4, 11, 0, tzinfo=IST), Decimal("24000")),
        (datetime(2026, 11, 4, 11, 30, tzinfo=IST), Decimal("24000")),
    )
    snapshot_day8 = _make_snapshot(
        spot=Decimal("24000"),
        spot_closes=closes_day8,
        breakeven_low=breakeven_low,
    )
    assert (now_day8.date() - entry_date).days == 7
    assert rule.evaluate(state, snapshot_day8, now_day8) == ExitDecision.CLOSE_BREACH_LATE

    # Day 9: 2026-11-05 (days diff = 8 >= 7) -> CLOSE_BREACH_LATE
    now_day9 = datetime(2026, 11, 5, 11, 30, tzinfo=IST)
    closes_day9 = (
        (datetime(2026, 11, 5, 11, 0, tzinfo=IST), Decimal("24000")),
        (datetime(2026, 11, 5, 11, 30, tzinfo=IST), Decimal("24000")),
    )
    snapshot_day9 = _make_snapshot(
        spot=Decimal("24000"),
        spot_closes=closes_day9,
        breakeven_low=breakeven_low,
    )
    assert (now_day9.date() - entry_date).days == 8
    assert rule.evaluate(state, snapshot_day9, now_day9) == ExitDecision.CLOSE_BREACH_LATE


def test_ltp_inflated_value_does_not_trigger_target() -> None:
    """Target evaluation strictly relies on executable_pnl, ignoring inflated ltp_pnl."""
    rule = MonthlyExitRule()
    state = _make_state(
        entry_date=date(2026, 10, 28),
        target_pnl=Decimal("3000"),
    )
    now = datetime(2026, 10, 30, 11, 0, tzinfo=IST)

    # LTP indicates 5000 profit (above 3000 target), but executable is only 1500 -> HOLD
    snapshot = _make_snapshot(
        executable_pnl=Decimal("1500"),
        ltp_pnl=Decimal("5000"),
    )
    assert rule.evaluate(state, snapshot, now) == ExitDecision.HOLD

    # Once executable_pnl meets target, then TARGET is returned
    snapshot_executable_hit = _make_snapshot(
        executable_pnl=Decimal("3000"),
        ltp_pnl=Decimal("5000"),
    )
    assert rule.evaluate(state, snapshot_executable_hit, now) == ExitDecision.TARGET


def test_first_day_target_logs_flag() -> None:
    """Hitting target on the entry day logs a warning event."""
    rule = MonthlyExitRule()
    state = _make_state(
        entry_date=date(2026, 10, 28),
        target_pnl=Decimal("3000"),
    )

    # Entry day: 2026-10-28
    now_same_day = datetime(2026, 10, 28, 14, 0, tzinfo=IST)
    snapshot = _make_snapshot(executable_pnl=Decimal("3200"))

    with structlog.testing.capture_logs() as captured:
        decision = rule.evaluate(state, snapshot, now_same_day)

    assert decision == ExitDecision.TARGET
    events = [e for e in captured if e.get("event") == "monthly_exit_rule.first_day_target_hit"]
    assert len(events) == 1
    assert events[0]["log_level"] == "warning"
    assert events[0]["entry_date"] == "2026-10-28"
    assert events[0]["executable_pnl"] == "3200"
    assert events[0]["target_pnl"] == "3000"

    # Subsequent day: 2026-10-29 -> TARGET without warning
    now_next_day = datetime(2026, 10, 29, 11, 0, tzinfo=IST)
    with structlog.testing.capture_logs() as captured_next:
        decision_next = rule.evaluate(state, snapshot, now_next_day)

    assert decision_next == ExitDecision.TARGET
    events_next = [
        e for e in captured_next if e.get("event") == "monthly_exit_rule.first_day_target_hit"
    ]
    assert len(events_next) == 0


def test_naive_datetime_rejected() -> None:
    """Naive datetimes in either now or snapshot.spot_closes raise ValueError."""
    rule = MonthlyExitRule()
    state = _make_state()
    snapshot = _make_snapshot()

    # Naive 'now'
    naive_now = datetime(2026, 10, 30, 11, 0)
    with pytest.raises(ValueError, match="timezone-aware"):
        rule.evaluate(state, snapshot, naive_now)

    # Naive timestamp in spot_closes
    aware_now = datetime(2026, 10, 30, 11, 0, tzinfo=IST)
    naive_spot_closes = ((datetime(2026, 10, 30, 10, 45), Decimal("24500")),)
    snapshot_with_naive_ts = _make_snapshot(spot_closes=naive_spot_closes)
    with pytest.raises(ValueError, match="timezone-aware"):
        rule.evaluate(state, snapshot_with_naive_ts, aware_now)

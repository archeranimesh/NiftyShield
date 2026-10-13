"""Unit tests for BiweeklyExitRule."""

from datetime import date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from src.nifty_calendar.config import CalendarVariantConfig
from src.nifty_calendar.cycle import EntryPlan
from src.nifty_calendar.exit_rules import (
    BiweeklyExitRule,
    CycleExitState,
    ExitDecision,
    ExitRule,
    ExitSnapshot,
)

IST = ZoneInfo("Asia/Kolkata")


def _make_plan(
    entry_date: date = date(2026, 10, 9),
    near_expiry: date = date(2026, 10, 27),
    far_expiry: date = date(2026, 11, 3),
    planned_exit_date: date = date(2026, 10, 16),
    hard_exit_date: date = date(2026, 10, 20),
    entry_time_ist: time = time(10, 30),
    variant_name: str = "biweekly",
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
    entry_date: date = date(2026, 10, 9),
    entry_spot: Decimal = Decimal("24500"),
    entry_short_strike: Decimal = Decimal("24500"),
    target_pnl: Decimal = Decimal("1600"),
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


def test_biweekly_exit_rule_protocol() -> None:
    """Assert BiweeklyExitRule satisfies ExitRule protocol."""
    rule = BiweeklyExitRule()
    assert isinstance(rule, ExitRule)


def test_hold_when_nothing_triggers() -> None:
    """Assert HOLD is returned when all conditions are within normal parameters."""
    rule = BiweeklyExitRule()
    state = _make_state(entry_date=date(2026, 10, 9))
    now = datetime(2026, 10, 12, 11, 0, tzinfo=IST)  # Day 3
    snapshot = _make_snapshot(
        spot=Decimal("24550"),
        executable_pnl=Decimal("500"),
    )
    assert rule.evaluate(state, snapshot, now) == ExitDecision.HOLD


def test_200_point_boundary_199_holds_200_recentres() -> None:
    """Assert 199 point drift on day 4 holds while 200 point drift triggers RECENTRE_OFF_CENTRE."""
    rule = BiweeklyExitRule()
    entry_strike = Decimal("24500")
    state = _make_state(entry_date=date(2026, 10, 9), entry_short_strike=entry_strike)
    now_day4 = datetime(2026, 10, 13, 11, 0, tzinfo=IST)  # days_held = 4

    # 199 points up -> HOLD
    snap_199 = _make_snapshot(spot=entry_strike + Decimal("199"))
    assert rule.evaluate(state, snap_199, now_day4) == ExitDecision.HOLD

    # 200 points up -> RECENTRE_OFF_CENTRE
    snap_200 = _make_snapshot(spot=entry_strike + Decimal("200"))
    assert rule.evaluate(state, snap_200, now_day4) == ExitDecision.RECENTRE_OFF_CENTRE

    # 200 points down -> RECENTRE_OFF_CENTRE
    snap_down_200 = _make_snapshot(spot=entry_strike - Decimal("200"))
    assert rule.evaluate(state, snap_down_200, now_day4) == ExitDecision.RECENTRE_OFF_CENTRE


def test_off_centre_outside_window_holds() -> None:
    """Assert 200 point drift outside day 4-5 window (day 3 or day 6) evaluates to HOLD."""
    rule = BiweeklyExitRule()
    entry_strike = Decimal("24500")
    state = _make_state(entry_date=date(2026, 10, 9), entry_short_strike=entry_strike)
    snap_200 = _make_snapshot(spot=entry_strike + Decimal("200"))

    # Day 3 (2026-10-12): before window -> HOLD
    now_day3 = datetime(2026, 10, 12, 11, 0, tzinfo=IST)
    assert rule.evaluate(state, snap_200, now_day3) == ExitDecision.HOLD

    # Day 6 (2026-10-15): after window -> HOLD
    now_day6 = datetime(2026, 10, 15, 11, 0, tzinfo=IST)
    assert rule.evaluate(state, snap_200, now_day6) == ExitDecision.HOLD


def test_target_with_room_redeploys_same_pair() -> None:
    """Assert target met with DTE > exit_by_dte returns REDEPLOY_SAME_PAIR."""
    rule = BiweeklyExitRule()
    state = _make_state(
        entry_date=date(2026, 10, 9),
        target_pnl=Decimal("1600"),
        plan=_make_plan(
            entry_date=date(2026, 10, 9),
            near_expiry=date(2026, 10, 27),  # On 13 Oct, DTE is 14 > 7
        ),
    )
    now = datetime(2026, 10, 13, 11, 0, tzinfo=IST)
    snap = _make_snapshot(executable_pnl=Decimal("1600"))
    assert rule.evaluate(state, snap, now) == ExitDecision.REDEPLOY_SAME_PAIR


def test_target_late_closes_without_redeploy() -> None:
    """Assert target met when near DTE <= exit_by_dte triggers DTE_GUARD rather than redeploy."""
    rule = BiweeklyExitRule()
    state = _make_state(
        entry_date=date(2026, 10, 9),
        target_pnl=Decimal("1600"),
        plan=_make_plan(
            entry_date=date(2026, 10, 9),
            near_expiry=date(2026, 10, 20),  # DTE = 7 on 13 Oct (exit_by_dte = 7)
        ),
    )
    now = datetime(2026, 10, 13, 11, 0, tzinfo=IST)
    snap = _make_snapshot(executable_pnl=Decimal("1600"))
    # Priority 1 DTE_GUARD triggers because DTE <= 7
    decision = rule.evaluate(state, snap, now)
    assert decision == ExitDecision.DTE_GUARD
    assert decision != ExitDecision.REDEPLOY_SAME_PAIR


def test_priority_dte_guard_beats_target() -> None:
    """Assert DTE guard takes precedence over target profit."""
    rule = BiweeklyExitRule()
    state = _make_state(
        entry_date=date(2026, 10, 9),
        target_pnl=Decimal("1600"),
        plan=_make_plan(near_expiry=date(2026, 10, 20)),
    )
    now = datetime(2026, 10, 14, 11, 0, tzinfo=IST)  # DTE = 6 <= 7
    snap = _make_snapshot(executable_pnl=Decimal("2500"))  # Exceeds target
    assert rule.evaluate(state, snap, now) == ExitDecision.DTE_GUARD


def test_early_target_flagged_spread_artifact(caplog: pytest.LogCaptureFixture) -> None:
    """Assert target hit on entry day logs a warning for spread artifact."""
    rule = BiweeklyExitRule()
    entry_day = date(2026, 10, 9)
    state = _make_state(entry_date=entry_day, target_pnl=Decimal("1600"))
    now = datetime(2026, 10, 9, 14, 0, tzinfo=IST)  # Same day as entry
    snap = _make_snapshot(executable_pnl=Decimal("1650"))

    with caplog.at_level("WARNING"):
        decision = rule.evaluate(state, snap, now)

    assert decision == ExitDecision.REDEPLOY_SAME_PAIR
    assert "biweekly_exit_rule.first_day_target_hit" in caplog.text


def test_breach_before_day_3_holds() -> None:
    """Assert confirmed breakeven breach before day 3 (days_held < 3) evaluates to HOLD."""
    rule = BiweeklyExitRule()
    state = _make_state(entry_date=date(2026, 10, 9))
    # Day 2: 2026-10-11
    now = datetime(2026, 10, 11, 12, 0, tzinfo=IST)
    t0 = now - timedelta(minutes=30)
    t1 = now - timedelta(minutes=15)
    spot_closes = (
        (t0, Decimal("25000")),
        (t1, Decimal("25050")),
        (now, Decimal("25100")),
    )
    snap = _make_snapshot(
        spot=Decimal("25100"),
        breakeven_high=Decimal("24900"),  # Breached
        spot_closes=spot_closes,
    )
    assert rule.evaluate(state, snap, now) == ExitDecision.HOLD


def test_breach_in_window_recentres() -> None:
    """Assert confirmed breakeven breach in days 3-4 evaluates to RECENTRE."""
    rule = BiweeklyExitRule()
    state = _make_state(entry_date=date(2026, 10, 9))
    # Day 3: 2026-10-12
    now = datetime(2026, 10, 12, 12, 0, tzinfo=IST)
    t0 = now - timedelta(minutes=30)
    spot_closes = (
        (t0, Decimal("25000")),
        (now, Decimal("25050")),
    )
    snap = _make_snapshot(
        spot=Decimal("25050"),
        breakeven_high=Decimal("24900"),
        spot_closes=spot_closes,
    )
    assert rule.evaluate(state, snap, now) == ExitDecision.RECENTRE


def test_breach_late_closes() -> None:
    """Assert confirmed breakeven breach after day 4 evaluates to CLOSE_BREACH_LATE."""
    rule = BiweeklyExitRule()
    state = _make_state(entry_date=date(2026, 10, 9))
    # Day 5: 2026-10-14
    now = datetime(2026, 10, 14, 12, 0, tzinfo=IST)
    t0 = now - timedelta(minutes=30)
    spot_closes = (
        (t0, Decimal("25000")),
        (now, Decimal("25050")),
    )
    snap = _make_snapshot(
        spot=Decimal("25050"),
        breakeven_high=Decimal("24900"),
        spot_closes=spot_closes,
    )
    assert rule.evaluate(state, snap, now) == ExitDecision.CLOSE_BREACH_LATE


def test_time_exit_triggers() -> None:
    """Assert past hard exit date/time evaluates to TIME_EXIT."""
    rule = BiweeklyExitRule()
    hard_exit = date(2026, 10, 20)
    state = _make_state(
        entry_date=date(2026, 10, 9),
        plan=_make_plan(hard_exit_date=hard_exit, near_expiry=date(2026, 11, 3)),
    )
    # On hard exit date at 15:15 IST
    now = datetime.combine(hard_exit, time(15, 15), tzinfo=IST)
    snap = _make_snapshot()
    assert rule.evaluate(state, snap, now) == ExitDecision.TIME_EXIT


def test_naive_datetime_raises() -> None:
    """Assert ValueError when now or spot_closes is naive."""
    rule = BiweeklyExitRule()
    state = _make_state()
    snap = _make_snapshot()

    with pytest.raises(ValueError, match="now must be timezone-aware"):
        rule.evaluate(state, snap, datetime(2026, 10, 12, 11, 0))

    naive_closes = ((datetime(2026, 10, 12, 10, 30), Decimal("24500")),)
    snap_naive = _make_snapshot(spot_closes=naive_closes)
    with pytest.raises(ValueError, match="spot_closes timestamps must be timezone-aware"):
        rule.evaluate(state, snap_naive, datetime(2026, 10, 12, 11, 0, tzinfo=IST))


def test_non_default_config_thresholds_and_windows() -> None:
    """Assert custom config thresholds and windows are respected."""
    cfg = CalendarVariantConfig(
        name="custom_bw",
        strategy_name="paper_custom_bw",
        target_per_lot=Decimal("2000"),
        planned_hold_days=4,
        hard_hold_days=6,
        exit_by_dte=5,
        put_wing_start_points=300,
        call_wing_start_points=300,
        min_wing_points=250,
        vega_cap=Decimal("4"),
        delta_cap=Decimal("0.10"),
        risk_reward_floor=Decimal("0.75"),
        breakeven_symmetry_tolerance_pct=Decimal("0.50"),
        breakeven_loss_symmetry_tolerance=Decimal("0.25"),
        spread_tolerance=Decimal("3.0"),
        lot_size=65,
        breach_adjust_window_days_start=2,
        breach_adjust_window_days=3,
        recentre_spot_threshold_points=150,
        off_centre_window_days_start=3,
        off_centre_window_days_end=4,
    )
    rule = BiweeklyExitRule(config=cfg)
    state = _make_state(
        entry_date=date(2026, 10, 9),
        entry_short_strike=Decimal("24500"),
        target_pnl=Decimal("2000"),
    )

    # 150 points drift on day 3 with custom threshold 150 -> RECENTRE_OFF_CENTRE
    now_day3 = datetime(2026, 10, 12, 11, 0, tzinfo=IST)
    snap_150 = _make_snapshot(spot=Decimal("24650"))
    assert rule.evaluate(state, snap_150, now_day3) == ExitDecision.RECENTRE_OFF_CENTRE

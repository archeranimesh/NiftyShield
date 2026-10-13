"""Configuration models and variant defaults for Nifty calendar spreads."""

from dataclasses import dataclass
from datetime import time
from decimal import Decimal

__all__ = ["CalendarVariantConfig", "MONTHLY"]


@dataclass(frozen=True)
class CalendarVariantConfig:
    """Configuration parameters for a calendar spread strategy variant.

    Attributes:
        name: Short identifier for the variant (e.g. 'monthly', 'biweekly').
        strategy_name: Full strategy name used in trade logs and db entries.
        target_per_lot: Target profit per lot in INR.
        planned_hold_days: Planned holding period in trading days.
        hard_hold_days: Maximum holding period in trading days before forced exit.
        exit_by_dte: Minimum DTE before near expiry to trigger mandatory exit.
        put_wing_start_points: Initial strike distance for put far wing in index points.
        call_wing_start_points: Initial strike distance for call far wing in index points.
        min_wing_points: Minimum allowable wing distance in index points.
        vega_cap: Maximum acceptable net vega exposure per unit.
        delta_cap: Maximum allowable net delta exposure.
        risk_reward_floor: Minimum acceptable reward-to-risk ratio.
        breakeven_symmetry_tolerance_pct: Symmetry tolerance percentage for breakeven points.
        breakeven_loss_symmetry_tolerance: Asymmetry tolerance for losses at breakeven.
        spread_tolerance: Maximum allowable bid-ask spread in INR or points.
        breach_confirm_minutes: Confirmation window in minutes for breakeven breach.
        breach_adjust_window_days: Days before expiry during which adjustments are allowed.
        lots: Number of lots to trade.
        lot_size: Contract lot size in quantity units (e.g. 65 for Nifty).
        wing_step_points: Strike step size in points when searching for wings.
        max_wing_search_steps: Maximum search steps away from initial wing points.
        entry_time_ist: Standard entry time in IST.
        hard_exit_time_ist: Hard exit time on the exit date in IST.
    """

    name: str
    strategy_name: str
    target_per_lot: Decimal
    planned_hold_days: int
    hard_hold_days: int
    exit_by_dte: int
    put_wing_start_points: int
    call_wing_start_points: int
    min_wing_points: int
    vega_cap: Decimal
    delta_cap: Decimal
    risk_reward_floor: Decimal
    breakeven_symmetry_tolerance_pct: Decimal
    breakeven_loss_symmetry_tolerance: Decimal
    spread_tolerance: Decimal
    breach_confirm_minutes: int = 30
    breach_adjust_window_days: int = 7
    lots: int = 1
    lot_size: int = 65
    wing_step_points: int = 100
    max_wing_search_steps: int = 3
    entry_time_ist: time = time(10, 30)
    hard_exit_time_ist: time = time(15, 15)


MONTHLY: CalendarVariantConfig = CalendarVariantConfig(
    name="monthly",
    strategy_name="paper_nifty_calendar_monthly",
    target_per_lot=Decimal("3000"),
    planned_hold_days=7,
    hard_hold_days=10,
    exit_by_dte=7,
    put_wing_start_points=600,
    call_wing_start_points=600,
    min_wing_points=300,
    vega_cap=Decimal("20"),
    delta_cap=Decimal("0.10"),
    risk_reward_floor=Decimal("0.75"),
    breakeven_symmetry_tolerance_pct=Decimal("0.50"),
    breakeven_loss_symmetry_tolerance=Decimal("0.25"),
    spread_tolerance=Decimal("3.0"),
    breach_confirm_minutes=30,
    breach_adjust_window_days=7,
    lots=1,
    lot_size=65,
    wing_step_points=100,
    max_wing_search_steps=3,
    entry_time_ist=time(10, 30),
    hard_exit_time_ist=time(15, 15),
)

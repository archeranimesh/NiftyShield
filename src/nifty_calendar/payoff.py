"""Payoff and risk calculation for Nifty calendar structures."""

from __future__ import annotations

from datetime import date, datetime, time
from decimal import ROUND_HALF_UP, Decimal

from src.models.portfolio import AssetType
from src.nifty_calendar.errors import InvalidStructureError
from src.nifty_calendar.models import CalendarStructure, StructureMetrics
from src.nifty_calendar.pricing import b76_price, years_between


def derive_far_carry_from_atm(
    far_atm_strike: Decimal,
    far_atm_ce_mid: Decimal,
    far_atm_pe_mid: Decimal,
    spot: Decimal,
) -> Decimal:
    """Derive forward carry for far expiry from ATM put-call parity.

    Formula:
        (far_atm_strike + far_atm_ce_mid - far_atm_pe_mid) - spot

    Args:
        far_atm_strike: ATM strike in far expiry.
        far_atm_ce_mid: Mid price of ATM call in far expiry.
        far_atm_pe_mid: Mid price of ATM put in far expiry.
        spot: Spot price of underlying.

    Returns:
        Carry in points as Decimal.
    """
    return (far_atm_strike + far_atm_ce_mid - far_atm_pe_mid) - spot


def payoff_at(
    structure: CalendarStructure,
    spot: Decimal,
    as_of: date | datetime | None = None,
    iv_shift: Decimal = Decimal("0"),
    *,
    far_carry: Decimal,
    lot_size: int,
) -> Decimal:
    """Calculate per-lot structure P&L at spot and evaluation timestamp.

    Near legs are valued at intrinsic value at spot (pricing valid only on or
    after near_expiry). Far legs are repriced using Black-76 with
    vol = (leg.iv + iv_shift) / 100. If effective volatility (iv + iv_shift) is
    negative or zero, far legs are valued at intrinsic value at the forward.

    Args:
        structure: Calendar structure to value.
        spot: Underlying spot price.
        as_of: Evaluation timestamp (defaults to near_expiry at 15:30 IST).
        iv_shift: Parallel shift to far wing IV in percentage points.
        far_carry: Forward carry added to spot for far legs (required, keyword-only).
        lot_size: Contract lot size in units (required, keyword-only).

    Returns:
        Per-lot P&L in rupees as Decimal.

    Raises:
        InvalidStructureError: If as_of date is before near_expiry.
    """
    as_of_date = as_of.date() if isinstance(as_of, datetime) else (as_of or structure.near_expiry)
    if as_of_date < structure.near_expiry:
        raise InvalidStructureError(
            "as_of cannot be before near_expiry; near legs priced strictly at intrinsic"
        )

    if as_of is None:
        as_of_dt = datetime.combine(structure.near_expiry, time(15, 30))
    elif isinstance(as_of, datetime):
        as_of_dt = as_of
    else:
        as_of_dt = datetime.combine(as_of, time(15, 30))

    far_expiry_dt = datetime.combine(structure.far_expiry, time(15, 30))
    t_years = years_between(as_of_dt, far_expiry_dt)
    forward = float(spot + far_carry)

    # Near legs valued at intrinsic value at spot
    near_ce_intrinsic = max(spot - structure.short_ce.strike, Decimal("0"))
    near_pe_intrinsic = max(structure.short_pe.strike - spot, Decimal("0"))

    # Far legs repriced using Black-76
    vol_ce = float((structure.long_ce_wing.iv + iv_shift) / Decimal("100"))
    vol_pe = float((structure.long_pe_wing.iv + iv_shift) / Decimal("100"))

    far_ce_price = b76_price(
        AssetType.CE,
        forward,
        float(structure.long_ce_wing.strike),
        t_years,
        vol_ce,
    )
    far_pe_price = b76_price(
        AssetType.PE,
        forward,
        float(structure.long_pe_wing.strike),
        t_years,
        vol_pe,
    )

    far_ce_val = Decimal(str(round(far_ce_price, 4)))
    far_pe_val = Decimal(str(round(far_pe_price, 4)))

    pnl_per_unit = (
        structure.net_credit_per_unit
        - near_ce_intrinsic
        - near_pe_intrinsic
        + far_ce_val
        + far_pe_val
    )
    return pnl_per_unit * Decimal(lot_size)


def compute_metrics(
    structure: CalendarStructure,
    spot: Decimal,
    *,
    far_carry: Decimal,
    lot_size: int,
    as_of: date | datetime | None = None,
) -> StructureMetrics:
    """Compute risk, Greeks, and structure metrics over spot grid (+-15% in 1-pt steps).

    Loss at breakevens is defined per the video convention: the loss at the
    opposite breakeven's distance from spot:
      - loss_at_breakeven_low_per_lot: spot shifted down by abs(breakeven_high - spot)
      - loss_at_breakeven_high_per_lot: spot shifted up by abs(spot - breakeven_low)

    Args:
        structure: Calendar structure to evaluate.
        spot: Current underlying spot price.
        far_carry: Forward carry added to spot for far legs (required, keyword-only).
        lot_size: Contract lot size in units (required, keyword-only).
        as_of: Evaluation timestamp (defaults to near_expiry at 15:30 IST).

    Returns:
        StructureMetrics instance with all fields in Decimal.
    """
    net_delta = (
        -structure.short_ce.delta
        - structure.short_pe.delta
        + structure.long_ce_wing.delta
        + structure.long_pe_wing.delta
    )
    net_vega = (
        structure.long_ce_wing.vega
        + structure.long_pe_wing.vega
        - structure.short_ce.vega
        - structure.short_pe.vega
    )
    net_credit_per_unit = structure.net_credit_per_unit
    net_credit_per_lot = structure.net_credit_per_lot(lot_size)

    low_grid = int((spot * Decimal("0.85")).to_integral_value(rounding=ROUND_HALF_UP))
    high_grid = int((spot * Decimal("1.15")).to_integral_value(rounding=ROUND_HALF_UP))

    grid_spots = [Decimal(s) for s in range(low_grid, high_grid + 1)]
    grid_pnls = [
        payoff_at(structure, s, as_of=as_of, far_carry=far_carry, lot_size=lot_size)
        for s in grid_spots
    ]

    max_profit_per_lot = max(grid_pnls).quantize(Decimal("0.01"))
    max_loss_per_lot = min(grid_pnls).quantize(Decimal("0.01"))

    # Breakeven search by linear interpolation across zero-crossings
    breakeven_low: Decimal | None = None
    for i in range(len(grid_spots) - 1):
        if grid_pnls[i] <= Decimal("0") and grid_pnls[i + 1] > Decimal("0"):
            s0, s1 = grid_spots[i], grid_spots[i + 1]
            y0, y1 = grid_pnls[i], grid_pnls[i + 1]
            breakeven_low = (s0 + (-y0) * (s1 - s0) / (y1 - y0)).quantize(Decimal("0.01"))
            break

    if breakeven_low is None:
        raise InvalidStructureError("No lower breakeven crossing found on grid")

    breakeven_high: Decimal | None = None
    for i in range(len(grid_spots) - 1):
        if grid_pnls[i] > Decimal("0") and grid_pnls[i + 1] <= Decimal("0"):
            s0, s1 = grid_spots[i], grid_spots[i + 1]
            y0, y1 = grid_pnls[i], grid_pnls[i + 1]
            breakeven_high = (s0 + y0 * (s1 - s0) / (y0 - y1)).quantize(Decimal("0.01"))
            break

    if breakeven_high is None:
        raise InvalidStructureError("No upper breakeven crossing found on grid")

    breakeven_low_pct = (abs(spot - breakeven_low) / spot * Decimal("100")).quantize(
        Decimal("0.01")
    )
    breakeven_high_pct = (abs(breakeven_high - spot) / spot * Decimal("100")).quantize(
        Decimal("0.01")
    )

    if max_loss_per_lot >= Decimal("0"):
        # Zero loss sentinel: structure is in profit across grid; passes R:R floor
        risk_reward = Decimal("999.99")
    else:
        risk_reward = (max_profit_per_lot / abs(max_loss_per_lot)).quantize(Decimal("0.01"))

    shift_down = abs(breakeven_high - spot)
    loss_at_breakeven_low_per_lot = payoff_at(
        structure,
        spot - shift_down,
        as_of=as_of,
        far_carry=far_carry,
        lot_size=lot_size,
    ).quantize(Decimal("0.01"))

    shift_up = abs(spot - breakeven_low)
    loss_at_breakeven_high_per_lot = payoff_at(
        structure,
        spot + shift_up,
        as_of=as_of,
        far_carry=far_carry,
        lot_size=lot_size,
    ).quantize(Decimal("0.01"))

    return StructureMetrics(
        net_delta=net_delta,
        net_vega=net_vega,
        risk_reward=risk_reward,
        breakeven_low=breakeven_low,
        breakeven_high=breakeven_high,
        breakeven_low_pct=breakeven_low_pct,
        breakeven_high_pct=breakeven_high_pct,
        loss_at_breakeven_low_per_lot=loss_at_breakeven_low_per_lot,
        loss_at_breakeven_high_per_lot=loss_at_breakeven_high_per_lot,
        net_credit_per_unit=net_credit_per_unit,
        net_credit_per_lot=net_credit_per_lot,
        max_profit_per_lot=max_profit_per_lot,
        max_loss_per_lot=max_loss_per_lot,
    )

"""Strategy-agnostic expiry payoff math.

Expiry P&L is piecewise linear in spot with kinks only at option strikes, so
extrema and breakevens fall out of evaluating at ``0`` and every strike plus the
slope past the highest strike. No strategy is special-cased.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from src.payoff.errors import InvalidLegsError

_ZERO = Decimal("0")


@dataclass(frozen=True)
class PayoffLeg:
    """One leg of a position.

    Attributes:
        kind: Instrument type; FUT / EQ are linear in spot.
        strike: Option strike; ``None`` for FUT / EQ.
        qty: Signed units (+ long, - short); lots already times lot size.
        entry_price: Per-unit entry price.
        role: Free-form label, e.g. ``short_put``.
    """

    kind: Literal["CE", "PE", "FUT", "EQ"]
    strike: Decimal | None
    qty: int
    entry_price: Decimal
    role: str = ""


@dataclass(frozen=True)
class StrategyPayoff:
    """Computed expiry payoff summary.

    ``max_profit`` / ``max_loss`` are ``None`` when that side is unbounded;
    ``max_loss`` is negative. ``net_premium`` is + credit / - debit in rupees.
    """

    legs: tuple[PayoffLeg, ...]
    net_premium: Decimal
    max_profit: Decimal | None
    max_loss: Decimal | None
    breakevens: tuple[Decimal, ...]
    rr_ratio: Decimal | None
    key_spots: tuple[Decimal, ...]


def _leg_pnl(leg: PayoffLeg, spot: Decimal) -> Decimal:
    if leg.kind == "CE":
        intrinsic = max(spot - leg.strike, _ZERO)
    elif leg.kind == "PE":
        intrinsic = max(leg.strike - spot, _ZERO)
    else:
        intrinsic = spot
    return leg.qty * (intrinsic - leg.entry_price)


def _pnl(legs: Sequence[PayoffLeg], spot: Decimal) -> Decimal:
    return sum((_leg_pnl(leg, spot) for leg in legs), _ZERO)


def _validate(legs: Sequence[PayoffLeg]) -> None:
    if not legs:
        raise InvalidLegsError("legs must not be empty")
    for leg in legs:
        if leg.kind in ("CE", "PE") and leg.strike is None:
            raise InvalidLegsError(f"{leg.kind} leg requires a strike")
        if leg.kind in ("FUT", "EQ") and leg.strike is not None:
            raise InvalidLegsError(f"{leg.kind} leg must not have a strike")


def _find_breakevens(
    points: list[Decimal], values: list[Decimal], slope_up: int
) -> tuple[Decimal, ...]:
    pairs = list(zip(points, values, strict=True))
    found: set[Decimal] = {p for p, v in pairs if v == 0}
    for (x0, y0), (x1, y1) in zip(pairs, pairs[1:], strict=False):
        if y0 * y1 < 0:
            found.add(x0 + (x1 - x0) * (-y0) / (y1 - y0))
    if slope_up != 0:
        root = points[-1] - values[-1] / Decimal(slope_up)
        if root > points[-1]:
            found.add(root)
    return tuple(sorted(found))


def compute_payoff(legs: Sequence[PayoffLeg]) -> StrategyPayoff:
    """Compute max profit/loss, breakevens and R:R for any leg set.

    Args:
        legs: Position legs; at least one.

    Returns:
        A ``StrategyPayoff``; unbounded sides are ``None``.

    Raises:
        InvalidLegsError: On an empty list or an option leg without a strike.
    """
    _validate(legs)
    strikes = sorted({leg.strike for leg in legs if leg.strike is not None})
    points = sorted({_ZERO, *strikes})
    values = [_pnl(legs, p) for p in points]
    slope_up = sum(leg.qty for leg in legs if leg.kind != "PE")
    max_profit = None if slope_up > 0 else max(values)
    max_loss = None if slope_up < 0 else min(values)
    rr = None
    if max_profit is not None and max_loss is not None and max_loss != 0:
        rr = max_profit / abs(max_loss)
    return StrategyPayoff(
        legs=tuple(legs),
        net_premium=-sum((leg.qty * leg.entry_price for leg in legs), _ZERO),
        max_profit=max_profit,
        max_loss=max_loss,
        breakevens=_find_breakevens(points, values, slope_up),
        rr_ratio=rr,
        key_spots=tuple(strikes),
    )


def expiry_pnl_at(payoff: StrategyPayoff, spot: Decimal) -> Decimal:
    """Expiry P&L in rupees at a settlement spot.

    Shares ``_pnl`` with ``compute_payoff``, so the two cannot drift.

    Args:
        payoff: A computed payoff.
        spot: Settlement price.

    Returns:
        Sum of per-leg P&L at ``spot``.
    """
    return _pnl(payoff.legs, spot)


def expiry_pnl_series(
    payoff: StrategyPayoff, lo: Decimal, hi: Decimal, n: int
) -> tuple[list[Decimal], list[Decimal]]:
    """Expiry P&L over ``n`` evenly spaced spots in ``[lo, hi]``.

    Args:
        payoff: A computed payoff.
        lo: First spot (exact).
        hi: Last spot (exact).
        n: Number of points, at least 2.

    Returns:
        Matched ``(spots, pnls)`` lists of length ``n``.

    Raises:
        ValueError: If ``n < 2`` or ``hi < lo``.
    """
    if n < 2 or hi < lo:
        raise ValueError("need n >= 2 and hi >= lo")
    step = (hi - lo) / (n - 1)
    spots = [lo + step * i for i in range(n - 1)] + [hi]
    return spots, [expiry_pnl_at(payoff, s) for s in spots]

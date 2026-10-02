"""Reference-model helpers for option-chain correctness tests.

Pure, stdlib-only numerics. Values cross from ``Decimal`` to ``float`` at this
boundary: these are numerical reference models, not money paths (DECISIONS.md
"Greeks / option-chain correctness checks", 2026-10-02).

Put-call parity is checked against a chain-implied forward rather than an
assumed rate/dividend: an OLS of ``C_mid - P_mid`` on ``K`` gives
``slope = -e^(-rT)`` and ``intercept = e^(-rT) * F``.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.models.options import OptionChain


@dataclass(frozen=True)
class ParityPoint:
    """Mid-price parity inputs for one strike.

    Attributes:
        strike: Strike price.
        call_mid: CE (bid + ask) / 2.
        put_mid: PE (bid + ask) / 2.
        half_spread: Half the combined CE + PE bid/ask spread — the quote
            uncertainty on ``call_mid - put_mid``.
    """

    strike: float
    call_mid: float
    put_mid: float
    half_spread: float


@dataclass(frozen=True)
class ParityFit:
    """OLS fit of ``C_mid - P_mid = intercept + slope * K``.

    Attributes:
        slope: Fitted slope; ``-e^(-rT)`` under parity.
        intercept: Fitted intercept; ``e^(-rT) * F`` under parity.
    """

    slope: float
    intercept: float

    @property
    def forward(self) -> float:
        """Chain-implied forward ``F = intercept / -slope``."""
        return self.intercept / -self.slope


def parity_points(chain: OptionChain, max_distance: float) -> list[ParityPoint]:
    """Collect mid-price parity inputs from strikes two-sided on both legs.

    A strike is kept only when both CE and PE are present with ``bid > 0`` and
    ``ask > 0``, and ``|K - spot| <= max_distance``. LTP is deliberately unused
    (stale on illiquid strikes).

    Args:
        chain: Parsed option chain.
        max_distance: Max absolute strike distance from spot, index points.

    Returns:
        Parity points sorted by strike.
    """
    spot = float(chain.underlying_spot)
    points: list[ParityPoint] = []
    for strike, row in sorted(chain.strikes.items()):
        ce, pe = row.ce, row.pe
        if ce is None or pe is None:
            continue
        if min(ce.bid, ce.ask, pe.bid, pe.ask) <= 0:
            continue
        if abs(float(strike) - spot) > max_distance:
            continue
        points.append(
            ParityPoint(
                strike=float(strike),
                call_mid=float(ce.bid + ce.ask) / 2,
                put_mid=float(pe.bid + pe.ask) / 2,
                half_spread=float((ce.ask - ce.bid) + (pe.ask - pe.bid)) / 2,
            )
        )
    return points


def fit_implied_forward(points: list[ParityPoint]) -> ParityFit:
    """Fit ``C_mid - P_mid`` on strike by ordinary least squares.

    Args:
        points: Parity points; at least two distinct strikes.

    Returns:
        The fitted slope and intercept.

    Raises:
        ValueError: If fewer than two distinct strikes are supplied.
    """
    xs = [p.strike for p in points]
    if len(set(xs)) < 2:
        raise ValueError("need at least two distinct strikes to fit a forward")
    ys = [p.call_mid - p.put_mid for p in points]
    mean_x = sum(xs) / len(xs)
    mean_y = sum(ys) / len(ys)
    sxx = sum((x - mean_x) ** 2 for x in xs)
    sxy = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys, strict=True))
    slope = sxy / sxx
    return ParityFit(slope=slope, intercept=mean_y - slope * mean_x)


def parity_residuals(points: list[ParityPoint], fit: ParityFit) -> list[float]:
    """Return ``(C_mid - P_mid) - (intercept + slope * K)`` per point."""
    return [p.call_mid - p.put_mid - (fit.intercept + fit.slope * p.strike) for p in points]

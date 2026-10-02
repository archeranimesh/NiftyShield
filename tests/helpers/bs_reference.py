"""Reference-model helpers for option-chain correctness tests.

Pure, stdlib-only numerics. Values cross from ``Decimal`` to ``float`` at this
boundary: these are numerical reference models, not money paths (DECISIONS.md
"Greeks / option-chain correctness checks", 2026-10-02).

Put-call parity is checked against a chain-implied forward rather than an
assumed rate/dividend: an OLS of ``C_mid - P_mid`` on ``K`` gives
``slope = -e^(-rT)`` and ``intercept = e^(-rT) * F``.

The Black-Scholes reference pins Upstox's empirically fitted convention (spot
BSM, fitted r, q = 0, calendar/365 time to 15:30 IST, carry-free theta) so a
convention drift or parser unit error fails loudly.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone

from src.models.options import OptionChain, OptionLeg


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


_IST = timezone(timedelta(hours=5, minutes=30))
_EXPIRY_CLOSE = time(15, 30)
_SECONDS_PER_YEAR = 365 * 86400


@dataclass(frozen=True)
class GoldenLeg:
    """One chain leg selected for the Black-Scholes golden test.

    Attributes:
        strike: Strike price.
        is_call: True for CE, False for PE.
        iv_pct: The leg's implied volatility in percent, guaranteed > 0.
        leg: The broker-reported leg (Greeks under test).
    """

    strike: float
    is_call: bool
    iv_pct: float
    leg: OptionLeg


@dataclass(frozen=True)
class BSGreeks:
    """Reference Greeks in Upstox's units.

    Attributes:
        delta: Signed delta (PE negative).
        gamma: Per index point.
        vega: Per 1 vol point (σ change of 0.01).
        theta: Per calendar day.
    """

    delta: float
    gamma: float
    vega: float
    theta: float


def year_fraction(recorded_at: datetime, expiry: date) -> float:
    """Calendar-time fraction of a 365-day year from snapshot to 15:30 IST expiry.

    Args:
        recorded_at: Timezone-aware snapshot timestamp.
        expiry: Option expiry date.

    Returns:
        Time to expiry in years.

    Raises:
        ValueError: If ``recorded_at`` is naive or not before expiry close.
    """
    if recorded_at.tzinfo is None:
        raise ValueError("recorded_at must be timezone-aware")
    seconds = (datetime.combine(expiry, _EXPIRY_CLOSE, tzinfo=_IST) - recorded_at).total_seconds()
    if seconds <= 0:
        raise ValueError(f"snapshot {recorded_at.isoformat()} is not before expiry {expiry}")
    return seconds / _SECONDS_PER_YEAR


def golden_legs(chain: OptionChain, width: int) -> list[GoldenLeg]:
    """Select CE and PE legs within ``width`` strikes of the strike nearest spot.

    Legs with ``iv`` None or 0 are dropped: the parser stores a missing IV as
    ``Decimal("0")`` and no BS reference exists for it.

    Args:
        chain: Parsed option chain.
        width: Strikes either side of the ATM strike.

    Returns:
        Selected legs, sorted by strike, CE before PE.
    """
    strikes = sorted(chain.strikes)
    atm = min(range(len(strikes)), key=lambda i: abs(strikes[i] - chain.underlying_spot))
    selected: list[GoldenLeg] = []
    for strike in strikes[max(atm - width, 0) : atm + width + 1]:
        row = chain.strikes[strike]
        for is_call, leg in ((True, row.ce), (False, row.pe)):
            if leg is not None and leg.iv is not None and leg.iv > 0:
                selected.append(
                    GoldenLeg(strike=float(strike), is_call=is_call, iv_pct=float(leg.iv), leg=leg)
                )
    return selected


def _norm_cdf(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def _norm_pdf(x: float) -> float:
    return math.exp(-x * x / 2) / math.sqrt(2 * math.pi)


def bs_greeks(
    spot: float,
    strike: float,
    iv_pct: float,
    t: float,
    rate: float,
    is_call: bool,
    *,
    carry_theta: bool = False,
) -> BSGreeks:
    """Black-Scholes-Merton Greeks (q = 0) in Upstox's fitted convention.

    Upstox theta omits the carry term ``-rKe^(-rT)N(d2)``; ``carry_theta=True``
    adds it back, giving textbook BSM theta — used only to prove the omission.

    Args:
        spot: Underlying spot.
        strike: Strike price.
        iv_pct: Implied volatility in percent (Upstox ``iv``).
        t: Time to expiry in years.
        rate: Continuously compounded rate.
        is_call: True for CE, False for PE.
        carry_theta: Include the rate-carry term in theta.

    Returns:
        Reference delta, gamma, vega (per vol point), theta (per calendar day).

    Raises:
        ValueError: If ``iv_pct`` or ``t`` is not positive.
    """
    if iv_pct <= 0 or t <= 0:
        raise ValueError(f"iv_pct ({iv_pct}) and t ({t}) must be positive")
    sigma = iv_pct / 100
    sqrt_t = math.sqrt(t)
    d1 = (math.log(spot / strike) + (rate + sigma * sigma / 2) * t) / (sigma * sqrt_t)
    pdf = _norm_pdf(d1)
    theta = -spot * sigma * pdf / (2 * sqrt_t)
    if carry_theta:
        d2 = d1 - sigma * sqrt_t
        sign = 1 if is_call else -1
        theta -= sign * rate * strike * math.exp(-rate * t) * _norm_cdf(sign * d2)
    return BSGreeks(
        delta=_norm_cdf(d1) if is_call else _norm_cdf(d1) - 1,
        gamma=pdf / (spot * sigma * sqrt_t),
        vega=spot * pdf * sqrt_t / 100,
        theta=theta / 365,
    )

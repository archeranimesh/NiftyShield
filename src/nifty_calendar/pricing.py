"""Interim Black-76 pricing module for Nifty calendar structures.

NOTE: This module is marked interim and will be replaced by src/pricing in CM-9
once greeks-bs-fallback (GF-2/GF-3) ships. Ported from
scratch/chart_poc/2026-10-13_calendar_payoff_poc.py.
"""

from __future__ import annotations

import math
from datetime import date, datetime, time

from src.models.portfolio import AssetType


def _n(x: float) -> float:
    """Standard normal cumulative distribution function."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def years_between(start: date | datetime, end: date | datetime) -> float:
    """Calculate year fraction between two dates or datetimes using 365-day year.

    Args:
        start: Start date or datetime.
        end: End date or datetime.

    Returns:
        Year fraction as float.
    """
    if isinstance(start, datetime) and isinstance(end, datetime):
        return (end - start).total_seconds() / (365.0 * 86400.0)
    if isinstance(start, datetime) or isinstance(end, datetime):
        s_dt = start if isinstance(start, datetime) else datetime.combine(start, time(0, 0))
        e_dt = end if isinstance(end, datetime) else datetime.combine(end, time(0, 0))
        return (e_dt - s_dt).total_seconds() / (365.0 * 86400.0)
    return (end - start).days / 365.0


def b76_price(
    kind: AssetType | str,
    forward: float,
    strike: float,
    t_years: float,
    vol: float,
) -> float:
    """Calculate undiscounted Black-76 option price.

    Args:
        kind: Option type ('CE' or 'PE', or AssetType.CE / AssetType.PE).
        forward: Forward price of underlying asset.
        strike: Option strike price.
        t_years: Time to expiry in years.
        vol: Annualised volatility as a decimal fraction (e.g. 0.15 for 15%).

    Returns:
        Undiscounted Black-76 option price. If t_years <= 0 or vol <= 0,
        returns intrinsic value.
    """
    kind_str = kind.value if isinstance(kind, AssetType) else str(kind).upper()
    if kind_str not in ("CE", "PE"):
        raise ValueError(f"Invalid option kind: {kind}")

    if t_years <= 0.0 or vol <= 0.0:
        return max(forward - strike, 0.0) if kind_str == "CE" else max(strike - forward, 0.0)

    if forward <= 0.0 or strike <= 0.0:
        return max(forward - strike, 0.0) if kind_str == "CE" else max(strike - forward, 0.0)

    d1 = (math.log(forward / strike) + 0.5 * vol * vol * t_years) / (vol * math.sqrt(t_years))
    d2 = d1 - vol * math.sqrt(t_years)
    if kind_str == "CE":
        return forward * _n(d1) - strike * _n(d2)
    return strike * _n(-d2) - forward * _n(-d1)


def solve_iv(
    kind: AssetType | str,
    forward: float,
    strike: float,
    t_years: float,
    price: float,
) -> float:
    """Solve implied volatility using bisection.

    Args:
        kind: Option type ('CE' or 'PE', or AssetType.CE / AssetType.PE).
        forward: Forward price of underlying asset.
        strike: Option strike price.
        t_years: Time to expiry in years.
        price: Option price to match.

    Returns:
        Implied volatility as decimal fraction.

    Raises:
        ValueError: If t_years <= 0, price <= 0, or price is below intrinsic value.
    """
    kind_str = kind.value if isinstance(kind, AssetType) else str(kind).upper()
    if kind_str not in ("CE", "PE"):
        raise ValueError(f"Invalid option kind: {kind}")

    if t_years <= 0.0:
        raise ValueError(f"t_years must be positive, got {t_years}")
    if price <= 0.0:
        raise ValueError(f"price must be positive, got {price}")

    intrinsic = max(forward - strike, 0.0) if kind_str == "CE" else max(strike - forward, 0.0)
    if price < intrinsic:
        raise ValueError(f"price {price} is below intrinsic value {intrinsic}")

    lo = 0.001
    hi = 5.0
    for _ in range(100):
        mid = 0.5 * (lo + hi)
        if b76_price(kind_str, forward, strike, t_years, mid) > price:
            hi = mid
        else:
            lo = mid
    return 0.5 * (lo + hi)

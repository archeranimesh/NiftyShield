"""Phase B intraday features derived from prior scans (strategy doc section 4).

Pure and zero-I/O. The scan passes in the earlier ``gamma_signal_log`` rows of
one contract and gets back the inputs Layers 1, 2 and 4 need. Every feature is
``None`` when its look-back row is missing (first scan of the day, a missed
scan) so the signal stack fails closed with its ``*_UNAVAILABLE`` code.

Interpretations (the doc is silent or literal formulas do not fit):

* Look-backs pick the prior scan closest to ``now - N min`` within
  ``LOOKBACK_TOLERANCE``; there is no interpolation.
* ``speed_5m`` is ``d(gamma) / (d(spot) * direction)`` with direction +1 for
  CE and -1 for PE, so a positive value means gamma rose while spot moved in
  the trade direction, and is ``None`` when spot did not move in the trade
  direction (otherwise falling gamma on a move away would read as positive).
  The literal ``d(gamma)/d(spot)`` is negative for a PE approaching its strike.
* ``distance_sigma`` uses the scan-interval spot returns (no 1-min series is
  stored): sample std of the returns over the last 15 minutes, scaled by
  ``sqrt(bars left until the close)``. It needs ``MIN_RETURNS`` returns.
* ``volume_5m`` / ``volume_zscore_5m`` are not derived here: the log stores no
  cumulative day volume, so the scan leaves them ``None`` (Layer 4 fails
  closed) until that is persisted.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from statistics import stdev
from typing import Literal

LOOKBACK_TOLERANCE = timedelta(seconds=150)
BAR_MINUTES = 5
MIN_RETURNS = 3
_DIRECTION = {"CE": Decimal(1), "PE": Decimal(-1)}


@dataclass(frozen=True)
class PriorScan:
    """One earlier evaluation of the same contract (a ``gamma_signal_log`` row)."""

    at: datetime
    nifty_spot: Decimal
    gamma_val: Decimal
    best_ask: Decimal
    oi: int | None
    distance_pct: Decimal


@dataclass(frozen=True)
class ScanFeatures:
    """Look-back derived inputs; ``None`` = unavailable."""

    underlying_return_15m: Decimal | None
    distance_pct_15m_ago: Decimal | None
    speed_5m: Decimal | None
    oi_velocity_15m: Decimal | None
    option_price_rising: bool | None
    underlying_rvol_15m: Decimal | None
    distance_sigma: Decimal | None


def _nearest(history: Sequence[PriorScan], now: datetime, minutes: int) -> PriorScan | None:
    target = now - timedelta(minutes=minutes)
    close = [p for p in history if p.at < now and abs(p.at - target) <= LOOKBACK_TOLERANCE]
    return min(close, key=lambda p: abs(p.at - target)) if close else None


def _speed(
    option_type: Literal["CE", "PE"], spot: Decimal, gamma: Decimal, prior: PriorScan | None
) -> Decimal | None:
    if prior is None:
        return None
    d_spot = (spot - prior.nifty_spot) * _DIRECTION[option_type]
    if d_spot <= 0:  # spot not moving toward the strike: a falling gamma must not read as rising
        return None
    return (gamma - prior.gamma_val) / d_spot


def _oi_velocity(oi: int | None, prior: PriorScan | None) -> Decimal | None:
    if oi is None or prior is None or prior.oi is None:
        return None
    return Decimal(oi - prior.oi) / Decimal(max(prior.oi, 1))


def _rvol_and_sigma(
    now: datetime,
    spot: Decimal,
    distance_pct: Decimal,
    history: Sequence[PriorScan],
    close_at: datetime,
) -> tuple[Decimal | None, Decimal | None]:
    window = now - timedelta(minutes=15) - LOOKBACK_TOLERANCE
    points = sorted((p.at, p.nifty_spot) for p in history if window <= p.at < now)
    spots = [s for _, s in points] + [spot]
    rets = [spots[i] / spots[i - 1] - 1 for i in range(1, len(spots)) if spots[i - 1] > 0]
    if len(rets) < MIN_RETURNS:
        return None, None
    per_bar = stdev(rets)
    left = max(Decimal(int((close_at - now).total_seconds())) / 60 / BAR_MINUTES, Decimal(1))
    scaled = per_bar * left.sqrt()
    if scaled <= 0:
        return per_bar, None
    return per_bar, distance_pct / scaled


def derive_features(
    *,
    now: datetime,
    option_type: Literal["CE", "PE"],
    spot: Decimal,
    gamma: Decimal,
    ask: Decimal,
    oi: int | None,
    distance_pct: Decimal,
    history: Sequence[PriorScan],
    close_at: datetime,
) -> ScanFeatures:
    """Derive Layer 1/2/4 look-back inputs for one contract.

    Args:
        now: Scan time (timezone-aware).
        option_type: ``CE`` or ``PE``.
        spot: Current Nifty spot.
        gamma: Current option gamma.
        ask: Current ask.
        oi: Current open interest.
        distance_pct: Current ``|spot - strike| / spot``.
        history: Earlier rows of the same contract (any order).
        close_at: Session close, for the remaining-bars scaling.

    Returns:
        ``ScanFeatures``; each field is None when its look-back is missing.
    """
    p5 = _nearest(history, now, 5)
    p15 = _nearest(history, now, 15)
    rvol, sigma = _rvol_and_sigma(now, spot, distance_pct, history, close_at)
    return ScanFeatures(
        underlying_return_15m=None if p15 is None else spot / p15.nifty_spot - 1,
        distance_pct_15m_ago=None if p15 is None else p15.distance_pct,
        speed_5m=_speed(option_type, spot, gamma, p5),
        oi_velocity_15m=_oi_velocity(oi, p15),
        option_price_rising=None if p5 is None else ask >= p5.best_ask,
        underlying_rvol_15m=rvol,
        distance_sigma=sigma,
    )

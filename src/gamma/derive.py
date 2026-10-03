"""Pure derived-field maths for near-expiry gamma chain snapshots.

No I/O and no store access: callers pass in the chain and the prior-day OI
mapping. Shared by ``gamma_daily_watch.py`` and Phase B ``gamma_scan.py``.
"""

from __future__ import annotations

import datetime
from collections.abc import Mapping
from decimal import Decimal

import structlog

from src.gamma.models import GammaChainSnapshot
from src.models.options import OptionChain, OptionLeg

logger = structlog.get_logger(__name__)

_SPOT_BAND = Decimal("0.10")
_MIN_ASK_FOR_GEARING = Decimal("0.50")


def derive_snapshots(
    chain: OptionChain,
    expiry_date: datetime.date,
    today: datetime.date,
    snapshot_time: str,
    prior_oi: Mapping[tuple[int, str], int],
) -> list[GammaChainSnapshot]:
    """Build snapshot rows with derived fields for every strike within ±10% of spot.

    Args:
        chain: Parsed option chain for one expiry.
        expiry_date: Expiry the chain belongs to.
        today: Snapshot date.
        snapshot_time: Snapshot time as HH:MM.
        prior_oi: Prior-day OI keyed by (strike, option_type).

    Returns:
        One GammaChainSnapshot per available CE/PE leg, ordered by strike then
        CE before PE. Empty if the chain has no spot or no strikes.
    """
    spot = chain.underlying_spot
    if spot <= 0:
        return []
    created_at = datetime.datetime.now(datetime.timezone.utc)
    rows: list[GammaChainSnapshot] = []
    for strike in sorted(chain.strikes):
        if abs(strike - spot) / spot > _SPOT_BAND:
            continue
        pair = chain.strikes[strike]
        for option_type, leg in (("CE", pair.ce), ("PE", pair.pe)):
            if leg is None:
                continue
            rows.append(
                _build_row(
                    leg,
                    option_type,
                    int(strike),
                    spot,
                    expiry_date,
                    today,
                    snapshot_time,
                    prior_oi.get((int(strike), option_type)),
                    created_at,
                )
            )
    return rows


def _build_row(
    leg: OptionLeg,
    option_type: str,
    strike: int,
    spot: Decimal,
    expiry_date: datetime.date,
    today: datetime.date,
    snapshot_time: str,
    prior: int | None,
    created_at: datetime.datetime,
) -> GammaChainSnapshot:
    """Assemble one snapshot row from a leg and its derived fields."""
    return GammaChainSnapshot(
        snapshot_date=today,
        snapshot_time=snapshot_time,
        expiry_date=expiry_date,
        strike=strike,
        option_type=option_type,  # type: ignore[arg-type]  # always "CE" or "PE" from the caller loop
        dte_calendar=(expiry_date - today).days,
        nifty_spot=spot,
        nifty_futures=None,
        india_vix=None,
        delta_val=leg.delta,
        gamma_val=leg.gamma,
        vega_val=leg.vega,
        theta_val=leg.theta,
        iv_val=leg.iv,
        gamma_gearing=_gamma_gearing(leg, strike, spot),
        distance_pct=abs(spot - strike) / spot,
        best_bid=leg.bid,
        best_ask=leg.ask,
        bid_ask_spread=leg.ask - leg.bid if leg.ask > 0 and leg.bid > 0 else None,
        oi=leg.oi,
        oi_change_1d=_oi_change(leg.oi, prior),
        volume_day=leg.volume,
        strike_iv_pctile_20d=None,
        gamma_gearing_pctile_dte=None,
        created_at=created_at,
    )


def _gamma_gearing(leg: OptionLeg, strike: int, spot: Decimal) -> Decimal | None:
    """Return gamma × spot² / ask, or None if gamma is missing or ask is too low."""
    if leg.gamma is None:
        return None
    if leg.ask <= _MIN_ASK_FOR_GEARING:
        logger.warning("gamma.derive.ask_too_low_for_gearing", strike=strike, ask=str(leg.ask))
        return None
    return leg.gamma * spot * spot / leg.ask


def _oi_change(oi: int, prior: int | None) -> Decimal | None:
    """Return (oi - prior) / prior, or None if prior is missing or zero."""
    if prior is None or prior == 0:
        return None
    return Decimal(oi - prior) / Decimal(prior)

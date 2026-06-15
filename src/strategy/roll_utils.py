"""Shared roll utility functions for strategy adjustment logic.

All strategy ``_select_*_roll_target()`` helpers must call
``find_strike_by_delta`` rather than duplicating delta-range filtering.
Council mandate: 2026-06-02 strategy-monitor-watchlist-design.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from src.models.options import OptionChain, OptionLeg


def find_strike_by_delta(
    chain: OptionChain,
    option_type: Literal["CE", "PE"],
    delta_range: tuple[Decimal, Decimal],
    target_delta: Decimal,
) -> OptionLeg | None:
    """Filter chain strikes by absolute delta band and return the leg closest to target.

    Scans all strikes in the chain for the given option type, filters to those whose
    absolute delta falls within [delta_range[0], delta_range[1]], then returns the
    leg whose absolute delta is closest to target_delta. Returns None when no
    candidates exist or the chain has no strikes.

    Args:
        chain: Current Nifty 50 option chain snapshot.
        option_type: "CE" for call legs, "PE" for put legs.
        delta_range: Inclusive (min, max) absolute delta filter band.
                     E.g. (Decimal("0.18"), Decimal("0.28")) for CSP target zone.
        target_delta: Ideal absolute delta to rank candidates against.
                      E.g. Decimal("0.22") for CSP 22-delta target.

    Returns:
        OptionLeg with absolute delta closest to target_delta within the band,
        or None when no candidates found.
    """
    lo, hi = delta_range
    candidates: list[OptionLeg] = []

    for strike_data in chain.strikes.values():
        leg: OptionLeg | None = strike_data.ce if option_type == "CE" else strike_data.pe
        if leg is None:
            continue
        if leg.ltp <= Decimal("0"):
            continue
        if leg.delta is None:
            continue
        abs_delta = abs(leg.delta)
        if lo <= abs_delta <= hi:
            candidates.append(leg)

    if not candidates:
        return None

    def _sort_key(leg: OptionLeg) -> tuple[Decimal, int]:
        # Primary: distance from target; secondary: descending OI (negate for min-sort).
        return (abs(abs(leg.delta) - target_delta), -leg.oi)  # type: ignore[return-value]

    return min(candidates, key=_sort_key)

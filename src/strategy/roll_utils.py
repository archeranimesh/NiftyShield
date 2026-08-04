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
        # candidates is already filtered for delta is None above.
        assert leg.delta is not None
        return (abs(abs(leg.delta) - target_delta), -leg.oi)

    return min(candidates, key=_sort_key)


def evaluate_floor_formula(
    new_width_pts: Decimal,
    d_cum_pts: Decimal,
    d_lock_pts: Decimal,
    k_pts: Decimal,
    entry_credit_pts: Decimal,
    floor_budget: Decimal,
) -> bool:
    """max(W_put, W_call) + D_cum + D_lock + K <= floor_budget * C0.

    Same inequality as ``ProfitLockEngine._evaluate_floor_formula`` (Zone 2
    profit-lock wing contraction) — extracted here (BUG-022) so the
    delta-stop roll-search path (``search_narrow_wing_replacement`` below)
    can reuse it without introducing a strategy-layer dependency on
    ``profit_lock_engine``. ``ProfitLockEngine`` is left calling its own
    private copy unchanged to avoid an unrelated behavior-preserving refactor
    in the same commit as this bug fix.
    """
    return (
        new_width_pts + d_cum_pts + d_lock_pts + k_pts
        <= floor_budget * entry_credit_pts
    )


def search_narrow_wing_replacement(
    chain: OptionChain,
    option_type: Literal["CE", "PE"],
    short_strike: Decimal,
    current_wing_strike: Decimal,
    other_side_width_pts: Decimal,
    d_cum_pts: Decimal,
    d_lock_pts: Decimal,
    k_pts: Decimal,
    entry_credit_pts: Decimal,
    floor_budget: Decimal,
    min_premium: Decimal,
    liquidity_spread_pct: Decimal = Decimal("0.05"),
) -> OptionLeg | None:
    """Search progressively narrower replacement wings after a delta-stop roll failure.

    BUG-022: when the single delta-band candidate a roll attempt evaluates
    fails a liquidity/premium check, the pre-fix behavior gave up and fell
    through to a naked single-side ``CLOSE_CALL_SPREAD``/``CLOSE_PUT_SPREAD``.
    This walks every strike strictly between ``current_wing_strike`` and
    ``short_strike`` (``short_strike`` itself is never a candidate — that
    would collapse the hedge to zero width, i.e. a naked short), ordered from
    widest (nearest the original wing) to narrowest (nearest the short
    strike), and returns the first strike whose leg clears both the
    liquidity/premium floor and the shared floor-guarantee inequality
    (``evaluate_floor_formula``, the same one Zone 2 profit-lock uses).

    Args:
        chain: Current option chain snapshot.
        option_type: "CE" for the call wing, "PE" for the put wing.
        short_strike: Strike of the threatened short leg. Never a candidate.
        current_wing_strike: Strike of the existing long hedge being replaced.
        other_side_width_pts: Width (points) of the *other* side's wing, for
            the shared inequality's ``max(W_put, W_call)`` term.
        d_cum_pts: Cumulative debit already spent on prior wing rolls this cycle.
        d_lock_pts: Debit committed by any already-executed profit-lock roll.
        k_pts: Fixed transaction-cost buffer.
        entry_credit_pts: C0 — the position's original entry credit.
        floor_budget: Fraction of C0 the combined width+debit may not exceed.
        min_premium: Minimum acceptable mid-price for a candidate leg.
        liquidity_spread_pct: Max acceptable bid/ask spread as a fraction of mid.

    Returns:
        The first candidate ``OptionLeg`` clearing both checks, or ``None``
        when every strike in range fails — the caller must then escalate to
        ``CLOSE_FULL`` rather than a naked single-side close.
    """
    is_call = option_type == "CE"

    def _leg_for(strike: Decimal) -> OptionLeg | None:
        strike_data = chain.strikes.get(strike)
        if strike_data is None:
            return None
        return strike_data.ce if is_call else strike_data.pe

    if is_call:
        # Wing above the short call; narrower = smaller strike, closer to
        # short_strike. Widest-first: descending strike order.
        ordered_strikes = sorted(
            (
                strike
                for strike in chain.strikes
                if short_strike < strike < current_wing_strike
            ),
            reverse=True,
        )
    else:
        # Wing below the short put; narrower = larger strike, closer to
        # short_strike. Widest-first: ascending strike order.
        ordered_strikes = sorted(
            strike
            for strike in chain.strikes
            if current_wing_strike < strike < short_strike
        )

    for strike in ordered_strikes:
        leg = _leg_for(strike)
        if leg is None:
            continue
        if leg.bid <= Decimal("0") or leg.ask <= Decimal("0"):
            continue
        mid = (leg.bid + leg.ask) / Decimal("2")
        if mid < min_premium:
            continue
        spread = leg.ask - leg.bid
        if spread / mid > liquidity_spread_pct:
            continue

        width_pts = abs(strike - short_strike)
        new_width = max(width_pts, other_side_width_pts)
        if evaluate_floor_formula(
            new_width, d_cum_pts, d_lock_pts, k_pts, entry_credit_pts, floor_budget
        ):
            return leg

    return None

"""Tests for src/strategy/roll_utils.py — find_strike_by_delta."""

from __future__ import annotations

import datetime
from decimal import Decimal

from src.models.options import OptionChain, OptionChainStrike, OptionLeg
from src.strategy.roll_utils import (
    evaluate_floor_formula,
    find_strike_by_delta,
    search_narrow_wing_replacement,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _leg(
    strike: str,
    delta: str | None,
    ltp: str = "50",
    oi: int = 1000,
) -> OptionLeg:
    """Build a minimal OptionLeg for testing."""
    return OptionLeg(
        ltp=Decimal(ltp),
        bid=Decimal("49"),
        ask=Decimal("51"),
        oi=oi,
        volume=100,
        delta=Decimal(delta) if delta is not None else None,
        gamma=None,
        theta=None,
        vega=None,
        iv=None,
        strike=Decimal(strike),
    )


def _chain(
    strikes: dict[str, tuple[OptionLeg | None, OptionLeg | None]],
) -> OptionChain:
    """Build OptionChain from {strike_str: (ce_leg, pe_leg)} mapping."""
    return OptionChain(
        underlying_spot=Decimal("22500"),
        expiry=datetime.date(2026, 7, 1),
        strikes={Decimal(k): OptionChainStrike(ce=ce, pe=pe) for k, (ce, pe) in strikes.items()},
    )


# ---------------------------------------------------------------------------
# Happy-path tests
# ---------------------------------------------------------------------------


def test_pe_chain_returns_closest_to_target() -> None:
    """PE chain with 3 strikes in band → returns leg closest to target delta."""
    # Abs deltas: 0.20, 0.22, 0.26 — target 0.22; expect strike 22300 (exact hit).
    chain = _chain(
        {
            "22400": (None, _leg("22400", "-0.20")),
            "22300": (None, _leg("22300", "-0.22")),
            "22200": (None, _leg("22200", "-0.26")),
            "22100": (None, _leg("22100", "-0.40")),  # outside band
        }
    )
    result = find_strike_by_delta(
        chain,
        "PE",
        (Decimal("0.18"), Decimal("0.28")),
        Decimal("0.22"),
    )
    assert result is not None
    assert result.strike == Decimal("22300")


def test_ce_chain_returns_closest_to_target() -> None:
    """CE chain with 3 strikes in band → returns leg closest to target delta."""
    # Abs deltas: 0.20, 0.23, 0.28 — target 0.22.
    # Distances: 0.02, 0.01, 0.06 → 22600 wins (distance 0.01).
    chain = _chain(
        {
            "22500": (_leg("22500", "0.20"), None),
            "22600": (_leg("22600", "0.23"), None),
            "22700": (_leg("22700", "0.28"), None),
            "22800": (_leg("22800", "0.35"), None),  # outside band
        }
    )
    result = find_strike_by_delta(
        chain,
        "CE",
        (Decimal("0.18"), Decimal("0.28")),
        Decimal("0.22"),
    )
    assert result is not None
    assert result.strike == Decimal("22600")


def test_single_strike_exactly_at_target() -> None:
    """Single strike exactly at target delta → returns it."""
    chain = _chain({"22300": (None, _leg("22300", "-0.22"))})
    result = find_strike_by_delta(
        chain,
        "PE",
        (Decimal("0.20"), Decimal("0.25")),
        Decimal("0.22"),
    )
    assert result is not None
    assert result.strike == Decimal("22300")


def test_tie_break_prefers_higher_oi() -> None:
    """Two equidistant candidates → returns the one with higher OI."""
    # Abs deltas: 0.20 and 0.24, both distance 0.02 from target 0.22.
    # Higher OI is on 22200 (oi=5000).
    chain = _chain(
        {
            "22400": (None, _leg("22400", "-0.20", oi=1000)),
            "22200": (None, _leg("22200", "-0.24", oi=5000)),
        }
    )
    result = find_strike_by_delta(
        chain,
        "PE",
        (Decimal("0.18"), Decimal("0.28")),
        Decimal("0.22"),
    )
    assert result is not None
    assert result.strike == Decimal("22200")


# ---------------------------------------------------------------------------
# Edge / error tests
# ---------------------------------------------------------------------------


def test_no_strikes_with_positive_ltp_returns_none() -> None:
    """No strikes with ltp > 0 in band → returns None."""
    chain = _chain(
        {
            "22300": (None, _leg("22300", "-0.22", ltp="0")),
            "22200": (None, _leg("22200", "-0.24", ltp="0")),
        }
    )
    result = find_strike_by_delta(
        chain,
        "PE",
        (Decimal("0.18"), Decimal("0.28")),
        Decimal("0.22"),
    )
    assert result is None


def test_empty_chain_returns_none() -> None:
    """Empty chain (no strikes) → returns None."""
    chain = OptionChain(
        underlying_spot=Decimal("22500"),
        expiry=datetime.date(2026, 7, 1),
        strikes={},
    )
    result = find_strike_by_delta(
        chain,
        "PE",
        (Decimal("0.18"), Decimal("0.28")),
        Decimal("0.22"),
    )
    assert result is None


def test_all_strikes_outside_delta_range_returns_none() -> None:
    """All strikes outside delta range → returns None."""
    chain = _chain(
        {
            "22600": (None, _leg("22600", "-0.10")),  # too low
            "21800": (None, _leg("21800", "-0.50")),  # too high
        }
    )
    result = find_strike_by_delta(
        chain,
        "PE",
        (Decimal("0.18"), Decimal("0.28")),
        Decimal("0.22"),
    )
    assert result is None


def _priced_leg(
    strike: str,
    bid: str = "49",
    ask: str = "51",
) -> OptionLeg:
    """Build an OptionLeg with explicit bid/ask, for floor/liquidity tests."""
    return OptionLeg(
        ltp=(Decimal(bid) + Decimal(ask)) / Decimal("2"),
        bid=Decimal(bid),
        ask=Decimal(ask),
        oi=1000,
        volume=100,
        delta=None,
        gamma=None,
        theta=None,
        vega=None,
        iv=None,
        strike=Decimal(strike),
    )


# ---------------------------------------------------------------------------
# evaluate_floor_formula (BUG-022)
# ---------------------------------------------------------------------------


def test_evaluate_floor_formula_passes_at_exact_boundary() -> None:
    """width + d_cum + d_lock + k == floor_budget * C0 (equality) → passes."""
    assert evaluate_floor_formula(
        Decimal("40"), Decimal("0"), Decimal("0"), Decimal("10"), Decimal("100"), Decimal("0.5")
    )


def test_evaluate_floor_formula_fails_just_over_boundary() -> None:
    """One point over the boundary → fails."""
    assert not evaluate_floor_formula(
        Decimal("41"), Decimal("0"), Decimal("0"), Decimal("10"), Decimal("100"), Decimal("0.5")
    )


# ---------------------------------------------------------------------------
# search_narrow_wing_replacement (BUG-022)
# ---------------------------------------------------------------------------


def test_search_narrow_wing_call_widest_valid_candidate_wins() -> None:
    """Call side: widest candidate that clears the floor is chosen first."""
    chain = _chain(
        {
            "25010": (_priced_leg("25010"), None),
            "25020": (_priced_leg("25020"), None),
            "25030": (_priced_leg("25030"), None),
            "25040": (_priced_leg("25040"), None),
        }
    )
    result = search_narrow_wing_replacement(
        chain=chain,
        option_type="CE",
        short_strike=Decimal("25000"),
        current_wing_strike=Decimal("25050"),
        other_side_width_pts=Decimal("0"),
        d_cum_pts=Decimal("0"),
        d_lock_pts=Decimal("0"),
        k_pts=Decimal("10"),
        entry_credit_pts=Decimal("100"),
        floor_budget=Decimal("0.5"),  # budget=50; width<=40 passes
        min_premium=Decimal("1"),
    )
    assert result is not None
    assert result.strike == Decimal("25040")


def test_search_narrow_wing_call_falls_back_to_narrower_candidate() -> None:
    """Widest candidate fails the inequality; a narrower one succeeds."""
    chain = _chain(
        {
            "25010": (_priced_leg("25010"), None),
            "25020": (_priced_leg("25020"), None),
            "25030": (_priced_leg("25030"), None),
            "25040": (_priced_leg("25040"), None),
        }
    )
    result = search_narrow_wing_replacement(
        chain=chain,
        option_type="CE",
        short_strike=Decimal("25000"),
        current_wing_strike=Decimal("25050"),
        other_side_width_pts=Decimal("0"),
        d_cum_pts=Decimal("0"),
        d_lock_pts=Decimal("0"),
        k_pts=Decimal("10"),
        entry_credit_pts=Decimal("100"),
        floor_budget=Decimal("0.45"),  # budget=45; only width<=35 passes
        min_premium=Decimal("1"),
    )
    assert result is not None
    assert result.strike == Decimal("25030")


def test_search_narrow_wing_put_ascending_order_narrower_candidate() -> None:
    """Put side: search walks upward toward the short strike, same logic mirrored."""
    chain = _chain(
        {
            "24960": (None, _priced_leg("24960")),
            "24970": (None, _priced_leg("24970")),
            "24980": (None, _priced_leg("24980")),
            "24990": (None, _priced_leg("24990")),
        }
    )
    result = search_narrow_wing_replacement(
        chain=chain,
        option_type="PE",
        short_strike=Decimal("25000"),
        current_wing_strike=Decimal("24950"),
        other_side_width_pts=Decimal("0"),
        d_cum_pts=Decimal("0"),
        d_lock_pts=Decimal("0"),
        k_pts=Decimal("10"),
        entry_credit_pts=Decimal("100"),
        floor_budget=Decimal("0.45"),  # budget=45; only width<=35 passes
        min_premium=Decimal("1"),
    )
    assert result is not None
    assert result.strike == Decimal("24970")  # width=30, narrowest that clears 35


def test_search_narrow_wing_exhausted_returns_none() -> None:
    """No candidate width clears the floor at any point in the range → None.

    Caller must escalate to CLOSE_FULL, never fall through to a naked
    single-side close (BUG-022).
    """
    chain = _chain(
        {
            "25010": (_priced_leg("25010"), None),
            "25020": (_priced_leg("25020"), None),
            "25030": (_priced_leg("25030"), None),
            "25040": (_priced_leg("25040"), None),
        }
    )
    result = search_narrow_wing_replacement(
        chain=chain,
        option_type="CE",
        short_strike=Decimal("25000"),
        current_wing_strike=Decimal("25050"),
        other_side_width_pts=Decimal("0"),
        d_cum_pts=Decimal("0"),
        d_lock_pts=Decimal("0"),
        k_pts=Decimal("10"),
        entry_credit_pts=Decimal("100"),
        floor_budget=Decimal("0.15"),  # budget=15; even width=10 fails (10+10=20>15)
        min_premium=Decimal("1"),
    )
    assert result is None


def test_search_narrow_wing_never_returns_short_strike_or_current_wing() -> None:
    """Even if legs exist exactly at the short strike or current wing, they
    are never candidates — collapsing the hedge to zero width would be a
    naked short, and the current wing already failed the caller's own check."""
    chain = _chain(
        {
            # Trivially "passes" every floor if it were ever considered
            # (width would be 0), but must never be returned.
            "25000": (_priced_leg("25000"), None),
            "25050": (_priced_leg("25050"), None),
            "25030": (_priced_leg("25030"), None),
        }
    )
    result = search_narrow_wing_replacement(
        chain=chain,
        option_type="CE",
        short_strike=Decimal("25000"),
        current_wing_strike=Decimal("25050"),
        other_side_width_pts=Decimal("0"),
        d_cum_pts=Decimal("0"),
        d_lock_pts=Decimal("0"),
        k_pts=Decimal("10"),
        entry_credit_pts=Decimal("100"),
        floor_budget=Decimal("0.5"),
        min_premium=Decimal("1"),
    )
    assert result is not None
    assert result.strike == Decimal("25030")
    assert result.strike not in (Decimal("25000"), Decimal("25050"))


def test_search_narrow_wing_skips_illiquid_candidate() -> None:
    """A candidate failing the bid/ask liquidity gate is skipped, not accepted."""
    chain = _chain(
        {
            # Widest candidate: huge spread relative to mid (fails liquidity).
            "25040": (_priced_leg("25040", bid="30", ask="70"), None),
            "25030": (_priced_leg("25030"), None),
        }
    )
    result = search_narrow_wing_replacement(
        chain=chain,
        option_type="CE",
        short_strike=Decimal("25000"),
        current_wing_strike=Decimal("25050"),
        other_side_width_pts=Decimal("0"),
        d_cum_pts=Decimal("0"),
        d_lock_pts=Decimal("0"),
        k_pts=Decimal("10"),
        entry_credit_pts=Decimal("100"),
        floor_budget=Decimal("0.5"),
        min_premium=Decimal("1"),
    )
    assert result is not None
    assert result.strike == Decimal("25030")


def test_search_narrow_wing_skips_below_min_premium() -> None:
    """A candidate below the minimum premium floor is skipped, not accepted."""
    chain = _chain(
        {
            "25040": (_priced_leg("25040", bid="0.10", ask="0.20"), None),
            "25030": (_priced_leg("25030"), None),
        }
    )
    result = search_narrow_wing_replacement(
        chain=chain,
        option_type="CE",
        short_strike=Decimal("25000"),
        current_wing_strike=Decimal("25050"),
        other_side_width_pts=Decimal("0"),
        d_cum_pts=Decimal("0"),
        d_lock_pts=Decimal("0"),
        k_pts=Decimal("10"),
        entry_credit_pts=Decimal("100"),
        floor_budget=Decimal("0.5"),
        min_premium=Decimal("15"),
    )
    assert result is not None
    assert result.strike == Decimal("25030")


def test_search_narrow_wing_empty_range_returns_none() -> None:
    """No strikes at all between short and current wing → None, no crash."""
    chain = _chain({})
    result = search_narrow_wing_replacement(
        chain=chain,
        option_type="CE",
        short_strike=Decimal("25000"),
        current_wing_strike=Decimal("25050"),
        other_side_width_pts=Decimal("0"),
        d_cum_pts=Decimal("0"),
        d_lock_pts=Decimal("0"),
        k_pts=Decimal("10"),
        entry_credit_pts=Decimal("100"),
        floor_budget=Decimal("0.5"),
        min_premium=Decimal("1"),
    )
    assert result is None


def test_exact_match_only_delta_range() -> None:
    """delta_range min == max (exact match only) → returns matching leg or None."""
    chain = _chain(
        {
            "22300": (None, _leg("22300", "-0.22")),
            "22200": (None, _leg("22200", "-0.24")),
        }
    )
    # Only 0.22 matches a [0.22, 0.22] band.
    result = find_strike_by_delta(
        chain,
        "PE",
        (Decimal("0.22"), Decimal("0.22")),
        Decimal("0.22"),
    )
    assert result is not None
    assert result.strike == Decimal("22300")

    # No strike has delta 0.30 exactly.
    result_none = find_strike_by_delta(
        chain,
        "PE",
        (Decimal("0.30"), Decimal("0.30")),
        Decimal("0.30"),
    )
    assert result_none is None

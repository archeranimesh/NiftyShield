"""Unit tests for WingStructureSelector and pure quote helpers in src/nifty_calendar."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from src.models.options import OptionChain, OptionChainStrike, OptionLeg
from src.nifty_calendar.config import MONTHLY
from src.nifty_calendar.models import CalendarStructure
from src.nifty_calendar.selector import NoEntry, WingStructureSelector, mid, spread_points


def _make_leg(
    strike: Decimal,
    bid: Decimal,
    ask: Decimal,
    delta: Decimal | None,
    vega: Decimal | None,
    iv: Decimal | None,
    ltp: Decimal | None = None,
) -> OptionLeg:
    """Helper to build OptionLeg with Decimal prices and Greeks."""
    return OptionLeg(
        strike=strike,
        ltp=ltp if ltp is not None else ((bid + ask) / Decimal("2")),
        bid=bid,
        ask=ask,
        oi=100000,
        volume=50000,
        delta=delta,
        gamma=Decimal("0.001"),
        theta=Decimal("-10.0"),
        vega=vega,
        iv=iv,
    )


def _build_chains(
    spot: Decimal,
    near_exp: date,
    far_exp: date,
    near_atm_strike: Decimal,
    far_wing_pe_strikes: dict[
        Decimal, tuple[Decimal, Decimal, Decimal, Decimal, Decimal]
    ],  # strike: (bid, ask, delta, vega, iv)
    far_wing_ce_strikes: dict[Decimal, tuple[Decimal, Decimal, Decimal, Decimal, Decimal]],
    near_ce_quote: tuple[Decimal, Decimal, Decimal, Decimal, Decimal] = (
        Decimal("320.0"),
        Decimal("322.0"),
        Decimal("0.50"),
        Decimal("20.0"),
        Decimal("14.0"),
    ),
    near_pe_quote: tuple[Decimal, Decimal, Decimal, Decimal, Decimal] = (
        Decimal("310.0"),
        Decimal("312.0"),
        Decimal("-0.50"),
        Decimal("20.0"),
        Decimal("14.0"),
    ),
    far_atm_quote: tuple[Decimal, Decimal, Decimal, Decimal, Decimal] | None = None,
) -> tuple[OptionChain, OptionChain]:
    """Build mock near and far OptionChains."""
    near_strikes: dict[Decimal, OptionChainStrike] = {}
    near_strikes[near_atm_strike] = OptionChainStrike(
        ce=_make_leg(
            near_atm_strike,
            near_ce_quote[0],
            near_ce_quote[1],
            near_ce_quote[2],
            near_ce_quote[3],
            near_ce_quote[4],
        ),
        pe=_make_leg(
            near_atm_strike,
            near_pe_quote[0],
            near_pe_quote[1],
            near_pe_quote[2],
            near_pe_quote[3],
            near_pe_quote[4],
        ),
    )

    far_strikes: dict[Decimal, OptionChainStrike] = {}
    if far_atm_quote:
        far_strikes[near_atm_strike] = OptionChainStrike(
            ce=_make_leg(
                near_atm_strike,
                far_atm_quote[0],
                far_atm_quote[1],
                Decimal("0.52"),
                Decimal("25.0"),
                Decimal("13.5"),
            ),
            pe=_make_leg(
                near_atm_strike,
                far_atm_quote[0],
                far_atm_quote[1],
                Decimal("-0.48"),
                Decimal("25.0"),
                Decimal("13.5"),
            ),
        )
    else:
        # Default far ATM with tight quotes
        far_strikes[near_atm_strike] = OptionChainStrike(
            ce=_make_leg(
                near_atm_strike,
                Decimal("420.0"),
                Decimal("421.5"),
                Decimal("0.52"),
                Decimal("25.0"),
                Decimal("13.5"),
            ),
            pe=_make_leg(
                near_atm_strike,
                Decimal("390.0"),
                Decimal("391.5"),
                Decimal("-0.48"),
                Decimal("25.0"),
                Decimal("13.5"),
            ),
        )

    all_far_ks = set(far_wing_pe_strikes.keys()).union(set(far_wing_ce_strikes.keys()))
    for k in all_far_ks:
        pe_leg = None
        if k in far_wing_pe_strikes:
            q = far_wing_pe_strikes[k]
            pe_leg = _make_leg(k, q[0], q[1], q[2], q[3], q[4])

        ce_leg = None
        if k in far_wing_ce_strikes:
            q = far_wing_ce_strikes[k]
            ce_leg = _make_leg(k, q[0], q[1], q[2], q[3], q[4])

        far_strikes[k] = OptionChainStrike(ce=ce_leg, pe=pe_leg)

    chain_near = OptionChain(underlying_spot=spot, expiry=near_exp, strikes=near_strikes)
    chain_far = OptionChain(underlying_spot=spot, expiry=far_exp, strikes=far_strikes)
    return chain_near, chain_far


def test_quote_helpers_mid_and_spread() -> None:
    leg = _make_leg(
        Decimal("22600"),
        Decimal("100.0"),
        Decimal("102.5"),
        Decimal("0.2"),
        Decimal("10.0"),
        Decimal("13.0"),
    )
    assert mid(leg) == Decimal("101.25")
    assert spread_points(leg) == Decimal("2.5")

    # Missing bid raises
    bad_leg_bid = _make_leg(
        Decimal("22600"),
        Decimal("0.0"),
        Decimal("102.5"),
        Decimal("0.2"),
        Decimal("10.0"),
        Decimal("13.0"),
    )
    with pytest.raises(ValueError, match="missing or non-positive quote"):
        mid(bad_leg_bid)
    with pytest.raises(ValueError, match="missing or non-positive quote"):
        spread_points(bad_leg_bid)


def test_selects_video_structure() -> None:
    """Video structure: 22,700 straddle, ~600/600 wings selected under MONTHLY."""
    spot = Decimal("22700.0")
    near_exp = date(2026, 10, 27)
    far_exp = date(2026, 11, 23)
    atm = Decimal("22700")

    # Offer wings at 500, 600, 700
    # 600 put is 22100, 600 call is 23300
    pe_quotes = {
        Decimal("22100"): (
            Decimal("150.0"),
            Decimal("151.5"),
            Decimal("-0.22"),
            Decimal("23.0"),
            Decimal("14.0"),
        ),
        Decimal("22200"): (
            Decimal("180.0"),
            Decimal("182.0"),
            Decimal("-0.26"),
            Decimal("24.0"),
            Decimal("14.0"),
        ),
    }
    ce_quotes = {
        Decimal("23300"): (
            Decimal("155.0"),
            Decimal("156.5"),
            Decimal("0.22"),
            Decimal("23.0"),
            Decimal("13.5"),
        ),
        Decimal("23200"): (
            Decimal("185.0"),
            Decimal("187.0"),
            Decimal("0.26"),
            Decimal("24.0"),
            Decimal("13.5"),
        ),
    }

    chain_near, chain_far = _build_chains(spot, near_exp, far_exp, atm, pe_quotes, ce_quotes)
    selector = WingStructureSelector()
    res = selector.select(chain_near, chain_far, spot, MONTHLY)

    assert isinstance(res, CalendarStructure)
    assert res.short_strike == atm
    assert res.long_pe_wing.strike == Decimal("22100")
    assert res.long_ce_wing.strike == Decimal("23300")


def test_selects_reference_400_400_structure() -> None:
    """Reference trade (22,600 straddle, 22,200 PE / 23,000 CE wings, 400/400)."""
    spot = Decimal("22600.0")
    near_exp = date(2026, 10, 27)
    far_exp = date(2026, 11, 23)
    atm = Decimal("22600")

    pe_quotes = {
        Decimal("22200"): (
            Decimal("220.0"),
            Decimal("222.0"),
            Decimal("-0.25"),
            Decimal("25.0"),
            Decimal("14.0"),
        ),
    }
    ce_quotes = {
        Decimal("23000"): (
            Decimal("230.0"),
            Decimal("232.0"),
            Decimal("0.26"),
            Decimal("25.0"),
            Decimal("13.5"),
        ),
    }

    chain_near, chain_far = _build_chains(spot, near_exp, far_exp, atm, pe_quotes, ce_quotes)
    selector = WingStructureSelector()
    res = selector.select(chain_near, chain_far, spot, MONTHLY)

    assert isinstance(res, CalendarStructure)
    assert res.short_strike == Decimal("22600")
    assert res.long_pe_wing.strike == Decimal("22200")
    assert res.long_ce_wing.strike == Decimal("23000")


def test_no_entry_when_vega_cap_unreachable() -> None:
    """When all far wings have vega > 40, net vega > 20 cap -> NoEntry(failed_filter='vega_cap')."""
    spot = Decimal("22600.0")
    near_exp = date(2026, 10, 27)
    far_exp = date(2026, 11, 23)
    atm = Decimal("22600")

    # Near vega is 20 + 20 = 40 short. Far wings vega 45 + 45 = 90 -> net vega = +50 > 20.
    pe_quotes = {
        Decimal("22000"): (
            Decimal("150.0"),
            Decimal("151.0"),
            Decimal("-0.20"),
            Decimal("45.0"),
            Decimal("14.0"),
        ),
    }
    ce_quotes = {
        Decimal("23200"): (
            Decimal("150.0"),
            Decimal("151.0"),
            Decimal("0.20"),
            Decimal("45.0"),
            Decimal("14.0"),
        ),
    }

    chain_near, chain_far = _build_chains(spot, near_exp, far_exp, atm, pe_quotes, ce_quotes)
    selector = WingStructureSelector()
    res = selector.select(chain_near, chain_far, spot, MONTHLY)

    assert isinstance(res, NoEntry)
    assert res.failed_filter == "vega_cap"


def test_wing_strikes_multiples_of_100() -> None:
    """Verify wing strikes returned are exact multiples of 100."""
    spot = Decimal("22600.0")
    near_exp = date(2026, 10, 27)
    far_exp = date(2026, 11, 23)
    atm = Decimal("22600")

    pe_quotes = {
        Decimal("22000"): (
            Decimal("160.0"),
            Decimal("162.0"),
            Decimal("-0.20"),
            Decimal("24.0"),
            Decimal("14.0"),
        ),
    }
    ce_quotes = {
        Decimal("23200"): (
            Decimal("160.0"),
            Decimal("162.0"),
            Decimal("0.20"),
            Decimal("24.0"),
            Decimal("14.0"),
        ),
    }

    chain_near, chain_far = _build_chains(spot, near_exp, far_exp, atm, pe_quotes, ce_quotes)
    selector = WingStructureSelector()
    res = selector.select(chain_near, chain_far, spot, MONTHLY)

    assert isinstance(res, CalendarStructure)
    assert res.long_pe_wing.strike % Decimal("100") == Decimal("0")
    assert res.long_ce_wing.strike % Decimal("100") == Decimal("0")


def test_wide_spread_leg_rejected() -> None:
    """Far wing spread > 3.0 points rejected."""
    spot = Decimal("22600.0")
    near_exp = date(2026, 10, 27)
    far_exp = date(2026, 11, 23)
    atm = Decimal("22600")

    # Spread is 164.0 - 160.0 = 4.0 points (> 3.0)
    pe_quotes = {
        Decimal("22000"): (
            Decimal("160.0"),
            Decimal("164.0"),
            Decimal("-0.20"),
            Decimal("24.0"),
            Decimal("14.0"),
        ),
    }
    ce_quotes = {
        Decimal("23200"): (
            Decimal("160.0"),
            Decimal("161.0"),
            Decimal("0.20"),
            Decimal("24.0"),
            Decimal("14.0"),
        ),
    }

    chain_near, chain_far = _build_chains(spot, near_exp, far_exp, atm, pe_quotes, ce_quotes)
    selector = WingStructureSelector()
    res = selector.select(chain_near, chain_far, spot, MONTHLY)

    assert isinstance(res, NoEntry)
    assert res.failed_filter == "spread_tolerance"


def test_near_leg_wide_spread_rejected() -> None:
    """Near ATM leg spread > 3.0 points rejected."""
    spot = Decimal("22600.0")
    near_exp = date(2026, 10, 27)
    far_exp = date(2026, 11, 23)
    atm = Decimal("22600")

    pe_quotes = {
        Decimal("22000"): (
            Decimal("160.0"),
            Decimal("161.0"),
            Decimal("-0.20"),
            Decimal("24.0"),
            Decimal("14.0"),
        ),
    }
    ce_quotes = {
        Decimal("23200"): (
            Decimal("160.0"),
            Decimal("161.0"),
            Decimal("0.20"),
            Decimal("24.0"),
            Decimal("14.0"),
        ),
    }

    # Near CE has spread 325 - 320 = 5.0 points
    chain_near, chain_far = _build_chains(
        spot,
        near_exp,
        far_exp,
        atm,
        pe_quotes,
        ce_quotes,
        near_ce_quote=(
            Decimal("320.0"),
            Decimal("325.0"),
            Decimal("0.50"),
            Decimal("20.0"),
            Decimal("14.0"),
        ),
    )
    selector = WingStructureSelector()
    res = selector.select(chain_near, chain_far, spot, MONTHLY)

    assert isinstance(res, NoEntry)
    assert res.failed_filter == "spread_tolerance"


def test_missing_greeks_is_no_entry_not_exception() -> None:
    """Far wing leg with None vega returns NoEntry(failed_filter='missing_greeks') without exception."""
    spot = Decimal("22600.0")
    near_exp = date(2026, 10, 27)
    far_exp = date(2026, 11, 23)
    atm = Decimal("22600")

    pe_quotes = {
        Decimal("22000"): (
            Decimal("160.0"),
            Decimal("161.0"),
            Decimal("-0.20"),
            None,
            Decimal("14.0"),
        ),
    }
    ce_quotes = {
        Decimal("23200"): (
            Decimal("160.0"),
            Decimal("161.0"),
            Decimal("0.20"),
            Decimal("24.0"),
            Decimal("14.0"),
        ),
    }

    chain_near, chain_far = _build_chains(spot, near_exp, far_exp, atm, pe_quotes, ce_quotes)
    selector = WingStructureSelector()
    res = selector.select(chain_near, chain_far, spot, MONTHLY)

    assert isinstance(res, NoEntry)
    assert res.failed_filter == "missing_greeks"


def test_missing_quote_is_no_entry_not_exception() -> None:
    """Far wing leg with bid=0 returns NoEntry(failed_filter='missing_quote')."""
    spot = Decimal("22600.0")
    near_exp = date(2026, 10, 27)
    far_exp = date(2026, 11, 23)
    atm = Decimal("22600")

    pe_quotes = {
        Decimal("22000"): (
            Decimal("0.0"),
            Decimal("161.0"),
            Decimal("-0.20"),
            Decimal("24.0"),
            Decimal("14.0"),
        ),
    }
    ce_quotes = {
        Decimal("23200"): (
            Decimal("160.0"),
            Decimal("161.0"),
            Decimal("0.20"),
            Decimal("24.0"),
            Decimal("14.0"),
        ),
    }

    chain_near, chain_far = _build_chains(spot, near_exp, far_exp, atm, pe_quotes, ce_quotes)
    selector = WingStructureSelector()
    res = selector.select(chain_near, chain_far, spot, MONTHLY)

    assert isinstance(res, NoEntry)
    assert res.failed_filter == "missing_quote"


def test_no_quotable_wings_returns_no_entry() -> None:
    """No far wing strikes available in far chain returns NoEntry(failed_filter='missing_quote')."""
    spot = Decimal("22600.0")
    near_exp = date(2026, 10, 27)
    far_exp = date(2026, 11, 23)
    atm = Decimal("22600")

    chain_near, chain_far = _build_chains(spot, near_exp, far_exp, atm, {}, {})
    selector = WingStructureSelector()
    res = selector.select(chain_near, chain_far, spot, MONTHLY)

    assert isinstance(res, NoEntry)
    assert res.failed_filter == "missing_quote"


def test_ranking_prefers_fewest_failed_filters() -> None:
    """Candidate with 1 failed filter is ranked above candidate with 2 failed filters."""
    spot = Decimal("22600.0")
    near_exp = date(2026, 10, 27)
    far_exp = date(2026, 11, 23)
    atm = Decimal("22600")

    # 22000/23200 fails 1 filter (vega_cap only)
    # 21900/23300 fails 2 filters (vega_cap AND spread_tolerance)
    pe_quotes = {
        Decimal("22000"): (
            Decimal("160.0"),
            Decimal("161.0"),
            Decimal("-0.20"),
            Decimal("45.0"),
            Decimal("14.0"),
        ),
        Decimal("21900"): (
            Decimal("140.0"),
            Decimal("145.0"),
            Decimal("-0.18"),
            Decimal("45.0"),
            Decimal("14.0"),
        ),  # spread 5.0
    }
    ce_quotes = {
        Decimal("23200"): (
            Decimal("160.0"),
            Decimal("161.0"),
            Decimal("0.20"),
            Decimal("45.0"),
            Decimal("14.0"),
        ),
        Decimal("23300"): (
            Decimal("140.0"),
            Decimal("141.0"),
            Decimal("0.18"),
            Decimal("45.0"),
            Decimal("14.0"),
        ),
    }

    chain_near, chain_far = _build_chains(spot, near_exp, far_exp, atm, pe_quotes, ce_quotes)
    selector = WingStructureSelector()
    res = selector.select(chain_near, chain_far, spot, MONTHLY)

    assert isinstance(res, NoEntry)
    assert res.failed_filter == "vega_cap"


def test_tie_break_toward_start_wings() -> None:
    """When both 600/600 and 700/700 pass all filters, 600/600 is selected (closer to start)."""
    spot = Decimal("22600.0")
    near_exp = date(2026, 10, 27)
    far_exp = date(2026, 11, 23)
    atm = Decimal("22600")

    pe_quotes = {
        Decimal("22000"): (
            Decimal("160.0"),
            Decimal("161.5"),
            Decimal("-0.22"),
            Decimal("24.0"),
            Decimal("14.0"),
        ),  # 600
        Decimal("21900"): (
            Decimal("130.0"),
            Decimal("131.5"),
            Decimal("-0.18"),
            Decimal("22.0"),
            Decimal("14.0"),
        ),  # 700
    }
    ce_quotes = {
        Decimal("23200"): (
            Decimal("160.0"),
            Decimal("161.5"),
            Decimal("0.22"),
            Decimal("24.0"),
            Decimal("13.5"),
        ),  # 600
        Decimal("23300"): (
            Decimal("130.0"),
            Decimal("131.5"),
            Decimal("0.18"),
            Decimal("22.0"),
            Decimal("13.5"),
        ),  # 700
    }

    chain_near, chain_far = _build_chains(spot, near_exp, far_exp, atm, pe_quotes, ce_quotes)
    selector = WingStructureSelector()
    res = selector.select(chain_near, chain_far, spot, MONTHLY)

    assert isinstance(res, CalendarStructure)
    assert res.long_pe_wing.strike == Decimal("22000")
    assert res.long_ce_wing.strike == Decimal("23200")


def test_wings_move_inward_to_min_floor() -> None:
    """Asserts that selector explores down to min_wing_points=300 (e.g. 22300 PE / 22900 CE)."""
    spot = Decimal("22600.0")
    near_exp = date(2026, 10, 27)
    far_exp = date(2026, 11, 23)
    atm = Decimal("22600")

    # Only 300/300 wings are available
    pe_quotes = {
        Decimal("22300"): (
            Decimal("250.0"),
            Decimal("251.5"),
            Decimal("-0.28"),
            Decimal("26.0"),
            Decimal("14.0"),
        ),
    }
    ce_quotes = {
        Decimal("22900"): (
            Decimal("250.0"),
            Decimal("251.5"),
            Decimal("0.28"),
            Decimal("26.0"),
            Decimal("14.0"),
        ),
    }

    chain_near, chain_far = _build_chains(
        spot,
        near_exp,
        far_exp,
        atm,
        pe_quotes,
        ce_quotes,
        far_atm_quote=(
            Decimal("400.0"),
            Decimal("401.5"),
            Decimal("0.50"),
            Decimal("25.0"),
            Decimal("14.0"),
        ),
    )
    selector = WingStructureSelector()
    res = selector.select(chain_near, chain_far, spot, MONTHLY)

    assert isinstance(res, CalendarStructure)
    assert res.long_pe_wing.strike == Decimal("22300")
    assert res.long_ce_wing.strike == Decimal("22900")


def test_net_vega_over_cap_is_no_entry() -> None:
    """Explicit test asserting signed net vega over cap returns NoEntry with failed_filter='vega_cap'."""
    spot = Decimal("22600.0")
    near_exp = date(2026, 10, 27)
    far_exp = date(2026, 11, 23)
    atm = Decimal("22600")

    # Near vega is 40. Far wings vega is 35 + 35 = 70. Net vega = 30 > 20
    pe_quotes = {
        Decimal("22000"): (
            Decimal("160.0"),
            Decimal("161.0"),
            Decimal("-0.20"),
            Decimal("35.0"),
            Decimal("14.0"),
        ),
    }
    ce_quotes = {
        Decimal("23200"): (
            Decimal("160.0"),
            Decimal("161.0"),
            Decimal("0.20"),
            Decimal("35.0"),
            Decimal("14.0"),
        ),
    }

    chain_near, chain_far = _build_chains(spot, near_exp, far_exp, atm, pe_quotes, ce_quotes)
    selector = WingStructureSelector()
    res = selector.select(chain_near, chain_far, spot, MONTHLY)

    assert isinstance(res, NoEntry)
    assert res.failed_filter == "vega_cap"


def test_net_credit_violation_normalisation_non_zero_denominator() -> None:
    """Verify net debit structure computes violation without ZeroDivisionError."""
    spot = Decimal("22600.0")
    near_exp = date(2026, 10, 27)
    far_exp = date(2026, 11, 23)
    atm = Decimal("22600")

    # Near credit: 100 + 100 = 200. Far debit: 200 + 200 = 400. Net credit = -200 (debit).
    pe_quotes = {
        Decimal("22000"): (
            Decimal("200.0"),
            Decimal("201.0"),
            Decimal("-0.20"),
            Decimal("20.0"),
            Decimal("14.0"),
        ),
    }
    ce_quotes = {
        Decimal("23200"): (
            Decimal("200.0"),
            Decimal("201.0"),
            Decimal("0.20"),
            Decimal("20.0"),
            Decimal("14.0"),
        ),
    }

    chain_near, chain_far = _build_chains(
        spot,
        near_exp,
        far_exp,
        atm,
        pe_quotes,
        ce_quotes,
        near_ce_quote=(
            Decimal("100.0"),
            Decimal("101.0"),
            Decimal("0.50"),
            Decimal("20.0"),
            Decimal("14.0"),
        ),
        near_pe_quote=(
            Decimal("100.0"),
            Decimal("101.0"),
            Decimal("-0.50"),
            Decimal("20.0"),
            Decimal("14.0"),
        ),
    )
    selector = WingStructureSelector()
    res = selector.select(chain_near, chain_far, spot, MONTHLY)

    assert isinstance(res, NoEntry)
    assert res.failed_filter in ("net_credit", "risk_reward")


def test_missing_far_atm_quote_returns_no_entry() -> None:
    """Assert missing or non-positive far ATM quote returns NoEntry(failed_filter='missing_quote')."""
    spot = Decimal("22600.0")
    near_exp = date(2026, 10, 27)
    far_exp = date(2026, 11, 23)
    atm = Decimal("22600")

    pe_quotes = {
        Decimal("22000"): (
            Decimal("160.0"),
            Decimal("161.0"),
            Decimal("-0.20"),
            Decimal("24.0"),
            Decimal("14.0"),
        ),
    }
    ce_quotes = {
        Decimal("23200"): (
            Decimal("160.0"),
            Decimal("161.0"),
            Decimal("0.20"),
            Decimal("24.0"),
            Decimal("14.0"),
        ),
    }

    # Case 1: Non-positive far ATM quote (bid=0)
    chain_near, chain_far = _build_chains(
        spot,
        near_exp,
        far_exp,
        atm,
        pe_quotes,
        ce_quotes,
        far_atm_quote=(
            Decimal("0.0"),
            Decimal("401.0"),
            Decimal("0.50"),
            Decimal("25.0"),
            Decimal("14.0"),
        ),
    )
    selector = WingStructureSelector()
    res = selector.select(chain_near, chain_far, spot, MONTHLY)
    assert isinstance(res, NoEntry)
    assert res.failed_filter == "missing_quote"
    assert "Far ATM quote" in res.reason

    # Case 2: Far ATM strike missing completely
    del chain_far.strikes[atm]
    res2 = selector.select(chain_near, chain_far, spot, MONTHLY)
    assert isinstance(res2, NoEntry)
    assert res2.failed_filter == "missing_quote"
    assert "Far ATM quote" in res2.reason


def test_net_short_vega_rejected_by_vega_floor() -> None:
    """Assert net vega < 0 is rejected with failed_filter='vega_floor', while vega >= 0 passes."""
    spot = Decimal("22600.0")
    near_exp = date(2026, 10, 27)
    far_exp = date(2026, 11, 23)
    atm = Decimal("22600")

    # Near straddle vega: 20 + 20 = 40.
    # Far wings vega: 5 + 5 = 10 -> net vega = 10 - 40 = -30 (< 0).
    pe_quotes = {
        Decimal("22000"): (
            Decimal("160.0"),
            Decimal("161.0"),
            Decimal("-0.20"),
            Decimal("5.0"),
            Decimal("14.0"),
        ),
    }
    ce_quotes = {
        Decimal("23200"): (
            Decimal("160.0"),
            Decimal("161.0"),
            Decimal("0.20"),
            Decimal("5.0"),
            Decimal("14.0"),
        ),
    }

    chain_near, chain_far = _build_chains(spot, near_exp, far_exp, atm, pe_quotes, ce_quotes)
    selector = WingStructureSelector()
    res = selector.select(chain_near, chain_far, spot, MONTHLY)
    assert isinstance(res, NoEntry)
    assert res.failed_filter == "vega_floor"


def test_candidate_without_breakeven_is_ranked_not_raised(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Assert candidate raising InvalidStructureError in compute_metrics is ranked not raised."""
    from src.nifty_calendar.errors import InvalidStructureError

    spot = Decimal("22600.0")
    near_exp = date(2026, 10, 27)
    far_exp = date(2026, 11, 23)
    atm = Decimal("22600")

    pe_quotes = {
        Decimal("22000"): (
            Decimal("160.0"),
            Decimal("161.0"),
            Decimal("-0.20"),
            Decimal("24.0"),
            Decimal("14.0"),
        ),
    }
    ce_quotes = {
        Decimal("23200"): (
            Decimal("160.0"),
            Decimal("161.0"),
            Decimal("0.20"),
            Decimal("24.0"),
            Decimal("14.0"),
        ),
    }

    chain_near, chain_far = _build_chains(spot, near_exp, far_exp, atm, pe_quotes, ce_quotes)

    # Monkeypatch compute_metrics to raise InvalidStructureError
    def mock_metrics(*args: object, **kwargs: object) -> object:
        raise InvalidStructureError("No lower breakeven crossing found on grid")

    monkeypatch.setattr("src.nifty_calendar.selector.compute_metrics", mock_metrics)

    selector = WingStructureSelector()
    res = selector.select(chain_near, chain_far, spot, MONTHLY)
    assert isinstance(res, NoEntry)
    assert res.failed_filter == "no_breakeven"


def _two_strike_chains(spot: Decimal) -> tuple[OptionChain, OptionChain]:
    """Reference 400/400 chains with a second, adjacent short strike (22,650) and its wings."""
    pe = (Decimal("220.0"), Decimal("222.0"), Decimal("-0.25"), Decimal("25.0"), Decimal("14.0"))
    ce = (Decimal("230.0"), Decimal("232.0"), Decimal("0.26"), Decimal("25.0"), Decimal("13.5"))
    near, far = _build_chains(
        spot,
        date(2026, 10, 27),
        date(2026, 11, 23),
        Decimal("22600"),
        {Decimal("22200"): pe, Decimal("22250"): pe},
        {Decimal("23000"): ce, Decimal("23050"): ce},
    )
    adjacent = Decimal("22650")
    near.strikes[adjacent] = near.strikes[Decimal("22600")]
    far.strikes[adjacent] = far.strikes[Decimal("22600")]
    return near, far


def test_excluded_short_strike_moves_entry_to_adjacent_strike() -> None:
    """A same-day collision at 22,650 re-enters at 22,600 with the wings re-anchored."""
    spot = Decimal("22640")
    near, far = _two_strike_chains(spot)

    res = WingStructureSelector().select(near, far, spot, MONTHLY, frozenset({Decimal("22650")}))

    assert isinstance(res, CalendarStructure) and res.short_strike == Decimal("22600")
    assert res.long_pe_wing.strike == Decimal("22200")
    assert res.long_ce_wing.strike == Decimal("23000")


def test_exclusion_still_applies_entry_filters() -> None:
    """The adjacent strike is not exempt: here it fails breakeven symmetry and is refused."""
    spot = Decimal("22660")
    near, far = _two_strike_chains(spot)
    selector = WingStructureSelector()

    base = selector.select(near, far, spot, MONTHLY)
    moved = selector.select(near, far, spot, MONTHLY, frozenset({Decimal("22650")}))

    assert isinstance(base, CalendarStructure) and base.short_strike == Decimal("22650")
    assert isinstance(moved, NoEntry) and moved.failed_filter == "breakeven_symmetry"


def test_exact_midpoint_spot_picks_lower_strike() -> None:
    """Spot midway between two strikes resolves to the lower one, deterministically."""
    spot = Decimal("22625")
    near, far = _two_strike_chains(spot)

    res = WingStructureSelector().select(near, far, spot, MONTHLY)

    assert isinstance(res, CalendarStructure) and res.short_strike == Decimal("22600")


def test_excluding_every_near_strike_is_no_entry() -> None:
    """With no eligible strike left the selector refuses rather than raising."""
    spot = Decimal("22600")
    near, far = _build_chains(spot, date(2026, 10, 27), date(2026, 11, 23), spot, {}, {})

    res = WingStructureSelector().select(near, far, spot, MONTHLY, frozenset({spot}))

    assert isinstance(res, NoEntry) and res.failed_filter == "missing_quote"


def test_excluding_a_strike_not_in_the_chain_changes_nothing() -> None:
    """A stale excluded strike is ignored rather than raising."""
    spot = Decimal("22600")
    near, far = _two_strike_chains(spot)

    res = WingStructureSelector().select(near, far, spot, MONTHLY, frozenset({Decimal("99999")}))

    assert isinstance(res, CalendarStructure) and res.short_strike == Decimal("22600")

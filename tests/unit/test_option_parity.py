"""Put-call parity check on the recorded Upstox option chain fixture.

Policy and tolerances: DECISIONS.md "Greeks / option-chain correctness
checks — parity + BS reference assumptions" (2026-10-02). The fixture goes
through ``parse_upstox_option_chain`` so parser-side errors (CE/PE or field
swap, mis-keyed strike, bad Decimal cast) surface here, not just bad broker
data.

The bands only need to clear microstructure noise: the target failure modes
produce residuals in the hundreds, observed fixture residuals max out at ~9.
"""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from src.client.upstox_market import parse_upstox_option_chain
from src.models.options import OptionChain, OptionChainStrike, OptionLeg
from tests.helpers.bs_reference import (
    ParityPoint,
    fit_implied_forward,
    parity_points,
    parity_residuals,
)

_FIXTURE = (
    Path(__file__).parent.parent
    / "fixtures"
    / "responses"
    / "option_chain"
    / "nifty_chain_2026-04-07.json"
)

MAX_STRIKE_DISTANCE = 1500.0
SLOPE_TOLERANCE = 0.01
RESIDUAL_PAD = 2.0
RESIDUAL_FLOOR = 8.0
MAX_BREACH_FRACTION = 0.05


@pytest.fixture(scope="module")
def chain() -> OptionChain:
    raw = json.loads(_FIXTURE.read_text())
    return parse_upstox_option_chain(raw["response"]["data"])


def _band(point: ParityPoint) -> float:
    return max(point.half_spread + RESIDUAL_PAD, RESIDUAL_FLOOR)


def _parity_violations(points: list[ParityPoint]) -> list[str]:
    """Apply the DECISIONS.md parity asserts; one message per failed rule."""
    fit = fit_implied_forward(points)
    residuals = parity_residuals(points, fit)
    violations: list[str] = []
    if abs(fit.slope + 1) > SLOPE_TOLERANCE:
        violations.append(f"slope {fit.slope:.4f} not within {SLOPE_TOLERANCE} of -1")
    breaches = sum(abs(r) > _band(p) for p, r in zip(points, residuals, strict=True))
    if breaches > MAX_BREACH_FRACTION * len(points):
        violations.append(f"{breaches}/{len(points)} strikes breach the residual band")
    # OLS residuals sum to zero overall: sign bias is only meaningful per wing.
    for wing, in_wing in (
        ("below F", lambda k: k < fit.forward),
        ("above F", lambda k: k > fit.forward),
    ):
        signs = {r > 0 for p, r in zip(points, residuals, strict=True) if in_wing(p.strike)}
        if len(signs) == 1:
            violations.append(f"residuals {wing} all one sign")
    return violations


def _leg(strike: int, bid: str, ask: str) -> OptionLeg:
    return OptionLeg(
        ltp=Decimal(bid),
        bid=Decimal(bid),
        ask=Decimal(ask),
        oi=0,
        volume=0,
        delta=None,
        gamma=None,
        theta=None,
        vega=None,
        iv=None,
        strike=Decimal(strike),
    )


def _swap_ce_pe(chain: OptionChain) -> OptionChain:
    swapped = {k: OptionChainStrike(ce=row.pe, pe=row.ce) for k, row in chain.strikes.items()}
    return chain.model_copy(update={"strikes": swapped})


# --- fixture: parity holds --------------------------------------------------


def test_fixture_filter_keeps_sixty_two_sided_strikes(
    chain: OptionChain,
) -> None:
    assert len(parity_points(chain, MAX_STRIKE_DISTANCE)) == 60


def test_fixture_satisfies_put_call_parity(chain: OptionChain) -> None:
    assert _parity_violations(parity_points(chain, MAX_STRIKE_DISTANCE)) == []


def test_fixture_implied_forward_is_near_spot(chain: OptionChain) -> None:
    fit = fit_implied_forward(parity_points(chain, MAX_STRIKE_DISTANCE))
    assert abs(fit.forward - float(chain.underlying_spot)) < 25


def test_fixture_quotes_are_not_crossed(chain: OptionChain) -> None:
    """ask >= bid on every two-sided leg — the guard for a bid/ask field swap,
    which parity on mids cannot see."""
    crossed = [
        (k, side)
        for k, row in chain.strikes.items()
        for side, leg in (("CE", row.ce), ("PE", row.pe))
        if leg is not None and leg.bid > 0 and leg.ask > 0 and leg.ask < leg.bid
    ]
    assert crossed == []


# --- error / edge cases -----------------------------------------------------


def test_ce_pe_swap_fails_parity(chain: OptionChain) -> None:
    violations = _parity_violations(parity_points(_swap_ce_pe(chain), MAX_STRIKE_DISTANCE))
    assert any(v.startswith("slope") for v in violations)


def test_ce_mis_keyed_by_one_strike_fails_parity(chain: OptionChain) -> None:
    strikes = sorted(chain.strikes)
    shifted = {
        k: OptionChainStrike(ce=chain.strikes[nxt].ce, pe=chain.strikes[k].pe)
        for k, nxt in zip(strikes, strikes[1:], strict=False)
    }
    mis_keyed = chain.model_copy(update={"strikes": shifted})
    assert _parity_violations(parity_points(mis_keyed, MAX_STRIKE_DISTANCE)) != []


def test_one_sided_strike_is_filtered_out() -> None:
    chain = OptionChain(
        underlying_spot=Decimal("22000"),
        expiry=date(2026, 4, 7),
        strikes={
            Decimal(21900): OptionChainStrike(
                ce=_leg(21900, "120", "121"), pe=_leg(21900, "20", "21")
            ),
            Decimal(22000): OptionChainStrike(
                ce=_leg(22000, "0", "61"), pe=_leg(22000, "60", "61")
            ),
            Decimal(22100): OptionChainStrike(ce=_leg(22100, "20", "21"), pe=None),
            Decimal(22200): OptionChainStrike(
                ce=_leg(22200, "5", "6"), pe=_leg(22200, "205", "206")
            ),
        },
    )
    assert [p.strike for p in parity_points(chain, MAX_STRIKE_DISTANCE)] == [
        21900.0,
        22200.0,
    ]


def test_strike_beyond_max_distance_is_filtered_out() -> None:
    chain = OptionChain(
        underlying_spot=Decimal("22000"),
        expiry=date(2026, 4, 7),
        strikes={
            Decimal(20000): OptionChainStrike(
                ce=_leg(20000, "1990", "2010"), pe=_leg(20000, "1", "2")
            ),
            Decimal(22000): OptionChainStrike(
                ce=_leg(22000, "60", "61"), pe=_leg(22000, "60", "61")
            ),
        },
    )
    assert [p.strike for p in parity_points(chain, MAX_STRIKE_DISTANCE)] == [22000.0]


def test_fit_recovers_exact_parity_forward() -> None:
    discount, forward = 0.999, 22050.0
    points = [
        ParityPoint(
            strike=k,
            call_mid=discount * (forward - k) + 50,
            put_mid=50.0,
            half_spread=0.5,
        )
        for k in (21800.0, 21900.0, 22000.0, 22100.0)
    ]
    fit = fit_implied_forward(points)
    assert fit.slope == pytest.approx(-discount)
    assert fit.forward == pytest.approx(forward)
    assert parity_residuals(points, fit) == pytest.approx([0.0] * 4, abs=1e-9)


def test_fit_requires_two_distinct_strikes() -> None:
    point = ParityPoint(strike=22000.0, call_mid=60.0, put_mid=55.0, half_spread=0.5)
    with pytest.raises(ValueError, match="two distinct strikes"):
        fit_implied_forward([point, point])

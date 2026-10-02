"""Black-Scholes golden test on Upstox-reported Greeks.

Policy and tolerances: DECISIONS.md "Greeks / option-chain correctness
checks — parity + BS reference assumptions" (2026-10-02). The reference pins
Upstox's empirically fitted convention (spot BSM, r = 0.05, q = 0, calendar
time to 15:30 IST, carry-free theta), not an independent "true" model — the
point is that a convention drift or a parser unit error fails loudly.

Tolerances are ~3-5x the max observed error on the 2026-04-07 fixture
(delta 0.0009, vega 0.015, theta 0.038, gamma 0.00005). Every
``nifty_chain_*.json`` fixture is checked, so a longer-DTE snapshot slots in.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from src.client.upstox_market import parse_upstox_option_chain
from src.models.options import OptionChain, OptionChainStrike, OptionLeg
from tests.helpers.bs_reference import bs_greeks, golden_legs, year_fraction

_FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "responses" / "option_chain"
_FIXTURES = sorted(_FIXTURE_DIR.glob("nifty_chain_*.json"))

RATE = 0.05
ATM_WIDTH = 5
TOLERANCES = {"delta": 0.005, "gamma": 0.0001, "vega": 0.05, "theta": 0.10}


def _load(path: Path) -> tuple[OptionChain, datetime]:
    raw = json.loads(path.read_text())
    chain = parse_upstox_option_chain(raw["response"]["data"])
    return chain, datetime.fromisoformat(raw["recorded_at"])


@pytest.fixture(scope="module")
def snapshot() -> tuple[OptionChain, datetime]:
    return _load(_FIXTURE_DIR / "nifty_chain_2026-04-07.json")


def _greek_violations(
    chain: OptionChain, recorded_at: datetime, *, carry_theta: bool = False
) -> list[str]:
    """Compare each ATM-window leg to the BS reference; one message per breach."""
    t = year_fraction(recorded_at, chain.expiry)
    spot = float(chain.underlying_spot)
    violations: list[str] = []
    for g in golden_legs(chain, ATM_WIDTH):
        ref = bs_greeks(spot, g.strike, g.iv_pct, t, RATE, g.is_call, carry_theta=carry_theta)
        label = f"{g.strike:.0f}{'CE' if g.is_call else 'PE'}"
        for name, tol in TOLERANCES.items():
            reported = getattr(g.leg, name)
            if reported is None:
                violations.append(f"{label} {name} missing")
            elif abs(float(reported) - getattr(ref, name)) > tol:
                violations.append(f"{label} {name} {reported} vs ref {getattr(ref, name):.5f}")
    return violations


def _scale_vega(chain: OptionChain, factor: int) -> OptionChain:
    def scaled(leg: OptionLeg | None) -> OptionLeg | None:
        if leg is None or leg.vega is None:
            return leg
        return leg.model_copy(update={"vega": leg.vega * factor})

    strikes = {
        k: OptionChainStrike(ce=scaled(row.ce), pe=scaled(row.pe))
        for k, row in chain.strikes.items()
    }
    return chain.model_copy(update={"strikes": strikes})


def _leg(strike: int, iv: str) -> OptionLeg:
    return OptionLeg(
        ltp=Decimal("10"),
        bid=Decimal("10"),
        ask=Decimal("11"),
        oi=0,
        volume=0,
        delta=None,
        gamma=None,
        theta=None,
        vega=None,
        iv=Decimal(iv),
        strike=Decimal(strike),
    )


# --- fixtures: Upstox Greeks match the reference -----------------------------


@pytest.mark.parametrize("path", _FIXTURES, ids=lambda p: p.stem)
def test_fixture_greeks_match_bs_reference(path: Path) -> None:
    chain, recorded_at = _load(path)
    assert golden_legs(chain, ATM_WIDTH), "ATM window selected no legs"
    assert _greek_violations(chain, recorded_at) == []


def test_fixture_atm_window_selects_twenty_two_legs(
    snapshot: tuple[OptionChain, datetime],
) -> None:
    chain, _ = snapshot
    assert len(golden_legs(chain, ATM_WIDTH)) == 22


def test_year_fraction_counts_calendar_time_to_1530_ist() -> None:
    recorded_at = datetime(2026, 4, 2, 12, 4, 54, tzinfo=timezone(timedelta(hours=5, minutes=30)))
    expected = (5 * 86400 + 3 * 3600 + 25 * 60 + 6) / (365 * 86400)
    assert year_fraction(recorded_at, date(2026, 4, 7)) == pytest.approx(expected)


def test_bs_reference_delta_satisfies_put_call_identity() -> None:
    call = bs_greeks(22266.25, 22300.0, 14.0, 0.014, RATE, True)
    put = bs_greeks(22266.25, 22300.0, 14.0, 0.014, RATE, False)
    assert call.delta - put.delta == pytest.approx(1.0)
    assert (call.gamma, call.vega, call.theta) == pytest.approx((put.gamma, put.vega, put.theta))


# --- error / edge cases -------------------------------------------------------


def test_zero_iv_leg_is_excluded() -> None:
    chain = OptionChain(
        underlying_spot=Decimal("22000"),
        expiry=date(2026, 4, 7),
        strikes={Decimal(22000): OptionChainStrike(ce=_leg(22000, "14.5"), pe=_leg(22000, "0"))},
    )
    assert [(g.strike, g.is_call) for g in golden_legs(chain, ATM_WIDTH)] == [(22000.0, True)]


def test_vega_per_unit_vol_fails(snapshot: tuple[OptionChain, datetime]) -> None:
    chain, recorded_at = snapshot
    violations = _greek_violations(_scale_vega(chain, 100), recorded_at)
    assert violations and all(" vega " in v for v in violations)


def test_textbook_carry_theta_does_not_fit(snapshot: tuple[OptionChain, datetime]) -> None:
    """Upstox theta omits -rKe^(-rT)N(d2); a full-BSM reference must breach.

    Only-theta breaches assume delta/gamma/vega already pass on this fixture
    (``test_fixture_greeks_match_bs_reference``); the carry flag leaves d1 alone.
    """
    chain, recorded_at = snapshot
    violations = _greek_violations(chain, recorded_at, carry_theta=True)
    assert violations and all(" theta " in v for v in violations)


def test_year_fraction_rejects_naive_timestamp() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        year_fraction(datetime(2026, 4, 2, 12, 0), date(2026, 4, 7))


def test_year_fraction_rejects_snapshot_after_expiry_close() -> None:
    after_close = datetime(2026, 4, 7, 10, 1, tzinfo=timezone.utc)  # 15:31 IST
    with pytest.raises(ValueError, match="not before expiry"):
        year_fraction(after_close, date(2026, 4, 7))


def test_bs_greeks_rejects_zero_iv() -> None:
    with pytest.raises(ValueError, match="must be positive"):
        bs_greeks(22000.0, 22000.0, 0.0, 0.014, RATE, True)

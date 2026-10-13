"""Unit tests for Black-76 pricing, payoff calculation, and calendar metrics."""

from datetime import date
from decimal import Decimal

import pytest

from src.models.portfolio import AssetType, Direction
from src.nifty_calendar.models import CalendarLeg, CalendarStructure
from src.nifty_calendar.payoff import (
    compute_metrics,
    derive_far_carry_from_atm,
    payoff_at,
)
from src.nifty_calendar.pricing import b76_price, solve_iv


def _make_video_fixture() -> tuple[CalendarStructure, Decimal, Decimal, int]:
    """Fixture matching TM Trading 22,700 straddle with 22,100 PE / 23,200 CE wings."""
    near_expiry = date(2026, 10, 27)
    far_expiry = date(2026, 11, 24)
    short_ce = CalendarLeg(
        instrument_key="NIFTY26OCT22700CE",
        strike=Decimal("22700"),
        option_type=AssetType.CE,
        expiry=near_expiry,
        side=Direction.SELL,
        qty_lots=1,
        entry_price=Decimal("310.0"),
        delta=Decimal("0.50"),
        vega=Decimal("16.0"),
        iv=Decimal("13.0"),
    )
    short_pe = CalendarLeg(
        instrument_key="NIFTY26OCT22700PE",
        strike=Decimal("22700"),
        option_type=AssetType.PE,
        expiry=near_expiry,
        side=Direction.SELL,
        qty_lots=1,
        entry_price=Decimal("270.0"),
        delta=Decimal("-0.50"),
        vega=Decimal("16.0"),
        iv=Decimal("13.5"),
    )
    long_ce = CalendarLeg(
        instrument_key="NIFTY26NOV23200CE",
        strike=Decimal("23200"),
        option_type=AssetType.CE,
        expiry=far_expiry,
        side=Direction.BUY,
        qty_lots=1,
        entry_price=Decimal("205.0"),
        delta=Decimal("0.22"),
        vega=Decimal("22.5"),
        iv=Decimal("13.0"),
    )
    long_pe = CalendarLeg(
        instrument_key="NIFTY26NOV22100PE",
        strike=Decimal("22100"),
        option_type=AssetType.PE,
        expiry=far_expiry,
        side=Direction.BUY,
        qty_lots=1,
        entry_price=Decimal("225.0"),
        delta=Decimal("-0.18"),
        vega=Decimal("22.5"),
        iv=Decimal("15.0"),
    )
    structure = CalendarStructure(
        short_ce=short_ce,
        short_pe=short_pe,
        long_ce_wing=long_ce,
        long_pe_wing=long_pe,
    )
    spot = Decimal("22700")
    far_carry = Decimal("-60.0")
    lot_size = 65
    return structure, spot, far_carry, lot_size


def test_b76_at_or_after_expiry_returns_intrinsic() -> None:
    """Assert b76_price returns intrinsic value when t_years <= 0 or vol <= 0."""
    # At expiry (t = 0.0)
    assert b76_price(AssetType.CE, forward=22800.0, strike=22700.0, t_years=0.0, vol=0.15) == 100.0
    assert b76_price(AssetType.CE, forward=22600.0, strike=22700.0, t_years=0.0, vol=0.15) == 0.0
    assert b76_price(AssetType.PE, forward=22600.0, strike=22700.0, t_years=0.0, vol=0.15) == 100.0
    assert b76_price(AssetType.PE, forward=22800.0, strike=22700.0, t_years=0.0, vol=0.15) == 0.0

    # After expiry (t < 0.0)
    assert b76_price("CE", forward=22900.0, strike=22700.0, t_years=-0.1, vol=0.15) == 200.0
    assert b76_price("PE", forward=22500.0, strike=22700.0, t_years=-0.1, vol=0.15) == 200.0

    # Zero volatility
    assert b76_price("CE", forward=22800.0, strike=22700.0, t_years=0.1, vol=0.0) == 100.0
    assert b76_price("PE", forward=22600.0, strike=22700.0, t_years=0.1, vol=0.0) == 100.0


def test_solve_iv_round_trip_and_invalid_price_raises() -> None:
    """Assert solve_iv round-trips b76_price and raises ValueError on invalid inputs."""
    forward = 22700.0
    strike = 23000.0
    t_years = 0.1
    target_vol = 0.20

    price = b76_price(AssetType.CE, forward=forward, strike=strike, t_years=t_years, vol=target_vol)
    solved_iv = solve_iv(AssetType.CE, forward=forward, strike=strike, t_years=t_years, price=price)
    assert abs(solved_iv - target_vol) < 1e-4

    # Invalid inputs
    with pytest.raises(ValueError, match="t_years must be positive"):
        solve_iv(AssetType.CE, forward=forward, strike=strike, t_years=0.0, price=price)

    with pytest.raises(ValueError, match="price must be positive"):
        solve_iv(AssetType.CE, forward=forward, strike=strike, t_years=t_years, price=0.0)

    with pytest.raises(ValueError, match="is below intrinsic value"):
        # Forward 23000, strike 22000 has intrinsic 1000 for CE
        solve_iv(AssetType.CE, forward=23000.0, strike=22000.0, t_years=t_years, price=500.0)


def test_payoff_at_far_carry_is_required() -> None:
    """Assert far_carry and lot_size are required keyword-only arguments for payoff_at."""
    structure, spot, far_carry, lot_size = _make_video_fixture()

    # Omitting far_carry raises TypeError
    with pytest.raises(TypeError):
        payoff_at(structure, spot, lot_size=lot_size)  # type: ignore[call-arg]

    # Omitting lot_size raises TypeError
    with pytest.raises(TypeError):
        payoff_at(structure, spot, far_carry=far_carry)  # type: ignore[call-arg]

    # derive_far_carry_from_atm verification
    carry = derive_far_carry_from_atm(
        far_atm_strike=Decimal("22700"),
        far_atm_ce_mid=Decimal("350"),
        far_atm_pe_mid=Decimal("290"),
        spot=Decimal("22700"),
    )
    assert carry == Decimal("60")


def test_breakevens_shift_with_far_carry() -> None:
    """Assert breakevens shift when far_carry increases forward price."""
    structure, spot, _, lot_size = _make_video_fixture()

    m_zero = compute_metrics(structure, spot, far_carry=Decimal("0"), lot_size=lot_size)
    m_high = compute_metrics(structure, spot, far_carry=Decimal("100"), lot_size=lot_size)

    assert m_high.breakeven_high != m_zero.breakeven_high
    assert m_high.breakeven_low != m_zero.breakeven_low
    assert m_high.breakeven_high > m_zero.breakeven_high
    assert m_high.breakeven_low > m_zero.breakeven_low


def test_metrics_match_video_sample() -> None:
    """Assert metrics match TM Trading video sample (22,700 straddle, 22,100 PE / 23,200 CE wings)."""
    structure, spot, far_carry, lot_size = _make_video_fixture()
    metrics = compute_metrics(structure, spot, far_carry=far_carry, lot_size=lot_size)

    # Net delta near 0 (sample 0.04)
    assert abs(metrics.net_delta) < Decimal("0.10")
    assert metrics.net_delta == Decimal("0.04")

    # Net vega ~13
    assert abs(metrics.net_vega - Decimal("13.0")) < Decimal("0.5")

    # Breakevens approx 2.5% / 2.4% within tolerance
    assert abs(metrics.breakeven_low_pct - Decimal("2.5")) <= Decimal("0.3")
    assert abs(metrics.breakeven_high_pct - Decimal("2.4")) <= Decimal("0.3")

    # Risk-reward >= 0.75 floor
    assert metrics.risk_reward >= Decimal("0.75")

    # Net credit collected
    assert metrics.net_credit_per_unit > Decimal("0")


def test_iv_shift_directional() -> None:
    """Assert +3% IV raises payoff and -3% IV lowers payoff (net long vega structure)."""
    structure, spot, far_carry, lot_size = _make_video_fixture()

    payoff_base = payoff_at(
        structure, spot, iv_shift=Decimal("0"), far_carry=far_carry, lot_size=lot_size
    )
    payoff_up = payoff_at(
        structure, spot, iv_shift=Decimal("3.0"), far_carry=far_carry, lot_size=lot_size
    )
    payoff_down = payoff_at(
        structure, spot, iv_shift=Decimal("-3.0"), far_carry=far_carry, lot_size=lot_size
    )

    assert payoff_up > payoff_base
    assert payoff_down < payoff_base

"""Unit tests for Nifty calendar models, invariants, and Greeks normalization."""

from dataclasses import FrozenInstanceError
from datetime import date
from decimal import Decimal

import pytest

from src.models.portfolio import AssetType, Direction
from src.nifty_calendar.errors import InvalidStructureError, MissingGreeksError
from src.nifty_calendar.models import CalendarLeg, CalendarStructure, StructureMetrics
from src.nifty_calendar.payoff import compute_metrics


def _make_leg(
    instrument_key: str = "NIFTY26OCT22700CE",
    strike: Decimal = Decimal("22700"),
    option_type: AssetType = AssetType.CE,
    expiry: date = date(2026, 10, 27),
    side: Direction = Direction.SELL,
    qty_lots: int = 1,
    entry_price: Decimal = Decimal("280.0"),
    delta: Decimal = Decimal("0.50"),
    vega: Decimal = Decimal("16.0"),
    iv: Decimal = Decimal("13.0"),
) -> CalendarLeg:
    """Helper to construct a valid CalendarLeg."""
    return CalendarLeg(
        instrument_key=instrument_key,
        strike=strike,
        option_type=option_type,
        expiry=expiry,
        side=side,
        qty_lots=qty_lots,
        entry_price=entry_price,
        delta=delta,
        vega=vega,
        iv=iv,
    )


def _make_structure(
    qty_lots: int = 1,
    near_expiry: date = date(2026, 10, 27),
    far_expiry: date = date(2026, 11, 24),
) -> CalendarStructure:
    """Helper to construct a valid CalendarStructure."""
    short_ce = _make_leg(
        instrument_key="NIFTY26OCT22700CE",
        strike=Decimal("22700"),
        option_type=AssetType.CE,
        expiry=near_expiry,
        side=Direction.SELL,
        qty_lots=qty_lots,
        entry_price=Decimal("280.0"),
        delta=Decimal("0.50"),
        vega=Decimal("16.0"),
        iv=Decimal("13.0"),
    )
    short_pe = _make_leg(
        instrument_key="NIFTY26OCT22700PE",
        strike=Decimal("22700"),
        option_type=AssetType.PE,
        expiry=near_expiry,
        side=Direction.SELL,
        qty_lots=qty_lots,
        entry_price=Decimal("260.0"),
        delta=Decimal("-0.50"),
        vega=Decimal("16.0"),
        iv=Decimal("13.5"),
    )
    long_ce = _make_leg(
        instrument_key="NIFTY26NOV23200CE",
        strike=Decimal("23200"),
        option_type=AssetType.CE,
        expiry=far_expiry,
        side=Direction.BUY,
        qty_lots=qty_lots,
        entry_price=Decimal("150.0"),
        delta=Decimal("0.22"),
        vega=Decimal("22.5"),
        iv=Decimal("14.0"),
    )
    long_pe = _make_leg(
        instrument_key="NIFTY26NOV22100PE",
        strike=Decimal("22100"),
        option_type=AssetType.PE,
        expiry=far_expiry,
        side=Direction.BUY,
        qty_lots=qty_lots,
        entry_price=Decimal("140.0"),
        delta=Decimal("-0.18"),
        vega=Decimal("22.5"),
        iv=Decimal("14.5"),
    )
    return CalendarStructure(
        short_ce=short_ce,
        short_pe=short_pe,
        long_ce_wing=long_ce,
        long_pe_wing=long_pe,
    )


def test_models_frozen_and_properties() -> None:
    """Assert models are frozen dataclasses and structure properties compute correctly."""
    leg = _make_leg()
    with pytest.raises(FrozenInstanceError):
        leg.strike = Decimal("22800")  # type: ignore[misc]

    structure = _make_structure()
    with pytest.raises(FrozenInstanceError):
        structure.short_ce = leg  # type: ignore[misc]

    assert len(structure.legs) == 4
    assert structure.legs == (
        structure.short_ce,
        structure.short_pe,
        structure.long_ce_wing,
        structure.long_pe_wing,
    )
    assert structure.near_expiry == date(2026, 10, 27)
    assert structure.far_expiry == date(2026, 11, 24)
    assert structure.short_strike == Decimal("22700")
    assert structure.qty_lots == 1

    # net_credit_per_unit = (280 + 260) - (150 + 140) = 540 - 290 = 250
    assert structure.net_credit_per_unit == Decimal("250.0")
    assert structure.net_credit_per_lot(65) == Decimal("16250.0")


def test_models_invalid_structure_raises() -> None:
    """Assert invalid leg or structure constraints raise InvalidStructureError."""
    # Invalid option_type on leg
    with pytest.raises(InvalidStructureError):
        _make_leg(option_type=AssetType.EQUITY)  # type: ignore[arg-type]

    # Non-positive qty_lots on leg
    with pytest.raises(InvalidStructureError):
        _make_leg(qty_lots=0)

    # Short legs must have side=SELL
    with pytest.raises(InvalidStructureError):
        CalendarStructure(
            short_ce=_make_leg(side=Direction.BUY),
            short_pe=_make_leg(option_type=AssetType.PE),
            long_ce_wing=_make_leg(side=Direction.BUY, expiry=date(2026, 11, 24)),
            long_pe_wing=_make_leg(
                side=Direction.BUY, option_type=AssetType.PE, expiry=date(2026, 11, 24)
            ),
        )

    # Long wings must have side=BUY
    with pytest.raises(InvalidStructureError):
        CalendarStructure(
            short_ce=_make_leg(),
            short_pe=_make_leg(option_type=AssetType.PE),
            long_ce_wing=_make_leg(side=Direction.SELL, expiry=date(2026, 11, 24)),
            long_pe_wing=_make_leg(
                side=Direction.BUY, option_type=AssetType.PE, expiry=date(2026, 11, 24)
            ),
        )

    # Near expiries must match
    with pytest.raises(InvalidStructureError):
        CalendarStructure(
            short_ce=_make_leg(expiry=date(2026, 10, 27)),
            short_pe=_make_leg(option_type=AssetType.PE, expiry=date(2026, 10, 20)),
            long_ce_wing=_make_leg(side=Direction.BUY, expiry=date(2026, 11, 24)),
            long_pe_wing=_make_leg(
                side=Direction.BUY, option_type=AssetType.PE, expiry=date(2026, 11, 24)
            ),
        )

    # Near strikes must match (straddle)
    with pytest.raises(InvalidStructureError):
        CalendarStructure(
            short_ce=_make_leg(strike=Decimal("22700")),
            short_pe=_make_leg(option_type=AssetType.PE, strike=Decimal("22800")),
            long_ce_wing=_make_leg(side=Direction.BUY, expiry=date(2026, 11, 24)),
            long_pe_wing=_make_leg(
                side=Direction.BUY, option_type=AssetType.PE, expiry=date(2026, 11, 24)
            ),
        )

    # Far expiries must match
    with pytest.raises(InvalidStructureError):
        CalendarStructure(
            short_ce=_make_leg(),
            short_pe=_make_leg(option_type=AssetType.PE),
            long_ce_wing=_make_leg(side=Direction.BUY, expiry=date(2026, 11, 24)),
            long_pe_wing=_make_leg(
                side=Direction.BUY, option_type=AssetType.PE, expiry=date(2026, 11, 17)
            ),
        )

    # Near expiry must be strictly before far expiry
    with pytest.raises(InvalidStructureError):
        CalendarStructure(
            short_ce=_make_leg(expiry=date(2026, 11, 24)),
            short_pe=_make_leg(option_type=AssetType.PE, expiry=date(2026, 11, 24)),
            long_ce_wing=_make_leg(side=Direction.BUY, expiry=date(2026, 10, 27)),
            long_pe_wing=_make_leg(
                side=Direction.BUY, option_type=AssetType.PE, expiry=date(2026, 10, 27)
            ),
        )

    # Leg qty_lots must match across all 4 legs
    with pytest.raises(InvalidStructureError):
        CalendarStructure(
            short_ce=_make_leg(qty_lots=1),
            short_pe=_make_leg(option_type=AssetType.PE, qty_lots=2),
            long_ce_wing=_make_leg(side=Direction.BUY, expiry=date(2026, 11, 24), qty_lots=1),
            long_pe_wing=_make_leg(
                side=Direction.BUY, option_type=AssetType.PE, expiry=date(2026, 11, 24), qty_lots=1
            ),
        )


def test_missing_greeks_raises() -> None:
    """Assert creating a leg with any missing Greek raises MissingGreeksError."""
    with pytest.raises(MissingGreeksError):
        _make_leg(delta=None)  # type: ignore[arg-type]

    with pytest.raises(MissingGreeksError):
        _make_leg(vega=None)  # type: ignore[arg-type]

    with pytest.raises(MissingGreeksError):
        _make_leg(iv=None)  # type: ignore[arg-type]


def test_money_is_decimal() -> None:
    """Assert all monetary and metric fields are Decimal instances, not float."""
    structure = _make_structure()
    metrics = compute_metrics(
        structure,
        spot=Decimal("22700"),
        far_carry=Decimal("0"),
        lot_size=65,
    )

    # Legs
    for leg in structure.legs:
        assert isinstance(leg.strike, Decimal)
        assert isinstance(leg.entry_price, Decimal)
        assert isinstance(leg.delta, Decimal)
        assert isinstance(leg.vega, Decimal)
        assert isinstance(leg.iv, Decimal)

    # Structure
    assert isinstance(structure.short_strike, Decimal)
    assert isinstance(structure.net_credit_per_unit, Decimal)
    assert isinstance(structure.net_credit_per_lot(65), Decimal)

    # Metrics
    assert isinstance(metrics, StructureMetrics)
    assert isinstance(metrics.net_delta, Decimal)
    assert isinstance(metrics.net_vega, Decimal)
    assert isinstance(metrics.risk_reward, Decimal)
    assert isinstance(metrics.breakeven_low, Decimal)
    assert isinstance(metrics.breakeven_high, Decimal)
    assert isinstance(metrics.breakeven_low_pct, Decimal)
    assert isinstance(metrics.breakeven_high_pct, Decimal)
    assert isinstance(metrics.loss_at_breakeven_low_per_lot, Decimal)
    assert isinstance(metrics.loss_at_breakeven_high_per_lot, Decimal)
    assert isinstance(metrics.net_credit_per_unit, Decimal)
    assert isinstance(metrics.net_credit_per_lot, Decimal)
    assert isinstance(metrics.max_profit_per_lot, Decimal)
    assert isinstance(metrics.max_loss_per_lot, Decimal)


def test_net_vega_per_unit_invariant_to_lots() -> None:
    """Assert net_vega and net_delta are normalized per unit and invariant to qty_lots."""
    s1 = _make_structure(qty_lots=1)
    s3 = _make_structure(qty_lots=3)

    m1 = compute_metrics(s1, spot=Decimal("22700"), far_carry=Decimal("0"), lot_size=65)
    m3 = compute_metrics(s3, spot=Decimal("22700"), far_carry=Decimal("0"), lot_size=65)

    assert m1.net_vega == m3.net_vega
    assert m1.net_delta == m3.net_delta


def test_inverted_wings_raise_invalid_structure_error() -> None:
    """Assert inverted or non-OTM wings raise InvalidStructureError."""
    # CE wing strike <= short straddle strike
    with pytest.raises(
        InvalidStructureError, match="Wing strikes must be strictly OTM relative to short straddle"
    ):
        CalendarStructure(
            short_ce=_make_leg(strike=Decimal("22700")),
            short_pe=_make_leg(option_type=AssetType.PE, strike=Decimal("22700")),
            long_ce_wing=_make_leg(
                strike=Decimal("22700"), side=Direction.BUY, expiry=date(2026, 11, 24)
            ),
            long_pe_wing=_make_leg(
                strike=Decimal("22100"),
                side=Direction.BUY,
                option_type=AssetType.PE,
                expiry=date(2026, 11, 24),
            ),
        )

    # PE wing strike >= short straddle strike
    with pytest.raises(
        InvalidStructureError, match="Wing strikes must be strictly OTM relative to short straddle"
    ):
        CalendarStructure(
            short_ce=_make_leg(strike=Decimal("22700")),
            short_pe=_make_leg(option_type=AssetType.PE, strike=Decimal("22700")),
            long_ce_wing=_make_leg(
                strike=Decimal("23200"), side=Direction.BUY, expiry=date(2026, 11, 24)
            ),
            long_pe_wing=_make_leg(
                strike=Decimal("22700"),
                side=Direction.BUY,
                option_type=AssetType.PE,
                expiry=date(2026, 11, 24),
            ),
        )

"""Unit tests for option chain utilities."""

from datetime import date
from decimal import Decimal

from src.models.options import OptionChain, OptionChainStrike, OptionLeg
from src.paper.chain_utils import (
    find_chain_leg,
    parse_expiry_from_key,
    parse_strike_from_key,
)


def test_parse_expiry_from_key() -> None:
    # Happy path: date-embedded key
    assert parse_expiry_from_key("NSE_FO|NIFTY29MAY2026CE23000") == date(2026, 5, 29)
    assert parse_expiry_from_key("NIFTY25JUN2026PE23000") == date(2026, 6, 25)

    # Edge cases / errors: invalid month or formats
    assert parse_expiry_from_key("NSE_FO|NIFTY29FOOBARCE23000") is None
    assert parse_expiry_from_key("NIFTY23000CE") is None
    assert parse_expiry_from_key("NSE_FO|NIFTY99XYZ9999CE23000") is None


def test_parse_strike_from_key() -> None:
    # Happy path: normal style
    assert parse_strike_from_key("NSE_FO|NIFTY23000CE") == Decimal("23000")
    # Date-embedded style with option type first
    assert parse_strike_from_key("NSE_FO|NIFTY29MAY2026CE23100") == Decimal("23100")

    # Error cases
    assert parse_strike_from_key("NSE_FO|47196") is None
    assert parse_strike_from_key("INVALID") is None


def test_find_chain_leg() -> None:
    # Setup chain
    ce_leg = OptionLeg(
        instrument_key="NSE_FO|NIFTY23000CE",
        option_type="CE",
        strike_price=Decimal("23000"),
        ltp=Decimal("100"),
        bid=Decimal("99"),
        ask=Decimal("101"),
        oi=100,
        volume=10,
        iv=Decimal("15"),
        delta=Decimal("0.5"),
        gamma=Decimal("0.01"),
        theta=Decimal("-1"),
        vega=Decimal("2"),
        strike=Decimal("23000"),
    )
    pe_leg = OptionLeg(
        instrument_key="NSE_FO|NIFTY23000PE",
        option_type="PE",
        strike_price=Decimal("23000"),
        ltp=Decimal("50"),
        bid=Decimal("49"),
        ask=Decimal("51"),
        oi=100,
        volume=10,
        iv=Decimal("15"),
        delta=Decimal("-0.5"),
        gamma=Decimal("0.01"),
        theta=Decimal("-1"),
        vega=Decimal("2"),
        strike=Decimal("23000"),
    )
    chain = OptionChain(
        underlying_spot=Decimal("23000"),
        expiry=date(2026, 6, 25),
        strikes={Decimal("23000"): OptionChainStrike(ce=ce_leg, pe=pe_leg)},
    )

    # Happy path
    assert find_chain_leg(chain, "NSE_FO|NIFTY23000CE", "CE") == ce_leg
    assert find_chain_leg(chain, "NSE_FO|NIFTY23000PE", "PE") == pe_leg

    # Resolution via lookup (numeric BOD keys)
    lookup_mock = type(
        "MockLookup",
        (),
        {"get_by_key": lambda self, k: {"strike_price": 23000.0} if k == "NSE_FO|71474" else None},
    )()

    assert find_chain_leg(chain, "NSE_FO|71474", "CE", lookup_mock) == ce_leg
    assert find_chain_leg(chain, "NSE_FO|71474", "PE", lookup_mock) == pe_leg

    # Absent/error cases
    assert find_chain_leg(chain, "NSE_FO|NIFTY24000CE", "CE") is None
    assert find_chain_leg(chain, "NSE_FO|71474", "CE", None) is None  # no lookup for numeric key

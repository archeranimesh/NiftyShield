"""Unit tests for apply_trade_positions() in src/portfolio/tracker.py.

All tests are pure — no DB, no I/O.

Matching is done on instrument_key, NOT display_name.  Tests deliberately
use the full display_name from ilts.py (e.g. "EBBETF0431 (Bharat Bond ETF
Apr 2031)") to confirm that display_name differences do NOT affect matching.

Coverage:
- No trades → strategy passes through unchanged.
- Known leg matched by instrument_key → qty and entry_price replaced.
- display_name mismatch does NOT prevent matching (key is instrument_key).
- Options legs absent from positions pass through unchanged.
- Zero net qty leg → dropped from updated strategy.
- Unknown leg_role (e.g. LIQUIDBEES, different instrument_key) → appended.
- Unknown leg_role with zero net qty → not appended.
- Returned object is a new Strategy instance (original unchanged).
- Strategy name/description preserved.
"""

from datetime import date
from decimal import Decimal

from src.models.portfolio import (
    AssetType,
    Direction,
    Leg,
    ProductType,
    Strategy,
)
from src.portfolio.tracker import apply_trade_positions


# ── Helpers ───────────────────────────────────────────────────────────────────


def _equity_leg(
    display_name: str = "EBBETF0431 (Bharat Bond ETF Apr 2031)",
    instrument_key: str = "NSE_EQ|INF754K01LE1",
    qty: int = 438,
    entry_price: str = "1388.12",
) -> Leg:
    """Uses the full display_name from ilts.py to catch any display_name-based matching."""
    return Leg(
        instrument_key=instrument_key,
        display_name=display_name,
        asset_type=AssetType.EQUITY,
        direction=Direction.BUY,
        quantity=qty,
        lot_size=1,
        entry_price=Decimal(entry_price),
        entry_date=date(2026, 1, 15),
        product_type=ProductType.CNC,
    )


def _option_leg(
    display_name: str = "NIFTY DEC 23000 PE",
    instrument_key: str = "NSE_FO|37810",
    qty: int = 65,
    entry_price: str = "975.00",
    direction: Direction = Direction.BUY,
) -> Leg:
    return Leg(
        instrument_key=instrument_key,
        display_name=display_name,
        asset_type=AssetType.PE,
        direction=direction,
        quantity=qty,
        lot_size=65,
        entry_price=Decimal(entry_price),
        entry_date=date(2026, 1, 15),
        expiry=date(2026, 12, 29),
        strike=23000.0,
        product_type=ProductType.NRML,
    )


def _strategy(*legs: Leg) -> Strategy:
    return Strategy(name="ILTS", description="test", legs=list(legs))


# ── No trades — passthrough ───────────────────────────────────────────────────


def test_no_positions_strategy_unchanged() -> None:
    """Empty positions dict → every leg in original strategy returned as-is."""
    s = _strategy(_equity_leg(), _option_leg())
    result = apply_trade_positions(s, {})
    assert len(result.legs) == 2
    assert result.legs[0].quantity == 438
    assert result.legs[1].quantity == 65


# ── Known leg matched by instrument_key ──────────────────────────────────────


def test_known_leg_qty_and_price_updated() -> None:
    """Leg matched on instrument_key gets new qty and entry_price."""
    s = _strategy(_equity_leg(qty=438, entry_price="1388.12"))
    # leg_role "EBBETF0431" != display_name "EBBETF0431 (Bharat Bond ETF Apr 2031)"
    # but instrument_key "NSE_EQ|INF754K01LE1" matches — that is the join key.
    positions = {"EBBETF0431": (465, Decimal("1388.01"), "NSE_EQ|INF754K01LE1")}
    result = apply_trade_positions(s, positions)
    leg = result.legs[0]
    assert leg.quantity == 465
    assert leg.entry_price == Decimal("1388.01")


def test_display_name_mismatch_does_not_prevent_match() -> None:
    """display_name 'EBBETF0431 (Bharat Bond ETF Apr 2031)' does NOT block the match."""
    full_display = "EBBETF0431 (Bharat Bond ETF Apr 2031)"
    s = _strategy(_equity_leg(display_name=full_display, qty=438))
    positions = {"EBBETF0431": (465, Decimal("1388.01"), "NSE_EQ|INF754K01LE1")}
    result = apply_trade_positions(s, positions)
    # If display_name were used as join key this would return 438; must be 465.
    assert result.legs[0].quantity == 465


def test_known_leg_instrument_key_preserved() -> None:
    """instrument_key on the matched Leg is preserved unchanged."""
    s = _strategy(_equity_leg(instrument_key="NSE_EQ|INF754K01LE1"))
    positions = {"EBBETF0431": (465, Decimal("1388.01"), "NSE_EQ|INF754K01LE1")}
    result = apply_trade_positions(s, positions)
    assert result.legs[0].instrument_key == "NSE_EQ|INF754K01LE1"


def test_option_leg_not_in_positions_passes_through() -> None:
    """Options legs whose instrument_key is absent from positions pass through unchanged."""
    s = _strategy(_equity_leg(), _option_leg())
    positions = {"EBBETF0431": (465, Decimal("1388.01"), "NSE_EQ|INF754K01LE1")}
    result = apply_trade_positions(s, positions)
    assert len(result.legs) == 2
    option = next(l for l in result.legs if l.asset_type == AssetType.PE)
    assert option.quantity == 65
    assert option.entry_price == Decimal("975.00")


# ── Zero net qty → leg dropped ────────────────────────────────────────────────


def test_zero_net_qty_leg_dropped() -> None:
    """A fully closed leg (net_qty=0) is removed from the updated strategy."""
    s = _strategy(_equity_leg(qty=438), _option_leg())
    positions = {"EBBETF0431": (0, Decimal("0"), "NSE_EQ|INF754K01LE1")}
    result = apply_trade_positions(s, positions)
    keys = [l.instrument_key for l in result.legs]
    assert "NSE_EQ|INF754K01LE1" not in keys
    assert "NSE_FO|37810" in keys


# ── Unknown leg appended ──────────────────────────────────────────────────────


def test_unknown_leg_role_appended_as_equity() -> None:
    """LIQUIDBEES — different instrument_key not in strategy — gets appended."""
    s = _strategy(_equity_leg())
    positions = {
        "EBBETF0431": (465, Decimal("1388.01"), "NSE_EQ|INF754K01LE1"),
        "LIQUIDBEES": (22, Decimal("1000.00"), "NSE_EQ|INF732E01037"),
    }
    result = apply_trade_positions(s, positions)
    names = [l.display_name for l in result.legs]
    assert "LIQUIDBEES" in names
    lb = next(l for l in result.legs if l.display_name == "LIQUIDBEES")
    assert lb.quantity == 22
    assert lb.entry_price == Decimal("1000.00")
    assert lb.instrument_key == "NSE_EQ|INF732E01037"
    assert lb.asset_type == AssetType.EQUITY
    assert lb.product_type == ProductType.CNC
    assert lb.lot_size == 1


def test_unknown_leg_zero_net_qty_not_appended() -> None:
    """Unknown leg_role with zero net qty is not added to the strategy."""
    s = _strategy(_equity_leg())
    positions = {
        "EBBETF0431": (465, Decimal("1388.01"), "NSE_EQ|INF754K01LE1"),
        "LIQUIDBEES": (0, Decimal("0"), "NSE_EQ|INF732E01037"),
    }
    result = apply_trade_positions(s, positions)
    names = [l.display_name for l in result.legs]
    assert "LIQUIDBEES" not in names


# ── Immutability ──────────────────────────────────────────────────────────────


def test_original_strategy_not_mutated() -> None:
    """apply_trade_positions returns a new Strategy; original is unchanged."""
    original_leg = _equity_leg(qty=438, entry_price="1388.12")
    s = _strategy(original_leg)
    positions = {"EBBETF0431": (465, Decimal("1388.01"), "NSE_EQ|INF754K01LE1")}
    result = apply_trade_positions(s, positions)
    assert result is not s
    assert s.legs[0].quantity == 438        # original untouched
    assert result.legs[0].quantity == 465   # new copy updated


def test_strategy_name_and_description_preserved() -> None:
    """Returned Strategy carries same name and description as original."""
    s = _strategy(_equity_leg())
    result = apply_trade_positions(s, {})
    assert result.name == s.name
    assert result.description == s.description

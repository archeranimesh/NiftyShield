"""Unit tests for src/portfolio/tracker.py — realized P&L regression coverage.

FR-7 row 1 (CRITICAL): apply_trade_positions() previously dropped realized P&L
for fully closed legs, and get_position()/get_all_positions_for_strategy()
returned average_price=Decimal("0") for short-first (sell-only) legs. These
tests cover the three required scenarios from stories.md T1:
    (a) a short-first leg (sell-only trades, no BUY)
    (b) a fully round-tripped leg (BUY then SELL closing it)
    (c) the existing BUY-first happy path, unchanged
"""

from datetime import date
from decimal import Decimal

from src.models.portfolio import (
    AssetType,
    Direction,
    Leg,
    Position,
    ProductType,
    Strategy,
)
from src.portfolio.tracker import apply_trade_positions


def _strategy(*legs: Leg) -> Strategy:
    return Strategy(name="ILTS", description="test", legs=list(legs))


def _option_leg(
    instrument_key: str = "NSE_FO|37810",
    qty: int = 65,
    entry_price: str = "975.00",
) -> Leg:
    return Leg(
        instrument_key=instrument_key,
        display_name="NIFTY DEC 23000 PE",
        asset_type=AssetType.PE,
        direction=Direction.SELL,
        quantity=qty,
        lot_size=65,
        entry_price=Decimal(entry_price),
        entry_date=date(2026, 1, 15),
        expiry=date(2026, 12, 29),
        strike=Decimal("23000"),
        product_type=ProductType.NRML,
    )


def _equity_leg(
    instrument_key: str = "NSE_EQ|INF754K01LE1",
    qty: int = 438,
    entry_price: str = "1388.12",
) -> Leg:
    return Leg(
        instrument_key=instrument_key,
        display_name="EBBETF0431",
        asset_type=AssetType.EQUITY,
        direction=Direction.BUY,
        quantity=qty,
        lot_size=1,
        entry_price=Decimal(entry_price),
        entry_date=date(2026, 1, 15),
        product_type=ProductType.CNC,
    )


# ── (a) short-first leg — sell-only, no BUY ──────────────────────────────────


def test_short_first_leg_open_gets_weighted_sell_price_as_entry() -> None:
    """A short-first leg still open (no BUY yet) carries the weighted SELL
    price as entry_price — not Decimal("0") — and contributes zero realized_pnl."""
    s = _strategy(_option_leg(qty=65, entry_price="0"))
    positions = {
        "NIFTY_DEC_23000_PE": Position(
            strategy_name="ILTS", leg_role="NIFTY_DEC_23000_PE", quantity=-65,
            average_price=Decimal("975.00"), instrument_key="NSE_FO|37810",
            realized_pnl=Decimal("0"),
        )
    }
    result = apply_trade_positions(s, positions)
    leg = result.legs[0]
    assert leg.quantity == -65
    assert leg.entry_price == Decimal("975.00")
    assert result.realized_pnl == Decimal("0")


# ── (b) fully round-tripped leg — BUY then SELL closing it ──────────────────


def test_round_tripped_leg_realized_pnl_survives_leg_drop() -> None:
    """A leg that fully round-trips (closed, quantity=0) is dropped from the
    active legs list, but its realized_pnl still lands on the Strategy."""
    s = _strategy(_equity_leg(qty=438), _option_leg())
    positions = {
        "EBBETF0431": Position(
            strategy_name="ILTS", leg_role="EBBETF0431", quantity=0,
            average_price=Decimal("0"), instrument_key="NSE_EQ|INF754K01LE1",
            realized_pnl=Decimal("52318.50"),
        )
    }
    result = apply_trade_positions(s, positions)
    keys = [leg.instrument_key for leg in result.legs]
    assert "NSE_EQ|INF754K01LE1" not in keys
    assert "NSE_FO|37810" in keys  # untouched option leg passes through
    assert result.realized_pnl == Decimal("52318.50")


# ── (c) existing BUY-first happy path — unchanged ────────────────────────────


def test_buy_first_happy_path_unchanged() -> None:
    """BUY-first leg still open behaves exactly as before this fix: qty and
    entry_price replaced from the trades ledger, realized_pnl zero."""
    s = _strategy(_equity_leg(qty=438, entry_price="1388.12"))
    positions = {
        "EBBETF0431": Position(
            strategy_name="ILTS", leg_role="EBBETF0431", quantity=465,
            average_price=Decimal("1388.01"), instrument_key="NSE_EQ|INF754K01LE1",
            realized_pnl=Decimal("0"),
        )
    }
    result = apply_trade_positions(s, positions)
    leg = result.legs[0]
    assert leg.quantity == 465
    assert leg.entry_price == Decimal("1388.01")
    assert result.realized_pnl == Decimal("0")

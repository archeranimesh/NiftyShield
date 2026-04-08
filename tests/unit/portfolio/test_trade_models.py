"""Unit tests for Trade model and TradeAction enum in src/portfolio/models.py.

All tests are purely in-memory — no DB, no I/O.

Coverage:
- TradeAction: enum values, string coercion, invalid value rejection.
- Trade: valid BUY and SELL construction.
- Trade: quantity and price validation (must be > 0).
- Trade: frozen=True enforcement (mutation raises TypeError).
- Trade: Decimal precision round-trip for price.
- Trade: optional notes field defaults to empty string.
"""

from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from src.portfolio.models import Trade, TradeAction


# ── TradeAction ──────────────────────────────────────────────────────────────


def test_trade_action_buy_value() -> None:
    assert TradeAction.BUY.value == "BUY"


def test_trade_action_sell_value() -> None:
    assert TradeAction.SELL.value == "SELL"


def test_trade_action_coerce_from_string_buy() -> None:
    assert TradeAction("BUY") == TradeAction.BUY


def test_trade_action_coerce_from_string_sell() -> None:
    assert TradeAction("SELL") == TradeAction.SELL


def test_trade_action_invalid_value_raises() -> None:
    with pytest.raises(ValueError):
        TradeAction("HOLD")


# ── Trade construction — happy path ──────────────────────────────────────────


def _make_trade(**overrides: object) -> Trade:
    """Helper — builds a valid BUY trade with sensible defaults."""
    defaults: dict = {
        "strategy_name": "ILTS",
        "leg_role": "EBBETF0431",
        "instrument_key": "NSE_EQ|INF754K01LE1",
        "trade_date": date(2026, 1, 15),
        "action": TradeAction.BUY,
        "quantity": 438,
        "price": Decimal("1388.12"),
    }
    defaults.update(overrides)
    return Trade(**defaults)


def test_valid_buy_trade_constructs() -> None:
    t = _make_trade()
    assert t.strategy_name == "ILTS"
    assert t.action == TradeAction.BUY
    assert t.quantity == 438
    assert t.price == Decimal("1388.12")


def test_valid_sell_trade_constructs() -> None:
    t = _make_trade(
        leg_role="NIFTY_JUN_PE",
        instrument_key="NSE_FO|37805",
        action=TradeAction.SELL,
        quantity=65,
        price=Decimal("840.00"),
    )
    assert t.action == TradeAction.SELL
    assert t.quantity == 65


def test_trade_notes_defaults_to_empty_string() -> None:
    t = _make_trade()
    assert t.notes == ""


def test_trade_notes_accepts_text() -> None:
    t = _make_trade(notes="addition to ILTS position")
    assert t.notes == "addition to ILTS position"


def test_trade_action_coerced_from_string_in_model() -> None:
    """TradeAction should accept a plain string in the model constructor."""
    t = _make_trade(action="BUY")  # type: ignore[arg-type]
    assert t.action == TradeAction.BUY


# ── Quantity validation ──────────────────────────────────────────────────────


def test_quantity_zero_rejected() -> None:
    with pytest.raises(ValidationError):
        _make_trade(quantity=0)


def test_quantity_negative_rejected() -> None:
    with pytest.raises(ValidationError):
        _make_trade(quantity=-10)


def test_quantity_one_is_valid() -> None:
    t = _make_trade(quantity=1)
    assert t.quantity == 1


# ── Price validation ─────────────────────────────────────────────────────────


def test_price_zero_rejected() -> None:
    with pytest.raises(ValidationError):
        _make_trade(price=Decimal("0"))


def test_price_negative_rejected() -> None:
    with pytest.raises(ValidationError):
        _make_trade(price=Decimal("-100"))


def test_price_float_input_coerced_to_decimal() -> None:
    """Float inputs must be coerced via str() to avoid binary representation errors."""
    t = _make_trade(price=1386.20)  # type: ignore[arg-type]
    assert isinstance(t.price, Decimal)
    assert t.price == Decimal("1386.2")


def test_price_string_input_accepted() -> None:
    t = _make_trade(price="1388.12")  # type: ignore[arg-type]
    assert t.price == Decimal("1388.12")


def test_price_decimal_precision_preserved() -> None:
    """Six decimal places must survive a Decimal round-trip."""
    t = _make_trade(price=Decimal("975.123456"))
    assert t.price == Decimal("975.123456")


# ── Immutability ─────────────────────────────────────────────────────────────


def test_trade_is_frozen_quantity() -> None:
    t = _make_trade()
    with pytest.raises((TypeError, ValidationError)):
        t.quantity = 999  # type: ignore[misc]


def test_trade_is_frozen_price() -> None:
    t = _make_trade()
    with pytest.raises((TypeError, ValidationError)):
        t.price = Decimal("9999")  # type: ignore[misc]


def test_trade_is_frozen_action() -> None:
    t = _make_trade()
    with pytest.raises((TypeError, ValidationError)):
        t.action = TradeAction.SELL  # type: ignore[misc]

import pytest
from decimal import Decimal
from src.notifications.formatting import (
    format_money,
    format_greek,
    format_strike,
    format_pct,
)

def test_format_money_happy_path():
    assert format_money(Decimal("86.68")) == "₹86.68"

def test_format_money_edge_zero():
    assert format_money(Decimal("0")) == "₹0.00"

def test_format_money_raises_type_error_on_float():
    with pytest.raises(TypeError, match="format_money requires Decimal, not float"):
        format_money(86.68)  # type: ignore

def test_format_greek_happy_path_positive():
    assert format_greek(0.28) == "+0.28"

def test_format_greek_happy_path_negative():
    assert format_greek(-0.03) == "-0.03"

def test_format_greek_edge_none():
    assert format_greek(None) == "-"

def test_format_strike_happy_path():
    assert format_strike(23000.0) == "23000"

def test_format_strike_edge_zero():
    assert format_strike(0) == "0"

def test_format_strike_raises_value_error_on_fractional():
    with pytest.raises(ValueError, match="format_strike requires an integer or whole-number float"):
        format_strike(23000.5)

def test_format_pct_happy_path_whole():
    assert format_pct(4.0) == "4%"

def test_format_pct_edge_zero():
    assert format_pct(0.0) == "0%"

# tests/unit/paper/test_display.py
from decimal import Decimal
from src.paper._display import fmt_decimal, delta_arrow, hedge_verdict

def test_fmt_decimal():
    assert fmt_decimal(Decimal("1234.56")) == "+1,235"
    assert fmt_decimal(Decimal("-1234.56")) == "-1,235"
    assert fmt_decimal(Decimal("0")) == "0"
    assert fmt_decimal(Decimal("1234.56"), precision=2) == "+1,234.56"

def test_delta_arrow():
    assert "▲" in delta_arrow(Decimal("10"))
    assert "▼" in delta_arrow(Decimal("-10"))
    assert "±0" in delta_arrow(Decimal("0"))
    assert "no prior" in delta_arrow(None)

def test_hedge_verdict_protected():
    # Base loss -500, Overlay gain +400 -> 80% absorbed
    v = hedge_verdict(Decimal("-500"), Decimal("400"))
    assert "Protected" in v
    assert "80%" in v

def test_hedge_verdict_no_protection():
    v = hedge_verdict(Decimal("-500"), Decimal("0"))
    assert "No protection" in v

def test_hedge_verdict_drag():
    # Base gain +500, Overlay loss -100 -> Drag
    v = hedge_verdict(Decimal("500"), Decimal("-100"))
    assert "Cost" in v

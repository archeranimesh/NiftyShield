"""Tests for paper trading metrics."""

from decimal import Decimal
from src.paper.metrics import (
    compute_nee,
    compute_return_on_nee,
    compute_cycle_max_drawdown,
    compute_annualised_overlay_cost,
)

def test_compute_nee():
    assert compute_nee(Decimal("20000"), 50) == Decimal("1000000")

def test_compute_return_on_nee():
    assert compute_return_on_nee(Decimal("50000"), Decimal("1000000")) == Decimal("5.0")
    assert compute_return_on_nee(Decimal("50000"), Decimal("0")) == Decimal("0")

def test_compute_cycle_max_drawdown():
    # Peak at 100, drops to 80 (DD = -20), then up to 120, drops to 90 (DD = -30)
    history = [Decimal("100"), Decimal("80"), Decimal("120"), Decimal("90")]
    nee = Decimal("1000")
    abs_dd, pct_dd = compute_cycle_max_drawdown(history, nee)
    assert abs_dd == Decimal("-30")
    assert pct_dd == Decimal("-3.0")
    
    # Only going up
    history_up = [Decimal("100"), Decimal("120"), Decimal("150")]
    abs_up, pct_up = compute_cycle_max_drawdown(history_up, nee)
    assert abs_up == Decimal("0")
    assert pct_up == Decimal("0")
    
    # Empty history
    abs_emp, pct_emp = compute_cycle_max_drawdown([], nee)
    assert abs_emp == Decimal("0")
    assert pct_emp == Decimal("0")

def test_compute_annualised_overlay_cost():
    result = compute_annualised_overlay_cost(Decimal("1000"), 30)
    expected = (Decimal("1000") / Decimal("30")) * Decimal("365")
    assert result == expected
    assert compute_annualised_overlay_cost(Decimal("1000"), 0) == Decimal("0")

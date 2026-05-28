# tests/unit/paper/test_cc_constants.py
"""Unit tests for CC overlay constants and compute_max_lots."""

from decimal import Decimal

import pytest

from src.paper.constants import STRATEGY_CC_OVERLAY, compute_max_lots


class TestStrategyConstant:
    def test_strategy_name_value(self) -> None:
        assert STRATEGY_CC_OVERLAY == "paper_covered_call_v1"


class TestComputeMaxLots:
    def test_happy_path_returns_one(self) -> None:
        # 24500/280 × 65 ≈ 5691 units/lot; 5725/5691 ≈ 1.006 → floor = 1
        result = compute_max_lots(
            niftybees_units=5725,
            nifty_spot=Decimal("24500"),
            niftybees_ltp=Decimal("280"),
            lot_size=65,
        )
        assert result == 1

    def test_double_units_returns_two(self) -> None:
        result = compute_max_lots(
            niftybees_units=11450,
            nifty_spot=Decimal("24500"),
            niftybees_ltp=Decimal("280"),
            lot_size=65,
        )
        assert result == 2

    def test_undersized_holding_returns_zero(self) -> None:
        result = compute_max_lots(
            niftybees_units=1000,
            nifty_spot=Decimal("24500"),
            niftybees_ltp=Decimal("280"),
            lot_size=65,
        )
        assert result == 0

    def test_zero_nifty_spot_returns_zero(self) -> None:
        result = compute_max_lots(
            niftybees_units=5725,
            nifty_spot=Decimal("0"),
            niftybees_ltp=Decimal("280"),
            lot_size=65,
        )
        assert result == 0

    def test_zero_niftybees_ltp_returns_zero(self) -> None:
        result = compute_max_lots(
            niftybees_units=5725,
            nifty_spot=Decimal("24500"),
            niftybees_ltp=Decimal("0"),
            lot_size=65,
        )
        assert result == 0

    def test_zero_lot_size_returns_zero(self) -> None:
        result = compute_max_lots(
            niftybees_units=5725,
            nifty_spot=Decimal("24500"),
            niftybees_ltp=Decimal("280"),
            lot_size=0,
        )
        assert result == 0

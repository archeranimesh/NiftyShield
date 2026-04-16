"""Unit tests for src/utils/number_formatting.fmt_inr.

Coverage:
  - Happy path: integers, Decimal, float, zero
  - Indian grouping thresholds: <1000, 1k–99k (same as international), 1L+, 1Cr+
  - sign=True for positive and negative
  - decimals > 0
  - width padding
  - Error path: invalid input
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from src.utils.number_formatting import fmt_inr, _group_indian


# ── _group_indian (pure grouping helper) ────────────────────────────────────


class TestGroupIndian:
    def test_one_digit(self) -> None:
        assert _group_indian("5") == "5"

    def test_three_digits_no_comma(self) -> None:
        assert _group_indian("999") == "999"

    def test_four_digits_one_comma(self) -> None:
        # 1,000
        assert _group_indian("1000") == "1,000"

    def test_five_digits(self) -> None:
        # 10,000 — same in both systems
        assert _group_indian("10000") == "10,000"

    def test_six_digits_one_lakh(self) -> None:
        # 1,00,000 — diverges from international "100,000"
        assert _group_indian("100000") == "1,00,000"

    def test_seven_digits(self) -> None:
        # 13,91,279
        assert _group_indian("1391279") == "13,91,279"

    def test_eight_digits(self) -> None:
        # 1,39,12,790
        assert _group_indian("13912790") == "1,39,12,790"

    def test_seven_digits_one_crore(self) -> None:
        # 1,00,00,000 — 1 crore = 10_000_000 (7 digits)
        assert _group_indian("10000000") == "1,00,00,000"

    def test_nine_digits_ten_crore(self) -> None:
        # 10,00,00,000 — 10 crore = 100_000_000 (9 digits)
        assert _group_indian("100000000") == "10,00,00,000"

    def test_leading_zeros_preserved(self) -> None:
        # Fractional int part like "001" should pass through
        assert _group_indian("001") == "001"


# ── fmt_inr happy paths ──────────────────────────────────────────────────────


class TestFmtInrBasic:
    def test_zero_int(self) -> None:
        assert fmt_inr(0) == "0"

    def test_small_positive_int(self) -> None:
        assert fmt_inr(500) == "500"

    def test_four_digit_same_as_international(self) -> None:
        assert fmt_inr(3450) == "3,450"

    def test_five_digit_same_as_international(self) -> None:
        assert fmt_inr(80000) == "80,000"

    def test_six_digit_lakh(self) -> None:
        # Diverges from international "242,531"
        assert fmt_inr(242531) == "2,42,531"

    def test_six_digit_round_lakh(self) -> None:
        assert fmt_inr(100000) == "1,00,000"

    def test_seven_digit_crore(self) -> None:
        assert fmt_inr(10000000) == "1,00,00,000"

    def test_decimal_input(self) -> None:
        assert fmt_inr(Decimal("1391279")) == "13,91,279"

    def test_float_input(self) -> None:
        assert fmt_inr(1391279.0) == "13,91,279"

    def test_negative_no_sign_flag(self) -> None:
        assert fmt_inr(Decimal("-242531")) == "-2,42,531"

    def test_zero_decimal(self) -> None:
        assert fmt_inr(Decimal("0")) == "0"


# ── sign=True ────────────────────────────────────────────────────────────────


class TestFmtInrSign:
    def test_positive_gets_plus(self) -> None:
        assert fmt_inr(3300, sign=True) == "+3,300"

    def test_negative_gets_minus_not_double(self) -> None:
        # sign=True must not prepend '+' to negative values
        assert fmt_inr(Decimal("-1840"), sign=True) == "-1,840"

    def test_zero_with_sign_gets_plus(self) -> None:
        assert fmt_inr(0, sign=True) == "+0"

    def test_large_positive_with_sign(self) -> None:
        assert fmt_inr(Decimal("242531"), sign=True) == "+2,42,531"

    def test_large_negative_with_sign(self) -> None:
        assert fmt_inr(Decimal("-80000"), sign=True) == "-80,000"


# ── decimals > 0 ─────────────────────────────────────────────────────────────


class TestFmtInrDecimals:
    def test_two_decimal_places(self) -> None:
        assert fmt_inr(Decimal("1391279.50"), decimals=2) == "13,91,279.50"

    def test_two_decimal_places_trailing_zero(self) -> None:
        assert fmt_inr(Decimal("100000.00"), decimals=2) == "1,00,000.00"

    def test_zero_with_decimals(self) -> None:
        assert fmt_inr(Decimal("0"), decimals=2) == "0.00"

    def test_negative_with_decimals(self) -> None:
        assert fmt_inr(Decimal("-1391.75"), decimals=2) == "-1,391.75"

    def test_small_value_with_decimals(self) -> None:
        assert fmt_inr(Decimal("22500.00"), decimals=2) == "22,500.00"


# ── width padding ────────────────────────────────────────────────────────────


class TestFmtInrWidth:
    def test_padded_wider_than_value(self) -> None:
        result = fmt_inr(3300, sign=True, width=15)
        assert result == "         +3,300"
        assert len(result) == 15

    def test_no_truncation_when_value_exceeds_width(self) -> None:
        # width is a minimum, not a maximum (100_000_000 = 10 crore)
        result = fmt_inr(Decimal("100000000"), width=5)
        assert result == "10,00,00,000"
        assert len(result) > 5

    def test_exact_width_no_padding(self) -> None:
        result = fmt_inr(Decimal("3450"), width=5)
        assert result == "3,450"

    def test_width_with_sign(self) -> None:
        result = fmt_inr(Decimal("-80000"), sign=True, width=12)
        assert result == "     -80,000"
        assert len(result) == 12


# ── error handling ───────────────────────────────────────────────────────────


class TestFmtInrErrors:
    def test_invalid_string_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="fmt_inr"):
            fmt_inr("not_a_number")  # type: ignore[arg-type]

    def test_none_raises_value_error(self) -> None:
        with pytest.raises((ValueError, TypeError)):
            fmt_inr(None)  # type: ignore[arg-type]

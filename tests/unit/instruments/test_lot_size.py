"""Unit tests for DateAwareLotSizeResolver."""

from datetime import date
import pytest

from src.instruments.lot_size import DateAwareLotSizeResolver


def test_resolve_nifty_happy_path() -> None:
    """Test Nifty lot sizes across different historical date ranges."""
    resolver = DateAwareLotSizeResolver

    # January 1, 2026 onwards: 65
    assert resolver.resolve("NIFTY", date(2026, 1, 1)) == 65
    assert resolver.resolve("NIFTY DEC 23000 PE", date(2026, 4, 1)) == 65

    # November 20, 2024 to December 31, 2025: 75
    assert resolver.resolve("NIFTY", date(2024, 11, 20)) == 75
    assert resolver.resolve("NIFTY", date(2025, 12, 31)) == 75

    # April 26, 2024 to November 19, 2024: 25
    assert resolver.resolve("NIFTY", date(2024, 4, 26)) == 25
    assert resolver.resolve("NIFTY", date(2024, 11, 19)) == 25

    # October 1, 2021 to April 25, 2024: 50
    assert resolver.resolve("NIFTY", date(2021, 10, 1)) == 50
    assert resolver.resolve("NIFTY", date(2024, 4, 25)) == 50

    # October 2015 to September 30, 2021: 75
    assert resolver.resolve("NIFTY", date(2015, 10, 1)) == 75
    assert resolver.resolve("NIFTY", date(2021, 9, 30)) == 75


def test_resolve_banknifty_happy_path() -> None:
    """Test Bank Nifty lot sizes across different historical date ranges."""
    resolver = DateAwareLotSizeResolver

    # January 1, 2026 onwards: 30
    assert resolver.resolve("BANKNIFTY", date(2026, 1, 1)) == 30
    assert resolver.resolve("NIFTY BANK", date(2026, 4, 1)) == 30

    # July 1, 2023 to December 31, 2025: 15
    assert resolver.resolve("BANKNIFTY", date(2023, 7, 1)) == 15
    assert resolver.resolve("BANKNIFTY", date(2025, 12, 31)) == 15

    # Before July 1, 2023: 25
    assert resolver.resolve("BANKNIFTY", date(2023, 6, 30)) == 25


def test_resolve_edge_cases() -> None:
    """Test edge cases: ETFs, other indices, case insensitivity, etc."""
    resolver = DateAwareLotSizeResolver

    # NiftyBees ETF (should be 1)
    assert resolver.resolve("NIFTYBEES", date(2026, 4, 1)) == 1
    assert resolver.resolve("NSE_EQ|INF204KB14I2", date(2026, 4, 1)) == 1

    # Unknown indices or stock options should default to 1 (or other fallbacks)
    assert resolver.resolve("RELIANCE", date(2026, 4, 1)) == 1

    # Case insensitivity
    assert resolver.resolve("nifty", date(2026, 4, 1)) == 65
    assert resolver.resolve("banknifty", date(2026, 4, 1)) == 30

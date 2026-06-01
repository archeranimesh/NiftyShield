"""Tests for NuvamaStore.get_monthly_realized_pnl.

Keeps separate from test_store.py to isolate the Phase E addition.
Uses the same in-memory-style pattern: tmp_path SQLite.
"""

from datetime import date
from decimal import Decimal

import pytest

from src.nuvama.store import NuvamaStore


@pytest.fixture
def store(tmp_path):
    return NuvamaStore(str(tmp_path / "test.sqlite"))


def _snap(
    store: NuvamaStore,
    snapshot_date: date,
    symbol: str,
    realized: str,
) -> None:
    """Insert a minimal options snapshot row with only the fields under test."""
    store.record_options_snapshot(
        snapshot_date,
        symbol,
        f"Instrument {symbol}",
        0,  # net_qty
        Decimal("0"),  # avg_price
        Decimal("0"),  # ltp
        Decimal("0"),  # unrealized_pnl
        Decimal(realized),
    )


class TestGetMonthlyRealizedPnl:
    def test_happy_path_sums_all_rows_in_month(self, store) -> None:
        """Three rows across two symbols in same month → correct total."""
        _snap(store, date(2026, 5, 1), "A", "1000")
        _snap(store, date(2026, 5, 2), "A", "500")
        _snap(store, date(2026, 5, 2), "B", "300")

        result = store.get_monthly_realized_pnl(2026, 5)
        assert result == Decimal("1800")

    def test_before_date_excludes_on_and_after(self, store) -> None:
        """Rows on or after before_date are excluded — matches cumulative boundary."""
        _snap(store, date(2026, 5, 1), "A", "1000")
        _snap(store, date(2026, 5, 5), "A", "500")  # excluded: on before_date
        _snap(store, date(2026, 5, 6), "A", "200")  # excluded: after before_date

        result = store.get_monthly_realized_pnl(2026, 5, before_date=date(2026, 5, 5))
        assert result == Decimal("1000")

    def test_excludes_rows_from_other_months(self, store) -> None:
        """Prior and next month rows are not counted for the queried month."""
        _snap(store, date(2026, 4, 30), "A", "9999")  # April — excluded
        _snap(store, date(2026, 5, 15), "A", "500")  # May — included
        _snap(store, date(2026, 6, 1), "A", "9999")  # June — excluded

        result = store.get_monthly_realized_pnl(2026, 5)
        assert result == Decimal("500")

    def test_returns_zero_when_no_rows(self, store) -> None:
        """Empty table → Decimal('0'), not None or 0."""
        result = store.get_monthly_realized_pnl(2026, 5)
        assert result == Decimal("0")
        assert isinstance(result, Decimal)

    def test_before_date_none_includes_all_rows_in_month(self, store) -> None:
        """No before_date → all rows in month included (including 'today').

        Uses distinct symbols so the UPSERT key (snapshot_date, symbol) never
        collides even when today == the 1st of the month.
        """
        today = date.today()
        _snap(store, date(today.year, today.month, 1), "A", "400")
        _snap(store, today, "B", "100")  # different symbol → always a separate row

        result = store.get_monthly_realized_pnl(today.year, today.month)
        assert result == Decimal("500")

    def test_negative_realized_pnl_summed_correctly(self, store) -> None:
        """Losing days reduce the monthly total — Decimal sign is preserved."""
        _snap(store, date(2026, 5, 3), "A", "5000")
        _snap(store, date(2026, 5, 4), "A", "-3000")
        _snap(store, date(2026, 5, 5), "B", "-1500")

        result = store.get_monthly_realized_pnl(2026, 5)
        assert result == Decimal("500")

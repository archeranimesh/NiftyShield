"""Tests for src/dhan/store.py — DhanStore SQLite persistence."""

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from src.dhan.models import DhanHolding
from src.dhan.store import DhanStore


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "test.sqlite"


@pytest.fixture
def store(db_path: Path) -> DhanStore:
    return DhanStore(db_path)


def _make_holdings() -> list[DhanHolding]:
    return [
        DhanHolding(
            trading_symbol="NIFTYIETF", isin="INF109K012R6",
            security_id="13611", exchange="NSE_EQ",
            total_qty=500, collateral_qty=500,
            avg_cost_price=Decimal("268.50"), classification="EQUITY",
            ltp=Decimal("275.40"),
        ),
        DhanHolding(
            trading_symbol="LIQUIDCASE", isin="INF0R8F01034",
            security_id="25780", exchange="NSE_EQ",
            total_qty=200, collateral_qty=200,
            avg_cost_price=Decimal("1003.25"), classification="BOND",
            ltp=Decimal("1005.50"),
        ),
    ]


# ── record_snapshot ──────────────────────────────────────────────


class TestRecordSnapshot:

    def test_records_holdings(self, store: DhanStore):
        count = store.record_snapshot(_make_holdings(), date(2026, 4, 14))
        assert count == 2

    def test_empty_list_returns_zero(self, store: DhanStore):
        assert store.record_snapshot([], date(2026, 4, 14)) == 0

    def test_upsert_idempotent(self, store: DhanStore):
        d = date(2026, 4, 14)
        store.record_snapshot(_make_holdings(), d)
        store.record_snapshot(_make_holdings(), d)  # same date, no error
        result = store.get_snapshot_for_date(d)
        assert len(result) == 2

    def test_upsert_updates_ltp(self, store: DhanStore):
        d = date(2026, 4, 14)
        store.record_snapshot(_make_holdings(), d)
        updated = [DhanHolding(
            trading_symbol="NIFTYIETF", isin="INF109K012R6",
            security_id="13611", exchange="NSE_EQ",
            total_qty=500, collateral_qty=500,
            avg_cost_price=Decimal("268.50"), classification="EQUITY",
            ltp=Decimal("280.00"),
        )]
        store.record_snapshot(updated, d)
        result = store.get_snapshot_for_date(d)
        nifty = next(h for h in result if h.trading_symbol == "NIFTYIETF")
        assert nifty.ltp == Decimal("280.00")


# ── get_snapshot_for_date ────────────────────────────────────────


class TestGetSnapshotForDate:

    def test_returns_holdings_for_date(self, store: DhanStore):
        d = date(2026, 4, 14)
        store.record_snapshot(_make_holdings(), d)
        result = store.get_snapshot_for_date(d)
        assert len(result) == 2
        symbols = {h.trading_symbol for h in result}
        assert symbols == {"NIFTYIETF", "LIQUIDCASE"}

    def test_returns_empty_for_missing_date(self, store: DhanStore):
        store.record_snapshot(_make_holdings(), date(2026, 4, 14))
        result = store.get_snapshot_for_date(date(2026, 4, 15))
        assert result == []

    def test_decimal_precision_preserved(self, store: DhanStore):
        d = date(2026, 4, 14)
        store.record_snapshot(_make_holdings(), d)
        result = store.get_snapshot_for_date(d)
        nifty = next(h for h in result if h.trading_symbol == "NIFTYIETF")
        assert isinstance(nifty.avg_cost_price, Decimal)
        assert nifty.avg_cost_price == Decimal("268.50") or nifty.avg_cost_price == Decimal("268.5")
        assert isinstance(nifty.ltp, Decimal)

    def test_null_ltp_stored(self, store: DhanStore):
        h = DhanHolding(
            trading_symbol="TEST", isin="INF000001",
            security_id="99", exchange="NSE_EQ",
            total_qty=10, collateral_qty=0,
            avg_cost_price=Decimal("100"), classification="EQUITY",
            ltp=None,
        )
        store.record_snapshot([h], date(2026, 4, 14))
        result = store.get_snapshot_for_date(date(2026, 4, 14))
        assert len(result) == 1
        assert result[0].ltp is None


# ── get_prev_snapshot ────────────────────────────────────────────


class TestGetPrevSnapshot:

    def test_returns_previous_day(self, store: DhanStore):
        store.record_snapshot(_make_holdings(), date(2026, 4, 11))
        store.record_snapshot(_make_holdings(), date(2026, 4, 14))
        prev = store.get_prev_snapshot(date(2026, 4, 14))
        assert len(prev) == 2
        assert "INF109K012R6" in prev
        assert "INF0R8F01034" in prev

    def test_returns_empty_on_first_day(self, store: DhanStore):
        store.record_snapshot(_make_holdings(), date(2026, 4, 14))
        prev = store.get_prev_snapshot(date(2026, 4, 14))
        assert prev == {}

    def test_skips_weekends(self, store: DhanStore):
        store.record_snapshot(_make_holdings(), date(2026, 4, 10))  # Friday
        # No Saturday/Sunday data
        prev = store.get_prev_snapshot(date(2026, 4, 14))  # Monday
        assert len(prev) == 2  # Returns Friday's data

    def test_keyed_by_isin(self, store: DhanStore):
        store.record_snapshot(_make_holdings(), date(2026, 4, 11))
        store.record_snapshot(_make_holdings(), date(2026, 4, 14))
        prev = store.get_prev_snapshot(date(2026, 4, 14))
        nifty = prev["INF109K012R6"]
        assert nifty.trading_symbol == "NIFTYIETF"

    def test_empty_store(self, store: DhanStore):
        prev = store.get_prev_snapshot(date(2026, 4, 14))
        assert prev == {}


# ── Schema coexistence ───────────────────────────────────────────


class TestSchemaCoexistence:

    def test_shares_db_with_portfolio(self, db_path: Path):
        """DhanStore's table coexists with other tables in the same DB."""
        from src.portfolio.store import PortfolioStore

        # Both stores can use the same DB file
        portfolio_store = PortfolioStore(db_path)
        dhan_store = DhanStore(db_path)

        # Both can write without conflict
        dhan_store.record_snapshot(_make_holdings(), date(2026, 4, 14))
        result = dhan_store.get_snapshot_for_date(date(2026, 4, 14))
        assert len(result) == 2

        # Portfolio store still works
        strategies = portfolio_store.get_all_strategies()
        assert strategies == []  # empty but no error

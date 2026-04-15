"""Tests for src/nuvama/store.py — NuvamaStore."""

from datetime import date
from decimal import Decimal

import pytest

from src.nuvama.store import NuvamaStore


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def store(tmp_path):
    return NuvamaStore(str(tmp_path / "test.sqlite"))


def _pos(isin: str, avg_price: str = "1000.00", qty: int = 100, label: str = "") -> dict:
    return {"isin": isin, "avg_price": Decimal(avg_price), "qty": qty, "label": label}


def _holding_stub(isin: str, qty: int = 100, ltp: str = "1010.00"):
    """Minimal stub that duck-types NuvamaBondHolding for record_all_snapshots."""
    from types import SimpleNamespace
    return SimpleNamespace(
        isin=isin,
        qty=qty,
        ltp=Decimal(ltp),
        current_value=Decimal(ltp) * qty,
    )


# ---------------------------------------------------------------------------
# Schema coexistence
# ---------------------------------------------------------------------------


class TestSchemaCoexistence:
    def test_shares_db_with_portfolio(self, tmp_path):
        """Both nuvama tables and portfolio tables coexist in the same DB."""
        pytest.importorskip("pydantic", reason="pydantic required for PortfolioStore")
        from src.portfolio.store import PortfolioStore

        db = str(tmp_path / "shared.sqlite")
        NuvamaStore(db)
        PortfolioStore(db)  # must not raise

    def test_creates_positions_table(self, tmp_path):
        import sqlite3
        db = str(tmp_path / "t.sqlite")
        NuvamaStore(db)
        with sqlite3.connect(db) as conn:
            tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        assert "nuvama_positions" in tables

    def test_creates_snapshots_table(self, tmp_path):
        import sqlite3
        db = str(tmp_path / "t.sqlite")
        NuvamaStore(db)
        with sqlite3.connect(db) as conn:
            tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        assert "nuvama_holdings_snapshots" in tables

    def test_idempotent_init(self, tmp_path):
        """Calling NuvamaStore twice on same DB must not raise."""
        db = str(tmp_path / "t.sqlite")
        NuvamaStore(db)
        NuvamaStore(db)  # no error


# ---------------------------------------------------------------------------
# seed_positions / get_positions
# ---------------------------------------------------------------------------


class TestSeedPositions:
    def test_seed_inserts_rows(self, store):
        inserted = store.seed_positions([_pos("A"), _pos("B")])
        assert inserted == 2

    def test_get_positions_returns_decimal(self, store):
        store.seed_positions([_pos("A", avg_price="1001.06")])
        pos = store.get_positions()
        assert pos["A"] == Decimal("1001.06")

    def test_seed_idempotent_by_default(self, store):
        store.seed_positions([_pos("A")])
        inserted2 = store.seed_positions([_pos("A")])
        assert inserted2 == 0  # INSERT OR IGNORE

    def test_seed_overwrite_replaces(self, store):
        store.seed_positions([_pos("A", avg_price="1000.00")])
        store.seed_positions([_pos("A", avg_price="1005.00")], overwrite=True)
        pos = store.get_positions()
        assert pos["A"] == Decimal("1005.00")

    def test_get_positions_empty_when_no_seed(self, store):
        assert store.get_positions() == {}

    def test_get_positions_multiple(self, store):
        store.seed_positions([_pos("A"), _pos("B", avg_price="109.00")])
        pos = store.get_positions()
        assert len(pos) == 2
        assert pos["B"] == Decimal("109.00")

    def test_label_stored_and_retrieved(self, store):
        store.seed_positions([_pos("A", label="EFSL NCD 2034")])
        rec = store.get_position("A")
        assert rec is not None
        assert rec["label"] == "EFSL NCD 2034"


# ---------------------------------------------------------------------------
# get_position (single lookup)
# ---------------------------------------------------------------------------


class TestGetPosition:
    def test_returns_none_for_unknown_isin(self, store):
        assert store.get_position("UNKNOWN") is None

    def test_returns_dict_for_known_isin(self, store):
        store.seed_positions([_pos("A", avg_price="1000.00", qty=700)])
        rec = store.get_position("A")
        assert rec is not None
        assert rec["isin"] == "A"
        assert rec["avg_price"] == Decimal("1000.00")
        assert rec["qty"] == 700


# ---------------------------------------------------------------------------
# record_snapshot / get_snapshot_for_date
# ---------------------------------------------------------------------------


class TestRecordSnapshot:
    def test_records_single_holding(self, store):
        store.record_snapshot("A", date(2026, 4, 15), 700, Decimal("1014"), Decimal("709800"))
        result = store.get_snapshot_for_date(date(2026, 4, 15))
        assert result["A"] == Decimal("709800")

    def test_upsert_same_day(self, store):
        store.record_snapshot("A", date(2026, 4, 15), 700, Decimal("1010"), Decimal("707000"))
        store.record_snapshot("A", date(2026, 4, 15), 700, Decimal("1014"), Decimal("709800"))
        result = store.get_snapshot_for_date(date(2026, 4, 15))
        assert result["A"] == Decimal("709800")  # last write wins

    def test_multiple_instruments_same_day(self, store):
        store.record_snapshot("A", date(2026, 4, 15), 700, Decimal("1014"), Decimal("709800"))
        store.record_snapshot("B", date(2026, 4, 15), 2000, Decimal("144.40"), Decimal("288800"))
        result = store.get_snapshot_for_date(date(2026, 4, 15))
        assert len(result) == 2

    def test_different_dates_isolated(self, store):
        store.record_snapshot("A", date(2026, 4, 14), 700, Decimal("1010"), Decimal("707000"))
        store.record_snapshot("A", date(2026, 4, 15), 700, Decimal("1014"), Decimal("709800"))
        assert store.get_snapshot_for_date(date(2026, 4, 14))["A"] == Decimal("707000")
        assert store.get_snapshot_for_date(date(2026, 4, 15))["A"] == Decimal("709800")

    def test_empty_for_unknown_date(self, store):
        assert store.get_snapshot_for_date(date(2026, 4, 15)) == {}


# ---------------------------------------------------------------------------
# record_all_snapshots
# ---------------------------------------------------------------------------


class TestRecordAllSnapshots:
    def test_records_list_of_holdings(self, store):
        holdings = [_holding_stub("A", 700, "1014"), _holding_stub("B", 2000, "144.40")]
        store.record_all_snapshots(holdings, date(2026, 4, 15))
        result = store.get_snapshot_for_date(date(2026, 4, 15))
        assert len(result) == 2

    def test_empty_list_no_crash(self, store):
        store.record_all_snapshots([], date(2026, 4, 15))
        assert store.get_snapshot_for_date(date(2026, 4, 15)) == {}


# ---------------------------------------------------------------------------
# get_prev_total_value
# ---------------------------------------------------------------------------


class TestGetPrevTotalValue:
    def test_returns_none_when_no_prior_snapshot(self, store):
        store.record_snapshot("A", date(2026, 4, 15), 700, Decimal("1014"), Decimal("709800"))
        assert store.get_prev_total_value(date(2026, 4, 15)) is None

    def test_returns_sum_of_prior_day(self, store):
        store.record_snapshot("A", date(2026, 4, 14), 700, Decimal("1010"), Decimal("707000"))
        store.record_snapshot("B", date(2026, 4, 14), 2000, Decimal("140"), Decimal("280000"))
        result = store.get_prev_total_value(date(2026, 4, 15))
        assert result == Decimal("987000")

    def test_uses_most_recent_prior_date(self, store):
        store.record_snapshot("A", date(2026, 4, 13), 700, Decimal("1005"), Decimal("703500"))
        store.record_snapshot("A", date(2026, 4, 14), 700, Decimal("1010"), Decimal("707000"))
        result = store.get_prev_total_value(date(2026, 4, 15))
        assert result == Decimal("707000")  # uses 2026-04-14, not 2026-04-13

    def test_returns_none_when_empty(self, store):
        assert store.get_prev_total_value(date(2026, 4, 15)) is None

    def test_decimal_precision_preserved(self, store):
        store.record_snapshot("A", date(2026, 4, 14), 2000, Decimal("144.40"), Decimal("288800.00"))
        result = store.get_prev_total_value(date(2026, 4, 15))
        assert result == Decimal("288800.00")

"""Tests for src/nuvama/store.py — NuvamaStore."""

from datetime import date, timedelta
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


def _holding_stub(isin: str, qty: int = 100, ltp: str = "1010.00", chg_pct: str = "0"):
    """Minimal stub that duck-types NuvamaBondHolding for record_all_snapshots."""
    from types import SimpleNamespace
    return SimpleNamespace(
        isin=isin,
        qty=qty,
        ltp=Decimal(ltp),
        current_value=Decimal(ltp) * qty,
        chg_pct=Decimal(chg_pct),
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
        assert result["A"]["current_value"] == Decimal("709800")

    def test_upsert_same_day(self, store):
        store.record_snapshot("A", date(2026, 4, 15), 700, Decimal("1010"), Decimal("707000"))
        store.record_snapshot("A", date(2026, 4, 15), 700, Decimal("1014"), Decimal("709800"))
        result = store.get_snapshot_for_date(date(2026, 4, 15))
        assert result["A"]["current_value"] == Decimal("709800")  # last write wins

    def test_multiple_instruments_same_day(self, store):
        store.record_snapshot("A", date(2026, 4, 15), 700, Decimal("1014"), Decimal("709800"))
        store.record_snapshot("B", date(2026, 4, 15), 2000, Decimal("144.40"), Decimal("288800"))
        result = store.get_snapshot_for_date(date(2026, 4, 15))
        assert len(result) == 2

    def test_different_dates_isolated(self, store):
        store.record_snapshot("A", date(2026, 4, 14), 700, Decimal("1010"), Decimal("707000"))
        store.record_snapshot("A", date(2026, 4, 15), 700, Decimal("1014"), Decimal("709800"))
        assert store.get_snapshot_for_date(date(2026, 4, 14))["A"]["current_value"] == Decimal("707000")
        assert store.get_snapshot_for_date(date(2026, 4, 15))["A"]["current_value"] == Decimal("709800")

    def test_empty_for_unknown_date(self, store):
        assert store.get_snapshot_for_date(date(2026, 4, 15)) == {}

    def test_chg_pct_stored_and_returned(self, store):
        """chg_pct written via record_snapshot is returned by get_snapshot_for_date."""
        store.record_snapshot(
            "A", date(2026, 4, 15), 700, Decimal("1014"), Decimal("709800"),
            chg_pct=Decimal("-1.28"),
        )
        result = store.get_snapshot_for_date(date(2026, 4, 15))
        assert result["A"]["chg_pct"] == Decimal("-1.28")

    def test_chg_pct_defaults_to_zero_when_omitted(self, store):
        """Callers that omit chg_pct (e.g. seed scripts) get Decimal('0') back."""
        store.record_snapshot("A", date(2026, 4, 15), 700, Decimal("1014"), Decimal("709800"))
        result = store.get_snapshot_for_date(date(2026, 4, 15))
        assert result["A"]["chg_pct"] == Decimal("0")

    def test_upsert_updates_chg_pct(self, store):
        """A second record_snapshot on the same day overwrites chg_pct."""
        store.record_snapshot(
            "A", date(2026, 4, 15), 700, Decimal("1014"), Decimal("709800"),
            chg_pct=Decimal("-0.50"),
        )
        store.record_snapshot(
            "A", date(2026, 4, 15), 700, Decimal("1016"), Decimal("711200"),
            chg_pct=Decimal("0.20"),
        )
        result = store.get_snapshot_for_date(date(2026, 4, 15))
        assert result["A"]["chg_pct"] == Decimal("0.20")


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

    def test_chg_pct_propagated_from_holdings(self, store):
        """chg_pct on the stub is stored and round-trips through get_snapshot_for_date."""
        holdings = [_holding_stub("A", 700, "1014", chg_pct="-1.28")]
        store.record_all_snapshots(holdings, date(2026, 4, 15))
        result = store.get_snapshot_for_date(date(2026, 4, 15))
        assert result["A"]["chg_pct"] == Decimal("-1.28")

    def test_chg_pct_missing_on_stub_defaults_to_zero(self, store):
        """Stubs without chg_pct attribute (e.g. old code paths) default to '0'."""
        from types import SimpleNamespace
        h = SimpleNamespace(isin="A", qty=100, ltp=Decimal("1014"), current_value=Decimal("101400"))
        store.record_all_snapshots([h], date(2026, 4, 15))
        result = store.get_snapshot_for_date(date(2026, 4, 15))
        assert result["A"]["chg_pct"] == Decimal("0")

    def test_atomicity_rollback_on_error(self, store):
        """A corrupt row mid-batch must roll back the entire transaction."""
        import sqlite3

        h1 = _holding_stub("A", 700, "1014")
        h2 = _holding_stub(None, 700, "1014")  # None isin violates NOT NULL

        with pytest.raises(sqlite3.IntegrityError):
            store.record_all_snapshots([h1, h2], date(2026, 4, 15))

        # Assert table remains empty for this date, proving h1 was rolled back
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

# ---------------------------------------------------------------------------
# Options Snapshots
# ---------------------------------------------------------------------------


class TestOptionsSnapshots:
    def test_record_options_snapshot(self, store):
        store.record_options_snapshot(
            date(2026, 4, 15), "A", "Instrument A", 100, Decimal("10"), Decimal("11"), Decimal("100"), Decimal("50")
        )
        result = store.get_options_snapshot_for_date(date(2026, 4, 15))
        assert len(result) == 1
        assert result[0].trade_symbol == "A"
        assert result[0].realized_pnl_today == Decimal("50")

    def test_get_cumulative_realized_pnl_default_excludes_today(self, store):
        """Default behavior should exclude today (date.today())."""
        today = date.today()
        yesterday = today - timedelta(days=1)
        
        # Yesterday
        store.record_options_snapshot(
            yesterday, "A", "Instrument A", 0, Decimal("10"), Decimal("10"), Decimal("0"), Decimal("100")
        )
        # Today
        store.record_options_snapshot(
            today, "A", "Instrument A", 100, Decimal("10"), Decimal("11"), Decimal("100"), Decimal("50")
        )
        
        # Default implementation should exclude today
        result = store.get_cumulative_realized_pnl()
        assert result["A"] == Decimal("100")

    def test_get_cumulative_realized_pnl_with_explicit_before_date(self, store):
        """Explicit before_date should filter correctly."""
        d1 = date(2026, 4, 10)
        d2 = date(2026, 4, 11)
        d3 = date(2026, 4, 12)

        store.record_options_snapshot(d1, "A", "Ins", 0, Decimal("0"), Decimal("0"), Decimal("0"), Decimal("10"))
        store.record_options_snapshot(d2, "A", "Ins", 0, Decimal("0"), Decimal("0"), Decimal("0"), Decimal("20"))
        store.record_options_snapshot(d3, "A", "Ins", 0, Decimal("0"), Decimal("0"), Decimal("0"), Decimal("30"))

        # before d2 -> only d1
        assert store.get_cumulative_realized_pnl(before_date=d2)["A"] == Decimal("10")
        # before d3 -> d1 + d2
        assert store.get_cumulative_realized_pnl(before_date=d3)["A"] == Decimal("30")
        # before far future -> all
        assert store.get_cumulative_realized_pnl(before_date=date(2026, 5, 1))["A"] == Decimal("60")


# ---------------------------------------------------------------------------
# record_all_options_snapshots
# ---------------------------------------------------------------------------


class TestRecordAllOptionsSnapshots:
    def _make_pos(self, symbol: str, unrealized: str = "1000", realized: str = "0"):
        from src.nuvama.models import NuvamaOptionPosition
        return NuvamaOptionPosition(
            trade_symbol=symbol,
            instrument_name=f"Inst {symbol}",
            net_qty=-50,
            avg_price=Decimal("120"),
            ltp=Decimal("90"),
            unrealized_pnl=Decimal(unrealized),
            realized_pnl_today=Decimal(realized),
        )

    def test_records_multiple_positions(self, store):
        positions = [self._make_pos("A"), self._make_pos("B")]
        store.record_all_options_snapshots(positions, date(2026, 4, 21))
        result = store.get_options_snapshot_for_date(date(2026, 4, 21))
        assert len(result) == 2
        assert {r.trade_symbol for r in result} == {"A", "B"}

    def test_empty_list_no_crash(self, store):
        store.record_all_options_snapshots([], date(2026, 4, 21))
        assert store.get_options_snapshot_for_date(date(2026, 4, 21)) == []

    def test_idempotent_upsert_same_day(self, store):
        """Re-running record_all on the same day must not duplicate rows."""
        pos = self._make_pos("A")
        store.record_all_options_snapshots([pos], date(2026, 4, 21))
        store.record_all_options_snapshots([pos], date(2026, 4, 21))
        result = store.get_options_snapshot_for_date(date(2026, 4, 21))
        assert len(result) == 1  # upsert — not duplicated

    def test_atomicity_rollback_on_error(self, store):
        """A corrupt row mid-batch must roll back the entire transaction."""
        import sqlite3

        h1 = self._make_pos("A")
        h2 = self._make_pos(None)  # None trade_symbol violates NOT NULL

        with pytest.raises(sqlite3.IntegrityError):
            store.record_all_options_snapshots([h1, h2], date(2026, 4, 21))

        # Assert table remains empty for this date, proving h1 was rolled back
        assert store.get_options_snapshot_for_date(date(2026, 4, 21)) == []


# ---------------------------------------------------------------------------
# Intraday store methods
# ---------------------------------------------------------------------------


class TestIntradayStore:
    """Tests for record_intraday_positions, get_intraday_extremes, purge_old_intraday."""

    def _pos(self, symbol: str = "A", unrealized: str = "1000", realized: str = "200"):
        from types import SimpleNamespace
        return SimpleNamespace(
            trade_symbol=symbol,
            net_qty=-50,
            ltp=Decimal("90"),
            unrealized_pnl=Decimal(unrealized),
            realized_pnl_today=Decimal(realized),
        )

    def test_record_intraday_inserts_rows(self, store):
        import sqlite3
        from datetime import datetime
        ts = datetime(2026, 4, 21, 9, 15, 0)
        store.record_intraday_positions(ts, 22950.5, [self._pos("A")])
        with sqlite3.connect(store._db_path) as conn:
            rows = conn.execute("SELECT * FROM nuvama_intraday_snapshots").fetchall()
        assert len(rows) == 1

    def test_get_intraday_extremes_empty_returns_nones(self, store):
        assert store.get_intraday_extremes(date(2026, 4, 21)) == (None, None, None, None)

    def test_get_intraday_extremes_single_timestamp(self, store):
        from datetime import datetime
        ts = datetime(2026, 4, 21, 9, 15, 0)
        store.record_intraday_positions(ts, 22950.5, [self._pos("A", "1000", "200")])
        max_pnl, min_pnl, nifty_high, nifty_low = store.get_intraday_extremes(date(2026, 4, 21))
        # single timestamp: 1000 + 200 = 1200
        assert max_pnl == Decimal("1200")
        assert min_pnl == Decimal("1200")
        assert nifty_high == 22950.5
        assert nifty_low == 22950.5

    def test_get_intraday_extremes_multiple_timestamps(self, store):
        """max/min taken across aggregated per-timestamp totals."""
        from datetime import datetime
        ts1 = datetime(2026, 4, 21, 9, 15, 0)
        ts2 = datetime(2026, 4, 21, 9, 20, 0)
        store.record_intraday_positions(ts1, 22950.5, [self._pos("A", "1000", "0")])
        store.record_intraday_positions(ts2, 23100.0, [self._pos("A", "-500", "0")])
        max_pnl, min_pnl, nifty_high, nifty_low = store.get_intraday_extremes(date(2026, 4, 21))
        assert max_pnl == Decimal("1000")
        assert min_pnl == Decimal("-500")
        assert nifty_high == 23100.0
        assert nifty_low == 22950.5

    def test_get_intraday_extremes_multi_leg_same_timestamp(self, store):
        """Multiple legs at the same timestamp are SUMMED before taking max/min."""
        from datetime import datetime
        ts = datetime(2026, 4, 21, 9, 15, 0)
        pos_a = self._pos("A", unrealized="1000", realized="0")
        pos_b = self._pos("B", unrealized="500", realized="100")
        store.record_intraday_positions(ts, 23000.0, [pos_a, pos_b])
        max_pnl, min_pnl, _, _ = store.get_intraday_extremes(date(2026, 4, 21))
        # 1000 + 0 + 500 + 100 = 1600
        assert max_pnl == Decimal("1600")
        assert min_pnl == Decimal("1600")

    def test_get_intraday_extremes_date_isolation(self, store):
        """Yesterday's rows must not appear in today's query."""
        from datetime import datetime
        ts_today = datetime(2026, 4, 21, 9, 15, 0)
        ts_yest = datetime(2026, 4, 20, 9, 15, 0)
        store.record_intraday_positions(ts_today, 23000.0, [self._pos("A", "1000", "0")])
        store.record_intraday_positions(ts_yest, 22000.0, [self._pos("A", "9999", "0")])
        max_pnl, _, _, _ = store.get_intraday_extremes(date(2026, 4, 21))
        assert max_pnl == Decimal("1000")  # yesterday's 9999 excluded

    def test_get_intraday_extremes_nifty_none_when_no_rows(self, store):
        result = store.get_intraday_extremes(date(2026, 4, 21))
        assert result[2] is None  # nifty_high
        assert result[3] is None  # nifty_low

    def test_purge_removes_old_rows(self, store):
        """Rows older than the retention window are deleted by purge_old_intraday."""
        import sqlite3
        from datetime import datetime, timedelta
        old_ts = (datetime.now() - timedelta(days=31)).isoformat()
        with sqlite3.connect(store._db_path) as conn:
            conn.execute(
                """INSERT INTO nuvama_intraday_snapshots
                   (timestamp, nifty_spot, trade_symbol, net_qty, ltp,
                    unrealized_pnl, realized_pnl_today)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (old_ts, 23000.0, "OLD", -50, "90", "1000", "0"),
            )
        store.purge_old_intraday(days=30)
        with sqlite3.connect(store._db_path) as conn:
            rows = conn.execute("SELECT * FROM nuvama_intraday_snapshots").fetchall()
        assert len(rows) == 0

    def test_purge_keeps_recent_rows(self, store):
        """Rows within the retention window are preserved by purge_old_intraday."""
        import sqlite3
        from datetime import datetime, timedelta
        recent_ts = (datetime.now() - timedelta(days=1)).isoformat()
        with sqlite3.connect(store._db_path) as conn:
            conn.execute(
                """INSERT INTO nuvama_intraday_snapshots
                   (timestamp, nifty_spot, trade_symbol, net_qty, ltp,
                    unrealized_pnl, realized_pnl_today)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (recent_ts, 23000.0, "RECENT", -50, "90", "1000", "0"),
            )
        store.purge_old_intraday(days=30)
        with sqlite3.connect(store._db_path) as conn:
            rows = conn.execute("SELECT * FROM nuvama_intraday_snapshots").fetchall()
        assert len(rows) == 1

    def test_record_intraday_purges_automatically(self, store):
        """record_intraday_positions calls purge on every write — stale rows are cleaned up."""
        import sqlite3
        from datetime import datetime, timedelta
        old_ts = (datetime.now() - timedelta(days=31)).isoformat()
        with sqlite3.connect(store._db_path) as conn:
            conn.execute(
                """INSERT INTO nuvama_intraday_snapshots
                   (timestamp, nifty_spot, trade_symbol, net_qty, ltp,
                    unrealized_pnl, realized_pnl_today)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (old_ts, 23000.0, "OLD", -50, "90", "1000", "0"),
            )
        # new record_intraday_positions call should purge the old row automatically
        new_ts = datetime(2026, 4, 21, 9, 15, 0)
        store.record_intraday_positions(new_ts, 23000.0, [self._pos("NEW")])
        with sqlite3.connect(store._db_path) as conn:
            rows = conn.execute("SELECT trade_symbol FROM nuvama_intraday_snapshots").fetchall()
        symbols = [r[0] for r in rows]
        assert "OLD" not in symbols
        assert "NEW" in symbols

"""Tests for DhanStore options + margin table extensions (Phase C).

All tests use in-memory SQLite (:memory:) via a tmp_path-based DhanStore
pointing at a temp file, or direct Path(":memory:") workaround via monkeypatch.

Strategy: pass a real tmp_path DB so DhanStore.__init__ works normally;
each test gets a fresh DB via the `store` fixture.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from src.dhan.models import DhanFundLimit, DhanOptionPosition, DhanOptionsSummary
from src.dhan.store import DhanStore


# ── Fixtures ──────────────────────────────────────────────────────────────────

_TS = datetime(2026, 5, 6, 10, 0, 0, tzinfo=timezone.utc)
_DATE = date(2026, 5, 6)
_PREV_DATE = date(2026, 5, 1)
_OLD_DATE = date(2026, 3, 1)  # > 30 days before _DATE


@pytest.fixture()
def store(tmp_path: Path) -> DhanStore:
    """Fresh DhanStore backed by a temp SQLite file."""
    return DhanStore(tmp_path / "test.sqlite")


def _make_position(**overrides) -> DhanOptionPosition:
    defaults: dict = {
        "security_id": "41234",
        "trading_symbol": "NIFTY2550523500CE",
        "exchange_segment": "NSE_FNO",
        "product_type": "INTRADAY",
        "position_type": "SHORT",
        "buy_qty": 0,
        "sell_qty": 50,
        "net_qty": -50,
        "buy_avg": Decimal("0.00"),
        "sell_avg": Decimal("120.50"),
        "realized_pnl": Decimal("0.00"),
        "unrealized_pnl": Decimal("1250.00"),
    }
    defaults.update(overrides)
    return DhanOptionPosition(**defaults)


def _make_summary(**overrides) -> DhanOptionsSummary:
    defaults: dict = {
        "realized_pnl": Decimal("3000.00"),
        "unrealized_pnl": Decimal("0.00"),
        "total_pnl": Decimal("3000.00"),
        "position_count": 2,
        "snapshot_ts": _TS,
    }
    defaults.update(overrides)
    return DhanOptionsSummary(**defaults)


def _make_fund_limit(**overrides) -> DhanFundLimit:
    defaults: dict = {
        "available_balance": Decimal("150000.00"),
        "utilized_amount": Decimal("50000.00"),
        "collateral_amount": Decimal("200000.00"),
        "withdrawable_balance": Decimal("100000.00"),
        "snapshot_ts": _TS,
    }
    defaults.update(overrides)
    return DhanFundLimit(**defaults)


# ── record_options_snapshot ───────────────────────────────────────────────────


class TestRecordOptionsSnapshot:
    def test_happy_path_row_inserted(self, store: DhanStore, tmp_path: Path) -> None:
        summary = _make_summary()
        positions = [_make_position()]
        store.record_options_snapshot(_TS, summary, positions, is_eod=False)

        from src.db import connect as _connect
        with _connect(store.db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM dhan_options_snapshots"
            ).fetchall()
        assert len(rows) == 1
        row = rows[0]
        assert Decimal(row["realized_pnl"]) == Decimal("3000.00")
        assert Decimal(row["unrealized_pnl"]) == Decimal("0.00")
        assert Decimal(row["total_pnl"]) == Decimal("3000.00")
        assert row["position_count"] == 2
        assert row["is_eod"] == 0
        assert row["trade_date"] == "2026-05-06"

    def test_decimal_precision_preserved(self, store: DhanStore) -> None:
        summary = _make_summary(realized_pnl=Decimal("1234.56"), total_pnl=Decimal("1234.56"))
        store.record_options_snapshot(_TS, summary, [], is_eod=False)

        from src.db import connect as _connect
        with _connect(store.db_path) as conn:
            row = conn.execute("SELECT realized_pnl FROM dhan_options_snapshots").fetchone()
        assert Decimal(row["realized_pnl"]) == Decimal("1234.56")

    def test_is_eod_flag_persisted(self, store: DhanStore) -> None:
        summary = _make_summary()
        store.record_options_snapshot(_TS, summary, [], is_eod=True)

        from src.db import connect as _connect
        with _connect(store.db_path) as conn:
            row = conn.execute("SELECT is_eod FROM dhan_options_snapshots").fetchone()
        assert row["is_eod"] == 1

    def test_multiple_intraday_rows_allowed(self, store: DhanStore) -> None:
        """Blind append — same date can have many rows."""
        for _ in range(3):
            store.record_options_snapshot(_TS, _make_summary(), [], is_eod=False)

        from src.db import connect as _connect
        with _connect(store.db_path) as conn:
            count = conn.execute(
                "SELECT COUNT(*) AS n FROM dhan_options_snapshots"
            ).fetchone()["n"]
        assert count == 3


# ── get_intraday_extremes ─────────────────────────────────────────────────────


class TestGetIntradayExtremes:
    def _insert(
        self,
        store: DhanStore,
        total_pnl: Decimal,
        is_eod: bool = False,
        ts: datetime = _TS,
    ) -> None:
        summary = _make_summary(total_pnl=total_pnl, realized_pnl=total_pnl)
        store.record_options_snapshot(ts, summary, [], is_eod=is_eod)

    def test_happy_path_three_intraday_one_eod(self, store: DhanStore) -> None:
        self._insert(store, Decimal("1000"))
        self._insert(store, Decimal("3000"))
        self._insert(store, Decimal("2000"))
        self._insert(store, Decimal("2500"), is_eod=True)

        result = store.get_intraday_extremes(_DATE)
        assert result["max_pnl"] == Decimal("3000")
        assert result["min_pnl"] == Decimal("1000")
        assert result["eod_pnl"] == Decimal("2500")

    def test_no_eod_row_returns_none_for_eod_pnl(self, store: DhanStore) -> None:
        self._insert(store, Decimal("500"))
        self._insert(store, Decimal("800"))

        result = store.get_intraday_extremes(_DATE)
        assert result["max_pnl"] == Decimal("800")
        assert result["eod_pnl"] is None

    def test_no_rows_all_none(self, store: DhanStore) -> None:
        result = store.get_intraday_extremes(_DATE)
        assert result["max_pnl"] is None
        assert result["min_pnl"] is None
        assert result["eod_pnl"] is None

    def test_negative_pnl_extremes(self, store: DhanStore) -> None:
        self._insert(store, Decimal("-2000"))
        self._insert(store, Decimal("-500"))

        result = store.get_intraday_extremes(_DATE)
        assert result["max_pnl"] == Decimal("-500")
        assert result["min_pnl"] == Decimal("-2000")


# ── record_margin_snapshot ────────────────────────────────────────────────────


class TestRecordMarginSnapshot:
    def test_happy_path(self, store: DhanStore) -> None:
        fl = _make_fund_limit()
        store.record_margin_snapshot(_TS, fl)

        from src.db import connect as _connect
        with _connect(store.db_path) as conn:
            row = conn.execute("SELECT * FROM dhan_margin_snapshots").fetchone()
        assert row is not None
        assert Decimal(row["available_balance"]) == Decimal("150000.00")
        assert Decimal(row["utilized_amount"]) == Decimal("50000.00")
        assert Decimal(row["collateral_amount"]) == Decimal("200000.00")
        assert Decimal(row["withdrawable_balance"]) == Decimal("100000.00")
        assert row["trade_date"] == "2026-05-06"

    def test_decimal_precision_preserved(self, store: DhanStore) -> None:
        fl = _make_fund_limit(available_balance=Decimal("99999.99"))
        store.record_margin_snapshot(_TS, fl)

        from src.db import connect as _connect
        with _connect(store.db_path) as conn:
            row = conn.execute("SELECT available_balance FROM dhan_margin_snapshots").fetchone()
        assert Decimal(row["available_balance"]) == Decimal("99999.99")


# ── purge_old_intraday ────────────────────────────────────────────────────────


class TestPurgeOldIntraday:
    def test_removes_old_rows_keeps_recent(self, store: DhanStore) -> None:
        old_ts = datetime(2026, 3, 1, 10, 0, 0, tzinfo=timezone.utc)
        recent_ts = _TS  # 2026-05-06

        store.record_options_snapshot(old_ts, _make_summary(), [], is_eod=False)
        store.record_options_snapshot(old_ts, _make_summary(), [], is_eod=False)
        store.record_options_snapshot(recent_ts, _make_summary(), [], is_eod=False)

        deleted = store.purge_old_intraday(days=30)
        assert deleted == 2

        from src.db import connect as _connect
        with _connect(store.db_path) as conn:
            count = conn.execute(
                "SELECT COUNT(*) AS n FROM dhan_options_snapshots"
            ).fetchone()["n"]
        assert count == 1

    def test_nothing_to_purge_returns_zero(self, store: DhanStore) -> None:
        store.record_options_snapshot(_TS, _make_summary(), [], is_eod=False)
        deleted = store.purge_old_intraday(days=30)
        assert deleted == 0

    def test_empty_table_returns_zero(self, store: DhanStore) -> None:
        assert store.purge_old_intraday(days=30) == 0


# ── get_monthly_realized_pnl ──────────────────────────────────────────────────


class TestGetMonthlyRealizedPnl:
    def _insert_eod(
        self,
        store: DhanStore,
        realized: Decimal,
        ts: datetime,
    ) -> None:
        summary = _make_summary(realized_pnl=realized, total_pnl=realized)
        store.record_options_snapshot(ts, summary, [], is_eod=True)

    def _insert_intraday(self, store: DhanStore, realized: Decimal, ts: datetime) -> None:
        summary = _make_summary(realized_pnl=realized, total_pnl=realized)
        store.record_options_snapshot(ts, summary, [], is_eod=False)

    def test_happy_three_eod_rows_same_month(self, store: DhanStore) -> None:
        for day in (6, 7, 8):
            ts = datetime(2026, 5, day, 15, 45, 0, tzinfo=timezone.utc)
            self._insert_eod(store, Decimal("1000"), ts)

        result = store.get_monthly_realized_pnl(2026, 5)
        assert result == Decimal("3000")

    def test_excludes_intraday_rows(self, store: DhanStore) -> None:
        """Intraday rows (is_eod=0) must not be summed — they'd double-count."""
        self._insert_eod(store, Decimal("2000"), _TS)
        self._insert_intraday(store, Decimal("999"), _TS)  # same day intraday tick

        result = store.get_monthly_realized_pnl(2026, 5)
        assert result == Decimal("2000")

    def test_excludes_other_months(self, store: DhanStore) -> None:
        self._insert_eod(store, Decimal("5000"), _TS)  # May
        apr_ts = datetime(2026, 4, 30, 15, 45, 0, tzinfo=timezone.utc)
        self._insert_eod(store, Decimal("3000"), apr_ts)  # April

        assert store.get_monthly_realized_pnl(2026, 5) == Decimal("5000")
        assert store.get_monthly_realized_pnl(2026, 4) == Decimal("3000")

    def test_no_rows_returns_decimal_zero(self, store: DhanStore) -> None:
        assert store.get_monthly_realized_pnl(2026, 5) == Decimal("0")

    def test_negative_realized_pnl_summed_correctly(self, store: DhanStore) -> None:
        self._insert_eod(store, Decimal("-1500"), _TS)
        self._insert_eod(
            store,
            Decimal("500"),
            datetime(2026, 5, 7, 15, 45, 0, tzinfo=timezone.utc),
        )
        assert store.get_monthly_realized_pnl(2026, 5) == Decimal("-1000")

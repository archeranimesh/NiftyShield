"""SQLite persistence for Dhan portfolio snapshots.

Stores daily Dhan holdings snapshots for day-change delta tracking,
plus intraday and EOD options snapshots and margin state.
Uses the shared portfolio.sqlite DB via src/db.py connection factory.

Tables:
    dhan_holdings_snapshots — one row per holding per date (UNIQUE isin+date).
    dhan_options_snapshots  — one row per 15-min intraday tick + one EOD row
                              per day (is_eod flag differentiates them).
    dhan_margin_snapshots   — blind-append margin state from /v2/fundlimit.

Monetary values stored as TEXT for Decimal precision (same convention as
portfolio/store.py and mf/store.py).
"""

from __future__ import annotations

import dataclasses
import json
import sqlite3
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from src.db import connect as _connect
from src.dhan.models import DhanFundLimit, DhanHolding, DhanOptionPosition, DhanOptionsSummary

_SCHEMA = """
CREATE TABLE IF NOT EXISTS dhan_holdings_snapshots (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_date   TEXT NOT NULL,
    trading_symbol  TEXT NOT NULL,
    isin            TEXT NOT NULL,
    security_id     TEXT NOT NULL DEFAULT '',
    exchange        TEXT NOT NULL DEFAULT 'NSE_EQ',
    classification  TEXT NOT NULL,
    total_qty       INTEGER NOT NULL,
    collateral_qty  INTEGER NOT NULL DEFAULT 0,
    avg_cost_price  TEXT NOT NULL,
    ltp             TEXT,
    UNIQUE(isin, snapshot_date)
);

CREATE INDEX IF NOT EXISTS idx_dhan_snapshots_date
    ON dhan_holdings_snapshots(snapshot_date);

CREATE TABLE IF NOT EXISTS dhan_options_snapshots (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ts_utc          TEXT NOT NULL,
    trade_date      TEXT NOT NULL,
    realized_pnl    TEXT NOT NULL,
    unrealized_pnl  TEXT NOT NULL,
    total_pnl       TEXT NOT NULL,
    charges         TEXT NOT NULL DEFAULT '0',
    brokerage       TEXT NOT NULL DEFAULT '0',
    position_count  INTEGER NOT NULL,
    positions_json  TEXT NOT NULL,
    is_eod          INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_dhan_opts_date
    ON dhan_options_snapshots(trade_date);

CREATE TABLE IF NOT EXISTS dhan_margin_snapshots (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    ts_utc               TEXT NOT NULL,
    trade_date           TEXT NOT NULL,
    available_balance    TEXT NOT NULL,
    utilized_amount      TEXT NOT NULL,
    collateral_amount    TEXT NOT NULL,
    withdrawable_balance TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_dhan_margin_date
    ON dhan_margin_snapshots(trade_date);
"""


def _row_to_holding(row: sqlite3.Row) -> DhanHolding:
    """Convert a SQLite row to a DhanHolding."""
    return DhanHolding(
        trading_symbol=row["trading_symbol"],
        isin=row["isin"],
        security_id=row["security_id"],
        exchange=row["exchange"],
        total_qty=row["total_qty"],
        collateral_qty=row["collateral_qty"],
        avg_cost_price=Decimal(row["avg_cost_price"]),
        classification=row["classification"],
        ltp=Decimal(row["ltp"]) if row["ltp"] is not None else None,
    )


class DhanStore:
    """SQLite-backed store for Dhan portfolio snapshots."""

    def __init__(self, db_path: Path) -> None:
        """Initialize store, creating tables if needed.

        Args:
            db_path: Path to SQLite database file (shared with PortfolioStore).
        """
        self.db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        with _connect(self.db_path) as conn:
            conn.executescript(_SCHEMA)
        self._migrate()

    def _migrate(self) -> None:
        """Perform schema migrations (add columns if missing)."""
        with _connect(self.db_path) as conn:
            columns = [
                r["name"]
                for r in conn.execute("PRAGMA table_info(dhan_options_snapshots)").fetchall()
            ]
            if "charges" not in columns:
                conn.execute(
                    "ALTER TABLE dhan_options_snapshots ADD COLUMN charges TEXT NOT NULL DEFAULT '0'"
                )
            if "brokerage" not in columns:
                conn.execute(
                    "ALTER TABLE dhan_options_snapshots ADD COLUMN brokerage TEXT NOT NULL DEFAULT '0'"
                )

    def record_snapshot(
        self, holdings: list[DhanHolding], snapshot_date: date
    ) -> int:
        """Persist a snapshot of Dhan holdings.

        Uses upsert on (isin, snapshot_date) — safe to call multiple
        times on the same day (last write wins).

        Args:
            holdings: List of DhanHolding objects to persist.
            snapshot_date: Date of the snapshot.

        Returns:
            Number of rows written.
        """
        if not holdings:
            return 0

        with _connect(self.db_path) as conn:
            conn.executemany(
                """INSERT INTO dhan_holdings_snapshots
                   (snapshot_date, trading_symbol, isin, security_id, exchange,
                    classification, total_qty, collateral_qty, avg_cost_price, ltp)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(isin, snapshot_date) DO UPDATE SET
                       trading_symbol = excluded.trading_symbol,
                       security_id = excluded.security_id,
                       exchange = excluded.exchange,
                       classification = excluded.classification,
                       total_qty = excluded.total_qty,
                       collateral_qty = excluded.collateral_qty,
                       avg_cost_price = excluded.avg_cost_price,
                       ltp = excluded.ltp""",
                [
                    (
                        snapshot_date.isoformat(),
                        h.trading_symbol,
                        h.isin,
                        h.security_id,
                        h.exchange,
                        h.classification,
                        h.total_qty,
                        h.collateral_qty,
                        str(h.avg_cost_price),
                        str(h.ltp) if h.ltp is not None else None,
                    )
                    for h in holdings
                ],
            )
        return len(holdings)

    def get_snapshot_for_date(self, d: date) -> list[DhanHolding]:
        """Retrieve stored holdings for a specific date.

        Args:
            d: The snapshot date to query.

        Returns:
            List of DhanHolding objects. Empty if no snapshots exist.
        """
        with _connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM dhan_holdings_snapshots WHERE snapshot_date = ?",
                (d.isoformat(),),
            ).fetchall()
        return [_row_to_holding(r) for r in rows]

    def get_prev_snapshot(self, d: date) -> dict[str, DhanHolding]:
        """Return holdings for the most recent date strictly before d, keyed by ISIN.

        Uses MAX(snapshot_date) < d — calendar-agnostic, handles weekends.

        Args:
            d: Reference date.

        Returns:
            {isin: DhanHolding} for the prior date. Empty dict if none exist.
        """
        with _connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT MAX(snapshot_date) AS prev_date FROM dhan_holdings_snapshots"
                " WHERE snapshot_date < ?",
                (d.isoformat(),),
            ).fetchone()
            if not row or not row["prev_date"]:
                return {}
            rows = conn.execute(
                "SELECT * FROM dhan_holdings_snapshots WHERE snapshot_date = ?",
                (row["prev_date"],),
            ).fetchall()
        return {r["isin"]: _row_to_holding(r) for r in rows}

    # ── Options snapshots ─────────────────────────────────────────────────────

    def record_options_snapshot(
        self,
        ts: datetime,
        summary: DhanOptionsSummary,
        positions: list[DhanOptionPosition],
        is_eod: bool = False,
    ) -> None:
        """Persist one options snapshot row.

        positions is serialized to a JSON blob (default=str handles Decimal).
        Intraday rows (is_eod=False): blind append — multiple ticks per day are expected.
        EOD rows (is_eod=True): idempotent — any existing EOD row for the same trade_date
        is deleted before the new row is inserted, so re-running the EOD script cannot
        produce duplicate rows that double-count in get_monthly_realized_pnl.

        Args:
            ts: UTC timestamp of the snapshot.
            summary: Aggregated P&L summary.
            positions: Individual position objects to store as JSON blob.
            is_eod: True for the final 3:45 PM EOD snapshot; False for intraday ticks.
        """
        positions_json = json.dumps(
            [dataclasses.asdict(p) for p in positions], default=str
        )
        trade_date = ts.date().isoformat()
        with _connect(self.db_path) as conn:
            if is_eod:
                conn.execute(
                    "DELETE FROM dhan_options_snapshots WHERE trade_date = ? AND is_eod = 1",
                    (trade_date,),
                )
            conn.execute(
                """INSERT INTO dhan_options_snapshots
                   (ts_utc, trade_date, realized_pnl, unrealized_pnl, total_pnl,
                    charges, brokerage, position_count, positions_json, is_eod)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    ts.isoformat(),
                    trade_date,
                    str(summary.realized_pnl),
                    str(summary.unrealized_pnl),
                    str(summary.total_pnl),
                    str(summary.charges),
                    str(summary.brokerage),
                    summary.position_count,
                    positions_json,
                    1 if is_eod else 0,
                ),
            )

    def get_intraday_extremes(self, trade_date: date) -> dict:
        """Return max_pnl, min_pnl, eod_pnl for a given trade date.

        max_pnl and min_pnl are computed across all rows (intraday + EOD).
        eod_pnl is taken from the single row where is_eod=1.

        Args:
            trade_date: The trading day to query.

        Returns:
            Dict with keys: max_pnl, min_pnl, eod_pnl (each Decimal | None).
            All values are None when no rows exist for the date.
        """
        d = trade_date.isoformat()
        with _connect(self.db_path) as conn:
            agg = conn.execute(
                """SELECT MAX(CAST(total_pnl AS REAL)) AS max_pnl,
                          MIN(CAST(total_pnl AS REAL)) AS min_pnl
                   FROM dhan_options_snapshots
                   WHERE trade_date = ?""",
                (d,),
            ).fetchone()
            eod_row = conn.execute(
                """SELECT total_pnl FROM dhan_options_snapshots
                   WHERE trade_date = ? AND is_eod = 1
                   LIMIT 1""",
                (d,),
            ).fetchone()

        max_pnl = Decimal(str(agg["max_pnl"])) if agg["max_pnl"] is not None else None
        min_pnl = Decimal(str(agg["min_pnl"])) if agg["min_pnl"] is not None else None
        eod_pnl = Decimal(eod_row["total_pnl"]) if eod_row else None
        return {"max_pnl": max_pnl, "min_pnl": min_pnl, "eod_pnl": eod_pnl}

    def get_eod_options_snapshot(
        self, trade_date: date
    ) -> tuple[DhanOptionsSummary, list[DhanOptionPosition]] | None:
        """Read back the EOD options snapshot stored for a given trading date.

        Picks the latest is_eod=1 row for the date (there should only be one,
        but ORDER BY ts_utc DESC LIMIT 1 is defensive against duplicates).

        Args:
            trade_date: The trading day to retrieve.

        Returns:
            (DhanOptionsSummary, list[DhanOptionPosition]) if an EOD row exists,
            None otherwise.
        """
        d = trade_date.isoformat()
        with _connect(self.db_path) as conn:
            row = conn.execute(
                """SELECT ts_utc, realized_pnl, unrealized_pnl, total_pnl,
                          charges, brokerage, position_count, positions_json
                   FROM dhan_options_snapshots
                   WHERE trade_date = ? AND is_eod = 1
                   ORDER BY ts_utc DESC LIMIT 1""",
                (d,),
            ).fetchone()
        if row is None:
            return None

        ts = datetime.fromisoformat(row["ts_utc"])
        summary = DhanOptionsSummary(
            realized_pnl=Decimal(row["realized_pnl"]),
            unrealized_pnl=Decimal(row["unrealized_pnl"]),
            total_pnl=Decimal(row["total_pnl"]),
            charges=Decimal(row["charges"]),
            brokerage=Decimal(row["brokerage"]),
            position_count=row["position_count"],
            snapshot_ts=ts,
        )
        raw_pos: list[dict] = json.loads(row["positions_json"])
        positions = [
            DhanOptionPosition(
                security_id=p["security_id"],
                trading_symbol=p["trading_symbol"],
                exchange_segment=p["exchange_segment"],
                product_type=p["product_type"],
                position_type=p["position_type"],
                buy_qty=p["buy_qty"],
                sell_qty=p["sell_qty"],
                net_qty=p["net_qty"],
                buy_avg=Decimal(p["buy_avg"]),
                sell_avg=Decimal(p["sell_avg"]),
                realized_pnl=Decimal(p["realized_pnl"]),
                unrealized_pnl=Decimal(p["unrealized_pnl"]),
            )
            for p in raw_pos
        ]
        return summary, positions

    def get_monthly_realized_pnl(self, year: int, month: int) -> Decimal:
        """Sum realized_pnl from all EOD snapshots (is_eod=1) in a calendar month.

        Only EOD rows are summed — intraday rows hold cumulative-to-that-point
        values and would double-count if included.

        Args:
            year: Calendar year (e.g. 2026).
            month: Calendar month (1–12).

        Returns:
            Decimal sum. Returns Decimal("0") if no EOD rows exist for the month.
        """
        prefix = f"{year:04d}-{month:02d}-%"
        with _connect(self.db_path) as conn:
            row = conn.execute(
                """SELECT SUM(CAST(realized_pnl AS REAL)) AS total
                   FROM dhan_options_snapshots
                   WHERE is_eod = 1 AND trade_date LIKE ?""",
                (prefix,),
            ).fetchone()
        raw = row["total"] if row and row["total"] is not None else None
        return Decimal(str(raw)) if raw is not None else Decimal("0")

    def get_monthly_charges(self, year: int, month: int) -> tuple[Decimal, Decimal]:
        """Sum charges and brokerage from EOD rows (is_eod=1) in a calendar month.

        Args:
            year: Calendar year.
            month: Calendar month (1–12).

        Returns:
            (total_charges, total_brokerage) as Decimals.
        """
        prefix = f"{year:04d}-{month:02d}-%"
        with _connect(self.db_path) as conn:
            row = conn.execute(
                """SELECT SUM(CAST(charges AS REAL)) AS total_charges,
                          SUM(CAST(brokerage AS REAL)) AS total_brokerage
                   FROM dhan_options_snapshots
                   WHERE is_eod = 1 AND trade_date LIKE ?""",
                (prefix,),
            ).fetchone()

        charges = row["total_charges"] if row and row["total_charges"] is not None else 0
        brokerage = row["total_brokerage"] if row and row["total_brokerage"] is not None else 0

        return (Decimal(str(charges)), Decimal(str(brokerage)))

    # ── Margin snapshots ──────────────────────────────────────────────────────

    def record_margin_snapshot(self, ts: datetime, fund_limit: DhanFundLimit) -> None:
        """Persist one margin snapshot row. Blind append — no upsert.

        Args:
            ts: UTC timestamp of the fetch.
            fund_limit: Parsed DhanFundLimit from /v2/fundlimit.
        """
        trade_date = ts.date().isoformat()
        with _connect(self.db_path) as conn:
            conn.execute(
                """INSERT INTO dhan_margin_snapshots
                   (ts_utc, trade_date, available_balance, utilized_amount,
                    collateral_amount, withdrawable_balance)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    ts.isoformat(),
                    trade_date,
                    str(fund_limit.available_balance),
                    str(fund_limit.utilized_amount),
                    str(fund_limit.collateral_amount),
                    str(fund_limit.withdrawable_balance),
                ),
            )

    def purge_old_intraday(self, days: int = 30) -> int:
        """Delete dhan_options_snapshots rows older than `days`.

        Args:
            days: Retention window. Rows with trade_date older than this are removed.

        Returns:
            Number of rows deleted.
        """
        with _connect(self.db_path) as conn:
            cursor = conn.execute(
                """DELETE FROM dhan_options_snapshots
                   WHERE trade_date < date('now', ?)""",
                (f"-{days} days",),
            )
        return cursor.rowcount

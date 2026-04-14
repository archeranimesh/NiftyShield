"""SQLite persistence for Dhan portfolio snapshots.

Stores daily Dhan holdings snapshots for day-change delta tracking.
Uses the shared portfolio.sqlite DB via src/db.py connection factory.

Table: dhan_holdings_snapshots
    Stores one row per holding per date. UNIQUE on (isin, snapshot_date)
    so re-runs are idempotent (last write wins via upsert).

Monetary values stored as TEXT for Decimal precision (same convention as
portfolio/store.py and mf/store.py).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

from src.db import connect as _connect
from src.dhan.models import DhanHolding

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
"""


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
        return [self._row_to_holding(r) for r in rows]

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
        return {r["isin"]: self._row_to_holding(r) for r in rows}

    @staticmethod
    def _row_to_holding(row) -> DhanHolding:
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

"""SQLite persistence for mutual fund tracking.

Two tables added to the shared portfolio DB:
- mf_transactions: immutable ledger of purchase/SIP/redemption events.
- mf_nav_snapshots: daily NAV per scheme with upsert semantics.

Holdings and P&L are derived at query time — nothing is pre-computed.
"""

from __future__ import annotations

import sqlite3
from datetime import date
from decimal import Decimal
from pathlib import Path

from src.db import connect as _connect
from src.models.mf import MFHolding, MFNavSnapshot, MFTransaction, TransactionType

_SCHEMA = """
CREATE TABLE IF NOT EXISTS mf_transactions (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    scheme_name       TEXT NOT NULL,
    amfi_code         TEXT NOT NULL,
    transaction_date  TEXT NOT NULL,
    units             TEXT NOT NULL,
    amount            TEXT NOT NULL,
    transaction_type  TEXT NOT NULL,
    UNIQUE(amfi_code, transaction_date, transaction_type)
);

CREATE TABLE IF NOT EXISTS mf_nav_snapshots (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_date TEXT NOT NULL,
    amfi_code     TEXT NOT NULL,
    scheme_name   TEXT NOT NULL,
    nav           TEXT NOT NULL,
    UNIQUE(amfi_code, snapshot_date)
);

CREATE INDEX IF NOT EXISTS idx_mf_tx_amfi_date
    ON mf_transactions(amfi_code, transaction_date);

CREATE INDEX IF NOT EXISTS idx_mf_nav_amfi_date
    ON mf_nav_snapshots(amfi_code, snapshot_date);
"""


class MFStore:
    """SQLite-backed store for mutual fund transaction and NAV tracking.

    Shares the same DB file as PortfolioStore — tables are additive,
    no schema conflicts. Both stores can be initialised on the same path.
    """

    def __init__(self, db_path: Path) -> None:
        """Initialise store, creating MF tables if they don't exist.

        Args:
            db_path: Path to the shared SQLite database file.
        """
        self.db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        with _connect(self.db_path) as conn:
            conn.executescript(_SCHEMA)

    # ── Transactions ──────────────────────────────────────────────

    def insert_transaction(self, tx: MFTransaction) -> int:
        """Insert a transaction. Silently skips exact duplicates (idempotent).

        Uniqueness is on (amfi_code, transaction_date, transaction_type),
        so re-running a seed script never double-inserts.

        Args:
            tx: The transaction to persist.

        Returns:
            Row id of the inserted or pre-existing row.
        """
        with _connect(self.db_path) as conn:
            cursor = conn.execute(
                """INSERT INTO mf_transactions
                   (scheme_name, amfi_code, transaction_date, units, amount, transaction_type)
                   VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(amfi_code, transaction_date, transaction_type) DO NOTHING""",
                (
                    tx.scheme_name,
                    tx.amfi_code,
                    tx.transaction_date.isoformat(),
                    str(tx.units),
                    str(tx.amount),
                    tx.transaction_type.value,
                ),
            )
            if cursor.lastrowid:
                return cursor.lastrowid
            # Row already existed — return its id.
            row = conn.execute(
                """SELECT id FROM mf_transactions
                   WHERE amfi_code = ? AND transaction_date = ? AND transaction_type = ?""",
                (tx.amfi_code, tx.transaction_date.isoformat(), tx.transaction_type.value),
            ).fetchone()
            return row["id"]

    def insert_transactions_bulk(self, txs: list[MFTransaction]) -> int:
        """Bulk insert transactions, skipping duplicates.

        Args:
            txs: Transactions to persist.

        Returns:
            Number of rows attempted (mirrors PortfolioStore.record_snapshots_bulk).
        """
        with _connect(self.db_path) as conn:
            conn.executemany(
                """INSERT INTO mf_transactions
                   (scheme_name, amfi_code, transaction_date, units, amount, transaction_type)
                   VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(amfi_code, transaction_date, transaction_type) DO NOTHING""",
                [
                    (
                        tx.scheme_name,
                        tx.amfi_code,
                        tx.transaction_date.isoformat(),
                        str(tx.units),
                        str(tx.amount),
                        tx.transaction_type.value,
                    )
                    for tx in txs
                ],
            )
            return len(txs)

    def get_transactions(
        self,
        amfi_code: str | None = None,
        from_date: date | None = None,
        to_date: date | None = None,
    ) -> list[MFTransaction]:
        """Retrieve transactions, optionally filtered by scheme and/or date range.

        Args:
            amfi_code: If provided, restrict to this scheme.
            from_date: Inclusive lower bound on transaction_date.
            to_date: Inclusive upper bound on transaction_date.

        Returns:
            Transactions ordered by transaction_date then id.
        """
        query = "SELECT * FROM mf_transactions WHERE 1=1"
        params: list = []

        if amfi_code is not None:
            query += " AND amfi_code = ?"
            params.append(amfi_code)
        if from_date is not None:
            query += " AND transaction_date >= ?"
            params.append(from_date.isoformat())
        if to_date is not None:
            query += " AND transaction_date <= ?"
            params.append(to_date.isoformat())

        query += " ORDER BY transaction_date, id"

        with _connect(self.db_path) as conn:
            rows = conn.execute(query, params).fetchall()
            return [self._row_to_transaction(r) for r in rows]

    def get_holdings(self) -> dict[str, MFHolding]:
        """Net holdings per scheme, derived from the transaction ledger.

        INITIAL and SIP transactions add units and amount; REDEMPTIONs subtract.
        Aggregation is done in Python to preserve exact Decimal arithmetic.
        scheme_name is taken from the most recent transaction for each scheme
        (all transactions for a scheme carry the same name in practice).

        Returns:
            {amfi_code: MFHolding} for schemes with a positive net unit balance.
        """
        _units: dict[str, Decimal] = {}
        _invested: dict[str, Decimal] = {}
        _names: dict[str, str] = {}

        for tx in self.get_transactions():
            _names[tx.amfi_code] = tx.scheme_name
            if tx.transaction_type in (TransactionType.INITIAL, TransactionType.SIP):
                _units[tx.amfi_code] = _units.get(tx.amfi_code, Decimal(0)) + tx.units
                _invested[tx.amfi_code] = _invested.get(tx.amfi_code, Decimal(0)) + tx.amount
            else:  # REDEMPTION
                _units[tx.amfi_code] = _units.get(tx.amfi_code, Decimal(0)) - tx.units
                _invested[tx.amfi_code] = _invested.get(tx.amfi_code, Decimal(0)) - tx.amount

        return {
            code: MFHolding(
                amfi_code=code,
                scheme_name=_names[code],
                total_units=units,
                total_invested=_invested[code],
            )
            for code, units in _units.items()
            if units > 0
        }

    # ── NAV Snapshots ─────────────────────────────────────────────

    def upsert_nav_snapshot(self, snap: MFNavSnapshot) -> int:
        """Insert or update a NAV snapshot. Last write wins on (amfi_code, snapshot_date).

        Args:
            snap: The NAV snapshot to persist.

        Returns:
            Row id of the upserted row.
        """
        with _connect(self.db_path) as conn:
            cursor = conn.execute(
                """INSERT INTO mf_nav_snapshots (snapshot_date, amfi_code, scheme_name, nav)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(amfi_code, snapshot_date) DO UPDATE SET
                       scheme_name = excluded.scheme_name,
                       nav         = excluded.nav""",
                (
                    snap.snapshot_date.isoformat(),
                    snap.amfi_code,
                    snap.scheme_name,
                    str(snap.nav),
                ),
            )
            return cursor.lastrowid  # type: ignore[return-value]

    def upsert_nav_snapshots_bulk(self, snaps: list[MFNavSnapshot]) -> int:
        """Bulk upsert NAV snapshots.

        Args:
            snaps: Snapshots to persist.

        Returns:
            Number of rows processed.
        """
        with _connect(self.db_path) as conn:
            conn.executemany(
                """INSERT INTO mf_nav_snapshots (snapshot_date, amfi_code, scheme_name, nav)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(amfi_code, snapshot_date) DO UPDATE SET
                       scheme_name = excluded.scheme_name,
                       nav         = excluded.nav""",
                [
                    (
                        s.snapshot_date.isoformat(),
                        s.amfi_code,
                        s.scheme_name,
                        str(s.nav),
                    )
                    for s in snaps
                ],
            )
            return len(snaps)

    def get_nav_snapshots(
        self,
        amfi_code: str,
        from_date: date | None = None,
        to_date: date | None = None,
    ) -> list[MFNavSnapshot]:
        """Retrieve NAV snapshots for a scheme, optionally filtered by date range.

        Args:
            amfi_code: The scheme to query.
            from_date: Inclusive lower bound on snapshot_date.
            to_date: Inclusive upper bound on snapshot_date.

        Returns:
            Snapshots ordered by snapshot_date ascending.
        """
        query = (
            "SELECT snapshot_date, amfi_code, scheme_name, nav"
            " FROM mf_nav_snapshots WHERE amfi_code = ?"
        )
        params: list = [amfi_code]

        if from_date is not None:
            query += " AND snapshot_date >= ?"
            params.append(from_date.isoformat())
        if to_date is not None:
            query += " AND snapshot_date <= ?"
            params.append(to_date.isoformat())

        query += " ORDER BY snapshot_date"

        with _connect(self.db_path) as conn:
            rows = conn.execute(query, params).fetchall()
            return [self._row_to_nav_snapshot(r) for r in rows]

    def get_nav_snapshots_for_date(self, d: date) -> list[MFNavSnapshot]:
        """Return all NAV snapshots recorded on a specific date.

        Used by the historical query path in daily_snapshot.py to reconstruct
        MF P&L from stored NAVs without fetching from AMFI.

        Args:
            d: The snapshot date to query.

        Returns:
            All MFNavSnapshot rows for that date, ordered by amfi_code.
            Empty list if no snapshots exist for the date.
        """
        with _connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT snapshot_date, amfi_code, scheme_name, nav"
                " FROM mf_nav_snapshots WHERE snapshot_date = ? ORDER BY amfi_code",
                (d.isoformat(),),
            ).fetchall()
            return [self._row_to_nav_snapshot(r) for r in rows]

    def get_prev_nav_snapshots(self, d: date) -> list[MFNavSnapshot]:
        """Return all NAV snapshots for the most recent date strictly before d.

        Uses MAX(snapshot_date) < d — calendar-agnostic, handles weekends and
        holidays identically to PortfolioStore.get_prev_snapshots.

        Args:
            d: Reference date (usually today). Looks for the nearest prior date.

        Returns:
            All MFNavSnapshot rows for the prior date, ordered by amfi_code.
            Empty list if no prior snapshots exist.
        """
        with _connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT MAX(snapshot_date) AS prev_date FROM mf_nav_snapshots"
                " WHERE snapshot_date < ?",
                (d.isoformat(),),
            ).fetchone()
            if not row or not row["prev_date"]:
                return []
            rows = conn.execute(
                "SELECT snapshot_date, amfi_code, scheme_name, nav"
                " FROM mf_nav_snapshots WHERE snapshot_date = ? ORDER BY amfi_code",
                (row["prev_date"],),
            ).fetchall()
            return [self._row_to_nav_snapshot(r) for r in rows]

    def get_latest_nav(self, amfi_code: str) -> MFNavSnapshot | None:
        """Return the most recent NAV snapshot for a scheme.

        Args:
            amfi_code: The scheme to query.

        Returns:
            Latest MFNavSnapshot, or None if the scheme has no snapshots.
        """
        with _connect(self.db_path) as conn:
            row = conn.execute(
                """SELECT * FROM mf_nav_snapshots
                   WHERE amfi_code = ?
                   ORDER BY snapshot_date DESC LIMIT 1""",
                (amfi_code,),
            ).fetchone()
            return self._row_to_nav_snapshot(row) if row else None

    # ── Row mappers ───────────────────────────────────────────────

    @staticmethod
    def _row_to_transaction(row: sqlite3.Row) -> MFTransaction:
        return MFTransaction(
            scheme_name=row["scheme_name"],
            amfi_code=row["amfi_code"],
            transaction_date=date.fromisoformat(row["transaction_date"]),
            units=Decimal(row["units"]),
            amount=Decimal(row["amount"]),
            transaction_type=TransactionType(row["transaction_type"]),
        )

    @staticmethod
    def _row_to_nav_snapshot(row: sqlite3.Row) -> MFNavSnapshot:
        return MFNavSnapshot(
            snapshot_date=date.fromisoformat(row["snapshot_date"]),
            amfi_code=row["amfi_code"],
            scheme_name=row["scheme_name"],
            nav=Decimal(row["nav"]),
        )

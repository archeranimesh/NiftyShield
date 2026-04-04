"""SQLite persistence for portfolio tracking.

Three tables: strategies, legs, daily_snapshots.
All writes are explicit — no ORM magic. Reads return Pydantic models.
"""

from __future__ import annotations

import sqlite3
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from src.db import connect as _connect
from src.portfolio.models import (
    AssetType,
    DailySnapshot,
    Direction,
    Leg,
    ProductType,
    Strategy,
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS strategies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    description TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS legs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy_id INTEGER NOT NULL REFERENCES strategies(id),
    instrument_key TEXT NOT NULL,
    display_name TEXT NOT NULL,
    asset_type TEXT NOT NULL,
    direction TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    lot_size INTEGER NOT NULL DEFAULT 1,
    entry_price TEXT NOT NULL,
    entry_date TEXT NOT NULL,
    expiry TEXT,
    strike REAL,
    product_type TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS daily_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    leg_id INTEGER NOT NULL REFERENCES legs(id),
    snapshot_date TEXT NOT NULL,
    ltp TEXT NOT NULL,
    close TEXT,
    iv REAL,
    delta REAL,
    theta REAL,
    gamma REAL,
    vega REAL,
    oi INTEGER,
    volume INTEGER,
    underlying_price TEXT,
    UNIQUE(leg_id, snapshot_date)
);

CREATE INDEX IF NOT EXISTS idx_snapshots_leg_date
    ON daily_snapshots(leg_id, snapshot_date);

CREATE INDEX IF NOT EXISTS idx_snapshots_date
    ON daily_snapshots(snapshot_date);

CREATE INDEX IF NOT EXISTS idx_legs_strategy
    ON legs(strategy_id);
"""


class PortfolioStore:
    """SQLite-backed store for strategy portfolio tracking."""

    def __init__(self, db_path: Path) -> None:
        """Initialize store, creating DB and tables if needed.

        Args:
            db_path: Path to SQLite database file.
        """
        self.db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        with _connect(self.db_path) as conn:
            conn.executescript(_SCHEMA)

    # ── Strategy CRUD ────────────────────────────────────────────

    def upsert_strategy(self, strategy: Strategy) -> int:
        """Insert or update a strategy. Returns the strategy ID."""
        with _connect(self.db_path) as conn:
            cursor = conn.execute(
                """INSERT INTO strategies (name, description)
                   VALUES (?, ?)
                   ON CONFLICT(name) DO UPDATE SET description = excluded.description
                   RETURNING id""",
                (strategy.name, strategy.description),
            )
            strategy_id = cursor.fetchone()["id"]

            for leg in strategy.legs:
                leg.strategy_id = strategy_id
                self._upsert_leg(conn, leg)

            return strategy_id

    def _upsert_leg(self, conn: sqlite3.Connection, leg: Leg) -> int:
        """Insert a leg if it doesn't already exist (matched on strategy + instrument + direction + entry_price)."""
        existing = conn.execute(
            """SELECT id FROM legs
               WHERE strategy_id = ? AND instrument_key = ? AND direction = ?
                     AND entry_price = ?""",
            (leg.strategy_id, leg.instrument_key, leg.direction.value, str(leg.entry_price)),
        ).fetchone()

        if existing:
            return existing["id"]

        cursor = conn.execute(
            """INSERT INTO legs
               (strategy_id, instrument_key, display_name, asset_type, direction,
                quantity, lot_size, entry_price, entry_date, expiry, strike, product_type)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                leg.strategy_id,
                leg.instrument_key,
                leg.display_name,
                leg.asset_type.value,
                leg.direction.value,
                leg.quantity,
                leg.lot_size,
                str(leg.entry_price),
                leg.entry_date.isoformat(),
                leg.expiry.isoformat() if leg.expiry else None,
                leg.strike,
                leg.product_type.value,
            ),
        )
        return cursor.lastrowid  # type: ignore[return-value]

    def get_strategy(self, name: str) -> Strategy | None:
        """Load a strategy with all its legs by name."""
        with _connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM strategies WHERE name = ?", (name,)
            ).fetchone()
            if not row:
                return None

            legs = self._get_legs(conn, row["id"])
            return Strategy(
                id=row["id"],
                name=row["name"],
                description=row["description"],
                legs=legs,
                created_at=datetime.fromisoformat(row["created_at"]),
            )

    def get_all_strategies(self) -> list[Strategy]:
        """Load all strategies with their legs."""
        with _connect(self.db_path) as conn:
            rows = conn.execute("SELECT * FROM strategies ORDER BY name").fetchall()
            strategies = []
            for row in rows:
                legs = self._get_legs(conn, row["id"])
                strategies.append(
                    Strategy(
                        id=row["id"],
                        name=row["name"],
                        description=row["description"],
                        legs=legs,
                        created_at=datetime.fromisoformat(row["created_at"]),
                    )
                )
            return strategies

    def _get_legs(self, conn: sqlite3.Connection, strategy_id: int) -> list[Leg]:
        """Load all legs for a strategy."""
        rows = conn.execute(
            "SELECT * FROM legs WHERE strategy_id = ? ORDER BY id", (strategy_id,)
        ).fetchall()
        return [
            Leg(
                id=r["id"],
                strategy_id=r["strategy_id"],
                instrument_key=r["instrument_key"],
                display_name=r["display_name"],
                asset_type=AssetType(r["asset_type"]),
                direction=Direction(r["direction"]),
                quantity=r["quantity"],
                lot_size=r["lot_size"],
                entry_price=Decimal(r["entry_price"]),
                entry_date=date.fromisoformat(r["entry_date"]),
                expiry=date.fromisoformat(r["expiry"]) if r["expiry"] else None,
                strike=r["strike"],
                product_type=ProductType(r["product_type"]),
            )
            for r in rows
        ]

    # ── Snapshot CRUD ────────────────────────────────────────────

    def record_snapshot(self, snapshot: DailySnapshot) -> int:
        """Insert or replace a daily snapshot for a leg.

        Uses UPSERT on (leg_id, snapshot_date) — safe to call multiple
        times on the same day (last write wins).
        """
        with _connect(self.db_path) as conn:
            cursor = conn.execute(
                """INSERT INTO daily_snapshots
                   (leg_id, snapshot_date, ltp, close, iv, delta, theta,
                    gamma, vega, oi, volume, underlying_price)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(leg_id, snapshot_date) DO UPDATE SET
                       ltp = excluded.ltp,
                       close = excluded.close,
                       iv = excluded.iv,
                       delta = excluded.delta,
                       theta = excluded.theta,
                       gamma = excluded.gamma,
                       vega = excluded.vega,
                       oi = excluded.oi,
                       volume = excluded.volume,
                       underlying_price = excluded.underlying_price""",
                (
                    snapshot.leg_id,
                    snapshot.snapshot_date.isoformat(),
                    str(snapshot.ltp),
                    str(snapshot.close) if snapshot.close is not None else None,
                    snapshot.iv,
                    snapshot.delta,
                    snapshot.theta,
                    snapshot.gamma,
                    snapshot.vega,
                    snapshot.oi,
                    snapshot.volume,
                    str(snapshot.underlying_price) if snapshot.underlying_price is not None else None,
                ),
            )
            return cursor.lastrowid  # type: ignore[return-value]

    def record_snapshots_bulk(self, snapshots: list[DailySnapshot]) -> int:
        """Bulk insert/replace snapshots. Returns count of rows affected."""
        with _connect(self.db_path) as conn:
            conn.executemany(
                """INSERT INTO daily_snapshots
                   (leg_id, snapshot_date, ltp, close, iv, delta, theta,
                    gamma, vega, oi, volume, underlying_price)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(leg_id, snapshot_date) DO UPDATE SET
                       ltp = excluded.ltp,
                       close = excluded.close,
                       iv = excluded.iv,
                       delta = excluded.delta,
                       theta = excluded.theta,
                       gamma = excluded.gamma,
                       vega = excluded.vega,
                       oi = excluded.oi,
                       volume = excluded.volume,
                       underlying_price = excluded.underlying_price""",
                [
                    (
                        s.leg_id, s.snapshot_date.isoformat(),
                        str(s.ltp),
                        str(s.close) if s.close is not None else None,
                        s.iv, s.delta, s.theta, s.gamma, s.vega,
                        s.oi, s.volume,
                        str(s.underlying_price) if s.underlying_price is not None else None,
                    )
                    for s in snapshots
                ],
            )
            return len(snapshots)

    def get_snapshots(
        self,
        leg_id: int,
        from_date: date | None = None,
        to_date: date | None = None,
    ) -> list[DailySnapshot]:
        """Retrieve snapshots for a leg, optionally filtered by date range."""
        query = "SELECT * FROM daily_snapshots WHERE leg_id = ?"
        params: list = [leg_id]

        if from_date:
            query += " AND snapshot_date >= ?"
            params.append(from_date.isoformat())
        if to_date:
            query += " AND snapshot_date <= ?"
            params.append(to_date.isoformat())

        query += " ORDER BY snapshot_date"

        with _connect(self.db_path) as conn:
            rows = conn.execute(query, params).fetchall()
            return [self._row_to_snapshot(r) for r in rows]

    def get_strategy_snapshots(
        self,
        strategy_name: str,
        from_date: date | None = None,
        to_date: date | None = None,
    ) -> dict[int, list[DailySnapshot]]:
        """Get all snapshots for all legs of a strategy, keyed by leg_id."""
        strategy = self.get_strategy(strategy_name)
        if not strategy:
            return {}
        return {
            leg.id: self.get_snapshots(leg.id, from_date, to_date)  # type: ignore[arg-type]
            for leg in strategy.legs
            if leg.id is not None
        }

    def get_latest_snapshot_date(self) -> date | None:
        """Return the most recent snapshot date across all legs."""
        with _connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT MAX(snapshot_date) as max_date FROM daily_snapshots"
            ).fetchone()
            if row and row["max_date"]:
                return date.fromisoformat(row["max_date"])
            return None

    @staticmethod
    def _row_to_snapshot(row: sqlite3.Row) -> DailySnapshot:
        return DailySnapshot(
            id=row["id"],
            leg_id=row["leg_id"],
            snapshot_date=date.fromisoformat(row["snapshot_date"]),
            ltp=Decimal(row["ltp"]),
            close=Decimal(row["close"]) if row["close"] is not None else None,
            iv=row["iv"],
            delta=row["delta"],
            theta=row["theta"],
            gamma=row["gamma"],
            vega=row["vega"],
            oi=row["oi"],
            volume=row["volume"],
            underlying_price=Decimal(row["underlying_price"]) if row["underlying_price"] is not None else None,
        )

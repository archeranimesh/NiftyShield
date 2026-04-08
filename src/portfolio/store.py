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
    Trade,
    TradeAction,
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

CREATE TABLE IF NOT EXISTS trades (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy_name  TEXT NOT NULL,
    leg_role       TEXT NOT NULL,
    instrument_key TEXT NOT NULL,
    trade_date     TEXT NOT NULL,
    action         TEXT NOT NULL,
    quantity       INTEGER NOT NULL,
    price          TEXT NOT NULL,
    notes          TEXT NOT NULL DEFAULT '',
    UNIQUE(strategy_name, leg_role, trade_date, action)
);

CREATE INDEX IF NOT EXISTS idx_trades_strategy_leg
    ON trades(strategy_name, leg_role, trade_date);
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

    def get_snapshots_for_date(self, d: date) -> dict[int, DailySnapshot]:
        """Return all leg snapshots recorded on a specific date, keyed by leg_id.

        Used by the historical query path in daily_snapshot.py to reconstruct
        P&L from stored LTPs without any live API call.

        Args:
            d: The snapshot date to query.

        Returns:
            {leg_id: DailySnapshot} for every leg that has a row on that date.
            Empty dict if no snapshots exist for the date.
        """
        with _connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM daily_snapshots WHERE snapshot_date = ?",
                (d.isoformat(),),
            ).fetchall()
            return {r["leg_id"]: self._row_to_snapshot(r) for r in rows}

    def get_prev_snapshots(self, d: date) -> dict[int, DailySnapshot]:
        """Return all leg snapshots for the most recent date strictly before d.

        Uses MAX(snapshot_date) < d — calendar-agnostic and handles weekends
        or holidays without any date arithmetic. If today is Monday, this
        returns Friday's snapshots automatically.

        Args:
            d: Reference date (usually today). Looks for the nearest prior date.

        Returns:
            {leg_id: DailySnapshot} for the prior date, or empty dict if no
            prior snapshots exist.
        """
        with _connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT MAX(snapshot_date) AS prev_date FROM daily_snapshots"
                " WHERE snapshot_date < ?",
                (d.isoformat(),),
            ).fetchone()
            if not row or not row["prev_date"]:
                return {}
            rows = conn.execute(
                "SELECT * FROM daily_snapshots WHERE snapshot_date = ?",
                (row["prev_date"],),
            ).fetchall()
            return {r["leg_id"]: self._row_to_snapshot(r) for r in rows}

    def get_latest_snapshot_date(self) -> date | None:
        """Return the most recent snapshot date across all legs."""
        with _connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT MAX(snapshot_date) as max_date FROM daily_snapshots"
            ).fetchone()
            if row and row["max_date"]:
                return date.fromisoformat(row["max_date"])
            return None

    # ── Trades ledger ────────────────────────────────────────────

    def record_trade(self, trade: Trade) -> None:
        """Insert a trade into the ledger. Silently skips exact duplicates.

        Uniqueness is on (strategy_name, leg_role, trade_date, action) so
        re-running seed or record scripts is always idempotent.

        Args:
            trade: The trade to persist.
        """
        with _connect(self.db_path) as conn:
            conn.execute(
                """INSERT INTO trades
                   (strategy_name, leg_role, instrument_key, trade_date,
                    action, quantity, price, notes)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(strategy_name, leg_role, trade_date, action)
                   DO NOTHING""",
                (
                    trade.strategy_name,
                    trade.leg_role,
                    trade.instrument_key,
                    trade.trade_date.isoformat(),
                    trade.action.value,
                    trade.quantity,
                    str(trade.price),
                    trade.notes,
                ),
            )

    def get_trades(
        self,
        strategy_name: str,
        leg_role: str | None = None,
    ) -> list[Trade]:
        """Return all trades for a strategy, optionally filtered by leg_role.

        Args:
            strategy_name: Strategy to query (e.g. "ILTS").
            leg_role: If provided, restrict to this leg (e.g. "EBBETF0431").

        Returns:
            Trades ordered by trade_date ASC, then id ASC.
        """
        query = "SELECT * FROM trades WHERE strategy_name = ?"
        params: list = [strategy_name]

        if leg_role is not None:
            query += " AND leg_role = ?"
            params.append(leg_role)

        query += " ORDER BY trade_date, id"

        with _connect(self.db_path) as conn:
            rows = conn.execute(query, params).fetchall()
            return [self._row_to_trade(r) for r in rows]

    def get_position(
        self, strategy_name: str, leg_role: str
    ) -> tuple[int, Decimal]:
        """Derive net quantity and weighted average buy price from the ledger.

        Net quantity = SUM(qty for BUY) - SUM(qty for SELL).
        Avg buy price = weighted average of BUY trades only; SELL prices are
        not used (same rationale as get_holdings() in MFStore — Python Decimal
        arithmetic, not SQL CAST).

        Args:
            strategy_name: Strategy to query.
            leg_role: Leg within that strategy.

        Returns:
            (net_quantity, avg_buy_price). Returns (0, Decimal("0")) when no
            trades exist for the given strategy/leg combination.
        """
        trades = self.get_trades(strategy_name, leg_role)
        if not trades:
            return (0, Decimal("0"))

        buy_qty = Decimal("0")
        buy_value = Decimal("0")
        sell_qty = Decimal("0")

        for t in trades:
            if t.action == TradeAction.BUY:
                buy_qty += t.quantity
                buy_value += Decimal(t.quantity) * t.price
            else:
                sell_qty += t.quantity

        net_qty = int(buy_qty - sell_qty)
        avg_price = (buy_value / buy_qty) if buy_qty > 0 else Decimal("0")
        return (net_qty, avg_price)

    @staticmethod
    def _row_to_trade(row: sqlite3.Row) -> Trade:
        return Trade(
            strategy_name=row["strategy_name"],
            leg_role=row["leg_role"],
            instrument_key=row["instrument_key"],
            trade_date=date.fromisoformat(row["trade_date"]),
            action=TradeAction(row["action"]),
            quantity=row["quantity"],
            price=Decimal(row["price"]),
            notes=row["notes"],
        )

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

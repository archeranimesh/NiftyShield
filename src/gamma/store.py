"""SQLite persistence for the near-expiry gamma strategy.

Defines schemas and read/write interfaces for gamma chain snapshots
and watchlist entries. All monetary and Greek values are stored as TEXT
to preserve Decimal precision.
"""

from __future__ import annotations

import datetime
import decimal
import sqlite3
import typing

from src.gamma.models import GammaChainSnapshot, GammaWatchlistEntry

_SCHEMA = """
CREATE TABLE IF NOT EXISTS gamma_chain_snapshots (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_date      TEXT NOT NULL,          -- YYYY-MM-DD
    snapshot_time      TEXT NOT NULL,          -- HH:MM IST
    expiry_date        TEXT NOT NULL,          -- YYYY-MM-DD
    strike             INTEGER NOT NULL,
    option_type        TEXT NOT NULL,          -- CE | PE
    dte_calendar       INTEGER NOT NULL,

    -- Underlying
    nifty_spot         TEXT NOT NULL,
    nifty_futures      TEXT,
    india_vix          TEXT,

    -- Greeks
    delta_val          TEXT,
    gamma_val          TEXT,
    vega_val           TEXT,
    theta_val          TEXT,
    iv_val             TEXT,

    -- Derived
    gamma_gearing      TEXT,
    distance_pct       TEXT,

    -- Quote
    best_bid           TEXT,
    best_ask           TEXT,
    bid_ask_spread     TEXT,

    -- Volume / OI
    oi                 INTEGER,
    oi_change_1d       TEXT,                   -- fractional change vs prior day
    volume_day         INTEGER,

    -- Computed percentiles (populated during calibration update, NULL initially)
    strike_iv_pctile_20d    TEXT,
    gamma_gearing_pctile_dte TEXT,             -- percentile in DTE bucket

    created_at         TEXT NOT NULL,

    UNIQUE (snapshot_date, snapshot_time, expiry_date, strike, option_type)
);

CREATE INDEX IF NOT EXISTS idx_gcs_expiry
    ON gamma_chain_snapshots (expiry_date);
CREATE INDEX IF NOT EXISTS idx_gcs_strike
    ON gamma_chain_snapshots (strike, option_type);
CREATE INDEX IF NOT EXISTS idx_gcs_date
    ON gamma_chain_snapshots (snapshot_date);

CREATE TABLE IF NOT EXISTS gamma_watchlist (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    expiry_date           TEXT NOT NULL,
    strike                INTEGER NOT NULL,
    option_type           TEXT NOT NULL,       -- CE | PE
    added_date            TEXT NOT NULL,       -- date first qualified
    last_seen_date        TEXT NOT NULL,       -- updated daily by Phase A
    removed_date          TEXT,               -- NULL = still active
    -- Reason: spot_moved_away | oi_unwinding | expired
    removal_reason        TEXT,

    -- State at last evaluation
    distance_pct          TEXT,
    gamma_gearing         TEXT,
    oi                    INTEGER,
    oi_change_1d          TEXT,
    days_on_watchlist     INTEGER,

    -- Elevation flag
    elevated              INTEGER DEFAULT 0,  -- 1 = priority candidate
    elevation_reason      TEXT,

    UNIQUE (expiry_date, strike, option_type)  -- one active row per strike
);

CREATE INDEX IF NOT EXISTS idx_gwl_active
    ON gamma_watchlist (removed_date, expiry_date);
"""


def _dec(v: decimal.Decimal | None) -> str | None:
    """Helper to convert a Decimal to its DB string representation, or None."""
    return str(v) if v is not None else None


def _row_to_chain_snapshot(row: sqlite3.Row) -> GammaChainSnapshot:
    dt = datetime.datetime.fromisoformat(row["created_at"])
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    return GammaChainSnapshot(
        snapshot_date=datetime.date.fromisoformat(row["snapshot_date"]),
        snapshot_time=row["snapshot_time"],
        expiry_date=datetime.date.fromisoformat(row["expiry_date"]),
        strike=row["strike"],
        option_type=row["option_type"],
        dte_calendar=row["dte_calendar"],
        nifty_spot=decimal.Decimal(row["nifty_spot"]),
        nifty_futures=(
            decimal.Decimal(row["nifty_futures"])
            if row["nifty_futures"] is not None
            else None
        ),
        india_vix=(
            decimal.Decimal(row["india_vix"])
            if row["india_vix"] is not None
            else None
        ),
        delta_val=(
            decimal.Decimal(row["delta_val"])
            if row["delta_val"] is not None
            else None
        ),
        gamma_val=(
            decimal.Decimal(row["gamma_val"])
            if row["gamma_val"] is not None
            else None
        ),
        vega_val=(
            decimal.Decimal(row["vega_val"])
            if row["vega_val"] is not None
            else None
        ),
        theta_val=(
            decimal.Decimal(row["theta_val"])
            if row["theta_val"] is not None
            else None
        ),
        iv_val=(
            decimal.Decimal(row["iv_val"])
            if row["iv_val"] is not None
            else None
        ),
        gamma_gearing=(
            decimal.Decimal(row["gamma_gearing"])
            if row["gamma_gearing"] is not None
            else None
        ),
        distance_pct=(
            decimal.Decimal(row["distance_pct"])
            if row["distance_pct"] is not None
            else None
        ),
        best_bid=(
            decimal.Decimal(row["best_bid"])
            if row["best_bid"] is not None
            else None
        ),
        best_ask=(
            decimal.Decimal(row["best_ask"])
            if row["best_ask"] is not None
            else None
        ),
        bid_ask_spread=(
            decimal.Decimal(row["bid_ask_spread"])
            if row["bid_ask_spread"] is not None
            else None
        ),
        oi=row["oi"],
        oi_change_1d=(
            decimal.Decimal(row["oi_change_1d"])
            if row["oi_change_1d"] is not None
            else None
        ),
        volume_day=row["volume_day"],
        strike_iv_pctile_20d=(
            decimal.Decimal(row["strike_iv_pctile_20d"])
            if row["strike_iv_pctile_20d"] is not None
            else None
        ),
        gamma_gearing_pctile_dte=(
            decimal.Decimal(row["gamma_gearing_pctile_dte"])
            if row["gamma_gearing_pctile_dte"] is not None
            else None
        ),
        created_at=dt,
    )


def _row_to_watchlist_entry(row: sqlite3.Row) -> GammaWatchlistEntry:
    return GammaWatchlistEntry(
        expiry_date=datetime.date.fromisoformat(row["expiry_date"]),
        strike=row["strike"],
        option_type=row["option_type"],
        added_date=datetime.date.fromisoformat(row["added_date"]),
        last_seen_date=datetime.date.fromisoformat(row["last_seen_date"]),
        removed_date=(
            datetime.date.fromisoformat(row["removed_date"])
            if row["removed_date"] is not None
            else None
        ),
        removal_reason=row["removal_reason"],
        distance_pct=(
            decimal.Decimal(row["distance_pct"])
            if row["distance_pct"] is not None
            else None
        ),
        gamma_gearing=(
            decimal.Decimal(row["gamma_gearing"])
            if row["gamma_gearing"] is not None
            else None
        ),
        oi=row["oi"],
        oi_change_1d=(
            decimal.Decimal(row["oi_change_1d"])
            if row["oi_change_1d"] is not None
            else None
        ),
        days_on_watchlist=row["days_on_watchlist"],
        elevated=bool(row["elevated"]),
        elevation_reason=row["elevation_reason"],
    )


class GammaStore:
    """SQLite-backed store for near-expiry gamma data.

    All methods are stateless and expect an active sqlite3.Connection.
    The connection MUST have conn.row_factory = sqlite3.Row set before
    calling any read methods (this is the default in src.db.connect).
    """

    def create_tables(self, conn: sqlite3.Connection) -> None:
        """Create the gamma tables if they do not exist.

        Args:
            conn: An open SQLite connection.
        """
        conn.executescript(_SCHEMA)

    def insert_chain_snapshot(
        self, conn: sqlite3.Connection, snap: GammaChainSnapshot
    ) -> None:
        """Insert or update a chain snapshot in the database.

        Preserves the original created_at timestamp on conflict updates.

        Args:
            conn: An open SQLite connection.
            snap: The GammaChainSnapshot object to save.
        """
        conn.execute(
            """
            INSERT INTO gamma_chain_snapshots (
                snapshot_date, snapshot_time, expiry_date, strike, option_type,
                dte_calendar, nifty_spot, nifty_futures, india_vix, delta_val,
                gamma_val, vega_val, theta_val, iv_val, gamma_gearing,
                distance_pct, best_bid, best_ask, bid_ask_spread, oi,
                oi_change_1d, volume_day, strike_iv_pctile_20d,
                gamma_gearing_pctile_dte, created_at
            ) VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?
            )
            ON CONFLICT (
                snapshot_date, snapshot_time, expiry_date, strike, option_type
            ) DO UPDATE SET
                dte_calendar = excluded.dte_calendar,
                nifty_spot = excluded.nifty_spot,
                nifty_futures = excluded.nifty_futures,
                india_vix = excluded.india_vix,
                delta_val = excluded.delta_val,
                gamma_val = excluded.gamma_val,
                vega_val = excluded.vega_val,
                theta_val = excluded.theta_val,
                iv_val = excluded.iv_val,
                gamma_gearing = excluded.gamma_gearing,
                distance_pct = excluded.distance_pct,
                best_bid = excluded.best_bid,
                best_ask = excluded.best_ask,
                bid_ask_spread = excluded.bid_ask_spread,
                oi = excluded.oi,
                oi_change_1d = excluded.oi_change_1d,
                volume_day = excluded.volume_day,
                strike_iv_pctile_20d = excluded.strike_iv_pctile_20d,
                gamma_gearing_pctile_dte =
                    excluded.gamma_gearing_pctile_dte
            """,
            (
                snap.snapshot_date.isoformat(),
                snap.snapshot_time,
                snap.expiry_date.isoformat(),
                snap.strike,
                snap.option_type,
                snap.dte_calendar,
                str(snap.nifty_spot),
                _dec(snap.nifty_futures),
                _dec(snap.india_vix),
                _dec(snap.delta_val),
                _dec(snap.gamma_val),
                _dec(snap.vega_val),
                _dec(snap.theta_val),
                _dec(snap.iv_val),
                _dec(snap.gamma_gearing),
                _dec(snap.distance_pct),
                _dec(snap.best_bid),
                _dec(snap.best_ask),
                _dec(snap.bid_ask_spread),
                snap.oi,
                _dec(snap.oi_change_1d),
                snap.volume_day,
                _dec(snap.strike_iv_pctile_20d),
                _dec(snap.gamma_gearing_pctile_dte),
                snap.created_at.isoformat(),
            ),
        )

    def get_chain_snapshots(
        self,
        conn: sqlite3.Connection,
        expiry_date: datetime.date,
        snapshot_date: datetime.date,
    ) -> list[GammaChainSnapshot]:
        """Fetch chain snapshots for an expiry and snapshot date.

        Args:
            conn: An open SQLite connection.
            expiry_date: The expiry date to filter by.
            snapshot_date: The snapshot date to filter by.

        Returns:
            A list of GammaChainSnapshot objects ordered by strike ASC,
            option_type ASC.
        """
        rows = conn.execute(
            """
            SELECT * FROM gamma_chain_snapshots
            WHERE expiry_date = ? AND snapshot_date = ?
            ORDER BY strike ASC, option_type ASC
            """,
            (expiry_date.isoformat(), snapshot_date.isoformat()),
        ).fetchall()
        return [_row_to_chain_snapshot(r) for r in rows]

    def get_yesterday_snapshot(
        self,
        conn: sqlite3.Connection,
        expiry_date: datetime.date,
        strike: int,
        option_type: typing.Literal["CE", "PE"],
        today: datetime.date,
    ) -> GammaChainSnapshot | None:
        """Fetch the most recent snapshot before today for the option.

        Args:
            conn: An open SQLite connection.
            expiry_date: Expiry date of the option.
            strike: Strike price.
            option_type: Option type ('CE' | 'PE').
            today: Date threshold (returns snapshots strictly before this date).

        Returns:
            The most recent GammaChainSnapshot before today, or None if none.
        """
        row = conn.execute(
            """
            SELECT * FROM gamma_chain_snapshots
            WHERE expiry_date = ?
              AND strike = ?
              AND option_type = ?
              AND snapshot_date < ?
            ORDER BY snapshot_date DESC, snapshot_time DESC
            LIMIT 1
            """,
            (expiry_date.isoformat(), strike, option_type, today.isoformat()),
        ).fetchone()
        return _row_to_chain_snapshot(row) if row is not None else None

    def upsert_watchlist(
        self, conn: sqlite3.Connection, entry: GammaWatchlistEntry
    ) -> None:
        """Insert or update a watchlist entry.

        Args:
            conn: An open SQLite connection.
            entry: The GammaWatchlistEntry object.
        """
        conn.execute(
            """
            INSERT INTO gamma_watchlist (
                expiry_date, strike, option_type, added_date, last_seen_date,
                removed_date, removal_reason, distance_pct, gamma_gearing,
                oi, oi_change_1d, days_on_watchlist, elevated,
                elevation_reason
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (
                expiry_date, strike, option_type
            ) DO UPDATE SET
                last_seen_date = excluded.last_seen_date,
                removed_date = excluded.removed_date,
                removal_reason = excluded.removal_reason,
                distance_pct = excluded.distance_pct,
                gamma_gearing = excluded.gamma_gearing,
                oi = excluded.oi,
                oi_change_1d = excluded.oi_change_1d,
                days_on_watchlist = excluded.days_on_watchlist,
                elevated = excluded.elevated,
                elevation_reason = excluded.elevation_reason
            """,
            (
                entry.expiry_date.isoformat(),
                entry.strike,
                entry.option_type,
                entry.added_date.isoformat(),
                entry.last_seen_date.isoformat(),
                (
                    entry.removed_date.isoformat()
                    if entry.removed_date is not None
                    else None
                ),
                entry.removal_reason,
                _dec(entry.distance_pct),
                _dec(entry.gamma_gearing),
                entry.oi,
                _dec(entry.oi_change_1d),
                entry.days_on_watchlist,
                1 if entry.elevated else 0,
                entry.elevation_reason,
            ),
        )

    def get_active_watchlist(
        self, conn: sqlite3.Connection, expiry_date: datetime.date
    ) -> list[GammaWatchlistEntry]:
        """Fetch all active watchlist entries for a given expiry date.

        Args:
            conn: An open SQLite connection.
            expiry_date: Expiry date to filter by.

        Returns:
            A list of active GammaWatchlistEntry objects.
        """
        rows = conn.execute(
            """
            SELECT * FROM gamma_watchlist
            WHERE expiry_date = ? AND removed_date IS NULL
            ORDER BY strike ASC, option_type ASC
            """,
            (expiry_date.isoformat(),),
        ).fetchall()
        return [_row_to_watchlist_entry(r) for r in rows]

    def remove_from_watchlist(
        self,
        conn: sqlite3.Connection,
        expiry_date: datetime.date,
        strike: int,
        option_type: typing.Literal["CE", "PE"],
        reason: str,
        removed_date: datetime.date,
    ) -> bool:
        """Mark an entry on the watchlist as removed.

        Args:
            conn: An open SQLite connection.
            expiry_date: Expiry date of the option.
            strike: Strike price.
            option_type: Option type ('CE' | 'PE').
            reason: Reason for removal.
            removed_date: Date of removal.

        Returns:
            True if the watchlist entry was updated, False otherwise.
        """
        cur = conn.execute(
            """
            UPDATE gamma_watchlist
            SET removed_date = ?, removal_reason = ?
            WHERE expiry_date = ? AND strike = ? AND option_type = ?
            """,
            (
                removed_date.isoformat(),
                reason,
                expiry_date.isoformat(),
                strike,
                option_type,
            ),
        )
        return cur.rowcount > 0

    def get_iv_history(
        self,
        conn: sqlite3.Connection,
        strike: int,
        option_type: typing.Literal["CE", "PE"],
        limit_days: int = 20,
    ) -> list[decimal.Decimal]:
        """Fetch the trailing IV values across the last limit_days.

        Args:
            conn: An open SQLite connection.
            strike: Strike price.
            option_type: Option type ('CE' | 'PE').
            limit_days: Maximum number of historical trading days to look back.

        Returns:
            A list of Decimal objects representing the historical IV values,
            ordered chronologically (oldest to newest).
        """
        rows = conn.execute(
            """
            SELECT iv_val FROM gamma_chain_snapshots
            WHERE strike = ?
              AND option_type = ?
              AND iv_val IS NOT NULL
              AND snapshot_date IN (
                SELECT DISTINCT snapshot_date FROM gamma_chain_snapshots
                WHERE strike = ?
                  AND option_type = ?
                  AND iv_val IS NOT NULL
                ORDER BY snapshot_date DESC
                LIMIT ?
              )
            ORDER BY snapshot_date DESC, snapshot_time DESC
            """,
            (strike, option_type, strike, option_type, limit_days),
        ).fetchall()
        return [decimal.Decimal(row["iv_val"]) for row in reversed(rows)]

    def get_gearing_by_dte(
        self, conn: sqlite3.Connection, target_dte: int, limit_days: int = 60
    ) -> list[decimal.Decimal]:
        """Fetch all gamma_gearing values for target DTE over limit_days.

        Args:
            conn: An open SQLite connection.
            target_dte: The calendar DTE to match.
            limit_days: Number of distinct trailing snapshot dates
                to look back.

        Returns:
            A list of Decimal objects representing the gamma_gearing values,
            ordered by snapshot_date DESC.
        """
        rows = conn.execute(
            """
            SELECT gamma_gearing FROM gamma_chain_snapshots
            WHERE dte_calendar = ?
              AND gamma_gearing IS NOT NULL
              AND snapshot_date IN (
                SELECT DISTINCT snapshot_date FROM gamma_chain_snapshots
                WHERE dte_calendar = ?
                  AND gamma_gearing IS NOT NULL
                ORDER BY snapshot_date DESC
                LIMIT ?
            )
            ORDER BY snapshot_date DESC, snapshot_time DESC
            """,
            (target_dte, target_dte, limit_days),
        ).fetchall()
        return [decimal.Decimal(row["gamma_gearing"]) for row in rows]

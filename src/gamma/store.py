"""SQLite persistence for the near-expiry gamma strategy.

Defines schemas and read/write interfaces for gamma chain snapshots
and watchlist entries. All monetary and Greek values are stored as TEXT
to preserve Decimal precision.
"""

from __future__ import annotations

import sqlite3
from datetime import date, datetime
from decimal import Decimal

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

CREATE INDEX IF NOT EXISTS idx_gcs_expiry  ON gamma_chain_snapshots (expiry_date);
CREATE INDEX IF NOT EXISTS idx_gcs_strike  ON gamma_chain_snapshots (strike, option_type);
CREATE INDEX IF NOT EXISTS idx_gcs_date    ON gamma_chain_snapshots (snapshot_date);

CREATE TABLE IF NOT EXISTS gamma_watchlist (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    expiry_date           TEXT NOT NULL,
    strike                INTEGER NOT NULL,
    option_type           TEXT NOT NULL,       -- CE | PE
    added_date            TEXT NOT NULL,       -- date first qualified
    last_seen_date        TEXT NOT NULL,       -- updated daily by Phase A
    removed_date          TEXT,               -- NULL = still active
    removal_reason        TEXT,               -- spot_moved_away | oi_unwinding | expired

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

CREATE INDEX IF NOT EXISTS idx_gwl_active ON gamma_watchlist (removed_date, expiry_date);
"""


def _row_to_chain_snapshot(row: sqlite3.Row) -> GammaChainSnapshot:
    return GammaChainSnapshot(
        snapshot_date=date.fromisoformat(row["snapshot_date"]),
        snapshot_time=row["snapshot_time"],
        expiry_date=date.fromisoformat(row["expiry_date"]),
        strike=row["strike"],
        option_type=row["option_type"],
        dte_calendar=row["dte_calendar"],
        nifty_spot=Decimal(row["nifty_spot"]),
        nifty_futures=(
            Decimal(row["nifty_futures"])
            if row["nifty_futures"] is not None
            else None
        ),
        india_vix=(
            Decimal(row["india_vix"])
            if row["india_vix"] is not None
            else None
        ),
        delta_val=(
            Decimal(row["delta_val"])
            if row["delta_val"] is not None
            else None
        ),
        gamma_val=(
            Decimal(row["gamma_val"])
            if row["gamma_val"] is not None
            else None
        ),
        vega_val=(
            Decimal(row["vega_val"])
            if row["vega_val"] is not None
            else None
        ),
        theta_val=(
            Decimal(row["theta_val"])
            if row["theta_val"] is not None
            else None
        ),
        iv_val=(
            Decimal(row["iv_val"])
            if row["iv_val"] is not None
            else None
        ),
        gamma_gearing=(
            Decimal(row["gamma_gearing"])
            if row["gamma_gearing"] is not None
            else None
        ),
        distance_pct=(
            Decimal(row["distance_pct"])
            if row["distance_pct"] is not None
            else None
        ),
        best_bid=(
            Decimal(row["best_bid"])
            if row["best_bid"] is not None
            else None
        ),
        best_ask=(
            Decimal(row["best_ask"])
            if row["best_ask"] is not None
            else None
        ),
        bid_ask_spread=(
            Decimal(row["bid_ask_spread"])
            if row["bid_ask_spread"] is not None
            else None
        ),
        oi=row["oi"],
        oi_change_1d=(
            Decimal(row["oi_change_1d"])
            if row["oi_change_1d"] is not None
            else None
        ),
        volume_day=row["volume_day"],
        strike_iv_pctile_20d=(
            Decimal(row["strike_iv_pctile_20d"])
            if row["strike_iv_pctile_20d"] is not None
            else None
        ),
        gamma_gearing_pctile_dte=(
            Decimal(row["gamma_gearing_pctile_dte"])
            if row["gamma_gearing_pctile_dte"] is not None
            else None
        ),
        created_at=datetime.fromisoformat(row["created_at"]),
    )


def _row_to_watchlist_entry(row: sqlite3.Row) -> GammaWatchlistEntry:
    return GammaWatchlistEntry(
        expiry_date=date.fromisoformat(row["expiry_date"]),
        strike=row["strike"],
        option_type=row["option_type"],
        added_date=date.fromisoformat(row["added_date"]),
        last_seen_date=date.fromisoformat(row["last_seen_date"]),
        removed_date=(
            date.fromisoformat(row["removed_date"])
            if row["removed_date"] is not None
            else None
        ),
        removal_reason=row["removal_reason"],
        distance_pct=(
            Decimal(row["distance_pct"])
            if row["distance_pct"] is not None
            else None
        ),
        gamma_gearing=(
            Decimal(row["gamma_gearing"])
            if row["gamma_gearing"] is not None
            else None
        ),
        oi=row["oi"],
        oi_change_1d=(
            Decimal(row["oi_change_1d"])
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
                    excluded.gamma_gearing_pctile_dte,
                created_at = excluded.created_at
            """,
            (
                snap.snapshot_date.isoformat(),
                snap.snapshot_time,
                snap.expiry_date.isoformat(),
                snap.strike,
                snap.option_type,
                snap.dte_calendar,
                str(snap.nifty_spot),
                (
                    str(snap.nifty_futures)
                    if snap.nifty_futures is not None
                    else None
                ),
                (
                    str(snap.india_vix)
                    if snap.india_vix is not None
                    else None
                ),
                (
                    str(snap.delta_val)
                    if snap.delta_val is not None
                    else None
                ),
                (
                    str(snap.gamma_val)
                    if snap.gamma_val is not None
                    else None
                ),
                (
                    str(snap.vega_val)
                    if snap.vega_val is not None
                    else None
                ),
                (
                    str(snap.theta_val)
                    if snap.theta_val is not None
                    else None
                ),
                (
                    str(snap.iv_val)
                    if snap.iv_val is not None
                    else None
                ),
                (
                    str(snap.gamma_gearing)
                    if snap.gamma_gearing is not None
                    else None
                ),
                (
                    str(snap.distance_pct)
                    if snap.distance_pct is not None
                    else None
                ),
                (
                    str(snap.best_bid)
                    if snap.best_bid is not None
                    else None
                ),
                (
                    str(snap.best_ask)
                    if snap.best_ask is not None
                    else None
                ),
                (
                    str(snap.bid_ask_spread)
                    if snap.bid_ask_spread is not None
                    else None
                ),
                snap.oi,
                (
                    str(snap.oi_change_1d)
                    if snap.oi_change_1d is not None
                    else None
                ),
                snap.volume_day,
                (
                    str(snap.strike_iv_pctile_20d)
                    if snap.strike_iv_pctile_20d is not None
                    else None
                ),
                (
                    str(snap.gamma_gearing_pctile_dte)
                    if snap.gamma_gearing_pctile_dte is not None
                    else None
                ),
                snap.created_at.isoformat(),
            ),
        )

    def get_chain_snapshots(
        self,
        conn: sqlite3.Connection,
        expiry_date: date,
        snapshot_date: date,
    ) -> list[GammaChainSnapshot]:
        """Fetch all chain snapshots for a given expiry date and snapshot date.

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
        expiry_date: date,
        strike: int,
        option_type: str,
        today: date,
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
                (
                    str(entry.distance_pct)
                    if entry.distance_pct is not None
                    else None
                ),
                (
                    str(entry.gamma_gearing)
                    if entry.gamma_gearing is not None
                    else None
                ),
                entry.oi,
                (
                    str(entry.oi_change_1d)
                    if entry.oi_change_1d is not None
                    else None
                ),
                entry.days_on_watchlist,
                1 if entry.elevated else 0,
                entry.elevation_reason,
            ),
        )

    def get_active_watchlist(
        self, conn: sqlite3.Connection, expiry_date: date
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
        expiry_date: date,
        strike: int,
        option_type: str,
        reason: str,
        removed_date: date,
    ) -> None:
        """Mark an entry on the watchlist as removed.

        Args:
            conn: An open SQLite connection.
            expiry_date: Expiry date of the option.
            strike: Strike price.
            option_type: Option type ('CE' | 'PE').
            reason: Reason for removal.
            removed_date: Date of removal.
        """
        conn.execute(
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

    def get_iv_history(
        self,
        conn: sqlite3.Connection,
        strike: int,
        option_type: str,
        limit: int = 20,
    ) -> list[Decimal]:
        """Fetch the trailing limit IV values, across all expiries.

        Args:
            conn: An open SQLite connection.
            strike: Strike price.
            option_type: Option type ('CE' | 'PE').
            limit: Maximum number of historical values to retrieve.

        Returns:
            A list of Decimal objects representing the historical IV values,
            in chronological order.
        """
        rows = conn.execute(
            """
            SELECT iv_val FROM gamma_chain_snapshots
            WHERE strike = ? AND option_type = ? AND iv_val IS NOT NULL
            ORDER BY snapshot_date DESC, snapshot_time DESC
            LIMIT ?
            """,
            (strike, option_type, limit),
        ).fetchall()
        return [Decimal(row["iv_val"]) for row in reversed(rows)]

    def get_gearing_by_dte(
        self, conn: sqlite3.Connection, target_dte: int, limit_days: int = 60
    ) -> list[Decimal]:
        """Fetch all gamma_gearing values for target DTE over limit_days.

        Args:
            conn: An open SQLite connection.
            target_dte: The calendar DTE to match.
            limit_days: Number of distinct trailing snapshot dates to look back.

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
                ORDER BY snapshot_date DESC
                LIMIT ?
            )
            ORDER BY snapshot_date DESC, snapshot_time DESC
            """,
            (target_dte, limit_days),
        ).fetchall()
        return [Decimal(row["gamma_gearing"]) for row in rows]

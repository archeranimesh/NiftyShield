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

from src.gamma.models import (
    GammaChainSnapshot,
    GammaSignalLogEntry,
    GammaWatchlistEntry,
)

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

CREATE TABLE IF NOT EXISTS gamma_signal_log (
    signal_id              TEXT PRIMARY KEY,
    signal_timestamp       TEXT NOT NULL,      -- UTC ISO-8601
    expiry_date            TEXT NOT NULL,
    strike                 INTEGER NOT NULL,
    option_type            TEXT NOT NULL,      -- CE | PE
    dte_calendar           INTEGER NOT NULL,
    dte_trading            INTEGER NOT NULL,
    watchlist_hit          INTEGER NOT NULL DEFAULT 0,  -- was strike on watchlist?
    watchlist_elevated     INTEGER NOT NULL DEFAULT 0,  -- was it elevated priority?

    -- Underlying context
    nifty_spot             TEXT NOT NULL,
    nifty_futures_price    TEXT,
    futures_basis          TEXT,
    underlying_return_1m   TEXT,
    underlying_return_5m   TEXT,
    underlying_return_15m  TEXT,
    underlying_rvol_15m    TEXT,
    distance_pct           TEXT NOT NULL,
    distance_sigma         TEXT,

    -- Option quote (Upstox)
    best_bid               TEXT,
    best_ask               TEXT NOT NULL,
    bid_ask_spread         TEXT,
    spread_pct_of_mid      TEXT,

    -- L2 depth (Dhan; NULL if not subscribed)
    bid_qty_l1             INTEGER,
    ask_qty_l1             INTEGER,
    total_bid_qty          INTEGER,
    total_ask_qty          INTEGER,

    -- Greeks
    delta_val              TEXT,
    gamma_val              TEXT NOT NULL,
    vega_val               TEXT,
    theta_val              TEXT,
    iv_val                 TEXT,

    -- Derived
    gamma_gearing          TEXT NOT NULL,
    speed_5m               TEXT,
    speed_5m_unavailable   INTEGER DEFAULT 0,
    theoretical_price      TEXT,
    model_edge             TEXT,
    strike_iv_pctile_20d   TEXT,
    gearing_threshold_used TEXT,              -- bootstrap value or calibrated p75

    -- Volume / OI
    volume_5m              INTEGER,
    volume_zscore_5m       TEXT,
    oi_now                 INTEGER,
    oi_velocity_15m        TEXT,
    option_price_rising    INTEGER,

    -- Market regime
    india_vix              TEXT,
    india_vix_pctile_252d  TEXT,
    event_flag             INTEGER NOT NULL DEFAULT 0,
    event_type             TEXT,

    -- Filter results (1=pass, 0=fail, NULL=not evaluated)
    f0_hard_pass           INTEGER,
    f0_fail_reason         TEXT,
    f1_directional_pass    INTEGER,
    f2_convexity_pass      INTEGER,
    f3_quality_pass        INTEGER,
    f3_quality_method      TEXT,
    f4_flow_pass           INTEGER,
    signal_triggered       INTEGER NOT NULL DEFAULT 0,

    -- Paper trade
    paper_trade_attempted  INTEGER NOT NULL DEFAULT 0,
    paper_trade_filled     INTEGER NOT NULL DEFAULT 0,
    entry_fill_price       TEXT,
    fill_timestamp         TEXT,
    unfilled_reason        TEXT,

    -- Exit
    exit_price             TEXT,
    exit_timestamp         TEXT,
    exit_reason            TEXT,
    mfe                    TEXT,
    mae                    TEXT,
    realised_r_multiple    TEXT,

    created_at             TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_gsl_timestamp ON gamma_signal_log (signal_timestamp);
CREATE INDEX IF NOT EXISTS idx_gsl_expiry    ON gamma_signal_log (expiry_date);
CREATE INDEX IF NOT EXISTS idx_gsl_triggered ON gamma_signal_log (signal_triggered);
CREATE INDEX IF NOT EXISTS idx_gsl_watchlist ON gamma_signal_log (watchlist_hit, signal_triggered);
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
            decimal.Decimal(row["nifty_futures"]) if row["nifty_futures"] is not None else None
        ),
        india_vix=(decimal.Decimal(row["india_vix"]) if row["india_vix"] is not None else None),
        delta_val=(decimal.Decimal(row["delta_val"]) if row["delta_val"] is not None else None),
        gamma_val=(decimal.Decimal(row["gamma_val"]) if row["gamma_val"] is not None else None),
        vega_val=(decimal.Decimal(row["vega_val"]) if row["vega_val"] is not None else None),
        theta_val=(decimal.Decimal(row["theta_val"]) if row["theta_val"] is not None else None),
        iv_val=(decimal.Decimal(row["iv_val"]) if row["iv_val"] is not None else None),
        gamma_gearing=(
            decimal.Decimal(row["gamma_gearing"]) if row["gamma_gearing"] is not None else None
        ),
        distance_pct=(
            decimal.Decimal(row["distance_pct"]) if row["distance_pct"] is not None else None
        ),
        best_bid=(decimal.Decimal(row["best_bid"]) if row["best_bid"] is not None else None),
        best_ask=(decimal.Decimal(row["best_ask"]) if row["best_ask"] is not None else None),
        bid_ask_spread=(
            decimal.Decimal(row["bid_ask_spread"]) if row["bid_ask_spread"] is not None else None
        ),
        oi=row["oi"],
        oi_change_1d=(
            decimal.Decimal(row["oi_change_1d"]) if row["oi_change_1d"] is not None else None
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
            decimal.Decimal(row["distance_pct"]) if row["distance_pct"] is not None else None
        ),
        gamma_gearing=(
            decimal.Decimal(row["gamma_gearing"]) if row["gamma_gearing"] is not None else None
        ),
        oi=row["oi"],
        oi_change_1d=(
            decimal.Decimal(row["oi_change_1d"]) if row["oi_change_1d"] is not None else None
        ),
        days_on_watchlist=row["days_on_watchlist"],
        elevated=bool(row["elevated"]),
        elevation_reason=row["elevation_reason"],
    )


def _opt_bool(v: bool | None) -> int | None:
    """Helper to convert optional bool to 1, 0, or None for tri-state DB columns."""
    if v is None:
        return None
    return 1 if v else 0


def _require_utc(dt: datetime.datetime, field_name: str) -> str:
    """Validate timezone-aware datetime, convert to UTC and return ISO string."""
    if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
        raise ValueError(f"{field_name} must be a timezone-aware UTC datetime, got naive: {dt}")
    # Normalize to UTC
    return dt.astimezone(datetime.timezone.utc).isoformat()


def _row_to_signal_log_entry(row: sqlite3.Row) -> GammaSignalLogEntry:
    def _parse_utc(val: str | None) -> datetime.datetime | None:
        if val is None:
            return None
        dt = datetime.datetime.fromisoformat(val)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=datetime.timezone.utc)
        return dt.astimezone(datetime.timezone.utc)

    sig_dt = _parse_utc(row["signal_timestamp"])
    assert sig_dt is not None, "signal_timestamp cannot be None"

    created_dt = _parse_utc(row["created_at"])
    assert created_dt is not None, "created_at cannot be None"

    return GammaSignalLogEntry(
        signal_id=row["signal_id"],
        signal_timestamp=sig_dt,
        expiry_date=datetime.date.fromisoformat(row["expiry_date"]),
        strike=row["strike"],
        option_type=row["option_type"],
        dte_calendar=row["dte_calendar"],
        dte_trading=row["dte_trading"],
        watchlist_hit=bool(row["watchlist_hit"]),
        watchlist_elevated=bool(row["watchlist_elevated"]),
        nifty_spot=decimal.Decimal(row["nifty_spot"]),
        nifty_futures_price=(
            decimal.Decimal(row["nifty_futures_price"])
            if row["nifty_futures_price"] is not None
            else None
        ),
        futures_basis=(
            decimal.Decimal(row["futures_basis"]) if row["futures_basis"] is not None else None
        ),
        underlying_return_1m=(
            decimal.Decimal(row["underlying_return_1m"])
            if row["underlying_return_1m"] is not None
            else None
        ),
        underlying_return_5m=(
            decimal.Decimal(row["underlying_return_5m"])
            if row["underlying_return_5m"] is not None
            else None
        ),
        underlying_return_15m=(
            decimal.Decimal(row["underlying_return_15m"])
            if row["underlying_return_15m"] is not None
            else None
        ),
        underlying_rvol_15m=(
            decimal.Decimal(row["underlying_rvol_15m"])
            if row["underlying_rvol_15m"] is not None
            else None
        ),
        distance_pct=decimal.Decimal(row["distance_pct"]),
        distance_sigma=(
            decimal.Decimal(row["distance_sigma"]) if row["distance_sigma"] is not None else None
        ),
        best_bid=(decimal.Decimal(row["best_bid"]) if row["best_bid"] is not None else None),
        best_ask=decimal.Decimal(row["best_ask"]),
        bid_ask_spread=(
            decimal.Decimal(row["bid_ask_spread"]) if row["bid_ask_spread"] is not None else None
        ),
        spread_pct_of_mid=(
            decimal.Decimal(row["spread_pct_of_mid"])
            if row["spread_pct_of_mid"] is not None
            else None
        ),
        bid_qty_l1=row["bid_qty_l1"],
        ask_qty_l1=row["ask_qty_l1"],
        total_bid_qty=row["total_bid_qty"],
        total_ask_qty=row["total_ask_qty"],
        delta_val=(decimal.Decimal(row["delta_val"]) if row["delta_val"] is not None else None),
        gamma_val=decimal.Decimal(row["gamma_val"]),
        vega_val=(decimal.Decimal(row["vega_val"]) if row["vega_val"] is not None else None),
        theta_val=(decimal.Decimal(row["theta_val"]) if row["theta_val"] is not None else None),
        iv_val=(decimal.Decimal(row["iv_val"]) if row["iv_val"] is not None else None),
        gamma_gearing=decimal.Decimal(row["gamma_gearing"]),
        speed_5m=(decimal.Decimal(row["speed_5m"]) if row["speed_5m"] is not None else None),
        speed_5m_unavailable=bool(row["speed_5m_unavailable"]),
        theoretical_price=(
            decimal.Decimal(row["theoretical_price"])
            if row["theoretical_price"] is not None
            else None
        ),
        model_edge=(decimal.Decimal(row["model_edge"]) if row["model_edge"] is not None else None),
        strike_iv_pctile_20d=(
            decimal.Decimal(row["strike_iv_pctile_20d"])
            if row["strike_iv_pctile_20d"] is not None
            else None
        ),
        gearing_threshold_used=(
            decimal.Decimal(row["gearing_threshold_used"])
            if row["gearing_threshold_used"] is not None
            else None
        ),
        volume_5m=row["volume_5m"],
        volume_zscore_5m=(
            decimal.Decimal(row["volume_zscore_5m"])
            if row["volume_zscore_5m"] is not None
            else None
        ),
        oi_now=row["oi_now"],
        oi_velocity_15m=(
            decimal.Decimal(row["oi_velocity_15m"]) if row["oi_velocity_15m"] is not None else None
        ),
        option_price_rising=(
            bool(row["option_price_rising"]) if row["option_price_rising"] is not None else None
        ),
        india_vix=(decimal.Decimal(row["india_vix"]) if row["india_vix"] is not None else None),
        india_vix_pctile_252d=(
            decimal.Decimal(row["india_vix_pctile_252d"])
            if row["india_vix_pctile_252d"] is not None
            else None
        ),
        event_flag=bool(row["event_flag"]),
        event_type=row["event_type"],
        f0_hard_pass=(bool(row["f0_hard_pass"]) if row["f0_hard_pass"] is not None else None),
        f0_fail_reason=row["f0_fail_reason"],
        f1_directional_pass=(
            bool(row["f1_directional_pass"]) if row["f1_directional_pass"] is not None else None
        ),
        f2_convexity_pass=(
            bool(row["f2_convexity_pass"]) if row["f2_convexity_pass"] is not None else None
        ),
        f3_quality_pass=(
            bool(row["f3_quality_pass"]) if row["f3_quality_pass"] is not None else None
        ),
        f3_quality_method=row["f3_quality_method"],
        f4_flow_pass=(bool(row["f4_flow_pass"]) if row["f4_flow_pass"] is not None else None),
        signal_triggered=bool(row["signal_triggered"]),
        paper_trade_attempted=bool(row["paper_trade_attempted"]),
        paper_trade_filled=bool(row["paper_trade_filled"]),
        entry_fill_price=(
            decimal.Decimal(row["entry_fill_price"])
            if row["entry_fill_price"] is not None
            else None
        ),
        fill_timestamp=_parse_utc(row["fill_timestamp"]),
        unfilled_reason=row["unfilled_reason"],
        exit_price=(decimal.Decimal(row["exit_price"]) if row["exit_price"] is not None else None),
        exit_timestamp=_parse_utc(row["exit_timestamp"]),
        exit_reason=row["exit_reason"],
        mfe=(decimal.Decimal(row["mfe"]) if row["mfe"] is not None else None),
        mae=(decimal.Decimal(row["mae"]) if row["mae"] is not None else None),
        realised_r_multiple=(
            decimal.Decimal(row["realised_r_multiple"])
            if row["realised_r_multiple"] is not None
            else None
        ),
        created_at=created_dt,
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

    def insert_chain_snapshot(self, conn: sqlite3.Connection, snap: GammaChainSnapshot) -> None:
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

    def get_prior_oi(
        self,
        conn: sqlite3.Connection,
        expiry_date: datetime.date,
        today: datetime.date,
    ) -> dict[tuple[int, str], int]:
        """Fetch the latest prior-day OI per (strike, option_type) in one query.

        Args:
            conn: An open SQLite connection.
            expiry_date: Expiry date to filter by.
            today: Date threshold (only snapshots strictly before this date).

        Returns:
            Mapping of (strike, option_type) to the OI of that option's most
            recent snapshot before today. Rows with NULL OI are omitted.
        """
        rows = conn.execute(
            """
            SELECT strike, option_type, oi FROM (
                SELECT strike, option_type, oi,
                       ROW_NUMBER() OVER (
                           PARTITION BY strike, option_type
                           ORDER BY snapshot_date DESC, snapshot_time DESC
                       ) AS rn
                FROM gamma_chain_snapshots
                WHERE expiry_date = ? AND snapshot_date < ? AND oi IS NOT NULL
            ) WHERE rn = 1
            """,
            (expiry_date.isoformat(), today.isoformat()),
        ).fetchall()
        return {(int(r["strike"]), r["option_type"]): int(r["oi"]) for r in rows}

    def get_prior_snapshots(
        self,
        conn: sqlite3.Connection,
        expiry_date: datetime.date,
        today: datetime.date,
        days: int,
    ) -> list[GammaChainSnapshot]:
        """Fetch the latest snapshot per (strike, option_type) for each prior date.

        Covers the last ``days`` distinct snapshot dates strictly before
        ``today`` for the expiry, in one query. Same-day re-runs collapse to
        the latest snapshot_time of that date.

        Args:
            conn: An open SQLite connection.
            expiry_date: Expiry date to filter by.
            today: Date threshold (only snapshot dates strictly before this).
            days: Number of distinct prior snapshot dates to include.

        Returns:
            Snapshots ordered by snapshot_date DESC, strike ASC, option_type ASC.
        """
        rows = conn.execute(
            """
            SELECT * FROM (
                SELECT *, ROW_NUMBER() OVER (
                           PARTITION BY snapshot_date, strike, option_type
                           ORDER BY snapshot_time DESC
                       ) AS rn
                FROM gamma_chain_snapshots
                WHERE expiry_date = ?
                  AND snapshot_date IN (
                    SELECT DISTINCT snapshot_date FROM gamma_chain_snapshots
                    WHERE expiry_date = ? AND snapshot_date < ?
                    ORDER BY snapshot_date DESC
                    LIMIT ?
                  )
            ) WHERE rn = 1
            ORDER BY snapshot_date DESC, strike ASC, option_type ASC
            """,
            (expiry_date.isoformat(), expiry_date.isoformat(), today.isoformat(), days),
        ).fetchall()
        return [_row_to_chain_snapshot(r) for r in rows]

    def upsert_watchlist(self, conn: sqlite3.Connection, entry: GammaWatchlistEntry) -> None:
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
                (entry.removed_date.isoformat() if entry.removed_date is not None else None),
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

    def get_all_active_watchlist(self, conn: sqlite3.Connection) -> list[GammaWatchlistEntry]:
        """Fetch every active watchlist entry regardless of expiry.

        Args:
            conn: An open SQLite connection.

        Returns:
            Active entries ordered by expiry_date, strike, option_type.
        """
        rows = conn.execute(
            """
            SELECT * FROM gamma_watchlist
            WHERE removed_date IS NULL
            ORDER BY expiry_date ASC, strike ASC, option_type ASC
            """
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
        before: datetime.date | None = None,
    ) -> list[decimal.Decimal]:
        """Fetch the trailing IV values across the last limit_days.

        Args:
            conn: An open SQLite connection.
            strike: Strike price.
            option_type: Option type ('CE' | 'PE').
            limit_days: Maximum number of historical trading days to look back.
            before: When given, only dates strictly before it are read and each
                date contributes ONE value (its latest snapshot_time), so
                ``len(result)`` is the number of distinct prior days (D5).
                When None, every snapshot of the last ``limit_days`` dates is
                returned.

        Returns:
            A list of Decimal objects representing the historical IV values,
            ordered chronologically (oldest to newest).
        """
        if before is not None:
            rows = conn.execute(
                """
                SELECT iv_val FROM (
                    SELECT snapshot_date, iv_val, ROW_NUMBER() OVER (
                               PARTITION BY snapshot_date
                               ORDER BY snapshot_time DESC, expiry_date ASC
                           ) AS rn
                    FROM gamma_chain_snapshots
                    WHERE strike = ? AND option_type = ?
                      AND iv_val IS NOT NULL AND snapshot_date < ?
                ) WHERE rn = 1
                ORDER BY snapshot_date DESC
                LIMIT ?
                """,
                (strike, option_type, before.isoformat(), limit_days),
            ).fetchall()
            return [decimal.Decimal(row["iv_val"]) for row in reversed(rows)]
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
        self,
        conn: sqlite3.Connection,
        target_dte: int,
        limit_days: int = 60,
        before: datetime.date | None = None,
    ) -> list[decimal.Decimal]:
        """Fetch all gamma_gearing values for target DTE over limit_days.

        Args:
            conn: An open SQLite connection.
            target_dte: The calendar DTE to match.
            limit_days: Number of distinct trailing snapshot dates
                to look back.
            before: When given, only snapshot dates strictly before it are
                read (so today's own rows never rank against themselves).

        Returns:
            A list of Decimal objects representing the gamma_gearing values,
            ordered by snapshot_date DESC.
        """
        cutoff = before.isoformat() if before is not None else "9999-12-31"
        rows = conn.execute(
            """
            SELECT gamma_gearing FROM gamma_chain_snapshots
            WHERE dte_calendar = ?
              AND gamma_gearing IS NOT NULL
              AND snapshot_date < ?
              AND snapshot_date IN (
                SELECT DISTINCT snapshot_date FROM gamma_chain_snapshots
                WHERE dte_calendar = ?
                  AND gamma_gearing IS NOT NULL
                  AND snapshot_date < ?
                ORDER BY snapshot_date DESC
                LIMIT ?
            )
            ORDER BY snapshot_date DESC, snapshot_time DESC
            """,
            (target_dte, cutoff, target_dte, cutoff, limit_days),
        ).fetchall()
        return [decimal.Decimal(row["gamma_gearing"]) for row in rows]

    def count_prior_gearing_days(
        self, conn: sqlite3.Connection, target_dte: int, before: datetime.date
    ) -> int:
        """Count distinct snapshot dates before ``before`` with gearing at a DTE.

        ``get_gearing_by_dte`` returns one value per strike, so its length
        counts strikes, not days; the D5 history gate needs days.

        Args:
            conn: An open SQLite connection.
            target_dte: The calendar DTE to match.
            before: Only snapshot dates strictly before this are counted.

        Returns:
            Number of distinct prior snapshot dates.
        """
        row = conn.execute(
            """
            SELECT COUNT(DISTINCT snapshot_date) AS n FROM gamma_chain_snapshots
            WHERE dte_calendar = ? AND gamma_gearing IS NOT NULL AND snapshot_date < ?
            """,
            (target_dte, before.isoformat()),
        ).fetchone()
        return int(row["n"])

    def update_percentiles(
        self,
        conn: sqlite3.Connection,
        *,
        snapshot_date: datetime.date,
        snapshot_time: str,
        expiry_date: datetime.date,
        strike: int,
        option_type: str,
        iv_pctile: decimal.Decimal | None = None,
        gearing_pctile: decimal.Decimal | None = None,
    ) -> bool:
        """Write the two percentile columns for one snapshot key.

        A ``None`` argument leaves that column untouched; no other column is
        modified.

        Args:
            conn: An open SQLite connection.
            snapshot_date: Snapshot date of the row.
            snapshot_time: Snapshot time (HH:MM) of the row.
            expiry_date: Expiry of the row.
            strike: Strike of the row.
            option_type: 'CE' | 'PE'.
            iv_pctile: New ``strike_iv_pctile_20d``, or None to keep.
            gearing_pctile: New ``gamma_gearing_pctile_dte``, or None to keep.

        Returns:
            True if a row matched the key, False for an unknown key (no-op).
        """
        cur = conn.execute(
            """
            UPDATE gamma_chain_snapshots
            SET strike_iv_pctile_20d = COALESCE(?, strike_iv_pctile_20d),
                gamma_gearing_pctile_dte = COALESCE(?, gamma_gearing_pctile_dte)
            WHERE snapshot_date = ? AND snapshot_time = ? AND expiry_date = ?
              AND strike = ? AND option_type = ?
            """,
            (
                _dec(iv_pctile),
                _dec(gearing_pctile),
                snapshot_date.isoformat(),
                snapshot_time,
                expiry_date.isoformat(),
                strike,
                option_type,
            ),
        )
        return cur.rowcount > 0

    def insert_signal_log(self, conn: sqlite3.Connection, entry: GammaSignalLogEntry) -> None:
        """Insert a gamma signal log entry.

        Uses plain INSERT (no OR REPLACE) so duplicates raise sqlite3.IntegrityError.
        Does not commit, allowing callers to participate in outer transactions.
        Requires timezone-aware UTC datetime fields.

        Args:
            conn: An open SQLite connection.
            entry: The GammaSignalLogEntry to insert.

        Raises:
            ValueError: If signal_timestamp, fill_timestamp, exit_timestamp,
                or created_at is naive.
            sqlite3.IntegrityError: If signal_id already exists.
        """
        sig_ts_str = _require_utc(entry.signal_timestamp, "signal_timestamp")
        created_at_str = _require_utc(entry.created_at, "created_at")
        fill_ts_str = (
            _require_utc(entry.fill_timestamp, "fill_timestamp")
            if entry.fill_timestamp is not None
            else None
        )
        exit_ts_str = (
            _require_utc(entry.exit_timestamp, "exit_timestamp")
            if entry.exit_timestamp is not None
            else None
        )

        conn.execute(
            """
            INSERT INTO gamma_signal_log (
                signal_id, signal_timestamp, expiry_date, strike, option_type,
                dte_calendar, dte_trading, watchlist_hit, watchlist_elevated,
                nifty_spot, nifty_futures_price, futures_basis,
                underlying_return_1m, underlying_return_5m, underlying_return_15m,
                underlying_rvol_15m, distance_pct, distance_sigma,
                best_bid, best_ask, bid_ask_spread, spread_pct_of_mid,
                bid_qty_l1, ask_qty_l1, total_bid_qty, total_ask_qty,
                delta_val, gamma_val, vega_val, theta_val, iv_val,
                gamma_gearing, speed_5m, speed_5m_unavailable,
                theoretical_price, model_edge, strike_iv_pctile_20d,
                gearing_threshold_used, volume_5m, volume_zscore_5m,
                oi_now, oi_velocity_15m, option_price_rising,
                india_vix, india_vix_pctile_252d, event_flag, event_type,
                f0_hard_pass, f0_fail_reason, f1_directional_pass,
                f2_convexity_pass, f3_quality_pass, f3_quality_method,
                f4_flow_pass, signal_triggered, paper_trade_attempted,
                paper_trade_filled, entry_fill_price, fill_timestamp,
                unfilled_reason, exit_price, exit_timestamp, exit_reason,
                mfe, mae, realised_r_multiple, created_at
            ) VALUES (
                ?, ?, ?, ?, ?,
                ?, ?, ?, ?,
                ?, ?, ?,
                ?, ?, ?,
                ?, ?, ?,
                ?, ?, ?, ?,
                ?, ?, ?, ?,
                ?, ?, ?, ?, ?,
                ?, ?, ?,
                ?, ?, ?,
                ?, ?, ?,
                ?, ?, ?,
                ?, ?, ?, ?,
                ?, ?, ?,
                ?, ?, ?,
                ?, ?, ?,
                ?, ?, ?,
                ?, ?, ?, ?,
                ?, ?, ?, ?
            )
            """,
            (
                entry.signal_id,
                sig_ts_str,
                entry.expiry_date.isoformat(),
                entry.strike,
                entry.option_type,
                entry.dte_calendar,
                entry.dte_trading,
                1 if entry.watchlist_hit else 0,
                1 if entry.watchlist_elevated else 0,
                str(entry.nifty_spot),
                _dec(entry.nifty_futures_price),
                _dec(entry.futures_basis),
                _dec(entry.underlying_return_1m),
                _dec(entry.underlying_return_5m),
                _dec(entry.underlying_return_15m),
                _dec(entry.underlying_rvol_15m),
                str(entry.distance_pct),
                _dec(entry.distance_sigma),
                _dec(entry.best_bid),
                str(entry.best_ask),
                _dec(entry.bid_ask_spread),
                _dec(entry.spread_pct_of_mid),
                entry.bid_qty_l1,
                entry.ask_qty_l1,
                entry.total_bid_qty,
                entry.total_ask_qty,
                _dec(entry.delta_val),
                str(entry.gamma_val),
                _dec(entry.vega_val),
                _dec(entry.theta_val),
                _dec(entry.iv_val),
                str(entry.gamma_gearing),
                _dec(entry.speed_5m),
                1 if entry.speed_5m_unavailable else 0,
                _dec(entry.theoretical_price),
                _dec(entry.model_edge),
                _dec(entry.strike_iv_pctile_20d),
                _dec(entry.gearing_threshold_used),
                entry.volume_5m,
                _dec(entry.volume_zscore_5m),
                entry.oi_now,
                _dec(entry.oi_velocity_15m),
                _opt_bool(entry.option_price_rising),
                _dec(entry.india_vix),
                _dec(entry.india_vix_pctile_252d),
                1 if entry.event_flag else 0,
                entry.event_type,
                _opt_bool(entry.f0_hard_pass),
                entry.f0_fail_reason,
                _opt_bool(entry.f1_directional_pass),
                _opt_bool(entry.f2_convexity_pass),
                _opt_bool(entry.f3_quality_pass),
                entry.f3_quality_method,
                _opt_bool(entry.f4_flow_pass),
                1 if entry.signal_triggered else 0,
                1 if entry.paper_trade_attempted else 0,
                1 if entry.paper_trade_filled else 0,
                _dec(entry.entry_fill_price),
                fill_ts_str,
                entry.unfilled_reason,
                _dec(entry.exit_price),
                exit_ts_str,
                entry.exit_reason,
                _dec(entry.mfe),
                _dec(entry.mae),
                _dec(entry.realised_r_multiple),
                created_at_str,
            ),
        )

    def update_signal_exit(
        self,
        conn: sqlite3.Connection,
        signal_id: str,
        *,
        exit_price: decimal.Decimal,
        exit_timestamp: datetime.datetime,
        exit_reason: str,
        mfe: decimal.Decimal | None = None,
        mae: decimal.Decimal | None = None,
        realised_r_multiple: decimal.Decimal | None = None,
    ) -> bool:
        """Update exit fields on an open signal log entry.

        Updates only unexited rows (``exit_timestamp IS NULL``).
        Returns False if the signal_id was not found or was already exited.

        Args:
            conn: An open SQLite connection.
            signal_id: The signal_id to update.
            exit_price: Realised exit price.
            exit_timestamp: Timezone-aware UTC timestamp of exit.
            exit_reason: Reason for exit (e.g. 'E1', 'E2', 'E3').
            mfe: Maximum favorable excursion (optional).
            mae: Maximum adverse excursion (optional).
            realised_r_multiple: Realised R-multiple (optional).

        Returns:
            True if an unexited row was updated, False otherwise.

        Raises:
            ValueError: If exit_timestamp is naive.
        """
        exit_ts_str = _require_utc(exit_timestamp, "exit_timestamp")
        cur = conn.execute(
            """
            UPDATE gamma_signal_log
            SET exit_price = ?,
                exit_timestamp = ?,
                exit_reason = ?,
                mfe = ?,
                mae = ?,
                realised_r_multiple = ?
            WHERE signal_id = ? AND exit_timestamp IS NULL
            """,
            (
                str(exit_price),
                exit_ts_str,
                exit_reason,
                _dec(mfe),
                _dec(mae),
                _dec(realised_r_multiple),
                signal_id,
            ),
        )
        return cur.rowcount > 0

    def get_open_signal_positions(
        self,
        conn: sqlite3.Connection,
        option_type: typing.Literal["CE", "PE"] | None = None,
    ) -> list[GammaSignalLogEntry]:
        """Fetch open signal positions.

        Defined as ``paper_trade_filled = 1 AND exit_timestamp IS NULL``.

        Args:
            conn: An open SQLite connection with sqlite3.Row factory.
            option_type: Optional filter ('CE' or 'PE').

        Returns:
            List of open GammaSignalLogEntry rows.
        """
        if option_type is not None:
            cur = conn.execute(
                """
                SELECT
                    signal_id, signal_timestamp, expiry_date, strike, option_type,
                    dte_calendar, dte_trading, watchlist_hit, watchlist_elevated,
                    nifty_spot, nifty_futures_price, futures_basis,
                    underlying_return_1m, underlying_return_5m, underlying_return_15m,
                    underlying_rvol_15m, distance_pct, distance_sigma,
                    best_bid, best_ask, bid_ask_spread, spread_pct_of_mid,
                    bid_qty_l1, ask_qty_l1, total_bid_qty, total_ask_qty,
                    delta_val, gamma_val, vega_val, theta_val, iv_val,
                    gamma_gearing, speed_5m, speed_5m_unavailable,
                    theoretical_price, model_edge, strike_iv_pctile_20d,
                    gearing_threshold_used, volume_5m, volume_zscore_5m,
                    oi_now, oi_velocity_15m, option_price_rising,
                    india_vix, india_vix_pctile_252d, event_flag, event_type,
                    f0_hard_pass, f0_fail_reason, f1_directional_pass,
                    f2_convexity_pass, f3_quality_pass, f3_quality_method,
                    f4_flow_pass, signal_triggered, paper_trade_attempted,
                    paper_trade_filled, entry_fill_price, fill_timestamp,
                    unfilled_reason, exit_price, exit_timestamp, exit_reason,
                    mfe, mae, realised_r_multiple, created_at
                FROM gamma_signal_log
                WHERE paper_trade_filled = 1 AND exit_timestamp IS NULL AND option_type = ?
                ORDER BY signal_timestamp ASC
                """,
                (option_type,),
            )
        else:
            cur = conn.execute(
                """
                SELECT
                    signal_id, signal_timestamp, expiry_date, strike, option_type,
                    dte_calendar, dte_trading, watchlist_hit, watchlist_elevated,
                    nifty_spot, nifty_futures_price, futures_basis,
                    underlying_return_1m, underlying_return_5m, underlying_return_15m,
                    underlying_rvol_15m, distance_pct, distance_sigma,
                    best_bid, best_ask, bid_ask_spread, spread_pct_of_mid,
                    bid_qty_l1, ask_qty_l1, total_bid_qty, total_ask_qty,
                    delta_val, gamma_val, vega_val, theta_val, iv_val,
                    gamma_gearing, speed_5m, speed_5m_unavailable,
                    theoretical_price, model_edge, strike_iv_pctile_20d,
                    gearing_threshold_used, volume_5m, volume_zscore_5m,
                    oi_now, oi_velocity_15m, option_price_rising,
                    india_vix, india_vix_pctile_252d, event_flag, event_type,
                    f0_hard_pass, f0_fail_reason, f1_directional_pass,
                    f2_convexity_pass, f3_quality_pass, f3_quality_method,
                    f4_flow_pass, signal_triggered, paper_trade_attempted,
                    paper_trade_filled, entry_fill_price, fill_timestamp,
                    unfilled_reason, exit_price, exit_timestamp, exit_reason,
                    mfe, mae, realised_r_multiple, created_at
                FROM gamma_signal_log
                WHERE paper_trade_filled = 1 AND exit_timestamp IS NULL
                ORDER BY signal_timestamp ASC
                """
            )
        return [_row_to_signal_log_entry(row) for row in cur.fetchall()]

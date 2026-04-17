"""SQLite store for Nuvama bond portfolio snapshots and positions.

Two tables, both in the shared portfolio.sqlite:

  nuvama_positions(isin PK, avg_price TEXT, qty INT, label TEXT)
    — Static cost-basis table seeded once from scripts/seed_nuvama_positions.py.
      Never updated by the snapshot run; only by explicit seed/update commands.

  nuvama_holdings_snapshots(isin, snapshot_date, qty, ltp, current_value)
    — Daily EOD snapshot per instrument. UNIQUE(isin, snapshot_date) with
      upsert semantics — re-runs on the same day are idempotent.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from decimal import Decimal

from src.db import connect

logger = logging.getLogger(__name__)

_CREATE_POSITIONS = """
CREATE TABLE IF NOT EXISTS nuvama_positions (
    isin        TEXT PRIMARY KEY,
    avg_price   TEXT NOT NULL,
    qty         INTEGER NOT NULL,
    label       TEXT NOT NULL DEFAULT ''
)
"""

_CREATE_SNAPSHOTS = """
CREATE TABLE IF NOT EXISTS nuvama_holdings_snapshots (
    isin            TEXT NOT NULL,
    snapshot_date   TEXT NOT NULL,
    qty             INTEGER NOT NULL,
    ltp             TEXT NOT NULL,
    current_value   TEXT NOT NULL,
    PRIMARY KEY (isin, snapshot_date)
)
"""

_CREATE_OPTIONS_SNAPSHOTS = """
CREATE TABLE IF NOT EXISTS nuvama_options_snapshots (
    snapshot_date       TEXT NOT NULL,
    trade_symbol        TEXT NOT NULL,
    instrument_name     TEXT NOT NULL,
    net_qty             INTEGER NOT NULL,
    avg_price           TEXT NOT NULL,
    ltp                 TEXT NOT NULL,
    unrealized_pnl      TEXT NOT NULL,
    realized_pnl_today  TEXT NOT NULL,
    PRIMARY KEY (trade_symbol, snapshot_date)
)
"""

_CREATE_INTRADAY_SNAPSHOTS = """
CREATE TABLE IF NOT EXISTS nuvama_intraday_snapshots (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp           TIMESTAMP NOT NULL,
    nifty_spot          DECIMAL,
    trade_symbol        TEXT NOT NULL,
    net_qty             INTEGER NOT NULL,
    ltp                 DECIMAL NOT NULL,
    unrealized_pnl      DECIMAL NOT NULL,
    realized_pnl_today  DECIMAL NOT NULL
)
"""


class NuvamaStore:
    """Read/write access to Nuvama tables in portfolio.sqlite."""

    def __init__(self, db_path: str = "data/portfolio/portfolio.sqlite") -> None:
        self._db_path = db_path
        self._ensure_tables()

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def _ensure_tables(self) -> None:
        """Create tables if they do not exist."""
        with connect(self._db_path) as conn:
            conn.execute(_CREATE_POSITIONS)
            conn.execute(_CREATE_SNAPSHOTS)
            conn.execute(_CREATE_OPTIONS_SNAPSHOTS)
            conn.execute(_CREATE_INTRADAY_SNAPSHOTS)

    # ------------------------------------------------------------------
    # Positions (cost basis)
    # ------------------------------------------------------------------

    def seed_positions(
        self, positions: list[dict], *, overwrite: bool = False
    ) -> int:
        """Insert cost-basis positions.  Idempotent by default.

        Args:
            positions: List of dicts with keys: isin, avg_price, qty, label.
            overwrite: When True uses INSERT OR REPLACE; otherwise
                INSERT OR IGNORE (default — safe for repeated seeding).

        Returns:
            Number of rows inserted (0 if all already existed and overwrite=False).
        """
        verb = "INSERT OR REPLACE" if overwrite else "INSERT OR IGNORE"
        sql = f"{verb} INTO nuvama_positions (isin, avg_price, qty, label) VALUES (?, ?, ?, ?)"
        inserted = 0
        with connect(self._db_path) as conn:
            for pos in positions:
                cur = conn.execute(
                    sql,
                    (
                        pos["isin"],
                        str(pos["avg_price"]),
                        int(pos["qty"]),
                        pos.get("label", ""),
                    ),
                )
                inserted += cur.rowcount
        return inserted

    def get_positions(self) -> dict[str, Decimal]:
        """Return all seeded positions as ISIN → avg_price mapping.

        Returns:
            Dict mapping ISIN to Decimal avg_price. Empty if no positions seeded.
        """
        with connect(self._db_path) as conn:
            rows = conn.execute(
                "SELECT isin, avg_price FROM nuvama_positions"
            ).fetchall()
        return {row["isin"]: Decimal(row["avg_price"]) for row in rows}

    def get_position(self, isin: str) -> dict | None:
        """Return a single position record or None if not found.

        Args:
            isin: ISIN to look up.

        Returns:
            Dict with keys isin, avg_price (Decimal), qty, label — or None.
        """
        with connect(self._db_path) as conn:
            row = conn.execute(
                "SELECT isin, avg_price, qty, label FROM nuvama_positions WHERE isin = ?",
                (isin,),
            ).fetchone()
        if row is None:
            return None
        return {
            "isin": row["isin"],
            "avg_price": Decimal(row["avg_price"]),
            "qty": row["qty"],
            "label": row["label"],
        }

    # ------------------------------------------------------------------
    # Snapshots
    # ------------------------------------------------------------------

    def record_snapshot(
        self,
        isin: str,
        snapshot_date: date,
        qty: int,
        ltp: Decimal,
        current_value: Decimal,
    ) -> None:
        """Upsert one holding snapshot row.

        Last-write-wins on (isin, snapshot_date) — re-running the daily
        snapshot on the same day is safe.

        Args:
            isin: ISIN of the instrument.
            snapshot_date: Date of the snapshot.
            qty: Quantity held.
            ltp: Last traded price.
            current_value: ltp × qty (Decimal, stored as TEXT).
        """
        with connect(self._db_path) as conn:
            conn.execute(
                """
                INSERT INTO nuvama_holdings_snapshots
                    (isin, snapshot_date, qty, ltp, current_value)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(isin, snapshot_date) DO UPDATE SET
                    qty           = excluded.qty,
                    ltp           = excluded.ltp,
                    current_value = excluded.current_value
                """,
                (
                    isin,
                    snapshot_date.isoformat(),
                    qty,
                    str(ltp),
                    str(current_value),
                ),
            )

    def record_all_snapshots(
        self,
        holdings: list,
        snapshot_date: date,
    ) -> None:
        """Upsert snapshot rows for a list of NuvamaBondHolding objects.

        Convenience wrapper used by daily_snapshot.py after fetch.

        Args:
            holdings: List of NuvamaBondHolding instances.
            snapshot_date: Date to record against.
        """
        for h in holdings:
            self.record_snapshot(
                isin=h.isin,
                snapshot_date=snapshot_date,
                qty=h.qty,
                ltp=h.ltp,
                current_value=h.current_value,
            )

    def get_snapshot_for_date(self, snapshot_date: date) -> dict[str, Decimal]:
        """Return all snapshot rows for a given date as ISIN → current_value.

        Args:
            snapshot_date: Date to query.

        Returns:
            Dict mapping ISIN to current_value. Empty dict if no rows.
        """
        with connect(self._db_path) as conn:
            rows = conn.execute(
                "SELECT isin, current_value FROM nuvama_holdings_snapshots WHERE snapshot_date = ?",
                (snapshot_date.isoformat(),),
            ).fetchall()
        return {row["isin"]: Decimal(row["current_value"]) for row in rows}

    def get_prev_total_value(self, before_date: date) -> Decimal | None:
        """Return the sum of current_value for the most recent snapshot before a date.

        Calendar-agnostic: uses MAX(snapshot_date) < before_date, same
        pattern as DhanStore.get_prev_snapshot().

        Args:
            before_date: The reference date (exclusive upper bound).

        Returns:
            Total bond portfolio value on the previous snapshot date,
            or None if no prior snapshot exists.
        """
        # Step 1: find the most recent snapshot date before before_date
        with connect(self._db_path) as conn:
            date_row = conn.execute(
                "SELECT MAX(snapshot_date) AS d FROM nuvama_holdings_snapshots WHERE snapshot_date < ?",
                (before_date.isoformat(),),
            ).fetchone()
        if date_row is None or date_row["d"] is None:
            return None

        # Step 2: sum current_value in Python with Decimal (avoids CAST rounding)
        with connect(self._db_path) as conn:
            rows = conn.execute(
                "SELECT current_value FROM nuvama_holdings_snapshots WHERE snapshot_date = ?",
                (date_row["d"],),
            ).fetchall()
        if not rows:
            return None
        return sum((Decimal(r["current_value"]) for r in rows), Decimal("0"))

    # ------------------------------------------------------------------
    # Options Snapshots
    # ------------------------------------------------------------------

    def record_options_snapshot(
        self,
        snapshot_date: date,
        trade_symbol: str,
        instrument_name: str,
        net_qty: int,
        avg_price: Decimal,
        ltp: Decimal,
        unrealized_pnl: Decimal,
        realized_pnl_today: Decimal,
    ) -> None:
        """Upsert one options holding snapshot row."""
        with connect(self._db_path) as conn:
            conn.execute(
                """
                INSERT INTO nuvama_options_snapshots
                    (snapshot_date, trade_symbol, instrument_name, net_qty, avg_price, ltp, unrealized_pnl, realized_pnl_today)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(trade_symbol, snapshot_date) DO UPDATE SET
                    instrument_name    = excluded.instrument_name,
                    net_qty            = excluded.net_qty,
                    avg_price          = excluded.avg_price,
                    ltp                = excluded.ltp,
                    unrealized_pnl     = excluded.unrealized_pnl,
                    realized_pnl_today = excluded.realized_pnl_today
                """,
                (
                    snapshot_date.isoformat(),
                    trade_symbol,
                    instrument_name,
                    net_qty,
                    str(avg_price),
                    str(ltp),
                    str(unrealized_pnl),
                    str(realized_pnl_today),
                ),
            )

    def record_all_options_snapshots(
        self,
        holdings: list,
        snapshot_date: date,
    ) -> None:
        """Upsert snapshot rows for a list of NuvamaOptionPosition objects."""
        for h in holdings:
            self.record_options_snapshot(
                snapshot_date=snapshot_date,
                trade_symbol=h.trade_symbol,
                instrument_name=h.instrument_name,
                net_qty=h.net_qty,
                avg_price=h.avg_price,
                ltp=h.ltp,
                unrealized_pnl=h.unrealized_pnl,
                realized_pnl_today=h.realized_pnl_today,
            )

    def get_cumulative_realized_pnl(self) -> dict[str, Decimal]:
        """Return cumulative realized PnL grouped by trade_symbol across all snapshots."""
        with connect(self._db_path) as conn:
            rows = conn.execute(
                "SELECT trade_symbol, realized_pnl_today FROM nuvama_options_snapshots"
            ).fetchall()
        
        result: dict[str, Decimal] = {}
        for row in rows:
            sym = row["trade_symbol"]
            val = Decimal(row["realized_pnl_today"])
            result[sym] = result.get(sym, Decimal("0")) + val
        return result

    def get_options_snapshot_for_date(self, snapshot_date: date) -> list[dict]:
        """Return all options snapshot rows for a given date."""
        with connect(self._db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM nuvama_options_snapshots WHERE snapshot_date = ?",
                (snapshot_date.isoformat(),),
            ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Intraday Tracker
    # ------------------------------------------------------------------

    def purge_old_intraday(self, days: int = 30) -> None:
        """Delete intraday snapshots older than the retention limit."""
        cutoff = datetime.now() - timedelta(days=days)
        with connect(self._db_path) as conn:
            conn.execute(
                "DELETE FROM nuvama_intraday_snapshots WHERE timestamp < ?",
                (cutoff.isoformat(),)
            )

    def record_intraday_positions(
        self,
        timestamp: datetime,
        nifty_spot: float,
        positions: list,
    ) -> None:
        """Insert the raw 5-minute leg states for later investigation."""
        with connect(self._db_path) as conn:
            conn.executemany(
                """
                INSERT INTO nuvama_intraday_snapshots (
                    timestamp, nifty_spot, trade_symbol, net_qty, ltp,
                    unrealized_pnl, realized_pnl_today
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        timestamp.isoformat(),
                        nifty_spot,
                        pos.trade_symbol,
                        pos.net_qty,
                        str(pos.ltp),
                        str(pos.unrealized_pnl),
                        str(pos.realized_pnl_today),
                    )
                    for pos in positions
                ],
            )
        self.purge_old_intraday(days=30)

    def get_intraday_extremes(self, snap_date: date) -> tuple[Decimal | None, Decimal | None, float | None, float | None]:
        """Aggregate 5-minute states to find the day's total portfolio high and low."""
        with connect(self._db_path) as conn:
            rows = conn.execute(
                """
                SELECT timestamp, unrealized_pnl, realized_pnl_today, nifty_spot
                FROM nuvama_intraday_snapshots
                WHERE date(timestamp) = ?
                """,
                (snap_date.isoformat(),)
            ).fetchall()
            
        if not rows:
            return None, None, None, None
            
        pnl_by_ts: dict[str, Decimal] = {}
        nifty_spots: list[float] = []
        
        for row in rows:
            ts = row["timestamp"]
            urlz = Decimal(str(row["unrealized_pnl"]))
            rlz = Decimal(str(row["realized_pnl_today"]))
            nifty = row["nifty_spot"]
            
            pnl_by_ts[ts] = pnl_by_ts.get(ts, Decimal("0")) + urlz + rlz
            if nifty is not None:
                nifty_spots.append(float(str(nifty)))
                
        pnls = list(pnl_by_ts.values())
        max_pnl = max(pnls) if pnls else None
        min_pnl = min(pnls) if pnls else None
        nifty_high = max(nifty_spots) if nifty_spots else None
        nifty_low = min(nifty_spots) if nifty_spots else None
        
        return max_pnl, min_pnl, nifty_high, nifty_low

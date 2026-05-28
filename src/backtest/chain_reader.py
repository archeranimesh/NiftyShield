import glob
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
import pandas as pd
import duckdb

class ChainReader:
    """Reader for querying OptionChain snapshots stored in Parquet format via DuckDB."""

    EMPTY_COLS = [
        "snapshot_ts", "underlying", "expiry_date", "strike", "option_type",
        "spot", "ltp", "bid", "ask", "oi", "volume", "iv", "delta", "gamma",
        "theta", "vega"
    ]

    def __init__(self, eod_dir: str, intraday_dir: str | None = None) -> None:
        """Store paths. DuckDB connection opened lazily on first query."""
        self.eod_dir = Path(eod_dir)
        self.intraday_dir = Path(intraday_dir) if intraday_dir else None
        self._conn = None

    @property
    def conn(self) -> duckdb.DuckDBPyConnection:
        """Lazy-loaded in-memory DuckDB connection."""
        if self._conn is None:
            self._conn = duckdb.connect(database=":memory:")
        return self._conn

    def close(self) -> None:
        """Explicitly close the in-memory DuckDB connection if active."""
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None

    def get_eod_snapshots(
        self,
        start_date: date,
        end_date: date,
        underlying: str = "NIFTY_50",
        expiry_date: date | None = None,
        option_type: str | None = None,
        delta_min: Decimal | None = None,
        delta_max: Decimal | None = None,
    ) -> pd.DataFrame:
        """Scan EOD Parquet files for the given date range and optional filters.

        Globs: {eod_dir}/{year}/{month}/upstox_*.parquet.
        Returns empty DataFrame if no files exist.

        Note:
            DuckDB materializes PyArrow Decimal128 columns as float64 inside the returned
            pandas DataFrame (e.g., spot, strike, ltp, bid, ask, iv, delta, gamma, vega, theta).
            Callers who require precise Decimal representations should cast floats explicitly.
        """
        if not self.eod_dir.exists():
            return pd.DataFrame(columns=self.EMPTY_COLS)

        glob_pattern = str(self.eod_dir / "*" / "*" / "upstox_*.parquet")
        files = glob.glob(glob_pattern)
        if not files:
            return pd.DataFrame(columns=self.EMPTY_COLS)

        # Note: Using an f-string for the glob path is required here because DuckDB's
        # read_parquet() function is a table function and does not accept parameter markers (?)
        # for its file path parameter.
        query = f"""
            SELECT * FROM read_parquet('{glob_pattern}')
            WHERE CAST(snapshot_ts AS DATE) >= ?
              AND CAST(snapshot_ts AS DATE) <= ?
              AND underlying = ?
        """
        params = [start_date, end_date, underlying]

        if expiry_date is not None:
            query += " AND expiry_date = ?"
            params.append(expiry_date)

        if option_type is not None:
            query += " AND option_type = ?"
            params.append(option_type)

        if delta_min is not None:
            query += " AND delta >= ?"
            params.append(delta_min)

        if delta_max is not None:
            query += " AND delta <= ?"
            params.append(delta_max)

        df = self.conn.execute(query, params).df()
        if df.empty:
            return pd.DataFrame(columns=self.EMPTY_COLS)
        return df

    def get_intraday_snapshots(
        self,
        trade_date: date,
        underlying: str = "NIFTY_50",
        expiry_date: date | None = None,
        strike: Decimal | None = None,
        option_type: str | None = None,
    ) -> pd.DataFrame:
        """Scan intraday Parquet files for a single trading day.

        Globs: {intraday_dir}/{year}/{month}/{day}/upstox_*.parquet.
        Returns empty DataFrame if no files exist or intraday_dir is None.

        Note:
            DuckDB materializes PyArrow Decimal128 columns as float64 inside the returned
            pandas DataFrame (e.g., spot, strike, ltp, bid, ask, iv, delta, gamma, vega, theta).
            Callers who require precise Decimal representations should cast floats explicitly.
        """
        if self.intraday_dir is None or not self.intraday_dir.exists():
            return pd.DataFrame(columns=self.EMPTY_COLS)

        year = f"{trade_date.year:04d}"
        month = f"{trade_date.month:02d}"
        day_str = f"{trade_date.day:02d}"
        day_dir = self.intraday_dir / year / month / day_str

        if not day_dir.exists():
            return pd.DataFrame(columns=self.EMPTY_COLS)

        glob_pattern = str(day_dir / "upstox_*.parquet")
        files = glob.glob(glob_pattern)
        if not files:
            return pd.DataFrame(columns=self.EMPTY_COLS)

        # Note: Using an f-string for the glob path is required here because DuckDB's
        # read_parquet() function is a table function and does not accept parameter markers (?)
        # for its file path parameter.
        query = f"""
            SELECT * FROM read_parquet('{glob_pattern}')
            WHERE underlying = ?
        """
        params = [underlying]

        if expiry_date is not None:
            query += " AND expiry_date = ?"
            params.append(expiry_date)

        if strike is not None:
            query += " AND strike = ?"
            params.append(strike)

        if option_type is not None:
            query += " AND option_type = ?"
            params.append(option_type)

        df = self.conn.execute(query, params).df()
        if df.empty:
            return pd.DataFrame(columns=self.EMPTY_COLS)
        return df

    def get_strike_delta_series(
        self,
        start_date: date,
        end_date: date,
        strike: Decimal,
        option_type: str,
        underlying: str = "NIFTY_50",
        expiry_date: date | None = None,
    ) -> pd.DataFrame:
        """Return daily delta time series for a specific strike.

        Convenience wrapper over get_eod_snapshots. Columns: snapshot_ts, delta, iv, ltp.

        Note:
            DuckDB materializes PyArrow Decimal128 columns as float64 inside the returned
            pandas DataFrame (e.g., ltp, iv, delta).
            Callers who require precise Decimal representations should cast floats explicitly.
        """
        cols = ["snapshot_ts", "delta", "iv", "ltp"]
        if not self.eod_dir.exists():
            return pd.DataFrame(columns=cols)

        glob_pattern = str(self.eod_dir / "*" / "*" / "upstox_*.parquet")
        files = glob.glob(glob_pattern)
        if not files:
            return pd.DataFrame(columns=cols)

        # Note: Using an f-string for the glob path is required here because DuckDB's
        # read_parquet() function is a table function and does not accept parameter markers (?)
        # for its file path parameter.
        query = f"""
            SELECT snapshot_ts, delta, iv, ltp
            FROM read_parquet('{glob_pattern}')
            WHERE CAST(snapshot_ts AS DATE) >= ?
              AND CAST(snapshot_ts AS DATE) <= ?
              AND underlying = ?
              AND strike = ?
              AND option_type = ?
        """
        params = [start_date, end_date, underlying, strike, option_type]

        if expiry_date is not None:
            query += " AND expiry_date = ?"
            params.append(expiry_date)

        query += " ORDER BY snapshot_ts ASC"

        df = self.conn.execute(query, params).df()
        if df.empty:
            return pd.DataFrame(columns=cols)
        return df

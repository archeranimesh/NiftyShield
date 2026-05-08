import datetime
from typing import Optional

from src.db import connect


class IntradayMarketStore:
    """Broker-agnostic store for intraday market context snapshots.

    Owns the ``intraday_market_snapshots`` table — one row per tracker tick
    recording Nifty spot and India VIX.  Shared by both the Nuvama and Dhan
    intraday trackers via the combined orchestrator.
    """

    def __init__(self, db_path: str = "data/portfolio/portfolio.sqlite") -> None:
        """Initialise the store and create the table if it does not exist.

        Args:
            db_path: Path to the shared SQLite database.
        """
        self._db_path = db_path
        self._ensure_tables()

    def _ensure_tables(self) -> None:
        with connect(self._db_path) as db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS intraday_market_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TIMESTAMP NOT NULL,
                    nifty_spot REAL,
                    india_vix REAL
                )
            """)

    def record_market_snapshot(
        self,
        timestamp: datetime.datetime,
        nifty_spot: float,
        india_vix: float,
    ) -> None:
        """Insert one market-context row.

        Args:
            timestamp: UTC datetime of the snapshot tick.
            nifty_spot: Nifty 50 index level (0.0 if fetch failed).
            india_vix: India VIX level (0.0 if fetch failed).
        """
        with connect(self._db_path) as db:
            db.execute(
                """
                INSERT INTO intraday_market_snapshots (timestamp, nifty_spot, india_vix)
                VALUES (?, ?, ?)
                """,
                (timestamp, nifty_spot, india_vix),
            )

    def purge_old(self, days: int = 30) -> int:
        """Delete snapshots older than ``days`` days.

        Args:
            days: Retention window in calendar days (default 30).

        Returns:
            Number of rows deleted.
        """
        cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days)
        with connect(self._db_path) as db:
            cursor = db.execute(
                "DELETE FROM intraday_market_snapshots WHERE timestamp < ?",
                (cutoff,),
            )
            return cursor.rowcount

    def get_latest(self) -> Optional[tuple[float, float]]:
        """Return the most recent (nifty_spot, india_vix) pair.

        Returns:
            Tuple of (nifty_spot, india_vix), or None if the table is empty.
        """
        with connect(self._db_path) as db:
            cursor = db.execute(
                "SELECT nifty_spot, india_vix FROM intraday_market_snapshots"
                " ORDER BY timestamp DESC LIMIT 1"
            )
            row = cursor.fetchone()
            if row:
                return (row["nifty_spot"], row["india_vix"])
            return None

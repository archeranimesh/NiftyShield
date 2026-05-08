import sqlite3
import datetime
from typing import Optional

from src.db import connect

class IntradayMarketStore:
    def __init__(self, db_path: str = "data/portfolio/portfolio.sqlite") -> None:
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

    def record_market_snapshot(self, timestamp: datetime.datetime, nifty_spot: float, india_vix: float) -> None:
        with connect(self._db_path) as db:
            db.execute(
                """
                INSERT INTO intraday_market_snapshots (timestamp, nifty_spot, india_vix)
                VALUES (?, ?, ?)
                """,
                (timestamp, nifty_spot, india_vix),
            )

    def purge_old(self, days: int = 30) -> int:
        cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days)
        with connect(self._db_path) as db:
            cursor = db.execute(
                "DELETE FROM intraday_market_snapshots WHERE timestamp < ?",
                (cutoff,)
            )
            return cursor.rowcount

    def get_latest(self) -> Optional[tuple[float, float]]:
        with connect(self._db_path) as db:
            cursor = db.execute(
                "SELECT nifty_spot, india_vix FROM intraday_market_snapshots ORDER BY timestamp DESC LIMIT 1"
            )
            row = cursor.fetchone()
            if row:
                return (row["nifty_spot"], row["india_vix"])
            return None

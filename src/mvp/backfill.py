"""Historical backfill primitives for the MVP tracker (M6).

Reads M0's ingested equity Parquet (``data/offline/equity_ohlcv/``) — no live API calls.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pyarrow.parquet as pq
import structlog

logger = structlog.get_logger(__name__)

DEFAULT_EQUITY_DIR = Path("data/offline/equity_ohlcv")


def _month_range(from_date: date, to_date: date) -> list[date]:
    months = []
    current = from_date.replace(day=1)
    while current <= to_date:
        months.append(current)
        if current.month == 12:
            current = current.replace(year=current.year + 1, month=1)
        else:
            current = current.replace(month=current.month + 1)
    return months


def fetch_historical_closes(
    symbol: str,
    from_date: date,
    to_date: date,
    *,
    data_dir: Path = DEFAULT_EQUITY_DIR,
) -> list[tuple[date, Decimal]]:
    """Fetch daily equity close prices for a symbol from M0's ingested Parquet.

    Args:
        symbol: NSE equity symbol to filter to.
        from_date: Start of the range, inclusive.
        to_date: End of the range, inclusive.
        data_dir: Root of the ``year/month`` partitioned equity Parquet tree.

    Returns:
        ``(date, close)`` pairs sorted ascending by date. Empty if no partition
        in the range exists.
    """
    closes: list[tuple[date, Decimal]] = []
    for month_start in _month_range(from_date, to_date):
        year = month_start.strftime("%Y")
        month = month_start.strftime("%m")
        parquet_path = data_dir / year / month / f"equity_{year}_{month}.parquet"
        if not parquet_path.exists():
            continue
        table = pq.read_table(parquet_path)
        for row in table.to_pylist():
            if row["symbol"] != symbol:
                continue
            trade_date = row["trade_date"]
            if not (from_date <= trade_date <= to_date):
                continue
            closes.append((trade_date, Decimal(str(row["close"]))))

    if not closes:
        logger.warning(
            "mvp_backfill_no_data", symbol=symbol, from_date=str(from_date), to_date=str(to_date)
        )
    return sorted(closes, key=lambda pair: pair[0])

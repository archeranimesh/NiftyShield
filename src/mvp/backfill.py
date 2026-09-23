"""Historical backfill primitives for the MVP tracker (M6).

Reads M0's ingested equity Parquet (``data/offline/equity_ohlcv/``) — no live API calls.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING

import pyarrow.parquet as pq
import structlog

from src.market_calendar.holidays import is_trading_day
from src.mvp.models import MVPSnapshot, PickStatus

if TYPE_CHECKING:
    from src.mvp.models import Pick
    from src.mvp.store import MVPStore

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


def enter_backfill_pick(
    pick: Pick, equity_closes: dict[date, Decimal]
) -> tuple[date, Decimal] | None:
    """Determine the entry date and price for a past backfilled pick.

    The rule: use the NEXT trading day's daily CLOSE after reco_date.
    If close > reco_price, enter at that close on that date.
    Else the pick stays PENDING (returns None).
    """
    if pick.reco_price is None:
        return None

    reco_date = date.fromisoformat(pick.pick_date)
    candidate = reco_date + timedelta(days=1)

    while not is_trading_day(candidate):
        candidate += timedelta(days=1)

    next_trading_day = candidate

    if next_trading_day not in equity_closes:
        return None

    next_close = equity_closes[next_trading_day]

    if next_close > pick.reco_price:
        return (next_trading_day, next_close)

    return None


def run_backfill(
    store: MVPStore,
    pick_id: str,
    equity_closes: dict[date, Decimal],
    index_closes: dict[date, Decimal],
    end_date: date | None = None,
) -> None:
    """Walk daily equity closes from entry date to today.

    Records one MVPSnapshot per trading day.
    Auto-exits if target_price or stop_loss is hit.

    WARNING: The walk-start-date invariant here is that starting from `reco_date + 1`
    is safe because there are zero trading days between `reco_date` and `entry_date`
    that we could accidentally snapshot while still PENDING. If adapting this function
    to resume an already-OPEN pick from arbitrary dates, the start logic must be hardened.
    """
    pick = store.get_pick(pick_id)
    if not pick:
        return

    if pick.status == PickStatus.PENDING:
        entry = enter_backfill_pick(pick, equity_closes)
        if not entry:
            return
        entry_date, entry_price = entry
        store.update_pick(pick.pick_id, entry_price=entry_price)
        pick = store.get_pick(pick_id)
        if not pick or pick.status != PickStatus.OPEN:
            return

    if pick.status != PickStatus.OPEN:
        return

    if end_date is None:
        end_date = datetime.now(timezone.utc).date()

    existing_snapshots = store.get_snapshots(pick_id, limit=10000)
    existing_dates = {date.fromisoformat(s.captured_at[:10]) for s in existing_snapshots}

    start_date = date.fromisoformat(pick.pick_date) + timedelta(days=1)
    current_date = start_date

    while current_date <= end_date:
        if not is_trading_day(current_date):
            current_date += timedelta(days=1)
            continue

        if current_date in existing_dates:
            current_date += timedelta(days=1)
            continue

        if current_date not in equity_closes:
            current_date += timedelta(days=1)
            continue

        close_price = equity_closes[current_date]
        benchmark_close = index_closes.get(current_date)

        snapshot = MVPSnapshot(
            pick_id=pick_id,
            ltp=close_price,
            captured_at=f"{current_date.isoformat()}T00:00:00Z",
            benchmark_close=benchmark_close,
        )
        store.record_snapshot(snapshot)

        # Check for auto-exit
        terminal_status = None
        if pick.target_price is not None and close_price >= pick.target_price:
            terminal_status = PickStatus.TARGET_HIT
        elif pick.stop_loss is not None and close_price <= pick.stop_loss:
            terminal_status = PickStatus.SL_HIT

        if terminal_status is not None:
            store.close_pick(pick_id, close_price, terminal_status)
            break

        current_date += timedelta(days=1)

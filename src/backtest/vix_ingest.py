"""India VIX historical data ingestion and loading.

Handles fetching VIX daily OHLC from NSE CSV files or Upstox API,
storing them as per-year Parquet files, and loading them into
pandas Series for IVR computation.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import quote

import pandas as pd
import requests

from src.client.exceptions import DataFetchError
from src.config import settings

logger = logging.getLogger(__name__)


def ingest_vix_from_csv(csv_path: Path, out_dir: Path) -> int:
    """Parse NSE historical VIX CSV, write/merge into Parquet.

    Args:
        csv_path: Path to the NSE VIX CSV file.
        out_dir: Root directory for Parquet storage.

    Returns:
        Count of new rows written (0 if all already present).

    Raises:
        ValueError: If csv_path does not exist.
    """
    if not csv_path.exists():
        raise ValueError(f"CSV file not found: {csv_path}")

    df = pd.read_csv(csv_path)
    # NSE CSV date format: DD-Mon-YYYY (e.g. "01-Jan-2024")
    df["date"] = pd.to_datetime(df["Date"], format="%d-%b-%Y")
    df = df.rename(
        columns={
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
        }
    )
    df = df[["date", "open", "high", "low", "close"]]

    return _merge_and_save(df, out_dir)


def ingest_vix_from_api(
    from_date: date, to_date: date, out_dir: Path, token: str | None = None
) -> int:
    """Fetch daily VIX candles from Upstox API, write/merge into Parquet.

    Args:
        from_date: Start date for the fetch.
        to_date: End date for the fetch.
        out_dir: Root directory for Parquet storage.
        token: Upstox API token. Falls back to UPSTOX_ANALYTICS_TOKEN env var.

    Returns:
        Count of new rows written.

    Raises:
        DataFetchError: On HTTP errors or API failures.
    """
    token = token or settings.upstox_analytics_token
    if not token:
        raise ValueError("Upstox token not provided and UPSTOX_ANALYTICS_TOKEN env var not set.")

    # Resumability check: find the gap
    existing_series = load_vix_series(out_dir)
    if not existing_series.empty:
        last_date = existing_series.index[-1]
        if from_date <= last_date:
            # last_date is a date object. pd.to_datetime converts to Timestamp.
            gap_ts = pd.to_datetime(last_date) + pd.Timedelta(days=1)
            from_date = gap_ts.date()

    if from_date > to_date:
        return 0

    instrument_key = "NSE_INDEX|India VIX"
    encoded_key = quote(instrument_key, safe="")
    url = f"https://api.upstox.com/v2/historical-candle/{encoded_key}/day/{to_date.isoformat()}"
    params = {"from_date": from_date.isoformat()}
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}

    logger.debug("Fetching VIX candles from_date=%s to_date=%s", from_date, to_date)
    try:
        response = requests.get(url, params=params, headers=headers, timeout=10)
        response.raise_for_status()
    except requests.RequestException as e:
        raise DataFetchError(f"VIX candle fetch failed: {e}") from e

    data = response.json()
    candles = data.get("data", {}).get("candles", [])
    logger.debug(
        "VIX candle fetch complete status=%d rows=%d",
        response.status_code,
        len(candles),
    )

    if not candles:
        return 0

    # candles array: [[timestamp_str, open, high, low, close, volume, oi], ...]
    rows = []
    for c in candles:
        # Upstox returns tz-aware strings. Normalize and remove tz.
        dt = pd.to_datetime(c[0]).tz_localize(None).normalize()
        rows.append(
            {
                "date": dt,
                "open": float(c[1]),
                "high": float(c[2]),
                "low": float(c[3]),
                "close": float(c[4]),
            }
        )

    df = pd.DataFrame(rows)
    return _merge_and_save(df, out_dir)


def fetch_vix_latest(token: str | None = None) -> float | None:
    """Fetch the most recent India VIX daily close from the Upstox API.

    Requests the last 5 calendar days so that intraday calls (before today's
    candle settles) still return the previous close rather than nothing.

    Args:
        token: Upstox Analytics token. Falls back to UPSTOX_ANALYTICS_TOKEN
            env var.

    Returns:
        Most recent VIX close, or None if the token is missing, the network
        call fails, or the API returns no candles.
    """
    token = token or settings.upstox_analytics_token
    if not token:
        logger.warning("UPSTOX_ANALYTICS_TOKEN not set — cannot fetch live VIX.")
        return None

    today = date.today()
    from_date = today - timedelta(days=5)
    instrument_key = "NSE_INDEX|India VIX"
    encoded_key = quote(instrument_key, safe="")
    url = f"https://api.upstox.com/v2/historical-candle/{encoded_key}/day/{today.isoformat()}"
    params = {"from_date": from_date.isoformat()}
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}

    try:
        response = requests.get(url, params=params, headers=headers, timeout=10)
        response.raise_for_status()
        candles = response.json().get("data", {}).get("candles", [])
        if not candles:
            logger.warning("Upstox returned no VIX candles for last 5 days.")
            return None
        # candles are newest-first; take index 0 for the latest close
        return float(candles[0][4])
    except requests.RequestException as exc:
        logger.warning("Live VIX fetch failed: %s", exc)
        return None


def load_vix_series(data_dir: Path) -> pd.Series:
    """Load all VIX Parquet files under data_dir, return daily closes.

    Args:
        data_dir: Root directory of India VIX Parquet files.

    Returns:
        Daily closes sorted ascending, indexed by date (datetime.date objects).
        Returns empty Series if no files found.
    """
    files = list(data_dir.glob("**/india_vix_*.parquet"))
    if not files:
        return pd.Series(dtype="float64")

    dfs = [pd.read_parquet(f) for f in files]
    df = pd.concat(dfs).drop_duplicates(subset=["date"]).sort_values("date")

    series = df.set_index("date")["close"]
    series.index = series.index.date
    return series


def _merge_and_save(df: pd.DataFrame, out_dir: Path) -> int:
    """Merge new rows with existing Parquet files and save.

    Returns:
        Count of new unique rows added.
    """
    if df.empty:
        return 0

    new_count = 0
    df["year"] = df["date"].dt.year

    for year, group in df.groupby("year"):
        year_dir = out_dir / str(year)
        year_dir.mkdir(parents=True, exist_ok=True)
        parquet_path = year_dir / f"india_vix_{year}.parquet"

        if parquet_path.exists():
            existing = pd.read_parquet(parquet_path)
            # Filter incoming rows to only those not already present
            combined = pd.concat([existing, group[["date", "open", "high", "low", "close"]]])
            combined = combined.drop_duplicates(subset=["date"]).sort_values("date")
            added = len(combined) - len(existing)
            if added > 0:
                combined.to_parquet(parquet_path)
                new_count += added
        else:
            (
                group[["date", "open", "high", "low", "close"]]
                .sort_values("date")
                .to_parquet(parquet_path)
            )
            new_count += len(group)

    return new_count

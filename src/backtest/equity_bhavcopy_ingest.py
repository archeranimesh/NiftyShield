"""NSE CM (equity cash-market) bhavcopy ingest — M0 prerequisite for the MVP tracker's
historical backfill (M6/M8). Mirrors src/backtest/bhavcopy_ingest.py's session/parse/write
pattern for the F&O bhavcopy, scoped to equity daily closes for a caller-supplied symbol set.
"""

from __future__ import annotations

import csv
import subprocess
import zipfile
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import requests
import structlog
from pydantic import BaseModel

from src.config import settings

logger = structlog.get_logger(__name__)

_ZIP_MAGIC = b"PK\x03\x04"

_NSE_HEADERS = {
    "user-agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/134.0.0.0 Safari/537.36"
    ),
    "accept": ("text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8"),
    "accept-language": "en-US,en;q=0.9",
    "accept-encoding": "gzip, deflate, br",
    "Referer": "https://www.nseindia.com/",
    "Sec-CH-UA": '"Google Chrome";v="134", "Chromium";v="134", "Not?A_Brand";v="99"',
    "Sec-CH-UA-Mobile": "?0",
    "Sec-CH-UA-Platform": '"Windows"',
    "DNT": "1",
}

_CM_UDIFF_CDN = "https://nsearchives.nseindia.com/content/cm"
_INDEX_CDN = "https://nsearchives.nseindia.com/content/indices"


class EquityBhavRecord(BaseModel, frozen=True):
    trade_date: date
    symbol: str
    close: Decimal


class IndexBhavRecord(BaseModel, frozen=True):
    trade_date: date
    close: Decimal


def _build_session() -> requests.Session:
    """Build a requests.Session with NSE headers and optional cookie injection."""
    session = requests.Session()
    session.headers.update(_NSE_HEADERS)
    nse_cookie = (settings.nse_cookie or "").strip()
    if nse_cookie:
        session.headers["Cookie"] = nse_cookie
        logger.info("NSE_COOKIE found in env — using browser session cookie")
    else:
        # Pre-warm: pick up any stateless Akamai cookies from the homepage.
        try:
            session.get("https://www.nseindia.com", timeout=10)
        except Exception:  # Intentional: best-effort Akamai warm-up; failure is non-fatal
            pass
    return session


def download_equity_bhavcopy(trade_date: date, dest_dir: Path) -> Path:
    """Download the NSE CM (equity) Bhavcopy UDiFF ZIP for the given trade date.

    Uses a requests.Session pre-warmed on nseindia.com to acquire Akamai cookies;
    set NSE_COOKIE env-var to inject a browser session cookie when automated
    warm-up is insufficient.

    Returns the local path of the downloaded ZIP.
    Raises FileNotFoundError on HTTP 404 (holiday / non-trading day).
    Raises IOError on Akamai bot-block (non-ZIP response) or other network error.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    session = _build_session()

    filename = f"BhavCopy_NSE_CM_0_0_0_{trade_date:%Y%m%d}_F_0000.csv.zip"
    url = f"{_CM_UDIFF_CDN}/{filename}"

    try:
        resp = session.get(url, timeout=30)
    except Exception as e:
        raise OSError(f"Error downloading {trade_date}: {e}") from e

    if resp.status_code == 404:
        raise FileNotFoundError(f"NSE returned 404 for {trade_date} — likely a holiday")
    if resp.status_code != 200:
        raise OSError(f"HTTP {resp.status_code} for {trade_date}")

    content = resp.content
    if content[:4] != _ZIP_MAGIC:
        raise OSError(
            f"Response for {trade_date} is not a ZIP — Akamai bot-check returned HTML. "
            f"Set NSE_COOKIE env-var with a browser session cookie."
        )

    dest_path = dest_dir / filename
    dest_path.write_bytes(content)
    logger.info("Downloaded equity bhavcopy for %s → %s", trade_date, filename)
    return dest_path


def parse_equity_bhavcopy(csv_path: Path, symbols: set[str]) -> list[EquityBhavRecord]:
    """Parse an NSE CM Bhavcopy ZIP and return records for the given symbol set.

    Filters to the ``EQ`` series only — a symbol can appear multiple times per day
    under other series (BE, BZ, …), which would otherwise duplicate/skew the close.
    Raises ValueError on a corrupt or unreadable ZIP.
    """
    try:
        with zipfile.ZipFile(csv_path) as z:
            csv_filename = z.namelist()[0]
            with z.open(csv_filename) as f:
                lines = [line.decode("utf-8") for line in f.readlines()]
    except zipfile.BadZipFile as e:
        raise ValueError(f"Corrupt or unreadable ZIP file: {csv_path}") from e

    reader = csv.DictReader(lines)
    records = []
    for row in reader:
        sym = row["TckrSymb"].strip()
        if sym not in symbols:
            continue
        if row.get("SctySrs", "").strip() != "EQ":
            continue
        records.append(
            EquityBhavRecord(
                trade_date=date.fromisoformat(row["TradDt"].strip()),
                symbol=sym,
                close=Decimal(row["ClsPric"]),
            )
        )
    return records


def _git_commit_metadata() -> bytes:
    try:
        return (
            subprocess.check_output(
                ["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL, timeout=2
            )
            .strip()
            .encode("utf-8")
        )
    except Exception:  # Intentional: git metadata is advisory; missing commit hash is acceptable
        return b"unknown"


def write_equity_to_parquet(
    records: list[EquityBhavRecord], month_date: date, dest_dir: Path
) -> None:
    """Idempotently appends equity close records to the Parquet file for the given month."""
    if not records:
        return

    year = month_date.strftime("%Y")
    month = month_date.strftime("%m")

    partition_dir = dest_dir / year / month
    partition_dir.mkdir(parents=True, exist_ok=True)

    parquet_path = partition_dir / f"equity_{year}_{month}.parquet"

    data = [r.model_dump() for r in records]

    schema = pa.schema(
        [
            ("trade_date", pa.date32()),
            ("symbol", pa.string()),
            ("close", pa.decimal128(18, 4)),
        ]
    )

    metadata = schema.metadata or {}
    metadata.update(
        {
            b"git_commit": _git_commit_metadata(),
            b"run_timestamp": datetime.now(timezone.utc).isoformat().encode("utf-8"),
        }
    )
    schema = schema.with_metadata(metadata)

    new_table = pa.Table.from_pylist(data, schema=schema)

    if parquet_path.exists():
        existing_table = pq.read_table(parquet_path)
        existing_dates = set(existing_table.column("trade_date").to_pylist())
        new_dates = set(new_table.column("trade_date").to_pylist())

        # Note: This batch behavior is conservative — if any date in a batch
        # overlaps, the whole batch is skipped rather than just the duplicates.
        # For the bootstrap use case (one day at a time) this is correct.
        if any(d in existing_dates for d in new_dates):
            return

        final_table = pa.concat_tables([existing_table, new_table])
        final_table = final_table.replace_schema_metadata(schema.metadata)
    else:
        final_table = new_table

    pq.write_table(final_table, parquet_path)


def download_index_bhavcopy(trade_date: date, dest_dir: Path) -> Path:
    """Download the NSE 'indices close' CSV for the given trade date."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    session = _build_session()

    filename = f"ind_close_all_{trade_date:%d%m%Y}.csv"
    url = f"{_INDEX_CDN}/{filename}"

    try:
        resp = session.get(url, timeout=30)
    except Exception as e:
        raise OSError(f"Error downloading index close {trade_date}: {e}") from e

    if resp.status_code == 404:
        raise FileNotFoundError(f"NSE returned 404 for index close {trade_date} — likely a holiday")
    if resp.status_code != 200:
        raise OSError(f"HTTP {resp.status_code} for index close {trade_date}")

    content = resp.content
    if b"<html" in content[:100].lower() or b"<!doctype" in content[:100].lower():
        raise OSError(
            f"Response for {trade_date} is HTML — Akamai bot-check. "
            f"Set NSE_COOKIE env-var with a browser session cookie."
        )

    dest_path = dest_dir / filename
    dest_path.write_bytes(content)
    logger.info("Downloaded index close for %s → %s", trade_date, filename)
    return dest_path


def parse_index_bhavcopy(csv_path: Path) -> IndexBhavRecord | None:
    """Parse an NSE ind_close_all CSV and return the Nifty 50 record."""
    date_str = csv_path.stem[-8:]  # extracts DDMMYYYY from ind_close_all_DDMMYYYY
    trade_date = datetime.strptime(date_str, "%d%m%Y").date()

    with csv_path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row["Index Name"].strip().strip('"') == "Nifty 50":
                return IndexBhavRecord(
                    trade_date=trade_date,
                    close=Decimal(row["Closing Index Value"].strip()),
                )
    return None


def write_index_to_parquet(
    records: list[IndexBhavRecord], month_date: date, dest_dir: Path
) -> None:
    """Idempotently appends index close records to the Parquet file for the given month."""
    if not records:
        return

    year = month_date.strftime("%Y")
    month = month_date.strftime("%m")

    partition_dir = dest_dir / year / month
    partition_dir.mkdir(parents=True, exist_ok=True)

    parquet_path = partition_dir / f"index_{year}_{month}.parquet"

    data = [r.model_dump() for r in records]

    schema = pa.schema(
        [
            ("trade_date", pa.date32()),
            ("close", pa.decimal128(18, 4)),
        ]
    )

    metadata = schema.metadata or {}
    metadata.update(
        {
            b"git_commit": _git_commit_metadata(),
            b"run_timestamp": datetime.now(timezone.utc).isoformat().encode("utf-8"),
        }
    )
    schema = schema.with_metadata(metadata)

    new_table = pa.Table.from_pylist(data, schema=schema)

    if parquet_path.exists():
        existing_table = pq.read_table(parquet_path)
        existing_dates = set(existing_table.column("trade_date").to_pylist())
        new_dates = set(new_table.column("trade_date").to_pylist())

        if any(d in existing_dates for d in new_dates):
            return

        final_table = pa.concat_tables([existing_table, new_table])
        final_table = final_table.replace_schema_metadata(schema.metadata)
    else:
        final_table = new_table

    pq.write_table(final_table, parquet_path)

import calendar
import csv
import logging
import re
import subprocess
import zipfile
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import requests
from pydantic import BaseModel, Field

from src.config import settings

logger = logging.getLogger(__name__)

# UDiFF (Dec 2024+) instrument type codes → canonical instrument strings
_UDIFF_FI_MAP: dict[str, str] = {
    "IDO": "OPTIDX",
    "STO": "OPTSTK",
    "IDF": "FUTIDX",
    "SDF": "FUTSTK",
}


class BhavRecord(BaseModel, frozen=True):
    trade_date: date
    symbol: str
    underlying: str
    instrument: str
    expiry: date
    strike: Decimal = Field(default=Decimal("0"))
    option_type: str = Field(default="XX")
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    settle_price: (
        Decimal  # Note: NSE bhavcopy settle_price is a 30-min VWAP (3:00-3:30 PM), not EOD LTP.
    )
    volume: int
    oi: int


def get_last_thursday(year: int, month: int) -> date:
    c = calendar.Calendar(firstweekday=calendar.MONDAY)
    monthcal = c.monthdatescalendar(year, month)
    for week in reversed(monthcal):
        thursday = week[calendar.THURSDAY]
        if thursday.month == month:
            return thursday
    return date(year, month, 1)


def parse_option_symbol(symbol: str) -> dict[str, str | date | Decimal]:
    """
    Parses NSE option symbols into expiry, strike, and option_type.
    """
    if len(symbol) < 6:
        raise ValueError(f"Invalid symbol format: {symbol}")

    option_type = symbol[-2:]
    if option_type not in ("CE", "PE"):
        raise ValueError(f"Invalid option type in symbol: {symbol}")

    core = symbol[:-2]

    first_digit_match = re.search(r"\d", core)
    if not first_digit_match:
        raise ValueError(f"No expiry token found in symbol: {symbol}")

    underlying = core[: first_digit_match.start()]
    rest = core[first_digit_match.start() :]

    # Try YYMDD (weekly)
    m_weekly = re.match(r"^(\d{2}[1-9OND]\d{2})(\d+)$", rest)
    if m_weekly and Decimal(m_weekly.group(2)) > 0:
        expiry_token, strike_str = m_weekly.groups()
        yy = int(expiry_token[:2])
        m_char = expiry_token[2]
        dd = int(expiry_token[3:])
        year = 2000 + yy
        if m_char == "O":
            month = 10
        elif m_char == "N":
            month = 11
        elif m_char == "D":
            month = 12
        else:
            month = int(m_char)
        return {
            "underlying": underlying,
            "expiry": date(year, month, dd),
            "strike": Decimal(strike_str),
            "option_type": option_type,
        }

    # Try YYMON (monthly)
    m_monthly = re.match(r"^(\d{2}[A-Z]{3})(\d+)$", rest)
    if m_monthly:
        expiry_token, strike_str = m_monthly.groups()
        yy = int(expiry_token[:2])
        mon_str = expiry_token[2:5]
        year = 2000 + yy
        month = datetime.strptime(mon_str, "%b").month
        return {
            "underlying": underlying,
            "expiry": get_last_thursday(year, month),
            "strike": Decimal(strike_str),
            "option_type": option_type,
        }

    raise ValueError(f"Unrecognized expiry format in symbol: {symbol}")


def _parse_legacy(
    reader: csv.DictReader,
    valid_instruments: set[str],
    underlying: str,
) -> list[BhavRecord]:
    """Parse pre-Dec 2024 NSE F&O bhavcopy CSV (legacy archive format)."""
    records = []
    for row in reader:
        instrument = row["INSTRUMENT"]
        if instrument not in valid_instruments:
            continue
        sym = row["SYMBOL"]
        if sym != underlying:
            continue
        strike = Decimal(row["STRIKE_PR"])
        opt_type = row["OPTION_TYP"]
        if strike == 0 and opt_type in ("CE", "PE"):
            logger.warning("Skipping corrupted strike row: %s", row)
            continue
        trade_date = datetime.strptime(row["TIMESTAMP"], "%d-%b-%Y").date()
        expiry = datetime.strptime(row["EXPIRY_DT"], "%d-%b-%Y").date()
        records.append(
            BhavRecord(
                trade_date=trade_date,
                symbol=sym,
                underlying=sym,
                instrument=instrument,
                expiry=expiry,
                strike=strike,
                option_type=opt_type,
                open=Decimal(row["OPEN"]),
                high=Decimal(row["HIGH"]),
                low=Decimal(row["LOW"]),
                close=Decimal(row["CLOSE"]),
                # Note: SETTLE_PR in legacy bhavcopy is the 30-minute VWAP settlement price.
                # IV reconstruction using settle_price will diverge from live Greeks on volatile close days.
                # Refer to T1-B.1 in docs/reviews/audit_2026-05-15.md.
                settle_price=Decimal(row["SETTLE_PR"]),
                volume=int(row["CONTRACTS"]),
                oi=int(row["OPEN_INT"]),
            )
        )
    return records


def _parse_udiff(
    reader: csv.DictReader,
    valid_instruments: set[str],
    underlying: str,
) -> list[BhavRecord]:
    """Parse Dec 2024+ NSE F&O bhavcopy CSV (UDiFF format).

    Instrument type codes are mapped via ``_UDIFF_FI_MAP`` to the same canonical
    strings used by the legacy parser so ``BhavRecord`` is format-agnostic.
    """
    records = []
    for row in reader:
        fi_code = row.get("FinInstrmTp", "").strip()
        instrument = _UDIFF_FI_MAP.get(fi_code)
        if instrument is None or instrument not in valid_instruments:
            continue
        sym = row["TckrSymb"].strip()
        if sym != underlying:
            continue
        strike_raw = (row.get("StrkPric") or "0").strip() or "0"
        strike = Decimal(strike_raw)
        opt_type = (row.get("OptnTp") or "").strip() or "XX"
        if strike == 0 and opt_type in ("CE", "PE"):
            logger.warning("Skipping corrupted strike row: %s", row)
            continue
        trade_date = date.fromisoformat(row["TradDt"].strip())
        expiry = date.fromisoformat(row["XpryDt"].strip())
        records.append(
            BhavRecord(
                trade_date=trade_date,
                symbol=sym,
                underlying=sym,
                instrument=instrument,
                expiry=expiry,
                strike=strike,
                option_type=opt_type,
                open=Decimal(row["OpnPric"]),
                high=Decimal(row["HghPric"]),
                low=Decimal(row["LwPric"]),
                close=Decimal(row["ClsPric"]),
                # Note: SttlmPric in UDiFF bhavcopy is the 30-minute VWAP settlement price.
                # IV reconstruction using settle_price will diverge from live Greeks on volatile close days.
                # Refer to T1-B.1 in docs/reviews/audit_2026-05-15.md.
                settle_price=Decimal(row["SttlmPric"]),
                volume=int(row["TtlTradgVol"]),
                oi=int(row["OpnIntrst"]),
            )
        )
    return records


def parse_bhavcopy(
    csv_path: Path, underlying: str = "NIFTY", include_futures: bool = False
) -> list[BhavRecord]:
    """Parse an NSE F&O Bhavcopy ZIP and return matching BhavRecords.

    Detects legacy vs UDiFF format automatically by inspecting CSV headers.
    Raises ValueError on a corrupt or unreadable ZIP.
    """
    valid_instruments = {"OPTIDX", "OPTSTK"}
    if include_futures:
        valid_instruments.update({"FUTIDX", "FUTSTK"})

    try:
        with zipfile.ZipFile(csv_path) as z:
            csv_filename = z.namelist()[0]
            with z.open(csv_filename) as f:
                lines = [line.decode("utf-8") for line in f.readlines()]
                reader = csv.DictReader(lines)
                if "TradDt" in (reader.fieldnames or []):
                    return _parse_udiff(reader, valid_instruments, underlying)
                return _parse_legacy(reader, valid_instruments, underlying)
    except zipfile.BadZipFile as e:
        raise ValueError(f"Corrupt or unreadable ZIP file: {csv_path}") from e


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

_NSE_CDN = "https://nsearchives.nseindia.com/content/historical/DERIVATIVES"
_UDIFF_CDN = "https://nsearchives.nseindia.com/content/fo"


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
        except Exception:
            pass  # best-effort; continue regardless
    return session


def download_bhavcopy(trade_date: date, dest_dir: Path) -> Path:
    """Download the NSE F&O Bhavcopy ZIP for the given trade date.

    Tries the UDiFF URL first (Dec 2024+). On 404 falls back to the legacy
    archive URL (2016 – ~Nov 2024). Uses a requests.Session pre-warmed on
    nseindia.com to acquire Akamai cookies; set NSE_COOKIE env-var to inject
    a browser session cookie when automated warm-up is insufficient.

    Returns the local path of the downloaded ZIP.
    Raises FileNotFoundError on HTTP 404 from both URLs (holiday / non-trading day).
    Raises IOError on Akamai bot-block (non-ZIP response) or other network error.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    session = _build_session()

    # --- UDiFF URL (Dec 2024+) ---
    udiff_date_str = trade_date.strftime("%Y%m%d")
    udiff_filename = f"BhavCopy_NSE_FO_0_0_0_{udiff_date_str}_F_0000.csv.zip"
    udiff_url = f"{_UDIFF_CDN}/{udiff_filename}"

    try:
        resp = session.get(udiff_url, timeout=30)
    except Exception as e:
        raise OSError(f"Error downloading {trade_date}: {e}") from e

    if resp.status_code == 200:
        content = resp.content
        if content[:4] != _ZIP_MAGIC:
            raise OSError(
                f"UDiFF response for {trade_date} is not a ZIP — Akamai bot-check "
                f"returned HTML. Set NSE_COOKIE env-var with a browser session cookie."
            )
        dest_path = dest_dir / udiff_filename
        dest_path.write_bytes(content)
        logger.info("Downloaded UDiFF bhavcopy for %s → %s", trade_date, udiff_filename)
        return dest_path

    if resp.status_code != 404:
        raise OSError(f"UDiFF HTTP {resp.status_code} for {trade_date}")

    # UDiFF 404 — fall back to legacy archive URL
    logger.debug("UDiFF 404 for %s — trying legacy URL", trade_date)

    # --- Legacy URL (2016 – ~Nov 2024) ---
    date_str = trade_date.strftime("%d%b%Y").upper()
    month_str = trade_date.strftime("%b").upper()
    year_str = trade_date.strftime("%Y")
    legacy_filename = f"fo{date_str}bhav.csv.zip"
    legacy_url = f"{_NSE_CDN}/{year_str}/{month_str}/{legacy_filename}"

    try:
        legacy_resp = session.get(legacy_url, timeout=30)
    except Exception as e:
        raise OSError(f"Error downloading {trade_date} (legacy): {e}") from e

    if legacy_resp.status_code == 404:
        raise FileNotFoundError(f"NSE returned 404 for {trade_date} — likely a holiday")
    if legacy_resp.status_code != 200:
        raise OSError(f"Legacy HTTP {legacy_resp.status_code} for {trade_date}")

    content = legacy_resp.content
    if content[:4] != _ZIP_MAGIC:
        raise OSError(
            f"Legacy response for {trade_date} is not a ZIP — Akamai bot-check "
            f"returned HTML. Set NSE_COOKIE env-var with a browser session cookie."
        )

    dest_path = dest_dir / legacy_filename
    dest_path.write_bytes(content)
    logger.info("Downloaded legacy bhavcopy for %s → %s", trade_date, legacy_filename)
    return dest_path


def write_to_parquet(records: list[BhavRecord], month_date: date, dest_dir: Path) -> None:
    """
    Idempotently appends records to the Parquet file for the given month.
    """
    if not records:
        return

    year = month_date.strftime("%Y")
    month = month_date.strftime("%m")

    partition_dir = dest_dir / year / month
    partition_dir.mkdir(parents=True, exist_ok=True)

    parquet_path = partition_dir / f"nifty_{year}_{month}.parquet"

    # Convert records to list of dicts
    data = [r.model_dump() for r in records]

    # Schema must strictly use decimal128(18,4) for price fields to prevent float64 inference
    schema = pa.schema(
        [
            ("trade_date", pa.date32()),
            ("symbol", pa.string()),
            ("underlying", pa.string()),
            ("instrument", pa.string()),
            ("expiry", pa.date32()),
            ("strike", pa.decimal128(18, 4)),
            ("option_type", pa.string()),
            ("open", pa.decimal128(18, 4)),
            ("high", pa.decimal128(18, 4)),
            ("low", pa.decimal128(18, 4)),
            ("close", pa.decimal128(18, 4)),
            ("settle_price", pa.decimal128(18, 4)),
            ("volume", pa.int64()),
            ("oi", pa.int64()),
        ]
    )

    metadata = schema.metadata or {}
    try:
        git_commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL, timeout=2
        ).strip()
    except Exception:
        git_commit = "unknown"

    metadata.update(
        {
            b"git_commit": git_commit.encode("utf-8"),
            b"run_timestamp": datetime.now(timezone.utc).isoformat().encode("utf-8"),
        }
    )
    schema = schema.with_metadata(metadata)

    new_table = pa.Table.from_pylist(data, schema=schema)

    if parquet_path.exists():
        existing_table = pq.read_table(parquet_path)

        # Idempotency check: if trade_date already in existing data, skip append
        existing_dates = set(existing_table.column("trade_date").to_pylist())
        new_dates = set(new_table.column("trade_date").to_pylist())

        # If any of the new dates are already in the existing dates, we assume it's already written.
        # Note: This batch behavior is conservative — if any date in a batch overlaps, the whole
        # batch is skipped rather than just the duplicates. For the bootstrap use case (one day
        # at a time) this is correct. Downstream callers passing multi-day batches need to know about it.
        if any(d in existing_dates for d in new_dates):
            return

        final_table = pa.concat_tables([existing_table, new_table])
        final_table = final_table.replace_schema_metadata(schema.metadata)
    else:
        final_table = new_table

    pq.write_table(final_table, parquet_path)

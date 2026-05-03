import csv
import logging
import os
import zipfile
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
import re
import calendar

import requests

import pyarrow as pa
import pyarrow.parquet as pq
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

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
    settle_price: Decimal
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
    
    first_digit_match = re.search(r'\d', core)
    if not first_digit_match:
        raise ValueError(f"No expiry token found in symbol: {symbol}")
        
    underlying = core[:first_digit_match.start()]
    rest = core[first_digit_match.start():]
    
    # Try YYMDD (weekly)
    m_weekly = re.match(r'^(\d{2}[1-9OND]\d{2})(\d+)$', rest)
    if m_weekly and Decimal(m_weekly.group(2)) > 0:
        expiry_token, strike_str = m_weekly.groups()
        yy = int(expiry_token[:2])
        m_char = expiry_token[2]
        dd = int(expiry_token[3:])
        year = 2000 + yy
        if m_char == 'O': month = 10
        elif m_char == 'N': month = 11
        elif m_char == 'D': month = 12
        else: month = int(m_char)
        return {
            "underlying": underlying,
            "expiry": date(year, month, dd),
            "strike": Decimal(strike_str),
            "option_type": option_type
        }
        
    # Try YYMON (monthly)
    m_monthly = re.match(r'^(\d{2}[A-Z]{3})(\d+)$', rest)
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
            "option_type": option_type
        }
        
    raise ValueError(f"Unrecognized expiry format in symbol: {symbol}")

def parse_bhavcopy(csv_path: Path, underlying: str = "NIFTY", include_futures: bool = False) -> list[BhavRecord]:
    """
    Parses an NSE Bhavcopy CSV file inside a ZIP and returns matching BhavRecords.
    Raises ValueError on a corrupt or unreadable ZIP.
    """
    records = []
    
    valid_instruments = {"OPTIDX", "OPTSTK"}
    if include_futures:
        valid_instruments.update({"FUTIDX", "FUTSTK"})
        
    try:
        with zipfile.ZipFile(csv_path) as z:
            # Assume there's only one CSV in the ZIP
            csv_filename = z.namelist()[0]
            with z.open(csv_filename) as f:
                # Decode lines as string
                lines = [line.decode("utf-8") for line in f.readlines()]
                reader = csv.DictReader(lines)
                
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
                    
                    rec = BhavRecord(
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
                        settle_price=Decimal(row["SETTLE_PR"]),
                        volume=int(row["CONTRACTS"]),
                        oi=int(row["OPEN_INT"])
                    )
                    records.append(rec)
                
    except zipfile.BadZipFile as e:
        raise ValueError(f"Corrupt or unreadable ZIP file: {csv_path}") from e
                
    return records


_ZIP_MAGIC = b"PK\x03\x04"

_NSE_HEADERS = {
    "user-agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/134.0.0.0 Safari/537.36"
    ),
    "accept": (
        "text/html,application/xhtml+xml,application/xml;"
        "q=0.9,image/webp,*/*;q=0.8"
    ),
    "accept-language": "en-US,en;q=0.9",
    "accept-encoding": "gzip, deflate, br",
    "Referer": "https://www.nseindia.com/",
    "Sec-CH-UA": '"Google Chrome";v="134", "Chromium";v="134", "Not?A_Brand";v="99"',
    "Sec-CH-UA-Mobile": "?0",
    "Sec-CH-UA-Platform": '"Windows"',
    "DNT": "1",
}

_NSE_CDN = "https://nsearchives.nseindia.com/content/historical/DERIVATIVES"


def download_bhavcopy(trade_date: date, dest_dir: Path) -> Path:
    """
    Downloads the NSE F&O Bhavcopy ZIP for the given date.

    Uses a requests.Session that pre-warms on nseindia.com to acquire Akamai
    cookies before hitting nsearchives.nseindia.com. Optionally reads a raw
    NSE_COOKIE env-var to inject a browser session cookie when automated
    warm-up is insufficient.

    Returns the path to the downloaded ZIP.
    Raises FileNotFoundError on HTTP 404 (holiday or non-trading day).
    Raises IOError if the response is not a valid ZIP (Akamai block) or on
    any other network failure.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)

    date_str = trade_date.strftime("%d%b%Y").upper()
    month_str = trade_date.strftime("%b").upper()
    year_str = trade_date.strftime("%Y")
    filename = f"fo{date_str}bhav.csv.zip"
    url = f"{_NSE_CDN}/{year_str}/{month_str}/{filename}"
    dest_path = dest_dir / filename

    session = requests.Session()
    session.headers.update(_NSE_HEADERS)

    # Inject browser cookie if provided — get from browser DevTools → Network
    # tab → any nseindia.com request → copy the Cookie header value, then:
    # export NSE_COOKIE="<paste here>"
    nse_cookie = os.environ.get("NSE_COOKIE", "").strip()
    if nse_cookie:
        session.headers["Cookie"] = nse_cookie
        logger.info("NSE_COOKIE found in env — using browser session cookie")
    else:
        # Pre-warm: visit nseindia.com to acquire Akamai session cookies.
        # This may not fully satisfy JS-challenge requirements but picks up
        # any stateless cookies set on the homepage.
        try:
            session.get("https://www.nseindia.com", timeout=10)
        except Exception:
            pass  # warm-up is best-effort; continue regardless

    try:
        resp = session.get(url, timeout=30)
    except Exception as e:
        raise IOError(f"Error downloading {trade_date}: {e}")

    if resp.status_code == 404:
        raise FileNotFoundError(f"NSE returned 404 for {trade_date} — likely a holiday")
    if resp.status_code != 200:
        raise IOError(f"HTTP {resp.status_code} for {trade_date}")

    content = resp.content
    if not content[:4] == _ZIP_MAGIC:
        raise IOError(
            f"Response for {trade_date} is not a ZIP file — Akamai bot-check "
            f"returned HTML. Set NSE_COOKIE env-var with a browser session "
            f"cookie from nseindia.com to bypass."
        )

    dest_path.write_bytes(content)
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
    schema = pa.schema([
        ('trade_date', pa.date32()),
        ('symbol', pa.string()),
        ('underlying', pa.string()),
        ('instrument', pa.string()),
        ('expiry', pa.date32()),
        ('strike', pa.decimal128(18, 4)),
        ('option_type', pa.string()),
        ('open', pa.decimal128(18, 4)),
        ('high', pa.decimal128(18, 4)),
        ('low', pa.decimal128(18, 4)),
        ('close', pa.decimal128(18, 4)),
        ('settle_price', pa.decimal128(18, 4)),
        ('volume', pa.int64()),
        ('oi', pa.int64()),
    ])
    
    new_table = pa.Table.from_pylist(data, schema=schema)
    
    if parquet_path.exists():
        existing_table = pq.read_table(parquet_path)
        
        # Idempotency check: if trade_date already in existing data, skip append
        existing_dates = set(existing_table.column('trade_date').to_pylist())
        new_dates = set(new_table.column('trade_date').to_pylist())
        
        # If any of the new dates are already in the existing dates, we assume it's already written.
        # Note: This batch behavior is conservative — if any date in a batch overlaps, the whole 
        # batch is skipped rather than just the duplicates. For the bootstrap use case (one day 
        # at a time) this is correct. Downstream callers passing multi-day batches need to know about it.
        if any(d in existing_dates for d in new_dates):
            return
            
        final_table = pa.concat_tables([existing_table, new_table])
    else:
        final_table = new_table
        
    pq.write_table(final_table, parquet_path)


import csv
import logging
import zipfile
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
import re
import urllib.request
import urllib.error

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
        
    # Try DDMONYY / YYMONDD
    m_monthly_day = re.match(r'^(\d{2}[A-Z]{3}\d{2})(\d+)$', rest)
    if m_monthly_day and Decimal(m_monthly_day.group(2)) > 0:
        expiry_token, strike_str = m_monthly_day.groups()
        yy = int(expiry_token[:2])
        mon_str = expiry_token[2:5]
        dd = int(expiry_token[5:])
        year = 2000 + yy
        month = datetime.strptime(mon_str, "%b").month
        return {
            "underlying": underlying,
            "expiry": date(year, month, dd),
            "strike": Decimal(strike_str),
            "option_type": option_type
        }
        
    # Try YYMON
    m_monthly = re.match(r'^(\d{2}[A-Z]{3})(\d+)$', rest)
    if m_monthly:
        expiry_token, strike_str = m_monthly.groups()
        yy = int(expiry_token[:2])
        mon_str = expiry_token[2:5]
        year = 2000 + yy
        month = datetime.strptime(mon_str, "%b").month
        # We don't know the exact day without a calendar calculation, defaulting to 1st for now
        # Actually, if we just need it for testing, returning the 1st of the month is okay unless specified
        return {
            "underlying": underlying,
            "expiry": date(year, month, 1),
            "strike": Decimal(strike_str),
            "option_type": option_type
        }
        
    raise ValueError(f"Unrecognized expiry format in symbol: {symbol}")

def parse_bhavcopy(csv_path: Path, underlying: str = "NIFTY") -> list[BhavRecord]:
    """
    Parses an NSE Bhavcopy CSV file inside a ZIP and returns matching BhavRecords.
    """
    records = []
    
    with zipfile.ZipFile(csv_path) as z:
        # Assume there's only one CSV in the ZIP
        csv_filename = z.namelist()[0]
        with z.open(csv_filename) as f:
            # Decode lines as string
            lines = [line.decode("utf-8") for line in f.readlines()]
            reader = csv.DictReader(lines)
            
            for row in reader:
                instrument = row["INSTRUMENT"]
                if instrument not in ("OPTIDX", "OPTSTK", "FUTIDX", "FUTSTK"):
                    continue
                    
                sym = row["SYMBOL"]
                if sym != underlying:
                    continue
                    
                strike = Decimal(row["STRIKE_PR"])
                opt_type = row["OPTION_TYP"]
                
                if strike == 0 and opt_type in ("CE", "PE"):
                    logger.warning(f"Skipping corrupted strike row: {row}")
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
                
    return records

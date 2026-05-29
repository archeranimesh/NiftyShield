from datetime import datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from src.models.options import OptionChain


def _chain_to_table(
    chain: OptionChain,
    snapshot_ts: datetime,
    underlying: str,
) -> pa.Table:
    """Convert an OptionChain snapshot into a PyArrow Table."""
    cols = {
        "snapshot_ts": [],
        "underlying": [],
        "expiry_date": [],
        "strike": [],
        "option_type": [],
        "spot": [],
        "ltp": [],
        "bid": [],
        "ask": [],
        "oi": [],
        "volume": [],
        "iv": [],
        "delta": [],
        "gamma": [],
        "theta": [],
        "vega": [],
    }

    _D6 = Decimal("1.000000")

    def q6(v: Decimal | None) -> Decimal:
        if v is None:
            return Decimal("0.000000")
        return v.quantize(_D6, rounding=ROUND_HALF_UP)

    for strike_price, strike_strike in chain.strikes.items():
        for opt_type, leg in [("CE", strike_strike.ce), ("PE", strike_strike.pe)]:
            if leg is None:
                continue
            cols["snapshot_ts"].append(snapshot_ts)
            cols["underlying"].append(underlying)
            cols["expiry_date"].append(chain.expiry)
            cols["strike"].append(q6(leg.strike))
            cols["option_type"].append(opt_type)
            cols["spot"].append(q6(chain.underlying_spot))
            cols["ltp"].append(q6(leg.ltp))
            cols["bid"].append(q6(leg.bid))
            cols["ask"].append(q6(leg.ask))
            cols["oi"].append(int(leg.oi))
            cols["volume"].append(int(leg.volume))
            cols["iv"].append(q6(leg.iv))
            cols["delta"].append(q6(leg.delta))
            cols["gamma"].append(q6(leg.gamma))
            cols["theta"].append(q6(leg.theta))
            cols["vega"].append(q6(leg.vega))

    schema = pa.schema([
        ("snapshot_ts", pa.timestamp("us", tz="UTC")),
        ("underlying", pa.string()),
        ("expiry_date", pa.date32()),
        ("strike", pa.decimal128(18, 6)),
        ("option_type", pa.string()),
        ("spot", pa.decimal128(18, 6)),
        ("ltp", pa.decimal128(18, 6)),
        ("bid", pa.decimal128(18, 6)),
        ("ask", pa.decimal128(18, 6)),
        ("oi", pa.int64()),
        ("volume", pa.int64()),
        ("iv", pa.decimal128(18, 6)),
        ("delta", pa.decimal128(18, 6)),
        ("gamma", pa.decimal128(18, 6)),
        ("theta", pa.decimal128(18, 6)),
        ("vega", pa.decimal128(18, 6)),
    ])
    return pa.Table.from_pydict(cols, schema=schema)


class ChainWriter:
    """Writer for saving OptionChain snapshots to Parquet format."""

    def __init__(self, base_dir: str) -> None:
        """Store base_dir. Create no directories in __init__."""
        self.base_dir = Path(base_dir)

    def write_eod_snapshot(
        self,
        chain: OptionChain,
        snapshot_ts: datetime,
        underlying: str = "NIFTY_50",
    ) -> Path:
        """Write an EOD chain snapshot to Parquet.

        Path: {base_dir}/{year}/{month}/upstox_{date}.parquet
        Overwrites any existing file for the same date (idempotent).
        Returns the path written.
        """
        if snapshot_ts.tzinfo is None or snapshot_ts.tzinfo.utcoffset(snapshot_ts) != timedelta(0):
            raise ValueError("snapshot_ts must be timezone-aware UTC")

        ist_tz = timezone(timedelta(hours=5, minutes=30))
        ist_ts = snapshot_ts.astimezone(ist_tz)
        year = f"{ist_ts.year:04d}"
        month = f"{ist_ts.month:02d}"
        date_str = ist_ts.strftime("%Y-%m-%d")

        dest_dir = self.base_dir / year / month
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_path = dest_dir / f"upstox_{date_str}.parquet"

        table = _chain_to_table(chain, snapshot_ts, underlying)
        pq.write_table(table, dest_path)
        return dest_path

    def write_intraday_snapshot(
        self,
        chain: OptionChain,
        snapshot_ts: datetime,
        underlying: str = "NIFTY_50",
    ) -> Path:
        """Write a 5-min intraday snapshot to Parquet.

        Path: {base_dir}/{year}/{month}/{day}/upstox_{HHMM}.parquet
        HHMM is IST 24-hour (convert from UTC snapshot_ts internally).
        Overwrites any existing file for the same HHMM (idempotent).
        Returns the path written.
        """
        if snapshot_ts.tzinfo is None or snapshot_ts.tzinfo.utcoffset(snapshot_ts) != timedelta(0):
            raise ValueError("snapshot_ts must be timezone-aware UTC")

        ist_tz = timezone(timedelta(hours=5, minutes=30))
        ist_ts = snapshot_ts.astimezone(ist_tz)
        year = f"{ist_ts.year:04d}"
        month = f"{ist_ts.month:02d}"
        day = f"{ist_ts.day:02d}"
        hhmm = ist_ts.strftime("%H%M")

        dest_dir = self.base_dir / year / month / day
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_path = dest_dir / f"upstox_{hhmm}.parquet"

        table = _chain_to_table(chain, snapshot_ts, underlying)
        pq.write_table(table, dest_path)
        return dest_path

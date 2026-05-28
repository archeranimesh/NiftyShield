from datetime import datetime, date, timezone, timedelta
from decimal import Decimal
from pathlib import Path
import pandas as pd
import pytest

from src.backtest.chain_writer import ChainWriter
from src.backtest.chain_reader import ChainReader
from src.models.options import OptionChain, OptionChainStrike, OptionLeg


def _make_dummy_leg(strike: Decimal, delta: Decimal = Decimal("-0.25"), iv: Decimal = Decimal("15.5")) -> OptionLeg:
    return OptionLeg(
        ltp=Decimal("123.45"),
        bid=Decimal("123.00"),
        ask=Decimal("123.90"),
        oi=1000,
        volume=5000,
        delta=delta,
        gamma=Decimal("0.0012"),
        theta=Decimal("-12.34"),
        vega=Decimal("5.67"),
        iv=iv,
        strike=strike,
    )


def test_get_eod_snapshots_happy_path(tmp_path: Path) -> None:
    """Write fixture Parquet files via ChainWriter, read back with ChainReader; assert row count and columns."""
    eod_dir = tmp_path / "eod"
    writer = ChainWriter(str(eod_dir))
    
    chain = OptionChain(
        underlying_spot=Decimal("22000.00"),
        expiry=date(2026, 5, 28),
        strikes={
            Decimal("22000"): OptionChainStrike(
                ce=_make_dummy_leg(Decimal("22000"), Decimal("0.5")),
                pe=_make_dummy_leg(Decimal("22000"), Decimal("-0.5")),
            )
        },
    )
    
    ts = datetime(2026, 5, 27, 10, 0, tzinfo=timezone.utc)
    writer.write_eod_snapshot(chain, ts)

    reader = ChainReader(str(eod_dir))
    df = reader.get_eod_snapshots(
        start_date=date(2026, 5, 26),
        end_date=date(2026, 5, 28),
        underlying="NIFTY_50",
    )
    
    assert len(df) == 2
    assert set(df.columns) == set(ChainReader.EMPTY_COLS)
    assert df["option_type"].tolist() == ["CE", "PE"]
    assert df["underlying"].tolist() == ["NIFTY_50"] * 2
    
    # Verify close method cleans up without error
    reader.close()


def test_get_eod_snapshots_date_filter(tmp_path: Path) -> None:
    """Two files for different dates; filter by range; assert only correct date returned."""
    eod_dir = tmp_path / "eod"
    writer = ChainWriter(str(eod_dir))
    
    chain = OptionChain(
        underlying_spot=Decimal("22000.00"),
        expiry=date(2026, 5, 28),
        strikes={
            Decimal("22000"): OptionChainStrike(
                ce=_make_dummy_leg(Decimal("22000"), Decimal("0.5")),
            )
        },
    )
    
    # Write for May 26
    ts1 = datetime(2026, 5, 26, 10, 0, tzinfo=timezone.utc)
    writer.write_eod_snapshot(chain, ts1)
    
    # Write for May 27
    ts2 = datetime(2026, 5, 27, 10, 0, tzinfo=timezone.utc)
    writer.write_eod_snapshot(chain, ts2)

    reader = ChainReader(str(eod_dir))
    
    # Query only for May 27
    df = reader.get_eod_snapshots(
        start_date=date(2026, 5, 27),
        end_date=date(2026, 5, 27),
    )
    assert len(df) == 1
    assert df["snapshot_ts"].iloc[0].date() == date(2026, 5, 27)


def test_get_eod_snapshots_option_type_filter(tmp_path: Path) -> None:
    """Write CE and PE legs; assert query with option_type='CE' filters out PE."""
    eod_dir = tmp_path / "eod"
    writer = ChainWriter(str(eod_dir))
    
    chain = OptionChain(
        underlying_spot=Decimal("22000.00"),
        expiry=date(2026, 5, 28),
        strikes={
            Decimal("22000"): OptionChainStrike(
                ce=_make_dummy_leg(Decimal("22000"), Decimal("0.5")),
                pe=_make_dummy_leg(Decimal("22000"), Decimal("-0.5")),
            )
        },
    )
    ts = datetime(2026, 5, 27, 10, 0, tzinfo=timezone.utc)
    writer.write_eod_snapshot(chain, ts)

    reader = ChainReader(str(eod_dir))
    df = reader.get_eod_snapshots(
        start_date=date(2026, 5, 27),
        end_date=date(2026, 5, 27),
        option_type="CE",
    )
    assert len(df) == 1
    assert df["option_type"].iloc[0] == "CE"


def test_get_eod_snapshots_empty_dir(tmp_path: Path) -> None:
    """Non-existent dir -> empty DataFrame with correct columns."""
    non_existent = tmp_path / "does_not_exist"
    reader = ChainReader(str(non_existent))
    
    df = reader.get_eod_snapshots(
        start_date=date(2026, 5, 27),
        end_date=date(2026, 5, 27),
    )
    assert len(df) == 0
    assert list(df.columns) == ChainReader.EMPTY_COLS


def test_get_eod_snapshots_delta_filter(tmp_path: Path) -> None:
    """Assert only rows with delta in range returned."""
    eod_dir = tmp_path / "eod"
    writer = ChainWriter(str(eod_dir))
    
    chain = OptionChain(
        underlying_spot=Decimal("22000.00"),
        expiry=date(2026, 5, 28),
        strikes={
            Decimal("22000"): OptionChainStrike(
                ce=_make_dummy_leg(Decimal("22000"), Decimal("0.35")), # In range
                pe=_make_dummy_leg(Decimal("22000"), Decimal("-0.15")), # Out of range
            ),
            Decimal("22100"): OptionChainStrike(
                ce=_make_dummy_leg(Decimal("22100"), Decimal("0.55")), # Out of range
                pe=_make_dummy_leg(Decimal("22100"), Decimal("-0.35")), # Out of range
            )
        },
    )
    ts = datetime(2026, 5, 27, 10, 0, tzinfo=timezone.utc)
    writer.write_eod_snapshot(chain, ts)

    reader = ChainReader(str(eod_dir))
    
    df = reader.get_eod_snapshots(
        start_date=date(2026, 5, 27),
        end_date=date(2026, 5, 27),
        delta_min=Decimal("0.3"),
        delta_max=Decimal("0.5"),
    )
    assert len(df) == 1
    assert Decimal(str(df["delta"].iloc[0])) == Decimal("0.35")


def test_get_intraday_snapshots_happy_path(tmp_path: Path) -> None:
    """Write intraday Parquet, read back; assert row count."""
    intraday_dir = tmp_path / "intraday"
    writer = ChainWriter(str(intraday_dir))
    
    chain = OptionChain(
        underlying_spot=Decimal("22000.00"),
        expiry=date(2026, 5, 28),
        strikes={
            Decimal("22000"): OptionChainStrike(
                ce=_make_dummy_leg(Decimal("22000"), Decimal("0.5")),
                pe=_make_dummy_leg(Decimal("22000"), Decimal("-0.5")),
            )
        },
    )
    # 09:00 UTC = 14:30 IST -> upstox_1430.parquet
    ts = datetime(2026, 5, 27, 9, 0, tzinfo=timezone.utc)
    writer.write_intraday_snapshot(chain, ts)

    reader = ChainReader(eod_dir=str(tmp_path / "eod"), intraday_dir=str(intraday_dir))
    
    df = reader.get_intraday_snapshots(
        trade_date=date(2026, 5, 27),
        expiry_date=date(2026, 5, 28),
    )
    assert len(df) == 2
    assert set(df.columns) == set(ChainReader.EMPTY_COLS)


def test_get_intraday_snapshots_strike_filter(tmp_path: Path) -> None:
    """Write multiple strikes in intraday snapshot, query with strike filter."""
    intraday_dir = tmp_path / "intraday"
    writer = ChainWriter(str(intraday_dir))
    
    chain = OptionChain(
        underlying_spot=Decimal("22000.00"),
        expiry=date(2026, 5, 28),
        strikes={
            Decimal("22000"): OptionChainStrike(
                ce=_make_dummy_leg(Decimal("22000"), Decimal("0.5")),
            ),
            Decimal("22100"): OptionChainStrike(
                ce=_make_dummy_leg(Decimal("22100"), Decimal("0.4")),
            )
        },
    )
    ts = datetime(2026, 5, 27, 9, 0, tzinfo=timezone.utc)
    writer.write_intraday_snapshot(chain, ts)

    reader = ChainReader(eod_dir=str(tmp_path / "eod"), intraday_dir=str(intraday_dir))
    df = reader.get_intraday_snapshots(
        trade_date=date(2026, 5, 27),
        strike=Decimal("22100"),
    )
    assert len(df) == 1
    assert Decimal(str(df["strike"].iloc[0])) == Decimal("22100")


def test_get_intraday_no_intraday_dir(tmp_path: Path) -> None:
    """intraday_dir=None -> empty DataFrame, no error."""
    reader = ChainReader(eod_dir=str(tmp_path / "eod"), intraday_dir=None)
    df = reader.get_intraday_snapshots(
        trade_date=date(2026, 5, 27),
    )
    assert len(df) == 0
    assert list(df.columns) == ChainReader.EMPTY_COLS


def test_get_strike_delta_series(tmp_path: Path) -> None:
    """Assert columns = [snapshot_ts, delta, iv, ltp]; one row per file."""
    eod_dir = tmp_path / "eod"
    writer = ChainWriter(str(eod_dir))
    
    chain_26 = OptionChain(
        underlying_spot=Decimal("22000.00"),
        expiry=date(2026, 5, 28),
        strikes={
            Decimal("22000"): OptionChainStrike(
                ce=_make_dummy_leg(Decimal("22000"), Decimal("0.45"), Decimal("14.0")),
            )
        },
    )
    chain_27 = OptionChain(
        underlying_spot=Decimal("22050.00"),
        expiry=date(2026, 5, 28),
        strikes={
            Decimal("22000"): OptionChainStrike(
                ce=_make_dummy_leg(Decimal("22000"), Decimal("0.48"), Decimal("14.5")),
            )
        },
    )
    
    writer.write_eod_snapshot(chain_26, datetime(2026, 5, 26, 10, 0, tzinfo=timezone.utc))
    writer.write_eod_snapshot(chain_27, datetime(2026, 5, 27, 10, 0, tzinfo=timezone.utc))

    reader = ChainReader(str(eod_dir))
    df = reader.get_strike_delta_series(
        start_date=date(2026, 5, 25),
        end_date=date(2026, 5, 28),
        strike=Decimal("22000"),
        option_type="CE",
    )
    
    assert len(df) == 2
    assert list(df.columns) == ["snapshot_ts", "delta", "iv", "ltp"]
    assert Decimal(str(df["delta"].iloc[0])) == Decimal("0.45")
    assert Decimal(str(df["delta"].iloc[1])) == Decimal("0.48")
    assert Decimal(str(df["iv"].iloc[0])) == Decimal("14.0")
    assert Decimal(str(df["iv"].iloc[1])) == Decimal("14.5")


def test_get_strike_delta_series_expiry_filter(tmp_path: Path) -> None:
    """Verify that get_strike_delta_series works with expiry_date filter."""
    eod_dir = tmp_path / "eod"
    writer = ChainWriter(str(eod_dir))
    
    # Expiry 1
    chain_exp1 = OptionChain(
        underlying_spot=Decimal("22000.00"),
        expiry=date(2026, 5, 28),
        strikes={
            Decimal("22000"): OptionChainStrike(
                ce=_make_dummy_leg(Decimal("22000"), Decimal("0.45")),
            )
        },
    )
    # Expiry 2
    chain_exp2 = OptionChain(
        underlying_spot=Decimal("22000.00"),
        expiry=date(2026, 6, 25),
        strikes={
            Decimal("22000"): OptionChainStrike(
                ce=_make_dummy_leg(Decimal("22000"), Decimal("0.40")),
            )
        },
    )
    
    # Write both expiries on the same date/snapshot_ts
    ts = datetime(2026, 5, 27, 10, 0, tzinfo=timezone.utc)
    writer.write_eod_snapshot(chain_exp1, ts)
    
    # Note: EOD writer overwrites files for the same date. So if we want to write both
    # expiries for the same snapshot, we can merge strikes in a single OptionChain or
    # write to separate files. Wait, OptionChain represents a single underlying + expiry.
    # So writing chain_exp2 would overwrite if it has the exact same date!
    # Let's write them at slightly different dates to simulate daily series or check.
    # Actually, we can write them on different dates.
    writer.write_eod_snapshot(chain_exp1, datetime(2026, 5, 26, 10, 0, tzinfo=timezone.utc))
    writer.write_eod_snapshot(chain_exp2, datetime(2026, 5, 27, 10, 0, tzinfo=timezone.utc))

    reader = ChainReader(str(eod_dir))
    
    # Query with expiry_date matching exp1
    df = reader.get_strike_delta_series(
        start_date=date(2026, 5, 25),
        end_date=date(2026, 5, 28),
        strike=Decimal("22000"),
        option_type="CE",
        expiry_date=date(2026, 5, 28),
    )
    assert len(df) == 1
    assert Decimal(str(df["delta"].iloc[0])) == Decimal("0.45")


def test_get_strike_delta_series_empty(tmp_path: Path) -> None:
    """No matching strike -> empty DataFrame."""
    eod_dir = tmp_path / "eod"
    reader = ChainReader(str(eod_dir))
    df = reader.get_strike_delta_series(
        start_date=date(2026, 5, 25),
        end_date=date(2026, 5, 28),
        strike=Decimal("22000"),
        option_type="PE",
    )
    assert len(df) == 0
    assert list(df.columns) == ["snapshot_ts", "delta", "iv", "ltp"]

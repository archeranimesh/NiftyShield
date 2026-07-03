from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import pandas as pd
import pytest

from src.backtest.chain_writer import ChainWriter
from src.models.options import OptionChain, OptionChainStrike, OptionLeg

pytestmark = pytest.mark.slow


def _make_dummy_leg(strike: Decimal, delta: Decimal = Decimal("-0.25")) -> OptionLeg:
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
        iv=Decimal("15.5"),
        strike=strike,
    )


def test_write_eod_creates_correct_path(tmp_path: Path) -> None:
    """Assert returned path matches {base_dir}/2026/05/upstox_2026-05-27.parquet."""
    writer = ChainWriter(str(tmp_path))
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
    # 09:30 UTC = 15:00 IST, so date remains 2026-05-27
    ts = datetime(2026, 5, 27, 9, 30, tzinfo=timezone.utc)
    path = writer.write_eod_snapshot(chain, ts)
    expected_path = tmp_path / "2026" / "05" / "upstox_2026-05-27_default.parquet"
    assert path == expected_path
    assert path.exists()


def test_write_eod_idempotent(tmp_path: Path) -> None:
    """Write twice with same date; file count = 1, last write wins."""
    writer = ChainWriter(str(tmp_path))
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
    ts = datetime(2026, 5, 27, 9, 30, tzinfo=timezone.utc)
    path1 = writer.write_eod_snapshot(chain, ts)

    # Write a slightly modified one
    chain2 = OptionChain(
        underlying_spot=Decimal("22100.00"),
        expiry=date(2026, 5, 28),
        strikes={
            Decimal("22000"): OptionChainStrike(
                ce=_make_dummy_leg(Decimal("22000"), Decimal("0.5")),
                pe=_make_dummy_leg(Decimal("22000"), Decimal("-0.5")),
            )
        },
    )
    path2 = writer.write_eod_snapshot(chain2, ts)
    assert path1 == path2

    df = pd.read_parquet(path2)
    assert Decimal(str(df["spot"].iloc[0])) == Decimal("22100.000000")

    # Check that there is only 1 file in the directory
    dir_files = list((tmp_path / "2026" / "05").glob("*.parquet"))
    assert len(dir_files) == 1


def test_write_eod_roundtrip(tmp_path: Path) -> None:
    """Write then read back with pd.read_parquet; assert row count and spot value correct."""
    writer = ChainWriter(str(tmp_path))
    chain = OptionChain(
        underlying_spot=Decimal("22000.00"),
        expiry=date(2026, 5, 28),
        strikes={
            Decimal("22000"): OptionChainStrike(
                ce=_make_dummy_leg(Decimal("22000"), Decimal("0.5")),
                pe=_make_dummy_leg(Decimal("22000"), Decimal("-0.5")),
            ),
            Decimal("22100"): OptionChainStrike(
                ce=_make_dummy_leg(Decimal("22100"), Decimal("0.4")),
                pe=None,  # Only CE leg present
            ),
        },
    )
    ts = datetime(2026, 5, 27, 10, 0, tzinfo=timezone.utc)
    path = writer.write_eod_snapshot(chain, ts)

    df = pd.read_parquet(path)
    # Total legs: 2 from strike 22000 (CE+PE) and 1 from strike 22100 (CE) = 3 rows
    assert len(df) == 3
    assert Decimal(str(df["spot"].iloc[0])) == Decimal("22000.000000")
    assert df["option_type"].tolist() == ["CE", "PE", "CE"]
    assert df["strike"].tolist() == [Decimal("22000"), Decimal("22000"), Decimal("22100")]
    assert df["underlying"].tolist() == ["NIFTY_50"] * 3
    # Check that the timezone of snapshot_ts is preserved as UTC in read-back
    assert df["snapshot_ts"].dt.tz is not None


def test_write_intraday_path(tmp_path: Path) -> None:
    """Assert {base_dir}/2026/05/27/upstox_1430.parquet for 09:00 UTC (= 14:30 IST)."""
    writer = ChainWriter(str(tmp_path))
    chain = OptionChain(
        underlying_spot=Decimal("22000.00"),
        expiry=date(2026, 5, 28),
        strikes={
            Decimal("22000"): OptionChainStrike(
                ce=_make_dummy_leg(Decimal("22000"), Decimal("0.5")),
            )
        },
    )
    # 09:00 UTC -> 14:30 IST (9 + 5.5 = 14.5)
    ts = datetime(2026, 5, 27, 9, 0, tzinfo=timezone.utc)
    path = writer.write_intraday_snapshot(chain, ts)
    expected_path = tmp_path / "2026" / "05" / "27" / "upstox_1430_default.parquet"
    assert path == expected_path
    assert path.exists()


def test_write_intraday_idempotent(tmp_path: Path) -> None:
    """Same 5-min window, second write overwrites."""
    writer = ChainWriter(str(tmp_path))
    chain1 = OptionChain(
        underlying_spot=Decimal("22000.00"),
        expiry=date(2026, 5, 28),
        strikes={
            Decimal("22000"): OptionChainStrike(
                ce=_make_dummy_leg(Decimal("22000"), Decimal("0.5")),
            )
        },
    )
    chain2 = OptionChain(
        underlying_spot=Decimal("22050.00"),
        expiry=date(2026, 5, 28),
        strikes={
            Decimal("22000"): OptionChainStrike(
                ce=_make_dummy_leg(Decimal("22000"), Decimal("0.5")),
            )
        },
    )
    ts = datetime(2026, 5, 27, 9, 0, tzinfo=timezone.utc)
    path1 = writer.write_intraday_snapshot(chain1, ts)
    path2 = writer.write_intraday_snapshot(chain2, ts)

    assert path1 == path2
    df = pd.read_parquet(path2)
    assert Decimal(str(df["spot"].iloc[0])) == Decimal("22050.000000")

    dir_files = list((tmp_path / "2026" / "05" / "27").glob("*.parquet"))
    assert len(dir_files) == 1


def test_naive_ts_raises(tmp_path: Path) -> None:
    """datetime.utcnow() (naive) -> ValueError."""
    writer = ChainWriter(str(tmp_path))
    chain = OptionChain(
        underlying_spot=Decimal("22000.00"),
        expiry=date(2026, 5, 28),
        strikes={},
    )
    # Using timezone-naive datetime (intentionally — tests the guard)
    naive_ts = datetime.now()

    with pytest.raises(ValueError, match="snapshot_ts must be timezone-aware UTC"):
        writer.write_eod_snapshot(chain, naive_ts)

    with pytest.raises(ValueError, match="snapshot_ts must be timezone-aware UTC"):
        writer.write_intraday_snapshot(chain, naive_ts)


def test_empty_chain_writes_zero_rows(tmp_path: Path) -> None:
    """OptionChain with no strikes -> Parquet with 0 rows, no error."""
    writer = ChainWriter(str(tmp_path))
    chain = OptionChain(
        underlying_spot=Decimal("22000.00"),
        expiry=date(2026, 5, 28),
        strikes={},
    )
    ts = datetime(2026, 5, 27, 9, 30, tzinfo=timezone.utc)
    path = writer.write_eod_snapshot(chain, ts)

    assert path.exists()
    df = pd.read_parquet(path)
    assert len(df) == 0
    # Columns should still be defined
    assert "strike" in df.columns
    assert "option_type" in df.columns


def test_write_intraday_distinct_labels_no_collision(tmp_path: Path) -> None:
    """BUG-006 happy-path: same HHMM, different labels -> 2 distinct files, both readable.

    Reproduces the exact collision scenario: main() fetches monthly/quarterly/yearly
    expiries within the same 5-min run (same snapshot_ts -> same HHMM). Without the
    `label` param, the second write silently overwrote the first (BUG-006).
    """
    writer = ChainWriter(str(tmp_path))
    chain_monthly = OptionChain(
        underlying_spot=Decimal("22000.00"),
        expiry=date(2026, 6, 26),
        strikes={
            Decimal("22000"): OptionChainStrike(
                ce=_make_dummy_leg(Decimal("22000"), Decimal("0.5")),
            ),
        },
    )
    chain_yearly = OptionChain(
        underlying_spot=Decimal("22000.00"),
        expiry=date(2026, 12, 31),
        strikes={
            Decimal("22000"): OptionChainStrike(
                ce=_make_dummy_leg(Decimal("22000"), Decimal("0.5")),
            ),
        },
    )
    ts = datetime(2026, 5, 27, 9, 0, tzinfo=timezone.utc)

    path_monthly = writer.write_intraday_snapshot(chain_monthly, ts, label="monthly")
    path_yearly = writer.write_intraday_snapshot(chain_yearly, ts, label="yearly")

    assert path_monthly != path_yearly
    assert path_monthly.exists()
    assert path_yearly.exists()

    df_monthly = pd.read_parquet(path_monthly)
    df_yearly = pd.read_parquet(path_yearly)
    assert df_monthly["expiry_date"].iloc[0] == date(2026, 6, 26)
    assert df_yearly["expiry_date"].iloc[0] == date(2026, 12, 31)

    dir_files = list((tmp_path / "2026" / "05" / "27").glob("*.parquet"))
    assert len(dir_files) == 2


def test_write_intraday_same_label_still_idempotent(tmp_path: Path) -> None:
    """BUG-006 edge case: same HHMM + same label overwrites (idempotency preserved)."""
    writer = ChainWriter(str(tmp_path))
    chain1 = OptionChain(
        underlying_spot=Decimal("22000.00"),
        expiry=date(2026, 6, 26),
        strikes={
            Decimal("22000"): OptionChainStrike(
                ce=_make_dummy_leg(Decimal("22000"), Decimal("0.5")),
            ),
        },
    )
    chain2 = OptionChain(
        underlying_spot=Decimal("22050.00"),
        expiry=date(2026, 6, 26),
        strikes={
            Decimal("22000"): OptionChainStrike(
                ce=_make_dummy_leg(Decimal("22000"), Decimal("0.5")),
            ),
        },
    )
    ts = datetime(2026, 5, 27, 9, 0, tzinfo=timezone.utc)

    path1 = writer.write_intraday_snapshot(chain1, ts, label="monthly")
    path2 = writer.write_intraday_snapshot(chain2, ts, label="monthly")

    assert path1 == path2
    df = pd.read_parquet(path2)
    assert Decimal(str(df["spot"].iloc[0])) == Decimal("22050.000000")
    dir_files = list((tmp_path / "2026" / "05" / "27").glob("*.parquet"))
    assert len(dir_files) == 1


def test_write_eod_distinct_labels_no_collision(tmp_path: Path) -> None:
    """BUG-006 happy-path (EOD writer): same date, different labels -> 2 distinct files."""
    writer = ChainWriter(str(tmp_path))
    chain_monthly = OptionChain(
        underlying_spot=Decimal("22000.00"),
        expiry=date(2026, 6, 26),
        strikes={
            Decimal("22000"): OptionChainStrike(
                ce=_make_dummy_leg(Decimal("22000"), Decimal("0.5")),
            ),
        },
    )
    chain_quarterly = OptionChain(
        underlying_spot=Decimal("22000.00"),
        expiry=date(2026, 9, 24),
        strikes={
            Decimal("22000"): OptionChainStrike(
                ce=_make_dummy_leg(Decimal("22000"), Decimal("0.5")),
            ),
        },
    )
    ts = datetime(2026, 5, 27, 9, 30, tzinfo=timezone.utc)

    path_monthly = writer.write_eod_snapshot(chain_monthly, ts, label="monthly")
    path_quarterly = writer.write_eod_snapshot(chain_quarterly, ts, label="quarterly")

    assert path_monthly != path_quarterly
    assert path_monthly.exists()
    assert path_quarterly.exists()
    dir_files = list((tmp_path / "2026" / "05").glob("*.parquet"))
    assert len(dir_files) == 2


def test_decimal_precision(tmp_path: Path) -> None:
    """Read back a delta field; assert Decimal(str(val)) matches input to 6 dp."""
    writer = ChainWriter(str(tmp_path))
    delta_val = Decimal("0.123456")
    chain = OptionChain(
        underlying_spot=Decimal("22000.00"),
        expiry=date(2026, 5, 28),
        strikes={
            Decimal("22000"): OptionChainStrike(
                ce=_make_dummy_leg(Decimal("22000"), delta_val),
            )
        },
    )
    ts = datetime(2026, 5, 27, 9, 30, tzinfo=timezone.utc)
    path = writer.write_eod_snapshot(chain, ts)

    df = pd.read_parquet(path)
    assert len(df) == 1
    retrieved_delta = Decimal(str(df["delta"].iloc[0]))
    assert retrieved_delta == delta_val

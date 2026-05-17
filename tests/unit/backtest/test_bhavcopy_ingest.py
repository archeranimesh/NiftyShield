import pytest
from datetime import date
from decimal import Decimal
import zipfile
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock
from src.backtest.bhavcopy_ingest import parse_option_symbol, parse_bhavcopy, BhavRecord, download_bhavcopy

_ZIP_MAGIC = b"PK\x03\x04"

def test_parse_option_symbol_monthly():
    res = parse_option_symbol("NIFTY26APR24000PE")
    assert res["strike"] == Decimal("24000")
    assert res["option_type"] == "PE"

def test_parse_option_symbol_zero_padded():
    res = parse_option_symbol("NIFTY26APR08000CE")
    assert res["strike"] == Decimal("8000")
    assert res["option_type"] == "CE"

def test_parse_option_symbol_weekly():
    res = parse_option_symbol("NIFTY2641724000PE")
    assert res["strike"] == Decimal("24000")
    assert res["option_type"] == "PE"
    assert res["expiry"] == date(2026, 4, 17)

def test_parse_option_symbol_unknown_raises():
    with pytest.raises(ValueError):
        parse_option_symbol("NIFTYGARBAGE")

@pytest.fixture
def bhavcopy_zip(tmp_path):
    csv_path = Path("tests/fixtures/responses/bhavcopy/synthetic_bhavcopy.csv")
    zip_path = tmp_path / "bhavcopy.csv.zip"
    with zipfile.ZipFile(zip_path, 'w') as zf:
        zf.write(csv_path, arcname="bhavcopy.csv")
    return zip_path

def test_parse_bhavcopy_filters_to_nifty(bhavcopy_zip):
    records = parse_bhavcopy(bhavcopy_zip, underlying="NIFTY", include_futures=True)
    
    # 1 OPTIDX CE, 1 OPTIDX PE, 1 FUTIDX. 
    # Missing: BANKNIFTY, RELIANCE, corrupted CE strike 0.
    assert len(records) == 3
    for r in records:
        assert r.underlying == "NIFTY"
        assert r.instrument in ("OPTIDX", "FUTIDX")

def test_parse_bhavcopy_decimal_fields(bhavcopy_zip):
    records = parse_bhavcopy(bhavcopy_zip, underlying="NIFTY")
    for r in records:
        assert isinstance(r.open, Decimal)
        assert isinstance(r.high, Decimal)
        assert isinstance(r.low, Decimal)
        assert isinstance(r.close, Decimal)
        assert isinstance(r.settle_price, Decimal)

def test_parse_bhavcopy_empty_on_no_match(bhavcopy_zip):
    records = parse_bhavcopy(bhavcopy_zip, underlying="SENSEX")
    assert len(records) == 0

def test_parse_bhavcopy_corrupt_zip(tmp_path):
    corrupt_zip = tmp_path / "corrupt.zip"
    corrupt_zip.write_bytes(b"not a zip file")
    with pytest.raises(ValueError, match="Corrupt or unreadable ZIP file"):
        parse_bhavcopy(corrupt_zip)

from src.backtest.bhavcopy_ingest import write_to_parquet
from src.backtest.bhavcopy_loader import load_options_ohlcv
import pyarrow.parquet as pq

def test_idempotency_skip_existing_date(bhavcopy_zip, tmp_path):
    records = parse_bhavcopy(bhavcopy_zip, underlying="NIFTY")
    assert len(records) > 0
    trade_date = records[0].trade_date
    
    # First write
    write_to_parquet(records, trade_date, dest_dir=tmp_path)
    
    # Check rows
    year = trade_date.strftime("%Y")
    month = trade_date.strftime("%m")
    parquet_path = tmp_path / year / month / f"nifty_{year}_{month}.parquet"
    assert parquet_path.exists()
    
    first_table = pq.read_table(parquet_path)
    initial_rows = first_table.num_rows
    
    # Second write
    write_to_parquet(records, trade_date, dest_dir=tmp_path)
    
    # Check rows are unchanged
    second_table = pq.read_table(parquet_path)
    assert second_table.num_rows == initial_rows

def test_load_options_ohlcv_date_filter(bhavcopy_zip, tmp_path):
    records = parse_bhavcopy(bhavcopy_zip, underlying="NIFTY", include_futures=True)
    trade_date = records[0].trade_date
    write_to_parquet(records, trade_date, dest_dir=tmp_path)
    
    # Load with valid date
    df = load_options_ohlcv(underlying="NIFTY", start=trade_date, end=trade_date, data_dir=tmp_path)
    assert len(df) == 3
    assert (df['trade_date'] == trade_date).all()
    
    # Load outside date
    outside_date = date(1999, 1, 1)
    df_empty = load_options_ohlcv(underlying="NIFTY", start=outside_date, end=outside_date, data_dir=tmp_path)
    assert len(df_empty) == 0

def test_load_options_ohlcv_empty_on_no_data(tmp_path):
    df = load_options_ohlcv(underlying="NIFTY", start=date(2020, 1, 1), end=date(2020, 1, 31), data_dir=tmp_path)
    assert len(df) == 0

from scripts.bhavcopy_bootstrap import main as bootstrap_main
import urllib.error
from unittest.mock import patch, MagicMock

@patch('scripts.bhavcopy_bootstrap.download_bhavcopy')
@patch('scripts.bhavcopy_bootstrap.time.sleep')
def test_bhavcopy_bootstrap_404_handling(mock_sleep, mock_download, tmp_path):
    mock_download.side_effect = FileNotFoundError("NSE returned 404")
    
    args = [
        "--start", "2024-04-24",
        "--end", "2024-04-24",
        "--dest", str(tmp_path)
    ]
    
    # Should not raise exception
    bootstrap_main(args)
    
    assert mock_download.call_count == 1
    mock_sleep.assert_called_once_with(1.0)

@patch('scripts.bhavcopy_bootstrap.download_bhavcopy')
@patch('scripts.bhavcopy_bootstrap.time.sleep')
def test_bhavcopy_bootstrap_error_handling(mock_sleep, mock_download, tmp_path):
    mock_download.side_effect = IOError("HTTP Error 500")
    
    args = [
        "--start", "2024-04-24",
        "--end", "2024-04-24",
        "--dest", str(tmp_path)
    ]
    
    # Should not raise exception
    bootstrap_main(args)
    
    assert mock_download.call_count == 1
    mock_sleep.assert_called_once_with(1.0)


# ---------------------------------------------------------------------------
# UDiFF format tests
# ---------------------------------------------------------------------------

@pytest.fixture
def udiff_bhavcopy_zip(tmp_path):
    csv_path = Path("tests/fixtures/responses/bhavcopy/udiff_bhavcopy.csv")
    zip_path = tmp_path / "udiff_bhavcopy.csv.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.write(csv_path, arcname="udiff_bhavcopy.csv")
    return zip_path


def test_parse_bhavcopy_udiff_format_detected(udiff_bhavcopy_zip):
    """UDiFF header (TradDt) routes to the UDiFF parser, not the legacy one."""
    records = parse_bhavcopy(udiff_bhavcopy_zip, underlying="NIFTY", include_futures=True)
    # 1 CE + 1 PE + 1 FUTIDX; BANKNIFTY and corrupted-zero-strike CE are excluded
    assert len(records) == 3


def test_parse_bhavcopy_udiff_filters_underlying(udiff_bhavcopy_zip):
    records = parse_bhavcopy(udiff_bhavcopy_zip, underlying="NIFTY")
    for r in records:
        assert r.underlying == "NIFTY"
        assert r.instrument in ("OPTIDX", "OPTSTK")


def test_parse_bhavcopy_udiff_instrument_mapping(udiff_bhavcopy_zip):
    """IDO → OPTIDX, IDF → FUTIDX — model canonical strings preserved."""
    records = parse_bhavcopy(udiff_bhavcopy_zip, underlying="NIFTY", include_futures=True)
    instruments = {r.instrument for r in records}
    assert "OPTIDX" in instruments
    assert "FUTIDX" in instruments


def test_parse_bhavcopy_udiff_decimal_fields(udiff_bhavcopy_zip):
    records = parse_bhavcopy(udiff_bhavcopy_zip, underlying="NIFTY")
    for r in records:
        for field in ("open", "high", "low", "close", "settle_price", "strike"):
            assert isinstance(getattr(r, field), Decimal), f"{field} is not Decimal"


def test_parse_bhavcopy_udiff_date_parsing(udiff_bhavcopy_zip):
    records = parse_bhavcopy(udiff_bhavcopy_zip, underlying="NIFTY")
    for r in records:
        assert r.trade_date == date(2025, 1, 2)
        assert r.expiry == date(2025, 1, 30)


def test_parse_bhavcopy_udiff_futures_excluded_by_default(udiff_bhavcopy_zip):
    records = parse_bhavcopy(udiff_bhavcopy_zip, underlying="NIFTY", include_futures=False)
    assert all(r.instrument != "FUTIDX" for r in records)


def test_parse_bhavcopy_udiff_no_match(udiff_bhavcopy_zip):
    records = parse_bhavcopy(udiff_bhavcopy_zip, underlying="SENSEX")
    assert len(records) == 0


# ---------------------------------------------------------------------------
# download_bhavcopy: UDiFF-first with legacy fallback
# ---------------------------------------------------------------------------

def _fake_zip_response(status_code: int = 200, is_zip: bool = True) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.content = _ZIP_MAGIC + b"\x00" * 16 if is_zip else b"<html>blocked</html>"
    return resp


def _patched_session(mock_session_cls: MagicMock) -> MagicMock:
    """Return the inner session mock wired up to the Session constructor."""
    session = MagicMock()
    mock_session_cls.return_value = session
    return session


# Set NSE_COOKIE so _build_session skips the pre-warm GET — keeps side_effect
# counts deterministic (no extra call consumed by the warm-up).
_SKIP_WARMUP = {"NSE_COOKIE": "test_cookie"}


@patch("src.backtest.bhavcopy_ingest.requests.Session")
@patch.dict("os.environ", _SKIP_WARMUP)
def test_download_bhavcopy_udiff_success(mock_session_cls, tmp_path):
    session = _patched_session(mock_session_cls)
    session.get.return_value = _fake_zip_response(200, is_zip=True)

    result = download_bhavcopy(date(2025, 1, 2), tmp_path)

    assert "BhavCopy_NSE_FO_0_0_0_20250102_F_0000" in result.name
    assert result.exists()
    # Only one GET: UDiFF succeeded on first try
    assert session.get.call_count == 1


@patch("src.backtest.bhavcopy_ingest.requests.Session")
@patch.dict("os.environ", _SKIP_WARMUP)
def test_download_bhavcopy_udiff_404_falls_back_to_legacy(mock_session_cls, tmp_path):
    session = _patched_session(mock_session_cls)
    session.get.side_effect = [
        _fake_zip_response(404, is_zip=False),  # UDiFF 404
        _fake_zip_response(200, is_zip=True),   # legacy success
    ]

    result = download_bhavcopy(date(2024, 4, 25), tmp_path)

    assert result.name.startswith("fo")  # legacy filename pattern
    assert result.exists()
    assert session.get.call_count == 2


@patch("src.backtest.bhavcopy_ingest.requests.Session")
@patch.dict("os.environ", _SKIP_WARMUP)
def test_download_bhavcopy_both_404_raises(mock_session_cls, tmp_path):
    session = _patched_session(mock_session_cls)
    session.get.side_effect = [
        _fake_zip_response(404, is_zip=False),  # UDiFF 404
        _fake_zip_response(404, is_zip=False),  # legacy 404 → holiday
    ]

    with pytest.raises(FileNotFoundError, match="404"):
        download_bhavcopy(date(2025, 1, 1), tmp_path)


@patch("src.backtest.bhavcopy_ingest.requests.Session")
@patch.dict("os.environ", _SKIP_WARMUP)
def test_download_bhavcopy_udiff_akamai_block_raises(mock_session_cls, tmp_path):
    session = _patched_session(mock_session_cls)
    session.get.return_value = _fake_zip_response(200, is_zip=False)  # HTML, not ZIP

    with pytest.raises(IOError, match="not a ZIP"):
        download_bhavcopy(date(2025, 1, 2), tmp_path)


@patch('scripts.bhavcopy_bootstrap.download_bhavcopy')
@patch('scripts.bhavcopy_bootstrap.time.sleep')
def test_bhavcopy_integration_end_to_end(mock_sleep, mock_download, bhavcopy_zip, tmp_path):
    mock_download.return_value = bhavcopy_zip
    
    args = [
        "--start", "2024-04-25",
        "--end", "2024-04-25",
        "--dest", str(tmp_path),
        "--include-futures"
    ]
    
    bootstrap_main(args)
    
    # 1. Options Parquet
    options_df = load_options_ohlcv("NIFTY", date(2024, 4, 25), date(2024, 4, 25), tmp_path / "options_ohlcv")
    assert len(options_df) == 2  # 1 CE, 1 PE for NIFTY
    
    first_open = options_df.iloc[0]['open']
    assert isinstance(first_open, Decimal)
    
    assert str(options_df['volume'].dtype).startswith('int')
    
    # 2. Futures Parquet
    futures_df = load_options_ohlcv("NIFTY", date(2024, 4, 25), date(2024, 4, 25), tmp_path / "futures_ohlcv")
    assert len(futures_df) == 1
    assert futures_df.iloc[0]['instrument'] == 'FUTIDX'
    assert futures_df.iloc[0]['strike'] == Decimal("0")
    assert futures_df.iloc[0]['option_type'] == "XX"

def test_write_to_parquet_lineage_metadata(bhavcopy_zip, tmp_path):
    records = parse_bhavcopy(bhavcopy_zip, underlying="NIFTY")
    assert len(records) > 0
    trade_date = records[0].trade_date
    
    write_to_parquet(records, trade_date, dest_dir=tmp_path)
    
    year = trade_date.strftime("%Y")
    month = trade_date.strftime("%m")
    parquet_path = tmp_path / year / month / f"nifty_{year}_{month}.parquet"
    
    table = pq.read_table(parquet_path)
    metadata = table.schema.metadata
    
    assert metadata is not None
    assert b"git_commit" in metadata
    assert b"run_timestamp" in metadata
    assert len(metadata[b"git_commit"]) > 0

@patch("src.backtest.bhavcopy_ingest.subprocess.check_output")
def test_write_to_parquet_metadata_git_failure(mock_subprocess, bhavcopy_zip, tmp_path):
    import subprocess
    mock_subprocess.side_effect = subprocess.CalledProcessError(1, "git")
    
    records = parse_bhavcopy(bhavcopy_zip, underlying="NIFTY")
    trade_date = records[0].trade_date
    
    # Should not raise exception
    write_to_parquet(records, trade_date, dest_dir=tmp_path)
    
    year = trade_date.strftime("%Y")
    month = trade_date.strftime("%m")
    parquet_path = tmp_path / year / month / f"nifty_{year}_{month}.parquet"
    
    table = pq.read_table(parquet_path)
    metadata = table.schema.metadata
    
    assert metadata is not None
    assert metadata[b"git_commit"] == b"unknown"
    assert b"run_timestamp" in metadata

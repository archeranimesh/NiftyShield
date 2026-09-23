import zipfile
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch

import pyarrow.parquet as pq
import pytest

from src.backtest.equity_bhavcopy_ingest import (
    download_equity_bhavcopy,
    parse_equity_bhavcopy,
    write_equity_to_parquet,
)

_ZIP_MAGIC = b"PK\x03\x04"


@pytest.fixture
def equity_bhavcopy_zip(tmp_path):
    csv_path = Path("tests/fixtures/responses/bhavcopy/synthetic_equity_bhavcopy.csv")
    zip_path = tmp_path / "equity_bhavcopy.csv.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.write(csv_path, arcname="equity_bhavcopy.csv")
    return zip_path


def test_parse_equity_bhavcopy_filters_to_symbol_set(equity_bhavcopy_zip):
    records = parse_equity_bhavcopy(equity_bhavcopy_zip, symbols={"UNIPARTS", "RELIANCE"})

    # INFY excluded (not in symbol set), TATASTEEL excluded (BE series, not EQ).
    assert len(records) == 2
    symbols = {r.symbol for r in records}
    assert symbols == {"UNIPARTS", "RELIANCE"}


def test_parse_equity_bhavcopy_decimal_fields(equity_bhavcopy_zip):
    records = parse_equity_bhavcopy(equity_bhavcopy_zip, symbols={"UNIPARTS"})
    assert len(records) == 1
    assert isinstance(records[0].close, Decimal)
    assert records[0].close == Decimal("855.50")
    assert records[0].trade_date == date(2026, 6, 12)


def test_parse_equity_bhavcopy_empty_on_no_match(equity_bhavcopy_zip):
    records = parse_equity_bhavcopy(equity_bhavcopy_zip, symbols={"SOMEOTHERSTOCK"})
    assert records == []


def test_parse_equity_bhavcopy_corrupt_zip(tmp_path):
    corrupt_zip = tmp_path / "corrupt.zip"
    corrupt_zip.write_bytes(b"not a zip file")
    with pytest.raises(ValueError, match="Corrupt or unreadable ZIP file"):
        parse_equity_bhavcopy(corrupt_zip, symbols={"UNIPARTS"})


def _fake_response(status_code: int = 200, is_zip: bool = True) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.content = _ZIP_MAGIC + b"\x00" * 16 if is_zip else b"<html>blocked</html>"
    return resp


def _patched_session(mock_session_cls: MagicMock) -> MagicMock:
    session = MagicMock()
    mock_session_cls.return_value = session
    return session


# Set NSE_COOKIE so _build_session skips the pre-warm GET — keeps call counts
# deterministic (no extra call consumed by the warm-up).
_SKIP_WARMUP = {"NSE_COOKIE": "test_cookie"}


@patch("src.backtest.equity_bhavcopy_ingest.requests.Session")
@patch.dict("os.environ", _SKIP_WARMUP)
def test_download_equity_bhavcopy_success(mock_session_cls, tmp_path):
    session = _patched_session(mock_session_cls)
    session.get.return_value = _fake_response(200, is_zip=True)

    result = download_equity_bhavcopy(date(2026, 6, 12), tmp_path)

    assert "BhavCopy_NSE_CM_0_0_0_20260612_F_0000" in result.name
    assert result.exists()
    assert session.get.call_count == 1


@patch("src.backtest.equity_bhavcopy_ingest.requests.Session")
@patch.dict("os.environ", _SKIP_WARMUP)
def test_download_equity_bhavcopy_404_raises(mock_session_cls, tmp_path):
    session = _patched_session(mock_session_cls)
    session.get.return_value = _fake_response(404, is_zip=False)

    with pytest.raises(FileNotFoundError, match="404"):
        download_equity_bhavcopy(date(2026, 6, 13), tmp_path)


def test_write_equity_to_parquet_idempotent_append(equity_bhavcopy_zip, tmp_path):
    records = parse_equity_bhavcopy(equity_bhavcopy_zip, symbols={"UNIPARTS", "RELIANCE"})
    month_date = date(2026, 6, 1)

    write_equity_to_parquet(records, month_date, tmp_path)
    parquet_path = tmp_path / "2026" / "06" / "equity_2026_06.parquet"
    assert parquet_path.exists()
    table = pq.read_table(parquet_path)
    assert table.num_rows == 2

    # Second write of the same trade_date is a no-op (idempotent skip).
    write_equity_to_parquet(records, month_date, tmp_path)
    table_after = pq.read_table(parquet_path)
    assert table_after.num_rows == 2


def test_write_equity_to_parquet_empty_records_noop(tmp_path):
    write_equity_to_parquet([], date(2026, 6, 1), tmp_path)
    assert not (tmp_path / "2026").exists()

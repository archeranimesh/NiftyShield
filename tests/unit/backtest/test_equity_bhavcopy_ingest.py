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
    parse_index_bhavcopy,
    write_equity_to_parquet,
    write_index_to_parquet,
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


@pytest.fixture
def index_bhavcopy_csv(tmp_path):
    csv_path = Path("tests/fixtures/responses/bhavcopy/synthetic_index_close.csv")
    test_path = tmp_path / "ind_close_all_12062026.csv"
    test_path.write_text(csv_path.read_text(encoding="utf-8"), encoding="utf-8")
    return test_path


def test_parse_index_bhavcopy_happy_path(index_bhavcopy_csv):
    record = parse_index_bhavcopy(index_bhavcopy_csv)
    assert record is not None
    assert record.trade_date == date(2026, 6, 12)
    assert record.close == Decimal("23398.90")


def test_parse_index_bhavcopy_missing_row(tmp_path):
    # CSV without "Nifty 50" row
    content = (
        "Index Name,Index Date,Open Index Value,High Index Value,Low Index Value,Closing Index Value,Points Change(Absolute),Points Change(%),Volume,Turnover (Rs. Cr.),P/E,P/B,Div Yield\n"
        '"Nifty Next 50",12-06-2026,71556.70,72121.25,71363.30,71926.85,735.65,1.03,812002165,22115.65,26.79,5.54,1.13\n'
    )
    test_path = tmp_path / "ind_close_all_12062026.csv"
    test_path.write_text(content, encoding="utf-8")
    record = parse_index_bhavcopy(test_path)
    assert record is None


def test_write_index_to_parquet_idempotent_append(index_bhavcopy_csv, tmp_path):
    record = parse_index_bhavcopy(index_bhavcopy_csv)
    month_date = date(2026, 6, 1)

    write_index_to_parquet([record], month_date, tmp_path)
    parquet_path = tmp_path / "2026" / "06" / "index_2026_06.parquet"
    assert parquet_path.exists()
    table = pq.read_table(parquet_path)
    assert table.num_rows == 1

    # Second write is a no-op
    write_index_to_parquet([record], month_date, tmp_path)
    table_after = pq.read_table(parquet_path)
    assert table_after.num_rows == 1


@patch("scripts.pipeline.equity_bhavcopy_bootstrap.time.sleep")
@patch("scripts.pipeline.equity_bhavcopy_bootstrap.MVPStore")
@patch("scripts.pipeline.equity_bhavcopy_bootstrap.get_nse_holidays")
@patch("scripts.pipeline.equity_bhavcopy_bootstrap.download_index_bhavcopy")
@patch("scripts.pipeline.equity_bhavcopy_bootstrap.download_equity_bhavcopy")
def test_bootstrap_main_happy_path(
    mock_dl_equity,
    mock_dl_idx,
    mock_holidays,
    mock_store_cls,
    mock_sleep,
    equity_bhavcopy_zip,
    index_bhavcopy_csv,
    tmp_path,
):
    from scripts.pipeline.equity_bhavcopy_bootstrap import main

    mock_store_cls.return_value.get_distinct_symbols.return_value = {"UNIPARTS"}
    mock_holidays.return_value = {date(2026, 6, 12)}  # Friday, holiday

    mock_dl_equity.return_value = equity_bhavcopy_zip
    mock_dl_idx.return_value = index_bhavcopy_csv

    dest_dir = tmp_path / "offline"

    main(
        [
            "--start",
            "2026-06-11",
            "--end",
            "2026-06-15",
            "--dest",
            str(dest_dir),
        ]
    )

    assert mock_dl_equity.call_count == 2
    # 12 is skipped (holiday), 13 and 14 are skipped (weekend). Called for 11 and 15.
    assert mock_dl_equity.call_args_list[0][0][0] == date(2026, 6, 11)
    assert mock_dl_equity.call_args_list[1][0][0] == date(2026, 6, 15)

    assert mock_dl_idx.call_count == 2
    assert mock_dl_idx.call_args_list[0][0][0] == date(2026, 6, 11)
    assert mock_dl_idx.call_args_list[1][0][0] == date(2026, 6, 15)

    # Since the fixture data has TradDt = 2026-06-12 and write functions are idempotent,
    # the second loop's write is a no-op, resulting in exactly 1 batch of data being written.
    eq_parquet = dest_dir / "equity_ohlcv" / "2026" / "06" / "equity_2026_06.parquet"
    assert eq_parquet.exists()

    idx_parquet = dest_dir / "nifty_index" / "2026" / "06" / "index_2026_06.parquet"
    assert idx_parquet.exists()

    eq_table = pq.read_table(eq_parquet)
    assert eq_table.num_rows == 1  # 1 record for UNIPARTS

    idx_table = pq.read_table(idx_parquet)
    assert idx_table.num_rows == 1  # 1 record for Nifty 50


@patch("scripts.pipeline.equity_bhavcopy_bootstrap.time.sleep")
@patch("scripts.pipeline.equity_bhavcopy_bootstrap.MVPStore")
@patch("scripts.pipeline.equity_bhavcopy_bootstrap.get_nse_holidays")
@patch("scripts.pipeline.equity_bhavcopy_bootstrap.download_index_bhavcopy")
@patch("scripts.pipeline.equity_bhavcopy_bootstrap.download_equity_bhavcopy")
def test_bootstrap_main_filenotfound_error_skip(
    mock_dl_equity,
    mock_dl_idx,
    mock_holidays,
    mock_store_cls,
    mock_sleep,
    equity_bhavcopy_zip,
    index_bhavcopy_csv,
    tmp_path,
):
    from scripts.pipeline.equity_bhavcopy_bootstrap import main

    mock_store_cls.return_value.get_distinct_symbols.return_value = {"UNIPARTS"}
    mock_holidays.return_value = set()

    def side_effect_equity(dt, dest_dir):
        if dt == date(2026, 6, 11):
            raise FileNotFoundError("404")
        return equity_bhavcopy_zip

    mock_dl_equity.side_effect = side_effect_equity
    mock_dl_idx.return_value = index_bhavcopy_csv

    dest_dir = tmp_path / "offline"

    main(
        [
            "--start",
            "2026-06-11",
            "--end",
            "2026-06-12",  # Thursday to Friday
            "--dest",
            str(dest_dir),
        ]
    )

    assert mock_dl_equity.call_count == 2
    # If equity download raises FileNotFoundError, it logs and skips, so index download is not called for that day
    assert mock_dl_idx.call_count == 1
    assert mock_dl_idx.call_args_list[0][0][0] == date(2026, 6, 12)

    eq_parquet = dest_dir / "equity_ohlcv" / "2026" / "06" / "equity_2026_06.parquet"
    assert eq_parquet.exists()

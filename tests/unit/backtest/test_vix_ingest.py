from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
import requests

from src.backtest.vix_ingest import (
    fetch_vix_latest,
    ingest_vix_from_api,
    ingest_vix_from_csv,
    load_vix_series,
)
from src.client.exceptions import DataFetchError

pytestmark = pytest.mark.slow


@pytest.fixture
def fixture_csv():
    return Path("tests/fixtures/vix/india_vix_sample.csv")


def test_ingest_csv_writes_parquet(fixture_csv, tmp_path):
    out_dir = tmp_path / "vix"
    new_rows = ingest_vix_from_csv(fixture_csv, out_dir)

    assert new_rows == 5
    parquet_path = out_dir / "2024" / "india_vix_2024.parquet"
    assert parquet_path.exists()

    df = pd.read_parquet(parquet_path)
    assert set(df.columns) == {"date", "open", "high", "low", "close"}
    assert len(df) == 5
    assert "datetime64" in str(df["date"].dtype)


def test_ingest_csv_resumable(fixture_csv, tmp_path):
    out_dir = tmp_path / "vix"
    # First write
    ingest_vix_from_csv(fixture_csv, out_dir)
    # Second write (same data)
    new_rows = ingest_vix_from_csv(fixture_csv, out_dir)

    assert new_rows == 0
    parquet_path = out_dir / "2024" / "india_vix_2024.parquet"
    df = pd.read_parquet(parquet_path)
    assert len(df) == 5


def test_ingest_csv_partial_overlap(fixture_csv, tmp_path):
    out_dir = tmp_path / "vix"
    ingest_vix_from_csv(fixture_csv, out_dir)

    # Create an extended CSV
    extended_csv = tmp_path / "extended.csv"
    content = (
        "Date,Open,High,Low,Close,Prev Close,Change,%Change\n"
        "03-Jan-2024,15.10,15.80,14.90,15.40,15.10,0.30,1.99\n"
        "04-Jan-2024,15.40,16.00,15.20,15.70,15.40,0.30,1.95\n"
        "05-Jan-2024,15.70,16.30,15.50,16.00,15.70,0.30,1.91\n"
        "06-Jan-2024,16.00,16.60,15.80,16.30,16.00,0.30,1.87\n"
        "07-Jan-2024,16.30,16.90,16.10,16.60,16.30,0.30,1.84\n"
    )
    extended_csv.write_text(content)

    new_rows = ingest_vix_from_csv(extended_csv, out_dir)
    assert new_rows == 2

    df = pd.read_parquet(out_dir / "2024" / "india_vix_2024.parquet")
    assert len(df) == 7
    assert df["date"].iloc[-1] == pd.Timestamp("2024-01-07")


def test_load_vix_series_returns_sorted_series(fixture_csv, tmp_path):
    out_dir = tmp_path / "vix"
    ingest_vix_from_csv(fixture_csv, out_dir)

    series = load_vix_series(out_dir)
    assert isinstance(series, pd.Series)
    assert len(series) == 5
    assert list(series.index) == sorted(series.index)
    assert isinstance(series.index[0], date)
    assert series.iloc[0] == 14.80  # Close of 01-Jan-2024


def test_load_vix_series_empty_dir_returns_empty(tmp_path):
    series = load_vix_series(tmp_path)
    assert isinstance(series, pd.Series)
    assert series.empty


@patch("src.backtest.vix_ingest.requests.get")
def test_ingest_api_skips_dates_already_present(mock_get, tmp_path):
    out_dir = tmp_path / "vix"
    # Pre-populate 2024-01-01 to 2024-01-05
    initial_df = pd.DataFrame(
        {
            "date": pd.to_datetime(
                ["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"]
            ),
            "open": [14.5, 14.8, 15.1, 15.4, 15.7],
            "high": [15.2, 15.5, 15.8, 16.0, 16.3],
            "low": [14.1, 14.6, 14.9, 15.2, 15.5],
            "close": [14.8, 15.1, 15.4, 15.7, 16.0],
        }
    )
    year_dir = out_dir / "2024"
    year_dir.mkdir(parents=True)
    initial_df.to_parquet(year_dir / "india_vix_2024.parquet")

    # Mock API response for 2024-01-06 to 2024-01-08
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "data": {
            "candles": [
                ["2024-01-06T00:00:00+05:30", 16.0, 16.6, 15.8, 16.3, 0, 0],
                ["2024-01-07T00:00:00+05:30", 16.3, 16.9, 16.1, 16.6, 0, 0],
                ["2024-01-08T00:00:00+05:30", 16.6, 17.2, 16.4, 16.9, 0, 0],
            ]
        }
    }
    mock_get.return_value = mock_response

    new_rows = ingest_vix_from_api(
        from_date=date(2024, 1, 1), to_date=date(2024, 1, 8), out_dir=out_dir, token="test_token"
    )

    assert new_rows == 3
    # Check that API was called with from_date=2024-01-06
    args, kwargs = mock_get.call_args
    assert "NSE_INDEX%7CIndia%20VIX" in args[0]
    assert kwargs["params"]["from_date"] == "2024-01-06"
    assert kwargs["timeout"] == 10

    df = pd.read_parquet(year_dir / "india_vix_2024.parquet")
    assert len(df) == 8
    assert df["date"].iloc[-1] == pd.Timestamp("2024-01-08")


@patch("src.backtest.vix_ingest.requests.get")
def test_fetch_vix_latest_returns_most_recent_close(mock_get):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "data": {
            "candles": [
                ["2026-05-15T00:00:00+05:30", 14.5, 15.2, 14.1, 14.80, 0, 0],
                ["2026-05-14T00:00:00+05:30", 14.2, 14.9, 13.8, 14.50, 0, 0],
            ]
        }
    }
    mock_get.return_value = mock_response

    result = fetch_vix_latest(token="test_token")

    assert result == 14.80  # close of the most recent (index 0) candle


@patch("src.backtest.vix_ingest.requests.get")
def test_fetch_vix_latest_returns_none_on_empty_candles(mock_get):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"data": {"candles": []}}
    mock_get.return_value = mock_response

    assert fetch_vix_latest(token="test_token") is None


def test_fetch_vix_latest_returns_none_when_no_token():
    # No token passed, no env var set
    with patch.dict("os.environ", {}, clear=True):
        assert fetch_vix_latest(token=None) is None


@patch("src.backtest.vix_ingest.requests.get")
def test_fetch_vix_latest_returns_none_on_network_error(mock_get):
    mock_get.side_effect = requests.RequestException("timeout")

    assert fetch_vix_latest(token="test_token") is None


@patch("src.backtest.vix_ingest.requests.get")
def test_ingest_api_raises_data_fetch_error_on_network_failure(mock_get, tmp_path):
    mock_get.side_effect = requests.RequestException("Connection timeout")

    with pytest.raises(DataFetchError, match="VIX candle fetch failed"):
        ingest_vix_from_api(
            from_date=date(2024, 1, 1),
            to_date=date(2024, 1, 8),
            out_dir=tmp_path,
            token="test_token",
        )

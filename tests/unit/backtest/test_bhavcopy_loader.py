from __future__ import annotations

import inspect
from datetime import date
from unittest.mock import patch

import pandas as pd
import pytest

from src.backtest.bhavcopy_loader import load_options_ohlcv
from src.backtest.constants import DEFAULT_DATA_DIR

pytestmark = pytest.mark.slow


def test_load_options_ohlcv_default_value():
    """Verify that the function's default data_dir is DEFAULT_DATA_DIR."""
    sig = inspect.signature(load_options_ohlcv)
    assert sig.parameters["data_dir"].default == DEFAULT_DATA_DIR


def test_load_options_ohlcv_happy_path(tmp_path):
    # Setup: Create a dummy parquet file
    data_dir = tmp_path / "options_ohlcv"
    month_dir = data_dir / "2024" / "04"
    month_dir.mkdir(parents=True)
    parquet_file = month_dir / "nifty_2024_04.parquet"

    # Create a dummy DataFrame and save to parquet
    df = pd.DataFrame(
        {
            "trade_date": [date(2024, 4, 24), date(2024, 4, 25)],
            "underlying": ["NIFTY", "NIFTY"],
            "close": [22000.0, 22100.0],
        }
    )
    df.to_parquet(parquet_file)

    # Test
    result = load_options_ohlcv(
        underlying="NIFTY", start=date(2024, 4, 24), end=date(2024, 4, 24), data_dir=data_dir
    )

    assert len(result) == 1
    assert result.iloc[0]["trade_date"] == date(2024, 4, 24)
    assert result.iloc[0]["underlying"] == "NIFTY"


@patch("pyarrow.parquet.ParquetDataset")
def test_load_options_ohlcv_error_path(mock_dataset, tmp_path, caplog):
    # Setup: Create a dummy directory to trigger the read attempt
    data_dir = tmp_path / "options_ohlcv"
    month_dir = data_dir / "2024" / "04"
    month_dir.mkdir(parents=True)
    parquet_file = month_dir / "nifty_2024_04.parquet"
    parquet_file.touch()

    # Mock ParquetDataset to raise an exception
    mock_dataset.side_effect = Exception("Simulated read error")

    # Test
    with caplog.at_level("ERROR"):
        result = load_options_ohlcv(
            underlying="NIFTY", start=date(2024, 4, 24), end=date(2024, 4, 24), data_dir=data_dir
        )

    assert result.empty
    assert "Error loading Parquet partitions: Simulated read error" in caplog.text

"""Unit tests for scripts/pipeline/refresh_vix.py."""

from unittest.mock import patch

from scripts.pipeline.refresh_vix import main
from src.client.exceptions import DataFetchError


@patch("scripts.pipeline.refresh_vix.ingest_vix_from_api")
def test_main_happy_path(mock_ingest, tmp_path):
    """Happy path: ingest succeeds and main returns 0."""
    mock_ingest.return_value = 5

    exit_code = main(["--out-dir", str(tmp_path), "--lookback-days", "30"])

    assert exit_code == 0
    mock_ingest.assert_called_once()
    call_kwargs = mock_ingest.call_args.kwargs
    assert call_kwargs["out_dir"] == tmp_path
    # to_date should be >= from_date
    assert call_kwargs["to_date"] >= call_kwargs["from_date"]


@patch("scripts.pipeline.refresh_vix.ingest_vix_from_api")
def test_main_data_fetch_error_returns_1(mock_ingest, tmp_path):
    """DataFetchError from ingest causes main to return 1."""
    mock_ingest.side_effect = DataFetchError("API timeout")

    exit_code = main(["--out-dir", str(tmp_path)])

    assert exit_code == 1


@patch("scripts.pipeline.refresh_vix.ingest_vix_from_api")
def test_main_missing_token_returns_1(mock_ingest, tmp_path):
    """ValueError (e.g. missing token) causes main to return 1."""
    mock_ingest.side_effect = ValueError("UPSTOX_ANALYTICS_TOKEN not set")

    exit_code = main(["--out-dir", str(tmp_path)])

    assert exit_code == 1


@patch("scripts.pipeline.refresh_vix.ingest_vix_from_api")
def test_main_zero_rows_still_succeeds(mock_ingest, tmp_path):
    """Zero rows written (already up to date) is a success."""
    mock_ingest.return_value = 0

    exit_code = main(["--out-dir", str(tmp_path)])

    assert exit_code == 0

from datetime import date
from unittest.mock import patch

import pandas as pd
import pytest

from scripts.record.record_paper_trade import main


@pytest.fixture
def mock_vix():
    """Mock for back-dated trade tests (trade_date != today)."""
    with (
        patch("scripts.record.record_paper_trade.load_vix_series") as mock_load,
        patch("scripts.record.record_paper_trade.compute_ivr") as mock_ivr,
    ):
        yield mock_load, mock_ivr


@pytest.fixture
def mock_vix_today():
    """Mock for today's trade tests — patches fetch_vix_latest instead of load."""
    with (
        patch("scripts.record.record_paper_trade.fetch_vix_latest") as mock_live,
        patch("scripts.record.record_paper_trade.load_vix_series") as mock_load,
        patch("scripts.record.record_paper_trade.compute_ivr") as mock_ivr,
    ):
        yield mock_live, mock_load, mock_ivr


def test_record_trade_uses_intraday_db_vix_when_available(mock_vix_today, capsys):
    mock_live, mock_load, mock_ivr = mock_vix_today
    mock_load.return_value = pd.Series(dtype="float64")
    mock_ivr.return_value = 0.35

    argv = [
        "scripts/record/record_paper_trade.py",
        "--key",
        "KEY",
        "--price",
        "100",
        "--strategy",
        "paper_test",
    ]
    with patch("scripts.record.record_paper_trade.IntradayMarketStore") as mock_store_cls:
        mock_store_cls.return_value.get_latest_vix_today.return_value = 14.8
        with patch("sys.argv", argv):
            main()

    captured = capsys.readouterr()
    mock_live.assert_not_called()  # API not hit — DB had it
    assert "India VIX from intraday snapshot = 14.80" in captured.err
    assert "ivr_entry : 0.35" in captured.out


def test_record_trade_falls_back_to_api_when_db_has_no_today_snapshot(mock_vix_today, capsys):
    mock_live, mock_load, mock_ivr = mock_vix_today
    mock_live.return_value = 14.8
    mock_load.return_value = pd.Series(dtype="float64")
    mock_ivr.return_value = 0.35

    argv = [
        "scripts/record/record_paper_trade.py",
        "--key",
        "KEY",
        "--price",
        "100",
        "--strategy",
        "paper_test",
    ]
    with patch("scripts.record.record_paper_trade.IntradayMarketStore") as mock_store_cls:
        mock_store_cls.return_value.get_latest_vix_today.return_value = None
        with patch("sys.argv", argv):
            main()

    captured = capsys.readouterr()
    mock_live.assert_called_once()  # DB had nothing — API was hit
    assert "Live India VIX = 14.80" in captured.err
    assert "ivr_entry : 0.35" in captured.out


def test_record_trade_skips_ivr_when_db_and_api_both_fail(mock_vix_today, capsys):
    mock_live, mock_load, mock_ivr = mock_vix_today
    mock_live.return_value = None  # API also down

    argv = [
        "scripts/record/record_paper_trade.py",
        "--key",
        "KEY",
        "--price",
        "100",
        "--strategy",
        "paper_test",
    ]
    with patch("scripts.record.record_paper_trade.IntradayMarketStore") as mock_store_cls:
        mock_store_cls.return_value.get_latest_vix_today.return_value = None
        with patch("sys.argv", argv):
            main()

    captured = capsys.readouterr()
    assert "Could not fetch live India VIX" in captured.err
    assert "ivr_entry : None (VIX data missing — R3 gate skipped)" in captured.out


def test_record_trade_includes_ivr_in_dry_run(mock_vix, capsys):
    mock_load, mock_ivr = mock_vix
    # Mock data present for 2024-01-01
    mock_load.return_value = pd.Series({date(2024, 1, 1): 15.0})
    mock_ivr.return_value = 0.42

    argv = [
        "scripts/record/record_paper_trade.py",
        "--key",
        "KEY",
        "--price",
        "100",
        "--date",
        "2024-01-01",
        "--strategy",
        "paper_test",
    ]
    with patch("sys.argv", argv):
        main()

    captured = capsys.readouterr()
    assert "ivr_entry : 0.42" in captured.out
    assert "ATTENTION: IVR is 0.42 (R3 Entry Window)" in captured.err


def test_record_trade_warns_on_low_ivr(mock_vix, capsys):
    mock_load, mock_ivr = mock_vix
    mock_load.return_value = pd.Series({date(2024, 1, 1): 15.0})
    mock_ivr.return_value = 0.15

    argv = [
        "scripts/record/record_paper_trade.py",
        "--key",
        "KEY",
        "--price",
        "100",
        "--date",
        "2024-01-01",
        "--strategy",
        "paper_test",
    ]
    with patch("sys.argv", argv):
        with pytest.raises(SystemExit) as excinfo:
            main()
        assert excinfo.value.code == 1

    captured = capsys.readouterr()
    assert "ERROR: R3 blocked — low IVR (0.15)" in captured.err


def test_record_trade_warns_on_high_ivr(mock_vix, capsys):
    mock_load, mock_ivr = mock_vix
    mock_load.return_value = pd.Series({date(2024, 1, 1): 15.0})
    mock_ivr.return_value = 0.75

    argv = [
        "scripts/record/record_paper_trade.py",
        "--key",
        "KEY",
        "--price",
        "100",
        "--date",
        "2024-01-01",
        "--strategy",
        "paper_test",
    ]
    with patch("sys.argv", argv):
        main()

    captured = capsys.readouterr()
    assert "ivr_entry : 0.75" in captured.out
    assert "WARNING: High IVR (0.75)" in captured.err
    assert "Elevated vol regime" in captured.err


def test_record_trade_skips_ivr_on_insufficient_data(mock_vix, capsys):
    mock_load, mock_ivr = mock_vix
    mock_load.return_value = pd.Series({date(2024, 1, 1): 15.0})
    mock_ivr.return_value = None  # Insufficient data

    argv = [
        "scripts/record/record_paper_trade.py",
        "--key",
        "KEY",
        "--price",
        "100",
        "--date",
        "2024-01-01",
        "--strategy",
        "paper_test",
    ]
    with patch("sys.argv", argv):
        main()

    captured = capsys.readouterr()
    assert "ivr_entry : None (VIX data missing — R3 gate skipped)" in captured.out
    assert "WARNING: Insufficient VIX history" in captured.err


def test_record_trade_skips_ivr_on_missing_date(mock_vix, capsys):
    mock_load, mock_ivr = mock_vix
    mock_load.return_value = pd.Series({date(2024, 1, 2): 15.0})  # Different date

    argv = [
        "scripts/record/record_paper_trade.py",
        "--key",
        "KEY",
        "--price",
        "100",
        "--date",
        "2024-01-01",
        "--strategy",
        "paper_test",
    ]
    with patch("sys.argv", argv):
        main()

    captured = capsys.readouterr()
    assert "ivr_entry : None (VIX data missing — R3 gate skipped)" in captured.out
    assert "WARNING: No VIX data for 2024-01-01" in captured.err

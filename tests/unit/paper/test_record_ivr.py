import pytest
import pandas as pd
from datetime import date
from unittest.mock import patch
from scripts.record_paper_trade import main

@pytest.fixture
def mock_vix():
    with patch("scripts.record_paper_trade.load_vix_series") as mock_load, \
         patch("scripts.record_paper_trade.compute_ivr") as mock_ivr:
        yield mock_load, mock_ivr

def test_record_trade_includes_ivr_in_dry_run(mock_vix, capsys):
    mock_load, mock_ivr = mock_vix
    # Mock data present for 2024-01-01
    mock_load.return_value = pd.Series({date(2024, 1, 1): 15.0})
    mock_ivr.return_value = 0.42
    
    argv = [
        "scripts/record_paper_trade.py",
        "--key", "KEY",
        "--price", "100",
        "--date", "2024-01-01",
        "--strategy", "paper_test"
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
        "scripts/record_paper_trade.py",
        "--key", "KEY",
        "--price", "100",
        "--date", "2024-01-01",
        "--strategy", "paper_test"
    ]
    with patch("sys.argv", argv):
        main()
        
    captured = capsys.readouterr()
    assert "ivr_entry : 0.15" in captured.out
    assert "WARNING: Low IVR (0.15)" in captured.err

def test_record_trade_warns_on_high_ivr(mock_vix, capsys):
    mock_load, mock_ivr = mock_vix
    mock_load.return_value = pd.Series({date(2024, 1, 1): 15.0})
    mock_ivr.return_value = 0.75
    
    argv = [
        "scripts/record_paper_trade.py",
        "--key", "KEY",
        "--price", "100",
        "--date", "2024-01-01",
        "--strategy", "paper_test"
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
        "scripts/record_paper_trade.py",
        "--key", "KEY",
        "--price", "100",
        "--date", "2024-01-01",
        "--strategy", "paper_test"
    ]
    with patch("sys.argv", argv):
        main()
        
    captured = capsys.readouterr()
    assert "ivr_entry" not in captured.out
    assert "WARNING: Insufficient VIX history" in captured.err

def test_record_trade_skips_ivr_on_missing_date(mock_vix, capsys):
    mock_load, mock_ivr = mock_vix
    mock_load.return_value = pd.Series({date(2024, 1, 2): 15.0}) # Different date
    
    argv = [
        "scripts/record_paper_trade.py",
        "--key", "KEY",
        "--price", "100",
        "--date", "2024-01-01",
        "--strategy", "paper_test"
    ]
    with patch("sys.argv", argv):
        main()
        
    captured = capsys.readouterr()
    assert "ivr_entry" not in captured.out
    assert "WARNING: No VIX data for 2024-01-01" in captured.err

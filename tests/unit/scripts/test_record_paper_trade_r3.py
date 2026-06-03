"""Unit tests for the R3 hard block and MANUAL_OVERRIDE logging in record_paper_trade.py."""

from __future__ import annotations

from collections.abc import Generator
from datetime import date
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from scripts.record.record_paper_trade import main
from src.paper.store import PaperStore


@pytest.fixture
def mock_vix() -> Generator[tuple[MagicMock, MagicMock], None, None]:
    """Mock load_vix_series and compute_ivr for VIX historical checks."""
    with (
        patch("scripts.record.record_paper_trade.load_vix_series") as mock_load,
        patch("scripts.record.record_paper_trade.compute_ivr") as mock_ivr,
    ):
        yield mock_load, mock_ivr


def test_r3_no_block_on_high_ivr(mock_vix, tmp_path) -> None:
    mock_load, mock_ivr = mock_vix
    mock_load.return_value = pd.Series({date(2024, 1, 1): 15.0})
    mock_ivr.return_value = 0.30  # Above 0.25 floor

    db_file = tmp_path / "test.db"
    argv = [
        "scripts/record/record_paper_trade.py",
        "--key",
        "NSE_FO|12345",
        "--price",
        "100",
        "--date",
        "2024-01-01",
        "--strategy",
        "paper_csp_nifty_v1",
        "--db-path",
        str(db_file),
        "--no-dry-run",
    ]
    with patch("sys.argv", argv):
        main()

    # Verify trade is in DB
    store = PaperStore(db_file)
    trades = store.get_trades("paper_csp_nifty_v1")
    assert len(trades) == 1
    assert trades[0].instrument_key == "NSE_FO|12345"

    # Verify no exit events
    events = store.get_open_exit_events("paper_csp_nifty_v1")
    assert len(events) == 0


def test_r3_blocked_on_low_ivr(mock_vix, tmp_path) -> None:
    mock_load, mock_ivr = mock_vix
    mock_load.return_value = pd.Series({date(2024, 1, 1): 15.0})
    mock_ivr.return_value = 0.22  # Below 0.25 floor

    db_file = tmp_path / "test.db"
    argv = [
        "scripts/record/record_paper_trade.py",
        "--key",
        "NSE_FO|12345",
        "--price",
        "100",
        "--date",
        "2024-01-01",
        "--strategy",
        "paper_csp_nifty_v1",
        "--db-path",
        str(db_file),
        "--no-dry-run",
    ]
    with patch("sys.argv", argv):
        with pytest.raises(SystemExit) as excinfo:
            main()
        assert excinfo.value.code == 1

    # Verify no trade written
    store = PaperStore(db_file)
    trades = store.get_trades("paper_csp_nifty_v1")
    assert len(trades) == 0


def test_r3_override_with_force_entry(mock_vix, tmp_path) -> None:
    mock_load, mock_ivr = mock_vix
    mock_load.return_value = pd.Series({date(2024, 1, 1): 15.0})
    mock_ivr.return_value = 0.22  # Below 0.25 floor

    db_file = tmp_path / "test.db"
    argv = [
        "scripts/record/record_paper_trade.py",
        "--key",
        "NSE_FO|12345",
        "--price",
        "100",
        "--date",
        "2024-01-01",
        "--strategy",
        "paper_csp_nifty_v1",
        "--db-path",
        str(db_file),
        "--force-entry",
        "--no-dry-run",
    ]
    with patch("sys.argv", argv):
        main()

    # Verify trade is written
    store = PaperStore(db_file)
    trades = store.get_trades("paper_csp_nifty_v1")
    assert len(trades) == 1

    # Verify MANUAL_OVERRIDE event is written to DB
    events = store.get_open_exit_events("paper_csp_nifty_v1")
    assert len(events) == 1
    assert events[0]["exit_signal"] == "MANUAL_OVERRIDE"
    assert events[0]["detected_by"] == "MANUAL"
    assert events[0]["severity"] == "WARNING"


def test_r3_override_dry_run_skips_db_write(mock_vix, tmp_path) -> None:
    mock_load, mock_ivr = mock_vix
    mock_load.return_value = pd.Series({date(2024, 1, 1): 15.0})
    mock_ivr.return_value = 0.22  # Below 0.25 floor

    db_file = tmp_path / "test.db"
    argv = [
        "scripts/record/record_paper_trade.py",
        "--key",
        "NSE_FO|12345",
        "--price",
        "100",
        "--date",
        "2024-01-01",
        "--strategy",
        "paper_csp_nifty_v1",
        "--db-path",
        str(db_file),
        "--force-entry",
        "--dry-run",  # Dry run
    ]
    with patch("sys.argv", argv):
        main()

    # Verify nothing is written to DB
    store = PaperStore(db_file)
    trades = store.get_trades("paper_csp_nifty_v1")
    assert len(trades) == 0
    events = store.get_open_exit_events("paper_csp_nifty_v1")
    assert len(events) == 0


def test_r3_no_block_on_missing_ivr(mock_vix, tmp_path) -> None:
    mock_load, mock_ivr = mock_vix
    mock_load.return_value = pd.Series({date(2024, 1, 1): 15.0})
    mock_ivr.return_value = None  # Missing VIX history

    db_file = tmp_path / "test.db"
    argv = [
        "scripts/record/record_paper_trade.py",
        "--key",
        "NSE_FO|12345",
        "--price",
        "100",
        "--date",
        "2024-01-01",
        "--strategy",
        "paper_csp_nifty_v1",
        "--db-path",
        str(db_file),
        "--no-dry-run",
    ]
    with patch("sys.argv", argv):
        main()

    # Verify trade is in DB
    store = PaperStore(db_file)
    trades = store.get_trades("paper_csp_nifty_v1")
    assert len(trades) == 1

    # Verify no exit events
    events = store.get_open_exit_events("paper_csp_nifty_v1")
    assert len(events) == 0


def test_r3_no_block_on_buy(mock_vix, tmp_path) -> None:
    mock_load, mock_ivr = mock_vix
    mock_load.return_value = pd.Series({date(2024, 1, 1): 15.0})
    mock_ivr.return_value = 0.10  # Below 0.25 floor

    db_file = tmp_path / "test.db"
    argv = [
        "scripts/record/record_paper_trade.py",
        "--key",
        "NSE_FO|12345",
        "--price",
        "100",
        "--date",
        "2024-01-01",
        "--strategy",
        "paper_csp_nifty_v1",
        "--action",
        "BUY",  # BUY action
        "--db-path",
        str(db_file),
        "--no-dry-run",
    ]
    with patch("sys.argv", argv):
        main()

    # Verify trade is in DB
    store = PaperStore(db_file)
    trades = store.get_trades("paper_csp_nifty_v1")
    assert len(trades) == 1

    # Verify no exit events
    events = store.get_open_exit_events("paper_csp_nifty_v1")
    assert len(events) == 0

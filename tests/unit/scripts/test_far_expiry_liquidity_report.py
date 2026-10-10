import datetime
import sys
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from scripts.dev.far_expiry_liquidity_report import main
from src.far_expiry.store import FarExpiryRow


@pytest.fixture
def mock_store():
    with patch("scripts.dev.far_expiry_liquidity_report.FarExpiryStore") as mock_cls:
        store = MagicMock()
        mock_cls.return_value = store
        yield store


@pytest.fixture
def mock_settings():
    with patch("scripts.dev.far_expiry_liquidity_report.Settings") as mock_cls:
        settings = MagicMock()
        settings.db_path = "mock.db"
        mock_cls.return_value = settings
        yield settings


def test_liquidity_report_no_data(mock_store, mock_settings, capsys):
    mock_store.read_chain_snapshots.return_value = []

    test_args = [
        "script",
        "--start-date",
        "2026-10-01",
        "--end-date",
        "2026-10-02",
        "--expiry",
        "2026-12-31",
    ]
    with patch.object(sys, "argv", test_args):
        main()

    captured = capsys.readouterr()
    assert "No data found." in captured.out


def test_liquidity_report_with_data(mock_store, mock_settings, capsys):
    row1 = FarExpiryRow(
        snapshot_date=datetime.date(2026, 10, 1),
        captured_at=datetime.datetime(2026, 10, 1, 15, 30),
        underlying="NIFTY",
        expiry=datetime.date(2026, 12, 31),
        strike=Decimal("24000"),
        option_type="CE",
        source="upstox",
        underlying_spot=Decimal("23000"),
        ltp=Decimal("100"),
        bid=Decimal("99"),
        ask=Decimal("101"),
        oi=150000,
        volume=1000,
        iv=Decimal("15"),
        delta=Decimal("0.16"),
        gamma=None,
        theta=None,
        vega=None,
    )
    row2 = FarExpiryRow(
        snapshot_date=datetime.date(2026, 10, 1),
        captured_at=datetime.datetime(2026, 10, 1, 15, 30),
        underlying="NIFTY",
        expiry=datetime.date(2026, 12, 31),
        strike=Decimal("22000"),
        option_type="PE",
        source="upstox",
        underlying_spot=Decimal("23000"),
        ltp=Decimal("120"),
        bid=Decimal("118"),
        ask=Decimal("122"),
        oi=120000,
        volume=2000,
        iv=Decimal("16"),
        delta=Decimal("-0.14"),
        gamma=None,
        theta=None,
        vega=None,
    )
    row3 = FarExpiryRow(
        snapshot_date=datetime.date(2026, 10, 1),
        captured_at=datetime.datetime(2026, 10, 1, 15, 30),
        underlying="NIFTY",
        expiry=datetime.date(2026, 12, 31),
        strike=Decimal("25000"),
        option_type="CE",
        source="upstox",
        underlying_spot=Decimal("23000"),
        ltp=Decimal("10"),
        bid=Decimal("0"),
        ask=Decimal("0"),
        oi=1000,
        volume=0,
        iv=Decimal("15"),
        delta=Decimal("0.05"),
        gamma=None,
        theta=None,
        vega=None,
    )

    mock_store.read_chain_snapshots.return_value = [row1, row2, row3]

    test_args = [
        "script",
        "--start-date",
        "2026-10-01",
        "--end-date",
        "2026-10-02",
        "--expiry",
        "2026-12-31",
        "--target-ce-delta",
        "0.15",
        "--target-pe-delta",
        "0.15",
    ]
    with patch.object(sys, "argv", test_args):
        main()

    captured = capsys.readouterr()
    assert "2026-10-01" in captured.out
    assert "24000" in captured.out
    assert "22000" in captured.out
    assert "2.00%" in captured.out
    assert "3.33%" in captured.out
    assert " 3      " in captured.out  # 3 rows with non-zero delta

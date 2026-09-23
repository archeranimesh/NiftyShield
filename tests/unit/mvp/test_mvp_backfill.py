"""Tests for src.mvp.backfill.fetch_historical_closes."""

from datetime import date
from decimal import Decimal
from pathlib import Path

from src.backtest.equity_bhavcopy_ingest import EquityBhavRecord, write_equity_to_parquet
from src.mvp.backfill import fetch_historical_closes


def test_fetch_historical_closes_happy_path_spans_two_months(tmp_path: Path) -> None:
    june_records = [
        EquityBhavRecord(trade_date=date(2026, 6, 29), symbol="UNIPARTS", close=Decimal("640.10")),
        EquityBhavRecord(trade_date=date(2026, 6, 30), symbol="UNIPARTS", close=Decimal("650.00")),
    ]
    july_records = [
        EquityBhavRecord(trade_date=date(2026, 7, 1), symbol="UNIPARTS", close=Decimal("659.70")),
        EquityBhavRecord(trade_date=date(2026, 7, 1), symbol="RELIANCE", close=Decimal("2900.00")),
    ]
    write_equity_to_parquet(june_records, date(2026, 6, 29), tmp_path)
    write_equity_to_parquet(july_records, date(2026, 7, 1), tmp_path)

    closes = fetch_historical_closes(
        "UNIPARTS", date(2026, 6, 29), date(2026, 7, 1), data_dir=tmp_path
    )

    assert closes == [
        (date(2026, 6, 29), Decimal("640.10")),
        (date(2026, 6, 30), Decimal("650.00")),
        (date(2026, 7, 1), Decimal("659.70")),
    ]


def test_fetch_historical_closes_no_partition_returns_empty(tmp_path: Path) -> None:
    closes = fetch_historical_closes(
        "UNIPARTS", date(2026, 6, 1), date(2026, 6, 30), data_dir=tmp_path
    )

    assert closes == []

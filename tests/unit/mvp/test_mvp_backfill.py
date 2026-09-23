"""Tests for src.mvp.backfill.fetch_historical_closes."""

from collections.abc import Generator
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from src.backtest.equity_bhavcopy_ingest import EquityBhavRecord, write_equity_to_parquet
from src.mvp.backfill import enter_backfill_pick, fetch_historical_closes, run_backfill
from src.mvp.models import Pick, PickStatus
from src.mvp.store import MVPStore


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


@pytest.fixture
def mem_store(tmp_path: Path) -> Generator[MVPStore, None, None]:
    store = MVPStore(str(tmp_path / "test.sqlite"))
    store.init_db()
    yield store


def _make_test_pick(
    pick_id="p1", reco_price=Decimal("100"), target_price=Decimal("150"), stop_loss=Decimal("80")
) -> Pick:
    return Pick(
        pick_id=pick_id,
        symbol="TEST",
        pick_date="2026-06-11",
        reco_price=reco_price,
        target_price=target_price,
        stop_loss=stop_loss,
        created_at="2026-06-11T00:00:00Z",
        updated_at="2026-06-11T00:00:00Z",
    )


def test_enter_backfill_pick_happy_path() -> None:
    # 2026-06-11 was a Thursday. Next trading day is 2026-06-12 (Friday).
    pick = _make_test_pick(reco_price=Decimal("100"))
    closes = {date(2026, 6, 12): Decimal("101.50")}
    result = enter_backfill_pick(pick, closes)
    assert result is not None
    assert result[0] == date(2026, 6, 12)
    assert result[1] == Decimal("101.50")


def test_enter_backfill_pick_stays_pending() -> None:
    pick = _make_test_pick(reco_price=Decimal("100"))
    closes = {
        date(2026, 6, 12): Decimal("99.00")  # Below reco price
    }
    result = enter_backfill_pick(pick, closes)
    assert result is None


def test_run_backfill_happy_path(mem_store: MVPStore, monkeypatch: pytest.MonkeyPatch) -> None:
    mem_store.add_pick(_make_test_pick())

    # 2026-06-12 is Fri, 2026-06-15 is Mon
    equity_closes = {
        date(2026, 6, 12): Decimal("105"),  # Entry (105 > 100)
        date(2026, 6, 15): Decimal("110"),
        date(2026, 6, 16): Decimal("155"),  # Hits target 150
    }
    index_closes = {
        date(2026, 6, 12): Decimal("20000"),
        date(2026, 6, 15): Decimal("20050"),
        date(2026, 6, 16): Decimal("20100"),
    }

    run_backfill(mem_store, "p1", equity_closes, index_closes, end_date=date(2026, 6, 17))

    pick = mem_store.get_pick("p1")
    assert pick is not None
    assert pick.status == PickStatus.TARGET_HIT
    assert pick.close_price == Decimal("155")

    snaps = mem_store.get_snapshots("p1")
    assert len(snaps) == 3  # 12th, 15th, 16th
    assert snaps[-1].benchmark_close == Decimal("20000")  # earliest snapshot


def test_run_backfill_never_enters(mem_store: MVPStore) -> None:
    mem_store.add_pick(_make_test_pick())
    equity_closes = {
        date(2026, 6, 12): Decimal("95"),  # Stays below reco_price 100
    }
    run_backfill(mem_store, "p1", equity_closes, {}, end_date=date(2026, 6, 12))

    pick = mem_store.get_pick("p1")
    assert pick is not None
    assert pick.status == PickStatus.PENDING
    assert len(mem_store.get_snapshots("p1")) == 0


def test_run_backfill_stop_loss_hit(mem_store: MVPStore) -> None:
    mem_store.add_pick(_make_test_pick())
    equity_closes = {
        date(2026, 6, 12): Decimal("105"),  # Entry
        date(2026, 6, 15): Decimal("75"),  # Hits SL (80)
    }
    run_backfill(mem_store, "p1", equity_closes, {}, end_date=date(2026, 6, 15))

    pick = mem_store.get_pick("p1")
    assert pick is not None
    assert pick.status == PickStatus.SL_HIT
    assert pick.close_price == Decimal("75")
    assert len(mem_store.get_snapshots("p1")) == 2

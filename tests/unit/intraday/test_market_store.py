import datetime
import pytest

from src.intraday.market_store import IntradayMarketStore

@pytest.fixture
def temp_db(tmp_path) -> str:
    return str(tmp_path / "test_intraday.sqlite")

def test_ensure_tables_is_idempotent(temp_db):
    store1 = IntradayMarketStore(temp_db)
    store2 = IntradayMarketStore(temp_db)  # Should not raise

def test_get_latest_empty(temp_db):
    store = IntradayMarketStore(temp_db)
    assert store.get_latest() is None

def test_record_and_get_latest(temp_db):
    store = IntradayMarketStore(temp_db)
    now = datetime.datetime.now(datetime.timezone.utc)
    store.record_market_snapshot(now, 22000.5, 14.2)
    
    latest = store.get_latest()
    assert latest is not None
    assert latest == (22000.5, 14.2)

def test_purge_old(temp_db):
    store = IntradayMarketStore(temp_db)
    now = datetime.datetime.now(datetime.timezone.utc)
    old = now - datetime.timedelta(days=35)

    store.record_market_snapshot(old, 21000.0, 15.0)
    store.record_market_snapshot(now, 22000.5, 14.2)

    deleted = store.purge_old(days=30)
    assert deleted == 1

    latest = store.get_latest()
    assert latest == (22000.5, 14.2)


def test_record_naive_timestamp_raises(temp_db):
    store = IntradayMarketStore(temp_db)
    naive = datetime.datetime(2026, 5, 8, 15, 25, 0)  # no tzinfo
    with pytest.raises(ValueError, match="timezone-aware"):
        store.record_market_snapshot(naive, 24172.6, 13.45)


def test_get_latest_vix_today_returns_vix_for_todays_snapshot(temp_db):
    store = IntradayMarketStore(temp_db)
    now = datetime.datetime.now(datetime.timezone.utc)
    store.record_market_snapshot(now, 23500.0, 14.80)

    result = store.get_latest_vix_today()
    assert result == 14.80


def test_get_latest_vix_today_returns_none_for_stale_snapshot(temp_db):
    store = IntradayMarketStore(temp_db)
    yesterday = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=1)
    store.record_market_snapshot(yesterday, 23500.0, 15.20)

    assert store.get_latest_vix_today() is None


def test_get_latest_vix_today_returns_none_when_table_empty(temp_db):
    store = IntradayMarketStore(temp_db)
    assert store.get_latest_vix_today() is None


def test_get_latest_vix_today_returns_none_when_vix_is_zero(temp_db):
    store = IntradayMarketStore(temp_db)
    now = datetime.datetime.now(datetime.timezone.utc)
    store.record_market_snapshot(now, 23500.0, 0.0)  # VIX fetch failed that tick

    assert store.get_latest_vix_today() is None

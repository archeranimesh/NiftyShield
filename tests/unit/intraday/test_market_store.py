import sqlite3
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
    
    # Verify only the old one was deleted and latest is the new one
    latest = store.get_latest()
    assert latest == (22000.5, 14.2)

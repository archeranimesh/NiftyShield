import pytest
import sqlite3
from decimal import Decimal
from datetime import date
from src.paper.models import PaperTrade
from src.paper.store import PaperStore
from src.models.portfolio import TradeAction

@pytest.fixture
def store(tmp_path):
    # Use file-based DB for tests as PaperStore opens new connections
    db_file = tmp_path / "test_paper.db"
    return PaperStore(db_file)

def test_paper_trade_accepts_ivr_at_entry():
    trade = PaperTrade(
        strategy_name="paper_test",
        leg_role="test_leg",
        instrument_key="KEY",
        trade_date=date(2024, 1, 1),
        action=TradeAction.SELL,
        quantity=1,
        price=Decimal("100.0"),
        ivr_at_entry=0.42
    )
    assert trade.ivr_at_entry == 0.42

def test_paper_trade_ivr_defaults_to_none():
    trade = PaperTrade(
        strategy_name="paper_test",
        leg_role="test_leg",
        instrument_key="KEY",
        trade_date=date(2024, 1, 1),
        action=TradeAction.SELL,
        quantity=1,
        price=Decimal("100.0")
    )
    assert trade.ivr_at_entry is None

def test_store_round_trips_ivr_at_entry(store):
    trade = PaperTrade(
        strategy_name="paper_test",
        leg_role="test_leg",
        instrument_key="KEY",
        trade_date=date(2024, 1, 1),
        action=TradeAction.SELL,
        quantity=1,
        price=Decimal("100.0"),
        ivr_at_entry=0.42
    )
    store.record_trade(trade)
    
    trades = store.get_trades("paper_test")
    assert len(trades) == 1
    assert trades[0].ivr_at_entry == 0.42

def test_store_round_trips_ivr_none(store):
    trade = PaperTrade(
        strategy_name="paper_test",
        leg_role="test_leg",
        instrument_key="KEY",
        trade_date=date(2024, 1, 1),
        action=TradeAction.SELL,
        quantity=1,
        price=Decimal("100.0"),
        ivr_at_entry=None
    )
    store.record_trade(trade)
    
    trades = store.get_trades("paper_test")
    assert len(trades) == 1
    assert trades[0].ivr_at_entry is None

def test_store_migration_idempotent(tmp_path):
    # Use a file-based DB to test multi-init
    db_file = tmp_path / "test.sqlite"
    store1 = PaperStore(db_file)
    # Should not raise exception
    store2 = PaperStore(db_file)
    assert store1.db_path == store2.db_path

from decimal import Decimal

import pytest

from src.db import connect as _connect
from src.paper.store import PaperStore
from src.strategy.profit_lock_engine import ProfitLockState


@pytest.fixture
def store(tmp_path):
    db_path = tmp_path / "portfolio.sqlite"
    return PaperStore(db_path)


def test_get_default_state_when_missing(store):
    state = store.get_profit_lock_state("test_strat")
    assert state.profit_lock_zone == 0
    assert state.zone2_lock_executed is False
    assert state.zone3_lock_executed is False
    assert state.cumulative_lock_debit_pts == Decimal("0")
    assert state.active_put_width_pts == 0
    assert state.active_call_width_pts == 0
    assert state.cycle_id == ""


def test_set_and_get_roundtrip(store):
    state = ProfitLockState(
        profit_lock_zone=2,
        zone2_lock_executed=True,
        zone3_lock_executed=False,
        cumulative_lock_debit_pts=Decimal("34"),
        active_put_width_pts=150,
        active_call_width_pts=100,
        cycle_id="cycle_123",
    )
    store.set_profit_lock_state("test_strat", state)

    retrieved = store.get_profit_lock_state("test_strat")
    assert retrieved == state


def test_decimal_stored_as_text(store):
    state = ProfitLockState(
        profit_lock_zone=1,
        zone2_lock_executed=False,
        zone3_lock_executed=False,
        cumulative_lock_debit_pts=Decimal("12.5"),
        active_put_width_pts=200,
        active_call_width_pts=200,
        cycle_id="c",
    )
    store.set_profit_lock_state("test_strat", state)

    with _connect(store.db_path) as conn:
        row = conn.execute(
            "SELECT cumulative_lock_debit FROM paper_strategies WHERE strategy_name = 'test_strat'"
        ).fetchone()
        assert type(row["cumulative_lock_debit"]) is str
        assert row["cumulative_lock_debit"] == "12.5"

    retrieved = store.get_profit_lock_state("test_strat")
    assert retrieved.cumulative_lock_debit_pts == Decimal("12.5")


def test_reset_clears_all_fields(store):
    state = ProfitLockState(
        profit_lock_zone=2,
        zone2_lock_executed=True,
        zone3_lock_executed=True,
        cumulative_lock_debit_pts=Decimal("100"),
        active_put_width_pts=50,
        active_call_width_pts=50,
        cycle_id="old_cycle",
    )
    store.set_profit_lock_state("test_strat", state)

    store.reset_profit_lock_state("test_strat", "new_cycle")

    retrieved = store.get_profit_lock_state("test_strat")
    assert retrieved.profit_lock_zone == 0
    assert retrieved.zone2_lock_executed is False
    assert retrieved.zone3_lock_executed is False
    assert retrieved.cumulative_lock_debit_pts == Decimal("0")
    assert retrieved.active_put_width_pts == 0
    assert retrieved.active_call_width_pts == 0
    assert retrieved.cycle_id == "new_cycle"


def test_upsert_does_not_duplicate(store):
    state1 = ProfitLockState(
        profit_lock_zone=1,
        zone2_lock_executed=False,
        zone3_lock_executed=False,
        cumulative_lock_debit_pts=Decimal("0"),
        active_put_width_pts=0,
        active_call_width_pts=0,
        cycle_id="1",
    )
    store.set_profit_lock_state("test_strat", state1)

    state2 = ProfitLockState(
        profit_lock_zone=2,
        zone2_lock_executed=True,
        zone3_lock_executed=False,
        cumulative_lock_debit_pts=Decimal("20"),
        active_put_width_pts=100,
        active_call_width_pts=100,
        cycle_id="1",
    )
    store.set_profit_lock_state("test_strat", state2)

    with _connect(store.db_path) as conn:
        count = conn.execute(
            "SELECT COUNT(*) as c FROM paper_strategies WHERE strategy_name = 'test_strat'"
        ).fetchone()["c"]
        assert count == 1

    retrieved = store.get_profit_lock_state("test_strat")
    assert retrieved == state2

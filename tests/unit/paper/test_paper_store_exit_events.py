"""Unit tests for paper exit events database storage and transitions."""

from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from src.models.portfolio import TradeAction
from src.paper.models import ExitSignal, PaperTrade
from src.paper.store import PaperStore


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "test_paper_exit_events.db"


@pytest.fixture
def store(db_path: Path) -> PaperStore:
    return PaperStore(db_path)


def test_create_and_get_exit_event(store: PaperStore) -> None:
    # 1. Insert & Roundtrip
    t_now = datetime(2026, 6, 3, 10, 0, 0, tzinfo=timezone.utc)
    event_id = store.create_exit_event(
        strategy_name="paper_csp_nifty_v1",
        leg_name="short_put",
        trade_id="trade_123",
        event_time=t_now,
        detected_by="EOD",
        exit_signal=ExitSignal.PROFIT_TARGET,
        severity="ACTION",
        entry_price=Decimal("150.50"),
        snapshot_id=42,
        ltp=75.25,
        mid=75.30,
        bid=75.10,
        ask=75.50,
        delta=-0.22,
        dte=14,
        threshold_value=0.50,
        delta_stop_would_fire=0,
        premium_stop_would_fire=1,
        actual_rule_used="PREMIUM",
        notes="initial notes",
    )
    assert event_id >= 1

    events = store.get_open_exit_events("paper_csp_nifty_v1")
    assert len(events) == 1
    ev = events[0]
    assert ev["id"] == event_id
    assert ev["strategy_name"] == "paper_csp_nifty_v1"
    assert ev["leg_name"] == "short_put"
    assert ev["trade_id"] == "trade_123"
    assert ev["snapshot_id"] == 42
    assert ev["event_time"] == t_now.isoformat()
    assert ev["detected_by"] == "EOD"
    assert ev["exit_signal"] == ExitSignal.PROFIT_TARGET.value
    assert ev["severity"] == "ACTION"
    assert ev["ltp"] == 75.25
    assert ev["mid"] == 75.30
    assert ev["bid"] == 75.10
    assert ev["ask"] == 75.50
    assert ev["delta"] == -0.22
    assert ev["dte"] == 14
    assert ev["threshold_value"] == 0.50
    assert ev["delta_stop_would_fire"] == 0
    assert ev["premium_stop_would_fire"] == 1
    assert ev["actual_rule_used"] == "PREMIUM"
    assert ev["status"] == "OPEN"
    assert ev["notes"] == "initial notes"

    # 2. Float Assertion: Verify that entry_price is explicitly a float in database retrieval
    assert isinstance(ev["entry_price"], float)
    assert ev["entry_price"] == 150.50


def test_nullable_optional_fields(store: PaperStore) -> None:
    t_now = datetime(2026, 6, 3, 10, 0, 0, tzinfo=timezone.utc)
    event_id = store.create_exit_event(
        strategy_name="paper_csp_nifty_v1",
        leg_name="short_put",
        trade_id="trade_123",
        event_time=t_now,
        detected_by="MANUAL",
        exit_signal=ExitSignal.MANUAL,
        severity="INFO",
        entry_price=200.0,
    )
    events = store.get_open_exit_events()
    assert len(events) == 1
    ev = events[0]
    assert ev["id"] == event_id
    assert ev["snapshot_id"] is None
    assert ev["ltp"] is None
    assert ev["mid"] is None
    assert ev["bid"] is None
    assert ev["ask"] is None
    assert ev["delta"] is None
    assert ev["dte"] is None
    assert ev["threshold_value"] is None
    assert ev["delta_stop_would_fire"] is None
    assert ev["premium_stop_would_fire"] is None
    assert ev["actual_rule_used"] is None
    assert ev["notes"] is None


def test_ordering_by_event_time(store: PaperStore) -> None:
    t1 = datetime(2026, 6, 3, 12, 0, 0, tzinfo=timezone.utc)
    t2 = datetime(2026, 6, 3, 10, 0, 0, tzinfo=timezone.utc)
    t3 = datetime(2026, 6, 3, 11, 0, 0, tzinfo=timezone.utc)

    store.create_exit_event(
        "paper_csp_nifty_v1", "short_put", "t1", t1, "EOD", ExitSignal.TIME_STOP, "ACTION", 10.0
    )
    store.create_exit_event(
        "paper_csp_nifty_v1", "short_put", "t2", t2, "EOD", ExitSignal.TIME_STOP, "ACTION", 10.0
    )
    store.create_exit_event(
        "paper_csp_nifty_v1", "short_put", "t3", t3, "EOD", ExitSignal.TIME_STOP, "ACTION", 10.0
    )

    events = store.get_open_exit_events()
    assert len(events) == 3
    assert events[0]["trade_id"] == "t2"  # earliest
    assert events[1]["trade_id"] == "t3"
    assert events[2]["trade_id"] == "t1"  # latest


def test_state_transitions_and_guards(store: PaperStore) -> None:
    t_now = datetime(2026, 6, 3, 10, 0, 0, tzinfo=timezone.utc)
    ev_id = store.create_exit_event(
        "paper_csp_nifty_v1", "short_put", "t1", t_now, "EOD", ExitSignal.TIME_STOP, "ACTION", 10.0
    )

    # Transition to ACKNOWLEDGED
    store.acknowledge_exit_event(ev_id)
    events = store.get_open_exit_events()
    assert len(events) == 1
    assert events[0]["status"] == "ACKNOWLEDGED"

    # Guards: double acknowledge should fail because status is not 'OPEN'
    with pytest.raises(ValueError, match="No open paper_exit_events row"):
        store.acknowledge_exit_event(ev_id)

    # Transition to ACTED
    store.resolve_exit_event(ev_id, "ACTED", "resolved trade")
    events = store.get_open_exit_events()
    assert len(events) == 0  # removed from open list

    # Guards: trying to acknowledge or resolve an already resolved event should fail
    with pytest.raises(ValueError, match="No open paper_exit_events row"):
        store.acknowledge_exit_event(ev_id)

    with pytest.raises(ValueError, match="No open or acknowledged paper_exit_events row"):
        store.resolve_exit_event(ev_id, "ACTED")


def test_notes_appending_semantics(store: PaperStore) -> None:
    t_now = datetime(2026, 6, 3, 10, 0, 0, tzinfo=timezone.utc)

    # 1. Event created with initial notes
    ev_id_1 = store.create_exit_event(
        "paper_csp_nifty_v1",
        "short_put",
        "t1",
        t_now,
        "EOD",
        ExitSignal.TIME_STOP,
        "ACTION",
        10.0,
        notes="initial notes",
    )
    store.resolve_exit_event(ev_id_1, "ACTED", "resolved note")

    # Verify via custom query or fetching from database
    with store.db_path.open() as _:
        from src.db import connect as _connect

        with _connect(store.db_path) as conn:
            row = conn.execute(
                "SELECT notes FROM paper_exit_events WHERE id = ?", (ev_id_1,)
            ).fetchone()
            assert row["notes"] == "initial notes\nresolved note"

    # 2. Event created with empty notes
    ev_id_2 = store.create_exit_event(
        "paper_csp_nifty_v1",
        "short_put",
        "t2",
        t_now,
        "EOD",
        ExitSignal.TIME_STOP,
        "ACTION",
        10.0,
        notes="",
    )
    store.resolve_exit_event(ev_id_2, "ACTED", "resolved note")

    with _connect(store.db_path) as conn:
        row = conn.execute(
            "SELECT notes FROM paper_exit_events WHERE id = ?", (ev_id_2,)
        ).fetchone()
        assert row["notes"] == "resolved note"

    # 3. Event created with None notes
    ev_id_3 = store.create_exit_event(
        "paper_csp_nifty_v1",
        "short_put",
        "t3",
        t_now,
        "EOD",
        ExitSignal.TIME_STOP,
        "ACTION",
        10.0,
        notes=None,
    )
    store.resolve_exit_event(ev_id_3, "ACTED", "resolved note")

    with _connect(store.db_path) as conn:
        row = conn.execute(
            "SELECT notes FROM paper_exit_events WHERE id = ?", (ev_id_3,)
        ).fetchone()
        assert row["notes"] == "resolved note"


def test_coexistence_with_paper_trades(store: PaperStore) -> None:
    # 1. Round-trip a trade before exit event operations
    trade1 = PaperTrade(
        strategy_name="paper_csp_nifty_v1",
        leg_role="short_put",
        instrument_key="NSE_FO|12345",
        trade_date=date(2026, 6, 1),
        action=TradeAction.SELL,
        quantity=75,
        price=Decimal("120.50"),
        notes="initial trade",
    )
    assert store.record_trade(trade1) is True

    # 2. Insert exit events
    t_now = datetime(2026, 6, 3, 10, 0, 0, tzinfo=timezone.utc)
    ev_id = store.create_exit_event(
        "paper_csp_nifty_v1",
        "short_put",
        "trade_123",
        t_now,
        "EOD",
        ExitSignal.TIME_STOP,
        "ACTION",
        10.0,
    )
    store.acknowledge_exit_event(ev_id)

    # 3. Round-trip another trade after exit event operations
    trade2 = PaperTrade(
        strategy_name="paper_csp_nifty_v1",
        leg_role="short_call",
        instrument_key="NSE_FO|67890",
        trade_date=date(2026, 6, 2),
        action=TradeAction.SELL,
        quantity=75,
        price=Decimal("80.00"),
        notes="second trade",
    )
    assert store.record_trade(trade2) is True

    # Verify both trades read back successfully
    trades = store.get_trades("paper_csp_nifty_v1")
    assert len(trades) == 2
    assert trades[0].leg_role == "short_put"
    assert trades[1].leg_role == "short_call"

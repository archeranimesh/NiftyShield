"""Unit tests for paper exit events database storage and transitions."""

from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from src.db import connect as _connect
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
        ltp=Decimal("75.25"),
        mid=Decimal("75.30"),
        bid=Decimal("75.10"),
        ask=Decimal("75.50"),
        delta=-0.22,
        dte=14,
        threshold_value=Decimal("0.50"),
        delta_stop_would_fire=0,
        premium_stop_would_fire=1,
        actual_rule_used="PREMIUM",
        counterfactual_dte_marks='{"exit_dte": 14}',
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
    assert ev["ltp"] == Decimal("75.25")
    assert ev["mid"] == Decimal("75.30")
    assert ev["bid"] == Decimal("75.10")
    assert ev["ask"] == Decimal("75.50")
    assert ev["delta"] == -0.22
    assert ev["dte"] == 14
    assert ev["threshold_value"] == Decimal("0.50")
    assert ev["delta_stop_would_fire"] == 0
    assert ev["premium_stop_would_fire"] == 1
    assert ev["actual_rule_used"] == "PREMIUM"
    assert ev["counterfactual_dte_marks"] == '{"exit_dte": 14}'
    assert ev["status"] == "OPEN"
    assert ev["notes"] == "initial notes"

    # Verify monetary fields are Decimal, not float
    assert isinstance(ev["entry_price"], Decimal)
    assert ev["entry_price"] == Decimal("150.50")


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
        entry_price=Decimal("200"),
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
    assert ev["counterfactual_dte_marks"] is None
    assert ev["notes"] is None


def test_ordering_by_event_time(store: PaperStore) -> None:
    t1 = datetime(2026, 6, 3, 12, 0, 0, tzinfo=timezone.utc)
    t2 = datetime(2026, 6, 3, 10, 0, 0, tzinfo=timezone.utc)
    t3 = datetime(2026, 6, 3, 11, 0, 0, tzinfo=timezone.utc)

    store.create_exit_event(
        "paper_csp_nifty_v1",
        "short_put",
        "t1",
        t1,
        "EOD",
        ExitSignal.TIME_STOP,
        "ACTION",
        Decimal("10"),
    )
    store.create_exit_event(
        "paper_csp_nifty_v1",
        "short_put",
        "t2",
        t2,
        "EOD",
        ExitSignal.TIME_STOP,
        "ACTION",
        Decimal("10"),
    )
    store.create_exit_event(
        "paper_csp_nifty_v1",
        "short_put",
        "t3",
        t3,
        "EOD",
        ExitSignal.TIME_STOP,
        "ACTION",
        Decimal("10"),
    )

    events = store.get_open_exit_events()
    assert len(events) == 3
    assert events[0]["trade_id"] == "t2"  # earliest
    assert events[1]["trade_id"] == "t3"
    assert events[2]["trade_id"] == "t1"  # latest


def test_state_transitions_and_guards(store: PaperStore) -> None:
    t_now = datetime(2026, 6, 3, 10, 0, 0, tzinfo=timezone.utc)
    ev_id = store.create_exit_event(
        "paper_csp_nifty_v1",
        "short_put",
        "t1",
        t_now,
        "EOD",
        ExitSignal.TIME_STOP,
        "ACTION",
        Decimal("10"),
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

    # Test DISMISSED path independently
    ev_id_dismissed = store.create_exit_event(
        "paper_csp_nifty_v1",
        "short_put",
        "t2",
        t_now,
        "EOD",
        ExitSignal.TIME_STOP,
        "ACTION",
        Decimal("10"),
    )
    store.resolve_exit_event(ev_id_dismissed, "DISMISSED", "dismissed notes")
    events = store.get_open_exit_events()
    assert len(events) == 0  # removed from open list

    # Check status is DISMISSED in DB
    with _connect(store.db_path) as conn:
        row = conn.execute(
            "SELECT status, notes FROM paper_exit_events WHERE id = ?", (ev_id_dismissed,)
        ).fetchone()
        assert row["status"] == "DISMISSED"
        assert row["notes"] == "dismissed notes"


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
        Decimal("10"),
        notes="initial notes",
    )
    store.resolve_exit_event(ev_id_1, "ACTED", "resolved note")

    # Verify via custom query or fetching from database
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
        Decimal("10"),
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
        Decimal("10"),
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
        Decimal("10"),
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


def test_monetary_fields_stored_as_text_in_db(store: PaperStore) -> None:
    """Decimal monetary fields must be stored as TEXT, not REAL, in SQLite."""
    t_now = datetime(2026, 6, 3, 10, 0, 0, tzinfo=timezone.utc)
    store.create_exit_event(
        strategy_name="paper_csp_nifty_v1",
        leg_name="short_put",
        trade_id="trade_text",
        event_time=t_now,
        detected_by="EOD",
        exit_signal=ExitSignal.PROFIT_TARGET,
        severity="ACTION",
        entry_price=Decimal("150.50"),
        ltp=Decimal("75.25"),
        bid=Decimal("75.10"),
        ask=Decimal("75.50"),
        threshold_value=Decimal("0.30"),
    )

    with _connect(store.db_path) as conn:
        row = conn.execute(
            "SELECT ltp, bid, ask, entry_price, threshold_value "
            "FROM paper_exit_events WHERE trade_id = 'trade_text'"
        ).fetchone()

    # SQLite type() confirms TEXT affinity; isinstance str confirms no float coercion
    assert isinstance(row["ltp"], str), "ltp must be TEXT in SQLite"
    assert isinstance(row["entry_price"], str), "entry_price must be TEXT in SQLite"
    assert isinstance(row["threshold_value"], str), "threshold_value must be TEXT in SQLite"


def test_decimal_roundtrip_preserves_exact_value(store: PaperStore) -> None:
    """Values written as Decimal must read back as the same Decimal, losslessly."""
    t_now = datetime(2026, 6, 3, 10, 0, 0, tzinfo=timezone.utc)
    store.create_exit_event(
        strategy_name="paper_csp_nifty_v1",
        leg_name="short_put",
        trade_id="trade_roundtrip",
        event_time=t_now,
        detected_by="EOD",
        exit_signal=ExitSignal.PROFIT_TARGET,
        severity="ACTION",
        entry_price=Decimal("231.68"),
        ltp=Decimal("69.50"),
        mid=Decimal("69.75"),
        bid=Decimal("69.25"),
        ask=Decimal("70.25"),
        threshold_value=Decimal("0.30"),
    )

    events = store.get_open_exit_events("paper_csp_nifty_v1")
    assert len(events) == 1
    ev = events[0]
    assert ev["entry_price"] == Decimal("231.68")
    assert ev["ltp"] == Decimal("69.50")
    assert ev["mid"] == Decimal("69.75")
    assert ev["bid"] == Decimal("69.25")
    assert ev["ask"] == Decimal("70.25")
    assert ev["threshold_value"] == Decimal("0.30")


def test_none_monetary_fields_stored_as_null(store: PaperStore) -> None:
    """None monetary fields must be stored as NULL, not zero."""
    t_now = datetime(2026, 6, 3, 10, 0, 0, tzinfo=timezone.utc)
    store.create_exit_event(
        strategy_name="paper_csp_nifty_v1",
        leg_name="short_put",
        trade_id="trade_null",
        event_time=t_now,
        detected_by="EOD",
        exit_signal=ExitSignal.TIME_STOP,
        severity="ACTION",
        entry_price=Decimal("100"),
        ltp=None,
        mid=None,
        bid=None,
        ask=None,
        threshold_value=None,
    )

    with _connect(store.db_path) as conn:
        row = conn.execute(
            "SELECT ltp, mid, bid, ask, threshold_value "
            "FROM paper_exit_events WHERE trade_id = 'trade_null'"
        ).fetchone()

    assert row["ltp"] is None
    assert row["mid"] is None
    assert row["bid"] is None
    assert row["ask"] is None
    assert row["threshold_value"] is None


def test_get_exit_event(store: PaperStore) -> None:
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
    )
    # Check present event
    ev = store.get_exit_event(event_id)
    assert ev is not None
    assert ev["id"] == event_id
    assert ev["strategy_name"] == "paper_csp_nifty_v1"
    assert ev["entry_price"] == Decimal("150.50")

    # Check non-existent event
    assert store.get_exit_event(99999) is None

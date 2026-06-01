import sqlite3
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import pytest

from src.models.portfolio import TradeAction
from src.paper.models import PaperTrade
from src.paper.store import PaperStore


def test_create_and_get_pending_approvals(tmp_path):
    db_path = tmp_path / "portfolio.sqlite"
    store = PaperStore(db_path)

    expires_at = (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat()
    app_id = store.create_approval(
        strategy_name="paper_csp_nifty",
        event_type="ENTRY",
        council_output_json='{"decision": "GO"}',
        telegram_msg_id=12345,
        expires_at=expires_at,
    )
    assert isinstance(app_id, int)

    pending = store.get_pending_approvals()
    assert len(pending) == 1
    row = pending[0]
    assert row["id"] == app_id
    assert row["strategy_name"] == "paper_csp_nifty"
    assert row["event_type"] == "ENTRY"
    # Verify council_output is deserialized as a dict / JSON object
    assert row["council_output"] == {"decision": "GO"}
    assert row["status"] == "PENDING"
    assert row["telegram_msg_id"] == 12345
    assert row["expires_at"] == expires_at
    assert row["approved_rank"] is None
    assert row["resolved_at"] is None


def test_resolve_approval_approved(tmp_path):
    db_path = tmp_path / "portfolio.sqlite"
    store = PaperStore(db_path)

    expires_at = (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat()
    app_id = store.create_approval(
        strategy_name="paper_csp_nifty",
        event_type="ENTRY",
        council_output_json='{"decision": "GO"}',
        telegram_msg_id=12345,
        expires_at=expires_at,
    )

    store.resolve_approval(app_id, "APPROVED", approved_rank=1)

    pending = store.get_pending_approvals()
    assert len(pending) == 0

    # Query database directly to verify resolution fields
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM pending_approvals WHERE id = ?", (app_id,)).fetchone()
    conn.close()

    assert row is not None
    assert row["status"] == "APPROVED"
    assert row["approved_rank"] == 1
    assert row["resolved_at"] is not None


def test_resolve_approval_invalid_id_raises(tmp_path):
    db_path = tmp_path / "portfolio.sqlite"
    store = PaperStore(db_path)

    with pytest.raises(ValueError, match="No pending_approval row with id=99999"):
        store.resolve_approval(99999, "APPROVED", approved_rank=1)


def test_resolve_approval_expired(tmp_path):
    db_path = tmp_path / "portfolio.sqlite"
    store = PaperStore(db_path)

    expires_at = (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat()
    app_id = store.create_approval(
        strategy_name="paper_csp_nifty",
        event_type="ENTRY",
        council_output_json='{"decision": "GO"}',
        telegram_msg_id=12345,
        expires_at=expires_at,
    )

    store.resolve_approval(app_id, "EXPIRED")

    pending = store.get_pending_approvals()
    assert len(pending) == 0

    # Query database directly
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM pending_approvals WHERE id = ?", (app_id,)).fetchone()
    conn.close()

    assert row is not None
    assert row["status"] == "EXPIRED"
    assert row["approved_rank"] is None
    assert row["resolved_at"] is not None


def test_multiple_approvals(tmp_path):
    db_path = tmp_path / "portfolio.sqlite"
    store = PaperStore(db_path)

    expires_at = (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat()
    app_id1 = store.create_approval("paper_csp_nifty", "ENTRY", "{}", None, expires_at)
    app_id2 = store.create_approval("paper_csp_nifty", "EXIT", "{}", None, expires_at)

    pending = store.get_pending_approvals()
    assert len(pending) == 2
    assert pending[0]["id"] == app_id1
    assert pending[1]["id"] == app_id2

    store.resolve_approval(app_id1, "REJECTED")
    pending = store.get_pending_approvals()
    assert len(pending) == 1
    assert pending[0]["id"] == app_id2


def test_daemon_heartbeat_roundtrip(tmp_path):
    db_path = tmp_path / "portfolio.sqlite"
    store = PaperStore(db_path)

    # Empty get
    assert store.get_heartbeat() is None

    # Write
    store.write_heartbeat(
        pid=9999, strategies=["paper_csp_nifty", "paper_ic_nifty"], last_event="TICK"
    )

    hb = store.get_heartbeat()
    assert hb is not None
    assert hb["pid"] == 9999
    assert hb["strategies"] == ["paper_csp_nifty", "paper_ic_nifty"]
    assert hb["last_event"] == "TICK"
    assert hb["last_beat"] is not None

    # Upsert/Replace
    store.write_heartbeat(pid=8888, strategies=["paper_csp_nifty"], last_event=None)

    # Check that there is still only 1 row
    conn = sqlite3.connect(db_path)
    count = conn.execute("SELECT count(*) FROM daemon_heartbeat").fetchone()[0]
    conn.close()
    assert count == 1

    hb2 = store.get_heartbeat()
    assert hb2 is not None
    assert hb2["pid"] == 8888
    assert hb2["strategies"] == ["paper_csp_nifty"]
    assert hb2["last_event"] is None


def test_reinit_preserves_existing_trades(tmp_path):
    # Setup database with paper_trades first using old schema/manually or verify via store
    db_path = tmp_path / "portfolio.sqlite"

    # Initialize store to create table and add one trade
    store = PaperStore(db_path)
    trade = PaperTrade(
        strategy_name="paper_csp_nifty",
        leg_role="short_put",
        instrument_key="NIFTY26JUN2422000PE",
        trade_date=date(2026, 6, 1),
        action=TradeAction.BUY,
        quantity=50,
        price=Decimal("150.50"),
        notes="Test trade",
        ivr_at_entry=0.45,
    )
    store.record_trade(trade)
    assert len(store.get_trades("paper_csp_nifty")) == 1

    # Re-initialize the same database to run PaperStore.__init__ (simulating migration / subsequent startup)
    store2 = PaperStore(db_path)
    trades = store2.get_trades("paper_csp_nifty")
    assert len(trades) == 1
    assert trades[0].instrument_key == "NIFTY26JUN2422000PE"
    assert trades[0].quantity == 50
    assert trades[0].price == Decimal("150.50")


def test_council_outputs_crud(tmp_path):
    db_path = tmp_path / "portfolio.sqlite"
    store = PaperStore(db_path)

    expires_at = (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat()
    app_id = store.create_approval(
        strategy_name="paper_csp_nifty",
        event_type="ENTRY",
        council_output_json='{"decision": "GO"}',
        telegram_msg_id=12345,
        expires_at=expires_at,
    )

    # Empty list initially
    assert len(store.get_council_outputs(app_id)) == 0

    # Write
    out_id = store.create_council_output(
        approval_id=app_id,
        persona="Chairman",
        model="deepseek/deepseek-r1-0528",
        prompt_tokens=100,
        output_tokens=120,
        latency_ms=2500,
        response="Approved entries",
    )
    assert isinstance(out_id, int)

    # Read back
    outputs = store.get_council_outputs(app_id)
    assert len(outputs) == 1
    row = outputs[0]
    assert row["id"] == out_id
    assert row["approval_id"] == app_id
    assert row["persona"] == "Chairman"
    assert row["model"] == "deepseek/deepseek-r1-0528"
    assert row["prompt_tokens"] == 100
    assert row["output_tokens"] == 120
    assert row["latency_ms"] == 2500
    assert row["response"] == "Approved entries"
    assert row["created_at"] is not None

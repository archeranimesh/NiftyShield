"""Unit tests for src/mf/store.py.

All tests are fully offline — they use a file-based SQLite DB under pytest's
tmp_path, which is created fresh per test and deleted automatically afterwards.

We do NOT use :memory: because MFStore._connect() opens a new connection on
each call; :memory: would give a fresh empty DB every time, losing all state.

Coverage:
- Schema: both MF tables created; coexists cleanly with PortfolioStore tables.
- mf_transactions: insert, bulk insert, duplicate-skip idempotency, read, date range.
- get_holdings: correct unit accumulation, REDEMPTION subtraction.
- mf_nav_snapshots: upsert insert, upsert update (last-write-wins), bulk upsert,
  date range queries, get_latest_nav.
"""

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from src.mf.models import MFHolding, MFNavSnapshot, MFTransaction, TransactionType
from src.mf.store import MFStore
from src.portfolio.store import PortfolioStore


# ── Fixtures ──────────────────────────────────────────────────────


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "test_portfolio.db"


@pytest.fixture
def store(db_path: Path) -> MFStore:
    return MFStore(db_path)


def make_tx(
    amfi_code: str = "122640",
    scheme_name: str = "Parag Parikh Flexi Cap Fund - Reg Gr",
    transaction_date: date = date(2024, 1, 15),
    units: str = "100.000",
    amount: str = "50000.00",
    transaction_type: TransactionType = TransactionType.INITIAL,
) -> MFTransaction:
    return MFTransaction(
        scheme_name=scheme_name,
        amfi_code=amfi_code,
        transaction_date=transaction_date,
        units=Decimal(units),
        amount=Decimal(amount),
        transaction_type=transaction_type,
    )


def make_nav(
    amfi_code: str = "122640",
    scheme_name: str = "Parag Parikh Flexi Cap Fund - Reg Gr",
    snapshot_date: date = date(2024, 4, 1),
    nav: str = "75.4321",
) -> MFNavSnapshot:
    return MFNavSnapshot(
        snapshot_date=snapshot_date,
        amfi_code=amfi_code,
        scheme_name=scheme_name,
        nav=Decimal(nav),
    )


# ── Schema ────────────────────────────────────────────────────────


def test_mf_tables_created(store: MFStore, db_path: Path) -> None:
    """Both MF tables must exist after initialisation."""
    import sqlite3

    conn = sqlite3.connect(str(db_path))
    tables = {
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    conn.close()
    assert "mf_transactions" in tables
    assert "mf_nav_snapshots" in tables


def test_schema_coexists_with_portfolio_store(db_path: Path) -> None:
    """MFStore and PortfolioStore can both be initialised on the same DB file
    without conflicting — all five tables must coexist cleanly."""
    MFStore(db_path)
    PortfolioStore(db_path)

    import sqlite3

    conn = sqlite3.connect(str(db_path))
    tables = {
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    conn.close()

    expected = {
        "strategies",
        "legs",
        "daily_snapshots",
        "mf_transactions",
        "mf_nav_snapshots",
    }
    assert expected.issubset(tables)


def test_schema_coexists_init_order_reversed(db_path: Path) -> None:
    """Order of initialisation must not matter — portfolio first, then MF."""
    PortfolioStore(db_path)
    MFStore(db_path)

    import sqlite3

    conn = sqlite3.connect(str(db_path))
    tables = {
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    conn.close()
    assert "mf_transactions" in tables
    assert "strategies" in tables


# ── mf_transactions: insert ───────────────────────────────────────


def test_insert_transaction_returns_id(store: MFStore) -> None:
    tx = make_tx()
    row_id = store.insert_transaction(tx)
    assert isinstance(row_id, int)
    assert row_id >= 1


def test_insert_transaction_roundtrip(store: MFStore) -> None:
    tx = make_tx(units="32424.322", amount="1719925.75")
    store.insert_transaction(tx)
    results = store.get_transactions(amfi_code=tx.amfi_code)
    assert len(results) == 1
    result = results[0]
    assert result.scheme_name == tx.scheme_name
    assert result.amfi_code == tx.amfi_code
    assert result.transaction_date == tx.transaction_date
    assert result.units == tx.units
    assert result.amount == tx.amount
    assert result.transaction_type == tx.transaction_type


def test_insert_transaction_idempotent(store: MFStore) -> None:
    """Inserting the same transaction twice must not create a second row."""
    tx = make_tx()
    id1 = store.insert_transaction(tx)
    id2 = store.insert_transaction(tx)
    assert id1 == id2
    assert len(store.get_transactions()) == 1


def test_insert_different_types_same_date_allowed(store: MFStore) -> None:
    """INITIAL and SIP on the same date for the same scheme are distinct rows."""
    tx_initial = make_tx(transaction_type=TransactionType.INITIAL)
    tx_sip = make_tx(
        transaction_type=TransactionType.SIP, amount="5000.00", units="10.000"
    )
    store.insert_transaction(tx_initial)
    store.insert_transaction(tx_sip)
    assert len(store.get_transactions()) == 2


# ── mf_transactions: bulk insert ─────────────────────────────────


def test_insert_transactions_bulk(store: MFStore) -> None:
    txs = [
        make_tx(amfi_code="101281", transaction_date=date(2024, 1, 1)),
        make_tx(
            amfi_code="118989",
            scheme_name="DSP Midcap Fund - Reg Gr",
            transaction_date=date(2024, 1, 1),
        ),
    ]
    count = store.insert_transactions_bulk(txs)
    assert count == 2
    assert len(store.get_transactions()) == 2


def test_insert_transactions_bulk_idempotent(store: MFStore) -> None:
    """Running bulk insert twice must not double the rows."""
    txs = [
        make_tx(amfi_code="101281"),
        make_tx(amfi_code="118989", scheme_name="DSP Midcap Fund - Reg Gr"),
    ]
    store.insert_transactions_bulk(txs)
    store.insert_transactions_bulk(txs)
    assert len(store.get_transactions()) == 2


# ── mf_transactions: read / filter ───────────────────────────────


def test_get_transactions_all(store: MFStore) -> None:
    store.insert_transaction(make_tx(amfi_code="111111"))
    store.insert_transaction(
        make_tx(amfi_code="222222", scheme_name="DSP Midcap Fund - Reg Gr")
    )
    assert len(store.get_transactions()) == 2


def test_get_transactions_filter_amfi_code(store: MFStore) -> None:
    store.insert_transaction(make_tx(amfi_code="111111"))
    store.insert_transaction(
        make_tx(amfi_code="222222", scheme_name="DSP Midcap Fund - Reg Gr")
    )
    results = store.get_transactions(amfi_code="111111")
    assert len(results) == 1
    assert results[0].amfi_code == "111111"


def test_get_transactions_date_range_from(store: MFStore) -> None:
    store.insert_transaction(make_tx(transaction_date=date(2024, 1, 1)))
    store.insert_transaction(
        make_tx(transaction_date=date(2024, 3, 1), transaction_type=TransactionType.SIP)
    )
    results = store.get_transactions(from_date=date(2024, 2, 1))
    assert len(results) == 1
    assert results[0].transaction_date == date(2024, 3, 1)


def test_get_transactions_date_range_to(store: MFStore) -> None:
    store.insert_transaction(make_tx(transaction_date=date(2024, 1, 1)))
    store.insert_transaction(
        make_tx(transaction_date=date(2024, 3, 1), transaction_type=TransactionType.SIP)
    )
    results = store.get_transactions(to_date=date(2024, 2, 1))
    assert len(results) == 1
    assert results[0].transaction_date == date(2024, 1, 1)


def test_get_transactions_date_range_both_bounds(store: MFStore) -> None:
    for d, tt in [
        (date(2024, 1, 1), TransactionType.INITIAL),
        (date(2024, 3, 1), TransactionType.SIP),
        (date(2024, 5, 1), TransactionType.SIP),
    ]:
        store.insert_transaction(make_tx(transaction_date=d, transaction_type=tt))
    results = store.get_transactions(
        from_date=date(2024, 2, 1), to_date=date(2024, 4, 1)
    )
    assert len(results) == 1
    assert results[0].transaction_date == date(2024, 3, 1)


def test_get_transactions_empty(store: MFStore) -> None:
    assert store.get_transactions() == []


# ── get_holdings ──────────────────────────────────────────────────


def test_get_holdings_initial_and_sip(store: MFStore) -> None:
    """INITIAL + SIP units and amounts for the same scheme are summed."""
    store.insert_transaction(
        make_tx(
            amfi_code="101281",
            units="1000.000",
            transaction_type=TransactionType.INITIAL,
        )
    )
    store.insert_transaction(
        make_tx(
            amfi_code="101281",
            units="200.000",
            amount="10000.00",
            transaction_date=date(2024, 2, 1),
            transaction_type=TransactionType.SIP,
        )
    )
    holdings = store.get_holdings()
    h = holdings["101281"]
    assert isinstance(h, MFHolding)
    assert h.amfi_code == "101281"
    assert h.scheme_name == "Parag Parikh Flexi Cap Fund - Reg Gr"
    assert h.total_units == Decimal("1200.000")
    assert h.total_invested == Decimal("60000.00")  # 50000 (INITIAL) + 10000 (SIP)


def test_get_holdings_redemption_reduces_units(store: MFStore) -> None:
    """REDEMPTION subtracts units and amount from the running total."""
    store.insert_transaction(
        make_tx(
            amfi_code="101281",
            units="500.000",
            transaction_type=TransactionType.INITIAL,
        )
    )
    store.insert_transaction(
        make_tx(
            amfi_code="101281",
            units="100.000",
            amount="8000.00",
            transaction_date=date(2024, 3, 1),
            transaction_type=TransactionType.REDEMPTION,
        )
    )
    holdings = store.get_holdings()
    h = holdings["101281"]
    assert h.total_units == Decimal("400.000")
    assert h.total_invested == Decimal("42000.00")  # 50000 − 8000


def test_get_holdings_full_redemption_excluded(store: MFStore) -> None:
    """Scheme fully redeemed must not appear in holdings."""
    store.insert_transaction(
        make_tx(
            amfi_code="101281",
            units="500.000",
            transaction_type=TransactionType.INITIAL,
        )
    )
    store.insert_transaction(
        make_tx(
            amfi_code="101281",
            units="500.000",
            amount="40000.00",
            transaction_date=date(2024, 3, 1),
            transaction_type=TransactionType.REDEMPTION,
        )
    )
    assert "101281" not in store.get_holdings()


def test_get_holdings_multiple_schemes(store: MFStore) -> None:
    store.insert_transaction(make_tx(amfi_code="111111", units="100.000"))
    store.insert_transaction(
        make_tx(
            amfi_code="222222", scheme_name="DSP Midcap Fund - Reg Gr", units="200.000"
        )
    )
    holdings = store.get_holdings()
    assert len(holdings) == 2
    assert holdings["111111"].total_units == Decimal("100.000")
    assert holdings["222222"].total_units == Decimal("200.000")
    assert holdings["111111"].scheme_name == "Parag Parikh Flexi Cap Fund - Reg Gr"
    assert holdings["222222"].scheme_name == "DSP Midcap Fund - Reg Gr"


def test_get_holdings_empty(store: MFStore) -> None:
    assert store.get_holdings() == {}


# ── mf_nav_snapshots: upsert ─────────────────────────────────────


def test_upsert_nav_snapshot_returns_id(store: MFStore) -> None:
    snap = make_nav()
    row_id = store.upsert_nav_snapshot(snap)
    assert isinstance(row_id, int)
    assert row_id >= 1


def test_upsert_nav_snapshot_insert(store: MFStore) -> None:
    snap = make_nav(nav="75.4321")
    store.upsert_nav_snapshot(snap)
    results = store.get_nav_snapshots(snap.amfi_code)
    assert len(results) == 1
    assert results[0].nav == Decimal("75.4321")
    assert results[0].snapshot_date == snap.snapshot_date


def test_upsert_nav_snapshot_updates_existing(store: MFStore) -> None:
    """Second upsert on same (amfi_code, snapshot_date) must overwrite nav."""
    snap_v1 = make_nav(nav="75.0000", snapshot_date=date(2024, 4, 1))
    snap_v2 = make_nav(nav="76.5000", snapshot_date=date(2024, 4, 1))
    store.upsert_nav_snapshot(snap_v1)
    store.upsert_nav_snapshot(snap_v2)
    results = store.get_nav_snapshots(snap_v1.amfi_code)
    assert len(results) == 1
    assert results[0].nav == Decimal("76.5000")


def test_upsert_nav_snapshot_idempotent(store: MFStore) -> None:
    """Upserting identical snapshot twice must leave exactly one row."""
    snap = make_nav()
    store.upsert_nav_snapshot(snap)
    store.upsert_nav_snapshot(snap)
    assert len(store.get_nav_snapshots(snap.amfi_code)) == 1


def test_upsert_nav_snapshots_bulk(store: MFStore) -> None:
    snaps = [
        make_nav(amfi_code="101281", snapshot_date=date(2024, 4, 1), nav="75.00"),
        make_nav(
            amfi_code="118989",
            scheme_name="DSP Midcap Fund - Reg Gr",
            snapshot_date=date(2024, 4, 1),
            nav="82.50",
        ),
    ]
    count = store.upsert_nav_snapshots_bulk(snaps)
    assert count == 2
    assert len(store.get_nav_snapshots("101281")) == 1
    assert len(store.get_nav_snapshots("118989")) == 1


def test_upsert_nav_snapshots_bulk_idempotent(store: MFStore) -> None:
    snaps = [make_nav(nav="75.00")]
    store.upsert_nav_snapshots_bulk(snaps)
    store.upsert_nav_snapshots_bulk(snaps)
    assert len(store.get_nav_snapshots(snaps[0].amfi_code)) == 1


# ── mf_nav_snapshots: read / filter ──────────────────────────────


def test_get_nav_snapshots_date_range(store: MFStore) -> None:
    for d, nav in [
        (date(2024, 1, 1), "70.00"),
        (date(2024, 3, 1), "73.00"),
        (date(2024, 5, 1), "76.00"),
    ]:
        store.upsert_nav_snapshot(make_nav(snapshot_date=d, nav=nav))

    results = store.get_nav_snapshots(
        "122640", from_date=date(2024, 2, 1), to_date=date(2024, 4, 1)
    )
    assert len(results) == 1
    assert results[0].snapshot_date == date(2024, 3, 1)


def test_get_nav_snapshots_from_only(store: MFStore) -> None:
    store.upsert_nav_snapshot(make_nav(snapshot_date=date(2024, 1, 1), nav="70.00"))
    store.upsert_nav_snapshot(make_nav(snapshot_date=date(2024, 6, 1), nav="80.00"))
    results = store.get_nav_snapshots("122640", from_date=date(2024, 3, 1))
    assert len(results) == 1
    assert results[0].snapshot_date == date(2024, 6, 1)


def test_get_nav_snapshots_ordered_ascending(store: MFStore) -> None:
    for d, nav in [(date(2024, 3, 1), "73.00"), (date(2024, 1, 1), "70.00")]:
        store.upsert_nav_snapshot(make_nav(snapshot_date=d, nav=nav))
    results = store.get_nav_snapshots("122640")
    assert results[0].snapshot_date < results[1].snapshot_date


def test_get_nav_snapshots_empty(store: MFStore) -> None:
    assert store.get_nav_snapshots("999999") == []


def test_get_latest_nav(store: MFStore) -> None:
    store.upsert_nav_snapshot(make_nav(snapshot_date=date(2024, 1, 1), nav="70.00"))
    store.upsert_nav_snapshot(make_nav(snapshot_date=date(2024, 6, 1), nav="80.00"))
    latest = store.get_latest_nav("122640")
    assert latest is not None
    assert latest.snapshot_date == date(2024, 6, 1)
    assert latest.nav == Decimal("80.00")


def test_get_latest_nav_none_if_missing(store: MFStore) -> None:
    assert store.get_latest_nav("999999") is None


def test_nav_decimal_precision_preserved(store: MFStore) -> None:
    """NAV precision must survive the TEXT round-trip intact."""
    precise_nav = "123.456789"
    store.upsert_nav_snapshot(make_nav(nav=precise_nav))
    result = store.get_latest_nav("122640")
    assert result is not None
    assert result.nav == Decimal(precise_nav)

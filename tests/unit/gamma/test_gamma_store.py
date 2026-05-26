"""Unit tests for GammaStore and associated models.

Uses an in-memory SQLite database to test DDL creation, CRUD operations,
conflict resolution, and calibration queries.
"""

import datetime
import decimal
import sqlite3

import pytest

from src.gamma.models import GammaChainSnapshot, GammaWatchlistEntry
from src.gamma.store import GammaStore


@pytest.fixture
def db_conn():
    """Fixture to provide a configured in-memory SQLite connection."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    yield conn
    conn.close()


@pytest.fixture
def store(db_conn):
    """Fixture to initialize a GammaStore and create tables."""
    gamma_store = GammaStore()
    gamma_store.create_tables(db_conn)
    return gamma_store


def test_create_tables(db_conn):
    """Verify tables and indexes are created successfully."""
    store = GammaStore()
    # Before create, tables shouldn't exist
    with pytest.raises(sqlite3.OperationalError):
        db_conn.execute("SELECT count(*) FROM gamma_chain_snapshots")

    store.create_tables(db_conn)

    # Tables should exist now
    db_conn.execute("SELECT count(*) FROM gamma_chain_snapshots")
    db_conn.execute("SELECT count(*) FROM gamma_watchlist")


def test_chain_snapshot_roundtrip(store, db_conn):
    """Test inserting a chain snapshot and fetching it back.

    Verifies all fields round-trip and preserve types and timezones.
    """
    snap = GammaChainSnapshot(
        snapshot_date=datetime.date(2026, 5, 26),
        snapshot_time="15:20",
        expiry_date=datetime.date(2026, 5, 28),
        strike=25000,
        option_type="CE",
        dte_calendar=2,
        nifty_spot=decimal.Decimal("25010.50"),
        nifty_futures=decimal.Decimal("25035.75"),
        india_vix=decimal.Decimal("13.45"),
        delta_val=decimal.Decimal("0.5523"),
        gamma_val=decimal.Decimal("0.0012"),
        vega_val=decimal.Decimal("12.45"),
        theta_val=decimal.Decimal("-15.20"),
        iv_val=decimal.Decimal("0.1450"),
        gamma_gearing=decimal.Decimal("5.85"),
        distance_pct=decimal.Decimal("0.0004"),
        best_bid=decimal.Decimal("85.50"),
        best_ask=decimal.Decimal("86.00"),
        bid_ask_spread=decimal.Decimal("0.50"),
        oi=15000,
        oi_change_1d=decimal.Decimal("0.125"),
        volume_day=45000,
        strike_iv_pctile_20d=decimal.Decimal("0.45"),
        gamma_gearing_pctile_dte=decimal.Decimal("0.78"),
        created_at=datetime.datetime(
            2026, 5, 26, 9, 50, 0, tzinfo=datetime.timezone.utc
        ),
    )

    store.insert_chain_snapshot(db_conn, snap)

    results = store.get_chain_snapshots(
        db_conn,
        expiry_date=datetime.date(2026, 5, 28),
        snapshot_date=datetime.date(2026, 5, 26),
    )
    assert len(results) == 1
    fetched = results[0]

    assert fetched.snapshot_date == snap.snapshot_date
    assert fetched.snapshot_time == snap.snapshot_time
    assert fetched.expiry_date == snap.expiry_date
    assert fetched.strike == snap.strike
    assert fetched.option_type == snap.option_type
    assert fetched.dte_calendar == snap.dte_calendar
    assert fetched.nifty_spot == snap.nifty_spot
    assert fetched.nifty_futures == snap.nifty_futures
    assert fetched.india_vix == snap.india_vix
    assert fetched.delta_val == snap.delta_val
    assert fetched.gamma_val == snap.gamma_val
    assert fetched.vega_val == snap.vega_val
    assert fetched.theta_val == snap.theta_val
    assert fetched.iv_val == snap.iv_val
    assert fetched.gamma_gearing == snap.gamma_gearing
    assert fetched.distance_pct == snap.distance_pct
    assert fetched.best_bid == snap.best_bid
    assert fetched.best_ask == snap.best_ask
    assert fetched.bid_ask_spread == snap.bid_ask_spread
    assert fetched.oi == snap.oi
    assert fetched.oi_change_1d == snap.oi_change_1d
    assert fetched.volume_day == snap.volume_day
    assert fetched.strike_iv_pctile_20d == snap.strike_iv_pctile_20d
    assert fetched.gamma_gearing_pctile_dte == snap.gamma_gearing_pctile_dte
    assert fetched.created_at == snap.created_at


def test_chain_snapshot_upsert_on_conflict(store, db_conn):
    """Verify that inserting a snapshot with the same unique constraint
    triggers an update but preserves created_at.
    """
    t1 = datetime.datetime(2026, 5, 26, 9, 50, 0, tzinfo=datetime.timezone.utc)
    snap1 = GammaChainSnapshot(
        snapshot_date=datetime.date(2026, 5, 26),
        snapshot_time="15:20",
        expiry_date=datetime.date(2026, 5, 28),
        strike=25000,
        option_type="CE",
        dte_calendar=2,
        nifty_spot=decimal.Decimal("25000.00"),
        nifty_futures=None,
        india_vix=None,
        delta_val=None,
        gamma_val=None,
        vega_val=None,
        theta_val=None,
        iv_val=decimal.Decimal("0.14"),
        gamma_gearing=decimal.Decimal("4.5"),
        distance_pct=decimal.Decimal("0.0"),
        best_bid=None,
        best_ask=None,
        bid_ask_spread=None,
        oi=1000,
        oi_change_1d=None,
        volume_day=2000,
        strike_iv_pctile_20d=None,
        gamma_gearing_pctile_dte=None,
        created_at=t1,
    )
    store.insert_chain_snapshot(db_conn, snap1)

    t2 = datetime.datetime(2026, 5, 26, 9, 55, 0, tzinfo=datetime.timezone.utc)
    snap2 = GammaChainSnapshot(
        snapshot_date=datetime.date(2026, 5, 26),
        snapshot_time="15:20",
        expiry_date=datetime.date(2026, 5, 28),
        strike=25000,
        option_type="CE",
        dte_calendar=2,
        nifty_spot=decimal.Decimal("25010.00"),  # updated spot
        nifty_futures=decimal.Decimal("25020.00"),
        india_vix=decimal.Decimal("14.0"),
        delta_val=decimal.Decimal("0.5"),
        gamma_val=decimal.Decimal("0.001"),
        vega_val=decimal.Decimal("10.0"),
        theta_val=decimal.Decimal("-10.0"),
        iv_val=decimal.Decimal("0.15"),  # updated IV
        gamma_gearing=decimal.Decimal("5.5"),  # updated gearing
        distance_pct=decimal.Decimal("0.0004"),
        best_bid=decimal.Decimal("50.0"),
        best_ask=decimal.Decimal("51.0"),
        bid_ask_spread=decimal.Decimal("1.0"),
        oi=1200,  # updated OI
        oi_change_1d=decimal.Decimal("0.2"),
        volume_day=2500,  # updated vol
        strike_iv_pctile_20d=decimal.Decimal("0.5"),
        gamma_gearing_pctile_dte=decimal.Decimal("0.6"),
        created_at=t2,  # should be ignored on upsert conflict
    )
    store.insert_chain_snapshot(db_conn, snap2)

    results = store.get_chain_snapshots(
        db_conn,
        expiry_date=datetime.date(2026, 5, 28),
        snapshot_date=datetime.date(2026, 5, 26),
    )
    assert len(results) == 1
    fetched = results[0]
    assert fetched.nifty_spot == decimal.Decimal("25010.00")
    assert fetched.iv_val == decimal.Decimal("0.15")
    assert fetched.gamma_gearing == decimal.Decimal("5.5")
    assert fetched.oi == 1200
    assert fetched.volume_day == 2500
    # verify created_at was NOT overwritten by snap2.created_at (t2)
    assert fetched.created_at == t1


def test_get_yesterday_snapshot(store, db_conn):
    """Verify get_yesterday_snapshot fetches the most recent snapshot
    strictly before today.
    """
    expiry = datetime.date(2026, 5, 28)
    strike = 25000
    opt = "CE"

    # Create helper to build dummy snapshots
    def make_snap(snap_date, time, iv):
        return GammaChainSnapshot(
            snapshot_date=snap_date,
            snapshot_time=time,
            expiry_date=expiry,
            strike=strike,
            option_type=opt,
            dte_calendar=5,
            nifty_spot=decimal.Decimal("25000.00"),
            nifty_futures=None,
            india_vix=None,
            delta_val=None,
            gamma_val=None,
            vega_val=None,
            theta_val=None,
            iv_val=iv,
            gamma_gearing=None,
            distance_pct=None,
            best_bid=None,
            best_ask=None,
            bid_ask_spread=None,
            oi=None,
            oi_change_1d=None,
            volume_day=None,
            strike_iv_pctile_20d=None,
            gamma_gearing_pctile_dte=None,
            created_at=datetime.datetime.now(datetime.timezone.utc),
        )

    # Insert snapshots on 24, 25 (twice), and 26 May
    store.insert_chain_snapshot(
        db_conn,
        make_snap(
            datetime.date(2026, 5, 24), "15:20", decimal.Decimal("0.12")
        ),
    )
    store.insert_chain_snapshot(
        db_conn,
        make_snap(
            datetime.date(2026, 5, 25), "10:30", decimal.Decimal("0.13")
        ),
    )
    store.insert_chain_snapshot(
        db_conn,
        make_snap(
            datetime.date(2026, 5, 25), "15:20", decimal.Decimal("0.14")
        ),
    )
    store.insert_chain_snapshot(
        db_conn,
        make_snap(
            datetime.date(2026, 5, 26), "15:20", decimal.Decimal("0.15")
        ),
    )

    # Query with today = 2026-05-26. Should get 2026-05-25 15:20 snapshot
    yesterday = store.get_yesterday_snapshot(
        db_conn, expiry, strike, opt, today=datetime.date(2026, 5, 26)
    )
    assert yesterday is not None
    assert yesterday.snapshot_date == datetime.date(2026, 5, 25)
    assert yesterday.snapshot_time == "15:20"
    assert yesterday.iv_val == decimal.Decimal("0.14")

    # Query with today = 2026-05-25. Should get 2026-05-24 snapshot
    yesterday = store.get_yesterday_snapshot(
        db_conn, expiry, strike, opt, today=datetime.date(2026, 5, 25)
    )
    assert yesterday is not None
    assert yesterday.snapshot_date == datetime.date(2026, 5, 24)
    assert yesterday.iv_val == decimal.Decimal("0.12")

    # Query with today = 2026-05-23. Should return None
    yesterday = store.get_yesterday_snapshot(
        db_conn, expiry, strike, opt, today=datetime.date(2026, 5, 23)
    )
    assert yesterday is None


def test_watchlist_operations(store, db_conn):
    """Test watchlist upsert, active queries, and removal updates."""
    expiry = datetime.date(2026, 5, 28)

    entry1 = GammaWatchlistEntry(
        expiry_date=expiry,
        strike=25000,
        option_type="CE",
        added_date=datetime.date(2026, 5, 25),
        last_seen_date=datetime.date(2026, 5, 26),
        removed_date=None,
        removal_reason=None,
        distance_pct=decimal.Decimal("0.015"),
        gamma_gearing=decimal.Decimal("4.5"),
        oi=2500,
        oi_change_1d=decimal.Decimal("0.15"),
        days_on_watchlist=2,
        elevated=False,
        elevation_reason=None,
    )

    entry2 = GammaWatchlistEntry(
        expiry_date=expiry,
        strike=24900,
        option_type="PE",
        added_date=datetime.date(2026, 5, 26),
        last_seen_date=datetime.date(2026, 5, 26),
        removed_date=None,
        removal_reason=None,
        distance_pct=decimal.Decimal("0.02"),
        gamma_gearing=decimal.Decimal("6.2"),
        oi=5000,
        oi_change_1d=decimal.Decimal("0.35"),
        days_on_watchlist=1,
        elevated=True,
        elevation_reason="Aggressive OI build",
    )

    store.upsert_watchlist(db_conn, entry1)
    store.upsert_watchlist(db_conn, entry2)

    # Fetch active watchlist
    active = store.get_active_watchlist(db_conn, expiry)
    assert len(active) == 2
    # Ordered by strike (24900 first, then 25000)
    assert active[0].strike == 24900
    assert active[0].elevated is True
    assert active[0].elevation_reason == "Aggressive OI build"
    assert active[1].strike == 25000
    assert active[1].elevated is False

    # Update entry1 to be elevated
    entry1_updated = GammaWatchlistEntry(
        expiry_date=expiry,
        strike=25000,
        option_type="CE",
        added_date=datetime.date(2026, 5, 25),
        last_seen_date=datetime.date(2026, 5, 26),
        removed_date=None,
        removal_reason=None,
        distance_pct=decimal.Decimal("0.012"),
        gamma_gearing=decimal.Decimal("5.1"),
        oi=3000,
        oi_change_1d=decimal.Decimal("0.20"),
        days_on_watchlist=2,
        elevated=True,  # updated to True
        elevation_reason="Now elevated",
    )
    store.upsert_watchlist(db_conn, entry1_updated)

    active = store.get_active_watchlist(db_conn, expiry)
    assert len(active) == 2
    assert active[1].strike == 25000
    assert active[1].elevated is True
    assert active[1].elevation_reason == "Now elevated"

    # Remove entry1 from watchlist - should return True
    assert store.remove_from_watchlist(
        db_conn,
        expiry,
        25000,
        "CE",
        "spot_moved_away",
        datetime.date(2026, 5, 27),
    ) is True

    # Try removing non-existing entry - should return False
    assert store.remove_from_watchlist(
        db_conn,
        expiry,
        25200,
        "CE",
        "spot_moved_away",
        datetime.date(2026, 5, 27),
    ) is False

    # Active watchlist should now only contain entry2
    active = store.get_active_watchlist(db_conn, expiry)
    assert len(active) == 1
    assert active[0].strike == 24900

    # Let's verify entry1 is still in DB but marked as removed
    rows = db_conn.execute(
        "SELECT * FROM gamma_watchlist WHERE strike = 25000"
    ).fetchall()
    assert len(rows) == 1
    assert rows[0]["removed_date"] == "2026-05-27"
    assert rows[0]["removal_reason"] == "spot_moved_away"


def test_get_iv_history(store, db_conn):
    """Test get_iv_history returns chronologically ordered IV values
    cross-expiry.
    """
    strike = 25000
    opt = "CE"

    def insert_snap(dt_val, iv_val, expiry_val, snap_time="15:20"):
        snap = GammaChainSnapshot(
            snapshot_date=dt_val,
            snapshot_time=snap_time,
            expiry_date=expiry_val,
            strike=strike,
            option_type=opt,
            dte_calendar=2,
            nifty_spot=decimal.Decimal("25000.00"),
            nifty_futures=None,
            india_vix=None,
            delta_val=None,
            gamma_val=None,
            vega_val=None,
            theta_val=None,
            iv_val=iv_val,
            gamma_gearing=None,
            distance_pct=None,
            best_bid=None,
            best_ask=None,
            bid_ask_spread=None,
            oi=None,
            oi_change_1d=None,
            volume_day=None,
            strike_iv_pctile_20d=None,
            gamma_gearing_pctile_dte=None,
            created_at=datetime.datetime.now(datetime.timezone.utc),
        )
        store.insert_chain_snapshot(db_conn, snap)

    # Insert snapshots on 2026-05-10, 2026-05-11, 2026-05-17, 2026-05-18
    # and add a second snapshot on 2026-05-18 to test distinct days logic
    insert_snap(
        datetime.date(2026, 5, 10),
        decimal.Decimal("0.12"),
        datetime.date(2026, 5, 14),
    )
    insert_snap(
        datetime.date(2026, 5, 11),
        decimal.Decimal("0.13"),
        datetime.date(2026, 5, 14),
    )
    insert_snap(
        datetime.date(2026, 5, 17),
        decimal.Decimal("0.14"),
        datetime.date(2026, 5, 21),
    )
    insert_snap(
        datetime.date(2026, 5, 18),
        decimal.Decimal("0.15"),
        datetime.date(2026, 5, 21),
        "10:30",
    )
    insert_snap(
        datetime.date(2026, 5, 18),
        decimal.Decimal("0.16"),
        datetime.date(2026, 5, 21),
        "15:20",
    )

    # Fetch history with limit_days=3.
    # The distinct days are May 18 (gives May 18 10:30 and 15:20),
    # May 17 (gives May 17 15:20), and May 11 (gives May 11 15:20).
    # Chronological ordering should return May 11, May 17, May 18 (10:30),
    # May 18 (15:20).
    history = store.get_iv_history(db_conn, strike, opt, limit_days=3)
    assert history == [
        decimal.Decimal("0.13"),
        decimal.Decimal("0.14"),
        decimal.Decimal("0.15"),
        decimal.Decimal("0.16"),
    ]


def test_get_gearing_by_dte(store, db_conn):
    """Test get_gearing_by_dte correctly filters by target_dte and
    limits snapshot dates.
    """
    def insert_snap(dt_val, time_val, expiry_val, dte, gearing):
        snap = GammaChainSnapshot(
            snapshot_date=dt_val,
            snapshot_time=time_val,
            expiry_date=expiry_val,
            strike=25000,
            option_type="CE",
            dte_calendar=dte,
            nifty_spot=decimal.Decimal("25000.00"),
            nifty_futures=None,
            india_vix=None,
            delta_val=None,
            gamma_val=None,
            vega_val=None,
            theta_val=None,
            iv_val=None,
            gamma_gearing=gearing,
            distance_pct=None,
            best_bid=None,
            best_ask=None,
            bid_ask_spread=None,
            oi=None,
            oi_change_1d=None,
            volume_day=None,
            strike_iv_pctile_20d=None,
            gamma_gearing_pctile_dte=None,
            created_at=datetime.datetime.now(datetime.timezone.utc),
        )
        store.insert_chain_snapshot(db_conn, snap)

    # Insert snapshots on 24, 25, and 26 May with DTE = 0 or 1
    insert_snap(
        datetime.date(2026, 5, 24),
        "15:20",
        datetime.date(2026, 5, 24),
        0,
        decimal.Decimal("8.5"),
    )
    insert_snap(
        datetime.date(2026, 5, 25),
        "15:20",
        datetime.date(2026, 5, 25),
        0,
        decimal.Decimal("9.2"),
    )
    insert_snap(
        datetime.date(2026, 5, 26),
        "15:20",
        datetime.date(2026, 5, 26),
        0,
        decimal.Decimal("10.1"),
    )

    # Snapshot on same date but different DTE
    insert_snap(
        datetime.date(2026, 5, 26),
        "15:20",
        datetime.date(2026, 5, 27),
        1,
        decimal.Decimal("3.2"),
    )

    # Fetch gearing for DTE = 0, limit_days = 2 (dates 25 and 26)
    gearing_list = store.get_gearing_by_dte(
        db_conn, target_dte=0, limit_days=2
    )
    # Should get [10.1, 9.2] (descending order by date/time)
    assert gearing_list == [decimal.Decimal("10.1"), decimal.Decimal("9.2")]

    # Fetch gearing for DTE = 1
    gearing_list_dte1 = store.get_gearing_by_dte(
        db_conn, target_dte=1, limit_days=2
    )
    assert gearing_list_dte1 == [decimal.Decimal("3.2")]

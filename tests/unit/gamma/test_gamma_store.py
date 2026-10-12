"""Unit tests for GammaStore and associated models.

Uses an in-memory SQLite database to test DDL creation, CRUD operations,
conflict resolution, and calibration queries.
"""

import datetime
import decimal
import sqlite3
import typing

import pytest

from src.gamma.models import (
    GammaChainSnapshot,
    GammaSignalLogEntry,
    GammaWatchlistEntry,
)
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
        created_at=datetime.datetime(2026, 5, 26, 9, 50, 0, tzinfo=datetime.timezone.utc),
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
        make_snap(datetime.date(2026, 5, 24), "15:20", decimal.Decimal("0.12")),
    )
    store.insert_chain_snapshot(
        db_conn,
        make_snap(datetime.date(2026, 5, 25), "10:30", decimal.Decimal("0.13")),
    )
    store.insert_chain_snapshot(
        db_conn,
        make_snap(datetime.date(2026, 5, 25), "15:20", decimal.Decimal("0.14")),
    )
    store.insert_chain_snapshot(
        db_conn,
        make_snap(datetime.date(2026, 5, 26), "15:20", decimal.Decimal("0.15")),
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
    assert (
        store.remove_from_watchlist(
            db_conn,
            expiry,
            25000,
            "CE",
            "spot_moved_away",
            datetime.date(2026, 5, 27),
        )
        is True
    )

    # Try removing non-existing entry - should return False
    assert (
        store.remove_from_watchlist(
            db_conn,
            expiry,
            25200,
            "CE",
            "spot_moved_away",
            datetime.date(2026, 5, 27),
        )
        is False
    )

    # Active watchlist should now only contain entry2
    active = store.get_active_watchlist(db_conn, expiry)
    assert len(active) == 1
    assert active[0].strike == 24900

    # Let's verify entry1 is still in DB but marked as removed
    rows = db_conn.execute("SELECT * FROM gamma_watchlist WHERE strike = 25000").fetchall()
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
    gearing_list = store.get_gearing_by_dte(db_conn, target_dte=0, limit_days=2)
    # Should get [10.1, 9.2] (descending order by date/time)
    assert gearing_list == [decimal.Decimal("10.1"), decimal.Decimal("9.2")]

    # Fetch gearing for DTE = 1
    gearing_list_dte1 = store.get_gearing_by_dte(db_conn, target_dte=1, limit_days=2)
    assert gearing_list_dte1 == [decimal.Decimal("3.2")]


def _prior_snap(date: datetime.date, time: str, strike: int, oi: int | None) -> GammaChainSnapshot:
    return GammaChainSnapshot(
        snapshot_date=date,
        snapshot_time=time,
        expiry_date=datetime.date(2026, 5, 28),
        strike=strike,
        option_type="CE",
        dte_calendar=2,
        nifty_spot=decimal.Decimal("25000"),
        nifty_futures=None,
        india_vix=None,
        delta_val=None,
        gamma_val=None,
        vega_val=None,
        theta_val=None,
        iv_val=None,
        gamma_gearing=None,
        distance_pct=None,
        best_bid=None,
        best_ask=None,
        bid_ask_spread=None,
        oi=oi,
        oi_change_1d=None,
        volume_day=None,
        strike_iv_pctile_20d=None,
        gamma_gearing_pctile_dte=None,
        created_at=datetime.datetime(2026, 5, 26, 9, 50, tzinfo=datetime.timezone.utc),
    )


def test_get_prior_oi_returns_latest_pre_today_per_key(store, db_conn):
    expiry = datetime.date(2026, 5, 28)
    today = datetime.date(2026, 5, 27)
    for snap in (
        _prior_snap(datetime.date(2026, 5, 25), "15:20", 25000, 100),
        _prior_snap(datetime.date(2026, 5, 26), "09:20", 25000, 200),
        _prior_snap(datetime.date(2026, 5, 26), "15:20", 25000, 300),
        _prior_snap(datetime.date(2026, 5, 26), "15:20", 25100, None),
        _prior_snap(today, "09:20", 25000, 999),
    ):
        store.insert_chain_snapshot(db_conn, snap)

    assert store.get_prior_oi(db_conn, expiry, today) == {(25000, "CE"): 300}


def test_get_prior_oi_empty_store(store, db_conn):
    assert store.get_prior_oi(db_conn, datetime.date(2026, 5, 28), datetime.date(2026, 5, 27)) == {}


def test_get_prior_snapshots_latest_per_date_excludes_today(store, db_conn):
    expiry = datetime.date(2026, 5, 28)
    today = datetime.date(2026, 5, 27)
    for snap in (
        _prior_snap(datetime.date(2026, 5, 22), "15:20", 25000, 50),
        _prior_snap(datetime.date(2026, 5, 25), "15:20", 25000, 100),
        _prior_snap(datetime.date(2026, 5, 26), "09:20", 25000, 200),
        _prior_snap(datetime.date(2026, 5, 26), "15:20", 25000, 300),
        _prior_snap(datetime.date(2026, 5, 26), "15:20", 25100, 400),
        _prior_snap(today, "09:20", 25000, 999),
    ):
        store.insert_chain_snapshot(db_conn, snap)

    got = store.get_prior_snapshots(db_conn, expiry, today, days=2)

    assert [(s.snapshot_date.day, s.strike, s.oi) for s in got] == [
        (26, 25000, 300),
        (26, 25100, 400),
        (25, 25000, 100),
    ]


def test_get_prior_snapshots_empty_store(store, db_conn):
    got = store.get_prior_snapshots(
        db_conn, datetime.date(2026, 5, 28), datetime.date(2026, 5, 27), days=3
    )
    assert got == []


def _wl_entry(expiry: datetime.date, strike: int, removed: bool) -> GammaWatchlistEntry:
    return GammaWatchlistEntry(
        expiry_date=expiry,
        strike=strike,
        option_type="CE",
        added_date=datetime.date(2026, 5, 20),
        last_seen_date=datetime.date(2026, 5, 20),
        removed_date=datetime.date(2026, 5, 21) if removed else None,
        removal_reason="expired" if removed else None,
        distance_pct=None,
        gamma_gearing=None,
        oi=None,
        oi_change_1d=None,
        days_on_watchlist=1,
        elevated=False,
        elevation_reason=None,
    )


def test_get_all_active_watchlist_spans_expiries_and_skips_removed(store, db_conn):
    e1, e2 = datetime.date(2026, 5, 19), datetime.date(2026, 5, 26)
    for entry in (
        _wl_entry(e2, 25000, False),
        _wl_entry(e1, 24900, False),
        _wl_entry(e1, 24800, True),
    ):
        store.upsert_watchlist(db_conn, entry)

    got = store.get_all_active_watchlist(db_conn)

    assert [(g.expiry_date, g.strike) for g in got] == [(e1, 24900), (e2, 25000)]


def test_get_all_active_watchlist_empty(store, db_conn):
    assert store.get_all_active_watchlist(db_conn) == []


def _calib_snap(
    date: datetime.date,
    time: str = "15:20",
    *,
    iv: str | None = None,
    gearing: str | None = None,
    dte: int = 2,
    strike: int = 25000,
) -> GammaChainSnapshot:
    return GammaChainSnapshot(
        snapshot_date=date,
        snapshot_time=time,
        expiry_date=datetime.date(2026, 6, 30),
        strike=strike,
        option_type="CE",
        dte_calendar=dte,
        nifty_spot=decimal.Decimal("25000"),
        nifty_futures=None,
        india_vix=None,
        delta_val=None,
        gamma_val=None,
        vega_val=None,
        theta_val=None,
        iv_val=decimal.Decimal(iv) if iv else None,
        gamma_gearing=decimal.Decimal(gearing) if gearing else None,
        distance_pct=None,
        best_bid=None,
        best_ask=None,
        bid_ask_spread=None,
        oi=None,
        oi_change_1d=None,
        volume_day=None,
        strike_iv_pctile_20d=None,
        gamma_gearing_pctile_dte=None,
        created_at=datetime.datetime(2026, 6, 1, tzinfo=datetime.timezone.utc),
    )


def test_update_percentiles_writes_only_given_columns(store, db_conn):
    snap = _calib_snap(datetime.date(2026, 6, 1), iv="0.15", gearing="4.0")
    store.insert_chain_snapshot(db_conn, snap)
    key = {
        "snapshot_date": snap.snapshot_date,
        "snapshot_time": "15:20",
        "expiry_date": snap.expiry_date,
        "strike": 25000,
        "option_type": "CE",
    }

    assert store.update_percentiles(db_conn, **key, iv_pctile=decimal.Decimal("0.35")) is True
    assert store.update_percentiles(db_conn, **key, gearing_pctile=decimal.Decimal("0.8")) is True

    (row,) = store.get_chain_snapshots(db_conn, snap.expiry_date, snap.snapshot_date)
    assert row.strike_iv_pctile_20d == decimal.Decimal("0.35")  # not clobbered by 2nd call
    assert row.gamma_gearing_pctile_dte == decimal.Decimal("0.8")
    assert row.iv_val == decimal.Decimal("0.15")


def test_update_percentiles_unknown_key_is_noop(store, db_conn):
    ok = store.update_percentiles(
        db_conn,
        snapshot_date=datetime.date(2026, 6, 1),
        snapshot_time="15:20",
        expiry_date=datetime.date(2026, 6, 30),
        strike=99999,
        option_type="CE",
        iv_pctile=decimal.Decimal("0.5"),
    )
    assert ok is False


def test_get_iv_history_before_one_value_per_prior_day(store, db_conn):
    d1, d2, today = (datetime.date(2026, 6, n) for n in (1, 2, 3))
    store.insert_chain_snapshot(db_conn, _calib_snap(d1, "09:30", iv="0.10"))
    store.insert_chain_snapshot(db_conn, _calib_snap(d1, "15:20", iv="0.11"))
    store.insert_chain_snapshot(db_conn, _calib_snap(d2, "15:20", iv="0.12"))
    store.insert_chain_snapshot(db_conn, _calib_snap(today, "15:20", iv="0.99"))

    hist = store.get_iv_history(db_conn, 25000, "CE", limit_days=20, before=today)

    assert hist == [decimal.Decimal("0.11"), decimal.Decimal("0.12")]


def test_get_iv_history_before_empty(store, db_conn):
    assert store.get_iv_history(db_conn, 25000, "CE", before=datetime.date(2026, 6, 3)) == []


def test_gearing_before_and_distinct_day_count(store, db_conn):
    d1, today = datetime.date(2026, 6, 1), datetime.date(2026, 6, 2)
    for strike in (25000, 25100, 25200):  # 3 rows on d1, 2 snapshot times
        store.insert_chain_snapshot(db_conn, _calib_snap(d1, "09:30", gearing="4", strike=strike))
        store.insert_chain_snapshot(db_conn, _calib_snap(d1, "15:20", gearing="5", strike=strike))
    store.insert_chain_snapshot(db_conn, _calib_snap(today, gearing="9"))

    vals = store.get_gearing_by_dte(db_conn, 2, 60, before=today)

    assert len(vals) == 6 and decimal.Decimal("9") not in vals
    assert store.count_prior_gearing_days(db_conn, 2, today) == 1  # rows != days
    assert store.count_prior_gearing_days(db_conn, 2, d1) == 0  # today excluded
    assert store.count_prior_gearing_days(db_conn, 7, today) == 0  # other DTE


def _sample_signal_entry(
    signal_id: str = "SIG-20260601-25000-CE",
    option_type: typing.Literal["CE", "PE"] = "CE",
    paper_trade_filled: bool = False,
    exit_timestamp: datetime.datetime | None = None,
    f0_hard_pass: bool | None = None,
    option_price_rising: bool | None = None,
    best_bid: decimal.Decimal | None = decimal.Decimal("4.50"),
    naive_ts: bool = False,
) -> GammaSignalLogEntry:
    if naive_ts:
        sig_ts = datetime.datetime(2026, 6, 1, 9, 35, 0)
    else:
        sig_ts = datetime.datetime(2026, 6, 1, 9, 35, 0, tzinfo=datetime.timezone.utc)

    created_at = datetime.datetime(2026, 6, 1, 9, 35, 1, tzinfo=datetime.timezone.utc)

    return GammaSignalLogEntry(
        signal_id=signal_id,
        signal_timestamp=sig_ts,
        expiry_date=datetime.date(2026, 6, 2),
        strike=25000,
        option_type=option_type,
        dte_calendar=1,
        dte_trading=1,
        watchlist_hit=True,
        watchlist_elevated=False,
        nifty_spot=decimal.Decimal("24950.25"),
        nifty_futures_price=decimal.Decimal("24970.00"),
        futures_basis=decimal.Decimal("19.75"),
        underlying_return_1m=decimal.Decimal("0.0005"),
        underlying_return_5m=decimal.Decimal("0.0015"),
        underlying_return_15m=decimal.Decimal("0.0035"),
        underlying_rvol_15m=decimal.Decimal("0.1250"),
        distance_pct=decimal.Decimal("0.0020"),
        distance_sigma=decimal.Decimal("0.85"),
        best_bid=best_bid,
        best_ask=decimal.Decimal("4.60"),
        bid_ask_spread=decimal.Decimal("0.10"),
        spread_pct_of_mid=decimal.Decimal("0.022"),
        bid_qty_l1=150,
        ask_qty_l1=300,
        total_bid_qty=1500,
        total_ask_qty=2250,
        delta_val=decimal.Decimal("0.18"),
        gamma_val=decimal.Decimal("0.0012"),
        vega_val=decimal.Decimal("2.45"),
        theta_val=decimal.Decimal("-8.20"),
        iv_val=decimal.Decimal("0.1450"),
        gamma_gearing=decimal.Decimal("162.39"),
        speed_5m=decimal.Decimal("0.0002"),
        speed_5m_unavailable=False,
        theoretical_price=decimal.Decimal("5.10"),
        model_edge=decimal.Decimal("0.50"),
        strike_iv_pctile_20d=decimal.Decimal("0.25"),
        gearing_threshold_used=decimal.Decimal("5.0"),
        volume_5m=5000,
        volume_zscore_5m=decimal.Decimal("2.45"),
        oi_now=25000,
        oi_velocity_15m=decimal.Decimal("0.18"),
        option_price_rising=option_price_rising,
        india_vix=decimal.Decimal("13.40"),
        india_vix_pctile_252d=decimal.Decimal("0.45"),
        event_flag=False,
        event_type=None,
        f0_hard_pass=f0_hard_pass,
        f0_fail_reason=None,
        f1_directional_pass=True,
        f2_convexity_pass=True,
        f3_quality_pass=True,
        f3_quality_method="A",
        f4_flow_pass=True,
        signal_triggered=True,
        paper_trade_attempted=True,
        paper_trade_filled=paper_trade_filled,
        entry_fill_price=decimal.Decimal("4.60") if paper_trade_filled else None,
        fill_timestamp=(
            datetime.datetime(2026, 6, 1, 9, 35, 5, tzinfo=datetime.timezone.utc)
            if paper_trade_filled
            else None
        ),
        unfilled_reason=None,
        exit_price=decimal.Decimal("7.20") if exit_timestamp else None,
        exit_timestamp=exit_timestamp,
        exit_reason="E1" if exit_timestamp else None,
        mfe=decimal.Decimal("3.00") if exit_timestamp else None,
        mae=decimal.Decimal("-0.40") if exit_timestamp else None,
        realised_r_multiple=decimal.Decimal("2.50") if exit_timestamp else None,
        created_at=created_at,
    )


def test_signal_log_roundtrip_decimal_exactness(store, db_conn):
    """Test full insert and read back verifying exact Decimal precision."""
    entry = _sample_signal_entry("SIG-ROUNDTRIP-1")
    store.insert_signal_log(db_conn, entry)

    cur = db_conn.execute("SELECT * FROM gamma_signal_log WHERE signal_id = 'SIG-ROUNDTRIP-1'")
    from src.gamma.store import _row_to_signal_log_entry

    fetched = _row_to_signal_log_entry(cur.fetchone())

    assert fetched.signal_id == "SIG-ROUNDTRIP-1"
    assert fetched.nifty_spot == decimal.Decimal("24950.25")
    assert fetched.gamma_val == decimal.Decimal("0.0012")
    assert fetched.gamma_gearing == decimal.Decimal("162.39")
    assert fetched.best_ask == decimal.Decimal("4.60")
    assert fetched.watchlist_hit is True
    assert fetched.watchlist_elevated is False
    assert fetched.signal_timestamp == entry.signal_timestamp
    assert fetched.created_at == entry.created_at


def test_signal_log_create_tables_idempotent(db_conn):
    """Test re-running create_tables is a no-op."""
    store = GammaStore()
    store.create_tables(db_conn)
    entry = _sample_signal_entry("SIG-IDEMPOTENT-1")
    store.insert_signal_log(db_conn, entry)

    # Re-running create_tables should not wipe data or error
    store.create_tables(db_conn)
    cur = db_conn.execute("SELECT count(*) as c FROM gamma_signal_log")
    assert cur.fetchone()["c"] == 1


def test_signal_log_tristate_none_vs_false_roundtrip(store, db_conn):
    """Test tri-state boolean columns preserve None vs False."""
    entry_none = _sample_signal_entry("SIG-TRI-NONE", f0_hard_pass=None, option_price_rising=None)
    entry_false = _sample_signal_entry(
        "SIG-TRI-FALSE", f0_hard_pass=False, option_price_rising=False
    )

    store.insert_signal_log(db_conn, entry_none)
    store.insert_signal_log(db_conn, entry_false)

    from src.gamma.store import _row_to_signal_log_entry

    r_none = _row_to_signal_log_entry(
        db_conn.execute(
            "SELECT * FROM gamma_signal_log WHERE signal_id = 'SIG-TRI-NONE'"
        ).fetchone()
    )
    r_false = _row_to_signal_log_entry(
        db_conn.execute(
            "SELECT * FROM gamma_signal_log WHERE signal_id = 'SIG-TRI-FALSE'"
        ).fetchone()
    )

    assert r_none.f0_hard_pass is None
    assert r_none.option_price_rising is None

    assert r_false.f0_hard_pass is False
    assert r_false.option_price_rising is False


def test_signal_log_nullable_decimal_roundtrip(store, db_conn):
    """Test nullable Decimal fields remain None vs populated Decimal."""
    entry_nulls = _sample_signal_entry("SIG-NULL-DEC", best_bid=None)
    store.insert_signal_log(db_conn, entry_nulls)

    from src.gamma.store import _row_to_signal_log_entry

    r = _row_to_signal_log_entry(
        db_conn.execute(
            "SELECT * FROM gamma_signal_log WHERE signal_id = 'SIG-NULL-DEC'"
        ).fetchone()
    )
    assert r.best_bid is None
    assert r.best_ask == decimal.Decimal("4.60")


def test_signal_log_duplicate_id_and_naive_ts_rejection(store, db_conn):
    """Test duplicate signal_id raises IntegrityError and naive timestamps raise ValueError."""
    entry = _sample_signal_entry("SIG-DUP-1")
    store.insert_signal_log(db_conn, entry)

    # Duplicate signal_id must raise sqlite3.IntegrityError
    with pytest.raises(sqlite3.IntegrityError):
        store.insert_signal_log(db_conn, entry)

    # Naive timestamp must raise ValueError
    entry_naive = _sample_signal_entry("SIG-NAIVE-1", naive_ts=True)
    with pytest.raises(ValueError, match="must be a timezone-aware UTC datetime"):
        store.insert_signal_log(db_conn, entry_naive)


def test_update_signal_exit_unknown_or_already_exited(store, db_conn):
    """Test update_signal_exit returns False for unknown id or already exited row."""
    # Unknown ID returns False
    exit_ts = datetime.datetime(2026, 6, 1, 10, 0, 0, tzinfo=datetime.timezone.utc)
    ok = store.update_signal_exit(
        db_conn,
        "NON-EXISTENT",
        exit_price=decimal.Decimal("5.0"),
        exit_timestamp=exit_ts,
        exit_reason="E1",
    )
    assert ok is False

    # Insert open filled position
    entry = _sample_signal_entry("SIG-EXIT-1", paper_trade_filled=True)
    store.insert_signal_log(db_conn, entry)

    # First exit succeeds
    ok1 = store.update_signal_exit(
        db_conn,
        "SIG-EXIT-1",
        exit_price=decimal.Decimal("6.50"),
        exit_timestamp=exit_ts,
        exit_reason="E1",
        realised_r_multiple=decimal.Decimal("2.0"),
    )
    assert ok1 is True

    # Double-exit on already exited row must return False
    ok2 = store.update_signal_exit(
        db_conn,
        "SIG-EXIT-1",
        exit_price=decimal.Decimal("7.00"),
        exit_timestamp=exit_ts,
        exit_reason="E2",
    )
    assert ok2 is False

    # Naive exit timestamp rejected
    naive_exit = datetime.datetime(2026, 6, 1, 10, 0, 0)
    with pytest.raises(ValueError, match="must be a timezone-aware UTC datetime"):
        store.update_signal_exit(
            db_conn,
            "SIG-EXIT-1",
            exit_price=decimal.Decimal("6.50"),
            exit_timestamp=naive_exit,
            exit_reason="E1",
        )


def test_get_open_signal_positions_filtering(store, db_conn):
    """Test get_open_signal_positions returns only paper_trade_filled=1 and exit_timestamp IS NULL."""
    exit_ts = datetime.datetime(2026, 6, 1, 10, 0, 0, tzinfo=datetime.timezone.utc)

    # 1. Open CE position
    store.insert_signal_log(
        db_conn, _sample_signal_entry("SIG-OPEN-CE", option_type="CE", paper_trade_filled=True)
    )
    # 2. Open PE position
    store.insert_signal_log(
        db_conn, _sample_signal_entry("SIG-OPEN-PE", option_type="PE", paper_trade_filled=True)
    )
    # 3. Unfilled attempt (paper_trade_filled=False)
    store.insert_signal_log(
        db_conn, _sample_signal_entry("SIG-UNFILLED", option_type="CE", paper_trade_filled=False)
    )
    # 4. Exited position (paper_trade_filled=True, exit_timestamp set)
    store.insert_signal_log(
        db_conn,
        _sample_signal_entry(
            "SIG-EXITED", option_type="CE", paper_trade_filled=True, exit_timestamp=exit_ts
        ),
    )

    # All open positions
    open_all = store.get_open_signal_positions(db_conn)
    assert [p.signal_id for p in open_all] == ["SIG-OPEN-CE", "SIG-OPEN-PE"]

    # Filtered by option_type
    open_ce = store.get_open_signal_positions(db_conn, option_type="CE")
    assert [p.signal_id for p in open_ce] == ["SIG-OPEN-CE"]

    open_pe = store.get_open_signal_positions(db_conn, option_type="PE")
    assert [p.signal_id for p in open_pe] == ["SIG-OPEN-PE"]


def test_update_signal_exit_null_price_stores_null(store, db_conn):
    """A time stop with no bid exits with a NULL exit_price (GS-4 contract)."""
    store.insert_signal_log(db_conn, _sample_signal_entry("SIG-NULLPX", paper_trade_filled=True))
    exit_ts = datetime.datetime(2026, 6, 1, 10, 0, 0, tzinfo=datetime.timezone.utc)
    ok = store.update_signal_exit(
        db_conn, "SIG-NULLPX", exit_price=None, exit_timestamp=exit_ts, exit_reason="E3_TIME_STOP"
    )
    assert ok is True
    row = db_conn.execute(
        "SELECT exit_price, exit_reason FROM gamma_signal_log WHERE signal_id = 'SIG-NULLPX'"
    ).fetchone()
    assert row["exit_price"] is None
    assert row["exit_reason"] == "E3_TIME_STOP"

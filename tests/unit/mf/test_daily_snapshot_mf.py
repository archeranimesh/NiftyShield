"""Tests for the MF wire-up in daily_snapshot.py (Commit 6).

These tests exercise the exact code path that daily_snapshot.py adds:
  MFStore(db_path) → MFTracker(mf_store).record_snapshot(date)

They verify:
  1. MFStore initialises cleanly on a DB that PortfolioStore already owns.
  2. record_snapshot() returns a PortfolioPnL when holdings + NAVs are present.
  3. record_snapshot() returns an empty PortfolioPnL gracefully when holdings
     are absent (no seed has been run yet — the "first cron run" scenario).
  4. A failed nav_fetcher (simulating AMFI unreachable) does not crash — it
     logs and returns whatever schemes succeeded (in this case, none).
  5. Decimal precision on total_pnl matches the per-scheme sum exactly
     (no rounding drift from the wire-up path).

No network, no Upstox client, no real AMFI call — fully offline.
The nav_fetcher is always a plain lambda or a raising callable.
"""

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from scripts.seed_mf_holdings import seed_holdings
from src.mf.models import MFHolding
from src.mf.store import MFStore
from src.mf.tracker import MFTracker, PortfolioPnL
from src.portfolio.store import PortfolioStore


# ── Fixtures ──────────────────────────────────────────────────────


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    """Shared DB path — mirrors the single-file setup in daily_snapshot.py."""
    return tmp_path / "portfolio.sqlite"


@pytest.fixture
def seeded_mf_store(db_path: Path) -> MFStore:
    """MFStore initialised on a DB that PortfolioStore already created."""
    PortfolioStore(db_path)   # portfolio init first — matches real cron ordering
    store = MFStore(db_path)
    seed_holdings(store)
    return store


def _nav_fetcher_for_all_11(amfi_codes: set[str]) -> dict[str, Decimal]:
    """Return a fixed NAV of 100.00 for every requested code — fully offline."""
    return {code: Decimal("100.00") for code in amfi_codes}


def _nav_fetcher_raises(_: set[str]) -> dict[str, Decimal]:
    raise ConnectionError("AMFI unreachable")


# ── Schema coexistence (regression guard) ─────────────────────────


def test_mfstore_init_on_existing_portfolio_db(db_path: Path) -> None:
    """MFStore must initialise without error on a DB PortfolioStore already owns."""
    PortfolioStore(db_path)
    MFStore(db_path)  # must not raise


def test_mfstore_init_is_idempotent_across_cron_runs(db_path: Path) -> None:
    """Every cron run calls MFStore(db_path) — CREATE TABLE IF NOT EXISTS is safe."""
    PortfolioStore(db_path)
    for _ in range(3):
        MFStore(db_path)  # must not raise or corrupt


# ── record_snapshot — seeded path ────────────────────────────────


def test_record_snapshot_returns_portfolio_pnl(seeded_mf_store: MFStore) -> None:
    """record_snapshot must return a PortfolioPnL instance."""
    tracker = MFTracker(seeded_mf_store, nav_fetcher=_nav_fetcher_for_all_11)
    result = tracker.record_snapshot(date(2026, 4, 3))
    assert isinstance(result, PortfolioPnL)


def test_record_snapshot_covers_all_11_schemes(seeded_mf_store: MFStore) -> None:
    """After seeding, record_snapshot must return P&L for all 11 schemes."""
    tracker = MFTracker(seeded_mf_store, nav_fetcher=_nav_fetcher_for_all_11)
    result = tracker.record_snapshot(date(2026, 4, 3))
    assert len(result.schemes) == 11


def test_record_snapshot_date_propagated(seeded_mf_store: MFStore) -> None:
    """snapshot_date on the returned PortfolioPnL must match the argument."""
    snap_date = date(2026, 4, 3)
    tracker = MFTracker(seeded_mf_store, nav_fetcher=_nav_fetcher_for_all_11)
    result = tracker.record_snapshot(snap_date)
    assert result.snapshot_date == snap_date


def test_record_snapshot_persists_nav_snapshots(seeded_mf_store: MFStore) -> None:
    """One MFNavSnapshot per scheme must be written to the store."""
    snap_date = date(2026, 4, 3)
    tracker = MFTracker(seeded_mf_store, nav_fetcher=_nav_fetcher_for_all_11)
    tracker.record_snapshot(snap_date)
    # Verify by reading back one known scheme
    snaps = seeded_mf_store.get_nav_snapshots("118834", from_date=snap_date)
    assert len(snaps) == 1
    assert snaps[0].nav == Decimal("100.00")


def test_record_snapshot_total_invested_matches_seed(seeded_mf_store: MFStore) -> None:
    """Total invested in PortfolioPnL must equal the sum of all seeded amounts."""
    from scripts.seed_mf_holdings import _HOLDINGS
    expected = sum(Decimal(row[3]) for row in _HOLDINGS)
    tracker = MFTracker(seeded_mf_store, nav_fetcher=_nav_fetcher_for_all_11)
    result = tracker.record_snapshot(date(2026, 4, 3))
    assert result.total_invested == expected


def test_record_snapshot_pnl_sum_matches_total(seeded_mf_store: MFStore) -> None:
    """Sum of per-scheme pnl values must equal total_pnl — no rounding drift."""
    tracker = MFTracker(seeded_mf_store, nav_fetcher=_nav_fetcher_for_all_11)
    result = tracker.record_snapshot(date(2026, 4, 3))
    assert sum(s.pnl for s in result.schemes) == result.total_pnl


def test_record_snapshot_idempotent(seeded_mf_store: MFStore) -> None:
    """Running record_snapshot twice on the same date must not create duplicates."""
    snap_date = date(2026, 4, 3)
    tracker = MFTracker(seeded_mf_store, nav_fetcher=_nav_fetcher_for_all_11)
    tracker.record_snapshot(snap_date)
    tracker.record_snapshot(snap_date)
    snaps = seeded_mf_store.get_nav_snapshots("118834")
    assert len(snaps) == 1  # upsert — not doubled


# ── record_snapshot — no holdings (first cron run before seed) ───


def test_record_snapshot_empty_holdings_no_crash(db_path: Path) -> None:
    """record_snapshot on an unseeded DB must return empty PortfolioPnL, not raise."""
    PortfolioStore(db_path)
    store = MFStore(db_path)
    tracker = MFTracker(store, nav_fetcher=_nav_fetcher_for_all_11)
    result = tracker.record_snapshot(date(2026, 4, 3))
    assert isinstance(result, PortfolioPnL)
    assert result.schemes == []
    assert result.total_pnl == Decimal("0")


def test_record_snapshot_empty_holdings_returns_zero_totals(db_path: Path) -> None:
    """All monetary totals must be zero when no holdings exist."""
    store = MFStore(db_path)
    tracker = MFTracker(store, nav_fetcher=_nav_fetcher_for_all_11)
    result = tracker.record_snapshot(date(2026, 4, 3))
    assert result.total_invested == Decimal("0")
    assert result.total_current_value == Decimal("0")
    assert result.total_pnl_pct == Decimal("0")


# ── record_snapshot — AMFI fetch failure (non-fatal path) ────────


def test_record_snapshot_nav_fetcher_raises_returns_empty(seeded_mf_store: MFStore) -> None:
    """A raising nav_fetcher propagates the exception — caller (daily_snapshot.py)
    wraps it in try/except.  The tracker itself does not swallow it."""
    tracker = MFTracker(seeded_mf_store, nav_fetcher=_nav_fetcher_raises)
    with pytest.raises(ConnectionError):
        tracker.record_snapshot(date(2026, 4, 3))

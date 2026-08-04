"""BUG-020 Phase 1: PaperStore.set_original_entry_credit / get_original_entry_credit.

Persistence-only tests — no strategy logic is exercised here (that's Phase 2/3).
No network; SQLite fixture is a tmp_path file per the project's offline-test standard.
"""

from decimal import Decimal

import pytest

from src.paper.store import PaperStore


@pytest.fixture
def store(tmp_path):
    db_path = tmp_path / "portfolio.sqlite"
    return PaperStore(db_path)


def test_get_returns_none_when_never_recorded(store):
    """Edge case: no paper_strategies row at all for this strategy yet."""
    assert store.get_original_entry_credit("paper_ic_nifty_v2_monthly") is None


def test_set_and_get_roundtrip(store):
    """Happy path: write then read back the same Decimal value."""
    store.set_original_entry_credit("paper_ic_nifty_v2_monthly", Decimal("163.850"))

    retrieved = store.get_original_entry_credit("paper_ic_nifty_v2_monthly")

    assert retrieved == Decimal("163.850")


def test_set_overwrites_prior_value(store):
    """A new entry's set() call replaces the prior cycle's persisted credit."""
    store.set_original_entry_credit("paper_ic_nifty_v2_monthly", Decimal("100"))
    store.set_original_entry_credit("paper_ic_nifty_v2_monthly", Decimal("163.850"))

    assert store.get_original_entry_credit("paper_ic_nifty_v2_monthly") == Decimal("163.850")


def test_get_returns_none_when_row_exists_but_column_null(store):
    """Edge case: paper_strategies row exists (e.g. via profit-lock state) but
    original_entry_credit was never set on it — must read back as None, not 0,
    so Phase 3's fallback-to-recompute logic can distinguish "unknown" from
    "zero credit"."""
    # get_profit_lock_state() inserts a default row as a side effect.
    store.get_profit_lock_state("paper_ic_nifty_v2_monthly")

    assert store.get_original_entry_credit("paper_ic_nifty_v2_monthly") is None


def test_scoped_per_strategy_name(store):
    """Two different strategies persist independent values."""
    store.set_original_entry_credit("paper_ic_nifty_v2_monthly", Decimal("163.850"))
    store.set_original_entry_credit("paper_ic_nifty_v1_monthly", Decimal("98.375"))

    assert store.get_original_entry_credit("paper_ic_nifty_v2_monthly") == Decimal("163.850")
    assert store.get_original_entry_credit("paper_ic_nifty_v1_monthly") == Decimal("98.375")

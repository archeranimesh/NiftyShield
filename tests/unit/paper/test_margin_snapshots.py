# tests/unit/paper/test_margin_snapshots.py
"""Unit tests for the paper_margin_snapshots table and MarginSnapshot model.

Covers PaperStore.record_margin_snapshot and get_margin_snapshot — the
entry-cycle margin persistence layer used by scripts/strategies/ic/
paper_ic_entry.py, paper_ic_entry_v2.py (via capture_entry_margin), and
read by paper_ic_snapshot.py's ROI-on-margin report line.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from src.paper.models import MarginSnapshot
from src.paper.store import PaperStore


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "test_margin_snapshots.db"


@pytest.fixture
def store(db_path: Path) -> PaperStore:
    return PaperStore(db_path)


def _make_snapshot(
    strategy_name: str = "paper_ic_nifty_v1_weekly",
    entry_date: date = date(2026, 7, 21),
    required_margin: Decimal = Decimal("273414.70"),
    final_margin: Decimal = Decimal("73233.55"),
) -> MarginSnapshot:
    return MarginSnapshot(
        strategy_name=strategy_name,
        entry_date=entry_date,
        required_margin=required_margin,
        final_margin=final_margin,
        captured_at=datetime(2026, 7, 21, 9, 20, 0, tzinfo=timezone.utc),
    )


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_record_and_get_margin_snapshot_round_trips(store: PaperStore) -> None:
    """A recorded snapshot is retrievable with Decimal precision intact."""
    snapshot = _make_snapshot()
    store.record_margin_snapshot(snapshot)

    result = store.get_margin_snapshot("paper_ic_nifty_v1_weekly", date(2026, 7, 21))

    assert result is not None
    assert result.strategy_name == "paper_ic_nifty_v1_weekly"
    assert result.entry_date == date(2026, 7, 21)
    assert result.required_margin == Decimal("273414.70")
    assert result.final_margin == Decimal("73233.55")
    assert isinstance(result.required_margin, Decimal)
    assert isinstance(result.final_margin, Decimal)


def test_record_margin_snapshot_upserts_on_same_strategy_and_entry_date(
    store: PaperStore,
) -> None:
    """A second call for the same (strategy, entry_date) overwrites, not duplicates."""
    store.record_margin_snapshot(_make_snapshot(final_margin=Decimal("73233.55")))
    store.record_margin_snapshot(_make_snapshot(final_margin=Decimal("80000.00")))

    result = store.get_margin_snapshot("paper_ic_nifty_v1_weekly", date(2026, 7, 21))

    assert result is not None
    assert result.final_margin == Decimal("80000.00")


def test_distinct_entry_dates_produce_distinct_rows(store: PaperStore) -> None:
    """Two different entry cycles for the same strategy are stored independently."""
    store.record_margin_snapshot(_make_snapshot(entry_date=date(2026, 6, 1)))
    store.record_margin_snapshot(_make_snapshot(entry_date=date(2026, 7, 21)))

    first = store.get_margin_snapshot("paper_ic_nifty_v1_weekly", date(2026, 6, 1))
    second = store.get_margin_snapshot("paper_ic_nifty_v1_weekly", date(2026, 7, 21))

    assert first is not None and second is not None
    assert first.entry_date != second.entry_date


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_get_margin_snapshot_returns_none_when_not_found(store: PaperStore) -> None:
    """No snapshot recorded for this (strategy, entry_date) — None, not an error.

    Expected for entry cycles that predate this feature, or where the
    margin-calculator call failed non-fatally at entry time.
    """
    result = store.get_margin_snapshot("paper_ic_nifty_v1_yearly", date(2020, 1, 1))
    assert result is None


def test_get_margin_snapshot_scoped_to_strategy_name(store: PaperStore) -> None:
    """Same entry_date, different strategy — lookup does not cross-contaminate."""
    store.record_margin_snapshot(
        _make_snapshot(strategy_name="paper_ic_nifty_v1_weekly", final_margin=Decimal("100"))
    )
    store.record_margin_snapshot(
        _make_snapshot(strategy_name="paper_ic_nifty_v2_monthly", final_margin=Decimal("200"))
    )

    weekly = store.get_margin_snapshot("paper_ic_nifty_v1_weekly", date(2026, 7, 21))
    monthly = store.get_margin_snapshot("paper_ic_nifty_v2_monthly", date(2026, 7, 21))

    assert weekly is not None and weekly.final_margin == Decimal("100")
    assert monthly is not None and monthly.final_margin == Decimal("200")

# tests/unit/paper/test_gate_violations.py
"""Unit tests for the gate_violations table and GateViolation model.

Covers PaperStore.record_gate_violation and get_gate_violation_counts —
the log-only-gates persistence layer used by scripts/strategies/ic/
paper_ic_entry.py and paper_ic_entry_v2.py when a threshold gate would
have blocked entry.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.paper.models import GateViolation
from src.paper.store import PaperStore


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "test_gate_violations.db"


@pytest.fixture
def store(db_path: Path) -> PaperStore:
    return PaperStore(db_path)


def _make_violation(
    gate_name: str = "ivr",
    strategy_name: str = "paper_ic_nifty_v1_weekly",
    threshold: str = "0.25",
    actual: str = "0.10",
) -> GateViolation:
    return GateViolation(
        gate_name=gate_name,
        threshold=threshold,
        actual=actual,
        strategy_name=strategy_name,
        logged_at=datetime(2026, 7, 2, 10, 0, 0, tzinfo=timezone.utc),
    )


# ---------------------------------------------------------------------------
# Happy path — record + GROUP BY aggregate query
# ---------------------------------------------------------------------------


def test_record_and_aggregate_gate_violations(store: PaperStore) -> None:
    """Threshold violation is persisted and queryable via a GROUP BY aggregate.

    Mirrors the pipeline-validation use case: a trade opens under
    --log-only-gates, the would-be-blocking gate is recorded instead of
    aborting, and later analysis aggregates counts per (strategy, gate)
    rather than dumping raw rows (project Rule 1).
    """
    v1 = _make_violation(gate_name="ivr", strategy_name="paper_ic_nifty_v1_weekly")
    v2 = _make_violation(gate_name="ivr", strategy_name="paper_ic_nifty_v1_weekly")
    v3 = _make_violation(gate_name="portfolio_delta", strategy_name="paper_ic_nifty_v1_weekly")

    id1 = store.record_gate_violation(v1)
    id2 = store.record_gate_violation(v2)
    id3 = store.record_gate_violation(v3)

    assert id1 >= 1
    assert id2 > id1
    assert id3 > id2

    counts = store.get_gate_violation_counts(strategy_name="paper_ic_nifty_v1_weekly")
    by_gate = {row["gate_name"]: row["violation_count"] for row in counts}
    assert by_gate["ivr"] == 2
    assert by_gate["portfolio_delta"] == 1


def test_get_gate_violation_counts_filters_by_gate_name(store: PaperStore) -> None:
    """Optional gate_name filter narrows the GROUP BY aggregate to one gate."""
    store.record_gate_violation(_make_violation(gate_name="ivr"))
    store.record_gate_violation(_make_violation(gate_name="liquidity_short_put"))

    counts = store.get_gate_violation_counts(gate_name="liquidity_short_put")
    assert len(counts) == 1
    assert counts[0]["gate_name"] == "liquidity_short_put"
    assert counts[0]["violation_count"] == 1


# ---------------------------------------------------------------------------
# Edge case — structural gates never produce a GateViolation
# ---------------------------------------------------------------------------


def test_no_violations_recorded_for_untouched_strategy(store: PaperStore) -> None:
    """Structural gates (duplicate, post-expiry, unresolved keys, stale chain)
    never call record_gate_violation — querying an untouched strategy/gate
    combination returns an empty aggregate, not a fabricated zero-count row.

    This is the DB-layer half of the "structural gate still blocks, no
    bypass even with flag on" contract: the entry scripts' structural gates
    call sys.exit(1) before ever reaching a GateViolation construction site,
    so no row exists for them regardless of --log-only-gates.
    """
    counts = store.get_gate_violation_counts(strategy_name="paper_ic_nifty_v2_monthly")
    assert counts == []

# tests/unit/paper/test_warn_signal_state.py
"""Unit tests for the warn_signal_state table and its PaperStore methods.

Covers is_warn_active / set_warn_active / reconcile_warn_state — the
WARN-severity Telegram dedup layer used by StrategyMonitor._route_event so
a persistently-breached condition (e.g. DELTA_WARN) alerts once on the
OFF->ON transition instead of on every ~poll_interval_s tick.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.paper.store import PaperStore

_STRATEGY = "paper_ic_nifty_v1_monthly"
_EVENT_TYPE = "DELTA_WARN"
_LEG = "short_call"


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "test_warn_signal_state.db"


@pytest.fixture
def store(db_path: Path) -> PaperStore:
    return PaperStore(db_path)


# ---------------------------------------------------------------------------
# Happy path — new condition, mark active, then recovers
# ---------------------------------------------------------------------------


def test_is_warn_active_false_when_never_set(store: PaperStore) -> None:
    assert store.is_warn_active(_STRATEGY, _EVENT_TYPE, _LEG) is False


def test_set_warn_active_then_is_active(store: PaperStore) -> None:
    store.set_warn_active(_STRATEGY, _EVENT_TYPE, _LEG, True)
    assert store.is_warn_active(_STRATEGY, _EVENT_TYPE, _LEG) is True


def test_reconcile_clears_state_not_fired_this_tick(store: PaperStore) -> None:
    store.set_warn_active(_STRATEGY, _EVENT_TYPE, _LEG, True)
    # Condition recovered — this tick's fired_keys no longer includes it.
    store.reconcile_warn_state(_STRATEGY, fired_keys=set())
    assert store.is_warn_active(_STRATEGY, _EVENT_TYPE, _LEG) is False


def test_reconcile_leaves_still_firing_condition_active(store: PaperStore) -> None:
    store.set_warn_active(_STRATEGY, _EVENT_TYPE, _LEG, True)
    store.reconcile_warn_state(_STRATEGY, fired_keys={(_EVENT_TYPE, _LEG, "")})
    assert store.is_warn_active(_STRATEGY, _EVENT_TYPE, _LEG) is True


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_reconcile_only_affects_named_strategy(store: PaperStore) -> None:
    other_strategy = "paper_ic_nifty_v1_weekly"
    store.set_warn_active(_STRATEGY, _EVENT_TYPE, _LEG, True)
    store.set_warn_active(other_strategy, _EVENT_TYPE, _LEG, True)
    store.reconcile_warn_state(_STRATEGY, fired_keys=set())
    assert store.is_warn_active(_STRATEGY, _EVENT_TYPE, _LEG) is False
    assert store.is_warn_active(other_strategy, _EVENT_TYPE, _LEG) is True


def test_set_warn_active_upsert_does_not_duplicate_row(store: PaperStore) -> None:
    store.set_warn_active(_STRATEGY, _EVENT_TYPE, _LEG, True)
    store.set_warn_active(_STRATEGY, _EVENT_TYPE, _LEG, False)
    store.set_warn_active(_STRATEGY, _EVENT_TYPE, _LEG, True)
    assert store.is_warn_active(_STRATEGY, _EVENT_TYPE, _LEG) is True


def test_reconcile_mixed_recovery_across_leg_roles(store: PaperStore) -> None:
    """Two active legs under the same event_type — only the non-firing one clears."""
    store.set_warn_active(_STRATEGY, _EVENT_TYPE, "short_call", True)
    store.set_warn_active(_STRATEGY, _EVENT_TYPE, "short_put", True)
    # short_call recovered this tick; short_put is still breached and fired again.
    store.reconcile_warn_state(_STRATEGY, fired_keys={(_EVENT_TYPE, "short_put", "")})
    assert store.is_warn_active(_STRATEGY, _EVENT_TYPE, "short_call") is False
    assert store.is_warn_active(_STRATEGY, _EVENT_TYPE, "short_put") is True


def test_expiry_distinguishes_dedup_key(store: PaperStore) -> None:
    """Same (strategy, event_type, leg_role) across two expiries dedup independently.

    Guards against a calendar/multi-expiry strategy where two distinct
    breaches under the same strategy_name and leg_role would otherwise
    silently alias to one row and suppress a genuinely new occurrence.
    """
    store.set_warn_active(_STRATEGY, _EVENT_TYPE, _LEG, True, expiry="2026-08-27")
    assert store.is_warn_active(_STRATEGY, _EVENT_TYPE, _LEG, expiry="2026-09-24") is False
    assert store.is_warn_active(_STRATEGY, _EVENT_TYPE, _LEG, expiry="2026-08-27") is True

"""Tests for scripts/mvp_watch.py's split-gap interlock helper."""

from datetime import date
from decimal import Decimal
from pathlib import Path

from scripts.mvp_watch import _gap_interlock
from src.mvp.models import MVPSnapshot, Pick, PickStatus
from src.mvp.store import MVPStore

_TS = "2026-09-01T00:00:00Z"


def _store(tmp_path: Path) -> MVPStore:
    store = MVPStore(tmp_path / "w.db")
    store.init_db()
    store.add_pick(
        Pick(
            pick_id="p1",
            symbol="XYZ",
            instrument_key="NSE_EQ|XYZ",
            status=PickStatus.OPEN,
            pick_date="2026-09-01",
            created_at=_TS,
            updated_at=_TS,
        )
    )
    store.record_snapshot(
        MVPSnapshot(pick_id="p1", ltp=Decimal("1000"), captured_at="2026-09-24T09:30:00Z")
    )
    return store


def _pick(store: MVPStore) -> Pick:
    pick = store.get_pick("p1")
    assert pick is not None
    return pick


def test_interlock_suppresses_and_warns_on_first_tick(tmp_path: Path) -> None:
    store = _store(tmp_path)
    suppressed, warnings = _gap_interlock(
        store, [_pick(store)], {"NSE_EQ|XYZ": Decimal("200")}, {}, date(2026, 9, 25)
    )
    assert suppressed == {"p1"}
    assert len(warnings) == 1 and "XYZ" in warnings[0] and "5:1" in warnings[0]
    assert store.get_corporate_actions() == []  # never auto-inserts


def test_interlock_still_suppresses_later_tick_without_repeat_warning(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.record_snapshot(
        MVPSnapshot(pick_id="p1", ltp=Decimal("200"), captured_at="2026-09-25T04:00:00Z")
    )
    suppressed, warnings = _gap_interlock(
        store, [_pick(store)], {"NSE_EQ|XYZ": Decimal("210")}, {}, date(2026, 9, 25)
    )
    assert suppressed == {"p1"} and warnings == []


def test_interlock_organic_drop_not_suppressed(tmp_path: Path) -> None:
    store = _store(tmp_path)
    suppressed, warnings = _gap_interlock(
        store, [_pick(store)], {"NSE_EQ|XYZ": Decimal("850")}, {}, date(2026, 9, 25)
    )
    assert suppressed == set() and warnings == []

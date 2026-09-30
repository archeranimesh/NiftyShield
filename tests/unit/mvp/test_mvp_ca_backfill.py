"""Backfill walk with a split inside the pick's own history (BECTORFOOD-shaped)."""

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from src.mvp.backfill import enter_backfill_pick, run_backfill
from src.mvp.models import CorporateAction, CorporateActionType, Pick, PickStatus
from src.mvp.store import MVPStore

_TS = "2026-06-11T00:00:00Z"


def _split_5() -> CorporateAction:
    return CorporateAction(
        action_id="ca-1",
        symbol="TEST",
        ex_date="2026-06-17",
        action_type=CorporateActionType.SPLIT,
        new_shares=5,
        old_shares=1,
        source="test",
        created_at=_TS,
    )


def _pick() -> Pick:
    return Pick(
        pick_id="p1",
        symbol="TEST",
        pick_date="2026-06-11",
        reco_price=Decimal("1000"),
        target_price=Decimal("1500"),
        stop_loss=Decimal("800"),
        created_at=_TS,
        updated_at=_TS,
    )


@pytest.fixture
def store(tmp_path: Path) -> MVPStore:
    s = MVPStore(tmp_path / "ca_bf.sqlite")
    s.init_db()
    s.add_pick(_pick())
    s.add_corporate_action(_split_5())
    return s


def test_split_mid_pending_does_not_false_enter() -> None:
    # Pre-split closes sit below reco 1000; a rebased reco (200) would false-enter on them.
    closes = {
        date(2026, 6, 12): Decimal("950"),
        date(2026, 6, 15): Decimal("960"),
        date(2026, 6, 16): Decimal("990"),
        date(2026, 6, 17): Decimal("205"),  # ex-date; adjusted reco = 200
    }
    assert enter_backfill_pick(_pick(), closes, [_split_5()]) == (
        date(2026, 6, 17),
        Decimal("205"),
    )


def test_split_mid_pending_stays_pending_below_adjusted_reco() -> None:
    closes = {date(2026, 6, 12): Decimal("950"), date(2026, 6, 17): Decimal("190")}
    assert enter_backfill_pick(_pick(), closes, [_split_5()]) is None


def test_split_mid_open_no_false_sl_then_target_on_adjusted_basis(store: MVPStore) -> None:
    closes = {
        date(2026, 6, 12): Decimal("1010"),  # entry
        date(2026, 6, 15): Decimal("1020"),
        date(2026, 6, 17): Decimal("205"),  # raw SL 800 would false-fire; adjusted SL is 160
        date(2026, 6, 18): Decimal("210"),
        date(2026, 6, 19): Decimal("302"),  # adjusted target is 300
    }
    run_backfill(store, "p1", closes, {}, end_date=date(2026, 6, 19))

    pick = store.get_pick("p1")
    assert pick is not None
    assert pick.status == PickStatus.TARGET_HIT
    assert pick.close_price == Decimal("302")
    assert len(store.get_snapshots("p1")) == 5
    assert pick.avg_cost is not None
    # P&L restated to the close-day basis: qty x5, avg_cost / 5; rupee capital untouched.
    expected = (Decimal("302") * Decimal("0.9975") - pick.avg_cost / 5) * (pick.total_qty * 5)
    assert pick.realized_pnl == expected
    assert pick.deployed_capital == Decimal("1010") * pick.total_qty


def test_split_mid_open_real_sl_breach_on_adjusted_basis(store: MVPStore) -> None:
    closes = {
        date(2026, 6, 12): Decimal("1010"),
        date(2026, 6, 17): Decimal("205"),
        date(2026, 6, 18): Decimal("160"),  # adjusted SL 160
    }
    run_backfill(store, "p1", closes, {}, end_date=date(2026, 6, 18))
    pick = store.get_pick("p1")
    assert pick is not None and pick.status == PickStatus.SL_HIT
    assert pick.close_price == Decimal("160")


def test_no_actions_backfill_unchanged(tmp_path: Path) -> None:
    s = MVPStore(tmp_path / "plain.sqlite")
    s.init_db()
    s.add_pick(_pick())
    closes = {date(2026, 6, 12): Decimal("1010"), date(2026, 6, 15): Decimal("790")}
    run_backfill(s, "p1", closes, {}, end_date=date(2026, 6, 15))
    pick = s.get_pick("p1")
    assert pick is not None and pick.status == PickStatus.SL_HIT

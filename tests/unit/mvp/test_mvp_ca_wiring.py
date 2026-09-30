"""Tests wiring corporate actions into live tracking, close, backfill and display."""

from datetime import date
from decimal import Decimal
from pathlib import Path

from src.mvp.adjustment import Fill, adjust_position, adjusted_pick
from src.mvp.models import (
    CorporateAction,
    CorporateActionType,
    MVPSnapshot,
    Pick,
    PickStatus,
)
from src.mvp.store import MVPStore
from src.mvp.tracker import check_prices

_NOW = "2026-09-23T00:00:00"


def _split(
    symbol: str = "TCS", ex_date: str = "2026-09-15", new: int = 5, old: int = 1
) -> CorporateAction:
    return CorporateAction(
        action_id=f"ca-{symbol}-{ex_date}",
        symbol=symbol,
        ex_date=ex_date,
        action_type=CorporateActionType.SPLIT,
        new_shares=new,
        old_shares=old,
        source="test",
        created_at=_NOW,
    )


def _pick(**over: object) -> Pick:
    base: dict[str, object] = dict(
        pick_id="P1",
        symbol="TCS",
        instrument_key="NSE_EQ|TCS",
        entry_price=Decimal("75"),
        pick_date="2026-09-01",
        target_price=Decimal("100"),
        stop_loss=Decimal("50"),
        status=PickStatus.OPEN,
        created_at=_NOW,
        updated_at=_NOW,
    )
    base.update(over)
    return Pick(**base)  # type: ignore[arg-type]


def test_check_prices_post_split_no_false_sl() -> None:
    # Raw SL 50 would falsely fire at post-split LTP 15; adjusted SL is 10.
    events = check_prices(
        [_pick()], {"NSE_EQ|TCS": Decimal("15")}, {"TCS": [_split()]}, as_of=date(2026, 9, 20)
    )
    assert events == []


def test_check_prices_post_split_target_and_sl_on_adjusted_basis() -> None:
    actions = {"TCS": [_split()]}
    hit = check_prices([_pick()], {"NSE_EQ|TCS": Decimal("20")}, actions, as_of=date(2026, 9, 20))
    assert [e.event_type for e in hit] == [PickStatus.TARGET_HIT]
    stop = check_prices([_pick()], {"NSE_EQ|TCS": Decimal("10")}, actions, as_of=date(2026, 9, 20))
    assert [e.event_type for e in stop] == [PickStatus.SL_HIT]


def test_check_prices_action_not_yet_effective_uses_raw_levels() -> None:
    events = check_prices(
        [_pick()],
        {"NSE_EQ|TCS": Decimal("100")},
        {"TCS": [_split(ex_date="2026-09-25")]},
        as_of=date(2026, 9, 20),
    )
    assert [e.event_type for e in events] == [PickStatus.TARGET_HIT]


def test_check_prices_other_symbol_actions_ignored() -> None:
    events = check_prices(
        [_pick()],
        {"NSE_EQ|TCS": Decimal("15")},
        {"INFY": [_split("INFY")]},
        as_of=date(2026, 9, 20),
    )
    assert [e.event_type for e in events] == [PickStatus.SL_HIT]


def test_adjust_position_tranches_on_both_sides_of_ex_date() -> None:
    # 10 @ 100 pre-split (=> 50 @ 20), plus 20 @ 21 post-split; rupee cost preserved.
    fills = [
        Fill(Decimal("100"), 10, date(2026, 9, 1)),
        Fill(Decimal("21"), 20, date(2026, 9, 16)),
    ]
    pos = adjust_position(fills, [_split()], as_of=date(2026, 9, 20))
    assert pos.total_qty == Decimal("70")
    assert pos.avg_cost == (Decimal("1000") + Decimal("420")) / Decimal("70")


def test_adjust_position_no_fills() -> None:
    pos = adjust_position([], [_split()], as_of=date(2026, 9, 20))
    assert pos.total_qty == Decimal("0") and pos.avg_cost is None


def test_adjusted_pick_leaves_rupee_fields_untouched() -> None:
    pick = _pick(
        avg_cost=Decimal("100"),
        total_qty=10,
        deployed_capital=Decimal("1000"),
        idle_cash=Decimal("500"),
        realized_pnl=Decimal("7"),
        benchmark_entry=Decimal("25000"),
        reco_price=Decimal("90"),
    )
    fills = [Fill(Decimal("100"), 10, date(2026, 9, 1))]
    adj = adjusted_pick(pick, [_split()], date(2026, 9, 20), fills)
    assert adj.total_qty == 50 and adj.avg_cost == Decimal("20")
    assert adj.target_price == Decimal("20") and adj.stop_loss == Decimal("10")
    assert adj.reco_price == Decimal("18") and adj.entry_price == Decimal("15")
    assert adj.deployed_capital == Decimal("1000") and adj.idle_cash == Decimal("500")
    assert adj.realized_pnl == Decimal("7") and adj.benchmark_entry == Decimal("25000")
    assert adjusted_pick(pick, [], date(2026, 9, 20), fills) is pick


def _open_store(tmp_path: Path) -> MVPStore:
    store = MVPStore(tmp_path / "wire.db")
    store.init_db()
    store.add_pick(_pick(avg_cost=Decimal("100"), total_qty=10, deployed_capital=Decimal("1000")))
    store.record_snapshot(
        MVPSnapshot(pick_id="P1", ltp=Decimal("100"), captured_at="2026-09-02T00:00:00Z")
    )
    return store


def test_close_pick_post_split_pnl_uses_adjusted_position(tmp_path: Path) -> None:
    store = _open_store(tmp_path)
    store.add_corporate_action(_split())
    res = store.close_pick("P1", Decimal("22"), PickStatus.TARGET_HIT, as_of=date(2026, 9, 20))
    # adjusted: 50 sh @ 20; net exit 22 * (1 - 25bps) - 20 = 1.945 per share.
    assert res.total_qty == 50 and res.avg_cost == Decimal("20")
    assert res.realized_pnl == (Decimal("22") * Decimal("0.9975") - Decimal("20")) * 50


def test_close_pick_without_actions_unchanged(tmp_path: Path) -> None:
    store = _open_store(tmp_path)
    res = store.close_pick("P1", Decimal("110"), PickStatus.MANUAL_CLOSE)
    assert res.total_qty == 10 and res.avg_cost == Decimal("100")
    assert res.realized_pnl == (Decimal("110") * Decimal("0.9975") - Decimal("100")) * 10


def test_close_pick_before_ex_date_unadjusted(tmp_path: Path) -> None:
    store = _open_store(tmp_path)
    store.add_corporate_action(_split(ex_date="2026-09-25"))
    res = store.close_pick("P1", Decimal("110"), PickStatus.MANUAL_CLOSE, as_of=date(2026, 9, 20))
    assert res.total_qty == 10

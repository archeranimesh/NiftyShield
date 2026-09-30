"""Adjusted-view display/aggregation call sites (B054.6)."""

from decimal import Decimal
from pathlib import Path

import pytest

from src.db import connect
from src.mvp.analytics import _daily_price_returns, compute_category_returns
from src.mvp.models import (
    Category,
    CorporateAction,
    CorporateActionType,
    MVPSnapshot,
    Pick,
    PickStatus,
    Provider,
    ProviderSource,
)
from src.mvp.store import MVPStore
from src.mvp.tracker import format_holdings_row, format_hourly_summary

_TS = "2026-09-01T00:00:00Z"
_KEY = "NSE_EQ|TCS"


def _split() -> CorporateAction:
    return CorporateAction(
        action_id="ca-1",
        symbol="TCS",
        ex_date="2026-09-15",
        action_type=CorporateActionType.SPLIT,
        new_shares=5,
        old_shares=1,
        source="test",
        created_at=_TS,
    )


def _store(tmp_path: Path, **pick_over: object) -> MVPStore:
    store = MVPStore(tmp_path / "disp.db")
    store.init_db()
    store.add_provider(
        Provider(
            provider_id="pr",
            slug="p",
            display_name="P",
            source_type=ProviderSource.OTHER,
            created_at=_TS,
        )
    )
    store.add_category(
        Category(category_id="c1", provider_id="pr", slug="c", display_name="C", created_at=_TS)
    )
    fields: dict[str, object] = dict(
        pick_id="P1",
        category_id="c1",
        symbol="TCS",
        instrument_key=_KEY,
        entry_price=Decimal("100"),
        pick_date="2026-09-01",
        status=PickStatus.OPEN,
        deployed_capital=Decimal("1000"),
        avg_cost=Decimal("100"),
        total_qty=10,
        created_at=_TS,
        updated_at=_TS,
    )
    fields.update(pick_over)
    store.add_pick(Pick(**fields))  # type: ignore[arg-type]
    store.record_snapshot(
        MVPSnapshot(pick_id="P1", ltp=Decimal("100"), captured_at="2026-09-02T04:00:00Z")
    )
    return store


def test_holdings_row_pnl_pre_and_post_split_lump_sum(tmp_path: Path) -> None:
    store = _store(tmp_path)
    pick = store.get_pick("P1")
    assert pick is not None
    assert format_holdings_row(pick, Decimal("110"))[3] == "+100"  # pre-split, raw view
    store.add_corporate_action(_split())
    adjusted = store.get_adjusted_pick(pick)
    # 50 sh @ 20 -> (22 - 20) * 50 = +100; raw view would show a bogus large loss.
    assert format_holdings_row(adjusted, Decimal("22"))[3] == "+100"
    assert format_holdings_row(pick, Decimal("22"))[3] == "-780"


def test_tranches_either_side_of_ex_date_recompute_avg_cost(tmp_path: Path) -> None:
    store = _store(tmp_path, total_qty=30, avg_cost=Decimal("47.3333"))
    with connect(store.db_path) as conn:
        conn.executemany(
            "INSERT INTO mvp_tranches (tranche_id, pick_id, tranche_index, trigger_pct,"
            " fill_price, qty, filled_at) VALUES (?, 'P1', ?, '0', ?, ?, ?)",
            [
                ("t0", 0, "100", 10, "2026-09-02T04:00:00Z"),
                ("t1", 1, "21", 20, "2026-09-16T04:00:00Z"),
            ],
        )
    store.add_corporate_action(_split())
    pick = store.get_pick("P1")
    assert pick is not None
    adjusted = store.get_adjusted_pick(pick)
    # 10 pre-split sh -> 50; plus 20 post-split = 70; avg = (1000 + 420) / 70.
    assert adjusted.total_qty == 70
    assert adjusted.avg_cost == Decimal("1420") / Decimal("70")
    assert adjusted.deployed_capital == Decimal("1000")
    summary = format_hourly_summary([adjusted], {_KEY: Decimal("22")}, "11:00 AM")
    assert "120" in summary  # (22 - 1420/70) * 70


def test_category_stats_mark_to_market_uses_adjusted_qty(tmp_path: Path) -> None:
    store = _store(tmp_path)
    ltp_map = {_KEY: Decimal("22")}
    assert store.get_category_stats("c1", ltp_map).current == Decimal("220")  # no action yet
    store.add_corporate_action(_split())
    stats = store.get_category_stats("c1", ltp_map)
    assert stats.invested == Decimal("1000") and stats.current == Decimal("1100")


def test_category_returns_use_adjusted_qty(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.add_corporate_action(_split())
    store.record_snapshot(
        MVPSnapshot(pick_id="P1", ltp=Decimal("22"), captured_at="2026-09-20T04:00:00Z")
    )
    (row,) = compute_category_returns(store)
    assert row.total_return_pct == Decimal("10")


def test_daily_returns_do_not_count_split_as_price_move(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.record_snapshot(
        MVPSnapshot(pick_id="P1", ltp=Decimal("1000"), captured_at="2026-09-14T04:00:00Z")
    )
    store.record_snapshot(
        MVPSnapshot(pick_id="P1", ltp=Decimal("210"), captured_at="2026-09-15T04:00:00Z")
    )
    raw = _daily_price_returns(store.db_path)["P1"]["2026-09-15"]
    adj = _daily_price_returns(store.db_path, {"P1": [_split()]})["P1"]["2026-09-15"]
    assert raw == pytest.approx(-79.0) and adj == pytest.approx(5.0)

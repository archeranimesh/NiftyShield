"""Tests for MVPStore init_db and provider/category persistence."""

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from src.mvp.models import Category, MVPSnapshot, Pick, PickStatus, Provider, ProviderSource
from src.mvp.store import MVPStore


def _make_provider(provider_id: str = "prov-1", slug: str = "dsij") -> Provider:
    return Provider(
        provider_id=provider_id,
        slug=slug,
        display_name="DSIJ",
        source_type=ProviderSource.TV,
        notes=None,
        created_at="2026-09-22T00:00:00Z",
    )


def _make_category(
    category_id: str = "cat-1",
    provider_id: str = "prov-1",
    slug: str = "value-picks",
) -> Category:
    return Category(
        category_id=category_id,
        provider_id=provider_id,
        slug=slug,
        display_name="Value Picks",
        notes=None,
        created_at="2026-09-22T00:00:00Z",
    )


def _make_pick(pick_id: str = "pick-1", category_id: str | None = None) -> Pick:
    return Pick(
        pick_id=pick_id,
        category_id=category_id,
        symbol="TCS",
        pick_date="2026-09-22",
        created_at="2026-09-22T00:00:00Z",
        updated_at="2026-09-22T00:00:00Z",
    )


def _make_snapshot(
    pick_id: str = "pick-1", captured_at: str = "2026-09-22T10:00:00Z"
) -> MVPSnapshot:
    return MVPSnapshot(pick_id=pick_id, ltp=Decimal("3500.50"), captured_at=captured_at)


def test_init_db_is_idempotent(tmp_path: Path) -> None:
    store = MVPStore(str(tmp_path / "test.sqlite"))
    store.init_db()
    store.init_db()


def test_add_provider_get_provider_round_trip(tmp_path: Path) -> None:
    store = MVPStore(str(tmp_path / "test.sqlite"))
    store.init_db()
    provider = _make_provider()
    store.add_provider(provider)

    fetched = store.get_provider("dsij")

    assert fetched is not None
    assert fetched.slug == provider.slug
    assert fetched.display_name == provider.display_name


def test_get_provider_missing_slug_returns_none(tmp_path: Path) -> None:
    store = MVPStore(str(tmp_path / "test.sqlite"))
    store.init_db()

    assert store.get_provider("nonexistent") is None


def test_list_providers_returns_all_sorted_by_display_name(tmp_path: Path) -> None:
    store = MVPStore(str(tmp_path / "test.sqlite"))
    store.init_db()
    store.add_provider(_make_provider(provider_id="prov-1", slug="dsij"))
    store.add_provider(
        Provider(
            provider_id="prov-2",
            slug="prudentequity",
            display_name="Prudent Equity",
            source_type=ProviderSource.TELEGRAM,
            notes=None,
            created_at="2026-09-22T00:00:00Z",
        )
    )

    providers = store.list_providers()

    assert [p.display_name for p in providers] == ["DSIJ", "Prudent Equity"]


def test_add_category_get_category_round_trip(tmp_path: Path) -> None:
    store = MVPStore(str(tmp_path / "test.sqlite"))
    store.init_db()
    store.add_provider(_make_provider())
    category = _make_category()
    store.add_category(category)

    fetched = store.get_category("prov-1", "value-picks")

    assert fetched is not None
    assert fetched.category_id == category.category_id
    assert fetched.display_name == category.display_name


def test_add_category_duplicate_is_ignored(tmp_path: Path) -> None:
    store = MVPStore(str(tmp_path / "test.sqlite"))
    store.init_db()
    store.add_provider(_make_provider())
    store.add_category(_make_category())
    store.add_category(_make_category())

    categories = store.list_categories("prov-1")
    assert len(categories) == 1


def test_list_categories_filters_by_provider(tmp_path: Path) -> None:
    store = MVPStore(str(tmp_path / "test.sqlite"))
    store.init_db()
    store.add_provider(_make_provider(provider_id="prov-1", slug="dsij"))
    store.add_provider(
        Provider(
            provider_id="prov-2",
            slug="prudentequity",
            display_name="Prudent Equity",
            source_type=ProviderSource.TELEGRAM,
            notes=None,
            created_at="2026-09-22T00:00:00Z",
        )
    )
    store.add_category(
        _make_category(category_id="cat-1", provider_id="prov-1", slug="value-picks")
    )
    store.add_category(
        _make_category(category_id="cat-2", provider_id="prov-2", slug="multibagger")
    )

    prov1_categories = store.list_categories("prov-1")
    prov2_categories = store.list_categories("prov-2")

    assert len(prov1_categories) == 1
    assert prov1_categories[0].provider_id == "prov-1"
    assert len(prov2_categories) == 1
    assert prov2_categories[0].provider_id == "prov-2"


def test_add_pick_get_pick_round_trip(tmp_path: Path) -> None:
    store = MVPStore(str(tmp_path / "test.sqlite"))
    store.init_db()
    pick = _make_pick()
    store.add_pick(pick)

    fetched = store.get_pick("pick-1")

    assert fetched is not None
    assert fetched.symbol == "TCS"
    assert fetched.capital_allotted == Decimal("100000")
    assert fetched.tranche_step_pct == Decimal("6")
    assert isinstance(fetched.capital_allotted, Decimal)


def test_update_pick_with_entry_price_advances_pending_to_open(tmp_path: Path) -> None:
    store = MVPStore(str(tmp_path / "test.sqlite"))
    store.init_db()
    store.add_pick(_make_pick())

    store.update_pick("pick-1", entry_price=Decimal("3500"))

    fetched = store.get_pick("pick-1")
    assert fetched is not None
    assert fetched.status == PickStatus.OPEN
    assert fetched.entry_price == Decimal("3500")


def test_update_pick_with_entry_price_computes_lump_sum_fill(tmp_path: Path) -> None:
    store = MVPStore(str(tmp_path / "test.sqlite"))
    store.init_db()
    store.add_pick(_make_pick())

    store.update_pick("pick-1", entry_price=Decimal("3500"))

    fetched = store.get_pick("pick-1")
    assert fetched is not None
    assert fetched.total_qty == 28  # floor(100000 / 3500)
    assert fetched.deployed_capital == Decimal("98000")  # 28 * 3500
    assert fetched.idle_cash == Decimal("2000")  # 100000 - 98000
    assert fetched.avg_cost == Decimal("3500") * Decimal("1.0025")  # 25 bps knob


def test_update_pick_entry_price_on_already_open_pick_does_not_recompute_fill(
    tmp_path: Path,
) -> None:
    store = MVPStore(str(tmp_path / "test.sqlite"))
    store.init_db()
    store.add_pick(_make_pick())
    store.update_pick("pick-1", entry_price=Decimal("3500"))

    store.update_pick("pick-1", entry_price=Decimal("3600"))

    fetched = store.get_pick("pick-1")
    assert fetched is not None
    assert fetched.entry_price == Decimal("3600")
    assert fetched.total_qty == 28
    assert fetched.deployed_capital == Decimal("98000")


def test_update_pick_without_entry_price_stays_pending(tmp_path: Path) -> None:
    store = MVPStore(str(tmp_path / "test.sqlite"))
    store.init_db()
    store.add_pick(_make_pick())

    store.update_pick("pick-1", notes="watching")

    fetched = store.get_pick("pick-1")
    assert fetched is not None
    assert fetched.status == PickStatus.PENDING
    assert fetched.notes == "watching"


def test_close_pick_with_manual_close_sets_closed_at_and_price(tmp_path: Path) -> None:
    store = MVPStore(str(tmp_path / "test.sqlite"))
    store.init_db()
    store.add_pick(_make_pick())

    store.close_pick("pick-1", Decimal("3600"), PickStatus.MANUAL_CLOSE)

    fetched = store.get_pick("pick-1")
    assert fetched is not None
    assert fetched.status == PickStatus.MANUAL_CLOSE
    assert fetched.close_price == Decimal("3600")
    assert fetched.closed_at is not None


def test_close_pick_computes_realized_pnl_with_cost(tmp_path: Path) -> None:
    store = MVPStore(str(tmp_path / "test.sqlite"))
    store.init_db()
    store.add_pick(_make_pick())
    store.update_pick("pick-1", entry_price=Decimal("3500"))

    result = store.close_pick("pick-1", Decimal("3800"), PickStatus.TARGET_HIT)

    fetched = store.get_pick("pick-1")
    assert fetched is not None
    avg_cost = Decimal("3500") * Decimal("1.0025")
    expected_pnl = (Decimal("3800") * Decimal("0.9975") - avg_cost) * 28
    assert fetched.realized_pnl == expected_pnl
    assert result.realized_pnl == expected_pnl
    assert result.total_qty == 28
    assert result.deployed_capital == fetched.deployed_capital
    assert result.avg_cost == avg_cost


def test_close_pick_never_entered_has_zero_realized_pnl(tmp_path: Path) -> None:
    store = MVPStore(str(tmp_path / "test.sqlite"))
    store.init_db()
    store.add_pick(_make_pick())

    result = store.close_pick("pick-1", Decimal("3600"), PickStatus.MANUAL_CLOSE)

    fetched = store.get_pick("pick-1")
    assert fetched is not None
    assert fetched.realized_pnl == Decimal("0")
    assert result.realized_pnl == Decimal("0")
    assert result.total_qty == 0
    assert result.deployed_capital == Decimal("0")
    assert result.avg_cost is None


def test_close_pick_with_non_terminal_status_raises(tmp_path: Path) -> None:
    store = MVPStore(str(tmp_path / "test.sqlite"))
    store.init_db()
    store.add_pick(_make_pick())

    with pytest.raises(ValueError):
        store.close_pick("pick-1", Decimal("3600"), PickStatus.OPEN)


def test_get_distinct_symbols_collapses_duplicates(tmp_path: Path) -> None:
    store = MVPStore(str(tmp_path / "test.sqlite"))
    store.init_db()
    store.add_pick(_make_pick(pick_id="pick-1").model_copy(update={"symbol": "TCS"}))
    store.add_pick(_make_pick(pick_id="pick-2").model_copy(update={"symbol": "TCS"}))
    store.add_pick(_make_pick(pick_id="pick-3").model_copy(update={"symbol": "RELIANCE"}))

    assert store.get_distinct_symbols() == {"TCS", "RELIANCE"}


def test_get_distinct_symbols_empty_when_no_picks(tmp_path: Path) -> None:
    store = MVPStore(str(tmp_path / "test.sqlite"))
    store.init_db()

    assert store.get_distinct_symbols() == set()


def test_get_open_picks_excludes_pending_and_terminal(tmp_path: Path) -> None:
    store = MVPStore(str(tmp_path / "test.sqlite"))
    store.init_db()
    store.add_pick(_make_pick(pick_id="pick-pending"))
    store.add_pick(_make_pick(pick_id="pick-open"))
    store.update_pick("pick-open", entry_price=Decimal("100"))
    store.add_pick(_make_pick(pick_id="pick-closed"))
    store.update_pick("pick-closed", entry_price=Decimal("100"))
    store.close_pick("pick-closed", Decimal("110"), PickStatus.MANUAL_CLOSE)

    open_picks = store.get_open_picks()

    assert [p.pick_id for p in open_picks] == ["pick-open"]


def test_list_picks_filters_by_provider_via_category(tmp_path: Path) -> None:
    store = MVPStore(str(tmp_path / "test.sqlite"))
    store.init_db()
    store.add_provider(_make_provider())
    store.add_category(_make_category())
    store.add_pick(_make_pick(pick_id="pick-1", category_id="cat-1"))
    store.add_pick(_make_pick(pick_id="pick-2", category_id=None))

    picks = store.list_picks(provider_id="prov-1")

    assert [p.pick_id for p in picks] == ["pick-1"]


def test_record_snapshot_get_snapshots_round_trip(tmp_path: Path) -> None:
    store = MVPStore(str(tmp_path / "test.sqlite"))
    store.init_db()
    store.add_pick(_make_pick())

    snapshot_1 = _make_snapshot(captured_at="2026-09-22T09:00:00Z")
    store.record_snapshot(snapshot_1)

    snapshot_2 = MVPSnapshot(
        pick_id="pick-1",
        ltp=Decimal("3500.50"),
        captured_at="2026-09-22T10:00:00Z",
        benchmark_close=Decimal("25000.00"),
    )
    store.record_snapshot(snapshot_2)

    snapshots = store.get_snapshots("pick-1")

    assert len(snapshots) == 2
    assert snapshots[0].captured_at == "2026-09-22T10:00:00Z"
    assert snapshots[0].ltp == Decimal("3500.50")
    assert snapshots[0].benchmark_close == Decimal("25000.00")
    assert snapshots[1].benchmark_close is None
    assert isinstance(snapshots[0].ltp, Decimal)


def test_backfill_snapshots_inserts_all_new_dates(tmp_path: Path) -> None:
    store = MVPStore(str(tmp_path / "test.sqlite"))
    store.init_db()
    store.add_pick(_make_pick())

    daily_closes = [
        (date(2026, 9, 1), Decimal("100.00")),
        (date(2026, 9, 2), Decimal("101.50")),
        (date(2026, 9, 3), Decimal("99.75")),
        (date(2026, 9, 4), Decimal("102.00")),
        (date(2026, 9, 5), Decimal("103.25")),
    ]

    inserted = store.backfill_snapshots("pick-1", daily_closes)

    assert inserted == 5
    assert len(store.get_snapshots("pick-1", limit=10)) == 5


def test_backfill_snapshots_skips_dates_already_present(tmp_path: Path) -> None:
    store = MVPStore(str(tmp_path / "test.sqlite"))
    store.init_db()
    store.add_pick(_make_pick())
    store.backfill_snapshots(
        "pick-1",
        [
            (date(2026, 9, 1), Decimal("100.00")),
            (date(2026, 9, 2), Decimal("101.50")),
        ],
    )

    inserted = store.backfill_snapshots(
        "pick-1",
        [
            (date(2026, 9, 2), Decimal("101.50")),
            (date(2026, 9, 3), Decimal("99.75")),
        ],
    )

    assert inserted == 1
    assert len(store.get_snapshots("pick-1", limit=10)) == 3


def test_get_category_stats_aggregates_wins_and_losses(tmp_path: Path) -> None:
    store = MVPStore(str(tmp_path / "test.sqlite"))
    store.init_db()
    store.add_provider(_make_provider())
    store.add_category(_make_category())

    for i, (entry, close) in enumerate(
        [
            (Decimal("100"), Decimal("150")),  # win
            (Decimal("100"), Decimal("160")),  # win
            (Decimal("100"), Decimal("50")),  # loss
        ]
    ):
        pick_id = f"pick-{i}"
        store.add_pick(_make_pick(pick_id=pick_id, category_id="cat-1"))
        store.update_pick(pick_id, entry_price=entry)
        store.close_pick(pick_id, close, PickStatus.TARGET_HIT)

    stats = store.get_category_stats("cat-1")

    assert stats.closed_count == 3
    assert stats.wins == 2
    assert stats.losses == 1
    assert stats.win_rate == Decimal("2") / Decimal("3")
    assert stats.inception_pnl > 0
    assert stats.invested == Decimal("0")
    assert stats.current == Decimal("0")
    total_deployed = Decimal("100000") * 3
    assert stats.inception_pct == stats.inception_pnl / total_deployed * 100


def test_get_category_stats_with_no_closed_picks_returns_none_win_rate(tmp_path: Path) -> None:
    store = MVPStore(str(tmp_path / "test.sqlite"))
    store.init_db()

    stats = store.get_category_stats("cat-does-not-exist")

    assert stats.closed_count == 0
    assert stats.win_rate is None
    assert stats.inception_pnl == Decimal("0")
    assert stats.inception_pct is None


def test_get_category_stats_inception_pct_combines_realized_and_unrealized(
    tmp_path: Path,
) -> None:
    store = MVPStore(str(tmp_path / "test.sqlite"))
    store.init_db()
    store.add_provider(_make_provider())
    store.add_category(_make_category())

    # Closed pick: entry 100, close 150, qty = floor(100000/100) = 1000 ->
    # deployed_capital = 100000, realized_pnl > 0.
    store.add_pick(_make_pick(pick_id="closed-1", category_id="cat-1"))
    store.update_pick("closed-1", entry_price=Decimal("100"))
    store.close_pick("closed-1", Decimal("150"), PickStatus.TARGET_HIT)

    # Open pick: entry 100 (same fill math), marked to market at 120 via ltp_map.
    store.add_pick(_make_pick(pick_id="open-1", category_id="cat-1"))
    store.update_pick(
        "open-1",
        entry_price=Decimal("100"),
        instrument_key="NSE_EQ|TCS",
    )

    open_pick = store.get_pick("open-1")
    assert open_pick is not None
    ltp_map = {"NSE_EQ|TCS": Decimal("120")}

    stats = store.get_category_stats("cat-1", ltp_map=ltp_map)

    assert stats.closed_count == 1
    assert stats.invested == open_pick.deployed_capital
    assert stats.current == Decimal("120") * open_pick.total_qty
    unrealized_pnl = stats.current - stats.invested
    combined_pnl = stats.inception_pnl + unrealized_pnl
    # Both picks filled identically, so total_deployed is double one fill.
    total_deployed = open_pick.deployed_capital * 2
    assert stats.inception_pct == combined_pnl / total_deployed * 100


def test_get_category_stats_open_pick_without_ltp_uses_deployed_capital(
    tmp_path: Path,
) -> None:
    store = MVPStore(str(tmp_path / "test.sqlite"))
    store.init_db()
    store.add_provider(_make_provider())
    store.add_category(_make_category())

    store.add_pick(_make_pick(pick_id="open-1", category_id="cat-1"))
    store.update_pick(
        "open-1",
        entry_price=Decimal("100"),
        instrument_key="NSE_EQ|TCS",
    )

    stats = store.get_category_stats("cat-1")  # no ltp_map

    assert stats.invested == stats.current
    assert stats.inception_pct == Decimal("0")


def test_category_day_change_weights_by_capital(tmp_path: Path) -> None:
    store = MVPStore(str(tmp_path / "test.sqlite"))
    store.init_db()
    store.add_provider(_make_provider())
    store.add_category(_make_category())

    # pick-a: deployed_capital 100000, +10% day change
    store.add_pick(_make_pick(pick_id="pick-a", category_id="cat-1"))
    store.update_pick("pick-a", entry_price=Decimal("100"))
    store.record_snapshot(
        MVPSnapshot(
            pick_id="pick-a",
            ltp=Decimal("100"),
            captured_at="2026-09-22T15:00:00+00:00",
        )
    )
    store.record_snapshot(
        MVPSnapshot(
            pick_id="pick-a",
            ltp=Decimal("110"),
            captured_at="2026-09-23T15:00:00+00:00",
        )
    )

    # pick-b: deployed_capital 100000, -20% day change
    store.add_pick(_make_pick(pick_id="pick-b", category_id="cat-1"))
    store.update_pick("pick-b", entry_price=Decimal("200"))
    store.record_snapshot(
        MVPSnapshot(
            pick_id="pick-b",
            ltp=Decimal("50"),
            captured_at="2026-09-22T15:00:00+00:00",
        )
    )
    store.record_snapshot(
        MVPSnapshot(
            pick_id="pick-b",
            ltp=Decimal("40"),
            captured_at="2026-09-23T15:00:00+00:00",
        )
    )

    day_change = store.get_category_day_change("cat-1")

    weight = Decimal("100000")
    expected = (Decimal("10") * weight + Decimal("-20") * weight) / (weight + weight)
    assert day_change == expected


def test_get_category_day_change_returns_none_without_two_snapshot_days(
    tmp_path: Path,
) -> None:
    store = MVPStore(str(tmp_path / "test.sqlite"))
    store.init_db()
    store.add_provider(_make_provider())
    store.add_category(_make_category())

    store.add_pick(_make_pick(pick_id="pick-a", category_id="cat-1"))
    store.update_pick("pick-a", entry_price=Decimal("100"))
    # single snapshot day only
    store.record_snapshot(_make_snapshot(pick_id="pick-a"))

    assert store.get_category_day_change("cat-1") is None
    assert store.get_category_day_change("no-such-category") is None


def test_get_category_high_low_tracks_running_max_and_min(tmp_path: Path) -> None:
    store = MVPStore(str(tmp_path / "test.sqlite"))
    store.init_db()
    store.add_provider(_make_provider())
    store.add_category(_make_category())

    # entry_price 100 -> total_qty 1000, deployed_capital 100000
    store.add_pick(_make_pick(pick_id="pick-a", category_id="cat-1"))
    store.update_pick("pick-a", entry_price=Decimal("100"))
    store.record_snapshot(
        MVPSnapshot(pick_id="pick-a", ltp=Decimal("100"), captured_at="2026-09-21T15:00:00+00:00")
    )
    store.record_snapshot(
        MVPSnapshot(pick_id="pick-a", ltp=Decimal("120"), captured_at="2026-09-22T15:00:00+00:00")
    )
    store.record_snapshot(
        MVPSnapshot(pick_id="pick-a", ltp=Decimal("90"), captured_at="2026-09-23T15:00:00+00:00")
    )

    result = store.get_category_high_low("cat-1")

    assert result is not None
    high_pct, low_pct = result
    assert high_pct == Decimal("20")
    assert low_pct == Decimal("-10")


def test_get_category_high_low_returns_none_without_snapshots(tmp_path: Path) -> None:
    store = MVPStore(str(tmp_path / "test.sqlite"))
    store.init_db()
    store.add_provider(_make_provider())
    store.add_category(_make_category())
    store.add_pick(_make_pick(pick_id="pick-a", category_id="cat-1"))

    assert store.get_category_high_low("cat-1") is None
    assert store.get_category_high_low("no-such-category") is None


def test_get_category_high_low_forward_fills_across_picks(tmp_path: Path) -> None:
    store = MVPStore(str(tmp_path / "test.sqlite"))
    store.init_db()
    store.add_provider(_make_provider())
    store.add_category(_make_category())

    # pick-a: entry 100 -> total_qty 1000, deployed_capital 100000; sampled all 3 days
    store.add_pick(_make_pick(pick_id="pick-a", category_id="cat-1"))
    store.update_pick("pick-a", entry_price=Decimal("100"))
    for day, ltp in (("21", "100"), ("22", "100"), ("23", "100")):
        store.record_snapshot(
            MVPSnapshot(
                pick_id="pick-a",
                ltp=Decimal(ltp),
                captured_at=f"2026-09-{day}T15:00:00+00:00",
            )
        )

    # pick-b: entry 100 -> total_qty 1000, deployed_capital 100000; sampled day 1 and 3 only
    store.add_pick(_make_pick(pick_id="pick-b", category_id="cat-1"))
    store.update_pick("pick-b", entry_price=Decimal("100"))
    store.record_snapshot(
        MVPSnapshot(pick_id="pick-b", ltp=Decimal("100"), captured_at="2026-09-21T15:00:00+00:00")
    )
    store.record_snapshot(
        MVPSnapshot(pick_id="pick-b", ltp=Decimal("140"), captured_at="2026-09-23T15:00:00+00:00")
    )

    # day 2: pick-a at 100 (sampled), pick-b forward-filled at 100 (from day 1) -> pct 0
    # day 3: pick-a at 100, pick-b at 140 -> current 240000, invested 200000 -> pct +20
    result = store.get_category_high_low("cat-1")

    assert result is not None
    high_pct, low_pct = result
    assert high_pct == Decimal("20")
    assert low_pct == Decimal("0")


def test_get_category_high_low_forward_fills_unsampled_picks(tmp_path: Path) -> None:
    store = MVPStore(str(tmp_path / "test.sqlite"))
    store.init_db()
    store.add_provider(_make_provider())
    store.add_category(_make_category())

    # pick-a: entry 100 -> 1000 qty; pick-b: entry 50 -> 2000 qty; both 100000 deployed
    store.add_pick(_make_pick(pick_id="pick-a", category_id="cat-1"))
    store.update_pick("pick-a", entry_price=Decimal("100"))
    store.add_pick(_make_pick(pick_id="pick-b", category_id="cat-1"))
    store.update_pick("pick-b", entry_price=Decimal("50"))
    for day, ltp in (("21", "100"), ("22", "120"), ("23", "90")):
        store.record_snapshot(
            MVPSnapshot(
                pick_id="pick-a", ltp=Decimal(ltp), captured_at=f"2026-09-{day}T15:00:00+00:00"
            )
        )
    # pick-b sampled only on the 22nd; its 60 must carry forward to the 23rd
    store.record_snapshot(
        MVPSnapshot(pick_id="pick-b", ltp=Decimal("60"), captured_at="2026-09-22T15:00:00+00:00")
    )

    # 21st: a only, 0%; 22nd: 240000/200000 = +20%; 23rd: (90000+120000)/200000 = +5%
    assert store.get_category_high_low("cat-1") == (Decimal("20"), Decimal("0"))

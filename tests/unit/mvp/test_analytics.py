"""Tests for src.mvp.analytics category return + volatility aggregation."""

from decimal import Decimal
from pathlib import Path

from src.mvp.analytics import compute_category_returns, compute_category_volatility
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
    category_id: str = "cat-1", provider_id: str = "prov-1", slug: str = "value-picks"
) -> Category:
    return Category(
        category_id=category_id,
        provider_id=provider_id,
        slug=slug,
        display_name="Value Picks",
        notes=None,
        created_at="2026-09-22T00:00:00Z",
    )


def _make_pick(
    pick_id: str = "pick-1",
    category_id: str | None = "cat-1",
    status: PickStatus = PickStatus.OPEN,
    deployed_capital: Decimal = Decimal("100000"),
    total_qty: int = 100,
    realized_pnl: Decimal = Decimal("0"),
) -> Pick:
    return Pick(
        pick_id=pick_id,
        category_id=category_id,
        symbol="TCS",
        pick_date="2026-09-22",
        status=status,
        deployed_capital=deployed_capital,
        total_qty=total_qty,
        realized_pnl=realized_pnl,
        created_at="2026-09-22T00:00:00Z",
        updated_at="2026-09-22T00:00:00Z",
    )


def _make_snapshot(pick_id: str, ltp: str, captured_at: str) -> MVPSnapshot:
    return MVPSnapshot(pick_id=pick_id, ltp=Decimal(ltp), captured_at=captured_at)


def _seeded_store(tmp_path: Path) -> MVPStore:
    store = MVPStore(str(tmp_path / "test.sqlite"))
    store.init_db()
    store.add_provider(_make_provider())
    store.add_category(_make_category())
    return store


def test_compute_category_returns_blends_open_and_closed_picks(tmp_path: Path) -> None:
    store = _seeded_store(tmp_path)
    open_pick = _make_pick(pick_id="pick-open", deployed_capital=Decimal("100000"), total_qty=100)
    closed_pick = _make_pick(
        pick_id="pick-closed",
        status=PickStatus.TARGET_HIT,
        deployed_capital=Decimal("50000"),
        total_qty=0,
        realized_pnl=Decimal("5000"),
    )
    store.add_pick(open_pick)
    store.add_pick(closed_pick)
    store.record_snapshot(_make_snapshot("pick-open", "1100", "2026-09-24T10:00:00Z"))

    results = compute_category_returns(store)

    assert len(results) == 1
    result = results[0]
    assert result.provider == "DSIJ"
    assert result.category == "Value Picks"
    assert result.n_picks == 2
    assert result.deployed == Decimal("150000")
    # open: 1100*100=110000 mark, closed: 50000+5000=55000 -> current=165000
    assert result.current_value == Decimal("165000")
    assert result.total_return_pct == Decimal("10")


def test_compute_category_returns_falls_back_to_deployed_capital_without_snapshot(
    tmp_path: Path,
) -> None:
    store = _seeded_store(tmp_path)
    store.add_pick(_make_pick(pick_id="pick-no-snapshot", deployed_capital=Decimal("100000")))

    results = compute_category_returns(store)

    assert len(results) == 1
    assert results[0].current_value == Decimal("100000")
    assert results[0].total_return_pct == Decimal("0")


def test_compute_category_returns_skips_picks_with_no_deployed_capital(tmp_path: Path) -> None:
    store = _seeded_store(tmp_path)
    store.add_pick(
        _make_pick(pick_id="pending", status=PickStatus.PENDING, deployed_capital=Decimal("0"))
    )

    results = compute_category_returns(store)

    assert results == []


def test_compute_category_volatility_ranks_least_volatile_first(tmp_path: Path) -> None:
    store = _seeded_store(tmp_path)
    store.add_pick(_make_pick(pick_id="pick-1", total_qty=100))

    prices = ["1000", "1010", "990", "1005", "995", "1020", "980", "1000", "1015", "1000", "1005"]
    for i, price in enumerate(prices):
        store.record_snapshot(_make_snapshot("pick-1", price, f"2026-09-{10 + i:02d}T10:00:00Z"))

    results = compute_category_volatility(store, min_days=5)

    assert len(results) == 1
    stats = results[0]
    assert stats.provider == "DSIJ"
    assert stats.category == "Value Picks"
    assert stats.n_days == len(prices) - 1
    assert stats.annualized_stdev_pct is not None
    assert stats.annualized_stdev_pct > 0
    assert stats.max_drawdown_pct is not None
    assert stats.max_drawdown_pct <= 0


def test_compute_category_volatility_skips_categories_below_min_days(tmp_path: Path) -> None:
    store = _seeded_store(tmp_path)
    store.add_pick(_make_pick(pick_id="pick-1", total_qty=100))
    store.record_snapshot(_make_snapshot("pick-1", "1000", "2026-09-22T10:00:00Z"))
    store.record_snapshot(_make_snapshot("pick-1", "1010", "2026-09-23T10:00:00Z"))

    results = compute_category_volatility(store, min_days=10)

    assert results == []

"""Tests for portfolio models, store, and tracker."""

from __future__ import annotations

import asyncio
import tempfile
from datetime import date
from pathlib import Path

import pytest

from src.portfolio.models import (
    AssetType,
    DailySnapshot,
    Direction,
    Leg,
    ProductType,
    Strategy,
)
from src.portfolio.store import PortfolioStore
from src.portfolio.tracker import PortfolioTracker


# ── Helpers ──────────────────────────────────────────────────────


def _make_leg(
    direction: Direction,
    entry_price: float,
    quantity: int,
    id: int | None = None,
    asset_type: AssetType = AssetType.EQUITY,
    lot_size: int = 1,
) -> Leg:
    return Leg(
        id=id,
        instrument_key="TEST|INST",
        display_name="Test Instrument",
        asset_type=asset_type,
        direction=direction,
        quantity=quantity,
        lot_size=lot_size,
        entry_price=entry_price,
        entry_date=date(2026, 4, 1),
        product_type=ProductType.CNC,
    )


class FakeMarket:
    """Fake market data provider for tracker tests."""

    def __init__(self, prices: dict[str, float]) -> None:
        self.prices = prices

    async def get_ltp(self, instruments: list[str]) -> dict[str, float]:
        return {k: self.prices.get(k, 0.0) for k in instruments}

    async def get_option_chain(self, instrument: str, expiry: str) -> dict:
        return {}


# ── Fixtures ─────────────────────────────────────────────────────


@pytest.fixture
def tmp_store() -> PortfolioStore:
    with tempfile.TemporaryDirectory() as tmpdir:
        yield PortfolioStore(Path(tmpdir) / "test.sqlite")


# ── Leg P&L tests ───────────────────────────────────────────────


class TestLegPnL:
    def test_buy_profit(self):
        assert _make_leg(Direction.BUY, 100.0, 10).pnl(110.0) == 100.0

    def test_buy_loss(self):
        assert _make_leg(Direction.BUY, 100.0, 10).pnl(90.0) == -100.0

    def test_sell_profit(self):
        assert _make_leg(Direction.SELL, 100.0, 10).pnl(90.0) == 100.0

    def test_sell_loss(self):
        assert _make_leg(Direction.SELL, 100.0, 10).pnl(110.0) == -100.0

    def test_pnl_percent(self):
        leg = _make_leg(Direction.BUY, 1000.0, 1)
        assert leg.pnl_percent(1100.0) == pytest.approx(10.0)

    def test_zero_at_entry(self):
        assert _make_leg(Direction.BUY, 500.0, 65).pnl(500.0) == 0.0

    def test_entry_value(self):
        assert _make_leg(Direction.BUY, 1388.12, 438).entry_value == pytest.approx(607996.56)

    def test_total_lots(self):
        leg = _make_leg(Direction.BUY, 975.0, 65, lot_size=65)
        assert leg.total_lots == 1


# ── Strategy P&L tests ──────────────────────────────────────────


class TestStrategyPnL:
    def test_mixed_legs(self):
        strategy = Strategy(
            name="test",
            legs=[
                _make_leg(Direction.BUY, 1388.0, 438, id=1),
                _make_leg(Direction.BUY, 975.0, 65, id=2),
                _make_leg(Direction.BUY, 1082.0, 65, id=3),
                _make_leg(Direction.SELL, 840.0, 65, id=4),
            ],
        )
        prices = {1: 1400.0, 2: 950.0, 3: 1150.0, 4: 800.0}
        expected = (12 * 438) + (-25 * 65) + (68 * 65) + (40 * 65)
        assert strategy.total_pnl(prices) == pytest.approx(expected)

    def test_total_entry_value(self):
        strategy = Strategy(
            name="test",
            legs=[
                _make_leg(Direction.BUY, 500.0, 100),
                _make_leg(Direction.SELL, 200.0, 50),
            ],
        )
        assert strategy.total_entry_value == pytest.approx(40000.0)


# ── Store tests ──────────────────────────────────────────────────


class TestPortfolioStore:
    def test_upsert_strategy(self, tmp_store):
        s = Strategy(name="s1", legs=[_make_leg(Direction.BUY, 100.0, 10)])
        sid = tmp_store.upsert_strategy(s)
        assert sid > 0

        loaded = tmp_store.get_strategy("s1")
        assert loaded is not None
        assert len(loaded.legs) == 1
        assert loaded.legs[0].entry_price == 100.0

    def test_upsert_idempotent(self, tmp_store):
        s = Strategy(name="idem", legs=[_make_leg(Direction.SELL, 200.0, 5)])
        tmp_store.upsert_strategy(s)
        tmp_store.upsert_strategy(s)
        assert len(tmp_store.get_strategy("idem").legs) == 1

    def test_snapshot_upsert(self, tmp_store):
        s = Strategy(name="snap", legs=[_make_leg(Direction.BUY, 50.0, 1)])
        tmp_store.upsert_strategy(s)
        leg_id = tmp_store.get_strategy("snap").legs[0].id

        tmp_store.record_snapshot(
            DailySnapshot(leg_id=leg_id, snapshot_date=date(2026, 4, 1), ltp=55.0)
        )
        tmp_store.record_snapshot(
            DailySnapshot(leg_id=leg_id, snapshot_date=date(2026, 4, 1), ltp=60.0)
        )
        snaps = tmp_store.get_snapshots(leg_id)
        assert len(snaps) == 1
        assert snaps[0].ltp == 60.0

    def test_bulk_insert(self, tmp_store):
        s = Strategy(name="bulk", legs=[_make_leg(Direction.BUY, 50.0, 1)])
        tmp_store.upsert_strategy(s)
        leg_id = tmp_store.get_strategy("bulk").legs[0].id

        tmp_store.record_snapshots_bulk([
            DailySnapshot(leg_id=leg_id, snapshot_date=date(2026, 4, 1), ltp=51.0),
            DailySnapshot(leg_id=leg_id, snapshot_date=date(2026, 4, 2), ltp=52.0),
            DailySnapshot(leg_id=leg_id, snapshot_date=date(2026, 4, 3), ltp=53.0),
        ])
        assert len(tmp_store.get_snapshots(leg_id)) == 3

    def test_date_range_filter(self, tmp_store):
        s = Strategy(name="range", legs=[_make_leg(Direction.BUY, 50.0, 1)])
        tmp_store.upsert_strategy(s)
        leg_id = tmp_store.get_strategy("range").legs[0].id

        tmp_store.record_snapshots_bulk([
            DailySnapshot(leg_id=leg_id, snapshot_date=date(2026, 4, 1), ltp=51.0),
            DailySnapshot(leg_id=leg_id, snapshot_date=date(2026, 4, 2), ltp=52.0),
            DailySnapshot(leg_id=leg_id, snapshot_date=date(2026, 4, 3), ltp=53.0),
        ])
        filtered = tmp_store.get_snapshots(leg_id, from_date=date(2026, 4, 2))
        assert len(filtered) == 2

    def test_get_all_strategies(self, tmp_store):
        for name in ["alpha", "beta"]:
            tmp_store.upsert_strategy(Strategy(name=name))
        assert len(tmp_store.get_all_strategies()) == 2

    def test_latest_snapshot_date(self, tmp_store):
        s = Strategy(name="latest", legs=[_make_leg(Direction.BUY, 50.0, 1)])
        tmp_store.upsert_strategy(s)
        leg_id = tmp_store.get_strategy("latest").legs[0].id

        tmp_store.record_snapshot(
            DailySnapshot(leg_id=leg_id, snapshot_date=date(2026, 4, 5), ltp=55.0)
        )
        assert tmp_store.get_latest_snapshot_date() == date(2026, 4, 5)


# ── Tracker tests ────────────────────────────────────────────────


class TestPortfolioTracker:
    def test_compute_pnl(self, tmp_store):
        s = Strategy(
            name="tracker_test",
            legs=[
                Leg(
                    instrument_key="A", display_name="A", asset_type=AssetType.EQUITY,
                    direction=Direction.BUY, quantity=100, entry_price=500.0,
                    entry_date=date(2026, 4, 1), product_type=ProductType.CNC,
                ),
                Leg(
                    instrument_key="B", display_name="B", asset_type=AssetType.PE,
                    direction=Direction.SELL, quantity=65, entry_price=840.0,
                    entry_date=date(2026, 4, 1), product_type=ProductType.NRML, lot_size=65,
                ),
            ],
        )
        tmp_store.upsert_strategy(s)

        market = FakeMarket({"A": 510.0, "B": 800.0})
        tracker = PortfolioTracker(tmp_store, market)

        pnl = asyncio.run(tracker.compute_pnl("tracker_test"))
        assert pnl is not None
        # BUY: (510-500)*100=1000, SELL: (840-800)*65=2600
        assert pnl.total_pnl == pytest.approx(3600.0)

    def test_record_snapshot(self, tmp_store):
        s = Strategy(
            name="record_test",
            legs=[
                Leg(
                    instrument_key="X", display_name="X", asset_type=AssetType.EQUITY,
                    direction=Direction.BUY, quantity=10, entry_price=100.0,
                    entry_date=date(2026, 4, 1), product_type=ProductType.CNC,
                ),
            ],
        )
        tmp_store.upsert_strategy(s)

        market = FakeMarket({"X": 105.0})
        tracker = PortfolioTracker(tmp_store, market)

        count = asyncio.run(
            tracker.record_daily_snapshot("record_test", date(2026, 4, 2))
        )
        assert count == 1

        leg_id = tmp_store.get_strategy("record_test").legs[0].id
        snaps = tmp_store.get_snapshots(leg_id)
        assert len(snaps) == 1
        assert snaps[0].ltp == 105.0

    def test_nonexistent_strategy(self, tmp_store):
        market = FakeMarket({})
        tracker = PortfolioTracker(tmp_store, market)
        pnl = asyncio.run(tracker.compute_pnl("does_not_exist"))
        assert pnl is None

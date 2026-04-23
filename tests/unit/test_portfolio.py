"""Tests for portfolio models, store, and tracker."""

from __future__ import annotations

import asyncio
import tempfile
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from src.models.portfolio import (
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
        assert _make_leg(Direction.BUY, 100.0, 10).pnl(110.0) == Decimal("100")

    def test_buy_loss(self):
        assert _make_leg(Direction.BUY, 100.0, 10).pnl(90.0) == Decimal("-100")

    def test_sell_profit(self):
        assert _make_leg(Direction.SELL, 100.0, 10).pnl(90.0) == Decimal("100")

    def test_sell_loss(self):
        assert _make_leg(Direction.SELL, 100.0, 10).pnl(110.0) == Decimal("-100")

    def test_pnl_percent(self):
        leg = _make_leg(Direction.BUY, "1000.00", 1)
        assert leg.pnl_percent(1100.0) == Decimal("10")

    def test_zero_at_entry(self):
        assert _make_leg(Direction.BUY, 500.0, 65).pnl(500.0) == Decimal("0")

    def test_entry_value(self):
        leg = _make_leg(Direction.BUY, "1388.12", 438)
        assert leg.entry_value == Decimal("1388.12") * 438

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
        expected = Decimal((12 * 438) + (-25 * 65) + (68 * 65) + (40 * 65))
        assert strategy.total_pnl(prices) == expected

    def test_total_entry_value(self):
        strategy = Strategy(
            name="test",
            legs=[
                _make_leg(Direction.BUY, 500.0, 100),
                _make_leg(Direction.SELL, 200.0, 50),
            ],
        )
        assert strategy.total_entry_value == Decimal("40000")


# ── Store tests ──────────────────────────────────────────────────


class TestPortfolioStore:
    def test_upsert_strategy(self, tmp_store):
        s = Strategy(name="s1", legs=[_make_leg(Direction.BUY, 100.0, 10)])
        sid = tmp_store.upsert_strategy(s)
        assert sid > 0

        loaded = tmp_store.get_strategy("s1")
        assert loaded is not None
        assert len(loaded.legs) == 1
        assert loaded.legs[0].entry_price == Decimal("100.0")

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
        assert snaps[0].ltp == Decimal("60.0")

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

    # ── get_snapshots_for_date ───────────────────────────────────

    def test_get_snapshots_for_date_returns_correct_leg_ids(self, tmp_store):
        """Snapshots for the queried date are returned keyed by leg_id."""
        s = Strategy(name="hist", legs=[
            _make_leg(Direction.BUY, 100.0, 10),
            _make_leg(Direction.SELL, 200.0, 5),
        ])
        tmp_store.upsert_strategy(s)
        legs = tmp_store.get_strategy("hist").legs
        leg_a, leg_b = legs[0].id, legs[1].id

        tmp_store.record_snapshots_bulk([
            DailySnapshot(leg_id=leg_a, snapshot_date=date(2026, 4, 6), ltp=Decimal("110")),
            DailySnapshot(leg_id=leg_b, snapshot_date=date(2026, 4, 6), ltp=Decimal("190")),
        ])

        result = tmp_store.get_snapshots_for_date(date(2026, 4, 6))
        assert set(result.keys()) == {leg_a, leg_b}
        assert result[leg_a].ltp == Decimal("110")
        assert result[leg_b].ltp == Decimal("190")

    def test_get_snapshots_for_date_excludes_other_dates(self, tmp_store):
        """Snapshots from other dates must not appear in the result."""
        s = Strategy(name="excl", legs=[_make_leg(Direction.BUY, 50.0, 1)])
        tmp_store.upsert_strategy(s)
        leg_id = tmp_store.get_strategy("excl").legs[0].id

        tmp_store.record_snapshots_bulk([
            DailySnapshot(leg_id=leg_id, snapshot_date=date(2026, 4, 6), ltp=Decimal("55")),
            DailySnapshot(leg_id=leg_id, snapshot_date=date(2026, 4, 7), ltp=Decimal("60")),
        ])

        result = tmp_store.get_snapshots_for_date(date(2026, 4, 6))
        assert len(result) == 1
        assert result[leg_id].ltp == Decimal("55")

    def test_get_snapshots_for_date_empty_when_no_data(self, tmp_store):
        """Returns an empty dict when no snapshots exist for the requested date."""
        result = tmp_store.get_snapshots_for_date(date(2026, 4, 6))
        assert result == {}

    def test_get_snapshots_for_date_preserves_underlying_price(self, tmp_store):
        """underlying_price stored in the snapshot is returned faithfully."""
        s = Strategy(name="up", legs=[_make_leg(Direction.BUY, 100.0, 1)])
        tmp_store.upsert_strategy(s)
        leg_id = tmp_store.get_strategy("up").legs[0].id

        tmp_store.record_snapshot(
            DailySnapshot(
                leg_id=leg_id,
                snapshot_date=date(2026, 4, 7),
                ltp=Decimal("105"),
                underlying_price=Decimal("23500.50"),
            )
        )
        result = tmp_store.get_snapshots_for_date(date(2026, 4, 7))
        assert result[leg_id].underlying_price == Decimal("23500.50")

    # ── get_prev_snapshots ───────────────────────────────────────

    def test_get_prev_snapshots_returns_most_recent_prior_date(self, tmp_store):
        """Returns the nearest prior day's snapshots, not the queried date."""
        s = Strategy(name="prev", legs=[_make_leg(Direction.BUY, 100.0, 1)])
        tmp_store.upsert_strategy(s)
        leg_id = tmp_store.get_strategy("prev").legs[0].id

        tmp_store.record_snapshots_bulk([
            DailySnapshot(leg_id=leg_id, snapshot_date=date(2026, 4, 6), ltp=Decimal("95")),
            DailySnapshot(leg_id=leg_id, snapshot_date=date(2026, 4, 7), ltp=Decimal("100")),
        ])

        result = tmp_store.get_prev_snapshots(date(2026, 4, 7))
        assert set(result.keys()) == {leg_id}
        assert result[leg_id].ltp == Decimal("95")

    def test_get_prev_snapshots_skips_gap_handles_weekend(self, tmp_store):
        """Calendar gaps (weekend / holiday) are handled — returns Friday when queried on Monday."""
        s = Strategy(name="gap", legs=[_make_leg(Direction.SELL, 200.0, 5)])
        tmp_store.upsert_strategy(s)
        leg_id = tmp_store.get_strategy("gap").legs[0].id

        # Friday snapshot only — simulates Monday query with no Saturday/Sunday rows
        tmp_store.record_snapshot(
            DailySnapshot(leg_id=leg_id, snapshot_date=date(2026, 4, 3), ltp=Decimal("190"))
        )

        result = tmp_store.get_prev_snapshots(date(2026, 4, 6))  # Monday
        assert result[leg_id].ltp == Decimal("190")

    def test_get_prev_snapshots_excludes_same_date(self, tmp_store):
        """The reference date itself must not appear in the result."""
        s = Strategy(name="same", legs=[_make_leg(Direction.BUY, 50.0, 1)])
        tmp_store.upsert_strategy(s)
        leg_id = tmp_store.get_strategy("same").legs[0].id

        tmp_store.record_snapshot(
            DailySnapshot(leg_id=leg_id, snapshot_date=date(2026, 4, 7), ltp=Decimal("55"))
        )

        result = tmp_store.get_prev_snapshots(date(2026, 4, 7))
        assert result == {}

    def test_get_prev_snapshots_empty_when_no_prior_data(self, tmp_store):
        """Returns empty dict when no snapshots exist before the reference date."""
        result = tmp_store.get_prev_snapshots(date(2026, 4, 6))
        assert result == {}


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
        assert pnl.total_pnl == Decimal("3600")

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

        count, pnl = asyncio.run(
            tracker.record_daily_snapshot("record_test", date(2026, 4, 2))
        )
        assert count == 1
        assert pnl is not None
        assert pnl.total_pnl == Decimal("50")

        leg_id = tmp_store.get_strategy("record_test").legs[0].id
        snaps = tmp_store.get_snapshots(leg_id)
        assert len(snaps) == 1
        assert snaps[0].ltp == Decimal("105.0")

    def test_nonexistent_strategy(self, tmp_store):
        market = FakeMarket({})
        tracker = PortfolioTracker(tmp_store, market)
        pnl = asyncio.run(tracker.compute_pnl("does_not_exist"))
        assert pnl is None

    def test_compute_pnl_zero_ltp_used_as_is(self, tmp_store):
        """A zero LTP (option expiring worthless) must be used as-is,
        not replaced by entry_price as the old `if not raw_ltp:` bug did.

        AR-1: prices.get(key) + `if raw_ltp is None:` fix.
        """
        s = Strategy(
            name="zero_ltp_test",
            legs=[
                Leg(
                    instrument_key="OPT|KEY",
                    display_name="Short PE expiring worthless",
                    asset_type=AssetType.PE,
                    direction=Direction.SELL,
                    quantity=65,
                    lot_size=65,
                    entry_price=500.0,
                    entry_date=date(2026, 4, 1),
                    product_type=ProductType.NRML,
                ),
            ],
        )
        tmp_store.upsert_strategy(s)

        # Explicitly provide LTP=0.0 (option has expired worthless).
        market = FakeMarket({"OPT|KEY": 0.0})
        tracker = PortfolioTracker(tmp_store, market)

        pnl = asyncio.run(tracker.compute_pnl("zero_ltp_test"))

        assert pnl is not None
        leg_pnl = pnl.legs[0]
        # LTP must be 0, not entry_price (500).
        assert leg_pnl.current_price == Decimal("0")
        # SELL P&L = (entry - ltp) * qty = (500 - 0) * 65 = 32500
        assert leg_pnl.pnl == Decimal("32500")

    def test_record_daily_snapshot_uses_provided_prices(self, tmp_store):
        from unittest.mock import patch
        s = Strategy(
            name="pass_through_test",
            legs=[
                Leg(
                    instrument_key="Y", display_name="Y", asset_type=AssetType.EQUITY,
                    direction=Direction.BUY, quantity=10, entry_price=100.0,
                    entry_date=date(2026, 4, 1), product_type=ProductType.CNC,
                ),
            ],
        )
        tmp_store.upsert_strategy(s)

        market = FakeMarket({"Y": 105.0})
        tracker = PortfolioTracker(tmp_store, market)

        with patch.object(market, "get_ltp", wraps=market.get_ltp) as spy:
            count, pnl = asyncio.run(
                tracker.record_daily_snapshot("pass_through_test", date(2026, 4, 2), prices={"Y": 110.0})
            )
            assert count == 1
            assert spy.call_count == 0  # market.get_ltp was skipped
            assert pnl.total_pnl == Decimal("100")  # (110 - 100) * 10

    def test_record_all_strategies_uses_provided_prices(self, tmp_store):
        from unittest.mock import patch
        for name in ["strat1", "strat2"]:
            tmp_store.upsert_strategy(Strategy(
                name=name,
                legs=[
                    Leg(
                        instrument_key=name, display_name=name, asset_type=AssetType.EQUITY,
                        direction=Direction.BUY, quantity=10, entry_price=100.0,
                        entry_date=date(2026, 4, 1), product_type=ProductType.CNC,
                    )
                ]
            ))

        market = FakeMarket({"strat1": 110.0, "strat2": 120.0})
        tracker = PortfolioTracker(tmp_store, market)

        with patch.object(market, "get_ltp", wraps=market.get_ltp) as spy:
            counts, pnls = asyncio.run(tracker.record_all_strategies(
                snapshot_date=date(2026, 4, 2),
                prices={"strat1": 110.0, "strat2": 120.0}
            ))
            
            assert spy.call_count == 0  # no internal get_ltp calls because prices were provided
            assert len(counts) == 2
            assert len(pnls) == 2
            assert pnls["strat1"].total_pnl == Decimal("100")
            assert pnls["strat2"].total_pnl == Decimal("200")

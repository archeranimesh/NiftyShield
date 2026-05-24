"""Tests for portfolio models, store, and tracker."""

from __future__ import annotations

import asyncio
import tempfile
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from src.models.portfolio import (
    AssetType,
    DailySnapshot,
    Direction,
    HedgeStrategy,
    Leg,
    ProductType,
    Strategy,
    create_strategy_instance,
    register_strategy_type,
)
from src.portfolio.store import PortfolioStore
from src.portfolio.tracker import PortfolioTracker
from src.portfolio.service import SnapshotService


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


class TestLegValidation:
    def test_valid_legs(self):
        # 1. Equity: no expiry, no strike
        leg_eq = Leg(
            instrument_key="EQ_TEST",
            display_name="Equity Test",
            asset_type=AssetType.EQUITY,
            direction=Direction.BUY,
            quantity=10,
            lot_size=1,
            entry_price=Decimal("150.00"),
            entry_date=date(2026, 4, 1),
            product_type=ProductType.CNC,
        )
        assert leg_eq.expiry is None
        assert leg_eq.strike is None

        # 2. Futures: expiry must be not None, strike must be None
        leg_fut = Leg(
            instrument_key="FUT_TEST",
            display_name="Futures Test",
            asset_type=AssetType.FUTURES,
            direction=Direction.BUY,
            quantity=1,
            lot_size=75,
            entry_price=Decimal("22000.00"),
            entry_date=date(2026, 4, 1),
            expiry=date(2026, 1, 1),  # Jan 1, 2026 is a Thursday
            product_type=ProductType.NRML,
        )
        assert leg_fut.expiry == date(2026, 1, 1)
        assert leg_fut.strike is None

        # 3. Option PE: expiry and strike not None
        leg_pe = Leg(
            instrument_key="PE_TEST",
            display_name="PE Test",
            asset_type=AssetType.PE,
            direction=Direction.SELL,
            quantity=75,
            lot_size=75,
            entry_price=Decimal("100.00"),
            entry_date=date(2026, 4, 1),
            expiry=date(2026, 1, 1),  # Jan 1, 2026 is Thursday
            strike=Decimal("22000.00"),
            product_type=ProductType.NRML,
        )
        assert leg_pe.expiry == date(2026, 1, 1)
        assert leg_pe.strike == Decimal("22000.00")

    def test_invalid_asset_type_invariants(self):
        # Equity with expiry
        with pytest.raises(
            ValidationError, match="Expiry must be None for EQUITY"
        ):
            Leg(
                instrument_key="EQ_TEST",
                display_name="Equity Test",
                asset_type=AssetType.EQUITY,
                direction=Direction.BUY,
                quantity=10,
                entry_price=Decimal("150.00"),
                entry_date=date(2026, 4, 1),
                product_type=ProductType.CNC,
                expiry=date(2026, 1, 1),
            )

        # Equity with strike
        with pytest.raises(
            ValidationError, match="Strike must be None for EQUITY"
        ):
            Leg(
                instrument_key="EQ_TEST",
                display_name="Equity Test",
                asset_type=AssetType.EQUITY,
                direction=Direction.BUY,
                quantity=10,
                entry_price=Decimal("150.00"),
                entry_date=date(2026, 4, 1),
                product_type=ProductType.CNC,
                strike=Decimal("150"),
            )

        # Bond with expiry
        with pytest.raises(
            ValidationError, match="Expiry must be None for BOND"
        ):
            Leg(
                instrument_key="BOND_TEST",
                display_name="Bond Test",
                asset_type=AssetType.BOND,
                direction=Direction.BUY,
                quantity=10,
                entry_price=Decimal("150.00"),
                entry_date=date(2026, 4, 1),
                product_type=ProductType.CNC,
                expiry=date(2026, 1, 1),
            )

        # Bond with strike
        with pytest.raises(
            ValidationError, match="Strike must be None for BOND"
        ):
            Leg(
                instrument_key="BOND_TEST",
                display_name="Bond Test",
                asset_type=AssetType.BOND,
                direction=Direction.BUY,
                quantity=10,
                entry_price=Decimal("150.00"),
                entry_date=date(2026, 4, 1),
                product_type=ProductType.CNC,
                strike=Decimal("150"),
            )

        # Futures without expiry
        with pytest.raises(
            ValidationError, match="Expiry must not be None for FUTURES"
        ):
            Leg(
                instrument_key="FUT_TEST",
                display_name="Futures Test",
                asset_type=AssetType.FUTURES,
                direction=Direction.BUY,
                quantity=75,
                entry_price=Decimal("22000.00"),
                entry_date=date(2026, 4, 1),
                product_type=ProductType.NRML,
            )

        # Futures with strike
        with pytest.raises(
            ValidationError, match="Strike must be None for FUTURES"
        ):
            Leg(
                instrument_key="FUT_TEST",
                display_name="Futures Test",
                asset_type=AssetType.FUTURES,
                direction=Direction.BUY,
                quantity=75,
                entry_price=Decimal("22000.00"),
                entry_date=date(2026, 4, 1),
                product_type=ProductType.NRML,
                expiry=date(2026, 1, 1),
                strike=Decimal("22000"),
            )

        # Option without expiry
        with pytest.raises(
            ValidationError,
            match="Expiry must not be None for option type CE",
        ):
            Leg(
                instrument_key="CE_TEST",
                display_name="CE Test",
                asset_type=AssetType.CE,
                direction=Direction.BUY,
                quantity=75,
                entry_price=Decimal("100.00"),
                entry_date=date(2026, 4, 1),
                product_type=ProductType.NRML,
                strike=Decimal("22000"),
            )

        # Option without strike
        with pytest.raises(
            ValidationError,
            match="Strike must not be None for option type PE",
        ):
            Leg(
                instrument_key="PE_TEST",
                display_name="PE Test",
                asset_type=AssetType.PE,
                direction=Direction.BUY,
                quantity=75,
                entry_price=Decimal("100.00"),
                entry_date=date(2026, 4, 1),
                product_type=ProductType.NRML,
                expiry=date(2026, 1, 1),
            )

    def test_nifty_strike_grid_validation(self):
        # Valid Nifty strike < 18000: multiple of 50
        Leg(
            instrument_key="NIFTY_PE",
            display_name="NIFTY 17550 PE",
            asset_type=AssetType.PE,
            direction=Direction.BUY,
            quantity=75,
            entry_price=Decimal("100.00"),
            entry_date=date(2026, 4, 1),
            product_type=ProductType.NRML,
            expiry=date(2026, 1, 1),
            strike=Decimal("17550"),
        )

        # Invalid Nifty strike < 18000: not multiple of 50
        with pytest.raises(
            ValidationError,
            match="Nifty strike 17525.5 must be a multiple of 50",
        ):
            Leg(
                instrument_key="NIFTY_PE",
                display_name="NIFTY 17525.5 PE",
                asset_type=AssetType.PE,
                direction=Direction.BUY,
                quantity=75,
                entry_price=Decimal("100.00"),
                entry_date=date(2026, 4, 1),
                product_type=ProductType.NRML,
                expiry=date(2026, 1, 1),
                strike=Decimal("17525.5"),
            )

        # Valid Nifty strike >= 18000: multiple of 100
        Leg(
            instrument_key="NIFTY_CE",
            display_name="NIFTY 22100 CE",
            asset_type=AssetType.CE,
            direction=Direction.BUY,
            quantity=75,
            entry_price=Decimal("100.00"),
            entry_date=date(2026, 4, 1),
            product_type=ProductType.NRML,
            expiry=date(2026, 1, 1),
            strike=Decimal("22100"),
        )

        # Invalid Nifty strike >= 18000: multiple of 50 but not 100
        with pytest.raises(
            ValidationError,
            match=r"Nifty strike 22150\.0 must be a multiple of 100",
        ):
            Leg(
                instrument_key="NIFTY_CE",
                display_name="NIFTY 22150 CE",
                asset_type=AssetType.CE,
                direction=Direction.BUY,
                quantity=75,
                entry_price=Decimal("100.00"),
                entry_date=date(2026, 4, 1),
                product_type=ProductType.NRML,
                expiry=date(2026, 1, 1),
                strike=Decimal("22150.0"),
            )

        # Non-Nifty option is not grid validated
        Leg(
            instrument_key="OTHER_CE",
            display_name="OTHER 22150 CE",
            asset_type=AssetType.CE,
            direction=Direction.BUY,
            quantity=75,
            entry_price=Decimal("100.00"),
            entry_date=date(2026, 4, 1),
            product_type=ProductType.NRML,
            expiry=date(2026, 1, 1),
            strike=Decimal("22150.0"),
        )

        # BANKNIFTY option is not Nifty-grid validated
        Leg(
            instrument_key="BANKNIFTY_CE",
            display_name="BANKNIFTY 22150 CE",
            asset_type=AssetType.CE,
            direction=Direction.BUY,
            quantity=75,
            entry_price=Decimal("100.00"),
            entry_date=date(2026, 4, 1),
            product_type=ProductType.NRML,
            expiry=date(2026, 1, 1),
            strike=Decimal("22150.0"),
        )

        # FINNIFTY option is not Nifty-grid validated
        Leg(
            instrument_key="FINNIFTY_CE",
            display_name="FINNIFTY 22150 CE",
            asset_type=AssetType.CE,
            direction=Direction.BUY,
            quantity=75,
            entry_price=Decimal("100.00"),
            entry_date=date(2026, 4, 1),
            product_type=ProductType.NRML,
            expiry=date(2026, 1, 1),
            strike=Decimal("22150.0"),
        )

        # Nifty key but generic name triggers validation
        with pytest.raises(
            ValidationError,
            match=r"Nifty strike 22150\.0 must be a multiple of 100",
        ):
            Leg(
                instrument_key="NIFTY_CE_TEST",
                display_name="CE 22150",
                asset_type=AssetType.CE,
                direction=Direction.BUY,
                quantity=75,
                entry_price=Decimal("100.00"),
                entry_date=date(2026, 4, 1),
                product_type=ProductType.NRML,
                expiry=date(2026, 1, 1),
                strike=Decimal("22150.0"),
            )

    def test_expiry_trading_day_validation(self):
        # Saturday is not a trading day
        with pytest.raises(
            ValidationError, match="is not a valid trading day"
        ):
            Leg(
                instrument_key="FUT_TEST",
                display_name="Futures Test",
                asset_type=AssetType.FUTURES,
                direction=Direction.BUY,
                quantity=75,
                entry_price=Decimal("22000.00"),
                entry_date=date(2026, 4, 1),
                product_type=ProductType.NRML,
                expiry=date(2026, 1, 3),  # Jan 3, 2026 is Saturday
            )

    def test_expiry_thursday_logic(self):
        # Jan 1, 2026 is a Thursday (trading day)
        # Jan 2, 2026 is a Friday (trading day). Expiry on Friday should fail.
        with pytest.raises(
            ValidationError, match="cannot be after Thursday of its week"
        ):
            Leg(
                instrument_key="FUT_TEST",
                display_name="Futures Test",
                asset_type=AssetType.FUTURES,
                direction=Direction.BUY,
                quantity=75,
                entry_price=Decimal("22000.00"),
                entry_date=date(2026, 4, 1),
                product_type=ProductType.NRML,
                expiry=date(2026, 1, 2),
            )

        # Wednesday Dec 31, 2025: nominal Thursday is Jan 1, 2026 which
        # is a trading day. So Dec 31, 2025 is not a valid expiry.
        with pytest.raises(
            ValidationError,
            match=(
                "must be Thursday or the preceding trading day if Thursday "
                "is a holiday"
            ),
        ):
            Leg(
                instrument_key="FUT_TEST",
                display_name="Futures Test",
                asset_type=AssetType.FUTURES,
                direction=Direction.BUY,
                quantity=75,
                entry_price=Decimal("22000.00"),
                entry_date=date(2026, 4, 1),
                product_type=ProductType.NRML,
                expiry=date(2025, 12, 31),
            )

        # Thursday April 2, 2026 is a holiday (Shri Ram Navami).
        # Wednesday April 1, 2026 is a valid expiry (preceding trading day).
        Leg(
            instrument_key="FUT_TEST",
            display_name="Futures Test",
            asset_type=AssetType.FUTURES,
            direction=Direction.BUY,
            quantity=75,
            entry_price=Decimal("22000.00"),
            entry_date=date(2026, 4, 1),
            product_type=ProductType.NRML,
            expiry=date(2026, 4, 1),
        )

        # Tuesday March 31, 2026: nominal Thursday is April 2, 2026 (holiday),
        # but Wednesday April 1, 2026 is a trading day, so Tuesday cannot
        # be the expiry.
        with pytest.raises(
            ValidationError,
            match="is a trading day after .* in the same week",
        ):
            Leg(
                instrument_key="FUT_TEST",
                display_name="Futures Test",
                asset_type=AssetType.FUTURES,
                direction=Direction.BUY,
                quantity=75,
                entry_price=Decimal("22000.00"),
                entry_date=date(2026, 4, 1),
                product_type=ProductType.NRML,
                expiry=date(2026, 3, 31),
            )

    def test_pre_2019_expiry_logic(self):
        # Prior to June 27, 2019, option expiries must be monthly.
        # May 31, 2018 is last Thursday of May 2018 (valid monthly expiry)
        Leg(
            instrument_key="PE_TEST",
            display_name="PE Test",
            asset_type=AssetType.PE,
            direction=Direction.BUY,
            quantity=75,
            entry_price=Decimal("100.00"),
            entry_date=date(2018, 4, 1),
            product_type=ProductType.NRML,
            expiry=date(2018, 5, 31),
            strike=Decimal("20000"),
        )

        # May 24, 2018 is Thursday, but not monthly expiry. Should fail.
        with pytest.raises(
            ValidationError,
            match="Prior to June 27, 2019, option",
        ):
            Leg(
                instrument_key="PE_TEST",
                display_name="PE Test",
                asset_type=AssetType.PE,
                direction=Direction.BUY,
                quantity=75,
                entry_price=Decimal("100.00"),
                entry_date=date(2018, 4, 1),
                product_type=ProductType.NRML,
                expiry=date(2018, 5, 24),
                strike=Decimal("20000"),
            )

    def test_expiry_whitelist(self):
        # Whitelist expiries date(2026, 4, 7) and date(2026, 12, 29)
        # are allowed even though they are Tuesdays
        Leg(
            instrument_key="PE_TEST",
            display_name="PE Test",
            asset_type=AssetType.PE,
            direction=Direction.BUY,
            quantity=75,
            entry_price=Decimal("100.00"),
            entry_date=date(2026, 4, 1),
            product_type=ProductType.NRML,
            expiry=date(2026, 4, 7),
            strike=Decimal("20000"),
        )
        Leg(
            instrument_key="PE_TEST",
            display_name="PE Test",
            asset_type=AssetType.PE,
            direction=Direction.BUY,
            quantity=75,
            entry_price=Decimal("100.00"),
            entry_date=date(2026, 4, 1),
            product_type=ProductType.NRML,
            expiry=date(2026, 12, 29),
            strike=Decimal("20000"),
        )


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


class TestPolymorphicStrategy:
    def test_create_strategy_instance_factory(self):
        s1 = create_strategy_instance(1, "FinRakshak", "Protective Put", [], None)
        assert isinstance(s1, HedgeStrategy)
        assert s1.name == "FinRakshak"

        s2 = create_strategy_instance(2, "finrakshak", "Protective Put", [], None)
        assert isinstance(s2, HedgeStrategy)

        s3 = create_strategy_instance(3, "finideas_ilts", "ILTS", [], None)
        assert isinstance(s3, Strategy)
        assert not isinstance(s3, HedgeStrategy)

        # Verify OCP dynamic registry capability
        class CustomTestStrategy(Strategy):
            pass

        register_strategy_type("custom_test", CustomTestStrategy)
        s_custom = create_strategy_instance(4, "custom_test", "Custom strategy description", [], None)
        assert isinstance(s_custom, CustomTestStrategy)
        assert s_custom.name == "custom_test"

    def test_get_protection_delta_polymorphism(self):
        strat = Strategy(name="some_strategy", legs=[])
        assert strat.get_protection_delta(Decimal("1000"), Decimal("800")) is None

        hedge_strat = HedgeStrategy(name="finrakshak", legs=[])
        delta = hedge_strat.get_protection_delta(Decimal("1000"), Decimal("800"))
        assert delta == Decimal("200")


# ── Store tests ──────────────────────────────────────────────────


class TestPortfolioStore:
    def test_get_strategy_returns_subclass(self, tmp_store):
        s = Strategy(name="finrakshak", legs=[_make_leg(Direction.BUY, 962.15, 65)])
        tmp_store.upsert_strategy(s)

        loaded = tmp_store.get_strategy("finrakshak")
        assert loaded is not None
        assert isinstance(loaded, HedgeStrategy)
        assert loaded.name == "finrakshak"

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

    def test_record_and_get_heartbeat(self, tmp_store):
        """Happy path: record a heartbeat and verify we can retrieve it."""
        assert tmp_store.get_latest_heartbeat("daily_snapshot") is None

        tmp_store.record_heartbeat("daily_snapshot", "SUCCESS", "Finished successfully")
        hb = tmp_store.get_latest_heartbeat("daily_snapshot")
        assert hb is not None
        assert hb["service"] == "daily_snapshot"
        assert hb["status"] == "SUCCESS"
        assert hb["message"] == "Finished successfully"
        assert hb["last_run"] is not None
        assert "+00:00" in hb["last_run"]

    def test_record_heartbeat_overwrite(self, tmp_store):
        """Verify record_heartbeat overwrites the previous state for the same service."""
        tmp_store.record_heartbeat("daily_snapshot", "SUCCESS", "All good")
        tmp_store.record_heartbeat("daily_snapshot", "FAILED", "Something went wrong")

        hb = tmp_store.get_latest_heartbeat("daily_snapshot")
        assert hb is not None
        assert hb["status"] == "FAILED"
        assert hb["message"] == "Something went wrong"


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
                    expiry=date(2026, 12, 29), strike=Decimal("840"),
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
                    expiry=date(2026, 12, 29),
                    strike=Decimal("500"),
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


# ── SnapshotService tests ──────────────────────────────────────────


class TestSnapshotService:
    def test_persist_snapshots_happy_path(self, tmp_store):
        """Happy path: persist snapshots for a strategy with legs."""
        s = Strategy(
            name="service_happy_test",
            legs=[
                Leg(
                    instrument_key="M1", display_name="M1", asset_type=AssetType.EQUITY,
                    direction=Direction.BUY, quantity=10, entry_price=Decimal("100.00"),
                    entry_date=date(2026, 4, 1), product_type=ProductType.CNC,
                ),
            ],
        )
        tmp_store.upsert_strategy(s)
        strategy = tmp_store.get_strategy("service_happy_test")

        service = SnapshotService(tmp_store)
        prices = {"M1": 105.0}
        greeks_map = {}

        count = service.persist_snapshots(
            strategy_name="service_happy_test",
            strategy=strategy,
            snap_date=date(2026, 4, 2),
            prices=prices,
            greeks_map=greeks_map,
            underlying_price=23500.5,
        )

        assert count == 1
        leg_id = strategy.legs[0].id
        snaps = tmp_store.get_snapshots(leg_id)
        assert len(snaps) == 1
        assert snaps[0].ltp == Decimal("105.0")
        assert snaps[0].underlying_price == Decimal("23500.5")

    def test_persist_snapshots_with_greeks(self, tmp_store):
        """Verify that all greeks (including theta) are persisted correctly."""
        s = Strategy(
            name="service_greeks_test",
            legs=[
                Leg(
                    instrument_key="OPT1", display_name="OPT1", asset_type=AssetType.PE,
                    direction=Direction.SELL, quantity=75, entry_price=Decimal("150.00"),
                    entry_date=date(2026, 4, 1), product_type=ProductType.NRML,
                    expiry=date(2026, 12, 29), strike=Decimal("150"),
                ),
            ],
        )
        tmp_store.upsert_strategy(s)
        strategy = tmp_store.get_strategy("service_greeks_test")

        service = SnapshotService(tmp_store)
        prices = {"OPT1": 120.0}
        greeks_map = {
            "OPT1": {
                "iv": 0.185,
                "delta": -0.22,
                "gamma": 0.0015,
                "theta": -4.25,
                "vega": 0.08,
                "oi": 150000,
                "volume": 25000,
            }
        }

        count = service.persist_snapshots(
            strategy_name="service_greeks_test",
            strategy=strategy,
            snap_date=date(2026, 4, 2),
            prices=prices,
            greeks_map=greeks_map,
        )

        assert count == 1
        leg_id = strategy.legs[0].id
        snaps = tmp_store.get_snapshots(leg_id)
        assert len(snaps) == 1
        snap = snaps[0]
        assert snap.ltp == Decimal("120.0")
        assert snap.iv == 0.185
        assert snap.delta == -0.22
        assert snap.gamma == 0.0015
        assert snap.theta == -4.25
        assert snap.vega == 0.08
        assert snap.oi == 150000
        assert snap.volume == 25000

    def test_persist_snapshots_trade_only_leg_auto_persisted(self, tmp_store):
        """Trade-only leg (where id is None) must be auto-persisted before recording daily snapshot."""
        s = Strategy(
            name="service_trade_only_test",
            legs=[
                # Leg without id (id is None) - mimics LIQUIDBEES from overlay
                Leg(
                    instrument_key="LIQUIDBEES", display_name="LIQUIDBEES",
                    asset_type=AssetType.EQUITY, direction=Direction.BUY,
                    quantity=5, entry_price=Decimal("1000.00"),
                    entry_date=date(2026, 4, 1), product_type=ProductType.CNC,
                ),
            ],
        )
        # Note: We do NOT call upsert_strategy, so the leg has no ID in the DB.
        # However, the strategy itself must exist in strategies table.
        tmp_store.upsert_strategy(Strategy(name="service_trade_only_test"))

        service = SnapshotService(tmp_store)
        prices = {"LIQUIDBEES": 1001.0}
        greeks_map = {}

        count = service.persist_snapshots(
            strategy_name="service_trade_only_test",
            strategy=s,
            snap_date=date(2026, 4, 2),
            prices=prices,
            greeks_map=greeks_map,
        )

        assert count == 1
        # The leg should now be auto-persisted, let's verify we can load the strategy and see it
        loaded = tmp_store.get_strategy("service_trade_only_test")
        assert len(loaded.legs) == 1
        leg = loaded.legs[0]
        assert leg.instrument_key == "LIQUIDBEES"
        assert leg.id is not None

        # Verify snapshot was written
        snaps = tmp_store.get_snapshots(leg.id)
        assert len(snaps) == 1
        assert snaps[0].ltp == Decimal("1001.0")

    def test_persist_snapshots_empty_strategy_legs(self, tmp_store):
        """If strategy has no legs, zero snapshots should be recorded."""
        s = Strategy(name="service_empty_test", legs=[])
        tmp_store.upsert_strategy(s)

        service = SnapshotService(tmp_store)
        count = service.persist_snapshots(
            strategy_name="service_empty_test",
            strategy=s,
            snap_date=date(2026, 4, 2),
            prices={},
            greeks_map={},
        )
        assert count == 0

    def test_tracker_uses_injected_snapshot_service(self, tmp_store):
        """PortfolioTracker.record_daily_snapshot should delegate persistence to SnapshotService."""
        from unittest.mock import MagicMock
        s = Strategy(
            name="tracker_delegate_test",
            legs=[
                Leg(
                    instrument_key="Z", display_name="Z", asset_type=AssetType.EQUITY,
                    direction=Direction.BUY, quantity=10, entry_price=100.0,
                    entry_date=date(2026, 4, 1), product_type=ProductType.CNC,
                ),
            ],
        )
        tmp_store.upsert_strategy(s)

        market = FakeMarket({"Z": 105.0})
        mock_service = MagicMock(spec=SnapshotService)
        mock_service.persist_snapshots.return_value = 42

        tracker = PortfolioTracker(tmp_store, market, snapshot_service=mock_service)

        count, pnl = asyncio.run(
            tracker.record_daily_snapshot("tracker_delegate_test", date(2026, 4, 2))
        )

        assert count == 42
        assert mock_service.persist_snapshots.called
        # Verify it was called with correct arguments
        args, kwargs = mock_service.persist_snapshots.call_args
        assert kwargs["strategy_name"] == "tracker_delegate_test"
        assert kwargs["snap_date"] == date(2026, 4, 2)
        assert kwargs["prices"] == {"Z": 105.0}

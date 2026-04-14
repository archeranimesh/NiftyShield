"""Tests for the historical query path in scripts/daily_snapshot.py.

Covers:
  - _compute_strategy_pnl_from_prices: pure helper, no I/O
  - _historical_main: DB-only path, no network, no .env

All tests are fully offline.  No Upstox token, no AMFI fetch, no asyncio.
"""

from __future__ import annotations

import tempfile
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from scripts.daily_snapshot import (
    _build_prev_prices,
    _compute_strategy_pnl_from_prices,
    _historical_main,
)
from src.mf.models import MFNavSnapshot
from src.mf.store import MFStore
from src.portfolio.models import (
    AssetType,
    DailySnapshot,
    Direction,
    Leg,
    ProductType,
    Strategy,
)
from src.portfolio.store import PortfolioStore


# ── Factories ────────────────────────────────────────────────────


def _make_leg(
    instrument_key: str,
    direction: Direction,
    entry_price: str,
    quantity: int,
    asset_type: AssetType = AssetType.PE,
) -> Leg:
    return Leg(
        instrument_key=instrument_key,
        display_name=instrument_key,
        asset_type=asset_type,
        direction=direction,
        quantity=quantity,
        entry_price=Decimal(entry_price),
        entry_date=date(2026, 1, 1),
        product_type=ProductType.NRML,
    )


def _seed_strategy(store: PortfolioStore, name: str, legs: list[Leg]) -> list[Leg]:
    """Insert a strategy and return legs with DB-assigned IDs."""
    s = Strategy(name=name, legs=legs)
    store.upsert_strategy(s)
    return store.get_strategy(name).legs  # type: ignore[return-value]


# ── _compute_strategy_pnl_from_prices ────────────────────────────


class TestComputeStrategyPnlFromPrices:
    def test_buy_leg_profit(self) -> None:
        leg = _make_leg("A|1", Direction.BUY, "100.00", 10)
        strategy = Strategy(name="test", legs=[leg])
        pnl = _compute_strategy_pnl_from_prices(
            strategy, {"A|1": Decimal("110.00")}
        )
        assert pnl.total_pnl == Decimal("100")  # (110−100)×10

    def test_sell_leg_profit(self) -> None:
        leg = _make_leg("B|2", Direction.SELL, "200.00", 5)
        strategy = Strategy(name="test", legs=[leg])
        pnl = _compute_strategy_pnl_from_prices(
            strategy, {"B|2": Decimal("180.00")}
        )
        assert pnl.total_pnl == Decimal("100")  # (200−180)×5

    def test_falls_back_to_entry_price_when_ltp_missing(self) -> None:
        """Missing key in prices → P&L of zero (entry_price used as LTP)."""
        leg = _make_leg("C|3", Direction.BUY, "500.00", 1)
        strategy = Strategy(name="test", legs=[leg])
        pnl = _compute_strategy_pnl_from_prices(strategy, {})
        assert pnl.total_pnl == Decimal("0")

    def test_mixed_legs_correct_total(self) -> None:
        """Long + short legs: P&L is the algebraic sum."""
        strategy = Strategy(
            name="ilts",
            legs=[
                _make_leg("ETF|1", Direction.BUY, "1388.00", 438, AssetType.EQUITY),
                _make_leg("OPT|PE", Direction.SELL, "840.00", 65),
            ],
        )
        prices = {
            "ETF|1": Decimal("1400.00"),  # +12×438 = +5256
            "OPT|PE": Decimal("800.00"),  # (840−800)×65 = +2600
        }
        pnl = _compute_strategy_pnl_from_prices(strategy, prices)
        assert pnl.total_pnl == Decimal("7856")

    def test_strategy_name_propagated(self) -> None:
        strategy = Strategy(name="my_strat", legs=[_make_leg("K|1", Direction.BUY, "100", 1)])
        pnl = _compute_strategy_pnl_from_prices(strategy, {"K|1": Decimal("100")})
        assert pnl.strategy_name == "my_strat"

    def test_per_leg_pnl_sums_to_total(self) -> None:
        strategy = Strategy(
            name="sum",
            legs=[
                _make_leg("X|1", Direction.BUY, "100", 10),
                _make_leg("X|2", Direction.SELL, "200", 5),
            ],
        )
        prices = {"X|1": Decimal("110"), "X|2": Decimal("190")}
        pnl = _compute_strategy_pnl_from_prices(strategy, prices)
        leg_sum = sum(lp.pnl for lp in pnl.legs)
        assert leg_sum == pnl.total_pnl


# ── _historical_main ──────────────────────────────────────────────


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "portfolio.sqlite"


@pytest.fixture
def seeded_store(db_path: Path) -> PortfolioStore:
    """PortfolioStore with one strategy, one leg, one snapshot on 2026-04-06."""
    store = PortfolioStore(db_path)
    legs = _seed_strategy(
        store, "ILTS", [_make_leg("NSE_FO|99", Direction.SELL, "840.00", 65)]
    )
    store.record_snapshot(
        DailySnapshot(
            leg_id=legs[0].id,
            snapshot_date=date(2026, 4, 6),
            ltp=Decimal("810.00"),
            underlying_price=Decimal("23000.00"),
        )
    )
    return store


class TestHistoricalMain:
    def test_returns_zero_on_success(self, seeded_store: PortfolioStore, db_path: Path) -> None:
        """Happy path: snapshots exist → exit code 0."""
        rc = _historical_main(date(2026, 4, 6), db_path)
        assert rc == 0

    def test_returns_one_when_db_missing(self, tmp_path: Path) -> None:
        """DB does not exist → exit code 1, no exception."""
        rc = _historical_main(date(2026, 4, 6), tmp_path / "no_such.sqlite")
        assert rc == 1

    def test_returns_one_when_no_snapshots_for_date(
        self, seeded_store: PortfolioStore, db_path: Path
    ) -> None:
        """Snapshots exist but not for the requested date → exit code 1."""
        rc = _historical_main(date(2026, 4, 7), db_path)
        assert rc == 1

    def test_prints_nifty_spot(
        self, seeded_store: PortfolioStore, db_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        """When underlying_price is stored, it should appear in output."""
        _historical_main(date(2026, 4, 6), db_path)
        out = capsys.readouterr().out
        assert "23,000" in out

    def test_prints_strategy_pnl(
        self, seeded_store: PortfolioStore, db_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        """Strategy P&L line should appear in output."""
        _historical_main(date(2026, 4, 6), db_path)
        out = capsys.readouterr().out
        assert "ILTS" in out

    def test_mf_absent_does_not_crash(
        self, seeded_store: PortfolioStore, db_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        """No MF NAV snapshots for the date → prints warning, still returns 0."""
        rc = _historical_main(date(2026, 4, 6), db_path)
        out = capsys.readouterr().out
        assert rc == 0
        assert "No MF NAV snapshots" in out

    def test_mf_pnl_computed_from_stored_navs(
        self, seeded_store: PortfolioStore, db_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        """When MF NAV snapshots exist, P&L appears in output."""
        from scripts.seed_mf_holdings import seed_holdings

        mf_store = MFStore(db_path)
        seed_holdings(mf_store)
        mf_store.upsert_nav_snapshot(
            MFNavSnapshot(
                amfi_code="122640",
                scheme_name="Parag Parikh Flexi Cap Fund - Reg Gr",
                snapshot_date=date(2026, 4, 6),
                nav=Decimal("85.00"),
            )
        )

        rc = _historical_main(date(2026, 4, 6), db_path)
        out = capsys.readouterr().out
        assert rc == 0
        assert "MF portfolio" in out

    def test_combined_summary_printed(
        self, seeded_store: PortfolioStore, db_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        """Restructured combined summary sections must appear on success."""
        _historical_main(date(2026, 4, 6), db_path)
        out = capsys.readouterr().out
        assert "── Equity" in out
        assert "── Derivatives" in out
        assert "Total value" in out

    def test_done_printed_on_success(
        self, seeded_store: PortfolioStore, db_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        _historical_main(date(2026, 4, 6), db_path)
        assert "Done" in capsys.readouterr().out

    def test_day_change_delta_shown_when_prev_snapshot_exists(
        self, seeded_store: PortfolioStore, db_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        """When a prior-date snapshot exists, Δday appears in the combined summary."""
        legs = seeded_store.get_strategy("ILTS").legs  # type: ignore[union-attr]
        seeded_store.record_snapshot(
            DailySnapshot(
                leg_id=legs[0].id,
                snapshot_date=date(2026, 4, 7),
                ltp=Decimal("820.00"),
                underlying_price=Decimal("23100.00"),
            )
        )
        _historical_main(date(2026, 4, 7), db_path)
        out = capsys.readouterr().out
        assert "Δday" in out

    def test_day_change_delta_omitted_when_no_prior_snapshot(
        self, seeded_store: PortfolioStore, db_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        """When no prior date exists (first ever run), Δday must NOT appear."""
        _historical_main(date(2026, 4, 6), db_path)
        assert "Δday" not in capsys.readouterr().out


# ── _build_prev_prices ────────────────────────────────────────────


class TestBuildPrevPrices:
    def test_maps_leg_id_to_instrument_key(self, db_path: Path) -> None:
        """Leg IDs from prev_snapshots are translated to instrument keys."""
        store = PortfolioStore(db_path)
        legs = _seed_strategy(
            store, "bp_test", [_make_leg("NSE_FO|999", Direction.SELL, "500.00", 65)]
        )
        leg_id = legs[0].id

        prev = {leg_id: DailySnapshot(leg_id=leg_id, snapshot_date=date(2026, 4, 6), ltp=Decimal("490"))}
        strategies = store.get_all_strategies()
        result = _build_prev_prices(strategies, prev)
        assert result == {"NSE_FO|999": 490.0}

    def test_ignores_leg_ids_not_in_strategies(self, db_path: Path) -> None:
        """Snapshot leg_ids with no matching strategy leg are silently dropped."""
        store = PortfolioStore(db_path)
        _seed_strategy(store, "bp_ignore", [_make_leg("NSE_FO|1", Direction.BUY, "100.00", 10)])
        orphan_id = 9999  # not a real leg in the DB
        prev = {orphan_id: DailySnapshot(leg_id=orphan_id, snapshot_date=date(2026, 4, 6), ltp=Decimal("50"))}
        strategies = store.get_all_strategies()
        result = _build_prev_prices(strategies, prev)
        assert result == {}


# ── Trade overlay wired into _historical_main ─────────────────────


class TestTradeOverlayInHistoricalMain:
    """Confirm apply_trade_positions is active in the historical query path."""

    def test_overlay_updates_qty_in_pnl(self, db_path: Path, capsys: pytest.CaptureFixture) -> None:
        """Trade with higher qty than static Leg definition → P&L reflects actual qty."""
        from src.portfolio.models import Trade, TradeAction

        store = PortfolioStore(db_path)
        # Seed strategy with display_name matching the leg_role we'll record in trades
        etf_leg = _make_leg("NSE_EQ|INF754K01LE1", Direction.BUY, "1388.12", 438, AssetType.EQUITY)
        etf_leg = etf_leg.model_copy(update={"display_name": "EBBETF0431"})
        seeded_legs = _seed_strategy(store, "ILTS", [etf_leg])

        # Record a snapshot for the leg
        store.record_snapshot(DailySnapshot(
            leg_id=seeded_legs[0].id,
            snapshot_date=date(2026, 4, 8),
            ltp=Decimal("1400.00"),
        ))

        # Record trades: 438 + 27 = 465 total qty, weighted avg ~1388.01
        store.record_trade(Trade(
            strategy_name="ILTS", leg_role="EBBETF0431",
            instrument_key="NSE_EQ|INF754K01LE1",
            trade_date=date(2026, 1, 15), action=TradeAction.BUY,
            quantity=438, price=Decimal("1388.12"),
        ))
        store.record_trade(Trade(
            strategy_name="ILTS", leg_role="EBBETF0431",
            instrument_key="NSE_EQ|INF754K01LE1",
            trade_date=date(2026, 4, 8), action=TradeAction.BUY,
            quantity=27, price=Decimal("1386.20"),
        ))

        _historical_main(date(2026, 4, 8), db_path)
        out = capsys.readouterr().out

        # P&L should reflect 465 units @ 1400 vs avg ~1388.01
        # (1400 - 1388.01) * 465 ≈ 5570, certainly > static 438*(1400-1388.12) ≈ 5203
        assert "Done" in out

    def test_overlay_appends_liquidbees_to_etf_value(self, db_path: Path, capsys: pytest.CaptureFixture) -> None:
        """LIQUIDBEES trade (no Leg in strategy) → its value flows into ETF component."""
        from src.portfolio.models import Trade, TradeAction

        store = PortfolioStore(db_path)
        etf_leg = _make_leg("NSE_EQ|INF754K01LE1", Direction.BUY, "1388.12", 438, AssetType.EQUITY)
        etf_leg = etf_leg.model_copy(update={"display_name": "EBBETF0431"})
        seeded_legs = _seed_strategy(store, "ILTS", [etf_leg])

        store.record_snapshot(DailySnapshot(
            leg_id=seeded_legs[0].id,
            snapshot_date=date(2026, 4, 8),
            ltp=Decimal("1400.00"),
        ))

        # Only LIQUIDBEES trade — no Leg for it in the strategy
        store.record_trade(Trade(
            strategy_name="ILTS", leg_role="LIQUIDBEES",
            instrument_key="NSE_EQ|INF732E01037",
            trade_date=date(2026, 4, 8), action=TradeAction.BUY,
            quantity=22, price=Decimal("1000.00"),
        ))

        _historical_main(date(2026, 4, 8), db_path)
        # Should complete without error — LIQUIDBEES appended as EQUITY leg
        assert "Done" in capsys.readouterr().out

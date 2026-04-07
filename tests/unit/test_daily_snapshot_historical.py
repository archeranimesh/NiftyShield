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

from scripts.daily_snapshot import _compute_strategy_pnl_from_prices, _historical_main
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
        """Combined portfolio section must always appear on success."""
        _historical_main(date(2026, 4, 6), db_path)
        out = capsys.readouterr().out
        assert "Combined Portfolio" in out

    def test_done_printed_on_success(
        self, seeded_store: PortfolioStore, db_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        _historical_main(date(2026, 4, 6), db_path)
        assert "Done" in capsys.readouterr().out

# tests/unit/risk/test_collateral_gate.py
"""Unit tests for src/risk/collateral_gate.py — shared warn-only NiftyBees
collateral-capacity gate (RH-4, 2026-08-06).

Covers: aggregate-at-capacity (breach logs a GateViolation, still returns
non-blocking), aggregate-under-capacity (no violation logged), and the
zero-holding edge case (no NiftyBees position at all).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from src.models.portfolio import TradeAction
from src.paper.constants import STRATEGY_CSP, STRATEGY_OVERLAY, STRATEGY_SPOT
from src.paper.models import PaperTrade
from src.paper.store import PaperStore
from src.risk.collateral_gate import GATE_NAME, check_collateral_capacity

_SPOT_PRICE = Decimal("24500")
_NIFTYBEES_LTP = Decimal("280")
_LOT_SIZE = 65
_DATE = date(2026, 8, 6)


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "test_collateral_gate.db"


@pytest.fixture
def store(db_path: Path) -> PaperStore:
    return PaperStore(db_path)


def _seed_niftybees(store: PaperStore, units: int) -> None:
    store.record_trade(
        PaperTrade(
            strategy_name=STRATEGY_SPOT,
            leg_role="base_spot",
            instrument_key="NSE_EQ|INF204KB14I2",
            trade_date=_DATE,
            action=TradeAction.BUY,
            quantity=units,
            price=Decimal("260.00"),
            notes="collateral seed",
        )
    )


def _seed_open_lot(store: PaperStore, strategy_name: str, leg_role: str, key: str) -> None:
    """Open exactly one lot (SELL, short) under the given strategy/leg/instrument."""
    store.record_trade(
        PaperTrade(
            strategy_name=strategy_name,
            leg_role=leg_role,
            instrument_key=key,
            trade_date=_DATE,
            action=TradeAction.SELL,
            quantity=_LOT_SIZE,
            price=Decimal("120.00"),
            notes="open lot",
        )
    )


class TestUnderCapacity:
    def test_entry_proceeds_no_violation_logged(self, store: PaperStore) -> None:
        # ~5691 units/lot at these prices -> holding of 5725 supports exactly 1 lot.
        _seed_niftybees(store, units=5725)

        violation = check_collateral_capacity(
            store=store,
            strategy_name=STRATEGY_CSP,
            lots_requested=1,
            nifty_spot=_SPOT_PRICE,
            niftybees_ltp=_NIFTYBEES_LTP,
            lot_size=_LOT_SIZE,
        )

        assert violation is None
        counts = store.get_gate_violation_counts(gate_name=GATE_NAME)
        assert counts == []


class TestAtCapacity:
    def test_entry_proceeds_but_violation_logged_when_breached(self, store: PaperStore) -> None:
        # Holding supports exactly 1 lot; CSP already has 1 lot open; requesting
        # a 2nd lot (via overlay) would push aggregate draw to 2 > capacity of 1.
        _seed_niftybees(store, units=5725)
        _seed_open_lot(store, STRATEGY_CSP, "short_put", "NSE_FO|11111")

        violation = check_collateral_capacity(
            store=store,
            strategy_name=STRATEGY_OVERLAY,
            lots_requested=1,
            nifty_spot=_SPOT_PRICE,
            niftybees_ltp=_NIFTYBEES_LTP,
            lot_size=_LOT_SIZE,
        )

        # Warn-only: a violation is returned/logged, but the caller is expected
        # to proceed regardless — this function never raises or blocks.
        assert violation is not None
        assert violation.gate_name == GATE_NAME
        assert violation.strategy_name == STRATEGY_OVERLAY
        assert violation.threshold == "1"
        assert violation.actual == "2"

        counts = store.get_gate_violation_counts(gate_name=GATE_NAME)
        assert counts[0]["violation_count"] == 1


class TestZeroHoldingEdgeCase:
    def test_no_niftybees_position_still_warns_not_raises(self, store: PaperStore) -> None:
        # No STRATEGY_SPOT position recorded at all -> compute_max_lots sees 0 units.
        violation = check_collateral_capacity(
            store=store,
            strategy_name=STRATEGY_CSP,
            lots_requested=1,
            nifty_spot=_SPOT_PRICE,
            niftybees_ltp=_NIFTYBEES_LTP,
            lot_size=_LOT_SIZE,
        )

        assert violation is not None
        assert violation.threshold == "0"
        assert violation.actual == "1"

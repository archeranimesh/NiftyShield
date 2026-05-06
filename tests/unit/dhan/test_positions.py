"""Tests for src/dhan/positions.py and the option-related models in src/dhan/models.py.

Phase A: model construction, field types, Decimal precision, frozen enforcement.
Phase B: parser functions, filter, build_options_summary, parse_fund_limit, formatter.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from src.dhan.models import DhanFundLimit, DhanOptionPosition, DhanOptionsSummary


# ── Helpers ──────────────────────────────────────────────────────────────────

_TS = datetime(2026, 5, 6, 10, 0, 0, tzinfo=timezone.utc)


def _make_option_position(**overrides) -> DhanOptionPosition:
    """Factory for DhanOptionPosition with sensible defaults."""
    defaults: dict = {
        "security_id": "41234",
        "trading_symbol": "NIFTY2550523500CE",
        "exchange_segment": "NSE_FNO",
        "product_type": "INTRADAY",
        "position_type": "SHORT",
        "buy_qty": 0,
        "sell_qty": 50,
        "net_qty": -50,
        "buy_avg": Decimal("0.00"),
        "sell_avg": Decimal("120.50"),
        "realized_pnl": Decimal("0.00"),
        "unrealized_pnl": Decimal("1250.00"),
    }
    defaults.update(overrides)
    return DhanOptionPosition(**defaults)


def _make_options_summary(**overrides) -> DhanOptionsSummary:
    """Factory for DhanOptionsSummary with sensible defaults."""
    defaults: dict = {
        "realized_pnl": Decimal("3000.00"),
        "unrealized_pnl": Decimal("0.00"),
        "total_pnl": Decimal("3000.00"),
        "position_count": 2,
        "snapshot_ts": _TS,
    }
    defaults.update(overrides)
    return DhanOptionsSummary(**defaults)


def _make_fund_limit(**overrides) -> DhanFundLimit:
    """Factory for DhanFundLimit with sensible defaults."""
    defaults: dict = {
        "available_balance": Decimal("150000.00"),
        "utilized_amount": Decimal("50000.00"),
        "collateral_amount": Decimal("200000.00"),
        "withdrawable_balance": Decimal("100000.00"),
        "snapshot_ts": _TS,
    }
    defaults.update(overrides)
    return DhanFundLimit(**defaults)


# ── DhanOptionPosition ────────────────────────────────────────────────────────


class TestDhanOptionPosition:
    def test_construction_happy(self) -> None:
        pos = _make_option_position()
        assert pos.security_id == "41234"
        assert pos.trading_symbol == "NIFTY2550523500CE"
        assert pos.exchange_segment == "NSE_FNO"
        assert pos.product_type == "INTRADAY"
        assert pos.position_type == "SHORT"
        assert pos.buy_qty == 0
        assert pos.sell_qty == 50
        assert pos.net_qty == -50
        assert pos.buy_avg == Decimal("0.00")
        assert pos.sell_avg == Decimal("120.50")
        assert pos.realized_pnl == Decimal("0.00")
        assert pos.unrealized_pnl == Decimal("1250.00")

    def test_monetary_fields_are_decimal(self) -> None:
        pos = _make_option_position()
        assert isinstance(pos.buy_avg, Decimal)
        assert isinstance(pos.sell_avg, Decimal)
        assert isinstance(pos.realized_pnl, Decimal)
        assert isinstance(pos.unrealized_pnl, Decimal)

    def test_decimal_precision_preserved(self) -> None:
        """Decimal(str(v)) from a Dhan float like 120.5 must not lose precision."""
        pos = _make_option_position(sell_avg=Decimal("120.55"))
        assert pos.sell_avg == Decimal("120.55")

    def test_frozen_raises_on_mutation(self) -> None:
        pos = _make_option_position()
        with pytest.raises((FrozenInstanceError, AttributeError)):
            pos.net_qty = 0  # type: ignore[misc]

    def test_net_qty_zero_means_fully_closed(self) -> None:
        """net_qty=0 is valid — represents a fully squared-off position."""
        pos = _make_option_position(buy_qty=50, sell_qty=50, net_qty=0)
        assert pos.net_qty == 0

    def test_long_position(self) -> None:
        pos = _make_option_position(
            position_type="LONG",
            buy_qty=50,
            sell_qty=0,
            net_qty=50,
            buy_avg=Decimal("95.00"),
            sell_avg=Decimal("0.00"),
        )
        assert pos.position_type == "LONG"
        assert pos.net_qty == 50


# ── DhanOptionsSummary ────────────────────────────────────────────────────────


class TestDhanOptionsSummary:
    def test_construction_happy(self) -> None:
        s = _make_options_summary()
        assert s.realized_pnl == Decimal("3000.00")
        assert s.unrealized_pnl == Decimal("0.00")
        assert s.total_pnl == Decimal("3000.00")
        assert s.position_count == 2
        assert s.snapshot_ts == _TS

    def test_monetary_fields_are_decimal(self) -> None:
        s = _make_options_summary()
        assert isinstance(s.realized_pnl, Decimal)
        assert isinstance(s.unrealized_pnl, Decimal)
        assert isinstance(s.total_pnl, Decimal)

    def test_snapshot_ts_is_datetime(self) -> None:
        s = _make_options_summary()
        assert isinstance(s.snapshot_ts, datetime)

    def test_frozen_raises_on_mutation(self) -> None:
        s = _make_options_summary()
        with pytest.raises((FrozenInstanceError, AttributeError)):
            s.position_count = 0  # type: ignore[misc]

    def test_zero_positions(self) -> None:
        s = _make_options_summary(
            realized_pnl=Decimal("0"),
            unrealized_pnl=Decimal("0"),
            total_pnl=Decimal("0"),
            position_count=0,
        )
        assert s.position_count == 0
        assert s.total_pnl == Decimal("0")

    def test_negative_pnl(self) -> None:
        """Losses are represented as negative Decimals."""
        s = _make_options_summary(
            realized_pnl=Decimal("-2500.00"),
            total_pnl=Decimal("-2500.00"),
        )
        assert s.realized_pnl < Decimal("0")


# ── DhanFundLimit ─────────────────────────────────────────────────────────────


class TestDhanFundLimit:
    def test_construction_happy(self) -> None:
        fl = _make_fund_limit()
        assert fl.available_balance == Decimal("150000.00")
        assert fl.utilized_amount == Decimal("50000.00")
        assert fl.collateral_amount == Decimal("200000.00")
        assert fl.withdrawable_balance == Decimal("100000.00")
        assert fl.snapshot_ts == _TS

    def test_monetary_fields_are_decimal(self) -> None:
        fl = _make_fund_limit()
        assert isinstance(fl.available_balance, Decimal)
        assert isinstance(fl.utilized_amount, Decimal)
        assert isinstance(fl.collateral_amount, Decimal)
        assert isinstance(fl.withdrawable_balance, Decimal)

    def test_frozen_raises_on_mutation(self) -> None:
        fl = _make_fund_limit()
        with pytest.raises((FrozenInstanceError, AttributeError)):
            fl.available_balance = Decimal("0")  # type: ignore[misc]

    def test_snapshot_ts_is_datetime(self) -> None:
        fl = _make_fund_limit()
        assert isinstance(fl.snapshot_ts, datetime)

    def test_zero_utilization(self) -> None:
        """Zero utilized_amount is valid (no open positions consuming margin)."""
        fl = _make_fund_limit(utilized_amount=Decimal("0"))
        assert fl.utilized_amount == Decimal("0")

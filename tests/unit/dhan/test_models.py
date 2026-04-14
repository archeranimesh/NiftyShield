"""Tests for src/dhan/models.py — DhanHolding and DhanPortfolioSummary."""

from datetime import date
from decimal import Decimal

import pytest

from src.dhan.models import DhanHolding, DhanPortfolioSummary


# ── Fixtures ─────────────────────────────────────────────────────


def _make_holding(**overrides) -> DhanHolding:
    """Factory for DhanHolding with sensible defaults."""
    defaults = {
        "trading_symbol": "NIFTYIETF",
        "isin": "INF109K012R6",
        "security_id": "13611",
        "exchange": "NSE_EQ",
        "total_qty": 500,
        "collateral_qty": 500,
        "avg_cost_price": Decimal("268.50"),
        "classification": "EQUITY",
        "ltp": Decimal("275.40"),
    }
    defaults.update(overrides)
    return DhanHolding(**defaults)


# ── DhanHolding property tests ───────────────────────────────────


class TestDhanHoldingProperties:

    def test_cost_basis(self):
        h = _make_holding()
        assert h.cost_basis == Decimal("268.50") * 500

    def test_current_value_with_ltp(self):
        h = _make_holding()
        assert h.current_value == Decimal("275.40") * 500

    def test_current_value_without_ltp(self):
        h = _make_holding(ltp=None)
        assert h.current_value is None

    def test_pnl_positive(self):
        h = _make_holding()
        expected = (Decimal("275.40") - Decimal("268.50")) * 500
        assert h.pnl == expected

    def test_pnl_negative(self):
        h = _make_holding(ltp=Decimal("260.00"))
        expected = (Decimal("260.00") - Decimal("268.50")) * 500
        assert h.pnl == expected
        assert h.pnl < 0

    def test_pnl_without_ltp(self):
        h = _make_holding(ltp=None)
        assert h.pnl is None

    def test_pnl_pct_positive(self):
        h = _make_holding()
        pct = h.pnl_pct
        assert pct is not None
        assert pct > 0
        # Verify it's quantized to 2 dp
        assert pct == pct.quantize(Decimal("0.01"))

    def test_pnl_pct_without_ltp(self):
        h = _make_holding(ltp=None)
        assert h.pnl_pct is None

    def test_pnl_pct_zero_cost_basis(self):
        h = _make_holding(avg_cost_price=Decimal("0"), ltp=Decimal("100"))
        assert h.pnl_pct == Decimal("0")

    def test_frozen(self):
        h = _make_holding()
        with pytest.raises(AttributeError):
            h.ltp = Decimal("999")  # type: ignore[misc]


# ── DhanHolding classification ───────────────────────────────────


class TestDhanHoldingClassification:

    def test_equity_classification(self):
        h = _make_holding(classification="EQUITY")
        assert h.classification == "EQUITY"

    def test_bond_classification(self):
        h = _make_holding(
            trading_symbol="LIQUIDCASE",
            isin="INF0R8F01034",
            classification="BOND",
        )
        assert h.classification == "BOND"


# ── DhanPortfolioSummary ─────────────────────────────────────────


class TestDhanPortfolioSummary:

    def test_empty_summary(self):
        s = DhanPortfolioSummary(
            snapshot_date=date(2026, 4, 14),
            equity_holdings=(),
            equity_value=Decimal("0"),
            equity_basis=Decimal("0"),
            equity_pnl=Decimal("0"),
            equity_pnl_pct=None,
            bond_holdings=(),
            bond_value=Decimal("0"),
            bond_basis=Decimal("0"),
            bond_pnl=Decimal("0"),
            bond_pnl_pct=None,
        )
        assert s.equity_day_delta is None
        assert s.bond_day_delta is None

    def test_summary_with_deltas(self):
        s = DhanPortfolioSummary(
            snapshot_date=date(2026, 4, 14),
            equity_holdings=(),
            equity_value=Decimal("137700"),
            equity_basis=Decimal("134250"),
            equity_pnl=Decimal("3450"),
            equity_pnl_pct=Decimal("2.57"),
            bond_holdings=(),
            bond_value=Decimal("201100"),
            bond_basis=Decimal("200650"),
            bond_pnl=Decimal("450"),
            bond_pnl_pct=Decimal("0.22"),
            equity_day_delta=Decimal("500"),
            bond_day_delta=Decimal("100"),
        )
        assert s.equity_day_delta == Decimal("500")
        assert s.bond_day_delta == Decimal("100")

    def test_frozen(self):
        s = DhanPortfolioSummary(
            snapshot_date=date(2026, 4, 14),
            equity_holdings=(),
            equity_value=Decimal("0"),
            equity_basis=Decimal("0"),
            equity_pnl=Decimal("0"),
            equity_pnl_pct=None,
            bond_holdings=(),
            bond_value=Decimal("0"),
            bond_basis=Decimal("0"),
            bond_pnl=Decimal("0"),
            bond_pnl_pct=None,
        )
        with pytest.raises(AttributeError):
            s.equity_value = Decimal("999")  # type: ignore[misc]

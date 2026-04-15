"""Tests for Nuvama fields on PortfolioSummary.

Verifies that the six new nuvama_* fields and nuvama_available flag:
  - default to zero / False (zero impact on existing callers)
  - accept Decimal values correctly
  - participate in frozen dataclass enforcement
"""

from datetime import date
from decimal import Decimal

import pytest

pytest.importorskip("pydantic", reason="pydantic required for PortfolioSummary")

from src.portfolio.models import PortfolioSummary  # noqa: E402


def _base_kwargs() -> dict:
    """Minimal kwargs for a valid PortfolioSummary (non-nuvama fields only)."""
    return dict(
        snapshot_date=date(2026, 4, 15),
        mf_value=Decimal("0"),
        mf_invested=Decimal("0"),
        mf_pnl=Decimal("0"),
        mf_pnl_pct=None,
        mf_available=False,
        etf_value=Decimal("0"),
        etf_basis=Decimal("0"),
        options_pnl=Decimal("0"),
        total_value=Decimal("0"),
        total_invested=Decimal("0"),
        total_pnl=Decimal("0"),
        total_pnl_pct=Decimal("0"),
    )


# ---------------------------------------------------------------------------
# Default values
# ---------------------------------------------------------------------------


def test_nuvama_bond_value_defaults_to_zero():
    s = PortfolioSummary(**_base_kwargs())
    assert s.nuvama_bond_value == Decimal("0")


def test_nuvama_bond_basis_defaults_to_zero():
    s = PortfolioSummary(**_base_kwargs())
    assert s.nuvama_bond_basis == Decimal("0")


def test_nuvama_bond_pnl_defaults_to_zero():
    s = PortfolioSummary(**_base_kwargs())
    assert s.nuvama_bond_pnl == Decimal("0")


def test_nuvama_bond_pnl_pct_defaults_to_none():
    s = PortfolioSummary(**_base_kwargs())
    assert s.nuvama_bond_pnl_pct is None


def test_nuvama_bond_day_delta_defaults_to_none():
    s = PortfolioSummary(**_base_kwargs())
    assert s.nuvama_bond_day_delta is None


def test_nuvama_available_defaults_to_false():
    s = PortfolioSummary(**_base_kwargs())
    assert s.nuvama_available is False


# ---------------------------------------------------------------------------
# Populated values round-trip correctly
# ---------------------------------------------------------------------------


def test_nuvama_fields_populated():
    s = PortfolioSummary(
        **_base_kwargs(),
        nuvama_bond_value=Decimal("3158740.00"),
        nuvama_bond_basis=Decimal("3629222.00"),
        nuvama_bond_pnl=Decimal("529518.00"),
        nuvama_bond_pnl_pct=Decimal("14.59"),
        nuvama_bond_day_delta=Decimal("-12345.67"),
        nuvama_available=True,
    )
    assert s.nuvama_bond_value == Decimal("3158740.00")
    assert s.nuvama_bond_basis == Decimal("3629222.00")
    assert s.nuvama_bond_pnl == Decimal("529518.00")
    assert s.nuvama_bond_pnl_pct == Decimal("14.59")
    assert s.nuvama_bond_day_delta == Decimal("-12345.67")
    assert s.nuvama_available is True


# ---------------------------------------------------------------------------
# Existing fields unaffected
# ---------------------------------------------------------------------------


def test_existing_dhan_fields_unaffected():
    """Adding nuvama fields must not change Dhan field defaults."""
    s = PortfolioSummary(**_base_kwargs())
    assert s.dhan_bond_value == Decimal("0")
    assert s.dhan_available is False


def test_existing_mf_fields_unaffected():
    s = PortfolioSummary(**_base_kwargs())
    assert s.mf_available is False
    assert s.mf_pnl == Decimal("0")

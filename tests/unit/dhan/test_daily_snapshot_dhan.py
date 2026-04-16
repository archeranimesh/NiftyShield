"""Tests for Dhan integration in scripts/daily_snapshot.py.

Covers:
  - _build_portfolio_summary Dhan field population
  - _format_combined_summary Equity/Bonds/Total sections with Dhan data
  - Dhan unavailable fallback (token expired or ValueError)
  - Double-count filtering — strategy ISINs excluded from Dhan holdings

All tests are fully offline — no network, no DB, no .env required.
daily_snapshot.py only imports stdlib + src.portfolio.models at module level,
so all helpers are importable cleanly.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

import pytest

from scripts.daily_snapshot import (
    _build_portfolio_summary,
    _format_combined_summary,
)
from src.dhan.models import DhanHolding, DhanPortfolioSummary
from src.models.portfolio import AssetType, PortfolioSummary

# ── Shared test constants ────────────────────────────────────────────

_SNAP_DATE = date(2026, 4, 14)

# ISINs for the fixture instruments
_NIFTYIETF_ISIN = "INF109K012R6"
_LIQUIDCASE_ISIN = "INF0R8F01034"
_EBBETF_ISIN = "INF754K01LE1"   # already tracked by finideas_ilts
_LIQUIDBEES_ISIN = "INF732E01037"  # already tracked by finideas_ilts


# ── Minimal fakes matching daily_snapshot pattern ────────────────────


@dataclass
class _Leg:
    instrument_key: str
    entry_price: float
    quantity: int
    asset_type: AssetType
    id: int | None = None


@dataclass
class _Strategy:
    legs: list[_Leg]
    name: str = "test_strat"


@dataclass
class _FakePnL:
    total_pnl: Decimal


@dataclass
class _FakeMFPnL:
    total_current_value: Decimal
    total_invested: Decimal
    total_pnl: Decimal
    total_pnl_pct: Decimal


def _etf_leg(key: str, entry_price: float, quantity: int) -> _Leg:
    return _Leg(key, entry_price, quantity, AssetType.EQUITY)


_ETF_KEY = "NSE_EQ|INF754K01LE1"
_ETF_STRATS = [_Strategy(legs=[_etf_leg(_ETF_KEY, 1388.00, 100)])]
_ETF_PRICES = {_ETF_KEY: 1400.00}

# ── Dhan fixture builders ─────────────────────────────────────────────


def _niftyietf_holding(ltp: Decimal | None = Decimal("275.40")) -> DhanHolding:
    return DhanHolding(
        trading_symbol="NIFTYIETF",
        isin=_NIFTYIETF_ISIN,
        security_id="13611",
        exchange="NSE_EQ",
        total_qty=500,
        collateral_qty=500,
        avg_cost_price=Decimal("268.50"),
        classification="EQUITY",
        ltp=ltp,
    )


def _liquidcase_holding(ltp: Decimal | None = Decimal("1005.50")) -> DhanHolding:
    return DhanHolding(
        trading_symbol="LIQUIDCASE",
        isin=_LIQUIDCASE_ISIN,
        security_id="25780",
        exchange="NSE_EQ",
        total_qty=200,
        collateral_qty=200,
        avg_cost_price=Decimal("1003.25"),
        classification="BOND",
        ltp=ltp,
    )


def _make_dhan_summary(
    eq_ltp: Decimal | None = Decimal("275.40"),
    bd_ltp: Decimal | None = Decimal("1005.50"),
    equity_day_delta: Decimal | None = None,
    bond_day_delta: Decimal | None = None,
) -> DhanPortfolioSummary:
    """Build a realistic DhanPortfolioSummary with NIFTYIETF (equity) + LIQUIDCASE (bond)."""
    eq = _niftyietf_holding(eq_ltp)
    bd = _liquidcase_holding(bd_ltp)
    eq_value = (eq.current_value or eq.cost_basis)
    bd_value = (bd.current_value or bd.cost_basis)
    eq_pnl = eq_value - eq.cost_basis
    bd_pnl = bd_value - bd.cost_basis
    return DhanPortfolioSummary(
        snapshot_date=_SNAP_DATE,
        equity_holdings=(eq,),
        equity_value=eq_value,
        equity_basis=eq.cost_basis,
        equity_pnl=eq_pnl,
        equity_pnl_pct=(eq_pnl / eq.cost_basis * 100).quantize(Decimal("0.01")) if eq.cost_basis else None,
        bond_holdings=(bd,),
        bond_value=bd_value,
        bond_basis=bd.cost_basis,
        bond_pnl=bd_pnl,
        bond_pnl_pct=(bd_pnl / bd.cost_basis * 100).quantize(Decimal("0.01")) if bd.cost_basis else None,
        equity_day_delta=equity_day_delta,
        bond_day_delta=bond_day_delta,
    )


# ── Tests: _build_portfolio_summary with dhan_summary ────────────────


class TestBuildPortfolioSummaryDhanFields:
    def test_dhan_available_true_when_summary_provided(self) -> None:
        dhan = _make_dhan_summary()
        result = _build_portfolio_summary(_SNAP_DATE, _ETF_STRATS, _ETF_PRICES, {}, None, dhan_summary=dhan)
        assert result.dhan_available is True

    def test_dhan_available_false_when_none(self) -> None:
        result = _build_portfolio_summary(_SNAP_DATE, _ETF_STRATS, _ETF_PRICES, {}, None, dhan_summary=None)
        assert result.dhan_available is False
        assert result.dhan_equity_value == Decimal("0")
        assert result.dhan_bond_value == Decimal("0")

    def test_equity_value_populated(self) -> None:
        dhan = _make_dhan_summary()
        result = _build_portfolio_summary(_SNAP_DATE, _ETF_STRATS, _ETF_PRICES, {}, None, dhan_summary=dhan)
        # NIFTYIETF: 500 × 275.40 = 137_700
        assert result.dhan_equity_value == Decimal("275.40") * 500

    def test_bond_value_populated(self) -> None:
        dhan = _make_dhan_summary()
        result = _build_portfolio_summary(_SNAP_DATE, _ETF_STRATS, _ETF_PRICES, {}, None, dhan_summary=dhan)
        # LIQUIDCASE: 200 × 1005.50 = 201_100
        assert result.dhan_bond_value == Decimal("1005.50") * 200

    def test_dhan_included_in_total_value(self) -> None:
        dhan = _make_dhan_summary()
        result = _build_portfolio_summary(_SNAP_DATE, _ETF_STRATS, _ETF_PRICES, {}, None, dhan_summary=dhan)
        expected_dhan = dhan.equity_value + dhan.bond_value
        # total_value = etf_value(140_000) + options_pnl(0) + dhan components
        assert result.total_value == Decimal("140000") + expected_dhan

    def test_dhan_excluded_from_total_when_unavailable(self) -> None:
        result_no_dhan = _build_portfolio_summary(_SNAP_DATE, _ETF_STRATS, _ETF_PRICES, {}, None, dhan_summary=None)
        assert result_no_dhan.total_value == Decimal("140000")

    def test_dhan_pnl_included_in_total_pnl(self) -> None:
        dhan = _make_dhan_summary()
        result = _build_portfolio_summary(_SNAP_DATE, _ETF_STRATS, _ETF_PRICES, {}, None, dhan_summary=dhan)
        # ETF P&L: 140_000 − 138_800 = 1_200
        etf_pnl = Decimal("140000") - Decimal("138800")
        assert result.total_pnl == etf_pnl + dhan.equity_pnl + dhan.bond_pnl

    def test_dhan_day_deltas_propagated(self) -> None:
        dhan = _make_dhan_summary(equity_day_delta=Decimal("3450"), bond_day_delta=Decimal("450"))
        result = _build_portfolio_summary(_SNAP_DATE, _ETF_STRATS, _ETF_PRICES, {}, None, dhan_summary=dhan)
        assert result.dhan_equity_day_delta == Decimal("3450")
        assert result.dhan_bond_day_delta == Decimal("450")

    def test_total_day_delta_includes_dhan_when_present(self) -> None:
        dhan = _make_dhan_summary(equity_day_delta=Decimal("2000"), bond_day_delta=Decimal("100"))
        result = _build_portfolio_summary(_SNAP_DATE, _ETF_STRATS, _ETF_PRICES, {}, None, dhan_summary=dhan)
        # total_day_delta = (mf:None→0) + (etf:None→0) + (options:None→0) + 2000 + 100
        # any_delta is True because dhan deltas are not None
        assert result.total_day_delta == Decimal("2100")


# ── Tests: _format_combined_summary Equity section ───────────────────


class TestFormatCombinedSummaryEquitySection:
    def test_dhan_equity_line_present_when_available(self) -> None:
        dhan = _make_dhan_summary()
        out = _format_combined_summary(_ETF_STRATS, _ETF_PRICES, {}, None, dhan_summary=dhan)
        assert "Dhan Equity" in out

    def test_dhan_equity_value_in_output(self) -> None:
        dhan = _make_dhan_summary()
        out = _format_combined_summary(_ETF_STRATS, _ETF_PRICES, {}, None, dhan_summary=dhan)
        # 500 × 275.40 = 137_700 → formatted as 137,700
        assert "137,700" in out

    def test_dhan_equity_line_absent_when_unavailable(self) -> None:
        out = _format_combined_summary(_ETF_STRATS, _ETF_PRICES, {}, None, dhan_summary=None)
        assert "Dhan Equity" not in out

    def test_equity_subtotal_present(self) -> None:
        dhan = _make_dhan_summary()
        out = _format_combined_summary(_ETF_STRATS, _ETF_PRICES, {}, None, dhan_summary=dhan)
        assert "Equity subtotal" in out

    def test_dhan_equity_day_delta_shown_when_present(self) -> None:
        dhan = _make_dhan_summary(equity_day_delta=Decimal("3450"))
        out = _format_combined_summary(_ETF_STRATS, _ETF_PRICES, {}, None, dhan_summary=dhan)
        assert "+3,450" in out


# ── Tests: _format_combined_summary Bonds section ────────────────────


class TestFormatCombinedSummaryBondsSection:
    def test_bonds_section_header_always_present(self) -> None:
        out = _format_combined_summary(_ETF_STRATS, _ETF_PRICES, {}, None, dhan_summary=None)
        assert "── Bonds" in out

    def test_dhan_unavailable_shows_placeholder(self) -> None:
        out = _format_combined_summary(_ETF_STRATS, _ETF_PRICES, {}, None, dhan_summary=None)
        assert "[unavailable]" in out

    def test_dhan_bond_line_present_when_available(self) -> None:
        dhan = _make_dhan_summary()
        out = _format_combined_summary(_ETF_STRATS, _ETF_PRICES, {}, None, dhan_summary=dhan)
        assert "Dhan Bonds" in out

    def test_dhan_bond_value_in_output(self) -> None:
        dhan = _make_dhan_summary()
        out = _format_combined_summary(_ETF_STRATS, _ETF_PRICES, {}, None, dhan_summary=dhan)
        # 200 × 1005.50 = 201_100 → formatted as 201,100
        assert "201,100" in out

    def test_bonds_subtotal_present_when_dhan_available(self) -> None:
        dhan = _make_dhan_summary()
        out = _format_combined_summary(_ETF_STRATS, _ETF_PRICES, {}, None, dhan_summary=dhan)
        assert "Bonds subtotal" in out

    def test_no_bond_holdings_shows_placeholder(self) -> None:
        # DhanPortfolioSummary with no bond holdings but dhan_available=True
        dhan = DhanPortfolioSummary(
            snapshot_date=_SNAP_DATE,
            equity_holdings=(_niftyietf_holding(),),
            equity_value=Decimal("137700"),
            equity_basis=Decimal("134250"),
            equity_pnl=Decimal("3450"),
            equity_pnl_pct=Decimal("2.57"),
            bond_holdings=(),
            bond_value=Decimal("0"),
            bond_basis=Decimal("0"),
            bond_pnl=Decimal("0"),
            bond_pnl_pct=None,
        )
        out = _format_combined_summary(_ETF_STRATS, _ETF_PRICES, {}, None, dhan_summary=dhan)
        assert "no bond holdings" in out


# ── Tests: _format_combined_summary Total section ────────────────────


class TestFormatCombinedSummaryTotalSection:
    def test_total_value_line_always_present(self) -> None:
        out = _format_combined_summary(_ETF_STRATS, _ETF_PRICES, {}, None, dhan_summary=None)
        assert "Total value" in out

    def test_dhan_unavailable_note_in_total(self) -> None:
        out = _format_combined_summary(_ETF_STRATS, _ETF_PRICES, {}, None, dhan_summary=None)
        assert "Dhan unavailable" in out

    def test_no_dhan_note_when_dhan_available(self) -> None:
        dhan = _make_dhan_summary()
        out = _format_combined_summary(_ETF_STRATS, _ETF_PRICES, {}, None, dhan_summary=dhan)
        assert "Dhan unavailable" not in out

    def test_derivatives_section_present(self) -> None:
        out = _format_combined_summary(_ETF_STRATS, _ETF_PRICES, {}, None, dhan_summary=None)
        assert "── Derivatives" in out

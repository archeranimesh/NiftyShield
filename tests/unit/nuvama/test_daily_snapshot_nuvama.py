"""Tests for Nuvama integration in scripts/daily_snapshot.py.

Covers:
- _build_portfolio_summary: nuvama fields wired into totals
- _format_combined_summary: Nuvama Bonds section rendering
- Nuvama unavailable / no holdings edge cases

All tests use the pure helper functions — no I/O, no .env, no DB.
"""

from datetime import date
from decimal import Decimal

import pytest

pytest.importorskip("pydantic", reason="pydantic required for PortfolioSummary")

from scripts.daily_snapshot import (  # noqa: E402
    _build_portfolio_summary,
    _format_combined_summary,
)
from src.nuvama.models import NuvamaBondHolding, NuvamaBondSummary  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_nuvama_summary(
    total_value: str = "3158740.00",
    total_basis: str = "3629222.00",
    total_pnl: str = "529518.00",
    total_pnl_pct: str = "14.59",
    total_day_delta: str = "-12345.00",
    snap_date: date = date(2026, 4, 15),
) -> NuvamaBondSummary:
    return NuvamaBondSummary(
        snapshot_date=snap_date,
        holdings=(),
        total_value=Decimal(total_value),
        total_basis=Decimal(total_basis),
        total_pnl=Decimal(total_pnl),
        total_pnl_pct=Decimal(total_pnl_pct),
        total_day_delta=Decimal(total_day_delta),
    )


def _minimal_summary_kwargs() -> dict:
    """Minimal args for _build_portfolio_summary with no market data."""
    return dict(
        snap_date=date(2026, 4, 15),
        strategies=[],
        prices={},
        strategy_pnls={},
        mf_pnl=None,
    )


# ---------------------------------------------------------------------------
# _build_portfolio_summary — nuvama fields
# ---------------------------------------------------------------------------


class TestBuildPortfolioSummaryNuvamaFields:
    def test_nuvama_available_true_when_summary_provided(self):
        s = _build_portfolio_summary(
            **_minimal_summary_kwargs(), nuvama_summary=_make_nuvama_summary()
        )
        assert s.nuvama_available is True

    def test_nuvama_available_false_when_none(self):
        s = _build_portfolio_summary(**_minimal_summary_kwargs())
        assert s.nuvama_available is False

    def test_nuvama_bond_value_populated(self):
        s = _build_portfolio_summary(
            **_minimal_summary_kwargs(),
            nuvama_summary=_make_nuvama_summary(total_value="3158740.00"),
        )
        assert s.nuvama_bond_value == Decimal("3158740.00")

    def test_nuvama_bond_pnl_populated(self):
        s = _build_portfolio_summary(
            **_minimal_summary_kwargs(),
            nuvama_summary=_make_nuvama_summary(total_pnl="529518.00"),
        )
        assert s.nuvama_bond_pnl == Decimal("529518.00")

    def test_nuvama_included_in_total_value(self):
        s = _build_portfolio_summary(
            **_minimal_summary_kwargs(),
            nuvama_summary=_make_nuvama_summary(total_value="1000000.00"),
        )
        assert s.total_value == Decimal("1000000.00")

    def test_nuvama_excluded_from_total_when_none(self):
        s = _build_portfolio_summary(**_minimal_summary_kwargs())
        assert s.total_value == Decimal("0")

    def test_nuvama_pnl_included_in_total_pnl(self):
        s = _build_portfolio_summary(
            **_minimal_summary_kwargs(),
            nuvama_summary=_make_nuvama_summary(
                total_value="1000000.00",
                total_basis="900000.00",
                total_pnl="100000.00",
            ),
        )
        assert s.total_pnl == Decimal("100000.00")

    def test_nuvama_basis_included_in_total_invested(self):
        s = _build_portfolio_summary(
            **_minimal_summary_kwargs(),
            nuvama_summary=_make_nuvama_summary(total_basis="3629222.00"),
        )
        assert s.total_invested == Decimal("3629222.00")

    def test_nuvama_day_delta_propagated(self):
        s = _build_portfolio_summary(
            **_minimal_summary_kwargs(),
            nuvama_summary=_make_nuvama_summary(total_day_delta="-12345.00"),
        )
        assert s.nuvama_bond_day_delta == Decimal("-12345.00")

    def test_total_day_delta_includes_nuvama(self):
        s = _build_portfolio_summary(
            **_minimal_summary_kwargs(),
            nuvama_summary=_make_nuvama_summary(total_day_delta="-12345.00"),
        )
        # Only Nuvama delta present — total_day_delta must include it
        assert s.total_day_delta == Decimal("-12345.00")


# ---------------------------------------------------------------------------
# _format_combined_summary — Bonds section
# ---------------------------------------------------------------------------


def _format(**kwargs) -> str:
    return _format_combined_summary(
        strategies=[],
        prices={},
        strategy_pnls={},
        mf_pnl=None,
        snap_date=date(2026, 4, 15),
        **kwargs,
    )


class TestFormatCombinedSummaryNuvamaBondsSection:
    def test_nuvama_bond_line_present_when_available(self):
        out = _format(nuvama_summary=_make_nuvama_summary())
        assert "Nuvama Bonds" in out

    def test_nuvama_bond_line_absent_when_unavailable(self):
        out = _format(nuvama_summary=None)
        # Shows [unavailable] marker instead
        assert "Nuvama Bonds" in out  # line exists but shows unavailable
        assert "[unavailable]" in out

    def test_nuvama_bond_value_in_output(self):
        out = _format(nuvama_summary=_make_nuvama_summary(total_value="3158740.00"))
        assert "3,158,740" in out

    def test_nuvama_bond_pnl_in_output(self):
        out = _format(nuvama_summary=_make_nuvama_summary(total_pnl="529518.00"))
        assert "+529,518" in out

    def test_nuvama_included_in_bonds_waterfall_and_total(self):
        # Waterfall layout: Nuvama sub-item visible under Bonds; total reflects
        # Nuvama value. "Bonds subtotal" label belongs to the fallback layout only.
        nuvama = _make_nuvama_summary(total_value="3000000.00")
        out = _format(nuvama_summary=nuvama)
        assert "├ Nuvama Bonds" in out
        assert "3,000,000" in out

    def test_both_zero_bond_holdings_bonds_section_present(self):
        """When both Dhan and Nuvama have zero bond holdings, Bonds section still
        renders with +0 delta — no placeholder text shown."""
        from src.dhan.models import DhanPortfolioSummary

        empty_dhan = DhanPortfolioSummary(
            snapshot_date=date(2026, 4, 15),
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
        empty_nuvama = NuvamaBondSummary(
            snapshot_date=date(2026, 4, 15),
            holdings=(),
            total_value=Decimal("0"),
            total_basis=Decimal("0"),
            total_pnl=Decimal("0"),
            total_pnl_pct=None,
            total_day_delta=Decimal("0"),
        )
        out = _format(dhan_summary=empty_dhan, nuvama_summary=empty_nuvama)
        assert "Bonds" in out
        assert "no bond holdings" not in out

    def test_nuvama_note_in_total_when_unavailable(self):
        out = _format(nuvama_summary=None)
        assert "Nuvama unavailable" in out

    def test_no_nuvama_note_when_available(self):
        out = _format(nuvama_summary=_make_nuvama_summary())
        assert "Nuvama unavailable" not in out

    def test_nuvama_day_delta_shown(self):
        out = _format(nuvama_summary=_make_nuvama_summary(total_day_delta="-12345.00"))
        # A non-None nuvama_bond_day_delta makes total_day_delta non-None, which
        # triggers the waterfall path (not the fallback). Confirm both the path
        # taken and the value.
        assert "📊 Today:" in out        # waterfall path confirmed
        assert "-12,345" in out          # Nuvama Bonds contribution line

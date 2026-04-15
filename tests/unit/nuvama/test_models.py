"""Tests for src/nuvama/models.py — NuvamaBondHolding and NuvamaBondSummary."""

from datetime import date
from decimal import Decimal

import pytest

from src.nuvama.models import NuvamaBondHolding, NuvamaBondSummary


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_holding(
    isin: str = "INE532F07FD3",
    company_name: str = "EFSL 10% NCD 2034",
    trading_symbol: str = "10EFSL34A",
    exchange: str = "BSE",
    qty: int = 700,
    avg_price: str = "1000.00",
    ltp: str = "1014.00",
    chg_pct: str = "-1.28",
    hair_cut: str = "25.00",
) -> NuvamaBondHolding:
    return NuvamaBondHolding(
        isin=isin,
        company_name=company_name,
        trading_symbol=trading_symbol,
        exchange=exchange,
        qty=qty,
        avg_price=Decimal(avg_price),
        ltp=Decimal(ltp),
        chg_pct=Decimal(chg_pct),
        hair_cut=Decimal(hair_cut),
    )


# ---------------------------------------------------------------------------
# NuvamaBondHolding — construction
# ---------------------------------------------------------------------------


def test_holding_classification_default():
    h = _make_holding()
    assert h.classification == "BOND"


def test_holding_frozen():
    h = _make_holding()
    with pytest.raises((AttributeError, TypeError)):
        h.qty = 999  # type: ignore[misc]


def test_holding_cost_basis():
    h = _make_holding(qty=700, avg_price="1000.00")
    assert h.cost_basis == Decimal("700000.00")


def test_holding_current_value():
    h = _make_holding(qty=700, ltp="1014.00")
    assert h.current_value == Decimal("709800.00")


def test_holding_pnl_positive():
    h = _make_holding(qty=700, avg_price="1000.00", ltp="1014.00")
    assert h.pnl == Decimal("9800.00")


def test_holding_pnl_negative():
    h = _make_holding(qty=500, avg_price="1000.00", ltp="988.68")
    assert h.pnl == Decimal("-5660.00")  # (988.68 - 1000.00) * 500 = -11.32 * 500


def test_holding_pnl_pct_positive():
    h = _make_holding(qty=700, avg_price="1000.00", ltp="1014.00")
    # pnl = 9800, basis = 700000 → 9800/700000*100 = 1.40%
    assert h.pnl_pct == Decimal("1.40")


def test_holding_pnl_pct_zero_basis_returns_none():
    h = _make_holding(avg_price="0.00", ltp="100.00")
    assert h.pnl_pct is None


def test_holding_pnl_pct_rounds_to_2dp():
    # 9800 / 700000 * 100 = 1.4000... → rounds to 1.40
    h = _make_holding(qty=700, avg_price="1000.00", ltp="1014.00")
    assert h.pnl_pct is not None
    assert len(str(h.pnl_pct).split(".")[-1]) <= 2


def test_holding_day_delta_negative():
    # current_value=709800, chg_pct=-1.28 → 709800 * -1.28 / 100 = -9085.44
    h = _make_holding(qty=700, ltp="1014.00", chg_pct="-1.28")
    expected = (Decimal("709800.00") * Decimal("-1.28") / 100).quantize(
        Decimal("0.01")
    )
    assert h.day_delta == expected


def test_holding_day_delta_positive():
    # SGB: qty=50, ltp=15382, chg_pct=2.55 → 769100 * 2.55 / 100 = 19612.05
    h = _make_holding(qty=50, ltp="15382", chg_pct="2.55")
    expected = (Decimal("769100") * Decimal("2.55") / 100).quantize(Decimal("0.01"))
    assert h.day_delta == expected


def test_holding_day_delta_zero():
    h = _make_holding(chg_pct="0.00")
    assert h.day_delta == Decimal("0.00")


# ---------------------------------------------------------------------------
# NuvamaBondHolding — GSec with sub-100 ltp and avg
# ---------------------------------------------------------------------------


def test_gsec_values():
    """G-Sec 8.28% 2027: qty=2000, avg=109, ltp=144.40"""
    h = _make_holding(
        isin="IN0020070069",
        qty=2000,
        avg_price="109.00",
        ltp="144.40",
        chg_pct="-5.00",
    )
    assert h.cost_basis == Decimal("218000.00")
    assert h.current_value == Decimal("288800.00")
    assert h.pnl == Decimal("70800.00")
    assert h.pnl_pct == Decimal("32.48")


# ---------------------------------------------------------------------------
# NuvamaBondSummary — construction and totals
# ---------------------------------------------------------------------------


def _make_summary(
    holdings: list[NuvamaBondHolding] | None = None,
    snap_date: date = date(2026, 4, 15),
) -> NuvamaBondSummary:
    from src.nuvama.reader import build_nuvama_summary

    return build_nuvama_summary(holdings or [], snap_date)


def test_summary_empty_holdings():
    s = _make_summary([])
    assert s.total_value == Decimal("0")
    assert s.total_basis == Decimal("0")
    assert s.total_pnl == Decimal("0")
    assert s.total_pnl_pct is None
    assert s.total_day_delta == Decimal("0")
    assert s.holdings == ()


def test_summary_single_holding_totals():
    h = _make_holding(qty=700, avg_price="1000.00", ltp="1014.00", chg_pct="-1.28")
    s = _make_summary([h])
    assert s.total_value == Decimal("709800.00")
    assert s.total_basis == Decimal("700000.00")
    assert s.total_pnl == Decimal("9800.00")


def test_summary_pnl_pct_computed():
    h = _make_holding(qty=700, avg_price="1000.00", ltp="1014.00")
    s = _make_summary([h])
    # 9800 / 700000 * 100 = 1.40
    assert s.total_pnl_pct == Decimal("1.40")


def test_summary_multiple_holdings_sum():
    h1 = _make_holding(isin="A", qty=700, avg_price="1000.00", ltp="1014.00")
    h2 = _make_holding(isin="B", qty=500, avg_price="1000.00", ltp="988.68")
    s = _make_summary([h1, h2])
    assert s.total_value == Decimal("709800.00") + Decimal("494340.00")
    assert s.total_basis == Decimal("700000.00") + Decimal("500000.00")


def test_summary_day_delta_sum():
    h1 = _make_holding(isin="A", qty=700, ltp="1014.00", chg_pct="-1.28")
    h2 = _make_holding(isin="B", qty=50, ltp="15382", chg_pct="2.55")
    s = _make_summary([h1, h2])
    assert s.total_day_delta == h1.day_delta + h2.day_delta


def test_summary_frozen():
    s = _make_summary()
    with pytest.raises((AttributeError, TypeError)):
        s.total_value = Decimal("999")  # type: ignore[misc]


def test_summary_snapshot_date_stored():
    snap = date(2026, 4, 15)
    s = _make_summary(snap_date=snap)
    assert s.snapshot_date == snap


def test_summary_holdings_tuple():
    h = _make_holding()
    s = _make_summary([h])
    assert isinstance(s.holdings, tuple)
    assert len(s.holdings) == 1

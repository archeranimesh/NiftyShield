"""Tests for the pure helper functions in scripts/daily_snapshot.py.

_etf_current_value, _etf_cost_basis, and _build_portfolio_summary have no
I/O — they only need strategies, prices, and a few typed dicts.  No
sys.modules patching required: daily_snapshot.py only imports stdlib and
src.portfolio.models at module level, so helpers are importable cleanly.

No network, no DB, no .env required.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from scripts.daily_snapshot import (
    _build_portfolio_summary,
    _etf_cost_basis,
    _etf_current_value,
)
from src.portfolio.models import AssetType, PortfolioSummary

# ── Minimal fakes ────────────────────────────────────────────────


@dataclass
class _Leg:
    instrument_key: str
    entry_price: float
    quantity: int
    asset_type: AssetType


@dataclass
class _Strategy:
    legs: list[_Leg]


def _etf_leg(key: str, entry_price: float, quantity: int) -> _Leg:
    return _Leg(key, entry_price, quantity, AssetType.EQUITY)


def _fo_leg(key: str, entry_price: float, quantity: int) -> _Leg:
    return _Leg(key, entry_price, quantity, AssetType.PE)


def _strats(*legs: _Leg) -> list[_Strategy]:
    """Build a single-strategy list from pre-built _Leg objects."""
    return [_Strategy(legs=list(legs))]


ETF_KEY = "NSE_EQ|INF754K01LE1"
ETF_KEY2 = "NSE_EQ|INF204KB14I2"
FO_KEY = "NSE_FO|37810"


# ── _etf_cost_basis ───────────────────────────────────────────────


def test_etf_cost_basis_single_etf_leg() -> None:
    assert _etf_cost_basis(_strats(_etf_leg(ETF_KEY, 1388.12, 438))) == Decimal("1388.12") * 438


def test_etf_cost_basis_excludes_fo_legs() -> None:
    strats = _strats(_etf_leg(ETF_KEY, 1388.12, 438), _fo_leg(FO_KEY, 975.00, 65))
    assert _etf_cost_basis(strats) == Decimal("1388.12") * 438


def test_etf_cost_basis_no_etf_legs_returns_zero() -> None:
    assert _etf_cost_basis(_strats(_fo_leg(FO_KEY, 975.00, 65))) == Decimal("0")


def test_etf_cost_basis_multiple_etf_legs_summed() -> None:
    strats = _strats(_etf_leg(ETF_KEY, 1388.12, 438), _etf_leg(ETF_KEY2, 50.00, 100))
    expected = Decimal("1388.12") * 438 + Decimal("50.00") * 100
    assert _etf_cost_basis(strats) == expected


def test_etf_cost_basis_decimal_precision() -> None:
    """Entry price with sub-rupee precision must survive Decimal conversion."""
    strats = _strats(_etf_leg(ETF_KEY, 1388.12, 438))
    assert _etf_cost_basis(strats) == Decimal(str(1388.12)) * 438


# ── _etf_current_value ────────────────────────────────────────────


def test_etf_current_value_uses_ltp_when_present() -> None:
    prices = {ETF_KEY: 1450.00}
    assert (
        _etf_current_value(_strats(_etf_leg(ETF_KEY, 1388.12, 438)), prices)
        == Decimal("1450.00") * 438
    )


def test_etf_current_value_falls_back_to_entry_price() -> None:
    """LTP missing from prices — must use entry_price, not raise KeyError."""
    result = _etf_current_value(_strats(_etf_leg(ETF_KEY, 1388.12, 438)), {})
    assert result == Decimal("1388.12") * 438


def test_etf_current_value_excludes_fo_legs() -> None:
    strats = _strats(_etf_leg(ETF_KEY, 1388.12, 438), _fo_leg(FO_KEY, 975.00, 65))
    prices = {ETF_KEY: 1450.00, FO_KEY: 900.00}
    assert _etf_current_value(strats, prices) == Decimal("1450.00") * 438


def test_etf_current_value_no_etf_legs_returns_zero() -> None:
    assert _etf_current_value(
        _strats(_fo_leg(FO_KEY, 975.00, 65)), {FO_KEY: 900.00}
    ) == Decimal("0")


def test_etf_current_value_ltp_higher_than_basis() -> None:
    prices = {ETF_KEY: 1500.00}
    value = _etf_current_value(_strats(_etf_leg(ETF_KEY, 1388.12, 438)), prices)
    basis = _etf_cost_basis(_strats(_etf_leg(ETF_KEY, 1388.12, 438)))
    assert value > basis


def test_etf_current_value_ltp_lower_than_basis() -> None:
    prices = {ETF_KEY: 1300.00}
    value = _etf_current_value(_strats(_etf_leg(ETF_KEY, 1388.12, 438)), prices)
    basis = _etf_cost_basis(_strats(_etf_leg(ETF_KEY, 1388.12, 438)))
    assert value < basis


# ── _build_portfolio_summary ─────────────────────────────────────


@dataclass
class _FakePnL:
    """Minimal stand-in for StrategyPnL — only total_pnl consumed."""
    total_pnl: Decimal


@dataclass
class _FakeMFPnL:
    """Minimal stand-in for PortfolioPnL — only top-level fields consumed."""
    total_current_value: Decimal
    total_invested: Decimal
    total_pnl: Decimal
    total_pnl_pct: Decimal


_SNAP_DATE = date(2026, 4, 8)
_ETF_STRATS = _strats(_etf_leg(ETF_KEY, 1388.00, 100))  # cost basis = 138_800
_ETF_PRICES = {ETF_KEY: 1400.00}                          # current value = 140_000


class TestBuildPortfolioSummary:
    def test_returns_portfolio_summary_instance(self) -> None:
        result = _build_portfolio_summary(_SNAP_DATE, _ETF_STRATS, _ETF_PRICES, {}, None)
        assert isinstance(result, PortfolioSummary)

    def test_snapshot_date_propagated(self) -> None:
        result = _build_portfolio_summary(_SNAP_DATE, _ETF_STRATS, _ETF_PRICES, {}, None)
        assert result.snapshot_date == _SNAP_DATE

    def test_mf_available_false_when_mf_pnl_none(self) -> None:
        result = _build_portfolio_summary(_SNAP_DATE, _ETF_STRATS, _ETF_PRICES, {}, None)
        assert result.mf_available is False
        assert result.mf_value == Decimal("0")
        assert result.mf_pnl_pct is None

    def test_mf_available_true_when_mf_pnl_provided(self) -> None:
        mf = _FakeMFPnL(
            total_current_value=Decimal("500000"),
            total_invested=Decimal("450000"),
            total_pnl=Decimal("50000"),
            total_pnl_pct=Decimal("11.11"),
        )
        result = _build_portfolio_summary(_SNAP_DATE, _ETF_STRATS, _ETF_PRICES, {}, mf)
        assert result.mf_available is True
        assert result.mf_value == Decimal("500000")
        assert result.mf_pnl_pct == Decimal("11.11")

    def test_total_value_is_mf_plus_etf_plus_options(self) -> None:
        # ETF: 1400 × 100 = 140_000; options P&L = +2000; MF = 500_000
        mf = _FakeMFPnL(Decimal("500000"), Decimal("450000"), Decimal("50000"), Decimal("11.11"))
        pnls = {"strat": _FakePnL(Decimal("2000"))}
        result = _build_portfolio_summary(_SNAP_DATE, _ETF_STRATS, _ETF_PRICES, pnls, mf)
        assert result.total_value == Decimal("500000") + Decimal("140000") + Decimal("2000")

    def test_total_pnl_computation(self) -> None:
        # total_pnl = mf_pnl + (etf_value - etf_basis) + options_pnl
        # = 50_000 + (140_000 − 138_800) + 2_000 = 53_200
        mf = _FakeMFPnL(Decimal("500000"), Decimal("450000"), Decimal("50000"), Decimal("11.11"))
        pnls = {"strat": _FakePnL(Decimal("2000"))}
        result = _build_portfolio_summary(_SNAP_DATE, _ETF_STRATS, _ETF_PRICES, pnls, mf)
        expected = Decimal("50000") + (Decimal("140000") - Decimal("138800")) + Decimal("2000")
        assert result.total_pnl == expected

    def test_total_pnl_pct_quantized_to_two_dp(self) -> None:
        mf = _FakeMFPnL(Decimal("500000"), Decimal("450000"), Decimal("50000"), Decimal("11.11"))
        result = _build_portfolio_summary(_SNAP_DATE, _ETF_STRATS, _ETF_PRICES, {}, mf)
        # quantize(Decimal("0.01")) gives exactly 2 decimal places
        assert result.total_pnl_pct == result.total_pnl_pct.quantize(Decimal("0.01"))

    def test_all_deltas_none_without_prev_data(self) -> None:
        result = _build_portfolio_summary(_SNAP_DATE, _ETF_STRATS, _ETF_PRICES, {}, None)
        assert result.etf_day_delta is None
        assert result.options_day_delta is None
        assert result.mf_day_delta is None
        assert result.total_day_delta is None

    def test_mf_day_delta_computed_when_prev_mf_provided(self) -> None:
        mf = _FakeMFPnL(Decimal("500000"), Decimal("450000"), Decimal("50000"), Decimal("11.11"))
        prev_mf = _FakeMFPnL(Decimal("495000"), Decimal("450000"), Decimal("45000"), Decimal("10.00"))
        result = _build_portfolio_summary(
            _SNAP_DATE, _ETF_STRATS, _ETF_PRICES, {}, mf, prev_mf_pnl=prev_mf
        )
        assert result.mf_day_delta == Decimal("5000")  # 500_000 − 495_000

    def test_total_day_delta_none_when_only_prev_mf_absent(self) -> None:
        """prev_mf_pnl=None + no prev_snapshots → total_day_delta is None."""
        result = _build_portfolio_summary(
            _SNAP_DATE, _ETF_STRATS, _ETF_PRICES, {}, None, prev_mf_pnl=None
        )
        assert result.total_day_delta is None

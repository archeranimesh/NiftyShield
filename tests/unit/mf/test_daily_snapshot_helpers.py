"""Tests for the pure helper functions in scripts/daily_snapshot.py.

_etf_current_value and _etf_cost_basis have no I/O — they only need
the strategies list and a prices dict.  Isolated here so they can be
imported without pulling in UpstoxMarketClient (which requires a live
.env).  All external modules that daily_snapshot imports at load time
are stubbed in sys.modules before the import.

No network, no DB, no .env required.
"""

from __future__ import annotations

import sys
import types
from dataclasses import dataclass
from decimal import Decimal

# ── Stub every module daily_snapshot.py imports at the top level ─────────
# Must happen before `from scripts.daily_snapshot import ...`


def _stub(name: str, **attrs) -> types.ModuleType:
    m = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(m, k, v)
    sys.modules[name] = m
    return m


_stub("dotenv", load_dotenv=lambda: None)
_stub("src.client", UpstoxMarketClient=object)
_stub("src.client.upstox_market", UpstoxMarketClient=object)
_stub("src.portfolio.tracker", PortfolioTracker=object)

from scripts.daily_snapshot import _etf_cost_basis, _etf_current_value  # noqa: E402
import importlib

del sys.modules["src.portfolio.tracker"]
importlib.import_module("src.portfolio.tracker")

# ── Minimal fakes ────────────────────────────────────────────────


@dataclass
class _Leg:
    instrument_key: str
    entry_price: float
    quantity: int


@dataclass
class _Strategy:
    legs: list[_Leg]


def _strats(*legs_spec: tuple) -> list[_Strategy]:
    """Build a single-strategy list from (key, entry_price, quantity) tuples."""
    return [_Strategy(legs=[_Leg(*s) for s in legs_spec])]


ETF_KEY = "NSE_EQ|INF754K01LE1"
FO_KEY = "NSE_FO|37810"


# ── _etf_cost_basis ───────────────────────────────────────────────


def test_etf_cost_basis_single_etf_leg() -> None:
    assert _etf_cost_basis(_strats((ETF_KEY, 1388.12, 438))) == Decimal("1388.12") * 438


def test_etf_cost_basis_excludes_fo_legs() -> None:
    strats = _strats((ETF_KEY, 1388.12, 438), (FO_KEY, 975.00, 65))
    assert _etf_cost_basis(strats) == Decimal("1388.12") * 438


def test_etf_cost_basis_no_etf_legs_returns_zero() -> None:
    assert _etf_cost_basis(_strats((FO_KEY, 975.00, 65))) == Decimal("0")


def test_etf_cost_basis_multiple_etf_legs_summed() -> None:
    key2 = "NSE_EQ|INF204KB14I2"
    strats = _strats((ETF_KEY, 1388.12, 438), (key2, 50.00, 100))
    expected = Decimal("1388.12") * 438 + Decimal("50.00") * 100
    assert _etf_cost_basis(strats) == expected


def test_etf_cost_basis_decimal_precision() -> None:
    """Entry price with sub-rupee precision must survive Decimal conversion."""
    strats = _strats((ETF_KEY, 1388.12, 438))
    assert _etf_cost_basis(strats) == Decimal(str(1388.12)) * 438


# ── _etf_current_value ────────────────────────────────────────────


def test_etf_current_value_uses_ltp_when_present() -> None:
    prices = {ETF_KEY: 1450.00}
    assert (
        _etf_current_value(_strats((ETF_KEY, 1388.12, 438)), prices)
        == Decimal("1450.00") * 438
    )


def test_etf_current_value_falls_back_to_entry_price() -> None:
    """LTP missing from prices — must use entry_price, not raise KeyError."""
    result = _etf_current_value(_strats((ETF_KEY, 1388.12, 438)), {})
    assert result == Decimal("1388.12") * 438


def test_etf_current_value_excludes_fo_legs() -> None:
    strats = _strats((ETF_KEY, 1388.12, 438), (FO_KEY, 975.00, 65))
    prices = {ETF_KEY: 1450.00, FO_KEY: 900.00}
    assert _etf_current_value(strats, prices) == Decimal("1450.00") * 438


def test_etf_current_value_no_etf_legs_returns_zero() -> None:
    assert _etf_current_value(
        _strats((FO_KEY, 975.00, 65)), {FO_KEY: 900.00}
    ) == Decimal("0")


def test_etf_current_value_ltp_higher_than_basis() -> None:
    prices = {ETF_KEY: 1500.00}
    value = _etf_current_value(_strats((ETF_KEY, 1388.12, 438)), prices)
    basis = _etf_cost_basis(_strats((ETF_KEY, 1388.12, 438)))
    assert value > basis


def test_etf_current_value_ltp_lower_than_basis() -> None:
    prices = {ETF_KEY: 1300.00}
    value = _etf_current_value(_strats((ETF_KEY, 1388.12, 438)), prices)
    basis = _etf_cost_basis(_strats((ETF_KEY, 1388.12, 438)))
    assert value < basis

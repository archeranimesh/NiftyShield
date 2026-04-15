"""Unit tests for scripts/roll_leg.py.

Tests focus on the pure _build_trades() function and CLI validation logic.
No DB I/O here — store.record_roll() is tested in test_trade_store.py.

Coverage:
- _build_trades: returns correct (close_trade, open_trade) tuple.
- _build_trades: close and open legs are independent (different leg_roles/keys).
- _build_trades: notes propagated to both trades.
- _build_trades: zero qty rejected (Pydantic validator).
- _build_trades: zero price rejected (Pydantic validator).
- _build_trades: negative qty rejected (Pydantic validator).
"""

from datetime import date
from decimal import Decimal

import pytest

from scripts.roll_leg import _build_trades
from src.portfolio.models import TradeAction


# ── Helpers ────────────────────────────────────────────────────────────────────

_STRATEGY = "finideas_ilts"
_DATE = date(2026, 6, 20)
_OLD_LEG = "NIFTY_MAY_PE_ATM"
_OLD_KEY = "NSE_FO|12345"
_NEW_LEG = "NIFTY_JUN_PE_ATM"
_NEW_KEY = "NSE_FO|67890"


def _valid_kwargs(**overrides):
    base = dict(
        strategy=_STRATEGY,
        trade_date=_DATE,
        old_leg=_OLD_LEG,
        old_key=_OLD_KEY,
        old_action="BUY",
        old_qty=50,
        old_price="45.00",
        new_leg=_NEW_LEG,
        new_key=_NEW_KEY,
        new_action="SELL",
        new_qty=50,
        new_price="85.00",
        notes="",
    )
    base.update(overrides)
    return base


# ── _build_trades happy path ───────────────────────────────────────────────────


def test_build_trades_returns_two_trade_objects() -> None:
    close_trade, open_trade = _build_trades(**_valid_kwargs())
    assert close_trade is not None
    assert open_trade is not None


def test_build_trades_close_fields_correct() -> None:
    close_trade, _ = _build_trades(**_valid_kwargs())
    assert close_trade.strategy_name == _STRATEGY
    assert close_trade.trade_date == _DATE
    assert close_trade.leg_role == _OLD_LEG
    assert close_trade.instrument_key == _OLD_KEY
    assert close_trade.action == TradeAction.BUY
    assert close_trade.quantity == 50
    assert close_trade.price == Decimal("45.00")


def test_build_trades_open_fields_correct() -> None:
    _, open_trade = _build_trades(**_valid_kwargs())
    assert open_trade.strategy_name == _STRATEGY
    assert open_trade.trade_date == _DATE
    assert open_trade.leg_role == _NEW_LEG
    assert open_trade.instrument_key == _NEW_KEY
    assert open_trade.action == TradeAction.SELL
    assert open_trade.quantity == 50
    assert open_trade.price == Decimal("85.00")


def test_build_trades_notes_propagated_to_both() -> None:
    close_trade, open_trade = _build_trades(**_valid_kwargs(notes="JUN expiry roll"))
    assert close_trade.notes == "JUN expiry roll"
    assert open_trade.notes == "JUN expiry roll"


def test_build_trades_legs_are_independent() -> None:
    """Close and open trades carry distinct leg_roles and instrument keys."""
    close_trade, open_trade = _build_trades(**_valid_kwargs())
    assert close_trade.leg_role != open_trade.leg_role
    assert close_trade.instrument_key != open_trade.instrument_key


# ── _build_trades validation errors ───────────────────────────────────────────


def test_build_trades_rejects_zero_old_qty() -> None:
    with pytest.raises(Exception):  # Pydantic ValidationError
        _build_trades(**_valid_kwargs(old_qty=0))


def test_build_trades_rejects_zero_new_qty() -> None:
    with pytest.raises(Exception):
        _build_trades(**_valid_kwargs(new_qty=0))


def test_build_trades_rejects_negative_old_qty() -> None:
    with pytest.raises(Exception):
        _build_trades(**_valid_kwargs(old_qty=-10))


def test_build_trades_rejects_zero_old_price() -> None:
    with pytest.raises(Exception):
        _build_trades(**_valid_kwargs(old_price="0"))


def test_build_trades_rejects_zero_new_price() -> None:
    with pytest.raises(Exception):
        _build_trades(**_valid_kwargs(new_price="0.00"))

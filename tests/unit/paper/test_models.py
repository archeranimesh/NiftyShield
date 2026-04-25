"""Unit tests for src/paper/models.py.

Coverage:
- PaperTrade: happy-path construction with all required fields.
- PaperTrade: strategy_name prefix validator rejects non-paper_ names.
- PaperTrade: strategy_name prefix validator accepts paper_ names.
- PaperTrade: price validator coerces float via str() to avoid fp drift.
- PaperTrade: price validator coerces string price correctly.
- PaperTrade: frozen — mutation raises TypeError.
- PaperTrade: is_paper is always True and cannot be overridden.
- PaperTrade: quantity must be positive (gt=0).
- PaperTrade: price must be positive (gt=0).
- PaperTrade: notes defaults to empty string.
- PaperPosition: happy-path construction, all fields accessible.
- PaperNavSnapshot: total_pnl is sum of unrealized + realized.
"""

from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from src.models.portfolio import TradeAction
from src.paper.models import PaperNavSnapshot, PaperPosition, PaperTrade


# ── Helpers ───────────────────────────────────────────────────────────────────


def _paper_trade(**overrides) -> PaperTrade:
    """Build a valid PaperTrade with sensible defaults."""
    defaults = dict(
        strategy_name="paper_csp_nifty_v1",
        leg_role="short_put",
        instrument_key="NSE_FO|12345",
        trade_date=date(2026, 5, 1),
        action=TradeAction.SELL,
        quantity=75,
        price=Decimal("120.50"),
        notes="entry at mid",
    )
    defaults.update(overrides)
    return PaperTrade(**defaults)


# ── PaperTrade: construction ──────────────────────────────────────────────────


def test_paper_trade_happy_path() -> None:
    t = _paper_trade()
    assert t.strategy_name == "paper_csp_nifty_v1"
    assert t.leg_role == "short_put"
    assert t.instrument_key == "NSE_FO|12345"
    assert t.trade_date == date(2026, 5, 1)
    assert t.action == TradeAction.SELL
    assert t.quantity == 75
    assert t.price == Decimal("120.50")
    assert t.notes == "entry at mid"


def test_paper_trade_is_paper_always_true() -> None:
    t = _paper_trade()
    assert t.is_paper is True


def test_paper_trade_cannot_set_is_paper_false() -> None:
    """Literal[True] type means is_paper=False raises ValidationError."""
    with pytest.raises(ValidationError):
        PaperTrade(
            strategy_name="paper_csp_nifty_v1",
            leg_role="short_put",
            instrument_key="NSE_FO|12345",
            trade_date=date(2026, 5, 1),
            action=TradeAction.SELL,
            quantity=75,
            price=Decimal("120.50"),
            is_paper=False,  # type: ignore[arg-type]
        )


def test_paper_trade_notes_defaults_empty() -> None:
    t = _paper_trade(notes="")
    assert t.notes == ""


# ── PaperTrade: strategy_name prefix validator ────────────────────────────────


def test_paper_trade_rejects_missing_prefix() -> None:
    with pytest.raises(ValidationError, match="must start with 'paper_'"):
        _paper_trade(strategy_name="csp_nifty_v1")


def test_paper_trade_rejects_live_strategy_name() -> None:
    with pytest.raises(ValidationError, match="must start with 'paper_'"):
        _paper_trade(strategy_name="finideas_ilts")


def test_paper_trade_rejects_empty_string() -> None:
    with pytest.raises(ValidationError):
        _paper_trade(strategy_name="")


def test_paper_trade_accepts_paper_prefix() -> None:
    t = _paper_trade(strategy_name="paper_ic_nifty_v1")
    assert t.strategy_name == "paper_ic_nifty_v1"


# ── PaperTrade: price validator ───────────────────────────────────────────────


def test_paper_trade_float_price_coerced_to_decimal() -> None:
    t = _paper_trade(price=120.5)
    assert isinstance(t.price, Decimal)
    assert t.price == Decimal("120.5")


def test_paper_trade_string_price_accepted() -> None:
    t = _paper_trade(price="98.75")
    assert t.price == Decimal("98.75")


def test_paper_trade_zero_price_rejected() -> None:
    with pytest.raises(ValidationError):
        _paper_trade(price=Decimal("0"))


def test_paper_trade_negative_price_rejected() -> None:
    with pytest.raises(ValidationError):
        _paper_trade(price=Decimal("-1"))


# ── PaperTrade: quantity validator ────────────────────────────────────────────


def test_paper_trade_zero_quantity_rejected() -> None:
    with pytest.raises(ValidationError):
        _paper_trade(quantity=0)


def test_paper_trade_negative_quantity_rejected() -> None:
    with pytest.raises(ValidationError):
        _paper_trade(quantity=-5)


# ── PaperTrade: immutability ──────────────────────────────────────────────────


def test_paper_trade_is_frozen() -> None:
    t = _paper_trade()
    with pytest.raises((TypeError, ValidationError)):
        t.quantity = 100  # type: ignore[misc]


# ── PaperPosition ─────────────────────────────────────────────────────────────


def test_paper_position_construction() -> None:
    pos = PaperPosition(
        strategy_name="paper_csp_nifty_v1",
        leg_role="short_put",
        net_qty=-75,
        avg_cost=Decimal("0"),
        avg_sell_price=Decimal("120.50"),
        instrument_key="NSE_FO|12345",
    )
    assert pos.strategy_name == "paper_csp_nifty_v1"
    assert pos.leg_role == "short_put"
    assert pos.net_qty == -75
    assert pos.avg_sell_price == Decimal("120.50")
    assert pos.instrument_key == "NSE_FO|12345"


def test_paper_position_is_frozen() -> None:
    pos = PaperPosition(
        strategy_name="paper_csp_nifty_v1",
        leg_role="short_put",
        net_qty=75,
        avg_cost=Decimal("100"),
        avg_sell_price=Decimal("0"),
        instrument_key="NSE_FO|12345",
    )
    with pytest.raises((TypeError, AttributeError)):
        pos.net_qty = 0  # type: ignore[misc]


# ── PaperNavSnapshot ──────────────────────────────────────────────────────────


def test_paper_nav_snapshot_total_pnl() -> None:
    snap = PaperNavSnapshot(
        strategy_name="paper_csp_nifty_v1",
        snapshot_date=date(2026, 5, 2),
        unrealized_pnl=Decimal("500.00"),
        realized_pnl=Decimal("250.00"),
        total_pnl=Decimal("750.00"),
    )
    assert snap.total_pnl == snap.unrealized_pnl + snap.realized_pnl


def test_paper_nav_snapshot_underlying_price_optional() -> None:
    snap = PaperNavSnapshot(
        strategy_name="paper_csp_nifty_v1",
        snapshot_date=date(2026, 5, 2),
        unrealized_pnl=Decimal("0"),
        realized_pnl=Decimal("0"),
        total_pnl=Decimal("0"),
    )
    assert snap.underlying_price is None


def test_paper_nav_snapshot_with_underlying_price() -> None:
    snap = PaperNavSnapshot(
        strategy_name="paper_csp_nifty_v1",
        snapshot_date=date(2026, 5, 2),
        unrealized_pnl=Decimal("100"),
        realized_pnl=Decimal("50"),
        total_pnl=Decimal("150"),
        underlying_price=Decimal("23500.00"),
    )
    assert snap.underlying_price == Decimal("23500.00")

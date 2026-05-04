"""Unit tests for scripts/paper_3track_overlay_roll.py.

Coverage:
- _parse_expiry_from_key: PE key, CE key, equity key (None).
- _find_expiring_overlay: filters by DTE threshold; skips equity legs.
- _cycle_pnl: BUY-to-open (PP) and SELL-to-open (CC) P&L directions.
- _roll_single: open-failure triggers delete_trade rollback.
"""

from __future__ import annotations

import asyncio
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

import scripts.paper_3track_overlay_roll as roll_mod
from src.models.portfolio import TradeAction
from src.paper.models import PaperTrade
from src.paper.store import PaperStore


# ── Helpers ───────────────────────────────────────────────────────────────────

_STRATEGY = "paper_nifty_spot"
_ROLL_DATE = date(2026, 5, 7)


def _make_store(tmp_path: Path) -> PaperStore:
    return PaperStore(tmp_path / "test.db")


def _make_pp_trade(
    strategy: str = _STRATEGY,
    instrument_key: str = "NSE_FO|NIFTY29MAY2026PE",
    price: Decimal = Decimal("300.00"),
    trade_date: date = date(2026, 4, 1),
    action: TradeAction = TradeAction.BUY,
) -> PaperTrade:
    return PaperTrade(
        strategy_name=strategy,
        leg_role="overlay_pp",
        instrument_key=instrument_key,
        trade_date=trade_date,
        action=action,
        quantity=65,
        price=price,
    )


def _make_cc_trade(
    strategy: str = _STRATEGY,
    instrument_key: str = "NSE_FO|NIFTY29MAY2026CE",
    price: Decimal = Decimal("150.00"),
    trade_date: date = date(2026, 4, 1),
    action: TradeAction = TradeAction.SELL,
) -> PaperTrade:
    return PaperTrade(
        strategy_name=strategy,
        leg_role="overlay_cc",
        instrument_key=instrument_key,
        trade_date=trade_date,
        action=action,
        quantity=65,
        price=price,
    )


# ── _parse_expiry_from_key ────────────────────────────────────────────────────


def test_parse_expiry_from_key_pe() -> None:
    result = roll_mod._parse_expiry_from_key("NSE_FO|NIFTY29MAY2026PE")
    assert result == date(2026, 5, 29)


def test_parse_expiry_from_key_ce() -> None:
    result = roll_mod._parse_expiry_from_key("NSE_FO|NIFTY26JUN2026CE")
    assert result == date(2026, 6, 26)


def test_parse_expiry_from_key_equity_returns_none() -> None:
    result = roll_mod._parse_expiry_from_key("NSE_EQ|NIFTYBEES")
    assert result is None


def test_parse_expiry_from_key_malformed_returns_none() -> None:
    result = roll_mod._parse_expiry_from_key("NSE_FO|NIFTY00XXX0000PE")
    assert result is None


# ── _find_expiring_overlay ────────────────────────────────────────────────────


def test_find_expiring_overlay_filters_by_dte() -> None:
    """Legs with DTE > OVERLAY_ROLL_DTE must not be returned unless force=True."""
    # Instrument key: 29MAY2026 — DTE from 2026-05-07 = 22 days, well above threshold=5
    trade = _make_pp_trade(instrument_key="NSE_FO|NIFTY29MAY2026PE")

    result_no_force = roll_mod._find_expiring_overlay([trade], _ROLL_DATE, "overlay_pp", force=False)
    assert result_no_force == []

    result_forced = roll_mod._find_expiring_overlay([trade], _ROLL_DATE, "overlay_pp", force=True)
    assert result_forced == [trade]


def test_find_expiring_overlay_skips_equity() -> None:
    """Equity instrument keys (no expiry in key) must be silently skipped."""
    equity_trade = PaperTrade(
        strategy_name=_STRATEGY,
        leg_role="base_etf",
        instrument_key="NSE_EQ|NIFTYBEES",
        trade_date=date(2026, 4, 1),
        action=TradeAction.BUY,
        quantity=65,
        price=Decimal("240.00"),
    )
    result = roll_mod._find_expiring_overlay([equity_trade], _ROLL_DATE, "base_etf", force=True)
    assert result == []


def test_find_expiring_overlay_near_expiry_returned() -> None:
    """Key with DTE ≤ 5 from roll_date must be returned without --force."""
    # 2026-05-12 is 5 days from _ROLL_DATE (2026-05-07), right at the boundary.
    trade = _make_pp_trade(instrument_key="NSE_FO|NIFTY12MAY2026PE")
    result = roll_mod._find_expiring_overlay([trade], _ROLL_DATE, "overlay_pp", force=False)
    assert result == [trade]


def test_find_expiring_overlay_closed_position_returns_empty() -> None:
    """Buy followed by equal sell → net=0 → no open position."""
    open_trade  = _make_pp_trade(action=TradeAction.BUY)
    close_trade = _make_pp_trade(action=TradeAction.SELL, trade_date=date(2026, 4, 15))
    result = roll_mod._find_expiring_overlay(
        [open_trade, close_trade], _ROLL_DATE, "overlay_pp", force=True
    )
    assert result == []


# ── _cycle_pnl ────────────────────────────────────────────────────────────────


def test_cycle_pnl_buy_to_open_pp() -> None:
    """PP: close_price > open_price → positive P&L."""
    open_trade = _make_pp_trade(price=Decimal("300.00"))
    close_trade = _make_pp_trade(
        action=TradeAction.SELL, price=Decimal("350.00"), trade_date=_ROLL_DATE
    )
    pnl = roll_mod._cycle_pnl(open_trade, close_trade)
    # (350 - 300) × 65 = 3250
    assert pnl == Decimal("3250")


def test_cycle_pnl_sell_to_open_cc() -> None:
    """CC: close_price < open_price → positive P&L (premium decay)."""
    open_trade = _make_cc_trade(price=Decimal("150.00"))
    close_trade = _make_cc_trade(
        action=TradeAction.BUY, price=Decimal("80.00"), trade_date=_ROLL_DATE
    )
    pnl = roll_mod._cycle_pnl(open_trade, close_trade)
    # (150 - 80) × 65 = 4550
    assert pnl == Decimal("4550")


# ── _roll_single rollback path ────────────────────────────────────────────────


def test_roll_single_open_failure_deletes_close_trade(tmp_path: Path) -> None:
    """If _open_new_leg raises, the close trade written by _close_leg must be deleted."""
    store = _make_store(tmp_path)

    # Record an open PP trade
    open_trade = _make_pp_trade(
        instrument_key="NSE_FO|NIFTY12MAY2026PE",  # DTE=5 from _ROLL_DATE
        price=Decimal("300.00"),
    )
    store.record_trade(open_trade)

    # Broker mock: LTP for close is 280
    mock_broker = AsyncMock()
    mock_broker.get_ltp = AsyncMock(
        return_value={"NSE_FO|NIFTY12MAY2026PE": 280.0}
    )

    mock_lookup = MagicMock()

    async def _run() -> None:
        with patch.object(roll_mod, "_open_new_leg", side_effect=RuntimeError("chain unavailable")):
            with pytest.raises(RuntimeError, match="chain unavailable"):
                await roll_mod._roll_single(
                    mock_broker, store, mock_lookup, open_trade, _ROLL_DATE, dry_run=False
                )

    asyncio.run(_run())

    # After rollback: only the original open trade should exist
    remaining = store.get_trades(_STRATEGY, "overlay_pp")
    assert len(remaining) == 1
    assert remaining[0].action == TradeAction.BUY
    assert remaining[0].price == Decimal("300.00")

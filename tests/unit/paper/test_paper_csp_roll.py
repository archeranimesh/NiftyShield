"""Unit tests for scripts/paper_csp_roll.py.

Coverage:
- Happy path: open CSP leg at DTE 4 -> close + open roundtrip succeeds.
- DTE gate: leg at DTE 6 -> blocked unless --force.
- Rollback: open fails -> delete_trade called on the close record.
- Dry run: no DB writes, output printed.
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

import scripts.paper_csp_roll as roll_mod
from src.models.portfolio import TradeAction
from src.paper.models import PaperTrade
from src.paper.store import PaperStore


# ── Helpers ───────────────────────────────────────────────────────────────────

_STRATEGY = "paper_csp_nifty_v1"
_ROLL_DATE = date(2026, 5, 7)


def _make_store(tmp_path: Path) -> PaperStore:
    return PaperStore(tmp_path / "test.db")


def _make_csp_trade(
    strategy: str = _STRATEGY,
    instrument_key: str = "NSE_FO|NIFTY12MAY2026PE",
    price: Decimal = Decimal("150.00"),
    trade_date: date = date(2026, 4, 1),
    action: TradeAction = TradeAction.SELL,
) -> PaperTrade:
    # Querying PaperTrade snippet shows field names:
    # strategy_name: str, leg_role: str, instrument_key: str, trade_date: date,
    # action: TradeAction, quantity: int, price: Decimal
    return PaperTrade(
        strategy_name=strategy,
        leg_role="short_put",
        instrument_key=instrument_key,
        trade_date=trade_date,
        action=action,
        quantity=65,
        price=price,
    )


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_parse_expiry_from_key() -> None:
    assert roll_mod._parse_expiry_from_key("NSE_FO|NIFTY12MAY2026PE") == date(2026, 5, 12)
    assert roll_mod._parse_expiry_from_key("NSE_FO|NIFTY29MAY2026CE") == date(2026, 5, 29)
    assert roll_mod._parse_expiry_from_key("NSE_EQ|INF204KB14I2") is None


def test_cycle_pnl() -> None:
    existing = _make_csp_trade(price=Decimal("150.00"))
    close = _make_csp_trade(price=Decimal("90.00"), action=TradeAction.BUY)
    # pnl = (150 - 90) * 65 = 60 * 65 = 3900
    assert roll_mod._cycle_pnl(existing, close) == Decimal("3900")


def test_find_expiring_csp_filters_by_dte() -> None:
    # DTE is 5 days from _ROLL_DATE (2026-05-12 - 2026-05-07 = 5)
    trade_dte5 = _make_csp_trade(instrument_key="NSE_FO|NIFTY12MAY2026PE")
    # DTE is 6 days from _ROLL_DATE (2026-05-13 - 2026-05-07 = 6)
    trade_dte6 = _make_csp_trade(instrument_key="NSE_FO|NIFTY13MAY2026PE")

    # DTE 5 qualifies
    assert roll_mod._find_expiring_csp([trade_dte5], _ROLL_DATE) == [trade_dte5]
    # DTE 6 does not qualify by default
    assert roll_mod._find_expiring_csp([trade_dte6], _ROLL_DATE) == []
    # DTE 6 qualifies with force=True
    assert roll_mod._find_expiring_csp([trade_dte6], _ROLL_DATE, force=True) == [trade_dte6]


def test_find_expiring_csp_closed_position() -> None:
    trade_open = _make_csp_trade(action=TradeAction.SELL)
    trade_close = _make_csp_trade(action=TradeAction.BUY)
    # Net position is 0
    assert roll_mod._find_expiring_csp([trade_open, trade_close], _ROLL_DATE) == []


def test_roll_csp_rollback_on_open_failure(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    existing = _make_csp_trade()
    store.record_trade(existing)

    mock_broker = AsyncMock()
    mock_broker.get_ltp = AsyncMock(return_value={existing.instrument_key: Decimal("90.00")})
    mock_lookup = MagicMock()

    async def _run() -> None:
        with patch.object(roll_mod, "_open_new_csp_leg", side_effect=RuntimeError("API Error")):
            with pytest.raises(RuntimeError, match="API Error"):
                await roll_mod._roll_csp(
                    mock_broker, store, mock_lookup, existing, _ROLL_DATE, dry_run=False
                )

    asyncio.run(_run())

    # The close trade should have been deleted (rolled back)
    trades = store.get_trades(_STRATEGY, "short_put")
    assert len(trades) == 1
    assert trades[0].action == TradeAction.SELL


def test_roll_csp_happy_path(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    existing = _make_csp_trade(instrument_key="NSE_FO|NIFTY12MAY2026PE")
    store.record_trade(existing)

    mock_broker = AsyncMock()
    mock_broker.get_ltp = AsyncMock(return_value={existing.instrument_key: Decimal("90.00")})
    
    # Mock get_option_chain
    dummy_chain = [
        {
            "strike_price": 22000.0,
            "underlying_spot_price": 22200.0,
            "put_options": {
                "instrument_key": "NSE_FO|NIFTY28MAY2026PE",
                "option_greeks": {"delta": -0.22, "iv": 15.0},
                "market_data": {"bid_price": 100.0, "ask_price": 102.0, "oi": 5000, "ltp": 101.0},
            }
        }
    ]
    mock_broker.get_option_chain = AsyncMock(return_value=dummy_chain)

    mock_lookup = MagicMock()
    mock_lookup.get_expiry_candidates = MagicMock(return_value=[("monthly", "2026-05-28")])

    async def _run() -> None:
        res = await roll_mod._roll_csp(
            mock_broker, store, mock_lookup, existing, _ROLL_DATE, dry_run=False
        )
        assert res.strategy == _STRATEGY
        assert res.old_instrument_key == "NSE_FO|NIFTY12MAY2026PE"
        assert res.new_instrument_key == "NSE_FO|NIFTY28MAY2026PE"
        assert res.close_price == Decimal("90.00")
        assert res.new_price == Decimal("101.00")
        assert res.cycle_pnl == Decimal("3900")  # (150 - 90) * 65

    asyncio.run(_run())

    # Store should have both close and new open trades
    trades = store.get_trades(_STRATEGY, "short_put")
    assert len(trades) == 3
    assert trades[1].action == TradeAction.BUY
    assert trades[1].price == Decimal("90.00")
    assert trades[2].action == TradeAction.SELL
    assert trades[2].price == Decimal("101.00")
    assert trades[2].instrument_key == "NSE_FO|NIFTY28MAY2026PE"


def test_roll_csp_dry_run(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    existing = _make_csp_trade()
    store.record_trade(existing)

    mock_broker = AsyncMock()
    mock_broker.get_ltp = AsyncMock(return_value={existing.instrument_key: Decimal("90.00")})
    
    dummy_chain = [
        {
            "strike_price": 22000.0,
            "underlying_spot_price": 22200.0,
            "put_options": {
                "instrument_key": "NSE_FO|NIFTY28MAY2026PE",
                "option_greeks": {"delta": -0.22, "iv": 15.0},
                "market_data": {"bid_price": 100.0, "ask_price": 102.0, "oi": 5000, "ltp": 101.0},
            }
        }
    ]
    mock_broker.get_option_chain = AsyncMock(return_value=dummy_chain)

    mock_lookup = MagicMock()
    mock_lookup.get_expiry_candidates = MagicMock(return_value=[("monthly", "2026-05-28")])

    async def _run() -> None:
        res = await roll_mod._roll_csp(
            mock_broker, store, mock_lookup, existing, _ROLL_DATE, dry_run=True
        )
        assert res.strategy == _STRATEGY
        assert res.old_instrument_key == existing.instrument_key

    asyncio.run(_run())

    # Store should only have the original open trade
    trades = store.get_trades(_STRATEGY, "short_put")
    assert len(trades) == 1
    assert trades[0].action == TradeAction.SELL

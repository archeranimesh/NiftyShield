"""Tests for track snapshot reporter."""

import pytest
from datetime import date
from decimal import Decimal

from src.models.portfolio import TradeAction
from src.paper.models import PaperTrade, PaperPosition
from src.paper.track_snapshot import generate_track_snapshot, _compute_realized_pnl_by_leg


class MockPaperStore:
    def __init__(self, trades, positions, snapshots):
        self._trades = trades
        self._positions = positions
        self._snapshots = snapshots
        
    def get_trades(self, strategy_name):
        return [t for t in self._trades if t.strategy_name == strategy_name]
        
    def get_position(self, strategy_name, leg_role):
        for p in self._positions:
            if p.strategy_name == strategy_name and p.leg_role == leg_role:
                return p
        return PaperPosition(strategy_name, leg_role, "", 0, Decimal("0"), Decimal("0"))
        
    def get_nav_snapshots(self, strategy_name):
        return [s for s in self._snapshots if s.strategy_name == strategy_name]


class MockBrokerClient:
    async def get_ltp(self, instrument_keys: list[str]) -> dict[str, float]:
        return {
            "NIFTYBEES": 250.0,
            "NIFTY_FUT": 24000.0,
            "NIFTY_OPT": 100.0
        }


class MockInstrumentLookup:
    def get_by_key(self, instrument_key: str):
        return None


@pytest.mark.asyncio
async def test_generate_track_snapshot_empty():
    store = MockPaperStore([], [], [])
    broker = MockBrokerClient()
    lookup = MockInstrumentLookup()
    
    snap = await generate_track_snapshot(
        store, broker, lookup, "paper_nifty_spot", Decimal("24000"), Decimal("10000"), date.today()
    )
    
    assert snap.pnl.net_pnl == Decimal("0")
    assert snap.greeks.net_delta == Decimal("0")


@pytest.mark.asyncio
async def test_generate_track_snapshot_base_etf():
    trades = [
        PaperTrade(strategy_name="paper_nifty_spot", leg_role="base_etf", instrument_key="NIFTYBEES", trade_date=date.today(), action=TradeAction.BUY, quantity=100, price=Decimal("240.0"), notes="")
    ]
    positions = [
        PaperPosition(strategy_name="paper_nifty_spot", leg_role="base_etf", instrument_key="NIFTYBEES", net_qty=100, avg_cost=Decimal("240.0"), avg_sell_price=Decimal("0"))
    ]
    
    store = MockPaperStore(trades, positions, [])
    broker = MockBrokerClient()
    lookup = MockInstrumentLookup()
    
    snap = await generate_track_snapshot(
        store, broker, lookup, "paper_nifty_spot", Decimal("24000"), Decimal("100000"), date.today()
    )
    
    # PnL = (250 - 240) * 100 = 1000
    assert snap.pnl.base_pnl == Decimal("1000")
    assert snap.pnl.net_pnl == Decimal("1000")
    
    # Delta = 0.92 * 100 = 92.0
    assert snap.greeks.net_delta == Decimal("92.0")
    
    # Return on NEE = 1000 / 100000 = 1.0%
    assert snap.return_on_nee == Decimal("1.0")


def test_compute_realized_pnl_by_leg():
    trades = [
        PaperTrade(strategy_name="paper_strat", leg_role="base", instrument_key="A", trade_date=date(2023,1,1), action=TradeAction.BUY, quantity=100, price=Decimal("100"), notes=""),
        PaperTrade(strategy_name="paper_strat", leg_role="base", instrument_key="A", trade_date=date(2023,1,2), action=TradeAction.SELL, quantity=50, price=Decimal("120"), notes=""),
        PaperTrade(strategy_name="paper_strat", leg_role="overlay", instrument_key="B", trade_date=date(2023,1,1), action=TradeAction.SELL, quantity=50, price=Decimal("50"), notes=""),
        PaperTrade(strategy_name="paper_strat", leg_role="overlay", instrument_key="B", trade_date=date(2023,1,2), action=TradeAction.BUY, quantity=50, price=Decimal("30"), notes="")
    ]
    
    store = MockPaperStore(trades, [], [])
    realized = _compute_realized_pnl_by_leg(store, "paper_strat")
    
    # base: buy 100 @ 100, sell 50 @ 120 -> closed 50. realized = (120 - 100) * 50 = 1000
    assert realized["base"] == Decimal("1000")
    # overlay: sell 50 @ 50, buy 50 @ 30 -> closed 50. realized = (50 - 30) * 50 = 1000
    assert realized["overlay"] == Decimal("1000")

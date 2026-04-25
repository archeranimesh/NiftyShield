"""Unit tests for src/paper/tracker.py.

Uses MockBrokerClient (offline, no network) and a tmp_path SQLite DB.

Coverage:
- compute_pnl: short position profits when LTP falls below avg_cost.
- compute_pnl: short position loses when LTP rises above avg_cost.
- compute_pnl: returns None when strategy has no trades.
- compute_pnl: long position profits when LTP rises above avg_cost.
- compute_pnl: realized_pnl reflects closed round-trips.
- record_daily_snapshot: persists a PaperNavSnapshot with correct P&L.
- record_daily_snapshot: idempotent — re-running same date updates row.
- record_daily_snapshot: returns None for unknown strategy.
- record_all_strategies: snapshots all known strategies.
"""

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from src.client.mock_client import MockBrokerClient
from src.models.portfolio import TradeAction
from src.paper.models import PaperTrade
from src.paper.store import PaperStore
from src.paper.tracker import PaperTracker, _compute_realized_pnl


# ── Fixtures ──────────────────────────────────────────────────────────────────

_STRATEGY = "paper_csp_nifty_v1"
_KEY = "NSE_FO|12345"
_DATE = date(2026, 5, 1)


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "paper_tracker.db"


@pytest.fixture
def store(db_path: Path) -> PaperStore:
    return PaperStore(db_path)


@pytest.fixture
def market() -> MockBrokerClient:
    return MockBrokerClient()


@pytest.fixture
def tracker(store: PaperStore, market: MockBrokerClient) -> PaperTracker:
    return PaperTracker(store, market)


def _sell(qty: int = 75, price: str = "120.00", leg: str = "short_put",
          trade_date: date = _DATE) -> PaperTrade:
    return PaperTrade(
        strategy_name=_STRATEGY,
        leg_role=leg,
        instrument_key=_KEY,
        trade_date=trade_date,
        action=TradeAction.SELL,
        quantity=qty,
        price=Decimal(price),
    )


def _buy(qty: int = 75, price: str = "60.00", leg: str = "short_put",
         trade_date: date = _DATE) -> PaperTrade:
    return PaperTrade(
        strategy_name=_STRATEGY,
        leg_role=leg,
        instrument_key=_KEY,
        trade_date=trade_date,
        action=TradeAction.BUY,
        quantity=qty,
        price=Decimal(price),
    )


# ── compute_pnl ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_compute_pnl_short_profit(
    tracker: PaperTracker, store: PaperStore, market: MockBrokerClient
) -> None:
    """Short put at 120, current LTP 60 → unrealized profit = (120-60)*75."""
    store.record_trade(_sell(qty=75, price="120.00"))
    market.set_price(_KEY, 60.0)
    result = await tracker.compute_pnl(_STRATEGY)
    assert result is not None
    unrealized, realized, total = result
    assert unrealized == Decimal("4500.00")  # (120-60)*75
    assert realized == Decimal("0")
    assert total == Decimal("4500.00")


@pytest.mark.asyncio
async def test_compute_pnl_short_loss(
    tracker: PaperTracker, store: PaperStore, market: MockBrokerClient
) -> None:
    """Short put at 120, current LTP 160 → unrealized loss = (120-160)*75."""
    store.record_trade(_sell(qty=75, price="120.00"))
    market.set_price(_KEY, 160.0)
    result = await tracker.compute_pnl(_STRATEGY)
    assert result is not None
    unrealized, _, _ = result
    assert unrealized == Decimal("-3000.00")  # (120-160)*75


@pytest.mark.asyncio
async def test_compute_pnl_long_profit(
    tracker: PaperTracker, store: PaperStore, market: MockBrokerClient
) -> None:
    """Long position bought at 60, current LTP 90 → unrealized profit."""
    store.record_trade(_buy(qty=75, price="60.00"))
    market.set_price(_KEY, 90.0)
    result = await tracker.compute_pnl(_STRATEGY)
    assert result is not None
    unrealized, _, _ = result
    assert unrealized == Decimal("2250.00")  # (90-60)*75


@pytest.mark.asyncio
async def test_compute_pnl_no_trades_returns_none(
    tracker: PaperTracker,
) -> None:
    result = await tracker.compute_pnl("paper_unknown")
    assert result is None


@pytest.mark.asyncio
async def test_compute_pnl_realized_from_closed_trade(
    tracker: PaperTracker, store: PaperStore, market: MockBrokerClient
) -> None:
    """Open SELL at 120, closed via BUY at 60 → realized = (120-60)*75 = 4500."""
    store.record_trade(_sell(qty=75, price="120.00", trade_date=date(2026, 5, 1)))
    store.record_trade(_buy(qty=75, price="60.00", trade_date=date(2026, 5, 20)))
    # Position is closed, no open instruments to price
    market.set_price(_KEY, 0.0)
    result = await tracker.compute_pnl(_STRATEGY)
    assert result is not None
    _, realized, _ = result
    assert realized == Decimal("4500.00")


# ── record_daily_snapshot ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_record_daily_snapshot_persists(
    tracker: PaperTracker, store: PaperStore, market: MockBrokerClient
) -> None:
    store.record_trade(_sell())
    market.set_price(_KEY, 80.0)
    snap = await tracker.record_daily_snapshot(_STRATEGY, snapshot_date=date(2026, 5, 2))
    assert snap is not None
    assert snap.strategy_name == _STRATEGY
    assert snap.snapshot_date == date(2026, 5, 2)
    assert snap.unrealized_pnl == Decimal("3000.00")  # (120-80)*75


@pytest.mark.asyncio
async def test_record_daily_snapshot_idempotent(
    tracker: PaperTracker, store: PaperStore, market: MockBrokerClient
) -> None:
    store.record_trade(_sell())
    market.set_price(_KEY, 80.0)
    await tracker.record_daily_snapshot(_STRATEGY, snapshot_date=date(2026, 5, 2))
    market.set_price(_KEY, 90.0)
    await tracker.record_daily_snapshot(_STRATEGY, snapshot_date=date(2026, 5, 2))
    snaps = store.get_nav_snapshots(_STRATEGY)
    assert len(snaps) == 1
    # Second run (LTP=90) should overwrite first run (LTP=80)
    assert snaps[0].unrealized_pnl == Decimal("2250.00")  # (120-90)*75


@pytest.mark.asyncio
async def test_record_daily_snapshot_unknown_returns_none(
    tracker: PaperTracker,
) -> None:
    result = await tracker.record_daily_snapshot("paper_unknown")
    assert result is None


@pytest.mark.asyncio
async def test_record_daily_snapshot_underlying_price_stored(
    tracker: PaperTracker, store: PaperStore, market: MockBrokerClient
) -> None:
    store.record_trade(_sell())
    market.set_price(_KEY, 80.0)
    snap = await tracker.record_daily_snapshot(
        _STRATEGY, snapshot_date=date(2026, 5, 2), underlying_price=23500.0
    )
    assert snap is not None
    assert snap.underlying_price == Decimal("23500.0")


# ── record_all_strategies ───────────────────────────────────────���─────────────


@pytest.mark.asyncio
async def test_record_all_strategies(
    tracker: PaperTracker, store: PaperStore, market: MockBrokerClient
) -> None:
    store.record_trade(_sell(leg="short_put"))
    store.record_trade(PaperTrade(
        strategy_name="paper_ic_nifty_v1",
        leg_role="short_call",
        instrument_key="NSE_FO|99999",
        trade_date=_DATE,
        action=TradeAction.SELL,
        quantity=75,
        price=Decimal("80.00"),
    ))
    market.set_price(_KEY, 100.0)
    market.set_price("NSE_FO|99999", 50.0)

    results = await tracker.record_all_strategies(snapshot_date=date(2026, 5, 2))
    assert _STRATEGY in results
    assert "paper_ic_nifty_v1" in results
    assert results[_STRATEGY] is not None
    assert results["paper_ic_nifty_v1"] is not None


# ── _compute_realized_pnl (unit, no async) ────────────────────────────────────


def test_compute_realized_pnl_no_closed_position(store: PaperStore) -> None:
    """Open short position (SELL only) → zero realized P&L."""
    store.record_trade(_sell())
    realized = _compute_realized_pnl(store, _STRATEGY)
    assert realized == Decimal("0")


def test_compute_realized_pnl_empty_strategy(store: PaperStore) -> None:
    realized = _compute_realized_pnl(store, "paper_unknown")
    assert realized == Decimal("0")

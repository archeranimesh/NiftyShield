"""Unit tests for src/paper/store.py.

All tests use a file-based SQLite DB under pytest's tmp_path — not :memory:
because PaperStore opens a new connection per call (same pattern as PortfolioStore).

Coverage:
- record_trade: inserts correctly; all fields round-trip cleanly.
- record_trade: idempotent — duplicate (strategy, leg, date, action) silently ignored.
- record_trade: multiple distinct trades for same strategy each stored.
- get_trades: returns all trades for a strategy ordered by trade_date ASC.
- get_trades: filtered by leg_role returns only matching rows.
- get_trades: returns empty list for unknown strategy.
- get_position: BUY-only net quantity and avg_cost.
- get_position: SELL-only net qty (short opened via SELL).
- get_position: mixed BUY + SELL net quantity.
- get_position: weighted average cost excludes SELL prices.
- get_position: returns zero position for unknown strategy/leg.
- record_nav_snapshot: inserts row; all fields round-trip cleanly.
- record_nav_snapshot: upsert on re-run — updates existing row.
- record_nav_snapshot: underlying_price stored and retrieved as Decimal.
- record_nav_snapshot: underlying_price None survives round-trip.
- get_nav_snapshots: returns multiple snapshots ordered by date ASC.
- get_nav_snapshots: returns empty list for unknown strategy.
- get_latest_nav_snapshot: returns most recent snapshot.
- get_latest_nav_snapshot: returns None when no snapshots exist.
- get_strategy_names: returns distinct sorted strategy names.
- Schema coexistence: paper tables created alongside existing portfolio tables.
"""

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from src.models.portfolio import TradeAction
from src.paper.models import PaperNavSnapshot, PaperTrade
from src.paper.store import PaperStore


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "test_paper.db"


@pytest.fixture
def store(db_path: Path) -> PaperStore:
    return PaperStore(db_path)


# ── Helpers ───────────────────────────────────────────────────────────────────

_STRATEGY = "paper_csp_nifty_v1"
_LEG = "short_put"
_KEY = "NSE_FO|12345"
_DATE = date(2026, 5, 1)


def _sell_trade(**overrides) -> PaperTrade:
    defaults = dict(
        strategy_name=_STRATEGY,
        leg_role=_LEG,
        instrument_key=_KEY,
        trade_date=_DATE,
        action=TradeAction.SELL,
        quantity=75,
        price=Decimal("120.50"),
        notes="entry",
    )
    defaults.update(overrides)
    return PaperTrade(**defaults)


def _buy_trade(**overrides) -> PaperTrade:
    defaults = dict(
        strategy_name=_STRATEGY,
        leg_role=_LEG,
        instrument_key=_KEY,
        trade_date=_DATE,
        action=TradeAction.BUY,
        quantity=75,
        price=Decimal("60.00"),
        notes="exit at 50%",
    )
    defaults.update(overrides)
    return PaperTrade(**defaults)


# ── record_trade ──────────────────────────────────────────────────────────────


def test_record_trade_inserts_row(store: PaperStore) -> None:
    store.record_trade(_sell_trade())
    trades = store.get_trades(_STRATEGY)
    assert len(trades) == 1


def test_record_trade_fields_round_trip(store: PaperStore) -> None:
    original = _sell_trade()
    store.record_trade(original)
    retrieved = store.get_trades(_STRATEGY)[0]
    assert retrieved.strategy_name == original.strategy_name
    assert retrieved.leg_role == original.leg_role
    assert retrieved.instrument_key == original.instrument_key
    assert retrieved.trade_date == original.trade_date
    assert retrieved.action == original.action
    assert retrieved.quantity == original.quantity
    assert retrieved.price == original.price
    assert retrieved.notes == original.notes


def test_record_trade_idempotent(store: PaperStore) -> None:
    t = _sell_trade()
    store.record_trade(t)
    store.record_trade(t)
    store.record_trade(t)
    assert len(store.get_trades(_STRATEGY)) == 1


def test_record_trade_different_legs_both_stored(store: PaperStore) -> None:
    store.record_trade(_sell_trade(leg_role="short_put"))
    store.record_trade(_sell_trade(leg_role="short_call", instrument_key="NSE_FO|99999"))
    assert len(store.get_trades(_STRATEGY)) == 2


# ── get_trades ────────────────────────────────────────────────────────────────


def test_get_trades_ordered_by_date(store: PaperStore) -> None:
    store.record_trade(_sell_trade(trade_date=date(2026, 6, 1)))
    store.record_trade(_buy_trade(trade_date=date(2026, 5, 1)))
    trades = store.get_trades(_STRATEGY)
    assert trades[0].trade_date < trades[1].trade_date


def test_get_trades_filter_by_leg(store: PaperStore) -> None:
    store.record_trade(_sell_trade(leg_role="short_put"))
    store.record_trade(_sell_trade(leg_role="short_call", instrument_key="NSE_FO|99999"))
    puts = store.get_trades(_STRATEGY, leg_role="short_put")
    assert len(puts) == 1
    assert puts[0].leg_role == "short_put"


def test_get_trades_unknown_strategy_returns_empty(store: PaperStore) -> None:
    assert store.get_trades("paper_unknown") == []


# ── get_position ──────────────────────────────────────────────────────────────


def test_get_position_sell_only(store: PaperStore) -> None:
    store.record_trade(_sell_trade(quantity=75, price=Decimal("120.50")))
    pos = store.get_position(_STRATEGY, _LEG)
    assert pos.net_qty == -75
    assert pos.avg_cost == Decimal("0")  # no BUYs
    assert pos.avg_sell_price == Decimal("120.50")


def test_get_position_buy_only(store: PaperStore) -> None:
    store.record_trade(_buy_trade(quantity=75, price=Decimal("60.00")))
    pos = store.get_position(_STRATEGY, _LEG)
    assert pos.net_qty == 75
    assert pos.avg_cost == Decimal("60.00")


def test_get_position_buy_then_sell_net(store: PaperStore) -> None:
    store.record_trade(_buy_trade(trade_date=date(2026, 5, 1)))
    store.record_trade(_sell_trade(trade_date=date(2026, 5, 20)))
    pos = store.get_position(_STRATEGY, _LEG)
    assert pos.net_qty == 0


def test_get_position_weighted_avg_cost(store: PaperStore) -> None:
    store.record_trade(_buy_trade(trade_date=date(2026, 5, 1), quantity=50, price=Decimal("100")))
    store.record_trade(_buy_trade(trade_date=date(2026, 5, 2), quantity=50, price=Decimal("120"),
                                  action=TradeAction.BUY))
    pos = store.get_position(_STRATEGY, _LEG)
    assert pos.net_qty == 100
    # (50*100 + 50*120) / 100 = 110
    assert pos.avg_cost == Decimal("110")


def test_get_position_unknown_returns_zero(store: PaperStore) -> None:
    pos = store.get_position("paper_unknown", "missing_leg")
    assert pos.net_qty == 0
    assert pos.avg_cost == Decimal("0")
    assert pos.avg_sell_price == Decimal("0")
    assert pos.instrument_key == ""


# ── record_nav_snapshot ───────────────────────────────────────────────────────


def _snap(**overrides) -> PaperNavSnapshot:
    defaults = dict(
        strategy_name=_STRATEGY,
        snapshot_date=date(2026, 5, 1),
        unrealized_pnl=Decimal("500.00"),
        realized_pnl=Decimal("250.00"),
        total_pnl=Decimal("750.00"),
        underlying_price=Decimal("23500.00"),
    )
    defaults.update(overrides)
    return PaperNavSnapshot(**defaults)


def test_record_nav_snapshot_inserts(store: PaperStore) -> None:
    store.record_nav_snapshot(_snap())
    snaps = store.get_nav_snapshots(_STRATEGY)
    assert len(snaps) == 1


def test_record_nav_snapshot_fields_round_trip(store: PaperStore) -> None:
    original = _snap()
    store.record_nav_snapshot(original)
    retrieved = store.get_nav_snapshots(_STRATEGY)[0]
    assert retrieved.strategy_name == original.strategy_name
    assert retrieved.snapshot_date == original.snapshot_date
    assert retrieved.unrealized_pnl == original.unrealized_pnl
    assert retrieved.realized_pnl == original.realized_pnl
    assert retrieved.total_pnl == original.total_pnl
    assert retrieved.underlying_price == original.underlying_price


def test_record_nav_snapshot_upsert_updates(store: PaperStore) -> None:
    store.record_nav_snapshot(_snap(unrealized_pnl=Decimal("100")))
    store.record_nav_snapshot(_snap(unrealized_pnl=Decimal("999")))
    snaps = store.get_nav_snapshots(_STRATEGY)
    assert len(snaps) == 1
    assert snaps[0].unrealized_pnl == Decimal("999")


def test_record_nav_snapshot_underlying_price_none(store: PaperStore) -> None:
    store.record_nav_snapshot(_snap(underlying_price=None))
    retrieved = store.get_nav_snapshots(_STRATEGY)[0]
    assert retrieved.underlying_price is None


def test_record_nav_snapshot_decimal_precision(store: PaperStore) -> None:
    store.record_nav_snapshot(_snap(unrealized_pnl=Decimal("123.456789")))
    retrieved = store.get_nav_snapshots(_STRATEGY)[0]
    assert retrieved.unrealized_pnl == Decimal("123.456789")


# ── get_nav_snapshots ─────────────────────────────────────────────────────────


def test_get_nav_snapshots_ordered_asc(store: PaperStore) -> None:
    store.record_nav_snapshot(_snap(snapshot_date=date(2026, 6, 1)))
    store.record_nav_snapshot(_snap(snapshot_date=date(2026, 5, 1)))
    snaps = store.get_nav_snapshots(_STRATEGY)
    assert snaps[0].snapshot_date < snaps[1].snapshot_date


def test_get_nav_snapshots_unknown_returns_empty(store: PaperStore) -> None:
    assert store.get_nav_snapshots("paper_unknown") == []


# ── get_latest_nav_snapshot ───────────────────────────────────────────────────


def test_get_latest_nav_snapshot_returns_most_recent(store: PaperStore) -> None:
    store.record_nav_snapshot(_snap(snapshot_date=date(2026, 5, 1)))
    store.record_nav_snapshot(_snap(snapshot_date=date(2026, 6, 1)))
    latest = store.get_latest_nav_snapshot(_STRATEGY)
    assert latest is not None
    assert latest.snapshot_date == date(2026, 6, 1)


def test_get_latest_nav_snapshot_none_when_empty(store: PaperStore) -> None:
    assert store.get_latest_nav_snapshot("paper_unknown") is None


# ── get_strategy_names ────────────────────────────────────────────────────────


def test_get_strategy_names_returns_distinct_sorted(store: PaperStore) -> None:
    store.record_trade(_sell_trade(strategy_name="paper_ic_nifty_v1"))
    store.record_trade(_sell_trade(strategy_name="paper_csp_nifty_v1"))
    store.record_trade(_sell_trade(strategy_name="paper_csp_nifty_v1",
                                   trade_date=date(2026, 6, 1)))
    names = store.get_strategy_names()
    assert names == ["paper_csp_nifty_v1", "paper_ic_nifty_v1"]


def test_get_strategy_names_empty(store: PaperStore) -> None:
    assert store.get_strategy_names() == []


# ── Schema coexistence ────────────────────────────────────────────────────────


def test_paper_tables_coexist_with_portfolio_tables(db_path: Path) -> None:
    """Paper tables can be created in a DB that already has portfolio tables."""
    from src.portfolio.store import PortfolioStore

    # Create live portfolio schema first
    PortfolioStore(db_path)
    # Now create paper schema in the same DB — must not raise
    ps = PaperStore(db_path)
    ps.record_trade(_sell_trade())
    assert len(ps.get_trades(_STRATEGY)) == 1

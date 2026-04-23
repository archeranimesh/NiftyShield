"""Unit tests for trade ledger methods in src/portfolio/store.py.

All tests use a file-based SQLite DB under pytest's tmp_path — not :memory:
because PortfolioStore._connect() opens a new connection per call.

Coverage:
- record_trade: inserts correctly, all fields round-trip cleanly.
- record_trade: idempotency — duplicate (strategy, leg, date, action) silently ignored.
- get_trades: returns all trades for a strategy.
- get_trades: filters correctly by leg_role.
- get_trades: returns in trade_date ASC order.
- get_position: BUY-only net quantity.
- get_position: SELL-only net quantity (short).
- get_position: mixed BUY+SELL net quantity.
- get_position: weighted average buy price (ignores SELL price).
- get_position: returns (0, Decimal("0")) for unknown strategy/leg.
- get_position: multiple BUYs at different prices — correct weighted average.
- Schema coexistence: trades table created alongside existing tables.
"""

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from src.models.portfolio import Trade, TradeAction
from src.portfolio.store import PortfolioStore


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "test_portfolio.db"


@pytest.fixture
def store(db_path: Path) -> PortfolioStore:
    return PortfolioStore(db_path)


def _buy(
    strategy: str = "ILTS",
    leg: str = "EBBETF0431",
    key: str = "NSE_EQ|INF754K01LE1",
    trade_date: date = date(2026, 1, 15),
    qty: int = 438,
    price: str = "1388.12",
    notes: str = "",
) -> Trade:
    return Trade(
        strategy_name=strategy,
        leg_role=leg,
        instrument_key=key,
        trade_date=trade_date,
        action=TradeAction.BUY,
        quantity=qty,
        price=Decimal(price),
        notes=notes,
    )


def _sell(
    strategy: str = "ILTS",
    leg: str = "NIFTY_JUN_PE",
    key: str = "NSE_FO|37805",
    trade_date: date = date(2026, 1, 15),
    qty: int = 65,
    price: str = "840.00",
) -> Trade:
    return Trade(
        strategy_name=strategy,
        leg_role=leg,
        instrument_key=key,
        trade_date=trade_date,
        action=TradeAction.SELL,
        quantity=qty,
        price=Decimal(price),
    )


# ── Schema coexistence ─────────────────────────────────────────────────────────


def test_trades_table_exists(store: PortfolioStore, db_path: Path) -> None:
    """trades table must be created alongside strategies, legs, daily_snapshots."""
    import sqlite3

    conn = sqlite3.connect(str(db_path))
    tables = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    conn.close()
    assert "trades" in tables
    assert "strategies" in tables
    assert "daily_snapshots" in tables


def test_trades_schema_columns(store: PortfolioStore, db_path: Path) -> None:
    """trades table must have all required columns."""
    import sqlite3

    conn = sqlite3.connect(str(db_path))
    cols = {row[1] for row in conn.execute("PRAGMA table_info(trades)").fetchall()}
    conn.close()
    expected = {
        "id", "strategy_name", "leg_role", "instrument_key",
        "trade_date", "action", "quantity", "price", "notes",
    }
    assert expected.issubset(cols)


# ── record_trade ──────────────────────────────────────────────────────────────


def test_record_trade_inserts_row(store: PortfolioStore, db_path: Path) -> None:
    store.record_trade(_buy())
    trades = store.get_trades("ILTS")
    assert len(trades) == 1


def test_record_trade_fields_round_trip(store: PortfolioStore) -> None:
    original = _buy(notes="contract note ref")
    store.record_trade(original)
    retrieved = store.get_trades("ILTS")[0]
    assert retrieved.strategy_name == "ILTS"
    assert retrieved.leg_role == "EBBETF0431"
    assert retrieved.instrument_key == "NSE_EQ|INF754K01LE1"
    assert retrieved.trade_date == date(2026, 1, 15)
    assert retrieved.action == TradeAction.BUY
    assert retrieved.quantity == 438
    assert retrieved.price == Decimal("1388.12")
    assert retrieved.notes == "contract note ref"


def test_record_trade_idempotent_exact_duplicate(store: PortfolioStore) -> None:
    """Inserting the same trade twice must leave exactly one row."""
    t = _buy()
    store.record_trade(t)
    store.record_trade(t)
    assert len(store.get_trades("ILTS")) == 1


def test_record_trade_idempotent_three_times(store: PortfolioStore) -> None:
    t = _buy()
    store.record_trade(t)
    store.record_trade(t)
    store.record_trade(t)
    assert len(store.get_trades("ILTS")) == 1


def test_record_trade_different_dates_both_inserted(store: PortfolioStore) -> None:
    """Same leg, different dates → two separate rows (not duplicates)."""
    t1 = _buy(trade_date=date(2026, 1, 15), qty=438, price="1388.12")
    t2 = _buy(trade_date=date(2026, 4, 8), qty=27, price="1386.20")
    store.record_trade(t1)
    store.record_trade(t2)
    assert len(store.get_trades("ILTS")) == 2


# ── get_trades ────────────────────────────────────────────────────────────────


def test_get_trades_filters_by_strategy(store: PortfolioStore) -> None:
    store.record_trade(_buy(strategy="ILTS"))
    store.record_trade(_buy(strategy="FinRakshak", leg="NIFTY_DEC_PE", key="NSE_FO|37810"))
    assert len(store.get_trades("ILTS")) == 1
    assert len(store.get_trades("FinRakshak")) == 1


def test_get_trades_filters_by_leg_role(store: PortfolioStore) -> None:
    store.record_trade(_buy(leg="EBBETF0431"))
    store.record_trade(_buy(leg="LIQUIDBEES", key="NSE_EQ|INF204KA1983", price="1000.00"))
    result = store.get_trades("ILTS", leg_role="EBBETF0431")
    assert len(result) == 1
    assert result[0].leg_role == "EBBETF0431"


def test_get_trades_leg_role_none_returns_all(store: PortfolioStore) -> None:
    store.record_trade(_buy(leg="EBBETF0431"))
    store.record_trade(_buy(leg="LIQUIDBEES", key="NSE_EQ|INF204KA1983", price="1000.00"))
    assert len(store.get_trades("ILTS")) == 2


def test_get_trades_ordered_by_date_asc(store: PortfolioStore) -> None:
    store.record_trade(_buy(trade_date=date(2026, 4, 8), qty=27, price="1386.20"))
    store.record_trade(_buy(trade_date=date(2026, 1, 15), qty=438, price="1388.12"))
    trades = store.get_trades("ILTS", leg_role="EBBETF0431")
    assert trades[0].trade_date == date(2026, 1, 15)
    assert trades[1].trade_date == date(2026, 4, 8)


def test_get_trades_unknown_strategy_returns_empty(store: PortfolioStore) -> None:
    assert store.get_trades("UNKNOWN") == []


# ── get_position ──────────────────────────────────────────────────────────────


def test_get_position_unknown_leg_returns_zero(store: PortfolioStore) -> None:
    qty, avg = store.get_position("ILTS", "EBBETF0431")
    assert qty == 0
    assert avg == Decimal("0")


def test_get_position_buy_only_net_quantity(store: PortfolioStore) -> None:
    store.record_trade(_buy(qty=438))
    qty, _ = store.get_position("ILTS", "EBBETF0431")
    assert qty == 438


def test_get_position_sell_only_net_quantity(store: PortfolioStore) -> None:
    """Short position — only SELL trades, no BUY."""
    store.record_trade(_sell(qty=65))
    qty, avg = store.get_position("ILTS", "NIFTY_JUN_PE")
    assert qty == -65
    assert avg == Decimal("0")  # no buy trades → avg is zero


def test_get_position_mixed_buy_sell_net(store: PortfolioStore) -> None:
    """BUY 100, SELL 30 → net 70."""
    store.record_trade(
        Trade(
            strategy_name="ILTS", leg_role="EBBETF0431",
            instrument_key="NSE_EQ|INF754K01LE1",
            trade_date=date(2026, 1, 15), action=TradeAction.BUY,
            quantity=100, price=Decimal("1388.00"),
        )
    )
    store.record_trade(
        Trade(
            strategy_name="ILTS", leg_role="EBBETF0431",
            instrument_key="NSE_EQ|INF754K01LE1",
            trade_date=date(2026, 2, 1), action=TradeAction.SELL,
            quantity=30, price=Decimal("1400.00"),
        )
    )
    qty, _ = store.get_position("ILTS", "EBBETF0431")
    assert qty == 70


def test_get_position_avg_price_single_buy(store: PortfolioStore) -> None:
    store.record_trade(_buy(qty=438, price="1388.12"))
    _, avg = store.get_position("ILTS", "EBBETF0431")
    assert avg == Decimal("1388.12")


def test_get_position_avg_price_two_buys_weighted(store: PortfolioStore) -> None:
    """Weighted average: (438*1388.12 + 27*1386.20) / 465."""
    store.record_trade(_buy(trade_date=date(2026, 1, 15), qty=438, price="1388.12"))
    store.record_trade(_buy(trade_date=date(2026, 4, 8), qty=27, price="1386.20"))
    _, avg = store.get_position("ILTS", "EBBETF0431")
    expected = (
        Decimal("438") * Decimal("1388.12") + Decimal("27") * Decimal("1386.20")
    ) / Decimal("465")
    assert avg == expected


def test_get_position_avg_price_ignores_sell_price(store: PortfolioStore) -> None:
    """Sell price must not affect the average buy price calculation."""
    store.record_trade(_buy(leg="EBBETF0431", qty=100, price="1388.00"))
    store.record_trade(
        Trade(
            strategy_name="ILTS", leg_role="EBBETF0431",
            instrument_key="NSE_EQ|INF754K01LE1",
            trade_date=date(2026, 2, 1), action=TradeAction.SELL,
            quantity=30, price=Decimal("9999.00"),  # artificially high — must be ignored
        )
    )
    _, avg = store.get_position("ILTS", "EBBETF0431")
    assert avg == Decimal("1388.00")


def test_get_position_sell_only_avg_price_is_zero(store: PortfolioStore) -> None:
    """No BUY trades → avg price is Decimal('0'), not an error."""
    store.record_trade(_sell(qty=65, price="840.00"))
    _, avg = store.get_position("ILTS", "NIFTY_JUN_PE")
    assert avg == Decimal("0")


# ── get_all_positions_for_strategy ────────────────────────────────────────────


def test_get_all_positions_empty_when_no_trades(store: PortfolioStore) -> None:
    """Returns empty dict when strategy has no trades at all."""
    result = store.get_all_positions_for_strategy("ILTS")
    assert result == {}


def test_get_all_positions_single_leg(store: PortfolioStore) -> None:
    """Single leg BUY — returns correct net qty, avg price, and instrument_key."""
    store.record_trade(_buy(qty=438, price="1388.12"))
    result = store.get_all_positions_for_strategy("ILTS")
    assert "EBBETF0431" in result
    net_qty, avg_price, key = result["EBBETF0431"]
    assert net_qty == 438
    assert avg_price == Decimal("1388.12")
    assert key == "NSE_EQ|INF754K01LE1"


def test_get_all_positions_multiple_legs(store: PortfolioStore) -> None:
    """Multiple legs returned — one BUY equity, one SELL option."""
    store.record_trade(_buy(qty=438, price="1388.12"))
    store.record_trade(_sell(qty=65, price="840.00"))
    result = store.get_all_positions_for_strategy("ILTS")
    assert set(result.keys()) == {"EBBETF0431", "NIFTY_JUN_PE"}
    assert result["EBBETF0431"][0] == 438
    assert result["NIFTY_JUN_PE"][0] == -65


def test_get_all_positions_accumulates_multiple_buys(store: PortfolioStore) -> None:
    """Two BUY trades for same leg on different dates → correct net qty and weighted avg."""
    store.record_trade(_buy(qty=438, price="1388.12", trade_date=date(2026, 1, 15)))
    store.record_trade(_buy(qty=27, price="1386.20", trade_date=date(2026, 4, 8)))
    result = store.get_all_positions_for_strategy("ILTS")
    net_qty, avg_price, _ = result["EBBETF0431"]
    assert net_qty == 465
    # Weighted avg: (438*1388.12 + 27*1386.20) / 465
    expected = (Decimal("438") * Decimal("1388.12") + Decimal("27") * Decimal("1386.20")) / Decimal("465")
    assert avg_price == expected


def test_get_all_positions_instrument_key_from_trades(store: PortfolioStore) -> None:
    """instrument_key in result comes from the trades table, not from Leg definitions."""
    store.record_trade(
        Trade(
            strategy_name="ILTS", leg_role="LIQUIDBEES",
            instrument_key="NSE_EQ|INF732E01037",
            trade_date=date(2026, 4, 8), action=TradeAction.BUY,
            quantity=22, price=Decimal("1000.00"),
        )
    )
    result = store.get_all_positions_for_strategy("ILTS")
    assert "LIQUIDBEES" in result
    assert result["LIQUIDBEES"][2] == "NSE_EQ|INF732E01037"


def test_get_all_positions_isolates_by_strategy(store: PortfolioStore) -> None:
    """ILTS trades do not appear in FinRakshak results and vice versa."""
    store.record_trade(_buy(strategy="ILTS", leg="EBBETF0431", qty=438))
    store.record_trade(
        Trade(
            strategy_name="FinRakshak", leg_role="NIFTY_DEC_PE",
            instrument_key="NSE_FO|37810",
            trade_date=date(2026, 1, 15), action=TradeAction.BUY,
            quantity=65, price=Decimal("962.15"),
        )
    )
    ilts = store.get_all_positions_for_strategy("ILTS")
    fr = store.get_all_positions_for_strategy("FinRakshak")
    assert "EBBETF0431" in ilts
    assert "EBBETF0431" not in fr
    assert "NIFTY_DEC_PE" in fr
    assert "NIFTY_DEC_PE" not in ilts


def test_get_all_positions_single_connection(store: PortfolioStore) -> None:
    """Must only open a single database connection for the entire operation, avoiding N+1."""
    import src.portfolio.store as store_mod
    from unittest.mock import patch
    
    store.record_trade(_buy(strategy="ILTS", leg="L1"))
    store.record_trade(_buy(strategy="ILTS", leg="L2"))
    store.record_trade(_buy(strategy="ILTS", leg="L3"))
    
    with patch.object(store_mod, "_connect", wraps=store_mod._connect) as spy:
        result = store.get_all_positions_for_strategy("ILTS")
        
        assert len(result) == 3
        assert spy.call_count == 1


# ── record_roll ───────────────────────────────────────────────────────────────


def _close_trade(
    strategy: str = "finideas_ilts",
    leg: str = "NIFTY_MAY_PE_ATM",
    key: str = "NSE_FO|12345",
    trade_date: date = date(2026, 6, 20),
    qty: int = 50,
    price: str = "45.00",
) -> Trade:
    """BUY-to-close an existing short option leg."""
    return Trade(
        strategy_name=strategy,
        leg_role=leg,
        instrument_key=key,
        trade_date=trade_date,
        action=TradeAction.BUY,
        quantity=qty,
        price=Decimal(price),
    )


def _open_trade(
    strategy: str = "finideas_ilts",
    leg: str = "NIFTY_JUN_PE_ATM",
    key: str = "NSE_FO|67890",
    trade_date: date = date(2026, 6, 20),
    qty: int = 50,
    price: str = "85.00",
) -> Trade:
    """SELL-to-open a new short option leg."""
    return Trade(
        strategy_name=strategy,
        leg_role=leg,
        instrument_key=key,
        trade_date=trade_date,
        action=TradeAction.SELL,
        quantity=qty,
        price=Decimal(price),
    )


def test_record_roll_both_trades_inserted(store: PortfolioStore) -> None:
    """Happy path: close + open trade both appear in the ledger."""
    store.record_roll(_close_trade(), _open_trade())
    close_rows = store.get_trades("finideas_ilts", leg_role="NIFTY_MAY_PE_ATM")
    open_rows = store.get_trades("finideas_ilts", leg_role="NIFTY_JUN_PE_ATM")
    assert len(close_rows) == 1
    assert len(open_rows) == 1
    assert close_rows[0].action == TradeAction.BUY
    assert close_rows[0].price == Decimal("45.00")
    assert open_rows[0].action == TradeAction.SELL
    assert open_rows[0].price == Decimal("85.00")


def test_record_roll_is_idempotent(store: PortfolioStore) -> None:
    """Calling record_roll twice leaves exactly 2 rows — no duplicates."""
    store.record_roll(_close_trade(), _open_trade())
    store.record_roll(_close_trade(), _open_trade())
    all_trades = store.get_trades("finideas_ilts")
    assert len(all_trades) == 2


def test_record_roll_partial_duplicate_still_inserts_missing_leg(
    store: PortfolioStore,
) -> None:
    """If close trade already exists, record_roll still inserts the open trade."""
    store.record_trade(_close_trade())  # pre-insert the close side
    store.record_roll(_close_trade(), _open_trade())
    assert len(store.get_trades("finideas_ilts", leg_role="NIFTY_MAY_PE_ATM")) == 1
    assert len(store.get_trades("finideas_ilts", leg_role="NIFTY_JUN_PE_ATM")) == 1


def test_record_roll_positions_reflect_both_legs(store: PortfolioStore) -> None:
    """After a roll: old leg shows net +50 (BUY to close a prior short),
    new leg shows net -50 (SELL to open)."""
    store.record_roll(_close_trade(), _open_trade())
    old_qty, _ = store.get_position("finideas_ilts", "NIFTY_MAY_PE_ATM")
    new_qty, _ = store.get_position("finideas_ilts", "NIFTY_JUN_PE_ATM")
    assert old_qty == 50   # BUY 50 → net +50
    assert new_qty == -50  # SELL 50 → net -50

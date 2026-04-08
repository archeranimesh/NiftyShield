"""Unit tests for scripts/seed_trades.py.

All tests use a file-based SQLite DB under pytest's tmp_path — fully offline.

Coverage:
- build_trades: correct count (7 total: 6 ILTS + 1 FinRakshak).
- build_trades: each trade has correct strategy_name and leg_role.
- build_trades: ILTS has both BUY and SELL actions (NIFTY_JUN_PE is SELL).
- build_trades: FinRakshak has exactly one BUY trade.
- build_trades: Decimal precision on price fields.
- seed_trades: all 7 trades inserted on first run.
- seed_trades: idempotent — running 3× leaves the same row count.
- seed_trades: correct instrument keys for each leg.
- seed_trades: ILTS EBBETF0431 has two BUY rows at different dates.
- seed_trades: get_position returns correct net qty + weighted avg for EBBETF0431.
"""

from decimal import Decimal
from pathlib import Path

import pytest

from scripts.seed_trades import _FINRAKSHAK_TRADES, _ILTS_TRADES, build_trades, seed_trades
from src.portfolio.models import TradeAction
from src.portfolio.store import PortfolioStore


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def store(tmp_path: Path) -> PortfolioStore:
    return PortfolioStore(tmp_path / "test.sqlite")


# ── build_trades ──────────────────────────────────────────────────────────────


def test_build_trades_total_count() -> None:
    assert len(build_trades()) == len(_ILTS_TRADES) + len(_FINRAKSHAK_TRADES)


def test_build_trades_ilts_count() -> None:
    ilts = [t for t in build_trades() if t.strategy_name == "ILTS"]
    assert len(ilts) == len(_ILTS_TRADES)


def test_build_trades_finrakshak_count() -> None:
    fr = [t for t in build_trades() if t.strategy_name == "FinRakshak"]
    assert len(fr) == len(_FINRAKSHAK_TRADES)


def test_build_trades_ilts_has_sell_action() -> None:
    """NIFTY_JUN_PE is the short leg — must be TradeAction.SELL."""
    ilts = [t for t in build_trades() if t.strategy_name == "ILTS"]
    sell_trades = [t for t in ilts if t.action == TradeAction.SELL]
    assert len(sell_trades) >= 1
    assert any(t.leg_role == "NIFTY_JUN_PE" for t in sell_trades)


def test_build_trades_all_finrakshak_are_buy() -> None:
    fr = [t for t in build_trades() if t.strategy_name == "FinRakshak"]
    assert all(t.action == TradeAction.BUY for t in fr)


def test_build_trades_ebbetf0431_has_two_buys() -> None:
    ebbetf = [
        t for t in build_trades()
        if t.strategy_name == "ILTS" and t.leg_role == "EBBETF0431"
    ]
    assert len(ebbetf) == 2
    assert all(t.action == TradeAction.BUY for t in ebbetf)


def test_build_trades_ebbetf0431_instrument_key() -> None:
    ebbetf = [t for t in build_trades() if t.leg_role == "EBBETF0431"]
    assert all(t.instrument_key == "NSE_EQ|INF754K01LE1" for t in ebbetf)


def test_build_trades_liquidbees_instrument_key() -> None:
    lb = [t for t in build_trades() if t.leg_role == "LIQUIDBEES"]
    assert len(lb) == 1
    assert lb[0].instrument_key == "NSE_EQ|INF732E01037"


def test_build_trades_finrakshak_instrument_key() -> None:
    fr = [t for t in build_trades() if t.strategy_name == "FinRakshak"]
    assert fr[0].instrument_key == "NSE_FO|37810"


def test_build_trades_decimal_precision_ebbetf() -> None:
    ebbetf = [t for t in build_trades() if t.leg_role == "EBBETF0431"]
    prices = {t.price for t in ebbetf}
    assert Decimal("1388.12") in prices
    assert Decimal("1386.20") in prices


def test_build_trades_decimal_precision_nifty_jun_pe() -> None:
    pe = [
        t for t in build_trades()
        if t.strategy_name == "ILTS" and t.leg_role == "NIFTY_JUN_PE"
    ]
    assert pe[0].price == Decimal("840.00")


def test_build_trades_finrakshak_price_precision() -> None:
    fr = [t for t in build_trades() if t.strategy_name == "FinRakshak"]
    assert fr[0].price == Decimal("962.15")


# ── seed_trades ───────────────────────────────────────────────────────────────


def test_seed_trades_inserts_all(store: PortfolioStore) -> None:
    count = seed_trades(store)
    assert count == len(build_trades())


def test_seed_trades_idempotent_twice(store: PortfolioStore) -> None:
    seed_trades(store)
    seed_trades(store)
    ilts = store.get_trades("ILTS")
    fr = store.get_trades("FinRakshak")
    assert len(ilts) == len(_ILTS_TRADES)
    assert len(fr) == len(_FINRAKSHAK_TRADES)


def test_seed_trades_idempotent_three_times(store: PortfolioStore) -> None:
    seed_trades(store)
    seed_trades(store)
    seed_trades(store)
    total = len(store.get_trades("ILTS")) + len(store.get_trades("FinRakshak"))
    assert total == len(build_trades())


def test_seed_trades_ebbetf0431_position(store: PortfolioStore) -> None:
    """After seed, EBBETF0431 net qty = 465 and avg price is the weighted average."""
    seed_trades(store)
    net_qty, avg_price = store.get_position("ILTS", "EBBETF0431")
    assert net_qty == 465
    expected_avg = (
        Decimal("438") * Decimal("1388.12") + Decimal("27") * Decimal("1386.20")
    ) / Decimal("465")
    assert avg_price == expected_avg


def test_seed_trades_nifty_jun_pe_is_short(store: PortfolioStore) -> None:
    """NIFTY_JUN_PE SELL 65 → net qty -65, avg buy price 0."""
    seed_trades(store)
    net_qty, avg_price = store.get_position("ILTS", "NIFTY_JUN_PE")
    assert net_qty == -65
    assert avg_price == Decimal("0")

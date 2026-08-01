"""S5 — automated base-leg roll tests (Futures/DITM).

See docs/plan/3track-consolidation/stories.md S5 for the confirmed decision log
(per-leg DTE thresholds, warn-only liquidity gates, atomic close+open persistence).
"""

from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

import scripts.strategies.three_track.paper_3track_roll as roll_mod
from src.instruments.lookup import InstrumentLookup
from src.paper.models import PaperPosition
from src.paper.store import PaperStore
from src.strategy.nifty_track_comparison_v1 import NiftyTrackComparisonV1


def _make_store(tmp_path: Path) -> PaperStore:
    return PaperStore(tmp_path / "test.db")


# ── Trigger threshold tests ─────────────────────────────────────────────────


def test_futures_roll_triggers_at_dte_1() -> None:
    assert roll_mod.should_roll_futures(1) is True
    assert roll_mod.should_roll_futures(0) is True


def test_futures_roll_does_not_trigger_above_dte_1() -> None:
    assert roll_mod.should_roll_futures(2) is False
    assert roll_mod.should_roll_futures(5) is False


def test_ditm_roll_triggers_at_dte_20() -> None:
    # DTE < 20 rolls — 19 is the first triggering value, 20 does not trigger.
    assert roll_mod.should_roll_ditm(19) is True
    assert roll_mod.should_roll_ditm(0) is True


def test_ditm_roll_does_not_trigger_above_dte_20() -> None:
    assert roll_mod.should_roll_ditm(20) is False
    assert roll_mod.should_roll_ditm(25) is False


def test_futures_and_ditm_use_independent_trigger_thresholds() -> None:
    """Regression guard: the two legs' DTE thresholds must never be unified."""
    dte = 5
    assert roll_mod.should_roll_futures(dte) is False
    assert roll_mod.should_roll_ditm(dte) is True
    assert roll_mod.FUTURES_ROLL_DTE != roll_mod.DITM_ROLL_DTE


# ── Liquidity gate tests (warn-only, never blocking) ────────────────────────


def test_futures_relative_oi_gate_warns_not_blocks() -> None:
    # Below 10% of near-month OI -> gate fails (caller still rolls; gate is diagnostic).
    assert roll_mod.check_futures_liquidity_gate(next_oi=500, near_oi=10_000) is False
    # At/above threshold -> gate passes.
    assert roll_mod.check_futures_liquidity_gate(next_oi=1_000, near_oi=10_000) is True
    # Missing data -> treated as a failure, never raises.
    assert roll_mod.check_futures_liquidity_gate(next_oi=None, near_oi=10_000) is False
    assert roll_mod.check_futures_liquidity_gate(next_oi=100, near_oi=0) is False


def test_ditm_liquidity_gate_reuses_existing_constants() -> None:
    from scripts.strategies.three_track.paper_3track_entry import (
        PROXY_OI_MIN,
        PROXY_SPREAD_MAX,
    )

    assert roll_mod.PROXY_OI_MIN == PROXY_OI_MIN
    assert roll_mod.PROXY_SPREAD_MAX == PROXY_SPREAD_MAX

    # Passes: OI at minimum, spread within max.
    assert roll_mod.check_ditm_liquidity_gate(oi=PROXY_OI_MIN, bid=100.0, ask=101.0) is True
    # Fails: OI below minimum.
    assert roll_mod.check_ditm_liquidity_gate(oi=PROXY_OI_MIN - 1, bid=100.0, ask=101.0) is False
    # Fails: spread above max.
    assert (
        roll_mod.check_ditm_liquidity_gate(
            oi=PROXY_OI_MIN, bid=100.0, ask=100.0 + PROXY_SPREAD_MAX + 1
        )
        is False
    )


# ── Atomic persistence tests ─────────────────────────────────────────────────


def _futures_lookup() -> InstrumentLookup:
    return InstrumentLookup(
        [
            {
                "instrument_key": "NSE_FO|NIFTY26JULFUT",
                "underlying_symbol": "NIFTY",
                "instrument_type": "FUT",
                "expiry": "2026-07-30",
                "trading_symbol": "NIFTY JUL FUT",
            },
            {
                "instrument_key": "NSE_FO|NIFTY26AUGFUT",
                "underlying_symbol": "NIFTY",
                "instrument_type": "FUT",
                "expiry": "2026-08-27",
                "trading_symbol": "NIFTY AUG FUT",
            },
        ]
    )


def _seed_entry_trade(store: PaperStore) -> None:
    """Seed the original entry BUY so get_positions() nets correctly after a roll.

    Mirrors production reality: paper_3track_entry.py always records the opening
    BUY before any roll can occur. Without this, a bare SELL-only roll would leave
    a spurious naked -qty position on the old (now-closed) contract.
    """
    from src.models.portfolio import TradeAction
    from src.paper.models import PaperTrade

    store.record_trade(
        PaperTrade(
            strategy_name="paper_nifty_futures",
            leg_role="base_futures",
            instrument_key="NSE_FO|NIFTY26JULFUT",
            trade_date=date(2026, 6, 25),
            action=TradeAction.BUY,
            quantity=50,
            price=Decimal("23000.0"),
        )
    )


@pytest.mark.asyncio
async def test_roll_persists_both_close_and_open_atomically(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    _seed_entry_trade(store)
    lookup = _futures_lookup()
    today = date(2026, 7, 29)  # 1 DTE on the July future -> due to roll

    pos = PaperPosition(
        strategy_name="paper_nifty_futures",
        leg_role="base_futures",
        net_qty=50,
        avg_cost=Decimal("23000.0"),
        avg_sell_price=Decimal("0.0"),
        instrument_key="NSE_FO|NIFTY26JULFUT",
    )

    broker = MagicMock()
    broker.get_ltp = AsyncMock(
        return_value={
            "NSE_FO|NIFTY26JULFUT": Decimal("23100.0"),
            "NSE_FO|NIFTY26AUGFUT": Decimal("23150.0"),
        }
    )

    summary = await roll_mod.check_and_roll_leg(
        pos, lookup, store, broker, notifier=None, today=today, dry_run=False
    )

    assert summary is not None
    assert summary["inserted"] == 2
    assert summary["skipped"] == 0

    positions = store.get_positions("paper_nifty_futures")
    # Old contract fully closed (flat), new contract open with the same qty.
    open_keys = {p.instrument_key: p.net_qty for p in positions}
    assert open_keys.get("NSE_FO|NIFTY26AUGFUT") == 50
    assert "NSE_FO|NIFTY26JULFUT" not in open_keys


@pytest.mark.asyncio
async def test_roll_notifies_telegram_on_success(tmp_path: Path) -> None:
    """S6: a successful roll must notify, and the message must not contain
    markdown asterisks (TelegramNotifier.send() wraps in <pre> with
    parse_mode HTML — a leftover *bold* marker would render literally)."""
    store = _make_store(tmp_path)
    _seed_entry_trade(store)
    lookup = _futures_lookup()
    today = date(2026, 7, 29)

    pos = PaperPosition(
        strategy_name="paper_nifty_futures",
        leg_role="base_futures",
        net_qty=50,
        avg_cost=Decimal("23000.0"),
        avg_sell_price=Decimal("0.0"),
        instrument_key="NSE_FO|NIFTY26JULFUT",
    )

    broker = MagicMock()
    broker.get_ltp = AsyncMock(
        return_value={
            "NSE_FO|NIFTY26JULFUT": Decimal("23100.0"),
            "NSE_FO|NIFTY26AUGFUT": Decimal("23150.0"),
        }
    )
    notifier = MagicMock()
    notifier.send = AsyncMock(return_value=True)

    summary = await roll_mod.check_and_roll_leg(
        pos, lookup, store, broker, notifier=notifier, today=today, dry_run=False
    )

    assert summary is not None
    notifier.send.assert_awaited_once()
    msg = notifier.send.await_args[0][0]
    assert "*" not in msg
    assert "BASE LEG ROLLED" in msg


@pytest.mark.asyncio
async def test_roll_notify_failure_does_not_block_trade(tmp_path: Path) -> None:
    """Non-fatal contract: a Telegram failure must never roll back or fail
    an already-executed roll."""
    store = _make_store(tmp_path)
    _seed_entry_trade(store)
    lookup = _futures_lookup()
    today = date(2026, 7, 29)

    pos = PaperPosition(
        strategy_name="paper_nifty_futures",
        leg_role="base_futures",
        net_qty=50,
        avg_cost=Decimal("23000.0"),
        avg_sell_price=Decimal("0.0"),
        instrument_key="NSE_FO|NIFTY26JULFUT",
    )

    broker = MagicMock()
    broker.get_ltp = AsyncMock(
        return_value={
            "NSE_FO|NIFTY26JULFUT": Decimal("23100.0"),
            "NSE_FO|NIFTY26AUGFUT": Decimal("23150.0"),
        }
    )
    notifier = MagicMock()
    notifier.send = AsyncMock(side_effect=RuntimeError("network down"))

    summary = await roll_mod.check_and_roll_leg(
        pos, lookup, store, broker, notifier=notifier, today=today, dry_run=False
    )

    # Roll itself must have completed despite the notify failure.
    assert summary is not None
    assert summary["inserted"] == 2
    positions = store.get_positions("paper_nifty_futures")
    open_keys = {p.instrument_key: p.net_qty for p in positions}
    assert open_keys.get("NSE_FO|NIFTY26AUGFUT") == 50


@pytest.mark.asyncio
async def test_roll_dry_run_does_not_persist(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    lookup = _futures_lookup()
    today = date(2026, 7, 29)

    pos = PaperPosition(
        strategy_name="paper_nifty_futures",
        leg_role="base_futures",
        net_qty=50,
        avg_cost=Decimal("23000.0"),
        avg_sell_price=Decimal("0.0"),
        instrument_key="NSE_FO|NIFTY26JULFUT",
    )

    broker = MagicMock()
    broker.get_ltp = AsyncMock(
        return_value={
            "NSE_FO|NIFTY26JULFUT": Decimal("23100.0"),
            "NSE_FO|NIFTY26AUGFUT": Decimal("23150.0"),
        }
    )

    summary = await roll_mod.check_and_roll_leg(
        pos, lookup, store, broker, notifier=None, today=today, dry_run=True
    )

    assert summary is not None
    assert "inserted" not in summary
    # dry_run never calls store.record_trades — DB stays empty regardless of the
    # (synthetic, not DB-backed) `pos` fixture passed in.
    assert store.get_positions("paper_nifty_futures") == []


@pytest.mark.asyncio
async def test_roll_not_due_returns_none(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    lookup = _futures_lookup()
    today = date(2026, 6, 1)  # far from July 30 expiry -> not due

    pos = PaperPosition(
        strategy_name="paper_nifty_futures",
        leg_role="base_futures",
        net_qty=50,
        avg_cost=Decimal("23000.0"),
        avg_sell_price=Decimal("0.0"),
        instrument_key="NSE_FO|NIFTY26JULFUT",
    )

    broker = MagicMock()
    result = await roll_mod.check_and_roll_leg(
        pos, lookup, store, broker, notifier=None, today=today, dry_run=True
    )
    assert result is None
    broker.get_ltp.assert_not_called()


@pytest.mark.asyncio
async def test_roll_partial_insert_flagged(tmp_path: Path) -> None:
    """If record_trades only lands one of the two legs (duplicate skip), the
    summary must flag it — Telegram is the sole visibility mechanism once this
    pipeline runs unattended, so a half-open roll can't look like a clean one."""
    store = _make_store(tmp_path)
    _seed_entry_trade(store)
    lookup = _futures_lookup()
    today = date(2026, 7, 29)

    # Pre-insert the close leg with the exact same (strategy, leg_role,
    # instrument_key, trade_date, action) tuple the roll will attempt, so
    # record_trades' ON CONFLICT DO NOTHING skips it on the real roll call.
    from src.models.portfolio import TradeAction
    from src.paper.models import PaperTrade

    store.record_trade(
        PaperTrade(
            strategy_name="paper_nifty_futures",
            leg_role="base_futures",
            instrument_key="NSE_FO|NIFTY26JULFUT",
            trade_date=today,
            action=TradeAction.SELL,
            quantity=50,
            price=Decimal("1.0"),  # different price, same conflict key -> still skipped
        )
    )

    pos = PaperPosition(
        strategy_name="paper_nifty_futures",
        leg_role="base_futures",
        net_qty=50,
        avg_cost=Decimal("23000.0"),
        avg_sell_price=Decimal("0.0"),
        instrument_key="NSE_FO|NIFTY26JULFUT",
    )

    broker = MagicMock()
    broker.get_ltp = AsyncMock(
        return_value={
            "NSE_FO|NIFTY26JULFUT": Decimal("23100.0"),
            "NSE_FO|NIFTY26AUGFUT": Decimal("23150.0"),
        }
    )

    summary = await roll_mod.check_and_roll_leg(
        pos, lookup, store, broker, notifier=None, today=today, dry_run=False
    )

    assert summary is not None
    assert summary["inserted"] == 1
    assert summary["partial"] is True


# ── DITM orchestration path ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_ditm_roll_persists_via_band_aware_lookup(tmp_path: Path) -> None:
    """DITM roll must use get_next_contract_in_band (never plain get_next_contract,
    which would land on a weekly contract) and persist atomically like futures."""
    store = _make_store(tmp_path)
    lookup = InstrumentLookup(
        [
            {
                "instrument_key": "NSE_FO|NIFTY26JUL23000CE",
                "segment": "NSE_FO",
                "underlying_symbol": "NIFTY",
                "instrument_type": "CE",
                "strike_price": 23000.0,
                "expiry": "2026-07-30",
                "trading_symbol": "NIFTY JUL 23000 CE",
            },
            {
                "instrument_key": "NSE_FO|NIFTY26AUG23000CE",
                "segment": "NSE_FO",
                "underlying_symbol": "NIFTY",
                "instrument_type": "CE",
                "strike_price": 23000.0,
                "expiry": "2026-08-27",
                "trading_symbol": "NIFTY AUG 23000 CE",
            },
        ]
    )
    today = date(2026, 7, 15)  # 15 DTE on the July CE -> under DITM_ROLL_DTE (20)

    from src.models.portfolio import TradeAction
    from src.paper.models import PaperTrade

    store.record_trade(
        PaperTrade(
            strategy_name="paper_nifty_proxy",
            leg_role="base_ditm_call",
            instrument_key="NSE_FO|NIFTY26JUL23000CE",
            trade_date=date(2026, 6, 25),
            action=TradeAction.BUY,
            quantity=50,
            price=Decimal("1000.0"),
        )
    )

    pos = PaperPosition(
        strategy_name="paper_nifty_proxy",
        leg_role="base_ditm_call",
        net_qty=50,
        avg_cost=Decimal("1000.0"),
        avg_sell_price=Decimal("0.0"),
        instrument_key="NSE_FO|NIFTY26JUL23000CE",
    )

    broker = MagicMock()
    broker.get_ltp = AsyncMock(
        return_value={
            "NSE_FO|NIFTY26JUL23000CE": Decimal("1050.0"),
            "NSE_FO|NIFTY26AUG23000CE": Decimal("1100.0"),
        }
    )

    summary = await roll_mod.check_and_roll_leg(
        pos, lookup, store, broker, notifier=None, today=today, dry_run=False
    )

    assert summary is not None
    assert summary["new_key"] == "NSE_FO|NIFTY26AUG23000CE"
    assert summary["inserted"] == 2

    positions = store.get_positions("paper_nifty_proxy")
    open_keys = {p.instrument_key: p.net_qty for p in positions}
    assert open_keys.get("NSE_FO|NIFTY26AUG23000CE") == 50
    assert "NSE_FO|NIFTY26JUL23000CE" not in open_keys


# ── Regression guard: overlay automation untouched ──────────────────────────


@pytest.mark.asyncio
async def test_niftytrackcomparisonv1_untouched() -> None:
    """S5 touches only base-leg rolling — NiftyTrackComparisonV1's overlay
    evaluation must emit nothing for a plain base_futures position (no overlay,
    no proxy-delta leg)."""
    strategy = NiftyTrackComparisonV1()

    pos_fut = PaperPosition(
        strategy_name="paper_nifty_futures",
        leg_role="base_futures",
        net_qty=50,
        avg_cost=Decimal("23000.0"),
        avg_sell_price=Decimal("0.0"),
        instrument_key="NSE_FO|NIFTY26JULFUT",
    )

    events = await strategy.check_signals(market=None, positions=[pos_fut])
    assert events == []

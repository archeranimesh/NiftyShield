"""Unit tests for the signals-paper-track store layer (SPT-2).

Covers `SignalPaperEntry` / `SignalMark` round-trip, the one-position-at-a-time
guard, the Decimal/TEXT boundary on every money column, `cumulative_pnl()` over
an empty table and a win/loss mix, and `gap_event` / `stale` persistence.

File-based SQLite under tmp_path (PaperStore opens a fresh connection per call).
"""

from __future__ import annotations

import sqlite3
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from src.models.portfolio import TradeAction
from src.paper.constants import LOT_SIZE, STRATEGY_SIGNAL_TRACK
from src.paper.models import (
    ExitSignal,
    PaperExitEvent,
    PaperTrade,
    SignalMark,
    SignalPaperEntry,
    TradeState,
)
from src.paper.store import PaperStore

_KEY = "NSE_FO|55555"
_LEG = "signal_long"


@pytest.fixture
def store(tmp_path: Path) -> PaperStore:
    return PaperStore(tmp_path / "test_signal.db")


def _open_buy_row(store: PaperStore, *, key: str = _KEY, day: date, price: str) -> int:
    """Record the opening BUY paper_trades leg and return its row id."""
    store.record_trade(
        PaperTrade(
            strategy_name=STRATEGY_SIGNAL_TRACK,
            leg_role=_LEG,
            instrument_key=key,
            trade_date=day,
            action=TradeAction.BUY,
            quantity=LOT_SIZE,
            price=Decimal(price),
        )
    )
    with sqlite3.connect(store.db_path) as conn:
        (row_id,) = conn.execute(
            "SELECT id FROM paper_trades WHERE instrument_key = ? AND action = 'BUY'"
            " AND trade_date = ?",
            (key, day.isoformat()),
        ).fetchone()
    return int(row_id)


def _entry(trade_id: int, **over: object) -> SignalPaperEntry:
    defaults: dict[str, object] = dict(
        trade_id=trade_id,
        signal_date=date(2026, 9, 10),
        trade_action="BUY_CALL",
        instrument_key=_KEY,
        expiry=date(2026, 9, 30),
        entry_dte=20,
        entry_ts=datetime(2026, 9, 10, 9, 32),
        entry_premium=Decimal("40.25"),
        entry_bid=Decimal("39.75"),
        entry_ask=Decimal("40.75"),
        entry_slippage=Decimal("1.5"),
        entry_vix=Decimal("12.34"),
        entry_underlying=Decimal("23041.55"),
        signal_confidence=4,
        sl_pct=Decimal("0.30"),
        tgt_pct=Decimal("0.50"),
        sl_price=Decimal("28.175"),
        tgt_price=Decimal("60.375"),
    )
    defaults.update(over)
    return SignalPaperEntry(**defaults)


def _mark(trade_id: int, **over: object) -> SignalMark:
    defaults: dict[str, object] = dict(
        trade_id=trade_id,
        ts=datetime(2026, 9, 10, 9, 33),
        quote_ts=datetime(2026, 9, 10, 9, 33),
        stale=False,
        ltp=Decimal("41.00"),
        bid=Decimal("40.50"),
        ask=Decimal("41.50"),
        mark=Decimal("41.00"),
        unrealised_pct=Decimal("0.0186"),
        mfe_pct=Decimal("0.0186"),
        mae_pct=Decimal("0"),
        gap_event=False,
    )
    defaults.update(over)
    return SignalMark(**defaults)


def _exit_event(trade_id: int) -> PaperExitEvent:
    return PaperExitEvent(
        strategy_name=STRATEGY_SIGNAL_TRACK,
        leg_name=_LEG,
        trade_id=str(trade_id),
        event_time=datetime(2026, 9, 10, 12, 5),
        detected_by="INTRADAY",
        exit_signal=ExitSignal.PROFIT_TARGET,
        severity="ACTION",
        entry_price=Decimal("40.25"),
        ltp=Decimal("60.50"),
    )


# ── round-trip ────────────────────────────────────────────────────────────────


def test_open_record_close_round_trip(store: PaperStore) -> None:
    tid = _open_buy_row(store, day=date(2026, 9, 10), price="40.25")
    store.open_signal_entry(_entry(tid))

    got = store.get_open_signal_entry()
    assert got is not None
    assert got.trade_id == tid
    assert got.entry_premium == Decimal("40.25")
    assert got.sl_price == Decimal("28.175")
    assert got.ruleset_version == "v1"

    for i in range(3):
        store.record_mark(_mark(tid, ts=datetime(2026, 9, 10, 9, 33 + i)))
    marks = store.get_marks(tid)
    assert len(marks) == 3
    assert all(isinstance(m.mark, Decimal) for m in marks)

    store.close_signal_entry(tid, _exit_event(tid))
    assert store.get_open_signal_entry() is None


def test_second_open_rejected_while_one_open(store: PaperStore) -> None:
    t1 = _open_buy_row(store, day=date(2026, 9, 10), price="40.25")
    store.open_signal_entry(_entry(t1))
    t2 = _open_buy_row(store, key="NSE_FO|66666", day=date(2026, 9, 11), price="35.00")
    with pytest.raises(ValueError, match="already open"):
        store.open_signal_entry(_entry(t2, instrument_key="NSE_FO|66666"))


def test_reopen_allowed_after_close(store: PaperStore) -> None:
    t1 = _open_buy_row(store, day=date(2026, 9, 10), price="40.25")
    store.open_signal_entry(_entry(t1))
    store.close_signal_entry(t1, _exit_event(t1))
    t2 = _open_buy_row(store, key="NSE_FO|66666", day=date(2026, 9, 11), price="35.00")
    store.open_signal_entry(_entry(t2, instrument_key="NSE_FO|66666"))
    assert store.get_open_signal_entry().trade_id == t2


# ── Decimal / TEXT boundary ───────────────────────────────────────────────────


def test_money_columns_stored_as_text_read_as_decimal(store: PaperStore) -> None:
    tid = _open_buy_row(store, day=date(2026, 9, 10), price="40.25")
    store.open_signal_entry(_entry(tid, entry_premium=Decimal("40.123456")))
    with sqlite3.connect(store.db_path) as conn:
        raw = conn.execute(
            "SELECT entry_premium, sl_price, entry_vix FROM paper_signal_entries"
        ).fetchone()
    assert raw[0] == "40.123456"  # exact TEXT, no float coercion
    assert isinstance(raw[1], str)
    got = store.get_open_signal_entry()
    assert got.entry_premium == Decimal("40.123456")
    assert got.entry_vix == Decimal("12.34")


def test_entry_vix_none_survives_round_trip(store: PaperStore) -> None:
    tid = _open_buy_row(store, day=date(2026, 9, 10), price="40.25")
    store.open_signal_entry(_entry(tid, entry_vix=None))
    assert store.get_open_signal_entry().entry_vix is None


def test_gap_event_and_stale_persist_as_written(store: PaperStore) -> None:
    tid = _open_buy_row(store, day=date(2026, 9, 10), price="40.25")
    store.open_signal_entry(_entry(tid))
    store.record_mark(_mark(tid, ts=datetime(2026, 9, 10, 9, 40), stale=True, gap_event=True))
    store.record_mark(_mark(tid, ts=datetime(2026, 9, 10, 9, 41), stale=False, gap_event=False))
    m0, m1 = store.get_marks(tid)
    assert (m0.stale, m0.gap_event) == (True, True)
    assert (m1.stale, m1.gap_event) == (False, False)


def test_record_mark_idempotent_on_trade_id_ts(store: PaperStore) -> None:
    tid = _open_buy_row(store, day=date(2026, 9, 10), price="40.25")
    store.open_signal_entry(_entry(tid))
    store.record_mark(_mark(tid))
    store.record_mark(_mark(tid))
    assert len(store.get_marks(tid)) == 1


# ── cumulative_pnl ────────────────────────────────────────────────────────────


def test_cumulative_pnl_empty(store: PaperStore) -> None:
    assert store.cumulative_pnl() == (Decimal("0"), 0, 0, 0)


def test_cumulative_pnl_open_position_not_counted(store: PaperStore) -> None:
    tid = _open_buy_row(store, day=date(2026, 9, 10), price="40.25")
    store.open_signal_entry(_entry(tid))
    assert store.cumulative_pnl() == (Decimal("0"), 0, 0, 0)


def _close_cycle(store: PaperStore, day: date, key: str, entry_px: str, exit_px: str) -> None:
    tid = _open_buy_row(store, key=key, day=day, price=entry_px)
    store.open_signal_entry(
        _entry(tid, signal_date=day, instrument_key=key, entry_premium=Decimal(entry_px))
    )
    store.record_trade(
        PaperTrade(
            strategy_name=STRATEGY_SIGNAL_TRACK,
            leg_role=_LEG,
            instrument_key=key,
            trade_date=day,
            action=TradeAction.SELL,
            quantity=LOT_SIZE,
            price=Decimal(exit_px),
        )
    )
    store.close_signal_entry(tid, _exit_event(tid))


def test_cumulative_pnl_win_loss_mix(store: PaperStore) -> None:
    _close_cycle(store, date(2026, 9, 10), "NSE_FO|1", "40.00", "60.00")  # +20 * 65
    _close_cycle(store, date(2026, 9, 11), "NSE_FO|2", "40.00", "28.00")  # -12 * 65
    _close_cycle(store, date(2026, 9, 12), "NSE_FO|3", "40.00", "50.00")  # +10 * 65

    total, n, wins, losses = store.cumulative_pnl()
    assert n == 3
    assert wins == 2
    assert losses == 1
    assert total == Decimal("18") * LOT_SIZE


def test_get_entries_filters_by_signal_date(store: PaperStore) -> None:
    _close_cycle(store, date(2026, 9, 10), "NSE_FO|1", "40.00", "60.00")
    _close_cycle(store, date(2026, 9, 20), "NSE_FO|2", "40.00", "50.00")
    got = store.get_entries(date(2026, 9, 1), date(2026, 9, 15))
    assert [e.signal_date for e in got] == [date(2026, 9, 10)]


def test_close_sets_trade_state_closed(store: PaperStore) -> None:
    tid = _open_buy_row(store, day=date(2026, 9, 10), price="40.25")
    store.open_signal_entry(_entry(tid))
    event_id = store.close_signal_entry(tid, _exit_event(tid))
    assert isinstance(event_id, int)
    with sqlite3.connect(store.db_path) as conn:
        (state,) = conn.execute("SELECT state FROM paper_trades WHERE id = ?", (tid,)).fetchone()
        (n_events,) = conn.execute(
            "SELECT COUNT(*) FROM paper_exit_events WHERE trade_id = ?", (str(tid),)
        ).fetchone()
    assert state == TradeState.CLOSED.value
    assert n_events == 1

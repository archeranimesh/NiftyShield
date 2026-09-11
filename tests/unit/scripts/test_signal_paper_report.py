"""Offline tests for the SPT-7 evaluation report + go-live gate.

Fixture set: closed `SignalPaperEntry` + `paper_signal_marks` rows built through
`PaperStore`'s real write path (same fixture pattern as
tests/unit/paper/test_signal_store.py), no network, no real DB.
"""

from __future__ import annotations

import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from scripts import signal_paper_report as spr
from src.models.portfolio import TradeAction
from src.paper.constants import LOT_SIZE, STRATEGY_SIGNAL_TRACK
from src.paper.models import ExitSignal, PaperExitEvent, PaperTrade, SignalPaperEntry
from src.paper.store import PaperStore
from src.signals.store import SignalStore

_KEY = "NSE_FO|55555"
_LEG = "signal_long"


@pytest.fixture
def store(tmp_path: Path) -> PaperStore:
    return PaperStore(tmp_path / "test_signal.db")


@pytest.fixture
def signal_store(tmp_path: Path) -> SignalStore:
    s = SignalStore(str(tmp_path / "test_signal.db"))
    s.init_db()
    return s


def _entry(trade_id: int, **over: object) -> SignalPaperEntry:
    defaults: dict[str, object] = dict(
        trade_id=trade_id,
        signal_date=date(2026, 9, 10),
        trade_action="BUY_CALL",
        instrument_key=_KEY,
        expiry=date(2026, 9, 30),
        entry_dte=20,
        entry_ts=datetime(2026, 9, 10, 9, 32),
        entry_premium=Decimal("40.00"),
        entry_bid=Decimal("39.75"),
        entry_ask=Decimal("40.25"),
        entry_slippage=Decimal("1.0"),
        entry_vix=Decimal("12.34"),
        entry_underlying=Decimal("23041.55"),
        signal_confidence=4,
        sl_pct=Decimal("0.30"),
        tgt_pct=Decimal("0.50"),
        sl_price=Decimal("28.00"),
        tgt_price=Decimal("60.00"),
    )
    defaults.update(over)
    return SignalPaperEntry(**defaults)


def _exit_event(
    trade_id: int, exit_signal: ExitSignal = ExitSignal.PROFIT_TARGET
) -> PaperExitEvent:
    return PaperExitEvent(
        strategy_name=STRATEGY_SIGNAL_TRACK,
        leg_name=_LEG,
        trade_id=str(trade_id),
        event_time=datetime(2026, 9, 10, 12, 5),
        detected_by="INTRADAY",
        exit_signal=exit_signal,
        severity="ACTION",
        entry_price=Decimal("40.00"),
        ltp=Decimal("60.00"),
    )


def _close_cycle(
    store: PaperStore,
    day: date,
    key: str,
    entry_px: str,
    exit_px: str,
    *,
    exit_signal: ExitSignal = ExitSignal.PROFIT_TARGET,
    entry_vix: Decimal | None = Decimal("12.0"),
    **entry_over: object,
) -> int:
    """Open + close one signals-paper-track cycle; returns the BUY trade_id."""
    store.record_trade(
        PaperTrade(
            strategy_name=STRATEGY_SIGNAL_TRACK,
            leg_role=_LEG,
            instrument_key=key,
            trade_date=day,
            action=TradeAction.BUY,
            quantity=LOT_SIZE,
            price=Decimal(entry_px),
        )
    )
    import sqlite3

    with sqlite3.connect(store.db_path) as conn:
        (tid,) = conn.execute(
            "SELECT id FROM paper_trades WHERE instrument_key=? AND trade_date=? AND action='BUY'",
            (key, day.isoformat()),
        ).fetchone()
    tid = int(tid)
    store.open_signal_entry(
        _entry(
            tid,
            signal_date=day,
            instrument_key=key,
            entry_premium=Decimal(entry_px),
            entry_vix=entry_vix,
            **entry_over,
        )
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
    store.close_signal_entry(tid, _exit_event(tid, exit_signal))
    return tid


# ── loading / grouping ───────────────────────────────────────────────────────


def test_load_closed_cycles_empty(store: PaperStore) -> None:
    assert spr.load_closed_cycles(store.db_path) == []


def test_load_closed_cycles_joins_exit_reason_and_price(store: PaperStore) -> None:
    _close_cycle(store, date(2026, 9, 10), "NSE_FO|1", "40.00", "60.00")
    cycles = spr.load_closed_cycles(store.db_path)
    assert len(cycles) == 1
    c = cycles[0]
    assert c.exit_price == Decimal("60.00")
    assert c.exit_reason == "PROFIT_TARGET"
    assert c.pnl == Decimal("20.00") * LOT_SIZE


def test_v1_v2_never_pooled(store: PaperStore) -> None:
    _close_cycle(store, date(2026, 9, 10), "NSE_FO|1", "40.00", "60.00")
    _close_cycle(store, date(2026, 9, 11), "NSE_FO|2", "40.00", "30.00", ruleset_version="v2")
    cycles = spr.load_closed_cycles(store.db_path)
    grouped = spr._by_ruleset(cycles)
    assert set(grouped) == {"v1", "v2"}
    assert len(grouped["v1"]) == 1
    assert len(grouped["v2"]) == 1


def test_default_window_no_entries() -> None:
    frm, to = spr._default_window([])
    assert frm == to


def test_empty_window_guard(store: PaperStore, capsys: pytest.CaptureFixture[str]) -> None:
    """No closed cycles anywhere -> main() prints the empty-window message and returns."""
    import scripts.signal_paper_report as mod

    class _Settings:
        db_path = store.db_path

    orig = mod.settings
    mod.settings = _Settings()
    try:
        mod.main()
    finally:
        mod.settings = orig
    assert "No closed signals-paper-track cycles" in capsys.readouterr().out


# ── metrics ──────────────────────────────────────────────────────────────────


def _cycles(store: PaperStore) -> list[spr.ClosedCycle]:
    return spr.load_closed_cycles(store.db_path)


def test_profit_factor_zero_losses(store: PaperStore) -> None:
    _close_cycle(store, date(2026, 9, 10), "NSE_FO|1", "40.00", "60.00")
    _close_cycle(store, date(2026, 9, 11), "NSE_FO|2", "40.00", "50.00")
    metrics = spr.compute_metrics(_cycles(store))
    assert metrics["profit_factor"] is None  # gross_loss == 0 -> undefined, not zero


def test_profit_factor_zero_wins(store: PaperStore) -> None:
    _close_cycle(store, date(2026, 9, 10), "NSE_FO|1", "40.00", "30.00")
    _close_cycle(store, date(2026, 9, 11), "NSE_FO|2", "40.00", "20.00")
    metrics = spr.compute_metrics(_cycles(store))
    assert metrics["profit_factor"] == Decimal("0")


def test_compute_metrics_win_loss_mix(store: PaperStore) -> None:
    _close_cycle(store, date(2026, 9, 10), "NSE_FO|1", "40.00", "60.00")  # +20*65 win
    _close_cycle(store, date(2026, 9, 11), "NSE_FO|2", "40.00", "28.00")  # -12*65 loss
    metrics = spr.compute_metrics(_cycles(store))
    assert metrics["n"] == 2
    assert metrics["wins"] == 1
    assert metrics["losses"] == 1
    assert metrics["total_pnl"] == Decimal("8") * LOT_SIZE


# ── gate ─────────────────────────────────────────────────────────────────────


def test_gate_g1_window_fails_below_floor(store: PaperStore, signal_store: SignalStore) -> None:
    _close_cycle(store, date(2026, 9, 10), "NSE_FO|1", "40.00", "60.00")
    cycles = _cycles(store)
    metrics = spr.compute_metrics(cycles)
    gate = spr.evaluate_gate(cycles, metrics, signal_store)
    assert gate["G1_window"][0] is False


def test_gate_g1_window_passes_at_floor(store: PaperStore, signal_store: SignalStore) -> None:
    for i in range(40):
        _close_cycle(store, date(2026, 9, 10), f"NSE_FO|{i}", "40.00", "60.00")
    cycles = _cycles(store)
    metrics = spr.compute_metrics(cycles)
    gate = spr.evaluate_gate(cycles, metrics, signal_store)
    assert gate["G1_window"][0] is True


def test_gate_g4_net_pnl_pass_and_fail(store: PaperStore, signal_store: SignalStore) -> None:
    _close_cycle(store, date(2026, 9, 10), "NSE_FO|1", "40.00", "60.00")
    cycles = _cycles(store)
    metrics = spr.compute_metrics(cycles)
    assert spr.evaluate_gate(cycles, metrics, signal_store)["G4_net_pnl"][0] is True

    _close_cycle(store, date(2026, 9, 11), "NSE_FO|2", "40.00", "10.00")
    cycles = _cycles(store)
    metrics = spr.compute_metrics(cycles)
    # +20*65 - 30*65 = -10*65 < 0
    assert spr.evaluate_gate(cycles, metrics, signal_store)["G4_net_pnl"][0] is False


def test_gate_g6_profit_factor_pass_and_fail(store: PaperStore, signal_store: SignalStore) -> None:
    # Wins dominate -> pf high -> pass.
    _close_cycle(store, date(2026, 9, 10), "NSE_FO|1", "40.00", "60.00")
    _close_cycle(store, date(2026, 9, 11), "NSE_FO|2", "40.00", "39.00")
    cycles = _cycles(store)
    metrics = spr.compute_metrics(cycles)
    assert spr.evaluate_gate(cycles, metrics, signal_store)["G6_profit_factor"][0] is True

    # Losses dominate -> pf low -> fail.
    _close_cycle(store, date(2026, 9, 12), "NSE_FO|3", "40.00", "10.00")
    cycles = _cycles(store)
    metrics = spr.compute_metrics(cycles)
    assert spr.evaluate_gate(cycles, metrics, signal_store)["G6_profit_factor"][0] is False


def test_gate_g3_regime_requires_vix_over_18(store: PaperStore, signal_store: SignalStore) -> None:
    _close_cycle(store, date(2026, 9, 10), "NSE_FO|1", "40.00", "60.00", entry_vix=Decimal("12"))
    cycles = _cycles(store)
    metrics = spr.compute_metrics(cycles)
    assert spr.evaluate_gate(cycles, metrics, signal_store)["G3_regime"][0] is False

    _close_cycle(store, date(2026, 9, 11), "NSE_FO|2", "40.00", "60.00", entry_vix=Decimal("19"))
    cycles = _cycles(store)
    metrics = spr.compute_metrics(cycles)
    assert spr.evaluate_gate(cycles, metrics, signal_store)["G3_regime"][0] is True


def test_gate_g2_exit_path_counts_mapped_reasons(
    store: PaperStore, signal_store: SignalStore
) -> None:
    for i in range(5):
        _close_cycle(
            store,
            date(2026, 9, 10),
            f"NSE_FO|t{i}",
            "40.00",
            "60.00",
            exit_signal=ExitSignal.PROFIT_TARGET,
        )
    cycles = _cycles(store)
    metrics = spr.compute_metrics(cycles)
    assert metrics["exit_reason_histogram"] == {"TARGET": 5}
    assert (
        spr.evaluate_gate(cycles, metrics, signal_store)["G2_exit_path"][0] is False
    )  # missing SL/TIME


def test_incidents_flag_gap_through_loss(store: PaperStore) -> None:
    # SL loss expected = 0.30 * 40 * 65 = 780; a loss of (40-1)*65 = 2535 > 1.5*780.
    _close_cycle(store, date(2026, 9, 10), "NSE_FO|1", "40.00", "1.00")  # loss ~39*65
    cycles = _cycles(store)
    incidents = spr._incidents(cycles)
    assert len(incidents) == 1

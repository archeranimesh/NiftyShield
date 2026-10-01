"""Unit tests for scripts/dev/backfill_signal_exit.py (BUG-063). Offline: stores are mocks."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

from scripts.dev.backfill_signal_exit import backfill
from src.paper.constants import LOT_SIZE
from src.paper.models import ExitSignal, SignalExit
from src.signals.models import SignalOutcome, TradeAction

_DAY = date(2026, 10, 1)


def _outcome(**over: object) -> SignalOutcome:
    base: dict[str, object] = {
        "trade_date": _DAY,
        "trade_action": TradeAction.BUY_PUT,
        "recommended_strike": 22550,
        "entry_premium": Decimal("265.225"),
        "exit_premium": Decimal("329.40"),
        "pnl_per_lot": (Decimal("329.40") - Decimal("265.225")) * LOT_SIZE,
        "nifty_close": Decimal("22422"),
        "executed": True,
        "phase": "openrouter_only",
    }
    base.update(over)
    return SignalOutcome(**base)


def _stores(outcome: SignalOutcome, tracker_exit: SignalExit | None) -> tuple[MagicMock, MagicMock]:
    signal_store, paper_store = MagicMock(), MagicMock()
    signal_store.get_all_outcomes.return_value = [outcome]
    paper_store.get_entries.return_value = [MagicMock(trade_id=408)]
    paper_store.get_signal_exit.return_value = tracker_exit
    return signal_store, paper_store


_TARGET_EXIT = SignalExit(exit_price=Decimal("399.0"), reason=ExitSignal.PROFIT_TARGET)


def test_dry_run_reports_change_and_writes_nothing() -> None:
    signal_store, paper_store = _stores(_outcome(), _TARGET_EXIT)

    changes = backfill(signal_store, paper_store, _DAY, _DAY, apply=False)

    assert len(changes) == 1
    assert changes[0].new_exit == Decimal("399.0")
    assert changes[0].new_pnl == (Decimal("399.0") - Decimal("265.225")) * LOT_SIZE
    assert changes[0].reason == "PROFIT_TARGET"
    signal_store.record_outcome.assert_not_called()


def test_apply_rewrites_exit_and_pnl_and_preserves_other_fields() -> None:
    signal_store, paper_store = _stores(_outcome(), _TARGET_EXIT)

    backfill(signal_store, paper_store, _DAY, _DAY, apply=True)

    written = signal_store.record_outcome.call_args[0][0]
    assert written.exit_premium == Decimal("399.0")
    assert written.pnl_per_lot == (Decimal("399.0") - Decimal("265.225")) * LOT_SIZE
    assert written.nifty_close == Decimal("22422")
    assert written.phase == "openrouter_only"


def test_idempotent_when_exit_already_matches_fill() -> None:
    signal_store, paper_store = _stores(_outcome(exit_premium=Decimal("399.0")), _TARGET_EXIT)

    assert backfill(signal_store, paper_store, _DAY, _DAY, apply=True) == []
    signal_store.record_outcome.assert_not_called()


def test_skips_not_executed_and_open_positions() -> None:
    not_taken, paper_a = _stores(_outcome(executed=False), _TARGET_EXIT)
    still_open, paper_b = _stores(_outcome(), None)

    assert backfill(not_taken, paper_a, _DAY, _DAY, apply=True) == []
    assert backfill(still_open, paper_b, _DAY, _DAY, apply=True) == []
    not_taken.record_outcome.assert_not_called()
    still_open.record_outcome.assert_not_called()

"""Unit tests for the signals-paper-track exit constants + evaluator
(SPT-3 / SPT-3b)."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from src.paper.models import SignalPaperEntry
from src.strategy.signal_exit import (
    RULESET_VERSION,
    SL_PCT,
    TGT_PCT,
    SignalExitReason,
    derive_levels,
    evaluate,
)


def test_derive_levels_happy_path() -> None:
    sl, tgt = derive_levels(Decimal("40"))
    assert sl == Decimal("28.0")  # 40 * (1 - 0.30)
    assert tgt == Decimal("60.0")  # 40 * (1 + 0.50)


def test_derive_levels_uses_module_constants() -> None:
    e = Decimal("13.37")
    sl, tgt = derive_levels(e)
    assert sl == e * (Decimal("1") - SL_PCT)
    assert tgt == e * (Decimal("1") + TGT_PCT)
    assert RULESET_VERSION == "v1"


@pytest.mark.parametrize("bad", [Decimal("0"), Decimal("-1.5")])
def test_derive_levels_rejects_non_positive(bad: Decimal) -> None:
    with pytest.raises(ValueError, match="must be positive"):
        derive_levels(bad)


def _make_entry(**over: object) -> SignalPaperEntry:
    defaults = dict(
        trade_id=1,
        signal_date=date(2026, 9, 10),
        trade_action="BUY_PUT",
        instrument_key="NSE_FO|12345",
        expiry=date(2026, 9, 29),
        entry_dte=19,
        entry_ts=datetime(2026, 9, 10, 9, 32),
        entry_premium=Decimal("40"),
        entry_bid=Decimal("39.00"),
        entry_ask=Decimal("40.04"),
        entry_slippage=Decimal("1.0"),
        entry_vix=Decimal("12.34"),
        entry_underlying=Decimal("23041.55"),
        signal_confidence=4,
        sl_pct=SL_PCT,
        tgt_pct=TGT_PCT,
        sl_price=Decimal("28.0"),
        tgt_price=Decimal("60.0"),
    )
    defaults.update(over)
    return SignalPaperEntry(**defaults)


def test_evaluate_target_at_and_above_threshold() -> None:
    entry = _make_entry()
    for mark in (Decimal("60.0"), Decimal("61.0")):
        decision = evaluate(entry, mark, datetime(2026, 9, 10, 11, 0))
        assert decision.reason == SignalExitReason.TARGET


def test_evaluate_stop_loss_at_and_below_threshold() -> None:
    entry = _make_entry()
    for mark in (Decimal("28.0"), Decimal("27.0")):
        decision = evaluate(entry, mark, datetime(2026, 9, 10, 11, 0))
        assert decision.reason == SignalExitReason.STOP_LOSS


def test_evaluate_time_exit_at_and_after_1500() -> None:
    entry = _make_entry()
    for now in (datetime(2026, 9, 10, 15, 0, 0), datetime(2026, 9, 10, 15, 1)):
        decision = evaluate(entry, Decimal("45.0"), now)
        assert decision.reason == SignalExitReason.TIME_EXIT


def test_evaluate_hold_in_dead_band_and_at_1459() -> None:
    entry = _make_entry()
    decision = evaluate(entry, Decimal("45.0"), datetime(2026, 9, 10, 11, 0))
    assert decision.reason is None
    before_cutoff = datetime(2026, 9, 10, 14, 59, 59)
    decision = evaluate(entry, Decimal("45.0"), before_cutoff)
    assert decision.reason is None


def test_evaluate_target_wins_over_time_exit() -> None:
    entry = _make_entry()
    decision = evaluate(entry, Decimal("60.0"), datetime(2026, 9, 10, 15, 30))
    assert decision.reason == SignalExitReason.TARGET


def test_signal_exit_reason_has_reserved_trailing_stop() -> None:
    assert SignalExitReason.TRAILING_STOP.value == "TRAILING_STOP"
    entry = _make_entry()
    for mark, now in (
        (Decimal("60.0"), datetime(2026, 9, 10, 11, 0)),
        (Decimal("28.0"), datetime(2026, 9, 10, 11, 0)),
        (Decimal("45.0"), datetime(2026, 9, 10, 15, 30)),
        (Decimal("45.0"), datetime(2026, 9, 10, 11, 0)),
    ):
        result = evaluate(entry, mark, now).reason
        assert result != SignalExitReason.TRAILING_STOP


def test_evaluate_converts_aware_datetime_to_ist() -> None:
    entry = _make_entry()
    # 09:31 UTC = 15:01 IST -> TIME_EXIT
    now_utc = datetime(2026, 9, 10, 9, 31, tzinfo=ZoneInfo("UTC"))
    decision = evaluate(entry, Decimal("45.0"), now_utc)
    assert decision.reason == SignalExitReason.TIME_EXIT

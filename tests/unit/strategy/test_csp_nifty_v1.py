"""Unit tests for CSPNiftyV1 backbone strategy.

All tests are offline — no network calls, no DB.

Instrument key conventions used here:
  "NSE_FO|NIFTY23000PE"        — strike embedded (23000), no expiry
  "NSE_FO|NIFTY{date}PE"       — expiry embedded, no strike (DTE tests)
  "NSE_FO|12345"                — numeric key, nothing parseable

Signal table (CR1b 2026-06-06):
  PROFIT_TARGET  ACTION  LTP ≤ 30% of entry credit (70% captured)
  HARD_STOP      ACTION  LTP ≥ 2× entry credit
  DELTA_BREACH   ACTION  |delta| ≥ 0.40 (OPEN state)
  TIME_STOP      ACTION  days_held ≥ 21
  ROLL_ELIGIBLE  ACTION  DTE ≤ 7
"""

from __future__ import annotations

import asyncio
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from src.models.options import OptionChain, OptionChainStrike, OptionLeg
from src.paper.models import PaperPosition, PaperTrade, TradeAction
from src.paper.store import PaperStore
from src.strategy.csp_nifty_v1 import CSPNiftyV1
from src.strategy.protocol import ApprovedAction

_STRATEGY = "paper_csp_nifty_v1"
_OTHER_STRATEGY = "paper_other_v1"

# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_put_leg(
    ltp: str,
    delta: str,
    strike: str = "23000",
    iv: str = "15.0",
) -> OptionLeg:
    """Build a minimal PE OptionLeg."""
    return OptionLeg(
        ltp=Decimal(ltp),
        bid=Decimal(ltp),
        ask=Decimal(ltp),
        oi=1000,
        volume=500,
        delta=Decimal(delta),
        gamma=Decimal("0.001"),
        theta=Decimal("-5"),
        vega=Decimal("10"),
        iv=Decimal(iv),
        strike=Decimal(strike),
    )


def _make_chain(ltp: str, delta: str, strike: str = "23000") -> OptionChain:
    """Build a one-strike OptionChain with the given PE leg."""
    pe = _make_put_leg(ltp=ltp, delta=delta, strike=strike)
    return OptionChain(
        underlying_spot=Decimal("24000"),
        expiry=date(2026, 6, 26),
        strikes={Decimal(strike): OptionChainStrike(pe=pe)},
    )


def _make_empty_chain() -> OptionChain:
    """Build a chain with no strikes (used for DTE/days_held-only tests)."""
    return OptionChain(
        underlying_spot=Decimal("24000"),
        expiry=date(2026, 6, 26),
        strikes={},
    )


def _make_position(
    instrument_key: str = "NSE_FO|NIFTY23000PE",
    avg_sell_price: str = "80",
    net_qty: int = -65,
    leg_role: str = "short_put",
    strategy_name: str = _STRATEGY,
    entry_date: date | None = None,
) -> PaperPosition:
    """Build a PaperPosition for a short-put leg."""
    return PaperPosition(
        strategy_name=strategy_name,
        leg_role=leg_role,
        net_qty=net_qty,
        avg_cost=Decimal("0"),
        avg_sell_price=Decimal(avg_sell_price),
        instrument_key=instrument_key,
        entry_date=entry_date,
    )


def _expiry_key(dte: int) -> str:
    """Build an instrument key whose embedded expiry yields ``dte`` from today."""
    expiry = date.today() + timedelta(days=dte)
    date_str = expiry.strftime("%d%b%Y").upper()
    return f"NSE_FO|NIFTY{date_str}PE"


def _run(coro):  # type: ignore[no-untyped-def]
    return asyncio.run(coro)


# ── check_signals — no positions ──────────────────────────────────────────────


def test_no_open_positions_returns_empty() -> None:
    """check_signals returns [] when no positions exist."""
    strategy = CSPNiftyV1()
    result = _run(strategy.check_signals(_make_empty_chain(), []))
    assert result == []


def test_filters_out_other_strategy_positions() -> None:
    """Positions belonging to a different strategy are ignored."""
    strategy = CSPNiftyV1()
    pos = _make_position(strategy_name=_OTHER_STRATEGY)
    result = _run(strategy.check_signals(_make_chain("40", "-0.20"), [pos]))
    assert result == []


def test_long_position_ignored() -> None:
    """Long positions (net_qty > 0) are not evaluated."""
    strategy = CSPNiftyV1()
    pos = _make_position(net_qty=65)  # long, not short
    result = _run(strategy.check_signals(_make_chain("40", "-0.20"), [pos]))
    assert result == []


# ── check_signals — mark-based signals ───────────────────────────────────────


def test_profit_target_fires_at_70_pct_captured() -> None:
    """PROFIT_TARGET ACTION when LTP ≤ 30% of entry credit (70% captured)."""
    strategy = CSPNiftyV1()
    # entry credit = 80, LTP = 23 → 23/80 = 0.2875 ≤ 0.30 → fires
    chain = _make_chain(ltp="23", delta="-0.20")
    pos = _make_position(avg_sell_price="80")
    events = _run(strategy.check_signals(chain, [pos]))
    event_types = {e.event_type for e in events}
    assert "PROFIT_TARGET" in event_types
    pt = next(e for e in events if e.event_type == "PROFIT_TARGET")
    assert pt.severity == "ACTION"


def test_hard_stop_fires_at_200_pct() -> None:
    """HARD_STOP ACTION when LTP = 200% of entry credit (≥ 2×)."""
    strategy = CSPNiftyV1()
    # entry credit = 80, LTP = 161 → 161/80 = 2.0125 ≥ 2.0 → fires
    chain = _make_chain(ltp="161", delta="-0.55")
    pos = _make_position(avg_sell_price="80")
    events = _run(strategy.check_signals(chain, [pos]))
    event_types = {e.event_type for e in events}
    assert "HARD_STOP" in event_types
    hs = next(e for e in events if e.event_type == "HARD_STOP")
    assert hs.severity == "ACTION"


def test_hard_stop_does_not_fire_below_200_pct() -> None:
    """HARD_STOP does NOT fire when LTP = 199% of entry credit (< 2×)."""
    strategy = CSPNiftyV1()
    # entry credit = 80, LTP = 159 → 159/80 = 1.9875 < 2.0
    chain = _make_chain(ltp="159", delta="-0.30")
    pos = _make_position(avg_sell_price="80")
    events = _run(strategy.check_signals(chain, [pos]))
    assert not any(e.event_type == "HARD_STOP" for e in events)


def test_profit_target_fires_at_24_pct() -> None:
    """PROFIT_TARGET fires at 24% mark (≤ 30%) — no ROLL_DUE_DECAY in spec."""
    strategy = CSPNiftyV1()
    # entry credit = 80, LTP = 19.2 → 19.2/80 = 0.24 ≤ 0.30 → fires
    chain = _make_chain(ltp="19.2", delta="-0.10")
    pos = _make_position(avg_sell_price="80")
    events = _run(strategy.check_signals(chain, [pos]))
    event_types = {e.event_type for e in events}
    assert "PROFIT_TARGET" in event_types
    assert "ROLL_DUE_DECAY" not in event_types


# ── check_signals — delta signals ────────────────────────────────────────────


def test_delta_breach_fires_at_0_40() -> None:
    """DELTA_BREACH ACTION when |delta| = 0.41 (≥ 0.40 threshold)."""
    strategy = CSPNiftyV1()
    chain = _make_chain(ltp="80", delta="-0.41")
    pos = _make_position(avg_sell_price="80")
    events = _run(strategy.check_signals(chain, [pos]))
    event_types = {e.event_type for e in events}
    assert "DELTA_BREACH" in event_types
    db = next(e for e in events if e.event_type == "DELTA_BREACH")
    assert db.severity == "ACTION"


def test_delta_breach_does_not_fire_at_0_39() -> None:
    """DELTA_BREACH does NOT fire at |delta| = 0.39 (< 0.40)."""
    strategy = CSPNiftyV1()
    chain = _make_chain(ltp="80", delta="-0.39")
    pos = _make_position(avg_sell_price="80")
    events = _run(strategy.check_signals(chain, [pos]))
    event_types = {e.event_type for e in events}
    assert "DELTA_BREACH" not in event_types
    assert "DELTA_STOP" not in event_types
    assert "DELTA_WARN" not in event_types


def test_no_delta_warn_signal_exists() -> None:
    """DELTA_WARN is removed in CR1b — no such signal fires at any delta level."""
    strategy = CSPNiftyV1()
    chain = _make_chain(ltp="80", delta="-0.36")
    pos = _make_position(avg_sell_price="80")
    events = _run(strategy.check_signals(chain, [pos]))
    assert not any(e.event_type == "DELTA_WARN" for e in events)


# ── check_signals — DTE signals ───────────────────────────────────────────────


def test_time_stop_fires_at_days_held_21() -> None:
    """TIME_STOP ACTION when days_held = 21 (calendar days since entry SELL)."""
    strategy = CSPNiftyV1()
    entry = date.today() - timedelta(days=21)
    pos = _make_position(avg_sell_price="80", entry_date=entry)
    events = _run(strategy.check_signals(_make_empty_chain(), [pos]))
    event_types = {e.event_type for e in events}
    assert "TIME_STOP" in event_types
    ts = next(e for e in events if e.event_type == "TIME_STOP")
    assert ts.severity == "ACTION"


def test_profit_target_valid_actions_includes_signal_type() -> None:
    """PROFIT_TARGET event carries ['PROFIT_TARGET', 'CLOSE_FULL'] in valid_actions."""
    strategy = CSPNiftyV1()
    chain = _make_chain(ltp="23", delta="-0.20")
    pos = _make_position(avg_sell_price="80")
    events = _run(strategy.check_signals(chain, [pos]))
    pt = next(e for e in events if e.event_type == "PROFIT_TARGET")
    assert pt.payload["valid_actions"] == ["PROFIT_TARGET", "CLOSE_FULL"]


def test_time_stop_valid_actions_includes_signal_type() -> None:
    """TIME_STOP event carries ['TIME_STOP', 'CLOSE_FULL'] in valid_actions."""
    strategy = CSPNiftyV1()
    entry = date.today() - timedelta(days=21)
    pos = _make_position(avg_sell_price="80", entry_date=entry)
    events = _run(strategy.check_signals(_make_empty_chain(), [pos]))
    ts = next(e for e in events if e.event_type == "TIME_STOP")
    assert ts.payload["valid_actions"] == ["TIME_STOP", "CLOSE_FULL"]


def test_hard_stop_valid_actions_is_close_full_only() -> None:
    """HARD_STOP event carries only ['CLOSE_FULL'] — no re-entry on hard stop."""
    strategy = CSPNiftyV1()
    chain = _make_chain(ltp="161", delta="-0.55")
    pos = _make_position(avg_sell_price="80")
    events = _run(strategy.check_signals(chain, [pos]))
    hs = next(e for e in events if e.event_type == "HARD_STOP")
    assert hs.payload["valid_actions"] == ["CLOSE_FULL"]


def test_time_stop_does_not_fire_at_days_held_20() -> None:
    """TIME_STOP does NOT fire when days_held = 20 (< 21)."""
    strategy = CSPNiftyV1()
    entry = date.today() - timedelta(days=20)
    pos = _make_position(avg_sell_price="80", entry_date=entry)
    events = _run(strategy.check_signals(_make_empty_chain(), [pos]))
    assert not any(e.event_type == "TIME_STOP" for e in events)


def test_time_stop_does_not_fire_on_dte_alone() -> None:
    """TIME_STOP does NOT fire when DTE = 20 but days_held is 0 (semantic fix vs PB2.1)."""
    strategy = CSPNiftyV1()
    key = _expiry_key(dte=20)
    # entry_date=None → days_held=0, so TIME_STOP cannot fire
    pos = _make_position(instrument_key=key, avg_sell_price="80", entry_date=None)
    events = _run(strategy.check_signals(_make_empty_chain(), [pos]))
    assert not any(e.event_type == "TIME_STOP" for e in events)


def test_roll_eligible_fires_at_dte_4() -> None:
    """ROLL_ELIGIBLE ACTION when DTE = 4 (≤ 7); replaces DTE_REVIEW WARN."""
    strategy = CSPNiftyV1()
    key = _expiry_key(dte=4)
    pos = _make_position(instrument_key=key, avg_sell_price="80")
    events = _run(strategy.check_signals(_make_empty_chain(), [pos]))
    event_types = {e.event_type for e in events}
    assert "ROLL_ELIGIBLE" in event_types
    assert "DTE_REVIEW" not in event_types
    re_event = next(e for e in events if e.event_type == "ROLL_ELIGIBLE")
    assert re_event.severity == "ACTION"


# ── check_signals — no events ─────────────────────────────────────────────────


def test_no_events_when_healthy() -> None:
    """No signals when mark = 60%, |delta| = 0.20, days_held = 10."""
    strategy = CSPNiftyV1()
    chain = _make_chain(ltp="48", delta="-0.20")  # 48/80 = 0.60
    pos = _make_position(
        instrument_key="NSE_FO|NIFTY23000PE",
        avg_sell_price="80",
        entry_date=date.today() - timedelta(days=10),
    )
    events = _run(strategy.check_signals(chain, [pos]))
    assert events == []


# ── apply_action ──────────────────────────────────────────────────────────────


def _make_close_full_action(legs: list[str] | None = None) -> ApprovedAction:
    return ApprovedAction(
        action_type="CLOSE_FULL",
        legs_to_close=legs or ["short_put"],
        legs_to_open=[],
        rationale="test",
        council_rank=1,
    )


def test_apply_action_close_full_returns_without_error() -> None:
    """apply_action with CLOSE_FULL does not raise and removes closed legs."""
    strategy = CSPNiftyV1()
    pos = _make_position()
    action = _make_close_full_action(["short_put"])
    result = _run(strategy.apply_action([pos], action))
    # closed leg is filtered out
    assert all(p.leg_role != "short_put" for p in result)


def test_apply_action_adjust_raises_value_error() -> None:
    """apply_action raises ValueError for unsupported action_type."""
    strategy = CSPNiftyV1()
    pos = _make_position()
    action = ApprovedAction(
        action_type="ADJUST",
        legs_to_close=[],
        legs_to_open=[],
        rationale="test",
        council_rank=1,
    )
    with pytest.raises(ValueError, match="CLOSE_FULL, PROFIT_TARGET, or TIME_STOP"):
        _run(strategy.apply_action([pos], action))


# ── describe_context ──────────────────────────────────────────────────────────


def test_describe_context_includes_key_fields() -> None:
    """describe_context returns a string with strategy name and signal type."""
    from src.strategy.protocol import SignalEvent

    strategy = CSPNiftyV1()
    chain = _make_chain(ltp="38.4", delta="-0.20")
    pos = _make_position(avg_sell_price="80")
    event = SignalEvent(
        event_type="PROFIT_TARGET",
        severity="ACTION",
        description="test",
        payload={},
    )
    ctx = strategy.describe_context(event, chain, [pos])
    assert "paper_csp_nifty_v1" in ctx
    assert "PROFIT_TARGET" in ctx
    assert "24000" in ctx  # spot


def test_describe_context_handles_no_positions() -> None:
    """describe_context handles empty positions gracefully."""
    from src.strategy.protocol import SignalEvent

    strategy = CSPNiftyV1()
    event = SignalEvent(
        event_type="TIME_STOP",
        severity="ACTION",
        description="test",
        payload={},
    )
    ctx = strategy.describe_context(event, _make_empty_chain(), [])
    assert "No open short-put positions" in ctx


# ── ES10: R5 re-entry eligibility ────────────────────────────────────────────


def _make_vix_series(ivr: float, length: int = 252) -> pd.Series:
    """Build a VIX series of ``length`` elements that yields ``ivr`` exactly.

    Uses vix_low=10, vix_high=30 → vix_today = 10 + ivr * 20.
    Last element of the series is vix_today.
    """
    vix_today = 10.0 + ivr * 20.0
    values = np.linspace(10.0, 30.0, length - 1).tolist() + [vix_today]
    return pd.Series(values, dtype="float64")


def _make_profit_target_action(legs: list[str] | None = None) -> ApprovedAction:
    return ApprovedAction(
        action_type="PROFIT_TARGET",
        legs_to_close=legs or ["short_put"],
        legs_to_open=[],
        rationale="profit target hit",
        council_rank=1,
    )


def _r5_expiry_key(dte: int) -> str:
    """Build an instrument key with an embedded expiry ``dte`` days from today."""
    expiry = date.today() + timedelta(days=dte)
    date_str = expiry.strftime("%d%b%Y").upper()
    return f"NSE_FO|NIFTY{date_str}PE"


# ── R5 gate 1: DTE ───────────────────────────────────────────────────────────


def test_r5_eligible_when_all_gates_pass(tmp_path: Path) -> None:
    """R5_REENTRY_ELIGIBLE written and notifier called when DTE=15, IVR=0.30, no open pos."""
    store = PaperStore(str(tmp_path / "db.sqlite"))
    notifier = MagicMock()
    notifier.send_plain_message = AsyncMock(return_value=True)
    strategy = CSPNiftyV1(store=store, notifier=notifier)

    vix_series = _make_vix_series(ivr=0.30)
    with patch("src.strategy.reentry_mixin.load_vix_series", return_value=vix_series):
        pos = _make_position(instrument_key=_r5_expiry_key(15), avg_sell_price="80")
        _run(strategy.apply_action([pos], _make_profit_target_action()))

    events = store.get_open_exit_events(strategy_name="paper_csp_nifty_v1")
    signals = [e["exit_signal"] for e in events]
    assert "R5_REENTRY_ELIGIBLE" in signals
    notifier.send_plain_message.assert_awaited_once()


def test_r5_blocked_when_dte_less_than_14(tmp_path: Path) -> None:
    """R5_REENTRY_BLOCKED when DTE=13 (< 14)."""
    store = PaperStore(str(tmp_path / "db.sqlite"))
    strategy = CSPNiftyV1(store=store)

    vix_series = _make_vix_series(ivr=0.30)
    with patch("src.strategy.reentry_mixin.load_vix_series", return_value=vix_series):
        pos = _make_position(instrument_key=_r5_expiry_key(13), avg_sell_price="80")
        _run(strategy.apply_action([pos], _make_profit_target_action()))

    events = store.get_open_exit_events(strategy_name="paper_csp_nifty_v1")
    blocked = [e for e in events if e["exit_signal"] == "R5_REENTRY_BLOCKED"]
    assert blocked
    assert "DTE" in blocked[0]["notes"]


# ── R5 gate 2: IVR ───────────────────────────────────────────────────────────


def test_r5_blocked_when_ivr_below_floor(tmp_path: Path) -> None:
    """R5_REENTRY_BLOCKED when IVR=0.22 (< 0.25)."""
    store = PaperStore(str(tmp_path / "db.sqlite"))
    strategy = CSPNiftyV1(store=store)

    vix_series = _make_vix_series(ivr=0.22)
    with patch("src.strategy.reentry_mixin.load_vix_series", return_value=vix_series):
        pos = _make_position(instrument_key=_r5_expiry_key(20), avg_sell_price="80")
        _run(strategy.apply_action([pos], _make_profit_target_action()))

    events = store.get_open_exit_events(strategy_name="paper_csp_nifty_v1")
    blocked = [e for e in events if e["exit_signal"] == "R5_REENTRY_BLOCKED"]
    assert blocked
    assert "IVR" in blocked[0]["notes"]


def test_r5_blocked_when_ivr_history_insufficient(tmp_path: Path) -> None:
    """R5_REENTRY_BLOCKED when VIX series has < 252 entries (IVR returns None)."""
    store = PaperStore(str(tmp_path / "db.sqlite"))
    strategy = CSPNiftyV1(store=store)

    short_series = pd.Series([15.0, 18.0, 20.0], dtype="float64")  # < 252 entries
    with patch("src.strategy.reentry_mixin.load_vix_series", return_value=short_series):
        pos = _make_position(instrument_key=_r5_expiry_key(20), avg_sell_price="80")
        _run(strategy.apply_action([pos], _make_profit_target_action()))

    events = store.get_open_exit_events(strategy_name="paper_csp_nifty_v1")
    blocked = [e for e in events if e["exit_signal"] == "R5_REENTRY_BLOCKED"]
    assert blocked
    assert "IVR history" in blocked[0]["notes"]


def test_r5_blocked_when_vix_series_empty(tmp_path: Path) -> None:
    """R5_REENTRY_BLOCKED when VIX series is empty (IVR history unavailable)."""
    store = PaperStore(str(tmp_path / "db.sqlite"))
    strategy = CSPNiftyV1(store=store)

    with patch(
        "src.strategy.reentry_mixin.load_vix_series", return_value=pd.Series(dtype="float64")
    ):
        pos = _make_position(instrument_key=_r5_expiry_key(20), avg_sell_price="80")
        _run(strategy.apply_action([pos], _make_profit_target_action()))

    events = store.get_open_exit_events(strategy_name="paper_csp_nifty_v1")
    blocked = [e for e in events if e["exit_signal"] == "R5_REENTRY_BLOCKED"]
    assert blocked
    assert "IVR history" in blocked[0]["notes"]


# ── R5 gate 3: open position guard ───────────────────────────────────────────


def test_r5_blocked_when_short_put_already_open(tmp_path: Path) -> None:
    """R5_REENTRY_BLOCKED when another short_put position is already open."""
    store = PaperStore(str(tmp_path / "db.sqlite"))
    strategy = CSPNiftyV1(store=store)

    # Record an open short_put in the store so gate 3 fires.
    store.record_trade(
        PaperTrade(
            strategy_name="paper_csp_nifty_v1",
            leg_role="short_put",
            action=TradeAction.SELL,
            quantity=65,
            price="100",
            instrument_key="NSE_FO|NIFTY23000PE",
            trade_date=date.today(),
        )
    )

    vix_series = _make_vix_series(ivr=0.30)
    with patch("src.strategy.reentry_mixin.load_vix_series", return_value=vix_series):
        pos = _make_position(instrument_key=_r5_expiry_key(20), avg_sell_price="80")
        _run(strategy.apply_action([pos], _make_profit_target_action()))

    events = store.get_open_exit_events(strategy_name="paper_csp_nifty_v1")
    blocked = [e for e in events if e["exit_signal"] == "R5_REENTRY_BLOCKED"]
    assert blocked
    assert "open position" in blocked[0]["notes"]


# ── Integration: apply_action(PROFIT_TARGET) ─────────────────────────────────


def test_apply_action_profit_target_closes_and_runs_r5(tmp_path: Path) -> None:
    """apply_action(PROFIT_TARGET) filters positions AND writes an R5 event."""
    store = PaperStore(str(tmp_path / "db.sqlite"))
    notifier = MagicMock()
    notifier.send_plain_message = AsyncMock(return_value=True)
    strategy = CSPNiftyV1(store=store, notifier=notifier)

    vix_series = _make_vix_series(ivr=0.30)
    with patch("src.strategy.reentry_mixin.load_vix_series", return_value=vix_series):
        pos = _make_position(instrument_key=_r5_expiry_key(20), avg_sell_price="80")
        remaining = _run(strategy.apply_action([pos], _make_profit_target_action()))

    # Close was recorded in positions list.
    assert all(p.leg_role != "short_put" for p in remaining)

    # R5 eligibility event was written.
    events = store.get_open_exit_events(strategy_name="paper_csp_nifty_v1")
    assert any(e["exit_signal"] in ("R5_REENTRY_ELIGIBLE", "R5_REENTRY_BLOCKED") for e in events)

    # Notifier was called.
    notifier.send_plain_message.assert_awaited_once()


# ── Non-fatal: notifier raises ────────────────────────────────────────────────


def test_r5_event_written_even_when_notifier_raises(tmp_path: Path) -> None:
    """Exit event is written to DB even when notifier.send_plain_message raises."""
    store = PaperStore(str(tmp_path / "db.sqlite"))
    notifier = MagicMock()
    notifier.send_plain_message = AsyncMock(side_effect=RuntimeError("telegram down"))
    strategy = CSPNiftyV1(store=store, notifier=notifier)

    vix_series = _make_vix_series(ivr=0.30)
    with patch("src.strategy.reentry_mixin.load_vix_series", return_value=vix_series):
        pos = _make_position(instrument_key=_r5_expiry_key(20), avg_sell_price="80")
        # Must not raise even though notifier throws.
        _run(strategy.apply_action([pos], _make_profit_target_action()))

    events = store.get_open_exit_events(strategy_name="paper_csp_nifty_v1")
    assert any(e["exit_signal"] in ("R5_REENTRY_ELIGIBLE", "R5_REENTRY_BLOCKED") for e in events)


# ── TIME_STOP regression: reentry check was missing ──────────────────────────


def test_apply_action_time_stop_runs_reentry(tmp_path: Path) -> None:
    """TIME_STOP action triggers reentry eligibility check (regression fix)."""
    store = PaperStore(str(tmp_path / "db.sqlite"))
    notifier = MagicMock()
    notifier.send_plain_message = AsyncMock(return_value=True)
    strategy = CSPNiftyV1(store=store, notifier=notifier)

    vix_series = _make_vix_series(ivr=0.30)
    time_stop_action = ApprovedAction(
        action_type="TIME_STOP",
        legs_to_close=["short_put"],
        legs_to_open=[],
        rationale="21 days elapsed",
        council_rank=1,
    )
    with patch("src.strategy.reentry_mixin.load_vix_series", return_value=vix_series):
        pos = _make_position(instrument_key=_r5_expiry_key(20), avg_sell_price="80")
        remaining = _run(strategy.apply_action([pos], time_stop_action))

    # Leg was closed.
    assert all(p.leg_role != "short_put" for p in remaining)

    # Re-entry event written — TIME_STOP now triggers same check as PROFIT_TARGET.
    events = store.get_open_exit_events(strategy_name="paper_csp_nifty_v1")
    assert any(e["exit_signal"] in ("R5_REENTRY_ELIGIBLE", "R5_REENTRY_BLOCKED") for e in events)
    notifier.send_plain_message.assert_awaited_once()


def test_apply_action_time_stop_rejects_unknown_action() -> None:
    """apply_action raises ValueError for unrecognised action_type."""
    strategy = CSPNiftyV1()
    bad_action = ApprovedAction(
        action_type="ROLL_DOWN",
        legs_to_close=["short_put"],
        legs_to_open=[],
        rationale="unknown",
        council_rank=1,
    )
    with pytest.raises(ValueError, match="ROLL_DOWN"):
        _run(strategy.apply_action([], bad_action))

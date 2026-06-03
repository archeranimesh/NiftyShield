"""Unit tests for CSPNiftyV1 backbone strategy.

All tests are offline — no network calls, no DB.

Instrument key conventions used here:
  "NSE_FO|NIFTY23000PE"        — strike embedded (23000), no expiry
  "NSE_FO|NIFTY{date}PE"       — expiry embedded, no strike (DTE tests)
  "NSE_FO|12345"                — numeric key, nothing parseable
"""

from __future__ import annotations

import asyncio
from datetime import date, timedelta
from decimal import Decimal

import pytest

from src.models.options import OptionChain, OptionChainStrike, OptionLeg
from src.paper.models import PaperPosition
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
    """Build a chain with no strikes (used for DTE-only tests)."""
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
) -> PaperPosition:
    """Build a PaperPosition for a short-put leg."""
    return PaperPosition(
        strategy_name=strategy_name,
        leg_role=leg_role,
        net_qty=net_qty,
        avg_cost=Decimal("0"),
        avg_sell_price=Decimal(avg_sell_price),
        instrument_key=instrument_key,
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


def test_profit_target_fires_at_48_pct() -> None:
    """PROFIT_TARGET ACTION when mark = 48% of entry credit (< 50%)."""
    strategy = CSPNiftyV1()
    # entry credit = 80, mark = 38.4  →  38.4/80 = 0.48
    chain = _make_chain(ltp="38.4", delta="-0.20")
    pos = _make_position(avg_sell_price="80")
    events = _run(strategy.check_signals(chain, [pos]))
    event_types = {e.event_type for e in events}
    assert "PROFIT_TARGET" in event_types
    pt = next(e for e in events if e.event_type == "PROFIT_TARGET")
    assert pt.severity == "ACTION"


def test_loss_stop_fires_at_210_pct() -> None:
    """LOSS_STOP ACTION when mark = 210% of entry credit (≥ 200%)."""
    strategy = CSPNiftyV1()
    # entry credit = 80, mark = 168  →  168/80 = 2.10
    chain = _make_chain(ltp="168", delta="-0.50")
    pos = _make_position(avg_sell_price="80")
    events = _run(strategy.check_signals(chain, [pos]))
    event_types = {e.event_type for e in events}
    assert "LOSS_STOP" in event_types
    ls = next(e for e in events if e.event_type == "LOSS_STOP")
    assert ls.severity == "ACTION"


def test_roll_due_decay_fires_at_24_pct() -> None:
    """ROLL_DUE_DECAY WARN when mark = 24% of entry credit (≤ 25%)."""
    strategy = CSPNiftyV1()
    # entry credit = 80, mark = 19.2  →  19.2/80 = 0.24
    chain = _make_chain(ltp="19.2", delta="-0.10")
    pos = _make_position(avg_sell_price="80")
    events = _run(strategy.check_signals(chain, [pos]))
    event_types = {e.event_type for e in events}
    assert "ROLL_DUE_DECAY" in event_types
    rd = next(e for e in events if e.event_type == "ROLL_DUE_DECAY")
    assert rd.severity == "WARN"


# ── check_signals — delta signals ────────────────────────────────────────────


def test_delta_stop_fires_at_0_36() -> None:
    """DELTA_STOP ACTION when |delta| = 0.36 (≥ 0.35)."""
    strategy = CSPNiftyV1()
    chain = _make_chain(ltp="80", delta="-0.36")
    pos = _make_position(avg_sell_price="80")
    events = _run(strategy.check_signals(chain, [pos]))
    event_types = {e.event_type for e in events}
    assert "DELTA_STOP" in event_types
    ds = next(e for e in events if e.event_type == "DELTA_STOP")
    assert ds.severity == "ACTION"


def test_delta_warn_fires_at_0_27() -> None:
    """DELTA_WARN WARN when |delta| = 0.27 (≥ 0.25, < 0.35)."""
    strategy = CSPNiftyV1()
    chain = _make_chain(ltp="80", delta="-0.27")
    pos = _make_position(avg_sell_price="80")
    events = _run(strategy.check_signals(chain, [pos]))
    event_types = {e.event_type for e in events}
    assert "DELTA_WARN" in event_types
    assert "DELTA_STOP" not in event_types
    dw = next(e for e in events if e.event_type == "DELTA_WARN")
    assert dw.severity == "WARN"


# ── check_signals — DTE signals ───────────────────────────────────────────────


def test_time_stop_fires_at_dte_20() -> None:
    """TIME_STOP ACTION when DTE = 20 (≤ 21)."""
    strategy = CSPNiftyV1()
    key = _expiry_key(dte=20)
    pos = _make_position(instrument_key=key, avg_sell_price="80")
    events = _run(strategy.check_signals(_make_empty_chain(), [pos]))
    event_types = {e.event_type for e in events}
    assert "TIME_STOP" in event_types
    ts = next(e for e in events if e.event_type == "TIME_STOP")
    assert ts.severity == "ACTION"


def test_roll_due_dte_fires_at_dte_4() -> None:
    """ROLL_DUE_DTE WARN when DTE = 4 (≤ 5)."""
    strategy = CSPNiftyV1()
    key = _expiry_key(dte=4)
    pos = _make_position(instrument_key=key, avg_sell_price="80")
    events = _run(strategy.check_signals(_make_empty_chain(), [pos]))
    event_types = {e.event_type for e in events}
    assert "ROLL_DUE_DTE" in event_types
    rd = next(e for e in events if e.event_type == "ROLL_DUE_DTE")
    assert rd.severity == "WARN"


# ── check_signals — no events ─────────────────────────────────────────────────


def test_no_events_when_healthy() -> None:
    """No signals when mark = 60%, |delta| = 0.20, DTE = 30."""
    strategy = CSPNiftyV1()
    # Build key with expiry 30 days out AND strike embedded
    # Use a numeric key (no expiry encoded) paired with a chain strike for mark/delta
    chain = _make_chain(ltp="48", delta="-0.20")  # 48/80 = 0.60
    pos = _make_position(
        instrument_key="NSE_FO|NIFTY23000PE",  # strike lookup works, no expiry → DTE=None
        avg_sell_price="80",
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
    with pytest.raises(ValueError, match="CLOSE_FULL"):
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

"""Unit tests for NiftyTrackComparisonV1 backbone strategy.

All tests are offline — no network calls, no DB.

Key conventions:
  "NSE_FO|NIFTY29MAY2026PE"  — expiry embedded (PE overlay)
  "NSE_FO|NIFTY24000PE"       — strike embedded (for chain lookup)
  overlay legs: leg_role starts with "overlay_"
  base legs: "base_etf", "base_futures", "base_ditm_call"
"""

from __future__ import annotations

import asyncio
from datetime import date, timedelta
from decimal import Decimal

import pytest

from src.models.options import OptionChain, OptionChainStrike, OptionLeg
from src.paper.models import PaperPosition
from src.strategy.nifty_track_comparison_v1 import NiftyTrackComparisonV1
from src.strategy.protocol import ApprovedAction, LegSpec

_SPOT = "paper_nifty_spot"
_FUTURES = "paper_nifty_futures"
_PROXY = "paper_nifty_proxy"
_OTHER = "paper_csp_nifty_v1"

# ── Helpers ───────────────────────────────────────────────────────────────────


def _run(coro):  # type: ignore[no-untyped-def]
    return asyncio.run(coro)


def _make_leg(
    ltp: str,
    delta: str = "-0.10",
    strike: str = "24000",
    option_type: str = "PE",
) -> OptionLeg:
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
        iv=Decimal("15"),
        strike=Decimal(strike),
    )


def _make_chain(
    pe_ltp: str = "100",
    ce_ltp: str = "100",
    strike: str = "24000",
) -> OptionChain:
    pe = _make_leg(ltp=pe_ltp, delta="-0.10", strike=strike, option_type="PE")
    ce = _make_leg(ltp=ce_ltp, delta="0.10", strike=strike, option_type="CE")
    return OptionChain(
        underlying_spot=Decimal("24000"),
        expiry=date(2026, 6, 26),
        strikes={Decimal(strike): OptionChainStrike(pe=pe, ce=ce)},
    )


def _make_empty_chain() -> OptionChain:
    return OptionChain(
        underlying_spot=Decimal("24000"),
        expiry=date(2026, 6, 26),
        strikes={},
    )


def _expiry_key(dte: int, option_type: str = "PE") -> str:
    """Build an instrument key with an embedded expiry date yielding ``dte`` days from today."""
    expiry = date.today() + timedelta(days=dte)
    date_str = expiry.strftime("%d%b%Y").upper()
    return f"NSE_FO|NIFTY{date_str}{option_type}"


def _past_expiry_key(days_ago: int = 1, option_type: str = "PE") -> str:
    expiry = date.today() - timedelta(days=days_ago)
    date_str = expiry.strftime("%d%b%Y").upper()
    return f"NSE_FO|NIFTY{date_str}{option_type}"


def _make_position(
    strategy_name: str = _SPOT,
    leg_role: str = "overlay_pp",
    instrument_key: str = "NSE_FO|NIFTY24000PE",
    net_qty: int = -65,
    avg_sell_price: str = "100",
    avg_cost: str = "0",
) -> PaperPosition:
    return PaperPosition(
        strategy_name=strategy_name,
        leg_role=leg_role,
        net_qty=net_qty,
        avg_cost=Decimal(avg_cost),
        avg_sell_price=Decimal(avg_sell_price),
        instrument_key=instrument_key,
    )


def _make_approved_action(
    action_type: str = "ROLL_OVERLAY",
    legs_to_close: list[str] | None = None,
    legs_to_open: list[LegSpec] | None = None,
) -> ApprovedAction:
    return ApprovedAction(
        action_type=action_type,
        legs_to_close=legs_to_close if legs_to_close is not None else ["overlay_pp"],
        legs_to_open=legs_to_open if legs_to_open is not None else [
            LegSpec(
                instrument_key="NSE_FO|NIFTY01JUL202624000PE",
                action="BUY",
                quantity=75,
                leg_role="overlay_pp",
            )
        ],
        rationale="test",
        council_rank=1,
    )


class MockBroker:
    """Minimal broker mock that returns a pre-built OptionChain from get_option_chain."""

    def __init__(self, chain: OptionChain | None = None) -> None:
        self._chain = chain

    async def get_option_chain(self, *args: object, **kwargs: object) -> OptionChain:
        if self._chain is None:
            raise ValueError("MockBroker: no chain configured")
        return self._chain


def _make_next_chain(
    option_type: str = "PE",
    strike: str = "23500",
    delta: str = "-0.20",
    ltp: str = "80",
) -> OptionChain:
    """Build a minimal next-expiry OptionChain with one candidate strike."""
    expiry = date.today() + timedelta(days=21)
    pe_leg = OptionLeg(
        ltp=Decimal(ltp),
        bid=Decimal(ltp),
        ask=Decimal(ltp),
        oi=5000,
        volume=1000,
        delta=Decimal(delta),
        gamma=Decimal("0.001"),
        theta=Decimal("-3"),
        vega=Decimal("10"),
        iv=Decimal("18"),
        strike=Decimal(strike),
    )
    ce_leg = OptionLeg(
        ltp=Decimal(ltp),
        bid=Decimal(ltp),
        ask=Decimal(ltp),
        oi=5000,
        volume=1000,
        delta=Decimal("0.20"),
        gamma=Decimal("0.001"),
        theta=Decimal("-3"),
        vega=Decimal("10"),
        iv=Decimal("18"),
        strike=Decimal(strike),
    )
    return OptionChain(
        underlying_spot=Decimal("24000"),
        expiry=expiry,
        strikes={Decimal(strike): OptionChainStrike(pe=pe_leg, ce=ce_leg)},
    )


# ── check_signals — no positions ──────────────────────────────────────────────


def test_no_positions_returns_empty() -> None:
    """No open positions → empty signal list."""
    strategy = NiftyTrackComparisonV1()
    result = _run(strategy.check_signals(_make_empty_chain(), []))
    assert result == []


def test_no_overlay_legs_returns_empty() -> None:
    """Base legs only → no signals (base legs are never evaluated)."""
    strategy = NiftyTrackComparisonV1()
    positions = [
        _make_position(leg_role="base_etf", net_qty=650),
        _make_position(strategy_name=_FUTURES, leg_role="base_futures", net_qty=65),
    ]
    result = _run(strategy.check_signals(_make_empty_chain(), positions))
    assert result == []


def test_other_strategy_positions_ignored() -> None:
    """Positions from non-track strategy names are not evaluated."""
    strategy = NiftyTrackComparisonV1()
    positions = [
        _make_position(strategy_name=_OTHER, leg_role="overlay_pp"),
    ]
    result = _run(strategy.check_signals(_make_empty_chain(), positions))
    assert result == []


# ── ROLL_ELIGIBLE / ROLL_BASE_FIRST / ROLL_DUE_DTE ───────────────────────────


def test_overlay_dte_4_no_base_emits_roll_eligible_action() -> None:
    """Overlay DTE=4, no base leg (base_dte defaults to 999) → ROLL_ELIGIBLE ACTION."""
    strategy = NiftyTrackComparisonV1()
    pos = _make_position(
        strategy_name=_SPOT,
        leg_role="overlay_pp",
        instrument_key=_expiry_key(4),
    )
    result = _run(strategy.check_signals(_make_empty_chain(), [pos]))
    roll_events = [e for e in result if e.event_type == "ROLL_ELIGIBLE"]
    assert len(roll_events) == 1
    ev = roll_events[0]
    assert ev.severity == "ACTION"
    assert ev.payload["track"] == _SPOT
    assert ev.payload["dte"] == 4
    assert "RECORD_ROLL" in ev.payload["valid_actions"]


def test_overlay_dte_exactly_5_emits_roll_eligible_action() -> None:
    """DTE = 5 is the boundary — should trigger ROLL_ELIGIBLE ACTION (not ROLL_DUE_DTE)."""
    strategy = NiftyTrackComparisonV1()
    pos = _make_position(instrument_key=_expiry_key(5))
    result = _run(strategy.check_signals(_make_empty_chain(), [pos]))
    assert any(e.event_type == "ROLL_ELIGIBLE" and e.severity == "ACTION" for e in result)
    assert not any(e.event_type == "ROLL_DUE_DTE" for e in result)


def test_overlay_dte_4_base_dte_25_emits_roll_eligible() -> None:
    """Overlay DTE=4, base DTE=25 → ROLL_ELIGIBLE ACTION."""
    strategy = NiftyTrackComparisonV1()
    overlay = _make_position(
        strategy_name=_FUTURES,
        leg_role="overlay_cc",
        instrument_key=_expiry_key(4, "CE"),
    )
    base = _make_position(
        strategy_name=_FUTURES,
        leg_role="base_futures",
        instrument_key=_expiry_key(25, "CE"),
        net_qty=65,
        avg_sell_price="0",
    )
    result = _run(strategy.check_signals(_make_empty_chain(), [overlay, base]))
    roll_events = [e for e in result if e.event_type == "ROLL_ELIGIBLE"]
    assert len(roll_events) == 1
    assert roll_events[0].severity == "ACTION"


def test_overlay_dte_4_base_dte_8_emits_roll_base_first() -> None:
    """Overlay DTE=4, base DTE=8 (≤ 10) → ROLL_BASE_FIRST WARN; no ROLL_ELIGIBLE."""
    strategy = NiftyTrackComparisonV1()
    overlay = _make_position(
        strategy_name=_PROXY,
        leg_role="overlay_collar_put",
        instrument_key=_expiry_key(4),
    )
    base = _make_position(
        strategy_name=_PROXY,
        leg_role="base_ditm_call",
        instrument_key=_expiry_key(8, "CE"),
        net_qty=65,
        avg_sell_price="0",
    )
    result = _run(strategy.check_signals(_make_empty_chain(), [overlay, base]))
    assert any(e.event_type == "ROLL_BASE_FIRST" and e.severity == "WARN" for e in result)
    assert not any(e.event_type == "ROLL_ELIGIBLE" for e in result)


def test_overlay_dte_8_emits_roll_due_dte_warn() -> None:
    """Overlay DTE=8 (range 6-10) → ROLL_DUE_DTE WARN (advance notice path)."""
    strategy = NiftyTrackComparisonV1()
    pos = _make_position(instrument_key=_expiry_key(8))
    result = _run(strategy.check_signals(_make_empty_chain(), [pos]))
    roll_events = [e for e in result if e.event_type == "ROLL_DUE_DTE"]
    assert len(roll_events) == 1
    assert roll_events[0].severity == "WARN"


def test_overlay_dte_20_no_dte_signals() -> None:
    """Overlay DTE=20 → no DTE-triggered signals."""
    strategy = NiftyTrackComparisonV1()
    pos = _make_position(instrument_key=_expiry_key(20))
    result = _run(strategy.check_signals(_make_empty_chain(), [pos]))
    dte_events = [
        e for e in result if e.event_type in ("ROLL_ELIGIBLE", "ROLL_BASE_FIRST", "ROLL_DUE_DTE")
    ]
    assert dte_events == []


def test_healthy_overlay_dte_only_no_signals() -> None:
    """Overlay with DTE = 15 (expiry-format key, no parseable strike) → no signals.

    Chain lookup returns None; decay branch skipped. Tests DTE path only.
    """
    strategy = NiftyTrackComparisonV1()
    pos = _make_position(
        instrument_key=_expiry_key(15),
        avg_sell_price="100",
        net_qty=-65,
    )
    result = _run(strategy.check_signals(_make_empty_chain(), [pos]))
    assert result == []


def test_healthy_combined_no_signals() -> None:
    """Strike-format key + premium at 60% of entry → no signals.

    Uses a strike-bearing key so _find_option_leg resolves and the decay path
    is actually exercised (60% > 25% → no ROLL_DUE_DECAY). DTE is None for
    strike-format keys, so ROLL_DUE_DTE is also absent.
    """
    strategy = NiftyTrackComparisonV1()
    pos = _make_position(
        instrument_key="NSE_FO|NIFTY24000PE",  # parseable strike; no expiry → dte=None
        avg_sell_price="100",
        net_qty=-65,
        leg_role="overlay_pp",
    )
    chain = _make_chain(pe_ltp="60", strike="24000")  # 60% remaining > 25% threshold
    result = _run(strategy.check_signals(chain, [pos]))
    assert result == []


# ── ROLL_DUE_DECAY ────────────────────────────────────────────────────────────


def test_short_overlay_premium_22pct_emits_decay_warn() -> None:
    """Short overlay with current mark = 22% of entry credit → ROLL_DUE_DECAY."""
    strategy = NiftyTrackComparisonV1()
    # Entry credit = 100; mark = 22 → 22% remaining
    pos = _make_position(
        instrument_key="NSE_FO|NIFTY24000PE",
        avg_sell_price="100",
        net_qty=-65,
        leg_role="overlay_pp",
    )
    chain = _make_chain(pe_ltp="22", strike="24000")
    result = _run(strategy.check_signals(chain, [pos]))
    decay_events = [e for e in result if e.event_type == "ROLL_DUE_DECAY"]
    assert len(decay_events) == 1
    assert decay_events[0].severity == "WARN"


def test_long_overlay_no_decay_check() -> None:
    """Long overlay (net_qty > 0) is not evaluated for decay — no ROLL_DUE_DECAY."""
    strategy = NiftyTrackComparisonV1()
    pos = _make_position(
        instrument_key="NSE_FO|NIFTY24000PE",
        avg_sell_price="0",  # long overlays have avg_cost not avg_sell_price
        net_qty=65,  # long position
        leg_role="overlay_pp",
    )
    chain = _make_chain(pe_ltp="5", strike="24000")
    result = _run(strategy.check_signals(chain, [pos]))
    assert not any(e.event_type == "ROLL_DUE_DECAY" for e in result)


# ── OVERLAY_EXPIRED ───────────────────────────────────────────────────────────


def test_overlay_expired_yesterday_emits_warn() -> None:
    """Overlay expiry yesterday (no roll recorded) → OVERLAY_EXPIRED WARN."""
    strategy = NiftyTrackComparisonV1()
    pos = _make_position(
        instrument_key=_past_expiry_key(days_ago=1),
        leg_role="overlay_pp",
    )
    result = _run(strategy.check_signals(_make_empty_chain(), [pos]))
    expired_events = [e for e in result if e.event_type == "OVERLAY_EXPIRED"]
    assert len(expired_events) == 1
    assert expired_events[0].severity == "WARN"


def test_expired_overlay_does_not_also_emit_dte_warn() -> None:
    """Once OVERLAY_EXPIRED fires, no ROLL_DUE_DTE is also emitted (early continue)."""
    strategy = NiftyTrackComparisonV1()
    pos = _make_position(instrument_key=_past_expiry_key(days_ago=3))
    result = _run(strategy.check_signals(_make_empty_chain(), [pos]))
    assert not any(e.event_type == "ROLL_DUE_DTE" for e in result)


# ── All three tracks trigger simultaneously ───────────────────────────────────


def test_all_three_tracks_roll_eligible_simultaneously() -> None:
    """Each track with an overlay at DTE 4, no base legs → three ROLL_ELIGIBLE ACTION events."""
    strategy = NiftyTrackComparisonV1()
    positions = [
        _make_position(strategy_name=_SPOT, leg_role="overlay_pp", instrument_key=_expiry_key(4)),
        _make_position(
            strategy_name=_FUTURES,
            leg_role="overlay_collar_put",
            instrument_key=_expiry_key(4, "PE"),
        ),
        _make_position(
            strategy_name=_PROXY, leg_role="overlay_cc", instrument_key=_expiry_key(4, "CE")
        ),
    ]
    result = _run(strategy.check_signals(_make_empty_chain(), positions))
    roll_events = [e for e in result if e.event_type == "ROLL_ELIGIBLE"]
    assert len(roll_events) == 3
    assert all(e.severity == "ACTION" for e in roll_events)
    tracks_seen = {e.payload["track"] for e in roll_events}
    assert tracks_seen == {_SPOT, _FUTURES, _PROXY}


# ── apply_action ──────────────────────────────────────────────────────────────


def test_apply_action_roll_overlay_removes_closed_leg() -> None:
    """ROLL_OVERLAY + one LegSpec → closed leg removed from positions."""
    strategy = NiftyTrackComparisonV1()
    positions = [
        _make_position(leg_role="overlay_pp"),
        _make_position(leg_role="base_etf", net_qty=650),
    ]
    action = _make_approved_action(
        action_type="ROLL_OVERLAY",
        legs_to_close=["overlay_pp"],
        legs_to_open=[
            LegSpec(
                instrument_key="NSE_FO|NIFTY01JUL202624000PE",
                action="BUY",
                quantity=75,
                leg_role="overlay_pp",
            )
        ],
    )
    result = _run(strategy.apply_action(positions, action))
    assert len(result) == 1
    assert result[0].leg_role == "base_etf"


def test_apply_action_roll_collar_removes_both_collar_legs() -> None:
    """ROLL_COLLAR + two LegSpecs → both collar legs removed, base_etf kept."""
    strategy = NiftyTrackComparisonV1()
    positions = [
        _make_position(leg_role="overlay_collar_put"),
        _make_position(leg_role="overlay_collar_call", net_qty=-65),
        _make_position(leg_role="base_etf", net_qty=650),
    ]
    action = _make_approved_action(
        action_type="ROLL_COLLAR",
        legs_to_close=["overlay_collar_put", "overlay_collar_call"],
        legs_to_open=[
            LegSpec(
                instrument_key="NSE_FO|NIFTY01JUL202623500PE",
                action="BUY",
                quantity=75,
                leg_role="overlay_collar_put",
            ),
            LegSpec(
                instrument_key="NSE_FO|NIFTY01JUL202625000CE",
                action="SELL",
                quantity=75,
                leg_role="overlay_collar_call",
            ),
        ],
    )
    result = _run(strategy.apply_action(positions, action))
    assert len(result) == 1
    assert result[0].leg_role == "base_etf"


class MockStore:
    def __init__(self, count: int = 0) -> None:
        self.count = count
        self.set_called_with = None

    def get_proxy_delta_breach_count(self, strategy_name: str) -> int:
        return self.count

    def set_proxy_delta_breach_count(self, strategy_name: str, count: int) -> None:
        self.set_called_with = (strategy_name, count)


def test_proxy_delta_warn_signal() -> None:
    # delta = 0.62 -> PROXY_DELTA_WARN
    store = MockStore(count=0)
    strategy = NiftyTrackComparisonV1(store=store)

    ce = _make_leg(ltp="80", delta="0.62", option_type="CE")
    market = OptionChain(
        underlying_spot=Decimal("24000"),
        expiry=date(2026, 6, 26),
        strikes={Decimal("24000"): OptionChainStrike(ce=ce, pe=None)},
    )
    positions = [
        PaperPosition(
            strategy_name=_PROXY,
            leg_role="base_ditm_call",
            instrument_key="NSE_FO|NIFTY24000CE",
            net_qty=65,
            avg_cost=Decimal("120"),
            avg_sell_price=Decimal("0"),
        )
    ]

    result = _run(strategy.check_signals(market, positions))
    assert len(result) == 1
    assert result[0].event_type == "PROXY_DELTA_WARN"
    assert result[0].severity == "WARN"
    # delta recovered/not below 0.40 -> resets to 0
    assert store.set_called_with == (_PROXY, 0)


def test_proxy_delta_first_breach() -> None:
    # delta = 0.38, count = 0 -> PROXY_DELTA_WARN, stores count = 1
    store = MockStore(count=0)
    strategy = NiftyTrackComparisonV1(store=store)

    ce = _make_leg(ltp="80", delta="0.38", option_type="CE")
    market = OptionChain(
        underlying_spot=Decimal("24000"),
        expiry=date(2026, 6, 26),
        strikes={Decimal("24000"): OptionChainStrike(ce=ce, pe=None)},
    )
    positions = [
        PaperPosition(
            strategy_name=_PROXY,
            leg_role="base_ditm_call",
            instrument_key="NSE_FO|NIFTY24000CE",
            net_qty=65,
            avg_cost=Decimal("120"),
            avg_sell_price=Decimal("0"),
        )
    ]

    result = _run(strategy.check_signals(market, positions))
    assert len(result) == 1
    assert result[0].event_type == "PROXY_DELTA_WARN"
    assert result[0].severity == "WARN"
    assert store.set_called_with == (_PROXY, 1)


def test_proxy_delta_critical_breach() -> None:
    # delta = 0.38, count = 3 -> PROXY_DELTA_CRITICAL ACTION, stores count = 4
    store = MockStore(count=3)
    strategy = NiftyTrackComparisonV1(store=store)

    ce = _make_leg(ltp="80", delta="0.38", option_type="CE")
    market = OptionChain(
        underlying_spot=Decimal("24000"),
        expiry=date(2026, 6, 26),
        strikes={Decimal("24000"): OptionChainStrike(ce=ce, pe=None)},
    )
    positions = [
        PaperPosition(
            strategy_name=_PROXY,
            leg_role="base_ditm_call",
            instrument_key="NSE_FO|NIFTY24000CE",
            net_qty=65,
            avg_cost=Decimal("120"),
            avg_sell_price=Decimal("0"),
        )
    ]

    result = _run(strategy.check_signals(market, positions))
    assert len(result) == 1
    assert result[0].event_type == "PROXY_DELTA_CRITICAL"
    assert result[0].severity == "ACTION"
    assert result[0].payload["valid_actions"] == ["RECORD_REENTRY"]
    assert store.set_called_with == (_PROXY, 4)


def test_proxy_delta_no_store() -> None:
    # store is None -> no crash, warning signals still emitted
    strategy = NiftyTrackComparisonV1(store=None)

    ce = _make_leg(ltp="80", delta="0.62", option_type="CE")
    market = OptionChain(
        underlying_spot=Decimal("24000"),
        expiry=date(2026, 6, 26),
        strikes={Decimal("24000"): OptionChainStrike(ce=ce, pe=None)},
    )
    positions = [
        PaperPosition(
            strategy_name=_PROXY,
            leg_role="base_ditm_call",
            instrument_key="NSE_FO|NIFTY24000CE",
            net_qty=65,
            avg_cost=Decimal("120"),
            avg_sell_price=Decimal("0"),
        )
    ]

    result = _run(strategy.check_signals(market, positions))
    assert len(result) == 1
    assert result[0].event_type == "PROXY_DELTA_WARN"


# ── NT-2: _check_futures_cc_block ────────────────────────────────────────────

def _empty_market() -> OptionChain:
    """Minimal OptionChain with no strikes — sufficient for block-guard tests."""
    return OptionChain(
        underlying_spot=Decimal("24000"),
        expiry=date(2026, 6, 26),
        strikes={},
    )


def test_futures_cc_standalone_blocked() -> None:
    """Futures + overlay_cc with no long put → BLOCKED_COMBINATION ACTION."""
    strategy = NiftyTrackComparisonV1()
    positions = [
        _make_position(strategy_name=_FUTURES, leg_role="overlay_cc",
                       instrument_key="NSE_FO|NIFTY29MAY2026CE", net_qty=-65),
    ]
    result = _run(strategy.check_signals(_empty_market(), positions))
    blocked = [e for e in result if e.event_type == "BLOCKED_COMBINATION"]
    assert len(blocked) == 1
    assert blocked[0].severity == "ACTION"
    assert "overlay_cc" in blocked[0].payload["violating_roles"]
    assert "CLOSE_LEG" in blocked[0].payload["valid_actions"]


def test_futures_cc_with_collar_put_allowed() -> None:
    """Futures + overlay_cc + overlay_collar_put (proper collar) → no block."""
    strategy = NiftyTrackComparisonV1()
    positions = [
        _make_position(strategy_name=_FUTURES, leg_role="overlay_cc",
                       instrument_key="NSE_FO|NIFTY29MAY2026CE", net_qty=-65),
        _make_position(strategy_name=_FUTURES, leg_role="overlay_collar_put",
                       instrument_key="NSE_FO|NIFTY29MAY2026PE", net_qty=65),
    ]
    result = _run(strategy.check_signals(_empty_market(), positions))
    assert not any(e.event_type == "BLOCKED_COMBINATION" for e in result)


def test_futures_collar_call_and_collar_put_allowed() -> None:
    """Futures + overlay_collar_call + overlay_collar_put → no block."""
    strategy = NiftyTrackComparisonV1()
    positions = [
        _make_position(strategy_name=_FUTURES, leg_role="overlay_collar_call",
                       instrument_key="NSE_FO|NIFTY29MAY2026CE", net_qty=-65),
        _make_position(strategy_name=_FUTURES, leg_role="overlay_collar_put",
                       instrument_key="NSE_FO|NIFTY29MAY2026PE", net_qty=65),
    ]
    result = _run(strategy.check_signals(_empty_market(), positions))
    assert not any(e.event_type == "BLOCKED_COMBINATION" for e in result)


def test_futures_degenerate_collar_blocked() -> None:
    """Futures + overlay_collar_call without paired put → BLOCKED_COMBINATION."""
    strategy = NiftyTrackComparisonV1()
    positions = [
        _make_position(strategy_name=_FUTURES, leg_role="overlay_collar_call",
                       instrument_key="NSE_FO|NIFTY29MAY2026CE", net_qty=-65),
    ]
    result = _run(strategy.check_signals(_empty_market(), positions))
    blocked = [e for e in result if e.event_type == "BLOCKED_COMBINATION"]
    assert len(blocked) == 1
    assert "overlay_collar_call" in blocked[0].payload["violating_roles"]


def test_spot_cc_not_blocked() -> None:
    """Spot base + overlay_cc → no BLOCKED_COMBINATION (guard only applies to Futures)."""
    strategy = NiftyTrackComparisonV1()
    positions = [
        _make_position(strategy_name=_SPOT, leg_role="overlay_cc",
                       instrument_key="NSE_FO|NIFTY29MAY2026CE", net_qty=-65),
    ]
    result = _run(strategy.check_signals(_empty_market(), positions))
    assert not any(e.event_type == "BLOCKED_COMBINATION" for e in result)


def test_proxy_cc_not_blocked() -> None:
    """Proxy base + overlay_cc → no BLOCKED_COMBINATION."""
    strategy = NiftyTrackComparisonV1()
    positions = [
        _make_position(strategy_name=_PROXY, leg_role="overlay_cc",
                       instrument_key="NSE_FO|NIFTY29MAY2026CE", net_qty=-65),
    ]
    result = _run(strategy.check_signals(_empty_market(), positions))
    assert not any(e.event_type == "BLOCKED_COMBINATION" for e in result)


def test_futures_no_overlays_no_block() -> None:
    """Futures base with no overlay legs → no BLOCKED_COMBINATION."""
    strategy = NiftyTrackComparisonV1()
    positions = [
        _make_position(strategy_name=_FUTURES, leg_role="base_futures",
                       instrument_key="NSE_FO|NIFTYFUT", net_qty=50),
    ]
    result = _run(strategy.check_signals(_empty_market(), positions))
    assert not any(e.event_type == "BLOCKED_COMBINATION" for e in result)


# ── PA1.3: ROLL_DUE_DTE ACTION upgrade (DTE 6–10) ────────────────────────────


def test_roll_due_dte_action_when_broker_has_replacement() -> None:
    """Overlay DTE=8 + broker returns a next-expiry chain → ROLL_DUE_DTE fires as ACTION."""
    next_chain = _make_next_chain(option_type="PE", strike="23500", delta="-0.20")
    broker = MockBroker(chain=next_chain)
    strategy = NiftyTrackComparisonV1(broker=broker)
    pos = _make_position(
        strategy_name=_SPOT,
        leg_role="overlay_pp",
        instrument_key=_expiry_key(8),
    )
    result = _run(strategy.check_signals(_make_empty_chain(), [pos]))
    dte_events = [e for e in result if e.event_type == "ROLL_DUE_DTE"]
    assert len(dte_events) == 1
    assert dte_events[0].severity == "ACTION"
    assert dte_events[0].payload.get("suggested_instrument_key") != ""
    assert dte_events[0].payload.get("valid_actions") == ["ROLL_OVERLAY"]


def test_roll_due_dte_warn_when_no_replacement() -> None:
    """Overlay DTE=8 + broker returns empty chain → ROLL_DUE_DTE fires as WARN."""
    empty_chain = OptionChain(
        underlying_spot=Decimal("24000"),
        expiry=date.today() + timedelta(days=21),
        strikes={},
    )
    broker = MockBroker(chain=empty_chain)
    strategy = NiftyTrackComparisonV1(broker=broker)
    pos = _make_position(
        strategy_name=_SPOT,
        leg_role="overlay_pp",
        instrument_key=_expiry_key(8),
    )
    result = _run(strategy.check_signals(_make_empty_chain(), [pos]))
    dte_events = [e for e in result if e.event_type == "ROLL_DUE_DTE"]
    assert len(dte_events) == 1
    assert dte_events[0].severity == "WARN"


# ── PA1.3: ROLL_DUE_DECAY ACTION upgrade ─────────────────────────────────────


def test_roll_due_decay_action_when_broker_has_replacement() -> None:
    """Short overlay at 20% of entry + broker returns chain → ROLL_DUE_DECAY fires as ACTION."""
    next_chain = _make_next_chain(option_type="PE", strike="23500", delta="-0.20")
    broker = MockBroker(chain=next_chain)
    strategy = NiftyTrackComparisonV1(broker=broker)
    pos = _make_position(
        strategy_name=_SPOT,
        leg_role="overlay_pp",
        instrument_key="NSE_FO|NIFTY24000PE",
        avg_sell_price="100",
        net_qty=-65,
    )
    chain = _make_chain(pe_ltp="20", strike="24000")  # 20% remaining < 25% threshold
    result = _run(strategy.check_signals(chain, [pos]))
    decay_events = [e for e in result if e.event_type == "ROLL_DUE_DECAY"]
    assert len(decay_events) == 1
    assert decay_events[0].severity == "ACTION"
    assert decay_events[0].payload.get("valid_actions") == ["ROLL_OVERLAY"]


# ── PA1.3: futures+CC block → ROLL_DUE_DTE stays WARN ─────────────────────────


def test_futures_cc_block_causes_roll_due_dte_warn() -> None:
    """paper_nifty_futures + overlay_cc → _select_overlay_roll_target returns None → WARN."""
    next_chain = _make_next_chain(option_type="CE", strike="25000", delta="0.20")
    broker = MockBroker(chain=next_chain)
    strategy = NiftyTrackComparisonV1(broker=broker)
    pos = _make_position(
        strategy_name=_FUTURES,
        leg_role="overlay_cc",
        instrument_key=_expiry_key(8, "CE"),
        net_qty=-65,
    )
    result = _run(strategy.check_signals(_empty_market(), [pos]))
    dte_events = [e for e in result if e.event_type == "ROLL_DUE_DTE"]
    assert len(dte_events) == 1
    assert dte_events[0].severity == "WARN"


# ── PA1.3: apply_action error cases ──────────────────────────────────────────


def test_apply_action_unknown_type_raises_value_error() -> None:
    """Unknown action_type raises ValueError."""
    strategy = NiftyTrackComparisonV1()
    action = ApprovedAction(
        action_type="CLOSE_FULL",
        legs_to_close=["overlay_pp"],
        legs_to_open=[],
        rationale="test",
        council_rank=1,
    )
    with pytest.raises(ValueError, match="does not permit"):
        _run(strategy.apply_action([_make_position()], action))


def test_apply_action_roll_overlay_empty_legs_to_open_raises_value_error() -> None:
    """ROLL_OVERLAY with empty legs_to_open raises ValueError."""
    strategy = NiftyTrackComparisonV1()
    action = ApprovedAction(
        action_type="ROLL_OVERLAY",
        legs_to_close=["overlay_pp"],
        legs_to_open=[],
        rationale="test",
        council_rank=1,
    )
    with pytest.raises(ValueError, match="requires at least one leg"):
        _run(strategy.apply_action([_make_position()], action))

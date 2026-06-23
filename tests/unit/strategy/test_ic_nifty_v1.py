"""Unit tests for IronCondorV1 backbone strategy.

All tests are offline — no network calls, no DB.

Instrument key conventions:
  "NSE_FO|NIFTY22000PE"   — short put strike 22000 (no expiry)
  "NSE_FO|NIFTY21500PE"   — long put hedge strike 21500
  "NSE_FO|NIFTY25000CE"   — short call strike 25000
  "NSE_FO|NIFTY25500CE"   — long call hedge strike 25500
  "NSE_FO|NIFTY{date}PE"  — expiry-embedded key for DTE tests
"""

from __future__ import annotations

import asyncio
from datetime import date, timedelta
from decimal import Decimal

import pytest

from src.models.options import OptionChain, OptionChainStrike, OptionLeg
from src.paper.models import PaperPosition
from src.strategy.ic_nifty_v1 import IronCondorV1
from src.strategy.protocol import ApprovedAction

_STRATEGY = "paper_ic_nifty_v1"
_OTHER_STRATEGY = "paper_other_v1"

# ── Default instrument keys ───────────────────────────────────────────────────

_SHORT_PUT_KEY = "NSE_FO|NIFTY22000PE"
_LONG_PUT_KEY = "NSE_FO|NIFTY21500PE"
_SHORT_CALL_KEY = "NSE_FO|NIFTY25000CE"
_LONG_CALL_KEY = "NSE_FO|NIFTY25500CE"

# Default entry credits / costs (net credit = 60 + 50 - 5 - 5 = 100)
_SHORT_PUT_SELL = "60"
_SHORT_CALL_SELL = "50"
_LONG_PUT_COST = "5"
_LONG_CALL_COST = "5"

# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_leg(
    ltp: str,
    delta: str,
    strike: str,
    iv: str = "18.0",
) -> OptionLeg:
    """Build a minimal OptionLeg."""
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


def _make_chain(
    short_put_ltp: str = "30",
    short_put_delta: str = "-0.15",
    long_put_ltp: str = "3",
    short_call_ltp: str = "25",
    short_call_delta: str = "0.10",
    long_call_ltp: str = "2",
) -> OptionChain:
    """Build a 4-strike IC chain with the given leg prices and deltas."""
    return OptionChain(
        underlying_spot=Decimal("24000"),
        expiry=date(2026, 6, 26),
        strikes={
            Decimal("21500"): OptionChainStrike(
                pe=_make_leg(ltp=long_put_ltp, delta="-0.05", strike="21500")
            ),
            Decimal("22000"): OptionChainStrike(
                pe=_make_leg(ltp=short_put_ltp, delta=short_put_delta, strike="22000")
            ),
            Decimal("25000"): OptionChainStrike(
                ce=_make_leg(ltp=short_call_ltp, delta=short_call_delta, strike="25000")
            ),
            Decimal("25500"): OptionChainStrike(
                ce=_make_leg(ltp=long_call_ltp, delta="0.04", strike="25500")
            ),
        },
    )


def _make_empty_chain() -> OptionChain:
    return OptionChain(
        underlying_spot=Decimal("24000"),
        expiry=date(2026, 6, 26),
        strikes={},
    )


def _make_position(
    leg_role: str,
    instrument_key: str,
    avg_sell_price: str = "0",
    avg_cost: str = "0",
    net_qty: int = -65,
    strategy_name: str = _STRATEGY,
) -> PaperPosition:
    return PaperPosition(
        strategy_name=strategy_name,
        leg_role=leg_role,
        net_qty=net_qty,
        avg_cost=Decimal(avg_cost),
        avg_sell_price=Decimal(avg_sell_price),
        instrument_key=instrument_key,
    )


def _make_ic_positions(
    short_put_key: str = _SHORT_PUT_KEY,
    long_put_key: str = _LONG_PUT_KEY,
    short_call_key: str = _SHORT_CALL_KEY,
    long_call_key: str = _LONG_CALL_KEY,
    strategy_name: str = _STRATEGY,
) -> list[PaperPosition]:
    """Build a standard 4-leg IC position set.

    Entry credit = 60 + 50 - 5 - 5 = 100 points.
    """
    return [
        _make_position(
            leg_role="short_put",
            instrument_key=short_put_key,
            avg_sell_price=_SHORT_PUT_SELL,
            net_qty=-65,
            strategy_name=strategy_name,
        ),
        _make_position(
            leg_role="long_put_hedge",
            instrument_key=long_put_key,
            avg_cost=_LONG_PUT_COST,
            net_qty=65,
            strategy_name=strategy_name,
        ),
        _make_position(
            leg_role="short_call",
            instrument_key=short_call_key,
            avg_sell_price=_SHORT_CALL_SELL,
            net_qty=-65,
            strategy_name=strategy_name,
        ),
        _make_position(
            leg_role="long_call_hedge",
            instrument_key=long_call_key,
            avg_cost=_LONG_CALL_COST,
            net_qty=65,
            strategy_name=strategy_name,
        ),
    ]


def _make_approved_action(action_type: str) -> ApprovedAction:
    return ApprovedAction(
        action_type=action_type,
        legs_to_close=[],
        legs_to_open=[],
        rationale="test",
        council_rank=1,
    )


# ── Tests ─────────────────────────────────────────────────────────────────────


def test_no_open_positions_returns_empty() -> None:
    """No IC positions → empty signal list."""
    strat = IronCondorV1()
    result = asyncio.run(strat.check_signals(_make_chain(), []))
    assert result == []


def test_other_strategy_positions_ignored() -> None:
    """Positions for a different strategy do not trigger signals."""
    strat = IronCondorV1()
    positions = _make_ic_positions(strategy_name=_OTHER_STRATEGY)
    result = asyncio.run(strat.check_signals(_make_chain(), positions))
    assert result == []


def test_profit_target_fires_when_mark_at_50_pct() -> None:
    """Combined mark ≤ 50% of entry credit → PROFIT_TARGET ACTION.

    Entry credit = 100. Combined mark = 28 + 23 - 3 - 2 = 46 ≤ 50.
    """
    strat = IronCondorV1()
    chain = _make_chain(
        short_put_ltp="28",
        long_put_ltp="3",
        short_call_ltp="23",
        long_call_ltp="2",
    )
    positions = _make_ic_positions()
    events = asyncio.run(strat.check_signals(chain, positions))
    types = [e.event_type for e in events]
    assert "PROFIT_TARGET" in types
    pt = next(e for e in events if e.event_type == "PROFIT_TARGET")
    assert pt.severity == "ACTION"


def test_loss_stop_fires_when_mark_at_200_pct() -> None:
    """Combined mark ≥ 200% of entry credit → LOSS_STOP ACTION.

    Entry credit = 100. Combined mark = 105 + 105 - 5 - 5 = 200 ≥ 200.
    """
    strat = IronCondorV1()
    chain = _make_chain(
        short_put_ltp="105",
        long_put_ltp="5",
        short_call_ltp="105",
        long_call_ltp="5",
    )
    positions = _make_ic_positions()
    events = asyncio.run(strat.check_signals(chain, positions))
    types = [e.event_type for e in events]
    assert "LOSS_STOP" in types
    ls = next(e for e in events if e.event_type == "LOSS_STOP")
    assert ls.severity == "ACTION"


def test_delta_stop_fires_on_short_call_breach() -> None:
    """Short call |delta| = 0.36 ≥ 0.35 → DELTA_STOP ACTION."""
    strat = IronCondorV1()
    chain = _make_chain(short_call_delta="0.36")
    positions = _make_ic_positions()
    events = asyncio.run(strat.check_signals(chain, positions))
    types = [e.event_type for e in events]
    assert "DELTA_STOP" in types
    ds = next(e for e in events if e.event_type == "DELTA_STOP")
    assert ds.severity == "ACTION"
    assert ds.payload["leg_role"] == "short_call"


def test_delta_stop_fires_on_short_put_breach() -> None:
    """Short put |delta| = 0.36 ≥ 0.35 → DELTA_STOP ACTION (either leg)."""
    strat = IronCondorV1()
    chain = _make_chain(short_put_delta="-0.36")
    positions = _make_ic_positions()
    events = asyncio.run(strat.check_signals(chain, positions))
    types = [e.event_type for e in events]
    assert "DELTA_STOP" in types
    ds = next(e for e in events if e.event_type == "DELTA_STOP")
    assert ds.severity == "ACTION"
    assert ds.payload["leg_role"] == "short_put"


def test_time_stop_fires_at_dte_13() -> None:
    """DTE = 13 ≤ 14 → TIME_STOP ACTION."""
    strat = IronCondorV1()
    expiry = date.today() + timedelta(days=13)
    date_str = expiry.strftime("%d%b%Y").upper()
    positions = _make_ic_positions(
        short_put_key=f"NSE_FO|NIFTY{date_str}PE",
        long_put_key=f"NSE_FO|NIFTY{date_str}PE",
        short_call_key=f"NSE_FO|NIFTY{date_str}CE",
        long_call_key=f"NSE_FO|NIFTY{date_str}CE",
    )
    events = asyncio.run(strat.check_signals(_make_empty_chain(), positions))
    types = [e.event_type for e in events]
    assert "TIME_STOP" in types
    ts = next(e for e in events if e.event_type == "TIME_STOP")
    assert ts.severity == "ACTION"


def test_delta_warn_fires_on_short_call_at_0_27() -> None:
    """Short call |delta| = 0.27 ≥ 0.25 → DELTA_WARN WARN."""
    strat = IronCondorV1()
    chain = _make_chain(short_call_delta="0.27")
    positions = _make_ic_positions()
    events = asyncio.run(strat.check_signals(chain, positions))
    types = [e.event_type for e in events]
    assert "DELTA_WARN" in types
    dw = next(e for e in events if e.event_type == "DELTA_WARN")
    assert dw.severity == "WARN"
    assert dw.payload["leg_role"] == "short_call"


def test_dte_warn_fires_at_dte_19() -> None:
    """DTE = 19 ≤ 21 → DTE_WARN INFO."""
    strat = IronCondorV1()
    expiry = date.today() + timedelta(days=19)
    date_str = expiry.strftime("%d%b%Y").upper()
    positions = _make_ic_positions(
        short_put_key=f"NSE_FO|NIFTY{date_str}PE",
        long_put_key=f"NSE_FO|NIFTY{date_str}PE",
        short_call_key=f"NSE_FO|NIFTY{date_str}CE",
        long_call_key=f"NSE_FO|NIFTY{date_str}CE",
    )
    events = asyncio.run(strat.check_signals(_make_empty_chain(), positions))
    types = [e.event_type for e in events]
    assert "DTE_WARN" in types
    dw = next(e for e in events if e.event_type == "DTE_WARN")
    assert dw.severity == "INFO"
    # TIME_STOP must NOT fire at DTE 19 (threshold is 14)
    assert "TIME_STOP" not in types


def test_healthy_ic_produces_no_signals() -> None:
    """Healthy IC: mark 70% of credit, both short deltas 0.15, DTE 30 → []."""
    strat = IronCondorV1()
    # Entry credit = 100. Mark at 70% = 70. short_put=38, short_call=37, longs=2.5 each.
    chain = _make_chain(
        short_put_ltp="38",
        short_put_delta="-0.15",
        long_put_ltp="2",
        short_call_ltp="35",
        short_call_delta="0.15",
        long_call_ltp="3",
    )
    # Use plain (non-date-keyed) positions: expiry not in key → DTE unavailable → DTE signals skip
    plain_positions = _make_ic_positions()
    # combined mark = 38 + 35 - 2 - 3 = 68 → 68% of 100 → no profit target or loss stop
    events = asyncio.run(strat.check_signals(chain, plain_positions))
    assert events == []


def test_apply_action_close_full_succeeds() -> None:
    """CLOSE_FULL is accepted without error."""
    strat = IronCondorV1()
    positions = _make_ic_positions()
    action = _make_approved_action("CLOSE_FULL")
    result = asyncio.run(strat.apply_action(positions, action))
    # legs_to_close is empty → all positions returned unchanged
    assert len(result) == len(positions)


def test_apply_action_close_call_spread_succeeds() -> None:
    """CLOSE_CALL_SPREAD is accepted without error."""
    strat = IronCondorV1()
    positions = _make_ic_positions()
    action = ApprovedAction(
        action_type="CLOSE_CALL_SPREAD",
        legs_to_close=["short_call", "long_call_hedge"],
        legs_to_open=[],
        rationale="test",
        council_rank=1,
    )
    result = asyncio.run(strat.apply_action(positions, action))
    remaining_roles = {p.leg_role for p in result}
    assert "short_call" not in remaining_roles
    assert "long_call_hedge" not in remaining_roles
    assert "short_put" in remaining_roles
    assert "long_put_hedge" in remaining_roles


def test_apply_action_adjust_wings_raises_value_error() -> None:
    """ADJUST_WINGS raises ValueError — not in allowed set."""
    strat = IronCondorV1()
    positions = _make_ic_positions()
    action = _make_approved_action("ADJUST_WINGS")
    with pytest.raises(ValueError, match="ADJUST_WINGS"):
        asyncio.run(strat.apply_action(positions, action))


# ── PA1.2 — ROLL_WING signal tests ───────────────────────────────────────────


def _make_chain_with_roll_targets(
    short_call_delta: str = "0.10",
    short_put_delta: str = "-0.10",
    include_ce_target: bool = True,
    include_pe_target: bool = True,
) -> OptionChain:
    """Build a chain that includes (or omits) farther OTM roll-target legs.

    Short call at 25000 (threatened), long call hedge at 25500.
    Short put at 22000 (threatened), long put hedge at 21500.
    CE roll target at 26000 with |delta|=0.14 (inside 0.10–0.20 band).
    PE roll target at 21000 with |delta|=0.12 (inside 0.10–0.20 band).
    """
    strikes: dict = {
        Decimal("21500"): OptionChainStrike(pe=_make_leg(ltp="3", delta="-0.05", strike="21500")),
        Decimal("22000"): OptionChainStrike(
            pe=_make_leg(ltp="30", delta=short_put_delta, strike="22000")
        ),
        Decimal("25000"): OptionChainStrike(
            ce=_make_leg(ltp="25", delta=short_call_delta, strike="25000")
        ),
        Decimal("25500"): OptionChainStrike(ce=_make_leg(ltp="2", delta="0.04", strike="25500")),
    }
    if include_ce_target:
        strikes[Decimal("26000")] = OptionChainStrike(
            ce=_make_leg(ltp="8", delta="0.14", strike="26000")
        )
    if include_pe_target:
        strikes[Decimal("21000")] = OptionChainStrike(
            pe=_make_leg(ltp="6", delta="-0.12", strike="21000")
        )
    return OptionChain(
        underlying_spot=Decimal("24000"),
        expiry=date(2026, 6, 26),
        strikes=strikes,
    )


def test_roll_wing_fires_on_short_call_breach_with_target() -> None:
    """Short call |delta|=0.36 + CE target at 26000 → ROLL_WING ACTION fires alongside DELTA_STOP."""
    strat = IronCondorV1()
    chain = _make_chain_with_roll_targets(short_call_delta="0.36")
    positions = _make_ic_positions()
    events = asyncio.run(strat.check_signals(chain, positions))
    types = [e.event_type for e in events]
    assert "DELTA_STOP" in types
    assert "ROLL_WING" in types
    rw = next(e for e in events if e.event_type == "ROLL_WING")
    assert rw.severity == "ACTION"
    assert rw.payload["leg_role"] == "short_call"
    assert "26000" in rw.payload["suggested_instrument_key"]
    assert rw.payload["current_instrument_key"] == _SHORT_CALL_KEY


def test_roll_wing_fires_on_short_put_breach_with_target() -> None:
    """Short put |delta|=0.37 + PE target at 21000 → ROLL_WING ACTION fires alongside DELTA_STOP."""
    strat = IronCondorV1()
    chain = _make_chain_with_roll_targets(short_put_delta="-0.37")
    positions = _make_ic_positions()
    events = asyncio.run(strat.check_signals(chain, positions))
    types = [e.event_type for e in events]
    assert "DELTA_STOP" in types
    assert "ROLL_WING" in types
    rw = next(e for e in events if e.event_type == "ROLL_WING")
    assert rw.severity == "ACTION"
    assert rw.payload["leg_role"] == "short_put"
    assert "21000" in rw.payload["suggested_instrument_key"]


def test_roll_wing_not_fired_when_no_ce_target_in_range() -> None:
    """Short call |delta|=0.36 but no CE in 0.10–0.20 range → only DELTA_STOP fires."""
    strat = IronCondorV1()
    chain = _make_chain_with_roll_targets(
        short_call_delta="0.36",
        include_ce_target=False,  # no farther OTM CE available
    )
    positions = _make_ic_positions()
    events = asyncio.run(strat.check_signals(chain, positions))
    types = [e.event_type for e in events]
    assert "DELTA_STOP" in types
    assert "ROLL_WING" not in types


def test_roll_wing_blocked_by_directional_guard() -> None:
    """CE target exists in delta range but is at a strike below current short_call
    strike → directional guard blocks it → no ROLL_WING (only DELTA_STOP fires).

    Short call is at 25000 (delta 0.36).  A CE at 24500 with |delta|=0.14
    is inside the 0.10–0.20 band but sits below 25000, so the guard correctly
    rejects it as a backward roll.
    """
    strat = IronCondorV1()
    # Build chain: short call at 25000 (threatened), CE roll candidate at 24500
    # (below current strike — must be blocked by directional guard).
    below_strike_chain = OptionChain(
        underlying_spot=Decimal("24000"),
        expiry=date(2026, 6, 26),
        strikes={
            Decimal("21500"): OptionChainStrike(
                pe=_make_leg(ltp="3", delta="-0.05", strike="21500")
            ),
            Decimal("22000"): OptionChainStrike(
                pe=_make_leg(ltp="30", delta="-0.15", strike="22000")
            ),
            Decimal("24500"): OptionChainStrike(
                # CE below current short_call at 25000; |delta|=0.14 is in range
                # but directional guard should block this as a backward roll.
                ce=_make_leg(ltp="40", delta="0.14", strike="24500")
            ),
            Decimal("25000"): OptionChainStrike(
                ce=_make_leg(ltp="25", delta="0.36", strike="25000")
            ),
            Decimal("25500"): OptionChainStrike(
                ce=_make_leg(ltp="2", delta="0.04", strike="25500")
            ),
        },
    )
    positions = _make_ic_positions()
    events = asyncio.run(strat.check_signals(below_strike_chain, positions))
    types = [e.event_type for e in events]
    assert "DELTA_STOP" in types
    assert "ROLL_WING" not in types


def test_apply_action_roll_wing_with_leg_to_open_succeeds() -> None:
    """ROLL_WING + one LegSpec in legs_to_open → closed leg removed from positions.

    apply_action only handles the close side (backbone design: PaperExecutor
    handles new-leg DB writes for legs_to_open; they are not appended here).
    """
    from src.strategy.protocol import LegSpec

    strat = IronCondorV1()
    positions = _make_ic_positions()
    action = ApprovedAction(
        action_type="ROLL_WING",
        legs_to_close=["short_call"],
        legs_to_open=[
            LegSpec(
                instrument_key="NSE_FO|NIFTY26000CE",
                action="SELL",
                quantity=1,
                leg_role="short_call",
                notes="roll_wing delta=0.14",
            )
        ],
        rationale="roll call wing farther OTM",
        council_rank=1,
    )
    result = asyncio.run(strat.apply_action(positions, action))
    remaining_roles = {p.leg_role for p in result}
    # Closed wing is gone; other three legs survive.
    assert "short_call" not in remaining_roles
    assert "short_put" in remaining_roles
    assert "long_put_hedge" in remaining_roles
    assert "long_call_hedge" in remaining_roles
    # legs_to_open is intentionally not in result — executor handles the new leg.
    assert len(result) == 3


def test_apply_action_roll_wing_empty_legs_to_open_raises() -> None:
    """ROLL_WING with empty legs_to_open → ValueError."""
    strat = IronCondorV1()
    positions = _make_ic_positions()
    action = ApprovedAction(
        action_type="ROLL_WING",
        legs_to_close=["short_call"],
        legs_to_open=[],
        rationale="test",
        council_rank=1,
    )
    with pytest.raises(ValueError, match="legs_to_open"):
        asyncio.run(strat.apply_action(positions, action))


def test_auto_execute_is_false() -> None:
    """IronCondorV1 must declare auto_execute=False (human-approval-only intent)."""
    strat = IronCondorV1()
    assert strat.auto_execute is False
    assert strat.strategy_name == "paper_ic_nifty_v1"


def test_strategy_ic_constant_matches_class() -> None:
    """STRATEGY_IC constant must stay in sync with IronCondorV1.strategy_name."""
    from src.paper.constants import STRATEGY_IC

    assert STRATEGY_IC == IronCondorV1.strategy_name

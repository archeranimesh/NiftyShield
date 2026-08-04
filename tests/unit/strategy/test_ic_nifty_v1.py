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
from structlog.testing import capture_logs

from src.models.options import OptionChain, OptionChainStrike, OptionLeg
from src.paper.models import PaperPosition
from src.strategy.ic_nifty_v1 import IronCondorV1
from src.strategy.protocol import ApprovedAction, LegClose

_STRATEGY = "paper_ic_nifty_v1_monthly"
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
    entry_date: date | None = None,
) -> PaperPosition:
    return PaperPosition(
        strategy_name=strategy_name,
        leg_role=leg_role,
        net_qty=net_qty,
        avg_cost=Decimal(avg_cost),
        avg_sell_price=Decimal(avg_sell_price),
        instrument_key=instrument_key,
        entry_date=entry_date,
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


def test_flat_legs_produce_no_signals_and_no_bod_warnings() -> None:
    """2026-07-21: a fully-closed IC (net_qty == 0 on all four legs) must be
    filtered out entirely, not re-resolved against the chain every tick.

    ``PaperStore.get_positions`` still returns one ``PaperPosition`` per
    ``leg_role`` after a leg closes (BUG-014), carrying the now-settled,
    delisted ``instrument_key`` of the closed contract. Without the
    ``net_qty != 0`` filter, ``check_signals`` calls ``_find_leg``/
    ``_compute_combined_pnl`` on that dead key every tick, which can never
    resolve via BOD again — producing permanent ``strike_parse_failed``/
    ``mark_unavailable`` warning noise. See DECISIONS.md 2026-07-21.
    """
    strat = IronCondorV1()
    positions = [
        _make_position(leg_role="short_put", instrument_key="NSE_FO|51348", net_qty=0),
        _make_position(leg_role="long_put_hedge", instrument_key="NSE_FO|51340", net_qty=0),
        _make_position(leg_role="short_call", instrument_key="NSE_FO|51405", net_qty=0),
        _make_position(leg_role="long_call_hedge", instrument_key="NSE_FO|51417", net_qty=0),
    ]
    with capture_logs() as logs:
        result = asyncio.run(strat.check_signals(_make_empty_chain(), positions))
    assert result == []
    assert not [e for e in logs if e["event"] == "ic_nifty_v1.strike_parse_failed"]
    assert not [e for e in logs if e["event"] == "ic_nifty_v1.mark_unavailable"]


def test_flat_legs_excluded_but_open_legs_still_evaluated() -> None:
    """A mix of flat and open legs: only the open legs (net_qty != 0) reach
    the chain-resolution path; the flat leg's dead instrument_key is dropped
    before it can ever trigger a BOD warning.
    """
    strat = IronCondorV1()
    positions = _make_ic_positions()
    # short_put's cycle already closed and rolled to a dead numeric key —
    # everything else in the IC is still open.
    positions[0] = _make_position(leg_role="short_put", instrument_key="NSE_FO|51348", net_qty=0)
    with capture_logs() as logs:
        events = asyncio.run(strat.check_signals(_make_chain(), positions))
    assert not [e for e in logs if e["event"] == "ic_nifty_v1.strike_parse_failed"]
    # short_put excluded from delta evaluation — only short_call's delta signal path runs.
    delta_events = [e for e in events if e.event_type in ("DELTA_STOP", "DELTA_WARN")]
    assert all(e.payload.get("leg_role") != "short_put" for e in delta_events)


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


def test_mark_unavailable_logs_warning_per_missing_leg() -> None:
    """BUG-2 follow-up (2026-07-20): each leg missing from the chain during
    _compute_combined_pnl must emit ic_nifty_v1.mark_unavailable — this is the
    exact point PROFIT_TARGET/LOSS_STOP went silent in the live incident.
    """
    strat = IronCondorV1()
    positions = _make_ic_positions()
    with capture_logs() as logs:
        combined_mark, entry_credit = strat._compute_combined_pnl(_make_empty_chain(), positions)
    assert combined_mark is None
    assert entry_credit == Decimal("100")
    unavailable_events = [e for e in logs if e["event"] == "ic_nifty_v1.mark_unavailable"]
    assert len(unavailable_events) == 4  # one per leg, chain has zero strikes
    leg_roles = {e["leg_role"] for e in unavailable_events}
    assert leg_roles == {"short_put", "long_put_hedge", "short_call", "long_call_hedge"}
    assert all(e["strategy"] == _STRATEGY for e in unavailable_events)


def test_mark_unavailable_not_logged_on_healthy_chain() -> None:
    """Happy path — no missing legs, no warning noise."""
    strat = IronCondorV1()
    positions = _make_ic_positions()
    with capture_logs() as logs:
        combined_mark, _entry_credit = strat._compute_combined_pnl(_make_chain(), positions)
    assert combined_mark is not None
    assert not [e for e in logs if e["event"] == "ic_nifty_v1.mark_unavailable"]


def test_pnl_gate_skipped_logged_when_mark_unavailable() -> None:
    """BUG-2 follow-up (2026-07-20): check_signals must log why PROFIT_TARGET/
    LOSS_STOP were skipped when the chain is missing legs, instead of silently
    returning no signal for that reason.
    """
    strat = IronCondorV1()
    positions = _make_ic_positions()
    with capture_logs() as logs:
        events = asyncio.run(strat.check_signals(_make_empty_chain(), positions))
    assert not [e for e in events if e.event_type in ("PROFIT_TARGET", "LOSS_STOP")]
    skipped = [e for e in logs if e["event"] == "ic_nifty_v1.pnl_gate_skipped"]
    assert len(skipped) == 1
    assert skipped[0]["reason"] == "mark_unavailable"
    assert skipped[0]["strategy"] == _STRATEGY


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


# ── Tests: BUG-021 — profit target/loss stop read persisted original_entry_credit ──


def test_profit_target_unaffected_when_persisted_credit_matches_recompute() -> None:
    """Happy path: full 4-leg basket, persisted credit == today's recompute (100 pts).

    Confirms the substitution is a no-op for the correct-case (no partial
    close yet) — same PROFIT_TARGET result as
    ``test_profit_target_fires_when_mark_at_50_pct``.
    """
    from unittest.mock import MagicMock

    from src.paper.store import PaperStore

    store = MagicMock(spec=PaperStore)
    store.get_original_entry_credit.return_value = Decimal("100")
    strat = IronCondorV1(store=store)
    chain = _make_chain(
        short_put_ltp="28",
        long_put_ltp="3",
        short_call_ltp="23",
        long_call_ltp="2",
    )
    positions = _make_ic_positions()
    events = asyncio.run(strat.check_signals(chain, positions))
    store.get_original_entry_credit.assert_called_once_with(_STRATEGY)
    types = [e.event_type for e in events]
    assert "PROFIT_TARGET" in types


def test_profit_target_uses_persisted_credit_after_partial_close() -> None:
    """BUG-021 symptom fix: after the call spread has already closed, the
    surviving put spread's own recomputed credit (60-5=55 pts, drifted above
    the true original via averaging) would falsely trigger the 50% profit
    target once its mark drops far enough. The persisted original 4-leg
    entry credit (100 pts) is the true basket economics and correctly keeps
    the pct above the 50% threshold — no PROFIT_TARGET.
    """
    from unittest.mock import MagicMock

    from src.paper.store import PaperStore

    store = MagicMock(spec=PaperStore)
    store.get_original_entry_credit.return_value = Decimal("100")
    strat = IronCondorV1(store=store)
    positions = [
        _make_position(
            leg_role="short_put",
            instrument_key=_SHORT_PUT_KEY,
            avg_sell_price=_SHORT_PUT_SELL,
            net_qty=-65,
        ),
        _make_position(
            leg_role="long_put_hedge",
            instrument_key=_LONG_PUT_KEY,
            avg_cost=_LONG_PUT_COST,
            net_qty=65,
        ),
        # Call spread already closed — flat, dead key, excluded by net_qty filter.
        _make_position(leg_role="short_call", instrument_key="NSE_FO|51405", net_qty=0),
        _make_position(leg_role="long_call_hedge", instrument_key="NSE_FO|51417", net_qty=0),
    ]
    # Surviving put spread mark = 20 - 2 = 18. Recompute-only pct = 18/55 = 32.7%
    # (would fire PROFIT_TARGET at ≤50%). True basket pct = 18/100 = 18%
    # (also ≤50% here) — use a mark where only the mis-scoped denominator
    # would cross the threshold: mark = 30 → recompute pct 30/55=54.5% (no
    # fire), true pct 30/100=30% (fires). This isolates the denominator bug.
    chain = _make_chain(short_put_ltp="31", long_put_ltp="1")
    events = asyncio.run(strat.check_signals(chain, positions))
    types = [e.event_type for e in events]
    assert "PROFIT_TARGET" in types, (
        "expected persisted 100pt basket credit to correctly fire PROFIT_TARGET "
        "at 30% remaining; recompute-only credit (55pt) would have missed it"
    )


def test_profit_target_falls_back_to_recompute_when_no_persisted_credit() -> None:
    """Edge case: `get_original_entry_credit` returns None (never persisted,
    e.g. pre-fix positions) — falls back to today's recompute-from-ic_positions
    behavior, unchanged.
    """
    from unittest.mock import MagicMock

    from src.paper.store import PaperStore

    store = MagicMock(spec=PaperStore)
    store.get_original_entry_credit.return_value = None
    strat = IronCondorV1(store=store)
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


def test_profit_target_skips_store_lookup_when_no_store_injected() -> None:
    """Edge case: `store=None` (test doubles / callers with no persistence
    wired) must not raise — the `self._store is not None` guard short-circuits
    the lookup entirely and falls back to recompute, same as the None-return case.
    """
    strat = IronCondorV1()  # broker=None, store=None
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


def test_loss_stop_survives_store_read_failure() -> None:
    """Edge case: `get_original_entry_credit` raises (e.g. transient SQLite
    lock/error). Must not propagate out of `check_signals` — degrades to the
    recompute fallback, same as the None case, so LOSS_STOP still evaluates
    for this tick instead of the whole method raising.
    """
    from unittest.mock import MagicMock

    from src.paper.store import PaperStore

    store = MagicMock(spec=PaperStore)
    store.get_original_entry_credit.side_effect = RuntimeError("db locked")
    strat = IronCondorV1(store=store)
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


def test_delta_stop_fires_on_short_call_breach() -> None:
    """Short call |delta| = 0.36 ≥ 0.35 → DELTA_STOP ACTION."""
    strat = IronCondorV1()
    strat.auto_execute = False
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
    strat.auto_execute = False
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
        legs_to_close=[LegClose(leg_role="short_call"), LegClose(leg_role="long_call_hedge")],
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
    strat.auto_execute = False
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
    strat.auto_execute = False
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
    strat.auto_execute = False
    chain = _make_chain_with_roll_targets(
        short_call_delta="0.36",
        include_ce_target=False,  # no farther OTM CE available
    )
    positions = _make_ic_positions()
    events = asyncio.run(strat.check_signals(chain, positions))
    types = [e.event_type for e in events]
    assert "DELTA_STOP" in types
    assert "ROLL_WING" not in types


def test_roll_wing_rescued_by_bug_022_narrower_search() -> None:
    """No delta-band CE target exists, but a narrower strike between the
    existing long hedge (25500) and the short strike (25000) clears the
    liquidity/premium floor and the floor-guarantee inequality (given a
    persisted entry credit) -> ROLL_WING fires instead of a bare DELTA_STOP."""
    from unittest.mock import MagicMock

    from src.paper.store import PaperStore

    store = MagicMock(spec=PaperStore)
    store.get_original_entry_credit.return_value = Decimal("1000")
    strat = IronCondorV1(store=store)
    strat.auto_execute = False

    strikes = {
        Decimal("21500"): OptionChainStrike(
            pe=_make_leg(ltp="3", delta="-0.05", strike="21500")
        ),
        Decimal("22000"): OptionChainStrike(
            pe=_make_leg(ltp="30", delta="-0.10", strike="22000")
        ),
        Decimal("25000"): OptionChainStrike(
            ce=_make_leg(ltp="25", delta="0.36", strike="25000")
        ),
        Decimal("25500"): OptionChainStrike(ce=_make_leg(ltp="2", delta="0.04", strike="25500")),
        # Narrower candidate strictly between 25000 (short) and 25500 (old
        # long hedge) — clears premium/liquidity floors.
        Decimal("25200"): OptionChainStrike(
            ce=_make_leg(ltp="20", delta="0.15", strike="25200")
        ),
    }
    chain = OptionChain(underlying_spot=Decimal("24000"), expiry=date(2026, 6, 26), strikes=strikes)
    positions = _make_ic_positions()

    events = asyncio.run(strat.check_signals(chain, positions))
    types = [e.event_type for e in events]
    assert "ROLL_WING" in types
    roll_event = next(e for e in events if e.event_type == "ROLL_WING")
    assert "25200" in roll_event.payload["suggested_instrument_key"]


def test_roll_wing_blocked_by_directional_guard() -> None:
    """CE target exists in delta range but is at a strike below current short_call
    strike → directional guard blocks it → no ROLL_WING (only DELTA_STOP fires).

    Short call is at 25000 (delta 0.36).  A CE at 24500 with |delta|=0.14
    is inside the 0.10–0.20 band but sits below 25000, so the guard correctly
    rejects it as a backward roll.
    """
    strat = IronCondorV1()
    strat.auto_execute = False
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
        legs_to_close=[LegClose(leg_role="short_call")],
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
        legs_to_close=[LegClose(leg_role="short_call")],
        legs_to_open=[],
        rationale="test",
        council_rank=1,
    )
    with pytest.raises(ValueError, match="legs_to_open"):
        asyncio.run(strat.apply_action(positions, action))


# ── Auto-close persistence (fix for silent no-op — closing fills were never
#    written to paper_trades, so the same exit signal re-fired every tick) ──


def _make_auto_close_action(action_type: str, event_type: str = "LOSS_STOP") -> ApprovedAction:
    """Build an auto-execute CLOSE_FULL-style action as StrategyMonitor would."""
    return ApprovedAction(
        action_type=action_type,
        legs_to_close=[],
        legs_to_open=[],
        rationale="auto-execute",
        council_rank=1,
        metadata={"auto_selected": True, "event_type": event_type},
    )


def test_apply_action_close_full_auto_execute_persists_all_legs() -> None:
    """Auto-execute CLOSE_FULL with broker+store injected writes 4 closing trades."""
    from unittest.mock import AsyncMock, MagicMock

    from src.client.protocol import BrokerClient
    from src.paper.store import PaperStore

    broker = MagicMock(spec=BrokerClient)
    broker.get_ltp = AsyncMock(
        return_value={
            _SHORT_PUT_KEY: Decimal("30.00"),
            _LONG_PUT_KEY: Decimal("2.00"),
            _SHORT_CALL_KEY: Decimal("28.00"),
            _LONG_CALL_KEY: Decimal("2.50"),
        }
    )
    store = MagicMock(spec=PaperStore)
    store.record_trades = MagicMock(side_effect=lambda trades: (trades, []))

    strat = IronCondorV1(broker=broker, store=store)
    positions = _make_ic_positions()
    action = _make_auto_close_action("CLOSE_FULL")

    result = asyncio.run(strat.apply_action(positions, action))

    store.record_trades.assert_called_once()
    (written,), _ = store.record_trades.call_args
    assert {t.leg_role for t in written} == {
        "short_put",
        "long_put_hedge",
        "short_call",
        "long_call_hedge",
    }
    # In-memory filtering behaviour unchanged: all legs removed for CLOSE_FULL.
    assert result == []


def test_apply_action_close_full_auto_execute_without_broker_skips_persist_no_raise() -> None:
    """No broker/store injected → logs and skips persistence, does not raise (regression guard)."""
    strat = IronCondorV1()  # broker=None, store=None
    positions = _make_ic_positions()
    action = _make_auto_close_action("CLOSE_FULL")

    result = asyncio.run(strat.apply_action(positions, action))

    # Still returns empty (in-memory filter), no exception even though nothing was persisted.
    assert result == []


def test_apply_action_close_full_auto_execute_sends_close_notification() -> None:
    """BUG-013 (2026-07-20): auto-execute CLOSE_FULL must confirm via Telegram.

    IronCondorV1 accepted a notifier but never called it — every auto-close
    was silent, unlike CSP/CC/Collar/PP. See docs/bugs/bugs.md BUG-013.
    """
    from unittest.mock import AsyncMock, MagicMock

    from src.client.protocol import BrokerClient
    from src.paper.store import PaperStore

    broker = MagicMock(spec=BrokerClient)
    broker.get_ltp = AsyncMock(
        return_value={
            _SHORT_PUT_KEY: Decimal("7.70"),
            _LONG_PUT_KEY: Decimal("3.95"),
            _SHORT_CALL_KEY: Decimal("3.35"),
            _LONG_CALL_KEY: Decimal("1.20"),
        }
    )
    store = MagicMock(spec=PaperStore)
    store.record_trades = MagicMock(side_effect=lambda trades: (trades, []))
    notifier = MagicMock()
    notifier.send_notification = AsyncMock()

    strat = IronCondorV1(broker=broker, store=store, notifier=notifier)
    positions = _make_ic_positions()
    action = _make_auto_close_action("CLOSE_FULL", event_type="PROFIT_TARGET")

    asyncio.run(strat.apply_action(positions, action))

    notifier.send_notification.assert_called_once()
    (message,), _ = notifier.send_notification.call_args
    assert "PROFIT_TARGET" in message
    assert _STRATEGY in message
    assert "short_put" in message


def test_apply_action_no_notifier_does_not_raise() -> None:
    """Happy path — no notifier configured, close still succeeds silently."""
    from unittest.mock import AsyncMock, MagicMock

    from src.client.protocol import BrokerClient
    from src.paper.store import PaperStore

    broker = MagicMock(spec=BrokerClient)
    broker.get_ltp = AsyncMock(
        return_value={
            _SHORT_PUT_KEY: Decimal("7.70"),
            _LONG_PUT_KEY: Decimal("3.95"),
            _SHORT_CALL_KEY: Decimal("3.35"),
            _LONG_CALL_KEY: Decimal("1.20"),
        }
    )
    store = MagicMock(spec=PaperStore)
    store.record_trades = MagicMock(side_effect=lambda trades: (trades, []))

    strat = IronCondorV1(broker=broker, store=store)  # no notifier
    positions = _make_ic_positions()
    action = _make_auto_close_action("CLOSE_FULL")

    result = asyncio.run(strat.apply_action(positions, action))
    assert result == []  # close still happens; notification is best-effort only


def test_send_close_notification_no_store_skips_pnl_without_raising() -> None:
    """store=None: notification still sends, net P&L text omitted, no crash.

    Regression guard for the mypy gap fixed 2026-07-29 — get_strategy_realized_pnl
    requires PaperStore, not PaperStore | None. _send_close_notification is only
    reached via apply_action's own None-store guard today (line ~557), so this
    branch is unreachable through that path; this test exercises the private
    method directly so the guard has real coverage rather than being dead code.
    """
    from unittest.mock import AsyncMock, MagicMock

    from src.models.portfolio import TradeAction
    from src.paper.models import PaperTrade

    notifier = MagicMock()
    notifier.send_notification = AsyncMock()

    strat = IronCondorV1(notifier=notifier)  # store=None
    closed_trades = [
        PaperTrade(
            strategy_name=_STRATEGY,
            leg_role="short_put",
            instrument_key=_SHORT_PUT_KEY,
            trade_date=date(2026, 5, 1),
            action=TradeAction.BUY,
            quantity=75,
            price=Decimal("7.70"),
            notes="close",
        )
    ]

    with capture_logs() as logs:
        asyncio.run(strat._send_close_notification("CLOSE_FULL", "PROFIT_TARGET", closed_trades))

    notifier.send_notification.assert_called_once()
    (message,), _ = notifier.send_notification.call_args
    assert "Net P&L" not in message
    assert any(log.get("event") == "ic_nifty_v1.net_pnl_calc_skipped_no_store" for log in logs)


def test_apply_action_close_full_manual_action_does_not_auto_persist() -> None:
    """A manually-approved (non auto-execute) CLOSE_FULL does not call close_ic_legs.

    Manual/Telegram-approved actions are persisted by PaperExecutor
    (src/strategy/executor.py) via the callback path in monitor_daemon.py,
    not by apply_action — avoids a double-write if both paths ever fired.
    """
    from unittest.mock import MagicMock

    from src.client.protocol import BrokerClient
    from src.paper.store import PaperStore

    broker = MagicMock(spec=BrokerClient)
    store = MagicMock(spec=PaperStore)

    strat = IronCondorV1(broker=broker, store=store)
    positions = _make_ic_positions()
    action = ApprovedAction(
        action_type="CLOSE_FULL",
        legs_to_close=[
            LegClose(leg_role="short_put"),
            LegClose(leg_role="long_put_hedge"),
            LegClose(leg_role="short_call"),
            LegClose(leg_role="long_call_hedge"),
        ],
        legs_to_open=[],
        rationale="manual approval",  # not "auto-execute"
        council_rank=1,
    )

    asyncio.run(strat.apply_action(positions, action))

    store.record_trades.assert_not_called()


def test_auto_execute_is_true() -> None:
    """IronCondorV1 must declare auto_execute=True (exits are rule-based)."""
    strat = IronCondorV1()
    assert strat.auto_execute is True


def test_strategy_ic_constant_matches_class() -> None:
    """STRATEGY_IC_MONTHLY constant must stay in sync with IronCondorV1().strategy_name."""
    from src.paper.constants import STRATEGY_IC_MONTHLY

    assert STRATEGY_IC_MONTHLY == IronCondorV1().strategy_name


def test_strategy_name_from_config() -> None:
    """Four presets must produce four distinct strategy_name values."""
    from src.strategy.ic_expiry_config import CONFIGS

    for config in CONFIGS.values():
        strat = IronCondorV1(config=config)
        assert strat.strategy_name == config.strategy_name


def test_auto_select_loss_stop_wins() -> None:
    """LOSS_STOP + PROFIT_TARGET both in events → CLOSE_FULL from LOSS_STOP priority."""
    from src.strategy.protocol import SignalEvent

    strat = IronCondorV1()
    events = [
        SignalEvent(event_type="PROFIT_TARGET", severity="ACTION", description="", payload={}),
        SignalEvent(event_type="LOSS_STOP", severity="ACTION", description="", payload={}),
    ]
    action = strat._auto_select_action(events, [])
    assert action is not None
    assert action.action_type == "CLOSE_FULL"
    assert {leg.leg_role for leg in action.legs_to_close} == {
        "short_call",
        "short_put",
        "long_call_hedge",
        "long_put_hedge",
    }


def test_auto_select_roll_over_delta_stop() -> None:
    """ROLL_WING + DELTA_STOP both in events → ROLL_WING action returned."""
    from src.strategy.protocol import SignalEvent

    strat = IronCondorV1()
    events = [
        SignalEvent(
            event_type="DELTA_STOP",
            severity="ACTION",
            description="",
            payload={"leg_role": "short_call"},
        ),
        SignalEvent(
            event_type="ROLL_WING",
            severity="ACTION",
            description="",
            payload={
                "leg_role": "short_call",
                "suggested_instrument_key": "NSE_FO|NIFTY26000CE",
                "suggested_delta": "0.15",
            },
        ),
    ]
    action = strat._auto_select_action(events, [])
    assert action is not None
    assert action.action_type == "ROLL_WING"
    assert action.legs_to_close == [LegClose(leg_role="short_call")]
    assert len(action.legs_to_open) == 1
    assert action.legs_to_open[0].instrument_key == "NSE_FO|NIFTY26000CE"
    assert action.legs_to_open[0].leg_role == "short_call"


def test_auto_select_delta_stop_escalates_to_close_full() -> None:
    """DELTA_STOP with no roll target → CLOSE_FULL (BUG-022), never a naked spread close."""
    from src.strategy.protocol import SignalEvent

    strat = IronCondorV1()
    events = [
        SignalEvent(
            event_type="DELTA_STOP",
            severity="ACTION",
            description="",
            payload={"leg_role": "short_call"},
        )
    ]
    action = strat._auto_select_action(events, [])
    assert action is not None
    assert action.action_type == "CLOSE_FULL"
    assert {leg.leg_role for leg in action.legs_to_close} == {
        "short_call",
        "long_call_hedge",
        "short_put",
        "long_put_hedge",
    }


def test_auto_select_none_when_no_action() -> None:
    """Only WARN/INFO events → returns None."""
    from src.strategy.protocol import SignalEvent

    strat = IronCondorV1()
    events = [
        SignalEvent(event_type="DELTA_WARN", severity="WARN", description="", payload={}),
        SignalEvent(event_type="DTE_WARN", severity="INFO", description="", payload={}),
    ]
    action = strat._auto_select_action(events, [])
    assert action is None


def test_auto_select_close_full_populates_instrument_key() -> None:
    """CLOSE_FULL's LegClose entries carry each role's live instrument_key (PG-4f)."""
    from src.strategy.protocol import SignalEvent

    strat = IronCondorV1()
    ic_positions = _make_ic_positions()
    events = [SignalEvent(event_type="LOSS_STOP", severity="ACTION", description="", payload={})]

    action = strat._auto_select_action(events, ic_positions)
    assert action is not None
    keys_by_role = {leg.leg_role: leg.instrument_key for leg in action.legs_to_close}
    assert keys_by_role == {
        "short_put": _SHORT_PUT_KEY,
        "long_put_hedge": _LONG_PUT_KEY,
        "short_call": _SHORT_CALL_KEY,
        "long_call_hedge": _LONG_CALL_KEY,
    }


def test_auto_select_roll_overlap_picks_most_recent_position() -> None:
    """CLOSE_FULL on a roll-overlap fixture selects the most-recently-entered
    position for the ambiguous leg_role, not just any match sharing the role
    (PG-4f, mirrors PaperStore.get_position's PG-2a ambiguity handling)."""
    from src.strategy.protocol import SignalEvent

    strat = IronCondorV1()
    old_short_call = _make_position(
        leg_role="short_call",
        instrument_key="NSE_FO|NIFTY25000CE_OLD",
        entry_date=date(2026, 5, 1),
    )
    new_short_call = _make_position(
        leg_role="short_call",
        instrument_key=_SHORT_CALL_KEY,
        entry_date=date(2026, 6, 1),
    )
    # Drop the standard short_call fixture, leaving only the two roll-overlap
    # positions (old + new) sharing leg_role="short_call".
    ic_positions = [p for p in _make_ic_positions() if p.leg_role != "short_call"] + [
        old_short_call,
        new_short_call,
    ]
    events = [SignalEvent(event_type="LOSS_STOP", severity="ACTION", description="", payload={})]

    action = strat._auto_select_action(events, ic_positions)
    assert action is not None
    short_call_leg = next(leg for leg in action.legs_to_close if leg.leg_role == "short_call")
    assert short_call_leg.instrument_key == _SHORT_CALL_KEY


def test_apply_action_close_full_roll_overlap_closes_only_matched_instrument() -> None:
    """apply_action(CLOSE_FULL) on a roll-overlap fixture removes only the position
    whose instrument_key matches the LegClose, leaving the other same-role position
    open (PG-4f)."""
    from unittest.mock import AsyncMock, MagicMock

    from src.client.protocol import BrokerClient
    from src.paper.store import PaperStore

    broker = MagicMock(spec=BrokerClient)
    broker.get_ltp = AsyncMock(
        return_value={
            _SHORT_PUT_KEY: Decimal("30.00"),
            _LONG_PUT_KEY: Decimal("2.00"),
            _SHORT_CALL_KEY: Decimal("28.00"),
            _LONG_CALL_KEY: Decimal("2.50"),
        }
    )
    store = MagicMock(spec=PaperStore)
    store.record_trades = MagicMock(side_effect=lambda trades: (trades, []))

    strat = IronCondorV1(broker=broker, store=store)
    old_short_call = _make_position(
        leg_role="short_call",
        instrument_key="NSE_FO|NIFTY25000CE_OLD",
        entry_date=date(2026, 5, 1),
    )
    positions = _make_ic_positions() + [old_short_call]
    action = ApprovedAction(
        action_type="CLOSE_FULL",
        legs_to_close=[
            LegClose(leg_role="short_put", instrument_key=_SHORT_PUT_KEY),
            LegClose(leg_role="long_put_hedge", instrument_key=_LONG_PUT_KEY),
            LegClose(leg_role="short_call", instrument_key=_SHORT_CALL_KEY),
            LegClose(leg_role="long_call_hedge", instrument_key=_LONG_CALL_KEY),
        ],
        legs_to_open=[],
        rationale="auto-execute",
        council_rank=1,
        metadata={"auto_selected": True},
    )

    result = asyncio.run(strat.apply_action(positions, action))

    assert result == [old_short_call]


# ── IC-F1: IVR wiring tests ───────────────────────────────────────────────────


def test_describe_context_ivr_present() -> None:
    """describe_context emits IVR value when VIX Parquet data is available."""
    from pathlib import Path
    from unittest.mock import patch

    import pandas as pd

    strat = IronCondorV1()
    mock_series = pd.Series([15.0, 16.0, 14.5])

    with (
        patch.object(Path, "exists", return_value=True),
        patch("src.backtest.vix_ingest.load_vix_series", return_value=mock_series),
        patch("src.backtest.vix_ingest.fetch_vix_latest", return_value=16.0),
        patch("src.backtest.ivr.compute_ivr", return_value=0.42),
    ):
        result = strat._compute_ivr_str()

    assert result == "IVR: 0.42"


def test_describe_context_ivr_unavailable() -> None:
    """_compute_ivr_str returns 'IVR: unavailable' when VIX directory is missing."""
    from pathlib import Path
    from unittest.mock import patch

    strat = IronCondorV1()

    with patch.object(Path, "exists", return_value=False):
        result = strat._compute_ivr_str()

    assert result == "IVR: unavailable"


# ── Integration tests for auto_execute=True check_signals pipeline ────────────


def test_check_signals_auto_execute_loss_stop() -> None:
    """LOSS_STOP fires, filters out others, and gets marked auto_execute."""
    strat = IronCondorV1()
    chain = _make_chain(
        short_put_ltp="105",
        long_put_ltp="5",
        short_call_ltp="105",
        long_call_ltp="5",
    )
    positions = _make_ic_positions()
    events = asyncio.run(strat.check_signals(chain, positions))
    action_events = [e for e in events if e.severity == "ACTION"]
    assert len(action_events) == 1
    ev = action_events[0]
    assert ev.event_type == "LOSS_STOP"
    assert ev.payload["auto_execute"] is True
    assert ev.payload["auto_action"] == "CLOSE_FULL"


def test_check_signals_auto_execute_profit_target() -> None:
    """PROFIT_TARGET fires, filters out others, and gets marked auto_execute."""
    strat = IronCondorV1()
    chain = _make_chain(
        short_put_ltp="25",
        long_put_ltp="5",
        short_call_ltp="25",
        long_call_ltp="5",
    )
    positions = _make_ic_positions()
    events = asyncio.run(strat.check_signals(chain, positions))
    action_events = [e for e in events if e.severity == "ACTION"]
    assert len(action_events) == 1
    ev = action_events[0]
    assert ev.event_type == "PROFIT_TARGET"
    assert ev.payload["auto_execute"] is True
    assert ev.payload["auto_action"] == "CLOSE_FULL"


def test_check_signals_auto_execute_delta_stop_with_roll() -> None:
    """DELTA_STOP fires with a roll target -> ROLL_WING action auto_executed."""
    from unittest.mock import patch

    from src.strategy.protocol import LegSpec

    strat = IronCondorV1()
    chain = _make_chain(
        short_call_delta="0.36",
        short_put_ltp="40",
        short_call_ltp="35",
    )
    positions = _make_ic_positions()

    roll_target = LegSpec(
        instrument_key="NSE_FO|NIFTY26000CE",
        action="SELL",
        quantity=1,
        leg_role="short_call",
        notes="roll_wing delta=0.15",
    )
    with patch.object(strat, "_select_wing_roll_target", return_value=roll_target):
        events = asyncio.run(strat.check_signals(chain, positions))

    action_events = [e for e in events if e.severity == "ACTION"]
    assert len(action_events) == 1
    ev = action_events[0]
    assert ev.event_type == "ROLL_WING"
    assert ev.payload["auto_execute"] is True
    assert ev.payload["auto_action"] == "ROLL_WING"


def test_check_signals_auto_execute_delta_stop_no_roll() -> None:
    """DELTA_STOP with both the direct target and the BUG-022 narrower search
    exhausted -> CLOSE_FULL action auto_executed (never a naked spread close)."""
    from unittest.mock import patch

    strat = IronCondorV1()
    chain = _make_chain(
        short_call_delta="0.36",
        short_put_ltp="40",
        short_call_ltp="35",
    )
    positions = _make_ic_positions()

    with (
        patch.object(strat, "_select_wing_roll_target", return_value=None),
        patch.object(strat, "_search_narrower_wing_candidate", return_value=None),
    ):
        events = asyncio.run(strat.check_signals(chain, positions))

    action_events = [e for e in events if e.severity == "ACTION"]
    assert len(action_events) == 1
    ev = action_events[0]
    assert ev.event_type == "DELTA_STOP"
    assert ev.payload["auto_execute"] is True
    assert ev.payload["auto_action"] == "CLOSE_FULL"


def test_is_auto_execute() -> None:
    """_is_auto_execute identifies auto-execution correctly."""
    from src.strategy.protocol import ApprovedAction

    strat = IronCondorV1()

    # Metadata-based
    act1 = ApprovedAction(
        action_type="CLOSE_FULL",
        legs_to_close=[],
        legs_to_open=[],
        rationale="foo",
        council_rank=1,
        metadata={"auto_selected": True},
    )
    assert strat._is_auto_execute(act1) is True

    # Rationale fallback
    act2 = ApprovedAction(
        action_type="CLOSE_FULL",
        legs_to_close=[],
        legs_to_open=[],
        rationale="auto-execute",
        council_rank=1,
    )
    assert strat._is_auto_execute(act2) is True

    # Normal manual action
    act3 = ApprovedAction(
        action_type="CLOSE_FULL",
        legs_to_close=[],
        legs_to_open=[],
        rationale="foo",
        council_rank=1,
    )
    assert strat._is_auto_execute(act3) is False


# ---------------------------------------------------------------------------
# IC-F9 — _parse_expiry handles both live key formats
# ---------------------------------------------------------------------------


def test_parse_expiry_date_before_pe_suffix() -> None:
    """Key format: date immediately before PE/CE — NSE_FO|NIFTY26JUN2026PE24000."""
    from datetime import date

    strat = IronCondorV1()
    result = strat._parse_expiry("NSE_FO|NIFTY26JUN2026PE24000")
    assert result == date(2026, 6, 26)


def test_parse_expiry_date_before_strike() -> None:
    """Key format: date followed by numeric strike — NSE_FO|NIFTY26JUN202624000PE."""
    from datetime import date

    strat = IronCondorV1()
    result = strat._parse_expiry("NSE_FO|NIFTY26JUN202624000PE")
    assert result == date(2026, 6, 26)


def test_parse_expiry_unrecognised_returns_none() -> None:
    """Unrecognised key format must return None without raising."""
    strat = IronCondorV1()
    assert strat._parse_expiry("NSE_EQ|INFY") is None


# ── BUG-012: numeric instrument key BOD fallback in _find_leg ────────────────


def test_find_leg_resolves_numeric_key_via_bod_pe() -> None:
    """Numeric key (no NIFTY<strike><PE|CE> substring) resolves via BOD lookup."""
    from unittest.mock import MagicMock, patch

    strat = IronCondorV1()
    chain = _make_chain()  # has a PE at strike 22000

    with patch("src.instruments.lookup.InstrumentLookup.from_file") as mock_from_file:
        lookup = MagicMock()
        lookup.get_by_key.return_value = {
            "strike_price": Decimal("22000"),
            "instrument_type": "PE",
        }
        mock_from_file.return_value = lookup

        leg = strat._find_leg(chain, "NSE_FO|63896")

    assert leg is not None
    assert leg.strike == Decimal("22000")


def test_find_leg_resolves_numeric_key_via_bod_ce() -> None:
    """Same BOD fallback path resolves a CE leg."""
    from unittest.mock import MagicMock, patch

    strat = IronCondorV1()
    chain = _make_chain()  # has a CE at strike 25000

    with patch("src.instruments.lookup.InstrumentLookup.from_file") as mock_from_file:
        lookup = MagicMock()
        lookup.get_by_key.return_value = {
            "strike_price": Decimal("25000"),
            "instrument_type": "CE",
        }
        mock_from_file.return_value = lookup

        leg = strat._find_leg(chain, "NSE_FO|63991")

    assert leg is not None
    assert leg.strike == Decimal("25000")


def test_find_leg_numeric_key_not_in_bod_returns_none() -> None:
    """Numeric key absent from the BOD master returns None, never raises."""
    from unittest.mock import MagicMock, patch

    strat = IronCondorV1()
    chain = _make_chain()

    with patch("src.instruments.lookup.InstrumentLookup.from_file") as mock_from_file:
        lookup = MagicMock()
        lookup.get_by_key.return_value = None
        mock_from_file.return_value = lookup

        leg = strat._find_leg(chain, "NSE_FO|99999999")

    assert leg is None


def test_find_leg_bod_lookup_raises_returns_none() -> None:
    """A BOD file/lookup failure is caught and degrades to None, never raises."""
    from unittest.mock import patch

    strat = IronCondorV1()
    chain = _make_chain()

    with patch(
        "src.instruments.lookup.InstrumentLookup.from_file",
        side_effect=OSError("BOD file missing"),
    ):
        leg = strat._find_leg(chain, "NSE_FO|63896")

    assert leg is None

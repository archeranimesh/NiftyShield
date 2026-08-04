"""Tests for IC-V2-10: profit-lock signal integration in IronCondorV2.check_signals().

Covers the 8-level precedence ladder (priorities 5 & 6), auto_execute path, and
apply_action() state update.  ProfitLockEngine.evaluate() is mocked to isolate
the wiring logic from the engine math (tested separately in test_profit_lock_engine.py).

No network calls.  All chains and positions are constructed in-memory.
greeks-analyst gate: mandatory before code-reviewer (IC-V2-10 spec).

Test list (from stories.md IC-V2-10):
  test_zone1_emits_info_no_action
  test_zone2_executes_automatically
  test_zone2_close_full_when_formula_fails
  test_zone2_not_repeated
  test_zone2_precedence_below_forced_close
  test_zone2_precedence_below_profit_target
  test_zone2_precedence_above_d3_roll
  test_notification_payload
  test_apply_action_updates_state
"""

from __future__ import annotations

import datetime
from asyncio import run as arun
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from src.models.options import OptionChain, OptionChainStrike, OptionLeg
from src.paper.models import PaperPosition
from src.strategy.ic_expiry_config_v2 import IC_V2_MONTHLY
from src.strategy.ic_nifty_v2 import IronCondorV2
from src.strategy.profit_lock_engine import ProfitLockDecision, ProfitLockState
from src.strategy.protocol import ApprovedAction, LegClose, LegSpec

# ── Constants ─────────────────────────────────────────────────────────────────

_STRATEGY_NAME = "paper_ic_nifty_v2_monthly"
_EXPIRY = datetime.date(2026, 7, 31)
_FROZEN_TODAY = datetime.date(2026, 7, 15)  # DTE = 16
_EXPIRY_TAG = "31JUL2026"

# Entry: shorts @ 23900 PE / 25100 CE each @ 100 pts; wings @ 50 pts.
# Net IC credit = 100 pts → entry_credit = 100 pts
_ENTRY_CREDIT = Decimal("100")

# ── Helpers ───────────────────────────────────────────────────────────────────


def _leg(
    strike: str,
    delta: str | None,
    ltp: str = "50",
    bid: str = "49",
    ask: str = "51",
    oi: int = 100_000,
) -> OptionLeg:
    return OptionLeg(
        ltp=Decimal(ltp),
        bid=Decimal(bid),
        ask=Decimal(ask),
        oi=oi,
        volume=10_000,
        delta=Decimal(delta) if delta is not None else None,
        gamma=None,
        theta=None,
        vega=None,
        iv=Decimal("15.0"),
        strike=Decimal(strike),
    )


def _chain(
    strikes: dict[str, tuple[OptionLeg | None, OptionLeg | None]],
    spot: str = "24500",
) -> OptionChain:
    return OptionChain(
        underlying_spot=Decimal(spot),
        expiry=_EXPIRY,
        strikes={Decimal(k): OptionChainStrike(ce=ce, pe=pe) for k, (ce, pe) in strikes.items()},
    )


def _key(strike: str, option_type: str) -> str:
    """Compound key embedding expiry (for _parse_expiry) and strike (for _find_leg)."""
    return f"NSE_FO|NIFTY{_EXPIRY_TAG}NIFTY{strike}{option_type}"


def _pos(
    leg_role: str,
    strike: str,
    option_type: str,
    avg_cost: str = "0",
    avg_sell_price: str = "100",
    net_qty: int = -1,
) -> PaperPosition:
    return PaperPosition(
        strategy_name=_STRATEGY_NAME,
        leg_role=leg_role,
        net_qty=net_qty,
        avg_cost=Decimal(avg_cost),
        avg_sell_price=Decimal(avg_sell_price),
        instrument_key=_key(strike, option_type),
    )


def _standard_positions() -> list[PaperPosition]:
    """4-leg IC: short_put@23900, lp_hedge@23200, short_call@25100, lc_hedge@25800.

    Entry credit per short = 100; wing cost = 50 each.
    Net entry_credit = (100+100)-(50+50) = 100 pts.
    """
    return [
        _pos("short_put", "23900", "PE", avg_sell_price="100"),
        _pos("long_put_hedge", "23200", "PE", avg_cost="50", net_qty=1),
        _pos("short_call", "25100", "CE", avg_sell_price="100"),
        _pos("long_call_hedge", "25800", "CE", avg_cost="50", net_qty=1),
    ]


def _healthy_chain_with_mark(put_mark: str = "40", call_mark: str = "30") -> OptionChain:
    """Chain where IC is profitable; short deltas well inside safe zone."""
    put_ltp = Decimal(put_mark)
    call_ltp = Decimal(call_mark)
    # combined_mark = short_put.ltp + short_call.ltp - long_put.ltp - long_call.ltp
    # = put_mark + call_mark - 5 - 5  (wings valued at 5)
    return _chain(
        {
            "23900": (
                None,
                _leg("23900", "-0.20", ltp=put_mark, bid=str(put_ltp - 1), ask=str(put_ltp + 1)),
            ),
            "25100": (
                _leg("25100", "0.18", ltp=call_mark, bid=str(call_ltp - 1), ask=str(call_ltp + 1)),
                None,
            ),
            "23200": (None, _leg("23200", "-0.08", ltp="5", bid="4.5", ask="5.5")),
            "25800": (_leg("25800", "0.07", ltp="5", bid="4.5", ask="5.5"), None),
            # Zone 2 target wing strikes (19Δ area)
            "23600": (None, _leg("23600", "-0.19", ltp="20", bid="19", ask="21")),
            "25400": (_leg("25400", "0.19", ltp="20", bid="19", ask="21"), None),
        }
    )


def _make_pl_state(
    zone: int = 0,
    zone2_executed: bool = False,
    cum_debit: str = "0",
    put_width: int = 700,
    call_width: int = 700,
    cycle_id: str = "cycle1",
) -> ProfitLockState:
    return ProfitLockState(
        profit_lock_zone=zone,
        zone2_lock_executed=zone2_executed,
        zone3_lock_executed=False,
        cumulative_lock_debit_pts=Decimal(cum_debit),
        active_put_width_pts=put_width,
        active_call_width_pts=call_width,
        cycle_id=cycle_id,
    )


def _make_strategy(store: object | None = None) -> IronCondorV2:
    """Build IronCondorV2 with frozen today and a mock store."""
    strategy = IronCondorV2(config=IC_V2_MONTHLY, store=store)  # type: ignore[arg-type]
    strategy.set_original_credit(_ENTRY_CREDIT)
    return strategy


def _zone2_decision(
    new_put_strike: str = "23600",
    new_call_strike: str = "25400",
    net_debit: str = "34",
    floor: str = "0.28",
) -> ProfitLockDecision:
    """Fake ZONE2_LOCK decision returned by mocked engine."""
    return ProfitLockDecision(
        action="ZONE2_LOCK",
        zone=2,
        captured_fraction=Decimal("0.52"),
        formula_passes=True,
        required_max_width_pts=100,
        new_put_wing=_leg(new_put_strike, "-0.19", ltp="20", bid="19", ask="21"),
        new_call_wing=_leg(new_call_strike, "0.19", ltp="20", bid="19", ask="21"),
        net_debit_pts=Decimal(net_debit),
        guaranteed_floor_fraction=Decimal(floor),
        skip_reason=None,
    )


def _none_decision(skip_reason: str = "already_executed") -> ProfitLockDecision:
    return ProfitLockDecision(
        action="NONE",
        zone=2,
        captured_fraction=Decimal("0.52"),
        formula_passes=False,
        required_max_width_pts=None,
        new_put_wing=None,
        new_call_wing=None,
        net_debit_pts=None,
        guaranteed_floor_fraction=None,
        skip_reason=skip_reason,
    )


def _close_full_decision(reason: str = "formula_failed") -> ProfitLockDecision:
    return ProfitLockDecision(
        action="CLOSE_FULL",
        zone=2,
        captured_fraction=Decimal("0.52"),
        formula_passes=False,
        required_max_width_pts=None,
        new_put_wing=None,
        new_call_wing=None,
        net_debit_pts=None,
        guaranteed_floor_fraction=None,
        skip_reason=reason,
    )


# ── Mock store factory ────────────────────────────────────────────────────────


def _mock_store(pl_state: ProfitLockState | None = None) -> MagicMock:
    """Build a mock PaperStore with profit-lock methods wired."""
    store = MagicMock()
    store.get_profit_lock_state.return_value = pl_state or _make_pl_state()
    store.set_profit_lock_state.return_value = None
    # BUG-020 Phase 3: check_signals now unconditionally reads this before
    # computing captured_fraction. None keeps these profit-lock-zone tests
    # exercising today's recompute-from-ic_positions path unchanged — they
    # are not testing Phase 3's persisted-credit substitution.
    store.get_original_entry_credit.return_value = None
    return store


# ── Tests ─────────────────────────────────────────────────────────────────────


@patch("src.strategy.ic_nifty_v2.market_today", return_value=_FROZEN_TODAY)
def test_zone1_emits_info_no_action(mock_today):
    """captured=0.28 → PROFIT_LOCK_ZONE1 INFO, no auto_execute (priority 6)."""
    # Mark such that captured ≈ 0.28: entry_credit=100, mark=72
    # combined_mark = short_put.ltp + short_call.ltp - long_put.ltp - long_call.ltp
    # = 40 + 35 - 5 - 5 = 65 → captured = (100-65)/100 = 0.35  [too high for zone1 only]
    # Need captured=0.28: mark = 72 pts (= 100 × (1-0.28))
    # short legs: 36+36=72; wings 0. But wings must be in chain.
    # Set: put_mark=40, call_mark=37, wing ltp=2 each → mark=40+37-2-2=73, captured=0.27
    # Close enough; let's set put=38, call=35, wings=1 each → mark=72, captured=0.28
    chain = _chain(
        {
            "23900": (None, _leg("23900", "-0.20", ltp="38", bid="37", ask="39")),
            "25100": (_leg("25100", "0.18", ltp="35", bid="34", ask="36"), None),
            "23200": (None, _leg("23200", "-0.08", ltp="1", bid="0.5", ask="1.5")),
            "25800": (_leg("25800", "0.07", ltp="1", bid="0.5", ask="1.5"), None),
        }
    )
    store = _mock_store(_make_pl_state(zone=0))  # Zone 1 not yet logged
    strategy = _make_strategy(store)
    positions = _standard_positions()

    signals = arun(strategy.check_signals(chain, positions))

    assert len(signals) == 1
    s = signals[0]
    assert s.event_type == "PROFIT_LOCK_ZONE1"
    assert s.severity == "INFO"
    assert s.payload.get("zone") == 1
    # No auto_execute field (INFO signals are not dispatched by StrategyMonitor)
    assert "auto_execute" not in s.payload


@patch("src.strategy.ic_nifty_v2.market_today", return_value=_FROZEN_TODAY)
@patch("src.strategy.ic_nifty_v2.ProfitLockEngine")
def test_zone2_executes_automatically(MockEngine, mock_today):
    """captured=0.52, engine returns ZONE2_LOCK → PROFIT_LOCK_ZONE2 ACTION, auto_execute=True."""
    MockEngine.return_value.evaluate.return_value = _zone2_decision()

    # Mark = 48: put=30, call=23, wings=2 each → mark=30+23-2-2=49, captured=0.51 ≈ 0.52 close enough
    # Use mark=48: captured=(100-48)/100=0.52 → put=25+call=28=53 - wings=2.5 each → 53-5=48
    chain = _healthy_chain_with_mark(put_mark="25", call_mark="28")
    store = _mock_store(_make_pl_state(zone=0, zone2_executed=False))
    strategy = _make_strategy(store)

    signals = arun(strategy.check_signals(chain, _standard_positions()))

    assert len(signals) == 1
    s = signals[0]
    assert s.event_type == "PROFIT_LOCK_ZONE2"
    assert s.severity == "ACTION"
    assert s.payload["auto_execute"] is True
    assert s.payload["auto_action"] == "PROFIT_LOCK_ZONE2"
    assert "PROFIT_LOCK_ZONE2" in s.payload["valid_actions"]
    MockEngine.return_value.evaluate.assert_called_once()


@patch("src.strategy.ic_nifty_v2.market_today", return_value=_FROZEN_TODAY)
@patch("src.strategy.ic_nifty_v2.ProfitLockEngine")
def test_zone2_close_full_when_formula_fails(MockEngine, mock_today):
    """Engine returns CLOSE_FULL → FORCED_CLOSE emitted (formula cannot be satisfied)."""
    MockEngine.return_value.evaluate.return_value = _close_full_decision("formula_failed")

    chain = _healthy_chain_with_mark(put_mark="25", call_mark="28")
    store = _mock_store(_make_pl_state(zone=0, zone2_executed=False))
    strategy = _make_strategy(store)

    signals = arun(strategy.check_signals(chain, _standard_positions()))

    assert len(signals) == 1
    s = signals[0]
    assert s.event_type == "FORCED_CLOSE"
    assert s.severity == "ACTION"
    assert "profit_lock_close_full" in s.payload["reason"]


@patch("src.strategy.ic_nifty_v2.market_today", return_value=_FROZEN_TODAY)
@patch("src.strategy.ic_nifty_v2.ProfitLockEngine")
def test_zone2_not_repeated(MockEngine, mock_today):
    """zone2_lock_executed=True → zone2 branch skipped; engine not called again."""
    chain = _healthy_chain_with_mark(put_mark="25", call_mark="28")
    # Already executed → NONE returned by engine for already_executed
    MockEngine.return_value.evaluate.return_value = _none_decision("already_executed")
    store = _mock_store(_make_pl_state(zone=2, zone2_executed=True))
    strategy = _make_strategy(store)

    signals = arun(strategy.check_signals(chain, _standard_positions()))

    # No zone2 re-trigger; engine called (because zone2_executed guard is in engine not caller)
    # but the engine itself returns NONE → no signal
    # In our implementation, zone2_executed check is caller-side (in _check_profit_lock):
    # if not pl_state.zone2_lock_executed: <call engine>
    # So engine should NOT be called when already executed.
    MockEngine.return_value.evaluate.assert_not_called()
    # Signal list: no PROFIT_LOCK_ZONE2
    assert not any(s.event_type == "PROFIT_LOCK_ZONE2" for s in signals)


@patch("src.strategy.ic_nifty_v2.market_today", return_value=_FROZEN_TODAY)
def test_zone2_precedence_below_forced_close(mock_today):
    """|delta|≥0.45 fires at priority 2 — zone2 branch never reached."""
    # Short put delta = -0.46 → FORCED_CLOSE at priority 2
    chain = _chain(
        {
            "23900": (None, _leg("23900", "-0.46", ltp="25", bid="24", ask="26")),
            "25100": (_leg("25100", "0.18", ltp="28", bid="27", ask="29"), None),
            "23200": (None, _leg("23200", "-0.08", ltp="2", bid="1.5", ask="2.5")),
            "25800": (_leg("25800", "0.07", ltp="2", bid="1.5", ask="2.5"), None),
        }
    )
    store = _mock_store(_make_pl_state(zone=0, zone2_executed=False))
    strategy = _make_strategy(store)

    signals = arun(strategy.check_signals(chain, _standard_positions()))

    assert len(signals) == 1
    s = signals[0]
    assert s.event_type == "FORCED_CLOSE"
    assert s.payload.get("reason") == "extreme_delta"
    # Store's profit-lock methods never called (short-circuited at priority 2)
    store.get_profit_lock_state.assert_not_called()


@patch("src.strategy.ic_nifty_v2.market_today", return_value=_FROZEN_TODAY)
def test_zone2_precedence_below_profit_target(mock_today):
    """captured=0.72 → profit target (priority 4) fires before zone2 (priority 5)."""
    # mark = 28: entry_credit=100, captured=(100-28)/100=0.72
    # short puts/calls very cheap, wings near zero
    chain = _chain(
        {
            "23900": (None, _leg("23900", "-0.20", ltp="15", bid="14", ask="16")),
            "25100": (_leg("25100", "0.18", ltp="14", bid="13", ask="15"), None),
            "23200": (None, _leg("23200", "-0.05", ltp="0.5", bid="0.3", ask="0.7")),
            "25800": (_leg("25800", "0.05", ltp="0.5", bid="0.3", ask="0.7"), None),
        }
    )
    # entry_credit = (avg_sell_price_put + avg_sell_price_call) - (avg_cost_put + avg_cost_call)
    # = (100 + 100) - (50 + 50) = 100
    # combined_mark = 15 + 14 - 0.5 - 0.5 = 28
    # 28 ≤ 30% × 100 = 30 → profit target fires
    store = _mock_store(_make_pl_state(zone=0, zone2_executed=False))
    strategy = _make_strategy(store)

    signals = arun(strategy.check_signals(chain, _standard_positions()))

    assert len(signals) == 1
    s = signals[0]
    assert s.event_type == "CLOSE_FULL"
    assert "captured_fraction" in s.payload
    # Profit-lock store never queried (short-circuited at priority 4)
    store.get_profit_lock_state.assert_not_called()


@patch("src.strategy.ic_nifty_v2.market_today", return_value=_FROZEN_TODAY)
@patch("src.strategy.ic_nifty_v2.ProfitLockEngine")
def test_zone2_precedence_above_d3_roll(MockEngine, mock_today):
    """captured=0.52 AND |put_delta|=0.36 → profit-lock fires (priority 5 > priority 7).

    D3 roll does NOT fire on the same tick. Re-evaluation happens on next daemon cycle
    after profit-lock execution updates the position.
    """
    MockEngine.return_value.evaluate.return_value = _zone2_decision()

    # Short put delta = -0.36 (≥ 0.35 D3 roll threshold) AND captured ≈ 0.52
    chain = _chain(
        {
            "23900": (None, _leg("23900", "-0.36", ltp="25", bid="24", ask="26")),
            "25100": (_leg("25100", "0.18", ltp="28", bid="27", ask="29"), None),
            "23200": (None, _leg("23200", "-0.08", ltp="2", bid="1.5", ask="2.5")),
            "25800": (_leg("25800", "0.07", ltp="2", bid="1.5", ask="2.5"), None),
            "23600": (None, _leg("23600", "-0.19", ltp="20", bid="19", ask="21")),
            "25400": (_leg("25400", "0.19", ltp="20", bid="19", ask="21"), None),
        }
    )
    # combined_mark = 25 + 28 - 2 - 2 = 49 → captured = 51/100 = 0.51 (close to zone 2)
    store = _mock_store(_make_pl_state(zone=0, zone2_executed=False))
    strategy = _make_strategy(store)

    signals = arun(strategy.check_signals(chain, _standard_positions()))

    assert len(signals) == 1
    s = signals[0]
    # Profit-lock fires, not D3 roll
    assert s.event_type == "PROFIT_LOCK_ZONE2"
    assert "ROLL_WING" not in [s.event_type for s in signals]


@patch("src.strategy.ic_nifty_v2.market_today", return_value=_FROZEN_TODAY)
@patch("src.strategy.ic_nifty_v2.ProfitLockEngine")
def test_notification_payload(MockEngine, mock_today):
    """PROFIT_LOCK_ZONE2 payload contains guaranteed_floor_fraction, new widths, net_debit."""
    MockEngine.return_value.evaluate.return_value = _zone2_decision(
        new_put_strike="23600",
        new_call_strike="25400",
        net_debit="34",
        floor="0.28",
    )
    chain = _healthy_chain_with_mark(put_mark="25", call_mark="28")
    store = _mock_store(_make_pl_state(zone=0, zone2_executed=False))
    strategy = _make_strategy(store)

    signals = arun(strategy.check_signals(chain, _standard_positions()))

    assert len(signals) == 1
    payload = signals[0].payload
    assert "guaranteed_floor_fraction" in payload
    assert "new_put_width_pts" in payload
    assert "new_call_width_pts" in payload
    assert "net_debit_pts" in payload
    assert payload["net_debit_pts"] == "34"
    assert payload["guaranteed_floor_fraction"] == "0.28"
    assert payload["new_put_wing_strike"] == "23600"
    assert payload["new_call_wing_strike"] == "25400"


def test_apply_action_updates_state():
    """PROFIT_LOCK_ZONE2 apply_action: store state updated with zone2_lock_executed=True."""
    store = _mock_store(_make_pl_state(zone=0, zone2_executed=False))
    notifier = MagicMock()
    notifier.send_notification = AsyncMock(return_value=None)
    strategy = IronCondorV2(config=IC_V2_MONTHLY, store=store, notifier=notifier)  # type: ignore[arg-type]

    positions = _standard_positions()
    action = ApprovedAction(
        action_type="PROFIT_LOCK_ZONE2",
        legs_to_close=[LegClose(leg_role="long_put_hedge"), LegClose(leg_role="long_call_hedge")],
        legs_to_open=[
            LegSpec(
                instrument_key="NSE_FO|NIFTY23600PE",
                action="BUY",
                quantity=1,
                leg_role="long_put_hedge",
            ),
            LegSpec(
                instrument_key="NSE_FO|NIFTY25400CE",
                action="BUY",
                quantity=1,
                leg_role="long_call_hedge",
            ),
        ],
        rationale="auto-execute",
        council_rank=1,
        metadata={
            "new_profit_lock_zone": 2,
            "zone2_lock_executed": True,
            "cumulative_lock_debit_pts": "34",
            "new_put_width_pts": 300,
            "new_call_width_pts": 300,
            "cycle_id": "cycle1",
            "captured_fraction": "0.52",
            "net_debit_pts": "34",
            "guaranteed_floor_fraction": "0.28",
            "new_put_wing_strike": "23600",
            "new_call_wing_strike": "25400",
            "dte": 16,
        },
    )

    updated = arun(strategy.apply_action(positions, action))

    # Old long wings removed
    remaining_roles = {p.leg_role for p in updated}
    assert "long_put_hedge" not in remaining_roles
    assert "long_call_hedge" not in remaining_roles
    # Short legs preserved
    assert "short_put" in remaining_roles
    assert "short_call" in remaining_roles
    # Store state updated with zone2_lock_executed=True
    store.set_profit_lock_state.assert_called_once()
    saved_state: ProfitLockState = store.set_profit_lock_state.call_args[0][1]
    assert saved_state.zone2_lock_executed is True
    assert saved_state.profit_lock_zone == 2
    assert saved_state.cumulative_lock_debit_pts == Decimal("34")
    assert saved_state.active_put_width_pts == 300
    # Telegram notification sent
    notifier.send_notification.assert_called_once()

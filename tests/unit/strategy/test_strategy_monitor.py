"""Unit tests for StrategyMonitor (PB1.2).

All tests are fully offline — no network calls, no real DB, no fixtures on disk.
The store and notifier are MagicMock objects; the broker is either a MagicMock
(async) or a MockBrokerClient with a queued error.
"""

from __future__ import annotations

import asyncio
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from structlog.testing import capture_logs

from src.client.exceptions import DataFetchError
from src.models.options import OptionChain
from src.paper.models import PaperPosition
from src.strategy.monitor import StrategyMonitor
from src.strategy.protocol import LegSpec, SignalEvent

# Import MockStrategy defined alongside the protocol tests.
from tests.unit.strategy.test_strategy_protocol import MockStrategy

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_empty_chain() -> OptionChain:
    """Minimal OptionChain with no strikes — safe as a test market snapshot."""
    from datetime import date

    return OptionChain(
        underlying_spot=Decimal("24000"),
        expiry=date(2026, 6, 26),
        strikes={},
    )


def _make_store(
    positions: list[PaperPosition] | None = None,
) -> MagicMock:
    """Mock PaperStore that returns configurable positions.

    write_heartbeat and add_pending_approval are available as MagicMock attrs
    so tests can assert call counts (PB1.6 wires the real implementations).
    """
    store = MagicMock()
    store.get_positions.return_value = positions or []
    # WARN dedup (StrategyMonitor._route_event): default to "not already
    # active" so existing WARN-fires-once-per-tick tests keep sending on
    # their first (and only) tick, matching pre-dedup behavior. Tests that
    # specifically exercise the dedup/reconcile path override this.
    store.is_warn_active.return_value = False
    return store


def _make_notifier() -> MagicMock:
    """Mock notifier with async send_plain_message and send_approval_request."""
    notifier = MagicMock()
    notifier.send_plain_message = AsyncMock()
    notifier.send_approval_request = AsyncMock()
    return notifier


def _make_broker(chain_data: list[dict[str, Any]] | None = None) -> MagicMock:
    """Mock broker whose get_option_chain returns a raw list.

    Args:
        chain_data: The list returned by get_option_chain. Defaults to [].
    """
    broker = MagicMock()
    broker.get_option_chain = AsyncMock(return_value=chain_data or [])
    return broker


def _make_monitor(
    broker: Any = None,
    store: Any = None,
    notifier: Any = None,
    strategies: list | None = None,
    expiry_fn: Any = lambda: "2026-06-26",
) -> StrategyMonitor:
    """Build a StrategyMonitor with sensible test defaults."""
    return StrategyMonitor(
        broker=broker or _make_broker(),
        store=store or _make_store(),
        notifier=notifier or _make_notifier(),
        strategies=strategies,
        poll_interval_s=1,
        expiry_fn=expiry_fn,
    )


# ---------------------------------------------------------------------------
# register()
# ---------------------------------------------------------------------------


def test_register_adds_strategy_to_internal_list() -> None:
    """register() appends a strategy so len(_strategies) increases by one."""
    monitor = _make_monitor(strategies=[])
    assert len(monitor._strategies) == 0
    monitor.register(MockStrategy())
    assert len(monitor._strategies) == 1


def test_register_multiple_strategies() -> None:
    """Registering two strategies gives length 2."""
    monitor = _make_monitor(strategies=[])
    monitor.register(MockStrategy())
    monitor.register(MockStrategy())
    assert len(monitor._strategies) == 2


# ---------------------------------------------------------------------------
# _tick() — happy paths with market-hours / trading-day patch
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tick_empty_strategy_list_writes_heartbeat() -> None:
    """Empty strategy list → tick completes silently, heartbeat written."""
    store = _make_store()
    monitor = _make_monitor(store=store, strategies=[])

    # Patch is_trading_day → True and market hours to be inside window
    with (
        patch("src.strategy.monitor.is_trading_day", return_value=True),
        patch(
            "src.strategy.monitor.datetime",
            **{
                "now.return_value": _fake_ist_time(10, 0),
                "side_effect": None,
            },
        ),
    ):
        await monitor._tick()

    store.write_heartbeat.assert_called_once()


@pytest.mark.asyncio
async def test_tick_strategy_returns_no_events_writes_heartbeat() -> None:
    """Strategy returning [] → heartbeat written, notifier not called."""
    store = _make_store()
    notifier = _make_notifier()
    monitor = _make_monitor(store=store, notifier=notifier, strategies=[MockStrategy()])

    with (
        patch("src.strategy.monitor.is_trading_day", return_value=True),
        patch(
            "src.strategy.monitor.datetime",
            **{"now.return_value": _fake_ist_time(10, 0), "side_effect": None},
        ),
    ):
        await monitor._tick()

    store.write_heartbeat.assert_called_once()
    notifier.send_plain_message.assert_not_called()
    notifier.send_approval_request.assert_not_called()


@pytest.mark.asyncio
async def test_tick_info_signal_no_telegram() -> None:
    """INFO signal → no Telegram message, heartbeat still written."""
    strategy = MockStrategy()
    info_event = SignalEvent(
        event_type="IVR_HIGH",
        severity="INFO",
        description="IVR above 50",
        payload={},
    )
    strategy.check_signals = AsyncMock(return_value=[info_event])

    store = _make_store()
    notifier = _make_notifier()
    monitor = _make_monitor(store=store, notifier=notifier, strategies=[strategy])

    with (
        patch("src.strategy.monitor.is_trading_day", return_value=True),
        patch(
            "src.strategy.monitor.datetime",
            **{"now.return_value": _fake_ist_time(10, 0), "side_effect": None},
        ),
    ):
        await monitor._tick()

    notifier.send_plain_message.assert_not_called()
    notifier.send_approval_request.assert_not_called()
    store.write_heartbeat.assert_called_once()


@pytest.mark.asyncio
async def test_tick_warn_signal_sends_plain_message() -> None:
    """WARN signal → notifier.send_plain_message called once."""
    strategy = MockStrategy()
    warn_event = SignalEvent(
        event_type="DELTA_BREACH",
        severity="WARN",
        description="Portfolio delta exceeded warning threshold",
        payload={"delta": 1.2},
    )
    strategy.check_signals = AsyncMock(return_value=[warn_event])

    notifier = _make_notifier()
    monitor = _make_monitor(notifier=notifier, strategies=[strategy])

    with (
        patch("src.strategy.monitor.is_trading_day", return_value=True),
        patch(
            "src.strategy.monitor.datetime",
            **{"now.return_value": _fake_ist_time(10, 0), "side_effect": None},
        ),
    ):
        await monitor._tick()

    notifier.send_plain_message.assert_called_once()
    notifier.send_approval_request.assert_not_called()


@pytest.mark.asyncio
async def test_tick_warn_signal_suppressed_when_already_active() -> None:
    """WARN condition already flagged active in store → no repeat Telegram send.

    Regression test for the DELTA_WARN-every-~2min issue: a strategy that
    re-emits the same WARN every tick while the condition persists must not
    re-send once StrategyMonitor has already alerted for that occurrence.
    """
    strategy = MockStrategy()
    warn_event = SignalEvent(
        event_type="DELTA_WARN",
        severity="WARN",
        description="short_call |delta| 0.3272 >= 0.25",
        payload={"leg_role": "short_call"},
    )
    strategy.check_signals = AsyncMock(return_value=[warn_event])

    store = _make_store()
    store.is_warn_active.return_value = True  # already alerted this occurrence
    notifier = _make_notifier()
    monitor = _make_monitor(store=store, notifier=notifier, strategies=[strategy])

    with (
        patch("src.strategy.monitor.is_trading_day", return_value=True),
        patch(
            "src.strategy.monitor.datetime",
            **{"now.return_value": _fake_ist_time(10, 0), "side_effect": None},
        ),
    ):
        await monitor._tick()

    notifier.send_plain_message.assert_not_called()
    store.set_warn_active.assert_not_called()
    # Still reconciled so a recovery elsewhere in the same tick is tracked.
    # broker.get_option_chain defaults to [] -> parse_upstox_option_chain
    # falls back to its own _EMPTY_EXPIRY sentinel (1970-01-01), distinct
    # from the expiry_fn-derived dict key (2026-06-26) used only to select
    # which chain to fetch.
    store.reconcile_warn_state.assert_called_once_with(
        strategy.strategy_name, {("DELTA_WARN", "short_call", "1970-01-01")}
    )


@pytest.mark.asyncio
async def test_tick_warn_signal_first_occurrence_marks_active() -> None:
    """First WARN occurrence (not yet active) → sends and marks active in store."""
    strategy = MockStrategy()
    warn_event = SignalEvent(
        event_type="DELTA_WARN",
        severity="WARN",
        description="short_call |delta| 0.3272 >= 0.25",
        payload={"leg_role": "short_call"},
    )
    strategy.check_signals = AsyncMock(return_value=[warn_event])

    store = _make_store()  # is_warn_active defaults to False
    notifier = _make_notifier()
    monitor = _make_monitor(store=store, notifier=notifier, strategies=[strategy])

    with (
        patch("src.strategy.monitor.is_trading_day", return_value=True),
        patch(
            "src.strategy.monitor.datetime",
            **{"now.return_value": _fake_ist_time(10, 0), "side_effect": None},
        ),
    ):
        await monitor._tick()

    notifier.send_plain_message.assert_called_once()
    store.set_warn_active.assert_called_once_with(
        strategy.strategy_name, "DELTA_WARN", "short_call", True, "1970-01-01"
    )


@pytest.mark.asyncio
async def test_tick_action_signal_sends_approval_and_creates_pending_row() -> None:
    """ACTION signal → send_approval_request called, create_approval written with msg_id."""
    strategy = MockStrategy()
    action_event = SignalEvent(
        event_type="ENTRY_CSP",
        severity="ACTION",
        description="All entry criteria met — open CSP",
        payload={"strike": 23000},
    )
    strategy.check_signals = AsyncMock(return_value=[action_event])

    store = _make_store()
    notifier = _make_notifier()
    notifier.send_approval_request = AsyncMock(return_value=42)
    monitor = _make_monitor(store=store, notifier=notifier, strategies=[strategy])

    with (
        patch("src.strategy.monitor.is_trading_day", return_value=True),
        patch(
            "src.strategy.monitor.datetime",
            **{"now.return_value": _fake_ist_time(10, 0), "side_effect": None},
        ),
    ):
        await monitor._tick()

    notifier.send_approval_request.assert_called_once()
    store.create_approval.assert_called_once()
    call_args = store.create_approval.call_args
    assert call_args[0][0] == strategy.strategy_name  # strategy_name
    assert call_args[0][1] == "ENTRY_CSP"  # event_type
    assert call_args[0][3] == 42  # telegram msg_id
    notifier.send_plain_message.assert_not_called()


@pytest.mark.asyncio
async def test_run_continues_after_tick_exception() -> None:
    """Exception in _tick must not stop the run() loop — next sleep still fires."""
    monitor = StrategyMonitor(
        broker=_make_broker(),
        store=_make_store(),
        notifier=_make_notifier(),
        poll_interval_s=0,
    )
    tick_calls: list[int] = []

    async def _bad_tick() -> None:
        tick_calls.append(1)
        if len(tick_calls) == 1:
            raise RuntimeError("simulated tick failure")

    monitor._tick = _bad_tick  # type: ignore[method-assign]

    async def _run_two_ticks() -> None:
        task = asyncio.create_task(monitor.run())
        # Wait long enough for two ticks at poll_interval_s=0.
        await asyncio.sleep(0.05)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    await _run_two_ticks()
    assert len(tick_calls) >= 2, "run() should have continued after the first tick raised"


@pytest.mark.asyncio
async def test_tick_action_create_approval_delegates_to_store() -> None:
    """create_approval is called with correct positional args; add_pending_approval absent."""
    strategy = MockStrategy()
    event = SignalEvent(
        event_type="TIME_STOP",
        severity="ACTION",
        description="21 days held",
        payload={"days_held": 21},
    )
    strategy.check_signals = AsyncMock(return_value=[event])

    store = _make_store()
    notifier = _make_notifier()
    notifier.send_approval_request = AsyncMock(return_value=99)
    monitor = _make_monitor(store=store, notifier=notifier, strategies=[strategy])

    with (
        patch("src.strategy.monitor.is_trading_day", return_value=True),
        patch(
            "src.strategy.monitor.datetime",
            **{"now.return_value": _fake_ist_time(10, 0), "side_effect": None},
        ),
    ):
        await monitor._tick()

    assert not hasattr(store, "add_pending_approval") or not store.add_pending_approval.called
    store.create_approval.assert_called_once()
    args = store.create_approval.call_args[0]
    assert args[0] == strategy.strategy_name
    assert args[1] == "TIME_STOP"
    assert args[3] == 99  # msg_id propagated from send_approval_request


@pytest.mark.asyncio
async def test_route_event_threads_legs_to_open_into_approved_action() -> None:
    """_route_event's generic auto-execute dispatch must pass event.payload's
    legs_to_open through to the ApprovedAction it builds — regression guard
    for the bug found while scoping S4 (NiftyTrackComparisonV1's ROLL_OVERLAY
    requires a non-empty legs_to_open; the old hardcoded legs_to_open=[]
    would raise inside apply_action and be silently swallowed)."""
    strategy = MockStrategy()
    strategy.auto_execute = True
    strategy.apply_action = AsyncMock(return_value=[])
    replacement_leg = LegSpec(
        instrument_key="NSE_FO|NIFTY01AUG202623500PE",
        action="BUY",
        quantity=75,
        leg_role="overlay_pp",
        price=Decimal("60"),
    )
    event = SignalEvent(
        event_type="ROLL_ELIGIBLE",
        severity="ACTION",
        description="roll eligible",
        payload={
            "leg_role": "overlay_pp",
            "auto_execute": True,
            "auto_action": "ROLL_OVERLAY",
            "legs_to_open": [replacement_leg],
        },
    )
    strategy.check_signals = AsyncMock(return_value=[event])

    store = _make_store()
    notifier = _make_notifier()
    monitor = _make_monitor(store=store, notifier=notifier, strategies=[strategy])

    with (
        patch("src.strategy.monitor.is_trading_day", return_value=True),
        patch(
            "src.strategy.monitor.datetime",
            **{"now.return_value": _fake_ist_time(10, 0), "side_effect": None},
        ),
    ):
        await monitor._tick()

    strategy.apply_action.assert_called_once()
    dispatched_action = strategy.apply_action.call_args[0][1]
    assert dispatched_action.legs_to_open == [replacement_leg]
    notifier.send_approval_request.assert_not_called()
    store.create_approval.assert_not_called()


@pytest.mark.asyncio
async def test_route_event_defaults_legs_to_open_empty_for_close_only_actions() -> None:
    """Regression guard: close-only auto-execute strategies (CCOverlayV1-style,
    no legs_to_open in payload) are unaffected by the legs_to_open threading —
    still get an empty list, same as before this fix."""
    strategy = MockStrategy()
    strategy.auto_execute = True
    strategy.apply_action = AsyncMock(return_value=[])
    event = SignalEvent(
        event_type="PROFIT_TARGET",
        severity="ACTION",
        description="close short call",
        payload={
            "leg_role": "overlay_cc",
            "auto_execute": True,
            "auto_action": "CLOSE_CC",
        },
    )
    strategy.check_signals = AsyncMock(return_value=[event])

    store = _make_store()
    notifier = _make_notifier()
    monitor = _make_monitor(store=store, notifier=notifier, strategies=[strategy])

    with (
        patch("src.strategy.monitor.is_trading_day", return_value=True),
        patch(
            "src.strategy.monitor.datetime",
            **{"now.return_value": _fake_ist_time(10, 0), "side_effect": None},
        ),
    ):
        await monitor._tick()

    dispatched_action = strategy.apply_action.call_args[0][1]
    assert dispatched_action.legs_to_open == []


# ---------------------------------------------------------------------------
# _tick() — error / edge cases
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tick_broker_data_fetch_error_does_not_raise_heartbeat_written() -> None:
    """DataFetchError from broker → tick completes without raising; heartbeat written."""
    broker = MagicMock()
    broker.get_option_chain = AsyncMock(side_effect=DataFetchError("timeout"))

    store = _make_store()
    monitor = _make_monitor(
        broker=broker,
        store=store,
        strategies=[MockStrategy()],
    )

    with (
        patch("src.strategy.monitor.is_trading_day", return_value=True),
        patch(
            "src.strategy.monitor.datetime",
            **{"now.return_value": _fake_ist_time(10, 0), "side_effect": None},
        ),
    ):
        # Must not raise
        await monitor._tick()

    store.write_heartbeat.assert_called_once()


@pytest.mark.asyncio
async def test_tick_skips_if_not_trading_day() -> None:
    """Non-trading day → strategies never called, heartbeat still written."""
    strategy = MockStrategy()
    strategy.check_signals = AsyncMock(return_value=[])
    store = _make_store()
    monitor = _make_monitor(store=store, strategies=[strategy])

    with patch("src.strategy.monitor.is_trading_day", return_value=False):
        await monitor._tick()

    strategy.check_signals.assert_not_called()
    store.write_heartbeat.assert_called_once()


@pytest.mark.asyncio
async def test_tick_skips_if_outside_market_hours() -> None:
    """Outside 09:15–15:30 IST → strategies never called, heartbeat still written."""
    strategy = MockStrategy()
    strategy.check_signals = AsyncMock(return_value=[])
    store = _make_store()
    monitor = _make_monitor(store=store, strategies=[strategy])

    with (
        patch("src.strategy.monitor.is_trading_day", return_value=True),
        patch(
            "src.strategy.monitor.datetime",
            **{"now.return_value": _fake_ist_time(16, 0), "side_effect": None},
        ),
    ):
        await monitor._tick()

    strategy.check_signals.assert_not_called()
    store.write_heartbeat.assert_called_once()


# ---------------------------------------------------------------------------
# BUG-2: multi-expiry chain fetch
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tick_fetches_chain_per_unique_expiry() -> None:
    """Two positions in different expiries → broker.get_option_chain called twice."""
    from datetime import date

    pos_monthly = PaperPosition(
        strategy_name="paper_csp_nifty_v1",
        leg_role="short_put",
        net_qty=-65,
        avg_cost=Decimal("0"),
        avg_sell_price=Decimal("100"),
        instrument_key="NIFTY30JUN2026PE23000",
        entry_date=date(2026, 6, 1),
    )
    pos_quarterly = PaperPosition(
        strategy_name="paper_csp_nifty_v1",
        leg_role="short_put",
        net_qty=-65,
        avg_cost=Decimal("0"),
        avg_sell_price=Decimal("80"),
        instrument_key="NIFTY29JUL2026PE22500",
        entry_date=date(2026, 6, 1),
    )

    strategy = MockStrategy()
    strategy.check_signals = AsyncMock(return_value=[])
    store = _make_store(positions=[pos_monthly, pos_quarterly])

    broker = MagicMock()
    broker.get_option_chain = AsyncMock(return_value=[])

    monitor = _make_monitor(broker=broker, store=store, strategies=[strategy])

    with (
        patch("src.strategy.monitor.is_trading_day", return_value=True),
        patch(
            "src.strategy.monitor.datetime",
            **{"now.return_value": _fake_ist_time(10, 0), "side_effect": None},
        ),
    ):
        await monitor._tick()

    # Two distinct expiry dates → two get_option_chain calls
    assert broker.get_option_chain.call_count == 2
    called_expiries = {call.args[1] for call in broker.get_option_chain.call_args_list}
    assert "2026-06-30" in called_expiries
    assert "2026-07-29" in called_expiries


def test_get_position_expiry_logs_warning_when_unresolvable() -> None:
    """BUG-2 follow-up (2026-07-20): a numeric instrument key with no lookup
    wired must log strategy_monitor.expiry_unresolved instead of silently
    returning None — this is the exact daemon misconfiguration behind the
    live incident (StrategyMonitor built without lookup=).
    """
    monitor = _make_monitor()  # no lookup passed — matches the pre-fix daemon
    pos = PaperPosition(
        strategy_name="paper_ic_nifty_v1_monthly",
        leg_role="short_put",
        net_qty=-65,
        avg_cost=Decimal("0"),
        avg_sell_price=Decimal("21.40"),
        instrument_key="NSE_FO|63896",  # real Upstox numeric key, no named format
    )
    with capture_logs() as logs:
        result = monitor._get_position_expiry(pos)
    assert result is None
    unresolved = [e for e in logs if e["event"] == "strategy_monitor.expiry_unresolved"]
    assert len(unresolved) == 1
    assert unresolved[0]["instrument_key"] == "NSE_FO|63896"
    assert unresolved[0]["lookup_wired"] is False


def test_get_position_expiry_no_warning_for_named_key() -> None:
    """Happy path — named-format key resolves via regex, no warning noise."""
    monitor = _make_monitor()
    pos = PaperPosition(
        strategy_name="paper_csp_nifty_v1",
        leg_role="short_put",
        net_qty=-65,
        avg_cost=Decimal("0"),
        avg_sell_price=Decimal("100"),
        instrument_key="NIFTY30JUN2026PE23000",
    )
    with capture_logs() as logs:
        result = monitor._get_position_expiry(pos)
    assert result is not None
    assert not [e for e in logs if e["event"] == "strategy_monitor.expiry_unresolved"]


def test_get_position_expiry_memoized_within_tick() -> None:
    """MC-1: repeated calls for the same instrument_key within one tick must
    hit the cache, not recompute — the underlying resolution logic (and its
    WARNING for an unresolvable key) only runs once per (tick, instrument_key)
    even though _fetch_chains and _group_positions_by_expiry both call
    _get_position_expiry independently on the same position list.
    """
    monitor = _make_monitor()  # no lookup passed — unresolvable numeric key
    pos = PaperPosition(
        strategy_name="paper_ic_nifty_v1_monthly",
        leg_role="short_put",
        net_qty=-65,
        avg_cost=Decimal("0"),
        avg_sell_price=Decimal("21.40"),
        instrument_key="NSE_FO|63896",
    )
    with capture_logs() as logs:
        first = monitor._get_position_expiry(pos)
        second = monitor._get_position_expiry(pos)
    assert first is None
    assert second is None
    unresolved = [e for e in logs if e["event"] == "strategy_monitor.expiry_unresolved"]
    assert len(unresolved) == 1


@pytest.mark.asyncio
async def test_tick_logs_expiry_unresolved_once_per_position_per_tick() -> None:
    """MC-1: a genuinely unresolvable position must produce exactly one
    strategy_monitor.expiry_unresolved WARNING per tick, even though both
    _fetch_chains and _group_positions_by_expiry call _get_position_expiry
    on it during the same tick. Regression test for the pre-fix double-log.
    """
    pos = PaperPosition(
        strategy_name="paper_ic_nifty_v1_monthly",
        leg_role="short_put",
        net_qty=-65,
        avg_cost=Decimal("0"),
        avg_sell_price=Decimal("21.40"),
        instrument_key="NSE_FO|63896",  # numeric key, no lookup wired
    )
    strategy = MockStrategy()
    strategy.check_signals = AsyncMock(return_value=[])
    store = _make_store(positions=[pos])
    broker = MagicMock()
    broker.get_option_chain = AsyncMock(return_value=[])

    monitor = _make_monitor(broker=broker, store=store, strategies=[strategy])

    with (
        patch("src.strategy.monitor.is_trading_day", return_value=True),
        patch(
            "src.strategy.monitor.datetime",
            **{"now.return_value": _fake_ist_time(10, 0), "side_effect": None},
        ),
        capture_logs() as logs,
    ):
        await monitor._tick()

    unresolved = [e for e in logs if e["event"] == "strategy_monitor.expiry_unresolved"]
    assert len(unresolved) == 1


def test_get_position_expiry_memoizes_resolved_value_not_just_none() -> None:
    """MC-1: the cache must also short-circuit the *resolvable* path — a
    second call for the same instrument_key must return the identical cached
    date object without re-running the regex/BOD resolution, not just
    suppress a duplicate warning on the unresolvable path.
    """
    monitor = _make_monitor()
    pos = PaperPosition(
        strategy_name="paper_csp_nifty_v1",
        leg_role="short_put",
        net_qty=-65,
        avg_cost=Decimal("0"),
        avg_sell_price=Decimal("100"),
        instrument_key="NIFTY30JUN2026PE23000",
    )
    first = monitor._get_position_expiry(pos)
    assert pos.instrument_key in monitor._expiry_cache
    with patch("src.strategy.monitor._date") as mock_date:
        second = monitor._get_position_expiry(pos)
    # Cache hit must bypass resolution entirely — no _date(...) construction call.
    mock_date.assert_not_called()
    assert second == first


@pytest.mark.asyncio
async def test_tick_logs_expiry_fallback_used_for_unresolvable_positions() -> None:
    """BUG-2 follow-up (2026-07-20): when a strategy's positions all fail
    expiry resolution (no lookup wired, numeric keys), _tick's blanket
    fallback — assigning every position to whichever chain was fetched
    first — must be visible via strategy_monitor.expiry_fallback_used.
    """
    pos = PaperPosition(
        strategy_name="paper_ic_nifty_v1_monthly",
        leg_role="short_put",
        net_qty=-65,
        avg_cost=Decimal("0"),
        avg_sell_price=Decimal("21.40"),
        instrument_key="NSE_FO|63896",
    )
    strategy = MockStrategy()
    strategy.strategy_name = "paper_ic_nifty_v1_monthly"
    strategy.check_signals = AsyncMock(return_value=[])
    store = _make_store(positions=[pos])
    monitor = _make_monitor(store=store, strategies=[strategy])  # no lookup

    with (
        patch("src.strategy.monitor.is_trading_day", return_value=True),
        patch(
            "src.strategy.monitor.datetime",
            **{"now.return_value": _fake_ist_time(10, 0), "side_effect": None},
        ),
        capture_logs() as logs,
    ):
        await monitor._tick()

    fallback_events = [e for e in logs if e["event"] == "strategy_monitor.expiry_fallback_used"]
    assert len(fallback_events) == 1
    assert fallback_events[0]["strategy"] == "paper_ic_nifty_v1_monthly"
    assert fallback_events[0]["position_count"] == 1


@pytest.mark.asyncio
async def test_fetch_chains_logs_fallback_to_expiry_fn_for_open_positions() -> None:
    """BUG-2 follow-up (2026-07-20): _fetch_chains falling back to expiry_fn()
    because every position failed resolution must log
    strategy_monitor.chain_fetch_fallback_to_expiry_fn with how many real
    positions are about to be mis-assigned.
    """
    pos = PaperPosition(
        strategy_name="paper_ic_nifty_v1_monthly",
        leg_role="short_put",
        net_qty=-65,
        avg_cost=Decimal("0"),
        avg_sell_price=Decimal("21.40"),
        instrument_key="NSE_FO|63896",
    )
    monitor = _make_monitor(expiry_fn=lambda: "2026-08-25")  # no lookup

    with capture_logs() as logs:
        await monitor._fetch_chains([pos])

    fallback_events = [
        e for e in logs if e["event"] == "strategy_monitor.chain_fetch_fallback_to_expiry_fn"
    ]
    assert len(fallback_events) == 1
    assert fallback_events[0]["open_position_count"] == 1
    assert fallback_events[0]["fallback_expiry"] == "2026-08-25"


@pytest.mark.asyncio
async def test_tick_single_expiry_single_chain_fetch() -> None:
    """All positions share one expiry → exactly one get_option_chain call."""
    from datetime import date

    positions = [
        PaperPosition(
            strategy_name="paper_csp_nifty_v1",
            leg_role="short_put",
            net_qty=-65,
            avg_cost=Decimal("0"),
            avg_sell_price=Decimal("100"),
            instrument_key="NIFTY30JUN2026PE23000",
            entry_date=date(2026, 6, 1),
        ),
        PaperPosition(
            strategy_name="paper_csp_nifty_v1",
            leg_role="short_put",
            net_qty=-65,
            avg_cost=Decimal("0"),
            avg_sell_price=Decimal("80"),
            instrument_key="NIFTY30JUN2026PE22500",  # same expiry
            entry_date=date(2026, 6, 1),
        ),
    ]

    strategy = MockStrategy()
    strategy.check_signals = AsyncMock(return_value=[])
    store = _make_store(positions=positions)

    broker = MagicMock()
    broker.get_option_chain = AsyncMock(return_value=[])

    monitor = _make_monitor(broker=broker, store=store, strategies=[strategy])

    with (
        patch("src.strategy.monitor.is_trading_day", return_value=True),
        patch(
            "src.strategy.monitor.datetime",
            **{"now.return_value": _fake_ist_time(10, 0), "side_effect": None},
        ),
    ):
        await monitor._tick()

    assert broker.get_option_chain.call_count == 1


@pytest.mark.asyncio
async def test_tick_all_chains_fail_skips_gracefully() -> None:
    """All chain fetches raise DataFetchError → tick skips signal eval, heartbeat written."""
    from datetime import date

    pos = PaperPosition(
        strategy_name="paper_csp_nifty_v1",
        leg_role="short_put",
        net_qty=-65,
        avg_cost=Decimal("0"),
        avg_sell_price=Decimal("100"),
        instrument_key="NIFTY30JUN2026PE23000",
        entry_date=date(2026, 6, 1),
    )
    strategy = MockStrategy()
    strategy.check_signals = AsyncMock(return_value=[])
    store = _make_store(positions=[pos])

    broker = MagicMock()
    broker.get_option_chain = AsyncMock(side_effect=DataFetchError("timeout"))

    monitor = _make_monitor(broker=broker, store=store, strategies=[strategy])

    with (
        patch("src.strategy.monitor.is_trading_day", return_value=True),
        patch(
            "src.strategy.monitor.datetime",
            **{"now.return_value": _fake_ist_time(10, 0), "side_effect": None},
        ),
    ):
        await monitor._tick()

    strategy.check_signals.assert_not_called()
    store.write_heartbeat.assert_called_once()


# ---------------------------------------------------------------------------
# _log_live_pnl_diag() — BUG-019 diagnostic
# ---------------------------------------------------------------------------
#
# User-reported (2026-07-23): suspected disparity between the live monitor's
# intraday P&L and paper_snapshot.py's EOD-cron reading, for paper_ic_nifty_v2
# specifically (BUG-018) but suspected generally. _log_live_pnl_diag calls
# the *exact* PaperTracker.compute_pnl the EOD snapshot cron calls, once per
# strategy with open positions, restricted to the 15:20-15:30 IST window so
# it doesn't add a get_ltp batch call to every ~90s tick all day.


def _open_position(strategy_name: str = "paper_mock_strategy") -> PaperPosition:
    """A single open (net_qty != 0) leg for the given strategy."""
    return PaperPosition(
        strategy_name=strategy_name,
        leg_role="short_put",
        net_qty=-1,
        avg_cost=Decimal("0"),
        avg_sell_price=Decimal("100"),
        instrument_key="NSE_FO|63930",
    )


def _flat_position(strategy_name: str = "paper_mock_strategy") -> PaperPosition:
    """A closed (net_qty == 0) leg — should never trigger the diagnostic."""
    return PaperPosition(
        strategy_name=strategy_name,
        leg_role="short_put",
        net_qty=0,
        avg_cost=Decimal("0"),
        avg_sell_price=Decimal("100"),
        instrument_key="NSE_FO|63930",
    )


@pytest.mark.asyncio
async def test_live_pnl_diag_logged_inside_close_window() -> None:
    """Open position + time inside [15:20, 15:30] → compute_pnl called, logged."""
    positions = [_open_position()]
    store = _make_store(positions=positions)
    strategy = MockStrategy()
    monitor = _make_monitor(store=store, strategies=[strategy])
    monitor._tracker = MagicMock()
    monitor._tracker.compute_pnl = AsyncMock(
        return_value=(Decimal("500.25"), Decimal("0"), Decimal("500.25"))
    )

    with (
        patch("src.strategy.monitor.is_trading_day", return_value=True),
        patch(
            "src.strategy.monitor.datetime",
            **{"now.return_value": _fake_ist_time(15, 25), "side_effect": None},
        ),
        capture_logs() as logs,
    ):
        await monitor._tick()

    monitor._tracker.compute_pnl.assert_awaited_once_with(strategy.strategy_name)
    diag = [e for e in logs if e.get("event") == "strategy_monitor.live_pnl_diag"]
    assert diag and diag[0]["strategy"] == strategy.strategy_name
    assert diag[0]["total_pnl"] == "500.25"
    assert diag[0]["time"] == "15:25"


@pytest.mark.parametrize(
    ("hour", "minute", "should_fire"),
    [
        (15, 20, True),  # window start, inclusive
        (15, 30, True),  # market close, inclusive
        (15, 19, False),  # one minute before window start
        (15, 31, False),  # one minute after close — exercises _log_live_pnl_diag's
        # own `> _MARKET_CLOSE` boundary directly, independent of _tick()'s
        # outer 09:15-15:30 market-hours guard which would normally reject
        # this time before _log_live_pnl_diag is ever reached in production.
    ],
)
@pytest.mark.asyncio
async def test_live_pnl_diag_window_boundaries(hour: int, minute: int, should_fire: bool) -> None:
    """Off-by-one regression coverage for the 15:20-15:30 inclusive window.

    Code-review finding (2026-07-23): the original tests only covered one
    clearly-inside and one clearly-outside time, leaving the `<`/`>`
    boundary comparisons — exactly where off-by-one errors hide — unasserted.
    Calls `_log_live_pnl_diag` directly (not via `_tick()`) so the window
    check is isolated from the outer market-hours guard.
    """
    monitor = _make_monitor(strategies=[MockStrategy()])
    monitor._tracker = MagicMock()
    monitor._tracker.compute_pnl = AsyncMock(
        return_value=(Decimal("1"), Decimal("0"), Decimal("1"))
    )

    await monitor._log_live_pnl_diag(
        now_ist=_fake_ist_time(hour, minute),
        per_strategy_positions={"paper_mock_strategy": [_open_position()]},
        trace_id="test-trace",
    )

    if should_fire:
        monitor._tracker.compute_pnl.assert_awaited_once()
    else:
        monitor._tracker.compute_pnl.assert_not_awaited()


@pytest.mark.asyncio
async def test_live_pnl_diag_skipped_outside_window() -> None:
    """Open position but time outside [15:20, 15:30] → compute_pnl never called."""
    positions = [_open_position()]
    store = _make_store(positions=positions)
    strategy = MockStrategy()
    monitor = _make_monitor(store=store, strategies=[strategy])
    monitor._tracker = MagicMock()
    monitor._tracker.compute_pnl = AsyncMock()

    with (
        patch("src.strategy.monitor.is_trading_day", return_value=True),
        patch(
            "src.strategy.monitor.datetime",
            **{"now.return_value": _fake_ist_time(11, 0), "side_effect": None},
        ),
    ):
        await monitor._tick()

    monitor._tracker.compute_pnl.assert_not_awaited()


@pytest.mark.asyncio
async def test_live_pnl_diag_skipped_when_strategy_flat() -> None:
    """Inside window but every position net_qty == 0 → compute_pnl never called."""
    positions = [_flat_position()]
    store = _make_store(positions=positions)
    strategy = MockStrategy()
    monitor = _make_monitor(store=store, strategies=[strategy])
    monitor._tracker = MagicMock()
    monitor._tracker.compute_pnl = AsyncMock()

    with (
        patch("src.strategy.monitor.is_trading_day", return_value=True),
        patch(
            "src.strategy.monitor.datetime",
            **{"now.return_value": _fake_ist_time(15, 25), "side_effect": None},
        ),
    ):
        await monitor._tick()

    monitor._tracker.compute_pnl.assert_not_awaited()


@pytest.mark.asyncio
async def test_live_pnl_diag_swallows_compute_pnl_exception() -> None:
    """A compute_pnl failure is logged and does not crash the tick / block heartbeat."""
    positions = [_open_position()]
    store = _make_store(positions=positions)
    strategy = MockStrategy()
    monitor = _make_monitor(store=store, strategies=[strategy])
    monitor._tracker = MagicMock()
    monitor._tracker.compute_pnl = AsyncMock(side_effect=RuntimeError("get_ltp failed"))

    with (
        patch("src.strategy.monitor.is_trading_day", return_value=True),
        patch(
            "src.strategy.monitor.datetime",
            **{"now.return_value": _fake_ist_time(15, 25), "side_effect": None},
        ),
        capture_logs() as logs,
    ):
        await monitor._tick()

    store.write_heartbeat.assert_called_once()
    err = [e for e in logs if e.get("event") == "strategy_monitor.live_pnl_diag_error"]
    assert err and err[0]["strategy"] == strategy.strategy_name


@pytest.mark.asyncio
async def test_live_pnl_diag_skipped_when_compute_pnl_returns_none() -> None:
    """compute_pnl returning None (no trades at all) → nothing logged, no crash."""
    positions = [_open_position()]
    store = _make_store(positions=positions)
    strategy = MockStrategy()
    monitor = _make_monitor(store=store, strategies=[strategy])
    monitor._tracker = MagicMock()
    monitor._tracker.compute_pnl = AsyncMock(return_value=None)

    with (
        patch("src.strategy.monitor.is_trading_day", return_value=True),
        patch(
            "src.strategy.monitor.datetime",
            **{"now.return_value": _fake_ist_time(15, 25), "side_effect": None},
        ),
        capture_logs() as logs,
    ):
        await monitor._tick()

    diag = [e for e in logs if e.get("event") == "strategy_monitor.live_pnl_diag"]
    assert diag == []
    store.write_heartbeat.assert_called_once()


# ---------------------------------------------------------------------------
# EC-2: observability log lines (q12 ruling, DECISIONS.md 2026-06-26)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_chain_fetch_complete_logged() -> None:
    """After a successful chain fetch, chain_fetch_complete is logged with
    expiry, strike_count, and fetch_latency_ms.

    Field is `expiry`, not the story spec's `strategy_name` — chains are
    fetched once per unique expiry and shared across every strategy holding
    a position in that expiry (see StrategyMonitor._fetch_chains), so there
    is no single strategy_name to attach to one fetch.
    """
    positions = [_open_position()]
    store = _make_store(positions=positions)
    strategy = MockStrategy()
    strategy.check_signals = AsyncMock(return_value=[])
    monitor = _make_monitor(store=store, strategies=[strategy])

    with (
        patch("src.strategy.monitor.is_trading_day", return_value=True),
        patch(
            "src.strategy.monitor.datetime",
            **{"now.return_value": _fake_ist_time(10, 0), "side_effect": None},
        ),
        capture_logs() as logs,
    ):
        await monitor._tick()

    fetched = [e for e in logs if e.get("event") == "strategy_monitor.chain_fetch_complete"]
    assert len(fetched) == 1
    # No lookup wired on the monitor → NSE_FO|63930 is unresolvable, so
    # _fetch_chains falls back to expiry_fn()'s default ("2026-06-26").
    assert fetched[0]["expiry"] == "2026-06-26"
    assert fetched[0]["strike_count"] == 0
    assert isinstance(fetched[0]["fetch_latency_ms"], int)
    assert fetched[0]["fetch_latency_ms"] >= 0


@pytest.mark.asyncio
async def test_tick_summary_logged() -> None:
    """After a tick, tick_summary is logged with strategies_evaluated,
    signals_emitted, and tick_duration_ms."""
    strategy = MockStrategy()
    strategy.check_signals = AsyncMock(return_value=[])
    store = _make_store()
    monitor = _make_monitor(store=store, strategies=[strategy])

    with (
        patch("src.strategy.monitor.is_trading_day", return_value=True),
        patch(
            "src.strategy.monitor.datetime",
            **{"now.return_value": _fake_ist_time(10, 0), "side_effect": None},
        ),
        capture_logs() as logs,
    ):
        await monitor._tick()

    summary = [e for e in logs if e.get("event") == "strategy_monitor.tick_summary"]
    assert len(summary) == 1
    assert summary[0]["strategies_evaluated"] == 1
    assert summary[0]["signals_emitted"] == 0
    assert isinstance(summary[0]["tick_duration_ms"], int)
    assert summary[0]["tick_duration_ms"] >= 0


@pytest.mark.asyncio
async def test_tick_summary_signal_count_matches() -> None:
    """Two strategies emitting 3 signals total → signals_emitted == 3."""
    info_event = SignalEvent(
        event_type="IVR_HIGH", severity="INFO", description="IVR above 50", payload={}
    )
    warn_event = SignalEvent(
        event_type="DELTA_BREACH", severity="WARN", description="delta breach", payload={}
    )

    strategy_a = MockStrategy()
    strategy_a.check_signals = AsyncMock(return_value=[info_event, warn_event])
    strategy_b = MockStrategy()
    strategy_b.strategy_name = "paper_mock_strategy_b"
    strategy_b.check_signals = AsyncMock(return_value=[info_event])

    store = _make_store()
    notifier = _make_notifier()
    monitor = _make_monitor(store=store, notifier=notifier, strategies=[strategy_a, strategy_b])

    with (
        patch("src.strategy.monitor.is_trading_day", return_value=True),
        patch(
            "src.strategy.monitor.datetime",
            **{"now.return_value": _fake_ist_time(10, 0), "side_effect": None},
        ),
        capture_logs() as logs,
    ):
        await monitor._tick()

    summary = [e for e in logs if e.get("event") == "strategy_monitor.tick_summary"]
    assert len(summary) == 1
    assert summary[0]["strategies_evaluated"] == 2
    assert summary[0]["signals_emitted"] == 3


# ---------------------------------------------------------------------------
# Helpers (private to this module)
# ---------------------------------------------------------------------------


def _fake_ist_time(hour: int, minute: int) -> MagicMock:
    """Return a mock datetime with .hour, .minute, and .date() set for IST."""
    from datetime import date, timedelta, timezone

    _IST = timezone(timedelta(hours=5, minutes=30))
    dt = MagicMock()
    dt.hour = hour
    dt.minute = minute
    dt.date.return_value = date(2026, 6, 2)  # a Monday
    return dt

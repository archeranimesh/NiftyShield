"""Unit tests for StrategyMonitor (PB1.2).

All tests are fully offline — no network calls, no real DB, no fixtures on disk.
The store and notifier are MagicMock objects; the broker is either a MagicMock
(async) or a MockBrokerClient with a queued error.
"""

from __future__ import annotations

import asyncio
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from src.client.exceptions import DataFetchError
from src.models.options import OptionChain
from src.paper.models import PaperPosition
from src.strategy.monitor import StrategyMonitor
from src.strategy.protocol import ApprovedAction, SignalEvent

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
async def test_tick_action_signal_sends_approval_and_creates_pending_row() -> None:
    """ACTION signal → send_approval_request called once, add_pending_approval called once."""
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
    store.add_pending_approval.assert_called_once_with(
        strategy.strategy_name, action_event
    )
    notifier.send_plain_message.assert_not_called()


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
# Helpers (private to this module)
# ---------------------------------------------------------------------------


def _fake_ist_time(hour: int, minute: int) -> MagicMock:
    """Return a mock datetime with .hour, .minute, and .date() set for IST."""
    from datetime import date, datetime, timedelta, timezone

    _IST = timezone(timedelta(hours=5, minutes=30))
    dt = MagicMock()
    dt.hour = hour
    dt.minute = minute
    dt.date.return_value = date(2026, 6, 2)  # a Monday
    return dt

"""StrategyMonitor — backbone daemon loop for paper-trading signal routing.

One instance per process. Registered strategies are polled on every tick.
Signal routing:
    INFO   → structlog DEBUG, no Telegram
    WARN   → plain Telegram message
    ACTION → Telegram approval request + pending_approvals DB row

The monitor never knows about IC, CSP, or 3-track — those are plugged in
as PaperStrategy instances via register() or the constructor.
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import date, datetime, timedelta, timezone
from typing import Callable

import structlog

from src.client.exceptions import DataFetchError
from src.client.protocol import BrokerClient
from src.client.upstox_market import parse_upstox_option_chain
from src.market_calendar.holidays import is_trading_day
from src.models.options import OptionChain
from src.paper.models import PaperPosition
from src.paper.store import PaperStore
from src.strategy.protocol import PaperStrategy, SignalEvent

log = structlog.get_logger(__name__)

_IST = timezone(timedelta(hours=5, minutes=30))
_MARKET_OPEN = (9, 15)
_MARKET_CLOSE = (15, 30)

_NIFTY_INSTRUMENT = "NSE_INDEX|Nifty 50"


class StrategyMonitor:
    """Backbone daemon loop — polls registered strategies and routes signals.

    Args:
        broker: Live or mock broker client (BrokerClient protocol).
        store: PaperStore for reading positions and writing heartbeat /
            pending_approvals rows (write_heartbeat + add_pending_approval
            are added by PB1.6).
        notifier: Any object with send_plain_message and send_approval_request
            coroutines (TelegramGateway from PB1.5 satisfies this structurally).
        strategies: Pre-registered strategies; more can be added via register().
        poll_interval_s: Seconds between ticks (default 90).
        expiry_fn: Zero-arg callable returning the target expiry date string
            (YYYY-MM-DD) for the NIFTY option chain fetch on each tick.
            Production callers should wire this to InstrumentLookup.get_expiry_candidates.
            If None, _fetch_chain returns an empty OptionChain (safe for testing).
    """

    def __init__(
        self,
        broker: BrokerClient,
        store: PaperStore,
        notifier: object,
        strategies: list[PaperStrategy] | None = None,
        poll_interval_s: int = 90,
        expiry_fn: Callable[[], str] | None = None,
    ) -> None:
        self._broker = broker
        self._store = store
        self._notifier = notifier
        self._strategies: list[PaperStrategy] = list(strategies or [])
        self._poll_interval_s = poll_interval_s
        self._expiry_fn = expiry_fn

    def register(self, strategy: PaperStrategy) -> None:
        """Add a strategy to the registry after construction.

        Args:
            strategy: A PaperStrategy-conformant instance.
        """
        self._strategies.append(strategy)

    async def run(self) -> None:
        """Main daemon loop. Runs until cancelled via asyncio.CancelledError."""
        while True:
            await self._tick()
            await asyncio.sleep(self._poll_interval_s)

    async def _tick(self) -> None:
        """Single tick — extracted for testability.

        Sequence:
          1. Guard: skip if not a trading day or outside 09:15–15:30 IST.
          2. Fetch live OptionChain (shared across all strategies).
          3. For each strategy: load positions → check_signals → route events.
          4. Write heartbeat.
        """
        now_ist = datetime.now(tz=_IST)
        today = now_ist.date()

        if not is_trading_day(today):
            log.debug("strategy_monitor.skip", reason="not_trading_day", date=str(today))
            self._write_heartbeat(os.getpid())
            return

        hour_min = (now_ist.hour, now_ist.minute)
        if hour_min < _MARKET_OPEN or hour_min > _MARKET_CLOSE:
            log.debug(
                "strategy_monitor.skip",
                reason="outside_market_hours",
                time=f"{now_ist.hour:02d}:{now_ist.minute:02d}",
            )
            self._write_heartbeat(os.getpid())
            return

        chain = await self._fetch_chain()
        if chain is None:
            self._write_heartbeat(os.getpid())
            return

        for strategy in self._strategies:
            positions = self._store.get_positions(strategy.strategy_name)
            try:
                events = await strategy.check_signals(chain, positions)
            except Exception:
                log.exception(
                    "strategy_monitor.check_signals_error",
                    strategy=strategy.strategy_name,
                )
                continue

            for event in events:
                await self._route_event(event, strategy, chain, positions)

        self._write_heartbeat(os.getpid())

    async def _route_event(
        self,
        event: SignalEvent,
        strategy: PaperStrategy,
        chain: OptionChain,
        positions: list[PaperPosition],
    ) -> None:
        """Dispatch a SignalEvent based on severity.

        Args:
            event: The signal emitted by the strategy.
            strategy: The strategy that emitted it (for context).
            chain: Current option chain (passed to describe_context).
            positions: Current open positions for this strategy.
        """
        if event.severity == "INFO":
            log.debug(
                "strategy_monitor.signal_info",
                strategy=strategy.strategy_name,
                event_type=event.event_type,
                description=event.description,
            )
        elif event.severity == "WARN":
            text = f"[{strategy.strategy_name}] {event.event_type}: {event.description}"
            await self._notifier.send_plain_message(text)  # type: ignore[attr-defined]
        elif event.severity == "ACTION":
            context_str = strategy.describe_context(event, chain, positions)
            await self._notifier.send_approval_request(event, context_str)  # type: ignore[attr-defined]
            self._store.add_pending_approval(strategy.strategy_name, event)  # type: ignore[attr-defined]

    async def _fetch_chain(self) -> OptionChain | None:
        """Fetch and parse the live NIFTY option chain.

        Returns None on DataFetchError so the caller skips the tick gracefully.
        Returns an empty-strikes OptionChain if expiry_fn is not configured
        (safe for testing without BOD data).

        Returns:
            Parsed OptionChain or None on fetch failure.
        """
        if self._expiry_fn is None:
            log.debug("strategy_monitor.expiry_fn_not_set")
            return parse_upstox_option_chain([])

        expiry_str = self._expiry_fn()
        try:
            raw = await self._broker.get_option_chain(_NIFTY_INSTRUMENT, expiry_str)
        except DataFetchError as exc:
            log.warning("strategy_monitor.chain_fetch_error", error=str(exc))
            return None

        data = raw if isinstance(raw, list) else []
        return parse_upstox_option_chain(data)

    def _write_heartbeat(self, pid: int) -> None:
        """Upsert daemon_heartbeat row (id=1).

        Calls PaperStore.write_heartbeat — added in PB1.6.  Until that
        migration lands, this is a documented forward-reference.

        Args:
            pid: Current process ID (os.getpid()).
        """
        strategy_names = [s.strategy_name for s in self._strategies]
        self._store.write_heartbeat(pid, strategy_names, last_event=None)  # type: ignore[attr-defined]

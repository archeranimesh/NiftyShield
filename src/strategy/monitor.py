"""StrategyMonitor — backbone daemon loop for paper-trading signal routing.

One instance per process. Registered strategies are polled on every tick.
Signal routing:
    INFO   → structlog DEBUG, no Telegram
    WARN   → plain Telegram message
    ACTION + strategy.auto_execute + payload["auto_execute"]
           → apply_action() called directly; send_notification() on completion
    ACTION (otherwise)
           → Telegram approval request + pending_approvals DB row

The monitor never knows about IC, CSP, or 3-track — those are plugged in
as PaperStrategy instances via register() or the constructor.
"""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import Callable
from datetime import datetime, timedelta, timezone

import structlog

from src.client.exceptions import DataFetchError
from src.client.protocol import BrokerClient
from src.client.upstox_market import parse_upstox_option_chain
from src.market_calendar.holidays import is_trading_day
from src.models.options import OptionChain
from src.paper.models import PaperPosition
from src.paper.store import PaperStore
from src.strategy.protocol import ApprovedAction, PaperStrategy, SignalEvent
from src.utils.logging import bind_trace_id, generate_trace_id

log = structlog.get_logger(__name__)

_IST = timezone(timedelta(hours=5, minutes=30))
_MARKET_OPEN = (9, 15)
_MARKET_CLOSE = (15, 30)

_NIFTY_INSTRUMENT = "NSE_INDEX|Nifty 50"


class StrategyMonitor:
    """Backbone daemon loop — polls registered strategies and routes signals.

    Args:
        broker: Live or mock broker client (BrokerClient protocol).
        store: PaperStore for reading positions, writing heartbeat, and
            persisting pending_approvals rows via create_approval.
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
            try:
                await self._tick()
            except Exception:
                log.exception("strategy_monitor.tick_unhandled_error")
            await asyncio.sleep(self._poll_interval_s)

    async def _tick(self) -> None:
        """Single tick — extracted for testability.

        Sequence:
          1. Bind a fresh trace_id to the structlog context for this tick.
          2. Guard: skip if not a trading day or outside 09:15–15:30 IST.
          3. Fetch live OptionChain (shared across all strategies).
          4. For each strategy: load positions → check_signals → route events.
          5. Write heartbeat.
        """
        trace_id = generate_trace_id()
        bind_trace_id(trace_id)
        log.info("tick.start", trace_id=trace_id)
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

        log.info("tick.end", trace_id=trace_id)
        self._write_heartbeat(os.getpid())

    async def _route_event(
        self,
        event: SignalEvent,
        strategy: PaperStrategy,
        chain: OptionChain,
        positions: list[PaperPosition],
    ) -> None:
        """Dispatch a SignalEvent based on severity and strategy auto_execute flag.

        For ACTION events on an auto-execute strategy (``strategy.auto_execute``
        is True and ``event.payload["auto_execute"]`` is True), ``apply_action``
        is called directly and a plain notification is sent.  All other ACTION
        events route to the Telegram approval flow.

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
            auto_execute_strategy = getattr(strategy, "auto_execute", False)
            auto_execute_payload = event.payload.get("auto_execute", False)

            if auto_execute_strategy and auto_execute_payload:
                action_type: str = event.payload.get("auto_action", "CLOSE_AND_WAIT")
                metadata = {
                    k: event.payload[k] for k in ("triggering_signal",) if k in event.payload
                }
                action = ApprovedAction(
                    action_type=action_type,
                    legs_to_close=[event.payload.get("leg_role", "short_put")],
                    legs_to_open=[],
                    rationale="auto-execute",
                    council_rank=1,
                    metadata=metadata,
                )
                try:
                    await strategy.apply_action(positions, action)
                    log.info(
                        "strategy_monitor.auto_execute_dispatched",
                        strategy=strategy.strategy_name,
                        event_type=event.event_type,
                        action_type=action_type,
                    )
                except Exception:
                    log.exception(
                        "strategy_monitor.auto_execute_failed",
                        strategy=strategy.strategy_name,
                        event_type=event.event_type,
                        action_type=action_type,
                    )
            else:
                context_str = strategy.describe_context(event, chain, positions)
                msg_id = await self._notifier.send_approval_request(event, context_str)  # type: ignore[attr-defined]
                expires_at = (datetime.now(tz=timezone.utc) + timedelta(hours=1)).isoformat()
                self._store.create_approval(
                    strategy.strategy_name,
                    event.event_type,
                    json.dumps(event.payload),
                    msg_id,
                    expires_at,
                )

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

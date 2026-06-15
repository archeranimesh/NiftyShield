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
from datetime import date, datetime, timedelta, timezone
from datetime import date as _date

import structlog

from src.client.exceptions import DataFetchError
from src.client.protocol import BrokerClient
from src.client.upstox_market import parse_upstox_option_chain
from src.instruments.lookup import InstrumentLookup, parse_expiry
from src.market_calendar.holidays import is_trading_day, market_today
from src.models.options import OptionChain
from src.notifications.protocol import NotifierProtocol
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
            Used as a fallback when no positions carry a parseable expiry.
            If None and no positions are open, _fetch_chains returns {}.
        lookup: Optional BOD instrument lookup for resolving numeric instrument
            keys (e.g. NSE_FO|71474) to their expiry dates.  Required for
            accurate multi-expiry chain fetch; without it, only named-key
            positions (e.g. NIFTY29MAY2026PE22500) have their expiry resolved.
    """

    def __init__(
        self,
        broker: BrokerClient,
        store: PaperStore,
        notifier: NotifierProtocol,
        strategies: list[PaperStrategy] | None = None,
        poll_interval_s: int = 90,
        expiry_fn: Callable[[], str] | None = None,
        lookup: InstrumentLookup | None = None,
    ) -> None:
        self._broker = broker
        self._store = store
        self._notifier: NotifierProtocol = notifier
        self._strategies: list[PaperStrategy] = list(strategies or [])
        self._poll_interval_s = poll_interval_s
        self._expiry_fn = expiry_fn
        self._lookup = lookup

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
          3. Collect all positions; derive unique expiry dates.
          4. Fetch one OptionChain per unique expiry (cached by date).
          5. For each strategy: call check_signals with the chain matching
             each position's expiry subset → route events.
          6. Write heartbeat.
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

        # Collect positions for all strategies up-front so we can derive expiries.
        per_strategy_positions: dict[str, list[PaperPosition]] = {}
        all_positions: list[PaperPosition] = []
        for strategy in self._strategies:
            positions = self._store.get_positions(strategy.strategy_name)
            per_strategy_positions[strategy.strategy_name] = positions
            all_positions.extend(positions)

        chains = await self._fetch_chains(all_positions)
        if not chains:
            log.warning("strategy_monitor.no_chains_available")
            self._write_heartbeat(os.getpid())
            return

        for strategy in self._strategies:
            positions = per_strategy_positions[strategy.strategy_name]
            # Group this strategy's positions by expiry; call check_signals once
            # per expiry subset so each position is evaluated against the right chain.
            expiry_groups = self._group_positions_by_expiry(positions)
            if not expiry_groups:
                # No resolvable expiry — fall back to first available chain.
                expiry_groups = {next(iter(chains)): positions}
            for expiry_date, expiry_positions in expiry_groups.items():
                chain = chains.get(expiry_date)
                if chain is None:
                    log.warning(
                        "strategy_monitor.no_chain_for_expiry",
                        strategy=strategy.strategy_name,
                        expiry=str(expiry_date),
                    )
                    continue
                try:
                    events = await strategy.check_signals(chain, expiry_positions)
                except Exception:
                    log.exception(
                        "strategy_monitor.check_signals_error",
                        strategy=strategy.strategy_name,
                    )
                    continue

                for event in events:
                    await self._route_event(event, strategy, chain, expiry_positions)

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
            await self._notifier.send_plain_message(text)
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
                msg_id = await self._notifier.send_approval_request(event, context_str)
                expires_at = (datetime.now(tz=timezone.utc) + timedelta(hours=1)).isoformat()
                self._store.create_approval(
                    strategy.strategy_name,
                    event.event_type,
                    json.dumps(event.payload),
                    msg_id,
                    expires_at,
                )

    def _get_position_expiry(self, pos: PaperPosition) -> date | None:
        """Resolve expiry date from a position's instrument key.

        Tries named-key regex first (e.g. NIFTY29MAY2026PE22500 → 2026-05-29),
        then BOD lookup for numeric keys (e.g. NSE_FO|71474) if lookup is wired.

        Args:
            pos: Open paper position.

        Returns:
            Expiry date or None when unresolvable.
        """
        import re as _re

        _KEY_EXPIRY_RE = _re.compile(r"NIFTY(\d{2})([A-Za-z]{3})(\d{4})(CE|PE)", _re.IGNORECASE)
        _MONTH_ABBR = {
            "JAN": 1,
            "FEB": 2,
            "MAR": 3,
            "APR": 4,
            "MAY": 5,
            "JUN": 6,
            "JUL": 7,
            "AUG": 8,
            "SEP": 9,
            "OCT": 10,
            "NOV": 11,
            "DEC": 12,
        }
        m = _KEY_EXPIRY_RE.search(pos.instrument_key)
        if m:
            try:
                day = int(m.group(1))
                month = _MONTH_ABBR.get(m.group(2).upper())
                year = int(m.group(3))
                if month:
                    return _date(year, month, day)
            except (ValueError, TypeError):
                pass

        if self._lookup is not None:
            inst = self._lookup.get_by_key(pos.instrument_key)
            if inst is not None:
                expiry_str = parse_expiry(inst.get("expiry"))
                if expiry_str:
                    try:
                        return _date.fromisoformat(expiry_str)
                    except ValueError:
                        pass
        return None

    def _group_positions_by_expiry(
        self, positions: list[PaperPosition]
    ) -> dict[date, list[PaperPosition]]:
        """Group positions by their resolved expiry date.

        Positions whose expiry cannot be resolved are collected under None
        and excluded from the returned dict (they trigger the fallback path).

        Args:
            positions: List of open paper positions.

        Returns:
            Dict mapping expiry date → positions sharing that expiry.
        """
        groups: dict[date, list[PaperPosition]] = {}
        for pos in positions:
            if pos.net_qty == 0:
                continue
            exp = self._get_position_expiry(pos)
            if exp is not None:
                groups.setdefault(exp, []).append(pos)
        return groups

    async def _fetch_chains(self, positions: list[PaperPosition]) -> dict[date, OptionChain]:
        """Fetch one OptionChain per unique expiry found in positions.

        Positions are examined to derive their expiry dates; one API call is
        made per unique expiry.  Falls back to ``expiry_fn`` when no positions
        carry a resolvable expiry (or when the list is empty).  Returns ``{}``
        if no chain can be fetched.

        Args:
            positions: All open positions across all registered strategies.

        Returns:
            Dict mapping expiry date → parsed OptionChain.
        """
        unique_expiries: set[date] = set()
        for pos in positions:
            if pos.net_qty == 0:
                continue
            exp = self._get_position_expiry(pos)
            if exp is not None:
                unique_expiries.add(exp)

        # Fallback: use expiry_fn when positions carry no parseable expiry.
        if not unique_expiries and self._expiry_fn is not None:
            expiry_str = self._expiry_fn()
            try:
                unique_expiries.add(_date.fromisoformat(expiry_str))
            except ValueError:
                pass

        if not unique_expiries:
            log.debug("strategy_monitor.expiry_fn_not_set_and_no_positions")
            # Return a single empty chain so test strategies without BOD still work.
            return {market_today(): parse_upstox_option_chain([])}

        chains: dict[date, OptionChain] = {}
        for expiry_date in unique_expiries:
            expiry_str = expiry_date.isoformat()
            try:
                raw = await self._broker.get_option_chain(_NIFTY_INSTRUMENT, expiry_str)
            except DataFetchError as exc:
                log.warning(
                    "strategy_monitor.chain_fetch_error",
                    expiry=expiry_str,
                    error=str(exc),
                )
                continue
            data = raw if isinstance(raw, list) else []
            chains[expiry_date] = parse_upstox_option_chain(data)
            log.debug(
                "strategy_monitor.chain_fetched",
                expiry=expiry_str,
                strikes=len(chains[expiry_date].strikes),
            )

        return chains

    def _write_heartbeat(self, pid: int) -> None:
        """Upsert daemon_heartbeat row (id=1).

        Calls PaperStore.write_heartbeat — added in PB1.6.  Until that
        migration lands, this is a documented forward-reference.

        Args:
            pid: Current process ID (os.getpid()).
        """
        strategy_names = [s.strategy_name for s in self._strategies]
        self._store.write_heartbeat(pid, strategy_names, last_event=None)  # type: ignore[attr-defined]

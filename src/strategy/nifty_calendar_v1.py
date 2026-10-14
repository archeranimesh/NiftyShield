"""NiftyCalendarV1: paper shell for the Nifty positional calendar (any variant).

All variant behaviour arrives through injected collaborators (``StructureSelector``,
``ExitRule``, ``CyclePolicy``) and a frozen ``CalendarVariantConfig``; this file
holds no variant branch. ``StrategyMonitor`` calls ``check_signals`` once per
expiry group with only that expiry's chain, so the shell acts only on the call
whose chain is the near expiry, reads every position from the store and fetches
the far chain through the injected broker (CM-0 design amendment). Cycle state is
rebuilt from ``paper_trades`` each tick; only the breach spot history is in memory.
"""

from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import Callable
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import structlog

from src.client.exceptions import DataFetchError
from src.client.protocol import BrokerClient
from src.client.upstox_market import parse_upstox_option_chain
from src.instruments.lookup import InstrumentLookup
from src.models.options import OptionChain
from src.models.portfolio import TradeAction
from src.nifty_calendar.config import CalendarVariantConfig
from src.nifty_calendar.cycle import CyclePolicy, EntryPlan
from src.nifty_calendar.errors import CalendarError
from src.nifty_calendar.exit_rules import (
    CycleExitState,
    ExitDecision,
    ExitRule,
    ExitSnapshot,
)
from src.nifty_calendar.payoff import compute_metrics
from src.nifty_calendar.selector import NoEntry, StructureSelector, mid
from src.notifications.protocol import NotifierProtocol
from src.paper.models import ExitSignal, PaperPosition, PaperTrade
from src.paper.store import PaperStore
from src.strategy.executor import PaperFillSimulator
from src.strategy.nifty_calendar_notify import ClosedLeg, send_close_message
from src.strategy.nifty_calendar_state import (
    LONG_CALL_WING,
    SHORT_CALL,
    build_structure,
    cycle_entry_date,
    cycle_origin_date,
    entry_leg_specs,
    executable_pnl,
    far_carry,
    is_close_trade,
    is_recentre_close,
    ledger_collisions,
    leg_quotes,
    resolve_open_legs,
    sold_short_strikes_on,
)
from src.strategy.protocol import ApprovedAction, LegClose, SignalEvent
from src.strategy.reentry_mixin import ReEntryMixin

log = structlog.get_logger(__name__)

_IST = ZoneInfo("Asia/Kolkata")
_NIFTY_INSTRUMENT = "NSE_INDEX|Nifty 50"
_CHAIN_TIMEOUT_S = 15.0
_MAX_REENTRIES_PER_DAY = 1
_EXIT_SIGNAL: dict[ExitDecision, ExitSignal] = {
    ExitDecision.TARGET: ExitSignal.PROFIT_TARGET,
    ExitDecision.TIME_EXIT: ExitSignal.TIME_STOP,
    ExitDecision.DTE_GUARD: ExitSignal.DTE_FORCED,
    ExitDecision.CLOSE_BREACH_LATE: ExitSignal.LOSS_STOP,
    ExitDecision.RECENTRE: ExitSignal.LOSS_STOP,
    ExitDecision.REDEPLOY_SAME_PAIR: ExitSignal.PROFIT_TARGET,
    ExitDecision.RECENTRE_OFF_CENTRE: ExitSignal.LOSS_STOP,
}


def _now_ist() -> datetime:
    return datetime.now(tz=_IST)


class NiftyCalendarV1(ReEntryMixin):
    """Paper strategy for a net-long-vega Nifty calendar; variant-agnostic."""

    auto_execute: bool = True
    _store: PaperStore  # narrows the mixin's Optional: the shell always has a store

    def __init__(
        self,
        *,
        broker: BrokerClient,
        store: PaperStore,
        notifier: NotifierProtocol | None,
        simulator: PaperFillSimulator,
        selector: StructureSelector,
        exit_rule: ExitRule,
        cycle_policy: CyclePolicy,
        config: CalendarVariantConfig,
        lookup: InstrumentLookup,
        vix_data_dir: Path = Path("data/historical/ohlc/india_vix"),
        vix_fn: Callable[[], float | None] = lambda: None,
        clock: Callable[[], datetime] = _now_ist,
    ) -> None:
        """Wire collaborators; nothing is constructed here.

        Args:
            broker: Source of the far-expiry chain.
            store: Ledger; the only source of cycle state.
            notifier: Telegram gateway used by the re-entry notice (may be None).
            simulator: Synthetic fill engine (mid plus VIX-regime slippage).
            selector: Picks the four-leg structure at entry.
            exit_rule: Variant exit rule.
            cycle_policy: Variant entry window and exit dates.
            config: Frozen variant configuration; names the strategy.
            lookup: BOD instrument lookup (key to strike/expiry and back).
            vix_data_dir: VIX history used by the re-entry check.
            vix_fn: Returns current India VIX for slippage, or None.
            clock: Timezone-aware IST clock (injectable for tests).
        """
        self.strategy_name = config.strategy_name
        self.reentry_leg_role = SHORT_CALL
        self.reentry_script_hint = (
            "python -m scripts.strategies.nifty_calendar.paper_calendar_entry"
        )
        self._broker, self._store, self._notifier = broker, store, notifier
        self._simulator, self._selector, self._exit_rule = simulator, selector, exit_rule
        self._policy, self._config, self._lookup = cycle_policy, config, lookup
        self._vix_data_dir, self._vix_fn, self._clock = vix_data_dir, vix_fn, clock
        self._spot_history: deque[tuple[datetime, Decimal]] = deque()

    @property
    def config(self) -> CalendarVariantConfig:
        """The variant configuration this shell was wired with."""
        return self._config

    # ── Signals ──────────────────────────────────────────────────────────────

    async def check_signals(
        self, market: OptionChain, positions: list[PaperPosition]
    ) -> list[SignalEvent]:
        """Entry when flat in the entry window, else evaluate the exit rule.

        ``positions`` is the monitor's per-expiry subset and is ignored; the full
        structure is read from the store.
        """
        held = [p for p in self._store.get_positions(self.strategy_name) if p.net_qty != 0]
        now = self._clock()
        if not held:
            return await self.plan_entry(market, now)
        return await self._exit_events(market, held, now)

    @staticmethod
    def _warn(event_type: str, description: str) -> SignalEvent:
        return SignalEvent(event_type, "WARN", description, {"leg_role": ""})

    async def _chain(self, expiry: date, market: OptionChain) -> OptionChain | None:
        """Return the chain for ``expiry`` (the given one if it matches), or None."""
        if market.expiry == expiry:
            return market
        try:
            raw = await asyncio.wait_for(
                self._broker.get_option_chain(_NIFTY_INSTRUMENT, expiry.isoformat()),
                timeout=_CHAIN_TIMEOUT_S,
            )
        except (DataFetchError, asyncio.TimeoutError) as exc:
            log.warning("nifty_calendar.chain_fetch_failed", expiry=str(expiry), error=str(exc))
            return None
        chain = parse_upstox_option_chain(raw if isinstance(raw, list) else [])
        return chain if chain.strikes else None

    def cycle_plan(self, entry_date: date) -> EntryPlan | None:
        """Plan of the original cycle that a (possibly re-centred) structure entered on ``entry_date``."""
        origin = cycle_origin_date(
            self._store.get_trades(self.strategy_name),
            entry_date,
            lambda d: self._policy.entry_window(d) is not None,
        )
        if origin is None:
            return None
        orig_plan = self._policy.entry_window(origin)
        if orig_plan is None:
            return None
        # Optional policy hook (documented on CyclePolicy): pins the original pair and hard exit.
        if hasattr(self._policy, "redeploy_plan"):
            return self._policy.redeploy_plan(orig_plan, entry_date)
        return orig_plan

    async def plan_entry(self, market: OptionChain, now: datetime) -> list[SignalEvent]:
        """Entry events for a flat strategy; also called directly by the entry script.

        Same-day re-entry after a RECENTRE close is allowed, including on the cycle's own entry
        day (Animesh, 2026-10-14), under the original cycle's plan so its hard exit date is
        kept. Any other close today blocks, and at most one re-entry per day is allowed.
        """
        today = now.date()
        trades = self._store.get_trades(self.strategy_name)
        todays = [t for t in trades if t.trade_date == today]
        if any(is_close_trade(t) and not is_recentre_close(t) for t in todays):
            return []  # already closed today for a non-re-centre reason: no churn
        recentres = sum(1 for t in todays if t.leg_role == SHORT_CALL and is_recentre_close(t))
        if recentres > _MAX_REENTRIES_PER_DAY:  # the 2nd re-centre close today stays flat
            return []
        plan = self.cycle_plan(today) if todays else self._policy.entry_window(today)
        if plan is None or now.time() < plan.entry_time_ist or today >= plan.hard_exit_date:
            return []
        near = await self._chain(plan.near_expiry, market)
        far = await self._chain(plan.far_expiry, market)
        if near is None or far is None:
            return [self._warn("NC_CHAIN_UNAVAILABLE", "near or far chain unavailable")]
        # A same-day re-entry must not reuse a short strike already sold today: the ledger's
        # unique key would drop the SELL silently. Fresh entries pass no exclusions.
        blocked = sold_short_strikes_on(trades, self._lookup, today) if todays else frozenset()
        result = self._selector.select(near, far, market.underlying_spot, self._config, blocked)
        if isinstance(result, NoEntry):
            log.info("nifty_calendar.no_entry", reason=result.reason, filter=result.failed_filter)
            return [self._warn("NC_NO_ENTRY", f"{result.reason} [{result.failed_filter}]")]
        try:
            specs = entry_leg_specs(result, self._lookup, self._config.lot_size)
        except CalendarError as exc:
            return [self._warn("NC_KEY_UNRESOLVED", str(exc))]
        if clashes := ledger_collisions(specs, trades, today):
            log.error("nifty_calendar.same_day_ledger_collision", legs=clashes)
            return [self._warn("NC_LEDGER_COLLISION", f"legs {clashes} already traded today")]
        payload: dict[str, Any] = {
            "auto_execute": True,
            "auto_action": "OPEN_STRUCTURE",
            "legs_to_open": specs,
            "legs_to_close": [],
        }
        desc = f"Open {self._config.name} calendar at {result.short_strike}"
        return [SignalEvent("NC_ENTRY", "ACTION", desc, payload)]

    async def _exit_events(
        self, market: OptionChain, held: list[PaperPosition], now: datetime
    ) -> list[SignalEvent]:
        try:
            legs = resolve_open_legs(held, self._lookup)
        except CalendarError as exc:
            return [self._warn("NC_STRUCTURE_INCOMPLETE", str(exc))]
        near_expiry, far_expiry = legs[SHORT_CALL].expiry, legs[LONG_CALL_WING].expiry
        if market.expiry != near_expiry:
            return []  # far-expiry group call: the near call decides for the whole structure
        far = await self._chain(far_expiry, market)
        if far is None:
            return [self._warn("NC_CHAIN_UNAVAILABLE", "far chain unavailable")]
        plan = self.cycle_plan(cycle_entry_date(legs))
        if plan is None:
            return [self._warn("NC_PLAN_MISSING", "no entry plan for the cycle entry date")]
        spot, lot = market.underlying_spot, self._config.lot_size
        try:
            quotes = leg_quotes(legs, {near_expiry: market, far_expiry: far})
            metrics = compute_metrics(
                build_structure(legs, quotes, lot),
                spot,
                far_carry=far_carry(far, spot),
                lot_size=lot,
            )
            pnl = executable_pnl(legs, quotes)
        except (CalendarError, ValueError) as exc:
            return [self._warn("NC_SNAPSHOT_UNAVAILABLE", str(exc))]
        self._record_spot(now, spot)
        lots = abs(legs[SHORT_CALL].position.net_qty) // lot
        state = CycleExitState(
            entry_date=plan.entry_date,
            entry_spot=legs[SHORT_CALL].strike,  # ATM strike proxy; the rules do not read it
            entry_short_strike=legs[SHORT_CALL].strike,
            plan=plan,
            target_pnl=self._config.target_per_lot * lots,
        )
        snap = ExitSnapshot(
            spot, tuple(self._spot_history), pnl, metrics.breakeven_low, metrics.breakeven_high
        )
        decision = self._exit_rule.evaluate(state, snap, now)
        if decision == ExitDecision.HOLD:
            return []
        payload: dict[str, Any] = {
            "auto_execute": True,
            "auto_action": f"CLOSE_{decision.value}",
            "exit_decision": decision.value,
            "near_expiry": near_expiry.isoformat(),
            "legs_to_open": [],
            "legs_to_close": [
                {"leg_role": r, "instrument_key": leg.position.instrument_key}
                for r, leg in legs.items()
            ],
            "mids": {legs[r].position.instrument_key: str(mid(q)) for r, q in quotes.items()},
        }
        desc = f"{decision.value}: executable pnl {pnl:.0f} vs target {state.target_pnl:.0f}"
        return [SignalEvent(f"NC_{decision.value}", "ACTION", desc, payload)]

    def _record_spot(self, now: datetime, spot: Decimal) -> None:
        """Append a spot sample and drop samples older than twice the breach window."""
        self._spot_history.append((now, spot))
        cutoff = now - timedelta(minutes=2 * self._config.breach_confirm_minutes)
        while self._spot_history and self._spot_history[0][0] < cutoff:
            self._spot_history.popleft()

    def describe_context(
        self, event: SignalEvent, market: OptionChain, positions: list[PaperPosition]
    ) -> str:
        """Plain-text context for an event."""
        held = ", ".join(f"{p.leg_role} {p.net_qty}" for p in positions if p.net_qty != 0)
        return (
            f"{self.strategy_name} {event.event_type}: {event.description}. "
            f"Spot {market.underlying_spot}, expiry {market.expiry}. Open: {held or 'flat'}."
        )

    # ── Execution ────────────────────────────────────────────────────────────

    async def apply_action(
        self, positions: list[PaperPosition], action: ApprovedAction
    ) -> list[PaperPosition]:
        """Open the structure (``legs_to_open``) or close it (``legs_to_close``)."""
        vix = self._vix_fn()
        if action.legs_to_open:
            self._open_structure(action, vix)
        else:
            await self._close_structure(action, vix)
        return self._store.get_positions(self.strategy_name)

    def _record(self, trade: PaperTrade) -> bool:
        """Persist a trade and log loudly if the ledger dropped it as a duplicate."""
        inserted = self._store.record_trade(trade)
        if not inserted:
            log.error(
                "nifty_calendar.duplicate_trade_dropped",
                leg_role=trade.leg_role,
                instrument_key=trade.instrument_key,
                action=trade.action.value,
            )
        return inserted

    def _open_structure(self, action: ApprovedAction, vix: float | None) -> None:
        if any(p.net_qty != 0 for p in self._store.get_positions(self.strategy_name)):
            log.warning("nifty_calendar.open_skipped_position_exists", strategy=self.strategy_name)
            return
        today = self._clock().date()
        for spec in action.legs_to_open:
            if spec.price is None:
                raise ValueError(f"LegSpec {spec.leg_role} carries no price")
            fill = self._simulator.simulate_fill(
                spec.instrument_key, spec.action, spec.quantity, spec.price, vix
            )
            self._record(
                PaperTrade(
                    strategy_name=self.strategy_name,
                    leg_role=spec.leg_role,
                    instrument_key=spec.instrument_key,
                    trade_date=today,
                    action=TradeAction(spec.action),
                    quantity=fill.quantity,
                    price=fill.fill_price,
                    notes=f"{self._config.name} entry slippage={fill.slippage}",
                )
            )

    async def _close_structure(self, action: ApprovedAction, vix: float | None) -> None:
        """Close every open leg; a crash mid-loop is recovered by re-running the same action."""
        meta = action.metadata or {}
        mids: dict[str, str] = meta.get("mids", {})
        targets: list[tuple[LegClose, PaperPosition]] = []
        for lc in action.legs_to_close:
            pos = self._store.get_position(
                self.strategy_name, lc.leg_role, instrument_key=lc.instrument_key
            )
            if pos.net_qty == 0:
                continue
            if pos.instrument_key not in mids:
                raise ValueError(f"no mid supplied for {lc.leg_role} {pos.instrument_key}")
            targets.append((lc, pos))  # validate every leg before writing any
        today = self._clock().date()
        decision = str(meta.get("exit_decision", action.action_type))
        closed: list[ClosedLeg] = []
        for lc, pos in targets:
            side = TradeAction.BUY if pos.net_qty < 0 else TradeAction.SELL
            fill = self._simulator.simulate_fill(
                pos.instrument_key,
                side.value,
                abs(pos.net_qty),
                Decimal(mids[pos.instrument_key]),
                vix,
            )
            trade = PaperTrade(
                strategy_name=self.strategy_name,
                leg_role=lc.leg_role,
                instrument_key=pos.instrument_key,
                trade_date=today,
                action=side,
                quantity=fill.quantity,
                price=fill.fill_price,
                notes=f"{decision} slippage={fill.slippage}",
            )
            if self._record(trade):
                self._store.mark_trade_closed(self.strategy_name, lc.leg_role, pos.instrument_key)
                entry = pos.avg_sell_price if pos.net_qty < 0 else pos.avg_cost
                closed.append(
                    ClosedLeg(
                        lc.leg_role, pos.instrument_key, entry, fill.fill_price, fill.quantity
                    )
                )
        self._spot_history.clear()
        short = next((p for lc, p in targets if lc.leg_role == SHORT_CALL), None)
        if short is None:
            return
        self._write_exit_event(short, decision, meta)
        near = date.fromisoformat(meta["near_expiry"])
        recentre = decision in (
            ExitDecision.RECENTRE.value,
            ExitDecision.RECENTRE_OFF_CENTRE.value,
            ExitDecision.REDEPLOY_SAME_PAIR.value,
        )
        held = (today - short.entry_date).days if short.entry_date else 0
        await send_close_message(
            self._notifier, self._store, self._lookup, strategy_name=self.strategy_name,
            signal=decision, near_expiry=near, today=today, held_days=held, legs=closed,
            recentre=recentre,
        )  # fmt: skip
        if recentre:
            await self._check_reentry(
                expiry=near, today=today, instrument_key=short.instrument_key, trade_id=0
            )

    def _write_exit_event(self, short: PaperPosition, decision: str, meta: dict[str, Any]) -> None:
        """Best-effort audit row for the close; never blocks the trades already written."""
        try:
            near = date.fromisoformat(meta["near_expiry"])
            self._store.create_exit_event(
                strategy_name=self.strategy_name,
                leg_name=SHORT_CALL,
                trade_id="0",
                event_time=datetime.now(timezone.utc),
                detected_by="INTRADAY",
                exit_signal=_EXIT_SIGNAL[ExitDecision(decision)],
                severity="ACTION",
                entry_price=short.avg_sell_price,
                dte=(near - self._clock().date()).days,
                notes=f"{self._config.name} {decision}",
            )
        except Exception as exc:  # audit row only; trades are already persisted
            log.warning("nifty_calendar.exit_event_failed", error=str(exc))

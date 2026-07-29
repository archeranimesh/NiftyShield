"""IronCondorV1 — backbone-compatible Iron Condor strategy for Nifty 50.

Implements PaperStrategy protocol so StrategyMonitor can auto-detect exit
signals for the paper_ic_nifty_v1 strategy.  Entry remains manual via
``scripts/paper_ic_entry.py`` (future script — not in this phase).

Signal table
------------
| Event type    | Severity | Trigger                                        |
|---------------|----------|------------------------------------------------|
| PROFIT_TARGET | ACTION   | combined mark ≤ 50% of entry credit            |
| LOSS_STOP     | ACTION   | combined mark ≥ 2.0× entry credit              |
| DELTA_STOP    | ACTION   | either short leg |delta| ≥ 0.35                |
| ROLL_WING     | ACTION   | short leg |delta| ≥ 0.35 AND roll target found  |
| TIME_STOP     | ACTION   | DTE ≤ 14                                       |
| DELTA_WARN    | WARN     | either short leg |delta| ≥ 0.25                |
| DTE_WARN      | INFO     | DTE ≤ 21                                       |

No adjustments are permitted in v1 except ROLL_WING rolls, which
are auto-executed when OTM replacements exist.
"""

from __future__ import annotations

import re
from dataclasses import replace
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Literal

import structlog

from src.instruments.lookup import InstrumentLookup
from src.market_calendar.holidays import market_today
from src.models.options import OptionChain, OptionLeg
from src.paper.constants import DEFAULT_BOD_PATH
from src.paper.models import PaperPosition, PaperTrade
from src.strategy import roll_utils
from src.strategy.ic_close_executor import close_ic_legs
from src.strategy.protocol import ApprovedAction, LegClose, LegSpec, SignalEvent

if TYPE_CHECKING:
    from src.client.protocol import BrokerClient
    from src.notifications.telegram_gateway import TelegramGateway
    from src.paper.store import PaperStore
    from src.strategy.ic_expiry_config import ICExpiryConfig

log = structlog.get_logger(__name__)

# ── Regexes ───────────────────────────────────────────────────────────────────

# Matches both live key formats:
#   "NSE_FO|NIFTY26JUN2026PE24000" → group 1 = "26JUN2026"  (date before strike)
#   "NSE_FO|NIFTY26JUN202624000PE" → group 1 = "26JUN2026"  (date before PE/CE suffix)
_EXPIRY_RE = re.compile(
    r"NSE_FO\|NIFTY(\d{2}[A-Za-z]{3}\d{4})",
    re.IGNORECASE,
)

# Matches keys like "NSE_FO|NIFTY23000PE" or "NSE_FO|NIFTY23000CE"
_STRIKE_RE = re.compile(r"NIFTY(\d+)(PE|CE)", re.IGNORECASE)

# ── Leg role sets ─────────────────────────────────────────────────────────────

_SHORT_ROLES = {"short_call", "short_put"}
_LONG_ROLES = {"long_call_hedge", "long_put_hedge"}
_ALL_ROLES = _SHORT_ROLES | _LONG_ROLES

# ── Allowed action types ─────────────────────────────────────────────────────
# ROLL_WING added in PA1.2: per-wing roll to farther OTM strike when threatened.

_ALLOWED_ACTIONS = {"CLOSE_FULL", "CLOSE_CALL_SPREAD", "CLOSE_PUT_SPREAD", "ROLL_WING"}


def _leg_close_matches(pos: PaperPosition, leg: LegClose) -> bool:
    """Return True when ``leg`` identifies ``pos`` as the position to close.

    Matches on ``leg_role`` always; additionally matches on ``instrument_key``
    when the ``LegClose`` supplies one, so that a roll overlap (two positions
    sharing a ``leg_role`` with different ``instrument_key``s) only selects
    the specific instrument being closed (PG-4f).
    """
    if pos.leg_role != leg.leg_role:
        return False
    if leg.instrument_key is not None:
        return pos.instrument_key == leg.instrument_key
    return True


def _position_for_role(ic_positions: list[PaperPosition], leg_role: str) -> PaperPosition | None:
    """Resolve the position to close for ``leg_role``.

    When two positions share ``leg_role`` (roll overlap), picks the one with
    the most-recent ``entry_date`` — mirrors ``PaperStore.get_position``'s
    ambiguity handling (PG-2a) so the auto-selected close target is
    consistent with the rest of the codebase.
    """
    matches = [p for p in ic_positions if p.leg_role == leg_role]
    if not matches:
        return None
    if len(matches) == 1:
        return matches[0]
    log.warning(
        "ic_nifty_v1.position_for_role_ambiguous",
        leg_role=leg_role,
        match_count=len(matches),
    )
    return max(matches, key=lambda p: p.entry_date or date.min)


class IronCondorV1:
    """Backbone-compatible wrapper for the paper_ic_nifty_v1 strategy.

    Registers with StrategyMonitor to emit exit signals on every tick.
    The strategy name must match the ``strategy_name`` column used by
    ``record_paper_trade.py`` when recording IC trades.

    No adjustments are permitted in v1 except ROLL_WING rolls, which
    are auto-executed when OTM replacements exist.
    """

    auto_execute: bool = True

    def __init__(
        self,
        broker: BrokerClient | None = None,
        store: PaperStore | None = None,
        notifier: TelegramGateway | None = None,
        config: ICExpiryConfig | None = None,
    ) -> None:
        from src.strategy.ic_expiry_config import CONFIGS

        self._config = config if config is not None else CONFIGS["monthly"]
        self._broker = broker
        self._store = store
        self._notifier = notifier

    @property
    def strategy_name(self) -> str:
        """DB discriminator derived from injected config."""
        return self._config.strategy_name

    # ── PaperStrategy protocol ────────────────────────────────────────────────

    async def check_signals(
        self,
        market: OptionChain,
        positions: list[PaperPosition],
    ) -> list[SignalEvent]:
        """Evaluate exit signals for the open Iron Condor position.

        Filters positions to ``strategy_name == "paper_ic_nifty_v1"`` and to
        ``net_qty != 0``. A flat leg's ``instrument_key`` is its most
        recently *closed* contract (``PaperStore.get_positions`` still
        returns one ``PaperPosition`` per ``leg_role`` regardless of
        flatness, per BUG-014) — once that contract settles, Upstox's BOD
        file drops it permanently, so resolving it via ``_find_leg`` can
        never succeed again. Without this filter, a fully-closed IC keeps
        emitting ``strike_parse_failed``/``mark_unavailable`` warnings on
        every tick indefinitely. Same defect class as BUG-014, one layer up
        the call chain (see DECISIONS.md 2026-07-21).
        Returns ``[]`` when no open IC positions exist.  All four legs are
        evaluated together; P&L signals are based on the combined mark.

        Args:
            market: Current Nifty 50 option chain snapshot.
            positions: All open paper positions (may include other strategies).

        Returns:
            List of detected SignalEvents; empty list when nothing to act on.
        """
        ic_positions = [
            p for p in positions if p.strategy_name == self.strategy_name and p.net_qty != 0
        ]
        if not ic_positions:
            return []

        events: list[SignalEvent] = []

        # ── DTE (parse from any leg — all share the same expiry) ─────────────
        expiry = next(
            (self._parse_expiry(p.instrument_key) for p in ic_positions),
            None,
        )
        dte = (expiry - market_today()).days if expiry is not None else None

        if dte is not None:
            if dte <= self._config.time_stop_dte:
                events.append(
                    SignalEvent(
                        event_type="TIME_STOP",
                        severity="ACTION",
                        description=f"DTE {dte} ≤ {self._config.time_stop_dte} — time stop triggered",
                        payload={
                            "dte": dte,
                            "valid_actions": [
                                "CLOSE_FULL",
                                "CLOSE_CALL_SPREAD",
                                "CLOSE_PUT_SPREAD",
                            ],
                        },
                    )
                )
            if dte <= self._config.dte_warn:
                events.append(
                    SignalEvent(
                        event_type="DTE_WARN",
                        severity="INFO",
                        description=f"DTE {dte} ≤ {self._config.dte_warn} — approaching expiry",
                        payload={"dte": dte},
                    )
                )

        # ── Delta signals (short legs only) ───────────────────────────────────
        short_legs = [p for p in ic_positions if p.leg_role in _SHORT_ROLES]
        for pos in short_legs:
            opt_leg = self._find_leg(market, pos.instrument_key)
            if opt_leg is None:
                continue
            if opt_leg.delta is None:
                continue  # Greek missing — cannot evaluate delta signals
            abs_delta = abs(opt_leg.delta)
            if abs_delta >= self._config.delta_stop:
                events.append(
                    SignalEvent(
                        event_type="DELTA_STOP",
                        severity="ACTION",
                        description=(
                            f"{pos.leg_role} |delta| {abs_delta} ≥ {self._config.delta_stop}"
                            " — delta stop triggered"
                        ),
                        payload={
                            "leg_role": pos.leg_role,
                            "delta": str(opt_leg.delta),
                            "valid_actions": [
                                "CLOSE_FULL",
                                "CLOSE_CALL_SPREAD",
                                "CLOSE_PUT_SPREAD",
                            ],
                        },
                    )
                )
                # Attempt roll: fire ROLL_WING alongside DELTA_STOP when a
                # farther OTM replacement is available.
                roll_target = self._select_wing_roll_target(market, pos.leg_role, opt_leg.strike)
                if roll_target is not None:
                    candidate_leg = self._find_leg(market, roll_target.instrument_key)
                    if candidate_leg is None:
                        log.warning(
                            "ic_nifty_v1.roll_wing_chain_lookup_failed",
                            instrument_key=roll_target.instrument_key,
                        )
                    suggested_strike = (
                        str(candidate_leg.strike) if candidate_leg is not None else ""
                    )
                    suggested_delta = str(candidate_leg.delta) if candidate_leg is not None else ""
                    suggested_mid_price = (
                        str(candidate_leg.ltp) if candidate_leg is not None else ""
                    )
                    events.append(
                        SignalEvent(
                            event_type="ROLL_WING",
                            severity="ACTION",
                            description=(
                                f"{pos.leg_role} roll target available: "
                                f"{roll_target.instrument_key} "
                                f"(δ≈{suggested_delta})"
                            ),
                            payload={
                                "leg_role": pos.leg_role,
                                "current_instrument_key": pos.instrument_key,
                                "current_delta": str(opt_leg.delta),
                                "suggested_instrument_key": roll_target.instrument_key,
                                "suggested_strike": suggested_strike,
                                "suggested_delta": suggested_delta,
                                "suggested_mid_price": suggested_mid_price,
                                "valid_actions": [
                                    "ROLL_WING",
                                    "CLOSE_FULL",
                                    "CLOSE_CALL_SPREAD",
                                    "CLOSE_PUT_SPREAD",
                                ],
                            },
                        )
                    )
            if abs_delta >= self._config.delta_warn:
                events.append(
                    SignalEvent(
                        event_type="DELTA_WARN",
                        severity="WARN",
                        description=(
                            f"{pos.leg_role} |delta| {abs_delta} ≥ {self._config.delta_warn} — delta warning"
                        ),
                        payload={
                            "leg_role": pos.leg_role,
                            "delta": str(opt_leg.delta),
                        },
                    )
                )

        # ── Combined mark signals ─────────────────────────────────────────────
        combined_mark, entry_credit = self._compute_combined_pnl(market, ic_positions)
        if combined_mark is None or entry_credit <= Decimal("0"):
            # 2026-07-20: this guard used to silently skip PROFIT_TARGET/
            # LOSS_STOP entirely with no trace — the exact failure point of
            # the BUG-2 follow-up incident. `grep pnl_gate_skipped` now shows
            # every tick this strategy went unmonitored and why.
            # See DECISIONS.md 2026-07-20.
            log.debug(
                "ic_nifty_v1.pnl_gate_skipped",
                strategy=self.strategy_name,
                reason="mark_unavailable" if combined_mark is None else "entry_credit_not_positive",
                entry_credit=str(entry_credit),
            )
        if combined_mark is not None and entry_credit > Decimal("0"):
            pct = combined_mark / entry_credit
            if pct <= self._config.profit_target_pct:
                events.append(
                    SignalEvent(
                        event_type="PROFIT_TARGET",
                        severity="ACTION",
                        description=(
                            f"Combined mark {combined_mark} ≤ "
                            f"{int(self._config.profit_target_pct * 100)}% of entry credit "
                            f"{entry_credit}"
                        ),
                        payload={
                            "combined_mark": str(combined_mark),
                            "entry_credit": str(entry_credit),
                            "pct_remaining": str(pct.quantize(Decimal("0.01"))),
                            "valid_actions": [
                                "CLOSE_FULL",
                                "CLOSE_CALL_SPREAD",
                                "CLOSE_PUT_SPREAD",
                            ],
                        },
                    )
                )
            if pct >= self._config.loss_stop_pct:
                events.append(
                    SignalEvent(
                        event_type="LOSS_STOP",
                        severity="ACTION",
                        description=(
                            f"Combined mark {combined_mark} ≥ "
                            f"{int(self._config.loss_stop_pct * 100)}% of entry credit "
                            f"{entry_credit}"
                        ),
                        payload={
                            "combined_mark": str(combined_mark),
                            "entry_credit": str(entry_credit),
                            "pct_of_credit": str(pct.quantize(Decimal("0.01"))),
                            "valid_actions": [
                                "CLOSE_FULL",
                                "CLOSE_CALL_SPREAD",
                                "CLOSE_PUT_SPREAD",
                            ],
                        },
                    )
                )

        # Wire _auto_select_action logic
        if self.auto_execute:
            selected_action = self._auto_select_action(events, ic_positions)
            if selected_action is not None:
                filtered_events: list[SignalEvent] = []
                action_emitted = False
                for e in events:
                    if e.severity != "ACTION":
                        filtered_events.append(e)
                    else:
                        is_match = False
                        if selected_action.action_type == "CLOSE_FULL" and e.event_type in (
                            "LOSS_STOP",
                            "TIME_STOP",
                            "PROFIT_TARGET",
                        ):
                            is_match = True
                        elif (
                            selected_action.action_type == "ROLL_WING"
                            and e.event_type == "ROLL_WING"
                        ):
                            is_match = True
                        elif (
                            selected_action.action_type in ("CLOSE_CALL_SPREAD", "CLOSE_PUT_SPREAD")
                            and e.event_type == "DELTA_STOP"
                        ):
                            leg_role = e.payload.get("leg_role")
                            if (
                                selected_action.action_type == "CLOSE_CALL_SPREAD"
                                and leg_role == "short_call"
                            ):
                                is_match = True
                            elif (
                                selected_action.action_type == "CLOSE_PUT_SPREAD"
                                and leg_role == "short_put"
                            ):
                                is_match = True

                        if is_match and not action_emitted:
                            new_payload = {
                                **e.payload,
                                "auto_execute": True,
                                "auto_action": selected_action.action_type,
                            }
                            filtered_events.append(replace(e, payload=new_payload))
                            action_emitted = True
                events = filtered_events
            else:
                # If auto-execute is enabled but no action was selected (because no ACTION
                # events were present), strip any residual ACTION events as a safety fallback
                # to prevent them from entering the manual Telegram approval flow.
                events = [e for e in events if e.severity != "ACTION"]

        return events

    def _compute_ivr_str(self) -> str:
        """Load VIX Parquet series and compute IVR; returns formatted string.

        Returns:
            ``"IVR: 0.42"`` on success, ``"IVR: unavailable"`` on any data gap.
        """
        from pathlib import Path

        from src.backtest.ivr import compute_ivr
        from src.backtest.vix_ingest import fetch_vix_latest, load_vix_series

        vix_dir = Path("data/historical/ohlc/india_vix")
        ivr_str = "unavailable"
        if vix_dir.exists():
            try:
                vix_series = load_vix_series(vix_dir)
                vix_today = fetch_vix_latest()
                if vix_today is not None:
                    ivr = compute_ivr(vix_today, vix_series)
                    ivr_str = f"{ivr:.2f}" if ivr is not None else "unavailable"
            except Exception:
                pass  # non-fatal: VIX data gap
        return f"IVR: {ivr_str}"

    def describe_context(
        self,
        event: SignalEvent,
        market: OptionChain,
        positions: list[PaperPosition],
    ) -> str:
        """Build a plain-text context block for the council prompt.

        Summarises: call spread delta, put spread delta, combined credit,
        mark-to-market, DTE, IVR (from VIX Parquet; "unavailable" on data gap), Nifty spot.

        Args:
            event: The signal event that triggered the context request.
            market: Current Nifty 50 option chain snapshot.
            positions: All open paper positions.

        Returns:
            Multi-line plain-text context string; no HTML markup.
        """
        ic_positions = [p for p in positions if p.strategy_name == self.strategy_name]
        expiry = next((self._parse_expiry(p.instrument_key) for p in ic_positions), None)
        dte = (expiry - market_today()).days if expiry is not None else None
        combined_mark, entry_credit = self._compute_combined_pnl(market, ic_positions)

        lines: list[str] = [
            f"Strategy: {self.strategy_name}",
            f"Signal: {event.event_type} ({event.severity})",
            f"Nifty spot: {market.underlying_spot}",
            f"DTE: {dte if dte is not None else 'unavailable'}",
            self._compute_ivr_str(),
            f"Entry credit: {entry_credit}",
            f"Combined mark: {combined_mark if combined_mark is not None else 'unavailable'}",
        ]

        for pos in ic_positions:
            opt_leg = self._find_leg(market, pos.instrument_key)
            lines.append(f"Leg: {pos.leg_role} | key: {pos.instrument_key}")
            if opt_leg is not None:
                lines.append(f"  Delta: {opt_leg.delta}  IV: {opt_leg.iv}  LTP: {opt_leg.ltp}")
            else:
                lines.append("  Chain lookup: unavailable")

        if not ic_positions:
            lines.append("No open IC positions found.")

        return "\n".join(lines)

    async def apply_action(
        self,
        positions: list[PaperPosition],
        action: ApprovedAction,
    ) -> list[PaperPosition]:
        """Validate and apply an approved action.

        Accepted action types: ``CLOSE_FULL``, ``CLOSE_CALL_SPREAD``,
        ``CLOSE_PUT_SPREAD``, and ``ROLL_WING`` (PA1.2).  Any other
        action_type raises ``ValueError``.

        Args:
            positions: Current open paper positions.
            action: Approved action; must have an allowed action_type.

        Returns:
            Updated positions with closed legs filtered out.

        Raises:
            ValueError: When ``action_type`` is not in the allowed set.
        """
        if action.action_type not in _ALLOWED_ACTIONS:
            raise ValueError(
                f"IronCondorV1 does not permit {action.action_type!r} — "
                f"allowed: {sorted(_ALLOWED_ACTIONS)}."
            )

        # Override legs to close if called via auto-execute (where legs_to_close is not fully populated).
        # Roles come from the override (or the action itself); instrument_key is preserved from
        # whatever action.legs_to_close already carries per role — populated by
        # _auto_select_action for the auto-execute path (PG-4f) — so a roll overlap (two
        # positions sharing a leg_role with different instrument_keys) only matches the exact
        # instrument identified by signal evaluation, not "a" position with that role.
        closed = {leg.leg_role for leg in action.legs_to_close}
        if self._is_auto_execute(action):
            if action.action_type == "CLOSE_FULL":
                closed = _SHORT_ROLES | _LONG_ROLES
            elif action.action_type == "CLOSE_CALL_SPREAD":
                closed = {"short_call", "long_call_hedge"}
            elif action.action_type == "CLOSE_PUT_SPREAD":
                closed = {"short_put", "long_put_hedge"}

        key_by_role = {leg.leg_role: leg.instrument_key for leg in action.legs_to_close}
        effective_legs = [LegClose(leg_role=r, instrument_key=key_by_role.get(r)) for r in closed]

        log.info(
            "ic_nifty_v1.apply_action",
            action_type=action.action_type,
            legs_to_close=list(closed),
        )
        if action.action_type == "ROLL_WING":
            if not action.legs_to_open and not self._is_auto_execute(action):
                raise ValueError("ROLL_WING action requires at least one leg in legs_to_open")
            # Note: legs_to_open is intentionally not consumed here.
            # PaperExecutor (backbone) handles the new-leg DB write.
            # apply_action only removes the closed wing from positions.
            # TODO(IC-CLOSE-2): ROLL_WING's own close side is not persisted
            # either — same gap as the flatten actions below, deferred
            # pending strike-selection for the replacement leg. See
            # DECISIONS.md and TODOS.md.
        elif action.action_type in (
            "CLOSE_FULL",
            "CLOSE_CALL_SPREAD",
            "CLOSE_PUT_SPREAD",
        ) and self._is_auto_execute(action):
            # Manual/Telegram-approved actions are persisted by PaperExecutor
            # (src/strategy/executor.py), not here — see monitor_daemon.py's
            # callback path. Only the auto-execute dispatch path (which never
            # reaches PaperExecutor) needs apply_action to self-persist.
            if self._broker is None or self._store is None:
                log.warning(
                    "ic_nifty_v1.apply_action.no_broker_or_store",
                    action_type=action.action_type,
                    strategy_name=self.strategy_name,
                )
            else:
                triggering_signal = (action.metadata or {}).get("event_type", action.action_type)
                closed_trades = await close_ic_legs(
                    broker=self._broker,
                    store=self._store,
                    positions=[
                        p
                        for p in positions
                        if any(_leg_close_matches(p, leg) for leg in effective_legs)
                    ],
                    closed_roles=closed,
                    strategy_name=self.strategy_name,
                    notes=f"ic_nifty_v1 auto-close: {triggering_signal}",
                )
                # BUG-013 (2026-07-20): IronCondorV1 accepted a notifier in its
                # constructor but never called it — every auto-close was
                # silent on Telegram, unlike every other auto-execute
                # strategy (CSP/CC/Collar/PP all confirm on close). See
                # DECISIONS.md 2026-07-20 and docs/bugs/bugs.md BUG-013.
                await self._send_close_notification(
                    action.action_type, triggering_signal, closed_trades
                )
        return [
            p for p in positions if not any(_leg_close_matches(p, leg) for leg in effective_legs)
        ]

    async def _send_close_notification(
        self,
        action_type: str,
        triggering_signal: str,
        closed_trades: list[PaperTrade],
    ) -> None:
        """Send a plain HTML close-confirmation notification. Non-fatal.

        Args:
            action_type: The ApprovedAction.action_type that was executed
                (CLOSE_FULL, CLOSE_CALL_SPREAD, or CLOSE_PUT_SPREAD).
            triggering_signal: The SignalEvent.event_type that caused the
                auto-execute (e.g. PROFIT_TARGET, LOSS_STOP, TIME_STOP).
            closed_trades: The closing PaperTrade rows actually persisted by
                close_ic_legs(); empty when nothing was open to close.
        """
        if self._notifier is None:
            return
        if not closed_trades:
            # close_ic_legs() already logs ic_close_executor.nothing_to_close;
            # no notification needed for a no-op.
            return
        legs_text = "\n".join(
            f"  {t.leg_role}: {t.action.value} {t.quantity} @ {t.price}" for t in closed_trades
        )
        if self._store is None:
            # Known, not exceptional: this instance was constructed without a
            # store (e.g. some test/dry-run paths). Distinct from the try/
            # except below, which is for genuine calc failures against a real
            # store — collapsing both into one except Exception previously
            # made mypy flag self._store as PaperStore | None at the call
            # site and would have logged a misleadingly generic
            # "net_pnl_calc_failed" for a case that isn't a calc failure.
            log.warning("ic_nifty_v1.net_pnl_calc_skipped_no_store")
            pnl_text = ""
        else:
            try:
                # Deferred import: src.paper.tracker -> src.paper.store ->
                # src.strategy.profit_lock_engine creates a circular import if
                # hoisted to module level, since src/strategy/__init__.py
                # eagerly imports this module.
                from src.paper.tracker import get_strategy_realized_pnl

                net_pnl = get_strategy_realized_pnl(self._store, self.strategy_name)
                pnl_text = f"Net P&L: ₹{net_pnl:,.2f}\n"
            except Exception as exc:
                log.warning("ic_nifty_v1.net_pnl_calc_failed", error=str(exc))
                pnl_text = ""
        text = (
            f"✅ <b>IC closed — {triggering_signal}</b>\n"
            f"Strategy: <code>{self.strategy_name}</code>\n"
            f"Action: {action_type}\n"
            f"{pnl_text}"
            f"{legs_text}"
        )
        try:
            await self._notifier.send_notification(text)
        except Exception as exc:
            log.warning("ic_nifty_v1.send_notification.failed", error=str(exc))

    # ── Private helpers ───────────────────────────────────────────────────────

    def _is_auto_execute(self, action: ApprovedAction) -> bool:
        """Determine if an action was initiated automatically or manually."""
        if action.metadata and action.metadata.get("auto_selected"):
            return True
        return action.rationale == "auto-execute"

    def _auto_select_action(
        self, events: list[SignalEvent], ic_positions: list[PaperPosition]
    ) -> ApprovedAction | None:
        """Select one action from a list of fired signals using priority rules.

        Priority (highest first):
          1. LOSS_STOP   → CLOSE_FULL
          2. TIME_STOP   → CLOSE_FULL
          3. PROFIT_TARGET → CLOSE_FULL
          4. ROLL_WING   → ROLL_WING (use suggested_instrument_key from payload)
          5. DELTA_STOP  → CLOSE_CALL_SPREAD or CLOSE_PUT_SPREAD (from leg_role)

        Returns None when no ACTION-severity events are present.

        Args:
            events: All SignalEvents returned by check_signals for this tick.
            ic_positions: Open positions for this strategy (already filtered
                to net_qty != 0) — used to populate each ``LegClose.instrument_key``
                so ``apply_action`` closes the exact instrument identified here,
                not just "a" position sharing the leg_role (PG-4f).

        Returns:
            Single ApprovedAction to execute, or None.
        """
        action_events = [e for e in events if e.severity == "ACTION"]
        if not action_events:
            return None

        types = {e.event_type for e in action_events}

        # Priority 1, 2, 3: Full position exits
        full_close_trigger = next(
            (t for t in ("LOSS_STOP", "TIME_STOP", "PROFIT_TARGET") if t in types), None
        )
        if full_close_trigger is not None:
            return ApprovedAction(
                action_type="CLOSE_FULL",
                legs_to_close=[
                    LegClose(
                        leg_role=r,
                        instrument_key=(
                            pos.instrument_key
                            if (pos := _position_for_role(ic_positions, r)) is not None
                            else None
                        ),
                    )
                    for r in (_SHORT_ROLES | _LONG_ROLES)
                ],
                legs_to_open=[],
                rationale="auto-execute",
                council_rank=1,
                metadata={"auto_selected": True},
            )

        # Priority 4: Roll threatened short wing
        roll_event = next((e for e in action_events if e.event_type == "ROLL_WING"), None)
        if roll_event is not None:
            new_leg = LegSpec(
                instrument_key=roll_event.payload["suggested_instrument_key"],
                action="SELL",
                quantity=1,
                leg_role=roll_event.payload["leg_role"],
                notes=f"auto_roll delta={roll_event.payload['suggested_delta']}",
            )
            return ApprovedAction(
                action_type="ROLL_WING",
                legs_to_close=[
                    LegClose(
                        leg_role=roll_event.payload["leg_role"],
                        instrument_key=roll_event.payload.get("current_instrument_key"),
                    )
                ],
                legs_to_open=[new_leg],
                rationale="auto-execute",
                council_rank=1,
                metadata={"auto_selected": True},
            )

        # Priority 5: Close single spread (delta breach without roll target)
        delta_event = next((e for e in action_events if e.event_type == "DELTA_STOP"), None)
        if delta_event is not None:
            leg_role = delta_event.payload["leg_role"]
            action_type = "CLOSE_CALL_SPREAD" if leg_role == "short_call" else "CLOSE_PUT_SPREAD"
            spread_roles = (
                {"short_call", "long_call_hedge"}
                if leg_role == "short_call"
                else {"short_put", "long_put_hedge"}
            )
            return ApprovedAction(
                action_type=action_type,
                legs_to_close=[
                    LegClose(
                        leg_role=r,
                        instrument_key=(
                            pos.instrument_key
                            if (pos := _position_for_role(ic_positions, r)) is not None
                            else None
                        ),
                    )
                    for r in spread_roles
                ],
                legs_to_open=[],
                rationale="auto-execute",
                council_rank=1,
                metadata={"auto_selected": True},
            )

        return None

    def _select_wing_roll_target(
        self,
        market: OptionChain,
        leg_role: str,
        current_strike: Decimal,
    ) -> LegSpec | None:
        """Find a farther OTM replacement leg for the threatened short wing.

        Delegates delta-range filtering to ``roll_utils.find_strike_by_delta``
        then enforces the directional constraint: the replacement CE must be
        above ``current_strike``; the replacement PE must be below it.

        Args:
            market: Current Nifty 50 option chain snapshot.
            leg_role: ``"short_call"`` or ``"short_put"``.
            current_strike: Strike price of the existing short leg.

        Returns:
            ``LegSpec`` for the best replacement, or ``None`` when no suitable
            strike exists or the chain data is insufficient.
        """
        option_type: Literal["CE", "PE"] = (
            "CE" if leg_role == "short_call" else "PE"  # caller guarantees short_put
        )
        candidate = roll_utils.find_strike_by_delta(
            market,
            option_type,
            (self._config.roll_wing_delta_lo, self._config.roll_wing_delta_hi),
            self._config.roll_wing_target_delta,
        )
        if candidate is None:
            return None

        # Directional guard: roll must move the wing farther OTM.
        if option_type == "CE" and candidate.strike <= current_strike:
            return None
        if option_type == "PE" and candidate.strike >= current_strike:
            return None

        instrument_key = f"NSE_FO|NIFTY{int(candidate.strike)}{option_type}"
        return LegSpec(
            instrument_key=instrument_key,
            action="SELL",
            quantity=1,
            leg_role=leg_role,
            notes=f"roll_wing delta={candidate.delta}",
        )

    def _find_leg(self, market: OptionChain, instrument_key: str) -> OptionLeg | None:
        """Locate a CE or PE leg in the chain for the given instrument key.

        Parses the strike and option type (CE/PE) from ``instrument_key`` via
        regex first. Real Upstox keys are numeric-only (e.g. ``NSE_FO|63896``)
        and never match the regex (BUG-009/BUG-012) — those fall back to a
        BOD instrument-master lookup for ``strike_price``/``instrument_type``,
        mirroring ``CSPNiftyV1._find_put_leg``.

        Args:
            market: Current option chain.
            instrument_key: Position's Upstox instrument key.

        Returns:
            Matching ``OptionLeg``, or ``None`` when unavailable.
        """
        m = _STRIKE_RE.search(instrument_key)
        if not m:
            return self._find_leg_via_bod(market, instrument_key)

        try:
            strike = Decimal(m.group(1))
        except InvalidOperation:
            log.warning(
                "ic_nifty_v1.strike_decimal_failed",
                instrument_key=instrument_key,
            )
            return None

        option_type = m.group(2).upper()
        strike_data = market.strikes.get(strike)
        if strike_data is None:
            return None

        return strike_data.ce if option_type == "CE" else strike_data.pe

    def _find_leg_via_bod(self, market: OptionChain, instrument_key: str) -> OptionLeg | None:
        """Resolve a numeric-only instrument key via the offline BOD master.

        Args:
            market: Current option chain.
            instrument_key: Position's Upstox instrument key (numeric form,
                e.g. ``NSE_FO|63896``, no embedded strike/type substring).

        Returns:
            Matching ``OptionLeg``, or ``None`` when the key can't be
            resolved (missing from BOD, no strike/type recorded, absent from
            the live chain, or an unexpected ``instrument_type``).
        """
        try:
            lookup = InstrumentLookup.from_file(DEFAULT_BOD_PATH)
            inst = lookup.get_by_key(instrument_key)
            if inst is None or inst.get("strike_price") is None:
                log.warning(
                    "ic_nifty_v1.strike_parse_failed",
                    instrument_key=instrument_key,
                    reason="not_found_in_bod",
                )
                return None

            option_type = inst.get("instrument_type")
            if option_type not in ("CE", "PE"):
                log.warning(
                    "ic_nifty_v1.strike_parse_failed",
                    instrument_key=instrument_key,
                    reason="unexpected_instrument_type",
                    instrument_type=option_type,
                )
                return None

            strike = Decimal(str(inst["strike_price"]))
            strike_data = market.strikes.get(strike)
            if strike_data is None:
                return None

            leg = strike_data.ce if option_type == "CE" else strike_data.pe
            if leg is not None:
                log.debug(
                    "ic_nifty_v1.leg_resolved_via_bod",
                    instrument_key=instrument_key,
                    strike=str(strike),
                    option_type=option_type,
                )
            return leg
        except Exception as exc:  # Intentional: fail-safe BOD lookup
            log.warning(
                "ic_nifty_v1.strike_parse_failed",
                instrument_key=instrument_key,
                reason="bod_lookup_failed",
                error=str(exc),
            )
            return None

    def _compute_combined_pnl(
        self,
        market: OptionChain,
        ic_positions: list[PaperPosition],
    ) -> tuple[Decimal | None, Decimal]:
        """Compute the combined current mark and entry credit for the IC.

        Combined mark = sum of short-leg LTPs - sum of long-leg LTPs.
        This is the cost to close the entire IC position at current prices.

        Entry credit = sum of short avg_sell_prices - sum of long avg_costs.

        Returns ``(None, entry_credit)`` when any leg's chain data is missing
        — partial mark is not meaningful for P&L gating decisions.

        Args:
            market: Current option chain snapshot.
            ic_positions: All IC positions for this strategy.

        Returns:
            Tuple of (combined_mark or None, entry_credit).
        """
        entry_credit = Decimal("0")
        combined_mark = Decimal("0")
        mark_available = True

        for pos in ic_positions:
            opt_leg = self._find_leg(market, pos.instrument_key)

            if pos.leg_role in _SHORT_ROLES:
                entry_credit += pos.avg_sell_price
                if opt_leg is not None:
                    combined_mark += opt_leg.ltp
                else:
                    mark_available = False
            elif pos.leg_role in _LONG_ROLES:
                entry_credit -= pos.avg_cost
                if opt_leg is not None:
                    combined_mark -= opt_leg.ltp
                else:
                    mark_available = False

            if opt_leg is None:
                # 2026-07-20: this is the exact point PROFIT_TARGET/LOSS_STOP
                # went silent during the BUG-2 follow-up incident — a leg not
                # found in `market` (e.g. because the daemon fetched the
                # wrong expiry's chain) used to flip mark_available=False
                # with zero logging. See DECISIONS.md 2026-07-20.
                log.warning(
                    "ic_nifty_v1.mark_unavailable",
                    strategy=self.strategy_name,
                    leg_role=pos.leg_role,
                    instrument_key=pos.instrument_key,
                    market_expiry=str(market.expiry),
                )

        return (combined_mark if mark_available else None, entry_credit)

    def _parse_expiry(self, instrument_key: str) -> date | None:
        """Extract the option expiry date from an instrument key.

        Handles keys like ``"NSE_FO|NIFTY29MAY2026PE"`` — returns
        ``date(2026, 5, 29)``.  Returns ``None`` for numeric or
        unrecognised key formats.

        Args:
            instrument_key: Upstox instrument key for the option leg.

        Returns:
            Parsed expiry date, or ``None`` if key carries no date.
        """
        m = _EXPIRY_RE.search(instrument_key)
        if not m:
            return None
        try:
            return datetime.strptime(m.group(1).upper(), "%d%b%Y").date()
        except ValueError:
            return None

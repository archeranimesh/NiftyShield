# src/strategy/collar_overlay_v1.py
"""CollarOverlayV1 — Collar overlay strategy class.

Implements PaperStrategy protocol for the paper_collar_v1 strategy.
Emits exit and warning signals for Collar short call and long put legs.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import structlog

from src.instruments.lookup import InstrumentLookup
from src.market_calendar.holidays import market_today
from src.models.options import OptionChain, OptionLeg
from src.models.portfolio import TradeAction
from src.paper.constants import DEFAULT_BOD_PATH, STRATEGY_COLLAR_OVERLAY
from src.paper.models import PaperPosition, PaperTrade
from src.strategy._price_utils import find_option_leg
from src.strategy.collar_entry import CollarEntrySelectionError, select_and_build_collar_entry
from src.strategy.exit_signals import ExitSignalEngine
from src.strategy.protocol import ApprovedAction, LegClose, SignalEvent
from src.strategy.reentry_mixin import ReEntryMixin

log = structlog.get_logger(__name__)

# Collar3b priority ordering (highest first) — all resolve to the same terminal
# action (atomic close both legs, then immediately reselect and open a fresh
# two-leg pair). Mirrors IronCondorV1._auto_select_action's priority-selection
# pattern. TIME_STOP is deliberately excluded — Collar3b operator ruling:
# DTE_REVIEW (DTE<=5) is the only time-based trigger for Collar, TIME_STOP
# (fixed calendar days_held) is wrong for a position decoupled from actual
# DTE-to-expiry. TIME_STOP may still appear in _check_reentry's own audit-log
# trigger tuple (secondary, logging-only) but never drives this action.
_REENTRY_ACTION_PRIORITY = (
    "CRASH_MONETIZE",
    "LOSS_STOP",
    "PROFIT_TARGET",
    "DTE_REVIEW",
    "DELTA_STOP",
)

# Matches keys like "NSE_FO|NIFTY29MAY2026PE" → group 1 = "29MAY2026"
_EXPIRY_RE = re.compile(
    r"NSE_FO\|NIFTY(\d{2}[A-Za-z]{3}\d{4})(PE|CE)",
    re.IGNORECASE,
)

SHORT_CALL_ROLE = "overlay_collar_call"
LONG_PUT_ROLE = "overlay_collar_put"


def _leg_close_matches(pos: PaperPosition, leg: LegClose) -> bool:
    """Return True when ``leg`` identifies ``pos`` as the position to close.

    Matches on ``leg_role`` always; additionally matches on ``instrument_key``
    when the ``LegClose`` supplies one, so that a roll overlap (two positions
    sharing a ``leg_role`` with different ``instrument_key``s) only selects
    and removes the specific instrument being closed (PG-4e).
    """
    if pos.leg_role != leg.leg_role:
        return False
    if leg.instrument_key is not None:
        return pos.instrument_key == leg.instrument_key
    return True


class CollarOverlayV1(ReEntryMixin):
    """Collar overlay strategy implementation."""

    strategy_name: str = STRATEGY_COLLAR_OVERLAY
    auto_execute: bool = True
    reentry_leg_role: str = "overlay_collar_call"
    reentry_script_hint: str = "run find_overlay_strikes.py --overlay-type collar"

    def __init__(
        self,
        store: Any = None,
        notifier: Any = None,
        vix_data_dir: Path | str | None = None,
        broker: Any = None,
        instrument_lookup: InstrumentLookup | None = None,
    ) -> None:
        """Initialise CollarOverlayV1.

        Args:
            store: PaperStore instance for persisting closing trades. None → writes skipped.
            notifier: TelegramGateway for re-entry notifications. None → notifications skipped.
            vix_data_dir: Path to Parquet VIX data directory for IVR gating. None → settings default.
            broker: BrokerClient for live chain fetch during Collar3b combined
                close+reenter. None → reenter selection is skipped (logged
                WARNING) — used by tests / any caller not wiring live reentry.
            instrument_lookup: Optional pre-built ``InstrumentLookup`` (BOD JSON),
                used by ``find_option_leg`` to resolve real numeric Upstox
                instrument keys that carry no strike/type in the key string
                itself. If not injected, lazily built from ``DEFAULT_BOD_PATH``
                on first use (same pattern as ``PaperStore._resolve_instrument_lookup``).
        """
        self._store = store
        self._notifier = notifier
        self._broker = broker
        self._instrument_lookup = instrument_lookup
        from src.config import settings

        self._vix_data_dir = (
            Path(vix_data_dir) if vix_data_dir is not None else Path(settings.vix_data_dir)
        )

    def _resolve_instrument_lookup(self) -> InstrumentLookup | None:
        """Lazily construct and cache the InstrumentLookup used for leg resolution.

        Non-fatal: on load failure, logs a WARNING and returns None so callers
        degrade to regex-only resolution (symbolic keys still work; real
        numeric keys will fail to resolve, same as before this fallback existed).
        """
        if self._instrument_lookup is None:
            try:
                self._instrument_lookup = InstrumentLookup.from_file(DEFAULT_BOD_PATH)
            except Exception as exc:
                log.warning("collar_overlay_v1.bod_lookup_load_failed", error=str(exc))
                return None
        return self._instrument_lookup

    async def check_signals(
        self,
        market: OptionChain,
        positions: list[PaperPosition],
    ) -> list[SignalEvent]:
        """Evaluate exit and warning signals for Collar option legs.

        Filters positions to matching strategy name and leg roles.
        """
        events: list[SignalEvent] = []
        today = market_today()

        short_call_pos = next(
            (
                p
                for p in positions
                if p.strategy_name == self.strategy_name
                and p.leg_role == SHORT_CALL_ROLE
                and p.net_qty < 0
            ),
            None,
        )
        long_put_pos = next(
            (
                p
                for p in positions
                if p.strategy_name == self.strategy_name
                and p.leg_role == LONG_PUT_ROLE
                and p.net_qty > 0
            ),
            None,
        )

        if not short_call_pos:
            return []

        leg_states: dict = {}
        leg_states["short_call"] = {
            "instrument_key": short_call_pos.instrument_key,
            "entry_price": str(short_call_pos.avg_sell_price),
            "qty": short_call_pos.net_qty,
        }
        if long_put_pos:
            leg_states["long_put"] = {
                "instrument_key": long_put_pos.instrument_key,
                "entry_price": str(long_put_pos.avg_cost),
                "qty": long_put_pos.net_qty,
            }

        # Evaluate Short Call only
        call_leg = self._find_call_leg(market, short_call_pos.instrument_key)
        expiry = self._parse_expiry(short_call_pos.instrument_key)
        dte = (expiry - today).days if expiry is not None else 9999
        if short_call_pos.entry_date is not None:
            days_held = (today - short_call_pos.entry_date).days
        else:
            log.warning(
                "collar_overlay_v1.check_signals.entry_date_missing",
                leg_role=short_call_pos.leg_role,
                instrument_key=short_call_pos.instrument_key,
            )
            days_held = 0

        entry_price = float(short_call_pos.avg_sell_price)
        current_mark = float(call_leg.ltp) if call_leg is not None else entry_price
        delta = (
            float(call_leg.delta) if (call_leg is not None and call_leg.delta is not None) else None
        )

        results = ExitSignalEngine.evaluate_cc(
            entry_price=entry_price,
            current_mark=current_mark,
            delta=delta,
            dte=dte,
            days_held=days_held,
        )

        for result in results:
            payload: dict = {
                "leg_role": short_call_pos.leg_role,
                "triggering_leg": "short_call",
                "leg_states": leg_states,
                "dte": dte,
            }
            if call_leg is not None:
                payload["delta"] = str(call_leg.delta)
                payload["mark"] = str(call_leg.ltp)
                payload["entry_credit"] = str(short_call_pos.avg_sell_price)
            if result.delta_stop_would_fire is not None:
                payload["delta_stop_would_fire"] = result.delta_stop_would_fire
            if result.premium_stop_would_fire is not None:
                payload["premium_stop_would_fire"] = result.premium_stop_would_fire
            if result.actual_rule_used is not None:
                payload["actual_rule_used"] = result.actual_rule_used

            if result.severity == "ACTION":
                payload["auto_execute"] = True
                payload["auto_action"] = "CLOSE_COLLAR"
                payload["triggering_signal"] = result.exit_signal
                payload["valid_actions"] = ["CLOSE_COLLAR"]

            events.append(
                SignalEvent(
                    event_type=result.exit_signal,
                    severity=result.severity,
                    description=result.notes or result.exit_signal,
                    payload=payload,
                )
            )

        # Evaluate Long Put — CRASH_MONETIZE only (Collar3b: net-new signal,
        # mirrors ExitSignalEngine.evaluate_pp's signal #1 exactly via the
        # shared evaluate_crash_monetize classmethod).
        if long_put_pos is not None:
            put_leg = self._find_put_leg(market, long_put_pos.instrument_key)
            put_entry_price = float(long_put_pos.avg_cost)
            put_current_mark = float(put_leg.ltp) if put_leg is not None else put_entry_price
            put_delta = (
                float(put_leg.delta) if (put_leg is not None and put_leg.delta is not None) else None
            )
            crash_results = ExitSignalEngine.evaluate_crash_monetize(
                entry_price=put_entry_price,
                current_mark=put_current_mark,
                delta=put_delta,
            )
            for result in crash_results:
                payload = {
                    "leg_role": long_put_pos.leg_role,
                    "triggering_leg": "long_put",
                    "leg_states": leg_states,
                }
                if put_leg is not None:
                    payload["delta"] = str(put_leg.delta)
                    payload["mark"] = str(put_leg.ltp)
                    payload["entry_debit"] = str(long_put_pos.avg_cost)

                payload["auto_execute"] = True
                payload["auto_action"] = "CLOSE_COLLAR"
                payload["triggering_signal"] = result.exit_signal
                payload["valid_actions"] = ["CLOSE_COLLAR"]

                events.append(
                    SignalEvent(
                        event_type=result.exit_signal,
                        severity=result.severity,
                        description=result.notes or result.exit_signal,
                        payload=payload,
                    )
                )

        events = self._select_combined_reentry_action(events)

        # Sort results: ACTION first, then WARN, then INFO
        severity_order = {"ACTION": 0, "WARN": 1, "INFO": 2}
        return sorted(events, key=lambda x: severity_order.get(x.severity, 3))

    def _select_combined_reentry_action(self, events: list[SignalEvent]) -> list[SignalEvent]:
        """Pick one ACTION event by Collar3b priority and mark it for the
        combined close+reenter action (``CLOSE_AND_REENTER_COLLAR``).

        Mirrors ``IronCondorV1._auto_select_action``'s priority-selection
        pattern: multiple ACTION-severity signals may fire on the same tick
        (e.g. DELTA_STOP on the call and CRASH_MONETIZE on the put); exactly
        one is promoted to drive auto-execute, per
        ``_REENTRY_ACTION_PRIORITY`` (highest first). All other events pass
        through unchanged (still visible for audit/Telegram context, but not
        auto-executed).
        """
        action_events = [e for e in events if e.severity == "ACTION"]
        if not action_events:
            return events

        types_present = {e.event_type for e in action_events}
        winner_type = next((t for t in _REENTRY_ACTION_PRIORITY if t in types_present), None)
        if winner_type is None:
            return events

        winner_emitted = False
        new_events: list[SignalEvent] = []
        for e in events:
            if e.severity == "ACTION" and e.event_type == winner_type and not winner_emitted:
                new_payload = {
                    **e.payload,
                    "auto_execute": True,
                    "auto_action": "CLOSE_AND_REENTER_COLLAR",
                    "triggering_signal": winner_type,
                    "valid_actions": ["CLOSE_AND_REENTER_COLLAR"],
                }
                new_events.append(
                    SignalEvent(
                        event_type=e.event_type,
                        severity=e.severity,
                        description=e.description,
                        payload=new_payload,
                    )
                )
                winner_emitted = True
            elif e.severity == "ACTION":
                # Non-winning ACTION event this tick — demote to informational,
                # never auto-executed alongside the winner.
                demoted_payload = {k: v for k, v in e.payload.items() if k != "auto_execute"}
                demoted_payload.pop("auto_action", None)
                new_events.append(
                    SignalEvent(
                        event_type=e.event_type,
                        severity=e.severity,
                        description=e.description,
                        payload=demoted_payload,
                    )
                )
            else:
                new_events.append(e)
        return new_events

    def describe_context(
        self,
        event: SignalEvent,
        market: OptionChain,
        positions: list[PaperPosition],
    ) -> str:
        """Structured context string for Collar positions."""
        collar_positions = [
            p
            for p in positions
            if p.strategy_name == self.strategy_name
            and p.leg_role in (SHORT_CALL_ROLE, LONG_PUT_ROLE)
        ]
        lines: list[str] = [
            f"Strategy: {self.strategy_name}",
            f"Signal: {event.event_type} ({event.severity})",
            f"Nifty spot: {market.underlying_spot}",
        ]

        for pos in collar_positions:
            expiry = self._parse_expiry(pos.instrument_key)
            dte = (expiry - market_today()).days if expiry is not None else None

            if pos.leg_role == SHORT_CALL_ROLE:
                call_leg = self._find_call_leg(market, pos.instrument_key)
                lines.append(f"Leg: {pos.leg_role} | key: {pos.instrument_key}")
                lines.append(f"  Entry credit : {pos.avg_sell_price}")
                if call_leg is not None:
                    lines.append(f"  Current mark : {call_leg.ltp}")
                    lines.append(f"  Delta        : {call_leg.delta}")
                else:
                    lines.append("  Current mark : unavailable")
            else:
                put_leg = self._find_put_leg(market, pos.instrument_key)
                lines.append(f"Leg: {pos.leg_role} | key: {pos.instrument_key}")
                lines.append(f"  Entry debit  : {pos.avg_cost}")
                if put_leg is not None:
                    lines.append(f"  Current mark : {put_leg.ltp}")
                    lines.append(f"  Delta        : {put_leg.delta}")
                else:
                    lines.append("  Current mark : unavailable")

            if dte is not None:
                lines.append(f"  DTE          : {dte}")

        if not collar_positions:
            lines.append("No open Collar positions found.")

        return "\n".join(lines)

    async def apply_action(
        self,
        positions: list[PaperPosition],
        action: ApprovedAction,
    ) -> list[PaperPosition]:
        """Apply approved action CLOSE_COLLAR or CLOSE_AND_REENTER_COLLAR.

        CLOSE_COLLAR: legacy — atomic two-leg close only (manual/Telegram
        approval path, or the ``_check_reentry`` audit-log-only re-entry
        eligibility check per PROFIT_TARGET/TIME_STOP/DTE_REVIEW/LOSS_STOP/
        DELTA_STOP).

        CLOSE_AND_REENTER_COLLAR (Collar3b): atomic close, then immediate
        reselection via ``select_and_build_collar_entry`` — no partial-close
        concept for Collar. ``_check_reentry`` still runs as a secondary
        audit-log entry (unchanged trigger set — TIME_STOP included there
        for logging parity only, never drives the combined action itself,
        since check_signals never emits TIME_STOP as an ACTION signal here).
        """
        if action.action_type not in ("CLOSE_COLLAR", "CLOSE_AND_REENTER_COLLAR"):
            raise ValueError(
                "CollarOverlayV1 only accepts CLOSE_COLLAR or CLOSE_AND_REENTER_COLLAR; "
                f"got {action.action_type!r}"
            )
        log.info(
            "collar_overlay_v1.apply_action",
            action_type=action.action_type,
        )

        short_call_pos, long_put_pos, updated = self._close_both_legs(positions, action)

        if short_call_pos is None and long_put_pos is None:
            log.warning(
                "collar_overlay_v1.apply_action.no_positions_found", strategy=self.strategy_name
            )
            return positions

        triggering_signal = action.metadata.get("triggering_signal") if action.metadata else None

        # Secondary audit-log-only re-entry eligibility check — unchanged trigger
        # set/behavior from Collar3a. Runs for both action types.
        if (
            triggering_signal
            in ("PROFIT_TARGET", "TIME_STOP", "DTE_REVIEW", "LOSS_STOP", "DELTA_STOP")
            and short_call_pos is not None
        ):
            expiry = self._parse_expiry(short_call_pos.instrument_key)
            await self._check_reentry(
                expiry=expiry,
                today=market_today(),
                instrument_key=short_call_pos.instrument_key,
                trade_id=0,
            )

        if action.action_type == "CLOSE_AND_REENTER_COLLAR":
            await self._reenter_collar(short_call_pos, triggering_signal or "UNKNOWN")

        await self._send_close_notification(short_call_pos, long_put_pos, action)
        return updated

    def _close_both_legs(
        self,
        positions: list[PaperPosition],
        action: ApprovedAction,
    ) -> tuple[PaperPosition | None, PaperPosition | None, list[PaperPosition]]:
        """Resolve the two Collar legs matched by ``action`` and write their
        closing trades atomically. Returns (short_call_pos, long_put_pos, updated_positions).
        """
        short_call_leg = next(
            (leg for leg in action.legs_to_close if leg.leg_role == SHORT_CALL_ROLE), None
        )
        long_put_leg = next(
            (leg for leg in action.legs_to_close if leg.leg_role == LONG_PUT_ROLE), None
        )

        short_call_pos = next(
            (
                p
                for p in positions
                if p.leg_role == SHORT_CALL_ROLE
                and p.net_qty < 0
                and (short_call_leg is None or _leg_close_matches(p, short_call_leg))
            ),
            None,
        )
        long_put_pos = next(
            (
                p
                for p in positions
                if p.leg_role == LONG_PUT_ROLE
                and p.net_qty > 0
                and (long_put_leg is None or _leg_close_matches(p, long_put_leg))
            ),
            None,
        )

        if not short_call_pos and not long_put_pos:
            return None, None, positions

        trades_to_record = []
        mark = action.metadata.get("mark") if action.metadata else None

        if short_call_pos is not None:
            trade = self._build_close_trade(short_call_pos, TradeAction.BUY, mark)
            if trade:
                trades_to_record.append(trade)

        if long_put_pos is not None:
            trade = self._build_close_trade(long_put_pos, TradeAction.SELL, None)
            if trade:
                trades_to_record.append(trade)
        else:
            log.warning("collar_overlay_v1.apply_action.missing_put_leg")

        if self._store is not None and trades_to_record:
            self._store.record_trades(trades_to_record)
            log.info(
                "collar_overlay_v1.apply_action.recorded_trades",
                strategy_name=self.strategy_name,
                count=len(trades_to_record),
            )

        closed_positions = [p for p in (short_call_pos, long_put_pos) if p is not None]
        updated = [p for p in positions if p not in closed_positions]
        return short_call_pos, long_put_pos, updated

    async def _reenter_collar(
        self,
        closed_short_call_pos: PaperPosition | None,
        triggering_signal: str,
    ) -> None:
        """Immediately reselect and open a fresh two-leg Collar pair (Collar3b).

        Failure handling (operator spec): reentry selection failure (no
        candidate clears the ladder, chain fetch fails, gate blocks) logs
        ERROR with full context, sends a Telegram message telling the
        operator to enter manually, and leaves the position flat — no
        auto-retry, no degraded fallback.
        """
        if self._broker is None or self._store is None:
            log.warning(
                "collar_overlay_v1.reenter_collar.skipped_no_broker_or_store",
                triggering_signal=triggering_signal,
            )
            return

        closing_dte: int | None = None
        if closed_short_call_pos is not None:
            expiry = self._parse_expiry(closed_short_call_pos.instrument_key)
            if expiry is not None:
                closing_dte = (expiry - market_today()).days

        try:
            new_trades = await select_and_build_collar_entry(
                self._broker,
                self._store,
                market_today(),
                triggering_signal,
                closing_dte=closing_dte,
            )
        except CollarEntrySelectionError as exc:
            log.error(
                "collar_overlay_v1.reenter_collar.selection_failed",
                error=str(exc),
                triggering_signal=triggering_signal,
                closing_dte=closing_dte,
            )
            await self._send_reentry_failure_notification(exc, triggering_signal)
            return
        except Exception as exc:  # noqa: BLE001 — never let an unexpected error crash the tick
            log.error(
                "collar_overlay_v1.reenter_collar.unexpected_failure",
                error=str(exc),
                triggering_signal=triggering_signal,
                closing_dte=closing_dte,
            )
            await self._send_reentry_failure_notification(exc, triggering_signal)
            return

        try:
            self._store.record_trades(new_trades)
            log.info(
                "collar_overlay_v1.reenter_collar.recorded",
                triggering_signal=triggering_signal,
                count=len(new_trades),
            )
        except Exception as exc:  # noqa: BLE001 — a failed write must never be swallowed silently
            log.error(
                "collar_overlay_v1.reenter_collar.record_failed",
                error=str(exc),
                triggering_signal=triggering_signal,
            )
            await self._send_reentry_failure_notification(exc, triggering_signal)

    async def _send_reentry_failure_notification(
        self, exc: Exception, triggering_signal: str
    ) -> None:
        """Non-fatal Telegram alert: reentry failed, operator must enter manually."""
        if self._notifier is None:
            return
        msg = (
            f"⚠️ <b>Collar: REENTRY FAILED ({triggering_signal})</b>\n"
            f"Position closed but automated reentry could not complete.\n"
            f"Reason: {exc}\n"
            f"Action required: enter the Collar manually."
        )
        try:
            if hasattr(self._notifier, "send_notification"):
                await self._notifier.send_notification(msg)
            elif hasattr(self._notifier, "send_plain_message"):
                await self._notifier.send_plain_message(msg)
            elif hasattr(self._notifier, "send"):
                await self._notifier.send(msg)
        except Exception as notify_exc:  # noqa: BLE001 — notify failure must never crash the tick
            log.error(
                "collar_overlay_v1.reentry_failure_notify_failed",
                error=str(notify_exc),
            )

    def _build_close_trade(
        self,
        pos: PaperPosition,
        close_action: TradeAction,
        mark: object | None,
    ) -> PaperTrade | None:
        """Construct a PaperTrade object for closing a leg."""
        try:
            price = Decimal(str(mark)) if mark is not None else Decimal("0")
        except Exception:
            price = Decimal("0")
        if price <= Decimal("0"):
            price = pos.avg_sell_price if close_action == TradeAction.BUY else pos.avg_cost
        if price <= Decimal("0"):
            log.warning(
                "collar_overlay_v1.build_close_trade.zero_price_skip",
                leg_role=pos.leg_role,
                instrument_key=pos.instrument_key,
            )
            return None
        return PaperTrade(
            strategy_name=pos.strategy_name,
            leg_role=pos.leg_role,
            instrument_key=pos.instrument_key,
            trade_date=market_today(),
            action=close_action,
            quantity=abs(pos.net_qty),
            price=price,
            notes="close via apply_action",
        )

    async def _send_close_notification(
        self,
        call_pos: PaperPosition | None,
        put_pos: PaperPosition | None,
        action: ApprovedAction,
    ) -> None:
        """Send HTML notification for closed Collar legs. Non-fatal."""
        if self._notifier is None:
            return

        try:
            metadata = action.metadata or {}
            triggering_signal = metadata.get("triggering_signal")

            call_key = call_pos.instrument_key if call_pos else "None"
            call_entry = call_pos.avg_sell_price if call_pos else Decimal("0")

            call_exit = (
                Decimal(str(metadata.get("mark")))
                if metadata.get("mark") is not None
                else call_entry
            )
            call_exit_str = (
                f"₹{call_exit:.2f}" if metadata.get("mark") is not None else f"~₹{call_entry:.2f}"
            )

            call_delta_val = metadata.get("delta")
            call_delta_str = (
                f"{Decimal(str(call_delta_val)):.3f}" if call_delta_val is not None else "N/A"
            )

            call_dte = 0
            call_dte_raw = metadata.get("dte")
            if call_dte_raw is not None:
                try:
                    call_dte = int(float(call_dte_raw))
                except (ValueError, TypeError):
                    pass
            elif call_pos:
                call_expiry = self._parse_expiry(call_pos.instrument_key)
                call_dte = (call_expiry - market_today()).days if call_expiry else 0

            put_key = put_pos.instrument_key if put_pos else "None"
            put_entry = put_pos.avg_cost if put_pos else Decimal("0")
            put_exit = put_entry
            put_exit_str = f"~₹{put_exit:.2f}" if put_pos else f"₹{put_exit:.2f}"

            call_pnl = (
                (call_entry - call_exit) * abs(call_pos.net_qty) if call_pos else Decimal("0")
            )
            put_pnl = (put_exit - put_entry) * abs(put_pos.net_qty) if put_pos else Decimal("0")
            net_pnl = call_pnl + put_pnl

            pnl_prefix = "~" if (call_pos is not None or put_pos is not None) else ""

            msg = (
                f"✅ <b>Collar: CLOSE ({triggering_signal or 'MANUAL'})</b>\n"
                f"📤 Short Call: {call_key} @ {call_exit_str}\n"
                f"   Entry ₹{call_entry:.2f} · Delta {call_delta_str} · DTE {call_dte}\n"
                f"📤 Long Put: {put_key} @ {put_exit_str}\n"
                f"   Entry ₹{put_entry:.2f}\n"
                f"Net P&amp;L: <b>{pnl_prefix}₹{net_pnl:+,.0f}</b>"
            )

            if hasattr(self._notifier, "send_notification"):
                await self._notifier.send_notification(msg)
            elif hasattr(self._notifier, "send_plain_message"):
                await self._notifier.send_plain_message(msg)
            else:
                log.warning(
                    "collar_overlay_v1.notifier_method_missing",
                    notifier_type=type(self._notifier).__name__,
                )
        except Exception as exc:
            log.error(
                "collar_overlay_v1.send_close_notification_failed",
                error=str(exc),
            )

    def _find_call_leg(self, market: OptionChain, instrument_key: str) -> OptionLeg | None:
        """Locate the CE leg in the chain.

        Delegates to the shared ``find_option_leg`` utility: tries a direct
        regex strike/type parse first (symbolic/test keys), then falls back
        to BOD JSON lookup for real numeric Upstox instrument keys that carry
        no strike/type in the key string itself.
        """
        return find_option_leg(instrument_key, market, lookup=self._resolve_instrument_lookup())

    def _find_put_leg(self, market: OptionChain, instrument_key: str) -> OptionLeg | None:
        """Locate the PE leg in the chain.

        Delegates to the shared ``find_option_leg`` utility: tries a direct
        regex strike/type parse first (symbolic/test keys), then falls back
        to BOD JSON lookup for real numeric Upstox instrument keys that carry
        no strike/type in the key string itself.
        """
        return find_option_leg(instrument_key, market, lookup=self._resolve_instrument_lookup())

    def _parse_expiry(self, instrument_key: str) -> date | None:
        """Extract option expiry date."""
        m = _EXPIRY_RE.search(instrument_key)
        if not m:
            return None
        try:
            return datetime.strptime(m.group(1).upper(), "%d%b%Y").date()
        except ValueError:
            return None

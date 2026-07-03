# src/strategy/collar_overlay_v1.py
"""CollarOverlayV1 — Collar overlay strategy class.

Implements PaperStrategy protocol for the paper_collar_v1 strategy.
Emits exit and warning signals for Collar short call and long put legs.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import structlog

from src.market_calendar.holidays import market_today
from src.models.options import OptionChain, OptionLeg
from src.models.portfolio import TradeAction
from src.paper.constants import STRATEGY_COLLAR_OVERLAY
from src.paper.models import PaperPosition, PaperTrade
from src.strategy.exit_signals import ExitSignalEngine
from src.strategy.protocol import ApprovedAction, SignalEvent
from src.strategy.reentry_mixin import ReEntryMixin

log = structlog.get_logger(__name__)

# Matches keys like "NSE_FO|NIFTY29MAY2026PE" → group 1 = "29MAY2026"
_EXPIRY_RE = re.compile(
    r"NSE_FO\|NIFTY(\d{2}[A-Za-z]{3}\d{4})(PE|CE)",
    re.IGNORECASE,
)

# Matches keys like "NSE_FO|NIFTY23000PE" → group 1 = "23000"
_STRIKE_RE = re.compile(r"NIFTY(\d+)(PE|CE)", re.IGNORECASE)

SHORT_CALL_ROLE = "overlay_collar_call"
LONG_PUT_ROLE = "overlay_collar_put"


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
    ) -> None:
        """Initialise CollarOverlayV1.

        Args:
            store: PaperStore instance for persisting closing trades. None → writes skipped.
            notifier: TelegramGateway for re-entry notifications. None → notifications skipped.
            vix_data_dir: Path to Parquet VIX data directory for IVR gating. None → settings default.
        """
        self._store = store
        self._notifier = notifier
        from src.config import settings

        self._vix_data_dir = (
            Path(vix_data_dir) if vix_data_dir is not None else Path(settings.vix_data_dir)
        )

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

        # Sort results: ACTION first, then WARN, then INFO
        severity_order = {"ACTION": 0, "WARN": 1, "INFO": 2}
        return sorted(events, key=lambda x: severity_order.get(x.severity, 3))

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
        """Apply approved action CLOSE_COLLAR."""
        if action.action_type != "CLOSE_COLLAR":
            raise ValueError(
                f"CollarOverlayV1 only accepts CLOSE_COLLAR; got {action.action_type!r}"
            )
        log.info(
            "collar_overlay_v1.apply_action",
            action_type=action.action_type,
        )

        short_call_pos = next(
            (p for p in positions if p.leg_role == SHORT_CALL_ROLE and p.net_qty < 0),
            None,
        )
        long_put_pos = next(
            (p for p in positions if p.leg_role == LONG_PUT_ROLE and p.net_qty > 0),
            None,
        )

        if not short_call_pos and not long_put_pos:
            log.warning(
                "collar_overlay_v1.apply_action.no_positions_found", strategy=self.strategy_name
            )
            return positions

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

        closed_roles = set()
        if short_call_pos:
            closed_roles.add(SHORT_CALL_ROLE)
        if long_put_pos:
            closed_roles.add(LONG_PUT_ROLE)

        updated = [p for p in positions if p.leg_role not in closed_roles]

        triggering_signal = action.metadata.get("triggering_signal") if action.metadata else None
        if triggering_signal in ("PROFIT_TARGET", "TIME_STOP") and short_call_pos is not None:
            expiry = self._parse_expiry(short_call_pos.instrument_key)
            await self._check_reentry(
                expiry=expiry,
                today=market_today(),
                instrument_key=short_call_pos.instrument_key,
                trade_id=0,
            )

        await self._send_close_notification(short_call_pos, long_put_pos, action)
        return updated

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
        """Locate the CE leg in the chain."""
        m = _STRIKE_RE.search(instrument_key)
        if m:
            try:
                strike = Decimal(m.group(1))
                strike_data = market.strikes.get(strike)
                if strike_data is not None and strike_data.ce is not None:
                    return strike_data.ce
            except InvalidOperation:
                log.warning(
                    "collar_overlay_v1.strike_parse_failed",
                    instrument_key=instrument_key,
                )

        for strike_data in market.strikes.values():
            if strike_data.ce is not None and strike_data.ce.ltp > Decimal("0"):
                return strike_data.ce

        return None

    def _find_put_leg(self, market: OptionChain, instrument_key: str) -> OptionLeg | None:
        """Locate the PE leg in the chain."""
        m = _STRIKE_RE.search(instrument_key)
        if m:
            try:
                strike = Decimal(m.group(1))
                strike_data = market.strikes.get(strike)
                if strike_data is not None and strike_data.pe is not None:
                    return strike_data.pe
            except InvalidOperation:
                log.warning(
                    "collar_overlay_v1.strike_parse_failed",
                    instrument_key=instrument_key,
                )

        for strike_data in market.strikes.values():
            if strike_data.pe is not None and strike_data.pe.ltp > Decimal("0"):
                return strike_data.pe

        return None

    def _parse_expiry(self, instrument_key: str) -> date | None:
        """Extract option expiry date."""
        m = _EXPIRY_RE.search(instrument_key)
        if not m:
            return None
        try:
            return datetime.strptime(m.group(1).upper(), "%d%b%Y").date()
        except ValueError:
            return None

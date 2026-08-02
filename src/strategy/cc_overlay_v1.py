# src/strategy/cc_overlay_v1.py
"""CCOverlayV1 — Covered Call overlay strategy class.

Implements PaperStrategy protocol for the paper_covered_call_v1 strategy.
Emits exit and warning signals for Standalone CC legs.
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
from src.paper.constants import STRATEGY_CC_OVERLAY
from src.paper.models import PaperPosition, PaperTrade
from src.strategy.exit_signals import ExitSignalEngine
from src.strategy.protocol import ApprovedAction, LegClose, SignalEvent
from src.strategy.reentry_mixin import ReEntryMixin

log = structlog.get_logger(__name__)


def _leg_close_matches(pos: PaperPosition, leg: LegClose) -> bool:
    """Return True when ``leg`` identifies ``pos`` as the position to close.

    Matches on ``leg_role`` always; additionally matches on ``instrument_key``
    when the ``LegClose`` supplies one, so that a roll overlap (two positions
    sharing a ``leg_role`` with different ``instrument_key``s) only removes
    the specific instrument being closed (PG-4c, mirrors PG-4b's
    ``csp_nifty_v1._leg_close_matches``).
    """
    if pos.leg_role != leg.leg_role:
        return False
    if leg.instrument_key is not None:
        return pos.instrument_key == leg.instrument_key
    return True


# Matches keys like "NSE_FO|NIFTY29MAY2026PE" → group 1 = "29MAY2026"
_EXPIRY_RE = re.compile(
    r"NSE_FO\|NIFTY(\d{2}[A-Za-z]{3}\d{4})(PE|CE)",
    re.IGNORECASE,
)

# Matches keys like "NSE_FO|NIFTY23000PE" → group 1 = "23000"
_STRIKE_RE = re.compile(r"NIFTY(\d+)(PE|CE)", re.IGNORECASE)

SHORT_CALL_ROLES = {"short_call", "cc_short_call", "covered_call"}


class CCOverlayV1(ReEntryMixin):
    """Covered Call overlay strategy implementation."""

    strategy_name: str = STRATEGY_CC_OVERLAY
    auto_execute: bool = True
    reentry_leg_role: str = "covered_call"
    reentry_script_hint: str = "run find_overlay_strikes.py --overlay-type cc"

    def __init__(
        self,
        store: Any = None,
        notifier: Any = None,
        vix_data_dir: Path | str | None = None,
    ) -> None:
        """Initialise CCOverlayV1."""
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
        """Evaluate exit and warning signals for Standalone CC short call legs.

        Filters positions to matching strategy name and leg roles.
        """
        events: list[SignalEvent] = []
        today = market_today()

        for pos in positions:
            if pos.strategy_name != self.strategy_name:
                continue
            if pos.leg_role not in SHORT_CALL_ROLES:
                continue
            if pos.net_qty >= 0:
                continue  # Only short positions trigger exit signals

            call_leg = self._find_call_leg(market, pos.instrument_key)
            expiry = self._parse_expiry(pos.instrument_key)
            dte = (expiry - today).days if expiry is not None else 9999

            delta = (
                float(call_leg.delta)
                if (call_leg is not None and call_leg.delta is not None)
                else None
            )
            entry_price = float(pos.avg_sell_price)
            current_mark = float(call_leg.ltp) if call_leg is not None else entry_price
            if pos.entry_date is not None:
                days_held = (today - pos.entry_date).days
            else:
                log.warning(
                    "cc_overlay_v1.check_signals.entry_date_missing",
                    leg_role=pos.leg_role,
                    instrument_key=pos.instrument_key,
                )
                days_held = 0

            results = ExitSignalEngine.evaluate_cc(
                entry_price=entry_price,
                current_mark=current_mark,
                delta=delta,
                dte=dte,
                days_held=days_held,
            )

            for result in results:
                payload: dict = {"leg_role": pos.leg_role}
                if call_leg is not None:
                    payload["delta"] = str(call_leg.delta)
                    payload["mark"] = str(call_leg.ltp)
                    payload["entry_credit"] = str(pos.avg_sell_price)
                if result.delta_stop_would_fire is not None:
                    payload["delta_stop_would_fire"] = result.delta_stop_would_fire
                if result.premium_stop_would_fire is not None:
                    payload["premium_stop_would_fire"] = result.premium_stop_would_fire
                if result.actual_rule_used is not None:
                    payload["actual_rule_used"] = result.actual_rule_used
                payload["dte"] = dte
                payload["valid_actions"] = ["CLOSE_CC"]

                if result.severity == "ACTION":
                    payload["auto_execute"] = True
                    payload["auto_action"] = "CLOSE_CC"
                    payload["triggering_signal"] = result.exit_signal

                events.append(
                    SignalEvent(
                        event_type=result.exit_signal,
                        severity=result.severity,
                        description=result.notes or result.exit_signal,
                        payload=payload,
                    )
                )

        return events

    def describe_context(
        self,
        event: SignalEvent,
        market: OptionChain,
        positions: list[PaperPosition],
    ) -> str:
        """Structured context string for CC positions."""
        cc_positions = [
            p
            for p in positions
            if p.strategy_name == self.strategy_name
            and p.leg_role in SHORT_CALL_ROLES
            and p.net_qty < 0
        ]
        lines: list[str] = [
            f"Strategy: {self.strategy_name}",
            f"Signal: {event.event_type} ({event.severity})",
            f"Nifty spot: {market.underlying_spot}",
        ]

        for pos in cc_positions:
            call_leg = self._find_call_leg(market, pos.instrument_key)
            expiry = self._parse_expiry(pos.instrument_key)
            dte = (expiry - market_today()).days if expiry is not None else None
            entry_credit = pos.avg_sell_price

            lines.append(f"Leg: {pos.leg_role} | key: {pos.instrument_key}")
            lines.append(f"  Entry credit : {entry_credit}")

            if call_leg is not None:
                mark = call_leg.ltp
                pct_remaining = (
                    (mark / entry_credit * 100).quantize(Decimal("0.1"))
                    if entry_credit > Decimal("0")
                    else Decimal("0")
                )
                lines.append(f"  Current mark : {mark} ({pct_remaining}% of credit)")
                lines.append(f"  Delta        : {call_leg.delta}")
                lines.append(f"  IV           : {call_leg.iv}")
            else:
                lines.append("  Current mark : unavailable (chain lookup failed)")

            if dte is not None:
                lines.append(f"  DTE          : {dte}")
            else:
                lines.append("  DTE          : unavailable")

        if not cc_positions:
            lines.append("No open CC positions found.")

        return "\n".join(lines)

    async def apply_action(
        self,
        positions: list[PaperPosition],
        action: ApprovedAction,
    ) -> list[PaperPosition]:
        """Apply approved action CLOSE_CC."""
        if action.action_type != "CLOSE_CC":
            raise ValueError(
                f"CCOverlayV1 only accepts CLOSE_CC actions; got {action.action_type!r}"
            )
        log.info(
            "cc_overlay_v1.apply_action",
            action_type=action.action_type,
            legs_to_close=[leg.leg_role for leg in action.legs_to_close],
        )

        closed_pos = next(
            (
                p
                for p in positions
                if any(_leg_close_matches(p, leg) for leg in action.legs_to_close) and p.net_qty < 0
            ),
            None,
        )
        updated = [
            p
            for p in positions
            if not any(_leg_close_matches(p, leg) for leg in action.legs_to_close)
        ]

        triggering_signal = action.metadata.get("triggering_signal") if action.metadata else None

        if (
            triggering_signal
            in ("PROFIT_TARGET", "TIME_STOP", "LOSS_STOP", "DELTA_STOP", "DTE_REVIEW")
            and closed_pos is not None
        ):
            expiry = self._parse_expiry(closed_pos.instrument_key)
            await self._check_reentry(
                expiry=expiry,
                today=market_today(),
                instrument_key=closed_pos.instrument_key,
                trade_id=0,
            )

        if closed_pos is not None:
            mark = action.metadata.get("mark") if action.metadata else None
            self._record_close_trade(closed_pos, mark)

        await self._send_close_notification(closed_pos, triggering_signal, action)
        return updated

    def _record_close_trade(
        self,
        pos: PaperPosition,
        mark: object | None,
    ) -> None:
        """Write a BUY closing trade to the ledger for a short-call position.

        Args:
            pos: The position being closed.
            mark: Current mark price from action metadata (Decimal, float, or str). None → fallback to avg_sell_price.
        """
        if self._store is None:
            return
        try:
            price = Decimal(str(mark)) if mark is not None else Decimal("0")
        except Exception:
            price = Decimal("0")
        if price <= Decimal("0"):
            price = pos.avg_sell_price
        if price <= Decimal("0"):
            log.warning(
                "cc_overlay_v1.record_close_trade.zero_price_skip",
                leg_role=pos.leg_role,
                instrument_key=pos.instrument_key,
            )
            return
        trade = PaperTrade(
            strategy_name=pos.strategy_name,
            leg_role=pos.leg_role,
            instrument_key=pos.instrument_key,
            trade_date=market_today(),
            action=TradeAction.BUY,
            quantity=abs(pos.net_qty),
            price=price,
            notes="close via apply_action",
        )
        inserted = self._store.record_trade(trade)
        log.info(
            "cc_overlay_v1.record_close_trade",
            leg_role=pos.leg_role,
            price=str(price),
            inserted=inserted,
        )

    async def _send_close_notification(
        self,
        pos: PaperPosition | None,
        signal: str | None,
        action: ApprovedAction,
    ) -> None:
        """Send HTML notification for closed CC leg. Non-fatal."""
        if pos is None or self._notifier is None:
            return

        try:
            metadata = action.metadata or {}
            exit_price = (
                Decimal(str(metadata.get("mark")))
                if metadata.get("mark") is not None
                else pos.avg_sell_price
            )
            delta_raw = metadata.get("delta")
            delta = float(delta_raw) if delta_raw is not None else 0.0

            expiry = self._parse_expiry(pos.instrument_key)
            dte = (expiry - market_today()).days if expiry is not None else 0
            dte_raw = metadata.get("dte")
            if dte_raw is not None:
                try:
                    dte = int(dte_raw)
                except (ValueError, TypeError):
                    pass

            entry_credit = pos.avg_sell_price
            signal_name = signal or "UNKNOWN"

            msg = (
                f"✅ <b>CC: CLOSE ({signal_name})</b>\n"
                f"📤 Closed: {pos.instrument_key} @ ₹{exit_price:.2f}\n"
                f"   Entry ₹{entry_credit:.2f} · Delta {delta:.3f} · DTE {dte}"
            )
            if hasattr(self._notifier, "send_notification"):
                await self._notifier.send_notification(msg)
            else:
                await self._notifier.send_plain_message(msg)
        except Exception as exc:
            log.error(
                "cc_overlay_v1.send_close_notification_failed",
                error=str(exc),
            )

    def _find_call_leg(self, market: OptionChain, instrument_key: str) -> OptionLeg | None:
        """Locate the CE leg in the chain for the position."""
        m = _STRIKE_RE.search(instrument_key)
        if m:
            try:
                strike = Decimal(m.group(1))
                strike_data = market.strikes.get(strike)
                if strike_data is not None and strike_data.ce is not None:
                    return strike_data.ce
            except InvalidOperation:
                log.warning(
                    "cc_overlay_v1.strike_parse_failed",
                    instrument_key=instrument_key,
                )

        for strike_data in market.strikes.values():
            if strike_data.ce is not None and strike_data.ce.ltp > Decimal("0"):
                log.debug(
                    "cc_overlay_v1.call_leg_fallback_used",
                    instrument_key=instrument_key,
                    fallback_strike=str(strike_data.ce.strike),
                )
                return strike_data.ce

        return None

    def _parse_expiry(self, instrument_key: str) -> date | None:
        """Extract the option expiry date from instrument key."""
        m = _EXPIRY_RE.search(instrument_key)
        if not m:
            return None
        try:
            return datetime.strptime(m.group(1).upper(), "%d%b%Y").date()
        except ValueError:
            return None

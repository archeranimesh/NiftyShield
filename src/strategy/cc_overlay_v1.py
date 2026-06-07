# src/strategy/cc_overlay_v1.py
"""CCOverlayV1 — Covered Call overlay strategy class.

Implements PaperStrategy protocol for the paper_covered_call_v1 strategy.
Emits exit and warning signals for Standalone CC legs.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

import structlog

from src.models.options import OptionChain, OptionLeg
from src.paper.constants import STRATEGY_CC_OVERLAY
from src.paper.models import PaperPosition
from src.strategy.exit_signals import ExitSignalEngine
from src.strategy.protocol import ApprovedAction, SignalEvent

log = structlog.get_logger(__name__)

# Matches keys like "NSE_FO|NIFTY29MAY2026PE" → group 1 = "29MAY2026"
_EXPIRY_RE = re.compile(
    r"NSE_FO\|NIFTY(\d{2}[A-Za-z]{3}\d{4})(PE|CE)",
    re.IGNORECASE,
)

# Matches keys like "NSE_FO|NIFTY23000PE" → group 1 = "23000"
_STRIKE_RE = re.compile(r"NIFTY(\d+)(PE|CE)", re.IGNORECASE)

SHORT_CALL_ROLES = {"short_call", "cc_short_call"}


class CCOverlayV1:
    """Covered Call overlay strategy implementation."""

    strategy_name: str = STRATEGY_CC_OVERLAY

    async def check_signals(
        self,
        market: OptionChain,
        positions: list[PaperPosition],
    ) -> list[SignalEvent]:
        """Evaluate exit and warning signals for Standalone CC short call legs.

        Filters positions to matching strategy name and leg roles.
        """
        events: list[SignalEvent] = []
        today = date.today()

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

            delta = float(call_leg.delta) if call_leg is not None else None
            entry_price = float(pos.avg_sell_price)
            current_mark = float(call_leg.ltp) if call_leg is not None else entry_price
            days_held = (today - pos.entry_date).days if pos.entry_date is not None else 0

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
            dte = (expiry - date.today()).days if expiry is not None else None
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
        closed = set(action.legs_to_close)
        log.info(
            "cc_overlay_v1.apply_action",
            action_type=action.action_type,
            legs_to_close=list(closed),
        )
        return [p for p in positions if p.leg_role not in closed]

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

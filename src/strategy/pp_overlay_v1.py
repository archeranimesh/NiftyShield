# src/strategy/pp_overlay_v1.py
"""PPOverlayV1 — Protective Put overlay strategy class.

Implements PaperStrategy protocol for the paper_protective_put_v1 strategy.
Emits exit and warning signals for Standalone PP legs.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

import structlog

from src.models.options import OptionChain, OptionLeg
from src.paper.constants import STRATEGY_PP_OVERLAY
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

LONG_PUT_ROLES = {"long_put", "pp_long_put", "protective_put"}


class PPOverlayV1:
    """Protective Put overlay strategy implementation."""

    strategy_name: str = STRATEGY_PP_OVERLAY

    async def check_signals(
        self,
        market: OptionChain,
        positions: list[PaperPosition],
    ) -> list[SignalEvent]:
        """Evaluate exit and warning signals for Standalone PP long put legs.

        Filters positions to matching strategy name and leg roles.
        """
        events: list[SignalEvent] = []
        today = date.today()

        for pos in positions:
            if pos.strategy_name != self.strategy_name:
                continue
            if pos.leg_role not in LONG_PUT_ROLES:
                continue
            if pos.net_qty <= 0:
                continue  # Only long positions trigger protective put signals

            put_leg = self._find_put_leg(market, pos.instrument_key)
            expiry = self._parse_expiry(pos.instrument_key)
            dte = (expiry - today).days if expiry is not None else 9999

            delta = float(put_leg.delta) if put_leg is not None else None

            entry_price = float(pos.avg_cost)
            current_mark = float(put_leg.ltp) if put_leg is not None else entry_price

            results = ExitSignalEngine.evaluate_pp(
                entry_price=entry_price,
                current_mark=current_mark,
                delta=delta,
                dte=dte,
            )

            for result in results:
                payload: dict = {"leg_role": pos.leg_role}
                if put_leg is not None:
                    payload["delta"] = str(put_leg.delta)
                    payload["mark"] = str(put_leg.ltp)
                    payload["entry_debit"] = str(pos.avg_cost)
                payload["dte"] = dte

                if result.exit_signal == "CRASH_MONETIZE":
                    payload["valid_actions"] = ["MONETIZE_PP"]
                elif result.exit_signal == "ROLL_ELIGIBLE":
                    payload["valid_actions"] = ["ROLL_PP"]

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
        """Structured context string for PP positions."""
        pp_positions = [
            p
            for p in positions
            if p.strategy_name == self.strategy_name
            and p.leg_role in LONG_PUT_ROLES
            and p.net_qty > 0
        ]
        lines: list[str] = [
            f"Strategy: {self.strategy_name}",
            f"Signal: {event.event_type} ({event.severity})",
            f"Nifty spot: {market.underlying_spot}",
        ]

        for pos in pp_positions:
            put_leg = self._find_put_leg(market, pos.instrument_key)
            expiry = self._parse_expiry(pos.instrument_key)
            dte = (expiry - date.today()).days if expiry is not None else None
            entry_debit = pos.avg_cost

            lines.append(f"Leg: {pos.leg_role} | key: {pos.instrument_key}")
            lines.append(f"  Entry debit  : {entry_debit}")

            if put_leg is not None:
                mark = put_leg.ltp
                pct_change = (
                    (mark / entry_debit * 100).quantize(Decimal("0.1"))
                    if entry_debit > Decimal("0")
                    else Decimal("0")
                )
                lines.append(f"  Current mark : {mark} ({pct_change}% of entry)")
                lines.append(f"  Delta        : {put_leg.delta}")
                lines.append(f"  IV           : {put_leg.iv}")
            else:
                lines.append("  Current mark : unavailable (chain lookup failed)")

            if dte is not None:
                lines.append(f"  DTE          : {dte}")
            else:
                lines.append("  DTE          : unavailable")

        if not pp_positions:
            lines.append("No open PP positions found.")

        return "\n".join(lines)

    async def apply_action(
        self,
        positions: list[PaperPosition],
        action: ApprovedAction,
    ) -> list[PaperPosition]:
        """Apply approved action MONETIZE_PP or ROLL_PP."""
        if action.action_type not in {"MONETIZE_PP", "ROLL_PP"}:
            raise ValueError(
                f"PPOverlayV1 only accepts MONETIZE_PP and ROLL_PP actions; got {action.action_type!r}"
            )
        closed = set(action.legs_to_close)
        log.info(
            "pp_overlay_v1.apply_action",
            action_type=action.action_type,
            legs_to_close=list(closed),
        )
        return [p for p in positions if p.leg_role not in closed]

    def _find_put_leg(self, market: OptionChain, instrument_key: str) -> OptionLeg | None:
        """Locate the PE leg in the chain for the position."""
        m = _STRIKE_RE.search(instrument_key)
        if m:
            try:
                strike = Decimal(m.group(1))
                strike_data = market.strikes.get(strike)
                if strike_data is not None and strike_data.pe is not None:
                    return strike_data.pe
            except InvalidOperation:
                log.warning(
                    "pp_overlay_v1.strike_parse_failed",
                    instrument_key=instrument_key,
                )

        for strike_data in market.strikes.values():
            if strike_data.pe is not None and strike_data.pe.ltp > Decimal("0"):
                log.debug(
                    "pp_overlay_v1.put_leg_fallback_used",
                    instrument_key=instrument_key,
                    fallback_strike=str(strike_data.pe.strike),
                )
                return strike_data.pe

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

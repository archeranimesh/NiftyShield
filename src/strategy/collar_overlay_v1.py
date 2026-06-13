# src/strategy/collar_overlay_v1.py
"""CollarOverlayV1 — Collar overlay strategy class.

Implements PaperStrategy protocol for the paper_collar_v1 strategy.
Emits exit and warning signals for Collar short call and long put legs.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

import structlog

from src.models.options import OptionChain, OptionLeg
from src.models.portfolio import TradeAction
from src.paper.constants import STRATEGY_COLLAR_OVERLAY
from src.paper.models import PaperPosition, PaperTrade
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

SHORT_CALL_ROLE = "collar_short_call"
LONG_PUT_ROLE = "collar_long_put"


class CollarOverlayV1:
    """Collar overlay strategy implementation."""

    strategy_name: str = STRATEGY_COLLAR_OVERLAY

    def __init__(self, store: Any = None) -> None:
        """Initialise CollarOverlayV1.

        Args:
            store: PaperStore instance for persisting closing trades. None → writes skipped.
        """
        self._store = store

    async def check_signals(
        self,
        market: OptionChain,
        positions: list[PaperPosition],
    ) -> list[SignalEvent]:
        """Evaluate exit and warning signals for Collar option legs.

        Filters positions to matching strategy name and leg roles.
        """
        events: list[SignalEvent] = []
        today = date.today()

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

        if not short_call_pos and not long_put_pos:
            return []

        # Construct common leg state payload info
        leg_states: dict = {}
        if short_call_pos:
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

        # 1. Evaluate Short Call
        if short_call_pos:
            call_leg = self._find_call_leg(market, short_call_pos.instrument_key)
            expiry = self._parse_expiry(short_call_pos.instrument_key)
            dte = (expiry - today).days if expiry is not None else 9999

            strike_price = 0.0
            if call_leg is not None:
                strike_price = float(call_leg.strike)
            else:
                m = _STRIKE_RE.search(short_call_pos.instrument_key)
                if m:
                    try:
                        strike_price = float(m.group(1))
                    except ValueError:
                        pass

            delta = float(call_leg.delta) if call_leg is not None else None
            entry_price = float(short_call_pos.avg_sell_price)
            current_mark = float(call_leg.ltp) if call_leg is not None else entry_price

            results = ExitSignalEngine.evaluate_collar_call(
                entry_price=entry_price,
                current_mark=current_mark,
                delta=delta,
                dte=dte,
                underlying_price=float(market.underlying_spot),
                strike_price=strike_price,
            )

            for result in results:
                payload: dict = {
                    "leg_role": short_call_pos.leg_role,
                    "triggering_leg": "short_call",
                    "leg_states": leg_states,
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
                payload["dte"] = dte
                payload["valid_actions"] = ["CLOSE_CALL_ONLY", "CLOSE_ALL_OVERLAY"]

                events.append(
                    SignalEvent(
                        event_type=result.exit_signal,
                        severity=result.severity,
                        description=result.notes or result.exit_signal,
                        payload=payload,
                    )
                )

        # 2. Evaluate Long Put
        if long_put_pos:
            put_leg = self._find_put_leg(market, long_put_pos.instrument_key)
            expiry = self._parse_expiry(long_put_pos.instrument_key)
            dte = (expiry - today).days if expiry is not None else 9999

            bid = float(put_leg.bid) if put_leg is not None else None
            ask = float(put_leg.ask) if put_leg is not None else None
            delta = float(put_leg.delta) if put_leg is not None else None

            entry_price = float(long_put_pos.avg_cost)
            current_mark = float(put_leg.ltp) if put_leg is not None else entry_price

            results = ExitSignalEngine.evaluate_collar_put(
                entry_price=entry_price,
                current_mark=current_mark,
                delta=delta,
                dte=dte,
                bid=bid,
                ask=ask,
            )

            for result in results:
                payload = {
                    "leg_role": long_put_pos.leg_role,
                    "triggering_leg": "long_put",
                    "leg_states": leg_states,
                    "dte": dte,
                }
                if put_leg is not None:
                    payload["delta"] = str(put_leg.delta)
                    payload["mark"] = str(put_leg.ltp)
                    payload["entry_debit"] = str(long_put_pos.avg_cost)
                    payload["bid"] = str(put_leg.bid)
                    payload["ask"] = str(put_leg.ask)
                payload["valid_actions"] = ["MONETIZE_PUT", "CLOSE_ALL_OVERLAY"]

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
            dte = (expiry - date.today()).days if expiry is not None else None

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
        """Apply approved actions: CLOSE_CALL_ONLY, MONETIZE_PUT, CLOSE_ALL_OVERLAY."""
        allowed = {"CLOSE_CALL_ONLY", "MONETIZE_PUT", "CLOSE_ALL_OVERLAY"}
        if action.action_type not in allowed:
            raise ValueError(
                f"CollarOverlayV1 only accepts actions {allowed}; got {action.action_type!r}"
            )
        closed = set(action.legs_to_close)
        log.info(
            "collar_overlay_v1.apply_action",
            action_type=action.action_type,
            legs_to_close=list(closed),
        )
        mark = action.metadata.get("mark") if action.metadata else None

        # Persist closing trades before filtering from in-memory list.
        short_call_pos = next(
            (p for p in positions if p.leg_role == SHORT_CALL_ROLE and p.net_qty < 0),
            None,
        )
        long_put_pos = next(
            (p for p in positions if p.leg_role == LONG_PUT_ROLE and p.net_qty > 0),
            None,
        )
        if (
            action.action_type in ("CLOSE_CALL_ONLY", "CLOSE_ALL_OVERLAY")
            and short_call_pos is not None
            and SHORT_CALL_ROLE in closed
        ):
            self._record_close_trade(short_call_pos, TradeAction.BUY, mark)
        if (
            action.action_type in ("MONETIZE_PUT", "CLOSE_ALL_OVERLAY")
            and long_put_pos is not None
            and LONG_PUT_ROLE in closed
        ):
            self._record_close_trade(long_put_pos, TradeAction.SELL, mark)

        return [p for p in positions if p.leg_role not in closed]

    def _record_close_trade(
        self,
        pos: PaperPosition,
        close_action: TradeAction,
        mark: object | None,
    ) -> None:
        """Persist a closing trade for a collar leg.

        Args:
            pos: Position being closed.
            close_action: BUY (short call) or SELL (long put).
            mark: Mark price from metadata; None → fallback to position avg price.
        """
        if self._store is None:
            return
        try:
            price = Decimal(str(mark)) if mark is not None else Decimal("0")
        except Exception:
            price = Decimal("0")
        if price <= Decimal("0"):
            price = pos.avg_sell_price if close_action == TradeAction.BUY else pos.avg_cost
        if price <= Decimal("0"):
            log.warning(
                "collar_overlay_v1.record_close_trade.zero_price_skip",
                leg_role=pos.leg_role,
                instrument_key=pos.instrument_key,
            )
            return
        trade = PaperTrade(
            strategy_name=pos.strategy_name,
            leg_role=pos.leg_role,
            instrument_key=pos.instrument_key,
            trade_date=date.today(),
            action=close_action,
            quantity=abs(pos.net_qty),
            price=price,
            notes="close via apply_action",
        )
        inserted = self._store.record_trade(trade)
        log.info(
            "collar_overlay_v1.record_close_trade",
            leg_role=pos.leg_role,
            close_action=close_action.value,
            price=str(price),
            inserted=inserted,
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

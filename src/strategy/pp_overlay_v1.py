# src/strategy/pp_overlay_v1.py
"""PPOverlayV1 — Protective Put overlay strategy class.

Implements PaperStrategy protocol for the paper_protective_put_v1 strategy.
Emits exit and warning signals for Standalone PP legs.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import structlog

from src.models.options import OptionChain, OptionLeg
from src.models.portfolio import TradeAction
from src.paper.constants import STRATEGY_PP_OVERLAY
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

LONG_PUT_ROLES = {"long_put", "pp_long_put", "protective_put"}


class PPOverlayV1(ReEntryMixin):
    """Protective Put overlay strategy implementation."""

    strategy_name: str = STRATEGY_PP_OVERLAY
    auto_execute: bool = True
    reentry_leg_role: str = "protective_put"
    reentry_script_hint: str = "run find_overlay_strikes.py --overlay-type pp"
    reentry_ivr_threshold: float = 0.60

    def __init__(
        self,
        store: Any = None,
        notifier: Any = None,
        vix_data_dir: Path | str | None = None,
    ) -> None:
        """Initialise PPOverlayV1."""
        self._store = store
        self._notifier = notifier
        from src.config import settings

        self._vix_data_dir = (
            Path(vix_data_dir) if vix_data_dir is not None else Path(settings.vix_data_dir)
        )

    def _ivr_passes(self, ivr: float) -> tuple[bool, str]:
        """Verify if the IVR passes the strategy criteria.

        Overridden for PP (long premium): blocks when IVR is too high (above threshold)
        to avoid buying protection when volatility is already elevated.
        """
        if ivr > self.reentry_ivr_threshold:
            return False, f"IVR={ivr:.2f} > {self.reentry_ivr_threshold:.2f} — high vol, skip cycle"
        return True, ""

    def _reentry_position_active(self, p: PaperPosition) -> bool:
        # Checks against the set LONG_PUT_ROLES to be robust to role variations
        return p.leg_role in LONG_PUT_ROLES and p.net_qty > 0

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

                if result.severity == "ACTION":
                    payload["auto_execute"] = True
                    payload["auto_action"] = (
                        "MONETIZE_PP" if result.exit_signal == "CRASH_MONETIZE" else "ROLL_PP"
                    )
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

        closed_pos = next(
            (p for p in positions if p.leg_role in closed and p.net_qty > 0),
            None,
        )
        updated = [p for p in positions if p.leg_role not in closed]

        if action.action_type == "MONETIZE_PP" and closed_pos is not None:
            expiry = self._parse_expiry(closed_pos.instrument_key)
            await self._check_reentry(
                expiry=expiry,
                today=date.today(),
                instrument_key=closed_pos.instrument_key,
                trade_id=0,  # Design choice: overlay positions are aggregated and lack unique trade IDs
            )

        if closed_pos is not None:
            mark = action.metadata.get("mark") if action.metadata else None
            self._record_close_trade(closed_pos, mark)

        await self._send_close_notification(closed_pos, action)
        return updated

    def _record_close_trade(
        self,
        pos: PaperPosition,
        mark: object | None,
    ) -> None:
        """Write a SELL closing trade to the ledger for a long-put position.

        Args:
            pos: The position being closed.
            mark: Current mark price from action metadata. None → fallback to avg_cost.
        """
        if self._store is None:
            return
        try:
            price = Decimal(str(mark)) if mark is not None else Decimal("0")
        except Exception:
            price = Decimal("0")
        if price <= Decimal("0"):
            price = pos.avg_cost
        if price <= Decimal("0"):
            log.warning(
                "pp_overlay_v1.record_close_trade.zero_price_skip",
                leg_role=pos.leg_role,
                instrument_key=pos.instrument_key,
            )
            return
        trade = PaperTrade(
            strategy_name=pos.strategy_name,
            leg_role=pos.leg_role,
            instrument_key=pos.instrument_key,
            trade_date=date.today(),
            action=TradeAction.SELL,
            quantity=abs(pos.net_qty),
            price=price,
            notes="close via apply_action",
        )
        inserted = self._store.record_trade(trade)
        log.info(
            "pp_overlay_v1.record_close_trade",
            leg_role=pos.leg_role,
            price=str(price),
            inserted=inserted,
        )

    async def _send_close_notification(
        self,
        pos: PaperPosition | None,
        action: ApprovedAction,
    ) -> None:
        """Send HTML notification for closed PP leg. Non-fatal."""
        if pos is None or self._notifier is None:
            return

        try:
            metadata = action.metadata or {}
            exit_price = (
                Decimal(str(metadata.get("mark")))
                if metadata.get("mark") is not None
                else pos.avg_cost
            )
            delta = float(metadata.get("delta")) if metadata.get("delta") is not None else 0.0

            expiry = self._parse_expiry(pos.instrument_key)
            dte = (expiry - date.today()).days if expiry is not None else 0
            if metadata.get("dte") is not None:
                try:
                    dte = int(float(metadata.get("dte")))
                except (ValueError, TypeError):
                    pass

            entry_debit = pos.avg_cost
            emoji = "🔄" if action.action_type == "ROLL_PP" else "💰"
            action_name = action.action_type

            msg = (
                f"{emoji} <b>PP: {action_name}</b>\n"
                f"📤 Closed: {pos.instrument_key} @ ₹{exit_price:.2f}\n"
                f"   Entry ₹{entry_debit:.2f} · Delta {delta:.3f} · DTE {dte}"
            )
            if self._notifier is not None:
                if hasattr(self._notifier, "send_notification"):
                    await self._notifier.send_notification(msg)
                elif hasattr(self._notifier, "send_plain_message"):
                    await self._notifier.send_plain_message(msg)
                else:
                    log.warning(
                        "pp_overlay_v1.notifier_method_missing",
                        notifier_type=type(self._notifier).__name__,
                    )
        except Exception as exc:
            log.error(
                "pp_overlay_v1.send_close_notification_failed",
                error=str(exc),
            )

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

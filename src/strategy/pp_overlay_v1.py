# src/strategy/pp_overlay_v1.py
"""PPOverlayV1 — Protective Put overlay strategy class.

Implements PaperStrategy protocol for the paper_protective_put_v1 strategy.
Emits exit and warning signals for Standalone PP legs.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import structlog

from src.instruments.lookup import InstrumentLookup, format_leg_label
from src.market_calendar.holidays import market_today
from src.models.options import OptionChain, OptionLeg
from src.models.portfolio import TradeAction
from src.notifications.formatting import format_greek, format_money
from src.notifications.markdown import escape_markdown, mdcode
from src.paper.constants import DEFAULT_BOD_PATH, STRATEGY_OVERLAY
from src.paper.models import PaperPosition, PaperTrade
from src.strategy._price_utils import find_option_leg, resolve_option_expiry
from src.strategy.exit_signals import ExitSignalEngine
from src.strategy.protocol import ApprovedAction, LegClose, SignalEvent
from src.strategy.reentry_mixin import ReEntryMixin

log = structlog.get_logger(__name__)


def _leg_close_matches(pos: PaperPosition, leg: LegClose) -> bool:
    """Return True when ``leg`` identifies ``pos`` as the position to close.

    Matches on ``leg_role`` always; additionally matches on ``instrument_key``
    when the ``LegClose`` supplies one, so that a roll overlap (two positions
    sharing a ``leg_role`` with different ``instrument_key``s) only removes
    the specific instrument being closed (PG-4d, mirrors PG-4b's
    ``csp_nifty_v1._leg_close_matches`` / PG-4c's ``cc_overlay_v1._leg_close_matches``).
    """
    if pos.leg_role != leg.leg_role:
        return False
    if leg.instrument_key is not None:
        return pos.instrument_key == leg.instrument_key
    return True


LONG_PUT_ROLES = {"overlay_pp"}


class PPOverlayV1(ReEntryMixin):
    """Protective Put overlay strategy implementation."""

    strategy_name: str = STRATEGY_OVERLAY
    auto_execute: bool = True
    reentry_leg_role: str = "protective_put"
    reentry_script_hint: str = "run find_overlay_strikes.py --overlay-type pp"
    reentry_ivr_threshold: float = 0.60

    def __init__(
        self,
        store: Any = None,
        notifier: Any = None,
        vix_data_dir: Path | str | None = None,
        instrument_lookup: InstrumentLookup | None = None,
    ) -> None:
        """Initialise PPOverlayV1.

        Args:
            store: PaperStore instance for persisting closing trades.
            notifier: TelegramGateway for re-entry notifications.
            vix_data_dir: Path to Parquet VIX data directory for IVR gating.
            instrument_lookup: Optional pre-built ``InstrumentLookup`` (BOD JSON),
                used by ``find_option_leg`` to resolve real numeric Upstox
                instrument keys that carry no strike/type in the key string
                itself. If not injected, lazily built from ``DEFAULT_BOD_PATH``
                on first use (same pattern as ``PaperStore._resolve_instrument_lookup``).
        """
        self._store = store
        self._notifier = notifier
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
                log.warning("pp_overlay_v1.bod_lookup_load_failed", error=str(exc))
                return None
        return self._instrument_lookup

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
        today = market_today()

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

            delta = (
                float(put_leg.delta)
                if (put_leg is not None and put_leg.delta is not None)
                else None
            )

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
            dte = (expiry - market_today()).days if expiry is not None else None
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
        log.info(
            "pp_overlay_v1.apply_action",
            action_type=action.action_type,
            legs_to_close=[leg.leg_role for leg in action.legs_to_close],
        )

        closed_pos = next(
            (
                p
                for p in positions
                if any(_leg_close_matches(p, leg) for leg in action.legs_to_close) and p.net_qty > 0
            ),
            None,
        )
        updated = [
            p
            for p in positions
            if not any(_leg_close_matches(p, leg) for leg in action.legs_to_close)
        ]

        # ROLL_PP deliberately does NOT call _check_reentry (PP3, investigated
        # 2026-08-03, confirmed correct-as-is — not the CC3 gap class). The
        # mixin's DTE gate (>= 14) would be evaluated against closed_pos's
        # expiry, which by construction has <= 5 DTE remaining whenever
        # ROLL_ELIGIBLE fires — it would report BLOCKED on every routine roll,
        # a spam notification with zero information content. ROLL_PP is
        # contract continuation, not a full exit to a fresh cycle (unlike
        # MONETIZE_PP, a real crash-triggered exit that may sit flat for
        # months). The actual reopen for ROLL_PP is handled by
        # paper_3track_overlay_entry.py's auto_pp_bootstrap() (--auto-pp),
        # gated on DTE <= 5 to match evaluate_pp's own ROLL_ELIGIBLE threshold
        # — see docs/plan/3track-consolidation/stories.md PP3.
        if action.action_type == "MONETIZE_PP" and closed_pos is not None:
            expiry = self._parse_expiry(closed_pos.instrument_key)
            await self._check_reentry(
                expiry=expiry,
                today=market_today(),
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
            trade_date=market_today(),
            action=TradeAction.SELL,
            quantity=abs(pos.net_qty),
            price=price,
            notes="close via apply_action",
        )
        inserted = self._store.record_trade(trade)
        if inserted:
            self._store.mark_trade_closed(pos.strategy_name, pos.leg_role, pos.instrument_key)
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
        """Send MarkdownV2 notification for closed PP leg. Non-fatal."""
        if pos is None or self._notifier is None:
            return

        try:
            metadata = action.metadata or {}
            exit_price = (
                Decimal(str(metadata.get("mark")))
                if metadata.get("mark") is not None
                else pos.avg_cost
            )
            delta_raw = metadata.get("delta")
            delta = float(delta_raw) if delta_raw is not None else None

            expiry = self._parse_expiry(pos.instrument_key)
            dte = (expiry - market_today()).days if expiry is not None else 0
            dte_raw = metadata.get("dte")
            if dte_raw is not None:
                try:
                    dte = int(float(dte_raw))
                except (ValueError, TypeError):
                    pass

            entry_debit = pos.avg_cost
            emoji = "🔄" if action.action_type == "ROLL_PP" else "💰"
            action_name = action.action_type

            lookup = self._resolve_instrument_lookup()
            label = format_leg_label(pos.instrument_key, lookup) if lookup else pos.instrument_key

            exit_price_str = escape_markdown(format_money(exit_price))
            entry_debit_str = escape_markdown(format_money(entry_debit))
            delta_str = escape_markdown(format_greek(delta))
            dte_str = escape_markdown(str(dte))

            msg = (
                f"{emoji} *PP: {escape_markdown(action_name)}*\n"
                f"📤 Closed: {mdcode(label)} @ {exit_price_str}\n"
                f"   Entry {entry_debit_str} · Delta {delta_str} "
                f"· DTE {dte_str}"
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
        """Locate the PE leg in the chain for the position.

        Delegates to the shared ``find_option_leg`` utility: tries a direct
        regex strike/type parse first (symbolic/test keys), then falls back
        to BOD JSON lookup for real numeric Upstox instrument keys that carry
        no strike/type in the key string itself.
        """
        return find_option_leg(instrument_key, market, lookup=self._resolve_instrument_lookup())

    def _parse_expiry(self, instrument_key: str) -> date | None:
        """Extract the option expiry date from instrument key.

        Regex-first with BOD-fallback for real numeric instrument keys —
        see docs/bugs/bugs.md BUG-033. Delegates to the shared
        ``_price_utils.resolve_option_expiry`` helper.
        """
        return resolve_option_expiry(instrument_key, self._resolve_instrument_lookup())

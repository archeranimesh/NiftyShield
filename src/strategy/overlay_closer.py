# src/strategy/overlay_closer.py
"""OverlayCloser — Atomic multi-leg close orchestrator with rollback on failure.

Handles atomic execution of close actions for CC, PP, and Collar overlays.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING, Any

import structlog

from src.instruments.lookup import InstrumentLookup
from src.market_calendar.holidays import market_today
from src.models.options import OptionChain, OptionLeg
from src.paper.constants import DEFAULT_BOD_PATH
from src.paper.models import ExitSignal, PaperPosition, PaperTrade, TradeAction

if TYPE_CHECKING:
    from src.paper.store import PaperStore
from src.strategy._price_utils import find_option_leg, resolve_price
from src.strategy.executor import PaperFillSimulator
from src.strategy.protocol import ApprovedAction

log = structlog.get_logger(__name__)

# Matches keys like "NSE_FO|NIFTY29MAY2026PE" → group 1 = "29MAY2026"
_EXPIRY_RE = re.compile(
    r"NSE_FO\|NIFTY(\d{2}[A-Za-z]{3}\d{4})(PE|CE)",
    re.IGNORECASE,
)

SHORT_CALL_ROLE = "overlay_collar_call"
LONG_PUT_ROLE = "overlay_collar_put"


class OverlayCloser:
    """Orchestrates overlay leg closure with rollback capabilities."""

    def __init__(
        self,
        store: PaperStore,
        simulator: PaperFillSimulator,
        notifier: Any = None,
        instrument_lookup: InstrumentLookup | None = None,
    ) -> None:
        """Initialise OverlayCloser.

        Args:
            store: PaperStore for database operations.
            simulator: PaperFillSimulator for fill pricing.
            notifier: Optional notifier (e.g. TelegramGateway) to alert on failure.
            instrument_lookup: Optional pre-built ``InstrumentLookup`` (BOD JSON),
                used by ``find_option_leg`` to resolve real numeric Upstox
                instrument keys that carry no strike/type in the key string
                itself. If not injected, lazily built from ``DEFAULT_BOD_PATH``
                on first use (same pattern as ``PaperStore._resolve_instrument_lookup``).
        """
        self._store = store
        self._simulator = simulator
        self._notifier = notifier
        self._instrument_lookup = instrument_lookup

    def _resolve_instrument_lookup(self) -> InstrumentLookup | None:
        """Lazily construct and cache the InstrumentLookup used for leg resolution.

        Non-fatal: on load failure, logs a WARNING and returns None so callers
        degrade to regex-only resolution (symbolic keys still work; real
        numeric keys will fail with the usual "leg absent from chain" error).
        """
        if self._instrument_lookup is None:
            try:
                self._instrument_lookup = InstrumentLookup.from_file(DEFAULT_BOD_PATH)
            except Exception as exc:
                log.warning("overlay_closer.bod_lookup_load_failed", error=str(exc))
                return None
        return self._instrument_lookup

    def close_single_leg(
        self,
        strategy_name: str,
        leg_role: str,
        market: OptionChain,
        event_id: int | None,
        vix: float | None = None,
        is_loss_stop: bool = False,
        dual_signal_audit: dict | None = None,
    ) -> None:
        """Close a single option position leg.

        Applies 1.5x slippage multiplier if is_loss_stop is True.
        """
        position = self._store.get_position(strategy_name, leg_role)
        if position.net_qty == 0:
            return

        close_action = TradeAction.SELL if position.net_qty > 0 else TradeAction.BUY
        mid_price = self._resolve_mid_price(position.instrument_key, market)

        fill = self._simulator.simulate_fill(
            instrument_key=position.instrument_key,
            action=close_action.value,
            quantity=abs(position.net_qty),
            mid_price=mid_price,
            vix=vix,
        )

        fill_price = fill.fill_price
        if is_loss_stop:
            slippage = fill.slippage
            if close_action == TradeAction.BUY:
                fill_price = mid_price + Decimal("1.5") * slippage
            else:
                fill_price = mid_price - Decimal("1.5") * slippage
            fill_price = max(fill_price, Decimal("0.01"))

        trade = PaperTrade(
            strategy_name=strategy_name,
            leg_role=leg_role,
            instrument_key=position.instrument_key,
            trade_date=market_today(),
            action=close_action,
            quantity=fill.quantity,
            price=fill_price,
            notes=f"overlay_close event_id={event_id}",
            ivr_at_entry=None,
            is_paper=True,
        )
        self._store.record_trade(trade)

        if event_id is not None:
            delta_stop_would_fire = None
            premium_stop_would_fire = None
            actual_rule_used = None
            if dual_signal_audit:
                delta_stop_would_fire = 1 if dual_signal_audit.get("delta_stop_would_fire") else 0
                premium_stop_would_fire = (
                    1 if dual_signal_audit.get("premium_stop_would_fire") else 0
                )
                actual_rule_used = dual_signal_audit.get("actual_rule_used")

            self._store.resolve_exit_event_with_audit(
                event_id=event_id,
                status="ACTED",
                delta_stop_would_fire=delta_stop_would_fire,
                premium_stop_would_fire=premium_stop_would_fire,
                actual_rule_used=actual_rule_used,
            )

    def close_collar_call_only(
        self,
        strategy_name: str,
        market: OptionChain,
        event_id: int | None,
        vix: float | None = None,
    ) -> None:
        """Close Collar short call leg only (e.g. on COLLAR_CALL_DECAY)."""
        dual_audit = None
        if event_id is not None:
            events = self._store.get_open_exit_events(strategy_name)
            event = next((e for e in events if e["id"] == event_id), None)
            if event:
                dual_audit = {
                    "delta_stop_would_fire": event.get("delta_stop_would_fire"),
                    "premium_stop_would_fire": event.get("premium_stop_would_fire"),
                    "actual_rule_used": event.get("actual_rule_used"),
                }
        self.close_single_leg(
            strategy_name=strategy_name,
            leg_role=SHORT_CALL_ROLE,
            market=market,
            event_id=event_id,
            vix=vix,
            is_loss_stop=False,
            dual_signal_audit=dual_audit,
        )

    def close_collar_all(
        self,
        strategy_name: str,
        market: OptionChain,
        event_id: int | None,
        vix: float | None = None,
    ) -> bool:
        """Atomically close both Collar legs (short call and long put) with rollback.

        Returns:
            True if the position ended up flat (either already flat, or the
            close trades were written successfully). False if a write failure
            left the position still open — callers must not treat the close
            as having happened when this returns False.
        """
        today = market_today()
        call_pos = self._store.get_position(strategy_name, SHORT_CALL_ROLE)
        put_pos = self._store.get_position(strategy_name, LONG_PUT_ROLE)
        call_qty = abs(call_pos.net_qty) if call_pos else 0
        put_qty = abs(put_pos.net_qty) if put_pos else 0
        if call_qty == 0 and put_qty == 0:
            log.warning("close_collar_all.already_flat", strategy_name=strategy_name)
            if event_id is not None:
                self._store.resolve_exit_event_with_audit(
                    event_id=event_id, status="DISMISSED", notes="Already flat"
                )
            return True

        # Build both close trades before any write so we can commit atomically.
        trades_to_write: list[PaperTrade] = []
        if call_pos and call_pos.net_qty < 0:
            mid = self._resolve_mid_price(call_pos.instrument_key, market)
            fill = self._simulator.simulate_fill(
                call_pos.instrument_key, "BUY", abs(call_pos.net_qty), mid, vix
            )
            trades_to_write.append(
                PaperTrade(
                    strategy_name=strategy_name,
                    leg_role=SHORT_CALL_ROLE,
                    instrument_key=call_pos.instrument_key,
                    trade_date=today,
                    action=TradeAction.BUY,
                    quantity=fill.quantity,
                    price=fill.fill_price,
                    notes=f"collar_close_all call event_id={event_id}",
                    ivr_at_entry=None,
                    is_paper=True,
                )
            )

        if put_pos and put_pos.net_qty > 0:
            mid = self._resolve_mid_price(put_pos.instrument_key, market)
            fill = self._simulator.simulate_fill(
                put_pos.instrument_key, "SELL", abs(put_pos.net_qty), mid, vix
            )
            trades_to_write.append(
                PaperTrade(
                    strategy_name=strategy_name,
                    leg_role=LONG_PUT_ROLE,
                    instrument_key=put_pos.instrument_key,
                    trade_date=today,
                    action=TradeAction.SELL,
                    quantity=fill.quantity,
                    price=fill.fill_price,
                    notes=f"collar_close_all put event_id={event_id}",
                    ivr_at_entry=None,
                    is_paper=True,
                )
            )

        if trades_to_write:
            try:
                inserted, skipped = self._store.record_trades(trades_to_write)
                if skipped:
                    raise RuntimeError(
                        f"Collar close: {len(skipped)} trade(s) skipped as duplicates"
                    )
            except Exception as e:
                # record_trades rolls back the entire batch on any exception;
                # no application-level delete is needed.
                log.error("collar_close_all.write_failed", error=str(e))
                if self._notifier:
                    self._notifier.send(
                        f"Collar close failed: could not write close trades. Error: {e}"
                    )
                return False

        if event_id is not None:
            self._store.resolve_exit_event_with_audit(event_id=event_id, status="ACTED")
        else:
            eid = self._store.create_exit_event(
                strategy_name=strategy_name,
                leg_name=SHORT_CALL_ROLE,
                trade_id="0",
                event_time=datetime.now(timezone.utc),
                detected_by="MANUAL",
                exit_signal=ExitSignal.COLLAR_CLOSE_ALL,
                severity="ACTION",
                entry_price=Decimal("0"),
                notes="MANUAL_OVERRIDE",
            )
            self._store.resolve_exit_event(eid, "ACTED")
        return True

    def monetize_collar_put(
        self,
        strategy_name: str,
        market: OptionChain,
        event_id: int | None,
        vix: float | None = None,
    ) -> None:
        """Monetise Collar put leg, buying back short call first if near-worthless."""
        today = market_today()
        call_pos = self._store.get_position(strategy_name, SHORT_CALL_ROLE)
        put_pos = self._store.get_position(strategy_name, LONG_PUT_ROLE)

        call_qty = abs(call_pos.net_qty) if call_pos else 0
        put_qty = abs(put_pos.net_qty) if put_pos else 0
        if call_qty == 0 and put_qty == 0:
            log.warning("monetize_collar_put.already_flat", strategy_name=strategy_name)
            if event_id is not None:
                self._store.resolve_exit_event_with_audit(
                    event_id=event_id, status="DISMISSED", notes="Already flat"
                )
            return

        # Guard: put leg must exist. Closing the call without the put would
        # leave a naked short call — an uncovered loss position.
        if put_qty == 0:
            log.error(
                "monetize_collar_put.incomplete_collar",
                strategy_name=strategy_name,
                call_qty=call_qty,
                put_qty=put_qty,
                note="Aborting — put leg missing, cannot monetize without leaving naked call",
            )
            if self._notifier:
                self._notifier.send(
                    f"Collar monetize aborted for {strategy_name}: "
                    "put leg is flat but call leg is open — incomplete collar structure."
                )
            return

        # Build all close trades first, then write atomically so a failure on
        # any leg rolls back the entire batch without application-level deletes.
        trades_to_write: list[PaperTrade] = []

        if call_pos and call_pos.net_qty < 0:
            call_leg = self._find_option_leg(market, call_pos.instrument_key)
            residual = float(call_leg.ltp) if call_leg is not None else 0.0
            if residual < 5.0:
                mid = self._resolve_mid_price(call_pos.instrument_key, market)
                fill = self._simulator.simulate_fill(
                    call_pos.instrument_key, "BUY", abs(call_pos.net_qty), mid, vix
                )
                trades_to_write.append(
                    PaperTrade(
                        strategy_name=strategy_name,
                        leg_role=SHORT_CALL_ROLE,
                        instrument_key=call_pos.instrument_key,
                        trade_date=today,
                        action=TradeAction.BUY,
                        quantity=fill.quantity,
                        price=fill.fill_price,
                        notes=f"collar_put_monetize call close event_id={event_id}",
                        ivr_at_entry=None,
                        is_paper=True,
                    )
                )

        if put_pos and put_pos.net_qty > 0:
            mid = self._resolve_mid_price(put_pos.instrument_key, market)
            fill = self._simulator.simulate_fill(
                put_pos.instrument_key, "SELL", abs(put_pos.net_qty), mid, vix
            )
            trades_to_write.append(
                PaperTrade(
                    strategy_name=strategy_name,
                    leg_role=LONG_PUT_ROLE,
                    instrument_key=put_pos.instrument_key,
                    trade_date=today,
                    action=TradeAction.SELL,
                    quantity=fill.quantity,
                    price=fill.fill_price,
                    notes=f"collar_put_monetize put close event_id={event_id}",
                    ivr_at_entry=None,
                    is_paper=True,
                )
            )

        if trades_to_write:
            try:
                inserted, skipped = self._store.record_trades(trades_to_write)
                if skipped:
                    raise RuntimeError(
                        f"Collar monetize: {len(skipped)} trade(s) skipped as duplicates"
                    )
            except Exception as e:
                # record_trades rolls back the entire batch on any exception.
                log.error("collar_put_monetize.write_failed", error=str(e))
                if self._notifier:
                    self._notifier.send(
                        f"Collar monetize failed: could not write close trades. Error: {e}"
                    )
                return

        expiry = self._parse_expiry(put_pos.instrument_key) if put_pos else None
        dte = (expiry - today).days if expiry is not None else 0
        notes = "Evaluate replacement" if dte >= 14 else ""

        if event_id is not None:
            self._store.resolve_exit_event_with_audit(
                event_id=event_id,
                status="ACTED",
                notes=notes if notes else None,
            )
        else:
            eid = self._store.create_exit_event(
                strategy_name=strategy_name,
                leg_name=LONG_PUT_ROLE,
                trade_id="0",
                event_time=datetime.now(timezone.utc),
                detected_by="MANUAL",
                exit_signal=ExitSignal.COLLAR_PUT_CRASH,
                severity="ACTION",
                entry_price=Decimal("0"),
                notes=notes if notes else None,
            )
            self._store.resolve_exit_event(eid, "ACTED")

    def route(
        self,
        strategy_name: str,
        action: ApprovedAction,
        market: OptionChain,
        event_id: int | None,
        vix: float | None = None,
    ) -> list[PaperPosition]:
        """Route the approved action to the appropriate overlay closer logic."""
        if action.action_type == "CLOSE_CC":
            is_loss_stop = False
            dual_audit = None
            if event_id is not None:
                events = self._store.get_open_exit_events(strategy_name)
                event = next((e for e in events if e["id"] == event_id), None)
                if event:
                    is_loss_stop = event["exit_signal"] in ("LOSS_STOP", "DELTA_STOP")
                    dual_audit = {
                        "delta_stop_would_fire": event.get("delta_stop_would_fire"),
                        "premium_stop_would_fire": event.get("premium_stop_would_fire"),
                        "actual_rule_used": event.get("actual_rule_used"),
                    }
            self.close_single_leg(
                strategy_name=strategy_name,
                leg_role="short_call",
                market=market,
                event_id=event_id,
                vix=vix,
                is_loss_stop=is_loss_stop,
                dual_signal_audit=dual_audit,
            )
        elif action.action_type == "MONETIZE_PP":
            self.close_single_leg(
                strategy_name=strategy_name,
                leg_role="protective_put",
                market=market,
                event_id=event_id,
                vix=vix,
                is_loss_stop=False,
            )
        elif action.action_type == "CLOSE_CALL_ONLY":
            self.close_collar_call_only(strategy_name, market, event_id, vix)
        elif action.action_type == "MONETIZE_PUT":
            self.monetize_collar_put(strategy_name, market, event_id, vix)
        elif action.action_type == "CLOSE_ALL_OVERLAY":
            self.close_collar_all(strategy_name, market, event_id, vix)
        else:
            raise ValueError(f"Unknown action type for OverlayCloser: {action.action_type}")

        return self._store.get_positions(strategy_name)

    # ── Private helpers ───────────────────────────────────────────────────────

    def _resolve_mid_price(self, instrument_key: str, market: OptionChain) -> Decimal:
        """Resolve mid price of option leg in chain.

        Args:
            instrument_key: Upstox instrument key.
            market: Current option chain snapshot.

        Returns:
            Mid price as ``Decimal``.

        Raises:
            ValueError: When the leg is absent from the chain or carries no
                positive price. Callers must not proceed with a zero-price fill.
        """
        leg = find_option_leg(instrument_key, market, lookup=self._resolve_instrument_lookup())
        if leg is None:
            raise ValueError(f"resolve_mid_price: leg absent from chain for {instrument_key}")
        return resolve_price(leg)

    def _find_option_leg(self, market: OptionChain, instrument_key: str) -> OptionLeg | None:
        """Locate option leg in chain.

        Delegates to the shared ``find_option_leg`` utility so that key-parse
        and lookup errors are logged at WARNING rather than silently swallowed.
        """
        return find_option_leg(instrument_key, market, lookup=self._resolve_instrument_lookup())

    def _parse_expiry(self, instrument_key: str) -> date | None:
        """Extract expiry date."""
        m = _EXPIRY_RE.search(instrument_key)
        if not m:
            return None
        try:
            return datetime.strptime(m.group(1).upper(), "%d%b%Y").date()
        except ValueError:
            return None

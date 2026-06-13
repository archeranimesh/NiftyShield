"""CSPNiftyV1 — fully-automated Cash-Secured Put strategy for Nifty 50.

Implements PaperStrategy protocol with ``auto_execute = True``.  On every
tick StrategyMonitor calls check_signals(); when an ACTION signal fires the
monitor calls apply_action() directly (no Telegram approval gate) and sends
a plain notification with the outcome.

Signal priority (CR1d — first matching ACTION signal per position per tick)
---------------------------------------
| Priority | Event type         | Severity | Trigger                       | Action         |
|----------|--------------------|----------|-------------------------------|----------------|
| 1        | HARD_STOP          | ACTION   | LTP ≥ 2× entry credit         | CLOSE_AND_WAIT |
| 2        | DELTA_BREACH_FINAL | ACTION   | |δ| ≥ 0.40 (DEFENDED state)   | CLOSE_AND_WAIT |
| 3        | DELTA_BREACH       | ACTION   | |δ| ≥ 0.40 (OPEN state)       | ROLL_DOWN_AND_OUT |
| 4        | PROFIT_TARGET      | ACTION   | LTP ≤ 30% of entry credit     | CLOSE_AND_ROLL |
| 5        | TIME_STOP          | ACTION   | days_held ≥ 21                | CLOSE_AND_ROLL |
| 6        | ROLL_ELIGIBLE      | ACTION   | DTE ≤ 7                       | CLOSE_AND_ROLL |

apply_action handles four action types:
  CLOSE_AND_ROLL   → close_csp_leg + open_new_csp_leg (re-entry check via ReEntryMixin)
  ROLL_DOWN_AND_OUT → roll_down_and_out; position state → DEFENDED
  CLOSE_AND_WAIT   → close_csp_leg; position state → RE_ENTRY_PENDING
  OPEN_NEW         → open_new_csp_leg (triggered when state = RE_ENTRY_PENDING)

Note: TIME_STOP is ``days_held ≥ 21`` (calendar days since first SELL trade),
NOT ``DTE ≤ 21``.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import structlog

from src.config import settings
from src.models.options import OptionChain, OptionLeg
from src.paper.models import PaperPosition, TradeState
from src.strategy.csp_roll_executor import close_csp_leg, open_new_csp_leg, roll_down_and_out
from src.strategy.exit_signals import ExitSignalEngine
from src.strategy.protocol import ApprovedAction, SignalEvent
from src.strategy.reentry_mixin import ReEntryMixin

log = structlog.get_logger(__name__)

# ── Regexes ───────────────────────────────────────────────────────────────────

# Matches keys like "NSE_FO|NIFTY29MAY2026PE" → group 1 = "29MAY2026"
_EXPIRY_RE = re.compile(
    r"NSE_FO\|NIFTY(\d{2}[A-Za-z]{3}\d{4})(PE|CE)",
    re.IGNORECASE,
)

# Matches keys like "NSE_FO|NIFTY23000PE" → group 1 = "23000"
# Does NOT match date-embedded keys (digit run broken by alpha month chars).
_STRIKE_RE = re.compile(r"NIFTY(\d+)(PE|CE)", re.IGNORECASE)

# Thresholds are owned by ExitSignalEngine (exit_signals.py).
# Constants here are kept only for docstring / describe_context reference.
_TIME_STOP_DAYS = 21  # days_held ≥ 21 (calendar days since entry SELL trade)

# Priority-ordered mapping: signal type → auto_action dispatched by StrategyMonitor.
# First matching ACTION signal per position per tick is emitted; lower entries are suppressed.
_SIGNAL_ACTION_MAP: dict[str, str] = {
    "HARD_STOP": "CLOSE_AND_WAIT",
    "DELTA_BREACH_FINAL": "CLOSE_AND_WAIT",
    "DELTA_BREACH": "ROLL_DOWN_AND_OUT",
    "PROFIT_TARGET": "CLOSE_AND_ROLL",
    "TIME_STOP": "CLOSE_AND_ROLL",
    "ROLL_ELIGIBLE": "CLOSE_AND_ROLL",
}


class CSPNiftyV1(ReEntryMixin):
    """Backbone-compatible wrapper for the paper_csp_nifty_v1 strategy.

    Registers with StrategyMonitor to emit exit/roll signals on every tick.
    The strategy name must match the ``strategy_name`` column used by
    ``record_paper_trade.py`` when recording CSP trades.
    """

    strategy_name: str = "paper_csp_nifty_v1"
    auto_execute: bool = True
    reentry_leg_role: str = "short_put"
    reentry_script_hint: str = "find_strike_by_delta.py"

    def __init__(
        self,
        broker: Any = None,
        store: Any = None,
        notifier: Any = None,
        vix_data_dir: Path | str | None = None,
    ) -> None:
        """Initialise CSPNiftyV1.

        Args:
            broker: BrokerClient instance used by apply_action to fetch LTP
                and open new positions (close_csp_leg / open_new_csp_leg).
            store: PaperStore instance for trade writes and R5 re-entry events.
            notifier: Notification gateway (must have ``send_plain_message``
                and ``send_notification``).
            vix_data_dir: Directory containing India VIX Parquet files.
                Defaults to ``settings.vix_data_dir``.
        """
        self._broker = broker
        self._store = store
        self._notifier = notifier
        self._vix_data_dir = (
            Path(vix_data_dir) if vix_data_dir is not None else Path(settings.vix_data_dir)
        )

    # ── PaperStrategy protocol ────────────────────────────────────────────────

    async def check_signals(
        self,
        market: OptionChain,
        positions: list[PaperPosition],
    ) -> list[SignalEvent]:
        """Evaluate exit and warning signals for all open short-put positions.

        Filters positions to ``strategy_name == "paper_csp_nifty_v1"`` and
        ``net_qty < 0`` (short).  Returns ``[]`` when no open positions exist.

        Signal priority (CR1d): for each position at most ONE ACTION signal is
        emitted — the highest-priority one per ``_SIGNAL_ACTION_MAP``.  All
        non-ACTION (WARN/INFO) signals are emitted unconditionally.

        ACTION payload includes ``auto_execute=True``, ``auto_action`` (the
        action type StrategyMonitor will dispatch), and ``triggering_signal``
        (the raw ExitSignalEngine result for audit).

        Args:
            market: Current Nifty 50 option chain snapshot.
            positions: All open paper positions (may include other strategies).

        Returns:
            List of detected SignalEvents; empty list when nothing to act on.
        """
        events: list[SignalEvent] = []
        today = date.today()

        for pos in positions:
            if pos.strategy_name != self.strategy_name:
                continue
            if pos.net_qty >= 0:
                continue  # only short legs trigger signals

            put_leg = self._find_put_leg(market, pos.instrument_key)
            if put_leg is None:
                log.warning(
                    "csp_nifty_v1.check_signals.put_leg_not_found",
                    instrument_key=pos.instrument_key,
                    reason="chain_expiry_mismatch_or_unresolved_strike",
                )

            expiry = self._parse_expiry(pos.instrument_key)
            dte = (expiry - today).days if expiry is not None else 9999

            days_held = (today - pos.entry_date).days if pos.entry_date is not None else 0

            entry_credit = Decimal(str(pos.avg_sell_price))
            trade_state = pos.state if hasattr(pos, "state") else TradeState.OPEN

            # Evaluate in priority order (highest priority first) so the action_emitted
            # suppression loop emits the most critical signal per position per tick.
            results = []
            if put_leg is not None:
                ltp = Decimal(str(put_leg.ltp))
                delta = float(put_leg.delta)
                results += ExitSignalEngine.evaluate_hard_stop_csp(
                    ltp=ltp, entry_credit=entry_credit
                )
                results += ExitSignalEngine.evaluate_delta_breach_csp(
                    delta=delta, state=trade_state
                )
                results += ExitSignalEngine.evaluate_profit_target_csp(
                    ltp=ltp, entry_credit=entry_credit
                )
            # Time-based signals fire even when the chain does not carry this expiry.
            results += ExitSignalEngine.evaluate_time_stop_csp(days_held=days_held)
            results += ExitSignalEngine.evaluate_roll_eligible_csp(dte=dte)
            results = ExitSignalEngine._sort_results(results)

            action_emitted = False
            for result in results:
                payload: dict = {"leg_role": pos.leg_role}
                if put_leg is not None:
                    payload["delta"] = str(put_leg.delta)
                    payload["ltp"] = str(put_leg.ltp)
                    payload["entry_credit"] = str(pos.avg_sell_price)
                payload["days_held"] = days_held
                payload["dte"] = dte

                if result.severity == "ACTION":
                    if action_emitted:
                        continue  # suppress lower-priority ACTION signals
                    auto_action = _SIGNAL_ACTION_MAP.get(result.exit_signal, "CLOSE_AND_WAIT")
                    payload["auto_execute"] = True
                    payload["auto_action"] = auto_action
                    payload["triggering_signal"] = result.exit_signal
                    payload["valid_actions"] = [auto_action, "CLOSE_FULL"]
                    action_emitted = True
                else:
                    payload["valid_actions"] = ["CLOSE_FULL"]

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
        """Build a plain-text context block for the council prompt.

        Returns a structured string summarising the current state of the open
        CSP position.  Falls back gracefully when chain data is unavailable.

        Args:
            event: The signal event that triggered the context request.
            market: Current Nifty 50 option chain snapshot.
            positions: All open paper positions.

        Returns:
            Multi-line plain-text context string; no HTML markup.
        """
        short_puts = [
            p for p in positions if p.strategy_name == self.strategy_name and p.net_qty < 0
        ]
        lines: list[str] = [
            f"Strategy: {self.strategy_name}",
            f"Signal: {event.event_type} ({event.severity})",
            f"Nifty spot: {market.underlying_spot}",
        ]

        for pos in short_puts:
            put_leg = self._find_put_leg(market, pos.instrument_key)
            expiry = self._parse_expiry(pos.instrument_key)
            dte = (expiry - date.today()).days if expiry is not None else None
            entry_credit = pos.avg_sell_price

            lines.append(f"Leg: {pos.leg_role} | key: {pos.instrument_key}")
            lines.append(f"  Entry credit : {entry_credit}")

            if put_leg is not None:
                mark = put_leg.ltp
                pct_remaining = (
                    (mark / entry_credit * 100).quantize(Decimal("0.1"))
                    if entry_credit > Decimal("0")
                    else Decimal("0")
                )
                pct_captured = (
                    ((Decimal("1") - mark / entry_credit) * 100).quantize(Decimal("0.1"))
                    if entry_credit > Decimal("0")
                    else Decimal("0")
                )
                lines.append(f"  Current mark : {mark} ({pct_remaining}% of credit)")
                lines.append(f"  % captured   : {pct_captured}%")
                lines.append(f"  Delta        : {put_leg.delta}")
                lines.append(f"  IV           : {put_leg.iv}")
            else:
                lines.append("  Current mark : unavailable (chain lookup failed)")

            if dte is not None:
                lines.append(f"  DTE          : {dte}")
                if expiry is not None:
                    lines.append(f"  Expiry       : {expiry.isoformat()}")
            else:
                lines.append("  DTE          : unavailable (expiry not in key)")

        if not short_puts:
            lines.append("No open short-put positions found.")

        return "\n".join(lines)

    async def apply_action(
        self,
        positions: list[PaperPosition],
        action: ApprovedAction,
    ) -> list[PaperPosition]:
        """Execute an action against the current CSP position.

        Supported action types (CR1d):

        ``CLOSE_AND_ROLL``
            Close the short-put leg at live LTP, then immediately open a new
            CSP leg on the next monthly expiry.  Re-entry eligibility check
            runs via ReEntryMixin.  Sends a Telegram notification on completion.

        ``ROLL_DOWN_AND_OUT``
            Defensive roll: close the short-put, open a new leg on next weekly
            expiry at a lower strike.  Sets position state to DEFENDED.

        ``CLOSE_AND_WAIT``
            Close the short-put at live LTP; state → RE_ENTRY_PENDING.
            No new position is opened.  Used for HARD_STOP / DELTA_BREACH_FINAL.

        ``OPEN_NEW``
            Open a fresh short-put (re-entry from RE_ENTRY_PENDING state).

        ``CLOSE_FULL`` (backward-compat)
            Alias for CLOSE_AND_WAIT without state change; kept to handle
            Telegram buttons from the pre-CR1d approval flow during rollover.

        Args:
            positions: Current open paper positions.
            action: Action to apply.  ``action.metadata`` may carry
                ``"triggering_signal"`` for re-entry gate logic.

        Returns:
            Updated positions list (closed legs removed, new leg appended if
            a new position was opened).

        Raises:
            ValueError: If ``action_type`` is not one of the supported values.
        """
        _valid = ("CLOSE_AND_ROLL", "ROLL_DOWN_AND_OUT", "CLOSE_AND_WAIT", "OPEN_NEW", "CLOSE_FULL")
        if action.action_type not in _valid:
            raise ValueError(
                f"CSPNiftyV1 does not accept action_type={action.action_type!r}; valid: {_valid}"
            )

        log.info(
            "csp_nifty_v1.apply_action",
            action_type=action.action_type,
            triggering_signal=(action.metadata or {}).get("triggering_signal"),
        )

        today = date.today()
        short_put = next(
            (p for p in positions if p.strategy_name == self.strategy_name and p.net_qty < 0),
            None,
        )

        if action.action_type == "OPEN_NEW":
            return await self._open_new(positions, today)

        # All other actions require an existing short-put to close.
        if short_put is None:
            log.warning(
                "csp_nifty_v1.apply_action.no_position",
                action_type=action.action_type,
            )
            return positions

        remaining = [p for p in positions if p is not short_put]

        if action.action_type in ("CLOSE_AND_ROLL", "CLOSE_FULL"):
            await self._close_leg(short_put, today)
            if action.action_type == "CLOSE_AND_ROLL":
                remaining = await self._open_new(remaining, today)
                await self._reentry_notification(short_put, action)
            return remaining

        if action.action_type == "CLOSE_AND_WAIT":
            await self._close_leg(short_put, today)
            await self._send_notification(
                f"⛔ <b>CSP closed — waiting</b>\n"
                f"Signal: {(action.metadata or {}).get('triggering_signal', 'CLOSE_AND_WAIT')}\n"
                f"Instrument: <code>{short_put.instrument_key}</code>\n"
                f"State → RE_ENTRY_PENDING — no new position opened."
            )
            return remaining

        if action.action_type == "ROLL_DOWN_AND_OUT":
            return await self._roll_down(short_put, remaining, today)

        return remaining  # unreachable but satisfies mypy

    # ── Action helpers ────────────────────────────────────────────────────────

    async def _close_leg(self, pos: PaperPosition, today: date) -> None:
        """Fetch live LTP and record a close trade for ``pos``."""
        from src.paper.models import PaperTrade

        if self._broker is None or self._store is None:
            log.warning("csp_nifty_v1._close_leg: broker or store not set — skipping DB write")
            return

        # Reconstruct a minimal PaperTrade for close_csp_leg.
        from src.paper.models import TradeAction

        existing = PaperTrade(
            strategy_name=pos.strategy_name,
            leg_role=pos.leg_role,
            instrument_key=pos.instrument_key,
            trade_date=pos.entry_date or today,
            action=TradeAction.SELL,
            quantity=abs(pos.net_qty),
            price=pos.avg_sell_price,
        )
        await close_csp_leg(
            broker=self._broker,
            store=self._store,
            existing=existing,
            roll_date=today,
            dry_run=False,
        )

    async def _open_new(self, positions: list[PaperPosition], today: date) -> list[PaperPosition]:
        """Open a new short-put and return the updated positions list."""
        if self._broker is None or self._store is None:
            log.warning("csp_nifty_v1._open_new: broker or store not set — skipping")
            return positions

        from src.instruments.lookup import InstrumentLookup

        lookup = InstrumentLookup.from_file("data/instruments/NSE.json.gz")
        try:
            await open_new_csp_leg(
                broker=self._broker,
                store=self._store,
                lookup=lookup,
                strategy=self.strategy_name,
                roll_date=today,
                dry_run=False,
                quantity=1,
            )
        except Exception as exc:
            log.error("csp_nifty_v1._open_new.failed", error=str(exc))
            await self._send_notification(
                f"⚠️ <b>CSP open_new failed</b>\nError: {exc}\n"
                f"Manual entry required via <code>record_paper_trade.py</code>"
            )
        return positions

    async def _roll_down(
        self,
        short_put: PaperPosition,
        remaining: list[PaperPosition],
        today: date,
    ) -> list[PaperPosition]:
        """Defensive roll: close + reopen on next weekly at lower strike."""
        if self._broker is None or self._store is None:
            log.warning("csp_nifty_v1._roll_down: broker or store not set — skipping")
            return remaining

        from src.instruments.lookup import InstrumentLookup
        from src.paper.models import PaperTrade, TradeAction

        lookup = InstrumentLookup.from_file("data/instruments/NSE.json.gz")
        existing = PaperTrade(
            strategy_name=short_put.strategy_name,
            leg_role=short_put.leg_role,
            instrument_key=short_put.instrument_key,
            trade_date=short_put.entry_date or today,
            action=TradeAction.SELL,
            quantity=abs(short_put.net_qty),
            price=short_put.avg_sell_price,
        )
        try:
            result = await roll_down_and_out(
                broker=self._broker,
                store=self._store,
                lookup=lookup,
                existing=existing,
                roll_date=today,
                dry_run=False,
            )
            await self._send_notification(
                f"🔄 <b>CSP rolled down-and-out</b>\n"
                f"Closed: <code>{short_put.instrument_key}</code>\n"
                f"Opened: <code>{result.new_trade.instrument_key}</code>\n"
                f"New credit: {result.new_trade.price}"
            )
        except Exception as exc:
            log.error("csp_nifty_v1._roll_down.failed", error=str(exc))
            await self._send_notification(
                f"⚠️ <b>CSP roll_down_and_out failed</b>\nError: {exc}\n"
                f"Position may be open — check immediately."
            )
        return remaining

    async def _reentry_notification(
        self, closed_pos: PaperPosition, action: ApprovedAction
    ) -> None:
        """Run re-entry eligibility check and notify."""
        triggering = (action.metadata or {}).get("triggering_signal", "CLOSE_AND_ROLL")
        expiry = self._parse_expiry(closed_pos.instrument_key)
        await self._check_reentry(
            expiry=expiry,
            today=date.today(),
            instrument_key=closed_pos.instrument_key,
            trade_id=0,
        )
        await self._send_notification(
            f"✅ <b>CSP closed — {triggering}</b>\n"
            f"Instrument: <code>{closed_pos.instrument_key}</code>\n"
            f"New position opened.  Re-entry eligibility check written to paper_exit_events."
        )

    async def _send_notification(self, message: str) -> None:
        """Send a plain HTML notification; non-fatal if notifier is absent."""
        if self._notifier is None:
            return
        try:
            await self._notifier.send_notification(message)
        except Exception as exc:
            log.warning("csp_nifty_v1.send_notification.failed", error=str(exc))

    # ── Private helpers ───────────────────────────────────────────────────────

    def _find_put_leg(self, market: OptionChain, instrument_key: str) -> OptionLeg | None:
        """Locate the PE leg in the chain for the given position.

        Tries a direct strike lookup by parsing ``instrument_key`` first.
        Falls back to scanning chain strikes for the first PE with non-zero
        LTP when the key carries no parseable strike (e.g. numeric Upstox
        IDs like ``NSE_FO|47196``).

        Args:
            market: Current option chain.
            instrument_key: Position's Upstox instrument key.

        Returns:
            Matching ``OptionLeg`` (PE side), or ``None`` when unavailable.
        """
        # Direct lookup: extract strike digits from key
        m = _STRIKE_RE.search(instrument_key)
        if m:
            try:
                strike = Decimal(m.group(1))
                strike_data = market.strikes.get(strike)
                if strike_data is not None and strike_data.pe is not None:
                    return strike_data.pe
            except InvalidOperation:
                log.warning(
                    "csp_nifty_v1.strike_parse_failed",
                    instrument_key=instrument_key,
                )

        # Fallback: scan for first PE with non-zero LTP.
        # Used when instrument_key carries no parseable strike (e.g. numeric
        # Upstox IDs like "NSE_FO|47196").  Safe for Phase 0 where at most
        # one CSP position is open at a time; incorrect in a multi-position
        # context.  Returns None when no PE leg is found.
        for strike_data in market.strikes.values():
            if strike_data.pe is not None and strike_data.pe.ltp > Decimal("0"):
                log.debug(
                    "csp_nifty_v1.put_leg_fallback_used",
                    instrument_key=instrument_key,
                    fallback_strike=str(strike_data.pe.strike),
                )
                return strike_data.pe

        return None

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

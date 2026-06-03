"""CSPNiftyV1 — backbone-compatible Cash-Secured Put strategy for Nifty 50.

Implements PaperStrategy protocol so StrategyMonitor can auto-detect exit
signals for the paper_csp_nifty_v1 strategy.  Entry remains manual via
``record_paper_trade.py``.

Signal table (council-spec 2026-05-28)
---------------------------------------
| Event type    | Severity | Trigger                                       |
|---------------|----------|-----------------------------------------------|
| PROFIT_TARGET | ACTION   | mark ≤ 50% of entry credit                    |
| LOSS_STOP     | ACTION   | mark ≥ 1.75× entry credit                     |
| DELTA_STOP    | ACTION   | short put |delta| ≥ 0.45                      |
| TIME_STOP     | ACTION   | 21 calendar days elapsed since entry          |
| DTE_REVIEW    | WARN     | DTE ≤ 5                                       |
| DELTA_WARN    | WARN     | short put |delta| ≥ 0.35                      |

Multiple signals may fire in a single tick.  ACTION signals gate a council +
Telegram approval flow; WARN signals send a plain Telegram message.

Note: TIME_STOP is ``days_held ≥ 21`` (calendar days since first SELL trade),
NOT ``DTE ≤ 21``.  These are different: a position entered with 5 DTE remaining
would never trigger a DTE-based check; the days-held check fires 21 days after
entry regardless of expiry distance.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import pandas as pd
import structlog

from src.backtest.ivr import compute_ivr
from src.backtest.vix_ingest import load_vix_series
from src.config import settings
from src.models.options import OptionChain, OptionLeg
from src.paper.models import ExitSignal, PaperPosition
from src.strategy.exit_signals import ExitSignalEngine
from src.strategy.protocol import ApprovedAction, SignalEvent

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
_ROLL_DTE = 5  # DTE_REVIEW WARN threshold


class CSPNiftyV1:
    """Backbone-compatible wrapper for the paper_csp_nifty_v1 strategy.

    Registers with StrategyMonitor to emit exit/roll signals on every tick.
    The strategy name must match the ``strategy_name`` column used by
    ``record_paper_trade.py`` when recording CSP trades.
    """

    strategy_name: str = "paper_csp_nifty_v1"

    def __init__(
        self,
        broker: Any = None,
        store: Any = None,
        notifier: Any = None,
        vix_data_dir: Path | str | None = None,
    ) -> None:
        """Initialise CSPNiftyV1.

        Args:
            broker: BrokerClient instance (unused by this strategy directly;
                accepted for protocol compatibility with StrategyMonitor).
            store: PaperStore instance for R5 re-entry event writes.
            notifier: Notification gateway (must have ``send_plain_message``).
            vix_data_dir: Directory containing India VIX Parquet files.
                Defaults to ``settings.vix_data_dir``.
        """
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

        Delegates threshold evaluation to ``ExitSignalEngine.evaluate_csp()``.
        Multiple signals may fire simultaneously.

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
            expiry = self._parse_expiry(pos.instrument_key)
            dte = (expiry - today).days if expiry is not None else 9999

            days_held = (today - pos.entry_date).days if pos.entry_date is not None else 0

            delta = float(put_leg.delta) if put_leg is not None else None
            current_mark = float(put_leg.ltp) if put_leg is not None else 0.0
            entry_price = float(pos.avg_sell_price)

            results = ExitSignalEngine.evaluate_csp(
                entry_price=entry_price,
                current_mark=current_mark,
                delta=delta,
                days_held=days_held,
                dte=dte,
            )

            for result in results:
                payload: dict = {"leg_role": pos.leg_role}
                if put_leg is not None:
                    payload["delta"] = str(put_leg.delta)
                    payload["mark"] = str(put_leg.ltp)
                    payload["entry_credit"] = str(pos.avg_sell_price)
                if result.delta_stop_would_fire is not None:
                    payload["delta_stop_would_fire"] = result.delta_stop_would_fire
                if result.premium_stop_would_fire is not None:
                    payload["premium_stop_would_fire"] = result.premium_stop_would_fire
                if result.actual_rule_used is not None:
                    payload["actual_rule_used"] = result.actual_rule_used
                payload["days_held"] = days_held
                payload["dte"] = dte

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
        """Validate and apply an approved action.

        Only ``CLOSE_FULL`` is supported.  Returns the positions list with
        closed legs removed.  Actual DB writes are handled by
        ``PaperExecutor``; this method performs validation + optimistic
        position filtering.

        Args:
            positions: Current open paper positions.
            action: Approved action; must have ``action_type`` of
                ``"CLOSE_FULL"`` or ``"PROFIT_TARGET"``.
                ``PROFIT_TARGET`` additionally triggers the R5 re-entry
                eligibility check and fires a Telegram alert.

        Returns:
            Updated positions with closed legs filtered out.

        Raises:
            ValueError: When ``action_type`` is anything other than
                ``"CLOSE_FULL"`` or ``"PROFIT_TARGET"``.
        """
        if action.action_type not in ("CLOSE_FULL", "PROFIT_TARGET"):
            raise ValueError(
                f"CSPNiftyV1 only accepts CLOSE_FULL or PROFIT_TARGET actions; "
                f"got {action.action_type!r}"
            )
        closed: set[str] = set(action.legs_to_close)
        log.info(
            "csp_nifty_v1.apply_action",
            action_type=action.action_type,
            legs_to_close=list(closed),
        )

        # Capture closed short-put position before filtering for R5 check.
        closed_pos = next(
            (p for p in positions if p.leg_role in closed and p.net_qty < 0),
            None,
        )
        updated = [p for p in positions if p.leg_role not in closed]

        if action.action_type == "PROFIT_TARGET":
            if closed_pos is not None:
                expiry = self._parse_expiry(closed_pos.instrument_key)
                await self._check_r5_reentry(
                    expiry=expiry,
                    today=date.today(),
                    instrument_key=closed_pos.instrument_key,
                )
            else:
                log.warning(
                    "csp_nifty_v1.r5_check_skipped",
                    reason="no short_put position found in legs_to_close",
                )

        return updated

    # ── Private helpers ───────────────────────────────────────────────────────

    async def _check_r5_reentry(
        self,
        expiry: date | None,
        today: date,
        instrument_key: str,
    ) -> None:
        """Evaluate R5 re-entry eligibility and write a paper_exit_events row.

        Three gates — all must pass for ELIGIBLE:
        1. ``(expiry - today).days ≥ 14`` calendar days to expiry.
        2. Trailing 252-day IVR ≥ 0.25 (None history → blocked conservatively).
        3. No open ``short_put`` position in store for this strategy.

        Always writes to ``paper_exit_events`` (ELIGIBLE or BLOCKED) and sends
        a Telegram notification.  Notifier failure is non-fatal — the event is
        written regardless.

        Args:
            expiry: Expiry date parsed from the closed instrument key, or
                ``None`` if the key carried no parseable date.
            today: Reference date (injectable for testing).
            instrument_key: Instrument key of the closed short-put position.
                Used as ``trade_id`` in the exit event row.
        """
        if self._store is None:
            log.warning("csp_nifty_v1.r5_check_skipped", reason="no store configured")
            return

        blocked_reason: str | None = None

        # ── Gate 1: DTE ≥ 14 ─────────────────────────────────────────────────
        dte = (expiry - today).days if expiry is not None else 0
        if expiry is None or dte < 14:
            blocked_reason = f"DTE={dte} < 14 — too close to expiry for re-entry"

        # ── Gate 2: IVR ≥ 0.25 ───────────────────────────────────────────────
        if blocked_reason is None:
            try:
                vix_series: pd.Series = load_vix_series(self._vix_data_dir)
                if vix_series.empty or len(vix_series) < 252:
                    blocked_reason = "IVR history insufficient — cannot verify R3"
                else:
                    vix_today = float(vix_series.iloc[-1])
                    ivr = compute_ivr(vix_today, vix_series)
                    if ivr is None:
                        blocked_reason = "IVR history insufficient — cannot verify R3"
                    elif ivr < 0.25:
                        blocked_reason = f"IVR={ivr:.2f} < 0.25 — low vol, skip cycle"
            except Exception as exc:
                log.warning("csp_nifty_v1.r5_ivr_load_failed", error=str(exc))
                blocked_reason = "IVR history insufficient — cannot verify R3"

        # ── Gate 3: No open short_put ─────────────────────────────────────────
        if blocked_reason is None:
            try:
                existing = self._store.get_positions(self.strategy_name)
                if any(p.leg_role == "short_put" and p.net_qty < 0 for p in existing):
                    blocked_reason = (
                        "open position: short_put already active for paper_csp_nifty_v1"
                    )
            except Exception as exc:
                log.warning("csp_nifty_v1.r5_positions_check_failed", error=str(exc))
                blocked_reason = "open position check failed — cannot verify gate 3"

        signal = (
            ExitSignal.R5_REENTRY_ELIGIBLE
            if blocked_reason is None
            else ExitSignal.R5_REENTRY_BLOCKED
        )
        notes = blocked_reason or "All R5 re-entry gates passed"

        # ── Write exit event ──────────────────────────────────────────────────
        try:
            self._store.create_exit_event(
                strategy_name=self.strategy_name,
                leg_name="short_put",
                trade_id=instrument_key or "unknown",
                event_time=datetime.utcnow(),
                detected_by="MANUAL",
                exit_signal=signal,
                severity="INFO",
                entry_price=0.0,
                notes=notes,
            )
            log.info(
                "csp_nifty_v1.r5_reentry_event_written",
                signal=signal.value,
                notes=notes,
            )
        except Exception as exc:
            log.error("csp_nifty_v1.r5_reentry_event_write_failed", error=str(exc))

        # ── Notify ────────────────────────────────────────────────────────────
        if self._notifier is not None:
            status_line = (
                "✅ CSP R5 Re-entry ELIGIBLE — run find_strike_by_delta.py"
                if signal == ExitSignal.R5_REENTRY_ELIGIBLE
                else "⛔ CSP R5 Re-entry BLOCKED"
            )
            msg = f"{status_line}\n{notes}"
            try:
                await self._notifier.send_plain_message(msg)
            except Exception as exc:
                log.warning("csp_nifty_v1.r5_reentry_notify_failed", error=str(exc))

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

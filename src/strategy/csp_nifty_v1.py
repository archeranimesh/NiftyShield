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

import structlog

from src.models.options import OptionChain, OptionLeg
from src.paper.models import PaperPosition
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
_TIME_STOP_DAYS = 21   # days_held ≥ 21 (calendar days since entry SELL trade)
_ROLL_DTE = 5          # DTE_REVIEW WARN threshold


class CSPNiftyV1:
    """Backbone-compatible wrapper for the paper_csp_nifty_v1 strategy.

    Registers with StrategyMonitor to emit exit/roll signals on every tick.
    The strategy name must match the ``strategy_name`` column used by
    ``record_paper_trade.py`` when recording CSP trades.
    """

    strategy_name: str = "paper_csp_nifty_v1"

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
            p
            for p in positions
            if p.strategy_name == self.strategy_name and p.net_qty < 0
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
                    ((Decimal("1") - mark / entry_credit) * 100).quantize(
                        Decimal("0.1")
                    )
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
            action: Approved action; must have ``action_type == "CLOSE_FULL"``.

        Returns:
            Updated positions with closed legs filtered out.

        Raises:
            ValueError: When ``action_type`` is anything other than
                ``"CLOSE_FULL"``.
        """
        if action.action_type != "CLOSE_FULL":
            raise ValueError(
                f"CSPNiftyV1 only accepts CLOSE_FULL actions; "
                f"got {action.action_type!r}"
            )
        closed: set[str] = set(action.legs_to_close)
        log.info(
            "csp_nifty_v1.apply_action",
            action_type=action.action_type,
            legs_to_close=list(closed),
        )
        return [p for p in positions if p.leg_role not in closed]

    # ── Private helpers ───────────────────────────────────────────────────────

    def _find_put_leg(
        self, market: OptionChain, instrument_key: str
    ) -> OptionLeg | None:
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

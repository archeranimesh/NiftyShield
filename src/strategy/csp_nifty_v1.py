"""CSPNiftyV1 — backbone-compatible Cash-Secured Put strategy for Nifty 50.

Implements PaperStrategy protocol so StrategyMonitor can auto-detect exit
signals for the paper_csp_nifty_v1 strategy.  Entry remains manual via
``record_paper_trade.py``.

Signal table
------------
| Event type    | Severity | Trigger                              |
|---------------|----------|--------------------------------------|
| PROFIT_TARGET | ACTION   | mark ≤ 50% of entry credit           |
| LOSS_STOP     | ACTION   | mark ≥ 2.0× entry credit             |
| DELTA_STOP    | ACTION   | short put |delta| ≥ 0.35             |
| TIME_STOP     | ACTION   | DTE ≤ 21                             |
| ROLL_DUE_DTE  | WARN     | DTE ≤ 5                              |
| ROLL_DUE_DECAY| WARN     | current premium ≤ 25% of entry credit|
| DELTA_WARN    | WARN     | short put |delta| ≥ 0.25             |

Multiple signals may fire in a single tick (e.g. DELTA_STOP also triggers
DELTA_WARN).  ACTION signals gate a council + Telegram approval flow;
WARN signals send a plain Telegram message.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from src.models.options import OptionChain, OptionLeg
from src.paper.models import PaperPosition
from src.strategy.protocol import ApprovedAction, SignalEvent

# ── Regexes ───────────────────────────────────────────────────────────────────

# Matches keys like "NSE_FO|NIFTY29MAY2026PE" → group 1 = "29MAY2026"
_EXPIRY_RE = re.compile(
    r"NSE_FO\|NIFTY(\d{2}[A-Za-z]{3}\d{4})(PE|CE)",
    re.IGNORECASE,
)

# Matches keys like "NSE_FO|NIFTY23000PE" → group 1 = "23000"
# Does NOT match date-embedded keys (digit run broken by alpha month chars).
_STRIKE_RE = re.compile(r"NIFTY(\d+)(PE|CE)", re.IGNORECASE)

# ── Thresholds ────────────────────────────────────────────────────────────────

_PROFIT_TARGET_PCT = Decimal("0.50")   # mark ≤ 50% of entry credit
_LOSS_STOP_PCT = Decimal("2.0")        # mark ≥ 200% of entry credit
_DECAY_WARN_PCT = Decimal("0.25")      # mark ≤ 25% of entry credit
_DELTA_STOP = Decimal("0.35")          # |delta| ≥ 0.35
_DELTA_WARN = Decimal("0.25")          # |delta| ≥ 0.25
_TIME_STOP_DTE = 21                    # DTE ≤ 21
_ROLL_DTE = 5                          # DTE ≤ 5


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
        """Evaluate exit and roll signals for all open short-put positions.

        Filters positions to ``strategy_name == "paper_csp_nifty_v1"`` and
        ``net_qty < 0`` (short).  Returns ``[]`` when no open positions exist.

        Multiple signals may fire simultaneously; callers should not assume
        exclusivity.

        Args:
            market: Current Nifty 50 option chain snapshot.
            positions: All open paper positions (may include other strategies).

        Returns:
            List of detected SignalEvents; empty list when nothing to act on.
        """
        events: list[SignalEvent] = []

        for pos in positions:
            if pos.strategy_name != self.strategy_name:
                continue
            if pos.net_qty >= 0:
                continue  # only short legs trigger signals

            entry_credit = pos.avg_sell_price
            put_leg = self._find_put_leg(market, pos.instrument_key)
            expiry = self._parse_expiry(pos.instrument_key)
            dte = (expiry - date.today()).days if expiry is not None else None

            # ── DTE signals ──────────────────────────────────────────────────
            if dte is not None:
                if dte <= _TIME_STOP_DTE:
                    events.append(
                        SignalEvent(
                            event_type="TIME_STOP",
                            severity="ACTION",
                            description=(
                                f"DTE {dte} ≤ {_TIME_STOP_DTE} — time stop triggered"
                            ),
                            payload={"dte": dte, "leg_role": pos.leg_role},
                        )
                    )
                if dte <= _ROLL_DTE:
                    events.append(
                        SignalEvent(
                            event_type="ROLL_DUE_DTE",
                            severity="WARN",
                            description=f"DTE {dte} ≤ {_ROLL_DTE} — consider rolling",
                            payload={"dte": dte, "leg_role": pos.leg_role},
                        )
                    )

            # ── Delta signals ─────────────────────────────────────────────────
            if put_leg is not None:
                abs_delta = abs(put_leg.delta)
                if abs_delta >= _DELTA_STOP:
                    events.append(
                        SignalEvent(
                            event_type="DELTA_STOP",
                            severity="ACTION",
                            description=(
                                f"|delta| {abs_delta} ≥ {_DELTA_STOP} — delta stop triggered"
                            ),
                            payload={
                                "delta": str(put_leg.delta),
                                "leg_role": pos.leg_role,
                            },
                        )
                    )
                if abs_delta >= _DELTA_WARN:
                    events.append(
                        SignalEvent(
                            event_type="DELTA_WARN",
                            severity="WARN",
                            description=(
                                f"|delta| {abs_delta} ≥ {_DELTA_WARN} — delta warning"
                            ),
                            payload={
                                "delta": str(put_leg.delta),
                                "leg_role": pos.leg_role,
                            },
                        )
                    )

            # ── Mark-based signals ────────────────────────────────────────────
            if put_leg is not None and entry_credit > Decimal("0"):
                mark = put_leg.ltp
                pct = mark / entry_credit
                if pct <= _PROFIT_TARGET_PCT:
                    events.append(
                        SignalEvent(
                            event_type="PROFIT_TARGET",
                            severity="ACTION",
                            description=(
                                f"Mark {mark} ≤ {int(_PROFIT_TARGET_PCT * 100)}%"
                                f" of entry credit {entry_credit}"
                            ),
                            payload={
                                "mark": str(mark),
                                "entry_credit": str(entry_credit),
                                "pct_captured": str(
                                    (Decimal("1") - pct).quantize(Decimal("0.01"))
                                ),
                                "leg_role": pos.leg_role,
                            },
                        )
                    )
                if pct >= _LOSS_STOP_PCT:
                    events.append(
                        SignalEvent(
                            event_type="LOSS_STOP",
                            severity="ACTION",
                            description=(
                                f"Mark {mark} ≥ {int(_LOSS_STOP_PCT * 100)}%"
                                f" of entry credit {entry_credit}"
                            ),
                            payload={
                                "mark": str(mark),
                                "entry_credit": str(entry_credit),
                                "leg_role": pos.leg_role,
                            },
                        )
                    )
                if pct <= _DECAY_WARN_PCT:
                    events.append(
                        SignalEvent(
                            event_type="ROLL_DUE_DECAY",
                            severity="WARN",
                            description=(
                                f"Mark {mark} ≤ {int(_DECAY_WARN_PCT * 100)}%"
                                f" of entry credit {entry_credit} — consider rolling"
                            ),
                            payload={
                                "mark": str(mark),
                                "entry_credit": str(entry_credit),
                                "leg_role": pos.leg_role,
                            },
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
            except Exception:
                pass

        # Fallback: scan for first PE with non-zero LTP
        for strike_data in market.strikes.values():
            if strike_data.pe is not None and strike_data.pe.ltp > Decimal("0"):
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

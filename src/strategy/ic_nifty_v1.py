"""IronCondorV1 — backbone-compatible Iron Condor strategy for Nifty 50.

Implements PaperStrategy protocol so StrategyMonitor can auto-detect exit
signals for the paper_ic_nifty_v1 strategy.  Entry remains manual via
``scripts/paper_ic_entry.py`` (future script — not in this phase).

Signal table
------------
| Event type    | Severity | Trigger                                        |
|---------------|----------|------------------------------------------------|
| PROFIT_TARGET | ACTION   | combined mark ≤ 50% of entry credit            |
| LOSS_STOP     | ACTION   | combined mark ≥ 2.0× entry credit              |
| DELTA_STOP    | ACTION   | either short leg |delta| ≥ 0.35                |
| TIME_STOP     | ACTION   | DTE ≤ 14                                       |
| DELTA_WARN    | WARN     | either short leg |delta| ≥ 0.25                |
| DTE_WARN      | INFO     | DTE ≤ 21                                       |

Council ruling (2026-05-02): no adjustments in v1.  ``apply_action`` only
accepts CLOSE_FULL, CLOSE_CALL_SPREAD, CLOSE_PUT_SPREAD.  Any other
action_type raises ValueError immediately.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

import structlog

from src.models.options import OptionChain, OptionLeg
from src.paper.models import PaperPosition
from src.strategy.protocol import ApprovedAction, SignalEvent

log = structlog.get_logger(__name__)

# ── Regexes ───────────────────────────────────────────────────────────────────

# Matches keys like "NSE_FO|NIFTY29MAY2026PE" → group 1 = "29MAY2026", group 2 = "PE"/"CE"
_EXPIRY_RE = re.compile(
    r"NSE_FO\|NIFTY(\d{2}[A-Za-z]{3}\d{4})(PE|CE)",
    re.IGNORECASE,
)

# Matches keys like "NSE_FO|NIFTY23000PE" or "NSE_FO|NIFTY23000CE"
_STRIKE_RE = re.compile(r"NIFTY(\d+)(PE|CE)", re.IGNORECASE)

# ── Thresholds ────────────────────────────────────────────────────────────────

_PROFIT_TARGET_PCT = Decimal("0.50")  # combined mark ≤ 50% of entry credit
_LOSS_STOP_PCT = Decimal("2.0")  # combined mark ≥ 2.0× entry credit
_DELTA_STOP = Decimal("0.35")  # |delta| ≥ 0.35 on either short leg
_DELTA_WARN = Decimal("0.25")  # |delta| ≥ 0.25 on either short leg
_TIME_STOP_DTE = 14  # DTE ≤ 14
_DTE_WARN = 21  # DTE ≤ 21

# ── Leg role sets ─────────────────────────────────────────────────────────────

_SHORT_ROLES = {"short_call", "short_put"}
_LONG_ROLES = {"long_call_hedge", "long_put_hedge"}
_ALL_ROLES = _SHORT_ROLES | _LONG_ROLES

# ── Allowed action types (council ruling: no adjustments in v1) ───────────────

_ALLOWED_ACTIONS = {"CLOSE_FULL", "CLOSE_CALL_SPREAD", "CLOSE_PUT_SPREAD"}


class IronCondorV1:
    """Backbone-compatible wrapper for the paper_ic_nifty_v1 strategy.

    Registers with StrategyMonitor to emit exit signals on every tick.
    The strategy name must match the ``strategy_name`` column used by
    ``record_paper_trade.py`` when recording IC trades.

    No adjustments are permitted in v1 — council mandate (2026-05-02).
    """

    strategy_name: str = "paper_ic_nifty_v1"

    # ── PaperStrategy protocol ────────────────────────────────────────────────

    async def check_signals(
        self,
        market: OptionChain,
        positions: list[PaperPosition],
    ) -> list[SignalEvent]:
        """Evaluate exit signals for the open Iron Condor position.

        Filters positions to ``strategy_name == "paper_ic_nifty_v1"``.
        Returns ``[]`` when no IC positions exist.  All four legs are
        evaluated together; P&L signals are based on the combined mark.

        Args:
            market: Current Nifty 50 option chain snapshot.
            positions: All open paper positions (may include other strategies).

        Returns:
            List of detected SignalEvents; empty list when nothing to act on.
        """
        ic_positions = [p for p in positions if p.strategy_name == self.strategy_name]
        if not ic_positions:
            return []

        events: list[SignalEvent] = []

        # ── DTE (parse from any leg — all share the same expiry) ─────────────
        expiry = next(
            (self._parse_expiry(p.instrument_key) for p in ic_positions),
            None,
        )
        dte = (expiry - date.today()).days if expiry is not None else None

        if dte is not None:
            if dte <= _TIME_STOP_DTE:
                events.append(
                    SignalEvent(
                        event_type="TIME_STOP",
                        severity="ACTION",
                        description=f"DTE {dte} ≤ {_TIME_STOP_DTE} — time stop triggered",
                        payload={"dte": dte},
                    )
                )
            if dte <= _DTE_WARN:
                events.append(
                    SignalEvent(
                        event_type="DTE_WARN",
                        severity="INFO",
                        description=f"DTE {dte} ≤ {_DTE_WARN} — approaching expiry",
                        payload={"dte": dte},
                    )
                )

        # ── Delta signals (short legs only) ───────────────────────────────────
        short_legs = [p for p in ic_positions if p.leg_role in _SHORT_ROLES]
        for pos in short_legs:
            opt_leg = self._find_leg(market, pos.instrument_key)
            if opt_leg is None:
                continue
            abs_delta = abs(opt_leg.delta)
            if abs_delta >= _DELTA_STOP:
                events.append(
                    SignalEvent(
                        event_type="DELTA_STOP",
                        severity="ACTION",
                        description=(
                            f"{pos.leg_role} |delta| {abs_delta} ≥ {_DELTA_STOP}"
                            " — delta stop triggered"
                        ),
                        payload={
                            "leg_role": pos.leg_role,
                            "delta": str(opt_leg.delta),
                        },
                    )
                )
            if abs_delta >= _DELTA_WARN:
                events.append(
                    SignalEvent(
                        event_type="DELTA_WARN",
                        severity="WARN",
                        description=(
                            f"{pos.leg_role} |delta| {abs_delta} ≥ {_DELTA_WARN} — delta warning"
                        ),
                        payload={
                            "leg_role": pos.leg_role,
                            "delta": str(opt_leg.delta),
                        },
                    )
                )

        # ── Combined mark signals ─────────────────────────────────────────────
        combined_mark, entry_credit = self._compute_combined_pnl(market, ic_positions)
        if combined_mark is not None and entry_credit > Decimal("0"):
            pct = combined_mark / entry_credit
            if pct <= _PROFIT_TARGET_PCT:
                events.append(
                    SignalEvent(
                        event_type="PROFIT_TARGET",
                        severity="ACTION",
                        description=(
                            f"Combined mark {combined_mark} ≤ "
                            f"{int(_PROFIT_TARGET_PCT * 100)}% of entry credit "
                            f"{entry_credit}"
                        ),
                        payload={
                            "combined_mark": str(combined_mark),
                            "entry_credit": str(entry_credit),
                            "pct_remaining": str(pct.quantize(Decimal("0.01"))),
                        },
                    )
                )
            if pct >= _LOSS_STOP_PCT:
                events.append(
                    SignalEvent(
                        event_type="LOSS_STOP",
                        severity="ACTION",
                        description=(
                            f"Combined mark {combined_mark} ≥ "
                            f"{int(_LOSS_STOP_PCT * 100)}% of entry credit "
                            f"{entry_credit}"
                        ),
                        payload={
                            "combined_mark": str(combined_mark),
                            "entry_credit": str(entry_credit),
                            "pct_of_credit": str(pct.quantize(Decimal("0.01"))),
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

        Summarises: call spread delta, put spread delta, combined credit,
        mark-to-market, DTE, IVR (not yet wired — logged as N/A), Nifty spot.

        Args:
            event: The signal event that triggered the context request.
            market: Current Nifty 50 option chain snapshot.
            positions: All open paper positions.

        Returns:
            Multi-line plain-text context string; no HTML markup.
        """
        ic_positions = [p for p in positions if p.strategy_name == self.strategy_name]
        expiry = next((self._parse_expiry(p.instrument_key) for p in ic_positions), None)
        dte = (expiry - date.today()).days if expiry is not None else None
        combined_mark, entry_credit = self._compute_combined_pnl(market, ic_positions)

        lines: list[str] = [
            f"Strategy: {self.strategy_name}",
            f"Signal: {event.event_type} ({event.severity})",
            f"Nifty spot: {market.underlying_spot}",
            f"DTE: {dte if dte is not None else 'unavailable'}",
            "IVR: N/A (not yet wired)",
            f"Entry credit: {entry_credit}",
            f"Combined mark: {combined_mark if combined_mark is not None else 'unavailable'}",
        ]

        for pos in ic_positions:
            opt_leg = self._find_leg(market, pos.instrument_key)
            lines.append(f"Leg: {pos.leg_role} | key: {pos.instrument_key}")
            if opt_leg is not None:
                lines.append(f"  Delta: {opt_leg.delta}  IV: {opt_leg.iv}  LTP: {opt_leg.ltp}")
            else:
                lines.append("  Chain lookup: unavailable")

        if not ic_positions:
            lines.append("No open IC positions found.")

        return "\n".join(lines)

    async def apply_action(
        self,
        positions: list[PaperPosition],
        action: ApprovedAction,
    ) -> list[PaperPosition]:
        """Validate and apply an approved action.

        Only ``CLOSE_FULL``, ``CLOSE_CALL_SPREAD``, and ``CLOSE_PUT_SPREAD``
        are accepted.  Any other action_type raises ``ValueError`` — the spec
        forbids adjustments in v1 (council ruling 2026-05-02).

        Args:
            positions: Current open paper positions.
            action: Approved action; must have an allowed action_type.

        Returns:
            Updated positions with closed legs filtered out.

        Raises:
            ValueError: When ``action_type`` is not in the allowed set.
        """
        if action.action_type not in _ALLOWED_ACTIONS:
            raise ValueError(
                f"IronCondorV1 does not permit {action.action_type!r} — "
                f"v1 allows only: {sorted(_ALLOWED_ACTIONS)}. "
                "Adjustments are deferred to IC v2."
            )
        closed: set[str] = set(action.legs_to_close)
        log.info(
            "ic_nifty_v1.apply_action",
            action_type=action.action_type,
            legs_to_close=list(closed),
        )
        return [p for p in positions if p.leg_role not in closed]

    # ── Private helpers ───────────────────────────────────────────────────────

    def _find_leg(self, market: OptionChain, instrument_key: str) -> OptionLeg | None:
        """Locate a CE or PE leg in the chain for the given instrument key.

        Parses the strike and option type (CE/PE) from ``instrument_key``.
        Returns ``None`` when the key is unrecognised or the strike is absent
        from the chain snapshot.

        Args:
            market: Current option chain.
            instrument_key: Position's Upstox instrument key.

        Returns:
            Matching ``OptionLeg``, or ``None`` when unavailable.
        """
        m = _STRIKE_RE.search(instrument_key)
        if not m:
            log.warning(
                "ic_nifty_v1.strike_parse_failed",
                instrument_key=instrument_key,
            )
            return None

        try:
            strike = Decimal(m.group(1))
        except InvalidOperation:
            log.warning(
                "ic_nifty_v1.strike_decimal_failed",
                instrument_key=instrument_key,
            )
            return None

        option_type = m.group(2).upper()
        strike_data = market.strikes.get(strike)
        if strike_data is None:
            return None

        return strike_data.ce if option_type == "CE" else strike_data.pe

    def _compute_combined_pnl(
        self,
        market: OptionChain,
        ic_positions: list[PaperPosition],
    ) -> tuple[Decimal | None, Decimal]:
        """Compute the combined current mark and entry credit for the IC.

        Combined mark = sum of short-leg LTPs - sum of long-leg LTPs.
        This is the cost to close the entire IC position at current prices.

        Entry credit = sum of short avg_sell_prices - sum of long avg_costs.

        Returns ``(None, entry_credit)`` when any leg's chain data is missing
        — partial mark is not meaningful for P&L gating decisions.

        Args:
            market: Current option chain snapshot.
            ic_positions: All IC positions for this strategy.

        Returns:
            Tuple of (combined_mark or None, entry_credit).
        """
        entry_credit = Decimal("0")
        combined_mark = Decimal("0")
        mark_available = True

        for pos in ic_positions:
            opt_leg = self._find_leg(market, pos.instrument_key)

            if pos.leg_role in _SHORT_ROLES:
                entry_credit += pos.avg_sell_price
                if opt_leg is not None:
                    combined_mark += opt_leg.ltp
                else:
                    mark_available = False
            elif pos.leg_role in _LONG_ROLES:
                entry_credit -= pos.avg_cost
                if opt_leg is not None:
                    combined_mark -= opt_leg.ltp
                else:
                    mark_available = False

        return (combined_mark if mark_available else None, entry_credit)

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

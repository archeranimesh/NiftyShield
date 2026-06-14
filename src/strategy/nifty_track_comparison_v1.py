"""NiftyTrackComparisonV1 — backbone integration for the 3-Track Nifty Comparison.

Covers all three tracks (spot / futures / proxy) as a single registered strategy.
Emits WARN events only; rolls remain manual via ``paper_3track_overlay_roll.py``.
``apply_action`` is a documented no-op.

Signal table
------------
| Event type     | Severity | Trigger                                       |
|----------------|----------|-----------------------------------------------|
| ROLL_DUE_DTE   | WARN     | any overlay leg with DTE ≤ 5                  |
| ROLL_DUE_DECAY | WARN     | any short overlay premium ≤ 25% of entry      |
| OVERLAY_EXPIRED| WARN     | overlay expiry has passed with no roll         |

Overlay legs are identified by ``leg_role.startswith("overlay_")``.
Base legs (``base_etf``, ``base_futures``, ``base_ditm_call``) are not evaluated.

Strategy spec: docs/strategies/nifty_track_comparison_v1.md
"""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

import structlog

from src.market_calendar.holidays import market_today
from src.models.options import OptionChain, OptionLeg
from src.paper.models import PaperPosition
from src.strategy.protocol import ApprovedAction, SignalEvent

log = structlog.get_logger(__name__)

# ── Regex ─────────────────────────────────────────────────────────────────────

# Matches keys like "NSE_FO|NIFTY29MAY2026PE" → group 1 = "29MAY2026"
_EXPIRY_RE = re.compile(
    r"NSE_FO\|NIFTY(\d{2}[A-Za-z]{3}\d{4})(PE|CE)",
    re.IGNORECASE,
)

# Matches keys like "NSE_FO|NIFTY23000PE" → group 1 = "23000"
_STRIKE_RE = re.compile(r"NIFTY(\d+)(PE|CE)", re.IGNORECASE)

# ── Thresholds ────────────────────────────────────────────────────────────────

_ROLL_DTE = 5  # DTE ≤ 5 → ROLL_DUE_DTE
_DECAY_WARN_PCT = Decimal("0.25")  # remaining premium ≤ 25% of entry → ROLL_DUE_DECAY


class NiftyTrackComparisonV1:
    """Backbone wrapper for the 3-Track Nifty Long Instrument Comparison.

    Monitors overlay legs across all three tracks and emits WARN signals when
    a roll is due. All actual rolls are executed manually via
    ``paper_3track_overlay_roll.py``.

    Registered under the umbrella ``strategy_name`` below; the per-track
    strategy namespaces in ``TRACK_STRATEGY_NAMES`` are filtered internally.
    """

    strategy_name: str = "paper_nifty_3track_v1"

    TRACK_STRATEGY_NAMES: list[str] = [
        "paper_nifty_spot",
        "paper_nifty_futures",
        "paper_nifty_proxy",
    ]

    # ── PaperStrategy protocol ────────────────────────────────────────────────

    async def check_signals(
        self,
        market: OptionChain,
        positions: list[PaperPosition],
    ) -> list[SignalEvent]:
        """Evaluate overlay legs across all three tracks and emit WARN signals.

        Filters to positions whose ``strategy_name`` is in
        ``TRACK_STRATEGY_NAMES`` and whose ``leg_role`` starts with
        ``"overlay_"``.  Base legs are never evaluated.

        Returns ``[]`` when no overlay legs exist.

        Args:
            market: Current Nifty 50 option chain snapshot (used for LTP lookup).
            positions: All open paper positions (may include other strategies).

        Returns:
            List of WARN SignalEvents; empty list when no overlays are open.
        """
        events: list[SignalEvent] = []
        today = market_today()

        for pos in positions:
            if pos.strategy_name not in self.TRACK_STRATEGY_NAMES:
                continue
            if not pos.leg_role.startswith("overlay_"):
                continue

            expiry = self._parse_expiry(pos.instrument_key)
            dte: int | None = (expiry - today).days if expiry is not None else None

            payload_base = {
                "track": pos.strategy_name,
                "leg_role": pos.leg_role,
                "dte": dte,
            }

            # ── Expired overlay (no roll recorded) ───────────────────────────
            if expiry is not None and expiry < today:
                events.append(
                    SignalEvent(
                        event_type="OVERLAY_EXPIRED",
                        severity="WARN",
                        description=(
                            f"Overlay {pos.leg_role} on {pos.strategy_name} "
                            f"expired {expiry} — roll not recorded"
                        ),
                        payload={**payload_base, "expiry": expiry.isoformat()},
                    )
                )
                continue  # no further checks for an already-expired leg

            # ── DTE check ────────────────────────────────────────────────────
            if dte is not None and dte <= _ROLL_DTE:
                events.append(
                    SignalEvent(
                        event_type="ROLL_DUE_DTE",
                        severity="WARN",
                        description=(
                            f"Overlay {pos.leg_role} on {pos.strategy_name} "
                            f"DTE {dte} ≤ {_ROLL_DTE} — roll due"
                        ),
                        payload=payload_base,
                    )
                )

            # ── Premium decay check (short overlay legs only) ─────────────────
            if pos.net_qty < 0:
                entry_credit = pos.avg_sell_price
                if entry_credit > Decimal("0"):
                    option_leg = self._find_option_leg(market, pos.instrument_key)
                    if option_leg is not None:
                        mark = option_leg.ltp
                        pct_remaining = mark / entry_credit
                        if pct_remaining <= _DECAY_WARN_PCT:
                            events.append(
                                SignalEvent(
                                    event_type="ROLL_DUE_DECAY",
                                    severity="WARN",
                                    description=(
                                        f"Overlay {pos.leg_role} on {pos.strategy_name} "
                                        f"mark {mark} ≤ {int(_DECAY_WARN_PCT * 100)}% "
                                        f"of entry {entry_credit} — consider rolling"
                                    ),
                                    payload={
                                        **payload_base,
                                        "mark": str(mark),
                                        "entry_credit": str(entry_credit),
                                        "pct_remaining": str(
                                            pct_remaining.quantize(Decimal("0.01"))
                                        ),
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
        """Build a plain-text context block summarising the triggering overlay.

        Returns a structured string with track name, leg role, DTE remaining,
        current premium vs entry premium, and % captured.

        Args:
            event: The signal event that triggered the context request.
            market: Current Nifty 50 option chain snapshot.
            positions: All open paper positions.

        Returns:
            Multi-line plain-text context string; no HTML markup.
        """
        today = market_today()
        lines: list[str] = [
            f"Strategy: {self.strategy_name}",
            f"Signal: {event.event_type} ({event.severity})",
            f"Track: {event.payload.get('track', 'unknown')}",
            f"Nifty spot: {market.underlying_spot}",
        ]

        track = event.payload.get("track")
        leg_role = event.payload.get("leg_role")

        overlay_legs = [
            p
            for p in positions
            if p.strategy_name == track
            and p.leg_role == leg_role
            and p.leg_role.startswith("overlay_")
        ]

        for pos in overlay_legs:
            expiry = self._parse_expiry(pos.instrument_key)
            dte = (expiry - today).days if expiry is not None else None
            option_leg = self._find_option_leg(market, pos.instrument_key)
            entry_credit = pos.avg_sell_price

            lines.append(f"Leg: {pos.leg_role} | key: {pos.instrument_key}")
            lines.append(f"  DTE          : {dte if dte is not None else 'unavailable'}")
            if expiry is not None:
                lines.append(f"  Expiry       : {expiry.isoformat()}")
            lines.append(f"  Entry credit : {entry_credit}")

            if option_leg is not None:
                mark = option_leg.ltp
                if entry_credit > Decimal("0"):
                    pct_remaining = (mark / entry_credit * 100).quantize(Decimal("0.1"))
                    pct_captured = ((Decimal("1") - mark / entry_credit) * 100).quantize(
                        Decimal("0.1")
                    )
                    lines.append(f"  Current mark : {mark} ({pct_remaining}% of entry)")
                    lines.append(f"  % captured   : {pct_captured}%")
                else:
                    lines.append(f"  Current mark : {mark}")
            else:
                lines.append("  Current mark : unavailable (chain lookup failed)")

        if not overlay_legs:
            lines.append("No matching overlay leg found.")

        return "\n".join(lines)

    async def apply_action(
        self,
        positions: list[PaperPosition],
        action: ApprovedAction,
    ) -> list[PaperPosition]:
        """No-op — rolls for 3-track overlays are executed manually.

        This strategy emits WARN events only and has no automated action flow.
        Rolls are performed via ``scripts/strategies/three_track/paper_3track_overlay_roll.py``.

        Calling ``apply_action`` is a no-op: positions are returned unchanged.

        Args:
            positions: Current open paper positions.
            action: Approved action (ignored — no automated rolls in this strategy).

        Returns:
            ``positions`` unchanged.
        """
        log.info(
            "nifty_track_comparison_v1.apply_action.noop",
            action_type=action.action_type,
            note="Rolls are manual via paper_3track_overlay_roll.py",
        )
        return positions

    # ── Private helpers ───────────────────────────────────────────────────────

    def _parse_expiry(self, instrument_key: str) -> date | None:
        """Extract the option expiry date from an instrument key.

        Handles keys like ``"NSE_FO|NIFTY29MAY2026PE"`` → ``date(2026, 5, 29)``.
        Returns ``None`` for numeric or unrecognised key formats.

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

    def _find_option_leg(self, market: OptionChain, instrument_key: str) -> OptionLeg | None:
        """Locate the chain leg (CE or PE) matching the position's instrument key.

        Tries a direct strike lookup by parsing ``instrument_key``.
        Returns the CE leg for calls (``overlay_cc``, ``overlay_collar_call``)
        and the PE leg for puts (``overlay_pp``, ``overlay_collar_put``).
        Returns ``None`` when no parseable strike is found or the strike is absent
        from the chain snapshot.

        Args:
            market: Current option chain.
            instrument_key: Position's Upstox instrument key.

        Returns:
            Matching ``OptionLeg``, or ``None`` when unavailable.
        """
        m = _STRIKE_RE.search(instrument_key)
        if not m:
            return None

        try:
            strike = Decimal(m.group(1))
        except InvalidOperation:
            log.warning(
                "nifty_track_comparison_v1.strike_parse_failed",
                instrument_key=instrument_key,
            )
            return None

        option_type = m.group(2).upper()
        strike_data = market.strikes.get(strike)
        if strike_data is None:
            return None

        return strike_data.ce if option_type == "CE" else strike_data.pe

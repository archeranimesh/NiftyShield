"""NiftyTrackComparisonV1 — backbone integration for the 3-Track Nifty Comparison.

Covers all three tracks (spot / futures / proxy) as a single registered strategy.
Emits WARN and ACTION events; rolls remain manual via ``paper_3track_overlay_roll.py``.
``apply_action`` is a documented no-op.

Signal table
------------
| Event type     | Severity | Trigger                                              |
|----------------|----------|------------------------------------------------------|
| ROLL_ELIGIBLE  | ACTION   | overlay DTE ≤ 5 and base DTE > 10                   |
| ROLL_BASE_FIRST| WARN     | overlay DTE ≤ 5 but base DTE ≤ 10 (roll base first) |
| ROLL_DUE_DTE   | WARN     | overlay DTE 6–10 (advance notice)                    |
| ROLL_DUE_DECAY | WARN     | any short overlay premium ≤ 25% of entry             |
| OVERLAY_EXPIRED| WARN     | overlay expiry has passed with no roll               |

Overlay legs are identified by ``leg_role.startswith("overlay_")``.
Base legs (``base_etf``, ``base_futures``, ``base_ditm_call``) are not evaluated.

Strategy spec: docs/strategies/nifty_track_comparison_v1.md
"""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

import structlog

from src.market_calendar.holidays import market_today
from src.models.options import OptionChain, OptionLeg
from src.paper.models import PaperPosition
from src.strategy.exit_signals import ExitSignalEngine
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

_ROLL_ELIGIBLE_DTE = 5  # DTE ≤ 5 → delegate to ExitSignalEngine.evaluate_roll_overlay
_ROLL_DUE_DTE_MAX = 10  # DTE 6–10 → ROLL_DUE_DTE WARN (advance notice)
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

    def __init__(
        self,
        store: Any = None,
        notifier: Any = None,
        broker: Any = None,
        **kwargs: Any,
    ) -> None:
        """Initialise NiftyTrackComparisonV1."""
        self._store = store
        self._notifier = notifier
        self._broker = broker

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

            is_overlay = pos.leg_role.startswith("overlay_")
            is_proxy_base = pos.leg_role == "base_ditm_call"
            if not (is_overlay or is_proxy_base):
                continue

            expiry = self._parse_expiry(pos.instrument_key)
            dte: int | None = (expiry - today).days if expiry is not None else None

            payload_base = {
                "track": pos.strategy_name,
                "leg_role": pos.leg_role,
                "dte": dte,
            }

            if is_proxy_base:
                option_leg = self._find_option_leg(market, pos.instrument_key)
                if option_leg is None:
                    log.warning(
                        "nifty_track_comparison_v1.check_signals.proxy_option_leg_missing",
                        leg_role=pos.leg_role,
                        instrument_key=pos.instrument_key,
                    )
                    continue

                if option_leg.delta is None:
                    log.warning(
                        "nifty_track_comparison_v1.check_signals.proxy_delta_missing",
                        leg_role=pos.leg_role,
                        instrument_key=pos.instrument_key,
                    )
                    continue

                current_delta = float(option_leg.delta)
                current_mark = option_leg.ltp
                days_below_critical = 0
                if self._store is not None:
                    days_below_critical = self._store.get_proxy_delta_breach_count(
                        pos.strategy_name
                    )

                val_dte = dte if dte is not None else 999
                proxy_results = ExitSignalEngine.evaluate_proxy_delta(
                    current_delta=current_delta,
                    current_mark=current_mark,
                    dte=val_dte,
                    days_below_critical=days_below_critical,
                )

                if self._store is not None:
                    if current_delta < 0.40:
                        self._store.set_proxy_delta_breach_count(
                            pos.strategy_name, days_below_critical + 1
                        )
                    else:
                        self._store.set_proxy_delta_breach_count(pos.strategy_name, 0)

                for res in proxy_results:
                    payload = {
                        **payload_base,
                        "delta": str(option_leg.delta),
                        "mark": str(option_leg.ltp),
                    }
                    if res.severity == "ACTION":
                        payload["valid_actions"] = ["RECORD_REENTRY"]

                    events.append(
                        SignalEvent(
                            event_type=res.exit_signal,
                            severity=res.severity,
                            description=res.notes or res.exit_signal,
                            payload=payload,
                        )
                    )
                continue

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
            if dte is not None and dte <= _ROLL_ELIGIBLE_DTE:
                # DTE ≤ 5: delegate to ExitSignalEngine for structured roll decision
                base_dte = self._get_base_dte(positions, pos.strategy_name, today)
                atm_strike = int(round(float(market.underlying_spot) / 50) * 50)
                try:
                    roll_results = ExitSignalEngine.evaluate_roll_overlay(
                        leg_role=pos.leg_role,
                        dte=dte,
                        base_dte=base_dte,
                        atm_strike=atm_strike,
                    )
                except ValueError:
                    # Unknown overlay role — fall back to generic advance warning
                    roll_results = []
                    events.append(
                        SignalEvent(
                            event_type="ROLL_DUE_DTE",
                            severity="WARN",
                            description=(
                                f"Overlay {pos.leg_role} on {pos.strategy_name} "
                                f"DTE {dte} ≤ {_ROLL_ELIGIBLE_DTE} — roll due"
                            ),
                            payload=payload_base,
                        )
                    )
                for res in roll_results:
                    if res.exit_signal == "ROLL_ELIGIBLE":
                        events.append(
                            SignalEvent(
                                event_type="ROLL_ELIGIBLE",
                                severity="ACTION",
                                description=(
                                    f"Overlay {pos.leg_role} on {pos.strategy_name} "
                                    f"DTE {dte} ≤ {_ROLL_ELIGIBLE_DTE} — roll eligible"
                                ),
                                payload={**payload_base, "valid_actions": ["RECORD_ROLL"]},
                            )
                        )
                    elif res.exit_signal == "ROLL_BASE_FIRST":
                        events.append(
                            SignalEvent(
                                event_type="ROLL_BASE_FIRST",
                                severity="WARN",
                                description=(
                                    f"Overlay {pos.leg_role} on {pos.strategy_name} "
                                    f"DTE {dte} — roll base first (base DTE {base_dte} ≤ 10)"
                                ),
                                payload=payload_base,
                            )
                        )
            elif dte is not None and dte <= _ROLL_DUE_DTE_MAX:
                # DTE 6–10: advance notice — manual roll due soon
                events.append(
                    SignalEvent(
                        event_type="ROLL_DUE_DTE",
                        severity="WARN",
                        description=(
                            f"Overlay {pos.leg_role} on {pos.strategy_name} "
                            f"DTE {dte} ≤ {_ROLL_DUE_DTE_MAX} — roll due soon"
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

    def _get_base_dte(
        self,
        positions: list[PaperPosition],
        strategy_name: str,
        today: date,
    ) -> int:
        """Return DTE of the base leg for the given track.

        Scans positions for a non-overlay leg in ``strategy_name`` with a
        parseable expiry date.  Returns 999 when no base leg is found or the
        base has no expiry (e.g. base_etf — ETF has no maturity).

        Args:
            positions: All open paper positions.
            strategy_name: Track strategy namespace to search.
            today: Reference date for DTE computation.

        Returns:
            Integer DTE of the base leg, or 999 when unavailable.
        """
        for pos in positions:
            if pos.strategy_name != strategy_name:
                continue
            if pos.leg_role.startswith("overlay_"):
                continue
            expiry = self._parse_expiry(pos.instrument_key)
            if expiry is not None:
                return (expiry - today).days
        return 999  # base has no expiry (ETF) or base not in positions

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

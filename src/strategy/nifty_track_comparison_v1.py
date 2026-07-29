"""NiftyTrackComparisonV1 — backbone integration for the 3-Track Nifty Comparison.

Covers all three tracks (spot / futures / proxy) as a single registered strategy.
Emits WARN and ACTION events; overlay rolls are executed via ``apply_action`` when
a replacement target is available, or remain WARN-only when no target can be found.

Signal table
------------
| Event type     | Severity         | Trigger                                          |
|----------------|------------------|--------------------------------------------------|
| ROLL_ELIGIBLE  | ACTION           | overlay DTE ≤ 5 and base DTE > 10               |
| ROLL_BASE_FIRST| WARN             | overlay DTE ≤ 5 but base DTE ≤ 10               |
| ROLL_DUE_DTE   | ACTION or WARN   | overlay DTE 6–10; ACTION when target available   |
| ROLL_DUE_DECAY | ACTION or WARN   | short overlay ≤ 25% of entry; ACTION when target |
| OVERLAY_EXPIRED| WARN             | overlay expiry has passed with no roll           |

Overlay legs are identified by ``leg_role.startswith("overlay_")``.
Base legs (``base_etf``, ``base_futures``, ``base_ditm_call``) are not evaluated.

Strategy spec: docs/strategies/nifty_track_comparison_v1.md
"""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

import structlog

from src.instruments.lookup import InstrumentLookup
from src.market_calendar.holidays import market_today
from src.models.options import OptionChain, OptionLeg
from src.paper.constants import DEFAULT_BOD_PATH
from src.paper.models import PaperPosition
from src.strategy._price_utils import find_option_leg
from src.strategy.exit_signals import ExitSignalEngine
from src.strategy.protocol import ApprovedAction, LegClose, LegSpec, SignalEvent
from src.strategy.roll_utils import find_strike_by_delta

log = structlog.get_logger(__name__)

# ── Regex ─────────────────────────────────────────────────────────────────────

# Matches keys like "NSE_FO|NIFTY29MAY2026PE" → group 1 = "29MAY2026"
_EXPIRY_RE = re.compile(
    r"NSE_FO\|NIFTY(\d{2}[A-Za-z]{3}\d{4})(PE|CE)",
    re.IGNORECASE,
)

# ── Thresholds ────────────────────────────────────────────────────────────────

_ROLL_ELIGIBLE_DTE = 5  # DTE ≤ 5 → delegate to ExitSignalEngine.evaluate_roll_overlay
_ROLL_DUE_DTE_MAX = 10  # DTE 6–10 → ROLL_DUE_DTE WARN (advance notice)
_DECAY_WARN_PCT = Decimal("0.25")  # remaining premium ≤ 25% of entry → ROLL_DUE_DECAY
# Delta parameters for overlay roll target selection (next-expiry chain).
# PP / collar-put: 8–10% OTM put, target 20Δ.
# CC / collar-call: 3–5% OTM call, target 20Δ.
_PP_DELTA_RANGE: tuple[Decimal, Decimal] = (Decimal("0.15"), Decimal("0.25"))
_PP_TARGET_DELTA: Decimal = Decimal("0.20")
_CC_DELTA_RANGE: tuple[Decimal, Decimal] = (Decimal("0.15"), Decimal("0.25"))
_CC_TARGET_DELTA: Decimal = Decimal("0.20")

# Roll action types handled by apply_action.
_ALLOWED_ACTIONS: frozenset[str] = frozenset({"ROLL_OVERLAY", "ROLL_COLLAR"})


def _leg_close_matches(pos: PaperPosition, leg: LegClose) -> bool:
    """Return True when ``leg`` identifies ``pos`` as the position to close.

    Matches on ``leg_role`` always; additionally matches on ``instrument_key``
    when the ``LegClose`` supplies one, so that a roll overlap (two positions
    sharing a ``leg_role`` with different ``instrument_key``s) only removes
    the specific instrument being closed (PG-4h).
    """
    if pos.leg_role != leg.leg_role:
        return False
    if leg.instrument_key is not None:
        return pos.instrument_key == leg.instrument_key
    return True


# Default lot size for Nifty overlay legs (SEBI standard as of 2024).
_NIFTY_LOT_SIZE: int = 75


class NiftyTrackComparisonV1:
    """Backbone wrapper for the 3-Track Nifty Long Instrument Comparison.

    Monitors overlay legs across all three tracks and emits roll signals
    (ROLL_OVERLAY, ROLL_COLLAR) via ``apply_action``; executor handles
    legs_to_open. ``paper_3track_overlay_roll.py`` retired (PA2).

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
        instrument_lookup: InstrumentLookup | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialise NiftyTrackComparisonV1.

        Args:
            store: SQLite-backed store for paper trading records.
            notifier: Notifier for sending Telegram alerts.
            broker: Broker client interface.
            instrument_lookup: Optional pre-built ``InstrumentLookup`` (BOD JSON),
                used by ``find_option_leg`` to resolve real numeric Upstox
                instrument keys that carry no strike/type in the key string
                itself. If not injected, lazily built from ``DEFAULT_BOD_PATH``
                on first use (same pattern as ``PaperStore._resolve_instrument_lookup``).
            **kwargs: Additional keyword arguments.
        """
        self._store = store
        self._notifier = notifier
        self._broker = broker
        self._instrument_lookup = instrument_lookup

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
                log.warning("nifty_track_comparison_v1.bod_lookup_load_failed", error=str(exc))
                return None
        return self._instrument_lookup

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

            payload_base: dict[str, Any] = {
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

                # Default DTE to 999 if parsing fails so premium decay triggers if mark < 0.50 (rather than suppressing it)
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
                # DTE 6–10: advance notice — upgrade to ACTION when a roll target is available.
                target = await self._select_overlay_roll_target(pos.leg_role)
                if target is not None:
                    events.append(
                        SignalEvent(
                            event_type="ROLL_DUE_DTE",
                            severity="ACTION",
                            description=(
                                f"Overlay {pos.leg_role} on {pos.strategy_name} "
                                f"DTE {dte} ≤ {_ROLL_DUE_DTE_MAX} — roll target ready"
                            ),
                            payload={
                                **payload_base,
                                "strategy_name": pos.strategy_name,
                                "suggested_instrument_key": target.instrument_key,
                                "suggested_strike": target.notes,
                                "suggested_expiry": "",
                                "suggested_delta": "",
                                "suggested_mid_price": "",
                                "valid_actions": ["ROLL_OVERLAY"],
                                "legs_to_open": [target],
                            },
                        )
                    )
                else:
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
                            decay_payload: dict[str, object] = {
                                **payload_base,
                                "mark": str(mark),
                                "entry_credit": str(entry_credit),
                                "pct_remaining": str(pct_remaining.quantize(Decimal("0.01"))),
                            }
                            target = await self._select_overlay_roll_target(pos.leg_role)
                            severity: Literal["WARN", "ACTION"]
                            if target is not None:
                                decay_payload["strategy_name"] = pos.strategy_name
                                decay_payload["suggested_instrument_key"] = target.instrument_key
                                decay_payload["suggested_strike"] = target.notes
                                decay_payload["suggested_expiry"] = ""
                                decay_payload["suggested_delta"] = ""
                                decay_payload["suggested_mid_price"] = ""
                                decay_payload["valid_actions"] = ["ROLL_OVERLAY"]
                                decay_payload["legs_to_open"] = [target]
                                severity = "ACTION"
                            else:
                                severity = "WARN"
                            events.append(
                                SignalEvent(
                                    event_type="ROLL_DUE_DECAY",
                                    severity=severity,
                                    description=(
                                        f"Overlay {pos.leg_role} on {pos.strategy_name} "
                                        f"mark {mark} ≤ {int(_DECAY_WARN_PCT * 100)}% "
                                        f"of entry {entry_credit} — consider rolling"
                                    ),
                                    payload=decay_payload,
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
        """Execute ROLL_OVERLAY or ROLL_COLLAR — optimistic in-memory position update.

        Closes legs listed in ``action.legs_to_close`` by removing matching
        positions from the list.  The executor handles all DB writes; this method
        only returns the post-roll in-memory position state.

        ROLL_OVERLAY: one leg closed + one LegSpec in ``legs_to_open``.
        ROLL_COLLAR:  two legs closed (collar_put + collar_call) + two LegSpecs.

        Args:
            positions: Current open paper positions.
            action: Approved action with ``action_type`` in {ROLL_OVERLAY, ROLL_COLLAR}.

        Returns:
            Updated positions list with closed legs removed.

        Raises:
            ValueError: Unknown ``action_type`` or empty ``legs_to_open``.
        """
        if action.action_type not in _ALLOWED_ACTIONS:
            raise ValueError(
                f"NiftyTrackComparisonV1 does not permit {action.action_type!r} — "
                f"allowed: {_ALLOWED_ACTIONS}"
            )
        if not action.legs_to_open:
            raise ValueError(f"{action.action_type} requires at least one leg in legs_to_open")

        # Match on instrument_key when the LegClose supplies one — during a roll
        # overlap two positions can share the same leg_role with different
        # instrument_keys, and leg_role-only matching would incorrectly drop both
        # (PG-4h).  Falls back to leg_role-only matching when instrument_key is
        # None, preserving pre-PG-4a behavior.
        return [
            p
            for p in positions
            if not any(_leg_close_matches(p, leg) for leg in action.legs_to_close)
        ]

    # ── Roll target selection ─────────────────────────────────────────────────

    async def _select_overlay_roll_target(
        self,
        leg_role: str,
    ) -> LegSpec | None:
        """Fetch the next-expiry chain and select a replacement overlay leg.

        Uses the broker client to fetch the next-expiry option chain.  Applies
        ``find_strike_by_delta`` with role-specific delta targets.  Returns
        ``None`` when no broker client is set, the chain fetch fails, or no
        candidate exists within the delta band.

        Track-independent (S2r, 2026-07-29): selection depends only on
        ``leg_role``, never on which track's context it is called from.

        The broker's ``get_option_chain`` may return either a raw Upstox dict
        (production) or an ``OptionChain`` instance (tests / mock brokers).
        Both forms are handled.

        Args:
            leg_role: Overlay leg role being rolled.

        Returns:
            ``LegSpec`` for the replacement leg, or ``None``.
        """
        if self._broker is None:
            return None

        # Determine option type and delta parameters by role.
        if leg_role in ("overlay_pp", "overlay_collar_put"):
            option_type: str = "PE"
            delta_range = _PP_DELTA_RANGE
            target_delta = _PP_TARGET_DELTA
            leg_action: str = "BUY"
        elif leg_role in ("overlay_cc", "overlay_collar_call"):
            option_type = "CE"
            delta_range = _CC_DELTA_RANGE
            target_delta = _CC_TARGET_DELTA
            leg_action = "SELL"
        else:
            log.warning(
                "nifty_track_comparison_v1._select_overlay_roll_target.unknown_role",
                leg_role=leg_role,
            )
            return None

        next_chain = await self._fetch_next_chain()
        if next_chain is None:
            return None

        # Literal cast required by find_strike_by_delta — safe because we set it above.
        ot: Literal["CE", "PE"] = option_type  # type: ignore[assignment]
        leg = find_strike_by_delta(next_chain, ot, delta_range, target_delta)
        if leg is None:
            return None

        # Build instrument key: NSE_FO|NIFTY{DDMMMYYYY}{strike}{CE|PE}
        expiry_str = next_chain.expiry.strftime("%d%b%Y").upper()
        instrument_key = f"NSE_FO|NIFTY{expiry_str}{int(leg.strike)}{option_type}"

        return LegSpec(
            instrument_key=instrument_key,
            action=leg_action,  # type: ignore[arg-type]
            quantity=_NIFTY_LOT_SIZE,
            leg_role=leg_role,
            notes=str(leg.strike),
        )

    async def _fetch_next_chain(self) -> OptionChain | None:
        """Fetch and parse the next-expiry Nifty option chain via the broker.

        Handles two broker return shapes:
        - ``OptionChain`` instance (mock / test brokers) — used directly.
        - Raw Upstox dict with ``"data"`` key — parsed via
          ``parse_upstox_option_chain``.

        Returns ``None`` on any error.
        """
        from src.client.upstox_market import parse_upstox_option_chain

        try:
            raw = await self._broker.get_option_chain(
                "NSE_INDEX|Nifty 50",
                "next",
            )
        except Exception:
            log.warning(
                "nifty_track_comparison_v1._fetch_next_chain.broker_error",
                exc_info=True,
            )
            return None

        if isinstance(raw, OptionChain):
            return raw

        # Production path: raw is the Upstox response list of strike dicts.
        try:
            data = raw if isinstance(raw, list) else []
            if not data:
                return None
            return parse_upstox_option_chain(data)
        except Exception:
            log.warning(
                "nifty_track_comparison_v1._fetch_next_chain.parse_error",
                exc_info=True,
            )
            return None

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

        Delegates to the shared ``find_option_leg`` utility: tries a direct
        regex strike/type parse first (symbolic/test keys), then falls back
        to BOD JSON lookup for real numeric Upstox instrument keys that carry
        no strike/type in the key string itself.

        Args:
            market: Current option chain.
            instrument_key: Position's Upstox instrument key.

        Returns:
            Matching ``OptionLeg``, or ``None`` when unavailable.
        """
        return find_option_leg(instrument_key, market, lookup=self._resolve_instrument_lookup())

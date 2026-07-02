# src/risk/delta_tracker.py
"""Portfolio delta aggregation across open paper positions.

``PortfolioDeltaTracker`` converts a list of ``PaperPosition`` objects into a
``PortfolioDelta`` snapshot expressed in Nifty-equivalent lots.  It is the sole
place where NiftyBees ETF exposure and options/futures delta are combined into a
single directional view.

Delta sign convention
---------------------
Positive lots = net long Nifty exposure (profits if Nifty rises).
Negative lots = net short Nifty exposure (profits if Nifty falls).

Per instrument type:
- **CE / PE** (classified via ``PaperPosition.option_type``, resolved by
  ``PaperStore`` from the offline BOD instrument lookup — see BUG-002/B002.3):
  if a chain-derived delta is supplied via ``position_deltas`` (keyed by
  ``instrument_key``), that value is used as-is — it is expected to already be
  the final signed delta-in-lots for the position (caller has folded in
  ``net_qty``, lot size, and sign convention using the real option delta from
  the chain). If no chain-derived value is available for the key, falls back
  to the approximation ``delta_lots = net_qty / lot_size`` (CE) or
  ``-net_qty / lot_size`` (PE), and logs a WARNING — this approximation prices
  the leg as a full-delta future and is known-imprecise (see BUG-002).
- **Futures** (``option_type == "FUT"``): ``delta_lots = net_qty / lot_size``.
- **NiftyBees ETF** (``NSE_EQ|INF204KB14I2``):
  ``delta_lots = net_qty × avg_cost / (nifty_spot × lot_size)``  (beta = 1.0)
- **Unresolved** (``option_type is None`` or any other value): logs a WARNING
  and contributes zero delta — an unrecognised/legacy instrument_key must
  never be silently misclassified as a full-delta future.

Chain-derived delta sourcing (``position_deltas``)
---------------------------------------------------
Per council ruling 2026-07-02
(``docs/council/2026-07-02_paper-delta-source-architecture.md``, absorbed into
``DECISIONS.md``): this module stays pure/sync/zero-I/O. It never
fetches an option chain itself. The caller (e.g. ``ic_entry_gates.py``, which
already fetches the chain for other entry gates) is responsible for resolving
real option deltas and passing them into ``aggregate_delta`` via
``position_deltas``. Missing/stale/failed chain data at the caller layer must
still fall back to this module's approximation with a WARNING — never a
silent block — per the council's paper-phase fallback policy. Escalating
missing/stale/failed chain data to a hard block is deferred to live-money
deployment and requires a fresh council pass before implementation.

Threshold design — net long only
---------------------------------
Thresholds guard against **net long bias** accumulating across the portfolio.
Unsigned (``abs()``) comparisons are intentionally NOT used: a net-short options
book (e.g. short calls hedging a long NiftyBees position) has negative delta and
does not breach any cap.  Breaches fire only when the signed delta is positive
and exceeds the threshold.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal

from src.paper.constants import NIFTYBEES_KEY
from src.paper.models import PaperPosition
from src.risk.models import PortfolioDelta

logger = logging.getLogger(__name__)

# ── Default thresholds (parameterised via constructor) ────────────────────────

#: Warn when options-only net delta exceeds this many lots.
OPTIONS_WARNING_LOTS: Decimal = Decimal("0.75")
#: Block new entries when options-only net delta exceeds this many lots.
OPTIONS_CAP_LOTS: Decimal = Decimal("1.00")

#: Warn when combined (options + NiftyBees) net delta exceeds this many lots.
COMBINED_WARNING_LOTS: Decimal = Decimal("1.50")
#: Block new entries when combined net delta exceeds this many lots.
COMBINED_CAP_LOTS: Decimal = Decimal("2.00")


class PortfolioDeltaTracker:
    """Aggregate delta across open paper positions and NiftyBees ETF holding.

    Args:
        options_warning: Warning threshold for options-only delta (lots).
        options_cap: Hard cap for options-only delta (lots).
        combined_warning: Warning threshold for combined total delta (lots).
        combined_cap: Hard cap for combined total delta (lots).
    """

    def __init__(
        self,
        options_warning: Decimal = OPTIONS_WARNING_LOTS,
        options_cap: Decimal = OPTIONS_CAP_LOTS,
        combined_warning: Decimal = COMBINED_WARNING_LOTS,
        combined_cap: Decimal = COMBINED_CAP_LOTS,
    ) -> None:
        self._options_warning = options_warning
        self._options_cap = options_cap
        self._combined_warning = combined_warning
        self._combined_cap = combined_cap

    # ── Public API ────────────────────────────────────────────────────────────

    def aggregate_delta(
        self,
        paper_positions: list[PaperPosition],
        nifty_spot: Decimal,
        lot_size: int,
        position_deltas: dict[str, Decimal] | None = None,
    ) -> PortfolioDelta:
        """Compute aggregate portfolio delta from open paper positions.

        Args:
            paper_positions: All open ``PaperPosition`` objects across strategies.
                Obtain via ``PaperStore.get_position`` for each open trade.
            nifty_spot: Current Nifty 50 spot price (used for NiftyBees lot conversion).
            lot_size: Active Nifty lot size (e.g. 65 from ``src.paper.constants``).
            position_deltas: Optional chain-derived delta per position,
                keyed by ``instrument_key``. Values are the final signed
                delta-in-lots for that position (caller has already folded
                in net_qty, lot size, and sign). Positions whose
                ``instrument_key`` is absent from this map fall back to the
                ``net_qty / lot_size`` approximation with a logged WARNING.
                See module docstring for the council-ruled module-boundary
                rationale (``src/risk/`` never fetches a chain itself).

        Returns:
            ``PortfolioDelta`` snapshot with breach flags set according to thresholds.

        Raises:
            ValueError: If ``nifty_spot`` ≤ 0 or ``lot_size`` ≤ 0.
        """
        if nifty_spot <= Decimal(0):
            raise ValueError(f"nifty_spot must be positive, got {nifty_spot}")
        if lot_size <= 0:
            raise ValueError(f"lot_size must be positive, got {lot_size}")

        options_delta = Decimal(0)
        niftybees_delta = Decimal(0)
        lot_size_d = Decimal(lot_size)

        for pos in paper_positions:
            delta = _position_delta(pos, nifty_spot, lot_size_d, position_deltas)
            if pos.instrument_key == NIFTYBEES_KEY:
                niftybees_delta += delta
            else:
                options_delta += delta

        total_delta = options_delta + niftybees_delta

        # Thresholds compare signed delta — negative (net-short) books never breach.
        # See module docstring for design rationale.
        warning_breached = (
            options_delta > self._options_warning or total_delta > self._combined_warning
        )
        cap_breached = options_delta > self._options_cap or total_delta > self._combined_cap

        return PortfolioDelta(
            options_delta_lots=options_delta,
            niftybees_delta_lots=niftybees_delta,
            total_delta_lots=total_delta,
            warning_breached=warning_breached,
            cap_breached=cap_breached,
            as_of=datetime.now(tz=timezone.utc),
        )


# ── Module-level helpers (no instance state required) ─────────────────────────


def _position_delta(
    pos: PaperPosition,
    nifty_spot: Decimal,
    lot_size_d: Decimal,
    position_deltas: dict[str, Decimal] | None = None,
) -> Decimal:
    """Compute signed delta in lots for a single position.

    Classification uses ``pos.option_type`` (resolved by ``PaperStore`` via the
    offline BOD instrument lookup — see BUG-002/B002.3), not substring-matching
    against ``instrument_key`` (real Upstox keys are pure numeric and never
    contain "PE"/"CE"; that was BUG-002's root cause).

    Args:
        pos: Open paper position.
        nifty_spot: Current Nifty 50 spot price.
        lot_size_d: Lot size as ``Decimal`` for arithmetic consistency.
        position_deltas: Optional chain-derived delta per position, keyed by
            ``instrument_key``. See ``PortfolioDeltaTracker.aggregate_delta``
            docstring for the value contract.

    Returns:
        Signed delta in Nifty-equivalent lots.
    """
    key = pos.instrument_key
    net_qty = Decimal(str(pos.net_qty))

    if key == NIFTYBEES_KEY:
        # NiftyBees: convert equity notional to Nifty-equivalent lots.
        # Use avg_cost as price proxy (paper trade entry price).
        return net_qty * pos.avg_cost / (nifty_spot * lot_size_d)

    if pos.option_type in ("PE", "CE"):
        if position_deltas is not None and key in position_deltas:
            return position_deltas[key]

        logger.warning(
            "PortfolioDeltaTracker: no chain-derived delta for %r "
            "(option_type=%s, strategy=%s, leg_role=%s, net_qty=%s) — "
            "falling back to net_qty/lot_size approximation "
            "(BUG-002 known-imprecise path)",
            key,
            pos.option_type,
            pos.strategy_name,
            pos.leg_role,
            pos.net_qty,
        )
        if pos.option_type == "PE":
            # Put options: sign-flip so short put → positive delta.
            return -net_qty / lot_size_d
        # Calls: long → positive.
        return net_qty / lot_size_d

    if pos.option_type == "FUT":
        return net_qty / lot_size_d

    logger.warning(
        "PortfolioDeltaTracker: unrecognised instrument_key %r (option_type=%s) — skipping delta",
        key,
        pos.option_type,
    )
    return Decimal(0)

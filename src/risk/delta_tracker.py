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
- **CE / Futures** (``NSE_FO|...CE...`` or no option type suffix):
  ``delta_lots = net_qty / lot_size``
  (short call → net_qty < 0 → negative delta ✓)
- **PE** (``NSE_FO|...PE...``):
  ``delta_lots = -net_qty / lot_size``
  (short put → net_qty < 0 → positive delta ✓; long put → positive net_qty → negative delta ✓)
- **NiftyBees ETF** (``NSE_EQ|INF204KB14I2``):
  ``delta_lots = net_qty × avg_cost / (nifty_spot × lot_size)``  (beta = 1.0)

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
    ) -> PortfolioDelta:
        """Compute aggregate portfolio delta from open paper positions.

        Args:
            paper_positions: All open ``PaperPosition`` objects across strategies.
                Obtain via ``PaperStore.get_position`` for each open trade.
            nifty_spot: Current Nifty 50 spot price (used for NiftyBees lot conversion).
            lot_size: Active Nifty lot size (e.g. 65 from ``src.paper.constants``).

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
            delta = _position_delta(pos, nifty_spot, lot_size_d)
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
) -> Decimal:
    """Compute signed delta in lots for a single position.

    Args:
        pos: Open paper position.
        nifty_spot: Current Nifty 50 spot price.
        lot_size_d: Lot size as ``Decimal`` for arithmetic consistency.

    Returns:
        Signed delta in Nifty-equivalent lots.
    """
    key = pos.instrument_key
    net_qty = Decimal(str(pos.net_qty))

    if key == NIFTYBEES_KEY:
        # NiftyBees: convert equity notional to Nifty-equivalent lots.
        # Use avg_cost as price proxy (paper trade entry price).
        return net_qty * pos.avg_cost / (nifty_spot * lot_size_d)

    if "PE" in key:
        # Put options: sign-flip so short put → positive delta.
        return -net_qty / lot_size_d

    if "CE" in key or ("NSE_FO|" in key and "PE" not in key):
        # Calls and futures (NSE_FO keys without a PE/CE suffix): long → positive.
        return net_qty / lot_size_d

    logger.warning(
        "PortfolioDeltaTracker: unrecognised instrument_key %r — skipping delta",
        key,
    )
    return Decimal(0)

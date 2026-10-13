"""Payoff-chart adapter for the Nifty calendar.

The standard ``DefaultPositionAdapter`` prices every leg at intrinsic, which is wrong for a
calendar: the far wings still carry time value when the near leg expires. This adapter draws
the near legs at intrinsic and the far legs through the CM-1 Black-76 ``payoff_at`` (each leg
at its own IV, forward from the far chain's put-call parity). It fails closed: with the
structure or carry missing it returns no legs, and the chart send logs and skips.

Caller contract: ``PayoffContext.extras`` carries ``"structure"`` (a ``CalendarStructure``)
and ``"far_carry"`` (``Decimal`` points), as built by ``nifty_calendar_state.build_structure``
and ``far_carry``.
"""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal

import structlog

from src.nifty_calendar.models import CalendarStructure
from src.nifty_calendar.payoff import payoff_at
from src.payoff.core import PayoffLeg
from src.payoff.registry import PayoffContext

logger = structlog.get_logger(__name__)


def _inputs(ctx: PayoffContext) -> tuple[CalendarStructure, Decimal] | None:
    structure, carry = ctx.extras.get("structure"), ctx.extras.get("far_carry")
    if not isinstance(structure, CalendarStructure) or not isinstance(carry, Decimal):
        logger.warning("calendar_payoff.inputs_missing", strategy=ctx.strategy_name)
        return None
    return structure, carry


class CalendarPayoffAdapter:
    """Four calendar legs at entry prices plus the near-expiry curve with repriced far legs."""

    def __init__(self, label: str = "Nifty Calendar") -> None:
        self._label = label

    def legs(self, ctx: PayoffContext) -> list[PayoffLeg]:
        """Return the four legs (signed units, entry prices); empty when inputs are missing."""
        inputs = _inputs(ctx)
        if inputs is None:
            return []
        return [
            PayoffLeg(
                kind=leg.option_type.value,  # type: ignore[arg-type]  # CE / PE only
                strike=leg.strike,
                qty=(-1 if leg.side.value == "SELL" else 1) * leg.qty_lots * ctx.lot_size,
                entry_price=leg.entry_price,
                role=leg.instrument_key,
            )
            for leg in inputs[0].legs
        ]

    def curve(self, ctx: PayoffContext) -> Callable[[Decimal], Decimal] | None:
        """Return near-expiry P&L in rupees at a spot, far legs repriced; ``None`` if missing."""
        inputs = _inputs(ctx)
        if inputs is None:
            return None
        structure, carry = inputs
        units = ctx.lot_size * structure.qty_lots

        def pnl(spot: Decimal) -> Decimal:
            return payoff_at(structure, spot, far_carry=carry, lot_size=units)

        return pnl

    def title(self, ctx: PayoffContext) -> str:
        """Return the chart title."""
        return self._label

    def subtitle(self, ctx: PayoffContext) -> str:
        """Return ``Short <near> · Long <far>`` when the structure is known."""
        structure = ctx.extras.get("structure")
        if not isinstance(structure, CalendarStructure):
            return ""
        return f"Short {structure.near_expiry:%d %b} · Long {structure.far_expiry:%d %b}".upper()

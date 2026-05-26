# src/risk/entry_gate.py
"""Entry gate — blocks or warns before a new paper trade increases long delta exposure.

``check_entry_allowed`` is the sole decision point for delta-based entry gating.
It consumes a pre-computed ``PortfolioDelta`` (from ``PortfolioDeltaTracker``)
so it has no I/O dependencies and is trivially testable.

Gate behaviour
--------------
- **Protective trade** (``is_protective=True``): always allowed, empty reason.
  Protective entries (long puts, collar hedges) reduce directional exposure and
  must never be blocked by a delta guard.
- **Cap breached**: entry blocked; non-empty reason string describes the breach.
- **Warning breached**: entry allowed but reason string contains a ``WARNING:``
  prefix so callers can surface it to the user.
- **No breach**: entry allowed, empty reason.
"""

from __future__ import annotations

from decimal import Decimal

from src.risk.models import PortfolioDelta


def check_entry_allowed(
    current_delta: PortfolioDelta,
    trade_delta_lots: Decimal,
    is_protective: bool,
) -> tuple[bool, str]:
    """Decide whether a new paper trade entry is allowed given current delta state.

    Args:
        current_delta: Aggregate portfolio delta computed by ``PortfolioDeltaTracker``
            immediately before the proposed trade.
        trade_delta_lots: Signed delta contribution of the proposed trade in Nifty lots.
            Positive = adds long bias; negative = reduces bias.  Used **only for the
            informational warning string** — the gate decision is based solely on the
            pre-trade ``current_delta`` state.  The gate does not re-compute a projected
            post-trade delta; callers should re-run ``aggregate_delta`` after the trade
            to verify the realised state.
        is_protective: When ``True``, bypass all delta gates unconditionally.  Set this
            for long puts, tail hedges, and any leg that reduces directional exposure.

    Returns:
        ``(allowed, reason)`` tuple.  ``reason`` is an empty string when ``allowed``
        is ``True`` with no warnings.  A ``WARNING:`` prefix indicates the warning
        threshold is breached but entry is not blocked.
    """
    if is_protective:
        return True, ""

    if current_delta.cap_breached:
        return (
            False,
            (
                f"Portfolio delta hard cap breached "
                f"(total={current_delta.total_delta_lots:.3f} lots, "
                f"options={current_delta.options_delta_lots:.3f} lots). "
                f"Close or roll existing positions before adding long exposure."
            ),
        )

    if current_delta.warning_breached:
        return (
            True,
            (
                f"WARNING: portfolio delta near cap "
                f"(total={current_delta.total_delta_lots:.3f} lots, "
                f"options={current_delta.options_delta_lots:.3f} lots). "
                f"Proposed trade adds {trade_delta_lots:+.3f} lots — review before confirming."
            ),
        )

    return True, ""

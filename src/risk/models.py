# src/risk/models.py
"""Data models for portfolio-level risk tracking.

``PortfolioDelta`` is the canonical snapshot of aggregate directional exposure
across all open paper positions. It is computed by ``PortfolioDeltaTracker`` and
consumed by ``check_entry_allowed`` to gate new paper trade entries.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True)
class PortfolioDelta:
    """Aggregate delta exposure snapshot across all open paper positions.

    Computed on demand by ``PortfolioDeltaTracker.aggregate_delta``.
    Never stored — reconstructed before each entry decision.

    Delta is expressed in **Nifty-equivalent lots** throughout:
    - Options / futures: ``net_qty / lot_size`` (signed; puts are sign-flipped
      so that short put = positive delta, long put = negative delta).
    - NiftyBees ETF: ``qty × avg_cost / (nifty_spot × lot_size)`` with beta = 1.0.

    Threshold semantics:
    - ``warning_breached``: options-only > OPTIONS_WARNING **or**
      combined total > COMBINED_WARNING.  Entry is still allowed but the
      caller should surface a warning.
    - ``cap_breached``: options-only > OPTIONS_CAP **or**
      combined total > COMBINED_CAP.  Entry is blocked.

    Attributes:
        options_delta_lots: Net delta from all options and futures positions.
        niftybees_delta_lots: Delta from NiftyBees ETF converted to Nifty lots.
        total_delta_lots: ``options_delta_lots + niftybees_delta_lots``.
        warning_breached: True when any warning threshold is exceeded.
        cap_breached: True when any hard cap is exceeded.
        as_of: UTC datetime when this snapshot was computed.
    """

    options_delta_lots: Decimal
    niftybees_delta_lots: Decimal
    total_delta_lots: Decimal
    warning_breached: bool
    cap_breached: bool
    as_of: datetime

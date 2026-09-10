"""Signals-paper-track exit policy — constants half (SPT-3).

The single owner of the SL / target numbers for ``paper_signal_track_v1``.
SPT-5 extends this same module with ``evaluate()`` + ``SignalExitReason`` (a
reserved ``TRAILING_STOP`` member included from the start) — keep the evaluator
here rather than splitting it into a second file.

The module constants are the *current default cohort* only. Per-position
``sl_pct`` / ``tgt_pct`` / ``sl_price`` / ``tgt_price`` are frozen onto
``paper_signal_entries`` at entry and stay the source of truth for a live
position. A v2 recalibration changes the constants here and ships new rows as
``ruleset_version='v2'`` — it never touches v1 rows.
"""

from __future__ import annotations

from decimal import Decimal

SL_PCT: Decimal = Decimal("0.30")
TGT_PCT: Decimal = Decimal("0.50")
RULESET_VERSION: str = "v1"


def derive_levels(entry_premium: Decimal) -> tuple[Decimal, Decimal]:
    """Return ``(sl_price, tgt_price)`` for a simulated fill at ``entry_premium``.

    ``sl_price = E * (1 - SL_PCT)``; ``tgt_price = E * (1 + TGT_PCT)``. Returned
    unrounded — the caller freezes the raw values onto ``paper_signal_entries``.

    Args:
        entry_premium: The simulated BUY fill ``E``. Must be positive.

    Returns:
        ``(sl_price, tgt_price)`` — both ``Decimal``.

    Raises:
        ValueError: If ``entry_premium`` is not positive.
    """
    if entry_premium <= 0:
        raise ValueError(f"entry_premium must be positive, got {entry_premium}")
    return (
        entry_premium * (Decimal("1") - SL_PCT),
        entry_premium * (Decimal("1") + TGT_PCT),
    )

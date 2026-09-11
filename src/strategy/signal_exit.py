"""Signals-paper-track exit policy —
constants + pure evaluator (SPT-3 / SPT-3b).

The single owner of the SL / target numbers for ``paper_signal_track_v1``, and
of the pure exit-decision function the SPT-4 monitor tick calls. SPT-5 is the
caller-side wiring only (fill / close / Telegram) — it does not add to this
module.

The module constants are the *current default cohort* only. Per-position
``sl_pct`` / ``tgt_pct`` / ``sl_price`` / ``tgt_price`` are frozen onto
``paper_signal_entries`` at entry and stay the source of truth for a live
position. A v2 recalibration changes the constants here and ships new rows as
``ruleset_version='v2'`` — it never touches v1 rows.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from decimal import Decimal
from enum import Enum
from zoneinfo import ZoneInfo

from src.paper.models import SignalPaperEntry

SL_PCT: Decimal = Decimal("0.30")
TGT_PCT: Decimal = Decimal("0.50")
RULESET_VERSION: str = "v1"

_IST = ZoneInfo("Asia/Kolkata")
_SQUARE_OFF = time(15, 0)


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


class SignalExitReason(str, Enum):
    """Why a signals-paper-track position exited (or would exit)."""

    TARGET = "TARGET"
    STOP_LOSS = "STOP_LOSS"
    TIME_EXIT = "TIME_EXIT"
    # Reserved for Phase 2; evaluate() never returns it.
    TRAILING_STOP = "TRAILING_STOP"


@dataclass(frozen=True)
class SignalExitDecision:
    """Result of one ``evaluate()`` call.

    Attributes:
        reason: The exit reason, or ``None`` for ``HOLD``.
    """

    reason: SignalExitReason | None


def evaluate(
    entry: SignalPaperEntry,
    mark: Decimal,
    now: datetime,
) -> SignalExitDecision:
    """Decide whether an open signals-paper-track position should exit.

    Pure — no I/O, no fill, no persistence. Priority order: target beats stop
    beats the 15:00 IST square-off beats hold.

    Args:
        entry: The frozen entry record (carries ``sl_price`` / ``tgt_price``).
        mark: The current observed mark, e.g. ``(bid + ask) / 2``.
        now: The tick evaluation time. Naive datetimes are treated as IST;
            aware datetimes are converted to IST before the 15:00 check.

    Returns:
        A ``SignalExitDecision`` with ``reason`` set to ``TARGET`` /
        ``STOP_LOSS`` / ``TIME_EXIT``, or ``None`` for ``HOLD``.
    """
    if mark >= entry.tgt_price:
        return SignalExitDecision(reason=SignalExitReason.TARGET)
    if mark <= entry.sl_price:
        return SignalExitDecision(reason=SignalExitReason.STOP_LOSS)
    now_ist = now if now.tzinfo is None else now.astimezone(_IST)
    if now_ist.time() >= _SQUARE_OFF:
        return SignalExitDecision(reason=SignalExitReason.TIME_EXIT)
    return SignalExitDecision(reason=None)

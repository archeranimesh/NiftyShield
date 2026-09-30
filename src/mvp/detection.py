"""Overnight-gap ratio matcher for possible corporate actions (pure, no I/O).

A ratio match only shortlists a pick for manual confirmation; it never
infers or inserts a corporate-action row (BUG-054 council ruling).
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from src.mvp.models import CorporateAction, MVPSnapshot

STANDARD_FACTORS: tuple[Decimal, ...] = tuple(
    Decimal(f) for f in ("2", "3", "4", "5", "10", "1.5", "2.5")
)
TOLERANCE = Decimal("0.03")


@dataclass(frozen=True)
class GapMatch:
    """A gap landing within tolerance of a standard split/bonus factor.

    ``reverse`` is True when the price rose by ``factor`` (consolidation-like).
    """

    factor: Decimal
    reverse: bool

    @property
    def label(self) -> str:
        """``N:1`` for a price drop by N (split/bonus), ``1:N`` for a rise."""
        n = format(self.factor.normalize(), "f")
        return f"1:{n}" if self.reverse else f"{n}:1"


def match_split_factor(
    prev_close: Decimal, ltp: Decimal, tolerance: Decimal = TOLERANCE
) -> GapMatch | None:
    """Match ``ltp / prev_close`` against 1/f and f for the standard factors.

    Args:
        prev_close: Previous session's last price.
        ltp: Today's opening price.
        tolerance: Relative tolerance around each target ratio.

    Returns:
        The closest match within ``tolerance``, or ``None``.
    """
    if prev_close <= 0 or ltp <= 0:
        return None
    ratio = ltp / prev_close
    best: tuple[Decimal, GapMatch] | None = None
    for factor in STANDARD_FACTORS:
        for target, reverse in ((1 / factor, False), (factor, True)):
            deviation = abs(ratio - target) / target
            if deviation <= tolerance and (best is None or deviation < best[0]):
                best = (deviation, GapMatch(factor=factor, reverse=reverse))
    return best[1] if best else None


def detect_overnight_gap(
    snapshots: Sequence[MVPSnapshot],
    today: date,
    current_ltp: Decimal,
    actions: Iterable[CorporateAction] = (),
) -> GapMatch | None:
    """Compare today's opening price to the previous session's last snapshot.

    Today's opening price is the earliest snapshot dated ``today`` (so the
    verdict stays stable across the day's later ticks), else ``current_ltp``.
    Returns ``None`` when there is no prior-session snapshot, or when a
    recorded action already covers the gap (``prev_date < ex_date <= today``).

    Args:
        snapshots: The pick's snapshots in any order.
        today: Current trading date.
        current_ltp: The live LTP on this tick.
        actions: Recorded corporate actions for the pick's symbol.

    Returns:
        The matched factor, or ``None`` for no (or an already-handled) gap.
    """
    dated = [(date.fromisoformat(s.captured_at[:10]), s) for s in snapshots]
    prior = [(d, s) for d, s in dated if d < today]
    if not prior:
        return None
    prev_date, prev = max(prior, key=lambda x: x[1].captured_at)
    if any(prev_date < date.fromisoformat(a.ex_date) <= today for a in actions):
        return None
    todays = sorted((s for d, s in dated if d == today), key=lambda s: s.captured_at)
    open_ltp = todays[0].ltp if todays else current_ltp
    return match_split_factor(prev.ltp, open_ltp)


def format_gap_warning(symbol: str, match: GapMatch) -> str:
    """Plain-text Telegram warning text for a suppressed pick."""
    return (
        f"\U0001f6a9 {symbol}: overnight gap matches {match.label} pattern. "
        "Possible corporate action. Auto-close paused. "
        "Verify and run corporate-action add if confirmed."
    )

"""Phase B candidate ranking (strategy doc sections 6-7).

Pure and zero-I/O. Score is the section 6 formula::

    (gamma_gearing * 0.7) + (watchlist_hit * 0.3 * gamma_gearing)

so a watchlist hit scores ``gearing`` and a non-hit ``0.7 * gearing``.
Higher score ranks first. A ``None`` gearing scores below every real score
(such a candidate cannot pass Layer 2 anyway).

Tie break (deterministic, applied in order): watchlist hit first, lower
ask (cheaper premium), smaller distance to strike, then option type
(``CE`` before ``PE``). ``Candidate`` carries no strike, so candidates
equal on all of those keep their input order (stable sort); the caller
must supply them in a stable order (e.g. ascending strike).
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal

from src.gamma.signals import Candidate

GEARING_WEIGHT = Decimal("0.7")
WATCHLIST_WEIGHT = Decimal("0.3")


def rank_score(c: Candidate) -> Decimal | None:
    """Return the section 6 ranking score, or ``None`` without gearing.

    Args:
        c: Candidate with ``gamma_gearing`` and ``watchlist_hit``.

    Returns:
        ``gearing * 0.7 + hit * 0.3 * gearing`` as Decimal, or None.
    """
    if c.gamma_gearing is None:
        return None
    hit = Decimal(int(c.watchlist_hit))
    return c.gamma_gearing * GEARING_WEIGHT + hit * WATCHLIST_WEIGHT * c.gamma_gearing


def _sort_key(c: Candidate) -> tuple[bool, Decimal, bool, Decimal, Decimal, str]:
    score = rank_score(c)
    return (
        score is None,
        -(score if score is not None else Decimal(0)),
        not c.watchlist_hit,
        c.ask,
        c.distance_pct,
        c.option_type,
    )


def rank_candidates(candidates: Sequence[Candidate]) -> list[Candidate]:
    """Order candidates best-first by the section 6 score.

    Args:
        candidates: Candidates that passed the signal stack.

    Returns:
        New list, highest score first; ties broken as in the module docstring.
    """
    return sorted(candidates, key=_sort_key)

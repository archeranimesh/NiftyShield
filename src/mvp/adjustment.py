"""Pure corporate-action adjustment helpers (no I/O)."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date
from decimal import Decimal

from src.mvp.models import CorporateAction


def cumulative_multiplier(
    actions: Iterable[CorporateAction],
    from_date: date,
    as_of: date,
) -> Decimal:
    """Product of ``new_shares / old_shares`` for actions with ``from_date < ex_date <= as_of``.

    Converts a level set on ``from_date`` to the basis in force on ``as_of``:
    ``price_new = price_old / M`` and ``qty_new = qty_old * M``, so
    ``price * qty`` is unchanged. Actions compound; none in range gives ``1``.

    Args:
        actions: Corporate actions for a single symbol.
        from_date: Date the level (price/qty) was set.
        as_of: Evaluation date.

    Returns:
        The cumulative share-count multiplier.
    """
    m = Decimal("1")
    for a in actions:
        if from_date < date.fromisoformat(a.ex_date) <= as_of:
            m *= Decimal(a.new_shares) / Decimal(a.old_shares)
    return m

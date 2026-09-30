"""Pure corporate-action adjustment helpers (no I/O)."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_FLOOR, Decimal

from src.mvp.models import CorporateAction, Pick


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


def adjust_level(
    level: Decimal | None,
    actions: Iterable[CorporateAction],
    level_date: date,
    as_of: date,
) -> Decimal | None:
    """Convert a price level set on ``level_date`` to the basis in force on ``as_of``.

    Args:
        level: Absolute price (target, stop-loss, reco, entry), or ``None``.
        actions: Corporate actions for the level's symbol.
        level_date: Date the level was set.
        as_of: Evaluation date.

    Returns:
        ``level / M``, or ``None`` when ``level`` is ``None``.
    """
    if level is None:
        return None
    return level / cumulative_multiplier(actions, level_date, as_of)


@dataclass(frozen=True)
class Fill:
    """One executed fill on its own (raw) price basis."""

    price: Decimal
    qty: int
    filled_on: date


@dataclass(frozen=True)
class AdjustedPosition:
    """Position restated on a single price basis (the ``as_of`` basis)."""

    total_qty: Decimal
    avg_cost: Decimal | None


def adjust_position(
    fills: Iterable[Fill],
    actions: Iterable[CorporateAction],
    as_of: date,
) -> AdjustedPosition:
    """Restate fills on the ``as_of`` basis, each from its own fill date.

    ``qty_adj = qty * M`` and ``price_adj = price / M`` per fill, with
    ``avg_cost = sum(price_adj * qty_adj) / sum(qty_adj)``. Since
    ``price_adj * qty_adj == price * qty`` the numerator is summed unadjusted
    (avoids Decimal rounding noise); rupee value is never rescaled.

    Args:
        fills: Executed fills (price and qty as recorded at fill time).
        actions: Corporate actions for the symbol.
        as_of: Evaluation date.

    Returns:
        Adjusted total quantity and average cost (``None`` when no quantity).
    """
    actions = list(actions)
    qty = Decimal("0")
    cost = Decimal("0")
    for f in fills:
        qty += f.qty * cumulative_multiplier(actions, f.filled_on, as_of)
        cost += f.price * f.qty
    return AdjustedPosition(total_qty=qty, avg_cost=cost / qty if qty else None)


def adjusted_pick(
    pick: Pick,
    actions: Iterable[CorporateAction],
    as_of: date,
    fills: Iterable[Fill] = (),
) -> Pick:
    """Return ``pick`` restated on the ``as_of`` price basis (read-time view).

    ``reco_price``/``target_price``/``stop_loss`` are adjusted from
    ``pick_date``; ``entry_price`` from the first fill date; ``total_qty``
    (floored, as fractional entitlements are cashed out) and ``avg_cost``
    from the fills. ``deployed_capital``, ``idle_cash``, ``realized_pnl`` and
    ``benchmark_entry`` are never touched. Returns ``pick`` itself when there
    are no actions.
    """
    actions = list(actions)
    if not actions:
        return pick
    pick_date = date.fromisoformat(pick.pick_date[:10])
    updates: dict[str, object] = {
        "reco_price": adjust_level(pick.reco_price, actions, pick_date, as_of),
        "target_price": adjust_level(pick.target_price, actions, pick_date, as_of),
        "stop_loss": adjust_level(pick.stop_loss, actions, pick_date, as_of),
    }
    fills = list(fills)
    if fills:
        pos = adjust_position(fills, actions, as_of)
        updates["total_qty"] = int(pos.total_qty.to_integral_value(rounding=ROUND_FLOOR))
        updates["avg_cost"] = pos.avg_cost
        first = min(f.filled_on for f in fills)
        updates["entry_price"] = adjust_level(pick.entry_price, actions, first, as_of)
    return pick.model_copy(update=updates)

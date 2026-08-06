# src/risk/collateral_gate.py
"""Shared NiftyBees collateral-capacity gate — warn-only (RH-4, 2026-08-06).

``check_collateral_capacity`` sums already-open lots across the CSP strategy
(``STRATEGY_CSP``) and the shared overlay namespace (``STRATEGY_OVERLAY``,
covering CC/PP/Collar — see ``src/paper/constants.py``) and compares the total
against ``compute_max_lots()``'s ceiling for the physical NiftyBees holding.

Design decision (operator-confirmed 2026-08-06, no council call — single-discipline
capital-allocation gate, fails the council's cross-disciplinary trigger condition):
warn-only, mirroring the existing IVR/DTE/liquidity log-only-gates pattern. A breach
never blocks entry — it persists a ``GateViolation`` via
``PaperStore.record_gate_violation`` and the caller proceeds regardless. This is a
deliberate asymmetry with structural gates (duplicate entry, unresolved instrument,
stale VIX window), which always hard-block; see ``docs/council/README.md`` and
``DECISIONS.md`` 2026-08-06 for the rationale.

``niftybees_units`` is resolved from the existing ``STRATEGY_SPOT``
(``paper_nifty_spot``) position — the CSP-collateral-leg story (closed
2026-08-06, see ``TODOS.md``) confirmed this *is* the physical pledged
NiftyBees holding; no new model or position type is introduced (CL-1
precedent). Callers still resolve live ``nifty_spot``/``niftybees_ltp`` prices
themselves — this module makes exactly one extra ``PaperStore`` read (the
NiftyBees holding) on top of the open-lots read, and one write on breach
(gate violation log), matching ``compute_max_lots()``'s own
caller-resolves-live-prices contract.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from src.paper.constants import (
    LOT_SIZE,
    STRATEGY_CSP,
    STRATEGY_OVERLAY,
    STRATEGY_SPOT,
    compute_max_lots,
)
from src.paper.models import GateViolation

if TYPE_CHECKING:
    # PaperStore imports src.strategy.profit_lock_engine, which imports
    # src.strategy (package __init__) -> csp_nifty_v1 -> csp_roll_executor ->
    # this module — a real runtime import here creates a circular import.
    # `from __future__ import annotations` makes all annotations strings, so
    # this is type-checking only; no runtime import of src.paper.store needed.
    from src.paper.store import PaperStore

GATE_NAME = "niftybees_collateral_capacity"

# Strategies that draw from the single physical NiftyBees collateral pool.
# STRATEGY_OVERLAY is the one shared namespace for CC/PP/Collar (S1r, 2026-07-29) —
# summing it once, not once per overlay type, avoids triple-counting the same pool.
_COLLATERAL_DRAWING_STRATEGIES = (STRATEGY_CSP, STRATEGY_OVERLAY)


def _open_lots_across_strategies(store: PaperStore, lot_size: int) -> int:
    """Sum absolute open lots across every strategy drawing on the NiftyBees pool.

    Args:
        store: PaperStore to read open positions from.
        lot_size: Nifty lot size used to convert net_qty to lots.

    Returns:
        Total open lots (always non-negative) across ``STRATEGY_CSP`` and
        ``STRATEGY_OVERLAY``. Each leg's ``net_qty`` is taken as absolute value —
        a short put and a short call both consume collateral regardless of sign.
    """
    if lot_size <= 0:
        return 0
    total_qty = 0
    for strategy_name in _COLLATERAL_DRAWING_STRATEGIES:
        for position in store.get_positions(strategy_name):
            total_qty += abs(position.net_qty)
    return total_qty // lot_size


def _niftybees_units_held(store: PaperStore) -> int:
    """Sum net units held in the STRATEGY_SPOT (paper_nifty_spot) position.

    Zero if no open NiftyBees position exists — this is a real "no collateral
    pledged" state, not an error; ``compute_max_lots`` already returns 0 lots
    for a zero/undersized holding.
    """
    return sum(
        position.net_qty
        for position in store.get_positions(STRATEGY_SPOT)
        if position.net_qty > 0
    )


def check_collateral_capacity(
    store: PaperStore,
    strategy_name: str,
    lots_requested: int,
    nifty_spot: Decimal,
    niftybees_ltp: Decimal,
    lot_size: int = LOT_SIZE,
) -> GateViolation | None:
    """Warn (never block) if aggregate collateral draw would exceed capacity.

    Args:
        store: PaperStore — read for the NiftyBees holding + currently open
            lots, written to on breach.
        strategy_name: The strategy attempting the new entry (used only for the
            logged ``GateViolation.strategy_name`` — the aggregate check itself
            always sums across all collateral-drawing strategies).
        lots_requested: Lots the caller is about to open.
        nifty_spot: Current Nifty 50 spot price.
        niftybees_ltp: Current NiftyBees ETF LTP.
        lot_size: Nifty lot size (default: ``LOT_SIZE``).

    Returns:
        A ``GateViolation`` (already persisted via ``record_gate_violation``) if
        ``already_open_lots + lots_requested`` exceeds ``compute_max_lots()``'s
        ceiling, else ``None``. In both cases the caller should proceed with
        entry — this gate is warn-only by design, not a block.
    """
    niftybees_units = _niftybees_units_held(store)
    max_lots = compute_max_lots(
        niftybees_units=niftybees_units,
        nifty_spot=nifty_spot,
        niftybees_ltp=niftybees_ltp,
        lot_size=lot_size,
    )
    already_open = _open_lots_across_strategies(store, lot_size)
    projected = already_open + lots_requested

    if projected <= max_lots:
        return None

    violation = GateViolation(
        gate_name=GATE_NAME,
        threshold=str(max_lots),
        actual=str(projected),
        strategy_name=strategy_name,
        logged_at=datetime.now(),
    )
    store.record_gate_violation(violation)
    return violation

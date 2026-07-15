"""Shared closing-leg execution helper for Iron Condor strategies (V1 and V2).

Both ``IronCondorV1.apply_action`` and ``IronCondorV2.apply_action`` compute
an in-memory ``closed`` set of leg roles when auto-executing ``CLOSE_FULL``,
``CLOSE_CALL_SPREAD``, or ``CLOSE_PUT_SPREAD`` — but historically neither
persisted the closing fills to ``paper_trades``. The in-memory
``PaperPosition`` filtering looked like a close (the returned list dropped
the closed legs) but the return value was discarded by
``StrategyMonitor._handle_event`` (auto-execute dispatch path), and
``PaperStore.get_positions()`` kept reporting the position as open on every
subsequent tick — causing the same exit signal (e.g. LOSS_STOP) to
re-fire indefinitely with no visible error.

This module fetches live LTP for every closing leg in a single batched
broker call, builds the opposite-action closing ``PaperTrade`` rows, and
writes them atomically via ``PaperStore.record_trades`` — mirroring the
pattern already used by ``OverlayCloser.close_collar_all`` for the overlay
strategies and ``close_csp_leg`` for CSP.

Scope: flatten-only actions (``CLOSE_FULL``, ``CLOSE_CALL_SPREAD``,
``CLOSE_PUT_SPREAD``). ``ROLL_WING`` and ``PROFIT_LOCK_ZONE2`` are roll
actions (close + open a replacement leg at a new strike) and are not
covered here — see DECISIONS.md and TODOS.md for the follow-up.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

import structlog

from src.market_calendar.holidays import market_today
from src.paper.models import PaperTrade, TradeAction

if TYPE_CHECKING:
    from src.client.protocol import BrokerClient
    from src.paper.models import PaperPosition
    from src.paper.store import PaperStore

log = structlog.get_logger(__name__)


async def close_ic_legs(
    broker: BrokerClient,
    store: PaperStore,
    positions: list[PaperPosition],
    closed_roles: set[str],
    strategy_name: str,
    notes: str,
) -> list[PaperTrade]:
    """Close the given IC legs at live LTP and persist atomically.

    Args:
        broker: BrokerClient used to fetch live LTP for the closing legs.
        store: PaperStore used to persist the closing trades.
        positions: Currently open positions (already filtered to this
            strategy by the caller).
        closed_roles: leg_role values to close (e.g. all four IC roles
            for CLOSE_FULL, or the two call-spread roles for
            CLOSE_CALL_SPREAD).
        strategy_name: Paper strategy name; must start with ``paper_``
            (enforced by ``PaperTrade``).
        notes: Note string recorded against every closing trade for the
            audit trail (e.g. the triggering signal).

    Returns:
        The closing ``PaperTrade`` rows actually inserted. Empty when
        nothing was open for the requested roles, when the LTP fetch and
        fallback both fail, or when the atomic write is rejected.
    """
    to_close = [p for p in positions if p.leg_role in closed_roles and p.net_qty != 0]
    if not to_close:
        log.warning(
            "ic_close_executor.nothing_to_close",
            strategy_name=strategy_name,
            closed_roles=sorted(closed_roles),
        )
        return []

    keys = [p.instrument_key for p in to_close]
    try:
        ltp_map = await broker.get_ltp(keys)
    except Exception as exc:
        log.error(
            "ic_close_executor.ltp_fetch_failed",
            strategy_name=strategy_name,
            error=str(exc),
        )
        ltp_map = {}

    today = market_today()
    trades: list[PaperTrade] = []
    for pos in to_close:
        raw = ltp_map.get(pos.instrument_key)
        close_price: Decimal
        if raw is None or Decimal(str(raw)) <= 0:
            # Fall back to the leg's own entry price — same degraded-mode
            # behaviour as close_csp_leg (src/strategy/csp_roll_executor.py).
            close_price = pos.avg_sell_price if pos.net_qty < 0 else pos.avg_cost
            log.warning(
                "ic_close_executor.ltp_missing_fallback_to_entry",
                strategy_name=strategy_name,
                instrument_key=pos.instrument_key,
                fallback_price=str(close_price),
            )
        else:
            close_price = Decimal(str(raw)).quantize(Decimal("0.01"))

        close_action = TradeAction.SELL if pos.net_qty > 0 else TradeAction.BUY
        trades.append(
            PaperTrade(
                strategy_name=strategy_name,
                leg_role=pos.leg_role,
                instrument_key=pos.instrument_key,
                trade_date=today,
                action=close_action,
                quantity=abs(pos.net_qty),
                price=close_price,
                notes=notes,
                ivr_at_entry=None,
                is_paper=True,
            )
        )

    if not trades:
        return []

    try:
        inserted, skipped = store.record_trades(trades)
    except Exception as exc:
        log.error(
            "ic_close_executor.write_failed",
            strategy_name=strategy_name,
            error=str(exc),
        )
        return []

    if skipped:
        log.error(
            "ic_close_executor.partial_write",
            strategy_name=strategy_name,
            skipped=[t.leg_role for t in skipped],
        )

    log.info(
        "ic_close_executor.legs_closed",
        strategy_name=strategy_name,
        legs=[t.leg_role for t in inserted],
        prices={t.leg_role: str(t.price) for t in inserted},
    )
    return inserted

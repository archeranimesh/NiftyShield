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

When a leg's LTP is missing, the fallback branches on *why*: if the BOD
instrument master shows the contract's expiry is today or earlier, LTP will
never resolve (the instrument is delisted or the exchange has stopped
quoting it for the day) — so the price is derived from
Nifty spot instead of reused verbatim. ITM legs settle at intrinsic value
(``|spot - strike|``); OTM legs settle at ``_OTM_EXPIRY_PRICE`` (0.05, the
NSE tick floor for a worthless expiry). Only when the contract has *not*
expired (a transient LTP gap) or BOD/spot resolution itself fails does it
fall back to the leg's own entry price — added 2026-07-16 after entry-price
fallback was found to silently zero out realized P&L on every post-expiry
LOSS_STOP close (see DECISIONS.md 2026-07-16).

Scope: flatten actions (``CLOSE_FULL``, ``CLOSE_CALL_SPREAD``,
``CLOSE_PUT_SPREAD``) via ``close_ic_legs``, and roll actions (``ROLL_WING``,
``PROFIT_LOCK_ZONE2`` — close the old leg(s) and open replacement leg(s) at a
new strike) via ``roll_ic_legs``. Both persist atomically through a single
``PaperStore.record_trades`` call.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

import structlog

from src.instruments.lookup import InstrumentLookup, parse_expiry
from src.market_calendar.holidays import market_today
from src.paper.constants import DEFAULT_BOD_PATH
from src.paper.models import PaperTrade, TradeAction

if TYPE_CHECKING:
    from src.client.protocol import BrokerClient
    from src.paper.models import PaperPosition
    from src.paper.store import PaperStore
    from src.strategy.protocol import LegSpec

log = structlog.get_logger(__name__)

# Nifty 50 index instrument key — used to derive intrinsic settlement value
# for legs whose own LTP is unavailable because the contract has expired.
_NIFTY_SPOT_KEY = "NSE_INDEX|Nifty 50"

# NSE minimum tick — used as the settlement price for OTM legs that expired
# worthless. Not literally 0: keeps the closing trade's price field positive
# and matches how NSE itself prices a worthless expiry on the bhavcopy.
_OTM_EXPIRY_PRICE = Decimal("0.05")


async def _build_close_trades(
    broker: BrokerClient,
    to_close: list[PaperPosition],
    strategy_name: str,
    notes: str,
) -> list[PaperTrade]:
    """Resolve close-side prices and build closing ``PaperTrade`` rows.

    Shared by ``close_ic_legs`` and ``roll_ic_legs`` — LTP is fetched live
    per leg, falling back to BOD-derived expiry settlement (intrinsic value
    for ITM, ``_OTM_EXPIRY_PRICE`` for OTM) or, as a last resort, the leg's
    own entry price. See module docstring for the full rationale. Does not
    write to the store — callers persist the returned trades themselves.
    """
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
    bod_lookup: InstrumentLookup | None = None
    spot: Decimal | None = None
    spot_fetch_attempted = False
    trades: list[PaperTrade] = []
    for pos in to_close:
        raw = ltp_map.get(pos.instrument_key)
        close_price: Decimal
        if raw is None or Decimal(str(raw)) <= 0:
            settlement_price = None
            if bod_lookup is None:
                try:
                    bod_lookup = InstrumentLookup.from_file(DEFAULT_BOD_PATH)
                except Exception as exc:
                    log.warning(
                        "ic_close_executor.bod_lookup_load_failed",
                        strategy_name=strategy_name,
                        error=str(exc),
                    )
                    bod_lookup = None

            inst = bod_lookup.get_by_key(pos.instrument_key) if bod_lookup else None
            expiry_str = parse_expiry(inst.get("expiry")) if inst else None
            option_type = inst.get("instrument_type") if inst else None
            strike_price = inst.get("strike_price") if inst else None

            is_post_expiry = expiry_str is not None and date.fromisoformat(expiry_str) <= today

            if is_post_expiry and option_type in ("CE", "PE") and strike_price is not None:
                if not spot_fetch_attempted:
                    spot_fetch_attempted = True
                    try:
                        spot_map = await broker.get_ltp([_NIFTY_SPOT_KEY])
                        spot_raw = spot_map.get(_NIFTY_SPOT_KEY)
                        spot = Decimal(str(spot_raw)) if spot_raw is not None else None
                    except Exception as exc:
                        log.warning(
                            "ic_close_executor.spot_fetch_failed",
                            strategy_name=strategy_name,
                            error=str(exc),
                        )
                        spot = None

                if spot is not None:
                    strike = Decimal(str(strike_price))
                    is_itm = (option_type == "CE" and spot > strike) or (
                        option_type == "PE" and spot < strike
                    )
                    if is_itm:
                        settlement_price = (
                            (spot - strike) if option_type == "CE" else (strike - spot)
                        ).quantize(Decimal("0.01"))
                    else:
                        settlement_price = _OTM_EXPIRY_PRICE
                    log.warning(
                        "ic_close_executor.ltp_missing_fallback_to_expiry_settlement",
                        strategy_name=strategy_name,
                        instrument_key=pos.instrument_key,
                        option_type=option_type,
                        strike=str(strike),
                        spot=str(spot),
                        settlement_price=str(settlement_price),
                    )

            if settlement_price is not None:
                close_price = settlement_price
            else:
                # Fall back to the leg's own entry price — same degraded-mode
                # behaviour as close_csp_leg (src/strategy/csp_roll_executor.py).
                # Used when the contract hasn't expired (transient LTP gap) or
                # when BOD/spot resolution itself failed.
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
    return trades


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

    trades = await _build_close_trades(broker, to_close, strategy_name, notes)
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


async def roll_ic_legs(
    broker: BrokerClient,
    store: PaperStore,
    close_positions: list[PaperPosition],
    closed_roles: set[str],
    open_legs: list[LegSpec],
    strategy_name: str,
    notes: str,
) -> list[PaperTrade]:
    """Close the old roll leg(s) and open the replacement leg(s) atomically.

    Used by ``ROLL_WING`` (V1/V2) and ``PROFIT_LOCK_ZONE2`` (V2) auto-execute:
    both close an existing leg and open a replacement at a new strike, and
    must persist both sides in a single ``PaperStore.record_trades`` call —
    a roll that writes only the close side would leave the position naked,
    worse than not rolling at all.

    Args:
        broker: BrokerClient used to fetch live LTP for the closing legs.
        store: PaperStore used to persist the close+open trades.
        close_positions: Currently open positions (already filtered to this
            strategy by the caller).
        closed_roles: leg_role values to close.
        open_legs: Replacement legs to open — each must carry a resolved
            ``price`` (captured at selection time); a leg with ``price``
            ``None`` or non-positive aborts the entire roll.
        strategy_name: Paper strategy name; must start with ``paper_``
            (enforced by ``PaperTrade``).
        notes: Note string recorded against every trade for the audit trail.

    Returns:
        The close+open ``PaperTrade`` rows actually inserted. Empty when
        there is nothing to close and nothing to open, when any open leg is
        missing a price, or when the atomic write is rejected.
    """
    to_close = [p for p in close_positions if p.leg_role in closed_roles and p.net_qty != 0]

    if not to_close and not open_legs:
        log.warning(
            "ic_close_executor.nothing_to_roll",
            strategy_name=strategy_name,
            closed_roles=sorted(closed_roles),
        )
        return []

    for leg in open_legs:
        if leg.price is None or leg.price <= 0:
            log.error(
                "ic_close_executor.roll_open_leg_price_missing",
                strategy_name=strategy_name,
                instrument_key=leg.instrument_key,
                leg_role=leg.leg_role,
            )
            return []

    close_trades = await _build_close_trades(broker, to_close, strategy_name, notes)

    today = market_today()
    open_trades: list[PaperTrade] = []
    for leg in open_legs:
        # Already validated non-None/positive in the guard loop above —
        # asserted here so mypy can narrow Decimal | None -> Decimal without
        # re-running the check (and to fail loudly if that invariant is ever
        # broken by a future edit to the guard loop).
        assert leg.price is not None
        open_trades.append(
            PaperTrade(
                strategy_name=strategy_name,
                leg_role=leg.leg_role,
                instrument_key=leg.instrument_key,
                trade_date=today,
                action=TradeAction[leg.action],
                quantity=leg.quantity,
                price=leg.price,
                notes=notes,
                ivr_at_entry=None,
                is_paper=True,
            )
        )

    all_trades = close_trades + open_trades
    if not all_trades:
        return []

    try:
        inserted, skipped = store.record_trades(all_trades)
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
        "ic_close_executor.legs_rolled",
        strategy_name=strategy_name,
        legs=[t.leg_role for t in inserted],
        prices={t.leg_role: str(t.price) for t in inserted},
    )
    return inserted

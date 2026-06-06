"""Roll execution core logic for Cash-Secured Put (CSP) legs.

Shared by daemon automation and CLI scripts.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

import structlog

from src.client.protocol import BrokerClient
from src.instruments.lookup import InstrumentLookup
from src.instruments.strike_selector import filter_strikes_by_delta, rank_strikes
from src.models.portfolio import TradeAction
from src.paper.constants import NIFTY_UNDERLYING
from src.paper.models import PaperTrade
from src.paper.store import PaperStore

# Explicit logger for the execution module
logger = structlog.get_logger("src.strategy.csp_roll_executor")

# Regex for parsing expiry from Nifty FO instrument keys
_EXPIRY_RE = re.compile(r"NSE_FO\|NIFTY(\d{2}[A-Z]{3}\d{4})(PE|CE)", re.IGNORECASE)


@dataclass
class RollResult:
    """One completed (or dry-run previewed) CSP roll leg."""

    strategy: str
    leg_role: str
    old_instrument_key: str
    old_price: Decimal
    close_price: Decimal
    new_instrument_key: str
    new_price: Decimal
    new_expiry: str
    new_dte: int
    cycle_pnl: Decimal


def _parse_expiry_from_key(instrument_key: str) -> date | None:
    """Parse the option expiry date from a Nifty FO instrument key.

    Args:
        instrument_key: e.g. ``"NSE_FO|NIFTY29MAY2026PE"``.

    Returns:
        Parsed expiry date, or ``None`` if the key is not a Nifty FO option.
    """
    m = _EXPIRY_RE.search(instrument_key)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1).upper(), "%d%b%Y").date()
    except ValueError:
        return None


def _cycle_pnl(existing: PaperTrade, close: PaperTrade) -> Decimal:
    """Compute realised P&L for the closing leg of one CSP cycle.

    For SELL-to-open CSP puts, pnl = (open_price - close_price) * quantity.

    Args:
        existing: The trade that opened the position.
        close:    The trade that closes it (opposite action, same qty).

    Returns:
        Realised cycle P&L as Decimal.
    """
    return (existing.price - close.price) * existing.quantity


async def close_csp_leg(
    broker: BrokerClient,
    store: PaperStore,
    existing: PaperTrade,
    roll_date: date,
    dry_run: bool,
) -> PaperTrade:
    """Fetch live LTP for the existing CSP and build/write a close trade.

    Args:
        broker:    BrokerClient protocol implementation.
        store:     PaperStore.
        existing:  The trade being closed.
        roll_date: Date to record the close trade against.
        dry_run:   If True, build the trade but do not write it.

    Returns:
        The close trade (PaperTrade).
    """
    ltp_resp = await broker.get_ltp([existing.instrument_key])
    raw = ltp_resp.get(existing.instrument_key, Decimal("0"))
    close_price = Decimal(str(raw)).quantize(Decimal("0.01"))
    if close_price <= 0:
        logger.warning(
            "LTP fetch returned 0 for %s — using existing open price as close fallback",
            existing.instrument_key,
        )
        close_price = existing.price

    close_action = TradeAction.BUY if existing.action == TradeAction.SELL else TradeAction.SELL

    close_trade = PaperTrade(
        strategy_name=existing.strategy_name,
        leg_role=existing.leg_role,
        instrument_key=existing.instrument_key,
        trade_date=roll_date,
        action=close_action,
        quantity=existing.quantity,
        price=close_price,
        notes=f"Roll close: expiring {existing.instrument_key}",
    )

    if not dry_run:
        store.record_trade(close_trade)

    logger.info(
        "csp_leg_closed",
        instrument_key=existing.instrument_key,
        leg_role=existing.leg_role,
        entry_price=str(existing.price),
        exit_price=str(close_price),
        quantity=existing.quantity,
        realized_pnl=str(_cycle_pnl(existing, close_trade)),
        dry_run=dry_run,
    )

    return close_trade


async def open_new_csp_leg(
    broker: BrokerClient,
    store: PaperStore,
    lookup: InstrumentLookup,
    strategy: str,
    roll_date: date,
    dry_run: bool,
    quantity: int,
    index: int = 0,
) -> PaperTrade:
    """Select and record the replacement CSP leg.

    Args:
        broker:    BrokerClient protocol implementation.
        store:     PaperStore.
        lookup:    Instrument lookup for expiry candidates.
        strategy:  Strategy name for the new trade.
        roll_date: Date to record the new trade.
        dry_run:   If True, build the trade but do not write it.
        quantity:  Number of contracts to open.
        index:     0-based rank index for candidate selection.

    Returns:
        The newly built PaperTrade.
    """
    expiries = lookup.get_expiry_candidates(
        underlying="NIFTY", today=roll_date, preference=["monthly"]
    )
    if not expiries:
        expiries = lookup.get_expiry_candidates(underlying="NIFTY", today=roll_date)
    if not expiries:
        raise ValueError("No valid expiry candidates found in BOD instrument list.")

    expiry_label, expiry_str = expiries[0]

    raw_data = await broker.get_option_chain(NIFTY_UNDERLYING, expiry_str)
    if not raw_data:
        raise ValueError(f"No option chain data returned for {expiry_str}")

    rows = filter_strikes_by_delta(
        raw_data,
        option_type="PE",
        delta_min=0.20,
        delta_max=0.35,
    )
    if not rows:
        raise ValueError(f"No PE strikes found in delta range [0.20, 0.35] for expiry {expiry_str}")

    for r in rows:
        r["expiry"] = expiry_str
        r["expiry_label"] = expiry_label

    ranked = rank_strikes(rows)
    pick_idx = min(index, len(ranked) - 1)
    selected = ranked[pick_idx]

    new_trade = PaperTrade(
        strategy_name=strategy,
        leg_role="short_put",
        instrument_key=selected["instrument_key"],
        trade_date=roll_date,
        action=TradeAction.SELL,
        quantity=quantity,
        price=Decimal(str(selected["mid"])).quantize(Decimal("0.01")),
        notes=f"Roll open: replacement {selected['instrument_key']}",
    )

    if not dry_run:
        store.record_trade(new_trade)

    logger.info(
        "csp_leg_opened",
        instrument_key=new_trade.instrument_key,
        leg_role=new_trade.leg_role,
        price=str(new_trade.price),
        quantity=new_trade.quantity,
        delta=selected.get("delta"),
        ivr=None,
        dry_run=dry_run,
    )

    return new_trade


async def roll_csp(
    broker: BrokerClient,
    store: PaperStore,
    lookup: InstrumentLookup,
    existing: PaperTrade,
    roll_date: date,
    dry_run: bool,
    index: int = 0,
) -> RollResult:
    """Roll the CSP leg atomically (close + open).

    If the open write fails after the close has been written, the close trade
    is deleted via store.delete_trade to restore the pre-roll position.

    Args:
        broker:    BrokerClient protocol implementation.
        store:     PaperStore.
        lookup:    BOD instrument lookup.
        existing:  The trade being closed/rolled.
        roll_date: Date for the new trades.
        dry_run:   If True, simulate without writing.
        index:     0-based candidate selection rank.

    Returns:
        RollResult describing the completed roll.
    """
    close_trade = await close_csp_leg(broker, store, existing, roll_date, dry_run)
    try:
        open_trade = await open_new_csp_leg(
            broker,
            store,
            lookup,
            existing.strategy_name,
            roll_date,
            dry_run,
            quantity=existing.quantity,
            index=index,
        )
    except Exception as e:
        if not dry_run:
            try:
                store.delete_trade(close_trade)
            except Exception as rollback_err:
                logger.error(
                    "CRITICAL: Failed to rollback close trade %s during roll failure: %s",
                    close_trade.instrument_key,
                    rollback_err,
                    exc_info=True,
                )
        raise e

    expiry_from_key = _parse_expiry_from_key(open_trade.instrument_key)
    new_dte = (expiry_from_key - roll_date).days if expiry_from_key else -1

    return RollResult(
        strategy=existing.strategy_name,
        leg_role=existing.leg_role,
        old_instrument_key=existing.instrument_key,
        old_price=existing.price,
        close_price=close_trade.price,
        new_instrument_key=open_trade.instrument_key,
        new_price=open_trade.price,
        new_expiry=str(expiry_from_key or "?"),
        new_dte=new_dte,
        cycle_pnl=_cycle_pnl(existing, close_trade),
    )

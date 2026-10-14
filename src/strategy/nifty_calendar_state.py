"""Rebuild helpers for NiftyCalendarV1: store positions to structure, quotes and P&L.

Cycle state lives only in ``paper_trades``; every tick the shell rebuilds it
through these functions. Failures raise ``InvalidStructureError`` so the shell
can fail closed with one WARN instead of acting on a half-known structure.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from src.instruments.lookup import InstrumentLookup
from src.models.options import OptionChain, OptionLeg
from src.models.portfolio import AssetType, Direction, TradeAction
from src.nifty_calendar.errors import InvalidStructureError
from src.nifty_calendar.exit_rules import ExitDecision
from src.nifty_calendar.models import CalendarLeg, CalendarStructure, StructureMetrics
from src.nifty_calendar.payoff import compute_metrics, derive_far_carry_from_atm
from src.nifty_calendar.selector import mid
from src.paper.models import PaperPosition, PaperTrade
from src.strategy._price_utils import resolve_option_expiry
from src.strategy.protocol import LegSpec

SHORT_CALL = "short_call"
SHORT_PUT = "short_put"
LONG_CALL_WING = "long_call_wing"
LONG_PUT_WING = "long_put_wing"
ROLES: tuple[str, ...] = (SHORT_CALL, SHORT_PUT, LONG_CALL_WING, LONG_PUT_WING)
_SHORT_ROLES = (SHORT_CALL, SHORT_PUT)


@dataclass(frozen=True)
class OpenLeg:
    """One open structure leg resolved to its strike, expiry and option type."""

    position: PaperPosition
    strike: Decimal
    expiry: date
    option_type: AssetType


def resolve_open_legs(
    positions: list[PaperPosition], lookup: InstrumentLookup
) -> dict[str, OpenLeg]:
    """Map the four structure roles to their open legs.

    Args:
        positions: Open (or flat) positions for the calendar strategy.
        lookup: BOD instrument lookup used to resolve strike, type and expiry.

    Returns:
        Role to OpenLeg for all four roles.

    Raises:
        InvalidStructureError: A role is missing or a key does not resolve.
    """
    by_role = {p.leg_role: p for p in positions if p.net_qty != 0 and p.leg_role in ROLES}
    missing = [r for r in ROLES if r not in by_role]
    if missing:
        raise InvalidStructureError(f"incomplete structure, missing roles: {missing}")
    legs: dict[str, OpenLeg] = {}
    for role, pos in by_role.items():
        inst = lookup.get_by_key(pos.instrument_key)
        expiry = resolve_option_expiry(pos.instrument_key, lookup)
        if inst is None or expiry is None or inst.get("instrument_type") not in ("CE", "PE"):
            raise InvalidStructureError(f"cannot resolve {role} key {pos.instrument_key}")
        legs[role] = OpenLeg(
            position=pos,
            strike=Decimal(str(inst["strike_price"])),
            expiry=expiry,
            option_type=AssetType(inst["instrument_type"]),
        )
    return legs


def cycle_entry_date(legs: dict[str, OpenLeg]) -> date:
    """Entry date of the cycle: the earliest SELL date of the short legs.

    Long wings carry no ``entry_date`` (BUY-only legs), so the shorts decide.
    """
    dates = [legs[r].position.entry_date for r in _SHORT_ROLES]
    known = [d for d in dates if d is not None]
    if not known:
        raise InvalidStructureError("short legs carry no entry_date")
    return min(known)


def is_recentre_close(trade: PaperTrade) -> bool:
    """True for a closing leg written by a re-centre or redeploy decision (``_close_structure`` notes prefix)."""
    return (trade.notes or "").startswith(
        (
            ExitDecision.RECENTRE.value,
            ExitDecision.RECENTRE_OFF_CENTRE.value,
            ExitDecision.REDEPLOY_SAME_PAIR.value,
        )
    )


def is_close_trade(trade: PaperTrade) -> bool:
    """True for a structure-closing leg: a BUY back of a short or a SELL of a long wing."""
    if trade.leg_role in _SHORT_ROLES:
        return trade.action == TradeAction.BUY
    return trade.action == TradeAction.SELL


def sold_short_strikes_on(
    trades: Sequence[PaperTrade], lookup: InstrumentLookup, trade_date: date
) -> frozenset[Decimal]:
    """Strikes of the short legs sold on ``trade_date``.

    ``paper_trades`` is unique on (strategy, role, instrument, date, action), so a same-day
    re-entry at one of these strikes would have its SELL silently dropped. The shell passes
    them to the selector as excluded strikes. Keys the lookup cannot resolve are skipped.

    Args:
        trades: The strategy's ledger.
        lookup: BOD instrument lookup used to resolve each key's strike.
        trade_date: The day the re-entry would be written on.

    Returns:
        The distinct strikes, empty when no short was sold that day.
    """
    strikes: set[Decimal] = set()
    for t in trades:
        if t.trade_date != trade_date or t.action != TradeAction.SELL:
            continue
        if t.leg_role not in _SHORT_ROLES:
            continue
        inst = lookup.get_by_key(t.instrument_key)
        if inst and inst.get("strike_price") is not None:
            strikes.add(Decimal(str(inst["strike_price"])))
    return frozenset(strikes)


def ledger_collisions(
    specs: Sequence[LegSpec], trades: Sequence[PaperTrade], trade_date: date
) -> list[str]:
    """Roles in ``specs`` whose (role, instrument, action) already has a trade on ``trade_date``.

    Such a leg would be dropped by the ledger's unique key, leaving a half-open structure.
    """
    taken = {
        (t.leg_role, t.instrument_key, t.action.value) for t in trades if t.trade_date == trade_date
    }
    return [s.leg_role for s in specs if (s.leg_role, s.instrument_key, s.action) in taken]


def cycle_origin_date(
    trades: Sequence[PaperTrade], entry_date: date, has_window: Callable[[date], bool]
) -> date | None:
    """Entry date of the original cycle that a (possibly re-centred) structure belongs to.

    A cycle runs from its first short-call SELL until a close that is not a re-centre or
    redeploy. Re-entries after a re-centre are part of the same cycle, including one on the
    entry day itself, so the origin is the first short-call SELL after the last real close.
    Its plan (hard day-10, DTE guard) still applies to the re-entry.

    Args:
        trades: The strategy's ledger.
        entry_date: Earliest short-leg SELL date of the structure, or today when flat.
        has_window: True when a date is a policy entry window.

    Returns:
        The original entry date, or None when it is not an entry window or no SELL exists.
    """
    last_close = max(
        (
            t.trade_date
            for t in trades
            if t.leg_role == SHORT_CALL
            and t.action == TradeAction.BUY
            and not is_recentre_close(t)
            and t.trade_date <= entry_date
        ),
        default=None,
    )
    sells = [
        t.trade_date
        for t in trades
        if t.leg_role == SHORT_CALL
        and t.action == TradeAction.SELL
        and t.trade_date <= entry_date
        and (last_close is None or t.trade_date > last_close)
    ]
    origin = min(sells, default=None)
    return origin if origin is not None and has_window(origin) else None


def leg_quotes(legs: dict[str, OpenLeg], chains: dict[date, OptionChain]) -> dict[str, OptionLeg]:
    """Current two-sided quote for every leg.

    Raises:
        InvalidStructureError: A chain or a strike side is missing, or a quote
            is not two-sided.
    """
    quotes: dict[str, OptionLeg] = {}
    for role, leg in legs.items():
        chain = chains.get(leg.expiry)
        row = chain.strikes.get(leg.strike) if chain else None
        side = None if row is None else (row.ce if leg.option_type == AssetType.CE else row.pe)
        if side is None or side.bid <= 0 or side.ask <= 0:
            raise InvalidStructureError(f"no two-sided quote for {role} {leg.strike}")
        quotes[role] = side
    return quotes


def executable_pnl(legs: dict[str, OpenLeg], quotes: dict[str, OptionLeg]) -> Decimal:
    """Rupee P&L if every leg closed at the executable side (buy ask, sell bid)."""
    total = Decimal("0")
    for role, leg in legs.items():
        qty = Decimal(abs(leg.position.net_qty))
        if role in _SHORT_ROLES:
            total += (leg.position.avg_sell_price - quotes[role].ask) * qty
        else:
            total += (quotes[role].bid - leg.position.avg_cost) * qty
    return total


def build_structure(
    legs: dict[str, OpenLeg], quotes: dict[str, OptionLeg], lot_size: int
) -> CalendarStructure:
    """Rebuild a CalendarStructure at current Greeks and original entry prices."""

    def _leg(role: str) -> CalendarLeg:
        leg, pos = legs[role], legs[role].position
        is_short = role in _SHORT_ROLES
        return CalendarLeg(
            instrument_key=pos.instrument_key,
            strike=leg.strike,
            option_type=leg.option_type,
            expiry=leg.expiry,
            side=Direction.SELL if is_short else Direction.BUY,
            qty_lots=abs(pos.net_qty) // lot_size,
            entry_price=pos.avg_sell_price if is_short else pos.avg_cost,
            delta=quotes[role].delta,  # type: ignore[arg-type]  # None rejected by CalendarLeg
            vega=quotes[role].vega,  # type: ignore[arg-type]
            iv=quotes[role].iv,  # type: ignore[arg-type]
        )

    return CalendarStructure(
        short_ce=_leg(SHORT_CALL),
        short_pe=_leg(SHORT_PUT),
        long_ce_wing=_leg(LONG_CALL_WING),
        long_pe_wing=_leg(LONG_PUT_WING),
    )


def far_carry(far_chain: OptionChain, spot: Decimal) -> Decimal:
    """Far-expiry forward carry from the far chain's own ATM put-call parity."""
    if not far_chain.strikes:
        raise InvalidStructureError("far chain has no strikes")
    atm = min(far_chain.strikes, key=lambda k: abs(k - spot))
    row = far_chain.strikes[atm]
    if row.ce is None or row.pe is None:
        raise InvalidStructureError("far ATM missing a side")
    return derive_far_carry_from_atm(atm, mid(row.ce), mid(row.pe), spot)


def entry_leg_specs(
    structure: CalendarStructure, lookup: InstrumentLookup, lot_size: int
) -> list[LegSpec]:
    """Four opening LegSpecs with real Upstox keys; ``price`` carries the mid.

    Raises:
        InvalidStructureError: A leg has no contract in the instrument file.
    """
    roles = (
        (SHORT_CALL, structure.short_ce),
        (SHORT_PUT, structure.short_pe),
        (LONG_CALL_WING, structure.long_ce_wing),
        (LONG_PUT_WING, structure.long_pe_wing),
    )
    specs: list[LegSpec] = []
    for role, leg in roles:
        found = lookup.search_options(
            "NIFTY",
            strike=float(leg.strike),
            option_type=leg.option_type.value,
            expiry=leg.expiry,
            max_results=1,
        )
        if not found:
            raise InvalidStructureError(f"no contract for {role} {leg.expiry} {leg.strike}")
        specs.append(
            LegSpec(
                instrument_key=found[0]["instrument_key"],
                action=leg.side.value,
                quantity=leg.qty_lots * lot_size,
                leg_role=role,
                price=leg.entry_price,
            )
        )
    return specs


@dataclass(frozen=True)
class CalendarView:
    """An open structure rebuilt at current quotes: legs, quotes, metrics and executable P&L."""

    legs: dict[str, OpenLeg]
    quotes: dict[str, OptionLeg]
    structure: CalendarStructure
    metrics: StructureMetrics
    carry: Decimal
    pnl: Decimal

    @property
    def near_expiry(self) -> date:
        """Expiry of the short legs."""
        return self.legs[SHORT_CALL].expiry

    @property
    def far_expiry(self) -> date:
        """Expiry of the long wings."""
        return self.legs[LONG_CALL_WING].expiry


def build_view(
    positions: list[PaperPosition],
    lookup: InstrumentLookup,
    chains: dict[date, OptionChain],
    spot: Decimal,
    lot_size: int,
) -> CalendarView:
    """Rebuild the open structure at the chains' quotes (the shell's exit-path steps, reusable).

    Raises:
        InvalidStructureError: A leg, quote or chain is missing.
        ValueError: A Greek is missing from a quote.
    """
    legs = resolve_open_legs(positions, lookup)
    far_chain = chains.get(legs[LONG_CALL_WING].expiry)
    if far_chain is None:
        raise InvalidStructureError("far chain unavailable")
    quotes = leg_quotes(legs, chains)
    carry = far_carry(far_chain, spot)
    structure = build_structure(legs, quotes, lot_size)
    metrics = compute_metrics(structure, spot, far_carry=carry, lot_size=lot_size)
    return CalendarView(legs, quotes, structure, metrics, carry, executable_pnl(legs, quotes))

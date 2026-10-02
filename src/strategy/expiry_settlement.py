# src/strategy/expiry_settlement.py
"""Settle expired paper option legs at intrinsic value (BUG-060, B060.2).

Nothing else in the paper stack closes a leg at expiry: a leg that reaches
expiry without an exit signal just stops quoting and stays ``OPEN`` forever,
blocking re-entry and poisoning P&L. This module closes every ``OPEN`` /
``DEFENDED`` option leg whose expiry is strictly before ``today`` with a
closing trade at intrinsic value against the official NIFTY 50 close on the
expiry date — how NSE cash-settles index options (DECISIONS.md §"BUG-060 —
expired paper legs settle at intrinsic vs NSE final settlement price").

Fail-closed: a leg whose contract metadata or expiry-date index close cannot
be obtained is left ``OPEN`` and reported in ``SettlementReport.failures`` —
never settled at the last mark.

Split: ``intrinsic_value`` / ``build_settlement_trade`` are pure; the I/O
(``find_expired_legs``, ``fetch_index_close``, ``settle_expired_legs``) wraps
them. Telegram is the entrypoint's job
(``scripts/strategies/three_track/paper_expiry_settle.py``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Any, Literal

import structlog

from src.client.exceptions import DataFetchError
from src.models.portfolio import TradeAction
from src.paper.constants import NIFTY_UNDERLYING
from src.paper.models import PaperTrade, TradeState
from src.strategy._price_utils import resolve_option_expiry

if TYPE_CHECKING:
    from src.client.protocol import BrokerClient
    from src.instruments.lookup import InstrumentLookup
    from src.paper.store import PaperStore

log = structlog.get_logger(__name__)

# NSE minimum tick. PaperTrade.price must be > 0, so a worthless (OTM) expiry
# is booked at one tick — same convention as ic_close_executor._OTM_EXPIRY_PRICE.
SETTLEMENT_PRICE_FLOOR = Decimal("0.05")

_SETTLEABLE_STATES = {TradeState.OPEN, TradeState.DEFENDED}
_CANDLE_LOOKBACK_DAYS = 7

OptionType = Literal["CE", "PE"]


@dataclass(frozen=True)
class ContractSpec:
    """Strike, option type and expiry of one option contract."""

    strike: Decimal
    option_type: OptionType
    expiry: date


@dataclass(frozen=True)
class ExpiredLeg:
    """A non-flat OPEN/DEFENDED option leg whose expiry is before today."""

    strategy_name: str
    leg_role: str
    instrument_key: str
    net_qty: int
    contract: ContractSpec


@dataclass(frozen=True)
class SettlementFailure:
    """A leg left OPEN because settlement could not be computed safely."""

    strategy_name: str
    leg_role: str
    instrument_key: str
    reason: str


@dataclass(frozen=True)
class Settlement:
    """A leg closed (or, on dry-run, that would be closed) at intrinsic."""

    leg: ExpiredLeg
    index_close: Decimal
    trade: PaperTrade


@dataclass
class SettlementReport:
    """Outcome of one settlement run."""

    settled: list[Settlement] = field(default_factory=list)
    failures: list[SettlementFailure] = field(default_factory=list)


# ── Pure computation ─────────────────────────────────────────────────────


def intrinsic_value(option_type: OptionType, strike: Decimal, index_close: Decimal) -> Decimal:
    """Return expiry intrinsic value: put ``max(0, K − S)``, call ``max(0, S − K)``.

    Args:
        option_type: ``"CE"`` or ``"PE"``.
        strike: Contract strike ``K``.
        index_close: Official NIFTY 50 close ``S`` on the expiry date.

    Returns:
        Non-negative intrinsic value per unit.

    Raises:
        ValueError: If ``option_type`` is not CE/PE.
    """
    if option_type == "PE":
        return max(Decimal("0"), strike - index_close)
    if option_type == "CE":
        return max(Decimal("0"), index_close - strike)
    raise ValueError(f"option_type must be CE or PE, got {option_type!r}")


def build_settlement_trade(leg: ExpiredLeg, index_close: Decimal) -> PaperTrade:
    """Build the closing trade that flattens ``leg`` at intrinsic value.

    Long legs close with a SELL, short legs with a BUY, for ``|net_qty|``
    units, dated the expiry date. Price is intrinsic floored at
    ``SETTLEMENT_PRICE_FLOOR`` (``PaperTrade.price`` must be positive).

    Args:
        leg: The expired leg to flatten.
        index_close: Official NIFTY 50 close on the expiry date.

    Returns:
        The closing ``PaperTrade``.

    Raises:
        ValueError: If ``leg.net_qty`` is zero (nothing to settle).
    """
    if leg.net_qty == 0:
        raise ValueError(f"leg {leg.leg_role} {leg.instrument_key} is already flat")
    c = leg.contract
    intrinsic = intrinsic_value(c.option_type, c.strike, index_close)
    return PaperTrade(
        strategy_name=leg.strategy_name,
        leg_role=leg.leg_role,
        instrument_key=leg.instrument_key,
        trade_date=c.expiry,
        action=TradeAction.SELL if leg.net_qty > 0 else TradeAction.BUY,
        quantity=abs(leg.net_qty),
        price=max(intrinsic, SETTLEMENT_PRICE_FLOOR),
        notes=(
            f"expiry_settlement (BUG-060): {c.option_type} K={c.strike} "
            f"S={index_close} intrinsic={intrinsic} expiry={c.expiry.isoformat()}"
        ),
    )


# ── I/O ──────────────────────────────────────────────────────────────────


def resolve_contract(instrument_key: str, lookup: InstrumentLookup) -> ContractSpec | None:
    """Resolve a NIFTY option key to its contract spec via the BOD master.

    Args:
        instrument_key: Upstox key, e.g. ``NSE_FO|73994``.
        lookup: BOD instrument master.

    Returns:
        ``ContractSpec``, or ``None`` when the key is absent from BOD, is not
        a NIFTY CE/PE, or has an unparseable strike/expiry.
    """
    inst = lookup.get_by_key(instrument_key)
    if inst is None:
        return None
    option_type = str(inst.get("instrument_type") or "").upper()
    underlying = str(inst.get("underlying_symbol") or "").upper()
    if option_type not in ("CE", "PE") or underlying != "NIFTY":
        return None
    expiry = resolve_option_expiry(instrument_key, lookup)
    try:
        strike = Decimal(str(inst.get("strike_price")))
    except InvalidOperation:
        return None
    if expiry is None or not strike.is_finite():
        return None
    return ContractSpec(strike=strike, option_type=option_type, expiry=expiry)  # type: ignore[arg-type]


def _settleable_keys(store: PaperStore, strategy_name: str) -> set[tuple[str, str]]:
    """Return ``(leg_role, instrument_key)`` pairs with an OPEN/DEFENDED row."""
    return {
        (t.leg_role, t.instrument_key)
        for t in store.get_trades(strategy_name)
        if t.state in _SETTLEABLE_STATES
    }


def find_expired_legs(
    store: PaperStore,
    lookup: InstrumentLookup,
    today: date,
    overrides: dict[str, ContractSpec] | None = None,
) -> tuple[list[ExpiredLeg], list[SettlementFailure]]:
    """Find non-flat OPEN/DEFENDED ``NSE_FO`` legs with expiry before ``today``.

    Args:
        store: Paper ledger.
        lookup: BOD instrument master.
        today: Settlement run date; legs expiring on or after it are untouched.
        overrides: Operator-supplied contract specs keyed by instrument key,
            used when an expired contract has already dropped out of BOD.

    Returns:
        ``(expired_legs, failures)`` — failures are ``NSE_FO`` legs whose
        contract could not be resolved (left OPEN, must be surfaced).
    """
    overrides = overrides or {}
    expired: list[ExpiredLeg] = []
    failures: list[SettlementFailure] = []
    for strategy in store.get_strategy_names():
        live = _settleable_keys(store, strategy)
        for pos in store.get_positions(strategy):
            key = pos.instrument_key
            if not key.startswith("NSE_FO|") or (pos.leg_role, key) not in live:
                continue
            contract = overrides.get(key) or resolve_contract(key, lookup)
            if contract is None:
                if _is_bod_non_option(key, lookup):
                    continue
                log.warning(
                    "expiry_settlement.contract_unresolved",
                    strategy=strategy,
                    leg_role=pos.leg_role,
                    instrument_key=key,
                )
                failures.append(
                    SettlementFailure(strategy, pos.leg_role, key, "contract not resolvable")
                )
                continue
            if contract.expiry < today:
                expired.append(ExpiredLeg(strategy, pos.leg_role, key, pos.net_qty, contract))
    return expired, failures


def _is_bod_non_option(instrument_key: str, lookup: InstrumentLookup) -> bool:
    """True when BOD knows the key and it is not a CE/PE (e.g. a live future)."""
    inst = lookup.get_by_key(instrument_key)
    return inst is not None and str(inst.get("instrument_type") or "").upper() not in ("CE", "PE")


async def fetch_index_close(broker: BrokerClient, on: date) -> Decimal | None:
    """Fetch the official NIFTY 50 daily close for exactly ``on``.

    Args:
        broker: Client exposing ``get_historical_candles``.
        on: The expiry date.

    Returns:
        The close as ``Decimal``, or ``None`` when no candle dated ``on`` is
        returned or the fetch/parse fails (callers must fail closed).
    """
    params = {
        "instrument_key": NIFTY_UNDERLYING,
        "interval": "day",
        "to_date": on.isoformat(),
        "from_date": (on - timedelta(days=_CANDLE_LOOKBACK_DAYS)).isoformat(),
    }
    try:
        # Rows are positional [ts, o, h, l, c, v, oi] lists; the protocol's
        # Candle alias still says dict (TD-7), hence list[Any].
        candles: list[Any] = await broker.get_historical_candles(params)
        row = next((c for c in candles if str(c[0])[:10] == on.isoformat()), None)
        if row is None:
            log.warning("expiry_settlement.no_candle", on=on.isoformat(), count=len(candles))
            return None
        close = Decimal(str(row[4]))
    except (DataFetchError, IndexError, TypeError, ValueError, InvalidOperation) as exc:
        log.warning("expiry_settlement.close_fetch_failed", on=on.isoformat(), error=str(exc))
        return None
    if not close.is_finite() or close <= 0:
        log.warning("expiry_settlement.bad_close", on=on.isoformat(), close=str(close))
        return None
    return close


async def settle_expired_legs(
    store: PaperStore,
    broker: BrokerClient,
    lookup: InstrumentLookup,
    today: date,
    *,
    dry_run: bool = True,
    overrides: dict[str, ContractSpec] | None = None,
) -> SettlementReport:
    """Close every expired OPEN/DEFENDED option leg at intrinsic value.

    Idempotent: a settled leg is flat, so a re-run finds nothing; a closing
    trade swallowed by ``record_trade``'s duplicate guard is reported as a
    failure and the leg is not marked closed.

    Args:
        store: Paper ledger.
        broker: Price source for the expiry-date NIFTY 50 close.
        lookup: BOD instrument master.
        today: Run date (IST). Only expiries strictly before it settle.
        dry_run: Compute and report without writing.
        overrides: Operator contract specs for keys missing from BOD.

    Returns:
        ``SettlementReport`` of settled legs and fail-closed legs.
    """
    legs, failures = find_expired_legs(store, lookup, today, overrides)
    report = SettlementReport(failures=failures)
    closes: dict[date, Decimal | None] = {}
    for leg in legs:
        expiry = leg.contract.expiry
        if expiry not in closes:
            closes[expiry] = await fetch_index_close(broker, expiry)
        close = closes[expiry]
        if close is None:
            report.failures.append(_failure(leg, f"no NIFTY 50 close for {expiry.isoformat()}"))
            continue
        trade = build_settlement_trade(leg, close)
        if not dry_run and not store.record_trade(trade):
            report.failures.append(_failure(leg, "closing trade blocked by duplicate guard"))
            continue
        if not dry_run:
            store.mark_trade_closed(leg.strategy_name, leg.leg_role, leg.instrument_key)
        log.info(
            "expiry_settlement.settled",
            strategy=leg.strategy_name,
            leg_role=leg.leg_role,
            instrument_key=leg.instrument_key,
            index_close=str(close),
            price=str(trade.price),
            action=trade.action.value,
            quantity=trade.quantity,
            dry_run=dry_run,
        )
        report.settled.append(Settlement(leg=leg, index_close=close, trade=trade))
    return report


def _failure(leg: ExpiredLeg, reason: str) -> SettlementFailure:
    log.warning(
        "expiry_settlement.left_open",
        strategy=leg.strategy_name,
        leg_role=leg.leg_role,
        instrument_key=leg.instrument_key,
        reason=reason,
    )
    return SettlementFailure(leg.strategy_name, leg.leg_role, leg.instrument_key, reason)

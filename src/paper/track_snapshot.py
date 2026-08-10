"""Core logic for producing the daily structured output for the three tracks."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any, cast

import structlog

from src.client.protocol import BrokerClient
from src.client.upstox_market import parse_upstox_option_chain
from src.instruments.lookup import InstrumentLookup, parse_expiry
from src.models.options import OptionChain
from src.models.portfolio import TradeAction
from src.paper.metrics import (
    NIFTYBEES_BETA_TO_NIFTY,
    compute_cycle_max_drawdown,
    compute_return_on_nee,
)
from src.paper.proxy_monitor import ProxyDeltaMonitor
from src.paper.store import PaperStore
from src.paper.tracker import _compute_leg_unrealized_pnl

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class TrackGreeks:
    net_delta: Decimal
    net_theta: Decimal
    net_vega: Decimal


@dataclass(frozen=True)
class TrackPnL:
    """Base-leg-only P&L for one 3-track strategy.

    BUG-028 (2026-08-10): overlay legs (CC/PP/Collar) are no longer
    discovered or attributed here — they live under the independent
    ``STRATEGY_OVERLAY`` strategy_name since S2r (2026-07-29) and are
    computed by ``scripts/strategies/three_track/paper_3track_snapshot.py``'s
    standalone overlay pipeline instead. ``net_pnl`` therefore always equals
    ``base_pnl`` for a track; the field is kept (rather than dropped) because
    downstream consumers (NAV snapshot persistence, max-DD/Ret-on-NEE calc)
    already read ``pnl.net_pnl`` as "this track's own P&L."
    """

    base_pnl: Decimal
    net_pnl: Decimal
    unrealized_pnl: Decimal
    realized_pnl: Decimal


@dataclass(frozen=True)
class TrackSnapshot:
    track_name: str
    pnl: TrackPnL
    greeks: TrackGreeks
    max_drawdown_abs: Decimal
    max_drawdown_pct: Decimal
    return_on_nee: Decimal
    proxy_delta_state: str | None = None
    proxy_delta_alert: str | None = None


def _compute_realized_pnl_by_leg(store: PaperStore, strategy_name: str) -> dict[str, Decimal]:
    """Compute cumulative realized P&L per leg_role."""
    trades = store.get_trades(strategy_name)
    realized_by_leg: dict[str, Decimal] = {}

    if not trades:
        return realized_by_leg

    for leg_role in {t.leg_role for t in trades}:
        leg_trades = [t for t in trades if t.leg_role == leg_role]
        total_buy_qty = sum(t.quantity for t in leg_trades if t.action == TradeAction.BUY)
        total_sell_qty = sum(t.quantity for t in leg_trades if t.action == TradeAction.SELL)
        closed_qty = min(total_buy_qty, total_sell_qty)

        if closed_qty == 0:
            realized_by_leg[leg_role] = Decimal("0")
            continue

        buy_total = sum(t.price * t.quantity for t in leg_trades if t.action == TradeAction.BUY)
        sell_total = sum(t.price * t.quantity for t in leg_trades if t.action == TradeAction.SELL)

        buy_avg = buy_total / Decimal(str(total_buy_qty)) if total_buy_qty else Decimal("0")
        sell_avg = sell_total / Decimal(str(total_sell_qty)) if total_sell_qty else Decimal("0")

        realized_by_leg[leg_role] = (sell_avg - buy_avg) * Decimal(str(closed_qty))

    return realized_by_leg


async def resolve_leg_delta(
    pos: Any,
    lookup: InstrumentLookup,
    broker: BrokerClient,
    fetched_chains: dict[str, OptionChain | None],
) -> tuple[Decimal, Decimal, Decimal]:
    """Resolve (delta, theta, vega) for one open leg — the single Greeks source.

    Shared by ``generate_track_snapshot`` (display/EOD snapshot) and
    ``src.portfolio.overlay_coverage.compute_overlay_coverage`` (S3r query-time
    coverage ratio) so there is exactly one place that fetches live chain
    Greeks — duplicating this fetch was explicitly flagged as a risk in
    docs/plan/3track-consolidation/stories.md S3r.

    ``base_etf``/``base_futures`` use fixed beta/delta assumptions (NiftyBees
    tracks Nifty ≈1:1; futures delta is definitionally 1.0). ``base_ditm_call``
    and any ``overlay_*`` role resolve delta live from the option chain,
    since both drift with spot/time and must never be assumed.

    Args:
        pos: PaperPosition for the leg (must have net_qty != 0 for a
            meaningful result — flat legs resolve to zero delta via the
            chain-lookup miss path, same as an unresolvable instrument).
        lookup: BOD instrument lookup for expiry/strike/type resolution.
        broker: BrokerClient used to fetch the live option chain on a
            per-expiry cache-miss basis.
        fetched_chains: Mutable per-call cache, keyed by parsed expiry
            string — passed in by the caller so multiple legs sharing an
            expiry only fetch the chain once.

    Returns:
        (delta, theta, vega) tuple, each zero if the leg's instrument or
        strike can't be resolved (never raises — matches the pre-refactor
        behavior in the ``generate_track_snapshot`` loop body).
    """
    is_overlay = pos.leg_role.startswith("overlay_")

    if pos.leg_role == "base_etf":
        return NIFTYBEES_BETA_TO_NIFTY, Decimal("0"), Decimal("0")
    if pos.leg_role == "base_futures":
        return Decimal("1.0"), Decimal("0"), Decimal("0")
    if pos.leg_role != "base_ditm_call" and not is_overlay:
        return Decimal("0"), Decimal("0"), Decimal("0")

    inst = lookup.get_by_key(pos.instrument_key)
    if not inst:
        return Decimal("0"), Decimal("0"), Decimal("0")

    expiry = inst.get("expiry")
    parsed_expiry = parse_expiry(expiry)
    strike = Decimal(str(inst.get("strike_price", 0)))
    opt_type = inst.get("instrument_type")

    if not parsed_expiry or strike <= Decimal("0"):
        return Decimal("0"), Decimal("0"), Decimal("0")

    if parsed_expiry not in fetched_chains:
        underlying = "NSE_INDEX|Nifty 50"  # assumption for Nifty 50 options
        try:
            raw_chain = await broker.get_option_chain(underlying, parsed_expiry)
            fetched_chains[parsed_expiry] = parse_upstox_option_chain(
                cast(list[dict[str, Any]], raw_chain)
            )
        # Intentional: isolate LTP fetch errors for single legs.
        except Exception:
            fetched_chains[parsed_expiry] = None

    chain = fetched_chains[parsed_expiry]
    if not (chain and strike in chain.strikes):
        return Decimal("0"), Decimal("0"), Decimal("0")

    strike_data = chain.strikes[strike]
    leg_data = strike_data.ce if opt_type == "CE" else strike_data.pe
    if not leg_data:
        return Decimal("0"), Decimal("0"), Decimal("0")

    return (
        leg_data.delta or Decimal("0"),
        leg_data.theta or Decimal("0"),
        leg_data.vega or Decimal("0"),
    )


async def generate_track_snapshot(
    store: PaperStore,
    broker: BrokerClient,
    lookup: InstrumentLookup,
    track_namespace: str,
    nifty_spot: Decimal,
    nee: Decimal,
    snapshot_date: date,
    proxy_monitor: ProxyDeltaMonitor | None = None,
) -> TrackSnapshot:
    """Generate the structured daily snapshot for a track's own base leg.

    BUG-028 (2026-08-10): reports base-leg P&L only. Overlay legs (CC/PP/
    Collar) are no longer discovered here — they live under the independent
    ``STRATEGY_OVERLAY`` strategy_name since S2r (2026-07-29) and are
    computed by the standalone overlay pipeline in
    ``scripts/strategies/three_track/paper_3track_snapshot.py`` instead. A
    track's own trades/positions can still legitimately include a leftover
    ``overlay_*``-role row from before S2r shipped (not yet closed/rolled
    off) — those rows are intentionally skipped here, not attributed to this
    track's P&L or Greeks; Phase 3's historical repair script reattributes
    them to ``STRATEGY_OVERLAY`` directly rather than this function
    re-discovering them.

    Fetches live Greeks from the Upstox chain for base legs, assigns fixed
    NiftyBees/Futures deltas, and computes return on NEE and max DD.
    """
    trades = store.get_trades(track_namespace)
    if not trades:
        return TrackSnapshot(
            track_name=track_namespace,
            pnl=TrackPnL(Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0")),
            greeks=TrackGreeks(Decimal("0"), Decimal("0"), Decimal("0")),
            max_drawdown_abs=Decimal("0"),
            max_drawdown_pct=Decimal("0"),
            return_on_nee=Decimal("0"),
        )

    leg_roles = {t.leg_role for t in trades if t.leg_role.startswith("base_")}
    positions = [store.get_position(track_namespace, role) for role in leg_roles]
    open_positions = [p for p in positions if p is not None and p.net_qty != 0]

    instrument_keys = [p.instrument_key for p in open_positions if p.instrument_key]
    prices = {}
    if instrument_keys:
        prices = await broker.get_ltp(instrument_keys)

    realized_by_leg = _compute_realized_pnl_by_leg(store, track_namespace)

    base_pnl = Decimal("0")
    total_unrealized = Decimal("0")
    total_realized = Decimal("0")

    net_delta = Decimal("0")
    net_theta = Decimal("0")
    net_vega = Decimal("0")

    proxy_state = None
    proxy_alert = None
    proxy_base_leg_delta = None

    fetched_chains: dict[str, OptionChain | None] = {}

    for pos in open_positions:
        raw_ltp = prices.get(pos.instrument_key)
        if raw_ltp is None:
            logger.warning(
                "LTP unavailable for %s (%s) — likely expired. Skipping MTM for this leg.",
                pos.instrument_key,
                pos.leg_role,
            )
            unrealized = Decimal("0")
        else:
            ltp = Decimal(str(raw_ltp))
            unrealized = _compute_leg_unrealized_pnl(pos, ltp)
        leg_realized = realized_by_leg.get(pos.leg_role, Decimal("0"))
        leg_total_pnl = unrealized + leg_realized

        total_unrealized += unrealized
        total_realized += leg_realized
        base_pnl += leg_total_pnl

        leg_delta, leg_theta, leg_vega = await resolve_leg_delta(
            pos, lookup, broker, fetched_chains
        )

        qty_d = Decimal(str(pos.net_qty))

        net_delta += leg_delta * qty_d
        net_theta += leg_theta * qty_d
        net_vega += leg_vega * qty_d

        if pos.leg_role == "base_ditm_call":
            proxy_base_leg_delta = leg_delta

    if proxy_monitor and proxy_base_leg_delta is not None:
        state_label, consecutive = proxy_monitor.update_and_check(
            proxy_base_leg_delta, snapshot_date
        )
        proxy_state = state_label
        if state_label == "CRITICAL":
            proxy_alert = f"CRITICAL (<0.40, day {consecutive} of 3+)"
        elif state_label == "WARNING":
            proxy_alert = "WARNING (<0.65)"
        else:
            proxy_alert = "OK"

    net_pnl = base_pnl

    # Calculate Max DD and Return on NEE
    nav_snapshots = store.get_nav_snapshots(track_namespace)
    nav_history = [s.total_pnl for s in nav_snapshots]
    if not nav_history or nav_history[-1] != net_pnl:
        nav_history.append(net_pnl)

    max_dd_abs, max_dd_pct = compute_cycle_max_drawdown(nav_history, nee)
    ret_on_nee = compute_return_on_nee(net_pnl, nee)

    return TrackSnapshot(
        track_name=track_namespace,
        pnl=TrackPnL(
            base_pnl,
            net_pnl,
            total_unrealized,
            total_realized,
        ),
        greeks=TrackGreeks(net_delta, net_theta, net_vega),
        max_drawdown_abs=max_dd_abs,
        max_drawdown_pct=max_dd_pct,
        return_on_nee=ret_on_nee,
        proxy_delta_state=proxy_state,
        proxy_delta_alert=proxy_alert,
    )

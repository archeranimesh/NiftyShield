"""Core logic for producing the daily structured output for the three tracks."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
import logging

from src.client.protocol import BrokerClient
from src.client.upstox_market import parse_upstox_option_chain
from src.instruments.lookup import InstrumentLookup
from src.models.portfolio import TradeAction
from src.paper.metrics import (
    NIFTYBEES_BETA_TO_NIFTY,
    compute_cycle_max_drawdown,
    compute_return_on_nee,
)
from src.paper.proxy_monitor import ProxyDeltaMonitor
from src.paper.store import PaperStore
from src.paper.tracker import _compute_leg_unrealized_pnl

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TrackGreeks:
    net_delta: Decimal
    net_theta: Decimal
    net_vega: Decimal


@dataclass(frozen=True)
class TrackPnL:
    base_pnl: Decimal
    overlay_pnls: dict[str, Decimal]  # e.g., {'overlay_pp': Decimal("-100"), ...}
    net_pnl: Decimal


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


async def generate_track_snapshot(
    store: PaperStore,
    broker: BrokerClient,
    lookup: InstrumentLookup,
    track_namespace: str,
    nifty_spot: Decimal,
    nee: Decimal,
    snapshot_date: date,
    proxy_monitor: ProxyDeltaMonitor | None = None
) -> TrackSnapshot:
    """Generate the structured daily snapshot for a track.
    
    Separates base vs overlay P&L by filtering leg_role prefixes,
    fetches live Greeks from Upstox chain, assigns base NiftyBees/Futures deltas,
    and computes return on NEE and max DD.
    """
    trades = store.get_trades(track_namespace)
    if not trades:
        return TrackSnapshot(
            track_name=track_namespace,
            pnl=TrackPnL(Decimal("0"), {}, Decimal("0")),
            greeks=TrackGreeks(Decimal("0"), Decimal("0"), Decimal("0")),
            max_drawdown_abs=Decimal("0"),
            max_drawdown_pct=Decimal("0"),
            return_on_nee=Decimal("0")
        )
        
    leg_roles = {t.leg_role for t in trades}
    positions = [store.get_position(track_namespace, role) for role in leg_roles]
    open_positions = [p for p in positions if p.net_qty != 0]
    
    instrument_keys = [p.instrument_key for p in open_positions if p.instrument_key]
    prices = {}
    if instrument_keys:
        prices = await broker.get_ltp(instrument_keys)
        
    realized_by_leg = _compute_realized_pnl_by_leg(store, track_namespace)
    
    base_pnl = Decimal("0")
    overlay_pnls: dict[str, Decimal] = {}
    
    net_delta = Decimal("0")
    net_theta = Decimal("0")
    net_vega = Decimal("0")
    
    proxy_state = None
    proxy_alert = None
    
    fetched_chains: dict[str, parse_upstox_option_chain] = {}
    
    for pos in open_positions:
        is_base = pos.leg_role.startswith("base_")
        is_overlay = pos.leg_role.startswith("overlay_")
        
        raw_ltp = prices.get(pos.instrument_key, 0.0)
        ltp = Decimal(str(raw_ltp))
        unrealized = _compute_leg_unrealized_pnl(pos, ltp)
        leg_total_pnl = unrealized + realized_by_leg.get(pos.leg_role, Decimal("0"))
        
        if is_base:
            base_pnl += leg_total_pnl
        elif is_overlay:
            overlay_pnls[pos.leg_role] = overlay_pnls.get(pos.leg_role, Decimal("0")) + leg_total_pnl
            
        leg_delta = Decimal("0")
        leg_theta = Decimal("0")
        leg_vega = Decimal("0")
        
        if pos.leg_role == "base_etf":
            leg_delta = NIFTYBEES_BETA_TO_NIFTY
        elif pos.leg_role == "base_futures":
            leg_delta = Decimal("1.0")
        elif pos.leg_role == "base_ditm_call" or is_overlay:
            inst = lookup.get_by_key(pos.instrument_key)
            if inst:
                expiry = inst.get("expiry")
                from src.instruments.lookup import _parse_expiry
                parsed_expiry = _parse_expiry(expiry)
                strike = Decimal(str(inst.get("strike_price", 0)))
                opt_type = inst.get("instrument_type")
                
                if parsed_expiry and strike > Decimal("0"):
                    if parsed_expiry not in fetched_chains:
                        underlying = "NSE_INDEX|Nifty 50" # assumption for Nifty 50 options
                        try:
                            raw_chain = await broker.get_option_chain(underlying, parsed_expiry)
                            fetched_chains[parsed_expiry] = parse_upstox_option_chain(raw_chain)
                        except Exception:
                            fetched_chains[parsed_expiry] = None
                            
                    chain = fetched_chains[parsed_expiry]
                    if chain and strike in chain.strikes:
                        strike_data = chain.strikes[strike]
                        leg_data = strike_data.ce if opt_type == "CE" else strike_data.pe
                        if leg_data:
                            leg_delta = leg_data.delta
                            leg_theta = leg_data.theta
                            leg_vega = leg_data.vega
                            
        qty_d = Decimal(str(pos.net_qty))
        
        net_delta += leg_delta * qty_d
        net_theta += leg_theta * qty_d
        net_vega += leg_vega * qty_d
        
        if pos.leg_role == "base_ditm_call" and proxy_monitor:
            # Note: pass the single-unit delta to monitor, not net_delta
            state_label, consecutive = proxy_monitor.update_and_check(leg_delta, snapshot_date)
            proxy_state = state_label
            if state_label == "CRITICAL":
                proxy_alert = f"CRITICAL (<0.40, day {consecutive} of 3+)"
            elif state_label == "WARNING":
                proxy_alert = f"WARNING (<0.65)"
            else:
                proxy_alert = "OK"
                
    net_pnl = base_pnl + sum(overlay_pnls.values())
    
    # Calculate Max DD and Return on NEE
    nav_snapshots = store.get_nav_snapshots(track_namespace)
    nav_history = [s.total_pnl for s in nav_snapshots]
    if not nav_history or nav_history[-1] != net_pnl:
        nav_history.append(net_pnl)
        
    max_dd_abs, max_dd_pct = compute_cycle_max_drawdown(nav_history, nee)
    ret_on_nee = compute_return_on_nee(net_pnl, nee)
    
    return TrackSnapshot(
        track_name=track_namespace,
        pnl=TrackPnL(base_pnl, overlay_pnls, net_pnl),
        greeks=TrackGreeks(net_delta, net_theta, net_vega),
        max_drawdown_abs=max_dd_abs,
        max_drawdown_pct=max_dd_pct,
        return_on_nee=ret_on_nee,
        proxy_delta_state=proxy_state,
        proxy_delta_alert=proxy_alert
    )

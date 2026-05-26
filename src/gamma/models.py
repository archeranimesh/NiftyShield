"""Data models for near-expiry gamma strategy.

All monetary, Greek, and numeric/derived values use Decimal (stored as TEXT in SQLite)
to preserve precision.
"""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal


@dataclass(frozen=True)
class GammaChainSnapshot:
    """Represents a single row in the gamma_chain_snapshots table.

    Attributes:
        snapshot_date: Date of the snapshot (YYYY-MM-DD).
        snapshot_time: Time of the snapshot (HH:MM).
        expiry_date: Expiry date of the options contract.
        strike: Option strike price.
        option_type: Option type ('CE' or 'PE').
        dte_calendar: Days to expiry (calendar).
        nifty_spot: Nifty 50 spot price.
        nifty_futures: Nifty futures price (optional).
        india_vix: India VIX value (optional).
        delta_val: Option Delta (optional).
        gamma_val: Option Gamma (optional).
        vega_val: Option Vega (optional).
        theta_val: Option Theta (optional).
        iv_val: Option Implied Volatility (optional).
        gamma_gearing: Computed gamma gearing (optional).
        distance_pct: Distance to strike as a percentage of spot (optional).
        best_bid: Best bid price (optional).
        best_ask: Best ask price (optional).
        bid_ask_spread: Bid-ask spread (optional).
        oi: Open interest in contracts (optional).
        oi_change_1d: Open interest fractional change vs prior day (optional).
        volume_day: Daily cumulative volume (optional).
        strike_iv_pctile_20d: Percentile rank of IV vs prior 20 days (optional).
        gamma_gearing_pctile_dte: Percentile rank of gearing by DTE (optional).
        created_at: Creation timestamp in UTC.
    """

    snapshot_date: date
    snapshot_time: str
    expiry_date: date
    strike: int
    option_type: str
    dte_calendar: int
    nifty_spot: Decimal
    nifty_futures: Decimal | None
    india_vix: Decimal | None
    delta_val: Decimal | None
    gamma_val: Decimal | None
    vega_val: Decimal | None
    theta_val: Decimal | None
    iv_val: Decimal | None
    gamma_gearing: Decimal | None
    distance_pct: Decimal | None
    best_bid: Decimal | None
    best_ask: Decimal | None
    bid_ask_spread: Decimal | None
    oi: int | None
    oi_change_1d: Decimal | None
    volume_day: int | None
    strike_iv_pctile_20d: Decimal | None
    gamma_gearing_pctile_dte: Decimal | None
    created_at: datetime


@dataclass(frozen=True)
class GammaWatchlistEntry:
    """Represents a single row in the gamma_watchlist table.

    Attributes:
        expiry_date: Expiry date of the option contract.
        strike: Option strike price.
        option_type: Option type ('CE' or 'PE').
        added_date: Date the strike was first added to the watchlist.
        last_seen_date: Date the strike was last seen/re-evaluated.
        removed_date: Date the strike was removed from the watchlist (optional).
        removal_reason: Reason for removal (optional).
        distance_pct: Distance to strike as percentage of spot at last evaluation (optional).
        gamma_gearing: Gamma gearing at last evaluation (optional).
        oi: Open interest at last evaluation (optional).
        oi_change_1d: Open interest fractional change vs prior day at last evaluation (optional).
        days_on_watchlist: Total days the strike has been on the watchlist.
        elevated: Whether the strike is elevated (priority candidate).
        elevation_reason: Reason for elevation (optional).
    """

    expiry_date: date
    strike: int
    option_type: str
    added_date: date
    last_seen_date: date
    removed_date: date | None
    removal_reason: str | None
    distance_pct: Decimal | None
    gamma_gearing: Decimal | None
    oi: int | None
    oi_change_1d: Decimal | None
    days_on_watchlist: int
    elevated: bool
    elevation_reason: str | None

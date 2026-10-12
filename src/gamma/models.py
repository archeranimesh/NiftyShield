"""Data models for near-expiry gamma strategy.

All monetary, Greek, and numeric/derived values use Decimal
(stored as TEXT in SQLite) to preserve precision.
"""

import dataclasses
import datetime
import decimal
import typing


@dataclasses.dataclass(frozen=True)
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
        distance_pct: Distance to strike as a % of spot (optional).
        best_bid: Best bid price (optional).
        best_ask: Best ask price (optional).
        bid_ask_spread: Bid-ask spread (optional).
        oi: Open interest in contracts (optional).
        oi_change_1d: Fractional change in OI vs prior day (optional).
        volume_day: Daily cumulative volume (optional).
        strike_iv_pctile_20d: IV percentile rank vs prior 20 days
            (optional).
        gamma_gearing_pctile_dte: Percentile rank of gearing by DTE
            (optional).
        created_at: Creation timestamp in UTC (must be timezone-aware).
    """

    snapshot_date: datetime.date
    snapshot_time: str
    expiry_date: datetime.date
    strike: int
    option_type: typing.Literal["CE", "PE"]
    dte_calendar: int
    nifty_spot: decimal.Decimal
    nifty_futures: decimal.Decimal | None
    india_vix: decimal.Decimal | None
    delta_val: decimal.Decimal | None
    gamma_val: decimal.Decimal | None
    vega_val: decimal.Decimal | None
    theta_val: decimal.Decimal | None
    iv_val: decimal.Decimal | None
    gamma_gearing: decimal.Decimal | None
    distance_pct: decimal.Decimal | None
    best_bid: decimal.Decimal | None
    best_ask: decimal.Decimal | None
    bid_ask_spread: decimal.Decimal | None
    oi: int | None
    oi_change_1d: decimal.Decimal | None
    volume_day: int | None
    strike_iv_pctile_20d: decimal.Decimal | None
    gamma_gearing_pctile_dte: decimal.Decimal | None
    created_at: datetime.datetime


@dataclasses.dataclass(frozen=True)
class GammaWatchlistEntry:
    """Represents a single row in the gamma_watchlist table.

    Attributes:
        expiry_date: Expiry date of the option contract.
        strike: Option strike price.
        option_type: Option type ('CE' or 'PE').
        added_date: Date the strike was first added to the watchlist.
        last_seen_date: Date the strike was last seen/re-evaluated.
        removed_date: Date the strike was removed from watchlist
            (optional).
        removal_reason: Reason for removal (optional).
        distance_pct: Distance to strike at last evaluation (optional).
        gamma_gearing: Gamma gearing at last evaluation (optional).
        oi: Open interest at last evaluation (optional).
        oi_change_1d: Fractional change in OI vs prior day (optional).
        days_on_watchlist: Total days the strike has been on the
            watchlist.
        elevated: Whether the strike is elevated (priority candidate).
        elevation_reason: Reason for elevation (optional).
    """

    expiry_date: datetime.date
    strike: int
    option_type: typing.Literal["CE", "PE"]
    added_date: datetime.date
    last_seen_date: datetime.date
    removed_date: datetime.date | None
    removal_reason: str | None
    distance_pct: decimal.Decimal | None
    gamma_gearing: decimal.Decimal | None
    oi: int | None
    oi_change_1d: decimal.Decimal | None
    days_on_watchlist: int
    elevated: bool
    elevation_reason: str | None


@dataclasses.dataclass(frozen=True)
class GammaSignalLogEntry:
    """Represents a single row in the gamma_signal_log table.

    Captures every 5-minute evaluation of candidate strikes during Near-Expiry
    Gamma Buy Phase B scans (including passed and failed filter evaluations).
    All monetary, Greek, and numeric/derived values use Decimal to preserve
    precision. Timestamps must be timezone-aware in UTC.
    """

    signal_id: str
    signal_timestamp: datetime.datetime
    expiry_date: datetime.date
    strike: int
    option_type: typing.Literal["CE", "PE"]
    dte_calendar: int
    dte_trading: int
    watchlist_hit: bool
    watchlist_elevated: bool

    # Underlying context
    nifty_spot: decimal.Decimal
    nifty_futures_price: decimal.Decimal | None
    futures_basis: decimal.Decimal | None
    underlying_return_1m: decimal.Decimal | None
    underlying_return_5m: decimal.Decimal | None
    underlying_return_15m: decimal.Decimal | None
    underlying_rvol_15m: decimal.Decimal | None
    distance_pct: decimal.Decimal
    distance_sigma: decimal.Decimal | None

    # Option quote
    best_bid: decimal.Decimal | None
    best_ask: decimal.Decimal
    bid_ask_spread: decimal.Decimal | None
    spread_pct_of_mid: decimal.Decimal | None

    # L2 depth (Dhan; None if not subscribed or NullDepth)
    bid_qty_l1: int | None
    ask_qty_l1: int | None
    total_bid_qty: int | None
    total_ask_qty: int | None

    # Greeks
    delta_val: decimal.Decimal | None
    gamma_val: decimal.Decimal
    vega_val: decimal.Decimal | None
    theta_val: decimal.Decimal | None
    iv_val: decimal.Decimal | None

    # Derived
    gamma_gearing: decimal.Decimal
    speed_5m: decimal.Decimal | None
    speed_5m_unavailable: bool
    theoretical_price: decimal.Decimal | None
    model_edge: decimal.Decimal | None
    strike_iv_pctile_20d: decimal.Decimal | None
    gearing_threshold_used: decimal.Decimal | None

    # Volume / OI
    volume_5m: int | None
    volume_zscore_5m: decimal.Decimal | None
    oi_now: int | None
    oi_velocity_15m: decimal.Decimal | None
    option_price_rising: bool | None

    # Market regime
    india_vix: decimal.Decimal | None
    india_vix_pctile_252d: decimal.Decimal | None
    event_flag: bool
    event_type: str | None

    # Filter results (True=pass, False=fail, None=not evaluated)
    f0_hard_pass: bool | None
    f0_fail_reason: str | None
    f1_directional_pass: bool | None
    f2_convexity_pass: bool | None
    f3_quality_pass: bool | None
    f3_quality_method: str | None
    f4_flow_pass: bool | None
    signal_triggered: bool

    # Paper trade
    paper_trade_attempted: bool
    paper_trade_filled: bool
    entry_fill_price: decimal.Decimal | None
    fill_timestamp: datetime.datetime | None
    unfilled_reason: str | None

    # Exit
    exit_price: decimal.Decimal | None
    exit_timestamp: datetime.datetime | None
    exit_reason: str | None
    mfe: decimal.Decimal | None
    mae: decimal.Decimal | None
    realised_r_multiple: decimal.Decimal | None

    created_at: datetime.datetime

from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel


class Direction(str, Enum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"


class TradeAction(str, Enum):
    BUY_CALL = "BUY_CALL"
    BUY_PUT = "BUY_PUT"
    NO_TRADE = "NO_TRADE"


# ── Input ────────────────────────────────────────────────────────────────────


class OILevel(BaseModel, frozen=True):
    """One strike's OI data row from the option chain."""

    strike: int
    oi: int
    oi_change: int  # vs previous day; negative = OI unwinding


class OptionChainSummary(BaseModel, frozen=True):
    """Derived option-chain fields injected into every model prompt."""

    atm_strike: int
    atm_iv: Decimal
    iv_skew: Decimal  # OTM call IV − OTM put IV; positive = calls rich
    pcr_total: Decimal
    pcr_atm: Decimal
    top_call_oi: list[OILevel]  # top 3 strikes by call OI
    top_put_oi: list[OILevel]  # top 3 strikes by put OI


class FIIData(BaseModel, frozen=True):
    """FII/DII cash-market net flows, previous session (NSE fiidiiTradeReact)."""

    fii_cash_net_cr: Decimal  # positive = FII net buyer in cash market (₹ cr)
    dii_cash_net_cr: Decimal  # positive = DII net buyer in cash market (₹ cr)


class MarketSnapshot(BaseModel, frozen=True):
    """
    Complete market context assembled at 09:10 AM.

    Injected verbatim into every model prompt.  Fields sourced from:
    - nifty_spot / prev_* : Upstox LTP + OHLC
    - gift_nifty          : NSE website pre-market page
    - india_vix           : Upstox or NSE
    - vix_5d_trend        : computed from last 5 VIX snapshots
    - usd_inr             : NSE or public API
    - monthly_expiry      : computed (last Thursday of current month)
    - option_chain        : parsed Upstox option chain
    - fii                 : NSE fiidiiTradeReact cash-market net (T-1)
    """

    trade_date: date
    nifty_spot: Decimal
    prev_close: Decimal
    prev_high: Decimal
    prev_low: Decimal
    gift_nifty: Decimal
    india_vix: Decimal
    vix_5d_trend: str  # "rising" | "falling" | "flat"
    usd_inr: Decimal
    monthly_expiry: date
    option_chain: OptionChainSummary
    fii: FIIData


# ── Output ───────────────────────────────────────────────────────────────────


class SignalUsage(BaseModel, frozen=True):
    """OpenRouter token usage and USD cost for one model call.

    Fields map to the OpenRouter response ``usage`` block: ``prompt_tokens``,
    ``completion_tokens``, and ``cost`` (billed USD credits). ``None`` on the
    ``mock`` provider and Gemini's Google-SDK path — neither returns a usage
    object.
    """

    prompt_tokens: int
    completion_tokens: int
    cost_usd: Decimal


class SignalResponse(BaseModel, frozen=True):
    """
    Raw structured output from one model call.

    One row written to signal_responses table per (trade_date, provider) pair.
    The aggregator rejects rows where strike is outside ATM±1, direction is
    invalid, or confidence is outside 1–5 — rejected rows are logged as WARNING
    and excluded from the vote (not treated as NEUTRAL).
    """

    trade_date: date
    provider: str  # "grok" | "gpt4o" | "gemini"
    direction: Direction
    confidence: int  # 1–5 inclusive
    recommended_strike: int
    entry_premium_low: Decimal
    entry_premium_high: Decimal
    key_reason: str  # ≤ 1 sentence
    key_risk: str  # ≤ 1 sentence
    raw_response: str  # full JSON string returned by model
    usage: SignalUsage | None = None


class DailySignal(BaseModel, frozen=True):
    """
    Aggregated consensus for one trading day.

    One row written to daily_signals table.  trade_action is NO_TRADE when:
    - fewer than 2 valid responses
    - all 3 directions differ (3-way split)
    - majority direction is NEUTRAL
    - consensus_confidence < MIN_CONFIDENCE_THRESHOLD (default 3)
    """

    trade_date: date
    responses: list[SignalResponse]
    consensus_direction: Direction
    consensus_confidence: Decimal  # avg confidence of agreeing models only
    trade_action: TradeAction
    recommended_strike: int | None  # None when NO_TRADE
    entry_premium: Decimal | None = None
    agreeing_models: list[str]
    dissenting_models: list[str]


class SignalOutcome(BaseModel, frozen=True):
    """
    Recorded at 15:00 IST.  One row per trading day in signal_outcomes table.

    executed=False means the signal was logged but you chose not to paper-trade.
    Skipped trades are still included in per-provider direction accuracy stats
    (the model call happened regardless) but excluded from P&L aggregates.
    """

    trade_date: date
    trade_action: TradeAction
    recommended_strike: int | None
    entry_premium: Decimal | None
    exit_premium: Decimal | None
    pnl_per_lot: Decimal | None
    nifty_close: Decimal
    executed: bool
    phase: str = "openrouter_only"  # "openrouter_only" | "search_enabled"
    notes: str = ""

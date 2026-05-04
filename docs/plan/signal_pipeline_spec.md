# Daily LLM Signal Pipeline — Spec

> **Status:** POC design — pending API token acquisition  
> **Purpose:** Multi-model LLM consensus for intraday Nifty directional signal, paper-traded to validate edge  
> **Research question:** Does multi-LLM consensus with live market data input beat a random baseline on intraday Nifty direction?

---

## 1. Architecture Overview

```
09:10 AM  fetch_market_snapshot()
             │
             ▼
         MarketSnapshot (Pydantic)
             │
     ┌───────┼───────────────────┐
     ▼       ▼                   ▼
  Grok    GPT-4o            Gemini Pro
 (xAI)  (OpenRouter)     (Google AI SDK)
 search   structured        search
 enabled  analysis        grounding
     │       │                   │
     └───────┼───────────────────┘
             ▼
      SignalAggregator
      (majority vote + confidence gate)
             │
             ▼
         DailySignal → SQLite (signal_inputs, signal_responses)
             │
             ▼
    Human reviews consensus at 09:30 AM
    → decides paper trade entry manually
             │
             ▼
    03:00 PM  record_signal_outcome.py
    → logs entry/exit/pnl to signal_outcomes table
```

---

## 2. Live Data Inputs

### 2a. Injected directly into prompt (structured, no model search needed)

| Field | Source | Notes |
|---|---|---|
| `nifty_spot` | Upstox LTP | Current index level |
| `prev_day_ohlc` | Upstox OHLC | Previous session close/high/low |
| `gift_nifty` | NSE website fetch | Pre-market direction indicator |
| `india_vix` | Upstox or NSE | Current VIX level |
| `vix_5d_trend` | Computed from snapshots | rising / falling / flat |
| `atm_strike` | Option chain | Nearest to spot |
| `atm_iv` | Option chain | ATM call+put avg IV |
| `iv_skew` | Option chain | 1-strike OTM call IV minus put IV |
| `pcr_total` | Option chain | Total OI PCR |
| `pcr_atm` | Option chain | ATM-only OI PCR |
| `top_call_oi` | Option chain | Top 3 strikes by call OI + OI change |
| `top_put_oi` | Option chain | Top 3 strikes by put OI + OI change |
| `fii_net_futures` | NSE FII/DII CSV | FII net long/short in index futures (₹ cr) |
| `fii_net_options` | NSE FII/DII CSV | FII net index options position (₹ cr) |
| `usd_inr` | NSE/public API | Direction proxy for FII flow intent |
| `monthly_expiry` | Computed | Current month's last Thursday |

### 2b. Fetched by model (search-enabled providers only)

| Provider | What it fetches |
|---|---|
| Grok (xAI search) | Real-time X/Twitter trader sentiment, breaking news last 2 hours |
| Gemini (Google Search) | Global market closes (S&P, Nasdaq, Nikkei, crude oil), macro headlines |
| GPT-4o | No search — pure structured analysis of injected data only |

---

## 3. Data Models (`src/signals/models.py`)

```python
from __future__ import annotations
from datetime import date
from decimal import Decimal
from enum import Enum
from pydantic import BaseModel, Field

class Direction(str, Enum):
    BULLISH  = "BULLISH"
    BEARISH  = "BEARISH"
    NEUTRAL  = "NEUTRAL"

class TradeAction(str, Enum):
    BUY_CALL = "BUY_CALL"
    BUY_PUT  = "BUY_PUT"
    NO_TRADE = "NO_TRADE"

# ── Input ───────────────────────────────────────────────────────────────────

class OILevel(BaseModel, frozen=True):
    strike: int
    oi: int
    oi_change: int          # vs previous day

class OptionChainSummary(BaseModel, frozen=True):
    atm_strike: int
    atm_iv: Decimal
    iv_skew: Decimal        # OTM call IV - OTM put IV; positive = call-heavy
    pcr_total: Decimal
    pcr_atm: Decimal
    top_call_oi: list[OILevel]   # top 3
    top_put_oi:  list[OILevel]   # top 3

class FIIData(BaseModel, frozen=True):
    net_futures_cr: Decimal     # positive = net long
    net_options_cr: Decimal

class MarketSnapshot(BaseModel, frozen=True):
    trade_date: date
    nifty_spot: Decimal
    prev_close: Decimal
    prev_high: Decimal
    prev_low: Decimal
    gift_nifty: Decimal
    india_vix: Decimal
    vix_5d_trend: str           # "rising" | "falling" | "flat"
    usd_inr: Decimal
    monthly_expiry: date
    option_chain: OptionChainSummary
    fii: FIIData

# ── Output ──────────────────────────────────────────────────────────────────

class SignalResponse(BaseModel, frozen=True):
    """Raw output from one model. One row in signal_responses table."""
    trade_date: date
    provider: str               # "grok" | "gpt4o" | "gemini"
    direction: Direction
    confidence: int             # 1–5
    recommended_strike: int
    entry_premium_low: Decimal
    entry_premium_high: Decimal
    key_reason: str             # ≤ 1 sentence
    key_risk: str               # ≤ 1 sentence
    raw_response: str           # full JSON string from model

class DailySignal(BaseModel, frozen=True):
    """Aggregated consensus. One row in daily_signals table."""
    trade_date: date
    responses: list[SignalResponse]
    consensus_direction: Direction
    consensus_confidence: Decimal   # avg confidence of agreeing models
    trade_action: TradeAction
    recommended_strike: int | None  # None when NO_TRADE
    agreeing_models: list[str]
    dissenting_models: list[str]

class SignalOutcome(BaseModel, frozen=True):
    """Recorded at 3 PM. One row in signal_outcomes table."""
    trade_date: date
    trade_action: TradeAction
    recommended_strike: int | None
    entry_premium: Decimal | None
    exit_premium: Decimal | None
    pnl_per_lot: Decimal | None
    nifty_close: Decimal
    executed: bool              # did we actually paper-trade this?
    notes: str
```

---

## 4. Provider Protocol (`src/signals/protocol.py`)

```python
from typing import Protocol, runtime_checkable
from .models import MarketSnapshot, SignalResponse

@runtime_checkable
class SignalProvider(Protocol):
    provider_name: str

    async def get_signal(self, snapshot: MarketSnapshot) -> SignalResponse:
        """Call LLM with snapshot, parse structured response."""
        ...
```

---

## 5. Prompt Template (`src/signals/prompt.py`)

One shared base prompt injected into all three providers. Each provider appends
its own instruction suffix (Grok: "search X for sentiment", Gemini: "search web
for global markets", GPT-4o: "analyse the structured data only").

```
SYSTEM:
You are a quantitative analyst for Indian derivatives markets.
Respond ONLY in valid JSON. No markdown, no explanation outside JSON.

USER:
Today is {trade_date}. Monthly expiry: {monthly_expiry}.

## Market Snapshot
- Nifty spot: {nifty_spot}  |  Prev close: {prev_close}
- Gift Nifty: {gift_nifty}  |  Change implied: {gift_nifty_chg:+.1f}%
- India VIX: {india_vix} ({vix_5d_trend} over 5 days)
- USD/INR: {usd_inr}

## Option Chain (as of 09:10 AM)
- ATM strike: {atm_strike}  |  ATM IV: {atm_iv:.1f}%
- IV skew (OTM call – OTM put): {iv_skew:+.2f}%  (positive = calls rich)
- PCR total: {pcr_total:.2f}  |  PCR ATM: {pcr_atm:.2f}
- Top CALL OI: {top_call_oi}
- Top PUT  OI: {top_put_oi}

## FII Positioning (yesterday)
- Index futures net: ₹{fii_net_futures:,.0f} cr  (positive = long)
- Index options net: ₹{fii_net_options:,.0f} cr

{provider_specific_suffix}

## Required JSON output
{{
  "direction": "BULLISH" | "BEARISH" | "NEUTRAL",
  "confidence": 1–5,
  "recommended_strike": <integer>,
  "entry_premium_low": <number>,
  "entry_premium_high": <number>,
  "key_reason": "<one sentence>",
  "key_risk": "<one sentence>"
}}
```

### Provider-specific suffixes

**Grok:**
```
Search X/Twitter right now for: "Nifty", "Bank Nifty", "NSE" from the last 2 hours.
Weigh retail and institutional sentiment. Factor it into your direction call.
```

**Gemini:**
```
Search for: overnight S&P 500, Nasdaq, Nikkei, and crude oil levels.
Factor global market direction into your call.
```

**GPT-4o:**
```
Analyse the structured data above only. Do not search the web.
Pay particular attention to FII positioning and OI concentration as
resistance/support proxies.
```

---

## 6. Aggregation Logic (`src/signals/aggregator.py`)

```
1. Parallel await of all three providers (asyncio.gather, timeout=30s)
2. Count votes per direction
3. If 2 or 3 models agree on BULLISH or BEARISH:
     consensus_direction = majority direction
     consensus_confidence = avg confidence of agreeing models
     trade_action = BUY_CALL (BULLISH) | BUY_PUT (BEARISH)
         only if consensus_confidence >= MIN_CONFIDENCE_THRESHOLD (default 3)
         else NO_TRADE
4. If split (all 3 differ, or 2/3 NEUTRAL):
     trade_action = NO_TRADE
5. recommended_strike = modal strike among agreeing models (or lower strike if tie)
```

---

## 7. SQLite Schema (added to `data/portfolio/portfolio.sqlite`)

```sql
CREATE TABLE IF NOT EXISTS signal_inputs (
    trade_date   TEXT PRIMARY KEY,   -- YYYY-MM-DD
    snapshot_json TEXT NOT NULL      -- full MarketSnapshot as JSON
);

CREATE TABLE IF NOT EXISTS signal_responses (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_date   TEXT NOT NULL,
    provider     TEXT NOT NULL,      -- "grok" | "gpt4o" | "gemini"
    direction    TEXT NOT NULL,
    confidence   INTEGER NOT NULL,
    strike       INTEGER NOT NULL,
    premium_low  TEXT NOT NULL,      -- Decimal as TEXT
    premium_high TEXT NOT NULL,
    key_reason   TEXT NOT NULL,
    key_risk     TEXT NOT NULL,
    raw_response TEXT NOT NULL,
    created_at   TEXT NOT NULL,      -- UTC ISO
    UNIQUE (trade_date, provider)
);

CREATE TABLE IF NOT EXISTS daily_signals (
    trade_date            TEXT PRIMARY KEY,
    consensus_direction   TEXT NOT NULL,
    consensus_confidence  TEXT NOT NULL,  -- Decimal as TEXT
    trade_action          TEXT NOT NULL,
    recommended_strike    INTEGER,
    agreeing_models       TEXT NOT NULL,  -- JSON array
    dissenting_models     TEXT NOT NULL,
    created_at            TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS signal_outcomes (
    trade_date         TEXT PRIMARY KEY,
    trade_action       TEXT NOT NULL,
    recommended_strike INTEGER,
    entry_premium      TEXT,
    exit_premium       TEXT,
    pnl_per_lot        TEXT,
    nifty_close        TEXT NOT NULL,
    executed           INTEGER NOT NULL DEFAULT 0,  -- boolean
    notes              TEXT,
    recorded_at        TEXT NOT NULL
);
```

---

## 8. File Structure

```
src/signals/
├── __init__.py
├── CLAUDE.md               # module invariants
├── models.py               # MarketSnapshot, SignalResponse, DailySignal, SignalOutcome
├── protocol.py             # SignalProvider protocol
├── prompt.py               # build_prompt(snapshot, provider) → str
├── aggregator.py           # parallel calls + consensus logic
├── store.py                # SignalStore — SQLite read/write
├── factory.py              # composition root — builds providers from env
└── providers/
    ├── __init__.py
    ├── grok.py             # GrokSignalProvider (xAI SDK, search=True)
    ├── gpt4o.py            # GPT4oSignalProvider (OpenRouter)
    ├── gemini.py           # GeminiSignalProvider (google-generativeai SDK)
    └── mock.py             # MockSignalProvider — deterministic, for tests

scripts/
├── morning_signal.py       # 09:15 AM cron — fetch data, run pipeline, log
└── record_signal_outcome.py  # 03:00 PM — manual or cron, log outcome
```

---

## 9. Daily Cron Schedule

```
# Morning signal (fetch + LLM calls + log)
15 9 * * 1-5  cd /path/to/NiftyShield && python scripts/morning_signal.py

# Outcome recording (end of session — can also be run manually)
0 15 * * 1-5  cd /path/to/NiftyShield && python scripts/record_signal_outcome.py --auto
```

`morning_signal.py` emits a one-line Telegram notification via the existing
`build_notifier()` with: direction, confidence, recommended strike, and which models agreed.

---

## 10. Environment Variables

```
# Add to .env and .env.example
XAI_API_KEY=                    # Grok — https://console.x.ai
OPENROUTER_API_KEY=             # GPT-4o — https://openrouter.ai
GOOGLE_AI_API_KEY=              # Gemini — https://aistudio.google.com

SIGNAL_MIN_CONFIDENCE=3         # default threshold for trade action
SIGNAL_PROVIDERS=grok,gpt4o,gemini   # comma-separated, easy to disable one
```

---

## 11. Config (`config/signals.toml`)

```toml
[signals]
min_confidence_threshold = 3    # avg confidence of agreeing models to trigger action
consensus_required = 2          # minimum models that must agree (out of 3)
call_timeout_seconds = 30       # per-provider timeout

[signals.providers.grok]
model   = "grok-3"
search  = true
max_tokens = 512

[signals.providers.gpt4o]
model   = "openai/gpt-4o"
base_url = "https://openrouter.ai/api/v1"
max_tokens = 512

[signals.providers.gemini]
model   = "gemini-2.0-flash"
search_grounding = true
max_tokens = 512
```

---

## 12. Phase 1 POC — OpenRouter Only (no search)

Before acquiring all three API keys, start with all providers via OpenRouter
to validate the pipeline end-to-end:

| Provider | Phase 1 (OpenRouter) | Phase 2 (full) |
|---|---|---|
| Grok | `x-ai/grok-3` via OpenRouter | xAI direct API, search enabled |
| GPT-4o | `openai/gpt-4o` via OpenRouter | same |
| Gemini | `google/gemini-2.0-flash` via OpenRouter | Google AI SDK, search grounding |

Phase 1 validates: prompt parsing, JSON output, aggregation logic, SQLite logging,
Telegram notification, cron cadence. Only one API key needed.

Phase 2 upgrade: swap Grok and Gemini to direct SDKs. Compare P&L outcomes
Phase 1 vs Phase 2 to quantify how much search capability contributes.

---

## 13. Evaluation (after 50 trades — ~2.5 months)

| Metric | Formula |
|---|---|
| Win rate | trades where pnl_per_lot > 0 / total executed trades |
| Expected value | avg(pnl_per_lot) across all executed trades |
| vs random baseline | flip a coin each day; same entry/exit rule; compare EV |
| Model accuracy | per-provider: direction_called == nifty_close > nifty_open |
| Confidence calibration | when confidence ≥ 4, what is actual win rate? |
| NO_TRADE accuracy | on days where NO_TRADE, did the market move adversely? |

The random baseline is critical. Without it you cannot distinguish signal from
luck in a trending market.

---

## 14. Required API Tokens (checklist)

- [ ] `XAI_API_KEY` — https://console.x.ai (Grok, Phase 2)
- [ ] `OPENROUTER_API_KEY` — https://openrouter.ai (Phase 1 start here)
- [ ] `GOOGLE_AI_API_KEY` — https://aistudio.google.com (Gemini, Phase 2)

Phase 1 can start with OpenRouter key alone.

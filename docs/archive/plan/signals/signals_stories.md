# Signals — Story Specs

> One task per session. Find the first unchecked item in `signals_tasks.md`. That is your only task.
> Full implementation rules in `CLAUDE.md` and `REVIEW.md`.
> After each task: tick `signals_tasks.md`, append `| SHA: <sha>`, add one line to `TODOS.md`.

---

## S1.1 — `src/signals/models.py`: data models + tests

**Files to change:**
- `src/signals/__init__.py` — new package, single comment line only
- `src/signals/models.py` — all enums and Pydantic models
- `tests/unit/signals/__init__.py` — new test package, single comment line only
- `tests/unit/signals/test_signals_models.py` — model tests

**Before any code:**
`search_graph("PaperTrade")` — confirm frozen Pydantic pattern used in this codebase;
`search_graph("Direction")` — confirm no existing `Direction` enum collision;
`search_graph("SignalResponse")` — confirm does NOT yet exist (zero results expected).

**Package structure (create all `__init__.py` stubs now):**

```
src/signals/
├── __init__.py
├── models.py
├── protocol.py         (S1.2)
├── prompt.py           (S1.2)
├── aggregator.py       (S1.3)
├── store.py            (S2.1 + S2.2)
├── factory.py          (S4.1)
└── providers/
    ├── __init__.py
    ├── mock.py         (S3.1)
    ├── gpt4o.py        (S3.2)
    ├── grok.py         (S3.3)
    └── gemini.py       (S3.4)
```

Create `src/signals/providers/__init__.py` (stub) in this task too — avoids a missing-package
failure when S3.x tasks run `__init__.py` checks.

**What to implement (`src/signals/models.py`):**

```python
from __future__ import annotations
from datetime import date
from decimal import Decimal
from enum import Enum
from pydantic import BaseModel, Field


class Direction(str, Enum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"


class TradeAction(str, Enum):
    BUY_CALL = "BUY_CALL"
    BUY_PUT  = "BUY_PUT"
    NO_TRADE = "NO_TRADE"


# ── Input ────────────────────────────────────────────────────────────────────

class OILevel(BaseModel, frozen=True):
    """One strike's OI data row from the option chain."""
    strike: int
    oi: int
    oi_change: int   # vs previous day; negative = OI unwinding


class OptionChainSummary(BaseModel, frozen=True):
    """Derived option-chain fields injected into every model prompt."""
    atm_strike: int
    atm_iv: Decimal
    iv_skew: Decimal        # OTM call IV − OTM put IV; positive = calls rich
    pcr_total: Decimal
    pcr_atm: Decimal
    top_call_oi: list[OILevel]   # top 3 strikes by call OI
    top_put_oi:  list[OILevel]   # top 3 strikes by put OI


class FIIData(BaseModel, frozen=True):
    """FII index positioning as of previous session (NSE FII/DII CSV)."""
    net_futures_cr: Decimal   # positive = net long index futures (₹ cr)
    net_options_cr: Decimal   # positive = net long index options (₹ cr)


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
    - fii                 : NSE FII/DII CSV (T-1)
    """
    trade_date:      date
    nifty_spot:      Decimal
    prev_close:      Decimal
    prev_high:       Decimal
    prev_low:        Decimal
    gift_nifty:      Decimal
    india_vix:       Decimal
    vix_5d_trend:    str       # "rising" | "falling" | "flat"
    usd_inr:         Decimal
    monthly_expiry:  date
    option_chain:    OptionChainSummary
    fii:             FIIData


# ── Output ───────────────────────────────────────────────────────────────────

class SignalResponse(BaseModel, frozen=True):
    """
    Raw structured output from one model call.

    One row written to signal_responses table per (trade_date, provider) pair.
    The aggregator rejects rows where strike is outside ATM±1, direction is
    invalid, or confidence is outside 1–5 — rejected rows are logged as WARNING
    and excluded from the vote (not treated as NEUTRAL).
    """
    trade_date:          date
    provider:            str       # "grok" | "gpt4o" | "gemini"
    direction:           Direction
    confidence:          int       # 1–5 inclusive
    recommended_strike:  int
    entry_premium_low:   Decimal
    entry_premium_high:  Decimal
    key_reason:          str       # ≤ 1 sentence
    key_risk:            str       # ≤ 1 sentence
    raw_response:        str       # full JSON string returned by model


class DailySignal(BaseModel, frozen=True):
    """
    Aggregated consensus for one trading day.

    One row written to daily_signals table.  trade_action is NO_TRADE when:
    - fewer than 2 valid responses
    - all 3 directions differ (3-way split)
    - majority direction is NEUTRAL
    - consensus_confidence < MIN_CONFIDENCE_THRESHOLD (default 3)
    """
    trade_date:            date
    responses:             list[SignalResponse]
    consensus_direction:   Direction
    consensus_confidence:  Decimal    # avg confidence of agreeing models only
    trade_action:          TradeAction
    recommended_strike:    int | None  # None when NO_TRADE
    agreeing_models:       list[str]
    dissenting_models:     list[str]


class SignalOutcome(BaseModel, frozen=True):
    """
    Recorded at 15:00 IST.  One row per trading day in signal_outcomes table.

    executed=False means the signal was logged but you chose not to paper-trade.
    Skipped trades are still included in per-provider direction accuracy stats
    (the model call happened regardless) but excluded from P&L aggregates.
    """
    trade_date:         date
    trade_action:       TradeAction
    recommended_strike: int | None
    entry_premium:      Decimal | None
    exit_premium:       Decimal | None
    pnl_per_lot:        Decimal | None
    nifty_close:        Decimal
    executed:           bool
    phase:              str = "openrouter_only"   # "openrouter_only" | "search_enabled"
    notes:              str = ""
```

**Tests (`tests/unit/signals/test_signals_models.py`):**
- `Direction` enum members match `"BULLISH"`, `"BEARISH"`, `"NEUTRAL"` strings.
- `TradeAction` enum members match `"BUY_CALL"`, `"BUY_PUT"`, `"NO_TRADE"`.
- `MarketSnapshot` round-trips through `model_dump()` / `model_validate()` with all
  `Decimal` fields preserved as `Decimal` (not float).
- `SignalResponse` with valid fields constructs without error.
- `DailySignal` with `recommended_strike=None` and `trade_action=NO_TRADE` → valid.
- `SignalOutcome` with `entry_premium=None` and `executed=False` → valid (skipped day).
- `OILevel` with negative `oi_change` → valid (OI unwinding).

**Commit:** `feat(signals): add signals data models — MarketSnapshot, SignalResponse, DailySignal, SignalOutcome`

---

## S1.1a — redefine `FIIData` as cash-market net flows

**Why this exists:** The S5.2a source-discovery spike (2026-09-07) confirmed FII **index F&O
positioning** data (`net_futures_cr` / `net_options_cr`) is unreachable in this environment —
the participant-wise OI CSVs 404 for every recent date. Only FII/DII **cash-market** net flows
are fetchable, via NSE `fiidiiTradeReact` JSON. Animesh's call: split the model change out of
S5.2a as its own tiny task so `market_inputs.py` is built against a settled model.

**Files to change:**
- `src/signals/models.py` — `FIIData` fields + docstring; `MarketSnapshot` docstring `fii` source line
- `src/signals/prompt.py` — §"FII Positioning (yesterday)" → "FII/DII Cash Flows (yesterday)";
  gpt4o suffix "FII positioning" → "FII/DII flows"
- `tests/unit/signals/test_signals_*.py` (8 files) — `FIIData(...)` constructor kwargs + the
  `Decimal` round-trip assertion in `test_signals_models.py`

**New shape:**
```python
class FIIData(BaseModel, frozen=True):
    """FII/DII cash-market net flows, previous session (NSE fiidiiTradeReact)."""
    fii_cash_net_cr: Decimal   # positive = FII net buyer in cash market (₹ cr)
    dii_cash_net_cr: Decimal   # positive = DII net buyer in cash market (₹ cr)
```

**Prompt section:**
```
## FII/DII Cash Flows (yesterday)
- FII cash net: ₹{fii_cash_net_cr:,.0f} cr  (positive = net buyer)
- DII cash net: ₹{dii_cash_net_cr:,.0f} cr  (positive = net buyer)
```

**Tests:** the existing 8 signals test files already construct `FIIData` and (in
`test_signals_models.py`) assert `Decimal` survives a `model_dump` / `model_validate`
round-trip — update the kwarg names in place; no new test files.

**Commit:** `refactor(signals): redefine FIIData as cash-market net flows`

---

## S1.2 — `src/signals/protocol.py` + `src/signals/prompt.py`: provider protocol + prompt builder + tests

**Files to change:**
- `src/signals/protocol.py` — `SignalProvider` runtime-checkable Protocol
- `src/signals/prompt.py` — `build_prompt(snapshot, provider_name)` pure function
- `tests/unit/signals/test_signals_prompt.py` — new test file

**Before any code:**
`get_code_snippet("SignalProvider")` — confirm does NOT yet exist;
`get_code_snippet("MarketSnapshot")` — exact field list from S1.1;
`search_code("runtime_checkable")` in `src/` — check existing Protocol usage pattern.

**What to implement (`src/signals/protocol.py`):**

```python
from typing import Protocol, runtime_checkable
from .models import MarketSnapshot, SignalResponse

@runtime_checkable
class SignalProvider(Protocol):
    """
    Contract for all signal providers (Grok, GPT-4o, Gemini, Mock).

    Constructor injection only — factory.py is the sole composition root.
    Implementations must be safe to call concurrently via asyncio.gather.
    """
    provider_name: str

    async def get_signal(self, snapshot: MarketSnapshot) -> SignalResponse:
        """Call the LLM with snapshot context, parse structured response."""
        ...
```

**What to implement (`src/signals/prompt.py`):**

`build_prompt(snapshot: MarketSnapshot, provider_name: str) -> str` — returns the
complete prompt string for the given provider.  Pure function; no I/O.

The prompt is a shared base injected with `snapshot` fields, with a
provider-specific suffix appended.  Implement exactly as below:

```
SYSTEM (first element, role="system"):
You are a quantitative analyst for Indian derivatives markets.
Respond ONLY in valid JSON. No markdown, no explanation outside JSON.

USER (second element, role="user"):
Today is {trade_date}. Monthly expiry: {monthly_expiry}.

## Market Snapshot
- Nifty spot: {nifty_spot}  |  Prev close: {prev_close}
- Prev session: H {prev_high} / L {prev_low}
- Gift Nifty: {gift_nifty}  |  Change implied: {gift_nifty_chg:+.2f}%
- India VIX: {india_vix} ({vix_5d_trend} over 5 days)
- USD/INR: {usd_inr}

## Option Chain (as of 09:10 AM)
- ATM strike: {atm_strike}  |  ATM IV: {atm_iv:.1f}%
- IV skew (OTM call – OTM put): {iv_skew:+.2f}%  (positive = calls rich)
- PCR total: {pcr_total:.2f}  |  PCR ATM: {pcr_atm:.2f}
- Top CALL OI: {top_call_oi_text}
- Top PUT  OI: {top_put_oi_text}

## FII Positioning (yesterday)
- Index futures net: ₹{fii_net_futures:,.0f} cr  (positive = long)
- Index options net: ₹{fii_net_options:,.0f} cr

{provider_suffix}

## Required JSON output
{
  "direction": "BULLISH" | "BEARISH" | "NEUTRAL",
  "confidence": 1–5,
  "recommended_strike": <integer — ATM or one strike above/below ATM only>,
  "entry_premium_low": <number>,
  "entry_premium_high": <number>,
  "key_reason": "<one sentence>",
  "key_risk": "<one sentence>"
}

ATM strike is {atm_strike}. Permitted strikes: {atm_minus_1}, {atm_strike}, {atm_plus_1}.
Any other strike will be rejected and your response discarded.
If uncertain, use {atm_strike}.
```

Provider suffixes (appended to USER turn):

```python
SUFFIXES = {
    "grok": (
        "Search X/Twitter right now for: \"Nifty\", \"Bank Nifty\", \"NSE\" "
        "posted in the last 2 hours. "
        "Weigh retail and institutional sentiment. Factor it into your direction call."
    ),
    "gemini": (
        "Search for: overnight S&P 500, Nasdaq, Nikkei 225, and crude oil levels. "
        "Factor global market direction into your call."
    ),
    "gpt4o": (
        "Analyse the structured data above only. Do not search the web. "
        "Pay particular attention to FII positioning and OI concentration as "
        "resistance/support proxies."
    ),
}
```

`top_call_oi_text` and `top_put_oi_text`: format each `OILevel` as
`"{strike} OI:{oi:,} Δ{oi_change:+,}"`, joined by `" | "`.

`gift_nifty_chg`: `(gift_nifty - prev_close) / prev_close * 100`.

`atm_minus_1` / `atm_plus_1`: `atm_strike - 50` / `atm_strike + 50`
(Nifty strikes are 50-point spaced; encode this as a module constant `NIFTY_STRIKE_STEP = 50`).

**Tests (`tests/unit/signals/test_signals_prompt.py`):**
- `build_prompt(snapshot, "gpt4o")` contains `"Analyse the structured data"` (GPT-4o suffix).
- `build_prompt(snapshot, "grok")` contains `"Search X/Twitter"` (Grok suffix).
- `build_prompt(snapshot, "gemini")` contains `"Search for: overnight"` (Gemini suffix).
- Prompt contains ATM strike value from snapshot.
- `top_call_oi_text` in output — first OI entry formatted with `OI:` and `Δ` prefix.
- Unknown `provider_name` → `KeyError` raised (no silent fallback).
- `gift_nifty_chg` sign: when `gift_nifty > prev_close`, output contains `+`.

**Commit:** `feat(signals): add SignalProvider protocol and build_prompt pure function`

---

## S1.3 — `src/signals/aggregator.py`: consensus logic + tests

**Files to change:**
- `src/signals/aggregator.py` — `SignalAggregator` class
- `tests/unit/signals/test_signals_aggregator.py` — new test file

**Before any code:**
`get_code_snippet("DailySignal")` — exact field list from S1.1;
`get_code_snippet("SignalResponse")` — exact field list;
`get_code_snippet("TradeAction")` — enum members;
`get_code_snippet("Direction")` — enum members.

**What to implement:**

`SignalAggregator` — thin class, no I/O, takes `min_confidence: int = 3` and
`consensus_required: int = 2` as constructor args.

Single public method:
```python
def aggregate(
    self,
    snapshot: MarketSnapshot,
    responses: list[SignalResponse],
) -> DailySignal:
```

**Algorithm (implement exactly):**

1. Validate each response — reject (log `WARNING`, exclude from vote) if ANY of:
   - `recommended_strike` not in `{atm_minus_1, atm_strike, atm_plus_1}`
   - `confidence` outside `[1, 5]`
   A rejected response is a missing vote, NOT a NEUTRAL vote.

2. Count votes per direction across validated responses only.

3. If `≥ consensus_required` models agree on `BULLISH` or `BEARISH`:
   - `consensus_direction` = that direction
   - `consensus_confidence` = `Decimal(mean(confidence of agreeing models))`
   - `trade_action` = `BUY_CALL` if BULLISH, `BUY_PUT` if BEARISH
   - BUT override to `NO_TRADE` if `consensus_confidence < self.min_confidence`
   - `recommended_strike` = modal strike among agreeing models (ATM on tie)

4. Otherwise (split / all NEUTRAL / fewer than `consensus_required` valid responses):
   - `trade_action = NO_TRADE`
   - `consensus_direction = NEUTRAL`
   - `recommended_strike = None`

5. `agreeing_models` = providers whose direction == `consensus_direction`
   `dissenting_models` = all other providers (including rejected ones)

**Tests (`tests/unit/signals/test_signals_aggregator.py`):**

Build a `MarketSnapshot` fixture and two `SignalResponse` fixtures (use
`get_code_snippet("MarketSnapshot")` before writing any constructor). All tests use
`SignalAggregator()` with defaults.

- Two BULLISH responses → `BUY_CALL`, both in `agreeing_models`.
- Two BEARISH responses → `BUY_PUT`.
- All three different directions → `NO_TRADE`, `consensus_direction=NEUTRAL`.
- Two agreeing but `avg_confidence < 3` → `NO_TRADE` (confidence gate).
- Response with strike outside ATM±50 → excluded; if only 1 valid remains → `NO_TRADE`.
- Response with `confidence=0` → rejected; warning logged; not a NEUTRAL vote.
- `recommended_strike` = modal strike of agreeing models; ATM wins on tie.
- Single response (only one provider returned) → `NO_TRADE` (< 2 required).

**Commit:** `feat(signals): add SignalAggregator consensus logic with validation + confidence gate`

---

## S2.1 — `src/signals/store.py`: init_db + write methods + tests

**Files to change:**
- `src/signals/store.py` — `SignalStore` class, `init_db` + all write methods
- `tests/unit/signals/test_signals_store.py` — new test file

**Before any code:**
`get_code_snippet("db_connection")` — confirm shared SQLite context manager in `src/db.py`;
`get_code_snippet("SignalStore")` — confirm does NOT yet exist;
`get_code_snippet("MarketSnapshot")` — for snapshot JSON serialisation;
`get_code_snippet("SignalResponse")` — field list for insert column mapping;
`get_code_snippet("DailySignal")` — field list.

**DDL:** use exact schema from `docs/plan/signals/signals_schema.md`. Call
`init_db()` in tests before any write.

**What to implement:**

`SignalStore.__init__(self, db_path: str)` — stores path only, no open connection.

`init_db(self) → None` — creates all four tables + two indexes (safe to call repeatedly).

`record_snapshot(self, snapshot: MarketSnapshot) → None` — INSERT OR REPLACE into
`signal_inputs`. Serialise `snapshot` via `snapshot.model_dump_json()`.

`record_response(self, response: SignalResponse) → None` — INSERT OR IGNORE into
`signal_responses`. `Decimal` fields stored as `str(value)`.

`record_signal(self, signal: DailySignal) → None` — INSERT OR REPLACE into
`daily_signals`. `agreeing_models` / `dissenting_models` stored as `json.dumps(list)`.

`record_outcome(self, outcome: SignalOutcome) → None` — INSERT OR REPLACE into
`signal_outcomes`. `executed` stored as `int(outcome.executed)`.

**Tests (`tests/unit/signals/test_signals_store.py`):**
All tests use `tmp_path` fixture: `SignalStore(str(tmp_path / "test.sqlite"))` + `init_db()`.

- `init_db()` called twice → no error.
- `record_snapshot` → row present in `signal_inputs` with correct `trade_date`.
- `record_response` twice for same `(trade_date, provider)` → second call is no-op
  (INSERT OR IGNORE); row count stays 1.
- `record_signal` with `recommended_strike=None` → `None` stored as SQL NULL.
- `record_outcome` with `executed=False` → stored as `0`; `pnl_per_lot=None` → NULL.
- `record_outcome` called twice for same `trade_date` → OR REPLACE updates row.

**Commit:** `feat(signals): add SignalStore init_db and write methods`

---

## S2.2 — `src/signals/store.py`: read methods + tests

**Files to change:**
- `src/signals/store.py` — extend with all read methods
- `tests/unit/signals/test_signals_store.py` — extend with read tests

**Before any code:**
`get_code_snippet("SignalStore")` — current public API (post S2.1);
`get_code_snippet("SignalOutcome")` — field list, especially `phase` default.

**What to implement (add to `SignalStore`):**

`get_snapshot(self, trade_date: date) → MarketSnapshot | None` — deserialise from
`snapshot_json` via `MarketSnapshot.model_validate_json(row["snapshot_json"])`.

`get_responses(self, trade_date: date) → list[SignalResponse]` — all rows for date,
ordered by `provider`. Deserialise `Decimal` fields with `Decimal(row["field"])`.

`get_signal(self, trade_date: date) → DailySignal | None` — joins with
`signal_responses` to populate `DailySignal.responses`. Returns `None` if no row.

`get_outcome(self, trade_date: date) → SignalOutcome | None`.

`get_all_outcomes(
    self,
    from_date: date | None = None,
    to_date: date | None = None,
    phase: str | None = None,
) → list[SignalOutcome]` — used by `signal_report.py`. All filters optional.

**Tests (extend `test_signals_store.py`):**
- `record_snapshot` → `get_snapshot` round-trip: all `Decimal` fields survive.
- `record_response` → `get_responses` returns correct count and provider name.
- `get_signal` — `responses` list populated from `signal_responses` table.
- `get_signal` on missing date → `None`.
- `get_outcome` → `executed` deserialises back to `bool`.
- `get_all_outcomes` with `phase="openrouter_only"` filter → returns only matching rows.
- `get_all_outcomes` with `from_date` / `to_date` range → excludes out-of-range rows.

**Commit:** `feat(signals): add SignalStore read methods — get_snapshot, get_signal, get_outcome, get_all_outcomes`

---

## S3.1 — `src/signals/providers/mock.py`: MockSignalProvider + tests

**Files to change:**
- `src/signals/providers/mock.py` — `MockSignalProvider`
- `tests/unit/signals/test_signals_mock_provider.py` — new test file

**Before any code:**
`get_code_snippet("SignalProvider")` — confirm Protocol signature;
`get_code_snippet("SignalResponse")` — exact field list;
`get_code_snippet("Direction")` — enum members;
`search_graph("MockBrokerClient")` — see existing mock pattern in `src/client/`.

**What to implement:**

```python
class MockSignalProvider:
    """
    Deterministic provider for tests and offline runs.

    Returns a fixed SignalResponse based on the direction and confidence
    passed at construction time.  Does not call any network API.
    Used by all unit tests that need a concrete SignalProvider instance.
    """
    provider_name: str

    def __init__(
        self,
        provider_name: str = "mock",
        direction: Direction = Direction.BULLISH,
        confidence: int = 4,
        strike_offset: int = 0,   # offset from ATM; 0 = ATM, -50 = one below, +50 = one above
    ) -> None: ...

    async def get_signal(self, snapshot: MarketSnapshot) -> SignalResponse:
        """Return a deterministic SignalResponse; never raises."""
        ...
```

`recommended_strike = snapshot.option_chain.atm_strike + strike_offset`.

`key_reason` and `key_risk` are fixed strings: `"mock reason"` / `"mock risk"`.
`raw_response` is `'{"mock": true}'`.
`entry_premium_low` = `Decimal("50")`, `entry_premium_high` = `Decimal("60")`.

**Tests (`tests/unit/signals/test_signals_mock_provider.py`):**
- `isinstance(MockSignalProvider(), SignalProvider)` → `True`
  (runtime-checkable Protocol check).
- `get_signal(snapshot)` returns `SignalResponse` with `direction == Direction.BULLISH`
  (default construction).
- `confidence` from constructor surfaces on `SignalResponse.confidence`.
- `recommended_strike` equals `atm_strike + strike_offset`.
- `MockSignalProvider(direction=Direction.BEARISH)` → response direction is `BEARISH`.

**Commit:** `feat(signals): add MockSignalProvider — deterministic, Protocol-compliant`

---

## S3.2 — `src/signals/providers/gpt4o.py`: OpenRouter provider + tests

**Files to change:**
- `src/signals/providers/gpt4o.py` — `GPT4oSignalProvider`
- `tests/unit/signals/test_signals_gpt4o_provider.py` — new test file (mock HTTP, no network)

**Before any code:**
`get_code_snippet("SignalProvider")` — Protocol contract;
`get_code_snippet("build_prompt")` — signature from S1.2;
`get_code_snippet("SignalResponse")` — field list for JSON parsing;
`search_code("aiohttp")` in `src/` — confirm existing aiohttp usage pattern;
`search_code("OPENROUTER_API_KEY")` in `src/` or `.env.example` — confirm env var name.

**Phase 1 — OpenRouter only (all three models via OpenRouter):**

| Provider | OpenRouter model string | Phase 2 upgrade |
|---|---|---|
| GPT-4o | `openai/gpt-4o` | same (stays on OpenRouter) |
| Grok | `x-ai/grok-3` | xAI direct API (`S3.3`) |
| Gemini | `google/gemini-2.0-flash` | Google AI SDK (`S3.4`) |

This task implements only the `gpt4o` provider. Phase 1 POC can start with a single
`OPENROUTER_API_KEY`. The other Phase 1 shims (`x-ai/grok-3` via OpenRouter) are
covered in `S3.3` and `S3.4` alongside their Phase 2 implementations.

**What to implement:**

```python
class GPT4oSignalProvider:
    provider_name = "gpt4o"

    def __init__(self, api_key: str, model: str = "openai/gpt-4o",
                 base_url: str = "https://openrouter.ai/api/v1",
                 timeout: float = 30.0) -> None: ...

    async def get_signal(self, snapshot: MarketSnapshot) -> SignalResponse:
        """POST to OpenRouter chat completions, parse JSON response."""
        ...
```

`get_signal` flow:
1. `prompt_messages = build_prompt(snapshot, "gpt4o")` — returns two dicts
   (`{"role": "system", ...}` and `{"role": "user", ...}`).
   Update `build_prompt` return type to `list[dict]` if not already structured that way;
   story S1.2 specifies two-element list — confirm with `get_code_snippet("build_prompt")`.
2. POST to `{base_url}/chat/completions` with `model`, `messages`, `max_tokens=512`,
   `temperature=0`, `response_format={"type": "json_object"}`.
3. Parse `choices[0].message.content` as JSON.
4. Build and return `SignalResponse` (set `raw_response = raw JSON string`).
5. On HTTP error or JSON parse failure → raise `DataFetchError(provider="gpt4o", ...)`.

`DataFetchError` is in `src/client/exceptions.py` — use it; do not define a new exception.

**Tests (`tests/unit/signals/test_signals_gpt4o_provider.py`):**
Use `unittest.mock.AsyncMock` / `aioresponses` to mock the HTTP call. No network.

- Valid JSON response → `SignalResponse` returned with correct `direction` and `confidence`.
- HTTP 429 (rate limit) → `DataFetchError` raised.
- Response body is not valid JSON → `DataFetchError` raised.
- `provider_name` attribute == `"gpt4o"`.

**Commit:** `feat(signals): add GPT4oSignalProvider via OpenRouter (Phase 1)`

---

## S3.3 — `src/signals/providers/grok.py`: xAI provider + tests

**Files to change:**
- `src/signals/providers/grok.py` — `GrokSignalProvider`
- `tests/unit/signals/test_signals_grok_provider.py` — new test file

**Before any code:**
`get_code_snippet("GPT4oSignalProvider")` — reuse HTTP pattern from S3.2;
`get_code_snippet("build_prompt")` — confirm `"grok"` suffix exists;
`search_code("XAI_API_KEY")` in `.env.example` — confirm env var name.

**Phase 1 shim + Phase 2 direct API:**

This provider has two operating modes, selected by constructor arg `use_openrouter: bool`.

Phase 1 (OpenRouter shim, `use_openrouter=True`, default until xAI key acquired):
- `base_url = "https://openrouter.ai/api/v1"`
- `model = "x-ai/grok-3"`
- Same HTTP call pattern as `GPT4oSignalProvider`.
- No search capability — behaves like a non-search model.

Phase 2 (xAI direct, `use_openrouter=False`):
- `base_url = "https://api.x.ai/v1"`
- `model = "grok-3"`
- Add `"search": True` to request body when available in the xAI API schema.

`GrokSignalProvider.__init__` takes `api_key: str, use_openrouter: bool = True,
timeout: float = 30.0`. The `model` and `base_url` are derived from `use_openrouter`.

**Tests (`tests/unit/signals/test_signals_grok_provider.py`):**
- Phase 1 path (OpenRouter): valid response → `SignalResponse` returned.
- Phase 2 path (xAI): correct `base_url` used (`"https://api.x.ai/v1"`).
- `provider_name` == `"grok"`.
- JSON parse failure → `DataFetchError`.

**Commit:** `feat(signals): add GrokSignalProvider — Phase 1 OpenRouter shim + Phase 2 xAI direct`

---

## S3.4 — `src/signals/providers/gemini.py`: Google AI provider + tests

**Files to change:**
- `src/signals/providers/gemini.py` — `GeminiSignalProvider`
- `tests/unit/signals/test_signals_gemini_provider.py` — new test file

**Before any code:**
`get_code_snippet("GPT4oSignalProvider")` — reuse HTTP call pattern for Phase 1 shim;
`get_code_snippet("build_prompt")` — confirm `"gemini"` suffix exists;
`search_code("GOOGLE_AI_API_KEY")` in `.env.example` — confirm env var name.

**Phase 1 shim + Phase 2 Google AI SDK:**

Phase 1 (`use_openrouter=True`, default):
- Routes via OpenRouter: `model = "google/gemini-2.0-flash"`.
- No search grounding.

Phase 2 (`use_openrouter=False`):
- Uses `google-generativeai` SDK (`import google.generativeai as genai`).
- Enables Google Search grounding tool.
- `model = "gemini-2.0-flash"`.
- SDK call: `genai.GenerativeModel(model).generate_content(prompt, tools=[search_tool])`.

Phase 2 code path should be guarded: `try: import google.generativeai as genai` at the top
of the file. If import fails and `use_openrouter=False`, raise `ImportError` with clear
message (`"google-generativeai not installed; run: pip install google-generativeai"`).

**Tests (`tests/unit/signals/test_signals_gemini_provider.py`):**
- Phase 1 path: valid response → `SignalResponse`.
- `use_openrouter=False` without `google-generativeai` installed → `ImportError` on
  provider construction (mock the import).
- `provider_name` == `"gemini"`.
- JSON parse failure → `DataFetchError`.

**Commit:** `feat(signals): add GeminiSignalProvider — Phase 1 OpenRouter shim + Phase 2 Google AI SDK`

---

## S4.1 — `src/signals/factory.py`: composition root + tests

**Files to change:**
- `src/signals/factory.py` — `build_providers(env: dict | None = None) → list[SignalProvider]`
- `tests/unit/signals/test_signals_factory.py` — new test file

**Before any code:**
`get_code_snippet("build_notifier")` in `src/notifications/` — see existing factory pattern;
`get_code_snippet("GPT4oSignalProvider")` — constructor args;
`get_code_snippet("GrokSignalProvider")` — constructor args;
`get_code_snippet("GeminiSignalProvider")` — constructor args.

**What to implement:**

```python
def build_providers(env: dict | None = None) -> list[SignalProvider]:
    """
    Build the active provider list from environment variables.

    env defaults to os.environ.  Pass a dict in tests to avoid touching
    real env vars.  Returns MockSignalProvider list when UPSTOX_ENV=test.

    Reads:
      SIGNAL_PROVIDERS   — comma-separated subset of "grok,gpt4o,gemini"
                           default: "gpt4o" (Phase 1 minimal start)
      OPENROUTER_API_KEY — required for gpt4o and Phase 1 shims of grok/gemini
      XAI_API_KEY        — required for grok Phase 2
      GOOGLE_AI_API_KEY  — required for gemini Phase 2
      UPSTOX_ENV         — "test" → return [MockSignalProvider()]
    """
    ...
```

Rules:
- `UPSTOX_ENV=test` → return `[MockSignalProvider()]`, no API keys checked.
- For each name in `SIGNAL_PROVIDERS`: if the required API key is missing, log `WARNING`
  and skip that provider (do not raise).
- If the resulting list is empty (all providers skipped or none configured), log
  `WARNING` and return `[MockSignalProvider()]` as safe fallback.

**Tests (`tests/unit/signals/test_signals_factory.py`):**
- `UPSTOX_ENV=test` → returns `[MockSignalProvider()]`.
- `SIGNAL_PROVIDERS=gpt4o` + `OPENROUTER_API_KEY` set → list contains one provider
  with `provider_name=="gpt4o"`.
- Missing API key for provider in `SIGNAL_PROVIDERS` → that provider skipped; warning logged.
- Empty resulting list → `[MockSignalProvider()]` returned.
- All three providers configured → list length 3, names match `["grok", "gpt4o", "gemini"]`.

**Commit:** `feat(signals): add build_providers factory — env-driven provider selection with safe fallback`

---

## S5.1 — Config + env: `config/signals.toml` + `.env.example` updates

**Files to change:**
- `config/signals.toml` — new file
- `.env.example` — extend with signals env vars

**Before any code:**
`search_code("\\[signals\\]")` in `config/` — confirm no existing signals section;
`bash cat .env.example` — see current structure to append correctly.

**No tests required.** Config files and `.env.example` are not unit-tested.

**`config/signals.toml`:**

```toml
[signals]
min_confidence_threshold = 3    # avg confidence of agreeing models to trigger trade_action
consensus_required        = 2   # minimum models that must agree (out of 3)
call_timeout_seconds      = 30  # per-provider asyncio timeout

[signals.providers.grok]
model    = "x-ai/grok-3"        # Phase 1: OpenRouter shim; Phase 2: "grok-3" direct
search   = true                 # Phase 2 only; ignored in Phase 1 OpenRouter path
max_tokens = 512

[signals.providers.gpt4o]
model    = "openai/gpt-4o"
base_url = "https://openrouter.ai/api/v1"
max_tokens = 512

[signals.providers.gemini]
model             = "google/gemini-2.0-flash"   # Phase 1: OpenRouter; Phase 2: "gemini-2.0-flash"
search_grounding  = true                         # Phase 2 only
max_tokens        = 512
```

**Add to `.env.example`:**

```bash
# ── Signals pipeline (src/signals/) ─────────────────────────────────────────
# Phase 1: only OPENROUTER_API_KEY is required to run the pipeline.
# Phase 2: acquire XAI_API_KEY and GOOGLE_AI_API_KEY for search-enabled providers.

OPENROUTER_API_KEY=             # https://openrouter.ai  — Phase 1 start here
XAI_API_KEY=                    # https://console.x.ai   — Grok Phase 2
GOOGLE_AI_API_KEY=              # https://aistudio.google.com — Gemini Phase 2

SIGNAL_PROVIDERS=gpt4o          # comma-separated; default single provider for Phase 1
                                 # Phase 2 full: grok,gpt4o,gemini
SIGNAL_MIN_CONFIDENCE=3         # avg confidence of agreeing models to emit trade_action
```

**API token acquisition checklist (track in `.env.example` comments or TODOS.md):**
- [ ] `OPENROUTER_API_KEY` — Phase 1 can start here; covers all three models
- [ ] `XAI_API_KEY` — Phase 2 Grok with live X search
- [ ] `GOOGLE_AI_API_KEY` — Phase 2 Gemini with Google Search grounding

**Commit:** `chore(signals): add config/signals.toml and extend .env.example with signals vars`

---

## S5.2a — source-discovery spike + `src/signals/market_inputs.py`

**Why this exists:** `MarketSnapshot` needs `gift_nifty`, `fii`, and `usd_inr`, and the repo has
no fetcher for any of them. Animesh's call (2026-09-07): do *not* hard-code neutral defaults and
do *not* scrape NSE HTML — probe the broker APIs we already authenticate against (Upstox, Dhan,
Nuvama) and see which one serves each field, then build a real helper module against the
confirmed endpoints.

---

### Step 1 — source-discovery spike ✅ DONE (2026-09-07)

Persistent artifact: **`scratch/2026-09-07_signal_input_sources.py`** (`git log` it for the
probe history — commits `c0208c9`..`735cb86`). All three sources are now settled; the spike
stays in-tree as the source-of-record. **The remaining work is Step 2 only** — a fresh session
can pick this up cold from the recipe below.

### Confirmed sources (spike-verified, 2026-09-07)

**`gift_nifty` → Upstox `GLOBAL_INDEX|SGX NIFTY` via `broker.get_ltp`.**
- It is a GLOBAL index, absent from `NSE.json.gz`; lives in the separate master
  `https://assets.upstox.com/market-quote/instruments/exchange/global.json.gz`. Metadata:
  `segment GLOBAL_INDEX`, `trading_symbol "GIFT NIFTY"`, 120 s latency, trades 06:30 Mon →
  02:45 Sat — live at the 09:10 snapshot.
- The batch-LTP endpoint passes any key straight through (no segment gate), so `GLOBAL_INDEX`
  keys work on the normal path. `GLOBAL_INDICATOR` keys do **not** (see usd_inr).
- **Verified:** `get_ltp(["GLOBAL_INDEX|SGX NIFTY"]) → Decimal('23791.0')` (Nifty spot
  23779.15 — sane premium).
- **Implementation:** module constant `GIFT_NIFTY_KEY = "GLOBAL_INDEX|SGX NIFTY"`;
  `fetch_gift_nifty` = `await broker.get_ltp([GIFT_NIFTY_KEY])`, return the one value, raise
  `DataFetchError` if the dict is empty / key missing / value ≤ 0.

**`usd_inr` → Upstox `NCD_FO` USDINR **monthly** future via `broker.get_ltp`.**
- `GLOBAL_INDICATOR|USDINR` exists in the global master but **only** the historical-candle v3
  endpoint accepts it (LTP / full-quote / ohlc all `400 "Invalid Instrument key"`) — T-1
  close only, and would need a new client method. **Rejected** in favour of the future.
- The **monthly** USDINR future (`NCD_FO`, e.g. `NCD_FO|1769` = "USDINR FUT 28 SEP 26") is
  liquid — `get_ltp` returned `Decimal('94.57')` even after hours, matching the live app
  (USDINR FUT 28SEP26 = 94.5675). The weekly contract (`NCD_FO|11993`) returned `0.0` — do
  not use weeklies.
- **Value sanity:** USD/INR sits ~94.5 in this scenario (not the ~83–88 of real 2024) —
  confirmed against Animesh's live app screenshot. Do not "correct" it.
- **Expiry resolution** (prototype: `_nearest_monthly_usdinr_future` in the spike):
  ```python
  lookup = InstrumentLookup.from_file(DEFAULT_BOD_PATH)   # src.paper.constants
  futs = lookup.search("USDINR", segment="NCD_FO", instrument_type="FUT", max_results=50)
  # keep expiry >= today; group by (year, month); take the last expiry of the
  # earliest month present → that contract's instrument_key
  ```
  `InstrumentLookup.search_futures` filters `segment == "NSE_FO"` so it will NOT find these —
  use `.search(..., segment="NCD_FO", ...)`. Rollover is automatic: expired contracts drop
  from the feed, so "nearest month-end ≥ today" always lands on the live one.
- **Implementation:** `fetch_usd_inr(broker, *, lookup: InstrumentLookup | None = None)` —
  lazily build `lookup` from `DEFAULT_BOD_PATH` (same pattern as
  `PaperStore._resolve_instrument_lookup`), resolve the monthly key, `get_ltp` it, raise
  `DataFetchError` on no contract / empty LTP / value ≤ 0.

**`fii` → NSE `fiidiiTradeReact` JSON — CASH-market net (spike-verified 2026-09-07).**
- **The F&O positioning data is NOT available.** The participant-wise OI CSV
  (`nsearchives.nseindia.com/content/nsccl/fao_participant_oi_<DD-Mon-YYYY>.csv`) and every
  `fii_stats_*.csv` variant 404 for every recent date in this environment. Index-futures /
  index-options net position cannot be sourced.
- **What IS available:** `https://www.nseindia.com/api/fiidiiTradeReact` → JSON, plain
  `User-Agent: Mozilla/5.0` header, no cookie priming needed. Returns the previous session's
  **cash-market** FII/FPI and DII buy / sell / net values in ₹ cr:
  ```json
  [{"category":"DII","date":"07-Sep-2026","buyValue":"13154.13","sellValue":"12587.37","netValue":"566.76"},
   {"category":"FII/FPI","date":"07-Sep-2026","buyValue":"9581.19","sellValue":"9301.06","netValue":"280.13"}]
  ```
  Two objects; `category` is `"FII/FPI"` and `"DII"`; `netValue` = buy − sell; all values are
  strings → `Decimal(str(v))`. No date param (returns the latest published session regardless).
- **✅ MODEL CHANGE DONE in S1.1a (2026-09-07).** `FIIData` is now
  `fii_cash_net_cr` / `dii_cash_net_cr`; `prompt.py` section renamed. The note below is
  retained as the rationale of record. Original text:
- **⚠ MODEL CHANGE REQUIRED — decide before Step 2.** `FIIData` today is
  `net_futures_cr` / `net_options_cr` (index F&O positioning), used only in
  `src/signals/models.py:45-49,78` and `src/signals/prompt.py:65-66`. That data is
  unreachable. Proposed redefine to match what's fetchable:
  ```python
  class FIIData(BaseModel, frozen=True):
      """FII/DII cash-market net flows, previous session (NSE fiidiiTradeReact)."""
      fii_cash_net_cr: Decimal   # positive = FII net buyer
      dii_cash_net_cr: Decimal   # positive = DII net buyer
  ```
  and `prompt.py` §"FII Positioning (yesterday)" → "FII/DII Cash Flows (yesterday)" with the
  two new fields. Arguably a better directional-sentiment signal than F&O positioning anyway.
  This drags `models.py` + `prompt.py` + their tests into S5.2a's scope (or split as a tiny
  S1.1-amendment task first — Animesh's call).
- **Implementation:** `fetch_fii_data(broker) -> FIIData` (broker arg unused, uniform
  signature) — GET the JSON, find the `FII/FPI` and `DII` rows, build
  `FIIData(fii_cash_net_cr=Decimal(...), dii_cash_net_cr=Decimal(...))`, raise
  `DataFetchError` on download / non-200 / missing-category / parse failure. `Decimal`, never
  `float`.

### Step 2 — build `src/signals/market_inputs.py` + tests  ⬅ REMAINING WORK

```python
GIFT_NIFTY_KEY = "GLOBAL_INDEX|SGX NIFTY"

async def fetch_gift_nifty(broker: BrokerClient) -> Decimal: ...
async def fetch_usd_inr(broker: BrokerClient, *, lookup: InstrumentLookup | None = None) -> Decimal: ...
async def fetch_fii_data(broker: BrokerClient) -> FIIData: ...
```
Each returns the typed value or raises `DataFetchError` (`src.client.exceptions`) on total
failure — **no neutral fallbacks inside the helpers**; the caller (S5.2b / the cron) decides
whether to abort.

**Before any code (graph):** `get_code_snippet("FIIData")` · `get_code_snippet("MarketSnapshot")`
· `get_code_snippet("DataFetchError")` · `get_code_snippet("InstrumentLookup")` ·
`get_code_snippet("BrokerClient")` for the `get_ltp` signature (`list[str] -> dict[str, Decimal]`).

**Tests:** `tests/unit/signals/test_market_inputs.py` — one happy-path + one failure test per
function, all offline. Mock the broker (`get_ltp` returning a canned dict / raising); for
`fetch_usd_inr` inject a small hand-built `InstrumentLookup(instruments=[...])` (a couple of
USDINR FUT dicts) — do not read the real BOD file in tests; for `fetch_fii_data` monkeypatch
`requests.get` with a canned `fiidiiTradeReact` JSON body + a non-200 / missing-category case.
**No network, no real BOD file.**

**Commit (two):** spike commits already landed (`chore(signals): …spike…`). Second:
`feat(signals): market_inputs.py — gift_nifty / fii / usd_inr fetchers`.

### MarketSnapshot field-coverage audit (2026-09-07 — "did we skip anything?")

Every `MarketSnapshot` field is accounted for across S5.2a / S5.2c — nothing dropped:

| field | source | task | spike status |
|---|---|---|---|
| `trade_date` | cron param | S5.2 | — |
| `nifty_spot` | `get_ltp("NSE_INDEX\|Nifty 50")` | S5.2c | ✅ 23779.15 |
| `prev_close/high/low` | Upstox daily candle | S5.2c | ⚠ see S5.2c note — `get_historical_candles` is `NotImplementedError` on the live client |
| `gift_nifty` | `get_ltp("GLOBAL_INDEX\|SGX NIFTY")` | **S5.2a** | ✅ 23791.0 |
| `india_vix` | `get_ltp("NSE_INDEX\|India VIX")` | S5.2c | ✅ 11.16 |
| `vix_5d_trend` | computed from last 5 `signal_inputs` rows | S5.2c | — (needs 5 sessions of history) |
| `usd_inr` | `get_ltp(<nearest-monthly NCD_FO USDINR FUT>)` | **S5.2a** | ✅ 94.57 |
| `monthly_expiry` | calendar helper (Thu→Tue Apr-2026) | S5.2c | — |
| `option_chain` | `get_option_chain` → `parse_upstox_option_chain` | S5.2c | `get_option_chain` delegates OK |
| `fii` | NSE `fiidiiTradeReact` (cash) | **S5.2a** | ✅ but ⚠ model change (F&O data unreachable) |

---

## S5.2b — client `get_ohlc` + `SignalStore.get_recent_snapshots` (snapshot prereqs)

> Split out of the old combined S5.2b per Animesh (2026-09-08). This is the "prereq commit"
> half; the assembler itself is now **S5.2c**. The `FIIData` redefine that was also listed
> here landed earlier in **S1.1a** — nothing model-side remains.

**Files to change:**
- `src/client/protocol.py` — add `get_ohlc(instruments, interval="1d")` to the
  `MarketDataProvider` + `BrokerClient` protocols
- `src/client/upstox_market.py` — async `get_ohlc` = `asyncio.to_thread(self.get_ohlc_sync,
  instruments, interval)` (mirrors the existing `get_ltp` / `get_option_chain` async wrappers)
- `src/client/upstox_live.py` — `get_ohlc` delegating to `self._market.get_ohlc`
- `src/client/mock_client.py` — `get_ohlc` returning an injectable canned dict (add a
  `set_ohlc(key, ohlc)` setter; honour `_raise_if_queued("get_ohlc")`)
- `src/signals/store.py` — `SignalStore.get_recent_snapshots(n)` →
  `SELECT snapshot_json FROM signal_inputs ORDER BY trade_date DESC LIMIT ?`, returns
  `list[MarketSnapshot]` (newest first; caller reverses for oldest→newest trend)

**Before any code (graph):** `get_code_snippet("UpstoxMarketClient.get_ohlc_sync")` (return
shape — `{pipe_key: {ohlc: {open,high,low,close}, ...}}` via `_remap_response`) ·
`get_code_snippet("_remap_response")` · `get_code_snippet("SignalStore")` (read-method style
+ `_SCHEMA` for the `signal_inputs` column names).

**Tests:**
- `tests/unit/client/` — `get_ohlc` on `MockBrokerClient`: happy path (canned dict returned)
  + error path (`simulate_error` → raises).
- `tests/unit/signals/test_signals_store.py` — `get_recent_snapshots`: happy path (writes 3
  snapshots, reads them newest-first) + edge (fewer than `n` rows → returns what exists).

**Commit:** `feat(client): add get_ohlc to BrokerClient + SignalStore.get_recent_snapshots`

---

## S5.2c — `src/signals/snapshot.py`: `assemble_market_snapshot`

**Files to change:**
- `src/signals/snapshot.py` — new module (the assembler)

Depends on the S5.2b prereqs (`broker.get_ohlc`, `store.get_recent_snapshots`).

**Before any code (graph):**
`get_code_snippet("MarketSnapshot")` · `get_code_snippet("OptionChainSummary")` ·
`get_code_snippet("OILevel")` — target model shapes;
`get_code_snippet("parse_upstox_option_chain")` + `get_code_snippet("OptionChain")` — parser
returns `OptionChain{underlying_spot, expiry, strikes: dict[Decimal, OptionChainStrike]}`;
`get_code_snippet("OptionChainStrike")` for per-strike call/put legs (ltp/oi/iv/greeks);
`get_code_snippet("InstrumentLookup.get_expiry_candidates")` — the monthly-expiry mechanism;
`get_code_snippet("SignalStore")` — read API for the `vix_5d_trend` history.

**What to implement:**
```python
async def assemble_market_snapshot(broker, *, store: SignalStore, trade_date: date) -> MarketSnapshot:
    """Assemble the full MarketSnapshot from live sources at ~09:10 IST."""
```

Per-field fetch recipe (all 10 `MarketSnapshot` fields — S5.2a's three are imported here, the
other seven are built in this task):

- **`trade_date`** — the `trade_date` arg; the S5.2 cron passes `market_calendar.market_today()`.
- **`nifty_spot`** — `(await broker.get_ltp(["NSE_INDEX|Nifty 50"]))["NSE_INDEX|Nifty 50"]`.
  ✅ spike: 23779.15. Key per `REFERENCES.md` — never `"NIFTY"`.
- **`india_vix`** — `(await broker.get_ltp(["NSE_INDEX|India VIX"]))[...]`. ✅ spike: 11.16.
- **`prev_close` / `prev_high` / `prev_low`** — daily OHLC for `NSE_INDEX|Nifty 50`.
  ⚠ `BrokerClient.get_historical_candles` raises `NotImplementedError`. But
  `UpstoxMarketClient.get_ohlc_sync(["NSE_INDEX|Nifty 50"], "1d")` **is** live (wraps
  `V3_OHLC_URL`), returning `{pipe_key: {ohlc: {open,high,low,close}, ...}}` via
  `_remap_response`. Prereq (S5.2b): `broker.get_ohlc` is added to the protocol + all impls. Then read
  `["ohlc"]["close" / "high" / "low"]` as `Decimal(str(...))`. At 09:10 the `"1d"` candle is
  the previous session (today's isn't formed) — verify the exact key name against a live
  response before locking.
- **`gift_nifty`** — `market_inputs.fetch_gift_nifty(broker)` (S5.2a).
- **`usd_inr`** — `market_inputs.fetch_usd_inr(broker)` (S5.2a).
- **`fii`** — `market_inputs.fetch_fii_data(broker)` (S5.2a; + the `FIIData` redefine).
- **`monthly_expiry`** — `InstrumentLookup.from_file(DEFAULT_BOD_PATH).get_expiry_candidates(
  "NIFTY", trade_date, preference=["monthly"])[0][1]` → `date.fromisoformat(...)`. This helper
  handles the Apr-2026 Thu→Tue move — **do not hand-roll last-Thursday**; the model docstring
  that says "last Thursday" is stale.
- **`option_chain`** — `raw = await broker.get_option_chain("NSE_INDEX|Nifty 50",
  monthly_expiry.isoformat())` → `chain = parse_upstox_option_chain(raw)` → derive
  `OptionChainSummary` (below).
- **`vix_5d_trend`** — `signal_inputs` stores the whole `MarketSnapshot` as `snapshot_json`
  keyed by `trade_date` (no per-column vix). Add `SignalStore.get_recent_snapshots(n=5)`
  (`SELECT snapshot_json … ORDER BY trade_date DESC LIMIT ?`), pull `india_vix` from each,
  order oldest→newest → `"rising"` if strictly increasing, `"falling"` if strictly decreasing,
  else `"flat"`. Fallback `"flat"` when < 5 rows exist (bootstrap — first 5 sessions).

**`OptionChainSummary` derivation from `OptionChain`:**
- `atm_strike` — strike in `chain.strikes` nearest `nifty_spot`, as `int`
- `atm_iv` — mean of the ATM strike's call + put `iv`
- `iv_skew` — (first OTM call IV) − (first OTM put IV); positive = calls rich
- `pcr_total` — Σ put OI / Σ call OI across all strikes
- `pcr_atm` — put OI / call OI at the ATM strike
- `top_call_oi` / `top_put_oi` — 3 strikes with the highest call (resp. put) OI, as
  `OILevel{strike:int, oi:int, oi_change:int}` (`oi_change` vs previous day — if the Upstox
  chain response has no prior-day OI field, set `0` and note it)

**Tests:** `tests/unit/signals/test_snapshot.py` — happy path with a mock broker returning
canned LTP / OHLC / option-chain dicts + a stub `SignalStore`; one error path (broker raises →
propagates). Offline only, no real BOD file (inject `InstrumentLookup` or monkeypatch the
expiry call).

**Commit:** `feat(signals): snapshot.py — assemble_market_snapshot from live sources`

---

## S5.2 — `scripts/morning_signal.py`: 09:15 AM cron (wiring only)

**Files to change:**
- `scripts/morning_signal.py` — new script

**Depends on:** S5.2a + S5.2b. This task is pure orchestration — it must not contain any
data-source logic; that all lives in `assemble_market_snapshot`.

**Before any code:**
`get_code_snippet("SignalStore")` — current public write API;
`get_code_snippet("SignalAggregator")` — constructor and `aggregate` signature;
`get_code_snippet("build_providers")` — factory signature;
`get_code_snippet("assemble_market_snapshot")` — S5.2b entry point;
`search_code("build_notifier")` in an existing cron script (e.g. `daily_snapshot.py`)
  — see usage pattern for Telegram + structured logging;
`search_code("asyncio.gather")` in `src/` — confirm existing gather pattern.

**Cron comment at top of file:** `# 15 9 * * 1-5`

**What to implement:**

```python
async def run() -> None:
    providers = build_providers()
    broker = create_client(settings.upstox_env)
    store = SignalStore(settings.db_path)
    store.init_db()
    snapshot = await assemble_market_snapshot(broker, store=store, trade_date=date.today())
    store.record_snapshot(snapshot)

    responses = await asyncio.gather(
        *[p.get_signal(snapshot) for p in providers],
        return_exceptions=True,
    )
    valid = []
    for r in responses:
        if isinstance(r, Exception):
            log.warning("provider_error", exc=str(r))
        else:
            store.record_response(r)
            valid.append(r)

    aggregator = SignalAggregator()
    signal = aggregator.aggregate(snapshot, valid)
    store.record_signal(signal)

    notifier = build_notifier()
    if notifier:
        msg = _format_signal_notification(signal)
        await notifier.send_message(msg)

async def _format_signal_notification(signal: DailySignal) -> str:
    """One-line Telegram notification: direction, confidence, strike, agreeing models."""
    ...
```

Telegram message format:
```
📈 BULLISH — confidence 3.5 — strike 24500
Agreed: grok, gemini  |  Dissented: gpt4o
```
or:
```
⏸ NO TRADE — split signal (grok: BULLISH, gpt4o: NEUTRAL, gemini: BEARISH)
```

Structured log (JSON, same pattern as `daily_snapshot.py`): log one entry at end of run
with keys: `trade_date`, `consensus_direction`, `trade_action`, `confidence`, `agreeing_models`.

No unit tests for this script. Integration only.

**Commit:** `feat(scripts): morning_signal.py — 09:15 AM signal pipeline cron`

---

## S5.3 — `scripts/record_signal_outcome.py`: 03:00 PM outcome recorder

**Files to change:**
- `scripts/record_signal_outcome.py` — new script

**Before any code:**
`get_code_snippet("SignalStore")` — `record_outcome` and `get_signal` signatures;
`get_code_snippet("SignalOutcome")` — field list;
`search_code("argparse")` in `scripts/record_paper_trade.py` — existing argparse pattern;
`get_code_snippet("TradeAction")` — enum members.

**Cron comment at top:** `# 0 15 * * 1-5  (or run manually after market close)`

**CLI:**

```
python -m scripts.record_signal_outcome \
    --entry-premium 65.50 \
    --exit-premium 42.00 \
    [--executed]        \  # flag — omit if you chose not to trade
    [--notes "text"]    \
    [--date YYYY-MM-DD] \  # default: today
    [--auto]               # non-interactive: derive entry/exit from snapshot + LTP at 15:00
```

`--auto` mode: fetches Nifty LTP at 15:00 IST for the recommended strike,
uses it as `exit_premium`. If `entry_premium` was never recorded (not `--executed` on entry),
marks `executed=False`. Still logs the outcome for direction accuracy tracking.

`phase` is set from env var `SIGNAL_PHASE` (default `"openrouter_only"`).
When `OPENROUTER_API_KEY` is the only key set, use `openrouter_only`. When `XAI_API_KEY`
or `GOOGLE_AI_API_KEY` are also present, set `search_enabled`.

Prints: `✓ Outcome recorded for <date>: <trade_action> | P&L: ₹<pnl_per_lot> per lot`
or: `✓ Outcome recorded for <date>: <trade_action> | not executed`.

No unit tests for this script.

**Commit:** `feat(scripts): record_signal_outcome.py — 03:00 PM outcome logger with --auto mode`

---

## S5.4 — `scripts/signal_report.py`: performance report

**Files to change:**
- `scripts/signal_report.py` — new script

**Before any code:**
`get_code_snippet("SignalStore.get_all_outcomes")` — signature + filter params;
`get_code_snippet("SignalStore.get_responses")` — for per-model accuracy;
`get_code_snippet("SignalOutcome")` — field list, especially `executed` and `phase`.

**CLI:**

```
python -m scripts.signal_report
python -m scripts.signal_report --from 2026-08-01 --to 2026-10-31
python -m scripts.signal_report --phase openrouter_only
python -m scripts.signal_report --phase search_enabled
```

**Output sections (print in this order):**

```
Signal Pipeline Performance Report
Period: {from} → {to}  |  Phase: {phase or "all"}
─────────────────────────────────────────────────
OVERALL
  Trading days in period : {N}
  Signals generated      : {M}   ({N-M} NO_TRADE days)
  Executed trades        : {X}   ({M-X} skipped)
  Win rate               : {W}/{X}  =  {pct:.1f}%
  Avg P&L per lot        : ₹ {avg_pnl:,.0f}
  Expected value         : ₹ {ev:,.0f}   (win_rate × avg_win + loss_rate × avg_loss)
  Random baseline EV     : ₹ {random_ev:,.0f}   (coin flip, same entry/exit)

PER-MODEL ACCURACY  (direction_called == nifty_close > nifty_open)
  grok   : {n}/{total} = {pct:.1f}%
  gpt4o  : {n}/{total} = {pct:.1f}%
  gemini : {n}/{total} = {pct:.1f}%

CONFIDENCE CALIBRATION
  confidence 1–2 : {n} trades   win rate {pct:.1f}%
  confidence 3   : {n} trades   win rate {pct:.1f}%
  confidence 4   : {n} trades   win rate {pct:.1f}%
  confidence 5   : {n} trades   win rate {pct:.1f}%

NO_TRADE ACCURACY
  NO_TRADE days          : {n}
  Market moved > 0.5%    : {m}/{n} ({pct:.0f}%) — signal correctly avoided

PHASE BREAKDOWN
  openrouter_only : {n} trades  EV ₹{ev:+,.0f}
  search_enabled  : {n} trades  EV ₹{ev:+,.0f}
─────────────────────────────────────────────────
```

**Random baseline:** for each executed-trade day, simulate a coin-flip direction using
`hash(str(trade_date)) % 2` — deterministic and reproducible. Same entry premium, same exit.

Per-model accuracy uses `signal_responses` joined to `signal_outcomes` by `trade_date`.
Direction correct when `response.direction == BULLISH` and `nifty_close > nifty_open`,
or `response.direction == BEARISH` and `nifty_close < nifty_open`.
`NEUTRAL` responses counted as incorrect.
Skipped days (`executed=False`) still count for direction accuracy.

Confidence calibration applies only to executed trades (`executed=True`).

**Minimum trade warning:** if total executed trades < 50, print at top:
`⚠ Only {X} executed trades — results below statistical significance threshold (50 trades).`

No unit tests for this script.

**Commit:** `feat(scripts): signal_report.py — on-demand performance report with random baseline`

---

## S5.5 — Rollout state + Telegram message-format scope (discussion, no code)

**Purpose:** the pipeline is code-complete (S1–S5.4). Record the rollout state and settle
what Telegram formatting work is still owed. No source or test changes.

**Resolved (Animesh, 2026-09-09):**

1. **Crons — already live** on the Mac host (`crontab -l`); no separate enablement runbook:
   ```
   30 09 * * 1-5  scripts.morning_signal              >> logs/morning_signal.log
   00 16 * * 1-5  scripts.record_signal_outcome --auto  >> logs/record_signal_outcome.log
   35 16 * * 1-5  scripts.signal_report               >> logs/signal_report.log
   ```
   NSE-holiday early-exit guard for `morning_signal.py` / `signal_report.py` is **S5.5b**.

2. **Rollout phase — Phase 1 `openrouter_only`.** Single `OPENROUTER_API_KEY`; all three
   models (grok / gpt4o / gemini) via OpenRouter, no web search. Phase 2 (`search_enabled`,
   xAI + Google AI direct SDKs) is a later flip of `SIGNAL_PHASE` — not part of this rollout.

3. **Telegram messages:**
   - **09:15 directional** — finalized; `format_directional_v3` in
     `scratch/2026-09-08_signal_telegram_messages.py` (CONSENSUS / NO CONSENSUS / PIPELINE
     FAILED), on-device validated 2026-09-08. Implementation = **S5.5c**.
   - **entry / exit / P&L** — moved to `signals-paper-track` SPT-3 / SPT-5 (the track now
     paper-trades for real). Not owed here.
   - **`signal_report.py` 16:35 digest** — push the **full 5-section report every weekday
     run**, MarkdownV2 fenced code block, escaped per the `FORMATTING.md` boundary contract.
     Implementation = **S5.5d**.

**DoD:** `signals_tasks.md` S5.5 checked; S5.5c / S5.5d boxes carry the message specs;
`DECISIONS.md` carries the 2026-09-09 rollout bullet. No `src/`, `scripts/`, or test changes.

---

## S5.5a — Phase-1 interim outcome message (`record_signal_outcome.py`)

**Why:** `scripts/record_signal_outcome.py` is cron'd at 16:00 Mon–Fri and writes one
`SignalOutcome` row per day, but sends nothing to Telegram. Until `signals-paper-track` SPT-5
(real exit engine) lands, post the daily outcome to the channel so the direction call and its
would-be P&L are visible. **Revived 2026-09-09** (was superseded → SPT-5; SPT-5 still
supersedes when the paper track goes live).

**Before any code:** `get_code_snippet` on `record_signal_outcome.main`, `SignalOutcome`,
`morning_signal._notify` (non-fatal `build_notifier()` pattern); read `FORMATTING.md`
§escaping-boundary. `get_code_snippet('SignalOutcome')` for the exact field list before any
test helper.

**Message spec** (matches the S5.5c vertical layout — bold header, blank line, one
emoji-prefixed line per field; formatter owns its escaping, caller sends without re-wrapping):

Executed:
```
*📊 SIGNAL OUTCOME · 08 Sep*

📈 BULLISH · BUY CALL 24800
💰 Entry ₹65.50 → Exit ₹92.00
✅ P&L: +₹1,722.50 / lot

🏁 Nifty close: 24,842
🔧 Phase: openrouter_only
```

Not taken (would-be — `--auto` populated both premiums, `executed=False`):
```
*📊 SIGNAL OUTCOME · 08 Sep · NOT TAKEN*

📈 BULLISH · BUY CALL 24800
💰 Entry ₹65.50 → Exit ₹92.00 (would-be)
📝 Paper P&L: +₹1,722.50 / lot

🏁 Nifty close: 24,842
🔧 Phase: openrouter_only
```

NO_TRADE (or any run missing a premium — close-only fallback):
```
*📊 SIGNAL OUTCOME · 08 Sep · NO TRADE*

➖ No signal issued today
🏁 Nifty close: 24,842
```

**Rules:**
- Direction emoji: 📈 BULLISH / 📉 BEARISH. Action label: `BUY CALL` / `BUY PUT`.
- Would-be P&L computed **in the formatter** — `(exit_premium − entry_premium) × LOT_SIZE`
  when `pnl_per_lot is None` and both premiums are present. No `SignalOutcome` /
  `SignalStore` change.
- Premium via `format_money`; strike via `format_strike` (identifier — no separator);
  Nifty close via `fmt_inr` / `format_money` without decimals per `FORMATTING.md`.
- P&L emoji via `pnl_emoji`; sign via `format_money(..., signed=True)`.
- Missing entry **or** exit premium (non-`--auto` run, or NO_TRADE) → close-only fallback,
  never a half-populated P&L line.
- Send via `build_notifier()` after the DB write; non-fatal when no notifier configured
  (mirror `morning_signal`).

**Reference renderer:** `format_outcome_notification` in
`scratch/2026-09-08_signal_telegram_messages.py` (messages 6–8, restyled 2026-09-09).

**Tests:** no-network render of executed / not-taken / NO_TRADE + the missing-premium
fallback. Register the formatter in `tests/unit/notifications/test_escaping_guard.py` if it
lands in `src/`; a pure local helper in the script is acceptable (match `morning_signal`).

**Commit:** `feat(signals): post daily outcome to Telegram`

---

## S5.5d — `signal_report.py` digest to Telegram

**Why:** `scripts/signal_report.py` is cron'd at 16:35 Mon–Fri but only `print()`s to
`logs/signal_report.log`. Push the report to the Telegram channel so the weekday performance
readout is visible without tailing a log.

**Before any code:** `get_code_snippet` on `signal_report.main`, `morning_signal._notify`
(the non-fatal `build_notifier()` pattern), and read `FORMATTING.md` §escaping-boundary.

**Scope:**
- In `main()`, after `print("\n".join(out))`, build the same text as a MarkdownV2 fenced
  code block (```` ``` ````…```` ``` ````), escape per the boundary contract, and send via
  `build_notifier()` — non-fatal when no notifier is configured (mirror `morning_signal`).
- The `"No signal outcomes recorded for the requested window."` early return stays
  terminal-only — no Telegram push for an empty window.
- Do **not** add the NSE-holiday guard here — that is S5.5b.

**Tests:** one no-network test that the rendered message is a non-empty fenced block for a
window with outcomes; one that the empty-window path sends nothing. Register any new
formatter in `tests/unit/notifications/test_escaping_guard.py` if a `src/` formatter is
introduced (a pure local helper in the script is acceptable — match how `morning_signal`
does it).

**Commit:** `feat(signals): push signal_report digest to Telegram`

---

## S5.6 — Real entry premium at 09:15, true P&L at exit

**Why:** The 09:15 "Entry band" (`morning_signal._consensus_entry_band`) is the mean of the
agreeing models' self-reported `entry_premium_low`/`_high` — an LLM guess, never validated
against the option chain. `record_signal_outcome --auto` then books would-be P&L as
`real_exit_LTP − mean(LLM entry_premium)` (`_consensus_entry_premium`). Compounding it, the
strike is selected on the **monthly** chain (`snapshot._resolve_monthly_expiry`) while the
exit LTP is read on the **weekly** option (`record_signal_outcome._resolve_option_key`) — so
entry and exit are not even the same contract. Result: the recorded P&L is not a real trade
outcome. Fetch the recommended option's actual LTP at 09:15, persist it, use it as the entry
leg, and pin strike / entry / exit to a single expiry.

**Decision to settle before code** (single discipline — `options-strategist` advisory, not a
council): weekly vs monthly option for a daily directional signal. Recommend **weekly**
(intraday-to-few-day horizon; matches `signals-paper-track` SPT-3). Whatever is chosen,
`snapshot` strike-selection, the 09:15 entry fetch, and `_resolve_option_key` must agree.

**Before any code:** `get_code_snippet` on `DailySignal`, `SignalStore.record_signal` /
`init_db`, `morning_signal.run`, `record_signal_outcome._resolve_option_key` /
`_consensus_entry_premium` / `_fetch_ltp`. Read `DB_REGISTRY.md` (`daily_signals` row).

**Scope:**
- `src/signals/models.py` — `DailySignal.entry_premium: Decimal | None = None` (frozen
  Pydantic; str-serialized per repo Decimal rules).
- `src/signals/store.py` — `daily_signals.entry_premium TEXT` nullable; additive migration in
  `init_db` guarded like the existing ones; `record_signal` writes it; reads hydrate via
  `Decimal(row["entry_premium"])` when non-null.
- Lift `_resolve_option_key` from `record_signal_outcome.py` into `src/signals/` (shared),
  using the decided expiry preference.
- `scripts/morning_signal.py` — on a directional consensus, resolve the option key and fetch
  its LTP via the broker already created in `run()`; persist as `signal.entry_premium`.
  Non-fatal: fetch failure → WARNING + `None`.
- `scripts/record_signal_outcome.py` — `--auto` uses `signal.entry_premium` when set;
  `_consensus_entry_premium` is the fallback for back-dated / null rows only.
- `_format_signal_notification` — real "💰 Entry: ₹NNN.NN" line when `entry_premium` is set;
  keep the band line as the `None` fallback.

**Tests:** model default + round-trip; store migration + read hydration; shared resolver
happy + no-match; formatter (real entry + fallback); `record_signal_outcome` prefers stored
entry, falls back when null. No network — mock the LTP fetch.

**Commits:** Model + Store → shared resolver + 09:15 capture → `record_signal_outcome`
switch → message format.

**Note:** superseded later by `signals-paper-track` SPT-3 / SPT-5 (real paper position); this
is the Phase-1 interim fix.

---

## S6 — Docs close

**Files to change:**
- `CONTEXT.md` — add `src/signals/` to module tree; add `scripts/morning_signal.py`,
  `scripts/record_signal_outcome.py`, `scripts/signal_report.py` to scripts list
- `DECISIONS.md` — one entry: "signals module added; Phase 1 uses OpenRouter only
  (single key); Phase 2 upgrades Grok + Gemini to direct SDKs with search; phase column
  in signal_outcomes tracks contribution of search capability"
- `TODOS.md` — session log entry

No code changes. No tests. Targeted `Edit` calls only — never `Write` on these files.

**Commit:** `docs(signals): update CONTEXT.md, DECISIONS.md, TODOS.md for signals module`

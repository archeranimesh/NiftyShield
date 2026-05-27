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

## S5.2 — `scripts/morning_signal.py`: 09:15 AM cron

**Files to change:**
- `scripts/morning_signal.py` — new script

**Before any code:**
`get_code_snippet("SignalStore")` — current public write API;
`get_code_snippet("SignalAggregator")` — constructor and `aggregate` signature;
`get_code_snippet("build_providers")` — factory signature;
`search_code("build_notifier")` in an existing cron script (e.g. `daily_snapshot.py`)
  — see usage pattern for Telegram + structured logging;
`search_code("asyncio.gather")` in `src/` — confirm existing gather pattern.

**Cron comment at top of file:** `# 15 9 * * 1-5`

**What to implement:**

```python
async def fetch_market_snapshot() -> MarketSnapshot:
    """Assemble MarketSnapshot from live sources at 09:10 AM."""
    # Sources:
    # - nifty_spot / prev_ohlc : Upstox LTP + OHLC (UPSTOX_ANALYTICS_TOKEN)
    # - gift_nifty             : NSE pre-market page (web fetch)
    # - india_vix              : Upstox LTP for India VIX instrument key
    # - vix_5d_trend           : last 5 entries from signal_inputs or VIX Parquet
    # - option_chain           : Upstox option chain → parse_upstox_option_chain
    # - fii                    : NSE FII/DII CSV (T-1) web fetch
    # - usd_inr                : NSE or public API
    ...

async def run() -> None:
    providers = build_providers()
    snapshot = await fetch_market_snapshot()
    store = SignalStore(DB_PATH)
    store.init_db()
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

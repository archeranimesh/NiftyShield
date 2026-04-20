# 1.10 — Dhan live option chain client + daily snapshot

**Status:** NOT STARTED
**Owner:** Cowork
**Phase:** 1
**Blocks:** 1.12 (Phase 1 gate), 3.5 (regime signal computation needs chain snapshots)
**Blocked by:** 0.2 (OptionChain model must be source-agnostic), 1.2 (TimescaleDB container)
**Estimated effort:** L (3-7 days)
**Literature:** LIT-18 (skew and term structure consumers)

## Problem statement

Two reasons this task exists:

**First:** Live paper trading (Phase 0.6) and future live trading need Greeks-aware strike selection. Dhan's `/v2/optionchain` returns delta/gamma/theta/vega, IV, bid/ask, and OI in one call — everything needed for strategy decisions. Upstox provides similar data but Dhan is the strategic direction per `DECISIONS.md` Dhan Integration (the full backtest stack is Dhan-based, keeping live data on the same vendor simplifies tooling).

**Second:** Accumulating forward-looking chain snapshots unlocks three downstream capabilities: (a) calibrating the BS-vs-Dhan delta drift documented in 1.6a; (b) fitting slippage models against realised bid/ask data; (c) providing regime signals (IVR, skew, term structure) to Phase 3.5. None of these require the snapshot to start later. Starting it now costs one cron job and pays dividends for two years.

The Upstox option chain path remains wired as a documented fallback — the `MarketDataProvider` protocol means any consumer can swap providers without touching strategy code.

## Acceptance criteria

### Client

- [ ] `src/client/dhan_market.py` — async client implementing `MarketDataProvider` sub-protocol from `src/client/protocol.py`.
- [ ] Methods:
  - `get_option_chain(underlying_scrip: int, underlying_seg: str, expiry: date) → OptionChain` — POSTs to `/v2/optionchain`. Parses Dhan's nested `data.oc.{strike}.ce/pe.greeks.*` shape into the source-agnostic `OptionChain` model from 0.2.
  - `get_expiry_list(underlying_scrip, underlying_seg) → list[date]` — POSTs to `/v2/optionchain/expirylist`.
  - `get_ltp(instruments: list[str]) → dict[str, float]` — POSTs to `/v2/marketfeed/ltp`. Reuses the free-tier endpoint.
- [ ] Rate limiter: `RateLimiter(1, 3.0)` — 1 request per 3 seconds, per Dhan docs. Shared type with 1.3's rate limiter but separate instance with different budget.
- [ ] Authentication: reuses `DHAN_ACCESS_TOKEN` + `DHAN_CLIENT_ID` from `.env`.
- [ ] Raises `DataFetchError` (existing exception hierarchy) on HTTP errors, empty chain, or malformed response.
- [ ] Tests: fixture-driven. Record a real Dhan chain response on day one, commit to `tests/fixtures/responses/dhan_option_chain/nifty_2026_XX_XX.json`. Cover: happy path (both CE and PE populated), empty chain response, CE-only or PE-only (single-sided), rate-limiter behavior (mocked clock), malformed response.
- [ ] ≥15 tests.

### Constants module

- [ ] `src/dhan/constants.py` — `UnderlyingScrip` values as module constants, not magic numbers inside the client. At minimum: `NIFTY_50 = 13`, `NIFTY_50_SEG = "IDX_I"`. Plus `NIFTYBEES` — look up from Dhan instrument list, record here and in `REFERENCES.md`.
- [ ] Each constant has a comment citing source of the value (Dhan docs, instrument list, etc.).

### Factory integration

- [ ] `src/client/factory.py` extended: new function `create_market_data_provider(source: str | None = None) → MarketDataProvider`.
- [ ] `source` defaults to env var `MARKET_DATA_SOURCE` (default `"dhan"`).
- [ ] Valid sources: `"dhan"`, `"upstox"`, `"test"` (for MockBrokerClient).
- [ ] Factory is the ONLY module that imports `DhanMarketClient` directly — strategy code imports `MarketDataProvider` protocol only (per existing `DECISIONS.md` "Composition root pattern").

### Snapshot persistence

- [ ] New Timescale hypertable `option_chain_snapshots` in `src/backtest/schema.sql`:
  ```
  (underlying TEXT, expiry_date DATE, strike NUMERIC, option_type CHAR(2),
   snapshot_ts TIMESTAMPTZ, ltp NUMERIC, bid NUMERIC, ask NUMERIC,
   oi BIGINT, volume BIGINT, iv NUMERIC,
   delta NUMERIC, gamma NUMERIC, theta NUMERIC, vega NUMERIC,
   spot NUMERIC)
  ```
  - Primary key `(underlying, expiry_date, strike, option_type, snapshot_ts)`.
  - Hypertable on `snapshot_ts`, chunk interval 7 days.
- [ ] `src/backtest/chain_store.py` — writer for the snapshot table. Accepts an `OptionChain` object, decomposes into per-strike per-side rows, batched insert.

### Snapshot cron job

- [ ] `scripts/dhan_chain_snapshot.py`:
  - Uses `market_calendar.is_trading_day()` guard (early exit on holidays).
  - Fetches option chain for three expiries: nearest weekly, current month, next month.
  - Three API calls spaced by 3-second rate limit = ~9 second total runtime.
  - Persists each chain to `option_chain_snapshots` via `chain_store`.
  - Logs run summary: strikes fetched, rows persisted, any errors.
  - Uses `os._exit()` if the Dhan SDK ever spawns non-daemon threads (none currently, but future-proof).
- [ ] Cron entry in `README.md`: `30 15 * * 1-5` — 3:30 PM IST, 15 minutes before `daily_snapshot.py` at 3:45. Doesn't compete for rate-limit budget (separate endpoints, separate process).
- [ ] Tests: mock `DhanMarketClient`, verify: happy-path persistence, holiday guard skip, empty-chain handling, idempotency (same `snapshot_ts` second run → UPDATE not duplicate).

## Definition of Done

- [ ] `python -m pytest tests/unit/` full suite green
- [ ] `code-reviewer` agent clean on diff — heavy focus on protocol conformance and rate-limit correctness
- [ ] Fixture file committed: real Dhan response recorded from a trading-day fetch, with sensitive tokens redacted
- [ ] `src/client/CLAUDE.md` updated — two providers now (Dhan primary, Upstox fallback), composition rule unchanged
- [ ] `CONTEXT.md` "What Exists" tree updated
- [ ] `DECISIONS.md` updated with: (a) "Live market data: Dhan primary, Upstox fallback" decision, (b) capacity note on 1 req / 3 sec cap and its implications for tick-level strategies
- [ ] `REFERENCES.md` updated with Dhan `UnderlyingScrip` IDs
- [ ] `TODOS.md` session log entry added
- [ ] Cron entry added and tested manually before committing
- [ ] `BACKTEST_PLAN.md` task 1.10 checkbox ticked
- [ ] Commit sequence: client → constants → factory wire-up → chain_store → snapshot CLI + schema → tests. 5-6 commits.

## Technical notes

**Dhan response shape** (reference from docs):
```json
{
  "data": {
    "last_price": 25642.8,
    "oc": {
      "25650.000000": {
        "ce": {
          "last_price": 134,
          "top_bid_price": 133.55,
          "top_ask_price": 134,
          "oi": 3786445,
          "volume": 117567970,
          "implied_volatility": 9.789,
          "greeks": {"delta": 0.539, "theta": -15.15, "gamma": 0.00132, "vega": 12.19}
        },
        "pe": { ... }
      }
    }
  },
  "status": "success"
}
```

Parser target shape is `OptionChain` from 0.2 — agnostic naming. Parser maps:
- `data.last_price` → `OptionChain.underlying_spot`
- `data.oc.{strike}.ce.last_price` → `OptionLeg.ltp`
- `data.oc.{strike}.ce.top_bid_price` → `OptionLeg.bid`
- `data.oc.{strike}.ce.greeks.delta` → `OptionLeg.delta`
- `data.oc.{strike}.ce.implied_volatility` → `OptionLeg.iv`

**Strike keys from Dhan are strings like `"25650.000000"`** — strip trailing zeros, cast to `Decimal`. Not `float`.

**Rate limiter interaction with multiple cron jobs:** the chain snapshot cron (3:30 PM) and the daily snapshot cron (3:45 PM) are separate processes. Each has its own rate-limiter instance. They don't share state. That's fine because they hit different endpoints and budgets are per-endpoint at Dhan's end.

**Snapshot cron expiry selection logic:**
- "Nearest weekly expiry" = smallest date in `get_expiry_list()` that is ≥ today. Fail gracefully if today is an expiry day and the list is empty for the rest of the week.
- "Current month" = last Tuesday of current month. Compute from calendar, don't trust client to filter.
- "Next month" = last Tuesday of next month.

**Capacity note to record in `DECISIONS.md`:** Dhan's 1 req / 3 sec rate limit caps intraday chain refresh at ~20 per minute. Sufficient for EOD snapshots and per-trade-decision paper strategies. Not sufficient for tick-level delta-neutral adjustment (Phase 3+ concern). If a future strategy needs sub-3-second chain updates, either batch a single chain call across multiple strategies (one response covers all strikes) or fall back to Upstox. The `MarketDataProvider` protocol allows this swap without touching strategy code.

## Non-goals

- Does NOT deprecate or remove the Upstox chain path. Both coexist. Upstox is fallback.
- Does NOT snapshot EVERY expiry — only three (weekly/current-month/next-month). More comprehensive capture can be added later; starting narrow keeps the write volume manageable.
- Does NOT backfill historical chain data. Snapshots are forward-looking only. Historical backtest data comes from `rollingoption` endpoint (tasks 1.3 and related).
- Does NOT implement Greek-based strike selection at the client layer. That's strategy code (`src/strategy/*`), not client code.

## Follow-up work

- Phase 3.5 consumes `option_chain_snapshots` for IVR, skew, term-structure signals.
- Phase 4.3 slippage-prediction ML model uses the accumulated bid/ask data.
- Future consideration: snapshot frequency. Currently once daily. May upgrade to 2-3x daily (morning + midday + close) if signal analysis benefits from intraday resolution. Trivial cron change, no code work.

---

## Session log

_(append-only, dated entries)_

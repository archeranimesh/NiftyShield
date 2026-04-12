# NiftyShield — Planner

> Forward-looking roadmap. Read when starting new feature work or evaluating architecture changes.
> Distinct from TODOS.md (immediate actionable items) — this covers multi-sprint thinking,
> blocked items, and design decisions being evaluated.

---

## Current Sprint (April 2026)

### ~~Context reorganisation~~ — DONE (2026-04-12)
CONTEXT.md split + DECISIONS.md + REFERENCES.md + TODOS.md + PLANNER.md. Module CLAUDE.md files, commit skill, code-reviewer + test-runner agents, PROJECT_INSTRUCTIONS_DRAFT.md, CODE_REVIEW.md archived.

### Next up: Greeks capture
- Define `OptionChain` Pydantic model using `tests/fixtures/responses/nifty_chain_2026-04-07.json`
- Implement `_extract_greeks_from_chain()` in `src/portfolio/tracker.py`
- Fix the option chain API call (must use `NSE_INDEX|Nifty 50`)
- Store Greeks columns in `daily_snapshots` (columns exist, currently null)
- Tests: fixture-driven, fully offline

### After Greeks: `scripts/roll_leg.py`
- Atomic close + open in a single DB transaction
- Hard deadline: JUN 2026 expiry roll on 2026-06-30
- Validate both legs via `Trade` model before writing
- Print updated net position after roll

---

## Near-Term (May–June 2026)

### `src/models/` migration
Move `portfolio/models.py` + `mf/models.py` to `src/models/` in one refactor commit.
Trigger: when starting `src/strategy/` — both model sets migrate together.
Stub type aliases in `protocol.py` (`X = Any`) get replaced with real imports at the same time.

### FinRakshak effectiveness tracking
Automated monthly report: FinRakshak P&L vs MF portfolio drawdown.
`finrakshak_day_delta` already in `PortfolioSummary` — query over snapshot history.

### P&L visualization
Matplotlib chart from `daily_snapshots` time series (component breakdown over time).
Start once 4+ weeks of snapshot data available.
`snapshot_date` field already in `PortfolioSummary` — ready to query.

---

## Medium-Term (Q3 2026 — post static IP)

### Order execution layer (`src/execution/`)
Unblocked when static IP is provisioned.
- `place_order`, `modify_order`, `cancel_order` on `UpstoxLiveClient`
- GTT orders for SL management
- Pre-order margin validation via `src/risk/`
- All logic already designed against `BrokerClient` protocol — implementation is straightforward once unblocked

### Risk module (`src/risk/`)
- Margin checks (pre-order validation)
- Position sizing for short strangles / Iron Condors
- Delta monitoring and rebalance triggers
- Depends on: Greeks capture being live + order execution unblocked

### Strategy engine (`src/strategy/`)
- Signal generation for NiftyBees price action (demand/supply zones)
- Entry/exit logic for delta-neutral positions
- Connects to websocket streaming for real-time triggers

### Websocket streaming (`src/streaming/`)
- `live.py`: Upstox websocket handler
- `recorder.py`: `StreamRecorder` — captures live ticks to Parquet
- `replay.py`: `ReplayMarketStream` — replays from Parquet at configurable speed

---

## Long-Term (Q4 2026+)

### Backtesting engine (`src/backtest/`)
- Currently blocked: Expired Instruments API requires paid subscription
- Interim: NSE option chain CSV dumps as backtest data source
- Data models already designed against target Upstox schema — migration seamless when API unlocks
- `bootstrap.py` in `data/` will add Upstox as second data source with no downstream changes

### Rate limiter + retry middleware
- Token bucket decorator for all API calls
- Exponential backoff with jitter for retryable errors (429, 5xx, timeout)
- Idempotent order placement (correlation IDs)
- Build when moving to live order execution

---

## Blocked Items

| What | Blocked By | ETA |
|---|---|---|
| Order execution (place/modify/cancel) | Static IP not provisioned | Unknown |
| GTT orders, webhooks | Static IP not provisioned | Unknown |
| Historical candles (expired instruments) | Paid Upstox subscription | Unknown |
| Expired option contracts | Paid Upstox subscription | Unknown |
| Portfolio/positions read on `UpstoxLiveClient` | Daily OAuth token not wired | When needed |

---

## Design Decisions Being Evaluated

**Replace `UpstoxMarketClient` (sync `requests`) with full async `aiohttp` client:**
Pros: eliminates the sync/async mismatch, removes the only sync network call, cleaner `UpstoxLiveClient` delegation.
Cons: larger change, breaks existing `test_client.py` tests, needs aiohttp fixture pattern.
Status: deferred until order execution is unblocked (natural refactor moment).

**`src/models/` timing:**
Option A: migrate now before strategy engine (cleaner start for new modules).
Option B: wait until strategy engine sprint (one large refactor vs two smaller ones).
Status: leaning Option B — no current consumers need shared models urgently.

**Nuvama order execution:**
Currently read-only. Evaluate whether to wire order execution for Nuvama's bond/NCD legs
(would bypass Upstox static IP constraint for non-F&O legs).
Status: deferred — assess after Upstox order execution is live for comparison.

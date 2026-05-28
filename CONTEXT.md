# NiftyShield — Project Context

> **For AI assistants:** This file is the authoritative state of the codebase.
> Read this before writing any code. Do not rely on session summaries or chat history.
> Repo: https://github.com/archeranimesh/NiftyShield

**Related files:** [MISSION.md](MISSION.md) — immutable mission + grounding principles | [DECISIONS.md](DECISIONS.md) | [REFERENCES.md](REFERENCES.md) | [TODOS.md](TODOS.md) | [PLANNER.md](PLANNER.md) | [BACKTEST_PLAN.md](BACKTEST_PLAN.md) — Phase 0 active tasks only (~300 lines) | [BACKTEST_PLAN_PHASE1.md](BACKTEST_PLAN_PHASE1.md) — Phase 1+ tasks (load only after Phase 0.8 gate) | [LITERATURE.md](LITERATURE.md) — concept reference (Kelly, Sharpe, meta-labeling) | [docs/plan/](docs/plan/) — one story file per task | [INSTRUCTION.md](INSTRUCTION.md)
---

## Current State (as of 2026-05-25)

### What Exists (committed and working)

Full file-level module tree: **[CONTEXT_TREE.md](CONTEXT_TREE.md)**
Load that file when adding new modules or doing a full structural survey.
Key top-level packages: `src/auth`, `src/client`, `src/models`, `src/portfolio`, `src/paper`, `src/mf`, `src/dhan`, `src/nuvama`, `src/intraday`, `src/instruments`, `src/market_calendar`, `src/notifications`, `src/utils`, `src/backtest`, `src/risk`, `src/gamma`, `src/db.py`
`src/risk/` — portfolio-level delta risk controls. `PortfolioDelta` frozen dataclass (`src/risk/models.py`): `options_delta_lots`, `niftybees_delta_lots`, `total_delta_lots`, `warning_breached`, `cap_breached`, `as_of`. `PortfolioDeltaTracker` (`src/risk/delta_tracker.py`): `aggregate_delta(paper_positions, nifty_spot, lot_size) → PortfolioDelta`; options-only thresholds warning=0.75/cap=1.0 lots, combined thresholds warning=1.5/cap=2.0 lots; parameterised via constructor. CE/futures = `net_qty/lot_size`; PE = `-net_qty/lot_size`; NiftyBees = `qty×avg_cost/(spot×lot_size)`. `check_entry_allowed` (`src/risk/entry_gate.py`): protective entries always allowed; cap → block; warning → allow with message. 20 unit tests in `tests/unit/risk/test_delta_tracker.py`.
`src/gamma/` — scaffolding, data models (`GammaChainSnapshot` and `GammaWatchlistEntry` frozen dataclasses), and persistence (`GammaStore` SQLite operations) for Near-Expiry Gamma Buy strategy.
`src/backtest/ivr.py` — `compute_ivr(vix_today, vix_series)`: IVR formula over trailing 252-day VIX window; returns `float | None`; clamps to `[0.0, 1.0]`; flat-window safe (returns 0.5). 11 unit tests in `tests/unit/backtest/test_ivr.py`.
`src/backtest/vix_ingest.py` — India VIX ingestion pipeline. Supports NSE CSV (legacy) and Upstox API.canonical Parquet storage: `data/historical/ohlc/india_vix/`. Resumable — identifies gaps and fetches missing days. 7 unit tests in `tests/unit/backtest/test_vix_ingest.py`.
`src/backtest/chain_writer.py` — `ChainWriter` class for EOD and intraday chain snapshot Parquet writes. 8 unit tests in `tests/unit/backtest/test_chain_writer.py`.
`src/backtest/chain_reader.py` — `ChainReader` class for DuckDB-based option chain EOD and intraday query scan utilities. 8 unit tests in `tests/unit/backtest/test_chain_reader.py`.

`src/models/options.py` — `OptionLeg`, `OptionChainStrike`, `OptionChain` (all `frozen=True` Pydantic). Source-agnostic field names; Upstox parser in `src/client/upstox_market.py` (`parse_upstox_option_chain`). Dhan parser deferred to chain-data story (`docs/plan/chain-data/`).
`src/paper/` — paper trading module. `PaperTrade` model (frozen Pydantic, `paper_` prefix enforced, includes `ivr_at_entry: float | None`), `PaperPosition` + `PaperNavSnapshot` + `PaperLegSnapshot` (frozen dataclasses), `PaperStore` (`paper_trades` + `paper_nav_snapshots` + `paper_leg_snapshots` tables in shared SQLite), `PaperTracker` (compute_pnl + record_daily_snapshot). `PaperStore` API: `record_leg_snapshot` (upsert; enforces `total_pnl == unrealized_pnl + realized_pnl`), `get_leg_snapshot`, `get_prev_leg_snapshot`, `delete_trade` (no-op if missing). See `src/paper/CLAUDE.md` for full invariants.
Scripts: `daily_snapshot.py`, `morning_nav.py`, `nuvama_intraday_tracker.py`, `intraday_tracker.py` (combined Dhan+Nuvama orchestrator, `*/15 9-15 * * 1-5`; fetches Nifty+VIX once async), `seed_*.py`, `record_trade.py`, `record_paper_trade.py` (supports `--underlying/--strike/--option-type/--expiry` auto-lookup via BOD JSON; `--expiry` optional — omit for auto-selection via `get_expiry_candidates`; integrates India VIX IVR computation and R3 entry gate warnings (IVR < 0.25 warn low-vol, 0.25–0.50 attention in-window, > 0.50 warn high-vol); `--vix-data-dir` arg), `paper_snapshot.py` (standalone paper mark-to-market), `roll_leg.py`, `find_strike_by_delta.py` (live option chain → filter by |delta| range → cross-ranks across all candidate expiries (monthly→quarterly→yearly from BOD) when `--expiry` omitted; strike/IV/key table + `--dry-run` record_paper_trade commands), `paper_3track_overlay.py` (live-fetch overlay entry for all 3 tracks; PP/CC/collar; CC permanently blocked on futures track), `paper_3track_snapshot.py` (canonical EOD cron — live spot fetch + per-leg delta-from-yesterday + writes to `paper_leg_snapshots`; `--no-save` for dry-run), `paper_3track_overlay_roll.py` (rolls expiring overlay legs at DTE ≤ 5; atomic close+open; collar is 4-trade atomic with full rollback chain; `--force` to bypass DTE gate), `bhavcopy_bootstrap.py` (resumable bulk NSE bhavcopy download 2016–present; auto-detects legacy vs UDiFF format — UDiFF URL tried first, 404 falls back to legacy; NSE_COOKIE env-var required for Akamai bypass)
`src/instruments/lookup.py` — `get_expiry_candidates(underlying, today, preference)`: enumerates NIFTY expiries from BOD JSON into monthly (DTE 15–45) / quarterly (46–200) / yearly (201–420) buckets; default preference `["monthly","quarterly","yearly"]`; custom order accepted for hedge use.

**Research tooling (docs/):**
`docs/strategies/regime_probe.pine` — Pine Script v6 sensor script (not a trading strategy). Outputs a structured 22-row `table.new()` on the last bar covering: regime label, regime code (−2→3), options recommendation, full ADX/DI block, ATR with 252-bar percentile rank, BB width with percentile rank, RSI, 20-day annualized HV, India VIX via `request.security()`, and bar date. Designed for MCP extraction via `data_get_pine_tables`. Study identified by name (stable across sessions). Key-value fallback via `label.new()` pipe-delimited text. Operational tool: load on NIFTY 1D and 1W at each paper trade entry (BACKTEST_PLAN.md Phase 0 gate criteria C/D).
`docs/archive/tv_mcp_testing_framework.md` — 7-phase capability probe for `tradesdontlie/tradingview-mcp` (CDP-based, connects to TradingView Desktop). Validated 2026-05-23: Phase 3 confirmed table readability end-to-end; Phase 3C confirmed timeframe switching updates correctly (no stale data). Archived — findings fully captured in `DECISIONS.md → TradingView MCP Regime Probe`.

### What Does NOT Exist Yet

- `src/nuvama/CLAUDE.md` — module context file not yet written
- `src/strategy/`, `src/execution/`, `src/backtest/`, `src/risk/`, `src/streaming/` — all empty (planned per BACKTEST_PLAN.md Phase 1–2)
- `src/gamma/` script logic (`gamma_daily_watch.py`) — planned for Phase A next (scaffolding and store implemented in Task B1)

### Live Data

- SQLite DB path confirmed: `data/portfolio/portfolio.sqlite`
- DB wiped clean on 2026-04-04 (`daily_snapshots`, `mf_transactions`, `mf_nav_snapshots` all cleared)
- `mf_transactions` re-seeded with all 11 schemes using correct AMFI codes
- `mf_nav_snapshots` empty — first clean snapshot on Monday 2026-04-06 (pre-market run)
- `daily_snapshots` empty — first clean baseline on Monday 2026-04-06 (pre-market run)
- `underlying_price` will populate from 2026-04-06 onwards
- Greeks columns are null across all snapshots
- `trades` table seeded 2026-04-08 — 7 rows: finideas_ilts (6 legs including LIQUIDBEES) + finrakshak (1). EBBETF0431 net=465 @ avg ₹1388.01. **strategy_name migrated 2026-04-08:** `ILTS` → `finideas_ilts`, `FinRakshak` → `finrakshak` to match strategies table. Must use DB strategy names in all future `record_trade.py` calls.
- `nuvama_intraday_snapshots` logging active on 2026-04-17 (30-day retention loop engaged automatically).
- Cron jobs set up: `45 15 * * 1-5` for daily EOD options recording, plus `*/5 9-15 * * 1-5` for intraday extremes monitoring.

---

## Key Decisions

Architecture decisions, rationale, and deferred items: **[DECISIONS.md](DECISIONS.md)**
Instrument keys, AMFI codes, API quirks, auth tokens: **[REFERENCES.md](REFERENCES.md)**

---

## Current Constraints

| Constraint | Workaround |
|---|---|
| Order execution blocked (static IP required) | MockBrokerClient for all order dev/testing |
| Expired Instruments API blocked (paid tier) | NSE option chain CSV dumps as interim backtest source |
| Greeks columns in DB | Populated from 2026-04-25 onwards via `_fetch_greeks()` + `parse_upstox_option_chain` |
| `underlying_price` null for pre-2026-04-06 snapshots | DB wiped; clean baseline starts Monday |
| Upstox has no MF API | AMFI flat file as sole NAV source; MF holdings managed via seed script + monthly SIP inserts |
| MF NAV at 3:45 PM cron is T-1 | Expected for MFs — AMFI publishes after market close. Combined summary shows mixed-timestamp data by design. |
| Day-change P&L | **Implemented** — Δday shown in combined summary from 2026-04-07 |

---

## Pre-Task Protocol (for AI assistants)

Before writing any code: read `CONTEXT.md`, state `CONTEXT.md ✓`, confirm scope, state plan. See `CLAUDE.md` for full protocol.
- Architecture decisions or new modules: also read `DECISIONS.md`
- Instrument keys, market data, AMFI codes: also read `REFERENCES.md`
- Starting new feature work: also read `TODOS.md` + `PLANNER.md`
- Working on backtest, paper trading, strategy research, or any Phase 0 task: also read `BACKTEST_PLAN.md` (Phase 0, ~300 lines). Phase 1+ work: also read `BACKTEST_PLAN_PHASE1.md` (only after Phase 0.8 gate passes). Tick `[x]` only when the task's DoD is fully met and the commit has landed. Do not skip phase gates.
- Working in a `src/` module: that module's `CLAUDE.md` loads automatically

## Immediate TODOs

Open work and priority order: **[TODOS.md](TODOS.md)**.

---

## Strategy Definitions

Strategy leg tables (instrument keys, entry prices, quantities, protected MF portfolio) are in **[REFERENCES.md](REFERENCES.md)**.

---

## Test Coverage

- **Total: ~1449 tests** (paper module: 92 tests across Phases A–D all passing; 6 new expiry-candidate tests in `tests/unit/instruments/test_expiry_candidates.py`; pre-existing failures in `test_upstox_live.py` + `test_mock_client.py` — `pytest-asyncio` not installed in sandbox, not code regressions)
- Run: `python -m pytest tests/unit/`
- Auth tests: `tests/unit/auth/` (64 tests — Nuvama login + verify, Dhan login + verify)
- MF tests: `tests/unit/mf/` (127 tests)
- Portfolio tests: `tests/unit/portfolio/` + `tests/unit/test_portfolio.py` (94+ tests — includes 4 record_roll store tests + 10 _build_trades script tests)
- Client tests: `tests/unit/test_client.py`, `test_protocol.py`, `test_exceptions.py`, `test_factory.py`, `test_mock_client.py`, `test_upstox_live.py` (90+ tests)
- Snapshot tests: `tests/unit/test_daily_snapshot_historical.py`, `test_daily_snapshot_helpers.py`, `test_notifications.py` (50+ tests)
- Dhan tests: `tests/unit/dhan/` (152 tests — models, positions parser/filter/formatter, store options+margin, daily_snapshot integration)
- Nuvama tests: `tests/unit/nuvama/` (169 tests — bond models, bond store, reader, seed, **NuvamaOptionPosition + NuvamaOptionsSummary models (AR-3), parse_options_positions + build_options_summary (AR-3), record_all_options_snapshots atomic (AR-7), record_intraday_positions, get_intraday_extremes, purge_old_intraday (AR-3), get_monthly_realized_pnl (Phase E)**; test_portfolio_summary_nuvama.py deleted — superseded by composed model structure)

---

## Session Log

Full session log has moved to **[TODOS.md](TODOS.md)**.

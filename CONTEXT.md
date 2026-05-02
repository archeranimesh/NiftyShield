# NiftyShield — Project Context

> **For AI assistants:** This file is the authoritative state of the codebase.
> Read this before writing any code. Do not rely on session summaries or chat history.
> Repo: https://github.com/archeranimesh/NiftyShield

**Related files:** [MISSION.md](MISSION.md) — immutable mission + grounding principles | [DECISIONS.md](DECISIONS.md) | [REFERENCES.md](REFERENCES.md) | [TODOS.md](TODOS.md) | [PLANNER.md](PLANNER.md) | [BACKTEST_PLAN.md](BACKTEST_PLAN.md) — Phase 0 active tasks only (~300 lines) | [BACKTEST_PLAN_PHASE1.md](BACKTEST_PLAN_PHASE1.md) — Phase 1+ tasks (load only after Phase 0.8 gate) | [LITERATURE.md](LITERATURE.md) — concept reference (Kelly, Sharpe, meta-labeling) | [docs/plan/](docs/plan/) — one story file per task | [INSTRUCTION.md](INSTRUCTION.md)
---

## Current State (as of 2026-05-01)

### What Exists (committed and working)

Full file-level module tree: **[CONTEXT_TREE.md](CONTEXT_TREE.md)**
Load that file when adding new modules or doing a full structural survey.
For task work, use the graph: `search_graph`, `get_code_snippet`, `trace_path`.

Key top-level packages: `src/auth`, `src/client`, `src/models`, `src/portfolio`, `src/paper`, `src/mf`, `src/dhan`, `src/nuvama`, `src/instruments`, `src/market_calendar`, `src/notifications`, `src/utils`, `src/db.py`

`src/models/options.py` — `OptionLeg`, `OptionChainStrike`, `OptionChain` (all `frozen=True` Pydantic). Source-agnostic field names; Upstox parser in `src/client/upstox_market.py` (`parse_upstox_option_chain`). Dhan parser deferred to Phase 1.10.
`src/paper/` — paper trading module. `PaperTrade` model (frozen Pydantic, `paper_` prefix enforced), `PaperPosition` + `PaperNavSnapshot` (frozen dataclasses), `PaperStore` (`paper_trades` + `paper_nav_snapshots` tables in shared SQLite), `PaperTracker` (compute_pnl + record_daily_snapshot). See `src/paper/CLAUDE.md` for module invariants.
Scripts: `daily_snapshot.py`, `morning_nav.py`, `nuvama_intraday_tracker.py`, `seed_*.py`, `record_trade.py`, `record_paper_trade.py` (supports `--underlying/--strike/--option-type/--expiry` auto-lookup via BOD JSON), `paper_snapshot.py` (standalone paper mark-to-market), `roll_leg.py`

### What Does NOT Exist Yet

- `src/nuvama/CLAUDE.md` — module context file not yet written
- `src/strategy/`, `src/execution/`, `src/backtest/`, `src/risk/`, `src/streaming/` — all empty (planned per BACKTEST_PLAN.md Phase 1–2)

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

- **Total: ~1010 tests** (985 passing; 25 pre-existing `test_upstox_live.py` failures — `pytest-asyncio` not installed in sandbox, not code regressions)
- Run: `python -m pytest tests/unit/`
- Auth tests: `tests/unit/auth/` (64 tests — Nuvama login + verify, Dhan login + verify)
- MF tests: `tests/unit/mf/` (127 tests)
- Portfolio tests: `tests/unit/portfolio/` + `tests/unit/test_portfolio.py` (94+ tests — includes 4 record_roll store tests + 10 _build_trades script tests)
- Client tests: `tests/unit/test_client.py`, `test_protocol.py`, `test_exceptions.py`, `test_factory.py`, `test_mock_client.py`, `test_upstox_live.py` (90+ tests)
- Snapshot tests: `tests/unit/test_daily_snapshot_historical.py`, `test_daily_snapshot_helpers.py`, `test_notifications.py` (50+ tests)
- Dhan tests: `tests/unit/dhan/` (90 tests — models, reader, store, daily_snapshot integration)
- Nuvama tests: `tests/unit/nuvama/` (163 tests — bond models, bond store, reader, seed, **NuvamaOptionPosition + NuvamaOptionsSummary models (AR-3), parse_options_positions + build_options_summary (AR-3), record_all_options_snapshots atomic (AR-7), record_intraday_positions, get_intraday_extremes, purge_old_intraday (AR-3)**; test_portfolio_summary_nuvama.py deleted — superseded by composed model structure)

---

## Session Log

Full session log has moved to **[TODOS.md](TODOS.md)**.

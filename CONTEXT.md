# NiftyShield — Project Context

> **For AI assistants:** This file is the authoritative state of the codebase.
> Read this before writing any code. Do not rely on session summaries or chat history.
> Repo: https://github.com/archeranimesh/NiftyShield

**Related files:**
[MISSION.md](MISSION.md) — immutable mission + grounding principles |
[DECISIONS.md](DECISIONS.md) | [REFERENCES.md](REFERENCES.md) | [TODOS.md](TODOS.md) |
[PLANNER.md](PLANNER.md) | [BACKTEST_PLAN.md](BACKTEST_PLAN.md) — Phase 0 active tasks only
(~300 lines) | [BACKTEST_PLAN_PHASE1.md](BACKTEST_PLAN_PHASE1.md) — Phase 1+ tasks (load only
after Phase 0.8 gate) | [LITERATURE.md](LITERATURE.md) — concept reference (Kelly, Sharpe,
meta-labeling) | [LOGGING.md](LOGGING.md) — logging standard | [docs/plan/](docs/plan/) — one
story file per task | [INSTRUCTION.md](INSTRUCTION.md)

---

## Current State (as of 2026-08-26)

### What Exists (committed and working)

Full file-level module tree with per-file descriptions: **[CONTEXT_TREE.md](CONTEXT_TREE.md)**.
Feature and bug-fix history with rationale (every `BUG-*` / `SNAP-*` / `PG-*` / council
ruling referenced below): **[DECISIONS.md](DECISIONS.md)**.
Verbatim snapshot of the previous prose version of this section (nothing was deleted, only
relocated): **[docs/archive/CONTEXT_WHAT_EXISTS_2026-08.md](docs/archive/CONTEXT_WHAT_EXISTS_2026-08.md)**.

Top-level `src/` packages, one line each (detail → `CONTEXT_TREE.md`):

- `src/auth/` — Upstox OAuth + Nuvama request_id + Dhan manual-token login/verify flows.
- `src/client/` — `BrokerClient` protocol + 4 impls (Upstox live/sandbox, Mock); `factory.create_client(env)`; order exec + portfolio read blocked (static IP / daily token).
- `src/models/` — canonical domain types: `Leg`/`Trade`/`Strategy`/`DailySnapshot`/`PortfolioSummary` (portfolio.py), MF types (mf.py), `OptionLeg`/`OptionChain` frozen Pydantic (options.py).
- `src/portfolio/` — live (non-paper) P&L: `PortfolioStore`, `PortfolioTracker`, pure `summary.py`/`formatting.py`, `SnapshotService`, `overlay_coverage.py`; finideas strategies (ILTS, FinRakshak).
- `src/paper/` — paper-trading engine. Models: `PaperTrade`, `PaperPosition`, `PaperNavSnapshot`,
  `PaperLegSnapshot`, `PaperExitEvent`, `TrackComparisonSnapshot`, `TradeState` enum. `PaperStore`
  (SQLite — `paper_trades`, `paper_nav_snapshots`, `paper_leg_snapshots`, `paper_exit_events`,
  `gate_violations`, `warn_signal_state`, `paper_track_comparison_snapshots`, …). `PaperTracker`
  (`compute_pnl`, `compute_pnl_by_leg_group`), fill simulator, selectors.
- `src/strategy/` — paper-backbone strategy layer. `PaperStrategy` protocol,
  `SignalEvent`/`ApprovedAction`/`LegSpec`/`LegClose`, `StrategyMonitor` daemon (tick loop, WARN
  dedup, auto-execute dispatch), `PaperExecutor`, `ReEntryMixin`. 7 strategies: `CSPNiftyV1`,
  `CCOverlayV1`, `PPOverlayV1`, `CollarOverlayV1`, `IronCondorV1`, `IronCondorV2`,
  `NiftyTrackComparisonV1`. Engines: `ExitSignalEngine`, `ProfitLockEngine`, `OverlayCloser`,
  `ic_close_executor`, `roll_utils`.
- `src/risk/` — portfolio-level delta controls: `PortfolioDelta` frozen dataclass,
  `PortfolioDeltaTracker.aggregate_delta(...)` (chain-derived `position_deltas` used as-is, else
  CE/PE approximation with logged WARNING; pure/zero-I/O per council 2026-07-02),
  `check_entry_allowed` gate.
- `src/mf/` — MF transaction ledger: `MFTransaction`/`MFNavSnapshot`/`MFHolding`, `MFStore`, AMFI flat-file `nav_fetcher`, `MFTracker`.
- `src/dhan/` — Dhan holdings + intraday options: frozen models, pure `reader.py`/`positions.py` (classify/enrich/charges), `DhanStore`.
- `src/nuvama/` — Nuvama bonds + options: frozen models, `reader.py`/`options_reader.py` (pure parse + aggregate), `NuvamaStore` (bond + options + intraday snapshot tables, SQL-layer aggregation).
- `src/intraday/` — `IntradayMarketStore`: broker-agnostic `intraday_market_snapshots` table, 30-day retention, stale-row guard.
- `src/instruments/` — `DateAwareLotSizeResolver`, `strike_selector` (filter/gate/rank + `_apply_liquidity_gate`), offline BOD `lookup` (ranked fuzzy search, `get_expiry_candidates`).
- `src/market_calendar/` — NSE holiday detection from version-controlled YAML: `is_trading_day`, `prev_trading_day` (fail-open).
- `src/notifications/` — `NotifierProtocol`, `TelegramNotifier` (non-fatal, HTML `<pre>`),
  `TelegramGateway` (council-free approval dispatch + callback polling + chat-ID allowlist),
  `formatting.py` (per-type value formatters + table builders).
- `src/backtest/` — offline research: `compute_ivr` (trailing 252-day VIX IVR), `vix_ingest` (NSE CSV + Upstox), `ChainWriter`/`ChainReader` (Parquet + DuckDB), bhavcopy ingest/loader.
- `src/gamma/` — Near-Expiry Gamma Buy scaffolding: frozen models + `GammaStore`.
- `src/council/` — AI council infra: `RapidCouncil` (parallel Stage-1 fan-out + chairman synthesis), request/response models.
- `src/utils/` — `setup_logging(*, json, level)` (structlog, canonical entrypoint — see `LOGGING.md`), `fmt_inr` Indian-numbering formatter.
- `src/config.py` — `Settings(BaseSettings)` singleton; declares every env var. `src/db.py` — shared SQLite context manager (WAL, FK, auto commit/rollback).

Scripts (`scripts/`, organised by functional axis — `pipeline/`, `lookup/`, `record/`,
`strategies/`, `portfolio/`, `intraday/`, `reporting/`, `seed/`, `council/`, `dev/`, plus
top-level crons `healthcheck.py`, `eod_summary.py`, `pre_market_brief.py`,
`monitor_daemon.py`): see `CONTEXT_TREE.md` §`scripts/`.

Developer + research tooling (`pyproject.toml`, `Makefile`, `.pre-commit-config.yaml`,
`.github/workflows/ci.yml`, `docs/strategies/regime_probe.pine`): see `CONTEXT_TREE.md`
§"Developer tooling" and §"Research tooling".

### What Does NOT Exist Yet

- `src/execution/`, `src/streaming/` — empty (planned per BACKTEST_PLAN.md Phase 1–2)
- PT-S2 Signal Pipeline (`src/strategy/signal_pipeline.py`) — blocked on signals story + OpenRouter API key

### Live Data

- SQLite DB path confirmed: `data/portfolio/portfolio.sqlite`
- DB wiped clean on 2026-04-04 (`daily_snapshots`, `mf_transactions`, `mf_nav_snapshots` all cleared)
- `mf_transactions` re-seeded with all 11 schemes using correct AMFI codes
- `mf_nav_snapshots` empty — first clean snapshot on Monday 2026-04-06 (pre-market run)
- `daily_snapshots` empty — first clean baseline on Monday 2026-04-06 (pre-market run)
- `underlying_price` will populate from 2026-04-06 onwards
- Greeks columns are null across all snapshots
- `trades` table seeded 2026-04-08 — 7 rows: finideas_ilts (6 legs including LIQUIDBEES) +
  finrakshak (1). EBBETF0431 net=465 @ avg ₹1388.01. **strategy_name migrated 2026-04-08:**
  `ILTS` → `finideas_ilts`, `FinRakshak` → `finrakshak` to match strategies table. Must use DB
  strategy names in all future `record_trade.py` calls.
- **2026-07-14:** Manual Zerodha close, 4 `record_trade.py` entries. `finideas_ilts`
  NIFTY_JUL_CE (`NSE_FO|63895`) and NIFTY_JUL_PE (`NSE_FO|63896`) closed to 0 (both legs of the
  post-roll overlay). NIFTY_DEC_PE hedge (`NSE_FO|37810`) closed to 0 in both `finideas_ilts`
  and `finrakshak` (130 combined units sold @ ₹269.95, split 65/65 by strategy). `finideas_ilts`
  now holds only the EBBETF0431 leg live. See REFERENCES.md strategy tables + TODOS.md session
  log for per-leg detail.
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
- Working on backtest, paper trading, strategy research, or any Phase 0 task: also read
  `BACKTEST_PLAN.md` (Phase 0, ~300 lines). Phase 1+ work: also read `BACKTEST_PLAN_PHASE1.md`
  (only after Phase 0.8 gate passes). Tick `[x]` only when the task's DoD is fully met and the
  commit has landed. Do not skip phase gates.
- Working in a `src/` module: that module's `CLAUDE.md` loads automatically
- Adding a new entrypoint script or any `logger.*()` call: also read `LOGGING.md` (canonical logging standard; see `BUG-010` in `docs/bugs/bugs.md`)

## Immediate TODOs

Open work and priority order: **[TODOS.md](TODOS.md)**.

---

## Strategy Definitions

Strategy leg tables (instrument keys, entry prices, quantities, protected MF portfolio) are in **[REFERENCES.md](REFERENCES.md)**.

---

## Test Coverage

- **~2982 tests, last green 2026-08-26** (2980 passed, 2 skipped — `python -m pytest tests/unit/`).
- Per-module breakdown (last snapshot, not re-verified every pass):
  **[docs/archive/CONTEXT_WHAT_EXISTS_2026-08.md](docs/archive/CONTEXT_WHAT_EXISTS_2026-08.md)**
  §"Test Coverage".

---

## Session Log

Full session log has moved to **[TODOS.md](TODOS.md)**.

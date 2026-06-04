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
Key top-level packages: `src/auth`, `src/client`, `src/models`, `src/portfolio`, `src/paper`, `src/mf`, `src/dhan`, `src/nuvama`, `src/intraday`, `src/instruments`, `src/market_calendar`, `src/notifications`, `src/utils`, `src/backtest`, `src/risk`, `src/gamma`, `src/strategy`, `src/council`, `src/db.py`
`src/risk/` — portfolio-level delta risk controls. `PortfolioDelta` frozen dataclass (`src/risk/models.py`): `options_delta_lots`, `niftybees_delta_lots`, `total_delta_lots`, `warning_breached`, `cap_breached`, `as_of`. `PortfolioDeltaTracker` (`src/risk/delta_tracker.py`): `aggregate_delta(paper_positions, nifty_spot, lot_size) → PortfolioDelta`; options-only thresholds warning=0.75/cap=1.0 lots, combined thresholds warning=1.5/cap=2.0 lots; parameterised via constructor. CE/futures = `net_qty/lot_size`; PE = `-net_qty/lot_size`; NiftyBees = `qty×avg_cost/(spot×lot_size)`. `check_entry_allowed` (`src/risk/entry_gate.py`): protective entries always allowed; cap → block; warning → allow with message. 20 unit tests in `tests/unit/risk/test_delta_tracker.py`.
`src/gamma/` — scaffolding, data models (`GammaChainSnapshot` and `GammaWatchlistEntry` frozen dataclasses), and persistence (`GammaStore` SQLite operations) for Near-Expiry Gamma Buy strategy.
`src/backtest/ivr.py` — `compute_ivr(vix_today, vix_series)`: IVR formula over trailing 252-day VIX window; returns `float | None`; clamps to `[0.0, 1.0]`; flat-window safe (returns 0.5). 11 unit tests in `tests/unit/backtest/test_ivr.py`.
`src/backtest/vix_ingest.py` — India VIX ingestion pipeline. Supports NSE CSV (legacy) and Upstox API.canonical Parquet storage: `data/historical/ohlc/india_vix/`. Resumable — identifies gaps and fetches missing days. 7 unit tests in `tests/unit/backtest/test_vix_ingest.py`.
`src/backtest/chain_writer.py` — `ChainWriter` class for EOD and intraday chain snapshot Parquet writes. 8 unit tests in `tests/unit/backtest/test_chain_writer.py`.
`src/backtest/chain_reader.py` — `ChainReader` class for DuckDB-based option chain EOD and intraday query scan utilities. 8 unit tests in `tests/unit/backtest/test_chain_reader.py`.

`src/models/options.py` — `OptionLeg`, `OptionChainStrike`, `OptionChain` (all `frozen=True` Pydantic). Source-agnostic field names; Upstox parser in `src/client/upstox_market.py` (`parse_upstox_option_chain`). Dhan parser not implemented (chain-data story complete; Dhan approach not pursued).
`src/paper/` — paper trading module. `PaperTrade` model (frozen Pydantic, `paper_` prefix enforced, includes `ivr_at_entry: float | None`), `PaperPosition` + `PaperNavSnapshot` + `PaperLegSnapshot` (frozen dataclasses), `PaperStore` (`paper_trades` + `paper_nav_snapshots` + `paper_leg_snapshots` + `pending_approvals` + `council_outputs` + `daemon_heartbeat` + `paper_exit_events` tables in shared SQLite), `PaperTracker` (compute_pnl + record_daily_snapshot). `PaperStore` API: `record_leg_snapshot` (upsert; enforces `total_pnl == unrealized_pnl + realized_pnl`), `get_leg_snapshot`, `get_prev_leg_snapshot`, `delete_trade` (no-op if missing), `create_exit_event` (upsert by trade_id + exit_signal), `get_open_exit_events` (filter by strategy/leg/status). `paper_exit_events` schema captures: strategy_name, leg_name, trade_id, exit_signal (`ExitSignal` enum), severity (INFO/WARN/ACTION), ltp/mid/bid/ask/delta/dte, entry_price, threshold_value, dual-signal audit fields (`delta_stop_would_fire`, `premium_stop_would_fire`, `actual_rule_used`), status (OPEN/ACKNOWLEDGED/ACTED/DISMISSED). `PaperExitEvent` frozen Pydantic model in `src/paper/models.py`. See `src/paper/CLAUDE.md` for full invariants.
`src/strategy/` — paper-backbone strategy layer. `PaperStrategy` protocol (`protocol.py`) + `SignalEvent` + `ApprovedAction` + `LegSpec` models. `StrategyMonitor` (`monitor.py`): registry + tick loop + signal routing + heartbeat. `PaperExecutor` (`executor.py`): action dispatch + `PaperFillSimulator` (VIX-regime slippage model). Concrete strategies: `CSPNiftyV1` (`csp_nifty_v1.py`), `IronCondorV1` (`ic_nifty_v1.py`), `NiftyTrackComparisonV1` (`nifty_track_comparison_v1.py`). All implement `PaperStrategy` protocol. `ExitSignalEngine` (`exit_signals.py`): static rule engine for CSP, CC, PP, and Collar overlay rule sets; returns `ExitSignalResult` with severity (INFO/WARN/ACTION) and dual-signal audit fields (`delta_stop_would_fire`, `premium_stop_would_fire`, `actual_rule_used`); thresholds: CSP delta stop |δ| ≥ 0.45, profit target 50% decay, time stop 21 days; CC loss stop 2.5×, delta stop +0.55; PP CRASH_MONETIZE when δ ≤ −0.80 or value ≥ 5× debit; Collar 75% decay on short call. Overlay strategies: `CCOverlayV1` (`cc_overlay_v1.py`), `PPOverlayV1` (`pp_overlay_v1.py`), `CollarOverlayV1` (`collar_overlay_v1.py`) — all implement `PaperStrategy`; emit exit/warning signals for standalone CC, PP, and Collar option legs respectively. All ACTION-severity `SignalEvent` payloads across all strategies include `"valid_actions": [...]` (the list of `ApprovedAction.action_type` strings accepted by that strategy's `apply_action`), used by `TelegramGateway.send_approval_request` to build the approval keyboard without a council call. `OverlayCloser` (`overlay_closer.py`): atomic multi-leg close orchestrator with rollback on failure; handles CC single-leg, PP single-leg, and Collar (call-first sequencing) close actions via `PaperFillSimulator`. `CSPNiftyV1` extended with R5 re-entry eligibility check (`_check_r5_reentry`) on `PROFIT_TARGET` action: gates on DTE ≥ 14, IVR threshold, no open position already exists; writes `R5_REENTRY_ELIGIBLE` or `R5_REENTRY_BLOCKED` event to `paper_exit_events`.
`src/council/` — AI council infrastructure. `RapidCouncil` (`rapid.py`): parallel Stage-1 fan-out (5 heterogeneous personas) + chairman synthesis + timeout handling.
Scripts (under `scripts/` structured into functional axis):
   - `pipeline/`: `upstox_chain_snapshot.py` (EOD option chain → Parquet), `upstox_chain_intraday.py` (5-min intraday chain → Parquet), `gamma_daily_watch.py` (Greeks monitoring), `bhavcopy_bootstrap.py` (resumable bulk NSE bhavcopy download 2016–present).
   - `lookup/`: `find_strike_by_delta.py` (live chain → filter by delta range; enforces `_apply_liquidity_gate()` — rejects strikes with insufficient OI/volume; exits with error if no candidate passes), `find_overlay_strikes.py` (overlay-specific strike finder), `instrument_lookup.py` (BOD JSON key resolver).
   - `record/`: `record_paper_trade.py` (entry/close for paper strategy; enforces liquidity gate + R3 IVR hard block on SELL; `--force-entry` flag overrides low-IVR block with logged warning), `record_trade.py` (live trade recording).
   - `strategies/`: strategy-specific scripts (e.g. `three_track/paper_3track_snapshot.py` EOD cron — includes Tier 1 exit signal detection via `ExitSignalEngine` for all leg roles (CSP/CC/PP/Collar), deduplication against existing OPEN events, and `_check_base_expiry()` for DTE ≤ 5 base-position expiry detection with `get_next_contract()` roll alert via Telegram; `three_track/paper_3track_overlay_roll.py` DTE ≤ 5 rolls, `csp/paper_csp_roll.py` time/delta stop exit).
   - `portfolio/`: live portfolio P&L crons/snapshots (e.g. `daily_snapshot.py` EOD portfolio snapshot cron, `morning_nav.py` pre-market NAV fetch, `paper_snapshot.py`, `roll_leg.py`).
   - `intraday/`: intraday monitoring crons (e.g. `intraday_tracker.py` combined Dhan+Nuvama orchestrator, `nuvama_intraday_tracker.py`, `dhan_intraday_tracker.py`).
   - `seed/`: one-time DB seed scripts (`seed_mf_holdings.py`, `seed_nuvama_positions.py`, `seed_portfolio.py`, `seed_trades.py`).
   - `council/`: council workflow tooling (`ask_council.py`, templates).
   - `daemon/`: monitor daemon scripts (`monitor_daemon.py` main loop, `start_monitor.py` launcher, `stop_monitor.py` shutdown, `pre_market_brief.py` pre-market summary cron, `eod_summary.py` EOD P&L summary cron).
   - `dev/`: diagnostics/migrations (`send_test_telegram.py`, `validate_strategy_spec.py`, `probe_nuvama_schema.py`, `migrate_strike_to_text.py`, `test_api_version.py`, `paper_track_snapshot.py`).
`src/notifications/telegram_gateway.py` — `TelegramGateway`: council-free approval request dispatch + inbound callback polling + auth guard (chat-ID allowlist) + timeout scan for stale pending approvals. `send_approval_request(event, context_str)` builds inline keyboard from `event.payload["valid_actions"]` (list of action_type strings embedded by each strategy); returns `None` + logs ERROR if `valid_actions` missing. No `CouncilOutput` or LLM call in the approval path. Non-fatal contract: errors logged and suppressed, never raise to caller.
`src/instruments/lookup.py` — `get_expiry_candidates(underlying, today, preference)`: enumerates NIFTY expiries from BOD JSON into monthly (DTE 15–45) / quarterly (46–200) / yearly (201–420) buckets; default preference `["monthly","quarterly","yearly"]`; custom order accepted for hedge use. `get_next_contract(instrument_key)`: given a futures or options instrument key, resolves the next-maturity contract from the BOD JSON by expiry order; returns `dict | None`; used by base-expiry roll alert.

`src/config.py` — `Settings(BaseSettings)` singleton (pydantic-settings). Declares every env var used across `src/` and `scripts/`: Upstox tokens (`upstox_env`, `upstox_analytics_token`, `upstox_access_token`, `upstox_sandbox_token`, `upstox_debug`), Telegram (`telegram_bot_token`, `telegram_chat_id`), Nuvama (`nuvama_settings_file`), Dhan (`dhan_client_id`, `dhan_access_token`), data paths (`vix_data_dir`). Loads from `.env` + environment. Import the `settings` singleton — never call `os.getenv()` directly. 3 unit tests in `tests/unit/test_config.py`.
`src/utils/logging.py` — `setup_logging(*, json: bool | None = None, level: str | None = None)`: configures structlog with shared processors (contextvars merge, log level, logger name, ISO timestamp). JSON renderer in prod (`upstox_env == "prod"`); `ConsoleRenderer` otherwise. Wired at entry point of every script in `scripts/`. 2 unit tests in `tests/unit/utils/test_logging.py`.
`scripts/healthcheck.py` — dead man's switch for EOD cron validation. Six checks in order: trading-day guard (silent exit on holidays), DB accessibility, `daily_snapshots` recency, `paper_nav_snapshots` recency, VIX data recency (warn if > 2 days stale), disk space (warn if < 500 MB free). Silent on full pass (exit 0); fires Telegram alert and exits 1 on any failure or warning. Intended cron: `30 16 * * 1-5`. 3 unit tests in `tests/unit/test_healthcheck.py`.

**Developer Tooling (repo root):**
`pyproject.toml` — project metadata, all dev dependencies (`pytest`, `ruff`, `mypy`, `pre-commit`, `vulture`, `bandit`, `commitizen`), `[tool.pytest.ini_options]` (testpaths, asyncio_mode, markers, `addopts = "-n auto"` for parallel), `[tool.ruff]` lint/format rules, `[tool.mypy]` with phased strict rollout (strict on `src/client.*` + `src/paper.*`; permissive elsewhere; third-party stubs silenced), `[tool.coverage.run]` (source=src) + `[tool.coverage.report]` (fail_under=80, excludes pragma/TYPE_CHECKING/NotImplementedError/@abstractmethod). Install: `pip install -e ".[dev]"`.
`Makefile` — targets: `test` (parallel, `-n auto`), `test-serial` (no randomly, for debugging), `coverage`, `lint`, `fmt`, `security`, `dupes`, `dead-code`, `ci` (lint → test → coverage → security, `--randomly-seed=last`), `index`. `make ci` is the single entry point for all dev and CI checks.
`.pre-commit-config.yaml` — three hooks: `ruff` (lint + fix), `ruff-format`, `mypy` (scoped to `src/client/` + `src/paper/` only), `detect-secrets`. Install: `bash scripts/dev/install_hooks.sh`.
`scripts/dev/install_hooks.sh` — installs pre-commit + post-commit hook in one command.
`scripts/dev/post_commit_hook.sh` — post-commit: echoes re-index reminder when `src/` or `scripts/` changed.
`docs/plan/dev-foundation/dx-foundation/mypy_baseline.md` — mypy error counts per module at DX-3 baseline. Use to track type-safety progress over time.
`.github/workflows/ci.yml` — GitHub Actions CI workflow. Triggers on push/PR to `main`. Matrix: Python 3.10 + 3.11. Steps: checkout → setup-python (pip cache) → `pip install -e ".[dev]"` → `make ci` (UPSTOX_ENV=test, forces MockBrokerClient) → coverage XML + `irongut/CodeCoverageSummary` summary action → `actions/upload-artifact` (htmlcov, 7-day retention, Python 3.10 only). No secrets required — `UPSTOX_ENV=test` bypasses all live API calls. `@pytest.mark.sandbox` tests excluded by default. Coverage thresholds: warn at 70%, fail at 80%.

**Research tooling (docs/):**
`docs/strategies/regime_probe.pine` — Pine Script v6 sensor script (not a trading strategy). Outputs a structured 22-row `table.new()` on the last bar covering: regime label, regime code (−2→3), options recommendation, full ADX/DI block, ATR with 252-bar percentile rank, BB width with percentile rank, RSI, 20-day annualized HV, India VIX via `request.security()`, and bar date. Designed for MCP extraction via `data_get_pine_tables`. Study identified by name (stable across sessions). Key-value fallback via `label.new()` pipe-delimited text. Operational tool: load on NIFTY 1D and 1W at each paper trade entry (BACKTEST_PLAN.md Phase 0 gate criteria C/D).
`docs/archive/tv_mcp_testing_framework.md` — 7-phase capability probe for `tradesdontlie/tradingview-mcp` (CDP-based, connects to TradingView Desktop). Validated 2026-05-23: Phase 3 confirmed table readability end-to-end; Phase 3C confirmed timeframe switching updates correctly (no stale data). Archived — findings fully captured in `DECISIONS.md → TradingView MCP Regime Probe`.

### What Does NOT Exist Yet

- `src/nuvama/CLAUDE.md` — module context file not yet written
- `src/execution/`, `src/streaming/` — empty (planned per BACKTEST_PLAN.md Phase 1–2)
- `src/gamma/` script logic (`gamma_daily_watch.py`) — planned for Phase A next (scaffolding and store implemented in Task B1)
- PT-S2 Signal Pipeline (`src/strategy/signal_pipeline.py`) — blocked on signals story + OpenRouter API key

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

- **Total: ~1559 tests** (includes CH-9b hypothesis property tests: 19 @given tests across `test_ivr_hypothesis.py`, `test_delta_hypothesis.py`, `test_pnl_hypothesis.py`) (paper module: 92 tests across Phases A–D all passing; 6 new expiry-candidate tests in `tests/unit/instruments/test_expiry_candidates.py`; strategy module exit-signals additions: `test_exit_signals.py` 20 tests, `test_cc_overlay_v1.py` 11, `test_pp_overlay_v1.py` 10, `test_collar_overlay_v1.py` 11, `test_overlay_closer.py` 10, `test_csp_nifty_v1.py` 29; pre-existing failures in `test_upstox_live.py` + `test_mock_client.py` — `pytest-asyncio` not installed in sandbox, not code regressions)
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

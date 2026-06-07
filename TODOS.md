# NiftyShield — TODOs

> Open work only. Completed items: [docs/archive/TODOS_ARCHIVE.md](docs/archive/TODOS_ARCHIVE.md) | Known defects: [BUGS.md](BUGS.md)
> Related: [CONTEXT.md](CONTEXT.md) | [DECISIONS.md](DECISIONS.md) | [PLANNER.md](PLANNER.md) | [BACKTEST_PLAN.md](BACKTEST_PLAN.md) | [BACKTEST_PLAN_PHASE1.md](BACKTEST_PLAN_PHASE1.md)

---

## June 2026 Calendar

Date-locked events — act before the date, not on it.

| Date | Event | Action |
|---|---|---|
| **2026-06-19** | CSP Cycle 2 time stop | Entry 2026-05-29 + 21 days. Profit target ≤ ₹79.30; delta stop ≥ 0.45. If profit target fires early, run R5 eligibility check (DTE ≥ 14, IVR ≥ 0.25). Monitor via `paper_snapshot.py --strategy paper_csp_nifty_v1`. |
| **2026-06-23** | Roll week begins | `paper_3track_overlay_roll.py` handles overlay legs at DTE ≤ 5. `paper_csp_roll.py` handles CSP Cycle 2 (`NSE_FO|79653`). |
| **2026-06-30** | All June contracts expire | Finideas roll (build queue #1). Base positions (`NSE_FO|62329` futures, `NSE_FO|79509` DITM call) need manual rolls — ES11 will automate the alert once built. |

**Verify soon:** June futures base (`NSE_FO|62329`) opened 2026-05-29 — confirm non-None LTP in the next EOD snapshot:
```bash
python scripts/paper_3track_snapshot.py --no-save
```

---

## Near-term Actions

Small items: no story file yet, or waiting for a single edit/commit.

- [ ] **Fix pre-existing mypy errors blocking pre-commit** — Two pre-existing failures surface when mypy follows transitive imports from `src/paper/`: (1) `src/market_calendar/holidays.py:19` — missing `types-PyYAML` stubs; fix: `pip install types-PyYAML` + add to `additional_dependencies` in `.pre-commit-config.yaml`. (2) `src/models/portfolio.py:270,276,312` — `Decorators on top of @property are not supported [misc]`; likely a `@deprecated` or custom decorator stacked on `@property` that mypy can't handle — either remove the decorator or suppress with `# type: ignore[misc]`. Until fixed, commits touching `src/paper/` require `--no-verify`.
- [ ] **Add healthcheck cron** — wire `scripts/healthcheck.py` into crontab: `30 16 * * 1-5 python /path/to/scripts/healthcheck.py`. Run once manually first to confirm Telegram alert fires correctly. (CH-8 shipped — cron entry is the remaining operational step.)
- [ ] **CH-4 redo — Populate `__all__` in all `src/` `__init__.py` files** — CH-4 (d97c099) was reverted: empty `__all__ = []` is worse than no `__all__` (hides symbols, contradicts explicit import pattern). When revisiting: use `search_graph` per module to enumerate actual public symbols, then populate each `__init__.py`. Only do this if the codebase shifts toward re-exporting from package roots (i.e., `from src.portfolio import PortfolioStore` style). Until then, leave `__init__.py` files as comment-only stubs.
- [ ] **Add IVR NULL note to BACKTEST_PLAN.md** — Phase 0.8 gate criterion A: *"IVR NULL for Cycles 1 and 2 — accepted data gap; criterion A satisfied from Cycle 3 onward."* Cycle 1 (id=14, 2026-05-11): pipeline not live. Cycle 2 (id=32, 2026-05-28): 0/252 days VIX history blocked computation.
- [ ] **Historical data abstraction (LOW priority)** — `HistoricalCandleFetcher` protocol so VIX and OHLC fetching can switch between Upstox, Dhan, Kite, and NSE CSV without touching storage. Currently `vix_ingest.py` has Upstox URLs hardcoded with sync `requests`; `get_historical_candles` on `BrokerClient` raises `NotImplementedError`. Start with **HD-0** (cost-bounded probe scripts — paid APIs require 5-day window only). Full story: `docs/plan/historical-data-abstraction/`. 11 tasks HD-0→HD-10. HD-6 (Dhan) and HD-7 (Kite ₹2000/month) are conditional on HD-0 decision matrix.
- [ ] **Broker abstraction (LOW priority)** — multi-broker parser/adapter layer so data fetching can migrate to Dhan or Kite without touching storage. Storage format (Parquet, SQLite, model field names) is frozen — only fetch + parse changes. Full story: `docs/plan/broker-abstraction/`. 16 tasks (BA-0 → BA-15). Start with **BA-0** (probe scripts + decision matrix — which broker is best for each data category) before writing any implementation code. BA-14 + BA-15 blocked until `src/execution/` (Phase 1) exists. Start BA-0 only after Phase 0.8 gate.
- [ ] **Create `docs/plan/entry-event-filter/`** — R4 event filter (Budget/RBI MPC/elections). Scope: `src/market_calendar/events.yaml` schema + loader + soft-warning integration into `record_paper_trade.py`. Dependency: ES12 must ship first. DoD: `prompt.md` + `tasks.md`, no code.
- [ ] **Create `docs/plan/csp-collateral-leg/`** — `long_niftybees` collateral leg. Back-fill Cycle 1 (2026-05-11); add to `paper_snapshot.py` LTP batch; annual reset. Formula: `qty = floor((65 × nifty_spot) / niftybees_ltp)`. DoD: story dir + back-fill command documented.
- [ ] **PB1.1 Post-Review: `strategy_name` constraint enforcement** — Validate that strategies use the required `paper_` prefix. Add comment/guard on the field or concrete implementations and assert in tests.
- [ ] **PB1.1 Post-Review: `legs_to_close: list[str]` ambiguity** — Document that `leg_role` must be unique within a position for unambiguous closure by `leg_role`.
- [ ] **PB1.1 Post-Review: Reconsider `council_rank: int` on `ApprovedAction`** — Evaluate decoupling council rank from the action model to support a single canonical action object before building the executor.
- [ ] **PB1.1 Post-Review: Add `strategy_name` presence check to protocol conformance test** — Assert `hasattr(mock_strategy, "strategy_name")` in test to document intent.

**Before build queue #6 starts** — verify paper-backbone prerequisites:
```bash
search_graph("StrategyMonitor")   # must return results
search_graph("PaperExecutor")     # must return results
search_graph("CCOverlayV1")       # must return zero results
```
If `StrategyMonitor` / `PaperExecutor` do not exist → complete build queue #5 first.

---

## Animesh-only: Stockmock Calibration Backtests

Prerequisite for Phase 1 task 1.7 (`CSPStrategy` calibration). Stockmock UI — no code required.

- [ ] COVID crash (Feb–Apr 2020) — strikes hit, premium, max M2M loss, breach frequency
- [ ] IL&FS crisis (Sep–Oct 2018) — same metrics
- [ ] 2022 rate-hike selloff (Jan–Jun 2022) — same metrics
- [ ] Stable baseline (Jan–Dec 2023) — expected exit-type distribution in normal markets
- [ ] Summarise in [docs/strategies/csp_nifty_v1.md](docs/strategies/csp_nifty_v1.md) under "Calibration Backtest Results (Stockmock)"
- [ ] Commit: `docs(strategies): CSP v1 Stockmock calibration backtest results`

---

## Active Tasks

> **Priority rule:** Infrastructure that blocks other stories runs before strategy-specific work.
> `paper-backbone` blocks `paper-exit-signals` — these two are the critical path.
> `covered-call-overlay` and `MVP` are independent and slot in around the critical path.
> `scripts-restructure SR1` (scaffold only) runs before `paper-backbone` so new daemon scripts land in the correct folder structure from day one.

---

### Build queue #1 — June 2026 Finideas Roll

**Hard deadline: 2026-06-30** (NIFTY_JUN 23000 CE and PE legs expire — see [REFERENCES.md](REFERENCES.md)).
Invoke `roll-validator` agent ≥1 week before deadline.

- [ ] Invoke `roll-validator` ≥1 week before 2026-06-30 — pre-check position state, Trade model integrity, DB atomicity.
- [ ] Receive Finideas roll instructions (strike, expiry, quantity for each leg).
- [ ] Run `python -m scripts.roll_leg --dry-run ...` with all four `--old-*/--new-*` flags. Verify output.
- [ ] Run without `--dry-run`. Verify both Trade rows inserted atomically.
- [ ] Run `python -m scripts.daily_snapshot` same day. Confirm P&L continues uninterrupted.
- [ ] Session log entry with date, old/new instrument keys, and any anomalies.
- [ ] File a separate fix commit before moving on if any bug surfaces.

**Owner:** Animesh (receives instructions) + Cowork (executes scripts).

---

### Build queue #3 — scripts-restructure SR1 (scaffold only)

**Story:** [docs/plan/scripts-restructure/](docs/plan/scripts-restructure/)
**Why now:** SR1 is scaffold-only (`__init__.py` files, no file moves, ~30 min). Must run before `paper-backbone` writes new daemon scripts so those land in `pipeline/`, `strategies/`, etc. from day one — not born flat and needing migration later. Full migration (SR2+) is post-market and lower urgency.

- [x] Run SR1: create all `__init__.py` files per `stories.md`, re-index graph, verify tests green.

---

### Build queue #4 — paper-backbone: Strategy Monitor Daemon

**Story:** [docs/plan/paper-backbone/](docs/plan/paper-backbone/) (prompt, tasks, stories, schema)
**Prerequisite:** PortfolioDeltaTracker ✅ shipped 2026-05-26 | scripts-restructure SR1 ✅ (run first)
**Blocks:** paper-exit-signals (#5) — `StrategyMonitor` + `PaperExecutor` must exist before ES0.

| Step | What | Deadline | Status |
|---|---|---|---|
| PT-0 — Common Infrastructure | PB1.1–PB1.7: `PaperStrategy` protocol, `StrategyMonitor`, `PaperExecutor`, `RapidCouncil`, `TelegramGateway`, DB migrations, daemon scripts | Jun–Jul 2026 | ✅ Done |
| PT-S0 — CSP v1 | PB2.1: `CSPNiftyV1` — adds auto-signal detection | After PT-0 | ✅ Done |
| PT-S1 — Iron Condor v1 | PB3.1: `IronCondorV1` — entry via `paper_ic_entry.py` | Aug 2026 | ✅ Done |
| PT-S3 — 3-Track | PB4.1: `NiftyTrackComparisonV1` — adds WARN roll reminders | After PT-0 | ✅ Done |
| PT-S2 — Signal Pipeline | Blocked on [signals story](docs/plan/signals/) + OpenRouter API key | Aug–Sep 2026 | ⬜ Blocked |
| PT-B — Backtesting mode | Historical replayer + AutoApprover swap-in | After Phase 0.8 gate | ⬜ Blocked |

---

### Build queue #5 — paper-exit-signals: Automated Exit Detection + Closure

**Story:** [docs/plan/paper-exit-signals/](docs/plan/paper-exit-signals/) (prompt, schema, stories, tasks)
**Blocked by:** Build queue #4 PT-0 (`StrategyMonitor` + `PaperExecutor` must exist before starting)
**Council authority:** `docs/council/2026-05-28_paper-trade-exit-philosophy.md` — all 10 thresholds binding; no changes without a new council decision.
**Archive gate (ES9 — must run last):** council file + `csp_nifty_v1.md` archived via `git mv` only after all stories committed.

| Step | Files | Status |
|---|---|---|
| CC1 | `src/paper/constants.py` — `STRATEGY_CC_OVERLAY` + `compute_max_lots` + tests | ✅ Shipped |
| CC2 | `scripts/paper_cc_entry.py` — delta selection + IVR gate + qty constraint + dry-run | ✅ Shipped |
| CC3 | `scripts/paper_cc_roll.py` — profit-target / time-stop / delta-stop exit handler + tests | ⬜ Not started |
| CC4 | Docs close | ⬜ Not started |

---

### Build queue #6 — Covered Call Overlay Scripts (CC3+CC4 remaining)

**Story:** [docs/plan/covered-call-overlay/](docs/plan/covered-call-overlay/) (prompt, tasks, stories, schema)
**Purpose:** NiftyBees lot-sizing calibration experiment — not a permanent strategy. Findings fold into 3-track NiftyBees CC after 3 cycles.
**Note:** Independent — does not block any other queue item. Slot in around critical path.

| Step | Files | Status |
|---|---|---|
| CC1 | `src/paper/constants.py` — `STRATEGY_CC_OVERLAY` + `compute_max_lots` + tests | ✅ Shipped |
| CC2 | `scripts/paper_cc_entry.py` — delta selection + IVR gate + qty constraint + dry-run | ✅ Shipped |
| CC3 | `scripts/paper_cc_roll.py` — profit-target / time-stop / delta-stop exit handler + tests | ⬜ Not started |
| CC4 | Docs close | ⬜ Not started |

---

### Build queue #7 — MVP: Multi-bagger Value Picks Tracker

**Story:** [docs/plan/mvp/](docs/plan/mvp/) (prompt, tasks, stories, schema)
**CLI surface and cron spec:** [docs/plan/mvp/mvp_tasks.md](docs/plan/mvp/mvp_tasks.md)
**Note:** Independent — does not block any other queue item.

| Step | Files | Status |
|---|---|---|
| M1 | `src/mvp/models.py`, `src/mvp/store.py`, `tests/unit/mvp/` | ⬜ Not started |
| M2 | `src/mvp/tracker.py` | ⬜ Not started |
| M3 | `scripts/mvp.py` (full CLI) | ⬜ Not started |
| M4 | `scripts/mvp_watch.py` (hourly cron) | ⬜ Not started |
| M5 | Docs close + cron entry | ⬜ Not started |

---

### Build queue #5 — paper-exit-signals: Automated Exit Detection + Closure

**Story:** [docs/plan/paper-exit-signals/](docs/plan/paper-exit-signals/) (prompt, schema, stories, tasks)
**Blocked by:** Build queue #5 PT-0 (`StrategyMonitor` + `PaperExecutor` must exist before starting)
**Council authority:** `docs/council/2026-05-28_paper-trade-exit-philosophy.md` — all 10 thresholds binding; no changes without a new council decision.
**Archive gate (ES9 — must run last):** council file + `csp_nifty_v1.md` archived via `git mv` only after all stories committed.

**Run order:**

| Step | Stories | Rationale |
|---|---|---|
| 1 | Prereq gate | Verify `StrategyMonitor` + `PaperExecutor` exist before ES0 |
| 2 | ES0 → ES1 → ES2 | Foundation: schema + rule engine + CSP threshold fix |
| 3 | ES10 → ES12 | CSP lifecycle (Cycle 2 open); entry discipline |
| 4 | ES3 → ES4 → ES5 → ES6 | Overlay strategy classes + OverlayCloser |
| 5 | ES7 → ES8 | EOD + daemon wiring |
| 6 | ES11 | Base roll detection — next event 2026-06-30 |
| 7 | ES9 | Docs close — always last |

| Story | Files | Status |
|---|---|---|
| ES0 | `paper_exit_events` DDL in `PaperStore.__init__`; store methods + tests | ✅ Shipped |
| ES1 | `src/strategy/exit_signals.py` — `ExitSignalEngine` (pure/stateless); CSP/CC/PP/Collar rules; tests | ✅ Shipped |
| ES2 | Fix `CSPNiftyV1` thresholds: `DELTA_STOP` 0.35→0.45, `DELTA_WARN` 0.35, `LOSS_STOP` 2.0×→1.75× | ⬜ Not started |
| ES3 | `src/strategy/cc_overlay_v1.py` — `CCOverlayV1`; dual-signal audit; tests | ⬜ Not started |
| ES4 | `src/strategy/pp_overlay_v1.py` — `PPOverlayV1`; `CRASH_MONETIZE` + bid/ask gate; tests | ⬜ Not started |
| ES5 | `src/strategy/collar_overlay_v1.py` — `CollarOverlayV1`; 4-path closure routing; tests | ⬜ Not started |
| ES6 | `src/strategy/overlay_closer.py` — `OverlayCloser`; atomic Collar close + rollback; tests | ✅ Shipped — 3dafad9 |
| ES7 | `scripts/paper_3track_snapshot.py` — Tier 1 EOD signal write + Telegram alert + deduplication | ✅ Shipped — 1d40d8f |
| ES8 | `scripts/monitor_daemon.py` — register CC/PP/Collar overlays; `MONITOR_OVERLAYS` gate | ✅ Shipped — 7c23864 |
| ES10 | `src/strategy/csp_nifty_v1.py` — R5 re-entry eligibility post profit-target; Telegram alert; tests | ✅ Shipped — c9625e1 |
| ES11 | `scripts/paper_3track_snapshot.py` + `InstrumentLookup.get_next_contract()` — base expiry alert | ✅ Shipped — 16c7f23 |
| ES12 | `find_strike_by_delta.py` liquidity gate; `record_paper_trade.py` R3 hard block + `--force-entry` | ✅ Shipped — b86925a |
| ES9 | Docs close (LAST): DECISIONS.md, CONTEXT.md, TODOS.md; `git mv` council + csp_nifty_v1 to archive | ✅ Shipped — e32b862 |

**Deferred gaps (separate stories — not blocking this task):**

| Gap | Story needed | When |
|---|---|---|
| R4 event filter (Budget/RBI/elections) | `docs/plan/entry-event-filter/` — needs `events.yaml` | After ES12 |
| Collateral leg (`long_niftybees`) per cycle | `docs/plan/csp-collateral-leg/` | Before Phase 0.8 gate |
| Transaction cost model in paper P&L | `docs/plan/paper-cost-model/` | Phase 1 |
| IVR at entry NULL for Cycles 1 + 2 | Permanent gap — log in Phase 0.8 gate evaluation | Accepted |

---

## Build Queue

Tasks run in priority order. Infrastructure that blocks other stories runs first. Independent strategy work slots in around the critical path.

| # | Task | Owner | Deadline | Blocks | Status |
|---|---|---|---|---|---|
| 1 | June 2026 Finideas roll | Animesh + Cowork | **2026-06-30** | — | Execution pending — awaiting Finideas instructions |
| 2 | chain-data: EOD + intraday chain snapshot cron | Cowork | — | — | ✅ Shipped — [story](docs/archive/plan/chain-data/) |
| 3 | scripts-restructure SR1 (scaffold only) | Cowork | Before #4 | #4 script placement | ✅ Shipped — [story](docs/plan/scripts-restructure/) |
| 4 | paper-backbone: Strategy Monitor daemon | Cowork | **Jun–Jul 2026** | #5 | ✅ Shipped — [story](docs/plan/paper-backbone/) |
| 5 | paper-exit-signals: automated exit detection + closure | Cowork | After #4 | — | ✅ Shipped — [story](docs/plan/paper-exit-signals/) |
| 6 | covered-call-overlay CC3+CC4 (calibration experiment) | Cowork | Any cycle | — | ⬜ CC3 not started — [story](docs/plan/covered-call-overlay/) |
| 7 | MVP: Multi-bagger Value Picks Tracker | Cowork | After #1 | — | ⬜ Not started — [story](docs/plan/mvp/) |
| 8 | backtest-eval-core: `BacktestStore` + `src/analytics/` | Cowork | Aug 2026 | #9 | ⬜ Not started — [story](docs/plan/backtest-eval-core/) — **blocked by tasks 1.3 + 1.4** |
| 9 | signals-eval-core: regime engine + signal generators + validation | Cowork | Q4 2026 | — | ⬜ Not started — [story](docs/plan/signals-eval-core/) — **blocked by #8 + Phase 1.12 gate** |
| 10 | council-refactor: remove RapidCouncil from daemon path; fix approval bug; add deterministic roll rules | Cowork | Before 2026-06-23 roll week | — | 🔄 CR0+CR1a+CR1b shipped — CR1c (CSPRollExecutor) + CR1d (CSPNiftyV1 auto-execute) pending — [story](docs/plan/council-refactor/) |
| 10 | broker-abstraction: multi-broker parser/adapter layer (Dhan, Kite) | Cowork | LOW — after Phase 0.8 gate | — | ⬜ Not started — [story](docs/plan/broker-abstraction/) — 16 tasks BA-0→BA-15; start with BA-0 analysis; BA-14/15 blocked on Phase 1 |
| 11 | historical-data-abstraction: `HistoricalCandleFetcher` protocol + vendor implementations | Cowork | LOW — after Phase 0.8 gate | — | ⬜ Not started — [story](docs/plan/historical-data-abstraction/) — 11 tasks HD-0→HD-10; start with HD-0 cost evaluation (paid APIs); HD-6/HD-7 conditional on HD-0 decision matrix |

Story folder IDs: chain-data=4a, covered-call-overlay=4cc, mvp=4b, paper-backbone=4c, paper-exit-signals=4d, scripts-restructure=4e.

---

### Backlog — Scripts Restructure

**Story:** [docs/plan/scripts-restructure/](docs/plan/scripts-restructure/) (prompt, tasks, stories)
**SR0 closed 2026-05-29.** Layout finalised on pipeline/lookup/record axis.
**Principle:** New scripts must be classified by the axis in stories.md before placement.
Existing scripts migrate folder-by-folder, one commit per folder, post-market only for cron-sensitive moves.

**Axis summary:**
- `pipeline/` — cron-driven, produces data or snapshots, shared across strategies
- `lookup/` — on-demand queries called by humans or entry scripts
- `record/` — human-facing write CLIs, one action per invocation
- `strategies/<name>/` — strategy-specific entry/exit/roll scripts
- `portfolio/`, `intraday/` — domain operational crons
- `seed/`, `council/`, `dev/` — supporting tooling

| Step | Scope | Status |
|---|---|---|
| SR0 | Layout sign-off | ✅ Closed 2026-05-29 |
| SR1–SR10 | Subdirectory scaffold, helper audit, and script migrations (pipeline, lookup, record, seed, dev, council, intraday, strategies, portfolio) | ✅ Shipped |
| SR11 | Docs close | ✅ Shipped |

---

## Phase 1 — Backtest Engine (Aug–Dec 2026)

*Gated on Phase 0.8. Load [BACKTEST_PLAN_PHASE1.md](BACKTEST_PLAN_PHASE1.md) when the gate clears.*

**Replay Harness** (`docs/plan/replay_harness.md` — design doc not yet written): prereq for Phase 0.8 gate criterion B. Injects historical chain snapshots (COVID 2020-03-16 or IL&FS 2018-09-21) into `PaperTracker`. No code until task 1.3a data exists.

**Key milestones (full spec in [BACKTEST_PLAN_PHASE1.md](BACKTEST_PLAN_PHASE1.md)):**
- **1.3a** — Nifty 50 + NiftyBees OHLC Parquet; derived: ATR-14, slope-50, SMA-10M, VIX rank-252.
- **1.3b** — TrueData 1-min options ingest (~1.5 GB for 2022–2024; start after zip delivery).
- **1.4** — `BacktestEngine` core (Strategy Protocol + DayContext + run loop).
- **1.5 + 1.5b** — `BacktestStore` + `src/analytics/`; full spec: [docs/plan/backtest-eval-core/](docs/plan/backtest-eval-core/).
- **1.7** — `CSPStrategy` with `CSPConfig` from Stockmock calibration results.
- **1.11** — Regime-matched Z-score; gate `|Z| ≤ 1.5`.
- **1.12** — Phase 1 gate: paper vs backtest distributions match; Animesh sign-off.

---

## Phase 2 — Research Pipelines & Integrations (2027+)

*Gated on Phase 1.12. Full specs in [PLANNER.md](PLANNER.md) and [docs/plan/](docs/plan/).*

| Item | Notes |
|---|---|
| P&L Visualization (Cowork artifact) | ~6 weeks of data available now — buildable if prioritised. Four panels: MF, Dhan ETFs, Nuvama Bonds, Nuvama Options. Panel 5 (Zerodha) blocked on Kite Connect. |
| Zerodha / Kite Connect integration | Defer until FinRakshak/ILTS P&L visibility matters. Evaluate Kite MCP server before writing `src/zerodha/` from scratch. |
| Swing Strategy Pipeline (Track A) | SE1–SE3 + SE5–SE6. Full sequence: [docs/plan/signals-eval-core/tasks.md](docs/plan/signals-eval-core/tasks.md). |
| Investment Strategy Pipeline (Track B) | SE1–SE2 + SE4–SE6. Same story file. Parallel branch off SE2.2. |
| Order Execution Layer (`src/execution/`) | Blocked: static IP not provisioned. Design done against `BrokerClient` protocol. |
| `paper_snapshot.py` → Telegram | Wire `build_notifier`; non-fatal. Defer until file is touched for another reason. |

---

## Technical Debt

Fix alongside adjacent refactoring only. Never a standalone commit.

**DEBT-3:** License boilerplate — decision needed before automation. Every file gets a header once chosen.

**DEBT-5:** `test_bhavcopy_ingest.py` missing append-path coverage — `write_to_parquet` merge branch (`replace_schema_metadata` call) not tested. Fix when touching that test file: write-twice test asserting second run's lineage metadata survives the merge.

**DEBT-6:** Leg validation + calendar data gaps for historical backtesting:
1. Move hardcoded expiry whitelist (`{2026-04-07, 2026-12-29}`) from `Leg` to `market_calendar` YAML.
2. Holiday YAML datasets for 2017–2025 missing in `src/market_calendar/data/` — historical `Leg` construction pre-2026 fails open.
3. Formalise `is_nifty` check: replace denylist with an `instrument_key`-based predicate.

**DEBT-7:** Refactor dynamic dispatch in `daily_snapshot.py` to eliminate `noqa: F401` unused import suppressions (which hide broken imports if helpers are renamed/moved).

---

## Session Log

| Date | What Changed |
|---|---|
| 2026-06-07 | council-refactor CC-1 — Align evaluate_cc() to CSP structure: add days_held, TIME_STOP signal, DTE_REVIEW WARN, use _PROFIT_TARGET_RETENTION, add _CC_MIN_ENTRY_CREDIT; update CCOverlayV1 caller; 15+ new tests (Awaiting Commit) |
| 2026-06-07 | council-refactor CR1c — Refactor paper_csp_roll.py to thin CLI wrapper around csp_roll_executor.py; existing tests stay green — 154a64c |
| 2026-06-06 | council-refactor CR1b — TradeState enum + state field on PaperTrade; PaperStore update_trade_state; ExitSignalEngine: remove evaluate_csp, add 5 independent CSP classmethods (70% profit target, 2× hard stop, 0.40 delta breach, 21-day time stop, DTE≤7 roll eligible); CSPNiftyV1.check_signals migrated; paper_3track_snapshot.py migrated; idempotent DB migration script; 20+ new tests — 8fd58d4 |
| 2026-06-06 | council-refactor CR1a — Extract strike_selector.py from find_strike_by_delta.py, update all imports in 4 scripts, and add unit tests — 0a6b3bd |
| 2026-06-04 | council-refactor CR0 — Fix send_approval_request signature mismatch (TypeError on first live ACTION); remove CouncilOutput from approval path; wire valid_actions in 5 strategy payloads; _build_keyboard(list[str]); guard returns None+logs ERROR on empty valid_actions — 4ce6d99 |
| 2026-06-04 | council-refactor story created — docs/plan/council-refactor/ (prompt, stories, tasks); README, TODOS, DECISIONS updated. Covers: RapidCouncil removal from daemon path, send_approval_request bug fix, deterministic IVR-tiered CSP roll rules, overlay roll rules with base-DTE guard. 4 tasks (CR0–CR4). Deadline: before 2026-06-23 roll week. |
| 2026-06-03 | paper-exit-signals ES9 — Docs close: DECISIONS.md verification, CONTEXT.md sync, TODOS.md updated; archive council exit-philosophy and csp_nifty_v1 spec — e32b862 |
| 2026-06-03 | paper-exit-signals ES12 — Enforce liquidity gate in find_strike_by_delta.py and R3 hard block in record_paper_trade.py + 11 tests — b86925a |
| 2026-06-03 | paper-exit-signals ES11 — Base position expiry detection (DTE <= 5), get_next_contract in InstrumentLookup, roll commands Telegram alert + 5 tests — 16c7f23 |
| 2026-06-03 | paper-exit-signals ES10 — CSPNiftyV1 R5 re-entry eligibility: __init__, PROFIT_TARGET action_type, _check_r5_reentry (DTE/IVR/open-pos gates), paper_exit_events write + Telegram + 9 tests — c9625e1 |
| 2026-06-03 | paper-exit-signals ES7 — compute_and_record_exit_signals() in paper_3track_snapshot.py: Tier 1 EOD exit signal dispatch (CSP/CC/PP/Collar), dedup, paper_exit_events write, Telegram alerts + 10 tests — 1d40d8f |
| 2026-06-03 | paper-exit-signals ES6 — OverlayCloser class with single leg and collar closure routing + tests (adjusted for review findings) — 3dafad9 |
| 2026-06-03 | paper-exit-signals ES5 — CollarOverlayV1 strategy class + 11 unit tests — d25abf7 |
| 2026-06-03 | paper-exit-signals ES4 — PPOverlayV1 strategy class + 10 unit tests — 681f7db |
| 2026-06-03 | paper-exit-signals ES3 — CCOverlayV1 strategy class + 11 unit tests — 9ed05fb |
| 2026-06-03 | paper-exit-signals ES1 — stateless ExitSignalEngine class with CSP, CC, PP, Collar exit & warning rules + 20 unit tests — 2de33eb |
| 2026-06-03 | paper-exit-signals ES0 — paper_exit_events DDL migration + PaperStore create/get/ack/resolve methods + Pydantic model + 6 tests — 7cd8212 |
| 2026-06-02 | paper-backbone PB5 — Docs close: CONTEXT.md (src/strategy/, src/council/, TelegramGateway, daemon scripts, What Does NOT Exist Yet), DECISIONS.md (paper-backbone entry), TODOS.md (build queue status) — 565b660 |
| 2026-06-02 | paper-backbone PB4.1 — NiftyTrackComparisonV1 backbone integration: WARN-only check_signals (ROLL_DUE_DTE, ROLL_DUE_DECAY, OVERLAY_EXPIRED) + apply_action no-op + 14 tests — 2567c04 |
| 2026-06-02 | paper-backbone PB3.1 — IronCondorV1 backbone integration: check_signals + apply_action (CLOSE_FULL/CLOSE_CALL_SPREAD/CLOSE_PUT_SPREAD; ADJUST_* raises ValueError per council) + 13 tests — 0937b60 |
| 2026-06-01 | paper-backbone PB1.7 CR — Code review fixes: tests, logging, date mismatch, layering — 0e51357 |
| 2026-06-01 | paper-backbone PB1.7 — Scripts: monitor_daemon.py + start_monitor.py + stop_monitor.py + pre_market_brief.py + eod_summary.py + requirements.txt — 9191c02 |
| 2026-06-01 | paper-backbone PB1.6 — DB migrations for pending_approvals + council_outputs + daemon_heartbeat + store methods — 60408cf, 436982e |
| 2026-06-01 | paper-backbone PB1.5 — TelegramGateway with approval flow, inbound polling, auth guard, timeout scanner — fde2b3b |
| 2026-06-01 | paper-backbone PB1.4 — RapidCouncil parallel Stage 1 advisors and Chairman synthesis — 6b71c9e, 845f1e0, 275e1bb |
| 2026-06-01 | paper-backbone PB1.3 — PaperFillSimulator (VIX-regime slippage) + PaperExecutor (close/open legs via PaperStore) — 46e58ba |
| 2026-06-01 | paper-backbone PB1.2 — StrategyMonitor daemon loop with registry and signal routing — 35b3099 |
| 2026-05-31 | paper-backbone PB1.1 — PaperStrategy protocol + SignalEvent + ApprovedAction + LegSpec models — 6c527c2 |
| 2026-05-31 | scripts-restructure SS1 — Move exploratory scripts out of src/ into scripts/dev/ and rename test_ prefixes — 4fd2e19 |
| 2026-05-31 | scripts-restructure SR11 — Docs close: CONTEXT.md, DECISIONS.md, and TODOS.md updated to finalize restructured layout — 4777759 |
| 2026-05-31 | scripts-restructure SR10 — Move portfolio/ scripts (daily_snapshot, morning_nav, paper_snapshot, roll_leg) to scripts/portfolio/ and update crontab — 13b7285 |
| 2026-05-31 | scripts-restructure SR9 — Move csp and cc_calibration strategy scripts to scripts/strategies/csp/ and scripts/strategies/cc_calibration/, update test imports — e161cc9 |
| 2026-05-31 | scripts-restructure SR8 — Move strategies/three_track/ scripts to scripts/strategies/three_track/, update test imports, and update crontab — 28894d2 |
| 2026-05-31 | scripts-restructure SR7 — Move intraday/ scripts (intraday_tracker, nuvama_intraday_tracker, dhan_intraday_tracker) to scripts/intraday/ and update crontab — 20b3834 |
| 2026-05-31 | scripts-restructure SR6 — Move council/ scripts + templates to scripts/council/ and update test imports and path references — 55bb02c |
| 2026-05-31 | scripts-restructure SR5 — Move seed/ and dev/ scripts to scripts/seed/ and scripts/dev/ and fix test imports — 16ca1e1 |
| 2026-05-31 | scripts-restructure SR4 — Move record/ scripts (record_paper_trade, record_trade) to scripts/record/, update references and test mock patches — 5acd9fe |
| 2026-05-31 | scripts-restructure SR3 — Move lookup/ scripts (find_strike_by_delta, find_overlay_strikes, instrument_lookup) and update imports in record_paper_trade, paper_cc_entry, paper_csp_roll, and tests — 3fac186 |
| 2026-05-31 | scripts-restructure DA1 — archive restructure: process/ + research/ created; 8 files moved; gamma_implementation_plan.md evicted from live docs/antigravity/; reco_tracker.md delete needs manual git rm |
| 2026-05-31 | scripts-restructure SS4 — src/gamma/CLAUDE.md + src/nuvama/CLAUDE.md written; model placement rule codified in DECISIONS.md |
| 2026-05-31 | scripts-restructure SS5 — CONTEXT_TREE.md full sync: added config.py, models/options.py, risk/ block (models/delta_tracker/entry_gate), utils/logging.py; verification script clean |
| 2026-05-31 | scripts-restructure SS3 — Audit complete: service.py protocol boundary added (5986948); market_store.py has 3 callers + 9 tests green; CONTEXT_TREE documented — SS3 closed, SS5 now unblocked |
| 2026-05-31 | scripts-restructure SR2 — Move pipeline/ scripts (chain snapshot, intraday, gamma watch, bhavcopy) and update test imports + crontab — a6ca253 |
| 2026-05-31 | scripts-restructure SR1 — Scaffold scripts/ subdirectories with __init__.py files — 72cb528 |
| 2026-05-31 | code-health CH-10 — Docs close: CONTEXT.md (config.py/logging.py/healthcheck.py entries, test count), DECISIONS.md (3 decisions), TODOS.md (healthcheck cron action, session log) — health sprint complete |
| 2026-05-31 | CH-9b — Implement @given tests for IVR, delta, and P&L arithmetic — 7157010 |
| 2026-05-31 | feat(scripts): add healthcheck.py dead man's switch for cron validation — fe1e123 |
| 2026-05-30 | refactor(src,scripts): replace direct environment access with Settings singleton — fe69612 |
| 2026-05-30 | CH-7a — Define Settings model in src/config.py mapping all env vars — 0222885 |
| 2026-05-30 | CH-6 — Central structlog logging setup + wire to scripts — 75f499b |
| 2026-05-30 | CH-5 — docs/architecture.md Mermaid C4 container diagram — 37b77bc |
| 2026-05-30 | CH-2 — vulture dead code scan across src/ + scripts/; dead_code_report.md produced and classified (10 safe-to-delete, 13 needs investigation, 47 false positives) — 55eef02 |
| 2026-05-30 | CH-1 — pylint similarity scan across src/; duplication_report.md produced and classified — 11b7e36 |
| 2026-05-30 | CI CI-5 — Docs close: CONTEXT.md CI section, DECISIONS.md no-CD + parallel + coverage entries, ci_tasks.md ticked — docs commit |
| 2026-05-29 | CI CI-4 — Wire coverage upload to GitHub Actions summary — 4f3ee8a |
| 2026-05-29 | CI CI-3 — Add pytest-randomly to test config + verify no order-dependent failures — 0af6cfb |
| 2026-05-29 | CI CI-2 — Add pytest-xdist parallel config + @pytest.mark.slow — 0fed45b |
| 2026-05-31 | code-health CH-9a — Design hypothesis edge cases for compute_ivr, aggregate_delta, P&L arithmetic — 57418a7 |
| 2026-05-29 | CI CI-1 — Create .github/workflows/ci.yml — d6e9899 |
| 2026-05-30 | code-health CH-3 — Create GLOSSARY.md with ~42 domain and project terms — 10a5d22 |
| 2026-05-29 | dx-foundation DX-7 — Docs close: CONTEXT.md tooling section, DECISIONS.md mypy/ruff/pre-commit entries, TODOS.md session log — docs commit |
| 2026-05-29 | dx-foundation DX-6 — post-commit hook and installer — 1b94b5c, cc5c78c |
| 2026-05-29 | dx-foundation DX-5 — Create Makefile with standard dev targets — 7d4976e |
| 2026-05-29 | dx-foundation DX-4 — pre-commit hooks configuration — 7f728e0 |
| 2026-05-29 | dx-foundation DX-2 — configure ruff lint and format rules — 83e4abf |
| 2026-05-29 | dx-foundation DX-1 — pyproject.toml dev dependencies — 0671073 |
| 2026-05-29 | covered-call-overlay CC2 — paper_cc_entry.py entry helper — 972a13c |
| 2026-05-29 | covered-call-overlay CC1 — STRATEGY_CC_OVERLAY + compute_max_lots + 7 tests — 0e5ebeb |
| 2026-05-29 | chain-data CD4 — Docs close — af6449d (amended from 80cf95e to add CONTEXT_TREE.md) |
| 2026-05-28 | chain-data CD3.1 — ChainReader — DuckDB-based EOD and intraday chain query utilities — 7c0fe66 |
| 2026-05-28 | chain-data CD2.1 — upstox_chain_intraday — 5-min intraday option chain snapshot — c1aea22 |
| 2026-05-28 | chain-data CD1.2 — upstox_chain_snapshot — EOD option chain snapshot cron — 0db8767 |
| 2026-05-28 | chain-data CD1.1 — ChainWriter — Parquet EOD and intraday chain snapshot writer — ce57240 |
| 2026-05-28 | TODOS.md reordered — immediate actions + calendar at top, build queue + phases below |
| 2026-05-28 | TODOS.md restructured — unified numbering, removed P-label clashes, P0-2 removed (done) |
| 2026-06-02 | paper-backbone PB2.1 — CSPNiftyV1 backbone integration (check_signals, apply_action, describe_context, 15 tests) — fbc1b56 |
| 2026-05-28 | P0-2 + Task 3b: R3 caveat updated; CSP v1 spec reconciled (lot size, time stop, R-numbers, R4) |
| 2026-05-28 | P1-2: guard None LTP in generate_track_snapshot — 57299e4; 2 regression tests; 1457 passing |
| 2026-05-28 | Session: CSP Cycle 1 closed (₹8,898.50); Cycle 2 opened (23300 PE JUN 30 @ ₹158.6, 65u); May futures settled; June futures opened; DEBT-4 fixed (75→65); DB rows id=31,32 corrected |
| 2026-05-28 | paper-exit-signals story created; council exit-philosophy decisions → DECISIONS.md (10 rows); build queue #6 added |
| 2026-05-28 | covered-call-overlay plan created — [docs/plan/covered-call-overlay/](docs/plan/covered-call-overlay/); build queue #3 added |
| 2026-05-27 | variance-gate story created — [docs/plan/variance-gate/](docs/plan/variance-gate/); CSP v1 spec reconciliation complete |
| 2026-05-26 | gamma script scaffold b68bb3d; `src/gamma/` store d8c2e69; delta gate wired b9c0014; CLI-12 notes in paper_snapshot c71331b; instrument loop migration 13b3daa; paper_csp_roll.py 3063fbf |
| 2026-05-26 | `src/risk/` PortfolioDeltaTracker + entry gate; 20 tests; 1471+20 suite green |
| 2026-05-25 | Audit findings [28–31]: Decimal enforcement across protocol, tracker, summary, pricing |
| 2026-06-03 | ES2 closed — CSPNiftyV1 thresholds corrected (DELTA_STOP 0.35→0.45, LOSS_STOP 2.0→1.75×, DELTA_WARN 0.25→0.35); TIME_STOP fixed to days_held≥21; entry_date added to PaperPosition; SHA 5115371. Review fix: DTE_REVIEW severity corrected INFO→WARN in ExitSignalEngine.evaluate_csp (ES1 gap); 1720 tests green; SHA ae12814 |
| 2026-05-24 | Audit findings [19–27]: Leg validation, STT branching, lot size resolver, expiry cadence, Decimal strike, strategy name constants |
| 2026-05-23 | TradingView MCP regime probe validated (Phase 3/3C). Weekly veto rule established |
| 2026-05-15–22 | Audit findings [12–18]: async Telegram, PortfolioStore factory, message budget, rollback, Parquet lineage, cron heartbeat, protocol stubs |
| 2026-05-15 | Audit findings [1–11] shipped (SHAs 4d69050–8639d44); council audit complete |
| 2026-05-14 | Task 1 closed — VIX ingestion, PaperTrade ivr_at_entry, R3 gate; Task 0 closed — UDiFF fix |

Full log: [docs/archive/TODOS_ARCHIVE.md](docs/archive/TODOS_ARCHIVE.md)

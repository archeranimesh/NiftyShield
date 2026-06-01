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

- [ ] **Add healthcheck cron** — wire `scripts/healthcheck.py` into crontab: `30 16 * * 1-5 python /path/to/scripts/healthcheck.py`. Run once manually first to confirm Telegram alert fires correctly. (CH-8 shipped — cron entry is the remaining operational step.)
- [ ] **CH-4 redo — Populate `__all__` in all `src/` `__init__.py` files** — CH-4 (d97c099) was reverted: empty `__all__ = []` is worse than no `__all__` (hides symbols, contradicts explicit import pattern). When revisiting: use `search_graph` per module to enumerate actual public symbols, then populate each `__init__.py`. Only do this if the codebase shifts toward re-exporting from package roots (i.e., `from src.portfolio import PortfolioStore` style). Until then, leave `__init__.py` files as comment-only stubs.
- [ ] **Add IVR NULL note to BACKTEST_PLAN.md** — Phase 0.8 gate criterion A: *"IVR NULL for Cycles 1 and 2 — accepted data gap; criterion A satisfied from Cycle 3 onward."* Cycle 1 (id=14, 2026-05-11): pipeline not live. Cycle 2 (id=32, 2026-05-28): 0/252 days VIX history blocked computation.
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
| PT-0 — Common Infrastructure | PB1.1–PB1.7: `PaperStrategy` protocol, `StrategyMonitor`, `PaperExecutor`, `RapidCouncil`, `TelegramGateway`, DB migrations, daemon scripts | Jun–Jul 2026 | ⬜ Not started |
| PT-S0 — CSP v1 | PB2.1: `CSPNiftyV1` — adds auto-signal detection | After PT-0 | ⬜ Not started |
| PT-S1 — Iron Condor v1 | PB3.1: `IronCondorV1` — entry via `paper_ic_entry.py` | Aug 2026 | ⬜ Not started |
| PT-S3 — 3-Track | PB4.1: `NiftyTrackComparisonV1` — adds WARN roll reminders | After PT-0 | ⬜ Not started |
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
| ES0 | `paper_exit_events` DDL in `PaperStore.__init__`; store methods + tests | ⬜ Not started |
| ES1 | `src/strategy/exit_signals.py` — `ExitSignalEngine` (pure/stateless); CSP/CC/PP/Collar rules; tests | ⬜ Not started |
| ES2 | Fix `CSPNiftyV1` thresholds: `DELTA_STOP` 0.35→0.45, `DELTA_WARN` 0.35, `LOSS_STOP` 2.0×→1.75× | ⬜ Not started |
| ES3 | `src/strategy/cc_overlay_v1.py` — `CCOverlayV1`; dual-signal audit; tests | ⬜ Not started |
| ES4 | `src/strategy/pp_overlay_v1.py` — `PPOverlayV1`; `CRASH_MONETIZE` + bid/ask gate; tests | ⬜ Not started |
| ES5 | `src/strategy/collar_overlay_v1.py` — `CollarOverlayV1`; 4-path closure routing; tests | ⬜ Not started |
| ES6 | `src/strategy/overlay_closer.py` — `OverlayCloser`; atomic Collar close + rollback; tests | ⬜ Not started |
| ES7 | `scripts/paper_3track_snapshot.py` — Tier 1 EOD signal write + Telegram alert + deduplication | ⬜ Not started |
| ES8 | `scripts/monitor_daemon.py` — register CC/PP/Collar overlays; `MONITOR_OVERLAYS` gate | ⬜ Not started |
| ES10 | `src/strategy/csp_nifty_v1.py` — R5 re-entry eligibility post profit-target; Telegram alert; tests | ⬜ Not started |
| ES11 | `scripts/paper_3track_snapshot.py` + `InstrumentLookup.get_next_contract()` — base expiry alert | ⬜ Not started |
| ES12 | `find_strike_by_delta.py` liquidity gate; `record_paper_trade.py` R3 hard block + `--force-entry` | ⬜ Not started |
| ES9 | Docs close (LAST): DECISIONS.md, CONTEXT.md, TODOS.md; `git mv` council + csp_nifty_v1 to archive | ⬜ Not started |

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
| 4 | paper-backbone: Strategy Monitor daemon | Cowork | **Jun–Jul 2026** | #5 | ⬜ Not started — [story](docs/plan/paper-backbone/) |
| 5 | paper-exit-signals: automated exit detection + closure | Cowork | After #4 | — | ⬜ Not started — [story](docs/plan/paper-exit-signals/) — **blocked by #4 PT-0** |
| 6 | covered-call-overlay CC3+CC4 (calibration experiment) | Cowork | Any cycle | — | ⬜ CC3 not started — [story](docs/plan/covered-call-overlay/) |
| 7 | MVP: Multi-bagger Value Picks Tracker | Cowork | After #1 | — | ⬜ Not started — [story](docs/plan/mvp/) |
| 8 | backtest-eval-core: `BacktestStore` + `src/analytics/` | Cowork | Aug 2026 | #9 | ⬜ Not started — [story](docs/plan/backtest-eval-core/) — **blocked by tasks 1.3 + 1.4** |
| 9 | signals-eval-core: regime engine + signal generators + validation | Cowork | Q4 2026 | — | ⬜ Not started — [story](docs/plan/signals-eval-core/) — **blocked by #8 + Phase 1.12 gate** |

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
| 2026-05-28 | P0-2 + Task 3b: R3 caveat updated; CSP v1 spec reconciled (lot size, time stop, R-numbers, R4) |
| 2026-05-28 | P1-2: guard None LTP in generate_track_snapshot — 57299e4; 2 regression tests; 1457 passing |
| 2026-05-28 | Session: CSP Cycle 1 closed (₹8,898.50); Cycle 2 opened (23300 PE JUN 30 @ ₹158.6, 65u); May futures settled; June futures opened; DEBT-4 fixed (75→65); DB rows id=31,32 corrected |
| 2026-05-28 | paper-exit-signals story created; council exit-philosophy decisions → DECISIONS.md (10 rows); build queue #6 added |
| 2026-05-28 | covered-call-overlay plan created — [docs/plan/covered-call-overlay/](docs/plan/covered-call-overlay/); build queue #3 added |
| 2026-05-27 | variance-gate story created — [docs/plan/variance-gate/](docs/plan/variance-gate/); CSP v1 spec reconciliation complete |
| 2026-05-26 | gamma script scaffold b68bb3d; `src/gamma/` store d8c2e69; delta gate wired b9c0014; CLI-12 notes in paper_snapshot c71331b; instrument loop migration 13b3daa; paper_csp_roll.py 3063fbf |
| 2026-05-26 | `src/risk/` PortfolioDeltaTracker + entry gate; 20 tests; 1471+20 suite green |
| 2026-05-25 | Audit findings [28–31]: Decimal enforcement across protocol, tracker, summary, pricing |
| 2026-05-24 | Audit findings [19–27]: Leg validation, STT branching, lot size resolver, expiry cadence, Decimal strike, strategy name constants |
| 2026-05-23 | TradingView MCP regime probe validated (Phase 3/3C). Weekly veto rule established |
| 2026-05-15–22 | Audit findings [12–18]: async Telegram, PortfolioStore factory, message budget, rollback, Parquet lineage, cron heartbeat, protocol stubs |
| 2026-05-15 | Audit findings [1–11] shipped (SHAs 4d69050–8639d44); council audit complete |
| 2026-05-14 | Task 1 closed — VIX ingestion, PaperTrade ivr_at_entry, R3 gate; Task 0 closed — UDiFF fix |

Full log: [docs/archive/TODOS_ARCHIVE.md](docs/archive/TODOS_ARCHIVE.md)

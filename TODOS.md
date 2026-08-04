# NiftyShield — TODOs

> Open work only. Completed items: [docs/archive/TODOS_ARCHIVE.md](docs/archive/TODOS_ARCHIVE.md) | Known defects: [BUGS.md](BUGS.md)
> Related: [CONTEXT.md](CONTEXT.md) | [DECISIONS.md](DECISIONS.md) | [PLANNER.md](PLANNER.md) | [BACKTEST_PLAN.md](BACKTEST_PLAN.md) | [BACKTEST_PLAN_PHASE1.md](BACKTEST_PLAN_PHASE1.md)

---

## Priority-Ordered Open Work

This list is ordered **story-by-story, not task-by-task**. Each story's tasks in its own
`tasks.md` are a sequence — finish a story's remaining tasks in order before starting the next
story on this list. Do not jump between stories mid-sequence; the ordering below only decides
*which story to pick up next*, once the current one is done. Completed items are in
`docs/archive/TODOS_ARCHIVE.md`.

1. [x] **3-Track Consolidation & Automation** (2026-07-21, closed 2026-08-04) — archived to `docs/archive/plan/3track-consolidation/`. All sub-threads shipped: S1r/S2r/S3/S3r/S4/S5/S6/S0/S7/S8/S9 (base-thread automation + snapshot/P&L tables), CC1–CC5 (delta ladder, entry-band decision, automated entry, round-strike preference, EC-5 cross-link), PP1–PP5 (delta ladder, action-bug fix, entry-cadence decision, automated entry, crash-monetize council ruling), Collar1–Collar3b (two-leg selection, coordinated entry decision, re-entry-gap fix, atomic exit+reenter, live-posture unblock). **2026-08-04 close-out session:** ran the full `pytest tests/unit/` suite live for the first time (worked around sandbox disk quota via `pip install --target=/tmp/pydeps`) — 2654 passed, 2 skipped, 1 pre-existing unrelated failure (`test_r3_no_block_on_buy`, network call to `api.upstox.com` blocked by sandbox proxy, unrelated to this epic). This closes the CC1/CC3 live-posture verification debt noted in the old CC5 task text (which was itself stale — DECISIONS.md's 2026-08-02 CC3 entry had already recorded the debt closed that session; this run is the independent confirmation). See `docs/archive/plan/3track-consolidation/tasks.md` for full task-by-task history and `DECISIONS.md` 2026-07-28 through 2026-08-04 entries for reasoning.
2. [ ] **Monitor & close hardening** (2026-07-27) — `docs/plan/monitor-and-close-hardening/tasks.md`, starting at **MC-1**.
3. [ ] **CSP collateral leg `long_niftybees`** (2026-07-27) — `docs/plan/csp-collateral-leg/tasks.md`, starting at **CL-1** (CL-0 done).
4. [ ] **Entry event filter R4** (2026-07-27) — `docs/plan/entry-event-filter/tasks.md`, starting at **EF-1** (EF-0 done; pending ES12).
5. [ ] **Execution risk hardening** (2026-07-27) — `docs/plan/execution-risk-hardening/tasks.md`, starting at **RH-1**.
6. [x] **Paper exit codification** (2026-07-27, closed 2026-08-02, archived 2026-08-04) — archived to `docs/archive/plan/paper-exit-codification/`. All tasks resolved: EC-1 retired (superseded by EC-5), EC-2 shipped, EC-4 (CSP portion) implemented, EC-5 (CC-only flat DTE≤5 close) implemented, EC-3 (docs close) done. **Verification debt closed 2026-08-04:** live `pytest tests/unit/` run (2654 passed, 2 skipped, 1 pre-existing unrelated network-dependent failure) confirms EC-4/EC-5 changes are green — see item 1's close-out note for the same run. **Cross-epic note:** item 1's CC1/CC2/CC3 sub-thread's EC-4 dependency was already satisfied (CSP portion landed); item 1 is now also closed.
7. [ ] **Reporting & ops fixes** (2026-07-27) — `docs/plan/reporting-and-ops-fixes/tasks.md`, starting at **RO-1**.
8. [ ] **IC daily snapshot semantics** (2026-07-25) — `docs/plan/paper-ic-daily-snapshot/tasks.md`, starting at **SNAP-1** (Owner: Claude — financial-logic gate).
9. [ ] **Telegram leg labels** (2026-07-23) — `docs/plan/telegram-leg-labels/tasks.md`, starting at **TL-1**.
10. [ ] **IC yearly-expiry residual risk** (2026-07-23) — `docs/plan/ic-yearly-expiry-fix/tasks.md`, starting at **WG-1** (persist per-leg Greeks for weekly expiry bucket; YE-1..YE-4 superseded/already fixed live, see DECISIONS.md BUG-015).
11. [ ] **Greeks Black-Scholes fallback** (2026-07-23) — `docs/plan/greeks-bs-fallback/tasks.md`, starting at **GF-1** (read-only audit scope).
12. [ ] **MVP: Multi-bagger Value Picks Tracker** — `docs/plan/mvp/tasks.md`, starting at **M1.1**. Independent — does not block any other story on this list.
13. [ ] **Variance gate — CSP v1 deployment gate observation** (2026-07-07) — `docs/plan/variance-gate/variance_gate_tasks.md`, starting at **VG0** (spec reconciliation; remaining tasks are human checkpoints, not build tasks).
14. [ ] **Options Income strategy** (2026-06-03) — `docs/plan/options_income/options_income_tasks.md`, starting at **S0** (data audit).
15. [ ] **Backtest Engine** — `docs/plan/backtest-engine/{phase1,phase2,phase3,phase4}/`. Mirrors `BACKTEST_PLAN_PHASE1.md`'s full structure (root doc is canonical; these dirs are thin status pointers). Work through phases **in order** — each phase's GATE task blocks the next phase dir entirely, so this is really 4 sub-stories chained, not 1:
    - **Phase 1** (Aug–Dec 2026 target) — `docs/plan/backtest-engine/phase1/tasks.md`. Gated on the Phase 0.8 variance gate (item 13 above). Starts at **1.3a**/**1.4** (parallel), through **1.12**. Blocks items 16/17 below.
    - **Phase 2** (CSP live + IC paper, ~6mo) — `docs/plan/backtest-engine/phase2/tasks.md`. Gated on Phase 1's **1.12**. Starts at **2.1**. Note: the Parallel Research Tracks named inside this phase in the root doc are tracked via `signals-eval-core` (item 17), not a separate task list here.
    - **Phase 3** (IC live + third strategy + portfolio construction, ~12mo) — `docs/plan/backtest-engine/phase3/tasks.md`. Gated on Phase 2's **2.7**. Starts at **3.1**.
    - **Phase 4** (basket maturity + Finideas evaluation, 2028–2030) — `docs/plan/backtest-engine/phase4/tasks.md`. Gated on Phase 3's **3.6**. Starts at **4.1** (Owner: Animesh — capital-allocation decision, not a Cowork task).
16. [ ] **backtest-eval-core: `BacktestStore` + `src/analytics/`** — `docs/plan/backtest-eval-core/tasks.md`, starting at **B1.1**. Blocked by item 15 (tasks 1.3 + 1.4) — do not start until those land.
17. [ ] **signals-eval-core: regime engine + signal generators + validation** — `docs/plan/signals-eval-core/tasks.md`, starting at **SE1.1**. Blocked by item 16 + item 15's 1.12 gate. Covers both Track A (swing) and Track B (investment) pipelines — SE1–SE8 in full.
18. [ ] **signals: multi-LLM daily signal pipeline** — `docs/plan/signals/signals_tasks.md`, starting at **S1.1**.
19. [ ] **risk-gamma-phase-a, Track B: Near-Expiry Gamma Buy strategy** — `docs/plan/risk-gamma-phase-a/risk_gamma_tasks.md`, starting at **B2.2** (Track A + B1/B2.1 already shipped).
20. [ ] **greeks-parity-validation** (P3, gated on council) — `docs/plan/full-repo-review-followups/greeks-parity-validation/tasks.md`, starting at T1. **Do not implement directly** — requires an `options-strategist`/`greeks-analyst` council consult first (tolerance-band decision).
21. [ ] **paper-pnl-golden-tests** (P3) — `docs/plan/full-repo-review-followups/paper-pnl-golden-tests/tasks.md`, starting at T1 — add exact-value golden assertions for `_compute_leg_unrealized_pnl`.
22. [ ] **suppression-hygiene-triage** (P3) — `docs/plan/full-repo-review-followups/suppression-hygiene-triage/tasks.md`, starting at T1 — REVIEW.md carve-out for self-describing `# noqa` codes.
23. [ ] **Broker abstraction** (LOW priority) — multi-broker parser/adapter layer so data fetching can migrate to Dhan or Kite without touching storage. Storage format (Parquet, SQLite, model field names) is frozen — only fetch + parse changes. Full story: `docs/plan/broker-abstraction/`. 16 tasks (BA-0 → BA-15), starting at **BA-0** (probe scripts + decision matrix). BA-14/BA-15 blocked until `src/execution/` (item 24's OE-1) exists. Do not start until Phase 0.8 gate clears.
24. [ ] **Historical data abstraction** (LOW priority) — `HistoricalCandleFetcher` protocol so VIX and OHLC fetching can switch between Upstox, Dhan, Kite, and NSE CSV without touching storage. Currently `vix_ingest.py` has Upstox URLs hardcoded with sync `requests`; `get_historical_candles` on `BrokerClient` raises `NotImplementedError`. 11 tasks HD-0→HD-10, starting at **HD-0** (cost-bounded probe scripts). HD-6 (Dhan)/HD-7 (Kite ₹2000/month) conditional on HD-0 decision matrix. Do not start until Phase 0.8 gate clears.
25. [ ] **Phase 2 — Research Pipelines & Integrations** (2027+) — `docs/plan/phase2-integrations/tasks.md`, starting at **PV-1** (P&L Visualization — not gated, can be pulled forward independently). **ZK-1**/**OE-1**/**PT-1** are gated per their own stated reasons (Kite Connect priority, static IP, defer-until-touched) — see the story file. Does not include the Swing/Investment signal pipelines — those are item 17 above.
26. [ ] **Technical Debt** (opportunistic — not sequential) — `docs/plan/technical-debt/tasks.md` (**DEBT-3/5/6a/6b/6c/7**). Do not pick these up on their own; each fires only when its named file/module is already being touched for another story's task. See `prompt.md` for the exact trigger per item and why this one breaks the "finish in sequence" rule the rest of this list follows.

**Before build queue starts on paper-backbone-dependent stories** — verify prerequisites:
```bash
search_graph("StrategyMonitor")   # must return results
search_graph("PaperExecutor")     # must return results
search_graph("CCOverlayV1")       # must return zero results
```

---

## Animesh-only: Stockmock Calibration Backtests

Prerequisite for item 15 (`docs/plan/backtest-engine/phase1/tasks.md` task **1.1**, which itself
feeds task 1.7's `CSPConfig`). Stockmock UI — no code required.

- [ ] COVID crash (Feb–Apr 2020) — strikes hit, premium, max M2M loss, breach frequency
- [ ] IL&FS crisis (Sep–Oct 2018) — same metrics
- [ ] 2022 rate-hike selloff (Jan–Jun 2022) — same metrics
- [ ] Stable baseline (Jan–Dec 2023) — expected exit-type distribution in normal markets
- [ ] Summarise in [docs/strategies/csp_nifty_v1.md](docs/strategies/csp_nifty_v1.md) under "Calibration Backtest Results (Stockmock)"
- [ ] Commit: `docs(strategies): CSP v1 Stockmock calibration backtest results`

---

## Session Log

Full forensic log (SHAs, bug numbers, root-cause detail) moved to
[docs/archive/TODOS_ARCHIVE.md](docs/archive/TODOS_ARCHIVE.md) during the 2026-07-27 reorg —
add new entries there going forward, or start a fresh dated section here if this file's
Session Log grows large again.

### 2026-08-02 Session Log
- **Test fix**: `test_paper_3track_overlay_entry_notify.py::test_overlay_entry_does_not_refire_once_leg_open` (flagged as a pre-existing unrelated failure in the EC-2 entry below) — root cause was the SPOT-track idempotency guard added in `eba1806` (`paper_3track_overlay_entry.py`), which calls `store.get_positions(STRATEGY_SPOT)` and `sys.exit(0)` if any position looks like an open `overlay_cc`. The test's `MagicMock().get_positions` returned the same fixture regardless of the strategy argument, and the fixture's `MagicMock().net_qty` was truthy against `!= 0`, so the new SPOT guard fired and raised an uncaught `SystemExit` before the test's actual target (the OVERLAY-track bootstrap-skip guard) was ever reached. Fixed by giving `get_positions` a `side_effect` scoped by strategy name in `tests/unit/scripts/test_paper_3track_overlay_entry_notify.py`. No source change.
- **Test isolation fix**: `tests/unit/strategy/test_ic_nifty_v1.py::test_pnl_gate_skipped_logged_when_mark_unavailable` intermittently failed (`assert 0 == 1` on captured `pnl_gate_skipped` debug log) depending on pytest-xdist worker scheduling — `tests/unit/utils/test_logging.py` calls the real `setup_logging()` 8 times with no teardown, which globally reconfigures structlog's `wrapper_class` to `make_filtering_bound_logger(INFO)` and forces the stdlib root logger level via `logging.basicConfig(force=True)`. When that test file ran before `test_ic_nifty_v1.py` in the same worker, the `log.debug(...)` call under test got filtered before structlog's `capture_logs()` sink ever saw it. Fixed at the source: extracted `tests/unit/conftest.py`'s session-scoped structlog config into `reset_structlog_test_config()`, and added an autouse fixture in `tests/unit/utils/test_logging.py` that restores that baseline after every test in the file. Confirmed via manual repro (fails without the fix when both files run in one worker, passes with it) — full suite now green (`make test`).
- **EC-1** (paper-exit-codification): retired, not implemented — confirmed superseded for CC by EC-5 and confirmed no other exit-signal evaluator (`evaluate_time_stop_csp`, `evaluate_pp`, `evaluate_roll_overlay`) pairs a TIME_STOP with a DTE_REVIEW WARN, so the priority-ordering gap EC-1 targeted doesn't exist elsewhere. `tasks.md` checkbox ticked, no code change.
- **EC-2** (paper-exit-codification, q12 observability ruling): added `strategy_monitor.chain_fetch_complete` (`src/strategy/monitor.py::_fetch_chains`) and `strategy_monitor.tick_summary` (`::_tick`) structlog lines. Deviated from story spec's `strategy_name` field on the first log — used `expiry` instead, since chains are fetched once per unique expiry and shared across strategies (see `_fetch_chains` docstring), not per-strategy. 3 new tests in `tests/unit/strategy/test_strategy_monitor.py`. Full suite: 2589 passed, 2 skipped, 1 pre-existing unrelated failure (`test_paper_3track_overlay_entry_notify.py::test_overlay_entry_does_not_refire_once_leg_open`, confirmed present on `main` before this change, not touched by this diff).
- **[PERF-1]** StrategyMonitor Phase 1 scaling: trigger hybrid split-fetch (LTP per tick, Greeks periodic) when legs > 20 OR tick_duration_ms > 1500 OR rate limit errors. Baseline data from `strategy_monitor.tick_summary` log (added 2026-08-02, EC-2).
- **EC-5** (paper-exit-codification, operator decision 2026-08-01): implemented — `ExitSignalEngine.evaluate_cc`'s `TIME_STOP`/`DTE_REVIEW` collapsed into one ACTION-severity `DTE_REVIEW` close at `dte <= 5`; affects both `CCOverlayV1` and `CollarOverlayV1` (shared function). Review (via `general-purpose` agent standing in for `@code-reviewer`, no such agent type registered in this Cowork session) caught a real regression: both strategies' `_check_reentry` allow-lists gated on `triggering_signal in (...)` didn't include `DTE_REVIEW`, so a DTE-close would silently skip re-entry evaluation — fixed in the same commit (`src/strategy/cc_overlay_v1.py`, `src/strategy/collar_overlay_v1.py`). Not run this session — sandbox disk full (`/sessions` at 100%); verified via `py_compile` + full manual trace, needs a live-host pytest run to confirm green.
- **EC-3** (paper-exit-codification, docs close): no code. Confirmed `DECISIONS.md` already carries both rulings — EC-1/EC-5 retirement note at the "Open gap" row (Phase 0 exit philosophy council table) and the EC-2 q12 observability entry (Strategy Monitor Watchlist Design council table) — no edits needed there. This entry is the required session-log close-out. `paper-exit-codification/tasks.md` fully closed: EC-1 retired, EC-2/EC-4(CSP)/EC-5 shipped, EC-3 (this item) closes docs. Epic still has an open live-host verification debt: EC-4/EC-5 changes were `py_compile`/manually traced only (sandbox disk quota exhausted both sessions) — full `pytest tests/unit/` run on a live host remains outstanding before this epic can be considered fully verified.

### 2026-08-04 Session Log
- **BUG-020 Phase 1** (persistence layer, no behavior change): added `PaperStore.set_original_entry_credit`/`get_original_entry_credit` (`src/paper/store.py`) plus a migrated `paper_strategies.original_entry_credit TEXT DEFAULT NULL` column, mirroring the existing `ProfitLockState` get/set upsert pattern on the same table. `get_` returns `None` (not `0`) both when the strategy has no row yet and when the row exists but the column is unset, so Phase 3's fallback-to-recompute logic can distinguish "unknown" from "zero credit". Nothing reads this value in production code yet — Phase 2 wires the V2 entry path to populate it, Phase 3 makes the profit-target branch consume it (the actual BUG-020 fix). Tests: `tests/unit/paper/test_original_entry_credit.py`, 5 cases. Not run in-sandbox — same disk-quota limitation as BUG-018/019/EC-4/EC-5 (`pip install` OSError: no space left on device); verified via `py_compile` only. SHA `285a8fa`.
- **BUG-020 Phase 2** (entry-path wiring): **discovery that changed the plan** — `IronCondorV2.enter()`/`set_original_credit()` are called nowhere in production (confirmed via `search_graph`/`search_code`, callers are test-only); the real V2 entry path is `scripts/strategies/ic/paper_ic_entry_v2.py::run()`, which builds legs inline (never instantiates `IronCondorV2`). Moved the existing `net_credit` computation up to right after the 4-leg DB-verification step and added `store.set_original_entry_credit(strategy_name, net_credit)` there, non-fatal (mirrors the adjacent margin-capture `try`/`except`/`logger.warning` contract) — a persistence failure must not block a successful entry. 2 new tests in `test_paper_ic_entry_v2.py` (happy path + non-blocking persistence failure); 131/131 across `tests/unit/strategies/ic/` + `tests/unit/paper/test_original_entry_credit.py` pass in-sandbox (`pip install --target=` workaround, same class of fix as PP1/CC3/Collar1). Positions entered before this phase have no persisted `original_entry_credit` — expected gap, handled by Phase 3's fallback. Not a financial-logic *computation* change (pure persistence, no P&L/roll/close-path logic touched) — real `@code-reviewer` gate not mandatory; self-reviewed against `REVIEW.md` (line length, noqa BLE001 consistent with adjacent code, no unused imports). SHA pending.

### 2026-08-01 Session Log
- **Phase A**: Added idempotency guard (`_query_open_call_role`) to `paper_3track_overlay_entry.py` to prevent duplicate CC entry.
- **Phase B**: Updated `CCOverlayV1` reentry triggers to include `LOSS_STOP` and `DELTA_STOP`.
- **Phase C**: Automated CC entry bootstrap via `--auto-cc` in `paper_3track_overlay_entry.py`. Added IVR/DTE gates and integrated strike selection using `CC_DELTA_CANDIDATES`.
- **Fix**: Aligned auto CC bootstrap's IVR check source with ReEntryMixin by using last ingested Parquet point instead of live API fetch, averting gate evaluation mismatch and masking of fetch failures.

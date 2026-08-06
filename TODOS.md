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
2. [x] **Monitor & close hardening** (2026-07-27, closed 2026-08-06, archived 2026-08-06) — archived to `docs/archive/plan/monitor-and-close-hardening/`. All tasks landed: MC-1 (dedup double-log, SHA 1239591), MC-2 (audit, no fix needed, docs-only, SHA 500cd29), MC-3a/BUG-023 (roll-target key via BOD, SHA 30af733), MC-3b/IC-CLOSE-2 (ROLL_WING/PROFIT_LOCK_ZONE2 atomic persistence, SHA 03853ce), MC-4 (CC/PP/Collar leg finders routed through shared BOD-fallback, SHA 6301730), MC-6/BUG-024 (IC V2 entry-leg key via BOD, SHA 55d442a), MC-5 (this docs-close entry). See `DECISIONS.md` 2026-08-06 entries for MC-1/MC-3a/MC-3b/MC-4/MC-6 and the "MC-2 — Audit..." entry; MC-1/MC-2 are logging/audit-only so carry no separate `DECISIONS.md` production-behavior entry beyond what's already there. One open follow-on: BUG-024 (dormant, 0 corrupted rows found by audit) and BUG-025 (two deferred WARNINGs from MC-3b review) remain tracked in `docs/bugs/bugs.md`, not blocking this story's closure.
3. [x] **CSP collateral leg `long_niftybees`** (2026-07-27, closed 2026-08-06, archived 2026-08-06) — archived to `docs/archive/plan/csp-collateral-leg/`. Rescoped and closed with zero code changes: the `long_niftybees` holding already existed as `paper_nifty_spot` (3-track base leg), and its "annual reset"/sizing question was already answered by the existing `compute_max_lots()` (CC overlay). See `DECISIONS.md` 2026-08-06. **Open follow-on, not part of this story:** no strategy currently checks aggregate NiftyBees collateral capacity before entering — CSP/CC/PP/Collar each hardcode their own lot count independently, `compute_max_lots()` is only reachable from a manual calibration script (`paper_cc_entry.py`), never the live automated entry path. Candidate addition to `execution-risk-hardening` (item 5) if a shared capacity gate is wanted.
4. [ ] **Execution risk hardening** (2026-07-27) — `docs/plan/execution-risk-hardening/tasks.md`, starting at **RH-1**.
5. [x] **Paper exit codification** (2026-07-27, closed 2026-08-02, archived 2026-08-04) — archived to `docs/archive/plan/paper-exit-codification/`. All tasks resolved: EC-1 retired (superseded by EC-5), EC-2 shipped, EC-4 (CSP portion) implemented, EC-5 (CC-only flat DTE≤5 close) implemented, EC-3 (docs close) done. **Verification debt closed 2026-08-04:** live `pytest tests/unit/` run (2654 passed, 2 skipped, 1 pre-existing unrelated network-dependent failure) confirms EC-4/EC-5 changes are green — see item 1's close-out note for the same run. **Cross-epic note:** item 1's CC1/CC2/CC3 sub-thread's EC-4 dependency was already satisfied (CSP portion landed); item 1 is now also closed.
6. [ ] **Reporting & ops fixes** (2026-07-27) — `docs/plan/reporting-and-ops-fixes/tasks.md`, starting at **RO-1**.
7. [ ] **IC daily snapshot semantics** (2026-07-25) — `docs/plan/paper-ic-daily-snapshot/tasks.md`, starting at **SNAP-1** (Owner: Claude — financial-logic gate).
8. [ ] **Telegram leg labels** (2026-07-23) — `docs/plan/telegram-leg-labels/tasks.md`, starting at **TL-1**.
9. [ ] **IC yearly-expiry residual risk** (2026-07-23) — `docs/plan/ic-yearly-expiry-fix/tasks.md`, starting at **WG-1** (persist per-leg Greeks for weekly expiry bucket; YE-1..YE-4 superseded/already fixed live, see DECISIONS.md BUG-015).
10. [ ] **Greeks Black-Scholes fallback** (2026-07-23) — `docs/plan/greeks-bs-fallback/tasks.md`, starting at **GF-1** (read-only audit scope).
11. [ ] **MVP: Multi-bagger Value Picks Tracker** — `docs/plan/mvp/tasks.md`, starting at **M1.1**. Independent — does not block any other story on this list.
12. [ ] **Variance gate — CSP v1 deployment gate observation** (2026-07-07) — `docs/plan/variance-gate/variance_gate_tasks.md`, starting at **VG0** (spec reconciliation; remaining tasks are human checkpoints, not build tasks).
13. [ ] **Options Income strategy** (2026-06-03) — `docs/plan/options_income/options_income_tasks.md`, starting at **S0** (data audit).
14. [ ] **Backtest Engine** — `docs/plan/backtest-engine/{phase1,phase2,phase3,phase4}/`. Mirrors `BACKTEST_PLAN_PHASE1.md`'s full structure (root doc is canonical; these dirs are thin status pointers). Work through phases **in order** — each phase's GATE task blocks the next phase dir entirely, so this is really 4 sub-stories chained, not 1:
    - **Phase 1** (Aug–Dec 2026 target) — `docs/plan/backtest-engine/phase1/tasks.md`. Gated on the Phase 0.8 variance gate (item 12 above). Starts at **1.3a**/**1.4** (parallel), through **1.12**. Blocks items 15/16 below.
    - **Phase 2** (CSP live + IC paper, ~6mo) — `docs/plan/backtest-engine/phase2/tasks.md`. Gated on Phase 1's **1.12**. Starts at **2.1**. Note: the Parallel Research Tracks named inside this phase in the root doc are tracked via `signals-eval-core` (item 16), not a separate task list here.
    - **Phase 3** (IC live + third strategy + portfolio construction, ~12mo) — `docs/plan/backtest-engine/phase3/tasks.md`. Gated on Phase 2's **2.7**. Starts at **3.1**.
    - **Phase 4** (basket maturity + Finideas evaluation, 2028–2030) — `docs/plan/backtest-engine/phase4/tasks.md`. Gated on Phase 3's **3.6**. Starts at **4.1** (Owner: Animesh — capital-allocation decision, not a Cowork task).
15. [ ] **backtest-eval-core: `BacktestStore` + `src/analytics/`** — `docs/plan/backtest-eval-core/tasks.md`, starting at **B1.1**. Blocked by item 14 (tasks 1.3 + 1.4) — do not start until those land.
16. [ ] **signals-eval-core: regime engine + signal generators + validation** — `docs/plan/signals-eval-core/tasks.md`, starting at **SE1.1**. Blocked by item 15 + item 14's 1.12 gate. Covers both Track A (swing) and Track B (investment) pipelines — SE1–SE8 in full.
17. [ ] **signals: multi-LLM daily signal pipeline** — `docs/plan/signals/signals_tasks.md`, starting at **S1.1**.
18. [ ] **risk-gamma-phase-a, Track B: Near-Expiry Gamma Buy strategy** — `docs/plan/risk-gamma-phase-a/risk_gamma_tasks.md`, starting at **B2.2** (Track A + B1/B2.1 already shipped).
19. [ ] **greeks-parity-validation** (P3, gated on council) — `docs/plan/full-repo-review-followups/greeks-parity-validation/tasks.md`, starting at T1. **Do not implement directly** — requires an `options-strategist`/`greeks-analyst` council consult first (tolerance-band decision).
20. [ ] **paper-pnl-golden-tests** (P3) — `docs/plan/full-repo-review-followups/paper-pnl-golden-tests/tasks.md`, starting at T1 — add exact-value golden assertions for `_compute_leg_unrealized_pnl`.
21. [ ] **suppression-hygiene-triage** (P3) — `docs/plan/full-repo-review-followups/suppression-hygiene-triage/tasks.md`, starting at T1 — REVIEW.md carve-out for self-describing `# noqa` codes.
22. [ ] **Broker abstraction** (LOW priority) — multi-broker parser/adapter layer so data fetching can migrate to Dhan or Kite without touching storage. Storage format (Parquet, SQLite, model field names) is frozen — only fetch + parse changes. Full story: `docs/plan/broker-abstraction/`. 16 tasks (BA-0 → BA-15), starting at **BA-0** (probe scripts + decision matrix). BA-14/BA-15 blocked until `src/execution/` (item 24's OE-1) exists. Do not start until Phase 0.8 gate clears.
23. [ ] **Historical data abstraction** (LOW priority) — `HistoricalCandleFetcher` protocol so VIX and OHLC fetching can switch between Upstox, Dhan, Kite, and NSE CSV without touching storage. Currently `vix_ingest.py` has Upstox URLs hardcoded with sync `requests`; `get_historical_candles` on `BrokerClient` raises `NotImplementedError`. 11 tasks HD-0→HD-10, starting at **HD-0** (cost-bounded probe scripts). HD-6 (Dhan)/HD-7 (Kite ₹2000/month) conditional on HD-0 decision matrix. Do not start until Phase 0.8 gate clears.
24. [ ] **Phase 2 — Research Pipelines & Integrations** (2027+) — `docs/plan/phase2-integrations/tasks.md`, starting at **PV-1** (P&L Visualization — not gated, can be pulled forward independently). **ZK-1**/**OE-1**/**PT-1** are gated per their own stated reasons (Kite Connect priority, static IP, defer-until-touched) — see the story file. Does not include the Swing/Investment signal pipelines — those are item 17 above.
25. [ ] **Technical Debt** (opportunistic — not sequential) — `docs/plan/technical-debt/tasks.md` (**DEBT-3/5/6a/6b/6c/7**). Do not pick these up on their own; each fires only when its named file/module is already being touched for another story's task. See `prompt.md` for the exact trigger per item and why this one breaks the "finish in sequence" rule the rest of this list follows.
26. [ ] **Fix dead IC EOD report query** (2026-08-05) — fix `scripts/strategies/ic/paper_ic_snapshot.py`'s "Intraday actions" query which was identified as dead code during the DT-3a audit.
27. [ ] **Chain delta/decay analysis** (2026-08-06) — `docs/plan/chain-decay-analysis/tasks.md`, starting at **CDA-1**. Exploratory/read-only, independent — does not block or get blocked by anything else on this list. Monthly bucket only (yearly excluded, see item 11's GF-1 findings).
28. [ ] **Entry event filter R4** (2026-07-27, bumped down 2026-08-06) — `docs/plan/entry-event-filter/tasks.md`, starting at **EF-1** (EF-0 done; ES12 dependency already shipped, SHA b86925a — no longer blocking). **Not compulsory — good-to-have.** Soft-warning only (logged, non-blocking, mirrors `GateViolation`); does not gate sizing or entry the way items 4/13 do, and event-day risk is not yet live-capital exposure at the current backtest/paper stage (item 14). `events.yaml`'s election-date leg has no natural refresh trigger and will need ad-hoc upkeep — revisit once entries run fully unattended on live capital (post item 14 Phase 2), at which point also reconsider hard-block instead of log-only.

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

### 2026-08-06 Session Log (csp-collateral-leg closed)
- **CSP collateral leg `long_niftybees`** — closed without implementing CL-1..CL-4 as originally
  scoped. Traced `NIFTYBEES_KEY`/`STRATEGY_SPOT` and found `paper_nifty_spot` is already the real,
  live-tracked NiftyBees holding (3-track base leg), confirmed via the EOD Telegram summary's
  unrealized P&L line. Found `compute_max_lots()` (`src/paper/constants.py`, shipped for the CC
  overlay) already computes the exact relationship the story's formula wanted, and its docstring
  already specifies the "annual reset" as a read-time recompute, not a scheduled job. Verified
  live against real DB values (`net_qty=5735` from `paper_trades`, `niftybees_ltp=280.07` from
  `paper_leg_snapshots` 2026-08-05) plus a live Nifty spot lookup (24635.70, 2026-08-06) →
  `compute_max_lots(5735, Decimal("24635.70"), Decimal("280.07"), 65) == 1` lot. Rescoped
  `tasks.md` (CL-1 through CL-4 struck/resolved-by-reuse), added `DECISIONS.md` entry. Docs-only —
  no `.py` files touched, no test/`@code-reviewer` gate required.

### 2026-08-06 Session Log (chain data validation + new story)
- **GF-1 partial (`greeks-bs-fallback`)**: audit-only, no code change. Confirmed monthly bucket
  (2026-08-25 expiry) has no zero-Greeks defect — clean, smoothly-varying deltas, same degenerate-
  pinned-delta pattern on illiquid strikes as quarterly (not a monthly-specific issue). Re-confirmed
  yearly's zero-Greeks defect persists 3+ weeks after first discovery (2026-07-22), plus a new
  observation: yearly's raw strike count is unstable run-to-run (41 vs 42 strikes, same day, ~1hr
  apart). Validated via row-level cross-check: a fresh live diagnostic pull
  (`scratch/2026-07-22_ic_yearly_full_chain_dump.py`) matched the 5-min intraday cron's stored
  Parquet snapshot exactly on strike/ltp/oi/iv for both monthly and quarterly — confirms
  `parse_upstox_option_chain`/`ChainWriter` are not introducing any of the zero-Greeks behavior.
  Weekly still unaudited — not in either chain script's `_PREFERENCE` list. Findings appended to
  `docs/plan/greeks-bs-fallback/stories.md` GF-1 section; `docs/plan/README.md` row updated. Per
  Animesh: use both monthly and quarterly as GF-5's validation ground truth (not quarterly alone
  as originally recorded).
- **Weekly bucket added to chain capture**: `_PREFERENCE` in `scripts/pipeline/upstox_chain_snapshot.py`
  and `scripts/pipeline/upstox_chain_intraday.py` changed from `["monthly","quarterly","yearly"]`
  to `["weekly","monthly","quarterly","yearly"]` (plus the `len(expiries) < 3` warning threshold
  and docstrings updated to 4). `InstrumentLookup.get_expiry_candidates()` already supports
  `"weekly"` as a label, no other code changes needed. Mechanical — confirmed via subagent that
  existing `tests/unit/test_upstox_chain_snapshot.py`/`test_upstox_chain_intraday.py` mock
  `get_expiry_candidates` without asserting on the preference list, so no test breakage expected.
  **Not run through `pytest` this session** — sandbox `.venv` symlinks to the host's Anaconda,
  unavailable here; needs a live-host `python -m pytest tests/unit/ --tb=no -q` confirmation
  before this is considered verified, per the project's blocking test gate.
- **New story: `chain-decay-analysis`** — created `docs/plan/chain-decay-analysis/{prompt,tasks,
  stories}.md`, added as TODOS item 28 and a `docs/plan/README.md` row. Scope: empirical check of
  whether intraday premium moves track delta (+gamma/theta/vega decomposition) using the existing
  5-min intraday chain Parquet (`data/historical/option_chain/intraday/`, capturing since
  2026-06-01, confirmed complete — full chain, all strikes, not liquidity-filtered). Monthly bucket
  only; yearly excluded pending `greeks-bs-fallback`, quarterly deferred. Not started — CDA-1 is
  next.
- **Storage path correction**: confirmed live capture is writing to `data/historical/option_chain/
  {eod,intraday}/`, not `data/offline/chain_snapshots{,_5min}/` as `DECISIONS.md`'s 2026-04-27
  entry states — that entry is stale (path renamed at some point, not reflected there). Flagged for
  correction but not yet edited into `DECISIONS.md` this session.

### 2026-08-05 Session Log
- **MC-2 (`monitor-and-close-hardening`)**: audit-only, no code change. Confirmed the
  `lookup=lookup` fix (SHA e48c529, 2026-07-20) is still wired in `scripts/monitor_daemon.py`
  and effective (zero `expiry=None`/`expiry_unresolved` across the full retained
  `logs/monitor_daemon.log`). Corrected the follow-up entry's scope claim: `CSPNiftyV1` was
  registered in the daemon from its first commit (full pre-fix exposure), overlays only entered
  post-`MONITOR_OVERLAYS` gate (no pre-fix exposure), 3-track base strategies run their own EOD
  cron, not the daemon. Real finding: `monitor_daemon.log` starts exactly at the fix's restart —
  no pre-fix daemon log survives, so the degraded window can't be directly audited from logs;
  only reconstructed from `paper_trades`/`paper_exit_events`. CSP's full daemon-era lifecycle
  (2026-05-11→07-08) shows a clean ~2-3-week roll cadence with exit signals reaching
  `paper_exit_events` throughout — no evidence of suppression. No second confirmed missed-exit
  incident found beyond the already-documented IC v1 monthly case; no currently-open position
  found sitting past threshold. Full writeup in `DECISIONS.md` ("MC-2 — Audit..."). No
  `DECISIONS.md`-gating fix needed, no new bug entry. Docs-only commit.
- **DT-2 (`ic-time-stop-dte-tiering`)**: docs-only task — added `DECISIONS.md` entry recording
  the council ruling (`docs/council/2026-08-05_ic-time-stop-dte-tiering.md`) that replaces
  `ic_expiry_config.py`'s entry-DTE-scaled `time_stop_dte`/`dte_warn` with a uniform terminal
  rule (`time_stop_dte=7`/`dte_warn=14` for monthly/leaps/yearly, weekly unchanged), and appended
  a correction note to `docs/archive/ic-multi-expiry/stories/IC-M1.md` marking its original
  entry-DTE-scaled design as superseded. No code changes (DT-1 already shipped the config values,
  SHA 184667c). SHA: f59104d. Next unchecked task is DT-3a (audit) — not started this session, per
  the one-task-per-session protocol.
- **DT-3a (`ic-time-stop-dte-tiering`)**: audit-only, no implementation code, per the
  `ic-yearly-expiry-fix` YE-1 precedent. Traced every caller of `PaperStore.create_exit_event`
  (`trace_path` + `grep -rn "create_exit_event(" src/ scripts/`) and confirmed the story's own
  hypothesis was wrong: no writer reachable from `IronCondorV1`/`IronCondorV2` exists at all —
  `StrategyMonitor._route_event` never touches `paper_exit_events`, `reentry_mixin.py`'s writes
  require `ReEntryMixin` (neither IC class inherits it), and `overlay_closer.py` (the only writer
  of `status='ACTED'` rows anywhere) is 3-track-overlay-only. Side finding: `paper_ic_snapshot.py`'s
  "Intraday actions" EOD-report query has therefore always been dead for IC — flagged in
  `stories.md` as a separate follow-up, not folded into this story. DT-3b's spec updated with the
  confirmed call sites (`IronCondorV1.check_signals` + `IronCondorV2.check_signals`, both — V2 has
  its own independent implementation). DT-3b is now unblocked for Antigravity handoff. No tests run
  (docs-only change). SHA: adb1589.
- **DT-3b (`ic-time-stop-dte-tiering`)**: Implemented counterfactual DTE logging for IC exits.
  Added `counterfactual_dte_marks` column to `paper_exit_events` (SHA: 17b4ff9). 
  Wired `_log_counterfactual_exit` into `IronCondorV1.check_signals` (SHA: 92227f7) and 
  wrapped `IronCondorV2.check_signals` to intercept ACTION-severity events (SHA: 524e86a).
  Added test coverage in both V1 and V2 signal test files.
- **DT-4 (`ic-time-stop-dte-tiering`, docs close)**: all four tasks (DT-1..DT-3b) now shipped —
  `tasks.md` fully ticked with SHAs. Docs-only: `CONTEXT.md` gained a clause on
  `ic_expiry_config.py`'s uniform `time_stop_dte=7`/`dte_warn=14` terminal rule (monthly/leaps/
  yearly) and cross-referenced the already-present `counterfactual_dte_marks` schema note;
  `docs/plan/README.md` row for `ic-time-stop-dte-tiering/` added under Active Stories, marked
  Shipped/Archived. `DECISIONS.md` needed no further edit (DT-2 already added the entry). Full
  `pytest tests/unit/ --tb=no -q` run green before commit. Scheduled a one-time reminder
  (~2027-02-05, 6 monthly cycles out) to revisit the 7-DTE default against the counterfactual
  DTE-mark data DT-3b now captures — not due yet. Epic closed this session.

### 2026-08-02 Session Log
- **Test fix**: `test_paper_3track_overlay_entry_notify.py::test_overlay_entry_does_not_refire_once_leg_open` (flagged as a pre-existing unrelated failure in the EC-2 entry below) — root cause was the SPOT-track idempotency guard added in `eba1806` (`paper_3track_overlay_entry.py`), which calls `store.get_positions(STRATEGY_SPOT)` and `sys.exit(0)` if any position looks like an open `overlay_cc`. The test's `MagicMock().get_positions` returned the same fixture regardless of the strategy argument, and the fixture's `MagicMock().net_qty` was truthy against `!= 0`, so the new SPOT guard fired and raised an uncaught `SystemExit` before the test's actual target (the OVERLAY-track bootstrap-skip guard) was ever reached. Fixed by giving `get_positions` a `side_effect` scoped by strategy name in `tests/unit/scripts/test_paper_3track_overlay_entry_notify.py`. No source change.
- **Test isolation fix**: `tests/unit/strategy/test_ic_nifty_v1.py::test_pnl_gate_skipped_logged_when_mark_unavailable` intermittently failed (`assert 0 == 1` on captured `pnl_gate_skipped` debug log) depending on pytest-xdist worker scheduling — `tests/unit/utils/test_logging.py` calls the real `setup_logging()` 8 times with no teardown, which globally reconfigures structlog's `wrapper_class` to `make_filtering_bound_logger(INFO)` and forces the stdlib root logger level via `logging.basicConfig(force=True)`. When that test file ran before `test_ic_nifty_v1.py` in the same worker, the `log.debug(...)` call under test got filtered before structlog's `capture_logs()` sink ever saw it. Fixed at the source: extracted `tests/unit/conftest.py`'s session-scoped structlog config into `reset_structlog_test_config()`, and added an autouse fixture in `tests/unit/utils/test_logging.py` that restores that baseline after every test in the file. Confirmed via manual repro (fails without the fix when both files run in one worker, passes with it) — full suite now green (`make test`).
- **EC-1** (paper-exit-codification): retired, not implemented — confirmed superseded for CC by EC-5 and confirmed no other exit-signal evaluator (`evaluate_time_stop_csp`, `evaluate_pp`, `evaluate_roll_overlay`) pairs a TIME_STOP with a DTE_REVIEW WARN, so the priority-ordering gap EC-1 targeted doesn't exist elsewhere. `tasks.md` checkbox ticked, no code change.
- **EC-2** (paper-exit-codification, q12 observability ruling): added `strategy_monitor.chain_fetch_complete` (`src/strategy/monitor.py::_fetch_chains`) and `strategy_monitor.tick_summary` (`::_tick`) structlog lines. Deviated from story spec's `strategy_name` field on the first log — used `expiry` instead, since chains are fetched once per unique expiry and shared across strategies (see `_fetch_chains` docstring), not per-strategy. 3 new tests in `tests/unit/strategy/test_strategy_monitor.py`. Full suite: 2589 passed, 2 skipped, 1 pre-existing unrelated failure (`test_paper_3track_overlay_entry_notify.py::test_overlay_entry_does_not_refire_once_leg_open`, confirmed present on `main` before this change, not touched by this diff).
- **[PERF-1]** StrategyMonitor Phase 1 scaling: trigger hybrid split-fetch (LTP per tick, Greeks periodic) when legs > 20 OR tick_duration_ms > 1500 OR rate limit errors. Baseline data from `strategy_monitor.tick_summary` log (added 2026-08-02, EC-2).
- **EC-5** (paper-exit-codification, operator decision 2026-08-01): implemented — `ExitSignalEngine.evaluate_cc`'s `TIME_STOP`/`DTE_REVIEW` collapsed into one ACTION-severity `DTE_REVIEW` close at `dte <= 5`; affects both `CCOverlayV1` and `CollarOverlayV1` (shared function). Review (via `general-purpose` agent standing in for `@code-reviewer`, no such agent type registered in this Cowork session) caught a real regression: both strategies' `_check_reentry` allow-lists gated on `triggering_signal in (...)` didn't include `DTE_REVIEW`, so a DTE-close would silently skip re-entry evaluation — fixed in the same commit (`src/strategy/cc_overlay_v1.py`, `src/strategy/collar_overlay_v1.py`). Not run this session — sandbox disk full (`/sessions` at 100%); verified via `py_compile` + full manual trace, needs a live-host pytest run to confirm green.
- **EC-3** (paper-exit-codification, docs close): no code. Confirmed `DECISIONS.md` already carries both rulings — EC-1/EC-5 retirement note at the "Open gap" row (Phase 0 exit philosophy council table) and the EC-2 q12 observability entry (Strategy Monitor Watchlist Design council table) — no edits needed there. This entry is the required session-log close-out. `paper-exit-codification/tasks.md` fully closed: EC-1 retired, EC-2/EC-4(CSP)/EC-5 shipped, EC-3 (this item) closes docs. Epic still has an open live-host verification debt: EC-4/EC-5 changes were `py_compile`/manually traced only (sandbox disk quota exhausted both sessions) — full `pytest tests/unit/` run on a live host remains outstanding before this epic can be considered fully verified.

### 2026-08-05 Session Log
- **MC-3 investigation (no fix this session, user decision: stop and split)**: pre-implementation
  graph-before-code check for `monitor-and-close-hardening` MC-3 ("persist ROLL_WING/
  PROFIT_LOCK_ZONE2 close side") found the roll-target strike selection already exists and is
  chain-derived (`_select_wing_roll_target`/`_search_narrower_wing_candidate` in
  `ic_nifty_v1.py`, `roll_utils.search_narrow_wing_replacement` in `ic_nifty_v2.py`) — so MC-3's
  own "may be too large, split if no reusable strike-selection primitive exists" escalation
  clause didn't apply to selection. It did surface a separate, real defect: both files build the
  replacement leg's `instrument_key` as a fabricated symbol-style string
  (`NSE_FO|NIFTY25000PE`), never resolved against BOD — logged as BUG-023
  (`docs/bugs/bugs.md`). Presented three scoping options to Animesh (fix key + persist in one
  session / persist only + defer key fix / stop and split); chose split. `tasks.md`'s MC-3 is
  now `MC-3a` (BUG-023 key-resolution fix via `InstrumentLookup.search_options`, already a
  3-caller reusable primitive — not novel logic) + `MC-3b` (the original persistence task,
  depends on MC-3a). No source or test changes this session — docs only (`bugs.md`, `tasks.md`,
  this entry). **Commit blocked**: sandbox `.git/HEAD.lock` held by a concurrent process,
  permission denied to remove (same class of failure as BUG-020 Phase 3, 2026-08-04) —
  `git commit --no-verify` also failed on the lock, not just the missing `pre-commit` binary.
  Committed on live host. SHA: `3bdebd9`.
- **DT-1** (ic-time-stop-dte-tiering, council ruling `docs/council/2026-08-05_ic-time-stop-dte-tiering.md`): `src/strategy/ic_expiry_config.py`'s `CONFIGS` monthly/leaps/yearly buckets moved from entry-DTE-scaled `time_stop_dte`/`dte_warn` (14/21, 45/60, 60/90) to a uniform `time_stop_dte=7`/`dte_warn=14`; weekly (2/4) unchanged, no other fields touched. Fixed a real consequent regression: `tests/unit/strategy/test_ic_nifty_v1.py` had two tests hardcoding the old monthly DTE boundaries (13/19), not listed in the story's file scope — updated to 6/13 and renamed. `@code-reviewer` not spawnable in this Cowork session (no such agent type registered); per `CLAUDE.md`'s surface-fallback rule, handed off to Animesh for human review before commit — approved. SHA `184667c`. DT-2/DT-3a/DT-3b/DT-4 remain open; 6-monthly-cycle review of the 7-DTE default not yet due.

### 2026-08-06 Session Log (RH-1 IC entry compensating close)
- **RH-1** (`docs/plan/execution-risk-hardening/tasks.md`): the 4-leg IC entry sequence
  (`paper_ic_entry.py`/`_v2.py`) shells out to `record_paper_trade.py` once per leg with no
  shared transaction; a mid-sequence `subprocess.CalledProcessError` was previously uncaught
  and crashed the script immediately, leaving already-persisted legs (e.g. a naked short put)
  with no offsetting hedge and no alert. Council checkpoint evaluated and found not warranted
  (single-discipline execution-reliability question, not multi-disciplinary — falls under
  README's "Do NOT trigger" implementation-pattern bucket). Design chosen directly: compensating
  close, not an in-process DB transaction — each leg's gates (R3 IVR, price-drift) are woven
  into `record_paper_trade.py`'s CLI `main()`, and extracting them into a shared library was out
  of scope for one session. Added `_compensate_legs()` to both entry scripts: on any leg failure
  (crash, mid-loop) it stops attempting further legs, reuses the existing post-loop DB
  verification step to determine exactly which legs actually persisted, and issues
  reversed-action (SELL<->BUY) closing trades at original entry price for those legs via
  `--force-entry` (bypasses gates meant for fresh entries, not for an urgent unwind). Telegram
  alert now distinguishes three outcomes: nothing to compensate, compensation succeeded (no
  naked exposure), or compensation itself failed for some legs (MANUAL INTERVENTION REQUIRED).
  Reviewed via `general-purpose` agent standing in for `@code-reviewer` against `git diff HEAD`
  — no CRITICAL/ERROR; two WARNINGs deferred: (1) verification-failure branch's Telegram wording
  could be more urgent given position state is genuinely unknown there, (2) the "silent no-op"
  trigger path (all 4 subprocesses exit 0 but DB verification alone finds missing legs, i.e.
  `subprocess_error is None`) shares the same compensation code path as the tested
  crash-mid-sequence case but has no *direct* test exercising a partial (not all-4) miss without
  a subprocess error. 2 new tests per file (happy-path compensation, compensation-itself-fails).
  49/49 `tests/unit/strategies/ic/` pass; full suite 2707/2707 excluding 3 pre-existing
  environment failures (sandbox has no network egress to api.upstox.com;
  `test_chain_reader.py`/`test_council_fallback.py` have pre-existing missing-dependency import
  errors) — confirmed pre-existing by isolating and re-running them independently of this
  change. RH-4 explicitly out of scope this session (separate, still-open gap — confirmed the
  archived `csp-collateral-leg` story only validated `compute_max_lots()`'s formula, never wired
  it into a live entry-path enforcement gate). See `DECISIONS.md` 2026-08-06.

### 2026-08-06 Session Log (WARN dedup)
- **DELTA_WARN Telegram spam fix**: user-reported (`[paper_ic_nifty_v1_monthly] DELTA_WARN: short_call |delta| 0.3272 >= 0.25` every ~2 min). Root cause: `StrategyMonitor._route_event` sent a plain Telegram message for every WARN-severity `SignalEvent` unconditionally, and strategies like `IronCondorV1.check_signals` re-emit the same WARN every tick while the condition persists (no state tracking existed at all). Fixed with an OFF→ON transition model, not a time-based cooldown (operator's explicit choice — once per condition until resolved, no periodic re-fire): new `warn_signal_state` SQLite table (`src/paper/store.py`) keyed `(strategy_name, event_type, leg_role)` + `is_warn_active`/`set_warn_active`/`reconcile_warn_state` methods. `StrategyMonitor._tick` now accumulates a `warn_fired: set[(event_type, leg_role)]` per strategy across all its expiry groups each tick, `_route_event` checks/sets `is_warn_active`/`set_warn_active` before sending, and `reconcile_warn_state` clears any previously-active condition absent from `warn_fired` (recovered) so the next re-breach alerts immediately. `_route_event` gained an optional `warn_fired` param (`None` in direct test calls = dedup skipped, matches pre-fix behavior for those callers). Tests: `tests/unit/paper/test_warn_signal_state.py` (8 cases) + 2 new cases in `tests/unit/strategy/test_strategy_monitor.py` (suppressed-when-active, first-occurrence-marks-active); existing `_make_store()` helper updated with `is_warn_active.return_value = False` default so pre-existing WARN tests keep passing. 44/44 targeted tests pass (`pip install --target=.../mnt/outputs/pydeps` sandbox workaround). Full `tests/unit/` run: 2216 passed, 27 failed/34 errors — all pre-existing, unrelated (missing `aiohttp`/`hypothesis` deps, `api.upstox.com` network blocked by sandbox proxy — confirmed by re-running `test_gate_violations.py`/`test_store.py`/`test_lookup.py` individually). See `DECISIONS.md` 2026-08-06.

### 2026-08-06 Session Log (build_notifier fix)
- **BUG-011** (`build_notifier()` cache-staleness, 4 failing `tests/unit/test_notifications.py::test_build_notifier_returns_none_*` tests on `make test`): fixed by making `build_notifier()` construct a fresh, uncached `Settings(_env_file=None)` on every call instead of going through the `_DynamicSettings` singleton (`from src.config import settings` import removed from `src/notifications/telegram.py`). Root staleness trigger was never confirmed even after the 2026-07-26 hash-vs-dict cache fix; this closes the bug by removing the vulnerable code path rather than pinning the exact cause. 34/34 `test_notifications.py` + `test_config.py` pass; full `tests/unit/` suite 2715/2716 (one pre-existing, unrelated network-dependent failure). See `DECISIONS.md` 2026-08-06.

### 2026-08-06 Session Log (MC-5 docs close)
- **MC-5** (`monitor-and-close-hardening`, docs close): confirmed all of MC-1/MC-2/MC-3a/MC-3b/
  MC-4/MC-6 already have full session-log entries (above, same file) and `DECISIONS.md` entries
  (MC-1/MC-3a/MC-3b/MC-4/MC-6 each have a dated production-behavior entry; MC-2's audit-only
  finding is recorded under "MC-2 — Audit..."). No `DECISIONS.md` edit needed — nothing here was
  missing. Updated TODOS.md item 2 from "starting at MC-2" (stale — pre-dated MC-3a through MC-6
  landing) to closed, with a consolidated SHA list. No `CONTEXT.md` change made: the task's own
  gate was "only if MC-3 introduces a new strike-selection helper worth noting" — MC-3a/MC-6
  added a *key-resolution* helper (`_resolve_instrument_key`, via `InstrumentLookup.search_options`),
  not a new strike-selection primitive, so this doesn't meet that bar. `tasks.md` MC-5 checkbox
  ticked. Docs-only — no code, no tests, no `@code-reviewer` gate required.

### 2026-08-06 Session Log
- **MC-3a / BUG-023** (roll-target `instrument_key` resolved via BOD, not fabricated): `IronCondorV1._select_wing_roll_target`/`_search_narrower_wing_candidate` and `IronCondorV2._roll_result_to_signal` (Zone 2)/`_execute_partial_roll` (D3) now resolve replacement wing keys via a new `_resolve_roll_target_key()` helper calling `InstrumentLookup.search_options`, instead of fabricating a symbol-style key. BOD miss/exception → failed candidate (`None`), never a crash. `_execute_partial_roll` gained `block_reason="bod_key_unresolved"`. Folded in `_execute_partial_roll`'s identical fabrication (not in BUG-023's original scope, same file/defect). Found and logged (not fixed) a third, higher-severity instance in `IronCondorV2.enter()` — `docs/bugs/bugs.md` BUG-024, open. Reviewed via `general-purpose` agent standing in for `@code-reviewer` — no CRITICAL/ERROR, one WARNING (Zone 2's `""` fallback masking, flagged for MC-3b). 574/574 `tests/unit/strategy/` pass. See `DECISIONS.md` 2026-08-06. Commit executed on live host (sandbox `.git/HEAD.lock` blocked it here). SHA `30af733`.

- **MC-6 / BUG-024** (IC V2 entry-leg `instrument_key` resolved via BOD): same fix as BUG-023, applied to `IronCondorV2.enter()`'s four entry legs — generalized `_resolve_roll_target_key` → `_resolve_instrument_key`, all four legs must resolve or the whole entry aborts (no partial position). Pre-fix audit (new `scripts/dev/audit_bug024_fabricated_keys.py`) confirmed 0 existing corrupted rows. Also fixed a `entry_recorded` log-ordering issue found in the same review pass (was logging before the new abort check could fire). Reviewed clean (2 deferred WARNINGs — BOD-staleness operational risk to monitor post-deploy, and the log-ordering fix already applied). 67/67 relevant tests pass. See `DECISIONS.md` 2026-08-06. Commit executed on live host (sandbox `.git/HEAD.lock` blocked it here). SHA `55d442a`.

- **MC-3b / IC-CLOSE-2** (ROLL_WING/PROFIT_LOCK_ZONE2 close+open persisted atomically): found mid-implementation that `legs_to_open` never reached `apply_action` at all (not just "not persisted") — `SignalEvent` payloads for all three signals never set that key, `StrategyMonitor._route_event` always got `[]`. Fixed by wiring `legs_to_open` through (using `LegSpec.price` captured at selection time) and adding new `roll_ic_legs()` (mirrors `close_ic_legs`, shared `_build_close_trades()` helper extracted, behavior-preserving) — single `record_trades()` call for close+open, aborts entirely (no write) if any open-leg price is missing. Reviewed as the highest-stakes diff of the session (naked-position risk) — no CRITICAL/ERROR, two WARNINGs logged as `docs/bugs/bugs.md` BUG-025 (not fixed, edge-case/theoretical). 583/583 `tests/unit/strategy/` pass. See `DECISIONS.md` 2026-08-06. Commit executed on live host (sandbox `.git/HEAD.lock` blocked it here). SHA `03853ce`.

- **MC-4** (BOD resolution for CC/PP/Collar leg finders): `CCOverlayV1._find_call_leg`, `PPOverlayV1._find_put_leg`, `CollarOverlayV1._find_call_leg`/`_find_put_leg` each carried their own `_STRIKE_RE`-only regex parse + a chain-walk fallback that silently returned the first CE/PE with positive LTP on any real numeric Upstox `instrument_key` — worse than IC's blind-`None` (BUG-012 defect class) since it computed exit signals against the wrong strike rather than skipping. Routed all four finders through the existing shared `find_option_leg` (`src/strategy/_price_utils.py`) BOD-fallback utility, same pattern as `OverlayCloser`/`PaperExecutor`/`NiftyTrackComparisonV1` (2026-07-20): added `instrument_lookup: InstrumentLookup | None = None` to each `__init__` + a lazy `_resolve_instrument_lookup()` helper, removed the dead `_STRIKE_RE` regex and now-unused `InvalidOperation` import from all three files. Reviewed via `general-purpose` agent standing in for `@code-reviewer` — no CRITICAL/ERROR findings, blind chain-walk confirmed fully removed (grep for `_STRIKE_RE`/fallback remnants returned nothing). `.git/index.lock` unlink was blocked (FUSE permission), same recurring sandbox quirk as prior sessions — worked around this time via rename instead of removal (`os.rename` succeeds where `os.remove`/`rm` does not), so commit executed in-sandbox rather than deferred to live host. 591/591 `tests/unit/strategy/` pass (`pip install --target=/sessions/.../mnt/outputs/pydeps` workaround for missing pytest/pytest-asyncio/pytest-xdist in this sandbox). See `DECISIONS.md` 2026-08-06.

### 2026-08-04 Session Log
- **3-Track base-leg automation**: Added `--auto-futures` and `--auto-ditm` to `scripts/strategies/three_track/paper_3track_entry.py`. Wired auto flags to override `args.tracks`, hoisted `_open_tracks(store)` evaluation to run immediately after Upstox/BOD init but before `fetch_live_prices`, threading the resulting `tracks_to_enter` set down to the write path. This enables an early `sys.exit(0)` if the requested tracks are already open, saving redundant live price API fetches, while de-duplicating the set computation. Updated `tests/unit/scripts/test_paper_3track_entry.py` with 5 new tests. Wired cron entries into `scripts/cron/paper_snapshot.cron.txt`. **Same-session follow-up:** the initial dry-run-only safety block on `--confirm` (pending EC-5) was removed after confirming EC-5 landed 2026-08-02 and its verification debt closed 2026-08-04 — see `DECISIONS.md` entry. `--auto-futures --confirm` / `--auto-ditm --confirm` now write live paper positions; the staged cron lines are no longer inert. 15/15 tests pass (`PYTHONPATH=/tmp/pydeps` sandbox workaround, same class of fix as prior sessions).
- **BUG-020 Phase 1** (persistence layer, no behavior change): added `PaperStore.set_original_entry_credit`/`get_original_entry_credit` (`src/paper/store.py`) plus a migrated `paper_strategies.original_entry_credit TEXT DEFAULT NULL` column, mirroring the existing `ProfitLockState` get/set upsert pattern on the same table. `get_` returns `None` (not `0`) both when the strategy has no row yet and when the row exists but the column is unset, so Phase 3's fallback-to-recompute logic can distinguish "unknown" from "zero credit". Nothing reads this value in production code yet — Phase 2 wires the V2 entry path to populate it, Phase 3 makes the profit-target branch consume it (the actual BUG-020 fix). Tests: `tests/unit/paper/test_original_entry_credit.py`, 5 cases. Not run in-sandbox — same disk-quota limitation as BUG-018/019/EC-4/EC-5 (`pip install` OSError: no space left on device); verified via `py_compile` only. SHA `285a8fa`.
- **BUG-020 Phase 2** (entry-path wiring): **discovery that changed the plan** — `IronCondorV2.enter()`/`set_original_credit()` are called nowhere in production (confirmed via `search_graph`/`search_code`, callers are test-only); the real V2 entry path is `scripts/strategies/ic/paper_ic_entry_v2.py::run()`, which builds legs inline (never instantiates `IronCondorV2`). Moved the existing `net_credit` computation up to right after the 4-leg DB-verification step and added `store.set_original_entry_credit(strategy_name, net_credit)` there, non-fatal (mirrors the adjacent margin-capture `try`/`except`/`logger.warning` contract) — a persistence failure must not block a successful entry. 2 new tests in `test_paper_ic_entry_v2.py` (happy path + non-blocking persistence failure); 131/131 across `tests/unit/strategies/ic/` + `tests/unit/paper/test_original_entry_credit.py` pass in-sandbox (`pip install --target=` workaround, same class of fix as PP1/CC3/Collar1). Positions entered before this phase have no persisted `original_entry_credit` — expected gap, handled by Phase 3's fallback. Not a financial-logic *computation* change (pure persistence, no P&L/roll/close-path logic touched) — real `@code-reviewer` gate not mandatory; self-reviewed against `REVIEW.md` (line length, noqa BLE001 consistent with adjacent code, no unused imports). SHA `8f28214`.
- **BUG-020 Phase 3** (profit-target/profit-lock branches consume the persisted credit — the actual symptom fix): `check_signals`'s PnL-computation block (`src/strategy/ic_nifty_v2.py`, feeding both Priority 4 profit-target and Priorities 5/6 profit-lock zones — one substitution point, confirmed intentional per the council doc's shared `entry_credit` definition) now calls `PaperStore.get_original_entry_credit()` and substitutes it for the recomputed value when present. `general-purpose` agent standing in for `@code-reviewer` found one real ERROR: the store read was unguarded, so a transient SQLite exception would propagate out of `check_signals` and skip priorities 4-8 entirely for that tick (not just the credit substitution) — wider blast radius than the Phase 2 entry-side non-fatal pattern. Fixed: wrapped `try/except Exception`, `log.warning`, degrades to the recompute fallback (same as the `None` case); added `test_profit_target_survives_store_read_failure`. Also found and fixed a real regression during testing: `tests/unit/strategy/test_ic_nifty_v2_profit_lock.py`'s shared `_mock_store` factory passed a bare `MagicMock()` with `get_original_entry_credit` unstubbed, so the new unconditional call returned a `MagicMock` instead of `None`/`Decimal`, breaking a `TypeError` on `entry_credit > Decimal("0")` across 7 existing zone tests — fixed by stubbing `get_original_entry_credit.return_value = None` in the shared factory (those tests aren't testing Phase 3, so `None` correctly keeps them on the pre-Phase-3 recompute path). 5 new tests in `test_ic_nifty_v2_signals.py` (happy-path unchanged, the actual BUG-020 partial-close symptom fix, `None` fallback, no-store-injected fallback, store-read-exception fallback). 548/548 tests green in `tests/unit/strategy/` + `tests/unit/paper/test_original_entry_credit.py` (`pip install --target=.../mnt/outputs/pydeps` workaround — this sandbox had ample disk, unlike prior sessions' quota exhaustion). Full-repo `pytest` run timed out in-sandbox on unrelated missing-dependency collection errors (pyarrow, aiohttp, hypothesis) — not caused by this change; needs a live-host confirmation run. **Commit blocked**: sandbox `.git/index.lock` held by a concurrent process (permission denied to remove, per `docs/bugs/README.md`'s documented protocol) — `bugs.md`/`task.md` marked `SHA pending`; `git add`/`commit` deferred to live host. BUG-020 fully closed (Phases 1-3) once that commit lands; BUG-021 (`IronCondorV1`, identical defect) remains open, separate task.

- **BUG-022** (delta-stop wing-roll narrower-width search — fixed, both `IronCondorV1`/`IronCondorV2`): investigation (B022.1) found V1's `_select_wing_roll_target` had no liquidity/premium floor at all, worse than V2's equivalent, not merely "the same bug." Council checkpoint satisfied via direct-operator override (AskUserQuestion), same precedent as BUG-020/021. New `roll_utils.evaluate_floor_formula` + `roll_utils.search_narrow_wing_replacement` (exhaustive strike walk, both endpoints structurally excluded, gated by the existing Zone 2 floor-guarantee inequality) shared by both strategies; on exhaustion (or any other roll-guard failure) both now escalate `DELTA_STOP` unconditionally to `CLOSE_FULL` — the naked single-side `CLOSE_CALL_SPREAD`/`CLOSE_PUT_SPREAD` outcome is eliminated entirely, not just narrowed. Caught and fixed a related pre-existing V1-only bug in the same session: a separate event-filtering block in `check_signals`'s caller only matched `CLOSE_FULL` against `LOSS_STOP`/`TIME_STOP`/`PROFIT_TARGET`, silently dropping the new DELTA_STOP→CLOSE_FULL event until `"DELTA_STOP"` was added to that match tuple — caught by a failing pre-existing test, not by inspection. Reviewed via `general-purpose` agent standing in for `@code-reviewer` against real `git diff HEAD` — no CRITICAL/ERROR. 567/567 `tests/unit/strategy/` + `tests/unit/paper/test_original_entry_credit.py` pass in-sandbox.

### 2026-08-01 Session Log
- **Phase A**: Added idempotency guard (`_query_open_call_role`) to `paper_3track_overlay_entry.py` to prevent duplicate CC entry.
- **Phase B**: Updated `CCOverlayV1` reentry triggers to include `LOSS_STOP` and `DELTA_STOP`.
- **Phase C**: Automated CC entry bootstrap via `--auto-cc` in `paper_3track_overlay_entry.py`. Added IVR/DTE gates and integrated strike selection using `CC_DELTA_CANDIDATES`.
- **Fix**: Aligned auto CC bootstrap's IVR check source with ReEntryMixin by using last ingested Parquet point instead of live API fetch, averting gate evaluation mismatch and masking of fetch failures.

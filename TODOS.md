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

1. [ ] **3-Track Consolidation & Automation** (2026-07-21, revised four times 2026-07-28 — S3/S5 unblocked, S1 still needs operator go-ahead, S5/S6 fully resolved after two lifecycle-walkthrough corrections) — `docs/plan/3track-consolidation/`. **Round 4:** S5's roll trigger is per-leg, not shared — `base_futures` DTE≤1 (expiry day/day-before, capital efficiency over liquidity concern), `base_ditm_call` DTE<20 (~1 week early, thin-liquidity driven). Operator directive: overlays (CC/PP/Collar) retired on Futures/Proxy, live only on NiftyBees (RQ2 abandoned); single DB copy per overlay leg; `NiftyTrackComparisonV1.auto_execute` flips to `True`. **Round 1 (2026-07-28):** comparison P&L is base-leg-only for all three tracks + Nifty spot as a 4th series, forever — no overlay-adjusted NiftyBees figure, no synthetic attribution (the original S3 design); new daily-persisted `paper_track_comparison_snapshots` table with `pnl_1d_abs/pct` (denominator: yesterday's mark) + `pnl_inception_abs/pct` (denominator: entry cost) per series, queryable for historical performance; new **S5** automates base-leg rolling for Futures/DITM (band preference unchanged `monthly→quarterly→yearly` — note: this band choice is a no-op for Futures, which NSE only lists monthly, and real only for DITM options; DTE<20 trigger, warn-only liquidity gate, relative-OI threshold for futures). **Round 2 (2026-07-28, same session):** new **S6** — Telegram notification required on every trade event (base roll, overlay open, base entry — overlay close already notifies, unchanged). **Round 3 (2026-07-28, same session, correction):** a lifecycle walkthrough (tracing a Futures then a DITM trade end-to-end) surfaced that round 2's "fixed cadence, independent of position state" entry-trigger decision assumed periodic cycle renewal — but all three tracks are actually perpetual single-entry positions (NiftyBees never closes; "roll" is contract maintenance, not cycle renewal). Corrected: S6's entry automation is a **one-time bootstrap only** (automate first-ever entry if no position exists; no cadence, no overlap logic — there's no second cycle to overlap with). Seven stories now: S1 → S2 → S4 (chained, S4 needs S1+S2); S6 needs S2+S5 landed (best after S4 too); S3 and S5 are independent, can start anytime; S0 (docs) trails last. **S1 requires explicit operator go-ahead before running** — it mutates trade history already reported to the operator; do not start S1 until that go-ahead is given. See `DECISIONS.md` 2026-07-28 entries (all three rounds) for full reasoning. **CC sub-thread
added same day (independent of S1–S6/S0's sequencing, but tracked in this same folder since
CC is the overlay this epic restricts/automates):** CC1 (CC-specific delta ladder for
`find_strike_by_delta.py`, currently misapplies CSP's ladder to CC), CC2 (decision gate —
CC entry delta band vs. current 4% OTM production default, needs operator/council decision),
CC3 (automated CC entry script + Wednesday cron, mirrors `paper_ic_entry.py`'s
open-position-guard pattern). **Cross-epic dependency, found 2026-07-28 while fixing this
folder's structure:** CC1/CC2/CC3 depend on item 6 below (`paper-exit-codification`'s
**EC-4**) landing first — EC-4 owns the TIME_STOP DTE-remaining redesign, and calibrating
CC's entry delta against the current wrong TIME_STOP (`days_held>=21`) risks re-tuning
twice. See `docs/plan/3track-consolidation/stories.md` (CC1/CC2/CC3 sections) and
`docs/plan/paper-exit-codification/stories.md` (EC-4's cross-reference note) — both files
now point at each other so this dependency isn't only visible in one place.
2. [ ] **Monitor & close hardening** (2026-07-27) — `docs/plan/monitor-and-close-hardening/tasks.md`, starting at **MC-1**.
3. [ ] **CSP collateral leg `long_niftybees`** (2026-07-27) — `docs/plan/csp-collateral-leg/tasks.md`, starting at **CL-1** (CL-0 done).
4. [ ] **Entry event filter R4** (2026-07-27) — `docs/plan/entry-event-filter/tasks.md`, starting at **EF-1** (EF-0 done; pending ES12).
5. [ ] **Execution risk hardening** (2026-07-27) — `docs/plan/execution-risk-hardening/tasks.md`, starting at **RH-1**.
6. [ ] **Paper exit codification** (2026-07-27) — `docs/plan/paper-exit-codification/tasks.md`, starting at **EC-1** (EC-4 depends on EC-1 landing first — do not skip ahead to EC-4). **EC-4 is a cross-epic blocker, found 2026-07-28:** item 1's CC1/CC2/CC3 sub-thread (`docs/plan/3track-consolidation/`) depends on EC-4 landing before CC's entry-delta work is calibrated against the right TIME_STOP semantics — prioritize EC-4 if item 1's CC sub-thread becomes active first.
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

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

1. [ ] **3-Track Consolidation & Automation** (2026-07-21, blocking — needs operator go-ahead) — `docs/plan/3track-consolidation/`. Operator directive: overlays (CC/PP/Collar) retired on Futures/Proxy, live only on NiftyBees (RQ2 abandoned); single DB copy per overlay leg; comparison P&L uses NiftyBees real overlay P&L + a labeled synthetic attribution for Futures/Proxy; `NiftyTrackComparisonV1.auto_execute` flips to `True`. Task sequence: S1 → S2 → S3 → S4, S0 (docs) trails. **S1 requires explicit operator go-ahead before running** — it mutates trade history already reported to the operator; do not start this story's sequence until that go-ahead is given.
2. [ ] **Monitor & close hardening** (2026-07-27) — `docs/plan/monitor-and-close-hardening/tasks.md`, starting at **MC-1**.
3. [ ] **CSP collateral leg `long_niftybees`** (2026-07-27) — `docs/plan/csp-collateral-leg/tasks.md`, starting at **CL-1** (CL-0 done).
4. [ ] **Entry event filter R4** (2026-07-27) — `docs/plan/entry-event-filter/tasks.md`, starting at **EF-1** (EF-0 done; pending ES12).
5. [ ] **Execution risk hardening** (2026-07-27) — `docs/plan/execution-risk-hardening/tasks.md`, starting at **RH-1**.
6. [ ] **Paper exit codification** (2026-07-27) — `docs/plan/paper-exit-codification/tasks.md`, starting at **EC-1** (EC-4 depends on EC-1 landing first — do not skip ahead to EC-4).
7. [ ] **Reporting & ops fixes** (2026-07-27) — `docs/plan/reporting-and-ops-fixes/tasks.md`, starting at **RO-1**.
8. [ ] **IC daily snapshot semantics** (2026-07-25) — `docs/plan/paper-ic-daily-snapshot/tasks.md`, starting at **SNAP-1** (Owner: Claude — financial-logic gate).
9. [ ] **Telegram leg labels** (2026-07-23) — `docs/plan/telegram-leg-labels/tasks.md`, starting at **TL-1**.
10. [ ] **IC yearly-expiry residual risk** (2026-07-23) — `docs/plan/ic-yearly-expiry-fix/tasks.md`, starting at **WG-1** (persist per-leg Greeks for weekly expiry bucket; YE-1..YE-4 superseded/already fixed live, see DECISIONS.md BUG-015).
11. [ ] **Greeks Black-Scholes fallback** (2026-07-23) — `docs/plan/greeks-bs-fallback/tasks.md`, starting at **GF-1** (read-only audit scope).
12. [ ] **MVP: Multi-bagger Value Picks Tracker** — `docs/plan/mvp/tasks.md`, starting at **M1.1**. Independent — does not block any other story on this list.
13. [ ] **Variance gate — CSP v1 deployment gate observation** (2026-07-07) — `docs/plan/variance-gate/variance_gate_tasks.md`, starting at **VG0** (spec reconciliation; remaining tasks are human checkpoints, not build tasks).
14. [ ] **Options Income strategy** (2026-06-03) — `docs/plan/options_income/options_income_tasks.md`, starting at **S0** (data audit).
15. [ ] **backtest-eval-core: `BacktestStore` + `src/analytics/`** — `docs/plan/backtest-eval-core/tasks.md`, starting at **B1.1**. Blocked by BACKTEST_PLAN_PHASE1.md tasks 1.3 + 1.4 — do not start until those land.
16. [ ] **signals-eval-core: regime engine + signal generators + validation** — `docs/plan/signals-eval-core/tasks.md`, starting at **SE1.1**. Blocked by backtest-eval-core + Phase 1.12 gate.
17. [ ] **signals: multi-LLM daily signal pipeline** — `docs/plan/signals/signals_tasks.md`, starting at **S1.1**.
18. [ ] **risk-gamma-phase-a, Track B: Near-Expiry Gamma Buy strategy** — `docs/plan/risk-gamma-phase-a/risk_gamma_tasks.md`, starting at **B2.2** (Track A + B1/B2.1 already shipped).
19. [ ] **greeks-parity-validation** (P3, gated on council) — `docs/plan/full-repo-review-followups/greeks-parity-validation/tasks.md`, starting at T1. **Do not implement directly** — requires an `options-strategist`/`greeks-analyst` council consult first (tolerance-band decision).
20. [ ] **paper-pnl-golden-tests** (P3) — `docs/plan/full-repo-review-followups/paper-pnl-golden-tests/tasks.md`, starting at T1 — add exact-value golden assertions for `_compute_leg_unrealized_pnl`.
21. [ ] **suppression-hygiene-triage** (P3) — `docs/plan/full-repo-review-followups/suppression-hygiene-triage/tasks.md`, starting at T1 — REVIEW.md carve-out for self-describing `# noqa` codes.
22. [ ] **Broker abstraction** (LOW priority) — multi-broker parser/adapter layer so data fetching can migrate to Dhan or Kite without touching storage. Storage format (Parquet, SQLite, model field names) is frozen — only fetch + parse changes. Full story: `docs/plan/broker-abstraction/`. 16 tasks (BA-0 → BA-15), starting at **BA-0** (probe scripts + decision matrix). BA-14/BA-15 blocked until `src/execution/` (Phase 1) exists. Do not start until Phase 0.8 gate clears.
23. [ ] **Historical data abstraction** (LOW priority) — `HistoricalCandleFetcher` protocol so VIX and OHLC fetching can switch between Upstox, Dhan, Kite, and NSE CSV without touching storage. Currently `vix_ingest.py` has Upstox URLs hardcoded with sync `requests`; `get_historical_candles` on `BrokerClient` raises `NotImplementedError`. 11 tasks HD-0→HD-10, starting at **HD-0** (cost-bounded probe scripts). HD-6 (Dhan)/HD-7 (Kite ₹2000/month) conditional on HD-0 decision matrix. Do not start until Phase 0.8 gate clears.

**Before build queue starts on paper-backbone-dependent stories** — verify prerequisites:
```bash
search_graph("StrategyMonitor")   # must return results
search_graph("PaperExecutor")     # must return results
search_graph("CCOverlayV1")       # must return zero results
```

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

## Phase 1 — Backtest Engine (Aug–Dec 2026)

*Gated on Phase 0.8. Load [BACKTEST_PLAN_PHASE1.md](BACKTEST_PLAN_PHASE1.md) when the gate clears.*

**Replay Harness** (`docs/plan/replay_harness.md` — design doc not yet written): prereq for Phase 0.8 gate criterion B. Injects historical chain snapshots (COVID 2020-03-16 or IL&FS 2018-09-21) into `PaperTracker`. No code until task 1.3a data exists.

**Key milestones (full spec in [BACKTEST_PLAN_PHASE1.md](BACKTEST_PLAN_PHASE1.md)):**
- **1.3a** — Nifty 50 + NiftyBees OHLC Parquet; derived: ATR-14, slope-50, SMA-10M, VIX rank-252.
- **1.3b** — TrueData 1-min options ingest (~1.5 GB for 2022–2024; start after zip delivery).
- **1.4** — `BacktestEngine` core (Strategy Protocol + DayContext + run loop).
- **1.5** — `BacktestStore` (`src/backtest/store.py`); `src/analytics/` (trade metrics, B2.1/B2.2) tracked separately under its own numbering — full spec: [docs/plan/backtest-eval-core/](docs/plan/backtest-eval-core/).
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

Full forensic log (SHAs, bug numbers, root-cause detail) moved to
[docs/archive/TODOS_ARCHIVE.md](docs/archive/TODOS_ARCHIVE.md) during the 2026-07-27 reorg —
add new entries there going forward, or start a fresh dated section here if this file's
Session Log grows large again.

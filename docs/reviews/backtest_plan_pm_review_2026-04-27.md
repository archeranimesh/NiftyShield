# NiftyShield BACKTEST_PLAN.md — PM/Architect Critical Review

**Date:** 2026-04-27
**Reviewer posture:** Senior PM + hands-on system architect
**Inputs:** `CONTEXT.md`, `BACKTEST_PLAN.md`, `DECISIONS.md`, `TODOS.md`

---

## 0. Explicit Assumptions

**Scale:**
- Data volume: ~4M rows EOD options (8 years NSE Bhavcopy), ~500K underlying OHLC rows, ~75K intraday chain snapshots/year. All comfortably within Parquet + SQLite. No distributed infra needed.
- Throughput: batch-only. No real-time order execution until static IP provisioned (constraint acknowledged). Cron-driven at 5-min and EOD cadences.
- Latency: irrelevant for Phase 0–1. Becomes relevant only at Phase 2 live deployment, and even then only for order placement (manual fallback exists).

**Users:** Single operator (Animesh). No multi-tenancy, no UI beyond CLI + Telegram. No concurrent access concerns.

**Infrastructure:** Single machine, Python 3.10+, SQLite, Parquet on local disk. No cloud deployment until explicitly needed. Docker only if TimescaleDB resurrects (unlikely per DECISIONS.md).

**Team size:** 1 human + AI pair. All code work is Cowork-delegated; all strategy decisions are human-owned. This is the correct separation.

**Capital at risk:** ~₹10L deployed (Finideas), CSP paper trading at 1-lot Nifty (~₹2L margin). Total MF portfolio ~₹80L+. The protective strategy (NiftyShield integrated) is the higher-stakes bet in terms of portfolio coverage gap.

| Input gap | Classification | Action |
|---|---|---|
| Upstox rate limits under 5-min chain snapshot load | Assumption | 225 calls/day estimated; monitor, no blocker |
| NSE Bhavcopy CDN reliability for 8-year bulk download | Assumption | Resumable design handles it; test with 1-month sample first |
| Stockmock UI output format (no API) | Deferrable | Manual transcription into spec; structured capture is post-MVP |
| Order execution (static IP) | Blocker for Phase 2 live | Manual order entry is the fallback; does not block Phase 0–1 |

---

## 1. Critical Review

### What's good (earned, not flattery)

The plan's central insight — **paper trade before you backtest, then calibrate the backtest against paper reality** — is architecturally sound and rare in retail quant projects. The variance check (task 1.11) with Z-score methodology and explicit bias subtraction is the strongest section. The kill criteria are quantified upfront, not retrofitted. TimescaleDB deferral was the right call.

### Weaknesses and risks

**1a. Scope creep disguised as thoroughness.** The plan spans 4–5 years and 4 phases with ~50 tasks across 3 parallel research tracks. For a single-operator system, this is a product roadmap pretending to be a build plan. The risk: cognitive overload causes Phase 0 to drag, Phase 1 never starts, and the entire system remains a monitoring tool for Finideas.

- **What to remove:** Phase 2 Track A (Swing Strategy Pipeline — tasks 2.S0 through 2.S7) and Track B (Investment Strategy Pipeline — tasks 2.I0 through 2.I5). These are research explorations, not execution tasks. They belong in a separate `RESEARCH_BACKLOG.md`, not in the build plan's critical path.
- **Why:** They share zero code dependencies with the CSP/IC pipeline (Track A needs a points-based backtester and regime engine that the options backtest engine doesn't use; Track B is NiftyBees allocation, orthogonal to options selling). Including them inflates the plan's apparent complexity and creates false parallelism — a single operator cannot run 3 tracks.
- **Cost of keeping:** Every planning session spends 30% of cognitive budget on tracks that won't execute for 12+ months. The plan file is already 1100 lines and growing.

**1b. The 6-month paper trading gate (0.6/0.6a) is calendar risk, not complexity risk.** Phase 0 requires 6 monthly CSP cycles + 2 quarterly tail put cycles + 1 Finideas roll. The earliest Phase 1 can start is ~November 2026 (6 months from first paper trade entry ~May 2026). This is fine — but the plan doesn't acknowledge that the code work for Phase 1 (tasks 1.3, 1.3a, 1.4, 1.5, 1.6, 1.6a) can start in parallel with the paper trading observation period. The gate is on data accumulation, not on code readiness.

- **Recommendation:** Explicitly split Phase 0 into Phase 0-code (done) and Phase 0-observe (calendar-bound). Allow Phase 1 code tasks to start once 0.1, 0.2, 0.5, 0.7 are complete (they already are). The gate at 0.8 remains for the variance check, but the code pipeline isn't blocked.

**1c. NiftyShield integrated strategy (0.4a, 0.6a, 1.9, 1.9a) is premature scope.** The integrated strategy adds protective put spreads + tail puts on top of CSP. It requires a synthetic pricer (1.9), parametric vol skew model, and a separate backtest run (1.9a). This triples Phase 1's code surface area for a strategy that hasn't been paper-traded yet (0.6a hasn't started).

- **What to defer:** Tasks 1.9, 1.9a to Phase 2. Paper trade the integrated strategy (0.6a) during Phase 0-observe in parallel, but don't build the synthetic pricing infrastructure until CSP-alone is validated.
- **Why:** The CSP is the income engine. The protective legs are insurance. Building the insurance backtest before the income engine is validated is solving the wrong problem first. If CSP fails the variance check, the integrated strategy is moot.
- **Cost of keeping:** ~3 weeks of code work (skew model, synthetic pricer, integrated backtest) that may be invalidated by CSP variance check results.

**1d. The 5-minute intraday chain snapshot (1.10a) is over-engineering for Phase 1.** 225 API calls/day, 75K Parquet files/year, for a bias measurement that could be done with EOD snapshots (1.10) + a handful of manual intraday samples during paper trading.

- **What to defer:** Task 1.10a to Phase 2, when you actually have live positions and intraday delta monitoring matters.
- **Cost of keeping:** Operational noise (cron failures, disk growth, rate limit contention with other scripts) for marginal statistical improvement in the bias estimate.

**1e. No explicit data validation checkpoint before building the backtest engine.** Task 1.3 (Bhavcopy ingest) feeds 1.4 (engine) feeds 1.7 (CSP strategy) feeds 1.8 (full-history run). If Bhavcopy data has systematic issues (missing strikes, incorrect settle prices, gaps during stress windows), you discover it late — during the 1.8 run or worse, during the 1.11 variance check.

- **Recommendation:** Add a standalone data quality audit task between 1.3 and 1.4. Run distribution checks: settle_price non-zero rates, strike coverage per expiry, OI sanity, gap detection. Compare a sample month against Stockmock output (1.1). This is a 1-day task that saves weeks of debugging.

**1f. The Iron Condor port (1.6) is dead weight in Phase 1.** It's described as a "scaffolding port" and "engine validation exercise." The engine can be validated with CSP alone (1.7). The IC doesn't get a spec until Phase 2.3, doesn't get paper-traded until 2.6. Porting it in Phase 1 is premature.

- **What to defer:** Task 1.6 to Phase 2, between 2.3 (IC spec) and 2.4 (IC implementation).
- **Cost of keeping:** ~1 week of code work that sits untouched for 6+ months, accumulating staleness.

**1g. India-specific market microstructure issues are unaddressed — these will break backtest accuracy (Critical).** Three implementation-breaking gaps the original review missed:

- **Bhavcopy settle price ≠ tradable price.** NSE Bhavcopy uses a 30-minute VWAP (3:00–3:30 PM) for settlement, not 3:30 PM LTP. Upstox EOD snapshots capture LTP. If a sharp move occurs at 3:25 PM, IV reconstructed from Bhavcopy diverges materially from live Greeks. In task 1.6a, validate the BS model against Upstox EOD snapshot data (synchronised spot + option LTP), not against Bhavcopy. Use Bhavcopy for broad strike selection only — and document explicitly that it carries VWAP smoothing.
- **Historical lot size changes.** Nifty lot sizes changed: 75 → 50 → 25 across the 8-year backtest window. Assuming lot size = 25 for 2018 data makes ROI calculations, margin math, and absolute P&L distributions invalid — and makes the variance check (1.11) structurally unfair against 2026 paper trades. Add "Historical Lot Size Mapping" to task 1.3-QA; the engine must dynamically resolve lot size by date.
- **Expiry-day STT trap.** A short put expiring ITM incurs STT at 0.125% on intrinsic value, versus 0.0625% on premium if squared off by 3:15 PM. This silently destroys CSP backtest P&L in tail scenarios. Enforce in strategy spec (1.7): always square off ITM options by 3:15 PM on expiry day; never allow physical settlement. Penalise ITM expiration in the cost model.

**1h. Sprint timeline is optimistic for a solo operator.** 8 weeks for Sprints 1–4 assumes near-daily Cowork sessions with no friction. A single operator with a day job, NSE bulk downloads requiring politeness delays (~2–3 hours unattended), and first-attempt IV reconstruction edge cases (negative time value, dividend effects, weekly vs monthly expiry transitions) will absorb at least 2–4 extra weeks.

- **Revised estimate:** Sprints 1–4 should be budgeted at 10–12 weeks total.
- **Impact:** None on the critical path — the month 6–7 paper trading gate doesn't move. This slack prevents false urgency that causes corners to be cut.

---

## 2. MVP Definition

### Primary user
Animesh — single retail trader running a CSP strategy on Nifty 50 index options, validated against historical data, with continuous drift detection.

### Core value delivered
A backtested, paper-validated, variance-checked CSP strategy running live at 1 lot, with automated weekly drift detection that alerts before the strategy silently fails.

### Success metrics

| Metric | Target |
|---|---|
| Paper trade cycles completed | ≥ 6 monthly, all 3 exit types triggered |
| Backtest coverage | 2016–present (8 years, includes COVID + IL&FS) |
| Variance check | \|Z\| ≤ 1.5 (bias-adjusted) |
| Continuous re-validation | Weekly, no missed runs for 3+ months |
| Time to first live trade | ≤ 14 months from plan activation (Apr 2026) |

### Acceptance criteria (binary, testable)

1. `scripts/bhavcopy_bootstrap.py` ingests NIFTY options 2016–present into Parquet with <5% missing ATM±5 strikes per monthly expiry.
2. `src/backtest/engine.py` runs CSP strategy across full history, producing per-month P&L with realistic Indian options cost model.
3. Backtest monthly P&L distribution matches paper-trade distribution within ±1.5 SD (Z-score, bias-adjusted).
4. `src/backtest/continuous.py` runs weekly, computes rolling Z-score, alerts via Telegram when |Z| > 1.5 for 3 consecutive weeks.
5. Live CSP trade recorded via `record_trade.py`, tracked in `daily_snapshots`, mark-to-market operational.

### Non-goals (explicit)

- Iron Condor implementation (Phase 2)
- NiftyShield integrated strategy backtest (Phase 2)
- Swing strategy pipeline (separate backlog)
- Investment strategy pipeline (separate backlog)
- Intraday chain snapshots at 5-min cadence (Phase 2)
- ML overlays of any kind (Phase 4)
- Automated order execution (blocked by static IP; manual fallback is acceptable)
- Multi-strategy portfolio attribution (Phase 3)

### MVP kill criteria
- **Win rate threshold:** After 6 paper trade cycles, ≤33% win rate (≤2 wins in 6) OR realised max monthly loss exceeds 2× the backtest-predicted max loss for the same market regime → full strategy review before proceeding to live. The original "<40% win rate" is statistically too aggressive: a correctly functioning 25-delta CSP has ~17% probability of ≤3 wins in 6 trials just by chance.
- **Month 3 checkpoint:** If 0 wins in first 3 cycles → pause paper trading immediately and investigate strike/timing selection. Don't wait 6 months to detect a systematic setup error.
- **Max drawdown:** >8% of deployed capital → re-evaluate strategy parameters. Regime-independent; unchanged.
- **Engine build is not blocked by poor early paper results.** Foundational infra (1.3, 1.3-QA, 1.3b, 1.4, 1.5, 1.6a) continues regardless. Only strategy-specific work (1.7, 1.8) gates on catastrophic paper failure. If performance is poor but explainable (e.g., entered during a high-vol regime), proceed — the engine is the diagnostic tool that explains why.
- **Data quality contingency:** If the Bhavcopy audit shows >10% gaps in stress windows but <5% in normal periods → proceed with partial backtest (2021–present, ~5 years) + use Stockmock output for 2016–2020 stress-period calibration. Re-evaluate full-engine value after 3 months of EOD snapshot accumulation. If gaps exceed 10% across all periods: Stockmock remains the sole tool.

---

## 3. Ruthless Prioritisation

### Must-have (MVP)

| Task | Justification |
|---|---|
| 0.3 — Finideas roll cycle | Operational necessity (hard deadline Jun 2026) |
| 0.6 — Paper trade CSP (6 cycles) | Validation data for the entire pipeline |
| 1.1 — Stockmock calibration | Establishes thresholds before code; zero code cost |
| 1.3 — Bhavcopy ingest | Foundation for programmatic backtest |
| **NEW: 1.3-QA — Data quality audit** | Catch data issues before building engine; includes historical lot size mapping and POC 1 validation (4–5 sample months, not just March 2020) |
| **NEW: 1.3b — Trading Calendar + Expiry Resolver** | Prevents subtle engine bugs: weekly/monthly expiry transitions (Nifty mid-2019 onward), holiday-shifted dates, lot size by date, strike interval by Nifty level — 1–2 day task |
| 1.3a — Underlying OHLC ingest | VIX for R3, Nifty spot for IV reconstruction |
| 1.4 — Backtest engine port | Core infrastructure |
| **NEW: 1.4a — Golden fixture dataset** | Regression test backbone: 1 normal month (Jul 2021), 1 volatile month (Mar 2020), 1 expiry week — strike selection, trade lifecycle, and P&L hand-calculated; without this, full-history run changes are untestable |
| 1.5 — Backtest results storage | Reproducibility; every run records `git_commit`, `strategy_spec_hash`, `data_version`, `cost_model_version`, `run_timestamp` — re-run with identical inputs must produce bit-identical P&L |
| 1.6a — BS IV reconstruction + Greeks | Strike selection in backtest; validate against Upstox EOD LTP (not Bhavcopy VWAP) — this is the POC 3 acceptance test |
| 1.7 — CSP strategy implementation | The strategy under test; must enforce ITM square-off by 3:15 PM on expiry day and penalise ITM expiration in cost model |
| 1.8 — Full-history CSP backtest (3 variants) | Generates the distribution to validate against |
| 1.10 — EOD chain snapshot | Forward data capture; cannot be back-filled; first 20 days is the POC 2 reliability test |
| 1.11 — Variance check | The gate |
| 2.1 — Continuous re-validation | The ongoing safety net |
| **NEW: 2.1a — Cron job healthcheck** | Daily script: did EOD snapshot produce today's file? Is it non-empty? Did daily_snapshot run? Telegram alert on failure. Silent data gaps are unfixable — more critical than dashboards for a solo system |

### Post-MVP (Phase 2, after variance check passes)

| Task | Rationale for deferral |
|---|---|
| 1.6 — IC port | No spec, no paper data, pure scaffolding |
| 1.9 — Synthetic pricer | Integrated strategy not validated yet |
| 1.9a — Integrated backtest | Depends on 1.9; premature |
| 1.10a — Intraday snapshots | EOD sufficient for Phase 1 bias measurement |
| 2.2–2.7 — CSP live + IC pipeline | Sequenced after variance gate |

### Nice-to-have (deferred indefinitely)

| Task | Rationale |
|---|---|
| Track A (2.S0–2.S7) — Swing strategies | Separate research track; zero dependency on CSP pipeline |
| Track B (2.I0–2.I5) — Investment strategies | Separate research track; orthogonal to options selling |
| Phase 3 — Portfolio construction | Requires 3 live strategies; years away |
| Phase 4 — ML overlays | Correctly deferred in the plan already |

---

## 4. Proofs of Concept (POCs)

These POCs are not standalone tasks — each is consolidated into the acceptance criteria of its corresponding implementation task. This saves ~1 week and ensures validation is embedded in delivery, not deferred to a separate phase.

### POC 1: NSE Bhavcopy data quality for delta-based strike selection
- **Consolidated into:** Task 1.3-QA (data quality audit)
- **Uncertainty:** Can Bhavcopy settle_price + BS IV reconstruction reliably identify 25-delta strikes across 8 years of history, including stress windows?
- **Why it cannot be assumed:** Settle prices for OTM strikes may be exchange-theoretical, not traded. COVID week data may have gaps.
- **Success criteria:** For 4–5 sample months (include Sept 2018, a weekly-expiry transition month, March 2020, and a boring month), reconstructed 25-delta strike matches the ATM-offset that Stockmock selects within ±1 strike width. March 2020 alone is insufficient — validate across regime types.
- **Decision unlocked:** Whether to proceed with the programmatic engine or fall back to Stockmock-only calibration.

### POC 2: Upstox EOD chain snapshot reliability
- **Consolidated into:** Task 1.10 Sprint 1 deliverable — the first 20 days of cron operation is the reliability test.
- **Uncertainty:** Does the Upstox Analytics Token reliably return full chain data (Greeks, bid/ask, OI) at 3:30 PM IST daily?
- **Why it cannot be assumed:** Rate limits, API uptime, and data freshness at near-close are untested at cron cadence.
- **Success criteria:** 20 consecutive trading days with complete chain data (no missing Greeks, no HTTP errors).
- **Decision unlocked:** Whether 1.10 can run unattended or needs retry/fallback logic.

### POC 3: BS IV reconstruction accuracy vs live Upstox Greeks
- **Consolidated into:** Task 1.6a acceptance test — validate against live Upstox data as part of implementation.
- **Uncertainty:** The documented 0.5–2 delta point bias between BS-reconstructed and Upstox-reported deltas. Additional uncertainty: Bhavcopy uses 30-minute VWAP settle prices (3:00–3:30 PM), while Upstox captures 3:30 PM LTP — these diverge on volatile close days.
- **Why it cannot be assumed:** The bias magnitude determines whether the variance check (1.11) can pass at all.
- **Success criteria:** On 5 trading days, compare BS-reconstructed delta for the 25-delta strike against Upstox live delta, using Upstox EOD LTP (not Bhavcopy settle_price) as the pricing input. Bias ≤ 2 delta points for 4/5 days.
- **Decision unlocked:** Whether `r` calibration is sufficient or a more sophisticated IV model is needed.

---

## 5. Fail-Fast Risk Surfacing

| # | Risk | Impact | Likelihood | Why it matters | Early validation | Earliest detection |
|---|---|---|---|---|---|---|
| 1 | Paper trade CSP shows ≤2 wins in 6 cycles or triggers kill criteria | H | M | Entire backtest engine build is predicated on CSP being viable | Stockmock calibration (1.1) gives directional read; month-2 interim Z-check (N=2) catches architectural bugs early | Month 2 interim check (~Jul 2026); Month 3 checkpoint if 0 wins (~Aug 2026) |
| 2 | Bhavcopy data gaps in stress windows (COVID Mar 2020, IL&FS Sep 2018) | H | M | Backtest results in stress windows are the plan's primary value; gaps invalidate them | 1.3-QA data quality audit across 4–5 sample months | Within 1 week of starting 1.3 |
| 3 | BS IV reconstruction bias > 3 delta points, making variance check structurally impossible | H | L | \|Z\| ≤ 1.5 threshold may be unachievable if the measurement instrument is broken; aggravated by Bhavcopy VWAP vs Upstox LTP divergence on volatile close days | POC 3 embedded in 1.6a (5-day comparison vs Upstox EOD LTP) | First week of 1.6a implementation |
| 4 | Calendar risk: 6-month paper observation delays Phase 1 code deployment | M | H | No code mitigation possible — it's a waiting game | Start Phase 1 code in parallel (recommendation 1b) | Already known — plan for it |
| 5 | Upstox Analytics Token rate limits under combined cron load (EOD snapshot + daily_snapshot + intraday) | M | L | Silent data gaps in forward capture | POC 2 embedded in 1.10 (20-day reliability test); 2.1a healthcheck detects failures within 24h | First 2 weeks of 1.10 deployment |
| 6 | Historical lot size mismatch (75 → 50 → 25) invalidates 2016–2022 P&L and margin calculations | H | H | Makes variance check (1.11) structurally unfair against 2026 paper trades | Historical lot size mapping added to 1.3-QA and 1.3b | During 1.3-QA before engine build |
| 7 | Expiry-day STT trap silently destroys P&L in tail scenarios | M | M | 0.125% on intrinsic value vs 0.0625% on premium — a 2× cost difference that compounds across backtested ITM expiries | STT rule enforced in strategy spec (1.7) and cost model | During 1.7 implementation review |

---

## 6. SDLC Validation (MVP only)

### Requirements clarity
Strong. Strategy spec (csp_nifty_v1.md) with all required sections exists and passes validator. Backtest cost model components are enumerated with specific percentages. Variance threshold is quantified (|Z| ≤ 1.5).

Gap 1: No explicit requirement for how fast the backtest engine must run. If a full 8-year CSP backtest takes >30 minutes, iterative debugging becomes painful. Add a non-functional requirement: full-history CSP run completes in <5 minutes on a single core.

Gap 2: No reproducibility requirement. Add: every backtest run must record `git_commit` hash, `strategy_spec_hash` (config YAML checksum), `data_version` (Parquet file checksums or date range), `cost_model_version`, and `run_timestamp`. Re-running with identical inputs must produce bit-identical P&L output. This is essential for debugging variance check failures — you must be able to distinguish "I fixed a bug" from "the data changed under me."

Gap 3: The variance check (1.11) currently treats |Z| ≤ 1.5 as binary pass/fail. Add graduated deployment tiers:

| Z-score range | Confidence | Deployment posture |
|---|---|---|
| \|Z\| ≤ 0.5 | High | Full planned size |
| 0.5 < \|Z\| ≤ 1.0 | Moderate | Full size, weekly monitoring |
| 1.0 < \|Z\| ≤ 1.5 | Low | Half size, daily monitoring for first month |
| \|Z\| > 1.5 | Fail | No deploy; run 2 debug variants (bias-adjusted, parameter-tuned) before re-gate |

Post-live monitoring triggers (feeds into 2.1): |Z| 1.5–2.0 for 3 consecutive weeks → reduce to paper-only until Z returns below 1.0; |Z| > 2.0 single week → halt all live trading; |Z| < 1.0 for 4 consecutive weeks after breach → resume normal size.

### High-level design
Sound. BrokerClient protocol for dependency injection. Parquet for time-series, SQLite for relational. Decimal invariant enforced. The engine port from quant-4pc-local is a known quantity.

### Data flow and interfaces
Bhavcopy CSV → parse → Parquet (1.3) → engine reads Parquet + joins Nifty spot from 1.3a → IV reconstruction (1.6a) → strike selection → strategy logic (1.7) → daily P&L → SQLite results (1.5) → variance check SQL (1.11). Clean, linear, testable at each boundary.

### Dev phases
Phase 0 code: DONE (0.1, 0.2, 0.5, 0.7 complete). Phase 0 observe: in progress (0.6 started).
Phase 1 code: ready to start (no code blockers).
Recommended parallel split: Phase 1 code starts now; Phase 0 gate (0.8) evaluated when paper data matures.

### Testing
976 tests passing. Pattern established: fixture-driven, no network, happy-path + edge-case per public function. Backtest engine tests should follow the same pattern.

Golden fixture dataset (task 1.4a): create a small, manually-verified test dataset covering 1 normal month (July 2021), 1 volatile month (March 2020), and 1 expiry week in detail — with expected strike selection, trade lifecycle, and P&L hand-calculated. This is the regression backbone. Without it, full-history runs are untestable — a 3% P&L change after a refactor is indistinguishable from a bug fix vs a regression. Integration tests run against this fixture, not 8 years of history.

### Deployment
Cron-based. No containerisation needed. Scripts run on Animesh's machine. Telegram for alerts. Sufficient for single-operator.

### Monitoring and observability
Daily snapshots + Telegram notifications already operational. Continuous re-validation (2.1) adds weekly Z-score monitoring. Missing: cron job health monitoring — formalized as task 2.1a. A daily script checks whether the EOD snapshot (1.10) produced today's file, whether daily_snapshot ran, and whether files are non-empty; Telegram alert on any failure. For a solo system with no cloud redundancy, silent data gaps in forward capture are unfixable — this is more operationally critical than any dashboard.

### Feedback loops
Paper trade → backtest → variance check → live → continuous re-validation. This is the plan's strongest structural element. The re-backtest-over-paper-window step (1.11) closes the loop that most retail quant projects leave open.

---

## 7. Build vs Buy

| Component | Decision | Rationale |
|---|---|---|
| Backtest engine | BUILD (port from quant-4pc) | Already designed; porting is cheaper than integrating a generic framework (Zipline, Backtrader) that doesn't handle Indian options costs or Decimal invariant |
| BS IV reconstruction | BUILD | scipy.optimize.brentq + scipy.stats.norm — 50 lines of pure math. No library needed. |
| Options cost model | BUILD | Indian-specific (STT, exchange charges, SEBI fee, stamp duty). No library covers this correctly. |
| Bhavcopy parser | BUILD | NSE-specific CSV format. No library. |
| Parquet storage | BUY (pyarrow) | Standard library; don't reinvent |
| Strategy spec validator | BUILD (done) | 28 tests, simple script. Correct call. |
| Stockmock backtesting | BUY (already subscribed) | UI-only, no API. Use as calibration reference, not as engine. |
| TimescaleDB | DO NOT BUY | Correctly deferred. Parquet + SQLite sufficient for EOD volumes. |
| DhanHQ Data API | DO NOT BUY | Correctly rejected. Insufficient historical depth. |
| TrueData | DO NOT BUY | Correctly rejected. 6-month depth, no historical Greeks. |
| Continuous re-validation | BUILD | Simple: weekly cron, SQL query, Z-score computation, Telegram alert. No framework needed. |

---

## 8. Execution Structure

### Sequential (blocking)

```
1.1 (Stockmock calibration, Animesh) ──blocks──▶ 1.7 (CSP config thresholds)
1.3 (Bhavcopy ingest) ──blocks──▶ 1.3-QA (data audit + lot size mapping) ──blocks──▶ 1.4 (engine)
1.3b (trading calendar + expiry resolver) ──blocks──▶ 1.4 (engine)
1.3a (OHLC ingest) ──blocks──▶ 1.6a (IV reconstruction) ──blocks──▶ 1.7 (CSP strategy)
1.4 (engine) + 1.4a (golden fixtures) + 1.5 (store + lineage) + 1.6a (Greeks) ──all block──▶ 1.7
1.7 ──blocks──▶ 1.8 (full run) ──blocks──▶ 1.11 (variance check) ──blocks──▶ 2.1 (continuous)
0.6 (paper trading, 6 cycles) ──blocks──▶ 1.11 (variance check)
```

### Parallelisable

```
1.3 (Bhavcopy) ║ 1.3a (OHLC) ║ 1.10 (EOD snapshot) — all independent data pipelines
1.4 (engine) ║ 1.5 (store) — engine and storage can be built concurrently
0.6 (paper trading) ║ 1.3 + 1.3a + 1.4 + 1.5 + 1.6a — code and observation in parallel
1.1 (Stockmock, Animesh) ║ 1.3 (Bhavcopy, Cowork) — different owners, no dependency
```

### Critical path

**0.6 (paper trading, 6 months)** is the critical path item. Everything else can be built faster than the paper trading window accumulates data. The plan's bottleneck is calendar time, not engineering time.

Secondary critical path: **1.3 → 1.3-QA → 1.3b → 1.4 → 1.4a → 1.7 → 1.8 → 1.11**. This is the code critical path. Estimated: 8–10 weeks of Cowork sessions (was 6–8; revised for single-operator pace and India-specific complexity).

### Bottlenecks

1. **Animesh's time** — Stockmock calibration (1.1), paper trade entries (0.6), Finideas roll (0.3), and strategy decisions are all human-only. These cannot be parallelised with each other.
2. **NSE Bhavcopy bulk download** — 8 years × ~250 trading days = ~2000 ZIP downloads with politeness delay. Estimate: 2–3 hours unattended. Not a real bottleneck, but must run before 1.4 can validate.

---

## 9. Final Execution Plan

### Immediate (this week, unblocked)

| Task | Owner | Outcome | Rationale |
|---|---|---|---|
| 0.3 pre-check: run `roll-validator` agent | Cowork | Position state verified for Jun 2026 roll | Hard deadline approaching; de-risk early |
| 0.6: enter first CSP paper trade | Animesh | First cycle started; clock ticking on 6-month gate | Calendar-critical; every day of delay pushes Phase 1 |
| 1.1: run Stockmock COVID + IL&FS backtests | Animesh | Calibration thresholds for CSP config | Unblocked; informs 1.7 config before code exists |

### Sprint 1 (weeks 1–3): Data pipelines + infra (parallelisable)

| Task | Owner | Outcome |
|---|---|---|
| 1.3 — Bhavcopy ingest module + bootstrap CLI | Cowork | NIFTY options 2016–present in Parquet |
| 1.3a — Underlying OHLC ingest (Nifty, VIX, NiftyBees) | Cowork | Daily + 15-min candles in Parquet |
| **1.3b — Trading Calendar + Expiry Resolver** | Cowork | Weekly/monthly expiry transitions, holiday shifts, lot size by date, strike interval by Nifty level — blocks engine build |
| 1.10 — EOD chain snapshot cron | Cowork | Forward data capture begins; cannot be back-filled; first 20 days is the POC 2 reliability test |
| **2.1a — Cron job healthcheck + Telegram alert** | Cowork | Daily file-existence check; silent gaps detected within 24h |

**Trade-off:** Starting 1.3, 1.3a, 1.3b in parallel with paper trading (0.6) means Phase 1 code is ready before the Phase 0 gate closes. If CSP paper trading fails badly, the data pipelines are still useful for any future strategy. Downside: ~2–3 weeks of code work potentially wasted if the project is abandoned entirely.

### Sprint 2 (weeks 3–5): Data quality + engine foundation

| Task | Owner | Outcome |
|---|---|---|
| **1.3-QA — Data quality audit** | Cowork | Bhavcopy stress-window coverage confirmed; historical lot size mapping verified; 4–5 sample months including Sept 2018 and a weekly-expiry transition month (POC 1 validation embedded) |
| 1.4 — Backtest engine port | Cowork | Engine running on fixture data |
| **1.4a — Golden fixture dataset** | Cowork | Jul 2021 (normal), Mar 2020 (volatile), 1 expiry week — hand-calculated expected P&L; regression test backbone |
| 1.5 — Backtest results storage | Cowork | SQLite schema for reproducible runs; run lineage metadata: `git_commit`, `strategy_spec_hash`, `data_version`, `cost_model_version`, `run_timestamp` |

### Sprint 3 (weeks 5–7): Greeks + strategy

| Task | Owner | Outcome |
|---|---|---|
| 1.6a — BS IV reconstruction + Greeks | Cowork | Delta-based strike selection operational; validated against Upstox EOD LTP on 5 live days (POC 3 embedded); bias ≤ 2 delta points for 4/5 days |
| 1.7 — CSP strategy implementation (V1/V2/V3 configs) | Cowork | Strategy code matching spec line-for-line; ITM square-off by 3:15 PM enforced; STT trap handled in cost model |

### Sprint 4 (weeks 7–10): Full run + results

| Task | Owner | Outcome |
|---|---|---|
| 1.8 — Full-history CSP backtest (3 variants) | Cowork + Animesh review | 8-year P&L distributions for V1/V2/V3 |
| Cross-reference 1.8 results against 1.1 Stockmock calibration | Animesh | Directional consistency check |

### Month 2 interim check (~8 weeks into paper trading)

After 2 complete paper cycles, run an informal Z-score comparison. N=2 is too small for a go/no-go decision, but sufficient to catch architectural bugs. If |Z| > 3.0, something is fundamentally broken in the measurement chain (e.g., wrong lot size, flipped slippage sign) — debug immediately, don't wait 4 more months.

### Gate (month 6–7, after paper trading completes)

| Task | Owner | Outcome |
|---|---|---|
| 1.11 — Variance check (paper vs backtest) | Animesh + Cowork compute | Z-score result determines deployment posture (see tiers in §6) |
| Phase 1 gate (1.12) | Animesh sign-off | Deployment posture set: full size / half size / no deploy |

### Post-gate (Phase 2 start)

| Task | Owner | Outcome |
|---|---|---|
| 2.1 — Continuous re-validation loop | Cowork | Weekly Z-score monitoring operational |
| 2.2 — Deploy CSP live (1 lot) | Animesh | First real trade |

---

## 10. Visual Execution Diagram

See inline widget rendered in conversation.

---

## Summary of Recommendations

1. **Start Phase 1 code now.** The paper trading observation period (0.6) is the true bottleneck. Don't let code work wait for calendar time.
2. **Add a data quality audit (1.3-QA)** between Bhavcopy ingest and engine build. One day of validation saves weeks of debugging. Include historical lot size mapping (75 → 50 → 25) and validate across 4–5 sample months.
3. **Defer IC port (1.6), synthetic pricer (1.9/1.9a), and intraday snapshots (1.10a)** to Phase 2. They add scope without validating the core CSP hypothesis.
4. **Move Track A and Track B** out of BACKTEST_PLAN.md into a separate research backlog. They inflate the plan without contributing to the MVP.
5. **Consolidate POCs into implementation acceptance criteria.** POC 1 → 1.3-QA, POC 2 → 1.10, POC 3 → 1.6a. Saves ~1 week and ensures validation is embedded in delivery.
6. **The critical path is calendar time, not engineering time.** Optimise for starting paper trading immediately and building code in parallel.
7. **Fix India-specific microstructure gaps before writing engine code:** validate IV reconstruction against Upstox EOD LTP (not Bhavcopy VWAP), implement historical lot size resolution in 1.3b, and enforce the expiry-day STT rule in strategy spec (1.7) and cost model. All three are implementation-breaking if missed.
8. **Add 1.3b (Trading Calendar + Expiry Resolver) to Sprint 1.** Nifty weekly/monthly expiry transitions, holiday-shifted dates, and strike interval changes are not optional edge cases — they are the normal operating conditions of the backtest window.
9. **Replace binary variance gate with graduated deployment tiers** (see §6 Requirements clarity). |Z| ≤ 1.5 is not a pass/fail — it's a spectrum that determines position sizing and monitoring intensity.
10. **Run a month-2 interim Z-check** after 2 paper cycles. No go/no-go decision, but |Z| > 3.0 at N=2 means something is architecturally wrong — catch it 4 months early.

### What NOT to adopt (council rejections)

| Suggestion | Reason |
|---|---|
| Move EOD snapshot to cloud | Conflicts with local-first assumption; adds operational complexity prematurely |
| Partially reinstate IC port in Phase 1 | Deferral logic is stronger; engine validates with CSP alone |
| Shorten critical path to 5–7 weeks | Unrealistic for solo operator |
| Full variance decomposition (4 bias types) | Premature for MVP; keep bias-adjusted Z-score simple |
| Assumptions register as a separate file | Process overhead for 1-person team; capture inline in DECISIONS.md |

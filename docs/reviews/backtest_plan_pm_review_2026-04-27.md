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
- If after 6 paper trade cycles, CSP shows <40% win rate or max drawdown >8% of deployed capital: re-evaluate strategy parameters before building the backtest engine. The engine is only worth building if the strategy has survival potential.
- If the Bhavcopy data quality audit (proposed task) shows >10% missing/suspect data in stress windows: Stockmock remains the sole backtest tool; programmatic engine is not worth the investment.

---

## 3. Ruthless Prioritisation

### Must-have (MVP)

| Task | Justification |
|---|---|
| 0.3 — Finideas roll cycle | Operational necessity (hard deadline Jun 2026) |
| 0.6 — Paper trade CSP (6 cycles) | Validation data for the entire pipeline |
| 1.1 — Stockmock calibration | Establishes thresholds before code; zero code cost |
| 1.3 — Bhavcopy ingest | Foundation for programmatic backtest |
| **NEW: 1.3-QA — Data quality audit** | Catch data issues before building engine |
| 1.3a — Underlying OHLC ingest | VIX for R3, Nifty spot for IV reconstruction |
| 1.4 — Backtest engine port | Core infrastructure |
| 1.5 — Backtest results storage | Reproducibility |
| 1.6a — BS IV reconstruction + Greeks | Strike selection in backtest |
| 1.7 — CSP strategy implementation | The strategy under test |
| 1.8 — Full-history CSP backtest (3 variants) | Generates the distribution to validate against |
| 1.10 — EOD chain snapshot | Forward data capture; cannot be back-filled |
| 1.11 — Variance check | The gate |
| 2.1 — Continuous re-validation | The ongoing safety net |

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

### POC 1: NSE Bhavcopy data quality for delta-based strike selection
- **Uncertainty:** Can Bhavcopy settle_price + BS IV reconstruction reliably identify 25-delta strikes across 8 years of history, including stress windows?
- **Why it cannot be assumed:** Settle prices for OTM strikes may be exchange-theoretical, not traded. COVID week data may have gaps.
- **Success criteria:** For a sample month (e.g., March 2020), reconstructed 25-delta strike matches the ATM-offset that Stockmock selects within ±1 strike width.
- **Decision unlocked:** Whether to proceed with the programmatic engine or fall back to Stockmock-only calibration.

### POC 2: Upstox EOD chain snapshot reliability
- **Uncertainty:** Does the Upstox Analytics Token reliably return full chain data (Greeks, bid/ask, OI) at 3:30 PM IST daily?
- **Why it cannot be assumed:** Rate limits, API uptime, and data freshness at near-close are untested at cron cadence.
- **Success criteria:** 20 consecutive trading days with complete chain data (no missing Greeks, no HTTP errors).
- **Decision unlocked:** Whether 1.10 can run unattended or needs retry/fallback logic.

### POC 3: BS IV reconstruction accuracy vs live Upstox Greeks
- **Uncertainty:** The documented 0.5–2 delta point bias between BS-reconstructed and Upstox-reported deltas.
- **Why it cannot be assumed:** The bias magnitude determines whether the variance check (1.11) can pass at all.
- **Success criteria:** On 5 trading days, compare BS-reconstructed delta for the 25-delta strike against Upstox live delta. Bias ≤ 2 delta points for 4/5 days.
- **Decision unlocked:** Whether `r` calibration is sufficient or a more sophisticated IV model is needed.

---

## 5. Fail-Fast Risk Surfacing

| # | Risk | Impact | Likelihood | Why it matters | Early validation | Earliest detection |
|---|---|---|---|---|---|---|
| 1 | Paper trade CSP shows <40% win rate or triggers kill criteria before 6 cycles | H | M | Entire backtest engine build is predicated on CSP being viable | Stockmock calibration (1.1) gives directional read before paper data accumulates | Month 3 of paper trading (~Aug 2026) |
| 2 | Bhavcopy data gaps in stress windows (COVID Mar 2020, IL&FS Sep 2018) | H | M | Backtest results in stress windows are the plan's primary value; gaps invalidate them | POC 1 (sample month data quality audit) | Within 1 week of starting 1.3 |
| 3 | BS IV reconstruction bias > 3 delta points, making variance check structurally impossible | H | L | |Z| ≤ 1.5 threshold may be unachievable if the measurement instrument is broken | POC 3 (5-day comparison) | First week of 1.6a implementation |
| 4 | Calendar risk: 6-month paper observation delays Phase 1 code deployment | M | H | No code mitigation possible — it's a waiting game | Start Phase 1 code in parallel (recommendation 1b) | Already known — plan for it |
| 5 | Upstox Analytics Token rate limits under combined cron load (EOD snapshot + daily_snapshot + intraday) | M | L | Silent data gaps in forward capture | POC 2 (20-day reliability test) | First 2 weeks of 1.10 deployment |

---

## 6. SDLC Validation (MVP only)

### Requirements clarity
Strong. Strategy spec (csp_nifty_v1.md) with all required sections exists and passes validator. Backtest cost model components are enumerated with specific percentages. Variance threshold is quantified (|Z| ≤ 1.5).

Gap: No explicit requirement for how fast the backtest engine must run. If a full 8-year CSP backtest takes >30 minutes, iterative debugging becomes painful. Add a non-functional requirement: full-history CSP run completes in <5 minutes on a single core.

### High-level design
Sound. BrokerClient protocol for dependency injection. Parquet for time-series, SQLite for relational. Decimal invariant enforced. The engine port from quant-4pc-local is a known quantity.

### Data flow and interfaces
Bhavcopy CSV → parse → Parquet (1.3) → engine reads Parquet + joins Nifty spot from 1.3a → IV reconstruction (1.6a) → strike selection → strategy logic (1.7) → daily P&L → SQLite results (1.5) → variance check SQL (1.11). Clean, linear, testable at each boundary.

### Dev phases
Phase 0 code: DONE (0.1, 0.2, 0.5, 0.7 complete). Phase 0 observe: in progress (0.6 started).
Phase 1 code: ready to start (no code blockers).
Recommended parallel split: Phase 1 code starts now; Phase 0 gate (0.8) evaluated when paper data matures.

### Testing
976 tests passing. Pattern established: fixture-driven, no network, happy-path + edge-case per public function. Backtest engine tests should follow the same pattern. Integration test for the full CSP backtest run on a 1-month fixture dataset (not 8 years) to catch pipeline breaks.

### Deployment
Cron-based. No containerisation needed. Scripts run on Animesh's machine. Telegram for alerts. Sufficient for single-operator.

### Monitoring and observability
Daily snapshots + Telegram notifications already operational. Continuous re-validation (2.1) adds weekly Z-score monitoring. Missing: a simple dashboard or log aggregation for cron job health (did all 3 cron jobs run today?). Recommend a 1-line healthcheck script that verifies today's Parquet/SQLite rows exist.

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
1.3 (Bhavcopy ingest) ──blocks──▶ 1.3-QA (data audit) ──blocks──▶ 1.4 (engine)
1.3a (OHLC ingest) ──blocks──▶ 1.6a (IV reconstruction) ──blocks──▶ 1.7 (CSP strategy)
1.4 (engine) + 1.5 (store) + 1.6a (Greeks) ──all block──▶ 1.7
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

Secondary critical path: **1.3 → 1.3-QA → 1.4 → 1.7 → 1.8 → 1.11**. This is the code critical path. Estimated: 6–8 weeks of focused Cowork sessions.

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

### Sprint 1 (weeks 1–3): Data pipelines (parallelisable)

| Task | Owner | Outcome |
|---|---|---|
| 1.3 — Bhavcopy ingest module + bootstrap CLI | Cowork | NIFTY options 2016–present in Parquet |
| 1.3a — Underlying OHLC ingest (Nifty, VIX, NiftyBees) | Cowork | Daily + 15-min candles in Parquet |
| 1.10 — EOD chain snapshot cron | Cowork | Forward data capture begins; cannot be back-filled |

**Trade-off:** Starting 1.3 and 1.3a in parallel with paper trading (0.6) means Phase 1 code is ready before the Phase 0 gate closes. If CSP paper trading fails badly, the data pipelines are still useful for any future strategy. Downside: ~2 weeks of code work potentially wasted if the project is abandoned entirely.

### Sprint 2 (weeks 3–4): Data quality + engine foundation

| Task | Owner | Outcome |
|---|---|---|
| **1.3-QA — Data quality audit** | Cowork | Bhavcopy stress-window coverage confirmed |
| 1.4 — Backtest engine port | Cowork | Engine running on fixture data |
| 1.5 — Backtest results storage | Cowork | SQLite schema for reproducible runs |

### Sprint 3 (weeks 4–6): Greeks + strategy

| Task | Owner | Outcome |
|---|---|---|
| 1.6a — BS IV reconstruction + Greeks | Cowork | Delta-based strike selection operational |
| 1.7 — CSP strategy implementation (V1/V2/V3 configs) | Cowork | Strategy code matching spec line-for-line |

### Sprint 4 (weeks 6–8): Full run + results

| Task | Owner | Outcome |
|---|---|---|
| 1.8 — Full-history CSP backtest (3 variants) | Cowork + Animesh review | 8-year P&L distributions for V1/V2/V3 |
| Cross-reference 1.8 results against 1.1 Stockmock calibration | Animesh | Directional consistency check |

### Gate (month 6–7, after paper trading completes)

| Task | Owner | Outcome |
|---|---|---|
| 1.11 — Variance check (paper vs backtest) | Animesh + Cowork compute | Z-score ≤ 1.5 → proceed; > 1.5 → debug |
| Phase 1 gate (1.12) | Animesh sign-off | "Ready to go live" |

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
2. **Add a data quality audit (1.3-QA)** between Bhavcopy ingest and engine build. One day of validation saves weeks of debugging.
3. **Defer IC port (1.6), synthetic pricer (1.9/1.9a), and intraday snapshots (1.10a)** to Phase 2. They add scope without validating the core CSP hypothesis.
4. **Move Track A and Track B** out of BACKTEST_PLAN.md into a separate research backlog. They inflate the plan without contributing to the MVP.
5. **Run POC 1 (Bhavcopy data quality)** as the first output of task 1.3, before investing in the engine.
6. **The critical path is calendar time, not engineering time.** Optimise for starting paper trading immediately and building code in parallel.

---

## 11. Council Synthesis — Refinements and Additions (2026-04-30)

**Synthesis posture:** Multi-reviewer council pass. The original review's six recommendations stand. The twelve refinements below are layered on top. Items marked "What NOT to Adopt" are explicitly rejected.

---

### 11.1 India-Specific Market Microstructure Fixes (Critical)

These are implementation-breaking issues the original review missed.

**A. Bhavcopy Settle Price ≠ Tradable Price**

NSE Bhavcopy uses a 30-minute VWAP (3:00–3:30 PM) for settlement, not the LTP at close. Upstox EOD snapshot captures 3:30 PM LTP. If a sharp move occurs at 3:25 PM, the IV reconstructed from Bhavcopy will diverge materially from live Greeks.

Action: In POC 3 and task 1.6a, validate the BS model against Upstox EOD snapshot data (synchronised spot + option LTP), not against Bhavcopy. Use Bhavcopy for broad strike selection only, with an explicit note that it carries VWAP smoothing.

**B. Historical Lot Size Changes**

Nifty lot sizes changed: 75 → 50 → 25 over the 8-year backtest window. If the engine assumes lot size = 25 for 2018 data, ROI calculations, margin math, and absolute P&L distributions are invalid — making the variance check (1.11) against 2026 paper trades structurally unfair.

Action: Add "Historical Lot Size Mapping" to task 1.3-QA. The engine must dynamically resolve lot size by date.

**C. Expiry-Day STT Trap**

If a short put expires ITM, STT is charged at 0.125% on intrinsic value — far higher than squaring off at 3:15 PM (0.0625% on premium). This silently destroys CSP backtest P&L in tail scenarios.

Action: Ensure the strategy spec (1.7) enforces "Always square off ITM options by 3:15 PM on expiry day; never allow physical settlement." Ensure the cost model penalises ITM expiration correctly if the rule is violated.

---

### 11.2 Statistical Fix to Kill Criteria (Strong Consensus)

A 25-delta CSP has ~75% expected win rate. With N=6 trials, even a correctly functioning strategy has a ~3.5% probability of showing ≤2 wins (≤33%), and ~17% probability of showing ≤3 wins (50%). The "<40% win rate" kill criterion is too aggressive for the sample size.

**Revised Kill Criteria:**

- Month 3 checkpoint: If 0 wins in first 3 cycles → pause paper trading, investigate strike/timing selection.
- Month 6 gate: If realised max monthly loss exceeds 2× the backtest-predicted max loss for the same market regime, OR win rate ≤33% (≤2 wins in 6) → full strategy review.
- Max drawdown criterion (8%): unchanged — this is regime-independent.

---

### 11.3 Add Trading Calendar & Expiry Resolver (Strong Consensus)

Indian options backtesting breaks on: weekly vs monthly expiry transitions (Nifty: mid-2019 onward), holiday-shifted expiry dates, changed expiry conventions over time, and strike spacing changes (50-point → 100-point at higher Nifty levels).

**Add task 1.3b — Trading Calendar + Expiry Resolver:**
- Trading day calendar (handles exchange holidays)
- Monthly expiry resolver by historical regime
- Lot size by date (absorbs the lot size mapping from 11.1B)
- Strike interval by Nifty level/date

Estimated effort: 1–2 days. Prevents weeks of subtle bugs in the engine.

---

### 11.4 Interim Variance Check at Month 2 (Strong Consensus)

Waiting 6 months to discover systematic errors (e.g., missing STT, wrong lot size, flipped slippage sign) wastes time.

Action: After 2 complete paper trading cycles (~8 weeks), run an interim Z-score comparison. The sample is too small for a go/no-go decision, but large enough to catch architectural bugs. If |Z| > 3.0 at N=2, something is fundamentally broken in the measurement chain — debug immediately rather than waiting 4 more months.

---

### 11.5 Graduated Response Protocol for Variance Check (Strong Consensus)

The current plan treats |Z| ≤ 1.5 as binary pass/fail. This doesn't translate into operational decisions.

**Confidence Tiers:**

| Z-score range | Confidence | Deployment posture |
|---|---|---|
| \|Z\| ≤ 0.5 | High | Full planned size |
| 0.5 < \|Z\| ≤ 1.0 | Moderate | Full size, weekly monitoring |
| 1.0 < \|Z\| ≤ 1.5 | Low | Half size, daily monitoring for first month |
| \|Z\| > 1.5 | Fail | No deploy; run 2 debug variants (bias-adjusted, parameter-tuned) before re-gate |

**Post-live monitoring triggers (section 2.1):**
- |Z| 1.5–2.0 for 3 weeks → reduce to paper-only until Z returns below 1.0
- |Z| > 2.0 single week → halt all live trading, full investigation
- |Z| < 1.0 for 4 consecutive weeks after breach → resume normal size

---

### 11.6 Reproducibility Requirement (Consensus)

**Add to task 1.5 (Backtest Results Storage):** Every run must record `git_commit` hash, `strategy_spec_hash` (config YAML checksum), `data_version` (Parquet file checksums or date range), `cost_model_version`, and `run_timestamp`.

Acceptance criterion: Re-running with identical inputs produces bit-identical P&L output. This is essential for debugging variance check failures — you must distinguish "I fixed the bug" from "the data changed under me."

---

### 11.7 Golden Dataset Fixtures (Majority Consensus)

**Add sub-task under 1.4:** Create a small, manually-verified test dataset covering:
- 1 normal month (e.g., July 2021)
- 1 volatile month (e.g., March 2020)
- 1 expiry week in detail
- Expected strike selection, trade lifecycle, and P&L hand-calculated

This becomes the regression test backbone. Without it, full-history runs are untestable — you can't tell if a 3% P&L change after a refactor is a bug fix or a regression.

---

### 11.8 Consolidate POCs into Implementation Tasks (Majority Consensus)

**Revised POC structure (replaces Section 4):**

- **POC 1** → Merge into task 1.3-QA. When auditing Bhavcopy data quality, simultaneously test whether 25-delta strikes can be reconstructed for 4–5 sample months: include Sept 2018, a weekly-expiry transition month, and a boring month — not just March 2020.
- **POC 2** → Merge into Sprint 1 deliverable for 1.10. Deploy EOD snapshot cron; its first 20 days of operation is the reliability test.
- **POC 3** → Fold into 1.6a implementation. When building the IV reconstruction, validate against 5 days of live Upstox data as part of the acceptance test.

Result: Zero standalone POC tasks. Validation is embedded in implementation. Saves ~1 week.

---

### 11.9 Cron Health Monitoring (Consensus)

**Add task 2.1a — Job Healthcheck:** A simple daily script checking whether the EOD snapshot (1.10) produced today's file, whether daily_snapshot ran, whether files are non-empty, and sending a Telegram alert on any failure.

For a solo system with no cloud redundancy, this is more important than dashboards. Silent data gaps in forward capture are unfixable — the data cannot be backfilled.

---

### 11.10 Timeline Realism (Majority Consensus)

**Adjust Sprints 1–4 from 8 weeks to 10–12 weeks.** Rationale: single operator with a day job, Cowork sessions are not daily, NSE bulk downloads have operational friction, and the first IV reconstruction attempt always surfaces edge cases (negative time value, dividend effects).

The paper trading gate (month 6–7) doesn't move, so this slack doesn't affect the critical path. It prevents false urgency that causes corners to be cut.

---

### 11.11 Contingency for Data Quality Failure (Consensus)

The original review proposes a kill criterion (>10% missing data → Stockmock-only) but no middle ground.

**Add contingency:** If Bhavcopy audit shows >10% gaps in stress windows but <5% gaps in normal periods → proceed with partial backtest (2021–present, ~5 years) + use Stockmock output for 2016–2020 stress-period calibration. Re-evaluate full-engine value after 3 months of EOD snapshot accumulation (1.10).

---

### 11.12 Don't Fully Block Engine on Poor Early Paper Results (Split Opinion — Adopted with Nuance)

The original review states: "If paper trading fails badly, don't build the engine." The nuance: a basic historical options engine has option value beyond this one CSP spec — it enables parameter diagnosis, variant testing, and stress-window replay. If early paper results look bad, you need the engine more, not less, to understand why.

**Revised rule:**
- Continue foundational infra regardless: 1.3, 1.3-QA, 1.3b, 1.4, 1.5, 1.6a
- Gate only strategy-specific work (1.7, 1.8) on whether early paper results show catastrophic failure
- If paper performance is poor but explainable (e.g., entered during high-vol regime), proceed with engine build — the engine is the diagnostic tool

---

### 11.13 What NOT to Adopt

| Suggestion | Reason to reject |
|---|---|
| Move EOD snapshot to cloud | Conflicts with local-first assumption; adds operational complexity prematurely; laptop sleep risk is manageable with simple OS settings |
| Partially reinstate IC port in Phase 1 | Original review's deferral logic is stronger; engine can be validated with CSP alone |
| Shorten critical path to 5–7 weeks | Unrealistic for solo operator; 10–12 weeks is honest |
| Full variance decomposition (4 bias types) | Premature analytical complexity for MVP; keep bias-adjusted Z-score simple |
| Extensive assumptions register as separate file | Good practice but process overhead for a 1-person team; capture in DECISIONS.md inline |

---

### 11.14 Revised Task Additions (Net)

| New Task | Effort | Sprint |
|---|---|---|
| 1.3-QA — Data quality audit (includes lot size mapping, POC 1 validation) | 1–2 days | Sprint 2 |
| 1.3b — Trading calendar + expiry resolver | 1–2 days | Sprint 1 |
| 1.4a — Golden fixture dataset with expected outputs | 1 day | Sprint 2 |
| 1.5 enhancement — Run lineage metadata | 2 hours | Sprint 2 |
| 2.1a — Cron job healthcheck + alert | 0.5 days | Sprint 1 |

Total added effort: ~5–6 days across 10–12 weeks. Net impact on critical path: negligible.

---

### 11.15 Updated Execution Plan (Section 9 Revisions)

**Revised Sprint durations:** Sprints 1–4 extend to 10–12 weeks total (was 8 weeks).

**Sprint 1 additions (weeks 1–3):**
- 1.3b — Trading Calendar + Expiry Resolver (Cowork, 1–2 days)
- 2.1a — Cron job healthcheck + Telegram alert (Cowork, 0.5 days)

**Sprint 2 additions (weeks 3–5, was 3–4):**
- 1.3-QA — includes lot size historical mapping + POC 1 validation (not just data quality)
- 1.4a — Golden fixture dataset: July 2021 (normal), March 2020 (volatile), 1 expiry week
- 1.5 — Add run lineage metadata (git_commit, spec_hash, data_version, cost_model_version, run_timestamp)

**Month 2 addition:**
- Interim Z-score check after 2 paper cycles (~8 weeks). No go/no-go decision; |Z| > 3.0 → debug immediately.

**Gate (month 6–7) revised:**
- Replace binary pass/fail with graduated response tiers (see 11.5)
- Kill criterion: win rate ≤33% (≤2 wins in 6), not <40%

---

### 11.16 Final Summary

The original review's six recommendations stand. Adopt them. Layer these twelve refinements on top:

1. Fix the VWAP vs LTP assumption in IV reconstruction — validate 1.6a against Upstox EOD, not Bhavcopy
2. Add historical lot size mapping to 1.3-QA and 1.3b
3. Handle expiry-day STT trap in cost model and strategy spec (1.7)
4. Revise kill criteria: ≤2 wins in 6 (not <40%), month-3 interim checkpoint
5. Add trading calendar + expiry resolver as task 1.3b (Sprint 1)
6. Run interim variance check at month 2 (|Z| > 3.0 = architectural bug)
7. Replace binary variance gate with graduated confidence tiers + post-live triggers
8. Add run lineage metadata (reproducibility) to 1.5
9. Create golden fixture dataset as task 1.4a (Sprint 2)
10. Consolidate POCs into implementation acceptance criteria (zero standalone POC tasks)
11. Add cron job healthcheck as task 2.1a (Sprint 1)
12. Budget 10–12 weeks for Sprints 1–4; keep month 6–7 gate unchanged

The single most important action remains unchanged from the original review: **start paper trading this week, and start code in parallel. The bottleneck is calendar time. Everything else is engineering that fits inside that window.**

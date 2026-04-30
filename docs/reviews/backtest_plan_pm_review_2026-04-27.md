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

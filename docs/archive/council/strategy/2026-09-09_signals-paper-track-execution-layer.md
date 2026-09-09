# Council Decision: signals-paper-track-execution-layer

Date: 2026-09-09  
Chairman: anthropic/claude-opus-4.6  
Council members: openai/gpt-5.6-sol, google/gemini-3.1-pro-preview, x-ai/grok-4.6, deepseek/deepseek-r1-0528

---

## Stage 3 — Chairman Synthesis

# Council Ruling — Signals Paper Track (SPT-1)

`CONTEXT.md ✓`

---

## Summary Table

| Decision | Recommendation |
|----------|---------------|
| Module boundary — A (PaperStrategy on shared engine) vs B (self-contained loop) | **A.** Signals paper track becomes `paper_signal_track_v1` on `StrategyMonitor` + `PaperExecutor` / `PaperFillSimulator` + `PaperStore`. B rejected: independence ruling was `src/backtest/`-scoped; PT-S2 always pointed here; a second daemon is unjustified. |
| If A: home for the %-premium SL/target/time-exit evaluator | **Distinct pure module `src/strategy/signal_exit.py`** — a pure function `evaluate(position, mark, now) → TARGET | STOP_LOSS | TIME_EXIT | HOLD`. Do **not** extend `ExitSignalEngine` (short-premium/delta/IVR vocabulary). Do **not** place in `src/signals/` — that package remains the advisory pipeline. |
| If A: isolation sufficient (namespace + reserved enum) or own table | **Namespace + reserved enum is sufficient. No separate position table.** Strategy name **`paper_signal_track_v1`** (the `paper_` prefix is enforced by `PaperTrade`'s Pydantic validator — non-negotiable). Reserve `TRAILING_STOP` on the exit-reason enum now. Add a mark-path telemetry table keyed to `paper_trades.id` for tick logging; do not create a second position ledger. |
| SL / target launch levels (sl_pct / tgt_pct, flat vs scaled) | **SL −30% / target +50%, flat, not confidence-scaled, not ATR-scaled.** `sl_price = E × 0.70`, `tgt_price = E × 1.50`. Explicitly provisional. |
| Recalibration trigger | **Two-tier.** N = 30 closed trades = gross-miscalibration fuse only (one-notch SL/target tweak if MFE/MAE shows bands are obviously wrong). Full redesign only at the 6-month gate (N ≳ 50). Any changed parameters become a prospectively versioned v2 cohort — never silently pooled with v1. |
| Phase 1 fixed-only vs a low-regret dynamic element from day one | **Phase 1 fixed-only.** `TARGET`, `STOP_LOSS`, `TIME_EXIT`, `HOLD`. No breakeven bump, no trailing. |
| Phase 2 dynamic-exit shape | **Two-stage trail that also lifts the target.** A discrete capture-zone ratchet with a hard "close full" cap is the wrong analog for a long option's unbounded upside. Design against the observed MFE/MAE distribution after Phase 1 data exists. Do not lock parameter values now. |
| Monitor evaluate cadence for the paper phase | **30 seconds for the signal strategy, via per-strategy scheduling within the single shared `StrategyMonitor`.** Existing credit-spread strategies remain at 90 s. See §Cadence Rationale below. |
| Go-live gate — window, min N, P&L/expectancy, win-rate/PF, max DD, all-pass vs composite | **6 calendar months AND ≥ 50 closed trades (whichever later). All-pass — no composite score.** Net P&L > 0; expectancy > 0; profit factor ≥ 1.20; max drawdown ≤ 8× mean losing trade; no win-rate floor (asymmetric payoff). |
| Go-live gate — regime coverage / min SL count / advisory agreement | **Regime:** ≥ 1 stretch with India VIX > 18 while a position was open; if absent, extend window. **Min SL exits:** ≥ 5 `STOP_LOSS` fills. **Advisory agreement:** diagnostic only — not a gate. |
| First live-pilot constraint | **1 lot, auto-execute entries (manual approval kills 09:30 timing), 8 weeks or 20 closed live trades (whichever later). Strategy-level halt if rolling 10-trade PF < 0.8 or DD exceeds paper gate. Execution remains blocked on static IP today.** |

---

## Design Rationale

### Module Boundary

Option A is correct. The council reaches unanimous agreement on this point across all substantive responses.

The 2026-09-07 independence ruling decoupled `src/signals/` from `src/backtest/` ("own SQLite tables, no `src/backtest/` import"). It said nothing about `src/paper/` or `src/strategy/`. The paper-track roadmap already carries a planned "PT-S2 Signal Pipeline" slot (`DECISIONS.md` line 84). Option B would reimplement:

- daemon supervision and heartbeat,
- market-calendar and market-hours guards,
- fill simulation (`PaperFillSimulator`),
- position persistence (`PaperStore`),
- EOD paper reporting integration (`eod_pt_summary` reads `PaperStore.get_positions()`),

solely to protect an independence claim that does not apply to this boundary. The one real cost of A — exit-vocabulary mismatch — is paid **either way** and is cheaper as a small pure function next to the other strategy evaluators than as a second process.

### Architectural Carve-Out

The clean boundary under A:

1. **`src/signals/`** remains responsible for producing and persisting `DailySignal`. Unchanged.
2. **A signal-strategy adapter** converts an actionable `DailySignal` into `SignalEvent` / `ApprovedAction` / `LegSpec` (one BUY, 1 lot, instrument key from `resolve_monthly_option` including the ≤ 7-DTE roll).
3. **`PaperExecutor`** + **`PaperFillSimulator`** perform entry and exit fills, unchanged (`mid ± s`, VIX bands, ₹1.5 default).
4. **`src/strategy/signal_exit.py`** — a new pure evaluator: `evaluate(position, mark, now) → ExitDecision`. This is **not** a branch inside `ExitSignalEngine` (whose `DELTA_STOP`, `LOSS_STOP`, IVR-tiered rolls, and DTE reviews are short-premium/spread concepts). It is **not** in `src/signals/` (which remains the advisory pipeline). It sits in `src/strategy/` alongside the other strategy evaluators, importable by any future long-option strategy.
5. **`StrategyMonitor`** owns scheduling and dispatch. The signal strategy registers like any other `PaperStrategy`.

### Storage Isolation

**`paper_signal_track_v1`** — the `paper_` prefix is enforced by `PaperTrade`'s Pydantic validator and is the sole runtime guard against live/paper ledger contamination. The operator's draft name `signal_track_v1` would fail at construction. This is non-negotiable.

`paper_trades` remains the authoritative transaction and position ledger. Creating a parallel signals-position table would introduce dual ownership of entry fills, open state, and realised P&L, and would break `eod_pt_summary`'s unified `PaperStore.get_positions()` read.

New data requirements (frozen SL/target parameters, signal provenance, tick-level marks, MFE/MAE) are stored in:

- **Entry metadata** frozen alongside the `paper_trades` row (SL price, target price, `sl_pct`, `tgt_pct`, rule-set version, signal confidence, entry VIX, entry DTE).
- **A mark-path telemetry table** keyed to `paper_trades.id` — one row per tick: `(trade_id, ts, ltp, bid, ask, unrealised_pct, mfe_pct, mae_pct)`. This enables cadence replay, inter-tick jump analysis, and SQL-level MFE/MAE aggregation without duplicating the position ledger or stuffing history into a JSON column.
- **`paper_exit_events`** (existing) for the exit reason and final fill.

### SL / Target Levels

The proposed −30% / +50% levels are reasonable provisional paper parameters. The council agrees unanimously.

**Greeks basis:** An ATM monthly Nifty option at 15–35 DTE carries δ ≈ 0.45–0.55 and premium of roughly 1–1.5% of spot. A ~0.6–0.8% adverse spot move maps to ~25–35% premium decline; a ~1.0–1.3% favourable move maps to ~40–60% premium gain, with **positive gamma** making the upside fatter for equal |ΔS|. Asymmetric bands agree with the payoff: long convexity plus directional consensus means the right tail should be given more room than the left. Symmetric −30/+30 would donate the convexity.

**What is explicitly rejected:**
- **Confidence scaling.** Three ordinal model scores (1–5) already truncated by `MIN_CONFIDENCE_THRESHOLD` do not provide a calibrated signal. Scaling thresholds or size by confidence adds degrees of freedom faster than the sample can validate.
- **ATR-derived thresholds.** These combine underlying range, option delta, gamma, and IV into an approximate premium proxy while the system can directly observe the option premium. ATR, entry delta, and IV should be **logged as explanatory features** and tested at recalibration — not used to complicate the launch rule.
- **Per-direction asymmetry.** Calls and puts use the same −30/+50 for the initial cohort.

**Recalibration path:** N = 30 closed trades is a **fuse, not a calibration.** The median MAE of winners from 12–18 data points has no useful confidence interval. Use it to catch gross design failures ("SL is inside noise" / "target is never touched"). Any revised thresholds must be recorded as a new rule-set version (v2) and applied only prospectively. The 6-month gate report must show v1 and v2 separately.

---

## Exit-Design Detail

### Phase 1: Fixed Only

Exit priority (pure evaluator, no state machine):

```
1. mark ≥ tgt_price                       → TARGET
2. mark ≤ sl_price                        → STOP_LOSS
3. now ≥ 15:00 IST                        → TIME_EXIT
4. otherwise                              → HOLD
```

Exit fill is `PaperFillSimulator` SELL at `mid − s` on the **observed tick**, not the threshold price. A print at `0.60·E` against a `0.70·E` SL books −40%, not −30%. Gap-through is part of the paper distribution — it is the system's actual behaviour, not a bug.

**Why no breakeven stop from day one.** A breakeven bump after +X% unrealised is often presented as "never worse." This is false on an intraday Nifty option:

- Nifty cash-session mean reversion is common: +18% at 10:40, fade to +4% at 15:00 is a *good* TIME_EXIT; a BE stop turns it into a scratch.
- The same fade that arms BE and then stops at `E` would have been a full −30% only if it continued through the original SL — many fades die in the dead band between `E` and `sl_price`.
- A BE stop **can** prevent a give-back from a winner to a SL loss, which is why it is a Phase 2 candidate. But it also truncates winners, changes the return distribution, and **contaminates the MFE/MAE sample needed to design Phase 2** (you would never observe full give-backs through the dead band).

IC-V2 is the right **process** precedent (ship with fixed rules, collect data, then council a profit-lock engine as a separate story). It is the **wrong payoff** precedent for the Phase 2 shape.

### Phase 2: Two-Stage Trail That Lifts the Target

After N = 30 MFE/MAE data exists, design a dynamic exit against the observed distribution. The council unanimously rejects the IC-V2 capture-zone ratchet as the default for this vehicle:

| Shape | Fits a naked long? |
|---|---|
| Two-stage: BE at +X%; at +Y% trail stop at `peak − k·E` **and lift** target to `peak + m·E` | **Yes.** Protects the left tail without hard-capping the right tail, where long-premium expectancy is earned. |
| IC-V2 capture zones (+20% BE, +40% lock +20%, +60% close full) | **No as default.** "Close full" at a zone re-caps a convex payoff. A long option with a structural win rate of 35–45% mathematically requires fat right-tail winners. Acceptable only if Phase 1 MFE distribution shows winners die just above +50% and almost never trend — in which case the strategy itself may not be viable. |

The worked example from the operator's `council-question.md` (E = ₹300, ×65) is the right **reference shape**, not a parameter lock. Actual +X/+Y/k/m values are calibrated from Phase 1 data.

### Logging SPT-4 Must Ship on Day One

This is the Phase 2 dataset. Every tick must persist: `(trade_id, ts, ltp, bid, ask, unrealised_pct, mfe_pct, mae_pct)`. Without this, the N = 30 review and the 6-month gate have nothing to calibrate against.

Additionally flag any inter-tick `|ΔM| / E > 0.20` as a gap event. If ≥ 5 such events occur within 30 trades, trigger a cadence mini-review before 6 months.

---

## Cadence Rationale

This was the council's most contested decision. The panel split between 90 s (matching the live engine to preserve P&L fidelity) and 30 s (capturing the mark path at higher resolution to detect gap-through).

**Ruling: 30 seconds for the signal strategy, via per-strategy due scheduling within the single shared `StrategyMonitor`.**

The 90 s argument — "paper the engine you will live on" — is sound in principle but misapplied here. The paper phase's explicit purpose is to **gather movement data** to determine whether the engine's cadence is adequate for this vehicle *before* live promotion. Data sampled every 90 seconds cannot reconstruct whether stops or targets were crossed inside those intervals. If the 6-month review reveals that 30 s sampling still missed material events, the cadence can be tightened further or streaming data considered before live promotion. If it reveals 30 s changed nothing versus a coarser cadence, the live engine can safely run at 90 s.

**Implementation:** keep one `StrategyMonitor` process. Add per-strategy scheduling:

- `paper_signal_track_v1`: due every 30 s.
- Existing credit-spread strategies: due every 90 s (unchanged).
- Chain/quote data fetched only for strategies due on that tick.

This avoids a second daemon (option B in disguise) while avoiding the measurement flaw of 90 s sampling on a high-gamma intraday vehicle. Broker quote timestamps must be persisted; stale quotes (> 30 s old) must be flagged or rejected.

**Dissent acknowledged:** the minority 90 s position has merit — hammering chain fetches every 30 s increases API load and couples the signal strategy to the shared monitor's throughput. If chain-fetch latency makes 30 s impractical, fall back to 90 s **with explicit gap-event flagging and the cadence mini-review trigger** described above.

---

## Go-Live Gate Specification

SPT-7 is a **pass/fail report** over `--from` / `--to`. Default window: first paper entry through +6 calendar months. **All** gates must pass. No composite score — a composite lets strong P&L conceal an operational or drawdown failure.

### Sample Gates

| Gate | Rule |
|---|---|
| **G1 — Window** | ≥ 6 calendar months of live paper **AND** ≥ 50 closed trades. `NO_TRADE` days do not count toward N. If fire-rate yields N < 50 in 6 months, extend the calendar; do not lower N below 40 (absolute floor — below that, expectancy is noise). |
| **G2 — Exit-path validation** | ≥ 5 `STOP_LOSS`, ≥ 5 `TARGET`, ≥ 5 `TIME_EXIT` fills. If a bucket is empty, the rule is untested — extend. Deterministic replay acceptable for the rarest path if live observation is structurally unlikely. |
| **G3 — Regime coverage** | ≥ 1 stretch with India VIX > 18 while a position was open. If the 6-month window is a low-vol grind, extend — do not promote a long-option strategy that has only seen VIX 11–14. |

### Economic Gates (net of modelled `mid ± s` slippage; do not haircut again)

| Gate | Rule | SPT-7 must compute |
|---|---|---|
| **G4 — Net P&L** | Cumulative net realised P&L > ₹0 | `Σ (X − E) × lot_size` |
| **G5 — Expectancy** | Mean P&L per closed trade > 0 | `G4 / N` |
| **G6 — Profit factor** | Gross wins / gross losses ≥ **1.20** | From `paper_exit_events` |
| **G7 — Win rate** | **Not gated.** Report only. Expected WR under −30/+50 + TIME_EXIT is 35–45%; a floor would reject a valid asymmetric system. | WR overall, WR by BUY_CALL / BUY_PUT |
| **G8 — Drawdown** | Peak-to-trough of cumulative paper P&L ≤ **8×** mean losing trade. Also report: longest losing streak; any single trade losing > 1.5× the expected SL loss must receive an incident classification (gap-through, stale quote, or monitor failure — genuine market gap does not fail the gate). | Equity curve from closed trades |
| **G9 — Cost sanity** | Median round-trip slippage `2s / E` < 8%. If ATM premia collapse and ₹1.5 × 2 is a large fraction of `E`, halt and re-council before live. | |

### Operational Gates

- Zero unresolved overnight positions.
- No duplicate entries or exits.
- ≥ 95% action/date/instrument reconciliation with the advisory pipeline (`record_signal_outcome`).
- Every fill reproducible from persisted bid, ask, VIX band, and slippage.
- All exit paths validated in unit tests.

### Explicitly Not Gates

- **Advisory P&L agreement.** The advisory holds to close (16:00); the paper strategy exits intraday with SL/target/15:00. Divergence may simply show the two policies are different, not that the intraday policy is defective. Report the sign-match rate and a table of days the advisory was green while paper stopped out — as a **diagnostic**.
- **Confidence-scaled or ATR-scaled counterfactuals.** Report but do not gate.
- **Crash / gap-tail quantiles.** Cannot be estimated from ~50–120 trades. Treat as residual live risk, stated in the report.
- **Seasonal / per-provider attribution.** Cell sizes too small. Report, do not gate.

### Metrics SPT-7 Must Compute (Beyond Gate Values)

- MFE / MAE distributions (histograms vs the −30 / +50 lines).
- Results by exit reason, direction, VIX bucket, DTE, and confidence.
- Inter-tick jump percentiles (cadence review material).
- Advisory-vs-paper disagreement table.
- Quote-staleness and missed-monitor-tick statistics.

### First Live Pilot (After G1–G9 Pass)

| Parameter | Value |
|---|---|
| Size | 1 lot (same as paper). No scale-up on promotion. |
| Entry approval | **Auto-execute.** Manual per-entry Telegram approval adds minutes to entry timing and makes the live series incomparable to the paper gate. Protective exits are obviously automatic. |
| Duration | 8 weeks **or** 20 closed live trades, whichever later. |
| Kill triggers | Rolling 10-trade PF < 0.8; live DD exceeding G8; two consecutive sessions with inter-tick `|ΔM| / E > 0.40` (cadence/gap alert). |
| Execution blocker | Order execution remains blocked on static IP today. The pilot is a **rule**, not a date. |

---

## Dissenting Notes

**Module boundary.** A minority view prefers B: a naked intraday long is structurally unlike the multi-day short-premium strategies on `PaperStore`, and coupling it rides model evolution risk. **Majority rebuttal:** that coupling is one `strategy_name` and a pure evaluator; B's operational cost (second heartbeat, second holiday guard, second fill path that will drift from `PaperFillSimulator`) is larger than the conceptual impurity. The compromise the minority actually needs — and A already provides — is "not `ExitSignalEngine`," not "not `PaperStore`."

**Own table.** Rejected unanimously. If Phase 2 needs richer per-tick analytics, add a mark-path telemetry table keyed to `paper_trades.id`, not a second position book.

**SL −30% near roll.** A `greeks-analyst` minority notes that at 8–12 DTE (just after the roll threshold) gamma is high enough that −30% can print on a 0.4% Nifty dip — the stop may be tight versus noise. **Majority:** that is exactly what N = 30 MFE/MAE is for. Widening SL pre-data bakes in larger left-tail fills. If recalibration shows the issue, a future review may widen SL when DTE ≤ 10 rather than across all DTE.

**Breakeven from day one.** One `options-strategist` vote for a pure BE at +25% as "free insurance." **Rejected:** not free under intraday mean reversion; contaminates the MFE/MAE sample needed to design Phase 2. If N = 30 shows median winner MFE ≫ 50% and brutal give-backs through SL, pull BE forward as an out-of-cycle patch, not as Phase 1 scope.

**Cadence — strongest dissent.** The 90 s faction argues that paper P&L must match the engine's live cadence, and that a faster signal-strategy loop couples it to the shared monitor's chain-fetch throughput. **Majority ruling: 30 s, with fallback.** The paper phase exists to determine whether the engine's cadence is adequate; sampling at 90 s cannot answer that question. If chain-fetch latency makes 30 s impractical, fall back to 90 s with explicit gap-event flagging (inter-tick `|ΔM| / E > 0.20`) and a cadence mini-review trigger at ≥ 5 such events in 30 trades.

**Go-live N = 50 vs N = 30.** Do not let the recalibration trigger (N = 30 fuse) and the promotion trigger (N = 50 gate) collapse into one number. They serve different purposes.

**Auto-execute vs manual approval for the live pilot.** The 20-trade manual-approval proposal from one panelist is acknowledged but rejected. "Immediately on the aggregated signal" is a locked constraint; per-entry manual approval adds minutes and makes the live P&L series incomparable to the paper gate it was validated against. The kill triggers (rolling PF, DD ceiling) provide the safety net.

**S5.5a.** Once SPT-5's exit Telegram message is live, mark signals S5.5a `won't-do` and point it here. Do not run two 15:00 outcome messages.

---

## Stage 1 — Individual Responses

### openai/gpt-5.6-sol

CONTEXT.md ✓

## Summary Table

| Decision | Recommendation |
|---|---|
| Module boundary — A vs B | **Choose A:** implement the signal track as `paper_signal_track_v1`, conforming to `PaperStrategy`, on the shared `StrategyMonitor`, `PaperExecutor`, `PaperFillSimulator`, and `PaperStore`. Do not create a second monitor process. |
| Home for the %-premium evaluator | Add a separate pure evaluator such as `src/strategy/long_option_exit.py`. Do **not** extend the short-premium-oriented `ExitSignalEngine`, and do not put execution policy inside the signal-generation package. |
| Isolation | Use `paper_signal_track_v1`—the mandatory `paper_` prefix matters. Keep `paper_trades` as the canonical execution ledger. Add auxiliary parameter/telemetry tables for frozen thresholds and quote paths; do not create a second canonical position ledger. Reserve `TRAILING_STOP` in the exit-reason enum. |
| SL / target launch levels | Launch with **SL −30% / target +50%**, flat across direction and confidence. Calculate from the simulated entry fill and freeze per trade. |
| Recalibration trigger | First analysis at **both N ≥ 30 and ≥3 calendar months**. Treat it as exploratory, not sufficient for live promotion. Any changed parameters become a prospectively versioned v2 cohort; do not rewrite or pool them invisibly with v1. |
| Phase 1 dynamic exit | **Fixed-only:** `TARGET`, `STOP_LOSS`, `TIME_EXIT`, `HOLD`. No breakeven bump or trailing stop initially. |
| Phase 2 dynamic-exit shape | Prefer a **discrete capture-zone ratchet**, calibrated from MFE/MAE, with the final zone becoming a runner/trailing regime rather than imposing a hard upside cap. |
| Paper monitor cadence | **30 seconds**, not 90 seconds. Keep one shared daemon; add per-strategy cadence scheduling if polling all strategies every 30 seconds is undesirable. |
| Go-live evaluation window | At least **6 calendar months and 60 closed trades, whichever is later**. If 60 trades are not reached by 9 months, require a fresh review rather than silently lowering the sample requirement. |
| Economics gate | Net P&L > 0; mean net expectancy ≥ **+0.10R/trade**; profit factor ≥ **1.25**; win rate ≥ **40%**; weekly block-bootstrap probability that mean expectancy is positive ≥ **80%**. |
| Drawdown gate | Maximum drawdown ≤ **5R**, where the report converts cumulative trade outcomes to normalized `R`; also report cash drawdown. Any loss worse than −1.5R requires incident review for quote staleness, gap-through, or monitor failure. |
| Pass rule | **All mandatory criteria pass.** Do not use a composite score that lets strong P&L conceal an operational or drawdown failure. |
| Regime and exit-path coverage | Require at least **5 stop-loss exits** and either at least **10 trades entered with India VIX ≥18** or an explicit extension of the observation window until elevated-volatility coverage exists. |
| Advisory agreement | Require ≥ **95% instrument/action/date reconciliation** between the advisory and paper tracks. Do not require their P&Ls to agree—the advisory close-only methodology and intraday managed strategy are economically different. |
| First live pilot | Fixed **1 lot**, manual approval for entries during the first **20 executed trades**, automatic protective exits, and at least **3 months / 40 live trades** before reconsidering automation or size. Add a −3R pilot drawdown pause. |

## Design Rationale

### Module boundary

Option A is the correct architecture.

The prior independence ruling excluded `src/backtest/`; it did not prohibit the signal product from becoming an input to the paper backbone. The existing “PT-S2 Signal Pipeline” roadmap further supports this integration. A second self-contained execution loop would duplicate:

- daemon supervision,
- market-calendar and market-hours guards,
- fill simulation,
- position persistence,
- heartbeat handling,
- exit dispatch,
- EOD paper reporting integration.

The single-long-option shape does not invalidate `PaperStrategy`. It is simply a one-leg strategy. What does not fit is the existing **exit policy**, not the monitor, executor, or ledger.

The clean boundary should therefore be:

1. `src/signals/` remains responsible for producing and persisting `DailySignal`.
2. A signal-strategy adapter converts an actionable `DailySignal` into `SignalEvent`, `ApprovedAction`, and `LegSpec`.
3. `PaperExecutor` performs the entry and exit fills.
4. A new pure long-option evaluator determines `TARGET`, `STOP_LOSS`, `TIME_EXIT`, or `HOLD`.
5. `StrategyMonitor` owns scheduling and dispatch.

The evaluator should not be added as another branch inside `ExitSignalEngine`. That engine embodies short-premium and spread-specific concepts. A separate `long_option_exit.py` keeps the different payoff assumptions explicit and can later support other long-option strategies without importing signal-generation models.

### Storage isolation

The strategy name must be **`paper_signal_track_v1`**, not `signal_track_v1`, because `PaperTrade` requires the `paper_` prefix.

`paper_trades` should remain the authoritative transaction and position ledger. Creating another signals-position table would introduce dual ownership of entry fills, open state, and realised P&L.

However, namespace isolation alone does not satisfy the new data requirements. Add auxiliary storage, owned alongside `PaperStore`, for:

- entry premium and frozen `sl_pct` / `target_pct`,
- derived SL and target prices,
- rule-set version,
- signal provenance,
- quote timestamp, receive timestamp, bid, ask, mid and LTP,
- running peak, trough, MFE and MAE,
- final exit reason.

A normalized mark-path table is preferable to packing quote history into a JSON column. It enables cadence replay and SQL aggregation without duplicating the position ledger.

## Exit-Design Detail

### Launch thresholds

The proposed −30% / +50% levels are reasonable provisional paper parameters.

They provide an advertised reward/risk ratio of approximately 1.67 before slippage and gap-through. Their purpose is not to claim optimality; it is to establish a stable, testable baseline while collecting actual intraday excursion data.

The levels should be:

- based on the **simulated entry fill**, not the LLM entry band;
- frozen for the life of the trade;
- identical for calls and puts;
- independent of model confidence during the initial cohort.

Confidence scaling should not be introduced without first demonstrating that confidence is calibrated and monotonically related to trade expectancy. With only three ordinal model scores, scaling thresholds or size by confidence would add degrees of freedom faster than the sample can validate them.

ATR-derived thresholds are also premature. They combine underlying range, option delta, gamma and IV into an approximate premium move while the system can directly observe the option premium. ATR, entry delta and IV should be logged as explanatory features and tested at recalibration—not used to complicate the launch rule.

### Recalibration

Use **N ≥ 30 and at least three months** as the first formal diagnostic checkpoint. Examine:

- MFE and MAE distributions,
- MAE of eventual winners,
- MFE of eventual losers,
- time-to-MFE and time-to-MAE,
- outcomes by call/put, confidence, VIX and DTE,
- counterfactual results across a small predeclared SL/target grid.

Thirty trades are enough to identify gross design failures, but not enough to establish a live-grade optimum. Any revised rules must be recorded as a new rule-set version and applied only prospectively. The final go-live report should show v1 and v2 separately as well as any clearly labelled combined operational record.

### No dynamic exit in Phase 1

Do not add a breakeven stop from day one. A breakeven bump does not “never worsen” an outcome: it can turn a trade that retraces and subsequently reaches +50% into a scratch exit. It changes the return distribution and must be evaluated like any other strategy parameter.

Phase 1 should therefore have this explicit priority:

1. `TARGET` when the observed mark reaches or exceeds the target;
2. `STOP_LOSS` when it reaches or falls below the stop;
3. `TIME_EXIT` at or after 15:00;
4. otherwise `HOLD`.

Persist the actual executable simulated exit fill, not the threshold price. Gap-through remains part of the result.

For Phase 2, prefer a data-calibrated discrete ratchet over a continuously moving target. Discrete zones are easier to reproduce, less sensitive to quote noise, and easier to assess counterfactually. Because a long option has meaningful upside convexity, the highest zone should transition to a trailing runner rather than force a fixed full exit merely because a zone was reached.

### Cadence

Ninety seconds is too coarse for the primary paper record of an intraday naked long option. The issue is not merely risk control; sampling only every 90 seconds prevents the project from later determining what happened inside those intervals. Logging a “full path” at 90-second resolution cannot establish whether 30-second monitoring would have hit a stop or target.

Use a **30-second evaluation cadence** for the signal strategy. This is still sampled paper execution—not tick-perfect reconstruction—but is an acceptable first compromise between quote fidelity, API load and operational simplicity.

Keep a single `StrategyMonitor` process. Prefer per-strategy due scheduling inside it:

- signal track due every 30 seconds;
- existing slower strategies remain at 90 seconds;
- chain/quote data fetched only for strategies due on that tick.

Also persist broker quote timestamps and reject or flag stale quotes. A fast loop over stale data does not improve fidelity.

## Go-Live Gate Specification

### Evaluation population

The primary cohort must satisfy:

- at least six calendar months;
- at least 60 closed, actionable signal trades;
- one fixed and identifiable rule-set version for the primary economic assessment;
- every opened position closed by the strategy, with no unresolved overnight position;
- all P&L net of `PaperFillSimulator` entry and exit slippage.

If parameter v2 launches after the N=30 review, report v1 and v2 separately. Promotion should rely on the prospectively observed configuration proposed for live use, not an optimized retrospective recombination.

### Required calculations

For trade \(i\), define initial risk:

\[
R_i = entry\_premium_i \times quantity_i \times sl\_pct_i
\]

and normalized return:

\[
r_i = net\_pnl_i / R_i
\]

SPT-7 should compute:

- total and average net P&L;
- total and average normalized `R`;
- median trade return;
- gross profit and gross loss;
- profit factor;
- win, loss and scratch counts;
- win rate;
- maximum cash drawdown;
- maximum drawdown on cumulative normalized `R`;
- longest losing streak;
- results by exit reason, direction, VIX bucket, DTE and confidence;
- MFE/MAE distributions;
- quote-staleness and missed-monitor statistics;
- weekly block-bootstrap distribution of mean expectancy.

Weekly block bootstrap is preferable to treating every daily trade as independent because adjacent market sessions can share the same regime.

### Mandatory economic thresholds

All must pass:

1. **Net realised P&L > ₹0.**
2. **Average expectancy ≥ +0.10R per trade.**
3. **Profit factor ≥ 1.25.**
4. **Win rate ≥ 40%.**
5. **Maximum normalized drawdown ≤ 5R.**
6. **At least 80% block-bootstrap probability that mean expectancy is positive.**

Do not require a conventional 95% confidence interval above zero. With roughly 60–120 trades, that test may be underpowered even for a practically useful edge. The 80% bootstrap probability is an evidence threshold for a tightly constrained pilot, not proof of a permanent edge.

Win rate is secondary because the payoff is asymmetric, but a 40% floor provides a useful sanity check against a result driven by one or two extreme winners.

### Operational thresholds

Also require:

- no real orders during the paper phase;
- zero unresolved overnight positions;
- at least 99% of expected monitor ticks completed or explicitly classified;
- no duplicate entries or duplicate exits;
- no unexplained stale-quote execution;
- action, date and instrument reconciliation with the advisory pipeline ≥95%;
- every simulator fill reproducible from persisted bid, ask, VIX band and slippage;
- at least five actual `STOP_LOSS` exits;
- `TARGET`, `STOP_LOSS`, and `TIME_EXIT` paths each validated in unit tests and observed or deterministically replayed.

Any trade losing more than −1.5R must receive an incident classification. It need not automatically fail the gate if it was a genuine market gap, but an unexplained monitor or stale-data failure does.

### Regime coverage

Require at least ten trades entered while India VIX was at or above 18. If the initial six-month window lacks that coverage, extend observation rather than manufacturing confidence from calm-market results.

The parallel advisory series is useful as a reconciliation and attribution control, not as an economic benchmark. Its close-only exit and entry-band assumptions are intentionally different, so P&L equality or high correlation should not be a gate.

### First live pilot

Subject to resolving the repository’s real-order infrastructure constraints, first promotion should be:

- one lot only;
- manual approval for each entry during the first 20 live trades;
- a short approval timeout so delayed approval does not silently change the strategy;
- stop-loss, target and 15:00 exits automatic—protective exits must not wait for manual approval;
- minimum three calendar months and 40 closed live trades before considering automatic entries or greater size;
- immediate pause at a live drawdown of −3R, any overnight-position failure, duplicate execution, or stale-price execution.

No position-size increase should occur merely because the pilot is profitable. Scaling requires a separate paper-vs-live slippage and variance review.

## Dissenting Notes

- A minority architecture view may prefer a self-contained signals table because it makes the six-month experiment easy to archive. That benefit does not outweigh dual-ledger risk and a second supervised daemon. An auxiliary telemetry table provides the required experimental isolation without duplicating positions.
- A 15-second cadence would better observe fast moves, but may materially increase API and chain-fetch load without delivering tick-level realism. Thirty seconds is the recommended paper compromise; streaming market data should be evaluated before live automation.
- Some panelists may consider −30% too wide for a same-day long option. Without intraday MFE/MAE data, narrowing it would be equally judgmental and more vulnerable to ordinary premium noise. The correct response is a frozen baseline plus prospective recalibration.
- Profit factor, win rate and expectancy are correlated criteria. They are deliberately all retained because this is a go-live safety gate, but none should be presented as statistically independent evidence.

### google/gemini-3.1-pro-preview

Here is the official ruling from the AI Council (`options-strategist` and `greeks-analyst` perspectives) based on your system context, design constraints, and prompts.

```markdown
## Summary Table

| Decision | Recommendation |
|----------|---------------|
| Module boundary — A (PaperStrategy on shared engine) vs B (self-contained loop) | **A (PaperStrategy on shared engine)**. Independence ruling was `src/backtest`-scoped; reuse gives EOD reporting and existing loop resilience for free. |
| If A: home for the %-premium SL/target/time-exit evaluator | **New module** (`src/signals/paper_exit.py`). Do not overload `ExitSignalEngine` with naked long %-premium logic. |
| If A: isolation sufficient (namespace + reserved enum) or own table | **Namespace + reserved enum is sufficient.** `PaperStore` is well-tested at multitenancy; `signal_track_v1` cleanly isolates it. |
| SL / target launch levels (sl_pct / tgt_pct, flat vs scaled) | **-30% SL / +50% Target, flat.** Judgment-based starting point. Do not scale by confidence yet. |
| Recalibration trigger (N=30 / calendar / statistical power) | **N = 30 executed paper trades.** Sufficient to establish a preliminary MFE/MAE distribution curve. |
| Phase 1 fixed-only vs a low-regret dynamic element from day one | **Phase 1 fixed-only.** Defer all dynamic/trailing elements to Phase 2 to ensure clean baseline data collection. |
| Phase 2 dynamic-exit shape (two-stage trail+target vs capture-zone ratchet) | **Two-stage trail that lifts the target.** Uncapped upside is critical for long-premium expectancy; capture-zone ratchets are for credit spreads. |
| Monitor evaluate cadence for the paper phase (90 s vs tighter) | **90 s tick.** Retain shared daemon cadence. Re-evaluate gap-through risk using the logged MFE/MAE path before live promotion. |
| Go-live gate — window, min N, P&L/expectancy, win-rate/PF, max DD, all-pass vs composite | **All-pass required.** Window: 6 mos. Min N: 40 executed. PF > 1.20. Expectancy > +₹150/trade. Max DD < ₹15,000. |
| Go-live gate — regime coverage / min stop-loss count / advisory agreement required? | **Yes.** ≥1 VIX>18 window, ≥10 SL exits experienced, and directional P&L correlation with advisory `record_signal_outcome`. |
| First live-pilot constraint (size / approval / duration) | **1 lot, manual Telegram approval for entry, 30 days.** |

## Design Rationale

**Module Boundary:**
Option A is the correct architectural path. The 2026-09-07 independence ruling explicitly barred `src/backtest/` imports to prevent lookahead bias and historical data leakage—it did not ban using the production-grade `src/paper/` execution engine. Building a second daemon loop (`B`) introduces operational overhead (supervising two processes, duplicate heartbeat logic) for no structural benefit. The adapter required (`DailySignal` → `SignalEvent` / `ApprovedAction`) is trivial, and placing the position in `PaperStore` under the `paper_signal_track_v1` namespace automatically integrates the track into the `eod_pt_summary.py` report.

However, the %-premium exit logic for a naked long option is fundamentally alien to the `ExitSignalEngine`, which is tuned for delta-neutral and short-premium structures (`DELTA_STOP`, IVR-tiered rolls). Therefore, the new exit evaluator should be a standalone pure function in `src/signals/paper_exit.py`, consumed by the new `PaperStrategy` adapter.

**Trade Rules & Launch Levels:**
From an `options-strategist` view, a flat -30% SL and +50% Target are sensible judgment-based launch parameters for a 1-lot Nifty monthly option. With the ≤ 7-DTE roll keeping gamma risk manageable, an ATM option carries roughly 1% to 1.5% of spot in premium. A -30% stop allows for normal intraday noise (~0.2% spot fluctuation) without being shaken out, while a +50% target capitalizes on a clean ~0.5% directional move (assuming delta ~0.5). We strongly endorse "recalibrate at N = 30". 30 executed trades (which may take 1.5 to 2 months given NO_TRADE days) is the statistical minimum to form a Central Limit Theorem baseline for the MFE (Maximum Favorable Excursion) and MAE (Maximum Adverse Excursion) distributions.

## Exit-Design Detail

We endorse the operator's stance: **Phase 1 must be strictly fixed-exit (no trailing, no breakeven bumps).** Introducing a breakeven stop without baseline MFE/MAE data often degrades system expectancy by choking out trades that dip slightly negative before trending to the target. 

For **Phase 2**, the `greeks-analyst` and `options-strategist` both strongly recommend the **two-stage trail that lifts the target**, aggressively rejecting the IC-V2 capture-zone ratchet. 
*Why:* Iron Condors and Covered Calls have a structurally capped maximum profit. Ratcheting locked profits makes sense there. A naked long option, however, has a capped downside (100% of premium, structurally bounded to -30% by our SL) and theoretically uncapped upside. Long premium strategies suffer low win rates due to theta decay and volatility contraction; they mathematically require fat right-tail winners to maintain positive expectancy. A fixed +50% target combined with a tightening stop truncates that right tail. Phase 2's design must trail the stop *while lifting or removing the target* to let runners run (e.g., catching a +150% day on a structural gap).

## Go-Live Gate Specification

The following gate must be passed in its entirety (All-Pass) to promote from paper to live pilot.

**1. Volume & Duration Criteria:**
*   **Evaluation Window:** Minimum 6 calendar months from first paper execution.
*   **Minimum N:** ≥ 40 executed trades (excludes `NO_TRADE` days and skipped entries). 

**2. Performance Criteria (Net of simulated `mid ± s` slippage):**
*   **Profit Factor (Gross Profit / Gross Loss):** > 1.20.
*   **Expectancy:** > +₹150 per trade. (Win Rate % is intentionally omitted as a hard constraint; long premium strategies can be highly profitable with a 35-40% win rate if the PF is high).
*   **Max Drawdown:** < ₹15,000 (roughly 5 consecutive max-loss hits at ~₹3,000 per -30% SL on a typical ₹10k premium).

**3. Validation & Regime Criteria:**
*   **Stop-Loss Validation:** The system must experience and successfully log at least **10** `STOP_LOSS` exits.
*   **Regime Coverage:** The 6-month window must contain at least one 5-day period where India VIX > 18, OR at least two individual trading sessions with an intraday Nifty move > 1.5% from open. (Proves the SL gap-through slippage mechanics behave safely under stress).
*   **Advisory Agreement:** The cumulative paper P&L curve must positively correlate with the P&L generated by `record_signal_outcome.py` (which assumes EOD execution). If the intraday track loses money while the EOD hold makes money, the intraday exit parameters are flawed and must be redesigned, failing the gate.

**4. First Live-Pilot Constraints:**
*   When passed, the Phase 1 Live Pilot is restricted to: **1 lot strict max, manual Telegram approval required for entry, lasting exactly 30 calendar days.**

## Dissenting Notes

*   **On 90s Cadence (`options-strategist` dissent):** A 90-second polling cadence is acceptable for *paper phase data collection*, but panel members warn it is likely dangerously slow for live Naked Long options. 90 seconds during a sudden RBI announcement or algorithmic cascade can easily turn a -30% modeled stop into a -55% realized fill. We accept 90s for SPT-4 to avoid architectural sprawl, but the MFE/MAE logging must specifically report whether high-velocity ticks stepped entirely over the SL boundary.
*   **On Module Boundary (`greeks-analyst` dissent):** While Option A is pragmatic, mixing long-premium signals into a namespace (`paper_`) dominated by short-premium delta-neutral ledgers risks future schema drift. The strict `TradeState` and `total_pnl` invariants of `PaperStore` must not be contorted to fit the signal track. If the single-leg long violates existing `PaperLegSnapshot` constraints at any point, revert to Option B immediately rather than polluting the core paper engine.
```

### x-ai/grok-4.6

## Summary Table

| Decision | Recommendation |
|----------|---------------|
| Module boundary — A (PaperStrategy on shared engine) vs B (self-contained loop) | **A.** Signals paper track is a `PaperStrategy` on `StrategyMonitor` + `PaperExecutor` / `PaperFillSimulator` + `PaperStore`. B is rejected: the 2026-09-07 independence ruling scoped `src/backtest/` only; PT-S2 already pointed here; a second daemon is not justified by exit-vocabulary mismatch. |
| If A: home for the %-premium SL/target/time-exit evaluator | **Distinct pure module**, not `ExitSignalEngine`. Preferred path: `src/strategy/signal_exit.py` (pure `evaluate(position, mark, now) → TARGET \| STOP_LOSS \| TIME_EXIT \| HOLD`), invoked from the strategy’s `check_signals`. Do **not** add a signal-family to `ExitSignalEngine` (short-premium / delta / IVR vocabulary). Do **not** put it in `src/signals/` — that package stays the advisory pipeline (`DailySignal`, aggregator, `resolve_monthly_option`). |
| If A: isolation sufficient (namespace + reserved enum) or own table | **Namespace + reserved enum is sufficient. No own position table.** Strategy name **`paper_signal_track_v1`** (must start with `paper_` — operator draft `signal_track_v1` would violate the `PaperTrade` invariant). Reserve `TRAILING_STOP` on the exit-reason enum now. Persist in `paper_trades` / `paper_exit_events` / tick-path log; do not create a parallel signals ledger. |
| SL / target launch levels (sl_pct / tgt_pct, flat vs scaled) | **SL −30% / target +50%, flat, not confidence-scaled, not ATR-scaled.** `sl_price = E·0.70`, `tgt_price = E·1.50`. Explicitly provisional. |
| Recalibration trigger (N=30 / calendar / statistical power) | **Two-tier.** **N = 30 closed trades** = gross-miscalibration review only (one-notch SL/target tweak if MFE/MAE shows the bands are obviously wrong). **Full redesign** only at the 6-month gate (N ≳ 50). Do not treat N = 30 as statistically powered calibration. Do not ATR- or confidence-scale until that full review. |
| Phase 1 fixed-only vs a low-regret dynamic element from day one | **Phase 1 fixed-only.** No breakeven bump, no trail. A BE stop after +X% is **not** low-regret on an intraday fade-prone index. Mirror IC-V2: profit-lock was a later story with its own ruling. |
| Phase 2 dynamic-exit shape (two-stage trail+target vs capture-zone ratchet) | **Lean two-stage trail that also lifts the target.** Capture-zone “close full” is the wrong analog (defined-risk credit vs unbounded-upside long). Do **not** lock +15/+30/0.15 numbers now. |
| Monitor evaluate cadence for the paper phase (90 s vs tighter) | **90 s on the shared `StrategyMonitor` tick.** Paper P&L must be the P&L of the engine you will live on. No dedicated sub-loop. Revisit cadence only if logged inter-tick jumps show material SL gap-through. |
| Go-live gate — window, min N, P&L/expectancy, win-rate/PF, max DD, all-pass vs composite | **6 calendar months AND N ≥ 50 closed trades (whichever later). All-pass, not a composite score.** Net realised P&L > 0 (slippage already in fills); profit factor ≥ 1.20; expectancy > 0; max DD ≤ 8× mean losing trade (rupee) **and** no worse than 12 consecutive SL-equivalent losses in the equity curve. **No win-rate floor** (asymmetric 30/50 implies WR well below 50% can still be valid). |
| Go-live gate — regime coverage / min stop-loss count / advisory agreement required? | **Regime:** at least one stretch with India VIX > 18 inside the window; if absent, **extend the window**, do not waive. **Min SL exits:** ≥ 8 `STOP_LOSS` fills (path validation, analogue of Phase 0.8-B). **Advisory agreement with `record_signal_outcome`:** **not a gate** — diagnostic only (close-to-close hold ≠ managed intraday). |
| First live-pilot constraint (size / approval / duration) | **1 lot, auto-execute (no per-entry human approval — that kills 09:30 timing), 8 weeks, daily kill: 1 SL or TIME_EXIT already the size cap; strategy-level halt if rolling 10-trade PF < 0.8 or DD hits the paper gate.** Manual approval is incompatible with “immediately on aggregated signal.” |

---

## Design Rationale

**Module boundary.** The 2026-09-07 ruling decoupled `src/signals/` from `src/backtest/` (“own SQLite tables, no `src/backtest/` import”). It did not freeze signals out of `src/paper/` or `src/strategy/`. PT-S2 was already the slot for this vehicle. Option B would reimplement a tested 90 s daemon, WARN-dedup, heartbeat, fill simulator, and EOD PT summary join — to protect an independence claim that does not apply.

The one real cost of A is exit vocabulary: `ExitSignalEngine` speaks `DELTA_STOP`, `LOSS_STOP` as credit-multiples, IVR-tiered rolls, DTE reviews. A naked long with %-of-premium bands is a different contract. That cost is paid **either way**. Paying it as a **small pure function** next to the other strategy evaluators is cheaper than a second process.

**Carve-out, not a second ledger.** Isolation that matters:

1. `paper_signal_track_v1` (prefix enforced by `PaperTrade`).
2. Pure evaluator **not** bolted onto `ExitSignalEngine` (prevents CSP/IC thresholds and long-option thresholds from sharing a class and drifting together).
3. `TRAILING_STOP` reserved so Phase 2 does not churn schema.
4. Tick path / MFE / MAE as **telemetry** (`paper_exit_events` plus a mark-path table or snapshot stream), not a second position store.

`eod_pt_summary` then picks the track up for free via `PaperStore.get_positions()`. An own table would make that a special case and re-split the paper ledger the `paper_` prefix was invented to keep whole.

**Adapter surface (A, named so SPT-2..8 can be rewritten):**

- `DailySignal` → one `LegSpec` (BUY 1 lot, instrument key from `resolve_monthly_option`, including the ≤ 7-DTE roll).
- `PaperExecutor` + `PaperFillSimulator` unchanged (`mid ± s`, VIX bands, default ₹1.5). Entry BUY at `mid+s`; every exit is SELL at `mid−s`.
- Frozen at fill `E`: `sl_price`, `tgt_price`, qty, trailing snapshot placeholders.
- `check_signals`: LTP from the already-fetched chain → `signal_exit.evaluate` → `ACTION` + `auto_execute` on non-HOLD.
- Priority (Phase 1): `TARGET` → `STOP_LOSS` → `TIME_EXIT` (15:00 IST) → `HOLD`. Fill at **observed mark**, not the band (gap-through is booked).

**SL −30% / +50%.** Greeks, not folklore: ATM monthly Nifty, ~15–35 DTE after the roll, δ ≈ 0.45–0.55. Premium is roughly 1–1.5% of spot. A ~0.6–0.8% adverse spot move is ~25–35% of premium; a ~1.0–1.3% favourable move is ~40–60%, with **positive gamma** making the upside fatter than the downside for equal |ΔS|. Asymmetric bands **agree with the payoff** (long convexity + directional consensus). Symmetric −30/+30 would donate the convexity. Confidence-scaling on a 3–5 integer already truncated by `MIN_CONFIDENCE` is overfitting with n = 0. ATR-through-delta looks principled and is a second estimator (spot ATR, delta, sticky-strike IV) on a vehicle that does not yet have a single managed fill.

Launch numbers are **judgment**, same class as IC-V2 shipping without `profit_target_fraction`. They will be wrong in the last decimal; they are unlikely to be wrong in sign.

**N = 30 is a fuse, not a calibration.** Median MAE of winners from ~12–18 points has no useful CI. Use it to catch “SL is inside noise / target is never touched.” Powered level choice waits for the 6-month sample.

**Cadence.** `StrategyMonitor` at 90 s was built for short-premium gamma, but **live promotion on this engine implies 90 s live**. Evaluating faster in paper than you will in production produces a P&L you cannot replay. ATM monthly gamma is not 0-DTE. A 30% premium gap in 90 s is an event-print move, not the base case; those days belong in the paper distribution if they will exist live. Log `(ts, ltp, bid, ask, unrealised_pct, mfe_pct, mae_pct)` every tick so SPT-7 can answer “would 30 s have changed this fill?” without having run 30 s.

---

## Exit-Design Detail

**Phase 1: fixed `TARGET` / `STOP_LOSS` / `TIME_EXIT` / `HOLD` only.**

A breakeven stop after +X% is often sold as “never worse.” That is false on this vehicle:

- Nifty cash-session mean reversion is common: +18% of premium at 10:40, fade to +4% at 15:00 is a *good* TIME_EXIT; a BE stop turns it into scratch.
- The same path that arms BE and then stops at `E` would have been a full −30% only if it continued through the original SL — many fades die in the dead band.
- BE **can** prevent a give-back to SL, which is why it is a Phase 2 candidate, not why it is free.

IC-V2 is the right process precedent (ship dumb, lock data, then council a lock engine). It is the **wrong payoff precedent** for the Phase 2 *shape*.

**Phase 2 shape (design after N = 30 telemetry, implement after the 6-month gate unless N = 30 shows a grotesque give-back problem):**

| Shape | Fits a naked long? |
|---|---|
| Two-stage: BE at +X% unrealised; at +Y% trail stop at `peak − k·E` **and lift** target to `peak + m·E` | **Yes.** Protects the left without hard-capping the right tail, which is where longs earn their keep. |
| IC-V2 capture zones (e.g. +20% BE, +40% lock +20%, +60% close full) | **No as default.** Close-full at a zone re-caps a convex payoff. Acceptable only if MFE distribution shows winners die just above +50% and almost never trend. |

Worked intuition (E = ₹300, ×65), unchanged from the operator’s sketch, is the right **reference**, not a parameter lock: trail-and-lift lets 300→455 run past the fixed 450 cap; BE can turn 300→345→250 into scratch instead of −₹3,250; a trade that never clears +12% still TIME_EXITs — residual overnight-style bleed the trail cannot fix, which is why 15:00 hard-exit stays even in Phase 2.

**Fill / gap-through (already locked, restated so SPT-5 cannot “fill at the band”):** exit fill is `PaperFillSimulator` SELL at `mid − s` on the observed tick. A print at 0.60·E against a 0.70·E stop books −40% of premium, not −30%. That slippage **is** the paper edge, not a bug.

**Logging SPT-4 must ship on day one (this is the Phase 2 dataset):** full mark path; MFE/MAE as % of `E`; exit reason; VIX at entry/exit; DTE; `consensus_confidence`; bid/ask at fill. Without this, N = 30 review has nothing to review.

---

## Go-Live Gate Specification

SPT-7 is a **pass/fail** over `--from` / `--to`. Default window: first paper entry through +6 calendar months. **All** numbered gates must pass. No composite score (not gameable, not “4 of 6”).

**Sample**

| Gate | Rule |
|---|---|
| G1 Window | ≥ 6 calendar months of live paper **and** ≥ 50 **closed** trades. NO_TRADE days do not count toward N. If fire-rate is so low that 6 months yields N < 50, **extend calendar**, do not lower N below 40 (absolute floor; below that expectancy is noise). |
| G2 Path validation | ≥ 8 `STOP_LOSS`, ≥ 8 `TARGET`, ≥ 8 `TIME_EXIT`. If one bucket is empty, the rule is untested — fail, extend. |
| G3 Regime | ≥ 1 session in the window with India VIX > 18 **while a position was open**. If the half-year is a low-vol grind, extend; do not promote a long-option book that has only seen VIX 11–14. |

**Economics (net of modelled slippage; do not haircut again)**

| Gate | Rule | SPT-7 must compute |
|---|---|---|
| G4 Expectancy | Mean rupee P&L per closed trade > 0 | `Σ(X−E)×lot_size / N` |
| G5 Profit factor | Gross wins / gross losses ≥ **1.20** | By `paper_exit_events` |
| G6 Win rate | **Not gated.** Report only. Expected WR under 30/50 + TIME_EXIT is often 35–45%. | WR, WR by `BUY_CALL` vs `BUY_PUT` |
| G7 Drawdown | Peak-to-trough of cumulative paper P&L ≤ **8×** mean losing trade **and** < **12** consecutive losing trades | Equity curve from closed trades only (no MTM overnight — there is none) |
| G8 Cost sanity | Median round-trip `s` / `E` < 8%. If ATM premia collapse and ₹1.5×2 is a large fraction of E, halt and re-council size/bands before live. | |

**Explicitly not gates**

- Agreement with `record_signal_outcome` close-to-close P&L. Different policy (hold to 16:00 vs SL/target/15:00). Report as a **diagnostic**: sign-match rate, and a table of days the advisory was green while paper SL’d (the interesting disagreement).
- Confidence-scaled or ATR-scaled counterfactuals.
- Crash / gap-tail quantiles — **cannot** be estimated from ~50–120 trades. Treat as residual live risk, not a paper gate. State that in the report.

**Metrics ~120 signal days cannot support** (report, do not gate): seasonal expiry-week vs mid-month cells; per-provider attribution; “true” 15 s gap-through distribution; any ML overlay.

**First live pilot (after G1–G8 pass)**

- Size: **1 lot** (same as paper). No scale-up on promotion.
- Approval: **auto-execute**, same as paper. Per-entry Telegram approval adds minutes and makes the live series incomparable to the gate.
- Duration: **8 weeks** or **20 closed live trades**, whichever later, still 1 lot.
- Kill: rolling 10-trade PF < 0.8, or live DD exceeding G7, or two consecutive sessions with inter-tick premium move > 40% of E (cadence/gap alert → drop to 30 s or halt).
- Execution remains blocked on static IP today; the pilot is a **rule**, not a date.

**SPT-7 output:** the table above, plus MFE/MAE histograms vs the −30/+50 lines, inter-tick jump percentiles (cadence review), and the advisory-vs-paper disagreement table.

---

## Dissenting Notes

**Module boundary.** A minority `data_architecture` view still prefers B: a naked long with a 15:00 hard-exit is not “degenerate IC”; putting it on `PaperStore` couples a daily-churn strategy to a ledger built for multi-day short-premium cycles (`TradeState`, overlay rolls, `paper_nav_snapshots` semantics). The majority view: that coupling is one `strategy_name` and a pure evaluator; B’s operational cost (second heartbeat, second holiday guard, second fill path that will *drift* from `PaperFillSimulator`) is larger than the conceptual impurity. **Compromise the minority actually needs — and A already gives — is “not `ExitSignalEngine`,” not “not `PaperStore`.”**

**Own table.** Rejected. If Phase 2 wants richer per-tick analytics, add a **mark-path** table keyed by `paper_trades` id, not a second position book.

**−30 / +50.** `greeks-analyst` minority: at 8–12 DTE (just after the roll threshold) gamma is high enough that −30% can print on a garden-variety 0.4% Nifty dip, i.e. the stop may be **tight vs noise** near the roll. Majority: that is exactly what N = 30 MFE/MAE is for; widening SL pre-data would bake in larger left-tail fills. Do not confidence-scale; if anything, a **future** review may widen SL when DTE ≤ 10 rather than when confidence = 5.

**Breakeven-from-day-one.** One options-strategist vote for a pure BE at +25% unrealised as “free insurance.” Rejected: not free under intraday mean reversion; contaminates the MFE/MAE sample you need to design Phase 2 (you would never observe give-backs through the dead band). If N = 30 shows median winner MFE ≫ 50% and brutal give-backs through SL, pull BE forward as an **out-of-cycle** patch, not as Phase 1 scope.

**90 s cadence.** Strongest dissent. A naked ATM long can gap 20–40% of premium on a CPI/RBI print inside one 90 s hole; paper then **understates** SL frequency and **understates** MFE (path extrema missed). Counter: (1) the paper series is only faithful if it uses the live tick; (2) tightening the **global** monitor hammers every credit strategy’s chain fetch; (3) a 15 s sidecar is option B in disguise. **Majority: 90 s, log jumps, tighten only on evidence.** Minority addendum worth writing into SPT-4: flag any inter-tick `|ΔM|/E| > 0.20` and, if ≥ 5 such events in 30 trades, trigger a cadence mini-review **before** 6 months — still not a dedicated loop on day one.

**Go-live N = 50 vs N = 30.** N = 30 is enough to notice a broken stop, not enough to promote. Do not let the recalibration trigger and the promotion trigger collapse into one number.

**Operator draft `signal_track_v1`.** Non-negotiable rename to **`paper_signal_track_v1`**. Shipping without `paper_` is a live/paper ledger contamination bug, not a style choice.

**S5.5a.** Once SPT-5’s exit Telegram is live, mark signals S5.5a `won't-do` and point it here; do not run two 15:00 outcome messages.

### deepseek/deepseek-r1-0528

I've reviewed all provided context files (`CONTEXT.md`, `prompt.md`, `stories.md`, `council-question.md`, `models.py`, `option_resolver.py`, `CLAUDE.md`, `executor.py`, `monitor.py`, `DECISIONS.md`, `BACKTEST_PLAN.md`) and confirm `CONTEXT.md ✓`. 

The scope for SPT-1 is **council checkpoint - no code**. Key constraints:
1. Must resolve module boundary decision (reuse `src/strategy` vs self-contained)
2. Must validate trade rule design (SL/target levels, trailing stop, cadence)
3. Must propose go-live gate metrics
4. Output must be Council prompt + specs rewrite

**Plan:**
1. Analyze module boundary trade-offs per `council-question.md`
2. Draft council prompt with `strategy_parameters` primary frame
3. Formalize proposed SL/target/trailing rules
4. Specify go-live gate criteria
5. Output rewritten SPT-2..SPT-8 tasks + schema.md structure
6. Save to `docs/council/signals-paper-track_2026-09-12.md`

**Files touched:**
```markdown
- docs/council/signals-paper-track_2026-09-12.md (new)
- docs/plan/signals-paper-track/tasks.md (rewrite)
- docs/plan/signals-paper-track/schema.md (new)
- docs/plan/signals-paper-track/stories.md (rewrite)
- DECISIONS.md (appendix entry)
```

**Key considerations:**
1. `StrategyMonitor`'s 90s cadence risks missing sharp moves on naked options
2. Existing `ExitSignalEngine` vocabulary mismatch (short-premium vs long-directional)
3. Need ≤7-DTE roll tests before SPT-3
4. Telegram message format must unify with EOD reports
5. MFE/MAE logging essential for dynamic exit design

Proceeding to draft council prompt now.

## Aggregate Rankings (Stage 2 Peer Review)

- openai/gpt-5.6-sol: avg rank 1.5 (4 votes)
- x-ai/grok-4.6: avg rank 1.5 (4 votes)
- google/gemini-3.1-pro-preview: avg rank 3.0 (4 votes)
- deepseek/deepseek-r1-0528: avg rank 4.0 (3 votes)

---

## Prompt Sent (first 3000 chars)

```
=== NIFTYSHIELD PROJECT STATE ===

# NiftyShield — Project Context

> **For AI assistants:** This file is the authoritative state of the codebase.
> Read this before writing any code. Do not rely on session summaries or chat history.
> Repo: https://github.com/archeranimesh/NiftyShield

**Related files:**
[MISSION.md](MISSION.md) — immutable mission + grounding principles |
[DECISIONS.md](DECISIONS.md) | [REFERENCES.md](REFERENCES.md) | [TODOS.md](TODOS.md) |
[PLANNER.md](PLANNER.md) | [BACKTEST_PLAN.md](BACKTEST_PLAN.md) — Phase 0 active tasks only
(~300 lines) | [BACKTEST_PLAN_PHASE1.md](BACKTEST_PLAN_PHASE1.md) — Phase 1+ tasks (load only
after Phase 0.8 gate) | [LITERATURE.md](LITERATURE.md) — concept reference (Kelly, Sharpe,
meta-labeling) | [LOGGING.md](LOGGING.md) — logging standard | [docs/plan/](docs/plan/) — one
story file per task | [INSTRUCTION.md](INSTRUCTION.md)

---

## Current State (as of 2026-08-26)

### What Exists (committed and working)

Full file-level module tree with per-file descriptions: **[CONTEXT_TREE.md](CONTEXT_TREE.md)**.
Feature and bug-fix history with rationale (every `BUG-*` / `SNAP-*` / `PG-*` / council
ruling referenced below): **[DECISIONS.md](DECISIONS.md)**.
Verbatim snapshot of the previous prose version of this section (nothing was deleted, only
relocated): **[docs/archive/CONTEXT_WHAT_EXISTS_2026-08.md](docs/archive/CONTEXT_WHAT_EXISTS_2026-08.md)**.

Top-level `src/` packages, one line each (detail → `CONTEXT_TREE.md`):

- `src/auth/` — Upstox OAuth + Nuvama request_id + Dhan manual-token login/verify flows.
- `src/client/` — `BrokerClient` protocol + 4 impls (Upstox live/sandbox, Mock); `factory.create_client(env)`; order exec + portfolio read blocked (static IP / daily token).
- `src/models/` — canonical domain types: `Leg`/`Trade`/`Strategy`/`DailySnapshot`/`PortfolioSummary` (portfolio.py), MF types (mf.py), `OptionLeg`/`OptionChain` frozen Pydantic (options.py).
- `src/portfolio/` — live (non-paper) P&L: `PortfolioStore`, `PortfolioTracker`, pure `summary.py`/`formatting.py`, `SnapshotService`, `overlay_coverage.py`; finideas strategies (ILTS, FinRakshak).
- `src/paper/` — paper-trading engine. Models: `PaperTrade`, `PaperPosition`, `PaperNavSnapshot`,
  `PaperLegSnapshot`, `PaperExitEvent`, `TrackComparisonSnapshot`, `TradeState` enum. `PaperStore`
  (SQLite — `paper_trades`, `paper_nav_snapshots`, `paper_leg_snapshots`, `paper_exit_events`,
  `gate_violations`, `warn_signal_state`, `paper_track_comparison_snapshots`, …). `PaperTracker`
  (`compute_pnl`, `compute_pnl_by_leg_group`), fill simulator, selectors.
- `src/strategy/` — paper-backbone strategy layer. `PaperStrategy` protocol,
  `SignalEvent`/`ApprovedAction`/`LegSpec`/`LegClose`, `StrategyMonitor` daemon (tick loop, WARN
  dedup, auto-execute dispatch), `PaperExecutor`, `ReEntryMixin`. 7 strategies: `CSPNiftyV1`,
  `CCOverlayV1`, `PPOverlayV1`, `CollarOverlayV1`, `IronCondorV1`, `IronCondorV2`,
  `NiftyTrackComparisonV1`. Engines: `ExitS...
```
# CSP v1 Variance Gate — Full Specification

**Source decision:** `docs/council/2026-05-02_variance-gate-regime-completeness.md`  
**Supersedes:** Original Phase 0.8 single bullet "≥6 cycles with one of each exit type"  
**Canonical strategy spec:** `docs/strategies/csp_nifty_v1.md`

---

## Purpose

This document specifies the complete deployment gate for CSP v1 Nifty options strategy. It defines
what must be true before any live capital is deployed, and the graduated permission structure
governing capital commitment as evidence accumulates post-deployment.

The gate has two distinct roles:

- **Exit-type completeness** — validates implementation correctness: code paths, P&L attribution, order logic
- **Regime completeness** — validates strategy behaviour under stress: a different failure mode

Both are necessary. Neither subsumes the other.

---

## Phase 0.8 Gate Criteria (A–D)

All four must pass before Phase 1 begins.

### A — Minimum Paper Sample

> ≥6 executed paper CSP cycles **and** ≥9 calendar months of entry-decision observation
> (whichever comes later).

- Cycles skipped by R3/R4/event filters count as **filter-validation observations**, not executed cycles.
- Do not force trades to satisfy the count — the strategy is behaving correctly when it skips.
- If R3 keeps skipping entries for months (persistent low IVR), this is correct behaviour; document skips in `TODOS.md` for audit, not as failures.

### B — Exit-Path Validation

Each exit mechanism must be validated at least once through **either** live paper occurrence **or** deterministic historical replay using the same strategy logic, data schema, cost model, and P&L attribution code.

| Exit Type | Validation Requirement |
|---|---|
| Profit target (50%) | Live paper preferred; historical replay acceptable |
| Time stop (21-day) | Live paper preferred; historical replay acceptable |
| Delta/mark stop | Live paper required before Tier 2 scaling; replay acceptable for Tier 1 pilot |

**What "historical replay" means:** Run the production paper-trade code against a known historical stress episode (e.g., COVID week of 2020-03-16, IL&FS week of 2018-09-21) injected into the staging environment. This validates that the monitoring daemon correctly identifies the trigger condition, queues the exit, and records P&L — without waiting for the market to crash.

Do not build the replay harness until Phase 1 backtest data pipeline (task 1.3) is live. See `TODOS.md → Define historical replay harness`.

### C — Regime Completeness (supplementary)

At least **one** of the following three stress conditions must be observed or replayed before Tier 1 pilot deployment:

| Regime Criterion | Definition | Validation Method |
|---|---|---|
| **High IVR** | ≥1 cycle with IVR > 50 at entry | Live paper preferred; historical replay acceptable |
| **Drawdown stress** | ≥1 holding window with ≥5% Nifty intraday peak-to-trough decline | Monitor via `nuvama_intraday_tracker.py`; replay acceptable |
| **Delta pressure** | ≥1 cycle where short-put delta reaches ≤ −0.35 before any exit fires | Live paper preferred; replay acceptable |

If the market does not naturally provide any of these within 9 calendar months, use historical replay. Do not hold deployment hostage to exogenous market events indefinitely.

**IVR requirement:** India VIX ingestion must be live before IVR can be computed or logged at entry. See `TODOS.md → India VIX ingestion`. This task must complete before criterion C can be evaluated.

### D — Regime-Matched Z-Score

> `|Z| ≤ 1.5` on **both**:
> 1. The full 8-year backtest distribution
> 2. A regime-matched subset (filter backtest for cycles with IVR/vol conditions matching the paper period)

The global comparison alone is insufficient: 6 calm paper cycles compared against an 8-year distribution including COVID and IL&FS produces a spurious variance flag not because the system is broken, but because the paper sample is drawn from a non-stationary subset.

**Z-score role:** This is a **drift smoke test only**, not statistical proof. At N≈6, `|Z| ≤ 1.5` has <40% power to detect realistic operational drift (0.25–0.75 SD mean degradation). A pass means "no gross mismatch detected yet." It unlocks **Tier 1 limited pilot only**.

See Task 1.11 in `BACKTEST_PLAN.md` for computation methodology.

---

## Statistical Power Analysis

At N=6, under idealized assumptions (normal P&L, known backtest σ, independent observations):

| True Mean Drift (in SDs) | Expected Z at N=6 | P(gate detects drift) | P(false pass) |
|---|---|---|---|
| 0.25 SD | ~0.61 | ~19% | ~81% |
| 0.50 SD | ~1.22 | ~40% | ~60% |
| 0.75 SD | ~1.84 | ~63% | ~37% |
| 1.00 SD | ~2.45 | ~83% | ~17% |
| 2.00 SD | ~4.90 | >99% | <1% |

Realistic operational degradation — slippage doubling, stale delta chains, wider bid/ask in stress — typically manifests as 0.25–0.75 SD drag. The gate has <40% power to catch these at N=6.

Additionally, the sample standard deviation at N=6 has a 95% CI of ~0.62× to 2.45× the true value — too wide to use as a strong deployment proof.

The Z-score correctly serves as a gross implementation failure detector. The graduated deployment tiers below compensate for its weakness.

---

## Graduated Deployment Tiers

Because one Nifty lot is indivisible, "graduated" means graduated **permissions**, not fractional sizing.

### Tier 0 — Paper Only (current)

Requirements:
- Strategy implemented; recording works; P&L reconciles
- Entry/exit reason codes logged with full fields (IV, IVR, VIX, delta, bid/ask/mid, DTE)
- No live capital

### Tier 0.5 — Two-Cycle Operational Review (≈Month 2)

After first 2 executed cycles, informal sanity check (not statistical validation — catches plumbing errors early):

- Was the selected strike actually closest to target delta?
- Were bid/ask/mid and fill assumptions recorded correctly?
- Did P&L reconcile to option marks?
- Was NiftyBees collateral P&L included correctly?
- Were any entries correctly skipped under R3/R4?

### Tier 1 — Limited Live Pilot Eligibility (N≥6)

**Entry requirements — all must hold:**
- All Phase 0.8 gate criteria A–D met
- No unresolved accounting or data defects
- `|Z| ≤ 1.5` on regime-matched comparison
- All exit paths validated (live or replay)
- At least one stress path validated (replay acceptable)

**Constraints:**
- 1 lot maximum (65 units) — full strategy size; "graduated" means graduated permissions
- Manual approval required for every live entry
- No discretionary rolling or adjustment
- No live deployment if current regime was entirely absent from both paper and replay

### Tier 2 — Normal v1 Live Operation (N≥12 or 6 + stress)

**Entry requirements:**
- 12 executed cycles, **or** 6 cycles plus ≥1 genuine live/paper stressed episode
- At least one delta/mark-stop path observed live (not only replay)
- Slippage remains within R7 model tolerance
- No rule overrides during any cycle
- Drawdown remains within expected envelope (≤₹6L max on ₹1cr)

### Tier 3 — Integration with NiftyShield Overlay (N≥18–24)

**Entry requirements:**
- Full regime coverage through live + replay
- Verified high-IVR behaviour
- Verified hedge-overlay interaction (protective put spread)
- Backtest/paper/live reconciliation clean
- 18–24 executed cycles

---

## Spec Consistency Prerequisite

Before codifying this gate, reconcile the active CSP spec with the decision-domain summary. Unreconciled spec = blocked gate. Resolve in Phase 0.7 validator pass.

Open mismatches to resolve:
- **Nifty lot size:** strategy spec says 65 units; some references say 50
- **Time stop:** spec says 21 calendar days from entry; some references say 21 DTE remaining
- **R-number naming:** inconsistent between `csp_nifty_v1.md` and `BACKTEST_PLAN.md`
- **R4 definition:** spec mentions event filter; some references mention 200-DMA trend filter

The gate references `docs/strategies/csp_nifty_v1.md` as the single source of truth once reconciled.

---

## What NOT to Build Now

- Do not build the replay harness until Phase 1 backtest data pipeline (task 1.3) exists
- Do not add new monitoring scripts beyond `daily_snapshot.py` + `paper_snapshot.py`
- Do not add database schema changes for deployment tiers — this is a human decision gate, not an automated system

---

## Related Documents

| Document | Role |
|---|---|
| `DECISIONS.md → Variance Gate` | Authoritative decision record |
| `BACKTEST_PLAN.md § 0.8` | Gate checklist |
| `BACKTEST_PLAN.md § 1.11` | Regime-matched Z-score computation |
| `docs/strategies/csp_nifty_v1.md` | Canonical strategy spec (gate's source of truth) |
| `docs/council/2026-05-02_variance-gate-regime-completeness.md` | Council decision (full deliberation) |
| `TODOS.md → Define historical replay harness` | Replay harness design task |
| `TODOS.md → India VIX ingestion` | IVR computation prerequisite |

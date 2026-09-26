# Council Question 3 — Variance Gate: Exit-Type Completeness vs Regime Completeness

## Why This Is Council-Worthy

1. **Load-bearing and costly to reverse.** The Phase 0.8 gate and task 1.11 variance check are
   the single gates between paper trading and live deployment. The criteria written into these
   gates define what "validated" means. If the completeness requirement is wrong — too permissive
   (live deployment on insufficient evidence) or too restrictive (blocking deployment when the
   strategy has genuine edge) — the consequences are capital at risk or indefinitely deferred
   income generation. Both outcomes damage the mission.

2. **Two defensible approaches with materially different outcomes.** The current gate requires
   three exit types (profit-target, time-stop, delta-stop) to be triggered at least once each
   across 6 cycles. This is an *exit-type completeness* gate. An alternative is a *regime
   completeness* gate: the paper window must contain at least one high-IVR cycle (IVR > 50),
   one low-IVR cycle (IVR 25–40), and one cycle that includes a ≥5% Nifty intraday drawdown.
   These two frameworks produce different gate-open probabilities: exit-type completeness
   can be satisfied in a calm, range-bound 6-month period; regime completeness cannot be
   satisfied by luck alone and requires genuine market stress exposure.

3. **Spans multiple disciplines.** Statistics (sample size, statistical power of N=6, selection
   bias when all 6 cycles happen to be in one regime), options strategy design (the strategy
   behaves differently in different regimes by explicit spec — the IVR filter, event filter,
   and delta-stop are regime-sensitive), and practical execution management (adding a regime
   requirement may extend Phase 0 beyond 6 months if the market stays benign — this has
   calendar and capital deployment cost implications).

---

## Command

```bash
python scripts/ask_council.py \
    --topic variance-gate-regime-completeness \
    --template strategy_parameters \
    --context docs/strategies/csp_nifty_v1.md \
    --question "The CSP v1 variance gate (Phase 0.8 and task 1.11) requires: (a) ≥6 full monthly expiry cycles; (b) at least one profit-target exit, one time-stop exit, and one delta-stop exit triggered; (c) |Z| ≤ 1.5 between paper-trade monthly P&L distribution and backtest distribution (bias-adjusted). The exit-type completeness criterion (b) was designed to ensure all three exit mechanisms have been exercised at least once. The gap this question identifies: what if all 6 cycles occur in a benign, range-bound, moderate-IVR regime? The paper distribution would reflect one narrow regime slice, and the variance check against the backtest (which covers 8 years including COVID, IL&FS, and 2022 selloff) would pass only because both distributions happen to be well-behaved in calm markets — not because the strategy's behaviour under stress has been validated. Concretely: if the first 6 paper cycles all run May–October 2026, India VIX stays 12–18 throughout (IVR 20–45), no month sees a ≥5% intraday Nifty decline, and the delta-stop never fires despite being a required exit type (just by market luck), the gate would require additional cycles. But if IVR stays low, the R3 filter would skip entry, meaning the strategy might not even produce 6 cycles in 6 calendar months. The question has two parts: (1) Should the gate replace or supplement exit-type completeness with regime completeness (minimum one cycle with IVR > 50, minimum one cycle with a ≥5% Nifty intraday drawdown, minimum one cycle where delta approaches -0.35 or closer before the profit target fires)? (2) At N=6 monthly cycles, what is the statistical power of the |Z| ≤ 1.5 variance check to detect a strategy with genuine drift (e.g., a 2-SD structural shift in mean return)? Is N=6 sufficient to trust a passing Z-score, or does the deployment decision need a secondary criterion (e.g., month-2 informal check + graduated deployment tiers) to compensate for the thin sample?"
```

---

## Parameters Summary

| Parameter  | Value                                                                        |
|------------|------------------------------------------------------------------------------|
| `--topic`  | `variance-gate-regime-completeness`                                          |
| `--template` | `strategy_parameters`                                                      |
| `--context` | `docs/strategies/csp_nifty_v1.md`                                          |
| `--question` | See command above                                                          |

---

## Additional Context Files

- `BACKTEST_PLAN.md` §0.6, §0.8, §1.11 (gate conditions and variance check methodology)
- `docs/reviews/backtest_plan_pm_review_2026-04-27.md` §3 (MVP kill criteria — month-3 checkpoint,
  graduated deployment tiers; the PM review already proposed some mitigations)
- `docs/strategies/csp_nifty_v1.md` §Variance Threshold section (current Z-score formula and
  bias-adjustment methodology)

## What This Decision Unlocks

- The Phase 0.8 gate checklist (BACKTEST_PLAN.md) — may need an additional regime-completeness
  bullet point
- The task 1.11 variance check implementation — if regime completeness is added, the check
  must tag paper cycles by regime and report the distribution
- The graduated deployment tier table in the PM review (|Z| ≤ 0.5 → full size, etc.) —
  should the tiers differ based on whether regime completeness was achieved?
- The month-2 interim Z-check: the council's answer on statistical power at N=6 directly
  determines whether the interim check at N=2 is actionable or purely diagnostic

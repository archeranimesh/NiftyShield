# Council Question 7 — Continuous Re-Validation: Statistical Power at Low N and Early Deployment

## Why This Is Council-Worthy

1. **Load-bearing and costly to reverse.** Task 2.1 (continuous re-validation — weekly Z-score
   monitoring) is the safety net between live deployment and catastrophic loss. If the monitoring
   framework is statistically too weak (Z-score is uninformative at N=6–12 monthly trades), live
   capital is at risk from an undetected strategy drift. If it is too strict (overly sensitive
   Z-score triggers false positives from normal variance), the strategy is paused on every
   volatile month, destroying the income thesis. The monitoring design is permanent — it runs
   for as long as the strategy is live.

2. **Two defensible approaches with materially different outcomes.** Option A: **run the weekly
   Z-score from day one of live deployment** with N starting at 1 and growing. The Z-score at
   N=3 or N=4 is largely noise, but the framework is consistent and any |Z| > 2.0 at any N
   triggers the pause protocol (from the PM review). Risk: false pauses due to low-N noise.
   Option B: **defer the Z-score to a minimum N** (e.g., N=8 cycles before the continuous
   re-validation has sufficient power) and use a different signal during early deployment —
   e.g., a hard per-trade P&L guard (any single cycle loss > 3× trailing average credit stops
   the strategy; kill criterion R6 already exists in the spec). These two approaches have
   materially different false-positive rates and different windows of undetected drift risk.

3. **Spans multiple disciplines.** Statistics (sample size and power of sequential Z-tests,
   CUSUM and other sequential hypothesis tests designed for small-N sequential monitoring),
   options strategy management (monthly CSP has only 6–12 observations per year — fundamentally
   different from a daily signal with 200+ annual data points), and operational continuity
   (pausing a strategy "early" because the monitoring fired a false alarm costs both income
   and paper-to-live transition momentum — there is a real second-order cost to false positives
   that pure statistics ignores).

---

## Command

```bash
python scripts/ask_council.py \
    --topic continuous-revalidation-statistical-power \
    --template backtest_methodology \
    --context docs/strategies/csp_nifty_v1.md \
    --question "Task 2.1 in BACKTEST_PLAN.md specifies weekly Z-score monitoring for live strategy re-validation: compute rolling Z-score = (live_mean_monthly_pnl − backtest_mean) / backtest_std, with alert thresholds at |Z| 1.5–2.0 for 3 consecutive weeks (reduce to paper-only) and |Z| > 2.0 single week (halt all live trading). The problem: the CSP strategy completes ~1 trade per month, which is ~12 data points per year and ~6 by the time live deployment starts. At N=6, a Z-score computed against a backtest distribution of 96 monthly observations (8 years × 12 months) has extremely low statistical power. Concretely: a strategy that has genuinely drifted 1.5 sigma from its backtest mean will only be detected with ~40–50% probability at N=6 (standard power analysis). Conversely, a correctly functioning strategy will produce |Z| > 1.5 by pure variance approximately 13% of the time at any given monthly check. At weekly Z-score monitoring frequency (about 4 checks per month), the false-positive probability over the first 3 months of live trading is substantial. Three specific questions: (1) MONITORING METHOD: Is a standard rolling Z-score the right method for a strategy with ~12 observations per year, or should a CUSUM (Cumulative Sum Control Chart) or Shiryaev-Roberts sequential test be used instead? CUSUM is specifically designed for small-N sequential monitoring and has a lower false-alarm rate at equivalent detection delay. If CUSUM is appropriate, what are the recommended h (threshold) and k (reference value) parameters for the CSP's expected return and standard deviation profile? (2) MINIMUM N BEFORE Z-SCORE IS INFORMATIVE: At what N does the Z-score first achieve sufficient statistical power (β ≥ 0.80 at the 1.5-sigma alternative) to be decision-relevant? Should the halt/reduce protocol from the PM review apply from day one, or only after this minimum N is reached? (3) EARLY DEPLOYMENT GUARD: During the period before minimum N is reached, what alternative monitoring metric should serve as the primary safety signal? The CSP spec already has per-cycle kill criterion R6 (single cycle loss > 3× trailing-12-cycle average credit → automatic pause). Is R6 sufficient as the sole guard during early deployment, or does it need to be supplemented with a rolling drawdown check or regime-divergence flag?"
```

---

## Parameters Summary

| Parameter  | Value                                                                        |
|------------|------------------------------------------------------------------------------|
| `--topic`  | `continuous-revalidation-statistical-power`                                  |
| `--template` | `backtest_methodology`                                                     |
| `--context` | `docs/strategies/csp_nifty_v1.md`                                          |
| `--question` | See command above                                                          |

---

## Additional Context Files

- `BACKTEST_PLAN.md` §2.1 (continuous re-validation task specification — weekly cron, Z-score
  formula, Telegram alert thresholds from PM review)
- `docs/reviews/backtest_plan_pm_review_2026-04-27.md` §6 (graduated deployment tiers and
  post-live monitoring triggers — the monitoring design the council answer must integrate with)
- `BACKTEST_PLAN.md` §1.11 (variance check methodology — the Z-score formula used for
  continuous re-validation should be consistent with 1.11's bias-adjusted Z-score)

## What This Decision Unlocks

- `src/backtest/continuous.py` implementation (task 2.1) — specifically, whether the module
  implements a standard Z-score or a CUSUM/SR sequential test, what the alert thresholds
  are, and whether there is a minimum-N guard before the primary monitoring activates
- The `2.1a` cron healthcheck design — the healthcheck monitors whether the monitoring ran;
  the council answer determines what "ran successfully" means in terms of reporting a
  meaningful vs. noise Z-score
- The operational runbook (not yet written) for the live CSP deployment: the runbook must
  specify exactly which metric to check first when the Telegram alert fires, and in what
  order to investigate. The council answer defines the primary signal hierarchy.

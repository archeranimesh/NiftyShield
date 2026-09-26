# Council Question 1 — CSP v2 Entry Delta: 20-delta vs 25-delta

## Why This Is Council-Worthy

All three conditions are met:

1. **Load-bearing and costly to reverse.** The entry delta is hardcoded into the CSP backtest
   engine config (`CSPConfig`) in task 1.7. It drives strike selection across the entire 8-year
   Bhavcopy history, the variance check distribution in task 1.11, and the live paper-trade
   ledger. Changing it after the backtest is complete requires a full re-run plus a new paper
   window.

2. **Two defensible approaches with materially different outcomes.** 25-delta: higher credit
   (₹60–90/unit more), win rate ~68%, delta-stop fires ~25–30% of cycles. 20-delta: lower
   credit, win rate ~74–78%, delta-stop fires ~12–16% of cycles. The risk-adjusted (Calmar)
   outcome is structurally different, not cosmetically different.

3. **Spans multiple disciplines.** Options microstructure (NSE put skew, bid-ask width at 20 vs
   25 delta), quantitative modelling (Calmar, exit-type frequency distribution), Indian execution
   reality (lot size = 65, SPAN margin differs by delta), and the specific 21-day hold period
   that creates asymmetric gamma exposure near expiry.

**Not a parameter sweep.** A sweep over [15, 20, 25, 30]-delta without structural reasoning
is fitting noise. This question asks for the mechanistic basis for the optimal delta and
whether the paper trade exit-type log (profit-target vs time-stop vs delta-stop frequency)
is sufficient evidence to decide, or whether the backtest must generate this answer.

---

## Command

```bash
python scripts/ask_council.py \
    --topic csp-entry-delta-v2 \
    --template strategy_parameters \
    --context docs/strategies/csp_nifty_v1.md \
    --question "CSP v1 targets 25-delta monthly Nifty puts (65-unit lot, 30–45 DTE, 21-day hold, R2 delta-stop at -0.45, R7 slippage model). After 6+ paper cycles, the exit-type frequency will reveal stop-firing rates. The v2 question is whether 20-delta is structurally superior for this specific setup. The design dimensions that change at 20-delta vs 25-delta: (a) credit collected (~30–35% less at 20-delta in a 30–35 IVR environment); (b) delta-stop firing frequency (roughly halves — 20-delta sits at a lower gamma region throughout the 21-day hold); (c) theta-to-gamma ratio at 21 DTE (20-delta is more favourable — lower gamma acceleration during the peak-theta window); (d) bid-ask spread as % of premium (widens at 20-delta, degrading slippage economics). The 21-day hold period is the key differentiator from a standard 50%-profit-target CSP: the system holds into peak gamma intentionally, making the choice of starting delta load-bearing for tail risk. The R2 delta gate at -0.45 fires when the put is already deep ITM; at 20-delta entry, the journey from -0.20 to -0.45 requires a larger Nifty decline, reducing stop frequency but also reducing the early-warning function of the gate. Question: What is the theoretically optimal entry delta for a monthly Nifty CSP with a fixed 21-day hold period, a -0.45 delta-stop, and a 50%-profit-target, when validated over the Indian market's specific skew structure and FII-flow-driven trend regime? Should the v2 decision wait for paper trade exit-type data (is N=6-8 sufficient?) or can the answer be derived analytically from the known Nifty vol surface properties?"
```

---

## Parameters Summary

| Parameter  | Value                                                                        |
|------------|------------------------------------------------------------------------------|
| `--topic`  | `csp-entry-delta-v2`                                                         |
| `--template` | `strategy_parameters`                                                      |
| `--context` | `docs/strategies/csp_nifty_v1.md`                                          |
| `--question` | See command above                                                          |

---

## Additional Context Files (read before submitting)

- `BACKTEST_PLAN.md` §1.7 (CSP strategy implementation spec, config parameters)
- `docs/reviews/backtest_plan_pm_review_2026-04-27.md` §3 (MVP definition — win rate thresholds)
- `DECISIONS.md` → Slippage Model (R7 values at 20-delta are wider percentage-wise)

## What This Decision Unlocks

- The `CSPConfig` delta parameter in task 1.7
- The V1/V2/V3 backtest variant definitions in task 1.8 (V1 = no re-entry, V2 = R5 re-entry — the delta target
  is currently fixed at 25 across all three variants, or should it differ?)
- The re-entry R5 rule threshold: R5 requires DTE ≥ 14 AND IVR ≥ 25 after a profit-target exit. At 20-delta
  the re-entry target also changes — the council answer should address whether V2 re-entry
  at 20-delta is still the same logic or needs a different delta target for the re-entry leg.

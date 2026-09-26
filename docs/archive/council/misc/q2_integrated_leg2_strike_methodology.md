# Council Question 2 — NiftyShield Integrated: Leg 2 Protective Put Spread Strike Methodology

## Why This Is Council-Worthy

1. **Load-bearing and costly to reverse.** Leg 2's strike selection method is baked into:
   (a) task 1.9 (synthetic pricer design — the skew model must be calibrated to the actual
   strike range being priced); (b) task 1.9a (integrated strategy backtest, which prices
   8 years of historical put spreads at these strikes); and (c) the annual lot-count
   rebalancing formula. Changing from %OTM to delta-based after the synthetic pricer is
   built requires a full backtest re-run and a recalibrated skew model.

2. **Two defensible approaches with materially different outcomes.** Percentage-OTM (8%/20%
   below spot) is regime-insensitive: at Nifty 24000, the long put is always near 22050
   regardless of IV level, meaning the hedge activates at the same nominal price whether
   IVR is 20 or 70. Delta-based (long at 15-delta, short at 5-delta) adapts to the IV surface:
   in a high-IVR (60+) environment the 15-delta strike may be only 5–6% OTM (tighter
   protection), while in low-IVR the same delta lands 10–12% OTM (looser protection). These
   produce structurally different hedge payoff profiles in the 8–15% correction zone that is
   the strategy's primary mandate.

3. **Spans multiple disciplines.** Options pricing theory (the vol smile at 8% vs 15% OTM is
   dramatically different — skew markup of +3–8 IV points), hedge theory (delta-equivalent
   notional hedged changes with IV regime), backtesting fidelity (synthetic BS pricer for
   8%/20% OTM strikes requires a skew model; delta-based pricing has tighter BS accuracy
   near-ATM), and NSE execution reality (8% OTM put on monthly Nifty has OI of a few
   hundred contracts vs 15-delta which has a few thousand — execution quality differs).

---

## Command

```bash
python scripts/ask_council.py \
    --topic integrated-leg2-strike-methodology \
    --template strategy_parameters \
    --context docs/strategies/niftyshield_integrated_v1.md \
    --question "The NiftyShield Integrated strategy (see context file) uses Leg 2 (protective put spread) with strikes defined as fixed percentages of spot: long put at 8% below spot (activation threshold), short put at 20% below spot (tail cap). The 4-lot sizing is calibrated to hedge 65% of ₹100L effective Nifty exposure. The open question for v2 is whether strike selection should switch to delta-based (long put at 15-delta, short put at 5-delta). The competing considerations: (1) REGIME SENSITIVITY: %OTM selects a fixed nominal price zone regardless of vol; delta-based selects the same probability-of-breach zone. In a pre-crash buildup (VIX rising from 14 to 22), the 15-delta put shifts inward from 10% OTM to 7% OTM — protection activates earlier precisely when it is most needed. (2) COST VARIANCE: In a high-IVR environment, %OTM strikes are cheaper per unit (further out on the smile); delta-based strikes are more expensive (closer in). The annual budget is 3–5% of MF portfolio value (₹2.4L–₹4L). Under %OTM, cost is more predictable; under delta-based, cost spikes in high-IV regimes that are also the highest-risk periods. (3) SYNTHETIC PRICER FIDELITY: The Phase 1 task 1.9 synthetic pricer uses BS with a parametric skew model. At 8% OTM (ATM−38 to ATM−48 strikes), BS systematically underprices by 10–20% (smile not captured). At 15-delta (ATM−12 to ATM−20 in low-vol, ATM−8 to ATM−14 in high-vol), BS is more accurate. (4) DEAD ZONE SENSITIVITY: Both methods leave a dead zone (5–8% Nifty decline where CSP is losing but protection hasn't activated). Does delta-based selection narrow or widen this dead zone in practice? (5) LIQUIDITY: 15-delta Nifty monthly put at 30–45 DTE typically has OI of 5,000–15,000 contracts; 8% OTM has OI of 500–2,000. For 4 lots (260 units), execution quality matters. Question: Which strike selection methodology produces more reliable hedge payoff in moderate (8–15%) corrections given NSE's specific vol skew structure, and which methodology is more consistent with the strategy's primary mandate of protecting the ₹80L+ MF portfolio during moderate corrections?"
```

---

## Parameters Summary

| Parameter  | Value                                                                        |
|------------|------------------------------------------------------------------------------|
| `--topic`  | `integrated-leg2-strike-methodology`                                         |
| `--template` | `strategy_parameters`                                                      |
| `--context` | `docs/strategies/niftyshield_integrated_v1.md`                             |
| `--question` | See command above                                                          |

---

## Additional Context Files

- `docs/strategies/csp_nifty_v1.md` (Leg 1 rules — strike selection by delta for the short put)
- `BACKTEST_PLAN.md` §1.9 and §1.9a (synthetic pricer and integrated backtest tasks)
- `DECISIONS.md` → IV Reconstruction Methodology (2026-04-30) (quadratic smile fit methodology
  already decided — council answer must be compatible with this)

## What This Decision Unlocks

- `CSPConfig`-equivalent struct for Leg 2 in task 1.9
- The skew model calibration range in task 1.9 (must cover the actual strikes being priced)
- The `lot_count` rebalancing formula in the annual reset procedure (currently fixed at 4 lots;
  delta-based would make it variable, requiring a more complex rebalancing rule)
- Paper trade data capture format for task 0.6a: if delta-based, the paper log must record
  actual delta at entry for each protective leg (currently only recorded for Leg 1)

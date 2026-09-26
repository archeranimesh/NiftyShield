# Council Question 5 — Iron Condor v1: Core Design on Nifty Given the Put-Call Skew

## Why This Is Council-Worthy

1. **Load-bearing and costly to reverse.** The IC v1 specification (task BACKTEST_PLAN.md §2.3,
   not yet written) will gate task 2.4 (IC implementation), task 2.5 (IC backtest), and
   task 2.6 (IC paper trading for 6+ months before Phase 3 live deployment). A wrong design
   decision — particularly on symmetric vs. asymmetric delta targets and the adjustment rule —
   is embedded in 12+ months of backtest history and paper trade log. Re-specifying IC v2
   after that is effectively starting from scratch.

2. **Two defensible approaches with materially different outcomes.** Symmetric IC (identical
   delta for short put and short call, e.g., both at -0.15/+0.15): cleaner delta-neutral entry,
   simpler to backtest, standard academic approach. Asymmetric IC (short put delta higher in
   magnitude than short call, e.g., -0.20 put / +0.10 call): reflects Nifty's put skew (puts
   carry 2–5 IV points more than equidistant calls at the same DTE), collecting more net credit
   from the structurally richer put side while taking less risk on the call side (Nifty's upside
   is structurally less volatile than its downside). The P&L profile, win rate, and max loss
   are materially different: symmetric IC has a centred P&L tent; asymmetric IC has a right-
   skewed tent (wider profit zone on the upside, tighter on the downside).

3. **Spans multiple disciplines.** Options microstructure (Nifty put skew empirics — magnitude
   of IV differential between equidistant put and call strikes), delta-neutral strategy design
   (should the IC start net-delta-neutral or net-delta-long to compensate for skew?), NSE
   execution reality (4-leg IC on Nifty monthly: bid-ask on 2 spreads × 2 sides × slippage),
   adjustment rule design (adjustments add complexity and destroy backtestability — no-
   adjustment IC v1 is simpler but may not survive validation because natural drift in a
   trending Nifty puts one side deep ITM without any recourse), and the interaction with
   the existing CSP portfolio (running CSP short put alongside IC short put creates double
   short-put exposure — does the IC need to size the put spread assuming CSP is already on?).

---

## Command

```bash
python scripts/ask_council.py \
    --topic iron-condor-v1-core-design \
    --template strategy_parameters \
    --context docs/strategies/csp_nifty_v1.md \
    --question "The Iron Condor (IC) is the planned Phase 2 strategy in NiftyShield. Its specification (task 2.3) has not been written. The system uses Nifty 50 monthly options, same collateral infrastructure as CSP (csp_nifty_v1.md, see context file), 1 lot at Phase 2 entry (currently 65 units but verify against NSE lot schedule). Three core design decisions need council input before writing the spec: (1) SYMMETRIC vs ASYMMETRIC DELTA TARGETS: Nifty has a persistent put skew — at 30 DTE, the 15-delta put typically carries 3–6 IV points more than the 15-delta call. A symmetric IC (e.g., -0.15 put / +0.15 call both sides) collects equal credit from both wings despite structurally different risk (Nifty's tail risk is asymmetric — sharp declines more frequent than sharp rallies of the same magnitude). An asymmetric IC (-0.20 put wing / -0.10 call wing) charges the put side more aggressively, matching credit collection to the premium richness of the skew, while keeping the call side tighter to reduce false stop-outs from occasional strong rallies. Which approach is appropriate for Nifty given its skew structure and FII-driven trend character? (2) ADJUSTMENT RULE: CSP v1 has no adjustments (by design — simplicity and backtestability). Should IC v1 also have no adjustments? The risk: a trending Nifty (55–60% of years) drives one IC wing deep ITM without an adjustment mechanism, producing 100% max loss on the breached spread far more often than a range-bound index would. The alternative: a defined delta-gate adjustment (roll the breached spread when the net IC delta exceeds ±0.15) — but this requires a defined roll strike, adds execution complexity, and makes the backtest significantly harder to implement. Without adjustment, the IC may fail the OOS Calmar threshold in trending regimes simply by design. (3) PORTFOLIO INTERACTION WITH CSP: When CSP (short put) and IC (short put spread) are running concurrently, the combined net delta has double put exposure. Should the IC's put spread be sized to net the portfolio to approximately delta-neutral after accounting for the CSP short put, or should each strategy be sized independently with the SPAN margin system managing the combined exposure? Specify the IC v1 design that produces the highest probability of passing the walk-forward Calmar ≥ 0.7 threshold on 8 years of Nifty monthly options history, while remaining operationally manageable for a single retail operator."
```

---

## Parameters Summary

| Parameter  | Value                                                                        |
|------------|------------------------------------------------------------------------------|
| `--topic`  | `iron-condor-v1-core-design`                                                 |
| `--template` | `strategy_parameters`                                                      |
| `--context` | `docs/strategies/csp_nifty_v1.md`                                          |
| `--question` | See command above                                                          |

---

## Additional Context Files

- `BACKTEST_PLAN.md` §1.4 (engine design — cost model already includes STT for both buy and
  sell sides; IC uses more legs than CSP, the cost model implications should be noted)
- `PLANNER.md` → "quant-4pc-local Reference" (the IC scaffold in that repo used symmetric
  deltas — the council should evaluate whether that default is right for Nifty)
- `DECISIONS.md` → Slippage Model (the IC stop-loss exit multiplier 1.5× applies per leg;
  for a 4-leg IC this compounds significantly)
- `docs/strategies/niftyshield_integrated_v1.md` (NiftyShield Integrated already has a CSP
  short put — the IC's put spread may create unintended overlap in months both are running)

## What This Decision Unlocks

- Task 2.3 (IC v1 spec document) — cannot be written until these design questions are answered
- Task 2.4 (IC implementation in `src/strategy/`) — depends on 2.3
- The `IronCondorConfig` dataclass in the engine (delta targets, adjustment rule flag,
  portfolio interaction policy)
- The combined net-delta monitoring rule in the future `src/risk/` module (when CSP + IC
  are both live, the risk module must check combined delta against a limit)

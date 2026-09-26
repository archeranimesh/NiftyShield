# Council Question 6 — Multi-Strategy Concurrent Portfolio Risk Allocation Framework

## Why This Is Council-Worthy

1. **Load-bearing and costly to reverse.** The risk allocation framework (which strategy gets
   how much margin budget, and what the combined net delta limit is) must be designed before
   live deployment of a second strategy. If the allocation framework is wrong — e.g., both
   strategies are short puts at similar strikes in the same expiry cycle — a single Nifty
   selloff blows through both strategies' stops simultaneously, and the realised drawdown
   exceeds each strategy's individual kill criteria by a compounding factor that neither
   specification anticipated. Rebuilding the risk framework after a correlated loss event
   is too late.

2. **Two defensible approaches with materially different outcomes.** Option A: **strategy-
   independent sizing** — each strategy is sized against its own kill criteria and max risk
   (CSP: 1 lot, IC: 1 lot, swing: 1 lot each), with portfolio net delta monitored but not
   capped by a hard rule. Each strategy's individual stop manages its own exposure. Option B:
   **portfolio-level delta cap** — a hard constraint on combined net delta-per-₹10L-collateral
   is enforced before each new position is entered; if the constraint would be breached by a
   new entry, it is skipped or sized down. Option A is simpler but allows correlated drawdown
   in a single market event. Option B requires a cross-strategy delta aggregation engine
   (part of `src/risk/`) and may cause strategy skips that distort the paper-to-backtest
   variance check (the backtest runs each strategy independently, not with the portfolio cap).

3. **Spans multiple disciplines.** Options portfolio theory (net delta, gamma, vega at the
   portfolio level), NSE-specific considerations (SPAN margin calculation across multiple
   strategies on the same underlying — can result in margin offsets that are not linearly
   additive), capital structure interaction (₹75L MF + ₹30L bonds + ₹15.5L NiftyBees as
   collateral — the margin system sees collateral at haircut values, not NAV), and operational
   execution (a single-operator system cannot dynamically delta-hedge in real time; any
   portfolio risk rule must be static, pre-defined, and automatable via `src/risk/`).

---

## Command

```bash
python scripts/ask_council.py \
    --topic multi-strategy-portfolio-risk-allocation \
    --template strategy_parameters \
    --context docs/strategies/niftyshield_integrated_v1.md \
    --question "By Phase 3, NiftyShield plans to run the following strategies concurrently on Nifty 50 options: (A) CSP v2 — 1 lot short Nifty monthly put at ~20–25 delta; (B) NiftyShield Integrated — 1 lot CSP + 4 lots protective put spread (long 8%–15% OTM put, short 20% OTM put) + 2 lots quarterly tail puts; (C) Swing strategies (Donchian or ORB) — 1–2 lots directional credit spreads at 15-delta, 30–45 DTE; (D) Covered call overlay — 1 lot short Nifty monthly call at 15-delta on the pledged NiftyBees position. The collateral pool is ~₹1.2cr (₹75L MF + ₹30L bonds + ₹15.5L NiftyBees). The combined SPAN + exposure margin for all strategies running simultaneously is approximately ₹6L–₹10L (rough estimate — depends on SPAN offsets from protective puts). Three unresolved design questions: (1) CORRELATED TAIL RISK: During a Nifty selloff of ≥10%, CSP (A) hits its delta stop, the swing strategy's bearish spread profits but the bullish spread in a prior cycle may still be open, and Integrated (B) provides protection only above the Leg 2 threshold. The strategies are NOT independent in a correlated market event. What is the correct portfolio-level net-delta constraint that prevents a single 10% Nifty decline from triggering kill criteria simultaneously across 3 strategies? (2) MARGIN INTERACTION: SPAN margin offsets exist when a short put and long put are in the same expiry cycle (the protective put spread in Integrated reduces SPAN for the CSP leg). Does this margin offset change the effective capital efficiency of running Integrated + CSP together vs. separately? And does it create a false sense of safety if the protective put's strike is far enough OTM that SPAN hasn't credited the full offset? (3) VARIANCE CHECK DISTORTION: If a portfolio-level delta cap causes some swing strategy entries to be skipped (because the cap is already reached by CSP + Integrated), the paper trade log will systematically underperform the per-strategy backtest (which assumes every signal is executed). How should the variance check at the portfolio level account for signal-skipping due to the risk cap? Should each strategy be validated independently (ignoring the portfolio cap) and the cap only applied live, or should the paper trading phase simulate the cap and validate against a cap-aware backtest?"
```

---

## Parameters Summary

| Parameter  | Value                                                                        |
|------------|------------------------------------------------------------------------------|
| `--topic`  | `multi-strategy-portfolio-risk-allocation`                                   |
| `--template` | `strategy_parameters`                                                      |
| `--context` | `docs/strategies/niftyshield_integrated_v1.md`                             |
| `--question` | See command above                                                          |

---

## Additional Context Files

- `MISSION.md` (Principle I: Protect Before You Earn; Principle IV: Segregate Pools)
- `docs/strategies/csp_nifty_v1.md` (kill criteria — at what drawdown CSP pauses)
- `docs/plan/signals-eval-core/stories.md` §SE6.4 (swing live kill criteria — trailing 60-day
  Calmar < 0.3 → reduce, 3 consecutive losses exceeding threshold → pause)
- `BACKTEST_PLAN.md` §Phase 3 (the phase where portfolio construction officially happens,
  but the risk framework needs to be designed before Phase 3 to inform Phase 2 live deployment)

## What This Decision Unlocks

- `src/risk/` module design — specifically, whether the risk module implements a
  per-strategy kill circuit or a portfolio-level delta monitor (or both)
- The `src/risk/` module's public interface: `check_new_entry(strategy, entry_delta)` →
  `allowed: bool` if portfolio cap logic is used
- Task 2.1 (continuous re-validation) — should it report per-strategy Z-scores or a
  combined portfolio Z-score?
- Phase 3 gate condition (BACKTEST_PLAN.md §3): "3 strategies live, ≥6 months each within
  envelope" — does the "within envelope" check apply individually or collectively?

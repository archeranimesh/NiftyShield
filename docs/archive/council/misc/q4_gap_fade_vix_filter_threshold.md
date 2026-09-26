# Council Question 4 — Gap Fade VIX-IVP Filter: 75th Percentile vs Alternatives

## Why This Is Council-Worthy

1. **Load-bearing and costly to reverse.** The VIX-IVP threshold for Gap Fade is baked into the
   signal generator (`src/strategy/signals/gap_fade.py`), the walk-forward validation (every
   window's trade count depends on how many days pass the filter), and the Monte Carlo simulation
   (fewer trades → wider confidence bands → potentially different kill conditions). It is also
   the one major difference between Gap Fade and ORB filter design that was never council-reviewed
   — it was set by analogy to ORB (90th) and reduced by 15 percentage points without a
   quantitative basis.

2. **Two defensible approaches with materially different outcomes.** The 75th percentile
   excludes ~25% of trading days from the signal universe. The 90th percentile (ORB standard)
   excludes ~10%. For a strategy targeting 60–100 trades/year (after the gap size filter), the
   difference is ~15–25 fewer qualifying trades per year. With a 252-day/year rolling walk-forward
   window requiring minimum 10 trades per window, the 75th threshold risks pushing the strategy
   below the minimum-trades-per-window threshold in low-activity periods, triggering the
   "insufficient-window cap" kill condition (>25% of windows insufficient). The 90th threshold
   avoids this. Conversely, if the true edge is concentrated in low-VIX days (below 75th),
   using 90th would let in high-IV days that dilute the edge.

3. **Spans multiple disciplines.** Mean-reversion signal theory (gap fade hypothesis depends
   on the GIFT Nifty → NSE open correlation being noise-driven, not information-driven; this
   breaks at different VIX levels than ORB does), statistical power (sample size implications
   of the filter cutoff), walk-forward validation design (minimum trades per window constraint),
   and the asymmetry between ORB and Gap Fade that needs a theoretical justification rather
   than an intuition.

---

## Command

```bash
python scripts/ask_council.py \
    --topic gap-fade-vix-filter-threshold \
    --template strategy_parameters \
    --context docs/plan/signals-eval-core/stories.md \
    --question "Strategy 3 (Mean-Reversion Overnight Gap Fade) in the swing strategy pipeline uses a VIX-IVP filter: skip the signal when India VIX's 63-day trailing percentile rank (IVP) is ≥ 75th percentile. Strategy 2 (ORB) uses 90th percentile for its VIX structural exclusion (council-reviewed 2026-05-01). The asymmetry — 75th for Gap Fade vs 90th for ORB — was never council-reviewed. It reflects the intuition that gap fades degrade more continuously with rising IV (because correlated gaps increasingly carry real information at moderate IV levels), while ORB only degrades at the extreme tail (where pre-event positioning dominates the OR). The question has three parts: (1) THEORETICAL BASIS: Is the 75th/90th asymmetry well-grounded? The Gap Fade hypothesis (GIFT Nifty → NSE open gap is correlation-driven, not information-driven, for gaps 0.3%–1.0%) degrades in high-IV regimes because those regimes correlate with genuine information-flow (global risk-off, EM capital flight, RBI surprises). At what VIX-IVP level does the GIFT→NSE correlation cease to be the dominant driver of the gap? Is this at the 75th percentile (~IVP 63-day rank ≥ 75%) or at a different level? (2) STATISTICAL IMPACT: Gap Fade targets 60–100 trades/year after the gap-size filter (0.3%–1.0%). With a 75th percentile VIX filter excluding ~25% of days vs 90th excluding ~10%, expected qualifying trades fall from ~60–100 to ~45–75. The walk-forward minimum is 10 trades per 252-day window. Is there a risk that the 75th threshold makes some rolling windows insufficient (fewer than 10 trades), triggering the >25% insufficient-window kill condition even if the strategy has genuine edge? (3) UNIFIED FILTER: Should ORB and Gap Fade use the same VIX-IVP threshold (for implementation simplicity and shared regime classification), or does each strategy's distinct failure mode justify different thresholds? If different thresholds are used, what should each be?"
```

---

## Parameters Summary

| Parameter  | Value                                                                        |
|------------|------------------------------------------------------------------------------|
| `--topic`  | `gap-fade-vix-filter-threshold`                                              |
| `--template` | `strategy_parameters`                                                      |
| `--context` | `docs/plan/signals-eval-core/stories.md`                                   |
| `--question` | See command above                                                          |

---

## Additional Context Files

- `docs/council/2026-05-01_orb-volatility-filter-design.md` (ORB council decision — the 90th
  percentile rationale that this question benchmarks against)
- `BACKTEST_PLAN.md` §1.3a (India VIX ingestion — required data for this filter)

## What This Decision Unlocks

- `VixFilter` configuration in `src/strategy/signals/gap_fade.py`:
  `vix_ivp_threshold` (currently `0.75`, potentially should be `0.90` or another value)
- The unified regime engine in `src/strategy/regime.py` — if ORB and Gap Fade use the same
  VIX threshold, the exclusion flag can be shared; if different, each signal generator manages
  its own VIX exclusion independently
- Walk-forward minimum-trades-per-window calibration: if 75th threshold makes some windows
  insufficient, the minimum may need to be lowered (currently 10/day for daily strategies)
  to avoid the kill condition

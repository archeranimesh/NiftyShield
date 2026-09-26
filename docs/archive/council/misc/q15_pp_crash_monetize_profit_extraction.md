# PP Profit Extraction: Binary CRASH_MONETIZE vs Tiered/Partial Capture

## System Context

`PPOverlayV1` (`src/strategy/pp_overlay_v1.py`) holds a protective long put on NiftyBees.
Entry is now resolved (PP2, 2026-08-03): 0.15 delta, ~3.1% OTM, monthly cadence — direct
operator decision, backed by a live chain pull and a 26-year Nifty monthly-return frequency
analysis.

From entry until exit, PP's exit surface is exactly two signals
(`ExitSignalEngine.evaluate_pp`, `src/strategy/exit_signals.py`):

- **CRASH_MONETIZE** (ACTION, auto-executes): delta ≤ -0.80 OR value ≥ 5× entry debit → closes
  the **entire** position in one shot.
- **ROLL_ELIGIBLE** (ACTION): DTE ≤ 5 → roll to next expiry, unconditional on P&L.

There is no partial profit-taking, no trailing mechanism, and no intermediate capture tier
between entry and `CRASH_MONETIZE`. The position is either fully open at original size or fully
closed. `PPOverlayV1.apply_action`'s `MONETIZE_PP` handling is full-close only
(`_record_close_trade` closes the whole `PaperPosition`).

## The empirical shape of the problem

26 years of Nifty monthly returns (2000–2026 YTD, 307 months, operator-supplied dataset,
reproduced in `DECISIONS.md`'s 2026-08-03 PP2 entry) shows single-month declines ≥5% occur
~1.4×/year, ≥10% ~once/2.6yr, ≥15% ~once/4.3yr, and ≥20% only twice (2008, 2020 — ~once/13yr).

Critically, the ≥15%/≥20% tier events are **not always single clean months**. 2008 alone
produced six separate ≥5% monthly declines across ten months (Jan −16.31%, Mar −9.36%,
May −5.73%, Jun −17.03%, Sep −10.06%, Oct −26.41%) — an extended, multi-leg decline, not one
sharp move. 2020's crash (Mar −23.25%) was closer to a single-month event, followed by a swift
partial recovery (Apr +14.68%).

A single fixed `CRASH_MONETIZE` threshold treats both shapes identically: it fully cashes in the
entire position at the first -0.80 delta print, regardless of whether the decline is effectively
over (2020-shape) or has several more down-months still ahead (2008-shape). In the 2008-shape
case, a worked example this session traced a `CRASH_MONETIZE` firing in January, followed by
IVR-blocked re-entry (separately resolved via PP3/PP4's `--log-only-gates`/`GateViolation`
pattern), leaving the book without any PP coverage for March's further −9.36% move.

## The counter-constraint: execution risk during the exact conditions this signal fires under

Any alternative to a single fixed threshold has to survive a specific, real constraint: NSE
deep-ITM put liquidity and bid-ask spreads are worst exactly during the crash conditions that
trigger `CRASH_MONETIZE`. `PaperFillSimulator`'s VIX-regime slippage model
(`src/strategy/executor.py`) caps at a flat ₹4.0 for VIX ≥ 30, with no further scaling for
genuine tail-event VIX levels (50s–90s, per 2008/2020) — meaning even the current single
full-close's simulated fill is probably optimistic relative to a real exit under those
conditions. A mechanism requiring multiple precisely-timed partial exits, or continuous
mark-to-market tracking for a trailing stop, could carry meaningfully more execution risk than
one immediate full-close, in the one scenario where getting the exit right matters most.

## Q1 — Is binary all-or-nothing the right shape, or does the data justify tiers?

Given the empirical prevalence of extended/multi-month declines (2008-shape) alongside sharper
single-month ones (2020-shape), should `CRASH_MONETIZE` remain a single binary full-close, or
should PP capture value in stages — e.g. partial/tranche exits (close half the position at the
existing threshold, let the remainder run under a fresh or trailing threshold), multiple
delta/value tiers (partial capture at intermediate deltas before -0.80, e.g. -0.50/-0.65/-0.80),
or some other give-back-limited design?

## Q2 — How should execution risk be weighed against captured value?

Any recommended design has to be evaluated against the deep-ITM liquidity/spread constraint
above, not just against theoretical payoff capture. Does the recommended approach (if any
change is recommended) meaningfully increase execution risk relative to today's single
full-close, and if so, is the additional captured value worth that tradeoff — or does the
execution-risk constraint argue for keeping the simpler design regardless of what the payoff
math alone would suggest?

## Q3 — Is the data sufficient to decide, or is the sample too small?

The 26-year dataset has exactly two ≥20% single-month events (2008, 2020) and only one genuine
multi-month extended-decline case (2008) to design around. Is this sample sufficient to justify
a specific tiered/partial design, or is it too small for a data-driven answer to be reliable —
in which case, should the recommendation default to the simpler, execution-robust single
full-close specifically *because* the sample can't support more structure, rather than because
the simpler design is theoretically optimal? Separately: would a full historical option-chain
backtest (not just spot-return data) meaningfully change this answer, or would it hit the same
small-sample ceiling on genuine crash events?

## Required Council Output Format

```
## Summary Table

| Decision | Recommendation |
|----------|---------------|
| Binary full-close vs tiered/partial capture | |
| If tiered: specific thresholds/tranche sizes | |
| Execution-risk tradeoff verdict | |
| Data sufficiency verdict (26yr sample size) | |
| Recommended validation approach (data / backtest / neither) | |

## Design Rationale
[Why the recommended capture design is correct given both the empirical drawdown-shape
evidence and the deep-ITM liquidity/execution-risk constraint]

## Execution Risk Detail
[Explicit assessment of slippage/fill risk for the recommended design vs. the current
single full-close, referencing PaperFillSimulator's VIX-regime slippage cap]

## Dissenting Notes
[Panel disagreements, particularly on whether the 2008/2020 sample is sufficient to
justify added complexity, or whether simplicity should win by default given small-N]
```

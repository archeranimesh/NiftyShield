# PP protection cost study — prompt

> Measure what a hold-to-DTE-5 protective put costs per year at three strike depths on one NIFTY lot, what deductible it really leaves, and what a covered call earns net of its losses, so the
> protection depth can be chosen on a Pareto basis instead of an assumed 5% freeze.

Read `CONTEXT.md` and state `CONTEXT.md ✓` before anything else. Then read `tasks.md`, find the first unchecked `- [ ]`, and do **only** that task. Read that task's full spec in `stories.md` (same
task id) before writing any code. One task per session. Complete it fully. Stop.

## Why this story exists

Animesh (2026-10-11): protect capital first, then enhance it. Idea on the table: hold NiftyBees (about ₹15 lakh, one NIFTY lot), buy a put to curb a 10% fall to roughly 5%, and sell a covered call for
rent so the downside is held to about one credit. He asked for an optimal depth that is comfortable about 80% of the time rather than a fixed 5%, and for Tradetron's cheap backtests to test the
assumptions.

What the earlier story already measured (`tradetron-delta-and-long-window/findings.md`, PP run `ttbt-999113502261011`, template 999135746), free, from the PP fills:

- 69 roll cycles averaging 26 days. Cycle NIFTY move: median +0.2%, 10th percentile -4.9%, 20th percentile -2.5%, worst -6.7%; 43% of cycles negative. The worst 20% of cycles (14 of 69) carry 81% of
  the total downside, so the 80/20 split holds on this sample.
- The PP's 0.20-delta put sat on average 3.4% OTM (range 1.7% to 7.8%) and cost 0.57% of spot per cycle, about 7.4% a year of notional before payoffs. Crash exits and residual values returned most of
  it. The net cost across the five years was about 0.8% a year of notional (fixed ₹11.7 lakh basis).
- **Correction recorded:** a session message said a 5%-OTM put would cost more than the PP's. That was backwards; a deeper put is cheaper per cycle and leaves a bigger deductible.
- The PP template exits at 5x the debit or delta <= -0.80, which gives up protection mid-fall and caps the payoff near +₹33k a lot per event. A freeze test needs a hold-to-DTE-5 version with no crash
  exit.
- The CC (template 999082574) kept about ₹10.6k a year net (+₹52.9k gross over 4.97 years, 196 trips) after 51 losses at the 2.5x exit, several of which gapped past the trigger. Rental income cannot
  be counted as premium collected; only realised net counts.

## Scope guard

In scope: free analysis of finished runs; creating and pre-flighting hold-to-DTE-5 put templates (no crash exit) at three depths and a CC variant with a 2x-price exit; funded runs after Animesh
confirms each spend; a cycle table built from the runs' fills; findings and a sizing note.

Out of scope: any `src/` or `scripts/` change except a reused, tested CLI in `scripts/dev/`; live or Live Offline deployment; the NiftyBees stock leg and margin inside Tradetron; IV, liquidity and
bid-ask (the engine fills at Open with flat 0.05% slippage, so real OTM put spreads cost more than shown); editing `tradetron-delta-and-long-window/` or `greeks-bs-fallback/` files; credentials,
broker tokens, the wallet top-up link.

Spend rule: no funded run before its free pre-flight says `backtestable` and Animesh confirms the spend in that session. Quote `next_run.quote` from `tt_backtest_workbench` verbatim. Wallet ₹100 on
2026-10-11. Planned: 3 put runs plus 1 CC run, 4 runs at ₹20 is ₹80, ceiling to be approved by Animesh at PPS-3 (his stated range was ₹40 to ₹60, so PPS-3 asks before assuming the extra).

## Design review

No new module, class or seam. A reusable cycle-table calculator, if one emerges, runs the triggers in `docs/refactor/design-principles.md` first and is recorded here.

## Session-start load hints

Always: `CONTEXT.md`, `tasks.md`, the current task in `stories.md`, `docs/reference/tradetron.md` (Backtesting, long-window runs), `docs/archive/plan/tradetron-delta-and-long-window/findings.md` (PP
and Collar runs, TDL-6 rules), `docs/archive/plan/tradetron-delta-and-long-window/template_pp.md` (PP template spec). The Tradetron MCP tools are deferred: load schemas with `ToolSearch`; call
`tt_get_tradetron_quickstart` once before authoring. PPS-1 first, because the per-trade index of the PP run ages out within days of 2026-10-11 (save the cycle data to this folder at once).

## Task overview

- **PPS-1** — Save the 69 PP cycles (free) and reproduce the Pareto numbers above.
- **PPS-2** — Put-depth templates (shallow, base, deep) with no crash exit; strike control keyword; validate, pre-flight, create. Free.
- **PPS-3** — Funded put runs and the per-depth cycle table.
- **PPS-4** — CC rental variant (2x exit): one funded run, net of losses and gap overshoot.
- **PPS-5** — Selection rule, sizing note against Animesh's exposure and loss limit, findings, close.

## Definition of done

PPS-1 to PPS-5 ticked with SHAs. `findings.md` holds the per-depth table with cycle counts, the CC net rental, the stated selection rule and the sizing note; `docs/reference/tradetron.md` carries any
new platform finding; the epic `README.md` status column and `TODOS.md` are updated.

## Perspectives not covered

Cycle returns here come from the PP's own roll schedule (about 26 days, 69 overlapping-regime samples), so the left tail is truncated by crash exits and no fall beyond -6.7% appears; a 10% month is
not in the sample. Tradetron's fill model understates OTM put cost, and its data has holes (4 absent and 5 skipped sessions). The study screens depth and cost; it does not predict the next sell-off.

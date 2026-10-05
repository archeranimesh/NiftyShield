
# Tradetron CC backtest POC — prompt

> Decide whether Tradetron's backtest can be relied on for POC validation, by backtesting the covered-call (CC) overlay's short-call leg and reconciling it trade by trade against NiftyShield's own
> paper CC records.

Read `CONTEXT.md` and state `CONTEXT.md ✓` before anything else. Then read `tasks.md`, find the first unchecked `- [ ]`, and do **only** that task. Read that task's full spec in `stories.md` (same
task id) before writing any code. One task per session. Complete it fully. Stop.

## Why this story exists

NiftyShield wants to know whether Tradetron can stand in for its own backtest and paper stack when validating a strategy, before any strategy is deployed there. A 2026-10-05 session established the
platform basics: the Tradetron MCP works on the account, a Live Offline deployment runs and writes Greeks into runtime variables, and `ATM` and `ATM-SPOT` in an instrument string are different
selectors (see `docs/reference/tradetron.md`, "Greeks probe results"). It did not run a backtest. The wallet is at ₹0 and every chat or MCP backtest costs ₹20, so the evaluation was deferred to a
later session.

The covered call was chosen over a plain short straddle and over the iron condor. A straddle only tests engine mechanics and says nothing about a strategy NiftyShield actually runs. IC v1 has several
unbuildable pieces on Tradetron (percent-of-credit exits, DTE gates, limit-at-mid execution), which would blur a platform verdict with a keyword-coverage verdict. The CC is a single short monthly call
selected at 15 delta, has paper trades to reconcile against (`scripts/strategies/cc_calibration/paper_cc_entry.py`, `src/strategy/cc_overlay_v1.py`), and its gaps are specific and checkable.

The question this story answers is narrow: for this one strategy, over a window after the April 2026 Tuesday-expiry change, does a Tradetron backtest reproduce what NiftyShield's paper records show,
and where it does not, is the gap a platform limit or a spec difference? The answer is a verdict with evidence, not a profitability claim.

## Scope guard

In scope: the short NIFTY monthly call leg of the CC overlay only. Reading the live CC thresholds and the paper records, drafting and validating one Tradetron template, free pre-flight checks, one
funded backtest run plus any re-reads, and the reconciliation write-up.

Out of scope: the NiftyBees leg and its margin pledge (passive, not modelled on Tradetron; compute it from price data if a combined figure is ever wanted), the iron condor, the near-expiry buy, any
live or Live Offline deployment of the CC, and any change to `src/` or `scripts/`. A reconciliation script is allowed only if it will be reused, and then it goes in `scripts/dev/` as a tested CLI; a
one-off comparison stays in `scratch/` per `SCRATCH.md`. Never record credentials or broker tokens in any file.

Do not spend wallet money until the free pre-flight (TCP-3) says the template is backtestable. Quote Tradetron's own `next_run.quote` verbatim; never estimate a price. A new run is needed only when
the template body, date range, type, expiry, fill price or candle frequency changes; reading and re-slicing a finished run is free.

## Design review

No new module, class or seam. This is an investigation story whose outputs are documents. If TCP-6 produces a reusable reconciliation CLI, run the SOLID triggers in
`docs/refactor/design-principles.md` and the prior-art audit in `docs/refactor/code-deduplication-and-taxonomy.md` against it before writing it, and record the outcome here.

## Session-start load hints

Always: `CONTEXT.md`, `tasks.md`, the current task in `stories.md`, and `docs/reference/tradetron.md` (tool catalogue, Backtesting section, Greeks probe results, Account state). Per task:

- TCP-1: `src/strategy/exit_signals.py` (`evaluate_cc`, line ~269) and `src/strategy/cc_overlay_v1.py`, via the graph (`scripts.dev.graph_snippet`), and the archived spec
  `docs/archive/strategies/covered_call_overlay_v1.md`. The archived spec is stale on thresholds; the code is the authority (see Task overview).
- TCP-2: `DB_REGISTRY.md` first, before any query against `portfolio.sqlite`. Bash output discipline applies: aggregate in SQL, named columns, `LIMIT 10`.
- TCP-3 to TCP-5: the Tradetron MCP tools are deferred; load their schemas with `ToolSearch` before calling. `tt_get_tradetron_quickstart` once before authoring (about 13k tokens; skip it for
  read-only checks).
- TCP-6: `docs/plan/README.md` §Conventions for the close-out, and `DECISIONS.md` if the verdict changes what NiftyShield does.

## Task overview

Six tasks, in order. TCP-1 fixes what the strategy actually is today. TCP-2 builds the ground-truth table from paper records. TCP-3 runs the free backtestability pre-flight and decides go or stop.
TCP-4 authors and creates the template. TCP-5 is the one funded run and needs Animesh to top up the wallet. TCP-6 reconciles, writes the verdict and saves learnings.

Known facts carried in from the 2026-10-05 session, so they are not re-derived:

- The archived CC spec shows a 50% profit target and a +0.40 delta stop. Its archive note says CC-1 changed the live values to delta stop 0.55, profit target at 30% of credit remaining, a 2.5x loss
  stop added, time stop 21 days unchanged. Treat these as claims to verify in `evaluate_cc()` (TCP-1), not as settled values.
- Entry rule in the archived spec: Wednesday after the monthly expiry, 30 to 45 DTE, sell the monthly call at the 15-delta strike read from the live Upstox chain, maximum 1 lot (65 units) per about
  5,700 NiftyBees units. NIFTY lot size is 65 per `tt_check_underlying_support`.
- Tradetron gaps for this strategy, from `docs/reference/tradetron.md`: delta-targeted strike needs `Find Strike` with its leg-drop hazard (a single-leg set simply skips entry, which is acceptable
  here); the delta stop needs `Delta()` on the traded instrument with a fill check; the percent-of-credit exit and the DTE and time-stop gates need keywords not yet identified.
- The single biggest unknown is whether the backtest engine has historical Greeks. If it does not, delta-based strike selection cannot be backtested and the CC cannot be reproduced as specified; that
  is itself a valid result.
- `Atmiv`, plain `ATM` in an instrument string, and `ATM` the strike formula anchor on the futures chart. Use `ATM-SPOT` or `ATM SPOT` for spot-anchored selection and do not mix them in one strategy.
- Free-plan data is delayed 1 minute on live reads; the backtest store is separate and is not affected. Monthly expiry is the last Tuesday (moved from Thursday in April 2026, see `REFERENCES.md`).

Where results go (the save-map):

- Run identifiers and the reconciliation table: this folder, in a `findings.md` (no task checkboxes, allowed as an extra reference file under §Extra files). Record `job_id` / `bt_id` and `report_url`
  rather than pasting numbers that `tt_backtest_result` and `tt_backtest_trades` can re-read for free.
- Platform behaviour that holds regardless of this strategy (Greeks in the backtest engine, Tuesday-expiry coverage, real per-run cost, fill or charge quirks): `docs/reference/tradetron.md`, under
  "Backtesting" or "Verified findings".
- The verdict, if it changes what NiftyShield does (rely on Tradetron for POC validation, or rule it out for delta-based strategies): `DECISIONS.md`, with a pointer back to this story.
- Story status and the session log: `docs/plan/README.md` and `TODOS.md` per Step 5a.
- Code only if reused: `scripts/dev/` as a tested CLI. Otherwise `scratch/`.
- Memory: only non-obvious lessons about working with this platform, never results.
- Record only what was measured. Mark inferences as inferences, the way the reference doc treats the old `ATM` strike.

Credit needed to run this: Tradetron quotes ₹20 and 1 credit per backtest (`tt_backtest_workbench`, 2026-10-05, quote source `me/backtest-routing`). The wallet is ₹0 and the prepaid pack's cycle ended
2023-07-24, so it funds nothing. Planned runs: one main run, one sensitivity run on `trade_price` (`Close` versus the default `Open`), and one or two re-runs if template fixes are needed after the
first result, so about 4 to 5 runs. Animesh should top up ₹100 as a minimum and ₹200 for headroom (10 runs). The count is an estimate; the price per run is Tradetron's. Top-up link comes from
`tt_wallet_balance`; it is minted per call, so fetch a fresh one when needed. The website's own Backtest button has a separate 25-run NSE allowance and costs nothing, but its results cannot be read
through the MCP.

## Definition of done

TCP-1 to TCP-6 ticked with SHAs. `findings.md` holds the run ids, the reconciliation table of paper versus backtest (strike, entry price, exit trigger, exit price, P&L) and a plain verdict.
`docs/reference/tradetron.md` carries the platform findings. `DECISIONS.md` carries the decision if there is one. The story is archived per §Conventions *Completion → archive*.

## Perspectives not covered

The NiftyBees leg, its pledge and the margin treatment are not modelled, so the figures describe the call only. The number of paper CC cycles is probably small; the project rule is no conclusions
before enough observations, so state the sample size next to every comparison and call it thin when it is. Tradetron's slippage and charge model may differ from NiftyShield's cost model, so separate
fill-price differences from charge differences before blaming the engine. Paper records use Upstox chain deltas; Tradetron computes its own, so a strike mismatch can be a Greeks-methodology difference
and not a backtest defect. A Greeks comparison against Upstox at the same timestamp (Tradetron versus Upstox, expiry-day behaviour, `Find Strike` by delta against Upstox's 15-delta strike) was
discussed on 2026-10-05 and is a separate experiment, not part of this story.

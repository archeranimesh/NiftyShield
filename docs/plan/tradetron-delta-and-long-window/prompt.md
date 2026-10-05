# Tradetron delta check and long-window validation — prompt

> Find out whether Tradetron's delta agrees with Upstox's, then use Tradetron as a cheap long-window screen of the paper strategies (CC first, then PP and Collar, IC audited) before any paid
> historical-data purchase, and see whether its Greeks give `greeks-bs-fallback` a reference for far-dated contracts.

Read `CONTEXT.md` and state `CONTEXT.md ✓` before anything else. Then read `tasks.md`, find the first unchecked `- [ ]`, and do **only** that task. Read that task's full spec in `stories.md` (same
task id) before writing any code. One task per session. Complete it fully. Stop.

## Why this story exists

The archived `docs/archive/plan/tradetron-cc-backtest-poc/` story (verdict in its `findings.md`, decision in `DECISIONS.md`) ran the covered-call short-call leg on Tradetron twice (₹40). Result:
partial reproduction. Expiries (5 of 5) and three entry and exit date pairs matched paper; the 0.15-delta strikes were 50 to 200 points higher than paper's on 4 of 5 cycles, so credits and P&L were
lower on all five pairs. The cause is an inference (Tradetron's delta against the Upstox chain delta paper used), and no delta was recorded on either side. The window was 7 weeks, one regime, 6 round
trips, and the loss, delta and DTE exits never fired. The rule recorded in `DECISIONS.md` is that Tradetron is a mechanics cross-check, not a P&L reconciliation source, until the delta question is
answered.

Animesh's purpose for Tradetron (2026-10-05): validate the paper strategies over a longer period, on profitability and usability, **before buying paid historical option data**; and, if it helps, give
`docs/plan/greeks-bs-fallback/` a reference for contracts where Upstox returns all-zero Greeks (the yearly bucket). This story answers four things in order: does Tradetron's delta match Upstox's
(TDL-1, TDL-2); can Tradetron run a long window at all and is there a comparator for it (TDL-3, TDL-4); what does a long CC, PP and Collar run show (TDL-5 to TDL-8); is IC expressible there (TDL-9);
and does the answer change the data-purchase decision (TDL-10).

What Tradetron can and cannot give, so expectations stay honest. It has no chain-dump tool; the chain is reached one instrument at a time (`docs/reference/tradetron.md`, "Greeks and option chain"). It
cannot supply a downloadable historical Greeks or price dataset. It can give point readings of `Delta()` and `Iv()` through a Live Offline probe, and cycle-level fills and P&L through a backtest. For
`greeks-bs-fallback` that means at most an independent third-party delta on far-dated contracts as a cross-check for GF-5, not ground truth (Tradetron's delta is another model, methodology unknown).
For the purchase decision it means a screen of rule viability, cycle counts, exit mix and rough P&L scale, not a substitute for fill-quality or liquidity data.

## Scope guard

In scope: read-only queries of stored Upstox Greeks and chain data; free Tradetron pre-flights; a Live Offline probe deployment (no orders reach a broker); creating PP, Collar and, only if TDL-9 says
GO, IC templates on Tradetron; funded runs after Animesh confirms each spend; findings and the save-map below.

Out of scope: any change to `src/` or `scripts/` (a comparison script is allowed only if it will be reused, as a tested CLI in `scripts/dev/`; one-offs stay in `scratch/` per `SCRATCH.md`); editing
the `greeks-bs-fallback` files (hand it a reference table in `findings.md` and let Animesh decide what GF-1 and GF-5 do with it); any live deployment with real orders; the NiftyBees stock leg and
margin; IC runs unless TDL-9 returns GO (they become a follow-up story). Never record credentials, broker tokens or the wallet top-up link in any file.

Spend rule: no funded run before its free pre-flight says backtestable and Animesh has confirmed the spend in that session. Quote `next_run.quote` from `tt_backtest_workbench` verbatim; never estimate
a price. A new run is needed only when the body, dates, type, expiry, fill price or candle frequency changes; reading a finished run is free. Wallet at the start of this story: about ₹160 (unverified;
read `tt_wallet_balance` first). Expected runs: 1 to 2 for CC, 1 to 2 each for PP and Collar, so roughly 4 to 6 at ₹20 each; the count is an estimate, the price is Tradetron's.

## Design review

No new module, class or seam. If any task produces a reusable reconciliation CLI, run the SOLID triggers in `docs/refactor/design-principles.md` and the prior-art audit in
`docs/refactor/code-deduplication-and-taxonomy.md` first and record the outcome here.

## Session-start load hints

Always: `CONTEXT.md`, `tasks.md`, the current task in `stories.md`, `docs/reference/tradetron.md` (tool catalogue, Greeks probe results, Backtesting, Verified findings),
`docs/archive/plan/tradetron-cc-backtest-poc/findings.md` (run ids, the v2 template, the reconciliation) and `docs/archive/plan/tradetron-cc-backtest-poc/template.md`. Per task:

- TDL-1, TDL-4, TDL-6: `DB_REGISTRY.md` first before any query against `portfolio.sqlite`; Bash output discipline applies (aggregate in SQL, named columns, `LIMIT 10`). TDL-4 also `src/backtest/` via
  the graph.
- TDL-2: `docs/plan/greeks-bs-fallback/prompt.md` (the zero-Greeks problem) and the Greeks probe results in the reference doc; template 999078810 is the existing probe.
- TDL-3, TDL-5, TDL-7, TDL-8, TDL-9: the Tradetron MCP tools are deferred; load schemas with `ToolSearch`. `tt_get_tradetron_quickstart` once before authoring.
- TDL-6, TDL-9: `src/strategy/exit_signals.py` and the strategy files via `scripts.dev.graph_snippet`; the code is the authority, not the archived specs (the CC spec was stale on four thresholds).
- TDL-10: `docs/plan/README.md` §Conventions for the close-out; `DECISIONS.md`.

## Task overview

- **TDL-1** — Free own-data delta check: for the six strikes Tradetron's `Find Strike` chose in run 2, read the Upstox delta from stored data at the nearest timestamp.
- **TDL-2** — Live Offline Greeks probe: Tradetron `Delta()` and `Iv()` against Upstox at one timestamp, near-dated and far-dated (yearly) contracts; hand a reference table to `greeks-bs-fallback`.
- **TDL-3** — Long-window pre-flight (free): data coverage, Greeks availability and the April 2026 Thursday-to-Tuesday expiry boundary for the CC v2 template; pick the window.
- **TDL-4** — Own-side comparator audit (read-only) and the go or no-go on funded runs, with Animesh's budget approval.
- **TDL-5** — CC long-window funded run on template v2; cycles, exit mix, regime split, sample size.
- **TDL-6** — PP and Collar: live rules from code and the paper ground-truth table from the DB.
- **TDL-7** — PP and Collar templates: validate, pre-flight, create.
- **TDL-8** — PP and Collar funded runs and reconciliation.
- **TDL-9** — IC v1 and v2 buildability audit (free); GO, PARTIAL or STOP; no template unless GO.
- **TDL-10** — Verdict on the data-purchase question, save-map, close and archive.

Carried-in facts (from the archived story; do not re-derive): the v2 CC template is id 999082574 (two sets, nearest monthly with at least 14 DTE, per-set exits, flat-position gate); template v1 is
999082430; the probe is 999078810. Run 2 job `ttbt-999069146261005`. `Current Month Expiry(..., 0)` stays on the current month until it expires; there is no if/else keyword. NIFTY lot size 65. Monthly
expiry moved from Thursday to Tuesday in April 2026 (`REFERENCES.md`). `ATM` anchors on the futures chart, `ATM-SPOT` on spot; do not mix them. Free-plan live reads are delayed 1 minute.

Where results go (the save-map):

- Run ids, tables, verdicts: this folder, in `findings.md` (no task checkboxes; allowed as an extra reference file). Record `job_id`, `bt_id` and `report_url` rather than numbers that
  `tt_backtest_result` and `tt_backtest_trades` can re-read for free.
- Platform behaviour that holds regardless of strategy: `docs/reference/tradetron.md` ("Greeks probe results", "Backtesting", "Verified findings").
- A reference table for far-dated Greeks: `findings.md` here, flagged for Animesh as an input to `greeks-bs-fallback` GF-1 and GF-5. This story does not edit that story's files.
- The data-purchase view and any rule change: `DECISIONS.md`, pointing back here.
- Status and session log: `docs/plan/README.md` and `TODOS.md` per Step 5a.
- Code only if reused: `scripts/dev/` as a tested CLI. Otherwise `scratch/`.
- Memory: only non-obvious lessons about working with this platform, never results.
- Record only what was measured; mark inferences as inferences.

## Definition of done

TDL-1 to TDL-10 ticked with SHAs. `findings.md` holds the delta check, the reference table for `greeks-bs-fallback`, the long-window run ids and tables, the buildability result for IC, and a plain
answer to the purchase question. `docs/reference/tradetron.md` carries the platform findings; `DECISIONS.md` carries any decision. The story is archived per §Conventions *Completion → archive*.

## Perspectives not covered

Tradetron's backtest is not a substitute for the paid data it is meant to precede: it gives no view of fill quality, bid-ask or liquidity beyond its flat 0.05% slippage, models no margin, and its
delta may differ from Upstox's (that is what TDL-1 and TDL-2 test). A long window adds round trips but the April 2026 expiry change splits the data into two regimes, and the report itself flags any
statistic under 30 round trips; per the project rule, state the round-trip count beside every figure and do not call a ratio or a P&L an edge below that. "Profitability" here means rough P&L scale and
exit mix over many cycles, as a screen, never a claim. Tradetron's Greeks, if nonzero on far-dated contracts, show agreement or disagreement with `greeks-bs-fallback`'s future Black-Scholes delta;
they do not prove either right, and the zero-Greeks pattern might be a thin-book suppression that a model-based delta would not reproduce.

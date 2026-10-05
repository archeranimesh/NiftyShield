
# Tradetron CC backtest POC — story specs

> One task per session. Find the first unchecked item in `tasks.md`. That is your only task. Full implementation rules in `CLAUDE.md` and `REVIEW.md`. After each task: set `SHA:` on the task line +
> tick the box, update the story status summary, add one line to `TODOS.md`. See `docs/plan/README.md` §Conventions.

All tasks are documentation or read-only investigation: no `src/` or `scripts/` change, so no unit tests and no `code-reviewer` run (docs-only diff). Tradetron MCP tools are deferred; load schemas
with `ToolSearch` before the first call. Never write credentials, tokens or the wallet top-up link into any file.

---

## TCP-1 — Confirm the live CC thresholds and entry rule from code

**Files to change / create:**
- `docs/plan/tradetron-cc-backtest-poc/findings.md` — new; section "Live CC rule set" with each value, its source line and whether it matches the archived spec.

**Before any code (graph queries — do not write model constructors from memory):**
- `bash python -m scripts.dev.graph_snippet <qualified_name>` for `ExitSignalEngine.evaluate_cc` (`src/strategy/exit_signals.py`, line ~269) and for the CC entry logic in
  `src/strategy/cc_overlay_v1.py` (`CCOverlayV1`, `compute_max_lots`).
- `search_code` for the constants those functions read (delta stop, profit-target fraction, loss-stop multiple, time stop days, delta target, DTE window).
- Read `docs/archive/strategies/covered_call_overlay_v1.md` (180 lines) only to diff against the code; the code wins.

**What to implement:**

1. Extract, with file and line, the current CC values: entry day and DTE window, call delta target, lot cap, profit target, delta stop, loss stop, time stop, any other trigger `evaluate_cc` returns.
2. Diff each against the archived spec and the CC-1 claim (delta stop 0.55, profit target 30% of credit remaining, loss stop 2.5x, time stop 21 days). Mark each MATCH or DIFFERS, quoting both values.
3. Write the table into `findings.md`. Do not edit the archived spec or any `src/` file.

**Done when:** every threshold the Tradetron template must encode has a code-sourced value and a stated source line.

**Commit:** `docs(plan): record live CC rule set for Tradetron POC`

---

## TCP-2 — Build the paper-trade ground-truth table

**Files to change / create:**
- `docs/plan/tradetron-cc-backtest-poc/findings.md` — add section "Paper CC ground truth".

**Before any code:**
- Read `DB_REGISTRY.md` first; never assume a table is empty or absent (its 2026-08-07 note on `paper_nav_snapshots` versus `paper_leg_snapshots` is the failure this prevents).
- Identify which tables hold CC entries and exits (strategy name `paper_covered_call_v1`, leg role `covered_call` per the archived spec; verify against the registry and
  `scripts/strategies/cc_calibration/paper_cc_entry.py`).
- `trace_path` on the entry script only if the registry is unclear.

**What to implement:**

1. First run a `COUNT` and `MIN/MAX(date)` aggregate over the CC records so the sample size and date span are known before any listing. Aggregate in SQL; named columns; `LIMIT 10` for any listing
   (Rule 1). Decimal values come back from TEXT columns.
2. List per cycle: entry date, expiry, strike, delta at entry, credit per unit, exit date, exit trigger, exit price, realised P&L. Skip nothing that was logged, including skipped cycles and their
   reason.
3. Write the table and the sample size into `findings.md`. If there are fewer than about five completed cycles, say so in the section header: the sample is thin and no conclusion is allowed beyond
   "reproduces or does not reproduce these cycles".
4. Choose the backtest window from the data: it must cover every paper cycle and start after 2026-04-01 (Tuesday expiry). Record it as `WINDOW: start..end`.

**Done when:** `findings.md` has the ground-truth table, the sample size and the chosen window.

**Commit:** `docs(plan): add paper CC ground truth for Tradetron POC`

---

## TCP-3 — Free pre-flight: is the CC backtestable on Tradetron?

**Files to change / create:**
- `docs/plan/tradetron-cc-backtest-poc/findings.md` — section "Pre-flight verdict".
- `docs/plan/tradetron-cc-backtest-poc/template.md` — the draft Tradetron strategy markdown (no task checkboxes).

**Before any code:**
- `ToolSearch` for `tt_get_tradetron_quickstart`, `tt_get_authoring_reference`, `tt_lookup_keyword`, `tt_find_keyword`, `tt_validate_markdown`, `tt_check_backtestability`. Call
  `tt_get_tradetron_quickstart` once before authoring.
- Pull `tt_get_authoring_reference` topics `option_chain_recipes`, `exit_sl_target`, `wire_vs_display_forms` (the %-of-credit exit and entry-credit capture live there), and look up the keywords for
  DTE and day-of-expiry gates under ExpiryFormula and StrategyInfo.
- Use the TCP-1 values; do not use the archived spec's numbers.

**What to implement:**

1. Draft `template.md`: one set, one short monthly NIFTY call at the 15-delta strike via `Find Strike` (Field `Delta`), entry gated to the Wednesday after expiry within the 30 to 45 DTE window,
   one-shot `entered` guard, exits for profit target, delta stop, loss stop and 21-day time stop as far as keywords allow, `Universal Exit` present, `Exit shorts first`. Qty 1 lot. Mark any rule that
   cannot be expressed as GAP with the missing keyword, rather than dropping it silently. Use `ATM SPOT` where a spot-anchored strike is needed.
2. Run `tt_validate_markdown` and fix every reported error. Record warnings.
3. Run `tt_check_backtestability` on the draft or on a saved template over the TCP-2 window. Branch on `verdict` (blocked, backtestable, unknown), not the boolean. Record the verdict verbatim and the
   reason.
4. Decision gate, written into `findings.md`: GO (backtestable, gaps listed), PARTIAL (backtestable only with fixed-offset strike, list what is lost) or STOP (blocked, say why, for example no
   historical Greeks). A STOP is a valid completed result; skip TCP-4 and TCP-5 and go to TCP-6 to record it.

**Done when:** `template.md` validates, the pre-flight verdict is recorded and the GO / PARTIAL / STOP decision is written.

**Commit:** `docs(plan): add CC template draft and Tradetron pre-flight`

---

## TCP-4 — Create the template on Tradetron

**Files to change / create:**
- `docs/plan/tradetron-cc-backtest-poc/findings.md` — add template id and `edit_url` to the pre-flight section.

**Before any code:**
- TCP-3 verdict must be GO or PARTIAL. If STOP, do not run this task.
- `tt_validate_markdown` again on the final `template.md`, and use its `dry_run_token` for `tt_create_strategy`.
- Check the account's template room: a previous 422 (`Template creation/update limit exceeded`) was cleared on 2026-10-04 when all old templates were deleted; the account now holds `NS Greeks Probe`
  (id 999078810).

**What to implement:**

1. Create the template with `tt_create_strategy` (or `tt_create_strategy_chunked` if size requires). Never pass a `tt_get_strategy` body to a create call; author from the markdown.
2. Read it back with `tt_get_strategy(<id>)` (it re-validates the stored body) and confirm set, condition and leg counts match the draft. The blank Repair Once envelope adds one to the condition
   count.
3. Record the template id and `edit_url` in `findings.md`. Do not deploy it; this story backtests only.

**Done when:** the template exists, reads back clean and its id is recorded.

**Commit:** `docs(plan): record CC template id for Tradetron POC`

---

## TCP-5 — Run the backtest (needs wallet top-up by Animesh)

**Files to change / create:**
- `docs/plan/tradetron-cc-backtest-poc/findings.md` — section "Runs": one row per run with job id, bt id, report URL, window, settings and price paid.

**Before any code:**
- `tt_wallet_balance` first. Animesh must top up before this task starts: ₹100 minimum, ₹200 recommended (quote ₹20 and 1 credit per run, planned 4 to 5 runs). This is Animesh's step; do not ask for
  broker or payment credentials, give the link only.
- `tt_backtest_workbench(<template id>, start, end)`: free; confirm no existing run already answers the question, and quote `next_run.quote` verbatim.

**What to implement:**

1. Run 1: `tt_backtest_strategy` over the TCP-2 window, `type=positional` (the cycle is multi-week; `intraday` would force-close at 15:30), `candle_freq=1`, `trade_price=Open`. State the charge and
   get an explicit yes before submitting.
2. Poll `tt_backtest_status` (10 to 75 seconds) and read results with `tt_backtest_result` and fills with `tt_backtest_trades` (free). Slice as needed without re-running.
3. Run 2 only if justified: `trade_price=Close` to measure the look-ahead effect, or a corrected template if run 1 exposed a template bug. Each needs a fresh yes and a new row in `findings.md`.
4. Record every run id and URL. Do not paste long trade lists into context; page with the summary and `limit`.

**Done when:** at least one finished run is readable and logged with ids and cost.

**Commit:** `docs(plan): log Tradetron CC backtest runs`

---

## TCP-6 — Reconcile, write the verdict, save the learnings

**Files to change / create:**
- `docs/plan/tradetron-cc-backtest-poc/findings.md` — sections "Reconciliation" and "Verdict".
- `docs/reference/tradetron.md` — platform findings under "Backtesting" or "Verified findings".
- `DECISIONS.md` — only if the verdict changes what NiftyShield does.
- `docs/plan/README.md`, `TODOS.md`, `tasks.md` — Step 5a close.

**Before any code:**
- If TCP-3 ended in STOP, this task records that result and skips the reconciliation.
- A reusable reconciliation CLI goes in `scripts/dev/` as a tested CLI and triggers the Design review in `prompt.md`; a one-off comparison stays in `scratch/` per `SCRATCH.md`. Prefer the one-off
  unless a second strategy is already planned.

**What to implement:**

1. Compare backtest fills against the TCP-2 table cycle by cycle: strike, entry price, exit trigger, exit price, P&L. Separate three kinds of difference: strike selection (Greeks methodology or Find
   Strike), fill price (`trade_price`, slippage), and charges. State the sample size beside every comparison.
2. Write the verdict in plain terms: reproduces, partially reproduces (list what and why) or does not reproduce, plus whether Tradetron can be relied on for POC validation of this strategy class. Say
   what was measured and mark every inference as an inference. Make no profitability claim.
3. Save learnings per the save-map in `prompt.md`: platform behaviour into `docs/reference/tradetron.md`, a decision into `DECISIONS.md` if warranted, session-log line in `TODOS.md`.
4. Close per Step 5a: `docs/plan/README.md` status row, `tasks.md` ticks and SHAs. Run `python -m scripts.dev.reflow_md` on every changed file in this folder before committing, then archive per
   §Conventions *Completion → archive*.

**Done when:** `findings.md` carries the reconciliation and verdict, the reference doc has the platform findings and the story is closed or archived.

**Commit:** `docs(plan): close Tradetron CC backtest POC with verdict`

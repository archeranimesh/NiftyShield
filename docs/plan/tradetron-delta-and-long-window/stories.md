
# Tradetron delta check and long-window validation — story specs

> One task per session. Find the first unchecked item in `tasks.md`. That is your only task. Full implementation rules in `CLAUDE.md` and `REVIEW.md`. After each task: set `SHA:` on the task line +
> tick the box, update the story status summary, add one line to `TODOS.md`. See `docs/plan/README.md` §Conventions.

All tasks are documentation or read-only investigation: no `src/` or `scripts/` change, so no unit tests and no `code-reviewer` run (docs-only diff). Tradetron MCP tools are deferred; load schemas
with `ToolSearch` before the first call. Never write credentials, tokens or the wallet top-up link into any file. Every task writes to `findings.md` in this folder; create it on TDL-1 with a
one-paragraph header and no task checkboxes. Run `python -m scripts.dev.reflow_md` on every changed `.md` in this folder before committing.

---

## TDL-1 — Free own-data delta check on the six run-2 strikes

**Files to change / create:**
- `docs/plan/tradetron-delta-and-long-window/findings.md` — new, section "Own-data delta check".
- `scratch/` — a throwaway query script only if needed; follow `SCRATCH.md`.

**Before any code:**
- `DB_REGISTRY.md` first; never assume a table is empty or absent. Find where Upstox chain Greeks are stored: the intraday snapshot tables (`intraday_market_snapshots`, `nuvama_intraday_snapshots`),
  `daily_snapshots` Greeks columns (populated from 2026-04-25 per `CONTEXT.md`), and the Parquet chain store (`ChainWriter`/`ChainReader`, `src/backtest/`). Use the graph for the readers.
- The six Tradetron picks (run 2, `ttbt-999069146261005`, from the archived `findings.md`): 2026-08-12 10:00 NIFTY 29SEP2026 25600 CE; 08-19 11:02 25100 CE; 09-02 15:12 24700 CE; 09-09 10:00 24250 CE;
  09-16 10:00 27OCT2026 24400 CE; 09-25 10:00 27OCT2026 23950 CE.

**What to implement:**

1. For each pick, look for a stored Upstox delta for that exact instrument at the nearest timestamp, and record the timestamp gap. Aggregate in SQL; named columns, `LIMIT 10`.
2. Where an exact instrument-time row is missing, say so; do not interpolate or fill from a model. If a chain snapshot exists for the date but not the minute, record the nearest and its gap.
3. Table: date and time, instrument, Tradetron's pick, Upstox delta found, gap in minutes, source table. Then the verdict in plain terms: is the Upstox delta of Tradetron's pick near 0.15, above, or
   below, by how much, and what does that say about the direction of the strike gap against paper (paper's strikes were 0 to 200 points lower). Mark inference as inference; n = at most 6.
4. If coverage is missing for most dates, record that as the result and note that TDL-2 is then the delta check.

**Done when:** the table and verdict, or a recorded coverage gap, are in `findings.md`.

**Commit:** `docs(plan): add own-data delta check for Tradetron strikes`

---

## TDL-2 — Live Offline Greeks probe, Tradetron versus Upstox

**Files to change / create:**
- `docs/plan/tradetron-delta-and-long-window/findings.md` — section "Live Greeks probe".
- `docs/reference/tradetron.md` — platform findings under "Greeks probe results".

**Before any code:**
- Read the existing probe results in the reference doc and `tt_get_strategy(999078810)` (`NS Greeks Probe`); the probe writes LTP, delta, gamma, theta, vega, rho and IV into runtime vars once at 09:30
  and you read them with `tt_get_strategy_counters(<SID>, changed_only=true)`. Reuse or extend it; do not start from nothing. Create or edit templates is free; check `tt_list_my_strategies` for room.
- Check the cost and terms of a Live Offline deploy with the deploy tool's own quote before using it. No orders reach a broker on Live Offline. Get Animesh's go-ahead before deploying, and note market
  hours: the probe only populates during the session, with a 1-minute delay on the free plan.
- Read `docs/plan/greeks-bs-fallback/prompt.md`: Upstox returns all-zero Greeks for the yearly bucket (Dec 2026 expiry) with real quotes, confirmed 2026-07-22 and 2026-08-06; quarterly and monthly
  clean.

**What to implement:**

1. Probe instruments by instrument CSV (`'NFO,NIFTY 50,<expiry token>,CE|PE,<strike spec>,,<offset>'`; numeric strikes go in OFFSET; use `ATM-SPOT`, never plain `ATM`): a near-dated contract, a
   monthly, and a far-dated one (Dec 2026, an nth `Current Month` offset; confirm which offset reaches December rather than assuming). Record the resolved strike in a runtime var, as the reference doc
   requires. Read `Delta`, `Iv`, `Gamma`, `Theta`, `Vega` and LTP for each.
2. At the same timestamp, read the Upstox chain for the same instruments with the repo's existing read-only fetch (graph first; do not write a new fetcher). Note both timestamps; they will differ by
   at least the 1-minute delay.
3. Table: instrument, Tradetron delta and IV, Upstox delta and IV, difference, timestamps. State plainly whether Tradetron returns nonzero Greeks on the far-dated contracts where Upstox returns 0.0.
4. Mark the table as a reference for `greeks-bs-fallback` GF-1 and GF-5, with the limits: one timestamp, a few strikes, Tradetron's delta methodology unknown, another model and not ground truth. Do
   not edit that story's files.
5. Add what holds beyond this strategy to the reference doc.

**Done when:** the side-by-side table is in `findings.md`, the far-dated result is stated, and the reference doc is updated.

**Commit:** `docs(plan): add Tradetron live Greeks probe results`

---

## TDL-3 — Long-window pre-flight on CC template v2

**Files to change / create:**
- `docs/plan/tradetron-delta-and-long-window/findings.md` — section "Long-window pre-flight".

**Before any code:**
- Free calls only. `tt_backtest_workbench(999082574, start, end)` for the quote (never estimate), `tt_check_backtestability` for the verdict. Template v2 body is
  `docs/archive/plan/tradetron-cc-backtest-poc/template.md`. The engine allows up to 60 months per run.

**What to implement:**

1. Pre-flight v2 over candidate windows, for example the longest the check accepts, and a post-2026-04 window. Record each verdict verbatim, including `data_coverage` and `coverage_window` results,
   skipped checks and the recommended run type.
2. Find from the check output where data starts for NIFTY options and whether the Thursday-to-Tuesday monthly-expiry change in April 2026 is handled. If the check does not say, record that and note
   the funded run in TDL-5 is what will show it.
3. Note any pre-flight blocker or warning that would hit a long window (for example a keyword absent from the BT engine).
4. Pick the window or windows and the expected number of runs, with the quote. Decision recorded here; spend waits for TDL-4.

**Done when:** verdicts, coverage facts and the chosen window with the quoted price are in `findings.md`.

**Commit:** `docs(plan): add Tradetron long-window pre-flight`

---

## TDL-4 — Own-side comparator audit and the go or no-go

**Files to change / create:**
- `docs/plan/tradetron-delta-and-long-window/findings.md` — section "Comparator and budget".

**Before any code:**
- `DB_REGISTRY.md` first. Use the graph on `src/backtest/` (`ChainWriter`, `ChainReader`, F&O bhavcopy ingest and loader, `compute_ivr`, VIX ingest). Read `BACKTEST_PLAN.md` (Phase 0 only) to see what
  an own backtest is meant to cover and what is already built.

**What to implement:**

1. List what own-side data exists and its date range: F&O bhavcopy, chain Parquet, VIX, equity and index bhav. Aggregate; no table dumps.
2. State whether a CC, PP or Collar cycle list could be built offline from that data over the TDL-3 window, with what delta source (bhavcopy has no Greeks; a model delta would overlap
   `greeks-bs-fallback`). Say what comparator a long Tradetron run would have: paper (only 2026-08-12 onward), own bhavcopy, or none.
3. Go or no-go for TDL-5 and TDL-8: if there is no comparator, a long run is interpretable only as a screen of rule viability and exit mix, and `findings.md` says so. Write the budget (number of runs,
   total at Tradetron's quote, wallet balance from `tt_wallet_balance`) and **stop for Animesh's approval** before TDL-5.

**Done when:** the audit, the go or no-go and the approved budget are written down.

**Commit:** `docs(plan): add own-side comparator audit and run budget`

---

## TDL-5 — CC long-window funded run

**Files to change / create:**
- `docs/plan/tradetron-delta-and-long-window/findings.md` — section "CC long-window run".
- `docs/reference/tradetron.md` — platform findings.

**Before any code:**
- TDL-3 chose the window and TDL-4 approved the budget; Animesh confirms the spend again in-session before submit. `tt_wallet_balance` and the workbench quote first.

**What to implement:**

1. Run template 999082574 over the chosen window, `type=positional`, `trade_price=Open`, 1-minute candles (change nothing else; v2 is the live-code rule set). Poll `tt_backtest_status`, then read with
   `tt_backtest_trades` and `tt_backtest_result` (free). Record `job_id`, `bt_id`, `report_url` and the price paid.
2. Cycle table (entry, strike, credit, exit, exit ratio, gross). Report the round-trip count and say plainly if it is under 30 (the report flags it).
3. Exit mix by exit-price ratio: how many at the 30% target, how many above 2.5x, and any exits near the delta or DTE rules. Say which untested paths (2.5x loss, 0.55 delta, DTE <= 5) now fired and
   which did not. The report has no exit-reason column, so state exit type as inference.
4. Split pre and post the April 2026 expiry change if the window spans it. Costs from the report. A `FinalClose` fill at the window end is not a rule exit.
5. Compare with paper only on the overlap (2026-08-12 onward); no profitability claim.

**Done when:** a finished run is logged with ids and settings, and the tables above are in `findings.md`.

**Commit:** `docs(plan): add CC long-window Tradetron run`

---

## TDL-6 — PP and Collar rules from code and the paper ground truth

**Files to change / create:**
- `docs/plan/tradetron-delta-and-long-window/findings.md` — sections "Live PP and Collar rule set" and "Paper PP and Collar ground truth".

**Before any code:**
- `DB_REGISTRY.md` first. Read the rules from code via the graph, as TCP-1 did for CC: `src/strategy/pp_overlay_v1.py`, `src/strategy/collar_overlay_v1.py`, the PP and Collar paths in
  `src/strategy/exit_signals.py`, `src/paper/constants.py`, and the entry scripts under `scripts/strategies/`. Archived specs are stale; the code is the authority.

**What to implement:**

1. Table of every threshold each template must encode (strike rule, expiry rule, delta targets, profit and loss exits, DTE rules, roll rules), each with a code-sourced value and line, and MATCH or
   DIFFERS against any archived spec.
2. Paper ground truth from `paper_trades` for the PP and Collar legs (the overlay rides `paper_nifty_overlay`; role names per `DB_REGISTRY.md`): cycle table like TCP-2's, sample size, window. Note
   what the DB does not hold (delta at entry, exit trigger).
3. List what is expressible on Tradetron and what is a GAP (for the Collar, the CC leg is already solved; the long put and any roll are new).

**Done when:** the rule table and the paper tables are in `findings.md`.

**Commit:** `docs(plan): add PP and Collar rules and paper ground truth`

---

## TDL-7 — PP and Collar templates

**Files to change / create:**
- `docs/plan/tradetron-delta-and-long-window/template_pp.md` and `template_collar.md` — the specs, validated.
- `docs/plan/tradetron-delta-and-long-window/findings.md` — section "PP and Collar templates".

**Before any code:**
- `tt_get_tradetron_quickstart` once. Reuse the v2 CC structure (two sets for the nearest-monthly rule, per-set exits, flat-position gate). Restate the logic in plain English and flag ambiguities
  before authoring. Never pass a `tt_get_strategy` body to a create call.

**What to implement:**

1. Author each template from the TDL-6 rule table, `tt_validate_markdown` until clean, `tt_check_backtestability` over the TDL-3 window. Record each verdict verbatim and a GO, PARTIAL or STOP.
2. Create each GO or PARTIAL template with `tt_create_strategy` using its dry-run token; read back with `tt_get_strategy` and confirm set, condition and leg counts. Record ids and `edit_url`. Do not
   deploy.
3. A STOP is a valid result: record the reason and skip the template.

**Done when:** each template exists with its id recorded, or its STOP reason is.

**Commit:** `docs(plan): record PP and Collar Tradetron templates`

---

## TDL-8 — PP and Collar funded runs and reconciliation

**Files to change / create:**
- `docs/plan/tradetron-delta-and-long-window/findings.md` — section "PP and Collar runs".
- `docs/reference/tradetron.md` — platform findings.

**Before any code:**
- Budget approved in TDL-4; Animesh reconfirms the spend in-session. Workbench quote and `tt_wallet_balance` first.

**What to implement:**

1. One run per built template over the TDL-3 window (positional, `Open`, 1-minute); read fills and report figures for free. Record ids, settings and price paid.
2. Reconcile against the TDL-6 paper tables on the overlapping window only, cycle by cycle (strike, entry, exit, P&L), separating strike selection, fill price and charges, with the sample size beside
   each comparison. Round-trip count and exit mix as in TDL-5.
3. Plain verdict per strategy: reproduces, partially or not, and what a long window shows that paper cannot. No profitability claim.

**Done when:** runs are logged and reconciled in `findings.md`.

**Commit:** `docs(plan): add PP and Collar Tradetron runs`

---

## TDL-9 — IC v1 and v2 buildability audit

**Files to change / create:**
- `docs/plan/tradetron-delta-and-long-window/findings.md` — section "IC buildability".

**Before any code:**
- Read `docs/reference/tradetron.md` "IC v1 vs Tradetron templates" and `docs/reference/tradetron_ic_templates.md` if present (an untracked draft at the time of writing). Read the live IC thresholds
  from code via the graph (`src/strategy/ic_nifty_v1.py`, `IronCondorV2`, `exit_signals.py`), not from archived specs.

**What to implement:**

1. Table of each IC v1 and v2 rule (entry delta, wing width, credit-percent exits, DTE gates, limit-at-mid, re-entry) with Tradetron keyword, EXPRESSIBLE, GAP or UNKNOWN, and BT-engine support (note
   `Leg SL trail`, `PCR` and `Total OI` are absent from it).
2. Run `tt_check_backtestability` on a minimal skeleton only if it adds information; free.
3. Verdict GO, PARTIAL or STOP. No template, no funded run. A GO becomes a follow-up story if Animesh wants it.

**Done when:** the table and verdict are in `findings.md`.

**Commit:** `docs(plan): add IC buildability audit for Tradetron`

---

## TDL-10 — Verdict on the data-purchase question and close

**Files to change / create:**
- `docs/plan/tradetron-delta-and-long-window/findings.md` — section "Verdict".
- `docs/reference/tradetron.md` — platform findings not yet saved.
- `DECISIONS.md` — only if the verdict changes what NiftyShield does (revisit the 2026-10-05 Tradetron rule).
- `docs/plan/README.md`, `TODOS.md`, `tasks.md` — Step 5a close, then archive per §Conventions *Completion → archive*.

**What to implement:**

1. Answer the question Animesh set: did a long Tradetron screen change whether to buy paid historical data, and for which strategies? State what it could and could not tell (rule viability, cycle
   counts, exit mix and rough P&L scale versus fill quality, liquidity, margin), with round-trip counts beside every figure and no edge claim under 30 round trips.
2. State the delta result (TDL-1, TDL-2) and what it means for the 2026-10-05 rule: if the deltas agree, say whether Tradetron can now be trusted for strike-level reconciliation; if not, the rule
   stands.
3. State plainly whether Tradetron's Greeks gave `greeks-bs-fallback` a usable reference and name the one decision Animesh should take about GF-1 and GF-5.
4. Save learnings per the save-map. Run `python -m scripts.dev.reflow_md` on every changed file, then close per Step 5a and archive.

**Done when:** the verdict is in `findings.md`, the reference doc has the platform findings, and the story is archived.

**Commit:** `docs(plan): close Tradetron delta and long-window story`


# Dhan data API POC — story specs

> One task per session. Find the first unchecked item in `tasks.md`. That is your only task. Full implementation rules in `CLAUDE.md` and `REVIEW.md`. After each task: set `SHA:` on the task line +
> tick the box, update the story status summary, add one line to `TODOS.md`. See `docs/plan/README.md` §Conventions.

All tasks are documentation or read-only investigation unless DDP-3 or DDP-4 produces a reusable CLI (then `scripts/dev/`, tested, after the design review in `prompt.md`). Every task writes to
`findings.md` in this folder; create it on DDP-1 with a one-paragraph header and no task checkboxes. Run `python -m scripts.dev.reflow_md` on every changed `.md` in this folder before committing.
Never write credentials, tokens, client ids or payment links into any file.

---

## DDP-1 — Free docs read

**Files to change / create:**
- `docs/plan/dhan-data-poc/findings.md` — new, section "Dhan docs read".

**Before any code:**
- `src/dhan/CLAUDE.md` for what the repo already does with Dhan (holdings and intraday, not a data-API client).

**What to implement:**

1. Read Dhan's public data-API documentation and record, with the page or section named: the historical or expired options endpoints; the fields returned (OHLC, volume, OI, IV, delta and other Greeks,
   spot); strike coverage (an ATM-relative window or a full chain) and expiry coverage (weekly, monthly, far-dated); history depth; candle sizes; rate limits; the subscription price and what the
   "historical data set" bundled with the purchase contains.
2. Mark each item as stated in the docs or unclear. Do not infer fields from memory, and do not claim a field exists that the docs do not name.
3. Score the POC criteria in `prompt.md` as pass, fail or cannot tell from docs. Cannot tell is a valid answer and moves the check to DDP-3.
4. Report to Animesh before DDP-2. The purchase is his decision.

**Done when:** the docs-read table and the criteria scores are in `findings.md`.

**Commit:** `docs(plan): add Dhan data API docs read`

---

## DDP-2 — Animesh buys the one-month POC

**Files to change / create:**
- `docs/plan/dhan-data-poc/findings.md` — section "POC purchase".

**What to implement:**

1. Animesh buys the plan. Record the plan name, the price he states, the date, and how the data is accessed (API calls, a downloadable file, both). No tokens, client ids or links.
2. Note the dataset's stated limits at purchase (period, request quotas). Do not run a pull until DDP-3.

**Done when:** the purchase facts are in `findings.md` and the access method is known.

**Commit:** `docs(plan): record Dhan POC purchase`

---

## DDP-3 — Coverage inventory on the real dataset

**Files to change / create:**
- `docs/plan/dhan-data-poc/findings.md` — section "Coverage inventory".
- `scratch/` — a throwaway pull and inventory script per `SCRATCH.md`; promote to `scripts/dev/` only if it will be re-run.

**Before any code:**
- `SCRATCH.md`. Read the entry-strike rules for each strategy from code via the graph (`src/strategy/`, `exit_signals.py`), not archived specs, to know which delta bands and DTE ranges the dataset has
  to cover. Bash output discipline applies: aggregate before printing.

**What to implement:**

1. Pull a small sample, then inventory the dataset: date range, expiries present (weekly, monthly, Dec 2026, Jun 2027, older expiries), strike range per expiry, candle size, and per field the share of
   rows that are present and nonzero (delta, IV, OI, bid and ask if any).
2. Table per strategy (CC, PP, Collar, IC v1, IC v2): covered, partly covered or missing, with the reason (strike outside the stored window, expiry absent, delta absent).
3. Say what the dataset cannot give (for example bid-ask, margin), as measured.

**Done when:** the inventory and the per-strategy table are in `findings.md`.

**Commit:** `docs(plan): add Dhan POC coverage inventory`

---

## DDP-4 — Old-data validation

**Files to change / create:**
- `docs/plan/dhan-data-poc/findings.md` — section "Old-data validation".

**Before any code:**
- `DB_REGISTRY.md` first. Chain Parquet via the files under `data/historical/option_chain/intraday/`; bhavcopy via the graph (`src/backtest/`). TDL-1 in
  `docs/plan/tradetron-delta-and-long-window/findings.md` holds the six run-2 strikes to reuse as test points.

**What to implement:**

1. On overlapping date, expiry and strike, compare Dhan against the stored Upstox chain: LTP, OI, IV and delta (if present); report the difference distribution, not a pass or fail on one row.
2. Compare Dhan or bhavcopy close prices against the stored chain on the same days; flag dates and expiries where the stored chain is missing or stale.
3. Compare Dhan against `paper_trades` for the overlapping 2026-08-12 onward window: entry and exit prices where the DB holds them, with the paper entry time unknown (TDL-1 found the DB does not store
   it). Say which comparisons are impossible and why.
4. Sample size beside every figure. Mark inference as inference. A disagreement is a finding, not a failure; say which source is more likely wrong only if the evidence supports it.

**Done when:** the validation tables are in `findings.md`.

**Commit:** `docs(plan): add Dhan POC old-data validation`

---

## DDP-5 — Contract questions

**Files to change / create:**
- `docs/plan/dhan-data-poc/findings.md` — section "Contract questions".

**Before any code:**
- `docs/plan/greeks-bs-fallback/prompt.md` and `REFERENCES.md` (yearly-expiry Greeks note). Read only; do not edit those files.

**What to implement:**

1. From the full stored 09:00 to 15:30 chain (not only the 09:00 sample), find the first day and time the Dec 2026 chain shows nonzero Upstox deltas, and what else changed that day (row count, strike
   range, DTE). Report the DTE at the flip. The cause is an inference unless the data shows it.
2. Record the yearly-bucket relabelling (2027-06-29 until about 2026-07-24, then 2026-12-29) and whether Jun 2027 is stored anywhere.
3. From Dhan, record what delta or IV looks like for Dec 2026 and Jun 2027 inside the window where Upstox was zero, and for the 16 deep-OTM strikes (20050 to 20800) that are still zero. State whether
   Dhan values are exchange fields or model values, only if the docs say.
4. State the one decision Animesh should take about `greeks-bs-fallback` (for example, whether GF-5 validates against Dhan, or whether the yearly bucket still needs a fallback at all). Flag it; do not
   edit that story.

**Done when:** the flip date, the relabelling and the Dhan comparison are in `findings.md` with the decision flagged.

**Commit:** `docs(plan): add Dhan POC contract findings`

---

## DDP-6 — Verdict and close

**Files to change / create:**
- `docs/plan/dhan-data-poc/findings.md` — section "Verdict".
- `DECISIONS.md` — only if the verdict changes what NiftyShield does.
- `docs/plan/README.md`, `TODOS.md`, `tasks.md` — Step 5a close, then archive per §Conventions *Completion → archive*.

**What to implement:**

1. Answer: buy the full year or not, for which strategies, and what a month could not show. State the POC criteria result (DDP-1, DDP-3) and the validation result (DDP-4) with sample sizes; no edge or
   profitability claim from a one-month sample.
2. State what feeds the Tradetron story: the comparator for TDL-4 and the purchase view for TDL-10. Do not edit that story's files; hand Animesh the lines.
3. Save learnings per the save-map in `prompt.md`; run `reflow_md` on every changed file; close and archive.

**Done when:** the verdict is in `findings.md` and the story is archived.

**Commit:** `docs(plan): close Dhan data API POC story`

# PP protection cost study — story specs

> One task per session. Find the first unchecked item in `tasks.md`. That is your only task. Full implementation rules in `CLAUDE.md` and `REVIEW.md`. After each task: set `SHA:` on the task line +
> tick the box, update the story status summary, add one line to `TODOS.md`. See `docs/plan/README.md` §Conventions.

---

## PPS-1 — Save the PP cycles and reproduce the Pareto numbers

**Files to change / create:**
- `docs/plan/tradetron-backtest/tradetron-pp-protection-study/pp_cycles.md` — one row per cycle.
- `docs/plan/tradetron-backtest/tradetron-pp-protection-study/findings.md` — section "PP cycle baseline".

**Before any code:**
- Do this first: the per-trade index ages out within days of the 2026-10-11 run. Read `tt_backtest_workbench` for template 999135746 to confirm the run is still readable.

**What to implement:**

1. Page the fills of job `ttbt-999113502261011` with `tt_backtest_trades` (limit 200; the page lands in a file, process it with Python under `-I`, do not read it into context).
2. Pair each buy with its sell and write one row per cycle: entry and exit date, NIFTY at each (`underlying_price`), strike, strike distance below spot in percent, entry premium, premium as percent of
   spot, exit price, cycle NIFTY move in percent.
3. Reproduce and record: cycle count and mean length, move percentiles (10, 20, 50, 80), share of negative cycles, share of total downside carried by the worst 20% of cycles and its cutoff, mean
   strike distance and per-cycle premium percent. Note that crash exits truncate some cycles.
4. If any figure differs from the numbers in `prompt.md`, say so and keep the new one.

**Done when:** `pp_cycles.md` has all cycles and `findings.md` has the baseline section.

**Commit:** `docs(plan): add PP cycle baseline for protection study`

---

## PPS-2 — Put-depth templates

**Files to change / create:**
- `docs/plan/tradetron-backtest/tradetron-pp-protection-study/template_put.md` — the spec for the three depths.
- `docs/plan/tradetron-backtest/tradetron-pp-protection-study/findings.md` — section "Put templates".

**Before any code:**
- `tt_get_tradetron_quickstart` once; `tt_lookup_keyword` for `Find Strike` and any spot-offset or percent-OTM selection mode before writing a strike term (never improvise keyword syntax).

**What to implement:**

1. Reuse `template_pp.md` of `tradetron-delta-and-long-window/` (two sets, nearest monthly with at least 14 DTE, flat gate, one lot, Market Price). Remove the crash exit; the only exit is DTE <= 5.
2. Strike control. First choice: a percent-or-points distance below spot (about 2.5% and 5% OTM) if the platform has a verified mode for it. Fallback (inference from the PP sample: 0.20 delta sat
   about 3.4% OTM, 1 sigma of a month about 4%): `Find Strike` by delta at about 0.27 (shallow, about 2.5%), 0.20 (base, about 3.4%) and 0.10 (deep, about 5%). Record which was used and why.
3. Validate (`tt_validate_markdown`, mode create) with zero errors, create, read back with `tt_get_strategy`, then `tt_check_backtestability` passing the leg instrument id (1855) over 2021-10-11 to
   2026-10-01. Record id, verdict, warnings and the workbench quote per template. No spend.

**Done when:** three templates exist with ids and verdicts recorded, or a skip is recorded.

**Commit:** `docs(plan): add put-depth templates for protection study`

---

## PPS-3 — Funded put runs and the per-depth table

**Files to change / create:**
- `docs/plan/tradetron-backtest/tradetron-pp-protection-study/findings.md` — section "Put-depth runs".
- `docs/plan/tradetron-backtest/tradetron-pp-protection-study/put_cycles.md` — paired cycles for each depth (save at once; the index ages out).
- `docs/reference/tradetron.md` — platform findings.

**Before any code:**
- `tt_wallet_balance` and the workbench quote first. Ask Animesh to confirm the spend for three runs (₹60 at the ₹20 quote); do not assume the CC run's extra ₹20.

**What to implement:**

1. One run per depth, `positional`, `Open`, 1-minute, 2021-10-11 to 2026-10-01. Log job ids, bt_ids, report URLs, price paid, and the wallet before and after.
2. Per depth, per cycle: premium paid, put value at roll, cycle NIFTY move, hold-plus-put P&L for one lot (65 units): `(NIFTY exit - NIFTY entry) x 65 + put P&L`.
3. Table per depth with cycle count beside each figure: annual gross premium (percent of notional), net annual cost after payoffs, realised deductible (median and 90th percentile of the worst cycles),
   share of cycles with hold-plus-put loss beyond 3% and beyond 5% of notional, worst cycle.
4. State what is inference (cycle chaining, fixed notional) and flag any figure under 30 cycles.

**Done when:** runs are logged and the per-depth table is in `findings.md`.

**Commit:** `docs(plan): add put-depth runs for protection study`

---

## PPS-4 — CC rental variant

**Files to change / create:**
- `docs/plan/tradetron-backtest/tradetron-pp-protection-study/findings.md` — section "CC rental".

**Before any code:**
- Template 999082574 (CC v2) read with `tt_get_strategy`. Animesh confirms the ₹20 in-session.

**What to implement:**

1. Copy the v2 spec from the read-back `summary_md`, change only the loss exit from 2.5x to 2x the entry price (a loss of one credit), validate, create, pre-flight (pass the instrument id), run once.
2. Report: trips, realised net rental per year (percent of notional), loss exits, and for each loss exit the gap overshoot (exit price against 2x entry), with the trip count beside each. Compare with
   the 2.5x run (196 trips, +₹52.9k gross, about ₹10.6k a year).
3. State whether "downside held to about one credit" held in practice.

**Done when:** one finished CC run is logged and the rental/overshoot table is in `findings.md`.

**Commit:** `docs(plan): add CC rental run for protection study`

---

## PPS-5 — Selection rule, sizing note and close

**Files to change / create:**
- `docs/plan/tradetron-backtest/tradetron-pp-protection-study/findings.md` — sections "Selection" and "Sizing".
- `docs/reference/tradetron.md`, `DECISIONS.md` (only if a rule changes), `docs/plan/README.md`, `TODOS.md`, the epic `README.md` — Step 5a close.

**What to implement:**

1. Propose the selection rule for Animesh to approve before applying it. Candidate: the cheapest net annual cost whose hold-plus-put loss stays within X% in at least 80% of cycles and leaves the worst
   20% of cycles (which carry about 81% of the downside) at no more than half their unhedged loss. X comes from Animesh's loss limit.
2. Ask for the rupee exposure to protect and the largest drawdown he would not accept. Record both.
3. Give the lot formula: lots = (share of loss to cover) x (loss on one lot) / (payoff per lot at the chosen depth, from PPS-3), and a table for a ₹15 lakh holding at 10%, 15% and 25% falls with the
   annual premium it implies. Note that the deductible and the 5x-type caps matter in deep falls.
4. Close per Step 5a; run `python -m scripts.dev.reflow_md` on every changed file.

**Done when:** the selection rule, chosen depth and sizing note are in `findings.md` with cycle counts, and the story is closed.

**Commit:** `docs(plan): close PP protection cost study`

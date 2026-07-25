# Paper IC Daily Snapshot Wiring — Story Specs

**Trigger:** 2026-07-25 Cowork session. User asked for a daily P&L graph for `paper_ic_nifty_v2_monthly`
(IC V2). Investigation found `paper_leg_snapshots` has zero rows for every IC variant (V1
weekly/monthly/leaps/yearly and V2 monthly) and for CSP/CC/PP/Collar — only the three-track
strategies (`paper_nifty_futures`, `paper_nifty_proxy`, `paper_nifty_spot`) have daily snapshot
history (50 rows each, 2026-05-11 → 2026-07-24), because `paper_3track_snapshot.py` is the only
caller of `PaperStore.record_leg_snapshot()` in the entire codebase. `paper_ic_snapshot.py` (the
EOD cron that already computes per-leg unrealized/realized/total P&L for its Telegram report)
throws that computation away instead of persisting it.

**Backfill is explicitly out of scope** (user directive) — chain-snapshot Parquet data only goes
through May 2026, so IC V2's 2026-07-03→07-24 cycle can't be reconstructed day-by-day; the
reconstructed inception-to-date number already given to the user (−₹3,056.63, from raw
`paper_trades` fill prices) stands as the historical record for that closed cycle. This story is
about every cycle **from today forward**.

**End goal (all four, once daily rows exist):**
1. Daily P&L graph, per strategy.
2. Realized P&L from inception.
3. Realized P&L for the current calendar month.
4. Unrealized P&L from inception.

---

## SNAP-1 — Confirm `realized_pnl` / `unrealized_pnl` snapshot semantics (cumulative vs. daily delta)

**Problem:** Before wiring a new writer or building report queries, we need to know for certain
whether `paper_leg_snapshots.realized_pnl`/`unrealized_pnl`/`total_pnl` are **cumulative-as-of-date**
values or **daily deltas**. Getting this wrong silently produces either double-counted or
under-counted totals in SNAP-4's reporting queries — this is exactly the kind of "SQL-layer
aggregation" mistake Rule 1 in `CLAUDE.md` exists to prevent.

**Task:**
1. Read `PaperTracker.compute_pnl()` and `record_daily_snapshot()` (`src/paper/tracker.py`) via
   the graph (`get_code_snippet`, not `Read`) — confirm what each field represents at write time.
2. Cross-check against the three-track data that already exists:
   `paper_nifty_futures`/`paper_nifty_proxy`/`paper_nifty_spot`, 50 rows each, 2026-05-11 →
   2026-07-24. Pull a short date-ordered slice (`SELECT snapshot_date, realized_pnl, unrealized_pnl,
   total_pnl ... LIMIT 10`, per Rule 1) and check: does `realized_pnl` monotonically move only on
   days a leg actually closed (cumulative), or does it reset/fluctuate daily (delta)?
3. Confirm the `total_pnl == unrealized_pnl + realized_pnl` invariant (`CONTEXT.md` states
   `record_leg_snapshot` enforces this at write time) holds across the sample.
4. Output: a short finding appended to this file under `### SNAP-1 findings`, stating the
   semantics in one sentence, plus the exact query used so SNAP-4 can reuse it without
   re-deriving.

**Files touched:** none (read-only). Append findings to this file via `Edit`.

**Why Claude, not Antigravity:** Pure graph-query + read investigation with no fixed spec for
what the answer will be — exploratory, not mechanical. Matches Step 3b's "exploratory work where
the spec may change" and "requiring graph queries mid-implementation" rows.

---

## SNAP-2 — Wire `record_leg_snapshot()` into `paper_ic_snapshot.py` for all IC variants

**Prerequisite:** SNAP-1 complete (need confirmed field semantics before writing values that will
be read by SNAP-4's queries).

**Problem:** `scripts/strategies/ic/paper_ic_snapshot.py`'s `process_variant()` already computes
per-leg P&L for its Telegram report but never calls `store.record_leg_snapshot()`. This is why
`paper_leg_snapshots` has zero rows for `paper_ic_nifty_v1_weekly/monthly/leaps/yearly` and
`paper_ic_nifty_v2_monthly` despite the cron running daily (`45 15 * * 1-5` per `CONTEXT.md`).

**Fix:**
1. In `process_variant()`, after the existing per-leg P&L computation used for the Telegram
   message, add a call to `store.record_leg_snapshot(...)` per leg, per variant — mirror the
   exact call shape already used in `paper_3track_snapshot.py` (get the call site via
   `search_code("record_leg_snapshot")`, do not write the call from memory).
2. Respect the existing flat-leg convention (BUG-014, `CLAUDE.md`/`CONTEXT.md`): do not write a
   snapshot for a leg with `net_qty == 0` — matches the guard already used elsewhere for closed
   legs.
3. Confirm `total_pnl == unrealized_pnl + realized_pnl` holds for every write (the store method
   already enforces this per `CONTEXT.md` — confirm it doesn't silently swallow a mismatch for
   the IC call shape specifically, e.g. wing legs vs. short legs having different P&L sign
   conventions).

**Tests required:**
- Happy path: one IC variant with all four legs open → `record_leg_snapshot` called once per
  leg with correct values (mock `PaperStore`, assert call args).
- Edge case: a variant with a flat leg (post-close, `net_qty == 0`) → `record_leg_snapshot` is
  **not** called for that leg (matches BUG-014 convention) — use a spy that fails the test if
  invoked, same pattern as the existing BUG-014 regression test in `test_store.py`.

**Financial-logic gate:** This persists real P&L numbers that SNAP-4's report and any future
Telegram/dashboard consumer will treat as ground truth — per `CLAUDE.md`'s AutoTrigger table,
this is a `greeks-analyst`-adjacent change (option chain / delta fields) and a P&L persistence
change, both requiring the real `@code-reviewer` gate. Cowork cannot spawn the local
`.claude/agents/code-reviewer` subagent — per the project's documented substitution pattern
(used for BUG-014), apply `REVIEW.md`'s checklist directly and state explicitly in the commit
message that this is a substitution, not an equivalent automated gate.

**Files touched:** `scripts/strategies/ic/paper_ic_snapshot.py`, `tests/unit/strategies/ic/test_paper_ic_snapshot.py` (new or existing).

**Why Claude, not Antigravity:** Only 1–2 files, but the exact `record_leg_snapshot()` call shape
must be resolved from the live store API via graph query (Step 3b's third Claude-routing
criterion) rather than assumed — same failure class `CLAUDE.md` documents from 2026-04-25
(writing a call from memory that doesn't match the real signature). Also financial logic, which
this project routes through the real code-reviewer gate rather than Antigravity's persona-based
self-review.

---

## SNAP-3 — Audit whether CSP/CC/PP/Collar have the same wiring gap

**Problem:** `paper_leg_snapshots` also has zero rows for `paper_csp_nifty_v1` and any CC/PP/Collar
overlay strategy. Unknown whether these have their own EOD snapshot cron that has the same
missing-`record_leg_snapshot`-call gap as `paper_ic_snapshot.py`, or whether they were never
expected to persist daily snapshots at all (e.g. if their P&L is derived differently, via
`get_strategy_realized_pnl()` reading `paper_trades` directly, per `_send_close_notification`'s
pattern in `CONTEXT.md`).

**Task:**
1. `search_code("record_leg_snapshot")` and `search_code("paper_leg_snapshots")` to find every
   script that touches this table or the strategies in question.
2. For each of `paper_csp_nifty_v1` and the overlay strategies (CC/PP/Collar, all currently only
   live on NiftyBees per the 3-Track Consolidation epic in `TODOS.md`): determine whether an EOD
   cron exists, and whether it has the same gap.
3. Output: short table (strategy → cron script → has gap? → recommendation) appended to this file
   under `### SNAP-3 findings`. **Do not fix anything found here** — this is scoping only, so a
   follow-up story can be sized correctly instead of silently expanding SNAP-2's blast radius.

**Files touched:** none (read-only). Append findings via `Edit`.

**Why Claude, not Antigravity:** Read-only audit, same reasoning as SNAP-1 and as YE-1's
precedent in `docs/plan/ic-yearly-expiry-fix/stories.md` (audit blast radius before any fix
lands).

---

## SNAP-4 — Reporting script: daily graph data + inception/monthly P&L summary

**Prerequisite:** SNAP-2 landed and has accumulated at least a few days of real snapshot rows
(the query can be written and tested against synthetic/fixture data before that, but should not
be treated as verified against production shape until real rows exist).

**Fix:** New script `scripts/reporting/paper_pnl_report.py` (or similar — confirm naming
convention against the `reporting`-equivalent scripts already under `scripts/portfolio/` first).
Given `--strategy <name>`:
1. **Daily P&L graph data**: `SELECT snapshot_date, SUM(total_pnl) AS daily_total FROM
   paper_leg_snapshots WHERE strategy_name=? GROUP BY snapshot_date ORDER BY snapshot_date` —
   exact aggregation depends on SNAP-1's cumulative-vs-delta finding; if cumulative, this is
   already the graph series as-is (no further delta computation needed); if delta, needs a
   running `SUM() OVER (ORDER BY snapshot_date)` window.
2. **Realized P&L since inception**: per SNAP-1's finding — either the latest snapshot's
   `realized_pnl` (if cumulative) or `SUM(realized_pnl)` (if delta). Do not guess; use SNAP-1's
   documented answer.
3. **Realized P&L this calendar month**: same field, but scoped — either
   `latest_this_month - value_as_of(last snapshot strictly before month start)` (cumulative case)
   or `SUM(realized_pnl) WHERE snapshot_date >= date_trunc('month', today)` (delta case). Handle
   the case where the strategy opened mid-month (no prior-month baseline row exists) — falls back
   to the latest value directly, same as IC V2's actual 2026-07-03 open this month.
4. **Unrealized P&L since inception**: latest snapshot's `unrealized_pnl`, summed across
   `leg_role` for multi-leg strategies (IC has 4 legs; CSP/overlays have 1–2).
5. Output: structured print/JSON (project convention — check whether existing EOD scripts print
   plain text or JSON before choosing) plus a data method importable for a future graphing layer
   (out of scope to build the actual chart in this story — just the data).

**Tests required:**
- Happy path: multi-day snapshot fixture (3+ dates, 1 strategy, multiple legs) → correct daily
  series, correct inception/monthly aggregates.
- Edge case: strategy with zero snapshot rows (matches every IC variant's current state until
  SNAP-2 has run for a few days) → clear "no data yet" result, not a crash or a silently empty
  chart.

**Files touched:** new `scripts/reporting/paper_pnl_report.py`, new
`tests/unit/reporting/test_paper_pnl_report.py`.

**Why Claude, not Antigravity:** Query correctness depends directly on SNAP-1's semantics finding
and needs to be validated against real accumulated data from SNAP-2, not written to a fixed
upfront spec — exploratory/dependent work, not mechanical. Once the semantics are nailed down and
the first version is working, a follow-up "add more strategies to the report" pass would be a
reasonable Antigravity candidate (mechanical, 1-file, no new judgment calls) — but not this first
pass.

---

## Sequencing

SNAP-1 → SNAP-2 → SNAP-3 (can run in parallel with SNAP-2 — independent audit) → SNAP-4.
SNAP-4 hard-depends on SNAP-1's finding and SNAP-2 having landed; don't start it before both are
done. SNAP-3's findings may spawn a follow-up story (SNAP-5+) — not pre-created here, per YE-1's
precedent of not scoping unstarted work speculatively.

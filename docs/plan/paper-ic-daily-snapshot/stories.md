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

### SNAP-1 findings (2026-08-07)

**Semantics: `realized_pnl`/`unrealized_pnl`/`total_pnl` are cumulative-as-of-date, not daily
deltas** — confirmed at the source in `PaperTracker.compute_pnl()` (`src/paper/tracker.py:133`),
which calls `_compute_realized_pnl(store, strategy_name)` (`tracker.py:94`) — that function pulls
`store.get_trades(strategy_name)` (the full trade ledger for the strategy) and sums realized P&L
across **all** closed legs to date, every time it runs; `unrealized` is a fresh mark-to-market
over currently-open positions. Both `record_daily_snapshot()` (writes `paper_nav_snapshots`) and
the leg-level equivalent used by `paper_3track_snapshot.py` (writes `paper_leg_snapshots`) call
`compute_pnl()`/its per-leg sibling the same way — no delta or running-sum logic exists anywhere
in the write path.

Verified against the live data (`paper_nifty_futures`, `paper_nav_snapshots`, strategy-level):
`realized_pnl` sits flat at a constant value for many consecutive days, then steps to a new
constant on the exact day a leg closes (`2026-05-27→28`: `0 → -5003.84`; `2026-06-08→09`:
`-5003.84 → 15903.41`; `2026-07-20→21`: `15903.41 → -41195.48`) — it does not reset between those
step days. `unrealized_pnl` fluctuates freely day to day (mark-to-market), consistent with
cumulative-as-of-date, not a delta.

Query used (Rule 1-compliant — named columns, no `SELECT *`):
```sql
SELECT snapshot_date, realized_pnl, unrealized_pnl, total_pnl
FROM paper_nav_snapshots
WHERE strategy_name = ?
ORDER BY snapshot_date;
```

**Caveat for SNAP-4 — "since inception" is not always a single monotonic run.** On `2026-08-05`,
`paper_nifty_futures`' `realized_pnl` in `paper_nav_snapshots` drops back to `0` after sitting at
`-41195.48` the prior session (same reset visible independently in `paper_leg_snapshots` for
`base_futures`, `-28172.08 → 0`) — a full-cycle close/reopen, not a bug in the field. **"Realized
P&L since inception" cannot be read as "the latest row's `realized_pnl`" if a strategy has been
through more than one full open→close cycle** — that would silently drop every prior cycle's
realized P&L. SNAP-4 must either (a) detect cycle boundaries (a same-day drop in `realized_pnl`
after previously nonzero) and sum across cycles, or (b) sum realized P&L directly from closed
`paper_trades` rows rather than trusting the latest snapshot. Recommend (b) for correctness —
`paper_trades` is the append-only source of truth per `DB_REGISTRY.md`; the snapshot tables are
derived and reset per the strategy's live position lifecycle, not a running total across
strategy lifetime. **This did not come up in the IC V2 sample quoted in the SNAP-2 finding above
because that cycle hasn't reset yet — do not assume IC is exempt.**

**Invariant `total_pnl == unrealized_pnl + realized_pnl` — holds in `paper_leg_snapshots`, does
NOT hold universally in `paper_nav_snapshots`.** Checked with `Decimal` arithmetic (not float) to
avoid rounding false-positives:

- `paper_leg_snapshots`: 647/647 rows satisfy the invariant exactly — consistent with
  `CONTEXT.md`'s statement that `record_leg_snapshot()` enforces it at write time.
- `paper_nav_snapshots`: **42 of 267 rows fail** (e.g. `paper_nifty_spot`/`paper_nifty_proxy`,
  `2026-06-17` and `2026-06-19`: `realized_pnl=20907.25`, `unrealized_pnl=-10409.50`,
  `total_pnl=-2825.95` — arithmetic gives `10497.75`, not `-2825.95`). `record_nav_snapshot()` /
  `record_daily_snapshot()` do not enforce this invariant at write time the way
  `record_leg_snapshot()` does. Root cause not investigated further here (out of scope — SNAP-1
  is semantics-confirmation, not a bug fix); flagging as a candidate follow-up story. **SNAP-4
  must not assume `total_pnl` in `paper_nav_snapshots` is trustworthy — recompute
  `unrealized_pnl + realized_pnl` at query time rather than reading the stored `total_pnl`
  column**, or investigate/fix the write path first.

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

### SNAP-2 finding (2026-08-07) — **closed, not implemented**

During a Cowork session investigating IC V2 daily P&L, `paper_nav_snapshots` was found to already
contain strategy-level `realized_pnl`/`unrealized_pnl`/`total_pnl` for all five IC variants
(V1 weekly/monthly/leaps/yearly, V2 monthly), 2026-07-21 through present, written daily by
`scripts/portfolio/paper_snapshot.py` (`36 15 * * 1-5`, calling `PaperTracker.record_nav_snapshot()`)
— a completely separate code path from `paper_ic_snapshot.py` (the Telegram-report script this
story originally targeted). Sample (`paper_ic_nifty_v2_monthly`):

```
2026-07-21  realized=0            unrealized=5422.63    total=5422.63
2026-07-24  realized=-3056.63     unrealized=0           total=-3056.63
2026-08-05  realized=-1756.08     unrealized=-157.63      total=-1913.71
```

The story's premise ("`paper_leg_snapshots` has zero rows for every IC variant" — still true)
was read as "IC has no persisted daily P&L at all" — false. `paper_leg_snapshots` is per-leg;
`paper_nav_snapshots` is per-strategy, and per-strategy is all four of this story's stated end
goals (daily graph, realized-since-inception, realized-this-month, unrealized-since-inception)
actually need. Per-leg attribution (which wing/short leg drove the P&L) was never a stated
requirement — it would be new scope, not a gap-fill.

**Decision:** close SNAP-2 without implementing. Do not wire `record_leg_snapshot()` into
`paper_ic_snapshot.py` unless a future requirement specifically needs per-leg breakdown for IC
(e.g. a per-leg Greeks dashboard). If that need arises, re-open as a new story rather than
un-closing this one — the original rationale (mirror `paper_3track_snapshot.py`'s call shape) still
applies then. See `DB_REGISTRY.md` for the full per-table writer/cadence breakdown that surfaced
this — check it before assuming any `paper_*` table is empty for a strategy.

**Downstream effect on SNAP-4:** no longer blocked by SNAP-2. Still blocked by SNAP-1 (need the
cumulative-vs-delta confirmation before writing aggregation queries), but SNAP-4's query source
should target `paper_nav_snapshots`, not `paper_leg_snapshots` — that table already has live rows
for every IC variant today, so SNAP-4 can be built and validated against production data
immediately once SNAP-1 lands, without waiting on any new writer code.

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

## SNAP-5 — Fix `total_pnl` write-time invariant gap in `paper_nav_snapshots`

**Problem:** SNAP-1's audit found `record_nav_snapshot()`/`record_daily_snapshot()`
(`src/paper/tracker.py`) do not enforce `total_pnl == unrealized_pnl + realized_pnl` at write
time, unlike `PaperStore.record_leg_snapshot()` (which enforces it and has zero violations across
647 `paper_leg_snapshots` rows). Live data check: 42 of 267 `paper_nav_snapshots` rows currently
have a `total_pnl` that does not equal `unrealized_pnl + realized_pnl` (exact `Decimal`
arithmetic, not a rounding artifact — see SNAP-1 findings for a reproducible example,
`paper_nifty_spot`/`paper_nifty_proxy` on `2026-06-17` and `2026-06-19`). Root cause not yet
diagnosed — SNAP-1 was semantics-confirmation only, this story is the actual investigation + fix.

**Open decision — requires Animesh, not a Claude call:** what to do with the 42 already-bad
historical rows.
- **Option A — backfill in place:** recompute and overwrite `total_pnl` for the 42 rows from
  their existing `unrealized_pnl`/`realized_pnl` values. Simple, but silently rewrites history
  that may already have been read/reported on (e.g. in a prior Telegram message or manual check).
- **Option B — leave history as-is, enforce going forward only:** add the write-time invariant
  check (mirroring `record_leg_snapshot()`'s pattern) so no *new* bad row can land, but leave the
  42 existing rows untouched (optionally flagged, e.g. a comment/log noting they predate the fix).
  Consistent with this project's stated "backfill is explicitly out of scope" posture elsewhere in
  this same story file (SNAP-2/SNAP-4), but that precedent was about *reconstructing missing*
  data, not *correcting wrong* data already present — not a clean 1:1 analogy, worth confirming
  explicitly rather than assuming.

Recommendation (not yet a decision): Option B, for consistency with this epic's existing
backfill-out-of-scope stance and because SNAP-4 (per SNAP-1's finding) already recomputes
`total_pnl` at query time rather than trusting the stored column — so the 42 bad rows are already
neutralized for reporting purposes even before this fix lands. But this is Animesh's call, not
assumed here.

**Task (once the backfill decision is made):**
1. Diagnose why the two values diverge for the 42 rows — check whether `record_nav_snapshot()`
   does something between compute and persist (e.g. rounding, a separate update path, a race with
   `paper_3track_snapshot.py`'s own writes to strategies that also appear in the 3-track set) via
   `search_code("record_nav_snapshot")` / `get_code_snippet` — do not assume the cause from
   SNAP-1's data alone.
2. Add the same write-time invariant enforcement `record_leg_snapshot()` already has.
3. Apply the backfill decision (A or B) to the 42 existing rows.

**Tests required:** happy path (matching values write cleanly) + edge case (mismatched values are
rejected/logged per the enforcement mechanism chosen, mirroring `record_leg_snapshot()`'s existing
regression test pattern in `test_store.py`).

**Financial-logic gate:** persists real P&L; per `CLAUDE.md`'s AutoTrigger table, the real
`@code-reviewer` gate (or its documented Cowork substitution) is mandatory before committing.

**Files touched:** `src/paper/tracker.py` (and/or `src/paper/store.py` if enforcement moves to the
store layer to mirror `record_leg_snapshot()`'s location exactly — confirm via graph before
choosing), `tests/unit/paper/test_tracker.py` (or `test_store.py`).

**Why Claude, not Antigravity:** Root cause is undiagnosed — exploratory investigation with a
judgment call on where enforcement belongs, not a fixed mechanical spec. Also financial logic,
routed through the real code-reviewer gate.

---

## Sequencing

SNAP-1 → SNAP-2 → SNAP-3 (can run in parallel with SNAP-2 — independent audit) → SNAP-4 → SNAP-5.
SNAP-4 hard-depends on SNAP-1's finding and SNAP-2 having landed; don't start it before both are
done. SNAP-5 is independent of SNAP-4's implementation but should land after SNAP-4 so the
reporting script's query-time workaround is proven in place regardless of when the write-path fix
ships; SNAP-5 also has an open Animesh decision gate (backfill approach) that must resolve before
implementation starts. SNAP-3's findings may spawn additional follow-up stories (SNAP-6+) — not
pre-created here, per YE-1's precedent of not scoping unstarted work speculatively.

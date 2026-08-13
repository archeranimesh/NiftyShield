# docs/bugs/ — Task Checklist

> Find the first unchecked `- [ ]` line **that belongs to a `BUG-ID` checklist** (see
> `docs/bugs/prompt.md` for the full session-start protocol). Tick the box and append
> `| SHA <commit_sha>` when done. Add one line to `TODOS.md` session log. Full bug detail for
> each item — symptom, root cause, suggested fix — lives in `docs/bugs/bugs.md`, never here.
>
> **Format contract:** every line in this file is `- [ ]`/`- [x]` **`**Bnnn.x**` — one short
> task sentence.` — optionally followed by `| SHA <sha>` once committed. Do not append
> implementation narrative, test lists, or review findings inline here — that detail belongs in
> the matching `docs/bugs/bugs.md` entry (add an "Implementation progress" note there instead).
> This file is a checklist, not a log.
>
> **Once every `Bnnn.x` line under a `BUG-ID` is checked** and the bug's `bugs.md` Status is
> ✅ Fixed: move the whole section to `docs/archive/bugs/task.md` (and the matching `bugs.md`
> entry to `docs/archive/bugs/bugs.md`) in the closing commit. Do not leave fully-checked
> sections in this file — an unchecked line here should always mean real open work.

---

## BUG-019 — Investigation: does every strategy show a live-tick vs. EOD-snapshot P&L disparity?

- [ ] **B019.1** — Diagnostics committed (SHA `f7177b6`); still awaiting a live trading day's
  `strategy_monitor.live_pnl_diag` vs. `paper_snapshot.log` diff before a fix can be scoped. Full
  context: `docs/bugs/bugs.md` BUG-019.

## BUG-025 — MC-3b review follow-ups: `roll_ic_legs` open-only write shape, `PROFIT_LOCK_ZONE2` state/write ordering

- [ ] **B025.1** — Deliberately deferred, not blocking (Animesh) — no checklist yet. Scope it
  before starting: `docs/bugs/bugs.md` BUG-025.

## BUG-027 — `scripts/healthcheck.py` never calls `load_dotenv()`

- [x] **B027.1** — `load_dotenv()` added to `scripts/healthcheck.py`, mirrors `eod_summary.py`'s
  placement. | No SHA yet — pending commit
- [x] **B027.2** — Tests: `tests/unit/test_healthcheck.py`, 4 new (8/8 total pass). |
  Verified via targeted pytest run — 44/44 pass across healthcheck/notifications/config
- [x] **B027.3** — Self-review against `REVIEW.md` (no CRITICAL/ERROR); real agent pass still
  recommended before commit. | Self-review only so far
- [ ] **B027.4** — Commit, update `bugs.md` BUG-027 status to ✅ Fixed + SHA, add a `TODOS.md`
  session log line.

## BUG-029 — `paper_exit_events.counterfactual_dte_marks` migration committed but never run; 3-track EOD snapshot cron has crashed every market day since 2026-08-05

- [x] **B029.1** — Root cause confirmed (schema diff + log tracebacks + `git log -S`). | No code
  change — investigation only
- [x] **B029.2** — Tests for the pre-existing migration script (4 cases, none existed before). |
  SHA `c8d5baa`
- [x] **B029.3** — Review: `general-purpose` + `REVIEW.md` substitute, no CRITICAL/ERROR/WARNING.
  | Review-only, no SHA
- [ ] **B029.4** — Run the migration against the live DB (back up first), confirm the next 15:35
  cron completes clean, then backfill the missed day's overlay-pnl/leg-snapshot/protection-recovery
  rows via `paper_3track_snapshot --no-dry-run`. **Migration itself confirmed run 2026-08-10** —
  still outstanding: confirm a subsequent cron ran clean, and the backfill re-run. Full detail:
  `docs/bugs/bugs.md` BUG-029.
- [x] **B029.5** — Healthcheck coverage for "did the 3-track snapshot cron crash" (non-blocking
  follow-up). | SHA `bee2649`
- [ ] **B029.6** — Commit, update `bugs.md` BUG-029 status to ✅ Fixed + SHA once B029.4 confirms
  clean, update `TODOS.md`.

## BUG-030 — `_overlay_type_groups()` elif-precedence drops an `overlay_cc` leg

- [ ] **B030.1** — Decide the entry-side question first (blocks B030.2): should the call leg have
  been tagged `overlay_collar_call` at entry instead of `overlay_cc`? Investigate
  `paper_3track_overlay_entry.py`'s collar/CC entry path. Likely needs a council checkpoint —
  see `docs/bugs/bugs.md` BUG-030.
- [ ] **B030.2** — Fix `_overlay_type_groups()` (`paper_3track_snapshot.py:1081-1117`) per B030.1's
  resolved semantics — add the missing `has_cc and has_put` branch. Must not regress the existing
  `has_put`-without-`has_call`-or-`has_cc` warning path.
- [ ] **B030.3** — Tests: regression test for `_overlay_type_groups({"overlay_cc",
  "overlay_collar_put"})`, edge cases for the other 3 combinations, end-to-end test on
  `_compute_overlay_pnl_snapshots`.
- [ ] **B030.4** — Backfill or document a discontinuity for the 2026-08-12/08-13
  `paper_overlay_pnl_snapshots` rows written with the missing leg's P&L.
- [ ] **B030.5** — Review: real `code-reviewer` or `general-purpose` + `REVIEW.md` substitute
  (mandatory — financial P&L reporting change).
- [ ] **B030.6** — Commit, update `bugs.md` BUG-030 status to ✅ Fixed + SHA, update `TODOS.md`.

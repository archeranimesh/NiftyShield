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

> BUG-033 closed 2026-08-24 (SHA `ef1c341`) — section moved to `docs/archive/bugs/{bugs,task}.md`.
> BUG-034 closed 2026-08-24 (SHA `88df26e`) — section moved to `docs/archive/bugs/{bugs,task}.md`.
> BUG-032 closed 2026-08-24 (SHA `67d4010`, backfill applied same day) — section moved to `docs/archive/bugs/{bugs,task}.md`.

## BUG-036 — `prev_mark_value` blends today's live quantity with yesterday's LTP in `pnl_1d_pct`'s denominator

- [x] **B036.1** — Decide the fix approach: add a `net_qty` field to
  `PaperLegSnapshot`/`paper_leg_snapshots` (schema addition, not a re-key —
  orthogonal to the BUG-032 council ruling's rejection of instrument-keying)
  so `prev_mark_value` can use historical quantity, or accept and more
  prominently document the imprecision as a percentage-only display
  limitation. See `docs/bugs/bugs.md` BUG-036. — decided: add `net_qty`.
- [x] **B036.2** — Fix `_compute_overlay_pnl_snapshots`'s `prev_mark_value`
  computation per B036.1's resolved approach.
- [x] **B036.3** — Tests: a day-over-day quantity change (partial close/add)
  with a real (non-`NULL`) `prev.ltp` — no existing test constructs this
  case, per the BUG-032 code review that surfaced this gap. Confirmed
  passing locally by Animesh (full suite: 157 passed, after fixing a sign
  error in the new backfill test's own expected `net_qty` — the test, not
  the implementation, had the bug: `SELL 50 to open` is `net_qty=-50`, not
  `+50`).
- [x] **B036.4** — Backfill `net_qty` for the 229 existing `paper_leg_snapshots`
  rows (2026-05-11 → present) by reconstructing historical net quantity from
  `paper_trades` (signed `quantity` by `action`, `trade_date <= snapshot_date`,
  grouped by `strategy_name`/`leg_role`) — via a proper query/store method, not
  a raw `UPDATE`. Without this, `prev.net_qty` is `NULL` for every lookback
  across existing history until new snapshots accumulate post-fix. | Run
  against the live DB by Animesh 2026-08-24 (after fixing a script bug — see
  bugs.md — where the raw sqlite connection queried `net_qty` before
  `PaperStore`'s migration had ever run in-process). Confirmed via direct
  query: 229/229 rows populated, 0 remaining NULL.
- [x] **B036.5** — Review: real `code-reviewer` or `general-purpose` +
  `REVIEW.md` substitute (mandatory — live overlay P&L reporting change). —
  general-purpose+REVIEW.md substitute run; no CRITICAL/ERROR findings.
- [ ] **B036.6** — Commit, update `bugs.md` BUG-036 status to ✅ Fixed + SHA,
  update `TODOS.md`. | SHA pending — sandbox .git/index.lock held by a
  concurrent process, commit deferred to live host.

## BUG-035 — `_record_close_trade()` never calls `mark_trade_closed()`; closed overlay legs stay `state='OPEN'` forever

- [ ] **B035.1** — Trace whether anything downstream (signal evaluation, position
  listing, BUG-031's monitor path) filters `paper_trades`/positions by
  `state='OPEN'` — confirms or rules out overlap with BUG-031 before fixing.
  See `docs/bugs/bugs.md` BUG-035.
- [ ] **B035.2** — Check `CollarOverlayV1`'s close path for the same missing
  `mark_trade_closed()` call (only CC/PP confirmed so far).
- [ ] **B035.3** — Add `self._store.mark_trade_closed(...)` after `record_trade()`
  in `CCOverlayV1._record_close_trade()`, `PPOverlayV1._record_close_trade()`,
  and Collar's equivalent (per B035.2).
- [ ] **B035.4** — Tests: assert `_record_close_trade()` transitions the opening
  row to `state='CLOSED'` end-to-end for each overlay strategy — no existing
  test covers `record_trade()` + `mark_trade_closed()` wired together.
- [ ] **B035.5** — Backfill the two stale live rows (`paper_trades` ids 213, 214,
  `overlay_pp`, `NSE_FO|61604`/`NSE_FO|74009`) via `mark_trade_closed()` — not
  raw SQL — once B035.3 lands.
- [ ] **B035.6** — Review: real `code-reviewer` or `general-purpose` +
  `REVIEW.md` substitute (mandatory — touches live paper-trading state
  transitions).
- [ ] **B035.7** — Commit, update `bugs.md` BUG-035 status to ✅ Fixed + SHA,
  update `TODOS.md`.

## BUG-019 — Investigation: does every strategy show a live-tick vs. EOD-snapshot P&L disparity?

> Moved to the bottom of this file deliberately (2026-08-24, Animesh) — the 08-14/17/19/20/21
> diff (see `bugs.md` BUG-019) found no systematic staleness bug, just ordinary intraday
> movement, so this is low-priority relative to BUG-030/031. Diagnostics are being left running
> longer rather than removed now. Keep this section last so the session-start protocol picks up
> BUG-030/031 first.

- [ ] **B019.1** — Diagnostics committed (SHA `f7177b6`) and now diffed against 5 live trading
  days (08-14, 08-17, 08-19, 08-20, 08-21) — no systematic bias found, gaps flip sign and scale
  with intraday movement (one exact 0.00 diff on a low-movement day confirms the mechanism
  itself is sound). Leaving diagnostics running per Animesh's call (2026-08-24) rather than
  closing/removing yet. Full context: `docs/bugs/bugs.md` BUG-019.

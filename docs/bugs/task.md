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

## BUG-032 — `get_position()`'s ambiguous-match fallback silently drops one leg's
P&L whenever an overlay role has two open positions

- [ ] **B032.1** — Decide the fix approach (blocks B032.2): sum across all open
  positions per `leg_role` (option a — needs a `paper_leg_snapshots` shape
  decision), or hard-fail/`GateViolation` on >1 open position per role until
  resolved (option b)? See `docs/bugs/bugs.md` BUG-032. Likely needs a council
  checkpoint per `docs/council/README.md`'s three-condition check, same bar
  BUG-028/BUG-030/BUG-031 used.
- [ ] **B032.2** — Fix `_compute_overlay_leg_totals()`, `_leg_entry_basis()`, and
  `_position_qty()` (`paper_3track_snapshot.py`) per B032.1's resolved approach.
  Must not regress the single-open-position (common) case.
- [ ] **B032.3** — Tests: simulate two open positions under one `leg_role` and
  assert the resulting P&L reflects both legs (option a) or refuses to silently
  proceed (option b) — no existing test exercises `get_position`'s
  ambiguous-match branch from the overlay P&L path.
- [ ] **B032.4** — Backfill or document the discontinuity in `overlay_pp`'s daily
  snapshots from 2026-08-20 onward (the older `NSE_FO|61604` leg's P&L has been
  silently excluded every day since) — same shape as BUG-030's B030.4, likely
  the same mechanism (rerun the fixed compute function per affected date).
- [ ] **B032.5** — Review: real `code-reviewer` or `general-purpose` +
  `REVIEW.md` substitute (mandatory — live overlay P&L reporting change).
- [ ] **B032.6** — Commit, update `bugs.md` BUG-032 status to ✅ Fixed + SHA,
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

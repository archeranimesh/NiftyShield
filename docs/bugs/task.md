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
> BUG-036 closed 2026-08-24 (SHA `d40c3a1`, backfill applied same day) — section moved to `docs/archive/bugs/{bugs,task}.md`.
> BUG-035 closed 2026-08-24 (SHA `0ecd86b`) — section moved to `docs/archive/bugs/{bugs,task}.md`.

## BUG-037 — `mark_trade_closed()` also never wired into CSP/IC v1/v2 close paths (54 stale flat legs)

- [x] **B037.1** — Trace `close_csp_leg`/`close_ic_legs`/`roll_ic_legs` (and
  `roll_down_and_out`) call sites for any partial-close/roll scenario that can
  leave `net_qty != 0` on the leg being written — CSP's `ROLL_DOWN_AND_OUT`
  and IC's spread-only closes are partial at the strategy level, unlike
  BUG-035's overlay legs. Confirms whether `mark_trade_closed()` can be called
  unconditionally per closing trade or needs a flatness check first. See
  `docs/bugs/bugs.md` BUG-037. | SHA `b399a3e`
- [x] **B037.2** — Trace `scripts/strategies/three_track/paper_3track_roll.py`'s
  futures/proxy roll-close write path for the same gap — the `base_futures`
  and `base_ditm_call` stale rows found may or may not share this root cause;
  not yet confirmed (unlike CSP/IC, which are confirmed via grep). | SHA `b399a3e`
- [ ] **B037.3** — Add `store.mark_trade_closed(...)` (or the appropriate
  partial-close-safe equivalent per B037.1) to `close_csp_leg`,
  `close_ic_legs`, `roll_ic_legs`, and the futures/proxy roll-close path
  (per B037.2, if confirmed in scope).
- [ ] **B037.4** — Tests: regression coverage per call site mirroring
  BUG-035's B035.4 pattern (mark_trade_closed called on full close, not
  called on partial close/duplicate insert).
- [ ] **B037.5** — Re-run `scripts/dev/backfill_mark_trade_closed_overlay.py`
  (already generalized, built for BUG-035) against the live DB once B037.3
  lands — it already covers all 54 rows found in this bug's discovery scan.
- [ ] **B037.6** — Review: real `code-reviewer` or `general-purpose` +
  `REVIEW.md` substitute (mandatory — touches live paper-trading state
  transitions across CSP/IC, the two highest-volume strategy families).
- [ ] **B037.7** — Commit, update `bugs.md` BUG-037 status to ✅ Fixed + SHA,
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

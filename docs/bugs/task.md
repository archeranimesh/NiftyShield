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

- [x] **B032.1** — Decided by council 2026-08-24 (unanimous): hybrid — aggregate
  per-instrument across all open positions per role, alert loudly on the
  invariant break, no hard-fail, no `paper_leg_snapshots` schema re-key. See
  `docs/bugs/bugs.md` BUG-032 and `DECISIONS.md`.
- [x] **B032.2** — Fixed `_compute_overlay_leg_totals()`, `_leg_entry_basis()`, and
  `_position_qty()` (`paper_3track_snapshot.py`) per the council's ruling: sum
  per-instrument P&L (never blended cost/LTP), `ltp=NULL` when `n>1`, added the
  deduplicated `overlay_pnl.multi_instrument_role` alert. Single-open-position
  case unchanged.
- [x] **B032.3** — Tests: implemented the council ruling's 13-item regression
  checklist plus a 14th from the B032.5 code review — all pass locally
  (Animesh, 2026-08-24). See `docs/bugs/bugs.md` BUG-032 for the full list.
- [ ] **B032.4** — Backfill or document the discontinuity in `overlay_pp`'s daily
  snapshots from 2026-08-20 onward (the older `NSE_FO|61604` leg's P&L has been
  silently excluded every day since) — same shape as BUG-030's B030.4, likely
  the same mechanism (rerun the fixed compute function per affected date).
- [x] **B032.5** — Review: general-purpose agent + `REVIEW.md` substitute
  (real `code-reviewer` unavailable this session) against the diff. Found and
  fixed a real regression (alert logging incorrectly gated on `notifier`,
  would go silent with no Telegram configured) and one pre-existing gap
  (logged separately as BUG-036, not fixed inline). No REVIEW.md violations.
- [x] **B032.6** — Committed SHA `67d4010`. `bugs.md` BUG-032 status ->
  ✅ Fixed, `TODOS.md` session log added.

## BUG-036 — `prev_mark_value` blends today's live quantity with yesterday's LTP in `pnl_1d_pct`'s denominator

- [ ] **B036.1** — Decide the fix approach: add a `net_qty` field to
  `PaperLegSnapshot`/`paper_leg_snapshots` (schema addition, not a re-key —
  orthogonal to the BUG-032 council ruling's rejection of instrument-keying)
  so `prev_mark_value` can use historical quantity, or accept and more
  prominently document the imprecision as a percentage-only display
  limitation. See `docs/bugs/bugs.md` BUG-036.
- [ ] **B036.2** — Fix `_compute_overlay_pnl_snapshots`'s `prev_mark_value`
  computation per B036.1's resolved approach.
- [ ] **B036.3** — Tests: a day-over-day quantity change (partial close/add)
  with a real (non-`NULL`) `prev.ltp` — no existing test constructs this
  case, per the BUG-032 code review that surfaced this gap.
- [ ] **B036.4** — Review: real `code-reviewer` or `general-purpose` +
  `REVIEW.md` substitute (mandatory — live overlay P&L reporting change).
- [ ] **B036.5** — Commit, update `bugs.md` BUG-036 status to ✅ Fixed + SHA,
  update `TODOS.md`.

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

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

## BUG-033 — `_parse_expiry` regex-only in `CCOverlayV1`/`PPOverlayV1`/`CollarOverlayV1` — DTE-gated exit signals (`ROLL_ELIGIBLE`/`DTE_REVIEW`) dead for every real numeric instrument key

- [ ] **B033.1** — Repoint each of the three files' `_parse_expiry` to try the existing regex
  first, then fall back to `self._resolve_instrument_lookup().get_by_key(instrument_key)`'s
  `expiry` field (epoch ms → `date`) when the regex misses — mirrors the fix already proven for
  `_open_pp_dte`/`paper_3track_overlay_entry.py` (`TODOS.md` 2026-08-13/2026-08-20) and
  `ic_nifty_v2.py::_parse_expiry`. Decide inline vs. a shared helper in
  `src/strategy/_price_utils.py` before implementing (three near-duplicate copies exist today —
  don't let the refactor question block the behavior fix). Full context: `docs/bugs/bugs.md`
  BUG-033.
- [ ] **B033.2** — Tests: regression coverage using real numeric instrument keys (not the
  text-format fixtures the existing suites use) asserting a resolvable near-expiry DTE actually
  fires `ROLL_ELIGIBLE`/`DTE_REVIEW` — one per class (CC/PP/Collar). Also assert the regex path
  still wins when both would resolve (no behavior change for text-format keys).
- [ ] **B033.3** — Review: real `code-reviewer` or `general-purpose` + `REVIEW.md` substitute
  (mandatory — same live-capital-adjacent auto-execution bar as B031.5).
- [ ] **B033.4** — Manual action, independent of the code fix and time-sensitive: `overlay_pp`
  leg `NSE_FO|61604` expires 2026-08-25 — decide whether to roll/close it by hand before expiry
  rather than wait for this fix to land.
- [ ] **B033.5** — Commit, update `bugs.md` BUG-033 status to ✅ Fixed + SHA, update `TODOS.md`.
  Re-run `scratch/2026-08-24_bug031_manual_exit_review.py` afterward to close out BUG-031's
  B031.4 with real DTE coverage. **Blocked on BUG-034 landing first** — the leg_role filter
  BUG-034 describes runs before this bug's DTE logic for PP/CC, so this fix can't be verified
  end-to-end until BUG-034 ships too.

## BUG-034 — `LONG_PUT_ROLES`/`SHORT_CALL_ROLES` stale in `pp_overlay_v1.py`/`cc_overlay_v1.py` — `check_signals()` evaluates zero real PP/CC positions, upstream of and more severe than BUG-033

- [ ] **B034.1** — Repoint `LONG_PUT_ROLES` (`src/strategy/pp_overlay_v1.py:54`) to `{"overlay_pp"}`
  and `SHORT_CALL_ROLES` (`src/strategy/cc_overlay_v1.py:54`) to `{"overlay_cc"}` — PP-only and
  CC-only sets respectively, not reusing `exit_signals._OVERLAY_LONG_PUT_ROLES`/
  `_OVERLAY_SHORT_CALL_ROLES` directly (those deliberately include the Collar variants too).
  Full context: `docs/bugs/bugs.md` BUG-034.
- [ ] **B034.2** — Tests: regression coverage using the real `"overlay_pp"`/`"overlay_cc"`
  leg_role strings (not the existing fixtures' `"protective_put"`/`"short_call"` defaults, which
  is exactly how this shipped passing against nothing real) asserting `check_signals()` actually
  evaluates a position with the real leg_role and does NOT evaluate one with the stale role names
  this fix removes.
- [ ] **B034.3** — Review: real `code-reviewer` or `general-purpose` + `REVIEW.md` substitute
  (mandatory — same live-capital-adjacent auto-execution bar as B031.5/B033.3).
- [ ] **B034.4** — Commit, update `bugs.md` BUG-034 status to ✅ Fixed + SHA, update `TODOS.md`.
  Land before or together with BUG-033 (B033.5 is blocked on this).

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

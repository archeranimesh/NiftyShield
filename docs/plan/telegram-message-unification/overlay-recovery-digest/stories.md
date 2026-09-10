# Overlay recovery digest — story specs

> One task per session. Find the first unchecked item in `tasks.md`. That is your only task.
> Full implementation rules in `CLAUDE.md` and `REVIEW.md`.
> After each task: set `SHA:` on the task line + tick the box, flip this sub-story's row in
> the epic `README.md` **Stories** table, add one line to `TODOS.md`. See
> `docs/plan/README.md` §Conventions.

Sub-story 4 (last) of the `telegram-message-unification/` epic. No `schema.md`. All work is
in `scripts/strategies/three_track/paper_3track_snapshot.py` + its tests + `docs/bugs/`.

---

## ORD-1 — Investigate the CC-into-collar grouping defect

**Files to change / create:**
- `docs/bugs/bugs.md` — new `## BUG-044` entry
- (optional) `docs/plan/telegram-message-unification/overlay-recovery-digest/findings.md` —
  the investigation notes, no task checkboxes

**Before any code (read-only):**
- `get_code_snippet("_overlay_type_groups")` and its full docstring + the BUG-030 / BUG-028
  comments.
- `search_code("overlay_cc")` in `scripts/strategies/three_track/paper_3track_overlay_entry.py`
  — the `build_overlay_trades()` / `_record_collar_trades()` dedup guard that "skips
  inserting a second short-call leg when an overlay_cc already covers the same instrument
  key".
- `trace_path("_compute_overlay_pnl_snapshots")` and `trace_path("_build_recovery_digest")`.
- `git log --oneline -5 -- scripts/strategies/three_track/paper_3track_snapshot.py` around
  the BUG-030 fix — the `Why:` line explains the original intent.

**What to determine:**

1. Can a **standalone CC overlay** (`auto_cc_bootstrap`) and a **collar** be open at the same
   time under `paper_nifty_overlay`, each with its own economic purpose? The 2026-09-09
   `cc_entry.log` "Overlay Entry | CC | Cycle 1 | RECORDED TO DB" alongside an
   `overlay_collar_put` in the same snapshot says yes — confirm from the entry code, not just
   the log.
2. When they coexist, is there a **marker** that distinguishes "this `overlay_cc` leg is the
   collar's shared call" from "this `overlay_cc` leg is a standalone CC"? Candidates: a
   distinct `leg_role`, the collar entry's dedup path setting a flag, the cycle/instrument
   key, or the presence/absence of `overlay_collar_call`. If there is **no** reliable marker,
   ORD-1's decision is which heuristic to adopt (and its failure mode).
3. Decide the correct `_overlay_type_groups` behaviour for
   `{overlay_cc, overlay_collar_put}` (no `overlay_collar_call`):
   - **(a)** standalone CC + collar-put-only → emit both a `cc` group and a `collar` group
     (the put alone), CC P&L not in the collar; or
   - **(b)** keep the BUG-030 merge only when the marker says the CC *is* the collar call,
     else (a).

**BUG-044 entry** must state: the symptom (`CC No data` + inflated `Collar`), the verified
log evidence (dates, line refs), the root cause (`_overlay_type_groups` `has_cc and has_put`
branch), both effects, and the ORD-1 grouping decision. Status `🔴 Open — fix tracked under
telegram-message-unification/overlay-recovery-digest/ ORD-2`.

**Commit:** `docs(bugs): BUG-044 — standalone CC vanishes into Collar in the S9 digest`

---

## ORD-2 — Fix the overlay grouping

**Files to change:**
- `scripts/strategies/three_track/paper_3track_snapshot.py` — `_overlay_type_groups`,
  and wherever `_compute_overlay_pnl_snapshots` / `_overlay_summary_row` consume its output
- `tests/unit/…/test_paper_3track_snapshot*.py` (or the existing overlay-grouping test file)

**Before any code:**
- `get_code_snippet("_compute_overlay_pnl_snapshots")` and `get_code_snippet("_overlay_summary_row")`
  — both call `_overlay_type_groups`; both must stay consistent after the change.
- Re-read ORD-1's decision + BUG-044.

**What to implement (per ORD-1's decision):**

1. `_overlay_type_groups`: split the `has_cc and has_put` case so a standalone `overlay_cc`
   produces its own `groups["cc"] = ["overlay_cc"]` and the collar group is built from the
   real collar legs only. Preserve the genuine "collar call tagged `overlay_cc`" merge when
   ORD-1's marker indicates it (keep the BUG-030 behaviour for that case — do not regress
   BUG-030's own test).
2. Confirm `_compute_overlay_pnl_snapshots` then writes a `cc` `OverlayPnLSnapshot` row and a
   `collar` row whose `pnl_1d_abs` / `pnl_inception_abs` exclude the CC leg.
3. `_build_recovery_digest`: the `cc` value is now present → the `No data` line only appears
   for an overlay that truly has no leg today.
4. Verify the printed "Snapshots for <date>" comparison table (`_overlay_summary_row` path)
   and the digest report the same CC and Collar figures.

**Tests:**
- `test_group_standalone_cc_with_collar_put` — roles `{overlay_cc, overlay_collar_put}` →
  `{"cc": [...], "collar": ["overlay_collar_put"]}` (or per ORD-1); CC P&L not in the collar
  sum.
- `test_group_collar_call_tagged_cc_still_merges` — the BUG-030 scenario (marker says the
  `overlay_cc` is the collar call) still yields one `collar` group — regression guard.
- `test_recovery_digest_shows_cc_line` — with a CC leg snapshot present, `_build_recovery_digest`
  emits a `CC` line, no `overlay_source_missing` WARNING for cc.
- `test_digest_collar_excludes_standalone_cc` — the `Collar` figure equals the collar legs'
  P&L only.

**Commit:** `fix(3track): standalone CC gets its own recovery line, out of the Collar total`

---

## ORD-3 — Fenced-format the digest

**Files to change:**
- `scripts/strategies/three_track/paper_3track_snapshot.py` — `_build_recovery_digest` +
  its `notifier.send()` call site
- `tests/unit/…` — the digest golden strings

**Before any code:**
- `get_code_snippet("_build_recovery_digest")` as ORD-2 left it.
- `unified-exit-message/` `stories.md` UXM-7 — the `pre_market_brief.py` fenced-table
  conventions (```` ``` ```` block, column widths, no per-value escaping).
- `src/notifications/CLAUDE.md` + `FORMATTING.md` §3 — the fenced-block escaping contract.

**What to implement:**

1. Rebuild the digest body inside one ```` ``` ```` fenced block: the `📊 NiftyBees vs
   overlays — <date>` header line, `NiftyBees: <±1d>`, then the overlay rows (red day: sorted
   by recovery desc, `<label>  <±1d>  (<pct>%)`; flat/green day: sorted by raw 1d desc, no
   pct, no `Best:` line — keep the existing S9 rules), `No data` rows last, `Best: <label>`
   on a red day.
2. Drop every per-line `escape_markdown(...)` — the fence makes content literal. Assert no
   interpolated field can contain a backtick / backslash (dates, labels, numeric strings
   cannot).
3. At the `notifier.send()` call site, send the fenced string directly — no whole-string
   `escape_markdown`. This is the BUG-042 fix for this caller.
4. Keep column alignment stable with fixed widths locked by the golden tests.

**Tests:**
- `test_digest_red_day_fenced` — exact-string match: fenced, sorted, pcts, `Best:` line.
- `test_digest_flat_day_fenced` — exact-string match: fenced, raw-P&L sort, no pcts, no
  `Best:`.
- `test_digest_send_not_double_escaped` — the string handed to `notifier.send` opens/closes
  with ```` ``` ```` and contains no `\-` / `\.` sequences.

**Commit:** `refactor(3track): send the S9 recovery digest as a fenced MarkdownV2 block`

---

## ORD-4 — Epic close

**Files to change:** `CONTEXT.md`, `DECISIONS.md`, `src/notifications/CLAUDE.md`,
`docs/plan/telegram-message-unification/README.md`, `docs/plan/README.md`, `TODOS.md`,
`docs/archive/TODOS_ARCHIVE.md`, `docs/bugs/bugs.md`, plus the epic-folder `git mv`. Targeted
`Edit` only, never `Write`.

**What to implement:**

1. `CONTEXT.md` — note the S9 digest now reports a standalone CC correctly and renders
   fenced; add the dated state line.
2. `DECISIONS.md` §"P&L & Reporting" (or the 3-track section) — one dated row: the overlay
   grouping now separates a standalone CC from a collar (ORD-1's decision), and every
   paper-strategy Telegram message — entry, exit, and the S9 digest — is on the fenced
   MarkdownV2 house style.
3. `src/notifications/CLAUDE.md` — the S9 digest is fenced; list it among the migrated
   callers.
4. `docs/bugs/bugs.md` — BUG-044 → `✅ Fixed` with the ORD-2 SHA.
5. Epic close (ORD-4 is the last sub-story — archive the **whole epic**, per
   `docs/plan/README.md` §Conventions *Completion → archive*):
   - epic `README.md` — flip the `overlay-recovery-digest/` Stories row to ✅ and confirm
     **Epic done when** satisfied.
   - `git mv docs/plan/telegram-message-unification docs/archive/plan/telegram-message-unification`.
   - `docs/plan/README.md` — collapse the epic entry under `## Active Epics` to
     `✅ Archived → docs/archive/plan/telegram-message-unification/`.
   - `TODOS.md` — delete the Feature Backlog epic line, append it to
     `docs/archive/TODOS_ARCHIVE.md` under a dated heading; add a Session Log line.
   One commit.

**Commit:** `docs: close telegram-message-unification epic (UEM/OEM/UXM/ORD)`

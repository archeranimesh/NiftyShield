# Overlay entry message — tasks

Work top-down. Find the first unchecked `- [ ]` and do only that task. Each task = one commit unless noted. See `prompt.md` for why the story exists; see `stories.md` for the per-task implementation
spec.

Sub-story 2 of the `telegram-message-unification/` epic. Depends on `unified-entry-message/` (UEM-1..3) — `src/notifications/entry_message.py` must already exist. Do not start OEM-1 before every UEM
box is ticked (its epic `README.md` Stories-table row is ✅).

**Open: none — story done.**

- [x] **OEM-1** — Sign-aware net line in `entry_message.py::_credit_line`: negative
      `net_credit` → `💰 *Net debit:* …` (absolute value, label flipped); positive / zero
      byte-identical. Two new tests.
      | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: 2832717
- [x] **OEM-2** — `CollarOverlayV1._reenter_collar` sends a `✅ *Collar Entry*` card (2 legs,
      `[B]` put + `[S]` call) on a successful two-leg record, via `self._notifier`, non-fatal.
      | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer + greeks-analyst | SHA: 24946d7
- [x] **OEM-3** — **Merged into OEM-4.** Graph inspection (`CCOverlayV1.apply_action`,
      `PPOverlayV1.apply_action`, `ReEntryMixin._check_reentry`) confirmed neither class
      performs an in-tick automated re-entry the way `CollarOverlayV1._reenter_collar` does
      (OEM-2). `apply_action` only closes and calls `_check_reentry`, which writes an
      ELIGIBLE/BLOCKED `paper_exit_events` row and tells the operator to run a script
      manually — no position is reopened there. The only place a CC/PP re-entry is actually
      recorded is `auto_cc_bootstrap` / `auto_pp_bootstrap` in
      `paper_3track_overlay_entry.py`, which is OEM-4's target. OEM-4 now delivers the
      `✅ *CC Entry*` / `✅ *PP Entry*` cards (in addition to Collar's bootstrap card) as part
      of its bootstrap-message migration; no separate code change lands under OEM-3.
      | Owner: Claude | Model: claude-sonnet-5 | Review: none | SHA: —
- [x] **OEM-4** — Migrate the `📥 Overlay Entry — {TYPE} Bootstrap` message in
      `paper_3track_overlay_entry.py` to `format_entry_message`; the `⚠️ Gate Logged` line
      stays appended by the caller after the rendered card.
      | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: 3982c0e
- [x] **OEM-5** — Sub-story docs close: `CONTEXT.md` / `src/notifications/CLAUDE.md` / `DECISIONS.md` /
      the epic `README.md` Stories table / `TODOS.md` Session Log. No folder archive — the epic
      archives as a whole at UXM-8.
      | Owner: Claude | Model: claude-sonnet-5 | Review: none | SHA: 61ea904

## Story done when

- **OEM-1** — `format_entry_message` renders `💰 *Net debit:*` for a negative `net_credit` and is byte-identical to the pre-OEM-1 output for a positive / zero one; all unit tests green.
- **OEM-2** — a successful Collar re-entry sends one `✅ *Collar Entry*` card (`[B]` put + `[S]` call, `💰 *Net debit:*` line); a send failure is logged and never crashes the tick; two tests green;
  `greeks-analyst` clean.
- **OEM-3** — merged into OEM-4: a successful CC re-entry (via `auto_cc_bootstrap`) sends `✅ *CC Entry*` (`Net credit`) and a successful PP re-entry (via `auto_pp_bootstrap`) sends `✅ *PP Entry*`
  (`Net debit`); send failure non-fatal; tests green; `greeks-analyst` clean (no automated in-tick re-entry exists in `CCOverlayV1`/`PPOverlayV1` themselves — only Collar has one, per OEM-2).
- **OEM-4** — the bootstrap message is `format_entry_message`'s output for cc / pp / collar, with the unchanged `⚠️ Gate Logged` line appended when a gate fired; no hand-rolled `📥 Overlay Entry`
  f-string remains; tests green.
- **OEM-5** — `CONTEXT.md`, `src/notifications/CLAUDE.md`, `DECISIONS.md` reflect the shared overlay renderer and the sign-aware net line; the epic `README.md` Stories-table row is ✅ with the closing
  SHA; `TODOS.md` Session Log line added. The epic folder is **not** archived here.

## After each task

Set `SHA:` to the real commit SHA on the task line and tick the box. Then flip this sub-story's row in the epic `README.md` **Stories** table (`docs/plan/telegram-message-unification/README.md`) and
add one line to `TODOS.md` Session Log. The epic folder is archived only when every sub-story is done — see the epic `prompt.md` Step 4.

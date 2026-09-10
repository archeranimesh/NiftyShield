# Overlay recovery digest — tasks

Work top-down. Find the first unchecked `- [ ]` and do only that task. Each task = one commit unless noted. See `prompt.md` for why the story exists; see `stories.md` for the per-task implementation
spec.

Sub-story 4 (last) of the `telegram-message-unification/` epic. Independent of the `entry_message.py` / `exit_message.py` renderer chain — but listed last, and ORD-4 is the epic close. No `schema.md`.
ORD-2 and ORD-3 touch overlay P&L / financial-logic paths → `code-reviewer` is mandatory.

**Open: ORD-1, ORD-2, ORD-3, ORD-4.**

- [ ] **ORD-1** — Investigate whether a standalone `overlay_cc` bootstrap and a collar
      genuinely coexist (vs. `overlay_cc` always being the collar call when a collar put is
      present); decide the correct `_overlay_type_groups` behaviour; file BUG-044 with the
      finding + decision.
      | Owner: Claude | Model: claude-sonnet-5 | Review: none | SHA: —
- [ ] **ORD-2** — Fix `_overlay_type_groups` + `_compute_overlay_pnl_snapshots` per ORD-1: a
      standalone CC gets its own `cc` `OverlayPnLSnapshot` row; the collar total stops
      absorbing it; the genuine collar-call-tagged-`overlay_cc` case still works.
      | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: —
- [ ] **ORD-3** — Migrate `_build_recovery_digest` to one MarkdownV2 fenced block (no
      per-line `escape_markdown`), matching the `pre_market_brief.py` house style; fix the
      BUG-042 send path for this caller.
      | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: —
- [ ] **ORD-4** — Epic close: `CONTEXT.md` / `DECISIONS.md` / `src/notifications/CLAUDE.md`;
      flip the last epic `README.md` Stories row + **Epic done when**; `git mv` the whole
      `telegram-message-unification/` folder to `docs/archive/plan/`; collapse the
      `docs/plan/README.md` epic entry to a pointer; move the `TODOS.md` Feature Backlog line
      to `TODOS_ARCHIVE.md`; flip BUG-044 to ✅ Fixed with the ORD-2 SHA.
      | Owner: Claude | Model: claude-sonnet-5 | Review: none | SHA: —

## Story done when

- **ORD-1** — `docs/bugs/bugs.md` carries a BUG-044 entry (symptom, the verified log evidence, root cause in `_overlay_type_groups`, both effects — CC vanishes and Collar inflated); the correct
  grouping behaviour is decided and recorded here + in BUG-044.
- **ORD-2** — with `{overlay_cc, overlay_pp, overlay_collar_put}` open, `_compute_overlay_pnl_snapshots` emits a standalone `cc` `OverlayPnLSnapshot` and a `collar` row that excludes the CC leg; the
  genuine "overlay_cc is the collar call" case (per ORD-1's marker) still merges; `_build_recovery_digest` shows a real `CC` line; `protection_recovery.overlay_source_missing` no longer fires when a
  CC leg snapshot exists; the printed comparison table and the digest agree; `code-reviewer` clean; tests green.
- **ORD-3** — `_build_recovery_digest` returns one fenced MarkdownV2 block; the send uses no whole-string `escape_markdown`; a red-day and a flat/green-day digest both render and would not 400;
  golden-string tests updated; tests green.
- **ORD-4** — all docs reflect the fix + the fenced digest; every epic `README.md` Stories row is ✅ and **Epic done when** is satisfied; BUG-044 is ✅ Fixed; the epic folder is archived to
  `docs/archive/plan/telegram-message-unification/`; the `docs/plan/README.md` epic entry is a one-line pointer; the `TODOS.md` line moved to `TODOS_ARCHIVE.md`.

## After each task

Set `SHA:` to the real commit SHA on the task line and tick the box. Then flip this sub-story's row in the epic `README.md` **Stories** table and add one line to `TODOS.md` Session Log. At ORD-4,
follow `docs/plan/README.md` §Conventions *Completion → archive* for the whole epic folder.

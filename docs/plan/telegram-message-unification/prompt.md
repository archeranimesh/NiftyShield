# Telegram message unification — prompt (router)

Central entry point for this epic. `/work` loads this file, **not** a sub-story `prompt.md`. Read `CONTEXT.md` and state `CONTEXT.md ✓` before anything else, then follow the steps below to find and
run exactly one task.

**Origin:** `README.md` in this folder — the epic index. Read it if you have not this session; it carries the scope decisions (fixed order, gross-short-premium decay, no schema change, `ivr` relaxed),
the ordered story list, and the cross-cutting constraints (non-fatal sends, frozen `build_leg_table`, byte-identical IC/CSP/CC, one commit per task).

---

## Step 1 — find the next task

Story order is fixed — it is the row order of the **Stories** table in this folder's `README.md`, and it is a hard dependency chain (each story needs the previous one fully shipped):

1. `unified-entry-message/` — shared `entry_message.py` renderer; IC + CSP + CC entry cards (UEM-1..3)
2. `overlay-entry-message/` — sign-aware net line + Collar / CC / PP re-entry cards + three-track bootstrap (blocked by: `unified-entry-message` complete)
3. `unified-exit-message/` — shared `exit_message.py` close renderer + `pre_market_brief.py` redesign (blocked by: `overlay-entry-message` complete)
4. `overlay-recovery-digest/` — fix the standalone-CC-into-Collar bug (BUG-044) in the S9 digest, then fenced-format it (blocked by: `unified-exit-message` complete). Carries the epic close.

Do not jump ahead even if a later story looks more urgent — the dependencies are real (OEM-1 adds the sign-aware net line UXM needs; UXM mirrors the entry renderer's structure). Sub-story 4 does not
share the renderer lineage but is still sequenced last so the epic-archive point is unambiguous.

Open `unified-entry-message/tasks.md`. If it has any unchecked `- [ ]` line, the first one (top to bottom) is your task — stop searching, go to Step 2. Only if every box there is checked: open
`overlay-entry-message/tasks.md`, first unchecked line is your task. And so on through `unified-exit-message/` then `overlay-recovery-digest/`. If every sub-story `tasks.md` is fully checked, the epic
is complete — say so and stop; do not invent new work.

## Step 2 — confirm you are the right owner

The task line carries `| Owner: … | Model: … | Review: … | SHA: …`. Read it before doing anything.

- If `Owner` does not match the agent running this session, **stop** and report: which task you found, what it is routed to, and that this session should not implement it.
- If `Model` names a model this session is not running, say so before proceeding.
- Note the `Review` gate now — if it names a sub-agent (`code-reviewer` / `greeks-analyst`), that gate is mandatory before commit per `CLAUDE.md` Agent AutoTrigger Rules. Every `src/paper/` and
  overlay strategy-class task in this epic carries `greeks-analyst`; the docs-close tasks (UEM-3 / OEM-5 / UXM-8 / ORD-4) and ORD-1 are `Review: none`; ORD-2 (overlay P&L grouping) and ORD-3 carry
  `code-reviewer`.

## Step 3 — load the sub-story context

Read that story's own `prompt.md` for its hard constraints (scope guard, test-gate command, the one renderer gap OEM-1 must close first, the three P&L levels for UXM) and its `stories.md` for the
task's full spec. No sub-story has a `schema.md` — this epic makes no DB schema change.

## Step 4 — implement, verify, record

Follow the sub-story `prompt.md`'s protocol: implement, run the test gate, run the `Review` gate if flagged, commit via `.claude/skills/commit/SKILL.md` (execute it, do not draft it), set `SHA:` on
the task line + tick the box, flip this sub-story's row in this folder's `README.md` **Stories** table (⬜ → 🔄 → ✅ with the closing SHA), add one line to `TODOS.md` Session Log.

**Epic close (ORD-4 only):** the last sub-story's docs-close task archives the *whole epic*, per `docs/plan/README.md` §Conventions *Completion → archive* — `git mv
docs/plan/telegram-message-unification docs/archive/plan/telegram-message-unification`, collapse the `docs/plan/README.md` epic entry to a one-line pointer, move the `TODOS.md` Feature Backlog line to
`docs/archive/TODOS_ARCHIVE.md`, flip BUG-044 to ✅ Fixed. UXM-8 and the other sub-story closes only flip their `README.md` Stories row — no earlier task archives anything.

**Stop.** One task per session — do not proceed to the next unchecked item in any story.

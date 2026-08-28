# NiftyShield — Root Markdown Cleanup Skill

> Invoke this skill to tidy all root-level markdown files: archive completed work, remove stale content, and ensure only current, loadable context remains at root.
>
> **Trigger phrase:** "clean up the markdown", "do a markdown cleanup", "archive completed TODOs"

---

## What This Skill Does

Ensures the project root contains only markdown files that carry _live, session-relevant context_. Completed work, one-off plans, and reusable tools get archived or moved. Nothing useful is deleted — it is relocated.

---

## Step 1 — Survey root markdown files

Run: `ls *.md`

**Files that must stay at root (never archive):**

| File | Why it must stay |
|---|---|
| `CLAUDE.md` | Auto-loaded project instructions — must be at root |
| `CONTEXT.md` | Single source of truth — read every session |
| `CONTEXT_TREE.md` | Module tree pointer — referenced by CONTEXT.md |
| `DECISIONS.md` | Architecture rationale — read on structural changes |
| `PLANNER.md` | Sprint roadmap — read when starting feature work |
| `TODOS.md` | Open work + session log — read every session |
| `REFERENCES.md` | Instrument keys, AMFI codes, API quirks |
| `INSTRUCTION.md` | Session workflow guide for the human operator |
| `BACKTEST_PLAN.md` | Phased backtest pipeline — read for Phase 0–4 work |
| `LITERATURE.md` | Concept reference (LIT-XX codes) for analytics/ML phases |
| `REVIEW.md` | Code review checklist — loaded by `code-reviewer` agent |
| `README.md` | Public-facing project overview — keep accurate |

**Candidates to move/archive:**
- Any `*-plan.md` or `*-implementation-plan.md` whose phase is complete → `docs/archive/`
- Any `*.prompt.md` or reusable tool prompts at root → `docs/`
- Task-specific agent files in `.claude/agents/` whose task is done → `docs/archive/`

---

## Step 2 — Clean TODOS.md

**Identify done items:** `✅ DONE` markers in P4-PKG and P5-DEBT sections.

**Archive:** All `### PKG-N` and `### DEBT-N` items marked `✅ DONE`. Session log entries older than current session.

**Keep:** Priority Key table, all open P1/P2/P3/P5 items, current session log entry + archive pointer.

**Archive target:** `docs/archive/TODOS_ARCHIVE_{YYYY-MM-DD}.md`
- If file exists for today → append a new section.
- If not → create with this header:

```markdown
# NiftyShield — Completed Work Archive

> Archived: {YYYY-MM-DD}. Contains all completed TODO items and session log through {YYYY-MM-DD}.
> Active open work lives in [TODOS.md](../../TODOS.md).
```

**Session log template in TODOS.md:**
```markdown
## Session Log

| Date | What Changed |
|---|---|
| YYYY-MM-DD | **Brief title.** One sentence. |

Full log (start → end): [docs/archive/TODOS_ARCHIVE_{DATE}.md](docs/archive/TODOS_ARCHIVE_{DATE}.md)
```

---

## Step 3 — Update CONTEXT.md

Use targeted `Edit` calls only — never `Write` on CONTEXT.md.

1. **Date header** — `## Current State (as of YYYY-MM-DD)` → today.
2. **Test count** — run `python -m pytest tests/unit/ --tb=no -q 2>&1 | tail -3` and update `~NNN tests`.
3. **"What Does NOT Exist Yet"** — verify with `ls src/<module>/`; remove any entry for a module/file that now exists.
4. **Live Data** — update only when you have direct evidence (seed ran, DB wiped).

---

## Step 4 — Update README.md

**Project Structure block:**
- Every real directory in `src/` and `scripts/` must appear.
- Planned-but-empty modules: `[empty — planned QN YYYY]`.
- Remove entries for directories that don't exist.

**Roadmap checkboxes:**
- `[x]` for anything shipped. `[ ]` for planned. Priority label in parens for the top open item.

---

## Step 5 — Move tool files out of root

```bash
# Reusable prompt templates → docs/
mv <file>.prompt.md docs/

# Completed task-specific agents → docs/archive/
mv .claude/agents/<task-specific>.md docs/archive/
```

---

## Step 5b — `docs/plan/` structure audit

Run: `python scripts/hooks/check_story_structure.py --all`

Every non-archived `docs/plan/*/` folder must be a story (`prompt.md` + `tasks.md`) or an
epic (holds story sub-folders). Act on what it reports:

- **empty folder** — the story shipped and was archived; `rmdir` it.
- **legacy `*_tasks.md`** — rename to bare `tasks.md` when you are already touching that story
  (do not mass-rename).
- **missing files** — the folder is a stub; flesh it out from `docs/plan/_TEMPLATE/` or remove it.

Then confirm `TODOS.md` `## Feature Backlog` + `## Open Bugs` items are still **pointer-only**:
title, the `docs/plan/<slug>/` or `docs/bugs/` path, the next unchecked task id, one line of
why. Multi-paragraph detail or per-task progress in an item is a hygiene violation — move it
into the story's own `tasks.md` and cut the `TODOS.md` line back to a pointer. Bug priority /
status must never be encoded in `## Open Bugs` — `docs/bugs/bugs.md` is canonical.
Also check for any story/bug with all `tasks.md` boxes ticked that was not archived — if
found, do the *Completion → archive* move (folder → `docs/archive/`, `TODOS.md` line →
`TODOS_ARCHIVE.md`, README row → pointer). Full rules: `docs/plan/README.md` §Conventions.

---

## Step 6 — Commit

```
docs(root): archive completed items, trim root markdown

Why: Completed items accumulating in TODOS.md; tool/plan files adding noise to root.
What:
- TODOS.md: remove all ✅ DONE items; keep open P1/P2/P3/P5 only
- docs/archive/TODOS_ARCHIVE_{DATE}.md: append completed items + session log
- CONTEXT.md: update date, test count, stale entries
- README.md: sync project structure + roadmap checkboxes
- docs/: relocated tool/plan files from root
Ref: none
```

---

## Step 7 — Re-sync AGENTS.md (only if CLAUDE.md changed this cleanup)

`AGENTS.md` is Antigravity's autoload protocol and a deliberate standalone mirror of
`CLAUDE.md` (`CLAUDE.md` is canonical). Claude Code does **not** auto-load `AGENTS.md` — it is
a maintenance cost, not a Claude token cost — but Antigravity reads it every session, so drift
is a real defect.

If `CLAUDE.md` was edited above:

1. Re-apply each `CLAUDE.md` edit to the matching passage in `AGENTS.md`.
2. Preserve the intentional deltas: the "Antigravity autoload" / "Antigravity deltas" header
   block, and every `Edit` → `multi_replace_file_content` / `write_to_file` and
   "emit the await-signal instead of spawning `@agent`" wording.
3. Confirm the only differences are those deltas:
   `diff <(sed 's/[[:space:]]*$//' CLAUDE.md) <(sed 's/[[:space:]]*$//' AGENTS.md)`
4. Fold the `AGENTS.md` change into the same Step 6 commit.

---

## Quick Checklist

- [ ] `TODOS.md` has zero `✅ DONE` markers
- [ ] `TODOS.md` session log: current session only + archive pointer
- [ ] `docs/archive/TODOS_ARCHIVE_{TODAY}.md` contains all archived items
- [ ] `CONTEXT.md` date header is today
- [ ] `CONTEXT.md` test count matches last green run
- [ ] `README.md` project structure matches actual `src/` and `scripts/`
- [ ] `README.md` roadmap checkboxes are accurate
- [ ] No `*.prompt.md` or completed-task plan files at root
- [ ] If `CLAUDE.md` changed: `AGENTS.md` re-synced (Step 7), `diff` shows only Antigravity deltas
- [ ] Commit made in project format

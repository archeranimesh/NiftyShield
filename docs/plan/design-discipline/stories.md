
# Design Discipline — story specs

> One task per session. Find the first unchecked item in `tasks.md`. That is your only task. Full implementation rules in `CLAUDE.md` and `REVIEW.md`. After each task: set `SHA:` on the task line +
> tick the box, update the story status summary, add one line to `TODOS.md`. See `docs/plan/README.md` §Conventions.

All tasks are docs, skill or hook work. No `src/` change, so no unit tests; each task's check is stated under **Verify**.

---

## DD-1 — Bug-to-principle evidence matrix

**Files:** `docs/refactor/bug-principle-evidence.md` (new). **Before any code:** `grep -n '^## BUG-' docs/archive/bugs/bugs.md docs/bugs/bugs.md`, then read each body's root-cause section by `sed -n`;
never the whole file. **Implement:** one row per bug (id, root cause in one line, principle that would have prevented it or limited the blast radius, blast radius). Start from the 8-principle first
cut (single seam, shared mechanism, typed collaborators, no silent failure, value types, OCP, config over constants, event-loop hygiene). Correct it where bodies disagree with titles. End with counts
per principle. **Verify:** every BUG id in both files appears once; counts sum to at least the bug count. **Commit:** `docs(refactor): add bug-to-principle evidence matrix`

## DD-2 — Two-tier decision card

**Files:** `docs/refactor/decision-card.md` (new, ≤40 lines). **Implement:** Tier 1 baseline for all code, independent of bug history: SOLID triggers, `Protocol` over `ABC`, EAFP, PEP 20 simplicity,
small named functions, no silent failure, explicit types, `Decimal`. Tier 2 evidence-ranked from DD-1. Each entry is trigger → action → an existing in-repo example. **Verify:** line count ≤40; every
example path exists. **Commit:** `docs(refactor): add two-tier design decision card`

## DD-3 — `design-check` skill and plan gate

**Files:** `.claude/skills/design-check/SKILL.md` (new), `CLAUDE.md`, `AGENTS.md`. **Implement:** the skill walks the card against a proposed change and emits a Design review block (triggers hit,
chosen seam, what is left alone). Merge the check into Step 2b/3 so it runs before the plan; the plan line gains `Design:`; widen the trigger to any change adding a branch or responsibility, or
touching more than one call site. `AGENTS.md` stays a full mirror, never a stub. **Verify:** `diff` of the changed Step text between the two files shows they match. **Commit:** `docs(protocol):
require Design clause before plan`

## DD-4 — Bug Design lens

**Files:** bug template under `docs/bugs/` (`prompt.md`, `task.md`) and `docs/plan/_TEMPLATE/` if it carries a bug form; the close checklist. **Implement:** a mandatory "Design lens" section:
principle that would have helped, seam that would have limited the blast radius, refactor follow-up (yes/no + pointer). Required only when the fix touches `src/` or `scripts/`. **Verify:** a sample
bug entry renders the section; the close text states the scope rule. **Commit:** `docs(bugs): require design lens on src/scripts bugs`

## DD-5 — Presence hook

**Files:** `.claude/hooks/design_review_check.sh` (new), `.claude/settings.json`, the `UserPromptSubmit` reminder. **Implement:** `PreToolUse` on `Edit`/`Write` for `src/` and `scripts/`; warn when
the session transcript has no Design review block. A single constant flips warn to block. Document the flip date (about one week after merge). **Verify:** run the hook against a fixture transcript
with and without the block; both outcomes as expected. **Commit:** `chore(hooks): warn on src edit without design review`

## DD-6 — Reviewer backstop

**Files:** `docs/refactor/code-review-checklist.md`, `.claude/agents/code-reviewer.md`. **Implement:** add the card's triggers as review items, including the multi-call-site duplication test.
**Verify:** seeded diff (a new `elif` on a decision method) is flagged with the card's trigger name. **Commit:** `docs(review): add design card triggers to reviewer`

## DD-7 — Refactor backlog

**Files:** `TODOS.md`. **Implement:** from DD-1, add pointer-only backlog items for the highest-ranked refactors (first: one close-leg seam covering the `mark_trade_closed` paths). No execution.
**Verify:** each item names the bugs it would have prevented. **Commit:** `docs(todos): add design-driven refactor backlog`

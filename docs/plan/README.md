# `docs/plan/` — Story Files

> One markdown file per task in `BACKTEST_PLAN.md`. Cowork can work from a single story file in isolation without re-reading the entire plan.
>
> Story files are the expanded form of each `BACKTEST_PLAN.md` checkbox. They have all the detail needed to execute the task — acceptance criteria, definition of done, dependencies, estimated effort — without cluttering the main plan file.

---

## Conventions

**File naming:** `<phase>_<task>_<slug>.md`. Examples: `0_1_nuvama_tests.md`, `1_5b_analytics_module.md`, `3_5b_regime_experiment.md`. Phase and task number come from `BACKTEST_PLAN.md`; renaming a story is a PR and must be reflected in the plan.

**Story file structure:**

```markdown
# <Task ID> — <Title>

**Status:** NOT STARTED | IN PROGRESS | IN REVIEW | DONE | BLOCKED | ABANDONED
**Owner:** Animesh | Cowork | Either
**Phase:** <phase number>
**Blocks:** <list of task IDs that depend on this>
**Blocked by:** <list of task IDs this depends on>
**Estimated effort:** S | M | L | XL (≤1 day | 1-3 days | 3-7 days | 1-2 weeks)
**Literature:** <LIT-XX codes from LITERATURE.md, if any>

## Problem statement

What problem this task solves, in 2-3 paragraphs. Should stand alone — a reader should understand why this exists without reading the main plan.

## Acceptance criteria

Specific, testable conditions. Each should be verifiable without subjective judgment.

- [ ] Criterion 1
- [ ] Criterion 2
- ...

## Definition of Done

What "complete" means operationally. Should include: tests green, docs updated, commit landed, agent review passed.

- [ ] `python -m pytest tests/unit/` green
- [ ] `code-reviewer` agent clean on diff
- [ ] `CONTEXT.md` updated
- [ ] `DECISIONS.md` updated if architecture changed
- [ ] `TODOS.md` session log entry added
- [ ] Commit landed with conventional format
- [ ] `BACKTEST_PLAN.md` checkbox ticked with commit SHA

## Technical notes

Implementation-level guidance. File paths, function names, schema choices, gotchas.

## Non-goals

Explicitly what this task does NOT cover. Prevents scope creep.

## Follow-up work (if any)

Tasks that this enables or suggests, with references to existing `BACKTEST_PLAN.md` tasks or new story file names.
```

---

## How Cowork Should Use These

**Session start protocol for a single story:**

1. Human points Cowork at a specific story file: *"Work on `docs/plan/0_1_nuvama_tests.md`."*
2. Cowork loads: that story file + `CONTEXT.md` + the module's `CLAUDE.md` (auto-loaded). Does NOT need to load `BACKTEST_PLAN.md` — the story file is self-contained.
3. Cowork states the plan (one sentence + files touched) per the Step 3 protocol in root `CLAUDE.md`.
4. Human confirms scope.
5. Cowork implements, tests, commits, updates status in the story file header.

**Status transitions:** Only `IN PROGRESS` → `IN REVIEW` → `DONE` require code changes. `BLOCKED` and `ABANDONED` need a reason line added. Never skip from `NOT STARTED` directly to `DONE` — the intermediate states exist so reviews happen.

---

## File Inventory

Story files exist for tasks that are:
- Currently in flight, or
- Next-up for the current phase, or
- Required for planning handoff (gates, key strategy decisions).

Not every `BACKTEST_PLAN.md` checkbox gets a story file upfront — that would be premature. When a phase becomes active, Cowork or Animesh generates the phase's remaining story files using the template above.

**Initial story files created** (2026-04-17):

- Phase 0: `0_1_nuvama_tests.md`, `0_2_greeks_capture.md`, `0_3_finideas_roll.md`, `0_5_paper_module.md`
- Phase 1: `1_5b_analytics_module.md`, `1_10_dhan_chain_client.md`

All other story files to be generated as their phase approaches activation.

---

## Maintenance Rules

- Story files are **append-only for status changes**. The file's content reflects the plan at start of work; the `Status` header and a dated log at the bottom track progress.
- If requirements change mid-story: close the current story as `ABANDONED`, open a new one. Never mutate a story mid-flight — it destroys the audit trail.
- `BACKTEST_PLAN.md` and story files must stay in sync. If the plan changes, the affected story file's header gets a dated note. If a story discovers something new, the plan gets updated and the story notes the PR.

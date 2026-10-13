<!-- Copy the whole `story/` folder to docs/plan/<slug>/ (single story) or
docs/plan/<epic-slug>/<story-slug>/ (epic sub-story). <slug> is kebab-case: no date prefix,
no <slug>_ prefix on the files inside. Delete these HTML comments. -->

# <Story title> — prompt

> One-line statement of what this story delivers.

Read `CONTEXT.md` and state `CONTEXT.md ✓` before anything else.
Then read `tasks.md`, find the first unchecked `- [ ]`, and do **only** that task.
Read that task's full spec in `stories.md` (same task id) before writing any code.
One task per session. Complete it fully. Stop.

## Why this story exists

<!-- 1–3 short paragraphs, prose lines filled to ≤200 chars. The problem, the trigger, the
decision that scoped it. A reader should understand why this exists without opening any other file. -->

## Scope guard

<!-- What this story does NOT touch. Name the modules / files in bounds and out of bounds.
State whether it changes src/ behaviour or is docs/tooling only. -->

## Design review

<!-- Mandatory when the story adds a module, class, Protocol or cross-module seam; write "n/a — docs/tooling only" otherwise. Run the triggers in docs/refactor/design-principles.md against
the plan and record the outcome here in prose: which SOLID trigger fired and what the design does about it; where the new code sits in the one-way dependency graph
(docs/refactor/code-deduplication-and-taxonomy.md — "leaf" packages import nothing project-internal); the prior-art search you ran before designing (what already exists, with evidence); and
that new interfaces are `Protocol`s with injected collaborators. For a larger story, also add a findings table (finding | source doc | resolution | task) as in
docs/plan/strategy-payoff-charts/README.md §Design review. -->

## Session-start load hints

<!-- Which docs a session picking up this story must read beyond CONTEXT.md (always include docs/refactor/design-principles.md when the story adds code structure, and
docs/refactor/code-review-checklist.md before its commit task):
module CLAUDE.md, DECISIONS.md rows, REFERENCES.md, BACKTEST_PLAN.md, LITERATURE.md codes,
council files. Delete the ones that don't apply.
If this story changes DB schema, it carries a `schema.md` — name it here and say "read it
before any Store work." (See §Conventions "When a story needs schema.md".) -->

## Task overview

<!-- One line per task id in tasks.md, in order. The detail lives in stories.md. -->

## Definition of done

<!-- The whole-story completion bar. Mirrors `tasks.md` "## Story done when". Per-task DoD
goes in stories.md. -->

## Perspectives not covered

<!-- Mandatory per CLAUDE.md "Rules for any review or handoff" #3. At least one. Write
"none identified" only if genuinely nothing comes to mind. -->

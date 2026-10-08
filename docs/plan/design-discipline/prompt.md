# Design Discipline — prompt

> Make Python design principles and clean-code rules a gate that runs before every code proposal, and make every `src/` or `scripts/` bug close with a design lens.

Read `CONTEXT.md` and state `CONTEXT.md ✓` before anything else. Then read `tasks.md`, find the first unchecked `- [ ]`, and do **only** that task. Read that task's full spec in `stories.md` (same
task id) before writing any code. One task per session. Complete it fully. Stop.

## Why this story exists

Requested by Animesh (2026-10-08) after a plan for the IC payoff-chart caption change was drafted without applying `docs/refactor/design-principles.md`. The rule existed (CLAUDE.md Step 3c) but sat
after the plan gate and triggered only on "new module, class or seam", so it did not fire. `docs/refactor/` is also generic prose with examples from another project, loaded whole, so it is read and
forgotten. A first-cut read of the bug archive (about 70 bugs) shows the same design gaps recurring: a multi-step state change with no single seam (`mark_trade_closed` unwired in 7 close paths),
per-variant copies of one mechanism (`_parse_expiry`, partial-close credit), untyped collaborators, and silent failures.

## Scope guard

In scope: a decision card, a `design-check` skill, the CLAUDE.md / `AGENTS.md` plan-gate rewording, a bug "Design lens" field, a presence hook, reviewer checklist updates, and a refactor backlog. Out
of scope: any `src/` or `scripts/` code change, `import-linter` contracts (separate story), and executing any refactor DD-7 logs.

The card has two tiers. **Tier 1 is baseline**: it applies to all code irrespective of bug history (SOLID triggers, `Protocol` over `ABC`, EAFP, PEP 20 simplicity, small named functions, no silent
failure, explicit types, `Decimal` for money). **Tier 2 is evidence-ranked** from the bug history. Bug history orders the card and supplies examples; it does not bound it.

## Design review

Docs, skill and hook work only: no new module, class or seam in `src/`. The one design choice is the gate. The hook checks that a Design review block exists, not that it was applied. It starts as a
warning and becomes a block after about one week (Animesh, 2026-10-08). The Design clause in the plan line is the artifact, reusing the story `prompt.md` Design review section that already exists.

## Session-start load hints

`docs/refactor/design-principles.md`, `code-review-checklist.md`, `docs/bugs/bugs.md`, `docs/archive/bugs/bugs.md` (read by `grep -n '^## BUG-'` first, then bodies for DD-1). `.claude/hooks/` for
DD-5.

## Task overview

DD-1 evidence matrix → DD-2 decision card → DD-3 skill and plan gate → DD-4 bug Design lens → DD-5 hook → DD-6 reviewer checklist → DD-7 refactor backlog. Order is fixed: the card feeds everything
after it.

## Definition of done

A plan line without a Design clause is visibly incomplete; the hook warns on `src/` or `scripts/` edits with no Design review block; a bug touching `src/` or `scripts/` cannot close without a Design
lens; `code-reviewer` checks the card's triggers; the ranked refactor backlog is in `TODOS.md`.

## Perspectives not covered

Whether a warning-then-block hook is too blunt for one-line fixes (an escape hatch may be needed); how to measure whether the card actually reduces recurrence over the next 10 bugs.

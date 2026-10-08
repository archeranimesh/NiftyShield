
# Design Gate — prompt

> Make Python design principles and clean-code rules a gate that runs before every code proposal, on every surface that writes code, and make every `src/` or `scripts/` bug close with a design lens.

Read `CONTEXT.md` and state `CONTEXT.md ✓` before anything else. Then read `tasks.md`, find the first unchecked `- [ ]`, and do **only** that task. Read that task's full spec in `stories.md` (same
task id) before writing any code. One task per session. Complete it fully. Stop.

## Why this story exists

Requested by Animesh (2026-10-08) after a plan for the IC payoff-chart caption change was drafted without applying `docs/refactor/design-principles.md`. The rule existed (CLAUDE.md Step 3c) but sat
after the plan gate and triggered only on "new module, class or seam", so it did not fire. `docs/refactor/` is also generic prose with examples from another project, loaded whole, so it is read and
forgotten.

A first-cut read of the bug archive (about 70 bugs) shows recurring design gaps: a multi-step state change with no single seam (`mark_trade_closed` unwired in 7 close paths), per-variant copies of one
mechanism (`_parse_expiry`, partial-close credit), untyped collaborators, and silent failures. `docs/refactor/code-review-checklist.md` is not used by the `code-reviewer` agent: the agent never loads
it, the checklist assumes a `py-code-review` pre-commit hook that is not wired, and its FCID section has no counterpart in `src/` or `scripts/`.

## Scope guard

In scope: bug-to-principle evidence; a GoF-pattern Python applicability audit; triage of all eight `docs/refactor/` docs; a two-tier decision card; the `design-check` skill and plan-gate rewording;
carrying the gate to Antigravity handoffs, `plan-loop` workers and `new-story`; a bug "Design lens"; a presence hook; the `code-reviewer` and checklist reconciliation.

Out of scope: any `src/` or `scripts/` code change (the scan tool is in `design-baseline/`); `LOGGING.md` and logging changes (separate epic); `import-linter` contracts; any refactor.

The card has two tiers. **Tier 1 is baseline**: it applies to all code irrespective of bug history (SOLID triggers, `Protocol` over `ABC`, EAFP, PEP 20 simplicity, small named functions, no silent
failure, explicit types, `Decimal` for money). **Tier 2 is evidence-ranked** from the bug history, which orders the card and supplies examples but does not bound it.

## Design review

Docs, skill and hook work only: no new module, class or seam in `src/`. The gate is a presence check: the hook confirms a Design review block exists, not that it was applied. It starts as a warning,
accepts `Design: n/a — <reason>` for docs-only and one-line changes, and flips to a block at the calibration review in `design-baseline/` (DBL-4). Decided by Animesh, 2026-10-08.

## Session-start load hints

`docs/refactor/` (all eight files), `.claude/agents/code-reviewer.md`, `docs/bugs/bugs.md`, `docs/archive/bugs/bugs.md` (read by `grep -n '^## BUG-'` first, then bodies for DG-1), `.claude/hooks/`,
`.claude/skills/`.

## Task overview

DG-1 evidence matrix → DG-2 GoF audit → DG-3 refactor-docs triage → DG-4 decision card → DG-5 skill and plan gate → DG-6 other surfaces → DG-7 bug Design lens → DG-8 hook → DG-9 reviewer and
checklist. Order is fixed: the card feeds everything after it.

## Definition of done

A plan line without a Design clause is visibly incomplete on every surface (Claude, `plan-loop` workers, Antigravity handoffs); the hook warns on `src/` or `scripts/` edits with no Design review
block; a bug touching `src/` or `scripts/` cannot close without a Design lens; `code-reviewer` checks the card's triggers.

## Perspectives not covered

Whether warn-then-block is too blunt for small fixes; how Antigravity can be held to the gate when it cannot run hooks (the handoff element is the only lever); whether a council critique of the
finished card is worth the cost.

# Refactor playbook — index

> A generic method, scoped to **Python** projects, for taking a sprawl of ad hoc, duplicated scripts/projects accumulated over time and re-implementing them, with discipline, as a single
> well-structured codebase. Distilled from a real multi-week refactor; every project-specific name has been stripped out, but the design-level guidance is intentionally Python-specific (PEP 20,
> `Protocol`/structural typing, `contextvars`, EAFP) rather than translated into language-neutral abstractions — Python already bakes a lot of classic design-pattern shape into the language itself,
> and a generic "interface"/"trait" framing would obscure that rather than use it. Apply this when the problem shape matches: a loose folder of organically-grown Python projects/scripts (no shared
> library, no taxonomy, no planning discipline) that needs to become one deliberately designed codebase, with the old tree kept read-only as reference until the new one fully replaces it.

## When this model fits — and when it doesn't

This playbook assumes:

- A **read-only legacy tree** exists (the "reference") that the new codebase is built *from*, not *in* — nothing in the legacy tree is ever edited or deleted during the refactor.
- The work is large enough to need **multi-session, multi-week planning** — not a single-sitting fix. If the whole thing fits in one sitting, skip the planning-protocol doc below and just do the work.
- The duplication problem is real and **auditable** — you can point at N copies of the same logic across M projects, not just a hunch that "there's probably duplication somewhere."
- A long-lived coding assistant (human or AI) is doing the work across many sessions, so **session-boundary discipline** (what to re-read, when to stop and ask, how to hand off a half-finished task)
  matters as much as the code design itself.

If instead you're refactoring a single existing codebase in place (no separate legacy tree, no multi-week timeline), most of this still applies but the planning-protocol and taxonomy docs are overkill
— read `design-principles.md` and `logging-and-correlation-id.md` only.

## How to use this

Read in this order the first time; after that, load whichever single doc matches the task at hand (each is self-contained):

1. **[`design-principles.md`](./design-principles.md)** — the code-level discipline: SOLID restated as checkable triggers (not an essay), the named patterns that fall out of applying them, and why
   "read this once, apply by judgment" is the right shape until it demonstrably isn't.
2. **[`code-deduplication-and-taxonomy.md`](./code-deduplication-and-taxonomy.md)** — how to find and fix duplication across many projects: audit-before-design, a shared-library module map, a "shared
   vs. specific" test, a project/folder taxonomy, and registries that make checking for prior art the fast path instead of the disciplined-but-skipped path.
3. **[`planning-protocol.md`](./planning-protocol.md)** — how to structure the refactor itself as trackable work: story/epic plan folders, one-task-per-session execution, design review as a distinct
   pre-implementation phase, and archiving completed work without losing its history.
4. **[`logging-and-correlation-id.md`](./logging-and-correlation-id.md)** — a concrete worked example of applying the design principles to one cross-cutting concern (run-level log correlation),
   including the propagation mechanism, what was deliberately deferred, and why.
5. **[`process-discipline.md`](./process-discipline.md)** — the meta-layer: the recurring protocol failures a real refactor of this kind produces (plan-before-editing, re-reading context, token
   efficiency) and how to close the loop on them session over session.
6. **[`python-hygiene-and-automation.md`](./python-hygiene-and-automation.md)** — the other layer below `design-principles.md`: a line-level Python defect/design-smell checklist, and how to turn it
   from a document into mechanical enforcement (lint/typecheck/test targets, pre-commit hooks, an AI-reviewer hook for the shapes a static rule can't express, phased adoption).
7. **[`architecture-diagrams.md`](./architecture-diagrams.md)** — drawing a "before" structure diagram at audit time and an "after" one once the new structure lands, excluding tests from both, and
   what a visible improvement (not just a claimed one) looks like in the comparison.
8. **[`code-review-checklist.md`](./code-review-checklist.md)** — a short per-PR checklist limited to what a diff-scoped automated reviewer structurally cannot check (SOLID/pattern-shape judgment,
   cross-project duplication, FCID correctness, diagram discipline, process discipline) — validated against this repo's actual `ruff`/pre-commit setup so it doesn't repeat what's already enforced.

## The one-sentence version

Audit first (find real, evidenced duplication — don't guess), design the seam before writing the implementation (`Protocol`-based dependency injection, named patterns only where a concrete trigger
fires — and only in their Pythonic shape, not a transplanted Java one), track the work as small plan-bearing story units with a pre-implementation design-review pass, and close every loop (docs,
tests, commit) before moving to the next unit — with a feedback mechanism that turns recurring process mistakes into a ranked, visible backlog instead of repeating silently.

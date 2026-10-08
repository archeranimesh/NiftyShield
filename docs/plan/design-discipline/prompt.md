# Design Discipline — prompt

> Make Python design principles and clean-code rules a gate that runs before every code proposal, baseline how much existing code follows them, and make every `src/` or `scripts/` bug close with a
> design lens.

Read `CONTEXT.md` and state `CONTEXT.md ✓` before anything else. Then read `tasks.md`, find the first unchecked `- [ ]`, and do **only** that task. Read that task's full spec in `stories.md` (same
task id) before writing any code. One task per session. Complete it fully. Stop.

## Why this story exists

Requested by Animesh (2026-10-08) after a plan for the IC payoff-chart caption change was drafted without applying `docs/refactor/design-principles.md`. The rule existed (CLAUDE.md Step 3c) but sat
after the plan gate and triggered only on "new module, class or seam", so it did not fire. `docs/refactor/` is also generic prose with examples from another project, loaded whole, so it is read and
forgotten.

A first-cut read of the bug archive (about 70 bugs) shows the same design gaps recurring: a multi-step state change with no single seam (`mark_trade_closed` unwired in 7 close paths), per-variant
copies of one mechanism (`_parse_expiry`, partial-close credit), untyped collaborators, and silent failures.

Two further gaps were found the same day. First, nobody knows how much existing code follows these principles, so there is no way to rank refactors by payoff. Second,
`docs/refactor/code-review-checklist.md` is not used by the `code-reviewer` agent: the agent never loads it, the checklist assumes a `py-code-review` AI pre-commit hook that is not wired in
`.pre-commit-config.yaml`, and its FCID section has no counterpart in `src/` or `scripts/`.

## Scope guard

In scope: a GoF-pattern Python applicability audit; a decision card; a tested `scripts/dev/design_scan.py` conformance scan and a baseline report (adherence, hotspots, latency, refactor ROI); a
`design-check` skill; the CLAUDE.md / `AGENTS.md` plan-gate rewording; a bug "Design lens" field; a presence hook; reconciling `code-review-checklist.md` with the `code-reviewer` agent; a refactor
backlog.

Out of scope: any `src/` code change; any `scripts/` change other than `scripts/dev/design_scan.py` and its tests; `import-linter` contracts (separate story); executing any refactor DD-10 logs.

The card has two tiers. **Tier 1 is baseline**: it applies to all code irrespective of bug history (SOLID triggers, `Protocol` over `ABC`, EAFP, PEP 20 simplicity, small named functions, no silent
failure, explicit types, `Decimal` for money). **Tier 2 is evidence-ranked** from the bug history. Bug history orders the card and supplies examples; it does not bound it.

## Design review

The one code artifact is `scripts/dev/design_scan.py`: a pure, read-only CLI (AST and `git log` over the tree, no network, no DB) with one function per check so a new check is a new function, not a
new branch. Everything else is docs, skill and hook work.

The gate: the hook checks that a Design review block exists, not that it was applied. It starts as a warning and becomes a block after about one week (Animesh, 2026-10-08). The Design clause in the
plan line is the artifact, reusing the story `prompt.md` Design review section that already exists.

Adherence is measured two ways. Mechanical checks (constructor-built collaborators, `elif` chains, complexity, function and file length, silent `except`, `ABC` vs `Protocol`, missing type hints,
`float` on money, blocking I/O in `async def`, duplicate bodies, graph fan-out) run repo-wide. SRP and LSP are judged by hand on the top 5 hotspots only. A hotspot is churn × complexity × the bug
count from DD-1.

Latency is a separate axis. Design refactors improve changeability and bug rate; they do not by themselves reduce latency, except event-loop hygiene (BUG-068). The report states which latency findings
are design fixes and which are tuning, and does not claim refactors speed anything up.

Checklist reconciliation: keep `code-review-checklist.md` §1–3 (SOLID triggers, `Protocol`/pattern shape, duplication and boundary discipline) and wire them into the `code-reviewer` agent. §5
(before/after diagrams) becomes a done-criterion for refactor stories only. Drop §4 (FCID, not used here) and §6 (duplicates CLAUDE.md Steps 3–5).

## Session-start load hints

`docs/refactor/design-principles.md`, `code-review-checklist.md`, `.claude/agents/code-reviewer.md`, `docs/bugs/bugs.md`, `docs/archive/bugs/bugs.md` (read by `grep -n '^## BUG-'` first, then bodies
for DD-1). `.claude/hooks/` for DD-8.

## Task overview

DD-1 evidence matrix → DD-2 GoF applicability audit → DD-3 decision card → DD-4 `design_scan.py` CLI → DD-5 baseline report → DD-6 skill and plan gate → DD-7 bug Design lens → DD-8 hook → DD-9
reviewer and checklist → DD-10 refactor backlog. Order is fixed: the card defines the checks, the scan measures them, the report ranks refactors.

## Definition of done

A plan line without a Design clause is visibly incomplete; the hook warns on `src/` or `scripts/` edits with no Design review block; a bug touching `src/` or `scripts/` cannot close without a Design
lens; `code-reviewer` checks the card's triggers; a baseline report shows per-module adherence, hotspots, a separate latency axis and a ranked refactor list; the ranked refactor backlog is in
`TODOS.md`.

## Perspectives not covered

Whether a warning-then-block hook is too blunt for one-line fixes (an escape hatch may be needed); that SRP and LSP adherence is judged by hand on 5 hotspots only, not measured repo-wide; that design
refactors do not by themselves reduce latency; how to measure whether the card reduces recurrence over the next 10 bugs.

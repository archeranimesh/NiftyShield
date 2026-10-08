
# Design Baseline — prompt

> Measure how much existing code follows the design card, rank refactors by payoff, and calibrate the gate after it has run for a while.

Read `CONTEXT.md` and state `CONTEXT.md ✓` before anything else. Then read `tasks.md`, find the first unchecked `- [ ]`, and do **only** that task. Read that task's full spec in `stories.md` (same
task id) before writing any code. One task per session. Complete it fully. Stop.

## Why this story exists

Nobody knows how much of `src/` and `scripts/` follows the design principles, so there is no way to rank refactors by payoff or to tell whether the gate in `design-gate/` is working. Requested by
Animesh (2026-10-08).

## Scope guard

In scope: `scripts/dev/design_scan.py` and its tests; a baseline report; a refactor backlog in `TODOS.md`; a calibration review.

Out of scope: any `src/` change; executing any refactor; `import-linter`; making the scan a recurring or blocking check (decide at DBL-4).

Blocked until `design-gate/` DG-4 (the decision card) is done: the scan implements the card's mechanical checks.

## Design review

The one code artifact is `scripts/dev/design_scan.py`: a pure, read-only CLI (AST and `git log` over the tree, no network, no DB). One small function per check, selected through a registry `dict`, so
a new check is a new entry, not a new branch. Run per the repo's logging rule (`_SCRIPT_NAME`, `setup_logging()`).

Adherence is measured two ways. Mechanical checks (constructor-built collaborators, `elif` chains, complexity, function and file length, silent `except`, `ABC` vs `Protocol`, missing type hints,
`float` on money, blocking I/O in `async def`, duplicate bodies, graph fan-out) run repo-wide. SRP and LSP are judged by hand on the top 5 hotspots only. A hotspot is churn × complexity × the bug
count from `design-gate/` DG-1.

Latency is a separate axis. Design refactors improve changeability and bug rate; they do not by themselves reduce latency, except event-loop hygiene (BUG-068). The report states which latency findings
are design fixes and which are tuning, and does not claim refactors speed anything up.

## Session-start load hints

`design-gate/` outputs (card, evidence matrix), `scripts/dev/` existing helpers, `LOGGING.md`, `git log` for churn.

## Task overview

DBL-1 scan CLI → DBL-2 baseline report → DBL-3 refactor backlog → DBL-4 calibration review (about a week after the DG-8 hook merges, or after 10 new bugs).

## Definition of done

A baseline report shows per-module adherence, hotspots, a separate latency axis and a ranked refactor list; the backlog is in `TODOS.md`; the calibration review has decided the hook mode.

## Perspectives not covered

SRP and LSP adherence is judged by hand on 5 hotspots only, not measured repo-wide; design refactors do not by themselves reduce latency; whether the scan should become a ratchet on touched files.


# Design Baseline — story specs

> One task per session. Find the first unchecked item in `tasks.md`. That is your only task. Full implementation rules in `CLAUDE.md` and `REVIEW.md`. After each task: set `SHA:` on the task line +
> tick the box, update the story status summary, add one line to `TODOS.md`. See `docs/plan/README.md` §Conventions.

## DBL-1 — `design_scan.py` conformance scan

**Files:** `scripts/dev/design_scan.py` (new), `tests/unit/dev/test_design_scan.py` (new; add `__init__.py` if the directory is new). **Before any code:** read DG-4's card and run its SOLID triggers
against the plan; `search_graph("scripts.dev")` for an existing scan or audit helper to extend rather than duplicate. A new `scripts/` entrypoint also needs `LOGGING.md` (`_SCRIPT_NAME =
"scripts.dev.design_scan"`, `setup_logging()`). **Implement:** a pure, read-only CLI over `src/` and `scripts/` using `ast`. One small function per check, each returning findings (path, line, check
id); a registry `dict` maps check id to function, so a new check adds an entry, not a branch. Checks: collaborator constructed in `__init__` (DIP), `elif` chain of 4 or more (OCP), cyclomatic
complexity, function length, file length, bare or silent `except`, `ABC` vs `Protocol`, public function missing type hints, `float` on monetary names, blocking call inside `async def`, near-duplicate
function bodies across files. Output a per-module scorecard (JSON and a short table). No network, no DB. **Tests:** one happy path and one edge case per check against small inline source strings
(`test_di_flags_constructed_collaborator`, `test_di_ignores_injected`, and so on), plus a CLI test on a temp tree. **Review:** `code-reviewer` before commit. **Commit:** `feat(dev): add design
conformance scan CLI`

---

## DBL-2 — Baseline report and refactor ROI

**Files:** `docs/refactor/baseline-2026-10.md` (new). **Implement:** run DBL-1 over the tree. Overlay hotspot score = `git log` churn × complexity × the DG-1 bug count per file. Hand-score the top 5
hotspots against the card for SRP and LSP, which no metric covers. Add a separate latency axis: time the `StrategyMonitor` tick loop and the cron entrypoints, and list blocking calls on the hot path,
labelling each as a design fix or tuning. End with a ranked refactor list naming the principle, the bugs it would have prevented, and the expected blast-radius reduction. State plainly what the report
cannot show (no repo-wide SRP/LSP number, no latency gain from design alone). **Verify:** the ranking cites DBL-1 output and DG-1 ids; the latency section contains measured numbers, not estimates.
**Commit:** `docs(refactor): add design baseline and refactor ranking`

---

## DBL-3 — Refactor backlog

**Files:** `TODOS.md`. **Implement:** from the DBL-2 ranking, add pointer-only backlog items for the highest-ranked refactors (the first candidate from the evidence so far: one close-leg seam covering
the `mark_trade_closed` paths). No execution. **Verify:** each item names the bugs it would have prevented. **Commit:** `docs(todos): add design-driven refactor backlog`

---

## DBL-4 — Calibration review

**Files:** `docs/refactor/calibration-<date>.md` (new); the hook constant from DG-8 if the mode changes. **When:** about one week after the DG-8 hook merges, or after the next 10 new `src/`/`scripts/`
bugs, whichever is later. **Implement:** re-run DBL-1 and compare with the DBL-2 baseline; tally which Design lens principles recur in the new bugs; count hook warnings, false positives and `Design:
n/a` uses; flip the hook from warn to block if false positives are rare. State whether the card caught anything and what to change in it. **Verify:** the report cites the re-run scan output and the
bug and warning counts; the hook mode in the repo matches the report's decision. **Commit:** `docs(refactor): add design discipline calibration review`


# Design Discipline — story specs

> One task per session. Find the first unchecked item in `tasks.md`. That is your only task. Full implementation rules in `CLAUDE.md` and `REVIEW.md`. After each task: set `SHA:` on the task line +
> tick the box, update the story status summary, add one line to `TODOS.md`. See `docs/plan/README.md` §Conventions.

Only DD-3 is Python code and has unit tests. The other tasks are docs, skill or hook work, and each states its own **Verify** step.

---

## DD-1 — Bug-to-principle evidence matrix

**Files:** `docs/refactor/bug-principle-evidence.md` (new). **Before any code:** `grep -n '^## BUG-' docs/archive/bugs/bugs.md docs/bugs/bugs.md`, then read each body's root-cause section by `sed -n`;
never the whole file. **Implement:** one row per bug (id, root cause in one line, files touched, principle that would have prevented it or limited the blast radius). Start from the 8-principle first
cut (single seam, shared mechanism, typed collaborators, no silent failure, value types, OCP, config over constants, event-loop hygiene). Correct it where bodies disagree with titles. End with counts
per principle. The files-touched column feeds the DD-4 hotspot overlay. **Verify:** every BUG id in both files appears once; counts sum to at least the bug count. **Commit:** `docs(refactor): add
bug-to-principle evidence matrix`

## DD-2 — Two-tier decision card

**Files:** `docs/refactor/decision-card.md` (new, ≤40 lines). **Implement:** Tier 1 baseline for all code, independent of bug history: SOLID triggers, `Protocol` over `ABC`, EAFP, PEP 20 simplicity,
small named functions, no silent failure, explicit types, `Decimal`. Tier 2 evidence-ranked from DD-1. Each entry is trigger → action → an existing in-repo example. Fold in `code-review-checklist.md`
§1–3 (SOLID triggers, `Protocol`/pattern shape, duplication and module boundary) so there is one source, not two. **Verify:** line count ≤40; every example path exists. **Commit:** `docs(refactor):
add two-tier design decision card`

## DD-3 — `design_scan.py` conformance scan

**Files:** `scripts/dev/design_scan.py` (new), `tests/unit/dev/test_design_scan.py` (new; add `__init__.py` if the directory is new). **Before any code:** read DD-2's card and run its SOLID triggers
against the plan; `search_graph("scripts.dev")` for an existing scan or audit helper to extend rather than duplicate. A new `scripts/` entrypoint also needs `LOGGING.md` (`_SCRIPT_NAME =
"scripts.dev.design_scan"`, `setup_logging()`). **Implement:** a pure, read-only CLI over `src/` and `scripts/` using `ast`. One small function per check, each returning findings (path, line, check
id); a registry `dict` maps check id to function, so a new check adds an entry, not a branch. Checks: collaborator constructed in `__init__` (DIP), `elif` chain of 4 or more (OCP), cyclomatic
complexity, function length, file length, bare or silent `except`, `ABC` vs `Protocol`, public function missing type hints, `float` on monetary names, blocking call inside `async def`, near-duplicate
function bodies across files. Output a per-module scorecard (JSON and a short table). No network, no DB. **Tests:** one happy path and one edge case per check against small inline source strings
(`test_di_flags_constructed_collaborator`, `test_di_ignores_injected`, and so on), plus a CLI test on a temp tree. **Review:** `code-reviewer` before commit. **Commit:** `feat(dev): add design
conformance scan CLI`

## DD-4 — Baseline report and refactor ROI

**Files:** `docs/refactor/baseline-2026-10.md` (new). **Implement:** run DD-3 over the tree. Overlay hotspot score = `git log` churn × complexity × the DD-1 bug count per file. Hand-score the top 5
hotspots against the card for SRP and LSP, which no metric covers. Add a separate latency axis: time the `StrategyMonitor` tick loop and the cron entrypoints, and list blocking calls on the hot path,
labelling each as a design fix or tuning. End with a ranked refactor list naming the principle, the bugs it would have prevented, and the expected blast-radius reduction. State plainly what the report
cannot show (no repo-wide SRP/LSP number, no latency gain from design alone). **Verify:** the ranking cites DD-3 output and DD-1 ids; the latency section contains measured numbers, not estimates.
**Commit:** `docs(refactor): add design baseline and refactor ranking`

## DD-5 — `design-check` skill and plan gate

**Files:** `.claude/skills/design-check/SKILL.md` (new), `CLAUDE.md`, `AGENTS.md`. **Implement:** the skill walks the card against a proposed change and emits a Design review block (triggers hit,
chosen seam, what is left alone). Merge the check into Step 2b/3 so it runs before the plan; the plan line gains `Design:`; widen the trigger to any change adding a branch or responsibility, or
touching more than one call site. `AGENTS.md` stays a full mirror, never a stub. **Verify:** `diff` of the changed Step text between the two files shows they match. **Commit:** `docs(protocol):
require Design clause before plan`

## DD-6 — Bug Design lens

**Files:** bug template under `docs/bugs/` (`prompt.md`, `task.md`) and the close checklist. **Implement:** a mandatory "Design lens" section: principle that would have helped, seam that would have
limited the blast radius, refactor follow-up (yes/no + pointer). Required only when the fix touches `src/` or `scripts/`. **Verify:** a sample bug entry renders the section; the close text states the
scope rule. **Commit:** `docs(bugs): require design lens on src/scripts bugs`

## DD-7 — Presence hook

**Files:** `.claude/hooks/design_review_check.sh` (new), `.claude/settings.json`, the `UserPromptSubmit` reminder. **Implement:** `PreToolUse` on `Edit`/`Write` for `src/` and `scripts/`; warn when
the session transcript has no Design review block. A single constant flips warn to block. Document the flip date (about one week after merge). **Verify:** run the hook against a fixture transcript
with and without the block; both outcomes as expected. **Commit:** `chore(hooks): warn on src edit without design review`

## DD-8 — Reviewer and checklist reconciliation

**Files:** `docs/refactor/code-review-checklist.md`, `.claude/agents/code-reviewer.md`, the CLAUDE.md and `AGENTS.md` table row that cites the checklist. **Implement:** in the checklist, keep §1–3,
make §5 (before/after diagrams) a done-criterion for refactor stories only, and remove §4 (FCID: no usage in `src/` or `scripts/`) and §6 (duplicates CLAUDE.md Steps 3–5). Remove its claim that a
`py-code-review` pre-commit hook already runs. In the agent, add a section 8 "Design" that points at the card, includes the multi-call-site duplication test, and tells the reviewer to use the graph
for repo context, since a diff alone cannot show duplication. The agent keeps its existing NiftyShield checks. **Verify:** a seeded diff (a new `elif` on a decision method; a collaborator built in
`__init__`) is flagged with the card's trigger name; the checklist has no inapplicable section. **Commit:** `docs(review): wire design card into code-reviewer`

## DD-9 — Refactor backlog

**Files:** `TODOS.md`. **Implement:** from the DD-4 ranking, add pointer-only backlog items for the highest-ranked refactors (the first candidate from the evidence so far: one close-leg seam covering
the `mark_trade_closed` paths). No execution. **Verify:** each item names the bugs it would have prevented. **Commit:** `docs(todos): add design-driven refactor backlog`

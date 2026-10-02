
# Strategy Module Refactor & AI-Collaboration Blueprint — story specs

> One task per session. Find the first unchecked item in `tasks.md`. That is your only task. Full implementation rules in `CLAUDE.md` and `REVIEW.md`. After each task: set `SHA:` on the task line +
> tick the box, update the story status summary, add one line to `TODOS.md`. See `docs/plan/README.md` §Conventions.

---

## BP-1 — Run `/md-organize`; resolve or confirm-clear doc growth

**Files to change / create:** whatever `/md-organize` itself touches (`TODOS.md`, `docs/archive/TODOS_ARCHIVE.md`, `DECISIONS.md`, `docs/archive/DECISIONS_worklog_2026.md`, `CONTEXT.md`, `README.md`
as applicable) — this task is "invoke the skill," not hand-edit docs.

**Before any code:** none — docs-only, no `src/` graph queries needed.

**What to implement:**

1. Invoke the `md-organize` skill end to end (its own Steps 1–7).
2. Confirm against this story's discussion trigger: is `TODOS.md` (949 lines, 2026-09-26 snapshot) actually carrying stale session-log entries that Step 2 would archive, or has it already been kept
   current and the "growth" observation was a stale read? Record the answer here as a one-line note before ticking the box — this is the confirm-or-refute step, not just a mechanical run.
3. Same check for `DECISIONS.md` (1,140 lines) against Step 4's semantic-split criteria.

**Tests:** none — docs/config-only change, `code-reviewer` and `test-runner` do not gate this.

**Commit:** `docs(root): organize markdown per md-organize skill` (or whatever the skill's own Step 6 template produces).

---

## BP-2 — Extend `paper-pnl-golden-tests/` scope to `ic_nifty_v1`/`v2` decision points

**Files to change / create:**
- `docs/archive/plan/full-repo-review-followups/paper-pnl-golden-tests/tasks.md` — add task(s) for strategy-decision-point fixtures alongside the existing P&L-math scope.
- `docs/archive/plan/full-repo-review-followups/paper-pnl-golden-tests/stories.md` — spec the new tasks.
- New fixture-capture tooling/tests under `tests/unit/strategy/` (exact paths TBD by the task spec written here — this task only scopes it, a later task in that story implements it).

**Before any code (graph queries — do not write model constructors from memory):**
- `get_code_snippet("CSPNiftyV1")`, `get_code_snippet("IronCondorV1")`, `get_code_snippet("IronCondorV2")` — confirm current entry/roll/close method signatures before scoping what a "decision point"
  fixture needs to capture.
- `trace_path("StrategyMonitor")` — confirm exactly how/when these strategies' decision functions are invoked, so the golden-test harness captures inputs at the right seam.

**What to implement:**

1. Identify the concrete decision points worth characterizing: entry sizing, roll-trigger evaluation, DTE-tiered exit/time-stop logic, partial-roll leg selection — for both v1 and v2.
2. For each, define what a golden fixture captures (recorded `OptionChain`/DTE/position state → asserted output action) and where recorded real data can come from (existing Parquet chain snapshots,
   `paper_leg_snapshots` rows) vs. what needs synthetic fixtures.
3. Write the task additions into `paper-pnl-golden-tests/tasks.md`/`stories.md` — do not implement the fixtures in this task; this task's job is scoping, so the existing story's owner (whoever picks
   it up next) has a complete spec.

**Tests:** N/A for this task itself (it's a scoping/spec task) — the golden tests it specs are covered by that story's own DoD once implemented.

**Commit:** `docs(plan): scope ic_nifty_v1/v2 golden-test coverage into paper-pnl-golden-tests`

---

## BP-3 — Council question: `ic_nifty_v1`/`v2` decomposition boundary

**Files to change / create:**
- `docs/council/pending/` draft question file (per `docs/council/README.md` template).
- `DECISIONS.md` — ruling recorded once the council returns (per `protocol-reference` §1).

**Before any code:** `trace_path("IronCondorV1")` and `trace_path("IronCondorV2")` to confirm current call-site overlap (are they ever invoked from shared code today, or fully independent?) before
drafting the question — the question should state confirmed facts, not assumptions.

**What to implement:**

1. Draft the council question: does `ic_nifty_v2.py` (2,935 lines) share enough entry/roll/close logic with `ic_nifty_v1.py` (1,409 lines) to warrant a common base/shared module, or does each stay
   independent with only cross-cutting pure helpers (DTE math, leg-selection utilities) extracted? Two defensible approaches, load-bearing, spans engineering (maintainability) + risk/greeks
   (behavior-preservation risk of a shared base silently changing one strategy when the other is touched) — the genuine Step 2b three-condition trigger.
2. Recommend a template per `docs/council/README.md`, get Animesh's go-ahead on the draft, submit.
3. On return: record the ruling in `DECISIONS.md`, update this story's `plan.md` scope (BP-4) accordingly.

**Tests:** none — council process, not code.

**Commit:** `docs(council): rule ic_nifty_v1/v2 decomposition boundary` (after the ruling lands).

---

## BP-4 — Council-ruled file-by-file decomposition `plan.md`

**Files to change / create:**
- `docs/plan/strategy-refactor-blueprint/plan.md` (new — an "extra file," no task checkboxes, per `docs/plan/README.md` §Conventions "Extra files").

**Before any code:** re-read `ic_nifty_v1.py`/`ic_nifty_v2.py` via `get_code_snippet` per block (not a raw `Read` of either file — both exceed the point where `sed -n` targeted reads or graph snippets
are mandatory per Rule 0) to identify the actual block boundaries the council ruling implies moving.

**What to implement:**

1. Enumerate every block that moves: source lines, destination file/module, whether it's a pure mechanical cut-paste or needs a signature change.
2. Order the moves into single-commit steps — each one small enough that BP-2's golden tests can gate it individually and a `git revert` of one commit doesn't touch another's changes.
3. Name which AutoTrigger agents gate each commit (`code-reviewer` always; `roll-validator` for any roll-logic block; `greeks-analyst` for any Greeks/delta-touching block).
4. Get council/Animesh sign-off on the plan itself before any extraction story is scaffolded.

**Tests:** N/A — this task produces a plan document, not code.

**Commit:** `docs(plan): decomposition plan for ic_nifty_v1/v2`

---

## BP-5 — Generalized AI-collaboration blueprint draft

**Files to change / create:**
- `docs/plan/strategy-refactor-blueprint/blueprint-draft.md` (new — extra file, no checkboxes).

**Before any code:** none.

**What to implement:**

1. Once BP-2–BP-4 (and ideally at least one real extraction commit from the follow-on story) have run, write up what worked: which parts of the Claude/Antigravity/council routing table in
   `protocol-reference` §3 held, and where this case study forced a deviation (e.g., did Antigravity actually execute a mechanical extraction step, or did every step end up Claude-owned because of the
   golden-test-diffing judgment calls?).
2. Draft it as a proposed diff to `protocol-reference` §3 — do not edit that skill file directly from this task; leave the actual merge as a separate, explicitly-scoped follow-up once Animesh reviews
   the draft.

**Tests:** none — docs.

**Commit:** `docs(plan): draft AI-collaboration blueprint from strategy-refactor case study`

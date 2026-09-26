
# Cross-Project Claude Template Blueprint — story specs

> One task per session. Find the first unchecked item in `tasks.md`. That is your only task. All tasks here are docs/design-only — no `src/`/`scripts/` graph queries needed, no tests, no code-reviewer
> gate. After each task: set `SHA:` on the task line + tick the box, update the story status summary, add one line to `TODOS.md`. See `docs/plan/README.md` §Conventions.

---

## PTB-1 — Write up discussion as `plan.md` draft

**Files to change / create:**
- `docs/plan/project-template-blueprint/plan.md` (new — extra file, no task checkboxes, per §Conventions "Extra files").

**Before any code:** none — pure write-up from the 2026-09-26 conversation transcript.

**What to implement:**

1. Transcribe the four-tier table (Bootstrap / Recurring work / Correctness-critical or multi-surface / Scale) with trigger conditions and contents, as sketched in discussion.
2. Transcribe the scratch/tmp distinction (git-tracked + curated vs gitignored + throwaway) and the architecture-doc trio (`CONTEXT.md` mutable snapshot / `DECISIONS.md` append-only rationale /
   `CONTEXT_TREE.md` derived index).
3. Transcribe the generalized model-routing sketch (mechanical/bulk, design/judgment, independent verification) and the reasoning for why full routing tables are a Tier 2+ concern.
4. Carry forward every open question from `prompt.md` §"Perspectives not covered" verbatim as a live "Open Questions" section — do not resolve them in this task, just preserve them.
5. Do not add new opinions beyond what was discussed — this task's job is capture, not advancement. PTB-2 onward is where the design actually moves forward, task by task, with Animesh's explicit
   input.

**Tests:** none — docs-only capture task.

**Commit:** `docs(plan): capture cross-project template discussion as plan.md`

---

## PTB-2 — Concretize Tier 0 (Bootstrap)

**Files to change / create:**
- `docs/plan/project-template-blueprint/plan.md` — Tier 0 section, expanded from sketch to literal file contents.

**Before any code:** re-read `SCRATCH.md` and `tmp/README.md` in full (already read once in this story's originating conversation — confirm nothing's drifted) before drafting their generalized
equivalents.

**What to implement:**

1. Draft the literal starting `CLAUDE.md` skeleton for a brand-new project (Step 1–5 shape, with every NiftyShield-specific reference — `DB_REGISTRY.md`, `BACKTEST_PLAN.md`, module-`CLAUDE.md` index —
   removed or replaced with a placeholder comment explaining when to add it back).
2. Draft the literal starting `CONTEXT.md` skeleton (headers only: "What Exists", "Key Decisions" pointer, "Current Constraints", "Pre-Task Protocol" pointer — no NiftyShield content).
3. Decide whether `scratch/`'s subfolder-per-purpose convention should exist from day one (empty buckets) or only appear once a project's own scratch/ folder passes some file count — this specific
   question was left open in discussion and needs Animesh's call, not an assumed answer.
4. Confirm the `tmp/README.md` one-liner travels as-is (it's already fully generic).
5. **Re-scoped in from PTB-3 (2026-09-26):** `commit` and `session-close` are both classified Tier 0 in `plan.md`'s own tier table, so their stripped/genericized skill files belong here, not in PTB-3.
   Produce `.claude/skills/commit/SKILL.md` and `.claude/skills/session-close/SKILL.md` with every NiftyShield-specific reference removed (`@code-reviewer`/`@greeks-analyst`/`@roll-validator` gates,
   `scripts.dev.commit_preflight`, `scripts.dev.token_audit`, `scripts.dev.session_audit_log`, council/Antigravity checklist rows) — keep only the mechanism that has no NiftyShield-specific tooling
   dependency: diff review → tests → structured commit message → stage/commit → confirm SHA (for `commit`); and a Tier-0-only protocol checklist (CONTEXT.md read, scope confirmed, plan + go-ahead,
   tests written, docs updated, commit + SHA confirmed) plus a plain-append `session_audit.jsonl` row with no external CLI dependency (for `session-close`).

**Tests:** none.

**Commit:** `docs(plan): concretize Tier 0 bootstrap file set`

---

## PTB-3 — Concretize Tier 1 (Recurring work)

**Files to change / create:**
- `docs/plan/project-template-blueprint/plan.md` — Tier 1 section.

**Before any code:** re-read `.claude/skills/work/SKILL.md`, `.claude/skills/new-story/SKILL.md` to identify exactly which lines are NiftyShield-specific (paths, project names, module lists) versus
mechanism. (`commit` and `session-close` moved to PTB-2, 2026-09-26 — both are Tier 0, not Tier 1.)

**What to implement:**

1. For each of `work` / `new-story`, produce a stripped/parameterized version (or a diff against the NiftyShield original) suitable for a new project.
2. Confirm `docs/plan/_TEMPLATE/` itself needs no changes (it's already project-agnostic scaffolding) — or note what, if anything, is NiftyShield-specific in it.
3. State the concrete trigger for adding `DECISIONS.md` and `TODOS.md` ("on the first real architecture decision" / "on the first backlog item" — confirm this is precise enough to act on, not just a
   slogan).

**Tests:** none.

**Commit:** `docs(plan): concretize Tier 1 recurring-work skill set`

---

## PTB-4 — Concretize Tier 2/3 gating + model-routing buckets

**Files to change / create:**
- `docs/plan/project-template-blueprint/plan.md` — Tier 2, Tier 3, and model-routing sections.

**Before any code:** re-read `.claude/skills/protocol-reference/SKILL.md` §3 (existing job-type → surface/model routing) to generalize its shape rather than reinvent one.

**What to implement:**

1. Write a concrete checklist (not prose) for "does this decision warrant Tier 2's council protocol" — reuse the existing three-condition test (load-bearing + two defensible approaches + spans
   disciplines) and add the size-independent framing from discussion (TaxCalculation's bracket logic as the worked example).
2. Write a concrete threshold for Rule 0 graph-tooling adoption (a rough LOC/file-count heuristic, or a behavioral one — "you're doing more lookups than reads").
3. Name what goes in each of the three generalized model-routing buckets (mechanical/bulk, design/judgment, independent verification), and state explicitly that a Tier 0/1 project should use one model
   for everything until this tier is warranted.
4. Note domain-specific AutoTrigger agents (NiftyShield's `greeks-analyst`/`roll-validator`) are per-project additions, never part of the portable set — only the table *mechanism* travels.

**Tests:** none.

**Commit:** `docs(plan): concretize Tier 2/3 gating and model-routing buckets`

---

## PTB-5 — Distribution mechanism + handoff

**Files to change / create:**
- `docs/plan/project-template-blueprint/plan.md` — final "Distribution" section.
- `DECISIONS.md` — record the distribution-mechanism decision.
- A new `docs/plan/<slug>/` story (slug TBD at authoring time) scoped to actually building the template repo, linked from this story's `plan.md`.

**Before any code:** none.

**What to implement:**

1. Confirm (does not re-litigate, just confirms) the template-repo-not-submodule-not-package conclusion from discussion, or record why it changed.
2. Decide where the template repo itself lives (a new local path, a GitHub template repository, or something else) — this is a real open decision, not assumed.
3. Scaffold the follow-on story via `/new-story` and link it from this story's `plan.md` and `DECISIONS.md`.
4. Follow §Conventions *Completion → archive* for this story once linked.

**Tests:** none.

**Commit:** `docs(plan): record template distribution decision; hand off to build story`


# Cross-Project Claude Template Blueprint — story specs

> One task per session. Find the first unchecked item in `tasks.md`. That is your only task. No task here touches NiftyShield `src/`/`scripts/` — no graph queries needed, no NiftyShield tests, no
> code-reviewer gate. PTB-5 onward write files into `/Users/abhadra/myWork/myCode/AI/project-scaffold/` (its own git repo — commit there too, and record that SHA in `plan.md` §Status); their "tests"
> are `scaffold.sh` runs against a scratch destination, spelled out per task. After each task: set `SHA:` on the task line + tick the box, update the story status summary, add one line to `TODOS.md`.
> See `docs/plan/README.md` §Conventions.

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

## PTB-5 — Distribution decision + `scaffold.sh` per-item selection and merge mechanics

> Re-scoped 2026-09-26. Originally "decide distribution; hand off template-repo build to a new story." The repo already exists and is committed (`project-scaffold`, `2e0c667` / `ebd0e8b`), so there is
> nothing to hand off — the remaining build work is PTB-6..PTB-9 inside this story. This task now owns the two structural problems PTB-4 surfaced (`plan.md` §"What `tier2/` and `tier3/` will hold"),
> because every later task writes files in the shape this one defines.

**Files to change / create:**
- `project-scaffold/scaffold.sh` — commit the current untracked version first, unchanged, as a baseline; then rewrite.
- `project-scaffold/tier0/CLAUDE.md` — add named insertion markers where later pieces' fragments land.
- `project-scaffold/tier2/`, `project-scaffold/tier3/` — restructure into per-piece folders (empty placeholders are fine; content is PTB-7/PTB-8).
- `docs/plan/project-template-blueprint/plan.md` — "Distribution" section finalized; stale bits reconciled (see step 1).
- `DECISIONS.md` — the distribution decision.

**Before any code:** read `plan.md` §"Distribution mechanism", §"Flatten-at-copy-time semantics", §"Validation script", and §"What `tier2/` and `tier3/` will hold" (the two structural problems). Read
the current `scaffold.sh` in full.

**What to implement:**

1. **Distribution decision.** Confirm (do not re-litigate) copy-once template repo, not submodule, not package. Decide with Animesh: does `project-scaffold` get a GitHub remote (and is it marked a
   GitHub template repository), or stay local-only for now? Reconcile `plan.md`'s stale mechanism text — it still names `py-project-tier0` and a `python -m scripts.dev.new_project_from_tier0` script
   that were superseded by `project-scaffold` + `scaffold.sh`. Record the decision in `DECISIONS.md`.
2. **Per-piece layout.** Tier 0 stays one folder (always applied); Tier 1 stays one folder (one question: "is there a backlog / second deferred piece of work yet?"). Tier 2 becomes `tier2/stakes/`,
   `tier2/test-runner/`, `tier2/multi-surface/`; Tier 3 becomes `tier3/rule0/`, `tier3/md-organize/`, `tier3/state-freshness/`, `tier3/weekly-audit/`. `python/` (PTB-6) is one more piece at root.
3. **Per-piece selection.** Replace the numeric tier-level argument with one yes/no per piece, each question phrased as its `plan.md` trigger (for example 2a asks the two-box project-level check).
   Support a non-interactive form too (flags) so validation runs are scriptable. Keep the existing rules: refuse a non-empty destination unless `--force`; re-running only adds files that don't exist,
   never overwrites; no `git init`, no commit.
4. **Merge semantics** for the three shared files, decided and implemented:
   - `CLAUDE.md` — each piece ships `CLAUDE.fragment.md` (or similar) inserted at its named marker in the Tier 0 skeleton; a fragment already present is not inserted twice (re-run safety).
   - `.claude/settings.json` — each piece ships a settings fragment; hook arrays are merged per event/matcher, not replaced. Decide the tool: `jq` (external dependency) vs `python3` (already required
     by `python/` projects, but not by a non-Python one) vs plain-bash append — state the tradeoff and the choice.
   - `.gitignore` — pieces append lines; duplicates skipped.
5. **Validate** against a scratch destination (`/Users/abhadra/myWork/myCode/AI/_scratch_to_delete`, per `plan.md` §"Validation script"): Tier 0 only; Tier 0+1; Tier 0+1 plus a dummy Tier 2 and a
   dummy Tier 3 piece that each register one hook and one fragment — confirm the result has both hooks in valid JSON, both fragments in `CLAUDE.md` at their markers, and a second run changes nothing.

**Tests:** the validation runs in step 5; paste the key checks (JSON validity, fragment count, second-run no-op) into the session log line.

**Commit:** `project-scaffold`: `feat: per-piece scaffold selection with merged shared files`. NiftyShield: `docs(plan): PTB-5 distribution decision and scaffold mechanics`.

---

## PTB-6a — Concretize the `python/` overlay: file set + Python-gated hooks

> Split from the original PTB-6 (2026-09-26) after review surfaced that several hooks assumed "NiftyShield-specific" without checking their actual content — see PTB-6b for the half that turned out to
> be a Tier 1 gap instead. PTB-6a keeps everything that is genuinely gated on "this project is Python."

**Files to change / create:**
- `docs/plan/project-template-blueprint/plan.md` — new "Python overlay" section, replacing the "`python-addon/` deferred" note.
- `/Users/abhadra/myWork/myCode/AI/project-scaffold/python/` — the actual file set (renamed from the earlier `python-addon/` concept — not a bolt-on, it's the base Python project shape).
- `project-scaffold/scaffold.sh` — extend to overlay `python/` when selected, if placement makes that necessary.

**Before any code:** re-read `plan.md`'s "`python-addon/` deferred, not built yet" note (historical record of why this was pulled out of Tier 0) — do not re-derive that reasoning, just read it. Also
re-read NiftyShield's own current top-level layout as the worked example this generalizes from: `src/` (151 files, the production package), `scripts/` (106 files, entrypoints/CLIs), `tests/` (238
files), `data/`, `logs/`, `config/`, `.venv/` (gitignored, never committed), `pyproject.toml` + `requirements.txt` + `requirements-dev.txt`, `.pre-commit-config.yaml`, and `Makefile` (`test`, `lint`,
`fmt`, `security`, `ci`, `clean`, `help` targets — `coverage`'s `--cov-fail-under` threshold and the `index`/`dupes`/`dead-code` targets are project-specific or Tier-3-scoped, not carried over as-is).

**Decisions already confirmed with Animesh (2026-09-26), do not re-litigate:**
- Dependency management: `requirements.txt` + `requirements-dev.txt`, matching NiftyShield's own convention — not a `pyproject.toml`-only dependency model.
- `logs/`: ships with a minimal `setup_logging()` stub (not just an empty gitignored folder), so every Python project starts with consistent log formatting from day one.
- `data/`: **conditional, not default** — only added when a project actually consumes/produces files (true for CardLedger's statement parsing; decide per-project otherwise). Do not ship it empty in
  every project.
- `src/`, `scripts/`, `tests/` — always ship, empty-but-present with a seeded `__init__.py` each (mirrors the "new Python package directory must include `__init__.py`" rule from NiftyShield's own
  `CLAUDE.md`).
- Pre-commit hooks, revised set (2026-09-26 session, superseding the original five-hook list — see the corrected reasoning below): `ruff`, `ruff-format`, `mypy`, `detect-secrets`, a generic test-gate
  hook that runs `pytest`, `bandit` (security scan — generic, not NiftyShield-specific, already a Makefile target), the two logging pygrep hooks (`no-script-main-logger`, `no-bare-logging` — generic
  Python logging hygiene enforcing use of this overlay's own `setup_logging()` stub, not a NiftyShield business rule), and `md-line-length`/`md-reflow` generalized to the whole tree (not
  `docs/plan`-scoped) — the *rule* was already Tier 0 text in `tier0/CLAUDE.md`'s "Markdown formatting" section; only the *enforcement script* was deferred, because it needs `python3` to run and Tier
  0 can't assume that. `check_story_structure`/`check_checkbox_consistency` are **not** part of this list — they check `docs/plan/` folder shape, a Tier 1 concept, not a Python concept; see PTB-6b.
- `Makefile`: generic targets ported (`test`, `test-serial`, `lint`, `fmt`, `security`, `ci`, `clean`, `help`); `coverage`'s pass threshold becomes a placeholder value, not NiftyShield's `80`; `index`
  (codebase-memory-mcp) stays out — that's Tier 3/`rule0` territory; `dupes`/`dead-code` (pylint-similarities, vulture) ship as advisory-only, commented-out targets, not active.
- Design principles: a compact 3-4 bullet addition to `tier0/CLAUDE.md`'s existing "Python conventions" section naming the concrete patterns this codebase validated — `Protocol`-based dependency
  injection (the `BrokerClient` pattern: depend on an interface, swap implementations for testing), frozen `dataclass`/Pydantic for immutable domain models, pure functions separated from I/O
  (`Store`/`Tracker` split). Not a general SOLID essay — `tier0/CLAUDE.md`'s own governing principle is to stay thin, and a generic design-patterns lecture doesn't change behavior the way naming
  concrete, enforced patterns does.

**What to implement:**

1. Decide placement: inside `tier0/` as a Python-specific sibling set, a separate `python/` folder at `project-scaffold/` root layered on top of whichever tier is chosen, or something else — state the
   reasoning, don't just restate the open question. (Given `python/` is orthogonal to the tier axis — a Tier 0 project can be Python or not — a root-level sibling overlay, not nested inside a tier, is
   the likely answer; confirm or override this with reasoning.)
2. Write the concrete file set per the confirmed decisions above: `src/`, `scripts/`, `tests/` (each with a seeded `__init__.py`), `logs/` + a minimal `setup_logging()` stub, `pyproject.toml`,
   `requirements.txt` + `requirements-dev.txt`, `.pre-commit-config.yaml` (the revised hook list above), `Makefile`, and a `.gitignore` addition for `.venv/`. `data/` is documented as an optional
   add-on, not scaffolded by default. Add the design-principles bullets to `tier0/CLAUDE.md`'s "Python conventions" section (not a new doc).
3. Validate the `python/` file set on its own: run `scaffold.sh` with a manual copy of `python/` (no interactive question yet) against a scratch destination and confirm the result is a working
   `pyproject.toml`-rooted Python project layout with no leftover placeholder folder names, mirroring the flatten-at-copy-time semantics already established for tier0/tier1. Do this **before** step 4
   — the file set must be right before wiring a question around it.
4. **Only once step 3 validates cleanly:** add `python/` as one more piece in PTB-5's per-piece selection ("Is this a Python project?"), flattened like every other piece. PTB-5 now lands first, so use
   its mechanism — no standalone fallback flag. `python/`'s `.venv/`/`__pycache__/` ignore lines go through PTB-5's `.gitignore` merge, and any Python-specific `CLAUDE.md` guidance (type hints, `(str,
   Enum)`, opt-in `Decimal` note) ships as a fragment at its marker, not as edits to `tier0/CLAUDE.md`.
5. Re-validate: run the updated `scaffold.sh` end-to-end (tier selection + Python question) against a fresh scratch destination and confirm a clean, flat, correctly-conditional result (`data/` absent
   unless something in the answers calls for it).

**Tests:** none (docs/config only; no NiftyShield `src/`/`scripts/` code changes).

**Commit:** `docs(plan): concretize python overlay`

---

## PTB-6b — Wire `docs/plan/` structure-enforcement hooks into Tier 1

> Split from the original PTB-6 (2026-09-26). `check_story_structure.py` and `check_checkbox_consistency.py` were originally assumed to be NiftyShield-specific and excluded from the overlay entirely;
> on inspection neither references NiftyShield's domain — they enforce the `docs/plan/` folder shape (`prompt.md`/`tasks.md`/`stories.md`) that Tier 1's own `_TEMPLATE` already ships. PTB-3
> (2026-09-26) narrowed Tier 1's scope to just the `work`/`new-story` skills and never carried these two hooks over — this task closes that gap.

**Files to change / create:**
- `project-scaffold/tier1/.claude/hooks/` (new) — `check_story_structure.py`, `check_checkbox_consistency.py`, generalized.
- `project-scaffold/tier1/.claude/settings.fragment.json` (new, Tier 1 currently ships no settings fragment) — registers both as pre-commit-equivalent hooks per PTB-5's merge mechanism.
- Possibly `project-scaffold/tier1/docs/plan/README.md` skeleton, if the scaffolded `_TEMPLATE` doesn't already carry a `§Conventions` section the hooks' error messages can point to — decide during
  implementation, don't assume either way.

**Before any code:** read `scripts/dev/hooks/check_story_structure.py` and `scripts/dev/hooks/check_checkbox_consistency.py` in full (NiftyShield originals) and `docs/plan/README.md` §Conventions (the
doc they enforce). Confirm `project-scaffold/tier1/docs/plan/_TEMPLATE/` already matches the shapes these scripts check (story folder = `prompt.md`+`tasks.md`+`stories.md`; epic folder =
`prompt.md`+`README.md`+sub-folders) before porting — if it doesn't, that mismatch is a bug to fix, not something to route around.

**What to implement:**

1. Port both scripts, stripping NiftyShield-specific content: `_LEGACY_ALLOWLIST` (session-specific grandfathering, not portable), the `RDO-15`/`SWEEP-4` convention references in comments, and any
   hardcoded review-agent names (`code-reviewer`/`greeks-analyst`/`roll-validator`) in `check_checkbox_consistency.py`'s tail-format check — replace with a generic placeholder the operator fills in,
   or make the review-agent field free-form.
2. Same hook-language-dependency note as PTB-7/PTB-8: both scripts need `python3`. State explicitly that Tier 1 is not gated on Python being confirmed (a non-Python project can still use
   `docs/plan/`), so this is a soft dependency on `python3` being present — acceptable since it's near-universal on the platforms this scaffold targets, but call it out rather than silently assuming.
3. Wire both into `tier1/.claude/settings.fragment.json` following PTB-5's hook-array-merge shape, and into a `CLAUDE.fragment.md` note under Tier 1 if one doesn't already reference `docs/plan/`
   conventions.
4. Validate: scaffold Tier 0+1 only (no `python/` piece) against a fresh scratch destination; confirm both hooks run cleanly (via `python3 <hook> --staged` or equivalent) against the freshly
   scaffolded `docs/plan/_TEMPLATE/` with zero findings, and that a deliberately malformed story folder trips `check_story_structure` correctly.

**Tests:** step 4 validation.

**Commit:** `docs(plan): PTB-6b wire docs/plan hooks into Tier 1`

---

## PTB-7 — Write Tier 2 into `project-scaffold`

**Files to change / create:** `project-scaffold/tier2/{stakes,test-runner,multi-surface}/` — the file list in `plan.md` §"What `tier2/` and `tier3/` will hold", in PTB-5's fragment shape.

**Before any code:** read `plan.md` §"The enforcement lesson" and §"Tier 2 — gating, concretely" (what each piece is for and which hook it travels with). Read each NiftyShield source file before
porting it: `.claude/agents/code-reviewer.md`, `.claude/agents/test-runner.md`, `REVIEW.md`, `docs/council/README.md` + its `_TEMPLATE`, `.claude/hooks/council_check.sh`,
`.claude/hooks/inline_full_suite.sh`, `.claude/skills/handoff-antigravity/SKILL.md`, `ANTIGRAVITY.md`, `AGENTS.md`, and `CLAUDE.md` Step 2b / Step 3b / the AutoTrigger table.

**What to implement:**

1. **`stakes/`**: generic `code-reviewer` agent (type hints, error handling, hygiene — every Decimal / BrokerClient / Greeks check removed); `REVIEW.md` skeleton (general Python-hygiene section kept
   only as a clearly marked Python-only block, or moved to `python/` — decide); `docs/council/README.md` + `_TEMPLATE` genericized (no NiftyShield models, templates, or topics); `council_check.sh`
   printing the four-box per-decision checklist from `plan.md`; `CLAUDE.md` fragment with Step 2b and an AutoTrigger table holding only the generic rows plus a commented example row showing how a
   project adds its own domain reviewer ("one reviewer per 2a computation, path-triggered").
2. **`test-runner/`**: `test-runner` agent with the test command left as a placeholder (not hardcoded `pytest`); `inline_full_suite.sh`.
3. **`multi-surface/`**: `handoff-antigravity` skill (four mandatory elements, content injected inline); `ANTIGRAVITY.md` and `AGENTS.md` templates (`AGENTS.md` as a mirror of `CLAUDE.md`, never a
   stub); Step 3b fragment.
4. **Hook language dependency.** NiftyShield's `inline_full_suite.sh` shells out to `scripts/dev/hooks/check_inline_full_suite.py`. The scaffold is language-agnostic, so each hook must be
   self-contained bash, or clearly require `python3` and ship its helper inside the piece. Pick per hook and state why.
5. Validate: scaffold with all three pieces selected; `grep -ri 'niftyshield\|greeks\|broker\|nifty'` returns nothing; `settings.json` parses; every registered hook path exists and is executable.

**Tests:** step 5 validation.

**Commit:** `project-scaffold`: `feat(tier2): add stakes, test-runner, and multi-surface pieces`. NiftyShield: `docs(plan): PTB-7 tier 2 written to project-scaffold`.

---

## PTB-8 — Write Tier 3 into `project-scaffold`

**Files to change / create:** `project-scaffold/tier3/{rule0,md-organize,state-freshness,weekly-audit}/`, in PTB-5's fragment shape.

**Before any code:** read `plan.md` §"Tier 3 — gating, concretely". Read each NiftyShield source before porting: `.claude/hooks/{guard_src_reads,repeat_read,wide_grep,state_doc_freshness}.sh`,
`scripts/dev/hooks/{check_repeat_read,check_wide_grep}.py`, `scripts/dev/graph_snippet.py`, `.claude/skills/{md-organize,weekly-audit}/SKILL.md`, `CONTEXT_TREE.md` (shape only), and `CLAUDE.md` Rule 0
/ the Rule 1 grep row.

**What to implement:**

1. **`rule0/`**: `guard_src_reads.sh`, `repeat_read.sh`, `wide_grep.sh` with the source directories made configurable (not hardcoded `src/`/`scripts/`); the `graph_snippet` wrapper as a standalone
   script (it is currently a NiftyShield `scripts.dev` module); `CONTEXT_TREE.md` skeleton; Rule 0 `CLAUDE.md` fragment with the `codebase-memory-mcp` project id left as a placeholder the operator
   fills in.
2. **`md-organize/`**: skill genericized to "any root doc over ~400 lines", `docs/archive/` with its dated-snapshot convention.
3. **`state-freshness/`**: `state_doc_freshness.sh` with the per-doc threshold list moved to a small config the project edits, seeded with Tier 0/1 docs only.
4. **`weekly-audit/`**: skill genericized, on-demand only.
5. Same hook-language rule as PTB-7 step 4. Same validation as PTB-7 step 5, with all four Tier 3 pieces selected on top of Tier 0+1+2.

**Tests:** step 5 validation.

**Commit:** `project-scaffold`: `feat(tier3): add rule0, md-organize, state-freshness, weekly-audit`. NiftyShield: `docs(plan): PTB-8 tier 3 written to project-scaffold`.

---

## PTB-9 — Self-documenting `project-scaffold`, end-to-end validation, archive

**Files to change / create:**
- `project-scaffold/README.md` (new, repo root — not copied into consuming projects).
- `project-scaffold/tier0/` — a compact trigger list shipped into every scaffolded project (file name decided here; likely `TIERS.md` plus one pointer line in the `CLAUDE.md` skeleton).
- `docs/plan/project-template-blueprint/plan.md` — final status; pointer to where the guide now lives.
- Story archive per §Conventions *Completion → archive*.

**Before any code:** read `plan.md` in full — it is the source being ported.

**What to implement:**

1. **`project-scaffold/README.md`**: what the repo is, how to run `scaffold.sh` (interactive and flag forms), and the full guide ported from `plan.md`: governing principle, per-piece triggers (Tier 1
   triggers, 2a two-box project check + four-box per-decision check, 2b trigger, test-runner trigger, Tier 3 threshold table), the enforcement rule, model-routing buckets, the scratch/tmp split, the
   architecture-doc trio. Strip NiftyShield history and SHAs — keep the reasoning, drop the provenance (`plan.md` stays the provenance record in NiftyShield's archive).
2. **Shipped trigger list**: a scaffolded project must be able to tell, on its own, when to re-run `scaffold.sh` for the next piece. Keep it short (one line per piece: trigger → what to add); the
   resident `CLAUDE.md` carries only a one-line pointer to it.
3. **Open questions**: resolve each remaining one in `plan.md` §"Open questions" with Animesh, or carry it into the README as explicitly open.
4. **End-to-end validation**, three reference configurations into fresh scratch destinations: (a) plain Tier 0, non-Python; (b) CardLedger-shaped — Tier 0 + 1 + `python/` + `data/`; (c)
   TaxCalculation-shaped — Tier 0 + 1 + `python/` + 2a `stakes/`. For each: no NiftyShield references, `settings.json` valid, hooks executable, `CLAUDE.md` fragments at their markers, re-run is a
   no-op.
5. Animesh confirms `project-scaffold` is ready to use. Then archive this story.

**Tests:** step 4 validation.

**Commit:** `project-scaffold`: `docs: add scaffold guide and shipped trigger list`. NiftyShield: `docs(plan): close project-template-blueprint and archive`.

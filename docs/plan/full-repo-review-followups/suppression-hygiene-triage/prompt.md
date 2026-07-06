Read `CONTEXT.md` and state `CONTEXT.md ✓` before doing anything else. Then read
`docs/plan/full-repo-review-followups/suppression-hygiene-triage/tasks.md` and find the first unchecked box. That is your
**only task** for this session. Do not look at any other unchecked item. One task.
Complete it fully. Stop.

**Origin:** Spawned from `docs/plan/full-repo-review/findings/FR-7_synthesis.md` (Chairman
Synthesis), FR-7 row 10 (ERROR, downgraded from FR-4's CRITICAL per FR-7 divergence D2) — FR-4 §3, §4. Independently re-verified against the live repo before this story was
created — see FR-9's commit message for the verification method.

26/26 `# type: ignore` and 80/89 `# noqa` suppressions lack the explanatory comment REVIEW.md's meta-rule mandates; 2 literal `assert`s exist in `src/` (G6 violation); 183 `except Exception` sites are only partially audited (10+ confirmed bare, no intent comment). FR-4 rated this CRITICAL per the letter of the rule; FR-7's chairman downgrades to ERROR because most bare `E402`/`F401` codes are self-describing and the load-bearing fix is a REVIEW.md policy carve-out, not 100+ mechanical comment additions — triage, not blanket-fix.

**Pre-implementation gate:** State in one sentence which task, which files, which test file.
Do not write any code until this plan is stated.

**Story spec:** Read the matching story in `docs/plan/full-repo-review-followups/suppression-hygiene-triage/stories.md` for the full spec.

**Graph-before-Read rule:** Never call `Read` on `src/` or `scripts/` without first using the
graph. Order: `git log --oneline -10 <file>` → `search_graph`/`get_code_snippet` →
`trace_path` → `search_code` → `sed -n` → `Read` (state why the graph was
insufficient).

**Before writing any test helper that constructs a domain model:** run
`get_code_snippet('<ModelClassName>')` and `search_graph('<EnumName>')` first — never write
a `_make_*`/`build_*` fixture helper from memory.

**Test gate — blocking:**
`python -m pytest tests/unit/ --tb=no -q`
All must be green before committing.


**Commit:** Use format from `.claude/skills/commit/SKILL.md`. Execute the commit — do not
draft it.

**Verify and record:** Tick `tasks.md`, append `| SHA: <sha>`. Add one line to `TODOS.md`.

**Stop.** Do not proceed to the next unchecked item.

Read `CONTEXT.md` and state `CONTEXT.md ✓` before doing anything else. Then read
`docs/plan/full-repo-review-followups/protocol-standards-reconciliation/tasks.md` and find the first unchecked box. That is your
**only task** for this session. Do not look at any other unchecked item. One task.
Complete it fully. Stop.

**Origin:** Spawned from `docs/plan/full-repo-review/findings/FR-7_synthesis.md` (Chairman
Synthesis), FR-7 rows 4, 5, 11 (CRITICAL + ERROR) — FR-1 F-C1, F-C2, F-E1, F-E2, F-E3. Independently re-verified against the live repo before this story was
created — see FR-9's commit message for the verification method.

Three protocol-layer contradictions confirmed live: (1) root CLAUDE.md's AutoTrigger table states `test-runner`/`code-reviewer` are "Blocking? Yes" and "not optional", but `ANTIGRAVITY.md` line 91 states Antigravity "cannot spawn Claude agents" and must instead emit an await-signal and hand control to a human — the root doc's absolute rule has no branch for a surface that structurally cannot satisfy it, which feeds the documented "commit drafted but not executed" failure mode. (2) Module CLAUDE.md files (`src/notifications/`, `src/dhan/`, `src/nuvama/`, `src/mf/`) mandate broad `except Exception` catches as a design requirement, and `src/paper/CLAUDE.md` describes the `total_pnl` invariant using the word "asserts" (confirmed at line 74) — but REVIEW.md G5 (line 704) and G6 (line 725) rate both patterns CRITICAL for new code without an inline intent comment / without being a real exception raise. An agent writing new code faithfully to the module spec produces code a literal REVIEW.md application blocks. (3) Three smaller ambiguities: Step 3 vs Step 3b routing is silent on ≤2-file tasks; Step 2b's mechanism is described three different, non-cross-referenced ways (CLAUDE.md body / AutoTrigger row / ai_collaboration_plan.md); "code" is undefined at the code-reviewer trigger boundary while ANTIGRAVITY.md scopes it precisely to `.py` in `src/scripts/tests`.

**Pre-implementation gate:** State in one sentence which task, which files, which test file.
Do not write any code until this plan is stated.

**Story spec:** Read the matching story in `docs/plan/full-repo-review-followups/protocol-standards-reconciliation/stories.md` for the full spec.

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

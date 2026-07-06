Read `CONTEXT.md` and state `CONTEXT.md ✓` before doing anything else. Then read
`docs/plan/full-repo-review-followups/docs-navigation-and-staleness/tasks.md` and find the first unchecked box. That is your
**only task** for this session. Do not look at any other unchecked item. One task.
Complete it fully. Stop.

**Origin:** Spawned from `docs/plan/full-repo-review/findings/FR-7_synthesis.md` (Chairman
Synthesis), FR-7 rows 3, 8, 14 (CRITICAL + ERROR) — FR-3 F1, FR-1 F-E6/F12a/F12b, FR-3 F5, FR-3.1 F10, FR-3 F2. Independently re-verified against the live repo before this story was
created — see FR-9's commit message for the verification method.

Three converging staleness issues in the docs layer, all root-caused by FR-7 row 15 (docs/plan/README.md not in Step 5a's mandatory update list): (1) `docs/plan/README.md`'s status table shows `dev-foundation`, `council-refactor`, `paper-backbone`, `ic-nifty-v2` as "Not started" when DECISIONS.md and `docs/archive/plan/` confirm all four are shipped/archived. (2) `docs/council/README.md` declares a taxonomy (`docs/council/archive/{strategy,risk,research}/`, 3 subfolders) that hasn't existed since commit `da93b64` moved the tree to `docs/archive/council/{strategy,risk,research,data_architecture,misc}/` (5 subfolders, different prefix) — this breaks two confirmed dead links: `docs/plan/variance-gate/prompt.md:18` and, more seriously, `DECISIONS.md` lines 397-407 which cite the dead `docs/council/2026-05-28_paper-trade-exit-philosophy.md` as the source of record for live CSP/CC/PP/collar exit thresholds (content was also revised 2026-06-26 — a reader following the dead link could land on a superseded version). (3) `CONTEXT.md` still claims `src/nuvama/CLAUDE.md` doesn't exist (it does, 47 lines).

**Pre-implementation gate:** State in one sentence which task, which files, which test file.
Do not write any code until this plan is stated.

**Story spec:** Read the matching story in `docs/plan/full-repo-review-followups/docs-navigation-and-staleness/stories.md` for the full spec.

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

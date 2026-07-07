Read `CONTEXT.md` and state `CONTEXT.md ✓` before doing anything else. Then read
`docs/plan/full-repo-review-followups/paper-pnl-golden-tests/tasks.md` and find the first unchecked box. That is your
**only task** for this session. Do not look at any other unchecked item. One task.
Complete it fully. Stop.

**Origin:** Spawned from `docs/plan/full-repo-review/findings/FR-7_synthesis.md` (Chairman
Synthesis), FR-7 row 13 (ERROR) — FR-5 PNL-1. Independently re-verified against the live repo before this story was
created — see FR-9's commit message for the verification method.

`_compute_leg_unrealized_pnl`'s targeted property-test file (`tests/unit/test_pnl_hypothesis.py`) has no golden (exact-value) assertion — only property-based (magnitude-preserving) tests, which pass even for a sign-flip bug. Currently mitigated one layer up by golden tests in `test_tracker.py`, but the unit closest to the math is not self-verifying.

**Surface & Model: Claude Code, Sonnet.** Requires `get_code_snippet('_compute_leg_unrealized_pnl')` mid-implementation to confirm the exact signature and sign convention before writing the fixture — Step 3b's explicit third Claude-routing criterion ("any task requiring graph queries mid-implementation to resolve ambiguity"). A cold Antigravity handoff has no live graph-MCP session to run that query against.

**Pre-implementation gate:** State in one sentence which task, which files, which test file.
Do not write any code until this plan is stated.

**Story spec:** Read the matching story in `docs/plan/full-repo-review-followups/paper-pnl-golden-tests/stories.md` for the full spec.

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

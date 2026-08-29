Read `CONTEXT.md` and state `CONTEXT.md ✓` before doing anything else. Then read
`docs/plan/full-repo-review-followups/portfolio-pnl-critical-fix/tasks.md` and find the first unchecked box. That is your
**only task** for this session. Do not look at any other unchecked item. One task.
Complete it fully. Stop.

**Origin:** Spawned from `docs/plan/full-repo-review/findings/FR-7_synthesis.md` (Chairman
Synthesis), FR-7 row 1 (CRITICAL) — FR-2 F1, F2. Independently re-verified against the live repo before this story was
created — see FR-9's commit message for the verification method.

Reconciliation against the live `finideas_ilts` position surfaced two accounting bugs:
`src/portfolio/store.py::get_position()` returns `average_price = Decimal("0")` whenever `buy_qty == 0` (short-first legs —
sell-only trades never populate `buy_value`/`buy_qty`),
and `src/portfolio/tracker.py::apply_trade_positions()` drops legs with zero net quantity as "fully closed" with no realized-P&L capture anywhere in the function.
Both confirmed live: ₹52,318.50 of booked profit was invisible; open short PE P&L was wrong in sign and magnitude.
`src/paper/tracker.py` already has a working reference implementation (`_compute_realized_pnl_by_leg`, `_compute_realized_pnl`) that `src/portfolio/` should mirror.

**Surface & Model: Claude Code, Opus for implementation, real `@code-reviewer` mandatory.** Not an Antigravity handoff despite touching only 4 files:
mirroring `src/paper/tracker.py`'s realized-P&L pattern onto `src/portfolio/`'s different data model (`Position`/`Strategy`,
no `PaperTrade` equivalent) is an inline judgment call, not a mechanical port — Step 3b's "single/2-file task where judgment calls are likely" spirit applies even at 4 files here.
This is also a financial-logic commit (P&L, real capital) —
per CLAUDE.md's AutoTrigger rules
and FR-1's F-C1, the real `@code-reviewer` gate cannot be satisfied by Antigravity in-process, so routing here through Antigravity would just bounce back to Claude Code for the gate anyway.

**Pre-implementation gate:** State in one sentence which task, which files, which test file.
Do not write any code until this plan is stated.

**Story spec:** Read the matching story in `docs/plan/full-repo-review-followups/portfolio-pnl-critical-fix/stories.md` for the full spec.

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

**Financial logic commit — real `@code-reviewer` subagent mandatory** per CLAUDE.md's Agent AutoTrigger Rules (this touches P&L / Decimal / broker-adjacent paths).
Resolve any CRITICAL/ERROR finding before committing.

**Commit:** Use format from `.claude/skills/commit/SKILL.md`. Execute the commit — do not
draft it.

**Verify and record:** Tick `tasks.md`, append `| SHA: <sha>`. Add one line to `TODOS.md`.

**Stop.** Do not proceed to the next unchecked item.

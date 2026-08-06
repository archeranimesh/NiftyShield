Read `CONTEXT.md` and state `CONTEXT.md ✓` before doing anything else. Then read
`docs/plan/execution-risk-hardening/tasks.md` and find the first unchecked box. That is your
**only task** for this session. Do not look at any other unchecked item. One task. Complete it
fully. Stop.

**Full spec for each task is inline in `tasks.md`** — no separate `stories.md` for this story.

**Council checkpoint (mandatory for RH-1):** before stating the implementation plan, check
whether the atomicity/compensation design decision qualifies for a council call per
`docs/council/README.md`'s three-condition test. If yes, surface the decision, draft the
council question, and wait for the council output before writing code.

**Graph-before-Read rule:** Never call `Read` on `src/` or `scripts/` without first using the
graph. Order: `git log` → graph query (`search_graph`/`get_code_snippet`/`trace_path`) →
`search_code` → `sed -n` → `Read` (state why the graph was insufficient).

**RH-1 must not ship without resolving the atomicity gap** — a naked short with no offsetting
hedge is a real capital-risk bug once this path sizes real money, not just bookkeeping.

**RH-2 and RH-3 may resolve to "already done" or "no change needed"** — verify against the
current codebase before assuming the TODOS.md description is still accurate; both items were
written against an earlier state of `src/strategy/`.

**Test gate — blocking (RH-1, RH-2 only):**
`python -m pytest tests/unit/ --tb=no -q`
All must be green before committing. No network in tests.

**Financial logic note:** RH-1 touches live order/entry sequencing — the real `@code-reviewer`
gate is mandatory per project protocol, even if this surface can't spawn it (state the
substitution used).

**Commit:** Use format from `.claude/skills/commit/SKILL.md`. Execute the commit — do not draft it.

**Verify and record:** Tick `tasks.md`, append `| SHA: <sha>`. Add one line to `TODOS.md`.

**Stop.** Do not proceed to the next unchecked item.

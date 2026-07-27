Read `CONTEXT.md` and state `CONTEXT.md ✓` before doing anything else. Then read
`docs/plan/monitor-and-close-hardening/tasks.md` and find the first unchecked box. That is your
**only task** for this session. Do not look at any other unchecked item. One task. Complete it
fully. Stop.

**Full spec for each task is inline in `tasks.md`** — no separate `stories.md` for this story;
the grouped items are small enough to spec directly in the checklist.

**Graph-before-Read rule:** Never call `Read` on `src/` or `scripts/` without first using the
graph. Order: `git log` → graph query (`search_graph`/`get_code_snippet`/`trace_path`) →
`search_code` → `sed -n` → `Read` (state why the graph was insufficient).

**Before writing any test helper that constructs a domain model:** run
`get_code_snippet('<ModelClassName>')` first.

**MC-2 is an audit, not a code fix** — do not write a source-code diff for it unless the audit
turns up a real missed exit signal, in which case stop, open a new bug entry, and treat the fix
as its own separate task rather than bundling it into MC-2's commit.

**MC-3 may be too large for one session** — if `search_graph` shows no reusable strike-selection
primitive exists for the replacement leg, stop and flag it for further scoping rather than
inventing new strike-selection logic inline.

**Test gate — blocking:**
`python -m pytest tests/unit/ --tb=no -q`
All must be green before committing. No network in tests.

**Financial logic note:** MC-3 and MC-4 touch live P&L/position-close paths — the real
`@code-reviewer` gate is mandatory for those two per project protocol, even if this surface
can't spawn it (state the substitution used, same as prior sessions in this repo).

**Commit:** Use format from `.claude/skills/commit/SKILL.md`. Execute the commit — do not draft it.

**Verify and record:** Tick `tasks.md`, append `| SHA: <sha>`. Add one line to `TODOS.md`.

**Stop.** Do not proceed to the next unchecked item.

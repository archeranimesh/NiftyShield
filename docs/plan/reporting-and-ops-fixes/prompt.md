Read `CONTEXT.md` and state `CONTEXT.md ✓` before doing anything else. Then read
`docs/plan/reporting-and-ops-fixes/tasks.md` and find the first unchecked box. That is your
**only task** for this session. Do not look at any other unchecked item. One task. Complete it
fully. Stop.

**Full spec for each task is inline in `tasks.md`** — no separate `stories.md` for this story;
the grouped items are unrelated small fixes bundled purely to avoid directory proliferation.

**Graph-before-Read rule:** Never call `Read` on `src/` or `scripts/` without first using the
graph. Order: `git log` → graph query (`search_graph`/`get_code_snippet`/`trace_path`) →
`search_code` → `sed -n` → `Read` (state why the graph was insufficient).

**Before writing any test helper that constructs a domain model:** run
`get_code_snippet('<ModelClassName>')` first.

**RO-3 and RO-5 are docs-only** — no code-reviewer gate, no test gate, targeted `Edit` only.

**RO-4 is operational, not code** — it may not be completable from a sandbox session without
live cron/host access; if so, flag it for Animesh rather than attempting a workaround.

**Test gate — blocking (RO-1, RO-2 only):**
`python -m pytest tests/unit/ --tb=no -q`
All must be green before committing. No network in tests.

**Commit:** Use format from `.claude/skills/commit/SKILL.md`. Execute the commit — do not draft it.

**Verify and record:** Tick `tasks.md`, append `| SHA: <sha>`. Add one line to `TODOS.md`.

**Stop.** Do not proceed to the next unchecked item.

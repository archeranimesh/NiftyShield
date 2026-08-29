Read `CONTEXT.md` and state `CONTEXT.md ✓` before doing anything else. Then read
`docs/plan/full-repo-review-followups/sqlite-backup-cron/tasks.md` and find the first unchecked box.
That is the only task for this session.

**This story is routed to Antigravity (see "Surface & Model" below for why).** Per CLAUDE.md
Step 3b: do not write any code yourself. Invoke the `handoff-antigravity` skill now and
produce the structured handoff prompt containing the four mandatory elements
(`ai_collaboration_plan.md` §4):
1. **Reading list** — explicit `view_file` paths, `CONTEXT.md` mandatory plus this story's
   `stories.md`.
2. **Objective** — one sentence, drawn from the first unchecked box in `tasks.md`.
3. **Pointers** — explicit file paths / graph queries from this story's `stories.md`. Do not
   rely on Antigravity to discover scope on its own.
4. **Boundaries** — Do not touch `data/portfolio/portfolio.sqlite` itself except through the read-only `.backup` API — no writes, no schema changes.
   Do not touch any file outside `scripts/portfolio/` and its test file.

Then stop. Do not proceed to implementation.

**When Antigravity returns its Phase Completion Output:** verify `files_changed` against
`git diff --name-only HEAD~1`, `tests_passing` against `pytest --tb=no -q`'s summary line, and
— the load-bearing check — that `commit_sha` matches `git log --oneline -1`. If all three
check out, tick `tasks.md`, append `| SHA: <sha>`, add one line to `TODOS.md`, stop. If
verification fails, open a fix session with the failure details per Step 3b — if the fix
needs the `code-reviewer`/`test-runner` AutoTrigger gates, run those yourself in Claude Code
rather than re-handing to Antigravity (FR-1 F-C1: Antigravity cannot spawn those subagents).

**Origin:** Spawned from `docs/plan/full-repo-review/findings/FR-7_synthesis.md` (Chairman
Synthesis), FR-7 row 2 (CRITICAL) — FR-6 S-4. Independently re-verified against the live repo before this story was
created — see FR-9's commit message for the verification method.

No backup mechanism of any kind exists for `data/portfolio/portfolio.sqlite` — the single store of record for all trade history, paper P&L, approvals, and risk state.
Confirmed: no `backup` reference anywhere in `scripts/`, no crontab entry, no doc. The DB also sits on a FUSE-artifact-littered mount, raising torn-copy risk for any naive `cp`-based backup.

**Surface & Model: Antigravity (handoff via the `handoff-antigravity` skill);
Claude Code / Sonnet for the review half.** Textbook Step 3b Antigravity case —
new script, mechanical once scoped (`sqlite3.Connection.backup()` + retention pruning), non-ambiguous spec, no real-time design decisions.
Claude verifies SHA + test count per Step 3b before closing the phase.

**Story spec:** Read the matching story in `docs/plan/full-repo-review-followups/sqlite-backup-cron/stories.md` for the full spec.

**Commit:** Antigravity executes the commit as part of its own protocol (per
`ai_collaboration_plan.md`) — Claude does not draft or run a separate commit for this story.

**Stop.** Do not proceed to the next unchecked item.

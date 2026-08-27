# Session Efficiency Suggestions — Ranked by Recurrence

> Maintained by `.claude/skills/session-close/SKILL.md` Step 4b. `Count` = number of sessions
> where this exact root cause recurred, i.e. how many times fixing it would have helped — not
> a bug tracker. Sorted by `Count` descending. Do not hand-edit `Count`; the skill owns it.

| Count | Slug | Suggestion | Category | First seen | Last seen | Example |
|---|---|---|---|---|---|---|
| 1 | scheduleWakeup-poll-spawned-agent | Don't call `ScheduleWakeup` to poll for a subagent you spawned — harness-tracked work re-invokes you automatically via task-notification on completion; polling wastes a turn and reloads per-turn hook overhead for nothing. | token-efficiency | 2026-08-27 | 2026-08-27 | ROLL-4 session — polled twice for the code-reviewer subagent instead of just ending the turn |
| 1 | pytest-inlined-not-test-runner | Spawn the `test-runner` (Haiku) subagent for the post-edit test run instead of running `pytest` inline in the main session's context. | agent-routing | 2026-08-27 | 2026-08-27 | ROLL-4 session — ran `python -m pytest tests/unit/ --tb=no -q` directly via Bash |
| 1 | context-md-full-sequential-read | Grep `CONTEXT.md` for the task's module/keyword first instead of a blind sequential `Read` from the top — the file is dense enough that a single unscoped read can hit the display token cap before reaching the relevant section. | token-efficiency | 2026-08-27 | 2026-08-27 | ROLL-4 session — first `Read` on CONTEXT.md hit the 25K-token cap at 31/157 lines |
| 1 | sequential-tasks-md-reads | Batch multiple candidate `tasks.md`/checklist reads into one parallel tool-call block instead of reading them one at a time across separate turns, when the routing logic only needs to know which one has the first unchecked box. | token-efficiency | 2026-08-27 | 2026-08-27 | ROLL-4 session — read backbone/formatting-rules/strategy-rollout tasks.md sequentially across 3 turns |
| 1 | skill-file-path-assumed-global | Skill `SKILL.md` files in this repo are project-local (`.claude/skills/<name>/SKILL.md` under the repo root), not `~/.claude/`. Check the repo path first — a same-batch `ls .claude/skills/` already shows this — instead of guessing the global path and eating a wrong-path round trip. | token-efficiency | 2026-08-27 | 2026-08-27 | root-doc-organization plan session — 2 wasted `Read` calls locating `md-cleanup/SKILL.md` (global path guess + hook false-positive) |

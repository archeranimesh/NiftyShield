Read `CONTEXT.md` and state `CONTEXT.md ✓` before doing anything else. Then read
`docs/plan/telegram-markdown-migration/strategy-rollout/tasks.md` and find the first unchecked
box. That is your **only task** for this session. Do not look at any other unchecked item. One
task. Complete it fully. Stop.

**Depends on:** `backbone/` (all tasks) and `formatting-rules/` (all tasks) fully complete
before starting ROLL-1.

**Origin:** `docs/plan/telegram-markdown-migration/README.md` — epic index. This story is the
"how to send for strategies" rollout — sequenced by risk, lowest-stakes message first.

**Story spec:** Read the matching task in
`docs/plan/telegram-markdown-migration/strategy-rollout/stories.md` for the full spec.

**ROLL-4 coordination check — mandatory before starting that task specifically:** re-read
`docs/plan/full-repo-review-followups/telegram-approval-auth-fix/tasks.md` to confirm its
current state before touching `TelegramGateway.send_approval_request`. Do not trust the outer
`docs/plan/README.md` epic-summary status line — it was already found stale once (2026-08-07).

**Graph-before-Read rule:** Never call `Read` on `src/` or `scripts/` without first using the
graph.

**Test gate — blocking:**
`python -m pytest tests/unit/ --tb=no -q`
All must be green before committing.

**Financial-logic commit note:** ROLL-3 and ROLL-4 touch strategy close-notification and
approval-request code. Run the real `@code-reviewer` subagent against `git diff HEAD` before
committing those tasks, per root `CLAUDE.md`'s AutoTrigger rules.

**Commit:** Use format from `.claude/skills/commit/SKILL.md`. Execute the commit — do not draft
it.

**Verify and record:** Tick `tasks.md`, append `| SHA: <sha>`. Add one line to `TODOS.md`.

**Stop.** Do not proceed to the next unchecked item.

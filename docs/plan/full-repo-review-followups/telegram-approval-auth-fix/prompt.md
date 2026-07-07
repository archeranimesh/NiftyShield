Read `CONTEXT.md` and state `CONTEXT.md ✓` before doing anything else. Then read
`docs/plan/full-repo-review-followups/telegram-approval-auth-fix/tasks.md` and find the first unchecked box. That is your
**only task** for this session. Do not look at any other unchecked item. One task.
Complete it fully. Stop.

**Origin:** Spawned from `docs/plan/full-repo-review/findings/FR-7_synthesis.md` (Chairman
Synthesis), FR-7 row 9 (ERROR) — FR-6 S-2. Independently re-verified against the live repo before this story was
created — see FR-9's commit message for the verification method.

The Telegram callback auth guard for approving/rejecting real trading decisions uses OR logic where it should use AND — any member of a group chat the bot is ever added to could approve/reject real trading decisions. Currently masked only by 1:1-DM topology living in the deployer's head, not enforced in code.

**Surface & Model: Claude Code, Sonnet (escalate to Opus if the guard's identity semantics are unclear from the surrounding code).** Small (2 files) but not purely mechanical — verifying *which* identity check is actually correct here (sender vs. chat membership) is a real security judgment call, not a search-and-replace; Step 3b's "single/2-file task where inline judgment calls are likely" criterion routes this to Claude, not Antigravity, despite the small diff size.

**Pre-implementation gate:** State in one sentence which task, which files, which test file.
Do not write any code until this plan is stated.

**Story spec:** Read the matching story in `docs/plan/full-repo-review-followups/telegram-approval-auth-fix/stories.md` for the full spec.

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

**Financial logic commit — real `@code-reviewer` subagent mandatory** per CLAUDE.md's Agent AutoTrigger Rules (this touches P&L / Decimal / broker-adjacent paths). Resolve any CRITICAL/ERROR finding before committing.

**Commit:** Use format from `.claude/skills/commit/SKILL.md`. Execute the commit — do not
draft it.

**Verify and record:** Tick `tasks.md`, append `| SHA: <sha>`. Add one line to `TODOS.md`.

**Stop.** Do not proceed to the next unchecked item.

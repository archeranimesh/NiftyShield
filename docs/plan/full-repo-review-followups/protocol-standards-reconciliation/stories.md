# CLAUDE.md / REVIEW.md Standards Reconciliation — Story

**Source:** `docs/plan/full-repo-review/findings/FR-7_synthesis.md`, FR-7 rows 4, 5, 11 (CRITICAL + ERROR) — FR-1 F-C1, F-C2, F-E1, F-E2, F-E3.

## T1

Single reconciliation pass across CLAUDE.md, REVIEW.md, and the affected module docs (targeted Edit only, never Write-over): (a) add one line to the AutoTrigger table's "Blocking" note —
on surfaces that cannot spawn `.claude/agents/*` (Antigravity, some subagent contexts), emit the await-signal per ANTIGRAVITY.md and treat the gate as human-completed, not skipped;
(b) add the REVIEW.md G5 intent-comment requirement inline to the 4 broad-catch module docs (notifications, dhan, nuvama, mf);
change `src/paper/CLAUDE.md`'s "asserts"/"Asserts" wording (both occurrences) to "raises `ValueError` on mismatch (never literal `assert` — REVIEW.md G6)";
(c) state in Step 3 that the Step 3b routing fork applies regardless of file count, independent of the go-ahead gate;
pick one authoritative Step 2b mechanism (recommend:
Step 2b body's manual three-condition check is authoritative, `options-strategist` is advisory-only per FR-8's judgment call)
and make the AutoTrigger row + ai_collaboration_plan.md point to it rather than restating; adopt ANTIGRAVITY.md's precise `.py` in `src/scripts/tests` scope for Step 5c's "code changes" trigger.
Docs-only commit.

**Files touched:** `CLAUDE.md`, `REVIEW.md`, `src/notifications/CLAUDE.md`, `src/dhan/CLAUDE.md`, `src/nuvama/CLAUDE.md`, `src/mf/CLAUDE.md`,
`src/paper/CLAUDE.md`, `docs/antigravity/ai_collaboration_plan.md`

**Tests:** happy-path + error/edge-case per CLAUDE.md Step 4, in the files listed above.

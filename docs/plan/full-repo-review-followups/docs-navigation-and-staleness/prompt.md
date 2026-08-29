Read `CONTEXT.md` and state `CONTEXT.md ✓` before doing anything else. Then read
`docs/plan/full-repo-review-followups/docs-navigation-and-staleness/tasks.md` and find the first unchecked box.
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
4. **Boundaries** — Docs-only. Do not touch anything under `src/` or `scripts/`. Do not touch `CLAUDE.md` (that's `protocol-standards-reconciliation/`'s scope, not this story's).

Then stop. Do not proceed to implementation.

**When Antigravity returns its Phase Completion Output:** verify `files_changed` against
`git diff --name-only HEAD~1`, `tests_passing` against `pytest --tb=no -q`'s summary line, and
— the load-bearing check — that `commit_sha` matches `git log --oneline -1`. If all three
check out, tick `tasks.md`, append `| SHA: <sha>`, add one line to `TODOS.md`, stop. If
verification fails, open a fix session with the failure details per Step 3b — if the fix
needs the `code-reviewer`/`test-runner` AutoTrigger gates, run those yourself in Claude Code
rather than re-handing to Antigravity (FR-1 F-C1: Antigravity cannot spawn those subagents).

**Origin:** Spawned from `docs/plan/full-repo-review/findings/FR-7_synthesis.md` (Chairman
Synthesis), FR-7 rows 3, 8, 14 (CRITICAL + ERROR) — FR-3 F1, FR-1 F-E6/F12a/F12b, FR-3 F5, FR-3.1 F10, FR-3 F2. Independently re-verified against the live repo before this story was
created — see FR-9's commit message for the verification method.

Three converging staleness issues in the docs layer, all root-caused by FR-7 row 15 (docs/plan/README.md not in Step 5a's mandatory update list):
(1) `docs/plan/README.md`'s status table shows `dev-foundation`, `council-refactor`, `paper-backbone`, `ic-nifty-v2` as "Not started" when DECISIONS.md
and `docs/archive/plan/` confirm all four are shipped/archived.
(2) `docs/council/README.md` declares a taxonomy (`docs/council/archive/{strategy,risk,research}/`,
3 subfolders) that hasn't existed since commit `da93b64` moved the tree to `docs/archive/council/{strategy,risk,research,data_architecture,misc}/` (5 subfolders, different prefix) —
this breaks two confirmed dead links:
`docs/plan/variance-gate/prompt.md:18` and, more seriously, `DECISIONS.md` lines 397-407
which cite the dead `docs/council/2026-05-28_paper-trade-exit-philosophy.md` as the source of record for live CSP/CC/PP/collar exit thresholds (content was also revised 2026-06-26 —
a reader following the dead link could land on a superseded version). (3) `CONTEXT.md` still claims `src/nuvama/CLAUDE.md` doesn't exist (it does, 47 lines).

**Surface & Model: Antigravity (handoff via `handoff-antigravity`);
Claude Code / Sonnet for the review half.** Mechanical, grep-verifiable link/table fixes across 4 docs — within `ai_collaboration_plan.md`'s 3-5 file ceiling for Antigravity.
Docs-only: skip the code-reviewer gate per Step 5c, but Claude should still `grep` for the dead paths after the handoff returns to confirm no other doc still references them.

**Story spec:** Read the matching story in `docs/plan/full-repo-review-followups/docs-navigation-and-staleness/stories.md` for the full spec.

**Commit:** Antigravity executes the commit as part of its own protocol (per
`ai_collaboration_plan.md`) — Claude does not draft or run a separate commit for this story.

**Stop.** Do not proceed to the next unchecked item.

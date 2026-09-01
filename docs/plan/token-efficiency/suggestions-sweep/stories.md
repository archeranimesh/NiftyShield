# Token Efficiency — Suggestions Sweep — story specs

> One task per session. Find the first unchecked item in `tasks.md`. That is your only task.
> Full implementation rules in `CLAUDE.md` and `REVIEW.md`.
> After each task: set `SHA:` on the task line + tick the box, update the epic `README.md`
> Stories status column, add one line to `TODOS.md`, record any measured token delta and the
> rows closed in that task's As-built here. See `docs/plan/README.md` §Conventions.

---

## SWEEP-1 — Cluster the backlog

**Files to change / create:**
- This file — fill the SWEEP-1 As-built with the final cluster map

**Before any code:** read `suggestions.md` in full. Count the rows. Note any row added since
this story was authored.

**What to implement:**

1. Assign every row to exactly one cluster. Start from this taxonomy (refine as needed —
   the goal is that each later SWEEP task owns one cluster cleanly):

   - **Cluster 1 — Read & discovery hygiene** (SWEEP-2): `reread-file-already-in-context`,
     `sequential-single-file-section-reads`, `wide-grep-dump-then-page`,
     `search-graph-broad-query-result-dump`, `graph-tools-unused-relied-on-grep`,
     `sequential-tasks-md-reads`, `context-md-full-sequential-read`,
     `md-hook-backlog-not-checked-before-edit`, `lint-hook-run-outside-configured-scope`,
     `clarify-questions-before-context-gather`, `skill-file-path-assumed-global`.
   - **Cluster 2 — Test-run routing** (SWEEP-3): `pytest-inlined-not-test-runner`,
     `full-suite-run-for-docs-only-change`.
   - **Cluster 3 — Commit flow & pre-commit** (SWEEP-4): `sha-recorded-via-second-commit`,
     `staged-index-not-checked-before-commit`, `ruff-format-check-skipped-precommit-abort`,
     `next-marker-points-at-just-closed-task`, `line-coupled-baseline-set-before-code-frozen`,
     `todos-pointer-not-synced-with-readme`, `authored-md-prose-over-200-cap`,
     `reflow-interleaved-with-edits`, `transform-script-iterated-not-prototyped`,
     `precommit-all-files-mass-reformat`.
   - **Cluster 4 — MCP & tool-call params** (SWEEP-5): `codebase-mcp-missing-required-param`,
     `askuserquestion-preview-json-parse-fail`, `scheduleWakeup-poll-spawned-agent`.
   - **Cluster 5 — Subagent orchestration** (SWEEP-6): `parallel-subagent-ran-git-stash`,
     `skill-loaded-then-abandoned`.
   - **Cluster 6 — Shell environment** (SWEEP-6): `cd-in-compound-bash-command`,
     `bash-isms-in-zsh-shell`.
   - **Cluster 7 — Protocol discipline, model judgement** (SWEEP-6):
     `plan-gate-skipped-on-prescriptive-prompt`, `scope-question-jumped-ahead`,
     `plan-file-count-grew-silently`, `context-md-ack-not-stated`,
     `context-md-skipped-on-escalated-ops-task`.

2. For each row, state the intended outcome — `fix` (mistake becomes impossible), `enforce`
   (a hook / preflight warns), or `accept` (a one-line reason it stays model discipline).
3. Write the finished map into the SWEEP-1 As-built below. If a later SWEEP task discovers a
   row is better handled elsewhere, it updates this map in its own commit.

**Tests:** none (`.md` only).

**Commit:** `docs(plan): cluster the suggestions.md backlog for the sweep`

**As-built (SHA `<—>`):** _record: the final cluster table with per-row outcome, the total
row count clustered, and any row that resisted clustering._

---

## SWEEP-2 — Read & discovery hygiene → hooks

**Files to change / create:**
- `scripts/dev/hooks/check_repeat_read.py` — the logic; `tests/unit/scripts/dev/hooks/`
- `scripts/dev/hooks/check_wide_grep.py` — the logic; its test
- `.claude/hooks/repeat_read.sh`, `.claude/hooks/wide_grep.sh` — thin shims (match the
  existing `guard_src_reads.sh` pattern)
- `.claude/settings.json` — register both on `PreToolUse` (Read; Bash)
- `CLAUDE.md` Rule 0 / Rule 1 — one line each pointing at the new guard

**Before any code:**
- Read `.claude/hooks/guard_src_reads.sh` and one `scripts/dev/hooks/*.py` for the
  shim→Python split and how a `PreToolUse` hook receives the tool input (JSON on stdin).
- Re-read every row in cluster 1 for its cited example — the hook must fire on those and not
  on the counter-examples.

**What to implement:**

1. `check_repeat_read.py` — given the `Read` tool input and a session-scoped seen-paths file
   (write under the session state dir), warn if this path was already read this session and
   no intervening `Edit`/`Write` touched it. Message: "already read this session — edit the
   copy in context or use `get_code_snippet` for a specific block." Exit 0 always.
2. `check_wide_grep.py` — given a `Bash` command string, warn if it is a `grep`/`sed`/`awk`
   over a path (not a pipe from another command) with no `-c` / `-l` / `-n 'N,Mp'` /
   `--max-count` / head-limit and the target file is over ~800 lines. Message: point at
   `-c` / a line range / `search_code`. Exit 0.
3. Register the shims. Keep them fast (< 50 ms) — a slow `PreToolUse` hook taxes every call.
4. Add the Rule 0 / Rule 1 pointer lines.
5. Mark cluster-1 rows closed in the SWEEP-1 map. `clarify-questions-before-context-gather`
   and `skill-file-path-assumed-global` have no clean hook — `accept` them with a reason, or
   fold a line into the `/work` skill.

**Tests (`tests/unit/scripts/dev/hooks/`):**
- `test_repeat_read_warns_on_second_read` / `test_repeat_read_silent_after_edit` /
  `test_repeat_read_silent_first_read`
- `test_wide_grep_warns_on_unscoped_grep_large_file` /
  `test_wide_grep_silent_with_count_flag` / `test_wide_grep_silent_on_small_file` /
  `test_wide_grep_silent_on_pipe_input`
- both: `test_hook_always_exits_zero`

**Commit:** `feat(hooks): warn on repeat reads and unscoped wide greps`

**As-built (SHA `<—>`):** _record: which cluster-1 rows are fix / enforce / accept, and
(if measurable) the token drop on a session re-run where the hook would have fired._

---

## SWEEP-3 — Test-run routing

**Files to change / create:**
- `scripts/dev/hooks/check_inline_full_suite.py` + `.claude/hooks/inline_full_suite.sh` +
  `.claude/settings.json` registration (PreToolUse: Bash)
- `tests/unit/scripts/dev/hooks/test_check_inline_full_suite.py`
- `CLAUDE.md` "Agent AutoTrigger Rules" — amend the `test-runner` row
- `.claude/skills/work/SKILL.md` (or wherever the AutoTrigger cadence is spelled out)

**Before any code:**
- Read the `CLAUDE.md` AutoTrigger table and the ROLL-7 As-built note in
  `telegram-markdown-migration/strategy-rollout/stories.md` (3 `test-runner` spawns in one
  session ≈ 99K).
- Re-read the `pytest-inlined-not-test-runner` and `full-suite-run-for-docs-only-change`
  rows.

**What to implement:**

1. `check_inline_full_suite.py` — warn when a `Bash` command is `pytest tests/unit/` (or
   `python -m pytest tests/unit/`) without a narrowing path/`-k`/`-m`, run from the main
   session. Message: "full-suite run — spawn `@test-runner` instead; for a docs/tooling
   change, gate on the targeted dir." Exit 0.
2. Amend the AutoTrigger `test-runner` row: it fires **once, before `@code-reviewer` / the
   commit** — not after every intermediate edit. The intent is one authoritative green run
   per task, not per keystroke. Keep it blocking.
3. Update any skill text that says "after any code file is edited" to the new cadence.
4. Close cluster-2 rows in the SWEEP-1 map.

**Tests:**
- `test_warns_on_bare_full_suite` / `test_silent_with_k_filter` /
  `test_silent_with_path_narrowing` / `test_exits_zero`

**Commit:** `feat(hooks): nudge test-runner for inline full-suite pytest`

**As-built (SHA `<—>`):** _record: the AutoTrigger cadence before/after, and an estimate of
`test-runner` spawns saved per multi-edit task × ~30K each._

---

## SWEEP-4 — Commit flow → `commit_preflight.py`

**Files to change / create:**
- `scripts/dev/commit_preflight.py` — new
- `tests/unit/scripts/dev/test_commit_preflight.py` — new
- `.claude/skills/commit/SKILL.md` — call it in Step 1 (before staging)

**Before any code:**
- Read `.claude/skills/commit/SKILL.md` in full.
- Re-read every cluster-3 row. Several are one check each; a couple
  (`transform-script-iterated-not-prototyped`, `reflow-interleaved-with-edits`) are workflow
  advice a preflight cannot enforce — those are `accept`.

**What to implement:**

1. `commit_preflight.py` runs, against the current staged set, these checks and prints a
   findings list (warn, exit non-zero only on a hard blocker the commit skill already
   enforces):
   - **staged-index sanity** — `git diff --cached --name-only`; flag files outside the
     phase's expected set (the skill passes the expected paths).
   - **`ruff format --check`** on staged `.py` — flag if the format hook would reformat.
   - **md-line-length** on staged hook-covered `.md` — flag > 200-char lines (reuse
     `check_md_line_length.py`).
   - **next-marker** — if a `tasks.md` box was ticked in the staged diff, check the
     `docs/plan/README.md` / `TODOS.md` `next:` marker points at an unchecked id, not the
     one just ticked.
   - **SHA-placeholder policy** — if a staged `tasks.md` line still has `SHA: <—>` while its
     box is `[x]`, flag it; if the policy is "land with `<pending>` and backfill next
     commit", state that in the skill so no dedicated swap-only commit is needed.
2. Wire it into the `commit` skill Step 1.
3. Close cluster-3 rows in the SWEEP-1 map with fix / enforce / accept each.

**Tests:**
- one per check: a passing fixture and a failing fixture
- `test_preflight_clean_repo_reports_nothing`

**Commit:** `feat(scripts): add commit_preflight.py and wire it into the commit skill`

**As-built (SHA `<—>`):** _record: which cluster-3 rows each check closes, which are
accepted, and the count of avoided re-stage / swap-only-commit cycles from a sample of recent
sessions._

---

## SWEEP-5 — MCP & tool-call param hygiene

**Files to change / create:**
- `.claude/skills/codebase-memory/SKILL.md` — the `project` / `repo_path` first-call rule
- `CLAUDE.md` Rule 0 tool list — same, one line
- Wherever `AskUserQuestion` guidance can live for the session to see it (a skill note or a
  `CLAUDE.md` line) — the plain-`questions`-array rule, no `preview`, no `{"raw": …}`
- The `ScheduleWakeup` note — "harness re-invokes on subagent completion; do not poll"

**Before any code:** re-read the three cluster-4 rows and their cited failures.

**What to implement:**

1. `codebase-memory` skill + Rule 0: "first call passes `project=Users-abhadra-...` (and
   `repo_path=<abs>` for `index_repository`) — omitting it costs a wasted round trip."
2. `AskUserQuestion` rule where a planning session will read it: plain array of short
   string-only fields; `preview` and envelope shapes have repeatedly failed the tool's JSON
   parse.
3. `ScheduleWakeup` rule: never schedule a wake-up to poll a subagent you spawned —
   task-notification re-invokes automatically on completion.
4. Close cluster-4 rows.

**Tests:** none (docs-only). If any row turns out to need a wrapper script, that adds a
`Review: code-reviewer` and a test file — note it in the commit.

**Commit:** `docs(skills): document MCP required params and tool-call param rules`

**As-built (SHA `<—>`):** _record: rows closed; per-row this is an `enforce`-by-doc, not a
hook — note if any recurred after and needs escalation._

---

## SWEEP-6 — Shell, subagent orchestration, protocol discipline

**Files to change / create:**
- `CLAUDE.md` — a "session shell is zsh" line + the `cd`-in-compound-Bash rule (the harness
  Bash-tool note already says this; make it prominent)
- `.claude/skills/handoff-antigravity/SKILL.md` / wherever parallel-subagent spawns are
  described — the "forbid every index/stash-touching git command, compute counts with
  `awk`/`grep` only" rule
- The Step 3b routing text — "settle the routing call before invoking `handoff-antigravity`;
  its body is wasted if you then decide Claude implements"
- The Step 3 protocol text — one consolidated line covering `plan-gate-skipped`,
  `scope-question-jumped-ahead`, `plan-file-count-grew-silently`: state the one-line plan and
  the in-scope file list, wait for go-ahead on > 2 files, and re-flag when the count grows
- The Step 1 text — `context-md-ack-not-stated` and `context-md-skipped-on-escalated-ops-task`
  are already covered; tighten the wording so "state `CONTEXT.md ✓`" and "the moment code
  enters scope" are unmissable

**Before any code:** re-read cluster-5, cluster-6, cluster-7 rows.

**What to implement:**

1. The shell rules (cluster 6) — `fix` by making the constraint prominent; a hook is
   possible but likely high-false-positive, so start with text.
2. The subagent-orchestration rules (cluster 5) — text in the relevant skills.
3. The protocol-discipline rows (cluster 7) — `accept` with a reason (these are model
   judgement), but consolidate the guidance so it is one clear paragraph, not scattered.
4. Close clusters 5 / 6 / 7 in the SWEEP-1 map.

**Tests:** none (`.md` only).

**Commit:** `docs(protocol): tighten shell, subagent, and plan-gate guidance`

**As-built (SHA `<—>`):** _record: rows fixed vs. accepted, and the consolidated
protocol-discipline paragraph's location._

---

## SWEEP-7 — Make Step 4b self-draining

**Files to change / create:**
- `.claude/skills/session-close/SKILL.md` — Step 4b (rebased onto `fixed-overhead/` FIX-3's
  redesigned skill)
- `docs/plan/technical-debt/tasks.md` + `stories.md` — seed the escalated slugs
- `suggestions.md` — the skill may add a "Status" column or an "Accepted / won't-fix"
  section; `Count` stays skill-owned

**Before any code:**
- Confirm FIX-3 has landed (the skill runs as a transcript-reading subagent). If not, note
  in the commit that a rebase onto FIX-3 is owed and coordinate.
- Read `docs/plan/technical-debt/prompt.md` for its "fix only when already there" convention.

**What to implement:**

1. Step 4b, new logic: after incrementing a slug's `Count`, if `Count >= 5` and the slug has
   no linked remediation, the skill must either (a) append a `DEBT-*` line to
   `technical-debt/tasks.md` describing the structural fix and marked
   **standalone-actionable** (the exception to that folder's convention, because these are
   proactive), or (b) if the team decides it is genuinely model discipline, move the row to
   an "Accepted / won't-fix" section of `suggestions.md` with a one-line reason. Either way
   the row leaves the active count-sorted list.
2. The skill states the threshold (5) and the two exits explicitly so a future session
   applies it consistently.
3. Seed: for every slug currently at `Count >= 5` (`reread-file-already-in-context`,
   `pytest-inlined-not-test-runner`, `wide-grep-dump-then-page`), add the `DEBT-*` line or
   the accepted-row — cross-referencing the SWEEP-2 / SWEEP-3 hooks that already address
   them, so the `DEBT-*` may simply be "verify the SWEEP-N hook is effective; if the slug
   still recurs 3 sessions after the hook landed, escalate to a protocol/model discussion."
4. Update `suggestions.md`'s header note to describe the drain path.

**Tests:** none (`.md` only).

**Commit:** `refactor(session-close): escalate and retire high-count suggestion slugs`

**As-built (SHA `<—>`):** _record: the threshold and exits chosen, the slugs seeded and
where, and confirmation the change is rebased onto FIX-3._

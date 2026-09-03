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

**As-built (SHA `622465c`):**

**40 rows** clustered (`suggestions.md` lines 9–48), each into exactly one of 7 clusters. No
row resisted clustering. Six rows added since this story was authored are folded in below and
flagged `[new]`: `sha-recorded-via-second-commit`, `next-marker-prose-evades-guard`,
`spec-prestep-skipped-source-not-read`, `heredoc-rewrite-echoes-whole-file-back`,
`py-authored-lines-over-ruff-cap`, `mirror-doc-path-convention-assumed`. Outcome legend:
**fix** = mistake becomes structurally impossible · **enforce** = a hook / preflight warns
when it happens · **accept** = stays model-discipline, reason given.

### Cluster 1 — Read & discovery hygiene → SWEEP-2 (12 rows)

| Slug | Count | Outcome | Note |
|---|--:|---|---|
| reread-file-already-in-context | 17 | enforce | `check_repeat_read.py` warns on a 2nd Read with no intervening Edit; Edit/Write prior-read gate case is a harness constraint (accept the residual) |
| wide-grep-dump-then-page | 7 | enforce | `check_wide_grep.py` — unscoped grep/sed over an >800-line file |
| sequential-single-file-section-reads | 4 | accept | batch-the-Reads discipline; no clean hook — one line into `/work` |
| context-md-full-sequential-read | 2 | accept | grep-CONTEXT.md-first discipline; low recurrence, fold into `/work` text |
| search-graph-broad-query-result-dump | 1 | accept | use a tight `qualified_name`; reinforce in Rule 0 graph-first text |
| graph-tools-unused-relied-on-grep | 1 | accept | graph-before-grep; reinforce Rule 0 text |
| sequential-tasks-md-reads | 1 | accept | parallel-batch candidate reads; one line into `/work` |
| md-hook-backlog-not-checked-before-edit | 1 | enforce | staged md-line-length check in `commit_preflight.py` (SWEEP-4) surfaces the backlog |
| lint-hook-run-outside-configured-scope | 1 | accept | check the `files:` regex first; rare, text note in SWEEP-2 |
| clarify-questions-before-context-gather | 3 | accept | read target docs before the first ask; fold a line into `/work` (spec-directed) |
| skill-file-path-assumed-global | 1 | accept | skills are repo-local `.claude/skills/`; fold a line into `/work` (spec-directed) |
| heredoc-rewrite-echoes-whole-file-back `[new]` | 1 | accept | prefer targeted `sed -i`/`python3` replace over `cat > file <<EOF`; edit-technique discipline, reinforce in SWEEP-2 text |

**Closed by SWEEP-2 (SHA `68683cb`):** all 12 rows. `enforce` — `reread-file-already-in-context`,
`wide-grep-dump-then-page` (new hooks `check_repeat_read.py` / `check_wide_grep.py`, warn-only).
`enforce` deferred to SWEEP-4 — `md-hook-backlog-not-checked-before-edit` (staged md-line-length
in `commit_preflight.py`). `fix`-by-text — `clarify-questions-before-context-gather` +
`skill-file-path-assumed-global` folded into `/work`; `search-graph-broad-query-result-dump`,
`graph-tools-unused-relied-on-grep` reinforced in the Rule 0 text; `heredoc-rewrite-echoes-whole-file-back`,
`lint-hook-run-outside-configured-scope` noted here as edit-technique / check-the-`files:`-regex
discipline. `accept` (batch-your-reads model discipline, no clean hook) —
`sequential-single-file-section-reads`, `context-md-full-sequential-read`, `sequential-tasks-md-reads`.

### Cluster 2 — Test-run routing → SWEEP-3 (2 rows)

| Slug | Count | Outcome | Note |
|---|--:|---|---|
| pytest-inlined-not-test-runner | 9 | enforce | `check_inline_full_suite.py` nudges `@test-runner`; AutoTrigger cadence amended to "once before commit" |
| full-suite-run-for-docs-only-change | 1 | enforce | same hook — for a docs/tooling change it points at the targeted hook-test dir |

**Closed by SWEEP-3 (SHA `e325e86`):** both rows. `check_inline_full_suite.py` +
`.claude/hooks/inline_full_suite.sh` (registered on `Bash`) warn-only when the main session
runs a bare `pytest tests/unit/` with no `-k`/`-m`/path/node-id narrowing, and point a
docs/tooling change at the targeted dir. AutoTrigger `test-runner` row amended in `CLAUDE.md`
+ `AGENTS.md` to "once per task, before `code-reviewer` / the commit — not per-edit";
`session-close` checklist rows 4-TR updated to match.

### Cluster 3 — Commit flow & pre-commit → SWEEP-4 (12 rows)

| Slug | Count | Outcome | Note |
|---|--:|---|---|
| sha-recorded-via-second-commit `[new]` | 5 | fix + escalate | SWEEP-4 puts the `<pending>`-then-backfill policy in the `commit` skill (no swap-only commit); Count ≥ 5 → SWEEP-7 escalation |
| authored-md-prose-over-200-cap | 4 | enforce | `commit_preflight.py` md-line-length on staged `.md`; un-reflowable task lines stay an accept |
| staged-index-not-checked-before-commit | 2 | enforce | preflight staged-index sanity vs. the phase's expected paths |
| next-marker-points-at-just-closed-task | 2 | enforce | preflight next-marker check — must point at an unchecked id |
| next-marker-prose-evades-guard `[new]` | 1 | fix | preflight next-marker check matches prose forms ("next is **X**"), closing the `README_ENTRY_RE` blind spot |
| line-coupled-baseline-set-before-code-frozen | 1 | accept | freeze the file, then set the `(file, line)` baseline once — sequencing discipline |
| todos-pointer-not-synced-with-readme | 1 | enforce | preflight flags a `docs/plan/README.md` pointer move not mirrored in `TODOS.md` in the same staged set |
| ruff-format-check-skipped-precommit-abort | 1 | enforce | preflight runs `ruff format --check` on staged `.py` |
| py-authored-lines-over-ruff-cap `[new]` | 1 | enforce | same preflight `ruff` pass catches over-cap authored lines before the hook aborts |
| precommit-all-files-mass-reformat | 1 | enforce | `commit` skill text: `pre-commit run --files $(…)`, never `--all-files` |
| reflow-interleaved-with-edits | 1 | accept | run reflow once after all structural Edits — workflow advice a preflight cannot enforce (spec-directed) |
| transform-script-iterated-not-prototyped | 1 | accept | prototype a bulk transform on a slice first — workflow advice (spec-directed) |

**Closed by SWEEP-4 (SHA `<pending>`):** all 12 rows. `enforce` (new
`scripts/dev/commit_preflight.py`, run against the staged set in `commit` skill Step 1b) —
`ruff-format-check-skipped-precommit-abort` + `py-authored-lines-over-ruff-cap` (one `ruff
format --check` pass on staged `.py`), `authored-md-prose-over-200-cap` +
`md-hook-backlog-not-checked-before-edit` (staged `.md` md-line-length, reusing
`check_md_line_length.check_file`), `staged-index-not-checked-before-commit` (staged paths
vs. `--expect` prefixes), `next-marker-points-at-just-closed-task` +
`todos-pointer-not-synced-with-readme` (next-marker scan over staged `tasks.md` /
`README.md` / `TODOS.md`). `fix` — `next-marker-prose-evades-guard` (the preflight check
matches the prose forms `Open: X (next)` / `next is **X**` that `README_ENTRY_RE` in
`check_checkbox_consistency.py` misses); `sha-recorded-via-second-commit` (the
`<pending>`-then-backfill policy is now stated in `commit` skill Step 1b — no swap-only
commit; also `enforce`d by the preflight's SHA-placeholder warning) — still Count ≥ 5, so
SWEEP-7 seeds it as a `technical-debt/` line. `fix`-by-text — `precommit-all-files-mass-reformat`
(`commit` skill Step 4 now says `pre-commit run --files …`, never `--all-files`). `accept`
(workflow-sequencing advice a preflight structurally cannot verify) —
`line-coupled-baseline-set-before-code-frozen`, `reflow-interleaved-with-edits`,
`transform-script-iterated-not-prototyped`.

### Cluster 4 — MCP & tool-call params → SWEEP-5 (3 rows)

| Slug | Count | Outcome | Note |
|---|--:|---|---|
| codebase-mcp-missing-required-param | 3 | fix | Rule 0 tool list + `codebase-memory` skill state the `project` / `repo_path` first-call rule so the first call is correct |
| askuserquestion-preview-json-parse-fail | 3 | enforce (by doc) | plain `questions` array, no `preview`/envelope — rule where a planning session reads it |
| scheduleWakeup-poll-spawned-agent | 1 | enforce (by doc) | "harness re-invokes on subagent completion — do not poll" note |

**Closed by SWEEP-5 (SHA `<pending>`):** all 3 rows, `enforce`-by-doc. A new
**Tool-call param hygiene** section in `CLAUDE.md` + `AGENTS.md` (after the AutoTrigger
rules, before Step 5) states all three: the `codebase-memory-mcp` `project=` /
`index_repository` `repo_path=` first-call rule (also pointed at from the Rule 0 tool list),
the `AskUserQuestion` plain-`questions`-array / no-`preview` / no-`{"raw":…}` rule, and the
`ScheduleWakeup` "never poll a spawned subagent — task-notification re-invokes you" rule.
The in-repo `.claude/skills/codebase-memory/SKILL.md` named in the SWEEP-5 spec does not
exist (that skill is plugin-provided, not repo-local), so the `project=` rule went to the
Rule 0 tool list instead — same "session sees it before the first call" placement. No
wrapper script was needed; all 3 are docs-only.

### Cluster 5 — Subagent orchestration → SWEEP-6 (2 rows)

| Slug | Count | Outcome | Note |
|---|--:|---|---|
| parallel-subagent-ran-git-stash | 1 | fix | parallel-spawn text forbids every index/stash-touching git command; counts via `awk`/`grep` only |
| skill-loaded-then-abandoned | 1 | fix | Step 3b text: settle the Claude-vs-Antigravity routing call before invoking `handoff-antigravity` |

**Closed by SWEEP-6 (SHA `<pending>`):** both rows, `fix`-by-text.
`parallel-subagent-ran-git-stash` — new `CLAUDE.md` / `AGENTS.md` **Step 3c** forbids every
index / stash-touching git command in a parallel-subagent spawn (not just `add` / `commit` /
`stash`) and mandates `awk` / `grep` for line counts. `skill-loaded-then-abandoned` —
`CLAUDE.md` Step 3b now leads with "settle this routing call firmly before invoking
`handoff-antigravity`", and the skill itself gained a "Before reading further: confirm the
routing call is Antigravity" callout (mirrored in `.agents/skills/`).

### Cluster 6 — Shell environment → SWEEP-6 (2 rows)

| Slug | Count | Outcome | Note |
|---|--:|---|---|
| cd-in-compound-bash-command | 1 | fix | prominent `CLAUDE.md` rule — CWD persists across Bash calls; use absolute paths / `git -C` |
| bash-isms-in-zsh-shell | 1 | fix | prominent "session shell is zsh" line — no `mapfile`/`readarray`, no `$var` word-split lists |

**Closed by SWEEP-6 (SHA `<pending>`):** both rows, `fix`-by-text. A new **Shell mechanics**
paragraph after Rule 1 in `CLAUDE.md` states: session shell is zsh (no `mapfile` / `readarray`,
no `$var` word-split lists) and never `cd` in a compound Bash command — cwd persists across
calls; use absolute paths / `git -C`. `AGENTS.md` carries the adapted delta (Antigravity's
`run_command` is an isolated `bash -c` with no persisted cwd, not zsh).

### Cluster 7 — Protocol discipline, model judgement → SWEEP-6 (7 rows)

| Slug | Count | Outcome | Note |
|---|--:|---|---|
| plan-gate-skipped-on-prescriptive-prompt | 2 | accept | model judgement; consolidate into one Step 3 paragraph — a prescriptive prompt is not a go-ahead |
| scope-question-jumped-ahead | 1 | accept | model judgement; same consolidated Step 3 paragraph — scope the first unstarted phase only |
| plan-file-count-grew-silently | 1 | accept | model judgement; same paragraph — re-flag when the file count grows past the approved plan |
| context-md-ack-not-stated | 1 | accept | tighten Step 1 wording so "state `CONTEXT.md ✓`" is unmissable |
| context-md-skipped-on-escalated-ops-task | 1 | accept | tighten Step 1 wording — Step 1 applies the moment code enters scope |
| spec-prestep-skipped-source-not-read `[new]` | 1 | accept | run a task spec's "Before any code" source-read prestep — model discipline, noted in SWEEP-6 |
| mirror-doc-path-convention-assumed `[new]` | 1 | accept | grep an existing mirror for the path convention before writing pointers into `AGENTS.md` — noted alongside the FIX-1 mirror rule |

**Closed by SWEEP-6 (SHA `<pending>`):** all 7 rows, `accept` with the guidance consolidated,
not left scattered. `plan-gate-skipped-on-prescriptive-prompt` + `scope-question-jumped-ahead`
+ `plan-file-count-grew-silently` — one consolidated paragraph appended to `CLAUDE.md` /
`AGENTS.md` **Step 3**: a prescriptive prompt is not a go-ahead, scope only the first unstarted
phase, re-flag when the file count grows past what was approved. `context-md-ack-not-stated` +
`context-md-skipped-on-escalated-ops-task` — **Step 1** wording tightened ("state `CONTEXT.md
✓` verbatim in your first user-facing response"; "applies the moment code enters scope").
`spec-prestep-skipped-source-not-read` — new **Step 3c** "Before writing code" makes a spec's
"Before any code" source-read pre-step mandatory. `mirror-doc-path-convention-assumed` — a line
in the `md-organize` skill Step 7 (alongside the FIX-1 mirror re-sync rule): grep an existing
mirror for the path convention before writing any path into `AGENTS.md` / `.agents/**`.

### Roll-up

23 rows land a structural **fix** or a **hook/preflight enforce** (7 fix, 16 enforce);
17 rows are **accept** with a stated reason — 12 of those are batch-your-reads / run-the-
prestep / state-the-plan model-discipline items with no mechanical catch, the rest are
workflow-sequencing advice a preflight structurally cannot verify. Cluster ownership matches
the SWEEP-2..SWEEP-7 task split exactly; SWEEP-2/3/4 carry the enforcement load, SWEEP-5/6
carry the doc fixes, SWEEP-7 drains `sha-recorded-via-second-commit` and any other slug that
crosses Count 5.

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

**As-built (SHA `68683cb`):** Two warn-only `PreToolUse` hooks landed:
`scripts/dev/hooks/check_repeat_read.py` (+ `.claude/hooks/repeat_read.sh`, registered on
`Read|Edit|Write`) tracks read paths in a PID-scoped `/tmp` file and warns on a 2nd `Read` with
no intervening `Edit`/`Write`; `scripts/dev/hooks/check_wide_grep.py` (+
`.claude/hooks/wide_grep.sh`, on `Bash`) warns on an unscoped `grep`/`sed`/`awk` over an
>800-line file argument, or a recursive `grep` with no `--include`/`--exclude`. Both exit 0
always. 56 tests in `tests/unit/scripts/dev/hooks/`. Rule 0 gains a repeat-Read pointer line,
Rule 1's table a wide-grep row; `/work` gains the two `fix`-by-text lines.

Cluster-1 outcomes: see the "Closed by SWEEP-2" block under the cluster map above — 5 enforce
(2 here + `md-hook-backlog` deferred to SWEEP-4's preflight + the 2 hooks), 4 fix-by-text, 3
accept.

Measured delta: baseline (epic `README.md`, `token_audit.py` over 5 sessions) —
`reread-file-already-in-context` cited in 6 of the last ~8 sessions with 2–5 redundant scoped
Reads each; `tool_results:Read` median 32K/session, up to 67K. A redundant scoped Read of a
~200-line source region ≈ 2.5–4K tokens; the repeat-Read hook firing on ~3 such Reads/session
recovers ≈ 8–12K/session on the sessions where it fires. `wide-grep-dump-then-page` (Count 7):
the two cited incidents wrote a 99KB and a ~2.5K-token result file — the second of which then
cost a 25K-cap paging Read; catching one such grep/session ≈ 3–25K saved. Both are
warn-only, so the realised saving depends on the model heeding the warning — the epic's
"re-run `token_audit.py` on post-hook sessions" follow-up (Perspectives not covered) is the
real measurement.

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

**As-built (SHA `e325e86`):** New warn-only `PreToolUse(Bash)` hook
`scripts/dev/hooks/check_inline_full_suite.py` (+ `.claude/hooks/inline_full_suite.sh`,
registered in `.claude/settings.json`) fires when a command runs `pytest` / `python -m pytest`
against `tests/unit` / `tests/` / no path, with no `-k` / `-m` / specific file / `::` node id
/ `--lf` narrowing (`./`-prefixed paths normalised) — message points at `@test-runner` and,
for a docs/tooling change, at the targeted dir. Exit 0 always. 14 tests in
`tests/unit/scripts/dev/hooks/test_check_inline_full_suite.py`. The hook has no reliable
main-vs-subagent signal, so a `@test-runner` subagent's own full-suite run also sees the line
— harmless warn-only noise, noted here.

AutoTrigger cadence — **before:** "`test-runner` (Haiku) | After any code file is edited,
before code-reviewer" (read as per-edit — the ROLL-7 session spawned it 3× as the diff grew).
**After:** "Once per task, after code files are edited and before `code-reviewer` / the commit
— not per-edit", with a paragraph making "one authoritative green run per task" explicit.
Mirrored in `CLAUDE.md`, `AGENTS.md`, and the `session-close` checklist (rows 4-TR + the
VIOLATION rule).

Measured delta: baseline (epic `README.md`) — `subagent_internal` median 367K/session;
`pytest-inlined-not-test-runner` Count 9. The ROLL-7 audit attributes ~99K to 3 `test-runner`
spawns (~33K each). Collapsing to one spawn per task saves ~2 × 33K ≈ **66K account-side per
multi-edit task** that previously re-ran the agent per edit; on single-edit tasks the cadence
change is a no-op. The inline-run hook itself is warn-only, so its realised saving depends on
the model heeding it (routing the run into the Haiku subagent instead of the main loop) — the
epic's post-hook `token_audit.py` re-run (Perspectives not covered) is the real measurement.

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

**As-built (SHA `<pending>`):** `scripts/dev/commit_preflight.py` — a CLI (not a git hook)
the `commit` skill runs in Step 1b against the staged set. Five checks: staged-index sanity
vs. `--expect` prefixes (warn), `ruff format --check` on staged `.py` (blocker, exit 1),
md-line-length on staged hook-covered `.md` (blocker, reuses
`scripts/dev/hooks/check_md_line_length.check_file`), next-marker (warn — a box the staged
diff ticks must not still be named `next:` / `next is **X**` / `X (next)` / `Open: X (next)`
in any staged `tasks.md` / `README.md` / `TODOS.md`), SHA-placeholder (warn — a `[x]` task
line still on `SHA: <—>`). Exit 1 only on a blocker; warnings are advisory, matching the
`.claude/hooks/` warn-only contract. 20 tests in
`tests/unit/scripts/dev/test_commit_preflight.py` (pure per-check functions + `main`
wiring). `commit` skill Step 1b added (invocation + the blocker/warning legend + the
`<pending>`-then-backfill SHA policy); Step 4 gains the `pre-commit run --files …` /
never-`--all-files` line. Cluster-3 outcomes: see the "Closed by SWEEP-4" block above — 8
enforce, 3 fix, 3 accept (the `sha-recorded-via-second-commit` row is both fixed here and
handed to SWEEP-7 for the Count-≥-5 drain).

Measured delta: this is a workflow-cycle saving, not a per-turn token cut. Baseline (epic
`README.md`) — the commit-flow slugs recur ~1×/session between them; the dominant cost is
`sha-recorded-via-second-commit` (Count 5), where a dedicated swap-only commit = one extra
`git` round trip plus a `code-reviewer` re-run on the trivial diff (~30–40K account-side
when the diff qualifies for review) and each `ruff-format`/`md-line-length` pre-commit abort
= one re-stage cycle (~2–5K in re-run tool output + assistant narration). Catching both
before the commit removes ≈ **30–45K on a session that would otherwise hit the swap-only +
one abort path**; on a clean session the preflight is a single ~1s Bash call (~0.2K). As
with the SWEEP-2/3 hooks the realised saving depends on the model acting on the warnings —
the epic's post-hook `token_audit.py` re-run (Perspectives not covered) is the real
measurement.

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

**As-built (SHA `<pending>`):** All 3 cluster-4 rows closed as `enforce`-by-doc — no hook, no
wrapper. New **Tool-call param hygiene (MCP / AskUserQuestion / ScheduleWakeup)** section
added to `CLAUDE.md` and mirrored in `AGENTS.md`, placed after the Agent AutoTrigger Rules
and before Step 5 so a session reads it before making any of the three calls:

- `codebase-mcp-missing-required-param` (Count 3) — the section + a new Rule 0 tool-list line
  state that every raw `codebase-memory-mcp` call needs
  `project=Users-abhadra-myWork-myCode-python-NiftyShield`, and `index_repository` also needs
  `repo_path=<abs>`. Notes that `scripts.dev.graph_snippet` already defaults `--project` but a
  direct MCP call does not — the RDO-15 / ROLL-7 failures were all direct calls.
- `askuserquestion-preview-json-parse-fail` (Count 3) — rule: plain `questions` array, short
  plain-string fields only, no `preview`, no `{"raw": <escaped json>}` envelope, no
  multi-line / backtick / brace values.
- `scheduleWakeup-poll-spawned-agent` (Count 1) — rule: never schedule a wake-up to poll a
  spawned subagent; task-notification re-invokes on completion.

The SWEEP-5 spec named `.claude/skills/codebase-memory/SKILL.md` as a target; that file is
not in the repo (the `codebase-memory` skill is plugin-provided), so the `project=` rule
went to the Rule 0 tool list — same placement intent (session sees it before the first
call). Docs-only: no `Review: code-reviewer`, no tests.

Measured delta: not a per-turn cut — an avoided-retry saving. Baseline (epic `README.md`) —
each cited failure cost one full tool round trip plus the assistant's error-handling
narration before the correct call: a rejected `codebase-memory-mcp` call ≈ 0.3–0.5K
(rejection + retry), a failed `AskUserQuestion` JSON parse ≈ 1–2K (the whole question
payload echoed back in the error, then re-sent), a `ScheduleWakeup` poll turn ≈ 3–6K (a full
turn's per-turn hook + protocol re-injection for nothing). Across the 4 cited incidents in
`suggestions.md` that is ≈ 6–12K of pure waste; the doc rules remove it on any session that
reads them before the call. As with SWEEP-2..4 the realised saving is the epic's post-change
`token_audit.py` re-run.

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

**As-built (SHA `<pending>`):** Docs-only, no tests, `Review: none`. 11 rows closed across
clusters 5 / 6 / 7 — see the three "Closed by SWEEP-6" blocks in the cluster map above. **4
`fix`-by-text** (`parallel-subagent-ran-git-stash`, `skill-loaded-then-abandoned`,
`cd-in-compound-bash-command`, `bash-isms-in-zsh-shell`); **7 `accept`** with the guidance
consolidated (`plan-gate-skipped-on-prescriptive-prompt`, `scope-question-jumped-ahead`,
`plan-file-count-grew-silently`, `context-md-ack-not-stated`,
`context-md-skipped-on-escalated-ops-task`, `spec-prestep-skipped-source-not-read`,
`mirror-doc-path-convention-assumed`).

Files touched: `CLAUDE.md` — **Shell mechanics** para after Rule 1; **Step 1** ack + scope
wording; **Step 3** consolidated plan-gate paragraph; **Step 3b** handoff-routing lead-in;
new **Step 3c — Before writing code** (spec pre-step + parallel-subagent git rule).
`AGENTS.md` — all of the above mirrored, with the shell note adapted to Antigravity's isolated
`bash -c`. `.claude/skills/handoff-antigravity/SKILL.md` (+ `.agents/` mirror) — "confirm the
routing call is Antigravity before reading further" callout. `.claude/skills/md-organize/SKILL.md`
Step 7 — grep-an-existing-mirror-for-the-path-convention line.

The consolidated protocol-discipline guidance lives in three anchored spots by design (per the
SWEEP-1 map): the plan-gate trio in **Step 3**, the CONTEXT.md-ack pair in **Step 1**, the
source-read pre-step in the new **Step 3c**.

Measured delta: **not measurable as a per-turn or per-session token cut** — every SWEEP-6 row
is a `fix`-by-text or an `accept`, i.e. protocol-text clarification with no hook or preflight
attached (the enforcement load was SWEEP-2 / SWEEP-3 / SWEEP-4). The avoided-waste ceiling per
cited incident is small and one-off: a `git stash` recovery ≈ 2–4K, a `mapfile`-in-zsh retry
≈ 1–2K × 2 runs, a `handoff-antigravity` load-then-reverse ≈ 1.5K, a missing `CONTEXT.md ✓`
costs nothing in tokens (it is a traceability gap). Whether the tightened wording changes
behaviour is the epic's post-change `token_audit.py` re-run (Perspectives not covered), not
this task's DoD.

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

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

### Cluster 4 — MCP & tool-call params → SWEEP-5 (3 rows)

| Slug | Count | Outcome | Note |
|---|--:|---|---|
| codebase-mcp-missing-required-param | 3 | fix | Rule 0 tool list + `codebase-memory` skill state the `project` / `repo_path` first-call rule so the first call is correct |
| askuserquestion-preview-json-parse-fail | 3 | enforce (by doc) | plain `questions` array, no `preview`/envelope — rule where a planning session reads it |
| scheduleWakeup-poll-spawned-agent | 1 | enforce (by doc) | "harness re-invokes on subagent completion — do not poll" note |

### Cluster 5 — Subagent orchestration → SWEEP-6 (2 rows)

| Slug | Count | Outcome | Note |
|---|--:|---|---|
| parallel-subagent-ran-git-stash | 1 | fix | parallel-spawn text forbids every index/stash-touching git command; counts via `awk`/`grep` only |
| skill-loaded-then-abandoned | 1 | fix | Step 3b text: settle the Claude-vs-Antigravity routing call before invoking `handoff-antigravity` |

### Cluster 6 — Shell environment → SWEEP-6 (2 rows)

| Slug | Count | Outcome | Note |
|---|--:|---|---|
| cd-in-compound-bash-command | 1 | fix | prominent `CLAUDE.md` rule — CWD persists across Bash calls; use absolute paths / `git -C` |
| bash-isms-in-zsh-shell | 1 | fix | prominent "session shell is zsh" line — no `mapfile`/`readarray`, no `$var` word-split lists |

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

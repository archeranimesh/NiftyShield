# NiftyShield — Session Close Skill

> Invoke at the end of any work session to produce a protocol compliance and token efficiency report.
> Trigger phrases: "session close", "close the session", "end of session report", "session summary"
>
> Goal: honest self-audit. Not a trophy — a diagnostic. Steps skipped need accurate labels,
> not post-hoc rationalization. The report is only useful if violations are called violations.

---

## Step 1 — Reconstruct the session's action log

Before scoring, build a factual list of what happened this session by recalling:

- Which files were `Read` (especially `src/` and `scripts/` paths)
- Which graph tools fired (`search_graph`, `get_code_snippet`, `trace_path`, `search_code`)
- Which bash commands ran (look for `pytest`, `git commit`, `git add`, `SELECT`)
- Which subagents were spawned (`@test-runner`, `@code-reviewer`, `@greeks-analyst`, `@roll-validator`)
- Which skills were invoked (`commit`, `prompt-refine`, `handoff-antigravity`)
- Whether a commit was made (`git log --oneline -1` was run and SHA confirmed)

Do not reconstruct from memory alone — confirm the latest commit via bash:

```bash
git -C /path/to/repo log --oneline -5
```

---

## Step 2 — Score each protocol step

For every step below, mark one of:

- ✅ **FOLLOWED** — step was completed as specified
- ⚠️ **LEGITIMATE SKIP** — step genuinely did not apply (give one-line reason)
- ❌ **VIOLATION** — step applied but was skipped or shortcut (give one-line reason)

### Protocol Checklist

| # | Step | Status | Reason (if not FOLLOWED) |
|---|---|---|---|
| 0 | Rule 0 — graph queried before any `src/` Read | | |
| 1 | CONTEXT.md read at session start | | |
| 2 | Scope confirmed (files named, or asked if not) | | |
| 2b | Council checkpoint evaluated | | |
| 3 | Plan stated in one sentence + go-ahead received | | |
| 3b | Routing decision made: Claude vs Antigravity | | |
| 4 | Tests written (happy path + edge case per public fn) | | |
| 4-TR | `@test-runner` spawned (not inline pytest) | | |
| 4-CR | `@code-reviewer` spawned before commit | | |
| 4-GA | `@greeks-analyst` spawned (if `src/paper/` or Greeks touched) | | |
| 4-RV | `@roll-validator` spawned (if roll logic touched) | | |
| 5a | Docs updated: CONTEXT.md / DECISIONS.md / TODOS.md | | |
| 5b | Tests confirmed green before commit | | |
| 5c | Commit executed (not drafted) + SHA confirmed | | |

### Classification rules

**Mark LEGITIMATE SKIP when:**
- Session was a query or read-only task (steps 2–5 don't apply to any of it)
- Step 3b: single-file Claude task where routing was unambiguous
- Step 2b: no load-bearing design decision involved (most mechanical implementation tasks)
- Step 4-GA / 4-RV: those modules were not touched this session

**Mark VIOLATION when:**
- A `src/` file was `Read` without a prior graph query for the same symbol
- pytest was run inline via bash instead of spawning `@test-runner`
- Commit was made without spawning `@code-reviewer` on financial logic, or without persona adoption + `REVIEW.md` on non-financial logic
- Step 3 was skipped — implementation started immediately after CONTEXT.md read with no plan stated
- SHA was not confirmed after commit (commit skill Step 5c skipped)
- CONTEXT.md was not updated after new files or modules were added

---

## Step 3 — Token efficiency audit

### 3a — Rule 0 violations (graph before Read)

List every `Read` call on a `src/` or `scripts/` path this session. For each, state whether
a graph query was attempted first. Count violations.

```
Rule 0 violations: N
  - src/module/file.py: Read without prior graph query
    → should have used: get_code_snippet("ClassName") or search_graph("function_name")
```

Token cost reference: a full-file Read on a 100-line file ≈ 400 tokens, persisting all session.
A targeted `get_code_snippet` for the same symbol ≈ 30–80 tokens. Delta per violation: ~320–370 tokens.

### 3b — Rule 1 violations (bash output discipline)

Check any SQL queries or log reads that ran this session. Flag:
- `SELECT *` or full table dumps without `LIMIT` or aggregation
- `cat` on log files instead of `tail -20` or `grep ERROR`
- `pytest -v` for a full suite run (not debugging a specific test failure)

```
Rule 1 violations: N
  - SELECT * on trades table (15 rows × 20 cols ≈ 300 tokens) — should have been SUM/COUNT
  - cat logs/snapshot.log — should have been tail -20 or grep ERROR
```

### 3c — AutoTrigger compliance

```
Agents spawned:   @test-runner [yes/no] | @code-reviewer [yes/no] | @greeks-analyst [N/A or yes/no]
Agents inlined:   pytest run inline [yes/no] | review inlined [yes/no]
```

Note: inlining an agent does not save tokens — the diff or test output is still processed.
It only forfeits the isolation guarantee and blocking gate semantics. No upside.

### 3d — Avoidable re-reads

List any files that were Read more than once this session, or Read when their content was
already present in context (e.g. CONTEXT.md re-read mid-session after Step 1).

```
Avoidable re-reads: N
  - CONTEXT.md re-read mid-session (already loaded at Step 1)
```

---

## Step 4 — Improvement suggestions

Based only on violations and patterns actually observed this session, produce 2–4 suggestions.
Do not generate generic advice if the session was clean.

Format each suggestion as:

```
[SUGGESTION] <category>: <one-sentence action>
  Why it matters: <one sentence on token or correctness impact>
  Next session trigger: <the exact situation where this applies>
```

Categories: `token-efficiency` | `protocol-compliance` | `agent-routing` | `commit-hygiene`

If the session was clean: state "No suggestions — session followed protocol." and stop.

---

## Step 4b — Rank into `suggestions.md` (repo root)

Every suggestion from Step 4 is a candidate row in `suggestions.md` at the repo root — a
running, cross-session tally of which inefficiency patterns actually recur, so the count is a
"how many times would fixing this have helped" ranking, not a one-off printout that gets
forgotten next session.

1. Read `suggestions.md` if it exists (create it with the header below if not).
2. For each Step 4 suggestion, decide whether it matches an **existing row's `Slug`** — same
   root cause, not just similar wording (e.g. "ran pytest inline" and "skipped test-runner
   agent" are the same slug, `pytest-inlined-not-test-runner`). Match on meaning, not string
   equality; the slug column exists precisely so this judgment call only has to be made once
   per pattern, then it's a deterministic key.
3. **Match found:** increment `Count`, update `Last seen` to today's date, leave `Slug` and
   `Suggestion` text untouched (do not rephrase an existing row just because this session's
   wording differs slightly).
4. **No match:** append a new row, `Count = 1`, `First seen = Last seen = today`, a new
   kebab-case `Slug` that names the root cause (not the symptom).
5. Re-sort the table by `Count` descending, ties broken by most recent `Last seen`.
6. Write the file back. Never hand-edit `Count` outside this procedure.

**File format:**

```markdown
# Session Efficiency Suggestions — Ranked by Recurrence

> Maintained by `.claude/skills/session-close/SKILL.md` Step 4b. `Count` = number of sessions
> where this exact root cause recurred, i.e. how many times fixing it would have helped — not
> a bug tracker. Sorted by `Count` descending. Do not hand-edit `Count`; the skill owns it.

| Count | Slug | Suggestion | Category | First seen | Last seen | Example |
|---|---|---|---|---|---|---|
| N | kebab-case-root-cause | One-sentence action | token-efficiency | YYYY-MM-DD | YYYY-MM-DD | task/session ref |
```

If Step 4 produced no suggestions (clean session), do not touch `suggestions.md` at all.

---

## Step 5 — Produce the final report block

Output this compact block. One screen maximum.

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SESSION CLOSE — <YYYY-MM-DD> — <one-line task description>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

PROTOCOL COMPLIANCE
  Steps followed:    <count> / 14
  Legitimate skips:  <count> — <comma-separated step IDs>
  Violations:        <count> — <comma-separated step IDs>

  Violations detail:
    ❌ Step <ID> (<name>): <reason — one line>
    ❌ Step <ID> (<name>): <reason — one line>

TOKEN EFFICIENCY
  Rule 0 violations:  <count>  (~<N> avoidable tokens)
  Rule 1 violations:  <count>  (~<N> avoidable tokens)
  Avoidable re-reads: <count>  (~<N> avoidable tokens)
  AutoTrigger gaps:   <count> agent(s) inlined instead of spawned

  Estimated avoidable token load: ~<total> tokens this session

SUGGESTIONS
  [SUGGESTION] <category>: <action>
    Why it matters: ...
    Next session trigger: ...
    suggestions.md: <new row | incremented "<slug>" to N>

  Top recurring (suggestions.md): <slug> ×<count>, <slug> ×<count>

COMMIT
  SHA: <hash — or "no commit this session">
  Tests at close: <N> passed, <N> failed
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

If no violations and no token issues: output "Clean session." and omit empty sections.

---

## Quick reference — step IDs

| ID | Name | Applies when |
|---|---|---|
| 0 | Rule 0 (graph before Read) | Any `src/` or `scripts/` file accessed |
| 1 | CONTEXT.md read | Every session |
| 2 | Scope confirmed | Prompt did not name specific files |
| 2b | Council checkpoint | Any task prompt received |
| 3 | Plan + go-ahead | Any implementation task |
| 3b | Routing decision | Any implementation task |
| 4 | Tests written | Any new or changed public function |
| 4-TR | test-runner spawned | Any code file edited |
| 4-CR | code-reviewer spawned | Any commit touching code |
| 4-GA | greeks-analyst spawned | `src/paper/`, option chain, or Greeks fields touched |
| 4-RV | roll-validator spawned | Roll logic or `scripts/roll_leg.py` touched |
| 5a | Docs updated | New files added or module invariants changed |
| 5b | Tests green before commit | Any commit |
| 5c | Commit executed + SHA | Any commit |

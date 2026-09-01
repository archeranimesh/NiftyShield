# Token Efficiency — Suggestions Sweep — tasks

Work top-down. Find the first unchecked `- [ ]` and do only that task. Each task = one commit.
See `prompt.md` for why the story exists and its hard constraints; see `stories.md` for the
per-task implementation spec.

**Open: SWEEP-1 (next), SWEEP-2, SWEEP-3, SWEEP-4, SWEEP-5, SWEEP-6, SWEEP-7.**

SWEEP-1 must land first (it defines the clusters every later task closes). SWEEP-2..SWEEP-6
are independent of each other. SWEEP-7 rebases onto `fixed-overhead/` FIX-3 — do it after
FIX-3 has landed, or note in its commit that FIX-3 is still pending and a rebase is owed.

- [ ] **SWEEP-1** — Cluster every `suggestions.md` row into ~7 groups; write the cluster map + each row's outcome (fix / enforce / accept + reason) into the SWEEP-1 As-built |
      Owner: Claude | Model: claude-sonnet-5 | Review: none | SHA: <—>
- [ ] **SWEEP-2** — Read/discovery cluster: `PreToolUse` hooks — warn on a re-`Read` of an already-read path, and on wide unscoped `grep`/`sed` over a large file; reinforce graph-first text |
      Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: <—>
- [ ] **SWEEP-3** — Test-run cluster: hook nudging `test-runner` for main-session full-suite `pytest`; amend the AutoTrigger cadence to once-before-commit |
      Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: <—>
- [ ] **SWEEP-4** — Commit-flow cluster: `scripts/dev/commit_preflight.py` (staged-index, `ruff format --check`, md-line-length, next-marker, `<pending>`-SHA policy) wired into the `commit` skill |
      Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: <—>
- [ ] **SWEEP-5** — MCP / tool-param cluster: document the `codebase-memory-mcp` required-params, the `AskUserQuestion` plain-array rule, and the "don't `ScheduleWakeup`-poll a spawned agent" rule |
      Owner: Claude | Model: claude-sonnet-5 | Review: none | SHA: <—>
- [ ] **SWEEP-6** — Shell + subagent-orchestration + residual protocol-discipline rows: targeted text fixes in `CLAUDE.md` and the relevant skills; the pure-judgement rows accepted with a reason |
      Owner: Claude | Model: claude-sonnet-5 | Review: none | SHA: <—>
- [ ] **SWEEP-7** — Rewrite `session-close` Step 4b: a `Count >= 5` slug escalates to a `technical-debt/` item or an accepted-row and leaves the active list; seed the over-threshold slugs |
      Owner: Claude | Model: claude-sonnet-5 | Review: none | SHA: <—>

## Story done when

- **SWEEP-1** — every `suggestions.md` row present at epic start appears in exactly one
  cluster in `stories.md` with a stated intended outcome; the cluster count and grouping
  match what SWEEP-2..SWEEP-7 actually deliver.
- **SWEEP-2** — the two `PreToolUse` hooks fire warn-only against their cited example
  patterns and stay silent on scoped reads/greps; tests cover both directions; the
  read/discovery cluster's rows are marked closed in the cluster map.
- **SWEEP-3** — the full-suite-`pytest` hook nudges toward `test-runner`; the AutoTrigger
  rule text says "once before commit"; `pytest-inlined-not-test-runner` and
  `full-suite-run-for-docs-only-change` are closed.
- **SWEEP-4** — `commit_preflight.py` runs the five checks, is invoked by the `commit` skill
  before staging, has happy-path + failing-case tests; the commit-flow cluster rows are
  closed (or accepted with reason for any that a preflight cannot catch).
- **SWEEP-5** — the required-param / `AskUserQuestion` / `ScheduleWakeup` rules are written
  where a session will see them before making the call; those rows are closed.
- **SWEEP-6** — the shell / subagent / discipline rows have their text fixes in place; the
  ones that are pure model judgement are marked "accepted" with a one-line reason.
- **SWEEP-7** — Step 4b of the (FIX-3-redesigned) `session-close` skill escalates a
  `Count >= 5` slug into a tracked item and removes it from the active list; the
  over-threshold slugs as of this task are seeded into `technical-debt/` or the accepted
  list; `suggestions.md` has a documented drain path.

## After each task

Set `SHA:` to the real commit SHA on the task line and tick the box. Update the epic
`README.md` **Stories** table status column (`suggestions-sweep/` row) and add one line to
`TODOS.md` Session Log. Where the task landed a structural fix, record the measured token
delta in that task's As-built in `stories.md`. When the whole story is done, follow
`docs/plan/README.md` §Conventions *Completion → archive* for the whole epic once
`fixed-overhead/` is also complete.

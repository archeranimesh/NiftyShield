# Token Efficiency — Suggestions Sweep — prompt

> Take the entire `suggestions.md` backlog — ~40 rows of recurring session-efficiency root
> causes — and give every one an outcome: a structural fix landed, a hook/config that
> enforces it, or an explicit "accepted, won't-fix" with a reason. Then make Step 4b of the
> session-close skill self-draining so the log stops growing without ever shrinking.

Read `CONTEXT.md` and state `CONTEXT.md ✓` before anything else. Then read `tasks.md`, find
the first unchecked `- [ ]`, and do **only** that task. Read that task's full spec in
`stories.md` (same task id) before writing any code. One task per session. Complete it fully.
Stop.

## Why this story exists

`suggestions.md` is maintained by `.claude/skills/session-close/SKILL.md` Step 4b: each
session's efficiency slips are logged as rows keyed by root cause, with a `Count` of how many
sessions hit the same one. It is sorted by `Count` descending and never drains.
`reread-file-already-in-context` is at Count 13, `pytest-inlined-not-test-runner` at Count 7,
`wide-grep-dump-then-page` at Count 6 — a month of the same mistakes logged and never fixed.

The log is doing its job; the loop around it is broken. There is no step that turns a
high-count slug into remediation, and most slugs describe a behaviour a hook or a preflight
check could catch mechanically rather than nagging the model each session.

## Scope guard

**In bounds:** `suggestions.md` (as input — the `Count` column stays skill-owned), new
`.claude/hooks/` + `scripts/dev/hooks/` checks, `scripts/dev/commit_preflight.py`,
`.claude/skills/commit/SKILL.md`, `.claude/skills/session-close/SKILL.md` (Step 4b only —
FIX-3 owns how the skill runs), targeted text fixes in `CLAUDE.md` / other skills, and
`docs/plan/technical-debt/` (destination for escalated slugs).

**Out of bounds:** the `CLAUDE.md` skill-ification (that is `fixed-overhead/` FIX-1) and how
`session-close` runs (FIX-3). This story only rewrites Step 4b's escalation content and
rebases onto FIX-3's redesigned skill.

## Session-start load hints

- Epic `README.md` Baseline section — SWEEP tasks that land a fix quote the measured delta
  against it.
- `suggestions.md` in full — SWEEP-1 clusters it; every later SWEEP task closes the rows in
  its cluster.
- `.claude/hooks/` — read `guard_src_reads.sh` and one Python check in `scripts/dev/hooks/`
  for the house pattern (thin `.sh` shim → testable Python).
- `.claude/skills/commit/SKILL.md` and `.claude/skills/session-close/SKILL.md` — read fully
  before SWEEP-4 / SWEEP-7.
- `docs/plan/technical-debt/prompt.md` — the "fix only when already there" convention;
  SWEEP-7's escalated items are the marked exception.
- No `schema.md` — no DB work.

## Hard constraints

- **Every row gets an outcome.** By the end of the story, each `suggestions.md` row present
  at epic start is: (a) fixed structurally — the mistake is no longer possible; (b) enforced
  — a hook or preflight check warns when it happens; or (c) accepted — a one-line reason why
  it stays a model-discipline item, recorded in the cluster map. No row is left untouched.
- **Hooks warn, never block** — stderr guidance, exit 0. Match the existing `.claude/hooks/`
  contract. A hook with a real false-positive rate is worse than none; tune against the
  cited examples in each row before shipping.
- **`Count` is skill-owned** — no task hand-edits it. SWEEP-7 changes the maintenance logic;
  the running tally stays the skill's.
- **Test gate (blocking):** `python -m pytest tests/unit/ --tb=no -q` green before commit.
  New Python hooks / `commit_preflight.py` get their own tests under
  `tests/unit/scripts/dev/hooks/`.
- **Graph-before-Read** for any `src/` / `scripts/` file.

## Task overview

- `SWEEP-1` — cluster all ~40 rows into ~7 groups; write the cluster map + per-row intended
  outcome into `stories.md`.
- `SWEEP-2` — read/discovery cluster → `PreToolUse` hooks (re-Read of a path already read;
  wide unscoped `grep`/`sed` over large files) + graph-first text.
- `SWEEP-3` — test-run cluster → `PreToolUse` hook nudging `test-runner` for main-session
  full-suite `pytest`; amend the AutoTrigger rule to "once before commit, not per-edit".
- `SWEEP-4` — commit-flow cluster → `scripts/dev/commit_preflight.py` wired into the
  `commit` skill (staged-index, `ruff format --check`, md-line-length, next-marker points at
  an unchecked id, SHA-placeholder policy).
- `SWEEP-5` — MCP / tool-param cluster → documented required-params + `AskUserQuestion`
  plain-array rule + `ScheduleWakeup`-poll rule; cheap wrappers where they pay.
- `SWEEP-6` — shell + subagent-orchestration + residual protocol-compliance rows → targeted
  text fixes in the relevant skills / `CLAUDE.md`.
- `SWEEP-7` — rewrite Step 4b: a slug at `Count >= 5` is converted to a tracked
  `technical-debt/` `DEBT-*` item (or an "accepted, won't-fix" row with a reason) and drops
  off the active list. Seed the currently-over-threshold slugs.

## Definition of done

Mirrors `tasks.md` "## Story done when". In short: every `suggestions.md` row is in a
documented cluster with an outcome; the read/test/commit clusters have working warn-only
enforcement with tests; the MCP/shell/discipline rows have their text fixes; and Step 4b now
escalates and retires high-count slugs instead of only incrementing them.

## Perspectives not covered

- **False-negative cost of the new hooks.** A warn-only hook the model learns to ignore is
  near-useless. Whether these hooks change behaviour, or just add noise, can only be judged
  by re-running `token_audit.py` on sessions after they land — a follow-up check, not part of
  a task's DoD.
- **The pure-discipline rows.** `plan-gate-skipped`, `scope-question-jumped-ahead`,
  `clarify-questions-before-context-gather` describe judgement the model must exercise;
  SWEEP-6 documents them but cannot mechanically prevent them. If they keep recurring after
  this epic, that is a model-capability signal, not a tooling gap.

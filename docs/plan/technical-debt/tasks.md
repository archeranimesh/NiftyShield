# Technical Debt — Tasks

**These are not a sequence.** Unlike every other story in `docs/plan/`, do not pick these up on their own — each is fixed **only** when you are already touching the same file or module for an
unrelated reason. Never a standalone commit. See `prompt.md` for the exact trigger condition per item.

**Exception — `standalone-actionable` items.** `DEBT-3` and the `DEBT-8`+ block (seeded by `session-close` Step 4b when a `suggestions.md` slug crosses Count 5) are explicitly allowed to be their own
commit — they are proactive verification/reconciliation work, not opportunistic cleanup. Every other item stays opportunistic.

- [ ] **DEBT-3** — License boilerplate: decision needed before automation. Every file gets a header once a license is chosen. Blocked on a decision, not on code — see `stories.md`.
  | Owner: Claude | Model: n/a | Review: none
- [ ] **DEBT-5** — `test_bhavcopy_ingest.py` missing append-path coverage. Trigger: next time `test_bhavcopy_ingest.py` or `write_to_parquet`'s merge branch is touched for another reason.
  | Owner: Claude | Model: n/a | Review: none
- [ ] **DEBT-6a** — Move hardcoded expiry whitelist (`{2026-04-07, 2026-12-29}`) from `Leg` to `market_calendar` YAML. Trigger: next time `Leg` construction or `market_calendar` is touched.
  | Owner: Claude | Model: n/a | Review: none
- [ ] **DEBT-6b** — Holiday YAML datasets for 2017–2025 missing in `src/market_calendar/data/` — historical `Leg` construction pre-2026 fails open. Trigger: next time historical/backtest `Leg`
  construction is touched (this one is also a real prerequisite for `docs/plan/backtest-engine/phase1/` tasks that construct pre-2026 `Leg`s — flag it if hit there).
  | Owner: Claude | Model: n/a | Review: none
- [ ] **DEBT-6c** — Formalise `is_nifty` check: replace denylist with an `instrument_key`-based predicate. Trigger: next time the `is_nifty` denylist is touched.
  | Owner: Claude | Model: n/a | Review: none
- [ ] **DEBT-7** — Refactor dynamic dispatch in `daily_snapshot.py` to eliminate `noqa: F401` unused-import suppressions (they hide broken imports if helpers are renamed/moved). Trigger: next time
  `daily_snapshot.py`'s dynamic-dispatch block is touched.
  | Owner: Claude | Model: n/a | Review: none

- [x] **DEBT-8** — `standalone-actionable`. Verify the SWEEP-2 `check_repeat_read.py` hook is effective against `reread-file-already-in-context` (Count 23 at escalation, 2026-09-03). Trigger:
  standalone once 3 sessions are logged after `68683cb`; if the slug still recurs, escalate to a protocol/model discussion. Verified NOT effective — slug recurred 34x through 2026-09-11, warn-only
  never stopped it; escalated to a protocol/model discussion (see `DECISIONS.md`), resolved by making the hook blocking (exit 2). | Owner: Claude | Model: claude-sonnet-5 | Review: none | SHA:
  <pending>
- [x] **DEBT-9** — `standalone-actionable`. Verify the SWEEP-3 `check_inline_full_suite.py` hook + the "once before commit" AutoTrigger cadence are effective against `pytest-inlined-not-test-runner`
  (Count 9 at escalation, 2026-09-03). Trigger: standalone once 3 sessions are logged after `e325e86`; escalate if still recurring. Verified NOT effective — slug recurred to Count 17 through
  2026-09-11, warn-only never stopped it; escalated to a protocol/model discussion (see `DECISIONS.md`), resolved by making the hook blocking (exit 2), mirroring DEBT-8. | Owner: Claude | Model:
  claude-sonnet-5 | Review: none | SHA: 300f5b8
- [x] **DEBT-10** — `standalone-actionable`. Verify the SWEEP-2 `check_wide_grep.py` hook is effective against `wide-grep-dump-then-page` (Count 7 at escalation, 2026-09-03). Trigger: standalone once
  3 sessions are logged after `68683cb`; escalate if still recurring. | Owner: Claude | Model: claude-sonnet-5 | Review: none | SHA: dc8fcc6
- [x] **DEBT-11** — `standalone-actionable`. `sha-recorded-via-second-commit` (Count 6 at escalation, 2026-09-03) is a protocol conflict, not a per-session lapse: the SWEEP-4 `commit` skill Step 1b
  `<pending>`-then-backfill policy contradicts some `tasks.md` folders' "one commit plus a follow-up" convention. Reconcile the two into one repo-wide policy, then verify `commit_preflight.py`'s
  SHA-placeholder warning is heeded. Trigger: standalone. | Owner: Claude | Model: claude-sonnet-5 | Review: none | SHA: c2d3af4
- [x] **DEBT-12** — `standalone-actionable`. Verify the SWEEP-4 `commit_preflight.py` staged md-line-length check is effective against `authored-md-prose-over-200-cap` (Count 5 at escalation,
  2026-09-03). Trigger: standalone once 3 sessions are logged after `2b85b84`; escalate if still recurring. | Owner: Claude | Model: claude-sonnet-5 | Review: none | SHA: 9b25bc2
- [x] **DEBT-13** — `standalone-actionable`. `next-marker-points-at-just-closed-task` (Count 5 at escalation, 2026-09-06). `check_checkbox_consistency.py` exists but is blind to the epic-row shape in
  `docs/plan/README.md` (a `<epic>/` line carrying `<sub-story>/ next: **ID**` for a nested `strategy-rollout/tasks.md`) — `--all` exits 0 with ROLL-14 checked and the README row still reading `next:
  **ROLL-14**`. Extend the guard's `README_ENTRY_RE` / resolution to follow the sub-story pointer, then verify. Trigger: standalone. | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer |
  SHA: bed9d0b
- [ ] **DEBT-14** — `standalone-actionable`. `context-tree-row-missing-for-new-module` (Count 5 at escalation, 2026-09-07). No mechanical catch exists: a session adds `src/<module>/` code (new dir, or
  a new file in an under-documented module) and closes without adding the `CONTEXT_TREE.md` row / `CONTEXT.md` "What Exists" line. `src/signals/` has had this gap open since S1.1 across four stories.
  Add a pre-commit / preflight audit that diffs `src/*/` and `scripts/*/` dirs against the anchors present in `CONTEXT_TREE.md`, then verify against the `src/signals/` backfill. Trigger: standalone. |
  Owner: Claude | Model: claude-sonnet-5 | Review: none
- [x] **DEBT-15** — `standalone-actionable`. Verify the SWEEP-4 `commit_preflight.py` staged `ruff format --check` blocker is effective against `ruff-format-check-skipped-precommit-abort` (Count 5 at
  escalation, 2026-09-08). It caught the S5.3 case (`✗ ruff-format` on `record_signal_outcome.py` before the commit) but still cost a `ruff format` + re-stage cycle because only `ruff check` + an
  `awk` length sweep were run pre-stage. Trigger: standalone once 3 sessions are logged after `2b85b84`; escalate if still recurring.
  | Owner: Claude | Model: claude-sonnet-5 | Review: none | SHA: e3b943f
- [ ] **DEBT-16** — `standalone-actionable`. Verify the Rule 0 `.claude/hooks/guard_src_reads.sh` PreToolUse hook is effective against `rule0-read-over-graph-hook-ignored` (Count 5 at escalation,
  2026-09-10). The hook is warn-only by design and has not stopped the pattern: a session greps a `src/`/`scripts/` file then issues a full-file `Read` instead of pivoting to `get_code_snippet` / a
  targeted `sed -n` or stating why the graph is insufficient. Decide whether the hook should block (or emit a stronger reminder), then verify. Trigger: standalone once 3 sessions are logged after this
  line lands; escalate to a protocol/model discussion if still recurring. | Owner: Claude | Model: claude-sonnet-5 | Review: none
- [ ] **DEBT-17** — `standalone-actionable`. `scheduleWakeup-poll-spawned-agent` (Count 5 at escalation, 2026-09-14). No mechanical catch exists yet: a session repeatedly calls `ScheduleWakeup` to
  poll a subagent it just spawned (`test-runner` / `code-reviewer`) instead of ending the turn and letting the harness's task-notification re-invoke it. Add a PreToolUse hook that warns (or blocks) on
  a `ScheduleWakeup` call issued while an `Agent` spawn from the same turn is still outstanding, then verify against the UXM-2 case (3 `ScheduleWakeup` calls back-to-back after the `test-runner` +
  `code-reviewer` spawns). Trigger: standalone. | Owner: Claude | Model: claude-sonnet-5 | Review: none
- [ ] **DEBT-18** — `standalone-actionable`. `context-md-skipped-on-escalated-ops-task` (Count 5 at escalation, 2026-09-14). No mechanical catch exists: an ops/diagnostic session (crontab check, log
  triage, "why did this fire") turns into a `src/`/`scripts/` code change mid-session, and `CONTEXT.md` is never read even though Step 1 applies the moment code enters scope, not just at session
  start. Add a PreToolUse hook that tracks whether `CONTEXT.md` has been `Read` this session and warns (or blocks) on the first `Edit`/`Write` to `src/`/`scripts/` if not, then verify against the
  NSE-2026-holiday-fix case (yaml + test edit landed with no `CONTEXT.md` read all session). Trigger: standalone. | Owner: Claude | Model: claude-sonnet-5 | Review: none
- [ ] **DEBT-19** — `standalone-actionable`. `readme-story-pointer-not-advanced-on-task-close` (Count 5 at escalation, 2026-09-23). `check_checkbox_consistency.py`'s `README_ENTRY_RE` validates that a
  `next: **<ID>**` marker exists in the right shape, but does not verify the ID still names the actual next unstarted task once earlier tasks close — S3.1, S5.6, SEC-1, M1.2, and M3.2 (mvp) all closed
  a task in `tasks.md` while leaving `docs/plan/README.md`'s pointer on an already-completed ID. Extend the guard to cross-check the README pointer against the first unchecked box in the story's own
  `tasks.md`, then verify over the next 3 logged sessions. If it still recurs, escalate to a protocol/model discussion. Trigger: standalone. | Owner: Claude | Model: claude-sonnet-5 | Review: none

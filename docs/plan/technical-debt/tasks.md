# Technical Debt — Tasks

**These are not a sequence.** Unlike every other story in `docs/plan/`, do not pick these up on
their own — each is fixed **only** when you are already touching the same file or module for an
unrelated reason. Never a standalone commit. See `prompt.md` for the exact trigger condition per
item.

**Exception — `standalone-actionable` items.** `DEBT-3` and the `DEBT-8`+ block (seeded by
`session-close` Step 4b when a `suggestions.md` slug crosses Count 5) are explicitly allowed to
be their own commit — they are proactive verification/reconciliation work, not opportunistic
cleanup. Every other item stays opportunistic.

- [ ] **DEBT-3** — License boilerplate: decision needed before automation. Every file gets a
  header once a license is chosen. Blocked on a decision, not on code — see `stories.md`.
- [ ] **DEBT-5** — `test_bhavcopy_ingest.py` missing append-path coverage. Trigger: next time
  `test_bhavcopy_ingest.py` or `write_to_parquet`'s merge branch is touched for another reason.
- [ ] **DEBT-6a** — Move hardcoded expiry whitelist (`{2026-04-07, 2026-12-29}`) from `Leg` to
  `market_calendar` YAML. Trigger: next time `Leg` construction or `market_calendar` is touched.
- [ ] **DEBT-6b** — Holiday YAML datasets for 2017–2025 missing in `src/market_calendar/data/` —
  historical `Leg` construction pre-2026 fails open. Trigger: next time historical/backtest `Leg`
  construction is touched (this one is also a real prerequisite for
  `docs/plan/backtest-engine/phase1/` tasks that construct pre-2026 `Leg`s — flag it if hit there).
- [ ] **DEBT-6c** — Formalise `is_nifty` check: replace denylist with an `instrument_key`-based
  predicate. Trigger: next time the `is_nifty` denylist is touched.
- [ ] **DEBT-7** — Refactor dynamic dispatch in `daily_snapshot.py` to eliminate `noqa: F401`
  unused-import suppressions (they hide broken imports if helpers are renamed/moved). Trigger:
  next time `daily_snapshot.py`'s dynamic-dispatch block is touched.

- [ ] **DEBT-8** — `standalone-actionable`. Verify the SWEEP-2 `check_repeat_read.py` hook is
  effective against `reread-file-already-in-context` (Count 23 at escalation, 2026-09-03).
  Trigger: standalone once 3 sessions are logged after `68683cb`; if the slug still recurs,
  escalate to a protocol/model discussion. | Owner: Claude | Model: claude-sonnet-5 | Review: none
- [ ] **DEBT-9** — `standalone-actionable`. Verify the SWEEP-3 `check_inline_full_suite.py` hook +
  the "once before commit" AutoTrigger cadence are effective against
  `pytest-inlined-not-test-runner` (Count 9 at escalation, 2026-09-03). Trigger: standalone once
  3 sessions are logged after `e325e86`; escalate if still recurring. | Owner: Claude | Model: claude-sonnet-5 | Review: none
- [ ] **DEBT-10** — `standalone-actionable`. Verify the SWEEP-2 `check_wide_grep.py` hook is
  effective against `wide-grep-dump-then-page` (Count 7 at escalation, 2026-09-03). Trigger:
  standalone once 3 sessions are logged after `68683cb`; escalate if still recurring. | Owner: Claude | Model: claude-sonnet-5 | Review: none
- [ ] **DEBT-11** — `standalone-actionable`. `sha-recorded-via-second-commit` (Count 6 at
  escalation, 2026-09-03) is a protocol conflict, not a per-session lapse: the SWEEP-4 `commit`
  skill Step 1b `<pending>`-then-backfill policy contradicts some `tasks.md` folders' "one commit
  plus a follow-up" convention. Reconcile the two into one repo-wide policy, then verify
  `commit_preflight.py`'s SHA-placeholder warning is heeded. Trigger: standalone. | Owner: Claude | Model: claude-sonnet-5 | Review: none
- [ ] **DEBT-12** — `standalone-actionable`. Verify the SWEEP-4 `commit_preflight.py` staged
  md-line-length check is effective against `authored-md-prose-over-200-cap` (Count 5 at
  escalation, 2026-09-03). Trigger: standalone once 3 sessions are logged after `2b85b84`;
  escalate if still recurring. | Owner: Claude | Model: claude-sonnet-5 | Review: none
- [ ] **DEBT-13** — `standalone-actionable`. `next-marker-points-at-just-closed-task` (Count 5 at
  escalation, 2026-09-06). `check_checkbox_consistency.py` exists but is blind to the epic-row
  shape in `docs/plan/README.md` (a `<epic>/` line carrying `<sub-story>/ next: **ID**` for a
  nested `strategy-rollout/tasks.md`) — `--all` exits 0 with ROLL-14 checked and the README row
  still reading `next: **ROLL-14**`. Extend the guard's `README_ENTRY_RE` / resolution to follow
  the sub-story pointer, then verify. Trigger: standalone. | Owner: Claude | Model: claude-sonnet-5 | Review: none

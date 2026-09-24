# Technical Debt — Stories

Each entry below only gets fixed opportunistically — see the trigger condition in `tasks.md` and the "Never a standalone commit" rule in `prompt.md`. Full spec here so that when the trigger fires,
there's no need to reconstruct context under time pressure.

## DEBT-3 — License boilerplate

Every file should get a license header once a license is chosen for the project. **This is blocked on a decision, not on code** — do not write header-insertion tooling or pick a license unilaterally.
When Animesh decides, record the choice in `DECISIONS.md` first, then this becomes a mechanical one-time sweep (not "alongside adjacent refactoring" — it's the one exception that can be its own
commit, since it touches every file uniformly by design).

## DEBT-5 — `test_bhavcopy_ingest.py` missing append-path coverage

`write_to_parquet`'s merge branch calls `replace_schema_metadata` when appending to an existing Parquet file (lineage metadata preservation) — this branch has no test today. **Trigger:** next time
`test_bhavcopy_ingest.py` or `write_to_parquet` is touched for another reason (e.g. a `docs/plan/backtest-engine/phase1/` task extending the ingest pipeline).

**Fix:** add a write-twice test — write once, write again with overlapping/adjacent data, assert the second run's lineage metadata (`replace_schema_metadata` output) survives the merge rather than
being dropped or overwritten with defaults. `get_code_snippet("write_to_parquet")` first to confirm current signature before writing the test.

## DEBT-6 — Leg validation + calendar data gaps for historical backtesting

Three related but independently-triggerable sub-fixes, all touching `Leg` construction / `market_calendar`:

**DEBT-6a** — Move the hardcoded expiry whitelist (`{2026-04-07, 2026-12-29}`) from `Leg` to a `market_calendar` YAML file. `search_graph("Leg")` to find the current hardcoded location before touching
it. **Trigger:** next time `Leg` construction or `market_calendar` is touched for another reason.

**DEBT-6b** — Holiday YAML datasets for 2017–2025 are missing in `src/market_calendar/data/` — historical `Leg` construction pre-2026 currently fails open (i.e. treats unknown dates as non-holidays
rather than raising). **Trigger:** next time historical/backtest `Leg` construction is touched — this is a real, not hypothetical, prerequisite for `docs/plan/backtest-engine/phase1/` tasks that
construct pre-2026 `Leg`s (e.g. 1.7's CSP backtest across 2016–present, 1.9a's integrated backtest). If a `backtest-engine/phase1` task hits this gap, treat it as unblocking that task's own trigger —
don't silently work around the fail-open behavior.

**DEBT-6c** — Formalise the `is_nifty` check: replace the current denylist-style substring match with an `instrument_key`-based predicate. Current implementation (confirmed via grep, 2026-07-27):
`src/models/portfolio.py:189` and `src/instruments/lot_size.py:29` both do `"NIFTY" in key_upper and not any(...)` independently — two separate ad-hoc implementations of the same check, not a single
shared denylist. **Trigger:** next time either of those two files is touched for another reason. Fix should consolidate both call sites onto one `instrument_key`-based predicate, not just reformat one
of the two independently.

## DEBT-7 — `daily_snapshot.py` dynamic dispatch `noqa: F401` suppressions

`scripts/portfolio/daily_snapshot.py` uses dynamic dispatch with `# noqa: F401` suppressions on what look like unused imports — these hide real broken imports if the dispatched helpers are ever
renamed or moved (the suppression would silently mask the resulting `ImportError`/`AttributeError` until runtime). **Trigger:** next time `daily_snapshot.py`'s dynamic-dispatch block is touched.

**Fix:** replace the dynamic-dispatch-via-string-import pattern with an explicit registry (e.g. a `dict[str, Callable]` built from direct imports) so unused-import suppressions are no longer needed
and a renamed helper fails at import time, not at dispatch time. `trace_path` on the current dispatch function first to see every call site before restructuring.

## DEBT-8..DEBT-12 — escalated `suggestions.md` slugs (`standalone-actionable`)

Seeded by `token-efficiency` SWEEP-7 (2026-09-03) and, going forward, by `session-close` Step 4b whenever a `suggestions.md` slug crosses **Count 5**. Unlike every other item here these **may be their
own commit** — they are proactive verification, not opportunistic cleanup. Each is a check on whether an already-landed remediation actually changed behaviour; the escalation retired the slug from the
active `suggestions.md` table so it stops being re-logged each session.

**Common procedure for DEBT-8 / -9 / -10 / -12:** run `token_audit.py` over the sessions logged since the cited remediation SHA and grep their `session-close` reports / `TODOS.md` Session Log for the
slug. If it did **not** recur in 3+ such sessions, tick the box — the hook worked. If it recurred, do **not** re-seed a `DEBT-*` line: open a protocol/model discussion (the slug re-enters
`suggestions.md` at Count 1 with an `Escalated:` prefix per Step 4b item 8) and record the outcome in `DECISIONS.md`.

- **DEBT-8** — `reread-file-already-in-context` (Count 23). Remediation: SWEEP-2 `check_repeat_read.py` warn-only `PreToolUse(Read|Edit|Write)` hook (`68683cb`). Residual known gap: the Edit/Write
  prior-read gate still forces a `Read` of a resident file — a harness constraint the hook cannot close; note it in the verification, don't count it against the hook.
- **DEBT-9** — `pytest-inlined-not-test-runner` (Count 9). Remediation: SWEEP-3 `check_inline_full_suite.py` (`e325e86`) + the `test-runner` AutoTrigger cadence amended to "once per task before
  `code-reviewer` / the commit".
- **DEBT-10** — `wide-grep-dump-then-page` (Count 7). Remediation: SWEEP-2 `check_wide_grep.py` (`68683cb`). **Verified (2026-09-11):** the slug has zero recurrence entries in `suggestions.md`'s
  active table across every session since `68683cb` (~8 days, ~250 commits) — far past the 3-session check window. Hook confirmed effective; no protocol discussion needed.
- **DEBT-11** — `sha-recorded-via-second-commit` (Count 6). **Not a hook-effectiveness check — a protocol reconciliation.** The SWEEP-4 `commit` skill Step 1b policy ("land with `SHA: <pending>`,
  backfill as the first edit of the next doc-touch, no swap-only commit") contradicts the "one commit plus a follow-up" convention stated in some `tasks.md` folders (flagged in the `suggestions.md`
  example for MEAS-2). Pick one policy, make it repo-wide (update `docs/plan/README.md` §Conventions and any folder `tasks.md` that says otherwise), record the decision in `DECISIONS.md`, then confirm
  `commit_preflight.py`'s SHA-placeholder warning matches the chosen policy. This one is genuinely standalone — no trigger wait. **Resolved (2026-09-11):** the `<pending>`-then-backfill-next-touch
  policy is the sole repo-wide policy — it was already `README.md` §Conventions and what `commit_preflight.py` enforces. The contradicting line in `root-doc-organization/tasks.md` was corrected to
  match; decision recorded in `DECISIONS.md` (Developer Tooling).
- **DEBT-12** — `authored-md-prose-over-200-cap` (Count 5). Remediation: SWEEP-4 `commit_preflight.py` staged md-line-length check reusing `check_md_line_length.check_file` (`2b85b84`). Un-reflowable
  long `tasks.md` lines remain an accepted residual. **Verified (2026-09-11):** 4 post-`2b85b84` recurrences all show the check firing and the commit aborting before landing (`5aa9ce6`, `b70f8fa`) —
  the blocker works; recurrence is authoring-time cost, not hook failure. `reflow_md.py` (doc-format-migration epic) is the standing remediation for that gap. See `DECISIONS.md` DEBT-12.
- **DEBT-13** — `next-marker-points-at-just-closed-task` (Count 5). Remediation exists but is ineffective for one shape: `check_checkbox_consistency.py`'s `README_ENTRY_RE` matches a flat `<folder>/ …
  next: **ID**` row and flags a pointer at a done id, but an epic row in `docs/plan/README.md` that carries a nested sub-story pointer (`strategy-rollout/ next: **ROLL-14**` while
  `strategy-rollout/tasks.md` has ROLL-14 checked) passes `--all` clean. Extend the guard to resolve the sub-story `tasks.md` for epic rows, then verify against the ROLL-14 close (`eb782d0`, README:43
  left at `next: **ROLL-14**`). Standalone — no trigger wait. **Fixed (2026-09-11):** added `_resolve_pointer_task_file()` — flat `<slug>/tasks.md` first, falling back to a sorted glob of
  `<slug>/**/tasks.md` for the nested file containing `**<id>**`. The cited README repro was already stale (the `telegram-markdown-migration` epic archived 2026-09-06; the current row reads `✅
  Shipped/Archived` with no `next:` marker), so no README correction was needed — verified via two new unit tests reconstructing the epic/nested-sub-story shape directly. See `DECISIONS.md`.
- **DEBT-14** — `context-tree-row-missing-for-new-module` (Count 5). No remediation exists. Every doc-freshness hook proxies "docs behind code" by a src-commit count and never checks whether a
  `src/<module>/` dir has a matching `CONTEXT_TREE.md` row or `CONTEXT.md` "What Exists" line. `src/signals/` was created by an Antigravity handoff at S1.1 (`8d295c6`) and S1.2/S1.3/S2.1 each added
  code (`store.py` at S2.1, `2aa5979`) without ever backfilling the row. Build a `check_context_tree_coverage.py` preflight that lists `src/*/` + `scripts/*/` dirs absent from `CONTEXT_TREE.md`, wire
  it into `commit_preflight.py`, then verify against the `src/signals/` backfill commit. Standalone — no trigger wait.
- **DEBT-15** — `ruff-format-check-skipped-precommit-abort` (Count 5). Remediation: SWEEP-4 `commit_preflight.py` staged `ruff format --check` blocker (`2b85b84`). It fires before the commit rather
  than letting the pre-commit hook abort it, but a `ruff format` + re-stage cycle still costs a round trip when only `ruff check` + an `awk` length sweep were run pre-stage (S5.3: `✗ ruff-format` on
  `record_signal_outcome.py`). Run `token_audit.py` / grep session-close reports over the 3 sessions after `2b85b84`; if the slug did not recur, tick the box. If it recurred, open a protocol/model
  discussion — likely folding `ruff format` into the standard pre-stage checklist. Standalone — no trigger wait. **Verified (2026-09-11):** one post-`2b85b84` recurrence (S5.2c, `b33a43d`), then none
  across the dozens of sessions since — the check fired and the commit aborted correctly both times cited (S5.2c, S5.3); the blocker works, the residual is a pre-stage-checklist cost, not hook
  failure. See `DECISIONS.md` DEBT-15.
- **DEBT-16** — `rule0-read-over-graph-hook-ignored` (Count 5). Remediation: the Rule 0 `.claude/hooks/guard_src_reads.sh` PreToolUse hook, which fires on every `Read` of a `src/` or `scripts/` path.
  It is warn-only by design ("It will not block — the decision is yours") and has not stopped the pattern across five sessions: BUG-041, S5.5d, signals-cost-tracking planning + SCT-1, and the
  read-path `init_db` cron fix (2026-09-10) each grepped a `src/`/`scripts/` file then issued a full-file `Read` rather than pivoting to `get_code_snippet` / a targeted `sed -n 'N,Mp'` or stating in
  one line why the graph was insufficient. Decide whether the hook should block on a missing prior graph/snippet call (or emit a harder-to-ignore reminder), implement, then verify over the next 3
  logged sessions. If it still recurs, escalate to a protocol/model discussion. Standalone — no trigger wait.
- **DEBT-17** — `scheduleWakeup-poll-spawned-agent` (Count 5). No remediation exists. Across ROLL-4, S5.2a, DEBT-9's escalation session, SEC-4 close, and this UXM-2 exit-message session, a session
  spawns `@test-runner` / `@code-reviewer` and then calls `ScheduleWakeup` one or more times to poll for their completion instead of simply ending the turn — the harness re-invokes on
  task-notification automatically, so the wakeup is pure waste. Build a PreToolUse hook that flags a `ScheduleWakeup` call made while an `Agent` spawn from the same turn has not yet returned, then
  verify over the next 3 logged sessions. If it still recurs, escalate to a protocol/model discussion. Standalone — no trigger wait.
- **DEBT-18** — `context-md-skipped-on-escalated-ops-task` (Count 5). No remediation exists. Across session-close S4c, a nuvama crontab session, an escaping-guard/telegram-env session, a ruff
  lint-sweep + llm-council session, and this NSE-2026-holiday-fix session, an ops/diagnostic task that turns into a `src/`/`scripts/` code change mid-session lands the edit without ever reading
  `CONTEXT.md`, even though Step 1 applies the moment code enters scope. Build a PreToolUse hook that tracks per-session whether `CONTEXT.md` has been read and warns (or blocks) on the first
  `Edit`/`Write` to `src/`/`scripts/` if not, then verify over the next 3 logged sessions. If it still recurs, escalate to a protocol/model discussion. Standalone — no trigger wait.
- **DEBT-19** — `readme-story-pointer-not-advanced-on-task-close` (Count 5). No remediation exists. `check_checkbox_consistency.py`'s `README_ENTRY_RE` only validates that a `next: **<ID>**` marker is
  present in the right literal shape; it never cross-checks that ID against the story's own `tasks.md` to see whether that task has since closed. Across S3.1, S5.6, SEC-1, M1.2, and M3.2 (mvp), a task
  closed with its `tasks.md` checkbox ticked and SHA recorded, yet `docs/plan/README.md`'s pointer for that story kept naming the already-completed task. Extend the guard's resolution to follow the
  pointer into the story's `tasks.md` and flag a mismatch, then verify over the next 3 logged sessions. If it still recurs, escalate to a protocol/model discussion. Standalone — no trigger wait.
- **DEBT-20** — `scripts-read-before-graph-query` (Count 5). Remediation already tracked under DEBT-16: the Rule 0 `.claude/hooks/guard_src_reads.sh` PreToolUse hook is warn-only and does not stop a
  full `Read` of a `src/`/`scripts/` file from landing before a graph query for that specific file's symbols — graph calls made for unrelated symbols elsewhere in the same session do not satisfy Rule
  0 for this file. Latest case: M13.1 mvp session — `src/mvp/backfill.py` read directly while the session's `search_graph`/`get_code_snippet` calls all targeted `MVPStore`/`CategoryStats`/`Pick`. This
  is the same hook-effectiveness gap as DEBT-16; do not fix independently. Standalone once DEBT-16 lands a fix — re-verify both slugs together.

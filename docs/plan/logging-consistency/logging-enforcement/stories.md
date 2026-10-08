
# Logging Enforcement — story specs

> One task per session. Find the first unchecked item in `tasks.md`. That is your only task. Full implementation rules in `CLAUDE.md` and `REVIEW.md`. After each task: set `SHA:` on the task line +
> tick the box, update the story status summary, add one line to `TODOS.md`. See `docs/plan/README.md` §Conventions.

## LE-1 — Pre-commit check: every cron entrypoint uses `run_entrypoint

**Files:** `scripts/dev/check_logging_entrypoint.py`, tests, `.pre-commit-config.yaml`. **Implement:** AST check over `scripts/`; the allowlist is explicit and small. Model it on the existing
`no-script-main-logger` hook. **Tests:** one pass and one fail fixture each. **Commit:** `chore(hooks): require runner or setup_logging in entrypoints`

---

## LE-2 — Pre-commit check: no `print(` in `src/` or cron-invoked scri

**Files:** `scripts/dev/check_no_print.py`, a baseline file, tests, `.pre-commit-config.yaml`. **Implement:** cron-invoked is decided by `run_entrypoint(kind="cron")` in the file. The baseline stores
a per-file count; a commit that raises a count fails. **Tests:** `test_print_in_src_fails`, `test_cron_script_print_fails`, `test_interactive_within_baseline_passes`,
`test_interactive_above_baseline_fails`. **Commit:** `chore(hooks): ban print in src and cron scripts`

---

## LE-3 — Event-name and field-vocabulary lint

**Files:** `scripts/dev/check_log_vocabulary.py`, a vocabulary file (`instrument_key`, `strategy_name`, `trade_date`, `expiry`, `run_id`, `job`, `duration_ms`), tests, `.pre-commit-config.yaml`.
**Implement:** AST check of structlog calls: event is a lowercase dotted literal per `LOGGING.md`, no f-strings, kwargs from the vocabulary or an explicit allow. **Commit:** `chore(hooks): lint log
event names and field keys`

---

## LE-4 — Contract tests

**Files:** `tests/unit/test_log_contracts.py` plus a small capture helper. **Implement:** from `LOGGING.md`'s silent-failure section and LF-1's audit, list the degrade branches (missing LTP, fail-open
guards, swallowed sends) and assert each logs its event. Add the capture helper only if one does not exist. **Commit:** `test(logging): assert silent-failure branches log`

---

## LE-5 — Rewrite `LOGGING.md`; reconcile `docs/refactor/logging-and-c

**Files:** `LOGGING.md`, `docs/refactor/logging-and-correlation-id.md` (per the DG-3 verdict), `.claude/agents/code-reviewer.md`. **Implement:** replace the migration checklist with the standing
rules; state the print policy (interactive result output allowed, cron-invoked never); add two reviewer items (entrypoint uses the runner, no `print` in cron code). **Commit:** `docs(logging): rewrite
standard around the runner`

---

## LE-6 — `logs/` file naming, rotation and retention convention

**Files:** `LOGGING.md` section, the cron redirect lines (documented, as the crontab is not in the repo). **Implement:** per-job file name, size or age rotation, retention window; note that `run_id`
joins a log line to its `job_runs` row. **Commit:** `docs(logging): define logs directory layout and retention`


# Logging Foundation — story specs

> One task per session. Find the first unchecked item in `tasks.md`. That is your only task. Full implementation rules in `CLAUDE.md` and `REVIEW.md`. After each task: set `SHA:` on the task line +
> tick the box, update the story status summary, add one line to `TODOS.md`. See `docs/plan/README.md` §Conventions.

## LF-1 — Audit: classify `print(` calls and entrypoints; verify the `

**Files:** `docs/plan/logging-consistency/audit.md` (new). **Input from Animesh:** a redacted `crontab -l` from the Mac host, since the repo has no crontab file and the cron-versus-interactive split
drives the print policy. **Before any code:** `grep -rc --include='*.py' '^\s*print(' src scripts` for counts; `sed -n` on `src/utils/logging.py` (164 lines) for the renderer; `LOGGING.md` migration
checklist against `git log` to see which boxes are stale. **Implement:** table of every file with `print(` (count, cron-invoked or interactive, diagnostic or result output); list of scripts that never
call `setup_logging()`; renderer findings (Decimal, date, Enum, secrets); which checklist items are already done. **Verify:** counts match `grep`; every cron-invoked script in the crontab appears in
the table. **Commit:** `docs(logging): add logging audit`

---

## LF-2 — `setup_logging()` binds `run_id` and job context by default;

**Files:** `src/utils/logging.py`, `tests/unit/utils/test_logging.py`. **Before any code:** `bash python -m scripts.dev.graph_snippet src.utils.logging.setup_logging`, `generate_trace_id`,
`bind_trace_id`; `trace_path` for their 2 callers. **Implement:** `setup_logging()` generates and binds `run_id` (reuse `generate_trace_id`; keep `bind_trace_id` as a thin alias so the 2 existing
callers do not change). Add `bind_job(name)`. `contextvars` already flow through `to_thread`; add a small `submit_with_context(executor, fn, ...)` for `ProcessPoolExecutor`, where they do not.
**Tests:** `test_run_id_present_after_setup`, `test_run_id_survives_to_thread`, `test_run_id_survives_process_pool`, `test_setup_twice_keeps_one_run_id`. **Commit:** `feat(logging): bind run_id by
default in setup_logging`

---

## LF-3 — Decimal/date/Enum-safe JSON rendering and secret redaction p

**Files:** `src/utils/logging.py`, `tests/unit/utils/test_logging.py`. **Before any code:** LF-1's renderer findings; `REFERENCES.md` for the token and chat-ID field names. **Implement:** a
serialisation processor (`Decimal` → string, `date`/`datetime` → ISO, `Enum` → value, Pydantic → `model_dump(mode="json")`) and a redaction processor driven by a key-name set and token patterns. Each
is its own small function wired into the processor chain, so a new rule is a new function. **Tests:** `test_decimal_not_float`, `test_enum_and_date_serialised`, `test_secret_key_masked`,
`test_non_secret_untouched`. **Commit:** `feat(logging): add safe serialisation and redaction processors`

---

## LF-4 — `timed()` context manager emitting `duration_ms`

**Files:** `src/utils/logging.py` (or `src/utils/timing.py` if the file passes about 220 lines), tests alongside. **Implement:** sync and async-safe context manager; logs at DEBUG by default, with a
`level` argument; never swallows the exception. It feeds the latency axis in `design-discipline/design-baseline/` DBL-2. **Tests:** `test_timed_logs_duration`, `test_timed_logs_and_reraises_on_error`.
**Commit:** `feat(logging): add timed context manager`

---

## LF-5 — `run_entrypoint` runner with an injected `HeartbeatSink` Pro

**Files:** `src/utils/runner.py` (new), `tests/unit/utils/test_runner.py` (new; `__init__.py` if the directory is new). **Before any code:** read `docs/refactor/design-principles.md` and run its
triggers. The runner is a Template Method: fixed sequence, injected collaborators. `src/utils/` must not import `src/portfolio/` or any store, so the sink is a `Protocol`
(`HeartbeatSink.record(run)`), supplied by the script. `kind` is `"cron"` or `"cli"` and is the marker the print policy keys on. **Implement:** `run_entrypoint(main, *, job, kind, sink=None)` runs
`main()` (sync or coroutine, with an explicit timeout), logs the three events, maps exceptions to a non-zero exit code, and writes the heartbeat in `finally`. A raising sink is logged and swallowed.
**Tests:** `test_success_records_ok`, `test_exception_records_failed_and_reraises_exit_code`, `test_sink_failure_does_not_change_exit`, `test_no_sink_still_logs`, `test_kind_recorded`. **Commit:**
`feat(logging): add run_entrypoint runner`

---

## LF-6 — `job_runs` table, `JobRunStore` sink, and the migration chec

**Files:** `src/ops/__init__.py` and `src/ops/run_store.py` (new), `tests/unit/ops/test_run_store.py`, `DB_REGISTRY.md`, `schema.md` (this story). **Before any code:** `DB_REGISTRY.md` first; use the
exact schema in `schema.md`. After adding the package, re-index the graph (`index_repository`). **Implement:** `JobRunStore` with `record(run)`, `last_success(job)`, `recent_failures(job, n)`;
`init_db()` is idempotent `CREATE TABLE IF NOT EXISTS`, so it is applied on first use, which avoids the ALTER-never-run trap behind BUG-029. 30-day retention prune, as `IntradayMarketStore` does.
**Live check (mandatory):** after the commit, run one job through the runner on the host and query `SELECT job, status, MAX(started_at) FROM job_runs GROUP BY job LIMIT 10`. A table that exists only
in code does not close this task. **Tests:** `test_record_and_last_success`, `test_failed_run_does_not_update_last_success`, `test_prune_keeps_recent`, `test_init_db_idempotent`. **Commit:**
`feat(ops): add job_runs store as heartbeat sink`

---

## LF-7 — Healthcheck reads `job_runs`: stale or failed job detection 

**Files:** `scripts/healthcheck.py`, its tests, a small expected-schedule config (one dict keyed by job). **Before any code:** read `scripts/healthcheck.py` `run_checks` and
`_check_3track_snapshot_cron`, which parses a log file today and is the fragile pattern this replaces. `BUG-027` (healthcheck never loaded `.env`) is the reminder to test the alert path end to end.
**Implement:** one pure `check_job_freshness(store, schedule, now)` returning `CheckResult`s; the schedule respects trading days via `is_trading_day`. Keep the existing log-based check until its job
reports through the runner, then remove it. **Tests:** `test_stale_job_flagged`, `test_recent_success_ok`, `test_holiday_not_flagged`, `test_consecutive_failures_flagged`. **Commit:**
`feat(healthcheck): detect stale and failing jobs from job_runs`

---

## LF-8 — Log notification send failures explicitly

**Files:** `src/notifications/telegram.py`, `src/notifications/telegram_gateway.py`, their tests; read `src/notifications/CLAUDE.md` first. **Implement:** keep the non-fatal contract (never raise) and
add the structured log line at each swallow point. BUG-039 and BUG-042 went unseen because failures here were silent. **Tests:** `test_send_failure_logged_not_raised`,
`test_success_not_logged_as_failure`. **Commit:** `feat(notifications): log swallowed send failures`

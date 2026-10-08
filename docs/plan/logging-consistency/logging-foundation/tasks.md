
# Logging Foundation — tasks

Work top-down. Find the first unchecked `- [ ]` and do only that task. Each task = one commit unless noted. See `prompt.md` for why the story exists; see `stories.md` for the per-task implementation
spec.

**Open: LF-1..LF-8.**

- [ ] **LF-1** — Audit: classify `print(` calls and entrypoints; verify the `LOGGING.md` checklist and the current renderer | Owner: Claude | Model: claude-sonnet-5 | Review: none | SHA: —
- [ ] **LF-2** — `setup_logging()` binds `run_id` and job context by default; carry it across threads and processes | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: —
- [ ] **LF-3** — Decimal/date/Enum-safe JSON rendering and secret redaction processors | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: —
- [ ] **LF-4** — `timed()` context manager emitting `duration_ms` | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: —
- [ ] **LF-5** — `run_entrypoint` runner with an injected `HeartbeatSink` Protocol | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: —
- [ ] **LF-6** — `job_runs` table, `JobRunStore` sink, and the migration check against the live DB | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: —
- [ ] **LF-7** — Healthcheck reads `job_runs`: stale or failed job detection per expected schedule | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: —
- [ ] **LF-8** — Log notification send failures explicitly | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: —

## Story done when

- **LF-1** — `docs/plan/logging-consistency/audit.md` lists every `print(` file as cron-invoked or interactive, every entrypoint without `setup_logging()`, the real state of the `LOGGING.md`
  checklist, and whether the renderer already handles `Decimal` and secrets.
- **LF-2** — Every script that calls `setup_logging()` gets a `run_id` on each line without further code; a log line emitted inside `asyncio.to_thread` carries it; a `ProcessPoolExecutor` helper
  carries it explicitly.
- **LF-3** — The JSON renderer never coerces `Decimal` to `float`; token, API-key and chat-ID values are masked in every log line.
- **LF-4** — `with timed("upstox.chain_fetch", ...)` logs one line with `duration_ms`, including when the block raises.
- **LF-5** — One runner wraps every entrypoint: setup, `run_id`, `run_started` / `run_finished` / `run_failed` with duration and exit code, traceback on crash, a heartbeat written in `finally`, and no
  failure from the sink reaching the job.
- **LF-6** — `job_runs` exists on the live `portfolio.sqlite` (verified by query), written by `JobRunStore` through the LF-5 sink Protocol; `cron_heartbeats` is untouched.
- **LF-7** — `healthcheck.py` alerts when a job has no success within its expected window or has failed on consecutive runs, without parsing any log file.
- **LF-8** — A swallowed Telegram send failure produces a `notify.send_failed` line with the error class and message size.

## After each task

Set `SHA:` to the real commit SHA on the task line and tick the box. Then update this story's status in the epic `README.md` story table and add one line to `TODOS.md` Session Log. When the whole
story is done, follow §Conventions *Completion → archive* — do not leave a done story half-archived.


# Logging Foundation — prompt

> Give every entrypoint a run ID, a runner that logs start, finish and failure, safe serialisation, secret redaction, timing, and a `job_runs` heartbeat that the healthcheck reads.

Read `CONTEXT.md` and state `CONTEXT.md ✓` before anything else. Then read `tasks.md`, find the first unchecked `- [ ]`, and do **only** that task. Read that task's full spec in `stories.md` (same
task id) before writing any code. One task per session. Complete it fully. Stop.

## Why this story exists

`LOGGING.md` fixes the line format, but the infrastructure behind it is thin. `generate_trace_id` / `bind_trace_id` exist and are used by 2 scripts; `setup_logging()` is called by 77 of 110 scripts.
Several bugs were crons failing silently for days (BUG-026, 027, 029, 039, 042, 047) and no mechanism surfaced them. The healthcheck parses a log file for at least one job.

## Scope guard

In scope: `src/utils/logging.py` additions, `src/utils/runner.py`, a new `src/ops/` package with `JobRunStore`, the `job_runs` table, the healthcheck freshness check, and notification-failure logging.
Out of scope: migrating existing scripts (`logging-migration/`), enforcement checks and the `LOGGING.md` rewrite (`logging-enforcement/`), `cron_heartbeats` changes, any log shipping or external
service.

## Design review

The runner is a Template Method with injected collaborators: `HeartbeatSink` is a `Protocol`, so `src/utils/` does not import a store (DIP, one-way dependency). Processors are small separate functions
in a chain, so a new redaction or serialisation rule is a new function (OCP). `JobRunStore` is its own class in `src/ops/`, not another method on the already large `PortfolioStore` (SRP). The
heartbeat is a DB table, not derived from logs: logs are for humans and their names and format change; a heartbeat needs a queryable contract. A new append-only table rather than extra columns on
`cron_heartbeats` avoids the unapplied-`ALTER` trap of BUG-029 and keeps run history. Each LF task states its design check before code, per the `design-discipline/` gate once it is live.

## Session-start load hints

`LOGGING.md`, `src/utils/logging.py`, `DB_REGISTRY.md`, `scripts/healthcheck.py`, `src/notifications/CLAUDE.md`, `docs/refactor/design-principles.md`.

## Task overview

LF-1 audit → LF-2 run_id → LF-3 processors → LF-4 timed → LF-5 runner → LF-6 `job_runs` store → LF-7 healthcheck → LF-8 notification failures. LF-6 includes a live-DB check: a table that exists only
in code does not close the task.

## Definition of done

A cron script wrapped by the runner writes `run_started` / `run_finished` lines with one `run_id`, a `job_runs` row, and the healthcheck alerts on a stale or failing job without reading a log file.

## Perspectives not covered

SQLite write contention between concurrent crons (WAL makes it small, but untested at 30 s tick cadence); whether Telegram alerts on every `run_failed` would be noisy; log shipping or remote
aggregation is deliberately out of scope.

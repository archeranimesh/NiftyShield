
# Logging Foundation — database schema

1 table added to `data/portfolio/portfolio.sqlite` (single shared DB via `src/db.py`). All timestamps stored as UTC ISO strings. No monetary values. Created by `JobRunStore.init_db()` — idempotent
`CREATE TABLE IF NOT EXISTS`; there is no migration-file mechanism. `cron_heartbeats` is not changed.

---

```sql
-- Append-only run history. Written by the run_entrypoint sink; read by healthcheck.py.
CREATE TABLE IF NOT EXISTS job_runs (
    run_id       TEXT PRIMARY KEY,     -- same value bound on every log line of the run
    job          TEXT NOT NULL,        -- stable job name, e.g. scripts.eod_summary
    kind         TEXT NOT NULL,        -- cron | cli
    started_at   TEXT NOT NULL,        -- UTC ISO
    finished_at  TEXT,                 -- NULL if the process died before finally ran
    status       TEXT NOT NULL,        -- ok | failed
    exit_code    INTEGER,
    duration_ms  INTEGER,
    error        TEXT                  -- exception class and message on failure, else NULL
);

CREATE INDEX IF NOT EXISTS idx_job_runs_job_started
    ON job_runs (job, started_at);
```

Why a new table and not `cron_heartbeats`: that table keeps only the latest run per service, so it cannot show failure streaks or duration trends, and adding columns needs an `ALTER TABLE` that
`init_db()` will not apply to the live DB (the BUG-029 failure). A new table is created automatically on first use.

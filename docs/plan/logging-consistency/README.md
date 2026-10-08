
# Logging Consistency — epic index

> Make logging consistent across every entrypoint and make silent cron failures visible: a run ID and runner on every job, safe serialisation and redaction, a `job_runs` heartbeat read by the
> healthcheck, migration of the existing scripts, and checks that stop it drifting back. Three stories because the infrastructure, the migration and the enforcement have different risk, owners and
> ordering.

## Why this epic exists

Requested by Animesh (2026-10-08): improve the logging infrastructure beyond correlation IDs and make it consistent everywhere. Today `setup_logging()` is called by 77 of 110 scripts, a trace ID
exists but 2 scripts use it, 73 files still contain 802 `print(` calls, and `logs/` has ad hoc file names. Several bugs (BUG-026, 027, 029, 039, 042, 047) were crons failing silently for days; nothing
surfaced them.

## Scope decisions

- **Separate epic** from `design-discipline/` (Animesh, 2026-10-08). `design-gate/` should land first so these plans carry a Design clause; this is a soft ordering, not a technical dependency.
- **Print policy** (Animesh, 2026-10-08): small interactive scripts may `print` their result output; cron-invoked scripts may not. Cron-invoked is defined by the crontab and by
  `run_entrypoint(kind="cron")`.
- **Heartbeat is a DB table** (recommendation, to confirm): a new append-only `job_runs` table, not log-derived and not extra columns on `cron_heartbeats`. The healthcheck already uses DB beacons and
  parses a log file for one check, which is the fragile pattern. A new table is created by `init_db()` on first use, avoiding the unapplied-`ALTER` failure of BUG-029, and keeps run history.
- **No council** (Step 2b): reversible, one technology discipline.
- **`cron_heartbeats` is left in place** and retired later once the healthcheck no longer reads it.

## Architecture and design review

`src/utils/runner.py` is a Template Method whose `HeartbeatSink` is a `Protocol`, so `src/utils/` never imports a store. `JobRunStore` lives in a new `src/ops/` package (SRP: not a method on
`PortfolioStore`). Processors, checks and hooks are small separate units so each new rule is an addition, not a branch.

## Stories

| Story | Purpose | Status | Depends on | Closing SHA |
|---|---|---|---|---|
| `logging-foundation/` | `run_id`, redaction, `timed()`, runner, `job_runs`, healthcheck freshness (LF-1..8) | ⬜ Not started | — | — |
| `logging-migration/` | Move `src/` and every entrypoint onto it; cron `print` to logger (LM-1..5) | ⬜ Not started | `logging-foundation` LF-5 | — |
| `logging-enforcement/` | Pre-commit checks, print ratchet, vocabulary lint, `LOGGING.md` rewrite (LE-1..6) | ⬜ Not started | `logging-migration` LM-4 | — |

Status: ⬜ Not started · 🔄 In progress · ✅ Done. This column is the epic's progress view — per-task checkboxes live only in each sub-story's `tasks.md`.

## Cross-cutting constraints

- **Non-fatal contract**: a heartbeat or log failure never changes a job's exit code or aborts a job.
- **No behaviour change** in the migration: what a script computes or sends is untouched.
- **Offline-first tests**: no network, no real DB; the `JobRunStore` live check in LF-6 is the one deliberate exception and is a manual host step.
- **Money**: never `float`; the JSON renderer must not coerce `Decimal`.
- **Docs follow the fill-to-≤200 style** (`reflow_md`).

## Supersession / coordination

`design-discipline/design-gate/` DG-3 triages `docs/refactor/logging-and-correlation-id.md`; LE-5 applies that verdict. DG-3 does not edit `LOGGING.md`; this epic owns it. LF-4's `timed()` feeds
`design-discipline/design-baseline/` DBL-2's latency axis.

## Epic done when

- **logging-foundation** — a runner-wrapped cron writes one `run_id` through its log lines and a `job_runs` row, and the healthcheck alerts on a stale or failing job.
- **logging-migration** — no `print(` or stdlib `getLogger` in `src/` or cron code; every cron entrypoint uses the runner.
- **logging-enforcement** — pre-commit blocks regressions and `LOGGING.md` matches the system.

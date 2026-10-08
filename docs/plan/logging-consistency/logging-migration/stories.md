
# Logging Migration — story specs

> One task per session. Find the first unchecked item in `tasks.md`. That is your only task. Full implementation rules in `CLAUDE.md` and `REVIEW.md`. After each task: set `SHA:` on the task line +
> tick the box, update the story status summary, add one line to `TODOS.md`. See `docs/plan/README.md` §Conventions.

## LM-1 — Move stdlib-logging and `print`-for-diagnostics stragglers i

**Files:** per LF-1's list, starting with `src/client/upstox_market.py` (stdlib `logging.getLogger`, 3 `%s` calls). **Implement:** `structlog.stdlib.get_logger(__name__)`, keyword arguments, event
names per `LOGGING.md`. One commit per module group. **Tests:** existing tests stay green; add a log-line assertion for any branch that had none. **Commit:** `refactor(logging): migrate <module> to
structlog`

---

## LM-2 — Wrap every cron-invoked entrypoint in `run_entrypoint(kind="

**Files:** the cron entrypoints from LF-1's crontab table (3 to 8 per commit, grouped by directory). **Implement:** replace the ad hoc `main()` plus `setup_logging()` boilerplate with the runner; pass
`JobRunStore` as the sink; add the job to the healthcheck schedule dict. No behaviour change otherwise. **Tests:** one test per entrypoint group that the runner is invoked with the right `job` and
`kind`. **Commit:** `refactor(logging): run <group> crons through run_entrypoint`

---

## LM-3 — Cron scripts, batch A (`scripts/strategies/`): `print(` to l

**Files:** from LF-1: `scripts/strategies/ic/*`, `cc_calibration/*`, other strategy entrypoints. Replace diagnostics with `logger.<level>(event, key=value)`. A report string that is sent to Telegram
stays; log a `report_sent` event beside it. **Commit:** `refactor(logging): replace print with logger in strategy crons`

---

## LM-4 — Cron scripts, batch B (`portfolio/`, `intraday/`, `pipeline/

**Files:** from LF-1: `scripts/portfolio/daily_snapshot.py` (64 prints and a bespoke `[timestamp] message` format), `scripts/record/record_paper_trade.py` where cron-invoked, `scripts/intraday/*`,
`scripts/pipeline/*`, `eod_summary.py`, `pre_market_brief.py`. **Commit:** `refactor(logging): replace print with logger in portfolio crons`

---

## LM-5 — Interactive CLIs: keep result output, move diagnostics to th

**Policy (Animesh, 2026-10-08):** small interactive scripts may `print` their result output; any cron-invoked script may not. A script is cron-invoked if it is in the crontab or uses
`run_entrypoint(kind="cron")`. **Files:** the interactive scripts from LF-1 (`mvp.py`, lookup tools, `scripts/dev/*`) and `LOGGING.md` checklist ticks only; the full `LOGGING.md` rewrite is
`logging-enforcement/`. **Implement:** keep result `print`; move warnings, errors and progress lines to the logger. **Commit:** `refactor(logging): separate result output from diagnostics in CLIs`

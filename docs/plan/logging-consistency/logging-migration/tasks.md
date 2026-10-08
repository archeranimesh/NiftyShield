
# Logging Migration — tasks

Work top-down. Find the first unchecked `- [ ]` and do only that task. Each task = one commit unless noted. See `prompt.md` for why the story exists; see `stories.md` for the per-task implementation
spec.

**Open: LM-1..LM-5.**

- [ ] **LM-1** — Move stdlib-logging and `print`-for-diagnostics stragglers in `src/` to structlog | Owner: Antigravity | Model: n/a | Review: code-reviewer | SHA: —
- [ ] **LM-2** — Wrap every cron-invoked entrypoint in `run_entrypoint(kind="cron")` | Owner: Antigravity | Model: n/a | Review: code-reviewer | SHA: —
- [ ] **LM-3** — Cron scripts, batch A (`scripts/strategies/`): `print(` to logger | Owner: Antigravity | Model: n/a | Review: code-reviewer | SHA: —
- [ ] **LM-4** — Cron scripts, batch B (`portfolio/`, `intraday/`, `pipeline/`, top-level crons): `print(` to logger | Owner: Antigravity | Model: n/a | Review: code-reviewer | SHA: —
- [ ] **LM-5** — Interactive CLIs: keep result output, move diagnostics to the logger; close the stale `LOGGING.md` checklist | Owner: Claude | Model: claude-sonnet-5 | Review: none | SHA: —

## Story done when

- **LM-1** — No `logging.getLogger` and no diagnostic `print(` remains in `src/`.
- **LM-2** — Every script in the crontab uses the runner and a `HeartbeatSink`, and appears in the healthcheck schedule.
- **LM-3** — No `print(` in cron-invoked scripts under `scripts/strategies/`.
- **LM-4** — No `print(` in any cron-invoked script.
- **LM-5** — Interactive scripts print results only; every diagnostic goes through the logger; the `LOGGING.md` migration checklist is accurate.

## After each task

Set `SHA:` to the real commit SHA on the task line and tick the box. Then update this story's status in the epic `README.md` story table and add one line to `TODOS.md` Session Log. When the whole
story is done, follow §Conventions *Completion → archive* — do not leave a done story half-archived.

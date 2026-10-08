
# Logging Enforcement — tasks

Work top-down. Find the first unchecked `- [ ]` and do only that task. Each task = one commit unless noted. See `prompt.md` for why the story exists; see `stories.md` for the per-task implementation
spec.

**Open: LE-1..LE-6.**

- [ ] **LE-1** — Pre-commit check: every cron entrypoint uses `run_entrypoint`; every script calls `setup_logging()` | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: —
- [ ] **LE-2** — Pre-commit check: no `print(` in `src/` or cron-invoked scripts; ratchet for interactive scripts | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: —
- [ ] **LE-3** — Event-name and field-vocabulary lint | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: —
- [ ] **LE-4** — Contract tests: every mandated silent-failure branch logs | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: —
- [ ] **LE-5** — Rewrite `LOGGING.md`; reconcile `docs/refactor/logging-and-correlation-id.md`; add reviewer items | Owner: Claude | Model: claude-sonnet-5 | Review: none | SHA: —
- [ ] **LE-6** — `logs/` file naming, rotation and retention convention | Owner: Claude | Model: claude-sonnet-5 | Review: none | SHA: —

## Story done when

- **LE-1** — A new entrypoint without the runner (cron) or `setup_logging()` fails the commit.
- **LE-2** — `print(` fails the commit in `src/` and cron scripts; the interactive-script `print` count can only go down.
- **LE-3** — Log calls with a non-conforming event name or a misspelled domain key fail the commit.
- **LE-4** — A test per listed degrade branch asserts its warning event is emitted.
- **LE-5** — `LOGGING.md` documents the runner, `run_id`, print policy, vocabulary, heartbeat and file layout; the `code-reviewer` agent checks them; the refactor logging doc is merged or retired
  consistently with the `design-gate` DG-3 verdict.
- **LE-6** — One documented layout and retention rule for `logs/`, applied to the cron redirects.

## After each task

Set `SHA:` to the real commit SHA on the task line and tick the box. Then update this story's status in the epic `README.md` story table and add one line to `TODOS.md` Session Log. When the whole
story is done, follow §Conventions *Completion → archive* — do not leave a done story half-archived.

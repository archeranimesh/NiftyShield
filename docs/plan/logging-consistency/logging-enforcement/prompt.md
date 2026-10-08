
# Logging Enforcement — prompt

> Make the logging standard self-enforcing so it does not drift back, and rewrite `LOGGING.md` around the new infrastructure.

Read `CONTEXT.md` and state `CONTEXT.md ✓` before anything else. Then read `tasks.md`, find the first unchecked `- [ ]`, and do **only** that task. Read that task's full spec in `stories.md` (same
task id) before writing any code. One task per session. Complete it fully. Stop.

## Why this story exists

`LOGGING.md` was written after BUG-010 found six incompatible formats, yet 802 `print(` calls remain. A written standard drifts unless it is checked. Pre-commit already enforces two logging rules
(`no-script-main-logger`, `no-bare-logging`); this adds the rest.

## Scope guard

In scope: the pre-commit checks, the print ratchet, the vocabulary lint, contract tests, the `LOGGING.md` rewrite, reviewer items, the `logs/` layout. Out of scope: infrastructure
(`logging-foundation/`), the migration itself (`logging-migration/`).

Blocked until `logging-migration/` LM-4 is done: a no-print rule for cron code cannot be enabled while cron code still prints.

## Design review

Each check is its own small script in `scripts/dev/` modelled on the existing hooks, selected by `.pre-commit-config.yaml`, so a new rule is a new hook, not a new branch in one checker. The print
ratchet is a baseline file that can only shrink, which avoids a flag-day rewrite of the interactive scripts.

## Session-start load hints

`.pre-commit-config.yaml`, the existing logging hook scripts, `LOGGING.md`, `docs/refactor/design-principles.md`.

## Task overview

LE-1 entrypoint check → LE-2 print ban and ratchet → LE-3 vocabulary lint → LE-4 contract tests → LE-5 `LOGGING.md` rewrite and reviewer items → LE-6 `logs/` layout.

## Definition of done

A commit that adds a cron `print`, a bare entrypoint, a malformed event name or a misspelled domain key fails pre-commit; `LOGGING.md` describes the system as built.

## Perspectives not covered

Pre-commit only sees committed code, so a crontab that points at the wrong script or redirect is invisible to it; the ratchet baseline needs occasional review so it does not freeze at a high number.

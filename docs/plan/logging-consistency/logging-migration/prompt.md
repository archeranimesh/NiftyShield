
# Logging Migration — prompt

> Move the existing scripts and `src/` stragglers onto the shared logging infrastructure, in small mechanical batches, with no behaviour change.

Read `CONTEXT.md` and state `CONTEXT.md ✓` before anything else. Then read `tasks.md`, find the first unchecked `- [ ]`, and do **only** that task. Read that task's full spec in `stories.md` (same
task id) before writing any code. One task per session. Complete it fully. Stop.

## Why this story exists

73 files still contain 802 `print(` calls, 33 scripts never call `setup_logging()`, and `LOGGING.md`'s own migration checklist is unticked. The foundation work is useless unless the entrypoints
actually use it.

## Scope guard

In scope: converting `print` diagnostics to structlog, wrapping cron entrypoints in `run_entrypoint`, moving `src/` stragglers off stdlib logging, and ticking the stale checklist. Out of scope: new
infrastructure (`logging-foundation/`), enforcement checks (`logging-enforcement/`), any change to what a script computes or sends.

Blocked until `logging-foundation/` LF-5 (runner) is done and LF-1's audit table exists: the migration batches are defined by that table.

## Design review

Mechanical and behaviour-preserving, so no new seam. Each batch is one directory group per commit to keep the blast radius small. Print policy: result output from small interactive scripts may stay as
`print`; cron-invoked scripts may not print at all.

## Session-start load hints

`docs/plan/logging-consistency/audit.md`, `LOGGING.md`, `src/utils/runner.py`.

## Task overview

LM-1 `src/` stragglers → LM-2 cron entrypoints onto the runner → LM-3 and LM-4 cron `print` batches → LM-5 interactive CLIs and the checklist. LM-1 to LM-4 suit an Antigravity handoff (3+ files,
mechanical, clear spec).

## Definition of done

No `print(` or stdlib `getLogger` in `src/` or in any cron-invoked script; every cron entrypoint runs through the runner; the `LOGGING.md` checklist matches reality.

## Perspectives not covered

A script's `print` output may be piped or parsed by another tool or cron redirect, so each batch must check for consumers before converting; the interactive/cron split depends on the host crontab,
which is not in the repo.

# Yearly Ops Wiring — prompt

> Makes the yearly book run and show up: monitor-daemon registration, labels, EOD and pre-market reports, cron entries, runbook lines.

Read `CONTEXT.md` and state `CONTEXT.md ✓` before anything else. Then read `tasks.md`, find the first unchecked `- [ ]`, and do **only** that task. Read that task's full spec in `stories.md` (same
task id) before writing any code. One task per session. Complete it fully. Stop.

## Why this story exists

The entrypoints can open yearly legs, but nothing monitors, labels or reports them. The daemon registers one instance of each overlay class today; the yearly book needs its own instances.

## Scope guard

Off by default behind its own env flag, so deploying this story changes nothing until enabled. No new strategy logic. No schema change expected (confirmed by YF-1).

## Design review

DIP: the daemon builds instances from the policy registry — a loop over `OVERLAY_TENORS`, not a copy of the registration block per tenor. Labels come from `STRATEGY_LABELS`, one copy of each string.

## Session-start load hints

`docs/plan/yearly-overlays/README.md`, `yearly-foundation/audit.md`, `LOGGING.md` (if a script is added), `FORMATTING.md` for report text, `src/notifications/CLAUDE.md`.

## Task overview

YW-1 daemon registration → YW-2 reports and labels → YW-3 crons, runbook, DB_REGISTRY note.

## Definition of done

With `MONITOR_YEARLY_OVERLAYS=1` the daemon registers three yearly instances next to the monthly ones; EOD, pre-market and overlay P&L views list the yearly book as its own rows; flag off means no
behaviour change.

## Perspectives not covered

Telegram message volume: three more strategies produce more alerts; no de-duplication across the two books is attempted.

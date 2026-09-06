# Telegram Markdown Migration — Strategy Rollout — prompt

> Migrate each Telegram message family to the confirmed bold / table MarkdownV2 format, staged by risk — informational messages first, live position-event notifications next, auth-sensitive
> interactive messages last.

Read `CONTEXT.md` and state `CONTEXT.md ✓` before anything else. Then read `tasks.md`, find the first unchecked `- [ ]`, and do **only** that task. Read that task's full spec in `stories.md` (same
task id) before writing any code. One task per session. Complete it fully. Stop.

## Why this story exists

`backbone/` made the transport MarkdownV2-safe without changing how any message looks; `formatting-rules/` built the shared spec and helpers. This story is the actual visual migration — each message
family gets its confirmed layout wired in using `src/notifications/formatting.py`'s formatters and table builders. The order is deliberate: a wrong-looking IC EOD audit costs a re-read; a broken
approval-request keyboard could block a real trade decision, so that goes last with a coordination check. Every message format is confirmed on-device via a `message-format-workshop.md` scratch script
before it is written into `stories.md` — never author a final format directly.

## Scope guard

The message-building code in the IC / three-track / overlay strategy classes and their cron scripts (`paper_ic_snapshot.py`, `paper_ic_monthly_comparison.py`, `eod_summary.py`, the 7 strategy
`_send_close_notification` paths, `send_approval_request`, and the ten missing-message call sites `ROLL-7..ROLL-16`). This story changes **how messages look**; it does not change the transport
(`backbone/`) or add new formatting helpers (`formatting-rules/`) — a helper that turns out to be missing (as `build_compare_table` was for ROLL-2) is promoted in a dedicated sub-task, not bundled
invisibly into a port commit.

## Session-start load hints

- Epic `README.md` — the risk-tier sequencing rationale and the improvement-backlog parallelization note.
- Root `FORMATTING.md` — the canonical value / table rules every port must follow; §§ 4 / 7 carry unresolved conflicts (`Δ` / `₹` / emoji inside a fence) to resolve at implementation time, not carry
  forward.
- The task's `stories.md` section — every open task has a full forward spec including its confirmed message block and the exact test list; every shipped task has an As-built with its phase SHAs.
- `src/notifications/CLAUDE.md` §"Instrument Label Formatting" for any message rendering an instrument label.
- No `schema.md` — this story changes no DB schema (ROLL-10's `TrackSnapshot` field addition is a dataclass change, not DB).

## Hard constraints

- **Depends on `backbone/` + `formatting-rules/` fully complete** before ROLL-1. ROLL-0 is data-only and independent.
- **ROLL-4 coordination check (mandatory, that task only):** re-read `docs/plan/full-repo-review-followups/telegram-approval-auth-fix/tasks.md` to confirm its current state before touching
  `TelegramGateway.send_approval_request`. Do not trust the outer `docs/plan/README.md` status line — it was found stale once (2026-08-07).
- **Non-fatal send contract** (`src/notifications/CLAUDE.md`) — unchanged.
- **Graph-before-Read** for any `src/` / `scripts/` file.
- **Test gate (blocking):** `python -m pytest tests/unit/ --tb=no -q` — all green before committing.
- **Financial-logic review:** ROLL-2b-i/2b-ii, ROLL-2c, ROLL-3.1/3.2/3.3, ROLL-4, ROLL-6, ROLL-9 render or source P&L — run the **real** `@code-reviewer` subagent (Opus) against `git diff HEAD` before
  committing, per root `CLAUDE.md` AutoTrigger rules.
- **Test helpers:** `get_code_snippet('<ModelClassName>')` before writing any fixture that constructs a domain model.

## Task overview

One line per task id (detail in `stories.md`): ROLL-0 net-Greeks data · ROLL-1 (1a emoji / 1b header / 1c port) IC EOD audit · ROLL-2 (2a builder / 2b P&L sourcing / 2c port) IC monthly comparison ·
ROLL-3 (3.1 CSP / 3.2 IC / 3.3 overlay) close/roll · ROLL-4 approval requests · ROLL-6 EOD Paper Summary · ROLL-7..ROLL-16 the ten missing-message call sites · ROLL-17 IC entry confirmation (design
incomplete) · ROLL-5 docs close.

## Definition of done

Mirrors `tasks.md` §"Story done when". In short: every message family renders in its confirmed MarkdownV2 format with a live-confirmed reference and passing tests, shared label tables are reused not
re-derived, ROLL-17's design is closed before it is implemented, and the docs-close task records the final state — at which point the whole epic follows *Completion → archive*.

## Perspectives not covered

- **On-device verification of the shipped ports.** Every format was confirmed on-device *as a scratch script*; whether the promoted real code renders byte-identically on-device after the port
  (escaping, fence width, emoji presentation) is asserted only by unit tests, not re-confirmed live per task.
- **ROLL-17's IC-only scope.** The leg *model* is IC-only by decision, but three-track entry messages (ROLL-13/14) have their own per-track leg vocabulary — whether a future unified leg model is worth
  it, or the duplication is permanent, is not decided here.

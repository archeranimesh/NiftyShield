
# Monitor-driven calendar entry — prompt

> Make the monitor daemon the single, fully-reported entry path for the calendar strategies: the shell itself writes the margin snapshot and sends the entry card and payoff chart, so the entry cron
> lines can be retired.

Read `CONTEXT.md` and state `CONTEXT.md ✓` before anything else. Then read `tasks.md`, find the first unchecked `- [ ]`, and do **only** that task. Read that task's full spec in `stories.md` (same
task id) before writing any code. One task per session. Complete it fully. Stop.

## Why this story exists

On 2026-10-14 the first-ever calendar entry (`paper_nifty_calendar_biweekly`, trades 501-504) came from the monitor daemon, not cron. `NiftyCalendarV1.check_signals` calls `plan_entry` whenever the
strategy is flat and emits an `auto_execute` `NC_ENTRY` event; `StrategyMonitor` dispatched it at 10:31:21 and `apply_action` wrote the four legs. That path logs one line and stops. The margin
snapshot (`capture_entry_margin`), the Telegram entry card and the payoff chart live only in `scripts/strategies/nifty_calendar/paper_calendar_entry.py` (`run_entry` and `_send_entry_card`), so the
daemon entry left no `paper_margin_snapshots` row and sent no message. That morning the cron entry also failed (`ModuleNotFoundError`, the crontab lines pointed at the wrong repo), which is the only
reason the daemon entered first.

Two entry paths for one strategy is a race, guarded only by the non-atomic "any open position" check, and the script is the one that reports. CC, PP, IC and collar entries all remain cron-driven (the
monitor has only ever dispatched closes, rolls and monetisations for them); the calendar is the first strategy whose entry lives in `check_signals`. This story keeps that design and makes it complete.

## Scope guard

**In bounds:**
- A `Protocol` for the entry report and one implementation in `src/strategy/` that does margin capture, entry card and payoff chart, extracted from the script (`_send_entry_card` plus the
  `capture_entry_margin` call).
- `NiftyCalendarV1.apply_action` calls it after an `OPEN_STRUCTURE` that actually wrote legs; `build_calendar_shell` wires it; the script's `run_entry` stops duplicating it.
- Per-strategy log routing for the daemon, and the cutover note for the two calendar entry cron lines.

**Out of bounds:**
- `StrategyMonitor` dispatch logic. The hook sits in the calendar shell, which both the daemon and the script already call, so no change to `monitor.py` is needed or allowed in this story.
- Moving CC, PP, IC or collar entries to the monitor. That is a separate, council-worthy decision (it changes the failure model for every strategy) and is not decided here.
- Order placement, sizing, any change to selection or exit rules.

## Design review

Placement: a generic post-dispatch hook in `StrategyMonitor` was considered and not chosen. It would change core dispatch for all 13 evaluated strategies to serve one, and the script path (which also
calls `shell.apply_action`) would still need its own copy. Putting the hook in `apply_action` makes both paths identical by construction and mirrors the existing precedent: `_close_structure` already
sends the close message from inside the shell via `nifty_calendar_notify.send_close_message`.

SOLID triggers (`docs/refactor/design-principles.md`): the shell takes the reporter as a constructor-injected `Protocol` collaborator (optional, default `None` so existing tests and callers are
unchanged); no new `elif` on a decision method; the reporter module is a leaf that depends on `src/notifications`, `src/paper` and `src/payoff`, never on `src/strategy/monitor.py`. Prior-art audit
(`code-deduplication-and-taxonomy.md`): reuse `send_close_message`'s notifier pattern and `capture_entry_margin` from `src/paper/margin_capture.py`; do not copy either. ME-1 records the outcome.

Council checkpoint (CLAUDE.md Step 2b): not warranted. The decision is reversible (one optional constructor argument) and has a single defensible shape for this story; the cross-strategy move to
monitor entries is the council-worthy one and is excluded above.

## Session-start load hints

- `src/strategy/CLAUDE.md`, `src/nifty_calendar/CLAUDE.md`, `src/notifications/CLAUDE.md` (Instrument Label Formatting), `FORMATTING.md` and `LOGGING.md`.
- `scripts/strategies/nifty_calendar/paper_calendar_entry.py` (the code being extracted), `src/strategy/nifty_calendar_v1.py` (`apply_action`, `_open_structure`, `_close_structure`) and
  `src/strategy/nifty_calendar_notify.py`.
- `DB_REGISTRY.md` for `paper_margin_snapshots`; the daemon log `logs/monitor_daemon.log` around 2026-10-14 10:31 for the first monitor entry.

## Task overview

ME-1 the entry reporter (Protocol plus implementation, extracted, tested in isolation) · ME-2 wire it into the shell and thin the script · ME-3 per-strategy log routing · ME-4 cutover, backfill
decision and close-out docs. ME-1 and ME-2 are Claude's (judgment-heavy, 1-3 files each); ME-3 touches shared logging and is Claude's; ME-4 has a manual step for Animesh.

## Definition of done

All tasks ticked with SHAs; unit suite green; an offline test shows a monitor-style `apply_action` call produces the margin row, the entry card and the chart exactly once, and a second call with an
open position produces none; the script and the daemon share the one reporter; calendar entry cron lines removed (Animesh) with the script retained as a manual re-entry tool; docs closed.

## Perspectives not covered

The 2026-10-14 biweekly entry has no margin row and no card was originally sent (a card was re-sent manually); whether to backfill that margin row is Animesh's call (ME-4). A daemon outage during the
entry window now means no entry at all, because cron is gone; whether to keep the cron entry as a safety net is a trade-off between that and the double-entry race, decided in ME-4 and not resolvable
by code alone. Per-strategy logging changes the log layout every operator tool greps today.

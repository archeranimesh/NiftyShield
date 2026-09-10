# Signals Paper Track — tasks

Work top-down. Find the first unchecked `- [ ]` and do only that task. Each task = one commit unless noted. See `prompt.md` for why the story exists; see `stories.md` for the per-task implementation
spec; `schema.md` is the sole DDL source.

**Open: SPT-2a.**

> SPT-1 (council checkpoint) is closed — ruled 2026-09-09, `docs/archive/council/strategy/2026-09-09_signals-paper-track-execution-layer.md`, absorbed into `DECISIONS.md` §"Signals Paper Track —
> Execution Layer". SPT-2..SPT-8 below are the rewrite from that ruling — no longer provisional.

> **Routing:** SPT-2a is `Owner: Antigravity` (bounded single-function change, airtight spec, TDD-shaped). Its `greeks-analyst` gate is a **real Claude subagent run**, not Antigravity's persona
> approximation (CLAUDE.md §AutoTrigger — financial logic). Everything else is `Owner: Claude` — model / design calls or graph queries land mid-implementation.

- [x] **SPT-1** — Council checkpoint (no code): module boundary (A — `paper_signal_track_v1` on the shared `StrategyMonitor` / `PaperExecutor` / `PaperStore`); pure `src/strategy/signal_exit.py`;
  fixed SL −30 % / target +50 %; Phase 1 fixed-only, `TRAILING_STOP` reserved; 30 s cadence; mark-path telemetry from day one; two-tier recalibration; go-live gate G1–G9; auto-execute live pilot.
  Output: `DECISIONS.md` entry + `schema.md` + this rewrite.
  | Owner: Animesh | Model: n/a | Review: none | SHA: 636c190
- [x] **SPT-2** — Signal paper models (`SignalPaperEntry`, `SignalMark`) + store methods (`open_signal_entry` / `get_open_signal_entry` / `record_mark` / `get_marks` / `close_signal_entry` /
  `get_entries` / `cumulative_pnl`). Position rides `paper_trades` as `paper_signal_track_v1`, `quantity` = `paper.constants.LOT_SIZE` (import, not the literal `65`); `STRATEGY_SIGNAL_TRACK` constant
  added. Tables `paper_signal_entries` / `paper_signal_marks` in `_SCHEMA` (non-STRICT, matching `schema.md` + sibling `paper_trades`). `close_signal_entry` runs the state-flip + exit-event insert in
  one transaction; `cumulative_pnl` pairs closed entries to SELL rows in order with a length-mismatch guard. | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: <—>
- [ ] **SPT-2a** — `<= 7-DTE` roll in `src/signals/option_resolver.py::resolve_monthly_option` (next-month contract in the current month's final week; `get_expiry_candidates` untouched).
  | Owner: Antigravity | Model: n/a | Review: greeks-analyst | SHA: <—>
- [ ] **SPT-3** — Entry executor: `src/strategy/signal_track_v1.py` `PaperStrategy` — `DailySignal` → `resolve_monthly_option` → `LegSpec` → `PaperExecutor` fill → frozen `SignalPaperEntry` → Telegram
  entry message. Also creates `src/strategy/signal_exit.py` as the SL/target constants home (`SL_PCT` / `TGT_PCT` / `RULESET_VERSION` / `derive_levels`), imports `paper.constants.LOT_SIZE`, and
  exposes the entry path as a plain `open_signal_paper_entry(signal, snapshot, broker, store)` callable (shared with SPT-6, no hardcoded level literals). Extract `_render_table` →
  `src/notifications/formatting.py::build_position_table`. | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: <—>
- [ ] **SPT-4** — Register `paper_signal_track_v1` with `StrategyMonitor` at 30 s per-strategy cadence; per-tick `paper_signal_marks` row (mark / MFE / MAE / stale / gap_event); hand tick to
  `signal_exit`. 90 s fallback + cadence-review trigger. | Owner: Claude | Model: claude-sonnet-5 | Review: greeks-analyst | SHA: <—>
- [ ] **SPT-5** — Extend `src/strategy/signal_exit.py` (created in SPT-3 as the constants module) with the pure `evaluate(entry, mark, now) → TARGET | STOP_LOSS | TIME_EXIT | HOLD`
  + `SignalExitReason` (`TRAILING_STOP` reserved, unused); caller takes the exit fill at the observed mark, closes the row + `paper_exit_events`, sends the Telegram exit message.
  | Owner: Claude | Model: claude-sonnet-5 | Review: greeks-analyst | SHA: <—>
- [ ] **SPT-6** — Entrypoint wiring, **no new cron**: a guarded paper-entry tail-call in `scripts/morning_signal.py` right after `store.record_signal(signal)`; a `paper_signal_track_v1` registration
  with `due_interval_s=30` inside `scripts/monitor_daemon.py`; `scripts/signal_paper_entry.py` as a manual `--date` backfill / re-entry tool (idempotent, **not** a scheduled cron). No unit tests.
  Deliver the updated runbook crontab comment block plus log paths. | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: <—>
- [ ] **SPT-7** — PAPER TRACK evaluation report over `--from` / `--to` (default: first paper entry → +6 calendar months), grouped by `ruleset_version`: the metric set + the all-pass G1–G9 go-live
  gate. Manual / periodic report — invoked like `signal_report` today, not a scheduled entrypoint. | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: <—>
- [ ] **SPT-8** — Docs close: `CONTEXT.md`, `DECISIONS.md` as-built note (the `morning_signal` tail-call seam, `signal_exit.py` as constants + evaluator home, `signal_paper_entry.py` = manual tool, 30
  s vs 90 s-fallback as shipped), `DB_REGISTRY.md`, `TODOS.md`, `docs/plan/README.md`, `src/strategy/CLAUDE.md`; mark `signals/` S5.5a `won't-do`; archive per §Conventions. | Owner: Claude | Model:
  claude-sonnet-5 | Review: none | SHA: <—>

## Story done when

- **SPT-1** — the council has ruled; the ruling is in `DECISIONS.md`; `schema.md` exists; SPT-2..SPT-8 and `stories.md` are rewritten to match. ✅
- **SPT-2** — `SignalPaperEntry` / `SignalMark` round-trip through the store; a second open is rejected; `cumulative_pnl()` aggregates correctly; happy-path + edge tests pass, no real DB.
- **SPT-2a** — near-month at 8 DTE stays, at 7 DTE rolls to next month, no next-month contract returns `None`; `record_signal_outcome` regression green; `greeks-analyst` clean.
- **SPT-3** — a firing `DailySignal` produces one resolved-option paper entry at a simulated fill, one `paper_trades` row + one frozen `SignalPaperEntry`, one Telegram entry message stating the fill
  price; NO_TRADE / already-open are logged no-ops; the EOD PT summary still renders after the `build_position_table` extraction.
- **SPT-4** — `paper_signal_track_v1` is polled every 30 s while open, each tick writes a `paper_signal_marks` row, and each tick reaches `signal_exit` without duplicate firing.
- **SPT-5** — an open position exits on the first of `TARGET` / `STOP_LOSS` / the 15:00 square-off; the fill is taken at the observed mark; the row + `paper_exit_events` record the reason and realised
  P&L; a Telegram exit message goes out; `TRAILING_STOP` is defined but never returned.
- **SPT-6** — no crontab line is added; `morning_signal` opens the paper entry via a guarded tail-call, the monitor picks up `paper_signal_track_v1` at 30 s, and `signal_paper_entry.py` is a manual
  idempotent backfill tool that no-ops on NO_TRADE / already-open / holiday.
- **SPT-7** — the report aggregates the paper track over a window, grouped by ruleset version, and returns an explicit all-pass / fail against G1–G9; it is a manual invocation, not a cron.
- **SPT-8** — every state doc, `DB_REGISTRY.md`, and `src/strategy/CLAUDE.md` reflect the shipped execution layer; `signals/` S5.5a is `won't-do`; the story folder is archived.

## After each task

Set `SHA:` to the real commit SHA on the task line and tick the box. Then update this story's status in `docs/plan/README.md` (single story) and add one line to `TODOS.md` Session Log. When the whole
story is done, follow `docs/plan/README.md` §Conventions *Completion → archive*.

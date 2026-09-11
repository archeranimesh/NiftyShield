# Signals Paper Track — tasks

Work top-down. Find the first unchecked `- [ ]` and do only that task. Each task = one commit unless noted. See `prompt.md` for why the story exists; see `stories.md` for the per-task implementation
spec; `schema.md` is the sole DDL source.

**Open: SPT-8.**

> SPT-1 (council checkpoint) is closed — ruled 2026-09-09, `docs/archive/council/strategy/2026-09-09_signals-paper-track-execution-layer.md`, absorbed into `DECISIONS.md` §"Signals Paper Track —
> Execution Layer". SPT-2..SPT-8 below are the rewrite from that ruling — no longer provisional.

> **Routing:** SPT-2a closed 2026-09-10 as a no-op (see its task line). Everything else is `Owner: Claude` — model / design calls or graph queries land mid-implementation.

- [x] **SPT-1** — Council checkpoint (no code): module boundary (A — `paper_signal_track_v1` on the shared `StrategyMonitor` / `PaperExecutor` / `PaperStore`); pure `src/strategy/signal_exit.py`;
  fixed SL −30 % / target +50 %; Phase 1 fixed-only, `TRAILING_STOP` reserved; 30 s cadence; mark-path telemetry from day one; two-tier recalibration; go-live gate G1–G9; auto-execute live pilot.
  Output: `DECISIONS.md` entry + `schema.md` + this rewrite.
  | Owner: Animesh | Model: n/a | Review: none | SHA: 636c190
- [x] **SPT-2** — Signal paper models (`SignalPaperEntry`, `SignalMark`) + store methods (`open_signal_entry` / `get_open_signal_entry` / `record_mark` / `get_marks` / `close_signal_entry` /
  `get_entries` / `cumulative_pnl`). Position rides `paper_trades` as `paper_signal_track_v1`, `quantity` = `paper.constants.LOT_SIZE` (import, not the literal `65`); `STRATEGY_SIGNAL_TRACK` constant
  added. Tables `paper_signal_entries` / `paper_signal_marks` in `_SCHEMA` (non-STRICT, matching `schema.md` + sibling `paper_trades`). `close_signal_entry` runs the state-flip + exit-event insert in
  one transaction; `cumulative_pnl` pairs closed entries to SELL rows in order with a length-mismatch guard. | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: 58e0b08
- [x] **SPT-2a** — No-op: closed as satisfied-by-existing-behaviour. `get_expiry_candidates(preference=["monthly"])` already enforces a `dte >= 14` floor, so `resolve_monthly_option` never returns a
  `<= 13-DTE` contract — the near-month is already rolled to next-month at 14 DTE. A `<= 7` hold would need to bypass that floor and realign `src/signals/snapshot.py`. Operator kept the 14-DTE roll
  (DECISIONS.md §"Signals Paper Track — Execution Layer" 2026-09-10 follow-up). No code change. | Owner: Antigravity | Model: n/a | Review: none | SHA: `<docs-only>`
- [x] **SPT-3** — Entry executor: `src/strategy/signal_track_v1.py` `PaperStrategy` — `DailySignal` → `resolve_monthly_option` → `LegSpec` → `PaperExecutor` fill → frozen `SignalPaperEntry` → Telegram
  entry message. Also creates `src/strategy/signal_exit.py` as the SL/target constants home (`SL_PCT` / `TGT_PCT` / `RULESET_VERSION` / `derive_levels`), imports `paper.constants.LOT_SIZE`, and
  exposes the entry path as a plain `open_signal_paper_entry(signal, snapshot, broker, store)` callable (shared with SPT-6, no hardcoded level literals). Extract `_render_table` →
  `src/notifications/formatting.py::build_position_table`. As-built: `open_signal_paper_entry` is `async` (both callers already run in an event loop); the entry hook fetches its own option chain
  (`broker.get_option_chain` + `parse_upstox_option_chain`) for bid/ask rather than `find_option_leg`; `PaperStore.record_signal_open_leg` added to return the opening BUY `paper_trades.id`; the fenced
  position table is `build_position_table(..., title=None)`. | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: 6b0dada
- [x] **SPT-3b** — Split from SPT-5 (2026-09-11, dependency ordering): extend `src/strategy/signal_exit.py` (created in SPT-3 as the constants module) with the pure `evaluate(entry, mark, now) →
  TARGET | STOP_LOSS | TIME_EXIT | HOLD` + `SignalExitReason` (`TRAILING_STOP` reserved, unused). No I/O, no fill, no persistence — SPT-4 needs this to exist before it can wire the monitor tick. |
  Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: c050de0
- [x] **SPT-4** — Register `paper_signal_track_v1` with `StrategyMonitor` via a new per-strategy `due_interval_s` (30 s; credit spreads stay 90 s); per-tick `paper_signal_marks` row (mark / MFE / MAE
  / stale / gap_event); hand tick to `signal_exit.evaluate` (SPT-3b). As-built: cadence is a tick-count/ratio scheme (not wall-clock elapsed time) so repeated `_tick()` calls in tests stay
  deterministic; `quote_ts` is always `None` for now (the chain parser doesn't expose one yet, so `stale` is currently dead in production, logic unit-tested directly); a non-HOLD decision from
  `signal_exit.evaluate` is only logged + deduped in-memory (`_exit_fired_trade_ids`) — no fill/close, that's SPT-5. | Owner: Claude | Model: claude-sonnet-5 | Review: greeks-analyst + code-reviewer |
  SHA: 7b11e83
- [x] **SPT-5** — Caller-side wiring only (evaluator moved to SPT-3b): on a non-HOLD decision from SPT-4's tick, take the exit fill at the observed mark via `PaperFillSimulator`, close the row +
  `paper_exit_events`, send the Telegram exit message. As-built: the closing SELL leg is recorded via `PaperStore.record_trade` (not `record_signal_open_leg`, which is opening-leg-only) — flagged
  independently by both `code-reviewer` and `greeks-analyst` in review. | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer + greeks-analyst | SHA: 06df9d8
- [x] **SPT-6** — Entrypoint wiring, **no new cron**: a guarded paper-entry tail-call in `scripts/morning_signal.py` right after `store.record_signal(signal)`; a `paper_signal_track_v1` registration
  with `due_interval_s=30` inside `scripts/monitor_daemon.py`; `scripts/signal_paper_entry.py` as a manual `--date` backfill / re-entry tool (idempotent, **not** a scheduled cron). No unit tests.
  Deliver the updated runbook crontab comment block plus log paths. As-built: `morning_signal.py` instantiates its own `PaperStore(settings.db_path)` (same file as `SignalStore`, the codebase's
  established multi-store pattern) and `await open_signal_paper_entry(signal, snapshot, broker, paper_store)` inside a `try/except Exception` isolation block, same shape as the entry-premium-capture
  try/except just above it; `monitor_daemon.py` registers `SignalTrackV1` structurally identically to the sibling strategy blocks — `due_interval_s=30` is a class attribute on `SignalTrackV1` (set in
  SPT-4), not a registration-time param. `test_monitor_daemon.py`'s two strategy-count assertions bumped +1 for the always-registered `SignalTrackV1`. | Owner: Claude | Model: claude-sonnet-5 |
  Review: code-reviewer | SHA: 1f52880
- [x] **SPT-7** — PAPER TRACK evaluation report over `--from` / `--to` (default: first paper entry → +6 calendar months), grouped by `ruleset_version`: the metric set + the all-pass G1–G9 go-live
  gate. Manual / periodic report — invoked like `signal_report` today, not a scheduled entrypoint. | Owner: Claude | Model: claude-sonnet-5 | Review: code-reviewer | SHA: 71da2d5
- [x] **SPT-8** — Docs close: `CONTEXT.md`, `DECISIONS.md` as-built note (the `morning_signal` tail-call seam, `signal_exit.py` as constants + evaluator home, `signal_paper_entry.py` = manual tool, 30
  s vs 90 s-fallback as shipped), `DB_REGISTRY.md`, `TODOS.md`, `docs/plan/README.md`, `src/strategy/CLAUDE.md`; mark `signals/` S5.5a `won't-do`; archive per §Conventions. As-built:
  `src/strategy/CLAUDE.md` did not exist — created it (also added `strategy` to root `CLAUDE.md`'s module index + `protocol-reference` §5). | Owner: Claude | Model: claude-sonnet-5 | Review: none |
  SHA: <pending>: filled after commit

## Story done when

- **SPT-1** — the council has ruled; the ruling is in `DECISIONS.md`; `schema.md` exists; SPT-2..SPT-8 and `stories.md` are rewritten to match. ✅
- **SPT-2** — `SignalPaperEntry` / `SignalMark` round-trip through the store; a second open is rejected; `cumulative_pnl()` aggregates correctly; happy-path + edge tests pass, no real DB.
- **SPT-2a** — closed as a no-op 2026-09-10: the `dte >= 14` floor in `get_expiry_candidates` already delivers the next-month roll; operator kept it. No code, no tests.
- **SPT-3** — a firing `DailySignal` produces one resolved-option paper entry at a simulated fill, one `paper_trades` row + one frozen `SignalPaperEntry`, one Telegram entry message stating the fill
  price; NO_TRADE / already-open are logged no-ops; the EOD PT summary still renders after the `build_position_table` extraction.
- **SPT-3b** — `evaluate()` returns `TARGET` / `STOP_LOSS` / `TIME_EXIT` / `HOLD` per the priority rule; `SignalExitReason.TRAILING_STOP` is defined but never returned; happy-path + edge tests pass,
  no I/O.
- **SPT-4** — `paper_signal_track_v1` is polled every 30 s while open, each tick writes a `paper_signal_marks` row, and each tick reaches `signal_exit.evaluate` without duplicate firing.
- **SPT-5** — an open position exits on the first of `TARGET` / `STOP_LOSS` / the 15:00 square-off; the fill is taken at the observed mark; the row + `paper_exit_events` record the reason and realised
  P&L; a Telegram exit message goes out.
- **SPT-6** — no crontab line is added; `morning_signal` opens the paper entry via a guarded tail-call, the monitor picks up `paper_signal_track_v1` at 30 s, and `signal_paper_entry.py` is a manual
  idempotent backfill tool that no-ops on NO_TRADE / already-open / holiday.
- **SPT-7** — the report aggregates the paper track over a window, grouped by ruleset version, and returns an explicit all-pass / fail against G1–G9; it is a manual invocation, not a cron.
- **SPT-8** — every state doc, `DB_REGISTRY.md`, and `src/strategy/CLAUDE.md` reflect the shipped execution layer; `signals/` S5.5a is `won't-do`; the story folder is archived.

## After each task

Set `SHA:` to the real commit SHA on the task line and tick the box. Then update this story's status in `docs/plan/README.md` (single story) and add one line to `TODOS.md` Session Log. When the whole
story is done, follow `docs/plan/README.md` §Conventions *Completion → archive*.

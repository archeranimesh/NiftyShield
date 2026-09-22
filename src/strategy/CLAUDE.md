# src/strategy — Module Context

> Auto-loaded when working inside `src/strategy/`. Read this before touching any file here.

---

## Module Purpose

The paper-backbone strategy layer: `PaperStrategy` protocol implementations run on the shared `StrategyMonitor` daemon, dispatch fills through `PaperExecutor`, and persist through `src/paper/`'s
`PaperStore`. Seven strategies live here: `CSPNiftyV1`, `CCOverlayV1`, `PPOverlayV1`, `CollarOverlayV1`, `IronCondorV1`, `IronCondorV2`, `NiftyTrackComparisonV1`, plus `SignalTrackV1` (added by
`signals-paper-track/`). Shared engines: `ExitSignalEngine`, `ProfitLockEngine`, `OverlayCloser`, `ic_close_executor`, `roll_utils`.

---

## `SignalTrackV1` — signals paper-track execution layer

Turns the `src/signals/` daily multi-LLM consensus into a paper-traded long-option position. Module boundary ruled by council q17 (2026-09-09,
`docs/archive/council/strategy/2026-09-09_signals-paper-track-execution-layer.md`, absorbed into `DECISIONS.md` §"Signals Paper Track — Execution Layer"): `paper_signal_track_v1` on the shared
`StrategyMonitor` / `PaperExecutor` / `PaperStore` — **not** a self-contained loop in `src/signals/`.

### `src/strategy/signal_exit.py` — constants + pure evaluator, one module two halves

Added across two tasks because the monitor-tick wiring needed the evaluator to exist first:

- **Constants** (SPT-3): `SL_PCT` (0.30), `TGT_PCT` (0.50), `RULESET_VERSION` ('v1'), `derive_levels(entry_premium) -> (sl_price, tgt_price)` — frozen at entry, never recalculated mid-trade.
- **Evaluator** (SPT-3b): `evaluate(entry, mark, now) -> SignalExitReason`. Pure, no I/O, no state. Priority: `TARGET` (mark >= tgt_price) -> `STOP_LOSS` (mark <= sl_price) -> `TIME_EXIT` (now >=
  15:00 IST) -> `HOLD`. `SignalExitReason.TRAILING_STOP` is defined but never returned in Phase 1 — reserved so a future trailing-stop redesign needs no enum migration.

### Entry / exit path

`open_signal_paper_entry(signal, snapshot, broker, store)` (`signal_track_v1.py`) is the shared entry hook — called both from `scripts/morning_signal.py`'s guarded tail-call and from the manual
`scripts/signal_paper_entry.py` backfill tool. It resolves the monthly option via `resolve_monthly_option`, takes a simulated BUY fill via `PaperFillSimulator`, writes the opening leg through
`PaperStore.record_signal_open_leg`, and freezes a `SignalPaperEntry` row via `PaperStore.open_signal_entry`. On a non-`HOLD` decision from `signal_exit.evaluate`, `SignalTrackV1._close_position`
takes the exit fill at the **observed mark** (not the threshold price — a gap-through is booked as-is), closes the row + writes `paper_exit_events` via `PaperStore.close_signal_entry`, and records the
closing SELL leg through `PaperStore.record_trade` — **not** `record_signal_open_leg`, which is opening-leg-only (flagged independently by both `code-reviewer` and `greeks-analyst` in SPT-5 review).

### Cadence

`SignalTrackV1.due_interval_s = 30` (class attribute, not a registration-time param) — checked by `StrategyMonitor`'s per-strategy due-scheduling so quotes are fetched only for strategies due that
tick (credit spreads stay at the default 90 s). The documented 90 s fallback (+ gap-event flagging) has never been triggered — 30 s has proven practical on chain-fetch latency.

### Telemetry

Every monitor tick while a position is open writes one `paper_signal_marks` row (`mark`, `mfe_pct`, `mae_pct`, `stale`, `gap_event`) — the Phase 2 dataset and the SPT-7 6-month go-live-gate input.
`quote_ts` is always `NULL` in production (the chain parser doesn't expose a broker quote timestamp yet), so `stale` is currently dead there; its logic is unit-tested directly. DDL + table detail:
`DB_REGISTRY.md`, `docs/archive/plan/signals-paper-track/schema.md`.

### Invariants

- One `paper_signal_track_v1` position open at a time — a second `open_signal_paper_entry` call while one is open is a logged no-op, never a second row.
- `sl_price` / `tgt_price` / `ruleset_version` are frozen at entry from `derive_levels` and never recalculated mid-trade — a recalibration ships as a new `ruleset_version` cohort (e.g. `'v2'`), never
  an in-place mutation of an open trade's levels.
- `signal_exit.py` stays pure — no `PaperStore`, no broker, no Telegram import in that module.
- Hard 15:00 IST square-off — no overnight hold, even after a future trailing-stop (Phase 2).

### Not yet exercised

The SPT-7 go-live gate (G1–G9) and the live pilot: the 6-month paper evaluation window has not elapsed as of this note (2026-09-11).

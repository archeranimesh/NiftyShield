# Signals Paper Track — prompt

> Turn the multi-LLM directional signal into a live paper-traded strategy: auto-enter the daily consensus as a long monthly option (near-month, rolling to next month at ≤ 7 DTE), monitor it intraday
> against a stop-loss / target / trailing-stop, auto-exit on a hit or square off by 15:00, and record every entry and exit for a 6-month evaluation window that gates the go-live decision.

Read `CONTEXT.md` and state `CONTEXT.md ✓` before anything else. Then read `tasks.md`, find the first unchecked `- [ ]`, and do **only** that task. Read that task's full spec in `stories.md` (same
task id) before writing any code. One task per session. Complete it fully. Stop.

**SPT-1 is a council checkpoint — no code.** Its output rewrites SPT-2 onward. Do not start SPT-2+ until the council decision has landed in `DECISIONS.md` and this folder's `tasks.md` / `stories.md`
have been updated from it.

## Why this story exists

The `signals/` epic (S1–S6) built the signal pipeline: at 09:15 three LLMs vote on Nifty direction, `SignalAggregator` produces a consensus `DailySignal`, and `record_signal_outcome.py` records at
15:00 what a trade *would* have done. That is a backtest-by-hand — there is no position, no intraday management, no fill.

Animesh's decision (2026-09-08): the track must actually paper-trade. Enter the consensus signal as a real (simulated-fill) long option position, manage it intraday with a predefined stop-loss and
target — or a trailing stop — and square off by 15:00 if neither fires. Run this for ~6 months; if the realised paper P&L is satisfactory, promote the strategy to live. The signal advisory alone is
not a decision-grade track record.

This needs an execution layer the signals package does not have: an entry executor, an intraday monitor loop, an exit engine, and a paper-position model. The repo already has all four shapes in
`src/strategy/` (`StrategyMonitor`, `PaperExecutor`, `ExitSignalEngine`, `ProfitLockEngine`) and `src/paper/` (`PaperStore`, `PaperTrade`, fill simulator, `TradeState`), but the signals track was
deliberately built independent of the paper engine — own models, own SQLite tables, zero `backtest-engine` / `src/paper` dependency. Whether to reuse that machinery or build a self-contained loop in
`src/signals/` is a load-bearing, hard-to-reverse call that spans strategy design, architecture, and risk — hence SPT-1.

## Scope guard

**In bounds:** a new execution layer for the signals track — an entry executor, an intraday monitor registration, a pure exit evaluator (SL / target / 15:00), the paper-position models
+ telemetry table, and the entry + exit Telegram messages. Module home fixed by SPT-1: a `PaperStrategy` `paper_signal_track_v1` in `src/strategy/`, with the exit evaluator in
  `src/strategy/signal_exit.py` and persistence on the shared `PaperStore`.

**Out of bounds:** the signal pipeline itself (`src/signals/models.py`, `aggregator.py`, `snapshot.py`, `providers/`, `factory.py`, `scripts/morning_signal.py`) — unchanged except where SPT-6 hands
the `DailySignal` to the new entry step (one guarded tail-call after `store.record_signal`). The live (non-paper) portfolio, `src/portfolio/`, and the finideas strategies are untouched. No real orders
— simulated fills only, consistent with `Order execution blocked (static IP)` in `CONTEXT.md`.

**Deferred to a follow-up story** (`docs/plan/signals-entrypoint-consolidation/`, do **not** start until this story ships): a `DailySignal.is_actionable` predicate to kill the repeated `trade_action
is not NO_TRADE` check; merging `record_signal_outcome.py` + `signal_report.py` into one 16:00 EOD script; a `market_calendar.guard_trading_day()` helper. SPT-3 keeps its own inline NO_TRADE check and
literal guard in the interim — one extra copy, removed there.

**One carved exception (2026-09-09 decision):** `src/signals/option_resolver.py::resolve_monthly_option` gains a ≤ 7-DTE roll — when the near-month monthly is 7 or fewer calendar days to expiry it
advances to the next month's last-Tuesday contract. This keeps the paper-track entry and `record_signal_outcome.py` on the exact same instrument (both call `resolve_monthly_option`), so SPT-3 reuses
it unchanged. `src/instruments/lookup.py::get_expiry_candidates` and its `dte >= 14` monthly floor are **not** touched — they are shared by the finideas overlays, the IC strategies and the chain
pipelines, all out of bounds here.

**Overlap with `docs/plan/signals/`:** S5.5c (the 09:15 advisory message) stays there. S5.5a (the 15:00 outcome message) is **superseded** by this story's exit message — mark S5.5a `won't-do` and
point it here once SPT's exit message lands. S5.5b (holiday guard) still applies to `morning_signal.py` and should ship independently.

## Session-start load hints

Beyond `CONTEXT.md`:
- `DECISIONS.md` — the §Paper & Reporting entries, the 2026-07-02 paper-delta-source council, and (after SPT-1) the new SPT architecture entry.
- `docs/plan/signals/signals_stories.md` — the `DailySignal` / `SignalResponse` shapes and the `record_signal_outcome.py` `--auto` monthly-expiry resolution this story reuses.
- `src/strategy/CLAUDE.md` and `src/paper/CLAUDE.md` — the existing monitor/executor/store contracts SPT-1 weighs reusing.
- `src/signals/` — read the current package before proposing where the new layer lives.
- `BACKTEST_PLAN.md` Phase 0 — the paper-trading / evaluation-gate context.
- `REFERENCES.md` — monthly-expiry calendar (last Tuesday; Thursday→Tuesday change, April 2026), lot size.
- This story changes DB schema (a signals paper-position table). It carries `schema.md` once SPT-1 fixes the storage decision — read it before any Store work.

## Task overview

SPT-1 is closed (ruled 2026-09-09, council q17 — `docs/archive/council/strategy/2026-09-09_signals-paper-track-execution-layer.md`, absorbed into `DECISIONS.md`). `tasks.md` / `stories.md` /
`schema.md` are the authoritative rewrite; the list below is the map.

**Fixed by the ruling + the pre-council locks:** module boundary **A** (`paper_signal_track_v1` on the shared `StrategyMonitor` / `PaperExecutor` / `PaperStore`); pure `src/strategy/signal_exit.py`;
monthly expiry, near-month, ≤ 7-DTE roll via `resolve_monthly_option`; fixed 1 lot; fixed SL −30 % / target +50 % of the entry fill (provisional); hard 15:00 square-off; Phase 1 fixed-only
(`TRAILING_STOP` reserved); 30 s per-strategy monitor cadence; mark-path telemetry from day one; two-tier recalibration (N=30 fuse / 6-month N≈50 redesign / v2 cohort); go-live gate G1–G9 all-pass;
auto-execute 1-lot live pilot.

- **SPT-1** — Council checkpoint. ✅ Done — `DECISIONS.md` entry + `schema.md` + the SPT-2..8 rewrite.
- **SPT-2** — `SignalPaperEntry` / `SignalMark` models + store methods (incl. `cumulative_pnl`).
- **SPT-2a** — ✅ Closed 2026-09-10 as a no-op: the `dte >= 14` floor in `get_expiry_candidates` already rolls `resolve_monthly_option` to next-month; operator kept it (see `tasks.md` + DECISIONS.md).
- **SPT-3** — Entry executor: `src/strategy/signal_track_v1.py` `PaperStrategy` + `build_position_table` extraction + Telegram entry message.
- **SPT-4** — `StrategyMonitor` registration at 30 s + per-tick `paper_signal_marks` logging.
- **SPT-5** — `src/strategy/signal_exit.py` pure evaluator + exit fill at the observed mark + Telegram exit message.
- **SPT-6** — Entrypoint wiring, no new cron: `morning_signal` paper-entry tail-call + `monitor_daemon` registration + `scripts/signal_paper_entry.py` as a manual backfill tool.
- **SPT-7** — PAPER TRACK evaluation report + the all-pass G1–G9 go-live gate.
- **SPT-8** — Docs close: `CONTEXT.md`, `DECISIONS.md` as-built, `DB_REGISTRY.md`, `TODOS.md`, `docs/plan/README.md`, `src/strategy/CLAUDE.md`; archive.

## Definition of done

The signals consensus is auto-entered as a paper long-option position each trading day it fires, managed intraday against a documented SL / target / trailing rule, exited on a hit or by 15:00, and
every entry and exit is persisted and pushed to Telegram. A report aggregates the paper track into the go-live gate metrics. All new public functions carry happy-path + edge tests; no network, no real
DB, no real orders in the suite. SPT-1's decision is recorded in `DECISIONS.md` and reflected in the shipped `tasks.md`.

## Perspectives not covered

The economic realism of simulated intraday fills for monthly Nifty options (slippage, spread, the 15:00 square-off assumption). Positions are intraday-only — never held overnight — so theta is a minor
cost and bid/ask is the dominant one; the ≤ 7-DTE roll keeps entries in the liquid near-month. SPT-1's rule design should name a fill model, but a rigorous slippage study is a separate
backtest-methodology question, not scoped here.

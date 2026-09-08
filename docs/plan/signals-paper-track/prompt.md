# Signals Paper Track — prompt

> Turn the multi-LLM directional signal into a live paper-traded strategy: auto-enter the
> daily consensus as a long weekly option, monitor it intraday against a stop-loss / target /
> trailing-stop, auto-exit on a hit or square off by 15:00, and record every entry and exit
> for a 6-month evaluation window that gates the go-live decision.

Read `CONTEXT.md` and state `CONTEXT.md ✓` before anything else.
Then read `tasks.md`, find the first unchecked `- [ ]`, and do **only** that task.
Read that task's full spec in `stories.md` (same task id) before writing any code.
One task per session. Complete it fully. Stop.

**SPT-1 is a council checkpoint — no code.** Its output rewrites SPT-2 onward. Do not start
SPT-2+ until the council decision has landed in `DECISIONS.md` and this folder's `tasks.md` /
`stories.md` have been updated from it.

## Why this story exists

The `signals/` epic (S1–S6) built the signal pipeline: at 09:15 three LLMs vote on Nifty
direction, `SignalAggregator` produces a consensus `DailySignal`, and `record_signal_outcome.py`
records at 15:00 what a trade *would* have done. That is a backtest-by-hand — there is no
position, no intraday management, no fill.

Animesh's decision (2026-09-08): the track must actually paper-trade. Enter the consensus
signal as a real (simulated-fill) long option position, manage it intraday with a
predefined stop-loss and target — or a trailing stop — and square off by 15:00 if neither
fires. Run this for ~6 months; if the realised paper P&L is satisfactory, promote the
strategy to live. The signal advisory alone is not a decision-grade track record.

This needs an execution layer the signals package does not have: an entry executor, an
intraday monitor loop, an exit engine, and a paper-position model. The repo already has all
four shapes in `src/strategy/` (`StrategyMonitor`, `PaperExecutor`, `ExitSignalEngine`,
`ProfitLockEngine`) and `src/paper/` (`PaperStore`, `PaperTrade`, fill simulator, `TradeState`),
but the signals track was deliberately built independent of the paper engine — own models,
own SQLite tables, zero `backtest-engine` / `src/paper` dependency. Whether to reuse that
machinery or build a self-contained loop in `src/signals/` is a load-bearing, hard-to-reverse
call that spans strategy design, architecture, and risk — hence SPT-1.

## Scope guard

**In bounds:** a new execution layer for the signals track — an entry executor, an intraday
monitor, an exit engine (SL / target / trailing), a paper-position model and its persistence,
and the entry + exit Telegram messages. The exact module home (`src/signals/` vs a
`PaperStrategy` under `src/strategy/`) is SPT-1's decision.

**Out of bounds:** the signal pipeline itself (`src/signals/models.py`, `aggregator.py`,
`snapshot.py`, `providers/`, `factory.py`, `scripts/morning_signal.py`) — unchanged except
where SPT hands the `DailySignal` to the new entry step. The live (non-paper) portfolio,
`src/portfolio/`, and the finideas strategies are untouched. No real orders — simulated fills
only, consistent with `Order execution blocked (static IP)` in `CONTEXT.md`.

**Overlap with `docs/plan/signals/`:** S5.5c (the 09:15 advisory message) stays there. S5.5a
(the 15:00 outcome message) is **superseded** by this story's exit message — mark S5.5a
`won't-do` and point it here once SPT's exit message lands. S5.5b (holiday guard) still
applies to `morning_signal.py` and should ship independently.

## Session-start load hints

Beyond `CONTEXT.md`:
- `DECISIONS.md` — the §Paper & Reporting entries, the 2026-07-02 paper-delta-source council,
  and (after SPT-1) the new SPT architecture entry.
- `docs/plan/signals/signals_stories.md` — the `DailySignal` / `SignalResponse` shapes and the
  `record_signal_outcome.py` `--auto` weekly-expiry resolution this story reuses.
- `src/strategy/CLAUDE.md` and `src/paper/CLAUDE.md` — the existing monitor/executor/store
  contracts SPT-1 weighs reusing.
- `src/signals/` — read the current package before proposing where the new layer lives.
- `BACKTEST_PLAN.md` Phase 0 — the paper-trading / evaluation-gate context.
- `REFERENCES.md` — weekly-expiry calendar (Thursday→Tuesday change, April 2026), lot size.
- This story changes DB schema (a signals paper-position table). It carries `schema.md` once
  SPT-1 fixes the storage decision — read it before any Store work.

## Task overview

Provisional — SPT-1's council output rewrites SPT-2 onward before any of it is executed.

- **SPT-1** — Council checkpoint (no code): reuse `src/strategy`+`src/paper` vs self-contained
  `src/signals` loop, and the SL / target / trailing-stop rule design. Output → `DECISIONS.md`
  + a rewrite of this file's `tasks.md` / `stories.md`.
- **SPT-2** — Paper-position model + `schema.md` + Store (persist entry, exit, state, P&L).
- **SPT-3** — Entry executor: `DailySignal` → resolved weekly option → simulated fill → row +
  Telegram entry message.
- **SPT-4** — Intraday monitor loop: poll the position's LTP on a cadence, evaluate exit rules.
- **SPT-5** — Exit engine: stop-loss, target, trailing-stop, 15:00 square-off; exit fill + row
  update + Telegram exit message with P&L.
- **SPT-6** — Cron / entrypoint wiring + market-calendar guard + `SIGNAL_PHASE` handling.
- **SPT-7** — 6-month evaluation report: extend `signal_report.py` (or a new report) with the
  paper-track realised P&L, win rate, and the go-live gate criteria.
- **SPT-8** — Docs close: `CONTEXT.md`, `DECISIONS.md`, `TODOS.md`, `docs/plan/README.md`,
  module `CLAUDE.md`.

## Definition of done

The signals consensus is auto-entered as a paper long-option position each trading day it
fires, managed intraday against a documented SL / target / trailing rule, exited on a hit or
by 15:00, and every entry and exit is persisted and pushed to Telegram. A report aggregates
the paper track into the go-live gate metrics. All new public functions carry happy-path +
edge tests; no network, no real DB, no real orders in the suite. SPT-1's decision is recorded
in `DECISIONS.md` and reflected in the shipped `tasks.md`.

## Perspectives not covered

The economic realism of simulated intraday fills for weekly Nifty options near expiry
(slippage, spread, the 15:00 square-off assumption) — SPT-1's rule design should name a fill
model but a rigorous slippage study is a separate backtest-methodology question, not scoped
here.

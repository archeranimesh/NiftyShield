# Options Income Strategy — prompt

> Systematic premium-collection strategy on Nifty index options: signal engine, strike selection, backtest V1/V2, paper trading, reporting.

Read `CONTEXT.md` and state `CONTEXT.md ✓` before anything else. Then read `tasks.md`, find the first unchecked `- [ ]`, and do **only** that task. Read that task's full spec in `stories.md` (same
task id) before writing any code. One task per session. Complete it fully. Stop.

## Why this story exists

Bullish-biased, trend-filtered premium collection on Nifty options — short 5-delta puts (monthly, naked) or 5/2-delta put spreads (quarterly) — gated by a 100-SMA trend filter, a neutral-zone block,
an India VIX floor, and an event calendar. The strategy is a hard-stop, no-rolling design: delta breach or expiry proximity closes the position outright. This story takes it from spec to backtested,
paper-traded, reported system across nine sequential tasks (S0–S8), each gated on the previous one's output (data audit → signal → strikes → positions → backtest → paper → reporting → docs close).

**Canonical strategy spec:** `plan.md` — every implementation task must trace back to a rule there. Do not add strategy logic that isn't in `plan.md`; if a gap is found, stop and raise it rather than
inventing a rule.

## Scope guard

In bounds: `src/options_income/` (signal, strike selector, position manager, backtest V1/V2), `src/paper/options_income_runner.py`, `scripts/audit/options_data_audit.py`, `scripts/backtest/run_v1.py`
/ `run_v2.py`, `scripts/reports/options_income_report.py`, and matching test packages under `tests/unit/`. This is new `src/` behaviour, not docs/tooling only. Out of bounds: any other strategy
module, `BrokerClient` protocol changes beyond calling existing methods, and any change to rolling/adjustment logic — the spec is explicitly hard-stop, no rolling.

## Session-start load hints

Read the matching module `CLAUDE.md` for `src/paper/` before S6. `REFERENCES.md` for instrument-key conventions before S2/S6. `LOGGING.md` before any new entrypoint script (S0, S4/S5 CLI runners, S7).
`DECISIONS.md` gets new entries at S8 — read it first to avoid duplicate rows.

## Task overview

- **S0** — Data audit: confirm historical Nifty options EOD data completeness.
- **S1** — Signal engine: SMA/neutral-zone/VIX-floor/event-calendar entry gate.
- **S2** — Strike selector: delta-based put and spread selection from a chain snapshot.
- **S3** — Position manager: exit-check pure function and P&L computation.
- **S4** — Backtest V1: monthly naked-put simulation over full history.
- **S5** — Backtest V2: quarterly put-spread simulation over full history.
- **S6** — Paper trading: daily runner wired to live Upstox chain + Telegram.
- **S7** — Reporting: backtest summary, V1-vs-V2 comparison, active paper positions.
- **S8** — Docs close: `CONTEXT.md`, `DECISIONS.md`, `TODOS.md`.

## Definition of done

Both variants (V1 monthly naked put, V2 quarterly spread) are backtested end-to-end on historical data with metrics computed, a paper-trading runner exercises live signals against
`MockBrokerClient`-verified logic with Telegram alerts on entry/exit, a reporting script prints the V1/V2 comparison plus active paper positions, and `CONTEXT.md` / `DECISIONS.md` / `TODOS.md` reflect
the new module. Every public function has a happy-path and an edge/error-case test; no network calls in tests.

## Perspectives not covered

No live-execution or real-money review — paper trading is the live gate per `plan.md` "Out of Scope (v1.0)", so this story never reaches a broker-execution or capital-at-risk sign-off; that review
belongs to whichever story promotes paper to live. No independent options-strategist review of the strategy rules themselves (trend filter thresholds, delta targets, hard-stop level) — `plan.md` is
treated as given, not re-derived here.

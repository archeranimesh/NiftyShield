# risk-gamma-phase-a — prompt

> Two parallel tracks shipped in one phase: (A) wiring `src/risk/` delta gate into `record_paper_trade.py`, and (B) the Near-Expiry Gamma Buy strategy scaffolding + `gamma_daily_watch.py` script.

Read `CONTEXT.md` and state `CONTEXT.md ✓` before anything else. Then read `tasks.md`, find the first unchecked `- [ ]`, and do **only** that task. Read that task's full spec in `stories.md` (same
task id) before writing any code. One task per session. Complete it fully. Stop.

## Why this story exists

Paper trading needed a portfolio delta gate on new entries (Track A) and a scaffold for the Near-Expiry Gamma Buy strategy (Track B) — a daily scan that snapshots the option chain near each week's
expiry, maintains a watchlist of high-gamma strikes, and alerts on qualifying setups. Track A shipped first and unblocks safe paper-trade entry; Track B builds out `src/gamma/` and
`scripts/gamma_daily_watch.py` in small, testable increments so each sub-task lands as one reviewable commit.

## Scope guard

In bounds: `src/risk/` wiring into `scripts/record_paper_trade.py` (Track A, done); `src/gamma/` models + `GammaStore`; `scripts/gamma_daily_watch.py` chain fetch, snapshot persistence, watchlist
maintenance, percentile calibration, and the Telegram summary (Track B). Out of bounds: `gamma_scan.py` (a separate story — see the note at the foot of `stories.md`) and any change to `src/risk/`
internals themselves. This story changes `src/` behaviour; it is not docs/tooling only.

## Session-start load hints

- `src/gamma/CLAUDE.md` (if present) before touching `src/gamma/`.
- `docs/strategies/near_expiry_buy_v1.md` — full strategy spec, especially §5b (watchlist add/elevate/remove criteria) and §11 (DDL for `gamma_chain_snapshots` and `gamma_watchlist`) for any
  `GammaStore` work.
- Greeks/delta fields are involved (gamma gearing, chain snapshots) — `greeks-analyst` review is expected on B2.2 and B2.4 per `CLAUDE.md` AutoTrigger rules.

## Task overview

- **A** — Wire `src/risk/` delta gate into `record_paper_trade.py`. Done.
- **B1** — `src/gamma/` package: models + `GammaStore`. Done.
- **B2.1** — `gamma_daily_watch.py` scaffold: CLI flags + expiry resolution. Done.
- **B2.2** — Chain fetch + field computation. Open.
- **B2.3** — Snapshot persistence. Open.
- **B2.4** — Watchlist maintenance. Open.
- **B2.5** — Percentile calibration + Telegram summary. Open.

## Definition of done

`gamma_daily_watch.py` runs end to end: fetches the option chain for the current and next week's expiry, computes gamma-gearing/distance/OI-change/spread/DTE fields, persists snapshots, maintains the
watchlist per §5b add/elevate/remove rules, calibrates IV and gearing percentiles, and sends a non-fatal Telegram summary. All stages covered by unit tests with no network and no real SQLite.

## Perspectives not covered

Live-market validation of the gamma-gearing threshold (`>= 3.0`) and the percentile calibration window (20/60 days) against real NSE option chain behaviour — this story only covers the scaffolding and
unit-test correctness, not strategy backtesting or live P&L attribution.

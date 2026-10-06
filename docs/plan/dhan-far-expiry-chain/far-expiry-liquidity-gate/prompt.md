# Far-Expiry Liquidity Gate — prompt

> A calibrated gate on the target-delta strike (two-sided quote, spread cap, OI floor) with a defined fallback ladder, and the data-driven yearly roll window.

Read `CONTEXT.md` and state `CONTEXT.md ✓` before anything else. Then read `tasks.md`, find the first unchecked `- [ ]`, and do **only** that task. Read that task's full spec in `stories.md` (same
task id) before writing any code. One task per session. Complete it fully. Stop.

## Why this story exists

"Adjust based on liquidity" must be code, applied identically by every strategy, with thresholds taken from observed data rather than guessed. The existing `_apply_liquidity_gate` checks spread as a
fraction of mid only; it has no OI floor, no two-sided-quote requirement and no fallback ladder.

## Scope guard

Blocked until the capture has enough history (README open decision 2, default 15 trading days). Extend the existing gate; do not add a second one. Existing callers keep their current default
behaviour. No strategy-specific branches.

## Design review

OCP: thresholds are per-expiry-type config; the fallback ladder is data (ordered steps), not nested `if`. DIP: the gate is a pure function over a chain. Prior-art:
`strike_selector._apply_liquidity_gate` and the `gate_violations` THRESHOLD-gate pattern (log-only under `--log-only-gates`).

## Session-start load hints

`docs/plan/dhan-far-expiry-chain/far-expiry-capture/` report output, `src/instruments/strike_selector.py`, `DB_REGISTRY.md` note on `gate_violations`, `docs/plan/yearly-overlays/README.md`.

## Task overview

FG-1 calibration findings (Claude) → FG-2 extend the gate and ladder → FG-3 roll-window decision.

## Definition of done

Thresholds recorded with the data behind them; gate tests cover pass, each failure reason and each ladder step; monthly/IC callers' results unchanged; yearly `roll_dte` set with evidence.

## Perspectives not covered

Execution cost beyond the spread: market impact on thin far-dated strikes is not modelled; the gate only screens on displayed quotes.

# Chart Model Overlay — prompt

> Add the model-driven layer to the payoff chart: the blue dashed T+0 mark-to-market curve,
> the ±1σ/±2σ expected-move bands, and POP (probability of profit) in the stat strip.

Read `CONTEXT.md` and state `CONTEXT.md ✓` before anything else.
Then read `tasks.md`, find the first unchecked `- [ ]`, and do **only** that task.
Read that task's full spec in `stories.md` (same task id) before writing any code.
One task per session. Complete it fully. Stop.

## ⛔ Blocked — check before starting any task

This story must not begin until **both** hold:

1. `chart-core/` is complete (every box in `../chart-core/tasks.md` ticked).
2. `greeks-bs-fallback/` GF-2 and GF-3 are ticked in `docs/plan/greeks-bs-fallback/tasks.md`
   — i.e. `src/pricing/black_scholes.py` (call/put price + delta) and
   `src/pricing/implied_vol.py` (`solve_iv`) exist and are tested.

If either is false, stop and report the block. Do not build a pricer or an IV solver here —
that is `greeks-bs-fallback/`'s scope.

## Why this story exists

The Stockmock reference chart shows more than the expiry payoff: a T+0 curve (today's
theoretical P&L across spot), ±1σ/±2σ vertical bands, and a POP figure. Each needs an option
pricing model. `chart-core/` deliberately shipped without them so the basic chart could land
immediately; this story adds them once the shared `src/pricing/` package exists.

## Scope guard

**In bounds:** new module `src/pricing/expected_move.py` (expected-move + POP math on top of
the `greeks-bs-fallback/` pricer); a shared ATM-IV accessor (V1 has none); a T+0 P&L series
builder; additive extensions to `src/notifications/payoff_chart.py`
(`render_expiry_payoff_png` / `build_and_send_ic_payoff` gain optional args); threading
per-leg IV + DTE through the five call sites `chart-core/` wired.

**Out of bounds:** `src/pricing/black_scholes.py` and `src/pricing/implied_vol.py` themselves
(owned by `greeks-bs-fallback/` — consume, do not edit); the three modeling decisions
(risk-free rate, DTE convention, delta tolerance — inherited from `greeks-bs-fallback/` GF-1,
use whatever it decided); the expiry payoff trapezoid + stat strip basics (done in
`chart-core/`); any DB schema change.

Changes `src/` and `scripts/` behaviour (richer chart). Not docs/tooling only.

## Session-start load hints

- `docs/plan/greeks-bs-fallback/` `prompt.md` + `stories.md` — the pricer's API surface, the
  `solve_iv` signature, and the three modeling-decision values GF-1 settled.
- `src/strategy/ic_nifty_v2.py:527` `_sd_sanity_check` and `:2789` `_atm_iv` — the existing
  1-SD-move formula and ATM-IV extraction to mirror / generalise.
- `src/notifications/CLAUDE.md` — non-fatal send contract (unchanged).
- `FORMATTING.md` — the POP % and any new label formatting.
- No `schema.md` — no DB schema change.

## Task overview

- **MO-1** — `src/pricing/expected_move.py`: `expected_move` + `pop_between` (`math.erf`).
- **MO-2** — shared `atm_iv(chain)` accessor.
- **MO-3** — `t0_pnl_series(...)` using `src/pricing/black_scholes.py`, `solve_iv` fallback for `iv == 0`.
- **MO-4** — draw the blue dashed T+0 curve on the chart.
- **MO-5** — draw the ±1σ/±2σ verticals + shaded bands.
- **MO-6** — add POP to the stat strip.
- **MO-7** — thread DTE + per-leg IV through `build_and_send_ic_payoff` + both entry scripts.
- **MO-8** — thread the same through the EOD snapshot + both close paths.
- **MO-9** — docs close (epic complete).

## Definition of done

Mirrors `tasks.md` "## Story done when". In short: the same renderer additionally draws the
T+0 curve, the σ bands, and POP; each degrades cleanly when its input (IV, DTE) is missing or
unsolvable; every call site passes the new inputs; the epic's docs record the dependency as
satisfied and the epic as complete.

## Perspectives not covered

- **Which risk-free rate / DTE convention** — deferred entirely to `greeks-bs-fallback/`
  GF-1. If that story has not settled them when a session picks up MO-3, stop: the overlay
  cannot be consistent with the rest of the repo's vol math without them.
- **Weekly-bucket IV behaviour** — `greeks-bs-fallback/` GF-1 never verified whether Upstox
  zeroes `iv` for the weekly expiry. If the weekly bucket also returns `iv == 0`, MO-3's
  `solve_iv` fallback covers it, but that path is unverified against real weekly data.
- **T+0 curve accuracy vs Stockmock** — Stockmock's exact vol surface / interpolation is
  unknown; a flat per-leg IV with no smile will diverge somewhat. Acceptable for a glance;
  not a pricing tool.

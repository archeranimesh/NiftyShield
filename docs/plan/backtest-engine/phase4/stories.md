# Backtest Engine — Phase 4 — Story Index

Full spec for every task below lives in `BACKTEST_PLAN_PHASE1.md` (root), lines 917–967.

## 4.1 — STRATEGY — Finideas evaluation
Section: `## 4.1 — STRATEGY — Finideas evaluation`. Owner: Animesh — this is not a Cowork task,
flag it back if picked up here. Prerequisites: ≥24 months of Finideas tracked realised P&L with
inception P&L, drawdown depth, and max intra-year drawdown all measurable. Benchmark against: 60%
Nifty index fund + 40% liquid debt, the CSP+IC basket net of costs, and Finideas net of its
subscription fee — compute all three over the same window. Document the decision in
`docs/decisions/finideas_evaluation_YYYY-MM.md`.

## 4.2 — STRATEGY — Fourth / fifth strategies (as maturity allows)
Section: `## 4.2 — STRATEGY — Fourth / fifth strategies`. Owner: Animesh. Candidates: short
strangle (regime-conditional, HIGH_IV only), ratio spread. One per year maximum. Each new
strategy goes through the full Phase 0–2 pipeline (spec → paper → backtest → variance check →
live) — no shortcuts even at this maturity stage.

## 4.3 — CODE — ML overlays (narrow scope only)
Section: `## 4.3 — CODE — ML overlays`. Optional — do not build speculatively. Only two candidate
problems named: vol-surface-arb detection (alert when a strike's IV is >2 SD from the fitted
surface) and slippage prediction (as a function of order size, strike distance from ATM, time of
day, trained on realised fills). **Explicitly out of scope, even at this maturity stage:**
direction prediction, strategy generation, regime prediction. Each ML feature that does get built
ships with its own spec, backtest, paper-trade validation, and kill criteria — same discipline as
a full strategy, not a shortcut because it's "just a feature."

## 4.4 — GATE — Plan closure
Section: `## 4.4 — GATE — Plan closure`. Requires 3–5 strategies in the live basket each with ≥1
year of realised data within envelope, the Finideas decision made and documented, realised
annualised basket return honestly measured/benchmarked/shared with no adjustments in
`docs/decisions/basket_performance_YYYY.md`, and confirmation that a kill criterion has actually
triggered at least once somewhere in the plan's history and was handled cleanly — the source spec
notes: if none ever triggered, either you got lucky or the kill criteria are too loose. This is
the terminal gate of `BACKTEST_PLAN_PHASE1.md` — nothing in `docs/plan/backtest-engine/` is gated
on anything past this.

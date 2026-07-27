# Backtest Engine — Phase 3 — Story Index

Full spec for every task below lives in `BACKTEST_PLAN_PHASE1.md` (root), lines 836–915.

## 3.1 — STRATEGY — Deploy IC v1 live
Section: `## 3.1 — STRATEGY — Deploy IC v1 live`. Owner: Animesh. 1 lot, no scaling for 3 months
minimum, runs in parallel with CSP. **Separate capital bucket** — do not share margin allocation
between strategies until 3.4's portfolio construction lands.

## 3.2 — STRATEGY — Third strategy specification
Section: `## 3.2 — STRATEGY — Third strategy specification`. Owner: Animesh. Two candidates:
**Jade Lizard** (preferred — short OTM put + short OTM bear call spread, net credit must exceed
call spread width to eliminate upside risk, exploits Nifty's structural put-call skew, reuses
~90% of IC engine infrastructure) vs. **Event-Driven Calendar Spread** (lower frequency, needs
`src/market_calendar/events.py` first, 18-month minimum variance-check window — deprioritised
because trade count is too low for robust validation within Phase 3's timeline). Document the
choice and rationale in `DECISIONS.md` before writing the spec. Spec doc:
`docs/strategies/jade_lizard_v1.md` or `calendar_event_v1.md` depending on choice. Must pass the
strategy-spec validator and get `options-strategist` review on sizing/risk before committing.

## 3.3 — CODE — Event calendar + calendar spread strategy
Section: `## 3.3 — CODE — Event calendar + calendar spread strategy`. **Only applies if 3.2 chose
Candidate B.** New modules `src/market_calendar/events.py` (YAML-driven, same annual-refresh
ritual as `holidays.py`) and `src/strategy/calendar_spread.py`. Paper trade ≥18 months (one full
annual cycle plus buffer) before considering live.

## 3.4 — CODE — Portfolio-level attribution
Section: `## 3.4 — CODE — Portfolio-level attribution`. Extends `PortfolioSummary` for
strategy-level breakdowns across CSP + IC + (calendar, if 3.2 chose Candidate B). New table
`strategy_daily_pnl`. New module `src/portfolio/correlation.py` — pairwise rolling 90-day
correlation, alert on any pair >0.8 for 4 consecutive weeks (concentration risk).

## 3.5 — CODE — Regime classifier (rule-based, not ML)
Section: `## 3.5 — CODE — Regime classifier`. **Read the overlap note in the source section
first.** Track A (`docs/plan/signals-eval-core/` SE2.2, `src/strategy/regime.py`) already builds
a 3×3 trend-slope × VIX-percentile regime engine. This task adds IV-based dimensions (IVR, IVP,
realised vol) on top. **Evaluate whether `src/strategy/regime.py` can be extended with IV
dimensions rather than creating a parallel `src/regime/` module** — one consolidated module with
pluggable dimension sets is architecturally preferred. Confirm with `code-reviewer` that any
consolidation doesn't break Track A's signal generators before merging. This is a measurement
module, not a prediction module — do not wire it into trade decisions yet (that's Phase 4).

## 3.6 — GATE — End of Phase 3
Section: `## 3.6 — GATE — End of Phase 3`. Requires: 3 strategies live ≥6 months each within
backtest envelope, portfolio attribution operational, regime classifier recording daily for ≥3
months, `src/risk/` fully operational (`PortfolioDeltaTracker` from Phase 0.6c + the Phase 1
scenario stress-loss engine running daily pre-market with intraday re-check), all 13 binding
rules from `DECISIONS.md §7.3` enforced with test coverage, and zero live breaches of the ₹6L
absolute portfolio drawdown kill zone. Blocks `docs/plan/backtest-engine/phase4/`.

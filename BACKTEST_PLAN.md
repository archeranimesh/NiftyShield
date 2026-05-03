# NiftyShield — Backtest → Paper → Live Pipeline Plan

> **Current phase:** Phase 0. Load this file for all backtest/paper/strategy tasks in Phase 0.
> **Phase 1+ tasks:** `BACKTEST_PLAN_PHASE1.md` — load only when Phase 0.8 gate has passed.
> **Archived done tasks (0.1, 0.2, 0.4, 0.4a, 0.5, 0.7):** `docs/archive/BACKTEST_PLAN_ARCHIVE.md`
>
> **Rendering:** Present using `mcp__visualize__show_widget` — card format with phase badge,
> section groupings (DONE ✓ / ONGOING / HARD DEADLINE / GATE), owner badges (Cowork / Animesh),
> left border: orange = Code/Cowork, purple = Strategy/Animesh, red = deadline, dashed-purple = gate.
>
> **Related files:** `CONTEXT.md` · `DECISIONS.md` · `REFERENCES.md` · `TODOS.md` · `PLANNER.md`

---

## Guiding Principles (read before starting any task)

1. **Paper trade before you backtest a strategy you've never run.** A backtest on an unfamiliar strategy is a simulation of an idealised world. Running the strategy on paper first, logging real decisions, then calibrating the backtest against that reality, is how you build a measurement instrument that can be trusted.
2. **One strategy at a time.** Running five strategies in parallel backtests is parameter optimisation dressed up as research. Ship one, run it for 6 months, only then start the next.
3. **Backtest → paper → re-backtest over the paper window → variance check → live.** This is the full loop. Skipping the re-backtest step is where retail traders fool themselves.
4. **Define kill criteria and variance thresholds before deploying.** Writing them down after the fact is self-deception.
5. **Finideas (ILTS + FinRakshak) stays running.** Current capital deployment (~₹10L) continues as-is. NiftyShield tracks it; this plan does not replace or backtest it. Evaluate Finideas separately (Phase 4) after ≥2 years of tracked realised P&L is available.
6. **Every code phase must end with:** (a) full `python -m pytest tests/unit/` green, (b) `code-reviewer` agent clean on the diff, (c) `CONTEXT.md` + `DECISIONS.md` + `TODOS.md` updated, (d) a commit in the project's `<type>(<scope>): ...` format.
7. **codebase-memory-mcp first, Read second.** When navigating existing code, use `search_graph`, `trace_path`, `get_code_snippet` before opening source files. This is repo protocol (`CLAUDE.md` Step 1). Re-index after adding new packages.

---

## Phase Overview

| Phase | Window | Focus | Gate to next phase |
|---|---|---|---|
| **Phase 0** | Now — ~Mar 2027 | Foundation hardening + first paper strategy live | Paper trade (CSP) running ≥ 6 full cycles (~6 months), trades ledger stable through one Finideas roll |
| **Phase 1** | Aug 2026 — Dec 2026 | Backtest engine + data pipeline + CSP backtest calibrated to paper | CSP backtest distribution matches paper realised within ±1.5 SD |
| **Phase 2** | Jan 2027 — Jun 2027 | CSP goes live (1 lot) + add strategy #2 (iron condor) to the pipeline | CSP live ≥3 months within backtest envelope, IC paper-trading started |
| **Phase 3** | Jul 2027 — 2028 | IC live + strategy #3 (event-driven) + portfolio-level construction | 3 strategies live, ≥6 months each within envelope, regime classifier operational |
| **Phase 4** | 2028 — 2030 | Finideas evaluation, basket maturity, optional ML overlays | Basket of 3–5 validated strategies, explicit Finideas keep/exit decision made |

**Current phase:** Phase 0

---

## How Cowork Should Work Through This File

1. Read this file in full before starting. Do not skip-ahead to `BACKTEST_PLAN_PHASE1.md`.
2. At the start of a session, scan for the first unchecked `[ ]` task in Phase 0 below.
3. Before writing any code: confirm scope, state plan (1-sentence + files touched), wait for go-ahead if >2 files.
4. After completing a task: tick `[x]`, note commit SHA in Completion Log, update `CONTEXT.md` / `TODOS.md`, commit.
5. Strategy/research tasks (marked `STRATEGY`) are not for Cowork — surface to Animesh.
6. Gate tasks (marked `GATE`) require human sign-off before the phase advances.

---

# Phase 0 — Foundation Hardening & First Paper Strategy

**Objective:** Get the first paper trade live, validate the operational stack through one real Finideas roll, and build the Phase 0 data infrastructure (risk module, VIX ingestion, delta tracker).

---

## 0.3 — CODE — June 2026 Finideas roll cycle

**Hard deadline: 2026-06-30** (NIFTY_JUN 23000 CE and PE legs expire, per `REFERENCES.md`).

- [ ] Invoke `roll-validator` agent ≥1 week before 2026-06-30 (per `.claude/agents/roll-validator.md`) to pre-check position state, Trade model integrity, and DB atomicity.
- [ ] Receive Finideas roll instructions (strike, expiry, quantity for each leg).
- [ ] Run `python -m scripts.roll_leg --dry-run ...` with all four `--old-*/--new-*` flags filled. Verify output.
- [ ] Run without `--dry-run`. Verify both Trade rows inserted atomically.
- [ ] Run `python -m scripts.daily_snapshot` same day. Confirm P&L continues uninterrupted; new JUL/SEP leg prices reflected in mark-to-market.
- [ ] Session log entry in `TODOS.md` with date, old/new instrument keys, and any anomalies observed.
- [ ] If any bug surfaces: file a separate fix commit before moving on.

---

## 0.4b — STRATEGY — 3-track Nifty long instrument comparison specification

**Owner: Animesh. Not for Cowork. Blocks task 0.6b.**

- [x] Write `docs/strategies/nifty_track_comparison_v1.md` covering:
  - Spot (NiftyBees ETF), Futures (Nifty Futures, monthly roll), Proxy (Deep ITM Call, delta ≈ 0.90)
  - Capital normalization: Notional Equivalent Exposure (NEE) — all tracks sized to 1 Nifty lot equivalent
  - Blocked combinations (must list explicitly): Futures + Covered Call (standalone)
  - Daily P&L report schema: base P&L + per-overlay P&L + net combined, per track; daily Delta/Theta/Vega
  - Strategy namespaces: `paper_nifty_spot`, `paper_nifty_futures`, `paper_nifty_proxy`
  - Roll mechanics: monthly roll for all tracks; Proxy kill criterion (delta < 0.40 for 3 consecutive days)
  - Minimum duration: 6 monthly cycles per track
- [x] Spec passes `validate_strategy_spec.py`.
- [x] Commit: `docs(strategies): add 3-track Nifty instrument comparison spec v1`. <!-- SHA: see below -->

**Source:** `docs/council/2026-05-02_nifty-long-instrument-comparison-protection.md` Stage 3.

---

## 0.6 — STRATEGY — Start paper trading CSP v1

**Owner: Animesh. Not for Cowork.**

- [ ] Each month at entry date: observe live option chain, decide strike (22-delta target per `csp_nifty_v1.md`). Log via `record_paper_trade.py` with mid price − 0.25 INR slippage haircut.
- [ ] Exit triggers: monitor daily via `daily_snapshot.py`. When profit target / time stop / loss stop hits, log exit.
- [ ] Never override the spec in real time. If urge to override: log it in `TODOS.md` with reason, then follow spec anyway.
- [ ] Minimum: **6 full monthly cycles (~6 months)**, with at least one cycle triggering each of: profit target, time stop, delta-stop (R2).

---

## 0.6a — STRATEGY — Start paper trading NiftyShield integrated v1

**Owner: Animesh. Not for Cowork.**

- [ ] Each month at Leg 1 (CSP) entry: also enter Leg 2 (put spread, 4 lots) via `record_paper_trade.py --strategy paper_niftyshield_v1`.
- [ ] Each quarter (Jan/Apr/Jul/Oct): enter Leg 3 (tail puts, 2 lots).
- [ ] Record real bid/ask and delta for protective strikes — critical for Phase 1 synthetic pricing calibration.
- [ ] Leg 2 enters even when Leg 1 is skipped (R3/R4 filters) — protection is unconditional.
- [ ] Minimum: 6 monthly cycles for Legs 1+2; 2 quarterly cycles for Leg 3.

---

## 0.6b — STRATEGY — Start paper trading 3-track Nifty instrument comparison

**Owner: Animesh. Not for Cowork. Blocked by: 0.4b (spec must exist and pass validator first).**

- [ ] Enter Spot base leg (long NiftyBees) via `record_paper_trade.py --strategy paper_nifty_spot --leg base_etf`.
- [ ] Enter Futures base leg (long Nifty Futures notional) via `--strategy paper_nifty_futures --leg base_futures`.
- [ ] Enter Proxy base leg (Deep ITM Call, delta ≈ 0.90) via `--strategy paper_nifty_proxy --leg base_ditm_call`.
- [ ] For each approved overlay per track, record as a separate leg within the same strategy namespace.
- [ ] Do NOT record Futures + standalone Covered Call — blocked per council ruling.
- [ ] On each expiry: roll all base legs; document delta at roll time for Proxy.
- [ ] Minimum 6 monthly cycles before cross-track conclusions. Include ≥1 high-VIX event (India VIX >18).

---

## 0.6c — CODE — PortfolioDeltaTracker

**Owner: Cowork. Source: `docs/council/2026-05-02_multi-strategy-portfolio-risk-allocation.md` §7.3.**

- [ ] `src/risk/__init__.py` — package stub.
- [ ] `src/risk/models.py` — `PortfolioDelta` frozen dataclass: `options_delta_lots: Decimal`, `niftybees_delta_lots: Decimal`, `total_delta_lots: Decimal`, `warning_breached: bool`, `cap_breached: bool`, `as_of: datetime`.
- [ ] `src/risk/delta_tracker.py` — `PortfolioDeltaTracker`:
  - `aggregate_delta(paper_positions: list[PaperPosition], nifty_spot: Decimal, lot_size: int) → PortfolioDelta`
  - Options-only cap: +1.0 lots (warning +0.75). Options + NiftyBees cap: +2.0 lots (warning +1.5). Constants parameterised.
  - NiftyBees delta: `niftybees_qty × niftybees_ltp / (nifty_spot × lot_size)` (beta = 1.0).
- [ ] `src/risk/entry_gate.py` — `check_entry_allowed(current_delta: PortfolioDelta, trade_delta_lots: Decimal, is_protective: bool) → tuple[bool, str]`. Protective entries always `(True, "")`.
- [ ] Tests: `tests/unit/risk/test_delta_tracker.py` — happy path, warning boundary, hard cap breach, protective bypass, zero-position base case.
- [ ] `python -m pytest tests/unit/ --tb=no -q` green.
- [ ] Commit: `feat(risk): add PortfolioDeltaTracker with entry gate`.

---

## 0.8 — GATE — End of Phase 0

All of the following must be true before loading `BACKTEST_PLAN_PHASE1.md`.

> **Council decision 2026-05-02:** Gate criteria revised. Full rationale in `DECISIONS.md → Variance Gate` and `docs/plan/variance_gate.md`.

- [ ] Tasks 0.1, 0.2, 0.3, 0.5, 0.7 are all `[x]` (0.1, 0.2, 0.5, 0.7 already done — see archive).

**CSP v1 paper trading gate — all four criteria (A–D) must pass:**

- [ ] **(A) Minimum paper sample:** ≥6 executed paper CSP cycles **and** ≥9 calendar months of entry-decision observation (whichever comes later). Cycles skipped by R3/R4/event filters count as filter-validation observations.

- [ ] **(B) Exit-path validation:** Each exit mechanism validated at least once via live paper or deterministic historical replay:

  | Exit Type | Validation requirement |
  |---|---|
  | Profit target (50%) | Live paper preferred; replay acceptable |
  | Time stop (21-day) | Live paper preferred; replay acceptable |
  | Delta/mark stop | Live paper required before Tier 2 scaling; replay acceptable for Tier 1 pilot |

- [ ] **(C) Regime completeness (at least one of three):**

  | Regime Criterion | Definition |
  |---|---|
  | High IVR | ≥1 cycle with IVR > 50 at entry |
  | Drawdown stress | ≥1 holding window with ≥5% Nifty intraday peak-to-trough decline |
  | Delta pressure | ≥1 cycle where short-put delta reaches ≤ −0.35 before any exit fires |

- [ ] **(D) Regime-matched Z-score:** Paper vs backtest `|Z| ≤ 1.5` on **both** the full 8-year backtest distribution **and** a regime-matched subset. See `BACKTEST_PLAN_PHASE1.md` task 1.11.

- [ ] **Spec consistency resolved** before codifying gate: lot size (65 vs 50), time-stop definition, R-number naming, R4 trend filter. Gate references `docs/strategies/csp_nifty_v1.md` as sole canonical spec.

- [ ] `docs/strategies/csp_nifty_v1.md` exists and passes the validator (0.7).
- [ ] `docs/strategies/niftyshield_integrated_v1.md` exists and passes the validator (0.4a).
- [ ] NiftyShield integrated paper trading (0.6a) has ≥6 monthly cycles for Legs 1+2 and ≥2 quarterly cycles for Leg 3.
- [ ] Jun 2026 Finideas roll executed cleanly with no orphaned positions (0.3).
- [ ] Full test suite green; `CONTEXT.md` + `DECISIONS.md` + `TODOS.md` reflect Phase 0 end state.
- [ ] Animesh has reviewed paper trade results and confirms "ready to build the backtest engine" in a session log entry.

---

# Cross-Cutting Rules (apply to every phase)

## Code quality

- Every code task ends with: `python -m pytest tests/unit/` green + `code-reviewer` agent clean + `CONTEXT.md`/`DECISIONS.md`/`TODOS.md` updated + commit in `<type>(<scope>):` format.
- No `@staticmethod`, no vertical alignment, no `assert` in `src/`, no f-strings in logger calls, 80-char lines, intent comments on broad `except`.
- `Decimal` everywhere for money. Floats from APIs get `Decimal(str(x))` at the boundary.
- `codebase-memory-mcp` before `Read`. `git log` before asking "why does this code look like this?".

## Strategy discipline

- One new strategy per year, maximum.
- Do not scale a strategy for the first 3 months of live trading, regardless of profitability.
- Write kill criteria before going live, not after.
- Post-mortem every strategy that dies AND every strategy that graduates to live.

## Risk sizing

- Max deployed on any single strategy: 25% of total capital.
- Max deployed across all open positions: 50% of total capital.
- Max loss per trade: ≤ 2% of total capital.

## Variance monitoring thresholds

- Per-cycle CUSUM (lower-sided, k=0.50): `C_t ≥ 3.0` warning, `C_t ≥ 4.0` reduce, `C_t ≥ 5.0` halt. N-gated (see `DECISIONS.md → Live Strategy Monitoring`).
- Monthly Z-score logged as dashboard metric; not a halt trigger before N=24 live closed cycles.

## Kill triggers (global)

- Trailing 6-month realised return < 0% for that strategy.
- Max drawdown > 10% of deployed capital for that strategy.
- CUSUM `C_t ≥ 5.0` at any cycle close (active at N≥12).
- Three consecutive execution errors.

---

# Completion Log

*Append-only. Cowork: add one row per completed task with date, task ID, commit SHA.*

| Date | Task | Commit SHA | Notes |
|---|---|---|---|
| 2026-04-24 | 0.1 | cd3ed6b | 174 nuvama tests. Follow-up fix 92a6c74. |
| 2026-04-25 | 0.4 | fb69043 | CSP v1 spec: docs/strategies/csp_niftybees_v1.md. |
| 2026-04-25 | 0.5 | 5ccfc52 | Paper trading module src/paper/. 65 new tests, 948 total. |
| 2026-04-26 | 0.4a | 88dc95e | NiftyShield integrated spec: docs/strategies/niftyshield_integrated_v1.md. |

---

# Open Questions for Animesh

Unresolved decisions only. Cowork: do not guess — surface and wait.

- **Phase 2.2:** Is static IP provisioned by the time CSP is ready to go live? If not, plan for manual order placement + `record_trade.py` ledger capture.
- **Phase 4.1:** What's the acceptable "Finideas is worth its fee" spread vs benchmark?
- **Phase 3.2 vs Track A swing strategies — UNRESOLVED:** Calendar spread (§3.2 in Phase 1 plan) vs Track A graduates (Donchian, ORB, Gap Fade). Decision required before Phase 3 begins: does the calendar spread replace a failing swing strategy, or become a fourth strategy (triggering the one-per-year rule)?
- **Phase 1.6a open question:** Should `bhavcopy_ingest.py` (task 1.3) also parse `FUTIDX NIFTY` rows, or should task 1.6a derive futures prices at query time? Resolve before starting 1.6a implementation.

# NiftyShield — Backtest → Paper → Live Pipeline Plan

> **Purpose:** A phased build plan for NiftyShield's backtesting engine, paper trading simulator, and forward validation loop. The end state is a basket of 3–5 validated options strategies running live, with continuous variance monitoring against backtest and paper simulations.
>
> **Time horizon:** 4–5 years.
>
> **For Cowork / Claude Code agents:** This file is a live planning document. Work through phases in order. Each task has a state checkbox — tick only when the Definition of Done (DoD) is fully met, tests are green, and the commit has landed. Do not skip gates between phases.
>
> **For the human operator (Animesh):** This file separates **code work** (agent-executable) from **strategy/research work** (owner-executable). Code tasks can be delegated to Cowork. Strategy tasks require your judgment and live observation — do not delegate them.

---

## Rendering Instructions (for AI assistants reading this file)

**When presenting this plan to Animesh, always render it as an interactive card-format HTML widget using `mcp__visualize__show_widget`.** Do not dump the raw markdown — the card view is the canonical display format.

Card format rules:
- **Phase header:** coloured badge pill (Phase 0 = green, Phase 1 = blue, Phase 2 = purple) + one-line description
- **Section groupings** inside each phase: `THIS WEEK — UNBLOCKED`, `DONE ✓`, `ONGOING`, `NEXT SPRINT`, `HARD DEADLINE`, `DECISION`, `GATE`
- **Task card fields:** task number (grey), title (bold), description (2–3 lines), time estimate badge (green ≤1d / orange 1–3d / red urgent / blue ongoing), owner badge (Cowork / Animesh / Both), italic "Blocked by:" line when relevant
- **Left border colour:** orange = Code (Cowork), purple = Strategy (Animesh), red = Operational, grey = Housekeeping/Decision, green = Done (strikethrough title + 60% opacity)
- **Gate row:** dashed purple border, lock icon 🔒, gate conditions as subtitle text
- **Completed phases/tasks:** dimmed at 75% opacity with `[x]` state reflected
- **SHA warning banner:** if completion log has "pending" SHAs, show a yellow ⚠ banner at top

Source of truth for current `[x]`/`[ ]` state: the checkboxes in this file. Reflect the actual checkbox state in the widget — do not guess or use session memory.
>
> **Related files:**
> `CONTEXT.md` (current state) · `DECISIONS.md` (architecture rationale) · `REFERENCES.md` (instrument keys, AMFI codes) · `TODOS.md` (open work + session log) · `PLANNER.md` (multi-sprint roadmap) · `REVIEW.md` (code review checklist)

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

1. Read this file in full before starting. Do not skip-ahead to a later phase.
2. At the start of a session, scan for the first unchecked `[ ]` task in the current phase.
3. Before writing any code: confirm scope with the human, state the plan (1-sentence + files touched), wait for go-ahead if >2 files (per `CLAUDE.md` Step 3).
4. After completing a task: tick the `[x]` checkbox, note the commit SHA in the **Completion Log** at the bottom, update `CONTEXT.md` / `TODOS.md`, commit.
5. Strategy/research tasks (marked `STRATEGY`) are **not** for the agent — skip them and surface to the human.
6. Gate tasks (marked `GATE`) require human sign-off before the phase advances.

---

# Phase 0 — Foundation Hardening & First Paper Strategy

**Objective:** Finish in-flight work on the trades ledger, complete one real roll cycle end-to-end, and start paper trading a strategy you will eventually run live.

**Duration target:** ~10–12 weeks from plan activation.

**Why this phase first:** You are about to subscribe to a ₹400/month data feed and build a backtest engine. Both become useful only when (a) the trades ledger can reliably record realised P&L from the live system, and (b) you have a strategy of your own whose mechanics you understand, so the backtest has something concrete to calibrate against.

---

## 0.1 — CODE — Tests for Nuvama options + intraday (protocol debt)

Close the test gap from `TODOS.md` item 0. These features were built without tests and violate the repo's "every public function needs happy-path + edge-case test" contract.

- [x] Add `tests/unit/nuvama/test_models.py` coverage for `NuvamaOptionPosition`, `NuvamaOptionsSummary.net_pnl` (unrealized + cumulative_realized) — frozen, construction validation, property math.
- [x] Add `tests/unit/nuvama/test_options_reader.py` — `parse_options_positions()` happy path (OPTIDX + OPTSTK), skips non-option rows, handles flat positions (net_qty=0), missing `resp.data.pos`, malformed records. `build_options_summary()` aggregation + empty-list edge case.
- [x] Extend `tests/unit/nuvama/test_store.py` — `record_options_snapshot` upsert + idempotency, `get_cumulative_realized_pnl` cross-symbol SUM, `record_intraday_positions` purge-on-call, `get_intraday_extremes` max/min/nifty aggregation, empty-date `(None, None, None, None)`.
- [x] Full suite green: `python -m pytest tests/unit/`.
- [x] `code-reviewer` agent clean on diff.
- [x] Commit: `test(nuvama): add coverage for options + intraday`.

**Why now:** This is tech debt that blocks confident refactors later. Every subsequent phase touches `nuvama/` indirectly; untested methods will break silently.

---

## 0.2 — CODE — Greeks capture (`OptionChain` model + `_extract_greeks_from_chain`)

Carried over from `TODOS.md` item 1 and `PLANNER.md` Current Sprint. Required before any options strategy can be backtested or paper-traded with proper delta/vega tracking.

- [x] Define `OptionChain` Pydantic model in `src/models/options.py`. Includes per-strike CE/PE with `ltp`, `bid`, `ask`, `oi`, `delta`, `gamma`, `theta`, `vega`, `iv`.
- [x] **Source-agnostic shape:** Field names are vendor-neutral (`delta`, not `greeks_delta`). Upstox → OptionLeg translation in `src/client/upstox_market.py`. Dhan parser deferred to Phase 1.10.
- [x] Fixed option chain API call in `_fetch_greeks` — uses `NSE_INDEX|Nifty 50` as underlying key.
- [x] Implemented `_extract_greeks_from_chain()` as module-level private function in `tracker.py`. Pure function, fixture-tested.
- [x] Greeks columns in `daily_snapshots` will populate from 2026-04-25 onwards.
- [x] 16 fixture-driven offline tests in `tests/unit/test_greeks_capture.py`. All green.
- [x] Commit: `feat(models): add source-agnostic OptionChain model + Upstox Greeks capture`.

**Why now:** CSP paper trading (0.6) uses the live option chain to pick strikes and log decisions. The existing Upstox client serves this for Phase 0. The `OptionChain` model built here is the foundation both for Phase 0 paper trading and for Phase 1.10's Dhan-backed production path.

---

## 0.3 — CODE — June 2026 Finideas roll cycle

**Hard deadline: 2026-06-30** (NIFTY_JUN 23000 CE and PE legs expire, per `REFERENCES.md`).

This is the first real operational test of `scripts/roll_leg.py` in production. Finideas will issue roll instructions; the system must execute them cleanly with no missed rolls, no orphaned positions, and a clean audit trail.

- [ ] Invoke `roll-validator` agent ≥1 week before 2026-06-30 (per `.claude/agents/roll-validator.md`) to pre-check position state, Trade model integrity, and DB atomicity.
- [ ] Receive Finideas roll instructions (strike, expiry, quantity for each leg).
- [ ] Run `python -m scripts.roll_leg --dry-run ...` with all four `--old-*/--new-*` flags filled. Verify output.
- [ ] Run without `--dry-run`. Verify both Trade rows inserted atomically.
- [ ] Run `python -m scripts.daily_snapshot` same day. Confirm P&L continues uninterrupted; new JUL/SEP leg prices reflected in mark-to-market.
- [ ] Session log entry in `TODOS.md` with date, old/new instrument keys, and any anomalies observed.
- [ ] If any bug surfaces: file a separate fix commit before moving on. Do not let roll bugs sit.

**Why it matters:** If `roll_leg.py` has a latent bug, you find out now on Finideas' schedule, not during a self-initiated roll of your own strategy later.

---

## 0.4 — STRATEGY — Choose the first paper-trade strategy

**Owner: Animesh. Not for Cowork.**

Decide the exact specification of the first strategy to paper-trade. The recommendation from conversation is **monthly cash-secured put (CSP) on NiftyBees at 25-delta, 30–45 DTE entry, exit at 50% profit OR 21 DTE OR 2× credit loss, no adjustments, one lot**. But the spec is yours to finalise.

- [x] Write `docs/strategies/csp_niftybees_v1.md` — the Strategy Specification Document. Sections required:
  - **Name, version, author, date**
  - **Entry rule** (what, when, at what strike/delta, how much capital)
  - **Exit rule** (profit target, time stop, loss stop — exact numbers)
  - **Adjustment rule** (must explicitly state "none" if none)
  - **Position sizing** (e.g., 1 lot, cap of ₹X at risk)
  - **Expected P&L distribution prior** (your best guess: win rate, avg win, avg loss — these are hypotheses to validate)
  - **Regimes you expect it to work in / fail in**
  - **Kill criteria** (conditions under which you stop running it — trailing 6-month return, max drawdown, variance from backtest, execution error count)
  - **Variance threshold for live deployment** (e.g., realised mean within ±1.5 SD of backtest mean over ≥4 months of paper trading)
- [x] Commit: `docs(strategies): add CSP v1 specification`.
- [x] **2026-04-25 review:** underlying switched from NiftyBees to Nifty 50 index options.
  `docs/strategies/csp_nifty_v1.md` created as successor; `csp_niftybees_v1.md` retained as
  DEPRECATED. Rules R1–R7 revised. See `DECISIONS.md` → Strategy Decisions.

**Why this artifact matters:** The spec is the contract between your intentions and your code. When paper-trade results diverge from expectations, you compare to the spec, not to a moving target. Without this, strategies mutate silently as you "improve" them and you lose the ability to measure anything consistently.

---

## 0.5 — CODE — Paper trading module (`src/paper/`) — DONE 2026-04-25

New module to record paper trades, mark-to-market daily, compute realised P&L. Reuses existing `Trade` model and `PortfolioStore` patterns — no parallel infrastructure.

- [x] Create `src/paper/` package with `__init__.py`. Re-index `codebase-memory-mcp` after.
- [x] `src/paper/CLAUDE.md` — module invariants (paper trades never touch live `trades` table; `strategy_name` prefix `paper_` by convention; no broker calls).
- [x] `src/paper/models.py` — `PaperTrade` (frozen, mirrors `Trade` model but with explicit `is_paper: Literal[True]` field and `strategy_name` constrained to start with `paper_`), `PaperPosition` (derived, frozen, includes `avg_sell_price` for short positions), `PaperNavSnapshot` (frozen dataclass).
- [x] `src/paper/store.py` — `PaperStore` with `paper_trades` and `paper_nav_snapshots` tables in shared `portfolio.sqlite`. UNIQUE constraint `(strategy_name, leg_role, trade_date, action)` for idempotency. Decimal-as-TEXT invariant preserved.
- [x] `src/paper/tracker.py` — `PaperTracker` that mirrors `PortfolioTracker`'s shape: `compute_pnl()`, `record_daily_snapshot()`, `record_all_strategies()`. Consumes `BrokerClient` protocol for LTP. Correct short P&L via `avg_sell_price`.
- [x] `scripts/record_paper_trade.py` — CLI mirroring `record_trade.py`, but writes to `paper_trades`. Enforces `strategy_name` starts with `paper_`.
- [x] Tests: 65 tests across 4 test files (20 models, 24 store, 18 tracker, 9 CLI). 948 total passing.
- [x] Paper trading runs standalone — not wired into `daily_snapshot.py`. Use `scripts/record_paper_trade.py` to log trades and `scripts/paper_snapshot.py` (future) or a direct `PaperTracker` call to mark-to-market. Keeps the live EOD run free of paper simulation concerns.
- [x] `code-reviewer` agent on diff — 1 CRITICAL (intent comment on broad except, fixed), WARNINGs addressed (enum comparison, redundant Decimal(str()), sorted set iteration).
- [x] Commit sequence: models → store → tracker → CLI → snapshot wiring → docs.

**Design decision to record in `DECISIONS.md`:** "Paper trades stored in same SQLite DB as live trades but in separate tables with `paper_` prefix on strategy names. Rationale: reuse of store, tracker, snapshot, and Telegram infrastructure with zero parallel code; prefix convention prevents accidental cross-contamination at query time."

---

## 0.6 — STRATEGY — Start paper trading CSP v1

**Owner: Animesh. Not for Cowork.**

Begin paper trading the strategy specified in 0.4. The mechanics:

- [ ] Each month, at the entry date specified in the spec, observe the live option chain and decide the strike. Log the decision via `record_paper_trade.py` with entry price = mid of bid/ask at decision time.
- [ ] Apply a slippage haircut on entry: assume you got filled 0.25 INR worse than mid. Record this in the notes field.
- [ ] Exit triggers: monitor daily via `daily_snapshot.py` output. When profit target / time stop / loss stop hits, log the exit trade.
- [ ] Never override the spec in real time. If you feel the urge to override, log it in `TODOS.md` with the reason — this is valuable data about your own discipline. Then follow the spec anyway.
- [ ] Minimum paper-trade duration before moving to Phase 1 live deployment: **6 full monthly
  expiry cycles (approximately 6 months)**, with at least one cycle that triggers each of:
  profit target, time stop, delta-stop (R2). All three exit mechanisms must be exercised at
  least once before the variance gate is credible.

**Why 6 cycles minimum:** 2 cycles is 2 data points — noise, not signal. You need enough
cycles to see the exit-type distribution (profit target vs time stop vs delta-stop) and
compare it against the backtest frequency of each. Six cycles is a coarse but credible
distribution; prefer 8+ if calendar permits before committing capital. The "8 weeks / 2
cycles" floor from the initial draft was statistically too thin.

---

## 0.7 — CODE — Strategy specification validator (lightweight)

Small tool to enforce that every strategy spec has the required sections. Prevents spec rot over years.

- [x] `scripts/validate_strategy_spec.py` — reads `docs/strategies/*.md`, checks for presence of required section headers (Name, Entry, Exit, Adjustment, Sizing, Kill Criteria, Variance Threshold). Returns non-zero exit on missing sections.
- [x] Tests: happy path + each missing-section case. 28 tests in `tests/unit/test_validate_strategy_spec.py` — parametrised per required section, deprecated detection, non-spec skip, directory scan, explicit file path. All green.
- [x] Add to a pre-commit hook or CI step (deferred until CI exists; for now, manual run).
- [x] Commit: `feat(scripts): strategy spec validator`.

---

## 0.4a — STRATEGY — NiftyShield Integrated Strategy Specification

**Owner: Animesh. Not for Cowork.**

Companion to 0.4 (CSP v1). Integrates the CSP income engine with layered MF
portfolio protection (protective put spreads + quarterly tail puts). Addresses the
FinRakshak coverage gap (~15% of ₹80L+ MF portfolio hedged).

- [x] Write `docs/strategies/niftyshield_integrated_v1.md` — full strategy spec with
  all required sections. CSP leg references `csp_nifty_v1.md` by inclusion; protective
  legs (put spread + tail puts) specified in full.
- [x] Spec passes strategy-spec validator (0.7).
- [x] Commit: `docs(strategies): add NiftyShield integrated v1 specification`.

**Why a separate spec (not just extending CSP v1):** The protection legs have different
entry schedules (Leg 2 monthly, Leg 3 quarterly), different exit rules (hold to expiry
vs CSP's three triggers), different kill criteria, and require a different backtest
methodology (synthetic pricing vs real market data). Bundling them into `csp_nifty_v1.md`
would produce an incoherent spec. The CSP rules are included by reference; the protective
rules stand independently.

---

## 0.6a — STRATEGY — Start paper trading NiftyShield integrated v1

**Owner: Animesh. Not for Cowork.**

Begin paper trading the protective legs alongside CSP v1:

- [ ] Each month, at Leg 1 (CSP) entry time, also enter Leg 2 (put spread, 4 lots)
  via `record_paper_trade.py` with `--strategy paper_niftyshield_v1`.
- [ ] Each quarter (Jan/Apr/Jul/Oct), enter Leg 3 (tail puts, 2 lots) via
  `record_paper_trade.py`.
- [ ] Record real bid/ask and delta for protective strikes — this data is critical for
  calibrating the Phase 1 synthetic pricing model.
- [ ] Minimum duration: 6 monthly cycles for Legs 1+2; 2 quarterly cycles for Leg 3.
- [ ] Leg 2 enters even when Leg 1 is skipped (R3/R4 filters) — protection is
  unconditional.
- [ ] Track NiftyBees accumulation: in surplus months, record intended NiftyBees BUY
  under `paper_niftyshield_v1 / accumulated_niftybees`.

---

## 0.8 — GATE — End of Phase 0

All of the following must be true before starting Phase 1. Do not start Phase 1 tasks until this gate is ticked.

- [ ] 0.1, 0.2, 0.3, 0.5, 0.7 are all `[x]`.
- [ ] CSP v1 paper trading has ≥ 6 full monthly expiry cycles, with at least one each of:
  profit-target exit, time-stop exit, delta-stop exit (0.6).
- [ ] `docs/strategies/csp_nifty_v1.md` exists and passes the validator (0.7).
  (`csp_niftybees_v1.md` retained as DEPRECATED — not required to pass validator.)
- [ ] `docs/strategies/niftyshield_integrated_v1.md` exists and passes the validator (0.4a).
- [ ] NiftyShield integrated paper trading (0.6a) has ≥ 6 monthly cycles for Legs 1+2
  and ≥ 2 quarterly cycles for Leg 3.
- [ ] Jun 2026 Finideas roll executed cleanly with no orphaned positions (0.3).
- [ ] Full test suite green; `CONTEXT.md` + `DECISIONS.md` + `TODOS.md` reflect Phase 0 end state.
- [ ] Animesh has reviewed paper trade results and confirms "ready to build the backtest engine" in a session log entry.

---

# Phase 1 — Backtest Engine & Data Pipeline

**Objective:** Build the backtest engine, ingest historical options data via DhanHQ, and validate the engine against the CSP paper-trade data from Phase 0. End state: you can run the CSP strategy across 2020–2026 history with realistic costs, and the backtest distribution matches the paper-trade distribution within ±1.5 SD.

**Duration target:** ~4–5 months.

**Why this order (backtest after paper, not before):** Covered in conversation. A backtest whose output can't be validated against a known realised outcome is a simulation, not a measurement. Phase 0 gives us that known outcome.

> **Task numbering note:** Tasks run 1.1 → 1.6 → 1.6a → 1.7 → 1.8 → 1.10 → 1.11 → 1.12. The 1.9 slot was reserved during an earlier draft and merged into the 1.11 variance check after the Dhan live chain decision (2026-04-17). The gap is intentional; do not renumber.

---

## 1.1 — STRATEGY — DhanHQ Data API subscription

**Owner: Animesh.**

Confirmed from Dhan docs (`https://dhanhq.co/docs/v2/expired-options-data/`, verified 2026-04-17):

- **History depth:** 5 years, rolling. Index options and stock options both covered. Covers 2021 onwards — includes Russia/Ukraine (Feb 2022), rate-hike vol (Oct 2022), SVB (Mar 2023), Israel (Oct 2023), election day (Jun 2024), Hindenburg/Adani (Oct 2024). **Does NOT cover COVID crash (Mar 2020)** — worst stress scenario available is Jun 2024 election day. Acknowledge this as a known limitation of the stress-test methodology.
- **Resolution:** 1-minute.
- **Strike coverage (asymmetric — important):** "ATM±10 for index options nearing expiry, ATM±3 for all other contracts." The cutoff for "nearing expiry" is NOT documented — must be verified before ingesting. A 30–45 DTE iron condor at 15-delta typically lives at ATM±5 to ATM±8, which could fall outside ATM±3 coverage if "nearing expiry" means <14 DTE or <7 DTE.
- **Query shape:** Strike parameter is ATM-relative (`ATM`, `ATM+3`, `ATM-7`), not absolute. Payload includes `expiryFlag` (`WEEK`/`MONTH`), `expiryCode` (expiry index), `drvOptionType` (`CALL`/`PUT`), `requiredData` array.
- **`requiredData` fields offered:** `open, high, low, close, iv, volume, strike, oi, spot`. **No delta, gamma, theta, vega.** Greeks must be computed locally (see 1.6a).
- **API rate limit:** 1 request per second (per the Market Quote page; rollingoption doesn't document a separate limit — assume same).
- **Per-call window:** Max 30 days of data. Full backfill requires ~60 calls per (strike, option_type) combination.

**Tasks:**

- [ ] Before subscribing, ask Dhan support (or test with one trial call): what does "nearing expiry" mean for the ATM±10 strike window? <14 DTE? <30 DTE? Record answer in `DECISIONS.md`. If the window is <7 DTE only, iron condor backtests at 30–45 DTE entry are impossible and the strategy pipeline must adapt (move to weekly IC with <7 DTE entry, or use ATM±3-compatible structures like bull/bear put spreads at 3-strikes-OTM).
- [ ] Subscribe to DhanHQ Data API (₹400/month per `DECISIONS.md` Dhan Integration).
- [ ] Store `DHAN_DATA_TOKEN` in `.env` (or confirm existing `DHAN_ACCESS_TOKEN` suffices — tier-dependent; verify via one test call).
- [ ] Record confirmed facts in `DECISIONS.md` → "Dhan Integration" section: 5-year history, 1-min resolution, ATM±10/±3 split, no Greeks in payload, 1 req/sec, 30-day window, confirmed "nearing expiry" definition.

**Stop signal:** If the "nearing expiry" definition restricts ATM±10 to <7 DTE only, the
Phase 2 iron condor strategy needs a redesign before Phase 1 starts. CSP at 25-delta
typically lands at ATM-3 or ATM-4 on Nifty — inside the always-available ATM±3 window —
so CSP backtesting is unaffected.

**Caveat on bid/ask history:** Dhan expired-options data (`rollingoption`) does not include
bid/ask spread history — only OHLCV + IV + OI. The backtest fills at OHLC midpoint and
applies the R7 slippage model (`max(₹0.25, 0.5 × spread)` at entry/target; 1.5× at
loss-stop). Realistic spread calibration — particularly the stressed-exit multiplier — is
deferred to the paper phase, where actual Dhan live-chain bid/ask snapshots will be captured
(task 1.10).

**India VIX ingestion requirement (Phase 1 prerequisite for R3 filter):** The CSP v1 R3
rule requires a trailing 252-day IVR computed from India VIX OHLC history. No India VIX
data currently exists in the repo (confirmed by grep 2026-04-25). Before R3 can be applied
in backtesting, a separate ingestion sub-task is needed: fetch India VIX OHLC history from
NSE or Upstox, store alongside `underlying_ohlc` in Timescale (see task 1.3), and expose it
to `CSPConfig`. Until this pipeline exists, V1/V2/V3 backtest runs proceed without the IVR
entry filter — the backtest will be slightly more permissive than the live spec. Document
this gap in the V1 backtest result notes.

---

## 1.2 — CODE — TimescaleDB container

Historical options data in SQLite does not scale. `DECISIONS.md` already commits to PostgreSQL + TimescaleDB for this data.

- [ ] Add `docker-compose.yml` at repo root with a `timescale` service. Pin version. Expose 5432 on localhost only. Persistent volume `data/timescale/` (gitignored).
- [ ] Document startup in `README.md`: `docker compose up -d timescale`.
- [ ] Add `TIMESCALE_DSN` to `.env.example`.
- [ ] Create `src/db_timescale.py` — connection context manager, sibling to existing `src/db.py`. Uses `psycopg` (v3, not psycopg2). No ORM.
- [ ] Smoke test script `scripts/timescale_health.py` — connects, runs `SELECT 1`, prints version. Not committed to tests (requires running container); runs manually.
- [ ] Commit: `chore(infra): add TimescaleDB container + connection layer`.

**Explicitly out of scope for this task:** SQLAlchemy, migrations framework, ORM models. Keep the raw-SQL posture consistent with existing SQLite code.

---

## 1.3 — CODE — Options OHLC schema + ingestion

- [ ] Timescale schema (raw SQL in `src/backtest/schema.sql`):
  - `options_ohlc` hypertable: `(underlying TEXT, expiry_flag TEXT, expiry_code INT, expiry_date DATE, atm_offset INT, option_type CHAR(2), timestamp TIMESTAMPTZ, open NUMERIC, high NUMERIC, low NUMERIC, close NUMERIC, iv NUMERIC, volume BIGINT, oi BIGINT, spot NUMERIC, strike NUMERIC)`. Primary key `(underlying, expiry_flag, expiry_code, atm_offset, option_type, timestamp)`. Hypertable on `timestamp`, chunk interval 7 days.
  - Index on `(underlying, expiry_flag, expiry_code, timestamp)` for strategy-side queries.
  - Rationale for schema shape: Dhan's API is ATM-relative (`ATM+3` not `22500CE`). Storing `atm_offset` + `spot` + `strike` lets you reconstruct absolute strikes for reporting while keeping the primary access pattern (ATM-relative lookup) a single index read.
- [ ] `src/backtest/dhan_ingest.py`:
  - Pydantic model for the `rollingoption` response shape (nested `data.ce`/`data.pe` with parallel arrays `open/high/low/close/iv/volume/oi/strike/spot/timestamp`).
  - Mapper `response_to_bars()` — zips the parallel arrays into `OptionsBar` records, one per (timestamp, option_type).
  - Handles `pe: null` / `ce: null` gracefully (empty side, not error).
  - Batched insert into Timescale via `ON CONFLICT DO NOTHING`.
- [ ] `src/backtest/rate_limiter.py` — token bucket at 1 req/sec (per Dhan docs). Async-safe. Reusable for live Dhan calls later.
- [ ] CLI `scripts/backtest_ingest.py`:
  - Args: `--underlying NIFTY --start 2021-08-01 --end 2026-06-30 --strikes "ATM-10:ATM+10" --expiry-flag MONTH --resolution 1`.
  - Iterates (expiry, strike, option_type, 30-day-window) and calls the API. ~60 calls per (strike, option_type) × 21 strikes × 2 types = ~2,500 calls per full backfill. At 1 req/sec that's ~45 minutes of runtime.
  - **Resumable:** before each call, check if the (underlying, expiry_code, atm_offset, option_type, date-range) is already fully populated in Timescale. Skip if yes. Required because the ingestion will be killed and restarted repeatedly during development.
  - Progress logging: emit `ingested %d bars for %s %s ATM%+d %s [%d/%d]` every call.
  - Graceful handling of empty responses (expired strike outside ATM±10 window, for instance) — log INFO, continue.
- [ ] Tests: response → bar mapping (happy path + `pe: null`), idempotency on re-ingest, rate limiter, resumability check (skip when range already covered).
- [ ] Commit sequence: schema → ingest module → rate limiter → CLI → tests.

**Why daily resolution is not the first target anymore:** Dhan returns 1-minute only. We aggregate to daily at query time, not ingest time. ~390 rows per trading day per strike × 21 strikes × 2 types × 60 expiries × 5 years = ~500M rows in Timescale. Compressible to ~15–30 GB on disk with Timescale's native compression. Acceptable.

**Note on the historical data endpoint:** Dhan also offers `/v2/charts/historical` for underlying OHLC, but see task 1.3a below — underlying OHLC (Nifty 50, India VIX, NiftyBees) is ingested via Upstox `/v2/historical-candle/` instead, at zero additional cost. Do not bundle with Dhan options ingestion — different APIs, different rate-limit budgets, different failure modes.

---

## 1.3a — CODE — Underlying OHLC ingest (Nifty 50, India VIX, NiftyBees)

**Data cost: FREE — uses existing `UPSTOX_ANALYTICS_TOKEN`. No DhanHQ subscription required.**

This is the zero-cost data foundation for two downstream research pipelines that run after Phase 1.12:
- **Swing strategy Tier 1** (points-based backtesting, Phase 2 Track A) — uses Nifty 50 daily + 15-min OHLC and India VIX. Zero paid data required for Tier 1. Only swing Tier 2 (option spread P&L) needs DhanHQ.
- **Investment strategy backtesting** (Phase 2 Track B, all stages) — uses Nifty 50 daily + NiftyBees daily. Entirely free throughout.

Also provides the India VIX series required by the CSP R3 IVR filter (tasks 1.7 / 1.8) — no other source currently exists in the repo.

- [ ] Ingest from Upstox `/v2/historical-candle/{instrument_key}/{interval}`:
  - `NSE_INDEX|Nifty 50` — daily candles, full available history (≥5 years)
  - `NSE_INDEX|Nifty 50` — 15-min candles, full available history (≥5 years)
  - `NSE_INDEX|India VIX` — daily candles, full available history (≥5 years)
  - `NSE_EQ|INF204KB14I2` (NiftyBees) — daily candles, full available history
- [ ] Storage: Parquet, partitioned by `instrument + date`. Follow `CONTEXT.md` data layer convention. Directory: `data/historical/ohlc/`.
- [ ] `src/backtest/ohlc_ingest.py` — async fetcher; resumable (check existing Parquet files before each request, skip if range present); rate-limited to Upstox historical-candle budget (separate from DhanHQ `rollingoption` budget).
- [ ] Derived fields computed and stored alongside raw OHLC: 14-day ATR, 20-day ATR, 50-day linear regression slope (swing regime engine), 10-month SMA (investment SMA filter), 252-day VIX percentile rank (IVR/IVP for CSP R3 + swing filters).
- [ ] Tests: fixture-driven, resumability check (skip if Parquet range already present), ATR computation unit test, VIX percentile rank boundary test.
- [ ] Commit: `feat(backtest): Upstox OHLC ingest for Nifty/VIX/NiftyBees`.

**Gate:** Nifty 50 daily close must match NSE published values within ±0.05% for 95% of days over full history. India VIX series must have <1% missing trading days (fill with previous close for holidays; flag and investigate gaps >1 trading day). NiftyBees NAV tracks Nifty 50 within ±0.5% tracking error over any rolling 1-year period.

---

## 1.4 — CODE — Port quant-4pc backtest engine

Per `PLANNER.md` → "quant-4pc-local Reference", the engine is already designed. Port, don't rebuild.

- [ ] `src/backtest/engine.py` — port `BacktestEngine`, `Strategy` Protocol (`setup / on_day / teardown`), `DayContext`, `BacktestResult`. Adapt data loader to consume Timescale (via `src/db_timescale.py`) instead of DuckDB/Parquet.
- [ ] `src/backtest/pricers.py` — option pricing callbacks. Two implementations:
  - `TimescalePricer` — mark-to-market from stored OHLC (primary).
  - `BlackScholesPricer` — for strikes/expiries not in Timescale (fallback; Phase 3 concern, stub for now).
- [ ] `src/backtest/costs.py` — realistic Indian options cost model:
  - Brokerage: ₹20/order (Zerodha/Upstox flat).
  - STT: 0.1% on sell side of premium for options sold; 0.125% on intrinsic value if exercised ITM.
  - Exchange transaction charges: 0.0345% on premium (NSE F&O).
  - GST: 18% on brokerage + transaction.
  - SEBI turnover fee: ₹10 per crore of premium.
  - Stamp duty: 0.003% on buy side.
  - Slippage model: 0.5–1 INR per lot at entry/exit under normal vol, 2–3 INR on expiry-day fast markets. Parameterise via `SlippageModel` dataclass.
- [ ] Tests: engine happy path, daily-loop invariants, cost model unit tests (each cost component + total on a known trade), slippage model edge cases.
- [ ] `code-reviewer` on diff — heavy focus on Decimal invariant (not float) throughout the cost model.
- [ ] Commit sequence: engine → pricers → costs → integration test.

**Decision to record in `DECISIONS.md`:** "Backtest cost model built as a composable `CostModel` with separate functions per cost component (brokerage, STT, exchange, GST, SEBI, stamp, slippage). Rationale: each component has its own regulatory source and changes independently. Unit-testable in isolation. Parametrised for what-if scenarios."

---

## 1.5 — CODE — Backtest results storage

Backtest output is low-volume and relational — belongs in SQLite, not Timescale.

- [ ] `src/backtest/store.py` — `BacktestStore` with tables:
  - `backtest_runs` — one row per run: `run_id`, `strategy_name`, `strategy_version`, `start_date`, `end_date`, `config_json`, `git_sha`, `created_at`.
  - `backtest_daily_pnl` — `run_id, date, unrealized_pnl, realized_pnl, mark_to_market, open_positions`.
  - `backtest_trades` — same shape as live `trades` table, with `run_id` FK.
  - `backtest_metrics` — `run_id, metric_name, value` (flexible for Sharpe, Sortino, max DD, etc.).
- [ ] `git_sha` captured automatically at run start — so every backtest is reproducible. Record the SHA of the strategy code, the cost model, the ingest pipeline.
- [ ] Tests: CRUD, idempotency (same run_id = UPDATE), JSON config round-trip.
- [ ] Commit: `feat(backtest): results storage`.

**Why this matters:** Six months from now, when you re-run the CSP backtest and get different numbers, you need to know whether it's because the data changed, the code changed, or the config changed. `git_sha` + `config_json` + `run_id` gives you that answer.

---

## 1.6 — CODE — Port Iron Condor strategy (reference implementation)

Port the IC strategy from quant-4pc as the second test of the engine (first test is CSP in 1.7). Do not deploy IC anywhere yet — this is an engine validation exercise.

- [ ] `src/strategy/iron_condor.py` — port `IronCondorConfig`, `IronCondorState`, `IronCondorStrategy` from quant-4pc per `PLANNER.md`. Adapt to NiftyShield's `Strategy` Protocol and Decimal invariant.
- [ ] `src/strategy/__init__.py` — package marker. Re-index graph.
- [ ] Tests: config validation, entry/exit decision logic (fixture-driven, no live data), pluggable pricer behavior.
- [ ] This is a **scaffolding port**, not a live strategy. No spec document needed yet.
- [ ] Commit: `feat(strategy): port iron condor from quant-4pc reference`.

---

## 1.6a — CODE — Black-Scholes Greeks for backtest

Dhan's `rollingoption` (historical) payload includes `iv` but not `delta`, `gamma`, `theta`, or `vega`. Strategies that select strikes by delta (CSP at 25-delta, IC at 15-delta wings) need local computation. **Decision (2026-04-17):** Option A — Black-Scholes from stored IV only, for historical backtest. Live paper trading uses Dhan's own Greeks from `/v2/optionchain` (see 1.10).

- [ ] `src/backtest/greeks.py` — pure functions:
  - `black_scholes_price(S, K, T, r, sigma, option_type)` → price.
  - `delta(S, K, T, r, sigma, option_type)` → delta.
  - `gamma`, `theta`, `vega` — sibling functions.
  - Use `scipy.stats.norm` for `N(d1)`/`N(d2)`. Add scipy to `requirements.txt`.
  - `r` (risk-free rate) — default to a configurable constant (7% for current Indian regime); expose as a parameter of `CostModel` or `BacktestConfig` so it can be tuned.
  - `T` (time to expiry in years) — computed from strategy `now` date to expiry date; **convention: calendar days / 365.25**. Document this explicitly in the module docstring — trading-days-over-252 is equally defensible and yields slightly different deltas, so the choice must be visible.
  - No dividend yield adjustment. Indian index options are European on a forward, but the forward-vs-spot gap on Nifty is small (<1% on monthly) and including it adds complexity without improving the backtest's fitness-for-purpose.
- [ ] Tests:
  - Parity check: BS call + put at same strike satisfy put-call parity to within 1e-4.
  - Known-value tests: compute delta for ATM option at 30 DTE at 15% IV → must be close to 0.52 for call, -0.48 for put. Pin these with `pytest.approx`.
  - Boundary: 0 DTE (expiration day) returns intrinsic for in-the-money, 0 for out-of-the-money.
- [ ] `src/backtest/strike_selector.py` — `select_strike_by_delta(chain, target_delta, option_type, now, expiry, r)` — reverse-lookup: given target delta, find the closest `atm_offset` strike in the loaded chain that satisfies it. Uses `greeks.delta()` + the `iv` from Dhan data.
- [ ] Tests: strike selection happy path, target-delta unreachable (log WARNING, return closest available), out-of-ATM-window (return None).
- [ ] Commit: `feat(backtest): Black-Scholes Greeks + delta-based strike selector`.

**Known bias (must be called out in the variance check at 1.11):** Local BS deltas will systematically differ from Dhan's reported deltas (from the live chain snapshots captured in 1.10) by ~0.5–2 delta points at 25-delta. Causes: Dhan fits a volatility surface and applies forward-adjustment assumptions; we use raw BS with a fixed `r` and no dividend/forward correction. Practical effect: backtest strike selection at "25-delta" may pick ATM−3 while live paper trading at "25-delta" picks ATM−4 on the same day, or vice versa. The P&L impact is small per month but creates a structural backtest-vs-paper variance floor that must be **subtracted or acknowledged** before computing the |Z| ≤ 1.5 threshold in 1.11. If this bias turns out to be larger than expected in practice, the fix is either (a) calibrate `r` to minimize RMS delta error against the 1.10 snapshot dataset, or (b) switch to reading historical Greeks from the 1.10 snapshot store for the subset of dates where snapshots exist (post-Phase-1.10 dates only; pre-Phase-1.10 history stays on BS).

**Why not do (b) upfront:** Phase 1 needs backtest results over 5 years, but 1.10 snapshots only start accumulating from 1.10 deployment date. Using snapshot Greeks for the last ~3 months and BS for the prior 5 years creates a discontinuity at the boundary that will confound the variance check. Uniform BS across the full history is the cleaner methodology. Revisit after Phase 2 when 6+ months of snapshot data exists.

---

## 1.7 — CODE — Implement CSP strategy in backtest engine

- [ ] `src/strategy/csp.py` — cash-secured put strategy matching `docs/strategies/csp_nifty_v1.md`
  line-for-line. Strategy rules are code-generated from the spec; if spec changes, code
  changes, commit both together.
- [ ] Config dataclass `CSPConfig` exposes all parameters from the spec: `target_delta`,
  `entry_dte_range`, `profit_target_pct`, `time_stop_days` (calendar days from entry — not
  DTE remaining), `loss_stop_delta` (R2 delta gate, default −0.45), `loss_stop_mark_multiple`
  (R2 mark trigger, default 1.75), `underlying_symbol`, `lot_size`,
  `niftybees_instrument_key` (default `NSE_EQ|INF204KB14I2`).
- [ ] **NiftyBees collateral leg in backtest P&L (required):** The backtest engine must model
  the NiftyBees ETF position alongside the short put — same decision as paper trading (see
  `DECISIONS.md` 2026-04-25 entry). At each simulated strategy start date, compute
  `niftybees_qty = floor(lot_size × nifty_spot / niftybees_ltp)` using the historical Nifty
  spot and NiftyBees closing price on that date. Mark the ETF position to market daily
  alongside the option. Annual reset within a multi-year backtest run: close the old ETF
  position at year-end, open a new qty-adjusted position in January. The combined P&L
  (option + ETF) is the authoritative metric for variance comparison against paper results.
- [ ] **R5 re-entry logic** implemented as an explicit branch in `on_day`, togglable via
  config flags:
  - `enable_reentry: bool = False` — default off → V1 baseline (no re-entry).
  - `enable_reentry=True, ivr_gated=True` → V2 (re-enter after profit exit if DTE ≥ 14 and
    IVR ≥ 25).
  - `enable_reentry=True, ivr_gated=False` → V3 (re-enter after any exit if DTE ≥ 14, no
    IVR gate).
  This three-way toggle must be clean enough to flip in config without touching strategy
  logic, so V1/V2/V3 variant runs differ only in config, not code.
- [ ] Tests: entry decision (correct strike from chain), exit decision (each of: profit
  target, 21-day time stop, delta gate, mark gate), R5 re-entry branch (IVR-gated and
  ungated paths), no-open-position idempotency.
- [ ] Commit: `feat(strategy): cash-secured put v1`.

---

## 1.8 — CODE — Run CSP backtest across full history (three variants)

Run three comparable variants so the V1-vs-V2-vs-V3 decision is data-driven:

- [ ] **V1** (baseline — no re-entry): `--strategy csp --config docs/strategies/csp_nifty_v1.md
  --variant V1` (`enable_reentry=False`)
- [ ] **V2** (R5 re-entry, IVR-gated): `--variant V2` (`enable_reentry=True, ivr_gated=True`)
- [ ] **V3** (always-on roll, no IVR gate): `--variant V3` (`enable_reentry=True,
  ivr_gated=False`)

`scripts/run_backtest.py` must accept a `--variant` flag and persist each run with its own
`run_id` + `variant` tag in `backtest_runs`. The three runs are comparable — same data
window, same cost model, same underlying — differing only in the re-entry config flag.

For each variant, extract from `backtest_daily_pnl` + `backtest_metrics`:
- Annualised net return (after cost model)
- Max drawdown (depth + duration)
- Monthly P&L distribution: mean, median, 5th percentile, 95th percentile, worst month
- **Sharpe, Sortino** (both required for the V1-vs-V2-vs-V3 comparison)
- Monthly win rate
- Behaviour during stress windows: Feb–Mar 2022, Jun 2024 (election day), Oct 2024

**Note on historical window:** Dhan `rollingoption` data starts 2021-08-01. COVID crash
(Mar 2020) is not covered — acknowledged limitation. Best available stress scenario is Jun
2024 election day.

**Note on R3 (IVR filter):** India VIX ingestion does not yet exist (see 1.1 note). All
three variant runs proceed without the IVR entry filter. Document this gap explicitly in the
backtest result notes — live paper trading will apply R3 manually until the ingestion
pipeline is built.

- [ ] Write results into `docs/strategies/csp_nifty_v1.md` → "Backtest Results" table (all
  three variants side by side). The V1-vs-V2-vs-V3 verdict is **Animesh's** to make based on
  the data; the backtest provides the comparison, not the decision.
- [ ] Commit: `docs(strategies): CSP v1 backtest results (V1/V2/V3 variants)`.

---

## 1.10 — CODE — Dhan live option chain client + daily snapshot

**Decision (2026-04-17):** Switch live Greeks source from Upstox to Dhan `/v2/optionchain`. Dhan returns `greeks.delta/theta/gamma/vega`, `implied_volatility`, `top_bid_price`/`top_ask_price`, OI, volume at every strike in one call. Upstox remains wired as a documented fallback — same `BrokerClient` protocol, different implementation.

- [ ] `src/client/dhan_market.py` — new async client for Dhan Data APIs. Methods:
  - `get_option_chain(underlying_scrip: int, underlying_seg: str, expiry: date) → OptionChain` — POSTs to `/v2/optionchain`. Uses the existing `OptionChain` Pydantic model from 0.2 (extended if needed to carry bid/ask and full Greeks dict — the model was sketched against an Upstox fixture, verify it accommodates Dhan's shape).
  - `get_expiry_list(underlying_scrip, underlying_seg) → list[date]` — POSTs to `/v2/optionchain/expirylist`. Returns parsed dates.
  - Rate limit: **1 request per 3 seconds** per Dhan docs. Use the same token bucket from 1.3 but parameterised (this is a different budget from rollingoption's 1/sec). `RateLimiter(1, 3.0)`.
  - Authentication: `DHAN_ACCESS_TOKEN` + `DHAN_CLIENT_ID` from `.env` (already present).
- [ ] `src/client/dhan_market.py` conforms to `MarketDataProvider` sub-protocol from `src/client/protocol.py`. No new protocol methods.
- [ ] `UnderlyingScrip` lookup: Nifty 50 is `13`, segment `IDX_I` per Dhan sample payloads. Add these as constants in `src/dhan/constants.py` along with any other commonly-queried underlyings (NIFTYBEES — look up security ID from Dhan instrument list, record in `REFERENCES.md`). **Do not hardcode magic numbers inside the client** — all security IDs go through the constants module.
- [ ] Extend `factory.py` — `create_market_data_provider(source: str)` where `source ∈ {"dhan", "upstox"}` returns the appropriate `MarketDataProvider`. Default from env var `MARKET_DATA_SOURCE=dhan`. Upstox path preserved for fallback.
- [ ] Tests: fixture-driven (record a real Dhan response on day one, commit to `tests/fixtures/responses/dhan_option_chain/`). Cover: happy path, empty chain, single-sided chain (only CE or only PE populated), rate-limiter behavior.
- [ ] `code-reviewer` agent on diff — heavy focus on protocol conformance and rate-limit correctness.

**Snapshot job (runs in parallel with daily_snapshot.py):**

- [ ] `scripts/dhan_chain_snapshot.py` — cron-ready. Holiday guard via `market_calendar.is_trading_day`. Fetches option chain for: (Nifty 50, current-week expiry), (Nifty 50, current-month expiry), (Nifty 50, next-month expiry). Three API calls = ~9 seconds at rate limit.
- [ ] Persist to new Timescale hypertable `option_chain_snapshots`: `(underlying, expiry_date, strike, option_type, snapshot_ts, ltp, bid, ask, oi, volume, iv, delta, gamma, theta, vega, spot)`. Hypertable on `snapshot_ts`, chunk interval 7 days. Primary key `(underlying, expiry_date, strike, option_type, snapshot_ts)`.
- [ ] Cron entry: `30 15 * * 1-5` (3:30 PM IST, before the 3:45 `daily_snapshot.py`, so the chain snapshot is captured at closer-to-closing levels without competing for rate-limit budget).
- [ ] Tests: mock chain response, verify persistence, snapshot idempotency.
- [ ] Commit sequence: client → factory wire-up → snapshot CLI + schema → tests.

**Why start the snapshot accumulating in Phase 1 even though it's not used by the Phase 1 backtest:** Forward-looking data capture. By end of Phase 2 you have 6+ months of daily Greeks + bid/ask captured, which unlocks three things: (a) calibration dataset for the BS-vs-Dhan delta drift documented in 1.6a; (b) realised bid/ask spread dataset to fit the Phase 1.4 slippage model against; (c) primary Greeks source for Phase 3+ strategies that need realistic delta tracking. None of these require the snapshot to start later. Starting it now costs one cron job.

**Capacity note to record in `DECISIONS.md`:** Dhan option chain rate limit of 1 req / 3 sec caps intraday chain refresh at ~20 per minute. Sufficient for EOD snapshots and per-trade-decision paper strategies. **Not sufficient for tick-level delta-neutral adjustment** (Phase 3+ concern). If a future strategy needs sub-3-second chain updates, either batch a single chain call across multiple strategies (all strikes in one response) or fall back to Upstox's option chain for that strategy's live-Greeks path. The `MarketDataProvider` protocol allows this swap without touching the strategy code.

---

## 1.9 — CODE — Synthetic pricer for deep OTM protective legs

Required for backtesting NiftyShield integrated strategy (Legs 2+3). Dhan
`rollingoption` does not cover 8–30% OTM strikes. Build a Black-Scholes synthetic
pricer with parametric vol skew.

- [ ] `src/backtest/skew.py` — parametric vol skew model:
  - `iv_with_skew(atm_iv, spot, strike, option_type)` → adjusted IV.
  - Initial model: fixed markup of +2% IV per 5% OTM (linear extrapolation from ATM).
  - Calibration interface: `fit_skew(observed_chain: OptionChain)` → `SkewParams`.
    Uses live chain snapshots from 1.10 when available; falls back to fixed markup.
  - Output: `SkewParams` dataclass with `slope_per_pct_otm` (default 0.4, i.e.,
    +2% per 5% OTM = 0.4% per 1% OTM) and optional quadratic term for smile
    curvature (deferred to Phase 2).
- [ ] `src/backtest/synthetic_pricer.py`:
  - `price_otm_put(spot, strike, expiry, atm_iv, skew_params, r, now)` → Decimal.
  - Combines `greeks.black_scholes_price` (from 1.6a) with `skew.iv_with_skew`.
  - `price_put_spread(spot, long_strike, short_strike, ...)` → net debit (Decimal).
  - `price_tail_put(spot, strike, ...)` → premium (Decimal).
- [ ] Tests: known-value synthetic prices vs hand-computed BS; skew markup correctness
  (8% OTM = +3.2% IV, 20% OTM = +8% IV); spread debit = long − short; edge cases
  (0 DTE, deep ITM).
- [ ] Commit: `feat(backtest): synthetic pricer with parametric vol skew for deep OTM`.

**Known bias (document in every backtest using this pricer):** BS + linear skew
underprices deep OTM puts by an estimated 10–20% vs real market. The paper-trading
phase (0.6a) collects real prices to measure this gap. After 6 months of 1.10
snapshots, recalibrate via `fit_skew` and re-run.

---

## 1.9a — CODE — Integrated strategy backtest (three legs combined)

Run NiftyShield integrated strategy across available history:
- Leg 1 (CSP): uses `TimescalePricer` from real Dhan data (per 1.7).
- Legs 2+3: uses `SyntheticPricer` from 1.9.

- [ ] `src/strategy/niftyshield.py` — `NiftyShieldConfig` + `NiftyShieldStrategy`
  implementing the `Strategy` protocol. Composes CSP logic (from 1.7) with protective
  put spread entry/exit and quarterly tail put entry. Config exposes: `put_spread_lots`,
  `tail_put_lots`, `otm_pct_long` (default 0.08), `otm_pct_short` (default 0.20),
  `tail_delta` (default 0.05), `beta` (default 1.25), `coverage_ratio` (default 0.65).
- [ ] Backtest across 2021-08 to present. Persist results in `backtest_runs` with
  `strategy_name = niftyshield_integrated_v1`.
- [ ] Extract metrics: net annual cost in flat/up years, payoff in Feb–Mar 2022
  (Russia/Ukraine ~15% drop), payoff in Jun 2024 (election day), combined Sharpe,
  max drawdown depth + duration.
- [ ] Write results into `docs/strategies/niftyshield_integrated_v1.md` → "Backtest
  Results" section.
- [ ] Commit: `docs(strategies): NiftyShield integrated v1 backtest results`.

**Critical note:** The Feb–Mar 2022 stress test is the most important single output.
If the put spread does not show a positive payoff during that window, the synthetic
pricer or the strategy logic has a bug. Investigate before moving on.

---

## 1.11 — STRATEGY — Variance check: paper vs backtest

**Owner: Animesh. Cowork may assist with the SQL/computation but the decision is yours.**

This is the core validation gate of the whole pipeline. If this step doesn't pass, the backtest is not trustworthy and Phase 2 cannot start.

- [ ] Compute the distribution of monthly returns from the CSP backtest, restricted to months that overlap the paper-trade window from Phase 0.6.
- [ ] Compute the distribution of monthly returns from the paper-trade data over the same window.
- [ ] Z-score: `(paper_mean - backtest_mean) / backtest_std`.
- [ ] **Pass condition:** |Z| ≤ 1.5. Realised within ±1.5 SD of backtest.
- [ ] **Expected bias (subtract before computing Z):** The BS-vs-Dhan delta drift from 1.6a
  typically costs 5–10 paise per lot per month on strike selection. If paper traded
  Dhan-delta-selected strikes and backtest used BS-delta-selected strikes, the systematic
  drift is real and not a bug. Compute the magnitude by re-running the **active variant**
  (V1, V2, or V3 — whichever Animesh selected after 1.8) with strike selection forced to
  match the strikes actually paper-traded (not delta-selected); the difference between the
  two runs = the BS selection bias. Subtract this from the paper-vs-backtest gap before
  evaluating Z. The active variant must be recorded in `docs/strategies/csp_nifty_v1.md`
  "Variance Check Results" before this computation runs.
- [ ] **Fail condition (after bias adjustment):** |Z| > 1.5. The backtest is miscalibrated.
  Debug before proceeding. Likely culprits in order of probability: slippage model too
  optimistic, cost model missing a component, entry/exit logic in code diverges from
  paper-trade behaviour, backtest data has survivorship or fill-assumption issues, BS drift
  larger than expected (revisit 1.6a option-(a) calibration of `r`).
- [ ] Record Z-score, bias adjustment, active variant, and decision in
  `docs/strategies/csp_nifty_v1.md` → "Variance Check Results" section.
- [ ] If fail: iterate on the backtest until it aligns, then re-run 1.8 and 1.11.

---

## 1.12 — GATE — End of Phase 1

- [ ] 1.1–1.10 all `[x]` (including **1.3a**, 1.6a, 1.9, 1.9a, and 1.10).
- [ ] 1.3a complete: Nifty 50 daily + 15-min, India VIX daily, NiftyBees daily ingested to Parquet; data quality gate passed (Nifty close ±0.05% vs NSE, VIX <1% missing days, NiftyBees tracking error <0.5% over any rolling 1-year period).
- [ ] 1.11 passes (|Z| ≤ 1.5, bias-adjusted) for CSP leg with results documented.
- [ ] 1.9a integrated backtest run complete; Feb–Mar 2022 stress test shows positive
  put spread payoff; results written to `niftyshield_integrated_v1.md`.
- [ ] Timescale has ≥3 years of Nifty options data ingested.
- [ ] Full test suite green.
- [ ] Animesh sign-off in a `TODOS.md` session log entry: "CSP backtest calibrated to paper. Ready to go live."

---

# Phase 2 — CSP Live + Iron Condor Paper

**Objective:** Deploy CSP live (1 lot) with continuous backtest/paper re-validation, and start paper-trading the iron condor to feed it into the same pipeline.

**Duration target:** ~6 months.

**Key behavioral rule:** Do not scale CSP beyond 1 lot for the first 3 months even if it is profitable. First 3 months of any new live strategy = regime-dependent data, not proof of edge.

---

## 2.1 — CODE — Continuous re-validation loop

The most important piece of code in this plan. Detects strategy drift in real time.

- [ ] `src/backtest/continuous.py` — weekly job that:
  1. Re-runs CSP backtest over the trailing 3 months of history.
  2. Queries live (or paper) P&L over the same 3-month window.
  3. Computes Z-score of realised vs backtest.
  4. Logs to `backtest_runs` with a `mode = "continuous"` flag.
  5. Alerts via Telegram if |Z| > 1.5 for 3 consecutive weeks.
- [ ] Cron entry: `0 18 * * SUN` (Sunday evening, after Friday close + weekend data settle).
- [ ] Tests: Z-score computation, threshold trigger, Telegram notification path (mocked).
- [ ] Commit: `feat(backtest): continuous re-validation`.

---

## 2.2 — STRATEGY — Deploy CSP live (1 lot)

**Owner: Animesh.**

- [ ] Upstox order execution status: Phase 2 of this plan assumes static IP is provisioned. If it is not, CSP goes live via manual order placement; NiftyShield still records trades via `record_trade.py`.
- [ ] Entry: first monthly expiry cycle after Phase 1 gate passes. Strike per the CSP spec.
- [ ] 1 lot only (lot size 65 as of Jan 2026; confirm current lot size before entry — lot sizes change annually).
- [ ] Commitment: at least 6 monthly cycles before deciding to scale, extend, or kill.

---

## 2.3 — STRATEGY — Iron Condor v1 specification

**Owner: Animesh.**

- [ ] `docs/strategies/ic_nifty_monthly_v1.md` — same required sections as CSP spec (0.4). Strategy candidate: 15-delta wings, 30–45 DTE entry, exit at 50% profit OR 21 DTE OR 2× credit loss, defined-risk (not naked), sized so max loss ≤ 2% of total capital.
- [ ] Passes strategy-spec validator (0.7).
- [ ] Invoke `options-strategist` agent on the sizing/risk section before committing.
- [ ] Commit: `docs(strategies): add IC v1 specification`.

---

## 2.4 — CODE — IC strategy to match spec

- [ ] Extend `src/strategy/iron_condor.py` to match `ic_nifty_monthly_v1.md` exactly. Diff against the scaffolding port from 1.6.
- [ ] Tests: all four legs entered at spec strikes, exit triggers, risk cap enforcement.
- [ ] Commit: `feat(strategy): iron condor v1 implementation`.

---

## 2.5 — CODE — IC backtest

- [ ] Run IC backtest across 2020–present. Persist results.
- [ ] Extract metrics as in 1.8. Add results section to `ic_nifty_monthly_v1.md`.
- [ ] Commit: `docs(strategies): IC v1 backtest results`.

---

## 2.6 — STRATEGY — Paper trade IC v1 (parallel to CSP live)

**Owner: Animesh.**

- [ ] Start paper trading IC v1 in parallel with CSP live.
- [ ] Minimum duration before considering live: 12 weeks + 1.11-style variance check passing.
- [ ] Log every entry, exit, adjustment decision in the paper trade store (Phase 0.5 infrastructure).

---

## 2.7 — GATE — End of Phase 2

- [ ] CSP live for ≥3 months within backtest envelope (|rolling 3-month Z| < 1.5 consistently).
- [ ] No kill criterion triggered for CSP.
- [ ] IC v1 paper trading ≥12 weeks, variance check passed (per 1.11 methodology).
- [ ] Continuous re-validation loop operational and has run weekly with no missed runs.

---

## Phase 2 — Parallel Research Tracks (start after Phase 1.12 gate)

These two tracks run **in parallel** with Phase 2.1–2.7. They are independent of the CSP/IC pipeline — the only prerequisite is Phase 1.12 (backtest engine + data pipeline complete). Neither track must wait for 2.7 to close before starting.

**Track A data cost:** Stages 2.S0–2.S3a (Tier 1) use **zero paid data** — Upstox OHLC only, from task 1.3a. Tier 2 (option spread backtesting, 2.S3b) requires DhanHQ at the same ₹400/month as task 1.3. Tier 2 is conditional on Tier 1 passing.

**Track B data cost:** All stages use **zero paid data** — Upstox OHLC (1.3a), NSE PE CSV (free download), AMFI liquid fund NAV (already in `src/mf/`). No DhanHQ at any stage.

Full methodology documents: `docs/plan/SWING_STRATEGY_RESEARCH.md` (Track A) · `docs/plan/INVESTMENT_STRATEGY_RESEARCH.md` (Track B).

---

### Track A — Swing Strategy Pipeline

Three strategies researched sequentially: **Donchian Channel Trend Following → Opening Range Breakout → Gap Fade**. One strategy must be fully validated through paper trading (2.S6) before the next begins signal generation (2.S2). No parallelism within the track.

#### 2.S0 — CODE — Swing data infrastructure

**No paid data required.**

- [ ] Verify Upstox OHLC Parquet from 1.3a covers: Nifty 50 daily + 15-min, India VIX daily.
- [ ] Confirm derived fields present: 14-day ATR, 20-day ATR, 50-day regression slope, 252-day VIX percentile rank.
- [ ] **Gate:** Nifty close ±0.05% vs NSE; VIX <1% missing trading days; ATR and slope values visually consistent with chart overlay on Nifty price history. No code written until data verified.

#### 2.S1 — CODE — Regime engine (`src/strategy/regime.py`)

**No paid data required.**

- [ ] 3×3 classifier: Dimension 1 = trend slope (50-day linear regression normalised by 50-day ATR → Trending up / Range-bound / Trending down). Dimension 2 = VIX percentile (252-day trailing → High vol >75th / Normal 25–75th / Low <25th).
- [ ] Tag every historical trading day with its regime cell. Store alongside OHLC in the signal Parquet.
- [ ] Regime distribution report: % of days and % of total Nifty return in each cell.
- [ ] **Gate:** Tags deterministic (same input → same output). No single cell >40% of all trading days. 2022 H1 correction visually tagged "trending-down + high-vol" transitioning to "range-bound + normal-vol".

**Overlap note:** This regime engine feeds directly into Phase 3.5's classifier — see 3.5 for consolidation guidance.

#### 2.S2 — CODE — Signal generators (sequential: Donchian → ORB → Gap Fade)

**No paid data required (Tier 1 points-based signals on spot index).**

- [ ] **2.S2a — Donchian Channel:** Daily OHLC → LONG/SHORT/FLAT signal + trailing stop level + current ATR. Parameters: channel lookback 40D (sweep 20–60), ATR stop multiplier 3.0 (sweep 2.0–4.5), ATR lookback 20D. Always-in system.
- [ ] **2.S2b — ORB:** 15-min OHLC + daily ATR → LONG/SHORT/NO_TRADE + OR range + target/stop levels. Entry on breakout candle close. Structural filter: exclude weekly expiry Thursdays. Parameters: opening candle count 2 (sweep 1–3), max OR width 0.6× 14D ATR (sweep 0.3–0.8), R:R multiple 1.5 (sweep 1.0–2.5).
- [ ] **2.S2c — Gap Fade:** Daily open vs prev close + 15-min → LONG/SHORT/NO_TRADE + gap size + target. VIX filter: skip when VIX > 75th percentile. Parameters: min gap 0.3% (sweep 0.2–0.5%), max gap 1.0% (sweep 0.7–1.5%), fill fraction 0.5 (sweep 0.3–0.7).
- [ ] **Gate per signal:** Trade log on full training set (pre-Jan 2024). Trade count within expected range: Donchian 15–25/yr, ORB 80–150/yr after filter, Gap Fade 60–100/yr after filter. No signals on non-trading days. No overlapping positions in always-in system.

#### 2.S3a — CODE — Tier 1 backtester (points-based) — `src/backtest/points_bt.py`

**No paid data required.**

- [ ] Per-signal P&L in Nifty points: entry price = spot at signal trigger; exit = spot at exit trigger (trailing stop / target / time stop). Direction: +1 long, −1 short.
- [ ] Mark-to-market daily (unrealised equity curve), not just trade-level.
- [ ] Cost model: flat ₹40/round-trip + 0.5 points slippage per side.
- [ ] **Donchian Tier 1 gate:** Equity curve + trade log + summary stats (Calmar, win rate, avg win/avg loss, max consecutive losses, max drawdown in points). Pass criteria: trade log internally consistent; win rate 35–50%; profit factor > 1.3. If win rate >60% or <25%, signal logic has a bug.
- [ ] If Donchian passes Tier 1: run ORB Tier 1, then Gap Fade Tier 1.

#### 2.S3b — CODE — Tier 2 backtester (option spread P&L) — `src/backtest/spread_bt.py`

**Requires DhanHQ expired options data (same ₹400/month as task 1.3).**

**Conditional on Tier 1 passing for the same strategy. A strategy may advance to walk-forward (2.S4) on Tier 1 P&L alone if DhanHQ strike coverage is insufficient.**

- [ ] Extend Phase 1 backtest engine to handle vertical spreads and iron condors (not just single legs).
- [ ] Strike selection per execution mapping (see `SWING_STRATEGY_RESEARCH.md §Design Constraint`): short strike at ~15-delta, long strike 200 points further OTM for credit spreads; iron condors = bull put spread + bear call spread.
- [ ] VIX regime governs spread type: credit spreads (normal/high VIX) vs debit spreads (low VIX) vs skip (neutral + low VIX).
- [ ] Track exclusion rate per strategy: if >20% of trades excluded due to missing DhanHQ strikes, Tier 1 is the authoritative validation for that strategy.
- [ ] Slippage sensitivity: re-run at 0, 2, 4 points per leg. If profitability flips between 2 and 4 points, edge is too thin for options execution.
- [ ] **Gate:** Tier 1 vs Tier 2 P&L gap documented (quantifies conversion cost of directional edge into options P&L). Results internally consistent (no negative prices, no trades on non-trading days).

#### 2.S4 — CODE + STRATEGY — Walk-forward optimisation + validation (per strategy)

- [ ] Rolling walk-forward: 252-day training window, 63-day step, parameter sweep per strategy within specified ranges. Primary P&L tier: Tier 1 (mandatory). Run Tier 2 walk-forward also if Tier 2 data available; Tier 1 optimum is authoritative if tiers disagree.
- [ ] Per-window OOS Calmar. Monte Carlo: 10,000 iterations on OOS trade returns — check 95th percentile DD < 1.5× observed max DD, 99th percentile DD < 50% of allocated capital.
- [ ] Parameter sensitivity: ≥60% of neighbours within 80% of optimal on all parameter axes; plateau width ≥3 steps per axis.
- [ ] Regime decomposition: no single regime cell contributing >80% of cumulative profit.
- [ ] **6 failure conditions** (per `SWING_STRATEGY_RESEARCH.md §Part 3`): OOS Calmar, walk-forward consistency, MC 95th DD, parameter sensitivity, regime concentration, slippage sensitivity. Any kill = abandon that strategy, move to next.
- [ ] Calmar thresholds: Donchian ≥0.8 · ORB ≥0.6 · Gap Fade ≥0.5.
- [ ] STRATEGY gate: human review and sign-off on full validation report (equity curve, trade log, MC distribution chart, parameter sensitivity heatmap, regime decomposition table).

#### 2.S5 — CODE — Portfolio construction (if ≥2 strategies pass 2.S4)

- [ ] Equal-risk allocation: normalise position size so each strategy contributes equal ATR-based risk to the combined portfolio.
- [ ] Combined OOS equity curve on Jan 2024+ test set.
- [ ] Combined walk-forward median Calmar ≥1.0; pairwise daily return correlation <0.3; MC 95th percentile combined DD < individual strategy worst-case.
- [ ] If only 1 strategy survived 2.S4: skip portfolio construction, proceed to 2.S6 with that strategy solo.
- [ ] **Gate:** Portfolio allocation weights documented; combined equity curve and risk metrics reviewed; human sign-off.

#### 2.S6 — STRATEGY — Paper trading (surviving strategies)

**Owner: Animesh. Not for Cowork.**

- [ ] Minimum 60 trading days (~3 calendar months). Minimum 15 completed trades for directional strategies, 8 for iron condors.
- [ ] Strategy name prefix: `paper_research_<strategy>_v1` (e.g., `paper_research_donchian_v1`).
- [ ] Record via `record_paper_trade.py`: observe live option chain, select strikes per execution mapping, record entry with bid/ask at decision time. Apply 1-point adverse slippage (note in record).
- [ ] Iron condor entry conditions: range-bound trend AND 25th–75th VIX percentile (both required); monthly expiry 30–45 DTE; skip when VIX <25th percentile.
- [ ] **Gate:** Realised Sharpe, win rate, avg trade duration within 1 SD of walk-forward OOS distribution. >1.5 SD below expectation → stop and diagnose (execution model wrong or regime shift). Paper trading report with trade log, equity curve, comparison to backtest OOS distribution, slippage analysis.

#### 2.S7 — STRATEGY — Live deployment (minimum viable size)

**Owner: Animesh. Not for Cowork.**

- [ ] 1 lot Nifty options per spread. Maximum 2 concurrent positions (1 directional + 1 neutral, or 2 directional from different strategies).
- [ ] Scaling: 2 lots after 60 live trading days with metrics within 1 SD of paper results. Never faster.
- [ ] Live kill criteria: trailing 60-day Calmar <0.3 → reduce to 1 lot, review; 3 consecutive losses >1.5× average backtest loss → pause, diagnose; any single trade loss >2× spread width → halt immediately (execution error).

---

### Track B — Investment Strategy Pipeline

Three strategies researched sequentially: **10-Month SMA Trend Filter → Dual Momentum → PE Band Rebalancing**. One strategy validated before the next begins.

**All stages: zero paid data required throughout.** Sources: Upstox OHLC (from 1.3a, existing token), NiftyBees NAV (Upstox, existing token), Nifty PE ratio (NSE historical CSV, free download), liquid fund NAV (AMFI, already in `src/mf/`).

#### 2.I0 — CODE — Investment data infrastructure

**No paid data required.**

- [ ] Nifty 50 weekly + monthly OHLC derived from daily Parquet in 1.3a (no new API call).
- [ ] NiftyBees ETF daily close from Upstox (existing token, `NSE_EQ|INF204KB14I2`).
- [ ] Nifty trailing PE monthly series from NSE historical CSV download (verify availability back to 1999; use full history if available).
- [ ] Risk-free rate series: 364-day T-bill yield OR liquid fund NAV (AMFI, already in `src/mf/`).
- [ ] Storage: Parquet, same convention as swing OHLC.
- [ ] **Gate:** NiftyBees NAV tracks Nifty 50 within ±0.5% tracking error over any rolling 1-year period. PE data <2% missing months (fill with previous value; flag gaps >1 month). Risk-free rate series complete for full backtest period. PE data visually cross-checked against NSE PE charts at known inflection points (2008 crash ~12, 2020 crash ~18, 2024 peak ~24).

#### 2.I1 — CODE — Signal generators (sequential: SMA → Dual Momentum → PE Band)

**No paid data required.**

- [ ] **I-1a: 10-month SMA signal** → monthly allocation % (0% or 100%). Entry when Nifty monthly close > N-month SMA. Exit when close < SMA. Parameters: SMA lookback 10 months (sweep 8–14), re-entry delay 0 months (sweep 0–2).
- [ ] **I-1b: Dual Momentum signal** → monthly allocation % (0% or 100%). Both conditions required: (1) Nifty trailing N-month return > 0% (absolute momentum); (2) Nifty trailing N-month return > risk-free rate proxy (relative momentum). Parameters: absolute lookback 12 months (sweep 6–15), relative lookback 12 months (sweep 6–15), risk-free rate 7% (sweep 5–8%).
- [ ] **I-1c: PE Band signal** → quarterly allocation % (30%, 70%, or 100%). Allocation rules: PE <18 → 100%; PE 18–25 → 70%; PE >25 → 30%. 30% floor preserves NiftyBees collateral for Finideas margin. Parameters: low threshold 18 (sweep 15–20), high threshold 25 (sweep 23–28), intermediate allocation 70% (sweep 50–80%).
- [ ] **Gate per signal:** Allocation log on full training set (pre-Jan 2024). Allocation change count within expected range: SMA 2–4/yr, Dual Momentum 2–4/yr, PE Bands 1–3/yr. >6 changes/yr → signal too noisy for >1yr investment approach.

#### 2.I2 — CODE — Points-based backtest (`src/backtest/allocation_bt.py`)

**No paid data required. Tier 1 only — no option data used at any stage.**

- [ ] P&L in NiftyBees NAV terms: entry NAV × (exit NAV / entry NAV − 1) × allocation %. Cash return (liquid fund rate) applied during out-of-market periods.
- [ ] Transaction costs: ₹100/round-trip (conservative for ₹5L+ NiftyBees orders).
- [ ] For all three strategies: equity curve vs buy-and-hold (single chart, both lines), drawdown chart, summary (total return, CAGR, max DD, Calmar, time-in-market %, round-trip count).
- [ ] **Gate:** Internally consistent (no NAV jumps on non-rebalancing days, cash return applied correctly, costs deducted at each round-trip). Visual inspection: equity curve tracks buy-and-hold during bull periods, diverges positively during corrections.

#### 2.I3 — CODE + STRATEGY — Walk-forward + validation (sequential: SMA → Dual Momentum → PE Band)

- [ ] 36-month training window, 12-month step (modified from swing's 252-day/63-day — monthly signals need longer windows).
- [ ] Thresholds per `INVESTMENT_STRATEGY_RESEARCH.md §Part 3` (relaxed vs swing): OOS Calmar ≥0.3, >50% windows net-positive, MC 95th DD <2× observed max DD, parameter plateau width ≥2 steps.
- [ ] **Buy-and-hold comparison mandatory:** strategy must demonstrate either (a) higher Calmar/Sharpe, OR (b) >30% reduction in max drawdown with ≤20% return underperformance. Neither condition → abandon regardless of other metrics.
- [ ] **Gate per strategy:** validation report (equity curve, allocation log, MC distribution chart, parameter sensitivity heatmap, regime decomposition table, buy-and-hold comparison); human review and sign-off.

#### 2.I4 — STRATEGY — Paper trading

**Owner: Animesh. Not for Cowork.**

- [ ] Minimum 6 months (2 rebalance events). Extend to 12 months if 2 events are statistically insufficient.
- [ ] Strategy name prefix: `paper_invest_<strategy>_v1` (e.g., `paper_invest_sma_v1`).
- [ ] On each monthly check day: record signal value (SMA level, momentum return, PE value), allocation decision, NiftyBees NAV at decision time.
- [ ] **Gate:** Allocation decisions match what the signal generator would produce on live data (verify by running generator on live data and comparing). Execution slippage ≤ ₹0.50/unit.

#### 2.I5 — STRATEGY — Live deployment

**Owner: Animesh. Not for Cowork.**

- [ ] Start with ₹5L NiftyBees allocation under the validated strategy. No explicit scaling rule — allocation % governs sizing automatically.
- [ ] Quarterly review: compare actual allocation changes and returns to backtest envelope.
- [ ] Live kill criteria: trailing 12-month Calmar <0.2 → review; 2 consecutive back-to-back whipsaws → pause and compare to backtest whipsaw frequency; >6 allocation changes in any 12-month period → signal degraded, suspend.

---

# Phase 3 — IC Live + Third Strategy + Portfolio Construction

**Objective:** CSP and IC running live, add a third strategy (event-driven), introduce portfolio-level thinking (correlations, regime-aware sizing).

**Duration target:** ~12 months.

---

## 3.1 — STRATEGY — Deploy IC v1 live

**Owner: Animesh.**

- [ ] 1 lot. No scaling for 3 months minimum. Runs in parallel with CSP.
- [ ] Separate bucket of capital — do not share margin allocation between strategies until Phase 3.4 portfolio construction.

---

## 3.2 — STRATEGY — Third strategy specification (event-driven calendar)

**Owner: Animesh.**

- [ ] Candidate: calendar spread entered 1 trading day before RBI policy / budget / major earnings, exited 1 trading day after. Monetises IV crush asymmetry.
- [ ] Write `docs/strategies/calendar_event_v1.md`. Validator passes.
- [ ] Low frequency (6–10 trades/year) so variance checking needs a longer window — note this in the spec (variance window = 18 months, not 4 months).

---

## 3.3 — CODE — Event calendar + calendar spread strategy

- [ ] `src/market_calendar/events.py` — RBI policy dates, Union Budget date, major earnings dates. YAML-driven like `holidays.py`. Annual refresh same ritual.
- [ ] `src/strategy/calendar_spread.py` — strategy implementation matching spec.
- [ ] Tests for both modules.
- [ ] Backtest over history; document results.
- [ ] Paper trade for ≥18 months (one full annual cycle plus buffer) before considering live.

---

## 3.4 — CODE — Portfolio-level attribution

- [ ] Extend `PortfolioSummary` to support strategy-level breakdowns across CSP + IC + calendar.
- [ ] New table `strategy_daily_pnl`: `(strategy_name, date, unrealized, realized, capital_deployed, margin_used)`.
- [ ] Correlation matrix computation: `src/portfolio/correlation.py`, pairwise rolling 90-day correlation across active strategies.
- [ ] Alert if any pairwise correlation > 0.8 for 4 consecutive weeks (concentration risk).
- [ ] Tests.
- [ ] Commit: `feat(portfolio): strategy-level attribution and correlation`.

---

## 3.5 — CODE — Regime classifier (rule-based, not ML)

**Overlap with Track A (2.S1):** The swing strategy pipeline builds a regime engine in 2.S1 (`src/strategy/regime.py`) using trend slope (50D regression / ATR) × VIX percentile (252D) — a 3×3 grid already tagging all historical trading days. Phase 3.5's classifier adds IV-based dimensions (IVR, IVP, realised vol) on top of that directional/vol framework. When building 3.5, evaluate whether `src/strategy/regime.py` (Track A) can be extended with IV dimensions rather than creating a parallel module. One consolidated `src/regime/` module with pluggable dimension sets is architecturally preferred over two independent classifiers with overlapping VIX logic. Confirm with the code-reviewer agent that the consolidation does not break Track A signal generators before merging.

- [ ] `src/regime/` module. Features: IV rank (IVR), IV percentile (IVP), trailing realised vol, VIX level, trend strength (20D SMA slope). Pure computation from existing `daily_snapshots` + option chain snapshots.
- [ ] Classifier outputs one of: HIGH_IV (IVR > 50), MID_IV (30–50), LOW_IV (< 30) — with separate TRENDING/RANGING overlay.
- [ ] This is a **measurement**, not a **prediction**. Record it daily. Do not use it for trade decisions yet — Phase 4 concern.
- [ ] Tests.
- [ ] Commit: `feat(regime): rule-based classifier`.

---

## 3.6 — GATE — End of Phase 3

- [ ] 3 strategies live, each ≥6 months, each within backtest envelope.
- [ ] Portfolio attribution operational.
- [ ] Regime classifier recording daily observations for ≥3 months (needed before Phase 4 can use it as an allocation signal).

---

# Phase 4 — Basket Maturity + Finideas Evaluation

**Objective:** Basket of 3–5 validated strategies. Explicit keep-or-exit decision on Finideas backed by ≥2 years of tracked realised data. Optional ML overlays for narrow problems only.

**Duration target:** 2028–2030.

---

## 4.1 — STRATEGY — Finideas evaluation

**Owner: Animesh. This is the big delayed decision from the earlier conversation.**

- [ ] Prerequisites: ≥24 months of Finideas tracked realised P&L in the system, with inception P&L, drawdown depth, and max intra-year drawdown all measurable.
- [ ] Benchmark candidates (compute each over the same window):
  - 60% Nifty index fund + 40% liquid debt (passive benchmark).
  - CSP + IC basket (your own strategies, net of costs).
  - Finideas net of their subscription fee.
- [ ] Decision framework:
  - If Finideas is within ±2% annualised of the best alternative: exit. The complexity isn't worth it.
  - If Finideas is +3% or more above the best alternative: stay subscribed.
  - If Finideas is between +2% and +3%: stay 6 more months, re-evaluate.
- [ ] Document decision and rationale in `docs/decisions/finideas_evaluation_YYYY-MM.md`.

---

## 4.2 — STRATEGY — Fourth / fifth strategies (as maturity allows)

**Owner: Animesh.**

- [ ] Candidates: short strangle (regime-conditional — HIGH_IV only), ratio spread, jade lizard. One per year maximum.
- [ ] Each goes through the full Phase 0–2 pipeline (spec → paper → backtest → variance check → live). No shortcuts.

---

## 4.3 — CODE — ML overlays (narrow scope only)

- [ ] Optional. Build only if a specific, narrow problem emerges that rule-based code cannot handle. Candidates:
  - **Vol surface arb detection:** Identify strikes where IV is mispriced relative to the surface. Input: daily option chain snapshots. Output: alerts on strikes >2 SD from fitted surface.
  - **Slippage prediction:** Predict execution slippage as a function of order size, strike distance from ATM, time of day. Train on realised fills.
- [ ] Do not attempt: direction prediction, strategy generation, regime prediction. Those are traps covered earlier in the conversation.
- [ ] Each ML feature ships with its own spec, backtest, paper-trade validation, and kill criteria.

---

## 4.4 — GATE — Plan closure

- [ ] 3–5 strategies in the live basket, each with ≥1 year of realised data within envelope.
- [ ] Finideas decision made and documented.
- [ ] Realised annualised return on the basket: honestly measured, benchmarked, and shared with no adjustments in `docs/decisions/basket_performance_YYYY.md`.
- [ ] Kill criteria triggered at least once on at least one strategy — and handled cleanly. (If never triggered, either you got lucky or the kill criteria are too loose.)

---

# Cross-Cutting Rules (apply to every phase)

## Code quality

- Every code task ends with: `python -m pytest tests/unit/` green + `code-reviewer` agent clean + `CONTEXT.md`/`DECISIONS.md`/`TODOS.md` updated + commit in `<type>(<scope>):` format.
- Google Python Style rules (`REVIEW.md` Part III) apply to every new or modified line. The tech-debt items TD-1 through TD-7 in `TODOS.md` get cleaned up opportunistically when touching adjacent code.
- No `@staticmethod`, no vertical alignment, no `assert` in `src/`, no f-strings in logger calls, 80-char lines, intent comments on broad `except`.
- `Decimal` everywhere for money. Floats from APIs get `Decimal(str(x))` at the boundary.
- `codebase-memory-mcp` before `Read`. `git log` before asking "why does this code look like this?".

## Strategy discipline

- One new strategy per year, maximum.
- Do not scale a strategy for the first 3 months of live trading, regardless of profitability.
- Write kill criteria before going live, not after.
- Spec documents are code contracts — if the code diverges from the spec, one of them is wrong.
- Post-mortem every strategy that dies AND every strategy that graduates to live. Write what you learned about the market and about yourself.

## Risk sizing (from conversation)

- Max deployed on any single strategy: 25% of total capital.
- Max deployed across all open positions: 50% of total capital.
- Max loss per trade: ≤ 2% of total capital.
- These are hard caps, not targets. Reduce, never expand, during drawdown.

## Variance monitoring thresholds

- Rolling 3-month Z-score of realised vs backtest: alert if |Z| > 1.5 for 3 consecutive weeks.
- Monthly: reconcile live trades against backtest predictions for the same month. Divergence > 1 SD investigated, > 2 SD reviewed with the `code-reviewer` and `options-strategist` agents.

## Kill triggers (global)

Any of these triggers a pause on the affected strategy, not the whole system:

- Trailing 6-month realised return < 0% for that strategy.
- Max drawdown > 10% of deployed capital for that strategy.
- |Z| > 2 for 4 consecutive weeks.
- Three consecutive execution errors (missed roll, wrong-side fill, fat finger).

When triggered: stop new entries immediately, close existing positions according to the strategy's normal exit rules (not panic-close), post-mortem, decide keep/modify/kill within 30 days.

---

# Completion Log

*Cowork: append a line here after each task is ticked, with date, task ID, commit SHA. Append-only — do not edit historical entries.*

| Date | Task | Commit SHA | Notes |
|---|---|---|---|
| 2026-04-24 | 0.1 | cd3ed6b | 174 nuvama tests across test_models (32), test_options_reader (26), test_store (43) + supporting files. Follow-up fix 92a6c74. Status gap closed retroactively. |
| 2026-04-25 | 0.4 | fb69043 | CSP v1 spec written: docs/strategies/csp_niftybees_v1.md. All required sections present: entry/exit/adjustment/sizing/prior P&L distribution/regimes/kill criteria/variance threshold. Open questions for v2 logged. |
| 2026-04-25 | 0.5 | 5ccfc52 | Paper trading module: src/paper/ (models, store, tracker), scripts/record_paper_trade.py, daily_snapshot.py wiring. 65 new tests, 948 total. |
| 2026-04-26 | 0.4a | 88dc95e | NiftyShield integrated strategy spec: docs/strategies/niftyshield_integrated_v1.md. CSP + put spread (4 lots, 8–20% OTM) + tail puts (2 lots, 5-delta quarterly). Validator passes. |

---

# Open Questions for Animesh

These need a decision from the human operator before the relevant phase starts. Cowork: do not guess; surface these and wait.

- **Phase 0.4:** Is the strategy CSP on NiftyBees, or do you want to start with a different first paper strategy?
- **Phase 1.1 — RESOLVED (2026-04-17):** DhanHQ Data API confirmed to offer 5 years of 1-minute expired options data (rollingoption endpoint) for both index and stock options. Does not cover COVID crash (Mar 2020); best stress data available is Jun 2024 election day. ₹400/month.
- **Phase 1.1 — STILL OPEN:** What is Dhan's definition of "nearing expiry" for the rollingoption ATM±10 strike window? (ATM±3 applies to "all other contracts".) Needs confirmation from Dhan support or a trial API call before the iron condor strategy design is locked. If the window is <7 DTE only, 30–45 DTE IC backtests are impossible and the Phase 2 strategy pipeline must adapt. **Note:** This is a historical-endpoint limitation only. The live `/v2/optionchain` endpoint (used in 1.10) returns all strikes for any expiry.
- **Phase 1.6a — RESOLVED (2026-04-17):** Option A chosen — Black-Scholes from stored IV for historical backtest. Known delta drift vs Dhan live Greeks documented as an expected bias in the 1.11 variance check.
- **Phase 1.6a:** Risk-free rate for Black-Scholes Greeks — defaulting to 7% (current Indian regime). Revisit if RBI policy shifts materially during Phase 1. Revisit also after 1.10 snapshots accumulate — `r` can be empirically calibrated to minimise RMS delta error vs Dhan's reported deltas.
- **Phase 1.10 — RESOLVED (2026-04-17):** Live Greeks source switched to Dhan `/v2/optionchain` (Greeks, IV, bid/ask, OI in one response; 1 req / 3 sec rate limit). Upstox retained as documented fallback. Live chain snapshot cron starts in Phase 1 (3:30 PM IST, before daily_snapshot) to accumulate forward-captured Greeks + bid/ask for calibration and Phase 3 strategy needs.
- **Phase 1.10:** Confirm `UnderlyingScrip` security IDs for NIFTYBEES (Nifty 50 is `13`, already known from Dhan docs). Look up via Dhan instrument list and record in `REFERENCES.md` before 1.10 CLI runs.
- **Phase 2.2:** Is static IP provisioned by the time CSP is ready to go live? If not, plan for manual order placement + `record_trade.py` ledger capture.
- **Phase 4.1:** What's the acceptable "Finideas is worth its fee" spread vs benchmark? The plan uses ±2% / +3% / middle-zone; this is the author's suggestion, not a hard rule.
- **Phase 3.2 vs Track A swing strategies — UNRESOLVED:** `BACKTEST_PLAN.md §3.2` specifies an "event-driven calendar spread" (RBI policy / budget / major earnings, entered 1 day before, exited 1 day after) as the third Phase 3 strategy. `docs/plan/SWING_STRATEGY_RESEARCH.md` defines three different strategy candidates (Donchian Channel, ORB, Gap Fade) that run through a separate research pipeline (Phase 2 Track A) producing 0–3 validated live strategies after Phase 1.12. These were designed independently and now conflict. **Decision required before Phase 3 begins:** Does the calendar spread (§3.2) (a) **replace** whichever swing strategy fails validation — making it the fallback third live strategy if Track A yields fewer than 3 survivors; or (b) become a **fourth strategy** that enters Phase 3 alongside Track A graduates? If (b), the "one new strategy per year" Cross-Cutting Rule applies and the Phase 3 timeline must be extended accordingly. Cowork: do not resolve — surface and wait.

---

*End of plan. This file is append-only for the Completion Log and checkbox state. Structural edits go through a normal code review like any other file.*

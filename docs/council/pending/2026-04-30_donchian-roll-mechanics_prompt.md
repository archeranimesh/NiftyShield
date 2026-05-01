=== NIFTYSHIELD PROJECT STATE ===

# NiftyShield — Project Context

> **For AI assistants:** This file is the authoritative state of the codebase.
> Read this before writing any code. Do not rely on session summaries or chat history.
> Repo: https://github.com/archeranimesh/NiftyShield

**Related files:** [DECISIONS.md](DECISIONS.md) | [REFERENCES.md](REFERENCES.md) | [TODOS.md](TODOS.md) | [PLANNER.md](PLANNER.md) | [BACKTEST_PLAN.md](BACKTEST_PLAN.md) — phased backtest → paper → live plan | [LITERATURE.md](LITERATURE.md) — concept reference (Kelly, Sharpe, meta-labeling) | [docs/plan/](docs/plan/) — one story file per task | [INSTRUCTION.md](INSTRUCTION.md)
---

## Current State (as of 2026-04-27)

### What Exists (committed and working)

Full file-level module tree: **[CONTEXT_TREE.md](CONTEXT_TREE.md)**
Load that file when adding new modules or doing a full structural survey.
For task work, use the graph: `search_graph`, `get_code_snippet`, `trace_path`.

Key top-level packages: `src/auth`, `src/client`, `src/models`, `src/portfolio`, `src/paper`, `src/mf`, `src/dhan`, `src/nuvama`, `src/instruments`, `src/market_calendar`, `src/notifications`, `src/utils`, `src/db.py`

`src/models/options.py` — `OptionLeg`, `OptionChainStrike`, `OptionChain` (all `frozen=True` Pydantic). Source-agnostic field names; Upstox parser in `src/client/upstox_market.py` (`parse_upstox_option_chain`). Dhan parser deferred to Phase 1.10.
`src/paper/` — paper trading module. `PaperTrade` model (frozen Pydantic, `paper_` prefix enforced), `PaperPosition` + `PaperNavSnapshot` (frozen dataclasses), `PaperStore` (`paper_trades` + `paper_nav_snapshots` tables in shared SQLite), `PaperTracker` (compute_pnl + record_daily_snapshot). See `src/paper/CLAUDE.md` for module invariants.
Scripts: `daily_snapshot.py`, `morning_nav.py`, `nuvama_intraday_tracker.py`, `seed_*.py`, `record_trade.py`, `record_paper_trade.py` (supports `--underlying/--strike/--option-type/--expiry` auto-lookup via BOD JSON), `paper_snapshot.py` (standalone paper mark-to-market), `roll_leg.py`

### What Does NOT Exist Yet

- `src/nuvama/CLAUDE.md` — module context file not yet written
- `src/strategy/`, `src/execution/`, `src/backtest/`, `src/risk/`, `src/streaming/` — all empty (planned per BACKTEST_PLAN.md Phase 1–2)

### Live Data

- SQLite DB path confirmed: `data/portfolio/portfolio.sqlite`
- DB wiped clean on 2026-04-04 (`daily_snapshots`, `mf_transactions`, `mf_nav_snapshots` all cleared)
- `mf_transactions` re-seeded with all 11 schemes using correct AMFI codes
- `mf_nav_snapshots` empty — first clean snapshot on Monday 2026-04-06 (pre-market run)
- `daily_snapshots` empty — first clean baseline on Monday 2026-04-06 (pre-market run)
- `underlying_price` will populate from 2026-04-06 onwards
- Greeks columns are null across all snapshots
- `trades` table seeded 2026-04-08 — 7 rows: finideas_ilts (6 legs including LIQUIDBEES) + finrakshak (1). EBBETF0431 net=465 @ avg ₹1388.01. **strategy_name migrated 2026-04-08:** `ILTS` → `finideas_ilts`, `FinRakshak` → `finrakshak` to match strategies table. Must use DB strategy names in all future `record_trade.py` calls.
- `nuvama_intraday_snapshots` logging active on 2026-04-17 (30-day retention loop engaged automatically).
- Cron jobs set up: `45 15 * * 1-5` for daily EOD options recording, plus `*/5 9-15 * * 1-5` for intraday extremes monitoring.

---

## Key Decisions

Architecture decisions, rationale, and deferred items: **[DECISIONS.md](DECISIONS.md)**
Instrument keys, AMFI codes, API quirks, auth tokens: **[REFERENCES.md](REFERENCES.md)**

---

## Current Constraints

| Constraint | Workaround |
|---|---|
| Order execution blocked (static IP required) | MockBrokerClient for all order dev/testing |
| Expired Instruments API blocked (paid tier) | NSE option chain CSV dumps as interim backtest source |
| Greeks columns in DB | Populated from 2026-04-25 onwards via `_fetch_greeks()` + `parse_upstox_option_chain` |
| `underlying_price` null for pre-2026-04-06 snapshots | DB wiped; clean baseline starts Monday |
| Upstox has no MF API | AMFI flat file as sole NAV source; MF holdings managed via seed script + monthly SIP inserts |
| MF NAV at 3:45 PM cron is T-1 | Expected for MFs — AMFI publishes after market close. Combined summary shows mixed-timestamp data by design. |
| Day-change P&L | **Implemented** — Δday shown in combined summary from 2026-04-07 |

---

## Pre-Task Protocol (for AI assistants)

Before writing any code: read `CONTEXT.md`, state `CONTEXT.md ✓`, confirm scope, state plan. See `CLAUDE.md` for full protocol.
- Architecture decisions or new modules: also read `DECISIONS.md`
- Instrument keys, market data, AMFI codes: also read `REFERENCES.md`
- Starting new feature work: also read `TODOS.md` + `PLANNER.md`
- Working on backtest, paper trading, strategy research, or any task tagged Phase 0-4: also read `BACKTEST_PLAN.md`. Tick `[x]` only when the task's DoD is fully met and the commit has landed. Do not skip phase gates.
- Working in a `src/` module: that module's `CLAUDE.md` loads automatically

## Immediate TODOs

Open work and priority order: **[TODOS.md](TODOS.md)**.

---

## Strategy Definitions

Strategy leg tables (instrument keys, entry prices, quantities, protected MF portfolio) are in **[REFERENCES.md](REFERENCES.md)**.

---

## Test Coverage

- **Total: ~976 tests** (976 passing; 1 pre-existing `test_lookup.py` rapidfuzz/difflib delta — unrelated to recent changes)
- Run: `python -m pytest tests/unit/`
- Auth tests: `tests/unit/auth/` (64 tests — Nuvama login + verify, Dhan login + verify)
- MF tests: `tests/unit/mf/` (127 tests)
- Portfolio tests: `tests/unit/portfolio/` + `tests/unit/test_portfolio.py` (94+ tests — includes 4 record_roll store tests + 10 _build_trades script tests)
- Client tests: `tests/unit/test_client.py`, `test_protocol.py`, `test_exceptions.py`, `test_factory.py`, `test_mock_client.py`, `test_upstox_live.py` (90+ tests)
- Snapshot tests: `tests/unit/test_daily_snapshot_historical.py`, `test_daily_snapshot_helpers.py`, `test_notifications.py` (50+ tests)
- Dhan tests: `tests/unit/dhan/` (90 tests — models, reader, store, daily_snapshot integration)
- Nuvama tests: `tests/unit/nuvama/` (163 tests — bond models, bond store, reader, seed, **NuvamaOptionPosition + NuvamaOptionsSummary models (AR-3), parse_options_positions + build_options_summary (AR-3), record_all_options_snapshots atomic (AR-7), record_intraday_positions, get_intraday_extremes, purge_old_intraday (AR-3)**; test_portfolio_summary_nuvama.py deleted — superseded by composed model structure)

---

## Session Log

Full session log has moved to **[TODOS.md](TODOS.md)**.


=== ADDITIONAL CONTEXT: SWING_STRATEGY_RESEARCH.md ===

# NiftyShield — Swing Strategy Research Pipeline

| Field        | Value                                                     |
|--------------|-----------------------------------------------------------|
| Author       | Animesh Bhadra (archeranimesh)                            |
| Date         | 2026-04-27                                                |
| Status       | Draft — pending Phase 0 gate (BACKTEST_PLAN.md §0.8)      |
| Signal source| Nifty 50 Index spot (`NSE_INDEX|Nifty 50`)                |
| Regime filter| India VIX (`NSE_INDEX|India VIX`, Dhan: security ID `25`) |
| Execution    | Nifty index options — vertical spreads + iron condors     |
| Data sources | Upstox (live candles, VIX), DhanHQ (expired options, Tier 2) |

> **Purpose:** Research plan for 3 rule-based directional/neutral swing strategies on Nifty 50
> Index. Signals are generated from spot OHLC + VIX. Execution uses defined-risk option spreads,
> not naked positions or futures. Each strategy maps to a specific spread type depending on
> the signal direction and the VIX regime. Backtesting uses a two-tier approach: Tier 1 (Nifty
> points, always available) validates signal quality; Tier 2 (option spread P&L) validates the
> execution layer when historical option data is available.
>
> **Relationship to BACKTEST_PLAN.md:** This plan runs *inside* the backtest engine built in
> Phase 1 of BACKTEST_PLAN.md. The CSP strategy (Phase 0) is the calibration strategy — its
> paper-trade → backtest variance check validates the engine. The strategies in *this* document
> are the payload that engine will eventually process. Do not start this work until Phase 1
> gate (§1.12) is passed.
>
> **Companion document:** [INVESTMENT_STRATEGY_RESEARCH.md](INVESTMENT_STRATEGY_RESEARCH.md)
> — 3 long-term (>1 year) systematic allocation strategies on NiftyBees ETF. Separate capital
> pool, separate validation thresholds, shared backtest engine infrastructure.
>
> **Prerequisite reading:** `BACKTEST_PLAN.md` (engine architecture), `CONTEXT.md` (codebase
> state), `REFERENCES.md` (instrument keys, DhanHQ data constraints).

---

## Design Constraint: Why Spreads, Not Futures

Futures require continuous position management, overnight margin, and expose the full notional
to gap risk. Defined-risk spreads cap loss at the spread width minus premium collected (credit
spreads) or premium paid (debit spreads). For a retail operator running this alongside an
existing Finideas portfolio and ₹1.2 cr+ collateral pool, capital efficiency and max-loss
predictability matter more than the theoretical purity of a futures backtest.

The tradeoff: option spreads introduce IV sensitivity, bid-ask slippage on 4-leg structures
(iron condors), and theta decay as a profit/cost component that doesn't exist in a futures
backtest. The backtest must model these — see §Implementation Stage 3.

**Execution mapping:**

| Signal direction | VIX regime    | Spread type          | Max loss            |
|-----------------|---------------|----------------------|---------------------|
| Bullish         | Normal/High   | Bull put spread (credit) | Spread width − credit |
| Bullish         | Low           | Bull call spread (debit) | Premium paid        |
| Bearish         | Normal/High   | Bear call spread (credit)| Spread width − credit |
| Bearish         | Low           | Bear put spread (debit)  | Premium paid        |
| Neutral         | Normal/High   | Iron condor (credit)     | Wider leg width − net credit |
| Neutral         | Low           | Skip — edge too thin     | —                   |

**Why credit spreads in normal/high VIX and debit in low VIX:** When VIX is elevated, option
premiums are rich — selling spreads captures inflated premium with a statistical tailwind
(realised vol typically undershoots implied during mean-reversion from VIX spikes). When VIX
is low, premiums are thin and selling offers poor risk/reward; buying a debit spread costs
less and benefits if the directional move materialises with any vol expansion.

The neutral/low-VIX "skip" is deliberate: iron condors in low-vol environments collect tiny
premiums relative to their spread width, making the risk/reward structurally negative. The
premium collected on a 200-point-wide Nifty iron condor at VIX 11 is roughly ₹3,000–4,000
per lot against a max loss of ₹9,000–10,000. Not worth the operational overhead.

---

## Part 1 — Strategy Selection

### Strategy 1: Donchian Channel Trend Following

**Core hypothesis:** Nifty exhibits sustained directional trends lasting 3–12 weeks, driven
by FII flow cycles, RBI rate decisions, global risk-on/off rotations, and election/budget
macro events. These trends persist because Nifty's participant structure — FII directional
flow on one side, retail and DII absorption on the other — creates momentum that takes weeks
to exhaust. A channel breakout on daily bars captures the initiation of these trends.

**Signal source:** Nifty 50 Index daily close vs. N-day high/low channel.

**Timeframe:** Daily bars. Not 60-min — sub-daily channel breakouts on Nifty are noise-
dominated and add false signals without improving trend capture. Not weekly — too slow to
catch 3-week trends and generates too few trades for statistical validation in 5 years.

**Parameters (3):**

| Parameter                | Initial | Sweep range | Step |
|--------------------------|---------|-------------|------|
| Channel lookback (N days)| 40      | 20–60       | 5    |
| ATR trailing stop mult.  | 3.0     | 2.0–4.5     | 0.5  |
| ATR lookback (days)      | 20      | 14, 20      | —    |

**Entry:** Go long (bull spread) when daily close > N-day high channel. Go short (bear spread)
when daily close < N-day low channel. Always-in system — a new breakout in the opposite
direction triggers exit of the current spread and entry of a new one.

**Exit:** Trailing stop at entry price ± (ATR multiplier × current ATR). Recalculated daily.
When stop triggers, close spread and wait for next channel breakout (no immediate reversal
on stop — only on a fresh channel break).

**Spread sizing:** Enter the spread on the signal day's close. Strike selection: short strike
at the nearest 15-delta option, long strike 200 points further OTM (credit spreads) or short
strike ATM ± 100, long strike 200 points further OTM (debit spreads). Monthly expiry, 30–45
DTE at entry. If the signal triggers within 14 DTE of the nearest monthly, use the *next*
monthly.

**Works in:** Sustained FII-driven trends (2021 H1 bull run, 2022 H1 correction, 2023
recovery, 2024 post-election rally). Nifty has spent roughly 55–60% of the last 5 years in
trending regimes — above average for a major index and the structural foundation of this edge.

**Fails in:** Choppy consolidation ranges. 2022 H2 (16000–18500 for months) is the canonical
failure period. Also fails during sharp V-reversals where the trailing stop exits at the worst
moment. Budget-week and election-week whipsaws can generate consecutive losing round-trips.

---

### Strategy 2: Opening Range Breakout (ORB) with Volatility Filter

**Core hypothesis:** The first 30 minutes of Nifty trading (9:15–9:45) absorb overnight
information — GIFT Nifty gap, Asian open, US close — through concentrated institutional order
flow. When the opening range (OR) is narrow relative to recent volatility, the market hasn't
chosen a direction yet. A breakout from this compressed range carries directional conviction
because it represents the resolution of overnight uncertainty. The compression filter is where
the edge concentrates — unfiltered ORB on Nifty is break-even at best.

**Signal source:** Nifty 50 Index 15-min candles (first N candles define the OR), filtered by
14-day ATR on daily bars.

**Timeframe:** 15-min bars for the opening range. Daily ATR for the volatility filter.

**Parameters (3):**

| Parameter                           | Initial | Sweep range | Step |
|-------------------------------------|---------|-------------|------|
| Opening candle count (15-min bars)  | 2       | 1–3         | 1    |
| Max OR width (fraction of 14d ATR)  | 0.6     | 0.3–0.8     | 0.1  |
| Risk-reward target multiple         | 1.5     | 1.0–2.5     | 0.5  |

**Entry:** Compute OR = high − low of first N 15-min candles. If OR < (filter × 14-day ATR),
the day qualifies. Go long (bull spread) on break above OR high. Go short (bear spread) on
break below OR low. One entry per direction per day. The spread is entered on the breakout
candle's close, not intraday — no live execution required.

**Exit:** Target at entry ± (R:R multiple × OR width). Hard close at 15:15 IST if target not
hit. This is strictly intraday — no overnight carry. Spread expiry is the nearest weekly
(Thursday expiry), giving 0–4 DTE. Use weekly options, not monthly, to minimise premium cost
on what is a same-day directional bet.

**Structural filter:** Exclude weekly expiry days (Thursday) from the universe entirely. Weekly
options expiry creates artificial pinning and two-way chop that systematically destroys ORB
entries. This is not an optimisation — it is a structural exclusion.

**Works in:** Trending days following overnight gaps, post-event days (RBI, Fed, earnings
season). Approximately 40–50% of Nifty trading days show a clean directional move from the
opening range.

**Fails in:** Expiry days (excluded). Gap days where the gap *is* the move and the OR just
consolidates. Days where the OR is wide (high-ATR-fraction filter catches this).

**Assumption to verify:** Confirm whether Upstox 15-min candles at 9:15 include the pre-open
auction match price or only regular-session trades. This changes OR calculation significantly.
Also verify that DhanHQ expired options data for weekly Nifty options covers the strikes needed
(ATM ± how many? — per BACKTEST_PLAN.md §1.1, coverage is ATM±10 near expiry, ATM±3 otherwise;
for weekly 0–4 DTE, ATM±10 should apply, but verify the "nearing expiry" cutoff).

---

### Strategy 3: Mean-Reversion Overnight Gap Fade

**Core hypothesis:** Nifty's open is driven by GIFT Nifty, which prices in US/Europe overnight
moves. Small-to-moderate gaps (0.3%–1.0% of previous close) are correlation-driven, not
information-driven, and domestic participants re-price independently during the session,
partially closing the gap. Large gaps (>1.0%) reflect genuine regime change and persist. The
strategy fades small gaps and ignores large ones.

This persists because the GIFT Nifty → NSE open arbitrage structure creates a systematic
opening dislocation that domestic institutional flow corrects within the first 2–3 hours.

**Signal source:** Nifty 50 Index daily open vs. previous daily close.

**Timeframe:** Daily bars for gap identification, 15-min bars for entry timing (enter after
the second 15-min candle, i.e., at 9:45, to let opening volatility settle).

**Parameters (3):**

| Parameter                              | Initial | Sweep range | Step |
|----------------------------------------|---------|-------------|------|
| Min gap size (% of prev close)         | 0.3%    | 0.2%–0.5%  | 0.1% |
| Max gap size (% of prev close)         | 1.0%    | 0.7%–1.5%  | 0.1% |
| Partial fill target (fraction of gap)  | 0.5     | 0.3–0.7    | 0.1  |

**Entry:** Gap-up > min and < max → short signal (bear spread). Gap-down > min and < max →
long signal (bull spread). Enter at the close of the second 15-min candle (9:45). Stop at the
session's high/low established in the first two candles. Weekly expiry options, 0–4 DTE.

**Exit:** Target at open ± (fill fraction × gap size). Hard exit at 12:30 IST — gap fills
that haven't happened by lunch rarely complete. Close spread at 12:30 regardless.


[... truncated at 200 lines — full file: SWING_STRATEGY_RESEARCH.md]

=== QUESTION FOR THE COUNCIL ===

The Donchian Channel Trend Following strategy (Strategy 1 in the attached SWING_STRATEGY_RESEARCH.md) is designed as an always-in system on Nifty 50 using monthly credit/debit spreads (30–45 DTE). Three specific design decisions need council review: (1) ROLL MECHANICS — when the ATR trailing stop fires mid-contract (say at 20 DTE remaining), the system must simultaneously close the existing spread and open a new directional spread at 30–45 DTE. What are the real-world cost and execution risk implications of this mid-contract roll on NSE, and is there a better exit architecture that preserves the always-in directional exposure without forcing a spread roll at sub-optimal DTE? (2) VIX REGIME SWITCHING — the execution table switches between selling credit spreads in normal/high VIX and buying debit spreads in low VIX. Does this dual-layer decision (directional signal + VIX regime) improve risk-adjusted return in practice, or does regime misclassification during VIX transitions (e.g., VIX moving from 19 to 21 across the 75th percentile threshold mid-trade) create a systematic execution noise problem? (3) SPREAD WIDTH — the plan uses a fixed 200-point spread width with the short strike at ~15-delta. At current Nifty levels (~23,000–24,000) and a 40-day ATR of ~350–500 points, is this spread width structurally sound, or should it scale dynamically with ATR to maintain consistent risk-reward across different volatility regimes?
# NiftyShield — TODOs

> Open work only. Completed items and session history through 2026-04-30:
> [docs/archive/TODOS_ARCHIVE_2026-05-01.md](docs/archive/TODOS_ARCHIVE_2026-05-01.md)

---

## Priority Key

| Label | Meaning |
|---|---|
| `P1-NEXT` | Do this sprint — unblocked, highest impact |
| `P2-EVAL` | Decision or evaluation required before any code |
| `P3-DEFER` | Explicitly deferred — reason and ETA documented |
| `P5-DEBT` | Technical debt — fix alongside adjacent refactoring only, never standalone |

---

## P1-NEXT — Define historical replay harness for exit-path validation

**Prerequisite for Phase 0.8 gate criterion B (delta/mark-stop and time-stop validation).**

When live paper trading doesn't produce a delta-stop or time-stop exit during the paper window, the council-approved alternative is a deterministic historical replay: run the production paper-trade code against a known stress episode (e.g., COVID week of 2020-03-16 or IL&FS week of 2018-09-21) injected into the staging environment.

**Scope (to design, not build yet — depends on Phase 1 backtest data pipeline):**
- Replay harness injects historical option chain snapshots into `PaperTracker` monitoring loop
- Must use the same strategy logic, data schema, cost model, and P&L attribution code as live paper
- Output: confirms monitoring daemon correctly identifies the trigger condition, queues the exit, and records P&L with correct attribution
- Do not build until Phase 1 NSE Bhavcopy pipeline (task 1.3) exists — historical chain data needed

**Owner:** Animesh + Cowork. Design doc first (`docs/plan/replay_harness.md`). No code until Phase 1 gate passes.

---

## P1-NEXT — India VIX ingestion for IVR calculation (blocks R3 enforcement)

**Prerequisite for Phase 0.8 gate criteria C and D (regime completeness + regime-matched Z-score).**

IVR (IV Rank) at entry is required to: (1) enforce R3 entry filter (IVR 25–50), (2) flag high-IVR regime cycles (IVR > 50) for criterion C, (3) filter backtest for regime-matched Z-score comparison in task 1.11. Currently, India VIX is not ingested — R3 enforcement and regime completeness checks are blocked.

**Scope:**
- Daily India VIX ingestion to Parquet (same pipeline as task 1.3a — confirm VIX is included there)
- 252-day rolling IVR calculation: `ivr = (vix_today - vix_252d_low) / (vix_252d_high - vix_252d_low)`
- Log IVR at entry for every paper trade record (add field to `PaperTrade` model or `paper_nav_snapshots`)
- Enable R3 gate enforcement in paper trading workflow

**Owner:** Cowork. Unblocks R3, criterion C, and task 1.11 regime-matched comparison.

---

## P1-NEXT — Stockmock calibration backtests (Animesh / STRATEGY)

**Prerequisite to Task 1.7** (hardcoded δ/IV/credit thresholds in `src/backtest/engine.py`).

Run CSP + IC backtests on Nifty options in Stockmock UI across four stress windows:
- IL&FS Sep–Oct 2018
- COVID Feb–Apr 2020
- 2022 bear (Jan–Jun 2022)
- Stable trending (Jan–Jun 2023)

Record results (max drawdown, Calmar, win rate, avg credit captured) in `docs/strategy/csp_nifty_v1.md` → section "Calibration Backtest Results (Stockmock)". These numbers become the empirical basis for 1.7 thresholds and 1.12 gate validation.

**Note:** User's decision document references `csp_niftybees_v1.md` — the canonical file is `csp_nifty_v1.md` (underlying changed from NiftyBees to Nifty 50 options per 2026-04-25 DECISIONS.md entry).

**Owner:** Animesh. No code required — manual UI workflow in Stockmock.

---

## P1-NEXT — NSE F&O Bhavcopy ingestion pipeline (`src/backtest/bhavcopy_ingest.py`)

Build the programmatic EOD options data pipeline. Unblocked — no paid data required.

**Scope:**
- `src/backtest/bhavcopy_ingest.py`: `download_bhavcopy(date) → Path`, `parse_bhavcopy(path) → pd.DataFrame`, `parse_option_symbol(symbol: str) → tuple[date, Decimal, str]`
- Output schema: `date DATE, symbol TEXT, underlying TEXT, expiry DATE, strike DECIMAL, option_type CHAR(2), open DECIMAL, high DECIMAL, low DECIMAL, close DECIMAL, volume BIGINT, oi BIGINT, settle_price DECIMAL`
- Parquet output path: `data/offline/options_ohlcv/{year}/{month}/`
- `scripts/bhavcopy_bootstrap.py`: resumable bulk download 2016-01-01 → today
- `src/backtest/bhavcopy_loader.py`: `load_options_ohlcv(underlying, start, end) → pd.DataFrame` (reads Parquet with pyarrow)

**Tests:** offline fixture-driven; no network in unit tests. One downloaded Bhavcopy CSV as fixture; test `parse_option_symbol` round-trips and edge cases (weekly vs monthly expiry symbol formats).

**Data source:** `https://www.nseindia.com/api/eodarchives?type=fo` — daily ZIP, contains `fo{DDMONYYYY}bhav.csv.zip`.

---

## P1-NEXT — `scripts/find_strike_by_delta.py`

Paper trading entry workflow: given an underlying + expiry, fetch the live option chain, filter strikes by a delta range, and print matching strikes with premium and instrument key — ready to pipe directly into `record_paper_trade.py`.

**Scope:**
- `scripts/find_strike_by_delta.py` — new script, no `src/` changes
- CLI: `--underlying NIFTY --expiry 2026-05-29 --option-type PE --delta-min -0.30 --delta-max -0.15 --expiry-date <today>` (defaults to today for spot)
- Uses `UpstoxLiveClient.get_option_chain()` + `parse_upstox_option_chain` (both exist in `src/client/upstox_market.py`)
- Output: table of matching strikes showing strike, delta, IV, bid, ask, LTP, instrument_key
- `--dry-run` prints the first match as a ready-to-run `record_paper_trade.py` command

**Dependencies already in place:** `OptionChainStrike` (delta/iv fields), `parse_upstox_option_chain`, `UPSTOX_ANALYTICS_TOKEN` in `.env`

**Tests:** offline fixture-driven (reuse `tests/fixtures/responses/nifty_chain_2026-04-07.json`); no new fixtures needed

---

## P2-EVAL — Nuvama Session P&L Alignment

Decision needed before any code changes.

Current `nuvama_intraday_tracker.py` shows "All-time Total P&L" — cumulative sum of all historical `realized_pnl_today` rows via `get_cumulative_realized_pnl()`. This diverges from the Nuvama mobile/web UI which shows "Session P&L" (Unrealized + Today's Realized only), causing a visible mismatch (e.g. system shows +17k, Nuvama shows -17k).

Options:
1. Keep cumulative — true inception P&L; diverges from Nuvama UI intentionally
2. Switch to session-only — matches Nuvama UI; cumulative history still in DB but not displayed

No implementation until Animesh chooses an option.

---

## P3-DEFER — P&L Visualization

Deferred until late May 2026 (need 4+ weeks of snapshot data).

Deliver as a **persistent Cowork artifact** (self-contained HTML page, re-opens with fresh data each session via live DB queries). Four independent panels, each independently viable:

### Panel 1 — Mutual Funds (MF)
- Source: `mf_nav_snapshots` (NAV history) + `mf_transactions` (cost basis: one INITIAL row per scheme with units + amount)
- Data available: 16 days (2026-04-03 → present), 11 schemes
- P&L formula: `(current_nav − avg_cost_per_unit) × units` per scheme per day
- Chart: cumulative rupee P&L curve per scheme + bar chart of current unrealized gain per scheme

### Panel 2 — Dhan ETFs
- Source: `dhan_holdings_snapshots` (avg_cost_price + ltp + total_qty per day)
- Data available: 9 days (2026-04-14 → present); NIFTYIETF (equity) + LIQUIDCASE (bond)
- P&L formula: `(ltp − avg_cost_price) × total_qty` — directly computable, no join needed
- Chart: daily P&L curve per instrument

### Panel 3 — Nuvama Bonds (NCDs, G-Sec, SGB)
- Source: `nuvama_holdings_snapshots` (current_value per ISIN per day) + `nuvama_positions` (static cost basis: avg_price × qty)
- Data available: 8 days (2026-04-15 → present); EFSL NCDs, G-Sec 8.28% 2027, SGB 2023-24
- P&L formula: `current_value − (qty × avg_price)` per ISIN per day
- Chart: daily mark-to-market P&L per bond instrument

### Panel 4 — Nuvama Options (own options book, not FinRakshak)
- Source: `nuvama_options_snapshots` (unrealized_pnl + realized_pnl_today per leg per EOD snapshot)
- Data available: 7 days (2026-04-16 → present); 23–38 open legs per day
- Caveat: closed legs disappear from subsequent snapshots; `realized_pnl_today` captures same-day closures only
- P&L formula: `SUM(unrealized_pnl)` for open legs + `SUM(realized_pnl_today)` cumulated over all historical dates
- Chart: daily total unrealized P&L + cumulative realized P&L line — strategy-level only, not per-leg

### Not yet possible — Zerodha (FinRakshak + ILTS)
- FinRakshak and ILTS both run on Zerodha. No Zerodha table in DB, no integration built. These strategies are a complete blind spot for visualization until Kite Connect is integrated (see P3-DEFER — Zerodha / Kite Connect Integration below).

### Implementation notes
- All four panels can share one artifact; data fetched via `mcp__workspace__bash` → Python → JSON on open
- Render with Chart.js or Recharts (both available in artifact sandbox)
- `PortfolioSummary` dataclass already extracted and queryable; `PLANNER.md` has broader context

---

## P3-DEFER — Zerodha / Kite Connect Integration

Deferred indefinitely — revisit when FinRakshak/ILTS P&L visibility becomes a priority.

FinRakshak and ILTS both run on Zerodha. Currently zero Zerodha data in the DB — positions, avg cost, and P&L for these two strategies are invisible to NiftyShield.

**Feasibility analysis (2026-04-24):**

Zerodha offers two tiers of Kite Connect API:

- **Personal (free):** `positions()`, `holdings()`, `orders()`, `funds()` — full portfolio state, no market data. Enough to capture holdings and avg cost price.
- **Paid (₹500/month):** Everything above + live LTP via REST (`ltp()`, `quote()`) and WebSocket tick streaming + historical candles.

For NiftyShield's use case the practical approach is a **hybrid**: Zerodha free API for position state (instrument, qty, avg cost) + existing Upstox Analytics token for LTP — the same pattern already used in `src/dhan/`. This avoids the ₹500/month charge while giving full P&L computation.

**Auth:** Kite Connect uses the same daily request-token → access-token flow as Upstox. A `src/zerodha/` module mirroring `src/auth/` would be needed, plus a morning login step.

**Implementation scope when ready:**
- `src/zerodha/` — auth + `KiteClient` implementing `BrokerClient` protocol (positions, holdings only; LTP delegated to Upstox)
- `zerodha_holdings_snapshots` table in SQLite (same shape as `dhan_holdings_snapshots`)
- `morning_nav.py` or new script to snapshot Zerodha positions at BOD
- Unblocks Panel 5 in P&L Visualization artifact (FinRakshak + ILTS)

**Note:** Zerodha also launched a **Kite MCP** server (2025) — could enable direct Zerodha queries inside Cowork sessions without building a custom client. Worth evaluating before writing `src/zerodha/` from scratch.

---

## P5-DEBT — Technical Debt

Fix alongside adjacent refactoring. Never worth a standalone commit.

### DEBT-3: Missing license boilerplate (TD-4)

License decision needed before this can be automated. Every file should carry a header once the license is chosen.

---

## Session Log

| Date | What Changed |
|---|---|
| 2026-05-03 | **Added `scripts/find_strike_by_delta.py`.** CLI: live option chain → filter strikes by |delta| range → fixed-width table (strike/IV/ltp/mid/bid/ask/OI/key) + `--dry-run` ready-to-paste `record_paper_trade.py` commands. Three importable helpers (`filter_strikes_by_delta`, `format_table`, `build_record_command`) + `_infer_leg`/`_safe_float`. Works directly on raw Upstox chain data to preserve `instrument_key` (stripped by the parsed `OptionChain` model). 30 offline unit tests in `tests/unit/test_find_strike_by_delta.py` using existing `nifty_chain_2026-04-07.json` fixture. |
| 2026-05-02 | **Council decision ingested — variance gate regime completeness.** Read `docs/council/2026-05-02_variance-gate-regime-completeness.md`; updated `DECISIONS.md` (new "Variance Gate" section — Z-score reframed as smoke test, graduated deployment tiers 0–3, regime completeness requirement, regime-matched Z-score mandate, spec consistency open issue); updated `BACKTEST_PLAN.md` Phase 0.8 gate (criteria A–D replacing single exit-type bullet) and Task 1.11 (dual Z-score: global + regime-matched); created `docs/plan/variance_gate.md` (full gate specification); added two P1-NEXT tasks to `TODOS.md` (replay harness + India VIX ingestion). No code changes. |
| 2026-05-02 | **Council decision ingested — near-expiry gamma buy research.** Read `docs/council/2026-05-02_gamma-acceleration-mispricing-option-buying.md`; updated `DECISIONS.md` with new "Signal Hierarchy Decisions — Near-Expiry Buy Research" section covering signal hierarchy (Gamma Gearing primary, Speed secondary, OI velocity confirmation), mispricing threshold formula, forward-test architecture, mandatory Phase 0 schema fields, Phase 3 prerequisites, and kill criteria. No code changes — data collection only until Phase 3 gate. |
| 2026-05-01 | **Root markdown cleanup.** Archived session log (2026-04-27 → 2026-04-30) to TODOS_ARCHIVE_2026-05-01.md; updated CONTEXT.md date + test count; synced README.md project structure. |

Full log (2026-04-01 → 2026-04-30): [docs/archive/TODOS_ARCHIVE_2026-05-01.md](docs/archive/TODOS_ARCHIVE_2026-05-01.md)

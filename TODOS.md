# NiftyShield — TODOs

> Open work only. Completed items and session history:
> - 2026-04-30 and earlier: [docs/archive/TODOS_ARCHIVE_2026-05-01.md](docs/archive/TODOS_ARCHIVE_2026-05-01.md)
> - 2026-05-01 to 2026-05-09: [docs/archive/TODOS_ARCHIVE_2026-05-10.md](docs/archive/TODOS_ARCHIVE_2026-05-10.md)

---

## Sequential Queue — Next 6 Months

Tasks 0–3 run in this order. Do not start the next until the current ships and tests are green.
Ongoing paper-trading tasks (Animesh) run in parallel and are listed separately below.

| # | Task | Owner | Hard Deadline | Status |
|---|---|---|---|---|
| **0** | Fix bhavcopy UDiFF format (Dec 2024+) | Cowork | ASAP | Unblocked |
| **1** | India VIX ingestion + IVR calculation | Cowork | Jun 2026 | Unblocked |
| **2** | PortfolioDeltaTracker (`src/risk/`) | Cowork | Jun 2026 | Unblocked |
| **3** | June 2026 Finideas roll cycle | Animesh + Cowork | **2026-06-30** | Awaiting Finideas instructions |

---

## Task 0 — Fix bhavcopy pipeline for NSE UDiFF format (Dec 2024+)

**Discovered 2026-05-03 during smoke test.** NSE migrated F&O bhavcopy to UDiFF format in
late 2024. Old URL and CSV schema only cover 2016 → ~Nov 2024. Full column mapping and fix
spec in `DECISIONS.md → "NSE Bhavcopy Format Migration"`.

**File to change:** `src/backtest/bhavcopy_ingest.py` only. No schema or model changes.

**Exact cutover date:** TBD. Confirmed working: `2024-04-25` (legacy). Confirmed broken:
`2024-12-02` (legacy). Binary search needed to pin the exact month boundary.

**Safe bootstrap range until fix ships:** `--end 2024-11-01`. Covers 2016–Oct 2024 (~8.5
years), including all critical stress windows: IL&FS Sep 2018, COVID Mar 2020,
rate-hike Jan–Jun 2022, Jun 2024 election day.

**Changes required:**

1. `download_bhavcopy`: try UDiFF URL first (`/content/fo/BhavCopy_NSE_FO_0_0_0_{YYYYMMDD}_F_0000.csv.zip`); fall back to legacy URL on 404.
2. `parse_bhavcopy`: detect format by checking `'TradDt' in reader.fieldnames`. Route to `_parse_legacy()` or `_parse_udiff()` accordingly. `BhavRecord` model unchanged.
3. `_parse_udiff()`: map UDiFF columns. Key differences: ISO date strings (no strptime); `FinInstrmTp` → instrument (`IDO`→OPTIDX, `STO`→OPTSTK, `IDF`→FUTIDX, `SDF`→FUTSTK); filter by `TckrSymb == underlying`.
4. Tests: add one UDiFF fixture row (NIFTY `IDO` option). Test format detection and routing.

---

## Task 1 — India VIX ingestion + IVR calculation

**Prerequisite for Phase 0.8 gate criteria C and D (regime completeness + regime-matched Z-score).**

IVR (IV Rank) at entry is required to: (1) enforce R3 entry filter (IVR 25–50), (2) flag high-IVR
regime cycles (IVR > 50) for criterion C, (3) filter backtest for regime-matched Z-score comparison
in task 1.11. Currently, India VIX is not ingested — R3 enforcement and regime completeness checks
are blocked.

**Scope (implements the VIX daily sub-path of BACKTEST_PLAN_PHASE1.md task 1.3a):**

- `src/backtest/ohlc_ingest.py` (or new `src/backtest/vix_ingest.py`): daily India VIX ingest from
  `NSE_INDEX|India VIX` via Upstox `/v2/historical-candle/` (free, existing `UPSTOX_ANALYTICS_TOKEN`).
  Store as Parquet: `data/historical/ohlc/india_vix/`. Resumable — skip dates already present.
- IVR formula: `ivr = (vix_today − vix_252d_low) / (vix_252d_high − vix_252d_low)`. Clamp to `[0.0, 1.0]`.
  Already implemented in `src/backtest/ivr.py` (`compute_ivr`) — wire at entry-log time.
- Log IVR at entry for every paper trade: add `ivr_at_entry: float | None` field to `PaperTrade` model
  or `paper_nav_snapshots` (confirm canonical location in `src/paper/CLAUDE.md` before changing schema).
- Enable R3 gate check in `scripts/record_paper_trade.py`: compute IVR from ingested data; warn (do not
  block) when IVR < 25 or > 50.
- Tests: VIX Parquet resumability (skip if already present); IVR boundary tests (already in `test_ivr.py`);
  R3 warning path in `record_paper_trade.py` (mock IVR fetch).

**Owner:** Cowork. Unblocks R3, criterion C, and BACKTEST_PLAN_PHASE1.md task 1.11 regime-matched comparison.

---

## Task 2 — PortfolioDeltaTracker (`src/risk/`)

**Source: `docs/council/2026-05-02_multi-strategy-portfolio-risk-allocation.md` §7.3.**

Cowork code task — unblocked. Implements the aggregate portfolio-delta guard that prevents net long bias
from compounding across all open paper positions and the NiftyBees ETF holding.

**Exact scope (from BACKTEST_PLAN.md task 0.6c):**

- `src/risk/__init__.py` — package stub with one comment line (required for codebase-memory-mcp indexing).
- `src/risk/models.py` — `PortfolioDelta` frozen dataclass: `options_delta_lots: Decimal`,
  `niftybees_delta_lots: Decimal`, `total_delta_lots: Decimal`, `warning_breached: bool`,
  `cap_breached: bool`, `as_of: datetime`.
- `src/risk/delta_tracker.py` — `PortfolioDeltaTracker`:
  - `aggregate_delta(paper_positions: list[PaperPosition], nifty_spot: Decimal, lot_size: int) → PortfolioDelta`
  - Options-only cap: +1.0 lots (warning +0.75). Options + NiftyBees cap: +2.0 lots (warning +1.5). Constants parameterised.
  - NiftyBees delta: `niftybees_qty × niftybees_ltp / (nifty_spot × lot_size)` (beta = 1.0).
- `src/risk/entry_gate.py` — `check_entry_allowed(current_delta: PortfolioDelta, trade_delta_lots: Decimal, is_protective: bool) → tuple[bool, str]`. Protective entries always `(True, "")`.
- Tests: `tests/unit/risk/test_delta_tracker.py` — happy path, warning boundary, hard cap breach,
  protective bypass, zero-position base case. `tests/unit/risk/__init__.py` required.
- `python -m pytest tests/unit/ --tb=no -q` green.
- Commit: `feat(risk): add PortfolioDeltaTracker with entry gate`.

**Owner:** Cowork. Unblocks the entry guard for 0.6b paper trades.

---

## Task 3 — June 2026 Finideas Roll Cycle

**Hard deadline: 2026-06-30** (NIFTY_JUN 23000 CE and PE legs expire, per `REFERENCES.md`).

Invoke `roll-validator` agent ≥1 week before deadline. Steps:

- [ ] Invoke `roll-validator` agent ≥1 week before 2026-06-30 to pre-check position state, Trade model integrity, and DB atomicity.
- [ ] Receive Finideas roll instructions (strike, expiry, quantity for each leg).
- [ ] Run `python -m scripts.roll_leg --dry-run ...` with all four `--old-*/--new-*` flags filled. Verify output.
- [ ] Run without `--dry-run`. Verify both Trade rows inserted atomically.
- [ ] Run `python -m scripts.daily_snapshot` same day. Confirm P&L continues uninterrupted; new JUL/SEP leg prices reflected in mark-to-market.
- [ ] Session log entry in `TODOS.md` with date, old/new instrument keys, and any anomalies.
- [ ] If any bug surfaces: file a separate fix commit before moving on.

**Owner:** Animesh (receives instructions) + Cowork (executes scripts).

---

## Ongoing Paper Trading (Animesh — parallel to Tasks 0–3)

These run continuously throughout Phase 0, independent of the code queue above.

### 0.6 — CSP v1 Paper Trading

- [ ] Each month at entry date: observe live chain, decide strike (22-delta target per `csp_nifty_v1.md`). Log via `record_paper_trade.py` with mid − 0.25 INR slippage haircut.
- [ ] Monitor daily via `daily_snapshot.py`. Log exit when profit target / time stop / loss stop hits.
- [ ] Never override the spec in real time. If urge to override: log it in `TODOS.md` with reason, then follow spec anyway.
- [ ] Minimum: **6 full monthly cycles (~6 months)**, with at least one cycle triggering each exit type.

### 0.6a — NiftyShield Integrated v1 Paper Trading

- [ ] At each CSP entry: also enter Leg 2 (put spread, 4 lots) via `--strategy paper_niftyshield_v1`.
- [ ] Each quarter (Jan/Apr/Jul/Oct): enter Leg 3 (tail puts, 2 lots).
- [ ] Leg 2 enters even when Leg 1 is skipped (R3/R4 filters) — protection is unconditional.
- [ ] Minimum: 6 monthly cycles for Legs 1+2; 2 quarterly cycles for Leg 3.

### 0.6b — 3-Track Nifty Instrument Comparison Paper Trading

**Unblocked (0.4b done 2026-05-03). Source: `docs/strategies/nifty_track_comparison_v1.md`.**

- [ ] Enter Spot base leg (long NiftyBees) via `--strategy paper_nifty_spot --leg base_etf`.
- [ ] Enter Futures base leg (long Nifty Futures notional) via `--strategy paper_nifty_futures --leg base_futures`.
- [ ] Enter Proxy base leg (Deep ITM Call, delta ≈ 0.90) via `--strategy paper_nifty_proxy --leg base_ditm_call`.
- [ ] For each approved overlay per track, record as a separate leg within the same strategy namespace.
- [ ] Do NOT record Futures + standalone Covered Call — blocked per council ruling.
- [ ] On each expiry: roll all base legs; document delta at roll time for Proxy.
- [ ] Minimum 6 monthly cycles before cross-track conclusions. Include ≥1 high-VIX event (India VIX >18).

### Stockmock Calibration Backtests (Animesh only — prerequisite for Phase 1.7)

Run CSP + IC backtests on Nifty options in Stockmock UI across four stress windows. No code required.

- [ ] COVID crash (Feb–Apr 2020): monthly CSP at 20-delta. Record strikes hit, premium, max M2M loss, breach frequency.
- [ ] IL&FS crisis (Sep–Oct 2018): same metrics.
- [ ] 2022 rate-hike selloff (Jan–Jun 2022): same metrics.
- [ ] Stable baseline (Jan–Dec 2023): establishes expected exit-type distribution in normal markets.
- [ ] Summarise in `docs/strategies/csp_nifty_v1.md` → "Calibration Backtest Results (Stockmock)" section.
- [ ] Commit: `docs(strategies): CSP v1 Stockmock calibration backtest results`.

**Note:** Canonical strategy file is `csp_nifty_v1.md` (underlying changed from NiftyBees to Nifty 50 per 2026-04-25 decision).

---

## Phase 1 — Backtest Engine (Aug–Dec 2026, after Phase 0.8 gate)

*Load `BACKTEST_PLAN_PHASE1.md` when Phase 0.8 gate clears. Tasks below are summaries only.*

### Historical Replay Harness for Exit-Path Validation

**Prerequisite for Phase 0.8 gate criterion B (delta/mark-stop and time-stop validation).**

When live paper trading doesn't produce a delta-stop or time-stop exit during the paper window,
the council-approved alternative is a deterministic historical replay against a known stress episode
(COVID week of 2020-03-16 or IL&FS week of 2018-09-21) injected into staging.

**Scope (design doc first — code depends on Phase 1 bhavcopy pipeline):**

- Replay harness injects historical option chain snapshots into `PaperTracker` monitoring loop.
- Must use same strategy logic, data schema, cost model, and P&L attribution code as live paper.
- Output: confirms monitoring daemon correctly identifies the trigger, queues the exit, records P&L.
- Do not build until Phase 1.3a (NSE Bhavcopy pipeline + VIX) data is available.
- Design doc: `docs/plan/replay_harness.md`. No code until Phase 0.8 gate passes.

**Owner:** Animesh + Cowork.

### Underlying OHLC Ingest — Nifty 50, India VIX, NiftyBees (task 1.3a)

Full spec in `BACKTEST_PLAN_PHASE1.md`. Parquet under `data/historical/ohlc/`. Resumable async fetcher.
Derived fields: 14-day ATR, 50-day regression slope, 10-month SMA, 252-day VIX percentile rank.

*Note: the VIX daily sub-path is pulled forward into Task 1 above (IVR gate unblock). The full
1.3a task (Nifty 50 15-min + NiftyBees) remains a Phase 1 item.*

### TrueData 1-min Options Ingestion (task 1.3b)

Full spec in `BACKTEST_PLAN_PHASE1.md`. Start only after TrueData delivers zip files (₹7,999/year, 3-year purchase recommended). Hive-partitioned Parquet at `data/historical/parquet/options/`. ~1.5 GB for 2022–2024.

### Backtest Engine + CSP Calibration (tasks 1.4–1.12)

Full task list in `BACKTEST_PLAN_PHASE1.md`. Key milestones:

- **1.4:** `BacktestEngine` core (Strategy Protocol + DayContext + run loop). Port from `quant-4pc-local`.
- **1.5:** `BacktestStore` — SQLite results storage (separate from `portfolio.sqlite`).
- **1.6a:** BS IV reconstruction from `settle_price` + Nifty Futures forward.
- **1.7:** `CSPStrategy` with `CSPConfig` — thresholds from Stockmock calibration results.
- **1.8:** Full bootstrap run 2016–2024; distribution analysis.
- **1.11:** Regime-matched Z-score (full distribution + stress-window subset). Gate: `|Z| ≤ 1.5` on both.
- **1.12:** Phase 1 gate — paper vs backtest distributions match; Animesh sign-off to start Phase 2.

---

## Phase 2 — Research Pipelines & Integrations (2027+)

*Start only after Phase 1.12 gate. Detailed specs in `PLANNER.md` and `docs/plan/`.*

### P&L Visualization (Cowork artifact)

Deferred until 4+ weeks of snapshot data available (was late May 2026, now at ~6 weeks — revisit).

Deliver as a persistent Cowork artifact (self-contained HTML, re-opens with fresh data via live DB queries). Four panels: MF (`mf_nav_snapshots`), Dhan ETFs (`dhan_holdings_snapshots`), Nuvama Bonds (`nuvama_holdings_snapshots`), Nuvama Options (`nuvama_options_snapshots`). Chart.js or Recharts. Panel 5 (Zerodha) blocked until Kite Connect integration.

**Note:** Now that ~6 weeks of data exists, this is buildable. Move to Task 4 if Animesh confirms priority.

### Zerodha / Kite Connect Integration

Deferred until FinRakshak/ILTS P&L visibility becomes a priority. Hybrid approach: Zerodha free API for position state + Upstox Analytics token for LTP (same pattern as `src/dhan/`). Evaluate Kite MCP server (2025) before writing `src/zerodha/` from scratch.

### Swing Strategy Research Pipeline (Phase 2 Track A)

Full methodology: `docs/plan/SWING_STRATEGY_RESEARCH.md`. Stages 2.S0–2.S7 (regime engine → signal generators → points backtester → option spread backtester → walk-forward → paper → live). Starts after Phase 1.12 gate.

### Investment Strategy Research Pipeline (Phase 2 Track B)

Full methodology: `docs/plan/INVESTMENT_STRATEGY_RESEARCH.md`. Stages 2.I0–2.I5 (SMA / Dual Momentum / PE Band strategies on NiftyBees, ₹5L pool). Zero paid data. Starts after Phase 1.12 gate.

### Order Execution Layer (`src/execution/`)

Blocked: static IP not provisioned. Unblocked when IP is confirmed. `place_order`, `modify_order`, `cancel_order` on `UpstoxLiveClient`; GTT orders; pre-order margin validation via `src/risk/`. All logic already designed against `BrokerClient` protocol.

### paper_snapshot.py → Telegram notification

Wire `build_notifier` from `src/notifications/` into `paper_snapshot.py`. Add `[DRY RUN]` label. Non-fatal, fire-and-forget. Defer until `paper_snapshot.py` is touched for another reason.

---

## Technical Debt

Fix alongside adjacent refactoring only. Never a standalone commit.

### DEBT-3: Missing license boilerplate

License decision needed before automation. Every file should carry a header once the license is chosen.

### DEBT-4: `find_strike_by_delta.py` — `DEFAULT_LOT_SIZE = 75` vs `constants.LOT_SIZE = 65`

`scripts/find_strike_by_delta.py` line 40 defines `DEFAULT_LOT_SIZE = 75`. All 3-track scripts use
`LOT_SIZE = 65` (centralised in `src/paper/constants.py`). Running `find_strike_by_delta.py` without
`--qty` produces dry-run commands with the wrong quantity.

**Fix when touching `find_strike_by_delta.py` next:**
1. Confirm correct lot size against NSE circular.
2. Replace `DEFAULT_LOT_SIZE = 75` with `from src.paper.constants import LOT_SIZE as DEFAULT_LOT_SIZE`.
3. Update the `--qty` help string.

---

## Session Log

| Date | What Changed |
|---|---|
| 2026-05-10 | **Auto-expiry for CSP entry scripts (SHA 21cd505).** `src/instruments/lookup.py`: added `get_expiry_candidates(underlying, today, preference)` — enumerates NIFTY expiries from BOD JSON into monthly (DTE 15–45) / quarterly (46–200) / yearly (201–420) buckets; default preference `["monthly","quarterly","yearly"]` (CSP income); accepts custom order for hedge use. `scripts/find_strike_by_delta.py`: `--expiry` now optional; when omitted, fetches chains for all candidate expiries and cross-ranks strikes by delta→round-100→spread→OI across the merged pool. `scripts/record_paper_trade.py`: wires same auto-expiry path; `--expiry` now an optional override. 6 unit tests in `tests/unit/instruments/test_expiry_candidates.py`. 58 targeted tests passing. |
| 2026-05-10 | **Markdown sweep.** Archived 2026-05-01 to 2026-05-09 session log + completed bhavcopy P1-NEXT section to `docs/archive/TODOS_ARCHIVE_2026-05-10.md`. Restructured TODOS.md (Task 0–3 sequential queue + Phase 1/2 buckets). Updated BACKTEST_PLAN.md completion log. Updated PLANNER.md completed section. Updated CONTEXT.md date + test count. |

Full log (2026-05-01 → 2026-05-09): [docs/archive/TODOS_ARCHIVE_2026-05-10.md](docs/archive/TODOS_ARCHIVE_2026-05-10.md)
Full log (2026-04-01 → 2026-04-30): [docs/archive/TODOS_ARCHIVE_2026-05-01.md](docs/archive/TODOS_ARCHIVE_2026-05-01.md)

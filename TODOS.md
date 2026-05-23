# NiftyShield — TODOs

> Open work only. Completed items and session history: [docs/archive/TODOS_ARCHIVE.md](docs/archive/TODOS_ARCHIVE.md)

---

## Sequential Queue — Next 6 Months

Tasks 0–3 run in this order. Do not start the next until the current ships and tests are green.
Ongoing paper-trading tasks (Animesh) run in parallel and are listed separately below.

| # | Task | Owner | Hard Deadline | Status |
|---|---|---|---|---|
| **0** | Fix bhavcopy UDiFF format (Dec 2024+) | Cowork | ASAP | ✅ Done (2026-05-14) |
| **1** | India VIX ingestion + IVR calculation | Cowork | Jun 2026 | ✅ Done (2026-05-14) |
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

- [x] `src/backtest/ohlc_ingest.py` (or new `src/backtest/vix_ingest.py`): daily India VIX ingest from
  `NSE_INDEX|India VIX` via Upstox `/v2/historical-candle/` (free, existing `UPSTOX_ANALYTICS_TOKEN`).
  Store as Parquet: `data/historical/ohlc/india_vix/`. Resumable — skip dates already present.
- [x] IVR formula: `ivr = (vix_today − vix_252d_low) / (vix_252d_high − vix_252d_low)`. Clamp to `[0.0, 1.0]`.
  Already implemented in `src/backtest/ivr.py` (`compute_ivr`) — wire at entry-log time.
- [x] Log IVR at entry for every paper trade: add `ivr_at_entry: float | None` field to `PaperTrade` model
  or `paper_nav_snapshots` (confirm canonical location in `src/paper/CLAUDE.md` before changing schema).
- [x] Enable R3 gate check in `scripts/record_paper_trade.py`: compute IVR from ingested data; warn (do not
  block) when IVR < 25 or > 50.
- [x] Tests: VIX Parquet resumability (skip if already present); IVR boundary tests (already in `test_ivr.py`);
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
- [ ] **Implementation Task**: Create `scripts/paper_csp_roll.py` to automate roll-over of Leg 1 (CSP) positions, mirroring the `paper_3track_overlay_roll.py` workflow.
- [ ] `paper_3track_overlay.py:243` — migrate `lookup._instruments` loop to `get_expiry_candidates` public API, same pattern as the Phase 1 fix in `paper_3track_entry.py`.
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

## Paper Trading CLI & UX Refactor

One remaining item from the 2026-05-11 audit. All others (CLI-1–5, CLI-10–11, UX-6–9) shipped in `264adf0` + `8cd9307`.

---

### CLI-12 — Surface `--notes` in snapshot output

**Problem:** `record_paper_trade.py` records a `--notes` field to the DB on every trade,
but no snapshot script reads or displays it. The field is write-only in the toolchain —
useful context (e.g. "entered at high IVR, slight slippage") is invisible during review.

**Fix:** In `paper_snapshot.py`, when printing per-strategy P&L, append a `Notes:` line
for any open trade that has a non-empty notes field. Pull via
`PaperStore.get_trades(strategy_name)` (already available) and filter for open legs.

**Files:** `scripts/paper_snapshot.py`, optionally `src/paper/store.py` if a
`get_trade_notes(strategy)` helper is warranted.

**Antigravity handoff:**
> Read `CONTEXT.md` and `src/paper/CLAUDE.md`. `PaperTrade` has a `notes: str | None`
> field stored in `paper_trades`. No snapshot script reads it. Surface it in
> `scripts/paper_snapshot.py`.
>
> In `_run()`, after computing P&L for a strategy, call `store.get_trades(name)` and
> collect all non-empty `trade.notes` from open trades (where `trade.closed_at is None`).
> If any notes exist, add a `Notes:` row to the output table (or a footer line below the
> table if UX-6 is already implemented). Format: `Notes: [leg_role] {notes}` per leg,
> deduplicated.
>
> Do not add a `get_trade_notes()` helper unless the logic is non-trivial — inline is fine
> given `get_trades()` already returns the full list.
>
> Tests: mock `store.get_trades()` returning one trade with notes and one without. Assert
> notes line appears in output for the trade with notes. Assert no notes line when all
> trades have null/empty notes.
>
> Run `python -m pytest tests/unit/ --tb=no -q` green.
> Commit: `feat(scripts): surface trade notes in paper_snapshot output`

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

### Telegram — Paper Trade Roll Alert (all tracks)

Single unified alert per leg. Fires when **either** condition is met first, then escalates in frequency as DTE shrinks. Not two independent alerts.

---

**Trigger conditions (first one to fire starts the alert cycle):**

- **Condition A — DTE:** `(expiry_date − today).days <= 5`. Applies to all open legs (short and long).
- **Condition B — Decay:** short/sell legs only; `current_premium ≤ entry_premium × 0.25` (≥ 75% of premium captured). Entry premium from `PaperTrade.entry_price`; current premium from daily snapshot LTP.

Whichever fires first determines the alert reason in the message body. If both are true simultaneously, lead with DTE since that's the action-forcing constraint.

---

**Escalating frequency schedule (DTE-driven once alert cycle starts):**

| DTE | Frequency |
|-----|-----------|
| 5–4 | Every other day |
| 3–2 | Daily |
| 1   | Daily, message prefixed with `⚠️ URGENT` |

If Condition B (decay) fires at DTE > 5: send once at the decay trigger date, then go quiet until DTE 5 when the normal escalation schedule kicks in.

Alert cycle ends when `PaperStore` records a close for the leg (roll completed). Re-arms on the replacement leg after a roll.

---

**Message content (minimum):**
- Alert reason: `ROLL DUE (DTE N)` or `DECAY TARGET HIT (X%)` — whichever triggered
- Strategy name, leg label, instrument key, expiry date, current DTE
- For decay alerts: entry premium, current premium, decay %
- Suggested command: `paper_3track_overlay_roll.py` or `paper_csp_roll.py` invocation

---

**Implementation notes:**
- Lives in `paper_snapshot.py` / `paper_3track_snapshot.py`, part of the daily EOD cron.
- Frequency gating requires persisted state: a `paper_alerts` table keyed on `(trade_id, alert_type)` storing `last_sent_date`. Check this before firing to enforce the every-other-day cadence.
- Use `build_notifier` from `src/notifications/`. Non-fatal — log warning on Telegram failure, do not abort snapshot.
- Idempotent: if cron runs twice in a day, alert fires at most once (guard on `last_sent_date == today`).

---

### `paper_alerts` Table — Schema + Audit Trail

New table in `portfolio.sqlite` (shared DB via `src/db.py`). Required before the alert cron logic can be built.

**DDL:**

```sql
CREATE TABLE IF NOT EXISTS paper_alerts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_id        TEXT        NOT NULL,          -- FK to paper_trades.trade_id
    alert_type      TEXT        NOT NULL,          -- 'ROLL_DTE' | 'DECAY_TARGET'
    triggered_by    TEXT        NOT NULL,          -- 'DTE' | 'DECAY' (which condition fired this cycle)
    dte_at_fire     INTEGER,                       -- DTE on the day alert was sent
    decay_pct       REAL,                          -- % decay at fire time (NULL for pure DTE alerts)
    entry_premium   TEXT        NOT NULL,          -- Decimal as TEXT (snapshot of entry_price at fire time)
    current_premium TEXT        NOT NULL,          -- Decimal as TEXT (LTP at fire time)
    last_sent_date  TEXT        NOT NULL,          -- ISO date YYYY-MM-DD (UTC); gate for idempotency + cadence
    sent_count      INTEGER     NOT NULL DEFAULT 1,-- total times this alert has fired for this trade_id + alert_type cycle
    telegram_ok     INTEGER     NOT NULL DEFAULT 1,-- 1 = delivered, 0 = Telegram call failed (logged but non-fatal)
    created_at      TEXT        NOT NULL,          -- ISO datetime UTC; set on first INSERT
    updated_at      TEXT        NOT NULL           -- ISO datetime UTC; updated on every re-fire
);

CREATE INDEX IF NOT EXISTS idx_paper_alerts_trade
    ON paper_alerts (trade_id, alert_type);

CREATE INDEX IF NOT EXISTS idx_paper_alerts_last_sent
    ON paper_alerts (last_sent_date);
```

**Row lifecycle:**
- **First fire:** `INSERT` with `sent_count = 1`, `created_at = updated_at = now`.
- **Re-fire (same cycle):** `UPDATE` — increment `sent_count`, refresh `last_sent_date`, `current_premium`, `dte_at_fire`, `decay_pct`, `telegram_ok`, `updated_at`. Never insert a second row for the same `(trade_id, alert_type)`.
- **Roll / leg close:** do NOT delete the row — it is the audit trail. The alert re-arms on the replacement leg's `trade_id`, which will have its own fresh row.

**Cadence gate logic (pseudo-code):**

```python
row = store.get_alert(trade_id, alert_type)
if row is None:
    fire_alert(); store.insert_alert(...)
elif row.last_sent_date == today:
    pass  # already fired today — idempotent guard
elif dte <= 2 or (dte <= 4 and (today - row.last_sent_date).days >= 2):
    fire_alert(); store.update_alert(...)
# else: too soon, skip
```

**`PaperStore` methods to add:**
- `get_alert(trade_id, alert_type) → PaperAlert | None`
- `upsert_alert(alert: PaperAlert) → None` — insert on first fire, update on re-fire

**`PaperAlert` model:** frozen `dataclass` (same pattern as `PaperNavSnapshot`). Monetary fields (`entry_premium`, `current_premium`) as `Decimal`, stored as TEXT. `last_sent_date` as `datetime.date`. `created_at` / `updated_at` as UTC `datetime`.

**Tests (`tests/unit/paper/test_paper_alerts.py`):**
- Happy path: first fire inserts row, re-fire increments `sent_count` and refreshes `last_sent_date`.
- Idempotency: second call on same day does not update.
- Cadence gate: at DTE 4, skips if `last_sent_date` was yesterday; fires if 2 days elapsed.
- Cadence gate: at DTE ≤ 2, fires regardless of gap.
- Telegram failure: `telegram_ok = 0` recorded, snapshot continues without exception.
- Roll re-arm: closing a leg does not delete the alert row; new leg gets its own fresh row.

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

### DEBT-5: `test_bhavcopy_ingest.py` — Missing test coverage for `write_to_parquet` append path

The `test_write_to_parquet_lineage_metadata` test only covers the initial write path (`new_table`). The merge/append path in `src/backtest/bhavcopy_ingest.py` (the `replace_schema_metadata` call) is not directly covered. 

**Fix when touching `test_bhavcopy_ingest.py` next:**
1. Add a test that writes twice with different dates.
2. Assert that the merged Parquet file carries the *second* run's lineage metadata (run_timestamp).

### DEBT-6: Leg validation and calendar data gaps for historical backtesting

The `Leg` domain model and validation routines carry several design debts
and missing data that must be resolved before executing backtests at scale:

1. **Move hardcoded expiry whitelist:** The irregular expiry whitelist
   (`{date(2026, 4, 7), date(2026, 12, 29)}`) is hardcoded in the domain model
   `Leg` class. Move this to a configuration file/YAML in `market_calendar`.
2. **Populate historical holidays:** Holiday YAML datasets for 2017–2025 are
   missing in `src/market_calendar/data/`. Constructing historical `Leg`
   instances pre-2026 will fail-open and skip holiday validation entirely.
3. **Formalize `is_nifty` check:** Replace the current denylist-based check
   on name and key with a formal predicate based on `instrument_key` to avoid
   false positives/negatives if other index options are introduced.

---

## Session Log

| Date | What Changed |
|---|---|
| 2026-05-23 | **TradingView MCP regime probe — validation + doc update.** Evaluated `tradesdontlie/tradingview-mcp` (CDP-based) as real-time regime signal channel. Built `docs/regime_probe.pine` (Pine Script v6 sensor: 22-row table output, regime code −2→3, options recommendation, ADX/ATR/BB/RSI/VIX). Built `docs/tv_mcp_testing_framework.md` (7-phase capability probe). Ran Phases 0, 3, 3C via ChatGPT/Codex: table readability confirmed end-to-end, timeframe switching reliable, study identified by stable name. Key findings: 1D vs 1W regime diverged on NIFTY (1D=Sideways, 1W=Volatile-Ranging) — weekly veto rule established. HV annualization bug identified (√252 hardcoded; invalid on weekly charts). Updated CONTEXT.md, DECISIONS.md, PLANNER.md, BACKTEST_PLAN.md with findings. No code changes — research/tooling only, no commit required. |
| 2026-05-15 | **Council audit + near_expiry_buy_v1.md.** All 12 council files verified absorbed → archived into `docs/council/archive/strategy/`, `archive/risk/`, `archive/research/`. Added missing DECISIONS.md row for integrated-leg2. Gamma strategy doc `near_expiry_buy_v1.md` v1.1 created with two-phase architecture. Dhan Data API subscription decision added to DECISIONS.md. |
| 2026-05-15 | **Audit Remediation Finding [11].** Removed `create_broker_client` alias from `src/client/factory.py`. Updated `scripts/paper_snapshot.py` to use `create_client` directly. Deleted `tests/unit/paper/test_paper_store.py` (redundant alias regression guard). All 1349 tests green. SHA: 8639d44. |
| 2026-05-15 | **Audit Remediation Finding [10].** Replaced hardcoded string path with `DEFAULT_DATA_DIR` constant anchored to `__file__` in `src/backtest/bhavcopy_loader.py`. Created `src/backtest/constants.py` to hold backtest defaults. Added `test_load_options_ohlcv_default_value` using `inspect.signature` to verify default behavior. SHA: e46e96d. |
| 2026-05-15 | **Audit Remediation Finding [7].** Moved inline imports (`asyncio`, `DataFetchError`) to module top-level in `src/client/upstox_market.py`. SHA: 67861d4. |
| 2026-05-15 | **Audit Remediation Finding [6].** Removed `sys.path` hack and module-level `noqa: E402` imports in `scripts/daily_snapshot.py`. SHA: 46a9bfe. |
| 2026-05-15 | **Audit Remediation Finding [5].** Replaced generic TODOs in `src/portfolio/summary.py:7,8` with tracker IDs (`(TODO: TD-5)`, `(TODO: TD-3)`). SHA: 1bfa20c. |
| 2026-05-15 | **Audit Remediation Finding [4].** Added intent comment to broad `except Exception` block in `src/portfolio/tracker.py:379`. SHA: 240aa9e. |
| 2026-05-15 | **Audit Remediation Finding [3].** Replaced `assert` with `RuntimeError` in usage example in `src/client/mock_client.py`. SHA: b54569e. |
| 2026-05-15 | **Audit Remediation Finding [2].** Replaced f-string with constant in `PRAGMA user_version` at `src/nuvama/store.py`. Added `test_schema_version_is_current`. SHA: 290a1d8. |
| 2026-05-15 | **Audit Remediation Finding [1].** Replaced f-string with lazy logging in `src/backtest/bhavcopy_loader.py:72`. Added unit tests in `tests/unit/backtest/test_bhavcopy_loader.py`. SHA: 4d69050. |

- [2026-05-18] audit finding [17] — implement cron heartbeat in DB for daily snapshot — 6f2ce32
- [2026-05-17] audit finding [16] — add missing lineage metadata to Parquet storage — 9874d84
- [2026-05-17] audit finding [15] — manual rollback — f54063c
- [2026-05-17] audit finding [14] — implement per-session Telegram message budget — 90f7acd
- [2026-05-16] audit finding [13] — convert TelegramNotifier to async aiohttp and fix all callers — b10aec9
- [2026-05-16] audit finding [12] — move PortfolioStore to async factory — 68504ae
- [2026-05-15] audit finding [11] — remove create_broker_client alias from factory — 8639d44
- [2026-05-15] audit finding [10] — replace hardcoded data path with constant in bhavcopy_loader — e46e96d
- [2026-05-15] audit finding [7] — move inline imports to top-level in upstox_market — 67861d4
- [2026-05-15] audit finding [6] — remove sys.path hack from daily_snapshot — 46a9bfe
- [2026-05-15] audit finding [5] — add tracker IDs to TODOs in summary docstring — 1bfa20c
- [2026-05-15] audit finding [4] — add intent comment for broad exception in tracker — 240aa9e
- [2026-05-15] audit finding [3] — replace assert in mock_client docstring — b54569e
- [2026-05-15] audit finding [2] — replace f-string in PRAGMA user_version with constant — 290a1d8
- [2026-05-15] audit finding [1] — replace f-string in logger.error with lazy formatting in bhavcopy_loader — 4d69050
| 2026-05-14 | **Task 1 closed.** India VIX ingestion pipeline (`vix_ingest.py`) implemented with Upstox API + NSE CSV support. `PaperTrade` model and `paper_trades` table migrated to include `ivr_at_entry`. `record_paper_trade.py` integrated with `compute_ivr` and R3 entry gate warnings (IVR < 0.25, 0.25–0.50, > 0.50). `--vix-data-dir` CLI arg added. 17 new tests across phases A–C + fix commit (`8449cbf`) green. Updated CONTEXT.md + TODOS.md. |
| 2026-05-14 | **Task 0 closed.** UDiFF fix confirmed already implemented by Antigravity (commits `490ec9b`, `590f472`): dual-URL download, `_parse_legacy`/`_parse_udiff`, format detection via `TradDt` header, 25 tests green, UDiFF fixture present. Smoke-tested against 2026-05-13 (live UDiFF download). Updated CONTEXT.md + TODOS.md. Bootstrap resume run pending (`--start 2017-06-01 --end <today>`). |
| 2026-05-12 | **CLI/UX audit cross-check.** Verified against commits `264adf0` + `8cd9307`: CLI-1–5, CLI-10–11, UX-6–9 all implemented. CLI-12 (--notes surface in paper_snapshot.py) confirmed absent — remains open. Archived session log to `TODOS_ARCHIVE.md`. Stripped done CLI/UX items from TODOS.md. |

Full log: [docs/archive/TODOS_ARCHIVE.md](docs/archive/TODOS_ARCHIVE.md)

- **2026-05-22**: Resolved audit finding [18] by replacing Any stubs in protocol.py with dict[str, Any] and importing OptionChain. Fixed time-bomb tests in nuvama/test_store.py.
- [2026-05-22] audit finding [19] — implement Leg validation constraints — 20f0bb3
- [2026-05-22] audit finding [19] follow-up — scan name and key for is_nifty — d4816f2
- [2026-05-23] audit finding [20] — return Position models instead of tuples from store — 1520d3f
- [2026-05-23] audit finding [21] — move pricing and ranking business logic from scripts to domain models — 80046db
- [2026-05-23] audit finding [8] — extract persistence logic into SnapshotService to resolve SRP violation — 6d28864



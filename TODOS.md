# NiftyShield — TODOs

> Open work only. Completed items and session history: [docs/archive/TODOS_ARCHIVE.md](docs/archive/TODOS_ARCHIVE.md)
> Known defects (deferred fixes): [BUGS.md](BUGS.md)

---

## Sequential Queue — Next 6 Months

Tasks run in order. Do not start the next until the current ships and tests are green.
Ongoing paper-trading tasks (Animesh) run in parallel and are listed separately below.

| # | Task | Owner | Hard Deadline | Status |
|---|---|---|---|---|
| **3** | June 2026 Finideas roll cycle | Animesh + Cowork | **2026-06-30** | Implementation complete — execution pending (awaiting Finideas instructions) |
| **4** | MVP: Multi-bagger Value Picks Tracker (`src/mvp/`) | Cowork | After Task 3 | ⬜ Not started |
| **5** | backtest-eval-core: `BacktestStore` + `src/analytics/` (tasks 1.5 + 1.5b) | Cowork | Aug 2026 (Phase 1, after tasks 1.3 + 1.4) | ⬜ Not started — **blocked by tasks 1.3 (Bhavcopy ingest) + 1.4 (BacktestEngine)** |

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

## Open Implementation Tasks (Phase 0)

### paper_csp_roll.py — CSP leg roll automation (0.6a)

Create `scripts/paper_csp_roll.py` to automate roll-over of Leg 1 (CSP) positions,
mirroring the `paper_3track_overlay_roll.py` workflow.

### paper_3track_overlay.py:243 — migrate private instrument loop

`paper_3track_overlay.py:243` uses `lookup._instruments` directly. Migrate to
`get_expiry_candidates` public API, same pattern as the Phase 1 fix in `paper_3track_entry.py`.

---

## Stockmock Calibration Backtests (Animesh only — prerequisite for Phase 1.7)

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

## Task 4 — MVP: Multi-bagger Value Picks Tracker (`src/mvp/`)

**Full spec:** `docs/plan/mvp/mvp_stories.md`
**Priority:** after Task 3 (June 2026 Finideas roll cycle)

Track stock calls from TV channels, Telegram, and research houses (DSIJ, prudentequity, etc.).
Capture quickly during the day, fill in price/target/SL EOD, hourly cron tracks performance.
**MVP** = **M**ulti-bagger, **V**alue, **P**ick — the three dominant recommendation categories.

### Phases

| Phase | Files | Status |
|---|---|---|
| M1 | `src/mvp/models.py`, `src/mvp/store.py`, `tests/unit/mvp/` | ⬜ Not started |
| M2 | `src/mvp/tracker.py` | ⬜ Not started |
| M3 | `scripts/mvp.py` (full CLI) | ⬜ Not started |
| M4 | `scripts/mvp_watch.py` (hourly cron) | ⬜ Not started |
| M5 | Docs close + cron entry | ⬜ Not started |

### CLI surface (final)

```bash
# Setup
mvp provider add dsij "DSIJ" --source tv
mvp category add dsij value-picks "Value Picks"

# Capture (minimum: symbol only)
mvp add RELIANCE
mvp add RELIANCE -p dsij -c value-picks

# EOD fill-in (flips PENDING → OPEN)
mvp update abc123 --price 1200 --target 1400 --sl 1100

# List / close
mvp list                     # pending (default)
mvp list --open
mvp close abc123 --price 1380

# Summary
mvp summary
mvp summary -p dsij
mvp summary -p dsij -c value-picks
mvp summary RELIANCE         # cross-provider view of one stock
```

### Cron
`0 9-15 * * 1-5` — hourly during market hours. Telegram summary + `logs/mvp_watch.log`.
Auto-closes on target/SL breach. Skips `PENDING` rows.

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
- **1.5 + 1.5b:** `BacktestStore` (SQLite results storage) + `src/analytics/` (pure-function evaluation layer). **Full spec: `docs/plan/backtest-eval-core/`** — copy `prompt.md` to start.
- **1.6a:** BS IV reconstruction from `settle_price` + Nifty Futures forward (Note: address actual IV/LTP divergence correction here per finding [23]).
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
| 2026-05-26 | Task B2.1 — Script scaffold: CLI + expiry resolution — b68bb3d |
| 2026-05-26 | Task B1 — scaffolding and store for `src/gamma/` option chain watcher — d8c2e69 |
| 2026-05-26 | Task A — Wire src/risk/ delta gate into record_paper_trade.py — b9c00146e2bb268aa0d8449a295e0d92c17cfab1 |
| 2026-05-26 | Task C — CLI-12: surface trade notes in paper_snapshot output — c71331b |
| 2026-05-26 | Task B — migrate private instrument loop in `paper_3track_overlay.py:243` — 13b3daa |
| 2026-05-26 | Task A — add paper_csp_roll.py for CSP leg roll automation — 3063fbf |
| 2026-05-26 | Task 2 closed — PortfolioDeltaTracker + entry gate (`src/risk/`); 20 tests; 1471+20 suite green |
| 2026-05-25 | audit finding [31] — document Decimal return type in protocol get_ltp — e100e28 |
| 2026-05-25 | audit finding [30] — note float re-contamination resolution in summary.py — 0c31655 |
| 2026-05-25 | audit finding [29] — refactor StrategyPnL and tracker to use Decimal strictly — 3a82c88 |
| 2026-05-25 | audit finding [28] — replace float ltp price cast with Decimal — 1cf71a5, fc0911e |
| 2026-05-24 | audit finding [27] — migrate Leg.strike float→Decimal; update store DDL, seed files, tests. 1449 tests green — faac98c |
| 2026-05-24 | audit finding [26] — centralize paper strategy names to constants — 763208a, 2a80ba8 |
| 2026-05-24 | audit finding [25] — implement STT branching logic for ITM options expiry — 64c13a4, 9eba231 |
| 2026-05-24 | audit finding [24] — verify contract cadence in get_expiry_candidates — 247e380 |
| 2026-05-24 | audit finding [23] — document VWAP distinction for settle_price in bhavcopy ingest — 518db23 |
| 2026-05-24 | audit finding [22] — implement DateAwareLotSizeResolver and resolve options lot sizes dynamically — eb078f2 |
| 2026-05-24 | audit finding [9] — implement polymorphic strategy summary methods to resolve OCP — c5cc706 |
| 2026-05-24 | audit finding [8] — extract persistence logic into SnapshotService to resolve SRP — 3242fbd |
| 2026-05-24 | audit finding [21] — move pricing and ranking logic from scripts to domain models — 80046db |
| 2026-05-23 | TradingView MCP regime probe validated (Phase 3/3C end-to-end). Weekly veto rule established. Docs only — no code changes |
| 2026-05-23 | audit finding [20] — return Position models instead of tuples from store — 1520d3f |
| 2026-05-23 | audit finding [19] follow-up — scan name and key for is_nifty — d4816f2 |
| 2026-05-23 | audit finding [19] — implement Leg validation constraints — 20f0bb3 |
| 2026-05-22 | audit finding [18] — replace Any stubs in protocol.py with dict[str, Any]; fix time-bomb tests in nuvama/test_store.py |
| 2026-05-18 | audit finding [17] — implement cron heartbeat in DB for daily snapshot — 6f2ce32 |
| 2026-05-17 | audit finding [16] — add missing lineage metadata to Parquet storage — 9874d84 |
| 2026-05-17 | audit finding [15] — manual rollback — f54063c |
| 2026-05-17 | audit finding [14] — implement per-session Telegram message budget — 90f7acd |
| 2026-05-16 | audit finding [13] — convert TelegramNotifier to async aiohttp and fix all callers — b10aec9 |
| 2026-05-16 | audit finding [12] — move PortfolioStore to async factory — 68504ae |
| 2026-05-15 | audit findings [1–11] — 11 remediations shipped (SHAs 4d69050–8639d44). Council audit complete; near_expiry_buy_v1.md v1.1 created |
| 2026-05-14 | Task 1 closed — India VIX ingestion (vix_ingest.py), PaperTrade ivr_at_entry, R3 gate. Task 0 closed — UDiFF fix confirmed (490ec9b, 590f472) |
| 2026-05-12 | CLI/UX audit cross-check — CLI-1–5, CLI-10–11, UX-6–9 confirmed shipped; CLI-12 (--notes in paper_snapshot) remains open |

Full log: [docs/archive/TODOS_ARCHIVE.md](docs/archive/TODOS_ARCHIVE.md)





# NiftyShield — TODOs

> Open work only. Completed items: [docs/archive/TODOS_ARCHIVE.md](docs/archive/TODOS_ARCHIVE.md) | Known defects: [BUGS.md](BUGS.md)
> Related: [CONTEXT.md](CONTEXT.md) | [DECISIONS.md](DECISIONS.md) | [PLANNER.md](PLANNER.md) | [BACKTEST_PLAN.md](BACKTEST_PLAN.md) | [BACKTEST_PLAN_PHASE1.md](BACKTEST_PLAN_PHASE1.md)

---

## June 2026 Calendar

Date-locked events — act before the date, not on it.

| Date | Event | Action |
|---|---|---|
| **2026-06-19** | CSP Cycle 2 time stop | Entry 2026-05-29 + 21 days. Profit target ≤ ₹79.30; delta stop ≥ 0.45. If profit target fires early, run R5 eligibility check (DTE ≥ 14, IVR ≥ 0.25). Monitor via `paper_snapshot.py --strategy paper_csp_nifty_v1`. |
| **2026-06-23** | Roll week begins | `paper_3track_overlay_roll.py` handles overlay legs at DTE ≤ 5. `paper_csp_roll.py` handles CSP Cycle 2 (`NSE_FO|79653`). |
| **2026-06-30** | All June contracts expire | Finideas roll ✅ done 2026-06-17. Base positions (`NSE_FO|62329` futures, `NSE_FO|79509` DITM call) still need manual rolls — ES11 will automate the alert once built. |

**Verify soon:** June futures base (`NSE_FO|62329`) opened 2026-05-29 — confirm non-None LTP in the next EOD snapshot:
```bash
python scripts/paper_3track_snapshot.py --no-save
```

---

## Near-term Actions

Small items: no story file yet, or waiting for a single edit/commit.

- [x] **Fix `nuvama/store.py` purge cutoff timezone** — `src/nuvama/store.py:532` uses naive `datetime.now()` instead of `datetime.now(timezone.utc)`. On a UTC host the retention window is off by +5:30, silently retaining or purging the wrong records. Fix: replace with `datetime.now(timezone.utc)`. Source: `docs/archive/reviews/2026-06-11_fable_codebase_review.md` WARNING. ✓ Verified already correct at `dc63bba` — `datetime.now(timezone.utc)` was in place; no code change needed.
- [x] **Fix `mock_client.py` float monetary fields** — `src/client/mock_client.py:92,244` uses `float` for `set_margin(amount: float)` and `"entry_price": float(price)`, diverging from the Decimal-as-TEXT protocol contract. Tests built against the mock encode float expectations that won't catch Decimal regressions. Fix: accept/emit `Decimal` in both call sites. Source: same review WARNING. ✓ Verified already correct — `set_margin(amount: Decimal)` at line 102; `entry_price` uses `price` directly from `_price_map: dict[str, Decimal]` at line 254; no float cast anywhere.
- [x] **Fix pre-existing mypy errors blocking pre-commit** — Two pre-existing failures surface when mypy follows transitive imports from `src/paper/`: (1) `src/market_calendar/holidays.py:19` — missing `types-PyYAML` stubs; fix: `pip install types-PyYAML` + add to `additional_dependencies` in `.pre-commit-config.yaml`. (2) `src/models/portfolio.py:270,276,312` — `Decorators on top of @property are not supported [misc]`; likely a `@deprecated` or custom decorator stacked on `@property` that mypy can't handle — either remove the decorator or suppress with `# type: ignore[misc]`. Until fixed, commits touching `src/paper/` require `--no-verify`. ✓ Both fixed: `types-PyYAML` in `.pre-commit-config.yaml` additional_dependencies; `# type: ignore[misc]` on all three `@computed_field` lines in `portfolio.py`.
- [ ] **Fix `PaperStore.get_positions()` per-instrument granularity** — Currently aggregates `net_qty` across all instrument keys for a given `(strategy_name, leg_role)` pair. During rolls, a SELL on the expiring instrument reduces the net_qty of the replacement instrument, producing incorrect position state. Fix: group by `(strategy_name, leg_role, instrument_key)` and return one `PaperPosition` per instrument. The `delete_trade` method already uses `instrument_key` in its WHERE clause — `get_positions` should be consistent. Detected: 2026-06-29 during `paper_nifty_proxy` base_ditm_call roll.
- [ ] **Fix daily breakdown columns in `paper_3track_snapshot.py`** — In `--daily` mode, `Day CC`, `Day Collar`, and `Day PP` display **inception-to-date totals**, not 1-day deltas. Root cause: `_compute_daily_deltas` returns only `{base_pnl, overlay_pnl, net_pnl}`; the merge `{**display_rows[i], **delta_row}` leaves the inception `cc_pnl`/`collar_pnl`/`pp_pnl` from `summary_rows` untouched. `Day Net` is correct (computed as `base_day + overlay_day` from real daily deltas). Fix: extend `_compute_daily_deltas` to also return `cc_pnl`, `collar_pnl`, `pp_pnl` as per-role daily deltas (same loop, broken out by role name). Detected: 2026-06-29.
- [ ] **Fix pre-market P&L for futures (`pre_market_brief.py`)** — During pre-market, futures have no LTP (no pre-open session), so `get_ltp` returns nothing and `prices.get(key, Decimal("0"))` defaults to 0. LONG futures at ~24000 × 75 qty = ~₹1.8M notional loss reported as unrealized P&L. Fix (Option 1): in `pre_market_brief.py`, fall back to the latest `paper_leg_snapshots` row per strategy when live LTP is unavailable (ltp=None or 0 for a futures-sized position), instead of calling `compute_pnl` directly. EOD snapshot already holds the correct unrealized. Detected: 2026-06-29.
- [ ] **Add healthcheck cron** — wire `scripts/healthcheck.py` into crontab: `30 16 * * 1-5 python /path/to/scripts/healthcheck.py`. Run once manually first to confirm Telegram alert fires correctly. (CH-8 shipped — cron entry is the remaining operational step.)
- [ ] **Fix TIME_STOP to gate on DTE-remaining, not days-held** — `evaluate_cc`, `evaluate_time_stop_csp`, and any other exit-signal evaluator that uses `days_held >= N` must be replaced with a DTE-remaining check (`dte_remaining <= threshold`). Days-held is meaningless for quarterly/leaps entries: a 113-DTE collar call held for 21 days still has 91 DTE left and should not be closed. The intent of TIME_STOP is to exit *before expiry*, not to impose a holding-period limit. Correct semantic: close when DTE drops below a per-strategy floor (e.g. ≤ 7 for weekly CC, ≤ 14 for monthly CSP, ≤ 21 for quarterly collar). The threshold should be a function of entry DTE or expiry type — not a flat wall-clock counter. Affects: `src/strategy/exit_signals.py` (`evaluate_time_stop_csp`, `evaluate_cc`), any caller that passes `days_held`. Detected: 2026-06-30 — event 68 fired TIME_STOP on `paper_nifty_spot / overlay_collar_call` (NSE_FO|65900, September 24000 CE, DTE=91 remaining); auto-close correctly failed (chain absent), but the signal itself was wrong.
- [ ] **Fix BOD resolution in CC / PP / Collar / IC V1 / IC V2 leg finders** — Five strategies fail to resolve numeric instrument keys (e.g. `NSE_FO|63916`) when `_STRIKE_RE` doesn't match. Severities differ: (1) **CC / PP / Collar** (worse) — fall back to a random chain walk, silently returning the wrong strike and computing signals against it; remove the fallback chain walk entirely. (2) **IC V1 / IC V2** (safer) — return `None` immediately, so signals go blind for that leg; `ic_nifty_v1.strike_parse_failed` / `ic_nifty_v2.strike_parse_failed` will appear in logs with no signal output. Fix for all five: add BOD lookup path identical to `csp_nifty_v1._find_put_leg` — load `InstrumentLookup.from_file(DEFAULT_BOD_PATH)`, pull `strike_price`, resolve option type from BOD `instrument_type` field, call `market.strikes.get(strike)`. Touches: `src/strategy/cc_overlay_v1.py`, `src/strategy/pp_overlay_v1.py`, `src/strategy/collar_overlay_v1.py`, `src/strategy/ic_nifty_v1.py`, `src/strategy/ic_nifty_v2.py`. Log keys to add: `*.call_leg_resolved_via_bod` / `*.put_leg_resolved_via_bod` per strategy. Detected: 2026-06-29.
- [x] **CH-4 redo — Populate `__all__` in all `src/` `__init__.py` files** — Won't do. NiftyShield has no external consumers; re-export style (`from src.portfolio import PortfolioStore`) adds maintenance overhead with no benefit over direct imports. `__init__.py` files stay as comment-only stubs. Decision: 2026-06-26.
- [ ] **Add IVR NULL note to BACKTEST_PLAN.md** — Phase 0.8 gate criterion A: *"IVR NULL for Cycles 1 and 2 — accepted data gap; criterion A satisfied from Cycle 3 onward."* Cycle 1 (id=14, 2026-05-11): pipeline not live. Cycle 2 (id=32, 2026-05-28): 0/252 days VIX history blocked computation.
- [x] **Weekly VIX refresh cron** — `scripts/pipeline/refresh_vix.py` created (thin wrapper around `ingest_vix_from_api`, 30-day lookback, `--out-dir` / `--lookback-days` flags, exit 0/1). 4 unit tests in `tests/unit/scripts/test_refresh_vix.py`. Cron: `0 8 * * 1 cd /path/to/NiftyShield && python -m scripts.pipeline.refresh_vix`. Done 2026-06-26.
- [ ] **Historical data abstraction (LOW priority)** — `HistoricalCandleFetcher` protocol so VIX and OHLC fetching can switch between Upstox, Dhan, Kite, and NSE CSV without touching storage. Currently `vix_ingest.py` has Upstox URLs hardcoded with sync `requests`; `get_historical_candles` on `BrokerClient` raises `NotImplementedError`. Start with **HD-0** (cost-bounded probe scripts — paid APIs require 5-day window only). Full story: `docs/plan/historical-data-abstraction/`. 11 tasks HD-0→HD-10. HD-6 (Dhan) and HD-7 (Kite ₹2000/month) are conditional on HD-0 decision matrix.
- [ ] **Broker abstraction (LOW priority)** — multi-broker parser/adapter layer so data fetching can migrate to Dhan or Kite without touching storage. Storage format (Parquet, SQLite, model field names) is frozen — only fetch + parse changes. Full story: `docs/plan/broker-abstraction/`. 16 tasks (BA-0 → BA-15). Start with **BA-0** (probe scripts + decision matrix — which broker is best for each data category) before writing any implementation code. BA-14 + BA-15 blocked until `src/execution/` (Phase 1) exists. Start BA-0 only after Phase 0.8 gate.
- [ ] **Create `docs/plan/entry-event-filter/`** — R4 event filter (Budget/RBI MPC/elections). Scope: `src/market_calendar/events.yaml` schema + loader + soft-warning integration into `record_paper_trade.py`. Dependency: ES12 must ship first. DoD: `prompt.md` + `tasks.md`, no code.
- [ ] **Create `docs/plan/csp-collateral-leg/`** — `long_niftybees` collateral leg. Back-fill Cycle 1 (2026-05-11); add to `paper_snapshot.py` LTP batch; annual reset. Formula: `qty = floor((65 × nifty_spot) / niftybees_ltp)`. DoD: story dir + back-fill command documented.
- [ ] **PB1.1 Post-Review: `strategy_name` constraint enforcement** — Validate that strategies use the required `paper_` prefix. Add comment/guard on the field or concrete implementations and assert in tests.
- [x] **PB1.1 Post-Review: `legs_to_close: list[str]` ambiguity** — Document that `leg_role` must be unique within a position for unambiguous closure by `leg_role`. ✓ Comment in `src/strategy/protocol.py:38`: "leg_role must be unique within a position to be unambiguous."
- [ ] **PB1.1 Post-Review: Reconsider `council_rank: int` on `ApprovedAction`** — Evaluate decoupling council rank from the action model to support a single canonical action object before building the executor.
- [x] **PB1.1 Post-Review: Add `strategy_name` presence check to protocol conformance test** — Assert `hasattr(mock_strategy, "strategy_name")` in test to document intent. ✓ `tests/unit/strategy/test_strategy_protocol.py:64–67` asserts `hasattr` + `startswith("paper_")`.

**Before build queue #6 starts** — verify paper-backbone prerequisites:
```bash
search_graph("StrategyMonitor")   # must return results
search_graph("PaperExecutor")     # must return results
search_graph("CCOverlayV1")       # must return zero results
```
If `StrategyMonitor` / `PaperExecutor` do not exist → complete build queue #5 first.

---

## Animesh-only: Stockmock Calibration Backtests

Prerequisite for Phase 1 task 1.7 (`CSPStrategy` calibration). Stockmock UI — no code required.

- [ ] COVID crash (Feb–Apr 2020) — strikes hit, premium, max M2M loss, breach frequency
- [ ] IL&FS crisis (Sep–Oct 2018) — same metrics
- [ ] 2022 rate-hike selloff (Jan–Jun 2022) — same metrics
- [ ] Stable baseline (Jan–Dec 2023) — expected exit-type distribution in normal markets
- [ ] Summarise in [docs/strategies/csp_nifty_v1.md](docs/strategies/csp_nifty_v1.md) under "Calibration Backtest Results (Stockmock)"
- [ ] Commit: `docs(strategies): CSP v1 Stockmock calibration backtest results`

---

## Active Tasks

> **Priority rule:** #1 (Finideas roll) is the immediate hard deadline. #2 (MVP) is independent and slots in any cycle.

---

### Build queue #1 — June 2026 Finideas Roll

**Hard deadline: 2026-06-30** (NIFTY_JUN 23000 CE and PE legs expire — see [REFERENCES.md](REFERENCES.md)).
Invoke `roll-validator` agent ≥1 week before deadline.

- [ ] Invoke `roll-validator` ≥1 week before 2026-06-30 — pre-check position state, Trade model integrity, DB atomicity.
- [ ] Receive Finideas roll instructions (strike, expiry, quantity for each leg).
- [ ] Run `python -m scripts.roll_leg --dry-run ...` with all four `--old-*/--new-*` flags. Verify output.
- [ ] Run without `--dry-run`. Verify both Trade rows inserted atomically.
- [ ] Run `python -m scripts.daily_snapshot` same day. Confirm P&L continues uninterrupted.
- [ ] Session log entry with date, old/new instrument keys, and any anomalies.
- [ ] File a separate fix commit before moving on if any bug surfaces.

**Owner:** Animesh (receives instructions) + Cowork (executes scripts).

---

### Build queue #2 — MVP: Multi-bagger Value Picks Tracker

**Story:** [docs/plan/mvp/](docs/plan/mvp/) (prompt, tasks, stories, schema)
**CLI surface and cron spec:** [docs/plan/mvp/mvp_tasks.md](docs/plan/mvp/mvp_tasks.md)
**Note:** Independent — does not block any other queue item.

| Step | Files | Status |
|---|---|---|
| M1 | `src/mvp/models.py`, `src/mvp/store.py`, `tests/unit/mvp/` | ⬜ Not started |
| M2 | `src/mvp/tracker.py` | ⬜ Not started |
| M3 | `scripts/mvp.py` (full CLI) | ⬜ Not started |
| M4 | `scripts/mvp_watch.py` (hourly cron) | ⬜ Not started |
| M5 | Docs close + cron entry | ⬜ Not started |

---

## Build Queue

Tasks run in priority order. Infrastructure that blocks other stories runs first. Independent strategy work slots in around the critical path.

| # | Task | Owner | Deadline | Blocks | Status |
|---|---|---|---|---|---|
| 1 | June 2026 Finideas roll | Animesh + Cowork | **2026-06-30** | — | Execution pending — awaiting Finideas instructions |
| 2 | chain-data: EOD + intraday chain snapshot cron | Cowork | — | — | ✅ Shipped — [story](docs/archive/plan/chain-data/) |
| 3 | scripts-restructure SR0–SR11 | Cowork | — | — | ✅ Shipped — [story](docs/archive/plan/scripts-restructure/) |
| 4 | paper-backbone: Strategy Monitor daemon | Cowork | — | — | ✅ Shipped — [story](docs/archive/plan/paper-backbone/) |
| 5 | paper-backbone-adj: roll signals + strategy adjustments | Cowork | — | — | ✅ Shipped — [story](docs/archive/plan/paper-backbone-adj/) |
| 6 | paper-exit-signals: automated exit detection + closure | Cowork | — | — | ✅ Shipped — [story](docs/archive/plan/paper-exit-signals/) |
| 7 | council-refactor: remove RapidCouncil from daemon path; deterministic roll rules | Cowork | — | — | ✅ Shipped — [story](docs/archive/plan/council-refactor/) |
| 8 | covered-call-overlay: NiftyBees CC calibration experiment | Cowork | — | — | ✅ Shipped — [story](docs/archive/covered-call-overlay/) |
| 9 | MVP: Multi-bagger Value Picks Tracker | Cowork | After #1 | — | ⬜ Not started — [story](docs/plan/mvp/) |
| 10 | backtest-eval-core: `BacktestStore` + `src/analytics/` | Cowork | Aug 2026 | #11 | ⬜ Not started — [story](docs/plan/backtest-eval-core/) — **blocked by tasks 1.3 + 1.4** |
| 11 | signals-eval-core: regime engine + signal generators + validation | Cowork | Q4 2026 | — | ⬜ Not started — [story](docs/plan/signals-eval-core/) — **blocked by #10 + Phase 1.12 gate** |
| 12 | broker-abstraction: multi-broker parser/adapter layer (Dhan, Kite) | Cowork | LOW — after Phase 0.8 gate | — | ⬜ Not started — [story](docs/plan/broker-abstraction/) — 16 tasks BA-0→BA-15; start with BA-0; BA-14/15 blocked on Phase 1 |
| 13 | historical-data-abstraction: `HistoricalCandleFetcher` protocol + vendor implementations | Cowork | LOW — after Phase 0.8 gate | — | ⬜ Not started — [story](docs/plan/historical-data-abstraction/) — 11 tasks HD-0→HD-10; start with HD-0 cost probe; HD-6/HD-7 conditional on HD-0 decision matrix |

---

## Phase 1 — Backtest Engine (Aug–Dec 2026)

*Gated on Phase 0.8. Load [BACKTEST_PLAN_PHASE1.md](BACKTEST_PLAN_PHASE1.md) when the gate clears.*

**Replay Harness** (`docs/plan/replay_harness.md` — design doc not yet written): prereq for Phase 0.8 gate criterion B. Injects historical chain snapshots (COVID 2020-03-16 or IL&FS 2018-09-21) into `PaperTracker`. No code until task 1.3a data exists.

**Key milestones (full spec in [BACKTEST_PLAN_PHASE1.md](BACKTEST_PLAN_PHASE1.md)):**
- **1.3a** — Nifty 50 + NiftyBees OHLC Parquet; derived: ATR-14, slope-50, SMA-10M, VIX rank-252.
- **1.3b** — TrueData 1-min options ingest (~1.5 GB for 2022–2024; start after zip delivery).
- **1.4** — `BacktestEngine` core (Strategy Protocol + DayContext + run loop).
- **1.5 + 1.5b** — `BacktestStore` + `src/analytics/`; full spec: [docs/plan/backtest-eval-core/](docs/plan/backtest-eval-core/).
- **1.7** — `CSPStrategy` with `CSPConfig` from Stockmock calibration results.
- **1.11** — Regime-matched Z-score; gate `|Z| ≤ 1.5`.
- **1.12** — Phase 1 gate: paper vs backtest distributions match; Animesh sign-off.

---

## Phase 2 — Research Pipelines & Integrations (2027+)

*Gated on Phase 1.12. Full specs in [PLANNER.md](PLANNER.md) and [docs/plan/](docs/plan/).*

| Item | Notes |
|---|---|
| P&L Visualization (Cowork artifact) | ~6 weeks of data available now — buildable if prioritised. Four panels: MF, Dhan ETFs, Nuvama Bonds, Nuvama Options. Panel 5 (Zerodha) blocked on Kite Connect. |
| Zerodha / Kite Connect integration | Defer until FinRakshak/ILTS P&L visibility matters. Evaluate Kite MCP server before writing `src/zerodha/` from scratch. |
| Swing Strategy Pipeline (Track A) | SE1–SE3 + SE5–SE6. Full sequence: [docs/plan/signals-eval-core/tasks.md](docs/plan/signals-eval-core/tasks.md). |
| Investment Strategy Pipeline (Track B) | SE1–SE2 + SE4–SE6. Same story file. Parallel branch off SE2.2. |
| Order Execution Layer (`src/execution/`) | Blocked: static IP not provisioned. Design done against `BrokerClient` protocol. |
| `paper_snapshot.py` → Telegram | Wire `build_notifier`; non-fatal. Defer until file is touched for another reason. |

---

## Technical Debt

Fix alongside adjacent refactoring only. Never a standalone commit.

**DEBT-3:** License boilerplate — decision needed before automation. Every file gets a header once chosen.

**DEBT-5:** `test_bhavcopy_ingest.py` missing append-path coverage — `write_to_parquet` merge branch (`replace_schema_metadata` call) not tested. Fix when touching that test file: write-twice test asserting second run's lineage metadata survives the merge.

**DEBT-6:** Leg validation + calendar data gaps for historical backtesting:
1. Move hardcoded expiry whitelist (`{2026-04-07, 2026-12-29}`) from `Leg` to `market_calendar` YAML.
2. Holiday YAML datasets for 2017–2025 missing in `src/market_calendar/data/` — historical `Leg` construction pre-2026 fails open.
3. Formalise `is_nifty` check: replace denylist with an `instrument_key`-based predicate.

**DEBT-7:** Refactor dynamic dispatch in `daily_snapshot.py` to eliminate `noqa: F401` unused import suppressions (which hide broken imports if helpers are renamed/moved).

---

## Session Log

| Date | What Changed |
| 2026-07-02 | BUG-003 B003.2-7 — `_post_expiry_gate` fix: added `_most_recently_settled_expiry()` (current month's last Tuesday if already passed, else previous month's, Dec→Jan rollover safe); gate now blocks only same-day re-entry on the prior cycle's settlement date instead of the entire new cycle against its own future expiry; B003.4 confirmed no separate already-fixed v2 gate existed to port (23e8e93 had already merged the still-buggy calendar gate into the shared `ic_entry_gates.py`, used by both V1/V2); `_last_tuesday_of_month` itself untouched (B003.3, REFERENCES.md Tuesday-expiry logic unaffected); 6 new/rewritten tests across `test_ic_entry_gates.py` + `test_paper_ic_entry_v2.py` (67/67 tests/unit/strategies/ic/ pass); code-reviewed (general-purpose + REVIEW.md substitute), no CRITICAL/ERROR findings — 2c6f771 |
| 2026-07-02 | BUG-002 B002.4-7 — magnitude fix: _position_delta classifies by PaperPosition.option_type (not instrument_key substring match); aggregate_delta/_position_delta gain optional position_deltas map for chain-derived delta, falls back to net_qty/lot_size approximation with logged WARNING when unavailable; module boundary + fallback policy per LLM council ruling 2026-07-02 (docs/council/2026-07-02_paper-delta-source-architecture.md) — src/risk/ stays pure/zero-I/O, caller (not yet wired) owns chain resolution; 3 new tests + all existing fixtures + hypothesis strategy updated to set option_type explicitly (30/30 tests/unit/risk/ pass); code-reviewed (general-purpose + REVIEW.md checklist substitute — code-reviewer subagent type unavailable in this environment), 1 CRITICAL (G2 line length) fixed — 62ed6ef |
| 2026-07-02 | BUG-002 B002.3 — PaperPosition.option_type (CE/PE/FUT/EQ) resolved lazily in get_position/get_positions via InstrumentLookup; NiftyBees short-circuits to EQ; code-reviewer C1/C2 (unhandled BOD load I/O errors) + W1 (bad FUT fallback for non-CE/PE/FUT types) fixed pre-commit; 9 new tests (69/69 in test_store.py) — 96398b4 |
| 2026-06-28 | ic-nifty-v2 IC-V2-16 — Phase 4 docs close: CONTEXT.md (post-expiry gate + DTE window in paper_ic_entry_v2.py; V2 loop in paper_ic_snapshot.py); TODOS.md session log — no code | SHA: a8a2149 |
| 2026-06-28 | ic-nifty-v2 IC-V2-15 — Telegram alert on gate failures: notifier Callable param added to check_duplicate + resolve_ivr; _gate_alert wrapper in run(); post_expiry + wing floor + delta exits also alert; 3 tests — c2cce55 |
| 2026-06-28 | ic-nifty-v2 IC-V2-13 final — _post_expiry_gate() moved to ic_entry_gates (calendar-based, no params); V1 monthly gate added; fixed c18baae always-block bug (was comparing today vs future expiry); 6 test files updated — 23e8e93 |
| 2026-06-28 | ic-nifty-v2 IC-V2-13 fix — post-expiry gate switched to BOD expiry date (holiday-aware); _last_tuesday_of_month removed; force_entry param dropped; holiday test added — c18baae |
| 2026-06-28 | ic-nifty-v2 IC-V2-13 — post-expiry entry gate: _post_expiry_gate() + _last_tuesday_of_month() in paper_ic_entry_v2.py; DTE window recalibrated 30→20 / 45→32; 4 gate tests; mock_gates fixture updated — 6868dd7 |
| 2026-06-28 | ic-nifty-v2 IC-V2-12 — final docs close: ProfitLockEngine + ProfitLockConfig in CONTEXT.md; profit_lock_engine.py + ic/ scripts subfolder in CONTEXT_TREE.md; profit-lock council ruling in DECISIONS.md — d4dbdf7 |
|---|---|
| 2026-06-15 | NT-1 fix — negative countdown clamped (max(0,...)), singular day grammar, recovery test added — 9acc1e3 |
| 2026-06-15 | NT-2 — _check_futures_cc_block(): BLOCKED_COMBINATION ACTION on Futures+standalone CC; collar exempted; degenerate collar blocked; 7 tests — da837b5 |
| 2026-06-15 | DAEMON-FIX — overlay_cls() zero-arg → overlay_cls(**overlay_kwargs) with store/gateway/vix_data_dir; MONITOR_OVERLAYS=1 in .env — c68250c |
| 2026-06-15 | FR-10 — NotifierProtocol added to src/notifications/protocol.py; _notifier typed as NotifierProtocol in StrategyMonitor; both # type: ignore[attr-defined] removed — b32cf55 |
| 2026-06-15 | RPT-2 — CLI period redesign: --daily/-d (default), --monthly/-m (guard), --inception/-i; _compute_daily_deltas helper; format_track_summary period param with Day Base/Day Overlay/Day Net headers; 11 new tests — cabf2ba |
| 2026-06-15 | RPT-ROLL — _find_expiring_overlay: reset last_trade=None when net reaches 0; only current open cycle contributes; 2 new tests (multi-cycle + all-closed) — 46d4848 |
| 2026-06-17 | finideas_ilts roll JUN→JUL: closed JUN CE @ ₹1065.15, JUN PE @ ₹18.25; opened JUL CE (NSE_FO\|63895) @ ₹1245.00, JUL PE (NSE_FO\|63896) @ ₹90.95; 65 lots each; fixed record_trade.py get_position unpacking (Position dataclass) |
| 2026-06-15 | paper-backbone-adj PA0 — roll_utils.find_strike_by_delta shared helper + 8 tests — eef6cca |
| 2026-06-15 | paper-backbone-adj PA1.1 — CSPNiftyV1 ROLL signal + _select_roll_target + apply_action ROLL branch + 7 tests — 4d8e81e |
| 2026-06-22 | paper-backbone-adj PA1.2 — IronCondorV1 ROLL_WING signal + _select_wing_roll_target() + apply_action ROLL_WING branch + 6 tests (incl. directional guard) — 355bf3c |
| 2026-06-22 | paper-backbone-adj PA2 — retire paper_csp_roll.py + paper_3track_overlay_roll.py + their test files; update CONTEXT.md, DECISIONS.md, NiftyTrackComparisonV1 docstring — 2eea225 |
| 2026-06-14 | SM-1 — DELTA_BREACH_FINAL state machine wired: get_trade_state + mark_trade_defended added to PaperStore; check_signals reads TradeState from DB (not hasattr); _roll_down transitions new leg to DEFENDED; _find_put_leg scan fallback removed (numeric keys now return None + WARN); 8 new tests — 37c38d0 |
| 2026-06-14 | BUG-5 — _check_reentry dedup: skip if R5_REENTRY_BLOCKED/ELIGIBLE event already exists today for same strategy+leg; fixed test_custom_ivr_passes_override to use different days; 2 new tests — 80784c0 |
| 2026-06-14 | BUG-3 — _open_new quantity=1 hardcode fixed; CLOSE_AND_ROLL now passes abs(short_put.net_qty); 2 new tests — 5d1c8eb |
| 2026-06-13 | SIG-2 — evaluate_pp zero-entry guard (WARN + early return); evaluate_collar_put ltp fallback when bid/ask None (INFO); Decimal conversion in both + evaluate_collar_call residual_breached; 7 new tests — f99a4cb |
| 2026-06-13 | SIG-1 — paper_action_audit table + record_action_audit(); _write_audit rewired to store per-leg fills; migrate_paper_action_audit.py; 6 new tests (TestResolveMidPrice + TestWriteAudit) — 580c0e8 |
| 2026-06-13 | BUG-4 — paper_trades UNIQUE constraint extended to include instrument_key; __init__ migration rebuilds constraint on stale DBs; migrate_paper_trades_unique.py for live DB; 2 new tests — 50c4e56 |
| 2026-06-13 | BUG-1 — get_positions multi-cycle: logic fix confirmed in DBI-3; added 2 regression tests (avg_sell_price current-cycle-only, fully-closed net-zero) — 77b6082 |
| 2026-06-13 | FR-2 — PaperExitEvent monetary fields (ltp, mid, bid, ask, entry_price, threshold_value): float→Decimal, REAL→TEXT; _parse_exit_event_row helper; migrate_exit_events_decimal.py; 3 new tests — 05a4e49 |
| 2026-06-13 | DBI-3 — get_positions: entry_date now set from opening trade regardless of BUY/SELL (fixes long-first PP/ETF legs); instrument_key now from cycle-opening contract not last loop row (fixes rolled legs); 4 new tests in test_store.py |
| 2026-06-13 | DBI-2 — cc_overlay_v1, pp_overlay_v1, collar_overlay_v1: each apply_action now records a closing PaperTrade to the DB (BUY for short call, SELL for long put); CollarOverlayV1 gets __init__(store=None); 14 new tests across the three overlay test files |
| 2026-06-12 | LOG-1 — Add generate_trace_id/bind_trace_id to logging.py; wire into monitor._tick (tick.start/end), paper_3track_snapshot main, paper_3track_overlay_roll _run, executor.apply (action.dispatch/fill/complete); 4 new tests — 74371a3 |
| 2026-06-12 | FR-1 — Extract shared _price_utils.py (find_option_leg + resolve_price); fix OverlayCloser._resolve_mid_price to raise ValueError instead of returning Decimal("0"); fix executor._resolve_mid_price stub; update 2 existing tests, add 10 new tests in test_price_utils.py — 611d5b5 |
| 2026-06-07 | council-refactor PP-1 — Update evaluate_pp() to remove spread guard, promote DTE_REVIEW INFO to ROLL_ELIGIBLE ACTION, and simplify callers and tests — 8fd7f68 |
| 2026-06-07 | council-refactor CC-5 — manual Covered Call roll/exit override CLI wrapper paper_cc_roll.py and unit tests in test_cc_roll.py — afd8a9a |
| 2026-06-07 | council-refactor CC-4 — CCOverlayV1 full automation: auto_execute=True, inherit ReEntryMixin, add __init__ with store/notifier/vix_data_dir, handle CLOSE_CC in apply_action, _send_close_notification via send_notification; re-entry check on PROFIT_TARGET + TIME_STOP only — 3058108 |
| 2026-06-07 | covered-call-overlay CC-3 — Migrate CSPNiftyV1 to ReEntryMixin: inherit mixin, add reentry_leg_role/reentry_script_hint class attrs, remove _check_r5_reentry (125 lines), call _check_reentry on PROFIT_TARGET and TIME_STOP (TIME_STOP regression fix), re-target 8 test VIX patches, add TIME_STOP happy-path + edge-case tests — 269c08e |
| 2026-06-07 | feat(strategy): ReEntryMixin with three-gate re-entry check; Telegram notification — fb38dde |
| 2026-06-07 | council-refactor CC-1 — Align evaluate_cc() to CSP structure: add days_held, TIME_STOP signal, DTE_REVIEW WARN, use _PROFIT_TARGET_RETENTION, add _CC_MIN_ENTRY_CREDIT; update CCOverlayV1 caller; 15+ new tests — 5314ec0 |
| 2026-06-07 | council-refactor CR1c — Refactor paper_csp_roll.py to thin CLI wrapper around csp_roll_executor.py; existing tests stay green — 154a64c |
| 2026-06-06 | council-refactor CR1b — TradeState enum + state field on PaperTrade; PaperStore update_trade_state; ExitSignalEngine: remove evaluate_csp, add 5 independent CSP classmethods (70% profit target, 2× hard stop, 0.40 delta breach, 21-day time stop, DTE≤7 roll eligible); CSPNiftyV1.check_signals migrated; paper_3track_snapshot.py migrated; idempotent DB migration script; 20+ new tests — 8fd58d4 |
| 2026-06-06 | council-refactor CR1a — Extract strike_selector.py from find_strike_by_delta.py, update all imports in 4 scripts, and add unit tests — 0a6b3bd |
| 2026-06-04 | council-refactor CR0 — Fix send_approval_request signature mismatch (TypeError on first live ACTION); remove CouncilOutput from approval path; wire valid_actions in 5 strategy payloads; _build_keyboard(list[str]); guard returns None+logs ERROR on empty valid_actions — 4ce6d99 |
| 2026-06-04 | council-refactor story created — docs/plan/council-refactor/ (prompt, stories, tasks); README, TODOS, DECISIONS updated. Covers: RapidCouncil removal from daemon path, send_approval_request bug fix, deterministic IVR-tiered CSP roll rules, overlay roll rules with base-DTE guard. 4 tasks (CR0–CR4). Deadline: before 2026-06-23 roll week. |
| 2026-06-03 | paper-exit-signals ES9 — Docs close: DECISIONS.md verification, CONTEXT.md sync, TODOS.md updated; archive council exit-philosophy and csp_nifty_v1 spec — e32b862 |
| 2026-06-03 | paper-exit-signals ES12 — Enforce liquidity gate in find_strike_by_delta.py and R3 hard block in record_paper_trade.py + 11 tests — b86925a |
| 2026-06-03 | paper-exit-signals ES11 — Base position expiry detection (DTE <= 5), get_next_contract in InstrumentLookup, roll commands Telegram alert + 5 tests — 16c7f23 |
| 2026-06-03 | paper-exit-signals ES10 — CSPNiftyV1 R5 re-entry eligibility: __init__, PROFIT_TARGET action_type, _check_r5_reentry (DTE/IVR/open-pos gates), paper_exit_events write + Telegram + 9 tests — c9625e1 |
| 2026-06-03 | paper-exit-signals ES7 — compute_and_record_exit_signals() in paper_3track_snapshot.py: Tier 1 EOD exit signal dispatch (CSP/CC/PP/Collar), dedup, paper_exit_events write, Telegram alerts + 10 tests — 1d40d8f |
| 2026-06-03 | paper-exit-signals ES6 — OverlayCloser class with single leg and collar closure routing + tests (adjusted for review findings) — 3dafad9 |
| 2026-06-03 | paper-exit-signals ES5 — CollarOverlayV1 strategy class + 11 unit tests — d25abf7 |
| 2026-06-03 | paper-exit-signals ES4 — PPOverlayV1 strategy class + 10 unit tests — 681f7db |
| 2026-06-03 | paper-exit-signals ES3 — CCOverlayV1 strategy class + 11 unit tests — 9ed05fb |
| 2026-06-03 | paper-exit-signals ES1 — stateless ExitSignalEngine class with CSP, CC, PP, Collar exit & warning rules + 20 unit tests — 2de33eb |
| 2026-06-03 | paper-exit-signals ES0 — paper_exit_events DDL migration + PaperStore create/get/ack/resolve methods + Pydantic model + 6 tests — 7cd8212 |
| 2026-06-02 | paper-backbone PB5 — Docs close: CONTEXT.md (src/strategy/, src/council/, TelegramGateway, daemon scripts, What Does NOT Exist Yet), DECISIONS.md (paper-backbone entry), TODOS.md (build queue status) — 565b660 |
| 2026-06-02 | paper-backbone PB4.1 — NiftyTrackComparisonV1 backbone integration: WARN-only check_signals (ROLL_DUE_DTE, ROLL_DUE_DECAY, OVERLAY_EXPIRED) + apply_action no-op + 14 tests — 2567c04 |
| 2026-06-02 | paper-backbone PB3.1 — IronCondorV1 backbone integration: check_signals + apply_action (CLOSE_FULL/CLOSE_CALL_SPREAD/CLOSE_PUT_SPREAD; ADJUST_* raises ValueError per council) + 13 tests — 0937b60 |
| 2026-06-01 | paper-backbone PB1.7 CR — Code review fixes: tests, logging, date mismatch, layering — 0e51357 |
| 2026-06-01 | paper-backbone PB1.7 — Scripts: monitor_daemon.py + start_monitor.py + stop_monitor.py + pre_market_brief.py + eod_summary.py + requirements.txt — 9191c02 |
| 2026-06-01 | paper-backbone PB1.6 — DB migrations for pending_approvals + council_outputs + daemon_heartbeat + store methods — 60408cf, 436982e |
| 2026-06-01 | paper-backbone PB1.5 — TelegramGateway with approval flow, inbound polling, auth guard, timeout scanner — fde2b3b |
| 2026-06-01 | paper-backbone PB1.4 — RapidCouncil parallel Stage 1 advisors and Chairman synthesis — 6b71c9e, 845f1e0, 275e1bb |
| 2026-06-01 | paper-backbone PB1.3 — PaperFillSimulator (VIX-regime slippage) + PaperExecutor (close/open legs via PaperStore) — 46e58ba |
| 2026-06-01 | paper-backbone PB1.2 — StrategyMonitor daemon loop with registry and signal routing — 35b3099 |
| 2026-05-31 | paper-backbone PB1.1 — PaperStrategy protocol + SignalEvent + ApprovedAction + LegSpec models — 6c527c2 |
| 2026-05-31 | scripts-restructure SS1 — Move exploratory scripts out of src/ into scripts/dev/ and rename test_ prefixes — 4fd2e19 |
| 2026-05-31 | scripts-restructure SR11 — Docs close: CONTEXT.md, DECISIONS.md, and TODOS.md updated to finalize restructured layout — 4777759 |
| 2026-05-31 | scripts-restructure SR10 — Move portfolio/ scripts (daily_snapshot, morning_nav, paper_snapshot, roll_leg) to scripts/portfolio/ and update crontab — 13b7285 |
| 2026-05-31 | scripts-restructure SR9 — Move csp and cc_calibration strategy scripts to scripts/strategies/csp/ and scripts/strategies/cc_calibration/, update test imports — e161cc9 |
| 2026-05-31 | scripts-restructure SR8 — Move strategies/three_track/ scripts to scripts/strategies/three_track/, update test imports, and update crontab — 28894d2 |
| 2026-05-31 | scripts-restructure SR7 — Move intraday/ scripts (intraday_tracker, nuvama_intraday_tracker, dhan_intraday_tracker) to scripts/intraday/ and update crontab — 20b3834 |
| 2026-05-31 | scripts-restructure SR6 — Move council/ scripts + templates to scripts/council/ and update test imports and path references — 55bb02c |
| 2026-05-31 | scripts-restructure SR5 — Move seed/ and dev/ scripts to scripts/seed/ and scripts/dev/ and fix test imports — 16ca1e1 |
| 2026-05-31 | scripts-restructure SR4 — Move record/ scripts (record_paper_trade, record_trade) to scripts/record/, update references and test mock patches — 5acd9fe |
| 2026-05-31 | scripts-restructure SR3 — Move lookup/ scripts (find_strike_by_delta, find_overlay_strikes, instrument_lookup) and update imports in record_paper_trade, paper_cc_entry, paper_csp_roll, and tests — 3fac186 |
| 2026-05-31 | scripts-restructure DA1 — archive restructure: process/ + research/ created; 8 files moved; gamma_implementation_plan.md evicted from live docs/antigravity/; reco_tracker.md delete needs manual git rm |
| 2026-05-31 | scripts-restructure SS4 — src/gamma/CLAUDE.md + src/nuvama/CLAUDE.md written; model placement rule codified in DECISIONS.md |
| 2026-05-31 | scripts-restructure SS5 — CONTEXT_TREE.md full sync: added config.py, models/options.py, risk/ block (models/delta_tracker/entry_gate), utils/logging.py; verification script clean |
| 2026-05-31 | scripts-restructure SS3 — Audit complete: service.py protocol boundary added (5986948); market_store.py has 3 callers + 9 tests green; CONTEXT_TREE documented — SS3 closed, SS5 now unblocked |
| 2026-05-31 | scripts-restructure SR2 — Move pipeline/ scripts (chain snapshot, intraday, gamma watch, bhavcopy) and update test imports + crontab — a6ca253 |
| 2026-05-31 | scripts-restructure SR1 — Scaffold scripts/ subdirectories with __init__.py files — 72cb528 |
| 2026-05-31 | code-health CH-10 — Docs close: CONTEXT.md (config.py/logging.py/healthcheck.py entries, test count), DECISIONS.md (3 decisions), TODOS.md (healthcheck cron action, session log) — health sprint complete |
| 2026-05-31 | CH-9b — Implement @given tests for IVR, delta, and P&L arithmetic — 7157010 |
| 2026-05-31 | feat(scripts): add healthcheck.py dead man's switch for cron validation — fe1e123 |
| 2026-05-30 | refactor(src,scripts): replace direct environment access with Settings singleton — fe69612 |
| 2026-05-30 | CH-7a — Define Settings model in src/config.py mapping all env vars — 0222885 |
| 2026-05-30 | CH-6 — Central structlog logging setup + wire to scripts — 75f499b |
| 2026-05-30 | CH-5 — docs/architecture.md Mermaid C4 container diagram — 37b77bc |
| 2026-05-30 | CH-2 — vulture dead code scan across src/ + scripts/; dead_code_report.md produced and classified (10 safe-to-delete, 13 needs investigation, 47 false positives) — 55eef02 |
| 2026-05-30 | CH-1 — pylint similarity scan across src/; duplication_report.md produced and classified — 11b7e36 |
| 2026-05-30 | CI CI-5 — Docs close: CONTEXT.md CI section, DECISIONS.md no-CD + parallel + coverage entries, ci_tasks.md ticked — docs commit |
| 2026-05-29 | CI CI-4 — Wire coverage upload to GitHub Actions summary — 4f3ee8a |
| 2026-05-29 | CI CI-3 — Add pytest-randomly to test config + verify no order-dependent failures — 0af6cfb |
| 2026-05-29 | CI CI-2 — Add pytest-xdist parallel config + @pytest.mark.slow — 0fed45b |
| 2026-05-31 | code-health CH-9a — Design hypothesis edge cases for compute_ivr, aggregate_delta, P&L arithmetic — 57418a7 |
| 2026-05-29 | CI CI-1 — Create .github/workflows/ci.yml — d6e9899 |
| 2026-05-30 | code-health CH-3 — Create GLOSSARY.md with ~42 domain and project terms — 10a5d22 |
| 2026-05-29 | dx-foundation DX-7 — Docs close: CONTEXT.md tooling section, DECISIONS.md mypy/ruff/pre-commit entries, TODOS.md session log — docs commit |
| 2026-05-29 | dx-foundation DX-6 — post-commit hook and installer — 1b94b5c, cc5c78c |
| 2026-05-29 | dx-foundation DX-5 — Create Makefile with standard dev targets — 7d4976e |
| 2026-05-29 | dx-foundation DX-4 — pre-commit hooks configuration — 7f728e0 |
| 2026-05-29 | dx-foundation DX-2 — configure ruff lint and format rules — 83e4abf |
| 2026-05-29 | dx-foundation DX-1 — pyproject.toml dev dependencies — 0671073 |
| 2026-05-29 | covered-call-overlay CC2 — paper_cc_entry.py entry helper — 972a13c |
| 2026-05-29 | covered-call-overlay CC1 — STRATEGY_CC_OVERLAY + compute_max_lots + 7 tests — 0e5ebeb |
| 2026-05-29 | chain-data CD4 — Docs close — af6449d (amended from 80cf95e to add CONTEXT_TREE.md) |
| 2026-05-28 | chain-data CD3.1 — ChainReader — DuckDB-based EOD and intraday chain query utilities — 7c0fe66 |
| 2026-05-28 | chain-data CD2.1 — upstox_chain_intraday — 5-min intraday option chain snapshot — c1aea22 |
| 2026-05-28 | chain-data CD1.2 — upstox_chain_snapshot — EOD option chain snapshot cron — 0db8767 |
| 2026-05-28 | chain-data CD1.1 — ChainWriter — Parquet EOD and intraday chain snapshot writer — ce57240 |
| 2026-05-28 | TODOS.md reordered — immediate actions + calendar at top, build queue + phases below |
| 2026-05-28 | TODOS.md restructured — unified numbering, removed P-label clashes, P0-2 removed (done) |
| 2026-06-02 | paper-backbone PB2.1 — CSPNiftyV1 backbone integration (check_signals, apply_action, describe_context, 15 tests) — fbc1b56 |
| 2026-05-28 | P0-2 + Task 3b: R3 caveat updated; CSP v1 spec reconciled (lot size, time stop, R-numbers, R4) |
| 2026-05-28 | P1-2: guard None LTP in generate_track_snapshot — 57299e4; 2 regression tests; 1457 passing |
| 2026-05-28 | Session: CSP Cycle 1 closed (₹8,898.50); Cycle 2 opened (23300 PE JUN 30 @ ₹158.6, 65u); May futures settled; June futures opened; DEBT-4 fixed (75→65); DB rows id=31,32 corrected |
| 2026-05-28 | paper-exit-signals story created; council exit-philosophy decisions → DECISIONS.md (10 rows); build queue #6 added |
| 2026-05-28 | covered-call-overlay plan created — [docs/plan/covered-call-overlay/](docs/plan/covered-call-overlay/); build queue #3 added |
| 2026-05-27 | variance-gate story created — [docs/plan/variance-gate/](docs/plan/variance-gate/); CSP v1 spec reconciliation complete |
| 2026-05-26 | gamma script scaffold b68bb3d; `src/gamma/` store d8c2e69; delta gate wired b9c0014; CLI-12 notes in paper_snapshot c71331b; instrument loop migration 13b3daa; paper_csp_roll.py 3063fbf |
| 2026-05-26 | `src/risk/` PortfolioDeltaTracker + entry gate; 20 tests; 1471+20 suite green |
| 2026-05-25 | Audit findings [28–31]: Decimal enforcement across protocol, tracker, summary, pricing |
| 2026-06-13 | DBI-1 closed — `delete_trade` adds `instrument_key` to WHERE; `delete_trade_by_id` added; `close_collar_all` + `monetize_collar_put` use `record_trades` for atomic 2-leg writes; `_roll_collar` uses `record_trades` for close pair and open pair; incomplete-collar guard in `monetize_collar_put`; 5 new tests |
| 2026-06-11 | DAEMON-S1 closed — replace `add_pending_approval` with `create_approval`; guard `run()` loop; 2 new tests; SHA pending |
| 2026-06-11 | Fable codebase review — 17 findings (1 CRITICAL, 5 ERROR, 8 WARNING, 3 INFO); FR-1..FR-10 added to tasks.md; review at `docs/reviews/2026-06-11_fable_codebase_review.md` |
| 2026-06-03 | ES2 closed — CSPNiftyV1 thresholds corrected (DELTA_STOP 0.35→0.45, LOSS_STOP 2.0→1.75×, DELTA_WARN 0.25→0.35); TIME_STOP fixed to days_held≥21; entry_date added to PaperPosition; SHA 5115371. Review fix: DTE_REVIEW severity corrected INFO→WARN in ExitSignalEngine.evaluate_csp (ES1 gap); 1720 tests green; SHA ae12814 |
| 2026-05-24 | Audit findings [19–27]: Leg validation, STT branching, lot size resolver, expiry cadence, Decimal strike, strategy name constants |
| 2026-05-23 | TradingView MCP regime probe validated (Phase 3/3C). Weekly veto rule established |
| 2026-05-15–22 | Audit findings [12–18]: async Telegram, PortfolioStore factory, message budget, rollback, Parquet lineage, cron heartbeat, protocol stubs |
| 2026-05-15 | Audit findings [1–11] shipped (SHAs 4d69050–8639d44); council audit complete |
| 2026-05-14 | Task 1 closed — VIX ingestion, PaperTrade ivr_at_entry, R3 gate; Task 0 closed — UDiFF fix |

Full log: [docs/archive/TODOS_ARCHIVE.md](docs/archive/TODOS_ARCHIVE.md)
| 2026-06-14 | BUG-6 closed — TradeState.CLOSED added; PaperStore.mark_trade_closed() by (strategy, leg_role, instrument_key); _close_leg calls it after record_trade (dry_run=False only); CHECK constraint widened in schema + migration script; 6 new tests; SHA ceefeb8 |
| 2026-06-13 | BUG-2 closed — multi-expiry chain fetch in snapshot + daemon; None-leg guard in CSPNiftyV1 and _dispatch_evaluate skips only LTP/delta signals (TIME_STOP/ROLL_ELIGIBLE still fire); signal priority reordered (HARD_STOP→DELTA_BREACH→PROFIT_TARGET→TIME_STOP→ROLL_ELIGIBLE); _KEY_DATE_STRIKE_RE added for date-embedded keys; 10 new tests; SHA 61f4690 |
| 2026-06-14 | SM-2 closed — CollarOverlayV1 inherits ReEntryMixin; reentry_leg_role='overlay_collar_call'; __init__ extended with notifier/vix_data_dir; _check_reentry wired in apply_action for PROFIT_TARGET/TIME_STOP on short call close; 2 new tests; SHA 7e4527b |
| 2026-06-14 | FR-6 closed — ReEntryMixin._check_reentry offloads load_vix_series to asyncio.to_thread (non-blocking); all f-string structlog event names replaced with constants (reentry.*) + strategy= bound field; 2 new tests; SHA c6dd309 |
| 2026-06-14 | FR-7 closed — OptionLeg Greeks (delta/gamma/theta/vega/iv) changed to Decimal | None; _safe_decimal_greek added to upstox_market.py; evaluate_delta_breach_csp emits DELTA_MISSING WARN on None; 10 call sites guarded; 4 tests updated/added; SHA ac1c7fa |
| 2026-06-14 | FR-8 closed — _safe_price() added to strike_selector.py; ltp/bid/ask/mid stored as Decimal; entries with un-coerceable ltp skipped with WARN log; _apply_liquidity_gate and rank_strikes updated for Decimal comparisons; 6 new tests; SHA 699d074 |
| 2026-06-14 | FR-9 closed — market_today() added to src/market_calendar/holidays.py using ZoneInfo('Asia/Kolkata'); exported from __init__.py; 25 date.today() call sites replaced across csp_nifty_v1, cc_overlay_v1, pp_overlay_v1, collar_overlay_v1, ic_nifty_v1, nifty_track_comparison_v1, overlay_closer, executor, monitor; 3 new tests; SHA fd89ab3 |
| 2026-06-15 | RPT-SNAP closed — extract _compute_realized_pnl_by_leg from tracker.py; _save_leg_snapshots uses per-leg realized for base and overlay legs; mypy fixes (sum start=Decimal("0"), protocol.py dict[str,Any]); 6 new tests; SHA 7914994 |
| 2026-06-15 | BUG-7 closed — DB-only cleanup: ran migrate_add_closed_state.py to widen CHECK constraint; backfilled 71474 rows (overlay_cc + overlay_collar_call, 10 rows) and 58627 collar_put rows (6 rows) to CLOSED; spurious Jun8 SELL and wrong BUY qty already resolved by UNIQUE constraint from BUG-4; sanity checks pass |

| 2026-06-15 | CR1d SHA annotated — tasks.md had stale SHA:pending; actual commit is e62aee9 |
| 2026-06-15 | RPT-1 closed — generate_track_snapshot second pass folds closed overlay legs (net_qty==0) into overlay_pnls + total_realized; 2 new tests; SHA bce1d4a |
| 2026-06-15 | COLLAR-1 closed — CollarOverlayV1 automated with ReEntryMixin, evaluate_cc, CLOSE_COLLAR atomic closing via record_trades, unified collar role names, and dispatch evaluate fixes; 14 tests updated; SHA: 906c0a7 |
| 2026-06-15 | COLLAR-1-FIX closed — Refined close notification exit prices (approximate call exit indicator, omitted put delta, approximate net P&L prefix), fixed log warnings format mismatch in snapshot/CC/Collar strategies, and added invalid qty warning for passive collar put; documented collar long put exit MTM divergence gap; 47 unit tests passed |
| 2026-06-15 | NT-1 closed — evaluate_proxy_delta() added to ExitSignalEngine; proxy delta consecutive days breach count methods added to PaperStore; wired into NiftyTrackComparisonV1; migrate_paper_strategies.py added; unit tests green; SHA 70d4a9b |
| 2026-06-15 | AUTO-1 closed — EOD snapshot auto-close implemented for all overlays: auto_close_overlay routing via OverlayCloser, status resolution to ACTED, unified Telegram close notification dispatch, and EOD PP re-entry eligibility checks evaluation; tests green; SHA bbd9368 |
| 2026-06-15 | CR4 + PP-3 closed — docs close for council-refactor story: DECISIONS.md (11 new entries: CC CLI tools, CSP always-open, CC automation, ReEntryMixin, threshold constants, PP always-reprotect, proxy delta tracking, PROXY_PREMIUM_DECAY guard, Futures+CC block); CONTEXT.md (src/strategy/ full rewrite, PaperStore proxy_delta methods, cc_calibration scripts); TODOS.md session log |
| 2026-06-22 | paper-backbone-adj PA1.3 — NiftyTrackComparisonV1 overlay roll ACTION signals: ROLL_DUE_DTE/DECAY upgraded to ACTION when broker returns next-expiry chain target; _select_overlay_roll_target(); _fetch_next_chain(); apply_action ROLL_OVERLAY + ROLL_COLLAR; 8 new tests — 58b488a |
| 2026-06-23 | ic-e2e IC-E1 — auto_execute=False to IronCondorV1 + STRATEGY_IC constant in constants.py + 2 protocol-compliance tests — 17a9744 |
| 2026-06-26 | ic-full IC-F1 — wire IVR into IronCondorV1.describe_context via VIX Parquet; _compute_ivr_str() helper; 2 new tests — cd8415a |
| 2026-06-26 | ic-full IC-F1 fix — stub fetch_vix_latest in 4 record_paper_trade tests that default trade_date to today; R3 gate no longer fires in dev env — 1d4b0cb |
| 2026-06-26 | ic-full IC-F2 — ICExpiryConfig frozen dataclass + CONFIGS presets (weekly/monthly/leaps/yearly) + STRATEGY_IC_* constants + 6 structural invariant tests — 5921426 |
| 2026-06-26 | ic-full IC-F3 — parameterise IronCondorV1; auto_execute=True; action priority — 6296328 |
| 2026-06-26 | ic-full IC-F4 — weekly Tuesday DTE≤14 bucket in get_expiry_candidates; docstring updated; 6 new tests — 1dc9d3c |
| 2026-06-26 | ic-full IC-F5 — register all four IronCondorV1 strategy configurations in monitor daemon; 2 registration tests — bf093eb |
| 2026-06-26 | ic-full IC-F6 — paper_ic_entry.py config-driven multi-expiry IC entry helper; 12 new tests — 261b906 |
| 2026-06-26 | ic-full IC-F7 — paper_ic_snapshot.py EOD audit cron for all IC variants; 8 new tests — 90bdd29 |
| 2026-06-26 | ic-full IC-F8 — IC entry crons installed as system cron jobs (crontab); Wed 10:30 IST × 4 expiry types + EOD snapshot 15:45 IST Mon–Fri |
| 2026-06-26 | ic-full IC-F9 — widen _EXPIRY_RE in ic_nifty_v1.py; remove snapshot monkey-patch; 3 tests — ee5b99a |
| 2026-06-26 | ic-full complete — all 9 stories (F1–F9) shipped; docs/plan/ic-full archived to docs/archive/ic-full; CONTEXT.md updated (ICExpiryConfig, IronCondorV1 parameterisation, paper_ic_snapshot.py); intraday holiday guard fix — 8bd5660 |
| 2026-06-27 | ic-nifty-v2 IC-V2-0 — IronCondorV2ExpiryConfig frozen dataclass; delta-based config replacing V1 wing_width_points; D1/D2/D3/D4 fields; IC_V2_MONTHLY preset; 8 tests — 9bcb838 |
| 2026-06-27 | ic-nifty-v2 IC-V2-0 review fixes — expiry_type: Literal["monthly"]; IC_V2_MONTHLY kwarg comment; monthly_close_full_dte naming-decision note; profit_target_fraction deferred note; 2 new invariant tests (roll_debit_cap_fraction, long_wing_min_premium); 10 tests green |
| 2026-06-27 | DEFERRED DESIGN — ic-nifty-v2 weekly story: when weekly preset lands, decide whether monthly_close_full_dte stays as per-expiry field (alongside weekly_close_full_dte=3) or both collapse to a single expiry-agnostic close_full_dte. See ic_expiry_config_v2.py docstring. |
| 2026-06-27 | ic-nifty-v2 IC-V2-1 — IronCondorV2 entry: 25Δ/22Δ shorts, 10Δ wings with delta/premium/liquidity floors, SD sanity guard (warn-only); 11 tests — f3e0423 |
| 2026-06-27 | ic-nifty-v2 IC-V2-2 — IronCondorV2 adjustment: _evaluate_adjustment (DELTA_WARN/ROLL_WING/DELTA_STOP/FORCED_CLOSE), _execute_partial_roll (4-leg atomic), 7 roll guards, RollResult dataclass, state helpers reset_roll_state/set_original_credit; 11 tests — b8942d9 |
| 2026-06-27 | ic-nifty-v2 IC-V2-3 — IronCondorV2 DTE-tiered exit: monthly hard-close DTE≤7, FORCE_CLOSE DTE≤1 — 5b0de55 |
| 2026-06-27 | ic-nifty-v2 IC-V2-4 — IronCondorV2 check_signals: DELTA_WARN/ROLL_WING/DELTA_STOP/FORCED_CLOSE hierarchy, apply_action, describe_context, profit target; 11 tests — cf81258 |
| 2026-06-27 | ic-nifty-v2 IC-V2-5 — IronCondorV2 registration: add CONFIGS_V2 dict to ic_expiry_config_v2.py; wire IronCondorV2 import + registration loop into monitor_daemon.py; 6 registration tests — 91d0bc7 |
| 2026-06-27 | ic-nifty-v2 IC-V2-6 — Docs close: CONTEXT.md add V2 config + strategy description (D1/D2/D3/D4 council ruling); CONTEXT_TREE.md add entire src/strategy/ section (20 files); TODOS.md session log entries — commit pending (git lock) |
| 2026-06-27 | ic-nifty-v2 IC-V2-7 — ProfitLockConfig dataclass (zone triggers, floor formula constants, DTE guards); added profit_lock field to IronCondorV2ExpiryConfig; IC_V2_MONTHLY override; 4 tests; daemon test mock fix |
| 2026-06-27 | ic-nifty-v2 IC-V2-9 — State persistence: paper_strategies schema migration + PaperStore.get/set/reset_profit_lock_state() + tests — b0485e7 |
| 2026-06-27 | ic-nifty-v2 IC-V2-10 — profit-lock signal wiring into check_signals() (8-level precedence, PROFIT_LOCK_ZONE2 auto-execute, Zone1 INFO, monitor.py metadata fix, 9 tests) — f737ee5 |
| 2026-06-27 | ic-nifty-v2 IC-V2-11 — paper_ic_monthly_comparison.py script comparing V1 and V2 paper monthly ICs; extracts ICMonthlyStats; 6 tests — a555c6c |
| 2026-06-28 | ic-nifty-v2 cron gap — paper_ic_entry_v2.py: V2 entry helper with delta-based 10Δ wing placement, long_wing_min_premium floor, portfolio-delta check; ic_entry_gates.py: shared check_duplicate/resolve_ivr/resolve_expiry helpers; 14 tests (test_ic_entry_gates.py + test_paper_ic_entry_v2.py); cron entries added for V2 monthly entry (Wed 10:30) + paper_ic_monthly_comparison (15:50 Mon–Fri) |
| 2026-06-28 | ic-nifty-v2 IC-V2-14 — EOD snapshot V2 coverage: refactor process_variant to accept strategy_cls; add V2 loop over CONFIGS_V2 / IronCondorV2 in paper_ic_snapshot.py; 3 tests |
| 2026-07-02 | docs/bugs/ folder created (prompt.md, bugs.md, task.md — mirrors docs/plan/ story conventions, separate from story workflow; ID sequence continues from root BUGS.md's BUG-001, see docs/bugs/prompt.md for the split). BUG-002 logged: `_position_delta` (src/risk/delta_tracker.py) put/call misclassification — substring-matches "PE"/"CE" against numeric instrument_key, dead code, all options priced as full-delta futures; caused ic_weekly.log's 6.901-lot delta gate rejection. Cross-strategy aggregation scope in aggregate_delta (paper_ic_entry.py) flagged as open question, not yet decided. BUG-003 logged: `_post_expiry_gate` (scripts/strategies/ic/ic_entry_gates.py) checks current-month expiry instead of prior settled cycle, blocking monthly IC entry for the whole month except a 1–3 day tail window; caused ic_monthly.log/ic_v2_monthly.log rejections — note paper_ic_entry_v2.py's own gate already fixed this differently (IC-V2-13, 2026-06-28, BOD-expiry-based), shared ic_entry_gates.py version was missed. No code fixed yet — investigation only, root cause confirmed via graph trace, fix pending go-ahead. See docs/bugs/task.md for fix checklist. |

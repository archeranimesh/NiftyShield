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
| **3b** | **variance-gate VG0: CSP v1 spec reconciliation** (lot size, time stop, R-numbers, R4) | Animesh + Cowork | Before Phase 0.8 gate evaluation | ⬜ Not started — story: `docs/plan/variance-gate/` |
| **4a** | **chain-data: EOD + intraday chain snapshot cron** (`src/backtest/chain_writer.py`, `scripts/upstox_chain_snapshot.py`, `scripts/upstox_chain_intraday.py`) | Cowork | **ASAP — data cannot be back-filled** | ⬜ Not started — story: `docs/plan/chain-data/` |
| **4cc** | **covered-call-overlay: entry helper + exit handler** (`src/paper/constants.py`, `scripts/paper_cc_entry.py`, `scripts/paper_cc_roll.py`) | Cowork | **ASAP — each skipped monthly cycle is a lost paper data point** | ⬜ Not started — story: `docs/plan/covered-call-overlay/` |
| **4b** | MVP: Multi-bagger Value Picks Tracker (`src/mvp/`) | Cowork | After Task 3 | ⬜ Not started |
| **4c** | **paper-backbone: Strategy Monitor daemon + pluggable strategy backbone** (`src/strategy/`, `src/council/`, `src/notifications/telegram_gateway.py`) | Cowork | **Jun–Jul 2026** | ⬜ Not started — story: `docs/plan/paper-backbone/` |
| **4d** | **paper-exit-signals: automated exit detection + closure for CC, PP, Collar overlays** (`src/strategy/exit_signals.py`, `CCOverlayV1`, `PPOverlayV1`, `CollarOverlayV1`, `OverlayCloser`, `paper_exit_events` table) | Cowork | **After 4c** — each live overlay cycle without automated exits is discretionary data | ⬜ Not started — story: `docs/plan/paper-exit-signals/` — **blocked by 4c (paper-backbone PB1.1–PB1.7)** |
| **5** | backtest-eval-core: `BacktestStore` + `src/analytics/` (tasks 1.5 + 1.5b) | Cowork | Aug 2026 (Phase 1, after tasks 1.3 + 1.4) | ⬜ Not started — **blocked by tasks 1.3 (Bhavcopy ingest) + 1.4 (BacktestEngine)** |
| **6** | **signals-eval-core: regime engine + signal generators + validation pipeline** (`src/strategy/`, `src/backtest/points_bt.py` + `allocation_bt.py` + `walkforward.py` + `montecarlo.py` + `sensitivity.py` + `reports.py`) | Cowork | Q4 2026 (Phase 2, after Phase 1.12 gate) | ⬜ Not started — **blocked by backtest-eval-core (task 5) + Phase 1.12 gate** — story: `docs/plan/signals-eval-core/` |

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

## Task 3b — Variance Gate: CSP v1 Spec Reconciliation

**Full spec:** `docs/plan/variance-gate/variance_gate_stories.md` → VG0
**Priority:** immediately actionable — docs-only, no code changes, unblocks Phase 0.8 gate evaluation
**Story folder:** `docs/plan/variance-gate/` (prompt, tasks, stories, spec)

Four mismatches to resolve in `docs/strategies/csp_nifty_v1.md`:

- [ ] **Lot size:** confirm 65 units; update any reference to 50 units with transition date annotation.
- [ ] **Time stop:** define as "21 calendar days from entry date" — align with `BACKTEST_PLAN.md`.
- [ ] **R-number naming:** pick one canonical scheme (R1–R7); update `csp_nifty_v1.md` + `BACKTEST_PLAN.md`.
- [ ] **R4 definition:** single definition — event filter or 200-DMA filter; if both, name R4a + R4b.

**Commit:** `docs(strategies): reconcile CSP v1 spec — lot size, time stop, R-numbers, R4`

**Variance gate parallel track** (ongoing, no Cowork action needed until events occur):
- VG1 Tier 0.5 review: triggers after 2nd CSP paper cycle closes
- VG2 Gate A+B: triggers at ≥6 cycles; Gate B3 (delta-stop) replay blocked until Phase 1.3a
- VG3 Gate C: triggers on first qualifying stress event (live) or after Phase 1 replay harness
- VG4 Gate D: blocked by Phase 1 task 1.11 (Z-score computation)

---

## Task 4cc — Covered Call Overlay Scripts

**Full spec:** `docs/plan/covered-call-overlay/stories.md`
**Priority:** immediately after chain-data (4a) — each skipped monthly cycle loses a paper data point
**Story folder:** `docs/plan/covered-call-overlay/` (prompt, tasks, stories, schema)
**Strategy doc:** `docs/strategies/covered_call_overlay_v1.md` (broker mechanics confirmed 2026-05-28)

Relationship to existing infrastructure: standalone scripts separate from `paper_3track_overlay.py`
(delta-based strike selection vs OTM-based; NiftyBees qty constraint; distinct strategy namespace).
First paper trade can be entered manually via `find_strike_by_delta.py` + `record_paper_trade.py`
in the interim — automation (CC1–CC3) makes subsequent cycles repeatable.

| Phase | Files | Status |
|---|---|---|
| CC1 | `src/paper/constants.py` — `STRATEGY_CC_OVERLAY` + `compute_max_lots` + tests | ⬜ Not started |
| CC2 | `scripts/paper_cc_entry.py` — delta selection + IVR gate + qty constraint + dry-run output | ⬜ Not started |
| CC3 | `scripts/paper_cc_roll.py` — profit-target / time-stop / delta-stop exit handler + tests | ⬜ Not started |
| CC4 | Docs close | ⬜ Not started |

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

## Task 4c — paper-backbone: Strategy Monitor Daemon + Pluggable Strategy Backbone

**Full spec:** `docs/plan/paper-backbone/paper_backbone_stories.md`
**Target:** Jun–Jul 2026 (PT-0 blocks all strategy phases)
**Prerequisite:** Task 2 (PortfolioDeltaTracker) — ✅ shipped 2026-05-26

One daemon backbone that all pluggable strategies (CSP, IC, 3-Track, Signal Pipeline) run on.
Replaces manual snapshot monitoring with automated signal detection + council consultation + Telegram approval.

CSP (`paper_csp_nifty_v1`) and 3-Track (`paper_nifty_spot/futures/proxy`) are already live as
paper trades — their backbone integration classes (PB2.1, PB4.1) plug in once PT-0 ships.

### Phases

| Phase | Tasks | Target | Status |
|---|---|---|---|
| PT-0 — Common Infrastructure | PB1.1–PB1.7: `PaperStrategy` protocol, `StrategyMonitor`, `PaperExecutor`, `RapidCouncil`, `TelegramGateway`, DB migrations, daemon scripts | Jun–Jul 2026 | ⬜ Not started |
| PT-S0 — CSP v1 backbone | PB2.1: `CSPNiftyV1` — already live, adds auto-signal detection | After PT-0 | ⬜ Not started |
| PT-S1 — Iron Condor v1 | PB3.1: `IronCondorV1` — entry via `paper_ic_entry.py`; backbone handles exits | Aug 2026 | ⬜ Not started |
| PT-S3 — 3-Track backbone | PB4.1: `NiftyTrackComparisonV1` — already live, adds WARN roll reminders | After PT-0 | ⬜ Not started |
| PT-S2 — Signal Pipeline | Blocked on `signals` story (`docs/plan/signals/`) + OpenRouter API key | Aug–Sep 2026 | ⬜ Not started |
| PT-B — Backtesting mode | Historical replayer + AutoApprover swap-in | After Phase 0.8 gate | ⬜ Blocked |

---

## Task 4d — paper-exit-signals: Automated Exit Detection + Closure (extended)

**Full spec:** `docs/plan/paper-exit-signals/` (prompt, schema, stories, tasks)
**Blocked by:** Task 4c PB1.1–PB1.7 (StrategyMonitor, PaperExecutor must be committed first)
**Council authority:** `docs/council/2026-05-28_paper-trade-exit-philosophy.md` — Chairman Synthesis. All 10 thresholds are binding. No threshold changes without a new council decision.

Extends paper-backbone with the full exit + lifecycle pipeline. Covers exit detection
(ExitSignalEngine), overlay closures (CCOverlayV1, PPOverlayV1, CollarOverlayV1,
OverlayCloser), CSP post-exit re-entry eligibility (R5), base position expiry roll
detection, and entry discipline enforcement (liquidity gate + R3 hard block).

Tier 1 (EOD detection) is mandatory for Phase 0. Tier 2 (intraday daemon) is wired but
disabled via `MONITOR_OVERLAYS=0` env gate.

**Archive gates (ES9 — must run last):** `docs/council/2026-05-28_paper-trade-exit-philosophy.md`
and `docs/strategies/csp_nifty_v1.md` archived via `git mv` only after all ES stories are committed.

**What remains manual after full story completion:**
- R5 re-entry execution (eligibility automated; strike + record is manual)
- Base roll execution (detection automated; close + open commands are manual paste)
- R4 event filter (Budget/RBI/elections) — separate story, requires `events.yaml`
- Collateral leg (`long_niftybees`) per cycle — separate lifecycle story
- Transaction cost model in paper P&L — separate analytics story

**Priority order:**

| Priority | Phase | Rationale |
|---|---|---|
| **P0** | Prereq gate | Must verify `StrategyMonitor` + `PaperExecutor` exist before ES0 |
| **P1** | ES0 → ES1 → ES2 | Foundation: schema + rule engine + CSP threshold fix. Everything depends on these. |
| **P2** | ES10 → ES12 | CSP lifecycle (Cycle 2 open now); entry discipline (prevents repeat of 75u bug class) |
| **P3** | ES3 → ES4 → ES5 → ES6 | Overlay strategy classes + OverlayCloser |
| **P4** | ES7 → ES8 | EOD + daemon wiring — needs P1 + P3 |
| **P5** | ES11 | Base roll detection — next event 2026-06-30 |
| **P6** | ES9 | Docs close — always last |

| Phase | Files | Status |
|---|---|---|
| ES0 | `paper_exit_events` DDL in `PaperStore.__init__`; store methods + tests | ⬜ Not started |
| ES1 | `src/strategy/exit_signals.py` — `ExitSignalEngine` (pure/stateless); all CSP/CC/PP/Collar rules; tests | ⬜ Not started |
| ES2 | Fix `CSPNiftyV1` thresholds: `DELTA_STOP` 0.35→0.45, `DELTA_WARN` 0.35, `LOSS_STOP` 2.0×→1.75×; re-test | ⬜ Not started |
| ES3 | `src/strategy/cc_overlay_v1.py` — `CCOverlayV1`; dual-signal audit; tests | ⬜ Not started |
| ES4 | `src/strategy/pp_overlay_v1.py` — `PPOverlayV1`; `CRASH_MONETIZE` + bid/ask gate; tests | ⬜ Not started |
| ES5 | `src/strategy/collar_overlay_v1.py` — `CollarOverlayV1`; 4-path closure routing; tests | ⬜ Not started |
| ES6 | `src/strategy/overlay_closer.py` — `OverlayCloser`; atomic Collar close + rollback; tests | ⬜ Not started |
| ES7 | `scripts/paper_3track_snapshot.py` — Tier 1 EOD signal write + Telegram alert + deduplication; tests | ⬜ Not started |
| ES8 | `scripts/monitor_daemon.py` — register CC/PP/Collar overlays; `MONITOR_OVERLAYS` gate | ⬜ Not started |
| ES10 | `src/strategy/csp_nifty_v1.py` — R5 re-entry eligibility check post profit-target; Telegram alert; tests | ⬜ Not started |
| ES11 | `scripts/paper_3track_snapshot.py` + `InstrumentLookup.get_next_contract()` — base expiry alert; tests | ⬜ Not started |
| ES12 | `find_strike_by_delta.py` liquidity gate enforcement; `record_paper_trade.py` R3 hard block + `--force-entry`; tests | ⬜ Not started |
| ES9 | Docs close (LAST): DECISIONS.md, CONTEXT.md, TODOS.md; `git mv` council + csp_nifty_v1 to archive | ⬜ Not started |

**Known gaps deferred to separate stories (not blocked on this task):**

| Gap | Story needed | Priority |
|---|---|---|
| R4 event filter (Budget/RBI/elections) | `docs/plan/entry-event-filter/` — needs `events.yaml` design | After ES12 |
| Collateral leg (`long_niftybees`) per cycle | `docs/plan/csp-collateral-leg/` | Before Phase 0.8 gate |
| Transaction cost model in paper P&L | `docs/plan/paper-cost-model/` | Phase 1 |
| IVR at entry NULL for Cycle 1 (data gap) | Manual note — permanent gap, log in gate criteria | Accepted |

---

## Pending — Immediate + Near-Term Actions (as of 2026-05-28)

> Concrete items that are not yet captured in any story or are waiting for a commit/edit.
> Sorted by urgency. Each item has a clear DoD so it can be ticked off immediately.

---

### P0 — Must Do Before Next Session

~~**P0-1: Commit `find_strike_by_delta.py` DEBT-4 fix**~~ ✅ DONE — `a086e40` (2026-05-28)
```
fix(scripts): import LOT_SIZE from constants in find_strike_by_delta

Why: DEFAULT_LOT_SIZE = 75 was hardcoded, contradicting constants.LOT_SIZE = 65
     (effective Jan 2026). Caused record_paper_trade.py (which imports from this
     module) to default to 75u, producing wrong quantity on CSP Cycle 2 entry.
     DB rows id=31,32 corrected directly from 75u → 65u.
What:
- scripts/find_strike_by_delta.py: replace hardcoded 75 with LOT_SIZE import
Ref: DEBT-4 (TODOS.md) — resolved
```

**P0-2: Fix stale R3 caveat in `docs/strategies/csp_nifty_v1.md`**
- What: Line 54 reads `"R3 not yet enforced"`. IVR warnings shipped in sha `8449cbf` (2026-05-14).
- Change to: `"R3 warning enforced at entry via record_paper_trade.py (sha 8449cbf, 2026-05-14). Hard block deferred to ES12."`
- DoD: targeted `Edit` call on that paragraph; no test required; commit as `docs(strategy): update R3 caveat — warnings live since 8449cbf`.

---

### P1 — Data Integrity Fixes

~~**P1-1: Fix corrupt `paper_nifty_futures` snapshots for 2026-05-27**~~ ✅ DONE (2026-05-28)
Both rows zeroed directly in DB — `paper_leg_snapshots` + `paper_nav_snapshots` for `base_futures` 2026-05-27 set to `unrealized_pnl=0, realized_pnl=0, total_pnl=0, ltp=NULL`. Root cause: snapshot ran after May futures expiry, got `None` LTP, propagated full notional as loss. Guarded by P1-2.

**P1-2: Guard `paper_3track_snapshot.py` against None LTP on expired legs**
- What: When a base position expires, any subsequent snapshot run will fetch `ltp=None`
  and corrupt the P&L. Need a guard in the snapshot MTM calculation.
- Fix: in the LTP fetch / P&L computation path, if `ltp is None` for a base leg, log a
  WARNING (`"LTP unavailable for {key} — likely expired. Skipping MTM for this leg."`)
  and write `unrealized_pnl=0` rather than propagating `None` into arithmetic.
- Files: `scripts/paper_3track_snapshot.py` (or the underlying `PaperTracker.compute_pnl`)
- DoD: unit test — mock LTP returns `None` for one leg → snapshot writes `unrealized_pnl=0`;
  no exception; WARNING logged.

**P1-3: Accept IVR-at-entry NULL for CSP Cycle 1 (data gap)**
- Cycle 1 (id=14, entered 2026-05-11): `ivr_at_entry=NULL` — VIX history pipeline was not
  yet live at entry time. This is a permanent data gap; do not attempt to back-fill.
- Cycle 2 (id=32, entered 2026-05-28): `ivr_at_entry=NULL` — IVR was available from the
  intraday snapshot (VIX=14.98) but insufficient history (0/252 days) blocked computation.
  This is also a permanent gap for this entry.
- Action: document both gaps in Phase 0.8 gate evaluation. Criterion A ("IVR at entry
  recorded") will be marked PARTIAL for Cycles 1 and 2, satisfied from Cycle 3 onwards
  once `vix_ingest.py` bootstraps ≥252 days of history.
- DoD: add a note to `BACKTEST_PLAN.md` Phase 0.8 gate criterion A: "IVR NULL for Cycles 1
  and 2 — accepted data gap; criterion A satisfied from Cycle 3 onward."

---

### P2 — New Story Files Needed

**P2-1: Create `docs/plan/entry-event-filter/` — R4 event filter story**
- What: R4 in `csp_nifty_v1.md` skips cycles when Budget / RBI MPC / election-result day
  falls inside the trade DTE window. Currently not enforced anywhere.
- Requires: `src/market_calendar/events.yaml` — annual list of tail-risk events (Budget date,
  RBI MPC dates, election result dates). Design decision needed: (a) what counts as "inside
  the window", (b) how far in advance is the event list updated, (c) how does the check
  integrate with `record_paper_trade.py`.
- Story scope: `events.yaml` schema + loader function + integration into `record_paper_trade.py`
  as a soft warning (Phase 0) with hard block option (Phase 1).
- DoD: story dir created with `prompt.md` + `tasks.md`. No code yet.
- Dependency: ES12 must be committed first (shares `record_paper_trade.py`).

**P2-2: Create `docs/plan/csp-collateral-leg/` — collateral leg tracking story**
- What: `csp_nifty_v1.md` specifies a `long_niftybees` leg recorded once per strategy year
  to track the combined P&L (short put + ETF collateral). Not recorded for current cycles.
- Missing for: Cycles 1 and 2 (entered 2026-05-11 and 2026-05-28).
- Story scope: (a) back-fill the `long_niftybees` entry for 2026-05-11 at NiftyBees price
  on that date, (b) add `long_niftybees` to `paper_snapshot.py` LTP batch so it appears
  in `paper_nav_snapshots`, (c) annual reset procedure.
- DoD: story dir created. Back-fill command for Cycle 1 documented.
- Formula: `qty = floor((65 × nifty_spot) / niftybees_ltp)` at strategy inception date.

---

### P3 — ES Prerequisite Gate

**P3-1: Verify paper-backbone prerequisites before ES0**
- What: ES0 cannot start until `StrategyMonitor` (PB1.2) and `PaperExecutor` (PB1.3) are
  committed. These are from Task 4c (paper-backbone) which is listed as "Not started".
- Action: before opening any ES story file, run:
  ```
  search_graph("StrategyMonitor")   # must return results
  search_graph("PaperExecutor")     # must return results
  search_graph("CCOverlayV1")       # must return zero results
  ```
  If `StrategyMonitor` / `PaperExecutor` do NOT exist, Task 4c must be completed first.
  Do not start ES0 without this check.

---

### P4 — Operational Calendar (paper trading)

**P4-1: CSP Cycle 2 — time stop fires 2026-06-19**
- Entry date: 2026-05-29. Time stop: 21 calendar days → fires on **2026-06-19**.
- Monitor daily via `paper_snapshot.py --strategy paper_csp_nifty_v1`.
- Profit target: mark ≤ 50% of ₹158.6 = ₹79.30. Delta stop: |delta| ≥ 0.45.
- If profit target fires before June 19: run R5 eligibility check (DTE ≥ 14, IVR ≥ 0.25).

**P4-2: June 30 expiry — all overlays and bases roll**
- All June 30 contracts (NSE_FO|58627, NSE_FO|71474, NSE_FO|37805, NSE_FO|79509,
  NSE_FO|62329, NSE_FO|79653) expire on **2026-06-30**.
- `paper_3track_overlay_roll.py` handles overlay legs at DTE ≤ 5 (circa **2026-06-23**).
- Base positions (futures `NSE_FO|62329`, DITM call `NSE_FO|79509`) need manual rolls
  at expiry — see ES11 for the automated alert (not yet implemented).
- CSP Cycle 2 (`NSE_FO|79653`) rolls via `paper_csp_roll.py` at DTE ≤ 5.
- Mark your calendar: **week of 2026-06-23** is the roll week.

**P4-3: Verify `paper_3track_snapshot.py` cron is running for June futures**
- The May futures base expired; the June futures base (`NSE_FO|62329`) was opened 2026-05-29.
- The cron fetches LTP for all open `paper_trades` positions. Confirm that the new June
  futures row is picked up in the next EOD snapshot run (2026-05-29 evening).
- Run manually first: `python scripts/paper_3track_snapshot.py --no-save` and verify
  `base_futures` shows a non-None LTP.

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

Full methodology: `docs/plan/signals-eval-core/` (tasks SE1–SE3 + SE5–SE6). Stages 2.S0–2.S7 (regime engine → signal generators → points backtester → option spread backtester → walk-forward → paper → live). Starts after Phase 1.12 gate.

### Investment Strategy Research Pipeline (Phase 2 Track B)

Full methodology: `docs/plan/signals-eval-core/` (tasks SE1–SE2 + SE4–SE6). Stages 2.I0–2.I5 (SMA / Dual Momentum / PE Band strategies on NiftyBees, ₹5L pool). Zero paid data. Starts after Phase 1.12 gate.

### signals-eval-core — Implementation Priority Order (Task 6)

Implementation sequence within `docs/plan/signals-eval-core/tasks.md`. Each phase gates the next.

| Priority | Task(s) | Prerequisite | What unblocks |
|----------|---------|--------------|---------------|
| **1** | SE1.1 — data coverage verification | Task 1.3a (Nifty OHLC Parquet) committed | Confirms data exists before writing any code |
| **2** | SE1.2 — `pe_loader.py` (NSE PE CSV → Parquet) | SE1.1 pass | Unblocks SE4.3 (PE Band signal) |
| **3** | SE1.3 — `rf_rate.py` (AMFI liquid fund monthly rate) | `src/mf/` infrastructure | Unblocks SE4.2 (Dual Momentum) |
| **4** | SE2.1 — `src/strategy/` package setup + `CLAUDE.md` | SE1.1 pass | Unblocks all SE2–SE4 |
| **5** | SE2.2 — `RegimeTagger` + `SignalEvalStore` (regime CRUD) | SE2.1 | Unblocks SE3.x signal generators |
| **6** | SE2.3 — `regime_distribution_report.py` (visual gate) | SE2.2 | Phase 2.S1 gate: no single cell >40% of days |
| **7** | SE3.1 — `DonchianSignalGenerator` + `SwingSignal` model | SE2.2 | Unblocks SE5.1 (Tier 1 backtester) |
| **8** | SE4.1 — `SMASignalGenerator` + `AllocationDecision` model | SE2.2 | Unblocks SE5.2 (allocation backtester); **parallel with SE3.1** |
| **9** | SE3.2 — `ORBSignalGenerator` + calendar exclusions | SE3.1 | Donchian must complete before ORB starts |
| **10** | SE4.2 — `DualMomSignalGenerator` | SE4.1 + SE1.3 | Sequential after SMA |
| **11** | SE3.3 — `GapFadeSignalGenerator` | SE3.2 | Sequential after ORB |
| **12** | SE4.3 — `PEBandSignalGenerator` | SE4.2 + SE1.2 | Sequential after Dual Momentum |
| **13** | SE5.1 — `PointsBacktester` (Tier 1 swing) | SE3.1 + backtest-eval-core B1.x | Core validation path — Donchian Tier 1 gate |
| **14** | SE5.2 — `AllocationBacktester` (investment) | SE4.1 + backtest-eval-core B1.x | **Parallel with SE5.1** |
| **15** | SE5.3 — `SpreadSelector` + `SpreadSpec` | SE3.1 (SwingSignal) | Used by SE7.1 only |
| **16** | SE6.1 — `WalkForwardEngine` | SE5.1 or SE5.2 + backtest-eval-core B2.x | Blocks SE6.2–SE6.4 |
| **17** | SE6.2 — `MonteCarloSimulator` | SE6.1 | **Parallel with SE6.3** |
| **18** | SE6.3 — `SensitivityAnalyser` | SE6.1 | **Parallel with SE6.2** |
| **19** | SE6.4 — `SwingValidationReport` + `InvestmentValidationReport` | SE6.1 + SE6.2 + SE6.3 | Phase 2.S4 / 2.I3 human review gate |
| **20** | SE7.1 — `SpreadBacktester` (Tier 2, conditional) | SE5.1 Donchian pass + Bhavcopy exclusion rate <20% | Start only if Tier 1 passes; otherwise skip |
| **21** | SE8 — Docs close | All prior SE tasks committed | Phase 2 checkboxes in `BACKTEST_PLAN_PHASE1.md` |

**Critical path:** SE1.1 → SE2.1 → SE2.2 → SE3.1 → SE5.1 → SE6.1 → SE6.2/SE6.3 → SE6.4.
SE4.x (investment signals) and SE5.2 are a parallel branch off SE2.2 that rejoins at SE6.1.
SE7.1 is conditional and does not block SE8.

### Order Execution Layer (`src/execution/`)

Blocked: static IP not provisioned. Unblocked when IP is confirmed. `place_order`, `modify_order`, `cancel_order` on `UpstoxLiveClient`; GTT orders; pre-order margin validation via `src/risk/`. All logic already designed against `BrokerClient` protocol.

### paper_snapshot.py → Telegram notification

Wire `build_notifier` from `src/notifications/` into `paper_snapshot.py`. Add `[DRY RUN]` label. Non-fatal, fire-and-forget. Defer until `paper_snapshot.py` is touched for another reason.

### Telegram — Paper Trade Roll Alert (all tracks) ⚠️ SUPERSEDED by paper-backbone PT-S0/PT-S3

> **Do not implement the manual `paper_alerts` cron logic below.** Once `paper-backbone` ships,
> roll alerts are delivered via `NiftyTrackComparisonV1.check_signals()` WARN events (PT-S3)
> and `CSPNiftyV1.check_signals()` WARN events (PT-S0) routed through `TelegramGateway`.
> The `paper_alerts` table design below is retained for reference only.

### Telegram — Paper Trade Roll Alert (original design — reference only)

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

### ~~DEBT-4~~: `find_strike_by_delta.py` — `DEFAULT_LOT_SIZE = 75` vs `constants.LOT_SIZE = 65` ✅ RESOLVED 2026-05-28

Fixed: replaced `DEFAULT_LOT_SIZE = 75` with `from src.paper.constants import LOT_SIZE as DEFAULT_LOT_SIZE`
in `scripts/find_strike_by_delta.py`. DB rows id=31,32 corrected from 75u → 65u directly.
Discovered via Cycle 2 CSP entry producing wrong quantity in production.

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
| 2026-05-28 | Session: CSP Cycle 1 closed (profit target ₹8,898.50); Cycle 2 opened (23300 PE JUN 30 @ ₹158.6, 65u); May futures settled (₹23,911.3, back-dated 2026-05-26); June futures opened (₹24,006.2); DEBT-4 fixed (DEFAULT_LOT_SIZE 75→65); DB rows id=31,32 corrected; paper-exit-signals stories extended with ES10/ES11/ES12 + gap analysis; Task 4d prioritisation updated |
| 2026-05-28 | paper-exit-signals story created — `docs/plan/paper-exit-signals/` (prompt, schema, stories, tasks); council exit-philosophy decisions absorbed into DECISIONS.md (10 rows); Task 4d added to sequential queue; csp_nifty_v1.md + council file archived at ES9 |
| 2026-05-28 | covered-call-overlay plan created — `docs/plan/covered-call-overlay/` (prompt, tasks, stories, schema); broker mechanics confirmed; Task 4cc added to sequential queue |
| 2026-05-27 | variance-gate story created — `docs/plan/variance-gate/` (prompt, tasks, stories, spec); `docs/plan/variance_gate.md` archived; README.md + TODOS.md updated |
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





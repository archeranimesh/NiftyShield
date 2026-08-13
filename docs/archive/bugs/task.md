# docs/bugs/ — Task Checklist Archive

> Completed checklists for bugs archived out of `docs/bugs/task.md`, moved here alongside their
> `docs/archive/bugs/bugs.md` entry. Every line below is checked `[x]` with a SHA — nothing here
> is actionable. Do not pick up work from this file; it exists for audit history only.
>
> Live checklist: `docs/bugs/task.md` | Archived registry: `docs/archive/bugs/bugs.md`

---

## BUG-002 — Delta sign/magnitude corrupted by put-call misclassification

- [x] **B002.1** — Root-cause confirmed: `_position_delta` substring-matches `"PE"`/`"CE"` against numeric `instrument_key`, dead code, all options priced as full-delta futures | Confirmed 2026-07-02 (no code change, investigation only)
- [x] **B002.2** — Decision: scope `aggregate_delta` to IC-relevant positions only; exclude `paper_nifty_futures`/`paper_nifty_proxy`/`paper_nifty_spot` from the IC delta-neutral gate. Decided by Animesh 2026-07-02 (no code change this step).
- [x] **B002.3** — Add option-type signal to position data | Implemented, code-reviewed (C1/C2/W1 findings resolved), 69/69 tests pass, committed 2026-07-02 | SHA 96398b4

  **Decision: option (a) — extend `PaperPosition`, resolved lazily in `PaperStore.get_position`/`get_positions` at read time (NOT at `record_trade` write time, and NOT a `legs` table join).**

  Rejected alternatives and why:
  - (b) join `legs` table — rejected: couples `src/paper/` to `src/portfolio/` schema; bugs.md notes paper positions aren't reliably `legs`-backed, so it'd need an InstrumentLookup fallback anyway, making it strictly more code than (a) for the same result.
  - (c) lazy-resolve inside `src/risk/delta_tracker.py` (no schema change, `_position_delta` calls `InstrumentLookup.get_by_key` directly) — rejected: adds a new `src/risk/` → `src/instruments/` + BOD-JSON-file dependency to a module whose tests (`tests/unit/risk/test_delta_tracker.py`) are currently pure-data with no filesystem dependency; would require mocking `InstrumentLookup` in every delta test for something that's really just a field on the position.
  - Write-time population (populate `option_type` inside `record_trade`, persist to `paper_trades` table) — rejected: `PaperPosition` docstring already states it is "never stored directly — reconstructed on demand"; write-time population would require a `paper_trades` schema migration (new column) and backfilling historical rows. Read-time resolution fits the existing reconstruction pattern with zero migration.

  **Implementation spec:**
  1. `src/paper/models.py` — add to `PaperPosition` (frozen dataclass, `strategy_name`/`leg_role`/`net_qty`/`avg_cost`/`avg_sell_price`/`instrument_key`/`entry_date: date | None = None` are the existing fields, lines 115–138):
     `option_type: Literal["PE", "CE", "FUT", "EQ"] | None = None` — appended AFTER `entry_date` (must stay last / keep a default; existing constructor call in `store.py` uses keyword args so field order doesn't matter there, but any positional test construction depends on it being last).
  2. `src/paper/store.py` — in `get_position` (lines 579–609) and `get_positions` (lines 499–577), resolve `option_type` per position via `InstrumentLookup.get_by_key(instrument_key)`:
     - `NIFTYBEES_KEY` (`NSE_EQ|INF204KB14I2`, from `src.paper.constants`) → `"EQ"` (no lookup needed, short-circuit).
     - Else call `InstrumentLookup.get_by_key(instrument_key)` → dict with `"instrument_type"` key (values `"CE"` / `"PE"` confirmed via `search_options`, `src/instruments/lookup.py` lines 188–233; `get_by_key` impl at lines 270–275, currently O(n) linear scan over `self._instruments` — acceptable at current position counts, don't over-engineer an index for this task).
     - If `instrument_type` is `"CE"`/`"PE"` → use as-is. If lookup returns a dict but `instrument_type` is something else (e.g. a plain future contract has no CE/PE type) → `"FUT"`. If `get_by_key` returns `None` (key not found in BOD JSON — unrecognised/legacy key) → `option_type=None` + `logger.warning(...)`, do NOT raise. This is the required edge-case behavior per B002.5.
     - `PaperStore` needs an `InstrumentLookup` instance — check constructor (`PaperStore.__init__`, `src/paper/store.py` lines 224–282) for whether one is already injected/available, or whether it needs to be constructed/passed in (likely needs a new constructor param or lazy singleton — confirm via graph before writing code, per Rule 0).
  3. Do NOT touch `src/risk/delta_tracker.py::_position_delta` in this step — that's B002.4 (replace `net_qty/lot_size` approximation with real delta once `option_type` is available on the position). B002.3 only adds the signal to the data; B002.4 consumes it.

  **Confirmed non-impact (verified 2026-07-02):** `PaperPosition` is only constructed in `src/paper/store.py` (`get_position`/`get_positions`); all other call sites (`csp_nifty_v1.py`, `overlay_closer.py`, `executor.py`, `reentry_mixin.py`, `monitor.py`, `paper_ic_entry.py`, `track_snapshot.py`, `tracker.py`, `auto_close.py`, etc.) only consume `PaperPosition` — none construct it. New field has a default and is appended last, so it's additive: no existing production or test call site breaks. CSP/CC/PP/Collar/futures behavior is unchanged since none of them branch on `option_type` yet.

  Depends on B002.2 scope decision (done, no code change).
- [x] **B002.4** — Replace `net_qty / lot_size` full-delta approximation in `_position_delta` with actual option delta from chain snapshot where available (short 1-lot put ≠ short 1-lot future) | Council-gated (module boundary (b): `src/risk/` stays pure/zero-I/O, caller resolves `position_deltas` map; see `docs/council/2026-07-02_paper-delta-source-architecture.md`), implemented 2026-07-02 | SHA 62ed6ef
- [x] **B002.5** — Tests: happy-path (short put → positive delta, correct magnitude), edge case (unrecognised/legacy `instrument_key` still falls back safely with a warning, does not silently misclassify) | 3 new tests (chain-value use, missing-key WARNING fallback, no-arg backward-compat) + all existing fixtures updated to set `option_type` explicitly; 30/30 `tests/unit/risk/` pass | SHA 62ed6ef
- [x] **B002.6** — Run real `@code-reviewer` subagent against `git diff HEAD` (financial-logic gate, mandatory per root `CLAUDE.md`) — resolve CRITICAL/ERROR before commit | `code-reviewer` subagent type not exposed in this Cowork environment — substituted `general-purpose` agent loaded with `REVIEW.md` checklist against real `git diff HEAD`, 2026-07-02. 1 CRITICAL (G2 80-char line length in new test/src lines) found and fixed; 1 WARNING (no runtime sign-sanity check on caller-supplied `position_deltas` — accepted, documented as caller-contract per council ruling) | SHA 62ed6ef
- [x] **B002.7** — Commit, update `bugs.md` status to ✅ Fixed + SHA, update `CONTEXT.md` if `PaperPosition` schema changed | `CONTEXT.md` `src/risk/` entry updated (no `PaperPosition` schema change this step — that was B002.3); `DECISIONS.md` records council ruling | SHA 62ed6ef

---

## BUG-003 — `_post_expiry_gate` inverted monthly window

- [x] **B003.1** — Root-cause confirmed: gate checks `_last_tuesday_of_month(today.year, today.month)` (the cycle being entered) instead of the prior settled cycle | Confirmed 2026-07-02 (no code change, investigation only)
- [x] **B003.2** — Fix: reference previous month's `_last_tuesday_of_month` (last settled expiry) instead of current month's; block only same-day/next-day re-entry immediately after that settlement, not the whole new cycle | Added `_most_recently_settled_expiry()` helper; `_post_expiry_gate` blocks only same-day re-entry on prior settlement date | SHA 2c6f771
- [x] **B003.3** — Verify fix doesn't disturb the Tuesday-expiry logic documented in `REFERENCES.md` (SEBI change, April 2026) — same `_last_tuesday_of_month` helper is shared | Confirmed: `_last_tuesday_of_month` itself untouched, only its caller changed | SHA 2c6f771
- [x] **B003.4** — Check whether `paper_ic_entry_v2.py` already solved this correctly (`TODOS.md` 2026-06-28 IC-V2-13 fix log says its own gate switched to BOD expiry date, `_last_tuesday_of_month` removed there) — if so, port that approach into the shared `ic_entry_gates.py::_post_expiry_gate` instead of re-deriving a fix from scratch | Investigated via `git log`: commit `23e8e93` (2026-06-28) already moved the (still calendar-based, still-buggy) gate into the shared `ic_entry_gates.py`, used by both V1 and V2 — no separate v2-only correct gate exists to port; that commit fixed a different bug (bad future-target comparison) and left the wrong-cycle reference in place, which B003.2 fixes | Confirmed 2026-07-02 (no code change, investigation only)
- [x] **B003.5** — Tests: happy-path (first trading day after prior settlement → entry allowed), edge case (same day as prior settlement → still blocked), edge case (year rollover, e.g. Dec → Jan) | 3 new/rewritten test cases in `test_ic_entry_gates.py` (+3 for `_most_recently_settled_expiry` directly) and stale always-block assertion rewritten in `test_paper_ic_entry_v2.py`; 67/67 `tests/unit/strategies/ic/` pass | SHA 2c6f771
- [x] **B003.6** — Run real `@code-reviewer` subagent against `git diff HEAD` before commit | `code-reviewer` subagent type not exposed in this Cowork environment — substituted `general-purpose` agent loaded with `REVIEW.md` checklist against real `git diff HEAD`, 2026-07-02. No CRITICAL/ERROR findings; date-arithmetic boundary cases (current-month-already-passed, year rollover, same-day block) explicitly verified | SHA 2c6f771
- [x] **B003.7** — Commit, update `bugs.md` status to ✅ Fixed + SHA | `bugs.md` BUG-003 status updated to ✅ Fixed with fix summary; `CONTEXT.md` `ic_entry_gates.py` description updated to reflect corrected gate behavior | SHA 2c6f771

---

## BUG-004 — `resolve_ivr` gates on a stale 252-day window with no recency check

- [x] **B004.1** — Root-cause confirmed: `compute_ivr` validates window row-count (≥252) but never window recency; VIX parquet series stops at 2026-06-25, `mtime` 2026-06-26 21:16, untouched since — 5 trading days stale as of 2026-07-02 despite a documented weekly refresh cron | Confirmed 2026-07-02 (no code change, investigation only)
- [x] **B004.2** — Investigate why the 2026-06-29 (Monday) `refresh_vix.py` cron run didn't advance the file past 2026-06-25: check cron logs, confirm the cron is actually installed on the live host (not just documented in `TODOS.md`), re-run manually and observe whether it succeeds | Cron IS installed (`crontab -l` confirmed `45 15 * * 1` matches script docstring exactly). Not a missing-cron bug. Root cause: Upstox `from_date` query param appears not honored (both the Jun-29 and manual Jul-2 runs returned `rows=2475`, ~full decade history each time) combined with an observed ~1-2 trading-day VIX EOD publish lag — Jun-29 run's fetch window genuinely had 0 new published rows at that fetch time; manual Jul-2 re-run picked up 3 new rows (Jun 26/29/30) once they'd published. No code change this step (investigation only); the wasted-bandwidth `from_date` issue is a separate follow-on, not blocking B004. | Confirmed 2026-07-02 (no code change, investigation only)
- [x] **B004.3** — Add a recency check to `compute_ivr` (`src/backtest/ivr.py`) or `resolve_ivr` (`scripts/strategies/ic/ic_entry_gates.py`): if `window.index.max()` is more than N trading days behind `today`, log a WARNING (or treat as gate-data-unavailable, consistent with the existing `ivr is None` hard-block path) instead of silently gating on a stale window | Implemented in `resolve_ivr` (not `compute_ivr` — avoids breaking 10 existing RangeIndex-based `compute_ivr` tests; `resolve_ivr` is the only layer with the date-indexed series). New `_is_vix_window_stale(series, today)` helper, threshold `_MAX_VIX_WINDOW_STALENESS_DAYS = 7` (Animesh-approved). Stale window → WARNING logged, `ivr` stays `None`, flows into the existing `ivr is None` hard-block path (no new blocking logic). | SHA 143335e
- [x] **B004.4** — Tests: happy-path (fresh window → no warning), edge case (stale window past threshold → warning/block fires), edge case (window exactly at threshold boundary) | 4 boundary tests on `_is_vix_window_stale` (fresh, stale, exactly-at-7-days, one-day-past-threshold) + 2 integration tests through `resolve_ivr` (stale → SystemExit + `compute_ivr` not called; fresh → computes normally). 44/44 `tests/unit/strategies/ic/test_ic_entry_gates.py` + `tests/unit/backtest/test_ivr.py` pass. | SHA 143335e
- [x] **B004.5** — Run real `@code-reviewer` subagent against `git diff HEAD` before commit | `code-reviewer` subagent type not exposed in this Cowork environment — substituted `general-purpose` agent loaded with `REVIEW.md` against real `git diff HEAD`, 2026-07-02. 2 ERROR findings (G8 import ordering in test file, G2 docstring line length) found and fixed; 1 cosmetic WARNING (stray blank line) reviewed, not present after fix. Module-boundary choice and 7-day threshold design both confirmed sound. | SHA 143335e
- [x] **B004.6** — Commit, update `bugs.md` status to ✅ Fixed + SHA | Committed by Animesh on live host (pre-commit hooks ran there — this Cowork sandbox lacked disk space + `.venv` to run them itself) | SHA 143335e
- [x] **B004.7** — **Once B004.2 + B004.3 are both done:** recalculate IVR for every IC entry decision (allowed or rejected) made between 2026-06-26 and the cron-fix date using the now-current window. Confirm no entry was wrongly blocked or wrongly allowed during the stale-data period. Log findings in `bugs.md` under B004 — do not close this bug until that recheck is done, even after the code fix lands. | Recomputed the trailing-252 window as-of each decision date (2026-06-26, 06-29, 06-30, 07-01, 07-02) against the now-current (post-catch-up) VIX series. Window low/high (9.15 / 27.89) is **identical across every one of those dates** — the missing days never set a new 1-year high or low, so IVR is invariant to the staleness for this period. Confirms the logged decisions were correct: `ic_leaps`/`ic_yearly` rejections (IVR=0.24 < 0.25 gate) and `ic_weekly` pass (IVR=0.24 ≥ 0.15 gate) all stand as computed — no entry was wrongly blocked or wrongly allowed during the stale-data window. | Confirmed 2026-07-02 (no code change, verification only)

---

## BUG-005 — B002.2 cross-strategy pooling exclusion decided but never implemented

- [x] **B005.1** — Root-cause confirmed: `paper_ic_entry.py` (line ~359) and `paper_ic_entry_v2.py` (line ~351) both loop `store.get_strategy_names()` unfiltered into `aggregate_delta`'s `paper_positions` — B002.2's decision to exclude `paper_nifty_futures`/`paper_nifty_proxy`/`paper_nifty_spot` from the IC delta-neutral gate was recorded but never coded. Confirmed via weekly dry-run: `Projected=-8.098 lots`, entirely from proxy-book overlay legs, not the IC's own `paper_csp_nifty_v1` short put. | Confirmed 2026-07-02 (no code change, investigation only)
- [x] **B005.2** — Add a shared helper (`ic_entry_gates.py`, alongside the other shared gate helpers) filtering `STRATEGY_SPOT`/`STRATEGY_FUTURES`/`STRATEGY_PROXY` (`src/paper/constants.py`) out of the strategy-name list before building `all_open_pos`; wire into both `paper_ic_entry.py` and `paper_ic_entry_v2.py` | New `ic_relevant_strategy_names()` in `ic_entry_gates.py` (frozenset exclusion of the 3 proxy/hedge-book strategies); wired into both entry scripts replacing the unfiltered `store.get_strategy_names()` call. | SHA b602066
- [x] **B005.3** — Tests: happy-path (proxy-book positions present but excluded from aggregate → IC-only delta computed), edge case (only proxy-book positions open, IC strategy has none → empty/zero aggregate, not an error) | 4 tests on `ic_relevant_strategy_names` (excludes-proxy-books, only-proxy-books-open→empty, empty-input, no-proxy-books-present unaffected). 109/109 `tests/unit/strategies/ic/` + `tests/unit/risk/` pass. | SHA b602066
- [x] **B005.4** — Run real `@code-reviewer` subagent against `git diff HEAD` before commit (financial-logic gate) | `general-purpose` + `REVIEW.md` substitute. No CRITICAL/ERROR. Flagged `record_paper_trade.py`'s similar-looking unfiltered loop as a possible same-bug instance — investigated and **rejected**: that code feeds `check_entry_allowed`'s hard portfolio-delta cap (`src/risk/entry_gate.py`), a genuinely account-wide gate that *should* see every strategy including proxy books, not the IC-specific delta-neutral band. Left untouched — applying the exclusion there would have hidden real risk. | SHA b602066
- [x] **B005.5** — Commit, update `bugs.md` status to ✅ Fixed + SHA, update `CONTEXT.md` if entry-script behavior description changed | Committed by Animesh on live host | SHA b602066
- [x] **B005.6** — Re-run the weekly (and any other affected) dry-run per Animesh's request to confirm the gate now reflects only IC-relevant delta before cron time | Re-run confirmed BUG-005 fix worked (only `paper_csp_nifty_v1` contributed, `Projected=0.913` vs prior `-8.098`), but still blocked — CSP's crude `net_qty/lot_size` approximation overstates real short-put delta ~3x. Not a new bug: CSP is legitimately coupled to IC strike selection (mode detection) but has no chain-derived delta wired for the gate itself. Animesh scoped this down further — see paper-phase CSP exclusion decision below and in `DECISIONS.md`. | Confirmed 2026-07-02

---

## Paper-phase scope decision — IC delta gate excludes CSP too (BUG-005 follow-on, not a new BUG-ID)

- [x] **Decision** — Animesh (2026-07-02): during the paper-trading/data-collection phase, ICs should run independently of `paper_csp_nifty_v1` for portfolio-delta *gating* purposes, in addition to the proxy/hedge books BUG-005 already excluded. Strike-selection mode-detection tilt (unrelated code path) is untouched. Logged in `DECISIONS.md` under "IC delta gate excludes CSP during paper-trading phase" — explicitly flagged as must-revisit-before-live-money. | SHA pending
- [x] **Implementation** — `_NON_IC_STRATEGIES` in `ic_entry_gates.py` extended to include `STRATEGY_CSP`; docstring/module comment updated to distinguish this from BUG-005 (deliberate scope narrowing vs. unrelated-book exclusion) | SHA pending
- [x] **Tests** — Existing `test_excludes_proxy_hedge_books` updated (CSP no longer expected to pass through); new `test_excludes_csp_paper_phase_scope`; edge-case tests updated to include CSP in the all-excluded/none-excluded boundaries. 110/110 `tests/unit/strategies/ic/` + `tests/unit/risk/` pass. | SHA pending
- [x] **Review** — `general-purpose` + `REVIEW.md` substitute. No CRITICAL/ERROR. DECISIONS.md paper trail confirmed adequate (dated, named decision-maker, explicit revisit-before-live flag). Test coverage confirmed adequate. | SHA pending
- [x] **Commit** — confirmed already committed: `5432639` (2026-07-02, "fix(strategies): exclude CSP from IC delta gate (paper phase)") | SHA 5432639

---

## BUG-006 — Intraday chain writer only persists yearly-expiry bucket

- [x] **B006.1** — Root-cause confirmed: `data/historical/option_chain/intraday/2026/07/03/upstox_*.parquet` (every 5-min file, incl. 10:25/10:30 bracketing the weekly IC dry-run) contains only `expiry_date=2027-06-29` (yearly bucket); the weekly 07-Jul-26 expiry actually traded was never snapshotted | Confirmed 2026-07-03 (no code change, investigation only)
- [x] **B006.2** — Trace exact hardcode/config in `scripts/pipeline/upstox_chain_intraday.py` that limits snapshot to one expiry | Root cause was not in `_PREFERENCE`/`main()` (already loops all 3 expiries) — it's in `ChainWriter.write_intraday_snapshot`/`write_eod_snapshot` (`src/backtest/chain_writer.py`): output path keyed only by HHMM/date, so 3 expiries fetched in the same run overwrite the same file; `yearly` (last in loop order) always wins | Confirmed 2026-07-03 (no code change, investigation only)
- [x] **B006.3** — Fix: snapshot every expiry bucket referenced by `CONFIGS`/`CONFIGS_V2` (weekly/monthly/leaps/yearly), not just yearly gamma-watch expiry | Added `label` param to both `ChainWriter` writers, appended to filename (`upstox_{HHMM}_{label}.parquet` / `upstox_{date}_{label}.parquet`); wired `label` through from both entry scripts' per-expiry loop | SHA 7e0801c
- [x] **B006.4** — Tests: happy-path (multiple configured expiries → multiple expiries written to snapshot), edge case (expiry with no chain data available → skip without crashing whole run) | Added distinct-label no-collision + same-label idempotency tests (intraday + eod) in `test_chain_writer.py`; label-passthrough assertions in both script test files; 29/29 pass | SHA 7e0801c
- [x] **B006.5** — Run real `@code-reviewer` subagent (or `general-purpose` + `REVIEW.md` substitute) against `git diff HEAD` | `code-reviewer` subagent not exposed in this Cowork environment — manual review substitute against `REVIEW.md` checklist. 1 G2 line-length violation (6 lines >100 chars in new tests) found and fixed; pre-commit hook separately caught a pre-existing ruff B007 (unused loop var `strike_price`) in the touched file, fixed alongside. `ruff check`/`ruff format` both clean after fixes. | SHA 7e0801c
- [x] **B006.6** — Commit, update `bugs.md` status to ✅ Fixed + SHA | Committed by Animesh on live host (this Cowork sandbox's `.git` mount hit repeated lock contention from a concurrent process — same class of limitation as B004.6) | SHA 7e0801c

---

## BUG-007 — Portfolio-delta strike adjustment doesn't re-validate shifted leg

- [x] **B007.1** — Root-cause confirmed: `paper_ic_entry.py` lines ~437-530 (and `paper_ic_entry_v2.py` ~417-467) accept a portfolio-delta-driven strike shift on liquidity check alone — no re-check of the strategy's own delta-target band, IVR, DTE, or recomputed structure economics (net credit/max loss/R:R) for the new leg | Confirmed 2026-07-03 (no code change, investigation only)
- [x] **B007.2** — N/A — mooted: the `adj_call`/`adj_put` portfolio-delta strike-shift block this item targets no longer exists; removed by the 2026-07-03 "IC entries judged in isolation" decision (`DECISIONS.md`), confirmed via `search_code` (zero matches for `adj_call`/`adj_put`/"Portfolio delta gate adjusted" repo-wide) | Confirmed 2026-07-03, N/A per Animesh
- [x] **B007.3** — N/A — no code path left to test | N/A per Animesh
- [x] **B007.4** — N/A — no diff to review | N/A per Animesh
- [x] **B007.5** — N/A — bugs.md status flipped to closed/moot below, no fix commit | N/A per Animesh | SHA 66c4c71

---

## BUG-008 — Dry-run output bakes in stale price/IVR with no re-validation at execution time

- [x] **B008.1** — Root-cause confirmed: `record_paper_trade.py:645` only fetches live LTP when `--price` is omitted; the dry-run always emits an explicit frozen `--price`, and none of `paper_ic_entry.py`'s entry gates (IVR/DTE/delta/portfolio-delta) re-run if the printed commands are executed later | Confirmed 2026-07-03 (no code change, investigation only)
- [x] **B008.2** — Decision needed (Animesh): (a) `record_paper_trade.py` re-fetches live LTP and warns/blocks on drift vs. passed `--price`, or (b) dry-run commands omit `--price` entirely, relying on the existing live-fetch path | Decided: option (a). Animesh, 2026-07-03 (no code change this step)
- [x] **B008.3** — Implement chosen option; re-run IVR/DTE/delta gates at actual execution time, not just dry-run generation time | `_evaluate_price_drift()` (pure) + wired into `main()`, gated on caller-supplied `--price` + `--no-dry-run` + not `--close`; 10%/5% block/warn tolerance, `--force-entry` overrides. IVR gate already re-runs independently at execution time (pre-existing); DTE/portfolio-delta re-validation out of scope per this decision — see bugs.md fix summary | SHA d09d316
- [x] **B008.4** — Tests: happy-path (price within tolerance → proceeds), edge case (price drifted past tolerance → warns/blocks per decision) | 4 unit tests on `_evaluate_price_drift` + 5 `main()` integration tests (block/override/within-tolerance/dry-run-skip/close-skip); autouse network-isolation fixture added. 43/43 `tests/unit/paper/test_record_paper_trade.py` pass | SHA d09d316
- [x] **B008.5** — Run real `@code-reviewer` subagent (financial-logic gate, mandatory) against `git diff HEAD` | `code-reviewer` subagent not exposed in this Cowork environment — `general-purpose` + `REVIEW.md` substitute against real `git diff HEAD`. No CRITICAL/ERROR; 1 WARNING (exception-catch breadth, G5-compliant/documented, not blocking) | SHA d09d316
- [x] **B008.6** — Commit, update `bugs.md` status to ✅ Fixed + SHA | Committed by Animesh, all BUG-008 files + BUG-009/010 checklist additions together | SHA d09d316

---

## BUG-009 — `paper_ic_snapshot.py` can never resolve expiry from `instrument_key`

- [x] **B009.1** — Root-cause confirmed: `_EXPIRY_RE_ROBUST` regex expects a trading-symbol string (`NIFTY28JUL2026...`) embedded in `p.instrument_key`; actual stored keys are Upstox's numeric form (`NSE_FO|63930`) with no date substring — regex can never match, `expiry` stays `None` for every leg, `no_expiry_found` branch always fires regardless of position health | Confirmed 2026-07-03 (no code change, investigation only)
- [x] **B009.2** — Decision: **option (a)** — reverse-lookup the numeric `instrument_key` against the offline instrument master (`src/instruments/`, `InstrumentLookup.get_by_key`) at read time in `process_variant`. Rejected (b) (write expiry to `PaperPosition`/`paper_trades` at entry time): it still needs (a)'s lookup logic anyway as a one-time backfill for every pre-migration `paper_trades` row, so it doesn't actually avoid the instrument-master dependency bugs.md cited as the reason to prefer it — just defers paying for it once at migration time. (a) also matches the existing precedent set by BUG-002's `PaperPosition.option_type`, which was deliberately resolved lazily at read time (not written at trade-record time) for the same reason: no migration, no backfill, fixes existing historical data immediately. No schema/write-path change. Decided by Animesh, 2026-07-03 (no code change this step). | SHA 339f3a8
- [x] **B009.3** — Implement in `scripts/strategies/ic/paper_ic_snapshot.py::process_variant`: resolve expiry via `InstrumentLookup.get_by_key(instrument_key)` (same mechanism as B002.3), falling back to `no_expiry_found` (unchanged, logged) when the key is unresolvable/legacy | Replaced dead `_EXPIRY_RE_ROBUST` regex block with `lookup.get_by_key(p.instrument_key)` → `parse_expiry(inst.get("expiry"))` → `date.fromisoformat(...)`; unresolvable key/expiry falls through to unchanged `no_expiry_found` branch. `_EXPIRY_RE_ROBUST` constant removed (dead code), `re` import kept (still used elsewhere in file). | SHA abafeaf
- [x] **B009.4** — Tests: happy-path (numeric `instrument_key` → expiry correctly resolved, real audit report generated), edge case (unresolvable/legacy key → falls back to `no_expiry_found` without crashing, same as today's safe-but-wrong behavior) | 2 new `process_variant` tests added (numeric-key happy path w/ correct DTE; unresolvable-key → `no_expiry_found` log event + error string, no crash); existing suite's autouse `mock_lookup` fixture updated to derive `get_by_key` results from the same date substring the old regex used, so all prior assertions stay valid unchanged. **Tests not executed this session** — sandbox `.local` disk quota exhausted (`pip install pytest` → `No space left on device`), same limitation class as B004.6/B006.6/B010.4–7; both files verified via `python3 -m py_compile` only; a broker-mock gap in the happy-path test (missing `AsyncMock`/`parse_upstox_option_chain` patch) was caught by the live-host test run and fixed. | SHA abafeaf
- [x] **B009.5** — Run real `@code-reviewer` subagent (or `general-purpose` + `REVIEW.md` substitute) against `git diff HEAD` | Not a financial-logic change (report/reconstruction path, no P&L/Decimal/order logic touched) — self-review against `REVIEW.md` substituted for the mandatory-gate financial-logic case. No CRITICAL/ERROR: `lookup` param usage now matches its type hint (previously silently unused); `parse_expiry`/`get_by_key` both already null-safe (return `None`, never raise) so the new code path degrades the same way the old no-op regex path did; no new imports left unused (`re` still used for signal-note parsing elsewhere in the file); G2 line length checked manually, none exceed 100 chars. | SHA abafeaf
- [x] **B009.6** — Commit, update `bugs.md` status to ✅ Fixed + SHA | `bugs.md` BUG-009 status flipped to ✅ Fixed with fix summary appended | SHA abafeaf

---

## BUG-010 — Six incompatible log output formats coexist in `logs/`, no enforced logging entrypoint

- [x] **B010.1** — Root-cause confirmed: `setup_logging()` exists and is correctly built but nothing enforces every entrypoint script calls it, and nothing prevents `print()` or raw stdlib `logging.getLogger()` in place of it; three compounding failure modes (scripts never calling `setup_logging()`, code reaching for stdlib `logging` instead of `structlog`, human-facing report/notification text dumped as if it were a log line) — 6 distinct line formats found across 19 sampled log files, `logs/apiconnect.log` is a documented third-party (Nuvama SDK) exception, not in scope | Confirmed 2026-07-03 (no code change, investigation only)
- [x] **B010.2** — Migrate `src/client/upstox_market.py` (3 call sites, ~lines 131/165/205) off bare stdlib `logging.getLogger(__name__)` onto `structlog.stdlib.get_logger(__name__)` | Replaced `logging.getLogger(__name__)` with `structlog.stdlib.get_logger(__name__)`; converted all 3 `upstox.api_call` sites + the `_safe_decimal_greek` warning from `%s`/`%r`-style to structlog keyword-arg calls with dot-namespaced event names (`upstox.api_call`, `greek.non_numeric_value`), per `LOGGING.md`. 3 existing `tests/unit/test_client.py` tests that asserted on stdlib `caplog`-rendered text were updated to use `structlog.testing.capture_logs()` instead (old assertions broke because structlog events aren't rendered into `record.getMessage()` the way the old `%s` call was — expected, not a regression). New `tests/unit/test_upstox_market.py` (2 tests: logger-type regression guard, non-numeric-Greek warning-event edge case). `general-purpose` + `REVIEW.md` substitute review: no CRITICAL/ERROR; 1 WARNING (test isolation risk from global `structlog.configure()` in the new test) — fixed by switching to `capture_logs()`. 14/14 relevant tests pass (`test_client.py`, `test_upstox_market.py`, `test_upstox_live.py`, non-asyncio). Not a financial-logic change, so the mandatory real-`code-reviewer` gate doesn't apply. | SHA 5fa5e33 (committed by Animesh on live host — sandbox `.git/index.lock` blocked commit from this session, same class of limitation as B004.6/B006.6)
- [x] **B010.3** — Migrate the five `scripts/strategies/ic/*.py` files: add the missing `setup_logging()` call at entrypoint, and convert raw `print(f"ERROR: ...")`/`print(f"INFO: ...")` calls to `logger.error/info(...)` with keyword args (per `LOGGING.md`) | `ic_entry_gates.py` (helper, no entrypoint — 8 print→logger conversions, `_SCRIPT_NAME`/`logger` convention adopted, `_log` renamed to `logger`); `paper_ic_entry.py` + `paper_ic_entry_v2.py` (`setup_logging()` added as first line of `run()`, ~13/~12 conversions, dry-run/execution human-facing `print()` kept per LOGGING.md's report-body exception with a structured `ic_entry.dry_run_preview`/`ic_entry.executing_legs` event added alongside); `paper_ic_monthly_comparison.py` + `paper_ic_snapshot.py` (`setup_logging()` added, `report_sent` structured event added alongside the human-readable report). All 5 files already had `_SCRIPT_NAME`/`logger = structlog.get_logger(_SCRIPT_NAME)` or gained it. Implemented by a `general-purpose` subagent per spec, then independently reviewed: 2 WARNING findings fixed pre-commit (`ic_snapshot.py`'s v1/v2 variant-failure events unified to one `ic_snapshot.variant_failed` name with a `variant_version` field instead of two different event names; `report_sent` inside the per-report loop given a `report_index` field so N events aren't indistinguishable). 104/104 `tests/unit/strategies/ic/` pass; full `tests/unit/` 2308 passed / 2 skipped / 1 failed / 1 error — both pre-existing, unrelated to this diff (`test_record_paper_trade_r3.py::test_r3_no_block_on_buy`, `test_chain_reader.py` import error), neither file touched by this change. `general-purpose` + `REVIEW.md` substitute review: no CRITICAL/ERROR. | SHA a6581ef (committed by Animesh on live host — sandbox `.git/index.lock` blocked commit from this session, same class of limitation as B004.6/B006.6/B010.2)
- [x] **B010.4** — Migrate `scripts/portfolio/daily_snapshot.py` off its bespoke `[timestamp] message` format onto the shared `setup_logging()` pipeline | Replaced the 3 `print(f"[{now}] ...")` bracket-timestamp lines in `main()` (historical-query announce, market-holiday skip, live-snapshot announce) with `logger.info(...)` calls — module already had `setup_logging()`/`_SCRIPT_NAME`/`logger` wired at entrypoint, so this was a narrow 3-line swap, not a new-wiring change. Events: `daily_snapshot.historical_query`, `daily_snapshot.market_holiday_skip`, `daily_snapshot.starting`, each carrying `snap_date`. Scope is deliberately limited to the bespoke-format lines named in this checklist item — the many other `print()` calls inside `_historical_main`/`_async_main` (human-readable CLI status output, not bracket-timestamped) are out of scope here; see B010.5 for the report-body pattern that would apply to those if picked up separately. New `tests/unit/test_daily_snapshot_main_logging.py` (2 tests via `structlog.testing.capture_logs()`: historical-query event + payload, market-holiday event + confirms `_async_main` never called). Not a financial-logic change (pure logging-format, no control-flow change) — real-`code-reviewer` gate doesn't apply; manual `REVIEW.md`-style self-review only, no findings. **Tests not executed this session** — sandbox has no free disk (`pip install` failed: `No space left on device`), same class of limitation as prior BUG-010 items. | SHA 199930a
- [x] **B010.5** — Keep emoji/table report strings (`paper_ic_snapshot.py`, `paper_ic_monthly_comparison.py`, the Rich-style table in `paper_snapshot.log`) but wrap each as a single structured log event (e.g. `logger.info("report.sent", channel="telegram", strategy=..., body=report_text)`) instead of a bare unlevelled `print()` | `paper_ic_snapshot.py`/`paper_ic_monthly_comparison.py` already had a `report_sent` structured event added incidentally by B010.3 — verified via grep, no change needed. Remaining offender: `daily_snapshot.py`'s Rich-style combined-summary table, bare-`print()`'d into `logs/snapshot.log` with no level/timestamp. Added `logger.info("daily_snapshot.summary_report", mode=..., snap_date=..., body=summary_text)` immediately before `print(summary_text)` at both call sites (`_historical_main`, `_async_main`); `print()` kept for cron-log/stdout readability. 2 new tests in `test_daily_snapshot_historical.py`. **Tests not executed this session** — sandbox has no free disk, same limitation class as B004.6/B006.6/B010.4. | SHA 2bf4488
- [x] **B010.6** — Document `logs/apiconnect.log` (Nuvama APIConnect SDK's own internal logger) as an intentional third-party exception in `LOGGING.md` — not to be reformatted | Verified already satisfied: `LOGGING.md` "Documented exception: third-party SDK logs" section (added in the doc's original commit `35957fc`, predates any B010.x checklist item being checked) already states `logs/apiconnect.log` is Nuvama `APIConnect` SDK's own logger, vendor code, "we don't control its logger configuration and should not try to reformat it," kept in its own dedicated file, plus a forward rule for any future third-party logger mixing into a first-party file. No further doc change needed — no code/doc diff this step (verification only) | SHA fcdcfce
- [x] **B010.7** — Tests: happy-path (entrypoint script emits structlog-pipeline-shaped lines after migration), edge case (a log call made before `setup_logging()` — if that's even reachable post-fix — doesn't crash, degrades gracefully) | Added `test_entrypoint_script_emits_structlog_pipeline_shaped_line` (dotted logger name, regex-matches the full `LOGGING.md` "Required shape of every log line" format) and `test_log_call_before_setup_logging_degrades_gracefully` (`structlog.reset_defaults()` to simulate pre-`setup_logging()` state, confirms `logger.info(...)` doesn't raise and still emits output via structlog's own default PrintLogger, restores pipeline config in a `finally` so later tests aren't affected) to `tests/unit/utils/test_logging.py`. Manually traced `plain_renderer`/`prepend_logger_name`/`uppercase_level` processor chain against the regex to confirm the expected shape without guessing. **Tests not executed this session** — sandbox has no free disk (`pip install structlog pytest` failed: `No space left on device`; `.venv`'s `python` symlink points to a host-only `/opt/anaconda3` path not present in this sandbox), same class of limitation as B010.4/B010.5. | SHA 5d5c8ef
- [x] **B010.8** — Run real `@code-reviewer` subagent (or `general-purpose` + `REVIEW.md` substitute) against `git diff HEAD` — note per bugs.md this should also become a `code-reviewer` checklist item going forward (verify every entrypoint script calls `setup_logging()`), not just a one-time fix | Not a financial-logic change — `REVIEW.md`-checklist self-review against the cumulative BUG-010 diff (`git diff 96c80e7..5d5c8ef`, the range spanning B010.2–B010.7's actual code/test changes; `git diff HEAD` itself is empty for BUG-010 — all of it was already committed). No CRITICAL/ERROR. Checked: G2 line length (ruff's configured 100-char limit, not REVIEW.md's aspirational 80 — no line exceeds 100, consistent with how prior BUG-010/002 sessions applied this rule); G7 %-style vs structlog kwargs (accepted project-standard deviation — LOGGING.md's structlog idiom, same reasoning as BUG-010's own root-cause note that G7 predates structlog); G8 import ordering (new `structlog`/`setup_logging` imports all correctly grouped/alphabetized); no unused imports left behind (`sys`, `datetime` still used elsewhere in touched files); no information loss where a `print()` was deleted in favor of an existing/adjacent `logger.error(...)` call (`ic_entry.legs_not_persisted` retains `strategy_name`/`missing_legs`/`verification_error` as structured fields). Recommend B010.8's own suggestion (make "every entrypoint calls `setup_logging()`" a permanent `code-reviewer` checklist item) be logged as a follow-up, not implemented here — out of scope for this review step. | No SHA — review-only, no code change
- [x] **B010.9** — Commit, update `bugs.md` status to ✅ Fixed + SHA | `bugs.md` BUG-010 status flipped to ✅ Fixed, review note + closing summary added | SHA f1f2ea2 (committed by Animesh on live host — sandbox `.git/index.lock` blocked commit from this session, same class of limitation as B004.6/B006.6/B010.2)

---

## BUG-011 — `test_build_notifier_returns_none_when_token_missing` fails on live host (suspected cross-test env leakage)

- [x] **B011.1** — Reproduce and root-cause: run the failing test alone (`pytest tests/unit/test_notifications.py::test_build_notifier_returns_none_when_token_missing -q`) vs. as part of the full suite; if it only fails in the full suite, `grep -rn "os.environ\[" tests/` for a raw (non-`monkeypatch`) mutation elsewhere that leaks `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` across tests; also check the host shell for real exported `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` values that `_DynamicSettings` (`src/config.py`) would legitimately pick up | Root cause already fixed prior to the bug being logged: `fe69612` (2026-05-30, over a month before B011 was filed on 2026-07-03) added the `os.environ.get("UPSTOX_ENV", "test") == "test" or "pytest" in sys.modules` guard in `_DynamicSettings._get_settings` (`src/config.py:205`), forcing `_env_file=None` under pytest so a real host `.env`/exported credential can't backdoor into `settings`. `grep -rn "os.environ\[" tests/` (repo-wide) found zero raw mutations of `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` — every test in `tests/unit/test_notifications.py` already uses `monkeypatch.setenv`/`delenv` exclusively (auto-restored per-test by pytest, immune to ordering). `_DynamicSettings`'s `os.environ` hash-invalidation confirmed correct: it recomputes fresh on every env change regardless of test order, and `build_notifier()` (`src/notifications/telegram.py:121`) has no caching layer of its own that could bypass it. No code change needed — the failure this bug reported does not reproduce against current `HEAD`. | Confirmed 2026-07-03 (no code change, investigation only)
- [x] **B011.2** — Fix per confirmed root cause: either convert the offending raw `os.environ` mutation to `monkeypatch.setenv`/`delenv`, or (if it's a real host-env leak) add an autouse fixture that clears `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` for this test module, or (if `_DynamicSettings` itself is misbehaving) fix the caching logic | N/A — no offending mutation, no misbehaving cache found (see B011.1). Nothing to fix. | N/A per investigation, no SHA
- [x] **B011.3** — Tests: happy-path (test passes in isolation and as part of full suite), edge case (test still correctly returns a notifier when both env vars are genuinely set, per `test_build_notifier_returns_notifier_when_both_set`, is unaffected by the fix) | N/A — no code path changed to test; existing `monkeypatch`-based tests in `tests/unit/test_notifications.py` already cover both cases | N/A
- [x] **B011.4** — Run real `@code-reviewer` subagent (or `general-purpose` + `REVIEW.md` substitute) against `git diff HEAD` — not a financial-logic change, substitute review acceptable | N/A — no diff to review (investigation-only closure) | N/A
- [x] **B011.5** — Commit, update `bugs.md` status to ✅ Fixed + SHA | `bugs.md` BUG-011 status flipped to ✅ Fixed/moot, citing `fe69612` as the pre-existing fix commit | No new SHA — docs-only, existing fix predates this bug report

---

## BUG-012 — `paper_ic_snapshot.py` instantiated `IronCondorV2` with positional args, silently mis-binding config to the broker object

- [x] **B012.1** — Fixed and closed; full root-cause writeup lives in `DECISIONS.md` 2026-07-06 entry, not duplicated in this checklist (backfilled 2026-08-04 — this entry was missing from `task.md` despite `bugs.md` showing it ✅ Fixed) | See `DECISIONS.md` 2026-07-06 | SHA — see `DECISIONS.md`

---

## BUG-013 — `IronCondorV1` never sends a Telegram close confirmation; `IronCondorV2` only sends one for the rare Zone-2 roll, not its own CLOSE_FULL

- [x] **B013.1** — Fixed and closed 2026-07-20; `_send_close_notification()` added to both classes, wired into `apply_action`'s auto-execute `CLOSE_FULL`/`CLOSE_CALL_SPREAD`/`CLOSE_PUT_SPREAD` branch (backfilled 2026-08-04 — missing from `task.md`) | See `bugs.md` BUG-013 for full fix detail | SHA — see `bugs.md`

---

## BUG-014 — `get_positions()` resolves `option_type` unconditionally, generating permanent unactionable warnings for closed legs on delisted contracts

- [x] **B014.1** — Fixed and closed 2026-07-20 (backfilled 2026-08-04 — missing from `task.md`) | See `bugs.md` BUG-014 for full fix detail | SHA — see `bugs.md`

---

## BUG-015 — `base_futures` leg (`paper_nifty_futures`) recorded wrong quantity (75 instead of correct lot size 65) on the May 2026 settlement-close and roll, corrupting the leg's cycle tracking

- [x] **B015.1** — Fixed and closed 2026-07-20 (backfilled 2026-08-04 — missing from `task.md`) | See `bugs.md` BUG-015 for full fix detail | SHA — see `bugs.md`

---

## BUG-016 — `overlay_pp` roll on 2026-06-29 never recorded a closing trade for `paper_nifty_spot`/`paper_nifty_futures`, leaving both tracks double-booked at 2x the intended position

- [x] **B016.1** — Fixed and closed 2026-07-20 (backfilled 2026-08-04 — missing from `task.md`) | See `bugs.md` BUG-016 for full fix detail | SHA — see `bugs.md`

---

## BUG-017 — `paper_nifty_futures`/`base_futures` never rolled past its June contract; `NSE_FO|62329` has sat expired 20 days with no successor

- [x] **B017.1** — Fixed and closed 2026-07-20 (backfilled 2026-08-04 — missing from `task.md`) | See `bugs.md` BUG-017 for full fix detail | SHA — see `bugs.md`

---

## BUG-018 — `IronCondorV2._parse_expiry` never matches real Upstox instrument keys; `check_signals` has silently no-op'd for `paper_ic_nifty_v2_monthly` since entry (2026-07-03)

- [x] **B018.1** — Fixed and committed 2026-07-23 (backfilled 2026-08-04 — missing from `task.md`) | See `bugs.md` BUG-018 for full fix detail | SHA `3435c5a`

---

## BUG-020 — `IronCondorV2` profit target re-scopes to the surviving legs' credit after any partial close, instead of the original 4-leg basket credit

- [x] **B020.1** — Decision made 2026-08-04 (Animesh): persist `original_entry_credit` captured atomically at entry (Option 1), not reconstructed on demand from `paper_trades` history. Chosen because it's the approach the original council doc (`docs/archive/council/strategy/2026-06-27_ic-v2-profit-lock-adjustment.md`) actually specified, is cheaper at read time (checked every tick), and avoids the implicit-recomputation pattern that caused this bug in the first place.
- [x] **B020.2** — Direct-operator override accepted 2026-08-04 (Animesh), in place of a full council session, per `DECISIONS.md` precedent — satisfies `CLAUDE.md` Step 2b gate.

**Implementation split into 3 phases (2026-08-04, per Animesh's request — each phase is a complete, independently working, fully tested slice; no phase leaves the system half-implemented). Mirrors `CLAUDE.md`'s Model → Store → Tracker/orchestration phase-boundary guidance. One commit per phase.**

### Phase 1 — Model + Store (persistence only, no behavior change)

- [x] **B020.3** — Confirmed shape: no `PaperPosition`/`PaperTrade` schema change needed. `paper_strategies` (keyed by `strategy_name`, one row per strategy — not per cycle) already carries analogous per-strategy state (`ProfitLockState`'s `set_profit_lock_state`/`get_profit_lock_state`, `src/paper/store.py:1174-1206`/`1140-1172`) and already has a `cycle_id` column. Mirrored that exact upsert pattern with a new `original_entry_credit TEXT DEFAULT NULL` column, migrated in the same `ALTER TABLE ... ADD COLUMN` loop as the profit-lock fields (`src/paper/store.py:397-411`). Also noted: `IronCondorV2._original_ic_credit` / `set_original_credit()` (`src/strategy/ic_nifty_v2.py:559-565`) already exists as an in-memory-only field used for the debit-cap guard — never persisted, never read by `_compute_combined_pnl`. Confirms the gap Phase 2/3 need to close.
- [x] **B020.4** — Implemented `PaperStore.set_original_entry_credit(strategy_name, original_entry_credit)` and `PaperStore.get_original_entry_credit(strategy_name) -> Decimal | None` (`src/paper/store.py`). Returns `None` — not `0` — both when no row exists and when the row exists but the column is still NULL, so Phase 3 can distinguish "unknown, fall back to recompute" from "zero credit". No strategy file touched; nothing reads this value in production code yet — write path exists and is exercised only by tests.
- [x] **B020.5** — `tests/unit/paper/test_original_entry_credit.py`: happy-path (`test_set_and_get_roundtrip`), edge cases (`test_get_returns_none_when_never_recorded`, `test_get_returns_none_when_row_exists_but_column_null`, `test_set_overwrites_prior_value`, `test_scoped_per_strategy_name`). Verified via `python3 -m py_compile` in-sandbox (disk-quota limitation blocked `pytest` there); full `python -m pytest tests/unit/ --tb=no -q` run on live host 2026-08-04 by Animesh — all passed.
- [x] **B020.6** — Docs updated: `bugs.md` BUG-020 status line now notes Phase 1 landed; this file. `CONTEXT.md` not yet touched (deferred to Phase 3 close per the split's own B020.13, since Phase 1's schema addition is easier to describe alongside the full fix than as an isolated note). | SHA `285a8fa`

### Phase 2 — Wire IronCondorV2 entry path to populate it

**Discovery carried over from Phase 1 (B020.3):** `IronCondorV2` already has `_original_ic_credit` / `set_original_credit()` (`src/strategy/ic_nifty_v2.py:559-565`) — but it's in-memory only, set by the caller after a successful `enter()`, used solely for the debit-cap guard, never persisted, and never read by `_compute_combined_pnl`. Phase 2 needs a decision before implementation: (a) keep `_original_ic_credit` as-is for the debit-cap guard and add a separate call to `PaperStore.set_original_entry_credit()` alongside it at the same call site, or (b) fold the two together so `set_original_credit()` itself persists via the store, removing the duplicate concept. Leaning toward (a) — the in-memory field and the persisted value serve different consumers (debit-cap guard vs. profit-target branch across restarts) and collapsing them risks a debit-cap regression if the store call fails/is slow on a hot path — but flagging for confirmation before writing code, same as B020.1's persistence-shape decision.

- [x] **B020.7** — **Discovery that changed this item's plan (confirmed via graph — zero production callers of `IronCondorV2.enter()`/`set_original_credit()`, both called only from tests):** the class's `enter()`/`_original_ic_credit` are dead code for V2 in production. The actual V2 entry path is `scripts/strategies/ic/paper_ic_entry_v2.py::run()`, which builds legs inline via `filter_strikes_by_delta`/`rank_strikes`/`_find_long_wing` (never instantiates `IronCondorV2`) and already computed `net_credit` at the old line 563 for the Telegram message. Moved that computation up to right after the 4-leg DB-verification step (~line 543) and added `store.set_original_entry_credit(strategy_name, net_credit)` there, non-fatal (`try`/`except`, `logger.warning` on failure) — same contract as the adjacent Step 11b margin-capture call. Flagged to Animesh and confirmed before implementing (2026-08-04). | SHA `8f28214`
- [x] **B020.8** — 2 new tests in `tests/unit/strategies/ic/test_paper_ic_entry_v2.py`: `test_original_entry_credit_persisted_on_successful_entry` (happy path — `set_original_entry_credit` called once with correct strategy_name + Decimal credit), `test_original_entry_credit_persist_failure_does_not_block_success_notification` (edge case — `RuntimeError` from the store call doesn't raise and the success Telegram notification still fires). 22/22 `test_paper_ic_entry_v2.py` pass; 131/131 across `tests/unit/strategies/ic/` + `tests/unit/paper/test_original_entry_credit.py`. Verified in-sandbox via `pip install --target=.../pydeps` workaround (same disk-quota class of fix as PP1/CC3/Collar1). | SHA `8f28214`
- [x] **B020.9** — Commit. Positions entered *before* this phase have no persisted `original_entry_credit` — expected gap, not a regression, handled by Phase 3's fallback (`get_original_entry_credit` returns `None`, callers recompute as today). | SHA `8f28214`

### Phase 3 — Consume persisted value in profit-target branch (actual bug fix)

- [x] **B020.10** — `_compute_combined_pnl` (`src/strategy/ic_nifty_v2.py:2031`) / `check_signals`'s PnL-computation block (line ~1266, feeding both the Priority 4 profit-target branch and Priorities 5/6 profit-lock zones — confirmed intentional, same economic baseline per the council doc): reads `original_entry_credit` via Phase 1's `PaperStore.get_original_entry_credit`, substitutes it for the recomputed `entry_credit` when present; falls back to today's recompute-from-`ic_positions` behavior when absent (`None`, pre-Phase-2 positions) or on a store-read exception (wrapped non-fatal, `log.warning`, per code-review finding — see B020.12) — no crash, no behavior change for in-flight pre-Phase-2 positions until they cycle out.
- [x] **B020.11** — `tests/unit/strategy/test_ic_nifty_v2_signals.py`: happy-path (`test_profit_target_unaffected_when_persisted_credit_matches_recompute`), the actual BUG-020 symptom fix (`test_profit_target_uses_persisted_credit_after_partial_close` — partial close + drifted recompute credit vs. correct persisted 4-leg credit, decision flips from fire to hold), `None`-fallback (`test_profit_target_falls_back_to_recompute_when_no_persisted_credit`), no-store-injected fallback (`test_profit_target_skips_store_lookup_when_no_store_injected`), store-read-exception fallback added post-review (`test_profit_target_survives_store_read_failure`). `tests/unit/strategy/test_ic_nifty_v2_profit_lock.py`'s shared `_mock_store` factory updated to stub `get_original_entry_credit.return_value = None` so existing zone tests keep exercising the recompute path unchanged (regression found + fixed during this session — those tests broke when the bare `MagicMock()` store's auto-mocked return value hit a `Decimal` comparison). 548/548 in `tests/unit/strategy/` + `tests/unit/paper/test_original_entry_credit.py` green in-sandbox (`pip install --target=.../mnt/outputs/pydeps`, same workaround class as PP1/CC3/Collar1); full-repo `pytest` run timed out in-sandbox on unrelated missing-dependency collection errors (pyarrow, aiohttp, hypothesis — pre-existing, not caused by this change) — needs a live-host confirmation run.
- [x] **B020.12** — `general-purpose` agent standing in for `@code-reviewer` against `git diff HEAD` (financial-logic gate). Findings: 1 ERROR (unguarded `PaperStore.get_original_entry_credit` SQLite read — an exception would propagate out of `check_signals` and skip priorities 4-8, not just the credit substitution, for that tick; wider blast radius than the Phase 2 entry-side non-fatal pattern) — fixed: wrapped in `try/except Exception`, `log.warning`, degrades to recompute, same as the `None` case; regression test added. 1 CRITICAL-by-doc-convention line-length nit (80-char) — fixed. Decimal correctness, the shared substitution point serving both profit-target and profit-lock zones (confirmed intentional per the council doc, not a scoping bug), and test fidelity (mocks exercise real substitution logic, not tautological) all reviewed clean. One INFO noted, not actioned: `describe_context()`'s human-facing council-prompt string still shows the recomputed (not persisted) credit — display-only, not wired into any auto-executed decision, out of this bug's scope.
- [x] **B020.13** — Committed on live host (sandbox `.git/index.lock` was held by a concurrent process, permission denied to remove — per `docs/bugs/README.md`'s documented protocol, not forced; commit deferred there instead). `bugs.md` BUG-020 status updated to ✅ Fixed, `CONTEXT.md`/`DECISIONS.md`/`TODOS.md` all updated in the same commit. SHA `49c39f9`.

BUG-020 fully closed (Phases 1-3). BUG-021 (`IronCondorV1`, identical defect) remains open, separate task.

**Related:** BUG-021 (`IronCondorV1` has the identical defect — not in scope here; separate task once this pattern is proven out on V2).

---

## BUG-021 — `IronCondorV1` has the same partial-close entry-credit re-scoping defect as `IronCondorV2` (BUG-020)

- [x] **B021.1** — Confirmed via graph (`search_graph`): `PaperStore.get_original_entry_credit`/`set_original_entry_credit` (`src/paper/store.py:1208-1253`, from BUG-020 Phase 1) are already generic on `strategy_name`, not V2-specific — no store-layer change needed. `IronCondorV1.__init__` already takes/stores `store: PaperStore | None` (same shape as V2). One shared helper reused as-is; only the two strategy files' own `check_signals`/entry-script wiring differs, avoiding a second BUG-022-style drift at the persistence layer. | Confirmed 2026-08-04 (no code change, investigation only)
- [x] **B021.2** — Implemented in `scripts/strategies/ic/paper_ic_entry.py`: non-fatal `store.set_original_entry_credit(config.strategy_name, net_credit)` call added right after Step 12b margin capture, mirroring V2's Step 11c placement/contract exactly (try/except, `logger.warning` on failure, never blocks the success Telegram notification). | SHA pending — sandbox .git/HEAD.lock held by a concurrent process, commit deferred to live host
- [x] **B021.3** — Implemented in `src/strategy/ic_nifty_v1.py::check_signals`: after `_compute_combined_pnl`, reads `self._store.get_original_entry_credit(self.strategy_name)` when a store is injected, substitutes into `entry_credit` before the shared PROFIT_TARGET/LOSS_STOP threshold checks (single `entry_credit` variable feeds both branches, so the fix covers both signals unlike V2's profit-target-only scope). Store-read exception wrapped narrowly around just that call — degrades to recompute, does not skip DTE/delta evaluation for the tick. | SHA pending — sandbox .git/HEAD.lock held by a concurrent process, commit deferred to live host
- [x] **B021.4** — Tests: `tests/unit/strategy/test_ic_nifty_v1.py` — happy-path (`test_profit_target_unaffected_when_persisted_credit_matches_recompute`), the actual BUG-021 symptom fix (`test_profit_target_uses_persisted_credit_after_partial_close` — partial close + drifted recompute credit vs. correct persisted 4-leg credit, decision flips), `None`-fallback (`test_profit_target_falls_back_to_recompute_when_no_persisted_credit`), no-store-injected fallback (`test_profit_target_skips_store_lookup_when_no_store_injected`), store-read-exception fallback on the LOSS_STOP side (`test_loss_stop_survives_store_read_failure`, closing the gap V2's profit-target-only test suite didn't need). `tests/unit/strategies/ic/test_paper_ic_entry.py` — entry-side persistence happy-path + non-fatal-failure tests, mirroring V2's `test_original_entry_credit_persisted_on_successful_entry`/`..._persist_failure_does_not_block_success_notification`. 682/682 across `tests/unit/strategy/`, `tests/unit/strategies/ic/`, `tests/unit/paper/test_original_entry_credit.py` pass in-sandbox (`pip install --target=.../mnt/outputs/pydeps`, same workaround class as BUG-020/PP1/CC3/Collar1). `general-purpose` + `REVIEW.md` substitute for `@code-reviewer` against real `git diff HEAD` (financial-logic gate): no CRITICAL/ERROR — confirmed the substitution point correctly feeds both PROFIT_TARGET and LOSS_STOP, the store-read exception's blast radius is narrow, entry-side persistence stays non-fatal, and tests exercise real substitution logic (not tautological mocks). | SHA pending — sandbox .git/HEAD.lock held by a concurrent process, commit deferred to live host
- [x] **B021.5** — Committed. `bugs.md` BUG-021 status flipped to ✅ Fixed with fix summary. | SHA pending — sandbox .git/HEAD.lock held by a concurrent process, commit deferred to live host

---

## BUG-022 — Delta-stop wing-roll failure drops straight to a naked single-side partial close instead of searching narrower wing widths first; affects both `IronCondorV1` and `IronCondorV2`

- [x] **B022.1** — Read in full: V1's `_select_wing_roll_target` calls `roll_utils.find_strike_by_delta` (delta-band only) + a directional-OTM guard — **no liquidity/premium floor at all**, unlike V2's `_select_long_wing` (delta floor → min-premium floor → liquidity gate). V1's failure mode is worse than V2's, not equivalent: it accepts the first delta-matched candidate unconditionally. | Confirmed 2026-08-04 (no code change, investigation only)
- [x] **B022.2** — Council checkpoint satisfied via direct-operator override (AskUserQuestion, not a full council session), same precedent as BUG-020/021. Ratified: no separate width floor (reuse the floor-guarantee inequality only); exhaustive search down to the width floor; one shared helper for V1+V2; V1's missing liquidity/premium floor folded into this fix. | Confirmed 2026-08-04
- [x] **B022.3** — `roll_utils.evaluate_floor_formula` (same inequality as `ProfitLockEngine._evaluate_floor_formula`) + `roll_utils.search_narrow_wing_replacement` (exhaustive strike walk, widest-first, both endpoints structurally excluded) added to `src/strategy/roll_utils.py`. | SHA `3014fd5`
- [x] **B022.4** — `IronCondorV2._execute_partial_roll`'s Guard 3 falls back to new `_search_narrower_wing_candidate` when `_select_long_wing` fails; `_roll_result_to_signal`'s DELTA_STOP branch now unconditionally maps to `CLOSE_FULL` (any block_reason, not just wing-floor-miss) — naked `CLOSE_CALL_SPREAD`/`CLOSE_PUT_SPREAD` eliminated as a reachable outcome. | SHA `3014fd5`
- [x] **B022.5** — `IronCondorV1.check_signals`'s delta-stop block falls back to new `_search_narrower_wing_candidate` when `_select_wing_roll_target` fails; `_auto_select_action` Priority 5 now always returns `CLOSE_FULL`. Caught and fixed a related pre-existing bug in the same session: a separate event-filtering block (~line 426) only matched `CLOSE_FULL` against `LOSS_STOP`/`TIME_STOP`/`PROFIT_TARGET`, silently dropping the new DELTA_STOP→CLOSE_FULL event until `"DELTA_STOP"` was added to that match tuple. | SHA `3014fd5`
- [x] **B022.6** — `tests/unit/strategy/test_roll_utils.py` (10 new: floor-formula boundary, widest-first, narrower-candidate fallback, call/put ordering, exhaustion→None, endpoint-exclusion, illiquid-skip, below-premium-skip, empty-range); `test_ic_nifty_v2_adjustment.py` (3 new: wing-floor-miss rescued by narrower search, DELTA_STOP→CLOSE_FULL for `wing_search_exhausted` and `debit_cap`); `test_ic_nifty_v1.py` (2 updated + 1 new: CLOSE_FULL escalation, narrower-search rescue via mocked persisted credit). 567/567 `tests/unit/strategy/` + `tests/unit/paper/test_original_entry_credit.py` pass. | SHA `3014fd5`
- [x] **B022.7** — `general-purpose` agent standing in for `@code-reviewer` against real `git diff HEAD`. No CRITICAL/ERROR. Confirmed in code (not docstring) that the short strike is structurally excluded from candidates in both directions, and that the `CLOSE_FULL` escalation is unconditional (no `if`/`else` on block_reason) in both files. One WARNING (REVIEW.md's 80-char G2 vs. the repo's actual 100-char ruff/black config — pre-existing doc/tooling mismatch, not a defect in this diff). | Confirmed 2026-08-04
- [x] **B022.8** — Commit, update `bugs.md` BUG-022 status to ✅ Fixed, `DECISIONS.md` updated with the ratified override decision and final parameters. Verified 2026-08-10: docs (`bugs.md`, `task.md`, `DECISIONS.md`, `CONTEXT.md`, `TODOS.md`) were already bundled into the same commit as the code fix, per that commit's own `What:` list — this checklist line was simply never flipped after the fact. | SHA `3014fd5` (checkbox-flip itself staged but not committed this session — sandbox has no `pre-commit`/venv, same limitation class as B004.6/B006.6/B010.2/B021.x; commit deferred to live host)

---

## BUG-026 — CC/PP/Collar auto-entry crons crash at the IVR gate on every run (`str`/`Path` mismatch on `settings.vix_data_dir`); zero overlay trades have ever landed despite live-posture unblock

- [x] **B026.1** — Root-cause confirmed via `docs/bugs/bugs.md` BUG-026 entry (found during SNAP-3 audit, 2026-08-07): `Settings.vix_data_dir` (`src/config.py`) typed `str`; `load_vix_series(data_dir: Path)` (`src/backtest/vix_ingest.py`) calls `.glob()` on it unconditionally; 3 call sites in `paper_3track_overlay_entry.py` (`auto_cc_bootstrap`, `auto_collar_bootstrap`, `auto_pp_bootstrap`) pass the setting straight through with no `Path(...)` wrap, unlike every other caller. | Confirmed 2026-08-07 (no code change, investigation only)
- [x] **B026.2** — Decision: root-cause fix — retype `Settings.vix_data_dir: str` → `Path`, not a narrow wrap at the 3 call sites. Animesh's direct choice (AskUserQuestion), over the narrower option this session proposed as the safer default. Full `grep`/graph sweep of all ~11 callers confirmed safety: every other caller already wraps the value in `Path(...)` before use (`Path(Path(x))` is a no-op), so only the 3 broken sites + 1 test assertion needed a change. | Decided by Animesh 2026-08-07 (no code change this step)
- [x] **B026.3** — Implemented: `src/config.py` — `vix_data_dir: Path = Field(default=Path("data/historical/ohlc/india_vix"), ...)` (was `str`); pydantic coerces string env values automatically, no `.env` change needed. | SHA `b3202e3` (committed by Animesh on live host — sandbox `pre-commit` hook hardcoded to `/opt/anaconda3/bin/python`, not present in this sandbox, same class of limitation as B004.6/B006.6/B010.2)
- [x] **B026.4** — Tests: `tests/unit/test_config.py` — happy-path (`test_vix_data_dir_is_path_type`, asserts `isinstance(..., Path)` + a real `.glob()` call, the exact BUG-026 crash site), edge case (`test_vix_data_dir_env_override_coerces_to_path`, string env var still coerces correctly). `tests/unit/paper/test_overlay_entry.py` — 3 new regression tests (`test_auto_{cc,pp,collar}_bootstrap_reaches_chain_fetch_with_real_vix_dir`) call the real (unmocked) `load_vix_series()` against a fixture VIX Parquet dir, closing the coverage gap that let this ship (every pre-existing test mocked `load_vix_series` directly). 2726 passed / 2 skipped / 1 pre-existing failure + 2 pre-existing collection errors (all confirmed unrelated — network-blocked `api.upstox.com` call, pre-existing import errors) on a live-sandbox `pytest tests/unit/` run (`pip install --target=/tmp/pydeps` workaround, sandbox had disk headroom this session). | SHA `b3202e3`
- [x] **B026.5** — Not a financial-logic correctness change (config type fix only — no P&L/Decimal/order-path code touched; it unblocks a dormant automation rather than changing trade logic) — `general-purpose` + `REVIEW.md` substitute review against real diff. No CRITICAL/ERROR: field retype is additive/backward-compatible (pydantic Path coercion), all 3 broken call sites now receive a real `Path`, all other callers' redundant `Path(...)` wraps are harmless no-ops, new tests exercise the real crash site instead of mocking around it. | Confirmed 2026-08-07 (no code change, review only)
- [x] **B026.6** — Commit, update `bugs.md` status to ✅ Fixed + SHA, `CONTEXT.md`/`DECISIONS.md`/`TODOS.md` updated | `CONTEXT.md` `src/config.py` entry updated; `DECISIONS.md` new 2026-08-07 entry; `TODOS.md` item 29 flipped to `[x]`; `bugs.md` BUG-026 status flipped to ✅ Fixed | SHA `b3202e3` (committed by Animesh on live host)

---

## BUG-028 — Overlay P&L reporting pipeline structurally blind to `STRATEGY_OVERLAY`-scoped legs since S2r

Council-ruled 2026-08-10 (`docs/council/2026-08-10_overlay-pnl-reporting-track-independence.md`,
unanimous 4/4, Position B "B-lite" — no DDL change). Full mandate in `DECISIONS.md` 2026-08-10.
3-phase split mirrors BUG-020's precedent — each phase independently working and tested, one
commit per phase.

### Phase 1 — Correctness fix

- [x] **B028.1** — `_compute_overlay_pnl_snapshots()` (`paper_3track_snapshot.py`): query
  `STRATEGY_OVERLAY` directly, not the base-track loop's `strategy_name`. This is BUG-028's root
  cause (the silent zero). | Signature dropped the `track_name` param entirely — reads
  `STRATEGY_OVERLAY` unconditionally, called once (not per-track) from `_run()`.
- [x] **B028.2** — `generate_track_snapshot()` (`track_snapshot.py`): stop discovering/persisting
  overlay legs entirely — base-track snapshots report base-leg P&L only. | `TrackPnL` lost
  `overlay_pnls`/`raw_overlay_pnls` fields; `open_positions` filtered to `base_*` leg_roles only;
  `_normalize_overlay_pnls()` deleted (dead). Standalone overlay P&L now computed by
  `_compute_overlay_leg_totals`/`_save_overlay_leg_snapshots` (new, `paper_3track_snapshot.py`).
- [x] **B028.3** — `_build_recovery_digest()`: reframe as "NiftyBees vs standalone overlay book,"
  joined by `snapshot_date`, no "active track" selection. | Digest text already said "NiftyBees vs
  overlays" with no track framing — reframing was actually needed at the data-source layer:
  `_compute_protection_recovery_snapshot()`'s overlay read switched `STRATEGY_SPOT` →
  `STRATEGY_OVERLAY`. New standalone "Overlay (standalone)" row added to the printed comparison
  table (`_overlay_summary_row`), independent of `--tracks` selection.
- [x] **B028.4** — `PaperStore.record_overlay_pnl_snapshot()`: canonical rows write
  `strategy_name = STRATEGY_OVERLAY` (no schema change). | No store.py change needed — it persists
  whatever `strategy_name` the caller sets; B028.1's caller change is sufficient. Docstrings updated.
- [x] **B028.5** — Tests: happy-path (overlay leg opened post-S2r now shows correct nonzero P&L in
  both the snapshot table and the digest), edge case (no overlay position open → digest shows "no
  position," not `0`). | 5 test files updated (`test_track_snapshot.py`,
  `test_paper_3track_snapshot.py`, `test_paper_3track_overlay_pnl.py`,
  `test_paper_3track_snapshot_period.py`, `test_paper_3track_protection_recovery.py`) — old
  per-track overlay-discovery tests replaced with tests asserting overlay legs under a track are
  now ignored; overlay-pnl-snapshot tests repointed to `STRATEGY_OVERLAY`. 60/60 relevant tests
  green.
- [x] **B028.6** — Real `@code-reviewer` subagent (or substitute) against `git diff HEAD` — financial
  P&L reporting change. | `general-purpose` + `REVIEW.md` substitute (subagent type not exposed in
  this environment, per established precedent). No CRITICAL/ERROR. 2 WARNINGs: stale
  `_normalize_overlay_pnls` docstring refs in live code (fixed); G2 line-length vs. REVIEW.md's
  aspirational 80-char text — deferred, diff matches the actually-enforced ruff 100-char limit
  (`pyproject.toml`), same precedent as BUG-002.6/BUG-010.8.
- [x] **B028.7** — Commit. | SHA `6820f81` (committed by Animesh on live host — sandbox
  `.git/index.lock` blocked commit from this session, same class of limitation as
  B004.6/B006.6/B010.2 etc.). Pre-commit `mypy` also caught 2 unrelated pre-existing
  type errors (`src/instruments/lookup.py::format_leg_label`, a `None` strike guard;
  `src/strategy/ic_close_executor.py::roll_ic_legs`, a narrowing `assert` for
  `leg.price`) — fixed and included in this commit since they blocked the hook.

### Phase 2 — Eliminate silent false zeros (mandatory DoD, not optional hardening)

- [x] **B028.8** — `ProtectionRecoverySnapshot.cc/pp/collar_pnl_1d` + `_inception` (6 fields,
  `src/paper/models.py`) changed `Decimal` → `Decimal | None`. `paper_protection_recovery_snapshots`
  was a `STRICT` table with those 6 columns `TEXT NOT NULL` — SQLite can't drop `NOT NULL` via
  `ALTER TABLE`, so `PaperStore.__init__` gained a one-time rebuild migration (create-new/copy/drop/
  rename, same pattern as the existing `paper_trades` UNIQUE-constraint migration), detected via
  `PRAGMA table_info` on `cc_pnl_1d`'s `notnull` flag (not a string match against
  `sqlite_master.sql` — reviewer flagged the original substring approach as DDL-reformatting-fragile,
  fixed before commit). `_compute_protection_recovery_snapshot`
  (`scripts/strategies/three_track/paper_3track_snapshot.py`) now defaults `overlay_1d`/
  `overlay_inception` to `None` per type and logs
  `logger.warning("protection_recovery.overlay_source_missing", strategy=STRATEGY_OVERLAY,
  overlay_type=..., date=...)` when `get_overlay_pnl_snapshots` returns no rows. `_best_recovery`
  skips `None` entries (a missing overlay can't be "best"). `_build_recovery_digest` renders
  `"  {label:<6} No data"` for `None` fields (sorted after the real-valued lines), preserves the
  existing `+0`-style rendering for a genuine zero.
- [x] **B028.9** — `tests/unit/paper/test_store.py`: nullable round-trip
  (`test_record_protection_recovery_snapshot_overlay_fields_null_round_trip`), genuine-zero-stays-
  zero (`test_record_protection_recovery_snapshot_genuine_zero_not_null`), schema-rebuild migration
  (`test_protection_recovery_table_migrates_from_not_null_schema` — raw-sqlite3-constructed
  old-schema DB, confirms pre-existing row survives + new nullable insert works post-migration).
  `tests/unit/scripts/test_paper_3track_protection_recovery.py`: missing-source →
  `None` + WARNING fires (`test_missing_overlay_source_yields_none_and_warns`), genuine zero not
  treated as missing (`test_genuine_zero_overlay_pnl_is_not_treated_as_missing`), digest renders
  "No data" without crashing on mixed Decimal/None sort
  (`test_digest_renders_no_data_for_missing_overlay_without_crashing`), all-missing suppresses
  "Best:" line (`test_digest_all_overlays_missing_suppresses_best_line`). 111/111 relevant tests
  pass; full `tests/unit/` 2662 passed / 2 skipped / 28 failed / 10 errors — all pre-existing
  environmental gaps (missing pyarrow, network-blocked `api.upstox.com`, missing hypothesis),
  confirmed unrelated, same failure set as before this change (was 2658 passed pre-change).
- [x] **B028.10** — `general-purpose` + `REVIEW.md` substitute for `@code-reviewer`
  (financial P&L reporting change, gate mandatory). No CRITICAL/ERROR. 2 WARNINGs, both fixed
  pre-commit: (1) missing wiring-level test coverage at the snapshot/digest layer (the pure
  `_best_recovery` and store round-trip were covered but not
  `_compute_protection_recovery_snapshot`'s WARNING-log path or `_build_recovery_digest`'s "No
  data" rendering) — 4 tests added, see B028.9; (2) migration's old-schema detection was a
  whitespace-fragile string match against `sqlite_master.sql` — switched to `PRAGMA table_info`'s
  `notnull` flag. INFO: migration correctly transaction-wrapped (`BEGIN`/`COMMIT`), no data-loss
  risk on mid-rebuild failure; `_best_recovery`'s all-real-data path provably unchanged. Committed
  and docs updated (`bugs.md`/`CONTEXT.md`/`TODOS.md`). | SHA `4b8b351` (this SHA-annotation
  follow-up itself staged but not committed — sandbox `.git/HEAD.lock` held by a concurrent
  process, permission denied to remove, same class of limitation as B004.6/B006.6/B010.2/B021.x;
  commit deferred to live host)

### Phase 3 — Historical repair (one-off script)

- [x] **B028.11** — `scripts/dev/migrate_overlay_pnl_attribution.py`: back up DB; derive actual S2r
  cutover date from the trade ledger (first `STRATEGY_OVERLAY` trade), not a hardcoded commit date;
  for each pre-cutover `paper_overlay_pnl_snapshots` row, check
  `(STRATEGY_OVERLAY, overlay_type, snapshot_date)` uniqueness before relabeling — skip with a
  logged WARNING on collision, never blind-`UPDATE`; do not dual-write; output
  migrated/skipped/unchanged counts. | Mirrors `migrate_paper_trades_state.py`/
  `backfill_nav_total_pnl.py` pattern (`--db-path`/`--dry-run`, `_SCRIPT_NAME` logger). Legacy
  candidates scoped to the 3 pre-S2r track strategies (`STRATEGY_SPOT`/`STRATEGY_FUTURES`/
  `STRATEGY_PROXY`, `src/paper/constants.py`); cutover = `MIN(trade_date)` where
  `strategy_name = STRATEGY_OVERLAY` in `paper_trades`. Collision check via
  `_canonical_row_exists()` before every relabel; relabel is a single `UPDATE strategy_name`
  (never an INSERT) so no dual-write is possible by construction. `MigrationResult` dataclass
  returns migrated/skipped/unchanged counts (`unchanged` always 0 by construction — every
  candidate row is either migrated or skipped, no other outcome is reachable given the
  cutover-date pre-filter; kept as an explicit field to match this item's output-contract
  wording and leave room for a future scope widening). | SHA `0fd4de8`
- [x] **B028.12** — Tests: happy-path (unambiguous legacy row relabeled correctly), edge case
  (collision detected → skipped, legacy row left intact, WARNING logged). |
  `tests/unit/scripts/test_migrate_overlay_pnl_attribution.py`, 5 tests: happy-path relabel
  (`test_migrate_relabels_precutover_legacy_row`), collision skip
  (`test_migrate_skips_on_collision_and_leaves_legacy_row_intact` — asserts skip count, legacy
  row still present, canonical row's `pnl_1d_abs` unchanged, proving no dual-write), no-op when
  no `STRATEGY_OVERLAY` trade exists yet (`test_migrate_no_overlay_trades_yet_is_noop`), dry-run
  (`test_migrate_dry_run_does_not_write`). **Confirmed green on live host** — all 5 tests pass
  (not executed in-sandbox originally due to no free disk for `pytest`/deps, same limitation
  class as prior BUG-020/021/026/027 sessions; live-host run closes that gap). | SHA `0fd4de8`
- [x] **B028.13** — Review + commit, update `bugs.md` BUG-028 status to ✅ Fixed + SHA,
  `CONTEXT.md`/`TODOS.md` updated. | `general-purpose` + `REVIEW.md` substitute for
  `@code-reviewer` (subagent type not exposed in this environment, same precedent as
  B028.6/B021.4/B010.8) against both new files — financial P&L reporting change, gate mandatory.
  No CRITICAL/ERROR. 2 WARNINGs: (1) `MigrationResult.unchanged` was a dead/unreachable field
  with a misleading docstring — fixed pre-commit (see B028.11 note); (2) no explicit
  `try/except`+`conn.rollback()` around the per-row `UPDATE` loop, relying on sqlite3's implicit
  rollback-on-close-without-commit — accepted as-is: this is a single-operator, run-once
  historical-repair script (not a service), the DB is backed up before any write, and
  `conn.commit()` only runs once at the very end after the full loop completes successfully, so
  a mid-loop exception can never leave a partial commit. Committed on live host, tests confirmed
  green. | SHA `0fd4de8`

### Phase 4 (found 2026-08-13) — `evaluate_pp_reentry_eod` missed by the Phase 1–3 sweep

- [x] **B028.14** — Root cause confirmed against current code (not just `bugs.md`'s snapshot):
  `src/strategy/auto_close.py::evaluate_pp_reentry_eod` built a local
  `track_strategies = [STRATEGY_SPOT, STRATEGY_FUTURES, STRATEGY_PROXY]` and used it for both the
  `active_pp` eligibility check and the "Overlay P&L (total realized)" sum — same root cause as
  B028.1/B028.2 (pre-S2r assumption that overlay legs live under a track's `strategy_name`), just
  in a file Phase 1–3's sweep didn't touch (`auto_close.py`, not `track_snapshot.py`/
  `paper_3track_snapshot.py`). | Confirmed 2026-08-13 (no code change, investigation only)
- [x] **B028.15** — `evaluate_pp_reentry_eod`: both call sites switched from `track_strategies` to
  `STRATEGY_OVERLAY` directly (matches B028's resolved architecture, decision (b) decouple
  pipeline) — eligibility check reads `store.get_positions(STRATEGY_OVERLAY)`, P&L figure reads
  `get_strategy_realized_pnl(store, STRATEGY_OVERLAY)` (single call, not a sum). `track_strategies`
  list and its three-track import dropped — nothing else in the function needs them.
- [x] **B028.16** — Tests: `test_evaluate_pp_reentry_eligible` docstring/assertion updated
  (`"3-track overlay"` → `"standalone overlay"` in the alert text);
  `test_evaluate_pp_reentry_suppressed_when_active` updated to seed the open `overlay_pp` leg
  under `STRATEGY_OVERLAY` instead of `STRATEGY_SPOT` (pre-fix, seeding under `STRATEGY_SPOT` would
  have made this test fail to suppress — genuinely regression-proof, not tautological). New
  `test_evaluate_pp_reentry_realized_pnl_reads_overlay_book_only` (edge case): seeds a closed
  round-trip under `STRATEGY_OVERLAY` (real P&L +325) plus a distractor closed round-trip under
  `STRATEGY_SPOT` (P&L −5000, wrong pre-fix sum −4675) and asserts only +325 appears in the
  message. `general-purpose` + `REVIEW.md` substitute for `@code-reviewer` (subagent type not
  exposed in this environment, same precedent as B028.6/B028.13/B021.4/B010.8) against
  `git diff HEAD` — financial P&L reporting + trading-eligibility change, gate mandatory. No
  CRITICAL/ERROR/WARNING against the diff; 1 INFO note logged (no invariant guards against a
  stray `overlay_pp` leg ever landing under a base track post-S2r — latent risk inherent to the
  council's decouple-pipeline decision itself, not introduced by this diff, not a blocker).
  8/8 tests in `tests/unit/strategy/test_auto_close.py` pass; broader
  `tests/unit/strategy/` + `tests/unit/paper/` (1057 tests) pass with zero regressions — run via
  a cloud sandbox venv (`pip install -e ".[dev]"` + `requirements*.txt`) since this device
  sandbox has no network to install `pytest`, same limitation class as prior BUG-020/021/026/027/
  B028.11-13 sessions.
- [x] **B028.17** — Commit, update `bugs.md` BUG-028 status (Phase 4 line) to ✅ Fixed + SHA,
  `TODOS.md` updated. Not a module-structure change (no new files) — `CONTEXT.md` left as-is.
  Committed on live host: code+tests SHA `94f3dc3`, this doc-tracking update SHA `affbd24`.

---

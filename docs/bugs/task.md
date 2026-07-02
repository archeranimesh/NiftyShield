# docs/bugs/ — Task Checklist

> Find the first unchecked `- [ ]` line. That is your only task for this session.
> Tick the box and append `| SHA <commit_sha>` when done. Add one line to `TODOS.md`
> session log. Full bug detail for each item: `docs/bugs/bugs.md`.

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
- [ ] **B002.4** — Replace `net_qty / lot_size` full-delta approximation in `_position_delta` with actual option delta from chain snapshot where available (short 1-lot put ≠ short 1-lot future)
- [ ] **B002.5** — Tests: happy-path (short put → positive delta, correct magnitude), edge case (unrecognised/legacy `instrument_key` still falls back safely with a warning, does not silently misclassify)
- [ ] **B002.6** — Run real `@code-reviewer` subagent against `git diff HEAD` (financial-logic gate, mandatory per root `CLAUDE.md`) — resolve CRITICAL/ERROR before commit
- [ ] **B002.7** — Commit, update `bugs.md` status to ✅ Fixed + SHA, update `CONTEXT.md` if `PaperPosition` schema changed

---

## BUG-003 — `_post_expiry_gate` inverted monthly window

- [x] **B003.1** — Root-cause confirmed: gate checks `_last_tuesday_of_month(today.year, today.month)` (the cycle being entered) instead of the prior settled cycle | Confirmed 2026-07-02 (no code change, investigation only)
- [ ] **B003.2** — Fix: reference previous month's `_last_tuesday_of_month` (last settled expiry) instead of current month's; block only same-day/next-day re-entry immediately after that settlement, not the whole new cycle
- [ ] **B003.3** — Verify fix doesn't disturb the Tuesday-expiry logic documented in `REFERENCES.md` (SEBI change, April 2026) — same `_last_tuesday_of_month` helper is shared
- [ ] **B003.4** — Check whether `paper_ic_entry_v2.py` already solved this correctly (`TODOS.md` 2026-06-28 IC-V2-13 fix log says its own gate switched to BOD expiry date, `_last_tuesday_of_month` removed there) — if so, port that approach into the shared `ic_entry_gates.py::_post_expiry_gate` instead of re-deriving a fix from scratch
- [ ] **B003.5** — Tests: happy-path (first trading day after prior settlement → entry allowed), edge case (same day as prior settlement → still blocked), edge case (year rollover, e.g. Dec → Jan)
- [ ] **B003.6** — Run real `@code-reviewer` subagent against `git diff HEAD` before commit
- [ ] **B003.7** — Commit, update `bugs.md` status to ✅ Fixed + SHA

---

## BUG-004 — `resolve_ivr` gates on a stale 252-day window with no recency check

- [x] **B004.1** — Root-cause confirmed: `compute_ivr` validates window row-count (≥252) but never window recency; VIX parquet series stops at 2026-06-25, `mtime` 2026-06-26 21:16, untouched since — 5 trading days stale as of 2026-07-02 despite a documented weekly refresh cron | Confirmed 2026-07-02 (no code change, investigation only)
- [ ] **B004.2** — Investigate why the 2026-06-29 (Monday) `refresh_vix.py` cron run didn't advance the file past 2026-06-25: check cron logs, confirm the cron is actually installed on the live host (not just documented in `TODOS.md`), re-run manually and observe whether it succeeds
- [ ] **B004.3** — Add a recency check to `compute_ivr` (`src/backtest/ivr.py`) or `resolve_ivr` (`scripts/strategies/ic/ic_entry_gates.py`): if `window.index.max()` is more than N trading days behind `today`, log a WARNING (or treat as gate-data-unavailable, consistent with the existing `ivr is None` hard-block path) instead of silently gating on a stale window
- [ ] **B004.4** — Tests: happy-path (fresh window → no warning), edge case (stale window past threshold → warning/block fires), edge case (window exactly at threshold boundary)
- [ ] **B004.5** — Run real `@code-reviewer` subagent against `git diff HEAD` before commit
- [ ] **B004.6** — Commit, update `bugs.md` status to ✅ Fixed + SHA
- [ ] **B004.7** — **Once B004.2 + B004.3 are both done:** recalculate IVR for every IC entry decision (allowed or rejected) made between 2026-06-26 and the cron-fix date using the now-current window. Confirm no entry was wrongly blocked or wrongly allowed during the stale-data period. Log findings in `bugs.md` under B004 — do not close this bug until that recheck is done, even after the code fix lands.

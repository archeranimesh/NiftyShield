# variance-gate — Story Specs

> One task per session. Find the first unchecked item in `variance_gate_tasks.md`. That is your only task.
> Full gate specification: `docs/plan/variance-gate/variance_gate_spec.md`.
> After each task: tick `variance_gate_tasks.md`, append evidence reference, add one line to `TODOS.md`.

---

## VG0 — CSP v1 Spec Reconciliation

**Status:** NOT STARTED
**Owner:** Animesh + Cowork
**Phase:** 0 (prerequisite — must complete before any gate evaluation is meaningful)
**Blocks:** VG1, VG2, VG3, VG4 (all gate evaluations reference csp_nifty_v1.md)
**Blocked by:** nothing
**Estimated effort:** S (≤1 day)

### Problem statement

`docs/strategies/csp_nifty_v1.md` is the gate's declared single source of truth, but it
currently contains four unresolved internal inconsistencies. Evaluating any gate criterion
against an ambiguous spec produces ambiguous results. Resolve all four before the first
gate criterion is evaluated.

### Acceptance criteria

- [ ] **Lot size:** confirmed as 65 units (per NSE circular for Nifty 50 effective 2024-11);
      any reference to 50 units updated or annotated with the transition date.
- [ ] **Time stop:** unambiguous definition — "21 calendar days from entry date" (not DTE
      remaining); spec and `BACKTEST_PLAN.md` use identical wording.
- [ ] **R-number naming:** consistent labels across `csp_nifty_v1.md` and `BACKTEST_PLAN.md`
      (R1–R7 or whichever scheme is canonical — pick one, update both files).
- [ ] **R4 definition:** single definition — either event filter or 200-DMA trend filter;
      if both apply, they are named R4a and R4b with explicit semantics for each.

### Definition of Done

- [ ] `docs/strategies/csp_nifty_v1.md` internally consistent; no conflicting references remain
- [ ] `BACKTEST_PLAN.md` R-number labels and time-stop definition aligned with spec
- [ ] `code-reviewer` agent clean on diff (docs-only; no code changes expected)
- [ ] `DECISIONS.md` entry added: "CSP v1 spec reconciliation — lot size 65, time stop calendar days, R-numbers canonical"
- [ ] `TODOS.md` session log entry added
- [ ] Commit landed: `docs(strategies): reconcile CSP v1 spec — lot size, time stop, R-numbers, R4`
- [ ] `variance_gate_tasks.md` VG0 ticked with commit SHA

### Technical notes

- Read `docs/strategies/csp_nifty_v1.md` in full before editing — do not patch blindly.
- Use `grep -n "lot size\|50 units\|65 units\|time stop\|21 DTE\|R3\|R4\|event filter\|200.DMA" docs/strategies/csp_nifty_v1.md BACKTEST_PLAN.md`
  to locate every occurrence before deciding canonical form.
- Docs-only commit: skip `test-runner` agent. `code-reviewer` is still required (docs review).
- Do not change strategy parameters (delta target, IVR thresholds, stop levels) — reconcile naming and definitions only.

### Non-goals

- Do not re-derive strategy parameters or change entry/exit rules.
- Do not add new R-filters beyond what is already specified.
- Do not touch any Python files.

---

## VG1 — Tier 0.5 Two-Cycle Operational Review

**Status:** NOT STARTED
**Owner:** Animesh (primary) + Cowork (query support)
**Phase:** 0 (early sanity check, not statistical validation)
**Blocks:** nothing formally — but findings here may require fixes before VG2
**Blocked by:** 2 executed paper CSP cycles in DB
**Estimated effort:** S (review session, <1 day)

### Problem statement

At N=2 the gate has no statistical power, but plumbing errors (wrong strike selected, bid/ask
not recorded, P&L not reconciling) are cheap to fix early and expensive to discover at N=6.
This checkpoint exists to catch implementation bugs, not validate the strategy.

### Acceptance criteria

- [ ] **Strike selection:** for each of the 2 cycles, confirm the recorded strike was actually
      closest to the target delta at entry time (query `paper_trades` + option chain snapshot
      for the entry date).
- [ ] **Bid/ask/mid recording:** `entry_price` field reflects mid-price (not bid or ask alone).
      Verify against chain snapshot for entry date.
- [ ] **P&L reconciliation:** closed cycle P&L matches `(entry_price − exit_price) × qty`.
      For open cycles: unrealized P&L matches current mark × qty.
- [ ] **NiftyBees collateral:** `niftybees_delta_lots` non-zero in `PortfolioDelta` output for
      the periods when NiftyBees was pledged. Verify via `nuvama_intraday_snapshots` or
      `daily_snapshots`.
- [ ] **R3/R4 skip logic:** any skipped entry during the observation window has a logged reason
      (IVR below threshold, event filter active). Confirm entries were skipped correctly
      when R3/R4 conditions were met.

### Definition of Done

- [ ] All 5 criteria above reviewed and documented
- [ ] Findings recorded in `docs/strategies/csp_nifty_v1.md` → new "Tier 0.5 Review" section
      with date, cycle count, and one-line verdict per criterion (PASS / FAIL / N/A)
- [ ] Any FAIL items produce a bug fix task in `TODOS.md` before proceeding to VG2
- [ ] Commit landed: `docs(strategies): CSP v1 Tier 0.5 two-cycle operational review`
- [ ] `variance_gate_tasks.md` VG1 ticked with date

### Technical notes

- Query pattern for P&L check:
  ```sql
  SELECT trade_id, strategy_name, entry_price, exit_price, qty, closed_at
  FROM paper_trades
  WHERE strategy_name = 'paper_csp_nifty_v1' AND closed_at IS NOT NULL;
  ```
- Cross-reference against `paper_leg_snapshots` for mark-to-market on open legs.
- If fewer than 2 cycles are closed when this task is actioned: tick partial criteria that
  can be assessed, note remaining ones as PENDING, revisit after 2nd cycle closes.

### Non-goals

- Not a statistical validation — do not compute mean P&L or compare to backtest.
- Do not change strategy parameters based on 2 observations.

---

## VG2 — Gate A + B: Minimum Sample + Exit-Path Validation

**Status:** NOT STARTED
**Owner:** Animesh (observation) + Cowork (replay support when Phase 1 data available)
**Phase:** 0.8 (gate criterion)
**Blocks:** VG4 (Z-score requires ≥6 cycles)
**Blocked by:** time (≥6 cycles ≈ 6+ months of paper trading); VG1 PASS
**Estimated effort:** XL (ongoing observation — not a single session)

### Problem statement

Gate A requires ≥6 executed cycles AND ≥9 calendar months of entry-decision observation.
Gate B requires each of the three exit mechanisms to be validated at least once — either
through live paper occurrence or deterministic historical replay. Replay is blocked until
Phase 1 data pipeline (task 1.3a) is live.

### Acceptance criteria

**Gate A:**
- [ ] ≥6 executed paper CSP cycles recorded in `paper_trades` (closed or with exit queued)
- [ ] ≥9 calendar months elapsed since first entry-decision date (entry OR documented skip)
- [ ] Skipped entries documented in `TODOS.md` session log with date and reason code

**Gate B:**
- [ ] Profit-target (50%) exit: at least one cycle closed at 50% premium captured
- [ ] Time-stop (21-day): at least one cycle closed at 21-calendar-day time stop
- [ ] Delta/mark-stop: at least one cycle closed on delta ≤ −0.35 or mark ≥ 2× premium
      (live paper required before Tier 2; historical replay acceptable for Tier 1 only)

### Definition of Done

- [ ] Gate A criteria verified by querying `paper_trades` + session log
- [ ] Gate B criteria verified (live occurrence logged or replay harness run documented)
- [ ] Findings recorded in `docs/strategies/csp_nifty_v1.md` → "Phase 0.8 Gate Evidence" section
- [ ] `variance_gate_tasks.md` VG2.A, VG2.B1–B3 ticked with dates and evidence references
- [ ] `DECISIONS.md` entry noting gate A + B pass date

### Technical notes

- Replay harness: do not build until Phase 1.3a (NSE Bhavcopy + VIX pipeline) is committed.
  Design doc lives at `docs/plan/replay_harness.md` (to be written when Phase 1 starts).
- Query for exit-type distribution:
  ```sql
  SELECT exit_reason, COUNT(*) as n
  FROM paper_trades
  WHERE strategy_name = 'paper_csp_nifty_v1'
  GROUP BY exit_reason;
  ```
  Requires `exit_reason` field populated at close time — verify `record_paper_trade.py`
  captures this before assuming the data is available.

### Non-goals

- Do not force trades to satisfy exit-type count — if market doesn't produce a delta stop,
  wait for replay harness.
- Gate A count excludes filter-skipped entries (those are observations, not cycles).

---

## VG3 — Gate C: Regime Completeness

**Status:** NOT STARTED
**Owner:** Animesh (observation) + Cowork (replay when available)
**Phase:** 0.8 (gate criterion)
**Blocks:** Tier 1 pilot eligibility (alongside VG2 + VG4)
**Blocked by:** market events (or Phase 1 replay harness for synthetic replay)
**Estimated effort:** M once replay harness exists; XL if waiting for live occurrence

### Problem statement

Six calm paper cycles compared against an 8-year backtest distribution including COVID
and IL&FS produces a spurious variance flag — not because the system is broken, but because
the sample is drawn from a non-stationary subset. At least one stress episode must be
observed or replayed before Tier 1 deployment.

### Acceptance criteria

At least **one** of the following must be satisfied:

- [ ] **High IVR:** ≥1 executed cycle with India VIX IVR > 50 at entry (live paper preferred;
      IVR is computed via `src/backtest/ivr.py` — verify it is populated in `paper_trades.ivr_at_entry`)
- [ ] **Drawdown stress:** ≥1 holding window during which Nifty had ≥5% intraday peak-to-trough
      decline (monitor via `nuvama_intraday_snapshots`; threshold is a single intraday event,
      not cumulative)
- [ ] **Delta pressure:** ≥1 cycle where short-put delta reached ≤ −0.35 before any exit fired
      (requires intraday Greeks data — logged via `paper_leg_snapshots` if `paper_3track_snapshot.py`
      captures Greeks at the time)

### Definition of Done

- [ ] One criterion above satisfied (live or replay)
- [ ] Evidence documented: date, metric value, data source (snapshot table + row ID or replay run log)
- [ ] Recorded in `docs/strategies/csp_nifty_v1.md` → "Phase 0.8 Gate Evidence" section
- [ ] `variance_gate_tasks.md` VG3.C ticked with date and criterion letter (a/b/c)
- [ ] If replay used: replay harness run log committed to `docs/plan/variance-gate/replay_run_log.md`

### Technical notes

- IVR > 50 check: query `paper_trades` for `ivr_at_entry > 0.50` (stored as float 0–1 range).
  Confirm with `get_code_snippet("PaperTrade")` before querying.
- Drawdown check: `nuvama_intraday_snapshots` — compare intraday high/low columns over the
  holding window. Or use `nuvama_intraday_tracker.py` which already monitors extremes.
- Delta pressure: `paper_leg_snapshots.delta` field — query for min delta across the holding window.
  Only valid if Greeks were populated during that period (from 2026-04-25 onwards per CONTEXT.md).
- If market does not provide any of these within 9 months: use historical replay
  (COVID 2020-03-16 or IL&FS 2018-09-21). Do not hold deployment hostage indefinitely.

### Non-goals

- Do not require ALL THREE criteria — one is sufficient.
- Do not build replay harness here — it is Phase 1 scope (`docs/plan/replay_harness.md`).

---

## VG4 — Gate D: Regime-Matched Z-Score

**Status:** NOT STARTED
**Owner:** Cowork (computation) + Animesh (sign-off)
**Phase:** 0.8 (final gate criterion)
**Blocks:** Tier 1 pilot eligibility
**Blocked by:** Phase 1 task 1.11 (Z-score methodology) + VG2.A (≥6 cycles)
**Estimated effort:** M (once 1.11 is implemented)

### Problem statement

The global Z-score (paper vs full 8-year backtest) is biased when the paper sample is drawn
from a calm low-volatility period while the backtest includes COVID and IL&FS. A regime-matched
comparison filters the backtest for periods with similar IVR/vol conditions to the paper window,
producing a fair comparison. Both Z-scores must pass.

At N=6 the gate has <40% power to detect 0.5 SD degradation. The Z-score is a gross failure
detector only — it unlocks Tier 1 limited pilot, not full deployment.

### Acceptance criteria

- [ ] `|Z| ≤ 1.5` on the full 8-year backtest distribution
- [ ] `|Z| ≤ 1.5` on the regime-matched subset (IVR/vol conditions matching paper period)
- [ ] Z-scores and methodology documented (sample N, backtest N, mean, SD, Z value for both)
- [ ] Regime-matching criteria documented (what IVR/vol conditions defined the subset)

### Definition of Done

- [ ] Z-score computation run per methodology in `BACKTEST_PLAN.md` task 1.11
- [ ] Both Z-scores ≤ 1.5 in absolute value
- [ ] No unresolved accounting or data defects across all paper cycles
- [ ] Results recorded in `docs/strategies/csp_nifty_v1.md` → "Phase 0.8 Gate Evidence"
- [ ] `variance_gate_tasks.md` VG4.D ticked with date and Z-score values
- [ ] `DECISIONS.md` entry: "Phase 0.8 gate passed — Tier 1 pilot eligibility confirmed"
- [ ] Animesh sign-off recorded in DECISIONS.md

### Technical notes

- Z-score formula: `Z = (paper_mean − backtest_mean) / (backtest_sd / sqrt(N_paper))`
  where backtest_sd is from the filtered regime-matched subset for the second computation.
- Regime-matched subset definition: cycles in the backtest where IVR (252-day VIX percentile)
  was in the same quartile as the paper period's average IVR.
- Implementation lives in `BACKTEST_PLAN.md` task 1.11. Do not implement here.
- Statistical interpretation: `|Z| ≤ 1.5` means "no gross mismatch detected" — not proof of
  equivalence. At N=6 there is 60% probability of a false pass for 0.5 SD degradation.
  The graduated tier structure (1-lot limit, manual approval) compensates for this.

### Non-goals

- Do not interpret a passing Z-score as statistical proof of strategy quality.
- Do not use this gate to justify full-size deployment (that is Tier 2 scope).
- Do not compute Z-score before ≥6 cycles are closed.

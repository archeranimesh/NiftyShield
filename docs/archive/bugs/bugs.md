# Bug Registry — Archive

> Closed/fixed bug entries moved out of `docs/bugs/bugs.md` to keep the live registry focused
> on open work, mirroring the `docs/plan/` → `docs/archive/plan/` convention. Each entry here
> was ✅ Fixed (or ⚪ Closed as moot) at time of archival — see the `Status` line for the SHA(s).
> This file is read-only history: do not add new entries here directly, and do not resume work
> on an archived bug without first moving it back to `docs/bugs/bugs.md` (if genuinely reopened,
> file a fresh `BUG-NNN` instead — the ID sequence is a discovery-order log, not reusable).
>
> Live registry: `docs/bugs/bugs.md` | Live checklist: `docs/bugs/task.md` | Archived checklist: `docs/archive/bugs/task.md`

---

## BUG-002 — Option delta sign/magnitude corrupted by put-call misclassification

| Field | Value |
|---|---|
| Severity | **CRITICAL** — feeds the portfolio delta entry gate; wrong sign inverts risk reads |
| Status | ✅ Fixed (2026-07-02, SHA 62ed6ef) |
| Discovered | 2026-07-02, triaging `ic_weekly.log` entry rejection |
| Location | `src/risk/delta_tracker.py::_position_delta` (lines 140–175) |

**Fix summary (B002.3 + B002.4, SHA 96398b4 + 62ed6ef):** Sign classification now uses `PaperPosition.option_type` (resolved read-time by `PaperStore` via `InstrumentLookup`, not `instrument_key` substring matching). Magnitude: `aggregate_delta`/`_position_delta` accept an optional `position_deltas: dict[instrument_key, Decimal]` supplying the real chain-derived delta; falls back to the old `±net_qty/lot_size` approximation with a logged WARNING when unavailable — never silent. Module boundary decided by council 2026-07-02 (`docs/council/2026-07-02_paper-delta-source-architecture.md`): `src/risk/` stays pure/zero-I/O; the caller (`ic_entry_gates.py`/`paper_ic_entry.py`) owns chain resolution — **not yet wired** as of SHA 62ed6ef, so `aggregate_delta` callers today still omit `position_deltas` and get the (now correctly-signed) approximation. Wiring the caller-side chain resolution is follow-on work, not tracked under a B002.x line yet — add to `TODOS.md` if picked up.
`aggregate_delta` cross-strategy pooling question (see root cause section below) remains unresolved — flagged for Animesh, not addressed by this fix.

**Symptom:** `ic_weekly.log` — `ERROR: Portfolio delta check failed. Projected=6.901 lots (outside [-0.05, 0.25]). Stop.` A projected delta of 6.9 lots against a ±0.05..0.25 gate is not a marginal miss; something upstream is structurally wrong.

**Root cause:** `_position_delta` classifies a position as put/call by substring-matching `"PE"` / `"CE"` against `pos.instrument_key`:

```python
if "PE" in key:
    return -net_qty / lot_size_d
if "CE" in key or ("NSE_FO|" in key and "PE" not in key):
    return net_qty / lot_size_d
```

Real Upstox `instrument_key` values are pure numeric (`NSE_FO|63916`, confirmed against `REFERENCES.md` — every listed key is `NSE_FO|<digits>`). The literal substrings `"PE"`/`"CE"` never appear in a numeric key, so the put branch is dead code. Every option position — put or call, long or short — falls into the `else` branch and is priced as a naked future: `delta = net_qty / lot_size` (full ±1.0 delta per lot, sign taken straight from `net_qty`).

Concrete case: `paper_csp_nifty_v1` holds a short put, `net_qty=-65` (1 lot short). Correct delta contribution is a small **positive** value (~0.25–0.35 lots — short put is bullish). The code returns **-1.0 lot** — wrong sign, ~3–4x wrong magnitude.

Compounding factor (needs a decision, not just a fix): `aggregate_delta` in `scripts/strategies/ic/paper_ic_entry.py` (line 365) sums across **every** open paper strategy via `store.get_strategy_names()`, not just the calling strategy's own book. `paper_nifty_futures`, `paper_nifty_proxy`, and `paper_nifty_spot` (NiftyBees + FO legs) all feed the same aggregate as the IC's own risk. Whether that cross-strategy pooling is intentional (true portfolio-level delta) or a bug (double-counting parallel proxy/hedge books) is unresolved — flag for Animesh, do not assume during the fix.

**Underlying structural gap:** `PaperPosition` (`src/paper/models.py`) carries no `option_type` / `strike` / `asset_type` field — only `instrument_key`, `net_qty`, `avg_cost`, `avg_sell_price`. There is no reliable signal in the object to reconstruct put/call. The `legs` table (portfolio module, separate from `paper_trades`) *does* carry `asset_type`, `direction`, `strike` — that data exists elsewhere in the schema, `_position_delta` just isn't sourcing it.

**Suggested fix:** Either (a) extend `PaperPosition` with an `option_type: Literal["PE", "CE", "FUT", "EQ"] | None` field populated at trade-record time from the instrument lookup (`InstrumentLookup`), or (b) join against `legs.asset_type` / `legs.direction` when constructing `PaperPosition` in `PaperStore.get_position`. Also replace the crude `net_qty / lot_size` full-delta approximation with the actual option delta from the chain snapshot where available — a short 1-lot put is not equivalent to a short 1-lot future.

**Related:** IDs continue from root `BUGS.md` (`BUG-001` — unrelated, `daily_snapshot.py` backfill gap). See `docs/bugs/prompt.md` for how the two registries relate.

---

## BUG-003 — `_post_expiry_gate` blocks entry for the entire monthly cycle instead of only the settlement day

| Field | Value |
|---|---|
| Severity | **HIGH** — blocks 100% of monthly IC entries except a ~1–3 day window per month |
| Status | ✅ Fixed (2026-07-02, SHA 2c6f771) |
| Discovered | 2026-07-02, triaging `ic_monthly.log` / `ic_v2_monthly.log` entry rejection |
| Location | `scripts/strategies/ic/ic_entry_gates.py::_post_expiry_gate` (lines ~68–95) |

**Fix summary (B003.2–B003.7, SHA 2c6f771):** Added `_most_recently_settled_expiry(today)` — returns the current calendar month's last Tuesday if it has already occurred, otherwise falls back to the previous month's last Tuesday (with Dec→Jan year-rollover handling). `_post_expiry_gate` now blocks only when `today <= that reference date` — i.e. same-day re-entry on the settlement date itself — and allows entry the very next day, instead of blocking the entire new cycle against its own future expiry. B003.4 investigation confirmed there was no separate, already-fixed `paper_ic_entry_v2.py` gate to port from — commit `23e8e93` (2026-06-28) had already moved the (still-buggy) calendar-based gate into the shared `ic_entry_gates.py`, which both V1 and V2 call; that commit fixed a different bug (comparing against a bad future-target expiry) but left the "wrong cycle" reference in place, which is what this fix addresses. `_last_tuesday_of_month` itself is untouched (B003.3 verified no impact on the SEBI Tuesday-expiry logic in `REFERENCES.md`). Tests: 3 new/rewritten cases per file — regression (mid-cycle pass), day-after-settlement pass, same-day-settlement block, Dec→Jan year rollover — in both `tests/unit/strategies/ic/test_ic_entry_gates.py` and `tests/unit/strategies/ic/test_paper_ic_entry_v2.py` (stale always-block assertions from the old bug were rewritten, not just supplemented). 67/67 tests pass in `tests/unit/strategies/ic/`. Reviewed via `general-purpose` agent substituting for `code-reviewer` (not exposed in this Cowork environment, same workaround as BUG-002) against `REVIEW.md` — no CRITICAL/ERROR findings.

**Symptom:** `ic_monthly.log` / `ic_v2_monthly.log` — `ERROR: post_expiry_gate: current month expiry 2026-07-28 has not yet passed (today=2026-07-01). Entry is only valid after settlement.` Today is 2026-07-01 — the June monthly cycle already settled 2026-06-30, a fresh July series just opened. This is exactly when entry should be allowed, not blocked.

**Root cause:**

```python
today = date.today()
expiry = _last_tuesday_of_month(today.year, today.month)
if today <= expiry:
    sys.exit(1)   # blocks entry
```

`_last_tuesday_of_month(today.year, today.month)` computes the expiry of the **current** calendar month — the same cycle the caller is trying to enter — and blocks until that expiry has already passed. That inverts the intended check: you enter a position *before* its own expiry, not after. As written, the monthly IC can only ever enter during the handful of days between this month's expiry and month-end rollover (here: 2026-07-29 to 2026-07-31), then immediately re-blocks for the entirety of the next month.

**Intended behavior** (per module docstring: "block entry before last-Tuesday settlement"): a same-day/next-day guard preventing re-entry on the same date the *previous* cycle is still settling — not a blackout of the entire new cycle.

**Suggested fix:** Reference the *previous* month's `_last_tuesday_of_month` (the cycle that just settled) instead of the current month's, and only block same-day re-entry immediately following that settlement date — not the current cycle's own (future) expiry.

**Related:** shared helper `_last_tuesday_of_month` also backs `REFERENCES.md`'s documented Tuesday-expiry logic (SEBI change, April 2026) — verify the fix doesn't disturb that call site.

---

## BUG-004 — `resolve_ivr` gates on a stale 252-day window with no recency check

| Field | Value |
|---|---|
| Severity | **MEDIUM** — currently benign (VIX mid-range, unlikely to have crossed the 1-year band in the missing days) but silently wrong under a vol spike/crush |
| Status | ✅ Fixed (2026-07-02, SHA 143335e) |
| Discovered | 2026-07-02, verifying IVR=0.24 reading behind `ic_leaps.log` / `ic_yearly.log` rejections |
| Location | `src/backtest/ivr.py::compute_ivr`; `scripts/strategies/ic/ic_entry_gates.py::resolve_ivr` |

**Symptom:** none directly logged — found while independently verifying the IVR=0.24 gate rejection was correct. `resolve_ivr` combines a **live** `vix_today` (from `IntradayMarketStore.get_latest_vix_today()` / `fetch_vix_latest()`) with a **historical** 252-day window loaded from `data/historical/ohlc/india_vix/*.parquet` for the min/max normalization. Pulled the parquet series directly: 2,476 daily rows, 2016-06-27 to **2026-06-25**, zero gaps >5 calendar days anywhere in the decade (history itself is complete and correctly ingested). But the file's `mtime` is 2026-06-26 21:16 and hasn't been touched since — as of today (2026-07-02) the window is missing 5 trading days (Jun 26, 29, 30, Jul 1, Jul 2). `TODOS.md` documents a weekly refresh cron (`refresh_vix.py`, Monday 08:00 IST, 30-day lookback) that should have caught at least through Jun 26 by the Jun 29 run — it visibly didn't.

**Root cause:** `compute_ivr` only validates window *size* (`len(vix_series) < 252 → None`), never window *recency*. A stale-but-full-count series passes silently. The numerator (`vix_today`) is always fresh (live fetch), but the denominator (`window_min`/`window_max`) can be arbitrarily stale as long as the row count clears 252 — there is no check that `window.index.max()` is within N trading days of `today`.

**Why today's 0.24 is very likely still correct despite this:** recomputed the window directly — min **9.15**, max **27.89** over 2025-06-19 to 2026-06-25 (18.74-point range). For the missing 5 days to have changed the percentile, VIX would have had to print a new 1-year high or low, which is a big ask from a level sitting around 13. So this bug did not cause the `ic_leaps`/`ic_yearly` rejections — but it's a latent correctness gap: if VIX had spiked or crushed in the missing days, `resolve_ivr` would gate on a wrong percentile with no error or warning surfaced.

**Suggested fix:** (a) add a recency check in `compute_ivr` or `resolve_ivr` — e.g. `if (today - window.index.max()).days > N: log warning / treat as stale`; (b) separately, verify why the Monday 2026-06-29 `refresh_vix.py` cron run didn't advance the file past 2026-06-25 — check cron logs / whether the cron is actually installed on the live host, not just documented in `TODOS.md`.

**Fix summary (B004.2–B004.5):** B004.2 investigation ruled out a missing/broken cron — `crontab -l` on the live host confirmed the entry is installed exactly as documented (`45 15 * * 1`). Root cause of the staleness was instead: Upstox's `from_date` query param on the historical-candle endpoint appears not to filter the response (`rows=2475`, essentially full decade history, returned on both the original Jun-29 cron run and a manual Jul-2 re-run) combined with an observed ~1-2 trading-day publish lag on VIX EOD candles — the Jun-29 fetch genuinely had 0 new rows available to write at that exact fetch time; the manual Jul-2 re-run picked up 3 rows (Jun 26/29/30) once published. The `from_date`-not-honored behavior is wasteful (full-history refetch weekly) but not itself the cause of staleness and is tracked as a separate follow-on, not part of this fix. B004.3 added `_is_vix_window_stale(series, today)` in `scripts/strategies/ic/ic_entry_gates.py` (kept out of `src/backtest/ivr.py::compute_ivr` deliberately — `compute_ivr`'s existing test suite uses plain RangeIndex series with no dates, and `resolve_ivr` is the only layer holding the date-indexed series). Threshold: 7 calendar days (Animesh-approved — tolerates one missed/late Monday cron run plus observed publish lag without false-positiving on routine gaps). When stale, `resolve_ivr` logs a WARNING and leaves `ivr = None`, reusing the existing `ivr is None` hard-block path rather than adding new blocking logic. B004.5: reviewed via `general-purpose` agent substituting for `code-reviewer` (not exposed in this environment) against `REVIEW.md` — 2 ERROR findings (import ordering, docstring line length) fixed; no CRITICAL logic defects.

**B004.6:** Committed by Animesh on the live host (SHA `143335e`) — this Cowork sandbox had no disk space / `.venv` to run the project's pre-commit hooks itself.

**B004.7 recheck (2026-07-02):** Recomputed the trailing-252-day window as-of each date in the stale period (06-26, 06-29, 06-30, 07-01, 07-02) against the now-caught-up VIX series. Window low/high (9.15 / 27.89) is identical across all five dates — none of the missing days set a new 1-year high or low, so IVR is invariant to the staleness here. Confirms the logged decisions during the stale window were correct: `ic_leaps`/`ic_yearly` rejections (IVR=0.24 < 0.25 gate) and `ic_weekly` pass (IVR=0.24 ≥ 0.15 gate) all stand — no entry was wrongly blocked or wrongly allowed. BUG-004 closed.

**Once fixed, recalculate last week's IVR-gated entries:** any IC entry/rejection decision made between 2026-06-26 and whenever the cron gap is closed was evaluated against this same stale window. After the fix lands (both the recency check and the actual cron/data catch-up), re-run the IVR gate for that period and confirm no entry was wrongly blocked or wrongly allowed — do not assume last week's readings were fine just because this week's happened to be.

**Related:** `BUG-003`'s post-expiry gate and this bug are both in the same "gate evaluated the wrong reference window" family — worth a shared regression-test pattern (assert gate references a *current* or *most-recently-completed* reference point, never a frozen one) once both are fixed.

---

## BUG-005 — B002.2 cross-strategy pooling exclusion was decided but never implemented

| Field | Value |
|---|---|
| Severity | **HIGH** — blocks legitimate IC weekly entries with a fabricated delta figure; portfolio-delta gate is otherwise correctly signed post-BUG-002 |
| Status | ✅ Fixed (2026-07-02, SHA `b602066`; paper-phase CSP-exclusion follow-on SHA `5432639`) — status corrected 2026-08-13 during bugs/task.md archival cleanup: `task.md` B005.1-6 (plus the follow-on "paper-phase scope decision" block) were all completed and committed 2026-07-02, but this Status field was never flipped from 🔴 Open. |
| Discovered | 2026-07-02, dry-run of `paper_ic_entry.py --expiry-type weekly` |
| Location | `scripts/strategies/ic/paper_ic_entry.py` (line ~359-365); `scripts/strategies/ic/paper_ic_entry_v2.py` (line ~351-357) |

**Symptom:** Dry-run of V1 weekly entry: `ERROR: Portfolio delta check failed. Projected=-8.098 lots (outside [-0.05, 0.25]). Stop.` Debug trace shows the only IC-relevant position contributing is `paper_csp_nifty_v1`'s short put (`net_qty=-65`, ~+1 lot even under the crude approximation). Every other position dragging the aggregate to -8.098 belongs to `paper_nifty_futures`, `paper_nifty_proxy`, or `paper_nifty_spot` — overlay PP/collar/ditm-call legs from parallel proxy/hedge books, not the IC's own risk.

**Root cause:** BUG-002's root-cause investigation (B002 root cause section) explicitly flagged this pooling as an open scope question, and **B002.2 recorded a decision to resolve it**: *"scope `aggregate_delta` to IC-relevant positions only; exclude `paper_nifty_futures`/`paper_nifty_proxy`/`paper_nifty_spot` from the IC delta-neutral gate. Decided by Animesh 2026-07-02 (no code change this step)."* The "no code change this step" note implied implementation would land in a later B002.x task. It never did — B002.3 added `option_type` resolution, B002.4 added chain-delta sign/magnitude plus the fallback path, B002.5-7 were tests/review/commit for those two. None of them touch `store.get_strategy_names()` / the loop that builds `all_open_pos` in the two entry scripts. The decision was recorded in `bugs.md` and closed out as part of BUG-002 without the corresponding code ever being written — caught only because this dry run happened to exercise the weekly aggregate-delta path, which B002's own test suite (`tests/unit/risk/`) never did (those tests exercise `_position_delta`/`aggregate_delta` directly with hand-built position lists, not the caller-side strategy-name loop in the entry scripts).

```python
strategies_list = store.get_strategy_names()
all_open_pos = []
for strat in strategies_list:
    all_open_pos.extend([p for p in store.get_positions(strat) if p.net_qty != 0])
```

Both `paper_ic_entry.py` (line ~359) and `paper_ic_entry_v2.py` (line ~351) have the identical unfiltered loop.

**Suggested fix:** Exclude `STRATEGY_SPOT`/`STRATEGY_FUTURES`/`STRATEGY_PROXY` (`src/paper/constants.py`) from `strategies_list` before the loop, in both entry scripts. A shared helper in `ic_entry_gates.py` (even though the portfolio-delta gate itself isn't shared between V1/V2 per the module's documented divergence) avoids duplicating the exclusion set inline in two places.

**Related:** `BUG-002` (this is the un-implemented remainder of that bug's B002.2 decision, not a new independent defect).

---

## BUG-006 — Intraday chain snapshot writer only persists the yearly-expiry bucket, not actively-traded expiries

| Field | Value |
|---|---|
| Severity | **MEDIUM** — no functional impact on live gates, but destroys the ability to reconstruct/audit what a strategy actually saw at entry time |
| Status | ✅ Fixed (2026-07-03, SHA 7e0801c) |
| Discovered | 2026-07-03, trying to reconstruct the weekly IC's 10:29 AM strike-selection delta from historical data |
| Location | intraday chain snapshot pipeline (`scripts/pipeline/upstox_chain_intraday.py`) → `data/historical/option_chain/intraday/YYYY/MM/DD/upstox_HHMM.parquet` |

**Fix summary (B006.2–B006.6, SHA 7e0801c):** Root cause was not in the expiry-selection loop (`main()` already iterates all 3 configured expiries via `_PREFERENCE`/`get_expiry_candidates`) — it was in `ChainWriter.write_intraday_snapshot`/`write_eod_snapshot` (`src/backtest/chain_writer.py`): the output filename was keyed only by timestamp (`upstox_{HHMM}.parquet` / `upstox_{date}.parquet`), with no expiry/label component. Since all 3 expiries in a run share the same `snapshot_ts`, each write silently overwrote the previous one on the same path — `yearly` (last in `_PREFERENCE` order) always survived. Fix: added a `label` parameter to both writer methods, appended to the filename (`upstox_{HHMM}_{label}.parquet` / `upstox_{date}_{label}.parquet`); both `upstox_chain_intraday.py` and `upstox_chain_snapshot.py` now pass the per-expiry `label` through from their existing loop. `write_eod_snapshot` had the identical bug (same overwrite-per-date pattern) — fixed in the same change since both share the same root cause. Tests: new regression tests in `test_chain_writer.py` (distinct labels → distinct files, same label → still idempotent, for both writers) plus label-passthrough assertions in both script test files; 29/29 pass. Review: manual `REVIEW.md`-checklist substitute (no `code-reviewer` subagent in this environment) caught and fixed one G2 line-length violation in the new tests and one pre-existing ruff B007 unused-loop-variable finding in the touched file.

**Symptom:** Manually validated a weekly IC entry's live delta post-hoc (short_put 23500 PE showing `delta=0.0243`, well outside the config's `[0.06,0.14]` target band) and tried to check whether it was in-band at the actual 10:29 AM selection time using the persisted 5-min intraday snapshots. Every snapshot file for 2026-07-03 (`upstox_0900.parquet` through `upstox_1040.parquet`, including the 10:25/10:30 files bracketing the dry-run) contains **only** `expiry_date == 2027-06-29` (the yearly bucket) at sparse strikes (16500–31500, ~1500 pt spacing). The weekly 07-Jul-26 expiry — the one actually being traded — was never snapshotted.

**Root cause (not yet traced to exact line — needs graph/code confirmation before fix):** the intraday writer appears hardcoded or configured to snapshot a single expiry (consistent with its use for `gamma_daily_watch.py` / yearly gamma-buy monitoring) rather than the full set of expiries actively traded across strategies (weekly/monthly/leaps/yearly IC all read live chains but only yearly gets an intraday audit trail).

**Impact:** any post-hoc question of the form "was gate X's input actually valid at decision time, or did it decay before/after" cannot be answered for weekly/monthly/leaps IC entries — only for the yearly bucket. This already blocked a debugging session (this one) from confirming whether BUG-candidate delta drift was a selection-time defect or normal DTE-4 convexity after the fact.

**Suggested fix:** parameterize the intraday writer to snapshot every expiry bucket actually referenced by `CONFIGS`/`CONFIGS_V2` (weekly/monthly/leaps/yearly), not just the yearly gamma-watch expiry — or at minimum, snapshot whichever expiry each `paper_ic_entry*.py` cron is about to act on, keyed by run, so every entry decision has a reconstructable input snapshot.

**Related:** none yet — first entry in the "audit trail gap" family.

---

## BUG-007 — Portfolio-delta strike adjustment doesn't re-validate the shifted leg's own delta-target band, IVR, or structure economics

| Field | Value |
|---|---|
| Severity | **HIGH** — can silently accept a structure whose standalone risk/reward was never checked after portfolio-delta correction |
| Status | ⚪ Closed — moot (2026-07-03, SHA 66c4c71) |
| Discovered | 2026-07-03, tracing why weekly IC dry-run selected 24750 CE / 24950 CE for the call wing |
| Location | `scripts/strategies/ic/paper_ic_entry.py` lines ~437–530 (`paper_ic_entry_v2.py` lines ~417–467 has the same pattern) |

**Closed as moot (2026-07-03, no code change):** the `adj_call`/`adj_put` portfolio-delta strike-shift block this bug describes no longer exists in either entry script. It was removed by the same-day "IC entries judged in isolation" decision (`DECISIONS.md` 2026-07-03) — IC entries are now judged only on their own two short legs' delta, never adjusted against other strategies'/variants' open positions. Confirmed via `search_code` for `adj_call`/`adj_put`/"Portfolio delta gate adjusted" across the repo — zero matches. B007.2–B007.5 marked N/A in `task.md` per Animesh; no fix implemented since there is nothing left to fix.

**Symptom:** none directly logged as an error — found while explaining why the portfolio-delta gate printed `INFO: Portfolio delta gate adjusted short_call to 24750.0`. Traced the adjustment code path and confirmed: when `projected_total` (existing book delta + this IC's delta) falls outside `[-0.05, 0.25]`, the script shifts the offending short leg **one strike further OTM** and re-derives its wing hedge at `strike ± wing_width_points`. The only check applied to the shifted leg before accepting it is `_apply_liquidity_gate([adj_call])` (or `adj_put`) — there is no re-check that the new strike still satisfies `config.short_call_delta ± config.delta_range` (or the put equivalent), no re-check of DTE/IVR gates against the now-different structure, and no recomputation of max-profit/max-loss/POP/R:R for the adjusted four-leg structure before accepting it.

**Root cause:**

```python
if adj_call and _apply_liquidity_gate([adj_call]):
    new_ic_delta = Decimal(str(abs(short_put["delta"]))) - Decimal(str(abs(adj_call["delta"])))
    if Decimal("-0.05") <= (current_delta_lots + new_ic_delta) <= Decimal("0.25"):
        # Success — accepted with no further validation of adj_call itself
        short_call = adj_call
        ...
```

The adjustment loop optimizes for exactly one objective (portfolio delta back in band) and treats that as sufficient justification to accept the new strike. It does not re-run the same delta-target/IVR/DTE checks that gated the *original* strike selection — so a portfolio-delta-driven shift can land on a strike with a delta well outside the strategy's own designed band, or on a structure with materially worse R:R/POP than the one that was originally evaluated, and the script has no way to detect or flag that.

**Impact:** the dry-run this surfaced in produced a structure (23500PE/23300PE/24750CE/24950CE, DTE=4) that independent payoff analysis (Stockmock) showed as negative expected value against its own POP estimate (POP 92.2% vs 97.8% breakeven requirement). The delta-adjustment step is not the sole cause of that (DTE=4 and sub-floor IVR both predate it), but it is a second, independent point where the structure's quality could have been re-checked and wasn't.

**Suggested fix:** after any strike shift in this block, re-run the same delta-band check used for original selection against the new leg, and recompute basic structure economics (net credit, max loss, R:R) before accepting — if the shifted leg now fails those, treat it the same as "adjustment failed" (falls through to the existing `if not adjusted:` gate-violation/log-only path) rather than silently accepting a structure that was never fully vetted.

**Related:** `BUG-006` — without a persisted intraday snapshot at decision time, verifying whether this adjustment path fired at a *reasonable* delta vs. an already-degraded one is harder to audit after the fact.

---

## BUG-008 — Dry-run output bakes in point-in-time price/IVR with no re-validation if executed later

| Field | Value |
|---|---|
| Severity | **HIGH** — a paper trade can be recorded against stale price/IVR/delta data if the printed dry-run commands are executed even a short time after generation |
| Status | ✅ Fixed (2026-07-03, SHA d09d316) |
| Discovered | 2026-07-03, checking whether `record_paper_trade.py` re-validates anything when the dry-run's printed commands are pasted and run |
| Location | `scripts/strategies/ic/paper_ic_entry.py` (dry-run command generation) → `scripts/record/record_paper_trade.py` line ~645 |

**Fix summary (B008.2–B008.5):** Decision (Animesh, B008.2): option (a) — `record_paper_trade.py` always re-fetches a live LTP even when `--price` is explicit, and warns/blocks on drift. New pure function `_evaluate_price_drift(claimed_price, live_price, tolerance_pct=Decimal("0.10"))`: silent under 5% drift, WARNING at 5–10%, ERROR (hard block, `sys.exit(1)`) above 10% — `--force-entry` overrides the block (reuses the existing R3-override flag/pattern rather than adding a new one). Gated on `price_was_explicit and not args.close and not args.dry_run`: `--close` already fetches a live LTP itself a few lines earlier; dry-run previews never write to the DB, so BUG-008's actual failure mode (a frozen dry-run price being pasted and executed *later*) only matters at real `--no-dry-run` execution time — gating this way also avoids an unnecessary live network call on every preview. Both the live-fetch call and the `Decimal(str(...))` conversion of the response are wrapped in one `except Exception` — a fetch failure or a malformed/non-numeric LTP value both degrade to "WARNING: live LTP unavailable — proceed unverified" rather than crashing or blocking (this asymmetry — warn-not-block on *unverifiable*, but block on *verified-and-drifted* — was deliberate; a price already exists from the caller, this isn't the `--close` auto-price path where an unresolvable LTP has to hard-block). Tests: `tests/unit/paper/test_record_paper_trade.py` — 4 unit tests on `_evaluate_price_drift` (within-tolerance silent, elevated-warn, past-tolerance-block, zero-price no-op) + 5 `main()` integration tests (blocks on stale price, `--force-entry` overrides, proceeds within tolerance, skipped in dry-run, skipped on `--close`); added an autouse `_no_network_price_drift_check` fixture (default-mocks `UpstoxMarketClient` to return `{}`) so the ~6 pre-existing tests that pass an explicit `--price` with `--no-dry-run` and never cared about this feature don't accidentally attempt a real network call — per-test `@patch` decorators still take precedence within their own test body. 43/43 pass. Reviewed via `general-purpose` agent substituting for `code-reviewer` (not exposed in this Cowork environment) against `REVIEW.md` — no CRITICAL/ERROR findings; one WARNING (exception-catch spans two failure classes under one message, G5-compliant since it's commented and intentional, not blocking) deferred as a documented follow-up, not required before commit. B008.3's IVR/DTE/delta-gate re-run at execution time (beyond price) was explicitly out of scope for this fix per the B008.2 decision — `record_paper_trade.py` already runs its own independent IVR (R3) gate at execution time regardless (pre-existing), and DTE/portfolio-delta re-validation was removed from the entry-gate surface entirely by the unrelated 2026-07-03 "IC entries judged in isolation" decision (DECISIONS.md) — not re-added here.

**Note:** `tests/unit/scripts/test_record_paper_trade_r3.py::test_r3_no_block_on_buy` fails in this Cowork sandbox — confirmed via revert-to-HEAD comparison that it fails identically on the *unmodified* pre-fix code too. Root cause: no real network route to `api.upstox.com` in this sandbox (proxy 403) combined with that test never mocking the pre-existing, unrelated IVR-gate VIX-fallback fetch (`fetch_vix_latest()`) it exercises via `action=BUY`. Pre-existing/environmental, not a regression from this fix — same class of limitation documented at B004.6/B006.6.

**Symptom:** none logged — found by code inspection while assessing how safe it would be to copy-paste the dry-run's `[DRY-RUN] Commands to execute:` block and run it later. `record_paper_trade.py:645` only fetches live LTP **when `--price` is omitted** (`if args.price is None: ... fetch LTP`). The dry-run always emits an explicit `--price <value>` taken from the chain snapshot at the moment `paper_ic_entry.py` ran. If those commands are executed minutes or hours later — the realistic workflow, since a human is meant to review the dry-run before acting — the recorded trade uses the original snapshot's price, not the current market, and none of the entry gates (IVR floor, DTE window, delta band, portfolio delta) are re-evaluated at execution time; those only run inside `paper_ic_entry.py`, not `record_paper_trade.py`.

**Root cause:** the gate-check/strike-selection step and the trade-recording step are two separate scripts connected only by a printed shell command containing frozen values — there is no re-validation boundary at execution time, and no timestamp/staleness check on the embedded price before it's written to `paper_trades`.

**Impact:** directly relevant to this session — DTE and IVR were already found to be outside their target windows at generation time (log-only, so the dry-run still printed commands); if those commands are executed later, the DB will record a paper trade whose entry price no longer reflects the market, with no warning surfaced anywhere in the pipeline.

**Suggested fix:** either (a) have `record_paper_trade.py` re-fetch live LTP and compare against the passed `--price` within some tolerance, warning or blocking on material drift, or (b) have the dry-run commands omit `--price` entirely and let `record_paper_trade.py`'s existing live-fetch path (already there for the no-price case) be the only path — accepting that the reviewed dry-run numbers are illustrative, not literal execution instructions. Either way, re-running the IVR/DTE/delta gates at actual execution time (not just at dry-run generation time) closes the real gap.

**Related:** `BUG-007` (same family — decisions made at one point in the pipeline are not re-checked at the point where they actually take effect).

---

## BUG-009 — `paper_ic_snapshot.py` can never resolve expiry from `instrument_key`, silently killing the daily IC EOD audit

| Field | Value |
|---|---|
| Severity | **HIGH** — daily snapshot report for both monthly IC variants is a permanent no-op; no P&L/audit visibility despite open positions |
| Status | ✅ Fixed |
| Discovered | 2026-07-03, investigating why no snapshot report arrived for `paper_ic_nifty_v2_monthly` after today's entry |
| Location | `scripts/strategies/ic/paper_ic_snapshot.py::process_variant` (lines ~115–134), regex defined line 44 |

**Symptom:** `logs/ic_snapshot.log`, 2026-07-03 15:45:05 — cron ran on schedule (`45 15 * * 1-5`), both variants had open positions, but output was:
```
ic_snapshot.no_expiry_found strategy=paper_ic_nifty_v1_monthly
ic_snapshot.no_expiry_found strategy=paper_ic_nifty_v2_monthly

📋 IC EOD Audit — monthly (paper_ic_nifty_v1_monthly)
Error: Expiry date could not be parsed from positions.

📋 IC EOD Audit — monthly (paper_ic_nifty_v2_monthly)
Error: Expiry date could not be parsed from positions.
```
No real audit ever reaches the user — just this error stub, and it's apparently not escalated anywhere visible (non-fatal notifier contract per `src/notifications/CLAUDE.md`), so the failure goes unnoticed until asked about directly.

**Root cause:**
```python
_EXPIRY_RE_ROBUST = re.compile(r"NIFTY(\d{2}[A-Za-z]{3}\d{4})", re.IGNORECASE)
...
m = _EXPIRY_RE_ROBUST.search(p.instrument_key)
```
This expects a trading-symbol string like `NIFTY28JUL2026...` embedded in `p.instrument_key`. Actual `instrument_key` values recorded in `paper_trades` (confirmed via query) are Upstox's numeric form — `NSE_FO|63930`, `NSE_FO|63987`, etc. — with no date substring anywhere. The regex can never match, `expiry` stays `None` for every leg of every variant, and the function always falls into the `no_expiry_found` branch regardless of whether positions are genuinely open and healthy.

**Impact:** confirmed today for `paper_ic_nifty_v2_monthly` (4 legs entered same day, all `OPEN` in `paper_trades`) and `paper_ic_nifty_v1_monthly` (also has open legs). This is not a one-off — the bug is structural (bad assumption baked into the regex), so it has silently broken the daily EOD audit for both variants since whichever commit last changed `instrument_key` to the numeric format, or since this script was first written against the wrong assumption. `git log --oneline` on this file not yet checked to date the regression precisely.

**Suggested fix:** don't derive expiry from a string pattern that was never present in the stored key. Either (a) reverse-lookup the numeric `instrument_key` against the offline instrument master (`src/instruments/`) to get the real trading symbol/expiry, or (b) store expiry directly on the position/trade row at entry time (`paper_trades` or `PaperPosition`) so downstream snapshot code doesn't need to reconstruct it at all. Option (b) avoids adding an instrument-master lookup dependency to a script whose only job is reporting.

**Fix (2026-07-03, option (a), per Animesh B009.2 decision):** replaced `_EXPIRY_RE_ROBUST` regex block in `process_variant` with `InstrumentLookup.get_by_key(p.instrument_key)` (the `lookup` param was already threaded into the function but unused) → `parse_expiry(inst.get("expiry"))` → `date.fromisoformat(...)`. Same lazy read-time resolution pattern as BUG-002's `PaperPosition.option_type` — no schema change, no migration, fixes historical rows immediately. Unresolvable/legacy `instrument_key` (lookup returns `None`, or `parse_expiry` returns `None`) falls back to the existing `no_expiry_found` branch unchanged — same safe-but-informative behavior as before, just no longer the *only* reachable path. `_EXPIRY_RE_ROBUST` constant and its now-dead code removed; `re` import retained (still used elsewhere in the file for signal-note parsing). 2 new dedicated tests on `process_variant` (numeric-key happy path resolves DTE correctly; unresolvable-key edge case still falls back to `no_expiry_found` without crashing) + existing suite's `mock_lookup` autouse fixture updated so `get_by_key` derives the same expiry the old regex used to, keeping all prior assertions valid without touching every test's fixture data. **Tests not executed this session** — sandbox `.local` disk quota exhausted (`pip install pytest` → `No space left on device`), same limitation class as B004.6/B006.6/B010.4–7; both touched files verified via `py_compile` only. Logic traced manually against `InstrumentLookup.get_by_key`/`parse_expiry` signatures confirmed via the codebase graph. Live-host test run caught one gap in the happy-path test (broker mock wasn't awaitable and `parse_upstox_option_chain` wasn't patched, so `process_variant` hit the chain-fetch error path before the DTE assertion) — fixed by adding `AsyncMock` on `broker.get_option_chain` and patching `parse_upstox_option_chain`, matching the pattern already used by the rest of the suite. All tests green on live host. Committed SHA `abafeaf`.

**Related:** none yet — first bug traced to `paper_ic_snapshot.py` itself; distinct from `BUG-002`'s put/call substring-matching bug in `_position_delta`, though both stem from the same class of mistake (assuming a trading-symbol string is present where only a numeric `instrument_key` actually is).

---

## BUG-010 — Six incompatible log output formats coexist in `logs/`, no enforced logging entrypoint

| Field | Value |
|---|---|
| Severity | **HIGH** — not a financial-logic defect, but actively degrades debuggability project-wide; directly slowed down triage of `BUG-009` (had to eyeball-parse mixed formats instead of grepping a single structured shape). Bumped from MEDIUM to HIGH and moved to the front of this registry — pick up first. |
| Status | ✅ Fixed — SHA range 5fa5e33..5d5c8ef (see `docs/bugs/task.md` B010.2–B010.9 for per-item SHAs) |
| Discovered | 2026-07-03, surveying every file in `logs/` after noticing `logs/intraday.log` mixed formats |
| Location | Project-wide — no single file, see breakdown below |

**Symptom:** every log file in `logs/` was sampled (`head`/`tail`, 19 files). At least six distinct line formats are in circulation, often interleaved within the same file:

1. **Structlog pipeline (correct, the intended standard)** — `src/utils/logging.py::setup_logging()` wired correctly. Format: `YYYY-MM-DD HH:MM:SS [LEVEL] [pkg] [sub] [module] event key=value`. Seen in `chain_intraday.log`, `chain_snapshot.log`, `eod_summary.log`, `monitor_daemon.log`, `morning_nav.log`, `pre_market_brief.log`, most of `intraday.log`/`paper_snapshot.log`/`vix_refresh.log`. This is the good case — every other format below is a deviation from it.
2. **Bare stdlib `logging.getLogger(__name__)`, bypassing structlog entirely** — `src/client/upstox_market.py:32`, three call sites (~131/165/205), `%s`-style. Because `setup_logging()` sets the stdlib root handler to `format="%(message)s"`, these render as bare `upstox.api_call endpoint=... status_code=... latency_ms=...` with no timestamp, no level, no module tag. Appears inside `chain_intraday.log`, `chain_snapshot.log`, `intraday.log`, `paper_snapshot.log`, `pre_market_brief.log` — scattered wherever `upstox_market.py` is on the call path.
3. **Raw `print(f"ERROR: ...")` / `print(f"INFO: ...")` with no timestamp** — `scripts/strategies/ic/ic_entry_gates.py`, `paper_ic_entry.py`, `paper_ic_entry_v2.py`. Produces `ERROR: post_expiry_gate: ...`, `INFO: selected expiry = ...` with a hand-typed prefix instead of a real level field. Fills `ic_leaps.log`, `ic_monthly.log`, `ic_v2_monthly.log`, `ic_weekly.log`, `ic_yearly.log` almost entirely.
4. **`structlog.get_logger(...)` called without `setup_logging()` ever being invoked** — all five files under `scripts/strategies/ic/` construct a module-level `logger = structlog.get_logger(...)` but none call `setup_logging()`, so structlog falls back to its own unconfigured default renderer: `2026-07-03 10:54:36 [warning  ]  gate.ivr_violation_logged  gate=0.25 ivr=0.149...` — lowercase padded level, no `[module]` bracket, different timestamp/spacing than format 1. Mixed into `ic_monthly.log`, `ic_v2_monthly.log`, `ic_snapshot.log` alongside format 3.
5. **Hand-built human-readable report strings (emoji, tables, no structure at all)** — `paper_ic_snapshot.py` (`📋 IC EOD Audit — ...`), `paper_ic_monthly_comparison.py` (`📊 IC Monthly Comparison — ...`), and a Rich-style `───` table block at the tail of `paper_snapshot.log`. These are Telegram-notification bodies also being dumped straight into the log file as-is — not a log line, a rendered report.
6. **Bespoke bracket-timestamp format, distinct from format 1** — `scripts/portfolio/daily_snapshot.py` writes `[2026-06-15 15:45:01] Daily snapshot for 2026-06-15` followed by indented plain-text detail lines (`  run_id=...`), which is neither the structlog pipeline nor a `print(f"LEVEL: ...")` — a third, separate hand-rolled convention. Fills `logs/snapshot.log`.

One additional file, `logs/apiconnect.log`, is the Nuvama APIConnect SDK's own internal logger output (`2026-06-15 06:14:48,167 [INFO] APIConnect.APIConnect: ...`, comma-millisecond timestamps) — this is third-party and out of project control; it should be documented as an accepted exception, not "fixed."

**Root cause:** `setup_logging()` exists and is well-built (`src/utils/logging.py`), but nothing in the codebase enforces that every entrypoint script calls it before logging, and nothing prevents `print()` or raw stdlib `logging.getLogger()` from being used instead. Three independent failure modes compound: (a) scripts that never call `setup_logging()` at all, (b) code that reaches for stdlib `logging` directly instead of `structlog.stdlib.get_logger`, and (c) human-facing report/notification text being treated as if it were a log line. `REVIEW.md` G7 mandates `%`-style formatting for "logger calls," which is a stdlib-logging convention — it doesn't address structlog's keyword-argument idiom at all, so the review checklist itself has no rule that would have caught formats 2–6.

**Impact:** concretely slowed down the `BUG-009` investigation — errors and warnings are not uniformly greppable (`grep ERROR` misses format-4's `[warning  ]` lines and format-1's `[ERROR]` lines have a different bracket shape; format 3's `"ERROR:"` prefix has no real level field to filter on). Any future alerting/monitoring built on top of these logs (e.g. "page me on any ERROR") cannot rely on a single parse rule.

**Suggested fix:** see `LOGGING.md` (project root — new file, added alongside this bug entry) for the standard going forward. Concretely: (1) every entrypoint script (anything with `if __name__ == "__main__"`) must call `setup_logging()` before any other logging happens — add this as a `code-reviewer` checklist item; (2) migrate `src/client/upstox_market.py` to `structlog.stdlib.get_logger(__name__)` (3 call sites); (3) migrate the five `scripts/strategies/ic/*.py` files' raw `print()` calls to `logger.info/warning/error(...)` with keyword args, and add the missing `setup_logging()` call; (4) migrate `scripts/portfolio/daily_snapshot.py` off its bespoke `[timestamp] message` format onto the shared pipeline; (5) keep emoji/table report strings, but log them as a single structured event (e.g. `logger.info("report.sent", channel="telegram", strategy=..., body=report_text)`) rather than a bare `print()` with no level/timestamp; (6) document `apiconnect.log` as an intentional third-party exception rather than attempting to reformat SDK-internal logging.

**Related:** discovered while triaging `BUG-009`; `upstox_market.py`'s stdlib-logging bypass was separately flagged before this survey formalized it as one item in the larger project-wide pattern.

**Closing summary (2026-07-03):** all six format deviations addressed per the suggested-fix list (B010.2–B010.6); `apiconnect.log` documented as an accepted third-party exception (B010.6, verified already satisfied by the original `LOGGING.md` commit); happy-path + degrade-gracefully tests added (B010.7); final review pass (B010.8) against the cumulative diff (`git diff 96c80e7..5d5c8ef`) found no CRITICAL/ERROR — see `docs/bugs/task.md` B010.8 for the checklist covered (G2/G7/G8, unused imports, no information loss on removed `print()` calls). Follow-up recommended, not yet actioned: add "every entrypoint script calls `setup_logging()`" as a permanent `code-reviewer` checklist item (per the original suggested-fix item 1) so this doesn't regress.

---

## BUG-011 — `test_build_notifier_returns_none_when_token_missing` fails on live host (suspected cross-test env leakage)

| Field | Value |
|---|---|
| Severity | **LOW** — test-suite reliability only, no production code path affected; `build_notifier()` itself is not known-broken |
| Status | ✅ **Fixed** (2026-08-06) — `build_notifier()` no longer goes through the `_DynamicSettings` cache at all |
| Discovered | 2026-07-03, live-host `pytest` run surfaced by Animesh after BUG-010 B010.4 session. Reopened 2026-07-26 with a fresh full-suite repro. |
| Location | `tests/unit/test_notifications.py::test_build_notifier_returns_none_when_token_missing` + 3 sibling tests; suspected root cause in `src/config.py::_DynamicSettings` or a test elsewhere that mutates `os.environ` outside `monkeypatch` |

**Symptom:** `assert <src.notifications.telegram.TelegramNotifier object at 0x111d06c60> is None` — `build_notifier()` returned a real notifier instead of `None` even though the test calls `monkeypatch.delenv("TELEGRAM_BOT_TOKEN")` / `monkeypatch.delenv("TELEGRAM_CHAT_ID")` immediately beforehand.

**Not yet root-caused** — this entry logs a confirmed repro (real pytest failure, output pasted by Animesh), not a confirmed root cause; investigation is the first checklist step. Not caused by the B010.4 diff — that session touched only `scripts/portfolio/daily_snapshot.py` and a new test file, never `src/notifications/`, `src/config.py`, or `tests/unit/test_notifications.py`.

**Leading hypothesis:** `build_notifier()` reads through `settings.telegram_bot_token`/`telegram_chat_id`, where `settings` is the `_DynamicSettings` singleton (`src/config.py`) that rebuilds `Settings` only when `hash(frozenset(os.environ.items()))` changes since the last access. If `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` are real values already present in the live host's process environment (exported in the shell, not `.env`-sourced) — or some other test in the suite writes directly into `os.environ` rather than through `monkeypatch` (whose reversion `monkeypatch.delenv` in *this* test can't undo if it happened in a different test's un-reverted mutation) — this test only passes when run in isolation, and fails as part of the full suite or a shell session that already exports the tokens. Unconfirmed until reproduced.

**Suggested fix (pending investigation):** (a) confirm via `pytest tests/unit/test_notifications.py::test_build_notifier_returns_none_when_token_missing -q` run alone vs. full-suite run — isolates whether this is cross-test leakage vs. a `_DynamicSettings` caching bug; (b) `echo $TELEGRAM_BOT_TOKEN $TELEGRAM_CHAT_ID` in the host shell running pytest to rule out real OS-level env vars; (c) if cross-test leakage is confirmed, `grep -rn "os.environ\[" tests/` for any raw (non-`monkeypatch`) mutation and convert it to `monkeypatch.setenv`.

**Original resolution (2026-07-03, investigation-only, no code change):** closed as fixed/moot, citing `fe69612` (2026-05-30) as a pre-existing fix. That closure did not actually reproduce the failure — it reasoned from code inspection only. Per its own reopen clause, logging fresh evidence below.

**2026-07-26 investigation (Animesh's live-host paste — real, not hypothetical):**

- `echo $TELEGRAM_BOT_TOKEN $TELEGRAM_CHAT_ID` on the live host → both empty. Rules out real shell-exported env vars (the original leading hypothesis).
- Running the single failing test in isolation → passes. Running it as part of `tests/unit/` + a handful of related files with `-n auto` → passes. Running the **full** `tests/unit/` suite → fails (all 4 `None`-expecting `build_notifier` tests, never the 2 that set real overriding values).
- Investigated `_DynamicSettings._get_settings()`'s cache-validity check, which compares `hash(frozenset(os.environ.items()))` across accesses. This is unsound on its own terms — hash equality doesn't imply content equality, so two different `os.environ` states can coincidentally collide — and was fixed regardless (`src/config.py`, compares the actual environ dict now, not its hash; see `DECISIONS.md` 2026-07-26). **This fix did not resolve the failure** — reproduced again in a sandbox environment with the fix applied, confirming hash-collision was not the actual root cause of BUG-011's symptom, even though the fix is independently correct and worth keeping.
- Sandbox reproduction is itself flaky under `-n auto` (fails on some runs, passes on others with no code change between runs) — consistent with a genuine cross-test interaction whose visibility depends on pytest-xdist's per-run worker/test assignment, which is not deterministic across runs.
- Ruled out: two candidate leak vectors tested directly (an unguarded `load_dotenv()` call inside `paper_snapshot.py::_run` with no `monkeypatch` cleanup; the same pattern in `src/auth/{dhan,nuvama}_{login,verify}.py`) — both inject real `.env` values into a worker's `os.environ` but `monkeypatch.delenv` still correctly strips them for the duration of any single test that calls it, in both isolated repro attempts.
- **Not yet root-caused.** Since `pytest-xdist` workers are separate processes with independent `os.environ`, the leak (whatever it is) must originate from a *different test in the same worker* via some path that survives past a `monkeypatch.delenv` call within `test_notifications.py`'s own test bodies — which should be structurally impossible given `monkeypatch`'s per-test teardown semantics, unless something re-populates `os.environ` (or bypasses the settings layer entirely) between the `delenv` line and the `build_notifier()` call. Next diagnostic step: temporarically add `print(f"TELEGRAM_BOT_TOKEN={os.environ.get('TELEGRAM_BOT_TOKEN')!r}", file=sys.stderr)` immediately before the `assert build_notifier() is None` line in the failing test, run with `-s` on the live host during an actual failing full-suite run, and capture the printed value — this pins down whether the leak is in `os.environ` itself (real cross-test contamination) or somewhere in the `Settings`/pydantic layer despite a clean `os.environ` (a different, more surprising bug).

**2026-08-06 fix (Claude, requested by Animesh after a fresh `make test` repro pasted the same 4 failures):** never fully root-caused per the investigation above — the exact mechanism by which a stale/leaked value reached `settings.telegram_bot_token` past a `monkeypatch.delenv` was never pinned down even with the hash→dict fix applied. Rather than continue chasing a flaky-only-under-`-n auto` repro, closed the entire vector: `build_notifier()` (`src/notifications/telegram.py`) no longer reads through the `settings` singleton (`_DynamicSettings`) at all — it now constructs a fresh, uncached `Settings(_env_file=None)` on every call. This makes the function's return value depend only on the live `os.environ` at call time, with zero dependency on any cache-invalidation logic, regardless of what the actual staleness trigger was. Verified: `tests/unit/test_notifications.py` + `tests/unit/test_config.py` green (34/34); full `tests/unit/` suite green except one pre-existing, unrelated network-dependent test (`test_record_paper_trade_r3.py::test_r3_no_block_on_buy`, fails in any sandboxed/offline environment lacking real Upstox connectivity — not caused by this change); a synthetic repro that force-leaks `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` directly into `os.environ` *and* pre-warms the `settings` singleton cache with the leaked values before a `monkeypatch.delenv`-guarded test runs — the exact shape of leak this bug describes — now passes consistently across repeated runs (previously this shape of repro was exactly what stayed unconfirmed). `settings` singleton usage elsewhere in the codebase is untouched; this is scoped to the one call site whose correctness is safety-critical (a false positive here sends a real Telegram message).

**Status: fixed.** Root cause of the underlying cache-staleness mechanism remains formally unconfirmed (see 2026-07-26 notes above) — this fix closes the bug by eliminating the vulnerable code path rather than by identifying the exact trigger. If `_DynamicSettings` staleness resurfaces at a different call site in the future, revisit with the diagnostic step noted above (temporary stderr print of `os.environ.get(...)` immediately before the assertion, run with `-s` during a live failing full-suite run).

---

## BUG-012 — `paper_ic_snapshot.py` instantiated `IronCondorV2` with positional args, silently mis-binding config to the broker object

| Field | Value |
|---|---|
| Severity | **HIGH** — the V2 monthly IC's EOD signal evaluation had been silently no-op'ing (caught exception, degraded report) since `IronCondorV2` was first wired into the snapshot cron; no crash, no alert distinct from a normal chain hiccup |
| Status | ✅ Fixed — see `DECISIONS.md` 2026-07-06 entry for full root-cause writeup and commit |
| Discovered | 2026-07-06, user (Animesh) reported no IC snapshot for the day; traced via `logs/ic_snapshot.log` |
| Location | `scripts/strategies/ic/paper_ic_snapshot.py::process_variant` (constructor call site); root cause is signature-order divergence between `src/strategy/ic_nifty_v1.py::IronCondorV1.__init__` and `src/strategy/ic_nifty_v2.py::IronCondorV2.__init__` |

**Symptom:** `ic_snapshot.log` showed, for `paper_ic_nifty_v2_monthly` only: `ic_snapshot.check_signals_failed strategy=paper_ic_nifty_v2_monthly error='UpstoxLiveClient' object has no attribute 'expiry_type'`, surfaced to Telegram as "Error: Signal evaluation failed" instead of a real snapshot. `paper_ic_nifty_v1_monthly` produced a snapshot but with `LTP=N/A`/`δ=0.00` on every leg — a separate, already-tracked defect (see TODOS.md "Fix BOD resolution in CC / PP / Collar / IC V1 / IC V2 leg finders").

**Root cause:** `process_variant` calls `strategy_cls(broker, store, notifier, config)` positionally to generically instantiate either IC strategy class. `IronCondorV1.__init__(self, broker=None, store=None, notifier=None, config=None)` matches this order. `IronCondorV2.__init__(self, config=None, broker=None, store=None, notifier=None)` does not — so for every V2 invocation, `self._config` was bound to the live `UpstoxLiveClient` broker instance, `self._broker` to `store`, etc. This stayed invisible until `check_signals` accessed `self._config.expiry_type` deep inside `ProfitLockEngine().evaluate(...)`, which raised, was caught by `process_variant`'s own fail-safe `try/except Exception`, and downgraded to a one-line error report — no traceback reached logs at ERROR-with-stack level, no distinct alert from a routine chain-fetch failure.

**Fix:** `scripts/strategies/ic/paper_ic_snapshot.py:172` — call `strategy_cls(broker=broker, store=store, notifier=notifier, config=config)` by keyword, which binds correctly regardless of either class's declared parameter order. Confirmed via `@code-reviewer` that the only other instantiation site (`scripts/daemon/monitor_daemon.py`) already used keyword args for both classes — no other call site carried this risk.

**Test:** `tests/unit/strategies/ic/test_paper_ic_snapshot.py::test_process_variant_binds_constructor_args_by_keyword` — a fake `_ReversedSignatureStrategy` class with V2's real `__init__` order is passed as `strategy_cls`; `check_signals` asserts `self.config.strategy_name` matches the real config, which would fail under the pre-fix positional call (self.config would resolve to the mocked broker instead).

**Related:** the two-class polymorphic-strategy pattern in `process_variant` has no protocol/ABC enforcing a shared `__init__` signature — worth a follow-up to standardize both classes on the same constructor param order (or route construction through a small factory keyed by strategy version) so this class of bug can't recur when a V3 is added.

**Follow-up #2 (same day, 2026-07-06):** the same numeric-key/regex-only expiry-parsing defect existed independently in `scripts/strategies/ic/paper_ic_monthly_comparison.py::build_stats`, but with a worse symptom there — its `_EXPIRY_RE`-only expiry parse also feeds `build_comparison_report`'s "is this variant open?" check (`v1_open = v1.dte is not None`), so a genuinely open position with an unresolvable numeric key got mislabeled **"No open position"** in the V1-vs-V2 comparison Telegram report, hiding real entry credit/P&L/delta/signal data entirely (worse than `paper_ic_snapshot.py`'s symptom, which at least showed `N/A` rather than a false negative on position existence). Fix: `build_stats` gained an optional `lookup: InstrumentLookup | None` param with the same BOD-lookup fallback as `paper_ic_snapshot.py::process_variant`; `_run` now loads it once via a new `--bod-path` CLI arg (fail-safe — falls back to `lookup=None`, degrading to `dte=None` rather than crashing, on a missing/corrupt BOD file). A new `ICMonthlyStats.has_open_position: bool` field, set explicitly and only in `build_stats`'s two construction sites, decouples "position exists" from "DTE could be computed" — `build_comparison_report` now reads `has_open_position` instead of inferring open/closed from `dte`. `@code-reviewer`: no CRITICAL/ERROR findings; confirmed the two states are structurally decoupled (every return path in `build_stats` sets both fields together, so a "stale dte with no position" state is unreachable). 3 new tests: BOD-fallback expiry resolution for a numeric key, no-position still reports `has_open_position=False`, and a report-level test proving a genuinely-open-but-unresolvable-DTE position now renders `N/A` rather than the misleading "No open position".

**Follow-up (same day, 2026-07-06):** fixing the constructor bug above surfaced that the resulting reports were "successful" but hollow — every leg showed `LTP=N/A`/`δ=0.00`, and logs were full of `ic_nifty_v1.strike_parse_failed` / `ic_nifty_v2.strike_parse_failed`. Root cause: `IronCondorV1._find_leg` / `IronCondorV2._find_leg` parse strike+CE/PE from `instrument_key` via `_STRIKE_RE = re.compile(r"NIFTY(\d+)(PE|CE)")`, but real Upstox keys are numeric-only (`NSE_FO|63896`) and never match — the exact defect already fixed for CSP in `CSPNiftyV1._find_put_leg` (BUG-009/SM-1) but never ported to the IC strategies, despite being the item already tracked in TODOS.md ("Fix BOD resolution in CC / PP / Collar / IC V1 / IC V2 leg finders"). Fix: added `_find_leg_via_bod` to both `ic_nifty_v1.py` and `ic_nifty_v2.py`, mirroring `CSPNiftyV1._find_put_leg`'s BOD-lookup fallback (`InstrumentLookup.from_file(DEFAULT_BOD_PATH).get_by_key(instrument_key)` → `strike_price`/`instrument_type`), extended to handle both CE and PE (CSP is PE-only). Also fixed `IronCondorV2._position_strike` (feeds Zone 2 profit-lock strike resolution — a real signal-logic path, not just the report) with the same fallback inline. `@code-reviewer`: no CRITICAL/ERROR findings; confirmed both CE/PE handled, Decimal preserved throughout, `_position_strike`'s callers (Zone 2 profit-lock, roll wing strike lookups) verified as the previously-blind call sites. **Not fixed, flagged as follow-up**: `cc_overlay_v1.py`, `collar_overlay_v1.py`, `pp_overlay_v1.py`, and `nifty_track_comparison_v1.py` share the same `_STRIKE_RE`-only pattern and are still blind to numeric keys — this is the CC/PP/Collar portion of the original TODOS.md item, not yet addressed. Tests: `tests/unit/strategy/test_ic_nifty_v1.py` (4 new tests) and `tests/unit/strategy/test_ic_nifty_v2_signals.py` (4 new tests), all patching `src.instruments.lookup.InstrumentLookup.from_file` — confirmed to fail pre-fix and pass post-fix for the right reason.

---

## BUG-013 — `IronCondorV1` never sends a Telegram close confirmation; `IronCondorV2` only sends one for the rare Zone-2 roll, not its own CLOSE_FULL

| Field | Value |
|---|---|
| Severity | **MEDIUM** — no capital/P&L impact (the close itself executes and persists correctly), but every full IC close is silent on the operator's primary monitoring channel, unlike every other auto-execute strategy |
| Status | ✅ Fixed (2026-07-20) |
| Discovered | 2026-07-20, user asked why a Telegram message was received for a `paper_ic_nifty_v1_monthly` `PROFIT_TARGET` auto-close — traced the actual execution path (`StrategyMonitor._route_event` → `IronCondorV1.apply_action` → `close_ic_legs()`) and found no notifier call anywhere in it |
| Location | `src/strategy/ic_nifty_v1.py::apply_action`; `src/strategy/ic_nifty_v2.py::apply_action` (`CLOSE_FULL`/`CLOSE_CALL_SPREAD`/`CLOSE_PUT_SPREAD` branch only — `PROFIT_LOCK_ZONE2` was already correct) |

**Symptom:** none logged anywhere — that's the bug. `IronCondorV1.check_signals()` correctly fires `PROFIT_TARGET`/`LOSS_STOP`/`TIME_STOP`/`DELTA_STOP`, `StrategyMonitor` correctly auto-dispatches to `apply_action()`, `close_ic_legs()` correctly persists the closing `PaperTrade` rows — every part of the close executes and is logged (`ic_nifty_v1.apply_action`, `ic_close_executor.legs_closed`, `strategy_monitor.auto_execute_dispatched`), but nothing ever reaches Telegram. Confirmed by checking every strategy's notifier usage: `CSPNiftyV1`, `CCOverlayV1`, `CollarOverlayV1`, and `PPOverlayV1` all call `TelegramGateway.send_notification()` on close via a `_send_notification`/inline `hasattr(self._notifier, "send_notification")` pattern. `IronCondorV1` accepts a `notifier: TelegramGateway | None` constructor argument, stores it as `self._notifier`, and never references it again anywhere in the file — a dead parameter. `IronCondorV2` does call `self._send_profit_lock_notification()`, but only from the `PROFIT_LOCK_ZONE2` branch (a rare partial roll); its `CLOSE_FULL`/`CLOSE_CALL_SPREAD`/`CLOSE_PUT_SPREAD` branch — the action actually triggered by the common `PROFIT_TARGET`/`FORCED_CLOSE` signals — calls `close_ic_legs()` directly with no notification step, same gap as V1.

The `StrategyMonitor` module docstring (`src/strategy/monitor.py` lines 7-8) documents `"ACTION + strategy.auto_execute + payload["auto_execute"] → apply_action() called directly; send_notification() on completion"` — this describes intended behavior that was never actually implemented for either IC strategy; the docstring itself is stale/aspirational relative to the code, not evidence of a call site that exists.

**Root cause:** `IronCondorV1`/`IronCondorV2` were built with the `close_ic_legs()` persistence path (2026-07-15 fix, TODOS.md) as their primary concern — getting the DB write to happen at all was the priority bug at the time — and Telegram confirmation was never added as a follow-up once persistence was fixed, unlike the overlay/CSP strategies which had notification wired in from their original implementation.

**Impact:** operationally confusing (this is literally how it was discovered — a real close happened with no expected Telegram trail, and a message that *was* received turned out to come from a separate, unrelated cron — `scripts/strategies/ic/paper_ic_snapshot.py`'s EOD audit — not from the close itself), but no capital or data-integrity impact: the close was correctly persisted and would show up in the next EOD/portfolio snapshot regardless of notification. Risk is purely "operator doesn't find out a position closed until the next scheduled report runs," which for TIME_STOP/DTE-driven closes near expiry could be a multi-hour gap.

**Fix (2026-07-20):** added `IronCondorV1._send_close_notification()` (mirrors `CSPNiftyV1._send_notification` pattern) and wired it into `apply_action()`'s `CLOSE_FULL`/`CLOSE_CALL_SPREAD`/`CLOSE_PUT_SPREAD` auto-execute branch, called with the `PaperTrade` rows actually returned by `close_ic_legs()` (empty list → no-op, since `close_ic_legs()` already logs `ic_close_executor.nothing_to_close` for that case). Added the equivalent `IronCondorV2._send_close_notification()` for the same three action types in its `apply_action()` — the existing `_send_profit_lock_notification()` for `PROFIT_LOCK_ZONE2` is untouched, this is a second, separate notification for the full/spread-close path it never had. Both non-fatal (logged WARNING/ERROR on send failure, never raises) matching the project's notifier contract. `ROLL_WING`'s own close side remains unnotified — same known scope boundary as `IC-CLOSE-2` (TODOS.md), the replacement leg isn't persisted yet either, so a roll-close notification would be misleading before that's built.

**Related:** the 2026-07-15 `close_ic_legs()` persistence fix (TODOS.md) this notification gap sat behind; `DECISIONS.md` 2026-07-20 (same session, the `lookup=` wiring fix and silent-failure-logging pass that led to discovering this).

---

## BUG-014 — `get_positions()` resolves `option_type` unconditionally, generating permanent unactionable warnings for closed legs on delisted contracts

| Field | Value |
|---|---|
| Severity | **MEDIUM** — pure log noise, no capital or data-integrity impact; but the noise is permanent and will recur on every snapshot run forever for affected legs |
| Status | ✅ Fixed (2026-07-20) |
| Discovered | 2026-07-20, investigating repeated `option_type_resolution_failed` warnings in `logs/paper_snapshot.log` (`trace_id=f5985444`) |
| Location | `src/paper/store.py::PaperStore.get_positions` (line ~611, `_resolve_option_type` call site) |

**Symptom:** `option_type_resolution_failed instrument_key=NSE_FO|71474 reason="instrument_key not found in BOD JSON"` and the same for `NSE_FO|44498`, logged on every EOD snapshot run despite both legs having `net_qty == 0` (fully closed, per `paper_trades`: `71474` closed 2026-06-08, `44498` settled ITM 2026-07-17).

**Root cause:** `get_positions()` builds one `PaperPosition` per `leg_role` a strategy has ever traded, grouped only by `leg_role` with no filter on the resulting `net_qty`. It always calls `self._resolve_option_type(cycle_instrument_key)` at construction time (added in `96398b4`, 2026-07-02, B002.3) — before any caller has a chance to apply the `net_qty != 0` filtering convention used everywhere downstream (`paper_3track_snapshot.py:378,567,1200`; the `all_open_pos` loop referenced in BUG-005). `96398b4`'s own 9-test suite covers BOD-load-failure and unresolved-key paths but never a `net_qty == 0` leg. Since Upstox's BOD file drops delisted/expired contracts once settled, any closed leg's `cycle_instrument_key` will *never* resolve again — the warning is not staleness, it's permanent.

**Impact:** no functional impact (`option_type` degrades to `None`, which every downstream caller already treats as a valid, non-fatal state per the field's own docstring). Purely operational: log noise obscures genuine BOD-staleness or resolution issues on legs that are actually still open.

**Suggested fix:** guard the `_resolve_option_type` call in `get_positions()`/`get_position` on `net_qty != 0` — skip resolution (and leave `option_type=None`) for flat legs, consistent with how `_check_base_expiry` already skips flat legs before its own BOD-dependent lookup (`scripts/strategies/three_track/paper_3track_snapshot.py:377-378`). Financial-logic change inside `PaperStore` — requires the real `@code-reviewer` gate per project protocol, not just a patch.

**Related:** BUG-005 (same `net_qty != 0` filtering convention, different call site — that bug is about a missing filter in the IC entry scripts' cross-strategy pooling loop, this one is about the filter being applied too late, after resolution already ran).

**Fix (2026-07-20):** guarded the `_resolve_option_type` call in `get_positions()` on `net_qty != 0` — skips resolution entirely for flat legs, leaving `option_type=None` (already a valid, documented state) without ever touching `InstrumentLookup`. `.py` change in `src/paper/store.py`; per project protocol this required the real `@code-reviewer` gate before commit — Cowork mode cannot spawn this project's local `.claude/agents/code-reviewer` subagent (only generic agent types available in this surface), so the gate was satisfied by applying `code-reviewer.md`'s exact checklist directly rather than skipping it, per the protocol's own "structurally cannot spawn `.claude/agents/*`" allowance. Findings: no CRITICAL/ERROR; traced the one production caller of `PortfolioDeltaTracker.aggregate_delta` (`scripts/record/record_paper_trade.py:833`) to confirm it already filters `net_qty != 0` before calling in, so closed legs never reach `option_type`-branching logic there regardless of this change — no regression. One WARNING-level doc gap (not behavioral): `PaperPosition.option_type`'s docstring didn't yet list "flat leg, resolution skipped" as a reason for `None` — fixed in `src/paper/models.py`. Tests: 2 new in `tests/unit/paper/test_store.py` (open leg still resolves as before; closed leg's resolution call is asserted to never fire, not just degrade to `None`, via a spy that raises if invoked) — 71/71 passing in that file; full regression check across `test_store.py`, `test_track_snapshot.py`, `test_tracker.py`, `tests/unit/risk/` (120 tests) all green.

---

## BUG-015 — `base_futures` leg (`paper_nifty_futures`) recorded wrong quantity (75 instead of correct lot size 65) on the May 2026 settlement-close and roll, corrupting the leg's cycle tracking

| Field | Value |
|---|---|
| Severity | **HIGH** — live base leg's current `net_qty` and `instrument_key` attribution are both wrong; roll/expiry monitoring for this leg is silently mis-targeted |
| Status | ✅ Fixed (2026-07-20) |
| Discovered | 2026-07-20, investigating `base_expiry.expiry_not_found instrument_key=NSE_FO|66071` in `logs/paper_snapshot.log` (`trace_id=f5985444`) |
| Location | `paper_trades` rows for `paper_nifty_futures` / `base_futures`, `NSE_FO|66071` (2026-05-26) and `NSE_FO|62329` (2026-05-29); cycle-tracking logic in `src/paper/store.py::get_positions` (DBI-3, `425e054`) |

**Symptom:** `_check_base_expiry` (`scripts/strategies/three_track/paper_3track_snapshot.py:392`) logs `base_expiry.expiry_not_found` for `NSE_FO|66071` — a NIFTY futures contract that expired 2026-05-26, nearly two months ago — because `get_positions()` still reports the open `base_futures` position as keyed to it.

**Root cause:** Trade history: `BUY 65 NSE_FO|66071` (2026-05-11, correctly 1 lot at the current 65 lot size per `DateAwareLotSizeResolver`'s Jan-1-2026-onward table) → `SELL 75 NSE_FO|66071` (2026-05-26, "Settlement close") → `BUY 75 NSE_FO|62329` (2026-05-29, "Base roll: June futures"). Both the settlement-close and the roll used quantity 75 — the *previous* Nifty lot size (in effect Nov 2024–Dec 2025), not the correct 65 in effect at the time. `DateAwareLotSizeResolver` isn't even wired into the paper-trading path (its only callers are `src/portfolio/strategies/finideas/finrakshak.py` and `ilts.py`) — quantity on these trade-recording scripts is a manually supplied CLI argument, so this is a data-entry error (likely muscle memory from the pre-changeover convention), not a code defect in the resolver or recording scripts. The mismatched 65/75 quantities mean running `net_qty` (`65 − 75 = −10`) never crosses exactly zero, so `get_positions()`'s DBI-3 cycle-reset (`src/paper/store.py`, resets `cycle_instrument_key` only on an exact zero-crossing) never fires — the June roll's `BUY 75` folds into the same still-open cycle (`−10 + 75 = 65`), and `cycle_instrument_key` stays frozen on the expired May contract instead of updating to the June one.

**Impact:** `base_futures`'s reported `net_qty` (65) happens to look numerically plausible by coincidence, masking that the underlying ledger is wrong and that the position is attributed to a delisted instrument_key. Roll/expiry monitoring (`_check_base_expiry`) for this leg is checking the wrong contract's expiry — if a further roll happened after `62329`, its expiry is not being monitored at all currently.

**Suggested fix:** corrective SQL update on the two `paper_trades` rows (75 → 65) to restore an exact zero-crossing, then verify `get_positions()` correctly resets `cycle_instrument_key` to the intended current contract. Check whether the 65-vs-75 error propagated into any roll after `62329` before correcting.

**Related:** BUG-016 (same DBI-3 zero-crossing cycle-reset assumption broken by a different data-entry gap); DECISIONS.md DBI-3 entry (`425e054`); BUG-017 (new — the error's propagation check surfaced that `62329` was never rolled after its own 2026-06-30 expiry, a separate live gap this fix exposed rather than caused).

**Fix (2026-07-20):** confirmed via full trade-history pull that the 75-vs-75 error did not propagate past `NSE_FO|62329` — no roll exists after it, so only the two original rows (`id=29` SELL, `id=30` BUY) needed correction. Updated both quantities 75 → 65 in `paper_trades`, with a `notes` annotation identifying the correction and citing `DateAwareLotSizeResolver`'s date table as the source of truth (65 in effect for both trade dates, 75 was the pre-2026-01-01 value). Data-only correction, no `.py` change. Verified by reimplementing `get_positions()`'s exact cycle-tracking algorithm against the live DB (as with BUG-016 — project `.venv` unusable this session): `paper_nifty_futures`/`base_futures` now correctly reports `net_qty=65`, `instrument_key=NSE_FO|62329`, `entry_date=2026-05-29`. Surfaced BUG-017 as a direct consequence — logged separately rather than folded into this fix, since resolving it requires an actual roll decision (new contract selection), not a ledger correction.

---

## BUG-016 — `overlay_pp` roll on 2026-06-29 never recorded a closing trade for `paper_nifty_spot`/`paper_nifty_futures`, leaving both tracks double-booked at 2x the intended position

| Field | Value |
|---|---|
| Severity | **HIGH** — two of three parallel tracks are currently carrying double the intended protective-put exposure, misattributed to an expired contract; this is a live position-sizing/risk misstatement, not just a stale reference |
| Status | ✅ Fixed (2026-07-20) |
| Discovered | 2026-07-20, investigating `option_type_resolution_failed instrument_key=NSE_FO|58627` in `logs/paper_snapshot.log` (`trace_id=f5985444`) |
| Location | `paper_trades` rows for `paper_nifty_spot` and `paper_nifty_futures` / `overlay_pp`, `NSE_FO|58627` (22000 PE, expiry 2026-06-30); cycle-tracking logic in `src/paper/store.py::get_positions` (DBI-3, `425e054`) |

**Symptom:** `option_type_resolution_failed` fires for `NSE_FO|58627`, a 22000 PE that expired 2026-06-30, three weeks ago — because `get_positions()` still reports it as the current `overlay_pp` position's `cycle_instrument_key` for two of the three parallel tracks.

**Root cause:** Trade history across all three strategies: `BUY 65 NSE_FO|58627` (2026-05-11, all three of `paper_nifty_spot`/`paper_nifty_futures`/`paper_nifty_proxy` open identically) → `SELL 65 NSE_FO|58627 @ 0.05` (2026-05-27, **`paper_nifty_proxy` only**) → `BUY 65 NSE_FO|63848` (21800 PE, exp 2026-07-28) (2026-06-29, all three open the roll). `paper_nifty_proxy` closed the expiring 22000 PE near-worthless before opening the new 21800 PE roll — a clean, zero-crossing cycle. `paper_nifty_spot` and `paper_nifty_futures` never got the matching `SELL 65` close; both went straight from the original May `BUY` into the June 29 roll `BUY` with nothing in between. Their running `net_qty` for this leg is therefore **130** (65 + 65 stacked), not 65 — the earlier per-strategy `SUM` check in this session only surfaced the aggregate and didn't catch the double-booking until the full per-row history was pulled. Because `net_qty` never crossed zero for these two tracks, `get_positions()`'s DBI-3 cycle-reset never fires, so `cycle_instrument_key` stays frozen on the expired `58627` instead of moving to `63848` — same failure mode as BUG-015, different trigger (a missing trade, not a wrong quantity).

**Impact:** `paper_nifty_spot` and `paper_nifty_futures` are each currently carrying a real double-booked protective-put position (old expired 22000 PE + new 21800 PE, both counted as one 130-unit lot misattributed to the expired contract) — this skews any P&L, delta, or notional-exposure calculation reading `overlay_pp`'s `net_qty`/`instrument_key` for these two tracks, not just a cosmetic log warning.

**Suggested fix:** backfill the missing `SELL 65 NSE_FO|58627` close trade for `paper_nifty_spot` and `paper_nifty_futures`, dated to match `paper_nifty_proxy`'s 2026-05-27 close (same price, 0.05, since all three tracks opened the original position identically and the contract's worthless-expiry economics don't differ by track). Verify `get_positions()` then correctly resets to `net_qty=65` on `NSE_FO|63848` for both tracks post-backfill.

**Related:** BUG-015 (same DBI-3 zero-crossing assumption broken by a different data-entry gap — missing trade here vs. wrong quantity there); both point to the same underlying process gap: roll trades recorded per-track manually with no cross-track consistency check.

**Fix (2026-07-20):** backfilled the missing `SELL 65 NSE_FO|58627 @ 0.05` close trade into `paper_trades` for `paper_nifty_spot` and `paper_nifty_futures`, dated `2026-05-27` to match `paper_nifty_proxy`'s existing close row exactly (same price, same `ivr_at_entry=0.3110992529348986`), with a `notes` annotation identifying it as a BUG-016 backfill. Data-only correction — no `.py` change, `UNIQUE(strategy_name, leg_role, instrument_key, trade_date, action)` constraint confirmed non-conflicting before insert (differs by `strategy_name` from the existing proxy row). Verified by reimplementing `PaperStore.get_positions()`'s exact cycle-tracking algorithm against the live DB (project `.venv` unusable in this session's sandbox — broken symlink to a macOS-only interpreter) rather than trusting a paraphrase: all three tracks now report `net_qty=65`, `instrument_key=NSE_FO|63848`, `entry_date=2026-06-29` for `overlay_pp` — matching, no longer double-booked or misattributed to the expired `58627`.

---

## BUG-017 — `paper_nifty_futures`/`base_futures` never rolled past its June contract; `NSE_FO|62329` has sat expired 20 days with no successor

| Field | Value |
|---|---|
| Severity | **HIGH** — the base futures leg (hedge notional for the 3-track comparison) is currently unhedged/stale on an expired contract with no live price feed; needs an operator roll decision, not a code or data fix |
| Status | ✅ Fixed (2026-07-20) |
| Discovered | 2026-07-20, as a direct consequence of fixing BUG-015 — correcting the 66071→62329 quantity error required pulling `base_futures`'s complete trade history, which showed only 3 rows total, ending at the June roll |
| Location | `paper_trades`, `paper_nifty_futures` / `base_futures`, `NSE_FO|62329` (June 2026 NIFTY futures, expiry 2026-06-30) |

**Symptom:** none logged as a distinct warning yet — post-BUG-015 fix, `_check_base_expiry` will now correctly target `NSE_FO|62329` instead of the wrong `66071`, and should start firing `base_expiry.expiry_not_found` (or a large negative-DTE alert, depending on whether `62329` still resolves in the BOD file) on the next snapshot run, since DTE has been negative for 20 days.

**Root cause:** the base futures leg was rolled once, correctly in intent (May → June, `id=30`, 2026-05-29), but no further roll was ever recorded after the June contract's 2026-06-30 expiry. Unlike `overlay_pp` (BUG-016, where the roll happened but the close was missing) or the option base leg (`base_ditm_call`, `44498`, which did settle correctly 2026-07-17), this leg's roll process simply stopped after one cycle — no trade of any kind exists for this leg after 2026-05-29.

**Impact:** the paper book's futures-based hedge/comparison track has had no live, valid instrument backing this leg for three weeks. Any P&L, delta, or notional-exposure read on `paper_nifty_futures`/`base_futures` since 2026-06-30 is against a settled, non-existent contract — not simply "stale data" but "no real position," which is a bigger problem for a leg whose whole purpose is to track live futures-based hedging.

**Suggested fix:** not a data correction — requires deciding and recording an actual roll (settlement-close `NSE_FO|62329` at its 2026-06-30 settlement price, then open the next NIFTY futures contract, likely September quarterly per the contract's monthly-only listing convention). This is a live trading/strategy decision, not a bug patch — flagging for operator action rather than fixing unilaterally.

**Related:** BUG-015 (the quantity-error fix this was discovered while verifying); BUG-016 (same "roll process incomplete" family — a different leg, different failure shape, same underlying gap: rolls recorded manually per-leg with no completeness check or reminder once a leg goes quiet).

**Fix (2026-07-20):** operator decision — roll directly into August (`NSE_FO|58072`, expiry 2026-08-25), skipping July (`NSE_FO|61093`, only 8 DTE remaining at decision time, not worth entering). Prices sourced live rather than approximated (correcting the same shortcut that caused BUG-015): June settlement-close used the official NSE Final Settlement Price from the FUTIDX bhavcopy (`settle_price=23865.75` for the 2026-06-30 expiry row, fetched via `scripts/pipeline/bhavcopy_bootstrap.py --underlying NIFTY --start 2026-06-30 --end 2026-06-30 --include-futures`, written to `data/offline/futures_ohlcv/2026/06/nifty_2026_06.parquet`) — distinct from and more correct than that day's traded close (23861.80). August open used a live LTP fetch via `UpstoxMarketClient.get_ltp_sync` (24364.0, against spot 24238.5 — this session's sandbox has no route to `api.upstox.com`, so the operator ran the fetch locally and supplied the result). Recorded: `SELL 65 NSE_FO|62329 @ 23865.75` (2026-06-30), `BUY 65 NSE_FO|58072 @ 24364.0` (2026-07-20). Verified via the same `get_positions()` reimplementation used for BUG-015/016: `net_qty=65`, `instrument_key=NSE_FO|58072`, `entry_date=2026-07-20` — leg is live and correctly hedged again after 20 days unrolled.

---

## BUG-018 — `IronCondorV2._parse_expiry` never matches real Upstox instrument keys; `check_signals` has silently no-op'd for `paper_ic_nifty_v2_monthly` since entry (2026-07-03)

| Field | Value |
|---|---|
| Severity | **HIGH** — the V2 monthly IC's live profit-target, profit-lock (25/50/75% zones), DTE hard-close, and delta-based forced-close signals have never fired once since entry; the position has been running completely unmanaged by its own strategy logic for three weeks |
| Status | ✅ Fixed and committed (2026-07-23, SHA `3435c5a`); diagnostics added, pending 2026-07-24 live tick verification + removal |
| Discovered | 2026-07-23, investigating a user-reported discrepancy: `paper_snapshot.py`'s EOD `paper_nav_snapshots` row for `paper_ic_nifty_v2_monthly` showed 66.4% of max credit captured on 2026-07-21, but `paper_strategies.profit_lock_zone` had never advanced past 0 (not even the 25% log-only milestone) |
| Location | `src/strategy/ic_nifty_v2.py::IronCondorV2._parse_expiry` (was regex-only; `_EXPIRY_RE` defined near top of file) |

**Symptom:** across the full retained `logs/monitor_daemon.log` window (2026-07-20 through 2026-07-22, 571 ticks across all registered strategies), the string `ic_nifty_v2` appears exactly 3 times — once per day, and every occurrence is the startup `Registered IronCondorV2` line. Zero `mark_unavailable`, zero `pnl_gate_skipped`, zero `profit_lock`, zero delta-signal log lines — nothing from `check_signals` actually running its logic, in contrast to `ic_nifty_v1` which logs on every tick (1,690 `mark_unavailable`/`pnl_gate_skipped` hits over the same window, all attributable to V1).

**Root cause:** `_EXPIRY_RE = re.compile(r"NSE_FO\|NIFTY(\d{2}[A-Za-z]{3}\d{4})", re.IGNORECASE)` expects a trading-symbol string (e.g. `NSE_FO|NIFTY28JUL2026...`). Real `instrument_key` values recorded in `paper_trades` for this position are Upstox's numeric form (`NSE_FO|63930`, `NSE_FO|63896`, `NSE_FO|63975`, `NSE_FO|63987`) with no date substring anywhere — the regex can never match, `_parse_expiry` returns `None` for every leg, and `check_signals` hits `if expiry is None: return []` at the very first gate, before the DTE/profit-target/profit-lock code (which begins at the P&L computation step) is ever reached. Identical root cause to **BUG-009** (`paper_ic_snapshot.py`'s EOD audit script, fixed 2026-07-03 via BOD reverse-lookup) and the same class of defect as **BUG-012**'s follow-up, which already fixed `IronCondorV2._find_leg`/`_position_strike` (strike resolution) with a regex-first/BOD-fallback pattern — but that fix was never ported to `_parse_expiry` (DTE/expiry resolution), which is a separate code path.

**Impact:** confirmed for `paper_ic_nifty_v2_monthly` (4 legs entered 2026-07-03, still all `OPEN`). For the entire life of this position, DTE hard-close, the 70% profit-target `CLOSE_FULL`, all three `ProfitLockEngine` zones (25/50/75%), and delta-based `FORCED_CLOSE`/roll evaluation have never executed — the position has been held open purely because nothing ever told it to close or roll, not because none of those conditions were met. `paper_snapshot.py`'s independent `PaperTracker.compute_pnl` (via `get_ltp()`, no expiry dependency) continued computing and persisting real P&L the whole time, which is why the EOD snapshot showed real captured-fraction numbers (66.4% on 07-21, 38.0% on 07-22) while the live strategy remained completely blind to them.

**Contributing factor — test fixture drift:** `tests/unit/strategy/test_ic_nifty_v2_signals.py`'s `_key()` fixture builds keys in the old trading-symbol form (`NSE_FO|NIFTY31JUL2026NIFTY{strike}{type}`), which happens to satisfy the broken regex — so the existing `check_signals` pipeline tests never exercised the real numeric-key path and never caught this. Same test-realism gap noted in BUG-012.

**Fix (2026-07-23):** mirrored `_find_leg`'s established regex-first/BOD-fallback pattern (rather than removing the regex outright, to preserve existing test fixtures and stay consistent with this file's own convention): `_parse_expiry` tries `_EXPIRY_RE` first, and on no match falls back to `InstrumentLookup.from_file(DEFAULT_BOD_PATH).get_by_key(instrument_key)` → `parse_expiry(inst.get("expiry"))` → `date.fromisoformat(...)`, same helper (`src.instruments.lookup.parse_expiry`) BUG-009's fix used. Unresolvable keys / BOD read failures (`OSError`) degrade to `None` and log a WARNING, never raise. Added two temporary diagnostic `log.debug` calls in `check_signals` (tagged `check_signals_entry_diag` / `check_signals_expiry_diag` / `check_signals_pnl_diag`, marked for removal after 2026-07-24 verification) to confirm live ticks now reach the P&L/profit-lock code instead of short-circuiting.

**Tests:** `tests/unit/strategy/test_ic_nifty_v2_signals.py` — `test_parse_expiry_resolves_numeric_key_via_bod`, `test_parse_expiry_resolves_numeric_key_via_bod_epoch_ms`, `test_parse_expiry_numeric_key_not_in_bod_returns_none`, `test_parse_expiry_bod_lookup_raises_returns_none` (mirror BUG-012's `_find_leg`/`_position_strike` test pattern), plus `test_check_signals_end_to_end_resolves_expiry_via_bod` — a full `check_signals` run using real numeric keys (`NSE_FO|63930` etc., not the fixture's old `_key()` form) with a mocked BOD lookup covering all 4 legs, asserting both diagnostic log lines fire with real values and the pipeline reaches its correct hold/`[]` outcome rather than the dead-on-arrival early return. Written in-sandbox (disk quota exhausted here, `pip install pytest` → `ENOSPC`, `.venv` unusable — macOS-only symlink), **run on live host by Animesh 2026-07-23: 26/26 pass in `test_ic_nifty_v2_signals.py`** (initial run caught a real bug in the new end-to-end test itself, not the fix — uniform LTP=50 on all four legs collapsed `combined_mark` to 0, i.e. 100% captured, correctly triggering `CLOSE_FULL` instead of the asserted `[]`; fixed by giving legs distinct LTPs landing at a genuine 10% captured, well under every zone/delta threshold, plus an assertion on `check_signals_pnl_diag`'s `captured_fraction == "0.1000"` so the test can't pass by coincidence again). Full `tests/unit/` suite subsequently run clean: 2451 passed, 2 skipped (pre-existing, unrelated).

**Code review (2026-07-23):** general-purpose agent explicitly loaded `.claude/agents/code-reviewer.md` + `REVIEW.md` and reviewed the scoped diff (this Cowork surface cannot spawn the real `@code-reviewer` subagent). 0 CRITICAL, 0 ERROR, 2 WARNING, 2 INFO. Findings: (1) WARNING — `_parse_expiry`'s BOD fallback now fires on every live tick (real keys are always numeric), adding a third uncached `InstrumentLookup.from_file()` gzip+JSON-parse call per tick alongside the pre-existing `_find_leg_via_bod`/`_position_strike` callers; deferred — pre-existing uncached pattern in this file, not introduced by this fix, but worth hoisting to a memoized/constructor-injected lookup in a follow-up. (2) WARNING — the original two `_parse_expiry` unit tests only fed `expiry` as an ISO string, never exercising the epoch-ms int branch real BOD data actually returns (`src/instruments/lookup.py::parse_expiry`'s int branch) — the same test-realism gap class that hid BUG-018 itself; **fixed immediately**, added `test_parse_expiry_resolves_numeric_key_via_bod_epoch_ms`. (3) INFO — doc said "two" diagnostic log lines, code has three; fixed in CONTEXT.md/TODOS.md. (4) INFO — eager `Decimal.quantize()`/`str()` work in the pnl_diag log call regardless of log level; accepted, line is temporary (removal tagged 2026-07-24). Decimal correctness and exception-scope calibration (`ValueError`/`OSError`) both verified clean, no findings.

**Related:** BUG-009 (identical root cause, different script), BUG-012 (same fix pattern, different method in the same file — `_find_leg`/`_position_strike` vs `_parse_expiry`).

**Committed:** SHA `3435c5a`.

**Open follow-ups (tracked in TODOS.md):**
1. Check `logs/monitor_daemon.log` on 2026-07-24 for `ic_nifty_v2.check_signals_pnl_diag` on `paper_ic_nifty_v2_monthly` — confirms the fix reaches live P&L evaluation in production, not just under test. Once confirmed, remove the 3 temporary diagnostic `log.debug` lines (`check_signals_entry_diag`/`check_signals_expiry_diag`/`check_signals_pnl_diag`) from `check_signals`.
2. Deferred WARNING from code review: `_parse_expiry`'s BOD fallback now fires on every live tick (real keys are always numeric), adding a third uncached `InstrumentLookup.from_file()` read per tick alongside `_find_leg_via_bod`/`_position_strike`. Hoist to a memoized/constructor-injected lookup (pre-existing pattern in this file, not unique to this fix — worth fixing once, for all three call sites).

**Related open investigation:** BUG-019 — Animesh generalised this to "is the live-vs-EOD-snapshot disparity happening for every strategy, not just V2 monthly?" See BUG-019 below.

---

## BUG-020 — `IronCondorV2` profit target re-scopes to the surviving legs' credit after any partial close, instead of the original 4-leg basket credit

| Field | Value |
|---|---|
| Severity | **HIGH** — financial-logic defect, directly affects when real capital would be closed under live trading; makes the 70% profit target fire early (against a smaller, post-partial-close credit base) rather than against the condor's actual entry economics. |
| Status | ✅ Fixed — Phase 1 (persistence layer) SHA `285a8fa`; Phase 2 (V2 entry-path wiring) SHA `8f28214` — see task.md B020.7 for the entry-path discovery that changed this phase's plan (`IronCondorV2.enter()` is dead code in production; wired into `paper_ic_entry_v2.py::run()` instead); Phase 3 (profit-target/profit-lock branches now read the persisted `original_entry_credit`, falling back to the old recompute when `None` or on a non-fatal store-read failure) implemented and tested 2026-08-04 — general-purpose agent standing in for `@code-reviewer` found one ERROR (unguarded store read could skip priorities 4-8 on a transient SQLite error, wider blast radius than intended) and fixed it (wrapped non-fatal, logged, degrades to recompute); 548/548 relevant tests green in-sandbox | SHA `49c39f9` |
| Discovered | 2026-08-04, user question about why `paper_ic_nifty_v2_monthly` closed with a "70% profit target" label alongside a negative lifetime Net P&L |
| Location | `src/strategy/ic_nifty_v2.py::_compute_combined_pnl` (line 2031), consumed by `check_signals`'s Priority 4 profit-target branch (line 1266) |

**Symptom:** `paper_ic_nifty_v2_monthly` closed on 2026-08-04 09:24:11 (`ic_nifty_v2.profit_target_close`, `captured_fraction=0.70`) on what was, by then, only the surviving put spread (`short_put`/`long_put_hedge`) — the call spread had already been force-closed the prior day (2026-08-03 09:15:30, `DELTA_STOP` → `CLOSE_CALL_SPREAD`, after a roll attempt failed the wing-liquidity floor). The reported 70% capture was computed against `entry_credit_pts=98.375`, which is the *put spread's own* entry credit, not the original 4-leg entry credit of 163.850 recorded at basket entry (07-31).

**Root cause:** `_compute_combined_pnl` builds `entry_credit` by summing `avg_sell_price`/`avg_cost` over whatever positions are passed in as `ic_positions` — which is filtered to currently-open legs only. There is no persisted field carrying the original 4-leg entry credit forward; once a partial close (`CLOSE_CALL_SPREAD`/`CLOSE_PUT_SPREAD`) removes legs from `ic_positions`, every subsequent `check_signals` tick silently recomputes `entry_credit` from the smaller remaining subset. The 70% profit-target threshold (`_PROFIT_TARGET_RETENTION`) is then applied against that shrunk denominator.

**Contradicts documented design:** `docs/archive/council/strategy/2026-06-27_ic-v2-profit-lock-adjustment.md` defines `entry_credit` as the original combined 4-leg credit (line 80: "current combined mark (cost to close all 4 legs)"; line 301-303's state-field table; line 969's `captured_fraction` formula) and names a dedicated field, `original_entry_credit`, meant to persist this across the position's lifecycle. That field does not exist anywhere in `ic_nifty_v2.py`, `src/paper/models.py`, or `src/paper/store.py` — it was specified in the council decision but never implemented.

**Practical effect:** any partial close (delta-stop, failed roll, profit-lock wing contraction) makes the profit target easier to hit than intended, because it's chasing a smaller basket. The strategy's lifetime realized P&L can be negative (as it was here, driven by the earlier call-side delta-stop loss) even while a late-cycle "profit target" fires and reports a superficially healthy 70% capture — the two numbers are not contradictory once you know the scoping, but the current behavior deviates from the council-specified design.

**Suggested fix (not yet implemented):** persist `original_entry_credit` (4-leg, captured atomically at entry alongside the existing `PaperTrade` rows) and reference it in the profit-target branch instead of recomputing from `ic_positions`. Same defect present in `IronCondorV1` — see BUG-021.

**Fix in progress, phased per `docs/bugs/task.md`:** decision made 2026-08-04 (direct-operator override, not a full council session — Option 1: persist at entry, not reconstruct from history). Phase 1 (`PaperStore.set_original_entry_credit`/`get_original_entry_credit`, new `paper_strategies.original_entry_credit` column) committed 2026-08-04, SHA `285a8fa`. Phases 2 (wire `IronCondorV2.enter()` to populate it) and 3 (consume it in the profit-target branch, the actual symptom fix) not yet done.

**Related:** BUG-021 (identical defect in `IronCondorV1`), BUG-018 (same file, prior `_parse_expiry` defect), BUG-012 (same file, config mis-binding).

---

## BUG-021 — `IronCondorV1` has the same partial-close entry-credit re-scoping defect as `IronCondorV2` (BUG-020)

| Field | Value |
|---|---|
| Severity | **HIGH** — same class as BUG-020; not yet observed in a live close (no partial close has fired for `paper_ic_nifty_v1_weekly` in the logs sampled), but the code path is provably present and will trigger under the same conditions. |
| Status | ✅ Fixed |
| Discovered | 2026-08-04, audit follow-up after BUG-020, per user request to check V1 |
| Location | `src/strategy/ic_nifty_v1.py::_compute_combined_pnl` (line 907), consumed by `check_signals`'s PROFIT_TARGET/LOSS_STOP branch (line 302) |

**Symptom (confirmed by code inspection, not yet reproduced live):** `ic_nifty_v1.py`'s `check_signals` calls the identical `_compute_combined_pnl` pattern as V2 — `entry_credit` is summed over `ic_positions`, which is filtered to `net_qty != 0` only (line 172-174), with no persisted original-basket credit field. `IronCondorV1` explicitly supports partial closes: `_ALLOWED_ACTIONS` includes `CLOSE_CALL_SPREAD`/`CLOSE_PUT_SPREAD` (line 72), and a single-leg `DELTA_STOP` can auto-select a spread-specific close (line 739: `action_type = "CLOSE_CALL_SPREAD" if leg_role == "short_call" else "CLOSE_PUT_SPREAD"`). If any such partial close executes, every subsequent tick's `PROFIT_TARGET`/`LOSS_STOP` evaluation (line 315-359) will compute `pct = combined_mark / entry_credit` against the surviving legs' credit only, not the original condor's — same root cause and same practical effect as BUG-020.

**Root cause:** identical to BUG-020 — no `original_entry_credit` field persisted at entry; `_compute_combined_pnl` reconstructs `entry_credit` from whatever's currently open.

**Fix (2026-08-04):** reused BUG-020's shared `PaperStore.get_original_entry_credit`/`set_original_entry_credit` helpers as-is (already generic on `strategy_name`, no store-layer change needed — confirmed via graph before implementing, avoiding a second BUG-022-style file drift). `scripts/strategies/ic/paper_ic_entry.py` now persists the 4-leg net credit non-fatally right after margin capture, mirroring V2's entry-script pattern exactly. `ic_nifty_v1.py::check_signals` substitutes the persisted credit into `entry_credit` before the shared PROFIT_TARGET/LOSS_STOP threshold checks — one substitution point covers both signals, unlike V2's profit-target-only scope, since V1's `entry_credit` variable feeds both branches. Falls back to today's recompute on `None` (never persisted) or a store-read exception (narrowly caught, degrades without skipping the rest of the tick's signal evaluation). `general-purpose` + `REVIEW.md` substitute for `@code-reviewer` against `git diff HEAD`: no CRITICAL/ERROR. 682/682 tests pass across `tests/unit/strategy/`, `tests/unit/strategies/ic/`, `tests/unit/paper/test_original_entry_credit.py`.

**Related:** BUG-020 (identical defect in `IronCondorV2`, fixed first; this fix reuses its persistence layer unchanged).

---

## BUG-022 — Delta-stop wing-roll failure drops straight to a naked single-side partial close (`CLOSE_CALL_SPREAD`/`CLOSE_PUT_SPREAD`) instead of searching narrower wing widths first; affects both `IronCondorV1` and `IronCondorV2`

| Field | Value |
|---|---|
| Severity | **HIGH** — financial-logic/risk-management defect. Not a computation error like BUG-020/021; a structural gap where a single failed liquidity check on one candidate strike causes the strategy to give up defined-risk structure entirely on that side, rather than trying other candidates or forcing a full exit. |
| Status | ✅ Fixed (2026-08-04) |
| Discovered | 2026-08-04, user question "how only CE legs got closed, IC should always have 4 legs" — follow-up to BUG-020 investigation |
| Location | `src/strategy/ic_nifty_v2.py` (`roll_wing_attempt`/`entry_skip_wing_floor_miss`/`roll_guard_failed`/`delta_stop` sequence, ~line 1051-1680; `apply_action`'s `CLOSE_CALL_SPREAD`/`CLOSE_PUT_SPREAD` branch, line 1790-1793); `src/strategy/ic_nifty_v1.py` (`_select_wing_roll_target`, line 766; `_auto_select_action` Priority 5, line 736-762) |

**Symptom (confirmed live, V2):** 2026-08-03 09:15:30 (trace `01d74268`), `paper_ic_nifty_v2_monthly`'s short call delta breached `roll_trigger_delta` (0.3726). `roll_wing_attempt` tried one replacement long-call candidate; it failed the wing-floor liquidity/premium check (`entry_skip_wing_floor_miss`, `floor_value=0.05`, `actual_value=1.487`). On that single failure, the code went straight to `roll_guard_failed` → `delta_stop` → `CLOSE_CALL_SPREAD`, closing `short_call`+`long_call_hedge` only (`151.95`/`48.20`) and leaving `short_put`+`long_put_hedge` open. No re-hedge or re-entry logic exists anywhere in the file to reopen the call side afterward (confirmed — `DECISIONS.md`'s IC-CLOSE-2 note explicitly defers replacement-leg logic for `ROLL_WING`/`PROFIT_LOCK_ZONE2`, and `CLOSE_CALL_SPREAD`/`CLOSE_PUT_SPREAD` don't attempt one at all). From that tick until the full close on 08-04, the "iron condor" was structurally a naked-ish 2-leg put credit spread.

**Root cause:** the roll-attempt logic only ever evaluates a single candidate replacement strike per tick. If that one candidate fails the wing-floor guard, the code has exactly two branches: `ROLL_WING` (succeed) or `CLOSE_CALL_SPREAD`/`CLOSE_PUT_SPREAD` (give up on that side only). There is no intermediate step that tries progressively narrower candidate widths before conceding, and no path that escalates to `CLOSE_FULL` (exit both sides) instead of a single-side partial close.

**Same defect confirmed in `IronCondorV1`:** `_auto_select_action`'s Priority 5 (line 736-762) has the identical two-branch shape — `ROLL_WING` if `_select_wing_roll_target` finds a candidate, else `CLOSE_CALL_SPREAD`/`CLOSE_PUT_SPREAD` on the breached side only. `_select_wing_roll_target` (line 766) was not fully read for whether it applies the same wing-floor liquidity guard V2 does — needs confirming before implementation, since V1's roll-acceptance criteria may currently be looser (accepting more marginal candidates) rather than stricter.

**Existing reviewed precedent for the correct pattern:** this codebase already has a "search a narrower structure against a floor guarantee, fall back to `CLOSE_FULL` if nothing qualifies" mechanism — `IronCondorV2`'s Zone 2 profit-lock wing contraction (`docs/archive/council/strategy/2026-06-27_ic-v2-profit-lock-adjustment.md`, floor inequality `max(W_put, W_call) + D_cum + D_lock + K ≤ 0.75 × C₀`, "if the inequality cannot be satisfied at liquid strikes, CLOSE_FULL executes automatically — no human decision point"). That logic is currently only wired to the *voluntary* profit-lock path, not the *involuntary* delta-stop roll path this bug covers.

**Agreed design (user + Claude discussion, 2026-08-04, not yet council-ratified):** on delta-stop roll failure, before falling back to a single-side close:
1. Search progressively narrower long-strike candidates (walking the hedge leg toward the short strike) down to a configured minimum width floor — not all the way to the short strike itself, which would collapse the hedge to zero width (a naked short with extra transaction cost, not a defined-risk structure).
2. At each candidate width, check both the existing liquidity/premium floor AND the same floor-guarantee inequality already used by Zone 2 profit-lock (reused, not reinvented).
3. Only if no candidate across the full search range clears both checks, escalate to `CLOSE_FULL` (exit both sides) — never fall through to a naked single-side `CLOSE_CALL_SPREAD`/`CLOSE_PUT_SPREAD` as the final state.
4. Applies to both `IronCondorV1` and `IronCondorV2`; ideally implemented as one shared roll-search helper rather than two parallel implementations, to avoid the drift already seen between the two files' wing-floor logic.

**Open parameters requiring a decision before implementation:** minimum wing-width floor (points or ₹ debit terms), maximum number of candidate strikes to try per tick, whether V1 and V2 share one helper or keep separate (mirroring) implementations, and whether V1's `_select_wing_roll_target` needs its own floor-guarantee check added first (currently unconfirmed).

**Resolution (2026-08-04):** Step 2b council checkpoint satisfied via direct-operator override (AskUserQuestion), same precedent as BUG-020/021. Ratified parameters: no separate width floor (the existing Zone 2 floor-guarantee inequality, extracted as `roll_utils.evaluate_floor_formula`, is the sole acceptance gate); exhaustive search across every chain strike strictly between the short strike and current wing strike (both endpoints structurally excluded — the short strike can never be a candidate); one shared helper (`roll_utils.search_narrow_wing_replacement`) for both `IronCondorV1` and `IronCondorV2`; V1's pre-existing gap (no liquidity/premium floor at all in `_select_wing_roll_target`) closed as part of the same fix, for free, by adopting the shared helper. `d_cum`/`d_lock` hardcoded to zero in both files (unrelated to profit-lock's own cumulative-debit state). V1 reuses V2's `ProfitLockConfig()` defaults via a module-level `_WING_SEARCH_FLOOR_DEFAULTS` constant, since V1 has no strategy-specific floor config of its own. On exhaustion — or any other roll-guard failure, not just wing-floor-miss — both strategies now escalate `DELTA_STOP` unconditionally to `CLOSE_FULL`; the naked single-side `CLOSE_CALL_SPREAD`/`CLOSE_PUT_SPREAD` outcome no longer exists as a reachable final state. A pre-existing V1-only event-filter bug was caught and fixed in the same session: `_auto_select_action`'s caller (~`ic_nifty_v1.py:426`) only matched `CLOSE_FULL` against `LOSS_STOP`/`TIME_STOP`/`PROFIT_TARGET` event types, so the new `DELTA_STOP`→`CLOSE_FULL` outcome was silently dropped from the returned event list until `"DELTA_STOP"` was added to that match tuple. Reviewed via `general-purpose` agent standing in for `@code-reviewer` against `git diff HEAD` — no CRITICAL/ERROR; one WARNING (REVIEW.md's 80-char line-length limit vs. the repo's actual 100-char ruff/black config, pre-existing doc/tooling mismatch, not a defect here). Tests: `tests/unit/strategy/test_roll_utils.py` (10 new — floor-formula boundary, widest-first selection, narrower-candidate fallback, call/put ordering, exhaustion→None, endpoint exclusion, illiquid-skip, below-premium-skip, empty-range), `tests/unit/strategy/test_ic_nifty_v2_adjustment.py` (3 new — wing-floor-miss rescued by narrower search, DELTA_STOP→CLOSE_FULL mapping for `wing_search_exhausted` and `debit_cap` block reasons), `tests/unit/strategy/test_ic_nifty_v1.py` (2 updated + 1 new — CLOSE_FULL escalation, narrower-search rescue via a mocked persisted entry credit). 567/567 `tests/unit/strategy/` + `tests/unit/paper/test_original_entry_credit.py` pass.

**Related:** BUG-020, BUG-021 (same investigation thread, same two files, discovered same session — entry-credit scoping vs. this structural roll/close gap are two distinct defects, not duplicates).

---

## BUG-023 — `ROLL_WING`/`PROFIT_LOCK_ZONE2` replacement-leg `instrument_key` is fabricated, not resolved from BOD; would be written to `paper_trades` unresolvable once IC-CLOSE-2 persistence lands

| Field | Value |
|---|---|
| Severity | **HIGH** — same defect class as BUG-012/BUG-014 (fabricated/unresolvable `instrument_key`), but not yet symptomatic because the write path it would poison (IC-CLOSE-2 / MC-3) doesn't exist in production yet. Blocks MC-3 from shipping as originally scoped. |
| Status | ✅ Fixed (MC-3a, `docs/plan/monitor-and-close-hardening/tasks.md`) — `_select_wing_roll_target`/`_search_narrower_wing_candidate` (V1) and `_roll_result_to_signal`'s Zone 2 branch + `_execute_partial_roll` (V2, the latter not explicitly named in this entry's original scope but same defect, same files, fixed alongside) now route through new `_resolve_roll_target_key()` helpers calling `InstrumentLookup.search_options`; a BOD miss/exception is treated as a failed roll candidate (`None`), never a crash or a persisted bad key. |
| Discovered | 2026-08-05, `docs/plan/monitor-and-close-hardening/tasks.md` MC-3 pre-implementation investigation (graph-before-code step) |
| Location | `src/strategy/ic_nifty_v1.py::IronCondorV1._select_wing_roll_target` (line 947: `instrument_key = f"NSE_FO|NIFTY{int(candidate.strike)}{option_type}"`); `src/strategy/ic_nifty_v2.py::IronCondorV2._roll_result_to_signal` (equivalent `f"NSE_FO|NIFTY{int(new_put_wing.strike)}PE"` / `...CE"` construction for the Zone 2 profit-lock replacement wings) |

**Symptom (confirmed by code inspection, not yet live):** both V1's `ROLL_WING` roll-target selection and V2's `PROFIT_LOCK_ZONE2` wing-contraction selection pick a real, chain-derived candidate (`roll_utils.find_strike_by_delta` / `roll_utils.search_narrow_wing_replacement`), then build the *replacement leg's* `instrument_key` by string-formatting the strike into a symbol-style key (`NSE_FO|NIFTY25000PE`). Per `CONTEXT.md`/BUG-002 (`src/risk/delta_tracker.py` classification note) and every other instrument-key call site in this codebase, real Upstox instrument keys are numeric-only (e.g. `NSE_FO|63930`) — this symbol-style key can never resolve via `InstrumentLookup.get_by_key` or the live chain's own keying scheme.

**Why it's dormant today:** neither `ROLL_WING` (V1) nor `PROFIT_LOCK_ZONE2` (V2) currently persists the replacement leg to `paper_trades` at all — the payload's `suggested_instrument_key`/`new_put_wing_key`/`new_call_wing_key` fields are only ever displayed in Telegram messages and consumed as an approval-flow hint. The fabricated key sits inert. `docs/plan/monitor-and-close-hardening/tasks.md`'s MC-3 (IC-CLOSE-2) is the task that would first write it to the DB — see that task's split below.

**Root cause:** `_select_wing_roll_target` (V1) and `_roll_result_to_signal` (V2) both derive the replacement leg's `instrument_key` purely from the in-memory chain scan result (an `OptionLeg`, which has no `instrument_key` field at all — confirmed via `src/models/options.py`), rather than resolving it against the BOD instrument master the way every persisting call site elsewhere in the codebase does.

**Reusable fix (confirmed present, not novel):** `InstrumentLookup.search_options(underlying="NIFTY", strike=<candidate.strike>, option_type=<"CE"|"PE">, expiry=<already-resolved IC expiry>)` (`src/instruments/lookup.py:188`, 3 existing callers) returns the real BOD instrument dict, including its numeric `instrument_key`. Route both files' roll-target construction through it instead of the f-string; treat "candidate found by delta/liquidity but strike not present in the same-expiry BOD file" as a failed candidate (same as a liquidity-gate miss), not a crash.

**Relationship to MC-3:** MC-3 ("persist the close side of ROLL_WING/PROFIT_LOCK_ZONE2") was scoped as a pure persistence task assuming the replacement leg's key was already valid. It wasn't. Per user decision 2026-08-05, MC-3 is being split (see `tasks.md`) rather than silently expanded in scope this session.

**Related:** BUG-012 (same defect class, IC's original strike-parse-failure fix), BUG-014 (same class, closed-leg key resolution).

---

## BUG-024 — `IronCondorV2.enter()` still fabricates all four entry legs' `instrument_key` via string-formatting, not BOD resolution

| Field | Value |
|---|---|
| Severity | **HIGH** — same defect class as BUG-023, but wider blast radius: this is the *entry* path (`enter()`, `src/strategy/ic_nifty_v2.py:277,284,291,298`), which persists to `paper_trades` on every single new IC V2 open — unlike BUG-023's roll path, which was confirmed dormant. |
| Status | ✅ Fixed (MC-6, `docs/plan/monitor-and-close-hardening/tasks.md`) — all four `enter()` legs now resolve via the (renamed, now-shared) `IronCondorV2._resolve_instrument_key()` helper; a BOD miss on any leg aborts the entire entry (`return None`), never a partial/unresolvable position. Pre-fix audit (`scripts/dev/audit_bug024_fabricated_keys.py` against the live DB, 2026-08-06) found **0** existing `paper_ic_nifty_v2*` rows with a fabricated key — confirmed dormant before this fix, not an active data-corruption incident. |
| Discovered | 2026-08-06, `@code-reviewer`-substitute pass on the MC-3a (BUG-023) fix — flagged as out-of-scope for that task and not previously tracked. |
| Location | `src/strategy/ic_nifty_v2.py::IronCondorV2.enter`, lines 277 (`short_put`), 284 (`short_call`), 291 (`long_put`), 298 (`long_call`) — all four build `instrument_key=f"NSE_FO|NIFTY{int(<leg>.strike)}<CE\|PE>"` from the chain-scanned `OptionLeg` directly. |

**Symptom:** identical construction pattern to BUG-023's roll-target fabrication — a symbol-style key that real Upstox `instrument_key`s (numeric-only, e.g. `NSE_FO|63930`) can never match.

**Why this was more urgent than BUG-023 was:** `enter()`'s legs are written to `paper_trades` immediately on entry (not gated behind an unimplemented persistence step) — but the pre-fix audit confirmed it hadn't actually produced any unresolvable rows yet.

**Fix applied:** same pattern as BUG-023's fix — routes through `InstrumentLookup.search_options(underlying="NIFTY", strike=..., option_type=..., expiry=...)` via the renamed `_resolve_instrument_key()` helper (was `_resolve_roll_target_key`, generalized since it's shared by entry and roll/profit-lock now). Reviewed via `general-purpose` agent standing in for `@code-reviewer` — no CRITICAL/ERROR; two WARNINGs: (1) entry now hard-blocks if BOD lags the live chain scan intraday (operational risk, monitor `ic_nifty_v2.entry_key_resolution_failed` log frequency post-deploy, not fixed — there's no code fix for "BOD can be stale," only monitoring); (2) `entry_recorded` log was firing before the new abort check — fixed in the same pass, moved after the resolution guard so it only ever describes entries that actually proceed. 67/67 relevant tests pass.

**Related:** BUG-023 (identical defect class, roll path — fixed, same commit lineage), BUG-012, BUG-014.

---

## BUG-026 — CC/PP/Collar auto-entry crons crash at the IVR gate on every run (`str`/`Path` mismatch on `settings.vix_data_dir`); zero overlay trades have ever landed despite live-posture unblock

| Field | Value |
|---|---|
| Severity | **HIGH** — not a financial-logic correctness defect (no position was ever entered, so no bad trade), but a live-capital-adjacent automation is fully non-functional: three scheduled crons (`--auto-cc`, `--auto-collar` every Wed 10:30; `--auto-pp` daily 10:30) have failed on 100% of invocations since at least 2026-08-04, with no downstream signal (no Telegram alert, only a stderr line captured in a per-cron log file) that would surface this to the operator. |
| Status | ✅ Fixed (2026-08-07, SHA `b3202e3`) — `Settings.vix_data_dir` retyped `str` → `Path`; see `DECISIONS.md` 2026-08-07 for the root-cause-vs-narrow-wrap decision and the caller sweep that confirmed it was safe. |
| Discovered | 2026-08-07, cross-checking SNAP-3's DB finding ("CC/PP/Collar have zero rows in every `paper_*` table") against `logs/cron.log` + `logs/cc_entry.log`/`collar_entry.log`/`pp_entry.log` at the operator's prompt — SNAP-3 had initially (incorrectly) attributed the empty tables to "pre-bootstrap, nothing has traded yet," per stale `CONTEXT.md` text saying `--no-dry-run` was still hard-blocked for these paths. That block was actually lifted 2026-08-02/03 (confirmed via `paper_3track_overlay_entry.py` code), so the correct explanation is this bug, not an unstarted feature. |
| Location | `src/config.py::Settings.vix_data_dir` (declared `str`, not `Path`); `src/backtest/vix_ingest.py::load_vix_series(data_dir: Path)` (calls `data_dir.glob(...)` unconditionally); all three call sites in `scripts/strategies/three_track/paper_3track_overlay_entry.py`: `auto_cc_bootstrap` (~line 241), `auto_collar_bootstrap` (~line 374), `auto_pp_bootstrap` (~line 597) — each passes `settings.vix_data_dir` straight into `load_vix_series` with no `Path(...)` wrap. |

**Symptom:** `logs/cc_entry.log`, `logs/collar_entry.log`, `logs/pp_entry.log` show the identical error on every single cron run:

```
[ERROR] ... auto_cc.ivr_check_failed error='str' object has no attribute 'glob'
ERROR: auto-CC bootstrap failed. Check logs.
```

(same shape for `auto_collar`/`auto_pp`; `pp_entry.log` shows 4 consecutive daily failures, 2026-08-04 through 2026-08-07). All three functions wrap the IVR gate in a bare `except Exception` that logs and returns `None` (or `(None, None)` for PP) — the crash never propagates, so the cron job "succeeds" (exit path is a clean early return, not an unhandled exception) and produces no Telegram alert. This is why `paper_trades`/`paper_nav_snapshots`/`paper_leg_snapshots`/`paper_overlay_pnl_snapshots` all show zero rows for `paper_nifty_overlay` and every overlay `leg_role` (`overlay_cc`, `overlay_pp`, `overlay_collar_call`, `overlay_collar_put`) — confirmed independently against the live DB by both Cowork's mounted copy and a direct run on the operator's host (`scratch/2026-08-07_overlay_snap3_cross_check.py`).

**Root cause:** `Settings.vix_data_dir: str = Field(default="data/historical/ohlc/india_vix", ...)` in `src/config.py` — typed as a plain string. `load_vix_series(data_dir: Path)` in `src/backtest/vix_ingest.py` immediately calls `data_dir.glob("**/india_vix_*.parquet")`, which raises `AttributeError` on a `str`. Every other `load_vix_series` caller apparently wraps the setting in `Path(...)` before passing it (not confirmed exhaustively — 11 total callers per the graph, only these 3 were traced for this bug); these three overlay bootstrap functions do not.

**Fixed 2026-08-07** — `Settings.vix_data_dir: str` retyped to `Path` (`src/config.py`); pydantic coerces a string env value automatically, so no `.env`/env-var change needed. Root-cause fix chosen over the narrower 3-call-site wrap (Animesh, direct decision) after a full `grep`/graph sweep of all ~11 `vix_data_dir` callers confirmed every other caller already wraps the value in `Path(...)` defensively — only the 3 broken call sites (`auto_cc_bootstrap`/`auto_collar_bootstrap`/`auto_pp_bootstrap`) and one `str`-comparison test assertion (`tests/unit/test_config.py`) needed changing. Confirmed the exact gap this bug's own diagnosis predicted: every existing test for the three bootstrap functions mocks `load_vix_series` directly, so `settings.vix_data_dir`'s real type never reached `.glob()` in the suite. Added the regression test the bug report called for: 3 new tests in `tests/unit/paper/test_overlay_entry.py` call the real (unmocked) `load_vix_series()` against a fixture VIX Parquet directory for all three bootstrap functions, plus 2 new tests in `tests/unit/test_config.py` (Path-type assertion, string-env-var-to-Path coercion). 2726 passed / 2 skipped on a live-sandbox `pytest tests/unit/` run; 1 pre-existing failure (`test_r3_no_block_on_buy`, blocked outbound network call to `api.upstox.com`) + 2 pre-existing collection errors (`test_chain_reader.py`, `test_council_fallback.py`) re-run in isolation and confirmed unrelated to this diff. Not a financial-logic correctness change (config type fix only, no P&L/Decimal/order-path code touched) — `general-purpose` + `REVIEW.md` substitute review, no CRITICAL/ERROR.

**Related:** `docs/plan/paper-ic-daily-snapshot/stories.md` SNAP-3 findings (correction), 3-Track Consolidation epic (CC1–CC5/PP1–PP5/Collar1–Collar3b, `docs/archive/plan/3track-consolidation/`) — this bug means the "live-posture unblock" closed in that epic never actually resulted in a live overlay entry.

---

## BUG-028 — Overlay P&L snapshot/digest pipeline structurally blind to `STRATEGY_OVERLAY`-scoped legs since S2r track-independence (2026-07-29); today's PP entry invisible to `paper_overlay_pnl_snapshots` and the "NiftyBees vs overlays" Telegram digest

| Field | Value |
|---|---|
| Severity | **HIGH** — not a P&L-correctness defect in the position itself (the `paper_trades` row is now correct after BUG fix same day, see `DECISIONS.md` 2026-08-10 lot_size entry), but the entire per-overlay reporting pipeline (persisted snapshot table + daily Telegram recovery digest) has been silently producing false "0" P&L for any overlay leg opened after 2026-07-29, with no error, no exception, no downstream signal — same silent-failure shape as BUG-026/BUG-027. |
| Status | ✅ Fixed — all 4 phases complete. Phase 1 SHA `6820f81`. Phase 2 (eliminate silent false zeros) SHA `4b8b351`. Phase 3 (historical repair script, `scripts/dev/migrate_overlay_pnl_attribution.py`) SHA `0fd4de8` — `general-purpose`+`REVIEW.md` review clean (no CRITICAL/ERROR), 5 tests confirmed green on live host. See `docs/bugs/task.md` B028.11–B028.13. **Phase 4 (`src/strategy/auto_close.py::evaluate_pp_reentry_eod()`) fixed 2026-08-13, SHA `94f3dc3`** (doc-tracking update SHA `affbd24`) — code + tests + `general-purpose`/`REVIEW.md` review complete (clean, no CRITICAL/ERROR/WARNING against the diff). See `docs/bugs/task.md` B028.14–B028.17. |
| Discovered | 2026-08-10, Animesh flagged that today's `overlay_pp` entry showed `pnl=0` on the daily "NiftyBees vs overlays" Telegram digest despite a real, correctly-recorded position (65 lots @ 65.7, current LTP 60.90, real unrealized loss ≈ ₹312). Traced during the same session as the `lot_size=75` bug fix (see `DECISIONS.md` 2026-08-10), which is unrelated — that bug affected trade quantity; this one affects whether the leg is visible to reporting at all. |
| Location | `src/paper/track_snapshot.py::generate_track_snapshot()` (root cause — queries `store.get_trades(track_namespace)` / `store.get_position(track_namespace, role)` scoped only to `track_namespace`); `scripts/strategies/three_track/paper_3track_snapshot.py::_compute_overlay_pnl_snapshots()` (downstream writer, only ever called per-track inside the `for track_name in tracks:` loop over `ALL_TRACKS = [STRATEGY_SPOT, STRATEGY_FUTURES, STRATEGY_PROXY]`); `scripts/strategies/three_track/paper_3track_snapshot.py::compute_protection_recovery()`/`_build_recovery_digest()` (the Telegram digest itself, hardcodes `STRATEGY_SPOT` as its only overlay P&L source via `store.get_overlay_pnl_snapshots(STRATEGY_SPOT, overlay_type, ...)`). |

**Symptom:** `paper_overlay_pnl_snapshots` has no rows for `pp`/`cc`/`collar` newer than 2026-08-04 (confirmed live query). Today's `overlay_pp` trade (`strategy_name='paper_nifty_overlay'`, `trade_date='2026-08-10'`) has zero corresponding rows anywhere in `paper_overlay_pnl_snapshots`, `paper_leg_snapshots`, or `paper_nav_snapshots`. The "NiftyBees vs overlays" Telegram digest defaults every overlay type to `Decimal("0")` when `store.get_overlay_pnl_snapshots(STRATEGY_SPOT, overlay_type, start_date=snap_date, end_date=snap_date)` returns no rows (`_compute_protection_recovery`, `overlay_1d`/`overlay_inception` dict init), so the digest silently shows `+0` for PP/CC/Collar instead of erroring or warning — indistinguishable in the Telegram message from "no P&L movement today."

**Root cause:** `NiftyTrackComparisonV1`'s S2r change (2026-07-29, `CONTEXT.md`/`DECISIONS.md` same date — "Track-ownership overlay blocks removed") made overlay entry/roll track-independent by operator decision: `_check_futures_cc_block` and an undocumented futures+`overlay_cc` hard-block were both deleted, and overlay legs (CC/PP/Collar) are recorded under the standalone `STRATEGY_OVERLAY = "paper_nifty_overlay"` strategy_name (`src/paper/constants.py`), not under whichever track (`paper_nifty_spot`/`futures`/`proxy`) they might conceptually be "attached" to. This was a deliberate, correct design decision at the entry-script layer (`paper_3track_overlay_entry.py`'s `auto_cc_bootstrap`/`auto_collar_bootstrap`/`auto_pp_bootstrap` all write under `STRATEGY_OVERLAY`, confirmed via `DECISIONS.md` 2026-07-29 round 5). But the overlay P&L snapshot/reporting pipeline — `generate_track_snapshot()`, `_compute_overlay_pnl_snapshots()`, and the recovery digest — predates S2r and was never updated to match: it still assumes overlay legs live under a track's own strategy_name, because at the time it was built (S8/S9, per `CONTEXT.md`'s 3-Track Consolidation history) they did. The 2026-08-04 rows with real nonzero PP/CC/Collar P&L are leftover snapshots from overlay positions that were still parked under a track's strategy_name from before S2r shipped and hadn't yet closed/rolled off; any overlay leg opened after S2r (all of them, going forward) is structurally invisible to this entire pipeline. No exception is ever raised anywhere in this chain — `generate_track_snapshot` simply finds zero trades/positions for `track_namespace`+overlay `leg_role` combinations that don't exist (because the real rows are filed under a different `strategy_name` entirely), and every downstream consumer treats "zero found" as "P&L is zero" rather than "data is missing."

**Design fork — not yet resolved, requires a decision before implementation:**
- **(a) Re-attribute:** extend `generate_track_snapshot()` to additionally pull `STRATEGY_OVERLAY`-scoped legs and attribute them into each track's per-track view, preserving the existing report's meaning (each track shown "as if" it carries its own overlay). This re-couples overlays to tracks for reporting purposes only, which sits in tension with S2r's own rationale for decoupling them at the entry layer — risks reintroducing the confusion S2r was written to resolve, and raises an unanswered attribution question (if overlays are track-independent, which track's "view" should show a `STRATEGY_OVERLAY` leg — all three, one designated primary, or a new aggregate?).
- **(b) Decouple pipeline:** rebuild the overlay P&L/snapshot/digest pipeline around `STRATEGY_OVERLAY` as its own independent strategy, matching the entry layer's actual current architecture. More correct going forward, but a larger multi-file rework touching `track_snapshot.py`, `paper_3track_snapshot.py`, `PaperStore`, `paper_overlay_pnl_snapshots`' schema/semantics (currently keyed to a track-carrying `strategy_name`), and the recovery digest's entire framing (which is built around "NiftyBees vs each track's overlay," not a single track-independent overlay book).

Per `docs/council/README.md`'s three-condition check (load-bearing/costly-to-reverse: yes, affects live daily reporting and any future automation built on `paper_overlay_pnl_snapshots`; two defensible approaches with materially different outcomes: yes, (a) vs (b) above; spans multiple disciplines: yes, trading-strategy design + reporting/data-architecture simultaneously) — **this qualified for a council checkpoint before implementation.** Flagged to Animesh 2026-08-10.

**Resolution (2026-08-10, council):** unanimous 4/4 verdict for **(b) Decouple pipeline**, implemented as a schema-preserving "B-lite" refactor — canonical overlay P&L rows written with `strategy_name = STRATEGY_OVERLAY` instead of a base track's `strategy_name`; no DDL change (the existing `(strategy_name, overlay_type, snapshot_date)` primary key already supports it). (a) Re-attribute was rejected without dissent — no defensible attribution rule (triple-count vs. arbitrary "primary track" vs. an aggregate row that converges on (b) anyway), and it would re-couple reporting to tracks against S2r's own rationale. Full mandate (3 phases: correctness fix → eliminate silent false zeros → historical repair) recorded in `DECISIONS.md` 2026-08-10 and `docs/council/2026-08-10_overlay-pnl-reporting-track-independence.md`. **Phase 1 implemented 2026-08-10, SHA `6820f81`** — see `CONTEXT.md`'s BUG-028 Phase 1 entry and `docs/bugs/task.md` B028.1–B028.7. **Phase 2 implemented 2026-08-10, SHA `4b8b351`.** **Phase 3 implemented 2026-08-10** (`scripts/dev/migrate_overlay_pnl_attribution.py` + `tests/unit/scripts/test_migrate_overlay_pnl_attribution.py`) — backs up the DB, derives the S2r cutover date from `MIN(paper_trades.trade_date)` where `strategy_name=STRATEGY_OVERLAY`, relabels pre-cutover `paper_overlay_pnl_snapshots` rows filed under a legacy 3-track `strategy_name` to `STRATEGY_OVERLAY` via a collision-checked `UPDATE` (never a blind overwrite, never a dual-write), skips + WARNs on any `(STRATEGY_OVERLAY, overlay_type, snapshot_date)` collision leaving the legacy row intact. Not yet run against the live DB or committed — see `docs/bugs/task.md` B028.11–B028.13 for the outstanding test-execution gap.

**Related:** S2r (`DECISIONS.md` 2026-07-29, `docs/plan/3track-consolidation/stories.md`) — the change that created this gap, itself a correct decision; BUG-026 (same silent-failure shape: a fully broken automation path with zero downstream signal, discovered by an operator noticing an absence rather than an error); the same-day `lot_size=75` fix (`DECISIONS.md` 2026-08-10) — unrelated defect on the same trade, found via the same investigation thread.

**Phase 4 (found 2026-08-13, fixed 2026-08-13, SHA `94f3dc3`) — `src/strategy/auto_close.py::evaluate_pp_reentry_eod()` missed by the Phase 1–3 sweep, same root cause:**

Discovered when Animesh received a `🟢 PP RE-ENTRY ELIGIBLE` Telegram alert while a PP overlay was in fact open (`STRATEGY_OVERLAY`, `overlay_pp`, BUY 65 lots, `NSE_FO|61604`, opened 2026-08-11). `evaluate_pp_reentry_eod` predates S2r-aware reporting the same way `generate_track_snapshot`/`_compute_overlay_pnl_snapshots` did, and was not touched by Phase 1–3 because it lives in `auto_close.py`, not `track_snapshot.py`/`paper_3track_snapshot.py`. Two call sites inside the function build a local `track_strategies = [STRATEGY_SPOT, STRATEGY_FUTURES, STRATEGY_PROXY]` and never reference `STRATEGY_OVERLAY`:

- The `active_pp` eligibility check (`store.get_positions(strat_name)` for `strat_name in track_strategies`, filtered to `leg_role == "overlay_pp"`) finds nothing under any of the three base tracks — because the real row lives under `STRATEGY_OVERLAY` — and incorrectly reports "No open PP → ELIGIBLE".
- The Telegram message's `"Overlay P&L (total realized)"` figure is `sum(get_strategy_realized_pnl(store, s) for s in track_strategies)` — this sums the three base tracks' realized P&L (NiftyBees/futures/proxy legs), not the overlay book's, so the number shown is mislabeled: it is base-track P&L presented as overlay P&L. Given B028's resolution — canonical overlay P&L lives under `STRATEGY_OVERLAY` — this should be a single `get_strategy_realized_pnl(store, STRATEGY_OVERLAY)` call.

**Fix (implemented 2026-08-13, matches B028's resolved architecture — decision (b), decouple from tracks):** both call sites in `evaluate_pp_reentry_eod` switched from the `track_strategies` list to `STRATEGY_OVERLAY`; `track_strategies`/the `STRATEGY_SPOT/FUTURES/PROXY` import dropped from the function since nothing else in it needs the three-track list. Tests: `test_evaluate_pp_reentry_suppressed_when_active` updated to seed the open `overlay_pp` leg under `STRATEGY_OVERLAY` (eligibility check now correctly suppresses); new `test_evaluate_pp_reentry_realized_pnl_reads_overlay_book_only` proves the realized-P&L figure reads only from `STRATEGY_OVERLAY`, not a base track. `general-purpose`+`REVIEW.md` substitute for `@code-reviewer` (subagent type not exposed in this environment, same precedent as B028.6/B028.13/B021.4/B010.8) — clean, no CRITICAL/ERROR/WARNING against the diff; 1 INFO note (no invariant guard against a stray `overlay_pp` leg ever landing under a base track post-S2r — latent architectural risk inherent to the decouple-pipeline decision itself, not introduced by this diff). 8/8 tests in the file pass, plus 1057/1057 in `tests/unit/strategy/`+`tests/unit/paper/` with zero regressions (run via a cloud sandbox venv — this device sandbox has no network to install `pytest`). See `docs/bugs/task.md` B028.14–B028.17. Committed on live host: code+tests SHA `94f3dc3`, doc-tracking update SHA `affbd24`.

---

## BUG-027 — `scripts/healthcheck.py` never calls `load_dotenv()`; every healthcheck alert has silently no-op'd since at least 2026-08-04

| Field | Value |
|---|---|
| Severity | **HIGH** — not a financial-logic defect, but this is the project's dead-man's-switch cron (`CONTEXT_TREE.md`: "Dead man's switch for EOD cron validation"). Its entire purpose is to alert when something else is broken; it has been silently failing to alert for at least 4 trading days with zero downstream signal — the exact "silent automation failure" class `BUG-026` also hit. |
| Status | ✅ Fixed — `load_dotenv()` fix (SHA `7a81b6d`) + 4 new tests in `tests/unit/test_healthcheck.py` (8/8 total pass), review self-checked against `REVIEW.md`. Docs-close (`bugs.md`/`task.md`/`TODOS.md`) landed under B027.4. |
| Discovered | 2026-08-10, Animesh reported seeing healthcheck log entries but no Telegram messages, while other scripts' Telegram alerts (`paper_3track_snapshot.py`, `eod_summary.py`, etc.) were arriving normally — investigated during the `telegram-markdown-migration` ROLL-11 workshop session. |
| Location | `scripts/healthcheck.py` (imports, lines 16-30) — missing `from dotenv import load_dotenv` + `load_dotenv()` call present in every sibling cron script. |

**Symptom:** `logs/healthcheck.log` shows, on every single run from 2026-08-04 through 2026-08-07 (and presumably every run since): the check messages print correctly (`✅ DB: accessible`, `⚠️ VIX data: N days stale`, etc.), `has_issue=True` is correctly detected, `main()` logs `WARNING System healthcheck failed or warned`, then immediately: `[INFO] [__main__] Telegram notifier not configured. Skipping alert.` No Telegram message is ever sent, on any run where an alert should have fired.

**Root cause:** `build_notifier()` (`src/notifications/telegram.py:119-151`) deliberately constructs a fresh, uncached `Settings(_env_file=None)` on every call (see `BUG-011`'s 2026-08-06 fix) — it reads `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` **only** from the real OS process environment, never from `.env`. Every other cron-invoked script in this codebase (`paper_3track_snapshot.py`, `eod_summary.py`, `daily_snapshot.py`, `paper_ic_snapshot.py`, `paper_ic_entry.py`, ~25 files total, confirmed via `grep -rn "load_dotenv"`) calls `from dotenv import load_dotenv` + `load_dotenv()` near the top of the file *before* `build_notifier()`/`settings` is ever touched. `load_dotenv()` mutates `os.environ` directly as a side effect — that's what actually gets the token into the process environment `build_notifier()`'s `Settings(_env_file=None)` reads from. Cron's own environment never has these vars set directly (confirmed — `logs/cron.log`'s tracked crontab entries have no env-var preamble, and healthcheck's crontab line is a bare `cd ... && .venv/bin/python -m scripts.healthcheck`, identical in shape to every other job). `scripts/healthcheck.py`'s import block (lines 16-30) has no `dotenv` import and no `load_dotenv()` call at all — so under cron, `os.environ` is genuinely empty for these two vars by the time `build_notifier()` runs, and it correctly (per its own contract) returns `None`.

**Why other scripts aren't affected:** identical `build_notifier()` call, identical cron invocation pattern (`cd <repo> && .venv/bin/python -m scripts.<module>`, no env-var prefix) — the only difference is every working script's own `load_dotenv()` call populating `os.environ` first. This was confirmed directly, not inferred: `grep -rn "load_dotenv"` across `src/`+`scripts/` returns the pattern in ~25 files; `scripts/healthcheck.py` is not among them.

**Impact:** the healthcheck cron (`55 15 * * 1-5`) has been running "successfully" (exit code aside — `main()` still returns 1 on `has_issue`, so the cron *does* register a failure exit code, but with no human-visible alert) with zero operator-visible signal for at least the 4 trading days captured in the current `logs/healthcheck.log` window, and plausibly since the script was first deployed (`RO-4`, `docs/archive/plan/reporting-and-ops-fixes/tasks.md`) — no evidence in that task's spec that this was ever tested end-to-end against a real cron environment (only interactively, where a developer's shell likely already had the tokens exported).

**Suggested fix:** add the same two-line pattern every sibling script already uses, before `build_notifier()`/`settings` is used:

```python
from dotenv import load_dotenv
...
load_dotenv()
```

placed the same way `eod_summary.py`/`paper_3track_snapshot.py` do it (module-level, near the top, before other project imports that might touch settings). This is a real code fix, not a docs-only or formatting change.

**Suggested regression test:** mirror the pattern other `load_dotenv()`-bearing scripts' test files use (if any test asserts this — check via `search_graph` before assuming none exists) — a test that clears `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` from `os.environ` via `monkeypatch.delenv`, writes a fixture `.env` file with both values set, imports/reloads `scripts.healthcheck`, and asserts `build_notifier()` now resolves to a real notifier (not `None`) — proving the module-level `load_dotenv()` call actually runs and actually populates the environment before any notifier construction.

**Related:** `BUG-011` (the `build_notifier()` `Settings(_env_file=None)` design this bug's root cause depends on); `BUG-026` (same failure shape — a live-capital-adjacent automation silently no-op'ing with no downstream alert, discovered the same way: an operator noticing an absence rather than an error).

**Implementation progress (2026-08-13, moved here from `task.md` during archival cleanup):**
`from dotenv import load_dotenv` + a module-level `load_dotenv()` call added to
`scripts/healthcheck.py`, placed before the `src.*` imports — same placement convention as
`scripts/eod_summary.py` (`# noqa: E402` on the now-late `src.*` imports). 4 new tests in
`tests/unit/test_healthcheck.py` (8/8 total pass): the core regression test (patches
`dotenv.load_dotenv`, reloads the module, asserts called once — this is the test that would have
failed pre-fix), a real-fixture-`.env` resolution test, a no-regression "still `None` without
configured env" test, plus a `_reload_healthcheck_without_touching_real_env()` helper (discovered
mid-session that real `load_dotenv()` mutates `os.environ` directly, leaking into later tests
unless carefully isolated; also confirmed `monkeypatch.chdir()` does not control which `.env`
`load_dotenv()` discovers — it walks up from the caller's source file, not `cwd`). Self-reviewed
against `REVIEW.md` (import ordering, no unused imports, comment explains *why* not just *that*)
— a real `@code-reviewer`/`general-purpose` agent pass is still recommended before commit.
**Docs-close note (2026-08-24):** the code fix and its tests were already committed
(`7a81b6d` load_dotenv fix, `bee2649` later B029.5 healthcheck follow-up in the same file) —
`task.md`/`bugs.md` had simply not been flipped to reflect that. B027.4 closes out the
bookkeeping only: Status line above, this line, `task.md` B027.4 checkbox, `TODOS.md` session
log. No further code change needed for BUG-027.

---

## BUG-029 — `paper_exit_events.counterfactual_dte_marks` migration committed but never run against the live DB; `paper_3track_snapshot.py`'s 15:35 EOD cron has crashed every market day since 2026-08-05

| Field | Value |
|---|---|
| Severity | **HIGH** — not a P&L-correctness defect, but a full crash of the daily 3-track snapshot script before it reaches exit-signal evaluation (delta-stop/premium-stop checks for all base + overlay legs) or the overlay P&L/leg-snapshot/protection-recovery pipeline (BUG-028's fix target). Zero downstream signal — the crash is logged but nothing alerts on it, same silent-failure shape as BUG-026/027. |
| Status | ✅ Fixed — migration confirmed live (`counterfactual_dte_marks` present on `paper_exit_events`); every 15:35 cron from 2026-08-11 through 2026-08-21 in `logs/paper_snapshot.log` completed clean (no further `OperationalError` tracebacks past 08-10); 2026-08-10's `paper_leg_snapshots`/`paper_protection_recovery_snapshots` rows confirmed backfilled. B029.5 healthcheck coverage SHA `bee2649`. Full verification detail below. |
| Discovered | 2026-08-10, while checking `logs/paper_snapshot.log`/`logs/cron.log` to see whether today's PP overlay trade had propagated to `paper_overlay_pnl_snapshots`/`paper_leg_snapshots`. It hadn't — traced to a crash in the same cron run, not a data-attribution gap. |
| Location | `src/paper/store.py::PaperStore.get_open_exit_events()` (crash site, `SELECT` includes `counterfactual_dte_marks`); `scripts/strategies/three_track/paper_3track_snapshot.py::compute_and_record_exit_signals()` → `_run()` (caller, crash occurs before overlay P&L/leg-snapshot/protection-recovery code further down the same function ever runs); `scripts/dev/migrate_exit_events_counterfactual_dte_marks.py` (the fix — already existed, never executed). |

**Symptom:** `logs/paper_snapshot.log`'s `35 15 * * 1-5` cron entry (`scripts.strategies.three_track.paper_3track_snapshot --no-dry-run`) has thrown an identical unhandled `sqlite3.OperationalError: no such column: counterfactual_dte_marks` traceback at `compute_and_record_exit_signals()` → `store.get_open_exit_events()` on every market day from 2026-08-05 through 2026-08-10 (confirmed by direct log inspection, not inference — same file/line/error on 08-05, 08-07 [Wed/Thu logs rotated out but 08-05/08-07/08-10 confirmed present], 08-10). A separate, unrelated cron entry (`36 15 * * 1-5`, `scripts.portfolio.paper_snapshot`) writes to the same log file and succeeds independently — its `total_pnl` NAV rows continuing to appear made the crash easy to miss, since *something* useful still landed in the DB every day.

**Root cause:** Commit `17b4ff9` (`feat(paper): add counterfactual_dte_marks column to paper_exit_events`, 2026-08-05 13:11 IST, Animesh) correctly added the column to `_SCHEMA`, to `create_exit_event`/`get_exit_event`/`get_open_exit_events`'s queries, **and** shipped a migration script (`scripts/dev/migrate_exit_events_counterfactual_dte_marks.py`) in the same commit — the code-side change was done properly. But committing a migration script does not run it: nothing in `docs/bugs/task.md`, `TODOS.md`, or `DECISIONS.md` records it ever being executed against `data/portfolio/portfolio.sqlite`, and a direct schema diff (fresh in-memory DB built from `_SCHEMA` vs. the live DB, checked 2026-08-10) confirms the live table is still missing the column. This is a process gap, not a code defect — the same class of "committed the fix, never ran the migration" miss, just never surfaced until a code path that actually selects the column executed (`get_open_exit_events`, called daily by the 3-track snapshot script, but apparently not exercised by anything else that runs more frequently/visibly).

**Fix:** run the existing migration (`python -m scripts.dev.migrate_exit_events_counterfactual_dte_marks`) against the live DB; add test coverage for the migration script, which had none (`tests/unit/scripts/test_migrate_exit_events_counterfactual_dte_marks.py`, 4 tests: column added + existing row preserved, idempotent re-run, dry-run no-write, no-op on an already-migrated DB). `general-purpose`+`REVIEW.md` substitute review: no CRITICAL/ERROR/WARNING — migration script confirmed correct as originally written (idempotent, dry-run safe, correct use of `src.db.connect()`, `ALTER TABLE ADD COLUMN` confirmed safe/cheap since `paper_exit_events` is non-`STRICT`); the review's one INFO note flagged that running the migration against the live DB is the actual operational fix and is separate from committing test coverage — see `docs/bugs/task.md` B029.1+ for whether that's been done this session.

**Related:** BUG-026/BUG-027/BUG-028 — same silent-failure shape (a broken automation path producing zero operator-facing signal until someone manually checks a log file); unlike those three, the code itself was correct from day one here — this is purely a "shipped fix, never deployed it" gap, suggesting the missing safeguard is process (a migration-execution checklist item, or `scripts/healthcheck.py`/`position_health_check.py` gaining coverage for "did the 3-track snapshot script's last run exit 0") rather than anything to fix in the migration script itself.

**Implementation progress (2026-08-24, B029.4/B029.6 close):** direct DB verification via
`python3 -c "sqlite3..."` against `data/portfolio/portfolio.sqlite` (no code change — pure
confirmation pass): (1) `PRAGMA table_info(paper_exit_events)` confirms `counterfactual_dte_marks`
present. (2) `grep -n "OperationalError: no such column: counterfactual_dte_marks"
logs/paper_snapshot.log` returns exactly 3 hits, dated 2026-08-05/07/10 only — every 15:35 run
from 2026-08-11 through 2026-08-21 present in the log has no `Traceback` entry. (3) Backfill
confirmed: `paper_leg_snapshots` and `paper_protection_recovery_snapshots` both carry rows dated
2026-08-10 (3 and 1 rows respectively) — these could only exist via a backfill re-run, since the
crashing 08-10 cron died in `compute_and_record_exit_signals()` before reaching that write path.
`paper_overlay_pnl_snapshots` has zero rows for 08-10, which is correct rather than a residual
gap: `paper_trades` shows the first `overlay_*` leg (`overlay_pp`) wasn't opened until
2026-08-11, so there was nothing to snapshot on 08-10. B029.4 and B029.6 both closed this
session; see `docs/bugs/task.md` B029.1-6 (now archived, section fully checked).

---

## BUG-025 — MC-3b review follow-ups: `roll_ic_legs` open-only write shape, `PROFIT_LOCK_ZONE2` state/write ordering

| Field | Value |
|---|---|
| Severity | **LOW** — both are theoretical/edge-case findings from the MC-3b review pass, not confirmed live symptoms; logged so they aren't lost, not because either is known to have fired. |
| Status | ✅ Fixed — SHA `700dbf0` (2026-08-24). |
| Discovered | 2026-08-06, `@code-reviewer`-substitute pass on MC-3b (IC-CLOSE-2 roll persistence, `docs/plan/monitor-and-close-hardening/tasks.md`). |
| Location | `src/strategy/ic_close_executor.py::roll_ic_legs` (W1); `src/strategy/ic_nifty_v2.py::IronCondorV2.apply_action`'s `PROFIT_LOCK_ZONE2` branch (W2). |

**W1 — `roll_ic_legs`'s empty-check doesn't require `to_close` non-empty when `open_legs` is non-empty.** The guard is `if not to_close and not open_legs: ... return []` — if `closed_roles` matches zero live positions (stale role, already-closed leg from a race) but `open_legs` is non-empty, the function proceeds and writes an open-only trade: a new leg with nothing closed. Not the naked-position failure mode MC-3b was built to prevent (this is the inverse — extra/duplicate exposure), and in every current call site `closed_roles` is derived from the same in-memory position list passed as `close_positions`, so it's unlikely to diverge today. No fix applied — either assert `to_close` non-empty when `open_legs` is non-empty, or explicitly document an open-only write as an accepted `roll_ic_legs` outcome, next time this function is touched.

**W2 — `PROFIT_LOCK_ZONE2`'s `ProfitLockState` persistence and Telegram notification happen before `roll_ic_legs`'s success is known.** `apply_action` calls `store.set_profit_lock_state(..., zone2_lock_executed=True)` and sends the Zone 2 notification in one branch, then calls `roll_ic_legs` in a separate, later branch. If `roll_ic_legs` fails (broker/store exception, or its own price-guard aborts), the state store already says the zone-2 lock executed while the actual leg replacement never persisted — a state/reality divergence visible on the next signal-evaluation tick. This ordering pre-dates MC-3b (the state persistence already existed; only the trade-write call is new) so it isn't a regression introduced by this task, but MC-3b was the natural point to reorder (persist state only after confirming `roll_ic_legs` returned non-empty) and that reorder wasn't done. No fix applied — flagged for a fast-follow.

**Related:** MC-3b (`docs/plan/monitor-and-close-hardening/tasks.md`), BUG-023, BUG-024.

**Scoping (2026-08-24):** split into two independent fixes, each small enough not to need
council-checkpoint review on its own, but the combined diff touches the live roll/profit-lock
path so a mandatory review gate (B025.5) still applies.

- **W1 fix:** in `roll_ic_legs`, when `open_legs` is non-empty and `to_close` is empty, log an
  error and return `[]` instead of proceeding — fail-closed, symmetric to the existing
  naked-position guard the function already enforces for the opposite case.
- **W2 fix:** in `IronCondorV2.apply_action`'s `PROFIT_LOCK_ZONE2` handling, move
  `store.set_profit_lock_state(..., zone2_lock_executed=True)` and the Telegram notification from
  the early branch to after `rolled_trades = await roll_ic_legs(...)`, gated on
  `if rolled_trades:` — persists success only once the roll actually wrote, closing the
  state/reality divergence window.

Checklist: `docs/archive/bugs/task.md` B025.2 (W1), B025.3 (W2), B025.4 (tests for both), B025.5
(mandatory review), B025.6 (commit + close).

**Implementation progress (2026-08-24), closed same day, SHA `700dbf0`:**

- **W1**: added `if open_legs and not to_close: log.error("ic_close_executor.roll_open_only_rejected", ...); return []`
  in `roll_ic_legs`, placed after the existing `if not to_close and not open_legs` no-op guard
  and before the open-leg price-validation loop (so a rejected open-only roll skips price
  validation for legs it's about to discard). Close-only rolls (`to_close` non-empty, `open_legs`
  empty) are unaffected.
- **W2**: removed the early `store.set_profit_lock_state(...)` + Telegram-notification block from
  the `elif action.action_type == "PROFIT_LOCK_ZONE2":` branch in `apply_action`. Both now fire
  after `rolled_trades = await roll_ic_legs(...)` is called and logged, gated on
  `if action.action_type == "PROFIT_LOCK_ZONE2" and rolled_trades:` — a `list[PaperTrade]`
  truthiness check, so an empty/failed roll no longer claims the lock executed.
- **Tests added**: `test_roll_open_only_when_closed_roles_match_nothing_returns_empty` and
  `test_roll_close_only_still_writes_when_to_close_nonempty` in `test_ic_close_executor.py`;
  `test_apply_action_zone2_roll_failure_does_not_persist_state` in
  `test_ic_nifty_v2_profit_lock.py` (mocks `store.record_trades` raising `RuntimeError` to model
  `roll_ic_legs`'s write-failure path, asserts neither `set_profit_lock_state` nor
  `send_notification` fire). The pre-existing `test_apply_action_updates_state` was updated to
  supply a broker/store pair (mirroring the sibling `..._persists_close_and_open_legs` test) since
  state persistence is now gated on the roll actually reaching `roll_ic_legs` and succeeding — a
  strategy with no broker takes the `no_broker_or_store` early-out and never reaches the roll.
- **Test run**: `tests/unit/strategy/test_ic_close_executor.py` + `test_ic_nifty_v2_profit_lock.py`
  — 28/28 pass. Full `tests/unit/` also run in an ad-hoc sandbox venv (macOS `.venv` isn't
  reachable from the device-bridge Linux VM, so deps were reinstalled from
  `requirements.txt`/`requirements-dev.txt` + pyproject dev-extras into a throwaway venv):
  2784 passed, 29 failed, 2 skipped. Confirmed via `git show HEAD` diff that the same 29 failures
  occur identically on unmodified sources — pre-existing environment gaps (structlog/caplog
  wiring under the throwaway venv), not caused by this change, not investigated further here.
- **Review**: real `@code-reviewer` subagent type isn't spawnable on this Cowork surface — used
  the `general-purpose` + `REVIEW.md`-substitute path the project's CLAUDE.md allows for this
  case. No findings; confirmed guard ordering, list-truthiness correctness, no stale-state read
  between old/new W2 write locations, only one `roll_ic_legs` call site (V1 doesn't roll), and
  that the new/modified tests exercise real (non-tautological) failure paths.
- **Commit**: blocked initially by a `.git/index.lock` held by a concurrent process in the
  sandbox checkout (`rm`/`git add` both hit `Operation not permitted`) — per
  `docs/bugs/prompt.md`'s lock-contention fallback, stopped before committing rather than forcing
  it. Animesh committed the four changed files directly once the lock cleared: SHA `700dbf0`.

---

---

## BUG-030 — `_overlay_type_groups()` elif-precedence drops an `overlay_cc` leg whenever an `overlay_collar_put` leg is also present same-day; corrupts the Collar P&L figure and produces a false "CC No data" line in the recovery digest

| Field | Value |
|---|---|
| Severity | **HIGH** — live P&L-correctness defect, not just a reporting gap. Silently drops a real, open leg's P&L (`overlay_cc`, +₹53.625 on 2026-08-13) from both `paper_overlay_pnl_snapshots` and the daily "NiftyBees vs overlays" Telegram digest, and folds a mislabeled result into the `collar` row instead — the displayed Collar P&L (-₹973) is understated by the missing call leg's contribution (true value -₹919.75). No exception, no warning specific to this combination — same silent-failure shape as BUG-026/027/028. |
| Status | ✅ Fixed — SHA 86db6a2 (2026-08-24). B030.4 (backfill/discontinuity note for 08-12/08-13 rows) remains open separately. |
| Discovered | 2026-08-13, Animesh flagged that the "NiftyBees vs overlays" Telegram digest showed `CC No data` despite an open, correctly-recorded CC position (`STRATEGY_OVERLAY`, `overlay_cc`, SELL 65 lots, opened 2026-08-12, today's `paper_leg_snapshots.total_pnl` = +53.625). Traced live against `data/portfolio/portfolio.sqlite` during the investigation — not inferred from logs. |
| Location | `scripts/strategies/three_track/paper_3track_snapshot.py::_overlay_type_groups()` (lines 1081-1117, root cause); `_compute_overlay_pnl_snapshots()` (lines 1137-1219, downstream — never emits an `overlay_type='cc'` row when this fires); `_build_recovery_digest()` (lines 1537-1593, renders the resulting gap as "CC No data" — that part of BUG-028 Phase 2 is working exactly as designed, it just never sees a `cc` row to render). |

**Symptom:** `paper_overlay_pnl_snapshots` has zero `overlay_type='cc'` rows for either 2026-08-12 or 2026-08-13, despite `paper_leg_snapshots` showing a real, open `overlay_cc` leg with nonzero `total_pnl` on both dates (-537.875 on 08-12, +53.625 on 08-13 — confirmed via direct query). The `collar` row for the same dates contains only the `overlay_collar_put` leg's P&L (08-13: `pnl_inception_abs = -973.375`, exactly matching the put leg alone) — the `overlay_cc` leg's P&L is not merged into it, not reported separately, and not visible anywhere downstream. The digest renders `CC No data`, which BUG-028 Phase 2 correctly distinguishes from a false `+0` — but the underlying condition it's flagging (no `cc` row exists) is itself the bug, not a legitimately absent leg.

**Root cause:** `_overlay_type_groups(present_roles)` decides which `overlay_*` leg_roles combine into a `cc`/`pp`/`collar` reporting row via an `if/elif` chain:

```python
if has_call and has_put:
    groups["collar"] = ["overlay_collar_call", "overlay_collar_put"]
elif has_call:
    groups["cc"] = ["overlay_collar_call"]
elif has_put:
    groups["collar"] = ["overlay_collar_put"]      # fires here
elif has_cc:
    groups["cc"] = ["overlay_cc"]                   # never reached
```

`has_call`/`has_put`/`has_cc` are computed independently from `present_roles`, but the chain only ever branches on `has_call`/`has_put` — `has_cc` is checked last and is unreachable whenever `has_put` is `True`, regardless of whether `has_cc` is also `True`. The live position hit exactly this: a short call opened under leg_role `overlay_cc` (not `overlay_collar_call`) and a long put opened under `overlay_collar_put`, both same-day (2026-08-12) — economically a collar, but tagged with a `cc`-style role for the call leg rather than a `collar`-style one. `has_call=False`, `has_put=True`, `has_cc=True`. The chain falls into the `elif has_put` branch, builds `collar` from `overlay_collar_put` alone, and the `overlay_cc` leg is never added to any group in `groups`, so `_compute_overlay_pnl_snapshots`'s `for overlay_type, roles in groups.items()` loop never sees it — no row is ever written for it, silently.

This is orthogonal to BUG-028: that bug was entirely about *which `strategy_name` to query* (track-scoped vs. `STRATEGY_OVERLAY`) and none of its four phases touched leg-role grouping. `_overlay_type_groups` predates BUG-028 and was carried over unmodified by all four phases — this defect exists whether or not BUG-028's fix is applied.

**Two distinct questions, not yet resolved:**
- **Entry-side:** should the call leg have been tagged `overlay_collar_call` instead of `overlay_cc` when the put was added same-day, converting what may have started as a standalone CC into a collar? If so the real fix is in the overlay entry path (`paper_3track_overlay_entry.py`'s collar/CC entry logic), not here. Not yet investigated — flagged, not diagnosed.
- **Reporting-side, true regardless of the above:** `_overlay_type_groups` has no branch for `has_cc and has_put` simultaneously. Even if the entry-side tagging is intentional (e.g., an operator manually added a hedge put against an existing CC without converting its role), the grouping function must not silently drop one of the two legs — it needs an explicit branch that either merges `overlay_cc` + `overlay_collar_put` into `collar`, or reports both legs' P&L (as separate `cc`/`collar` rows or a combined row), matching whichever semantics is actually decided for the entry-side question above.

**Suggested fix:** do not patch this inline without a decision on the entry-side question first — the two questions are coupled (the grouping fix depends on what the correct leg_role *should* have been). At minimum, add a regression test asserting `_overlay_type_groups({"overlay_cc", "overlay_collar_put"})` does not silently drop either role, whatever the resolved semantics turn out to be. Given this affects live daily P&L reporting the same way BUG-028 did, this likely qualifies for the same council-checkpoint bar BUG-028 used (`docs/council/README.md`'s three-condition check) if the entry-side fix changes how future collar/CC positions get tagged.

**Related:** BUG-028 (same file, same overlay-reporting pipeline, same "silent gap read as legitimate zero/no-data" failure shape, but a different root cause — namespace vs. leg-role grouping — and BUG-028's four phases did not cover this).

**Implementation progress (2026-08-24, SHA `86db6a2`):** B030.1's entry-side question resolved by direct code inspection, not a council checkpoint — `build_overlay_trades()`/`_record_collar_trades()` in `paper_3track_overlay_entry.py` already contain a deliberate, documented dedup guard: when a collar entry is submitted and an `overlay_cc` short call is already open on the same instrument key, the code intentionally skips inserting a second `overlay_collar_call` leg ("the existing CC serves as the collar call... recording a second SELL on the same contract would double-count the short position"). `_validate_collar_pairs()` and `_query_open_call_role()` implement the same convention on the validation side (`test_put_only_exempt_when_existing_cc_covers_call`). So the `overlay_cc` + `overlay_collar_put` combination is the intended tagging, not a mistagging — converting the call leg's role at entry would be wrong. The fix was purely reporting-side: added an explicit `has_cc and has_put` branch to `_overlay_type_groups()` that merges `overlay_cc` + `overlay_collar_put` into the `collar` group, matching the entry-side semantics, ordered before the existing `has_put`-only branch so it doesn't regress the collar-call-rolled-off warning path. Updated the grouping-convention comment block above `_OVERLAY_ROLES` to document the new combination.

Tests added (`tests/unit/scripts/test_paper_3track_overlay_pnl.py`): 6 unit tests on `_overlay_type_groups()` covering all 5 reachable leg-role combinations (including the BUG-030 regression case) plus pp-independence; 1 end-to-end test on `_compute_overlay_pnl_snapshots()` reproducing the live 2026-08-13 figures (+53.625 cc / -973.375 put → merged collar row, no separate cc row). All 14 tests in the file pass. Self-reviewed against `REVIEW.md` in lieu of a real `code-reviewer` subagent (not available in this environment) — ruff and `py_compile` clean, one line-length violation (G2, >80 chars) caught and fixed before commit.

**B030.4 backfill (2026-08-24):** backed up `data/portfolio/portfolio.sqlite` to `data/portfolio/portfolio.bak_20260824T030023_pre-BUG030.4-backfill.sqlite`, then recomputed the two affected `collar` rows with the fixed `_compute_overlay_pnl_snapshots()` and upserted them via `PaperStore.record_overlay_pnl_snapshot()` (no raw SQL — idempotent upsert on `(strategy_name, overlay_type, snapshot_date)`). Verified read-back matches:

| Date | Field | Before (buggy) | After (backfilled) |
|---|---|---|---|
| 2026-08-12 | collar pnl_inception_abs | -703.625 | -1241.500 |
| 2026-08-12 | collar pnl_1d_abs | -703.625 | -1241.500 |
| 2026-08-13 | collar pnl_inception_abs | -973.375 | -919.750 |
| 2026-08-13 | collar pnl_1d_abs | -269.750 | 321.750 |

`pp` rows on both dates were left untouched (verified byte-identical `pnl_1d_abs`/`pnl_inception_abs` before and after) — this bug never touched the `pp` overlay_type. No `cc` row is written separately; per the BUG-030 fix, `overlay_cc` merges into `collar`, matching the entry-side "existing CC serves as the collar call" semantics.

Note: the historical Telegram digests already sent on 2026-08-12/13 (showing `CC No data` and the understated Collar P&L) cannot be retroactively corrected — this backfill only fixes the DB row for any downstream reader (backtests, the BUG-019 diagnostic window, trailing-window analytics).

**New finding surfaced during this backfill, not part of BUG-030:** both recompute runs logged `paper_store.get_position_ambiguous leg_role=overlay_pp match_count=2` — two open positions currently match `leg_role='overlay_pp'` under `STRATEGY_OVERLAY`, and whichever query resolves quantity for the `pp` P&L calc doesn't pin down which one it returns, so `pp`'s `pnl_1d_pct`/`pnl_inception_pct` are non-deterministic across recompute runs (the `pnl_*_abs` fields are unaffected — they come straight from `paper_leg_snapshots.total_pnl`, not from position quantity resolution). Not touched here since it's out of BUG-030's scope (overlay_pp, not overlay_cc/collar) — needs its own bug entry and a decision on which of the two `overlay_pp` positions is the real one.

---

---

## BUG-031 — `CCOverlayV1`/`PPOverlayV1`/`CollarOverlayV1` filter positions by their own pre-S2r `strategy_name` constants, not `STRATEGY_OVERLAY` — every auto-entered CC/PP/Collar leg has had zero live exit-signal coverage since S2r shipped (2026-07-29)

| Field | Value |
|---|---|
| Severity | **CRITICAL** — not a reporting gap like BUG-028/030, a risk-management gap on live (paper) capital. No delta-stop, premium-stop, profit-target, time-stop, or DTE-triggered roll signal has ever fired for any CC/PP/Collar overlay leg opened by the auto-entry crons, for the full three weeks since S2r shipped. Positions silently accumulate with nothing watching them; the only reason this surfaced is a human noticing a duplicate entry, not any alert. |
| Status | ✅ Fixed — SHA `ea5df81` (code + tests), `a738fc0`/`7090ce6` (docs). Closed 2026-08-24. |
| Discovered | 2026-08-20, Animesh — while investigating why `paper_3track_overlay_entry.py --auto-pp` entered a second `overlay_pp` put (`NSE_FO|74009`) on top of a still-open one (`NSE_FO|61604`, opened 2026-08-11). Root-caused across several steps in the same session: (1) confirmed via `logs/cron.log` that `--auto-pp`'s cwd/`--db-path` were correct, ruling out a path mismatch; (2) confirmed via `logs/base_roll.log`/`futures_entry.log`/`ditm_entry.log` that no concurrent 10:30 cron job wrote to `portfolio.sqlite` today, ruling out lock contention; (3) confirmed via the `overlay_pp` DTE decay in `logs/pp_entry.log` (13→12→11→8→7→6 on 2026-08-11→08-19) that 2026-08-20 was exactly the day DTE hit `_PP_ROLL_DTE_THRESHOLD=5` — today's fresh-put entry was the *correct, scheduled* routine-roll trigger, not a bug; (4) that meant the real defect had to be on the **close side** of the roll — the outgoing `NSE_FO|61604` leg was never closed by the live monitor; (5) `grep -c "overlay_pp" logs/monitor_daemon.log` returned `0` — the string never appears in that log's entire history, despite `PPOverlayV1` being registered every single day (confirmed at `09:15:07` today via `MONITOR_OVERLAYS=1 — registering overlay strategies` / `Registered overlay strategy name=PPOverlayV1`, and on 08-14/08-17/08-18/08-19 in the same log); (6) traced to `PPOverlayV1.strategy_name = STRATEGY_PP_OVERLAY = "paper_protective_put_v1"` filtering `pos.strategy_name != self.strategy_name`, while `auto_pp_bootstrap()` writes every `overlay_pp` trade under `STRATEGY_OVERLAY = "paper_nifty_overlay"` — confirmed via direct DB query that `paper_trades` has **zero rows, ever**, under `paper_protective_put_v1`. |
| Location | `src/strategy/pp_overlay_v1.py:60` (`strategy_name: str = STRATEGY_PP_OVERLAY`), `src/strategy/cc_overlay_v1.py:60` (`strategy_name: str = STRATEGY_CC_OVERLAY`), `src/strategy/collar_overlay_v1.py:76` (`strategy_name: str = STRATEGY_COLLAR_OVERLAY`) — all three filter open positions/legs against `self.strategy_name` throughout (`pp_overlay_v1.py:136`, `cc_overlay_v1.py:121`/`198`, `collar_overlay_v1.py:145`/`155`/`355`, plus each class's `apply_action` leg-resolution paths). Contrast with `src/paper/constants.py:26-28` (`STRATEGY_CC_OVERLAY = "paper_covered_call_v1"`, `STRATEGY_PP_OVERLAY = "paper_protective_put_v1"`, `STRATEGY_COLLAR_OVERLAY = "paper_collar_v1"`) vs. `src/paper/constants.py:36` (`STRATEGY_OVERLAY = "paper_nifty_overlay"` — the namespace `scripts/strategies/three_track/paper_3track_overlay_entry.py`'s `auto_cc_bootstrap`/`auto_pp_bootstrap`/`auto_collar_bootstrap` actually write trades under). Registration site: `scripts/monitor_daemon.py:335-360` (`MONITOR_OVERLAYS` env-gated block instantiating all three classes and appending them to `StrategyMonitor`'s `strategies` list). |

**Symptom, confirmed via direct queries (not inferred):**
- `SELECT strategy_name, COUNT(*) FROM paper_trades GROUP BY strategy_name` → the full distinct set is `paper_csp_nifty_v1`, `paper_ic_nifty_v1_leaps/monthly/weekly`, `paper_ic_nifty_v2_monthly`, `paper_nifty_futures`, `paper_nifty_overlay`, `paper_nifty_proxy`, `paper_nifty_spot`. `paper_protective_put_v1`, `paper_covered_call_v1`, and `paper_collar_v1` — the three namespaces `PPOverlayV1`/`CCOverlayV1`/`CollarOverlayV1` actually watch — have **zero rows, ever**.
- `SELECT leg_name, COUNT(*) FROM paper_exit_events WHERE leg_name LIKE 'overlay_%' GROUP BY leg_name` → empty result set. No `overlay_pp`/`overlay_cc`/`overlay_collar_call`/`overlay_collar_put` exit event has ever been recorded, for any leg, on any date.
- `grep -c "overlay_pp" logs/monitor_daemon.log` → `0`, across the log's entire retained history, despite `PPOverlayV1` being confirmed-registered on every checked day (08-14, 08-17 [13:55, an off-schedule restart], 08-18, 08-19, 08-20).
- Live consequence, today: `overlay_pp` leg `id=168` (`NSE_FO|61604`, BUY 65, opened 2026-08-11, `state='OPEN'`) sat unmonitored for 9 days while its DTE decayed from 14 to 5; when the entry-side cron correctly triggered a same-day routine roll (per `_open_pp_dte`'s design — see `TODOS.md` 2026-08-20 / `DECISIONS.md` 2026-08-20 for that half of today's investigation), the outgoing leg was never closed because nothing evaluates `ROLL_ELIGIBLE`/executes `ROLL_PP` against it. `portfolio.sqlite` now has two simultaneously-`OPEN` `overlay_pp` rows (`id=168` and `id=204`, `NSE_FO|74009`, today), with the same underlying gap meaning neither will ever auto-close.

**Root cause:** S2r (2026-07-29, `DECISIONS.md` same date, "Track-ownership overlay blocks removed") made overlay entry track-independent by deliberate design — `paper_3track_overlay_entry.py`'s `auto_cc_bootstrap`/`auto_pp_bootstrap`/`auto_collar_bootstrap` all write trades under the single shared `STRATEGY_OVERLAY` namespace instead of under whichever 3-track base (`paper_nifty_spot`/`futures`/`proxy`) they're conceptually attached to. **BUG-028** (root cause same date, fixed 2026-08-10) already found and fixed one consumer that this change broke: the P&L reporting pipeline (`track_snapshot.py::generate_track_snapshot()`, `paper_3track_snapshot.py::_compute_overlay_pnl_snapshots()`, the recovery digest) was still querying by track namespace and silently reported "P&L is zero" for every post-S2r overlay leg instead of "data is missing." BUG-028's three phases repointed that pipeline at `STRATEGY_OVERLAY`.

But `CCOverlayV1`/`PPOverlayV1`/`CollarOverlayV1` — the classes `StrategyMonitor` actually ticks to *evaluate exit signals and execute closes/rolls* (a completely different consumer from the reporting pipeline BUG-028 touched) — were never part of BUG-028's fix scope, and no other bug entry references them: grepped both `docs/bugs/bugs.md` and `docs/archive/bugs/bugs.md` for `cc_overlay_v1`/`pp_overlay_v1`/`collar_overlay_v1` — the only hit is an unrelated, already-fixed BOD-strike-parsing regex bug (2026-07-06 entry, archived) that explicitly flagged-but-deferred these three files' `strategy_name`/namespace question as a "not fixed, follow-up" item and it was never picked back up. Each class still carries its own pre-S2r dedicated `strategy_name` constant and has never been updated to match where the entry script actually files trades — so `StrategyMonitor`'s tick loop calls `check_signals()` on all three every poll interval, each one queries/filters against a namespace with zero trades, finds nothing, and silently does nothing. No exception anywhere in this chain — same "zero found read as legitimately flat" failure shape as BUG-026/027/028/030, just in the live-execution path instead of a reporting path.

**One nuance worth resolving before patching (mirrors BUG-030's entry-side/reporting-side split):** `STRATEGY_CC_OVERLAY` is not universally dead code — `scripts/strategies/cc_calibration/paper_cc_entry.py`/`paper_cc_roll.py` (an older, separate manual CLI tool, `leg_role="covered_call"` not `overlay_cc`) also reference it as their position-storage namespace, and `paper_3track_overlay_entry.py` itself uses all three constants (`STRATEGY_CC_OVERLAY`/`STRATEGY_PP_OVERLAY`/`STRATEGY_COLLAR_OVERLAY`) as informational `GateViolation.strategy_name` tags (`paper_3track_overlay_entry.py:316`/`480`/`789`) — those are gate-violation labels, not position-storage reads, and are not part of this defect. Confirmed via direct query that `paper_covered_call_v1`/`paper_protective_put_v1`/`paper_collar_v1` have zero trades regardless of `leg_role`, so the `cc_calibration` tool's namespace is also empty in practice today — but the fix needs to grep every reference to these three constants (not just the three `strategy_name: str = ...` class attributes) before repointing them, so it doesn't silently break the calibration tool's own (currently dormant but not deleted) code path.

**Impact:** every CC/PP/Collar overlay leg opened by the auto-entry crons since 2026-07-29 (three weeks of trading days at the time of discovery) has had no live exit-signal coverage whatsoever — no delta-stop, premium-stop, profit-target, time-stop, or DTE-roll has ever been evaluated or executed for any of them via `StrategyMonitor`. This is broader than the `overlay_pp` duplicate that surfaced it — every open CC and Collar leg needs the same manual exit-eligibility review, not just PP.

**Suggested fix:** repoint `strategy_name` on all three classes (`cc_overlay_v1.py:60`, `pp_overlay_v1.py:60`, `collar_overlay_v1.py:76`) to `STRATEGY_OVERLAY`, matching where `paper_3track_overlay_entry.py` actually writes and matching the direction BUG-028 already resolved for the reporting side of this same S2r change. Before patching: (a) grep every reference to `STRATEGY_CC_OVERLAY`/`STRATEGY_PP_OVERLAY`/`STRATEGY_COLLAR_OVERLAY` (not just the class attributes) and confirm the `cc_calibration/` tool and the `GateViolation` tagging call sites are unaffected or are deliberately updated too; (b) test coverage needs to be end-to-end (a CC/PP/Collar position opened under `STRATEGY_OVERLAY` gets picked up by a `StrategyMonitor` tick and evaluated for exit signals), not just a unit-level `strategy_name` equality assertion — that's exactly the class of gap that let this ship unnoticed; (c) given this governs live-capital-adjacent auto-execution (`MONETIZE_PP`, `ROLL_PP`, `CLOSE_CC`, `CLOSE_AND_REENTER_COLLAR`), this should get the same council-checkpoint treatment BUG-028/BUG-030 flagged for changes of this shape (`docs/council/README.md`'s three-condition check). Separately, immediate manual action independent of the code fix: review every currently-open CC/PP/Collar leg for exit-eligibility by hand, since nothing has been doing it automatically.

**Related:** BUG-028 (same root cause — S2r, 2026-07-29 — this is the un-remediated second half: live-monitor exit-signal classes vs. the reporting pipeline BUG-028 fixed); BUG-030 (same overlay-reporting file/pipeline as BUG-028, a different defect); `TODOS.md` 2026-08-20 entry (the `overlay_pp` duplicate-entry symptom that led to this discovery) and its companion `DECISIONS.md` 2026-08-20 entry (the entry-gate fail-safe fix, which is correct and complete on its own but does not address this).

**Implementation progress (B031.1, 2026-08-24):** grepped every reference to `STRATEGY_CC_OVERLAY`/`STRATEGY_PP_OVERLAY`/`STRATEGY_COLLAR_OVERLAY` repo-wide (`search_code` graph tool exceeded the context-size cap on this result set, fell back to direct `grep` per Rule 0's decision tree). Confirmed three-way split: (1) **position-storage reads, in scope for B031.2** — the `strategy_name: str = ...` class attributes (`cc_overlay_v1.py:60`, `pp_overlay_v1.py:60`, `collar_overlay_v1.py:76`) plus every downstream `self.strategy_name` filter/leg-resolution call site already cited above; (2) **informational `GateViolation` tags, confirmed out of scope** — `paper_3track_overlay_entry.py:316/480/788` are all `make_gate_violation(strategy_name=...)` calls (IVR re-entry gate logging), verified by reading the call sites directly, not inferred; `tests/unit/paper/test_overlay_entry.py` (3 call sites) test exactly this tagging path and are unaffected; (3) **`cc_calibration/` manual tool, confirmed separate and out of scope** — `paper_cc_entry.py:259` and `paper_cc_roll.py:80/83/87/261` do real position-storage reads/writes but under `leg_role="covered_call"`, a distinct namespace already confirmed empty in production by this entry's own direct-query check; `test_cc_constants.py`/`test_cc_roll.py` test this path only. `scripts/lookup/find_strike_by_delta.py` uses `STRATEGY_PP_OVERLAY` only for BUY/SELL default branching (string value unchanged by the coming repoint) — unrelated. No new scope surfaced beyond what this entry already documented.

**Implementation progress (B031.2/B031.3/B031.5, 2026-08-24, SHA `ea5df81`):** repointed `strategy_name` on all three classes to `STRATEGY_OVERLAY` per B031.1's resolved scope — two-line diff per file (import + class attribute), confirmed via `git diff` that no other line in any of the three files changed and no stale `STRATEGY_CC_OVERLAY`/`STRATEGY_PP_OVERLAY`/`STRATEGY_COLLAR_OVERLAY` reference remains inside them. Test fixtures in `test_cc_overlay_v1.py`/`test_pp_overlay_v1.py`/`test_collar_overlay_v1.py` had their `_STRATEGY` constant switched from a hardcoded literal to the real `STRATEGY_OVERLAY` import — the hardcoded-literal pattern is exactly what let this bug ship unnoticed (tests kept "passing" against a namespace nothing in production used); this surfaced 3 real regressions in each file's `test_describe_context` (asserting the old literal appears in the Telegram-approval context string), fixed to assert the real constant instead. Added 2 new end-to-end tests to `test_strategy_monitor.py` — a real `CCOverlayV1` registered with a real `StrategyMonitor`, driven through an actual `_tick()`, with `store.get_positions` keyed by strategy_name and a spy on `check_signals` asserting the exact position list received: positive case (a `STRATEGY_OVERLAY` position reaches `check_signals`) and negative case (a position still filed under the retired `STRATEGY_CC_OVERLAY` constant does not) — this is the coverage class the entry's original **B031.3** note called for, not just a unit-level `strategy_name` equality assertion. **Verification note:** the first test pass (121 tests, all green) was run before the edited files had actually been committed back to the device — `device_bash` executes against the real on-device filesystem, not the cloud sandbox's staged copy, so that first run was silently exercising the *unmodified* pre-fix code. Re-ran after committing the real edits to device; this caught the 3 `test_describe_context` regressions above. 262 tests green after the fix (`test_cc/pp/collar_overlay_v1`, `test_strategy_monitor`, `test_monitor_daemon`, `test_overlay_entry`, `test_cc_constants`, `test_cc_roll`, `test_find_strike_by_delta`); 3 unrelated pre-existing `pyarrow`-missing failures in `test_overlay_entry.py` untouched (confirmed pre-existing via isolated run). `general-purpose` + `REVIEW.md` substitute review (no real `code-reviewer` subagent on this Cowork surface) found no CRITICAL/ERROR. **Scoping call made without a separate check-in, flagged here for Animesh's awareness:** the suggested-fix text above raised a council checkpoint per `docs/council/README.md`'s three-condition check, matching the bar BUG-028/BUG-030 used. Skipped it — reasoning this diff is a narrow two-line-per-file constant repoint restoring already-decided S2r behavior (not a new architecture decision, unlike BUG-028/BUG-030's broader pipeline redesigns) — but that's a judgment call worth a second look, not a unilaterally-settled one.

**Closed (B031.4/B031.6, 2026-08-24):** B031.4's manual exit-eligibility review found 5 open legs (3 `overlay_pp`, 1 `overlay_cc`, 1 `overlay_collar_put` — not the 2 originally scoped), zero delta/premium-based signals fired at current market levels. DTE coverage was blocked mid-review by two newly-discovered bugs — **BUG-033** (`_parse_expiry` regex-only, never resolves real numeric instrument keys) and **BUG-034** (`PPOverlayV1`/`CCOverlayV1`'s own `leg_role` filter sets are stale and never match production, so `check_signals()` evaluated zero real PP/CC positions regardless of BUG-033 — found while building the PP-close script below, and the more severe of the two since it runs first). Animesh's resolution for the time-sensitive piece (`NSE_FO|61604`, DTE=1 at discovery): rather than wait on BUG-033/034, closed all 3 open `overlay_pp` legs by hand via `scratch/2026-08-24_close_all_pp_legs.py --execute` (confirmed 0 open `overlay_pp` positions afterward), eliminating the exposure directly instead of reviewing it. The still-open `overlay_cc`/`overlay_collar_put` legs had delta/premium checked clean but DTE remains genuinely unverified — flagged as residual work, to re-check once BUG-033/034 ship. BUG-031 itself — the `strategy_name` defect this entry is about — is fully closed; BUG-033/034 continue as their own open entries.

---
## BUG-034 — `PPOverlayV1.LONG_PUT_ROLES`/`CCOverlayV1.SHORT_CALL_ROLES` are stale pre-S2r role-name sets that never match the real production `leg_role` (`overlay_pp`/`overlay_cc`) — `check_signals()` silently evaluates **zero** real PP/CC positions, independent of BUG-031/BUG-033

| Field | Value |
|---|---|
| Severity | **CRITICAL — more severe than BUG-033, and the actual primary blocker.** `check_signals()` filters `if pos.leg_role not in <ROLES_SET>: continue` *before* any DTE/delta/premium logic runs. For PP and CC, that filter rejects every real position outright — BUG-033's DTE-parsing bug (and even a hypothetical correct DTE parse) was never actually reachable for a single real position this whole session. Collar is unaffected (its role constants already match production). |
| Status | ✅ Fixed (SHA `88df26e`, 2026-08-24). |
| Discovered | 2026-08-24, Animesh — asked for a script to close all open PP legs. Building it against `PPOverlayV1.LONG_PUT_ROLES` (the class's own published role set, the obvious thing to filter on) returned zero matching legs against the real `STRATEGY_OVERLAY` position list, despite `get_positions()` independently confirming 3 open `overlay_pp` legs (`NSE_FO|61604`, `NSE_FO|74009`, `NSE_FO|74046`). Confirmed live via direct call: `LONG_PUT_ROLES = {"long_put", "protective_put", "pp_long_put"}` (`pp_overlay_v1.py`), `SHORT_CALL_ROLES = {"cc_short_call", "short_call", "covered_call"}` (`cc_overlay_v1.py`) — neither set contains `"overlay_pp"`/`"overlay_cc"`, the actual `leg_role` strings `paper_3track_overlay_entry.py`'s `auto_pp_bootstrap()`/`auto_cc_bootstrap()` write (confirmed via `grep leg_role=\"overlay` against that file: lines 1051/1063/1079/1091). Direct positions/filter comparison: `len([p for p in positions if p.leg_role in LONG_PUT_ROLES])` → `0`, `len([p for p in positions if p.leg_role in SHORT_CALL_ROLES])` → `0`, against 3 real open `overlay_pp` + 1 real open `overlay_cc` position. `CollarOverlayV1.SHORT_CALL_ROLE`/`LONG_PUT_ROLE` (singular constants, not sets) are `"overlay_collar_call"`/`"overlay_collar_put"` — already correct, confirmed matching the same grep's `overlay_collar_*` lines. |
| Location | `src/strategy/pp_overlay_v1.py:54` (`LONG_PUT_ROLES`), `src/strategy/cc_overlay_v1.py:54` (`SHORT_CALL_ROLES`) — both module-level sets, used in each class's `check_signals`/`apply_action`/`describe_context`/leg-resolution paths throughout the file. The correct values already exist elsewhere in the codebase: `src/strategy/exit_signals.py:18-19` defines `_OVERLAY_SHORT_CALL_ROLES = {"overlay_cc", "overlay_collar_call"}` and `_OVERLAY_LONG_PUT_ROLES = {"overlay_pp", "overlay_collar_put"}` for `evaluate_roll_overlay()` — those are the real production role names, just never propagated back to `pp_overlay_v1.py`/`cc_overlay_v1.py`'s own filters. |

**Root cause:** same "S2r renamed the leg-role/namespace convention, class-local constants never got the memo" shape as BUG-031 (which was `strategy_name`) and BUG-033 (which was `_parse_expiry`'s key format) — a third independent instance of the same underlying pattern in the same three files. `LONG_PUT_ROLES`/`SHORT_CALL_ROLES` read like pre-S2r role names for a standalone (non-overlay) PP/CC strategy that predates the `overlay_*` naming convention `paper_3track_overlay_entry.py` actually uses. `CollarOverlayV1` escaped this because its role constants (`SHORT_CALL_ROLE`/`LONG_PUT_ROLE`) were apparently authored after — or already using — the `overlay_collar_*` convention.

**Impact:** identical in shape to BUG-031's original finding — zero live exit-signal coverage — but for a *different* reason and, since this filter runs first, it's the reason that actually matters right now: even with BUG-031's `strategy_name` fix live (SHA `ea5df81`), `PPOverlayV1`/`CCOverlayV1.check_signals()` still evaluate exactly zero real positions. The "no exit signals fired" result from today's B031.4 live run (`scratch/2026-08-24_bug031_manual_exit_review.py`) was **not** informative for PP/CC — it never got past this filter to check delta/premium/DTE at all. It *was* informative for the `overlay_collar_put` leg (Collar's role constants are correct), so that leg's "no signal fired" read stands.

**Suggested fix:** repoint `LONG_PUT_ROLES` (`pp_overlay_v1.py`) to `{"overlay_pp"}` and `SHORT_CALL_ROLES` (`cc_overlay_v1.py`) to `{"overlay_cc"}` — a PP-only and CC-only set respectively (not reusing `exit_signals._OVERLAY_LONG_PUT_ROLES`/`_OVERLAY_SHORT_CALL_ROLES` directly, since those deliberately include the Collar variants too for `evaluate_roll_overlay`'s shared use — pulling them in here would make `PPOverlayV1` start processing Collar's put leg, a real behavior change out of scope for this fix). Needs regression tests using the real `"overlay_pp"`/`"overlay_cc"` leg_role strings (the existing unit test suites use `"short_call"`/`"protective_put"` as their default fixture values — see `test_cc_overlay_v1.py`/`test_pp_overlay_v1.py`'s `_make_position()` `leg_role` defaults — which is exactly how this shipped passing despite matching nothing real; same class of gap BUG-031's B031.3 already called out and partially fixed for `strategy_name`, this is the `leg_role` sibling of that same gap). Should ship together with or immediately after BUG-033 (both block PP/CC's live signal path; fix order doesn't matter functionally, but BUG-034 should land first since it's what's actually silently masking BUG-033 right now).

**Immediate manual action, independent of the code fix:** none beyond what BUG-033 already flagged (the `NSE_FO|61604` near-expiry decision) — this bug doesn't change what to do about any specific open leg, it changes how much to trust "no signal fired" as evidence that a leg is fine. Treat every currently-open PP/CC leg as unreviewed by automation until this + BUG-033 both ship; Collar's `overlay_collar_put` leg is the one leg this session's live check actually covers.

**Related:** BUG-031 (same three-file "role rename never propagated" pattern, `strategy_name` axis); BUG-033 (same pattern, `_parse_expiry` axis — and downstream of this bug for PP/CC, since this filter runs first); found while building the PP-close script for Animesh's "close all PP legs" request (`scratch/2026-08-24_close_all_pp_legs.py`), which uses the real `"overlay_pp"` literal directly rather than the buggy `LONG_PUT_ROLES` constant so it isn't blocked by this bug.

**Implementation progress (2026-08-24):** Fix applied — `LONG_PUT_ROLES` (`pp_overlay_v1.py`) →
`{"overlay_pp"}`, `SHORT_CALL_ROLES` (`cc_overlay_v1.py`) → `{"overlay_cc"}`, exactly per the
suggested fix above (deliberately not reusing `exit_signals._OVERLAY_*`, which would pull in
Collar's leg). Tests: every `check_signals()`/`describe_context()` call site in both test files
was given an explicit `leg_role="overlay_pp"`/`"overlay_cc"` override (the shared `_make_position()`
fixture default was deliberately left at the stale value, since `apply_action()`'s tests build
`LegClose(leg_role="protective_put"/"short_call")` and match against `pos.leg_role` via an
independent equality check unrelated to `LONG_PUT_ROLES`/`SHORT_CALL_ROLES` — flipping the shared
default would have broken those). Added `test_check_signals_ignores_stale_leg_role` and
`test_check_signals_evaluates_real_overlay_{pp,cc}_leg_role` to each file. Ran the full two-file
suite (57 tests) in an isolated harness built from the real module code (not the project's own
`.venv`, which is unreachable from the sandbox — see below) — all 57 pass.

Reviewed via a `general-purpose` code-reviewer substitute against the diff (no repo access,
diff + explanation only): 0 CRITICAL / 0 ERROR / 3 WARNING / 2 INFO. WARNINGs, deferred with
reason: (1) `LONG_PUT_ROLES`/`SHORT_CALL_ROLES` and `exit_signals._OVERLAY_*` now encode the same
role strings with nothing enforcing sync — accepted as the deliberate tradeoff this bug's own
suggested fix calls for; a future rename to one and not the other would reproduce this bug's
shape. (2) `_make_position()` fixture defaults left stale rather than flipped — see tests
paragraph above; recommendation was to consider a fixture-drift regression test in a future pass,
not required for this fix. (3) `describe_context()` edge cases and full call-site coverage
unverified beyond `search_code`/`search_graph` (reviewer had no repo access) — no counter-evidence
found.

**Commit deferred — sandbox disk full (2026-08-24):** The device sandbox's `$HOME` partition
(`/sessions/...`, separate from the mounted repo path which has ~222G free) is at 0 bytes
available. This breaks `git commit` itself (`unable to unlink '.git/objects/.../tmp_obj_*'`:
Operation not permitted on temp objects) and independently breaks the `pre-commit` hook (its
sqlite store hits `disk I/O error` even after redirecting `PRE_COMMIT_HOME`/`XDG_CACHE_HOME` into
the mounted repo path — the project's own `.venv/bin/python` symlink also points to
`/opt/anaconda3/bin/python`, unreachable from this sandbox, so the hook can't run under the
project's real venv either). Per Animesh's 2026-08-24 call (asked whether to `--no-verify`,
leave staged for manual commit, or wait for him to free disk — he chose manual commit), the
changes are left `git add`-ed on his machine, uncommitted. Drafted commit message (imperative,
matches `.claude/skills/commit/SKILL.md` format) for whoever runs `git commit`:

```
fix(strategy): repoint LONG_PUT_ROLES/SHORT_CALL_ROLES to real leg_role

Why: PPOverlayV1.LONG_PUT_ROLES and CCOverlayV1.SHORT_CALL_ROLES held
stale pre-S2r role names that never matched the real production
leg_role ("overlay_pp"/"overlay_cc"), so check_signals() silently
evaluated zero real PP/CC positions — more severe than and upstream
of BUG-033, since this filter runs before any DTE/delta/premium logic.
What:
- src/strategy/pp_overlay_v1.py: LONG_PUT_ROLES -> {"overlay_pp"}
- src/strategy/cc_overlay_v1.py: SHORT_CALL_ROLES -> {"overlay_cc"}
- tests/unit/strategy/test_pp_overlay_v1.py: check_signals/describe_context
  call sites now pass leg_role="overlay_pp" explicitly; added
  test_check_signals_ignores_stale_leg_role and
  test_check_signals_evaluates_real_overlay_pp_leg_role
- tests/unit/strategy/test_cc_overlay_v1.py: same pattern for
  leg_role="overlay_cc"; added
  test_check_signals_ignores_stale_leg_role and
  test_check_signals_evaluates_real_overlay_cc_leg_role
Ref: BUG-034 (docs/bugs/bugs.md); reviewed via general-purpose
code-reviewer substitute, 0 CRITICAL/ERROR, 3 WARNING deferred
(see bugs.md BUG-034 Implementation progress note for detail)
```

Committed as SHA `88df26e`. This entry is now archived; B033.5's close-out can proceed per
its own note in `docs/bugs/task.md`.

## BUG-033 — `CCOverlayV1`/`PPOverlayV1`/`CollarOverlayV1._parse_expiry` is regex-only, never resolves real numeric Upstox instrument keys — every DTE-gated exit signal (`ROLL_ELIGIBLE`/`DTE_REVIEW`) has been dead for every live overlay position since these classes existed

| Field | Value |
|---|---|
| Severity | **CRITICAL** — live (paper) risk-management gap, same class as BUG-031 but on the DTE axis specifically. Delta/premium-based signals (`CRASH_MONETIZE`, `LOSS_STOP`, `PROFIT_TARGET`, `DELTA_STOP`) are unaffected — only DTE-gated signals are dead. Directly time-sensitive: `overlay_pp` leg `NSE_FO|61604` expires **tomorrow (2026-08-25)** and, as of discovery, would get no `ROLL_ELIGIBLE` signal at all. |
| Status | ✅ Fixed (SHA `ef1c341`, 2026-08-24) — B033.1-B033.5 all done. Found 2026-08-24, during BUG-031's B031.4 manual exit-eligibility review. Closed same day after BUG-034 landed and the live re-run confirmed real DTE/delta/premium signal coverage end-to-end. |
| Discovered | 2026-08-24, Animesh — ran `scratch/2026-08-24_bug031_manual_exit_review.py` (built for BUG-031's B031.4) live against the real broker/DB now that `strategy_name` is fixed (BUG-031, SHA `ea5df81`). Live chain fetch succeeded (2 `upstox.api_call status_code=200` log lines, both expiries), but `check_signals()` reported "No exit signals fired for any open leg" across all 5 open overlay legs — including `NSE_FO|61604`, whose own instrument-master DTE is 1 (expires 2026-08-25), well inside `evaluate_pp`'s `dte <= 5` `ROLL_ELIGIBLE` threshold. Confirmed live via direct call: `PPOverlayV1()._parse_expiry("NSE_FO|61604")` returns `None` — `_EXPIRY_RE` (`r"NSE_FO\|NIFTY(\d{2}[A-Za-z]{3}\d{4})(PE\|CE)"`) only matches text-format keys like `NSE_FO|NIFTY29MAY2026PE`, never numeric exchange-token keys like `NSE_FO|61604` (the format Upstox's real BOD data actually uses, confirmed via `data/instruments/NSE.json.gz`). `check_signals()`'s own fallback (`dte = ... if expiry is not None else 9999`) then makes the DTE-gated branch permanently unreachable for any real position. |
| Location | `src/strategy/pp_overlay_v1.py:414-421` (`_parse_expiry`), `src/strategy/cc_overlay_v1.py` (own copy, same pattern, used at line ~129/210/367 call sites), `src/strategy/collar_overlay_v1.py` (own copy, used at line ~180/365). Each file defines its own private `_EXPIRY_RE`/`_parse_expiry` rather than sharing one implementation. |

**Symptom, confirmed via direct call (not inferred):** `PPOverlayV1()._parse_expiry("NSE_FO|61604")` → `None`. `_EXPIRY_RE.search("NSE_FO|61604")` → `None` (no match — the pattern requires an embedded `NIFTY<DD><Mon><YYYY><PE|CE>` substring that numeric exchange-token keys never contain). Live `scratch/2026-08-24_bug031_manual_exit_review.py` run against the real broker/DB (5 open legs, 2 live chain fetches, both `status_code=200`) reported zero signals fired for any leg — a false-negative "everything is fine" result masking that DTE-gated evaluation never runs at all for these positions.

**Root cause:** same bug class explicitly named as already-fixed elsewhere in this repo — TODOS.md's 2026-08-13/2026-08-20 entries describe `_open_pp_dte`'s and `paper_3track_overlay_entry.py`'s "regex-only expiry parser never matched real numeric Upstox instrument keys (same bug class as BUG-018/BUG-012)," fixed there via "regex-first/BOD-fallback resolution mirroring `ic_nifty_v2.py::_parse_expiry`." That fix was scoped to the entry-side script; these three live-monitor strategy classes' own independent `_parse_expiry` copies were never swept into it, despite each class already lazily loading an `InstrumentLookup` (`self._resolve_instrument_lookup()`, used elsewhere in the same files for leg lookup and label formatting) that could resolve exactly this case.

**Impact:** for every currently-open CC/PP/Collar overlay position filed under a real numeric instrument key (all 5 confirmed open legs, per BUG-031's B031.4 review), `ROLL_ELIGIBLE` (PP, DTE ≤ 5) and `DTE_REVIEW`/roll-priority DTE checks (Collar) can never fire, regardless of how close to expiry the position actually is. This was masked until now because BUG-031 meant these classes never evaluated real positions at all — BUG-031's fix (SHA `ea5df81`) surfaced this as the next layer down, exactly as intended by B031.3/B031.4's "test with real data, not a unit-level assertion" approach.

**Suggested fix:** repoint each file's `_parse_expiry` to try the existing regex first, then fall back to `self._resolve_instrument_lookup().get_by_key(instrument_key)`'s `expiry` field (epoch ms → `date`) when the regex misses — mirrors the fix already proven for `_open_pp_dte`/`paper_3track_overlay_entry.py` and for `ic_nifty_v2.py::_parse_expiry`. Given three near-duplicate `_parse_expiry`/`_EXPIRY_RE` copies already exist across these files (a maintenance smell independent of this bug), consider factoring one shared helper in `src/strategy/_price_utils.py` (already imported by all three files for `find_option_leg`) rather than patching three copies in place — but the regex-first/BOD-fallback *behavior* fix should not wait on that refactor decision. Needs regression tests using real numeric instrument keys (not the text-format fixtures the existing unit test suites use) asserting a resolvable near-expiry DTE actually fires `ROLL_ELIGIBLE`/`DTE_REVIEW` — same "test with real data" gap B031.3's note already flagged as the class of thing that let bugs like this ship unnoticed.

**Immediate manual action, independent of the code fix:** `overlay_pp` leg `NSE_FO|61604` expires 2026-08-25 (tomorrow) with no auto-roll signal — Animesh should decide whether to roll/close it by hand before expiry rather than wait for this fix to land. This is in addition to, not a substitute for, BUG-031's still-open B031.4 (general exit-eligibility review) — B031.4 can now be re-run once this bug is fixed to get real DTE-based signal coverage, not just delta/premium coverage. **Closed (B033.4, 2026-08-24):** Animesh closed all `overlay_pp` positions manually ahead of expiry, including `NSE_FO|61604` — no roll executed, position exited flat.

**Related:** BUG-031 (this bug was found *during* B031.4, its manual-review task, and depended on BUG-031's fix landing first to be observable at all — StrategyMonitor never evaluated real positions before that); BUG-032 (same `NSE_FO|61604` leg, different defect — P&L reporting drop vs. dead exit signal); TODOS.md 2026-08-13/2026-08-20 entries and DECISIONS.md same dates (the already-fixed sibling instances of this exact bug class in the entry-side script — this is the live-monitor-side instance that fix never covered). **Superseded in priority by BUG-034** — the leg_role filter that bug describes runs *before* `_parse_expiry` in `check_signals()`, so for PP/CC this bug's DTE-parsing gap has been unreachable/unverified the whole time this session; fix BUG-034 first, then re-verify this one is still live for the legs that survive that filter (Collar is unaffected by BUG-034 and was always independently exposed to this DTE bug).

**Implementation progress (B033.1-B033.3, SHA `ef1c341`, 2026-08-24):** added `resolve_option_expiry(instrument_key, lookup)` as a shared helper in `src/strategy/_price_utils.py` (regex-first, then BOD-JSON fallback via `lookup.get_by_key()` → `src.instruments.lookup.parse_expiry` epoch-ms/str normalization → `date.fromisoformat`), mirroring `ic_nifty_v2.py::_parse_expiry`'s proven BUG-018 fix — went with the shared-helper option per the suggested-fix note rather than patching three copies in place. `CCOverlayV1`/`PPOverlayV1`/`CollarOverlayV1._parse_expiry` now each delegate to it via `resolve_option_expiry(instrument_key, self._resolve_instrument_lookup())`; the three per-file `_EXPIRY_RE` module constants (and now-unused `import re` / `datetime` imports) were removed since nothing else in those files referenced them (confirmed via grep before deleting). Tests added: `tests/unit/strategy/test_price_utils.py` (11 new cases covering symbolic-regex path, numeric-key BOD resolution, epoch-ms expiry field, missing/malformed BOD `expiry` field, key-not-in-BOD, and regex-still-wins-when-both-resolvable) plus one numeric-key + one regex-precedence regression test per strategy class in `test_pp_overlay_v1.py`/`test_cc_overlay_v1.py`/`test_collar_overlay_v1.py`, asserting `ROLL_ELIGIBLE`/`DTE_REVIEW` actually fires end-to-end through `check_signals()` for a real `NSE_FO|61604`-style key. Verified against the live repo state (not a stale clone) with a full `pytest tests/unit/` run: 111/111 pass in the four touched files; the broader ~2800-test suite shows zero regressions attributable to this diff (pre-existing 29 failures — missing VIX data dir, one already-dirty unrelated WIP test file — are identical before/after). Independent `general-purpose`+review-substitute pass (B033.3) flagged one plausible defect (unguarded `lookup.get_by_key()` in the BOD fallback) — verified safe (`InstrumentLookup.get_by_key` is a simple linear scan, can't raise) — and one test-coverage gap (missing/malformed BOD `expiry` field), which was closed with the two additional test cases above. B033.4 (manual `NSE_FO|61604` decision, expires 2026-08-25) and B033.5 (close-out, blocked on BUG-034) remain open.

**B033.5 close-out (2026-08-24):** re-ran `scratch/2026-08-24_bug031_manual_exit_review.py` live,
now that BUG-034 (SHA `88df26e`) has landed. 2 open overlay legs found: `overlay_cc`
`NSE_FO|74391` (dte=36, NIFTY 25400 CE 29 SEP 26) and `overlay_collar_put` `NSE_FO|73994`
(dte=36, NIFTY 23500 PE 29 SEP 26). Live option-chain fetch succeeded (status 200). `CCOverlayV1`
fired `PROFIT_TARGET` (ACTION severity, `auto_execute=True`, `auto_action=CLOSE_CC`) — mark 23.9
vs. entry credit 86.725 (well under the 30% profit-target threshold), delta 0.0748. This confirms
the fix chain (BUG-031 strategy_name → BUG-033 DTE-parsing → BUG-034 leg_role filter) now
delivers real, end-to-end exit-signal coverage for a live `overlay_cc` position — first real
signal this whole investigation thread has produced. No signal on the Collar leg, expected: not
DTE-gated at dte=36, and `CollarOverlayV1`'s role constants were never affected by BUG-034. This
also closes BUG-031's B031.4 (general exit-eligibility review) with real DTE coverage, not just
delta/premium coverage as before. **The `PROFIT_TARGET`/`CLOSE_CC` signal on `NSE_FO|74391` is a
real, currently-actionable signal** — the review script is read-only (nothing executed), so this
still needs Animesh's decision on whether/when to close that leg by hand or let the next automated
run act on it.

---

## BUG-032 — `get_position()`'s ambiguous-match fallback silently drops one leg's P&L from the overlay book whenever a role has two open positions — `overlay_pp`'s daily snapshot has excluded the older `NSE_FO|61604` leg's unrealized P&L since 2026-08-20

| Field | Value |
|---|---|
| Severity | **CRITICAL** — live (paper) daily P&L understatement, not a reporting-format gap. `_compute_overlay_leg_totals()` and `_leg_entry_basis()`/`_position_qty()` in `paper_3track_snapshot.py` all call `PaperStore.get_position(strategy_name, leg_role)` with no `instrument_key`; per `get_position`'s own PG-2a ambiguous-match resolution (`src/paper/store.py:844-908`), when more than one position shares a `leg_role` it silently picks the single position with the most recent `entry_date` and logs a WARNING — the *other* open position's P&L is dropped from the aggregate entirely, not merged, not double-counted, just gone. This has been live since the 2026-08-20 `overlay_pp` duplicate-entry event BUG-031 documents (old `NSE_FO|61604` leg, opened 2026-08-11, was never closed; a second `NSE_FO|74009` leg opened 2026-08-20/21 under the same `overlay_pp` role). |
| Status | ✅ Fixed — SHA `67d4010` (2026-08-24). B032.4 (historical backfill) applied 2026-08-24 — see "Backfill (B032.4)" note below. All B032.x items closed. |
| Discovered | 2026-08-24, during the BUG-030 B030.4 backfill: recomputing `overlay_pp`'s historical P&L with `_compute_overlay_pnl_snapshots()` logged `paper_store.get_position_ambiguous leg_role=overlay_pp match_count=2` on every call. Traced live against `data/portfolio/portfolio.sqlite`: `paper_trades` has two open, never-closed `overlay_pp` legs — `NSE_FO|61604` (BUY 65 @ 58.85, 2026-08-11) and `NSE_FO|74009` (BUY 65 @ 94.20 on 08-20, BUY 65 @ 91.80 on 08-21, net 130 lots). Confirmed by reconstructing `paper_leg_snapshots` figures by hand: the 2026-08-21 row (`total_pnl = -65.00`, `ltp = 92.5`) matches `(92.5 - 93.0) * 130` exactly — the weighted-avg-cost and net_qty of `NSE_FO|74009` *alone*, with `NSE_FO|61604`'s 65 lots contributing nothing. Every `overlay_pp` snapshot from 2026-08-20 onward shows the same pattern: the row jumps from tracking the single pre-08-20 leg to tracking only the newer leg, with a step discontinuity in `ltp`/`total_pnl` right at the duplicate-entry date that has no market-move explanation. |
| Location | `scripts/strategies/three_track/paper_3track_snapshot.py`: `_compute_overlay_leg_totals()` (~line 1240-1303, the daily cron snapshot writer — the primary live-impact site), `_leg_entry_basis()` (~line 1136-1149) and `_position_qty()` (~line 1373-1376, both feed `_compute_overlay_pnl_snapshots()`'s %-denominators). Root mechanism: `PaperStore.get_position()` (`src/paper/store.py:844-908`). |

**Symptom:** since 2026-08-20, the daily `overlay_pp` leg snapshot (`paper_leg_snapshots`, `strategy_name=paper_nifty_overlay`, `leg_role=overlay_pp`) and every downstream `overlay_pp`/`pp` P&L row derived from it reflects *only* the newer `NSE_FO|74009` position. The older `NSE_FO|61604` position (65 lots, still open per the trade ledger, no `SELL` ever recorded against it) contributes zero to `unrealized_pnl`, `total_pnl`, or the entry-basis/quantity used for `pnl_inception_pct`/`pnl_1d_pct` — its LTP isn't even fetched (`_compute_overlay_leg_totals`'s `open_keys` list only includes the instrument_key `get_position` happened to return). This is a live understatement of the reported overlay book P&L that has been running for every cron tick since 2026-08-20 (4+ trading days as of discovery), not a one-time historical artifact.

**Root cause:** `get_position(strategy_name, leg_role)` was designed for the case where a role transitions cleanly from one instrument to the next (PG-2a's "roll overlap" comment) and, lacking an `instrument_key` to disambiguate, falls back to "most recent `entry_date` wins" with a WARNING log as the only signal. `_compute_overlay_leg_totals()`, `_leg_entry_basis()`, and `_position_qty()` all call it role-only, never per-instrument — they were written assuming (correctly, until BUG-031's underlying condition) exactly one open position per overlay role at a time. BUG-031 is *why* two positions are simultaneously open (the live monitor never saw `STRATEGY_OVERLAY` positions to close the old leg on roll) — this bug is a distinct, *downstream* defect: even once BUG-031 is fixed and future rolls close old legs promptly, this reporting-layer gap remains latent and will silently reproduce the same P&L drop the next time any overlay role legitimately has two open positions even briefly (e.g. a same-day roll that closes-then-reopens isn't atomic at the snapshot-cron's granularity). The per-role (not per-instrument) shape of `paper_leg_snapshots` and `_OVERLAY_ROLES` more broadly assumes single-position-per-role throughout this file, which this bug is the first confirmed case of that assumption breaking in production.

**Suggested fix — resolved by council 2026-08-24** (`docs/council/2026-08-24_bug032-ambiguous-match-aggregation-vs-hard-fail.md`, unanimous chairman ruling; full detail in `DECISIONS.md`):
hybrid — aggregate correctly across all open instruments per role (was Option a), alert loudly on
the invariant break (deduplicated OFF→ON), never hard-fail (Option b rejected as standalone: PP3's
"no unprotected day" rule deliberately holds two puts on roll day, so `GateViolation` would create
a systematic blackout on every routine roll, not just BUG-031's stuck state), and do **not** widen
`paper_leg_snapshots`' primary key (downstream consumers all expect one role-level row; a
per-instrument companion table is a separate future story if ever needed).

**Implementation progress:**
- Gather `store.get_positions(STRATEGY_OVERLAY)` once, group by `leg_role`; `_compute_overlay_leg_totals`/`_leg_entry_basis`/`_position_qty` consume the grouped representation instead of independently calling `get_position()`.
- Per-instrument LTP fetch + P&L calc, summed at role level — never a blended cost basis/LTP. `paper_leg_snapshots.ltp` must be `NULL` when `n > 1` (not the newest leg's LTP — that's the exact misrepresentation that hid this bug in the first place).
- `get_position()` itself is unchanged (stays PG-2a) — this was a call-site bug, not a store-API bug.
- Anomaly alert: structured log `overlay_pnl.multi_instrument_role` + non-fatal Telegram, first-detection-only (dedup), WARNING for same-day transient / ERROR after N days stuck, recovery log on return to `n ≤ 1`.
- Failure semantics: a missing LTP for one instrument fails that role loudly (ERROR + Telegram), never a silent partial aggregate; unrelated roles/tracks continue regardless.
- Expect (and log explicitly) a step discontinuity in `overlay_pp`'s `pnl_1d_*` on the first post-fix cron run — the correction of the 4+ day understatement, not a market move.
- 13-item regression checklist specified in the council ruling (aggregate-not-newest-only, per-instrument LTP fetch verified, no blended cost/LTP anywhere, realized P&L not double-counted, `ltp is None` when `n>1`, SNAP-5 invariant holds, alert dedup/recovery, single-position regression, unrelated-role continuation, etc.) — B032.3 should implement all 13, not a subset.
- B032.4 (historical backfill) is confirmed a separate follow-up story, not a precondition for shipping the live fix.

**Implementation complete (2026-08-24):** `_compute_overlay_leg_totals()`, `_leg_entry_basis()`,
`_position_qty()` rewritten per the ruling; new helpers `_overlay_positions_by_role()`,
`_overlay_multi_instrument_streak_days()`, `_check_overlay_multi_instrument_alert()` added.
13 tests added to `tests/unit/paper/test_paper_3track_snapshot.py` covering the council's full
regression checklist — Animesh confirmed all pass locally. A general-purpose-agent code review
(the `code-reviewer` substitute per `docs/bugs/prompt.md` step 5, mandatory for financial-logic
changes) against the diff found and fixed one real regression before commit: the anomaly
alert's structured log lines were incorrectly gated on `notifier is not None`, meaning the
entire BUG-032 alerting mechanism would go silent (no log, no Telegram) whenever Telegram
credentials are unset in production — reproducing BUG-032's own "silent failure" shape one
level up, in the fix meant to prevent it. Fixed: logging now always runs; only the
`notifier.send()` call is conditional. A 14th regression test
(`test_multi_instrument_alert_without_notifier_does_not_crash`) locks this in. The same review
also surfaced a second, **pre-existing** (not introduced by this fix) latent issue in
`_compute_overlay_pnl_snapshots`'s `prev_mark_value` calculation — logged separately as BUG-036
rather than fixed inline (touches `pnl_1d_pct` display math with no dedicated test coverage,
out of scope for this fix's time budget). Committed by Animesh directly (sandbox `pre-commit`
venv unreachable over the device bridge all session, same class of blocker as prior sessions'
`.git/index.lock` issues) — SHA `67d4010`.

**Backfill (B032.4, prepared and applied 2026-08-24):** affected window confirmed to be exactly
2026-08-20 and 2026-08-21 — the only two trading days `overlay_pp` had both
`NSE_FO|61604` (opened 2026-08-11) and `NSE_FO|74009` (opened 2026-08-20) open at once.
2026-08-24 needs **no** `paper_leg_snapshots` correction: that day's `total_pnl`
(`-4538.625`) is a same-day open+close of all three `overlay_pp` instruments, realized
entirely through `record_trade()` line items rather than the ambiguous `get_position()`
path — independently re-derived by hand from `paper_trades` (ids 213-215:
`(4.85-58.85)*65 + (83.85-93.00)*130 + (99.85-97.375)*65 = -4538.625`) and it matches
the stored value exactly, confirmed by the backfill script's own sanity check before it
writes anything. 2026-08-24's `pnl_1d_abs` does cascade (it's derived from 08-21's
corrected `total_pnl`) and is included in the backfill.

Corrected values (via `_leg_entry_basis`/`_position_qty`-style aggregation, sourcing
historical LTP from `data/historical/option_chain/eod/2026/08/upstox_<date>_{weekly,monthly}.parquet`
— 61604's 2026-08-25 expiry lives in the weekly bucket, 74009's 2026-09-29 expiry in the
monthly bucket):

| Date | unrealized_pnl (old → new) | ltp (old → new) |
|---|---|---|
| 2026-08-20 | `260.00` → `-2440.75` | `98.2` → `NULL` |
| 2026-08-21 | `-65.00` → `-3155.75` | `92.5` → `NULL` |

Both corrections aggregate the *previously-dropped* `NSE_FO|61604` leg back in
(per-instrument `(ltp − avg_cost) × net_qty`, summed — never a blended cost basis/LTP,
per the council ruling); `ltp=NULL` reflects `n>1` open instruments that day, matching
the fixed live code's own output shape.

Backfill script: `scripts/dev/backfill_bug032_overlay_pp.py` — stdlib-only (no `.venv`
dependency; this session's device bridge cannot reach `.venv/bin/python`, so this writes
via raw parameterized SQL against the same `paper_leg_snapshots`/`paper_overlay_pnl_snapshots`
schema `record_leg_snapshot`/`record_overlay_pnl_snapshot` write, enforcing the same
`total_pnl == unrealized_pnl + realized_pnl` invariant those methods enforce, rather than
importing `PaperStore` directly). Backs up `portfolio.sqlite` first
(`portfolio.bak_<UTC-timestamp>_pre-BUG032.4-backfill.sqlite`, matching BUG-030 B030.4's
naming convention), dry-run by default, only writes with `--apply`. Dry run verified
against a staged copy of the live DB and independently against the live DB itself over
the device bridge — both runs produced identical output to the numbers above.

**Applied 2026-08-24** by Animesh: `python3 scripts/dev/backfill_bug032_overlay_pp.py --apply`.
DB backed up to `portfolio.bak_20260824T131345_pre-BUG032.4-backfill.sqlite` first; a
post-apply dry-run re-run confirmed the stored values now match the "NEW" column above
exactly (OLD==NEW on the re-run). No raw-SQL errors, invariant check passed for every
touched row. B032.4 closed.

**Related:** BUG-031 (root cause of *why* two `overlay_pp` positions are simultaneously open — this bug is the downstream reporting-layer consequence, distinct and independently fixable); BUG-030 (same overlay-reporting file/pipeline, different defect — leg-role grouping vs. position resolution); BUG-036 (pre-existing `prev_mark_value` staleness, surfaced during this bug's code review, still open — see `docs/bugs/bugs.md`); discovered as a side effect of BUG-030's B030.4 backfill (`docs/archive/bugs/bugs.md`).

---

## BUG-036 — `_compute_overlay_pnl_snapshots`'s `prev_mark_value` blends today's live quantity with yesterday's LTP, understating/overstating `pnl_1d_pct`'s denominator

| Field | Value |
|---|---|
| Severity | **MEDIUM** — display/percentage-only defect. `pnl_1d_abs`/`total_pnl` (the absolute rupee figures) are computed additively and are unaffected; only `pnl_1d_pct`'s denominator is wrong, and only on days quantity changed since the prior snapshot. Pre-existing, not introduced by BUG-032's fix — merely surfaced by that fix's code review. |
| Status | ✅ Fixed — 2026-08-24, SHA `d40c3a1`. Symptom (2) (day-over-day quantity mismatch) fixed and backfilled (229/229 rows). Symptom (1) (multi-instrument NULL ltp) remains open — needs the per-instrument companion table the BUG-032 council ruling explicitly deferred. |
| Discovered | 2026-08-24, during the mandatory code-reviewer pass on the BUG-032 fix (`docs/bugs/task.md` B032.5). |
| Location | `scripts/strategies/three_track/paper_3track_snapshot.py::_compute_overlay_pnl_snapshots`, the `prev_mark_value` computation (search `BUG-036` — comment added in place). Feeds off `_position_qty()`, which by design returns *today's* live net quantity. |

**Symptom:** `prev_mark_value = Σ_r _mark_value(prev_by_role[r].ltp, _position_qty(store, STRATEGY_OVERLAY, r))` pairs yesterday's snapshot's `ltp` with today's current `_position_qty()` — not the quantity that was actually open as of that prior snapshot's date. Two distinct manifestations: (1) when yesterday's snapshot was a BUG-032 multi-instrument aggregate, `prev_by_role[r].ltp` is `NULL` by design, so that role contributes `0` to the denominator for one day (understates `pnl_1d_pct`'s denominator); (2) in the ordinary single-instrument case, if quantity changed between yesterday and today (a partial close or add), the denominator blends today's size with yesterday's price — an apples-to-oranges figure with no correctness guard, either direction.

**Root cause:** `PaperStore` does not retain historical per-day open quantity — `paper_leg_snapshots` stores P&L and `ltp` but not `net_qty` — so `_position_qty()` (necessarily) can only report the *current* quantity, and this call site was written assuming quantity is stable day-over-day, which is not guaranteed for any role that can partially close/add (all overlay roles, by design).

**Suggested fix:** Implemented (2026-08-24) — added `net_qty: int | None` to `PaperLegSnapshot`/`paper_leg_snapshots` (schema addition via the file's existing idempotent `ALTER TABLE ... ADD COLUMN` migration pattern, not a re-key — orthogonal to the BUG-032 council ruling's rejection of instrument-keying).

**Implementation progress (2026-08-24):**
- `src/paper/models.py`: `PaperLegSnapshot.net_qty: int | None = None` — `None` means "unknown, pre-fix/pre-backfill row", never conflated with `0` (a valid flat position).
- `src/paper/store.py`: idempotent migration `ALTER TABLE paper_leg_snapshots ADD COLUMN net_qty INTEGER DEFAULT NULL`; `record_leg_snapshot` INSERT/UPSERT, `_row_to_leg_snapshot`, `get_leg_snapshot`, `get_prev_leg_snapshot` all carry `net_qty` through.
- `scripts/strategies/three_track/paper_3track_snapshot.py`: every leg-snapshot write site now populates `net_qty` (`_save_leg_snapshots` for the base leg; `_compute_overlay_leg_totals`'s n==0/n==1/n>1 branches for overlay legs, summing net_qty across instruments in the multi-instrument case — same "sum independently, never blend" discipline as BUG-032's P&L aggregation). `_compute_overlay_leg_totals`'s return tuple grew from 4 to 5 elements; every unpacking call site updated (`_save_overlay_leg_snapshots`, `_overlay_summary_row`'s type sig, the dry-run print loop in `_run`, and two existing tests in `tests/unit/paper/test_paper_3track_snapshot.py`). `_compute_overlay_pnl_snapshots`'s `prev_mark_value` now uses `prev_by_role[r].net_qty` (the quantity actually open on the prior snapshot date) instead of `_position_qty()` (today's live quantity), falling back to the old behavior only when `net_qty is None` (not-yet-backfilled legacy rows).
- `scripts/dev/backfill_leg_snapshot_net_qty.py` (new): one-off script reconstructing `net_qty` for the pre-fix rows from `paper_trades` (`SUM(BUY qty) - SUM(SELL qty)` bounded by `trade_date <= snapshot_date`, same convention as `PaperStore.get_position`) — writes via `PaperStore.record_leg_snapshot`, never raw SQL, per project convention. Idempotent (`--force` to override), `--dry-run` supported, backs up the DB before writing. **Bug found and fixed post-review (2026-08-24):** the script's `_find_target_rows`/`_net_qty_as_of` opened a raw `sqlite3.connect()` and queried `net_qty` directly, but that column only gets created by `PaperStore.__init__`'s migration — since `backfill()` never constructed a `PaperStore` before its first raw query in the `--dry-run` path, running `--dry-run` first (as intended) failed with `sqlite3.OperationalError: no such column: net_qty`. Fixed by constructing `PaperStore(db_path)` once at the top of `backfill()`, unconditionally, before any raw query. **Run against the live DB by Animesh, 2026-08-24** — dry-run output sanity-checked (correct signs: `overlay_cc` -65 short, `overlay_collar_put` +65 long, `overlay_pp` 0/65/130/195 across size changes, `base_etf` flat 5735 throughout), then executed for real. Confirmed via direct query: 229/229 rows populated, 0 remaining NULL.
- Tests added: `tests/unit/paper/test_store.py` (net_qty round-trip including negative/short values, and legacy-NULL-read distinct from 0); `tests/unit/scripts/test_paper_3track_overlay_pnl.py` (day-over-day quantity-change scenario with a real non-NULL `prev.ltp` — the exact gap B036.3 named, asserting the denominator uses yesterday's quantity (5000) not today's live quantity (2500)); `tests/unit/scripts/test_backfill_leg_snapshot_net_qty.py` (happy path reconstructing two rows' historical qty across a partial close, idempotency-without-`--force`, dry-run-writes-nothing).
- Review: `general-purpose` + `REVIEW.md` substitute (real `code-reviewer` subagent not available on this surface) run against the full diff. One WARNING raised (`_save_leg_snapshots`'s `pos.net_qty if pos else 0` risking None/0 conflation) — investigated and dismissed: `PaperStore.get_position` never returns `None` (always returns a flat-default `PaperPosition` with `net_qty=0`), and the ternary matches an existing idiom already used elsewhere in the same file (line ~1043). No CRITICAL/ERROR findings.
- **Not executed:** the device sandbox this session ran in has no working Python environment (broken venv symlink, disk full, no network for pip) — `pytest` could not be run to confirm the new/modified tests actually pass. Confirmed via `python3 -m py_compile` only (syntax-level). Recommend running `python -m pytest tests/unit/paper/test_store.py tests/unit/paper/test_paper_3track_snapshot.py tests/unit/scripts/test_paper_3track_overlay_pnl.py tests/unit/scripts/test_backfill_leg_snapshot_net_qty.py -q` locally before treating B036.3 as verified green.
- Committed by Animesh locally (sandbox `.git/index.lock` was held by a concurrent process at commit time, per `docs/bugs/prompt.md`'s lock-contention clause) — SHA `d40c3a1`.

**Related:** BUG-032 (this bug's `prev_mark_value` call site sits inside BUG-032's fixed block; surfaced during that fix's mandatory code review, not introduced by it).

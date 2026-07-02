# Bug Registry

> One entry per confirmed defect. Do not log speculative issues here — confirm root cause
> first (graph trace / repro), then log. Suspicions belong in `TODOS.md` until confirmed.
> Status values: `🔴 Open` → `🟡 Fix in progress` → `✅ Fixed` (link commit SHA) → `⚪ Won't fix` (with reason).
>
> **Scope:** confirmed defects in live/shipped code (paper trading, cron scripts, live
> gates) — not unimplemented spec items, those are `docs/plan/` story tasks.
>
> **Relationship to root `BUGS.md`:** a bug registry already existed at the repo root
> (`BUGS.md`, single open entry `BUG-001` — `daily_snapshot.py` backfill gap, unrelated,
> low severity). This folder is the canonical home for *new* entries going forward; root
> `BUGS.md` is not migrated, it stays until `BUG-001` is fixed and deleted per its own
> convention. ID numbering is one shared sequence across both files — this registry
> starts at `BUG-002`.

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
| Status | 🔴 Open |
| Discovered | 2026-07-02, verifying IVR=0.24 reading behind `ic_leaps.log` / `ic_yearly.log` rejections |
| Location | `src/backtest/ivr.py::compute_ivr`; `scripts/strategies/ic/ic_entry_gates.py::resolve_ivr` |

**Symptom:** none directly logged — found while independently verifying the IVR=0.24 gate rejection was correct. `resolve_ivr` combines a **live** `vix_today` (from `IntradayMarketStore.get_latest_vix_today()` / `fetch_vix_latest()`) with a **historical** 252-day window loaded from `data/historical/ohlc/india_vix/*.parquet` for the min/max normalization. Pulled the parquet series directly: 2,476 daily rows, 2016-06-27 to **2026-06-25**, zero gaps >5 calendar days anywhere in the decade (history itself is complete and correctly ingested). But the file's `mtime` is 2026-06-26 21:16 and hasn't been touched since — as of today (2026-07-02) the window is missing 5 trading days (Jun 26, 29, 30, Jul 1, Jul 2). `TODOS.md` documents a weekly refresh cron (`refresh_vix.py`, Monday 08:00 IST, 30-day lookback) that should have caught at least through Jun 26 by the Jun 29 run — it visibly didn't.

**Root cause:** `compute_ivr` only validates window *size* (`len(vix_series) < 252 → None`), never window *recency*. A stale-but-full-count series passes silently. The numerator (`vix_today`) is always fresh (live fetch), but the denominator (`window_min`/`window_max`) can be arbitrarily stale as long as the row count clears 252 — there is no check that `window.index.max()` is within N trading days of `today`.

**Why today's 0.24 is very likely still correct despite this:** recomputed the window directly — min **9.15**, max **27.89** over 2025-06-19 to 2026-06-25 (18.74-point range). For the missing 5 days to have changed the percentile, VIX would have had to print a new 1-year high or low, which is a big ask from a level sitting around 13. So this bug did not cause the `ic_leaps`/`ic_yearly` rejections — but it's a latent correctness gap: if VIX had spiked or crushed in the missing days, `resolve_ivr` would gate on a wrong percentile with no error or warning surfaced.

**Suggested fix:** (a) add a recency check in `compute_ivr` or `resolve_ivr` — e.g. `if (today - window.index.max()).days > N: log warning / treat as stale`; (b) separately, verify why the Monday 2026-06-29 `refresh_vix.py` cron run didn't advance the file past 2026-06-25 — check cron logs / whether the cron is actually installed on the live host, not just documented in `TODOS.md`.

**Once fixed, recalculate last week's IVR-gated entries:** any IC entry/rejection decision made between 2026-06-26 and whenever the cron gap is closed was evaluated against this same stale window. After the fix lands (both the recency check and the actual cron/data catch-up), re-run the IVR gate for that period and confirm no entry was wrongly blocked or wrongly allowed — do not assume last week's readings were fine just because this week's happened to be.

**Related:** `BUG-003`'s post-expiry gate and this bug are both in the same "gate evaluated the wrong reference window" family — worth a shared regression-test pattern (assert gate references a *current* or *most-recently-completed* reference point, never a frozen one) once both are fixed.

# Bug Registry

> One entry per confirmed defect. Do not log speculative issues here — confirm root cause
> first (graph trace / repro), then log. Suspicions belong in `TODOS.md` until confirmed.
> Status values: `🔴 Open` → `🟡 Fix in progress` → `✅ Fixed` (link commit SHA) → `⚪ Won't fix` (with reason).

---

## BUG-002 — Option delta sign/magnitude corrupted by put-call misclassification

| Field | Value |
|---|---|
| Severity | **CRITICAL** — feeds the portfolio delta entry gate; wrong sign inverts risk reads |
| Status | 🔴 Open |
| Discovered | 2026-07-02, triaging `ic_weekly.log` entry rejection |
| Location | `src/risk/delta_tracker.py::_position_delta` (lines 140–175) |

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
| Status | 🔴 Open |
| Discovered | 2026-07-02, triaging `ic_monthly.log` / `ic_v2_monthly.log` entry rejection |
| Location | `scripts/strategies/ic/ic_entry_gates.py::_post_expiry_gate` (lines ~68–95) |

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

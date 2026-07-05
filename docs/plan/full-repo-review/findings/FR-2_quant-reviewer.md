# FR-2 — Financial Modeling & Greeks Correctness Review

**Persona:** Quant Reviewer
**Model:** Opus (this session)
**Scope reviewed:** `src/risk/` (delta_tracker.py, entry_gate.py, models.py), `src/paper/` (tracker.py, _utils.py, and callers), `src/strategy/` (exit_signals.py, profit_lock_engine.py, roll_utils.py, ic_nifty_v2.py, cc_overlay_v1.py, pp_overlay_v1.py, collar_overlay_v1.py, auto_close.py, reentry_mixin.py), `src/backtest/ivr.py`, `src/models/options.py`, `REFERENCES.md`, `DECISIONS.md`, plus ground-truth query against `data/portfolio/portfolio.sqlite`. `src/portfolio/tracker.py` + `src/portfolio/store.py` were additionally pulled in because Task Step 5 explicitly names "the live `portfolio/tracker.py` equivalent" as the reconciliation target for the finideas legs — this surfaced the review's most important finding.

Method note on Rule 0: the codebase-memory-mcp graph tools were not available in this session (deferred/not loaded); I used targeted `grep`/`git log`/direct file reads instead of a whole-file `Read` sweep, reading only the functions relevant to Greeks/delta/P&L math rather than entire files where avoidable.

---

## Finding 1 — CRITICAL: `PortfolioStore.get_position()` sets `entry_price = 0` for any leg opened short-first (SELL before any BUY), corrupting downstream unrealized P&L

**File:** `src/portfolio/store.py:616-662` (`get_position`), propagated via `src/portfolio/tracker.py:107-159` (`apply_trade_positions`, line 123: `"entry_price": pos.average_price`).

**Formula as implemented:**
```python
avg_price = (buy_value / buy_qty) if buy_qty > 0 else Decimal("0")
```
`average_price` is computed **only from BUY trades**. If a leg's only trades so far are SELLs (a short position opened by writing/selling first — e.g. a short put or short call that hasn't been closed), `buy_qty == 0` and the function returns `average_price = Decimal("0")`.

`apply_trade_positions` then copies this directly into `Leg.entry_price` unconditionally (no zero-check, no direction-aware branch), and `Leg.pnl_at()` (`src/models/portfolio.py:283-294`) computes:
```python
# direction == SELL:
return (self.entry_price - cp) * self.quantity
```
With `entry_price = 0`, this becomes `-cp * quantity` — the leg's unrealized P&L is reported as the full negative notional of the current market price, not `(sale_price - cp) * quantity`. For a short put sold at ₹90.95 currently marked at, say, ₹60, the correct P&L is `+30.95 × qty`; the system would instead show `-60 × qty` — wrong in both sign and magnitude.

**Ground-truth confirmation (see Reconciliation section):** `finideas_ilts`'s `NIFTY_JUL_PE` leg (`NSE_FO|63896`) is exactly this shape in the live DB right now — SELL 65 @ ₹90.95 on 2026-06-17, no BUY trade yet. `get_position()` on this leg returns `average_price = Decimal("0")` today, live, not a hypothetical.

**Correct derivation:** for a leg with `buy_qty == 0` and `sell_qty > 0`, the "entry price" the P&L calc needs is the weighted average **SELL** price (the credit received), not zero:
```python
avg_price = (sell_value / sell_qty) if buy_qty == 0 and sell_qty > 0 else (buy_value / buy_qty if buy_qty > 0 else Decimal("0"))
```
More precisely, the function conflates two different jobs — "cost basis for a currently-open position" and "which side was traded" — and picks BUY unconditionally regardless of which side is actually open. Contrast with `src/paper/tracker.py:_compute_realized_pnl_by_leg` (lines 50-89), which handles both `SELL→BUY` and `BUY→SELL` correctly and says so explicitly in its docstring ("Works correctly for both short-first and long-first legs"). That is the correct reference implementation living one module over; `portfolio/store.py` was never brought up to the same standard.

**Severity:** CRITICAL — real-money impact, confirmed against a live open position (`finideas_ilts` / `NIFTY_JUL_PE`) as of today (2026-07-05), not a synthetic scenario. Any `compute_pnl()` call against `finideas_ilts` right now returns a materially wrong unrealized P&L for this leg.

**Not currently caught by:** any existing test (searched `tests/` — no test in scope exercises `get_position()` with a SELL-only leg history), nor by `test_pnl_hypothesis.py` (paper-module scope, doesn't touch `src/portfolio/`).

---

## Finding 2 — CRITICAL: `apply_trade_positions` silently drops realized P&L for closed legs — no realized-P&L accounting exists anywhere in `src/portfolio/`

**File:** `src/portfolio/tracker.py:117-118`, `136` (`if pos.quantity == 0: continue  # fully closed — drop from active P&L`), and `src/portfolio/store.py:616-662` / `models/portfolio.py:84-99` (`Position` model has no realized-P&L field at all).

Once `buy_qty == sell_qty` for a leg (fully closed, round-tripped), `apply_trade_positions` drops it from the returned `Strategy.legs` entirely. There is no companion function anywhere in `src/portfolio/` analogous to `src/paper/tracker.py`'s `_compute_realized_pnl_by_leg`/`_compute_realized_pnl`/`get_strategy_realized_pnl` that sums the locked-in gain/loss of closed legs. `PortfolioTracker.compute_pnl()` (line 234) only calls `_build_strategy_pnl(strategy, prices)` against the (now realized-leg-stripped) `Strategy` — it has no realized-P&L term to add, unlike `PaperTracker.compute_pnl()` (`src/paper/tracker.py:131-164`) which explicitly does `total = unrealized + realized`.

**Ground-truth reconciliation (hand-computed vs. system):**

`finideas_ilts` rolled its June legs to July on 2026-06-17:

| Leg | Trades | Realized P&L (hand-computed) |
|---|---|---|
| `NIFTY_JUN_PE` (`NSE_FO\|37805`) | SELL 65 @ 840.00 (2026-01-15) → BUY 65 @ 18.25 (2026-06-17) | `(840.00 − 18.25) × 65 = +₹53,413.75` |
| `NIFTY_JUN_CE` (`NSE_FO\|37799`) | BUY 65 @ 1082.00 (2026-01-15) → SELL 65 @ 1065.15 (2026-06-17) | `(1065.15 − 1082.00) × 65 = −₹1,095.25` |
| **Net realized, this roll** | | **+₹52,318.50** |

**System value:** `PortfolioTracker.compute_pnl("finideas_ilts")` today returns a `StrategyPnL` built from `apply_trade_positions`'s output, which has already dropped both `NIFTY_JUN_PE` and `NIFTY_JUN_CE` (net_qty = 0 for both after the 06-17 roll) with **no realized component added back**. The system's reported total P&L for `finideas_ilts` is short by the full **+₹52,318.50** of real, already-booked profit from this roll — it simply never appears anywhere the strategy's P&L is queried.

**Correct derivation:** `src/paper/tracker.py`'s pattern is the fix shape — track realized P&L per leg from the full trade history (not just the currently-net-nonzero legs) and add it to unrealized P&L for a true total. `src/portfolio/` has no equivalent today.

**Severity:** CRITICAL — this is not an edge case; it is the exact operation (`profit_lock_engine.py`-style roll: close old wings, open new wings at a different expiry) the `finideas_ilts` strategy has already executed once, in the live trade ledger, today's date. Every subsequent roll compounds the same silent loss of realized-P&L visibility.

---

## Finding 3 — INFO (confirmed non-issue): `ProfitLockEngine`'s floor formula seed concern does not hold up

Seed issue asked to verify whether `max(W,W)` in the floor formula was a typo collapsing two different wing-width variables into one. Read `_evaluate_floor_formula` (`src/strategy/profit_lock_engine.py:334-347`) and its caller (`evaluate`, lines 226-228):
```python
new_put_width = short_put_strike - new_put.strike
new_call_width = new_call.strike - short_call_strike
max_width = max(new_put_width, new_call_width)
```
`new_put_width` and `new_call_width` are genuinely two distinct values (computed from different strikes on different sides of the chain) — this is `max(W_put, W_call)`, not a collapsed `max(W, W)`. The formula's semantics (worst-case single-side breach of an iron condor, where only one wing can be tested at expiry) are internally consistent: `worst_pnl = entry_credit − D_cum − D_lock − K − max(W_put, W_call)`, i.e. it assumes the max loss is bounded by whichever wing is wider, which is the correct worst-case bound for a symmetric IC (the underlying cannot breach both wings simultaneously at a single expiry). No bug found here — seed issue does not currently hold. Confirmed via `git log --oneline -10 -- src/strategy/profit_lock_engine.py`: 3 commits, most recent (`f737ee5`) is a wiring commit, and `08148ec` ("fix: address review findings") predates any DECISIONS.md-worthy formula change — no unexplained threshold drift.

---

## Finding 4 — WARNING: `compute_ivr`'s `vix_high == vix_low` is a float `==` comparison on a Greek-adjacent input, undocumented as an explicit exception to the no-float-== rule

**File:** `src/backtest/ivr.py:35`
```python
if vix_high == vix_low:
    return 0.5
```
`vix_high`/`vix_low` are `float(window.min())`/`float(window.max())` from a pandas Series (line 32-33). This is a legitimate use — the branch exists specifically to dodge `ZeroDivisionError` on a flat window, and the docstring explains the design intent (return 0.5 to "signal ambiguity"). It is not a monetary field, so the project's Decimal invariant does not strictly apply. However: `compute_ivr` returns a bare `float`, and every caller in `src/strategy/` (`ic_nifty_v1.py:373`, `ic_nifty_v2.py:1875`, `auto_close.py:320`, `reentry_mixin.py:135`, plus 5 script call sites) must remember to wrap the result in `Decimal(str(...))` before it touches any `ProfitLockConfig`/`ProfitLockEngine` comparison (`ivr >= config.min_ivr`, which is `Decimal`-typed). I verified `ic_nifty_v2.py:1876` (`_load_vix_ivr`) does this correctly (`Decimal(str(ivr_raw))`), but this is a manual discipline enforced at every call site, not a type-system guarantee — a future call site (there are 9 across `src/strategy/` and `scripts/`) that forgets the wrap and instead does raw `float < Decimal` arithmetic will raise `TypeError` at runtime (mixed-type arithmetic, not comparison, is what actually fails), or worse, a future refactor that changes `ProfitLockConfig.min_ivr` to plain `float` reintroduces float-precision risk into an IV-guard gate that unlocks/blocks real profit-lock decisions. Recommend `compute_ivr` return `Decimal` directly (or a `Decimal`-returning wrapper) so the boundary is enforced once, not at 9 call sites.

**Severity:** WARNING — correct today by convention at every checked call site, fragile against the next call site added without the same discipline.

---

## Finding 5 — INFO: `PortfolioDeltaTracker`'s fallback approximation is well-documented and its sign convention is correct, but has apparently never been exercised in anger

**File:** `src/risk/delta_tracker.py:171-232` (`_position_delta`).

Verified the sign convention by hand: for a **short PE** (the common case — selling puts for premium), `net_qty < 0` (or however the store represents a net-short leg; per module docstring "caller has folded in net_qty, lot size, and sign"). The fallback path applies `-net_qty / lot_size` for PE. Short put delta must contribute **positive** (long-bias) delta-equivalent lots — a short put profits when Nifty rises, same directional bias as long the index. If `net_qty` for a short position is stored negative, `-net_qty` is positive → correct sign. If `net_qty` is stored as a positive "quantity sold" magnitude (need to check `PaperPosition.net_qty`'s sign convention at the call site, not fully traceable without the graph tool in this session — flagging as a residual gap, see closing block), the sign could invert. This could not be fully closed out without `search_graph`/`trace_path` on `PaperPosition.net_qty`'s population site, which needs the codebase-memory-mcp tools this session didn't have loaded — recommend a follow-up pass specifically re-verifying this sign convention with graph tooling once available, rather than trusting my read of the docstring alone.

Git log check (`git log --oneline -3 -- src/risk/delta_tracker.py`) shows the fallback path was fixed once (`62ed6ef fix(risk): source real option delta from chain via caller map`) — i.e. this exact fallback approximation is the *residual* path after a real bug was already found and fixed here. No evidence in `tests/unit/risk/test_delta_hypothesis.py` of a specific regression test asserting the fallback's sign for a short-PE scenario specifically (it tests bounds/monotonicity per FR-5's known seed issue, not this specific sign case) — recommend a golden-value test: short 1 lot PE, `net_qty = -65`, `lot_size = 65`, assert `delta_lots == Decimal("1.00")` (full positive delta-lot exposure), not just "some positive value."

**Severity:** INFO/WARNING boundary — flagging as INFO because the documented contract is internally consistent and the fallback already carries a WARNING log and is known-imprecise by design (BUG-002); the residual gap is test coverage, which is FR-5's territory, not a live formula error I can confirm.

---

## Finding 6 — WARNING: Regulatory/Tuesday-expiry consistency — confirmed consistent in scope, but `src/instruments/lookup.py` uses a hardcoded weekday check without the pre/post-April-2026 cutoff guard that `src/models/portfolio.py` and `src/backtest/bhavcopy_ingest.py` both have

**Files:** `src/instruments/lookup.py:341` vs. `src/models/portfolio.py:208-209` and `src/backtest/bhavcopy_ingest.py:48,70`.

`src/models/portfolio.py` and `src/backtest/bhavcopy_ingest.py` both gate the Thursday/Tuesday rule behind an explicit `_NSE_TUESDAY_EXPIRY_CUTOFF = date(2026, 4, 1)` comparison — correct, handles historical (pre-cutoff) data correctly.

`src/instruments/lookup.py:341` (`is_tuesday = d.weekday() == 1`) has **no cutoff guard at all** — it unconditionally treats Tuesday as the weekly expiry day, for any date passed in, past or future. This is not currently a live bug (the docstring at line 340 states this function's purpose is "nearest Tuesday expiry" for the offline BOD instrument lookup, which by nature only serves currently-listed/future instruments — there's no legitimate reason to call it with a pre-April-2026 date). But it is the one file in the three DTE/expiry-computation sites the seed issue named that does **not** carry the same defensive cutoff pattern its siblings do — if `lookup.py` is ever repurposed for historical instrument resolution (e.g. backtest instrument mapping), it will silently mis-tag Thursday-era weeklies as non-matching or Tuesday-era rule as universal. Recommend either a comment stating the "current-instruments-only" assumption explicitly (cheap) or the same cutoff-date guard for defense in depth (per the sibling files' pattern).

**Severity:** WARNING — correct today under current usage, fragile against future reuse of this function outside its current single caller context.

---

## Finding 7 — WARNING: No golden-value test exists anywhere for a Black-Scholes-derived Greek — confirmed still true

Confirmed via `find tests -iname "*hypothesis*" -o -iname "*golden*" -o -iname "*parity*"`: only 3 files exist (`test_pnl_hypothesis.py`, `test_ivr_hypothesis.py`, `test_delta_hypothesis.py`), all property-based (Hypothesis), none golden-value, none parity-check. This confirms FR-2's seed issue #1 and FR-5's overlapping seed issue are both still accurate as of this review — not stale. No put-call-parity test exists for `parse_upstox_option_chain` (`src/client/upstox_market.py:327`) either — confirmed by the same search returning zero "parity" hits. This is the same underlying gap FR-5 is tasked with covering from the coverage angle; flagging here from the correctness angle per the task's cross-reference instruction (see closing block / FR-7 note).

**Severity:** WARNING (not CRITICAL on its own — absence of a test is not itself a wrong result — but it is the reason Findings 1 and 2 above went undetected until a manual ground-truth reconciliation against the live DB, which is not part of any CI gate).

---

## Ground-Truth Reconciliation (Task Step 5)

**Query used** (aggregate/named-column, no `SELECT *`, per root `CLAUDE.md` Rule 1):
```sql
SELECT strategy_name, leg_role, instrument_key, trade_date, action, quantity, price
FROM trades
WHERE strategy_name IN ('finideas_ilts','finrakshak')
ORDER BY trade_date;
```

**Rows returned (real, seeded, live data):**

| strategy | leg_role | instrument_key | date | action | qty | price |
|---|---|---|---|---|---|---|
| finideas_ilts | EBBETF0431 | NSE_EQ\|INF754K01LE1 | 2026-01-15 | BUY | 438 | 1388.12 |
| finideas_ilts | NIFTY_DEC_PE | NSE_FO\|37810 | 2026-01-15 | BUY | 65 | 975.00 |
| finideas_ilts | NIFTY_JUN_CE | NSE_FO\|37799 | 2026-01-15 | BUY | 65 | 1082.00 |
| finideas_ilts | NIFTY_JUN_PE | NSE_FO\|37805 | 2026-01-15 | SELL | 65 | 840.00 |
| finrakshak | NIFTY_DEC_PE | NSE_FO\|37810 | 2026-01-15 | BUY | 65 | 962.15 |
| finideas_ilts | EBBETF0431 | NSE_EQ\|INF754K01LE1 | 2026-04-08 | BUY | 27 | 1386.20 |
| finideas_ilts | LIQUIDBEES | NSE_EQ\|INF732E01037 | 2026-04-08 | BUY | 22 | 1000.00 |
| finideas_ilts | NIFTY_JUL_CE | NSE_FO\|63895 | 2026-06-17 | BUY | 65 | 1245.00 |
| finideas_ilts | NIFTY_JUL_PE | NSE_FO\|63896 | 2026-06-17 | SELL | 65 | 90.95 |
| finideas_ilts | NIFTY_JUN_CE | NSE_FO\|37799 | 2026-06-17 | SELL | 65 | 1065.15 |
| finideas_ilts | NIFTY_JUN_PE | NSE_FO\|37805 | 2026-06-17 | BUY | 65 | 18.25 |

**Hand-computed vs. system, side by side:**

| Metric | Hand-computed (ground truth) | System (`PortfolioTracker.compute_pnl("finideas_ilts")`) | Match? |
|---|---|---|---|
| EBBETF0431 net qty / avg cost | 465 units @ ₹1388.0086 (`(438×1388.12 + 27×1386.20)/465`) | `get_position()`: correctly weighted-average (BUY-only leg, no SELLs — this leg's math is unaffected by Finding 1) → matches `REFERENCES.md`'s documented ₹1388.01 | ✅ Match |
| NIFTY_JUN_PE + NIFTY_JUN_CE realized P&L from the 2026-06-17 roll | **+₹52,318.50** (see Finding 2 table) | **Not represented** — both legs net to zero and are dropped by `apply_trade_positions`; no realized-P&L term exists in `PortfolioTracker` | ❌ Mismatch — Finding 2 |
| NIFTY_JUL_PE (open short, no BUY yet) unrealized P&L basis | Entry credit ₹90.95/unit (short-sale price) | `entry_price = Decimal("0")` per `get_position()` fallback | ❌ Mismatch — Finding 1 |
| NIFTY_JUL_CE (open long) unrealized P&L basis | Entry cost ₹1245.00/unit | `entry_price = 1245.00` (BUY-only leg, `buy_qty>0` branch is correct) | ✅ Match |
| NIFTY_DEC_PE (finideas_ilts + finrakshak, open long, never touched again) | Entry cost ₹975.00 / ₹962.15 respectively | Correct (BUY-only legs) | ✅ Match |

**Conclusion:** 3 of 5 checked legs reconcile correctly. The 2 mismatches are not independent — both stem from the same root cause (`get_position()`'s BUY-only average-price logic, Finding 1) and its downstream consequence for closed legs (Finding 2). Both are real, live, dated positions in the actual portfolio, not synthetic scenarios — this is exactly the "stronger check than a synthetic golden value" the task step called for, and it found something a synthetic test likely would not have (a synthetic test author would probably not think to construct a short-first-no-buy-yet leg, precisely because it's an easy case to overlook when writing the original `get_position()` implementation).

---

## Decimal / float boundary audit (Task Step 3)

Grepped `src/risk/`, `src/paper/`, `src/strategy/`, `src/backtest/ivr.py`, `src/models/options.py` for `float(...)` and `== 0.`/`!= 0.` patterns. Findings:

- `src/backtest/ivr.py` — float end-to-end by design (IVR is a dimensionless ratio, not a monetary field); `vix_high == vix_low` float `==` is intentional and documented (Finding 4, WARNING not CRITICAL).
- `src/strategy/{collar_overlay_v1,cc_overlay_v1,pp_overlay_v1,csp_nifty_v1,auto_close,nifty_track_comparison_v1}.py` — all `float(...)` calls found convert `Decimal` Greeks (delta) or `Decimal`/raw metadata fields to `float` **for logging/notification formatting only** (e.g. `float(call_leg.delta)` passed to a log call or an f-string), not for arithmetic feeding back into a P&L or threshold decision. This is consistent with `LOGGING.md`'s guidance and is not a correctness issue — confirmed by reading each call site's surrounding context rather than assuming from the grep hit alone.
- `src/strategy/executor.py:38` — `(float("inf"), Decimal("4.0"))` — a sentinel tuple, not a computed value; `float("inf")` here is an upper-bound sentinel for a lookup table, not a monetary quantity. No issue.
- No file in scope does float arithmetic (`+`, `-`, `*`, `/`) directly on a monetary field — every monetary/Greek computation I traced (`_position_delta`, `Leg.pnl_at`, `ProfitLockEngine`'s formulas, `OptionLeg` fields) stays in `Decimal` throughout. The float boundary crossings found are all at display/logging edges, which is the correct place for them.

**No new float-arithmetic-on-money violations found** beyond the two already-known conflated issues in Findings 1/2, which are `Decimal`-typed throughout but wrong in *logic*, not in *type*.

---

## Regulatory/Compliance Check (Task Step 6) — Tuesday-expiry consistency

Grepped all of `src/` (excluding `.pyc`) for `Thursday`/`weekday() == 3` and `Tuesday`/`weekday() == 1`:

- `src/models/portfolio.py` — dual-path (pre/post `date(2026,4,1)` cutoff), correct.
- `src/backtest/bhavcopy_ingest.py` — dual-path with the same cutoff constant, correct.
- `src/instruments/lookup.py:341` — Tuesday-only, no cutoff guard (Finding 6, WARNING — not currently wrong, but structurally the odd one out).
- `src/strategy/ic_expiry_config.py:24` — comment only ("Wednesday entry → next Tuesday ≈ DTE 6"), consistent with the post-cutoff rule, no code logic to check.
- `src/strategy/exit_signals.py` — all DTE thresholds (`dte <= 5`, `dte <= 7`, `_BASE_DTE_GUARD = 10`) are expressed as **calendar-day counts**, never as weekday checks — this is the correct design (DTE-based thresholds are automatically expiry-day-agnostic, they don't care whether the expiry lands on Tuesday or Thursday, only how many days away it is). No inconsistency found here.

**Conclusion:** the Tuesday-expiry migration is consistently applied everywhere it's load-bearing in the FR-2 scope. `lookup.py`'s missing guard (Finding 6) is a structural fragility, not a live miscalculation, because its only current caller only ever resolves current/future instruments.

**Regulatory/compliance persona flag:** this check covered only the contract-date/DTE dimension. It did **not** cover margin rules, STT, or tax treatment (explicitly out of scope per the task itself) — flagging per the task's own instruction that no other FR-1 through FR-6 task covers those either. A dedicated Regulatory/Compliance persona is warranted for a follow-up pass if this system moves toward live order execution (currently blocked on static IP per `REFERENCES.md`'s Upstox API Status table), since margin/STT/tax correctness becomes load-bearing the moment real orders are placed, not just paper-tracked.

---

## Closing block

> Persona reviewed as: **Quant Reviewer**.
>
> Missing perspective: this review found a real accounting bug (Findings 1 & 2) in `src/portfolio/` — the manually-tracked long-term hedge book (`finideas_ilts`/`finrakshak`) — by following the task's own instruction to reconcile against `portfolio/tracker.py` as the ground-truth target. That module sits outside this task's stated attach-scope (`src/risk/`, `src/paper/`, `src/strategy/`, `src/backtest/ivr.py`, `src/models/options.py`) and outside every other FR task's stated scope too, as far as I can tell from `stories.md` — FR-3 (Systems Architect) is documents-only, FR-4 (Standards Auditor) is `src/`+`scripts/` but mechanical/grep-shaped not judgment-shaped, FR-5 (Test Auditor) is `tests/`-centric. **No task in this epic has `src/portfolio/` as a primary, judgment-level review target** — it was only touched here as a side effect of the ground-truth reconciliation instruction happening to name it. A dedicated pass explicitly scoped to `src/portfolio/` (store.py, tracker.py, models/portfolio.py) by a Quant Reviewer or Test Auditor persona is warranted — not because this module is more complex than the ones already covered, but because it's the one place real capital (the finideas hedge positions, not paper-traded strategies) is currently tracked, and it just turned out to have the review's single most consequential finding, found somewhat by accident.

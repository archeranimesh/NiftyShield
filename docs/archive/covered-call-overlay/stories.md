# Covered Call Overlay — Story Specs

> One task per session. Find the first unchecked item in `tasks.md`. That is your only task.
> Full implementation rules in `CLAUDE.md` and `REVIEW.md`.
> Strategy parameters are authoritative in `docs/strategies/covered_call_overlay_v1.md`.
> After each task: tick `tasks.md`, append `| SHA: <sha>`, add one line to `TODOS.md`.

---

## CC1 — `src/paper/constants.py`: strategy constant + `compute_max_lots` + tests

**Files to change:**
- `src/paper/constants.py` — add `STRATEGY_CC_OVERLAY` and `compute_max_lots`
- `tests/unit/paper/test_cc_constants.py` — new test file for `compute_max_lots`

**Before any code:**
`get_code_snippet("STRATEGY_CC_OVERLAY")` — confirm it does NOT yet exist (zero results expected).
`get_code_snippet("LOT_SIZE")` — get the current lot size constant value from `src/paper/constants.py`.
`search_graph("compute_max_lots")` — confirm does NOT yet exist.
`git log --oneline -5 src/paper/constants.py` — check recent changes before touching the file.

**What to implement:**

Add to `src/paper/constants.py` (do NOT rewrite the file — targeted `Edit` only):

```python
STRATEGY_CC_OVERLAY = "paper_covered_call_v1"
```

Add after the constant:

```python
def compute_max_lots(
    niftybees_units: int,
    nifty_spot: Decimal,
    niftybees_ltp: Decimal,
    lot_size: int = LOT_SIZE,
) -> int:
    """Return the maximum number of CC lots coverable by pledged NiftyBees units.

    Args:
        niftybees_units: Total NiftyBees units currently pledged as margin collateral.
        nifty_spot: Current Nifty 50 spot price.
        niftybees_ltp: Current NiftyBees ETF LTP.
        lot_size: Nifty lot size (default: LOT_SIZE from constants).

    Returns:
        Maximum lots as a non-negative integer (floored). Zero if holding is insufficient.

    Formula from covered_call_overlay_v1.md:
        max_lots = floor(niftybees_units / (nifty_spot / niftybees_ltp × lot_size))

    Recompute at each annual NiftyBees leg reset. At ~5,725 units and current
    Nifty/NiftyBees ratio, this returns 1 lot.
    """
    if nifty_spot <= 0 or niftybees_ltp <= 0 or lot_size <= 0:
        return 0
    units_per_lot = (nifty_spot / niftybees_ltp) * lot_size
    return int(niftybees_units / units_per_lot)
```

`Decimal` is already imported in `constants.py` — confirm with `search_code("from decimal")` in that file before adding any import.

**Tests (`tests/unit/paper/test_cc_constants.py`):**

- Happy path: `niftybees_units=5725`, `nifty_spot=Decimal("24500")`, `niftybees_ltp=Decimal("280")`, `lot_size=65` → assert result is `1` (verify arithmetic: 24500/280 × 65 ≈ 5691 units per lot; 5725/5691 ≈ 1.006 → floor = 1).
- Scale up: double `niftybees_units` → result is `2`.
- Undersized: `niftybees_units=1000` → result is `0` (holding too small to cover even one lot).
- Zero guard: `nifty_spot=Decimal("0")` → result is `0` (no ZeroDivisionError).
- Zero guard: `niftybees_ltp=Decimal("0")` → result is `0`.
- `STRATEGY_CC_OVERLAY` constant equals `"paper_covered_call_v1"`.

**Commit:** `feat(paper): add STRATEGY_CC_OVERLAY constant and compute_max_lots utility`

---

## CC2 — `scripts/paper_cc_entry.py`: entry helper

**Files to change:**
- `scripts/paper_cc_entry.py` — new script

**Before any code:**
`get_code_snippet("compute_max_lots")` — get exact signature post-CC1.
`get_code_snippet("STRATEGY_CC_OVERLAY")` — confirm constant exists.
`search_code("find_strike_by_delta")` in `scripts/` — get the delta-lookup pattern (CC entry
  uses the same live option chain fetch; do NOT reimplment — import or call as subprocess).
`search_code("IVR\|ivr_at_entry\|compute_ivr")` in `scripts/record_paper_trade.py` — get IVR
  gate pattern used there, same approach applies here.
`search_code("DEFAULT_BOD_PATH\|BOD_PATH")` in `scripts/` — get the BOD path constant.
`git log --oneline -5 scripts/find_strike_by_delta.py` — check recent changes.

**What to implement:**

Entry point: `python -m scripts.paper_cc_entry [--dry-run] [--niftybees-units N] [--niftybees-ltp PRICE]`

```
Usage:
  python -m scripts.paper_cc_entry
  python -m scripts.paper_cc_entry --niftybees-units 5725 --niftybees-ltp 280.50
  python -m scripts.paper_cc_entry --dry-run

Flags:
  --niftybees-units INT   NiftyBees units pledged (default: 5725 — current holding)
  --niftybees-ltp PRICE   NiftyBees LTP in ₹ (required for max_lots calculation;
                           fetched live from Upstox batch endpoint if omitted)
  --dry-run               Print record_paper_trade command only; do not execute
```

**Script flow (implement as `async def run()`):**

1. **IVR gate check**
   - Load VIX data from `data/historical/ohlc/india_vix/` (same path as `record_paper_trade.py`).
   - Compute IVR via `compute_ivr` from `src/backtest/ivr.py`.
   - If IVR < 0.25: print `⚠️  IVR {ivr:.2f} — below entry threshold (0.25). Skip this cycle or override manually.` and exit with code 0 (warn, do not hard-block).
   - If IVR is None (no VIX data): print warning, continue.

2. **Quantity constraint**
   - Call `compute_max_lots(niftybees_units, nifty_spot, niftybees_ltp)`.
   - If result is 0: print `ERROR: NiftyBees holding insufficient to cover even 1 lot at current Nifty/NiftyBees ratio.` and exit 1.
   - Print `Max lots: {max_lots} (covering {niftybees_units} NiftyBees units)`.
   - Use 1 lot for the entry command regardless of max_lots (strategy spec: 1 lot for current holding).

3. **Strike selection**
   - Fetch live Nifty 50 option chain via `parse_upstox_option_chain` (same client as other scripts).
   - Filter CE strikes with |delta| in range [0.12, 0.18] (±3 around 0.15 target).
   - Rank by |delta - 0.15| ascending. Print top 3 candidates:
     ```
     Strike   Delta    IV     LTP    Key
     ------   -----    --     ---    ---
     24800 CE  0.148   14.2%  62.00  NSE_FO|...
     24900 CE  0.138   13.8%  55.00  NSE_FO|...
     24700 CE  0.159   14.6%  70.00  NSE_FO|...
     ```
   - Auto-select the top candidate (closest to 0.15 delta).
   - Print the expiry used (monthly, 30–45 DTE).

4. **Output: dry-run record_paper_trade command**
   - Always print the exact `record_paper_trade.py` command regardless of `--dry-run` flag:
     ```
     python -m scripts.record_paper_trade \
       --strategy paper_covered_call_v1 \
       --leg-role covered_call \
       --underlying "NSE_INDEX|Nifty 50" \
       --option-type CE \
       --strike 24800 \
       --expiry 2026-06-26 \
       --action SELL \
       --qty 65 \
       --notes "15d CC entry; IVR=0.38; delta=0.148; NiftyBees=280.50"
     ```
   - If `--dry-run`: stop here. Do not execute the command.
   - If not `--dry-run`: prompt `Execute? [y/N]` and execute on `y`.

**Error handling:**
- Option chain fetch failure → print error, exit 1.
- No CE strikes in [0.12, 0.18] delta range → print `No CE strikes found in 12–18 delta range. Market may be closed or IVR/chain data stale.` and exit 1.
- `UPSTOX_ACCESS_TOKEN` or `UPSTOX_ANALYTICS_TOKEN` missing → print clear error, exit 1.

**No unit tests for this script** (live I/O). Integration tested via `--dry-run`.

**Commit:** `feat(scripts): paper_cc_entry.py — delta-based CE selection + IVR gate + qty constraint`

---

## CC3 — `scripts/paper_cc_roll.py`: three-trigger exit handler

**Files to change:**
- `scripts/paper_cc_roll.py` — new script
- `tests/unit/paper/test_cc_roll.py` — tests for the three pure trigger-check functions

**Before any code:**
`get_code_snippet("PaperStore")` — get current public API (especially `get_trades`, `close_trade` or equivalent).
`get_code_snippet("PaperTrade")` — get exact field list (entry_price, net_qty, leg_role, closed_at, expiry).
`get_code_snippet("STRATEGY_CC_OVERLAY")` — confirm constant post-CC1.
`search_code("paper_csp_roll")` in `scripts/` — get the CSP roll pattern; CC roll mirrors it.
`git log --oneline -5 scripts/paper_csp_roll.py` — check intent and recent changes.

**What to implement:**

**Three pure trigger functions** (unit-testable, no I/O):

```python
def profit_target_hit(entry_credit: Decimal, current_ltp: Decimal, threshold: float = 0.50) -> bool:
    """Return True if call has decayed to ≤ threshold × entry credit.

    Args:
        entry_credit: Credit collected per unit at entry (positive Decimal).
        current_ltp: Current mark-to-market LTP of the call (positive Decimal).
        threshold: Profit target as fraction of entry credit (default 0.50 = 50% remaining).

    Returns:
        True if current_ltp <= entry_credit × threshold.
    """

def time_stop_hit(entry_date: date, today: date, days: int = 21) -> bool:
    """Return True if calendar days since entry >= days.

    Args:
        entry_date: Date the CC leg was opened (UTC date).
        today: Evaluation date (UTC date).
        days: Time stop in calendar days (default 21).

    Returns:
        True if (today - entry_date).days >= days.
    """

def delta_stop_hit(current_delta: float, threshold: float = 0.40) -> bool:
    """Return True if call delta has crossed the delta stop threshold.

    Args:
        current_delta: Current absolute delta of the call (positive float, 0–1).
        threshold: Delta stop level (default 0.40). Fires when delta >= threshold.

    Returns:
        True if current_delta >= threshold.
    """
```

**Script flow (`async def run()`):**

Entry point: `python -m scripts.paper_cc_roll [--dry-run] [--force]`

```
Flags:
  --dry-run   Show which triggers have fired and what close command would run; do not execute.
  --force     Bypass the "no open CC leg" guard (for manual override).
```

1. Load open CC leg via `PaperStore.get_trades(STRATEGY_CC_OVERLAY)` — filter for open legs
   (`closed_at is None`, `leg_role == "covered_call"`).
2. If no open leg: print `No open covered_call leg for paper_covered_call_v1.` and exit 0
   (unless `--force`).
3. Fetch current LTP + delta for the CC leg instrument key from Upstox option chain.
4. Evaluate all three triggers in order:
   - `profit_target_hit(entry_credit, current_ltp)`
   - `time_stop_hit(entry_date, today)`
   - `delta_stop_hit(current_delta)`
5. Print trigger status for each:
   ```
   Profit target:  ✅ HIT  (LTP ₹31.00 ≤ 50% of entry ₹62.00)
   Time stop:      ⬜ not hit  (DTE from entry: 14 days / 21 limit)
   Delta stop:     ⬜ not hit  (delta 0.22 / 0.40 limit)
   ```
6. If any trigger fires: print the close command:
   ```
   Trigger: profit_target

   python -m scripts.record_paper_trade \
     --strategy paper_covered_call_v1 \
     --leg-role covered_call \
     --action BUY \
     --strike 24800 \
     --expiry 2026-06-26 \
     --qty 65 \
     --close \
     --notes "exit: profit_target; LTP=31.00; entry=62.00"
   ```
7. If `--dry-run`: stop. Otherwise prompt `Execute close? [y/N]`.
8. On `y`: execute the close command. Print confirmation + P&L summary.

**Tests (`tests/unit/paper/test_cc_roll.py`):**

`profit_target_hit`:
- Entry=100, LTP=50 → True (exactly at 50% threshold).
- Entry=100, LTP=49 → True (below threshold).
- Entry=100, LTP=51 → False (above threshold).
- Entry=100, LTP=0 (expired worthless) → True.

`time_stop_hit`:
- Entry 21 days ago → True.
- Entry 20 days ago → False.
- Entry today → False.
- Entry 30 days ago → True.

`delta_stop_hit`:
- delta=0.40 → True (at threshold).
- delta=0.41 → True (above threshold).
- delta=0.39 → False (below threshold).
- delta=0.15 (normal healthy CC) → False.

**Commit:** `feat(scripts): paper_cc_roll.py — profit-target, time-stop, delta-stop exit handler`

---

## CC4 — Docs close

**Files to change:**
- `CONTEXT.md` — add `scripts/paper_cc_entry.py` and `scripts/paper_cc_roll.py` to the scripts description block
- `DECISIONS.md` — one new entry for the CC overlay implementation decision
- `TODOS.md` — session log entry + mark Task 4cc complete in the sequential queue

No code changes. No tests. Targeted `Edit` calls only — never `Write` on these files.

**DECISIONS.md entry to add:**

```
| 2026-05-28 | Covered call overlay implemented as standalone scripts (paper_cc_entry.py + paper_cc_roll.py) rather than extending paper_3track_overlay.py. Reason: strike selection is delta-based (15Δ) vs OTM-based (3–5%) in 3-track; quantity constraint is NiftyBees-unit-driven; strategy name namespace is separate (paper_covered_call_v1 vs paper_nifty_spot/proxy). Overlap with 3-track CC would require fork logic that obscures both strategies. | covered-call-overlay |
```

**Commit:** `docs(covered-call-overlay): update CONTEXT.md, DECISIONS.md, TODOS.md for CC overlay scripts`

# Implementation Plan: `scripts/paper_3track_roll.py`

| Field   | Value                                          |
|---------|------------------------------------------------|
| Status  | Draft — not yet implemented                    |
| Author  | Animesh Bhadra (archeranimesh)                 |
| Date    | 2026-05-04                                     |
| Related | `docs/strategies/nifty_track_comparison_v1.md` |
| Related | `scripts/paper_3track_entry.py`                |

---

## Problem

`paper_3track_entry.py` is entry-only — it writes `BUY` trades for all three base
legs but has no roll awareness. Running it again on roll day would create duplicate
open positions without closing the previous cycle's legs.

A dedicated roll script is needed that:
1. Closes the expiring legs (Futures + Proxy) at current LTP
2. Opens the new-cycle legs (same role names, new instruments)
3. Reports the cycle P&L and running cumulative P&L

---

## What Rolls and What Does Not

| Track | Leg role | Roll? | Reason |
|-------|----------|-------|--------|
| `paper_nifty_futures` | `base_futures` | ✅ Monthly | Nifty futures expire last Thursday every month |
| `paper_nifty_proxy` | `base_ditm_call` | ✅ Monthly | DITM call is a monthly option contract |
| `paper_nifty_spot` | `base_etf` | ❌ Never (monthly) | NiftyBees ETF is perpetual; annual reset only in January |

**Overlay legs** (`overlay_pp`, `overlay_cc`, `overlay_collar_*`) on monthly expiry are
**out of scope for v1.** The script will detect any open overlay legs on the expiring
expiry date and warn the operator to roll them manually via `record_paper_trade.py`.
Quarterly / yearly overlays are not touched.

---

## Cycle Auto-Detection

The `--cycle` parameter is eliminated entirely. The current cycle number is derived
from the DB by counting BUY rows for the base leg — each cycle adds exactly one BUY.

```python
def detect_current_cycle(store: PaperStore, strategy: str, leg_role: str) -> int:
    """Count BUY trades for this leg — each cycle adds exactly one BUY."""
    trades = store.get_trades(strategy, leg_role)
    return sum(1 for t in trades if t.action == TradeAction.BUY)
```

After Cycle 1 entry: `count=1` → closing Cycle 1, opening Cycle 2.
After Cycle 2 entry: `count=2` → closing Cycle 2, opening Cycle 3.
Derives from data, requires no user memory, correct indefinitely.

---

## CLI

```bash
# Preview — default, no DB write:
python scripts/paper_3track_roll.py

# Commit roll to DB:
python scripts/paper_3track_roll.py --confirm

# Force a specific expiry for the new leg (if BOD auto-detect picks wrong):
python scripts/paper_3track_roll.py --expiry 2026-06-26 --confirm

# Debug logging:
LOG_LEVEL=DEBUG python scripts/paper_3track_roll.py
```

No `--cycle` flag. No `--strategy` flag — the script always operates on all three tracks.

---

## Roll Flow (step by step)

### Step 1 — Guard: verify open positions exist

Query `PaperStore.get_position()` for:
- `paper_nifty_futures / base_futures`
- `paper_nifty_proxy / base_ditm_call`

If either `net_qty == 0`, abort with a clear message:
> "No open position for base_futures in paper_nifty_futures. Already rolled or not yet entered."

This makes re-runs safe — the unique-index idempotency on `record_trade` is a
second line of defence, but failing fast at the position check is cleaner.

### Step 2 — Detect cycle numbers

Call `detect_current_cycle()` for each strategy/leg pair. Both must return the
same number (they were entered together). If they differ, warn the operator and
use the minimum — indicates a partially-entered prior cycle.

### Step 3 — Derive new expiry from BOD

Same logic as `paper_3track_entry.py → derive_expiry()`. Prefer 30–45 DTE.
`--expiry` override pins the proxy search to a specific date; futures always use
the BOD front-month independently.

### Step 4 — Fetch close prices (LTP of expiring legs)

Batch `get_ltp_sync([futures_key, proxy_key])`.

Slippage on close side:
- Futures: `max(₹0.25, 0.50 × spread)` — spread is typically sub-₹0.50 at 1 lot,
  so flat ₹0.25 applies in practice. Noted in preview output.
- Proxy (DITM call): `max(₹0.50, 0.50 × spread)` — same as entry, per strategy spec.

Close price = LTP − slippage (selling a long position).

### Step 5 — Compute cycle P&L (preview only, not stored separately)

```
cycle_pnl = (close_price - avg_cost) × net_qty
```

`avg_cost` comes from `PaperPosition.avg_cost` (already computed by `PaperStore.get_position`).

Cumulative realized P&L is read from `_compute_realized_pnl()` **after** the roll
is written — it will include this cycle's contribution automatically because
`_compute_realized_pnl` sums all SELL proceeds − BUY costs per `leg_role` across
all time.

### Step 6 — Fetch new entry prices (same as paper_3track_entry.py)

- **Futures:** look up new front-month key from BOD, fetch LTP via `get_ltp_sync`.
- **Proxy:** run the multi-expiry candidate scan (monthly → quarterly → yearly),
  re-run `auto_select_proxy()` + `compute_proxy_entry_price()` for the new expiry.
  The strike will differ from the prior cycle as Nifty has moved.

### Step 7 — Print preview table

See "Preview Output Format" section below.

### Step 8 — On `--confirm`: write four trades atomically

Two atomic `record_roll()` calls (one per rolling track), using the new
`PaperStore.record_roll()` method:

```python
store.record_roll(futures_close_trade, futures_open_trade)
store.record_roll(proxy_close_trade, proxy_open_trade)
```

Each `record_roll` wraps its SELL + BUY in a single SQLite transaction — a crash
between the two `record_roll` calls leaves one track rolled and one not, which is
detectable on re-run (one `net_qty > 0`, one `net_qty == 0`).

### Step 9 — Print confirmation

Reprint the table with "RECORDED TO DB" header and post-roll cumulative realized
P&L read fresh from the DB.

---

## Preview Output Format

```
════════════════════════════════════════════════════════════════════════
  3-Track Roll | 2026-05-07 | Cycle 1 → 2 | PREVIEW — not yet written
  New expiry: 2026-06-26  DTE=50
════════════════════════════════════════════════════════════════════════

  SPOT (paper_nifty_spot) — NiftyBees ETF is perpetual, no monthly roll
  Open: base_etf  qty=399  avg_cost=₹260.50  unrealized TBD at snapshot

  FUTURES (paper_nifty_futures)
  CLOSE  base_futures  NSE_FO|NIFTY29MAY2026FUT   qty=65  @₹24,452  (slippage=₹0.25)
  OPEN   base_futures  NSE_FO|NIFTY26JUN2026FUT   qty=65  @₹24,523
  Cycle 1 realised:     +₹19,500  [(₹24,452 − ₹24,152) × 65]
  Cumulative realised:  +₹19,500  (cycle 1 only)

  PROXY (paper_nifty_proxy)
  CLOSE  base_ditm_call  NSE_FO|NIFTY29MAY2026CE22000  qty=65  @₹2,418  (spread=₹4.20, slip=₹2.10)
  OPEN   base_ditm_call  NSE_FO|NIFTY26JUN2026CE22500  qty=65  @₹2,061  (δ=0.8923, OI=12,450)
  Proxy gate: ✅ OI=12,450 (min 5,000)  ✅ spread=₹4.20 (max ₹5.00)
  Cycle 1 realised:     +₹12,480  [(₹2,418 − ₹2,226) × 65]
  Cumulative realised:  +₹12,480  (cycle 1 only)

  ────────────────────────────────────────────────────────────────────
  TOTAL cumulative realised (Futures + Proxy): +₹31,980
════════════════════════════════════════════════════════════════════════
  ➜  Re-run with --confirm to write 4 trades (2 SELL + 2 BUY) to DB.
```

After `--confirm`, the same table is reprinted with "RECORDED TO DB" in the header
and cumulative P&L read fresh from the DB (includes the just-written trades).

---

## P&L Calculation — Cumulative

No special work is needed. `_compute_realized_pnl()` in `src/paper/tracker.py`
accumulates all SELL proceeds − BUY costs per `leg_role` across all rows in
`paper_trades`. As long as all cycles use the same `leg_role` names
(`base_futures`, `base_ditm_call`), realized P&L is cumulative automatically.

Example after 3 cycles of Futures:

| Event | trade_date | action | price | qty | Running realized |
|-------|-----------|--------|-------|-----|-----------------|
| Cycle 1 entry | 2026-04-02 | BUY | 24,152 | 65 | — |
| Cycle 1 close | 2026-05-07 | SELL | 24,452 | 65 | +₹19,500 |
| Cycle 2 entry | 2026-05-07 | BUY | 24,523 | 65 | — |
| Cycle 2 close | 2026-06-04 | SELL | 24,890 | 65 | +₹43,355 |
| Cycle 3 entry | 2026-06-04 | BUY | 24,960 | 65 | — |
| (open) | — | — | — | — | +₹43,355 + unrealized |

`_compute_realized_pnl` sees all rows, groups by `leg_role`, and returns
`(sum_of_SELLs - sum_of_BUYs for closed qty)` which equals the cumulative sum.

---

## Infrastructure Changes Required

### 1. `src/paper/store.py` — add `record_roll()`

Mirror of `PortfolioStore.record_roll()`. Wraps SELL + BUY in one SQLite
transaction. If either INSERT fails, the whole transaction rolls back.

```python
def record_roll(self, close_trade: PaperTrade, open_trade: PaperTrade) -> None:
    """Atomically close an existing leg and open a new one.

    Both trades are written in a single SQLite transaction. If either
    INSERT fails, neither is committed — no half-rolled state.
    Re-running is safe: the unique constraint silently skips duplicates.

    Args:
        close_trade: The SELL trade that closes the current cycle leg.
        open_trade: The BUY trade that opens the next cycle leg.
    """
```

### 2. `scripts/paper_3track_roll.py` — new script

Approximately 350–400 lines. Imports heavily from `paper_3track_entry.py`
shared logic (`filter_proxy_candidates`, `auto_select_proxy`,
`compute_proxy_entry_price`, `collect_candidate_expiries`, `derive_expiry`).

To avoid duplication, the shared functions from `paper_3track_entry.py` should be
extracted into a private helper module (`scripts/_3track_helpers.py`) that both
entry and roll scripts import. This refactor is bundled with the roll implementation.

### 3. `tests/unit/paper/test_store.py` — add `record_roll` tests

Two new tests:
- `test_record_roll_writes_both_trades` — happy path: both SELL and BUY appear
  in `get_trades()` after a successful roll.
- `test_record_roll_is_atomic` — simulate INSERT failure on the second trade;
  verify first trade was also rolled back (zero rows in DB).

### 4. `tests/unit/paper/test_paper_3track_roll.py` — new test file

Tests for:
- `detect_current_cycle` — 0 trades → cycle 0; 1 BUY → cycle 1; 1 BUY + 1 SELL → still cycle 1 (only BUYs counted)
- `compute_cycle_pnl` — correct arithmetic
- Guard logic — `net_qty == 0` raises expected error
- Preview output structure (string contains expected fields)

All tests offline (no network, `MockBrokerClient`).

---

## Edge Cases and Guards

| Condition | Behaviour |
|-----------|-----------|
| `net_qty == 0` for any base leg | Abort before any LTP fetch. Print which strategy is already flat. |
| Cycles disagree (Futures=2, Proxy=1) | Warn, use minimum, continue. Operator must reconcile manually. |
| LTP fetch returns 0 for expiring leg | Abort. Instrument may be expired and delisted from LTP API. Operator must record close manually via `record_paper_trade.py`. |
| No proxy candidate in delta band | Abort. Operator uses `--expiry` to force a different expiry. |
| Proxy OI < 5,000 or spread > ₹5 | Warn in output (same gate display as entry script), do not block. Operator confirms anyway. |
| Open overlay leg on same expiry | Print warning listing the leg; do not close it; remind operator to roll manually. |
| `--confirm` + duplicate trade (same date/action) | `ON CONFLICT DO NOTHING` — silently skipped. Preview will show no change on re-run. |

---

## Out of Scope (v1)

- Overlay leg rolling (PP, CC, collar on monthly expiry)
- Spot annual reset
- Recording roll metadata to a separate `paper_rolls` table (could be added later for
  per-cycle analytics without touching existing P&L computation)
- Telegram notification on roll completion (can be wired up post-v1 via the existing
  notifier)

---

## Implementation Sequence

1. Extract shared helpers from `paper_3track_entry.py` → `scripts/_3track_helpers.py`
   + update `paper_3track_entry.py` to import from helpers. Tests must still pass.
2. Add `PaperStore.record_roll()` + 2 tests → commit (phase 1).
3. Implement `paper_3track_roll.py` + its unit tests → commit (phase 2).
4. Update `CONTEXT.md` module tree + `TODOS.md` session log → commit (docs).

Do **not** bundle phases 1–3 into one commit.

---

## Open Questions (resolve before implementation)

1. **Spot unrealized in preview:** Should the roll script fetch NiftyBees LTP to
   show unrealized P&L for the Spot track in the preview, or just skip it? Fetching
   it adds one more LTP call but gives a complete picture. Lean: fetch it, show it,
   but clearly mark it as "no roll action."

2. **`scripts/_3track_helpers.py` vs inline duplication:** Extracting shared code
   is cleaner long-term but adds one more file and a refactor step. Alternative:
   duplicate the ~80 lines of shared functions in the roll script. Lean: extract to
   helpers — the entry script is already 734 lines and will grow further with future
   overlay roll support.

3. **Roll timing for Proxy — close before or at expiry?** The strategy spec says roll
   on "Wednesday after expiry." For an option that expired last Thursday, the
   instrument key may return stale or zero LTP from the Upstox API 6 days post-expiry.
   The safer interpretation: record the close at the **settlement price** (Nifty
   settlement − strike, floored at 0) rather than a live LTP fetch. This requires
   knowing the settlement price, which is published by NSE. Action: operator provides
   `--close-price-proxy` override flag if the LTP fetch returns 0 for the expired
   option. Document this in the script's `--help` output.

# Implementation Plan: Overlay Automation + 3-Track PnL Display

| Field   | Value                                          |
|---------|------------------------------------------------|
| Status  | Draft — not yet implemented                    |
| Author  | Animesh Bhadra (archeranimesh)                 |
| Date    | 2026-05-04                                     |
| Related | `docs/strategies/nifty_track_comparison_v1.md` |
| Related | `scripts/paper_3track_entry.py`                |
| Related | `docs/plan/paper_3track_roll.md`               |

---

## Problem

Three manual pain points:

1. **Overlay entry** requires running `find_strike_by_delta.py` three times per overlay
   type (quarterly / yearly / monthly), manually reading BID/ASK columns, computing
   `spread_pct`, selecting an expiry, and running `record_paper_trade.py` per track. For
   a Collar that is six `find_strike_by_delta.py` calls and six `record_paper_trade.py`
   calls.

2. **Overlay rolling** is explicitly deferred to manual in `paper_3track_roll.md v1`.
   Monthly overlays expire on the same schedule as base legs; quarterly/yearly overlays
   expire independently. There is no script to close and re-enter them.

3. **PnL display** is fragmented. `paper_snapshot.py` shows strategy-total P&L; there
   is no view separating base ("Longs") from overlay ("Protection") contribution, and no
   per-leg delta-from-yesterday.

This document specifies three new scripts and one new DB table to close all three gaps.

---

## Deliverables

| Deliverable | Purpose |
|---|---|
| `scripts/paper_3track_overlay.py` | Overlay entry — full automation |
| `scripts/paper_3track_overlay_roll.py` | Overlay roll — close expired, open new |
| `scripts/paper_3track_snapshot.py` | Combined PnL display (Longs + Protection) |
| `paper_leg_snapshots` table | Per-leg daily PnL store (enables Δ-from-yesterday) |

All three scripts share the same underlying infrastructure:
`PaperStore` → `PaperTracker` → `UpstoxMarketClient`. No new protocol changes.

---

## New DB Table: `paper_leg_snapshots`

### Why

`paper_nav_snapshots` is strategy-total (one row per strategy per day). Computing
"delta from yesterday" per overlay leg requires per-leg granularity. We add a parallel
table.

### Schema

```sql
CREATE TABLE IF NOT EXISTS paper_leg_snapshots (
    strategy_name  TEXT    NOT NULL,
    leg_role       TEXT    NOT NULL,
    snapshot_date  TEXT    NOT NULL,   -- ISO YYYY-MM-DD
    unrealized_pnl TEXT    NOT NULL,   -- Decimal stored as TEXT
    realized_pnl   TEXT    NOT NULL,
    total_pnl      TEXT    NOT NULL,
    ltp            TEXT,               -- LTP at snapshot time (nullable)
    PRIMARY KEY (strategy_name, leg_role, snapshot_date)
) STRICT;
```

### Location

Added to `src/paper/store.py` schema string (`_SCHEMA`). Migration is a single
`CREATE TABLE IF NOT EXISTS` — idempotent, no data loss.

### Read/write API (additions to `PaperStore`)

```python
def record_leg_snapshot(self, snap: PaperLegSnapshot) -> None: ...
def get_leg_snapshot(
    self, strategy_name: str, leg_role: str, snap_date: date
) -> PaperLegSnapshot | None: ...
def get_prev_leg_snapshot(
    self, strategy_name: str, leg_role: str, before_date: date
) -> PaperLegSnapshot | None: ...   # MAX(snapshot_date) < before_date
```

`PaperLegSnapshot` is a new frozen dataclass parallel to `PaperNavSnapshot`.

---

## Script 1: `paper_3track_overlay.py` — Overlay Entry

### What it does

One command records overlays for all applicable tracks in the correct order, with
automatic expiry selection and confirmation before any DB write.

```
python -m scripts.paper_3track_overlay \
    --overlay pp \
    --date 2026-05-07 \
    [--tracks spot futures proxy]   # default: all applicable
    [--yes]                          # skip interactive confirmation
    [--dry-run]                      # print proposed trades, no DB write
```

### Overlay menu enforcement (from strategy doc)

| `--overlay` | Applied to tracks | Blocked on |
|---|---|---|
| `pp` | spot, futures, proxy | — |
| `cc` | spot, proxy | futures (hard block, script exits with error) |
| `collar` | spot, futures, proxy | — |

If `--tracks futures` is passed with `--overlay cc`, the script prints:

```
ERROR: Covered call is BLOCKED on paper_nifty_futures (synthetic short put risk).
       Use --overlay collar to add protection alongside the covered call.
```

And exits 1 without touching the DB.

### Expiry selection algorithm (per strategy doc §Overlay Expiry Selection)

For each track × overlay leg:

```
candidates = [quarterly_expiry, yearly_expiry, monthly_expiry]
for expiry in candidates:
    rows = fetch_chain(underlying, expiry)
    strike = find_target_strike(rows, overlay_type, spot)
    spread_pct = (ask - bid) / mid * 100
    if spread_pct <= 3.0 and oi >= OI_MIN[overlay_type]:
        selected = expiry
        break
else:
    selected = monthly_expiry   # fallback
```

For a Collar, the gate is `max(put_spread_pct, call_spread_pct) ≤ 3.0` on the
same expiry. If no single expiry passes for both legs, fall back to monthly.

### Strike targeting (replacing manual delta-range guessing)

Rather than a fixed delta range, the script computes the target strike directly from
spot price and selects the closest listed strike:

| Overlay leg | Method | Typical |delta| |
|---|---|---|
| PP (protective put) | `floor(spot × 0.90)` rounded to nearest 50 | 0.05–0.15 |
| CC (covered call) | `ceil(spot × 1.04)` rounded to nearest 50 | 0.20–0.35 |
| Collar put | same as PP | 0.05–0.15 |
| Collar call | same as CC | 0.20–0.35 |

The exact percentage bounds (8–10% OTM for PP, 3–5% OTM for CC) are defined as
module-level constants and match the strategy doc. The actual delta is displayed in
the confirmation table for review — it is informational, not a gate.

### Confirmation display (before any DB write)

```
Overlay: Protective Put  |  Date: 2026-05-07
Expiry selected: 2026-06-26 (quarterly, DTE=50)

  Track       Strategy               Leg          Strike  Side  Qty  Price   spread_pct  OI
  ─────────────────────────────────────────────────────────────────────────────────────────
  Spot        paper_nifty_spot       overlay_pp    21700   PE    65   ₹220.50   1.8%   8,200
  Futures     paper_nifty_futures    overlay_pp    21700   PE    65   ₹220.50   1.8%   8,200
  Proxy       paper_nifty_proxy      overlay_pp    21700   PE    65   ₹220.50   1.8%   8,200

Proceed? [y/N]:
```

For a Collar, both legs appear in the same table. The call and put are confirmed
together — never one without the other.

With `--yes`, the confirmation prompt is skipped (for cron / scripted use).

### Leg role naming (per strategy doc)

| Overlay | Leg roles written |
|---|---|
| `pp` | `overlay_pp` |
| `cc` | `overlay_cc` |
| `collar` | `overlay_collar_put`, `overlay_collar_call` |

The `--notes` field written automatically includes: overlay type, expiry selected,
DTE at entry, spread_pct, OI, and whether it is a fallback expiry. This satisfies
the strategy doc logging requirement without operator effort.

### Safety checks before recording

1. Query `paper_trades` for an existing open `overlay_pp` (or `overlay_cc` /
   `overlay_collar_*`) on the target strategy. If an open position exists with a
   **different expiry**, warn and require `--force` to proceed. This prevents
   accidentally stacking a second PP on top of a live one.

2. For `collar`: verify no pre-existing open `overlay_collar_call` without a paired
   `overlay_collar_put`, and vice versa, before writing either leg.

3. Futures + CC guard: enforced at argument parse time, not DB query time.

---

## Script 2: `paper_3track_overlay_roll.py` — Overlay Roll

### What it does

Closes expiring overlay legs and opens replacement legs in one session, with the same
expiry-selection and confirmation logic as the entry script.

```
python -m scripts.paper_3track_overlay_roll \
    --overlay pp \
    --date 2026-05-28         # roll execution date (usually expiry Wednesday)
    [--tracks spot futures proxy]
    [--yes]
    [--dry-run]
```

### Roll detection

The script queries `PaperStore.get_trades(strategy, leg_role)` for each track and
identifies legs whose instrument key's embedded expiry date falls on or before
`--date`. It does not require the user to pass the old expiry.

```python
def _find_expiring_overlay(
    trades: list[PaperTrade], roll_date: date, leg_role: str
) -> list[PaperTrade]:
    """Return trades whose instrument key expires on or before roll_date."""
    ...
```

Instrument key expiry is parsed from the key string pattern
`NSE_FO|NIFTY<DDMMMYYYY>PE` / `CE`. For equity legs (NiftyBees — no expiry),
this function returns empty.

### Roll sequencing

For each expiring overlay leg per track:

```
1. Fetch current LTP  →  record CLOSE trade (SELL for long PP, BUY for short CC)
2. Run expiry selection for new cycle (same algorithm as entry script)
3. Show close + open in one confirmation table
4. On confirm: record both trades atomically (both or neither)
```

"Atomically" here means: both trades are constructed and validated before either is
passed to `PaperStore.record_trade`. If the second fails validation, the first is
rolled back via a delete (SQLite, single-file, no distributed transaction needed).

### Collar roll atomicity

A collar roll is four trades: close put, close call, open put, open call. All four
are validated before any is written. If any fails, none are written.

### Long-dated overlay independence

Quarterly and yearly overlays do not roll on the same schedule as base legs.
The roll script runs a DTE check: if an overlay leg's remaining DTE > 5, it is
skipped with a notice. Only legs with DTE ≤ 5 are included in the roll.

This means:
- A quarterly PP entered at 50 DTE is not touched during the monthly base roll at ~22 DTE.
- It appears in the roll script output for the cycle where its DTE falls below 5.

The operator can also roll early (DTE > 5) by passing `--force`. This is for cases
where spread_pct on the remaining position has widened and the quarterly premium is
near zero.

### Cycle PnL report after roll

Matching the format in `paper_3track_roll.md`:

```
Overlay roll complete: overlay_pp  |  2026-05-28

  Track   Closed at  Opened at  Overlay P&L (cycle)  Cumulative overlay P&L
  ─────────────────────────────────────────────────────────────────────────
  Spot      ₹85.00    ₹220.50        -₹8,775                 -₹8,775
  Futures   ₹85.00    ₹220.50        -₹8,775                 -₹8,775
  Proxy     ₹85.00    ₹220.50        -₹8,775                 -₹8,775
```

Overlay P&L (cycle) = realized gain/loss from the closed leg in this cycle only.
Cumulative overlay P&L = all realized + current open unrealized across all cycles.

---

## Script 3: `paper_3track_snapshot.py` — Combined PnL Display

### CLI

```
python -m scripts.paper_3track_snapshot \
    [--date YYYY-MM-DD]          # default: today
    [--save]                      # write paper_leg_snapshots rows to DB
    [--underlying <price>]        # Nifty spot (for NEE % display)
```

`--save` writes both `paper_nav_snapshots` (strategy-total, existing) and
`paper_leg_snapshots` (per-leg, new). Run with `--save` from the EOD cron so that
tomorrow's run can compute Δ from yesterday.

### Output format

```
════════════════════════════════════════════════════════════════
  3-Track PnL  |  2026-05-07  |  Nifty ₹24,350
════════════════════════════════════════════════════════════════

LONGS (base positions, cumulative from cycle 1)
  NiftyBees  ₹ +52,650   Δ +1,820  (base_etf)
  Futures    ₹ +61,100   Δ +2,340  (base_futures, all cycles)
  DITM Call  ₹ +38,900   Δ +1,560  (base_ditm_call, all cycles)

────────────────────────────────────────────────────────────────
PROTECTION
────────────────────────────────────────────────────────────────

🛡 Protective Put  |  Expiry: 2026-06-26 (DTE 50)
  NiftyBees Δ       +1,820      (base contributes)
  overlay_pp Δ        +320
  ────────────────────────────────────────────────
  Net Spot           +2,140  ✅ Protected

  overlay_pp Δ (Futures track)    +320   [overlay only — base excluded]
  overlay_pp Δ (Proxy track)      +320   [overlay only — base excluded]

🛡 Collar  |  Expiry: 2026-06-26 (DTE 50)
  NiftyBees Δ         +1,820    (base contributes)
  collar_put Δ          +420
  collar_call Δ         -680
  ────────────────────────────────────────────────
  Net Spot             +1,560  ✅ Protected

  collar_put Δ (Futures)    +420  collar_call Δ (Futures)  -680
  Net Futures overlay        -260  [overlay only — base excluded]

════════════════════════════════════════════════════════════════
FRAMEWORK  |  NEE: ₹15,82,750
  Total PnL (all tracks + overlays)   ₹ +1,45,210
  Return on NEE                            +9.18%
  Cycle max drawdown                       -2.31%
════════════════════════════════════════════════════════════════
```

### "Total PnL from initial position" — how it works

`_compute_realized_pnl` aggregates all trades with the same `leg_role` across all
cycles (rollovers use the same leg_role). `_compute_leg_unrealized_pnl` adds the
current open position's mark. Their sum is the "from initial position" total — the
existing tracker already does this correctly. No change to tracker logic.

### "Δ from yesterday" — per leg

```python
async def _leg_delta(
    store: PaperStore,
    strategy: str,
    leg_role: str,
    today_pnl: Decimal,
    today: date,
) -> Decimal:
    prev = store.get_prev_leg_snapshot(strategy, leg_role, before_date=today)
    if prev is None:
        return Decimal("0")
    return today_pnl - prev.total_pnl
```

On first run (no prior snapshot), Δ shows 0 — correct, because nothing has changed.

### Protection section — base inclusion rule

| Track | Overlay type | Base Δ shown in Protection? |
|---|---|---|
| `paper_nifty_spot` | any | ✅ Yes — NiftyBees is the primary capital deployment |
| `paper_nifty_futures` | any | ❌ No — futures base excluded; overlay Δ shown inline |
| `paper_nifty_proxy` | any | ❌ No — DITM base excluded; overlay Δ shown inline |

This matches the user requirement: "PnL for protection should never use the future
or DITM for comparison." The overlay legs on Futures and Proxy are shown as a
separate line (not netted with their base), so their contribution to cost-of-protection
is visible without distorting the base-vs-protection comparison.

### ✅ / ⚠️ / ❌ protection status logic

| Condition | Label |
|---|---|
| Net Spot (base + overlay) Δ > 0 | ✅ Protected |
| Net Spot Δ ≤ 0 but overlay Δ > 0 | ⚠️ Partial (overlay paid, base fell more) |
| Net Spot Δ ≤ 0 and overlay Δ ≤ 0 | ❌ Unprotected (both legs losing) |

The ❌ case is not a kill signal — it means Nifty moved up (CC / collar call loses,
base gains, but the net is shown in LONGS). These labels are display signals, not
trading signals.

### Proxy delta alert (from strategy doc)

```
  DITM Call  ₹ +38,900   Δ +1,560   delta=0.88 [OK]
  DITM Call  ₹ +38,900   Δ +1,560   delta=0.62 [⚠️  WARNING <0.65 — monitor]
  DITM Call  ₹ +38,900   Δ +1,560   delta=0.38 [🔴 CRITICAL day 1 of 3 — exit protocol active]
```

Delta is fetched from the live option chain for `base_ditm_call`'s instrument key.

---

## Execution Flow — Entry Day

```
1. paper_3track_entry.py       → records 3 base legs (existing script)
2. paper_3track_overlay.py \
       --overlay collar \
       --date <entry_date>     → queries 3 expiries × 2 legs × 3 tracks
                                  auto-selects expiry, confirms, records 6 trades
3. paper_3track_overlay.py \
       --overlay pp \
       --tracks futures proxy \
       --date <entry_date>     → records PP-only on Futures + Proxy
4. paper_3track_snapshot.py \
       --save                  → writes first leg snapshots (Δ = 0)
```

## Execution Flow — Monthly Roll Day

```
1. paper_3track_roll.py        → closes + opens base legs (Futures + Proxy)
2. paper_3track_overlay_roll.py \
       --overlay pp            → closes monthly PP (DTE ≤ 5), opens new cycle
   paper_3track_overlay_roll.py \
       --overlay collar        → closes monthly collar (DTE ≤ 5), opens new cycle
   [quarterly overlays skipped automatically — DTE > 5]
3. paper_3track_snapshot.py --save   → records post-roll PnL snapshot
```

## Execution Flow — Daily (EOD cron, 3:50 PM IST)

```
python -m scripts.paper_3track_snapshot --save --underlying <nifty_spot>
```

This is the only daily operation needed. Entry and roll scripts are manual, run
on the specific calendar dates.

---

## Key Design Constraints

**Leg role stability across rolls.** The overlay leg roles (`overlay_pp`,
`overlay_cc`, `overlay_collar_put`, `overlay_collar_call`) must never change across
roll cycles. The "total PnL from initial position" calculation relies on all trades
for a given `leg_role` being aggregated by `_compute_realized_pnl`. If a roll
script used a new leg_role per cycle (e.g., `overlay_pp_cycle2`), cumulative PnL
would break.

**No mixing of overlay and base in the same `leg_role`.** The protection split in
the snapshot works by filtering leg_roles. Any leg whose role starts with `overlay_`
is classified as an overlay leg; `base_*` legs are classified as base legs.

**Collar atomicity is non-negotiable.** `paper_3track_overlay.py` and
`paper_3track_overlay_roll.py` must never write one collar leg without the other.
If the DB write of the first succeeds but the second fails, the surviving single leg
is immediately deleted (or a roll-back trade is inserted) before the script exits.
This mirrors the strategy doc: "Never enter the covered-call leg of a collar without
simultaneously entering the protective put."

**Futures CC guard is hard-coded, not configurable.** There is no `--force-cc-on-futures`
flag. If this constraint needs to change, it requires a council decision and a
`DECISIONS.md` entry first.

**`--yes` flag is for automation, not for skipping safety checks.** The blocked
combination checks (Futures + CC, missing paired collar leg) run regardless of
`--yes`.

---

## Implementation Order

Given dependencies:

```
Phase A — DB model (no scripts, no UI):
  1. Add PaperLegSnapshot dataclass to src/paper/models.py
  2. Add paper_leg_snapshots table to src/paper/store.py _SCHEMA
  3. Add record_leg_snapshot / get_leg_snapshot / get_prev_leg_snapshot to PaperStore
  4. Tests for all three new store methods (happy path + edge cases)
  Commit: feat(paper): add paper_leg_snapshots table and PaperStore read/write API

Phase B — Overlay entry script:
  5. scripts/paper_3track_overlay.py
  6. tests/unit/paper/test_paper_3track_overlay.py
  Commit: feat(scripts): paper_3track_overlay entry automation

Phase C — Snapshot display:
  7. scripts/paper_3track_snapshot.py
  8. tests/unit/paper/test_paper_3track_snapshot.py
  Commit: feat(scripts): paper_3track_snapshot combined PnL display

Phase D — Overlay roll script:
  9. scripts/paper_3track_overlay_roll.py
  10. tests/unit/paper/test_paper_3track_overlay_roll.py
  Commit: feat(scripts): paper_3track_overlay_roll automation

Phase E — Docs:
  11. Update CONTEXT.md + CONTEXT_TREE.md
  12. Update TODOS.md
```

Phase A must complete before B, C, or D. B, C, D can be parallelised once A is done.
Start with Phase A.

---

## Open Questions (resolve before implementation)

1. **OTM% constants** — strategy doc says "8–10% OTM for PP" and "3–5% OTM for CC".
   Should these be configurable via CLI args, or fixed constants matching the strategy
   doc? Recommendation: fixed constants (matching spec), with a `--pp-otm-pct` override
   for experimentation. Decision needed before Phase B.

2. **OI threshold for PP** — strategy doc says OI ≥ 5,000 for the Proxy base DITM call.
   For overlay PPs (8–10% OTM), what is the minimum acceptable OI? Illiquid deep OTM
   puts on monthly expiry can have OI < 500. Recommendation: OI ≥ 1,000 for overlays
   (monthly), ≥ 500 for quarterly (institutional hedging OI patterns differ). Confirm.

3. **Snapshot script replaces or extends `paper_snapshot.py`?** — Two options: (a)
   `paper_3track_snapshot.py` is a new script that runs in addition to `paper_snapshot.py`
   (separate concerns), or (b) it replaces `paper_snapshot.py` for the 3-track strategies.
   Recommendation: new script — `paper_snapshot.py` remains general-purpose. Confirm.

4. **`--save` as default on cron?** — Should the cron always save leg snapshots, or only
   on explicit `--save`? Recommendation: `--save` opt-in (explicit) to prevent accidental
   snapshot pollution during ad-hoc runs. Confirm.

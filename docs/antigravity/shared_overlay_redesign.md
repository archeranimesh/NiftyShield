# Shared Overlay Redesign

**Status:** Draft  
**Date:** 2026-05-04  
**Supersedes:** `3track_overlay_implementation_plan.md` Phases B–D (overlay entry/snapshot/roll only; Phase A store API unchanged)

---

## Problem

The current implementation records one overlay trade **per track** per overlay type:

- PP → 3 `paper_trades` rows (one per strategy)
- CC → 2 rows (futures blocked at write time)
- Collar → 6 rows (2 legs × 3 tracks)

This is wrong because:

1. **P&L is tripled.** In reality you buy one PP, one CC, one collar. The snapshot shows 3× the actual premium cost/gain.
2. **Roll is tripled.** Rolling a PP closes and opens 3 lots instead of 1.
3. **CC block is in the wrong layer.** The "futures + CC = synthetic short put" rule is a *display* concern — you hold one CC against your spot/proxy underlying. The entry script shouldn't enforce a write-time block based on track count.
4. **Asymmetric CC display.** 2 CC rows (spot + proxy) looks broken vs 3 PP rows.

---

## Design

### New constant

```python
# scripts/paper_3track_overlay.py and paper_3track_overlay_roll.py
OVERLAY_STRATEGY = "paper_overlay_shared"
```

All overlay trades (`overlay_pp`, `overlay_cc`, `overlay_collar_put`, `overlay_collar_call`) are recorded under **one strategy name** — `paper_overlay_shared`. The three per-track strategy names (`paper_nifty_spot/futures/proxy`) hold **base legs only**.

### Overlay leg roles (unchanged)

```
overlay_pp              BUY PE  — protective put
overlay_cc              SELL CE — covered call
overlay_collar_put      BUY PE  — collar put leg
overlay_collar_call     SELL CE — collar call leg
```

---

## File-by-file changes

### A. `scripts/paper_3track_overlay.py`

**Remove:**
- Per-track loop over `effective_tracks` for overlay trade building.
- `_CC_BLOCKED_TRACKS` write-time guard (`sys.exit` if futures in tracks).
- The `existing` expiry check per (strategy, leg_role) — now just (OVERLAY_STRATEGY, leg_role).
- `--tracks` CLI argument entirely. With a single shared overlay strategy there is no concept of "apply to these tracks" at entry time — that is a display-layer concern resolved by `show_overlay` in the snapshot script. Removing `--tracks` also eliminates the need for `_TRACK_MAP` and `effective_tracks`.

**Add:**
- `OVERLAY_STRATEGY = "paper_overlay_shared"` constant.
- Single `_check_existing_overlay(store, OVERLAY_STRATEGY, leg_role)` call before writing.
- `--date` defaults to `date.today()` (no longer `required=True`). When the default is used, print a visible warning to stderr: `WARNING: --date not provided — defaulting to today: YYYY-MM-DD. Pass --date YYYY-MM-DD to override.` Pass an explicit date only when entering a trade retroactively (e.g. you decided intraday but are running the script post-market).

**Result:** Entry script writes 1 row for PP, 1 for CC, 2 for collar (put + call). No track loop.

**CLI changes:**
- `--tracks` removed entirely. No per-track loop means no track targeting at entry time.
- `--date` made optional; defaults to `date.today()` with a stderr warning:
  `WARNING: --date not provided — defaulting to today: YYYY-MM-DD. Pass --date YYYY-MM-DD to override.`
  Pass an explicit past date only when entering retroactively (e.g. decision made intraday, script run post-market).
- No `--spot` argument. Spot is fetched live from `underlying_spot_price` in the option chain payload. A CLI override would risk stale values silently misplacing the OTM band.

**Candidate display — same ranked table format as `paper_3track_entry.py`:**

One candidate table is printed per leg role (PP → one PE table; CC → one CE table; Collar → one PE table + one CE table). Format mirrors the proxy candidate block in `print_preview`, with `OTM%` replacing `Delta` as the selection axis:

```
  PP candidates — PE  8–10% OTM  (showing top 10 of N, ranked: round-100 first, spread↑ OI↓)
   Rk  Expiry         Strike  Type    OTM%         OI       Bid       Ask    Sprd   R
  ────────────────────────────────────────────────────────────────────────────────────────
    1  2026-06-26      21500    PE    8.9%    1,200,000    250.10    255.40   ₹5.30   ✓ ◀
    2  2026-06-26      21000    PE    9.8%      890,000    210.20    216.00   ₹5.80   ✓
   ...
  ──────────────────────────────────────────────────────────────────────────────────────
  Selected  expiry=2026-06-26  key=NSE_FO|XXXXX
  OI gate    : ✅ PASS  OI=1,200,000 (min 5,000)
  Spread gate: ✅ PASS  spread_pct=2.1% (max 3.0%)
════════════════════════════════════════════════════════════════════════
```

Ranking key (identical to `_rank_overlay_key` — ascending, lower wins):
1. `is_non_round` — multiples of 100 preferred (0) over 50-increment strikes (1)
2. `spread_bucket` — `int(spread / 2)` — tighter ₹2 spread tier wins
3. `-oi` — highest OI wins within the same spread tier
4. `spread` — exact spread tiebreaker inside a bucket
5. `otm_dist` — proximity to target OTM (9% for PP, 4% for CC) — final tiebreaker

Gates (warn-only, non-blocking — same philosophy as entry script):
- **OI gate**: `OI ≥ 5,000` → ✅ PASS / ⚠️ WARN
- **Spread gate**: `spread_pct ≤ 3.0%` → ✅ PASS / ⚠️ WARN (this is the expiry selection gate; best expiry already preferred but displayed for transparency)

`◀` marks the selected row. `✓` in the `R` column marks round-100 strikes.

```python
# Before (per-track):
for strategy in effective_tracks:
    store.record_trade(PaperTrade(strategy_name=strategy, leg_role="overlay_pp", ...))

# After (shared):
store.record_trade(PaperTrade(strategy_name=OVERLAY_STRATEGY, leg_role="overlay_pp", ...))
```

**CC futures block — move to display layer.** The entry script no longer exits on futures. It records one CC under `paper_overlay_shared`. The snapshot script decides whether to show the CC contribution on the futures track display (it won't).

---

### B. `src/paper/track_snapshot.py` — `generate_track_snapshot`

**Signature change:**

```python
async def generate_track_snapshot(
    store: PaperStore,
    broker: BrokerClient,
    lookup: InstrumentLookup,
    track_namespace: str,          # existing — base legs source
    overlay_strategy: str,         # NEW — shared overlay source
    nifty_spot: Decimal,
    nee: Decimal,
    snapshot_date: date,
    show_overlay: bool = True,     # NEW — False for futures + standalone CC
    proxy_monitor: ProxyDeltaMonitor | None = None,
) -> TrackSnapshot:
```

**Logic change:**

```python
# Base legs: read from track_namespace (unchanged)
trades = store.get_trades(track_namespace)

# Overlay legs: read from overlay_strategy (NEW)
overlay_trades = store.get_trades(overlay_strategy) if show_overlay else []
```

The `overlay_pnls` dict in `TrackPnL` is populated from `overlay_trades`, not from per-track trades. The base P&L computation is unchanged.

**`show_overlay=False`** is passed for `paper_nifty_futures` when the active overlay is a standalone CC. The snapshot still shows the track's base P&L; the overlay column displays "N/A (CC not applied to futures)".

---

### C. `scripts/paper_3track_snapshot.py`

**Changes:**

1. Pass `overlay_strategy=OVERLAY_STRATEGY` to every `generate_track_snapshot` call.
2. Detect the active overlay type from `store.get_trades(OVERLAY_STRATEGY)` — check leg_role to infer `pp`/`cc`/`collar`.
3. For the futures track: pass `show_overlay=False` if active overlay is `cc` (standalone). `pp` and `collar` always show overlay on all tracks.
4. `_save_leg_snapshots`: save overlay leg snapshots under `OVERLAY_STRATEGY` (not per-track). Display the same snapshot values for all three tracks.

```python
# Infer overlay type from shared trades
def _infer_overlay_type(store: PaperStore) -> str | None:
    trades = store.get_trades(OVERLAY_STRATEGY)
    roles = {t.leg_role for t in trades if t.action in active net}
    if "overlay_pp" in roles: return "pp"
    if "overlay_cc" in roles: return "cc"
    if "overlay_collar_put" in roles: return "collar"
    return None

# Per-track show_overlay flag
overlay_type = _infer_overlay_type(store)
for track in tracks:
    show = not (track == "paper_nifty_futures" and overlay_type == "cc")
    snap = await generate_track_snapshot(..., show_overlay=show)
```

---

### D. `scripts/paper_3track_overlay_roll.py`

**Remove:**
- Per-track loop over `effective_tracks`.
- Collar roll iterating over 3 strategies.

**Change:**
- All `store.get_trades(strategy, leg_role)` calls use `OVERLAY_STRATEGY`.
- `_find_expiring_overlay` operates on `OVERLAY_STRATEGY` only.
- `_roll_single` and `_roll_collar` write close + open under `OVERLAY_STRATEGY`.
- Roll report: one row per leg_role (not per track per leg_role).

**Result:** Rolling a PP closes 1 lot, opens 1 lot. Not 3.

---

### E. `src/paper/store.py`

**No schema changes required.** `paper_trades` already supports any `strategy_name`. `paper_leg_snapshots` also stores by `strategy_name` — overlay snapshots stored under `OVERLAY_STRATEGY` are read once and displayed across all tracks.

**One new read method (optional but useful):**

```python
def get_active_overlay_type(self) -> str | None:
    """Infer active overlay type from paper_overlay_shared open positions."""
    trades = self.get_trades("paper_overlay_shared")
    # ... compute net qty per leg_role, return "pp"/"cc"/"collar"/None
```

---

## Display layer — CC on futures

With the shared model, the CC futures block is purely visual:

| Track | PP display | CC display | Collar display |
|---|---|---|---|
| paper_nifty_spot | ✓ P&L shown | ✓ P&L shown | ✓ both legs |
| paper_nifty_futures | ✓ P&L shown | `—` (not applicable) | ✓ both legs |
| paper_nifty_proxy | ✓ P&L shown | ✓ P&L shown | ✓ both legs |

Collar on futures is shown in full — the put provides protection for the short call, making it structurally safe (unlike standalone CC). This is a display choice, not a risk block.

---

## Migration — existing DB data

If any 3-per-track overlay trades already exist in `paper_trades`:

```sql
-- Check existing overlay trades
SELECT strategy_name, leg_role, action, COUNT(*) 
FROM paper_trades 
WHERE leg_role LIKE 'overlay_%'
GROUP BY strategy_name, leg_role, action;

-- Migrate to shared (run only if duplicates exist)
UPDATE paper_trades 
SET strategy_name = 'paper_overlay_shared'
WHERE leg_role LIKE 'overlay_%'
  AND strategy_name IN ('paper_nifty_spot', 'paper_nifty_futures', 'paper_nifty_proxy');
```

If you have 3 identical PP rows (same instrument_key, same trade_date), the UNIQUE constraint on `(strategy_name, leg_role, trade_date, action)` will collapse them to 1 after migration. That's the correct outcome.

---

## Phase plan

| Phase | Scope | Files | Tests |
|---|---|---|---|
| F-1 | Add `OVERLAY_STRATEGY` constant; update entry script to write 1 row; remove `--tracks`; make `--date` optional (default today + warning) | `paper_3track_overlay.py` | 5 tests — single row per overlay type, CC futures no longer errors, `--date` absent emits warning and uses today |
| F-2 | Update `generate_track_snapshot` — `overlay_strategy` param + `show_overlay` flag | `src/paper/track_snapshot.py` | 3 tests — overlay injected from shared strategy; futures CC suppressed |
| F-3 | Update snapshot script — `_infer_overlay_type`, pass flags | `paper_3track_snapshot.py` | 3 tests — `_infer_overlay_type` pp/cc/collar/None |
| F-4 | Update roll script — single strategy, simplified loop | `paper_3track_overlay_roll.py` | 4 tests — roll writes 1 close + 1 open; collar is 4 trades not 12 |
| F-5 | DB migration script + docs | `scripts/migrate_overlay_shared.py`, docs | 1 idempotency test |

Each phase is one commit. F-1 and F-4 are independent and can be done in parallel.

---

## What stays the same

- `PaperLegSnapshot` model — unchanged.
- `paper_leg_snapshots` table — unchanged; overlay snapshots stored under `paper_overlay_shared`.
- `PaperStore` record/get methods — unchanged; just called with `OVERLAY_STRATEGY`.
- Base leg recording (`record_paper_trade.py`) — unchanged; base legs still per-track.
- Phase A store API (`record_leg_snapshot`, `get_prev_leg_snapshot`, `delete_trade`) — unchanged.
- `TrackPnL.overlay_pnls` dict — unchanged; now populated from shared trades instead of per-track.

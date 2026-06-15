# council-refactor — Overlay DB Decoupling Stories

> Shared context and signal tables: `README.md`
> Prerequisite: CR1b committed.

---

## Background

Currently `strategy_name` conflates two concerns: the track identity
(`paper_nifty_spot` / `paper_nifty_proxy` / `paper_nifty_futures`) and the overlay
instrument. Every overlay leg — CC, PP, Collar — is stored as a separate row per
strategy_name, producing 3× replication for the same physical instrument (same strike,
same expiry, same premium).

The fix: overlays are stored once in `paper_trades` with `track = NULL`. Track
association and applicability rules (e.g. "CC blocked on Futures") live in a code-layer
config, resolved at query time. Adding a 4th track requires zero DB changes.

**Story sequence:** OD-1 → OD-2 → OD-3 → OD-4.
NT-2 (`_FUTURES_BLOCKED_ROLES` hardcoded string check) must be revisited after OD-2
ships — the hardcoded `"paper_nifty_futures"` string becomes a config lookup.

---

## OD-1 `[Antigravity]` — DB migration: `track` column on `paper_trades` + `paper_leg_snapshots`

**Files:**
- `src/paper/models.py`
- `src/paper/store.py`
- `scripts/dev/migrate_overlay_track_decouple.py` (new)
- `tests/unit/paper/test_store.py`

**Prerequisite:** CR1b committed.

**Before any code:**
- `get_code_snippet("PaperTrade")` — current field list; confirm no existing `track` field
- `get_code_snippet("PaperLegSnapshot")` — same check
- `search_code("paper_trades")` in `src/paper/store.py` — get current CREATE TABLE DDL
- `search_code("paper_leg_snapshots")` in `src/paper/store.py` — same

**What to implement:**

Add optional `track` field to `PaperTrade` and `PaperLegSnapshot`:

```python
# src/paper/models.py

class PaperTrade(BaseModel, frozen=True):
    ...
    track: str | None = None
    # None = overlay leg (instrument-level, not tied to a specific track)
    # "spot" | "proxy" | "futures" = base leg of that track
```

Same addition to `PaperLegSnapshot`:
```python
class PaperLegSnapshot(BaseModel, frozen=True):
    ...
    track: str | None = None
```

**Schema migration:**

`ALTER TABLE paper_trades ADD COLUMN track TEXT;`
`ALTER TABLE paper_leg_snapshots ADD COLUMN track TEXT;`

Both columns default to `NULL` — existing rows are automatically valid (overlay legs).

**Migration script `scripts/dev/migrate_overlay_track_decouple.py`:**
```python
# Idempotent — checks column existence before ALTER.
# Run once per environment before OD-3 code is used.
# Also backfills track column for existing base-leg rows:
#   paper_nifty_spot    → track = 'spot'
#   paper_nifty_proxy   → track = 'proxy'
#   paper_nifty_futures → track = 'futures'
# Overlay legs (overlay_cc, overlay_pp, overlay_collar_call, overlay_collar_put)
# retain track = NULL.
```

Backfill logic — update existing rows by `leg_role` pattern:
```sql
UPDATE paper_trades
   SET track = CASE
       WHEN strategy_name = 'paper_nifty_spot'    THEN 'spot'
       WHEN strategy_name = 'paper_nifty_proxy'   THEN 'proxy'
       WHEN strategy_name = 'paper_nifty_futures' THEN 'futures'
       ELSE NULL
   END
WHERE track IS NULL;
```

Apply identical backfill to `paper_leg_snapshots`.

**`PaperStore` changes:**

`record_paper_trade` and `record_leg_snapshot` must write the `track` field.
`get_trades`, `get_positions`, `get_leg_snapshot` must read and populate it.
No changes to UNIQUE constraints — `(strategy_name, leg_role, trade_date, action)` is
still the natural key. Overlay legs continue to use a canonical `strategy_name` like
`"overlay"` or `"paper_overlays"` (decided in OD-3).

**Tests:**
- Round-trip: insert `PaperTrade(track="proxy")`, fetch → `track == "proxy"`
- Round-trip: insert overlay `PaperTrade(track=None)`, fetch → `track is None`
- Migration script: idempotent on second run (no error, no duplicate column)
- Migration script: backfill sets correct track values for existing strategy_name rows

**Commit:** `feat(paper): add track column to paper_trades + paper_leg_snapshots; migration script`

---

## OD-2 `[Claude]` — Track-overlay applicability config

**Files:**
- `src/strategy/track_overlay_config.py` (new)
- `tests/unit/strategy/test_track_overlay_config.py` (new)

**Prerequisite:** OD-1 committed.

**Before any code:**
- `search_graph("_FUTURES_BLOCKED_ROLES")` — confirm it lives in `nifty_track_comparison_v1.py` post-NT-2; we will supersede it here
- `search_graph("NiftyTrackComparisonV1")` — confirm strategy_name constants

**What to implement:**

```python
# src/strategy/track_overlay_config.py

from enum import StrEnum

class Track(StrEnum):
    SPOT    = "spot"
    PROXY   = "proxy"
    FUTURES = "futures"

class OverlayRole(StrEnum):
    CC           = "overlay_cc"
    PP           = "overlay_pp"
    COLLAR_CALL  = "overlay_collar_call"
    COLLAR_PUT   = "overlay_collar_put"

# Explicit block list. Any (track, overlay_role) pair not in this set is ALLOWED.
BLOCKED_COMBINATIONS: frozenset[tuple[Track, OverlayRole]] = frozenset({
    (Track.FUTURES, OverlayRole.CC),
    # Collar on Futures is allowed ONLY when both legs present — enforced at runtime
    # by NiftyTrackComparisonV1._check_futures_cc_block, not here.
    # This config encodes structural blocks only.
})

def is_overlay_allowed(track: Track, overlay_role: OverlayRole) -> bool:
    """Return True if the overlay role may be applied to the given track.

    Args:
        track: The track the overlay would be applied to.
        overlay_role: The overlay leg role.

    Returns:
        False if the combination is in BLOCKED_COMBINATIONS, True otherwise.
    """
    return (track, overlay_role) not in BLOCKED_COMBINATIONS

def get_allowed_overlays(track: Track) -> list[OverlayRole]:
    """Return all overlay roles allowed for the given track.

    Args:
        track: The track to query.

    Returns:
        List of OverlayRole values not blocked for this track.
    """
    return [r for r in OverlayRole if is_overlay_allowed(track, r)]
```

**Update NT-2 after this ships:**
Replace the hardcoded `_FUTURES_BLOCKED_ROLES` frozenset in `nifty_track_comparison_v1.py`
with a call to `is_overlay_allowed(Track.FUTURES, role)`. The test assertions remain
identical — only the implementation source changes.

**Tests:**
- `is_overlay_allowed(Track.FUTURES, OverlayRole.CC)` → `False`
- `is_overlay_allowed(Track.SPOT, OverlayRole.CC)` → `True`
- `is_overlay_allowed(Track.PROXY, OverlayRole.CC)` → `True`
- `is_overlay_allowed(Track.FUTURES, OverlayRole.PP)` → `True`
- `is_overlay_allowed(Track.FUTURES, OverlayRole.COLLAR_CALL)` → `True`
- `get_allowed_overlays(Track.FUTURES)` → does not contain `OverlayRole.CC`
- `get_allowed_overlays(Track.SPOT)` → contains all four roles
- Adding a new track: confirm no existing test breaks (open-world design)

**Commit:** `feat(strategy): track_overlay_config — applicability map + Track/OverlayRole enums`

---

## OD-3 `[Antigravity]` — Consolidate overlay recording in NiftyTrackComparisonV1

**Files:**
- `src/strategy/nifty_track_comparison_v1.py`
- `tests/unit/strategy/test_nifty_track_comparison_v1.py`

**Prerequisites:** OD-1 committed, OD-2 committed.

**Before any code:**
- `get_code_snippet("NiftyTrackComparisonV1")` — full class; find all `record_paper_trade` calls for overlay legs
- `search_code("overlay_cc")` in `src/strategy/nifty_track_comparison_v1.py` — count current replication sites
- `get_code_snippet("PaperStore.record_paper_trade")` — updated signature post-OD-1

**What to change:**

Currently overlay legs are recorded once per strategy_name track (3× for CC, 3× for PP,
6× for Collar). Replace with a single canonical `strategy_name = "paper_overlays"` for
all overlay leg inserts. Set `track = None` on those rows.

Define a module constant:
```python
_OVERLAY_STRATEGY_NAME = "paper_overlays"
```

All `record_paper_trade` calls for `leg_role` in `OverlayRole` use this constant instead
of the per-track strategy_name. Base leg inserts (`base_niftybees`, `base_futures`,
`base_ditm_call`) continue to use the per-track strategy_name with the appropriate `track`
value.

**Query-side update in the same commit:**

`get_positions(strategy_name)` is called with the per-track name. After this change,
overlay positions live under `"paper_overlays"` and will not appear in a per-track
`get_positions` call. Fix: add a `get_overlay_positions()` method to `PaperStore` that
queries `WHERE strategy_name = 'paper_overlays'`. Update `NiftyTrackComparisonV1` to
merge base positions (from `get_positions(track_strategy_name)`) with overlay positions
(from `get_overlay_positions()`) before signal evaluation.

```python
def get_overlay_positions(self) -> list[PaperPosition]:
    """Return all open overlay leg positions (track-agnostic).

    Returns:
        List of PaperPosition where strategy_name = 'paper_overlays'.
    """
```

**Tests:**
- Recording CC once: only one row in `paper_trades` with `strategy_name = "paper_overlays"`
- Three tracks active: overlay query returns single CC row, not three
- `get_overlay_positions()` returns CC, PP, both Collar legs
- Per-track `get_positions("paper_nifty_proxy")` returns base leg only, not overlays
- Merged position list (base + overlay) used in signal evaluation → existing signal tests unaffected

**Commit:** `refactor(strategy): consolidate overlay recording under paper_overlays; add get_overlay_positions`

---

## OD-4 `[Claude]` — Update snapshot and roll scripts to resolve applicability at query time

**Files:**
- `scripts/strategies/three_track/paper_3track_snapshot.py`
- `scripts/strategies/three_track/paper_3track_overlay_roll.py`
- `tests/unit/strategies/test_paper_3track_snapshot.py` (if exists, else create)

**Prerequisites:** OD-3 committed.

**Before any code:**
- `get_code_snippet("paper_3track_snapshot")` — full script; find where overlay positions are fetched per-track
- `get_code_snippet("paper_3track_overlay_roll")` — find roll eligibility checks
- `search_code("get_positions")` in both scripts — confirm current call pattern

**What to change:**

`paper_3track_snapshot.py`:
1. Replace per-track overlay `get_positions()` calls with a single `get_overlay_positions()` call.
2. At display/report time, for each track × overlay combination, call
   `is_overlay_allowed(track, overlay_role)` — if `False`, show "blocked" in output rather
   than an empty row. This is purely presentational; no DB read needed.
3. The "missing" rows in the screenshot (overlay_collar_call absent from all three tracks)
   become a code-side gap check: if `get_overlay_positions()` returns no row for
   `overlay_collar_call`, emit a WARNING log and Telegram alert: "collar_call leg not recorded
   — use record_paper_trade.py to add it".

`paper_3track_overlay_roll.py`:
1. Fetch overlays once via `get_overlay_positions()` instead of once per track.
2. Before emitting roll signal for any overlay, call `is_overlay_allowed(track, overlay_role)`
   for each target track — skip blocked combinations silently (already enforced at record time,
   but belt-and-suspenders check here).

**Tests:**
- Snapshot: single `get_overlay_positions()` call, not three `get_positions()` calls
- Blocked combination renders as "blocked" in output, not empty row
- Missing overlay_collar_call → WARNING emitted
- Roll script: roll signal only emitted for allowed track × overlay combinations

**Commit:** `refactor(scripts): three_track snapshot + roll use get_overlay_positions; applicability at query time`

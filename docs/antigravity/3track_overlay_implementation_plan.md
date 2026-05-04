# Implementation Plan: Overlay Automation + 3-Track PnL Display
> Source: `docs/plan/paper_3track_overlay.md` | Status: **Draft — pending approval**

---

## Background

The plan specifies 4 deliverables to close 3 manual pain points (overlay entry, overlay
rolling, fragmented PnL display). Codebase inspection reveals **two partial implementations
already exist** that must be reconciled:

| Plan deliverable | Actual file on disk | Gap |
|---|---|---|
| `paper_3track_overlay.py` | `scripts/paper_3track_overlay_entry.py` ✅ exists | YAML-based, no live market fetch |
| `paper_3track_overlay_roll.py` | ❌ does not exist | Needs full implementation |
| `paper_3track_snapshot.py` | `scripts/paper_track_snapshot.py` ✅ exists | Missing per-leg snapshots + Δ display |
| `paper_leg_snapshots` table | ❌ not in `store.py` _SCHEMA | Needs migration + API |

> [!IMPORTANT]
> `paper_3track_overlay_entry.py` is YAML-driven (reads `data/paper/overlay_entry.yaml`).
> The plan wants live-fetching automation. **Decision required: extend or replace?**
> Recommendation: keep the existing YAML script; create the new live-fetch script as
> `paper_3track_overlay.py` alongside it. Both coexist.

---

## User Review Required

> [!WARNING]
> `paper_track_snapshot.py` takes `--underlying-price` as a **required** CLI arg.
> The new `paper_3track_snapshot.py` makes it **optional** (default: fetch live).
> Confirm: should new script **replace** `paper_track_snapshot.py` or live alongside it?
> **Recommendation**: create `paper_3track_snapshot.py` as the new canonical cron script;
> keep `paper_track_snapshot.py` for backward compat (no deletion).

---

## Phased Implementation

**Phase A must complete before B, C, D. B, C, D can run in parallel.**

---

### Phase A — DB Model
> **Commit: `feat(paper): add paper_leg_snapshots table and PaperStore read/write API`**

#### [MODIFY] [models.py](file:///Users/abhadra/myWork/myCode/python/NiftyShield/src/paper/models.py)
Add `PaperLegSnapshot` frozen dataclass after `PaperNavSnapshot` (line 138):
```python
@dataclass(frozen=True)
class PaperLegSnapshot:
    """Per-leg daily P&L snapshot. One row per (strategy_name, leg_role, snapshot_date)."""
    strategy_name: str
    leg_role: str
    snapshot_date: date
    unrealized_pnl: Decimal
    realized_pnl: Decimal
    total_pnl: Decimal
    ltp: Decimal | None = None
```

#### [MODIFY] [store.py](file:///Users/abhadra/myWork/myCode/python/NiftyShield/src/paper/store.py)
1. Add `PaperLegSnapshot` to the import on line 22.
2. Append to `_SCHEMA` string (after line 67):
```sql
CREATE TABLE IF NOT EXISTS paper_leg_snapshots (
    strategy_name  TEXT    NOT NULL,
    leg_role       TEXT    NOT NULL,
    snapshot_date  TEXT    NOT NULL,
    unrealized_pnl TEXT    NOT NULL,
    realized_pnl   TEXT    NOT NULL,
    total_pnl      TEXT    NOT NULL,
    ltp            TEXT,
    PRIMARY KEY (strategy_name, leg_role, snapshot_date)
) STRICT;
```
> [!NOTE]
> No explicit index added — the PRIMARY KEY already creates an implicit B-tree index on
> `(strategy_name, leg_role, snapshot_date)`. A duplicate index would waste storage and
> would never be chosen over the PK index by SQLite's query planner.
3. Add 4 new methods to `PaperStore` (after `get_proxy_delta_consecutive_days`, line 441):
   - `record_leg_snapshot(snap: PaperLegSnapshot) -> None` — assert `snap.total_pnl == snap.unrealized_pnl + snap.realized_pnl` before the INSERT; raises `ValueError` on mismatch. Then upsert via ON CONFLICT UPDATE.
   - `get_leg_snapshot(strategy_name, leg_role, snap_date) -> PaperLegSnapshot | None`
   - `get_prev_leg_snapshot(strategy_name, leg_role, before_date) -> PaperLegSnapshot | None` — `MAX(snapshot_date) < before_date`
   - `delete_trade(trade: PaperTrade) -> None` — delete by unique constraint `(strategy_name, leg_role, trade_date, action)`; no-op if row not found (safe to call in a rollback path where the write may not have committed)

> [!IMPORTANT]
> The `total_pnl` assertion in `record_leg_snapshot` is the same class of invariant
> as the Decimal-as-TEXT rule: it prevents silent data corruption from a manually
> constructed `PaperLegSnapshot` with inconsistent fields. It must live in the store
> method (not only in a `__post_init__`), because the store is the last choke point
> before SQLite.

#### [MODIFY] [test_store.py](file:///Users/abhadra/myWork/myCode/python/NiftyShield/tests/unit/paper/test_store.py)
Add `TestLegSnapshots` class:
- `test_record_leg_snapshot_roundtrip`
- `test_record_leg_snapshot_upsert`
- `test_record_leg_snapshot_inconsistent_total_pnl_raises` — construct a `PaperLegSnapshot` where `total_pnl != unrealized_pnl + realized_pnl`, assert `store.record_leg_snapshot(...)` raises `ValueError`
- `test_get_leg_snapshot_missing`
- `test_get_prev_leg_snapshot_returns_max_before_date`
- `test_get_prev_leg_snapshot_no_prior`
- `test_delete_trade_removes_correct_row` — record two trades, delete one by its unique key fields, assert only the other remains via `get_trades`

---

### Phase B — Overlay Entry Script (Live-Fetch)
> **Commit: `feat(scripts): paper_3track_overlay live-fetch entry automation`**

#### [NEW] [paper_3track_overlay.py](file:///Users/abhadra/myWork/myCode/python/NiftyShield/scripts/paper_3track_overlay.py)

Module-level constants:
```python
LOT_SIZE = 65
PP_OTM_MIN, PP_OTM_MAX, PP_TARGET_OTM = 0.08, 0.10, 0.09
CC_OTM_MIN, CC_OTM_MAX, CC_TARGET_OTM = 0.03, 0.05, 0.04
SPREAD_PCT_MAX = 3.0
OVERLAY_ROLL_DTE = 5
```

Key functions:
```python
async def _fetch_candidates(broker, underlying, expiry, option_type, spot, otm_min, otm_max) -> list[dict]
def _rank_overlay_key(r: dict, target_otm: float) -> tuple  # 5-tuple: (is_non_round, spread_bucket, -oi, spread, otm_dist)
async def _select_expiry(broker, underlying, expiries, option_type, spot, ...) -> tuple[str, dict]
def _check_existing_overlay(store, strategy, leg_role) -> PaperTrade | None
def _build_trades(overlay_type, strategies, expiry, selected, entry_date, lot_size) -> list[PaperTrade]
def _print_confirmation_table(overlay_type, rows, entry_date, expiry, dte) -> None
async def main() -> None  # --overlay, --date, --tracks, --yes, --dry-run, --force
```

CLI blocked-combo guard — applied to the **resolved** track list, not raw argparse:
```python
ALL_TRACKS = ["paper_nifty_spot", "paper_nifty_futures", "paper_nifty_proxy"]

# In main(), immediately after parse_args():
effective_tracks = args.tracks if args.tracks else ALL_TRACKS  # resolve defaults first

if args.overlay == "cc" and "paper_nifty_futures" in effective_tracks:
    print("ERROR: Covered call BLOCKED on paper_nifty_futures...")
    sys.exit(1)
```
> [!IMPORTANT]
> `effective_tracks` must be resolved before the guard runs. Without this, omitting
> `--tracks` (which implies all three including futures) would silently bypass the
> hard exit(1) check — the exact failure mode that makes this rule safety-critical.

Collar atomicity: validate both legs before writing either; on second-leg failure, delete first.

#### [NEW] [test_paper_3track_overlay.py](file:///Users/abhadra/myWork/myCode/python/NiftyShield/tests/unit/paper/test_paper_3track_overlay.py)
- `test_rank_overlay_key_round_strike_wins` — `is_non_round=0` beats `is_non_round=1`
- `test_rank_overlay_key_higher_oi_wins_in_same_bucket`
- `test_cc_blocked_on_futures_exits_1` — implicit futures (no `--tracks`) triggers guard
- `test_cc_on_spot_and_proxy_succeeds` — positive case: CC on spot+proxy passes guard
- `test_build_trades_pp_leg_roles`
- `test_build_trades_collar_both_legs` — both `overlay_collar_put` + `overlay_collar_call`
- `test_check_existing_overlay_no_open_returns_none`
- `test_check_existing_overlay_same_expiry_no_force_needed` — existing open, same expiry: proceeds
- `test_check_existing_overlay_diff_expiry_requires_force` — different expiry without `--force` exits 1

---

### Phase C — Snapshot Script (Combined PnL + per-leg Δ)
> **Commit: `feat(scripts): paper_3track_snapshot combined PnL display with per-leg delta`**

#### [NEW] [paper_3track_snapshot.py](file:///Users/abhadra/myWork/myCode/python/NiftyShield/scripts/paper_3track_snapshot.py)

Module docstring carries cron line:
```
# 50 15 * * 1-5  python -m scripts.paper_3track_snapshot
```

Key functions:
```python
BASE_LEGS = {"base_etf", "base_futures", "base_ditm_call"}
OVERLAY_PREFIX = "overlay_"

def _leg_delta(store, strategy, leg_role, today_pnl, today) -> Decimal  # sync — SQLite call only
def _protection_status(base_delta: Decimal, overlay_delta: Decimal) -> str  # ✅/⚠️/❌
def _print_longs_section(leg_results: dict) -> None
def _print_protection_section(track_results: dict, overlay_type: str) -> None
async def main() -> None  # --date, --underlying (optional), --no-save
```

`--underlying` defaults to live fetch: `UpstoxMarketClient.get_ltp(["NSE_INDEX|Nifty 50"])`.

Save behavior: write `paper_nav_snapshots` + `paper_leg_snapshots` by default; `--no-save` skips all DB writes.

Base inclusion rule (Protection section):
- `paper_nifty_spot`: show NiftyBees Δ + overlay Δ → Net Spot
- `paper_nifty_futures` / `paper_nifty_proxy`: show overlay Δ only (base excluded per spec)

#### [NEW] [test_paper_3track_snapshot.py](file:///Users/abhadra/myWork/myCode/python/NiftyShield/tests/unit/paper/test_paper_3track_snapshot.py)
- `test_protection_status_protected`
- `test_protection_status_partial`
- `test_protection_status_unprotected`
- `test_leg_delta_no_prior_returns_zero`
- `test_leg_delta_with_prior`

---

### Phase D — Overlay Roll Script
> **Commit: `feat(scripts): paper_3track_overlay_roll automation`**

#### [NEW] [paper_3track_overlay_roll.py](file:///Users/abhadra/myWork/myCode/python/NiftyShield/scripts/paper_3track_overlay_roll.py)

Key functions:
```python
def _parse_expiry_from_key(instrument_key: str) -> date | None
    # Pattern: NSE_FO|NIFTY<DDMMMYYYY>PE/CE → datetime.strptime("<DDMMMYYYY>", "%d%b%Y").date()
    # Returns None for equity legs (NiftyBees — no expiry in key)

def _find_expiring_overlay(trades: list[PaperTrade], roll_date: date, leg_role: str) -> list[PaperTrade]

async def _close_leg(broker, store, trade, roll_date, dry_run) -> PaperTrade
    # SELL for long PP/collar_put; BUY for short CC/collar_call

async def _open_new_leg(broker, overlay_type, strategy, roll_date, lot_size, ...) -> PaperTrade

async def _roll_single(store, broker, lookup, overlay_type, strategy, leg_role, roll_date, force, dry_run, yes):
    # Resolve the expiring trade before attempting any writes.
    trades = store.get_trades(strategy, leg_role)
    expiring = _find_expiring_overlay(trades, roll_date, leg_role)
    if not expiring:
        return  # nothing to roll for this leg
    trade = expiring[0]  # at most one open overlay per leg role
    # 2-trade atomicity: close first, then open.
    # If _open_new_leg fails after the close trade has been written,
    # delete the close trade before re-raising — same 'all or none' guarantee as collar.
    close_trade = await _close_leg(broker, store, trade, roll_date, dry_run)
    try:
        open_trade = await _open_new_leg(broker, lookup, overlay_type, strategy, roll_date, ...)
    except Exception:
        if not dry_run:
            store.delete_trade(close_trade)  # rollback: un-close the leg
        raise

async def _roll_collar(...)  # 4-trade atomic: close_put, close_call, open_put, open_call
    # Same pattern: validate and write all four or none.
    # If any open fails after closes are written, delete both close trades before re-raising.

def _print_roll_report(results: list) -> None  # per-plan table

async def main() -> None  # --overlay, --date, --tracks, --yes, --dry-run, --force
```

> [!IMPORTANT]
> `_roll_single` (PP/CC) and `_roll_collar` must have identical atomicity guarantees.
> PP/CC is a 2-trade operation (close + open); collar is a 4-trade operation (close×2 + open×2).
> In both cases: if any write after the first fails, all prior writes in the same roll are
> deleted before the exception propagates. The paper book must never be left with a closed
> leg and no replacement.
>
> This requires `PaperStore.delete_trade(trade: PaperTrade) -> None` — a new store method
> (keyed on the unique constraint: `strategy_name, leg_role, trade_date, action`).
> Add it to Phase A's store method additions and include a test in `TestLegSnapshots`.

#### [NEW] [test_paper_3track_overlay_roll.py](file:///Users/abhadra/myWork/myCode/python/NiftyShield/tests/unit/paper/test_paper_3track_overlay_roll.py)
- `test_parse_expiry_from_key_pe`
- `test_parse_expiry_from_key_ce`
- `test_parse_expiry_from_key_equity_returns_none`
- `test_find_expiring_overlay_filters_by_dte`
- `test_find_expiring_overlay_skips_equity`
- `test_roll_single_open_failure_deletes_close_trade` — mock `_open_new_leg` to raise, assert `store.delete_trade` was called with the close trade (verifies the rollback path runs, not just that it exists)

---

### Phase E — Docs
> **Commit: `docs: update CONTEXT.md, TODOS.md, and src/paper/CLAUDE.md for overlay automation`**

#### [MODIFY] CONTEXT.md, CONTEXT_TREE.md, TODOS.md, src/paper/CLAUDE.md
- Add `paper_leg_snapshots` table to CONTEXT.md DB schema section
- Add new scripts to CONTEXT_TREE.md
- Mark overlay automation tasks complete in TODOS.md
- Note `paper_3track_snapshot.py` as new canonical cron script
- Update `src/paper/CLAUDE.md` with: new `PaperLegSnapshot` model, the `total_pnl` assertion invariant in `record_leg_snapshot`, and the three new store methods — material changes to `src/paper/` invariants require the module CLAUDE.md to stay current

---

## Verification Plan

### Automated Tests
```bash
# Phase A
pytest tests/unit/paper/test_store.py -k "LegSnapshot" -v

# Phase B
pytest tests/unit/paper/test_paper_3track_overlay.py -v

# Phase C
pytest tests/unit/paper/test_paper_3track_snapshot.py -v

# Phase D
pytest tests/unit/paper/test_paper_3track_overlay_roll.py -v

# Full regression (run after each phase)
pytest tests/unit/paper/ -v
```

### Manual Verification
- **Phase A**: `sqlite3 data/portfolio/portfolio.sqlite ".tables"` — confirm `paper_leg_snapshots` present
- **Phase B**: `python -m scripts.paper_3track_overlay --overlay pp --dry-run --date 2026-05-07`
- **Phase C**: `python -m scripts.paper_3track_snapshot --no-save --date 2026-05-07`
- **Phase D**: `python -m scripts.paper_3track_overlay_roll --overlay pp --dry-run --date 2026-05-28`

---

## Token-Efficient Session Strategy

Each phase is one conversation. At session start, load only:
1. This plan (mark completed phases)
2. Files being modified in that phase
3. The test file for that phase

| Phase | Files needed in context |
|---|---|
| A | `src/paper/models.py` (139 lines) + `src/paper/store.py` (442 lines) |
| B | `src/paper/store.py` imports only + `paper_3track_overlay_entry.py` (ranking/pattern reference) |
| C | `src/paper/store.py` imports + `paper_track_snapshot.py` (pattern reference) |
| D | Phase B output (for `_parse_expiry_from_key`) + `store.py` imports |
| E | CONTEXT.md + TODOS.md + `src/paper/CLAUDE.md` |

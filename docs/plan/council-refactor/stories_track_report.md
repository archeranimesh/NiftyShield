# Track Report Stories — RPT series

> Stories covering the 3-track summary table: overlay P&L bug fix and CLI/period redesign.
>
> Load alongside `README.md` for shared context.

---

## RPT-1 — Fix: closed overlay legs excluded from summary table

**Owner:** `[Claude]`
**Files:** `src/paper/track_snapshot.py`
**Tests:** `tests/unit/paper/test_track_snapshot.py`

### Problem

`generate_track_snapshot` computes overlay P&L by iterating `open_positions`
(positions where `net_qty != 0`). When an overlay leg is fully closed or expires
worthless, `net_qty` returns to 0 and the position is excluded from the loop.
Its entry in `realized_by_leg` is computed but never folded into `overlay_pnls`.

Result: every expired CC, collar call/put, or PP that has been closed is silently
dropped from the Overlay column. The cumulative discrepancy grows with each overlay
cycle. Observed gap on 2026-06-09: ~₹1.6L missing across 3 tracks.

### Root cause (exact location)

`src/paper/track_snapshot.py`, `generate_track_snapshot`, lines ~115–165:

```python
for pos in open_positions:          # ← only net_qty != 0
    ...
    leg_realized = realized_by_leg.get(pos.leg_role, Decimal("0"))
    overlay_pnls[pos.leg_role] = ... + leg_total_pnl
    # closed legs never enter this loop → their realized P&L vanishes
```

### Fix

After the main `open_positions` loop, add a second pass for fully-closed overlay roles:

```python
# Include realized P&L from fully-closed overlay legs (net_qty == 0)
all_overlay_roles = {t.leg_role for t in trades if t.leg_role.startswith("overlay_")}
open_overlay_roles = {p.leg_role for p in open_positions if p.leg_role.startswith("overlay_")}
for role in all_overlay_roles - open_overlay_roles:
    closed_realized = realized_by_leg.get(role, Decimal("0"))
    if closed_realized:
        overlay_pnls[role] = overlay_pnls.get(role, Decimal("0")) + closed_realized
```

No model changes. No new DB queries — `_compute_realized_pnl_by_leg` already returns
all roles including closed ones; we just weren't using the closed-leg entries.

### Tests (happy + edge)

| Test | Setup | Assert |
|---|---|---|
| Happy: expired overlay included | One open CC leg (net_qty=−1, realized=₹500) + one expired CC leg (net_qty=0, realized=₹1200) | `overlay_pnls["overlay_cc"]` = ₹500 + unrealized + ₹1200 |
| Happy: multiple closed cycles | Three closed PP legs (same role, net_qty=0), realized=₹300 each | `overlay_pnls["overlay_pp"]` = ₹900 |
| Edge: all overlays open | No closed roles | Behaviour identical to pre-fix |
| Edge: no overlays at all | Track has only base legs | `overlay_pnls` remains `{}` |

---

## RPT-2 — CLI redesign + daily P&L mode

**Owner:** `[Claude]`
**Files:**
- `scripts/strategies/three_track/paper_3track_snapshot.py`
- `src/paper/formatting.py`
**Tests:** `tests/unit/paper/test_paper_3track_snapshot.py`

**Prerequisite:** RPT-1 committed (inception mode depends on the fix being present).

### Problem

1. **CLI ergonomics**: `--mode daily|monthly|inception` is non-idiomatic for Linux
   tooling — string values are easy to misspell, not tab-completable, and don't
   compose naturally with other flags.

2. **Mixed time bases**: Base P&L is cumulative from NiftyBees purchase date; Overlay
   is cumulative from each overlay's entry date. The two columns are not comparable
   on a day-to-day basis. A 1-day delta view makes both columns immediately
   interpretable together.

### CLI design

Replace any `--mode` string with a **mutually exclusive flag group**. Argparse
enforces exclusivity automatically — passing two flags together is a hard error.

```
paper_3track_snapshot.py [--daily | --monthly | --inception]
                         [--date YYYY-MM-DD] [--spot PRICE]
                         [--tracks {spot,futures,proxy} [...]]
                         [--dry-run] [--verbose]
                         [--db-path PATH] [--bod-path PATH]
```

| Flag | Short | Default | Meaning |
|---|---|---|---|
| `--daily` | `-d` | ✓ (default) | 1-day delta for Base and Overlay |
| `--monthly` | `-m` | — | Month-to-date delta (deferred — RPT-3) |
| `--inception` | `-i` | — | Cumulative from entry (RPT-1 fix included) |

`--daily` is the default. Running the script with no period flag is equivalent to `-d`.

### Implementation

#### argparse wiring

```python
period = parser.add_mutually_exclusive_group()
period.add_argument(
    "--daily", "-d", dest="period", action="store_const", const="daily",
    help="1-day delta for Base and Overlay (default)",
)
period.add_argument(
    "--monthly", "-m", dest="period", action="store_const", const="monthly",
    help="Month-to-date delta from first trading day of current month",
)
period.add_argument(
    "--inception", "-i", dest="period", action="store_const", const="inception",
    help="Cumulative from entry (includes all closed overlay cycles)",
)
parser.set_defaults(period="daily")
```

#### Daily mode: computing 1-day delta per track

`generate_track_snapshot` returns a `TrackSnapshot` with cumulative P&L. The delta
computation is a post-processing step in `_run`, not inside `generate_track_snapshot`
(avoids changing the core model and keeps the function reusable for inception mode).

```python
def _day_delta_row(
    store: PaperStore,
    track_name: str,
    snapshot: TrackSnapshot,
    today: date,
) -> dict:
    """Return summary row with 1-day deltas for base and overlay."""
    pnl = snapshot.pnl

    base_role = _base_leg_role(track_name)
    prev_base = store.get_prev_leg_snapshot(track_name, base_role, before_date=today)
    prev_base_total = prev_base.total_pnl if prev_base else Decimal("0")
    day_base = pnl.base_pnl - prev_base_total

    day_overlay = Decimal("0")
    for role in pnl.overlay_pnls:
        prev_ovl = store.get_prev_leg_snapshot(track_name, role, before_date=today)
        prev_ovl_total = prev_ovl.total_pnl if prev_ovl else Decimal("0")
        day_overlay += pnl.overlay_pnls[role] - prev_ovl_total

    day_net = day_base + day_overlay
    nee = compute_nee(snapshot.greeks.net_delta, LOT_SIZE)   # approximate; pass actual nee
    day_ret = compute_return_on_nee(day_net, nee)

    return {
        "track": BASE_LABELS.get(track_name, track_name),
        "base_pnl": day_base,
        "overlay_pnl": day_overlay,
        "net_pnl": day_net,
        "return_on_nee": day_ret,
    }
```

Note: `nee` should be threaded from the outer `_run` context, not re-derived
from delta. Pass it explicitly to `_day_delta_row`.

#### Inception mode

Use the existing `summary_rows` construction path (no change needed beyond RPT-1 fix).

#### Monthly mode (guard only — RPT-3 not yet built)

```python
if args.period == "monthly":
    logger.error("Monthly mode not yet implemented. Use --daily or --inception.")
    sys.exit(1)
```

#### Column headers

`format_track_summary` in `src/paper/formatting.py` receives an optional `period`
argument and adjusts column headers:

```python
def format_track_summary(
    rows: list[dict],
    title: str = "",
    is_dry_run: bool = False,
    period: str = "daily",          # "daily" | "monthly" | "inception"
) -> str:
```

| Period | Base column header | Overlay column header |
|---|---|---|
| `daily` | `Day Base` | `Day Overlay` |
| `monthly` | `MTD Base` | `MTD Overlay` |
| `inception` | `Base P&L` | `Overlay` |

### Tests

| Test | Setup | Assert |
|---|---|---|
| Daily: prev snapshot exists | Mock `get_prev_leg_snapshot` returning total_pnl=₹1000; current base_pnl=₹1200 | `day_base` = ₹200 |
| Daily: no prev snapshot (first day) | `get_prev_leg_snapshot` returns None | `day_base` = full current base_pnl (no prior baseline) |
| Daily: overlay delta | Prev overlay total=₹500, current=₹800 | `day_overlay` = ₹300 |
| CLI: mutual exclusion | `-d -i` together | argparse raises SystemExit |
| CLI: default is daily | No period flag | `args.period == "daily"` |
| CLI: `-m` guard | `--monthly` flag | exits with error code 1, logs "not yet implemented" |
| Formatting: daily headers | `format_track_summary(..., period="daily")` | header line contains "Day Base", "Day Overlay" |
| Formatting: inception headers | `format_track_summary(..., period="inception")` | header line contains "Base P&L", "Overlay" |

---

## RPT-3 — Monthly mode (deferred)

**Owner:** `[Claude]`
**Files:** `scripts/strategies/three_track/paper_3track_snapshot.py`
**Prerequisite:** RPT-2 committed. `MarketCalendar` or equivalent available for
resolving the first trading day of the current month.

### Design (placeholder — spec to be written when scheduled)

- Resolve reference date: first NSE trading day of `args.date.month` (skip weekends +
  NSE holidays using `src/market_calendar/`).
- For each leg role, call `store.get_leg_snapshot(strategy, role, date=ref_date)`.
  If no snapshot on that exact date, use the nearest prior snapshot
  (`get_prev_leg_snapshot(before_date=ref_date + timedelta(1))`).
- Compute delta exactly as daily mode but against `ref_date` baseline.
- Remove the `sys.exit(1)` guard added in RPT-2.

### Why deferred

Requires `market_calendar` holiday list to be accurate and `paper_leg_snapshots`
to have a row near the 1st of every month (relies on cron running daily). Safe to
add once those invariants are confirmed stable.

# Covered Call Overlay — Data Schema

No new database tables. The covered call overlay uses the existing paper trading infrastructure
in `data/portfolio/portfolio.sqlite` with the strategy name `paper_covered_call_v1`.

---

## Tables used (existing)

### `paper_trades`

Each CC cycle produces one row with:

| Column | Value |
|---|---|
| `strategy_name` | `paper_covered_call_v1` |
| `leg_role` | `covered_call` |
| `option_type` | `CE` |
| `action` | `SELL` |
| `underlying` | `NSE_INDEX\|Nifty 50` |
| `strike` | 15-delta strike (resolved at entry) |
| `expiry` | Monthly expiry, 30–45 DTE from entry |
| `entry_price` | Credit collected per unit (₹/unit, Decimal as TEXT) |
| `net_qty` | 65 (one lot) |
| `ivr_at_entry` | IVR at entry time (float \| None) |
| `notes` | Exit trigger that closed the leg (e.g. `profit_target`, `time_stop`, `delta_stop`) |

### `paper_leg_snapshots`

Written by `paper_3track_snapshot.py` (or a dedicated `paper_cc_snapshot.py` if created).
One row per leg per EOD snapshot: `ltp`, `delta`, `unrealized_pnl`, `realized_pnl`, `total_pnl`.

### `paper_nav_snapshots`

Written at EOD. Aggregates NAV across all open positions including CC overlay.

---

## Strategy name constant

Defined in `src/paper/constants.py` (added in task CC1):

```python
STRATEGY_CC_OVERLAY = "paper_covered_call_v1"
```

---

## Quantity constraint formula

Defined in `src/paper/constants.py` as a pure function (added in task CC1):

```python
def compute_max_lots(
    niftybees_units: int,
    nifty_spot: Decimal,
    niftybees_ltp: Decimal,
    lot_size: int = LOT_SIZE,
) -> int:
    """Return maximum CC lots coverable by pledged NiftyBees units.

    Formula: floor(niftybees_units / (nifty_spot / niftybees_ltp × lot_size))
    Recompute at each annual NiftyBees leg reset.
    At ~5,725 units (current holding), returns 1 lot.
    """
```

---

## Exit trigger values (stored in `notes` field)

| Trigger | `notes` value written at close |
|---|---|
| Profit target (≤50% of credit remaining) | `profit_target` |
| Time stop (21 calendar days from entry) | `time_stop` |
| Delta stop (call delta crosses +0.40) | `delta_stop` |

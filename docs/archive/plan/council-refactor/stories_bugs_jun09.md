# BUG-1 through BUG-5 — Signal Flood & False Exit Bugs (discovered 2026-06-09)

> Root-cause investigation: multiple PROFIT_TARGET notifications fired for a brand-new
> CSP position opened on 2026-06-08.  Five bugs found across three commits.
> Fix priority order: BUG-1 → BUG-2 → BUG-3 → BUG-4 → BUG-5.

---

## Background — What Happened

1. User manually entered new CSP (NSE_FO|63876, NIFTY 22500 PE **28 JUL 26**, qty=65)
   on 2026-06-08 via `record_paper_trade.py`.
2. June 8 EOD snapshot fetched chain for **June 30** (nearest monthly, DTE=22).
   July 28 contract is not in the June 30 chain → `ltp = 0`.
3. `get_positions` aggregated all 3 historical CSP cycles into one position:
   `avg_sell_price = 210.51` (blended), `entry_date = 2026-05-11` (first-ever sell),
   `days_held = 28`. Both PROFIT_TARGET (threshold = 63.15, ltp = 0 → fires) and
   TIME_STOP (28 ≥ 21 → fires) emitted as ACTION for a same-day entry.
4. Daemon on 2026-06-09 auto-executed CLOSE_AND_ROLL: closed 63876 at a loss (236.95),
   opened 55186 (NIFTY 22500 PE **30 JUN 26**, qty=1 — wrong quantity).
5. 55186 (June 30) is also not in the daemon's chain fetch (daemon fetches monthly=June 30
   but the chain API call goes to the same expiry, so this one IS in the chain — however
   `_find_chain_leg` fails to resolve a numeric key → ltp=0 again until BF-1 is deployed).
6. `record_trade` ON CONFLICT DO NOTHING silently skips the second close attempt
   (same strategy/leg/date/action key already exists). `_close_leg` returns normally.
   `_reentry_notification` runs. 13+ R5_REENTRY_BLOCKED Telegram messages sent at 90 s
   intervals until market close.

---

## BUG-1 — `get_positions` cross-cycle aggregation  *(ROOT CAUSE)*

**Introduced:** `69c7a49` — "refactor(paper): address Issue 1 and 2 in trade notes extraction and position querying" (2026-05-26)

**File:** `src/paper/store.py` — `get_positions()`

**Problem:**
`get_positions` groups ALL trades by `leg_role` across the entire trade history, including
closed cycles.  When a leg has been opened and closed multiple times (e.g. 3 CSP cycles),
all historical SELL trades contribute to `avg_sell_price` and the **oldest** SELL date
becomes `entry_date`.

Concrete impact on 2026-06-08 EOD:
- `avg_sell_price = (241.25 + 158.60 + 231.68) × 65 / 195 = 210.51` (should be 231.68)
- `entry_date = 2026-05-11` (should be 2026-06-08)
- `days_held = 28` (should be 0)

**Fix (`src/paper/store.py`):**
Reset all accumulators (`net_qty`, `buy_*`, `sell_*`, `first_sell_date`) to zero whenever
`net_qty` returns to 0 mid-loop.  Only the trades since the last flat point contribute to
the current open position's metrics.

```python
for row in rows_for_leg:
    instrument_key = row["instrument_key"]
    qty = row["quantity"]
    price = Decimal(row["price"])
    if TradeAction(row["action"]) == TradeAction.BUY:
        net_qty += qty
        buy_total_qty += qty
        buy_total_cost += price * qty
    else:
        net_qty -= qty
        sell_total_qty += qty
        sell_total_cost += price * qty
        if first_sell_date is None:
            raw = row["trade_date"]
            first_sell_date = date.fromisoformat(raw) if isinstance(raw, str) else raw

    # Reset when position goes flat — next trade starts a new cycle
    if net_qty == 0:
        buy_total_qty = 0
        buy_total_cost = Decimal("0")
        sell_total_qty = 0
        sell_total_cost = Decimal("0")
        first_sell_date = None
        instrument_key = ""
```

**Tests to add (`tests/unit/paper/test_store_positions.py`):**
- Two complete CSP cycles (open → close → open): assert `avg_sell_price` and `entry_date`
  reflect only the second cycle.
- Three cycles, middle one still open (net_qty != 0 mid-history): assert position reflects
  only the current open cycle.
- Single open position (no prior cycles): behaviour unchanged.

---

## BUG-2 — Chain fetched for wrong expiry → `ltp = 0` → false PROFIT_TARGET

**Introduced:** `8fd58d4` — "feat(paper,strategy): TradeState + five independent CSP evaluators (CR1b)" (2026-06-06) and `9191c02` — monitor daemon wiring

**Files:**
- `scripts/strategies/three_track/paper_3track_snapshot.py` — EOD chain fetch block
- `src/strategy/monitor.py` — `_tick()` / `_fetch_chain()`
- `src/strategy/csp_nifty_v1.py` — `check_signals`

**Problem — wrong-way-round chain fetch:**
Both the EOD snapshot and the daemon pick a chain expiry first using a hardcoded
preference (`["monthly", "quarterly"]`), then evaluate whatever open positions exist.
The correct direction is the reverse: **look at the open position's expiry, then fetch
that chain.**

On 2026-06-08, the open CSP was **NIFTY 22500 PE 28 JUL 26** (July 28, quarterly).
Both scripts fetched the June 30 chain (nearest monthly). July 28 is not in the June 30
chain. `_find_chain_leg` returns `None`. Code falls through to `ltp = Decimal("0")`,
which trivially satisfies `ltp ≤ 0.30 × entry_credit` → PROFIT_TARGET fires every time.

`OptionChain` already carries `expiry: date` (added in `src/models/options.py`), so the
fetched chain knows its own expiry — it just isn't being compared against the position's
expiry before evaluation.

**Fix — position-driven chain fetch:**

*EOD snapshot (`paper_3track_snapshot.py`):*

Replace the single hardcoded chain fetch with a per-position lookup:

```python
# After collecting all_positions, group by expiry
from datetime import datetime as _dt

chains_by_expiry: dict[date, OptionChain] = {}

for pos in all_positions:
    if pos.net_qty == 0:
        continue
    if lookup is None:
        continue
    inst = lookup.get_by_key(pos.instrument_key)
    if inst is None:
        logger.warning("exit_signals.instrument_not_found", key=pos.instrument_key)
        continue
    pos_expiry = _dt.fromtimestamp(inst["expiry"] / 1000).date()
    if pos_expiry in chains_by_expiry:
        continue  # already fetched
    try:
        expiry_str = pos_expiry.isoformat()
        raw = await broker.get_option_chain("NSE_INDEX|Nifty 50", expiry_str)
        chain_data = raw if isinstance(raw, list) else []
        chains_by_expiry[pos_expiry] = parse_upstox_option_chain(chain_data)
    except Exception as exc:
        logger.warning("exit_signals.chain_fetch_failed", expiry=str(pos_expiry), error=str(exc))

# Evaluate each position against its own chain
for pos in all_positions:
    if pos.net_qty == 0:
        continue
    inst = lookup.get_by_key(pos.instrument_key) if lookup else None
    if inst is None:
        continue
    pos_expiry = _dt.fromtimestamp(inst["expiry"] / 1000).date()
    chain = chains_by_expiry.get(pos_expiry)
    if chain is None:
        logger.warning("exit_signals.no_chain_for_position", key=pos.instrument_key)
        continue
    # pass single-position list + its chain to compute_and_record_exit_signals
```

*Daemon (`monitor.py` + `csp_nifty_v1.py`):*

`_fetch_chain` currently uses `_expiry_fn()` which returns the nearest monthly.
Change `_tick` to resolve the chain per-strategy from the strategy's open position expiry:

```python
for strategy in self._strategies:
    positions = self._store.get_positions(strategy.strategy_name)
    open_pos = [p for p in positions if p.net_qty != 0]
    chain = await self._fetch_chain_for_positions(open_pos)
    if chain is None:
        continue
    events = await strategy.check_signals(chain, positions)
    ...
```

Where `_fetch_chain_for_positions` resolves expiry from `InstrumentLookup` using the
position's `instrument_key`, then calls `broker.get_option_chain(instrument, expiry_str)`.
If positions span multiple expiries (e.g. CC on June 30, CSP on July 28), fetch each
once and pass the matching chain to each strategy.

*Immediate safety guard (both files, deploy before full fix):*

```python
# Current (BUG):
ltp = Decimal(str(leg.ltp)) if leg is not None else Decimal("0")

# Safe guard:
if leg is None:
    logger.warning(
        "dispatch_evaluate.leg_not_in_chain — skipping signals",
        instrument_key=pos.instrument_key,
        chain_expiry=str(chain.expiry),
    )
    return []   # in _dispatch_evaluate
    # or: continue   # in check_signals loop
ltp = Decimal(str(leg.ltp))
```

This guard must be applied in:
- `_dispatch_evaluate` (CSP branch, CC branch, PP branch, Collar branch)
- `CSPNiftyV1.check_signals` (put_leg None check)

**Tests to add:**
- EOD snapshot: open CSP in July 28 expiry → chain fetched for July 28, not June 30.
- EOD snapshot: two positions in different expiries → two separate chain fetches.
- `_dispatch_evaluate` with `leg=None` → returns `[]`, WARNING logged.
- `check_signals` with put_leg=None → skips position, no signal emitted.
- Daemon `_fetch_chain_for_positions`: position in quarterly expiry → fetches that chain.

---

## BUG-3 — `_open_new` hardcodes `quantity=1`

**Introduced:** `e62aee9` — "feat(strategy): CR1d — CSPNiftyV1 full automation" (2026-06-08)

**File:** `src/strategy/csp_nifty_v1.py` — `_open_new()` line 414

**Problem:**
```python
await open_new_csp_leg(..., quantity=1)
```
Should use the closed position's lot count.  Opened NSE_FO|55186 with 1 lot instead of 65.

**Fix:**
```python
# In apply_action, capture closed qty before removing from positions:
closed_qty = abs(short_put.net_qty)

# In _open_new call:
await open_new_csp_leg(..., quantity=closed_qty)
```
Pass `closed_qty` through `_open_new(remaining, today, quantity=closed_qty)` or read it
from the `short_put` reference passed to `_reentry_notification`.

**Tests to add:**
- `apply_action(CLOSE_AND_ROLL)` with a 65-lot position: assert new open trade has qty=65.
- `apply_action(CLOSE_AND_ROLL)` with a 1-lot position: assert new open trade has qty=1.

---

## BUG-4 — `record_trade` unique key excludes `instrument_key` → silent no-op enables notification flood

**Introduced:** `69c7a49` — "refactor(paper): address Issue 1 and 2" (2026-05-26)

**File:** `src/paper/store.py` — `paper_trades` schema, `record_trade()`

**Problem:**
Unique constraint: `UNIQUE(strategy_name, leg_role, trade_date, action)`.
`instrument_key` is excluded.  After the first successful close of the old position on
2026-06-09, any subsequent close attempt for the NEW position (same strategy, same leg,
same date, same action=BUY) hits `ON CONFLICT DO NOTHING` and silently returns False.
`_close_leg` returns normally (no exception), execution flows to `_open_new` →
`_reentry_notification` → Telegram.  This repeats every 90 s.

**Fix:**
Add `instrument_key` to the unique constraint:
```sql
UNIQUE(strategy_name, leg_role, instrument_key, trade_date, action)
```
Write an idempotent migration script (`scripts/dev/migrate_paper_trades_unique.py`)
that drops the old index and creates the new one.

Note: `record_paper_trade.py` intentional idempotency (re-running same args is safe) is
preserved — instrument_key is now part of the key, so exact re-runs still no-op correctly.

**Tests to add:**
- Two SELL trades for different `instrument_key` on same date/leg: both inserted, no conflict.
- Two SELL trades for same `instrument_key` on same date/leg: second is no-op, returns False.

---

## BUG-5 — `_check_reentry` sends Telegram on every call with no dedup

**Introduced:** `c9625e1` — "feat(strategy): add R5 re-entry eligibility check" / `fb38dde` — CC-2 ReEntryMixin

**File:** `src/strategy/reentry_mixin.py` — `_check_reentry()`

**Problem:**
`_check_reentry` unconditionally writes a `paper_exit_events` row and sends a
`send_plain_message` on every invocation.  Combined with BUG-4, this produced 13+
identical R5_REENTRY_BLOCKED Telegram messages on 2026-06-09 (one per daemon tick).

**Fix:**
Before writing the event and notifying, check for an existing OPEN event today:
```python
today_iso = today.isoformat()
existing_events = self._store.get_open_exit_events(
    strategy_name=self.strategy_name,
    leg_name=self.reentry_leg_role,
)
already_sent = any(
    ev["exit_signal"] in (ExitSignal.R5_REENTRY_BLOCKED.value, ExitSignal.R5_REENTRY_ELIGIBLE.value)
    and ev["event_time"][:10] == today_iso
    for ev in existing_events
)
if already_sent:
    log.debug(f"{self.strategy_name}.reentry_check_dedup — already sent today")
    return
```

**Tests to add:**
- `_check_reentry` called twice on the same day: DB row written once, Telegram sent once.
- `_check_reentry` called on two different days: both rows written, both notified.

---

---

## BUG-6 — `_compute_realized_pnl` cross-cycle averaging inflates realized P&L

**Discovered:** 2026-06-09 — P&L analysis session

**File:** `src/paper/tracker.py` — `_compute_realized_pnl()`

**Problem:**
The function buckets all trades for a `leg_role` together and computes realized P&L as
`(weighted_avg_sell - weighted_avg_buy) × closed_qty`, where `closed_qty = min(total_buy_qty, total_sell_qty)`.

When a leg has been through multiple cycles (close cycle 1, open cycle 2), the new open SELL
is averaged together with the closed cycle's SELL into a single `sell_avg`.  The function
cannot distinguish "this SELL closed a position" from "this SELL opened a new position".

**Concrete impact (2026-06-09):**
- `overlay_cc` for `paper_nifty_spot`:
  - Cycle 1: SELL 65 @ 221.38 (2026-05-11), BUY 65 @ 12.60 (2026-06-08) → correct realized = **+13,571**
  - Cycle 2: SELL 65 @ 543.90 (2026-06-09) — still open, no close yet
  - Bug: sell_avg = (221.38 + 543.90) / 2 = 382.64; realized = (382.64 − 12.60) × 65 = **+24,053** (wrong)
- Same error on `overlay_collar_call`: +24,028 reported vs +13,521 correct
- `overlay_collar_put`: similar mis-attribution
- Per-strategy reported realized: ~44,960 vs correct ~25,589
- Across two identical tracks (spot + proxy): apparent ~90k vs correct ~51k

The bug also causes the `paper_nav_snapshots` `realized_pnl` column to be wrong whenever
any overlay has been rolled (i.e. cycle 1 closed and cycle 2 opened on the same leg_role).

**Fix (`src/paper/tracker.py` — `_compute_realized_pnl`):**

Replace the aggregate-then-divide approach with FIFO round-trip matching.  Walk trades in
chronological order; for short-first legs each SELL opens a round-trip and the next BUY
closes it; for long-first legs vice versa.  Only fully closed round-trips contribute to
realized P&L.  An open position's entry price must never enter the realized calculation.

```python
def _compute_realized_pnl(store: PaperStore, strategy_name: str) -> Decimal:
    trades = store.get_trades(strategy_name)
    if not trades:
        return Decimal("0")

    total_realized = Decimal("0")

    for leg_role in sorted({t.leg_role for t in trades}):
        leg_trades = sorted(
            [t for t in trades if t.leg_role == leg_role],
            key=lambda t: t.trade_date,
        )
        # Determine open direction from first trade
        first_action = leg_trades[0].action
        opens  = [t for t in leg_trades if t.action == first_action]
        closes = [t for t in leg_trades if t.action != first_action]

        for open_trade, close_trade in zip(opens, closes):
            if first_action == TradeAction.SELL:
                # Short leg: profit = sell_price - buy_price
                realized = (open_trade.price - close_trade.price) * open_trade.quantity
            else:
                # Long leg: profit = sell_price - buy_price
                realized = (close_trade.price - open_trade.price) * open_trade.quantity
            total_realized += realized

    return total_realized
```

Note: this assumes each round-trip uses the same quantity per leg.  If partial closes are
ever supported, replace `zip` with a proper FIFO queue consuming qty from both sides.

**Tests to add (`tests/unit/paper/test_tracker_realized_pnl.py`):**
- Single closed cycle (short leg): realized = (sell − buy) × qty.
- Two cycles, second still open: realized reflects only cycle 1; cycle 2 SELL not included.
- Long-first leg (PP): closed cycle realized = (exit_sell − entry_buy) × qty.
- No trades: returns Decimal("0").

---

## Fix Dependency Order

```
BUG-1 (get_positions)     ← fix first; corrects avg_sell_price + entry_date for all strategies
BUG-2 (ltp=0 guard)       ← fix second; independent of BUG-1 but blocks false signals
BUG-3 (_open_new qty=1)   ← fix third; safe standalone change
BUG-4 (unique key)        ← requires migration script; coordinate with BUG-1 fix
BUG-5 (reentry dedup)     ← fix last; lowest blast radius
BUG-6 (_compute_realized_pnl) ← fix after BUG-1; both touch tracker.py / realized P&L path
```

## DB Cleanup Required (2026-06-09)

```sql
-- Close the erroneous 1-lot position opened by the daemon
-- (run via record_paper_trade.py or direct SQL after stopping daemon)
-- Dismiss stale OPEN exit events from June 8–9
UPDATE paper_exit_events
SET status = 'DISMISSED'
WHERE id IN (15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25)
  AND strategy_name = 'paper_csp_nifty_v1';
```

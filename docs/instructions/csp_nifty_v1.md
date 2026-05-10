# Cash-Secured Put — Nifty 50 v1 — Operator Guide

> Source of truth for strategy spec: `docs/strategies/csp_nifty_v1.md`
> This guide covers the operational workflow only: what to run, when, and in what order.

---

## Purpose

A single-leg short put on Nifty 50 index options, collateralised by the pledged NiftyBees ETF
holding. The strategy sells monthly puts at 0.20–0.35 delta and manages them to expiry (or rolls
at DTE ≤ 5 if needed). Premium collected is the sole return source.

**Strategy namespace:** `paper_csp_nifty_v1`  
**Leg role:** `short_put`  
**Lot size:** 75 (verify against NSE circular before each cycle)  
**Underlying:** `NSE_INDEX|Nifty 50`  
**Collateral:** NiftyBees ETF (`NSE_EQ|INF204KB14I2`) — already pledged

---

## Lifecycle Overview

```
Cycle start (once per expiry cycle, ~25–35 DTE)
  └── record_paper_trade.py --no-dry-run                        ← auto-selects expiry + best strike
      └── (optional) find_strike_by_delta.py                    ← explore full ranked table first

Daily at 15:35 IST (cron)
  └── paper_snapshot.py                     ← mark-to-market P&L

At DTE ≤ 5 (or stop-loss hit)
  └── record_paper_trade.py  (BUY to close) ← close expiring leg
      └── find_strike_by_delta.py --dry-run ← pick next strike
          └── record_paper_trade.py (SELL)  ← open replacement leg
```

There is no automated roll script for CSP. Rolling is two sequential `record_paper_trade.py`
calls — close the old leg, open the new one.

---

## Step 1 — Find the Strike

Run **before entry and before every roll**. Fetches the live Upstox option chain, filters puts
in the 0.20–0.35 delta band, prints a ranked table, and (with `--dry-run`) emits a
ready-to-paste `record_paper_trade.py` command for each candidate.

```bash
# Full table + ready-to-paste commands (auto-selects monthly expiry):
python scripts/find_strike_by_delta.py

# Table only (suppress command block):
python scripts/find_strike_by_delta.py --no-dry-run

# Override to a specific expiry:
python scripts/find_strike_by_delta.py --expiry 2026-05-29

# Override delta range or option side:
python scripts/find_strike_by_delta.py \
    --delta-min 0.15 --delta-max 0.30 \
    --option-type PE
```

**Reading the table:** Columns are `EXPIRY | LABEL | SIDE | STRIKE | DELTA | IV% | LTP | MID | BID | ASK | OI | KEY`.
LABEL shows the expiry type (monthly/quarterly/yearly). Rows are ranked: round-100 strikes first,
then tighter spread, then highest OI — across all candidate expiries merged into one pool.
The dry-run commands use mid-price `(bid+ask)/2` when both sides are non-zero; falls back to LTP.
Copy the command for your chosen row and run it directly — key and mid-price are embedded.

**Entry timing:** Run between 10:00–11:00 AM IST after the opening noise settles. Re-run if
more than 15 minutes elapse before you record — mid-price drifts.

---

Run this directly to fetch the chain, rank candidates, pick rank 1, and resolve the price (mid-price) automatically.

```bash
# Preview (dry-run default — RECOMMENDED, auto-selects monthly expiry):
python scripts/record_paper_trade.py

# Write to DB (rank 1 — default):
python scripts/record_paper_trade.py --no-dry-run

# Write to DB (pick rank 2):
python scripts/record_paper_trade.py --index 2 --no-dry-run

# Force a specific expiry:
python scripts/record_paper_trade.py --expiry 2026-05-29 --no-dry-run
```

**Alternative — Manual resolution** (copy-paste command from `find_strike_by_delta.py` output):

```bash
# PE 24000 | delta=-0.2513 | iv=12.40%
python scripts/record_paper_trade.py \
    --key "NSE_FO|<instrument_key>" \
    --price 87.50 \
    --no-dry-run
```

**Alternative — BOD lookup** (offline search from BOD JSON):

```bash
python scripts/record_paper_trade.py \
    --underlying NIFTY \
    --strike 24000 \
    --option-type PE \
    --expiry 2026-05-29 \
    --price 87.50 \
    --no-dry-run
```

**Add `--notes`** to record entry rationale:

```bash
python scripts/record_paper_trade.py \
    --notes "entry: rank 1, IVR 42, 28 DTE" \
    --no-dry-run
```

---

## Step 3 — Daily Snapshot (cron)

Runs **every trading day at 15:35 IST**. Fetches live LTP for all open paper positions,
computes unrealised P&L, writes a `PaperNavSnapshot`. Safe to run multiple times — idempotent
upsert.

```bash
# Inspect P&L (dry-run default — no DB write):
python scripts/paper_snapshot.py --strategy paper_csp_nifty_v1

# With known underlying price:
python scripts/paper_snapshot.py --strategy paper_csp_nifty_v1 --underlying-price 24385.00

# Write snapshot (cron / end-of-day save):
python scripts/paper_snapshot.py --strategy paper_csp_nifty_v1 --no-dry-run

# Snapshot all paper strategies at once (omit --strategy):
python scripts/paper_snapshot.py
```

**Cron line (15:35 IST = 10:05 UTC):**

```
5 10 * * 1-5  cd /path/to/NiftyShield && python scripts/paper_snapshot.py --strategy paper_csp_nifty_v1 --no-dry-run
```

---

## Step 4 — Roll the Position (manual)

No automated roll script exists for CSP. Roll at **DTE ≤ 5** (or earlier on a stop-loss).
Rolling is two `record_paper_trade.py` calls executed back-to-back.

### 4a — Close the expiring leg

```bash
python scripts/record_paper_trade.py \
    --key "NSE_FO|<old_instrument_key>" \
    --action BUY \
    --price 12.50 \
    --notes "roll-close: 4 DTE, locking ₹75.00 realized" \
    --no-dry-run
```

### 4b — Find the new strike

Re-run Step 1 (auto-selects the next eligible monthly expiry from BOD):

```bash
python scripts/find_strike_by_delta.py
```

### 4c — Open the replacement leg

Copy the emitted command (it already contains `--no-dry-run`):

```bash
python scripts/record_paper_trade.py \
    --notes "roll-open: Jun expiry, 0.25 delta, spot 24420" \
    --no-dry-run

# Or with explicit key if you inspected the table first:
python scripts/record_paper_trade.py \
    --key "NSE_FO|<new_instrument_key>" \
    --price 94.00 \
    --notes "roll-open: Jun expiry, 0.25 delta, spot 24420" \
    --no-dry-run
```

**Atomicity note:** There is no DB-level transaction guaranteeing close+open succeed together.
If the open fails after the close is written, the strategy has no open position. Re-run Step 2
immediately to restore. Check with:

```bash
python - <<'EOF'
import sys; sys.path.insert(0, ".")
from src.paper.store import PaperStore
store = PaperStore("data/portfolio/portfolio.sqlite")
trades = store.get_trades("paper_csp_nifty_v1", "short_put")
print(f"\npaper_csp_nifty_v1 — short_put ({len(trades)} open trades):")
for t in trades:
    print(f"  {t.trade_date}  {t.action.value:<4}  qty={t.quantity}  price={t.price}  key={t.instrument_key}")
EOF
```

---

## Stop-Loss Rules

Per strategy spec (`docs/strategies/csp_nifty_v1.md`):

- **Intra-cycle stop:** Close if unrealised loss reaches 2× premium collected on entry.
- **Delta breach:** If short put delta crosses −0.50 (deep ITM), evaluate closing regardless of DTE.
- **VIX spike:** If India VIX jumps > 25% in a single session, run the snapshot dry-run, assess
  delta, and decide whether to hold or close before EOD.

Record any stop-loss close with `--notes "stop-loss: <reason>"` for later attribution analysis.

---

## Verifying Open Positions

Quick DB check at any time:

```bash
python - <<'EOF'
import sys; sys.path.insert(0, ".")
from src.paper.store import PaperStore
store = PaperStore("data/portfolio/portfolio.sqlite")
trades = store.get_trades("paper_csp_nifty_v1")
print(f"\npaper_csp_nifty_v1 — all legs ({len(trades)} trades):")
for t in trades:
    print(f"  {t.trade_date}  {t.leg_role:<14}  {t.action.value:<4}  qty={t.quantity}  price={t.price}")
EOF
```

---

## Environment Prerequisites

Required in `.env`:

```
UPSTOX_ANALYTICS_TOKEN=<long-lived analytics token>  # all market-data fetches
```

BOD instruments file must be current (needed for auto-expiry and `--underlying/--strike` lookup
mode): `data/instruments/NSE.json.gz`

---

## Quick Reference

| Task | Command | When |
|------|---------|------|
| Explore strikes | `python scripts/find_strike_by_delta.py` | Optional exploration |
| Preview entry (auto) | `python scripts/record_paper_trade.py` | Cycle start, 10:00–11:00 AM IST |
| Record entry (auto) | `python scripts/record_paper_trade.py --no-dry-run` | Cycle start |
| Record entry (manual) | `python scripts/record_paper_trade.py --key "NSE_FO|..." --price NNN.NN --no-dry-run` | Copy-paste from find_strike |
| Close expiring leg | `python scripts/record_paper_trade.py --key "NSE_FO|..." --action BUY --price NNN.NN --no-dry-run` | DTE ≤ 5 or stop-loss |
| Open replacement leg | `python scripts/record_paper_trade.py --no-dry-run` | Immediately after close |
| Inspect P&L (no write) | `python scripts/paper_snapshot.py --strategy paper_csp_nifty_v1` | Ad hoc |
| Write daily snapshot | `python scripts/paper_snapshot.py --strategy paper_csp_nifty_v1 --no-dry-run` | 15:35 IST cron |
| Verify open positions | inline Python snippet above | Any time |

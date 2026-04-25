# Paper Trading — Workflow Reference

> End-to-end guide: find an instrument, record entry, mark-to-market daily,
> record exit, inspect P&L.  All scripts are standalone — no connection to
> `daily_snapshot.py` or the live trades ledger.

---

## Prerequisites

### 1 — BOD instrument file (offline option lookup)

Download the Upstox exchange instrument list once per trading day (or as needed):

```bash
curl -o data/instruments/NSE.json.gz \
  https://assets.upstox.com/market-quote/instruments/exchange/NSE.json.gz
```

Without this file `--underlying` / `--strike` / `--option-type` / `--expiry`
lookup will fail.  The file is not committed to git (`data/instruments/` is
in `.gitignore`).

### 2 — Environment

```bash
export UPSTOX_ENV=prod               # prod | sandbox | test
export UPSTOX_ACCESS_TOKEN=...       # daily OAuth token
export UPSTOX_ANALYTICS_TOKEN=...    # long-lived market data token
```

`UPSTOX_ENV=test` uses `MockBrokerClient` (no network calls) — safe for
exploring without live tokens.

---

## Step 1 — Find the instrument key

### Option A: auto-lookup (recommended)

Use `record_paper_trade.py` with lookup flags.  The `--expiry` filter
narrows to a specific expiry.  Without it, all matching strikes across all
expiries are listed.

```bash
# List all NIFTY PE at 23000 across every expiry (browse available expiries):
python scripts/record_paper_trade.py \
    --strategy paper_csp_nifty_v1 --leg short_put \
    --underlying NIFTY --strike 23000 --option-type PE \
    --date 2026-05-01 --action SELL --qty 75 --price 120 \
    --dry-run

# Narrow to May 29 expiry:
python scripts/record_paper_trade.py \
    --strategy paper_csp_nifty_v1 --leg short_put \
    --underlying NIFTY --strike 23000 --option-type PE --expiry 2026-05-29 \
    --date 2026-05-01 --action SELL --qty 75 --price 120 \
    --dry-run
```

If a single instrument matches it is printed and the dry-run confirms the
trade without inserting.  If multiple match, the list is printed — supply
`--key` directly (Option B).

### Option B: standalone lookup script

```bash
python scripts/instrument_lookup.py --type PE --underlying NIFTY --strike 23000
```

Copy the `instrument_key` from the output (format: `NSE_FO|XXXXXXX`).

### Option C: Upstox web terminal

Open the Upstox option chain, hover over the contract — the URL contains the
instrument key.

---

## Step 2 — Record entry

### With auto-lookup (single matching instrument):

```bash
python scripts/record_paper_trade.py \
    --strategy paper_csp_nifty_v1 \
    --leg short_put \
    --underlying NIFTY \
    --strike 23000 \
    --option-type PE \
    --expiry 2026-05-29 \
    --date 2026-05-01 \
    --action SELL \
    --qty 75 \
    --price 120.50 \
    --notes "entry at mid; delta ~0.25; IVR 62"
```

### With explicit key:

```bash
python scripts/record_paper_trade.py \
    --strategy paper_csp_nifty_v1 \
    --leg short_put \
    --key "NSE_FO|12345678" \
    --date 2026-05-01 \
    --action SELL \
    --qty 75 \
    --price 120.50 \
    --notes "entry at mid; delta ~0.25; IVR 62"
```

Output confirms strategy, leg, net qty, direction, and average sell price:

```
Resolved instrument: NIFTY26MAY23000PE  (NSE_FO|12345678)
paper_csp_nifty_v1 / short_put: -75 units (short) @ avg ₹120.50
```

**Paper prefix rule:** `--strategy` must start with `paper_`.  The script
exits with code 1 if it does not.

**Idempotency:** inserting the same (strategy, leg, date, action) twice is a
no-op — the `ON CONFLICT DO NOTHING` constraint silently drops the duplicate.

---

## Step 3 — Daily mark-to-market

Run after market close (or at any point intraday) to record a P&L snapshot.

```bash
# All known paper strategies:
python scripts/paper_snapshot.py

# Single strategy with known underlying price:
python scripts/paper_snapshot.py \
    --strategy paper_csp_nifty_v1 \
    --underlying-price 23250.5

# Historical date (e.g. backfilling):
python scripts/paper_snapshot.py --date 2026-05-01

# Dry run — prints P&L without writing to DB:
python scripts/paper_snapshot.py --dry-run
```

Output:

```
paper_csp_nifty_v1 — 2026-05-01
  unrealized : ₹1,350.00
  realized   : ₹0.00
  total P&L  : ₹1,350.00
  underlying : ₹23,250.50
```

The snapshot is idempotent — re-running for the same (strategy, date) updates
the existing row.  Schedule this in cron alongside `daily_snapshot.py` if
desired, or run manually.

---

## Step 4 — Record exit

Use `record_paper_trade.py` with the opposite action.  For a short put opened
via SELL, close via BUY:

```bash
python scripts/record_paper_trade.py \
    --strategy paper_csp_nifty_v1 \
    --leg short_put \
    --key "NSE_FO|12345678" \
    --date 2026-05-15 \
    --action BUY \
    --qty 75 \
    --price 45.00 \
    --notes "21-DTE time stop; bought back at 37.5% of credit"
```

Output when fully closed:

```
paper_csp_nifty_v1 / short_put: position closed (net qty = 0)
```

---

## Step 5 — Inspect P&L

### Via paper_snapshot.py dry-run:

```bash
python scripts/paper_snapshot.py --strategy paper_csp_nifty_v1 --dry-run
```

### Direct DB query:

```bash
sqlite3 data/portfolio/portfolio.sqlite \
  "SELECT snapshot_date, unrealized_pnl, realized_pnl, total_pnl
   FROM paper_nav_snapshots
   WHERE strategy_name = 'paper_csp_nifty_v1'
   ORDER BY snapshot_date DESC LIMIT 10;"
```

### All paper positions (current open):

```bash
sqlite3 data/portfolio/portfolio.sqlite \
  "SELECT strategy_name, leg_role,
          SUM(CASE action WHEN 'SELL' THEN -quantity ELSE quantity END) AS net_qty
   FROM paper_trades
   GROUP BY strategy_name, leg_role
   HAVING net_qty != 0;"
```

---

## Strategy naming convention

| Strategy | Description |
|---|---|
| `paper_csp_nifty_v1` | Cash-secured put on Nifty 50 index options, V1 rules |
| `paper_ic_nifty_v1` | Iron condor on Nifty (if/when started) |

All paper strategy names **must start with `paper_`** — this is the sole
runtime guard preventing live/paper ledger cross-contamination.

---

## Cron integration (optional)

To run mark-to-market automatically at 3:30 PM after each market session,
add to crontab:

```
30 15 * * 1-5  cd /path/to/NiftyShield && python scripts/paper_snapshot.py >> logs/paper_snapshot.log 2>&1
```

---

## Key files

| File | Purpose |
|---|---|
| `scripts/record_paper_trade.py` | Record entry / exit for a single leg |
| `scripts/paper_snapshot.py` | Daily mark-to-market (P&L + DB snapshot) |
| `src/paper/models.py` | `PaperTrade`, `PaperPosition`, `PaperNavSnapshot` |
| `src/paper/store.py` | `PaperStore` — `paper_trades` + `paper_nav_snapshots` tables |
| `src/paper/tracker.py` | `PaperTracker` — compute_pnl, record_daily_snapshot |
| `src/paper/CLAUDE.md` | Module invariants (read before touching src/paper/) |
| `data/instruments/NSE.json.gz` | Offline BOD instrument file (download daily) |
| `data/portfolio/portfolio.sqlite` | Shared SQLite DB (paper tables have `paper_` prefix) |

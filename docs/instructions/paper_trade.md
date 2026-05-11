# Paper Trading — Full Flow Operator Guide

> Covers the complete daily/monthly workflow across both strategies:
> 3-Track Nifty Long Comparison and CSP Nifty (paper_csp_nifty_v1).
>
> For strategy context see `docs/instructions/3track.md` and `docs/instructions/csp_nifty_v1.md`.
> This guide is operations-only: what to run, when, and in what order.

---

## Lifecycle Overview

```
ENTRY (once per cycle)          OVERLAY (once per cycle)       EOD CRON (daily)
─────────────────────           ──────────────────────         ─────────────────
paper_3track_entry.py     →     record_paper_trade.py    →     paper_3track_snapshot.py
                                (CSP short put leg)             paper_snapshot.py
                          →     paper_3track_overlay_roll.py
                                (roll overlays near expiry)
```

**Month start**: Open 3-track base legs + CSP short put.
**Monthly ongoing**: Add / roll overlay legs (PP, CC, collar) via `record_paper_trade.py`.
**Near expiry (DTE ≤ 5)**: Run `paper_3track_overlay_roll.py` to roll expiring overlays.
**Every market day**: Run both snapshot scripts to mark-to-market.

---

## Step 1 — Open 3-Track Base Legs

```bash
python3 scripts/paper_3track_entry.py
```

**What this does**: Finds the best available Nifty instruments (spot, front-month futures,
deep ITM CE proxy) for the current cycle and prints a ranked candidate table. No DB write
until you confirm.

**Default behaviour**: Preview mode — prints candidates, writes nothing.

**To write to DB**:
```bash
python3 scripts/paper_3track_entry.py --confirm
```

### Overrides

| Flag | Default | When to use |
|------|---------|-------------|
| `--confirm` | off (preview) | Commit the selected candidates to DB |
| `--expiry YYYY-MM-DD` | auto (nearest monthly) | Pin a specific expiry date |
| `--cycle YYYYMM` | auto (current month) | Override the cycle month |
| `--bod-path PATH` | `data/instruments/NSE.json.gz` | Point to a different BOD file |
| `--db-path PATH` | `data/portfolio/portfolio.sqlite` | Use a different SQLite DB |
| `--index N` | 0 (top-ranked) | Select Nth candidate instead of the best one — see below |

### The `--index` option

In preview mode, the script prints a **ranked table** of candidates for each track leg
(futures contracts, proxy CE strikes, etc.). Row 0 is the top recommendation. If the
top pick is unsuitable (e.g., liquidity thin, strike is at an awkward level), pass
`--index 1` or `--index 2` to select the next candidate down.

```
# Preview — see the ranked list first
python3 scripts/paper_3track_entry.py

# Then confirm with the 2nd-ranked candidate (row 1)
python3 scripts/paper_3track_entry.py --confirm --index 1
```

---

## Step 2 — Open CSP Short Put Leg

The CSP strategy (`paper_csp_nifty_v1`) has one leg: a short monthly put at ~22-delta.
There is no auto-entry script for CSP — use `record_paper_trade.py` directly.

```bash
python3 scripts/record_paper_trade.py \
  --strategy paper_csp_nifty_v1 \
  --leg short_put \
  --action SELL \
  --underlying NSE_INDEX|Nifty\ 50 \
  --option-type PE
```

**Default behaviour**: Dry-run — prints what would be recorded, writes nothing.

**To write to DB**, add `--no-dry-run`:
```bash
python3 scripts/record_paper_trade.py --no-dry-run \
  --strategy paper_csp_nifty_v1 \
  --leg short_put \
  --action SELL \
  --underlying NSE_INDEX|Nifty\ 50 \
  --option-type PE
```

The script auto-selects the best expiry and strike from the live chain. The `--index N`
flag selects the Nth candidate from the ranked strike list (default 0 = top pick).

### Closing a CSP leg at expiry / stop-loss

```bash
python3 scripts/record_paper_trade.py --no-dry-run \
  --strategy paper_csp_nifty_v1 \
  --leg short_put \
  --action BUY \
  --close
```

`--close` resolves the instrument key and fetches LTP automatically. No `--key` or
`--price` needed when closing an existing position.

### Key overrides for `record_paper_trade.py`

| Flag | Default | When to use |
|------|---------|-------------|
| `--no-dry-run` | dry-run | Commit the trade to DB |
| `--index N` | 0 | Select Nth candidate from the ranked strike list |
| `--expiry YYYY-MM-DD` | auto (chain lookup) | Pin a specific expiry |
| `--strike FLOAT` | auto | Force a specific strike price |
| `--key INSTRUMENT_KEY` | auto | Bypass chain lookup; use a known key directly |
| `--price FLOAT` | auto (LTP on `--close`) | Override the trade price |
| `--close` | off | Mark action as closing; resolves key and price from DB position |
| `--notes TEXT` | none | Attach a free-text note to the trade record |
| `--db-path PATH` | `data/portfolio/portfolio.sqlite` | Use a different SQLite DB |

---

## Step 3 — Add Overlay Legs (3-Track)

Overlay legs (Protective Put, Covered Call, Collar) are added with `record_paper_trade.py`
specifying the overlay strategy namespace.

```bash
# Example: add a Protective Put overlay on the spot track
python3 scripts/record_paper_trade.py \
  --strategy paper_nifty_spot \
  --leg overlay_pp \
  --action SELL \
  --underlying NSE_INDEX|Nifty\ 50 \
  --option-type PE
```

To add via the overlay automation script (which handles all three tracks at once):

```bash
# Preview
python3 scripts/paper_3track_overlay.py --overlay pp

# Write
python3 scripts/paper_3track_overlay.py --overlay pp --no-dry-run --yes
```

`--overlay` accepts `pp`, `cc`, or `collar`. Same `--index N` logic applies.

---

## Step 4 — Roll Expiring Overlays

Run this in the last week before expiry (DTE ≤ 5 triggers automatically).

```bash
python3 scripts/paper_3track_overlay_roll.py
```

**Default behaviour**: Dry-run — shows what would be rolled, writes nothing.

# Execute the roll (after reviewing dry-run output):
python3 scripts/paper_3track_overlay_roll.py --no-dry-run --yes

The roll is atomic: it closes the expiring leg and opens the next-cycle leg in a single
transaction, with rollback on failure.

### Overrides

| Flag | Default | When to use |
|------|---------|-------------|
| `--no-dry-run` | off (dry-run) | Execute the roll |
| `--force` | off | Bypass the DTE ≤ 5 gate (use for out-of-cycle testing only) |
| `--tracks A,B,C` | all tracks | Limit roll to specific tracks |
| `--date YYYY-MM-DD` | today | Override the reference date |

---

## Step 5 — EOD Snapshot (3-Track)

Mark-to-market all 3-track positions and write daily P&L snapshots.

```bash
python3 scripts/paper_3track_snapshot.py
```

**Default behaviour**: Dry-run — preview proposed P&L, writes nothing.

**To write (live save)**:
```bash
python3 scripts/paper_3track_snapshot.py --no-dry-run
```

### Overrides

| Flag | Default | When to use |
|------|---------|-------------|
| `--no-dry-run` | off | Write snapshot to DB |
| `--spot FLOAT` | live fetch | Pass today's Nifty spot manually (e.g., market closed) |
| `--tracks A,B,C` | all | Limit snapshot to specific tracks |
| `--date YYYY-MM-DD` | today | Backfill a missed snapshot date |

---

## Step 6 — EOD Snapshot (CSP)

```bash
python3 scripts/paper_snapshot.py --strategy paper_csp_nifty_v1
```

**Default behaviour**: Dry-run — prints P&L, writes nothing.

**To write**:
```bash
python3 scripts/paper_snapshot.py --no-dry-run --strategy paper_csp_nifty_v1
```

### Overrides

| Flag | Default | When to use |
|------|---------|-------------|
| `--no-dry-run` | dry-run | Write the snapshot to DB |
| `--spot FLOAT` | live fetch | Pass today's Nifty spot manually |
| `--date YYYY-MM-DD` | today | Backfill a missed snapshot date |

---

## Quick Reference

| Script | Purpose | Safe by default? | Write flag |
|--------|---------|-----------------|------------|
| `paper_3track_entry.py` | Open 3-track base legs | ✓ preview | `--confirm` |
| `record_paper_trade.py` | Record any single leg (CSP, overlay, close) | ✓ dry-run | `--no-dry-run` |
| `paper_3track_overlay_roll.py` | Roll expiring overlay legs | ✓ dry-run | `--no-dry-run --yes` |
| `paper_3track_snapshot.py` | EOD mark-to-market (3-track) | ✓ dry-run | `--no-dry-run` |
| `paper_snapshot.py` | EOD mark-to-market (CSP) | ✓ dry-run | `--no-dry-run` |

**Rule of thumb**: always run without the write flag first to inspect output, then re-run
with the write flag to commit.

---

## Monthly Checklist

```
[ ] Month start
    [ ] paper_3track_entry.py --confirm           # open 3-track base legs
    [ ] record_paper_trade.py --no-dry-run        # open CSP short put
    [ ] paper_3track_overlay.py --overlay pp --no-dry-run --yes  # add protective put overlays

[ ] Every market day
    [ ] paper_3track_snapshot.py --no-dry-run     # 3-track EOD P&L
    [ ] paper_snapshot.py --no-dry-run --strategy paper_csp_nifty_v1  # CSP EOD P&L

[ ] When DTE ≤ 5 (expiry week)
    [ ] paper_3track_overlay_roll.py --no-dry-run --yes        # roll expiring overlays

[ ] Month end / CSP expiry
    [ ] record_paper_trade.py --no-dry-run --close  # close CSP short put
```

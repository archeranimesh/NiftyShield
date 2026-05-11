# 3-Track Nifty Long Comparison — Operator Guide

> Source of truth for strategy spec: `docs/strategies/nifty_track_comparison_v1.md`
> This guide covers the operational workflow only: what to run, when, and in what order.

---

## Purpose

This is a **controlled research framework**, not a live strategy. It runs three structurally
distinct ways to hold 1 Nifty lot of long exposure simultaneously, then measures how each
performs with and without protection overlays.

**Two research questions:**

1. Given identical notional exposure (NEE = Nifty spot × 65), do Spot / Futures / Proxy
   produce materially different returns over 6+ monthly cycles?
2. Which overlay structure (Protective Put, Covered Call, Collar) delivers the best
   protection at the lowest running cost on each base instrument?

The comparison is only meaningful after **≥ 6 complete monthly cycles** with at least one
high-VIX event (India VIX > 18) observed during the window.

**Three tracks:**

| Track | Strategy namespace | Base instrument | Capital at risk |
|-------|--------------------|-----------------|-----------------|
| A — Spot | `paper_nifty_spot` | NiftyBees ETF (delivery) | Full NEE (~₹15.5L) |
| B — Futures | `paper_nifty_futures` | Nifty front-month futures (1 lot) | SPAN margin ~₹1.5L |
| C — Proxy | `paper_nifty_proxy` | Deep ITM CE (delta ≈ 0.90) | Premium only (~₹2–3L) |

**NEE (Notional Equivalent Exposure):** `nifty_spot × lot_size`. At Nifty ~24,000 and
lot_size = 65 → NEE ≈ ₹15,60,000. All three tracks are sized to one NEE unit. Always
divide returns by full NEE for cross-track comparison — never by capital posted.

**⚠ Lot size:** Hardcoded as `65` in three scripts. Verify against NSE circular before
each new cycle. NSE revises lot sizes periodically.

---

## Overlay Menu and Blocked Combinations

| Overlay | Spot | Futures | Proxy |
|---------|------|---------|-------|
| Protective Put (PP) — BUY PE, ~8–10% OTM | ✅ | ✅ (creates synthetic long call — record for completeness) | ✅ (creates bull call spread) |
| Covered Call (CC) — SELL CE, ~3–5% OTM | ✅ | 🚫 **BLOCKED** | ✅ |
| Collar (PP + CC together) | ✅ | ✅ (collar only — standalone CC is permanently blocked) | ✅ |

**Hard block:** `paper_nifty_futures` + standalone `overlay_cc` = synthetic short put =
unlimited downside. Violates MISSION.md Principle I. Every script enforces this automatically
and will reject the combination.

---

## Lifecycle Overview

```
Cycle start (once per cycle, ~30–45 DTE)
  └── paper_3track_entry.py           ← base legs: 3 trades written

Overlay entry (same day or next session)
  └── paper_3track_overlay.py         ← live-fetch path (recommended)
  OR
  └── find_overlay_strikes.py         ← generates overlay_entry.yaml
      └── paper_3track_overlay_entry.py  ← YAML path

Daily at 15:35 IST (cron)
  └── paper_3track_snapshot.py        ← P&L + Greeks + delta-from-yesterday

Weekly — check DTE on overlay legs
  └── paper_3track_overlay_roll.py    ← rolls overlays at DTE ≤ 5

Monthly — full cycle roll
  └── Same as Cycle start (re-enter all base legs)
```

---

## Step 1 — Base Leg Entry

Run **once at cycle start** — the Wednesday after the current monthly expiry, at 10:00–10:30 AM IST.
All three tracks must enter on the same day.

```bash
# Preview (default — no DB write):
python scripts/paper_3track_entry.py

# Review the table, then confirm:
python scripts/paper_3track_entry.py --confirm
```

**What it does:** Connects to Upstox, fetches the option chain across monthly + quarterly + yearly
expiries, auto-selects the best DITM CE (delta 0.85–0.95, round-100 strike preferred, tightest
spread, highest OI), fetches NiftyBees LTP and futures LTP, computes NiftyBees qty, prints a
ranked candidate table, writes all three base legs on `--confirm`.

**Optional overrides:**

```bash
# Pin proxy to a specific expiry (if BOD auto-detect is wrong):
python scripts/paper_3track_entry.py --expiry 2026-05-29

# Tag as Cycle 2:
python scripts/paper_3track_entry.py --cycle 2 --confirm
```

**Gate checks (warn-only, not blocking):**

- Proxy OI ≥ 5,000
- Proxy bid-ask spread ≤ ₹5.00

If either gate warns, inspect the order book before confirming. Do not blindly proceed on a
warn — thin OI or wide spread inflates realised slippage.

---

## Step 2 — Overlay Entry

### How overlays work across tracks

One option contract is selected per overlay type. The same `instrument_key` is then recorded
as a separate leg against each eligible strategy namespace. This is not three independently
managed positions — it is one option tracked in three accounting buckets for comparison.

| Overlay | Tracks it applies to | DB rows written |
|---------|----------------------|-----------------|
| PP | spot, futures, proxy | 3 |
| CC | spot, proxy only (futures permanently blocked) | 2 |
| Collar | spot, futures, proxy | 6 (put + call per track) |

### Which option is selected

**PP — Buy PE:** 8–10% OTM below spot, target 9%. At Nifty 24,000 → target strike ~21,840.

**CC — Sell CE:** 3–5% OTM above spot, target 4%. At Nifty 24,000 → target strike ~24,960.

Both use the same ranking algorithm: round-100 strikes preferred over 50-increment → tightest
₹2 spread bucket → highest OI within that bucket → OTM proximity to target as final tiebreaker.
Expiry preference for both: quarterly (DTE 46–200) → yearly (DTE 201–420) → monthly (DTE 15–45),
using whichever expiry has spread_pct ≤ 3%. Falls back to monthly if no expiry passes the gate.

### Commands

```bash
# PP — preview then confirm:
python -m scripts.paper_3track_overlay --overlay pp
python -m scripts.paper_3track_overlay --overlay pp --no-dry-run --yes

# CC — preview then confirm (futures track is auto-skipped with a warning):
python -m scripts.paper_3track_overlay --overlay cc
python -m scripts.paper_3track_overlay --overlay cc --no-dry-run --yes

# Collar — preview then confirm:
python -m scripts.paper_3track_overlay --overlay collar
python -m scripts.paper_3track_overlay --overlay collar --no-dry-run --yes
```

### Reading the candidate table

Each command prints a ranked candidate table before the confirmation table — same format
as `paper_3track_entry.py`. Columns: `Rk | Expiry | Label | Strike | OTM% | OI | Bid | Ask | Sprd% | G`.
The `G` column is the spread gate (✓ = spread_pct ≤ 3%, ✗ = fails gate). The auto-selected
candidate is marked `◀`.

The confirmation table includes a **Type** column (PE/CE) so collar rows are unambiguous —
BUY PE rows and SELL CE rows appear separately per track.

### Selecting a non-default candidate

By default the top-ranked candidate (rank 1, marked `◀`) is used. To pick a different
candidate from the table, add `--index N` on the commit run:

```bash
# Dry-run — review the candidate table, note the rank you want:
python -m scripts.paper_3track_overlay --overlay pp

# Commit with rank 2 instead of rank 1:
python -m scripts.paper_3track_overlay --overlay pp --no-dry-run --yes --index 2

# Collar — same rank N is applied independently to both PE and CE pools:
python -m scripts.paper_3track_overlay --overlay collar --no-dry-run --yes --index 2
```

If `--index N` exceeds the number of available candidates, it clamps to the last rank and
logs a warning. `--index 1` is the default; you do not need to pass it explicitly.

### Verifying what was written

After any `--yes` run the status line shows `RECORDED TO DB — N new, M skipped`.
A non-zero skip count means the unique constraint `(strategy, leg_role, date, action)`
already existed — the DB was not modified for those rows. To inspect the DB directly:

```bash
python - <<'EOF'
import sys; sys.path.insert(0, ".")
from src.paper.store import PaperStore
store = PaperStore("data/portfolio/portfolio.sqlite")
for s in ["paper_nifty_spot", "paper_nifty_futures", "paper_nifty_proxy"]:
    trades = store.get_trades(s)
    print(f"\n{s} ({len(trades)} trades):")
    for t in trades:
        print(f"  {t.trade_date}  {t.leg_role:<26}  {t.action.value:<4}  qty={t.quantity}  price={t.price}")
EOF
```

### YAML path (offline price verification)

Use this when you want to inspect strikes before recording — for example if the option chain
had a momentary data issue during live fetch.

```bash
# Step 1: generate the YAML (review and edit prices if needed):
python scripts/find_overlay_strikes.py \
    --overlay-type pp \
    --nifty-spot 24000 \
    --monthly 2026-05-29 --quarterly 2026-06-26 --yearly 2026-12-25

# Step 2: inspect data/paper/overlay_entry.yaml — edit prices if stale

# Step 3: dry-run to verify what will be recorded:
python scripts/paper_3track_overlay_entry.py --dry-run

# Step 4: record:
python scripts/paper_3track_overlay_entry.py
```

---

## Step 3 — Daily Snapshot (cron)

Runs **every trading day at 15:35 IST**. This is the canonical EOD mark-to-market.

```bash
# Live save:
python scripts/paper_3track_snapshot.py --date 2026-05-09 --no-dry-run

# Dry-run — print report, no DB write (default):
python scripts/paper_3track_snapshot.py --date 2026-05-09

# If Upstox is down, pass spot manually:
python scripts/paper_3track_snapshot.py --date 2026-05-09 --dry-run --spot 24250

# Single track (debug):
python scripts/paper_3track_snapshot.py --date 2026-05-09 --dry-run --tracks proxy
```

**What it writes:**

- `paper_nav_snapshots` — strategy-level P&L per track
- `paper_leg_snapshots` — per-leg P&L (base + each overlay), used for delta-from-yesterday display

**Proxy delta alert:** If Proxy net delta < 0.65, a WARNING is printed. If < 0.40, a CRITICAL
alert fires and a Telegram notification is sent (if `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID`
are set in `.env`).

**Cron line (15:35 IST = 10:05 UTC):**

```
5 10 * * 1-5  cd /path/to/NiftyShield && python scripts/paper_3track_snapshot.py --date $(date +\%Y-\%m-\%d) --no-dry-run
```

---

## Step 4 — Overlay Roll

The roll script closes an expiring overlay leg at live LTP and immediately opens a fresh leg using
the same strike-selection logic as the entry script. The DTE gate is **≤ 5 calendar days** to
expiry (`OVERLAY_ROLL_DTE = 5` in `paper_3track_overlay.py`).

### When does DTE ≤ 5 occur?

Overlay expiry type determines when the roll window opens:

| Overlay expiry | Typical expiry date | Roll window opens |
|----------------|--------------------|--------------------|
| Monthly | Last Thursday of the month | ~Friday of the prior week |
| Quarterly (Jun/Sep/Dec) | Last Thursday of the quarter month | ~Friday of the prior week |
| Yearly (far-Dec) | Last Thursday of December | ~Friday of the prior week |

In practice: **check every Thursday morning**. If today's date is within 5 calendar days of
the overlay expiry, the roll fires. For monthly overlays this means the roll happens in the
last week of the month — typically the Thursday before expiry week or the Monday of expiry week.

### How to detect it

**Option A — daily cron (recommended):** Run the dry-run check every trading day at 09:30 IST.
It prints nothing if no leg is due; prints the roll table if DTE ≤ 5. Review output and execute
manually when non-empty.

```
30 4 * * 1-5  cd /path/to/NiftyShield && python -m scripts.paper_3track_overlay_roll 2>&1 | grep -v "^$"
```

**Option B — manual Thursday check:** Every Thursday morning before market open, run the dry-run
and decide whether to execute.

### Commands

```bash
# Dry-run — always safe, writes nothing (default):
python -m scripts.paper_3track_overlay_roll

# Execute the roll (after reviewing dry-run output):
python -m scripts.paper_3track_overlay_roll --no-dry-run --yes

# Force-roll even if DTE > 5 (manual intervention):
python -m scripts.paper_3track_overlay_roll --no-dry-run --yes --force

# Single track only:
python -m scripts.paper_3track_overlay_roll --no-dry-run --yes --tracks spot proxy
```

`--date` defaults to today, so it does not need to be passed in normal use.

### CC roll when the short call is ITM

The roll script has **one trigger only: DTE ≤ 5**. There is no ITM-based early roll.

If the market has rallied past the short call strike before DTE ≤ 5, the CC is held. This is
by design — the loss on an ITM CC is the data being collected (it quantifies the upside cap cost).
Rolling the strike higher mid-cycle would distort the comparison. When DTE ≤ 5 arrives, the roll
closes the ITM CC at live LTP (recording the realised loss) and opens a fresh CE at 3–5% OTM
from current spot.

**Do not use `--force` to roll early just because the CC is ITM.** If you want to study a
managed CC strategy that rolls ITM options, that belongs in a separate strategy spec, not here.

### Atomicity guarantee

- Single leg: close is written first. If the new open fails, the close is deleted (position restored).
- Collar (4-trade): rollback chain is open_call → open_put → close_call → close_put in reverse.
  All 4 succeed or none persist.

### Do not defer

If the roll cannot execute on the trigger day (market holiday, system error), execute on the next
trading day. **Never carry an expiring short option (CC or collar call) through to settlement** —
it expires worthless if OTM (acceptable) or gets assigned if ITM (not acceptable for paper tracking).
Log missed rolls in `TODOS.md`.

---

## Monthly Cycle Roll

On the **Wednesday after each monthly Nifty expiry** (same cadence as entry):

1. Close all three base legs at LTP.
2. Re-enter all three base legs via `paper_3track_entry.py --confirm`.
3. Re-enter overlays via `paper_3track_overlay.py --overlay <type> --no-dry-run --yes`.
4. Overlay legs on quarterly/yearly expiries do **not** roll monthly — they continue until
   their own DTE ≤ 5 trigger fires via `paper_3track_overlay_roll.py`.

If any roll cannot execute on the target date (market holiday, system error), log in
`TODOS.md` and execute on the next trading day. Never carry an expiring short option through
to settlement.

---

## Proxy — Special Monitoring Rules

The Proxy base leg requires daily delta monitoring. Two triggers beyond the standard monthly roll:

| Trigger | Condition | Action |
|---------|-----------|--------|
| Delta WARNING | net_delta < 0.65 | Flagged in snapshot output — watch for 3 days |
| Delta CRITICAL | net_delta < 0.40 for **3 consecutive days** | Close base leg immediately, re-enter delta ≈ 0.90 at current or next expiry |
| Premium near-zero | ltp < ₹0.50 with DTE ≥ 5 | Close and re-enter at next expiry |

These are intra-cycle corrections, not strategy pauses. Log delta readings and re-entry details
in `TODOS.md`.

The snapshot script tracks this automatically and fires a Telegram CRITICAL alert. But also
visually verify the delta column in the daily `--no-save` dry-run if the alert is not configured.

---

## Framework Kill Criteria

Triggers an **immediate pause on new entries** (existing positions managed to completion):

| # | Criterion | Threshold |
|---|-----------|-----------|
| 1 | Combined framework loss | > 5% of NEE across all three tracks in any rolling 30-day window (~₹77,500 at NEE ₹15.5L) |
| 2 | Uncovered short put on Futures | Any open CC on `paper_nifty_futures` without a paired PP — close violating leg immediately |
| 3 | Proxy delta data gap | Upstox chain returns no data for Proxy for ≥ 3 consecutive days |
| 4 | Three consecutive roll failures | Any track: wrong-side fill, missed roll, unintended expiry carry-through |

Do not drop a track that is losing. All three must complete the minimum 6 cycles for the
comparison to be valid.

---

## Conclusion Gate

After 6 cycles, the comparison is valid when all of:

- All three tracks completed all 6 cycles without a kill criterion breach
- At least one down-cycle observed per track (Nifty declined ≥ 3% in that cycle)
- Per-track, per-overlay P&L fully attributed in `paper_leg_snapshots`
- Greeks logged for ≥ 80% of trading days

**Output of the comparison:** Return on NEE, max drawdown, overlay cost/benefit, and a
recommendation of which (base × overlay) combination proceeds to a standalone strategy spec
and its own Phase 0 paper trading window. The 6 cycles here do **not** substitute for the
standalone paper-trading requirement of the winning combination.

---

## Environment Prerequisites

Required in `.env`:

```
UPSTOX_ANALYTICS_TOKEN=<long-lived analytics token>  # all scripts
TELEGRAM_BOT_TOKEN=<token>                           # optional — snapshot alerts
TELEGRAM_CHAT_ID=<chat_id>                           # optional — snapshot alerts
```

BOD instruments file must be current: `data/instruments/NSE.json.gz`

---

## Quick Reference

| Task | Command | When |
|------|---------|------|
| Enter base legs | `python scripts/paper_3track_entry.py --confirm` | Cycle start (Weds post-expiry, 10:00–10:30 AM) |
| Enter PP overlay | `python -m scripts.paper_3track_overlay --overlay pp --no-dry-run --yes` | Same day as base entry |
| Enter CC overlay | `python -m scripts.paper_3track_overlay --overlay cc --no-dry-run --yes` | Same day as base entry |
| Enter Collar overlay | `python -m scripts.paper_3track_overlay --overlay collar --no-dry-run --yes` | Same day as base entry |
| Pick non-default candidate | add `--no-dry-run --yes --index 2` | After dry-run review |
| Daily snapshot | `python scripts/paper_3track_snapshot.py --no-dry-run` | 15:35 IST daily (cron) |
| Dry-run snapshot | `python scripts/paper_3track_snapshot.py` | Ad hoc inspection |
| Roll check (dry) | `python -m scripts.paper_3track_overlay_roll` | Every Thursday morning (or daily cron) |
| Execute roll | `python -m scripts.paper_3track_overlay_roll --no-dry-run --yes` | After dry-run confirms DTE ≤ 5 on any overlay |

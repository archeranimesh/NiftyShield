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

### Live-fetch path (recommended)

```bash
# Preview — prints confirmation table, prompts Proceed? [y/N]:
python -m scripts.paper_3track_overlay --overlay pp

# Write directly (skip prompt):
python -m scripts.paper_3track_overlay --overlay pp --yes

# Collar:
python -m scripts.paper_3track_overlay --overlay collar --yes

# Specific tracks only:
python -m scripts.paper_3track_overlay --overlay pp --tracks spot proxy --yes
```

**`--date` is required as coded today.** Should default to `date.today()` — the fix is
pending (see TODOS.md). Until then, pass it explicitly:

```bash
python -m scripts.paper_3track_overlay --overlay pp --date 2026-05-09 --yes
```

**Expiry selection logic (automatic):** Prefers quarterly (DTE 46–200) → yearly (DTE 201–420)
→ monthly (DTE 15–45). Uses the expiry where spread_pct ≤ 3.0% (SPREAD_PCT_MAX). Falls back to
monthly if no expiry passes the gate. The chosen expiry and spread_pct are logged.

**OTM targets:**

- PP: 8–10% OTM (target 9%)
- CC: 3–5% OTM (target 4%)

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
# Live save (default):
python scripts/paper_3track_snapshot.py --date 2026-05-09

# Dry-run — print report, no DB write:
python scripts/paper_3track_snapshot.py --date 2026-05-09 --no-save

# If Upstox is down, pass spot manually:
python scripts/paper_3track_snapshot.py --date 2026-05-09 --no-save --spot 24250

# Single track (debug):
python scripts/paper_3track_snapshot.py --date 2026-05-09 --no-save --tracks proxy
```

**What it writes:**

- `paper_nav_snapshots` — strategy-level P&L per track
- `paper_leg_snapshots` — per-leg P&L (base + each overlay), used for delta-from-yesterday display

**Proxy delta alert:** If Proxy net delta < 0.65, a WARNING is printed. If < 0.40, a CRITICAL
alert fires and a Telegram notification is sent (if `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID`
are set in `.env`).

**Cron line (15:35 IST = 10:05 UTC):**

```
5 10 * * 1-5  cd /path/to/NiftyShield && python scripts/paper_3track_snapshot.py --date $(date +\%Y-\%m-\%d)
```

---

## Step 4 — Overlay Roll

Run **when DTE of any overlay leg reaches ≤ 5**. Default behaviour without `--yes` is dry-run.

```bash
# Check what would roll (dry-run — safe to run any time):
python -m scripts.paper_3track_overlay_roll --date 2026-05-09

# Execute the roll:
python -m scripts.paper_3track_overlay_roll --date 2026-05-09 --yes

# Force-roll even if DTE > 5 (manual intervention):
python -m scripts.paper_3track_overlay_roll --date 2026-05-09 --yes --force

# Single track:
python -m scripts.paper_3track_overlay_roll --date 2026-05-09 --yes --tracks spot proxy
```

**Atomicity guarantee:**

- Single leg: close is written first. If the new open fails, the close is deleted (position restored).
- Collar (4-trade): rollback chain is close_call → close_put → open_put in reverse order. All 4
  succeed or none persist.

**When to run the roll check:** Either add a cron to run `--dry-run` daily and alert on non-empty
output, or check manually every Monday morning.

---

## Monthly Cycle Roll

On the **Wednesday after each monthly Nifty expiry** (same cadence as entry):

1. Close all three base legs at LTP.
2. Re-enter all three base legs via `paper_3track_entry.py --cycle N --confirm`.
3. Re-enter overlays via `paper_3track_overlay.py --overlay <type> --yes`.
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
| Enter base legs | `python scripts/paper_3track_entry.py --confirm` | Cycle start (Weds post-expiry) |
| Enter PP overlay | `python -m scripts.paper_3track_overlay --overlay pp --date <date> --yes` | Same day as base entry |
| Enter Collar overlay | `python -m scripts.paper_3track_overlay --overlay collar --date <date> --yes` | Same day as base entry |
| Daily snapshot | `python scripts/paper_3track_snapshot.py --date <date>` | 15:35 IST daily |
| Dry-run snapshot | `python scripts/paper_3track_snapshot.py --date <date> --no-save` | Ad hoc inspection |
| Roll check (dry) | `python -m scripts.paper_3track_overlay_roll --date <date>` | Weekly / any time |
| Execute roll | `python -m scripts.paper_3track_overlay_roll --date <date> --yes` | When DTE ≤ 5 on any overlay |

# Near-Expiry Gamma Buy — Nifty 50 Weekly v1

| Field                   | Value                                                                                              |
|-------------------------|----------------------------------------------------------------------------------------------------|
| Name                    | Near-Expiry Gamma Acceleration Buy                                                                 |
| Version                 | v1                                                                                                 |
| Author                  | Animesh Bhadra (archeranimesh)                                                                     |
| Date                    | 2026-05-15                                                                                         |
| Status                  | Paper trading — data collection + P&L tracking                                                     |
| Underlying              | Nifty 50 index — weekly options only                                                               |
| Expiry scope            | Current-week expiry (Thursday) + Wednesday before it (0–1 DTE at entry)                           |
| Lot size                | 75 units (verify against NSE before each expiry)                                                   |
| Council source          | `docs/archive/council/research/2026-05-02_gamma-acceleration-mispricing-option-buying.md`          |
| Council pending         | 2 open questions — see §14. Both must resolve before Phase 3 live deployment.                      |
| Data dependency         | Dhan Data API (₹499/month) for L2 depth — see §4                                                  |

> **Research hypothesis:** At 0–1 DTE, the dominant mechanism for a 5–20× premium explosion
> is Gamma convexity, not Vega. Spot approaches a strike, delta jumps from ~0.03 to ~0.45,
> and premium follows non-linearly. The setup is visible days in advance: OI builds at a
> strike, spot drifts toward it, gamma_gearing rises as DTE collapses. This strategy
> identifies those setups early via daily monitoring, then enters on DTE 0–1 when the
> intraday convexity trigger fires.

> **Phase classification:** Phase 0 — data collection + paper trading. Goal is NOT to prove
> positive EV. Goal is to measure signal frequency, fillability, realised R-multiple
> distribution, and calibrate thresholds for Phase 3 deployment. No conclusions before
> 52 observed signals.

> **Relationship to CSP / IC:** Complementary buying overlay. Does not modify CSP/IC logic.
> Do not enter if a concurrent CSP or IC position is open at the same strike in the same
> direction.

---

## §1 — Purpose

The CSP and IC strategies are theta-decay sellers. The near-expiry gamma buy is structurally
opposite: it profits from rapid, non-linear premium expansion as spot accelerates toward a
strike near expiry.

The edge — if it exists — is not random. A strike that has been accumulating OI over 3–4
days while spot slowly drifts toward it carries fundamentally different gamma dynamics than
a cold strike that suddenly enters the range on expiry morning. The daily monitoring phase
exists to distinguish these two cases. Expiry-day entries on pre-qualified watchlist strikes
are the primary trade type. Cold strikes that pass all filters on DTE 0–1 are logged and
eligible but treated as secondary.

---

## §2 — Two-Phase Architecture

This strategy operates two independent processes that feed each other:

```
PHASE A — Daily chain watch (every trading day, all week)
    gamma_daily_watch.py  ← runs at 15:20 IST Mon–Fri
         │
         ├── gamma_chain_snapshots  (per-strike EOD state: Greeks, OI, IV, gearing)
         │        ↓
         └── gamma_watchlist        (strikes "warming up": OI building, spot approaching)
                  │
                  ▼
PHASE B — Intraday entry scan (DTE 0–1 only, 5-min cadence)
    gamma_scan.py  ← runs */5 09:25–15:00 Wed+Thu
         │
         ├── reads gamma_watchlist  → watchlist_hit flag per candidate
         ├── evaluates full signal stack on ALL near-expiry strikes
         ├── writes gamma_signal_log (every scan, every candidate)
         └── records paper_trade (paper_negamma_v1) when full signal fires + fill confirmed
```

**Phase A serves three distinct purposes:**

1. **Percentile calibration data.** `strike_iv_percentile_20d` in Layer 3 requires 20 days
   of per-strike IV history. The gamma_gearing 75th-percentile threshold (Layer 2) requires
   DTE-bucket distributions. Without Phase A running first, these fields are NULL and the
   quality filter degrades to Condition B only.

2. **Watchlist generation.** A strike that has been within 4% of spot for 3+ days with
   rising OI and rising gamma_gearing is a pre-qualified candidate on expiry day. Phase B
   prioritises these. Non-watchlist cold signals are still logged but lower confidence.

3. **Baseline volume statistics.** `volume_zscore_5m` in Layer 4 requires a rolling mean
   and std of 5-minute volume for each strike. Phase A's EOD volume data seeds these
   baselines before the intraday scan runs.

**Start Phase A immediately.** Phase B can begin running on the first DTE 0–1 day after
Phase A has at least one full week of snapshots (needed for the watchlist to be non-empty).
Phase A alone has value even before Phase B is implemented — every day of chain data is
irreplaceable.

---

## §3 — Operating Windows

### Phase A — Daily Chain Watch

**Days:** Every trading day (Mon–Fri), including expiry day itself.

**Time:** 15:20 IST (after most intraday noise has settled, 10 minutes before close).
Also run at 10:30 IST for a morning baseline snapshot (optional but useful for
distance-to-strike evolution tracking across the day).

**Expiry coverage:** Current-week expiry + next-week expiry. This builds multi-DTE gamma
profiles: the current week evolves from ~5 DTE down to 0 DTE, while next week starts at
~12 DTE and becomes next week's current. On expiry Thursday, capture both the expiring
chain's final state and the new current-week chain's opening state.

**Strike coverage:** All Nifty CE and PE strikes within ±10% of current spot. Approximately
40–60 strikes per expiry at NSE's 50-point intervals.

### Phase B — Intraday Entry Scan

**Days:** Wednesday (DTE = 1) and Thursday (DTE = 0, expiry day) only.

**Hours:** 09:25–15:00 IST. No new entries after 14:30 (insufficient time for meaningful
exit before 15:00 time stop). Exit-check scans continue until 15:00.

**Cadence:** Every 5 minutes.

---

## §4 — Data Requirements

| Source                    | Used by         | What it provides                                          | Cost       |
|---------------------------|-----------------|-----------------------------------------------------------|------------|
| Upstox Analytics Token    | Phase A + B     | Live option chain Greeks (delta, gamma, vega, iv) per strike | Existing |
| Upstox LTP batch          | Phase A + B     | Nifty spot, India VIX, Nifty Futures                     | Existing   |
| Dhan Data API             | Phase B         | L2 order book (top-5 bid/ask + qty), VWAP, OI ticks      | ₹499/month |

### On Dhan Data API

Subscribing serves two purposes simultaneously:

1. **This strategy (Phase B):** L2 depth is the only reliable fill-quality signal for
   near-expiry OTM options. A ₹3 ask with 20 lots available vs 3,000 lots available changes
   the paper trade decision. Without it, fill simulation degrades to spread-percentage only
   and `bid_qty`/`ask_qty` fields are NULL.

2. **Phase 1 backtest pipeline (task 1.3 supplement):** The Dhan Data API subscription
   includes historical expired options data (intraday resolution for subscribed date ranges).
   This supplements NSE Bhavcopy EOD data for intraday exit simulation in the Phase 1
   backtest. See `DECISIONS.md → Dhan Data API subscription (2026-05-15)`.

**Without Dhan Data API:** Phase A runs fully on Upstox. Phase B runs but marks depth
fields NULL and uses spread ≤ 25% of mid as the liquidity proxy.

### Derived fields (computed at capture/scan time)

```
gamma_gearing        = gamma × nifty_spot² / ask_price
speed_5m             = (gamma_t − gamma_{t-5m}) / (spot_t − spot_{t-5m})  [Phase B only]
distance_pct         = |nifty_spot − strike| / nifty_spot
distance_sigma       = distance_pct / underlying_realised_vol_15m           [Phase B only]
oi_change_1d         = (oi_today − oi_yesterday) / max(oi_yesterday, 1)    [Phase A]
oi_velocity_15m      = (oi_t − oi_{t-15m}) / max(oi_{t-15m}, 1)            [Phase B only]
volume_zscore_5m     = (volume_5m − mean_5m_vol) / std_5m_vol               [Phase B only]
                       rolling window: prior 10 equivalent 5-min bars on same strike
```

---

## §5 — Phase A: Daily Chain Watch Logic

`scripts/gamma_daily_watch.py` runs at 15:20 IST every trading day.

### 5a — What it captures

For each strike within ±10% of spot on the current-week and next-week expiries:

```
snapshot_date, snapshot_time, expiry_date, strike, option_type (CE/PE)
dte_calendar, nifty_spot, nifty_futures_price
delta, gamma, vega, theta, iv
gamma_gearing  (computed)
oi, oi_change_1d  (vs yesterday's gamma_chain_snapshots row for same strike)
volume_day  (daily cumulative from chain)
distance_pct  (computed)
best_bid, best_ask, bid_ask_spread
india_vix
```

Stored in `gamma_chain_snapshots` table (SQLite, Phase 0). See §11 for schema.

### 5b — Watchlist generation

After writing today's snapshots, the script re-evaluates the watchlist for the current-week
expiry. A strike is added to (or retained on) `gamma_watchlist` when **all** of:

```
dte_calendar BETWEEN 2 AND 6          (in the 2–6 DTE window; not too early, not too late)
distance_pct ≤ 0.04                   (within 4% of spot)
gamma_gearing ≥ 3.0                   (minimum gearing floor — pre-calibration bootstrap)
oi ≥ 1,000 contracts
oi_change_1d ≥ 0                      (OI not actively unwinding)
```

A strike is **elevated** on the watchlist (priority flag set) when additionally:

```
distance_pct ≤ 0.03 AND distance_pct < yesterday's distance_pct   (spot moving closer)
gamma_gearing > gamma_gearing_3d_avg  (gearing accelerating, not just constant)
oi_change_1d ≥ 0.10                   (+10% OI growth day-over-day)
```

A strike is **removed** from the watchlist when:

```
distance_pct > 0.05 for 2 consecutive days  (spot moved away and not returning)
oi_change_1d < −0.20 for 2 consecutive days (aggressive unwinding)
expiry_date < today  (expired)
```

### 5c — Percentile calibration update

After each snapshot batch, recompute rolling percentiles from `gamma_chain_snapshots`:

```
strike_iv_percentile_20d  — for each (strike, option_type): rank today's IV against
                             the prior 20 trading days' IV at the same strike.
                             Available after Day 21 of operation.

gamma_gearing_p75_dte0    — 75th percentile of all gamma_gearing values where
                             dte_calendar = 0, rolling 60-day window.

gamma_gearing_p75_dte1    — same for dte_calendar = 1.
```

Store these calibrated thresholds in a config row in `gamma_chain_snapshots` (or a
separate `gamma_thresholds` table) so Phase B can read them at scan time without
recomputing from the full dataset on every 5-minute run.

---

## §6 — Phase B: Signal Stack

`gamma_scan.py` runs every 5 minutes on DTE 0–1. Each run evaluates every candidate strike
against the four-layer signal stack. All evaluations are written to `gamma_signal_log`
regardless of outcome — failed filters are as valuable as passed ones for calibration.

At the start of each scan, load the current watchlist from `gamma_watchlist` and tag each
candidate with `watchlist_hit = (strike in watchlist)`. This flag is recorded in
`gamma_signal_log` and logged in Telegram notifications but does NOT change the signal
logic — watchlist and non-watchlist strikes are evaluated identically. The flag exists only
for post-hoc analysis of whether watchlist pre-qualification correlates with better outcomes.

### Layer 0 — Hard Filters

```
DTE ≤ 1
Option type: CE for bullish setups, PE for bearish
Premium (ask): ₹2–₹10  [COUNCIL PENDING — see §14 Q1]
Bid-ask spread: ≤ 25% of mid
Ask quantity: ≥ 1 lot (75 units) at ask price  (Dhan L2; NULL → assume pass)
India VIX: > 12
Quote freshness: last_traded_time within 5 minutes
No existing paper position in same direction  (checked against paper_trades DB)
Strike OI: ≥ 1,000 contracts
```

### Layer 1 — Directional Setup

```
For CE buy: underlying_return_15m > 0 AND distance_pct shrinking vs 15 min ago
For PE buy: underlying_return_15m < 0 AND distance_pct shrinking vs 15 min ago
distance_sigma ≤ 1.5  (strike within 1.5 intraday sigma of spot)
```

`distance_sigma = distance_pct / underlying_realised_vol_15m`. The vol denominator is
the rolling annualised std of 1-min returns over the prior 15 minutes, scaled to the
remaining session length.

### Layer 2 — Convexity Trigger (Primary)

```
gamma_gearing > threshold
AND speed_5m > 0  (Gamma rising due to spot approach, not time decay alone)
AND underlying_return_15m toward strike > 0.3%
```

**Threshold logic (three-stage):**

```
Stage 1 (Days 1–20):   gamma_gearing > 5.0  (bootstrap absolute floor)
Stage 2 (Days 21–60):  gamma_gearing > gamma_gearing_p75_dte{N}  (from Phase A calibration)
Stage 3 (Day 60+):     same as Stage 2, updated rolling 60-day window
```

`speed_5m` cold start: if prior 5-min gamma snapshot is missing (first scan of the day),
default to `speed_5m = 0`, which causes Layer 2 to fail. Do not enter on the first scan
each morning regardless of gamma_gearing. Log as `speed_5m_unavailable = true`.

### Layer 3 — Quality Filter

Passes if **either** condition holds:

```
Condition A (mispricing — valid for strikes within 10% of spot):
    theoretical_price − ask ≥ max(₹0.75, 1.0 × spread, 35% of ask)
    theoretical_price from Black '76 (src/backtest/greeks.py)

Condition B (IV cheapness — primary for strikes > 10% OTM, or when A unavailable):
    strike_iv_percentile_20d < 30th percentile
    (populated by Phase A after 20+ days; NULL → condition B fails → A must pass)
```

Log `quality_filter_method = "A" | "B" | "both" | "none"`.

### Layer 4 — Flow Confirmation

```
volume_zscore_5m > 2.0
AND oi_velocity_15m > 0.15  (+15% OI growth in 15 minutes)
AND option_price_rising = true  (current ask ≥ ask 5 minutes ago)
```

**OI directionality:** OI velocity is only meaningful with price context. `option_price_rising`
enforces directionality — rising call OI + falling call price = likely call writing (reject).
Rising call OI + rising call price + Nifty up = demand (confirm).

**Lookback:** Use 15-min OI velocity, not 5-min (NSE OI batches every ~3 minutes near
expiry, creating aliasing on short windows).

---

## §7 — Entry Rule

**Trigger:** All four layers pass in the same 5-minute scan.

**Instrument selection:** If multiple strikes pass all filters simultaneously, rank by
`gamma_gearing` descending (weighted 70%) + `watchlist_hit = true` bonus (30% rank boost).
Take the top-ranked strike. Log all qualifying candidates.

**Order type:** Limit at `mid + ₹0.10` (mildly aggressive — adverse selection risk of
strict mid-price limits in explosive moves).

**Fill assessment:** On the next 5-minute scan, if observed ask ≤ limit_price → filled.
If not: mark `paper_trade_status = "signal_valid_unfilled"`. Do not chase past the 2-minute
window (one scan cycle).

**Paper P&L entry price:** Conservative — use ask at signal time, regardless of fill
optimism. Never inflate paper P&L with theoretical fills.

**Record at entry:**

```
strike, expiry_date, option_type (CE/PE)
dte_calendar, dte_trading, watchlist_hit
entry_ask, entry_limit, entry_fill_price
nifty_spot, nifty_futures_price
india_vix, india_vix_percentile_252d
gamma, gamma_gearing, speed_5m
iv, theoretical_price, model_edge
distance_pct, distance_sigma
event_flag, event_type
signal_id (UUID), signal_timestamp
```

---

## §8 — Exit Rules

Three rules in priority order. First to fire exits the position.

### E1 — Profit Target

Close when mark ≥ **5× entry ask** (5R theoretical). In paper P&L, use **bid** at exit
scan, never mid. Target is 5R; accept 2–3R realised after bid-ask drag.

### E2 — Stop Loss

Close when mark ≤ ₹0.25 (effective zero for sub-₹10 options) or when ask_qty = 0 for
two consecutive scans (liquidity evaporation). Stop = 1R (full entry premium). Fixed.

### E3 — Time Stop

**DTE 0 (Thursday):** Close by 14:30 regardless of P&L.

**DTE 1 (Wednesday):** Close by 15:00 Wednesday unless mark ≥ 1.5× entry ask. If in
profit ≥ 1.5×, carry overnight — but gamma and theta both compress overnight, so the
probability of a 5R exit on Thursday morning from a ₹3 premium is low. When in doubt,
close Wednesday and look for a fresh signal Thursday.

### Exit accounting

```
exit_fill_price  = bid at exit scan  (never mid)
realised_R       = (exit_fill_price − entry_ask) / entry_ask
mfe              = max(observed bids during holding) − entry_ask
mae              = entry_ask − min(observed bids during holding)
```

---

## §9 — Risk Management

```
Max concurrent positions: 2 (one CE, one PE — not two CE or two PE simultaneously)
Max daily loss: 3R across all positions  (= 3 × entry_ask × 75 lots held)
No new entries after daily loss cap hit
No re-entry into same strike same day after stop-out
No concurrent position in same direction as open CSP or IC short leg at same strike
```

Capital allocation: option buying requires upfront premium only, no margin. Allocated
capital for paper tracking = sum of (entry_ask × 75) across all open positions.

---

## §10 — Paper Trading Integration

### Strategy name

`paper_negamma_v1` — conforms to `paper_` prefix invariant (see `src/paper/CLAUDE.md`).

### Leg roles

```
gamma_call    — call buy position (max 1 open at a time)
gamma_put     — put buy position  (max 1 open at a time)
```

Since at most one call and one put are open simultaneously, and positions open/close within
1–2 days, `UNIQUE(strategy_name, leg_role, trade_date, action)` is sufficient without
encoding strike in the leg_role.

### record_paper_trade.py usage

**Open (BUY-to-open):**
```bash
python scripts/record_paper_trade.py \
    --strategy paper_negamma_v1 \
    --leg gamma_call \
    --key "NSE_FO|<instrument_key>" \
    --price <entry_ask> \
    --action BUY --qty 1 --no-dry-run
```

**Close (SELL-to-close):**
```bash
python scripts/record_paper_trade.py \
    --strategy paper_negamma_v1 \
    --leg gamma_call \
    --close --no-dry-run
```

`--close` auto-resolves the open position and fetches live bid for exit price.

---

## §11 — Data Schemas

### gamma_chain_snapshots (Phase A output)

```sql
CREATE TABLE IF NOT EXISTS gamma_chain_snapshots (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_date      TEXT NOT NULL,          -- YYYY-MM-DD
    snapshot_time      TEXT NOT NULL,          -- HH:MM IST
    expiry_date        TEXT NOT NULL,          -- YYYY-MM-DD
    strike             INTEGER NOT NULL,
    option_type        TEXT NOT NULL,          -- CE | PE
    dte_calendar       INTEGER NOT NULL,

    -- Underlying
    nifty_spot         TEXT NOT NULL,
    nifty_futures      TEXT,
    india_vix          TEXT,

    -- Greeks
    delta_val          TEXT,
    gamma_val          TEXT,
    vega_val           TEXT,
    theta_val          TEXT,
    iv_val             TEXT,

    -- Derived
    gamma_gearing      TEXT,
    distance_pct       TEXT,

    -- Quote
    best_bid           TEXT,
    best_ask           TEXT,
    bid_ask_spread     TEXT,

    -- Volume / OI
    oi                 INTEGER,
    oi_change_1d       TEXT,                   -- fractional change vs prior day
    volume_day         INTEGER,

    -- Computed percentiles (populated during calibration update, NULL initially)
    strike_iv_pctile_20d    TEXT,
    gamma_gearing_pctile_dte TEXT,             -- percentile within same DTE bucket

    created_at         TEXT NOT NULL,

    UNIQUE (snapshot_date, snapshot_time, expiry_date, strike, option_type)
);

CREATE INDEX IF NOT EXISTS idx_gcs_expiry  ON gamma_chain_snapshots (expiry_date);
CREATE INDEX IF NOT EXISTS idx_gcs_strike  ON gamma_chain_snapshots (strike, option_type);
CREATE INDEX IF NOT EXISTS idx_gcs_date    ON gamma_chain_snapshots (snapshot_date);
```

### gamma_watchlist (Phase A output, Phase B input)

```sql
CREATE TABLE IF NOT EXISTS gamma_watchlist (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    expiry_date           TEXT NOT NULL,
    strike                INTEGER NOT NULL,
    option_type           TEXT NOT NULL,       -- CE | PE
    added_date            TEXT NOT NULL,       -- date first qualified
    last_seen_date        TEXT NOT NULL,       -- updated daily by Phase A
    removed_date          TEXT,               -- NULL = still active
    removal_reason        TEXT,               -- spot_moved_away | oi_unwinding | expired

    -- State at last evaluation
    distance_pct          TEXT,
    gamma_gearing         TEXT,
    oi                    INTEGER,
    oi_change_1d          TEXT,
    days_on_watchlist     INTEGER,

    -- Elevation flag
    elevated              INTEGER DEFAULT 0,  -- 1 = priority candidate
    elevation_reason      TEXT,

    UNIQUE (expiry_date, strike, option_type)  -- one active row per strike
);

CREATE INDEX IF NOT EXISTS idx_gwl_active ON gamma_watchlist (removed_date, expiry_date);
```

### gamma_signal_log (Phase B output)

```sql
CREATE TABLE IF NOT EXISTS gamma_signal_log (
    signal_id              TEXT PRIMARY KEY,
    signal_timestamp       TEXT NOT NULL,      -- UTC ISO-8601
    expiry_date            TEXT NOT NULL,
    strike                 INTEGER NOT NULL,
    option_type            TEXT NOT NULL,      -- CE | PE
    dte_calendar           INTEGER NOT NULL,
    dte_trading            INTEGER NOT NULL,
    watchlist_hit          INTEGER NOT NULL DEFAULT 0,  -- was strike on watchlist?
    watchlist_elevated     INTEGER NOT NULL DEFAULT 0,  -- was it elevated priority?

    -- Underlying context
    nifty_spot             TEXT NOT NULL,
    nifty_futures_price    TEXT,
    futures_basis          TEXT,
    underlying_return_1m   TEXT,
    underlying_return_5m   TEXT,
    underlying_return_15m  TEXT,
    underlying_rvol_15m    TEXT,
    distance_pct           TEXT NOT NULL,
    distance_sigma         TEXT,

    -- Option quote (Upstox)
    best_bid               TEXT,
    best_ask               TEXT NOT NULL,
    bid_ask_spread         TEXT,
    spread_pct_of_mid      TEXT,

    -- L2 depth (Dhan; NULL if not subscribed)
    bid_qty_l1             INTEGER,
    ask_qty_l1             INTEGER,
    total_bid_qty          INTEGER,
    total_ask_qty          INTEGER,

    -- Greeks
    delta_val              TEXT,
    gamma_val              TEXT NOT NULL,
    vega_val               TEXT,
    theta_val              TEXT,
    iv_val                 TEXT,

    -- Derived
    gamma_gearing          TEXT NOT NULL,
    speed_5m               TEXT,
    speed_5m_unavailable   INTEGER DEFAULT 0,
    theoretical_price      TEXT,
    model_edge             TEXT,
    strike_iv_pctile_20d   TEXT,
    gearing_threshold_used TEXT,              -- bootstrap value or calibrated p75

    -- Volume / OI
    volume_5m              INTEGER,
    volume_zscore_5m       TEXT,
    oi_now                 INTEGER,
    oi_velocity_15m        TEXT,
    option_price_rising    INTEGER,

    -- Market regime
    india_vix              TEXT,
    india_vix_pctile_252d  TEXT,
    event_flag             INTEGER NOT NULL DEFAULT 0,
    event_type             TEXT,

    -- Filter results (1=pass, 0=fail, NULL=not evaluated)
    f0_hard_pass           INTEGER,
    f0_fail_reason         TEXT,
    f1_directional_pass    INTEGER,
    f2_convexity_pass      INTEGER,
    f3_quality_pass        INTEGER,
    f3_quality_method      TEXT,
    f4_flow_pass           INTEGER,
    signal_triggered       INTEGER NOT NULL DEFAULT 0,

    -- Paper trade
    paper_trade_attempted  INTEGER NOT NULL DEFAULT 0,
    paper_trade_filled     INTEGER NOT NULL DEFAULT 0,
    entry_fill_price       TEXT,
    fill_timestamp         TEXT,
    unfilled_reason        TEXT,

    -- Exit
    exit_price             TEXT,
    exit_timestamp         TEXT,
    exit_reason            TEXT,
    mfe                    TEXT,
    mae                    TEXT,
    realised_r_multiple    TEXT,

    created_at             TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_gsl_timestamp ON gamma_signal_log (signal_timestamp);
CREATE INDEX IF NOT EXISTS idx_gsl_expiry    ON gamma_signal_log (expiry_date);
CREATE INDEX IF NOT EXISTS idx_gsl_triggered ON gamma_signal_log (signal_triggered);
CREATE INDEX IF NOT EXISTS idx_gsl_watchlist ON gamma_signal_log (watchlist_hit, signal_triggered);
```

---

## §12 — Operating Schedule

### Two scripts, two crons

```cron
# Phase A — daily chain watch, 15:20 IST every trading day
20 15 * * 1-5  cd /path/to/NiftyShield && python scripts/gamma_daily_watch.py >> logs/gamma_watch.log 2>&1

# Phase A — optional morning baseline, 10:30 IST every trading day
30 10 * * 1-5  cd /path/to/NiftyShield && python scripts/gamma_daily_watch.py --morning >> logs/gamma_watch.log 2>&1

# Phase B — intraday scan, every 5 min Wed+Thu 09:25–15:00 IST
*/5 9-15 * * 3,4  cd /path/to/NiftyShield && python scripts/gamma_scan.py >> logs/gamma_scan.log 2>&1
```

### gamma_daily_watch.py responsibilities

```
1. Determine expiry dates: current-week + next-week
2. Fetch Upstox option chain for both expiries
3. Compute derived fields for all strikes within ±10% of spot
4. Write gamma_chain_snapshots rows (upsert on date+time+expiry+strike+type)
5. Compute oi_change_1d vs yesterday's snapshot
6. Update gamma_watchlist:
   a. Add new qualifying strikes
   b. Update existing entries (last_seen_date, current state)
   c. Mark removals for strikes no longer qualifying
   d. Set elevated flag for priority candidates
7. Recompute percentile calibrations (strike_iv_pctile_20d, gearing p75 by DTE bucket)
   — only if ≥ 20 days of data exist; skip and log WARNING otherwise
8. Send Telegram summary: N strikes watched, N elevated, N added, N removed
```

### gamma_scan.py responsibilities

```
1. Determine current-week expiry from market_calendar
2. Fetch Upstox option chain
3. Load current gamma_watchlist (active rows for this expiry)
4. Fetch Dhan L2 depth if DHAN_DATA_API_KEY set
5. For each candidate strike:
   a. Compute derived fields
   b. Tag watchlist_hit + watchlist_elevated
   c. Evaluate layers 0–4
   d. Write gamma_signal_log row
6. If signal_triggered AND no open position in same direction:
   a. Rank candidates by (gamma_gearing × 0.7) + (watchlist_hit × 0.3 × gamma_gearing)
   b. Record paper trade for top-ranked candidate
   c. Mark paper_trade_attempted / filled in gamma_signal_log
7. Check open position exit conditions (E1/E2/E3)
   — If exit triggered: close via record_paper_trade.py --close, update signal_log exit fields
8. Telegram: signal fired / paper trade opened / exit triggered / no signal (silent unless debug)
```

### Environment variables

```
UPSTOX_ANALYTICS_TOKEN      existing
DHAN_DATA_API_KEY            new (optional — NULL = reduced mode without depth)
TELEGRAM_BOT_TOKEN           existing
TELEGRAM_CHAT_ID             existing
GAMMA_MIN_GEARING            override gearing floor (default: 5.0, Stage 1)
GAMMA_MIN_PREMIUM            override premium floor (default: 2.0)
GAMMA_MAX_PREMIUM            override premium ceiling (default: 10.0)
GAMMA_WATCHLIST_DISTANCE     override watchlist entry distance (default: 0.04)
```

---

## §13 — Evaluation Metrics

Compute after each 4-week block (roughly one month of expiry days):

```
Watch-to-signal rate:   signal_triggered / total scans on watchlist strikes
Cold signal rate:       signal_triggered on non-watchlist strikes / total cold scans
Fillability:            paper_trade_filled / signal_triggered
Win rate:               realised_R > 0 / filled trades
Median realised R:      median of realised_r_multiple across filled trades
Watchlist uplift:       win_rate(watchlist_hit=1) vs win_rate(watchlist_hit=0)
MFE/MAE distribution:   percentiles of mfe and mae
Filter calibration:     % of scans passing each layer individually
Gearing distribution:   histogram by DTE bucket — for threshold calibration update
```

**Kill criteria:** Abandon strategy design and restart from council if after 50 signals:

```
Win rate (filled) < 20%
OR median realised R < 1.3 (bid-price accounting)
OR fillability < 40%
OR watchlist_uplift is negative (watchlist adding noise, not signal)
OR gearing threshold capturing >80% of all scans (too loose — recalibrate immediately)
```

---

## §14 — Council Pending Questions

Both parameters are bootstrapped in the current paper phase. Council input required before
Phase 3 live deployment.

### Q1 — Weekly Nifty Premium Range (Layer 0)

**Bootstrap:** ₹2–₹10 (from council's monthly 0–2 DTE calibration)

**Tension:** The council calibrated ₹2–₹10 against monthly expiries. For Nifty 50 weekly
options at 0–1 DTE, the same premium range skews toward near-ATM strikes (delta ≥ 0.30),
which have good fills but lower explosive R:R. The ₹1–₹6 range targets more OTM strikes
with higher theoretical multiples but worse execution drag as a % of premium. For weekly
options where time value is already near-zero, the council's floor may be miscalibrated.

**Council command:**
```bash
python scripts/ask_council.py \
    --topic negamma-weekly-premium-range \
    --template strategy_parameters \
    --context docs/strategies/near_expiry_buy_v1.md \
    --question "For Nifty 50 weekly options at 0–1 DTE, what ask premium range optimises the tradeoff between gamma acceleration payoff potential and execution drag? The council's ₹2–₹10 was calibrated for monthly 0–2 DTE; weekly options at this DTE carry almost no time value, shifting the same premium range much closer to ATM. Should the range be ₹1–₹6 to target more OTM explosions, or does ₹2–₹10 hold for weeklies?"
```

### Q2 — Gamma Gearing Bootstrap Threshold (Layer 2)

**Bootstrap:** `gamma_gearing > 5.0` (Stage 1 absolute floor)

**Tension:** Council specifies ">75th percentile for DTE bucket" — correct in steady state
but provides no bootstrap value. Three approaches: (A) fixed absolute (5.0 or 8.0), simple
but regime-blind; (B) cross-sectional relative — top 25% of same-scan candidates, no
history needed but adapts on every 5-min snapshot; (C) rolling DTE-bucket percentile from
Phase A data after ≥ 20 days, then held for 60-day window. Behaviour differs materially
across IV regimes.

**Council command:**
```bash
python scripts/ask_council.py \
    --topic negamma-gearing-threshold \
    --template strategy_parameters \
    --context docs/strategies/near_expiry_buy_v1.md \
    --question "For the gamma_gearing Layer 2 filter in the near-expiry gamma buy strategy on Nifty 50 weekly 0–1 DTE: which calibration approach is correct — (A) fixed absolute threshold (gamma_gearing > 5.0 or 8.0), (B) cross-sectional top-25% relative to all candidates in the same 5-minute scan, or (C) rolling 75th-percentile by DTE bucket from 20+ days of Phase A chain data? Evaluate false-positive rates, regime sensitivity (low-VIX vs high-VIX periods), and operational complexity for NSE index options microstructure."
```

---

## §15 — Implementation Checklist

### Phase A — start immediately

- [ ] Create `gamma_chain_snapshots` and `gamma_watchlist` tables in `portfolio.sqlite`
- [ ] Implement `scripts/gamma_daily_watch.py`
- [ ] Add cron entries: 15:20 daily + optional 10:30 daily
- [ ] Run `gamma_daily_watch.py --dry-run` to validate chain fetch and schema writes
- [ ] Confirm Telegram summary fires after first live run

### Phase B — start after ≥ 5 days of Phase A data

- [ ] Subscribe to Dhan Data API (₹499/month)
- [ ] Add `DHAN_DATA_API_KEY` to `.env` and `.env.example`
- [ ] Create `gamma_signal_log` table in `portfolio.sqlite`
- [ ] Implement `scripts/gamma_scan.py`
- [ ] Add cron entry: `*/5 9-15 * * 3,4`
- [ ] Run `gamma_scan.py --dry-run` on first qualifying Wednesday

### Calibration milestones

- [ ] Day 21: `strike_iv_percentile_20d` becomes available — Layer 3 Condition B activates
- [ ] Day 21: advance Layer 2 to Stage 2 (gearing p75 from Phase A data)
- [ ] After 5 expiry days: submit Q1 (premium range) to council
- [ ] After 10 expiry days: submit Q2 (gearing threshold) to council
- [ ] After 10 expiry days: compute watchlist_uplift — if negative, revisit watchlist criteria

### Phase 3 gate (before live deployment)

- [ ] ≥ 52 observed signals with full schema (both phases running)
- [ ] Fillability ≥ 40%
- [ ] Median realised R > 1.5 (bid-price accounting)
- [ ] Watchlist uplift positive (watchlist_hit=1 wins more than hit=0)
- [ ] Kill criteria not triggered (§13)
- [ ] Q1 and Q2 council responses incorporated into this document

---

## §16 — Open Questions and Changelog

### Open

- Speed cold start (first scan of day): confirmed to default `speed_5m = 0` → Layer 2 fails.
  Acceptable: first 5 minutes of each expiry day are excluded. Log as `speed_5m_unavailable`.
- Wednesday overnight carry: for strikes where DTE 1 → DTE 0, should the watchlist elevation
  flag be the deciding factor for carry vs close at 15:00 Wednesday?
- Event-day Vega reactivation: `event_flag = 1` does not currently modify any filter. The
  council says Vega becomes co-primary on event days — a separate event-day signal variant
  may be needed, but deferred until base strategy has ≥ 20 signals.
- Phase A morning snapshot (10:30): optional for now. Evaluate whether distance_pct
  trajectory intraday (10:30 vs 15:20) meaningfully predicts watchlist outcomes before
  committing to the second daily cron.

### Changelog

| Date       | Change                                                             |
|------------|--------------------------------------------------------------------|
| 2026-05-15 | v1 created from council archive file                               |
| 2026-05-15 | v1.1 — redesigned to two-phase architecture (daily watch + intraday scan) |

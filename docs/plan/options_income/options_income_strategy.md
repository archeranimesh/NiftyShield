# Options Income Strategy — Spec v1.0

> Canonical strategy document. All implementation must trace back to a rule here.
> Two variants run independently. Do not mix logic between them.

---

## Overview

Systematic premium collection on Nifty index options. Directional bias is bullish-only,
enforced by trend filter. Strategy is not market-neutral — it profits from time decay in
calm or rising markets and stops out when the market structure breaks.

---

## Variants

| | V1 — Monthly Naked Put | V2 — Quarterly Spread |
|---|---|---|
| Expiry target | Last Thursday of current month | Last Thursday ~90 DTE |
| DTE at entry | 30–45 | 60–90 |
| Structure | Short 5Δ put (naked) | Short 5Δ put + Long 2Δ put (same expiry) |
| Max loss | Uncapped (sized by position limit) | Spread width − net premium |
| Typical premium | Higher % of spread | Lower % of spread |
| Turnover | ~monthly | ~quarterly |

---

## Entry Conditions

All conditions must be true simultaneously. One failure = no trade.

### 1. Trend filter
- Nifty spot **closing price** above **100-period daily SMA**
- SMA computed on Nifty spot (not futures)
- Signal fires on daily close; entry executes **next session open**

### 2. Neutral zone block
- No entry when `|Nifty spot − 100 SMA| / 100 SMA < 0.02` (within 2% of SMA)
- Rationale: crossover risk too high; wait for clear separation

### 3. VIX floor
- India VIX must be **≥ 12.0** at entry session open
- Below 12: premium too thin to justify tail risk and transaction costs

### 4. Event calendar block
- No new entry within **5 trading days** of:
  - RBI Monetary Policy Committee decision date
  - Union Budget
  - US FOMC decision date
  - Nifty monthly expiry week (Thursday expiry week)

### 5. Strike selection
- **V1:** Sell put at 5Δ on target monthly expiry
- **V2:** Sell put at 5Δ, buy put at 2Δ, same quarterly expiry
- Delta sourced from live option chain at entry open
- If exact delta not available: nearest strike with Δ ≤ 5 (go further OTM, never ITM)

---

## Exit Conditions

### Take-profit
- Close position when mark-to-market P&L reaches **25% of premium collected**
- V2: measure net spread premium collected (short leg premium − long leg cost)

### Stop-loss — hard stop, no rolling
- Close position when **short put delta reaches 25**
- This is a hard stop. No rolling, no adjustment, no averaging.
- Execute at next available market price after delta threshold is breached on EOD data
- In paper/live mode: check delta at 3:15 PM IST (15 min before close)

### Expiry exit
- If neither target nor stop is hit: close position **5 trading days before expiry**
- Never hold through expiry week

---

## Position Sizing

| Parameter | Rule |
|---|---|
| Max capital at risk per trade | 2% of strategy-allocated capital |
| Max open positions simultaneously | 2 (one V1 + one V2 allowed concurrently) |
| Lot size | Nifty: 75 units |
| Minimum lots | 1 |

Capital at risk definition:
- V1: SPAN margin required for 1 lot naked put
- V2: Spread width × 75 (max loss per lot)

---

## Data Requirements

### Backtesting
| Data | Source | Notes |
|---|---|---|
| Nifty spot OHLCV daily | NSE bhavcopy | For SMA computation |
| Nifty options EOD (strike, expiry, OHLCV, OI) | NSE bhavcopy options | Monthly expiry strikes |
| India VIX daily close | NSE | Filter check |
| Event calendar | Manual CSV | RBI, Budget, FOMC dates |

Minimum history required: **2018-01-01 to present** (captures COVID crash, rate cycle)

### Paper / Live
- Nifty spot: real-time via Upstox market data
- Option chain: Upstox option chain API (delta field)
- India VIX: Upstox or NSE live feed

---

## Backtest Methodology

- EOD simulation only (no intraday)
- Entry: next-day open after signal fires on close
- Exit: EOD delta check triggers next-day open exit
- Slippage assumption: **0.5% of premium** per leg
- Brokerage: ₹20 per order (both legs for V2)
- No partial fills assumed

### Metrics to compute
- Win rate
- Average hold days
- Average P&L per trade (in ₹ and % of premium)
- Max drawdown (consecutive losses)
- Sharpe ratio (annualised, using daily P&L)
- Trades filtered by event calendar (count)
- Trades filtered by VIX floor (count)
- Trades filtered by neutral zone (count)

---

## Out of Scope (v1.0)

- No intraday delta monitoring
- No gamma scalping or adjustment
- No short call side (strangle)
- No BankNifty or FinNifty
- No live order execution (paper trading is the live gate)

---

## Phase Gates

```
Phase 0: Data audit → confirm historical options data completeness
Phase 1: Signal engine → SMA, VIX, event calendar, neutral zone
Phase 2: Strike selector → delta-based strike finder from historical chain
Phase 3: Backtest V1 (monthly naked put)
Phase 4: Backtest V2 (quarterly spread)
Phase 5: Paper trading V1
Phase 6: Paper trading V2
Phase 7: Reporting dashboard
```

Phase N does not start until Phase N−1 passes its exit criteria.

**Phase 0 exit criteria:** ≥ 80% data completeness for monthly expiry strikes, 2018–present.
**Phase 3/4 exit criteria:** ≥ 100 trades simulated, metrics computed, no code errors.
**Phase 5/6 exit criteria:** 3 consecutive live paper trades execute correctly end-to-end.

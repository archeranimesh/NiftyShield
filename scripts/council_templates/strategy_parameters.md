# Strategy Parameters Domain

You are advising on parameter choices for a Nifty 50 options selling strategy (NiftyShield).

## Strategy

- **Instrument:** Nifty 50 index options (not NiftyBees options — switched 2026-04-25 due to
  insufficient liquidity: OI < 1,000 on monthlies, bid/ask > 5% of mid).
- **Type:** Monthly Cash Secured Put (CSP). Sell 1 lot (50 units) per cycle.
- **Phase:** Paper trading only (Phase 0). No live capital deployed. Minimum 6 full monthly
  expiry cycles before live deployment gate.

## Capital & Collateral

- ~₹1.2 crore collateral pool: ₹75L MF + ₹30L Nuvama bonds + ₹15.5L NiftyBees ETF pledged
- NiftyBees ETF is modelled as a collateral leg in paper P&L (BUY equivalent to 1 lot notional)
- Max drawdown tolerance: ~₹6L on a ₹1 crore portfolio (from strategy spec)

## Current Exit Rules (v1 spec — R1–R7)

- **R1:** 50% profit target (buy back at ≤ 50% of opening credit)
- **R2:** Delta stop — exit if short put delta reaches −0.45 AND mark-to-market ≥ 1.75× credit
- **R3:** IVR entry filter — only enter when trailing 252-day IV rank > threshold (TBD from Stockmock backtest)
- **R4:** Trend filter — skip entry when Nifty 50 is below its 200-day SMA (bearish regime)
- **R5:** 21 DTE time stop — exit if still open at 21 DTE remaining
- **R6:** 2× credit loss stop — exit if mark-to-market loss ≥ 2× opening credit
- **R7:** No intra-trade adjustments in v1. Exit only, never roll mid-trade.

## Existing Live Strategies (NOT in scope)

FinRakshak + ILTS run on Zerodha via Finideas (external manager). These are tracked
but not backtested or modified by NiftyShield. Evaluated separately in Phase 4 (2028+).

## Broker Costs (when live — Upstox)

₹20/order brokerage, STT 0.1% sell-side on premium, exchange charge 0.0345% on premium,
GST 18% on brokerage + exchange, SEBI ₹10/crore premium, stamp duty 0.003% buy-side.

## Protection Overlay (NiftyShield Integrated v1)

Alongside CSP, the integrated strategy runs:
- Leg 2: protective put spread (4 lots, 8–20% OTM), entered monthly alongside CSP
- Leg 3: quarterly tail puts (2 lots, ~30% OTM, ~5-delta), entered Jan/Apr/Jul/Oct
- Static portfolio beta: 1.25 (switch to rolling 60-day when 12+ months of NAV data exist)
- FinRakshak is NOT counted in hedge ratio — treated as independent

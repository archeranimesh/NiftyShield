# NiftyShield — Glossary

> Single source of truth for domain terms used across docs and AI sessions.
> Covers options trading, strategy names, project conventions, and data layer rules.
> ~42 entries. Maintained by Claude; update here first, then update docs that reference the term.

---

## Options Trading

## ATM (At-The-Money)
**Category:** Trading
**Definition:** An option whose strike price is equal (or closest) to the current spot price of the underlying.
**Example / note:** For NIFTY at 24,000, the 24,000 CE and 24,000 PE are both ATM.

## BOD (Beginning of Day)
**Category:** Project
**Definition:** The pre-market instrument master JSON file downloaded once at market open (typically 09:00–09:15 IST) containing all exchange-tradable instruments and their `instrument_key` values.
**Example / note:** Used by `src/instruments/lookup.py` for offline strike/expiry resolution. Do not re-download mid-session.

## CE (Call option)
**Category:** Trading
**Definition:** An options contract giving the buyer the right (not obligation) to buy the underlying at the strike price before expiry.
**Example / note:** In NSE notation, a NIFTY 24000 call expiring 26-Jun-2025 is written as `NIFTY2562524000CE`.

## Delta
**Category:** Trading
**Definition:** Rate of change of option price with respect to a ₹1 move in the underlying. Ranges [0, 1] for calls and [−1, 0] for puts.
**Example / note:** A delta of 0.30 means the option price moves ~₹0.30 for every ₹1 move in NIFTY. Used in `src/risk/` for portfolio-level delta aggregation.

## DITM (Deep In-The-Money)
**Category:** Trading
**Definition:** An option with a strike far inside the profitable range — delta approaches 1 (CE) or −1 (PE). High intrinsic value, very low extrinsic value.

## DTE (Days to Expiry)
**Category:** Trading
**Definition:** Calendar days remaining until option expiry (inclusive of expiry date).
**Example / note:** NiftyShield uses DTE ≤ 5 as the roll trigger for overlay legs. See `paper_3track_overlay_roll.py`.

## Expiry
**Category:** Trading
**Definition:** The date on which an options contract ceases to exist. NSE NIFTY options expire every Thursday (weekly), last Thursday of the month (monthly), last Thursday of the quarter (quarterly), or last Thursday of the year (yearly).
**Example / note:** `get_expiry_candidates()` enumerates expiries into monthly (DTE 15–45), quarterly (46–200), and yearly (201–420) buckets.

## Gamma
**Category:** Trading
**Definition:** Rate of change of delta with respect to a ₹1 move in the underlying. Highest at ATM near expiry.
**Example / note:** High gamma = delta changes rapidly — relevant for near-expiry positions in the Near-Expiry Gamma Buy strategy (`src/gamma/`).

## ITM (In-The-Money)
**Category:** Trading
**Definition:** An option with intrinsic value. For a CE: spot > strike. For a PE: spot < strike.

## IV (Implied Volatility)
**Category:** Trading
**Definition:** The market's forward-looking estimate of annualised volatility, derived by back-solving the Black-Scholes formula from the option's market price. Expressed as a percentage.
**Example / note:** High IV → expensive premiums → favourable for sellers. India VIX is the market IV for NIFTY options.

## IVR (IV Rank)
**Category:** Trading
**Definition:** Percentile rank of current IV relative to its 252-trading-day trailing range: `(IV_today − IV_min) / (IV_max − IV_min)`. Ranges [0.0, 1.0]; flat window returns 0.5.
**Example / note:** Threshold bands used in NiftyShield: < 0.25 = low-vol (warn), 0.25–0.50 = in-window (preferred entry), > 0.50 = high-vol (warn). Implemented in `src/backtest/ivr.py`.

## Lot Size
**Category:** Trading
**Definition:** The minimum tradeable unit for an NSE F&O contract. For NIFTY, `LOT_SIZE = 65` as of 2024 revision.
**Example / note:** All delta aggregation divides `net_qty` by `lot_size`. Stored as the constant `LOT_SIZE` in `REFERENCES.md`.

## OTM (Out-of-The-Money)
**Category:** Trading
**Definition:** An option with no intrinsic value. For a CE: spot < strike. For a PE: spot > strike. Premium is entirely extrinsic (time value + IV).

## PE (Put option)
**Category:** Trading
**Definition:** An options contract giving the buyer the right (not obligation) to sell the underlying at the strike price before expiry.
**Example / note:** Protective puts (PP) are long PEs bought as portfolio insurance.

## Theta
**Category:** Trading
**Definition:** Rate of time-decay of option premium per calendar day, expressed as a negative number for long options.
**Example / note:** Theta works in the seller's favour — short options collect theta decay each day.

## Underlying
**Category:** Trading
**Definition:** The index or security on which options are written. In NiftyShield the primary underlying is NIFTY 50.

## Vega
**Category:** Trading
**Definition:** Rate of change of option price with respect to a 1% change in IV. Long options have positive vega; short options have negative vega.

---

## Strategies

## Cash-Secured Put (CSP)
**Category:** Trading
**Definition:** Selling a PE while holding enough cash to buy the underlying if assigned. Generates premium income with downside participation.

## Collar
**Category:** Trading
**Definition:** Combination of a long protective put + short covered call on the same underlying. Caps both upside and downside. One of the three overlay tracks in NiftyShield (Track C).

## Covered Call (CC)
**Category:** Trading
**Definition:** Selling a CE against an existing long position in the underlying (or futures). Reduces cost basis; caps upside above the strike.
**Example / note:** CC is permanently blocked on the futures-based Track B overlay — futures cannot be "covered" the same way as equity.

## Delta-Neutral
**Category:** Trading
**Definition:** A portfolio where the aggregate delta (options + hedges) is approximately zero, so small moves in the underlying do not affect portfolio value.
**Example / note:** `PortfolioDeltaTracker` computes this; `check_entry_allowed` gates new entries based on how far delta is from neutral.

## Iron Condor
**Category:** Trading
**Definition:** Simultaneous short strangle + long strangle at wider strikes. Defined risk on both sides; profits when the underlying stays within a range.

## Overlay
**Category:** Project
**Definition:** An options position layered on top of a base equity position (NiftyBees ETF) for income generation or protection. Distinct from the base leg. Tracks A/B/C each have their own overlay type.

## Protective Put (PP)
**Category:** Trading
**Definition:** A long PE bought as insurance against a decline in the underlying. Track A overlay in NiftyShield.

## Short Strangle
**Category:** Trading
**Definition:** Simultaneously selling an OTM CE and an OTM PE. Collects premium from both; profits when the underlying remains between the two strikes through expiry.

## Strangle
**Category:** Trading
**Definition:** An options structure combining a CE and PE at different strikes (both OTM for a short strangle, both OTM but wider for a long strangle). Cheaper than a straddle.

---

## Project Conventions

## BUY-opened position
**Category:** Project
**Definition:** A paper or live position initiated with a BUY order — i.e., the trader is long the option. `direction = Direction.BUY`. Unrealized P&L = (current_price − entry_price) × qty.

## instrument_key
**Category:** Project
**Definition:** Upstox's canonical identifier for a tradeable instrument. Format: `NSE_FO|<numeric_id>` for F&O, `NSE_EQ|<numeric_id>` for equity. Resolved from the BOD JSON via `src/instruments/lookup.py`.
**Example / note:** Never hardcode `instrument_key` values — look them up from BOD. Keys change on contract rollover.

## leg_role
**Category:** Project
**Definition:** A string tag on a `Leg` or `PaperTrade` indicating the function of that leg in the overall strategy. Values used in NiftyShield: `"base"`, `"overlay"`, `"hedge"`.

## paper_ prefix convention
**Category:** Project
**Definition:** All paper-trading models and DB tables are prefixed with `paper_` to distinguish them from live-trading counterparts. E.g., `PaperTrade`, `paper_trades` table, `paper_nav_snapshots`.
**Example / note:** Enforced as a validator on the `PaperTrade` Pydantic model — `strategy_name` must start with `paper_`.

## Roll
**Category:** Project
**Definition:** The atomic operation of closing an expiring (or adjustment-triggered) option leg and opening a replacement leg at a new strike/expiry. In NiftyShield, implemented as a two-trade sequence with full rollback on failure.
**Example / note:** `paper_3track_overlay_roll.py` rolls overlay legs when DTE ≤ 5. Collar rolls are 4-trade atomic.

## SELL-opened position
**Category:** Project
**Definition:** A paper or live position initiated with a SELL order — i.e., the trader is short the option. `direction = Direction.SELL`. Unrealized P&L = (entry_price − current_price) × qty.

## strategy_name
**Category:** Project
**Definition:** The database-canonical identifier for a trading strategy. Must match a row in the `strategies` table. Examples: `finideas_ilts`, `finrakshak`, `paper_collar`. Never use display names (e.g., `ILTS`, `FinRakshak`) in DB calls.

## Track A / B / C
**Category:** Project
**Definition:** The three parallel paper-trading overlay tracks in NiftyShield. Track A = protective put (PP) overlay; Track B = futures-based overlay; Track C = collar overlay. Each track has its own base position and overlay leg(s).

---

## Data Layer Rules

## Decimal-as-TEXT
**Category:** Data
**Definition:** All monetary `Decimal` fields are stored as `TEXT` in SQLite and read back with `Decimal(row["col"])`. Never store as `REAL` — floating-point rounding corrupts financial arithmetic.

## LOT_SIZE
**Category:** Data
**Definition:** The constant `65` — the number of NIFTY units per F&O lot as of the current contract specification. Used in delta calculations: `delta_lots = net_qty / LOT_SIZE`.

## IVR Threshold Bands
**Category:** Data
**Definition:** The three operational IVR zones used to gate paper trade entries: `< 0.25` = low-vol (warn, premium thin); `0.25–0.50` = in-window (preferred); `> 0.50` = high-vol (warn, IV may mean-revert against seller).

## Parquet Storage
**Category:** Data
**Definition:** Historical market data (option chain snapshots, VIX OHLC, intraday candles) is stored in Parquet files partitioned by instrument + date under `data/historical/`. Queried via DuckDB in `src/backtest/chain_reader.py`.

## UTC / IST convention
**Category:** Data
**Definition:** All timestamps are stored in UTC in the database. Conversion to IST (UTC+5:30) happens only at the display layer. Never store IST timestamps in the DB.

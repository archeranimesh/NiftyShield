# API Evaluation: Historical Option Chain Data (Revised)

*This report has been updated to reflect accurate subscription pricing models, specifically the Dhan Data API, Upstox Plus tier, and Kite Connect.*

| Feature | Kite Connect (Zerodha) | DhanHQ Data API | Upstox Plus | Nuvama Wealth API |
| :--- | :--- | :--- | :--- | :--- |
| **Pricing** | ₹500 / month | ₹400 / month (or ₹4,788 / year) | Included in Upstox Plus Plan | Mostly Free / Promotional |
| **Historical Options Data** | ❌ Active contracts only | ✅ Up to 5 yrs Expired Options | ✅ Supported (since 2022) | ⚠️ Limited (EOD/Intraday) |
| **Option Chain Queries** | N/A (No expired data) | **Native (ATM ± Strikes)** | Master list mapping needed | Basic |
| **Market Depth** | 5 Levels | **200 Levels** | 30 Levels | Basic Data Stream |
| **Local Storage Fit** | Poor | **Excellent** | Good | Moderate |

---

## 1. Technical Winner: DhanHQ Data API 

Even with the subscription fee evaluated (₹400/month or ₹4,788/yr), Dhan remains the objectively best API for your specific architectural goal of downloading and storing historical chains.

*   **Architecture Advantage (The Crucial Differentiator)**: Storing option chains locally requires mapping exactly which strikes existed on a past day. DhanHQ offers an exclusive **Expired Options API** that accepts queries based on *relative strikes* (e.g., ATM ± 10 for a specific historical date) rather than fixed instrument IDs. This saves you from having to build and maintain a massive master dictionary of millions of expired derivative tokens.
*   **Market Depth**: At 200 levels of market depth via WebSocket, checking bid/ask liquidity for your option models is much more robust than the competitors.
*   **Data Coverage**: Up to 5 years of OHLC, Volume, OI, and IV for these chains.

## 2. Upstox Plus (Strong Alternative)

With the **Upstox Plus** plan, Upstox opens up access to their **Expired Instruments API**.

*   **Historical Data Capabilities**: You get solid minute/hour candle data dating back to Jan 2022 for expired derivatives.
*   **The Architecture Bottleneck**: To fetch an expired option chain for a day in 2023, you need the exact Upstox `instrument_key` for every individual CE/PE contract on that day. Your system architecture has to ingest their historical instrument master files, map the expiry dates, and assemble the chain manually before querying the candle data.
*   **Market Depth**: 30 Levels.

## 3. Kite Connect (Zerodha)

At ₹500/month, Kite is financially incredibly competitive, but completely fails the technical requirement for deep quantitative analysis on options.

*   **The Dealbreaker**: Kite's Historical API strictly provides data for *currently active* contracts. They purposefully do not store or provide OHLC data for options once they expire. You cannot reconstruct a historical option chain from 6 months ago using Kite.
*   **Market Depth**: 5 Levels.

## 4. Nuvama Wealth

While affordable/free, Nuvama's data is suited for simple live execution. Attempting to pull structured expired option chains via their standard endpoints is significantly less documented and less reliable than Dhan or Upstox.

---

## Final Recommendation on Local Storage Architecture

Given that **Dhan Data API** provides the path of least resistance for querying the chains (ATM mapping) and costs roughly the same as Kite (₹400/mo vs ₹500/mo), it is highly recommended you stick with Dhan.

### The Ingestion Architecture
1. **Data Ingestion Script**: A scheduled script hits Dhan's `POST /charts/rollingoption` daily.
2. **Database Choice**: Use **PostgreSQL + TimescaleDB**. Financial ticks and 1-minute OHLCV rows for hundreds of strikes across multiple expiries will rapidly blow up a standard SQLite database. Timescale will compress this data out of the box.
3. **Data Model**:
```sql
CREATE TABLE option_chain_history (
    timestamp TIMESTAMPTZ NOT NULL,
    underlying_symbol VARCHAR(20),      -- e.g., NIFTY
    underlying_spot NUMERIC,            -- Spot price at time
    expiry_date DATE NOT NULL,
    strike_price NUMERIC NOT NULL,
    option_type VARCHAR(2),             -- CE or PE
    open NUMERIC, high NUMERIC, low NUMERIC, close NUMERIC,
    volume BIGINT,
    open_interest BIGINT,
    implied_volatility NUMERIC
);
-- Create TimescaleDB hypertable for ultra-fast time-series queries
SELECT create_hypertable('option_chain_history', 'timestamp');
```

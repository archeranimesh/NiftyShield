# NiftyShield — References

> Read this when: touching instrument keys, AMFI codes, API endpoints, or auth tokens.
> Also read when defining new strategy legs or verifying any market data key.

---

## Tokens & Auth

| Token | Env Var | Lifetime | Used For |
|---|---|---|---|
| Analytics Token | `UPSTOX_ANALYTICS_TOKEN` | ~1 year | LTP, option chain, Greeks, candles, websocket |
| Daily OAuth Token | `UPSTOX_ACCESS_TOKEN` | Daily | Portfolio/positions read, order execution |
| Sandbox Token | `UPSTOX_SANDBOX_TOKEN` | Session | Upstox sandbox integration tests |
| Nuvama APIConnect | `NUVAMA_SETTINGS_FILE` path | Until invalidated | Bonds/holdings read, EOD positions |
| Dhan Client ID | `DHAN_CLIENT_ID` | Permanent | Identifies Dhan account (numeric) |
| Dhan Access Token | `DHAN_ACCESS_TOKEN` | 24 hours | Portfolio, positions, funds (free Trading APIs) |

**Nuvama login (one-time):** `python -m src.auth.nuvama_login`
**Nuvama verify:** `python -m src.auth.nuvama_verify`
**Upstox OAuth:** `python -m src.auth.login` (daily for portfolio/order features)
**Dhan login:** `python -m src.auth.dhan_login` (daily — opens browser, saves token)
**Dhan verify:** `python -m src.auth.dhan_verify` (confirms connectivity + prints holdings)


---

## Instrument Keys (verified against live API)

| Instrument | Key | Notes |
|---|---|---|
| EBBETF0431 (ETF) | `NSE_EQ\|INF754K01LE1` | ISIN starts with INF (ETF), not INE |
| LIQUIDBEES ETF | `NSE_EQ\|INF732E01037` | Verified 2026-04-08 via `InstrumentLookup.search_equity('LIQUIDBEES')` |
| NiftyBees ETF | `NSE_EQ\|INF204KB14I2` | Discovered Day 1 |
| NIFTY DEC 23000 PE | `NSE_FO\|37810` | Monthly expiry: 2026-12-29 (Tue) |
| NIFTY JUN 23000 CE | `NSE_FO\|37799` | Monthly expiry: 2026-06-30 (Tue) |
| NIFTY JUN 23000 PE | `NSE_FO\|37805` | Monthly expiry: 2026-06-30 (Tue) |
| Nifty Index | `NSE_INDEX\|Nifty 50` | Option chain + spot price — NOT `"NIFTY"` |

**To look up new instruments:** `python -m src.instruments.lookup --find-legs <query>` (uses `data/instruments/NSE.json.gz` offline BOD file)

---

## AMFI Codes (verified against live AMFI flat file 2026-04-04)

All 11 original codes were wrong — replaced by grepping the live AMFI flat file.
**Do NOT trust codes from any other source without verifying against the live flat file.**
Verification: `grep -i "<scheme name>" <(curl https://www.amfiindia.com/spages/NAVAll.txt)`

| Scheme | AMFI Code |
|---|---|
| Parag Parikh Flexi Cap Fund - Regular Plan - Growth | 122640 |
| DSP Midcap Fund - Regular Plan - Growth | 104481 |
| HDFC Focused Fund - Growth | 102760 |
| Mahindra Manulife Mid Cap Fund - Regular Plan - Growth | 142109 |
| Edelweiss Small Cap Fund - Regular Plan - Growth | 146193 |
| Tata Value Fund - Regular Plan - Growth | 101672 |
| quant Small Cap Fund - Growth - Regular Plan | 100177 |
| Kotak Flexicap Fund - Growth | 112090 |
| HDFC BSE Sensex Index Fund - Growth Plan | 101281 |
| Tata Nifty 50 Index Fund - Regular Plan | 101659 |
| WhiteOak Capital Large Cap Fund - Regular Plan Growth | 150799 |

---

## API Quirks

- **V3 Market Quote key format:** Send keys with pipe (`NSE_FO|37810`), response comes back with colon (`NSE_FO:NIFTY...`). Map back via `instrument_token` field in response.
- **Option chain instrument key:** Must be `NSE_INDEX|Nifty 50` — any other format returns empty/error.
- **Monthly expiry epoch:** Use `datetime.fromtimestamp(epoch/1000, tz=timezone.utc)` — local timezone causes IST offset bug (date shifts by one day).
- **Monthly NSE options expire last Tuesday of the month.** Monthly symbols show only month name; weeklies show full date.
- **Nifty Index LTP:** `NSE_INDEX|Nifty 50` can be included in the standard V3 LTP batch call alongside equity and F&O keys — no separate endpoint needed for spot price.
- **Upstox has no MF API.** No holdings, NAV, or transaction endpoints in V2 or V3. Community requests confirmed unanswered as of Feb 2026.
- **Yearly-expiry option Greeks are not reported.** Known Upstox limitation —
  the December/yearly-band contracts return `option_greeks.delta` as missing/None (silently coerced to `0.0` by any `_safe()`-style helper), even at high OI.
  Confirmed 2026-07-28 via `find_chain_entry` against the 2026-12-29 Nifty chain (OI 2.2M, spread 0.01%, delta reported as 0.000 — implausible for a real ~4% OTM 154-DTE call).
  Any strategy relying on delta-based exit signals (e.g. `evaluate_cc`'s DELTA_STOP/DELTA_WARN) cannot be trusted against a yearly-expiry position —
  LOSS_STOP (premium multiple) becomes the only working defense for that band.

---

## Upstox API Status

| Capability | Status | Notes |
|---|---|---|
| Market quotes (LTP, OHLC) | ✅ Available | Analytics Token |
| Option chain (live, Greeks, OI) | ✅ Available | `NSE_INDEX\|Nifty 50` only |
| Historical candles (active instruments) | ✅ Available | Analytics Token |
| Portfolio & positions (read) | ✅ Available | Daily OAuth Token required |
| Websocket streaming | ✅ Available | Analytics Token |
| Order placement / modification / cancellation | ⛔ Blocked | Static IP required |
| GTT orders | ⛔ Blocked | Static IP required |
| Webhooks | ⛔ Blocked | Static IP required |
| Historical candles (expired instruments) | ⛔ Blocked | Paid subscription |
| Expired option contracts | ⛔ Blocked | Paid subscription |
| Mutual fund data | ⛔ N/A | Does not exist in Upstox API |

---

## Strategy Definitions

### Finideas ILTS (`finideas_ilts`)

| Leg Role | Instrument | Key | Entry Price | Qty | Direction |
|---|---|---|---|---|---|
| EBBETF0431 | ETF | `NSE_EQ\|INF754K01LE1` | ₹1388.12 | 438 | LONG |
| NIFTY_DEC_PE | NIFTY DEC 23000 PE | `NSE_FO\|37810` | ₹975.00 | 0 (closed 2026-07-14 @ ₹269.95) | — |
| NIFTY_JUL_CE | NIFTY JUL 23000 CE | `NSE_FO\|63895` | ₹1245.00 | 0 (closed 2026-07-14 @ ₹1164.05) | — |
| NIFTY_JUL_PE | NIFTY JUL 23000 PE | `NSE_FO\|63896` | ₹90.95 | 0 (closed 2026-07-14 @ ₹26.95) | — |

> Note: EBBETF0431 net qty = 465 @ avg ₹1388.01 (trade-adjusted via `apply_trade_positions()`).
> Entry prices above are from strategy definition; actual cost basis driven by `trades` table.
> JUN CE/PE (`NSE_FO|37799`/`NSE_FO|37805`) rolled to JUL CE/PE on 2026-06-17 — see TODOS.md session log.
> Both JUL legs and the DEC PE hedge were closed manually via Zerodha on 2026-07-14; `finideas_ilts` currently holds only the EBBETF0431 leg.

### Finideas FinRakshak (`finrakshak`)

| Leg Role | Instrument | Key | Entry Price | Qty | Direction |
|---|---|---|---|---|---|
| NIFTY_DEC_PE | NIFTY DEC 23000 PE | `NSE_FO\|37810` | ₹962.15 | 0 (closed 2026-07-14 @ ₹269.95) | — |

### FinRakshak Protected MF Portfolio

| Scheme | AMFI Code | Inv. Amt. (₹) | Units |
|---|---|---|---|
| DSP Midcap Fund - Regular Plan - Growth | 104481 | 4,39,978.00 | 4,020.602 |
| Edelweiss Small Cap Fund - Regular Plan - Growth | 146193 | 3,79,981.00 | 8,962.544 |
| HDFC BSE Sensex Index Fund - Growth Plan | 101281 | 1,87,371.53 | 291.628 |
| HDFC Focused Fund - Growth | 102760 | 7,89,960.50 | 3,511.563 |
| Kotak Flexicap Fund - Growth | 112090 | 2,35,105.58 | 5,766.492 |
| Mahindra Manulife Mid Cap Fund - Regular Plan - Growth | 142109 | 4,49,977.50 | 13,962.132 |
| Parag Parikh Flexi Cap Fund - Regular Plan - Growth | 122640 | 17,19,925.75 | 32,424.322 |
| quant Small Cap Fund - Growth - Regular Plan | 100177 | 1,16,321.50 | 714.722 |
| Tata Nifty 50 Index Fund - Regular Plan | 101659 | 5,87,002.67 | 4,506.202 |
| Tata Value Fund - Regular Plan - Growth | 101672 | 9,59,956.25 | 3,726.583 |
| WhiteOak Capital Large Cap Fund - Regular Plan Growth | 150799 | 2,99,985.00 | 20,681.514 |

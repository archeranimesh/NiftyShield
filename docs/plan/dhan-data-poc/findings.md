
# Dhan data API POC — findings

> Run facts for the Dhan data API POC. No task checkboxes here; status lives in `tasks.md`. Record only what was measured; inferences are marked. No credentials, tokens, client ids or payment links.
> This file was started before DDP-1 by an exploratory live probe on 2026-10-05, so the first section holds measured facts that DDP-1, DDP-3 and DDP-5 will build on, not completed tasks.

## Task status as of 2026-10-05

None of DDP-1 to DDP-6 is ticked. The probe did part of the groundwork for four of them.

| Task | State | What the probe did and did not cover |
|---|---|---|
| DDP-1 docs read | Not done | Docs not read. The probe shows what responds, not what the docs state; limits, price and bundled dataset unrecorded. |
| DDP-2 purchase | Done by Animesh, not recorded | The profile call shows the data plan active. Plan name and price are still to be stated by Animesh; no estimate is recorded here. |
| DDP-3 coverage inventory | Started | Live chain per expiry and expired-option depth sampled. Per-strategy table, strike-range limit, candle sizes and delta bands not done. |
| DDP-4 old-data validation | Not started | No comparison against stored Upstox chain, bhavcopy or paper trades. |
| DDP-5 contract questions | Started | Dhan's Dec 2026 and Jun 2027 live chains were measured. The Upstox flip date, the relabelling and the 16 deep-OTM strikes were not. |
| DDP-6 verdict | Not started | Depends on DDP-3 and DDP-4. |

## Subscription state (DDP-2 input)

The profile endpoint reported the data plan as Active with validity to 2026-11-04 16:01 (one month from purchase). Plan name and price: not yet stated by Animesh.

## Endpoint probe, 2026-10-05

Script: `scratch/data_probes/2026-10-05_dhan_data_api_probe.py`. Read-only; 19 of 19 calls returned data. NIFTY index is security id 13 in segment IDX_I.

| Endpoint family | Result |
|---|---|
| Market feed (ltp, ohlc, quote) | Responds. The index has no depth; the equity sample (TCS) showed 5-level depth. |
| Daily and intraday candles | Respond with open, high, low, close, volume. Intraday tested at 5-minute candles, 150 rows over four days. |
| Live option chain | 244 strikes on the nearest expiry. Per strike: LTP, IV, OI, volume, top bid and ask, delta, gamma, theta, vega. |
| Expiry list | 18 expiries from 2026-10-06 to 2031-06-24. |
| Expired options (rolling) | Fields: open, high, low, close, iv, oi, volume, strike, spot; no delta, Greeks, bid or ask. Worked at ATM, ATM±10; 60-minute only (script limit). |
| Expired options, history depth | Five-day windows 60 to 1825 days back all returned rows (earliest 2021-10-02 to 2021-10-06), so both expiry regimes (before and after April 2026) are present. |

## Live chain by expiry, 2026-10-05 snapshot

One snapshot, taken during a single session; it says nothing about when the Greeks started.

| Expiry | Strikes | Delta present CE / PE | Real two-sided quotes | Read |
|---|---|---|---|---|
| 2026-12-29 | 249 | 78 / 94 | 191 | Liquid; strikes at delta 0.15 exist on both sides |
| 2027-03-30 | 32 | 9 / 10 | 19 | Thin, usable near ATM |
| 2027-06-29 | 33 | 11 / 9 | 10 | Thin; PE 21000 at delta -0.149 has a tight quote |
| 2027-09-28 | 30 | 5 / 6 | 3 | Mostly model values |
| 2027-12-28 | 39 | 12 / 18 | 22 | Thin |
| 2028-06-27 | 33 | 9 / 12 | 1 | Model values only |
| 2028-12-26 | 38 | 10 / 16 | 14 | Thin |
| 2029-06-26 to 2031-06-24 (5 series) | 32 to 35 | 5 to 17 per side | 0 to 8 | Model values only |

Delta and IV are populated on every expiry (IV on 30 or more rows each). Beyond Dec 2026 only about 30 to 39 strikes are listed, and most deltas sit on strikes with no OI and no bid or ask. From Sep
2027 the call side has no deltas below about 0.4 to 0.5, so the 0.12 to 0.18 delta call strikes are not listed there. Two requests (2027-12-28 and 2028-06-27) hit the rate limit (error 805) in the
first scan at a 3.2 s gap and returned on a retry at 6 s; use at least 4 s between chain calls.

Dec 2026 near delta 0.15, same snapshot: CE 24450 delta 0.150, bid 89.45, ask 92.6, OI 17810; PE 21300 delta -0.149, bid 143.05, ask 149.3, OI 9945. Only about a third of the Dec 2026 rows carry a
nonzero delta; the rest (deep OTM) are zero. Whether Dhan ever had an all-zero state like Upstox's (zero on every row until 2026-09-21) cannot be told from one snapshot.

## What this does and does not say against the POC pass criteria

Measured so far, pending DDP-1 and DDP-3: the dataset reaches back past April 2026 (pass on depth). Delta or IV: the live chain has delta; the expired data has IV only, so a delta from it would be a
model delta from IV and must be stated as such. Coverage of the 0.12 to 0.18 delta strikes: pass for live Dec 2026, unknown for expired data (offsets tested only to ATM±10, and the strategies' strike
offsets are not yet read from code). Agreement with held data: untested (DDP-4).

Open items this probe raised, for DDP-3 to settle: how far out the strike offset reaches on weekly and monthly expiries; other candle sizes on expired data (1, 5, 15, 25); the `expiryCode` values
(annexure) and what "near expiry" means for far-dated contracts; ATM+11 to confirm the reach is a hard limit; request quotas; whether the expired data has any delta at all or the docs name one.

## Dhan docs read (DDP-1), 2026-10-05

Sources: dhanhq.co/docs/v2 "Expired Options Data", "Option Chain" and "Annexure" pages; dhan.co support page "How does the DhanHQ Data API subscription work". Fetched through a summarising web tool,
not read verbatim, so exact wording is unchecked. Each row is marked stated (S) or unclear (U).

| Item | What the docs say | S/U |
|---|---|---|
| Expired options endpoint | `POST /charts/rollingoption`; params: segment, interval, securityId, instrument, expiryCode, expiryFlag (WEEK or MONTH), strike, drvOptionType, requiredData, dates | S |
| Expired fields | open, high, low, close, iv, volume, strike, oi, spot. No delta, Greeks, bid or ask are named | S |
| Expired strike coverage | ATM+10 to ATM-10 for index options near expiry; ATM+3 to ATM-3 for all other contracts. Strikes are ATM-relative, not a full chain | S |
| Expired expiry coverage | Weekly and monthly, index and stock options; "near expiry" wording leaves far-dated reach unclear | S / U |
| History depth | Last 5 years | S |
| Candle sizes | 1, 5, 15, 25 and 60 minutes. The docs' own example request uses 1-minute candles on expired data; the probe tried 60 only | S |
| Max window per request | Expired options: 30 days per call. Intraday candles (`/charts/intraday`): 90 days per call | S |
| Rate limit, data APIs | Not stated. Error 805 "too many requests or connections" exists; error 806 "Data APIs not subscribed" | U |
| Live option chain fields | Delta, theta, gamma, vega, IV, LTP, average price, previous close, volume, OI, previous OI, top bid and ask with quantities, security id | S |
| Live chain rate limit | One unique request per 3 seconds (the probe saw 805 at a 3.2 s gap, so allow 4 s or more) | S |
| Live chain strikes | All available strikes per underlying and expiry | S |
| Live chain is a snapshot | No date parameter, so no historical Greeks from the chain; Greeks can only be captured forward from now | S |
| Daily and intraday candles | `/charts/historical` and `/charts/intraday`: OHLC and volume; open interest only via the optional `oi` flag. Intraday 5 years back. No bid, ask, delta or IV | S |
| Full market depth | 20-level and 200-level depth over WebSocket, NSE equity and derivatives, live only (50 instruments per 20-level connection, 1 per 200-level). No historical depth | S |
| `expiryCode` values | Expired-options page says "refer here" and lists none; the annexure entry is still to be read | U |
| Meaning of "near expiry" | The ATM±10 window is for index options "near expiry"; the page does not define the term, so far-dated contracts may get only ATM±3 | U |
| Strike basis | Expired strikes are stored relative to spot (rolling ATM offsets), minute level, pre-processed by Dhan | S |
| Price | 499 rupees plus taxes per month, renews every 30 days. Free-for-trades promotion discontinued per Dhan's support page | S |
| Bundled "historical data set" | Not a downloadable dataset: the subscription is API access to historical, expired-options, live, tick and expired-futures data | S |

Limits this puts on the POC (from the docs, 2026-10-05): Dhan stores no historical bid or ask, so it cannot answer fill-quality or spread questions for backtests, whatever the volume of data. Any
historical delta is a model delta from the stored IV, to be labelled so. The live chain's Greeks can be captured forward only; a daily Dhan chain capture before the plan lapses on 2026-11-04 is the
only way to build an overlapping Greeks history against the stored Upstox chain (a proposal for DDP-3, not yet decided; chain calls need at least 4 s spacing).

Discrepancy to settle in DDP-3: the docs name ATM±10 for index options, and the probe reached ATM±10 only. Whether the 0.12 to 0.18 delta strikes sit inside ATM±10 depends on strike step and expiry;
that is DDP-3's check, not a docs fact.

### POC criteria scored from docs alone

| Criterion | Score | Why |
|---|---|---|
| Covers the expiries and 0.12 to 0.18 delta strikes the rules pick | Cannot tell | ATM±10 is documented; reach to those deltas is unmeasured, and far-dated historical reach is unstated. To DDP-3 |
| Reaches back past April 2026 | Pass | 5 years stated; the probe returned 2021 rows |
| Carries delta or IV | Partial pass | IV is stated for expired data; delta is not. Any historical delta is a model delta from IV and must be labelled so. Live chain has delta |
| Agrees with what we hold on overlapping dates | Cannot tell | Needs data; DDP-4 |

Price recorded here is Dhan's published list price, not a figure Animesh stated; DDP-2 still needs his actual plan and price.

## Probe script review, 2026-10-05

Review of `scratch/data_probes/2026-10-05_dhan_data_api_probe.py` against the claims above. The script is read-only and prints no credentials. Gaps in what it tested, to carry into DDP-3:

| Gap | Effect on the findings |
|---|---|
| Expired interval hardcoded to 60 | Earlier "60-minute only" wording was a script limit; corrected above |
| Strikes tried: ATM, ATM+10, ATM-10 only | ATM±10 reach is documented, not measured; ATM+11 untried |
| `expiryCode` fixed at 1, weekly tried for ATM CALL only | Far-dated expired data (Dec 2026, Jun 2027) untested; weekly PUT and weekly ATM±10 untested |
| Chain probe fetches first and last expiry, CE delta only | The 8-expiry table above came from a run whose script is not in `scratch/data_probes/`, so it cannot be reproduced from disk |
| Chain gap 3.2 s | At the documented 3 s limit; caused the 805 errors. Use 4 s or more |
| Output to stdout only | No raw responses saved; DDP-3 should write raw JSON to the scratchpad |

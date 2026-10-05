
# Dhan data API POC — findings

> Run facts for the Dhan data API POC. No task checkboxes here; status lives in `tasks.md`. Record only what was measured; inferences are marked. No credentials, tokens, client ids or payment links.
> This file was started before DDP-1 by an exploratory live probe on 2026-10-05, so the first section holds measured facts that DDP-1, DDP-3 and DDP-5 will build on, not completed tasks.

## Task status as of 2026-10-05

None of DDP-1 to DDP-6 is ticked. The probe did part of the groundwork for four of them.

| Task | State | What the probe did and did not cover |
|---|---|---|
| DDP-1 docs read | Not done | Docs not read. The probe shows what responds, not what the docs state; limits, price and bundled dataset unrecorded. |
| DDP-2 purchase | Done and recorded 2026-10-05 | See "Purchase record" below. |
| DDP-3 coverage inventory | Started | Live chain per expiry and expired-option depth sampled. Per-strategy table, strike-range limit, candle sizes and delta bands not done. |
| DDP-4 old-data validation | Not started | No comparison against stored Upstox chain, bhavcopy or paper trades. |
| DDP-5 contract questions | Started | Dhan's Dec 2026 and Jun 2027 live chains were measured. The Upstox flip date, the relabelling and the 16 deep-OTM strikes were not. |
| DDP-6 verdict | Not started | Depends on DDP-3 and DDP-4. |

## Subscription state (DDP-2 input)

The profile endpoint reported the data plan as Active with validity to 2026-11-04 16:01 (one month from purchase).

## Purchase record (DDP-2), 2026-10-05

From a screenshot of the Dhan account page "Data APIs from Dhan", supplied by Animesh. Taxes are not shown on that page. No credentials, client ids or payment links are recorded.

| Item | Value |
|---|---|
| Status | Active; access until 04 Nov 2026 |
| Plan bought | Monthly Plan, 499 rupees per month |
| Recurring payment | Enabled (auto-renews unless cancelled before 04 Nov 2026) |
| Yearly plan on offer | 399 rupees per month, 4,788 rupees paid per year |
| Features listed | Real-time price; historical data for 5 years; 20-level market depth; option chain on APIs; full market depth; expired options data |
| Access method | Dhan Data API with the access token from the existing Dhan token flow (`src.auth.dhan_verify`), credentials in `.env` |

Yearly against twelve monthly payments: 4,788 against 5,988 rupees before taxes, a saving of 1,200 rupees (20 percent). That is the figure DDP-6 weighs; it is arithmetic on the displayed prices, not a
verdict.


## Endpoint probe, 2026-10-05

Script: `scratch/data_probes/2026-10-05_dhan_data_api_probe.py`. Read-only; 19 of 19 calls returned data. NIFTY index is security id 13 in segment IDX_I.

| Endpoint family | Result |
|---|---|
| Market feed (ltp, ohlc, quote) | Responds. The index has no depth; the equity sample (TCS) showed 5-level depth. |
| Daily and intraday candles | Respond with open, high, low, close, volume. Intraday tested at 5-minute candles, 150 rows over four days. |
| Live option chain | 244 strikes on the nearest expiry. Per strike: LTP, IV, OI, volume, top bid and ask, delta, gamma, theta, vega. |
| Expiry list | 18 expiries from 2026-10-06 to 2031-06-24. |
| Expired options (rolling) | Fields: open, high, low, close, iv, oi, volume, strike, spot; no delta, Greeks, bid or ask. Worked at ATM and ATM±10, weekly and monthly; 60-minute only (script limit). |
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
| `expiryCode` values | Annexure: 0 near, 1 next, 2 far. Measured on `rollingoption`: 1, 2, 3 accepted; 0 and 4 rejected (DH-905), so the annexure scheme does not fit this endpoint | S / measured |
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
| `expiryCode` fixed at 1, weekly tried for ATM CALL only | Closed by the DDP-3 matrix below: codes 1 to 3, weekly and monthly, CALL and PUT, ATM±10 and ±11 |
| Chain probe fetches first and last expiry, CE delta only | The 8-expiry table above came from a run whose script is not in `scratch/data_probes/`, so it cannot be reproduced from disk |
| Chain gap 3.2 s | At the documented 3 s limit; caused the 805 errors. Use 4 s or more |
| Output to stdout only | No raw responses saved; DDP-3 should write raw JSON to the scratchpad |

## Coverage inventory (DDP-3), 2026-10-05

Script: `scratch/data_probes/2026-10-05_dhan_ddp3_coverage.py` (plumbing in `scratch/_lib/dhan_data_api.py`); raw responses are in the session scratchpad, not the repo. Read-only; about 75 calls.
Window for the matrix: 2026-09-26 to 2026-10-05, 60-minute candles, 35 rows per full case. Trading days present: 09-28, 09-29, 09-30, 10-01, 10-05 (10-02 is a market holiday). Model deltas below are
an inference: Black-Scholes from the stored IV, spot and strike, with the expiry taken from the Tuesday rule and r=6.5%. Dhan returns no delta for expired data. Sample size is five trading days, so
the deltas show the shape of the window, not a distribution.

### Measured, expired options (`rollingoption`)

| Question | Result |
|---|---|
| Strike reach | ATM±10 works; ATM±11 returns zero rows in all 24 weekly and monthly cases tried (CALL and PUT, codes 1 to 3). ATM±10 sits 2.1 to 2.3 percent from spot. A hard limit |
| Which expiries get ATM±10 | Code 1 (weekly and monthly): all 35 rows. Code 2 weekly: 14 rows, only 09-28 and 09-29. Code 2 monthly and code 3 (weekly, monthly): zero rows at ±10; ATM only |
| Expiry codes accepted | 1, 2, 3 for both WEEK and MONTH. Code 0 and 4 rejected. The yearly bucket is not offered (`expiryFlag` is WEEK or MONTH only), and nothing past code 3 exists |
| Candle sizes | 1, 5, 15 and 60 minutes work (1,540 / 308 / 104 / 28 rows over a 7-day window, which includes the 10-02 holiday). 25 minutes returns HTTP 400, though the docs list it |
| Fields present | iv, oi, volume non-zero on 34 to 35 of 35 rows at ATM; IV thins at the edge (PUT ATM+10 monthly 21 of 35, weekly 15 of 35). No delta, bid or ask |
| Date range | Depth probe in the earlier section: rows back to 2021-10; both expiry regimes present |

Model delta at the ATM±10 edge on the OTM side (call at ATM+10, put at ATM-10), inferred, by days to expiry:

| Expiry type | Days to expiry | Call edge delta | Put edge delta |
|---|---|---|---|
| Weekly, code 1 | 1 | 0.02 to 0.05 | 0.03 to 0.04 |
| Weekly, code 1 | 5 to 6 | 0.07 to 0.11 | 0.07 to 0.11 |
| Monthly, code 1 | 22 to 27 | 0.27 to 0.32 | 0.23 to 0.26 |

The window holds strikes from about 0.5 delta out to the edge value, so a target delta is covered only if it is above the edge value on that day. Scaling by the square root of time (inference), the
monthly edge would be near 0.20 at 14 days to expiry and near 0.15 at 7 days.

### Live option chain, all 18 expiries, 2026-10-05

The earlier 8-expiry table is reproduced: 2026-12-29 has 249 strikes, 78 CE and 94 PE with delta, 191 two-sided quotes; 2027-03-30 has 32, 9 and 10, 19; 2027-06-29 has 33, 11 and 9, 10. Near expiries
(10-06 to 11-23) carry 232 to 258 strikes with 60 to 123 deltas per side and 145 to 283 two-sided quotes. 2027-12-28 returned HTTP 429 at 4 s spacing on this run, so the second run's figure stands
only from the earlier probe. Raw chains are saved.

### Per-strategy coverage (entry rules read from code, 2026-10-05)

Delta targets are from `src/strategy/` (CC and PP in `nifty_track_comparison_v1.py`, collar in `collar_entry.py`, IC in `ic_expiry_config.py` and `ic_expiry_config_v2.py`). The POC criterion in
`prompt.md` named a 0.12 to 0.18 band; the code uses 0.08 to 0.25, so the criterion is restated per strategy here. Entry DTE for CC and PP was not read, so verdicts are stated by DTE.

| Strategy | Entry delta in code | Expired-data verdict | Reason |
|---|---|---|---|
| CC, PP (track comparison) | target 0.20, band 0.15 to 0.25 | Partly covered | Reachable at about 14 days to expiry or less (edge near 0.20); not at 22 to 27 days (edge 0.23 to 0.32) |
| Collar | CC 0.18, 0.20, 0.15; PP 0.20, 0.25, 0.15; entry needs 14+ DTE | Partly covered | At 14 DTE the edge is near 0.20, so 0.20 and 0.25 candidates fit and 0.15 and 0.18 do not |
| IC v1 weekly | shorts 0.10 put, 0.08 call (±0.04); wings 200 points | Partly covered | Shorts fit at 5 to 6 DTE (edge 0.07 to 0.11), thin at 1 DTE (edge 0.02 to 0.05); wings beyond ±10 |
| IC v1 monthly | shorts 0.15 put, 0.10 call (±0.06); wings 500 points | Missing | Edge at 22 to 27 DTE is 0.23 to 0.32, well above both targets; wings beyond reach |
| IC v2 monthly | shorts 0.25 put, 0.22 call (±0.03); long wings 0.10 (floor 0.05) | Partly covered | Put target touches the edge at 22 to 27 DTE; call 0.22 just outside; long wings outside |

Not scored: the CSP roll band of 0.18 to 0.28, which is a separate strategy.

### What the expired dataset cannot give, as measured

- Delta or Greeks: none. Any delta is a model delta from IV, and IV thins at the edge.
- Bid and ask: none, here or anywhere historical (depth is live-only). No fill quality.
- Strikes beyond ATM±10 on any expiry, and anything beyond ATM on codes 2 monthly and 3.
- Dec 2026 and Jun 2027 expired data: not offered. Codes stop at 3 and `expiryFlag` has no yearly option; those contracts exist only on the live chain until they expire.
- Margin, charges and exchange-quoted Greeks.

### Against the POC criteria

| Criterion | Score after DDP-3 |
|---|---|
| Expiries and strikes the rules pick | Partial: near-dated and weekly entries are inside the window; monthly entries at 20+ days and all wings are not |
| Reaches back past April 2026 | Pass (depth probe) |
| Carries delta or IV | IV only; delta is inferred |
| Agrees with what we hold | Untested, DDP-4 |

Open for Animesh: a daily Dhan chain capture before 2026-11-04 is still a proposal only. Nothing was scheduled.


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

## Old-data validation (DDP-4), 2026-10-05

Script: `scratch/data_probes/2026-10-05_dhan_ddp4_validation.py` (commits `a53c71b` to `1306668`). Raw Dhan responses: `data/historical/dhan_poc/` (gitignored; 100 pulls of 1-minute rolling data for
June to 5 October at ATM, ±5 and ±10, monthly and weekly, CALL and PUT, plus 9 paper-trade pulls; about 54 MB). Run logs: `logs/dhan_ddp4_*.log`. Read-only against Upstox Parquet, bhavcopy and
`portfolio.sqlite`. Dhan expiry for a rolling contract is inferred from the Tuesday rule, not returned by Dhan. Timestamps were verified: the first candle of each day is 09:15 IST.

### Dhan against the stored Upstox chain

Coverage first, because it limits everything below. The stored intraday chain held only one far expiry in early June (2026-12-29 on 06-02, 2027-06-29 on 06-30 and 07-01). Near expiries appear later:
on 07-21 the files hold 08-25, 09-29 and 2027-06-29 and not the front monthly 07-28. Seven June trading days (06-15 to 06-19, 06-22, 06-23) have no snapshots at all. Of 112,566 Dhan rows in minutes
that have a snapshot, 51,214 (45 percent) matched on minute, strike, option type and inferred expiry. In a 20,000-row sample of the unmatched, 61 percent had the strike under another expiry and 39
percent had no such strike. The inferred expiries are all valid Tuesdays, so the gap is the stored chain's, not the rule's. Matched rows by month: July 6,222; August 20,996; September 20,935; October
3,061. Nothing before late July could be compared.

| Field | All matched rows (n 51,214) | Rows with Dhan candle volume above zero (n 44,487) |
|---|---|---|
| Upstox LTP inside Dhan minute low to high (±0.05) | 98.7 percent (n 51,213) | 98.7 percent (n 44,486) |
| Upstox LTP minus Dhan close, rupees: p10, median, p90 | -2.65, 0.00, 2.75 | -3.00, 0.00, 3.10 |
| Relative difference when close is 1 or more: median, p90 | 1 percent, 3 percent | 1 percent, 3 percent |
| IV, Upstox minus Dhan, vol points: p10, median, p90 | -2.18, 0.00, 2.33 | -1.91, 0.00, 1.97 |
| Spot, Upstox minus Dhan, index points: p10, median, p90 | -5.40, 0.00, 5.55 | -5.50, 0.00, 5.65 |
| Open interest exactly equal | 24.6 percent | 13.2 percent |
| Open interest difference: p10, median, p90 | -21,106, 0, 9,100 | -27,430, 0, 12,415 |
| Delta, inference: model delta from Dhan IV minus Upstox absolute delta (n 47,228 and 41,162) | -0.04, 0.00, 0.04 | -0.04, 0.00, 0.03 |

Reading, marked as inference where it goes past the figures: the two vendors agree on price, IV and spot to within about 1 to 3 percent of price, about 2 vol points and 5 index points on liquid
strikes inside ATM±10. Open interest agrees at the median but rarely exactly; the cause (update timing against a different source) is not established. The delta row compares a model value to a model
value and shows consistency in method, not truth. The 1.3 percent of Upstox prices outside Dhan's minute range were not examined. Agreement between two feeds does not show either is right.

### Dhan against bhavcopy

The stored bhavcopy (`data/offline/options_ohlcv`) has one trade date in the window, 2026-06-30, an expiry day. 80 contracts matched; only 20 were covered by Dhan at the close, because a contract
leaves the rolling ATM window when spot moves, and none was covered from open to close, so no volume comparison is possible. On the 20: Dhan's last close minus the bhavcopy close has p10 -8.50, median
-0.18, p90 6.36; Dhan open interest divided by bhavcopy open interest has p10 1.00, median 1.02, p90 1.09. A first pass that used every matched contract gave misleading volume and close figures for
this reason and is not used. The bhavcopy `settle_price` column looks like the underlying settlement, not an option price (one sample: 23865.75); inference from that sample, not compared. Sample size
is too small to say more.

### Dhan against paper trades

| Result | Count |
|---|---|
| Paper rows since 2026-06-01 | 317 |
| Key not in the offline BOD file (expired contracts; no other table or file maps them) | 203 |
| Later expiry code (ATM only) | 57 |
| Beyond expiry code 3 | 27 |
| Outside ATM±10 on the day | 23 |
| Not an option | 1 |
| Checkable (all on 2026-09-30 and 10-01) | 6 |

The six checkable rows are IC v1 weekly (2), IC v2 monthly (2) and signal track (2). Entry price inside Dhan's day low to high (±0.05): 4 of 6. The two outside: an IC v2 monthly SELL of PE 22300 (27
October) at 120.75, 1.10 below Dhan's low of 121.85, which fits a bid-side paper fill against traded prices (inference); and a signal-track SELL of PE 22550 (27 October) at 399.00 against a Dhan high
of 317.45. The second is inconclusive: Dhan returned 201 of 375 minutes for that strike because it left the pulled offsets as spot fell (inference), so the true day high is missing. Paper entry times
are unknown except for signal-track trades, whose `paper_signal_entries` rows carry `entry_ts`, premium, bid and ask; that table was not used here and could sharpen the check. The 2026-08-12 onward
window the story named is effectively uncheckable beyond these six, because the keys of earlier trades cannot be resolved to a strike.

### TDL-1 test points

All six Tradetron strikes from TDL-1 sit 15 to 23 strikes from the day-open ATM (08-12 25600 at 23; 08-19 25100 at 20; 09-02 24700 at 18; 09-09 24250 at 15; 09-16 24400 at 23; 09-25 23950 at 17),
outside the ATM±10 window. They cannot be reused as test points against Dhan expired data.

### Against the POC criterion "agrees with what we hold"

Partial pass. On liquid strikes within ATM±10 from late July to 5 October the two sources agree closely on price, IV and spot (n above). Not tested or not testable: the 0.15 to 0.25 delta strikes that
monthly entries use (outside the window); everything before late July (stored chain holds no near expiry); the bhavcopy beyond one expiry day; paper trades beyond six. A disagreement was found nowhere
that the evidence lets either source be named wrong.

## Contract questions (DDP-5), 2026-10-05

Script: `scratch/data_probes/2026-10-05_dhan_ddp5_contract.py`; it scans all 18,987 stored intraday files (2026-06-01 to 10-05, 5-minute cadence, IST file names) and keeps the 2026-12-29 and
2027-06-29 expiries. A row counts as "nonzero delta" when 0 < |delta| < 1: Upstox also writes delta 1.0000 on deep ITM calls that have no traded price (51 of 176 rows at the flip, 43 of 212 on 10-05),
and those are placeholders, not Greeks. Dhan's side is the live chain saved on 2026-10-05 at 17:01 (`data/historical/dhan_poc/ddp3/`), one snapshot; Upstox's comparison file is the 15:55 snapshot of
the same day.

### When Upstox's Dec 2026 Greeks started

| Item | Last all-zero snapshot | First nonzero snapshot |
|---|---|---|
| Time | 2026-09-29 15:55 | 2026-09-30 09:51 (the first stored file that day; no 09:00 to 09:50 files exist for 09-30, so the flip happened somewhere between the two) |
| DTE | 91 | 90 |
| Rows for 2026-12-29 | 44 | 176 |
| Strikes listed | 22 (steps of 500, 1,000, 1,500) | 88 (steps of 50 near the money, 500 to 1,500 away) |
| Strike range | 15,000 to 33,000 | 15,000 to 33,000 |
| Rows with 0 < abs(delta) < 1 | 0 | 90 (141 rows have delta above 0, including the 51 placeholders) |
| Rows with IV above zero | 0 | 90 |

Zero on every row held for all 59 stored days of Dec 2026 data before the flip (2026-06-01 to 09-29, 6,671 snapshots across the quarterly, yearly and unsuffixed files). By 10-05 15:55 the chain had
212 rows, 106 strikes, 156 with a delta between 0 and 1.

The cause is an inference. Two things changed at once, the chain widened (22 to 88 strikes, 44 to 176 rows) and DTE crossed from 91 to 90, and the stored data cannot separate them. What the data does
support: the other far-dated expiry I can read behaves the same way. The 2026-09-29 expiry carries nonzero deltas on every stored day from DTE 85 down, and 2026-12-29 is all-zero at DTE 91 to 211 (59
stored days) and nonzero at DTE 90 and under (3 stored days: 09-30, 10-01, 10-05). A cutoff of about 90 days to expiry fits both, but the 2026-09-29 contract is stored only from DTE 85, so it cannot
test the cutoff from above. Treat "90 DTE" as a hypothesis with one contract behind it.

### Yearly-bucket relabelling

| Expiry | Stored in files | Bucket label | Greeks |
|---|---|---|---|
| 2026-12-29 | 06-01 to 06-11, then 07-22 on (`yearly`) and 08-17 on (`quarterly`) | `yearly` from 07-22, also `quarterly` from 08-17 | Zero to 09-29, nonzero from 09-30 |
| 2027-06-29 | 06-12 to 07-22 (`yearly` from 07-06; earlier files have no suffix) | `yearly` | Zero on all 1,722 stored snapshots, DTE 343 to 382 |

The 2027-06-29 contract was the yearly bucket from 06-12 and was last stored on 2026-07-22; both expiries appear on 07-22 only. From 07-22 the `yearly` file holds 2026-12-29 instead (the story's
"about 07-24" was one trading day late: 07-22 is the first file with Dec 2026 in a `yearly` file). Jun 2027 is stored nowhere after 07-22 in the intraday files, and 19 of the 233 EOD files (2026-06-12
to 07-21) carry it. So Upstox's current Jun 2027 Greeks, at DTE 267 today, were never measured by this repo; the one live Upstox call that would settle it is not made here.

### Dhan on Dec 2026 and Jun 2027, 2026-10-05 live chain

Dhan has no historical chain, so it cannot be asked what it showed during Upstox's zero window (June to 09-29). The expired endpoint has no yearly flag and stops at expiry code 3. All that can be said
is how Dhan's live chain compares to Upstox's on the same day.

| Item | 2026-12-29 | 2027-06-29 |
|---|---|---|
| Dhan rows, delta nonzero, IV above zero, two-sided quotes | 498, 172, 321, 191 | 66, 20, 38, 10 |
| Dhan and Upstox both nonzero, strikes matched | 149 of 212 matched | not stored |
| Absolute delta, Dhan minus Upstox: p10, median, p90 (n 149) | -0.095, -0.003, 0.105; largest 0.207 | n/a |
| IV, Upstox minus Dhan, vol points: p10, median, p90 (n 149) | -3.93, -1.16, 3.53 | n/a |

The two sets of deltas are not close enough to call identical. Near delta 0.15 on Dec 2026 puts Upstox's absolute delta runs about 0.01 above Dhan's (PE 21300: Dhan -0.149, Upstox -0.159), and on
calls about 0.01 below (CE 24450: Dhan 0.150, Upstox 0.136). The sign pattern (puts higher, calls lower on Upstox) looks like a different forward or rate assumption, but that is an inference; the docs
do not name either vendor's model. Timing also differs (17:01 against 15:55), so some of the spread is the clock. The docs do not say whether Dhan's chain Greeks are exchange fields or model values,
so no claim is made; at DTE 85 on a 0.1 to 0.5 delta strike they agree to about 0.01 to 0.02.

The 16 deep OTM puts at 20,050 to 20,800 (no calls at those strikes carry a real delta): Upstox shows a nonzero delta on 3 of 16 (20,200, 20,500, 20,800), so 13 are zero on 10-05 15:55, and all 13
have no LTP. Dhan shows a nonzero delta on 4 of 16 (the same three plus 20,300, which Upstox leaves at zero). The remaining 12 on Dhan are zero delta but carry IV values between 0.66 and 0.88, which
looks like a placeholder; none had an LTP. Neither vendor has a usable delta where no trade or quote exists, so these strikes need a model value from either source, and Dhan does not supply one.

### Live Upstox check on Jun 2027, 2026-10-05 21:11 IST

One read-only chain call per expiry (`scratch/data_probes/2026-10-05_upstox_jun2027_greeks_check.py`, raw JSON in the session scratchpad). Jun 2027 (DTE 267): 14 strikes, 28 rows, no row with 0 <
abs(delta) < 1, IV zero on every row, while 13 rows have a traded price and open interest and 12 have a two-sided quote. So the zero state is not an early-listing artefact: the contracts trade and
quote and Upstox still returns no Greeks. Control call on 2026-12-29: 106 strikes, 156 nonzero deltas, 199 two-sided rows, identical to the 15:55 snapshot, so the call and the parser work. Dhan lists
33 strikes for the same Jun 2027 expiry with 20 nonzero deltas, so on this day Dhan has Greeks where Upstox has none (one snapshot; Dhan's are model values or not, the docs do not say).

### Decision for Animesh on `greeks-bs-fallback` (flagged, story not edited)

The fallback is still needed: Upstox returns no Greeks on Jun 2027 at DTE 267, consistent with the DTE 90 cutoff hypothesis (inference). The yearly bucket should move to Jun 2027 around 2026-12-30 and
stay zero until about late March 2027 (inference). One decision: whether GF-5's ground truth for the computed delta is Dhan's live chain, which covers Jun 2027 where Upstox is blank, with Dec 2026 as
the overlap where both vendors carry deltas (agreement 0.01 to 0.02, so GF-5's tolerance should not be tighter than 0.02). Dhan's Jun 2027 chain is thin (33 strikes, 10 two-sided quotes), so a Dhan
delta there is itself a thin reference.

### Dhan expired data for 2025: no yearly contract, 2026-10-05

Script: `scratch/data_probes/2026-10-05_dhan_2025_yearly_check.py`; ATM calls, 60-minute candles, expiry codes 1 to 3, MONTH and WEEK, five 2025 windows (January, June, September, October, December).
Dhan returns no expiry date, so each contract's expiry is inferred by solving Black-Scholes for time to expiry from the stored close, spot, strike and IV. That inference runs about 20 to 35 percent
long (for example, 28 days for a 22-day contract), so only the pattern is used, not the dates.

The codes behave as the next three monthly series (code 1 about 25 DTE, code 2 about 55 and code 3 about 85 to 90 DTE) and the three weeklies. The roll test shows it: over 2025-09-15 to 10-14, code 1
rolls to the next month on 09-30 (the September expiry), and code 3 jumps on 10-01 from a contract about 70 DTE out to one about 90 DTE out, which on the calendar is the 2025-12-30 expiry (inference).
So the Dec 2025 contract first appears on Dhan's expired data on 2025-10-01, at about 90 DTE, and never earlier. No 2025 window returned a contract more than about 90 DTE out, so Dhan holds no
historical data for yearly or LEAPS contracts, in 2025 as in 2026. Its reach ends at the same ~90 DTE as the point where Upstox's Greeks start (an observation, with no cause established).

Related, measured in DDP-5: since 2026-08-17 the 2026-12-29 contract sits in both the `quarterly` and `yearly` Upstox bucket files, and the yearly label has pointed to 2027-06-29 (to 07-22) and then
2026-12-29 (DTE 160 down to 85). A "yearly" bucket that holds an 85-DTE contract is a quarterly in practice.

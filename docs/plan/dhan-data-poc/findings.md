
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
| Expired options (rolling) | Fields: open, high, low, close, iv, oi, volume, strike, spot. No delta, Greeks, bid or ask. Worked at ATM and ATM±10, weekly and monthly; 60-minute candles only. |
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

Open items this probe raised, for DDP-3 to settle: how far out the strike offset reaches on weekly and monthly expiries; 1-minute candles; the per-request window cap; request quotas; whether the
expired data has any delta at all or the docs name one.

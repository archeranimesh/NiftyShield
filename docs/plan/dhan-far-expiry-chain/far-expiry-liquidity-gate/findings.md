# Far-Expiry Liquidity Gate — FG-1 calibration findings

> Proposed spread cap, OI floor, quote rule and fallback ladder per expiry type, from the captured far-expiry chain. Status: **signed off by Animesh 2026-11-02 with one amendment (yearly spread cap
> 10%, not 5%)**; FG-2 may start.

## Window and method

Source: `far_expiry_chain_snapshots` (source `dhan`), 15 trading days, 2026-10-12 to 2026-11-02, one post-close snapshot per day. Two expiries captured: 2026-12-29 (about 2 months out, the "near far"
expiry) and 2027-12-28 (the yearly tenor, about 14 months out). NIFTY spot ranged 22363 to 23441 over the window (about 5%). Per day and option type, the target-delta strike is the row with non-zero
delta closest to |0.15| (the FC-5 report default); spread is `(ask - bid) / ((ask + bid) / 2)`. Every date had a usable target strike (zero days without delta). Rows with delta null or zero are 60% of
the Dec 2026 table and 62% of Dec 2027, so the delta-based selection only sees the minority of strikes that carry Greeks.

## Observed distribution at the |0.15| delta strike (15 days each)

| Expiry | Side | Two-sided quote days | Spread median (two-sided) | Spread worst | OI min | OI median |
|---|---|---|---|---|---|---|
| 2026-12-29 | CE | 15/15 | about 4% | 193% | 0 | about 65k |
| 2026-12-29 | PE | 15/15 | about 6% | 25% | 2.8k | about 43k |
| 2027-12-28 | CE | 15/15 | about 3% | 12% | 68k | about 178k |
| 2027-12-28 | PE | 15/15 | about 2% | 3% | 84k | about 90k |

The yearly expiry is clearly the more reliable one at 0.15 delta: spread is 2 to 5% typical and OI never falls below 68k. The Dec 2026 expiry is erratic, with CE spreads from 1.5% to 193% and the
chosen strike's OI ranging from 0 to 930k as the nearest-delta strike hops between a liquid round strike and a dead one. At |0.10| the Dec 2026 PE side is two-sided on only 6 of 15 days. The yearly CE
side at |0.10| picked a 65-lot OI strike on 4 days, so an OI floor matters there too.

## Pass fraction at the |0.15| strike, no fallback (days passing / 15)

| Expiry | Cap 5%, OI 10k (CE / PE) | Cap 5%, OI 50k | Cap 10%, OI 10k | Cap 10%, OI 50k |
|---|---|---|---|---|
| 2026-12-29 | 8 / 7 | 8 / 4 | 8 / 8 | 8 / 4 |
| 2027-12-28 | 11 / 15 | 11 / 15 | 14 / 15 | 14 / 15 |

## Proposed thresholds

Quote rule, all expiry types: both bid and ask strictly positive (two-sided). A bid-only or ask-only strike always fails; this matches the current gate and is not relaxed.

Yearly (2027-12-28 type): spread cap 10% of mid, OI floor 50,000. **Amended by Animesh 2026-11-02** from the proposed 5%: yearly liquidity is low, so the cap is the 10% hard maximum, which passes 14
of 15 CE days and every PE day with no ladder (5% passed 11/15 CE). OI at the chosen strike is above 68k whenever the strike is genuinely liquid; 50k excludes the 65-lot strikes without excluding a
liquid one. 10% is a ceiling, not a target: nothing past it is acceptable for any expiry type.

Near-far (2026-12-29 type): spread cap 10% of mid, OI floor 10,000. Rationale: at 5% the strike passes only about half the days; the cap here is a data-driven concession, not a quality target. The OI
floor is kept low because raising it to 50k cost 3 more PE failing days with no spread benefit.

Both values are starting points to be tuned once a second source of evidence exists; they are not backed by any fill-cost data.

## Fallback ladder (ordered, data not nested conditions)

1. Keep the target strike if it passes.
2. Next strike toward ATM-side then OTM-side, ordered by closeness to target delta, restricted to |delta| in [0.10, 0.20], first that passes.
3. Next expiry type in the policy ladder (yearly falls back to near-far for evidence only; no cross-tenor substitution without a human decision).
4. Fail closed: no entry, log the reason (spread, OI, one-sided).

Check of step 2 on the window: with the band [0.10, 0.20], cap 10% and OI 10k, at least one passing strike existed on 15 of 15 days for every expiry and side (both CE and PE, both expiries). So the
ladder rescues the days the strict target-strike gate rejects (Dec 2026: 8/15 to 15/15).

## What the data cannot say

Only 15 trading days with one post-close snapshot each: no intraday spread, no event days (a drop in spot beyond 5%, VIX spike, expiry-week effects), no behaviour across the Dec 2026 roll. The Dec
2027 history covers 14 months to expiry only; liquidity improves as an expiry nears, so the thresholds describe the far end, not the full yearly life. Post-close quotes understate live liquidity at
09:15 to 10:00 when the entry would actually trade. Displayed quotes only, not market impact or fills. Delta is missing for the majority of rows, so strikes without Greeks are invisible to the ladder;
whether those are the illiquid ones was not tested. FG-3 (roll-window) needs the same data but at DTE values this window cannot reach.

## Decision for Animesh

Sign off the thresholds above (or amend) before FG-2. FG-2 should put the per-expiry-type config in a policy-registry location (name it in the FG-2 pre-edit file list) and keep the defaults of
`_apply_liquidity_gate` unchanged for existing callers.

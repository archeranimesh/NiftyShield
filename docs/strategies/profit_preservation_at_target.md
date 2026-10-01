# Profit preservation after a target hit — carry vs bank (Greek analysis)

> Reference note, not a spec. Derived 2026-10-01 from the SignalTrackV1 trade `paper_signal_track_v1` (trade_id 408). All numbers are Black-Scholes estimates, not observed Greeks. Paper trading only.

## The case

Long 1 lot (65 qty) NIFTY 22550 PE, expiry 27 Oct 2026, bought at 265.225 (09:30:35 IST, spot ~22,540, VIX 13.79). The 50% target fired at 12:54:14 IST: mark 400.0, SELL fill 399.0, realised
+₹8,695.38 per lot (gross of costs). The put closed the day at ~329.4, about ₹4,500 per lot below the fill. Question: could the profit have been protected, with upside kept, by adding option legs and
carrying overnight?

## Data and assumptions

`intraday_market_snapshots` holds only `nifty_spot` and `india_vix`, with UTC timestamps (12:54 IST = 07:24 UTC). No stored chain or Greeks exist for that moment, so Greeks come from Black-Scholes.

Assumptions: r = 6.5%, q = 1.3%, flat IV across strikes (no skew), spot at 12:54 ~22,360, VIX ~15.0. The entry price solves to IV 12.5% and the 400 mark to IV 14.4%. Put Greeks per unit at 12:54:
delta -0.541, gamma 0.00046, theta -₹4.8/day, vega ₹23.7/vol point. Overnight scenarios use 1 calendar day of theta. 2 Oct 2026 is (verify against the NSE list) a Gandhi Jayanti holiday, so
"overnight" really means a 4-day closure to Monday; a 4-day-theta rerun changed the grids by under ~₹600, mostly on call hedges. Weekly expiry is Tuesday (6 Oct).

## Core identity

Any carried combination equals "bank the profit, then open a new position". So the question is never "how do I protect the open put" but "which new position gives a hard floor and keeps downside
convexity at the lowest cost". There is no free lunch: convexity costs theta, and anything that adds protection by selling premium sells the tail.

## Candidates, per lot, net Greeks at 12:54

| Position | Net delta | Theta/day | Vega/pt | Verdict |
|---|---|---|---|---|
| Long 22550 PE alone | -35 | -₹312 | +₹1,541 | baseline |
| Bear put spread 22550/22200 | -10 | +₹18 | +₹61 | greek-flat; sells ~55% of upside; gross floor -₹2,023 on a rally |
| + long 22400 CE (guts strangle) | -1 | -₹848 | +₹3,087 | a long straddle, not a hedge; loses -₹8.0k at flat spot with IV -2 |
| + short OTM call | more negative | n/a | n/a | not a hedge: adds short delta and short gamma, naked margin |
| 1x2 ratio 22550 / -2x22200 | +14 | +₹349 | -₹1,419 | inverts the goal: pays on a rally, loses -₹3.7k at -2% with IV +2, -₹74.6k at 20,500 |
| Fly +1 22550, -2 22200, +1 21850 | -1 | +₹66 | -₹219 | hard floor +₹5.2k, peak +₹28k at 22200 on expiry, but overnight it is flat (₹8.0–9.3k), no upside |

Long future: one lot is +65 delta against the put's -35, so it overhedges and leaves long gamma and vega. NiftyBees can hit ~35 delta (~3,500 units, ₹7.8 lakh) but ties up full capital.

## Best structure: bank, then free-roll

Sell at 399, then buy a small OTM put with part of the profit. The floor is 8,695 minus the premium paid, whatever spot or IV does. Maximum extra loss is the premium, no margin beyond it, full gamma
on the way down. P&L per lot after 1 day, IV unchanged unless noted:

| Free-roll | Premium/lot | −2% | −1% | 0 | +1% | +2% |
|---|---|---|---|---|---|---|
| Weekly 22100 PE (6 Oct) | ₹3,350 (51.5) | 20,874 | 12,601 | 7,985 | 6,067 | 5,490 |
| Weekly 22100 PE, IV -2 | | 19,839 | 11,400 | 7,144 | 5,705 | 5,392 |
| Monthly 21700 PE (27 Oct) | ₹5,797 (89.2) | 16,102 | 11,645 | 8,446 | 6,263 | 4,849 |
| Bear spread 22550/22200 | n/a | 13,420 | 11,151 | 8,779 | 6,465 | 4,355 |

The weekly 22100 beats the bear spread by ~₹7.5k at -2% and ~₹1.1k at +2%, and gives up ~₹800 at flat. Costs on top of the exit already being taken: ~₹60 statutory plus ~₹65 per side half-spread,
about ₹130–200, plus ~₹700 modelled overnight theta.

## Recommendation

Bank at the target as the base case. To keep convexity, spend about ₹3.4k of the profit on the weekly 22100 put (cheaper strike if the live quote allows) and treat it as the explicit price of
insurance, expected cost theta plus friction (hundreds of rupees a night). The bear spread is dominated by it; the ratio spread and fly give up the upside you want to keep.

Methodology caution: one trade is one sample, and the intraday exit rule is the thing under test. Overnight hedging changes the strategy being evaluated, so test a carry rule on the signal (partial
exit with a runner, trailing stop) separately, not by bolting on legs to one outcome.

## Caveats and open items

- The weekly price is likely overstated: 6 Oct is ~2 trading sessions away and market makers price trading-day variance, so the real quote is probably lower. Check the live chain and the Tuesday
  weekly first.
- The 400 mark followed a quick climb (388.85 → 395.6 → 400, ~1.6-point spread), so it likely carried a transient put-IV bump. About ₹1,600/lot of the later giveback is unexplained by delta, theta and
  VIX.
- Flat IV ignores skew: it understates what the 22200 and 21850 puts sell for and overstates call cost.
- The scenario script was scratch only (not saved). If this analysis recurs, promote it to a tested `scripts/dev/` CLI instead of re-deriving.

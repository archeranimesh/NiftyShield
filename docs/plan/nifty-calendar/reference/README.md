# nifty-calendar — reference trade evidence

Screenshots and Telegram captions of the TM Trading NIFTY Biweekly Double Calendar (3 lots), supplied by Animesh 2026-10-13. Strikes are masked in the screenshots, so these are shape and behaviour
evidence, not exact fixtures. The completed monthly trade below (supplied 2026-10-13) shows its real strikes in the exit screenshot; entry prices, entry date and IV are still missing.

## Structure (read from the legs table)

Short 3 x 19 Oct CE and PE at one strike (the expiry tent peaks near 22250 on all three days), long 3 x 27 Oct PE and CE further out. 19 Oct 2026 is a Monday, so this is probably a holiday-shifted
expiry (Dussehra 20 Oct); verify against `REFERENCES.md` before CM-0 hardcodes expiry logic. Grey 0-lot rows on 8 Oct (19 Oct 22550 CE/PE, 27 Oct 22100 PE and 22900 CE) are unchecked and the total
equals the four open legs, so they read as earlier or closed legs excluded from the payoff. That is a guess, to be confirmed by Animesh.

## Time series

| Date | File | Spot | Day move | Open P&L | Chart "projected" | Max profit / max loss | Expiry breakevens |
|---|---|---|---|---|---|---|---|
| Thu 8 Oct | `2026-10-08-payoff.png`, `2026-10-08-telegram-post.png` | 22231.80 | -1.64% | +1,079 | +960 | +54,044 (22%) / -57,741 (-23%) | 21928 (-1.4%) / 22615 (+1.7%) |
| Fri 9 Oct | `2026-10-09-payoff.png` | 22520.45 | +1.30% | -3,708 | -4,591 | +51,449 (23%) / -63,255 (-28%) | 21951 (-2.5%) / 22604 (+0.4%) |
| Mon 12 Oct | `2026-10-12-payoff.png` | 22363.35 | -0.70% | +3,760 | +4,033 | +53,849 (21%) / -57,995 (-23%) | 21923 (-2.0%) / 22607 (+1.1%) |

Per-leg open P&L: 8 Oct short CE +3,799, short PE -2,272, long PE +1,316, long CE -1,765. 9 Oct short CE -33,660, short PE +25,087, long PE -13,709, long CE +18,574. 12 Oct short CE -676, short PE
+13,904, long PE -8,434, long CE -1,034.

## Telegram captions as posted

8 Oct (from the Telegram screenshot, photo with caption in one message): "Current Live Position Update - NIFTY Biweekly Double Calendar Spread trade along with payoff graph of the setup. Expiry: 19th
October 2026".

9 Oct: "9th October 2026 / Current Live Position Update – NIFTY Biweekly Double Calendar Spread trade along with payoff graph of the setup. / Expiry: 19th October 2026 / The market has been making
unexpectedly large moves over the last two days, putting the setup's breakevens to the test. / The upside range is now quite limited. / Let's see how the position plays out on Monday!"

12 Oct: "12th October 2026 / Current Live Position Update – NIFTY Biweekly Double Calendar Spread trade along with payoff graph of the setup. / Expiry: 19th October 2026 / The market reversed today
after Friday's rally, bringing it back near the centre of our payoff graph, with breakeven range of 1%+ on both" (text as pasted, possibly cut off). Each is about 330 characters, well inside the 1024
caption cap.

## What the evidence says

- **No adjustment at 0.4% from breakeven.** The same four legs at 3 lots were held through 9 Oct, when spot was 0.4% from the upper expiry breakeven, and the position mean-reverted. Do not assume
  breakeven proximity is an adjustment trigger; the rule must come from Animesh.
- **Model tolerance.** Chart projected P&L versus live leg P&L differs by 119 (8 Oct), 883 (9 Oct) and 273 (12 Oct). Candidate acceptance tolerance for our own T+0 curve against mark-to-market: about
  ₹900, roughly 0.4% of capital.
- **The "On Expiry" curve is not a pure expiry payoff.** Max profit moved 54,044 → 51,449 → 53,849 with an unchanged structure, because the 27 Oct longs are still alive on 19 Oct and are priced with a
  model and an IV assumption. Open question for CM-0 and CM-1: does `compute_payoff` handle only expiry intrinsic value, and does a calendar need a Black-Scholes step with an IV input?
- **Margin base moves.** Percentages imply roughly ₹2.25L on 9 Oct and ₹2.5–2.57L on 8 and 12 Oct. Margin changes with spot, so a fixed-margin assumption is wrong for this structure.
- **Chart content our payoff chart lacks.** Per-leg P&L table, stat strip (max profit/loss, profit and loss left, breakevens at target and at expiry), T+0 and expiry curves together, OI bars with the
  max-OI strike, ±SD markers, and a projected-P&L pill at current spot.

## Completed monthly trade: NIFTY October monthly double calendar, 2 lots (5 to 7 Oct 2026)

Files: `2026-10-05-monthly-payoff.png`, `2026-10-06-monthly-payoff.png`, `2026-10-07-monthly-exit.png`. The entry date, entry prices and entry IV are not in the screenshots (the first one, 5 Oct,
already shows open P&L); a 7-day planned hold would put entry around 30 Sep, to be confirmed by Animesh.

**Structure, real strikes from the exit screenshot:** short 2 x 27 Oct 22600 CE and 22600 PE (ATM straddle), long 2 x 23 Nov 22200 PE and 23000 CE. Wings are 400 points either side of the straddle,
symmetric, multiples of 100. Far expiry is 23 Nov, a Monday, so likely another holiday shift of the last-Tuesday monthly (verify in `REFERENCES.md`).

| Date | Spot | Day move | Open P&L | Chart "projected" | Max profit / max loss | Expiry breakevens | Per-leg open P&L (S CE / S PE / B PE / B CE) |
|---|---|---|---|---|---|---|---|
| Mon 5 Oct | 22555.75 | +0.60% | +2,473 | +3,195 | +54,765 (32%) / -53,940 (-31%) | 22120 (-1.9%) / 23237 (+3.0%) | +19,133 / -8,505 / +6,828 / -14,983 |
| Tue 6 Oct | 22776.10 | +0.98% | +4,781 | +4,319 | +51,781 (29%) / -49,203 (-28%) | 22133 (-2.8%) / 23163 (+1.7%) | +10,384 / +4,365 / -1,882 / -8,086 |
| Wed 7 Oct exit | 22689.30 | -0.38% | +5,421 realised | n/a | n/a | n/a | +18,860 / -2,987 / +3,819 / -14,271 |

Leg P&L sums check out to the totals shown (2,473, 4,781 and 5,421). Model tolerance again: projected minus live is 722 and 462 on the two open days.

**Exit as posted, 7 Oct (about 630 characters with the header lines):** "Exited the NIFTY October Monthly Double Calendar at a profit of ₹5.4k with 2 lots. Didn't wait for the original target of ₹6k
(₹3k per lot). Exited before 10 AM ahead of the RBI interest rate decision, as the position was near the center of the payoff graph. Expected volatility after the announcement and any wild move on
either side could have reduced the existing profit. So, decided to book the gains instead of risking them for the remaining amount." The 5 and 6 Oct posts carry only the header and the expiry line (27
Oct 2026). Exit image is the same tool with booked P&L only: 0 lots, a flat payoff, and realised +5,421.

## Checks against the planned `calendar-monthly` design

- **Target matches.** ₹3,000 per lot is already the planned monthly target. The trader exited at ₹2.7k per lot (about 90% of target) by discretion, so a literal `TARGET` rule would not have fired.
- **Event-risk exit is missing from the plan.** The exit was driven by the RBI decision with the position near the centre of the payoff. `ExitDecision` has `DTE_GUARD`, `TIME_EXIT`, `TARGET` and the
  breach outcomes, but no event-calendar exit. Needs an RBI/event date source and a rule (for example: if near centre and profitable, close before the event), as a decision for Animesh.
- **Wing width differs from the plan.** The plan starts monthly wings at 600 put / 500 call and hill-climbs in 100-point steps. This trade used 400/400 on a 22600 straddle. Either the six filters
  admit 400/400 in the live chart or the start points are wrong; the selector fixture should be built from this real structure, not only the video's 22,700 sample.
- **Entry timing is unverified.** The plan enters on the first trading day on or after "the Tuesday following the previous monthly expiry". The previous monthly expiry was 29 Sep (a Tuesday); if this
  trade entered right after it, the phrase may mean the expiry day itself or the day after, not the next Tuesday. Needs the actual entry date.
- **Margin per lot.** The chart's percentages imply a base of about ₹85-90k per lot (₹171-181k for 2 lots monthly; about ₹82-85k per lot biweekly on 8 and 12 Oct). The planned CM-0 probe of
  `get_order_margin` should land near that; the video's ₹1.2L per lot is for the classic calendar.
- **Caption length.** The longest observed caption is the exit post at about 630 characters, inside the 1024 cap. A calendar entry or exit message with legs table and Greeks would not fit as a
  caption, so the audit's split-message verdict stays relevant.

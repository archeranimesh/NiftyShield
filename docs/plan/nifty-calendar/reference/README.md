# nifty-calendar — reference trade evidence

Screenshots and Telegram captions of the TM Trading NIFTY Biweekly Double Calendar (3 lots), supplied by Animesh 2026-10-13. Strikes are masked in the screenshots, so these are shape and behaviour
evidence, not exact fixtures. A completed trade with real strikes, entry prices and IV is to follow; replace this with exact fixtures when it arrives.

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

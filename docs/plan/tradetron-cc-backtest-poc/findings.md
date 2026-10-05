
# Tradetron CC backtest POC — findings

> Reference file for the story. No task checkboxes. Values are code-sourced; the archived spec (`docs/archive/strategies/covered_call_overlay_v1.md`) was read only to diff against.

## Live CC rule set

Source of truth: `src/strategy/exit_signals.py` `ExitSignalEngine.evaluate_cc` (line 269 onward), `src/paper/constants.py`, `scripts/strategies/cc_calibration/paper_cc_entry.py`, and
`src/instruments/lookup.py` `get_expiry_candidates` (line 279). `cc_overlay_v1.py` holds no thresholds; it only calls `evaluate_cc` (lines 135-149) with `delta`, `dte` and `days_held`.

| Rule | Live value (source) | Archived spec | CC-1 claim | Status |
|---|---|---|---|---|
| Call delta target | 0.15; candidates filtered to 0.12-0.18, ranked by closeness to 0.15 (`paper_cc_entry.py:197-212`) | 15 (range 10-20) | n/a | MATCH on target; the 0.12-0.18 band is extra |
<!-- lint-ignore-length -->
| Expiry selection | "monthly" = nearest last-expiry-of-calendar-month with DTE >= 14, no upper bound (`lookup.py:292-297`, DECISIONS 2026-08-12) | Wednesday after expiry, 30-45 DTE | n/a | DIFFERS: floor-only 14 DTE, no 30-45 window |
<!-- lint-ignore-length -->
| Entry day | No weekday check found in `paper_cc_entry.py`; entry is a manual script run | Wednesday after monthly expiry | n/a | DIFFERS (inference: weekday is operator discipline, not enforced; grep for weekday/Wednesday found nothing) |
| Lot cap | `floor(units / (spot / niftybees_ltp * 65))`, `LOT_SIZE = 65` (`constants.py:19,55-80`); script default 5725 units | 1 lot (65) per ~5,700 units | n/a | MATCH |
| BELOW_FLOOR | Entry credit < 12 per unit: INFO only, no profit-target check (`exit_signals.py:297`) | not specified | n/a | NEW in code |
<!-- lint-ignore-length -->
| Profit target | Mark <= 30% of entry credit (`_PROFIT_TARGET_RETENTION = 0.30`, line 15), only when entry credit >= 15 (`_CC_MIN_ENTRY_CREDIT`, line 16); ACTION | Mark <= 50% of credit | 30% remaining | DIFFERS from archive; MATCHES CC-1 |
| Loss stop | Mark >= 2.5 x entry credit (line 290-291, 3rd block); ACTION | not in spec | 2.5x | MATCH CC-1; NEW vs archive |
| Delta stop | Delta >= 0.55 (line 290; 4th block); ACTION | +0.40 | 0.55 | DIFFERS from archive; MATCHES CC-1 |
| Delta warn | Delta >= 0.45 and below 0.55: WARN only, no close | not in spec | n/a | NEW in code |
<!-- lint-ignore-length -->
| Time stop (21 days) | **Removed.** EC-5 (2026-08-02) collapsed TIME_STOP and DTE_REVIEW into one DTE rule (comment at `exit_signals.py:364-373`); `days_held` is accepted but unused | Close at 21 calendar days | "unchanged" | **DIFFERS from both: the CC-1 claim that it is unchanged is stale** |
| DTE review | DTE <= 5: ACTION, auto-close (line 375-385) | not in spec | n/a | NEW; replaces the time stop |

Notes for the template (TCP-3):

- Exit triggers the template must encode: profit target (30%, credit floor 15), loss stop (2.5x), delta stop (0.55) and DTE <= 5 close. Do not encode a 21-day time stop; the story's TCP-3 spec lists
  one, and that spec line is stale.
- `evaluate_cc` returns every signal that fires in one tick, sorted by `_sort_results`; the backtest's first-to-fire order may differ on the same candle. I did not read `_sort_results`, so how the
  paper engine picks one exit when several fire is unverified.
- Delta and mark values in the paper records are Upstox chain values. The Tradetron comparison inherits the methodology caveat in `prompt.md`.
- Not read: the full body of `get_expiry_candidates` beyond the docstring, and the rest of `paper_cc_entry.py` after line 215.

## Paper CC ground truth — thin sample (5 completed cycles)

Source: `paper_trades` where `strategy_name = 'paper_nifty_overlay'` and `leg_role = 'overlay_cc'` (`DB_REGISTRY.md` read first; the paper CC rides the overlay strategy, not a `paper_covered_call_v1`
name). Aggregate: 10 rows, 5 SELL and 5 BUY, all `CLOSED`, trade dates 2026-08-12 to 2026-10-01, quantity 65 (1 lot) on every row. `paper_leg_snapshots` has 37 daily rows for the leg (2026-08-12 to
2026-10-02) but no delta column. Prices are per unit; P&L is gross (credit minus exit, times 65), before any charges.

| # | Entry date | Expiry (DTE) | Strike | Credit | Exit date | Exit price | Exit / credit | Gross P&L (65) |
|---|---|---|---|---|---|---|---|---|
| 1 | 2026-08-12 (Wed) | 2026-09-29 (48) | 25400 | 86.725 | 2026-08-25 | 24.50 | 28.2% | 4,044.63 |
| 2 | 2026-08-26 (Wed) | 2026-09-29 (34) | 25100 | 60.825 | 2026-09-02 | 18.15 | 29.8% | 2,773.88 |
| 3 | 2026-09-09 (Wed) | 2026-09-29 (20) | 24200 | 53.900 | 2026-09-16 | 13.95 | 25.9% | 2,596.75 |
| 4 | 2026-09-16 (Wed) | 2026-10-27 (41) | 24200 | 97.475 | 2026-09-25 | 29.05 | 29.8% | 4,447.63 |
| 5 | 2026-09-25 (Fri) | 2026-10-27 (32) | 23900 | 64.425 | 2026-10-01 | 19.10 | 29.6% | 2,946.13 |

Total gross P&L across the five cycles: 16,809.00. This is a record of what happened, not a profitability claim.

What the DB does not hold, so the template cannot be reconciled on it:

- **Delta at entry: not recorded.** The entry notes carry strike, OI, DTE and expiry only; `paper_exit_events` has no CC rows and `gate_violations` has none for CC deltas. The 15-delta target is
  therefore unverifiable from the DB. The ledger holds nothing to compare a Tradetron `Find Strike` strike against except the strike itself.
- **Exit trigger: not recorded.** `paper_exit_events` for this strategy holds only six `R5_REENTRY_BLOCKED` INFO rows. Inference: all five exits are the 30% profit target, because every exit price is
  25.9% to 29.8% of its credit (at or under the 0.30 retention in TCP-1) and every credit is above the 15 floor. None of the five is a loss, delta or DTE exit. That is consistent with the ratios, not
  proven by a logged trigger.
- **Spread at entry: `None%`** in all five entry notes, so the fill is the logged price with no spread context.

Observations that bear on the template and the comparison:

- Cycle 3 entered at DTE 20 and cycle 1 at DTE 48, both outside the archived 30-45 window. This fits the TCP-1 finding that the code enforces only a 14-DTE floor and no weekday check; cycle 5 was
  entered on a Friday. The template's Wednesday and 30-45 DTE gates will therefore not reproduce cycles 3 and 5 by construction. This is a spec difference, not a platform defect.
- Cycles 1-3 share the 2026-09-29 expiry and cycles 4-5 share 2026-10-27. Each entry followed the previous exit within 0 to 7 days (1, 7, 0 and 0 days), so the five cycles are two expiries, not five
  independent samples.
- Strikes moved from 25400 to 23900 over the window, so the five strikes track a falling NIFTY and the sample covers one market regime. It says nothing about the loss, delta or DTE exit paths.
- Both expiries are the last Tuesday of the month, after the April 2026 expiry-day change.

WINDOW: 2026-08-12..2026-10-01

The window starts on the first paper entry and ends on the last paper exit. It covers every cycle and starts after 2026-04-01. The 2026-10-27 expiry is still live at the end date, so the backtest sees
cycle 5 close on 2026-10-01 only if its own exit rule fires; a template that is still open on 2026-10-01 will be force-closed or left open depending on `type=positional`, to be checked in TCP-5.

## Pre-flight verdict (TCP-3)

Draft: `template.md` (one set, one short monthly NIFTY call, `Find Strike` on delta 0.15, Universal Exit). Not saved to Tradetron; the dry-run create built the payload and nothing was posted.

**Validation.** `tt_validate_markdown` returned 0 errors. The one warning (`RUNTIME_GATE_ON_ZERO`, a guard gated on `== Number(0)`) was fixed by rebasing the `entered` guard to 1 armed, 2 after entry.
A re-run through the dry-run create returned `validation.ok: true` with no warnings.

**Backtestability.** `tt_check_backtestability`, window 2026-08-12..2026-10-01, verbatim: `verdict: backtestable`, `confidence: high`, `blockers: []`, `warnings: []`, `checks_skipped: []`,
`run_type_recommendation: positional` (strong), `price_per_run: ₹20`. Eleven checks ran, including `keyword_surface`, `data_coverage`, `underlying_data_coverage` and `coverage_window`. Caveats on what
this proves: I passed the compiled payload with the `*_json` and `*_display` members stripped, keeping `condition_value`, strike, expiry and variables; the check scans expressions, so I expect no
difference, but that is an inference. The check confirms `Delta` and `Find Strike` exist in the engine's keyword namespace. It does **not** say the backtest data store holds historical Greeks, so the
"does the engine have historical Greeks" unknown from `prompt.md` is still open and only the funded run (TCP-5) can answer it.

**Rules encoded.**

| Live rule (TCP-1) | In the template | Note |
|---|---|---|
| Delta target 0.15 | `Find Strike(..., 'delta', 0.15, 'CE', 'any')` in the leg's Strike cell | Mode `any` has no distance cap; the 0.12-0.18 band is **GAP**, not expressible |
| Profit target, mark <= 30% of credit, credit >= 15 | Exit group (AND): LTP <= 0.30 x entry price AND entry price >= 15 | Encoded. Entry price from `Traded Instrument('Entry','price',...)` |
| Loss stop, mark >= 2.5x credit | Exit: LTP >= 2.5 x entry price | Encoded |
| Delta stop >= 0.55 | Exit: `Delta(Traded Instrument Name(...)) >= 0.55` | Encoded; call delta is positive. Delta is Tradetron's own, not Upstox's |
| DTE <= 5 close | Exit: `Days Difference(Today('NSE'), traded leg expiry) <= 5` | Encoded. Calendar days, not trading days |
| 21-day time stop | Not encoded | Removed from the code by EC-5; the story spec line is stale (see TCP-1) |
| Delta WARN at 0.45, BELOW_FLOOR INFO | Not encoded | Both are informational in the code, no close |

**Entry rules are the archived spec, not the live code.** The template gates on Wednesday (`Week Day(NSE) == 3`) and DTE 30 to 45, as the story specifies. TCP-1 found live code has no weekday check
and only a 14-DTE floor, and paper cycles 3 (DTE 20) and 5 (Friday) fall outside the gate. They cannot be reproduced by this template; a mismatch there is a spec difference. The 10:00 entry time is my
assumption, since the paper entry time is not in the findings.

**Gaps and unknowns.**

- **Re-entry: GAP.** The `entered` one-shot guard never resets, so a positional run takes one cycle. Paper had five cycles over two expiries, with re-entry 0 to 7 days after each exit. A fair
  reconciliation needs the guard reset on exit or a flat-position gate instead; decide in TCP-4 before the template is created.
- **Exit priority.** All four exits are OR-joined in one Universal Exit, so the engine takes whichever it sees first. How the paper engine orders simultaneous signals (`_sort_results`) was not read.
- **Find Strike leg-drop hazard** applies (returns None, the leg is skipped). With a single leg that means no entry, which the prompt accepts. The exits read a missing leg through Traded Instrument
  and evaluate False when nothing is open.
- **Naked short.** The call is sold at Entry with no NiftyBees cover. A backtest does not model margin; the NiftyBees leg is out of scope.
- **Entry fill.** `Market Price` with the engine default fill `Open`; the `Close` sensitivity run is TCP-5.
- **Backtest evaluates bar open and close only**, so a mid-minute stop crossing can be missed (about 1 in 10 within a week of expiry, per the authoring reference, measured 2026-09-04). The DTE <= 5
  phase is the exposed one.

**Decision: GO.** The template validates and the pre-flight says backtestable with high confidence, so TCP-4 and TCP-5 proceed. The gaps above are known and listed (band, re-entry, exit priority,
21-day stop, entry-rule difference). GO means the run will execute, not that the delta-based strike will be reproducible: if the backtest store has no historical Greeks, `Find Strike` on delta can
fail or return nothing at run time, and that would be reported at TCP-5 as the platform result.

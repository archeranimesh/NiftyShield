
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

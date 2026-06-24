# IC-M3 — Weekly expiry bucket in `get_expiry_candidates()`

> **Assigned to: Claude** — additive change to existing function; no existing behaviour changes.

**Prerequisite:** None — independent of IC-M1 and IC-M2; can run in parallel.

**Files to change:**
- `src/instruments/lookup.py` — add `"weekly"` bucket to `get_expiry_candidates()`
- `tests/unit/instruments/test_expiry_candidates.py` — add weekly bucket tests

---

## Context

`get_expiry_candidates()` currently supports three DTE bands:
- `monthly`: DTE 15–45, last expiry of the calendar month
- `quarterly`: DTE 46–200, last expiry of Mar/Jun/Sep/Dec months
- `yearly`: DTE 201–420, last expiry of Jun/Dec months

Nifty weekly expiry moved from Thursday to Tuesday effective April 2026 (SEBI/NSE circular).
Weekly expiries are **not** the last expiry of a calendar month (that is the monthly), so
they are currently filtered out by the `is_monthly` guard.

A `"weekly"` bucket needs to resolve the nearest Tuesday expiry with DTE ≤ 14. This is
the entry target for weekly IC paper trades.

---

## What to implement

### `src/instruments/lookup.py` — `get_expiry_candidates()`

**Add weekly bucket logic** inside the expiry classification block, before the existing
`if 15 <= dte <= 45` check:

```python
# Weekly: nearest expiry on a Tuesday with DTE ≤ 14
# Nifty weekly moved from Thursday → Tuesday (NSE, April 2026)
is_tuesday = d.weekday() == 1  # 0=Mon … 6=Sun
if dte <= 14 and is_tuesday and "weekly" not in mapping:
    mapping["weekly"] = exp
```

**Update the `preference` default** to include `"weekly"` as a valid value (docstring only —
callers still pass their own preference list; the default remains `["monthly", "quarterly", "yearly"]`
since weekly is opt-in for IC entry):

```
DTE bands:
  weekly:    DTE ≤ 14, nearest Tuesday expiry (Nifty weekly, post-April 2026)
  monthly:   DTE 15–45, last expiry of the calendar month
  quarterly: DTE 46–200, last expiry of Mar/Jun/Sep/Dec
  yearly:    DTE 201–420, last expiry of Jun/Dec
```

**No change to function signature** — `preference` already accepts any list of strings.
Callers that want weekly pass `preference=["weekly"]`.

---

## Tests (`tests/unit/instruments/test_expiry_candidates.py`)

Use the existing test fixture pattern (build a minimal synthetic instruments list in memory —
no file I/O). Existing tests must all still pass.

**New happy-path tests:**

1. `test_weekly_bucket_nearest_tuesday` — instruments include two Tuesday expiries at DTE 7
   and DTE 12, plus one Thursday at DTE 5 (legacy format, should be ignored). Assert
   `get_expiry_candidates("NIFTY", today, ["weekly"])` returns the DTE-7 Tuesday
   (nearest = smallest DTE that is still a Tuesday and ≤ 14).

2. `test_weekly_not_in_default_preference` — call with default preference (no arg).
   Assert `"weekly"` is NOT in the returned labels (weekly is opt-in).

3. `test_weekly_and_monthly_independent` — instruments contain both a Tuesday at DTE 10
   and a last-of-month at DTE 30. Call with `preference=["weekly", "monthly"]`.
   Assert both labels appear in the result, each with the correct date.

**Edge/error tests:**

4. `test_weekly_no_tuesday_within_14` — all near-term expiries are Thursdays (DTE ≤ 14)
   or Tuesdays at DTE > 14. Assert `get_expiry_candidates("NIFTY", today, ["weekly"])`
   returns an empty list (no `"weekly"` entry).

5. `test_weekly_boundary_dte_14` — Tuesday expiry at exactly DTE 14. Assert it IS
   included (boundary is inclusive: `dte <= 14`).

6. `test_weekly_boundary_dte_15` — Tuesday expiry at exactly DTE 15. Assert it is NOT
   included in the weekly bucket (DTE > 14). It may appear as monthly if it is
   also the last-of-month — assert it does not appear under `"weekly"`.

---

## Commit

```
feat(instruments): add weekly expiry bucket to get_expiry_candidates()

Why: IC multi-expiry paper research requires weekly Nifty entry; post-April-2026
NSE weekly expiry is Tuesday not Thursday.
What:
- src/instruments/lookup.py: weekly DTE≤14 Tuesday bucket; docstring updated
- tests/unit/instruments/test_expiry_candidates.py: 6 new weekly bucket tests
Ref: ic-multi-expiry IC-M3
```

---

## Pre-baked Context

**`get_expiry_candidates` location:** `src/instruments/lookup.py`, method on `InstrumentLookup`
class. The classification block (where labels are assigned) starts after the
`parsed_expiries` / `last_of_month` setup and iterates `sorted(seen)`.

**Current classification block** (exact lines to read before editing):
```python
label = None
if 15 <= dte <= 45 and is_monthly:
    label = "monthly"
elif 46 <= dte <= 200 and is_quarterly:
    label = "quarterly"
elif 201 <= dte <= 420 and is_yearly:
    label = "yearly"

if label and label not in mapping:
    mapping[label] = exp
```

Insert the `"weekly"` check **before** this block (not inside the elif chain) so that a
Tuesday at DTE 10 is captured as `"weekly"` without interfering with the `"monthly"` check
(a Tuesday at DTE 10 would not qualify as monthly anyway since it is not the last-of-month,
but the guard is cleaner as a pre-check).

**`d.weekday()` return values:** Mon=0, Tue=1, Wed=2, Thu=3, Fri=4, Sat=5, Sun=6.
Nifty weekly expiry is Tuesday → `d.weekday() == 1`.

**Existing test file:** `tests/unit/instruments/test_expiry_candidates.py` — 6 existing
tests covering monthly/quarterly/yearly buckets and the preference ordering. All must
remain green. Do not modify existing tests.

# IC-F4 — Weekly Tuesday expiry bucket in `get_expiry_candidates()`

> **Assigned to: Claude** — additive; no existing behaviour changes.

**Prerequisite:** None — independent.

**Files to change:**
- `src/instruments/lookup.py` — add `"weekly"` bucket
- `tests/unit/instruments/test_expiry_candidates.py` — 6 new tests

---

## Context

`get_expiry_candidates()` supports monthly / quarterly / yearly bands. Nifty weekly
expiry moved from Thursday to Tuesday effective April 2026 (SEBI/NSE). Weekly ICs
enter on Wednesday (DTE ≈ 6) targeting the next Tuesday. The `"weekly"` bucket must
resolve to the nearest Tuesday with DTE ≤ 14.

---

## What to implement

### `src/instruments/lookup.py` — inside `get_expiry_candidates()`

Add **before** the existing `label = None` classification block:

```python
# Weekly: nearest Tuesday expiry with DTE ≤ 14
# Nifty weekly expiry is Tuesday post April 2026 (NSE/SEBI change)
is_tuesday = d.weekday() == 1  # Mon=0 … Sun=6
if dte <= 14 and is_tuesday and "weekly" not in mapping:
    mapping["weekly"] = exp
    continue  # do not also classify this date as monthly
```

The `continue` prevents a Tuesday that also happens to be last-of-month from being
double-classified. (In practice this overlap is rare but possible.)

**Update docstring DTE bands section:**
```
DTE bands:
  weekly:    DTE ≤ 14, nearest Tuesday (Nifty weekly post-April 2026)
  monthly:   DTE 15–45, last expiry of the calendar month
  quarterly: DTE 46–200, last expiry of Mar/Jun/Sep/Dec
  yearly:    DTE 201–420, last expiry of Jun/Dec

Default preference order: ["monthly", "quarterly", "yearly"] — weekly is opt-in.
Pass preference=["weekly"] for IC weekly entry.
```

---

## Tests (`tests/unit/instruments/test_expiry_candidates.py`)

Build synthetic instrument lists in memory — no file I/O. Follow existing fixture pattern.

1. `test_weekly_nearest_tuesday` — two Tuesdays at DTE 7 and DTE 12; one Thursday at DTE 5.
   `preference=["weekly"]` → returns DTE-7 Tuesday only.

2. `test_weekly_not_in_default_preference` — call with no preference arg.
   Assert `"weekly"` not in returned labels.

3. `test_weekly_and_monthly_coexist` — Tuesday at DTE 10 + last-of-month at DTE 32.
   `preference=["weekly", "monthly"]` → both returned with correct dates.

4. `test_weekly_no_tuesday_in_window` — only Thursdays at DTE ≤ 14.
   `preference=["weekly"]` → empty list.

5. `test_weekly_boundary_inclusive_14` — Tuesday at DTE 14 → included.

6. `test_weekly_boundary_exclusive_15` — Tuesday at DTE 15 → not in weekly bucket.

---

## Commit

```
feat(instruments): add weekly Tuesday expiry bucket to get_expiry_candidates

Why: IC weekly paper research requires DTE≤14 Tuesday expiry resolution;
post-April-2026 NSE weekly is Tuesday not Thursday.
What:
- src/instruments/lookup.py: weekly bucket with Tuesday guard; docstring updated
- tests/unit/instruments/test_expiry_candidates.py: 6 new tests
Ref: ic-full IC-F4
```

---

## Pre-baked Context

**Classification block in `get_expiry_candidates`** — insert before `label = None`:
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

Insert the weekly block **before** `label = None`. Use `continue` after setting
`mapping["weekly"]` to skip the label block entirely for that date.

**`d.weekday()`:** Mon=0, Tue=1, Wed=2, Thu=3, Fri=4.

**Existing tests:** `tests/unit/instruments/test_expiry_candidates.py` — 6 tests covering
monthly/quarterly/yearly. All must remain green. Do not modify them.

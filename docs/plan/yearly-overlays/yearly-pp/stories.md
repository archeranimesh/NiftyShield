# Yearly PP — story specs

> One task per session. Find the first unchecked item in `tasks.md`. That is your only task. Full implementation rules in `CLAUDE.md` and `REVIEW.md`. After each task: set `SHA:` + tick the box,
> update story status, add one line to `TODOS.md`.

---

## YP-1 — Flag and bootstrap

**Files to change / create:**
- `scripts/strategies/three_track/paper_3track_overlay_entry.py` — `--expiry-type` on `--auto-pp`; policy passed to `auto_pp_bootstrap`.
- `tests/unit/scripts/test_overlay_entry_yearly_pp.py`.

**Before any code:** `get_code_snippet("auto_pp_bootstrap")`, `get_code_snippet("_open_pp_dte")`, `search_graph("OVERLAY_TENORS")`.

**What to implement:**

1. Flag plumbing as in `yearly-cc/` YC-1; the "no open put -> bootstrap, open put with DTE <= threshold -> gap-fill roll, otherwise no-op" contract is evaluated per namespace.
2. `_open_pp_dte` takes the namespace so it measures the yearly put, not the monthly one.

**Tests:**
- `test_yearly_pp_bootstrap_opens_december_put`, `test_monthly_put_open_does_not_noop_yearly_bootstrap`, `test_yearly_put_open_does_not_noop_monthly_bootstrap`.

**Commit:** `feat(overlay): add yearly expiry-type to auto-pp`

---

## YP-2 — Yearly roll and re-entry

**Files to change / create:**
- `scripts/strategies/three_track/paper_3track_overlay_entry.py` — `_PP_ROLL_DTE_THRESHOLD` replaced by `policy.roll_dte`.
- `src/strategy/pp_overlay_v1.py` — ROLL_ELIGIBLE and crash-monetize re-entry gates (currently DTE <= 5 and >= 14) read the policy.
- `tests/unit/strategy/test_pp_overlay_yearly.py`.

**Before any code:** `get_code_snippet("PPOverlayV1")`, `get_code_snippet("evaluate_pp")` equivalent, `roll_utils` for the roll target expiry. Roll target for yearly must be the next yearly expiry
(Dec 2026 -> Dec 2027), resolved by `resolve_overlay_expiry` with the roll date as `today`.

**What to implement:**

1. Replace the two constants with policy fields; class default remains monthly.
2. Roll lands on the next yearly expiry using the injectable clock.

**Tests:**
- `test_yearly_roll_from_dec2026_targets_dec2027` — frozen date inside the window.
- `test_monthly_roll_threshold_unchanged` — pinned at 5.
- `test_roll_outside_window_noops`.

**Commit:** `feat(overlay): drive PP roll window from tenor policy`

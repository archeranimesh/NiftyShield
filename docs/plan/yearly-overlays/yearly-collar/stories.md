# Yearly Collar — story specs

> One task per session. Find the first unchecked item in `tasks.md`. That is your only task. Full implementation rules in `CLAUDE.md` and `REVIEW.md`. After each task: set `SHA:` + tick the box,
> update story status, add one line to `TODOS.md`.

---

## YL-1 — Flag, bootstrap, pair validation

**Files to change / create:**
- `scripts/strategies/three_track/paper_3track_overlay_entry.py` — flag; `auto_collar_bootstrap(policy, today)`; `_validate_collar_pairs(..., expected_expiry)`.
- `tests/unit/scripts/test_overlay_entry_yearly_collar.py`.

**Before any code:** `get_code_snippet("auto_collar_bootstrap")`, `get_code_snippet("_validate_collar_pairs")`, `get_code_snippet("OverlayConfig")`.

**What to implement:**

1. Resolve the expiry once via `resolve_overlay_expiry`, then pick both strikes from that single expiry's chain.
2. Pair validation compares each leg's expiry to the resolved one; failure aborts structurally.

**Tests:**
- `test_yearly_collar_pair_on_same_december_expiry`, `test_pair_with_different_expiries_rejected`, `test_monthly_collar_unchanged`.

**Commit:** `feat(overlay): add yearly expiry-type to auto-collar`

---

## YL-2 — Yearly collar behaviour

**Files to change / create:**
- `src/strategy/collar_overlay_v1.py` — DTE_REVIEW (currently <= 5) and re-entry gate read the policy.
- `src/strategy/collar_entry.py` — `_resolve_expiry` and `_check_gates` read the policy (added 2026-11-04, see below).
- `tests/unit/strategy/test_collar_overlay_yearly.py`.

More than 2 files: list them in the go-ahead.

**Before any code:** `get_code_snippet("CollarOverlayV1")`; `get_code_snippet("select_and_build_collar_entry")`, `get_code_snippet("_resolve_expiry")`, `get_code_snippet("_check_gates")`;
`src/paper/CLAUDE.md` for exit-event invariants.

**What to implement:** same pattern as `yearly-cc/` YC-2 for the collar's tenor constants; no new branch.

**Reselection must stay in the yearly tenor (added 2026-11-04).** `select_and_build_collar_entry` is called only from `CollarOverlayV1` reselection. `_resolve_expiry` hardcodes
`preference=["monthly"]` and `_check_gates` hardcodes a DTE >= 14 floor, so a yearly collar reviewed at 15 DTE would be re-entered on the next monthly expiry. Pass the tenor policy into
`select_and_build_collar_entry`; resolve the expiry via `resolve_overlay_expiry`; take the DTE floor from `policy` (yearly entry floor 20 DTE; monthly stays 14). With no policy given, behaviour is
byte-identical to today. The IVR gate: keep as is, and report in the task output whether it should differ for yearly rather than guessing.

**Tests:**
- `test_yearly_collar_review_uses_policy_dte`, `test_monthly_collar_golden_signals_unchanged`.
- `test_yearly_collar_reselect_resolves_december`, `test_yearly_collar_reselect_dte_floor_from_policy`, `test_monthly_collar_reselect_unchanged`.

**Commit:** `feat(overlay): drive collar DTE gates from tenor policy`

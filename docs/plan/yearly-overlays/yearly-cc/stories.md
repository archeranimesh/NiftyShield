# Yearly CC — story specs

> One task per session. Find the first unchecked item in `tasks.md`. That is your only task. Full implementation rules in `CLAUDE.md` and `REVIEW.md`. After each task: set `SHA:` + tick the box,
> update story status, add one line to `TODOS.md`.

---

## YC-1 — Flag and bootstrap

**Files to change / create:**
- `scripts/strategies/three_track/paper_3track_overlay_entry.py` — `--expiry-type` argument (choices `monthly`, `yearly`, default `monthly`); pass the registry policy into `auto_cc_bootstrap`.
- `tests/unit/scripts/test_overlay_entry_yearly_cc.py`.

**Before any code:** `get_code_snippet("auto_cc_bootstrap")`, `get_code_snippet("OverlayConfig")`, `search_graph("OVERLAY_TENORS")` (from YF-3).

**What to implement:**

1. Add the flag; reject `--expiry-type yearly` combined with `--auto-pp`/`--auto-collar` until those stories land, with a clear message.
2. The recorded trades use `policy.strategy_name`; `_has_open_overlay_leg` is called with it (YF-5).
3. Telegram/entry message names the book ("Yearly CC") via the existing label table.

**Tests:**
- `test_yearly_flag_opens_december_call_under_yearly_namespace` — fixture BOD + chain, frozen 2026-10-06.
- `test_monthly_default_records_under_monthly_namespace` — unchanged behaviour.
- `test_yearly_with_pp_flag_rejected` — non-zero exit, message names the story.

**Commit:** `feat(overlay): add yearly expiry-type to auto-cc`

---

## YC-2 — Yearly CC behaviour

**Files to change / create:**
- `src/strategy/cc_overlay_v1.py` — hardcoded DTE gates (review at <= 5, re-entry >= 14) read from the policy field instead.
- `tests/unit/strategy/test_cc_overlay_yearly.py`.

**Before any code:** `get_code_snippet("CCOverlayV1")`; `trace_path("evaluate_cc")`-equivalent from the audit; `src/paper/CLAUDE.md` for `paper_exit_events` invariants.

**What to implement:**

1. Replace each tenor-bearing constant with `self.tenor.<field>`; the class default stays the monthly policy so existing construction sites do not change.
2. Yearly instance gets the yearly policy and namespace via constructor injection.

**Tests:**
- `test_yearly_cc_review_dte_uses_policy` — a leg at DTE 20 is not reviewed under a yearly review_dte of 5 but is under a test policy of 30.
- `test_monthly_cc_unchanged_by_policy_injection` — golden signals for a fixed leg.

**Commit:** `feat(overlay): drive CC DTE gates from tenor policy`

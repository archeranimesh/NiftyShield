# Yearly Foundation — story specs

> One task per session. Find the first unchecked item in `tasks.md`. That is your only task. Full implementation rules in `CLAUDE.md` and `REVIEW.md`. After each task: set `SHA:` on the task line +
> tick the box, update the story status summary, add one line to `TODOS.md`. See `docs/plan/README.md` §Conventions.

---

## YF-1 — Overlay hardcode audit

**Files to change / create:**
- `docs/plan/yearly-overlays/yearly-foundation/audit.md` — table: site (file:line), what is hardcoded, what must change, owning story. No checkboxes (extra reference file).

**Before any code (graph queries):**
- `search_code("STRATEGY_OVERLAY")`, `search_code("preference=\\[\"monthly\"\\]")`, `search_code("date.today()")` scoped to overlay files, `search_code("_PP_ROLL_DTE_THRESHOLD")`.
- `trace_path("_has_open_overlay_leg")`, `trace_path("get_expiry_candidates")` callers for the overlay path.
- Read `docs/refactor/code-deduplication-and-taxonomy.md` and note any existing resolver helper before proposing a new one.

**What to implement:**

1. Enumerate every site; classify as tenor, clock, namespace or label.
2. Confirm whether `paper_overlay_pnl_snapshots`, `paper_exit_events` or `paper_strategies` need any schema change for a second namespace (expected: none). State the evidence.
3. Mark which sites belong to which later story; flag anything outside the epic's file budget.

**Tests:** none (docs-only).

**Commit:** `docs(plan): audit overlay hardcodes for yearly book`

---

## YF-2 — Fixtures and frozen clock

**Files to change / create:**
- `tests/fixtures/yearly_overlays/bod_dec2026_dec2027.json` — minimal BOD instrument set containing NIFTY monthly expiries through Dec 2027 (Dec 2026 = 2026-12-29, Dec 2027 = 2027-12-28).
- `tests/fixtures/yearly_overlays/chain_dec2026_greeks.json`, `chain_dec2027_zero_greeks.json` — one populated chain, one with every delta zero (the real far-expiry failure mode).
- `tests/unit/conftest.py` or a helper module — a `frozen_today(date)` fixture/helper, matching how existing tests freeze time.

**Before any code:**
- `get_code_snippet("OptionChain")`, `get_code_snippet("OptionLeg")` — exact fields. `search_graph("InstrumentLookup")`. Look at existing `tests/fixtures/` and how clock is frozen today.

**What to implement:**

1. Build fixtures from recorded shapes, not memory; keep each under a few hundred lines.
2. One clock helper only; reuse an existing one if present (YF-1 audit notes).

**Tests (`tests/unit/`):**
- `test_fixture_bod_resolves_yearly_dec2026` — lookup on the fixture, today 2026-10-06, yearly bucket gives 2026-12-29.
- `test_zero_greeks_fixture_parses_all_deltas_zero` — parser output has every delta zero.

**Commit:** `test(overlay): add yearly BOD and chain fixtures`

---

## YF-3 — OverlayTenorPolicy registry

**Files to change / create:**
- `src/strategy/overlay_tenor.py` — frozen dataclass `OverlayTenorPolicy(expiry_type, expiry_bucket, strategy_name, entry_min_dte, review_dte, reentry_min_dte, roll_dte)` and `OVERLAY_TENORS:
  dict[str, OverlayTenorPolicy]`.
- `src/paper/constants.py` — add `STRATEGY_OVERLAY_YEARLY = "paper_nifty_overlay_yearly"`.
- `tests/unit/strategy/test_overlay_tenor.py`.

**Before any code:**
- Read the YF-1 audit for the exact monthly values (expected 14 / 5 / 14 / 5). Use `ExpiryType` vocabulary from `ic_expiry_config.py`; do not invent a second Literal.

**What to implement:**

1. `monthly` entry: bucket `monthly`, `strategy_name=STRATEGY_OVERLAY`, values equal to the current hardcoded ones.
2. `yearly` entry: bucket `yearly`, `strategy_name=STRATEGY_OVERLAY_YEARLY`, values per README open decision 1.
3. No consumer is changed in this task.

**Tests:**
- `test_monthly_policy_pins_current_values` — every field equals today's hardcoded value.
- `test_unknown_expiry_type_raises_keyerror` — registry lookup fails loudly.

**Commit:** `feat(overlay): add tenor policy registry`

---

## YF-4 — Clock-injectable expiry resolver

**Files to change / create:**
- `src/strategy/overlay_tenor.py` or `src/instruments/` (per the YF-1 audit) — `resolve_overlay_expiry(lookup, today, policy) -> str | None`.
- `scripts/strategies/three_track/paper_3track_overlay_entry.py` — `auto_cc_bootstrap`, `auto_pp_bootstrap`, `auto_collar_bootstrap` gain keyword-only `today: date | None = None` and `policy`; default
  behaviour unchanged.
- `tests/unit/strategy/test_overlay_expiry_resolution.py`.

**Before any code:**
- `get_code_snippet("auto_cc_bootstrap")` and the PP/Collar equivalents; `trace_path("get_expiry_candidates")`.

**What to implement:**

1. Replace the three repeated "get candidates, find label" blocks with one call; DTE gate uses `policy.entry_min_dte`.
2. `today=None` falls back to `date.today()` so cron callers are untouched.

**Tests:**
- `test_yearly_resolves_dec2026_on_2026_10_06`, `test_yearly_resolves_dec2027_on_2026_12_30` — from the YF-2 fixture and frozen clock.
- `test_monthly_default_unchanged` — golden result for a fixed date equals the pre-change value.
- `test_no_candidate_returns_none_and_aborts` — bootstrap aborts structurally, not via gate.

**Commit:** `refactor(overlay): inject clock and tenor into bootstraps`

---

## YF-5 — Namespace read-paths

**Files to change / create:** the consumers listed by YF-1, expected: `src/strategy/reentry_mixin.py`, `src/risk/collateral_gate.py`, `src/strategy/auto_close.py`, `src/portfolio/overlay_coverage.py`,
`src/reporting/eod_pt_summary.py`, `src/paper/track_snapshot.py`, `_has_open_overlay_leg` in `paper_3track_overlay_entry.py`. More than 2 files: name them before editing.

**Before any code:**
- `get_code_snippet` for each consumer; for `src/paper/` edits load `src/paper/CLAUDE.md`. Re-read README open decision 2 (collateral pooling) and apply the confirmed default.

**What to implement:**

1. Each consumer iterates the policy registry's strategy names instead of the single `STRATEGY_OVERLAY` constant.
2. `_has_open_overlay_leg` takes the strategy name so a monthly leg never satisfies a yearly check and the reverse.

**Tests:**
- `test_monthly_leg_does_not_block_yearly_entry`, `test_yearly_leg_does_not_block_monthly_entry`.
- `test_collateral_gate_counts_yearly_namespace`, `test_coverage_reports_each_namespace_separately`.

**Commit:** `feat(overlay): recognise yearly namespace in read paths`

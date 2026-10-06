# Yearly Validation — story specs

> One task per session. Find the first unchecked item in `tasks.md`. That is your only task. Full implementation rules in `CLAUDE.md` and `REVIEW.md`. After each task: set `SHA:` + tick the box,
> update story status, add one line to `TODOS.md`.

---

## YV-1 — Independence tests

**Files to change / create:** `tests/unit/strategy/test_overlay_book_independence.py`.

**Before any code:** `get_code_snippet("PaperStore")` constructors and `PaperTrade` fields; `search_graph("TradeState")` members — do not write helpers from memory.

**What to implement:** seed one book via the store, act on the other, assert on positions, `paper_exit_events`, `collateral_gate`, `overlay_coverage`, and `paper_overlay_pnl_snapshots` keys.

**Tests:** `test_monthly_open_does_not_block_yearly_entry`, `test_yearly_open_does_not_block_monthly_entry`, `test_exit_event_in_one_book_not_visible_in_other`,
`test_collateral_pool_counts_both_books_per_decision`.

**Commit:** `test(overlay): prove monthly and yearly books are independent`

---

## YV-2 — End-to-end dry run

**Files to change / create:** `tests/integration/test_yearly_overlay_dry_run.py` (offline; no marker needed).

**Before any code:** `get_code_snippet("MockBrokerClient")`; how existing entry tests call `main()` with patched argv.

**What to implement:** call each entrypoint's `main()` with `--expiry-type yearly --dry-run`, injected mock client and temp DB path, frozen clock.

**Tests:** `test_yearly_cc_dry_run_selects_december`, `test_yearly_pp_dry_run_selects_december`, `test_yearly_collar_dry_run_pair_same_expiry`, `test_zero_greeks_chain_opens_no_leg`,
`test_dry_run_writes_nothing`.

**Commit:** `test(overlay): add yearly entry dry-run tests`

---

## YV-3 — Opt-in live smoke

**Files to change / create:** `tests/live/test_yearly_overlay_live_smoke.py` marked `live` (skipped by default; confirm the marker exists in `pyproject.toml`, add it only if missing).

**What to implement:** read-only chain fetch for the nearest December, run the yearly resolver and selector with `--dry-run`, assert no DB write; append the printed selection to the story's
`findings.md`.

**Tests:** `test_live_dry_run_resolves_december_and_writes_nothing`.

**Commit:** `test(overlay): add opt-in live yearly smoke test`

---

## YV-4 — IC coexistence check

**Files to change / create:** `tests/unit/strategy/test_ic_expiry_coexistence.py`.

**Before any code:** `get_code_snippet("CONFIGS")` / `ICExpiryConfig`; `get_code_snippet("get_expiry_candidates")`; daemon loops over `IC_CONFIGS` and `paper_ic_snapshot.py` lines 649-700 via `sed
-n`.

**What to implement:** assert unique `strategy_name` per config; resolve `leaps` and `yearly` for 2026-10-06, 2026-12-30, 2027-03-31 and record which dates they share a December expiry (intended);
assert the daemon and snapshot loops reach all four types.

**Tests:** `test_ic_strategy_names_unique`, `test_leaps_is_quarterly_and_yearly_is_december`, `test_shared_december_expiry_allowed_but_distinct_books`.

**Commit:** `test(ic): verify weekly monthly leaps yearly coexist`

---

## YV-5 — Paper-run and roll runbook (Animesh)

**Files to change / create:** `docs/plan/yearly-overlays/yearly-validation/findings.md` (reference file, no checkboxes).

**What to write:** entry date and strikes for the first yearly CC/PP/Collar in paper; weekly review cadence; and the roll go/no-go list: Dhan chain adapter live, at least N captured days, liquidity
gate calibrated, Dec 2027 target-delta strikes pass the gate, `roll_dte` set.

**Tests:** none.

**Commit:** `docs(plan): record yearly overlay paper run and roll gate`

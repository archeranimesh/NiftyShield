# Far-Expiry Liquidity Gate — story specs

> One task per session. Find the first unchecked item in `tasks.md`. That is your only task. Full implementation rules in `CLAUDE.md` and `REVIEW.md`. After each task: set `SHA:` + tick the box,
> update story status, add one line to `TODOS.md`.

---

## FG-1 — Calibration findings

**Files:** `docs/plan/dhan-far-expiry-chain/far-expiry-liquidity-gate/findings.md` (reference file, no checkboxes).

**Before any code:** run the FC-5 report over the captured window; read `DB_REGISTRY.md` note on `gate_violations` to keep the gate log-only compatible.

**What to write:** per expiry type, the proposed spread cap, OI floor and quote rule, the window and day count used, the fraction of days each target-delta strike would have passed, and the fallback
order. State what the data cannot say (short window, one snapshot per day). Animesh signs off before FG-2 starts.

**Tests:** none. **Commit:** `docs(plan): record far-expiry liquidity gate calibration`

---

## FG-2 — Extend the gate

**Files to change / create:** `src/instruments/strike_selector.py`, a gate config location named in FG-1, `tests/unit/instruments/test_liquidity_gate.py`. More than 2 files: name them before editing.

**Before any code:** `get_code_snippet("_apply_liquidity_gate")`; `trace_path("_apply_liquidity_gate")` for every caller; the strike dict fields (`bid`, `ask`, `mid`, `oi`).

**What to implement:**

1. Optional parameters for OI floor and require-two-sided-quote; defaults reproduce today's behaviour exactly.
2. An ordered fallback ladder as data: same expiry next strike inward, then the next candidate expiry; return which step passed and why earlier steps failed (for the `gate_violations` log).
3. Failure reasons are distinct values, not a bare empty list.

**Tests:** `test_defaults_match_previous_behaviour` (golden), `test_oi_floor_blocks_thin_strike`, `test_one_sided_quote_blocks`, `test_ladder_falls_to_next_strike`, `test_ladder_falls_to_next_expiry`,
`test_all_steps_fail_returns_reasons`.

**Commit:** `feat(strike): add OI floor and fallback ladder to liquidity gate`

---

## FG-3 — Roll-window decision

**Files to change / create:** the yearly entry in `src/strategy/overlay_tenor.py` (`roll_dte`), `DECISIONS.md`, `docs/plan/dhan-far-expiry-chain/far-expiry-liquidity-gate/findings.md`.

**Before any code:** the YF-3 registry; the capture history for the next December; `roll_utils` for how roll dates are used.

**What to implement:** compute, from captured days, the first DTE at which the next December's target-delta strikes pass the FG-2 gate and stay passing; set `roll_dte` with a margin and record the
numbers. If the data shows the next December never becomes tradable in time, record that and the bridge-expiry (Mar/Jun) fallback instead of forcing a value.

**Tests:** `test_policy_roll_dte_value_pinned` — the registry value equals the decision recorded.

**Commit:** `feat(overlay): set yearly roll window from captured liquidity`

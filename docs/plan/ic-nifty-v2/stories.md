# Iron Condor V2 — Story Specs

> One task per session. Find the first unchecked item in `tasks.md`. That is your only task.
> Full council ruling: `docs/archive/council/strategy/2026-06-26_ic-v2-core-design.md` Stage 3 (authoritative).
> After each task: tick `tasks.md`, append `| SHA: <sha>`, add one line to `TODOS.md`.

---

## IC-V2-0 — Config Dataclass

**Goal:** New config dataclass `IronCondorV2ExpiryConfig` replacing `wing_width_points: int` with delta-based wing fields. Both weekly and monthly presets.

**Files to change:**
- `src/strategy/ic_expiry_config_v2.py` — new file (new module)
- `tests/unit/strategy/test_ic_expiry_config_v2.py` — new test file

**Before any code:**
```
search_graph("IronCondorExpiryConfig")    # get V1 field list exactly
search_graph("IronCondorV2ExpiryConfig")  # confirm does NOT exist
get_code_snippet("IronCondorExpiryConfig")  # exact V1 definition
```

**What to implement:**

```python
@dataclass(frozen=True)
class IronCondorV2ExpiryConfig:
    """Delta-based config for IronCondorV2.

    Replaces V1's fixed wing_width_points with 10Δ long-wing placement.
    Council ruling: docs/archive/council/strategy/2026-06-26_ic-v2-core-design.md Stage 3.
    """
    expiry_type: str                              # "weekly" | "monthly"

    # Entry — short leg deltas (D1 ruling)
    short_put_delta_target: Decimal = Decimal("0.25")
    short_call_delta_target: Decimal = Decimal("0.22")
    delta_range: Decimal = Decimal("0.03")        # ±tolerance for strike selection

    # Wing sizing — long leg deltas (D2 ruling)
    long_wing_delta_target: Decimal = Decimal("0.10")
    long_wing_delta_floor: Decimal = Decimal("0.05")   # absolute minimum; skip entry if not met
    long_wing_min_premium: Decimal = Decimal("15")     # ₹ per unit; ₹10 for weekly

    # SD sanity guard (D2) — warn thresholds, not hard blocks
    sd_width_warn_upper_multiplier: Decimal = Decimal("1.5")
    sd_width_warn_lower_multiplier: Decimal = Decimal("0.4")
    sd_atm_iv_multiplier: Decimal = Decimal("1.25")    # k in sd_width formula

    # Adjustment (D3)
    roll_trigger_delta: Decimal = Decimal("0.35")      # |short_delta| ≥ this → ROLL_WING
    roll_warn_delta: Decimal = Decimal("0.30")         # |short_delta| ≥ this → DELTA_WARN
    forced_close_delta: Decimal = Decimal("0.45")      # |short_delta| ≥ this → FORCED_CLOSE
    roll_debit_cap_fraction: Decimal = Decimal("0.50") # roll debit ≤ 50% of original IC credit
    max_rolls_per_side_per_cycle: int = 1

    # DTE-tiered exit for weekly (D4)
    weekly_close_full_dte: int = 3     # DTE≤3 → CLOSE_FULL
    weekly_strict_guard_dte: int = 5   # DTE 4–5 → roll with strict debit+liquidity guard
    weekly_hard_close_dte: int = 1     # DTE≤1 → CLOSE_FULL, no discretion

    # DTE-tiered exit for monthly (D4)
    monthly_close_full_dte: int = 7    # DTE≤7 → CLOSE_FULL default (refineable during backtest)


# Canonical presets
IC_V2_WEEKLY = IronCondorV2ExpiryConfig(
    expiry_type="weekly",
    long_wing_min_premium=Decimal("10"),   # ₹10 floor for weekly (D2 ruling)
)

IC_V2_MONTHLY = IronCondorV2ExpiryConfig(
    expiry_type="monthly",
    long_wing_min_premium=Decimal("15"),   # ₹15 floor for monthly (D2 ruling)
)
```

**Tests (test_ic_expiry_config_v2.py):**
- `test_weekly_preset_defaults` — verify IC_V2_WEEKLY fields match D1/D2 rulings
- `test_monthly_preset_defaults` — verify IC_V2_MONTHLY fields, especially long_wing_min_premium=15
- `test_immutability` — frozen=True; assignment raises FrozenInstanceError
- `test_delta_range_positive` — delta_range > 0 on both presets
- `test_max_rolls_is_one` — max_rolls_per_side_per_cycle == 1 on both presets
- `test_weekly_close_full_dte_lte_strict_guard` — close_full_dte < strict_guard_dte (invariant)

**Commit:** `feat(strategy): IronCondorV2ExpiryConfig — delta-based config, D1/D2/D3/D4 fields`

---

## IC-V2-1 — Entry Logic

**Goal:** `IronCondorV2` strategy class with entry: 25Δ/22Δ short selection, 10Δ long wing placement with floors, SD sanity guard.

**Files to change:**
- `src/strategy/ic_nifty_v2.py` — new strategy class (entry only in this story)
- `tests/unit/strategy/test_ic_nifty_v2_entry.py` — new test file

**Before any code:**
```
search_graph("IronCondorV1")             # see V1 class structure
get_code_snippet("IronCondorV1")         # exact fields, method signatures
get_code_snippet("IronCondorV1._select_short_put")  # V1 strike selection pattern
get_code_snippet("IronCondorV1._apply_liquidity_gate")  # reuse liquidity gate
search_graph("PaperStrategy")            # protocol signature
get_code_snippet("IronCondorV2ExpiryConfig")  # confirm IC-V2-0 is done
```

**What to implement:**

Class skeleton with `enter()` only. Adjustment and exit go in IC-V2-2 / IC-V2-3.

```python
class IronCondorV2:
    """Iron Condor V2: high-delta (25Δ/22Δ) IC with 10Δ wings and partial-roll adjustments.

    Separate from V1. Structural differences:
    - Entry: 25Δ put / 22Δ call vs V1's 15Δ/10Δ
    - Wings: 10Δ placement with premium/liquidity floors vs V1's fixed points
    - Adjustment: full vertical roll (4-leg atomic) vs V1's ROLL_WING only
    """
```

**Entry method — key rules:**

1. `_select_short_put(chain)` — find the put strike where `|delta - 0.25| ≤ delta_range`. If multiple candidates, prefer the one with delta closest to target. If none, skip entry.

2. `_select_short_call(chain)` — same for call at 0.22Δ target.

3. `_select_long_wing(chain, short_delta_target, side)` — find the OTM wing at ~10Δ. Enforce:
   - `abs(delta) ≥ long_wing_delta_floor` (0.05)
   - `mid_premium ≥ long_wing_min_premium` (₹10 weekly / ₹15 monthly)
   - Passes `_apply_liquidity_gate()` (reuse from V1 or shared utility)
   - If no candidate satisfies all three: log `ic_v2.wing_floor_miss`, skip entry.

4. `_sd_sanity_check(spot, atm_iv, dte, actual_wing_width)` — compute:
   ```
   sd_width = spot × atm_iv × sqrt(dte / 365) × 1.25
   if actual_wing_width > 1.5 × sd_width: warn "ic_v2.sd_warn.wide"
   if actual_wing_width < 0.4 × sd_width: warn "ic_v2.sd_warn.tight"
   ```
   Warnings only — never block entry.

5. `enter(market, config)` — assemble the 4-leg IC, validate all conditions, return `PositionUpdate` or skip.

**Tests (test_ic_nifty_v2_entry.py):**
- `test_enter_happy_path` — valid chain, both shorts selected, wings pass floors, returns PositionUpdate with 4 legs
- `test_enter_skips_when_no_put_in_delta_range` — no put within ±0.03 of 0.25Δ
- `test_enter_skips_when_wing_premium_below_floor` — put wing mid < ₹15
- `test_enter_skips_when_wing_delta_below_floor` — available OTM put delta < 0.05
- `test_sd_sanity_check_wide_wing_emits_warn` — logs ic_v2.sd_warn.wide, does not skip entry
- `test_sd_sanity_check_tight_wing_emits_warn` — logs ic_v2.sd_warn.tight
- `test_enter_short_put_closer_to_money_than_call` — structural invariant: short put strike < short call strike

**Commit:** `feat(strategy): IronCondorV2 entry — 25Δ/22Δ shorts, 10Δ wings with floors, SD guard`

---

## IC-V2-2 — Adjustment Logic

**Goal:** Partial-roll adjustment: signal detection (`DELTA_WARN / ROLL_WING / DELTA_STOP / FORCED_CLOSE`), 4-leg atomic close+reopen via OverlayCloser, all roll guards.

**Files to change:**
- `src/strategy/ic_nifty_v2.py` — add `_evaluate_adjustment()`, `_execute_partial_roll()`, guards
- `tests/unit/strategy/test_ic_nifty_v2_adjustment.py` — new test file

**Before any code:**
```
get_code_snippet("IronCondorV2._select_long_wing")   # wing selector from IC-V2-1
get_code_snippet("OverlayCloser")                    # understand atomic close API
search_graph("OverlayCloser.close_collar_all")       # see atomic pattern to replicate
get_code_snippet("IronCondorV2ExpiryConfig.max_rolls_per_side_per_cycle")  # guard value
```

**Signal hierarchy (D3 ruling):**

```
|short_delta| ≥ 0.30  →  DELTA_WARN  (log only)
|short_delta| ≥ 0.35  →  ROLL_WING   (attempt partial roll)
|short_delta| ≥ 0.35 AND roll blocked  →  DELTA_STOP  (close challenged spread only)
|short_delta| ≥ 0.45 OR max_rolls exhausted  →  FORCED_CLOSE  (close full IC)
```

**Roll guards (ALL must pass for roll to execute):**
1. DTE above expiry-specific cutoff (delegated to DTE logic in IC-V2-3; treat as injected predicate here)
2. Replacement short strike exists within delta range on current chain
3. Replacement long wing satisfies delta floor + premium floor + liquidity gate
4. `replacement_width ≤ original_spread_width` — no max-loss expansion
5. `roll_debit ≤ 0.50 × original_ic_credit` (config: `roll_debit_cap_fraction`)
6. `rolls_executed_this_side < max_rolls_per_side_per_cycle` (config: 1)
7. `new_short_put_strike < existing_short_call_strike` (inverted condor guard); equivalently for call rolls: `new_short_call_strike > existing_short_put_strike`

**Atomic execution (4-leg):**
1. Close challenged spread: buy back short (challenged side), sell back long (challenged side)
2. Open replacement spread: sell new short at 25Δ farther OTM, buy new long at 10Δ
3. Leave profitable side untouched
4. Steps 1+2 must be submitted as a single `PositionUpdate` — no partial states

**State tracking:**
- `_rolls_executed: dict[str, int]` keyed by `"put" | "call"` — reset on new entry cycle
- Track `original_ic_credit: Decimal` at entry for debit-cap guard

**Tests (test_ic_nifty_v2_adjustment.py):**
- `test_delta_warn_fires_at_0_30` — DELTA_WARN logged, no roll attempted
- `test_roll_wing_fires_at_0_35` — ROLL_WING, all guards pass, returns 4-leg PositionUpdate
- `test_roll_blocked_escalates_to_delta_stop` — wing floor miss, escalates correctly
- `test_forced_close_at_0_45` — FORCED_CLOSE regardless of guards
- `test_max_rolls_exhausted_forces_close` — second roll attempt → FORCED_CLOSE
- `test_roll_debit_cap_blocks_roll` — roll debit > 50% → blocked → DELTA_STOP
- `test_inverted_condor_guard` — new put short would cross call short → blocked → DELTA_STOP
- `test_width_expansion_guard` — replacement width > original → blocked → DELTA_STOP
- `test_profitable_side_untouched` — roll only touches challenged vertical legs

**greeks-analyst gate:** Mandatory before code-reviewer.

**Commit:** `feat(strategy): IronCondorV2 adjustment — partial roll, 7 guards, atomic 4-leg execution`

---

## IC-V2-3 — DTE-Tiered Exit

**Goal:** Weekly DTE table logic and CLOSE_FULL escalation. Monthly hard-close at DTE≤7. Integrate as predicate injected into IC-V2-2's roll guards.

**Files to change:**
- `src/strategy/ic_nifty_v2.py` — add `_evaluate_dte_action()`, `_should_close_full()`, `_roll_allowed_by_dte()`
- `tests/unit/strategy/test_ic_nifty_v2_dte.py` — new test file

**Before any code:**
```
get_code_snippet("IronCondorV2ExpiryConfig.weekly_close_full_dte")  # confirm config values
get_code_snippet("IronCondorV2._evaluate_adjustment")  # see where DTE predicate is consumed
```

**DTE logic (D4 ruling):**

For weekly expiry:
```
dte ≤ 1    →  CLOSE_FULL immediately, no discretion
dte ≤ 3    →  CLOSE_FULL if any delta stop condition fires
dte 4–5    →  ROLL_WING with strict guards (enforce both debit cap AND premium floor with tighter tolerance)
dte ≥ 6    →  normal roll rules apply
```

For monthly expiry:
```
dte ≤ 7    →  CLOSE_FULL default; same behavior as weekly dte≤3
dte > 7    →  normal roll rules apply
```

`_roll_allowed_by_dte(dte, expiry_type)` → `bool` — returns False when CLOSE_FULL is forced.
`_evaluate_dte_action(dte, expiry_type)` → one of `{"NORMAL", "STRICT_GUARD", "CLOSE_FULL", "FORCE_CLOSE"}`.

**Tests (test_ic_nifty_v2_dte.py):**
- `test_weekly_dte_ge_6_normal` — NORMAL
- `test_weekly_dte_5_strict` — STRICT_GUARD
- `test_weekly_dte_4_strict` — STRICT_GUARD
- `test_weekly_dte_3_close_full` — CLOSE_FULL
- `test_weekly_dte_1_force_close` — FORCE_CLOSE (overrides even no delta stop)
- `test_monthly_dte_gt_7_normal` — NORMAL
- `test_monthly_dte_7_close_full` — CLOSE_FULL
- `test_monthly_dte_1_force_close` — FORCE_CLOSE
- `test_roll_allowed_by_dte_weekly` — False for dte≤3, True for dte≥6
- `test_dte_0_is_force_close` — boundary: DTE=0 → FORCE_CLOSE

**greeks-analyst gate:** Mandatory before code-reviewer.

**Commit:** `feat(strategy): IronCondorV2 DTE-tiered exit — weekly table, monthly hard-close, CLOSE_FULL`

---

## IC-V2-4 — Signal Integration + PaperStrategy Protocol

**Goal:** Wire adjustment and exit into `check_signals()` so `IronCondorV2` satisfies the `PaperStrategy` protocol. Connect IC-V2-1/2/3 methods into one coherent evaluation loop.

**Files to change:**
- `src/strategy/ic_nifty_v2.py` — implement `check_signals(market, positions)` + full signal hierarchy
- `tests/unit/strategy/test_ic_nifty_v2_signals.py` — integration test file

**Before any code:**
```
search_graph("PaperStrategy.check_signals")     # exact protocol signature
get_code_snippet("IronCondorV1.check_signals")  # see V1 implementation pattern
get_code_snippet("IronCondorV2._evaluate_dte_action")   # confirm IC-V2-3 done
get_code_snippet("IronCondorV2._evaluate_adjustment")   # confirm IC-V2-2 done
```

**Signal evaluation order in `check_signals()`:**

1. `_evaluate_dte_action(dte)` — if FORCE_CLOSE → emit `FORCED_CLOSE`, return early
2. For each short leg, compute `|delta|`:
   - ≥ 0.45 → `FORCED_CLOSE` (full IC close)
   - Check roll guard → if max_rolls exhausted → `FORCED_CLOSE`
   - ≥ 0.35 → attempt `ROLL_WING`:
     - If DTE action == CLOSE_FULL → emit `FORCED_CLOSE` instead
     - Try partial roll; if guards fail → `DELTA_STOP`
   - ≥ 0.30 → `DELTA_WARN` (log, no action)
3. No delta stop → evaluate profit target (if both spreads at ≤20% of original credit → CLOSE_FULL)
4. No exit → return empty signals (hold)

**Tests (test_ic_nifty_v2_signals.py):**
- `test_no_signal_on_healthy_position` — deltas near entry values → empty signals
- `test_full_pipeline_delta_warn` — |short_delta| 0.31 → DELTA_WARN, no action
- `test_full_pipeline_roll_wing` — |short_delta| 0.36, guards pass → ROLL_WING signal
- `test_full_pipeline_forced_close_delta` — |short_delta| 0.46 → FORCED_CLOSE
- `test_full_pipeline_forced_close_dte` — weekly DTE=1 → FORCED_CLOSE regardless of deltas
- `test_full_pipeline_profit_target` — both spreads decayed to 20% of credit → CLOSE_FULL
- `test_protocol_compliance` — IronCondorV2 satisfies isinstance check for PaperStrategy protocol

**greeks-analyst gate:** Mandatory before code-reviewer.

**Commit:** `feat(strategy): IronCondorV2 check_signals — full signal hierarchy, PaperStrategy protocol`

---

## IC-V2-5 — Registration

**Goal:** Register the two V2 strategies in the factory / entry script so they appear in the daemon and can be tracked in the DB.

**Files to change:**
- Strategy factory or registry file (confirm via `search_graph("strategy_factory")` or `search_graph("STRATEGY_REGISTRY")`)
- Entry script (confirm via `search_graph("paper_ic_nifty_v1")` to find where V1 is registered)
- `tests/unit/strategy/test_ic_nifty_v2_registration.py` — new test file

**Before any code:**
```
search_graph("paper_ic_nifty_v1_weekly")  # find where V1 strategy names are defined
search_graph("STRATEGY_REGISTRY")         # may not exist; fall back to grep
search_code("paper_ic_nifty_v1")          # locate all registration points
get_code_snippet("IronCondorV2")          # confirm IC-V2-4 is complete
```

**Strategy names (exact strings — must match DB):**
```
paper_ic_nifty_v2_weekly
paper_ic_nifty_v2_monthly
```

**Tests:**
- `test_v2_weekly_strategy_name` — assert `IronCondorV2(IC_V2_WEEKLY).strategy_name == "paper_ic_nifty_v2_weekly"`
- `test_v2_monthly_strategy_name` — assert `IronCondorV2(IC_V2_MONTHLY).strategy_name == "paper_ic_nifty_v2_monthly"`
- `test_v2_not_same_as_v1_name` — V2 names do not collide with V1 names

**Commit:** `feat(strategy): register paper_ic_nifty_v2_weekly and paper_ic_nifty_v2_monthly`

---

## IC-V2-6 — Docs Close

**Goal:** Update all doc files to reflect the new module. No code changes.

**Files to change (targeted `Edit` calls only — never `Write` on these):**
- `CONTEXT.md` — add `src/strategy/ic_nifty_v2.py` and `src/strategy/ic_expiry_config_v2.py` to module tree
- `CONTEXT_TREE.md` — add file-level descriptions for new files
- `TODOS.md` — add session log entry for IC V2 completion

**What to add to CONTEXT.md module tree (under `src/strategy/`):**
```
ic_expiry_config_v2.py  — IronCondorV2ExpiryConfig dataclass; IC_V2_WEEKLY / IC_V2_MONTHLY presets
ic_nifty_v2.py          — IronCondorV2 strategy: 25Δ/22Δ entry, 10Δ wings, partial roll adjustment, DTE-tiered exits
```

**No tests.** Docs-only commit:

**Commit:** `docs: add IronCondorV2 to CONTEXT.md, CONTEXT_TREE.md, TODOS.md`

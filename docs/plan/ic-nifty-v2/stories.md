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
3. No delta stop → evaluate profit target (if both spreads at ≤30% of original credit → CLOSE_FULL)
4. No exit → return empty signals (hold)

**Tests (test_ic_nifty_v2_signals.py):**
- `test_no_signal_on_healthy_position` — deltas near entry values → empty signals
- `test_full_pipeline_delta_warn` — |short_delta| 0.31 → DELTA_WARN, no action
- `test_full_pipeline_roll_wing` — |short_delta| 0.36, guards pass → ROLL_WING signal
- `test_full_pipeline_forced_close_delta` — |short_delta| 0.46 → FORCED_CLOSE
- `test_full_pipeline_forced_close_dte` — weekly DTE=1 → FORCED_CLOSE regardless of deltas
- `test_full_pipeline_profit_target` — both spreads decayed to 30% of credit → CLOSE_FULL
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

---

## Phase 2 — Profit-Lock Adjustment

> Council ruling (authoritative): `docs/archive/council/strategy/2026-06-27_ic-v2-profit-lock-adjustment.md` Stage 3.
>
> Design principle: profit-lock is **fully auto_execute=True**. No Telegram approval gate.
> Telegram notification fires **after** execution (confirmation only). If the formula cannot be
> satisfied, CLOSE_FULL executes automatically. No human decision point.

---

## IC-V2-7 — Profit-Lock Config

**Goal:** Add `ProfitLockConfig` dataclass and profit-lock state fields to `ic_expiry_config_v2.py`.
Council ruling: Q4 state fields + Q5 zone table.

**Files to change:**
- `src/strategy/ic_expiry_config_v2.py` — add `ProfitLockConfig` dataclass + update `IronCondorV2ExpiryConfig` with profit-lock fields
- `tests/unit/strategy/test_ic_expiry_config_v2.py` — extend existing test file

**Before any code:**
```
get_code_snippet("IronCondorV2ExpiryConfig")   # current V2 config fields
get_code_snippet("ICExpiryConfig")             # V1 config for comparison reference
```

**What to implement:**

```python
@dataclass(frozen=True)
class ProfitLockConfig:
    """Profit-lock thresholds for IronCondorV2.

    Council ruling: docs/archive/council/strategy/2026-06-27_ic-v2-profit-lock-adjustment.md Stage 3.

    Three zones:
      Zone 1 (25% captured): log-only, no structural change.
      Zone 2 (50% captured): roll long wings inward — structural guarantee required.
      Zone 3 (75% captured): CLOSE_FULL — formula too tight for Nifty execution.

    Floor guarantee formula (Zone 2, enforced before execution):
      max(W_put, W_call) + D_cum + D_lock + K ≤ 0.75 × C₀

    If formula cannot be satisfied: CLOSE_FULL (no exceptions).
    """
    # Zone trigger thresholds (fraction of entry credit captured)
    zone1_trigger: Decimal = Decimal("0.25")
    zone2_trigger: Decimal = Decimal("0.50")
    zone3_trigger: Decimal = Decimal("0.75")

    # Zone 2 — wing inward roll config
    zone2_long_wing_delta_target: Decimal = Decimal("0.19")   # target delta for inward wings
    zone2_long_wing_delta_lo: Decimal = Decimal("0.16")       # acceptable range lo
    zone2_long_wing_delta_hi: Decimal = Decimal("0.22")       # acceptable range hi
    zone2_long_wing_min_premium: Decimal = Decimal("15")      # ₹ min mid-price on new longs

    # Floor formula constants
    floor_budget_zone2: Decimal = Decimal("0.75")             # (1 - F) where F=0.25
    cost_buffer_pts: Decimal = Decimal("10")                  # K: conservative slippage + STT buffer (points)
    max_debit_fraction: Decimal = Decimal("0.25")             # D_lock ≤ 25% of C₀

    # Minimum restructured width to bother (below this → CLOSE_FULL is cleaner)
    min_viable_width_pts: int = 100                           # 100-point minimum on Nifty grid

    # DTE guards (monthly)
    monthly_lock_dte_lo: int = 10   # do not restructure below this DTE
    monthly_lock_dte_hi: int = 22   # prefer restructure window; above this restructure only if cheap

    # DTE guards (weekly)
    weekly_lock_dte_lo: int = 4
    weekly_lock_dte_hi: int = 6

    # IV/VIX guards (secondary — mathematical formula is primary)
    min_vix: Decimal = Decimal("11")
    min_ivr: Decimal = Decimal("0.20")
```

Add to `IronCondorV2ExpiryConfig`:
```python
    profit_lock: ProfitLockConfig = field(default_factory=ProfitLockConfig)
```

Update `IC_V2_MONTHLY` and `IC_V2_WEEKLY` presets to include `profit_lock=ProfitLockConfig(...)` with
weekly overriding `zone2_long_wing_min_premium=Decimal("10")` and DTE guards.

**Tests (append to test_ic_expiry_config_v2.py):**
- `test_profit_lock_config_defaults` — zone triggers at 0.25/0.50/0.75, floor_budget 0.75
- `test_profit_lock_monthly_preset` — min_premium=₹15, monthly DTE lo=10/hi=22
- `test_profit_lock_weekly_preset` — min_premium=₹10, weekly DTE lo=4/hi=6
- `test_profit_lock_frozen` — ProfitLockConfig is frozen=True
- `test_floor_budget_plus_zone3_equals_one` — floor_budget(z2)=0.75; if Zone 3 were implemented: 0.35

**Commit:** `feat(strategy): ProfitLockConfig — zone thresholds, floor formula constants, DTE/IV guards`

---

## IC-V2-8 — Profit-Lock Engine

**Goal:** Pure, stateless formula engine for profit-lock decisions.
Encapsulates: trigger detection, floor formula evaluation, wing selector, guard checker, PositionUpdate builder.
No I/O, no DB, fully testable offline.

Council ruling: Q1 (A=only valid approach), Q2 (complete formula), Q4 (automation feasibility).

**Files to change:**
- `src/strategy/profit_lock_engine.py` — new module
- `tests/unit/strategy/test_profit_lock_engine.py` — new test file

**Before any code:**
```
search_graph("IronCondorV2ExpiryConfig")           # confirm IC-V2-7 done
get_code_snippet("ProfitLockConfig")               # exact fields
search_graph("OptionChain")                        # chain data model
get_code_snippet("filter_strikes_by_delta")        # reuse wing selector pattern
search_graph("_apply_liquidity_gate")              # liquidity gate signature
```

**What to implement:**

```python
@dataclass(frozen=True)
class ProfitLockState:
    """Mutable profit-lock state for one IC cycle. Persisted in PaperStore (IC-V2-9)."""
    profit_lock_zone: int                    # highest zone reached: 0/1/2/3
    zone2_lock_executed: bool
    zone3_lock_executed: bool                # reserved; always CLOSE_FULL for now
    cumulative_lock_debit_pts: Decimal       # D_cum running total (option points)
    active_put_width_pts: int                # current put spread width post any restructure
    active_call_width_pts: int               # current call spread width post any restructure
    cycle_id: str                            # resets on new entry


@dataclass(frozen=True)
class ProfitLockDecision:
    """Output of ProfitLockEngine.evaluate(). Consumed by IronCondorV2.check_signals()."""
    action: Literal["NONE", "ZONE1_LOG", "ZONE2_LOCK", "CLOSE_FULL"]
    zone: int                                # zone that triggered (0 if NONE)
    captured_fraction: Decimal
    formula_passes: bool                     # True if floor constraint satisfied
    required_max_width_pts: int | None       # W constraint from formula (None if NONE/CLOSE_FULL)
    new_put_wing: OptionLeg | None           # selected replacement put long wing
    new_call_wing: OptionLeg | None          # selected replacement call long wing
    net_debit_pts: Decimal | None            # D_lock (per-unit points)
    guaranteed_floor_fraction: Decimal | None  # worst-case retained profit / C₀
    skip_reason: str | None                  # human-readable if action==NONE due to guard


class ProfitLockEngine:
    """Stateless evaluator for IC V2 profit-lock decisions.

    All inputs are pure values (no DB, no I/O). Caller (IronCondorV2) provides
    current state; this engine returns a ProfitLockDecision.
    """

    def evaluate(
        self,
        captured_fraction: Decimal,
        entry_credit_pts: Decimal,       # C₀ in option points per unit
        current_mark_pts: Decimal,
        dte: int,
        expiry_type: str,                # "weekly" | "monthly"
        vix: Decimal | None,
        ivr: Decimal | None,
        state: ProfitLockState,
        chain: OptionChain,
        config: ProfitLockConfig,
        short_put_strike: Decimal,       # to enforce width ≥ min_viable_width
        short_call_strike: Decimal,
    ) -> ProfitLockDecision: ...

    def _detect_zone(self, captured_fraction: Decimal, config: ProfitLockConfig) -> int:
        """Return highest un-acted zone: 0 if nothing new to act on."""
        ...

    def _evaluate_floor_formula(
        self,
        new_width_pts: int,
        d_cum_pts: Decimal,
        d_lock_pts: Decimal,
        k_pts: Decimal,
        entry_credit_pts: Decimal,
        floor_budget: Decimal,
    ) -> bool:
        """max(W_put, W_call) + D_cum + D_lock + K ≤ floor_budget × C₀."""
        ...

    def _select_inward_wing(
        self,
        chain: OptionChain,
        side: Literal["put", "call"],
        short_strike: Decimal,
        config: ProfitLockConfig,
    ) -> OptionLeg | None:
        """Find replacement long wing at ~19Δ satisfying delta/premium/liquidity floors."""
        ...

    def _check_dte_guard(self, dte: int, expiry_type: str, config: ProfitLockConfig) -> bool: ...
    def _check_iv_guard(self, vix: Decimal | None, ivr: Decimal | None, config: ProfitLockConfig) -> bool: ...
    def _check_debit_guard(self, d_lock_pts: Decimal, entry_credit_pts: Decimal, config: ProfitLockConfig) -> bool: ...
```

**Formula implementation (verbatim from council Q2):**
```python
def _evaluate_floor_formula(self, new_width_pts, d_cum_pts, d_lock_pts, k_pts,
                             entry_credit_pts, floor_budget) -> bool:
    return (Decimal(new_width_pts) + d_cum_pts + d_lock_pts + k_pts
            <= floor_budget * entry_credit_pts)
```

Note: `new_width_pts = max(new_put_width, new_call_width)`. Use worst side.

**Tests (test_profit_lock_engine.py):**
- `test_zone_detection_none_below_25pct` — captured=0.20 → zone=0, action=NONE
- `test_zone1_log_only` — captured=0.30, zone1 not yet acted → action=ZONE1_LOG, no wings selected
- `test_zone2_formula_passes` — valid chain, formula satisfied → action=ZONE2_LOCK, formula_passes=True
- `test_zone2_formula_fails_close_full` — debit too high, required width < 100pts → action=CLOSE_FULL
- `test_zone2_skips_if_already_executed` — zone2_lock_executed=True → action=NONE
- `test_zone2_dte_guard_blocks` — DTE=6 monthly → action=NONE, skip_reason set
- `test_zone2_iv_guard_bypass_when_formula_has_buffer` — VIX=9 but K≥15pts → still executes
- `test_zone2_debit_cap_blocks` — D_lock > 25% of C₀ → action=CLOSE_FULL
- `test_zone2_width_below_100pts_prefers_close` — required width=50pts → action=CLOSE_FULL
- `test_formula_evaluation_exact` — numeric spot-check: C₀=200, D_cum=0, D_lock=34, K=10, W=100 → 144 ≤ 150 ✓
- `test_formula_evaluation_fails` — W=120, D_lock=40, K=10 → 170 > 150 ✗
- `test_select_inward_wing_happy` — chain has 19Δ put/call with OI>50k → returns OptionLeg
- `test_select_inward_wing_no_candidate` — no strike in 16–22Δ band → returns None → CLOSE_FULL
- `test_guaranteed_floor_fraction` — verify output field = worst_pnl / C₀

**greeks-analyst gate:** Mandatory before code-reviewer.

**Commit:** `feat(strategy): ProfitLockEngine — floor formula, wing selector, 3-zone evaluation`

---

## IC-V2-9 — State Persistence

**Goal:** Persist `ProfitLockState` in `paper_strategies` table. Add `get/set_profit_lock_state()` to `PaperStore`.
Council ruling: Q4 state fields.

**Files to change:**
- `src/paper/store.py` — add `get_profit_lock_state()`, `set_profit_lock_state()`, migration SQL
- `tests/unit/paper/test_profit_lock_state.py` — new test file

**Before any code:**
```
get_code_snippet("PaperStore.get_proxy_delta_breach_count")   # existing pattern for paper_strategies table
get_code_snippet("PaperStore.set_proxy_delta_breach_count")   # setter pattern
search_graph("paper_strategies")                               # current schema
get_code_snippet("ProfitLockState")                           # confirm IC-V2-8 done
```

**Schema additions to `paper_strategies` table:**

```sql
ALTER TABLE paper_strategies ADD COLUMN profit_lock_zone       INTEGER  DEFAULT 0;
ALTER TABLE paper_strategies ADD COLUMN zone2_lock_executed    INTEGER  DEFAULT 0;   -- BOOLEAN
ALTER TABLE paper_strategies ADD COLUMN zone3_lock_executed    INTEGER  DEFAULT 0;   -- BOOLEAN
ALTER TABLE paper_strategies ADD COLUMN cumulative_lock_debit  TEXT     DEFAULT '0'; -- Decimal as TEXT
ALTER TABLE paper_strategies ADD COLUMN active_put_width_pts   INTEGER  DEFAULT 0;
ALTER TABLE paper_strategies ADD COLUMN active_call_width_pts  INTEGER  DEFAULT 0;
ALTER TABLE paper_strategies ADD COLUMN cycle_id               TEXT     DEFAULT '';
```

**API:**

```python
def get_profit_lock_state(self, strategy_name: str) -> ProfitLockState:
    """Return current profit-lock state; inserts default row if missing."""
    ...

def set_profit_lock_state(self, strategy_name: str, state: ProfitLockState) -> None:
    """Upsert all profit-lock state fields atomically."""
    ...

def reset_profit_lock_state(self, strategy_name: str, cycle_id: str) -> None:
    """Reset all fields to defaults for a new entry cycle."""
    ...
```

**Tests (test_profit_lock_state.py):**
- `test_get_default_state_when_missing` — no row → returns zero-state ProfitLockState
- `test_set_and_get_roundtrip` — set zone2_lock_executed=True, cumulative_debit=34 → retrieve matches
- `test_decimal_stored_as_text` — cumulative_lock_debit persisted as TEXT, read back as Decimal
- `test_reset_clears_all_fields` — after set, reset_profit_lock_state → all fields zero/False
- `test_upsert_does_not_duplicate` — set twice → only one row per strategy_name

**Commit:** `feat(paper): profit-lock state persistence — PaperStore get/set/reset + schema migration`

---

## IC-V2-10 — Signal Integration

**Goal:** Wire `ProfitLockEngine` into `IronCondorV2.check_signals()`. Auto-execute all profit-lock
actions. Send Telegram notification after execution (confirmation only — no approval gate).
Council ruling: Q3 precedence ladder + Q4 automation.

**Files to change:**
- `src/strategy/ic_nifty_v2.py` — integrate profit-lock evaluation into `check_signals()` + `apply_action()`
- `tests/unit/strategy/test_ic_nifty_v2_profit_lock.py` — new test file

**Before any code:**
```
get_code_snippet("IronCondorV2.check_signals")     # confirm IC-V2-4 done
get_code_snippet("ProfitLockEngine.evaluate")      # confirm IC-V2-8 done
get_code_snippet("PaperStore.get_profit_lock_state")  # confirm IC-V2-9 done
search_graph("TelegramGateway.send_message")       # notification (not approval) method
```

**Precedence ladder in `check_signals()` (full, after IC-V2-4 signals):**

```
Priority 1: DTE ≤ hard-close cutoff → FORCED_CLOSE (existing IC-V2-3)
Priority 2: |short_delta| ≥ 0.45   → FORCED_CLOSE (existing IC-V2-2)
Priority 3: D3 roll budget exhausted + delta breached → FORCED_CLOSE (existing IC-V2-2)
Priority 4: captured ≥ 70%          → CLOSE_FULL via existing profit target (existing IC-V2-4)
Priority 5: captured ≥ 50% (Zone 2) → ProfitLockEngine.evaluate():
              ZONE2_LOCK  → emit PROFIT_LOCK_ZONE2 (ACTION, auto_execute=True); notify Telegram
              CLOSE_FULL  → emit FORCED_CLOSE (formula failed); auto-execute
              NONE        → log skip_reason, continue
Priority 6: captured ≥ 25% (Zone 1) → emit PROFIT_LOCK_ZONE1 (INFO); log only
Priority 7: |short_delta| ≥ 0.35   → D3 roll (existing IC-V2-2)
Priority 8: |short_delta| ≥ 0.30   → DELTA_WARN (existing IC-V2-2)
```

**Key automability rules:**
- `PROFIT_LOCK_ZONE2` signal has `auto_execute=True` in payload — `StrategyMonitor` dispatches
  to `PaperExecutor` without Telegram approval gate.
- After execution, `_send_profit_lock_notification()` fires via `TelegramGateway.send_message()`
  (not `send_approval_request`). Message includes: zone, new widths, guaranteed floor %, net debit.
- `apply_action()` handles `PROFIT_LOCK_ZONE2`: closes old longs, opens new longs, calls
  `store.set_profit_lock_state()` with updated state. All in one atomic DB transaction.
- On new IC entry (detected by new `cycle_id`): call `store.reset_profit_lock_state()`.

**Profit-lock notification format (Telegram):**

```
🔒 IC V2 Profit-Lock Executed — Zone 2
Strategy: paper_ic_nifty_v2_monthly
Captured: 52.3% of entry credit
Action: Long wings rolled inward
  PUT:  23,500PE → 23,850PE (width 500→150 pts)
  CALL: 25,500CE → 25,150CE (width 500→150 pts)
Net debit: ₹34 pts (₹2,550/lot)
Floor locked: ≥25% of ₹15,000 (≥₹3,750) guaranteed
DTE: 16  VIX: 13.2  IVR: 0.34
```

**Tests (test_ic_nifty_v2_profit_lock.py):**
- `test_zone1_emits_info_no_action` — captured=0.28 → PROFIT_LOCK_ZONE1 INFO, no auto_execute
- `test_zone2_executes_automatically` — captured=0.52, formula passes → PROFIT_LOCK_ZONE2 ACTION, auto_execute=True
- `test_zone2_close_full_when_formula_fails` — engine returns CLOSE_FULL → FORCED_CLOSE emitted
- `test_zone2_not_repeated` — zone2_lock_executed=True → zone2 branch skipped, no duplicate signal
- `test_zone2_precedence_below_forced_close` — |delta|≥0.45 fires first → no zone2 signal
- `test_zone2_precedence_below_profit_target` — captured=0.72 → profit target fires, not zone2
- `test_zone2_precedence_above_d3_roll` — captured=0.52 AND |delta|=0.36 → profit-lock first, then re-evaluate D3
- `test_notification_payload` — PROFIT_LOCK_ZONE2 payload has guaranteed_floor_fraction, new widths, net_debit
- `test_apply_action_updates_state` — after PROFIT_LOCK_ZONE2 apply_action, store state has zone2_lock_executed=True

**greeks-analyst gate:** Mandatory before code-reviewer.

**Commit:** `feat(strategy): IronCondorV2 profit-lock signal integration — auto-execute, Telegram notify`

---

## IC-V2-11 — V1 vs V2 Monthly Comparison Script

**Goal:** EOD cron script comparing `paper_ic_nifty_v1_monthly` vs `paper_ic_nifty_v2_monthly`
side-by-side. Runs after `paper_ic_snapshot.py`. Sends a Telegram report showing which strategy
is performing better on all key dimensions.

**Files to change:**
- `scripts/strategies/ic/paper_ic_monthly_comparison.py` — new script
- `tests/unit/strategies/ic/test_paper_ic_monthly_comparison.py` — new test file

**Before any code:**
```
search_code("paper_ic_snapshot.py")               # understand existing snapshot pattern
get_code_snippet("PaperStore.get_open_exit_events") # signal event queries
search_graph("PaperNavSnapshot")                   # NAV snapshot model for P&L
search_code("paper_ic_nifty_v1_monthly")           # find all DB references
```

**What to implement:**

```python
_SCRIPT_NAME = "scripts.strategies.ic.paper_ic_monthly_comparison"

@dataclass
class ICMonthlyStats:
    strategy_name: str
    entry_credit_pts: Decimal | None       # avg across open cycles
    current_mark_pts: Decimal | None
    captured_fraction: Decimal | None      # (entry_credit - mark) / entry_credit
    dte: int | None
    short_put_delta: Decimal | None
    short_call_delta: Decimal | None
    profit_lock_zone: int                  # 0 if V1 (no profit-lock)
    realized_pnl_month: Decimal            # this calendar month's realized P&L
    unrealized_pnl: Decimal
    signals_fired_today: list[str]         # signal types from paper_exit_events
    adjustment_count: int                  # rolls + profit-locks executed this cycle


def build_comparison_report(v1: ICMonthlyStats, v2: ICMonthlyStats) -> str:
    """Build a Telegram-formatted plain-text comparison table."""
    ...
```

**Telegram report format:**

```
📊 IC Monthly Comparison — {date}

                    V1 Monthly      V2 Monthly
─────────────────────────────────────────────
Entry credit        ₹X,XXX          ₹X,XXX
Captured            XX%             XX%
Short put Δ         0.18            0.27
Short call Δ        0.12            0.24
DTE                 XX              XX
Unrealized P&L      ₹X,XXX          ₹X,XXX
Realized (month)    ₹X,XXX          ₹X,XXX
Profit-lock zone    N/A             Zone 2 ✓
Adjustments         X rolls         X rolls + X locks
Signals today       DELTA_WARN      —

Edge so far:  V2 +₹X,XXX vs V1
```

**Run cadence:** `45 15 * * 1-5` (after `paper_ic_snapshot.py`).
**Handles gracefully:** one or both strategies have no open position → reports "No open position".

**Tests (test_paper_ic_monthly_comparison.py):**
- `test_build_stats_no_open_position` — no paper positions → ICMonthlyStats with None fields
- `test_build_stats_happy_path` — 4-leg IC in store → populated ICMonthlyStats
- `test_captured_fraction_formula` — verify (entry - mark) / entry arithmetic
- `test_comparison_report_format` — both stats populated → output string contains both strategy names
- `test_comparison_report_one_missing` — V2 not open → report shows "No open position" for V2
- `test_edge_calculation` — V2 unrealized > V1 unrealized → edge line shows V2 leading

**Commit:** `feat(scripts/ic): paper_ic_monthly_comparison — V1 vs V2 EOD Telegram report`

---

## IC-V2-12 — Final Docs Close

**Goal:** Update all doc files to reflect the complete IC V2 module including profit-lock and comparison.
No code changes.

**Files to change (targeted `Edit` calls only):**
- `CONTEXT.md` — add new files to module tree under `src/strategy/` and `scripts/strategies/ic/`
- `CONTEXT_TREE.md` — file-level descriptions for all new modules
- `DECISIONS.md` — add profit-lock council ruling as architecture decision
- `TODOS.md` — session log entry for IC V2 completion

**What to add to CONTEXT.md:**
```
src/strategy/profit_lock_engine.py  — ProfitLockEngine: zone detection, floor formula, wing selector;
                                      ProfitLockState + ProfitLockDecision frozen dataclasses
scripts/strategies/ic/paper_ic_monthly_comparison.py
                                    — EOD V1 vs V2 monthly comparison cron; ICMonthlyStats; Telegram report
```

**No tests.** Docs-only commit:

**Commit:** `docs: IC V2 complete — profit-lock + comparison modules in CONTEXT.md, DECISIONS.md`

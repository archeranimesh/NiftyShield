# Iron Condor V2 — Story Specs

> One task per session. Find the first unchecked item in `tasks.md`. That is your only task.
> Full council ruling: `docs/archive/council/strategy/2026-06-26_ic-v2-core-design.md` Stage 3 (authoritative).
> After each task: tick `tasks.md`, append `| SHA: <sha>`, add one line to `TODOS.md`.

---

## Logging Contract

> All `ic_nifty_v2.*` log events must follow this contract. Implementors: read this section
> before writing any `log.*` call. Do not invent event names; use only the keys listed here.

### Logger declaration (every file that logs)

```python
import structlog
log = structlog.get_logger(__name__)
```

### Event key namespace

All events use the prefix `ic_nifty_v2.` followed by an underscore-separated suffix — matching
the convention in `ic_nifty_v1`, `cc_overlay_v1`, `collar_overlay_v1`.

Examples of the pattern:
```
ic_nifty_v2.entry_skip_no_short_put        # good
ic_nifty_v2.roll_guard_failed              # good
ic_nifty_v2.sd_warn.wide                   # ✗  — dotted sub-namespace, not used here
```

### Baseline context fields

Every `ic_nifty_v2.*` log call must include these kwargs (where available at the call site).
Omit only when the value is genuinely unavailable (e.g., `trade_id` before a trade exists).

| Field | Type | Example |
|---|---|---|
| `strategy_name` | `str` | `"paper_ic_nifty_v2_monthly"` |
| `trade_id` | `str` | `"ic_v2_monthly_20260627"` |
| `expiry` | `str` | `"2026-07-31"` |
| `dte` | `int` | `16` |

Adjustment and profit-lock events must also include:

| Field | Type | Example |
|---|---|---|
| `roll_count_put` | `int` | `0` |
| `roll_count_call` | `int` | `0` |
| `profit_lock_zone` | `int` | `0` |

### Log level guide

| Level | When to use |
|---|---|
| `log.debug` | Intermediate values, chain scans, candidate lists — high volume, dev-only |
| `log.info` | Normal business events: entry recorded, action applied, profit-lock executed |
| `log.warning` | Recoverable skip or guard block: entry skipped, roll blocked, guard failed |
| `log.error` | Unrecoverable failure: notification send failed, DB write failed |

### Event table

#### IC-V2-1 — Entry

| Event key | Level | Required kwargs (beyond baseline) |
|---|---|---|
| `ic_nifty_v2.entry_skip_no_short_put` | warning | `delta_range`, `best_available_delta` |
| `ic_nifty_v2.entry_skip_no_short_call` | warning | `delta_range`, `best_available_delta` |
| `ic_nifty_v2.entry_skip_wing_floor_miss` | warning | `side` (`"put"`/`"call"`), `reason` (`"delta"`/`"premium"`/`"liquidity"`), `floor_value`, `actual_value` |
| `ic_nifty_v2.entry_sd_warn_wide` | warning | `actual_width_pts`, `sd_width_pts`, `multiplier` |
| `ic_nifty_v2.entry_sd_warn_tight` | warning | `actual_width_pts`, `sd_width_pts`, `multiplier` |
| `ic_nifty_v2.entry_recorded` | info | `short_put_strike`, `short_call_strike`, `long_put_strike`, `long_call_strike`, `total_credit_pts`, `ivr` |

#### IC-V2-2 — Adjustment

| Event key | Level | Required kwargs (beyond baseline) |
|---|---|---|
| `ic_nifty_v2.delta_warn` | warning | `side`, `short_delta`, `threshold` |
| `ic_nifty_v2.roll_wing_attempt` | info | `side`, `short_delta`, `original_short_strike`, `original_long_strike` |
| `ic_nifty_v2.roll_guard_failed` | warning | `side`, `guard` (one of the values below), `detail` |
| `ic_nifty_v2.delta_stop` | warning | `side`, `short_delta`, `block_reason` (`"roll_guard_failed"` / `"no_roll_candidate"`) |
| `ic_nifty_v2.forced_close_delta` | warning | `side`, `short_delta`, `threshold` |
| `ic_nifty_v2.forced_close_rolls_exhausted` | warning | `side`, `roll_count` |
| `ic_nifty_v2.roll_wing_executed` | info | `side`, `old_short_strike`, `old_long_strike`, `new_short_strike`, `new_long_strike`, `roll_debit_pts`, `roll_count_after` |

Valid `guard` values for `ic_nifty_v2.roll_guard_failed`:

```
"dte_cutoff"          — DTE at or below close_full threshold
"no_short_candidate"  — no replacement short in delta range
"wing_floor_miss"     — replacement long fails delta/premium/liquidity floor
"width_expansion"     — replacement width > original spread width
"debit_cap"           — roll debit > roll_debit_cap_fraction × original IC credit
"max_rolls_exhausted" — rolls_executed_this_side >= max_rolls_per_side_per_cycle
"inverted_condor"     — new short would cross the opposite side's short strike
```

#### IC-V2-3 — DTE-tiered exit

| Event key | Level | Required kwargs (beyond baseline) |
|---|---|---|
| `ic_nifty_v2.dte_close_full` | warning | `dte`, `threshold` |
| `ic_nifty_v2.dte_force_close` | warning | `dte` |

#### IC-V2-4 — Signal integration / apply_action

| Event key | Level | Required kwargs (beyond baseline) |
|---|---|---|
| `ic_nifty_v2.apply_action` | info | `action_type`, `legs_to_close` |
| `ic_nifty_v2.profit_target_close` | info | `captured_fraction`, `current_mark_pts`, `entry_credit_pts` |

#### IC-V2-8 — Profit-lock engine

These are emitted by the *caller* (IC-V2-10), not inside the pure engine. The engine returns
`ProfitLockDecision`; the strategy logs the outcome.

| Event key | Level | Required kwargs (beyond baseline) |
|---|---|---|
| `ic_nifty_v2.profit_lock_zone1` | info | `captured_fraction`, `zone` |
| `ic_nifty_v2.profit_lock_zone2_attempt` | info | `captured_fraction`, `zone`, `formula_passes` |
| `ic_nifty_v2.profit_lock_zone2_skipped` | warning | `skip_reason`, `captured_fraction` |
| `ic_nifty_v2.profit_lock_zone2_executed` | info | `new_put_wing_strike`, `new_call_wing_strike`, `net_debit_pts`, `guaranteed_floor_fraction` |
| `ic_nifty_v2.profit_lock_close_full` | warning | `reason` (`"formula_failed"` / `"wing_not_found"` / `"debit_cap"`), `captured_fraction` |

#### IC-V2-10 / IC-V2-2 / IC-V2-4 — Infra errors (emit in any story that triggers them)

| Event key | Level | Required kwargs |
|---|---|---|
| `ic_nifty_v2.send_notification_failed` | error | `error` |
| `ic_nifty_v2.strike_parse_failed` | warning | `instrument_key` |
| `ic_nifty_v2.chain_lookup_failed` | warning | `instrument_key` |

---

## IC-V2-0 — Config Dataclass

**Goal:** New config dataclass `IronCondorV2ExpiryConfig` replacing `wing_width_points: int` with delta-based wing fields. Monthly preset only.

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
    expiry_type: str                              # "monthly"

    # Entry — short leg deltas (D1 ruling)
    short_put_delta_target: Decimal = Decimal("0.25")
    short_call_delta_target: Decimal = Decimal("0.22")
    delta_range: Decimal = Decimal("0.03")        # ±tolerance for strike selection

    # Wing sizing — long leg deltas (D2 ruling)
    long_wing_delta_target: Decimal = Decimal("0.10")
    long_wing_delta_floor: Decimal = Decimal("0.05")   # absolute minimum; skip entry if not met
    long_wing_min_premium: Decimal = Decimal("15")     # ₹ per unit

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

    # DTE-tiered exit (D4)
    monthly_close_full_dte: int = 7    # DTE≤7 → CLOSE_FULL default (refineable during backtest)


# Canonical preset
IC_V2_MONTHLY = IronCondorV2ExpiryConfig(
    expiry_type="monthly",
    long_wing_min_premium=Decimal("15"),   # ₹15 floor for monthly (D2 ruling)
)
```

**Tests (test_ic_expiry_config_v2.py):**
- `test_monthly_preset_defaults` — verify IC_V2_MONTHLY fields, especially long_wing_min_premium=15
- `test_immutability` — frozen=True; assignment raises FrozenInstanceError
- `test_delta_range_positive` — delta_range > 0 on monthly preset
- `test_max_rolls_is_one` — max_rolls_per_side_per_cycle == 1 on monthly preset

**Commit:** `feat(strategy): IronCondorV2ExpiryConfig — delta-based config, D1/D2/D3/D4 fields, monthly only`

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
get_code_snippet("IronCondorV1._parse_expiry")       # copy verbatim — regex, no V1 config dep
get_code_snippet("IronCondorV1._find_leg")           # copy verbatim — pure chain lookup
get_code_snippet("IronCondorV1._compute_combined_pnl")  # copy verbatim — same 4-leg structure
get_code_snippet("IronCondorV1._compute_ivr_str")    # copy verbatim — VIX/IVR load, no V1 dep
get_code_snippet("IronCondorV1._is_auto_execute")    # copy verbatim — util check on ApprovedAction
search_graph("find_strike_by_delta")     # use roll_utils.find_strike_by_delta for delta selection
search_graph("_apply_liquidity_gate")    # use src/instruments/strike_selector._apply_liquidity_gate
search_graph("PaperStrategy")            # protocol signature
get_code_snippet("IronCondorV2ExpiryConfig")  # confirm IC-V2-0 is done
```

**Reuse policy (copy, do not inherit from V1):**
- `_parse_expiry`, `_find_leg`, `_compute_combined_pnl`, `_compute_ivr_str`, `_is_auto_execute`,
  `_EXPIRY_RE`, `_STRIKE_RE`, `_SHORT_ROLES`, `_LONG_ROLES` — copy verbatim from `ic_nifty_v1.py`.
  These have zero V1-specific config dependency.
- `_select_short_put` / `_select_short_call` — call `roll_utils.find_strike_by_delta()` directly;
  do not copy V1's implementation (V1 uses a different delta range + config shape).
- `_select_long_wing` — call `roll_utils.find_strike_by_delta()` + `_apply_liquidity_gate()`;
  enforce V2-specific delta floor and premium floor from `IronCondorV2ExpiryConfig`.
- Do NOT copy `_auto_select_action` or `_select_wing_roll_target` from V1 — both encode V1-specific
  priority ordering and config references that differ in V2.

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
   - `mid_premium ≥ long_wing_min_premium` (₹15)
   - Passes `_apply_liquidity_gate()` (reuse from V1 or shared utility)
   - If no candidate satisfies all three: log `ic_nifty_v2.entry_skip_wing_floor_miss`, skip entry.

4. `_sd_sanity_check(spot, atm_iv, dte, actual_wing_width)` — compute:
   ```
   sd_width = spot × atm_iv × sqrt(dte / 365) × 1.25
   if actual_wing_width > 1.5 × sd_width: warn "ic_nifty_v2.entry_sd_warn_wide"
   if actual_wing_width < 0.4 × sd_width: warn "ic_nifty_v2.entry_sd_warn_tight"
   ```
   Warnings only — never block entry.

5. `enter(market, config)` — assemble the 4-leg IC, validate all conditions, return `PositionUpdate` or skip.

**Tests (test_ic_nifty_v2_entry.py):**
- `test_enter_happy_path` — valid chain, both shorts selected, wings pass floors, returns PositionUpdate with 4 legs
- `test_enter_skips_when_no_put_in_delta_range` — no put within ±0.03 of 0.25Δ
- `test_enter_skips_when_wing_premium_below_floor` — put wing mid < ₹15
- `test_enter_skips_when_wing_delta_below_floor` — available OTM put delta < 0.05
- `test_sd_sanity_check_wide_wing_emits_warn` — logs ic_nifty_v2.entry_sd_warn_wide, does not skip entry
- `test_sd_sanity_check_tight_wing_emits_warn` — logs ic_nifty_v2.entry_sd_warn_tight
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

**Goal:** Monthly DTE exit logic: hard-close at DTE≤7, force-close at DTE≤1. Integrate as predicate injected into IC-V2-2's roll guards.

**Files to change:**
- `src/strategy/ic_nifty_v2.py` — add `_evaluate_dte_action()`, `_should_close_full()`, `_roll_allowed_by_dte()`
- `tests/unit/strategy/test_ic_nifty_v2_dte.py` — new test file

**Before any code:**
```
get_code_snippet("IronCondorV2ExpiryConfig.monthly_close_full_dte")  # confirm config value
get_code_snippet("IronCondorV2._evaluate_adjustment")  # see where DTE predicate is consumed
```

**DTE logic (D4 ruling, monthly only):**

```
dte ≤ 1    →  FORCE_CLOSE immediately, no discretion
dte ≤ 7    →  CLOSE_FULL default
dte > 7    →  normal roll rules apply
```

`_roll_allowed_by_dte(dte)` → `bool` — returns False when CLOSE_FULL is forced.
`_evaluate_dte_action(dte)` → one of `{"NORMAL", "CLOSE_FULL", "FORCE_CLOSE"}`.

**Tests (test_ic_nifty_v2_dte.py):**
- `test_monthly_dte_gt_7_normal` — NORMAL
- `test_monthly_dte_7_close_full` — CLOSE_FULL
- `test_monthly_dte_1_force_close` — FORCE_CLOSE
- `test_roll_allowed_by_dte_monthly` — False for dte≤7, True for dte>7
- `test_dte_0_is_force_close` — boundary: DTE=0 → FORCE_CLOSE

**greeks-analyst gate:** Mandatory before code-reviewer.

**Commit:** `feat(strategy): IronCondorV2 DTE-tiered exit — monthly hard-close DTE≤7, FORCE_CLOSE DTE≤1`

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
- `test_full_pipeline_forced_close_dte` — monthly DTE=1 → FORCED_CLOSE regardless of deltas
- `test_full_pipeline_profit_target` — both spreads decayed to 30% of credit → CLOSE_FULL
- `test_protocol_compliance` — IronCondorV2 satisfies isinstance check for PaperStrategy protocol

**greeks-analyst gate:** Mandatory before code-reviewer.

**Commit:** `feat(strategy): IronCondorV2 check_signals — full signal hierarchy, PaperStrategy protocol`

---

## IC-V2-5 — Registration

**Goal:** Register the V2 monthly strategy in the factory / entry script so it appears in the daemon and can be tracked in the DB.

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

**Strategy name (exact string — must match DB):**
```
paper_ic_nifty_v2_monthly
```

**Tests:**
- `test_v2_monthly_strategy_name` — assert `IronCondorV2(IC_V2_MONTHLY).strategy_name == "paper_ic_nifty_v2_monthly"`
- `test_v2_not_same_as_v1_name` — V2 name does not collide with V1 names

**Commit:** `feat(strategy): register paper_ic_nifty_v2_monthly`

---

## IC-V2-6 — Docs Close

**Goal:** Update all doc files to reflect the new module. No code changes.

**Files to change (targeted `Edit` calls only — never `Write` on these):**
- `CONTEXT.md` — add `src/strategy/ic_nifty_v2.py` and `src/strategy/ic_expiry_config_v2.py` to module tree
- `CONTEXT_TREE.md` — add file-level descriptions for new files
- `TODOS.md` — add session log entry for IC V2 completion

**What to add to CONTEXT.md module tree (under `src/strategy/`):**
```
ic_expiry_config_v2.py  — IronCondorV2ExpiryConfig dataclass; IC_V2_MONTHLY preset
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

    # IV/VIX guards (secondary — mathematical formula is primary)
    min_vix: Decimal = Decimal("11")
    min_ivr: Decimal = Decimal("0.20")
```

Add to `IronCondorV2ExpiryConfig`:
```python
    profit_lock: ProfitLockConfig = field(default_factory=ProfitLockConfig)
```

Update `IC_V2_MONTHLY` preset to include `profit_lock=ProfitLockConfig(...)`.

**Tests (append to test_ic_expiry_config_v2.py):**
- `test_profit_lock_config_defaults` — zone triggers at 0.25/0.50/0.75, floor_budget 0.75
- `test_profit_lock_monthly_preset` — min_premium=₹15, monthly DTE lo=10/hi=22
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
get_code_snippet("find_strike_by_delta")           # use roll_utils.find_strike_by_delta for wing selection
search_graph("_apply_liquidity_gate")              # use src/instruments/strike_selector._apply_liquidity_gate
get_code_snippet("IronCondorV2._find_leg")         # confirm IC-V2-1 done — reuse for chain lookup in engine
```

**Reuse policy:**
- `_select_inward_wing()` must call `roll_utils.find_strike_by_delta()` for delta-range filtering —
  do not reimplement delta scanning. Pass `delta_range=(config.zone2_long_wing_delta_lo,
  config.zone2_long_wing_delta_hi)` and `target_delta=config.zone2_long_wing_delta_target`.
- After `find_strike_by_delta()` returns a candidate, apply the three additional floors inline:
  `abs(delta) ≥ long_wing_delta_floor`, `mid_premium ≥ long_wing_min_premium`, `_apply_liquidity_gate()`.
- Chain lookup within the engine (finding current wing marks for debit calculation) must use
  `IronCondorV2._find_leg()` — do not re-implement strike parsing. The engine receives the chain
  and delegates lookup to the strategy's existing helper via the caller (IC-V2-10 wires this).
- `_evaluate_floor_formula()` is pure arithmetic — no external calls, no chain access.

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
        expiry_type: str,                # "monthly"
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

---

## Phase 4 — Operational Hardening

> Covers three automation gaps identified after Phase 1+2 shipped:
> (1) entry cadence is calendar-unaware, (2) V2 is invisible to the EOD snapshot, (3) entry
> failures are silent. Stories are independent; any order is fine.
>
> **Calendar reality (important — read before IC-V2-13):**
> Nifty monthly expiry is the last Thursday of each month. First Wednesday after expiry gives
> only 22–29 DTE to the *next* monthly expiry (verified across May–Oct 2026). This is below
> the current `_V2_MONTHLY_DTE_WARN_LO=30`. IC-V2-13 recalibrates the DTE window to 20–32
> to match the actual post-expiry entry pattern.

---

## IC-V2-13 — Post-expiry entry gate + DTE recalibration

**Goal:** Make `paper_ic_entry_v2.py` calendar-aware: block entry if the current month's
Nifty monthly expiry has NOT yet passed, and adjust the DTE warning window to match the
22–29 DTE range that first-Wednesday-after-expiry naturally produces.

**Why this matters:** Without the gate, the Wednesday cron could enter mid-cycle (e.g. day 10
of a live position) if the duplicate guard somehow misses. With the gate, the script is
self-documenting about its intended cadence: one position per expiry cycle, entered after
settlement.

**DTE recalibration:**

| Constant | Current value | New value | Reason |
|---|---|---|---|
| `_V2_MONTHLY_DTE_WARN_LO` | 30 | 20 | First Wed after expiry → 22–29 DTE |
| `_V2_MONTHLY_DTE_WARN_HI` | 45 | 32 | Upper bound; warn if stale entry |

The DTE check remains a WARNING (not a hard block) — `--force-entry` bypasses it as before.

**Files to change:**
- `scripts/strategies/ic/paper_ic_entry_v2.py` — add `_post_expiry_gate()` helper +
  update `_V2_MONTHLY_DTE_WARN_LO` / `_V2_MONTHLY_DTE_WARN_HI`
- `tests/unit/strategies/ic/test_paper_ic_entry_v2.py` — add gate tests

**Before any code:**
```
search_code("last_thursday")       # check if InstrumentLookup or instruments module already has this
search_code("monthly_expiry")      # any existing expiry calendar helpers
get_code_snippet("resolve_expiry") # ic_entry_gates — understand how expiry_str is obtained
```

**`_post_expiry_gate()` spec:**

```python
def _post_expiry_gate(force_entry: bool) -> None:
    """Block entry if current month's Nifty monthly expiry has not yet passed.

    Nifty monthly expiry = last Thursday of the current calendar month.
    Entry is only valid after that date has passed (i.e. today > last_thursday(today)).

    Args:
        force_entry: When True, log WARNING and continue instead of sys.exit(1).

    Raises:
        SystemExit(1): If today is on or before the current month's expiry date
                       and force_entry is False.
    """
```

Implementation notes:
- `_last_thursday_of_month(year, month)`: find the last Thursday using
  `calendar.monthrange` — do not rely on hardcoded offsets.
- If `today == last_thursday(today.year, today.month)`: expiry day itself → block
  (settlement is not complete intraday).
- If `today > last_thursday(today.year, today.month)`: past expiry → allow.
- `--force-entry` bypasses with a logged WARNING (same pattern as IVR bypass).

**Call site:** invoke `_post_expiry_gate(args.force_entry)` immediately after `check_duplicate`
in `run()`, before IVR gate.

**Tests to add (append to `test_paper_ic_entry_v2.py`):**
- `test_post_expiry_gate_blocks_before_expiry` — today < last Thursday → `SystemExit(1)`
- `test_post_expiry_gate_blocks_on_expiry_day` — today == last Thursday → `SystemExit(1)`
- `test_post_expiry_gate_passes_after_expiry` — today > last Thursday → no exit
- `test_post_expiry_gate_force_entry_bypasses` — today < last Thursday + force_entry=True → no exit

**Commit:** `feat(scripts/ic): add post-expiry entry gate + recalibrate DTE window to 20-32`

---

## IC-V2-14 — EOD snapshot V2 coverage

**Goal:** Extend `paper_ic_snapshot.py` so V2 positions are included in the daily audit loop.
Currently the script only iterates `CONFIGS` (V1) and hardcodes `IronCondorV1`. V2 positions
get no EOD exit-signal evaluation — if the daemon crashes intraday, V2 has no safety net.

**Files to change:**
- `scripts/strategies/ic/paper_ic_snapshot.py` — add V2 loop after V1 loop
- `tests/unit/strategies/ic/test_paper_ic_snapshot.py` — add V2 coverage tests

**Before any code:**
```
get_code_snippet("process_variant")          # understand the existing per-config handler
search_code("IronCondorV1")                  # find every hardcoded V1 reference in snapshot
get_code_snippet("IronCondorV2.__init__")    # confirm constructor signature matches V1
search_graph("CONFIGS_V2")                   # confirm registry location
```

**What to change:**

The existing `process_variant` function hardcodes `IronCondorV1` instantiation. Refactor to
accept a `strategy_cls` parameter:

```python
async def process_variant(
    expiry_type: str,
    config: Any,                  # ICExpiryConfig or IronCondorV2ExpiryConfig
    store: PaperStore,
    broker: Any,
    lookup: InstrumentLookup,
    notifier: TelegramGateway | None,
    snap_date: date,
    save: bool,
    strategy_cls: type = IronCondorV1,   # injected; default preserves V1 behaviour
) -> str | None:
```

Then in `run()`, after the V1 loop add a V2 loop:

```python
from src.strategy.ic_expiry_config_v2 import CONFIGS_V2
from src.strategy.ic_nifty_v2 import IronCondorV2

for expiry_type, config in CONFIGS_V2.items():
    positions = store.get_positions(config.strategy_name)
    active = [p for p in positions if p.net_qty != 0]
    if active:
        has_any_positions = True
    try:
        report = await process_variant(
            expiry_type, config, store, broker, lookup,
            notifier, snap_date, save,
            strategy_cls=IronCondorV2,
        )
        if report is not None:
            reports.append(report)
    except Exception as exc:
        logger.error("ic_snapshot.v2_variant_failed", strategy=config.strategy_name, error=str(exc))
        reports.append(f"📋 IC EOD Audit — {expiry_type} ({config.strategy_name})\nError: Snapshot failed.")
```

**Important:** `process_variant` calls `ic._compute_ivr_str()`. Verify this method exists on
`IronCondorV2` before implementing — if not, add it or guard with `getattr(..., lambda: "IVR: N/A")`.

**Tests to add:**
- `test_v2_monthly_included_in_audit` — V2 position in store → `process_variant` called with
  `strategy_cls=IronCondorV2`
- `test_v2_no_position_skipped` — no V2 positions → no V2 report, no error
- `test_v1_loop_unchanged` — V2 addition does not alter V1 report output

**Commit:** `feat(scripts/ic): include IronCondorV2 in paper_ic_snapshot EOD audit loop`

---

## IC-V2-15 — Entry failure Telegram alerting

**Goal:** When `paper_ic_entry_v2.py` exits due to a gate failure, send a Telegram notification
before exiting. Currently all gate failures are silent — the cron writes to `logs/ic_v2_monthly.log`
but no inbound alert fires.

**Files to change:**
- `scripts/strategies/ic/paper_ic_entry_v2.py` — wrap gate exits with Telegram send
- `scripts/strategies/ic/ic_entry_gates.py` — add optional `notifier` param to
  `resolve_ivr` and `check_duplicate` (nullable; non-fatal if None)
- `tests/unit/strategies/ic/test_paper_ic_entry_v2.py` — alert tests

**Design:** add a `_build_notifier()` call at the top of `run()` (same pattern as
`src/notifications/__init__.py:build_notifier()`). Pass `notifier` into the gate helpers
that can fail. Gate helpers call `notifier.send_notification(msg)` wrapped in a bare
`except Exception` (non-fatal — telegram failure must never block the gate exit).

**Alert message format:**
```
⚠️ IC V2 Entry BLOCKED — {strategy_name}
Gate: {gate_name}
Reason: {reason}
IVR: {ivr:.2f} / Gate: {ivr_gate:.2f}    ← IVR gate only
```

**Gates that must alert:**

| Gate | Alert on |
|---|---|
| `_post_expiry_gate` | Blocked — expiry not yet passed |
| `check_duplicate` | Blocked — active position exists |
| `resolve_ivr` | IVR below gate (not on None / data-missing) |
| Long wing floor | No wing candidate passes delta + premium floors |
| Portfolio delta | Projected delta outside [-0.05, 0.25] after adjustment attempt |

**Gates that must NOT alert** (infra failures; surface via healthcheck, not entry alert):
- `resolve_expiry` BOD-missing / no candidate
- Chain fetch failure (Upstox API issue)

**Tests to add:**
- `test_ivr_gate_failure_sends_telegram` — IVR below gate → notifier called with ⚠️ message
- `test_duplicate_gate_failure_sends_telegram` — open position → notifier called
- `test_telegram_failure_does_not_block_exit` — notifier raises → script still exits 1

**Commit:** `feat(scripts/ic): Telegram alert on entry gate failures in paper_ic_entry_v2`

---

## IC-V2-16 — Phase 4 docs close

**Goal:** Update docs to reflect Phase 4 additions. No code changes.

**Files to change (targeted `Edit` calls only):**
- `CONTEXT.md` — note post-expiry gate + DTE window in `paper_ic_entry_v2.py` description;
  note V2 loop in `paper_ic_snapshot.py` description
- `TODOS.md` — session log entry

**No tests.** Docs-only commit:

**Commit:** `docs: IC V2 Phase 4 ops hardening in CONTEXT.md, TODOS.md`

**Commit:** `docs: IC V2 complete — profit-lock + comparison modules in CONTEXT.md, DECISIONS.md`

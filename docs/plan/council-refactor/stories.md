# council-refactor — Story Specs

> One task per session. Find the first unchecked item in `tasks.md` **tagged for you**.
> Implementation rules: `CLAUDE.md` and `REVIEW.md`. After each task: tick `tasks.md`,
> append `| SHA: <sha>`, add one line to `TODOS.md`.

**Prerequisite check (run before CR0):**
```
search_graph("ExitSignalEngine")      # must exist (ES1)
search_graph("StrategyMonitor")       # must exist (PB1.2)
search_code("send_approval_request")  # confirm mismatch in monitor.py vs telegram_gateway.py
```

---

## CR0 `[Claude]` — Fix `send_approval_request` signature mismatch

**Files:** `src/strategy/monitor.py`, `src/notifications/telegram_gateway.py`,
`tests/unit/notifications/test_telegram_gateway.py`,
`tests/unit/strategy/test_strategy_monitor.py`

**Before any code:**
- `get_code_snippet("StrategyMonitor._dispatch_event")` — see current call site
- `get_code_snippet("TelegramGateway.send_approval_request")` — see current signature
- `get_code_snippet("CouncilOutput")` — confirm what we are removing from the signature

**The bug:**

`monitor.py` calls:
```python
await self._notifier.send_approval_request(event, context_str)
```

`telegram_gateway.py` signature is:
```python
async def send_approval_request(self, council_output: CouncilOutput, event: SignalEvent, strategy_name: str)
```

This is a `TypeError` at runtime whenever any ACTION event fires. `self._notifier` is
typed `Any` so mypy does not catch it.

**What to change:**

Refactor `TelegramGateway.send_approval_request` to:
```python
async def send_approval_request(
    self,
    event: SignalEvent,
    context_str: str,
    action_options: list[str],   # human-readable action labels e.g. ["CLOSE_FULL", "REJECT"]
) -> int | None:
```

Remove the `CouncilOutput` import and parameter entirely from this method.

Telegram message format after fix:
```
<b>Action required — {strategy_name}</b>
Event: {event.event_type} ({event.severity})
{event.description}

<i>{context_str[:300]}</i>
```
Keyboard: one button per entry in `action_options`, plus "Reject All". `callback_data`
uses `approve:{index}` (0-based index into `action_options`).

Update `monitor._dispatch_event` to call:
```python
action_options = list(event.payload.get("action_options", ["CLOSE_FULL"]))
await self._notifier.send_approval_request(event, context_str, action_options)
```

Convention: each strategy populates `event.payload["action_options"]` with the list of
valid `action_type` strings for that signal. Single-option exits like CSP provide
`["CLOSE_FULL"]` — the Telegram button is a confirmation tap, not a choice.

`pending_approvals.council_output` column: rename to `action_options_json` in the
schema and in `PaperStore.create_approval`. Store `json.dumps(action_options)`. The
`on_approved` callback in `monitor_daemon.py` reads `action_options_json` and
reconstructs the `ApprovedAction` directly — no council reconstruction step.

**Update `monitor_daemon.py` `on_approved` callback:**
- Remove the `council_output` parsing block that reconstructs `ApprovedAction` from
  a `CouncilOutput` JSON structure
- Replace with: read `action_options_json` → pick `action_options[rank]` → build
  `ApprovedAction(action_type=selected, legs_to_close=[], legs_to_open=[], rationale="", council_rank=rank)`
- The `legs_to_close` and `legs_to_open` are looked up from the live position at
  execution time (strategy's `apply_action` owns that logic), not stored in the approval

**Tests:**
- `send_approval_request` with `action_options=["CLOSE_FULL"]` → one approve button + Reject All = 2 buttons
- `send_approval_request` with `action_options=["CLOSE_FULL", "CLOSE_CALL_SPREAD"]` → 3 buttons
- `send_approval_request` API failure → returns `None`; no exception propagated
- `_dispatch_event` with ACTION severity → `send_approval_request` called with `action_options` from `event.payload`
- `_dispatch_event` with ACTION event missing `action_options` key → falls back to `["CLOSE_FULL"]`

**Commit:** `fix(strategy): remove CouncilOutput from approval flow; fix send_approval_request signature mismatch`

---

## CR1a `[Antigravity]` — Extract `strike_selector.py` from `find_strike_by_delta.py`

**Files:**
- `src/instruments/strike_selector.py` (new)
- `scripts/lookup/find_strike_by_delta.py` (update imports)
- `scripts/strategies/csp/paper_csp_roll.py` (update imports)
- `tests/unit/instruments/test_strike_selector.py` (new)

**Before any code:**
- `get_code_snippet("filter_strikes_by_delta")` — exact signature + return shape
- `get_code_snippet("rank_strikes")` — exact signature + return shape
- `get_code_snippet("_apply_liquidity_gate")` — confirm it is a private helper called by `filter_strikes_by_delta`
- `search_graph("strike_selector")` — confirm does NOT yet exist

**What to extract into `src/instruments/strike_selector.py`:**

Move these three functions verbatim from `scripts/lookup/find_strike_by_delta.py`:
- `filter_strikes_by_delta(chain_data, option_type, delta_min, delta_max) -> list[dict]`
- `_apply_liquidity_gate(rows) -> list[dict]`
- `rank_strikes(rows) -> list[dict]`

`find_strike_by_delta.py` becomes a thin CLI wrapper — replace the three function bodies
with imports:
```python
from src.instruments.strike_selector import (
    filter_strikes_by_delta,
    _apply_liquidity_gate,
    rank_strikes,
)
```

`paper_csp_roll.py` line 48 currently imports from the script:
```python
from scripts.lookup.find_strike_by_delta import filter_strikes_by_delta, rank_strikes
```
Change to:
```python
from src.instruments.strike_selector import filter_strikes_by_delta, rank_strikes
```

**Tests (`tests/unit/instruments/test_strike_selector.py`):**

Use `get_code_snippet("filter_strikes_by_delta")` to read the exact interface before writing fixtures.

- `filter_strikes_by_delta` with valid PE rows in range → returns subset
- `filter_strikes_by_delta` with no rows in delta range → returns `[]`
- `_apply_liquidity_gate` with low-OI row → filtered out
- `rank_strikes` with multiple rows → sorted; first row is best candidate
- `rank_strikes` with empty input → returns `[]`

**Commit:** `refactor(instruments): extract strike_selector from find_strike_by_delta; update imports`

---

## CR1b `[Claude]` — `evaluate_roll_csp` + `CSPRollExecutor` + full CSP automation

**Files:**
- `src/strategy/exit_signals.py` (add `evaluate_roll_csp`)
- `src/strategy/csp_roll_executor.py` (new)
- `src/strategy/csp_nifty_v1.py` (store broker; wire `CLOSE_AND_ROLL`)
- `tests/unit/strategy/test_exit_signals.py` (extend)
- `tests/unit/strategy/test_csp_roll_executor.py` (new)
- `tests/unit/strategy/test_csp_nifty_v1.py` (extend)

**Prerequisite:** CR1a committed — `src/instruments/strike_selector.py` must exist.

**Before any code:**
- `get_code_snippet("ExitSignalEngine")` — confirm existing `evaluate_*` pattern
- `get_code_snippet("ExitSignalResult")` — field list; roll reuses this type
- `get_code_snippet("CSPNiftyV1.__init__")` — confirm `broker` param accepted but not stored
- `get_code_snippet("_close_csp_leg")` — exact signature from `paper_csp_roll.py`
- `get_code_snippet("_open_new_csp_leg")` — exact signature from `paper_csp_roll.py`
- `search_graph("CSPRollExecutor")` — confirm does NOT yet exist

**Part 1 — `evaluate_roll_csp` in `ExitSignalEngine`:**

```python
@classmethod
def evaluate_roll_csp(cls, *, dte: int) -> list[ExitSignalResult]:
    """Evaluate whether the CSP leg is eligible to roll.

    Triggers when dte <= 5. Returns a single ROLL_ELIGIBLE ACTION result.
    Returns [] when dte > 5 — no roll needed yet.

    Strike and expiry selection are delegated to CSPRollExecutor at
    execution time. This function only detects the trigger condition.

    Args:
        dte: Days to expiry of the short put leg.

    Returns:
        List with one ROLL_ELIGIBLE result, or empty list.
    """
    if dte <= 5:
        return [
            ExitSignalResult(
                exit_signal="ROLL_ELIGIBLE",
                severity="ACTION",
                threshold_value=5.0,
                notes=f"DTE {dte} ≤ 5 — close and reopen via strike_selector",
            )
        ]
    return []
```

**Part 2 — `src/strategy/csp_roll_executor.py`:**

Extract `_close_csp_leg` and `_open_new_csp_leg` from `paper_csp_roll.py` as public
functions `close_csp_leg` and `open_new_csp_leg`. Signatures unchanged — just made
public (remove leading underscore) and moved to `src/strategy/`.

```python
async def close_csp_leg(
    broker: BrokerClient,
    store: PaperStore,
    existing: PaperTrade,
    roll_date: date,
    dry_run: bool,
) -> PaperTrade: ...

async def open_new_csp_leg(
    broker: BrokerClient,
    store: PaperStore,
    lookup: InstrumentLookup,
    strategy: str,
    roll_date: date,
    dry_run: bool,
    quantity: int,
    index: int = 0,
) -> PaperTrade: ...
```

**Part 3 — `CSPNiftyV1` changes:**

In `__init__`, store broker: `self._broker = broker` (currently accepted but discarded).

In `check_signals()`, after the existing `evaluate_csp` loop, call `evaluate_roll_csp`:
```python
roll_results = ExitSignalEngine.evaluate_roll_csp(dte=dte)
for result in roll_results:
    events.append(
        SignalEvent(
            event_type=result.exit_signal,
            severity=result.severity,
            description=result.notes or result.exit_signal,
            payload={"leg_role": pos.leg_role, "dte": dte, "valid_actions": ["CLOSE_AND_ROLL", "CLOSE_FULL"]},
        )
    )
```

In `apply_action`, handle `CLOSE_AND_ROLL`:
```python
if action.action_type == "CLOSE_AND_ROLL":
    # atomically close existing leg and open new one
    await close_csp_leg(self._broker, self._store, existing_trade, today, dry_run=False)
    await open_new_csp_leg(self._broker, self._store, self._lookup, self.strategy_name, today, dry_run=False, quantity=existing_trade.quantity)
```
Rollback on failure: if `open_new_csp_leg` raises, call `self._store.delete_trade(close_trade)`.

**Tests:**

`test_exit_signals.py` additions:
- `evaluate_roll_csp(dte=5)` → one `ROLL_ELIGIBLE` ACTION result
- `evaluate_roll_csp(dte=4)` → one `ROLL_ELIGIBLE` ACTION result
- `evaluate_roll_csp(dte=6)` → `[]`
- `evaluate_roll_csp(dte=0)` → one `ROLL_ELIGIBLE` ACTION result (edge: expiry day)

`test_csp_roll_executor.py`:
- `close_csp_leg` with `dry_run=True` → returns trade, does not call `store.record_trade`
- `close_csp_leg` with `dry_run=False` → calls `store.record_trade` once
- `open_new_csp_leg` with `dry_run=True` → returns trade, does not call `store.record_trade`
- `open_new_csp_leg` with no expiry candidates → raises `ValueError`

`test_csp_nifty_v1.py` additions:
- `dte=4` position → `ROLL_ELIGIBLE` in signals alongside any exit signals
- `dte=6` position → no `ROLL_ELIGIBLE`
- `apply_action("CLOSE_AND_ROLL")` → calls `close_csp_leg` then `open_new_csp_leg`
- `open_new_csp_leg` raises → `delete_trade` called (rollback)

**Commit:** `feat(strategy): evaluate_roll_csp + CSPRollExecutor + CLOSE_AND_ROLL in CSPNiftyV1`

---

## CR1c `[Antigravity]` — Refactor `paper_csp_roll.py` to thin CLI wrapper

**Files:**
- `scripts/strategies/csp/paper_csp_roll.py`
- `tests/unit/scripts/test_paper_csp_roll.py` (update imports if needed)

**Prerequisite:** CR1b committed — `src/strategy/csp_roll_executor.py` must exist.

**Before any code:**
- `get_code_snippet("_close_csp_leg")` — confirm it is still in `paper_csp_roll.py` (CR1b moved it to executor but the script still has the old copy until this task)
- `get_code_snippet("_open_new_csp_leg")` — same
- `get_code_snippet("close_csp_leg")` — confirm CR1b's public version exists in `csp_roll_executor.py`

**What to change:**

Replace `_close_csp_leg` and `_open_new_csp_leg` function bodies in `paper_csp_roll.py`
with imports and delegation:

```python
from src.strategy.csp_roll_executor import close_csp_leg, open_new_csp_leg

async def _close_csp_leg(...):   # thin wrapper kept for backward compat
    return await close_csp_leg(...)

async def _open_new_csp_leg(...):
    return await open_new_csp_leg(...)
```

Or remove the wrappers entirely and update all callers in the script to use the imported
names directly — whichever is cleaner given the call sites.

Also update the import at line 48 (already changed by CR1a):
```python
# Already done in CR1a — no change needed here
from src.instruments.strike_selector import filter_strikes_by_delta, rank_strikes
```

**Tests:** existing `paper_csp_roll.py` tests must remain green — no behaviour change.

**Commit:** `refactor(scripts): paper_csp_roll delegates close/open to csp_roll_executor`

---

## CR2 `[Antigravity]` — `evaluate_roll_overlay()` in `ExitSignalEngine`

**Files:** `src/strategy/exit_signals.py`, `tests/unit/strategy/test_exit_signals.py`

**Prerequisite:** CR1b committed — confirm `evaluate_roll_csp` pattern before implementing.

**Before any code:**
- `get_code_snippet("ExitSignalEngine")` — confirm CR1b pattern: `evaluate_roll_csp` returns `list[ExitSignalResult]`
- `get_code_snippet("ExitSignalResult")` — field list; roll reuses this type
- `search_code("BASE_ROLL_ROLES")` in `scripts/` — confirm base role names

**What to implement:**

```python
_OVERLAY_SHORT_CALL_ROLES = {"cc_short_call", "collar_short_call"}
_OVERLAY_LONG_PUT_ROLES = {"pp_long_put", "collar_long_put"}
_OVERLAY_STRIKE_OFFSET = 50   # points
_BASE_DTE_GUARD = 10          # if base DTE <= this, block overlay roll

@classmethod
def evaluate_roll_overlay(
    cls,
    *,
    leg_role: str,
    dte: int,
    base_dte: int,
    atm_strike: int,
) -> list[ExitSignalResult]:
    """Evaluate whether an overlay leg is eligible to roll.

    Triggers when dte <= 5.
    If base_dte <= _BASE_DTE_GUARD: returns ROLL_BASE_FIRST WARN.
    Otherwise: returns ROLL_ELIGIBLE ACTION with suggested strike in notes.

    Strike suggestion (advisory — actual selection via strike_selector):
      short call roles: ATM + 50
      long put roles:   ATM - 50

    Args:
        leg_role: One of the known overlay leg roles.
        dte: Days to expiry of the overlay leg.
        base_dte: Days to expiry of the base position.
        atm_strike: Current ATM strike (nearest 50-point to spot).

    Returns:
        List with one result, or [] when dte > 5.

    Raises:
        ValueError: When leg_role is not a known overlay role.
    """
```

If `leg_role` not in `_OVERLAY_SHORT_CALL_ROLES | _OVERLAY_LONG_PUT_ROLES` → raise `ValueError`.

Base-DTE guard result:
```python
ExitSignalResult(
    exit_signal="ROLL_BASE_FIRST",
    severity="WARN",
    threshold_value=float(_BASE_DTE_GUARD),
    notes=f"Base DTE {base_dte} ≤ {_BASE_DTE_GUARD} — roll base first",
)
```

Roll eligible result (short call):
```python
ExitSignalResult(
    exit_signal="ROLL_ELIGIBLE",
    severity="ACTION",
    threshold_value=5.0,
    notes=f"DTE {dte} ≤ 5 — suggested strike {atm_strike + _OVERLAY_STRIKE_OFFSET}",
)
```

**Tests (extend `tests/unit/strategy/test_exit_signals.py`):**
- CC leg, `dte=4`, `base_dte=25` → `ROLL_ELIGIBLE` ACTION; notes contains `atm_strike + 50`
- PP leg, `dte=4`, `base_dte=25` → `ROLL_ELIGIBLE` ACTION; notes contains `atm_strike - 50`
- `dte=6` → `[]`
- `base_dte=8` → `ROLL_BASE_FIRST` WARN
- `base_dte=11` → `ROLL_ELIGIBLE` (guard does not fire)
- Unknown `leg_role` → `ValueError`
- Collar short call → same result as CC
- Collar long put → same result as PP

**Commit:** `feat(strategy): add evaluate_roll_overlay to ExitSignalEngine with base-DTE guard`

---

## CR3 `[Claude]` — Wire roll signals into strategies

**Files:** `src/strategy/csp_nifty_v1.py` (already done in CR1b for CSP),
`src/strategy/nifty_track_comparison_v1.py`,
`tests/unit/strategy/test_nifty_track_comparison_v1.py`

**Prerequisite:** CR2 committed — `evaluate_roll_overlay` must exist.

**Before any code:**
- `get_code_snippet("NiftyTrackComparisonV1.check_signals")` — current WARN emit logic for `ROLL_DUE_DTE`
- `get_code_snippet("evaluate_roll_overlay")` — CR2 signature

**3-track changes (`nifty_track_comparison_v1.py`):**

When DTE ≤ 5, replace `ROLL_DUE_DTE` WARN emission with a call to
`ExitSignalEngine.evaluate_roll_overlay(leg_role, dte, base_dte, atm_strike)`:

- If `ROLL_ELIGIBLE` ACTION → emit `SignalEvent(event_type="ROLL_ELIGIBLE", severity="ACTION", ..., payload={..., "valid_actions": ["RECORD_ROLL"]})`
- If `ROLL_BASE_FIRST` WARN → keep as WARN (same as current `ROLL_DUE_DTE`)
- DTE 6–10: keep existing `ROLL_DUE_DTE` WARN unchanged

**Tests:**
- Overlay leg `dte=4`, `base_dte=25` → `ROLL_ELIGIBLE` ACTION in signals
- Overlay leg `dte=8` → `ROLL_DUE_DTE` WARN (unchanged)
- `base_dte=8` → `ROLL_BASE_FIRST` WARN; no `ROLL_ELIGIBLE`
- Healthy overlay (`dte=20`) → `[]`

**Commit:** `feat(strategy): wire evaluate_roll_overlay into NiftyTrackComparisonV1`

---

## CR4 `[Claude]` — Docs close (MUST BE LAST)

**Files:** `DECISIONS.md`, `CONTEXT.md`, `TODOS.md`, `docs/plan/council-refactor/tasks.md`

**No code changes.**

**DECISIONS.md — update paper-backbone entry (2026-06-02, PB):**

Correct the line: *"RapidCouncil … used by the executor for ambiguous sizing decisions"* →
append: *"Note (2026-06-04, CR): RapidCouncil is NOT wired into the paper trading
approval path. The daemon approval flow bypassed it from the start (signature mismatch
bug fixed in CR0). Roll decisions are deterministic (evaluate_roll_csp /
evaluate_roll_overlay in ExitSignalEngine) and backtestable. Council is retained as a
module for future live trading use only — see docs/plan/council-refactor/prompt.md."*

**DECISIONS.md — add new entry:**

```
**RapidCouncil removed from paper trading path (2026-06-04, CR):**
RapidCouncil is not called in any Phase 0 paper trading flow. Reasons:
(1) Paper trading exits are single-option decisions — the action is determined by
ExitSignalEngine before a council could be consulted. (2) Roll decisions must be
deterministic and backtestable — LLM outputs are non-deterministic across runs and
model versions, and cannot be replayed against historical data without hindsight bias.
(3) A signature mismatch between StrategyMonitor and TelegramGateway meant the council
was bypassed anyway (fixed in CR0). Deterministic roll rules: evaluate_roll_csp()
uses IVR-tiered strike offsets (ATM / ATM−50 / ATM−100); evaluate_roll_overlay() uses
a fixed 50-point offset from ATM with a base-DTE guard. Both are pure functions in
ExitSignalEngine. Council wiring belongs in Phase 1 live trading for IC leg-selective
exits and novel signals outside the codified rule set.
```

**CONTEXT.md — update `src/strategy/` entry:**
Append to ExitSignalEngine description: `RollSignalResult` dataclass +
`evaluate_roll_csp()` (IVR-tiered: ATM / ATM−50 / ATM−100; delta floor 0.30) +
`evaluate_roll_overlay()` (CC = ATM+50, PP = ATM−50, base-DTE guard ≤ 10).
Update `CSPNiftyV1` description: now emits `ROLL_ELIGIBLE` ACTION via `evaluate_roll_csp`.
Update `NiftyTrackComparisonV1`: `ROLL_DUE_DTE` at DTE ≤ 5 promoted to ACTION (`ROLL_ELIGIBLE`).

**Commit:** `docs(strategy): document council removal from paper trading path and deterministic roll rules`

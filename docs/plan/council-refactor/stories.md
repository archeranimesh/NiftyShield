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

## CR1 `[Claude]` — `evaluate_roll_csp()` in `ExitSignalEngine` + `RollSignalResult`

**Files:** `src/strategy/exit_signals.py`, `tests/unit/strategy/test_exit_signals_roll.py`

**Before any code:**
- `get_code_snippet("ExitSignalEngine")` — confirm existing evaluate_* method pattern
- `get_code_snippet("ExitSignalResult")` — field list; `RollSignalResult` follows same pattern
- `get_code_snippet("get_expiry_candidates")` — confirm signature and return shape
- `search_graph("RollSignalResult")` — confirm does NOT yet exist

**What to implement:**

Add to `src/strategy/exit_signals.py`:

```python
@dataclass(frozen=True)
class RollSignalResult:
    """Deterministic roll recommendation from ExitSignalEngine.

    Returned by evaluate_roll_csp and evaluate_roll_overlay.
    None is returned (not this dataclass) when a roll is blocked.
    """
    signal: str          # "ROLL_ELIGIBLE" | "ROLL_BASE_FIRST"
    severity: str        # "ACTION" | "WARN"
    proposed_strike: int | None      # None when signal == "ROLL_BASE_FIRST"
    proposed_expiry: str | None      # ISO date string; None when blocked
    ivr_tier: str | None # "low" | "standard" | "aggressive" | None
    reason: str          # human-readable rationale for Telegram message
```

Add to `ExitSignalEngine`:

```python
IVR_TIER_THRESHOLDS = {
    "low":        (0.25, 0.35),   # ATM
    "standard":   (0.35, 0.50),   # ATM - 50
    "aggressive": (0.50, None),   # ATM - 100
}

CSP_ROLL_DELTA_FLOOR = Decimal("0.30")   # never roll below this delta

def evaluate_roll_csp(
    self,
    days_held: int,
    dte: int,
    ivr: float | None,
    spot: Decimal,
    atm_strike: int,
    expiry_candidates: list[dict],  # from get_expiry_candidates(); each has "expiry" and "dte"
) -> RollSignalResult | None:
    """Return deterministic CSP roll recommendation, or None if R3 blocks.

    Triggers when days_held >= 21 OR dte <= 5.
    IVR < 0.25 → return None (R3 blocks roll; caller emits no signal).
    IVR None   → return None with reason "IVR unavailable — cannot verify R3".

    Strike selection is IVR-tiered. Delta floor (0.30) overrides tier if needed.
    Expiry selection: first candidate with DTE in [21, 35]; expand to [35, 50] if none.
    """
```

**IVR tier → strike offset mapping:**

```python
_IVR_STRIKE_OFFSET: list[tuple[float, int, str]] = [
    # (ivr_floor, strike_offset_from_atm, tier_label)
    (0.50, -100, "aggressive"),
    (0.35,  -50, "standard"),
    (0.25,    0, "low"),
]
# IVR < 0.25 → return None (blocked)
```

Walk the list top-down; first threshold where `ivr >= ivr_floor` wins.
After selecting the raw strike, verify `|delta_at_strike| ≤ CSP_ROLL_DELTA_FLOOR`.
If breached, step the strike up by 50 until the constraint is satisfied or ATM is reached.
(Delta lookup is not performed inside this engine — pass `None` for now; document that
callers should validate delta post-recommendation before recording the trade. This keeps
the engine pure and avoids requiring a live chain reference.)

**Tests (`tests/unit/strategy/test_exit_signals_roll.py`):**

Build a minimal `expiry_candidates` fixture: list of dicts with `expiry` (ISO date) and
`dte` (int). Use `get_code_snippet("get_expiry_candidates")` first — confirm actual return shape.

- `days_held=21, dte=20, ivr=0.40` → `ROLL_ELIGIBLE` ACTION; tier=`standard`; strike = ATM − 50
- `days_held=10, dte=4, ivr=0.40` → `ROLL_ELIGIBLE` ACTION; DTE ≤ 5 triggers
- `days_held=10, dte=10, ivr=0.40` → `None` (no trigger condition met)
- `ivr=0.60, days_held=21` → tier=`aggressive`; strike = ATM − 100
- `ivr=0.28, days_held=21` → tier=`low`; strike = ATM (no offset)
- `ivr=0.22, days_held=21` → `None` (R3 blocks)
- `ivr=None, days_held=21` → `None`; reason contains "IVR unavailable"
- `proposed_expiry` is within the 21–35 DTE window from candidates
- No candidate in 21–35 DTE → picks from 35–50 DTE window
- `RollSignalResult` is frozen — mutation raises

**Commit:** `feat(strategy): add evaluate_roll_csp to ExitSignalEngine with IVR-tiered strike selection`

---

## CR2 `[Antigravity]` — `evaluate_roll_overlay()` in `ExitSignalEngine`

**Files:** `src/strategy/exit_signals.py`, `tests/unit/strategy/test_exit_signals_roll.py`

**Before any code:**
- `get_code_snippet("ExitSignalEngine")` — confirm CR1 is committed first
- `get_code_snippet("RollSignalResult")` — field list from CR1
- `search_code("BASE_ROLL_ROLES")` in `scripts/` — confirm `{"base_futures", "base_ditm_call"}`
- `get_code_snippet("get_expiry_candidates")` — confirm import path

**What to implement:**

```python
OVERLAY_STRIKE_OFFSET = 50      # points; CC = ATM + offset, PP = ATM - offset
BASE_DTE_GUARD = 10             # if base DTE <= this, block overlay roll

def evaluate_roll_overlay(
    self,
    leg_role: str,              # "cc_short_call" | "pp_long_put" | "collar_short_call" | "collar_long_put"
    dte: int,                   # DTE of the overlay leg
    base_dte: int,              # DTE of the base position (futures / DITM call)
    atm_strike: int,
    expiry_candidates: list[dict],
) -> RollSignalResult | None:
    """Return deterministic overlay roll recommendation.

    Triggers when dte <= 5.
    If base_dte <= BASE_DTE_GUARD: return RollSignalResult(signal="ROLL_BASE_FIRST",
    severity="WARN", proposed_strike=None, proposed_expiry=None, ivr_tier=None,
    reason="Base DTE={base_dte} — roll base first before rolling overlay").

    Strike offsets:
      - short call roles: ATM + OVERLAY_STRIKE_OFFSET
      - long put roles:   ATM - OVERLAY_STRIKE_OFFSET

    Expiry: next monthly Tuesday from expiry_candidates.
    If base DTE <= 60: align overlay expiry to base expiry (not next monthly).
    """
```

Short call roles: `{"cc_short_call", "collar_short_call"}`.
Long put roles: `{"pp_long_put", "collar_long_put"}`.
Unknown `leg_role` → raise `ValueError`.

**Tests (extend `test_exit_signals_roll.py`):**
- CC leg, DTE=4, base_dte=25 → `ROLL_ELIGIBLE` ACTION; strike = ATM + 50
- PP leg, DTE=4, base_dte=25 → `ROLL_ELIGIBLE` ACTION; strike = ATM − 50
- DTE=6 → `None` (not triggered)
- base_dte=8 → `ROLL_BASE_FIRST` WARN; `proposed_strike=None`
- base_dte=45 → overlay expiry = next monthly Tuesday
- base_dte=50 → overlay expiry aligned to base expiry (base DTE ≤ 60)
- Unknown `leg_role` → `ValueError`
- Collar short call → same as CC (ATM + 50)
- Collar long put → same as PP (ATM − 50)

**Commit:** `feat(strategy): add evaluate_roll_overlay to ExitSignalEngine with base-DTE guard`

---

## CR3 `[Claude]` — Wire roll signals into strategies

**Files:** `src/strategy/csp_nifty_v1.py`, `src/strategy/nifty_track_comparison_v1.py`,
`tests/unit/strategy/test_csp_nifty_v1.py`,
`tests/unit/strategy/test_nifty_track_comparison_v1.py`

**Before any code:**
- `get_code_snippet("CSPNiftyV1.check_signals")` — insertion point after existing signal checks
- `get_code_snippet("NiftyTrackComparisonV1.check_signals")` — current WARN emit logic
- `get_code_snippet("evaluate_roll_csp")` — CR1 must be committed
- `get_code_snippet("evaluate_roll_overlay")` — CR2 must be committed

**CSP changes (`csp_nifty_v1.py`):**

In `check_signals()`, after the existing exit signal evaluation, call
`engine.evaluate_roll_csp(days_held, dte, ivr, spot, atm_strike, expiry_candidates)`.

If result is not `None` and `result.signal == "ROLL_ELIGIBLE"`:
```python
SignalEvent(
    event_type="ROLL_ELIGIBLE",
    severity="ACTION",
    description=result.reason,
    payload={
        "proposed_strike": result.proposed_strike,
        "proposed_expiry": result.proposed_expiry,
        "ivr_tier": result.ivr_tier,
        "action_options": ["RECORD_ROLL"],   # CR0 convention
    },
)
```

Note: `evaluate_roll_csp` requires `expiry_candidates` — call
`get_expiry_candidates("NIFTY", today)` once in `check_signals` and pass through.
If `get_expiry_candidates` raises or returns empty, log WARNING and skip roll check.

**3-track changes (`nifty_track_comparison_v1.py`):**

Existing behaviour: `ROLL_DUE_DTE` is emitted as WARN for DTE ≤ 5.
Change: when DTE ≤ 5, call `engine.evaluate_roll_overlay(leg_role, dte, base_dte,
atm_strike, expiry_candidates)` and emit the result as ACTION:

```python
SignalEvent(
    event_type="ROLL_ELIGIBLE",
    severity="ACTION",
    description=result.reason,
    payload={
        "proposed_strike": result.proposed_strike,
        "proposed_expiry": result.proposed_expiry,
        "leg_role": leg_role,
        "action_options": ["RECORD_ROLL"],
    },
)
```

If result is `ROLL_BASE_FIRST`, keep it as WARN (severity unchanged from current WARN).
DTE 6–10 range: keep `ROLL_DUE_DTE` as WARN (no roll recommendation yet — advisory only).

`ExitSignalEngine` instance: inject at construction time via `CSPNiftyV1(engine=ExitSignalEngine())`
and `NiftyTrackComparisonV1(engine=ExitSignalEngine())`. Do not instantiate inside `check_signals`.
Update daemon startup in `monitor_daemon.py` accordingly.

**Tests — CSP:**
- `days_held=21, dte=20, ivr=0.40` → `ROLL_ELIGIBLE` ACTION in returned signals
- `ivr=0.22` → no `ROLL_ELIGIBLE` (R3 blocks); other exit signals unaffected
- `days_held=10, dte=4, ivr=0.40` → `ROLL_ELIGIBLE` ACTION (DTE trigger)
- `get_expiry_candidates` raises → `ROLL_ELIGIBLE` absent; no exception propagated

**Tests — 3-track:**
- Overlay leg DTE=4, base_dte=25 → `ROLL_ELIGIBLE` ACTION replaces `ROLL_DUE_DTE` WARN
- Overlay leg DTE=8 → `ROLL_DUE_DTE` WARN (unchanged)
- base_dte=8 → `ROLL_BASE_FIRST` WARN; no `ROLL_ELIGIBLE`
- Healthy overlay (DTE 20) → `[]`

**Commit:** `feat(strategy): wire evaluate_roll_csp and evaluate_roll_overlay into CSPNiftyV1 and NiftyTrackComparisonV1`

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

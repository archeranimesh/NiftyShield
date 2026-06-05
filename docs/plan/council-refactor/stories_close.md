# council-refactor — Docs Close

> **MUST BE LAST.** Run only after all other stories are committed and tests are green.

---

## CR4 `[Claude]` — Docs close

**Files:** `DECISIONS.md`, `CONTEXT.md`, `TODOS.md`, `docs/plan/council-refactor/tasks.md`

**No code changes.**

**Before writing:**
- `git log --oneline -20` — verify all story SHAs present
- `python -m pytest tests/unit/ --tb=no -q` — all green

---

### DECISIONS.md — append to paper-backbone entry (2026-06-02, PB):

> "Note (council-refactor, CR): RapidCouncil is NOT wired into the paper trading approval path.
> CSP and CC exits are deterministic (ExitSignalEngine classmethods) and backtestable.
> Council is retained for future live trading use only."

### DECISIONS.md — add new entries:

```
**RapidCouncil removed from paper trading path (council-refactor, CR):**
Not called in any Phase 0 paper trading flow. Reasons:
(1) CSP/CC exits are single-option decisions — action determined by ExitSignalEngine before
council could be consulted. (2) Roll decisions must be deterministic and backtestable —
LLM outputs are non-deterministic and cannot be replayed against historical data without
hindsight bias. (3) A signature mismatch between StrategyMonitor and TelegramGateway meant
the council was bypassed anyway (CR0). Council wiring belongs in Phase 1 live trading only.

**CSP always-open design (council-refactor, CR):**
CSP never truly closes — every exit cycles into a new position.
State machine: OPEN → DEFENDED (delta breach + roll) → RE_ENTRY_PENDING (any close) → OPEN.
Thresholds: profit target 70% (LTP ≤ 30% of entry), hard stop 2×, delta breach |δ| ≥ 0.40,
time stop 21 days, DTE roll ≤ 7. No second roll from DEFENDED state.

**CC automation design (council-refactor, CR):**
CC mirrors CSP signal structure. All ACTION signals map to CLOSE_CC (no roll variants —
covered nature removes assignment risk complexity). Re-entry gated by IVR ≥ 0.25 after
PROFIT_TARGET and TIME_STOP exits only; not after LOSS_STOP or DELTA_STOP (market moved
against position — reassess before re-entering). Strike selection: 4% OTM via
find_overlay_strikes.py.

**ReEntryMixin pattern (council-refactor, CR):**
Re-entry eligibility check extracted to ReEntryMixin. CSPNiftyV1 and CCOverlayV1 both
inherit it. Class attributes (reentry_leg_role, reentry_script_hint) customise behaviour
per strategy. Future strategies add re-entry gates by inheriting the mixin and overriding
two attributes. Gate changes (e.g., add ATR or regime filter) made once in the mixin.

**_PROFIT_TARGET_RETENTION shared constant (council-refactor, CR):**
Decimal("0.30") extracted as module constant in exit_signals.py. Shared by evaluate_csp
and evaluate_cc. Rationale: 70% decay threshold is strategy-agnostic for short premium
positions — separating CSP and CC constants would allow accidental drift.
```

---

### CONTEXT.md — update `src/strategy/` entry:

- `ExitSignalEngine`: five independent CSP classmethods (evaluate_profit_target_csp,
  evaluate_hard_stop_csp, evaluate_delta_breach_csp, evaluate_time_stop_csp,
  evaluate_roll_eligible_csp); updated evaluate_cc (TIME_STOP added, DTE_REVIEW replaces
  DTE_FORCED, _PROFIT_TARGET_RETENTION shared constant); evaluate_roll_overlay for 3-track overlays.
- `CSPNiftyV1`: always-open design, auto_execute=True, full state machine
  (OPEN/DEFENDED/RE_ENTRY_PENDING), three action types (CLOSE_AND_ROLL, ROLL_DOWN_AND_OUT,
  CLOSE_AND_WAIT). Inherits ReEntryMixin.
- `CCOverlayV1`: auto_execute=True, single action type (CLOSE_CC), inherits ReEntryMixin.
  Re-entry check on PROFIT_TARGET and TIME_STOP exits. Telegram notification after close.
- `ReEntryMixin` (`reentry_mixin.py`): three-gate re-entry check (DTE ≥ 14, IVR ≥ 0.25,
  no open position). Writes paper_exit_events row. Sends Telegram.
- `NiftyTrackComparisonV1`: ROLL_DUE_DTE at DTE ≤ 5 promoted to ACTION via evaluate_roll_overlay.
  auto_execute=False (overlay rolls require human confirmation).
- `StrategyMonitor`: auto-execute dispatch path for strategies with auto_execute=True.
  send_notification added to TelegramGateway for post-action informational messages.

### CONTEXT.md — update `src/paper/` entry:

- `PaperTrade`: `state: TradeState` field added.
- `TradeState` enum: OPEN / DEFENDED / RE_ENTRY_PENDING.
- `PaperStore`: `update_trade_state(trade_id, state)` added.

---

### tasks.md — tick all completed items, append SHAs.

**Commit:** `docs(council-refactor): close CR4 — DECISIONS, CONTEXT, TODOS updated`

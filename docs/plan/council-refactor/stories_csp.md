# council-refactor — CSP Roll Automation Stories

> Shared context, signal tables, state machine: `README.md`
> Prerequisite: CR0 committed (SHA: 4ce6d99)

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
- `get_code_snippet("_apply_liquidity_gate")` — confirm private helper
- `search_graph("strike_selector")` — confirm does NOT yet exist

**What to extract into `src/instruments/strike_selector.py`:**

Move verbatim from `scripts/lookup/find_strike_by_delta.py`:
- `filter_strikes_by_delta(chain_data, option_type, delta_min, delta_max) -> list[dict]`
- `_apply_liquidity_gate(rows) -> list[dict]`
- `rank_strikes(rows) -> list[dict]`

`find_strike_by_delta.py` becomes a thin CLI wrapper:
```python
from src.instruments.strike_selector import (
    filter_strikes_by_delta,
    _apply_liquidity_gate,
    rank_strikes,
)
```

`paper_csp_roll.py` import update:
```python
from src.instruments.strike_selector import filter_strikes_by_delta, rank_strikes
```

**Tests (`tests/unit/instruments/test_strike_selector.py`):**
- `filter_strikes_by_delta` with valid PE rows in range → returns subset
- `filter_strikes_by_delta` with no rows in delta range → returns `[]`
- `_apply_liquidity_gate` with low-OI row → filtered out
- `rank_strikes` with multiple rows → sorted; first row is best candidate
- `rank_strikes` with empty input → returns `[]`

**Commit:** `refactor(instruments): extract strike_selector from find_strike_by_delta; update imports`

---

## CR1b `[Claude]` — DB migration: `state` column + ExitSignalEngine full CSP signal set

**Files:**
- `src/paper/store.py` (expose `state` in `PaperTrade`; add `update_trade_state`)
- `src/paper/models.py` (add `state: TradeState` field to `PaperTrade`)
- `src/strategy/exit_signals.py` (add/update CSP signal functions)
- `scripts/dev/migrate_paper_trades_state.py` (new — one-time migration)
- `tests/unit/paper/test_paper_store.py` (extend)
- `tests/unit/strategy/test_exit_signals.py` (extend)

**Prerequisite:** CR1a committed.

**Before any code:**
- `get_code_snippet("PaperTrade")` — exact field list and types
- `get_code_snippet("ExitSignalEngine")` — existing evaluate_csp method signature
- `get_code_snippet("ExitSignalResult")` — field list
- `get_code_snippet("PaperStore.record_trade")` — confirm insert path

**Part 1 — `TradeState` enum and DB migration:**

Add to `src/paper/models.py`:
```python
class TradeState(str, Enum):
    OPEN = "OPEN"
    DEFENDED = "DEFENDED"
    RE_ENTRY_PENDING = "RE_ENTRY_PENDING"
```

Add `state: TradeState = TradeState.OPEN` to `PaperTrade`.

`scripts/dev/migrate_paper_trades_state.py`:
```sql
ALTER TABLE paper_trades ADD COLUMN state TEXT NOT NULL DEFAULT 'OPEN'
    CHECK(state IN ('OPEN','DEFENDED','RE_ENTRY_PENDING'));
UPDATE paper_trades SET state = 'OPEN';
```
Script is idempotent — checks if column exists before altering.

`PaperStore.update_trade_state(trade_id: int, state: TradeState) -> None`:
```sql
UPDATE paper_trades SET state = ? WHERE id = ?
```

**Part 2 — ExitSignalEngine: five independent CSP classmethods**

Replace the existing combined `evaluate_csp` with five independent classmethods.
Each returns `list[ExitSignalResult]` — empty list means signal did not fire.

```python
@classmethod
def evaluate_profit_target_csp(
    cls, *, ltp: Decimal, entry_credit: Decimal
) -> list[ExitSignalResult]:
    """Fire when 70% of entry credit has been captured (LTP ≤ 30% of entry).
    Uses module constant _PROFIT_TARGET_RETENTION = Decimal("0.30").
    """
    threshold = entry_credit * _PROFIT_TARGET_RETENTION
    if ltp <= threshold:
        return [ExitSignalResult(
            exit_signal="PROFIT_TARGET",
            severity="ACTION",
            threshold_value=float(threshold),
            notes=f"LTP {ltp} ≤ 30% of entry credit {entry_credit} (70% captured)",
        )]
    return []

@classmethod
def evaluate_hard_stop_csp(
    cls, *, ltp: Decimal, entry_credit: Decimal
) -> list[ExitSignalResult]:
    """Fire when LTP ≥ 2× entry credit."""
    threshold = entry_credit * Decimal("2.0")
    if ltp >= threshold:
        return [ExitSignalResult(
            exit_signal="HARD_STOP",
            severity="ACTION",
            threshold_value=float(threshold),
            notes=f"LTP {ltp} ≥ 2× entry credit {entry_credit}",
        )]
    return []

@classmethod
def evaluate_delta_breach_csp(
    cls, *, delta: float, state: TradeState
) -> list[ExitSignalResult]:
    """Fire when |delta| ≥ 0.40.
    OPEN state → DELTA_BREACH (roll down and out).
    DEFENDED state → DELTA_BREACH_FINAL (close and wait).
    Raises ValueError if state is RE_ENTRY_PENDING.
    """
    if state == TradeState.RE_ENTRY_PENDING:
        raise ValueError("evaluate_delta_breach_csp called on RE_ENTRY_PENDING state")
    if abs(delta) >= 0.40:
        if state == TradeState.OPEN:
            return [ExitSignalResult(
                exit_signal="DELTA_BREACH",
                severity="ACTION",
                threshold_value=0.40,
                notes=f"delta {delta:.4f}: |δ| ≥ 0.40 — roll down and out",
            )]
        else:  # DEFENDED
            return [ExitSignalResult(
                exit_signal="DELTA_BREACH_FINAL",
                severity="ACTION",
                threshold_value=0.40,
                notes=f"delta {delta:.4f}: second breach in DEFENDED state — close and wait",
            )]
    return []

@classmethod
def evaluate_time_stop_csp(cls, *, days_held: int) -> list[ExitSignalResult]:
    """Fire when days_held ≥ 21."""
    if days_held >= 21:
        return [ExitSignalResult(
            exit_signal="TIME_STOP",
            severity="ACTION",
            threshold_value=21.0,
            notes=f"Days held {days_held} ≥ 21",
        )]
    return []

@classmethod
def evaluate_roll_eligible_csp(cls, *, dte: int) -> list[ExitSignalResult]:
    """Fire when DTE ≤ 7."""
    if dte <= 7:
        return [ExitSignalResult(
            exit_signal="ROLL_ELIGIBLE",
            severity="ACTION",
            threshold_value=7.0,
            notes=f"DTE {dte} ≤ 7 — close and reopen via strike_selector",
        )]
    return []
```

Module-level constant introduced here (also used by CC):
```python
_PROFIT_TARGET_RETENTION = Decimal("0.30")  # 70% decay; shared by CSP and CC
```

Remove the old combined `evaluate_csp` method. Update any callers in `CSPNiftyV1`.

**Tests (`tests/unit/strategy/test_exit_signals.py`):**

`evaluate_profit_target_csp`:
- `ltp=47.0, entry_credit=Decimal("158.6")` → fires (47 < 158.6 × 0.30 = 47.58)
- `ltp=48.0, entry_credit=Decimal("158.6")` → `[]`
- `ltp=Decimal("0"), entry_credit=Decimal("100")` → fires (zero LTP edge case)

`evaluate_hard_stop_csp`:
- `ltp=320.0, entry_credit=Decimal("158.6")` → fires (320 ≥ 317.2)
- `ltp=316.0, entry_credit=Decimal("158.6")` → `[]`

`evaluate_delta_breach_csp`:
- `delta=-0.41, state=OPEN` → `DELTA_BREACH` ACTION
- `delta=-0.41, state=DEFENDED` → `DELTA_BREACH_FINAL` ACTION
- `delta=-0.39, state=OPEN` → `[]`
- `delta=-0.40, state=OPEN` → fires (boundary inclusive)
- `state=RE_ENTRY_PENDING` → raises `ValueError`

`evaluate_time_stop_csp`:
- `days_held=21` → fires (boundary inclusive)
- `days_held=20` → `[]`

`evaluate_roll_eligible_csp`:
- `dte=7` → fires
- `dte=8` → `[]`
- `dte=0` → fires (expiry day)

`PaperStore.update_trade_state`:
- updates state; subsequent `get_trade` returns new state
- unknown `trade_id` → raises `InstrumentNotFoundError` or equivalent

**Commit:** `feat(paper,strategy): add TradeState + ExitSignalEngine full CSP signal set; 70% profit target`

---

## CR1c `[Antigravity]` — CSPRollExecutor + `paper_csp_roll.py` thin wrapper

**Files:**
- `src/strategy/csp_roll_executor.py` (new)
- `scripts/strategies/csp/paper_csp_roll.py` (thin wrapper)
- `tests/unit/strategy/test_csp_roll_executor.py` (new)

**Prerequisite:** CR1a (strike_selector) + CR1b (TradeState, PaperTrade.state) committed.

**Before any code:**
- `get_code_snippet("_close_csp_leg")` — exact signature from `paper_csp_roll.py`
- `get_code_snippet("_open_new_csp_leg")` — exact signature from `paper_csp_roll.py`
- `get_code_snippet("PaperTrade")` — confirm `state` field exists (CR1b gate)
- `get_code_snippet("filter_strikes_by_delta")` — confirm in `strike_selector` (CR1a gate)
- `search_graph("CSPRollExecutor")` — confirm does NOT yet exist

**What to implement in `src/strategy/csp_roll_executor.py`:**

```python
async def close_csp_leg(
    broker: BrokerClient,
    store: PaperStore,
    existing: PaperTrade,
    roll_date: date,
    dry_run: bool,
) -> PaperTrade:
    """Close an existing short put position at current market price."""
    ...

async def open_new_csp_leg(
    broker: BrokerClient,
    store: PaperStore,
    lookup: InstrumentLookup,
    strategy: str,
    roll_date: date,
    dry_run: bool,
    quantity: int,
    ivr: float | None = None,
    index: int = 0,
) -> PaperTrade:
    """Open a new short put leg using IVR-tiered strike selection.

    IVR tiers (advisory — strike_selector makes final pick):
      IVR < 0.25         → delta_min=0.18, delta_max=0.24
      IVR 0.25–0.50      → delta_min=0.20, delta_max=0.27
      IVR > 0.50         → delta_min=0.22, delta_max=0.30
    """
    ...

async def roll_down_and_out(
    broker: BrokerClient,
    store: PaperStore,
    lookup: InstrumentLookup,
    existing: PaperTrade,
    roll_date: date,
    ivr: float | None = None,
    dry_run: bool = False,
) -> tuple[PaperTrade, PaperTrade]:
    """Defensive roll: close existing leg, open new leg on next weekly expiry.

    Selects next weekly expiry (Tuesday, 7–14 DTE from roll_date).
    Falls back to expiry+1 week if no valid strike found on first attempt.
    Raises ValueError if no candidate passes liquidity gate after both attempts.
    Does NOT update trade state — caller is responsible for TradeState.DEFENDED.
    """
    ...
```

Logging: `structlog.get_logger("src.strategy.csp_roll_executor")` (explicit, not `__name__`).
Every close/open emits structured log with instrument_key, price, qty, realized_pnl, dry_run.

**Tests (`tests/unit/strategy/test_csp_roll_executor.py`):**
- `close_csp_leg(dry_run=True)` → returns trade, does not call `store.record_trade`
- `close_csp_leg(dry_run=False)` → calls `store.record_trade` once
- `open_new_csp_leg(dry_run=True)` → returns trade, no DB write
- `open_new_csp_leg` with no expiry candidates → raises `ValueError`
- `open_new_csp_leg` with IVR=0.10 → picks delta range 0.18–0.24
- `open_new_csp_leg` with IVR=0.60 → picks delta range 0.22–0.30
- `roll_down_and_out` happy path → returns (closed, new); new trade has next-weekly expiry
- `roll_down_and_out` no candidate on first expiry → tries +1 week
- `roll_down_and_out` no candidate on either → raises `ValueError`

**Commit:** `feat(strategy): CSPRollExecutor with close, open, roll_down_and_out; paper_csp_roll delegates`

---

## CR1d `[Claude]` — CSPNiftyV1 full automation + StrategyMonitor auto-execute

**Files:**
- `src/strategy/csp_nifty_v1.py`
- `src/strategy/protocol.py` (add `auto_execute` to `PaperStrategy`)
- `src/strategy/monitor.py` (auto-execute dispatch path)
- `src/notifications/telegram_gateway.py` (add `send_notification`)
- `tests/unit/strategy/test_csp_nifty_v1.py`
- `tests/unit/strategy/test_strategy_monitor.py`

**Prerequisite:** CR1b + CR1c committed. CC-3 committed (CSPNiftyV1 already inherits ReEntryMixin).

**Before any code:**
- `get_code_snippet("CSPNiftyV1")` — confirm ReEntryMixin inheritance from CC-3
- `get_code_snippet("CSPNiftyV1.apply_action")` — confirm _check_reentry calls on PROFIT_TARGET + TIME_STOP
- `get_code_snippet("PaperStrategy")` — protocol field list
- `get_code_snippet("StrategyMonitor._dispatch_event")` — post-CR0 dispatch logic
- `get_code_snippet("close_csp_leg")` — confirm in csp_roll_executor (CR1c gate)

**Part 1 — `PaperStrategy` protocol: add `auto_execute`**

```python
class PaperStrategy(Protocol):
    auto_execute: ClassVar[bool]  # True → StrategyMonitor calls apply_action directly
    ...
```

Default `False` on all existing strategies.

**Part 2 — `CSPNiftyV1` changes**

`auto_execute = True`

Store broker: `self._broker = broker`

`check_signals()` — priority-ordered, first match only:

```python
_SIGNAL_ACTION_MAP: dict[str, list[str]] = {
    "HARD_STOP":          ["CLOSE_AND_WAIT"],
    "DELTA_BREACH_FINAL": ["CLOSE_AND_WAIT"],
    "DELTA_BREACH":       ["ROLL_DOWN_AND_OUT"],
    "PROFIT_TARGET":      ["CLOSE_AND_ROLL"],
    "TIME_STOP":          ["CLOSE_AND_ROLL"],
    "ROLL_ELIGIBLE":      ["CLOSE_AND_ROLL"],
}
```

`apply_action()` — handles all four action types:
- `CLOSE_AND_ROLL` → `close_csp_leg` + `open_new_csp_leg`
- `ROLL_DOWN_AND_OUT` → `roll_down_and_out`; set state to DEFENDED
- `CLOSE_AND_WAIT` → `close_csp_leg`; set state to RE_ENTRY_PENDING
- `OPEN_NEW` → `open_new_csp_leg` (re-entry from RE_ENTRY_PENDING)

Rollback on `ROLL_DOWN_AND_OUT` failure: if open fails after close, call `store.delete_trade(closed)` before re-raising.

Re-entry loop (`_evaluate_reentry`): called when state=RE_ENTRY_PENDING or no open trade.
IVR + delta-range check → `REENTRY_ELIGIBLE` ACTION or `RE_ENTRY_BLOCKED` INFO.

**Part 3 — Telegram notification**

`send_notification` called after every `apply_action`. HTML format per action type (see full spec in original stories.md). Non-fatal.

**Part 4 — `StrategyMonitor` auto-execute dispatch**

```python
async def _dispatch_event(self, strategy, event):
    if event.severity != "ACTION":
        await self._notify_info(event)
        return

    if strategy.auto_execute and event.payload.get("auto_execute"):
        action = ApprovedAction(
            action_type=event.payload["auto_action"],
            rationale="auto-execute",
        )
        await strategy.apply_action(action)
        logger.info("auto_execute_dispatched", ...)
    else:
        # existing approval path
        action_options = list(event.payload.get("action_options", ["CLOSE_FULL"]))
        context_str = self._build_context(event)
        await self._notifier.send_approval_request(event, context_str, action_options)
```

**Part 5 — `TelegramGateway.send_notification`**

```python
async def send_notification(self, message: str) -> None:
    """Send plain HTML informational message; no keyboard. Non-fatal."""
```

**Tests:**

Signal priority:
- HARD_STOP + PROFIT_TARGET both true → only HARD_STOP emitted
- DELTA_BREACH (OPEN) + TIME_STOP both true → only DELTA_BREACH emitted
- Only PROFIT_TARGET true → emitted with `auto_action="CLOSE_AND_ROLL"`
- All false → `[]`

`apply_action`:
- `CLOSE_AND_ROLL` → close + open called; state stays OPEN on new trade
- `ROLL_DOWN_AND_OUT` → roll called; new trade state = DEFENDED
- `ROLL_DOWN_AND_OUT` open fails → delete_trade called on closed (rollback)
- `CLOSE_AND_WAIT` → close called; state = RE_ENTRY_PENDING
- `OPEN_NEW` → open called

Re-entry:
- state=RE_ENTRY_PENDING, valid candidates → `REENTRY_ELIGIBLE` ACTION
- state=RE_ENTRY_PENDING, no candidates → `RE_ENTRY_BLOCKED` INFO

Monitor:
- `auto_execute=True` + ACTION event → `apply_action` called directly
- `auto_execute=False` + ACTION event → `send_approval_request` called
- `auto_execute=True` but payload `auto_execute=False` → falls back to approval

**Commit:** `feat(strategy): CSPNiftyV1 full automation; StrategyMonitor auto-execute; CLOSE_AND_WAIT re-entry loop`

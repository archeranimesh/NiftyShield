# council-refactor — Story Specs

> One task per session. Find the first unchecked item in `tasks.md` **tagged for you**.
> Implementation rules: `CLAUDE.md` and `REVIEW.md`. After each task: tick `tasks.md`,
> append `| SHA: <sha>`, add one line to `TODOS.md`.

**Prerequisite check (run before CR0):**
```
search_graph("ExitSignalEngine")        # must exist
search_graph("StrategyMonitor")         # must exist
search_graph("CSPNiftyV1")             # must exist
search_code("send_approval_request")   # confirm mismatch in monitor.py vs telegram_gateway.py
```

---

## CSP State Machine (applies to CR1b, CR1c, CR1d)

Every `paper_trades` row for `paper_csp_nifty_v1` carries a `state` column:

```
OPEN ──── |delta| ≥ 0.40 (first breach) ──────► DEFENDED
  │                                                  │
  │  any CLOSE_AND_ROLL trigger fires               │  |delta| ≥ 0.40 (second breach)
  │  (PROFIT_TARGET, TIME_STOP, ROLL_ELIGIBLE)      │  OR HARD_STOP fires
  ▼                                                  │
RE_ENTRY_PENDING ◄────────────────────────────────────┘
  │
  │  entry conditions met at next EOD eval
  │  (strike_selector finds delta ∈ [0.20, 0.28])
  ▼
OPEN  ← strategy never truly closes; cycles continuously
```

**No second roll:** a position in `DEFENDED` state can only close — `ROLL_DOWN_AND_OUT`
is blocked. This prevents chasing a trending move with repeated defensive rolls.

**Re-entry condition after `CLOSE_AND_WAIT`:** identical to initial entry — run
`strike_selector` with IVR-tiered delta range. If a valid strike is found on next EOD
eval, open new position (state → `OPEN`). If not, emit `RE_ENTRY_BLOCKED` INFO and
stay in `RE_ENTRY_PENDING`.

---

## Signal Priority (CSP, evaluated each EOD)

When multiple signals fire on the same snapshot, **higher priority wins**.
Only the highest-priority signal is emitted as an event.

| Priority | Signal | Trigger condition | Action | Valid in state |
|---|---|---|---|---|
| 1 | `HARD_STOP` | LTP ≥ 2.0 × entry_credit | `CLOSE_AND_WAIT` | OPEN, DEFENDED |
| 2 | `DELTA_BREACH_FINAL` | \|delta\| ≥ 0.40 AND state = DEFENDED | `CLOSE_AND_WAIT` | DEFENDED |
| 3 | `DELTA_BREACH` | \|delta\| ≥ 0.40 AND state = OPEN | `ROLL_DOWN_AND_OUT` | OPEN |
| 4 | `PROFIT_TARGET` | LTP ≤ 0.30 × entry_credit | `CLOSE_AND_ROLL` | OPEN, DEFENDED |
| 5 | `TIME_STOP` | days_held ≥ 21 | `CLOSE_AND_ROLL` | OPEN, DEFENDED |
| 6 | `ROLL_ELIGIBLE` | DTE ≤ 7 | `CLOSE_AND_ROLL` | OPEN, DEFENDED |

**70% profit target:** capturing 70% means current LTP = 30% of original credit.
`threshold_value = 0.30 × entry_credit`; fires when `ltp ≤ threshold_value`.

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

This is a `TypeError` at runtime whenever any ACTION event fires.

**What to change:**

Refactor `TelegramGateway.send_approval_request` to:
```python
async def send_approval_request(
    self,
    event: SignalEvent,
    context_str: str,
    action_options: list[str],
) -> int | None:
```

Remove `CouncilOutput` import and parameter entirely.

Telegram message format:
```
<b>Action required — {strategy_name}</b>
Event: {event.event_type} ({event.severity})
{event.description}

<i>{context_str[:300]}</i>
```
Keyboard: one button per entry in `action_options`, plus "Reject All".
`callback_data` uses `approve:{index}` (0-based index into `action_options`).

Update `monitor._dispatch_event` to call:
```python
action_options = list(event.payload.get("action_options", ["CLOSE_FULL"]))
await self._notifier.send_approval_request(event, context_str, action_options)
```

`pending_approvals.council_output` column: rename to `action_options_json` in the
schema and in `PaperStore.create_approval`. Store `json.dumps(action_options)`.
The `on_approved` callback in `monitor_daemon.py` reads `action_options_json`,
picks `action_options[rank]`, builds `ApprovedAction` directly.

**Tests:**
- `send_approval_request(action_options=["CLOSE_FULL"])` → 2 buttons (1 approve + Reject All)
- `send_approval_request(action_options=["CLOSE_FULL", "CLOSE_AND_ROLL"])` → 3 buttons
- `send_approval_request` API failure → returns `None`; no exception propagated
- `_dispatch_event` ACTION event → `send_approval_request` called with `action_options` from payload
- `_dispatch_event` ACTION event missing `action_options` key → falls back to `["CLOSE_FULL"]`

**Commit:** `fix(strategy): remove CouncilOutput from approval flow; fix send_approval_request signature`

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

`find_strike_by_delta.py` becomes a thin CLI wrapper with imports:
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

**Prerequisite:** CR0 committed.

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
```python
# ALTER TABLE paper_trades ADD COLUMN state TEXT NOT NULL DEFAULT 'OPEN'
#     CHECK(state IN ('OPEN','DEFENDED','RE_ENTRY_PENDING'));
# UPDATE paper_trades SET state = 'OPEN';  # already defaulted, belt-and-suspenders
```
Script is idempotent — checks if column exists before altering.

`PaperStore.update_trade_state(trade_id: int, state: TradeState) -> None`:
```python
UPDATE paper_trades SET state = ? WHERE id = ?
```

**Part 2 — ExitSignalEngine: full CSP signal set**

Replace the existing combined CSP evaluate function with five independent classmethods.
Each returns `list[ExitSignalResult]` — empty list means signal did not fire.

```python
@classmethod
def evaluate_profit_target_csp(
    cls, *, ltp: Decimal, entry_credit: Decimal
) -> list[ExitSignalResult]:
    """Fire when 70% of entry credit has been captured (LTP ≤ 30% of entry).

    Args:
        ltp: Current last-traded price of the short put.
        entry_credit: Premium received at entry (positive value).

    Returns:
        List with one PROFIT_TARGET result, or [].
    """
    threshold = entry_credit * Decimal("0.30")
    if ltp <= threshold:
        return [ExitSignalResult(
            exit_signal="PROFIT_TARGET",
            severity="ACTION",
            threshold_value=float(threshold),
            notes=f"LTP {ltp} ≤ 30% of entry credit {entry_credit} (70% captured)",
        )]
    return []
```

```python
@classmethod
def evaluate_hard_stop_csp(
    cls, *, ltp: Decimal, entry_credit: Decimal
) -> list[ExitSignalResult]:
    """Fire when position has doubled against us (LTP ≥ 2× entry credit).

    Args:
        ltp: Current last-traded price of the short put.
        entry_credit: Premium received at entry (positive value).

    Returns:
        List with one HARD_STOP result, or [].
    """
    threshold = entry_credit * Decimal("2.0")
    if ltp >= threshold:
        return [ExitSignalResult(
            exit_signal="HARD_STOP",
            severity="ACTION",
            threshold_value=float(threshold),
            notes=f"LTP {ltp} ≥ 2× entry credit {entry_credit}",
        )]
    return []
```

```python
@classmethod
def evaluate_delta_breach_csp(
    cls, *, delta: float, state: TradeState
) -> list[ExitSignalResult]:
    """Fire when short put delta exceeds the breach threshold (|delta| ≥ 0.40).

    Returns DELTA_BREACH (OPEN state → roll down and out) or
    DELTA_BREACH_FINAL (DEFENDED state → close and wait, no further roll).

    Args:
        delta: Current delta of the short put leg (negative for puts, e.g. -0.42).
        state: Current trade state from paper_trades.state.

    Returns:
        List with one result, or [].

    Raises:
        ValueError: If state is RE_ENTRY_PENDING (no open position to evaluate).
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
```

```python
@classmethod
def evaluate_time_stop_csp(cls, *, days_held: int) -> list[ExitSignalResult]:
    """Fire when position has been held 21 or more days.

    Args:
        days_held: Calendar days since trade_date.

    Returns:
        List with one TIME_STOP result, or [].
    """
    if days_held >= 21:
        return [ExitSignalResult(
            exit_signal="TIME_STOP",
            severity="ACTION",
            threshold_value=21.0,
            notes=f"Days held {days_held} ≥ 21",
        )]
    return []
```

```python
@classmethod
def evaluate_roll_eligible_csp(cls, *, dte: int) -> list[ExitSignalResult]:
    """Fire when DTE ≤ 7 — time to close and roll into next cycle.

    Args:
        dte: Days to expiry of the short put leg.

    Returns:
        List with one ROLL_ELIGIBLE result, or [].
    """
    if dte <= 7:
        return [ExitSignalResult(
            exit_signal="ROLL_ELIGIBLE",
            severity="ACTION",
            threshold_value=7.0,
            notes=f"DTE {dte} ≤ 7 — close and reopen via strike_selector",
        )]
    return []
```

Remove the old combined `evaluate_csp` method if it exists. Update any callers.

**Tests (`tests/unit/strategy/test_exit_signals.py`):**

`evaluate_profit_target_csp`:
- `ltp=47.0, entry_credit=Decimal("158.6")` → fires (47 < 158.6 × 0.30 = 47.58)
- `ltp=48.0, entry_credit=Decimal("158.6")` → `[]` (48 > 47.58)
- `ltp=Decimal("0"), entry_credit=Decimal("100")` → fires (edge: zero LTP)

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
- updates state in DB; subsequent `get_trade` returns new state
- unknown `trade_id` → raises `InstrumentNotFoundError` or equivalent

**Commit:** `feat(paper,strategy): add TradeState + ExitSignalEngine full CSP signal set; 70% profit target`

---

## CR1c `[Antigravity]` — CSPRollExecutor + `paper_csp_roll.py` thin wrapper

**Files:**
- `src/strategy/csp_roll_executor.py` (new)
- `scripts/strategies/csp/paper_csp_roll.py` (thin wrapper)
- `tests/unit/strategy/test_csp_roll_executor.py` (new)
- `tests/unit/scripts/test_paper_csp_roll.py` (update imports if needed)

**Prerequisite:** CR1a (strike_selector) + CR1b (TradeState, PaperTrade.state) committed.

**Before any code:**
- `get_code_snippet("_close_csp_leg")` — exact signature from `paper_csp_roll.py`
- `get_code_snippet("_open_new_csp_leg")` — exact signature from `paper_csp_roll.py`
- `get_code_snippet("PaperTrade")` — confirm `state` field exists (CR1b gate)
- `get_code_snippet("filter_strikes_by_delta")` — confirm in `strike_selector` (CR1a gate)
- `search_graph("CSPRollExecutor")` — confirm does NOT yet exist

**What to implement in `src/strategy/csp_roll_executor.py`:**

Extract `_close_csp_leg` and `_open_new_csp_leg` from `paper_csp_roll.py` as public
functions. Add `roll_down_and_out`.

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

    IVR tiers for delta range (advisory — strike_selector makes final pick):
      IVR < 0.25  → delta_min=0.18, delta_max=0.24 (ATM-100 range)
      IVR 0.25–0.50 → delta_min=0.20, delta_max=0.27 (ATM-50 range)
      IVR > 0.50  → delta_min=0.22, delta_max=0.30 (ATM range)

    Raises:
        ValueError: If no valid strike candidate passes the liquidity gate.
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
    Falls back to expiry+1 week if no valid strike found on next expiry.
    Raises ValueError if no candidate passes liquidity gate after both attempts.

    Does NOT update trade state — caller (CSPNiftyV1.apply_action) is responsible
    for calling store.update_trade_state(new_trade.id, TradeState.DEFENDED).

    Returns:
        Tuple of (closed_trade, new_trade).
    """
    ...
```

**`paper_csp_roll.py` becomes a thin wrapper:**
```python
from src.strategy.csp_roll_executor import close_csp_leg, open_new_csp_leg

async def _close_csp_leg(...):
    return await close_csp_leg(...)

async def _open_new_csp_leg(...):
    return await open_new_csp_leg(...)
```
Or remove wrappers entirely and update callers in the script — whichever is cleaner.

**Tests (`tests/unit/strategy/test_csp_roll_executor.py`):**
- `close_csp_leg(dry_run=True)` → returns trade, does not call `store.record_trade`
- `close_csp_leg(dry_run=False)` → calls `store.record_trade` once
- `open_new_csp_leg(dry_run=True)` → returns trade, no DB write
- `open_new_csp_leg` with no expiry candidates → raises `ValueError`
- `open_new_csp_leg` with IVR=0.10 → picks delta range 0.18–0.24
- `open_new_csp_leg` with IVR=0.60 → picks delta range 0.22–0.30
- `roll_down_and_out` happy path → returns (closed, new); new trade has next-weekly expiry
- `roll_down_and_out` no candidate on next expiry → tries expiry+1
- `roll_down_and_out` no candidate on either expiry → raises `ValueError`

**Structured logging in executor functions:**

Every `close_csp_leg` and `open_new_csp_leg` call must emit a structured log entry.
Use `structlog.get_logger("src.strategy.csp_roll_executor")` (explicit name, not `__name__`).

`close_csp_leg` — log after DB write:
```python
logger.info(
    "csp_leg_closed",
    instrument_key=existing.instrument_key,
    leg_role=existing.leg_role,
    entry_price=str(existing.price),
    exit_price=str(exit_ltp),
    quantity=existing.quantity,
    realized_pnl=str(realized_pnl),
    dry_run=dry_run,
)
```

`open_new_csp_leg` — log after DB write:
```python
logger.info(
    "csp_leg_opened",
    instrument_key=new_trade.instrument_key,
    leg_role=new_trade.leg_role,
    price=str(new_trade.price),
    quantity=new_trade.quantity,
    delta=candidate_delta,
    ivr=ivr,
    dry_run=dry_run,
)
```

`roll_down_and_out` — log the full roll as a single event after both legs complete:
```python
logger.info(
    "csp_roll_down_and_out",
    closed_instrument=existing.instrument_key,
    closed_price=str(exit_ltp),
    new_instrument=new_trade.instrument_key,
    new_price=str(new_trade.price),
    new_delta=candidate_delta,
    ivr=ivr,
    dry_run=dry_run,
)
```

**Commit:** `feat(strategy): CSPRollExecutor with close, open, roll_down_and_out; paper_csp_roll delegates`

---

## CR1d `[Claude]` — CSPNiftyV1 full automation + StrategyMonitor auto-execute

**Files:**
- `src/strategy/csp_nifty_v1.py`
- `src/strategy/protocol.py` (add `auto_execute` to `PaperStrategy`)
- `src/strategy/monitor.py` (auto-execute dispatch path)
- `src/notifications/telegram_gateway.py` (add `send_notification`)
- `tests/unit/strategy/test_csp_nifty_v1.py` (full rewrite / extend)
- `tests/unit/strategy/test_strategy_monitor.py` (extend)

**Prerequisite:** CR1b (signals + TradeState) + CR1c (CSPRollExecutor) committed.

**Before any code:**
- `get_code_snippet("CSPNiftyV1.__init__")` — current broker/store/lookup params
- `get_code_snippet("CSPNiftyV1.check_signals")` — current signal detection logic
- `get_code_snippet("CSPNiftyV1.apply_action")` — current action handlers
- `get_code_snippet("PaperStrategy")` — protocol field list
- `get_code_snippet("StrategyMonitor._dispatch_event")` — post-CR0 dispatch logic

**Part 1 — `PaperStrategy` protocol: add `auto_execute`**

```python
class PaperStrategy(Protocol):
    auto_execute: ClassVar[bool]   # True → StrategyMonitor calls apply_action directly
    ...
```

Default: `False` on all existing strategies (no behaviour change).

**Part 2 — `CSPNiftyV1` changes**

Set class attribute: `auto_execute = True`

Store broker (currently discarded): `self._broker = broker`

`check_signals()` — replace existing signal detection with priority-ordered evaluation:

```python
async def check_signals(self) -> list[SignalEvent]:
    events: list[SignalEvent] = []
    open_trade = await self._store.get_open_trade(self.strategy_name)

    if open_trade is None or open_trade.state == TradeState.RE_ENTRY_PENDING:
        # Re-entry evaluation path
        reentry_event = await self._evaluate_reentry()
        if reentry_event:
            events.append(reentry_event)
        return events

    # Fetch live Greeks for the open position
    ltp, delta, dte = await self._fetch_market_data(open_trade)
    entry_credit = Decimal(open_trade.price)
    days_held = (date.today() - open_trade.trade_date).days

    # Priority-ordered signal evaluation — first match wins
    priority_checks = [
        ExitSignalEngine.evaluate_hard_stop_csp(ltp=ltp, entry_credit=entry_credit),
        ExitSignalEngine.evaluate_delta_breach_csp(delta=delta, state=open_trade.state),
        ExitSignalEngine.evaluate_profit_target_csp(ltp=ltp, entry_credit=entry_credit),
        ExitSignalEngine.evaluate_time_stop_csp(days_held=days_held),
        ExitSignalEngine.evaluate_roll_eligible_csp(dte=dte),
    ]
    for results in priority_checks:
        if results:
            result = results[0]
            action_options = _SIGNAL_ACTION_MAP[result.exit_signal]
            events.append(SignalEvent(
                event_type=result.exit_signal,
                severity=result.severity,
                description=result.notes or result.exit_signal,
                payload={
                    "trade_id": open_trade.id,
                    "leg_role": open_trade.leg_role,
                    "trade_state": open_trade.state.value,
                    "action_options": action_options,
                    "auto_execute": True,
                    "auto_action": action_options[0],  # deterministic choice
                },
            ))
            break  # emit only highest-priority signal

    return events
```

Signal → action mapping (module-level constant):
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

`apply_action()` — handle all action types:

```python
async def apply_action(self, action: ApprovedAction) -> None:
    open_trade = await self._store.get_open_trade(self.strategy_name)

    if action.action_type == "CLOSE_AND_ROLL":
        closed = await close_csp_leg(self._broker, self._store, open_trade, date.today(), dry_run=False)
        new_trade = await open_new_csp_leg(
            self._broker, self._store, self._lookup,
            self.strategy_name, date.today(), dry_run=False,
            quantity=open_trade.quantity, ivr=await self._fetch_ivr(),
        )
        # state already OPEN on new_trade (default)

    elif action.action_type == "ROLL_DOWN_AND_OUT":
        closed, new_trade = await roll_down_and_out(
            self._broker, self._store, self._lookup,
            open_trade, date.today(),
            ivr=await self._fetch_ivr(), dry_run=False,
        )
        await self._store.update_trade_state(new_trade.id, TradeState.DEFENDED)

    elif action.action_type == "CLOSE_AND_WAIT":
        await close_csp_leg(self._broker, self._store, open_trade, date.today(), dry_run=False)
        await self._store.update_trade_state(open_trade.id, TradeState.RE_ENTRY_PENDING)

    elif action.action_type == "OPEN_NEW":
        # Triggered by re-entry evaluation; opens fresh position
        await open_new_csp_leg(
            self._broker, self._store, self._lookup,
            self.strategy_name, date.today(), dry_run=False,
            quantity=self._default_quantity, ivr=await self._fetch_ivr(),
        )
```

Rollback on `ROLL_DOWN_AND_OUT` failure: if `roll_down_and_out` raises after closing,
call `store.delete_trade(closed_trade)` before re-raising. Log the rollback attempt.

Re-entry evaluation (`_evaluate_reentry`):
```python
async def _evaluate_reentry(self) -> SignalEvent | None:
    """Check if entry conditions are met to re-open position from RE_ENTRY_PENDING."""
    ivr = await self._fetch_ivr()
    delta_min, delta_max = _ivr_to_delta_range(ivr)
    chain_data = await self._broker.get_option_chain(...)
    candidates = filter_strikes_by_delta(chain_data, "PE", delta_min, delta_max)
    candidates = rank_strikes(candidates)
    if candidates:
        return SignalEvent(
            event_type="REENTRY_ELIGIBLE",
            severity="ACTION",
            description=f"Entry conditions met — top candidate delta {candidates[0]['delta']:.3f}",
            payload={"action_options": ["OPEN_NEW"], "auto_execute": True, "auto_action": "OPEN_NEW"},
        )
    return SignalEvent(
        event_type="RE_ENTRY_BLOCKED",
        severity="INFO",
        description="No valid strike in delta range — staying in RE_ENTRY_PENDING",
        payload={},
    )
```

**Part 3 — `CSPNiftyV1`: inject notifier + rich Telegram notification**

Add `notifier: TelegramGateway | None = None` to `CSPNiftyV1.__init__`. Store as
`self._notifier = notifier`.

Add `_build_trade_notification` private method. Called at end of each `apply_action`
path. Returns an HTML string for `send_notification`. Format per action type:

`CLOSE_AND_ROLL`:
```
🔄 <b>CSP: CLOSE_AND_ROLL</b>
📤 Closed: {instrument_key} @ ₹{exit_price:.2f}
   Entry ₹{entry_price:.2f} · P&amp;L <b>₹{realized_pnl:+,.0f}</b>
📥 Opened: {new_instrument_key} @ ₹{new_price:.2f}
   Delta {new_delta:.3f} · IVR {ivr:.2f}
State: OPEN ✓
```

`ROLL_DOWN_AND_OUT`:
```
⚠️ <b>CSP: ROLL_DOWN_AND_OUT</b>
📤 Closed: {instrument_key} @ ₹{exit_price:.2f}
   Entry ₹{entry_price:.2f} · P&amp;L <b>₹{realized_pnl:+,.0f}</b>
📥 Rolled to: {new_instrument_key} @ ₹{new_price:.2f}
   Delta {new_delta:.3f} · IVR {ivr:.2f}
State: OPEN → DEFENDED 🔶
```

`CLOSE_AND_WAIT`:
```
🔴 <b>CSP: CLOSE_AND_WAIT</b>
📤 Closed: {instrument_key} @ ₹{exit_price:.2f}
   Entry ₹{entry_price:.2f} · P&amp;L <b>₹{realized_pnl:+,.0f}</b>
State: → RE_ENTRY_PENDING 🔵
Monitoring for re-entry (δ ∈ [0.20, 0.28])
```

`OPEN_NEW` (re-entry):
```
🟢 <b>CSP: OPEN_NEW (re-entry)</b>
📥 Opened: {instrument_key} @ ₹{price:.2f}
   Delta {delta:.3f} · IVR {ivr:.2f} · DTE {dte}
State: RE_ENTRY_PENDING → OPEN ✓
```

Send via `self._notifier.send_notification(html)` if `self._notifier` is not None.
Non-fatal: wrap in `try/except` and log error, never raise to caller.

Also emit a **structured log entry** in `apply_action` after execution completes:
```python
logger.info(
    "csp_action_executed",
    strategy=self.strategy_name,
    action=action.action_type,
    closed_instrument=closed.instrument_key if closed else None,
    closed_price=str(exit_price) if closed else None,
    realized_pnl=str(realized_pnl) if closed else None,
    new_instrument=new_trade.instrument_key if new_trade else None,
    new_price=str(new_trade.price) if new_trade else None,
    state_before=state_before.value,
    state_after=state_after.value,
)
```

Use `structlog.get_logger("src.strategy.csp_nifty_v1")`.

**Part 4 — `StrategyMonitor` auto-execute dispatch**

In `_dispatch_event`, check `strategy.auto_execute` before routing:

```python
async def _dispatch_event(self, strategy: PaperStrategy, event: SignalEvent) -> None:
    if event.severity != "ACTION":
        await self._notify_info(event)
        return

    if strategy.auto_execute and event.payload.get("auto_execute"):
        # Auto-execute path: apply action directly; strategy sends its own notification
        action_type = event.payload["auto_action"]
        action = ApprovedAction(action_type=action_type, rationale="auto-execute")
        await strategy.apply_action(action)
        # Note: CSPNiftyV1.apply_action sends the rich Telegram notification itself.
        # Monitor only logs the dispatch here for audit trail.
        logger.info(
            "auto_execute_dispatched",
            strategy=strategy.strategy_name,
            event_type=event.event_type,
            action=action_type,
        )
    else:
        # Human approval path (existing)
        action_options = list(event.payload.get("action_options", ["CLOSE_FULL"]))
        context_str = self._build_context(event)
        await self._notifier.send_approval_request(event, context_str, action_options)
```

**Part 5 — `TelegramGateway.send_notification`**

```python
async def send_notification(self, message: str) -> None:
    """Send a plain HTML informational message (no inline keyboard).

    Uses HTML parse_mode (same as send_approval_request).
    Non-fatal: errors are logged and suppressed, never raised to caller.
    """
```

**Tests (`tests/unit/strategy/test_csp_nifty_v1.py`):**

Signal priority:
- HARD_STOP condition + PROFIT_TARGET both true → only HARD_STOP emitted
- DELTA_BREACH (state=OPEN) + TIME_STOP both true → only DELTA_BREACH emitted
- Only PROFIT_TARGET true → PROFIT_TARGET emitted with `auto_action="CLOSE_AND_ROLL"`
- All conditions false → `[]`

`apply_action`:
- `CLOSE_AND_ROLL` → calls `close_csp_leg` then `open_new_csp_leg`
- `ROLL_DOWN_AND_OUT` → calls `roll_down_and_out`; new trade state set to DEFENDED
- `ROLL_DOWN_AND_OUT` fails on open → `delete_trade` called on closed trade (rollback)
- `CLOSE_AND_WAIT` → calls `close_csp_leg`; trade state set to RE_ENTRY_PENDING
- `OPEN_NEW` → calls `open_new_csp_leg`

Re-entry:
- State=RE_ENTRY_PENDING, valid candidates → `REENTRY_ELIGIBLE` ACTION emitted
- State=RE_ENTRY_PENDING, no candidates → `RE_ENTRY_BLOCKED` INFO emitted
- State=None (no open trade) → re-entry evaluation runs (same as RE_ENTRY_PENDING)

Notification tests:
- `CLOSE_AND_ROLL` → `send_notification` called with HTML containing "CLOSE_AND_ROLL", closed instrument, new instrument
- `ROLL_DOWN_AND_OUT` → notification contains "DEFENDED" and "ROLL_DOWN_AND_OUT"
- `CLOSE_AND_WAIT` → notification contains "RE_ENTRY_PENDING"
- `OPEN_NEW` → notification contains "re-entry" and new instrument key
- `notifier=None` (not injected) → no error raised; action still executes

`StrategyMonitor` auto-execute tests:
- `auto_execute=True` strategy + ACTION event → `apply_action` called directly; monitor logs dispatch
- `auto_execute=False` strategy + ACTION event → `send_approval_request` called
- `auto_execute=True` but `event.payload["auto_execute"]=False` → falls back to approval path

**Commit:** `feat(strategy): CSPNiftyV1 full automation; StrategyMonitor auto-execute; CLOSE_AND_WAIT re-entry loop`

---

## CR2 `[Antigravity]` — `evaluate_roll_overlay()` in `ExitSignalEngine`

**Files:** `src/strategy/exit_signals.py`, `tests/unit/strategy/test_exit_signals.py`

**Prerequisite:** CR1b committed — `ExitSignalResult` field list confirmed.

**Before any code:**
- `get_code_snippet("ExitSignalEngine")` — confirm CR1b signals committed
- `get_code_snippet("ExitSignalResult")` — field list
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

    Raises:
        ValueError: When leg_role is not a known overlay role.
    """
```

If `leg_role` not in `_OVERLAY_SHORT_CALL_ROLES | _OVERLAY_LONG_PUT_ROLES` → raise `ValueError`.

Base-DTE guard result (WARN — no auto-execute):
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

**Tests:**
- CC leg, `dte=4`, `base_dte=25` → `ROLL_ELIGIBLE` ACTION; notes contain `atm_strike + 50`
- PP leg, `dte=4`, `base_dte=25` → `ROLL_ELIGIBLE` ACTION; notes contain `atm_strike - 50`
- `dte=6` → `[]`
- `base_dte=8` → `ROLL_BASE_FIRST` WARN
- `base_dte=11` → `ROLL_ELIGIBLE` (guard does not fire)
- Unknown `leg_role` → `ValueError`
- Collar short call → same result as CC
- Collar long put → same result as PP

**Commit:** `feat(strategy): add evaluate_roll_overlay to ExitSignalEngine with base-DTE guard`

---

## CR3 `[Claude]` — Wire roll signals into overlay strategies

**Files:** `src/strategy/nifty_track_comparison_v1.py`,
`tests/unit/strategy/test_nifty_track_comparison_v1.py`

**Prerequisite:** CR2 committed — `evaluate_roll_overlay` must exist.

**Note:** `CSPNiftyV1` roll wiring is fully handled in CR1d. This story covers only the
3-track overlay strategy.

**Before any code:**
- `get_code_snippet("NiftyTrackComparisonV1.check_signals")` — current WARN emit logic
- `get_code_snippet("evaluate_roll_overlay")` — CR2 signature

**Changes:**

When DTE ≤ 5, replace `ROLL_DUE_DTE` WARN emission with a call to
`ExitSignalEngine.evaluate_roll_overlay(leg_role, dte, base_dte, atm_strike)`:

- `ROLL_ELIGIBLE` ACTION → emit `SignalEvent(severity="ACTION", payload={..., "action_options": ["RECORD_ROLL"]})`
- `ROLL_BASE_FIRST` WARN → keep as WARN (same as current `ROLL_DUE_DTE`)
- DTE 6–10: keep existing `ROLL_DUE_DTE` WARN unchanged

Overlay strategies (`NiftyTrackComparisonV1`) do NOT set `auto_execute = True` —
overlay rolls require human confirmation via Telegram because the leg selection
(which overlay to roll, in what order) is not deterministic.

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

Append: *"Note (2026-06-04, CR): RapidCouncil is NOT wired into the paper trading
approval path. The daemon approval flow bypassed it from the start (signature mismatch
bug fixed in CR0). CSP roll decisions are deterministic (five independent classmethods
in ExitSignalEngine: evaluate_profit_target_csp / evaluate_hard_stop_csp /
evaluate_delta_breach_csp / evaluate_time_stop_csp / evaluate_roll_eligible_csp)
and backtestable. Council is retained as a module for future live trading use only."*

**DECISIONS.md — add new entry:**

```
**RapidCouncil removed from paper trading path (2026-06-04, CR):**
RapidCouncil is not called in any Phase 0 paper trading flow. Reasons:
(1) CSP exits are single-option decisions — action is determined by ExitSignalEngine
before a council could be consulted. (2) Roll decisions must be deterministic and
backtestable — LLM outputs are non-deterministic and cannot be replayed against
historical data without hindsight bias. (3) A signature mismatch between
StrategyMonitor and TelegramGateway meant the council was bypassed anyway (CR0).
CSP is an always-open strategy with five deterministic signals and three action types
(CLOSE_AND_ROLL, ROLL_DOWN_AND_OUT, CLOSE_AND_WAIT). Overlay strategies retain the
human approval path because leg-selective roll order is not deterministic.
Council wiring belongs in Phase 1 live trading only.

**CSP always-open design (2026-06-05, CR):**
CSP never truly closes — every exit cycles into a new position.
State machine: OPEN → DEFENDED (delta breach + roll) → RE_ENTRY_PENDING (any close)
→ OPEN (entry conditions met). No terminal CLOSE_FULL action.
Re-entry condition is identical to initial entry condition — no special-case code.
Thresholds: profit target 70% captured (LTP ≤ 30% of entry credit), hard stop 2×
entry credit, delta breach |δ| ≥ 0.40, time stop 21 days, DTE roll at ≤ 7.
No second roll: DEFENDED state positions can only CLOSE_AND_WAIT.
```

**CONTEXT.md — update `src/strategy/` entry:**

- `ExitSignalEngine`: add five CSP methods + `evaluate_roll_overlay`; remove combined evaluate_csp
- `CSPNiftyV1`: always-open design, auto_execute=True, full state machine (OPEN/DEFENDED/RE_ENTRY_PENDING), three action types
- `NiftyTrackComparisonV1`: ROLL_DUE_DTE at DTE ≤ 5 promoted to ACTION via evaluate_roll_overlay
- `StrategyMonitor`: auto-execute dispatch path; send_notification for observability

**CONTEXT.md — update `src/paper/` entry:**

- `PaperTrade`: add `state: TradeState` field
- `TradeState` enum: OPEN / DEFENDED / RE_ENTRY_PENDING
- `PaperStore`: add `update_trade_state(trade_id, state)`

**Commit:** `docs(strategy): document always-open CSP design, deterministic signals, council removal`

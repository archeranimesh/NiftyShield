# council-refactor — PP Automation Stories

> Shared context, signal tables, state machines: `README.md`
> Prerequisite: CR1a (strike_selector) + CR1b (TradeState) committed.

---

## PP State Machine

PP has two states. No DEFENDED equivalent — there is no defensive roll concept
for a long put. After monetizing, the strategy waits for IV to normalize before
re-buying protection.

```
OPEN ──── CRASH_MONETIZE fires ──────────────────────► RE_ENTRY_PENDING
  │                                                          │
  │  ROLL_ELIGIBLE (DTE ≤ 5)                                │  IVR ≤ 0.60 AND DTE ≥ 14
  │  → close current PP + open new PP at same delta         │  AND no open PP position
  │  stays OPEN                                             │
  └──────────────────────────────────────────────────────► OPEN
```

Re-entry gate is IVR ≤ 0.60 (inverse of CSP): after a crash monetization,
IV spikes. Buying protection at peak IV is expensive and often unnecessary
(the crash may be over). Wait for normalization.

No second monetize from RE_ENTRY_PENDING — no position exists to monetize.

---

## Signal Table (PP, evaluated each EOD)

| Priority | Signal | Trigger | Action | Severity | Valid state |
|---|---|---|---|---|---|
| 1 | `CRASH_MONETIZE` | delta ≤ −0.80 OR value ≥ 5× entry debit | MONETIZE_PP | ACTION | OPEN |
| 2 | `ROLL_ELIGIBLE` | DTE ≤ 5 | ROLL_PP | ACTION | OPEN |

No WARN or INFO signals (DTE_REVIEW is promoted to ACTION, no TIME_STOP for long options).

When both `CRASH_MONETIZE` and `ROLL_ELIGIBLE` fire (crash at DTE ≤ 5):
`PPOverlayV1.check_signals()` emits only `CRASH_MONETIZE` — highest priority wins.
`_sort_results()` puts ACTION before WARN but cannot distinguish two ACTIONs by name.
The caller breaks ties by list position: `CRASH_MONETIZE` is appended first, so
the priority-ordered break loop in `check_signals()` picks it.

Re-entry is modelled as a signal from RE_ENTRY_PENDING state:

| Signal | Trigger | Action | Severity |
|---|---|---|---|
| `PP_REENTRY_ELIGIBLE` | IVR ≤ 0.60 AND DTE ≥ 14 on next contract AND no open PP | OPEN_NEW_PP | ACTION |
| `PP_REENTRY_BLOCKED` | any gate fails | — | INFO |

---

## PP-1 `[Antigravity]` — Update `evaluate_pp()`: remove spread guard, promote DTE signal

**Files:**
- `src/strategy/exit_signals.py`
- `src/strategy/pp_overlay_v1.py` (update caller — remove bid/ask args)
- `tests/unit/strategy/test_exit_signals.py`
- `tests/unit/strategy/test_pp_overlay_v1.py` (update caller fixture)

**Prerequisite:** CR1b committed (confirms ExitSignalResult field list, _sort_results exists).

**Before any code:**
- `get_code_snippet("ExitSignalEngine.evaluate_pp")` — current signature (bid/ask present)
- `get_code_snippet("PPOverlayV1.check_signals")` — confirm call site passes bid/ask
- `get_code_snippet("ExitSignalResult")` — field list
- `search_graph("_sort_results")` — confirm sorting by severity only

**What to change in `exit_signals.py`:**

Remove `bid` and `ask` parameters. CRASH_MONETIZE fires when delta/value condition
is met — spread check is irrelevant in paper mode (PaperFillSimulator models slippage).

New signature:

```python
@classmethod
def evaluate_pp(
    cls,
    *,
    entry_price: float,
    current_mark: float,
    delta: float | None,
    dte: int,
) -> list[ExitSignalResult]:
    """Evaluate exit signals for a Protective Put (PP) long put leg.

    Signal priority (both may fire; caller takes first only):
      1. CRASH_MONETIZE — delta ≤ -0.80 OR value ≥ 5× entry debit
      2. ROLL_ELIGIBLE  — DTE ≤ 5 (auto-roll to next expiry)

    No spread guard: paper mode slippage is handled by PaperFillSimulator.

    Args:
        entry_price: Debit paid at entry (positive value).
        current_mark: Current LTP / mark of the long put.
        delta: Current delta of the long put (negative, e.g. -0.85).
        dte: Days to expiry.

    Returns:
        List of ExitSignalResult, sorted ACTION-first. Empty list if no signal.
    """
```

CRASH_MONETIZE condition (simplified):

```python
delta_breached = delta <= -0.80 if delta is not None else False
value_breached = current_mark >= 5.0 * entry_price
if delta_breached or value_breached:
    results.append(ExitSignalResult(
        exit_signal="CRASH_MONETIZE",
        severity="ACTION",
        threshold_value=5.0,
        notes=f"Crash monetise: delta={delta}, value={current_mark:.2f}, 5x_threshold={5.0 * entry_price:.2f}",
    ))
```

ROLL_ELIGIBLE (replaces DTE_REVIEW INFO):

```python
if dte <= 5:
    results.append(ExitSignalResult(
        exit_signal="ROLL_ELIGIBLE",
        severity="ACTION",
        threshold_value=5.0,
        notes=f"DTE {dte} ≤ 5 — roll PP to next expiry",
    ))
```

`_sort_results()` puts CRASH_MONETIZE before ROLL_ELIGIBLE when both fire
because `results` is built in that order and both are ACTION severity
(stable sort preserves insertion order for equal keys).

**What to change in `pp_overlay_v1.py`:**

Remove `bid` and `ask` from the `evaluate_pp()` call site. Remove `bid`/`ask`
extraction from `put_leg`. Remove `payload["bid"]` and `payload["ask"]`.

Update `payload["valid_actions"]` from `["MONETIZE_PP"]` to `["MONETIZE_PP", "ROLL_PP"]`
depending on signal type:

```python
if result.exit_signal == "CRASH_MONETIZE":
    payload["valid_actions"] = ["MONETIZE_PP"]
elif result.exit_signal == "ROLL_ELIGIBLE":
    payload["valid_actions"] = ["ROLL_PP"]
```

**Tests (`tests/unit/strategy/test_exit_signals.py`):**

`evaluate_pp` — CRASH_MONETIZE via delta:
- `delta=-0.81, current_mark=50.0, entry_price=20.0, dte=20` → CRASH_MONETIZE ACTION
- `delta=-0.80, current_mark=50.0, entry_price=20.0, dte=20` → CRASH_MONETIZE ACTION (boundary inclusive)
- `delta=-0.79, current_mark=50.0, entry_price=20.0, dte=20` → `[]` (neither fires)

`evaluate_pp` — CRASH_MONETIZE via value:
- `delta=-0.30, current_mark=101.0, entry_price=20.0, dte=20` → CRASH_MONETIZE (101 ≥ 5 × 20)
- `delta=-0.30, current_mark=99.0, entry_price=20.0, dte=20` → `[]`
- `delta=None, current_mark=105.0, entry_price=20.0, dte=20` → CRASH_MONETIZE (delta=None, value fires)

`evaluate_pp` — ROLL_ELIGIBLE:
- `delta=-0.20, current_mark=10.0, entry_price=20.0, dte=5` → ROLL_ELIGIBLE ACTION
- `delta=-0.20, current_mark=10.0, entry_price=20.0, dte=6` → `[]`
- `delta=-0.20, current_mark=10.0, entry_price=20.0, dte=0` → ROLL_ELIGIBLE (expiry day)

`evaluate_pp` — both fire (crash at DTE ≤ 5):
- `delta=-0.85, current_mark=110.0, entry_price=20.0, dte=3` → 2 results; CRASH_MONETIZE is index 0 (list ordering)

`evaluate_pp` — old spread guard gone:
- Previously required bid/ask; now no such parameters — verify calling without them works
- `delta=-0.82, current_mark=50.0, entry_price=20.0, dte=10` → CRASH_MONETIZE fires (no spread needed)

**Tests (`tests/unit/strategy/test_pp_overlay_v1.py`):**
- `check_signals` call no longer passes bid/ask; verify no AttributeError
- CRASH_MONETIZE event has `valid_actions=["MONETIZE_PP"]`
- ROLL_ELIGIBLE event has `valid_actions=["ROLL_PP"]`

**Commit:** `feat(strategy): evaluate_pp — remove spread guard, ROLL_ELIGIBLE replaces DTE_REVIEW`

---

## PP-2 `[Antigravity]` — `PPOverlayV1` full automation + state machine

**Files:**
- `src/strategy/pp_overlay_v1.py` (major refactor — inject store/broker/notifier, auto_execute, state machine)
- `tests/unit/strategy/test_pp_overlay_v1.py` (full rewrite)

**Prerequisite:** PP-1 committed + CR1a (strike_selector) + CR1b (TradeState, PaperStore.update_trade_state) committed.

**Before any code:**
- `get_code_snippet("PPOverlayV1.__init__")` — current constructor (no store/broker)
- `get_code_snippet("PPOverlayV1.check_signals")` — post-PP-1 state (positions-based)
- `get_code_snippet("PPOverlayV1.apply_action")` — current no-op pattern
- `get_code_snippet("CSPNiftyV1.__init__")` — reference: inject pattern, auto_execute wiring
- `get_code_snippet("CSPNiftyV1._evaluate_reentry")` — reference: re-entry evaluation pattern
- `get_code_snippet("PaperStore.get_open_trade")` — confirm signature
- `get_code_snippet("PaperStore.update_trade_state")` — confirm signature (CR1b gate)
- `get_code_snippet("filter_strikes_by_delta")` — confirm in strike_selector (CR1a gate)
- `get_code_snippet("TradeState")` — confirm OPEN / RE_ENTRY_PENDING (no DEFENDED)
- `search_graph("PPOverlayV1")` — verify current class exists

**Part 1 — Constructor injection**

```python
class PPOverlayV1:
    strategy_name: str = STRATEGY_PP_OVERLAY
    auto_execute: ClassVar[bool] = True
    reentry_leg_role: ClassVar[str] = "overlay_pp"  # gate 3: no open position with this role
    # Note: PPOverlayV1 does NOT inherit ReEntryMixin — PP re-entry uses an inverted IVR gate
    # (≤ 0.60, not ≥ 0.25) and is implemented in _evaluate_pp_reentry. reentry_leg_role is used
    # only internally in gate 3; it is not a mixin class attribute.

    def __init__(
        self,
        broker: BrokerClient,
        store: PaperStore,
        lookup: InstrumentLookup,
        notifier: TelegramGateway | None = None,
        vix_data_dir: Path | None = None,
    ) -> None:
        self._broker = broker
        self._store = store
        self._lookup = lookup
        self._notifier = notifier
        self._vix_data_dir = vix_data_dir
```

`vix_data_dir` is used for IVR computation (same pattern as CSPNiftyV1 / ReEntryMixin).
If `None`, IVR check is skipped and re-entry is always blocked (conservative default).

**Part 2 — `check_signals()` with state dispatch**

Signature remains protocol-compatible (`market: OptionChain, positions: list[PaperPosition]`)
but internal implementation switches to store-based state query, consistent with CSPNiftyV1:

```python
async def check_signals(
    self,
    market: OptionChain,
    positions: list[PaperPosition],
) -> list[SignalEvent]:
    open_trade = await self._store.get_open_trade(self.strategy_name)

    if open_trade is None or open_trade.state == TradeState.RE_ENTRY_PENDING:
        reentry_event = await self._evaluate_pp_reentry(market)
        return [reentry_event] if reentry_event else []

    # OPEN state — evaluate exit signals
    put_leg = self._find_put_leg(market, open_trade.instrument_key)
    expiry = self._parse_expiry(open_trade.instrument_key)
    dte = (expiry - date.today()).days if expiry is not None else 9999

    delta = float(put_leg.delta) if put_leg is not None else None
    current_mark = float(put_leg.ltp) if put_leg is not None else float(open_trade.price)
    entry_price = float(open_trade.price)

    results = ExitSignalEngine.evaluate_pp(
        entry_price=entry_price,
        current_mark=current_mark,
        delta=delta,
        dte=dte,
    )

    if not results:
        return []

    # Priority: emit only highest-priority signal (first result after _sort_results)
    result = results[0]
    if result.exit_signal == "CRASH_MONETIZE":
        action_options = ["MONETIZE_PP"]
    else:  # ROLL_ELIGIBLE
        action_options = ["ROLL_PP"]

    return [SignalEvent(
        event_type=result.exit_signal,
        severity=result.severity,
        description=result.notes or result.exit_signal,
        payload={
            "trade_id": open_trade.id,
            "leg_role": open_trade.leg_role,
            "trade_state": open_trade.state.value,
            "action_options": action_options,
            "auto_execute": True,
            "auto_action": action_options[0],
        },
    )]
```

**Part 3 — `apply_action()` — three action types**

```python
async def apply_action(
    self,
    positions: list[PaperPosition],
    action: ApprovedAction,
) -> list[PaperPosition]:
    open_trade = await self._store.get_open_trade(self.strategy_name)

    if action.action_type == "MONETIZE_PP":
        # Close the long put at market; mark state RE_ENTRY_PENDING
        await self._close_pp_leg(open_trade)
        await self._store.update_trade_state(open_trade.id, TradeState.RE_ENTRY_PENDING)
        await self._send_pp_notification("MONETIZE_PP", closed=open_trade, new_trade=None)

    elif action.action_type == "ROLL_PP":
        # Close current leg; open new PP on next weekly expiry (same delta range)
        closed = await self._close_pp_leg(open_trade)
        new_trade = await self._open_pp_leg(date.today())
        # State stays OPEN — new position, same protection
        await self._send_pp_notification("ROLL_PP", closed=open_trade, new_trade=new_trade)

    elif action.action_type == "OPEN_NEW_PP":
        # Triggered by re-entry from RE_ENTRY_PENDING
        new_trade = await self._open_pp_leg(date.today())
        await self._send_pp_notification("OPEN_NEW_PP", closed=None, new_trade=new_trade)

    else:
        raise ValueError(
            f"PPOverlayV1 only accepts MONETIZE_PP / ROLL_PP / OPEN_NEW_PP; got {action.action_type!r}"
        )

    return positions  # PaperPosition list unchanged — store is source of truth
```

**Part 4 — Private helpers**

`_close_pp_leg(trade: PaperTrade) -> PaperTrade`:
- Fetch current LTP via `self._broker.get_ltp(trade.instrument_key)`
- Call `self._store.record_trade(...)` with action="BUY" (closes the long put), price=ltp
- Emit structured log: `logger.info("pp_leg_closed", instrument_key=..., entry_price=..., exit_price=..., realized_pnl=...)`
- Use `structlog.get_logger("src.strategy.pp_overlay_v1")`

`_open_pp_leg(trade_date: date) -> PaperTrade`:
- Resolve next weekly expiry (Tuesday, DTE ≥ 7 from trade_date) via `self._lookup`
- Call `filter_strikes_by_delta(chain_data, "PE", delta_min=0.20, delta_max=0.30)`
- Call `rank_strikes(candidates)` — take `candidates[0]`
- If no candidate: raise `ValueError("No valid PP strike found in delta range 0.20–0.30")`
- Record via `self._store.record_trade(...)` with action="BUY"
- Emit structured log: `logger.info("pp_leg_opened", instrument_key=..., price=..., delta=..., dte=...)`

**Fixed delta range for PP: 0.20–0.30.** No IVR-based widening. The protective put depth is
a coverage decision (ATM-100 to ATM-150 at Nifty 24000), not an IV-level choice.

**Part 5 — Re-entry evaluation**

```python
async def _evaluate_pp_reentry(
    self, market: OptionChain
) -> SignalEvent | None:
    """Check if conditions allow re-buying protection from RE_ENTRY_PENDING.

    Gates (all must pass):
    1. Next weekly contract has DTE ≥ 14
    2. IVR ≤ 0.60 (don't buy at peak post-crash IV)
    3. No currently open PP position (redundant guard)

    IVR gate is skipped (always blocks) if vix_data_dir is None.
    """
    # Gate 1: DTE ≥ 14 on next expiry
    next_expiry = self._lookup.get_next_expiry(...)
    if next_expiry is None or (next_expiry - date.today()).days < 14:
        return SignalEvent(
            event_type="PP_REENTRY_BLOCKED",
            severity="INFO",
            description="Re-entry blocked: DTE < 14 on next contract",
            payload={},
        )

    # Gate 2: IVR ≤ 0.60
    if self._vix_data_dir is None:
        return SignalEvent(
            event_type="PP_REENTRY_BLOCKED",
            severity="INFO",
            description="Re-entry blocked: vix_data_dir not configured",
            payload={},
        )
    ivr = await self._fetch_ivr()
    if ivr is None or ivr > 0.60:
        return SignalEvent(
            event_type="PP_REENTRY_BLOCKED",
            severity="INFO",
            description=f"Re-entry blocked: IVR {ivr:.2f} > 0.60 (IV still elevated post-crash)",
            payload={},
        )

    # Gate 3: no open position
    existing = await self._store.get_open_trade(self.strategy_name)
    if existing is not None and existing.state == TradeState.OPEN:
        return SignalEvent(
            event_type="PP_REENTRY_BLOCKED",
            severity="INFO",
            description="Re-entry blocked: PP position already open",
            payload={},
        )

    return SignalEvent(
        event_type="PP_REENTRY_ELIGIBLE",
        severity="ACTION",
        description=f"Re-entry eligible: IVR {ivr:.2f} ≤ 0.60, DTE {(next_expiry - date.today()).days}",
        payload={
            "action_options": ["OPEN_NEW_PP"],
            "auto_execute": True,
            "auto_action": "OPEN_NEW_PP",
        },
    )
```

`_fetch_ivr()` — same pattern as CSPNiftyV1: `compute_ivr(vix_today, vix_series)`.

**Part 6 — Telegram notifications**

`_send_pp_notification(action_type, closed, new_trade)` — HTML format, wrapped in
`try/except`, non-fatal (same contract as CSPNiftyV1 notifier).

`MONETIZE_PP`:
```
💰 <b>PP: CRASH_MONETIZE</b>
📤 Closed: {instrument_key} @ ₹{exit_price:.2f}
   Entry ₹{entry_price:.2f} · P&amp;L <b>₹{realized_pnl:+,.0f}</b>
State: → RE_ENTRY_PENDING 🔵
Monitoring for re-entry (IVR ≤ 0.60, DTE ≥ 14)
```

`ROLL_PP`:
```
🔄 <b>PP: ROLL_ELIGIBLE</b>
📤 Closed: {instrument_key} @ ₹{exit_price:.2f}
📥 Rolled to: {new_instrument_key} @ ₹{new_price:.2f}
   Delta {new_delta:.3f} · DTE {new_dte}
State: OPEN ✓
```

`OPEN_NEW_PP` (re-entry):
```
🟢 <b>PP: OPEN_NEW_PP (re-entry)</b>
📥 Bought: {instrument_key} @ ₹{price:.2f}
   Delta {delta:.3f} · DTE {dte} · IVR {ivr:.2f}
State: RE_ENTRY_PENDING → OPEN ✓
```

Send via `self._notifier.send_notification(html)` if `self._notifier is not None`.

**Structured log in `apply_action` after execution:**

```python
logger.info(
    "pp_action_executed",
    strategy=self.strategy_name,
    action=action.action_type,
    closed_instrument=open_trade.instrument_key if open_trade else None,
    closed_price=str(exit_ltp) if open_trade else None,
    realized_pnl=str(realized_pnl) if open_trade else None,
    new_instrument=new_trade.instrument_key if new_trade else None,
    new_price=str(new_trade.price) if new_trade else None,
    state_after=state_after.value,
)
```

**Tests (`tests/unit/strategy/test_pp_overlay_v1.py`):**

`check_signals` dispatch:
- State=OPEN, CRASH_MONETIZE condition true → CRASH_MONETIZE ACTION, `auto_action="MONETIZE_PP"`
- State=OPEN, ROLL_ELIGIBLE only → ROLL_ELIGIBLE ACTION, `auto_action="ROLL_PP"`
- State=OPEN, both conditions true (crash at DTE ≤ 5) → only CRASH_MONETIZE emitted (priority)
- State=OPEN, no signal → `[]`
- State=RE_ENTRY_PENDING → `_evaluate_pp_reentry` called; CRASH_MONETIZE path NOT entered
- open_trade=None → re-entry evaluation path (same as RE_ENTRY_PENDING)

`apply_action`:
- `MONETIZE_PP` → `_close_pp_leg` called; state set to RE_ENTRY_PENDING
- `ROLL_PP` → `_close_pp_leg` then `_open_pp_leg` called; state stays OPEN (new trade is OPEN by default)
- `OPEN_NEW_PP` → `_open_pp_leg` called; new state OPEN
- Unknown action type → raises `ValueError`

`_open_pp_leg`:
- No candidates in delta range → raises `ValueError`
- Valid candidates → first candidate by `rank_strikes` selected

`_evaluate_pp_reentry`:
- DTE < 14 on next contract → PP_REENTRY_BLOCKED INFO
- IVR > 0.60 → PP_REENTRY_BLOCKED INFO
- vix_data_dir=None → PP_REENTRY_BLOCKED INFO
- All gates pass (IVR=0.40, DTE=21) → PP_REENTRY_ELIGIBLE ACTION, `auto_action="OPEN_NEW_PP"`
- Existing open trade → PP_REENTRY_BLOCKED INFO

Notification:
- `MONETIZE_PP` → `send_notification` called with HTML containing "CRASH_MONETIZE" and "RE_ENTRY_PENDING"
- `ROLL_PP` → notification contains "ROLL_ELIGIBLE" and new instrument key
- `OPEN_NEW_PP` → notification contains "re-entry" and "OPEN"
- `notifier=None` → no error; action executes normally

**Commit:** `feat(strategy): PPOverlayV1 full automation — auto_execute, MONETIZE_PP, ROLL_PP, RE_ENTRY_PENDING loop`

---

## PP-3 `[Claude]` — Docs close for PP automation (add after PP-2)

**Files:** `DECISIONS.md`, `CONTEXT.md`, `docs/plan/council-refactor/README.md`,
`docs/plan/council-refactor/tasks.md`

**No code changes.**

**`README.md` — add PP signal table and state machine** (already reflected in this file;
confirm against implementation before committing).

**`DECISIONS.md` — add entry:**

```
**PP always-reprotect design (2026-06-__, PP):**
PP (Protective Put) on NiftyBees tracks a simple two-state machine: OPEN ↔ RE_ENTRY_PENDING.
No DEFENDED state — there is no defensive roll for a long put.
After CRASH_MONETIZE, strategy enters RE_ENTRY_PENDING and waits for IVR ≤ 0.60
before re-buying protection. This prevents buying at peak post-crash IV.
Delta range for new PP: fixed 0.20–0.30 (coverage depth, not IV-driven).
Spread guard removed from CRASH_MONETIZE: paper mode slippage handled by PaperFillSimulator;
in a real crash, spread guard would block auto-execution at exactly the wrong moment.
DTE roll (ROLL_ELIGIBLE at DTE ≤ 5) auto-executes: straightforward forward roll, same delta.
```

**`CONTEXT.md` — update `src/strategy/` entry:**

- `ExitSignalEngine.evaluate_pp`: signature simplified (no bid/ask); CRASH_MONETIZE no spread guard;
  DTE_REVIEW INFO replaced by ROLL_ELIGIBLE ACTION.
- `PPOverlayV1`: auto_execute=True; two-state machine (OPEN / RE_ENTRY_PENDING); three action types
  (MONETIZE_PP, ROLL_PP, OPEN_NEW_PP); IVR ≤ 0.60 re-entry gate.

**Commit:** `docs(strategy): document PP always-reprotect design, IVR re-entry gate, spread guard removal`

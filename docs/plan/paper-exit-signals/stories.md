# paper-exit-signals — Story Specs

> One task per session. Find the first unchecked item in `tasks.md`. That is your only task.
> Full implementation rules in `CLAUDE.md` and `REVIEW.md`.
> After each task: tick `tasks.md`, append `| SHA: <sha>`, add one line to `TODOS.md`.

**Prerequisite check (run before any task):**
```
search_graph("StrategyMonitor")   # must exist — PB1.2 committed
search_graph("PaperExecutor")     # must exist — PB1.3 committed
search_graph("CCOverlayV1")       # must NOT exist yet
```

---

## ES0 — `paper_exit_events` table migration + store methods + tests

**Files to change:**
- `src/paper/store.py` — add `paper_exit_events` migration + 4 new methods
- `tests/unit/paper/test_paper_store_exit_events.py` — new test file

**Before any code:**
- `get_code_snippet("PaperStore")` — current `__init__`, confirm existing table list
- `get_code_snippet("db_connection")` — context manager signature
- Read `docs/plan/paper-exit-signals/schema.md` — exact DDL

**What to implement in `PaperStore`:**

```python
def create_exit_event(
    self,
    strategy_name: str,
    leg_name: str,
    trade_id: str,
    event_time: str,           # ISO 8601 UTC
    detected_by: str,          # "EOD" | "INTRADAY" | "MANUAL"
    exit_signal: str,          # enum value from schema.md
    severity: str,             # "INFO" | "WARNING" | "ACTION"
    entry_price: float,
    *,
    snapshot_id: int | None = None,
    ltp: float | None = None,
    mid: float | None = None,
    bid: float | None = None,
    ask: float | None = None,
    delta: float | None = None,
    dte: int | None = None,
    threshold_value: float | None = None,
    delta_stop_would_fire: bool | None = None,
    premium_stop_would_fire: bool | None = None,
    actual_rule_used: str | None = None,
    notes: str | None = None,
) -> int:
    """INSERT into paper_exit_events, status=OPEN. Returns new row id."""

def get_open_exit_events(
    self,
    strategy_name: str | None = None,
) -> list[dict]:
    """SELECT all rows with status=OPEN, optionally filtered by strategy_name."""

def acknowledge_exit_event(self, event_id: int) -> None:
    """UPDATE status=ACKNOWLEDGED."""

def resolve_exit_event(
    self,
    event_id: int,
    status: Literal["ACTED", "DISMISSED"],
    notes: str | None = None,
) -> None:
    """UPDATE status. Append notes if provided."""
```

**Tests (`tests/unit/paper/test_paper_store_exit_events.py`):**

All tests use `tmp_path` fixture with a fresh `PaperStore`.

- `create_exit_event` → returns integer id ≥ 1.
- `get_open_exit_events` → returns created row with all nullable fields as None.
- `create_exit_event` with all optional fields set → round-trip preserves all values.
- `acknowledge_exit_event` → row status is `ACKNOWLEDGED`; still in `get_open_exit_events`.
- `resolve_exit_event(ACTED)` → row no longer in `get_open_exit_events`.
- `resolve_exit_event(DISMISSED)` → row no longer in `get_open_exit_events`.
- Create two events, resolve one → `get_open_exit_events` returns exactly one row.
- `get_open_exit_events(strategy_name="paper_nifty_spot")` → filters correctly.
- `paper_exit_events` table created by `PaperStore.__init__` → existing `paper_trades`
  table unaffected (confirm row count unchanged after migration).
- Dual-signal fields: create event with `delta_stop_would_fire=True,
  premium_stop_would_fire=False` → round-trip returns 1 and 0 respectively.

**Commit:** `feat(paper): add paper_exit_events table migration and store methods`

---

## ES1 — `src/strategy/exit_signals.py`: ExitSignalEngine + tests

**Files to change:**
- `src/strategy/exit_signals.py` — pure rule engine, no DB, no async
- `tests/unit/strategy/test_exit_signals.py` — new test file

**Before any code:**
- `get_code_snippet("SignalEvent")` — severity literals from PB1.1
- `get_code_snippet("PaperPosition")` — field list; confirm `entry_price`, `leg_role`, `net_qty`
- `get_code_snippet("OptionChainStrike")` — confirm delta field name
- Read `docs/plan/paper-exit-signals/prompt.md` — canonical exit rule table (all 4 leg types)

**What to implement:**

`ExitSignalEngine` is a stateless class — no constructor dependencies. Every method
is a pure function of its arguments. No DB calls. No async. Fully unit-testable.

```python
from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

LOT_SIZE = 65
MIN_ENTRY_CREDIT_FLOOR = Decimal("12")   # ₹/unit — below this, % exits suspended
PREFERRED_ENTRY_FLOOR  = Decimal("15")   # ₹/unit — below this, flagged as marginal


@dataclass(frozen=True)
class ExitSignalResult:
    exit_signal: str
    severity: Literal["INFO", "WARNING", "ACTION"]
    threshold_value: float | None
    delta_stop_would_fire: bool | None    # None for non-sell legs (PP)
    premium_stop_would_fire: bool | None  # None for non-sell legs (PP)
    actual_rule_used: str | None
    description: str


class ExitSignalEngine:

    # ── CSP ──────────────────────────────────────────────────────────────
    def evaluate_csp(
        self,
        entry_credit: Decimal,       # ₹/unit at entry
        current_mark: Decimal,       # ₹/unit current option price
        delta: float | None,         # short put delta (negative; use abs)
        dte: int,
        days_held: int,
    ) -> list[ExitSignalResult]:
        """
        Evaluate CSP exit signals per csp_nifty_v1 + 2026-05-28 council.
        Returns list ordered by severity (ACTION first).
        """

    # ── Standalone CC ─────────────────────────────────────────────────────
    def evaluate_cc(
        self,
        entry_credit: Decimal,
        current_mark: Decimal,
        delta: float | None,         # short call delta (positive)
        dte: int,
        spot: Decimal,
        strike: Decimal,
    ) -> list[ExitSignalResult]:
        """
        Evaluate standalone CC exit signals per 2026-05-28 council.
        Includes BELOW_FLOOR check before any % target evaluation.
        """

    # ── PP ────────────────────────────────────────────────────────────────
    def evaluate_pp(
        self,
        entry_debit: Decimal,
        current_mark: Decimal,
        delta: float | None,         # long put delta (negative)
        bid: Decimal | None,
        ask: Decimal | None,
        dte: int,
    ) -> list[ExitSignalResult]:
        """
        Evaluate PP exit signals. Default is hold-to-expiry.
        Only CRASH_MONETIZE and DTE_REVIEW can fire.
        bid/ask required to evaluate the liquidity gate.
        """

    # ── Collar ────────────────────────────────────────────────────────────
    def evaluate_collar_call(
        self,
        entry_credit: Decimal,       # short call entry credit
        current_mark: Decimal,
        delta: float | None,         # short call delta (positive)
        dte: int,
        spot: Decimal,
        strike: Decimal,
    ) -> list[ExitSignalResult]:
        """
        Evaluate Collar short call. 75% decay rule (not 50%).
        No independent LOSS_STOP — COLLAR_CALL_WARN only.
        """

    def evaluate_collar_put(
        self,
        entry_debit: Decimal,
        current_mark: Decimal,
        delta: float | None,
        bid: Decimal | None,
        ask: Decimal | None,
        dte: int,
    ) -> list[ExitSignalResult]:
        """Same logic as evaluate_pp."""
```

**Threshold constants (define at module level):**

```python
# CSP
CSP_PROFIT_PCT       = Decimal("0.50")   # close at 50% decay
CSP_LOSS_MULTIPLE    = Decimal("1.75")
CSP_DELTA_ACTION     = 0.45
CSP_DELTA_WARN       = 0.35
CSP_TIME_STOP_DAYS   = 21
CSP_DTE_REVIEW       = 5

# CC standalone
CC_PROFIT_PCT        = Decimal("0.50")
CC_LOSS_MULTIPLE     = Decimal("2.50")
CC_DELTA_ACTION      = 0.55
CC_DELTA_WARN        = 0.45
CC_DTE_FORCED        = 5
CC_DTE_RESIDUAL_FLOOR = Decimal("5")   # ₹/unit — close at DTE ≤ 5 if residual ≥ this

# PP / Collar long put
PP_CRASH_DELTA       = -0.80
PP_CRASH_MULTIPLE    = Decimal("5.00")
PP_SPREAD_GATE       = Decimal("0.10")  # bid/ask ≤ 10% of mid

# Collar short call
COLLAR_CALL_DECAY_PCT   = Decimal("0.25")   # close at 25% remaining (75% decayed)
COLLAR_CALL_RESIDUAL    = Decimal("3")      # ₹/unit floor
COLLAR_CALL_WARN_DELTA  = 0.55
COLLAR_DTE_FORCED       = 5
COLLAR_DTE_CALL_DELTA   = 0.50
```

**Tests (`tests/unit/strategy/test_exit_signals.py`):**

CSP:
- mark = 49% of entry → `PROFIT_TARGET` ACTION.
- mark = 51% → no profit target signal.
- mark = 1.76× entry → `LOSS_STOP` ACTION. Also `premium_stop_would_fire=True`.
- mark = 1.74× → no loss stop.
- delta = 0.46 → `DELTA_STOP` ACTION. Also `delta_stop_would_fire=True`.
- delta = 0.36 → `DELTA_WARN` WARNING.
- days_held = 21 → `TIME_STOP` ACTION.
- days_held = 20 → no time stop.
- dte = 4 → `DTE_REVIEW` INFO.
- Healthy position (mark 60%, delta 0.20, days 10) → `[]`.
- `delta_stop_would_fire` and `premium_stop_would_fire` both set on LOSS_STOP event
  (delta = 0.46, mark = 1.76×) — both `True`.
- delta=None → delta-based signals absent; premium backstop still fires if mark threshold met.

CC:
- entry_credit = ₹10/unit → `BELOW_FLOOR` INFO fires; PROFIT_TARGET does NOT fire even if mark ≤ 50%.
- entry_credit = ₹15/unit, mark ≤ 50% → `PROFIT_TARGET` ACTION.
- mark = 2.51× entry → `LOSS_STOP` ACTION.
- delta = 0.56 → `DELTA_STOP` ACTION.
- delta = 0.46 → `DELTA_WARN` WARNING.
- DTE=4, spot > strike (call ITM) → `DTE_FORCED` ACTION.
- DTE=4, spot < strike, delta=0.10, residual ₹3 → no DTE_FORCED (none of the three conditions met).

PP:
- delta = −0.81 → `CRASH_MONETIZE` ACTION.
- value = 5.01× entry, bid/ask = 8% of mid → `CRASH_MONETIZE` ACTION.
- value = 5.01× entry, bid/ask = 12% of mid → no CRASH_MONETIZE (liquidity gate fails).
- dte = 4 → `DTE_REVIEW` INFO.
- Healthy PP (delta −0.15, value 1.5×, dte 20) → `[]`.

Collar call:
- mark ≤ 25% of entry (75% decayed), DTE > 7 → `COLLAR_CALL_DECAY` ACTION.
- residual ≤ ₹3/unit, DTE > 7 → `COLLAR_CALL_DECAY` ACTION.
- delta = 0.56 → `COLLAR_CALL_WARN` WARNING (no ACTION stop).
- DTE=4, call ITM → `DTE_FORCED` ACTION.
- Healthy collar call (mark 40%, delta 0.25, DTE 20) → `[]`.

**Commit:** `feat(strategy): add ExitSignalEngine with CSP, CC, PP, Collar rule sets`

---

## ES2 — `src/strategy/csp_nifty_v1.py`: fix thresholds + re-test

**Files to change:**
- `src/strategy/csp_nifty_v1.py` — replace inline threshold literals with `ExitSignalEngine` calls
- `tests/unit/strategy/test_csp_nifty_v1.py` — update tests to corrected thresholds

**Before any code:**
- `get_code_snippet("CSPNiftyV1")` — confirm PB2.1 implementation exists
- `get_code_snippet("ExitSignalEngine")` — ES1 must be committed first
- Read `docs/plan/paper-exit-signals/prompt.md` CSP table — confirmed thresholds

**What changes:**

PB2.1 implemented thresholds that do not match the confirmed council spec:
- `LOSS_STOP` was `mark ≥ 2.0×` → correct to `1.75×`
- `DELTA_STOP` was `|delta| ≥ 0.35` → correct to `0.45`
- `DELTA_WARN` threshold was `0.25` → correct to `0.35`

Replace all inline threshold comparisons in `check_signals()` with calls to
`ExitSignalEngine.evaluate_csp()`. Map `ExitSignalResult` → `SignalEvent`.

`apply_action()` remains `CLOSE_FULL` only. No change.

**Test updates:**
- `|delta| = 0.36` → `DELTA_WARN` WARNING (was `DELTA_STOP` ACTION in PB2.1 — wrong threshold).
- `|delta| = 0.46` → `DELTA_STOP` ACTION (corrected).
- `mark = 1.76× entry` → `LOSS_STOP` ACTION.
- `mark = 2.01× entry` → `LOSS_STOP` ACTION (still fires, threshold is lower not higher).

**Commit:** `fix(strategy): correct CSPNiftyV1 thresholds to match council ruling (delta 0.45, loss 1.75×)`

---

## ES3 — `src/strategy/cc_overlay_v1.py`: CCOverlayV1 + tests

**Files to change:**
- `src/strategy/cc_overlay_v1.py` — `CCOverlayV1` implements `PaperStrategy`
- `tests/unit/strategy/test_cc_overlay_v1.py` — new test file

**Before any code:**
- `get_code_snippet("PaperStrategy")` — exact protocol signature
- `get_code_snippet("PaperPosition")` — confirm `leg_role`, `strategy_name`, `entry_price`, `net_qty`
- `get_code_snippet("ExitSignalEngine")` — `evaluate_cc` signature
- `get_code_snippet("OptionChainStrike")` — delta and bid/ask field names

**What to implement:**

```python
class CCOverlayV1:
    strategy_name = "paper_cc_overlay_v1"

    # leg_role values this strategy monitors
    SHORT_CALL_ROLES = {"short_call", "cc_short_call"}

    async def check_signals(
        self,
        market: OptionChain,
        positions: list[PaperPosition],
    ) -> list[SignalEvent]:
        """
        For each position with strategy_name in SHORT_CALL_ROLES:
          1. Find matching strike in market.strikes by instrument_key.
          2. Call ExitSignalEngine.evaluate_cc(entry_credit, current_mark, delta, dte, ...).
          3. Map ExitSignalResult → SignalEvent with payload including:
               entry_price, current_mark, delta, dte, leg_name, trade_id
        If delta unavailable (strike not found in chain): use delta=None,
        premium backstop still evaluated.
        """

    def describe_context(
        self,
        event: SignalEvent,
        market: OptionChain,
        positions: list[PaperPosition],
    ) -> str:
        """Plain text: entry credit, current mark, % decay, delta, DTE, spot."""

    async def apply_action(
        self,
        positions: list[PaperPosition],
        action: ApprovedAction,
    ) -> list[PaperPosition]:
        """
        Accepts: CLOSE_CC (close the short call only).
        Any other action_type → raises ValueError.
        Uses PaperFillSimulator for fill price.
        """
```

**Tests (`tests/unit/strategy/test_cc_overlay_v1.py`):**

Use `MockBrokerClient` and a mock `OptionChain` fixture.

- No CC positions → `check_signals` returns `[]`.
- CC with mark ≤ 50% of entry, credit ≥ ₹15 → `PROFIT_TARGET` ACTION event.
- CC with entry credit < ₹12 → `BELOW_FLOOR` INFO; no PROFIT_TARGET.
- CC with delta ≥ +0.56 → `DELTA_STOP` ACTION.
- CC with mark ≥ 2.5× entry → `LOSS_STOP` ACTION.
- CC with delta unavailable (strike missing from chain) → premium backstop still evaluates.
- `apply_action(CLOSE_CC)` → no error.
- `apply_action(ADJUST)` → raises `ValueError`.
- `describe_context` returns non-empty string with key fields present.

**Commit:** `feat(strategy): add CCOverlayV1 with ExitSignalEngine integration`

---

## ES4 — `src/strategy/pp_overlay_v1.py`: PPOverlayV1 + tests

**Files to change:**
- `src/strategy/pp_overlay_v1.py` — `PPOverlayV1` implements `PaperStrategy`
- `tests/unit/strategy/test_pp_overlay_v1.py` — new test file

**Before any code:**
- `get_code_snippet("PaperStrategy")` — protocol signature
- `get_code_snippet("ExitSignalEngine")` — `evaluate_pp` signature; note bid/ask required
  for CRASH_MONETIZE liquidity gate

**What to implement:**

```python
class PPOverlayV1:
    strategy_name = "paper_pp_overlay_v1"
    LONG_PUT_ROLES = {"long_put", "pp_long_put", "protective_put"}

    async def check_signals(...) -> list[SignalEvent]:
        """
        For each long put position:
          1. Locate strike in chain by instrument_key.
          2. Call ExitSignalEngine.evaluate_pp(entry_debit, current_mark, delta, bid, ask, dte).
          3. CRASH_MONETIZE → ACTION. DTE_REVIEW → INFO.
        bid/ask: use chain strike values if available; else mid=ltp, bid=ask=None
        (liquidity gate will not fire without bid/ask — acceptable, conservative).
        """

    async def apply_action(
        self,
        positions: list[PaperPosition],
        action: ApprovedAction,
    ) -> list[PaperPosition]:
        """
        Accepts: MONETIZE_PP.
        Closes long put at mid price (not loss-stop slippage — it's a profitable close).
        Does NOT automatically re-establish replacement protection — that is a separate
        manual entry decision. Logs a WARN Telegram message: "PP closed. Evaluate
        replacement if DTE ≥ 14."
        Any other action_type → raises ValueError.
        """
```

**Tests (`tests/unit/strategy/test_pp_overlay_v1.py`):**

- No PP positions → `[]`.
- PP with delta ≤ −0.81 AND bid/ask ≤ 10% of mid → `CRASH_MONETIZE` ACTION.
- PP with delta ≤ −0.81 AND bid/ask > 10% → no CRASH_MONETIZE (liquidity gate blocks).
- PP with value ≥ 5× entry AND spread OK → `CRASH_MONETIZE` ACTION.
- bid/ask unavailable (None) → no CRASH_MONETIZE even if delta breached (conservative).
- DTE = 4 → `DTE_REVIEW` INFO.
- Healthy PP (delta −0.15, value 1.2×, DTE 25) → `[]`.
- `apply_action(MONETIZE_PP)` → no error.
- `apply_action(CLOSE_FULL)` → raises `ValueError`.

**Commit:** `feat(strategy): add PPOverlayV1 with crash-monetise detection`

---

## ES5 — `src/strategy/collar_overlay_v1.py`: CollarOverlayV1 + tests

**Files to change:**
- `src/strategy/collar_overlay_v1.py` — `CollarOverlayV1` implements `PaperStrategy`
- `tests/unit/strategy/test_collar_overlay_v1.py` — new test file

**Before any code:**
- `get_code_snippet("PaperStrategy")` — protocol
- `get_code_snippet("ExitSignalEngine")` — `evaluate_collar_call` + `evaluate_collar_put`
- `get_code_snippet("PaperPosition")` — confirm `leg_role` values for collar legs
  (expected: `collar_short_call`, `collar_long_put`)
- Read `docs/plan/paper-exit-signals/prompt.md` Collar closure sequences — 4 distinct paths

**What to implement:**

```python
class CollarOverlayV1:
    strategy_name = "paper_collar_overlay_v1"
    SHORT_CALL_ROLE = "collar_short_call"
    LONG_PUT_ROLE   = "collar_long_put"

    async def check_signals(...) -> list[SignalEvent]:
        """
        Evaluate both legs independently, but signal semantics differ:
        Short call: COLLAR_CALL_DECAY (ACTION), COLLAR_CALL_WARN (WARN), DTE_FORCED (ACTION).
        Long put:   COLLAR_PUT_CRASH (ACTION), DTE_REVIEW (INFO).
        No independent LOSS_STOP for the short call — COLLAR_CALL_WARN only.
        payload must include which leg triggered + both leg states for context.
        """

    async def apply_action(
        self,
        positions: list[PaperPosition],
        action: ApprovedAction,
    ) -> list[PaperPosition]:
        """
        Routes to OverlayCloser based on action_type:
          CLOSE_CALL_ONLY   → buy back short call; keep long put + base long
          MONETIZE_PUT      → sequence: close cheap call first → sell put
          CLOSE_ALL_OVERLAY → atomic: close call + close put (rollback on failure)
          Any other         → raises ValueError
        """
```

**Tests (`tests/unit/strategy/test_collar_overlay_v1.py`):**

- No collar positions → `[]`.
- Short call at 24% of entry, DTE > 7 → `COLLAR_CALL_DECAY` ACTION.
- Short call at 26% of entry → no decay signal.
- Short call residual ≤ ₹3/unit, DTE > 7 → `COLLAR_CALL_DECAY` ACTION.
- Short call delta ≥ +0.56 → `COLLAR_CALL_WARN` WARNING (not ACTION).
- Long put delta ≤ −0.81, spread ≤ 10% → `COLLAR_PUT_CRASH` ACTION.
- DTE=4, short call ITM → `DTE_FORCED` ACTION.
- Healthy collar (call 40%, put delta −0.15, DTE 20) → `[]`.
- `apply_action(CLOSE_CALL_ONLY)` → no error.
- `apply_action(MONETIZE_PUT)` → no error.
- `apply_action(CLOSE_ALL_OVERLAY)` → no error.
- `apply_action(ROLL_COLLAR)` → raises `ValueError`.

**Commit:** `feat(strategy): add CollarOverlayV1 with 4-path closure routing`

---

## ES6 — `src/strategy/overlay_closer.py`: OverlayCloser + tests

**Files to change:**
- `src/strategy/overlay_closer.py` — atomic multi-leg close with rollback
- `tests/unit/strategy/test_overlay_closer.py` — new test file

**Before any code:**
- `get_code_snippet("PaperExecutor")` — `apply()` signature from PB1.3
- `get_code_snippet("PaperFillSimulator")` — slippage model
- `get_code_snippet("PaperStore")` — `record_trade` and `create_exit_event` signatures
- Read `docs/plan/paper-exit-signals/prompt.md` Collar closure sequences — exact steps
- `search_code("rollback")` in `scripts/paper_3track_overlay_roll.py` — confirm pattern

**What to implement:**

`OverlayCloser` handles multi-leg close sequences where failure of one leg
requires rolling back already-completed legs.

```python
class OverlayCloser:
    def __init__(
        self,
        store: PaperStore,
        simulator: PaperFillSimulator,
        notifier: TelegramGateway,
    ) -> None: ...

    def close_single_leg(
        self,
        strategy_name: str,
        position: PaperPosition,
        exit_signal: str,
        *,
        is_loss_stop: bool = False,   # True → 1.5× slippage multiplier
        dual_signal_audit: dict | None = None,
    ) -> None:
        """
        Close one leg. Records paper_trade + paper_exit_event.
        dual_signal_audit: {"delta_stop_would_fire": bool, "premium_stop_would_fire": bool,
                             "actual_rule_used": str}
        """

    def close_collar_call_only(
        self,
        strategy_name: str,
        call_position: PaperPosition,
        exit_signal: str,
    ) -> None:
        """Close only the short call. Long put and base long untouched."""

    def close_collar_all(
        self,
        strategy_name: str,
        call_position: PaperPosition,
        put_position: PaperPosition,
    ) -> None:
        """
        Atomic close:
        Step 1: close short call (BUY back).
        Step 2: close long put (SELL).
        If Step 2 fails: re-open the short call (SELL, same strike/expiry/qty)
        to restore the Collar structure. Log rollback. Alert via notifier.
        Never leave the portfolio in a half-closed Collar state silently.
        Records paper_exit_events for both legs: ACTED if success, OPEN if rolled back.
        """

    def monetize_collar_put(
        self,
        strategy_name: str,
        call_position: PaperPosition,
        put_position: PaperPosition,
        market: OptionChain,
    ) -> None:
        """
        Crash monetisation sequence:
        Step 1: close call if residual < ₹5/unit (buy back near-worthless).
        Step 2: close put (SELL at mid, not loss-stop slippage).
        Note in paper_exit_events: "Evaluate replacement protection if DTE ≥ 14."
        """
```

**Tests (`tests/unit/strategy/test_overlay_closer.py`):**

Use `tmp_path` PaperStore, MockBrokerClient, mock TelegramGateway.

- `close_single_leg` → paper_trade recorded with reverse action; paper_exit_events row
  written with status=ACTED.
- `close_single_leg(is_loss_stop=True)` → slippage is 1.5× base (verify via FillResult).
- `close_single_leg` with `dual_signal_audit` → both fields persisted in exit event.
- `close_collar_call_only` → call trade recorded; put position unchanged in PaperStore.
- `close_collar_all` happy path → both trades recorded; both exit events ACTED.
- `close_collar_all` Step 2 failure (mock store raises on second record_trade call) →
  rollback trade inserted for call; notifier called; both exit events remain OPEN.
- `monetize_collar_put` → call closed first if residual < ₹5; put closed at mid price.
- `monetize_collar_put` → exit event notes contain "Evaluate replacement".

**Commit:** `feat(strategy): add OverlayCloser with atomic Collar close + rollback`

---

## ES7 — EOD integration: extend `paper_3track_snapshot.py` + tests

**Files to change:**
- `scripts/paper_3track_snapshot.py` — add Tier 1 exit signal computation after mark-to-market
- `tests/unit/scripts/test_paper_3track_snapshot_exit.py` — new test file

**Before any code:**
- `get_code_snippet("paper_3track_snapshot")` — current structure; confirm where mark
  fetch and delta-from-yesterday happen
- `get_code_snippet("ExitSignalEngine")` — all four evaluate_* signatures
- `get_code_snippet("PaperStore.create_exit_event")` — field list from ES0

**What to implement:**

After the existing mark-to-market fetch, add a function:

```python
def compute_and_record_exit_signals(
    store: PaperStore,
    positions: list[PaperPosition],
    chain: OptionChain,
    snapshot_id: int,
    engine: ExitSignalEngine,
    today: date,
) -> list[int]:
    """
    For every open position leg, determine leg type from leg_role,
    call the appropriate engine.evaluate_* method,
    write ACTION and WARNING results to paper_exit_events (detected_by=EOD),
    skip INFO if already written today for the same trade_id + exit_signal.
    Returns list of created paper_exit_events IDs.
    """
```

Deduplication: `SELECT 1 FROM paper_exit_events WHERE trade_id=? AND exit_signal=?
AND date(event_time)=? AND status='OPEN'` — skip insert if row exists.
Prevents duplicate signals across multiple EOD runs on the same day.

After computing signals, send Telegram summary:
- ACTION signals: one message per signal with leg details + exit threshold.
- WARNING signals: batched into one summary message per strategy.
- No signals: no message sent (silence is good news).

**Tests (`tests/unit/scripts/test_paper_3track_snapshot_exit.py`):**

- CSP position with mark ≤ 50% → `create_exit_event` called with `PROFIT_TARGET`, `detected_by=EOD`.
- CC position with delta ≥ 0.56 → `DELTA_STOP` exit event written.
- PP position with delta ≤ −0.81, spread ≤ 10% → `CRASH_MONETIZE` written.
- Healthy position (no threshold breach) → `create_exit_event` NOT called.
- Running twice on same day with same signal → second run does NOT create duplicate.
- INFO signals → NOT written to paper_exit_events (INFO is engine-internal only).
- Multiple positions, one breaches → only breaching position creates event.
- Notifier called once for ACTION signals; once for batched WARNINGs.
- Notifier failure (raises) → signal still written to DB (notifier is non-fatal).

**Commit:** `feat(scripts): add Tier 1 EOD exit signal detection to paper_3track_snapshot`

---

## ES8 — Daemon integration: register overlay strategies + env gate

**Files to change:**
- `scripts/monitor_daemon.py` — register CCOverlayV1, PPOverlayV1, CollarOverlayV1;
  add `MONITOR_OVERLAYS` env gate
- `src/strategy/__init__.py` — expose new strategy classes

**Before any code:**
- `get_code_snippet("monitor_daemon")` — current startup and strategy registration block
- `search_code("MONITOR_OVERLAYS")` — confirm does NOT yet exist (zero results)

**What to implement:**

In `monitor_daemon.py`, the strategy registration block becomes:

```python
MONITOR_OVERLAYS = os.getenv("MONITOR_OVERLAYS", "0") == "1"

strategies = [CSPNiftyV1(...), IronCondorV1(...), NiftyTrackComparisonV1(...)]
if MONITOR_OVERLAYS:
    strategies.extend([CCOverlayV1(...), PPOverlayV1(...), CollarOverlayV1(...)])
    log.info("Overlay monitoring enabled (MONITOR_OVERLAYS=1)")
else:
    log.info("Overlay monitoring disabled — Tier 1 EOD only (MONITOR_OVERLAYS=0)")
```

When an overlay strategy fires an ACTION signal, `StrategyMonitor` routes it through
`TelegramGateway.send_approval_request()` → `pending_approvals` row → button press →
`OverlayCloser` executes via the existing `PaperExecutor.apply()` callback path.

Wire `OverlayCloser` into the `on_approved` callback of `TelegramGateway.start_polling()`:

```python
async def on_approved(approval_id: int, rank: int) -> None:
    approval = store.get_pending_approvals()  # find by id
    council_output = CouncilOutput.from_json(approval["council_output"])
    action = council_output.actions[rank - 1]
    # Route to OverlayCloser or PaperExecutor based on action_type
    if action.action_type in ("CLOSE_CALL_ONLY", "MONETIZE_PUT", "CLOSE_ALL_OVERLAY"):
        overlay_closer.route(strategy_name, action, positions, market)
    else:
        executor.apply(strategy_name, action, market, approval_id)
    store.resolve_approval(approval_id, "APPROVED", rank)
```

No new tests required — daemon startup is covered by existing backbone tests.
Add one integration smoke test: daemon registers overlays when `MONITOR_OVERLAYS=1`.

**Commit:** `feat(scripts): register overlay strategies in daemon with MONITOR_OVERLAYS gate`

---

## ES9 — Docs close + archive

**Files to change:**
- `DECISIONS.md` — add 10 rows from council Summary Table
- `CONTEXT.md` — update `src/strategy/` tree with new modules
- `TODOS.md` — session log entry
- `docs/plan/paper-exit-signals/tasks.md` — tick ES9

**Git archive moves (do not delete — preserve history):**
```bash
git mv docs/council/2026-05-28_paper-trade-exit-philosophy.md \
       docs/council/archive/strategy/

git mv docs/strategies/csp_nifty_v1.md \
       docs/strategies/archive/csp_nifty_v1.md
```

**Deprecation notice** — prepend to archived `csp_nifty_v1.md`:
```markdown
> **ARCHIVED 2026-05-28** — Exit rules codified in `src/strategy/csp_nifty_v1.py`
> (ExitSignalEngine constants) and `docs/plan/paper-exit-signals/`.
> This file is retained for historical reference only. Do not update.
```

**DECISIONS.md entries** — one row per Summary Table decision:

| Date | Decision | Source |
|---|---|---|
| 2026-05-28 | CC profit target: 50% decay, ₹15/unit floor, ₹12 hard minimum | council exit-philosophy |
| 2026-05-28 | CC loss stop: delta ≥ +0.55 primary, 2.5× premium backstop | council exit-philosophy |
| 2026-05-28 | PP exit: hold to expiry; CRASH_MONETIZE at delta ≤ −0.80 + bid/ask ≤ 10% | council exit-philosophy |
| 2026-05-28 | Collar short call profit: 75% decay rule (25% remaining), close call only | council exit-philosophy |
| 2026-05-28 | Collar short call loss: no independent stop; WARN only; full overlay close = MANUAL_OVERRIDE | council exit-philosophy |
| 2026-05-28 | Collar put profit: no early exit; CRASH_MONETIZE same as PP | council exit-philosophy |
| 2026-05-28 | Static exits for Phase 0; regime conditioning deferred to ≥24 cycles | council exit-philosophy |
| 2026-05-28 | Automation: Tier 1 EOD mandatory; Tier 2 intraday behind MONITOR_OVERLAYS=1 | council exit-philosophy |
| 2026-05-28 | Storage: paper_exit_events table (not enum column); dual-signal audit mandatory on sell legs | council exit-philosophy |
| 2026-05-28 | CSP thresholds corrected: DELTA_STOP=0.45, LOSS_STOP=1.75× (PB2.1 had 0.35, 2.0×) | council exit-philosophy |

Also add to DECISIONS.md Dissenting Notes section:
> **Noted, deferred (Q2 minority):** Premium-multiple-only stop for Phase 0 (skip delta).
> Validation: compare `delta_stop_would_fire` vs `premium_stop_would_fire` in
> `paper_exit_events` after 6–12 overlay cycles.

**No code changes in ES9.**

**Commit:** `docs(strategy): add paper-exit-signals decisions, archive council + csp_nifty_v1 spec`

# council-refactor — CC Automation Stories

> Shared context, signal tables, ReEntryMixin contract: `README.md`
> Prerequisite: CR0 committed (SHA: 4ce6d99)

---

## CC-1 `[Antigravity]` — Align `evaluate_cc()` to CSP signal structure

**Files:**
- `src/strategy/exit_signals.py`
- `src/strategy/cc_overlay_v1.py` (update caller signature)
- `tests/unit/strategy/test_exit_signals.py`
- `tests/unit/strategy/test_cc_overlay_v1.py`

**Prerequisite:** CR1b committed — `_PROFIT_TARGET_RETENTION` constant introduced there.

**Before any code:**
- `get_code_snippet("ExitSignalEngine.evaluate_cc")` — current signature (underlying_price, strike_price present)
- `get_code_snippet("evaluate_profit_target_csp")` — confirm uses `_PROFIT_TARGET_RETENTION`
- `search_graph("_CC_MIN_ENTRY_CREDIT")` — confirm does NOT yet exist
- `get_code_snippet("CCOverlayV1.check_signals")` — confirm call site for evaluate_cc

**What to change in `exit_signals.py`:**

Add module-level constant (alongside `_PROFIT_TARGET_RETENTION` from CR1b):
```python
_CC_MIN_ENTRY_CREDIT = Decimal("15")  # CC: below this floor, no early exit — ride to DTE_REVIEW
```

Update `evaluate_cc()` signature — add `days_held: int`, remove `underlying_price` and
`strike_price` (only used by the old DTE_FORCED ITM check, which is replaced by DTE_REVIEW):

```python
@classmethod
def evaluate_cc(
    cls,
    *,
    entry_price: float,
    current_mark: float,
    delta: float | None,
    dte: int,
    days_held: int,
) -> list[ExitSignalResult]:
    """Evaluate exit signals for a Covered Call (CC) short call leg.

    Signal set mirrors CSP structure — same signal names, same severity pattern.
    Thresholds differ where direction or covered nature requires it.
    """
```

Signal changes (full aligned set):

| Signal | Old | New |
|---|---|---|
| `BELOW_FLOOR` | entry < 12 → INFO | unchanged |
| `PROFIT_TARGET` | mark ≤ 50% of entry, entry ≥ 15 | mark ≤ `_PROFIT_TARGET_RETENTION` (30%) of entry, entry ≥ `_CC_MIN_ENTRY_CREDIT` |
| `LOSS_STOP` | mark ≥ 2.5× entry | unchanged |
| `DELTA_STOP` | delta ≥ 0.55 | unchanged |
| `DELTA_WARN` | delta ≥ 0.45 | unchanged |
| `TIME_STOP` | did not exist | days_held ≥ 21 → ACTION (same threshold as CSP) |
| `DTE_FORCED` | DTE ≤ 5 AND (ITM OR delta ≥ 0.30 OR residual ≥ 5) → ACTION | **removed** |
| `DTE_REVIEW` | did not exist | DTE ≤ 5 → WARN (no conditions) |

`DTE_FORCED` is gone entirely. `DTE_REVIEW` replaces it with a flat WARN — no ITM/delta/residual
sub-conditions. Re-entry gating is handled by `ReEntryMixin`, not the exit signal.

**Update `CCOverlayV1.check_signals()`:**

Remove `underlying_price` and `strike_price` from the `evaluate_cc()` call site.
Add `days_held` calculation (same pattern as CSPNiftyV1):
```python
days_held = (today - pos.entry_date).days if pos.entry_date is not None else 0
```

**Tests (`tests/unit/strategy/test_exit_signals.py`):**

`evaluate_cc` — PROFIT_TARGET:
- `entry=20.0, mark=5.9, days_held=5, dte=20` → fires (5.9 ≤ 20 × 0.30 = 6.0)
- `entry=20.0, mark=6.1, days_held=5, dte=20` → `[]` (6.1 > 6.0)
- `entry=14.0, mark=3.0, days_held=5, dte=20` → `[]` (entry < _CC_MIN_ENTRY_CREDIT)
- `entry=15.0, mark=4.5, days_held=5, dte=20` → fires (boundary inclusive)

`evaluate_cc` — TIME_STOP:
- `entry=20.0, mark=15.0, days_held=21, dte=20` → TIME_STOP ACTION
- `days_held=20` → `[]`
- `days_held=21, dte=4` → both TIME_STOP AND DTE_REVIEW fire

`evaluate_cc` — DTE_REVIEW:
- `dte=5` → DTE_REVIEW WARN (no conditions checked — always fires at DTE ≤ 5)
- `dte=6` → `[]`
- `dte=4, delta=0.70` → DTE_REVIEW WARN (not ACTION — delta stop fires separately)

`evaluate_cc` — DTE_FORCED gone:
- `dte=3, delta=0.70, underlying > strike` → no DTE_FORCED signal; DELTA_STOP fires instead

`evaluate_cc` — DELTA_WARN suppressed when DELTA_STOP fires (elif coupling):
- `delta=0.60, entry=20.0, mark=15.0, days_held=5, dte=20` → `[DELTA_STOP]` only; no DELTA_WARN
  *(DELTA_WARN uses `elif`, so it is skipped when DELTA_STOP fires. Lock this in a test to prevent drift.)*
- `delta=0.47, entry=20.0, mark=15.0, days_held=5, dte=20` → `[DELTA_WARN]` only (below DELTA_STOP threshold)

`evaluate_cc` — sort order:
- LOSS_STOP + DELTA_STOP both true → both returned; ACTION before WARN

**Tests (`tests/unit/strategy/test_cc_overlay_v1.py`):**
- `check_signals` with days_held=21 → TIME_STOP ACTION in events
- `check_signals` with `pos.entry_date=None` → no crash; days_held defaults to 0

**Commit:** `feat(strategy): align evaluate_cc to CSP — TIME_STOP, DTE_REVIEW, _PROFIT_TARGET_RETENTION`

---

## CC-2 `[Antigravity]` — `ReEntryMixin` in `src/strategy/reentry_mixin.py`

**Files:**
- `src/strategy/reentry_mixin.py` (new)
- `tests/unit/strategy/test_reentry_mixin.py` (new)

**Prerequisite:** None — independent of all other stories.

**Before any code:**
- `get_code_snippet("CSPNiftyV1._check_r5_reentry")` — copy gate logic verbatim; this becomes the mixin body
- `get_code_snippet("ExitSignal")` — confirm R5_REENTRY_ELIGIBLE and R5_REENTRY_BLOCKED values
- `search_graph("ReEntryMixin")` — confirm does NOT yet exist

**What to implement:**

```python
# src/strategy/reentry_mixin.py

class ReEntryMixin:
    """Mixin providing post-close re-entry eligibility gates for short-premium strategies.

    Concrete class must define as class attributes:
        strategy_name: str          — used in paper_exit_events rows
        reentry_leg_role: str       — leg role to check for open position gate
        reentry_script_hint: str    — shown in Telegram notification on ELIGIBLE

    Concrete class must provide as instance attributes:
        _store: PaperStore | None
        _notifier: object | None    — must have send_plain_message coroutine
        _vix_data_dir: Path
    """

    strategy_name: str
    reentry_leg_role: str
    reentry_script_hint: str

    async def _check_reentry(
        self,
        expiry: date | None,
        today: date,
        instrument_key: str,
    ) -> None:
        """Three-gate re-entry eligibility check. Writes paper_exit_events row.
        Sends Telegram notification. Non-fatal — errors logged, never raised.

        Gate 1: (expiry - today).days >= 14
        Gate 2: IVR >= 0.25 (conservative block if history insufficient)
        Gate 3: No open position with leg_role == self.reentry_leg_role
        """
```

Gate logic: copy verbatim from `CSPNiftyV1._check_r5_reentry`.

Telegram message format:
```
✅ {strategy_name} Re-entry ELIGIBLE — {reentry_script_hint}
```
or:
```
⛔ {strategy_name} Re-entry BLOCKED
{blocked_reason}
```

**Tests (`tests/unit/strategy/test_reentry_mixin.py`):**

Use a minimal concrete class:
```python
class _TestStrategy(ReEntryMixin):
    strategy_name = "test_strategy"
    reentry_leg_role = "short_put"
    reentry_script_hint = "run find_strike_by_delta.py"
    # _store, _notifier, _vix_data_dir injected in tests
```

- All gates pass → writes R5_REENTRY_ELIGIBLE; notifier called with ELIGIBLE message
- Gate 1 fails (DTE < 14) → R5_REENTRY_BLOCKED; reason contains "DTE"
- Gate 2 fails (IVR < 0.25) → R5_REENTRY_BLOCKED; reason contains "IVR"
- Gate 3 fails (open position exists) → R5_REENTRY_BLOCKED; reason contains "open position"
- `_store=None` → logs warning; no crash
- `_notifier=None` → writes event; no crash
- IVR history insufficient (< 252 bars) → R5_REENTRY_BLOCKED conservatively
- Multiple gates fail → first failing gate's reason recorded (gates are sequential)

**Commit:** `feat(strategy): ReEntryMixin with three-gate re-entry check; Telegram notification`

---

## CC-3 `[Claude]` — Migrate `CSPNiftyV1` to `ReEntryMixin` + fix `TIME_STOP` re-entry gap

**Files:**
- `src/strategy/csp_nifty_v1.py`
- `tests/unit/strategy/test_csp_nifty_v1.py`

**Prerequisite:** CC-2 committed.

**Before any code:**
- `get_code_snippet("ReEntryMixin")` — confirm CC-2 committed; get class attr names
- `get_code_snippet("CSPNiftyV1._check_r5_reentry")` — will be deleted; confirm it matches mixin
- `get_code_snippet("CSPNiftyV1.apply_action")` — confirm current PROFIT_TARGET path only

**Changes:**

1. Inherit `ReEntryMixin`:
   ```python
   class CSPNiftyV1(ReEntryMixin):
   ```

2. Add class attributes:
   ```python
   reentry_leg_role: str = "short_put"
   reentry_script_hint: str = "run find_strike_by_delta.py"
   ```

3. Remove `_check_r5_reentry` method entirely (mixin provides `_check_reentry`).

4. In `apply_action`, call `_check_reentry` for **both** `PROFIT_TARGET` and `TIME_STOP`:

   ```python
   if action.action_type in ("PROFIT_TARGET", "TIME_STOP"):
       if closed_pos is not None:
           expiry = self._parse_expiry(closed_pos.instrument_key)
           await self._check_reentry(
               expiry=expiry,
               today=date.today(),
               instrument_key=closed_pos.instrument_key,
           )
   ```

   Previously only `PROFIT_TARGET` triggered this. `TIME_STOP` was silently skipping re-entry evaluation — a gap.

**Tests:**
- `apply_action("PROFIT_TARGET")` → `_check_reentry` called once
- `apply_action("TIME_STOP")` → `_check_reentry` called once (was not called before — regression test)
- `apply_action("CLOSE_FULL")` → `_check_reentry` NOT called
- All existing tests must remain green

**Commit:** `refactor(strategy): CSPNiftyV1 inherits ReEntryMixin; fix TIME_STOP missing re-entry check`

---

## CC-4 `[Antigravity]` — `CCOverlayV1` full automation

**Files:**
- `src/strategy/cc_overlay_v1.py`
- `tests/unit/strategy/test_cc_overlay_v1.py`

**Prerequisite:** CC-1 (aligned signals + days_held), CC-2 (ReEntryMixin), CR1d (StrategyMonitor auto-execute path + `send_notification`).

**Before any code:**
- `get_code_snippet("CCOverlayV1")` — confirm CC-1 caller update already removed underlying_price/strike_price
- `get_code_snippet("ReEntryMixin")` — confirm CC-2 committed; class attr names
- `get_code_snippet("StrategyMonitor._dispatch_event")` — confirm auto-execute path exists (CR1d gate)
- `get_code_snippet("OverlayCloser")` — confirm close mechanism for CC leg
- `search_graph("send_notification")` — confirm TelegramGateway has this (CR1d gate)

**Changes to `cc_overlay_v1.py`:**

1. Inherit `ReEntryMixin`:
   ```python
   class CCOverlayV1(ReEntryMixin):
   ```

2. Add class attributes:
   ```python
   auto_execute: bool = True
   reentry_leg_role: str = "overlay_cc"
   reentry_script_hint: str = "run find_overlay_strikes.py --overlay-type cc"
   ```

3. Constructor: accept and store `store`, `notifier`, `vix_data_dir` (currently CCOverlayV1 has no `__init__`).
   ```python
   def __init__(
       self,
       store: Any = None,
       notifier: Any = None,
       vix_data_dir: Path | str | None = None,
   ) -> None:
   ```

4. `check_signals()` — add `auto_execute` and `auto_action` to ACTION payloads:

   Signal → action mapping (module-level constant):
   ```python
   _CC_SIGNAL_ACTION_MAP: dict[str, str] = {
       "PROFIT_TARGET": "CLOSE_CC",
       "LOSS_STOP":     "CLOSE_CC",
       "DELTA_STOP":    "CLOSE_CC",
       "TIME_STOP":     "CLOSE_CC",
   }
   ```

   For ACTION results, payload includes:
   ```python
   payload["auto_execute"] = True
   payload["auto_action"] = "CLOSE_CC"
   payload["valid_actions"] = ["CLOSE_CC"]
   payload["triggering_signal"] = result.exit_signal  # needed by apply_action for re-entry gate
   ```

   WARN and INFO results: payload unchanged (no auto_execute key).

5. `apply_action()` — handle `CLOSE_CC`:

   ```python
   async def apply_action(
       self,
       positions: list[PaperPosition],
       action: ApprovedAction,
   ) -> list[PaperPosition]:
       if action.action_type != "CLOSE_CC":
           raise ValueError(f"CCOverlayV1 only accepts CLOSE_CC; got {action.action_type!r}")

       # Close the CC leg via OverlayCloser
       closed_pos = next(
           (p for p in positions if p.leg_role == "overlay_cc" and p.net_qty < 0),
           None,
       )
       updated = [p for p in positions if p.leg_role != "overlay_cc"]

       # Re-entry check for PROFIT_TARGET and TIME_STOP only
       triggering_signal = action.metadata.get("triggering_signal") if action.metadata else None
       if triggering_signal in ("PROFIT_TARGET", "TIME_STOP") and closed_pos is not None:
           expiry = self._parse_expiry(closed_pos.instrument_key)
           await self._check_reentry(
               expiry=expiry,
               today=date.today(),
               instrument_key=closed_pos.instrument_key,
           )

       # Telegram notification (non-fatal)
       await self._send_close_notification(closed_pos, triggering_signal)

       return updated
   ```

6. `_send_close_notification` — HTML notification via `self._notifier.send_notification`:

   ```
   ✅ <b>CC: CLOSE ({signal})</b>
   📤 Closed: {instrument_key} @ ₹{exit_price:.2f}
      Entry ₹{entry_credit:.2f} · Delta {delta:.3f} · DTE {dte}
   ```

   Non-fatal: wrap in try/except, log error, never raise.

**Tests (`tests/unit/strategy/test_cc_overlay_v1.py`):**

`check_signals` — auto-execute payload:
- PROFIT_TARGET fires → payload has `auto_execute=True`, `auto_action="CLOSE_CC"`, `triggering_signal="PROFIT_TARGET"`
- DELTA_WARN fires → payload has no `auto_execute` key (WARN only)
- DTE_REVIEW fires → payload has no `auto_execute` key (WARN only)
- TIME_STOP fires → `auto_execute=True`, `triggering_signal="TIME_STOP"`

`apply_action`:
- `CLOSE_CC` triggered by PROFIT_TARGET → `_check_reentry` called
- `CLOSE_CC` triggered by TIME_STOP → `_check_reentry` called
- `CLOSE_CC` triggered by LOSS_STOP → `_check_reentry` NOT called
- `CLOSE_CC` triggered by DELTA_STOP → `_check_reentry` NOT called
- `action_type="CLOSE_FULL"` → raises `ValueError`
- `notifier=None` → close executes without crash
- `store=None` → close executes; re-entry check skips gracefully

Re-entry notification:
- PROFIT_TARGET close with all gates passing → `send_notification` called with ELIGIBLE message containing `find_overlay_strikes.py`
- LOSS_STOP close → `send_notification` called with close notification; NO re-entry notification

**Commit:** `feat(strategy): CCOverlayV1 full automation — auto_execute, ReEntryMixin, close notification`

---

## CC-5 `[Antigravity]` — `scripts/paper_cc_roll.py`: manual override exit handler

> **Context:** `CCOverlayV1` (CC-4) handles automated EOD exit evaluation. This script is the
> manual inspection and override path — dry-run, mid-session emergency close, or operator-triggered
> exit outside the daemon cycle. Thresholds must match `evaluate_cc()` exactly.

**Files to change:**
- `scripts/strategies/cc_calibration/paper_cc_roll.py` — new script
  (mirrors `scripts/strategies/csp/paper_csp_roll.py` path convention)

**Prerequisite:** CC-1 committed (corrected signal thresholds in `evaluate_cc`).

**Before any code:**
- `get_code_snippet("ExitSignalEngine.evaluate_cc")` — get exact thresholds post-CC-1
- `get_code_snippet("STRATEGY_CC_OVERLAY")` — confirm constant from `src/paper/constants.py`
- `get_code_snippet("PaperStore")` — get `get_trades` / close API
- `get_code_snippet("PaperTrade")` — get exact field list (entry_price, net_qty, leg_role, closed_at, expiry, entry_date)
- `search_code("paper_csp_roll")` in `scripts/` — mirror the CSP roll CLI pattern

**Entry point:** `python -m scripts.strategies.cc_calibration.paper_cc_roll [--dry-run] [--force]`

```
Flags:
  --dry-run   Show trigger status and close command; do not execute.
  --force     Bypass "no open CC leg" guard for manual override.
```

**Three pure trigger functions** (unit-testable, no I/O) — thresholds match `evaluate_cc()` post-CC-1:

```python
def profit_target_hit(entry_credit: Decimal, current_ltp: Decimal) -> bool:
    """Return True if call has decayed to ≤ 30% of entry credit (70% profit captured).

    Threshold mirrors _PROFIT_TARGET_RETENTION in exit_signals.py.
    Only fires if entry_credit >= _CC_MIN_ENTRY_CREDIT (Decimal("15")).

    Args:
        entry_credit: Credit collected per unit at entry (positive Decimal).
        current_ltp: Current mark-to-market LTP of the call (positive Decimal).

    Returns:
        True if entry_credit >= 15 AND current_ltp <= entry_credit * Decimal("0.30").
    """

def time_stop_hit(entry_date: date, today: date, days: int = 21) -> bool:
    """Return True if calendar days since entry >= days.

    Args:
        entry_date: Date the CC leg was opened (UTC date).
        today: Evaluation date (UTC date).
        days: Time stop in calendar days (default 21 — matches evaluate_cc TIME_STOP).

    Returns:
        True if (today - entry_date).days >= days.
    """

def delta_stop_hit(current_delta: float, threshold: float = 0.55) -> bool:
    """Return True if call delta has crossed the delta stop threshold.

    Threshold matches evaluate_cc DELTA_STOP (0.55). Note: delta_warn fires at 0.45
    (informational only — not an exit trigger for the CLI).

    Args:
        current_delta: Current absolute delta of the call (positive float, 0–1).
        threshold: Delta stop level (default 0.55).

    Returns:
        True if current_delta >= threshold.
    """

def loss_stop_hit(entry_credit: Decimal, current_ltp: Decimal, multiplier: float = 2.5) -> bool:
    """Return True if current mark has exceeded multiplier × entry credit (loss stop).

    Threshold matches evaluate_cc LOSS_STOP (2.5×).

    Args:
        entry_credit: Credit collected per unit at entry (positive Decimal).
        current_ltp: Current mark-to-market LTP of the call (positive Decimal).
        multiplier: Loss stop multiplier (default 2.5).

    Returns:
        True if current_ltp >= entry_credit * Decimal(str(multiplier)).
    """
```

**Script flow (`async def run()`):**

1. Load open CC leg via `PaperStore.get_trades(STRATEGY_CC_OVERLAY)` — filter for open legs
   (`closed_at is None`, `leg_role == "covered_call"`).
2. If no open leg: print `No open covered_call leg for paper_covered_call_v1.` and exit 0
   (unless `--force`).
3. Fetch current LTP + delta for the CC leg instrument key from Upstox option chain.
4. Evaluate all four triggers in priority order (mirrors `evaluate_cc` signal priority):
   - `loss_stop_hit(entry_credit, current_ltp)` — priority 1 (LOSS_STOP)
   - `delta_stop_hit(current_delta)` — priority 2 (DELTA_STOP, threshold 0.55)
   - `profit_target_hit(entry_credit, current_ltp)` — priority 3 (PROFIT_TARGET, 30% remaining)
   - `time_stop_hit(entry_date, today)` — priority 4 (TIME_STOP, 21 days)
5. Print trigger status for all four:
   ```
   Loss stop:      ⬜ not hit  (LTP ₹80.00 / 2.5× entry ₹155.00)
   Delta stop:     ⬜ not hit  (delta 0.38 / 0.55 limit)
   Profit target:  ✅ HIT  (LTP ₹18.00 ≤ 30% of entry ₹62.00)
   Time stop:      ⬜ not hit  (14 days held / 21 limit)
   ```
   Also print delta warn if delta ≥ 0.45 (informational — does not trigger close):
   ```
   ⚠️  Delta warn: delta 0.47 approaching stop (0.55). Monitor closely.
   ```
6. If any trigger fires: print the highest-priority trigger name and the close command:
   ```
   Trigger: profit_target

   python -m scripts.record_paper_trade \
     --strategy paper_covered_call_v1 \
     --leg-role covered_call \
     --action BUY \
     --strike 24800 \
     --expiry 2026-06-26 \
     --qty 65 \
     --close \
     --notes "exit: profit_target; LTP=18.00; entry=62.00; delta=0.38"
   ```
7. If `--dry-run`: stop. Otherwise prompt `Execute close? [y/N]`.
8. On `y`: execute the close command. Print confirmation.

**No unit tests for the script itself** (live I/O). Unit tests cover the four pure trigger functions.

**Tests (`tests/unit/paper/test_cc_roll.py`):**

`profit_target_hit`:
- `entry=Decimal("62"), ltp=Decimal("18.60")` → True (18.60 ≤ 62 × 0.30 = 18.60, boundary inclusive)
- `entry=Decimal("62"), ltp=Decimal("18.61")` → False (above 30% threshold)
- `entry=Decimal("62"), ltp=Decimal("0")` → True (expired worthless)
- `entry=Decimal("14"), ltp=Decimal("3")` → False (entry < _CC_MIN_ENTRY_CREDIT floor of 15)
- `entry=Decimal("15"), ltp=Decimal("4.50")` → True (boundary of floor, exactly at 30%)

`time_stop_hit`:
- Entry 21 days ago → True.
- Entry 20 days ago → False.
- Entry today → False.
- Entry 30 days ago → True.

`delta_stop_hit`:
- `delta=0.55` → True (at threshold).
- `delta=0.56` → True (above threshold).
- `delta=0.54` → False (below threshold).
- `delta=0.15` → False (normal healthy CC).

`loss_stop_hit`:
- `entry=Decimal("62"), ltp=Decimal("155.00")` → True (exactly 2.5×)
- `entry=Decimal("62"), ltp=Decimal("154.99")` → False (just below)
- `entry=Decimal("62"), ltp=Decimal("200")` → True (above 2.5×)
- `entry=Decimal("62"), ltp=Decimal("62")` → False (at-entry, no loss)

**Commit:** `feat(scripts): paper_cc_roll.py — loss-stop, delta-stop (0.55), profit-target (30%), time-stop exit handler`

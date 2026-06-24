# IC-E1 — `auto_execute` attribute + `STRATEGY_IC` constant

> **Assigned to: Claude** — single-file fix; requires graph lookup on IronCondorV1 class body.

**Files to change:**
- `src/strategy/ic_nifty_v1.py` — add `auto_execute: bool = False` class attribute
- `src/paper/constants.py` — add `STRATEGY_IC = "paper_ic_nifty_v1"`
- `tests/unit/strategy/test_ic_nifty_v1.py` — add protocol-compliance test

---

## Context

`StrategyMonitor._dispatch` reads `auto_execute` via `getattr(strategy, "auto_execute", False)`.
Without the attribute, the fallback silently routes all IC ACTION signals to Telegram approval —
which is the correct behaviour — but the intent is invisible and diverges from all other strategy
classes (`CSPNiftyV1`, `CCOverlayV1`, etc. all declare it explicitly).

`src/paper/constants.py` already declares `STRATEGY_CSP`, `STRATEGY_CC_OVERLAY`, etc.
`IronCondorV1.strategy_name = "paper_ic_nifty_v1"` is the only place this string exists.
`paper_ic_snapshot.py` (IC-E4) and `paper_ic_entry.py` (IC-E2) both need the constant.
Add it now so downstream stories can import it.

The IC spec mandates no adjustments in v1 (`docs/strategies/ic_nifty_v1.md` — Adjustment Rule).
`auto_execute = False` is consistent with that: every ACTION signal routes to human approval
via Telegram. This is also consistent with `NiftyTrackComparisonV1.auto_execute = False`.

---

## What to implement

### 1. `src/strategy/ic_nifty_v1.py`

Add the class attribute immediately after `strategy_name`:

```python
strategy_name: str = "paper_ic_nifty_v1"
auto_execute: bool = False
```

No other changes to `ic_nifty_v1.py`.

### 2. `src/paper/constants.py`

Add after the existing `STRATEGY_COLLAR_OVERLAY` line:

```python
STRATEGY_IC = "paper_ic_nifty_v1"
```

---

## Tests (`tests/unit/strategy/test_ic_nifty_v1.py`)

**New happy-path test:**
- Instantiate `IronCondorV1(broker=..., store=..., notifier=...)` and assert
  `strategy.auto_execute is False`. Also assert `strategy.strategy_name == "paper_ic_nifty_v1"`.

**New protocol-compliance test:**
- Import `STRATEGY_IC` from `src.paper.constants` and assert it equals
  `IronCondorV1.strategy_name`. Ensures the constant and the class stay in sync.

All existing tests must still pass — no behaviour changes.

---

## Commit

```
feat(strategy): add auto_execute=False to IronCondorV1 + STRATEGY_IC constant

Why: StrategyMonitor uses getattr fallback today; explicit attribute matches
all other strategy classes and documents IC's human-approval-only intent.
What:
- src/strategy/ic_nifty_v1.py: auto_execute: bool = False class attribute
- src/paper/constants.py: STRATEGY_IC = "paper_ic_nifty_v1"
- tests/unit/strategy/test_ic_nifty_v1.py: 2 new protocol-compliance tests
Ref: ic-e2e IC-E1
```

---

## Pre-baked Context

**`IronCondorV1`** class body starts at line 69 of `src/strategy/ic_nifty_v1.py`.
`strategy_name: str = "paper_ic_nifty_v1"` is the first class-level attribute (line ~89).
`auto_execute` does not exist in the file — confirmed by grep returning no results.

**`src/paper/constants.py`** — existing strategy constants (lines 22–27):
```python
STRATEGY_SPOT = "paper_nifty_spot"
STRATEGY_FUTURES = "paper_nifty_futures"
STRATEGY_PROXY = "paper_nifty_proxy"
STRATEGY_CSP = "paper_csp_nifty_v1"
STRATEGY_CC_OVERLAY = "paper_covered_call_v1"
STRATEGY_PP_OVERLAY = "paper_protective_put_v1"
STRATEGY_COLLAR_OVERLAY = "paper_collar_v1"
```
Add `STRATEGY_IC` as the next line.

**`IronCondorV1.__init__`** signature (from graph):
`__init__(self, broker: BrokerClient, store: PaperStore, notifier: TelegramGateway)`.
Use `MockBrokerClient`, a real or mock `PaperStore`, and a mock `TelegramGateway` in tests —
same pattern as existing `test_ic_nifty_v1.py` fixtures.

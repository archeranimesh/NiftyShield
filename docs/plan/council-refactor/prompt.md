# council-refactor — Design Prompt

## What This Story Builds

Removes `RapidCouncil` from the paper trading daemon approval path and replaces it
with deterministic, backtestable roll rules baked into `ExitSignalEngine`.

Fixes a latent runtime bug where `StrategyMonitor` calls
`send_approval_request(event, context_str)` but `TelegramGateway.send_approval_request`
expects `(CouncilOutput, SignalEvent, str)` — a signature mismatch that would raise
`TypeError` the first time any ACTION event fires in a live daemon run.

When this story is complete:
1. The daemon approval path has no LLM API calls — signals go directly to Telegram
2. CSP roll: DTE ≤ 5 fires `ROLL_ELIGIBLE` ACTION; `csp_roll_executor` closes current
   leg and reopens via `strike_selector` (first ranked candidate); fully automated via daemon
3. 3-track overlay roll: DTE ≤ 5 fires `ROLL_ELIGIBLE` with suggested ATM±50 strike;
   base-DTE guard blocks overlay roll when base DTE ≤ 10
4. `evaluate_roll_csp` and `evaluate_roll_overlay` are pure functions in `ExitSignalEngine`
   returning `list[ExitSignalResult]` — replayable against historical data
5. `strike_selector.py` lives in `src/instruments/` — importable by any module that needs
   delta-filtered, liquidity-gated strike selection
6. `csp_roll_executor.py` lives in `src/strategy/` — shared by the daemon and CLI script
7. `RapidCouncil` remains as a module but is **not wired** anywhere in Phase 0

---

## Why the Council Does Not Belong Here

### Paper trading exits are single-option decisions

`ExitSignalEngine` already determines whether to exit and why. Each strategy's
`apply_action()` accepts a fixed set of action types — `CLOSE_FULL` for CSP, `CLOSE_CC`
for CC, `MONETIZE_PP` for PP. There is nothing to deliberate: the action is determined
before the council would be asked.

### Roll decisions must be backtestable

Roll decisions (what strike, what expiry) must be deterministic given the same market
inputs so they can be replayed against historical data. An LLM council call is:
- Non-deterministic across runs
- Model-version-dependent (GPT-4o today ≠ GPT-4o in six months)
- Incapable of time-travel (replaying 2025 data through a 2026 model leaks hindsight)

A roll decision driven by the council cannot be statistically validated via backtest.
A roll decision driven by `evaluate_roll_csp(dte)` — "roll when DTE ≤ 5" — can be.

### The council belongs in live trading for genuinely ambiguous decisions

The council earns its place when:
- Real capital is at stake (wrong decision is not reversible)
- The action space has multiple defensible options (IC leg-selective exit, live sizing)
- The strategy spec does not resolve the choice

None of these conditions hold during Phase 0 paper trading exits. The council should be
wired in at Phase 1 (live trading) for specific scenarios — not as a blanket gate on
every paper trade ACTION event.

---

## Deterministic Roll Rules

### Design decisions (finalised 2026-06-04)

**No `RollSignalResult`.** Roll signals are returned as `list[ExitSignalResult]` — the
same type as every other `ExitSignalEngine` evaluator. `exit_signal="ROLL_ELIGIBLE"` or
`"ROLL_BASE_FIRST"` is what distinguishes them. This keeps return types uniform and
lets `CSPNiftyV1.check_signals` merge exit + roll results without type juggling.

**No IVR-tiered strike selection in the engine.** Strike selection is delegated to
`src/instruments/strike_selector.py` (extracted from `find_strike_by_delta.py`) which
already applies delta filter, liquidity gate, and ranking. The engine stays pure — it
detects *when* to roll, not *what* strike to roll to.

**Execution layer: `src/strategy/csp_roll_executor.py`.** Contains importable
`close_csp_leg()` and `open_new_csp_leg()` functions, extracted from
`scripts/strategies/csp/paper_csp_roll.py`. Both the CLI script and `CSPNiftyV1.apply_action`
import from this module. `paper_csp_roll.py` becomes a thin CLI wrapper.

---

### CSP — `ExitSignalEngine.evaluate_roll_csp()`

**Trigger:** `dte ≤ 5` on the short put leg.

(TIME_STOP at `days_held ≥ 21` already fires as `CLOSE_FULL` via `evaluate_csp`. The
roll trigger is expiry proximity only — the operator decides whether to re-enter.)

**Output:** `list[ExitSignalResult]` with one element:
```python
ExitSignalResult(
    exit_signal="ROLL_ELIGIBLE",
    severity="ACTION",
    threshold_value=5.0,
    notes="DTE {dte} ≤ 5 — close and reopen via strike_selector",
)
```
Returns `[]` when `dte > 5`.

**Execution path when user approves `CLOSE_AND_ROLL`:**
1. `CSPNiftyV1.apply_action("CLOSE_AND_ROLL")` calls `csp_roll_executor.close_csp_leg()`
2. Then calls `strike_selector.filter_strikes_by_delta()` + `rank_strikes()` — picks index 0
3. Then calls `csp_roll_executor.open_new_csp_leg()` with the selected strike
4. Atomicity: if open fails, close is rolled back via `store.delete_trade()`

`CSPNiftyV1.__init__` stores `self._broker = broker` (parameter already accepted but
previously discarded).

---

### 3-Track Overlays — `ExitSignalEngine.evaluate_roll_overlay()`

**Trigger:** `dte ≤ 5` on any overlay leg.

**Guard:** if `base_dte ≤ 10`, block overlay roll — base rolls first.
Returns `ROLL_BASE_FIRST` WARN:
```python
ExitSignalResult(
    exit_signal="ROLL_BASE_FIRST",
    severity="WARN",
    threshold_value=10.0,
    notes="Base DTE={base_dte} ≤ 10 — roll base first",
)
```

**Strike selection (advisory only — actual selection via `strike_selector`):**

| Overlay leg | Suggested offset | Rationale |
|---|---|---|
| Short call (CC / Collar) | ATM + 50 | Slightly OTM — avoid early assignment on roll day |
| Long put (PP / Collar) | ATM − 50 | Slightly OTM — cost-effective protection |

The `notes` field carries the suggested strike for the Telegram message. The roll script
makes the final selection via `strike_selector`.

**Expiry selection:** next monthly Tuesday expiry from BOD. If `base_dte ≤ 60`, align
overlay expiry to base expiry.

Returns `[]` when `dte > 5`.

---

## Approval Flow After Refactor

```
Signal detected (EOD cron or daemon tick)
        ↓
ExitSignalEngine evaluates rules
        ↓
Single valid action? ──────────────────────────────────────────→ Telegram message
  (CSP CLOSE_FULL, CC CLOSE_CC, PP MONETIZE_PP, ROLL_ELIGIBLE)    with pre-built
        ↓                                                           action options
Multiple valid actions?                                                   ↓
  (IC CLOSE_FULL / CLOSE_CALL_SPREAD / CLOSE_PUT_SPREAD)         You tap approve
        ↓                                                                 ↓
  Telegram with all valid options listed                          PaperExecutor
  You choose one
        ↓
  PaperExecutor
```

No LLM call in any path. `CouncilOutput` is not required by `send_approval_request`.
The action options come from the strategy's known action space, not from council deliberation.

---

## Where RapidCouncil Stays (Future)

`src/council/rapid.py` is **retained but unwired**. It belongs in:

- **IC leg-selective exits in live trading** — when real capital is at stake and the
  choice between CLOSE_FULL vs. CLOSE_CALL_SPREAD has meaningful P&L consequences
- **Roll parameter decisions in live trading** — if the deterministic rules prove
  insufficient over paper observation cycles and require context-sensitive override
- **Novel signals outside the codified rule set** — situations the spec does not cover

The criterion for wiring council into any future story:
> The action space has ≥ 2 defensible options AND real capital is at stake AND the strategy
> spec does not resolve the choice.

---

## Relationship to Other Stories

| Story | Relationship |
|---|---|
| `paper-backbone` | Provides `PaperStrategy`, `StrategyMonitor`, `TelegramGateway` — this story fixes the bug those introduced |
| `paper-exit-signals` | Provides `ExitSignalEngine` — this story extends it with `evaluate_roll_csp` and `evaluate_roll_overlay` |
| `signals` | Signal pipeline has its own purpose-built multi-model consensus — independent of `RapidCouncil`, unaffected by this story |
| `broker-abstraction` | Phase 1 live trading — correct place to re-evaluate council wiring |
| **OD-1→OD-4** (`stories_db_decouple.md`) | Overlay DB decoupling — removes per-track overlay replication; overlays stored once under `paper_overlays`, track association in code via `track_overlay_config.py`. **NT-2 must be updated after OD-2 ships**: replace hardcoded `_FUTURES_BLOCKED_ROLES` frozenset with `is_overlay_allowed(Track.FUTURES, role)` call. Sequence: OD-1 → OD-2 → OD-3 → OD-4 → NT-2 update. |

---

## Prerequisites

Before CR0:
```
search_graph("ExitSignalEngine")      # must exist (ES1 committed)
search_graph("StrategyMonitor")       # must exist (PB1.2 committed)
search_code("send_approval_request")  # confirm signature mismatch in monitor.py
```

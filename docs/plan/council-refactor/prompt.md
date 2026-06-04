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
2. CSP roll strike + expiry are chosen deterministically from IVR tier and BOD data
3. 3-track overlay roll strike + expiry are chosen deterministically from spot + BOD
4. All roll rules are pure functions in `ExitSignalEngine` — replayable against
   historical data in the same way exit rules already are
5. `RapidCouncil` remains as a module but is **not wired** anywhere in Phase 0

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
A roll decision driven by `evaluate_roll_csp(days_held, dte, ivr, spot, atm_strike)`
can be.

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

### CSP — `ExitSignalEngine.evaluate_roll_csp()`

Triggers when `days_held ≥ 21` (TIME_STOP) OR `dte ≤ 5` on the short put leg.

**IVR-tiered strike selection:**

| IVR range | Roll strike | Rationale |
|-----------|-------------|-----------|
| < 0.25 | No roll (blocked) | R3 floor — low vol, skip cycle |
| 0.25 – 0.35 | ATM | Cautious — premium thin, stay at money |
| 0.35 – 0.50 | ATM − 50 | Standard — one strike below ATM |
| > 0.50 | ATM − 100 | Aggressive — rich premium environment |

Override: if the selected strike has `|delta| > 0.30`, move up one strike (closer to ATM)
until delta constraint is satisfied. Never roll below delta 0.30 — that is too directional.

**Expiry selection:** call `get_expiry_candidates(underlying, today, preference=["monthly"])`
and pick the first candidate with DTE between 21 and 35 days. If none found in that window,
expand to 35–50 days. Log WARNING if no candidate found.

**Output:** `RollSignalResult(signal="ROLL_ELIGIBLE", severity="ACTION", proposed_strike,
proposed_expiry, ivr_tier, reason)` — or `None` when IVR < 0.25.

### 3-Track Overlays — `ExitSignalEngine.evaluate_roll_overlay()`

Triggers when `dte ≤ 5` on any overlay leg.

**Guard:** if the base position DTE is ≤ 10, block the overlay roll — the base rolls first.
Emit `ROLL_BASE_FIRST` WARN instead.

**Strike selection (all tracks):**

| Overlay leg | Roll strike | Rationale |
|-------------|-------------|-----------|
| Short call (CC) | ATM + 50 | Slightly OTM — avoid early assignment on roll day |
| Long put (PP) | ATM − 50 | Slightly OTM — cost-effective protection |
| Collar short call | ATM + 50 | Same as CC |
| Collar long put | ATM − 50 | Same as PP |

**Expiry selection:** next monthly Tuesday expiry from BOD. If base DTE ≤ 60, match
overlay expiry to base expiry (keep them aligned).

**Output:** `RollSignalResult` per leg, or `RollSignalResult(signal="ROLL_BASE_FIRST",
severity="WARN")` when base guard fires.

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

---

## Prerequisites

Before CR0:
```
search_graph("ExitSignalEngine")      # must exist (ES1 committed)
search_graph("StrategyMonitor")       # must exist (PB1.2 committed)
search_code("send_approval_request")  # confirm signature mismatch in monitor.py
```

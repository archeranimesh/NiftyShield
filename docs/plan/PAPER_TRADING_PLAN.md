# NiftyShield — Paper Trading Backbone Plan

> **Status:** Design document. No code exists yet for this system.
> **Depends on:** `BACKTEST_PLAN.md` Phase 0 (current). Read that first.
> **Related:** `CONTEXT.md` · `DECISIONS.md` · `BACKTEST_PLAN.md` · `docs/council/2026-05-02_iron-condor-v1-core-design.md`
> **Load this file when:** planning or implementing anything in `src/strategy/`, `src/council/`,
> or the paper trading monitor/daemon layer.

---

## Design Philosophy

Three principles govern every decision in this plan:

1. **The backbone is strategy-agnostic.** Monitoring logic, council consultation, Telegram
   approval, and synthetic fills are infrastructure. Strategies plug into them — not the
   reverse. A new strategy (short strangle, calendar spread) requires implementing one
   protocol, not touching the backbone.

2. **The LLM is never in the hot path.** The monitor daemon fires on deterministic threshold
   breach. The council runs only after a breach. You approve before anything executes.
   Council latency (15–30s) is acceptable because human approval is already required.

3. **IC v1 uses exits, not adjustments — per council ruling.**
   `docs/council/2026-05-02_iron-condor-v1-core-design.md` (Chairman: Opus, unanimous
   3/4 on no-rolls) mandates exit-only logic for IC v1. The backbone supports adjustment
   capability for future strategies (IC v2, short strangle). IC v1 routes all breach events
   to the exit stack, not the adjustment advisor.

---

## Architecture Overview

```
CRON LAYER
├── 09:00  pre_market_brief.py       (stateless, exits)
├── 09:15  start_paper_monitor.py    (launches daemon, exits)
├── 15:30  stop_paper_monitor.py     (SIGTERM daemon, exits)
└── 15:35  eod_paper_summary.py      (stateless, exits)

DAEMON (09:15–15:30, persistent asyncio process)
└── paper_monitor_daemon.py
    ├── MarketDataProvider (existing BrokerClient sub-protocol)
    │   ├── UpstoxLiveClient        ← paper trading mode
    │   └── HistoricalReplayer      ← backtest mode (Phase PT-5)
    │
    ├── StrategyMonitor             ← Layer 1: deterministic thresholds
    │   └── PaperStrategy (protocol) ← each strategy implements this
    │       └── IronCondorV1        ← first concrete implementation
    │
    ├── RapidCouncil                ← Layer 2: multi-model panel (on breach only)
    │   ├── QuantAnalyst    (Haiku) ← Greeks math, EV, probability
    │   ├── SpecGuardian    (Haiku) ← spec compliance check
    │   ├── RiskManager   (Sonnet) ← tail scenarios, margin impact
    │   └── OptionsStrategist (Sonnet) ← market structure, VIX regime, OI walls
    │       └── Chairman  (Sonnet) ← parallel Stage 1 → immediate synthesis
    │
    ├── ApprovalGateway (protocol)
    │   ├── TelegramGateway         ← paper trading: you approve via phone
    │   └── AutoApprover            ← backtest: auto-accepts council's top pick
    │
    └── PaperExecutor               ← Layer 3: synthetic fills, position update
        ├── PaperFillSimulator      ← paper: mid ± slippage
        └── BacktestFillSim         ← backtest: VIX-regime slippage model

PERSISTENCE (portfolio.sqlite, shared via src/db.py)
├── paper_trades           ← existing (PaperStore)
├── paper_nav_snapshots    ← existing (PaperStore)
├── paper_leg_snapshots    ← existing (PaperStore)
├── paper_alerts           ← existing (planned in TODOS.md)
├── pending_adjustments    ← NEW: approval state machine
├── council_outputs        ← NEW: full council reasoning log
└── daemon_heartbeat       ← NEW: watchdog signal
```

---

## Phase PT-0 — Strategy Protocol & Core Infrastructure

**Target:** June 2026 (after Task 2 PortfolioDeltaTracker ships)
**Owner:** Cowork
**Blocks:** All subsequent phases

### What gets built

**`src/strategy/__init__.py`** — package stub (required for codebase-memory-mcp indexing).

**`src/strategy/protocol.py`** — `PaperStrategy` protocol. Three abstract methods every
strategy must implement:

```python
def check_thresholds(
    self,
    position: PaperPosition,
    market: OptionChain,
) -> list[BreachEvent]:
    """Return breach events if any monitoring threshold is violated."""

def describe_context(
    self,
    position: PaperPosition,
    market: OptionChain,
    breach: BreachEvent,
) -> str:
    """Return structured context string for the council prompt."""

def apply_adjustment(
    self,
    position: PaperPosition,
    adjustment: Adjustment,
) -> PaperPosition:
    """Apply an approved adjustment and return the new position state."""
```

`BreachEvent` is a frozen dataclass: `breach_type: str`, `severity: Literal["INFO","WARN","ACTION"]`,
`current_value: Decimal`, `threshold_value: Decimal`, `description: str`.

`Adjustment` is a frozen dataclass: `adjustment_type: str`, `legs_to_close: list[str]`,
`legs_to_open: list[LegSpec]`, `rationale: str`, `council_rank: int`.

**`src/strategy/monitor.py`** — `StrategyMonitor`. Async polling loop. Polls every 90 seconds
during market hours. On each tick: fetches live option chain for each open paper position,
calls `strategy.check_thresholds()`, raises breach events with `severity == "ACTION"` to the
council pipeline. `severity == "INFO"` is logged silently. `severity == "WARN"` is logged and
sent as a Telegram message (no approval required).

Heartbeat: writes `{timestamp, positions_checked, last_breach}` to `daemon_heartbeat` table
on every poll cycle. Watchdog in `start_paper_monitor.py` checks this on startup — if last
heartbeat > 5 minutes ago and market is open, it restarts the daemon.

**`src/strategy/executor.py`** — `PaperExecutor`. Given an approved `Adjustment`, computes
synthetic fills (mid price ± slippage haircut), updates `paper_trades` via `PaperStore`,
writes a row to `adjustment_log`. Returns updated `PaperPosition`.

**New SQLite tables** (migrations in `PaperStore`):

```sql
CREATE TABLE IF NOT EXISTS pending_adjustments (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy_name   TEXT NOT NULL,
    breach_type     TEXT NOT NULL,
    council_output  TEXT NOT NULL,       -- JSON blob of full council response
    status          TEXT NOT NULL,       -- PENDING | APPROVED | REJECTED | EXPIRED | AUTO
    approved_option INTEGER,             -- which ranked option was chosen (1-indexed)
    expires_at      TEXT NOT NULL,       -- ISO UTC datetime (30 min default)
    telegram_msg_id INTEGER,             -- for editing/deleting the approval message
    created_at      TEXT NOT NULL,
    resolved_at     TEXT
);

CREATE TABLE IF NOT EXISTS daemon_heartbeat (
    id              INTEGER PRIMARY KEY CHECK (id = 1),  -- singleton row
    last_beat       TEXT NOT NULL,       -- ISO UTC datetime
    positions_count INTEGER NOT NULL DEFAULT 0,
    last_breach     TEXT                 -- breach_type of last event, or NULL
);

CREATE TABLE IF NOT EXISTS council_outputs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    pending_adj_id  INTEGER NOT NULL REFERENCES pending_adjustments(id),
    persona         TEXT NOT NULL,       -- QuantAnalyst | SpecGuardian | RiskManager | OptionsStrategist | Chairman
    model           TEXT NOT NULL,       -- e.g. claude-haiku-4-5
    prompt_tokens   INTEGER,
    output_tokens   INTEGER,
    latency_ms      INTEGER,
    response        TEXT NOT NULL,       -- raw text response
    created_at      TEXT NOT NULL
);
```

**Tests:** `tests/unit/strategy/` — protocol conformance, monitor threshold firing, executor
fill simulation, heartbeat write, pending_adjustments state transitions.

---

## Phase PT-1 — Bidirectional Telegram Gateway

**Target:** July 2026
**Owner:** Cowork
**Blocked by:** PT-0

The existing `src/notifications/` is outbound-only (fire-and-forget). This phase adds an
inbound polling bot that runs as a task within the daemon's asyncio event loop.

### What gets built

**Dependency:** `python-telegram-bot>=21.0` added to `requirements.txt`. Uses async polling
mode — no webhook, no public URL required. Compatible with the existing asyncio event loop.

**`src/notifications/telegram_gateway.py`** — `TelegramGateway`. Extends the notification
pattern (non-fatal, `build_gateway()` returns `None` when unconfigured) with:

- `send_approval_request(adj: PendingAdjustment) → int`: sends an inline keyboard message
  with council-ranked options. Returns the Telegram `message_id` for tracking.
- `start_polling(callback: ApprovalCallback) → None`: starts the async polling loop.
  Handles `CallbackQuery` (button press) and routes to the approval callback.
- `send_info(message: str) → bool`: same contract as the existing notifier's `send()`.

Inline keyboard layout for an adjustment request:
```
⚠️ NIFTY IC — Short Call delta hit 0.36
Spot: 24,180 | Strike: 24,000 | DTE: 12 | P&L: -₹2,340

QuantAnalyst + RiskManager: Roll call spread to 24,500
OptionsStrategist: Close full IC (trending move, don't fight it)
SpecGuardian: Both options comply with ic_nifty_v1.md

[1] Roll call spread → 24,500 (+₹12 credit est.)
[2] Close full IC (–₹2,340 locked loss)
[3] Do nothing (monitor continues, re-alerts in 15 min)

⏱ Expires in 28 min → auto "Do nothing"
```

**Inbound commands** (registered as `CommandHandler`):

| Command | Response |
|---|---|
| `/status` | Open positions, current Greeks, unrealized P&L |
| `/pnl` | Cumulative paper P&L by strategy |
| `/pending` | Any pending approval requests |
| `/pause` | Suspend monitoring (sends WARN-level only, no ACTION triggers) |
| `/resume` | Re-enable monitoring |
| `/help` | Command list |

**Auth guard:** Every inbound handler checks `update.effective_chat.id == TELEGRAM_CHAT_ID`.
Messages from other chat IDs are silently dropped and logged at WARNING.

**Timeout handling:** A background asyncio task scans `pending_adjustments` every 5 minutes.
Rows where `expires_at < now` and `status == PENDING` are set to `EXPIRED` with
`approved_option = NULL`. The daemon treats EXPIRED as "do nothing" and continues monitoring.

**Non-fatal contract preserved:** `TelegramGateway` wraps all Telegram API calls in
`try/except`. Network failure → log WARNING, return False. The daemon never aborts due to
Telegram failure.

**Tests:** mock `python-telegram-bot`'s `Application` object. Test auth guard, button
routing, timeout scanning, non-fatal on API failure.

---

## Phase PT-2 — Rapid Council Integration

**Target:** July–August 2026
**Owner:** Cowork
**Blocked by:** PT-1

### Council Design

**Architecture:** Stage 1 fires 4 API calls in parallel (`asyncio.gather`). Chairman calls
immediately after. No Stage 2 peer review (too slow). Total budget: 30 seconds.

**`src/council/__init__.py`** — package stub.

**`src/council/rapid.py`** — `RapidCouncil`:

```python
async def consult(
    self,
    context: str,          # from strategy.describe_context()
    strategy_spec: str,    # full text of e.g. ic_nifty_v1.md
    breach: BreachEvent,
) -> CouncilOutput:
    """Run rapid council. Returns ranked adjustment options."""
```

`CouncilOutput` is a frozen Pydantic model: `options: list[AdjustmentOption]`, `chairman_rationale: str`,
`dissenting_notes: str | None`, `total_latency_ms: int`, `persona_responses: list[PersonaResponse]`.

`AdjustmentOption`: `rank: int`, `label: str`, `description: str`, `credit_impact: Decimal | None`,
`delta_impact: Decimal | None`, `supporting_personas: list[str]`, `dissenting_personas: list[str]`.

### Council Members — Model Assignments

| Persona | Model | Role | Why |
|---|---|---|---|
| **QuantAnalyst** | `claude-haiku-4-5` | Greeks math, EV, probability of each option | Haiku is fast and accurate on structured numeric reasoning. Greeks context is well-structured. |
| **SpecGuardian** | `claude-haiku-4-5` | Reads strategy spec doc verbatim, flags compliance violations | Mechanical check — does not need deep reasoning. Haiku speed matters here. |
| **RiskManager** | `claude-sonnet-4-6` | Tail scenarios, worst-case P&L, margin impact, liquidity at stressed bid/ask | Needs more nuance than Haiku; Opus is overkill for a time-bounded decision. |
| **OptionsStrategist** | `claude-sonnet-4-6` | Market structure, VIX regime, OI walls, whether this is a trending or noise move | Same reasoning — Sonnet quality at Sonnet speed. |
| **Chairman** | `claude-sonnet-4-6` | Synthesises all four responses into ranked options | Speed matters. Opus is authoritative for governance councils but too slow for real-time. |

**System prompt structure per persona:** Each persona receives a system prompt encoding its
"lens" (e.g. QuantAnalyst: "You evaluate adjustment options purely through the lens of
expected value and Greeks arithmetic. Do not discuss market narrative."). The user turn
contains the structured context from `strategy.describe_context()`.

**SpecGuardian note:** This persona receives the full text of the relevant strategy spec
(`ic_nifty_v1.md` for Iron Condor) as part of its context. Its output is: "complies / does
not comply" for each proposed option, with cited spec clause. This prevents council drift
where members suggest adjustments that the strategy spec explicitly forbids.

**Timeout safety:** `asyncio.wait_for(gather(...), timeout=25.0)`. If any persona times out,
its `PersonaResponse` is marked `timed_out=True` and the chairman proceeds with available
responses. A full timeout escalates to "do nothing" and sends a Telegram warning.

**Logging:** Every council run writes to `council_outputs` (one row per persona + one for
chairman). Token counts and latency recorded. This is the audit trail and the training corpus
for future council calibration.

**Tests:** Mock all 5 API calls. Test parallel execution, partial timeout handling, option
ranking, SpecGuardian veto path.

---

## Phase PT-3 — Cron Layer & Daemon Lifecycle

**Target:** August 2026
**Owner:** Cowork
**Blocked by:** PT-2

### Scripts

**`scripts/pre_market_brief.py`** (cron 09:00 weekdays): fetches current paper positions from
`PaperStore`, computes delta via `PortfolioDeltaTracker`, fetches spot from `BrokerClient`,
sends Telegram message: open positions, strikes vs spot, DTE, unrealized P&L, IVR from
latest VIX Parquet. Stateless — reads DB, sends Telegram, exits.

**`scripts/start_paper_monitor.py`** (cron 09:15 weekdays): checks `daemon_heartbeat` —
if heartbeat exists and is < 10 minutes old, daemon is already running (skip). Otherwise:
`subprocess.Popen(['python', '-m', 'scripts.paper_monitor_daemon'])`. Exits immediately.

**`scripts/paper_monitor_daemon.py`** (persistent): the main event loop. Runs
`StrategyMonitor.run()` (polls every 90s) and `TelegramGateway.start_polling()` as two
concurrent asyncio tasks. Writes heartbeat on each monitor tick. Handles `SIGTERM` cleanly:
marks pending adjustments as EXPIRED, writes final heartbeat, exits.

**`scripts/stop_paper_monitor.py`** (cron 15:30 weekdays): reads PID from `daemon_heartbeat`
(add a `pid` column in PT-0 migration), sends `SIGTERM`. Waits up to 30s for clean exit,
then `SIGKILL` if unresponsive.

**`scripts/eod_paper_summary.py`** (cron 15:35 weekdays): reads `paper_nav_snapshots` and
`paper_leg_snapshots` from today, computes daily P&L, adjustment count, Greeks snapshot.
Formats and sends to Telegram. Stateless — exits after send.

### Cron table (additions to existing crontab)

```cron
# Paper trading lifecycle
00 09 * * 1-5   cd /path/to/NiftyShield && python -m scripts.pre_market_brief
15 09 * * 1-5   cd /path/to/NiftyShield && python -m scripts.start_paper_monitor
30 15 * * 1-5   cd /path/to/NiftyShield && python -m scripts.stop_paper_monitor
35 15 * * 1-5   cd /path/to/NiftyShield && python -m scripts.eod_paper_summary
```

**Tests:** Daemon startup/shutdown integration test with `MockBrokerClient`. Heartbeat
write + stale detection. SIGTERM clean exit. Pre-market and EOD formatting unit tests.

---

## Phase PT-4 — Iron Condor v1 Strategy Implementation

**Target:** August–September 2026
**Owner:** Cowork (backbone) + Animesh (entry decisions during paper run)
**Blocked by:** PT-3, `docs/strategies/ic_nifty_v1.md` (must exist per council impl. path)

### Council ruling recap

Per `docs/council/2026-05-02_iron-condor-v1-core-design.md` (Chairman synthesis, §2):
IC v1 has **no adjustments**. All breach events route to the IC exit stack. The council
in paper trading mode will still run and log its analysis — but the `AdjustmentOptions`
are restricted to exit variants only (close full IC, close call spread only, close put
spread only). No rolls, no hedges added in v1.

This is enforced in `IronCondorV1.describe_context()` which appends:
`"STRATEGY CONSTRAINT: IC v1 permits exits only. Do not propose rolls or new legs."`.
`SpecGuardian` will flag any non-exit suggestion as non-compliant.

### What gets built

**`src/strategy/ic_nifty_v1.py`** — `IronCondorV1` implements `PaperStrategy`.

`IronCondorV1Config` (frozen Pydantic):

```python
short_put_delta: Decimal = Decimal("0.15")   # standalone default
short_call_delta: Decimal = Decimal("0.10")  # standalone default
wing_width_points: int = 500
profit_target_pct: Decimal = Decimal("0.50")
loss_stop_multiple: Decimal = Decimal("2.0")
delta_stop: Decimal = Decimal("0.35")
time_stop_dte: int = 14
csp_open_put_delta: Decimal = Decimal("0.09")   # when CSP concurrent
csp_open_call_delta: Decimal = Decimal("0.13")  # when CSP concurrent
```

`check_thresholds()` returns breach events for:
- **PROFIT_TARGET**: mark ≤ 50% of entry credit → severity ACTION
- **LOSS_STOP**: mark ≥ 2.0× entry credit → severity ACTION
- **DELTA_STOP**: either short leg |delta| ≥ 0.35 → severity ACTION
- **TIME_STOP**: DTE ≤ 14 → severity ACTION
- **DELTA_WARN**: either short leg |delta| ≥ 0.25 → severity WARN (Telegram alert, no council)
- **DTE_WARN**: DTE ≤ 21 → severity INFO (logged only)

`apply_adjustment()` for IC v1 only handles `adjustment_type == "CLOSE_FULL"` or `"CLOSE_CALL_SPREAD"`
or `"CLOSE_PUT_SPREAD"`. Any other type raises `ValueError("IC v1: only exits permitted")`.

**Entry helper integration:** `find_strike_by_delta.py` already exists and outputs
`record_paper_trade.py` commands. A new `scripts/paper_ic_entry.py` wraps the 4-leg IC
entry: calls `find_strike_by_delta` for each leg, validates portfolio delta gate via
`PortfolioDeltaTracker`, checks minimum credit, liquidity gate, then generates the 4
`record_paper_trade.py` commands for Animesh to review and run.

**Strategy name:** `paper_ic_nifty_v1` (enforced by `paper_` prefix rule).

**Tests:** All 5 breach types. `apply_adjustment` rejects non-exit types. Entry validation
(delta gate, credit gate, liquidity gate). Integration with `MockBrokerClient`.

---

## Phase PT-5 — Backtesting Mode

**Target:** Phase 1 (after Phase 0.8 gate, Aug–Dec 2026)
**Owner:** Cowork
**Blocked by:** PT-4 + Phase 1.3 (NSE Bhavcopy + TrueData pipeline operational)

The key design payoff: same `StrategyMonitor` + `IronCondorV1` code runs over historical
data with swapped providers.

### What gets built

**`src/backtest/historical_replayer.py`** — `HistoricalReplayer` implements `MarketDataProvider`.
Reads option chain Parquet files (from bhavcopy/TrueData pipeline), reconstructs Greeks via
Black '76 (`src/backtest/greeks.py`), yields `OptionChain` objects in chronological order.
Configurable replay speed (useful for debugging). Respects market calendar via
`src/market_calendar/`.

**`src/backtest/auto_approver.py`** — `AutoApprover` implements `ApprovalGateway`. Two modes:
`COUNCIL_TOP_PICK` (auto-accepts option ranked #1 by chairman — optimistic scenario) and
`RULE_BASED` (pre-specified policy: e.g. "always close full IC on any ACTION breach").
`RULE_BASED` mode is the default for walk-forward validation — it makes backtest results
policy-reproducible without council calls.

**`src/backtest/fill_simulator.py`** — `BacktestFillSim` implements fill simulation using
the slippage model from `DECISIONS.md §Slippage`: VIX-regime-aware absolute INR slippage +
OI liquidity multiplier. Generates optimistic / base / conservative P&L scenarios (slippage
multiplier ×1.0 / ×1.0 / ×1.5). Slippage definition already decided and documented.

**Backtest entry point:** `scripts/run_ic_backtest.py`. Args: `--start`, `--end`, `--mode`
(COUNCIL_TOP_PICK | RULE_BASED), `--policy` (for RULE_BASED), `--slippage` (optimistic |
base | conservative). Runs `StrategyMonitor` in replay mode, collects `BacktestResult` per
cycle, writes to a separate `backtest.sqlite` (not `portfolio.sqlite`).

**Tests:** Replayer reading fixture Parquet file. `AutoApprover` both modes. `BacktestFillSim`
slippage model boundary cases. Full mini-backtest over 3 synthetic cycles.

---

## Infrastructure Gaps — Existing Code Needs Enhancement

Before PT-0 ships, audit these gaps:

| Gap | Current State | Required Change | Priority |
|---|---|---|---|
| `src/strategy/` | Empty directory | Create from PT-0 | PT-0 blocker |
| `src/council/` | Does not exist | Create from PT-2 | PT-2 blocker |
| `src/notifications/` | Outbound only | Add `TelegramGateway` as separate class (do not modify `TelegramNotifier`) | PT-1 |
| `src/paper/store.py` | No `pending_adjustments`, `council_outputs`, `daemon_heartbeat` tables | Add migrations in PT-0 | PT-0 |
| `src/paper/` | No `PaperExecutor` | Add in PT-0 | PT-0 |
| `src/client/protocol.py` | `MarketDataProvider` sub-protocol exists | Already correct — no change | — |
| `src/risk/` | Task 2 (PortfolioDeltaTracker) pending | Must ship before PT-0 starts | Prerequisite |
| `scripts/` | No daemon lifecycle scripts | Add in PT-3 | PT-3 |
| `requirements.txt` | No `python-telegram-bot` | Add in PT-1 | PT-1 |
| `tests/unit/strategy/` | Does not exist | Create with `__init__.py` in PT-0 | PT-0 |
| `tests/unit/council/` | Does not exist | Create with `__init__.py` in PT-2 | PT-2 |

**Invariants that apply to all new code in this plan:**

- `paper_` prefix on all strategy names — enforced by Pydantic validator on `PaperTrade`.
- `Decimal` everywhere for money. Never float in the P&L path.
- All timestamps UTC in DB; IST only at display layer.
- New packages must have `__init__.py` (re-index codebase-memory-mcp after each new package).
- `BrokerClient` injected via constructor; never imported directly outside `factory.py`.
- All Telegram interactions non-fatal: catch all exceptions, log WARNING, continue.
- No `SELECT *` queries — aggregate at SQL layer.

---

## Council Member Recommendation & Open Question

### Recommended Rapid Council (this plan)

| Persona | Model | Cost/call | Speed |
|---|---|---|---|
| QuantAnalyst | `claude-haiku-4-5` | Lowest | ~3s |
| SpecGuardian | `claude-haiku-4-5` | Lowest | ~3s |
| RiskManager | `claude-sonnet-4-6` | Medium | ~8s |
| OptionsStrategist | `claude-sonnet-4-6` | Medium | ~8s |
| Chairman (synthesis) | `claude-sonnet-4-6` | Medium | ~10s |

All four Stage 1 calls run in parallel. Total wall-clock: ~13s (chairman waits for slowest
Stage 1 response). Well within the 30-second budget.

The SpecGuardian is the addition that didn't exist in earlier architecture discussions.
It prevents "adjustment creep" — the tendency for council members to suggest creative
solutions that violate the documented strategy rules. Having a model that reads the spec
verbatim and flags compliance creates an audit-friendly paper trail.

### Open Question for Animesh

**Should we add a 5th Stage 1 persona: `MarketSentimentAnalyst`?**

This persona would use web search to check for:
- SEBI circulars, RBI announcements, or budget dates in the next 5 trading days
- Any NSE technical advisories (margin changes, lot size changes)
- FII/DII provisional data from NSE (published intraday)

**Arguments for:** Brings macro context that the other personas lack. An adjustment decision
looks different if RBI MPC is tomorrow vs. a quiet week.

**Arguments against:**
- Adds ~10–15 seconds via web fetch (possible timeout risk during market hours)
- Web search can fail silently, leaving the council without this persona's input
- The event filter (R4 in CSP/IC spec) already screens for known events at entry time. By
  the time the monitor fires, you're already inside a trade — macro context is advisory, not
  actionable.
- The existing `OptionsStrategist` persona already has market context in its system prompt
  (VIX level, IVR, DTE, spot vs strikes). Most of what `MarketSentimentAnalyst` would add
  is already implicitly in the Greeks and VIX context.

**Recommendation: Skip for PT-2, add only if OptionsStrategist recommendations consistently
feel under-informed during paper trading review.** The SpecGuardian is higher value per
token.

---

## Phase Dependency Map

```
[BACKTEST_PLAN Task 2: PortfolioDeltaTracker]
        ↓
   [PT-0: Protocol + Core Infra]
        ↓
   [PT-1: Bidirectional Telegram]
        ↓
   [PT-2: Rapid Council]
        ↓
   [PT-3: Cron Layer + Daemon]
        ↓
   [PT-4: IronCondorV1 Strategy]
        ↓
[Phase 0.8 gate passes]
        ↓
   [PT-5: Backtesting Mode]
```

---

## Completion Log

*Append-only. One row per completed phase.*

| Date | Phase | Commit SHA | Notes |
|---|---|---|---|
| — | — | — | — |

---

## Open Questions for Future Sessions

- **PT-1:** Should the Telegram approval window be 30 minutes (default) or DTE-aware (shorter
  when DTE ≤ 5)?
- **PT-3:** Should the daemon run as a `systemd` service instead of cron-launched subprocess?
  More robust restart guarantees but requires system-level setup.
- **PT-4:** Confirm NSE lot size before hardcoding IC lot size. Current constants file has
  `LOT_SIZE = 65` (`src/paper/constants.py`) but DEBT-4 flags a `DEFAULT_LOT_SIZE = 75`
  inconsistency in `find_strike_by_delta.py`. Resolve before IC entry scripts are built.
- **MarketSentimentAnalyst:** Add as 5th council persona or not? (see above)

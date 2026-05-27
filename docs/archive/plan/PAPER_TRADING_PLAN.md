# NiftyShield — Paper Trading Backbone Plan

> **Status:** Design document. Implementation not started.
> **Load this file when:** planning or implementing `src/strategy/`, `src/council/`,
> the monitor daemon, or any pluggable strategy.
> **Related:** `CONTEXT.md` · `DECISIONS.md` · `BACKTEST_PLAN.md`
> · `docs/plan/signals/` (signals_stories.md + signals_tasks.md + signals_schema.md)
> · `docs/council/2026-05-02_iron-condor-v1-core-design.md`

---

## Core Idea

One backbone. Any number of pluggable strategies.

The backbone runs a cron-driven daemon that calls every registered strategy on every tick.
Each strategy decides independently whether it has something to act on — an entry signal,
a threshold breach, an exit trigger. If it does, the council is consulted and the result
goes to Telegram for approval. If it doesn't, the tick is silent.

A strategy that fires every day (Signal Pipeline) and a strategy that fires once in three
weeks (Iron Condor) both live on the same backbone without any special-casing.

---

## What Already Exists

Before building anything, this is the infrastructure already in place that the backbone
builds on. Do not reimplement these.

| What | Where | Role in backbone |
|---|---|---|
| `PaperStore` | `src/paper/store.py` | Persistence for all paper trades, snapshots, leg snapshots |
| `PaperTracker` | `src/paper/tracker.py` | Mark-to-market computation |
| `PaperTrade` / `PaperPosition` | `src/paper/models.py` | Position state models |
| `TelegramNotifier` | `src/notifications/notifier.py` | Outbound alerts — backbone extends this, does not replace it |
| `BrokerClient` / `MarketDataProvider` | `src/client/protocol.py` | Live market data — `StrategyMonitor` consumes this sub-protocol |
| `OptionChain` / `OptionChainStrike` | `src/models/options.py` | Chain model passed to every strategy on each tick |
| `PortfolioDeltaTracker` | `src/risk/` (Task 2) | Entry gate — strategies call this before opening a position |
| `compute_ivr` | `src/backtest/ivr.py` | IVR at entry — used by both IC and Signal Pipeline |
| `get_expiry_candidates` | `src/instruments/lookup.py` | Expiry selection for IC entry |
| `is_trading_day` | `src/market_calendar/holidays.py` | Daemon skips non-trading days |
| `src/db.py` | `src/db.py` | Shared SQLite connection — all new tables go through this |

---

## Architecture

```
CRON (stateless scripts, exit after run)
├── 09:00  pre_market_brief.py     — positions + Greeks + IVR snapshot → Telegram
├── 09:15  start_monitor.py        — launches daemon if not running
├── 15:30  stop_monitor.py         — SIGTERM daemon
└── 15:35  eod_summary.py          — daily P&L + council activity → Telegram

DAEMON (persistent, 09:15–15:30)
└── monitor_daemon.py
    │
    ├── StrategyMonitor             ← polls every 90s; calls check_signals() on all strategies
    │   │
    │   └── [registered strategies]
    │       ├── IronCondorV1        ← pluggable strategy (PT-S1)
    │       └── SignalPipeline      ← pluggable strategy (PT-S2)
    │
    ├── RapidCouncil                ← fires only when a strategy returns an ACTION event
    │   ├── QuantAnalyst   (DeepSeek R1)
    │   ├── SpecGuardian   (Haiku)
    │   ├── RiskManager    (o3-mini)
    │   ├── OptionsStrategist (Grok-4-fast)
    │   └── Chairman       (Sonnet)  ← parallel Stage 1 → immediate synthesis
    │
    ├── TelegramGateway             ← extends TelegramNotifier; adds inbound polling
    │   └── inline keyboard approval → callback routes to PaperExecutor
    │
    └── PaperExecutor               ← wraps PaperStore; applies approved actions
        └── PaperFillSimulator      ← mid ± slippage; records to paper_trades

PERSISTENCE  (portfolio.sqlite via src/db.py)
├── [existing]  paper_trades, paper_nav_snapshots, paper_leg_snapshots, paper_alerts
└── [new]       pending_approvals, council_outputs, daemon_heartbeat
```

---

## Phase PT-0 — Common Infrastructure

**Target:** June–July 2026
**Prerequisite:** Task 2 (PortfolioDeltaTracker) shipped
**Owner:** Cowork
**Blocks:** all strategy phases

Everything in this phase is strategy-agnostic. No IC-specific or signal-specific logic here.

---

### PT-0a — PaperStrategy Protocol

**`src/strategy/__init__.py`** — package stub.

**`src/strategy/protocol.py`** — `PaperStrategy` protocol. This is the only contract a
strategy must satisfy to plug into the backbone.

```python
class PaperStrategy(Protocol):
    strategy_name: str   # must start with "paper_"

    async def check_signals(
        self,
        market: OptionChain,
        positions: list[PaperPosition],
    ) -> list[SignalEvent]:
        """
        Called on every monitor tick for every registered strategy.
        Return [] if nothing to act on — the tick is silent.
        Return one or more SignalEvents to trigger council consultation.
        """

    def describe_context(
        self,
        event: SignalEvent,
        market: OptionChain,
        positions: list[PaperPosition],
    ) -> str:
        """Structured context string for the council prompt."""

    async def apply_action(
        self,
        positions: list[PaperPosition],
        action: ApprovedAction,
    ) -> list[PaperPosition]:
        """Apply an approved action. Returns updated position list."""
```

`SignalEvent`: `event_type: str`, `severity: Literal["INFO","WARN","ACTION"]`,
`description: str`, `payload: dict[str, Any]`.

Only `severity == "ACTION"` triggers council + Telegram approval.
`WARN` sends a plain Telegram message (no approval needed).
`INFO` is logged silently.

`ApprovedAction`: `action_type: str`, `legs_to_close: list[str]`,
`legs_to_open: list[LegSpec]`, `rationale: str`, `council_rank: int`.

---

### PT-0b — StrategyMonitor

**`src/strategy/monitor.py`** — `StrategyMonitor`.

- Holds a registry of `PaperStrategy` instances.
- Polls every 90 seconds during market hours.
- On each tick: fetches live `OptionChain` once (shared across all strategies), calls
  `check_signals()` on each registered strategy.
- Routes `ACTION` events to `RapidCouncil` → `TelegramGateway`.
- Writes heartbeat to `daemon_heartbeat` on every tick.
- Does not know about IC or Signal Pipeline specifically.

---

### PT-0c — PaperExecutor

**`src/strategy/executor.py`** — `PaperExecutor`.

Thin layer over `PaperStore`. Given an `ApprovedAction`:
1. Computes synthetic fills via `PaperFillSimulator` (mid ± slippage).
2. Calls `PaperStore.record_trade()` for each leg change.
3. Writes a row to `council_outputs` for audit.
4. Returns the updated `list[PaperPosition]`.

`PaperFillSimulator`: uses the VIX-regime slippage model from `DECISIONS.md §Slippage`
(already specified: ₹1.0–₹4.0 base + OI multiplier). Port the model, do not reinvent it.

---

### PT-0d — RapidCouncil

**`src/council/__init__.py`** — package stub.

**`src/council/rapid.py`** — `RapidCouncil`.

Fires only when `StrategyMonitor` routes an `ACTION` event to it. Four Stage 1 calls in
parallel (`asyncio.gather`), chairman call immediately after. Total budget: 30 seconds.

**Council composition (heterogeneous multi-vendor — avoids correlated blind spots):**

| Persona | Model | Provider | Rationale |
|---|---|---|---|
| QuantAnalyst | `deepseek/deepseek-r1-0528` | OpenRouter | Reasoning model; strong math, EV, Greeks probability — proven in governance council |
| SpecGuardian | `claude-haiku-4-5` | Anthropic direct | Fastest at mechanical rule-following; spec compliance is a retrieval+check task, not reasoning |
| RiskManager | `openai/o3-mini` | OpenRouter | Chain-of-thought adversarial reasoning; built specifically for "what breaks this plan" |
| OptionsStrategist | `x-ai/grok-4-fast` | **xAI direct** | Live search for real-time FII flow, OI changes, breaking news — unique capability not available via OpenRouter |
| Chairman | `claude-sonnet-4-6` | Anthropic direct | Synthesis; consistent with existing council infrastructure within 30s wall-clock budget |

> **⚠ Grok-4-fast must be called via xAI direct API (`https://api.x.ai/v1`), not OpenRouter.**
> OpenRouter routes Grok without search grounding enabled. Live search is the entire reason
> Grok is in this seat — without it, substitute `openai/gpt-4o` via OpenRouter instead.

**SpecGuardian** receives the full strategy spec doc as context (e.g. `ic_nifty_v1.md`
for the IC strategy). It outputs "complies / does not comply" for each proposed action
with cited clause. This prevents council members from suggesting actions the strategy
spec forbids.

`CouncilOutput`: `actions: list[ApprovedAction]`, `chairman_rationale: str`,
`dissenting_notes: str | None`, `latency_ms: int`.

Timeout: Stage 1 parallel calls `asyncio.wait_for(..., timeout=25.0)` → expected ~10s.
Chairman call `asyncio.wait_for(..., timeout=15.0)` → expected ~10s.
Total wall-clock budget: **~20s typical, 40s hard cap**.
Partial Stage 1 timeout → chairman proceeds with available responses.
Full timeout → escalates to `WARN` Telegram, no action taken.

---

### PT-0e — Bidirectional Telegram Gateway

**`src/notifications/telegram_gateway.py`** — `TelegramGateway`.

Extends (does not replace) the existing `TelegramNotifier`. Added capabilities:

- `send_approval_request(council_output, event) → int`: sends inline keyboard message
  with council-ranked actions. Returns `message_id`.
- `start_polling(callback) → None`: async polling loop for `CallbackQuery` (button presses)
  and command handlers (`/status`, `/pnl`, `/pending`, `/pause`, `/resume`).

Non-fatal contract preserved: all Telegram API calls wrapped in `try/except`, return
`False` on failure, never raise.

Auth guard: every inbound handler checks `chat_id == TELEGRAM_CHAT_ID`. Other senders
are silently dropped and logged at WARNING.

Timeout scanning: background asyncio task checks `pending_approvals` every 5 minutes.
Expired rows (status PENDING, `expires_at < now`) set to EXPIRED → treated as no action.

---

### PT-0f — New SQLite Tables

Three new tables, migrations added to `PaperStore.__init__`:

```sql
CREATE TABLE IF NOT EXISTS pending_approvals (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy_name   TEXT NOT NULL,
    event_type      TEXT NOT NULL,
    council_output  TEXT NOT NULL,      -- JSON blob
    status          TEXT NOT NULL,      -- PENDING|APPROVED|REJECTED|EXPIRED
    approved_rank   INTEGER,
    expires_at      TEXT NOT NULL,      -- ISO UTC
    telegram_msg_id INTEGER,
    created_at      TEXT NOT NULL,
    resolved_at     TEXT
);

CREATE TABLE IF NOT EXISTS council_outputs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    approval_id     INTEGER NOT NULL REFERENCES pending_approvals(id),
    persona         TEXT NOT NULL,
    model           TEXT NOT NULL,
    prompt_tokens   INTEGER,
    output_tokens   INTEGER,
    latency_ms      INTEGER,
    response        TEXT NOT NULL,
    created_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS daemon_heartbeat (
    id              INTEGER PRIMARY KEY CHECK (id = 1),
    pid             INTEGER NOT NULL,
    last_beat       TEXT NOT NULL,      -- ISO UTC
    strategies      TEXT NOT NULL,      -- JSON array of registered strategy names
    last_event      TEXT
);
```

---

### PT-0g — Daemon + Cron Scripts

**`scripts/monitor_daemon.py`** — persistent process. Two concurrent asyncio tasks:
`StrategyMonitor.run()` and `TelegramGateway.start_polling()`. Writes heartbeat every
tick. Handles `SIGTERM` cleanly: expires pending approvals, writes final heartbeat, exits.

**`scripts/start_monitor.py`** — checks heartbeat staleness; if stale or absent, launches
daemon via `subprocess.Popen`. Exits immediately.

**`scripts/stop_monitor.py`** — reads PID from `daemon_heartbeat`; `SIGTERM`; waits 30s;
`SIGKILL` if unresponsive.

**`scripts/pre_market_brief.py`** — stateless; open positions + Greeks + IVR → Telegram.

**`scripts/eod_summary.py`** — stateless; today's P&L + council activity count → Telegram.

**Cron additions:**
```cron
00 09 * * 1-5  python -m scripts.pre_market_brief
15 09 * * 1-5  python -m scripts.start_monitor
30 15 * * 1-5  python -m scripts.stop_monitor
35 15 * * 1-5  python -m scripts.eod_summary
```

**Dependency to add:** `python-telegram-bot>=21.0` in `requirements.txt`.

---

### PT-0 Tests

`tests/unit/strategy/` and `tests/unit/council/` (both need `__init__.py`):

- Protocol conformance: a `MockStrategy` satisfies `PaperStrategy`.
- `StrategyMonitor`: INFO/WARN/ACTION routing; heartbeat write; empty strategy list.
- `PaperExecutor`: fill simulation; `PaperStore.record_trade` called correctly.
- `RapidCouncil`: parallel execution (mocked API); partial timeout; SpecGuardian veto;
  full timeout escalation.
- `TelegramGateway`: auth guard; button routing; timeout scanning; non-fatal on failure.
- Table migrations: all three tables created idempotently.

---

## Phase PT-S0 — CSP v1 (Pluggable Strategy)

**Target:** After PT-0 ships (validates backbone with a live strategy before IC)
**Blocked by:** PT-0
**Owner:** Cowork
**Note:** CSP is already running via `record_paper_trade.py` + `daily_snapshot.py`.
This phase migrates it onto the backbone — it does not change the strategy spec.
Existing `paper_trades` rows are unaffected.

**`src/strategy/csp_nifty_v1.py`** — `CSPNiftyV1` implements `PaperStrategy`.

`check_signals()` returns `SignalEvent` for:

| Event | Severity | Trigger |
|---|---|---|
| `PROFIT_TARGET` | ACTION | mark ≤ 50% of entry credit |
| `LOSS_STOP` | ACTION | mark ≥ 2.0× entry credit |
| `DELTA_STOP` | ACTION | short put \|delta\| ≥ 0.35 |
| `TIME_STOP` | ACTION | DTE ≤ 21 |
| `ROLL_DUE_DTE` | WARN | DTE ≤ 5 |
| `ROLL_DUE_DECAY` | WARN | current premium ≤ 25% of entry premium (≥75% captured) |
| `DELTA_WARN` | WARN | short put \|delta\| ≥ 0.25 |

`WARN` events replace the `paper_alerts` table logic currently specced in `TODOS.md`
(CLI-12 area). Once this phase ships, the `paper_alerts` cron alert logic is retired in
favour of the unified `WARN` path through `TelegramGateway`.

Entry remains manual: `record_paper_trade.py` as today. The daemon picks up the new
position on its next tick automatically.

The existing cron entry for `paper_snapshot.py` is retired; EOD mark-to-market is
handled by `eod_summary.py` via `PaperTracker` (already used there).

**Strategy name:** `paper_csp_nifty_v1`

---

## Phase PT-S1 — Iron Condor v1 (Pluggable Strategy)

**Target:** August 2026
**Blocked by:** PT-0 + `docs/strategies/ic_nifty_v1.md` (must exist first)
**Owner:** Cowork (backbone wiring) + Animesh (entry execution)

**Council ruling:** `docs/council/2026-05-02_iron-condor-v1-core-design.md` — no
adjustments in v1. All `ACTION` events route to exit options only. `SpecGuardian`
receives `ic_nifty_v1.md` and flags any non-exit proposal as non-compliant.

**`src/strategy/ic_nifty_v1.py`** — `IronCondorV1` implements `PaperStrategy`.

`check_signals()` returns `SignalEvent` for:

| Event | Severity | Trigger |
|---|---|---|
| `PROFIT_TARGET` | ACTION | mark ≤ 50% of entry credit |
| `LOSS_STOP` | ACTION | mark ≥ 2.0× entry credit |
| `DELTA_STOP` | ACTION | either short leg \|delta\| ≥ 0.35 |
| `TIME_STOP` | ACTION | DTE ≤ 14 |
| `DELTA_WARN` | WARN | either short leg \|delta\| ≥ 0.25 |
| `DTE_WARN` | INFO | DTE ≤ 21 |

No open position → `check_signals()` returns `[]`. Entry is manual via
`scripts/paper_ic_entry.py` (validates delta gate, credit gate, liquidity gate).

`apply_action()` accepts only `CLOSE_FULL`, `CLOSE_CALL_SPREAD`, `CLOSE_PUT_SPREAD`.
Any other `action_type` raises `ValueError` — the spec forbids it.

**Strategy name:** `paper_ic_nifty_v1`

---

## Phase PT-S2 — Signal Pipeline (Pluggable Strategy)

**Target:** August–September 2026
**Blocked by:** PT-0 + OpenRouter API key
**Owner:** Cowork
**Stories + tasks:** `docs/plan/signals/signals_stories.md` · `docs/plan/signals/signals_tasks.md`

**`src/signals/`** — full module per spec §8. `SignalPipeline` implements `PaperStrategy`.

`check_signals()` fires **every day** regardless of open position state:
1. Fetches `MarketSnapshot` (option chain, VIX, FII, GIFT Nifty).
2. Calls all three providers in parallel: Grok, GPT-4o, Gemini (same `asyncio.gather`
   pattern as `RapidCouncil` — 30s timeout).
3. Aggregates votes via `SignalAggregator` (majority + confidence gate).
4. Consensus ≥ 2/3 with confidence ≥ 3 → `ACTION` event with direction + strike.
5. Split or low confidence → `INFO` event (logged only, no Telegram).

At 15:00 IST, if a signal position is open → `ACTION` event for `CLOSE_POSITION`
(fixed exit). Auto-approved — no council call needed.

`apply_action()` handles `ENTER_CALL`, `ENTER_PUT`, `NO_TRADE`, `CLOSE_POSITION`.

**Note on council interaction:** The Signal Pipeline's three providers (Grok/GPT-4o/Gemini)
form their own internal consensus inside `check_signals()`. The `RapidCouncil` (Claude
personas) is called after, to frame the approved action for the Telegram approval message.
This keeps the approval UX identical across all strategies.

**Strategy name:** `paper_signal_v1`

---

## Phase PT-S3 — 3-Track Comparison (Pluggable Strategy)

**Target:** After PT-S0
**Blocked by:** PT-0
**Owner:** Cowork
**Note:** 3-track already runs via `paper_3track_snapshot.py` (EOD cron) and
`paper_3track_overlay_roll.py` (manual roll). This phase migrates roll alerts onto
the backbone. Greek-based adjustment decisions are not needed here — these are long
positions with mechanical roll timing.

**`src/strategy/nifty_track_comparison_v1.py`** — `NiftyTrackComparisonV1` implements
`PaperStrategy`. Covers all three tracks (Spot/Futures/Proxy) and their overlays
(collar, CSP overlay, CC) as a single registered strategy.

`check_signals()` returns `SignalEvent` for:

| Event | Severity | Trigger |
|---|---|---|
| `ROLL_DUE_DTE` | WARN | any open leg DTE ≤ 5 |
| `ROLL_DUE_DECAY` | WARN | any short overlay premium ≤ 25% of entry (≥75% captured) |
| `OVERLAY_EXPIRED` | WARN | overlay expiry passed with no roll recorded |

No `ACTION` events — 3-track rolls are mechanical, no council consultation needed.
`apply_action()` is a no-op (rolls are executed manually via the existing
`paper_3track_overlay_roll.py` script; the backbone only delivers the reminder).

The existing `paper_3track_snapshot.py` EOD cron is **retained** — it writes
`paper_leg_snapshots` which the backbone's `eod_summary.py` reads. The two coexist
during the migration period; `paper_3track_snapshot.py` is retired only after
`eod_summary.py` covers all three tracks cleanly.

**Strategy name:** `paper_nifty_3track_v1` (single registration covers all tracks)

---

## Phase PT-B — Backtesting Mode (Infrastructure Swap)

**Target:** Phase 1 (after Phase 0.8 gate)
**Blocked by:** PT-S1 + Phase 1.3 (Bhavcopy + TrueData pipeline)

Same strategies, swapped providers — no strategy code changes.

| Live | Backtest |
|---|---|
| `UpstoxLiveClient` (MarketDataProvider) | `HistoricalReplayer` |
| `TelegramGateway` | `AutoApprover` |
| `PaperFillSimulator` | `BacktestFillSim` (VIX-regime slippage model) |

**`src/backtest/historical_replayer.py`** — reads Parquet, reconstructs Greeks via
Black '76 (`src/backtest/greeks.py`), yields `OptionChain` chronologically.

**`src/backtest/auto_approver.py`** — two modes: `COUNCIL_TOP_PICK` (accepts rank-1,
optimistic) and `RULE_BASED` (pre-specified policy, reproducible walk-forward).

**`src/backtest/fill_simulator.py`** — VIX-regime slippage from `DECISIONS.md`.
Generates optimistic / base / conservative scenarios.

---

## Infrastructure Gap Summary

| Gap | State | Phase |
|---|---|---|
| `src/strategy/` | Empty directory | PT-0 |
| `src/council/` | Does not exist | PT-0 |
| `src/notifications/telegram_gateway.py` | Does not exist | PT-0 |
| `pending_approvals`, `council_outputs`, `daemon_heartbeat` tables | Do not exist | PT-0 |
| `PaperExecutor` | Does not exist | PT-0 |
| Daemon + cron scripts | Do not exist | PT-0 |
| `python-telegram-bot>=21.0` | Not in requirements.txt | PT-0 |
| `tests/unit/strategy/`, `tests/unit/council/` | Do not exist | PT-0 |
| `src/strategy/csp_nifty_v1.py` | Does not exist | PT-S0 |
| `src/strategy/ic_nifty_v1.py` | Does not exist | PT-S1 |
| `docs/strategies/ic_nifty_v1.md` | Does not exist (council specified, not written) | PT-S1 prereq |
| `src/signals/` | Spec exists, no code | PT-S2 |
| `src/strategy/nifty_track_comparison_v1.py` | Does not exist | PT-S3 |
| `src/backtest/historical_replayer.py` | Does not exist | PT-B |
| `src/backtest/auto_approver.py` | Does not exist | PT-B |
| `src/backtest/fill_simulator.py` | Does not exist | PT-B |

**Invariants that apply to all new code:**
- `paper_` prefix on all `strategy_name` values — enforced by `PaperTrade` Pydantic validator.
- `Decimal` for all monetary fields; TEXT in SQLite; `Decimal(str(row["col"]))` at read.
- Timestamps UTC in DB; IST at display layer only.
- `BrokerClient` injected via constructor; never imported outside `factory.py`.
- `__init__.py` in every new package; re-index codebase-memory-mcp after adding packages.
- All Telegram calls non-fatal: catch all exceptions, log WARNING, never raise.

---

## Open Question — 5th Council Persona

**Should we add `MarketSentimentAnalyst` (web search, real-time news)?**

Adds ~10–15s and a web-fetch dependency during market hours. Current recommendation: skip.
The Signal Pipeline's Grok and Gemini providers already cover real-time sentiment and global
macro — that context flows into `describe_context()` and is available to the Claude council
without a 5th persona. Revisit after PT-S2 paper trading review if `OptionsStrategist`
recommendations feel under-informed.

---

## Phase Dependency Map

```
[Task 2: PortfolioDeltaTracker]
              ↓
    [PT-0: Common Infrastructure]
              ↓
    [PT-S0: CSP v1]          ← validates backbone with live strategy
       ↓        ↓        ↓        ↓
[PT-S1: IC] [PT-S2: Signal] [PT-S3: 3-Track] [future strategies...]
       ↓
[Phase 0.8 gate]
       ↓
  [PT-B: Backtesting]
```

---

## Completion Log

| Date | Phase | Commit SHA | Notes |
|---|---|---|---|
| — | — | — | — |

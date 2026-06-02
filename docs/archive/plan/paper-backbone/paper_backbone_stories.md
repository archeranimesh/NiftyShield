# paper-backbone — Story Specs

> One task per session. Find the first unchecked item in `paper_backbone_tasks.md`. That is your only task.
> Full implementation rules in `CLAUDE.md` and `REVIEW.md`.
> After each task: tick `paper_backbone_tasks.md`, append `| SHA: <sha>`, add one line to `TODOS.md`.

---

## PB1.1 — `src/strategy/protocol.py`: PaperStrategy protocol + models + tests

**Files to change:**
- `src/strategy/__init__.py` — new package, single comment line only
- `src/strategy/protocol.py` — `PaperStrategy` protocol + `SignalEvent` + `ApprovedAction` + `LegSpec` models
- `tests/unit/strategy/__init__.py` — new test package, single comment line only
- `tests/unit/strategy/test_strategy_protocol.py` — model + protocol conformance tests

**Before any code:**
- `search_graph("PaperStrategy")` — confirm does NOT yet exist (zero results expected)
- `search_graph("PaperTrade")` — confirm frozen Pydantic pattern used in this codebase
- `search_graph("PortfolioDeltaTracker")` — confirm Task 2 prerequisite is committed
- `search_graph("OptionChain")` — confirm import path for the `market` argument type

**Package structure — create all stubs now:**

```
src/strategy/
├── __init__.py           (this task)
├── protocol.py           (this task)
├── monitor.py            (PB1.2)
├── executor.py           (PB1.3)
├── csp_nifty_v1.py       (PB2.1)
├── ic_nifty_v1.py        (PB3.1)
└── nifty_track_comparison_v1.py  (PB4.1)
```

Create all `__init__.py` stubs (single comment line) in `src/strategy/` and
`tests/unit/strategy/` now to avoid missing-package failures in later tasks.

**What to implement (`src/strategy/protocol.py`):**

```python
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Literal, Protocol, runtime_checkable

from src.models.options import OptionChain
from src.paper.models import PaperPosition


@dataclass(frozen=True)
class LegSpec:
    """Describes one leg to open as part of an ApprovedAction."""
    instrument_key: str
    action: Literal["BUY", "SELL"]
    quantity: int
    leg_role: str          # e.g. "short_put", "long_put_hedge"
    notes: str = ""


@dataclass(frozen=True)
class SignalEvent:
    """Emitted by a strategy when it detects something worth acting on."""
    event_type: str
    severity: Literal["INFO", "WARN", "ACTION"]
    description: str
    payload: dict[str, Any]


@dataclass(frozen=True)
class ApprovedAction:
    """An action approved by the council and optionally by the user via Telegram."""
    action_type: str
    legs_to_close: list[str]    # leg_role values of positions to close
    legs_to_open: list[LegSpec]
    rationale: str
    council_rank: int           # 1 = top pick


@runtime_checkable
class PaperStrategy(Protocol):
    """
    Contract every pluggable strategy must satisfy.

    The StrategyMonitor calls check_signals() on every tick for every registered strategy.
    Only ACTION severity events trigger council consultation + Telegram approval.
    WARN events send a plain Telegram message with no approval flow.
    INFO events are logged silently.
    """

    strategy_name: str   # must start with "paper_"

    async def check_signals(
        self,
        market: OptionChain,
        positions: list[PaperPosition],
    ) -> list[SignalEvent]:
        """Return [] if nothing to act on. Return events to trigger council or alerts."""
        ...

    def describe_context(
        self,
        event: SignalEvent,
        market: OptionChain,
        positions: list[PaperPosition],
    ) -> str:
        """Structured context string for the council prompt. Plain text, no HTML."""
        ...

    async def apply_action(
        self,
        positions: list[PaperPosition],
        action: ApprovedAction,
    ) -> list[PaperPosition]:
        """Apply an approved action. Returns updated position list."""
        ...
```

All three methods are `async` even if the concrete implementation is synchronous —
`check_signals` and `apply_action` are `async` because live implementations will call
`UpstoxLiveClient`; `describe_context` is sync (pure string building).

**Tests (`tests/unit/strategy/test_strategy_protocol.py`):**

Write a `MockStrategy` class that satisfies `PaperStrategy` with no-op implementations.

- `isinstance(MockStrategy(), PaperStrategy)` → `True` (runtime_checkable).
- `SignalEvent` with `severity="INFO"` → frozen dataclass, no error.
- `SignalEvent` with `severity="ACTION"` → `payload` accepts arbitrary dict.
- `ApprovedAction` with empty `legs_to_close` and empty `legs_to_open` → valid.
- `LegSpec` with `action="BUY"` → `quantity` and `leg_role` stored correctly.
- A class missing `check_signals` → `isinstance(..., PaperStrategy)` → `False`.

**Commit:** `feat(strategy): add PaperStrategy protocol + SignalEvent + ApprovedAction + LegSpec models`

---

## PB1.2 — `src/strategy/monitor.py`: StrategyMonitor + tests

**Files to change:**
- `src/strategy/monitor.py` — `StrategyMonitor` class
- `tests/unit/strategy/test_strategy_monitor.py` — new test file

**Before any code:**
- `get_code_snippet("PaperStrategy")` — exact protocol signature from PB1.1
- `get_code_snippet("SignalEvent")` — severity literals
- `search_graph("OptionChain")` — confirm import for `MarketDataProvider` return type
- `search_graph("is_trading_day")` — confirm import path from `src/market_calendar/`

**What to implement:**

`StrategyMonitor` is the backbone daemon loop. It does not know about IC, CSP, or 3-track.

```python
class StrategyMonitor:
    def __init__(
        self,
        broker: BrokerClient,
        store: PaperStore,
        notifier: TelegramGateway,
        strategies: list[PaperStrategy],
        poll_interval_s: int = 90,
    ) -> None: ...

    def register(self, strategy: PaperStrategy) -> None:
        """Add a strategy to the registry after construction."""

    async def run(self) -> None:
        """
        Main daemon loop. Runs until cancelled.
        On each tick:
          1. Skip if not a trading day or outside 09:15–15:30 IST.
          2. Fetch live OptionChain once (shared across all strategies).
          3. Load open PaperPositions from PaperStore.
          4. For each registered strategy: call check_signals(market, positions).
          5. Route each SignalEvent:
             - INFO  → log at DEBUG, no Telegram
             - WARN  → send plain Telegram message via notifier
             - ACTION → call notifier.send_approval_request(event, context_str)
                        write row to pending_approvals
          6. Write heartbeat to daemon_heartbeat.
          7. Sleep poll_interval_s seconds.
        """

    async def _tick(self) -> None:
        """Single tick — extracted for testability."""

    def _write_heartbeat(self, pid: int) -> None:
        """Upsert daemon_heartbeat row (id=1)."""
```

**Market data fetch:** Call `broker.get_option_chain("NSE_INDEX|Nifty 50")` — reuse the
existing `parse_upstox_option_chain` path. If the fetch fails, log WARNING and skip the
tick (do not crash the daemon).

**IST window check:** 09:15 to 15:30 inclusive. Compute from UTC system time + IST offset
(`+05:30`). Do not import pytz — use `datetime.timezone(timedelta(hours=5, minutes=30))`.

**Tests (`tests/unit/strategy/test_strategy_monitor.py`):**

Use `MockStrategy` from test_strategy_protocol (import it) and a `MockBrokerClient`.

- `register()` adds strategy to internal list; `len(monitor._strategies) == 1`.
- `_tick()` with one strategy returning `[]` → heartbeat written, no approval created.
- `_tick()` with one strategy returning `[SignalEvent("INFO", ...)]` → no Telegram call.
- `_tick()` with one strategy returning `[SignalEvent("WARN", ...)]` → notifier
  `send_plain_message` called once.
- `_tick()` with one strategy returning `[SignalEvent("ACTION", ...)]` → notifier
  `send_approval_request` called once; `pending_approvals` row created with status `PENDING`.
- Broker raises `DataFetchError` → tick completes without raising; heartbeat still written.
- Empty strategy list → tick completes silently, heartbeat written.

**Commit:** `feat(strategy): add StrategyMonitor daemon loop with registry and signal routing`

---

## PB1.3 — `src/strategy/executor.py`: PaperExecutor + PaperFillSimulator + tests

**Files to change:**
- `src/strategy/executor.py` — `PaperFillSimulator` + `PaperExecutor`
- `tests/unit/strategy/test_executor.py` — new test file

**Before any code:**
- `get_code_snippet("PaperStore")` — confirm `record_trade` signature
- `get_code_snippet("PaperTrade")` — exact field list; confirm `paper_` prefix validator
- `get_code_snippet("ApprovedAction")` — field list from PB1.1
- `get_code_snippet("LegSpec")` — field list from PB1.1
- `search_graph("compute_ivr")` — confirm import path from `src/backtest/ivr.py`
- Read `DECISIONS.md` section on slippage model before implementing `PaperFillSimulator`

**What to implement:**

**`PaperFillSimulator`** — VIX-regime slippage model from `DECISIONS.md §Slippage`.
Port the model as documented; do not reinvent.

```python
@dataclass(frozen=True)
class FillResult:
    instrument_key: str
    action: Literal["BUY", "SELL"]
    quantity: int
    fill_price: Decimal     # mid ± slippage
    slippage: Decimal       # absolute slip applied


class PaperFillSimulator:
    def simulate_fill(
        self,
        instrument_key: str,
        action: Literal["BUY", "SELL"],
        quantity: int,
        mid_price: Decimal,
        vix: float | None = None,
    ) -> FillResult:
        """
        Compute synthetic fill using VIX-regime slippage model.
        BUY fill_price = mid + slippage (paid more).
        SELL fill_price = mid - slippage (received less).
        """
```

**`PaperExecutor`** — thin layer over `PaperStore`. Given an `ApprovedAction`:

```python
class PaperExecutor:
    def __init__(
        self,
        store: PaperStore,
        simulator: PaperFillSimulator,
        db_path: str,
    ) -> None: ...

    def apply(
        self,
        strategy_name: str,
        action: ApprovedAction,
        market: OptionChain,
        approval_id: int,
        vix: float | None = None,
    ) -> list[PaperPosition]:
        """
        1. For each leg_role in action.legs_to_close: record a closing trade via
           PaperStore.record_trade (action=opposite of entry, price=simulated fill).
        2. For each LegSpec in action.legs_to_open: simulate fill, call
           PaperStore.record_trade to open the leg.
        3. Write a row to council_outputs for audit (approval_id FK).
        4. Return the updated list[PaperPosition] from PaperStore.get_open_positions().
        """
```

**Tests (`tests/unit/strategy/test_executor.py`):**

- `PaperFillSimulator.simulate_fill` with low VIX → slippage in low-vol band.
- `simulate_fill` with high VIX → slippage in high-vol band.
- `simulate_fill` with `vix=None` → uses base/default slippage, no error.
- BUY fill_price > mid; SELL fill_price < mid.
- `PaperExecutor.apply` with one leg to open → `PaperStore.record_trade` called once with
  correct `action`, `price`, `strategy_name`.
- `PaperExecutor.apply` with one leg to close → closing trade recorded with opposite action.
- `apply` with empty `legs_to_open` and empty `legs_to_close` → no store calls, returns
  current positions unchanged.

**Commit:** `feat(strategy): add PaperFillSimulator + PaperExecutor`

---

## PB1.4 — `src/council/rapid.py`: RapidCouncil + tests

**Files to change:**
- `src/council/__init__.py` — new package, single comment line only
- `src/council/models.py` — `CouncilOutput` + `PersonaResponse` dataclasses
- `src/council/rapid.py` — `RapidCouncil`
- `tests/unit/council/__init__.py` — new test package, single comment line only
- `tests/unit/council/test_rapid_council.py` — new test file

**Before any code:**
- `search_graph("RapidCouncil")` — confirm does NOT yet exist
- `get_code_snippet("ApprovedAction")` — field list; this is what chairman must produce
- `get_code_snippet("SignalEvent")` — input to council
- `search_code("aiohttp")` in `src/client/` — confirm aiohttp usage pattern for HTTP calls
- `search_code("OPENROUTER_API_KEY")` in `.env.example` — confirm env var name

**What to implement (`src/council/models.py`):**

```python
@dataclass(frozen=True)
class PersonaResponse:
    persona: str            # "QuantAnalyst" | "SpecGuardian" | "RiskManager" | "OptionsStrategist"
    model: str
    response: str           # raw text from model
    latency_ms: int
    timed_out: bool = False


@dataclass(frozen=True)
class CouncilOutput:
    actions: list[ApprovedAction]       # chairman-ranked, rank 1 = top pick
    chairman_rationale: str
    dissenting_notes: str | None
    stage1_responses: list[PersonaResponse]
    latency_ms: int                     # total wall-clock time
```

**What to implement (`src/council/rapid.py`):**

Council composition:

| Persona | Model | API endpoint |
|---|---|---|
| QuantAnalyst | `deepseek/deepseek-r1-0528` | OpenRouter |
| SpecGuardian | `claude-haiku-4-5-20251001` | Anthropic direct |
| RiskManager | `openai/o3-mini` | OpenRouter |
| OptionsStrategist | `x-ai/grok-4-fast` | xAI direct (`https://api.x.ai/v1`) |
| Chairman | `claude-sonnet-4-6` | Anthropic direct |

```python
class RapidCouncil:
    def __init__(
        self,
        spec_doc: str,          # strategy spec text passed to SpecGuardian
        openrouter_api_key: str,
        anthropic_api_key: str,
        xai_api_key: str,
    ) -> None: ...

    async def consult(
        self,
        event: SignalEvent,
        context: str,           # strategy.describe_context() output
    ) -> CouncilOutput:
        """
        Stage 1: fire all four persona calls in parallel via asyncio.gather.
                 Each call: asyncio.wait_for(..., timeout=25.0).
                 Timed-out persona → PersonaResponse(timed_out=True, response="").
        Stage 2: pass all Stage 1 responses to Chairman with timeout=15.0.
                 Chairman produces ranked ApprovedAction list.
        Full timeout: if Chairman times out → raise CouncilTimeoutError.
        """
```

**Prompt construction** — inline in `rapid.py`, not a separate module at this stage:
- Each Stage 1 persona receives: the strategy context string + their persona framing.
- SpecGuardian additionally receives `spec_doc` and must output "COMPLIANT / NON-COMPLIANT"
  for each proposed action with the cited clause.
- Chairman receives all Stage 1 responses and produces a JSON array of `ApprovedAction`
  objects ranked by quality.

**API calls** — use `aiohttp.ClientSession` with `asyncio.wait_for`. All calls must have
explicit `Content-Type: application/json` headers and bearer token auth.

**Error handling** — `CouncilTimeoutError(BrokerError)` for full chairman timeout.
Individual Stage 1 timeouts do not raise — chairman proceeds with partial responses.

**Tests (`tests/unit/council/test_rapid_council.py`):**

All API calls must be mocked (no network). Use `unittest.mock.AsyncMock`.

- Happy path: all four Stage 1 calls resolve → chairman called with four responses.
- Stage 1 partial timeout: one persona times out → chairman called with 3 responses + 1
  `timed_out=True`; no exception raised.
- All Stage 1 calls return → chairman produces 2 `ApprovedAction` items → `CouncilOutput`
  has `len(actions) == 2`.
- SpecGuardian NON-COMPLIANT response → chairman still called; result in `dissenting_notes`.
- Chairman timeout → `CouncilTimeoutError` raised.
- `latency_ms` field is positive integer.

**Commit:** `feat(council): add RapidCouncil with parallel Stage 1 + chairman synthesis`

---

## PB1.5 — `src/notifications/telegram_gateway.py`: TelegramGateway + tests

**Files to change:**
- `src/notifications/telegram_gateway.py` — `TelegramGateway`
- `tests/unit/notifications/test_telegram_gateway.py` — new test file

**Before any code:**
- `get_code_snippet("TelegramNotifier")` — exact `__init__` signature + `send_message` method
- `search_code("TELEGRAM_BOT_TOKEN")` in `src/notifications/` — confirm env var name
- `get_code_snippet("CouncilOutput")` — field list from PB1.4
- `search_graph("PaperStore")` — confirm `get_pending_approvals` will be added in PB1.6;
  for now just query via `db_connection` directly
- `search_code("non-fatal")` in `src/notifications/CLAUDE.md` — confirm the non-fatal contract

**What to implement:**

`TelegramGateway` extends (wraps, does not inherit) `TelegramNotifier`. Added capabilities:

```python
class TelegramGateway:
    def __init__(
        self,
        bot_token: str,
        chat_id: str,
        db_path: str,
    ) -> None:
        self._notifier = TelegramNotifier(bot_token, chat_id)
        ...

    def send_plain_message(self, text: str) -> bool:
        """Delegate to TelegramNotifier.send_message. Non-fatal."""

    async def send_approval_request(
        self,
        council_output: CouncilOutput,
        event: SignalEvent,
        strategy_name: str,
    ) -> int | None:
        """
        Send inline-keyboard message with council-ranked actions.
        Keyboard buttons: one per ApprovedAction (labelled by action_type + rationale[:40]).
        Plus a "Reject All" button.
        Returns Telegram message_id on success, None on failure. Non-fatal.
        """

    async def start_polling(
        self,
        on_approved: Callable[[int, int], Awaitable[None]],   # (approval_id, rank)
        on_rejected: Callable[[int], Awaitable[None]],        # (approval_id,)
    ) -> None:
        """
        Async long-polling loop for CallbackQuery events (button presses).
        Auth guard: silently drop any update not from TELEGRAM_CHAT_ID.
        Routes button press to on_approved or on_rejected callbacks.
        Runs until cancelled.
        """
```

**Timeout scanner** — background asyncio task started inside `start_polling`:
Checks `pending_approvals` every 5 minutes. Rows with `status = 'PENDING'` and
`expires_at < now` → set `status = 'EXPIRED'`, set `resolved_at = now`.
Non-fatal: exception in scanner logs WARNING, loop continues.

**Auth guard** — every inbound `CallbackQuery` handler checks that `from.id` or
`chat.id` matches `TELEGRAM_CHAT_ID`. Unknown senders → log WARNING, no callback fired.

**Non-fatal contract** — all Telegram API calls wrapped in `try/except Exception`.
Return `False` / `None` on failure. Never raise.

**Tests (`tests/unit/notifications/test_telegram_gateway.py`):**

Mock `aiohttp.ClientSession` (no real HTTP calls).

- `send_plain_message` succeeds → returns `True`.
- `send_plain_message` raises network error → returns `False`, no exception propagated.
- `send_approval_request` with 2 actions → message sent with inline keyboard containing 3
  buttons (2 actions + Reject All).
- `send_approval_request` API failure → returns `None`, no exception.
- Auth guard: `CallbackQuery` from unknown chat_id → `on_approved` callback NOT called.
- Auth guard: `CallbackQuery` from correct chat_id → `on_approved` callback called with
  correct `(approval_id, rank)`.
- Timeout scanner: `pending_approvals` row with `expires_at` in the past → status set to
  `EXPIRED`.

**Commit:** `feat(notifications): add TelegramGateway with approval flow and inbound polling`

---

## PB1.6 — `src/paper/store.py`: DB migrations + approval store methods + tests

**Files to change:**
- `src/paper/store.py` — add three table migrations + approval CRUD methods
- `tests/unit/paper/test_paper_store_approvals.py` — new test file (keep existing tests untouched)

**Before any code:**
- `get_code_snippet("PaperStore")` — current `__init__` and existing table list
- `get_code_snippet("db_connection")` — confirm context manager signature
- Read `docs/plan/paper-backbone/paper_backbone_schema.md` — exact DDL for all three tables

**What to implement in `PaperStore`:**

Three table migrations added to `PaperStore.__init__` via `init_db()` (or inline if that's
the existing pattern — check with `get_code_snippet` first):

```sql
-- from paper_backbone_schema.md (add these three tables)
pending_approvals, council_outputs, daemon_heartbeat
```

New methods:

```python
def create_approval(
    self,
    strategy_name: str,
    event_type: str,
    council_output_json: str,
    telegram_msg_id: int | None,
    expires_at: str,            # ISO UTC
) -> int:
    """INSERT into pending_approvals, status=PENDING. Returns new row id."""

def resolve_approval(
    self,
    approval_id: int,
    status: Literal["APPROVED", "REJECTED", "EXPIRED"],
    approved_rank: int | None = None,
) -> None:
    """UPDATE pending_approvals: set status, resolved_at=now(), approved_rank."""

def get_pending_approvals(self) -> list[dict]:
    """SELECT all rows with status=PENDING, ordered by created_at ASC."""

def write_heartbeat(
    self,
    pid: int,
    strategies: list[str],
    last_event: str | None = None,
) -> None:
    """INSERT OR REPLACE into daemon_heartbeat (id=1). Updates last_beat=now UTC."""

def get_heartbeat(self) -> dict | None:
    """SELECT the single daemon_heartbeat row. Returns None if absent."""
```

**Tests (`tests/unit/paper/test_paper_store_approvals.py`):**

All tests use `tmp_path` fixture with a fresh `PaperStore`.

- `create_approval` → `get_pending_approvals` returns one row with status `PENDING`.
- `resolve_approval(APPROVED, rank=1)` → row no longer in `get_pending_approvals`;
  `resolved_at` is set.
- `resolve_approval(EXPIRED)` → row no longer in `get_pending_approvals`.
- `create_approval` called twice → `get_pending_approvals` returns two rows.
- `resolve_approval` one of two → `get_pending_approvals` returns one row.
- `write_heartbeat` then `get_heartbeat` → round-trip; `pid`, `strategies` JSON correct.
- `write_heartbeat` called twice → still one row (upsert).
- `get_heartbeat` on empty DB → `None`.
- All three new tables created by `PaperStore.__init__` → existing `paper_trades` table
  unaffected (confirm row count unchanged after migration).

**Commit:** `feat(paper): add pending_approvals + council_outputs + daemon_heartbeat migrations and store methods`

---

## PB1.7 — Daemon + cron scripts + requirements.txt

**Files to change:**
- `scripts/monitor_daemon.py` — persistent daemon process
- `scripts/start_monitor.py` — launches daemon if not running
- `scripts/stop_monitor.py` — sends SIGTERM to daemon
- `scripts/pre_market_brief.py` — 09:00 stateless cron
- `scripts/eod_summary.py` — 15:35 stateless cron
- `requirements.txt` — add `python-telegram-bot>=21.0`

**Before any code:**
- `get_code_snippet("StrategyMonitor")` — constructor signature from PB1.2
- `get_code_snippet("TelegramGateway")` — constructor signature from PB1.5
- `get_code_snippet("PaperStore")` — confirm `write_heartbeat` + `get_heartbeat` from PB1.6
- `get_code_snippet("build_notifier")` — existing Telegram factory in `src/notifications/`
- `search_code("UPSTOX_ENV")` in existing scripts — confirm env var for client selection
- `search_code("factory")` in `scripts/daily_snapshot.py` — confirm factory.py usage pattern

**What to implement:**

**`scripts/monitor_daemon.py`** — Two concurrent asyncio tasks:
`StrategyMonitor.run()` and `TelegramGateway.start_polling()`.
Writes heartbeat on every tick. Handles `SIGTERM` cleanly:
  1. Cancel both tasks.
  2. Set all `PENDING` approvals to `EXPIRED`.
  3. Write final heartbeat with `last_event="SHUTDOWN"`.
  4. `sys.exit(0)`.

Registered strategies at startup: `CSPNiftyV1`, `IronCondorV1`, `NiftyTrackComparisonV1`
(instantiate each; if a strategy raises on init, log ERROR and skip — do not crash daemon).

**`scripts/start_monitor.py`** — Checks `daemon_heartbeat.last_beat`. If absent or stale
(> 5 minutes old): launch `python -m scripts.monitor_daemon` via `subprocess.Popen`.
Exits immediately after launch (does not block).

**`scripts/stop_monitor.py`** — Reads PID from `daemon_heartbeat`. Sends `SIGTERM`.
Polls for up to 30 seconds. If process still alive: sends `SIGKILL`. Logs outcome.

**`scripts/pre_market_brief.py`** — Stateless. Cron: `00 09 * * 1-5`.
Fetches open `PaperPosition`s from all 4 strategy names.
Formats a Telegram message: strategy name, leg count, total unrealized P&L, IVR.
Sends via `TelegramGateway.send_plain_message`. Non-fatal.

**`scripts/eod_summary.py`** — Stateless. Cron: `35 15 * * 1-5`.
Fetches today's `paper_nav_snapshots`. Formats daily P&L summary per strategy.
Fetches today's council activity count from `pending_approvals`.
Sends via `TelegramGateway.send_plain_message`. Non-fatal.

**Cron additions (document in script header comments):**
```
00 09 * * 1-5  python -m scripts.pre_market_brief
15 09 * * 1-5  python -m scripts.start_monitor
30 15 * * 1-5  python -m scripts.stop_monitor
35 15 * * 1-5  python -m scripts.eod_summary
```

No unit tests required for daemon/cron scripts (no testable pure logic beyond what
store and monitor tests cover).

**Commit:** `feat(scripts): add monitor_daemon + start/stop + pre_market_brief + eod_summary + python-telegram-bot dep`

---

## PB2.1 — `src/strategy/csp_nifty_v1.py`: CSPNiftyV1 + tests

**Files to change:**
- `src/strategy/csp_nifty_v1.py` — `CSPNiftyV1` implements `PaperStrategy`
- `tests/unit/strategy/test_csp_nifty_v1.py` — new test file

**Before any code:**
- `get_code_snippet("PaperStrategy")` — exact protocol signature
- `get_code_snippet("PaperPosition")` — field list; confirm `leg_role` and `net_qty` fields
- `get_code_snippet("OptionChain")` — field list; confirm how to find a strike by delta
- Read `docs/strategies/csp_nifty_v1.md` — authoritative strategy spec (entry rules,
  exit triggers, delta thresholds). Do not implement from memory.
- `search_graph("get_expiry_candidates")` — confirm import path

**Context:** CSP is already running via `record_paper_trade.py` + `paper_3track_snapshot.py`.
This phase adds the backbone-compatible class so the daemon can auto-detect exit signals.
Existing `paper_trades` rows are unaffected. Entry remains manual.

**What to implement:**

```python
class CSPNiftyV1:
    strategy_name = "paper_csp_nifty_v1"

    async def check_signals(
        self,
        market: OptionChain,
        positions: list[PaperPosition],
    ) -> list[SignalEvent]:
        """
        Filter positions to strategy_name == "paper_csp_nifty_v1".
        If no open positions: return [].
        For each open short_put leg, evaluate (from csp_nifty_v1.md spec):
        """
```

Signal table (from strategy spec):

| Event type | Severity | Trigger |
|---|---|---|
| `PROFIT_TARGET` | ACTION | mark ≤ 50% of entry credit |
| `LOSS_STOP` | ACTION | mark ≥ 2.0× entry credit |
| `DELTA_STOP` | ACTION | short put \|delta\| ≥ 0.35 |
| `TIME_STOP` | ACTION | DTE ≤ 21 |
| `ROLL_DUE_DTE` | WARN | DTE ≤ 5 |
| `ROLL_DUE_DECAY` | WARN | current premium ≤ 25% of entry premium |
| `DELTA_WARN` | WARN | short put \|delta\| ≥ 0.25 |

`apply_action()` accepts `CLOSE_FULL` only. Any other `action_type` raises `ValueError`.
Entry is manual — no `ENTER_*` action type.

`describe_context()` — returns a structured plain-text string: current delta, DTE,
mark vs entry credit, % of credit captured, IVR, Nifty spot.

**Tests (`tests/unit/strategy/test_csp_nifty_v1.py`):**

- No open positions → `check_signals` returns `[]`.
- Short put with mark = 48% of entry credit → `PROFIT_TARGET` ACTION event.
- Short put with mark = 210% of entry credit → `LOSS_STOP` ACTION event.
- Short put with `|delta| = 0.36` → `DELTA_STOP` ACTION event.
- Short put with DTE = 20 → `TIME_STOP` ACTION event.
- Short put with DTE = 4 → `ROLL_DUE_DTE` WARN event.
- Short put with mark = 24% of entry premium → `ROLL_DUE_DECAY` WARN event.
- Short put with `|delta| = 0.27` → `DELTA_WARN` WARN event.
- Short put with mark = 60%, `|delta| = 0.20`, DTE = 30 → `[]` (no events).
- `apply_action` with `CLOSE_FULL` → no error.
- `apply_action` with `ADJUST` → raises `ValueError`.

**Commit:** `feat(strategy): add CSPNiftyV1 backbone integration`

---

## PB3.1 — `src/strategy/ic_nifty_v1.py`: IronCondorV1 + tests

**Files to change:**
- `src/strategy/ic_nifty_v1.py` — `IronCondorV1` implements `PaperStrategy`
- `tests/unit/strategy/test_ic_nifty_v1.py` — new test file

**Before any code:**
- `get_code_snippet("PaperStrategy")` — exact protocol signature
- `get_code_snippet("PaperPosition")` — field list; confirm `leg_role` field
- Read `docs/strategies/ic_nifty_v1.md` — authoritative spec. Council ruling:
  `docs/council/2026-05-02_iron-condor-v1-core-design.md` — no adjustments in v1,
  all ACTION events route to exit only.
- `search_code("SpecGuardian")` — confirm SpecGuardian will receive `ic_nifty_v1.md`

**What to implement:**

```python
class IronCondorV1:
    strategy_name = "paper_ic_nifty_v1"
```

Signal table (from strategy spec):

| Event type | Severity | Trigger |
|---|---|---|
| `PROFIT_TARGET` | ACTION | mark ≤ 50% of entry credit |
| `LOSS_STOP` | ACTION | mark ≥ 2.0× entry credit |
| `DELTA_STOP` | ACTION | either short leg \|delta\| ≥ 0.35 |
| `TIME_STOP` | ACTION | DTE ≤ 14 |
| `DELTA_WARN` | WARN | either short leg \|delta\| ≥ 0.25 |
| `DTE_WARN` | INFO | DTE ≤ 21 |

No open position → `check_signals()` returns `[]`. Entry is manual via
`scripts/paper_ic_entry.py` (not in this phase; document as future script).

`apply_action()` accepts only `CLOSE_FULL`, `CLOSE_CALL_SPREAD`, `CLOSE_PUT_SPREAD`.
Any other `action_type` raises `ValueError` — the spec forbids adjustments in v1.

`describe_context()` — returns: call spread delta, put spread delta, combined credit,
mark-to-market, DTE, IVR, Nifty spot.

**Tests (`tests/unit/strategy/test_ic_nifty_v1.py`):**

Mirror the CSP test structure with IC-specific triggers:

- No open positions → `[]`.
- Combined mark ≤ 50% of entry credit → `PROFIT_TARGET` ACTION.
- Combined mark ≥ 200% of entry credit → `LOSS_STOP` ACTION.
- Short call `|delta| = 0.36` → `DELTA_STOP` ACTION.
- Short put `|delta| = 0.36` → `DELTA_STOP` ACTION (either leg triggers it).
- DTE = 13 → `TIME_STOP` ACTION.
- Short call `|delta| = 0.27` → `DELTA_WARN` WARN.
- DTE = 19 → `DTE_WARN` INFO.
- Healthy IC (mark 70%, both deltas 0.15, DTE 30) → `[]`.
- `apply_action(CLOSE_FULL)` → no error.
- `apply_action(CLOSE_CALL_SPREAD)` → no error.
- `apply_action(ADJUST_WINGS)` → raises `ValueError`.

**Commit:** `feat(strategy): add IronCondorV1 backbone integration`

---

## PB4.1 — `src/strategy/nifty_track_comparison_v1.py`: NiftyTrackComparisonV1 + tests

**Files to change:**
- `src/strategy/nifty_track_comparison_v1.py` — `NiftyTrackComparisonV1` implements `PaperStrategy`
- `tests/unit/strategy/test_nifty_track_comparison_v1.py` — new test file

**Before any code:**
- `get_code_snippet("PaperStrategy")` — protocol signature
- `get_code_snippet("PaperPosition")` — field list; confirm `leg_role` values used by 3-track
- Read `docs/strategies/nifty_track_comparison_v1.md` — authoritative spec
- `search_code("paper_nifty_spot")` in `scripts/paper_3track_snapshot.py` — confirm
  the 3 strategy_name strings and leg_role values in live data

**Context:** 3-track already runs via `paper_3track_snapshot.py` (EOD cron) and
`paper_3track_overlay_roll.py` (manual roll). This phase adds WARN event routing so
the daemon delivers roll reminders via Telegram. No ACTION events — rolls remain manual.
`paper_3track_snapshot.py` is retained alongside the backbone during the migration period.

**What to implement:**

```python
class NiftyTrackComparisonV1:
    strategy_name = "paper_nifty_3track_v1"

    TRACK_STRATEGY_NAMES = [
        "paper_nifty_spot",
        "paper_nifty_futures",
        "paper_nifty_proxy",
    ]
```

`check_signals()` covers all three tracks as a single registered strategy:

| Event type | Severity | Trigger |
|---|---|---|
| `ROLL_DUE_DTE` | WARN | any open overlay leg with DTE ≤ 5 |
| `ROLL_DUE_DECAY` | WARN | any short overlay premium ≤ 25% of entry |
| `OVERLAY_EXPIRED` | WARN | overlay expiry date has passed with no roll recorded |

No ACTION events. `apply_action()` is a no-op (returns positions unchanged) — document
clearly that rolls are executed manually via `paper_3track_overlay_roll.py`.

`describe_context()` — returns: track name, leg role, DTE remaining, current premium vs
entry premium, % captured.

**Tests (`tests/unit/strategy/test_nifty_track_comparison_v1.py`):**

- No open overlay legs → `[]`.
- Overlay leg with DTE = 4 → `ROLL_DUE_DTE` WARN event; `payload` contains track name.
- Short overlay with premium = 22% of entry → `ROLL_DUE_DECAY` WARN.
- Overlay leg with expiry yesterday, no roll recorded → `OVERLAY_EXPIRED` WARN.
- Healthy overlays (DTE 15, premium 60%) → `[]`.
- All three tracks trigger simultaneously → three separate WARN events.
- `apply_action` called with any action → returns positions unchanged, no error.

**Commit:** `feat(strategy): add NiftyTrackComparisonV1 backbone integration`

---

## PB5 — Docs close

**Files to change:**
- `CONTEXT.md` — add `src/strategy/` and `src/council/` to module tree; add
  `scripts/monitor_daemon.py`, `scripts/start_monitor.py`, `scripts/stop_monitor.py`,
  `scripts/pre_market_brief.py`, `scripts/eod_summary.py` to scripts list;
  add `src/notifications/telegram_gateway.py` note
- `DECISIONS.md` — entry: "paper-backbone added: PaperStrategy protocol, StrategyMonitor
  daemon, RapidCouncil (5-persona heterogeneous), TelegramGateway approval flow;
  PT-S0/S1/S3 strategies integrated; PT-S2 (Signal Pipeline) blocked on signals story"
- `TODOS.md` — session log entry

No code changes. No tests. Targeted `Edit` calls only — never `Write` on these files.

**Commit:** `docs(strategy): update CONTEXT.md, DECISIONS.md, TODOS.md for paper-backbone`

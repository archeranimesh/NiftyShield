# PB1.2 — `src/strategy/monitor.py`: StrategyMonitor + tests
> **Assigned to: Claude** — IST window logic and broker error handling require inline judgment.

**Files to change:**
- `src/strategy/monitor.py` — `StrategyMonitor` class
- `tests/unit/strategy/test_strategy_monitor.py` — new test file

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

## Pre-baked Context

> Graph queries pre-run 2026-05-31. Skip "Before any code" graph calls — use these directly.

**`PaperStrategy`** — defined in `src/strategy/protocol.py` (created in PB1.1).
Import: `from src.strategy.protocol import PaperStrategy, SignalEvent, ApprovedAction`.
`severity` literals: `"INFO"`, `"WARN"`, `"ACTION"`.

**`SignalEvent`** — frozen dataclass. Fields: `event_type: str`, `severity: Literal["INFO","WARN","ACTION"]`,
`description: str`, `payload: dict[str, Any]`.

**`OptionChain`** — `src/models/options.py:69`. Import: `from src.models.options import OptionChain`.
Fields: `underlying_spot: Decimal`, `expiry: date`, `strikes: dict[Decimal, OptionChainStrike]`.

**`is_trading_day`** — `src/market_calendar/holidays.py:82`.
Import: `from src.market_calendar.holidays import is_trading_day`.
Signature: `is_trading_day(d: date, *, data_dir: Path = _DATA_DIR) -> bool`.
Returns `False` for weekends; checks NSE holiday YAML. Fail-open if YAML absent.

**`PaperStore`** — `src/paper/store.py:110`. Constructor: `PaperStore(db_path: Path | str)`.
Relevant methods for this task: `get_positions(strategy_name) -> list[PaperPosition]`,
`write_heartbeat(pid, strategies, last_event)` (added in PB1.6 — stub or add alongside).

**`BrokerClient`** — protocol in `src/client/protocol.py`. Use `MockBrokerClient` in tests
(import from `src/client/mock_client.py`).

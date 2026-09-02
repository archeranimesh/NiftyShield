# src/client — Module Context

> Auto-loaded when working inside `src/client/`. Read this before touching any file here.
> Invariants and caller contracts only — the implementations table, the sub-protocol method
> split, and the `MockBrokerClient` setup API live in **`NOTES.md`** (same directory, not
> auto-loaded).

---

## The Cardinal Rule: No Concrete Imports Outside `factory.py`

All modules outside `src/client/` **must** depend only on `src.client.protocol.BrokerClient` (or a sub-protocol). They receive a client via constructor injection.

`factory.py` is the **only** file in `src/` that imports `UpstoxLiveClient` or `MockBrokerClient` directly. If you find yourself writing `from src.client.upstox_live import UpstoxLiveClient` outside `factory.py`, stop — you're breaking the DI contract.

```python
# ✅ Correct — any module consuming a client
def __init__(self, client: BrokerClient) -> None: ...

# ❌ Wrong — direct concrete import outside factory.py
from src.client.upstox_live import UpstoxLiveClient
```

`create_client(env)` in `factory.py` selects the implementation: `"prod"` → `UpstoxLiveClient(UPSTOX_ANALYTICS_TOKEN)`, `"sandbox"` → `UpstoxLiveClient(UPSTOX_SANDBOX_TOKEN)`, `"test"` → `MockBrokerClient`. Which implementation to reach for when: `NOTES.md`.

---

## Active Constraints

| Method | Status | Reason |
|---|---|---|
| `place_order`, `modify_order`, `cancel_order` | ⛔ `NotImplementedError` | Static IP not provisioned |
| `get_positions`, `get_holdings`, `get_margins` | ⛔ `NotImplementedError` | Daily OAuth token not wired |
| `get_historical_candles` | ⛔ `NotImplementedError` | Not yet implemented |
| `get_expired_option_contracts` | ⛔ `NotImplementedError` | Paid Upstox subscription required |
| `get_ltp`, `get_option_chain` | ✅ Live | Analytics Token (long-lived) |

Blocked methods raise `NotImplementedError` with an explanatory message via `_raise_order_blocked()`. Never return `None` silently — fail loudly.

---

## Sub-Protocols (ISP)

Three narrow sub-protocols in `protocol.py` — `MarketDataProvider`, `OrderExecutor`, `PortfolioReader`. Depend on the narrowest one that covers your use. `BrokerClient` is flat (not inheriting from them) so its full method list is readable in one place; structural typing means any class satisfying all 10 `BrokerClient` methods satisfies all three. Per-protocol method lists: `NOTES.md`.

---

## `MockBrokerClient`

Offline test double — `set_price` / `set_margin` / `simulate_error` / `reset` setup API in `NOTES.md`. Missing fixtures log `WARNING` and return `None`/`[]`/`{}` — never raises.

---

## Exception Hierarchy (`exceptions.py`)

```
BrokerError
├── AuthenticationError
├── RateLimitError
├── DataFetchError
│   └── LTPFetchError
├── OrderRejectedError
│   └── InsufficientMarginError
└── InstrumentNotFoundError
```

`DataFetchError` is retryable. `OrderRejectedError` and `InstrumentNotFoundError` are terminal — do not retry.

---

## `upstox_market.py` — Legacy Module

Pre-abstraction sync `requests` client, wrapped inside `UpstoxLiveClient`. Violates the DI rule. Do not add new dependents on `UpstoxMarketClient` directly.

---

## Two-Token Constraint

- **Analytics Token** (`UPSTOX_ANALYTICS_TOKEN`) — long-lived, powers `get_ltp` + `get_option_chain`.
- **Daily OAuth Token** (`UPSTOX_ACCESS_TOKEN`) — expires daily, required for portfolio-read methods. Not currently wired into `UpstoxLiveClient`.

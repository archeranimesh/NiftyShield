# src/client — Module Context

> Auto-loaded when working inside `src/client/`. Read this before touching any file here.

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

---

## Four Implementations

| Class | File | When Used | Network |
|---|---|---|---|
| `UpstoxLiveClient` | `upstox_live.py` | Production + manual dev testing | Yes — live Upstox APIs |
| `UpstoxLiveClient` (sandbox token) | `upstox_live.py` | Pre-deploy integration tests | Yes — Upstox sandbox |
| `MockBrokerClient` | `mock_client.py` | Unit tests, offline dev, CI, **all order testing** | **No** — fully offline |
| *(ReplayMarketStream)* | *(not yet built)* | Strategy testing with recorded tick feeds | No |

`create_client(env)` in `factory.py` selects the implementation: `"prod"` → `UpstoxLiveClient(UPSTOX_ANALYTICS_TOKEN)`, `"sandbox"` → `UpstoxLiveClient(UPSTOX_SANDBOX_TOKEN)`, `"test"` → `MockBrokerClient`.

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

Three narrow sub-protocols in `protocol.py`:
- `MarketDataProvider` — `get_ltp`, `get_option_chain` (used by tracker/signals)
- `OrderExecutor` — `place_order`, `modify_order`, `cancel_order` (execution layer)
- `PortfolioReader` — `get_positions`, `get_holdings`, `get_margins`

`BrokerClient` is flat (not inheriting from sub-protocols) so its full method list is readable in one place. Python structural typing — any class satisfying all 10 `BrokerClient` methods automatically satisfies all three sub-protocols.

---

## `MockBrokerClient` Setup API

For tests, after constructing `MockBrokerClient(fixtures_dir=...)`:
```python
mock.set_price("NSE_EQ|INE...", Decimal("100.50"))
mock.set_margin(Decimal("500000"))
mock.simulate_error("place_order", RateLimitError("mock rate limit"))  # one-shot
mock.reset()  # clears orders/positions/error queue; preserves _price_map
```
Missing fixtures log `WARNING` and return `None`/`[]`/`{}` — never raises.

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

Sync `requests` client built before the `BrokerClient` abstraction. Violates the DI rule. Currently wrapped inside `UpstoxLiveClient` — no other consumer should import it. Do not add new dependents on `UpstoxMarketClient` directly.

---

## Two-Token Constraint

- **Analytics Token** (`UPSTOX_ANALYTICS_TOKEN`) — long-lived, powers `get_ltp` + `get_option_chain`.
- **Daily OAuth Token** (`UPSTOX_ACCESS_TOKEN`) — expires daily, required for portfolio-read methods. Not currently wired into `UpstoxLiveClient`.

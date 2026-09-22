# src/client — Reference Notes

> **Not auto-loaded.** Reference detail relocated out of `CLAUDE.md` (FIX-2, `docs/archive/plan/token-efficiency/fixed-overhead/`) so the auto-injected file carries only invariants and caller
> contracts.

---

## Implementations (2 built + 1 variant + 1 planned)

| Class | File | When Used | Network |
|---|---|---|---|
| `UpstoxLiveClient` | `upstox_live.py` | Production + manual dev testing | Yes — live Upstox APIs |
| `UpstoxLiveClient` (sandbox token) | `upstox_live.py` | Pre-deploy integration tests | Yes — Upstox sandbox |
| `MockBrokerClient` | `mock_client.py` | Unit tests, offline dev, CI, **all order testing** | **No** — fully offline |
| *(ReplayMarketStream)* | *(not yet built)* | Strategy testing with recorded tick feeds | No |

---

## Sub-Protocols (ISP) — full method split

Three narrow sub-protocols in `protocol.py`:

- `MarketDataProvider` — `get_ltp`, `get_option_chain`, `get_ohlc` (used by tracker/signals)
- `OrderExecutor` — `place_order`, `modify_order`, `cancel_order` (execution layer)
- `PortfolioReader` — `get_positions`, `get_holdings`, `get_margins`

`BrokerClient` is flat (not inheriting from sub-protocols) so its full method list is readable in one place. Python structural typing — any class satisfying all 10 `BrokerClient` methods automatically
satisfies all three sub-protocols.

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

## `upstox_market.py` — Legacy Module

Sync `requests` client built before the `BrokerClient` abstraction. Violates the DI rule. Currently wrapped inside `UpstoxLiveClient` — no other consumer should import it.

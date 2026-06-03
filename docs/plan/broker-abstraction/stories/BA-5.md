# BA-5 — Wire Dhan parsers into `factory.py` + integration smoke test

> Assigned to: Claude
> Phase: 2 — Dhan Integration
> Priority: LOW
> Blocked by: BA-3 and BA-4 must be merged first

---

## Goal

Extend `factory.py` (the sole composition root) to build and return a `DhanMarketDataParser`
and `DhanInstrumentKeyAdapter` when `UPSTOX_ENV=dhan`. Add a smoke test that exercises the
full parse path end-to-end using fixture data — no network calls.

---

## Context: current factory pattern

`factory.py` currently selects `BrokerClient` implementation based on `settings.upstox_env`.
The same env var gates the parser/adapter selection — a single env var controls the entire
broker stack, which is the right constraint for this project (one active broker at a time).

---

## Files to change

| File | Action |
|------|--------|
| `src/client/factory.py` | Add `build_market_data_parser()` factory function |
| `src/config.py` | Add `"dhan"` as a valid `upstox_env` literal (alongside `"prod"`, `"sandbox"`, `"test"`) |
| `tests/unit/client/test_factory_parsers.py` | New — factory selection tests + smoke test |

---

## What to implement

### `src/client/factory.py` — new function

```python
def build_market_data_parser(
    settings: Settings | None = None,
    adapter: InstrumentKeyAdapter | None = None,
) -> MarketDataParser:
    """Return the MarketDataParser for the active broker environment.

    Args:
        settings: Settings singleton. Uses module-level singleton if None.
        adapter: InstrumentKeyAdapter override (primarily for testing).
                 If None, builds the default adapter for the active env.

    Returns:
        MarketDataParser conforming to the protocol.

    Raises:
        ValueError: If upstox_env is set to an unrecognised broker string.
    """
    ...
```

Selection logic:
- `upstox_env in ("prod", "sandbox", "test")` → `UpstoxMarketDataParser()`
- `upstox_env == "dhan"` → `DhanMarketDataParser(adapter or _build_dhan_adapter())`
- anything else → `ValueError(f"Unknown broker env: {upstox_env}")`

`_build_dhan_adapter()` is a private helper that constructs `DhanInstrumentKeyAdapter`
with the production map path (`data/instruments/dhan_key_map.csv`).

### `src/config.py`

Extend the `upstox_env` literal type to include `"dhan"`:

```python
upstox_env: Literal["prod", "sandbox", "test", "dhan"] = "test"
```

---

## Tests — `tests/unit/client/test_factory_parsers.py`

1. **Upstox selection:** `upstox_env="prod"` → `build_market_data_parser()` returns `UpstoxMarketDataParser` instance.
2. **Upstox test env:** `upstox_env="test"` → also returns `UpstoxMarketDataParser`.
3. **Dhan selection:** `upstox_env="dhan"` with injected mock adapter → returns `DhanMarketDataParser`.
4. **Unknown env:** `upstox_env="unknown_broker"` → raises `ValueError`.
5. **Smoke test — Dhan parse:** with `upstox_env="dhan"`, injected `DhanInstrumentKeyAdapter` using fixture CSV, and Dhan chain fixture → `build_market_data_parser().parse_option_chain(fixture)` returns valid `OptionChain` with correct strike count.
6. **Protocol conformance:** returned parser from both `"prod"` and `"dhan"` paths satisfies `isinstance(..., MarketDataParser)`.

All tests use injected settings — no live API calls, no filesystem access except fixture CSV.

---

## Commit message

```
feat(client): wire Dhan parsers into factory + smoke test

Why: makes factory.py the sole composition root for broker selection,
     keeping all concrete broker imports out of feature code.
What:
- src/client/factory.py: build_market_data_parser() with env-based selection
- src/config.py: extend upstox_env Literal to include "dhan"
- tests/unit/client/test_factory_parsers.py: 6 factory + smoke tests
Ref: docs/plan/broker-abstraction/stories/BA-5.md
```

---

## Pre-baked graph context

```
search_graph("factory")                   # current factory.py — build_broker_client pattern
search_graph("build_broker_client")        # existing factory function signature to mirror
search_graph("Settings")                  # upstox_env field — current Literal values
search_graph("MarketDataParser")           # confirm BA-1 shipped
search_graph("DhanMarketDataParser")       # confirm BA-3 shipped
search_graph("DhanInstrumentKeyAdapter")   # confirm BA-4 shipped
```
